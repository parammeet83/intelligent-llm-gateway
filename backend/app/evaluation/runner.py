"""Benchmark runner: identical cases, interleaved strategies, full provenance.

Each strategy gets its own gateway instance (and fresh provider-health state) built by the same
factory as the API. Requests go through the real pipeline (routing, retries, fallbacks, cost
accounting, request logging) under a dedicated evaluation tenant with no budget.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.api.v1.schemas import GenerateRequest
from app.auth.keys import AuthenticatedTenant
from app.core.config import Settings
from app.core.errors import GatewayError
from app.db.models import EvaluationCase, EvaluationResult, EvaluationRun, Tenant
from app.db.session import Database
from app.evaluation import preflight
from app.evaluation.dataset import (
    EVAL_ROOT,
    Dataset,
    apply_review_attestation,
    apply_scoring_amendment,
    load_execution_revision,
    load_execution_schedule,
    load_preregistration,
    preregistration_path,
    schedule_day_cases,
)
from app.evaluation.pacing import (
    AttemptPacer,
    DailyBudget,
    PacedProvider,
    QuotaExhausted,
    QuotaLedger,
)
from app.evaluation.scorers import score
from app.providers.base import Provider
from app.routing.config import load_policy
from app.services.factory import build_gateway

logger = logging.getLogger(__name__)

EVAL_TENANT = "eval-runner"
EXCERPT_CHARS = 600
# Cases and strategies run strictly one request at a time (pinned in v4+ manifests).
RUN_CONCURRENCY = 1
# Persistent per-attempt quota ledger (git-ignored with the other reports).
DEFAULT_LEDGER = EVAL_ROOT / "reports" / "quota_ledger.json"

# Strategy name -> (policy overrides, request overrides). Same cases, same pipeline.
STRATEGIES: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "baseline_premium": ({}, {"preferred_tier": "premium"}),
    "routewise": ({}, {}),
    "routewise_tier_first": ({"selection": "lowest_tier_first"}, {}),
}


@dataclass
class CaseOutcome:
    case_id: str
    difficulty: str
    category: str
    strategy: str
    passed: bool | None
    score: float | None
    needs_human_review: bool
    error_code: str | None
    provider: str | None = None
    model: str | None = None
    tier: str | None = None
    fallback_used: bool = False
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_list_cost_usd: str | None = None
    list_cost_status: str = "unavailable"
    actual_charge_usd: str | None = None
    cost_status: str = "unavailable"
    simulated: bool = False
    request_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    # Model ID as reported by the provider for the answer (`model` is the registry ID).
    answer_model: str | None = None
    # Every provider call for this case, answered or not: attempt, provider, model, tier,
    # reason_code, status, error_code, latency_ms.
    attempts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    label: str
    simulated: bool
    dataset: str
    dataset_sha256: str
    dataset_fully_reviewed: bool
    preregistration: dict[str, Any]
    preregistration_sha256: str
    started_at: str
    finished_at: str
    config_snapshot: dict[str, Any]
    run_ids: dict[str, str]
    outcomes: list[CaseOutcome]
    incomplete: bool = False


async def _eval_tenant(db: Database) -> Tenant:
    async with db.sessionmaker() as session:
        tenant: Tenant | None = await session.scalar(
            select(Tenant).where(Tenant.slug == EVAL_TENANT)
        )
        if tenant is None:
            tenant = Tenant(
                slug=EVAL_TENANT,
                name="Benchmark runner (no budget)",
                rate_limit_rpm=100_000,
                daily_budget_usd=None,
                monthly_budget_usd=None,
            )
            session.add(tenant)
            await session.commit()
        return tenant


def config_snapshot(
    gateway: Any, providers: dict[str, Provider], settings: Settings
) -> dict[str, Any]:
    return {
        "policy": gateway.policy.model_dump(mode="json"),
        "providers": {
            name: {
                "simulated": p.simulated,
                "charge_basis": p.charge_basis,
                "max_retries": p.max_retries,
            }
            for name, p in sorted(providers.items())
        },
        "models": [
            {
                "key": m.key,
                "tier": m.tier,
                "enabled": m.enabled,
                "capabilities": m.capabilities,
                "verified_on": m.verified_on.isoformat() if m.verified_on else None,
                "pricing": None
                if m.pricing is None
                else {
                    "input_usd_per_mtok": str(m.pricing.input_usd_per_mtok),
                    "output_usd_per_mtok": str(m.pricing.output_usd_per_mtok),
                    "effective_date": m.pricing.effective_date.isoformat(),
                    "source_url": m.pricing.source_url,
                    "simulated": m.pricing.simulated,
                },
            }
            for m in gateway.models
        ],
        "settings": {
            "request_deadline_s": settings.request_deadline_s,
            "provider_timeout_s": settings.provider_timeout_s,
            "groq_billing_plan": settings.groq_billing_plan,
            "circuit_failure_threshold": settings.circuit_failure_threshold,
        },
    }


async def _upsert_cases(db: Database, dataset: Dataset) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    async with db.sessionmaker() as session:
        for case in dataset.cases:
            row = await session.scalar(
                select(EvaluationCase).where(
                    EvaluationCase.dataset_version == dataset.name,
                    EvaluationCase.case_key == case.id,
                )
            )
            payload = {
                "prompt": case.prompt,
                "task_type": case.task_type,
                "response_format": case.response_format,
                "max_output_tokens": case.max_output_tokens,
            }
            if row is None:
                row = EvaluationCase(dataset_version=dataset.name, case_key=case.id)
                session.add(row)
            row.category = case.category
            row.difficulty = case.difficulty
            row.payload = payload
            row.acceptance = {"expected": case.expected, "scoring": case.scoring}
            row.eval_method = str(case.scoring["method"])
            await session.flush()
            ids[case.id] = row.id
        await session.commit()
    return ids


async def run_benchmark(
    *,
    settings: Settings,
    db: Database,
    providers: dict[str, Provider],
    dataset: Dataset,
    strategies: list[str],
    label: str,
    allow_code_exec: bool = False,
    delay_s: float = 0.0,
    limit_cases: int | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    revision: str | None = None,
    daily_budget: DailyBudget | None = None,
    ledger_path: Path | None = None,
    accept_incomplete_risk: bool = False,
    schedule_day: int | None = None,
) -> BenchmarkResult:
    """`revision` selects an execution revision (e.g. routewise_bench_v5.1) of `dataset`.
    For manifests that pin `execution.attempt_quota` (v5.1+), every provider attempt reserves quota
    before transmission (PacedProvider), `daily_budget` is required, and the worst-case preflight
    must pass before any request is made. A revision with a registered execution schedule
    (v5.2.3+) runs one scheduled day per call (`schedule_day`); its preflight covers that day."""
    unknown = set(strategies) - set(STRATEGIES)
    if unknown:
        raise ValueError(f"unknown strategies: {sorted(unknown)}")
    if revision:
        prereg_path, pinned = load_execution_revision(revision, dataset)
        prereg, prereg_sha = load_preregistration(
            prereg_path, dataset=dataset, pinned_sha256=pinned
        )
    else:
        prereg, prereg_sha = load_preregistration(
            preregistration_path(dataset.name), dataset=dataset
        )
    # v5.2.1+: pre-registered scoring corrections for named cases (the dataset file is unchanged).
    dataset, scoring_amendment = apply_scoring_amendment(dataset, prereg)
    # v5.2.2+: review status from a pinned owner attestation (an in-memory overlay; fails closed).
    dataset, review_attestation = apply_review_attestation(dataset, prereg)
    # v5.2.3+: a registered multi-day schedule. Each call runs one day; a case's strategies stay
    # together on that day, so the paired comparison is preserved.
    schedule = load_execution_schedule(dataset, prereg)
    if schedule is None:
        if schedule_day is not None:
            raise ValueError("this pre-registration registers no execution schedule")
        indexed = list(enumerate(dataset.cases[:limit_cases] if limit_cases else dataset.cases))
    else:
        if schedule_day is None:
            raise ValueError(
                f"a {len(schedule['days'])}-day execution schedule is registered: pass the day "
                "(--schedule-day)"
            )
        if limit_cases:
            raise ValueError("limit_cases can't be combined with a registered execution schedule")
        indexed = schedule_day_cases(dataset, schedule, schedule_day)
    planned = dataset.model_copy(update={"cases": [case for _, case in indexed]})
    from app.evaluation.manifest import check_manifest

    manifest = check_manifest(
        prereg,
        settings,
        providers,
        strategies,
        run_params={
            "concurrency": RUN_CONCURRENCY,
            "delay_s": float(delay_s),
            "limit_cases": limit_cases,
            "allow_code_exec": allow_code_exec,
        },
    )
    execution = (manifest or {}).get("pinned", {}).get("execution", {})
    if execution.get("quota"):
        raise ValueError(
            "schema-3 (v5) quota pacing reserved once per gateway request and was superseded in "
            "v5.1; run the routewise_bench_v5.1 execution revision instead"
        )
    attempt_quotas = execution.get("attempt_quota") or {}
    if len(attempt_quotas) > 1:
        raise ValueError("attempt quota supports one quota-limited provider per run")
    pacer: AttemptPacer | None = None
    quota_report: dict[str, Any] | None = None
    if attempt_quotas:
        ((quota_provider, quota),) = attempt_quotas.items()
        ledger = QuotaLedger(ledger_path or DEFAULT_LEDGER, quota_provider)
        pre = preflight.evaluate(
            preflight.plan(planned, strategies, settings, providers, quota),
            quota,
            daily_budget,
            ledger,
            accept_incomplete_risk=accept_incomplete_risk,
        )
        if not pre.ok:
            raise ValueError("quota preflight failed: " + "; ".join(pre.problems))
        pacer = AttemptPacer(quota, daily_budget, ledger, sleep=sleep)
        providers = {
            name: PacedProvider(p, pacer) if name == quota_provider else p
            for name, p in providers.items()
        }
        quota_report = {
            "provider": quota_provider,
            "preflight": {
                "gateway_requests": pre.gateway_requests,
                "max_provider_attempts": pre.max_provider_attempts,
                "total_reservation_tokens": pre.total_reservation_tokens,
                "constraints": pre.constraints,
                "warnings": pre.warnings,
            },
            "accept_incomplete_risk": accept_incomplete_risk,
        }
    simulated = all(p.simulated for p in providers.values())
    tenant = await _eval_tenant(db)
    auth = AuthenticatedTenant(tenant=tenant, api_key_id=None, key_prefix="internal")
    base_policy = load_policy(settings.routing_policy_path)
    gateways = {
        name: build_gateway(
            settings, db, providers, policy=base_policy.model_copy(update=STRATEGIES[name][0])
        )
        for name in strategies
    }
    case_ids = await _upsert_cases(db, dataset)
    started = datetime.now(UTC)

    run_ids: dict[str, str] = {}
    snapshot = config_snapshot(gateways[strategies[0]], providers, settings)
    snapshot["manifest"] = (
        None
        if manifest is None
        else {
            "file": prereg["experiment_manifest"]["file"],
            "sha256": prereg["experiment_manifest"]["sha256"],
            "expected_models": manifest["pinned"]["expected_models"],
        }
    )
    snapshot["execution_revision"] = revision
    snapshot["scoring_amendment"] = scoring_amendment
    snapshot["review_attestation"] = review_attestation
    snapshot["execution_schedule"] = (
        None
        if schedule is None
        else {
            "file": schedule["file"],
            "sha256": schedule["sha256"],
            "day": schedule_day,
            "days": len(schedule["days"]),
            "case_ids": [case.id for _, case in indexed],
            "utc_date": started.astimezone(UTC).date().isoformat(),
        }
    )
    snapshot["quota"] = quota_report
    async with db.sessionmaker() as session:
        for name in strategies:
            run = EvaluationRun(
                label=label,
                strategy=name,
                dataset_version=dataset.name,
                policy_version=gateways[name].policy.version,
                config_snapshot={
                    **snapshot,
                    "policy": gateways[name].policy.model_dump(mode="json"),
                    "request_overrides": STRATEGIES[name][1],
                    "dataset_sha256": dataset.sha256,
                    "dataset_fully_reviewed": dataset.fully_reviewed,
                    "allow_code_exec": allow_code_exec,
                },
                preregistration_sha256=prereg_sha,
                simulated=simulated,
                status="running",
            )
            session.add(run)
            await session.flush()
            run_ids[name] = str(run.id)
        await session.commit()

    outcomes: list[CaseOutcome] = []
    incomplete = False
    stopped = False
    try:
        for index, case in indexed:
            order = strategies if index % 2 == 0 else list(reversed(strategies))
            for name in order:
                if pacer is not None:
                    # Wait (outside the measured request) until the first attempt fits; every
                    # attempt then reserves its own quota inside PacedProvider.
                    in_bound, out_bound = pacer.attempt_tokens(
                        [case.prompt], case.max_output_tokens
                    )
                    await pacer.wait_for(in_bound + out_bound)
                outcome = await _run_case(
                    gateways[name], auth, case, name, run_ids[name], allow_code_exec
                )
                outcome.simulated = outcome.simulated or simulated
                outcomes.append(outcome)
                await _persist(db, run_ids[name], case_ids[case.id], outcome)
                if pacer is not None and pacer.exhausted is not None:
                    # A blocked or over-bound attempt: stop, never complete over budget.
                    stopped = True
                    break
                if delay_s:
                    await sleep(delay_s)
            if stopped:
                break
        incomplete = stopped
    except QuotaExhausted:
        # Stop rather than exceed a limit; the run is incomplete and never publishable.
        incomplete = True
    except (KeyboardInterrupt, asyncio.CancelledError):
        incomplete = True
        raise
    finally:
        if pacer is not None and quota_report is not None:
            quota_report["stop_reason"] = pacer.exhausted
            quota_report["attempts_reserved"] = pacer.attempts
            if pacer.exhausted:
                incomplete = True
                logger.warning("benchmark_stopped_quota", extra={"reason": pacer.exhausted})
        async with db.sessionmaker() as session:
            for rid in run_ids.values():
                finished = await session.get(EvaluationRun, uuid.UUID(rid))
                if finished is not None:
                    finished.status = "failed" if incomplete else "completed"
                    finished.finished_at = datetime.now(UTC)
            await session.commit()

    return BenchmarkResult(
        label=label,
        simulated=simulated,
        dataset=dataset.name,
        dataset_sha256=dataset.sha256,
        dataset_fully_reviewed=dataset.fully_reviewed,
        preregistration=prereg,
        preregistration_sha256=prereg_sha,
        started_at=started.isoformat(),
        finished_at=datetime.now(UTC).isoformat(),
        config_snapshot=snapshot,
        run_ids=run_ids,
        outcomes=outcomes,
        incomplete=incomplete,
    )


async def _run_case(
    gateway: Any,
    auth: AuthenticatedTenant,
    case: Any,
    strategy: str,
    run_id: str,
    allow_code_exec: bool,
) -> CaseOutcome:
    body = GenerateRequest(
        prompt=case.prompt,
        task_type=case.task_type,
        response_format=case.response_format,
        max_output_tokens=case.max_output_tokens,
        request_id=f"eval-{run_id[:8]}-{case.id}",
        prompt_version=f"bench:{case.id}",
        **STRATEGIES[strategy][1],
    )
    base = {
        "case_id": case.id,
        "difficulty": case.difficulty,
        "category": case.category,
        "strategy": strategy,
        "needs_human_review": case.needs_human_review,
    }

    def with_tiers(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for a in attempts:
            spec = gateway.by_key.get(f"{a.get('provider')}/{a.get('model')}")
            out.append({**a, "tier": spec.tier if spec else None})
        return out

    try:
        response = await gateway.generate(auth, body, str(uuid.uuid4()))
    except GatewayError as error:
        failed_attempts = ((error.details or {}).get("fallback") or {}).get("attempts") or []
        return CaseOutcome(
            **base,
            passed=False,
            score=0.0,
            error_code=error.code,
            details={"error": error.message},
            attempts=with_tiers(list(failed_attempts)),
        )
    result = score(response.content, case.scoring, allow_code_exec=allow_code_exec)
    return CaseOutcome(
        answer_model=response.provider_reported_model,
        attempts=with_tiers([a.model_dump() for a in response.fallback.attempts]),
        **base,
        passed=result.passed,
        score=result.score,
        error_code=None,
        provider=response.provider,
        model=response.model,
        tier=response.tier,
        fallback_used=response.fallback.used,
        latency_ms=response.latency_ms,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        estimated_list_cost_usd=response.cost.estimated_list_cost_usd,
        list_cost_status=response.cost.list_cost_status,
        actual_charge_usd=response.cost.actual_charge_usd,
        cost_status=response.cost.cost_status,
        simulated=response.simulated,
        request_id=response.request_id,
        details={**result.details, "output_excerpt": response.content[:EXCERPT_CHARS]},
    )


async def _persist(db: Database, run_id: str, case_uuid: uuid.UUID, outcome: CaseOutcome) -> None:
    async with db.sessionmaker() as session:
        session.add(
            EvaluationResult(
                run_id=uuid.UUID(run_id),
                case_id=case_uuid,
                request_log_id=uuid.UUID(outcome.request_id) if outcome.request_id else None,
                passed=outcome.passed,
                score=outcome.score,
                provider=outcome.provider,
                model_id=outcome.model,
                routing_tier=outcome.tier,
                fallback_used=outcome.fallback_used,
                error_code=outcome.error_code,
                scorer_details=outcome.details,
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
                latency_ms=outcome.latency_ms,
                estimated_list_cost_usd=Decimal(outcome.estimated_list_cost_usd)
                if outcome.estimated_list_cost_usd
                else None,
                list_cost_status=outcome.list_cost_status,
                actual_charge_usd=Decimal(outcome.actual_charge_usd)
                if outcome.actual_charge_usd
                else None,
                cost_status=outcome.cost_status,
                simulated=outcome.simulated,
            )
        )
        await session.commit()


def outcome_dicts(result: BenchmarkResult) -> list[dict[str, Any]]:
    return [asdict(o) for o in result.outcomes]
