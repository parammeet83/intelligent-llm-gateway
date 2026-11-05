"""Fail-closed guard for scripts/benchmark-day.ps1 (registered routewise_bench_v5.2.3 schedule).

Decides, before any provider request, whether a scheduled day may start. A day may never start
twice, even if an earlier attempt crashed before writing its report. The guard therefore checks
three independent records, and refuses if it can't read any of them:

1. local reports: a report for this day, a report directory for it, earlier days missing or
   incomplete, another day already on today's UTC date, or a schedule span over 14 days;
2. the persistent quota ledger: provider attempts already recorded on today's UTC date;
3. Neon: evaluation runs already created for this day, whatever their status (read-only query
   through the application's own settings).

Prints one JSON object (the day's registered requirement and the list of problems). Never prints
credentials or the database URL. Usage (from backend/):
    uv run --offline --frozen python ../scripts/benchmark_guard.py
        --day N --reports DIR --ledger FILE
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REVISION = "routewise_bench_v5.2.3"
LABEL = "v5.2.3-day{day}"
NEON_TIMEOUT_S = 60.0


def report_days(reports: Path) -> dict[int, list[dict[str, Any]]]:
    """Every local report of this revision, by scheduled day."""
    done: dict[int, list[dict[str, Any]]] = {}
    for summary in sorted(reports.glob("*/summary.json")):
        s = json.loads(summary.read_text(encoding="utf-8"))
        info = s.get("execution_schedule") or {}
        if s.get("execution_revision") == REVISION and info.get("day") is not None:
            done.setdefault(int(info["day"]), []).append(
                {
                    "dir": summary.parent.name,
                    "utc_date": info.get("utc_date"),
                    "incomplete": bool(s.get("incomplete")),
                }
            )
    return done


def evaluate(
    day: int,
    *,
    today: date,
    max_span_days: int,
    reports: Path,
    ledger_requests_today: Callable[[date], int],
    neon_runs: Callable[[int], list[dict[str, Any]]],
) -> dict[str, Any]:
    """All reasons the day may not start (empty = it may). Unreadable sources count as reasons."""
    problems: list[str] = []
    try:
        done = report_days(reports)
    except (OSError, ValueError) as error:
        done = {}
        problems.append(
            f"could not read local reports ({type(error).__name__}): refusing (fail closed)"
        )
    label = LABEL.format(day=day)
    if day in done:
        problems.append(
            f"day {day} already has a report ({done[day][0]['dir']}): each day runs exactly once"
        )
    if (reports / label).exists():
        problems.append(f"report directory {label} already exists: each day runs exactly once")
    for d in range(1, day):
        if d not in done:
            problems.append(f"day {d} has not run yet: days run in order")
    for d, entries in sorted(done.items()):
        for entry in entries:
            if entry["incomplete"] and d != day:
                problems.append(
                    f"day {d} is recorded as incomplete ({entry['dir']}): the registered "
                    "comparison "
                    "can no longer be completed, so no further day may run"
                )
            if entry["utc_date"] == today.isoformat():
                problems.append(
                    f"day {d} already ran on {today} (UTC): each day needs its own UTC date"
                )
    if 1 in done and done[1][0]["utc_date"]:
        span = (today - date.fromisoformat(done[1][0]["utc_date"])).days
        if span > max_span_days:
            problems.append(
                f"day 1 ran {span} days ago; the registered span is {max_span_days} days"
            )
    try:
        attempts = ledger_requests_today(today)
    except Exception as error:  # any failure to read the ledger refuses
        problems.append(
            f"could not read the quota ledger ({type(error).__name__}): refusing (fail closed)"
        )
    else:
        if attempts:
            problems.append(
                f"the quota ledger already records {attempts} provider attempt(s) "
                f"on {today} (UTC): "
                "a day that started is never restarted, and each day needs its own UTC date"
            )
    runs: list[dict[str, Any]] | None
    try:
        runs = neon_runs(day)
    except Exception as error:  # Neon unreachable or the query failed: never assume "no run"
        runs = None
        problems.append(
            f"could not check Neon for existing day {day} runs ({type(error).__name__}): "
            "refusing (fail closed)"
        )
    else:
        if runs:
            statuses = ", ".join(sorted({str(r.get("status")) for r in runs}))
            problems.append(
                f"Neon already has {len(runs)} evaluation run(s) for day {day} "
                f"(status: {statuses}): "
                "a day that started is never restarted, even if it failed"
            )
    return {"problems": problems, "local_reports": done, "neon_runs": runs}


def _neon_runs(schedule_sha256: str) -> Callable[[int], list[dict[str, Any]]]:
    """Read-only Neon lookup of runs for a scheduled day, via the application's own settings."""

    def query(day: int) -> list[dict[str, Any]]:
        from sqlalchemy import text

        from app.core.config import get_settings
        from app.db.session import Database

        async def run() -> list[dict[str, Any]]:
            db = Database(get_settings().database_url.get_secret_value())
            try:
                async with db.engine.connect() as conn:
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                    rows = (
                        (
                            await conn.execute(
                                text(
                                    "SELECT id::text AS id, strategy, status FROM evaluation_runs "
                                    "WHERE label = :label OR ("
                                    "config_snapshot->'execution_schedule'->>'day' = :day AND "
                                    "config_snapshot->'execution_schedule'->>'sha256' = :sha)"
                                ),
                                {
                                    "label": LABEL.format(day=day),
                                    "day": str(day),
                                    "sha": schedule_sha256,
                                },
                            )
                        )
                        .mappings()
                        .all()
                    )
                    await conn.rollback()
                    return [dict(r) for r in rows]
            finally:
                await db.dispose()

        return asyncio.run(asyncio.wait_for(run(), NEON_TIMEOUT_S))

    return query


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=int, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    import yaml

    from app.evaluation.dataset import (
        load_dataset,
        load_execution_revision,
        load_execution_schedule,
        load_preregistration,
    )
    from app.evaluation.pacing import QuotaLedger

    v5 = load_dataset("routewise_bench_v5")
    path, pinned = load_execution_revision(REVISION, v5)
    prereg, _ = load_preregistration(path, dataset=v5, pinned_sha256=pinned)
    schedule = load_execution_schedule(v5, prereg)
    if schedule is None or args.day not in schedule["days"]:
        print(json.dumps({"problems": [f"day {args.day} is not a registered schedule day"]}))
        return 0
    raw = yaml.safe_load((path.parent / schedule["file"]).read_text(encoding="utf-8"))
    ledger = QuotaLedger(args.ledger, "groq")
    result = evaluate(
        args.day,
        today=datetime.now(UTC).date(),
        max_span_days=schedule["max_span_days"],
        reports=args.reports,
        ledger_requests_today=ledger.requests_on,
        neon_runs=_neon_runs(schedule["sha256"]),
    )
    plan = raw["day_worst_case"][args.day]
    print(
        json.dumps(
            {
                "required": plan["required_remaining_daily_tokens"],
                "worst_case": plan["worst_case_tokens"],
                "cases": schedule["days"][args.day],
                "schedule_sha256": schedule["sha256"],
                **result,
            },
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
