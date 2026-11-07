"""scripts/benchmark_guard.py for revision routewise_bench_v5.2.6 (Day 4 only).

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

REVISION = "routewise_bench_v5.2.6"
DAY4 = ["S01", "S04", "S12", "S13", "S15", "T01", "T04", "T10", "T12", "C02", "C04", "C05"]


def _no_runs(day: int) -> list[dict[str, Any]]:
    return []


def _evaluate(reports: Path, neon: Any = _no_runs, day: int = 4) -> list[str]:
    result = guard.evaluate(
        day,
        today=date(2026, 11, 7),
        max_span_days=14,
        reports=reports,
        ledger_requests_today=QuotaLedger(reports / "ledger.json", "groq").requests_on,
        neon_runs=neon,
        revision=REVISION,
        days_in_scope=[4],
    )
    problems: list[str] = result["problems"]
    return problems


def test_day_4_may_start_with_nothing_recorded(tmp_path: Path) -> None:
    assert _evaluate(tmp_path) == []
    assert guard.day_label(REVISION, 4) == "v5.2.6-day4"


def test_day_3_is_not_registered_by_v5_2_6(tmp_path: Path) -> None:
    assert _evaluate(tmp_path, day=3)[0] == f"{REVISION} does not register day 3 (registered: [4])"


def test_an_existing_claim_refuses(tmp_path: Path) -> None:
    problems = _evaluate(tmp_path, lambda day: [{"id": "c-1", "status": "claimed"}])
    assert len(problems) == 1 and "Neon already has 1 evaluation run(s) for day 4" in problems[0]


def test_neon_unavailable_fails_closed(tmp_path: Path) -> None:
    def broken(day: int) -> list[dict[str, Any]]:
        raise TimeoutError("timed out")

    problems = _evaluate(tmp_path, broken)
    assert len(problems) == 1 and "fail closed" in problems[0]


def test_main_reports_the_registered_day_4_requirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    real = runner_mod.check_execution_window

    def inside(prereg: dict[str, Any], d: int, now: datetime) -> None:
        real(prereg, d, datetime(2026, 11, 7, 12, 0, tzinfo=UTC))

    monkeypatch.setattr(runner_mod, "check_execution_window", inside)
    monkeypatch.setattr(guard, "_neon_runs", lambda sha, revision: _no_runs)
    args = ["--day", "4", "--reports", str(tmp_path), "--ledger", str(tmp_path / "l.json")]
    assert guard.main([*args, "--revision", REVISION]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["problems"] == [] and out["required"] == 167285 and out["worst_case"] == 150556
    assert out["cases"] == DAY4
