"""routewise_bench_v4: dataset, strict final answers, baseline guarantee, reporting, manifest, CLI.

Unchanged cases reuse v3's reference and adversarial answers. Each v4 correction has positive,
negative and adversarial answers, plus v3-vs-v4 evidence for every false pass it fixes.
No model or provider is called: the CLI test stops before any network access, and the runner
test uses the mock provider on a scratch database.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.evaluation import manifest as manifest_mod
from app.evaluation.dataset import (
    EVAL_ROOT,
    load_dataset,
    load_preregistration,
    preregistration_path,
)
from app.evaluation.scorers import score
from app.providers.catalog import load_catalog
from app.providers.groq import GroqProvider
from app.routing.config import load_policy
from app.routing.engine import RoutingRequest, route
from tests.evaluation.test_dataset_v3 import ADVERSARIAL as V3_ADVERSARIAL
from tests.evaluation.test_dataset_v3 import CARRIED as V3_CARRIED
from tests.evaluation.test_dataset_v3 import REFERENCE as V3_REFERENCE

V3 = load_dataset("routewise_bench_v3")
V4 = load_dataset("routewise_bench_v4")
CASES = {c.id: c for c in V4.cases}
V3_CASES = {c.id: c for c in V3.cases}
CHANGED = ["T03", "T04", "T10", "T17", "C01", "C03", "C08", "C09"]
SCORING_CHANGED = ["T10", "T17", "C01", "C03", "C08", "C09"]  # T03/T04: prompt only

REFERENCE: dict[str, tuple[str, str]] = {
    **{cid: pair for cid, pair in V3_REFERENCE.items() if cid not in SCORING_CHANGED},
    "C01": (
        "A is 90 km ahead at 09:00; closing at 30 km/h takes 3 hours.\nANSWER: 12:00",
        "ANSWER: 11:00",
    ),
    "T10": ("Line 7 counts every number, not just positives.\nANSWER: 7", "ANSWER: 6"),
    "C03": ("2 + 3 + 3 + 3 = 11\nANSWER: 11", "ANSWER: 8"),
    "C08": ("2+3+5+7+11+13+17+19+23+29+31+37+41+43+47\nANSWER: 328", "ANSWER: 329"),
    "C09": ("1000 x 1.05^3 = 1157.625, rounded half up.\nANSWER: 1157.63", "ANSWER: 1157.62"),
    "T17": ("Only B keeps the verb, the time and the noun.\nANSWER: B", "ANSWER: D"),
}

ADVERSARIAL: list[tuple[str, str, bool, str]] = [
    # C01 — exact final-answer line
    ("C01", "ANSWER: 12:00.", True, "trailing full stop"),
    ("C01", "**ANSWER:** 12:00", True, "markdown"),
    ("C01", "ANSWER: Not 12:00", False, "negation on the ANSWER line"),
    (
        "C01",
        "ANSWER: The train does not catch A at 12:00",
        False,
        "contradicting prose on the ANSWER line",
    ),
    ("C01", "Not 12:00", False, "negation, no ANSWER line (v3 false pass)"),
    (
        "C01",
        "The train does not catch A at 12:00",
        False,
        "contradicting prose, no ANSWER line (v3 false pass)",
    ),
    ("C01", "ANSWER: 12:00 or 13:00", False, "two answers"),
    ("C01", "ANSWER: noon", False, "not HH:MM"),
    ("C01", "ANSWER: 12:00 noon", False, "extra words"),
    ("C01", "12:00", False, "no ANSWER line"),
    # T10 — strict number
    ("T10", "**ANSWER: 7**", True, "markdown"),
    ("T10", "ANSWER: 7.", True, "trailing full stop"),
    ("T10", "ANSWER: 7 (indentation)", False, "trailing note (v3 false pass)"),
    ("T10", "ANSWER: 7 or 6", False, "contradictory second number (v3 false pass)"),
    ("T10", "ANSWER: line 7", False, "prose before the number"),
    ("T10", "ANSWER: seven", False, "word, not a number"),
    ("T10", "The bug is on line 7.", False, "no ANSWER line"),
    # C03 — strict number
    ("C03", "ANSWER: 11", True, "plain"),
    ("C03", "ANSWER: 11 (sum of gaps)", False, "trailing note (v3 false pass)"),
    ("C03", "ANSWER: 11, not 12", False, "contradictory second number (v3 false pass)"),
    ("C03", "ANSWER: 12", False, "wrong"),
    # C08 — strict number
    ("C08", "ANSWER: 328", True, "plain"),
    (
        "C08",
        "ANSWER: 328 (sum of 15 primes)",
        False,
        "trailing note with a second number (v3 false pass)",
    ),
    ("C08", "ANSWER: 328 or 329", False, "two answers (v3 false pass)"),
    ("C08", "ANSWER: 3,28", False, "invalid thousands grouping"),
    ("C08", "ANSWER: about 328", False, "hedging prose"),
    # C09 — strict number
    ("C09", "ANSWER: $1,157.63", True, "currency and valid grouping"),
    ("C09", "ANSWER: 1157.63.", True, "trailing full stop"),
    ("C09", "ANSWER: 1157.63 (rounded half up)", False, "trailing note (v3 false pass)"),
    ("C09", "ANSWER: 1157.63 USD", False, "unit word"),
    ("C09", "ANSWER: 1157.63 or 1157.62", False, "two answers (v3 false pass)"),
    ("C09", "ANSWER: 1157.62", False, "round-half-even"),
    ("C09", "ANSWER: 1157.625", False, "unrounded"),
    ("C09", "ANSWER: 115,7.63", False, "invalid thousands grouping"),
    # T17 — four-option multiple choice
    ("T17", "ANSWER: (B)", True, "parenthesised"),
    ("T17", "ANSWER: b.", True, "lowercase with full stop"),
    ("T17", "ANSWER: B)", True, "as printed in the options"),
    ("T17", "ANSWER: A", False, "closes"),
    ("T17", "ANSWER: C", False, "ten"),
    ("T17", "ANSWER: D", False, "bookshop (false friend)"),
    ("T17", "ANSWER: B or D", False, "two options"),
    ("T17", "ANSWER: Not B", False, "negated"),
    (
        "T17",
        "ANSWER: B) La biblioteca abre a las nueve en punto.",
        False,
        "letter followed by text",
    ),
    ("T17", "The answer is B.", False, "no ANSWER line"),
    # T03 / T04 — prompts changed; copying the placeholder example must not pass
    (
        "T03",
        next(line for line in CASES["T03"].prompt.splitlines() if line.startswith("{")),
        False,
        "placeholder example copied verbatim",
    ),
    (
        "T04",
        next(line for line in CASES["T04"].prompt.splitlines() if line.startswith("{")),
        False,
        "placeholder example copied verbatim",
    ),
]

# v3's adversarial answers stay valid wherever the scoring rule is unchanged.
CARRIED = [a for a in V3_ADVERSARIAL + V3_CARRIED if a[0] not in SCORING_CHANGED]


def test_earlier_versions_are_unchanged() -> None:
    assert V3.sha256 == "c0c58c306cd18671e70e40aeab7bbae8672428369bbbe2cbb140144bc61119c7"
    assert load_dataset("routewise_bench_v2").sha256 == (
        "614e14497b380539baed24ad87f3619e11107d2adc35230004b652dec6994550"
    )
    assert load_dataset("routewise_bench_v1").sha256.startswith("5b0107d18347")


def test_v4_size_balance_and_review_status() -> None:
    assert len(V4.cases) == 45
    assert Counter(c.difficulty for c in V4.cases) == {"simple": 15, "standard": 18, "complex": 12}
    assert V4.meta["status"] == "draft-pending-human-review"
    assert V4.meta["reviewed_by"] == {}
    assert V4.fully_reviewed is False
    assert V4.meta["code_execution"] is False and V4.code_execution_cases == []


def test_only_the_listed_cases_differ_from_v3() -> None:
    changed = [c.id for c in V4.cases if c.model_dump() != V3_CASES[c.id].model_dump()]
    assert changed == CHANGED
    assert V4.meta["changed_from_v3"] == CHANGED


def test_no_first_number_scoring_remains_on_final_answer_lines() -> None:
    for case in V4.cases:
        if case.scoring.get("final_answer") and case.scoring["method"] == "numeric":
            assert case.scoring.get("strict_number") is True, case.id
            assert not case.scoring.get("first_number"), case.id


def test_t03_t04_prompts_have_valid_json_examples_and_separate_permitted_values() -> None:
    for cid in ("T03", "T04"):
        prompt = CASES[cid].prompt
        example = next(line for line in prompt.splitlines() if line.startswith("{"))
        json.loads(example)
        assert "Permitted values:" in prompt and prompt.index(example) < prompt.index(
            "Permitted values:"
        )


def test_t17_is_four_option_multiple_choice_with_one_correct_answer() -> None:
    prompt = CASES["T17"].prompt
    options = [line for line in prompt.splitlines() if line[:3] in ("A) ", "B) ", "C) ", "D) ")]
    assert len(options) == 4 and len(set(options)) == 4
    passing = [
        letter for letter in "ABCD" if score(f"ANSWER: {letter}", CASES["T17"].scoring).passed
    ]
    assert passing == ["B"]
    assert "native" not in json.dumps(CASES["T17"].model_dump()).lower()  # no validation claimed


def test_every_case_has_a_reference_pair() -> None:
    assert set(REFERENCE) == set(CASES)


@pytest.mark.parametrize("case_id", sorted(REFERENCE))
def test_correct_answer_passes_and_wrong_answer_fails(case_id: str) -> None:
    good, bad = REFERENCE[case_id]
    spec = CASES[case_id].scoring
    assert score(good, spec).passed is True, (case_id, score(good, spec).details)
    assert score(bad, spec).passed is False, (case_id, score(bad, spec).details)


@pytest.mark.parametrize(("case_id", "answer", "must_pass", "why"), ADVERSARIAL + CARRIED)
def test_adversarial_answers(case_id: str, answer: str, must_pass: bool, why: str) -> None:
    result = score(answer, CASES[case_id].scoring)
    assert result.passed is must_pass, (case_id, why, result.details)


@pytest.mark.parametrize(
    ("case_id", "answer"),
    [
        ("C01", "Not 12:00"),
        ("C01", "The train does not catch A at 12:00"),
        ("T10", "ANSWER: 7 or 6"),
        ("C03", "ANSWER: 11, not 12"),
        ("C08", "ANSWER: 328 or 329"),
        ("C09", "ANSWER: 1157.63 or 1157.62"),
    ],
)
def test_v3_false_passes_are_fixed_in_v4(case_id: str, answer: str) -> None:
    assert score(answer, V3_CASES[case_id].scoring).passed is True  # v3 accepted it
    assert score(answer, CASES[case_id].scoring).passed is False


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        ("7", True),
        ("1,157.63", True),
        ("$1,157.63", True),
        ("-3", True),
        ("328.", True),
        ("3,28", False),
        ("1157.63 USD", False),
        ("7 or 6", False),
        ("line 7", False),
        ("", False),
        ("1.2.3", False),
        ("12,345,678", True),
        ("12,34", False),
    ],
)
def test_strict_number_format(value: str, ok: bool) -> None:
    spec = {
        "method": "numeric",
        "answer": float(value.strip("$.").replace(",", "")) if ok else 0,
        "tolerance": 0,
        "strict_number": True,
    }
    assert score(value, spec).passed is ok


# --- baseline: premium-only generation is guaranteed by construction ---------------------------


@pytest.mark.parametrize("providers", [frozenset({"groq"}), frozenset({"groq", "openrouter"})])
def test_baseline_routes_only_to_premium_models_for_every_case(providers: frozenset[str]) -> None:
    from app.core.config import BACKEND_ROOT
    from app.evaluation.runner import STRATEGIES

    class NoHealth:
        def exclusion(self, provider: str, model_id: str) -> None:
            return None

        def p95_ms(self, provider: str, model_id: str, min_samples: int) -> None:
            return None

    models = load_catalog(BACKEND_ROOT / "config" / "models.yaml").models
    policy = load_policy(BACKEND_ROOT / "config" / "routing_policy.yaml")
    overrides = STRATEGIES["baseline_premium"][1]
    assert overrides == {"preferred_tier": "premium"}
    from app.providers.base import ChatMessage

    for case in V4.cases:
        decision = route(
            RoutingRequest(
                messages=(ChatMessage(role="user", content=case.prompt),),
                task_type=case.task_type,
                max_output_tokens=case.max_output_tokens,
                response_format=case.response_format,
                **overrides,
            ),
            models=models,
            enabled_providers=providers,
            simulated_providers=frozenset({"mock"}),
            policy=policy,
            health=NoHealth(),
        )
        assert decision.required_tier == "premium", case.id
        assert decision.eligible and {c.tier for c in decision.eligible} == {"premium"}, case.id


# --- pre-registration and manifest ----------------------------------------------------------------


def _prereg() -> dict[str, Any]:
    prereg, _ = load_preregistration(preregistration_path("routewise_bench_v4"), dataset=V4)
    return prereg


def _intended(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "groq_enabled": True,
        "groq_api_key": "test-placeholder-key-0000000000000000",
        "groq_billing_plan": "free",
        "mock_provider_enabled": False,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def _groq() -> dict[str, Any]:
    return {"groq": GroqProvider(api_key="test-placeholder", charge_basis="free_tier")}


STRATEGIES_ALL = ["baseline_premium", "routewise", "routewise_tier_first"]
PACING = {"concurrency": 1, "delay_s": 6.0, "limit_cases": None, "allow_code_exec": False}


def test_v4_preregistration_chain() -> None:
    prereg, sha = load_preregistration(preregistration_path("routewise_bench_v4"), dataset=V4)
    assert prereg["dataset_sha256"] == V4.sha256 and V4.meta["preregistration_sha256"] == sha
    manifest, msha = manifest_mod.load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])
    assert msha == prereg["experiment_manifest"]["sha256"]
    assert manifest["schema"] == 2 and manifest["dataset_sha256"] == V4.sha256
    assert prereg["baseline_tier_guard"] == "premium_only"
    assert prereg["run_validity"]["provider_errors"] == "missing"
    assert prereg["cost_rule"]["requires_ci_supported_non_inferiority"] is True


def test_v4_manifest_matches_the_intended_configuration_except_superseded_code() -> None:
    """v5 changed execution code that v4 pinned (scorers, providers, runner, manifest, …). v4 is
    therefore correctly unrunnable on current code; everything except code-file hashes still
    matches v4's intended configuration and pacing."""
    prereg = _prereg()
    manifest, _ = manifest_mod.load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])
    actual = manifest_mod.build_manifest(
        _intended(), _groq(), STRATEGIES_ALL, schema=2, run_params=PACING
    )
    differences = manifest_mod.diff(manifest["pinned"], actual)
    assert differences, "v4 should no longer match: its pinned code was superseded by v5"
    assert all(d.startswith("files.") and d.endswith(".sha256") for d in differences), differences
    with pytest.raises(ValueError, match="configuration differs"):
        manifest_mod.check_manifest(prereg, _intended(), _groq(), STRATEGIES_ALL, run_params=PACING)
    pinned = manifest["pinned"]
    assert pinned["execution"]["pacing"] == PACING
    required = {
        "routing_engine",
        "routing_features",
        "routing_config",
        "provider_interface",
        "provider_http_and_usage_extraction",
        "provider_adapter_groq",
        "executor_retries_fallbacks",
        "gateway_pipeline",
        "cost_accounting",
        "scorers",
        "report",
        "runner",
        "manifest",
        "routing_policy",
        "model_registry",
        "api_schemas",
        "settings",
    }
    assert required <= set(pinned["files"])


@pytest.mark.parametrize(
    ("change", "where"),
    [
        ({"delay_s": 2.0}, "execution.pacing.delay_s"),
        ({"delay_s": 0.0}, "execution.pacing.delay_s"),
        ({"limit_cases": 5}, "execution.pacing.limit_cases"),
        ({"concurrency": 4}, "execution.pacing.concurrency"),
        ({"allow_code_exec": True}, "execution.pacing.allow_code_exec"),
    ],
)
def test_manifest_refuses_different_pacing(change: dict[str, Any], where: str) -> None:
    with pytest.raises(ValueError, match="configuration differs") as info:
        manifest_mod.check_manifest(
            _prereg(), _intended(), _groq(), STRATEGIES_ALL, run_params={**PACING, **change}
        )
    assert where in str(info.value)


@pytest.mark.parametrize(
    "component",
    [
        "routing_engine",
        "provider_interface",
        "provider_http_and_usage_extraction",
        "executor_retries_fallbacks",
        "cost_accounting",
        "gateway_pipeline",
        "scorers",
    ],
)
def test_manifest_detects_changed_execution_code(
    component: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = manifest_mod.CODE_FILES_V2[component]
    edited = tmp_path / original.name
    edited.write_text(original.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    monkeypatch.setitem(manifest_mod.CODE_FILES_V2, component, edited)
    with pytest.raises(ValueError, match=rf"files\.{component}"):
        manifest_mod.check_manifest(
            _prereg(), _intended(), _groq(), STRATEGIES_ALL, run_params=PACING
        )


def test_cli_refuses_mismatched_pacing_before_any_network_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app import cli
    from app.providers import registry

    async def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("refresh_catalogs must not run when the manifest doesn't match")

    monkeypatch.setattr(cli, "get_settings", lambda: _intended())
    monkeypatch.setattr(registry, "build_providers", lambda settings: _groq())
    monkeypatch.setattr(registry, "refresh_catalogs", no_network)
    code = cli.main(
        ["eval-run", "--dataset", "routewise_bench_v4", "--label", "pytest", "--delay-s", "2"]
    )
    assert code == 2
    assert "execution.pacing.delay_s" in capsys.readouterr().err


# --- reporting: availability, conditional pass rate, attempts, baseline guard -------------------


def _outcome(
    strategy: str, i: int, *, passed: bool, error: bool = False, tier: str = "premium"
) -> Any:
    from app.evaluation.runner import CaseOutcome

    model = "openai/gpt-oss-120b" if tier == "premium" else "openai/gpt-oss-20b"
    return CaseOutcome(
        case_id=f"X{i:02d}",
        difficulty="simple",
        category="c",
        strategy=strategy,
        passed=False if error else passed,
        score=None,
        needs_human_review=False,
        error_code="ALL_PROVIDERS_FAILED" if error else None,
        provider=None if error else "groq",
        model=None if error else model,
        answer_model=None if error else model,
        latency_ms=None if error else 100,
        estimated_list_cost_usd=None if error else "0.00010000",
        list_cost_status="unavailable" if error else "estimated",
        attempts=[
            {
                "attempt": 1,
                "provider": "groq",
                "model": model,
                "tier": tier,
                "status": "timeout" if error else "succeeded",
            }
        ],
    )


def _summary(base: list[Any], cand: list[Any]) -> dict[str, Any]:
    from app.evaluation.report import build_summary
    from app.evaluation.runner import BenchmarkResult

    prereg, sha = load_preregistration(preregistration_path("routewise_bench_v4"), dataset=V4)
    return build_summary(
        BenchmarkResult(
            label="synthetic",
            simulated=False,
            dataset=V4.name,
            dataset_sha256=V4.sha256,
            dataset_fully_reviewed=True,
            preregistration=prereg,
            preregistration_sha256=sha,
            started_at="",
            finished_at="",
            config_snapshot={
                "manifest": {
                    "expected_models": ["groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b"]
                }
            },
            run_ids={},
            outcomes=base + cand,
        )
    )


def test_pass_rate_is_labelled_conditional_and_availability_is_separate() -> None:
    base = [_outcome("baseline_premium", i, passed=i < 40, error=i == 44) for i in range(45)]
    cand = [_outcome("routewise", i, passed=i < 40, tier="small") for i in range(45)]
    m = _summary(base, cand)["metrics"]["baseline_premium"]
    assert m["pass_rate_basis"] == "conditional_on_answer_returned"
    assert (m["answered"], m["cases"], m["answer_rate"]) == (44, 45, 0.9778)
    assert m["pass_rate"] == round(40 / 44, 4)  # conditional on an answer
    assert m["pass_rate_unconditional"] == round(40 / 45, 4)
    assert m["answer_model_distribution"] == {"groq/openai/gpt-oss-120b": 44}
    assert m["attempt_model_distribution"] == {"groq/openai/gpt-oss-120b": 45}  # incl. the failure
    assert m["attempt_status_distribution"] == {"succeeded": 44, "timeout": 1}


def test_baseline_attempt_outside_premium_invalidates_the_run() -> None:
    base = [_outcome("baseline_premium", i, passed=True) for i in range(45)]
    base[3] = _outcome("baseline_premium", 3, passed=True, tier="small")
    cand = [_outcome("routewise", i, passed=True, tier="small") for i in range(45)]
    summary = _summary(base, cand)
    assert summary["publishable"] is False
    assert any("outside the premium tier" in r for r in summary["publishable_reasons"])


async def test_runner_records_answer_model_and_every_attempt(
    database_url: str, tmp_path: Path
) -> None:
    """Mock provider on a scratch DB (v1 dataset: no manifest), with one forced failure."""
    from app.db.session import Database
    from app.evaluation.runner import run_benchmark
    from app.providers.base import ProviderErrorKind
    from app.providers.mock import MockProvider
    from tests.conftest import make_settings

    provider = MockProvider()
    provider.script("mock-premium", [MockProvider.error(ProviderErrorKind.BAD_REQUEST)])
    db = Database(database_url)
    try:
        result = await run_benchmark(
            settings=make_settings(database_url),
            db=db,
            providers={"mock": provider},
            dataset=load_dataset("routewise_bench_v1"),
            strategies=["baseline_premium", "routewise"],
            label="pytest-attempts",
            limit_cases=3,
        )
    finally:
        await db.dispose()
    for o in result.outcomes:
        assert o.attempts, o.case_id
        assert all({"provider", "model", "tier", "status"} <= set(a) for a in o.attempts)
        if o.error_code is None:
            assert o.answer_model == o.model  # mock reports the requested model
            assert o.attempts[-1]["status"] == "succeeded"
    failed = [o for o in result.outcomes if o.error_code]
    assert failed and all(a["status"] != "succeeded" for o in failed for a in o.attempts)
    baseline = [o for o in result.outcomes if o.strategy == "baseline_premium"]
    assert {a["tier"] for o in baseline for a in o.attempts} == {"premium"}
