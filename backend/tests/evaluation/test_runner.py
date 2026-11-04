"""End-to-end benchmark pipeline on the mock provider (a pipeline check, never a result)."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvaluationCase, EvaluationResult, EvaluationRun, RequestLog
from app.db.session import Database
from app.evaluation.dataset import load_dataset
from app.evaluation.report import store_summaries, write_report
from app.evaluation.runner import run_benchmark
from app.providers.base import ProviderErrorKind
from app.providers.mock import MockProvider
from tests.conftest import make_settings


async def test_mock_benchmark_end_to_end(
    database_url: str, session: AsyncSession, tmp_path: Path
) -> None:
    settings = make_settings(database_url)
    db = Database(database_url)
    provider = MockProvider()
    # One forced failure, so failed cases must show up in the report rather than vanish.
    provider.script("mock-premium", [MockProvider.error(ProviderErrorKind.BAD_REQUEST)])
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    try:
        result = await run_benchmark(
            settings=settings,
            db=db,
            providers={"mock": provider},
            dataset=load_dataset(),
            strategies=["baseline_premium", "routewise", "routewise_tier_first"],
            label="pytest",
            delay_s=0.5,
            limit_cases=6,
            sleep=fake_sleep,
        )
        out, summary = write_report(result, tmp_path)
        await store_summaries(db, summary)
    finally:
        await db.dispose()

    assert result.simulated is True
    assert len(result.outcomes) == 18 and len(sleeps) == 18
    # Interleaving: case order alternates the strategy order.
    assert [o.strategy for o in result.outcomes[:6]] == [
        "baseline_premium",
        "routewise",
        "routewise_tier_first",
        "routewise_tier_first",
        "routewise",
        "baseline_premium",
    ]
    baseline = [o for o in result.outcomes if o.strategy == "baseline_premium"]
    assert {o.tier for o in baseline if o.error_code is None} == {"premium"}
    assert any(o.error_code for o in baseline)  # the scripted failure is reported

    assert summary["publishable"] is False
    assert any("simulated" in r for r in summary["publishable_reasons"])
    assert any("human-reviewed" in r for r in summary["publishable_reasons"])
    metrics = summary["metrics"]["baseline_premium"]
    assert metrics["failures"] == 1 and metrics["cases"] == 6
    assert "routewise" in summary["comparisons_vs_baseline"]
    assert out.name == "simulated-pytest"
    assert "SIMULATED RUN" in (out / "summary.md").read_text(encoding="utf-8")
    assert len((out / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 18
    json.loads((out / "summary.json").read_text(encoding="utf-8"))

    runs = (await session.scalars(select(EvaluationRun))).all()
    assert len(runs) == 3 and all(r.simulated and r.status == "completed" for r in runs)
    assert all(r.preregistration_sha256 and r.summary for r in runs)
    assert all(r.config_snapshot["dataset_sha256"] == result.dataset_sha256 for r in runs)
    assert await session.scalar(select(func.count()).select_from(EvaluationResult)) == 18
    assert await session.scalar(select(func.count()).select_from(EvaluationCase)) == 45
    # Requests went through the real gateway pipeline and were logged.
    assert await session.scalar(select(func.count()).select_from(RequestLog)) == 18
