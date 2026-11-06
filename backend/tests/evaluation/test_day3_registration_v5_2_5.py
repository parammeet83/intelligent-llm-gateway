"""Revision routewise_bench_v5.2.5: post-incident, exploratory Day 3 registration and run-once
protection (execution window, atomic execution claim, fail closed on any database doubt).

No provider is called and Neon is never used: claims and runs go to the test databases, provider
calls are replaced by assertions, and time-dependent checks use a fixed moment inside the window.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BenchmarkExecutionClaim, EvaluationRun
from app.db.session import Database
from app.evaluation import manifest as manifest_mod
from app.evaluation import runner as runner_mod
from app.evaluation.dataset import (
    EVAL_ROOT,
    load_dataset,
    load_execution_recovery,
    load_execution_revision,
    load_execution_schedule,
    load_preregistration,
    scheduled_combinations,
)
from app.evaluation.pacing import DailyBudget
from app.evaluation.runner import (
    DatabaseUnavailable,
    check_execution_window,
    claim_scheduled_day,
    run_benchmark,
    scheduled_day_started,
)
from app.providers.groq import GroqProvider
from tests.conftest import migrate

REVISION = "routewise_bench_v5.2.5"
STRATS = ["baseline_premium", "routewise", "routewise_tier_first"]
DAY3 = ["S02", "S03", "S09", "S10", "T05", "T07", "T11", "T13", "C07", "C09", "C12"]
INSIDE = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)  # a moment inside the registered window
V5 = load_dataset("routewise_bench_v5")
HISTORICAL = {
    "routewise_bench_v5.2.3.revision.yaml": (
        "70f0059153b4f66c90780cfbc9d6dad115ad87e629851b170b788fe9f005c4a8"
    ),
    "routewise_bench_v5.2.4.revision.yaml": (
        "eed5b11c0650c916860805ac9c5537182eda8d73ea93738ac2bae7d0502c8ec6"
    ),
    "preregistration_routewise_bench_v5.2.4.yaml": (
        "b041f94a2fa0ad8e53cc4530e6f45568da9fe4dedbf708ba2750c99267515619"
    ),
    "experiment_manifest_routewise_bench_v5.2.4.yaml": (
        "d6efb0d9ec9d12d25a132ccb9fb1ee929d776783a50a3d68ebbdee6e483099b2"
    ),
    "execution_recovery_routewise_bench_v5.2.4.yaml": (
        "e3c46ba492fd5cf5ba33cb13b672c2771d273563ec01ca2b64e5082472f7a1da"
    ),
    "execution_schedule_routewise_bench_v5.2.3.yaml": (
        "c74699c11ec73ef08e0d883fedf7ffe5b5bc996c84de8ba9abbb0207b94756e6"
    ),
}


def _prereg() -> tuple[dict[str, Any], str]:
    path, pinned = load_execution_revision(REVISION, V5)
    return load_preregistration(path, dataset=V5, pinned_sha256=pinned)


PREREG, PREREG_SHA = _prereg()
SCHEDULE = load_execution_schedule(V5, PREREG)


async def _no_sleep(seconds: float) -> None:
    return None


def _sha(name: str) -> str:
    return hashlib.sha256((EVAL_ROOT / name).read_bytes()).hexdigest()


# --- the registration -----------------------------------------------------------------------------


def test_historical_registrations_are_unchanged() -> None:
    for name, sha in HISTORICAL.items():
        assert _sha(name) == sha, name


def test_the_v5_2_5_chain_reuses_the_pinned_schedule_for_day_3_only() -> None:
    rev = yaml.safe_load((EVAL_ROOT / f"{REVISION}.revision.yaml").read_text(encoding="utf-8"))
    assert rev["preregistration"]["sha256"] == PREREG_SHA
    assert rev["authorised_days"] == [3] and rev["publishable"] is False
    assert rev["amends_revision"]["sha256"] == HISTORICAL["routewise_bench_v5.2.4.revision.yaml"]
    assert (
        rev["execution_schedule"]["sha256"]
        == (HISTORICAL["execution_schedule_routewise_bench_v5.2.3.yaml"])
    )
    assert (EVAL_ROOT / rev["changelog"]).is_file()
    assert SCHEDULE is not None and SCHEDULE["days"][3] == DAY3
    assert len(scheduled_combinations(V5, SCHEDULE, 3, STRATS)) == 33
    assert load_execution_recovery(V5, PREREG, SCHEDULE) is None  # no Day 2 recovery here


def test_the_registration_is_disclosed_as_post_incident_exploratory_and_non_publishable() -> None:
    text = (EVAL_ROOT / "preregistration_routewise_bench_v5.2.5.yaml").read_text(encoding="utf-8")
    assert "POST-INCIDENT" in text and "EXPLORATORY" in text and "DAY 3 ONLY" in text
    assert PREREG["publishable"] is False and "exploratory" in PREREG["publishable_reason"]
    assert "POST-INCIDENT, EXPLORATORY" in PREREG["changes_from_prereg_v5_2_4"][0]
    assert "Day 4 is not authorised" in PREREG["changes_from_prereg_v5_2_4"][1]
    assert "v5.2.5 Day 3 registration is post-incident" in PREREG["publication"]["rule"]
    window = PREREG["execution_window"]
    assert window["days"] == [3] and window["latest_start_utc"] == "22:00"
    assert (window["earliest_utc_date"], window["latest_utc_date"]) == ("2026-11-06", "2026-11-17")


def test_nothing_else_about_the_experiment_changed_from_v5_2_4() -> None:
    old = yaml.safe_load(
        (EVAL_ROOT / "preregistration_routewise_bench_v5.2.4.yaml").read_text(encoding="utf-8")
    )
    for key in (
        "dataset",
        "dataset_sha256",
        "execution_schedule",
        "scoring_amendment",
        "dataset_metadata",
        "review_attestation",
        "strategies",
        "baseline_tier_guard",
        "quota",
        "scope",
        "reporting",
        "primary_metric",
        "primary_population",
        "run_validity",
        "baseline_floor",
        "quality_rule",
        "secondary_rules",
        "cost_rule",
        "latency",
        "per_case_limits",
        "statistics",
    ):
        assert PREREG[key] == old[key], key
    assert "execution_recovery" not in PREREG and "execution_window" not in old


# --- the execution window -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "now", "message"),
    [
        (4, INSIDE, r"authorises day\(s\) \[3\] only, not day 4"),
        (1, INSIDE, r"not day 1"),
        (3, datetime(2026, 11, 5, 12, 0, tzinfo=UTC), "outside the registered execution window"),
        (3, datetime(2026, 11, 18, 0, 1, tzinfo=UTC), "outside the registered execution window"),
        (3, datetime(2026, 11, 10, 22, 0, 1, tzinfo=UTC), "after the registered latest start"),
    ],
)
def test_the_window_refuses_other_days_dates_and_late_starts(
    day: int, now: datetime, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        check_execution_window(PREREG, day, now)


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 11, 6, 0, 0, tzinfo=UTC),
        datetime(2026, 11, 17, 22, 0, tzinfo=UTC),
        INSIDE,
    ],
)
def test_the_window_allows_day_3_inside_it(now: datetime) -> None:
    check_execution_window(PREREG, 3, now)


def test_registrations_without_a_window_are_unaffected() -> None:
    path, pinned = load_execution_revision("routewise_bench_v5.2.3", V5)
    old, _ = load_preregistration(path, dataset=V5, pinned_sha256=pinned)
    check_execution_window(old, 4, datetime(2030, 1, 1, 23, 59, tzinfo=UTC))


# --- the atomic execution claim -------------------------------------------------------------------


async def _claims(session: AsyncSession) -> int:
    session.expire_all()
    q = select(func.count()).select_from(BenchmarkExecutionClaim)
    return int(await session.scalar(q) or 0)


async def test_a_scheduled_day_can_be_claimed_only_once(
    database_url: str, session: AsyncSession
) -> None:
    db = Database(database_url)
    try:
        await claim_scheduled_day(db, REVISION, 3, "v5.2.5-day3", _no_sleep)
        with pytest.raises(ValueError, match="already claimed: a scheduled day never starts twice"):
            await claim_scheduled_day(db, REVISION, 3, "v5.2.5-day3", _no_sleep)
        # other days and other revisions are separate claims
        await claim_scheduled_day(db, REVISION, 4, "v5.2.5-day4", _no_sleep)
        await claim_scheduled_day(db, "routewise_bench_v9.9", 3, "v9.9-day3", _no_sleep)
    finally:
        await db.dispose()
    assert await _claims(session) == 3


async def test_concurrent_starts_let_exactly_one_claim_win(
    database_url: str, session: AsyncSession
) -> None:
    dbs = [Database(database_url) for _ in range(4)]
    try:
        results = await asyncio.gather(
            *(claim_scheduled_day(db, REVISION, 3, "v5.2.5-day3", _no_sleep) for db in dbs),
            return_exceptions=True,
        )
    finally:
        for db in dbs:
            await db.dispose()
    won = [r for r in results if r is None]
    refused = [r for r in results if isinstance(r, ValueError) and "already claimed" in str(r)]
    assert len(won) == 1 and len(refused) == 3, results
    assert await _claims(session) == 1


async def test_an_ambiguous_claim_commit_refuses_instead_of_running(
    database_url: str, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The claim reaches the database but its acknowledgement is lost: the retry hits the unique
    constraint and refuses. Safe: the day is claimed but nothing runs."""
    from sqlalchemy.exc import OperationalError

    real_commit = AsyncSession.commit
    state = {"failed": False}

    async def commit_then_lose_ack(self: AsyncSession) -> None:
        await real_commit(self)
        if not state["failed"]:
            state["failed"] = True
            raise OperationalError("COMMIT", {}, TimeoutError("connection timed out"))

    monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)
    db = Database(database_url)
    try:
        with pytest.raises(ValueError, match="already claimed"):
            await claim_scheduled_day(db, REVISION, 3, "v5.2.5-day3", _no_sleep)
    finally:
        await db.dispose()
    monkeypatch.undo()
    assert state["failed"] and await _claims(session) == 1


def _unreachable(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'missing-dir' / 'x.db').as_posix()}"


async def test_an_unreachable_database_fails_closed(tmp_path: Path) -> None:
    db = Database(_unreachable(tmp_path))
    try:
        with pytest.raises(DatabaseUnavailable):
            await scheduled_day_started(db, REVISION, 3, _no_sleep)
        with pytest.raises(DatabaseUnavailable):
            await claim_scheduled_day(db, REVISION, 3, "v5.2.5-day3", _no_sleep)
    finally:
        await db.dispose()


@pytest.fixture
def before_0003(tmp_path: Path) -> str:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'old.db').as_posix()}"
    migrate(url, "0002")
    return url


async def test_a_database_without_the_claims_table_fails_closed(before_0003: str) -> None:
    """Migration 0003 not applied: never read as 'no claim' and never claimed."""
    db = Database(before_0003)
    try:
        with pytest.raises(Exception) as checked:
            await scheduled_day_started(db, REVISION, 3, _no_sleep)
        with pytest.raises(Exception) as claimed:
            await claim_scheduled_day(db, REVISION, 3, "v5.2.5-day3", _no_sleep)
    finally:
        await db.dispose()
    for raised in (checked, claimed):
        assert "benchmark_execution_claims" in str(raised.value.__cause__ or raised.value)
        assert not isinstance(raised.value, ValueError)  # an error, never a decision


def _run(revision: str, day: int, status: str) -> EvaluationRun:
    return EvaluationRun(
        label="earlier",
        strategy="routewise",
        dataset_version="routewise_bench_v5",
        config_snapshot={"execution_revision": revision, "execution_schedule": {"day": day}},
        preregistration_sha256="x" * 64,
        simulated=False,
        status=status,
    )


async def test_existing_runs_and_claims_mark_the_day_started(
    database_url: str, session: AsyncSession
) -> None:
    db = Database(database_url)
    try:
        assert await scheduled_day_started(db, REVISION, 3, _no_sleep) == []
        # other revisions' and other days' runs don't count
        session.add_all([_run("routewise_bench_v5.2.3", 3, "failed"), _run(REVISION, 4, "failed")])
        await session.commit()
        assert await scheduled_day_started(db, REVISION, 3, _no_sleep) == []
        session.add(_run(REVISION, 3, "failed"))  # a failed run still counts: never restarted
        await session.commit()
        found = await scheduled_day_started(db, REVISION, 3, _no_sleep)
        assert len(found) == 1 and found[0].endswith("(failed)")
        await claim_scheduled_day(db, REVISION, 3, "v5.2.5-day3", _no_sleep)
        assert len(await scheduled_day_started(db, REVISION, 3, _no_sleep)) == 2
    finally:
        await db.dispose()


# --- the runner: window, run-once check and claim before any run or provider call ----------------


def _settings() -> Any:
    from app.core.config import Settings

    return Settings(
        _env_file=None,
        groq_enabled=True,
        groq_api_key="test-placeholder-key-0000000000000000",
        groq_billing_plan="free",
        mock_provider_enabled=False,
    )


def _groq() -> dict[str, Any]:
    return {"groq": GroqProvider(api_key="test-placeholder", charge_basis="free_tier")}


@pytest.fixture
def fixed_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Window checks see a fixed moment inside the window (the runner, CLI and guard all resolve
    check_execution_window through the runner module at call time)."""
    real = runner_mod.check_execution_window

    def at_inside(prereg: dict[str, Any], day: int, now: datetime) -> None:
        real(prereg, day, INSIDE)

    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(runner_mod, "check_execution_window", at_inside)


class _Stop(Exception):
    """Raised where the run would create its tenant: proves everything before it passed."""


def _budget(tokens: int = 157_747) -> DailyBudget:
    return DailyBudget(remaining_tokens=tokens, verified_at=datetime.now(UTC), source="test")


async def _start_day(database_url: str, tmp_path: Path, day: int = 3) -> None:
    db = Database(database_url)
    try:
        await run_benchmark(
            settings=_settings(),
            db=db,
            providers=_groq(),
            dataset=V5,
            strategies=STRATS,
            label="v5.2.5-day3",
            revision=REVISION,
            delay_s=6.0,
            schedule_day=day,
            daily_budget=_budget(),
            ledger_path=tmp_path / "ledger.json",
            sleep=_no_sleep,
        )
    finally:
        await db.dispose()


@pytest.fixture
def stop_before_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stop(*args: Any, **kwargs: Any) -> Any:
        raise _Stop

    monkeypatch.setattr(runner_mod, "_eval_tenant", stop)


async def test_the_runner_claims_day_3_once_and_refuses_a_second_start(
    fixed_window: None,
    stop_before_runs: None,
    database_url: str,
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    with pytest.raises(_Stop):  # the manifest, window and preflight passed; the day is claimed
        await _start_day(database_url, tmp_path)
    assert await _claims(session) == 1
    with pytest.raises(ValueError, match=r"already started .*claim .*never starts twice"):
        await _start_day(database_url, tmp_path)
    assert await _claims(session) == 1
    assert int(await session.scalar(select(func.count()).select_from(EvaluationRun)) or 0) == 0


async def test_the_runner_refuses_when_a_run_predates_the_claims(
    fixed_window: None,
    stop_before_runs: None,
    database_url: str,
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    session.add(_run(REVISION, 3, "failed"))
    await session.commit()
    with pytest.raises(ValueError, match="already started"):
        await _start_day(database_url, tmp_path)
    assert await _claims(session) == 0


async def test_concurrent_runner_starts_let_exactly_one_through(
    fixed_window: None,
    stop_before_runs: None,
    database_url: str,
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    results = await asyncio.gather(
        *(_start_day(database_url, tmp_path / str(i)) for i in range(3)), return_exceptions=True
    )
    through = [r for r in results if isinstance(r, _Stop)]
    refused = [r for r in results if isinstance(r, ValueError) and "never starts twice" in str(r)]
    assert len(through) == 1 and len(refused) == 2, results
    assert await _claims(session) == 1


async def test_the_runner_fails_closed_when_the_database_is_unavailable(
    fixed_window: None, stop_before_runs: None, tmp_path: Path
) -> None:
    with pytest.raises(DatabaseUnavailable):
        await _start_day(_unreachable(tmp_path), tmp_path)


async def test_the_runner_refuses_day_4_before_touching_the_database(
    fixed_window: None, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match=r"authorises day\(s\) \[3\] only, not day 4"):
        await _start_day(_unreachable(tmp_path), tmp_path, day=4)


# --- the CLI: every refusal happens before any network call ---------------------------------------


@pytest.fixture
def intended_cli(fixed_window: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import cli
    from app.providers import registry

    async def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no network call may happen in these tests")

    monkeypatch.setattr(cli, "get_settings", _settings)
    monkeypatch.setattr(registry, "build_providers", lambda settings: _groq())
    monkeypatch.setattr(registry, "refresh_catalogs", no_network)


def _main(*argv: str) -> int:
    from app import cli

    return cli.main(list(argv))


def _budget_args(tokens: int) -> list[str]:
    return [
        "--remaining-daily-tokens",
        str(tokens),
        "--daily-budget-source",
        "test",
        "--daily-budget-verified-at",
        datetime.now(UTC).isoformat(),
    ]


VALIDATE = ["eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION]


def test_eval_validate_reports_the_window_and_the_33_combination_preflight(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    ledger = ["--ledger", str(tmp_path / "l.json")]
    assert _main(*VALIDATE, *_budget_args(157_747), *ledger) == 0
    out = capsys.readouterr().out
    assert "experiment_manifest_routewise_bench_v5.2.5.yaml: matches" in out
    assert "execution window: day(s) [3] on one UTC date from 2026-11-06 to 2026-11-17" in out
    assert "gateway requests: 33" in out and "total conservative reservation: 141972" in out
    assert "preflight: OK" in out
    assert _main(*VALIDATE, *_budget_args(157_746), *ledger) == 1  # one token short: fail closed


def test_eval_validate_refuses_day_4(intended_cli: None, capsys: Any, tmp_path: Path) -> None:
    ledger = ["--ledger", str(tmp_path / "l.json")]
    assert _main(*VALIDATE, "--schedule-day", "4", *_budget_args(10**6), *ledger) == 1
    assert "WINDOW: this registration authorises day(s) [3] only" in capsys.readouterr().out


EVAL_RUN = ["eval-run", "--dataset", "routewise_bench_v5", "--label", "t", "--delay-s", "6"]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ([], "pass the day"),
        (["--schedule-day", "4"], "authorises day(s) [3] only, not day 4"),
        (["--schedule-day", "3"], "quota preflight failed"),
    ],
)
def test_eval_run_refuses_before_any_network_call(
    intended_cli: None, capsys: Any, extra: list[str], message: str
) -> None:
    assert _main(*EVAL_RUN, "--revision", REVISION, *extra) == 2
    assert message in capsys.readouterr().err


@pytest.mark.parametrize(
    ("check", "message"),
    [
        ("down", "could not confirm that day 3 has not started (DatabaseUnavailable)"),
        ("started", "day 3 already started (claim c-1"),
    ],
)
def test_eval_run_checks_the_database_before_any_network_call(
    intended_cli: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: Any,
    tmp_path: Path,
    check: str,
    message: str,
) -> None:
    async def started(*args: Any, **kwargs: Any) -> list[str]:
        if check == "down":
            raise DatabaseUnavailable("check: unavailable")
        return ["claim c-1 (2026-11-10 12:00 UTC)"]

    monkeypatch.setattr(runner_mod, "scheduled_day_started", started)
    ledger = ["--ledger", str(tmp_path / "l.json")]
    argv = [*EVAL_RUN, "--revision", REVISION, "--schedule-day", "3", *_budget_args(157_747)]
    assert _main(*argv, *ledger) == 2
    err = capsys.readouterr().err
    assert message in err
    if check == "down":
        assert "refusing (fail closed)" in err


@pytest.mark.parametrize("old", ["routewise_bench_v5.2.3", "routewise_bench_v5.2.4"])
def test_historical_revisions_are_refused_on_current_code(
    intended_cli: None, capsys: Any, old: str
) -> None:
    assert _main(*EVAL_RUN, "--revision", old, "--schedule-day", "2") == 2
    assert f"configuration differs from experiment_manifest_{old}" in capsys.readouterr().err


# --- the report -----------------------------------------------------------------------------------


def _summary(prereg: dict[str, Any]) -> dict[str, Any]:
    from app.evaluation.report import build_summary
    from app.evaluation.runner import BenchmarkResult, CaseOutcome

    def outcome(strategy: str, case: str) -> CaseOutcome:
        return CaseOutcome(
            case_id=case,
            difficulty="simple",
            category="c",
            strategy=strategy,
            passed=True,
            score=1.0,
            needs_human_review=False,
            error_code=None,
            provider="groq",
            model="openai/gpt-oss-120b",
            answer_model="openai/gpt-oss-120b",
            tier="premium",
            attempts=[
                {
                    "attempt": 1,
                    "provider": "groq",
                    "model": "openai/gpt-oss-120b",
                    "tier": "premium",
                }
            ],
        )

    return build_summary(
        BenchmarkResult(
            label="synthetic",
            simulated=False,
            dataset=V5.name,
            dataset_sha256=V5.sha256,
            dataset_fully_reviewed=True,
            preregistration=prereg,
            preregistration_sha256="x" * 64,
            started_at="",
            finished_at="",
            config_snapshot={"execution_revision": REVISION},
            run_ids={str(uuid.uuid4()): s for s in STRATS},
            outcomes=[outcome(s, c) for s in STRATS for c in DAY3],
        )
    )


def test_a_report_of_v5_2_5_is_never_publishable() -> None:
    summary = _summary(PREREG)
    assert summary["publishable"] is False
    assert PREREG["publishable_reason"] in summary["publishable_reasons"]
    without = _summary({k: v for k, v in PREREG.items() if k != "publishable"})
    assert PREREG["publishable_reason"] not in without["publishable_reasons"]
