"""scripts/benchmark_guard.py: a scheduled benchmark day can never start twice (fail closed).

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
from app.evaluation.pacing import QuotaLedger

_spec = importlib.util.spec_from_file_location(
    "benchmark_guard", REPO_ROOT / "scripts" / "benchmark_guard.py"
)
assert _spec and _spec.loader
guard: Any = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)

TODAY = date(2026, 11, 6)


def _report(reports: Path, day: int, utc_date: str, *, incomplete: bool = False) -> None:
    out = reports / f"v5.2.3-day{day}"
    out.mkdir(parents=True)
    summary = {
        "execution_revision": "routewise_bench_v5.2.3",
        "execution_schedule": {"day": day, "utc_date": utc_date},
        "incomplete": incomplete,
    }
    (out / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def _ledger(path: Path, *, on: date | None = None) -> QuotaLedger:
    ledger = QuotaLedger(path, "groq")
    if on is not None:
        ledger.add(
            {
                "id": "attempt-1",
                "model": "openai/gpt-oss-20b",
                "reserved_at": datetime(on.year, on.month, on.day, 6, 0, tzinfo=UTC).isoformat(),
                "tpm_reserved_tokens": 500,
                "daily_tokens": 120,
                "status": "sent_known",
            }
        )
    return ledger


def _no_runs(day: int) -> list[dict[str, Any]]:
    return []


def _evaluate(day: int, reports: Path, ledger: QuotaLedger, neon: Any = _no_runs) -> list[str]:
    result = guard.evaluate(
        day,
        today=TODAY,
        max_span_days=14,
        reports=reports,
        ledger_requests_today=ledger.requests_on,
        neon_runs=neon,
    )
    problems: list[str] = result["problems"]
    return problems


def test_a_clean_next_day_may_start(tmp_path: Path) -> None:
    _report(tmp_path, 1, "2026-11-04")
    _report(tmp_path, 2, "2026-11-05")
    assert _evaluate(3, tmp_path, _ledger(tmp_path / "ledger.json", on=date(2026, 11, 5))) == []


def test_day_one_with_nothing_recorded_may_start(tmp_path: Path) -> None:
    assert _evaluate(1, tmp_path, _ledger(tmp_path / "ledger.json")) == []
    assert not (tmp_path / "ledger.json").exists()  # read-only: no ledger file created


def test_neon_runs_without_a_local_report_refuse(tmp_path: Path) -> None:
    """The Day 2 incident: the run crashed before writing its report, but its runs exist in Neon."""
    _report(tmp_path, 1, "2026-11-04")

    def runs(day: int) -> list[dict[str, Any]]:
        return (
            [{"id": "4c2aed09", "strategy": "baseline_premium", "status": "failed"}]
            if day == 2
            else []
        )

    problems = _evaluate(2, tmp_path, _ledger(tmp_path / "ledger.json"), runs)
    assert len(problems) == 1 and "Neon already has 1 evaluation run(s) for day 2" in problems[0]
    assert "status: failed" in problems[0]


def test_ledger_attempts_today_without_a_local_report_refuse(tmp_path: Path) -> None:
    _report(tmp_path, 1, "2026-11-04")
    problems = _evaluate(2, tmp_path, _ledger(tmp_path / "ledger.json", on=TODAY))
    assert (
        len(problems) == 1 and "quota ledger already records 1 provider attempt(s)" in problems[0]
    )


def test_an_existing_report_refuses(tmp_path: Path) -> None:
    _report(tmp_path, 1, "2026-11-04")
    problems = _evaluate(1, tmp_path, _ledger(tmp_path / "ledger.json"))
    assert any("day 1 already has a report" in p for p in problems)
    assert any("report directory v5.2.3-day1 already exists" in p for p in problems)


def test_an_existing_report_directory_without_a_summary_refuses(tmp_path: Path) -> None:
    _report(tmp_path, 1, "2026-11-04")
    (tmp_path / "v5.2.3-day2").mkdir()
    problems = _evaluate(2, tmp_path, _ledger(tmp_path / "ledger.json"))
    assert problems == ["report directory v5.2.3-day2 already exists: each day runs exactly once"]


@pytest.mark.parametrize("error", [TimeoutError("timed out"), OSError("unreachable"), RuntimeError])
def test_neon_unavailable_fails_closed(tmp_path: Path, error: Any) -> None:
    def broken(day: int) -> list[dict[str, Any]]:
        raise error

    problems = _evaluate(1, tmp_path, _ledger(tmp_path / "ledger.json"), broken)
    assert len(problems) == 1 and "could not check Neon" in problems[0]
    assert "fail closed" in problems[0]


def test_an_unreadable_ledger_fails_closed(tmp_path: Path) -> None:
    def broken(day: date) -> int:
        raise ValueError("corrupt ledger")

    result = guard.evaluate(
        1,
        today=TODAY,
        max_span_days=14,
        reports=tmp_path,
        ledger_requests_today=broken,
        neon_runs=_no_runs,
    )
    assert result["problems"] == [
        "could not read the quota ledger (ValueError): refusing (fail closed)"
    ]


def test_an_incomplete_earlier_day_blocks_every_later_day(tmp_path: Path) -> None:
    _report(tmp_path, 1, "2026-11-04")
    _report(tmp_path, 2, "2026-11-05", incomplete=True)
    for day in (3, 4):
        problems = _evaluate(day, tmp_path, _ledger(tmp_path / "ledger.json"))
        assert any("day 2 is recorded as incomplete" in p for p in problems)


def test_order_same_date_and_span_rules_still_hold(tmp_path: Path) -> None:
    _report(tmp_path, 1, "2026-11-06")
    problems = _evaluate(3, tmp_path, _ledger(tmp_path / "ledger.json"))
    assert "day 2 has not run yet: days run in order" in problems
    assert "day 1 already ran on 2026-11-06 (UTC): each day needs its own UTC date" in problems
    late = guard.evaluate(
        2,
        today=date(2026, 11, 21),
        max_span_days=14,
        reports=tmp_path,
        ledger_requests_today=_ledger(tmp_path / "l.json").requests_on,
        neon_runs=_no_runs,
    )["problems"]
    assert "day 1 ran 15 days ago; the registered span is 14 days" in late


def test_preflight_and_run_paths_share_the_guard() -> None:
    """The helper runs the guard before the preflight and before the -Run branch, unconditionally,
    so the preflight-only and -Run invocations enforce exactly the same checks."""
    script = (REPO_ROOT / "scripts" / "benchmark-day.ps1").read_text(encoding="utf-8")
    body = script[script.index("$ErrorActionPreference") :]
    calls = [
        body.index("scripts\\benchmark_guard.py"),
        body.index("if (@($info.problems).Count -gt 0) { throw"),
        body.index("app.cli eval-validate"),
        body.index("if (-not $Run)"),
        body.index("app.cli eval-run"),
    ]
    assert calls == sorted(calls)
    assert body.count('"scripts\\benchmark_guard.py"') == 1  # invoked exactly once
    assert body.count("app.cli eval-run") == 1
    guard_block = body[: calls[1]]
    assert "$Run" not in guard_block  # the guard doesn't depend on -Run
    assert "if ($LASTEXITCODE) { throw" in guard_block  # a guard crash refuses


def test_the_guard_never_prints_credentials(tmp_path: Path, capsys: Any) -> None:
    def broken(day: int) -> list[dict[str, Any]]:
        raise OSError("postgresql://user:secret@host/db unreachable")  # pragma: allowlist secret

    problems = _evaluate(1, tmp_path, _ledger(tmp_path / "ledger.json"), broken)
    assert "secret" not in " ".join(problems) and "postgresql://" not in " ".join(problems)
