"""Benchmark runner: identical cases, interleaved strategies, full provenance.

Each strategy gets its own gateway instance (and fresh provider-health state) built by the same
factory as the API. Requests go through the real pipeline (routing, retries, fallbacks, cost
accounting, request logging) under a dedicated evaluation tenant with no budget.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.exc import InterfaceError as SAInterfaceError

from app.api.v1.schemas import GenerateRequest
from app.auth.keys import AuthenticatedTenant
from app.core.config import Settings
from app.core.errors import GatewayError
from app.db.models import (
    BenchmarkExecutionClaim,
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    Tenant,
)
from app.db.session import Database
from app.evaluation import preflight
from app.evaluation.dataset import (
    EVAL_ROOT,
    Dataset,
    apply_review_attestation,
    apply_scoring_amendment,
    load_execution_recovery,
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

# v5.2.4: bounded backoff for database operations (6 tries over about 31 s). A Neon outage that
# outlasts it stops the run (fail closed) instead of losing or guessing a result.
DB_RETRY_DELAYS_S = (1.0, 2.0, 4.0, 8.0, 16.0)


class DatabaseUnavailable(RuntimeError):
    """The database couldn't record or confirm benchmark state within the bounded retries."""


class CombinationStateUnknown(RuntimeError):
    """A database error hit a combination after a provider attempt may have been sent. Such a
    combination is never retried (that could repeat a provider request); the run stops."""


def is_transient_db_error(error: BaseException) -> bool:
    """Connection-level database failures (timeouts, dropped or refused connections). A constraint
    violation or a schema problem (e.g. a missing table) is not transient and is never retried."""
    if isinstance(error, (IntegrityError, ProgrammingError)):
        return False
    return isinstance(
        error,
        (
            DBAPIError,
            OperationalError,
            SAInterfaceError,
            asyncpg.PostgresConnectionError,
            asyncpg.InterfaceError,
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )


async def with_db_retry[T](
    op: Callable[[], Awaitable[T]],
    what: str,
    sleep: Callable[[float], Awaitable[None]],
) -> T:
    """Run a database operation, retrying transient failures with bounded backoff. Callers make
    `op` idempotent, so a retry after an ambiguous commit can't duplicate anything."""
    last: BaseException | None = None
    for attempt, delay in enumerate((0.0, *DB_RETRY_DELAYS_S)):
        if delay:
            await sleep(delay)
        try:
            return await op()
        except Exception as error:
            if not is_transient_db_error(error):
                raise
            last = error
            logger.warning(
                "benchmark_db_retry",
                extra={"operation": what, "attempt": attempt + 1, "error": type(error).__name__},
            )
    raise DatabaseUnavailable(
        f"{what}: the database was unavailable after {len(DB_RETRY_DELAYS_S) + 1} attempts"
    ) from last


def check_execution_window(prereg: dict[str, Any], day: int, now: datetime) -> None:
    """A registered execution window (v5.2.5+): only its days may run, on a UTC date inside the
    window and no later than its latest start time. Raises ValueError otherwise."""
    window = prereg.get("execution_window")
    if not window:
        return
    days = [int(d) for d in window["days"]]
    if day not in days:
        raise ValueError(f"this registration authorises day(s) {days} only, not day {day}")
    moment = now.astimezone(UTC)
    earliest = date.fromisoformat(str(window["earliest_utc_date"]))
    latest = date.fromisoformat(str(window["latest_utc_date"]))
    if not earliest <= moment.date() <= latest:
        raise ValueError(
            f"outside the registered execution window ({earliest} to {latest} UTC): "
            f"today is {moment.date()}"
        )
    if moment.time() > time.fromisoformat(str(window["latest_start_utc"])):
        raise ValueError(
            f"after the registered latest start time ({window['latest_start_utc']} UTC)"
        )


async def scheduled_day_started(
    db: Database, revision: str, day: int, sleep: Callable[[float], Awaitable[None]]
) -> list[str]:
    """Read-only: every execution claim and every evaluation run (any status) already recorded for
    this revision's scheduled day. Unreachable database or missing claims table: raises (callers
    fail closed)."""

    async def once() -> list[str]:
        async with db.sessionmaker() as session:
            claims = (
                await session.scalars(
                    select(BenchmarkExecutionClaim).where(
                        BenchmarkExecutionClaim.revision == revision,
                        BenchmarkExecutionClaim.schedule_day == day,
                    )
                )
            ).all()
            runs = (await session.scalars(select(EvaluationRun))).all()
        found = [f"claim {c.id} ({c.claimed_at:%Y-%m-%d %H:%M} UTC)" for c in claims]
        for r in runs:
            snap = r.config_snapshot or {}
            if (
                snap.get("execution_revision") == revision
                and (snap.get("execution_schedule") or {}).get("day") == day
            ):
                found.append(f"run {r.id} ({r.status})")
        return found

    return await with_db_retry(once, "check whether the scheduled day already started", sleep)


async def claim_scheduled_day(
    db: Database,
    revision: str,
    day: int,
    label: str,
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    """Atomically claim a revision's scheduled day. The unique (revision, schedule_day) constraint
    lets exactly one of several concurrent starts insert its claim; every other start (and any
    later one) is refused. A claim is never removed, so a failed day can't be restarted. If a
    commit's acknowledgement is lost, the retry hits the constraint and refuses (safe: the day is
    then claimed but nothing runs)."""

    async def once() -> None:
        async with db.sessionmaker() as session:
            session.add(BenchmarkExecutionClaim(revision=revision, schedule_day=day, label=label))
            await session.commit()

    try:
        await with_db_retry(once, "claim the scheduled day", sleep)
    except IntegrityError:
        raise ValueError(
            f"{revision} day {day} is already claimed: a scheduled day never starts twice"
        ) from None


async def finalize_runs(
    db: Database,
    run_ids: list[str],
    status: str,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Move these runs from `running` to `status` (idempotent: runs already finished keep their
    status and finish time). Retried with backoff. Returns the number of runs changed."""

    async def once() -> int:
        async with db.sessionmaker() as session:
            changed = await session.execute(
                update(EvaluationRun)
                .where(
                    EvaluationRun.id.in_([uuid.UUID(r) for r in run_ids]),
                    EvaluationRun.status == "running",
                )
                .values(status=status, finished_at=datetime.now(UTC))
            )
            await session.commit()
            return int(getattr(changed, "rowcount", 0) or 0)

    return await with_db_retry(once, "finalise evaluation runs", sleep)


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
        # v5.2.5+: a registered execution window limits which days may run, and when.
        check_execution_window(prereg, schedule_day, datetime.now(UTC))
    # v5.2.4+: a registered, disclosed recovery of an interrupted day. Only its listed combinations
    # run; genuine results the interrupted runs already persisted are carried over, never re-run.
    recovery = load_execution_recovery(dataset, prereg, schedule)
    only: set[tuple[str, str]] | None = None
    if recovery is not None:
        if schedule_day != recovery["day"]:
            raise ValueError(
                f"the registered recovery is for day {recovery['day']}: "
                f"pass --schedule-day {recovery['day']}"
            )
        absent = {s for _, s in recovery["execute"]} - set(strategies)
        if absent:
            raise ValueError(f"the registered recovery needs strategies {sorted(absent)}")
        only = set(recovery["execute"])
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
            preflight.plan(planned, strategies, settings, providers, quota, only=only),
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
    if recovery is not None:
        await _refuse_started_recovery(db, recovery["sha256"], sleep)
    if schedule is not None and schedule_day is not None and revision:
        # v5.2.5+: a scheduled day starts at most once per revision. Read-only check first (also
        # covers runs that predate claims), then the atomic claim that wins against concurrent
        # starts. Any database doubt raises: fail closed, before any run or provider call.
        already = await scheduled_day_started(db, revision, schedule_day, sleep)
        if already:
            raise ValueError(
                f"{revision} day {schedule_day} already started ({'; '.join(already)}): "
                "a scheduled day never starts twice"
            )
        await claim_scheduled_day(db, revision, schedule_day, label, sleep)
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
    snapshot["execution_recovery"] = (
        None
        if recovery is None
        else {
            "file": recovery["file"],
            "sha256": recovery["sha256"],
            "day": recovery["day"],
            "executes": [list(c) for c in recovery["execute"]],
            "carried_over": len(recovery["carried_over"]),
            "original_runs": recovery["original_runs"],
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
    failure: BaseException | None = None
    try:
        for index, case in indexed:
            order = strategies if index % 2 == 0 else list(reversed(strategies))
            for name in order:
                if only is not None and (case.id, name) not in only:
                    continue  # recovery: carried over from the interrupted run, never re-run
                if pacer is not None:
                    # Wait (outside the measured request) until the first attempt fits; every
                    # attempt then reserves its own quota inside PacedProvider.
                    in_bound, out_bound = pacer.attempt_tokens(
                        [case.prompt], case.max_output_tokens
                    )
                    await pacer.wait_for(in_bound + out_bound)
                outcome = await _run_case_retrying_db(
                    functools.partial(
                        _run_case, gateways[name], auth, case, name, run_ids[name], allow_code_exec
                    ),
                    pacer,
                    sleep,
                    f"{name}/{case.id}",
                )
                outcome.simulated = outcome.simulated or simulated
                outcomes.append(outcome)
                await _persist(db, run_ids[name], case_ids[case.id], outcome, sleep)
                if pacer is not None and pacer.exhausted is not None:
                    # A blocked or over-bound attempt: stop, never complete over budget.
                    stopped = True
                    break
                if delay_s:
                    await sleep(delay_s)
            if stopped:
                break
        incomplete = stopped
        # A run is complete only if the database confirms every outcome was persisted.
        if not await _all_persisted(db, run_ids, outcomes, sleep):
            incomplete = True
    except QuotaExhausted:
        # Stop rather than exceed a limit; the run is incomplete and never publishable.
        incomplete = True
    except BaseException as error:
        # Any other failure (a database outage, an interrupt, a bug) also makes the run incomplete.
        # It stays the exception the caller sees: finalisation problems below are attached to it
        # as a note and never raised over it.
        incomplete = True
        failure = error
        raise
    finally:
        if pacer is not None and quota_report is not None:
            quota_report["stop_reason"] = pacer.exhausted
            quota_report["attempts_reserved"] = pacer.attempts
            if pacer.exhausted:
                incomplete = True
                logger.warning("benchmark_stopped_quota", extra={"reason": pacer.exhausted})
        status = "failed" if incomplete else "completed"
        try:
            await finalize_runs(db, list(run_ids.values()), status, sleep)
        except Exception as fin_error:
            logger.error(
                "benchmark_finalize_failed",
                extra={"runs": sorted(run_ids.values()), "error": type(fin_error).__name__},
            )
            if failure is None:
                raise
            failure.add_note(
                f"finalising runs {sorted(run_ids.values())} as {status!r} also failed "
                f"({type(fin_error).__name__}); close them with `eval-finalize-runs`"
            )

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


async def _run_case_retrying_db(
    run: Callable[[], Awaitable[CaseOutcome]],
    pacer: AttemptPacer | None,
    sleep: Callable[[float], Awaitable[None]],
    what: str,
) -> CaseOutcome:
    """Run one combination. A transient database error is retried (bounded backoff) only when the
    quota ledger proves no provider attempt was reserved for it: PacedProvider reserves before every
    transmission, so an unchanged count means nothing was sent. Otherwise the combination is never
    retried (that could repeat a provider request) and the run stops (fail closed)."""
    reserved_before = pacer.attempts if pacer is not None else None
    last: BaseException | None = None
    for attempt, delay in enumerate((0.0, *DB_RETRY_DELAYS_S)):
        if delay:
            await sleep(delay)
        try:
            return await run()
        except Exception as error:
            if not is_transient_db_error(error):
                raise
            if pacer is None or pacer.attempts != reserved_before:
                raise CombinationStateUnknown(
                    f"{what}: database error after a provider attempt may have been sent; "
                    "not retried, run stopped"
                ) from error
            last = error
            logger.warning(
                "benchmark_db_retry",
                extra={"operation": what, "attempt": attempt + 1, "error": type(error).__name__},
            )
    raise DatabaseUnavailable(
        f"{what}: the database was unavailable after {len(DB_RETRY_DELAYS_S) + 1} attempts "
        "(no provider attempt was sent)"
    ) from last


async def _refuse_started_recovery(
    db: Database, recovery_sha256: str, sleep: Callable[[float], Awaitable[None]]
) -> None:
    """A registered recovery runs once: refuse if any run already carries this recovery plan."""

    async def once() -> list[str]:
        async with db.sessionmaker() as session:
            runs = (await session.scalars(select(EvaluationRun))).all()
            return [
                f"{r.id} ({r.status})"
                for r in runs
                if ((r.config_snapshot or {}).get("execution_recovery") or {}).get("sha256")
                == recovery_sha256
            ]

    started = await with_db_retry(once, "check for an earlier recovery run", sleep)
    if started:
        raise ValueError(
            f"the registered recovery has already started ({', '.join(started)}): it never restarts"
        )


async def _all_persisted(
    db: Database,
    run_ids: dict[str, str],
    outcomes: list[CaseOutcome],
    sleep: Callable[[float], Awaitable[None]],
) -> bool:
    """True only if the database holds exactly one result per outcome for every run."""
    expected = Counter(o.strategy for o in outcomes)

    async def once() -> dict[str, int]:
        async with db.sessionmaker() as session:
            rows = await session.execute(
                select(EvaluationResult.run_id, func.count())
                .where(EvaluationResult.run_id.in_([uuid.UUID(r) for r in run_ids.values()]))
                .group_by(EvaluationResult.run_id)
            )
            return {str(run_id): int(n) for run_id, n in rows.all()}

    persisted = await with_db_retry(once, "verify persisted results", sleep)
    ok = all(persisted.get(rid, 0) == expected.get(name, 0) for name, rid in run_ids.items())
    if not ok:
        logger.error("benchmark_persisted_mismatch", extra={"persisted": persisted})
    return ok


async def _persist(
    db: Database,
    run_id: str,
    case_uuid: uuid.UUID,
    outcome: CaseOutcome,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Persist one result, idempotently: a retry first checks (run_id, case_id), so an earlier
    attempt whose commit reached the database but whose acknowledgement was lost is never
    duplicated. v5.2.4+ also stores the provider-reported model and the attempts (provenance)."""
    fields: dict[str, Any] = {
        "run_id": uuid.UUID(run_id),
        "case_id": case_uuid,
        "request_log_id": uuid.UUID(outcome.request_id) if outcome.request_id else None,
        "passed": outcome.passed,
        "score": outcome.score,
        "provider": outcome.provider,
        "model_id": outcome.model,
        "routing_tier": outcome.tier,
        "fallback_used": outcome.fallback_used,
        "error_code": outcome.error_code,
        "scorer_details": {
            **outcome.details,
            "provenance": {"answer_model": outcome.answer_model, "attempts": outcome.attempts},
        },
        "input_tokens": outcome.input_tokens,
        "output_tokens": outcome.output_tokens,
        "latency_ms": outcome.latency_ms,
        "estimated_list_cost_usd": Decimal(outcome.estimated_list_cost_usd)
        if outcome.estimated_list_cost_usd
        else None,
        "list_cost_status": outcome.list_cost_status,
        "actual_charge_usd": Decimal(outcome.actual_charge_usd)
        if outcome.actual_charge_usd
        else None,
        "cost_status": outcome.cost_status,
        "simulated": outcome.simulated,
    }

    async def once() -> None:
        async with db.sessionmaker() as session:
            existing = await session.scalar(
                select(EvaluationResult.id).where(
                    EvaluationResult.run_id == fields["run_id"],
                    EvaluationResult.case_id == case_uuid,
                )
            )
            if existing is not None:
                return
            session.add(EvaluationResult(**fields))
            await session.commit()

    await with_db_retry(once, "persist evaluation result", sleep)


def outcome_dicts(result: BenchmarkResult) -> list[dict[str, Any]]:
    return [asdict(o) for o in result.outcomes]
