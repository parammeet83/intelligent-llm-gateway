"""routewise_bench_v5: exact/strict scoring fixes, T03 exact keys, quota pacing, manifest schema 3.

Unchanged cases reuse v4's reference and adversarial answers. Each v5 correction has positive,
negative and adversarial answers, plus v4-vs-v5 evidence for every false pass it fixes. No model or
provider is called: pacing is tested with a fake clock, the adapter with a fake transport, the
runner with the mock provider, and the CLI stops before any network access.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.evaluation import manifest as manifest_mod
from app.evaluation import pacing as pacing_mod
from app.evaluation.dataset import (
    EVAL_ROOT,
    load_dataset,
    load_preregistration,
    preregistration_path,
)
from app.evaluation.pacing import GROQ_FREE_QUOTA, QuotaExhausted, QuotaPacer
from app.evaluation.scorers import score
from app.providers.base import ProviderError, RateLimitState
from app.providers.groq import GroqProvider
from app.providers.http import parse_duration_s, parse_rate_limit
from tests.evaluation.test_dataset_v4 import ADVERSARIAL as V4_ADVERSARIAL
from tests.evaluation.test_dataset_v4 import CARRIED as V4_CARRIED
from tests.evaluation.test_dataset_v4 import REFERENCE as V4_REFERENCE

V4 = load_dataset("routewise_bench_v4")
V5 = load_dataset("routewise_bench_v5")
CASES = {c.id: c for c in V5.cases}
V4_CASES = {c.id: c for c in V4.cases}
CHANGED = [
    "S01",
    "S03",
    "S04",
    "S09",
    "S10",
    "S14",
    "T03",
    "T09",
    "T10",
    "T11",
    "C03",
    "C08",
    "C09",
]

T03_OK = '{"start_time_utc": "09:12", "day": "Monday", "affected_feature": "checkout", "duration_minutes": 45, "root_cause": "disk_full", "alert_threshold_percent": 80}'

REFERENCE: dict[str, tuple[str, str]] = {
    **{cid: pair for cid, pair in V4_REFERENCE.items() if cid not in CHANGED},
    "S01": ("Positive", "Negative"),
    "S03": ("Dolphin", "Shark"),
    "S04": ("billing", "account"),
    "S14": ("Yes", "No"),
    "S09": ("391", "381"),
    "S10": ("0.9", "0.11"),
    "T09": ("14", "18"),
    "T11": ("33", "34"),
    "T10": ("Line 7 counts every number, not just positives.\nANSWER: 7", "ANSWER: 6"),
    "C03": ("2 + 3 + 3 + 3 = 11\nANSWER: 11", "ANSWER: 8"),
    "C08": ("2+3+5+7+11+13+17+19+23+29+31+37+41+43+47\nANSWER: 328", "ANSWER: 329"),
    "C09": ("1000 x 1.05^3 = 1157.625, rounded half up.\nANSWER: 1157.63", "ANSWER: 1157.62"),
    "T03": (T03_OK, T03_OK.replace('"duration_minutes": 45', '"duration_minutes": 54')),
}

ADVERSARIAL: list[tuple[str, str, bool, str]] = [
    # A. whole-answer exact matching (the four reported false positives first)
    ("S01", "Not positive", False, "negated label (v4 false pass)"),
    ("S01", "Positive.", True, "capitalised with full stop"),
    ("S01", "POSITIVE", True, "upper case"),
    ("S01", "`positive`", True, "backticks"),
    ("S01", "positive (not negative)", False, "extra words"),
    ("S01", "The sentiment is positive", False, "a sentence, not the label"),
    ("S03", "Not dolphin", False, "negated label (v4 false pass)"),
    ("S03", "dolphin.", True, "full stop"),
    ("S03", "Dolphin!", True, "exclamation mark"),
    ("S03", "Dolphin, not shark", False, "two labels"),
    ("S03", "a dolphin", False, "extra word (the prompt asks for the name only)"),
    ("S04", "Not billing", False, "negated label (v4 false pass)"),
    ("S04", "Billing.", True, "capitalised with full stop"),
    ("S04", "billing, not account", False, "extra words"),
    ("S04", "Category: billing", False, "prefix"),
    ("S14", "Not yes", False, "negated label (v4 false pass)"),
    ("S14", "Yes.", True, "full stop"),
    ("S14", "yes", True, "lower case"),
    (
        "S14",
        "Yes, about 99.97 °C, which is approximately 100 °C.",
        False,
        "elaboration (the prompt asks for yes or no)",
    ),
    ("S14", "No", False, "wrong"),
    # B. strict single numbers
    ("S09", "not 391", False, "negation (v4 false pass via last number)"),
    ("S09", "391.", True, "full stop"),
    ("S09", "17 x 23 = 391", False, "working shown (prompt: the number only)"),
    ("S09", "391 or 381", False, "contradictory numbers"),
    ("S09", "$391", False, "currency not allowed for a product"),
    ("S10", "Not 0.9", False, "negation (v4 false pass)"),
    ("S10", "0.90", True, "trailing zero"),
    ("S10", "0.9 is larger", False, "explanatory text"),
    ("S10", "0.9 > 0.11", False, "two numbers"),
    ("T09", "That is not 14", False, "negation (v4 false pass)"),
    ("T09", "14\n", True, "trailing newline"),
    ("T09", "8 + 6 = 14", False, "working shown"),
    ("T09", "$14", False, "currency not allowed for program output"),
    (
        "T11",
        "It is not 33, but final number is 33",
        False,
        "negation and prose (v4 false pass via last number)",
    ),
    ("T11", "$33", True, "dollar price"),
    ("T11", "$33.00", True, "dollar price with cents"),
    ("T11", "33 dollars", False, "unit word"),
    ("T11", "€33", False, "only $ is allowed"),
    ("T11", "40 x 0.75 = 30; 30 x 1.10 = 33", False, "working shown (prompt: the number only)"),
    ("T10", "ANSWER: $7", False, "currency on a line number (v4 false pass)"),
    ("T10", "ANSWER: 7", True, "plain"),
    ("C03", "ANSWER: $11", False, "currency on a program output"),
    ("C08", "ANSWER: $328", False, "currency on a sum of primes"),
    ("C08", "ANSWER: 328", True, "plain"),
    ("C09", "ANSWER: $1,157.63", True, "dollar amount"),
    ("C09", "ANSWER: €1,157.63", False, "only $ is allowed"),
    ("C09", "ANSWER: 1157.63 (rounded half up)", False, "strict final answer unchanged from v4"),
    # C. T03 exact keys and types
    ("T03", "```json\n" + T03_OK + "\n```", True, "fenced"),
    (
        "T03",
        '{"alert_threshold_percent": 80, "root_cause": "disk_full", "duration_minutes": 45, "affected_feature": "checkout", "day": "Monday", "start_time_utc": "09:12"}',
        True,
        "key order is irrelevant",
    ),
    ("T03", T03_OK.replace(', "alert_threshold_percent": 80', ""), False, "missing key"),
    (
        "T03",
        T03_OK.replace("80}", '80, "notes": "storage expanded"}'),
        False,
        "extra key (v4 false pass)",
    ),
    ("T03", T03_OK.replace('"disk_full"', '"network"'), False, "wrong value"),
    (
        "T03",
        T03_OK.replace('"duration_minutes": 45', '"duration_minutes": 45.0'),
        False,
        "integer field as a float",
    ),
    (
        "T03",
        T03_OK.replace('"duration_minutes": 45', '"duration_minutes": "45"'),
        False,
        "integer field as a string",
    ),
    ("T03", T03_OK.replace('"09:12"', "912"), False, "string field as a number"),
    ("T03", "[" + T03_OK + "]", False, "array instead of object"),
]

CARRIED = [a for a in V4_ADVERSARIAL + V4_CARRIED if a[0] not in CHANGED]


def test_earlier_versions_are_unchanged() -> None:
    assert V4.sha256 == "715830467f26d833142b073497f2f7fd47cca0f9fa11cc2f7feabc5773987016"
    assert load_dataset("routewise_bench_v3").sha256.startswith("c0c58c306cd1")
    assert load_dataset("routewise_bench_v2").sha256.startswith("614e14497b38")
    assert load_dataset("routewise_bench_v1").sha256.startswith("5b0107d18347")


def test_v5_size_balance_and_review_status() -> None:
    assert len(V5.cases) == 45
    assert Counter(c.difficulty for c in V5.cases) == {"simple": 15, "standard": 18, "complex": 12}
    assert V5.meta["status"] == "draft-pending-human-review" and V5.meta["reviewed_by"] == {}
    assert V5.fully_reviewed is False and V5.code_execution_cases == []


def test_only_scoring_of_the_listed_cases_differs_from_v4() -> None:
    changed = [c.id for c in V5.cases if c.model_dump() != V4_CASES[c.id].model_dump()]
    assert changed == CHANGED and V5.meta["changed_from_v4"] == CHANGED
    for c in V5.cases:
        assert c.model_dump(exclude={"scoring"}) == V4_CASES[c.id].model_dump(exclude={"scoring"})


def test_no_label_search_or_partial_number_scoring_remains() -> None:
    for c in V5.cases:
        assert c.scoring["method"] != "choice", c.id
        assert not c.scoring.get("last_number") and not c.scoring.get("first_number"), c.id
        if c.scoring.get("strict_number"):
            assert "currency_symbols" in c.scoring, c.id
    allowed = {c.id for c in V5.cases if c.scoring.get("currency_symbols")}
    assert allowed == {"T11", "C09"}  # the two dollar answers


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
        ("S01", "Not positive"),
        ("S03", "Not dolphin"),
        ("S04", "Not billing"),
        ("S14", "Not yes"),
        ("S09", "not 391"),
        ("S10", "Not 0.9"),
        ("T09", "That is not 14"),
        ("T11", "It is not 33, but final number is 33"),
        ("T10", "ANSWER: $7"),
        ("T03", T03_OK.replace("80}", '80, "notes": "x"}')),
    ],
)
def test_v4_false_passes_are_fixed_in_v5(case_id: str, answer: str) -> None:
    assert score(answer, V4_CASES[case_id].scoring).passed is True  # v4 accepted it
    assert score(answer, CASES[case_id].scoring).passed is False


def test_v4_strict_number_behaviour_is_unchanged_without_currency_symbols() -> None:
    # v4 specs don't set currency_symbols, so "$" stays accepted there (v4 is immutable).
    assert score("ANSWER: $7", V4_CASES["T10"].scoring).passed is True
    assert score("ANSWER: 7 (indentation)", V4_CASES["T10"].scoring).passed is False


# --- rate-limit headers -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("1m26.4s", 86.4),
        ("7.66s", 7.66),
        ("120ms", 0.12),
        ("2h", 7200.0),
        ("3", 3.0),
        ("", None),
        ("soon", None),
    ],
)
def test_parse_duration(value: str, seconds: float | None) -> None:
    got = parse_duration_s(value)
    assert got == pytest.approx(seconds) if seconds is not None else got is None


def test_parse_rate_limit_headers() -> None:
    headers = httpx.Headers(
        {
            "x-ratelimit-limit-requests": "1000",
            "x-ratelimit-remaining-requests": "999",
            "x-ratelimit-reset-requests": "1m26.4s",
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-tokens": "7789",
            "x-ratelimit-reset-tokens": "1.582s",
        }
    )
    state = parse_rate_limit(headers, "openai/gpt-oss-20b")
    assert state is not None
    assert (
        state.limit_requests,
        state.remaining_requests,
        state.limit_tokens,
        state.remaining_tokens,
    ) == (1000, 999, 8000, 7789)
    assert state.reset_tokens_s == pytest.approx(1.582) and state.reset_requests_s == pytest.approx(
        86.4
    )
    assert parse_rate_limit(httpx.Headers({"content-type": "application/json"}), "m") is None


async def test_adapter_records_rate_limit_headers_on_success_and_on_429() -> None:
    from tests.providers.fakes import Recorder, completion, groq, json_response, request

    ok = json_response(
        200,
        completion(),
        {"x-ratelimit-remaining-tokens": "5000", "x-ratelimit-limit-tokens": "8000"},
    )
    provider = groq(Recorder(ok))
    await provider.generate(request("openai/gpt-oss-20b"))
    assert (
        provider.last_rate_limit is not None and provider.last_rate_limit.remaining_tokens == 5000
    )

    limited = json_response(
        429,
        {"error": {"message": "rate limit"}},
        {"retry-after": "3", "x-ratelimit-remaining-tokens": "0"},
    )
    provider = groq(Recorder(limited))
    with pytest.raises(ProviderError):
        await provider.generate(request("openai/gpt-oss-20b"))
    assert provider.last_rate_limit is not None and provider.last_rate_limit.remaining_tokens == 0


# --- quota pacer (fake clock; nothing waits for real) -----------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _pacer(**overrides: Any) -> tuple[QuotaPacer, FakeClock]:
    clock = FakeClock()
    return QuotaPacer({**GROQ_FREE_QUOTA, **overrides}, clock=clock, sleep=clock.sleep), clock


async def test_pacer_allows_calls_within_the_token_budget() -> None:
    pacer, clock = _pacer()
    await pacer.acquire(2000)
    await pacer.acquire(2000)
    assert clock.sleeps == []  # 4000 <= 8000 * 0.75


async def test_pacer_waits_for_the_token_window_to_free_up() -> None:
    pacer, clock = _pacer()
    for _ in range(3):
        await pacer.acquire(2500)  # third call: 7500 > 6000 budget
    assert clock.sleeps == [pytest.approx(60.0)]


async def test_pacer_limits_requests_per_minute() -> None:
    pacer, clock = _pacer()
    for _ in range(23):
        await pacer.acquire(10)  # 30 * 0.75 = 22.5 calls per minute
    assert len(clock.sleeps) == 1


async def test_headers_can_only_make_pacing_stricter() -> None:
    lower, clock = _pacer()
    lower.record(
        calls=1,
        reserved_tokens=0,
        reported_tokens=0,
        headers=[RateLimitState("m", clock.now, limit_tokens=4000)],
    )
    await lower.acquire(2000)
    await lower.acquire(2000)  # 4000 > 4000 * 0.75 = 3000: must wait
    assert clock.sleeps

    higher, clock2 = _pacer()
    higher.record(
        calls=1,
        reserved_tokens=0,
        reported_tokens=0,
        headers=[RateLimitState("m", clock2.now, limit_tokens=80000)],
    )
    for _ in range(3):
        await higher.acquire(2500)  # still capped by the pinned 8000
    assert clock2.sleeps


async def test_pacer_waits_for_the_reported_token_reset() -> None:
    pacer, clock = _pacer()
    pacer.record(
        calls=1,
        reserved_tokens=0,
        reported_tokens=0,
        headers=[RateLimitState("m", clock.now, remaining_tokens=100, reset_tokens_s=12.5)],
    )
    await pacer.acquire(1000)
    assert clock.sleeps == [pytest.approx(12.5)]


async def test_pacer_stops_instead_of_exceeding_daily_limits() -> None:
    pacer, _ = _pacer()
    pacer.day_requests = 900  # 1000 * 0.9
    with pytest.raises(QuotaExhausted, match="daily budget"):
        await pacer.acquire(100)
    pacer, clock = _pacer()
    pacer.record(
        calls=1,
        reserved_tokens=0,
        reported_tokens=0,
        headers=[RateLimitState("m", clock.now, limit_requests=1000, remaining_requests=50)],
    )
    with pytest.raises(QuotaExhausted, match="requests left today"):
        await pacer.acquire(100)
    pacer, _ = _pacer()
    with pytest.raises(QuotaExhausted, match="above the"):
        await pacer.acquire(7000)  # a single call larger than the per-minute budget


def test_pacer_accounting_never_treats_unknown_usage_as_zero() -> None:
    pacer, _ = _pacer()
    pacer.record(calls=1, reserved_tokens=900, reported_tokens=300, headers=[])
    assert (pacer.day_requests, pacer.day_tokens) == (0, 300)  # acquire() counts the first call
    pacer.record(calls=2, reserved_tokens=900, reported_tokens=300, headers=[])  # a retry happened
    assert (pacer.day_requests, pacer.day_tokens) == (1, 300 + 1800)
    pacer.record(calls=1, reserved_tokens=900, reported_tokens=None, headers=[])  # usage unknown
    assert pacer.day_tokens == 300 + 1800 + 900


def test_worst_case_reserves_the_full_output_budget() -> None:
    pacer, _ = _pacer()
    assert pacer.worst_case_tokens("x" * 400, 2048) >= 2048 + 100


async def test_runner_stops_incomplete_instead_of_exceeding_the_quota(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Edited in v5.1: v5's schema-3 quota (one reservation per gateway request) was superseded.
    The runner now refuses it outright instead of running with unreserved retries/fallbacks;
    per-attempt behaviour is tested in test_execution_v5_1.py."""
    from app.db.session import Database
    from app.evaluation import runner
    from app.providers.mock import MockProvider
    from tests.conftest import make_settings

    v1 = load_dataset("routewise_bench_v1")
    prereg, sha = load_preregistration(preregistration_path(v1.name), dataset=v1)
    prereg = {**prereg, "experiment_manifest": {"file": "test", "sha256": "test"}}
    tiny = {**GROQ_FREE_QUOTA, "requests_per_day": 5, "per_day_safety": 1.0}
    fake_manifest = {"pinned": {"expected_models": [], "execution": {"quota": {"mock": tiny}}}}
    monkeypatch.setattr(runner, "load_preregistration", lambda *a, **k: (prereg, sha))
    monkeypatch.setattr(manifest_mod, "check_manifest", lambda *a, **k: fake_manifest)

    clock = FakeClock()
    db = Database(database_url)
    try:
        with pytest.raises(ValueError, match=r"superseded in v5\.1"):
            await runner.run_benchmark(
                settings=make_settings(database_url),
                db=db,
                providers={"mock": MockProvider()},
                dataset=v1,
                strategies=["baseline_premium", "routewise"],
                label="pytest-quota",
                limit_cases=10,
                sleep=clock.sleep,
            )
    finally:
        await db.dispose()


# --- pre-registration and manifest (schema 3) ------------------------------------------------------


def _prereg() -> dict[str, Any]:
    prereg, _ = load_preregistration(preregistration_path("routewise_bench_v5"), dataset=V5)
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


@pytest.fixture(autouse=True)
def _no_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)


def test_v5_preregistration_chain() -> None:
    prereg, sha = load_preregistration(preregistration_path("routewise_bench_v5"), dataset=V5)
    assert prereg["dataset_sha256"] == V5.sha256 and V5.meta["preregistration_sha256"] == sha
    manifest, msha = manifest_mod.load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])
    assert msha == prereg["experiment_manifest"]["sha256"]
    assert manifest["schema"] == 3 and manifest["dataset_sha256"] == V5.sha256
    assert manifest["pinned"]["execution"]["quota"] == {"groq": GROQ_FREE_QUOTA}
    assert prereg["quota"]["tokens_per_minute"] == GROQ_FREE_QUOTA["tokens_per_minute"]


def test_v5_manifest_matches_the_intended_configuration() -> None:
    """Edited in v5.1: v5.1 changed execution code that v5 pinned, so v5 is correctly unrunnable
    on current code; every non-code field still matches v5's intended configuration."""
    manifest, _ = manifest_mod.load_manifest(EVAL_ROOT / _prereg()["experiment_manifest"]["file"])
    actual = manifest_mod.build_manifest(
        _intended(), _groq(), STRATEGIES_ALL, schema=3, run_params=PACING
    )
    differences = manifest_mod.diff(manifest["pinned"], actual)
    assert differences and all(
        d.startswith("files.") and d.endswith(".sha256") for d in differences
    ), differences
    with pytest.raises(ValueError, match="configuration differs"):
        manifest_mod.check_manifest(
            _prereg(), _intended(), _groq(), STRATEGIES_ALL, run_params=PACING
        )
    files = manifest["pinned"]["files"]
    assert {"cli", "quota_pacing", "error_types", "dependency_lock"} <= set(files)
    assert files["cli"]["path"] == "backend/app/cli.py"
    assert manifest["pinned"]["execution"]["runtime"]["network_env_present"] == {
        n: False for n in manifest_mod.NETWORK_ENV
    }


@pytest.mark.parametrize(
    ("change", "where"),
    [
        ({"delay_s": 2.0}, "execution.pacing.delay_s"),
        ({"limit_cases": 5}, "execution.pacing.limit_cases"),
    ],
)
def test_v5_manifest_refuses_different_pacing(change: dict[str, Any], where: str) -> None:
    actual = manifest_mod.build_manifest(
        _intended(), _groq(), STRATEGIES_ALL, schema=3, run_params={**PACING, **change}
    )
    pinned, _ = manifest_mod.load_manifest(EVAL_ROOT / _prereg()["experiment_manifest"]["file"])
    assert where in manifest_mod.diff(pinned["pinned"], actual)


def test_v5_manifest_detects_quota_and_proxy_and_cli_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pinned, _ = manifest_mod.load_manifest(EVAL_ROOT / _prereg()["experiment_manifest"]["file"])

    def diffs() -> list[str]:
        actual = manifest_mod.build_manifest(
            _intended(), _groq(), STRATEGIES_ALL, schema=3, run_params=PACING
        )
        return manifest_mod.diff(pinned["pinned"], actual)

    # Edited in v5.1: superseded code hashes are the only baseline differences now.
    baseline = set(diffs())
    assert all(d.startswith("files.") and d.endswith(".sha256") for d in baseline)
    monkeypatch.setitem(pacing_mod.GROQ_FREE_QUOTA, "tokens_per_minute", 16000)
    assert "execution.quota.groq.tokens_per_minute" in diffs()
    monkeypatch.setitem(pacing_mod.GROQ_FREE_QUOTA, "tokens_per_minute", 8000)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    assert "execution.runtime.network_env_present.HTTPS_PROXY" in diffs()
    monkeypatch.delenv("HTTPS_PROXY")
    edited = tmp_path / "cli.py"
    edited.write_text(
        manifest_mod.CODE_FILES_V3["cli"].read_text(encoding="utf-8") + "\n# edit\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(manifest_mod.CODE_FILES_V3, "cli", edited)
    assert "files.cli.sha256" in diffs()


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
        ["eval-run", "--dataset", "routewise_bench_v5", "--label", "pytest", "--delay-s", "2"]
    )
    assert code == 2
    assert "execution.pacing.delay_s" in capsys.readouterr().err


def test_eval_validate_prints_the_quota_preflight(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app import cli
    from app.providers import registry

    """Edited in v5.1: v5 is superseded, so eval-validate now reports the manifest mismatch and
    exits non-zero; the v5.1 preflight is tested in test_execution_v5_1.py."""
    monkeypatch.setattr(cli, "get_settings", lambda: _intended())
    monkeypatch.setattr(registry, "build_providers", lambda settings: _groq())
    assert cli.main(["eval-validate", "--dataset", "routewise_bench_v5"]) == 1
    out = capsys.readouterr().out
    assert "experiment manifest: DOES NOT MATCH" in out
    json.dumps(out)  # printable, no secrets involved
