"""Executes a routing decision: primary -> bounded retries -> permitted fallbacks.

Rules:
- Only models in the decision's eligible chain are ever called. The router already applied every
  cost/tier/capability/provider filter, so fallbacks can't violate them. Health and the paid-model
  guard are re-checked immediately before each call (defence in depth).
- Same-model retries only for transient errors (timeout, 5xx, network), up to the provider's
  `max_retries` (OpenRouter: 0). Rate limits are never retried on the same model.
- Exponential backoff with full jitter. A Retry-After hint is honoured when it fits under the cap;
  a longer hint skips the retry and moves on.
- Non-fallback-eligible errors (bad request) stop immediately: another model would fail the same.
- One overall deadline bounds the whole request; each attempt's timeout is clipped to it.
- Every call that reached a provider becomes an AttemptRecord. Calls refused locally (quota
  guard, health changed mid-request) are listed as skipped, not as attempts.
- An attempt whose usage is unknown (timeout, 5xx, no usage block) draws its worst case from the
  budget cap, never 0; one that can't be bounded uses up the cap.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from time import monotonic, perf_counter

from app.accounting.cost import CostBreakdown, attempt_cost, budget_draw
from app.db.base import utcnow
from app.providers.base import (
    ATTEMPT_STATUS_FOR_KIND,
    REJECTED_BEFORE_GENERATION,
    Provider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from app.providers.catalog import ModelSpec
from app.resilience.health import HealthRegistry
from app.routing.engine import RoutingDecision

# Leave this much of the deadline unused rather than start an attempt that can't finish.
_MIN_ATTEMPT_S = 0.25


@dataclass
class AttemptRecord:
    attempt_number: int
    provider: str
    model_id: str
    reason_code: str
    status: str
    error_code: str | None
    http_status: int | None
    retry_after_s: float | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    latency_ms: int
    started_at: datetime
    finished_at: datetime
    simulated: bool
    usage_reported: bool
    cost: CostBreakdown
    # Tokens may have been consumed but weren't (fully) reported.
    usage_unknown: bool = False
    # Shadow-budget draw (see accounting.cost.budget_draw). None = can't be bounded.
    budget_draw_usd: Decimal | None = Decimal(0)


@dataclass
class ExecutionResult:
    response: ProviderResponse | None
    model: ModelSpec | None
    attempts: list[AttemptRecord] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    last_error: ProviderError | None = None
    # SUCCEEDED | ALL_CANDIDATES_FAILED | NON_RETRYABLE_ERROR | DEADLINE_EXCEEDED | NO_CANDIDATES
    outcome: str = "NO_CANDIDATES"

    def fallback_used(self, selected_key: str | None) -> bool:
        """True if any model other than the router's selection was called."""
        return any(f"{a.provider}/{a.model_id}" != selected_key for a in self.attempts)


class Executor:
    def __init__(
        self,
        providers: dict[str, Provider],
        health: HealthRegistry,
        *,
        deadline_s: float,
        default_timeout_s: float,
        backoff_base_s: float,
        backoff_cap_s: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.providers = providers
        self.health = health
        self.deadline_s = deadline_s
        self.default_timeout_s = default_timeout_s
        self.backoff_base_s = backoff_base_s
        self.backoff_cap_s = backoff_cap_s
        self._sleep = sleep
        self._rand = rand
        self._clock = clock

    def backoff_delay(self, retry_number: int, retry_after_s: float | None) -> float | None:
        """Delay before retry #`retry_number` (0-based), or None to skip the retry."""
        if retry_after_s is not None:
            return retry_after_s if retry_after_s <= self.backoff_cap_s else None
        ceiling = min(self.backoff_cap_s, self.backoff_base_s * (2.0**retry_number))
        return self._rand() * ceiling  # full jitter

    async def run(
        self,
        decision: RoutingDecision,
        models: dict[str, ModelSpec],
        template: ProviderRequest,
        *,
        budget_cap_usd: Decimal | None = None,
    ) -> ExecutionResult:
        """`budget_cap_usd`: the request's reservation. No attempt starts whose worst-case cost
        could push this request's estimated consumption past it."""
        result = ExecutionResult(response=None, model=None)
        deadline = self._clock() + self.deadline_s
        reason = "PRIMARY"
        consumed = Decimal(0)

        for candidate in decision.eligible:
            key = f"{candidate.provider}/{candidate.model_id}"
            model = models.get(key)
            provider = self.providers.get(candidate.provider)

            skip = None
            if model is None or provider is None:
                skip = "PROVIDER_DISABLED"
            elif model.billing != "free":
                skip = "PAID_MODEL_BLOCKED"  # unreachable via the router; kept as a hard stop
            else:
                skip = self.health.exclusion(candidate.provider, candidate.model_id)
                if skip is None and not provider.quota_available():
                    skip = "QUOTA_EXHAUSTED"
            if skip:
                result.skipped.append({"model": key, "reason": skip})
                continue
            assert model is not None and provider is not None

            retries = 0
            while True:
                if budget_cap_usd is not None:
                    worst = candidate.worst_case_list_cost_usd
                    if worst is None or consumed + Decimal(worst) > budget_cap_usd:
                        result.skipped.append({"model": key, "reason": "BUDGET_CONSTRAINT"})
                        break
                remaining = deadline - self._clock()
                if remaining < _MIN_ATTEMPT_S:
                    result.outcome = "DEADLINE_EXCEEDED"
                    return result
                timeout = min(model.timeout_s or self.default_timeout_s, remaining)
                request = replace(
                    template,
                    model_id=model.model_id,
                    timeout_s=timeout,
                    reasoning_effort=model.reasoning_effort,
                )

                self.health.on_call_started(model.provider, model.model_id)
                started_at = utcnow()
                t0 = perf_counter()
                try:
                    response = await provider.generate(request)
                except ProviderError as error:
                    self.health.record_failure(model.provider, model.model_id, error)
                    if not error.sent:
                        result.skipped.append({"model": key, "reason": error.code})
                        break
                    result.last_error = error
                    record = self._record(
                        result,
                        provider,
                        model,
                        reason,
                        started_at,
                        t0,
                        worst_case=candidate.worst_case_list_cost_usd,
                        error=error,
                    )
                    result.attempts.append(record)
                    if record.budget_draw_usd is None:
                        if budget_cap_usd is not None:
                            consumed = budget_cap_usd  # unbounded: no further attempt fits
                    else:
                        consumed += record.budget_draw_usd
                    if error.retryable and retries < provider.max_retries:
                        delay = self.backoff_delay(retries, error.retry_after_s)
                        if delay is not None and self._clock() + delay + _MIN_ATTEMPT_S < deadline:
                            await self._sleep(delay)
                            retries += 1
                            reason = f"RETRY_AFTER_{error.code}"
                            continue
                    if not error.fallback_eligible:
                        result.outcome = "NON_RETRYABLE_ERROR"
                        return result
                    reason = f"FALLBACK_AFTER_{error.code}"
                    break
                else:
                    self.health.record_success(model.provider, model.model_id, response.latency_ms)
                    result.attempts.append(
                        self._record(
                            result,
                            provider,
                            model,
                            reason,
                            started_at,
                            t0,
                            worst_case=candidate.worst_case_list_cost_usd,
                            response=response,
                        )
                    )
                    result.response = response
                    result.model = model
                    result.outcome = "SUCCEEDED"
                    return result

        result.outcome = "ALL_CANDIDATES_FAILED" if result.attempts else "NO_CANDIDATES"
        return result

    @staticmethod
    def _record(
        result: ExecutionResult,
        provider: Provider,
        model: ModelSpec,
        reason: str,
        started_at: datetime,
        t0: float,
        *,
        worst_case: str | None,
        response: ProviderResponse | None = None,
        error: ProviderError | None = None,
    ) -> AttemptRecord:
        usage = response.usage if response else (error.usage if error else None)
        latency_ms = response.latency_ms if response else int((perf_counter() - t0) * 1000)
        cost = attempt_cost(
            model, usage, simulated=provider.simulated, charge_basis=provider.charge_basis
        )
        rejected = error is not None and error.kind in REJECTED_BEFORE_GENERATION
        usage_complete = (
            usage is not None and usage.input_tokens is not None and usage.output_tokens is not None
        )
        usage_unknown = not usage_complete and not rejected
        return AttemptRecord(
            attempt_number=len(result.attempts) + 1,
            provider=model.provider,
            model_id=model.model_id,
            reason_code=reason,
            status="succeeded" if error is None else ATTEMPT_STATUS_FOR_KIND[error.kind],
            error_code=error.code if error else None,
            http_status=error.http_status if error else None,
            retry_after_s=error.retry_after_s if error else None,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            reasoning_tokens=usage.reasoning_tokens if usage else None,
            latency_ms=latency_ms,
            started_at=started_at,
            finished_at=utcnow(),
            simulated=provider.simulated,
            usage_reported=bool(
                usage and (usage.input_tokens is not None or usage.output_tokens is not None)
            ),
            cost=cost,
            usage_unknown=usage_unknown,
            budget_draw_usd=budget_draw(
                cost,
                usage_unknown=usage_unknown,
                rejected_before_generation=rejected,
                worst_case_usd=Decimal(worst_case) if worst_case is not None else None,
            ),
        )
