"""routewise_bench_v3: integrity, pre-registration, manifest, report rules, and scoring regressions.

Unchanged cases reuse v2's reference and adversarial answers. Each of the seven v3 corrections
has positive, negative and adversarial answers, including the v2 false pass it fixes. No model or
provider is called; the manifest tests build adapter objects without any network access.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
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
from app.evaluation.scorers import count_sentences, score
from app.providers.groq import GroqProvider
from tests.evaluation.test_dataset_v2 import ADVERSARIAL as V2_ADVERSARIAL
from tests.evaluation.test_dataset_v2 import REFERENCE as V2_REFERENCE

V2 = load_dataset("routewise_bench_v2")
V3 = load_dataset("routewise_bench_v3")
CASES = {c.id: c for c in V3.cases}
V2_CASES = {c.id: c for c in V2.cases}
CORRECTED = ["T03", "T04", "T07", "T12", "T17", "C07", "C09"]

T03_OK = '{"start_time_utc": "09:12", "day": "Monday", "affected_feature": "checkout", "duration_minutes": 45, "root_cause": "disk_full", "alert_threshold_percent": 80}'
T04_OK = '{"decisions": [{"topic": "launch_date", "owner": null, "date": "2026-06-02"}, {"topic": "press_release", "owner": "marketing", "date": null}, {"topic": "feature_freeze", "owner": "engineering", "date": "2026-05-20"}]}'
C07_OK = '{"customer": "Omar Haddad", "items": [{"sku": "SKU-118", "quantity": 5}, {"sku": "SKU-204", "quantity": 5}], "total_units": 10}'

REFERENCE: dict[str, tuple[str, str]] = {
    **{cid: pair for cid, pair in V2_REFERENCE.items() if cid not in CORRECTED},
    "T03": (T03_OK, T03_OK.replace('"duration_minutes": 45', '"duration_minutes": 54')),
    "T04": (T04_OK, T04_OK.replace('"owner": "marketing"', '"owner": "engineering"')),
    "T07": ("Please send me the report when you have a moment.", "Send me the report now."),
    "T12": ("Five of the 36 outcomes sum to 8.\nANSWER: 5/36", "ANSWER: 1/6"),
    "T17": ("La biblioteca abre a las nueve.", "La biblioteca cierra a las nueve."),
    "C07": (
        C07_OK,
        C07_OK.replace('"quantity": 5}, {"sku": "SKU-204"', '"quantity": 2}, {"sku": "SKU-204"'),
    ),
    "C09": ("1000 x 1.05^3 = 1157.625, rounded half up.\nANSWER: 1157.63", "ANSWER: 1157.62"),
}

# (case, answer, must_pass, why) for the seven corrections.
ADVERSARIAL: list[tuple[str, str, bool, str]] = [
    # T03 — fact extraction replaces keyword matching
    ("T03", T03_OK.replace('"Monday"', '"monday"'), True, "day in lowercase"),
    ("T03", T03_OK.replace("80}", '80, "notes": "storage expanded"}'), True, "extra key ignored"),
    (
        "T03",
        T03_OK.replace('"alert_threshold_percent": 80', '"alert_threshold_percent": 80.0'),
        True,
        "80.0 equals 80",
    ),
    ("T03", "```json\n" + T03_OK + "\n```", True, "fenced JSON"),
    (
        "T03",
        "The disk filled up, checkout failed for 45 minutes, and an alert was added.",
        False,
        "v2 keyword answer (v2 false-pass risk) is not JSON",
    ),
    (
        "T03",
        "Disk not full; 45 people; no alert.",
        False,
        "negated keywords (would pass v2 keyword matching)",
    ),
    (
        "T03",
        T03_OK.replace('"duration_minutes": 45', '"duration_minutes": "45"'),
        False,
        "duration as a string",
    ),
    (
        "T03",
        T03_OK.replace('"disk_full"', '"disk"'),
        False,
        "root cause not one of the allowed values",
    ),
    ("T03", T03_OK.replace('"checkout"', '"checkout failures"'), False, "feature is not one word"),
    ("T03", T03_OK.replace('"09:12"', '"9:12"'), False, "time not HH:MM"),
    (
        "T03",
        T03_OK.replace('"alert_threshold_percent": 80', '"alert_threshold_percent": 45'),
        False,
        "swapped numbers",
    ),
    # T04 — decision ↔ owner relationship enforced
    (
        "T04",
        T04_OK.replace('"marketing"', '"Marketing"').replace('"press_release"', '"Press_Release"'),
        True,
        "case-insensitive owner and topic",
    ),
    (
        "T04",
        T04_OK.replace('"owner": "marketing"', '"owner": "engineering"').replace(
            '"owner": "engineering", "date": "2026-05-20"',
            '"owner": "marketing", "date": "2026-05-20"',
        ),
        False,
        "owners swapped (v2 keyword false pass)",
    ),
    (
        "T04",
        T04_OK.replace("]}", ', {"topic": "pricing", "owner": null, "date": null}]}'),
        False,
        "undecided pricing included",
    ),
    (
        "T04",
        T04_OK.replace("]}", ', {"topic": "press_release", "owner": "marketing", "date": null}]}'),
        False,
        "duplicate decision",
    ),
    (
        "T04",
        T04_OK.replace(
            '"owner": null, "date": "2026-06-02"', '"owner": "marketing", "date": "2026-06-02"'
        ),
        False,
        "owner invented for the launch",
    ),
    ("T04", T04_OK.replace('"2026-06-02"', '"2 June 2026"'), False, "date not ISO"),
    (
        "T04",
        T04_OK.replace(
            ', {"topic": "feature_freeze", "owner": "engineering", "date": "2026-05-20"}', ""
        ),
        False,
        "decision missing",
    ),
    (
        "T04",
        '{"decisions": "launch 2 June; marketing press release; engineering freeze 20 May"}',
        False,
        "not a list of records",
    ),
    (
        "T04",
        "- Launch 2 June\n- Marketing owns the press release\n- Feature freeze 20 May",
        False,
        "v2-style bullet list",
    ),
    # T07 — explicit instruction compliance only
    ("T07", '"Please send me the report when you can."', True, "wrapped in quotes"),
    ("T07", "Please let me know when the report is ready.", True, "'know' is not 'now'"),
    ("T07", "Please, could you share the report.", True, "comma after Please"),
    ("T07", "PLEASE SEND THE REPORT.", True, "rules are case-insensitive"),
    ("T07", "Please send the report now.", False, "contains 'now'"),
    ("T07", "Please send the report; it is late.", False, "contains 'late'"),
    ("T07", "Could you please send the report.", False, "does not start with Please"),
    ("T07", "Pleased to receive the report.", False, "'Pleased' is not the word 'Please'"),
    ("T07", "Please send the report", False, "no full stop"),
    ("T07", "Please send the report?", False, "ends with a question mark"),
    ("T07", "Please send the reports.", False, "'the reports' is not the words 'the report'"),
    (
        "T07",
        "Please send me the report when you have a free moment later this week if possible.",
        False,
        "16 words",
    ),
    (
        "T07",
        "Please send me the report when you have a free moment this week if possible.",
        True,
        "exactly 15 words",
    ),
    # T12 — fully anchored final answer
    ("T12", "ANSWER: 5/36.", True, "trailing full stop"),
    ("T12", "ANSWER: 5 / 36", True, "spaces around slash"),
    ("T12", "ANSWER: 5/36 or 1/6", False, "trailing wrong alternative (v2 false pass)"),
    ("T12", "ANSWER: 5/36, i.e. 1/6", False, "trailing contradiction (v2 false pass)"),
    ("T12", "ANSWER: 15/36", False, "anchored at the start"),
    ("T12", "ANSWER: 5/360", False, "anchored at the end"),
    ("T12", "5/36", False, "no ANSWER line"),
    # T17 — validated accepted translations only
    *[("T17", t + ".", True, "accepted translation") for t in CASES["T17"].scoring["accept"]],
    ("T17", "la biblioteca abre a las nueve", True, "lowercase, no full stop"),
    ("T17", "La biblioteca no abre a las nueve.", False, "negated (v2 false pass)"),
    ("T17", "Las nueve abre a la biblioteca.", False, "scrambled word order (v2 false pass)"),
    ("T17", "La biblioteca abre a las nueve de la noche.", False, "adds 'at night'"),
    ("T17", "La biblioteca abre a las diez.", False, "wrong time"),
    ("T17", "La biblioteca cierra a las 9.", False, "wrong verb"),
    ("T17", "Translation: La biblioteca abre a las nueve.", False, "extra prose"),
    ("T17", "The library opens at nine o'clock.", False, "not translated"),
    # C07 — exactly two unique, merged SKUs
    ("C07", C07_OK.replace("SKU-118", "sku-118"), True, "SKU key case-insensitive"),
    (
        "C07",
        '{"customer": "Omar Haddad", "items": [{"sku": "SKU-118", "quantity": 2}, {"sku": "SKU-118", "quantity": 3}, {"sku": "SKU-204", "quantity": 5}], "total_units": 10}',
        False,
        "repeated SKU not merged (v2 false pass)",
    ),
    ("C07", C07_OK.replace("]", ', {"sku": "SKU-999", "quantity": 0}]'), False, "extra SKU"),
    ("C07", C07_OK.replace('"total_units": 10', '"total_units": 7'), False, "wrong total"),
    (
        "C07",
        C07_OK.replace(
            '"quantity": 5}, {"sku": "SKU-204", "quantity": 5}',
            '"quantity": 5}, {"sku": "SKU-204", "quantity": "5"}',
        ),
        False,
        "quantity as a string",
    ),
    ("C07", C07_OK.replace('"Omar Haddad"', '"Omar"'), False, "wrong customer"),
    # C09 — round-half-up specified
    ("C09", "ANSWER: $1,157.63", True, "currency and thousands separator"),
    ("C09", "ANSWER: 1157.63 (rounded half up)", True, "trailing note"),
    ("C09", "ANSWER: 1157.62", False, "round-half-even result"),
    ("C09", "ANSWER: 1157.625", False, "not rounded (v2 accepted this within tolerance)"),
    ("C09", "ANSWER: 1157.6", False, "one decimal place"),
]

# v2 adversarial answers for every unchanged case must behave identically in v3.
CARRIED = [a for a in V2_ADVERSARIAL if a[0] not in CORRECTED]


def test_v2_is_unchanged() -> None:
    assert V2.sha256 == "614e14497b380539baed24ad87f3619e11107d2adc35230004b652dec6994550"


def test_v3_size_balance_and_review_status() -> None:
    assert len(V3.cases) == 45
    assert Counter(c.difficulty for c in V3.cases) == {"simple": 15, "standard": 18, "complex": 12}
    assert V3.meta["status"] == "draft-pending-human-review"
    assert V3.meta["reviewed_by"] == {}
    assert V3.fully_reviewed is False
    assert V3.meta["code_execution"] is False and V3.code_execution_cases == []
    assert not any(c.needs_human_review for c in V3.cases)


def test_only_the_corrected_cases_differ_from_v2() -> None:
    changed = [c.id for c in V3.cases if c.model_dump() != V2_CASES[c.id].model_dump()]
    assert changed == CORRECTED
    assert V3.meta["changed_from_v2"] == CORRECTED


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
        (
            "T04",
            T04_OK.replace('"owner": "marketing"', '"owner": "engineering"').replace(
                '"owner": "engineering", "date": "2026-05-20"',
                '"owner": "marketing", "date": "2026-05-20"',
            ),
        ),
        ("T12", "Five of 36 outcomes.\nANSWER: 5/36 or 1/6"),
        ("T17", "La biblioteca no abre a las nueve."),
        ("T17", "Las nueve abre a la biblioteca."),
        (
            "C07",
            '{"customer": "Omar Haddad", "items": [{"sku": "SKU-118", "quantity": 2}, {"sku": "SKU-118", "quantity": 3}, {"sku": "SKU-204", "quantity": 5}], "total_units": 10}',
        ),
        ("C09", "ANSWER: 1157.625"),
    ],
)
def test_v2_false_passes_are_fixed_in_v3(case_id: str, answer: str) -> None:
    """Evidence for the review findings: v2 accepted these wrong answers; v3 rejects them."""
    if case_id == "T04":
        # v2's T04 was a bullet list, so the equivalent wrong answer is "owners swapped".
        v2_answer = "- Launch 2 June\n- Engineering owns the press release\n- Marketing freezes features on 20 May"
        assert score(v2_answer, V2_CASES["T04"].scoring).passed is True
    else:
        assert score(answer, V2_CASES[case_id].scoring).passed is True
    assert score(answer, CASES[case_id].scoring).passed is False


def test_completed_corrections_all_have_positive_and_negative_answers() -> None:
    for case_id in CORRECTED:
        outcomes = {must for cid, _, must, _ in ADVERSARIAL if cid == case_id}
        assert outcomes == {True, False}, case_id


# --- abbreviation-aware sentence counting (opt-in; v2's T03 behaviour is unchanged) --------


@pytest.mark.parametrize(
    ("text", "default", "aware"),
    [
        ("See e.g. the logs. Fixed.", 3, 2),
        ("Dr. Lee fixed it at 9 a.m. today.", 3, 1),
        ("J. Smith restored service. Done.", 3, 2),
        ("It took approx. 45 minutes.", 2, 1),
        ("Disk filled. Checkout broke.", 2, 2),
        ("Done etc.", 1, 1),
        ("", 0, 0),
    ],
)
def test_sentence_counting(text: str, default: int, aware: int) -> None:
    assert count_sentences(text) == default
    assert count_sentences(text, abbreviation_aware=True) == aware


def test_sentence_rules_option_in_contains_scoring() -> None:
    spec = {"method": "contains", "all": ["disk"], "max_sentences": 2}
    text = "Disk filled, e.g. on db-1. Fixed."
    assert score(text, spec).passed is False  # legacy counter: 3 sentences
    assert score(text, {**spec, "sentence_rules": "abbreviation_aware"}).passed is True


# --- pre-registration chain -------------------------------------------------------------------


def test_v3_preregistration_is_pinned_and_names_the_manifest() -> None:
    path = preregistration_path("routewise_bench_v3")
    assert path.name == "preregistration_routewise_bench_v3.yaml"
    prereg, sha = load_preregistration(path, dataset=V3)
    assert prereg["dataset_sha256"] == V3.sha256
    assert V3.meta["preregistration_sha256"] == sha
    assert prereg["cost_rule"]["requires_ci_supported_non_inferiority"] is True
    assert prereg["cost_rule"]["unknown_cost_observations"] == "block"
    assert prereg["run_validity"]["provider_errors"] == "missing"
    manifest_path = EVAL_ROOT / prereg["experiment_manifest"]["file"]
    _, manifest_sha = manifest_mod.load_manifest(manifest_path)
    assert manifest_sha == prereg["experiment_manifest"]["sha256"]
    # v2 keeps its own, untouched pre-registration.
    v2_prereg, v2_sha = load_preregistration(preregistration_path("routewise_bench_v2"), dataset=V2)
    assert v2_sha == V2.meta["preregistration_sha256"] and "experiment_manifest" not in v2_prereg


# --- experiment manifest -----------------------------------------------------------------------


def _intended_settings(**overrides: Any) -> Settings:
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


def _prereg() -> dict[str, Any]:
    prereg, _ = load_preregistration(preregistration_path("routewise_bench_v3"), dataset=V3)
    return prereg


STRATEGY_NAMES = ["baseline_premium", "routewise", "routewise_tier_first"]


def test_manifest_matches_the_intended_configuration_except_superseded_code() -> None:
    """v4 changed evaluation code that v3 pinned (scorers, report, runner). v3 is therefore
    correctly unrunnable on current code. Every non-code field still matches v3's intended
    configuration, and the only differences are code-file hashes."""
    prereg = _prereg()
    manifest, _ = manifest_mod.load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])
    actual = manifest_mod.build_manifest(_intended_settings(), _groq(), STRATEGY_NAMES, schema=1)
    differences = manifest_mod.diff(manifest["pinned"], actual)
    assert differences, "v3 should no longer match: its pinned evaluation code was superseded by v4"
    assert all(d.startswith("files.") and d.endswith(".sha256") for d in differences), differences
    with pytest.raises(ValueError, match="configuration differs"):
        manifest_mod.check_manifest(prereg, _intended_settings(), _groq(), STRATEGY_NAMES)
    pinned = manifest["pinned"]
    assert pinned["expected_models"] == ["groq/openai/gpt-oss-120b", "groq/openai/gpt-oss-20b"]
    assert {m["provider_model_id"] for m in pinned["models"]} == {
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    }
    assert all(m["pricing"] for m in pinned["models"])  # pricing snapshot recorded per model
    assert pinned["routing_policy"]["version"] == "rw-2026.11-v1"
    assert set(pinned["files"]) >= {
        "routing_policy",
        "model_registry",
        "scorers",
        "report",
        "runner",
    }


@pytest.mark.parametrize(
    ("overrides", "providers", "strategies", "where"),
    [
        ({"mock_provider_enabled": True}, None, None, "execution.mock_provider_enabled"),
        ({"request_deadline_s": 90.0}, None, None, "execution.request_deadline_s"),
        ({"retry_backoff_cap_s": 8.0}, None, None, "execution.retry_backoff_cap_s"),
        ({}, None, ["routewise"], "execution.strategies"),
        ({}, "retries", None, "providers.groq.max_retries"),
    ],
)
def test_manifest_refuses_any_configuration_drift(
    overrides: dict[str, Any], providers: str | None, strategies: list[str] | None, where: str
) -> None:
    provs = _groq()
    if providers == "retries":
        provs["groq"].max_retries = 0
    with pytest.raises(ValueError, match="configuration differs") as info:
        manifest_mod.check_manifest(
            _prereg(), _intended_settings(**overrides), provs, strategies or STRATEGY_NAMES
        )
    assert where in str(info.value)


def test_manifest_detects_changed_file_contents(tmp_path: Path) -> None:
    policy = tmp_path / "routing_policy.yaml"
    policy.write_text(
        Path(_intended_settings().routing_policy_path).read_text(encoding="utf-8") + "\n# edit\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"files\.routing_policy"):
        manifest_mod.check_manifest(
            _prereg(), _intended_settings(routing_policy_path=policy), _groq(), STRATEGY_NAMES
        )


def test_manifest_hash_ignores_line_endings(tmp_path: Path) -> None:
    lf, crlf = tmp_path / "lf.txt", tmp_path / "crlf.txt"
    lf.write_bytes(b"a\nb\n")
    crlf.write_bytes(b"a\r\nb\r\n")
    assert manifest_mod.text_sha256(lf) == manifest_mod.text_sha256(crlf)


def test_edited_manifest_file_is_refused(tmp_path: Path) -> None:
    prereg = _prereg()
    original = (EVAL_ROOT / prereg["experiment_manifest"]["file"]).read_text(encoding="utf-8")
    (tmp_path / prereg["experiment_manifest"]["file"]).write_text(
        original + "\n# edit\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="changed since it was pre-registered"):
        manifest_mod.check_manifest(
            prereg, _intended_settings(), _groq(), STRATEGY_NAMES, directory=tmp_path
        )


# --- report rules registered in prereg-v3 (synthetic outcomes; nothing is run) -------------------


def _outcomes(
    strategy: str,
    *,
    passes: int,
    answered: int = 45,
    cost: str | None = "0.00010000",
    unknown_cost: int = 0,
    model: str = "openai/gpt-oss-120b",
) -> list[Any]:
    from app.evaluation.runner import CaseOutcome

    out = []
    for i in range(45):
        executed = i < answered
        priced = executed and i >= unknown_cost and cost is not None
        out.append(
            CaseOutcome(
                case_id=f"X{i:02d}",
                difficulty="simple",
                category="c",
                strategy=strategy,
                passed=(i < passes) if executed else False,  # how the runner records errors
                score=None,
                needs_human_review=False,
                error_code=None if executed else "ALL_PROVIDERS_FAILED",
                provider="groq" if executed else None,
                model=model if executed else None,
                latency_ms=100 if executed else None,
                estimated_list_cost_usd=cost if priced else None,
                list_cost_status="estimated" if priced else "unavailable",
            )
        )
    return out


def _summary(base: list[Any], cand: list[Any]) -> dict[str, Any]:
    from app.evaluation.report import build_summary
    from app.evaluation.runner import BenchmarkResult

    prereg, sha = load_preregistration(preregistration_path("routewise_bench_v3"), dataset=V3)
    return build_summary(
        BenchmarkResult(
            label="synthetic",
            simulated=False,
            dataset=V3.name,
            dataset_sha256=V3.sha256,
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


def test_provider_errors_are_missing_not_failures() -> None:
    summary = _summary(
        _outcomes("baseline_premium", passes=44, answered=44),
        _outcomes("routewise", passes=44, cost="0.00005000", model="openai/gpt-oss-20b"),
    )
    base = summary["metrics"]["baseline_premium"]
    assert base["scorable"] == 44 and base["pass_rate"] == 1.0  # the error is not a failure


def test_cost_claim_requires_ci_supported_non_inferiority() -> None:
    # Point estimate within the margin (-4.4 pp), but the CI lower bound is below -5 pp.
    summary = _summary(
        _outcomes("baseline_premium", passes=40),
        _outcomes("routewise", passes=38, cost="0.00005000", model="openai/gpt-oss-20b"),
    )
    comparison = summary["comparisons_vs_baseline"]["routewise"]
    assert comparison["quality_rule_point_estimate_holds"] is True
    assert comparison["non_inferiority_supported_by_ci"] is False
    assert comparison["cost_rule_holds"] is False
    assert (
        "quality non-inferiority not supported by the CI" in comparison["cost_rule_blocked_reasons"]
    )


def test_cost_claim_allowed_when_supported_and_cheaper() -> None:
    summary = _summary(
        _outcomes("baseline_premium", passes=40),
        _outcomes("routewise", passes=40, cost="0.00005000", model="openai/gpt-oss-20b"),
    )
    comparison = summary["comparisons_vs_baseline"]["routewise"]
    assert comparison["non_inferiority_supported_by_ci"] is True
    assert comparison["cost_rule_holds"] is True and comparison["cost_rule_blocked_reasons"] == []


@pytest.mark.parametrize("where", ["unpriced", "failed"])
def test_unknown_cost_observations_block_cost_claims(where: str) -> None:
    candidate = (
        _outcomes(
            "routewise", passes=40, cost="0.00005000", unknown_cost=1, model="openai/gpt-oss-20b"
        )
        if where == "unpriced"
        else _outcomes(
            "routewise", passes=40, answered=44, cost="0.00005000", model="openai/gpt-oss-20b"
        )
    )
    summary = _summary(_outcomes("baseline_premium", passes=40), candidate)
    assert summary["metrics"]["routewise"]["unknown_cost_observations"] == 1
    comparison = summary["comparisons_vs_baseline"]["routewise"]
    assert comparison["cost_rule_holds"] is False
    assert any("unknown cost" in r for r in comparison["cost_rule_blocked_reasons"])
    # Unknown is never zero: the known total isn't inflated by a zero-cost observation.
    assert (
        Decimal(summary["metrics"]["routewise"]["estimated_list_cost_total_usd"])
        == Decimal("0.00005000") * 44
    )


def test_model_outside_the_manifest_invalidates_the_run() -> None:
    summary = _summary(
        _outcomes("baseline_premium", passes=40),
        _outcomes("routewise", passes=40, model="llama-3.1-8b-instant"),
    )
    assert summary["publishable"] is False
    assert any("outside the experiment manifest" in r for r in summary["publishable_reasons"])
