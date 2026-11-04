"""routewise_bench_v2: integrity, pre-registration, and scoring regression tests.

Every case has a (correct, wrong) reference pair. Every scoring rule changed from v1 also has
adversarial answers: wrong answers that used to pass (false positives) and right answers that used
to fail (false negatives), each pinned to the outcome it must now have. No model is called.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from app.evaluation.dataset import (
    EVAL_ROOT,
    load_dataset,
    load_preregistration,
    preregistration_path,
)
from app.evaluation.scorers import count_sentences, final_answer, score

V1 = load_dataset("routewise_bench_v1")
V2 = load_dataset("routewise_bench_v2")
CASES = {c.id: c for c in V2.cases}

# (correct answer, plausible wrong answer) for every v2 case.
REFERENCE: dict[str, tuple[str, str]] = {
    "S01": ("Positive", "Negative"),
    "S02": ("apple, mango, pear", "pear, mango, apple"),
    "S03": ("Dolphin", "Shark"),
    "S04": ("billing", "account"),
    "S05": ("+14155550132", "415-555-0132"),
    "S06": ("maria.lopez@example.org", "Maria Lopez"),
    "S07": ("2026-03-14", "2026-14-03"),
    "S08": ("Canberra", "Sydney"),
    "S09": ("391", "381"),
    "S10": ("0.9", "0.11"),
    "S11": ("French", "Spanish"),
    "S12": ("spam", "legitimate"),
    "S13": ("SHIP IT TODAY", "Ship It Today"),
    "S14": ("Yes", "No"),
    "S15": ('{"name": "Priya", "age": 34}', '{"name": "Priya", "age": "thirty-four"}'),
    "T01": (
        '{"invoice_number": "INV-2026-0042", "total_amount": 1250.0, "currency": "EUR"}',
        '{"invoice_number": "INV-2026-0042", "total_amount": 1250, "currency": "€"}',
    ),
    "T02": (
        '{"people": [{"name": "Dana Kim", "role": "Product Manager"}, {"name": "Luis Ortega", "role": "backend engineer"}, {"name": "Aiko Sato", "role": "designer"}]}',
        '{"people": [{"name": "Dana Kim", "role": "designer"}, {"name": "Luis Ortega", "role": "backend engineer"}, {"name": "Aiko Sato", "role": "product manager"}]}',
    ),
    "T03": (
        "The primary database ran out of disk space, breaking checkout for 45 minutes. Engineers expanded storage and added an alert at 80% disk usage.",
        "Checkout failed on Monday and engineers fixed it.",
    ),
    "T04": (
        "- Launch moved to 2 June\n- Marketing owns the press release\n- Feature freeze on 20 May",
        "- Launch moved to 2 June\n- Marketing owns the press release",
    ),
    "T05": ("Thursday", "Tuesday"),
    "T06": (
        '{"category": "account", "urgency": "high"}',
        '{"category": "account", "urgency": "low"}',
    ),
    "T07": (
        "Could you please send me the report when you get a moment? Thank you.",
        "Please send me the report now.",
    ),
    "T08": (
        "SELECT name FROM customers WHERE country = 'Germany' ORDER BY name ASC;",
        "SELECT * FROM customers;",
    ),
    "T09": ("14", "18"),
    "T10": ("Line 7 counts every number, not just positives.\nANSWER: 7", "ANSWER: 6"),
    "T11": ("33", "34"),
    "T12": ("Five of the 36 outcomes sum to 8.\nANSWER: 5/36", "ANSWER: 1/6"),
    "T13": ("Thursday", "Wednesday"),
    "T14": (
        '{"dates": ["2026-02-03", "2026-02-14", "2026-03-01", "2026-04-01"]}',
        '{"dates": ["2026-03-02", "2026-02-14", "2026-01-03", "2026-04-01"]}',
    ),
    "T15": ('{"total": 9.9}', '{"total": 9.0}'),
    "T16": ("NOT_IN_CONTEXT", "The phone number is not listed."),
    "T17": ("La biblioteca abre a las nueve.", "The library opens at nine."),
    "T18": ('{"defect": true, "part": "zipper"}', '{"defect": false, "part": null}'),
    "C01": (
        "A is 90 km ahead at 09:00 and B closes at 30 km/h, so 3 hours.\n12:00",
        "B catches A after 2 hours.\n11:00",
    ),
    "C02": (
        "500 L by 08:20, then 50 L/min for 14 minutes.\nANSWER: 08:34",
        "Pipe A closes at 08:40, so the tank is full at 08:40.\nANSWER: 08:40",
    ),
    "C03": ("2 + 3 + 3 + 3 = 11\nANSWER: 11", "ANSWER: 8"),
    "C04": (
        '{"Ana": 30, "Ben": 10, "Cara": 0, "rejected": 1}',
        '{"Ana": 30, "Ben": -15, "Cara": 25, "rejected": 0}',
    ),
    "C05": (
        '{"rows": [["Cara", 120], ["Abe", 75]]}',
        '{"rows": [["Cara", 120], ["Abe", 75], ["Dev", 30]]}',
    ),
    "C06": ("Ana yellow, Cy blue, so Eli is white.\nANSWER: Eli", "ANSWER: Di"),
    "C07": (
        '{"customer": "Omar Haddad", "items": [{"sku": "SKU-118", "quantity": 5}, {"sku": "SKU-204", "quantity": 5}], "total_units": 10}',
        '{"customer": "Omar Haddad", "items": [{"sku": "SKU-118", "quantity": 2}, {"sku": "SKU-204", "quantity": 5}], "total_units": 7}',
    ),
    "C08": ("2+3+5+7+11+13+17+19+23+29+31+37+41+43+47\nANSWER: 328", "ANSWER: 329"),
    "C09": ("1000 * 1.05^3 = 1157.625\nANSWER: 1157.63", "ANSWER: 1150.00"),
    "C10": (
        '{"duration": 11, "critical_path": ["A", "C", "E", "F"]}',
        '{"duration": 10, "critical_path": ["A", "B", "D", "E", "F"]}',
    ),
    "C11": (
        '{"valid": ["Harbor2026Tide", "Quartz88Lantern", "Orbit9StoneArc"]}',
        '{"valid": ["Harbor2026Tide", "Kai2026Rivers", "Quartz88Lantern", "Orbit9StoneArc"]}',
    ),
    "C12": (
        '{"A": "09:30", "B": "10:30", "C": "09:00"}',
        '{"A": "09:00", "B": "10:00", "C": "09:30"}',
    ),
}

# Adversarial answers for every changed scoring rule: (case, answer, must_pass, why).
ADVERSARIAL: list[tuple[str, str, bool, str]] = [
    # S02 (new)
    ("S02", "apple,mango,pear", True, "no spaces after commas"),
    ("S02", "Apple, Mango, Pear.", True, "capitalised with full stop"),
    ("S02", "apple, pear, mango", False, "wrong order"),
    ("S02", "apple, mango", False, "missing word"),
    # S03 (new)
    ("S03", "dolphin.", True, "lowercase with full stop"),
    ("S03", "Dolphin, not shark", False, "two labels"),
    ("S03", "trout", False, "fish"),
    # S05 (moved from v1 T14; scoring unchanged)
    ("S05", "+14155550132.", True, "trailing period"),
    ("S05", "14155550132", False, "missing +"),
    ("S05", "+1 415 555 0132", False, "E.164 has no spaces"),
    # S07: false negative fixed
    ("S07", "2026-03-14.", True, "trailing period (v1 false fail)"),
    ("S07", "`2026-03-14`", True, "backticks"),
    ("S07", "14/03/2026", False, "wrong format"),
    ("S07", "The date is 2026-03-14", False, "extra prose, prompt asks for the date only"),
    # S09 / T11: false negatives fixed
    ("S09", "17 x 23 = 391", True, "restated working (v1 false fail)"),
    ("S09", "391.", True, "trailing period"),
    ("S09", "17 x 23 = 381", False, "wrong result after working"),
    ("T11", "40 x 0.75 = 30; 30 x 1.10 = 33", True, "restated working (v1 false fail)"),
    ("T11", "$33.00", True, "currency format"),
    ("T11", "30 x 1.10 = 33.5", False, "wrong final number"),
    # S10 (new)
    ("S10", "0.90", True, "trailing zero"),
    ("S10", "0.9 is larger than 0.11", False, "two numbers, ambiguous"),
    # S12: false positive fixed
    ("S12", "Not spam", False, "negated label with a space (v1 false pass)"),
    ("S12", "not_spam", False, "old label"),
    ("S12", "Spam.", True, "capitalised with full stop"),
    ("S12", "spam, not legitimate", False, "extra words"),
    # S14: false negative fixed by rewording
    ("S14", "Yes, about 99.97 °C, which is approximately 100 °C.", True, "pedantic but correct"),
    ("S14", "No.", False, "wrong"),
    # T02: false positive fixed
    (
        "T02",
        '{"people": [{"name": "Dana Kim", "role": "chef"}, {"name": "Luis Ortega", "role": "x"}, {"name": "Aiko Sato", "role": "y"}]}',
        False,
        "names right, roles wrong (v1 false pass)",
    ),
    (
        "T02",
        '{"people": [{"name": "Dana Kim", "role": "product manager"}, {"name": "Luis Ortega", "role": "Back-end engineer"}, {"name": "Aiko Sato", "role": "designer"}]}',
        True,
        "hyphenated role variant",
    ),
    (
        "T02",
        '{"people": [{"name": "Dana Kim", "role": "product manager"}, {"name": "Luis Ortega", "role": "backend engineer"}, {"name": "Aiko Sato", "role": "designer"}, {"name": "Maria", "role": "intern"}]}',
        False,
        "invented fourth person",
    ),
    # T03: false positive fixed
    (
        "T03",
        "Disk filled up. Checkout broke for 45 minutes. Storage was expanded. An alert was added. Service was restored.",
        False,
        "five sentences (v1 false pass)",
    ),
    (
        "T03",
        "Disk space ran out at 09:12 UTC and checkout failed for 45 minutes; storage was expanded and an alert now fires above 80%.",
        True,
        "one sentence with times and percent",
    ),
    (
        "T03",
        "Checkout failed for 45 minutes. Engineers expanded storage.",
        False,
        "missing disk and alert",
    ),
    # T04: false positive and false negative fixed
    (
        "T04",
        "- Launch moved to June 2\n- Marketing owns the press release\n- Feature freeze on May 20",
        True,
        "US date order (v1 false fail)",
    ),
    (
        "T04",
        "- Launch 2nd June\n- Press release: Marketing\n- Freeze 20th May",
        True,
        "ordinal dates",
    ),
    (
        "T04",
        "- Launch 2 June\n- Marketing: press release\n- Pricing set at $10\n- Freeze 20 May",
        False,
        "lists undecided pricing (v1 false pass)",
    ),
    (
        "T04",
        "- Launch 2 June\n- Marketing owns the press release\n- Feature freeze 20 May\n- Pricing was postponed",
        False,
        "mentions the undecided topic",
    ),
    # T05: contains -> exact
    ("T05", "Thursday.", True, "full stop"),
    ("T05", "Tuesday or Thursday", False, "hedged (would have passed v1 contains)"),
    # T06: prompt now defines categories
    (
        "T06",
        '{"category": "technical", "urgency": "high"}',
        False,
        "sign-in issues are defined as account",
    ),
    (
        "T06",
        '```json\n{"category": "Account", "urgency": "High"}\n```',
        True,
        "fenced, capitalised",
    ),
    # T07: false negative fixed (instruction-based)
    (
        "T07",
        "I would be grateful if you could please send the report at your earliest convenience.",
        True,
        "polite wording off the v1 keyword list (v1 false fail)",
    ),
    (
        "T07",
        "Please let me know when you can send the report.",
        True,
        "'know' must not trip the 'now' ban",
    ),
    ("T07", "Please send the report now.", False, "uses 'now'"),
    ("T07", "Please send the report; it is late.", False, "uses 'late'"),
    ("T07", "I'd be pleased to receive the report.", False, "'pleased' is not 'please'"),
    ("T07", "Could you send the report when convenient?", False, "missing 'please'"),
    # T08: false negative fixed, stricter shape
    (
        "T08",
        "SELECT c.name FROM customers c WHERE c.country = 'Germany' ORDER BY c.name;",
        True,
        "table alias (v1 false fail)",
    ),
    (
        "T08",
        "```sql\nSELECT name\nFROM customers AS cu\nWHERE country = 'Germany'\nORDER BY name;\n```",
        True,
        "fenced, multi-line, AS alias",
    ),
    (
        "T08",
        "SELECT name FROM customers WHERE country = 'Germany' ORDER BY name DESC",
        False,
        "descending",
    ),
    (
        "T08",
        "SELECT name, country FROM customers WHERE country = 'Germany' ORDER BY name",
        False,
        "extra column",
    ),
    ("T08", "SELECT name FROM customers WHERE country = 'Germany'", False, "no ORDER BY"),
    # T09 (new)
    ("T09", "14\n", True, "trailing newline"),
    ("T09", "The output is 8 + 6 = 14", False, "several numbers; prompt asks for the output only"),
    # T10 (new)
    ("T10", "**ANSWER: 7**", True, "markdown bold"),
    (
        "T10",
        "Line 7 is wrong because count += 1 runs for every n.\nANSWER: 7 (indentation)",
        True,
        "explanation after the number",
    ),
    ("T10", "The bug is on line 7.", False, "no ANSWER line"),
    ("T10", "ANSWER: 5", False, "wrong line"),
    # T12 (moved from C02): false positive fixed
    (
        "T12",
        "Not 5/36; the answer is 1/6\nANSWER: 1/6",
        False,
        "mentions 5/36 but answers 1/6 (v1 false pass)",
    ),
    ("T12", "ANSWER: 5 / 36", True, "spaces around slash"),
    ("T12", "ANSWER: 10/72", False, "not reduced"),
    # T14 (new)
    ("T14", '{"dates": ["2026-02-03", "2026-02-14", "2026-03-01"]}', False, "missing a date"),
    (
        "T14",
        '{"dates": ["2026-02-14", "2026-02-03", "2026-03-01", "2026-04-01"]}',
        False,
        "wrong order",
    ),
    # T17: false positive fixed
    ("T17", "La biblioteca cierra a las 9.", False, "wrong verb 'closes' (v1 false pass)"),
    ("T17", "La biblioteca abre a las 9:00.", True, "digits"),
    ("T17", "La biblioteca abre a las diez.", False, "wrong time"),
    # T18: wording now fixes the part name
    ("T18", '{"defect": true, "part": "zip"}', False, "not the word in the review"),
    # C02 (new)
    ("C02", "ANSWER: 8:34", True, "no leading zero"),
    ("C02", "The tank is full at 08:34.", False, "no ANSWER line"),
    # C03 (new)
    ("C03", "ANSWER: 11 (sum of gaps)", True, "trailing note"),
    ("C03", "ANSWER: 12", False, "off by one"),
    # C04 (new)
    (
        "C04",
        '{"Ana": 30, "Ben": 10, "Cara": 0, "rejected": 1, "notes": "event 6 rejected"}',
        True,
        "extra key ignored",
    ),
    (
        "C04",
        '{"Ana": "30", "Ben": 10, "Cara": 0, "rejected": 1}',
        False,
        "string instead of number",
    ),
    # C05 (new)
    ("C05", '{"rows": [["Abe", 75], ["Cara", 120]]}', False, "wrong order"),
    ("C05", '{"rows": [["cara", 120], ["abe", 75]]}', False, "names must be as stored"),
    # C06 (rewritten)
    ("C06", "ANSWER: eli", True, "lowercase"),
    ("C06", "Eli", False, "no ANSWER line"),
    # C08: false negative fixed
    ("C08", "ANSWER: 328 (sum of 15 primes)", True, "trailing note (v1 false fail)"),
    ("C08", "There are 15 primes.\nANSWER: 327", False, "wrong sum"),
    # C09: same convention
    ("C09", "ANSWER: $1,157.63", True, "currency and thousands separator"),
    ("C09", "ANSWER: 1157.625", True, "unrounded value within tolerance"),
    ("C09", "ANSWER: 1157.50", False, "wrong"),
    # C10 (new, replaces the subjective case)
    ("C10", '{"duration": 11, "critical_path": ["A", "C", "E"]}', False, "incomplete path"),
    (
        "C10",
        '{"duration": "11 days", "critical_path": ["A", "C", "E", "F"]}',
        False,
        "duration not a number",
    ),
    # C11 (new)
    (
        "C11",
        '{"valid": ["Harbor2026Tide", "Orbit9StoneArc", "Quartz88Lantern"]}',
        False,
        "not in the order listed",
    ),
    ("C11", '{"valid": ["Harbor2026Tide", "Quartz88Lantern"]}', False, "missed one"),
]


def test_v1_is_unchanged_and_still_valid() -> None:
    assert len(V1.cases) == 45
    assert V1.meta["status"] == "draft-pending-human-review"
    assert V1.fully_reviewed is False


def test_v2_size_balance_and_review_status() -> None:
    assert len(V2.cases) == 45
    assert Counter(c.difficulty for c in V2.cases) == {"simple": 15, "standard": 18, "complex": 12}
    for case in V2.cases:
        prefix = {"simple": "S", "standard": "T", "complex": "C"}[case.difficulty]
        assert case.id.startswith(prefix)
    assert V2.meta["status"] == "draft-pending-human-review"
    assert V2.meta["reviewed_by"] == {}  # never marked reviewed on the owner's behalf
    assert V2.fully_reviewed is False


def test_v2_has_no_code_execution_and_no_human_graded_cases() -> None:
    assert V2.meta["code_execution"] is False
    assert V2.code_execution_cases == []
    assert not any(c.needs_human_review for c in V2.cases)


def test_v2_preregistration_matches_dataset_and_is_pinned() -> None:
    path = preregistration_path("routewise_bench_v2")
    assert path.name == "preregistration_routewise_bench_v2.yaml"
    prereg, sha = load_preregistration(path, dataset=V2)
    assert prereg["dataset"] == "routewise_bench_v2"
    assert prereg["dataset_sha256"] == V2.sha256  # registered against this exact file
    assert V2.meta["preregistration_sha256"] == sha
    assert prereg["quality_rule"]["non_inferiority_margin"] == 0.05
    # v1 keeps its original pre-registration.
    assert preregistration_path("routewise_bench_v1") == EVAL_ROOT / "preregistration.yaml"


def test_preregistration_for_another_dataset_is_refused() -> None:
    with pytest.raises(ValueError, match="registered for"):
        load_preregistration(preregistration_path("routewise_bench_v2"), dataset=V1)


def test_edited_preregistration_is_refused(tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    original = preregistration_path("routewise_bench_v2").read_text(encoding="utf-8")
    edited = tmp_path / "preregistration_routewise_bench_v2.yaml"
    edited.write_text(
        original.replace("non_inferiority_margin: 0.05", "non_inferiority_margin: 0.10"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="changed since it was pinned"):
        load_preregistration(edited, dataset=V2)


def test_every_case_has_a_reference_pair() -> None:
    assert set(REFERENCE) == set(CASES)


@pytest.mark.parametrize("case_id", sorted(REFERENCE))
def test_correct_answer_passes_and_wrong_answer_fails(case_id: str) -> None:
    case = CASES[case_id]
    good, bad = REFERENCE[case_id]
    assert score(good, case.scoring).passed is True, (case_id, score(good, case.scoring).details)
    assert score(bad, case.scoring).passed is False, (case_id, score(bad, case.scoring).details)


@pytest.mark.parametrize(("case_id", "answer", "must_pass", "why"), ADVERSARIAL)
def test_adversarial_answers(case_id: str, answer: str, must_pass: bool, why: str) -> None:
    result = score(answer, CASES[case_id].scoring)
    assert result.passed is must_pass, (case_id, why, result.details)


def test_changed_scoring_rules_all_have_adversarial_tests() -> None:
    v1 = {c.id: c for c in V1.cases}
    changed = {
        c.id
        for c in V2.cases
        if c.id not in v1 or v1[c.id].scoring != c.scoring or v1[c.id].prompt != c.prompt
    }
    covered = {case_id for case_id, *_ in ADVERSARIAL}
    assert changed <= covered, sorted(changed - covered)


def test_unchanged_cases_are_identical_to_v1() -> None:
    unchanged = V2.meta["unchanged_from_v1"]
    v1 = {c.id: c for c in V1.cases}
    for case_id in unchanged:
        assert CASES[case_id].model_dump() == v1[case_id].model_dump(), case_id


# --- scorer helpers ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ANSWER: 42", "42"),
        ("working...\n**Answer:** 12:00", "12:00"),
        ("Final answer: Eli", "Eli"),
        ("ANSWER: 1\nmore text\nANSWER: 2", "2"),  # the last one counts
        ("The answer is 42", None),
    ],
)
def test_final_answer_extraction(text: str, expected: str | None) -> None:
    assert final_answer(text) == expected


@pytest.mark.parametrize(
    ("text", "n"),
    [
        ("One. Two.", 2),
        ("At 09:12 UTC disk hit 80%. Fixed.", 2),
        ("No closing punctuation", 1),
        ("Wait! Really? Yes.", 3),
        ("", 0),
    ],
)
def test_sentence_count(text: str, n: int) -> None:
    assert count_sentences(text) == n


# --- pre-registered guards in the report (synthetic outcomes; nothing is run) -------------


def _outcomes(strategy: str, passes: int, answered: int, total: int = 45) -> list[Any]:
    from app.evaluation.runner import CaseOutcome

    out = []
    for i in range(total):
        executed = i < answered
        out.append(
            CaseOutcome(
                case_id=f"X{i:02d}",
                difficulty="simple",
                category="c",
                strategy=strategy,
                passed=(i < passes) if executed else None,
                score=None,
                needs_human_review=False,
                error_code=None if executed else "ALL_PROVIDERS_FAILED",
                latency_ms=100 if executed else None,
            )
        )
    return out


def _summary(base: tuple[int, int], cand: tuple[int, int]) -> dict[str, Any]:
    from app.evaluation.report import build_summary
    from app.evaluation.runner import BenchmarkResult

    prereg, sha = load_preregistration(preregistration_path("routewise_bench_v2"), dataset=V2)
    result = BenchmarkResult(
        label="synthetic",
        simulated=False,
        dataset=V2.name,
        dataset_sha256=V2.sha256,
        dataset_fully_reviewed=True,
        preregistration=prereg,
        preregistration_sha256=sha,
        started_at="",
        finished_at="",
        config_snapshot={},
        run_ids={},
        outcomes=_outcomes("baseline_premium", *base) + _outcomes("routewise", *cand),
    )
    return build_summary(result)


def test_valid_run_allows_claims() -> None:
    summary = _summary((40, 45), (39, 45))
    assert summary["publishable"] is True
    assert summary["comparisons_vs_baseline"]["routewise"]["claims_allowed"] is True


def test_run_with_too_many_missing_answers_is_invalid() -> None:
    summary = _summary((40, 45), (39, 42))  # 42/45 answered < 95%
    comparison = summary["comparisons_vs_baseline"]["routewise"]
    assert comparison["claims_allowed"] is False
    assert summary["publishable"] is False
    assert any("run invalid" in r for r in summary["publishable_reasons"])


def test_baseline_below_floor_blocks_claims() -> None:
    summary = _summary((20, 45), (20, 45))  # 0.44 < 0.60 floor
    comparison = summary["comparisons_vs_baseline"]["routewise"]
    assert comparison["claims_allowed"] is False
    assert any("uninformative" in r for r in comparison["claims_blocked_reasons"])
