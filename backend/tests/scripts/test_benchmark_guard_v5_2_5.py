"""scripts/benchmark_guard.py for revision routewise_bench_v5.2.5 (Day 3 only, execution window,
execution claims). The v5.2.3 behaviour is covered, unchanged, by test_benchmark_guard.py.

No provider is called and no real database is used: Neon lookups are injected fakes, and reports and
ledgers live in temporary directories.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.core.config import REPO_ROOT
from app.evaluation import runner as runner_mod
from app.evaluation.pacing import QuotaLedger

_spec = importlib.util.spec_from_file_location(
    "benchmark_guard", REPO_ROOT / "scripts" / "benchmark_guard.py"
)
assert _spec and _spec.loader
guard: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

REVISION = "routewise_bench_v5.2.5"
TODAY = date(2026, 11, 10)


def _no_runs(day: int) -> list[dict[str, Any]]:
    return []


def _evaluate(reports: Path, neon: Any = _no_runs, day: int = 3, **kw: Any) -> list[str]:
    result = guard.evaluate(
        day,
        today=TODAY,
        max_span_days=14,
        reports=reports,
        ledger_requests_today=QuotaLedger(reports / "ledger.json", "groq").requests_on,
        neon_runs=neon,
        revision=REVISION,
        days_in_scope=[3],
        **kw,
    )
    problems: list[str] = result["problems"]
    return problems


def _report(reports: Path, revision: str, day: int, utc_date: str, incomplete: bool) -> None:
    out = reports / f"{revision.removeprefix('routewise_bench_')}-day{day}"
    out.mkdir(parents=True)
    summary = {
        "execution_revision": revision,
        "execution_schedule": {"day": day, "utc_date": utc_date},
        "incomplete": incomplete,
    }
    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def test_day_3_may_start_with_nothing_recorded_for_v5_2_5(tmp_path: Path) -> None:
    # the earlier days belong to other revisions (v5.2.3 Day 1, the v5.2.3 Day 2 incident record
    # and the v5.2.4 recovery); they neither block nor satisfy v5.2.5's own order checks
    _report(tmp_path, "routewise_bench_v5.2.3", 1, "2026-11-04", False)
    _report(tmp_path, "routewise_bench_v5.2.3", 2, "2026-11-05", True)
    assert _evaluate(tmp_path) == []
    assert guard.day_label(REVISION, 3) == "v5.2.5-day3"


def test_day_4_is_not_registered_by_v5_2_5(tmp_path: Path) -> None:
    problems = _evaluate(tmp_path, day=4)
    assert problems[0] == f"{REVISION} does not register day 4 (registered: [3])"


@pytest.mark.parametrize(
    "rows",
    [
        [{"id": "c-1", "status": "claimed"}],  # an execution claim
        [{"id": "r-1", "status": "failed"}],  # a run, whatever its status
    ],
)
def test_a_claim_or_run_in_neon_refuses(tmp_path: Path, rows: list[dict[str, Any]]) -> None:
    problems = _evaluate(tmp_path, lambda day: rows)
    assert len(problems) == 1 and "Neon already has 1 evaluation run(s) for day 3" in problems[0]


@pytest.mark.parametrize("error", [TimeoutError("timed out"), OSError, RuntimeError("no table")])
def test_neon_unavailable_or_without_the_claims_table_fails_closed(
    tmp_path: Path, error: Any
) -> None:
    def broken(day: int) -> list[dict[str, Any]]:
        raise error

    problems = _evaluate(tmp_path, broken)
    assert len(problems) == 1 and "could not check Neon" in problems[0]
    assert "fail closed" in problems[0]


def test_an_existing_v5_2_5_report_refuses(tmp_path: Path) -> None:
    _report(tmp_path, REVISION, 3, "2026-11-08", False)
    problems = _evaluate(tmp_path)
    assert "day 3 already has a report (v5.2.5-day3): each day runs exactly once" in problems


def test_a_window_problem_is_reported_first(tmp_path: Path) -> None:
    problems = _evaluate(tmp_path, window_problem="outside the registered execution window")
    assert problems == ["outside the registered execution window"]


def _main(tmp_path: Path, day: int, monkeypatch: pytest.MonkeyPatch, capsys: Any) -> Any:
    real = runner_mod.check_execution_window

    def inside(prereg: dict[str, Any], d: int, now: datetime) -> None:
        real(prereg, d, datetime(2026, 11, 10, 12, 0, tzinfo=UTC))

    monkeypatch.setattr(runner_mod, "check_execution_window", inside)
    monkeypatch.setattr(guard, "_neon_runs", lambda sha, revision: _no_runs)
    args = ["--day", str(day), "--reports", str(tmp_path), "--ledger", str(tmp_path / "l.json")]
    assert guard.main([*args, "--revision", REVISION]) == 0
    return json.loads(capsys.readouterr().out)


def test_main_reports_the_registered_day_3_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    out = _main(tmp_path, 3, monkeypatch, capsys)
    assert out["problems"] == [] and out["required"] == 157747 and out["worst_case"] == 141972
    assert out["cases"] == [
        "S02",
        "S03",
        "S09",
        "S10",
        "T05",
        "T07",
        "T11",
        "T13",
        "C07",
        "C09",
        "C12",
    ]


def test_main_refuses_day_4_through_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    problems = _main(tmp_path, 4, monkeypatch, capsys)["problems"]
    assert problems[0] == "this registration authorises day(s) [3] only, not day 4"
    assert f"{REVISION} does not register day 4 (registered: [3])" in problems
