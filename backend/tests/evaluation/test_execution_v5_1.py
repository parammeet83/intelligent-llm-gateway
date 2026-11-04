"""Execution revision routewise_bench_v5.1: per-attempt quota safety, preflight, daily budget.

Self-contained (no imports from other test modules) so it runs from the clean-room review bundle.
No provider is called: attempts go through MockProvider (or tiny fakes) behind PacedProvider, the
executor and the runner use mock providers on a scratch database, and the CLI tests stop before
any network access. Time is faked; nothing sleeps for real.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.core.config import BACKEND_ROOT, Settings
from app.evaluation import manifest as manifest_mod
from app.evaluation import preflight
from app.evaluation.dataset import (
    EVAL_ROOT,
    load_dataset,
    load_execution_revision,
    load_preregistration,
    preregistration_path,
)
from app.evaluation.pacing import (
    GROQ_QUOTA_V5_1,
    AttemptPacer,
    DailyBudget,
    PacedProvider,
    QuotaLedger,
    input_token_bound,
)
from app.providers.base import (
    ChatMessage,
    Provider,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
    RateLimitState,
)
from app.providers.groq import GroqProvider
from app.providers.mock import MockProvider

REVISION = "routewise_bench_v5.1"
V5 = load_dataset("routewise_bench_v5")
V5_SHA = "76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd"
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
E = ProviderErrorKind


# --- helpers ----------------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.mono = 1000.0
        self.wall = NOW
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.mono

    def now(self) -> datetime:
        return self.wall

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)


def budget(
    remaining: int = 1_000_000, *, verified_at: datetime = NOW - timedelta(hours=1)
) -> DailyBudget:
    return DailyBudget(remaining, verified_at, "operator check of the Groq console (test)")


def make_pacer(
    tmp_path: Path,
    *,
    remaining: int = 1_000_000,
    quota: dict[str, Any] | None = None,
    ledger_name: str = "ledger.json",
) -> tuple[AttemptPacer, FakeClock]:
    clock = FakeClock()
    pacer = AttemptPacer(
        quota or GROQ_QUOTA_V5_1,
        budget(remaining),
        QuotaLedger(tmp_path / ledger_name, "groq"),
        clock=clock,
        now=clock.now,
        sleep=clock.sleep,
    )
    return pacer, clock


def request(model: str = "m", prompt: str = "hello", max_out: int = 100) -> ProviderRequest:
    return ProviderRequest(
        model_id=model,
        messages=(ChatMessage(role="user", content=prompt),),
        max_output_tokens=max_out,
    )


class RecordingProvider(Provider):
    """Records, at the moment of 'transmission', how many reservations the ledger holds."""

    name = "groq"

    def __init__(self, pacer: AttemptPacer, outcomes: list[Any]) -> None:
        self.pacer = pacer
        self.outcomes = list(outcomes)
        self.reservations_at_send: list[int] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.reservations_at_send.append(len(self.pacer.ledger.entries))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ProviderError):
            raise outcome
        return ProviderResponse(
            content="ok",
            provider="groq",
            model_id=request.model_id,
            usage=outcome,
            latency_ms=5,
            simulated=False,
        )


def err(
    kind: ProviderErrorKind, *, sent: bool = True, usage: ProviderUsage | None = None
) -> ProviderError:
    return ProviderError(kind=kind, message=kind.value, provider="groq", sent=sent, usage=usage)


# --- 1-5: per-attempt reservation in the provider wrapper -----------------------------------------


async def test_initial_attempt_reserves_before_transmission(tmp_path: Path) -> None:
    pacer, _ = make_pacer(tmp_path)
    inner = RecordingProvider(pacer, [ProviderUsage(10, 20)])
    await PacedProvider(inner, pacer).generate(request())
    assert inner.reservations_at_send == [1]  # the reservation existed when the call was made
    (entry,) = pacer.ledger.entries
    assert entry["kind"] == "sent_reported_usage" and entry["tokens"] == 30


def _executor(providers: dict[str, Provider]) -> Any:
    from app.resilience.health import HealthRegistry
    from app.services.executor import Executor

    async def no_sleep(_: float) -> None:
        return None

    return Executor(
        providers,
        HealthRegistry(failure_threshold=5, open_s=30),
        deadline_s=600,
        default_timeout_s=30,
        backoff_base_s=0.0,
        backoff_cap_s=1.0,
        sleep=no_sleep,
    )


def _decision(models: list[Any]) -> Any:
    from app.routing.config import load_policy
    from app.routing.engine import RoutingRequest, route

    class NoHealth:
        def exclusion(self, provider: str, model_id: str) -> None:
            return None

        def p95_ms(self, provider: str, model_id: str, min_samples: int) -> None:
            return None

    return route(
        RoutingRequest(
            messages=(ChatMessage(role="user", content="Is this positive?"),),
            task_type="classification",
            max_output_tokens=64,
        ),
        models=models,
        enabled_providers=frozenset({"mock"}),
        simulated_providers=frozenset({"mock"}),
        policy=load_policy(BACKEND_ROOT / "config" / "routing_policy.yaml"),
        health=NoHealth(),
    )


def _mock_models() -> tuple[list[Any], dict[str, Any]]:
    from app.providers.catalog import load_catalog

    models = [
        m
        for m in load_catalog(BACKEND_ROOT / "config" / "models.yaml").models
        if m.provider == "mock"
    ]
    return models, {m.key: m for m in models}


def _paced_mock(
    tmp_path: Path, remaining: int = 1_000_000
) -> tuple[MockProvider, PacedProvider, AttemptPacer]:
    clock = FakeClock()
    pacer = AttemptPacer(
        GROQ_QUOTA_V5_1,
        budget(remaining),
        QuotaLedger(tmp_path / "l.json", "mock"),
        clock=clock,
        now=clock.now,
        sleep=clock.sleep,
    )
    inner = MockProvider()
    return inner, PacedProvider(inner, pacer), pacer


async def test_retry_obtains_a_separate_reservation(tmp_path: Path) -> None:
    models, by_key = _mock_models()
    decision = _decision(models)
    first = decision.eligible[0].model_id
    inner, paced, pacer = _paced_mock(tmp_path)
    inner.script(first, [MockProvider.error(E.TIMEOUT)])  # retryable: same model again
    result = await _executor({"mock": paced}).run(decision, by_key, request(first))
    assert [a.status for a in result.attempts] == ["timeout", "succeeded"]
    assert pacer.attempts == 2 and len(inner.calls) == 2
    ids = [e["id"] for e in pacer.ledger.entries]
    assert len(ids) == 2 and len(set(ids)) == 2  # two distinct reservations
    assert {e["model"] for e in pacer.ledger.entries} == {first}


async def test_fallback_obtains_a_separate_reservation(tmp_path: Path) -> None:
    models, by_key = _mock_models()
    decision = _decision(models)
    first = decision.eligible[0].model_id
    inner, paced, pacer = _paced_mock(tmp_path)
    inner.script(first, [MockProvider.error(E.RATE_LIMITED)])  # never retried: falls back
    result = await _executor({"mock": paced}).run(decision, by_key, request(first))
    assert len(result.attempts) == 2 and result.attempts[0].model_id != result.attempts[1].model_id
    assert pacer.attempts == 2
    assert [e["model"] for e in pacer.ledger.entries] == [a.model_id for a in result.attempts]


async def test_second_attempt_is_blocked_when_quota_is_exhausted(tmp_path: Path) -> None:
    models, by_key = _mock_models()
    decision = _decision(models)
    first = decision.eligible[0].model_id
    one_attempt = input_token_bound(["Is this positive?"], 256) + 64
    # Room for exactly one attempt (0.9 safety).
    inner, paced, pacer = _paced_mock(tmp_path, remaining=int((one_attempt + 1) / 0.9) + 1)
    inner.script(first, [MockProvider.error(E.TIMEOUT)])
    result = await _executor({"mock": paced}).run(
        decision,
        by_key,
        ProviderRequest(
            model_id=first,
            messages=(ChatMessage(role="user", content="Is this positive?"),),
            max_output_tokens=64,
        ),
    )
    assert len(inner.calls) == 1  # the retry and every fallback were blocked before sending
    assert pacer.exhausted is not None and "daily token budget" in pacer.exhausted
    assert result.response is None
    assert all(s["reason"] in ("QUOTA_EXHAUSTED",) for s in result.skipped)


async def test_unknown_usage_is_not_treated_as_zero(tmp_path: Path) -> None:
    pacer, _ = make_pacer(tmp_path)
    worst = input_token_bound(["hello"], 256) + 100
    inner = RecordingProvider(pacer, [err(E.TIMEOUT, sent=True)])
    with pytest.raises(ProviderError):
        await PacedProvider(inner, pacer).generate(request())
    (entry,) = pacer.ledger.entries
    assert entry["tokens"] == worst and entry["kind"] == "sent_usage_unknown_worst_case_kept"
    # Refused locally before sending: known zero, so the reservation is released.
    pacer2, _ = make_pacer(tmp_path, ledger_name="l2.json")
    inner2 = RecordingProvider(pacer2, [err(E.QUOTA_EXHAUSTED, sent=False)])
    with pytest.raises(ProviderError):
        await PacedProvider(inner2, pacer2).generate(request())
    assert pacer2.ledger.entries == [] and pacer2.attempts == 0


async def test_reported_usage_above_the_bound_stops_the_run(tmp_path: Path) -> None:
    pacer, _ = make_pacer(tmp_path)
    inner = RecordingProvider(pacer, [ProviderUsage(100_000, 5)])  # impossible under the bound
    await PacedProvider(inner, pacer).generate(request())
    assert pacer.exhausted is not None and "exceeded the reserved bound" in pacer.exhausted
    assert pacer.ledger.entries[0]["tokens"] == 100_005  # true usage is recorded, not the bound


# --- 6: preflight counts retries and fallbacks ----------------------------------------------------


def _intended(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "groq_enabled": True,
        "groq_api_key": "test-placeholder-key-0000000000000000",
        "groq_billing_plan": "free",
        "mock_provider_enabled": False,
        **overrides,
    }
    return Settings(_env_file=None, **values)


def _groq(max_retries: int | None = None) -> dict[str, Any]:
    provider = GroqProvider(api_key="test-placeholder", charge_basis="free_tier")
    if max_retries is not None:
        provider.max_retries = max_retries
    return {"groq": provider}


STRATEGIES = ["baseline_premium", "routewise", "routewise_tier_first"]


def test_preflight_counts_maximum_retries_and_fallbacks() -> None:
    pre = preflight.plan(V5, STRATEGIES, _intended(), _groq(), GROQ_QUOTA_V5_1)
    assert pre.bounded and pre.gateway_requests == 135
    # Independent recomputation: each eligible model allows 1 + max_retries (1) attempts.
    from app.evaluation.runner import STRATEGIES as DEFS
    from app.providers.catalog import load_catalog
    from app.routing.config import load_policy
    from app.routing.engine import RoutingRequest, route

    models = [
        m
        for m in load_catalog(BACKEND_ROOT / "config" / "models.yaml").models
        if m.enabled and m.provider == "groq"
    ]
    expected = 0
    for name in STRATEGIES:
        policy = load_policy(BACKEND_ROOT / "config" / "routing_policy.yaml").model_copy(
            update=DEFS[name][0]
        )
        for c in V5.cases:
            d = route(
                RoutingRequest(
                    messages=(ChatMessage(role="user", content=c.prompt),),
                    task_type=c.task_type,
                    max_output_tokens=c.max_output_tokens,
                    response_format=c.response_format,
                    **DEFS[name][1],
                ),
                models=models,
                enabled_providers=frozenset({"groq"}),
                simulated_providers=frozenset(),
                policy=policy,
                health=preflight._NoHealth(),
            )
            expected += 2 * len(d.eligible)
    assert pre.max_provider_attempts == expected
    assert pre.max_provider_attempts > pre.gateway_requests  # never labelled as 135 calls
    assert pre.max_attempts_per_request == 4  # small tier: 20b (+1 retry) then 120b (+1 retry)
    # More retries -> more attempts; unbounded retries -> refused.
    assert (
        preflight.plan(V5, STRATEGIES, _intended(), _groq(2), GROQ_QUOTA_V5_1).max_provider_attempts
        > expected
    )
    unbounded = preflight.plan(V5, STRATEGIES, _intended(), _groq(10_000), GROQ_QUOTA_V5_1)
    assert not unbounded.bounded and not unbounded.ok


# --- 7-9: daily budget ----------------------------------------------------------------------------


def _evaluate(tmp_path: Path, b: DailyBudget | None, **kw: Any) -> preflight.Preflight:
    pre = preflight.plan(V5, STRATEGIES, _intended(), _groq(), GROQ_QUOTA_V5_1)
    return preflight.evaluate(
        pre, GROQ_QUOTA_V5_1, b, QuotaLedger(tmp_path / "pre.json", "groq"), now=NOW, **kw
    )


def test_preflight_fails_when_the_daily_budget_is_unverified(tmp_path: Path) -> None:
    assert not _evaluate(tmp_path, None).ok
    stale = budget(10**9, verified_at=NOW - timedelta(days=1))
    assert any("not verified today" in p for p in _evaluate(tmp_path, stale).problems)
    assert any(
        "timezone" in p
        for p in _evaluate(tmp_path, DailyBudget(10**9, datetime(2026, 11, 5, 9), "x")).problems
    )
    assert any("source" in p for p in _evaluate(tmp_path, DailyBudget(10**9, NOW, " ")).problems)
    assert _evaluate(tmp_path, budget(10**9)).ok


def test_preflight_fails_closed_or_warns_when_the_worst_case_does_not_fit(tmp_path: Path) -> None:
    small = budget(50_000)
    assert any("exceeds the usable daily" in p for p in _evaluate(tmp_path, small).problems)
    accepted = _evaluate(tmp_path, small, accept_incomplete_risk=True)
    assert accepted.ok and accepted.warnings


async def test_prior_daily_usage_reduces_the_remaining_budget(tmp_path: Path) -> None:
    ledger_path = tmp_path / "shared.json"
    first, clock = make_pacer(tmp_path, ledger_name="shared.json")
    first.ledger.add(
        {
            "id": "prior",
            "at": (NOW - timedelta(minutes=30)).isoformat(),
            "model": "m",
            "tokens": 40_000,
            "kind": "sent_reported_usage",
        }
    )
    pre = _evaluate(tmp_path, budget(100_000), accept_incomplete_risk=True)
    usable_without = pre.constraints["usable_daily_tokens"]
    restarted = QuotaLedger(ledger_path, "groq")  # a restart re-reads the ledger
    pre2 = preflight.evaluate(
        preflight.plan(V5, STRATEGIES, _intended(), _groq(), GROQ_QUOTA_V5_1),
        GROQ_QUOTA_V5_1,
        budget(100_000),
        restarted,
        now=NOW,
        accept_incomplete_risk=True,
    )
    assert pre2.constraints["usable_daily_tokens"] == usable_without - 40_000
    # Operator-supplied limit and prior usage.
    b = DailyBudget.from_limit_and_usage(
        limit=500_000, used=120_000, verified_at=NOW, source="console"
    )
    assert b.remaining_tokens == 380_000
    # A new pacer on the same ledger can't spend the prior usage again.
    pacer = AttemptPacer(
        GROQ_QUOTA_V5_1, budget(50_000), restarted, clock=clock, now=clock.now, sleep=clock.sleep
    )
    with pytest.raises(Exception, match="daily token budget"):
        await pacer.reserve("m", 4000, 2000)  # 40,000 + 6,000 > 45,000 usable


async def test_rate_limit_headers_tighten_available_capacity(tmp_path: Path) -> None:
    pacer, clock = make_pacer(tmp_path)
    pacer.observe(RateLimitState("m", clock(), limit_tokens=4000))  # 4000 x 0.75 = 3000/min
    with pytest.raises(Exception, match="above the 3000/min budget"):
        await pacer.reserve("m", 2000, 1500)
    pacer2, clock2 = make_pacer(tmp_path, ledger_name="b.json")
    pacer2.observe(RateLimitState("m", clock2(), remaining_tokens=100, reset_tokens_s=7.0))
    await pacer2.reserve("m", 500, 500)
    assert clock2.sleeps == [pytest.approx(7.0)]
    pacer3, clock3 = make_pacer(tmp_path, ledger_name="c.json")
    pacer3.observe(RateLimitState("m", clock3(), limit_requests=1000, remaining_requests=40))
    with pytest.raises(Exception, match="requests left today"):
        await pacer3.reserve("m", 10, 10)
    pacer4, clock4 = make_pacer(tmp_path, ledger_name="d.json")
    pacer4.observe(
        RateLimitState("m", clock4(), limit_tokens=80_000)
    )  # can't loosen the pinned 8000
    with pytest.raises(Exception, match="above the 6000/min budget"):
        await pacer4.reserve("m", 4000, 2500)


# --- 10: the run can't complete over budget ---------------------------------------------------------


async def _run(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    remaining: int,
    *,
    accept: bool = True,
    cases: int = 6,
) -> Any:
    from app.db.session import Database
    from app.evaluation import runner
    from tests.conftest import make_settings

    v1 = load_dataset("routewise_bench_v1")
    prereg, sha = load_preregistration(preregistration_path(v1.name), dataset=v1)
    prereg = {**prereg, "experiment_manifest": {"file": "test", "sha256": "test"}}
    fake = {
        "pinned": {"expected_models": [], "execution": {"attempt_quota": {"mock": GROQ_QUOTA_V5_1}}}
    }
    monkeypatch.setattr(runner, "load_preregistration", lambda *a, **k: (prereg, sha))
    monkeypatch.setattr(manifest_mod, "check_manifest", lambda *a, **k: fake)
    clock = FakeClock()
    db = Database(database_url)
    try:
        return await runner.run_benchmark(
            settings=make_settings(database_url),
            db=db,
            providers={"mock": MockProvider()},
            dataset=v1,
            strategies=["baseline_premium", "routewise"],
            label="pytest-v51",
            limit_cases=cases,
            sleep=clock.sleep,
            daily_budget=DailyBudget(remaining, datetime.now(UTC) - timedelta(minutes=1), "test"),
            ledger_path=tmp_path / "run.json",
            accept_incomplete_risk=accept,
        ), QuotaLedger(tmp_path / "run.json", "mock")
    finally:
        await db.dispose()


async def test_last_request_cannot_complete_the_run_over_budget(
    database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 1,500 x 0.9 = 1,350 usable: each attempt reserves ~900 worst case and settles to ~50 actual,
    # so a later attempt's worst case no longer fits and is refused before it is sent.
    result, ledger = await _run(database_url, monkeypatch, tmp_path, remaining=1_500)
    assert result.incomplete is True  # stopped by the quota guard, never "completed"
    assert len(result.outcomes) < 12
    used = ledger.tokens_since(datetime.now(UTC) - timedelta(hours=1))
    assert used <= 1_500 * 0.9  # never over budget
    assert result.config_snapshot["quota"]["stop_reason"]


async def test_a_run_that_fits_completes_within_budget(
    database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, ledger = await _run(database_url, monkeypatch, tmp_path, remaining=10_000_000, cases=3)
    assert result.incomplete is False and len(result.outcomes) == 6
    assert result.config_snapshot["quota"]["stop_reason"] is None
    assert result.config_snapshot["quota"]["attempts_reserved"] == len(ledger.entries) >= 6


async def test_run_refuses_without_a_budget_or_when_the_worst_case_does_not_fit(
    database_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="quota preflight failed"):
        await _run(database_url, monkeypatch, tmp_path, remaining=1_000, accept=False)


# --- 11: CLI exit codes and fail-closed preflight ---------------------------------------------


@pytest.fixture
def intended_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import cli
    from app.providers import registry

    async def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no network call may happen in these tests")

    for name in manifest_mod.NETWORK_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cli, "get_settings", lambda: _intended())
    monkeypatch.setattr(registry, "build_providers", lambda settings: _groq())
    monkeypatch.setattr(registry, "refresh_catalogs", no_network)


def _validate(*extra: str) -> int:
    from app import cli

    return cli.main(
        ["eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION, *extra]
    )


def test_manifest_mismatch_returns_a_nonzero_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    from app import cli
    from app.providers import registry

    monkeypatch.setattr(cli, "get_settings", lambda: _intended(mock_provider_enabled=True))
    monkeypatch.setattr(
        registry, "build_providers", lambda settings: {**_groq(), "mock": MockProvider()}
    )
    assert _validate() == 1
    assert "DOES NOT MATCH" in capsys.readouterr().out


def test_eval_validate_fails_closed_without_a_daily_budget(intended_cli: None, capsys: Any) -> None:
    assert _validate() == 1
    out = capsys.readouterr().out
    assert "experiment_manifest_routewise_bench_v5.1.yaml: matches" in out
    assert "UNVERIFIED" in out and "preflight: FAILED (fail closed)" in out
    assert "gateway requests: 135" in out and "maximum provider attempts:" in out


def test_eval_validate_passes_with_a_verified_budget(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    now = datetime.now(UTC).isoformat()
    assert (
        _validate(
            "--remaining-daily-tokens",
            "100000000",
            "--daily-budget-source",
            "test",
            "--daily-budget-verified-at",
            now,
            "--ledger",
            str(tmp_path / "ledger.json"),
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "usable_daily_tokens" in out and "preflight: OK" in out


def test_eval_run_refuses_before_any_network_call_without_a_budget(
    intended_cli: None, capsys: Any
) -> None:
    from app import cli

    code = cli.main(
        [
            "eval-run",
            "--dataset",
            "routewise_bench_v5",
            "--revision",
            REVISION,
            "--label",
            "t",
            "--delay-s",
            "6",
        ]
    )
    assert code == 2
    assert "quota preflight failed" in capsys.readouterr().err


def test_v5_without_the_revision_is_refused(intended_cli: None, capsys: Any) -> None:
    from app import cli

    assert (
        cli.main(["eval-run", "--dataset", "routewise_bench_v5", "--label", "t", "--delay-s", "6"])
        == 2
    )
    assert "configuration differs" in capsys.readouterr().err


# --- revision chain and manifest completeness ---------------------------------------------------


def test_v5_artefacts_are_unchanged_and_the_v5_1_chain_holds() -> None:
    import hashlib

    assert V5.sha256 == V5_SHA
    prereg_path, pinned = load_execution_revision(REVISION, V5)
    prereg, sha = load_preregistration(prereg_path, dataset=V5, pinned_sha256=pinned)
    assert sha == pinned and prereg["revision"] == REVISION and prereg["dataset_sha256"] == V5_SHA
    raw = (EVAL_ROOT / prereg["experiment_manifest"]["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == prereg["experiment_manifest"]["sha256"]
    manifest = manifest_mod.load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])[0]
    assert manifest["schema"] == 4
    assert manifest["pinned"]["execution"]["attempt_quota"] == {"groq": GROQ_QUOTA_V5_1}
    assert GROQ_QUOTA_V5_1["tokens_per_day"] is None  # no unverified daily limit
    # The v5 pre-registration still loads through the immutable meta pin (and is refused at run time).
    load_preregistration(preregistration_path("routewise_bench_v5"), dataset=V5)


def test_v5_1_manifest_matches_the_intended_configuration(intended_cli: None) -> None:
    prereg_path, pinned = load_execution_revision(REVISION, V5)
    prereg, _ = load_preregistration(prereg_path, dataset=V5, pinned_sha256=pinned)
    pacing = {"concurrency": 1, "delay_s": 6.0, "limit_cases": None, "allow_code_exec": False}
    assert manifest_mod.check_manifest(prereg, _intended(), _groq(), STRATEGIES, run_params=pacing)


def test_manifest_pins_the_whole_execution_import_closure() -> None:
    script = (
        "import importlib, json, pathlib, sys\n"
        "for m in ('app.cli','app.evaluation.runner','app.evaluation.preflight','app.evaluation.manifest',"
        "'app.evaluation.report','app.providers.registry'):\n"
        "    importlib.import_module(m)\n"
        "root = pathlib.Path('app').resolve()\n"
        "print(json.dumps(sorted({pathlib.Path(x.__file__).resolve().relative_to(root).as_posix() for x in list(sys.modules.values())"
        " if getattr(x, '__file__', None) and pathlib.Path(x.__file__).resolve().is_relative_to(root)})))\n"
    )
    # Our own fixed script, run with the current interpreter (no untrusted input).
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], cwd=BACKEND_ROOT, capture_output=True, text=True, check=True
    )
    closure = set(json.loads(out.stdout))
    assert closure <= set(manifest_mod.EXECUTION_MODULES_V4), sorted(
        closure - set(manifest_mod.EXECUTION_MODULES_V4)
    )
    assert "core/logging.py" in manifest_mod.EXECUTION_MODULES_V4


def test_no_decimal_regression_in_cost_reporting() -> None:
    # Sanity: the per-attempt guard doesn't touch cost accounting (estimated list cost stays Decimal).
    from app.accounting.cost import CostBreakdown

    assert (
        CostBreakdown(Decimal(0), "free_tier", None, "unavailable").estimated_list_cost_usd is None
    )
