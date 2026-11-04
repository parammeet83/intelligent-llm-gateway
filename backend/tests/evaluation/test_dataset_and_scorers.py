"""Dataset integrity + scorer correctness.

The reference-answer tests are the important ones: for every case, a correct answer must pass
and a plausible wrong answer must fail. That's what shows the scoring rules accept correct answers
and reject incorrect ones, rather than just running without errors.
"""

from __future__ import annotations

from collections import Counter

import pytest

from app.evaluation.dataset import load_dataset, load_preregistration
from app.evaluation.scorers import score
from app.evaluation.stats import mean_difference, paired_bootstrap, percentile, wilson_interval

DATASET = load_dataset()
CASES = {c.id: c for c in DATASET.cases}

GOOD_CODE = {
    "T09": "```python\nimport re\ndef is_palindrome(s: str) -> bool:\n    t = re.sub(r'[^a-z0-9]', '', s.lower())\n    return t == t[::-1]\n```",
    "T10": "```python\ndef fizzbuzz(n):\n    out = []\n    for i in range(1, n + 1):\n        out.append('FizzBuzz' if i % 15 == 0 else 'Fizz' if i % 3 == 0 else 'Buzz' if i % 5 == 0 else str(i))\n    return out\n```",
    "C03": "```python\ndef merge_intervals(intervals):\n    out = []\n    for s, e in sorted(intervals):\n        if out and s <= out[-1][1]:\n            out[-1][1] = max(out[-1][1], e)\n        else:\n            out.append([s, e])\n    return out\n```",
    "C04": "```python\ndef roman_to_int(s):\n    v = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}\n    total = 0\n    for i, ch in enumerate(s):\n        if i + 1 < len(s) and v[ch] < v[s[i+1]]:\n            total -= v[ch]\n        else:\n            total += v[ch]\n    return total\n```",
    "C05": "```python\nfrom collections import Counter\ndef top_k_frequent(words, k):\n    c = Counter(words)\n    return sorted(c, key=lambda w: (-c[w], w))[:k]\n```",
    "C11": "```python\nimport re\ndef parse_duration(text):\n    m = re.fullmatch(r'(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?', text or '')\n    if not text or not m:\n        raise ValueError(text)\n    h, mi, s = (int(g) if g else 0 for g in m.groups())\n    return h * 3600 + mi * 60 + s\n```",
}

# (correct answer, plausible wrong answer) for every case.
REFERENCE: dict[str, tuple[str, str]] = {
    "S01": ("Positive", "Negative"),
    "S02": ("negative.", "neutral"),
    "S03": ("Neutral", "Positive"),
    "S04": ("billing", "account"),
    "S05": ("Technical", "shipping"),
    "S06": ("maria.lopez@example.org", "Maria Lopez"),
    "S07": ("2026-03-14", "14 March 2026"),
    "S08": ("Canberra", "Sydney"),
    "S09": ("391", "381"),
    "S10": ("2500", "250"),
    "S11": ("French", "Spanish"),
    "S12": ("spam", "not_spam"),
    "S13": ("SHIP IT TODAY", "Ship It Today"),
    "S14": ("Yes", "No"),
    "S15": ('{"name": "Priya", "age": 34}', '{"name": "Priya", "age": "thirty-four"}'),
    "T01": (
        '{"invoice_number": "INV-2026-0042", "total_amount": 1250.0, "currency": "EUR"}',
        '{"invoice_number": "INV-2026-0042", "total_amount": 1250, "currency": "€"}',
    ),
    "T02": (
        '{"people": [{"name": "Dana Kim", "role": "product manager"}, {"name": "Luis Ortega", "role": "backend engineer"}, {"name": "Aiko Sato", "role": "designer"}]}',
        '{"people": [{"name": "Dana Kim", "role": "product manager"}]}',
    ),
    "T03": (
        "The primary database ran out of disk space, breaking checkout for 45 minutes. Engineers expanded storage and added an alert at 80% disk usage.",
        "Checkout failed on Monday and engineers fixed it.",
    ),
    "T04": (
        "- Launch moved to 2 June\n- Marketing owns the press release\n- Feature freeze on 20 May",
        "- Launch moved to 2 June\n- Pricing decided",
    ),
    "T05": ("Thursday", "Tuesday"),
    "T06": (
        '{"category": "account", "urgency": "high"}',
        '{"category": "technical", "urgency": "high"}',
    ),
    "T07": (
        "Could you please send me the report as soon as possible? Thank you.",
        "Send me the report now, you are already late.",
    ),
    "T08": (
        "SELECT name FROM customers WHERE country = 'Germany' ORDER BY name ASC;",
        "SELECT * FROM customers;",
    ),
    "T09": (GOOD_CODE["T09"], "```python\ndef is_palindrome(s):\n    return s == s[::-1]\n```"),
    "T10": (
        GOOD_CODE["T10"],
        "```python\ndef fizzbuzz(n):\n    return [str(i) for i in range(1, n + 1)]\n```",
    ),
    "T11": ("33", "34"),
    "T12": ("yes", "no"),
    "T13": ("Thursday", "Wednesday"),
    "T14": ("+14155550132", "415-555-0132"),
    "T15": ('{"total": 9.9}', '{"total": 9.0}'),
    "T16": ("NOT_IN_CONTEXT", "The phone number is not listed."),
    "T17": ("La biblioteca abre a las nueve.", "The library opens at nine."),
    "T18": ('{"defect": true, "part": "zipper"}', '{"defect": false, "part": null}'),
    "C01": (
        "A is 90 km ahead at 09:00 and B closes at 30 km/h, so 3 hours.\n12:00",
        "B catches A after 2 hours.\n11:00",
    ),
    "C02": ("There are 5 outcomes out of 36.\n5/36", "6/36"),
    "C03": (
        GOOD_CODE["C03"],
        "```python\ndef merge_intervals(intervals):\n    return intervals\n```",
    ),
    "C04": (
        GOOD_CODE["C04"],
        "```python\ndef roman_to_int(s):\n    v = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}\n    return sum(v[c] for c in s)\n```",
    ),
    "C05": (
        GOOD_CODE["C05"],
        "```python\ndef top_k_frequent(words, k):\n    return words[:k]\n```",
    ),
    "C06": ("Ben is green, Ana yellow, Cy blue.\nDi", "Cy"),
    "C07": (
        '{"customer": "Omar Haddad", "items": [{"sku": "SKU-118", "quantity": 5}, {"sku": "SKU-204", "quantity": 5}], "total_units": 10}',
        '{"customer": "Omar Haddad", "items": [{"sku": "SKU-118", "quantity": 2}, {"sku": "SKU-204", "quantity": 5}], "total_units": 7}',
    ),
    "C08": ("2+3+5+7+11+13+17+19+23+29+31+37+41+43+47\n328", "The sum is 329"),
    "C09": ("1000 * 1.05^3 = 1157.625\n1157.63", "1150.00"),
    "C10": (
        "Optimistic locking retries on conflict, which under heavy contention causes repeated retries. Pessimistic locking serialises updates. I recommend pessimistic locking or an atomic conditional update.",
        "Use a cache.",
    ),
    "C11": (GOOD_CODE["C11"], "```python\ndef parse_duration(text):\n    return 0\n```"),
    "C12": (
        '{"A": "09:30", "B": "10:30", "C": "09:00"}',
        '{"A": "09:00", "B": "10:00", "C": "09:30"}',
    ),
}


def test_dataset_size_and_balance() -> None:
    assert len(DATASET.cases) == 45
    assert Counter(c.difficulty for c in DATASET.cases) == {
        "simple": 15,
        "standard": 18,
        "complex": 12,
    }
    for case in DATASET.cases:
        assert case.expected and case.prompt and case.scoring["method"]


def test_dataset_is_marked_as_ai_draft_pending_review() -> None:
    assert DATASET.meta["status"] == "draft-pending-human-review"
    assert "AI-drafted" in DATASET.meta["authored_by"]
    assert DATASET.fully_reviewed is False


def test_preregistration_exists_with_quality_threshold() -> None:
    prereg, sha = load_preregistration()
    assert prereg["quality_rule"]["non_inferiority_margin"] == 0.05
    assert prereg["publication"]["dataset_review_required"] is True
    assert len(sha) == 64


def test_every_case_has_a_reference_pair() -> None:
    assert set(REFERENCE) == set(CASES)


@pytest.mark.parametrize("case_id", sorted(REFERENCE))
def test_correct_answer_passes_and_wrong_answer_fails(case_id: str) -> None:
    case = CASES[case_id]
    good, bad = REFERENCE[case_id]
    good_result = score(good, case.scoring, allow_code_exec=True)
    bad_result = score(bad, case.scoring, allow_code_exec=True)
    assert good_result.passed is True, (case_id, good_result.details)
    assert bad_result.passed is False, (case_id, bad_result.details)


def test_code_is_not_executed_unless_allowed() -> None:
    result = score(GOOD_CODE["T09"], CASES["T09"].scoring, allow_code_exec=False)
    assert result.passed is None and "disabled" in result.details["reason"]


def test_code_execution_times_out() -> None:
    looping = "```python\ndef is_palindrome(s):\n    while True:\n        pass\n```"
    result = score(looping, CASES["T09"].scoring, allow_code_exec=True)
    assert result.passed is False and "timed out" in result.details["reason"]


@pytest.mark.parametrize(
    ("output", "passed"),
    [("not_spam", False), ("spam", True), ("It is spam, not not_spam", False)],
)
def test_choice_scorer_rejects_ambiguous_answers(output: str, passed: bool) -> None:
    assert score(output, CASES["S12"].scoring).passed is passed


def test_numeric_scorer_requires_unambiguous_number() -> None:
    assert score("17 x 23 = 391", CASES["S09"].scoring).passed is False  # several numbers
    assert score("391", CASES["S09"].scoring).passed is True


def test_json_scorer_accepts_code_fences_and_rejects_garbage() -> None:
    assert score('```json\n{"name": "Priya", "age": 34}\n```', CASES["S15"].scoring).passed
    assert score("not json", CASES["S15"].scoring).passed is False


def test_human_review_case_is_flagged() -> None:
    result = score(REFERENCE["C10"][0], CASES["C10"].scoring)
    assert result.details["needs_human_review"] is True and result.details["rubric"]


def test_statistics() -> None:
    low, high = wilson_interval(40, 45)  # type: ignore[misc]
    assert 0.76 < low < 0.80 and 0.94 < high < 0.97
    assert wilson_interval(0, 0) is None
    assert percentile([5, 1, 9, 3], 50) == 3
    pairs = [(1.0, 1.0)] * 30 + [(1.0, 0.0)] * 5 + [(0.0, 1.0)] * 5
    ci = paired_bootstrap(pairs, mean_difference, resamples=2000, seed=1)
    assert ci is not None and ci[0] < 0 < ci[1]
    assert ci == paired_bootstrap(pairs, mean_difference, resamples=2000, seed=1)  # reproducible
