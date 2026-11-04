"""Revision routewise_bench_v5.2.3: the registered four-day execution schedule.

Self-contained (no imports from other test modules) so it runs from the clean-room review bundle.
No provider is called. Day reports for the combine tests are synthetic and written to a temporary
directory; they are never reported as results.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.config import Settings
from app.evaluation import manifest as manifest_mod
from app.evaluation import preflight
from app.evaluation import runner as runner_mod
from app.evaluation.dataset import (
    EVAL_ROOT,
    apply_review_attestation,
    apply_scoring_amendment,
    load_dataset,
    load_execution_revision,
    load_execution_schedule,
    load_preregistration,
    schedule_day_cases,
)
from app.evaluation.pacing import GROQ_QUOTA_V5_2
from app.providers.groq import GroqProvider

REVISION = "routewise_bench_v5.2.3"
V5 = load_dataset("routewise_bench_v5")
SCHEDULE_FILE = "execution_schedule_routewise_bench_v5.2.3.yaml"
STRATEGIES = ["baseline_premium", "routewise", "routewise_tier_first"]
PACING = {"concurrency": 1, "delay_s": 6.0, "limit_cases": None, "allow_code_exec": False}
# Preserved byte-for-byte (verified against the repository).
PRESERVED = {
    "routewise_bench_v5.2.2.revision.yaml": (
        "66320623bb6d6bc3518f6ebb5bf1b1c1e6c59830bca016d22639f33927de6bf7"
    ),
    "preregistration_routewise_bench_v5.2.2.yaml": (
        "2c8f76fbd3d6fa498d2922ee732481e0ea3f96e567d023228af403b972203b73"
    ),
    "experiment_manifest_routewise_bench_v5.2.2.yaml": (
        "de0117cae450b4038b214857691ff8cdbc33bf201dc08b646bffbcbbe3ce8a20"
    ),
    "reviews/routewise_bench_v5.2.1_HUMAN_REVIEW_ATTESTATION.yaml": (
        "b7099444ac312eef336ebacbdb6e93335ba366f9de452be88cb17a97524c59ed"
    ),
    "datasets/routewise_bench_v5.jsonl": (
        "76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd"
    ),
    "datasets/routewise_bench_v5.meta.yaml": (
        "262dde03c4018fe1f79c1fe8760f32cfcce3e1624284ea6b56eafed432806ada"
    ),
}
DAYS = {
    1: ["S05", "S08", "S11", "T03", "T06", "T16", "T17", "C03", "C10", "C11"],
    2: ["S06", "S07", "S14", "T02", "T08", "T09", "T14", "T15", "T18", "C01", "C06", "C08"],
    3: ["S02", "S03", "S09", "S10", "T05", "T07", "T11", "T13", "C07", "C09", "C12"],
    4: ["S01", "S04", "S12", "S13", "S15", "T01", "T04", "T10", "T12", "C02", "C04", "C05"],
}
DAY_TOKENS = {1: 146532, 2: 144678, 3: 141972, 4: 150556}
TPD, DAY_SAFETY = 200_000, 0.9


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prereg() -> tuple[dict[str, Any], str]:
    prereg_path, pinned = load_execution_revision(REVISION, V5)
    return load_preregistration(prereg_path, dataset=V5, pinned_sha256=pinned)


PREREG, PREREG_SHA = _prereg()
SCHEDULE = load_execution_schedule(V5, PREREG)
AMENDED, AMENDMENT = apply_scoring_amendment(V5, PREREG)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        groq_enabled=True,
        groq_api_key="test-placeholder-key-0000000000000000",
        groq_billing_plan="free",
        mock_provider_enabled=False,
    )


def _groq() -> dict[str, Any]:
    return {"groq": GroqProvider(api_key="test-placeholder", charge_basis="free_tier")}


def _plan(case_ids: list[str]) -> preflight.Preflight:
    by_id = {c.id: c for c in AMENDED.cases}
    subset = AMENDED.model_copy(update={"cases": [by_id[c] for c in case_ids]})
    return preflight.plan(subset, STRATEGIES, _settings(), _groq(), GROQ_QUOTA_V5_2)


# --- preserved history and the schedule itself ----------------------------------------------------


def test_previous_registrations_are_byte_identical() -> None:
    for rel, want in PRESERVED.items():
        assert _sha(EVAL_ROOT / rel) == want, rel


def test_the_schedule_covers_every_case_exactly_once_in_dataset_order() -> None:
    assert SCHEDULE is not None and SCHEDULE["days"] == DAYS
    flat = [c for ids in DAYS.values() for c in ids]
    assert sorted(flat) == sorted(c.id for c in V5.cases) and len(flat) == len(set(flat)) == 45
    order = {c.id: i for i, c in enumerate(V5.cases)}
    for ids in DAYS.values():
        assert [order[c] for c in ids] == sorted(order[c] for c in ids)
    assert SCHEDULE["max_span_days"] == 14


def test_the_allocation_is_reproducible_from_the_registered_method() -> None:
    raw = yaml.safe_load((EVAL_ROOT / SCHEDULE_FILE).read_text(encoding="utf-8"))
    rng = random.Random(raw["allocation"]["seed"])  # noqa: S311 (a registered allocation, not security)
    load = {c.id: _plan([c.id]).total_reservation_tokens for c in AMENDED.cases}
    days: dict[int, list[str]] = {d: [] for d in DAYS}
    totals = {d: 0 for d in DAYS}
    for stratum in ("complex", "standard", "simple"):
        ids = [c.id for c in AMENDED.cases if c.difficulty == stratum]
        rng.shuffle(ids)
        count = {d: 0 for d in DAYS}
        for cid in ids:
            day = min(totals, key=lambda k: (totals[k], count[k], k))
            days[day].append(cid)
            totals[day] += load[cid]
            count[day] += 1
    order = {c.id: i for i, c in enumerate(AMENDED.cases)}
    assert {d: sorted(ids, key=lambda c: order[c]) for d, ids in days.items()} == DAYS
    for prefix in ("S", "T", "C"):  # each difficulty stratum is spread across all four days
        assert all(any(c.startswith(prefix) for c in ids) for ids in DAYS.values())


# --- quota arithmetic -----------------------------------------------------------------------------


def test_totals_match_the_registered_single_day_preflight() -> None:
    whole = _plan([c.id for c in AMENDED.cases])
    assert (whole.gateway_requests, whole.max_provider_attempts) == (135, 378)
    assert whole.total_reservation_tokens == 583738 == sum(DAY_TOKENS.values())
    assert (whole.input_reservation_tokens, whole.output_reservation_tokens) == (195642, 388096)
    usable = TPD * DAY_SAFETY
    assert whole.total_reservation_tokens > usable  # one day can't hold it
    assert math.ceil(whole.total_reservation_tokens / usable) == 4  # minimum under the shared cap


@pytest.mark.parametrize("day", sorted(DAYS))
def test_each_day_fits_one_day_of_quota_with_margin(day: int) -> None:
    pre = _plan(DAYS[day])
    registered = yaml.safe_load((EVAL_ROOT / SCHEDULE_FILE).read_text(encoding="utf-8"))
    plan = registered["day_worst_case"][day]
    assert pre.total_reservation_tokens == plan["worst_case_tokens"] == DAY_TOKENS[day]
    assert pre.max_provider_attempts == plan["max_provider_attempts"]
    assert pre.gateway_requests == plan["gateway_requests"] == 3 * len(DAYS[day])
    # The shared guard: all Groq models together within 90% of the smaller remaining budget.
    assert pre.total_reservation_tokens <= TPD * DAY_SAFETY
    assert plan["required_remaining_daily_tokens"] == math.ceil(pre.total_reservation_tokens / 0.9)
    assert plan["required_remaining_daily_tokens"] <= TPD
    # Each model separately well inside its own limits.
    for model, m in plan["per_model"].items():
        assert m["worst_case_tokens"] <= TPD * DAY_SAFETY, model
        assert m["max_attempts"] <= 1000 * DAY_SAFETY, model
    assert sum(m["worst_case_tokens"] for m in plan["per_model"].values()) == DAY_TOKENS[day]
    assert pre.max_provider_attempts <= 1000 * DAY_SAFETY  # requests per day (shared cap)
    assert pre.largest_attempt_tokens <= 8000 * 0.75  # a single attempt fits the per-minute cap


def test_per_model_totals_across_the_schedule() -> None:
    registered = yaml.safe_load((EVAL_ROOT / SCHEDULE_FILE).read_text(encoding="utf-8"))
    per_model: dict[str, dict[str, int]] = {}
    for plan in registered["day_worst_case"].values():
        for model, m in plan["per_model"].items():
            acc = per_model.setdefault(model, {"max_attempts": 0, "worst_case_tokens": 0})
            acc["max_attempts"] += m["max_attempts"]
            acc["worst_case_tokens"] += m["worst_case_tokens"]
    assert per_model == {
        "openai/gpt-oss-120b": {"max_attempts": 270, "worst_case_tokens": 445890},
        "openai/gpt-oss-20b": {"max_attempts": 108, "worst_case_tokens": 137848},
    }


# --- the loader refuses anything but the registered schedule --------------------------------------


@pytest.fixture
def evaldir(tmp_path: Path) -> Path:
    shutil.copyfile(EVAL_ROOT / SCHEDULE_FILE, tmp_path / SCHEDULE_FILE)
    return tmp_path


def _with(evaldir: Path, doc: dict[str, Any] | bytes) -> dict[str, Any]:
    raw = doc if isinstance(doc, bytes) else yaml.safe_dump(doc, sort_keys=False).encode()
    (evaldir / SCHEDULE_FILE).write_bytes(raw)
    prereg = copy.deepcopy(PREREG)
    prereg["execution_schedule"]["sha256"] = hashlib.sha256(raw).hexdigest()
    return prereg


def _doc() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((EVAL_ROOT / SCHEDULE_FILE).read_text(encoding="utf-8"))
    return loaded


def test_an_edited_schedule_is_refused(evaldir: Path) -> None:
    path = evaldir / SCHEDULE_FILE
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed since it was pre-registered"):
        load_execution_schedule(V5, PREREG, evaldir)


def test_a_faithful_round_trip_is_accepted(evaldir: Path) -> None:
    loaded = load_execution_schedule(V5, _with(evaldir, _doc()), evaldir)
    assert loaded is not None and loaded["days"] == DAYS


def _moved(cid: str, to: int) -> Any:
    def mutate(doc: dict[str, Any]) -> None:
        for ids in doc["days"].values():
            if cid in ids:
                ids.remove(cid)
        doc["days"][to].append(cid)
        order = {c.id: i for i, c in enumerate(V5.cases)}
        doc["days"][to].sort(key=order.get)

    return mutate


BAD_SCHEDULES: dict[str, tuple[Any, str]] = {
    "case on two days": (lambda d: d["days"][2].insert(0, "S05"), r"duplicates \['S05'\]"),
    "missing case": (lambda d: d["days"][1].remove("T17"), r"missing \['T17'\]"),
    "unregistered case": (lambda d: d["days"][4].append("X99"), r"unregistered \['X99'\]"),
    "day gap": (lambda d: d["days"].update({5: d["days"].pop(4)}), r"numbered 1\.\.4"),
    "extra day": (lambda d: d["days"].update({5: []}), r"numbered 1\.\.4"),
    "wrong dataset hash": (lambda d: d.update(dataset_sha256="0" * 64), "different dataset"),
    "wrong dataset": (lambda d: d.update(dataset="routewise_bench_v4"), "different dataset"),
    "out of dataset order": (lambda d: d["days"][1].reverse(), "dataset order"),
}


@pytest.mark.parametrize("name", sorted(BAD_SCHEDULES))
def test_an_inconsistent_schedule_is_refused(evaldir: Path, name: str) -> None:
    mutate, message = BAD_SCHEDULES[name]
    doc = _doc()
    mutate(doc)
    with pytest.raises(ValueError, match=message):
        load_execution_schedule(V5, _with(evaldir, doc), evaldir)


def test_moving_a_case_to_another_day_needs_a_new_registration(evaldir: Path) -> None:
    doc = _doc()
    _moved("S05", 4)(doc)
    reloaded = load_execution_schedule(V5, _with(evaldir, doc), evaldir)
    assert reloaded is not None and reloaded["days"] != DAYS  # valid shape, but...
    with pytest.raises(ValueError, match="changed since it was pre-registered"):
        load_execution_schedule(V5, PREREG, evaldir)  # ...not the registered bytes


def test_a_duplicate_day_key_is_refused(evaldir: Path) -> None:
    text = (evaldir / SCHEDULE_FILE).read_text(encoding="utf-8")
    raw = text.replace("\n  2:\n", "\n  1:\n", 1).encode()
    with pytest.raises(ValueError, match="duplicate key 1"):
        load_execution_schedule(V5, _with(evaldir, raw), evaldir)


def test_day_cases_keep_their_dataset_index() -> None:
    assert SCHEDULE is not None
    order = {c.id: i for i, c in enumerate(V5.cases)}
    for day, ids in DAYS.items():
        pairs = schedule_day_cases(V5, SCHEDULE, day)
        assert [c.id for _, c in pairs] == ids and [i for i, _ in pairs] == [order[c] for c in ids]
    with pytest.raises(ValueError, match="schedule day 5 is not registered"):
        schedule_day_cases(V5, SCHEDULE, 5)


# --- chain and manifest ---------------------------------------------------------------------------


def test_v5_2_3_chain_pins_the_schedule() -> None:
    rev = yaml.safe_load((EVAL_ROOT / f"{REVISION}.revision.yaml").read_text(encoding="utf-8"))
    sched_sha = _sha(EVAL_ROOT / SCHEDULE_FILE)
    assert rev["execution_schedule"] == {"file": SCHEDULE_FILE, "sha256": sched_sha, "days": 4}
    assert PREREG["execution_schedule"] == rev["execution_schedule"]
    assert rev["amends_revision"]["sha256"] == PRESERVED["routewise_bench_v5.2.2.revision.yaml"]
    assert rev["preregistration"]["sha256"] == PREREG_SHA
    for key in ("scoring_amendment", "dataset_metadata", "review_attestation"):
        assert rev[key]["sha256"] == PREREG[key]["sha256"]
    manifest_file = EVAL_ROOT / PREREG["experiment_manifest"]["file"]
    assert _sha(manifest_file) == PREREG["experiment_manifest"]["sha256"]
    pinned = manifest_mod.load_manifest(manifest_file)[0]["pinned"]
    assert pinned["files"]["evidence/execution_schedule"]["sha256"] == sched_sha
    assert pinned["execution"]["attempt_quota"] == {"groq": GROQ_QUOTA_V5_2}  # guard unchanged


def test_the_review_gate_and_scoring_are_carried_over_unchanged() -> None:
    old = yaml.safe_load(
        (EVAL_ROOT / "preregistration_routewise_bench_v5.2.2.yaml").read_text(encoding="utf-8")
    )
    for key in ("scoring_amendment", "dataset_metadata", "review_attestation", "quality_rule"):
        assert PREREG[key] == old[key], key
    for key in ("cost_rule", "statistics", "primary_metric", "baseline_floor", "strategies"):
        assert PREREG[key] == old[key], key
    reviewed, _ = apply_review_attestation(V5, PREREG)
    assert reviewed.fully_reviewed


def test_v5_2_3_manifest_matches_the_intended_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    assert manifest_mod.check_manifest(PREREG, _settings(), _groq(), STRATEGIES, run_params=PACING)


# --- CLI and runner enforce one registered day per run --------------------------------------------


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


def _budget(remaining: int, ledger: Path) -> list[str]:
    return [
        "--remaining-daily-tokens",
        str(remaining),
        "--daily-budget-source",
        "test",
        "--daily-budget-verified-at",
        datetime.now(UTC).isoformat(),
        "--ledger",
        str(ledger),
    ]


def test_eval_validate_preflights_every_day_and_fails_closed_without_a_budget(
    intended_cli: None, capsys: Any
) -> None:
    assert _main(*VALIDATE) == 1
    out = capsys.readouterr().out
    assert f"execution schedule {SCHEDULE_FILE} sha256" in out
    assert "day 1: 10 cases, day 2: 12 cases, day 3: 11 cases, day 4: 12 cases" in out
    assert "experiment_manifest_routewise_bench_v5.2.3.yaml: matches" in out
    for day, tokens in DAY_TOKENS.items():
        assert f"scheduled day {day} ({len(DAYS[day])} cases):" in out
        assert f"total conservative reservation: {tokens} tokens" in out
    assert out.count("preflight: FAILED (fail closed)") == 4
    assert "pass --schedule-day N" in out


def test_all_four_days_pass_with_a_full_day_of_quota(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    assert _main(*VALIDATE, *_budget(TPD, tmp_path / "ledger.json")) == 0
    assert capsys.readouterr().out.count("preflight: OK") == 4


def test_a_day_needing_more_than_the_supplied_budget_fails_closed(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    ledger = tmp_path / "ledger.json"
    assert _main(*VALIDATE, "--schedule-day", "4", *_budget(167285, ledger)) == 0
    assert "preflight: OK" in capsys.readouterr().out
    assert _main(*VALIDATE, "--schedule-day", "4", *_budget(167284, ledger)) == 1
    assert "exceeds the usable daily budget" in capsys.readouterr().out


EVAL_RUN = ["eval-run", "--dataset", "routewise_bench_v5", "--label", "t", "--delay-s", "6"]


def test_eval_run_needs_a_scheduled_day(intended_cli: None, capsys: Any) -> None:
    assert _main(*EVAL_RUN, "--revision", REVISION) == 2
    assert "4-day execution schedule is registered: pass the day" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--schedule-day", "5"], "schedule day 5 is not registered"),
        (["--schedule-day", "1", "--limit", "3"], "--limit can't be combined"),
        (["--schedule-day", "1"], "quota preflight failed"),  # no budget: fails closed
    ],
)
def test_eval_run_refuses_before_any_network_call(
    intended_cli: None, capsys: Any, extra: list[str], message: str
) -> None:
    assert _main(*EVAL_RUN, "--revision", REVISION, *extra) == 2
    assert message in capsys.readouterr().err


def test_a_revision_without_a_schedule_rejects_a_schedule_day(
    intended_cli: None, capsys: Any
) -> None:
    assert _main(*EVAL_RUN, "--revision", "routewise_bench_v5.2.2", "--schedule-day", "1") == 2
    assert "registers no execution schedule" in capsys.readouterr().err


@pytest.mark.parametrize(
    "revision", ["routewise_bench_v5.2.2", "routewise_bench_v5.2.1", "routewise_bench_v5.2"]
)
def test_historical_revisions_are_refused(intended_cli: None, capsys: Any, revision: str) -> None:
    assert _main(*EVAL_RUN, "--revision", revision) == 2
    assert "configuration differs from experiment_manifest_" in capsys.readouterr().err


async def _run(**kwargs: Any) -> Any:
    return await runner_mod.run_benchmark(
        settings=_settings(),
        db=None,  # type: ignore[arg-type]  # never reached
        providers=_groq(),
        dataset=V5,
        strategies=STRATEGIES,
        label="t",
        revision=REVISION,
        delay_s=6.0,
        **kwargs,
    )


async def test_the_runner_needs_a_registered_day() -> None:
    with pytest.raises(ValueError, match="pass the day"):
        await _run()
    with pytest.raises(ValueError, match="limit_cases can't be combined"):
        await _run(schedule_day=1, limit_cases=3)


async def test_the_runner_preflights_only_the_scheduled_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    planned: list[list[str]] = []
    real = preflight.plan

    def spy(dataset: Any, *args: Any) -> Any:
        planned.append([c.id for c in dataset.cases])
        return real(dataset, *args)

    monkeypatch.setattr(preflight, "plan", spy)
    with pytest.raises(ValueError, match="quota preflight failed"):  # no budget: before any call
        await _run(schedule_day=3)
    assert planned == [DAYS[3]]


# --- pooling the days (synthetic reports) ---------------------------------------------------------


def _outcome(case: Any, strategy: str, *, passed: bool = True) -> Any:
    from app.evaluation.runner import CaseOutcome

    model = "openai/gpt-oss-120b" if strategy == "baseline_premium" else "openai/gpt-oss-20b"
    tier = "premium" if strategy == "baseline_premium" else "small"
    return CaseOutcome(
        case_id=case.id,
        difficulty=case.difficulty,
        category=case.category,
        strategy=strategy,
        passed=passed,
        score=1.0 if passed else 0.0,
        needs_human_review=False,
        error_code=None,
        provider="groq",
        model=model,
        answer_model=model,
        tier=tier,
        latency_ms=100,
        estimated_list_cost_usd="0.00010000",
        list_cost_status="estimated",
        attempts=[{"attempt": 1, "provider": "groq", "model": model, "tier": tier}],
    )


def _write_day(
    reports: Path,
    day: int,
    utc_date: str,
    *,
    incomplete: bool = False,
    drop: int = 0,
    review: Any = "real",
) -> Path:
    from app.evaluation.report import write_report
    from app.evaluation.runner import BenchmarkResult

    by_id = {c.id: c for c in V5.cases}
    reviewed, attestation = apply_review_attestation(V5, PREREG)
    outcomes = [_outcome(by_id[c], s) for c in DAYS[day] for s in STRATEGIES]
    result = BenchmarkResult(
        label=f"day{day}",
        simulated=False,
        dataset=V5.name,
        dataset_sha256=V5.sha256,
        dataset_fully_reviewed=reviewed.fully_reviewed,
        preregistration=PREREG,
        preregistration_sha256=PREREG_SHA,
        started_at=f"{utc_date}T08:00:00+00:00",
        finished_at=f"{utc_date}T09:00:00+00:00",
        config_snapshot={
            "manifest": {
                "expected_models": ["groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b"]
            },
            "execution_revision": REVISION,
            "scoring_amendment": AMENDMENT,
            "review_attestation": attestation
            if review == "real"
            else {**(attestation or {}), "sha256": "0" * 64},
            "execution_schedule": {
                "file": SCHEDULE_FILE,
                "sha256": PREREG["execution_schedule"]["sha256"],
                "day": day,
                "days": 4,
                "case_ids": DAYS[day],
                "utc_date": utc_date,
            },
        },
        run_ids={s: f"{day}-{s}" for s in STRATEGIES},
        outcomes=outcomes[: len(outcomes) - drop],
        incomplete=incomplete,
    )
    out, _ = write_report(result, reports)
    return out


DATES = {1: "2026-11-10", 2: "2026-11-11", 3: "2026-11-12", 4: "2026-11-13"}


def _combine(tmp_path: Path, dirs: list[Path]) -> tuple[Path, dict[str, Any]]:
    from app.evaluation.report import combine_scheduled_reports

    return combine_scheduled_reports(
        dirs,
        dataset=V5,
        prereg=PREREG,
        prereg_sha=PREREG_SHA,
        revision=REVISION,
        label="combined",
        directory=tmp_path / "combined",
    )


def test_four_complete_days_pool_into_one_paired_analysis(tmp_path: Path) -> None:
    dirs = [_write_day(tmp_path, d, DATES[d]) for d in DAYS]
    out, summary = _combine(tmp_path, dirs)
    assert summary["incomplete"] is False and summary["schedule_violations"] == []
    assert all(m["cases"] == 45 for m in summary["metrics"].values())
    for comparison in summary["comparisons_vs_baseline"].values():
        assert comparison["paired_cases"] == 45  # every case paired, across all four days
    assert [d["utc_date"] for d in summary["schedule_days"]] == list(DATES.values())
    assert summary["execution_schedule"]["utc_dates"] == list(DATES.values())
    assert (
        summary["review_attestation"]["sha256"]
        == PRESERVED["reviews/routewise_bench_v5.2.1_HUMAN_REVIEW_ATTESTATION.yaml"]
    )
    assert "dataset not fully human-reviewed" not in summary["publishable_reasons"]
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert len(rows) == 135 and {r["schedule_day"] for r in rows} == {1, 2, 3, 4}
    assert all(
        r["schedule_day"] == next(d for d, ids in DAYS.items() if r["case_id"] in ids) for r in rows
    )
    md = (out / "summary.md").read_text(encoding="utf-8")
    assert "## Scheduled days" in md and "2026-11-13" in md
    assert "**Disclosure:** T17: translator-assisted owner review" in md


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("missing day", r"missing scheduled days \[4\]"),
        ("duplicate day", "scheduled day 2 supplied twice"),
        ("same date", "distinct UTC dates in day order"),
        ("reversed dates", "distinct UTC dates in day order"),
        ("different attestation", "scheduled days differ in review_attestation"),
    ],
)
def test_combining_refuses_anything_but_one_report_per_day(
    tmp_path: Path, setup: str, message: str
) -> None:
    dates = dict(DATES)
    if setup == "same date":
        dates[3] = dates[2]
    if setup == "reversed dates":
        dates[1], dates[2] = dates[2], dates[1]
    dirs = [_write_day(tmp_path / str(d), d, dates[d]) for d in DAYS]
    if setup == "missing day":
        dirs = dirs[:3]
    if setup == "duplicate day":
        dirs.append(_write_day(tmp_path / "again", 2, "2026-11-14"))
    if setup == "different attestation":
        dirs[3] = _write_day(tmp_path / "other", 4, DATES[4], review="other")
    with pytest.raises(ValueError, match=message):
        _combine(tmp_path, dirs)


def test_combining_refuses_a_report_from_another_registration(tmp_path: Path) -> None:
    dirs = [_write_day(tmp_path, d, DATES[d]) for d in DAYS]
    summary_file = dirs[0] / "summary.json"
    data = json.loads(summary_file.read_text(encoding="utf-8"))
    summary_file.write_text(json.dumps({**data, "preregistration_sha256": "0" * 64}))
    with pytest.raises(ValueError, match="not run under this pre-registration"):
        _combine(tmp_path, dirs)


def test_combining_refuses_a_day_with_other_cases(tmp_path: Path) -> None:
    dirs = [_write_day(tmp_path, d, DATES[d]) for d in DAYS]
    summary_file = dirs[1] / "summary.json"
    data = json.loads(summary_file.read_text(encoding="utf-8"))
    data["execution_schedule"]["case_ids"] = DAYS[2][:-1]
    summary_file.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cases differ from scheduled day 2"):
        _combine(tmp_path, dirs)


@pytest.mark.parametrize(
    ("kind", "violation"),
    [
        ("incomplete day", None),
        ("missing results", "day 3"),
        ("span too long", "days span 21 days"),
    ],
)
def test_a_flawed_day_makes_the_whole_comparison_incomplete(
    tmp_path: Path, kind: str, violation: str | None
) -> None:
    dates = dict(DATES)
    if kind == "span too long":
        dates[4] = "2026-12-01"
    dirs = [
        _write_day(
            tmp_path,
            d,
            dates[d],
            incomplete=kind == "incomplete day" and d == 2,
            drop=1 if kind == "missing results" and d == 3 else 0,
        )
        for d in DAYS
    ]
    _, summary = _combine(tmp_path, dirs)
    assert summary["incomplete"] is True and summary["publishable"] is False
    assert "run incomplete" in summary["publishable_reasons"]
    if violation:
        assert any(violation in v for v in summary["schedule_violations"])
    assert sum(m["cases"] for m in summary["metrics"].values()) >= 134  # nothing is dropped


def test_eval_combine_cli_pools_the_days(tmp_path: Path, capsys: Any) -> None:
    dirs = [_write_day(tmp_path, d, DATES[d]) for d in DAYS]
    from app.evaluation import dataset as dataset_mod

    original = dataset_mod.REPORTS_DIR
    try:
        dataset_mod.REPORTS_DIR = tmp_path
        code = _main(
            "eval-combine",
            "--dataset",
            "routewise_bench_v5",
            "--revision",
            REVISION,
            "--label",
            "pooled",
            "--reports",
            *[str(d) for d in dirs],
        )
    finally:
        dataset_mod.REPORTS_DIR = original
    assert code == 0
    assert "combined report:" in capsys.readouterr().out
    assert (tmp_path / "pooled" / "summary.json").exists()
