"""Revision routewise_bench_v5.2.4: disclosed Day 2 recovery and database reliability.

No provider is called and Neon is never used: reliability tests run the benchmark pipeline on the
mock provider against the test databases, and recovery tests use copies in temporary directories.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvaluationCase, EvaluationResult, EvaluationRun
from app.db.session import Database
from app.evaluation import manifest as manifest_mod
from app.evaluation import preflight
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
from app.evaluation.runner import (
    CaseOutcome,
    CombinationStateUnknown,
    DatabaseUnavailable,
    finalize_runs,
    run_benchmark,
    with_db_retry,
)
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider
from tests.conftest import make_settings

REVISION = "routewise_bench_v5.2.4"
RECOVERY_FILE = "execution_recovery_routewise_bench_v5.2.4.yaml"
STRATS = ["baseline_premium", "routewise", "routewise_tier_first"]
V5 = load_dataset("routewise_bench_v5")
ORIGINAL = {
    "baseline_premium": "4c2aed09-3b2c-4f56-ac93-24cc0c59019d",
    "routewise": "8221d2a2-ef04-4515-8d79-fffa0c60d640",
    "routewise_tier_first": "315cc0c9-e8ee-4a2f-946b-843525d4e485",
}
CARRIED = {
    ("S06", "routewise_tier_first"),
    ("S06", "routewise"),
    ("S06", "baseline_premium"),
    ("S07", "baseline_premium"),
    ("S07", "routewise"),
    ("S07", "routewise_tier_first"),
    ("S14", "routewise_tier_first"),
    ("S14", "routewise"),
    ("S14", "baseline_premium"),
    ("T02", "baseline_premium"),
    ("T02", "routewise"),
}


def _transient() -> OperationalError:
    return OperationalError("SELECT 1", {}, TimeoutError("connection timed out"))


async def _no_sleep(seconds: float) -> None:
    return None


# --- bounded, idempotent database retries ---------------------------------------------------------


async def test_transient_database_errors_are_retried_with_backoff() -> None:
    calls, sleeps = [], []

    async def sleep(s: float) -> None:
        sleeps.append(s)

    async def op() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise _transient()
        return "ok"

    assert await with_db_retry(op, "test", sleep) == "ok"
    assert len(calls) == 3 and sleeps == [1.0, 2.0]


async def test_retries_are_bounded_and_fail_closed() -> None:
    async def op() -> None:
        raise _transient()

    with pytest.raises(DatabaseUnavailable, match="unavailable after 6 attempts") as raised:
        await with_db_retry(op, "test", _no_sleep)
    assert isinstance(raised.value.__cause__, OperationalError)


@pytest.mark.parametrize("error", [IntegrityError("x", {}, Exception()), ValueError("bug")])
async def test_non_transient_errors_are_never_retried(error: Exception) -> None:
    calls = []

    async def op() -> None:
        calls.append(1)
        raise error

    with pytest.raises(type(error)):
        await with_db_retry(op, "test", _no_sleep)
    assert calls == [1]


class _Pacer:
    def __init__(self) -> None:
        self.attempts = 0


async def test_a_combination_is_retried_only_when_no_provider_attempt_was_reserved() -> None:
    pacer, calls = _Pacer(), []

    async def run() -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise _transient()  # failed before any reservation: provably nothing was sent
        return "outcome"

    result: Any = await runner_mod._run_case_retrying_db(run, pacer, _no_sleep, "x")  # type: ignore[arg-type]
    assert result == "outcome" and len(calls) == 2


async def test_a_combination_is_never_retried_after_a_reservation() -> None:
    pacer, provider_calls = _Pacer(), []

    async def run() -> Any:
        provider_calls.append(1)
        pacer.attempts += 1  # the provider attempt was reserved (and may have been sent)
        raise _transient()

    with pytest.raises(CombinationStateUnknown, match="not retried"):
        await runner_mod._run_case_retrying_db(run, pacer, _no_sleep, "x")  # type: ignore[arg-type]
    assert provider_calls == [1]  # no duplicate provider request


async def test_without_a_ledger_the_state_is_unknown_and_never_retried() -> None:
    calls = []

    async def run() -> Any:
        calls.append(1)
        raise _transient()

    with pytest.raises(CombinationStateUnknown):
        await runner_mod._run_case_retrying_db(run, None, _no_sleep, "x")
    assert calls == [1]


async def _run_and_case(session: AsyncSession) -> tuple[str, uuid.UUID]:
    run = EvaluationRun(
        label="t",
        strategy="routewise",
        dataset_version="d",
        config_snapshot={},
        preregistration_sha256="x" * 64,
        simulated=True,
        status="running",
    )
    case = EvaluationCase(
        dataset_version="d",
        case_key="S01",
        category="c",
        difficulty="simple",
        payload={},
        acceptance={},
        eval_method="exact",
    )
    session.add_all([run, case])
    await session.commit()
    return str(run.id), case.id


def _outcome() -> CaseOutcome:
    return CaseOutcome(
        case_id="S01",
        difficulty="simple",
        category="c",
        strategy="routewise",
        passed=True,
        score=1.0,
        needs_human_review=False,
        error_code=None,
        answer_model="mock-small-v1",
        attempts=[{"attempt": 1, "model": "mock-small"}],
    )


async def _count(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(EvaluationResult)) or 0)


async def test_persistence_is_idempotent(database_url: str, session: AsyncSession) -> None:
    run_id, case_id = await _run_and_case(session)
    db = Database(database_url)
    try:
        await runner_mod._persist(db, run_id, case_id, _outcome(), _no_sleep)
        await runner_mod._persist(db, run_id, case_id, _outcome(), _no_sleep)
    finally:
        await db.dispose()
    assert await _count(session) == 1
    row = await session.scalar(select(EvaluationResult))
    assert row is not None and row.scorer_details["provenance"]["answer_model"] == "mock-small-v1"


async def test_an_ambiguous_commit_is_not_duplicated(
    database_url: str, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The commit reaches the database but its acknowledgement is lost: the retry finds the row."""
    run_id, case_id = await _run_and_case(session)
    real_commit = AsyncSession.commit
    state = {"failed": False}

    async def commit_then_lose_ack(self: AsyncSession) -> None:
        await real_commit(self)
        if not state["failed"]:
            state["failed"] = True
            raise _transient()

    monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_ack)
    db = Database(database_url)
    try:
        await runner_mod._persist(db, run_id, case_id, _outcome(), _no_sleep)
    finally:
        await db.dispose()
    monkeypatch.undo()
    assert state["failed"] and await _count(session) == 1


async def test_finalisation_only_closes_running_runs_and_is_idempotent(
    database_url: str, session: AsyncSession
) -> None:
    run_id, _ = await _run_and_case(session)
    db = Database(database_url)
    try:
        assert await finalize_runs(db, [run_id], "failed", _no_sleep) == 1
        assert await finalize_runs(db, [run_id], "completed", _no_sleep) == 0  # already finished
    finally:
        await db.dispose()
    session.expire_all()
    run = await session.get(EvaluationRun, uuid.UUID(run_id))
    assert run is not None and run.status == "failed" and run.finished_at is not None


# --- the runner: no run left running, the original error kept, nothing silently incomplete --------


async def _mock_run(database_url: str, **kwargs: Any) -> Any:
    db = Database(database_url)
    try:
        return await run_benchmark(
            settings=make_settings(database_url),
            db=db,
            providers={"mock": MockProvider()},
            dataset=load_dataset(),
            strategies=STRATS,
            label="pytest",
            limit_cases=2,
            sleep=_no_sleep,
            **kwargs,
        )
    finally:
        await db.dispose()


async def _statuses(session: AsyncSession) -> list[str]:
    session.expire_all()
    return [r.status for r in (await session.scalars(select(EvaluationRun))).all()]


async def test_an_unexpected_error_marks_runs_failed_not_completed(
    database_url: str, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: before v5.2.4 any exception other than a quota stop left `incomplete` False, so a
    successful finalisation would have marked the interrupted runs `completed`."""

    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bug")

    monkeypatch.setattr(runner_mod, "_run_case", boom)
    with pytest.raises(RuntimeError, match="bug"):
        await _mock_run(database_url)
    assert await _statuses(session) == ["failed"] * 3


async def test_a_database_error_without_a_ledger_stops_the_run_fail_closed(
    database_url: str, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def db_down(*args: Any, **kwargs: Any) -> Any:
        raise _transient()

    monkeypatch.setattr(runner_mod, "_run_case", db_down)
    with pytest.raises(CombinationStateUnknown):
        await _mock_run(database_url)
    assert await _statuses(session) == ["failed"] * 3


async def test_the_original_error_survives_a_finalisation_failure(
    database_url: str, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("original failure")

    async def finalisation_down(*args: Any, **kwargs: Any) -> int:
        raise DatabaseUnavailable("finalise evaluation runs: unavailable")

    monkeypatch.setattr(runner_mod, "_run_case", boom)
    monkeypatch.setattr(runner_mod, "finalize_runs", finalisation_down)
    with pytest.raises(RuntimeError, match="original failure") as raised:
        await _mock_run(database_url)
    notes = " ".join(getattr(raised.value, "__notes__", []))
    assert "also failed (DatabaseUnavailable)" in notes and "eval-finalize-runs" in notes
    assert await _statuses(session) == ["running"] * 3  # closable later; see the next test


async def test_runs_left_running_can_be_closed_afterwards(
    database_url: str, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def finalisation_down(*args: Any, **kwargs: Any) -> int:
        raise DatabaseUnavailable("finalise evaluation runs: unavailable")

    monkeypatch.setattr(runner_mod, "finalize_runs", finalisation_down)
    with pytest.raises(DatabaseUnavailable):  # a clean run whose finalisation fails isn't silent
        await _mock_run(database_url)
    monkeypatch.undo()
    session.expire_all()
    ids = [str(r.id) for r in (await session.scalars(select(EvaluationRun))).all()]
    db = Database(database_url)
    try:
        assert await finalize_runs(db, ids, "failed", _no_sleep) == 3
    finally:
        await db.dispose()
    assert await _statuses(session) == ["failed"] * 3


async def test_a_lost_result_write_makes_the_run_incomplete(
    database_url: str, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = runner_mod._persist
    skipped: list[str] = []

    async def lose_one(db: Any, run_id: str, case_uuid: Any, outcome: Any, sleep: Any) -> None:
        if not skipped:
            skipped.append(outcome.case_id)  # silently "lost": the verification must notice
            return
        await real(db, run_id, case_uuid, outcome, sleep)

    monkeypatch.setattr(runner_mod, "_persist", lose_one)
    result = await _mock_run(database_url)
    assert result.incomplete is True and await _statuses(session) == ["failed"] * 3


async def test_a_clean_run_still_completes(database_url: str, session: AsyncSession) -> None:
    result = await _mock_run(database_url)
    assert result.incomplete is False and len(result.outcomes) == 6
    assert await _statuses(session) == ["completed"] * 3
    assert await _count(session) == 6


# --- the registered recovery ----------------------------------------------------------------------


def _prereg() -> tuple[dict[str, Any], str]:
    path, pinned = load_execution_revision(REVISION, V5)
    return load_preregistration(path, dataset=V5, pinned_sha256=pinned)


PREREG, PREREG_SHA = _prereg()
SCHEDULE = load_execution_schedule(V5, PREREG)
RECOVERY = load_execution_recovery(V5, PREREG, SCHEDULE)


def test_the_recovery_plan_accounts_for_all_36_combinations() -> None:
    assert RECOVERY is not None and SCHEDULE is not None
    order = scheduled_combinations(V5, SCHEDULE, 2, STRATS)
    assert len(order) == 36 and RECOVERY["order"] == order
    carried = {(str(c["case_id"]), str(c["strategy"])) for c in RECOVERY["carried_over"]}
    assert carried == CARRIED and len(RECOVERY["execute"]) == 25
    assert set(RECOVERY["execute"]) | carried == set(order)
    assert RECOVERY["execute"][0] == ("T02", "routewise_tier_first")  # continues the sequence
    assert RECOVERY["original_runs"] == ORIGINAL
    assert all(str(c["run_id"]) == ORIGINAL[c["strategy"]] for c in RECOVERY["carried_over"])


def test_the_recovery_is_disclosed_as_post_hoc_and_never_publishable() -> None:
    plan = yaml.safe_load((EVAL_ROOT / RECOVERY_FILE).read_text(encoding="utf-8"))
    assert plan["kind"].startswith("POST-HOC RECOVERY AMENDMENT (disclosed)")
    assert "Never publishable" in plan["publishability"]
    assert any("Post-hoc" in x for x in plan["disclosed_limitations"])
    assert "complete only" in plan["completeness"].lower()
    assert "never re-run" in plan["policies"]["carried_over"]
    assert "DISCLOSED POST-HOC RECOVERY" in PREREG["changes_from_prereg_v5_2_3"][0]
    assert "never publishable" in PREREG["publication"]["rule"]
    # Everything else about the experiment is unchanged from v5.2.3.
    old = yaml.safe_load(
        (EVAL_ROOT / "preregistration_routewise_bench_v5.2.3.yaml").read_text(encoding="utf-8")
    )
    for key in ("execution_schedule", "scoring_amendment", "review_attestation", "quality_rule"):
        assert PREREG[key] == old[key], key
    for key in ("cost_rule", "statistics", "primary_metric", "run_validity", "quota"):
        assert PREREG[key] == old[key], key


@pytest.fixture
def recdir(tmp_path: Path) -> Path:
    for rel in (RECOVERY_FILE, "execution_schedule_routewise_bench_v5.2.3.yaml"):
        shutil.copyfile(EVAL_ROOT / rel, tmp_path / rel)
    return tmp_path


def _with(recdir: Path, mutate: Any) -> dict[str, Any]:
    doc = yaml.safe_load((recdir / RECOVERY_FILE).read_text(encoding="utf-8"))
    mutate(doc)
    raw = yaml.safe_dump(doc, sort_keys=False).encode()
    (recdir / RECOVERY_FILE).write_bytes(raw)
    prereg = copy.deepcopy(PREREG)
    prereg["execution_recovery"]["sha256"] = hashlib.sha256(raw).hexdigest()
    return prereg


BAD_PLANS: dict[str, tuple[Any, str]] = {
    "a carried combination re-run": (
        lambda d: d["execute"].insert(0, {"case_id": "S06", "strategy": "routewise"}),
        "each exactly once",
    ),
    "a missing combination": (lambda d: d["execute"].pop(), "each exactly once"),
    "out of order": (lambda d: d["execute"].reverse(), "registered order"),
    "another dataset": (lambda d: d.update(dataset_sha256="0" * 64), "different dataset"),
    "another schedule": (lambda d: d.update(schedule_sha256="0" * 64), "different execution"),
}


@pytest.mark.parametrize("name", sorted(BAD_PLANS))
def test_an_inconsistent_recovery_plan_is_refused(recdir: Path, name: str) -> None:
    mutate, message = BAD_PLANS[name]
    with pytest.raises(ValueError, match=message):
        load_execution_recovery(V5, _with(recdir, mutate), SCHEDULE, recdir)


def test_an_edited_recovery_plan_is_refused(recdir: Path) -> None:
    (recdir / RECOVERY_FILE).write_bytes((recdir / RECOVERY_FILE).read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed since it was pre-registered"):
        load_execution_recovery(V5, PREREG, SCHEDULE, recdir)


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


PACING = {"concurrency": 1, "delay_s": 6.0, "limit_cases": None, "allow_code_exec": False}


def test_v5_2_4_chain_and_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    rev = yaml.safe_load((EVAL_ROOT / f"{REVISION}.revision.yaml").read_text(encoding="utf-8"))
    assert rev["preregistration"]["sha256"] == PREREG_SHA
    assert rev["execution_recovery"] == PREREG["execution_recovery"]
    assert (
        hashlib.sha256((EVAL_ROOT / RECOVERY_FILE).read_bytes()).hexdigest()
        == (rev["execution_recovery"]["sha256"])
    )
    manifest = manifest_mod.check_manifest(PREREG, _settings(), _groq(), STRATS, run_params=PACING)
    assert manifest is not None
    files = manifest["pinned"]["files"]
    assert files["evidence/execution_recovery"]["sha256"] == rev["execution_recovery"]["sha256"]


async def test_the_runner_plans_only_the_25_registered_combinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    seen: list[Any] = []
    real = preflight.plan

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs.get("only"))
        return real(*args, **kwargs)

    monkeypatch.setattr(preflight, "plan", spy)
    with pytest.raises(ValueError, match="quota preflight failed"):  # no budget: before any call
        await run_benchmark(
            settings=_settings(),
            db=None,  # type: ignore[arg-type]  # never reached
            providers=_groq(),
            dataset=V5,
            strategies=STRATS,
            label="t",
            revision=REVISION,
            delay_s=6.0,
            schedule_day=2,
        )
    assert RECOVERY is not None and seen == [set(RECOVERY["execute"])]


async def test_the_runner_refuses_another_day_for_the_recovery() -> None:
    with pytest.raises(ValueError, match="the registered recovery is for day 2"):
        await run_benchmark(
            settings=_settings(),
            db=None,  # type: ignore[arg-type]
            providers=_groq(),
            dataset=V5,
            strategies=STRATS,
            label="t",
            revision=REVISION,
            delay_s=6.0,
            schedule_day=3,
        )


async def test_a_started_recovery_is_never_restarted(
    database_url: str, session: AsyncSession
) -> None:
    assert RECOVERY is not None
    session.add(
        EvaluationRun(
            label="earlier",
            strategy="routewise",
            dataset_version="routewise_bench_v5",
            config_snapshot={"execution_recovery": {"sha256": RECOVERY["sha256"]}},
            preregistration_sha256=PREREG_SHA,
            simulated=False,
            status="failed",
        )
    )
    await session.commit()
    db = Database(database_url)
    try:
        with pytest.raises(ValueError, match="already started"):
            await runner_mod._refuse_started_recovery(db, RECOVERY["sha256"], _no_sleep)
    finally:
        await db.dispose()


@pytest.fixture
def intended_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import cli
    from app.providers import registry

    async def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no network call may happen in these tests")

    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "get_settings", _settings)
    monkeypatch.setattr(registry, "build_providers", lambda settings: _groq())
    monkeypatch.setattr(registry, "refresh_catalogs", no_network)


def _main(*argv: str) -> int:
    from app import cli

    return cli.main(list(argv))


VALIDATE = ["eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION]


def test_eval_validate_reports_the_recovery_and_its_25_combination_preflight(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    budget = ["--remaining-daily-tokens", "120812", "--daily-budget-source", "test"]
    budget += ["--daily-budget-verified-at", datetime.now(UTC).isoformat()]
    assert _main(*VALIDATE, *budget, "--ledger", str(tmp_path / "l.json")) == 0
    out = capsys.readouterr().out
    assert "experiment_manifest_routewise_bench_v5.2.4.yaml: matches" in out
    assert "day 2: 11 carried over, 25 to execute" in out
    assert "gateway requests: 25" in out and "total conservative reservation: 108730" in out
    assert "preflight: OK" in out
    low = ["--remaining-daily-tokens", "120811", "--daily-budget-source", "test"]
    low += ["--daily-budget-verified-at", datetime.now(UTC).isoformat()]
    assert _main(*VALIDATE, *low, "--ledger", str(tmp_path / "l.json")) == 1


EVAL_RUN = ["eval-run", "--dataset", "routewise_bench_v5", "--label", "t", "--delay-s", "6"]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ([], "pass the day"),
        (["--schedule-day", "3"], "the registered recovery is for day 2"),
        (["--schedule-day", "2"], "quota preflight failed"),
    ],
)
def test_eval_run_refuses_before_any_network_call(
    intended_cli: None, capsys: Any, extra: list[str], message: str
) -> None:
    assert _main(*EVAL_RUN, "--revision", REVISION, *extra) == 2
    assert message in capsys.readouterr().err


def test_v5_2_3_is_refused_on_current_code(intended_cli: None, capsys: Any) -> None:
    assert _main(*EVAL_RUN, "--revision", "routewise_bench_v5.2.3", "--schedule-day", "2") == 2
    assert "configuration differs from experiment_manifest_routewise_bench_v5.2.3" in (
        capsys.readouterr().err
    )
