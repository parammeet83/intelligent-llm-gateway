"""Management commands (run from backend\\ with `uv run python -m app.cli <command>`).

seed [--no-demo]                         sync model registry + routing policy (+ demo tenants)
create-tenant SLUG NAME [--rpm N] [--daily USD] [--monthly USD]
create-api-key TENANT [--name NAME] [--json]   prints the new key ONCE
list-api-keys TENANT                     prefixes and status only, never secrets
revoke-api-key KEY_ID
rotate-api-key KEY_ID [--grace-s N] [--json]   prints the replacement ONCE
reconcile                                charge reservations of abandoned requests
prune                                    delete rate-limit windows older than a day
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import budget
from app.auth import keys as key_service
from app.core.config import get_settings
from app.db.base import utcnow
from app.db.models import ApiKey, Tenant
from app.db.session import Database
from app.providers.catalog import load_catalog
from app.routing.config import load_policy
from app.seed import run_seed
from app.tenancy import rate_limit


class CliError(Exception):
    pass


async def _with_session(work: Callable[[AsyncSession], Awaitable[int]]) -> int:
    db = Database(get_settings().database_url.get_secret_value())
    try:
        async with db.sessionmaker() as session:
            return await work(session)
    finally:
        await db.dispose()


async def _tenant(session: AsyncSession, slug: str) -> Tenant:
    tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        raise CliError(f"tenant '{slug}' not found")
    return tenant


async def _key(session: AsyncSession, key_id: str) -> tuple[ApiKey, Tenant]:
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise CliError("KEY_ID must be the key's UUID (see list-api-keys)") from None
    row = (
        await session.execute(
            select(ApiKey, Tenant)
            .join(Tenant, Tenant.id == ApiKey.tenant_id)
            .where(ApiKey.id == kid)
        )
    ).first()
    if row is None:
        raise CliError("key not found")
    return row[0], row[1]


def _print_key(slug: str, key: ApiKey, plaintext: str, as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "tenant": slug,
                    "key_id": str(key.id),
                    "prefix": key.key_prefix,
                    "api_key": plaintext,
                }
            )
        )
        return
    print(f"tenant: {slug}\nkey id: {key.id}\nprefix: {key.key_prefix}")
    print(f"api key (shown once, store it now): {plaintext}")


async def cmd_seed(args: argparse.Namespace) -> int:
    settings = get_settings()
    catalog = load_catalog(settings.model_registry_path, allow_paid=settings.allow_paid_models)
    policy = load_policy(settings.routing_policy_path)

    async def work(session: AsyncSession) -> int:
        report = await run_seed(
            session,
            catalog,
            settings.api_key_pepper.get_secret_value(),
            demo_tenants=not args.no_demo,
            policy=policy,
        )
        print(
            f"models: {report.models_created} created, {report.models_updated} updated; "
            f"pricing snapshots: {report.pricing_created} created; "
            f"tenants: {report.tenants_created} created; "
            f"routing policy {policy.version}: "
            + ("recorded" if report.policy_created else "already recorded")
        )
        if report.new_keys:
            print("\nNew API keys (copy now; they cannot be shown again):")
            for slug, key in report.new_keys.items():
                print(f"  {slug}: {key}")
        return 0

    return await _with_session(work)


async def cmd_create_tenant(args: argparse.Namespace) -> int:
    async def work(session: AsyncSession) -> int:
        if await session.scalar(select(Tenant.id).where(Tenant.slug == args.slug)):
            raise CliError(f"tenant '{args.slug}' already exists")
        session.add(
            Tenant(
                slug=args.slug,
                name=args.name,
                rate_limit_rpm=args.rpm,
                daily_budget_usd=Decimal(args.daily) if args.daily else None,
                monthly_budget_usd=Decimal(args.monthly) if args.monthly else None,
            )
        )
        await session.commit()
        print(f"tenant '{args.slug}' created")
        return 0

    return await _with_session(work)


async def cmd_create_key(args: argparse.Namespace) -> int:
    pepper = get_settings().api_key_pepper.get_secret_value()

    async def work(session: AsyncSession) -> int:
        tenant = await _tenant(session, args.tenant)
        issued = await key_service.issue_key(session, tenant, args.name, pepper)
        await session.commit()
        _print_key(tenant.slug, issued.key, issued.plaintext, args.json)
        return 0

    return await _with_session(work)


async def cmd_list_keys(args: argparse.Namespace) -> int:
    async def work(session: AsyncSession) -> int:
        tenant = await _tenant(session, args.tenant)
        rows = (
            await session.scalars(
                select(ApiKey).where(ApiKey.tenant_id == tenant.id).order_by(ApiKey.created_at)
            )
        ).all()
        now = utcnow()
        for key in rows:
            state = "active" if key_service.key_is_active(key, now) else "inactive"
            print(
                f"{key.id}  {key.key_prefix}  {key.name:<16} {state:<8} "
                f"created {key.created_at:%Y-%m-%d}"
            )
        if not rows:
            print("(no keys)")
        return 0

    return await _with_session(work)


async def cmd_revoke_key(args: argparse.Namespace) -> int:
    async def work(session: AsyncSession) -> int:
        key, tenant = await _key(session, args.key_id)
        await key_service.revoke_key(session, key)
        await session.commit()
        print(f"revoked {key.key_prefix} ({tenant.slug})")
        return 0

    return await _with_session(work)


async def cmd_rotate_key(args: argparse.Namespace) -> int:
    pepper = get_settings().api_key_pepper.get_secret_value()

    async def work(session: AsyncSession) -> int:
        key, tenant = await _key(session, args.key_id)
        if not key_service.key_is_active(key, utcnow()):
            raise CliError("only an active key can be rotated")
        issued = await key_service.rotate_key(session, key, tenant, pepper, grace_s=args.grace_s)
        await session.commit()
        if not args.json:
            when = f"after {args.grace_s}s" if args.grace_s else "now"
            print(f"old key {key.key_prefix} stops working {when}")
        _print_key(tenant.slug, issued.key, issued.plaintext, args.json)
        return 0

    return await _with_session(work)


async def cmd_reconcile(_: argparse.Namespace) -> int:
    older = get_settings().stale_reservation_s

    async def work(session: AsyncSession) -> int:
        released = await budget.release_stale(session, older_than_s=older)
        print(f"charged {released} abandoned reservation(s) in full")
        return 0

    return await _with_session(work)


async def cmd_prune(_: argparse.Namespace) -> int:
    async def work(session: AsyncSession) -> int:
        print(f"deleted {await rate_limit.prune(session)} old rate-limit window(s)")
        return 0

    return await _with_session(work)


def prereg_manifest_pacing(prereg: dict[str, Any]) -> dict[str, Any] | None:
    from app.evaluation.dataset import EVAL_ROOT
    from app.evaluation.manifest import load_manifest

    manifest, _ = load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])
    pacing: dict[str, Any] | None = manifest["pinned"]["execution"].get("pacing")
    return pacing


def _load_prereg(args: argparse.Namespace, dataset: Any) -> tuple[dict[str, Any], str, Any]:
    """The dataset's own pre-registration, or the one pinned by `--revision`."""
    from app.evaluation.dataset import (
        load_execution_revision,
        load_preregistration,
        preregistration_path,
    )

    if getattr(args, "revision", None):
        path, pinned = load_execution_revision(args.revision, dataset)
        prereg, sha = load_preregistration(path, dataset=dataset, pinned_sha256=pinned)
    else:
        path = preregistration_path(dataset.name)
        prereg, sha = load_preregistration(path, dataset=dataset)
    return prereg, sha, path


def _daily_budget(args: argparse.Namespace) -> Any:
    """The operator-verified remaining daily token budget, or None if none was supplied."""
    from datetime import datetime

    from app.evaluation.pacing import DailyBudget

    remaining = getattr(args, "remaining_daily_tokens", None)
    limit = getattr(args, "daily_token_limit", None)
    used = getattr(args, "tokens_used_today", None)
    if remaining is None and limit is None and used is None:
        return None
    if not args.daily_budget_source or not args.daily_budget_verified_at:
        raise CliError("a daily budget needs --daily-budget-source and --daily-budget-verified-at")
    try:
        verified_at = datetime.fromisoformat(args.daily_budget_verified_at)
    except ValueError:
        raise CliError("--daily-budget-verified-at must be an ISO 8601 date-time") from None
    if verified_at.tzinfo is None:
        raise CliError(
            "--daily-budget-verified-at must include a UTC offset, e.g. ...T09:30:00+00:00"
        )
    if remaining is not None:
        if limit is not None or used is not None:
            raise CliError(
                "use either --remaining-daily-tokens or --daily-token-limit with "
                "--tokens-used-today, not both"
            )
        return DailyBudget(remaining, verified_at, args.daily_budget_source)
    if limit is None or used is None:
        raise CliError("--daily-token-limit and --tokens-used-today must be given together")
    return DailyBudget.from_limit_and_usage(
        limit=limit, used=used, verified_at=verified_at, source=args.daily_budget_source
    )


def _attempt_quota(prereg: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    from app.evaluation.dataset import EVAL_ROOT
    from app.evaluation.manifest import load_manifest

    if not prereg.get("experiment_manifest"):
        return None
    manifest, _ = load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])
    quotas = manifest["pinned"]["execution"].get("attempt_quota") or {}
    if len(quotas) != 1:
        return None
    ((provider, quota),) = quotas.items()
    return provider, quota


def _quota_preflight(
    args: argparse.Namespace,
    prereg: dict[str, Any],
    dataset: Any,
    settings: Any,
    providers: dict[str, Any],
    strategies: list[str],
) -> Any:
    """Print and return the worst-case quota preflight (None if the revision has no quota)."""
    from pathlib import Path

    from app.evaluation import preflight
    from app.evaluation.pacing import QuotaLedger
    from app.evaluation.runner import DEFAULT_LEDGER

    found = _attempt_quota(prereg)
    if found is None:
        return None
    provider, quota = found
    ledger = QuotaLedger(Path(args.ledger) if args.ledger else DEFAULT_LEDGER, provider)
    pre = preflight.evaluate(
        preflight.plan(dataset, strategies, settings, providers, quota),
        quota,
        _daily_budget(args),
        ledger,
        accept_incomplete_risk=args.accept_incomplete_risk,
    )
    print(f"quota preflight ({provider}, all models combined):")
    for line in preflight.format_report(pre):
        print("  " + line)
    return pre


async def cmd_eval_validate(args: argparse.Namespace) -> int:
    """Exit code 0 only if everything checked is valid. A manifest mismatch or a failed quota
    preflight returns 1, so scripts can't mistake a refused configuration for a valid one."""
    from collections import Counter

    from app.evaluation.dataset import load_dataset

    dataset = load_dataset(args.dataset)
    prereg, prereg_sha, prereg_file = _load_prereg(args, dataset)
    counts = Counter(c.difficulty for c in dataset.cases)
    methods = Counter(str(c.scoring["method"]) for c in dataset.cases)
    print(
        f"dataset {dataset.name}: {len(dataset.cases)} cases {dict(counts)}; "
        f"sha256 {dataset.sha256[:12]}"
    )
    print(f"scoring methods: {dict(methods)}")
    print(f"needs human review: {[c.id for c in dataset.cases if c.needs_human_review]}")
    reviewed = len(dataset.reviewed_case_ids & {c.id for c in dataset.cases})
    print(f"human-reviewed: {reviewed}/{len(dataset.cases)} (status: {dataset.meta.get('status')})")
    print(f"code-execution cases: {dataset.code_execution_cases or 'none'}")
    if getattr(args, "revision", None):
        print(f"execution revision: {args.revision}")
    print(f"pre-registration {prereg_file.name} sha256 {prereg_sha[:12]}")
    status = 0
    if prereg.get("scoring_amendment"):
        from app.evaluation.dataset import apply_scoring_amendment

        try:
            _, amendment = apply_scoring_amendment(dataset, prereg)
        except ValueError as error:
            print(f"scoring amendment: INVALID — {error}")
            status = 1
        else:
            if amendment is not None:
                print(
                    f"scoring amendment {amendment['file']} sha256 {amendment['sha256'][:12]}: "
                    f"valid; amends {', '.join(amendment['cases'])}"
                )
    if prereg.get("review_attestation"):
        from app.evaluation.dataset import apply_review_attestation

        try:
            overlay, review = apply_review_attestation(dataset, prereg)
        except (ValueError, OSError) as error:
            print(f"review attestation: INVALID — {error} (publication gate fails closed)")
            status = 1
        else:
            if review is not None:
                print(
                    f"review attestation {review['file']} sha256 {review['sha256'][:12]}: valid; "
                    f"{len(overlay.reviewed_case_ids)}/{len(overlay.cases)} cases reviewed "
                    f"(fully reviewed: {overlay.fully_reviewed})"
                )
                for note in review["disclosures"].values():
                    print(f"  disclosure: {note}")
    if prereg.get("experiment_manifest"):
        from app.evaluation.manifest import check_manifest
        from app.evaluation.runner import STRATEGIES
        from app.providers.registry import build_providers

        settings = get_settings()
        providers = build_providers(settings)  # adapter objects only; no network call
        try:
            check_manifest(prereg, settings, providers, list(STRATEGIES))
            print(f"experiment manifest {prereg['experiment_manifest']['file']}: matches")
            pinned_pacing = prereg_manifest_pacing(prereg) or {}
            if pinned_pacing:
                print(f"  eval-run must use pacing {pinned_pacing}")
        except ValueError as error:
            print(f"experiment manifest: DOES NOT MATCH — {error}")
            status = 1
        pre = _quota_preflight(args, prereg, dataset, settings, providers, list(STRATEGIES))
        if pre is not None and not pre.ok:
            status = 1
    return status


async def cmd_eval_run(args: argparse.Namespace) -> int:
    from pathlib import Path

    from app.evaluation.dataset import REPORTS_DIR, load_dataset
    from app.evaluation.manifest import check_manifest
    from app.evaluation.report import store_summaries, write_report
    from app.evaluation.runner import RUN_CONCURRENCY, run_benchmark
    from app.providers.registry import build_providers, refresh_catalogs
    from app.resilience.health import HealthRegistry

    settings = get_settings()
    providers = build_providers(settings)
    if all(p.simulated for p in providers.values()) and not args.allow_simulated:
        raise CliError(
            "only simulated providers are enabled; pass --allow-simulated for a pipeline check "
            "(its output is labelled simulated and is never a result)"
        )
    # Fail before any network call if the configuration isn't the pre-registered one.
    dataset = load_dataset(args.dataset)
    prereg, _, _ = _load_prereg(args, dataset)
    try:
        # Validated here so a bad amendment or attestation fails before any network call;
        # run_benchmark applies both.
        from app.evaluation.dataset import apply_review_attestation, apply_scoring_amendment

        apply_scoring_amendment(dataset, prereg)
        apply_review_attestation(dataset, prereg)
        check_manifest(
            prereg,
            settings,
            providers,
            args.strategies,
            run_params={
                "concurrency": RUN_CONCURRENCY,
                "delay_s": float(args.delay_s),
                "limit_cases": args.limit,
                "allow_code_exec": bool(args.allow_code_exec),
            },
        )
    except ValueError as error:
        raise CliError(str(error)) from None
    pre = _quota_preflight(args, prereg, dataset, settings, providers, args.strategies)
    if pre is not None and not pre.ok:
        raise CliError("quota preflight failed (fail closed): " + "; ".join(pre.problems))
    await refresh_catalogs(providers, HealthRegistry())
    db = Database(settings.database_url.get_secret_value())
    try:
        result = await run_benchmark(
            settings=settings,
            db=db,
            providers=providers,
            dataset=dataset,
            strategies=args.strategies,
            label=args.label,
            allow_code_exec=args.allow_code_exec,
            delay_s=args.delay_s,
            limit_cases=args.limit,
            revision=args.revision,
            daily_budget=_daily_budget(args),
            ledger_path=Path(args.ledger) if args.ledger else None,
            accept_incomplete_risk=args.accept_incomplete_risk,
        )
        out, summary = write_report(result, REPORTS_DIR)
        await store_summaries(db, summary)
    finally:
        for provider in providers.values():
            await provider.aclose()
        await db.dispose()
    print(f"report: {out}")
    for name, m in summary["metrics"].items():
        print(
            f"  {name}: pass {m['passed']}/{m['scorable']}, failures {m['failures']}, "
            f"est. cost/accepted {m['estimated_list_cost_per_accepted_answer_usd']}"
        )
    if summary["publishable_reasons"]:
        print("not publishable: " + "; ".join(summary["publishable_reasons"]))
    return 1 if result.incomplete else 0


def _add_revision_and_budget_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--revision", default=None, help="execution revision, e.g. routewise_bench_v5.1")
    p.add_argument(
        "--remaining-daily-tokens",
        type=int,
        default=None,
        help="operator-verified tokens left today for the provider organisation",
    )
    p.add_argument(
        "--daily-token-limit",
        type=int,
        default=None,
        help="operator-verified daily token limit (with --tokens-used-today)",
    )
    p.add_argument(
        "--tokens-used-today",
        type=int,
        default=None,
        help="operator-verified tokens already used today (with --daily-token-limit)",
    )
    p.add_argument(
        "--daily-budget-source",
        default=None,
        help="where the daily budget was read, e.g. 'Groq console limits page'",
    )
    p.add_argument(
        "--daily-budget-verified-at",
        default=None,
        help="when it was read, ISO 8601 with UTC offset",
    )
    p.add_argument(
        "--accept-incomplete-risk",
        action="store_true",
        help="start even if the worst case exceeds the daily budget (the run stops "
        "incomplete rather than exceed it)",
    )
    p.add_argument("--ledger", default=None, help="quota ledger path (default: evaluation/reports)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("seed", help="sync model registry, routing policy and demo tenants")
    p.add_argument("--no-demo", action="store_true", help="skip demo tenants")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("create-tenant")
    p.add_argument("slug")
    p.add_argument("name")
    p.add_argument("--rpm", type=int, default=60)
    p.add_argument("--daily", help="daily shadow budget in USD")
    p.add_argument("--monthly", help="monthly shadow budget in USD")
    p.set_defaults(func=cmd_create_tenant)

    p = sub.add_parser("create-api-key")
    p.add_argument("tenant")
    p.add_argument("--name", default="default")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_create_key)

    p = sub.add_parser("list-api-keys")
    p.add_argument("tenant")
    p.set_defaults(func=cmd_list_keys)

    p = sub.add_parser("revoke-api-key")
    p.add_argument("key_id")
    p.set_defaults(func=cmd_revoke_key)

    p = sub.add_parser("rotate-api-key")
    p.add_argument("key_id")
    p.add_argument("--grace-s", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_rotate_key)

    sub.add_parser("reconcile").set_defaults(func=cmd_reconcile)
    sub.add_parser("prune").set_defaults(func=cmd_prune)

    p = sub.add_parser("eval-validate", help="validate the benchmark dataset and review status")
    p.add_argument("--dataset", default="routewise_bench_v1")
    _add_revision_and_budget_args(p)
    p.set_defaults(func=cmd_eval_validate)

    p = sub.add_parser("eval-run", help="run the benchmark through the gateway")
    p.add_argument("--label", required=True, help="report directory name, e.g. 2026-11-05-live")
    p.add_argument("--dataset", default="routewise_bench_v1")
    p.add_argument(
        "--strategies",
        nargs="+",
        default=["baseline_premium", "routewise", "routewise_tier_first"],
    )
    p.add_argument(
        "--allow-code-exec", action="store_true", help="run model-written code tests locally"
    )
    p.add_argument(
        "--allow-simulated", action="store_true", help="permit a mock-only pipeline check"
    )
    p.add_argument(
        "--delay-s", type=float, default=0.0, help="pause between requests (free-tier limits)"
    )
    p.add_argument("--limit", type=int, default=None, help="only the first N cases")
    _add_revision_and_budget_args(p)
    p.set_defaults(func=cmd_eval_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], Coroutine[Any, Any, int]] = args.func
    try:
        return asyncio.run(handler(args))
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def run(argv: list[str]) -> Any:
    return main(argv)


if __name__ == "__main__":
    sys.exit(main())
