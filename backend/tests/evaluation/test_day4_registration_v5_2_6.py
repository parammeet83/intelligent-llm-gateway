"""Revision routewise_bench_v5.2.6: post-incident, exploratory Day 4 registration.

The run-once machinery itself is tested in test_day3_registration_v5_2_5.py. These tests check the
v5.2.6 chain and its window, and that the same protections apply to Day 4. No provider is called and
Neon is never used.
"""

from __future__ import annotations

import asyncio
import hashlib
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
from app.evaluation.runner import check_execution_window, claim_scheduled_day, run_benchmark
from app.providers.groq import GroqProvider

REVISION = "routewise_bench_v5.2.6"
STRATS = ["baseline_premium", "routewise", "routewise_tier_first"]
DAY4 = ["S01", "S04", "S12", "S13", "S15", "T01", "T04", "T10", "T12", "C02", "C04", "C05"]
INSIDE = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
V5 = load_dataset("routewise_bench_v5")
V5_2_5 = {
    "routewise_bench_v5.2.5.revision.yaml": (
        "27966b436884cc89db91c87ad316111b0e0e5e4cc2b7981076526ae8262692e8"
    ),
    "preregistration_routewise_bench_v5.2.5.yaml": (
        "9b1f17befef2ae93409f48ec58807e703e2d19253215391b54411c3d624b1818"
    ),
    "experiment_manifest_routewise_bench_v5.2.5.yaml": (
        "da3001d6ac9ca5df4681230736f784fc72dad618d1f77a0edfd61c59ccd6fca7"
    ),
}


def _prereg(revision: str = REVISION) -> tuple[dict[str, Any], str]:
    path, pinned = load_execution_revision(revision, V5)
    return load_preregistration(path, dataset=V5, pinned_sha256=pinned)


PREREG, PREREG_SHA = _prereg()
SCHEDULE = load_execution_schedule(V5, PREREG)


async def _no_sleep(seconds: float) -> None:
    return None


def _yaml(name: str) -> Any:
    return yaml.safe_load((EVAL_ROOT / name).read_text(encoding="utf-8"))


# --- the registration -----------------------------------------------------------------------------


def test_v5_2_5_is_unchanged() -> None:
    for name, sha in V5_2_5.items():
        assert hashlib.sha256((EVAL_ROOT / name).read_bytes()).hexdigest() == sha, name


def test_the_chain_reuses_the_pinned_schedule_for_day_4_only() -> None:
    rev = _yaml(f"{REVISION}.revision.yaml")
    assert rev["preregistration"]["sha256"] == PREREG_SHA
    assert rev["authorised_days"] == [4] and rev["publishable"] is False
    assert rev["amends_revision"]["sha256"] == V5_2_5["routewise_bench_v5.2.5.revision.yaml"]
    assert (EVAL_ROOT / rev["changelog"]).is_file()
    assert SCHEDULE is not None and SCHEDULE["days"][4] == DAY4
    assert len(scheduled_combinations(V5, SCHEDULE, 4, STRATS)) == 36
    assert load_execution_recovery(V5, PREREG, SCHEDULE) is None


def test_disclosed_as_post_incident_exploratory_and_non_publishable() -> None:
    text = (EVAL_ROOT / "preregistration_routewise_bench_v5.2.6.yaml").read_text(encoding="utf-8")
    assert "POST-INCIDENT" in text and "EXPLORATORY" in text and "DAY 4 ONLY" in text
    assert PREREG["publishable"] is False and "exploratory" in PREREG["publishable_reason"]
    assert "POST-INCIDENT, EXPLORATORY DAY 4" in PREREG["changes_from_prereg_v5_2_5"][0]
    assert "No other day is authorised" in PREREG["changes_from_prereg_v5_2_5"][1]
    assert "remains incomplete" in PREREG["changes_from_prereg_v5_2_5"][-1]
    assert "v5.2.6 Day 4 registration is post-incident" in PREREG["publication"]["rule"]


def test_only_identity_window_and_disclosures_differ_from_v5_2_5() -> None:
    old, _ = _prereg("routewise_bench_v5.2.5")
    changed = {k for k in set(PREREG) | set(old) if PREREG.get(k) != old.get(k)}
    assert changed == {
        "version",
        "registered_on",
        "registered_at_utc",
        "revision",
        "supersedes",
        "amends_revision",
        "publishable_reason",
        "experiment_manifest",
        "execution_window",
        "changes_from_prereg_v5_2_4",
        "changes_from_prereg_v5_2_5",
        "execution",
        "publication",
    }
    new_manifest = _yaml("experiment_manifest_routewise_bench_v5.2.6.yaml")["pinned"]
    old_manifest = _yaml("experiment_manifest_routewise_bench_v5.2.5.yaml")["pinned"]
    assert new_manifest == old_manifest  # identical pinned code and configuration


@pytest.mark.parametrize(
    ("day", "now", "message"),
    [
        (3, INSIDE, r"authorises day\(s\) \[4\] only, not day 3"),
        (1, INSIDE, r"not day 1"),
        (4, datetime(2026, 11, 6, 23, 0, tzinfo=UTC), "outside the registered execution window"),
        (4, datetime(2026, 11, 19, 0, 1, tzinfo=UTC), "outside the registered execution window"),
        (4, datetime(2026, 11, 7, 22, 0, 1, tzinfo=UTC), "after the registered latest start"),
    ],
)
def test_the_window_refuses_other_days_dates_and_late_starts(
    day: int, now: datetime, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        check_execution_window(PREREG, day, now)


@pytest.mark.parametrize(
    "now", [datetime(2026, 11, 7, 0, 0, tzinfo=UTC), datetime(2026, 11, 18, 22, 0, tzinfo=UTC)]
)
def test_the_window_allows_day_4_inside_it(now: datetime) -> None:
    check_execution_window(PREREG, 4, now)


# --- run-once protection for Day 4 ----------------------------------------------------------------


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
    real = runner_mod.check_execution_window

    def at_inside(prereg: dict[str, Any], day: int, now: datetime) -> None:
        real(prereg, day, INSIDE)

    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(runner_mod, "check_execution_window", at_inside)


class _Stop(Exception):
    """Raised where the run would create its tenant: everything before it passed."""


@pytest.fixture
def stop_before_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def stop(*args: Any, **kwargs: Any) -> Any:
        raise _Stop

    monkeypatch.setattr(runner_mod, "_eval_tenant", stop)


async def _start_day_4(database_url: str, tmp_path: Path) -> None:
    db = Database(database_url)
    try:
        await run_benchmark(
            settings=_settings(),
            db=db,
            providers=_groq(),
            dataset=V5,
            strategies=STRATS,
            label="v5.2.6-day4",
            revision=REVISION,
            delay_s=6.0,
            schedule_day=4,
            daily_budget=DailyBudget(
                remaining_tokens=167_285, verified_at=datetime.now(UTC), source="test"
            ),
            ledger_path=tmp_path / "ledger.json",
            sleep=_no_sleep,
        )
    finally:
        await db.dispose()


async def _claims(session: AsyncSession) -> list[tuple[str, int]]:
    session.expire_all()
    rows = (await session.scalars(select(BenchmarkExecutionClaim))).all()
    return sorted((c.revision, c.schedule_day) for c in rows)


async def test_day_4_is_claimed_once_and_a_second_start_is_refused(
    fixed_window: None,
    stop_before_runs: None,
    database_url: str,
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    db = Database(database_url)
    try:  # the completed Day 3 claim already exists and must stay untouched
        await claim_scheduled_day(db, "routewise_bench_v5.2.5", 3, "v5.2.5-day3", _no_sleep)
    finally:
        await db.dispose()
    with pytest.raises(_Stop):
        await _start_day_4(database_url, tmp_path)
    with pytest.raises(ValueError, match="already started"):
        await _start_day_4(database_url, tmp_path)
    assert await _claims(session) == [("routewise_bench_v5.2.5", 3), (REVISION, 4)]
    assert int(await session.scalar(select(func.count()).select_from(EvaluationRun)) or 0) == 0


async def test_concurrent_day_4_starts_let_exactly_one_through(
    fixed_window: None,
    stop_before_runs: None,
    database_url: str,
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    results = await asyncio.gather(
        *(_start_day_4(database_url, tmp_path / str(i)) for i in range(3)), return_exceptions=True
    )
    assert sum(isinstance(r, _Stop) for r in results) == 1, results
    assert await _claims(session) == [(REVISION, 4)]


async def test_a_failed_earlier_day_4_run_blocks_a_restart(
    fixed_window: None,
    stop_before_runs: None,
    database_url: str,
    session: AsyncSession,
    tmp_path: Path,
) -> None:
    session.add(
        EvaluationRun(
            label="earlier",
            strategy="routewise",
            dataset_version="routewise_bench_v5",
            config_snapshot={"execution_revision": REVISION, "execution_schedule": {"day": 4}},
            preregistration_sha256="x" * 64,
            simulated=False,
            status="failed",
        )
    )
    await session.commit()
    with pytest.raises(ValueError, match="already started"):
        await _start_day_4(database_url, tmp_path)
    assert await _claims(session) == []


async def test_an_unreachable_database_refuses_day_4(
    fixed_window: None, stop_before_runs: None, tmp_path: Path
) -> None:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'missing' / 'x.db').as_posix()}"
    with pytest.raises(runner_mod.DatabaseUnavailable):
        await _start_day_4(url, tmp_path)


# --- the CLI --------------------------------------------------------------------------------------


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


def _budget(tokens: int) -> list[str]:
    return [
        "--remaining-daily-tokens",
        str(tokens),
        "--daily-budget-source",
        "test",
        "--daily-budget-verified-at",
        datetime.now(UTC).isoformat(),
    ]


VALIDATE = ["eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION]


def test_eval_validate_reports_the_36_combination_day_4_preflight(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    ledger = ["--ledger", str(tmp_path / "l.json")]
    assert _main(*VALIDATE, "--schedule-day", "4", *_budget(167_285), *ledger) == 0
    out = capsys.readouterr().out
    assert "experiment_manifest_routewise_bench_v5.2.6.yaml: matches" in out
    assert "execution window: day(s) [4] on one UTC date from 2026-11-07 to 2026-11-18" in out
    assert "gateway requests: 36" in out and "total conservative reservation: 150556" in out
    assert "preflight: OK" in out
    assert _main(*VALIDATE, "--schedule-day", "4", *_budget(167_284), *ledger) == 1


EVAL_RUN = ["eval-run", "--dataset", "routewise_bench_v5", "--label", "t", "--delay-s", "6"]


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--schedule-day", "3"], "authorises day(s) [4] only, not day 3"),
        (["--schedule-day", "4"], "quota preflight failed"),
    ],
)
def test_eval_run_refuses_before_any_network_call(
    intended_cli: None, capsys: Any, extra: list[str], message: str
) -> None:
    assert _main(*EVAL_RUN, "--revision", REVISION, *extra) == 2
    assert message in capsys.readouterr().err


def test_v5_2_5_still_refuses_day_4(intended_cli: None, capsys: Any) -> None:
    assert _main(*EVAL_RUN, "--revision", "routewise_bench_v5.2.5", "--schedule-day", "4") == 2
    assert "authorises day(s) [3] only, not day 4" in capsys.readouterr().err
