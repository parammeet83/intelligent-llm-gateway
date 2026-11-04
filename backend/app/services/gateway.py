"""Orchestrates one /generate request: route -> log (idempotent) -> execute -> persist -> respond.

Persistence happens in two commits:
  1. A `pending` request_logs row with the routing decision. The unique (tenant_id,
     client_request_id) constraint makes duplicate request IDs fail here, before any provider
     call, including concurrent duplicates.
  2. The settled outcome plus one request_attempts row per provider call.
If the process dies between the two, the row stays `pending` (visible, never silently lost).

Prompt and response text are not stored: only a SHA-256 of the messages and their length.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import date
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.accounting import budget
from app.accounting.cost import CostBreakdown, settle_request
from app.api.v1 import schemas
from app.auth.keys import AuthenticatedTenant
from app.core.errors import GatewayError
from app.db.base import utcnow
from app.db.models import PricingSnapshot, RequestAttempt, RequestLog, Tenant
from app.db.session import Database
from app.providers.base import ChatMessage, Provider, ProviderRequest
from app.providers.catalog import ModelSpec
from app.resilience.health import HealthRegistry
from app.routing.config import RoutingPolicyConfig
from app.routing.engine import RoutingDecision, RoutingRequest, route
from app.services.executor import ExecutionResult, Executor
from app.tenancy import rate_limit

logger = logging.getLogger(__name__)

# Reserve up to this multiple of the most expensive eligible model's worst-case cost (capped by
# the remaining budget), so a retry or fallback can run inside the same reservation.
RESERVATION_MULTIPLIER = Decimal(3)

_FAILURE_STATUS = {
    "ALL_CANDIDATES_FAILED": (502, "ALL_PROVIDERS_FAILED", "Every eligible model failed."),
    "NON_RETRYABLE_ERROR": (
        502,
        "UPSTREAM_REJECTED_REQUEST",
        "The provider rejected the request; other models would reject it too.",
    ),
    "DEADLINE_EXCEEDED": (504, "DEADLINE_EXCEEDED", "The request deadline was reached."),
    "NO_CANDIDATES": (
        503,
        "NO_AVAILABLE_PROVIDER",
        "No eligible model could be called (quota, health, or availability).",
    ),
}


def _money(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def prompt_digest(messages: tuple[ChatMessage, ...]) -> str:
    canonical = json.dumps(
        [[m.role, m.content] for m in messages], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def cost_note(cost: CostBreakdown, simulated: bool, *, usage_unknown: int = 0) -> str:
    if simulated:
        return (
            "Simulated response from the mock provider: "
            "no real model was called and no charge applies."
        )
    parts = {
        "reported": "Actual charge as reported by the provider.",
        "free_tier": "Actual charge: $0 under the provider's free tier.",
        "estimated": "Actual charge estimated from verified prices.",
        "unavailable": "Actual charge unknown.",
    }
    note = parts[cost.cost_status]
    if cost.list_cost_status == "estimated":
        note += (
            " The estimated list cost is a shadow figure at published pay-as-you-go prices"
            f" (as of {cost.pricing_effective_date}); it is not money spent."
        )
    elif usage_unknown:
        note += (
            f" List cost unknown: {usage_unknown} attempt(s) may have consumed tokens the provider"
            " didn't report; any tenant budget was charged their worst case."
        )
    else:
        note += " No verified list price is available for this request."
    return note


class GatewayService:
    def __init__(
        self,
        *,
        db: Database,
        models: list[ModelSpec],
        policy: RoutingPolicyConfig,
        health: HealthRegistry,
        providers: dict[str, Provider],
        executor: Executor,
    ) -> None:
        self.db = db
        self.models = models
        self.by_key = {m.key: m for m in models}
        self.policy = policy
        self.health = health
        self.providers = providers
        self.executor = executor
        self._snapshot_ids: dict[tuple[str, str, date], uuid.UUID | None] = {}

    @property
    def enabled_providers(self) -> frozenset[str]:
        return frozenset(self.providers)

    @property
    def simulated_providers(self) -> frozenset[str]:
        return frozenset(name for name, p in self.providers.items() if p.simulated)

    def decide(
        self,
        body: schemas.GenerateRequest,
        messages: tuple[ChatMessage, ...],
        budget_remaining: Decimal | None = None,
    ) -> RoutingDecision:
        constraints = body.constraints
        return route(
            RoutingRequest(
                messages=messages,
                task_type=body.task_type,
                max_output_tokens=body.max_output_tokens,
                response_format=body.response_format,
                quality=body.quality,
                priority=body.priority,
                preferred_tier=body.preferred_tier,
                allow_downgrade=body.allow_downgrade,
                latency_target_ms=body.latency_target_ms,
                max_cost_usd=body.max_cost_usd,
                allowed_providers=frozenset(constraints.providers)
                if constraints and constraints.providers is not None
                else None,
                allowed_models=frozenset(constraints.models)
                if constraints and constraints.models is not None
                else None,
                # Read here only to filter candidates; enforcement is the atomic reservation.
                budget_remaining_usd=budget_remaining,
            ),
            models=self.models,
            enabled_providers=self.enabled_providers,
            simulated_providers=self.simulated_providers,
            policy=self.policy,
            health=self.health,
        )

    async def generate(
        self, auth: AuthenticatedTenant, body: schemas.GenerateRequest, request_id: str
    ) -> schemas.GenerateResponse:
        started = perf_counter()
        tenant = auth.tenant
        log_id = uuid.UUID(request_id)
        messages = (
            tuple(ChatMessage(role=m.role, content=m.content) for m in body.messages)
            if body.messages
            else (ChatMessage(role="user", content=body.prompt or ""),)
        )

        # 1. Rate limit (before any routing work). Rejections are logged for the metrics.
        async with self.db.sessionmaker() as session:
            limited = await rate_limit.hit(session, tenant.id, tenant.rate_limit_rpm)
        if not limited.allowed:
            await self._log_rejection(
                auth, body, messages, log_id, "rejected_rate_limit", "RATE_LIMITED"
            )
            raise GatewayError(
                "RATE_LIMITED",
                f"Tenant rate limit of {limited.limit} requests/minute exceeded.",
                status_code=429,
                details={"limit_rpm": limited.limit, "retry_after_s": limited.retry_after_s},
                headers={"Retry-After": str(limited.retry_after_s)},
            )

        # 2. Route with the current budget headroom (a read; enforcement is step 4).
        async with self.db.sessionmaker() as session:
            headroom = await budget.remaining(session, tenant)
        decision = self.decide(body, messages, headroom)
        await self._insert_pending(auth, body, messages, decision, log_id)

        # 3. Nothing eligible.
        if decision.selected is None:
            # The tenant budget (not the request's own max_cost_usd) is what ruled models out.
            tenant_budget_binding = headroom is not None and (
                headroom <= 0
                or (
                    "BUDGET_CONSTRAINT" in decision.reason_codes
                    and (body.max_cost_usd is None or headroom < body.max_cost_usd)
                )
            )
            if tenant_budget_binding:
                await self._finalize(
                    log_id, decision, None, status="rejected_budget", error_code="BUDGET_EXHAUSTED"
                )
                raise self._budget_error(decision)
            await self._finalize(
                log_id, decision, None, status="rejected_policy", error_code="NO_ELIGIBLE_MODEL"
            )
            raise GatewayError(
                "NO_ELIGIBLE_MODEL",
                "No configured model satisfies this request's constraints.",
                status_code=422,
                details={"routing": self._routing(decision).model_dump()},
            )

        # 4. Atomic reservation, recorded on the request row in the same transaction.
        reservation: list[dict[str, Any]] = []
        cap: Decimal | None = None
        if headroom is not None:
            worst = max(Decimal(c.worst_case_list_cost_usd or 0) for c in decision.eligible)
            cap = min(headroom, worst * RESERVATION_MULTIPLIER)
            try:
                reservation = await self._reserve(tenant, log_id, cap)
            except budget.BudgetExhausted:
                await self._finalize(
                    log_id, decision, None, status="rejected_budget", error_code="BUDGET_EXHAUSTED"
                )
                raise self._budget_error(decision) from None

        # 5. Execute within the reservation.
        template = ProviderRequest(
            model_id="",
            messages=messages,
            max_output_tokens=body.max_output_tokens,
            temperature=body.temperature,
            response_format=body.response_format,
        )
        result = await self.executor.run(decision, self.by_key, template, budget_cap_usd=cap)
        total_ms = int((perf_counter() - started) * 1000)
        settled = settle_request(
            [(a.cost, a.usage_reported) for a in result.attempts],
            succeeded=result.response is not None,
            usage_unknown=any(a.usage_unknown for a in result.attempts),
        )

        if result.response is None or result.model is None:
            http_status, code, message = _FAILURE_STATUS[result.outcome]
            await self._finalize(
                log_id,
                decision,
                result,
                status="failed",
                error_code=code,
                settled=settled,
                total_ms=total_ms,
                tenant_id=tenant.id,
                reservation=reservation,
            )
            raise GatewayError(
                code,
                message,
                status_code=http_status,
                details={"fallback": self._fallback(decision, result).model_dump()},
            )

        await self._finalize(
            log_id,
            decision,
            result,
            status="succeeded",
            settled=settled,
            total_ms=total_ms,
            tenant_id=tenant.id,
            reservation=reservation,
        )
        final = result.attempts[-1]
        return schemas.GenerateResponse(
            request_id=request_id,
            client_request_id=body.request_id,
            tenant=tenant.slug,
            simulated=result.response.simulated,
            content=result.response.content,
            finish_reason=result.response.finish_reason,
            provider=result.model.provider,
            model=result.model.model_id,
            provider_reported_model=result.response.model_id,
            tier=result.model.tier,
            routing=self._routing(decision),
            usage=schemas.Usage(
                input_tokens=final.input_tokens,
                output_tokens=final.output_tokens,
                total_tokens=(final.input_tokens or 0) + (final.output_tokens or 0)
                if final.input_tokens is not None and final.output_tokens is not None
                else None,
                reasoning_tokens=final.reasoning_tokens,
            ),
            latency_ms=total_ms,
            provider_latency_ms=final.latency_ms,
            cost=schemas.Cost(
                actual_charge_usd=_money(settled.actual_charge_usd),
                cost_status=settled.cost_status,
                estimated_list_cost_usd=_money(settled.estimated_list_cost_usd),
                list_cost_status=settled.list_cost_status,
                pricing_effective_date=settled.pricing_effective_date,
                pricing_source_url=settled.pricing_source_url,
                note=cost_note(
                    settled,
                    result.response.simulated,
                    usage_unknown=sum(a.usage_unknown for a in result.attempts),
                ),
            ),
            fallback=self._fallback(decision, result),
        )

    # --- response building ----------------------------------------------------------------

    @staticmethod
    def _routing(decision: RoutingDecision) -> schemas.Routing:
        return schemas.Routing(
            policy_version=decision.policy_version,
            task_type=decision.task_type,
            score=decision.score,
            computed_tier=decision.computed_tier,
            required_tier=decision.required_tier,
            reason_codes=list(decision.reason_codes),
            explanation=decision.explanation(),
            contributions=[
                {"feature": c.feature, "points": c.points, "detail": c.detail}
                for c in decision.contributions
            ],
            fallback_chain=[f"{c.provider}/{c.model_id}" for c in decision.fallback_chain],
            excluded=[
                {
                    "model": f"{c.provider}/{c.model_id}",
                    "tier": c.tier,
                    "reasons": list(c.exclusions),
                }
                for c in decision.candidates
                if not c.eligible
            ],
        )

    @staticmethod
    def _fallback(decision: RoutingDecision, result: ExecutionResult) -> schemas.Fallback:
        selected = (
            f"{decision.selected.provider}/{decision.selected.model_id}"
            if decision.selected
            else None
        )
        return schemas.Fallback(
            used=result.fallback_used(selected),
            attempts=[
                schemas.AttemptSummary(
                    attempt=a.attempt_number,
                    provider=a.provider,
                    model=a.model_id,
                    reason_code=a.reason_code,
                    status=a.status,
                    error_code=a.error_code,
                    latency_ms=a.latency_ms,
                )
                for a in result.attempts
            ],
            skipped=result.skipped,
            failed_attempts_without_usage=sum(
                1 for a in result.attempts if a.status != "succeeded" and not a.usage_reported
            ),
        )

    # --- persistence ----------------------------------------------------------------------

    @staticmethod
    def _budget_error(decision: RoutingDecision) -> GatewayError:
        return GatewayError(
            "BUDGET_EXHAUSTED",
            "The tenant's daily or monthly budget can't cover this request.",
            status_code=402,
            details={"routing": GatewayService._routing(decision).model_dump()},
        )

    async def _log_rejection(
        self,
        auth: AuthenticatedTenant,
        body: schemas.GenerateRequest,
        messages: tuple[ChatMessage, ...],
        log_id: uuid.UUID,
        status: str,
        error_code: str,
    ) -> None:
        """Record a request rejected before routing. The client's request_id is kept out of the
        idempotency column so the client can retry with the same ID once allowed."""
        async with self.db.sessionmaker() as session:
            session.add(
                RequestLog(
                    id=log_id,
                    tenant_id=auth.tenant.id,
                    api_key_id=auth.api_key_id,
                    status=status,
                    error_code=error_code,
                    task_type=body.task_type,
                    prompt_version=body.prompt_version,
                    prompt_sha256=prompt_digest(messages),
                    input_chars=sum(len(m.content) for m in messages),
                    decision={
                        "client_request_id": body.request_id,
                        "rejected_before_routing": True,
                    },
                    completed_at=utcnow(),
                )
            )
            await session.commit()

    async def _reserve(
        self, tenant: Tenant, log_id: uuid.UUID, amount: Decimal
    ) -> list[dict[str, Any]]:
        async with self.db.sessionmaker() as session:
            reservation = await budget.reserve(session, tenant, amount, commit=False)
            log = await session.get(RequestLog, log_id)
            assert log is not None
            log.budget_reservation = reservation
            await session.commit()
        return reservation

    async def _insert_pending(
        self,
        auth: AuthenticatedTenant,
        body: schemas.GenerateRequest,
        messages: tuple[ChatMessage, ...],
        decision: RoutingDecision,
        log_id: uuid.UUID,
    ) -> None:
        tenant = auth.tenant
        async with self.db.sessionmaker() as session:
            session.add(
                RequestLog(
                    id=log_id,
                    tenant_id=tenant.id,
                    api_key_id=auth.api_key_id,
                    client_request_id=body.request_id,
                    status="pending",
                    task_type=body.task_type,
                    prompt_version=body.prompt_version,
                    prompt_sha256=prompt_digest(messages),
                    input_chars=sum(len(m.content) for m in messages),
                    routing_tier=decision.required_tier,
                    policy_version=decision.policy_version,
                    decision=decision.to_dict(),
                    simulated=bool(decision.selected and decision.selected.simulated),
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(RequestLog).where(
                        RequestLog.tenant_id == tenant.id,
                        RequestLog.client_request_id == body.request_id,
                    )
                )
                raise GatewayError(
                    "DUPLICATE_REQUEST_ID",
                    "A request with this request_id was already received for this tenant.",
                    status_code=409,
                    details={
                        "original_request_id": str(existing.id) if existing else None,
                        "original_status": existing.status if existing else None,
                    },
                ) from None

    async def _snapshot_id(self, model: ModelSpec) -> uuid.UUID | None:
        if model.pricing is None:
            return None
        key = (model.provider, model.model_id, model.pricing.effective_date)
        if key not in self._snapshot_ids:
            async with self.db.sessionmaker() as session:
                self._snapshot_ids[key] = await session.scalar(
                    select(PricingSnapshot.id).where(
                        PricingSnapshot.provider == model.provider,
                        PricingSnapshot.model_id == model.model_id,
                        PricingSnapshot.effective_date == model.pricing.effective_date,
                    )
                )
        return self._snapshot_ids[key]

    async def _finalize(
        self,
        log_id: uuid.UUID,
        decision: RoutingDecision,
        result: ExecutionResult | None,
        *,
        status: str,
        error_code: str | None = None,
        settled: CostBreakdown | None = None,
        total_ms: int | None = None,
        tenant_id: uuid.UUID | None = None,
        reservation: list[dict[str, Any]] | None = None,
    ) -> None:
        attempts = result.attempts if result else []
        snapshot_ids = {
            f"{a.provider}/{a.model_id}": await self._snapshot_id(
                self.by_key[f"{a.provider}/{a.model_id}"]
            )
            for a in attempts
        }

        def total(attr: str) -> int | None:
            values = [getattr(a, attr) for a in attempts if getattr(a, attr) is not None]
            return sum(values) if values else None

        # Budget draw: known list costs, worst case for unknown usage, and the whole reservation
        # if any attempt can't be bounded. Never 0 for tokens that may have been consumed.
        draws = [a.budget_draw_usd for a in attempts]
        held = max((Decimal(item["amount"]) for item in reservation or []), default=Decimal(0))
        consumed = (
            held
            if any(d is None for d in draws)
            else sum((d for d in draws if d is not None), Decimal(0))
        )

        stored_decision: dict[str, Any] = decision.to_dict()
        if result is not None:
            stored_decision["execution"] = {
                "outcome": result.outcome,
                "skipped": result.skipped,
                "usage_unknown_attempts": sum(a.usage_unknown for a in attempts),
                # No column for it; kept here so reasoning overhead stays auditable.
                "reasoning_tokens": [a.reasoning_tokens for a in attempts],
                "budget_charged_usd": str(consumed) if reservation else None,
            }

        async with self.db.sessionmaker() as session:
            log = await session.get(RequestLog, log_id)
            assert log is not None
            log.status = status
            log.error_code = error_code
            log.decision = stored_decision
            log.completed_at = utcnow()
            log.latency_ms = total_ms
            log.attempt_count = len(attempts)
            if result is not None and result.model is not None:
                log.selected_provider = result.model.provider
                log.selected_model = result.model.model_id
                log.routing_tier = result.model.tier
                log.simulated = result.response.simulated if result.response else log.simulated
            elif decision.selected is not None:
                log.selected_provider = decision.selected.provider
                log.selected_model = decision.selected.model_id
            selected = (
                f"{decision.selected.provider}/{decision.selected.model_id}"
                if decision.selected
                else None
            )
            log.fallback_used = bool(result and result.fallback_used(selected))
            log.input_tokens = total("input_tokens")
            log.output_tokens = total("output_tokens")
            if settled is not None:
                log.actual_charge_usd = settled.actual_charge_usd
                log.cost_status = settled.cost_status
                log.estimated_list_cost_usd = settled.estimated_list_cost_usd
                log.list_cost_status = settled.list_cost_status
            if reservation and tenant_id is not None:
                # Settled in the same transaction as the attempt rows: spend and records
                # can't disagree.
                await budget.settle(session, tenant_id, reservation, consumed)
                log.budget_reservation = None
            for a in attempts:
                session.add(
                    RequestAttempt(
                        request_id=log_id,
                        attempt_number=a.attempt_number,
                        provider=a.provider,
                        model_id=a.model_id,
                        reason_code=a.reason_code,
                        status=a.status,
                        error_code=a.error_code,
                        http_status=a.http_status,
                        retry_after_s=a.retry_after_s,
                        input_tokens=a.input_tokens,
                        output_tokens=a.output_tokens,
                        latency_ms=a.latency_ms,
                        started_at=a.started_at,
                        finished_at=a.finished_at,
                        simulated=a.simulated,
                        actual_charge_usd=a.cost.actual_charge_usd,
                        cost_status=a.cost.cost_status,
                        estimated_list_cost_usd=a.cost.estimated_list_cost_usd,
                        list_cost_status=a.cost.list_cost_status,
                        pricing_snapshot_id=snapshot_ids.get(f"{a.provider}/{a.model_id}"),
                    )
                )
            await session.commit()
        logger.info(
            "generate_completed",
            extra={
                "request_id": str(log_id),
                "status": status,
                "error_code": error_code,
                "attempts": len(attempts),
                "policy_version": decision.policy_version,
            },
        )
