"""Execution revision routewise_bench_v5.2: transactional quota ledger and persisted TPM history.

Self-contained (no imports from other test modules) so it runs from the clean-room review bundle.
No provider is called. Concurrency tests use real, separate OS processes on a temporary ledger.
Restart tests create fresh ledger and pacer instances on the same file. Time is faked except in
the multi-process tests, which never need to wait.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.core.config import BACKEND_ROOT, Settings
from app.evaluation import manifest as manifest_mod
from app.evaluation.dataset import (
    EVAL_ROOT,
    load_dataset,
    load_execution_revision,
    load_preregistration,
)
from app.evaluation.pacing import (
    GROQ_QUOTA_V5_1,
    GROQ_QUOTA_V5_2,
    AttemptPacer,
    DailyBudget,
    PacedProvider,
    QuotaExhausted,
    QuotaLedger,
)
from app.providers.base import (
    ChatMessage,
    Provider,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
    RateLimitState,
)
from app.providers.groq import GroqProvider

REVISION = "routewise_bench_v5.2"
V5 = load_dataset("routewise_bench_v5")
V5_SHA = "76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd"
T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, wall: datetime = T0, mono: float = 1000.0) -> None:
        self.mono = mono
        self.wall = wall
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.mono

    def now(self) -> datetime:
        return self.wall

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.wall += timedelta(seconds=seconds)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)


def _budget(remaining: int = 10_000_000) -> DailyBudget:
    return DailyBudget(remaining, T0 - timedelta(hours=1), "operator check (test)")


def _pacer(path: Path, clock: FakeClock, remaining: int = 10_000_000) -> AttemptPacer:
    """A fresh process's view: new ledger object, new pacer, nothing carried over in memory."""
    return AttemptPacer(
        GROQ_QUOTA_V5_2,
        _budget(remaining),
        QuotaLedger(path, "groq"),
        clock=clock,
        now=clock.now,
        sleep=clock.sleep,
    )


# --- 1-2: independent instances and concurrent processes ----------------------------------------


def test_two_ledger_instances_cannot_overwrite_each_others_reservations(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    a, b = QuotaLedger(path, "groq"), QuotaLedger(path, "groq")  # both created before any write
    for i in range(5):
        a.add({"id": f"a{i}", "at": T0.isoformat(), "model": "m", "tokens": 10})
        b.add({"id": f"b{i}", "at": T0.isoformat(), "model": "m", "tokens": 10})
    ids = {e["id"] for e in QuotaLedger(path, "groq").entries}
    assert ids == {f"a{i}" for i in range(5)} | {f"b{i}" for i in range(5)}


_ADD_SCRIPT = """
import sys
from app.evaluation.pacing import QuotaLedger
from pathlib import Path
ledger = QuotaLedger(Path(sys.argv[1]), "groq")
for i in range(int(sys.argv[3])):
    ledger.add({"id": f"{sys.argv[2]}-{i}", "at": "2026-11-05T12:00:00+00:00", "model": "m", "tokens": 1})
"""

_RESERVE_SCRIPT = """
import asyncio, json, sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from app.evaluation.pacing import GROQ_QUOTA_V5_2, AttemptPacer, DailyBudget, QuotaExhausted, QuotaLedger
quota = {**GROQ_QUOTA_V5_2, "tokens_per_minute": 10**9, "requests_per_minute_cap": 10**6, "requests_per_day": 10**6}
budget = DailyBudget(int(sys.argv[2]), datetime.now(UTC) - timedelta(minutes=5), "test")
pacer = AttemptPacer(quota, budget, QuotaLedger(Path(sys.argv[1]), "groq"))
async def main():
    n = 0
    try:
        while True:
            await pacer.reserve("m", 500, 500)
            n += 1
    except QuotaExhausted:
        pass
    print(json.dumps({"reserved": n}))
asyncio.run(main())
"""


def _spawn(script: str, *args: str) -> subprocess.Popen[str]:
    # Our own fixed test scripts, run with the current (pinned) interpreter.
    return subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", script, *args],
        cwd=BACKEND_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_concurrent_processes_cannot_lose_each_others_writes(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    procs = [_spawn(_ADD_SCRIPT, str(path), name, "40") for name in ("p1", "p2", "p3")]
    for p in procs:
        _, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
    entries = QuotaLedger(path, "groq").entries
    assert len(entries) == 120 and len({e["id"] for e in entries}) == 120


def test_concurrent_reservations_cannot_exceed_the_daily_budget(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    remaining = 20_000  # usable = 0.9 x 20,000 = 18,000 tokens = exactly 18 attempts of 1,000
    procs = [_spawn(_RESERVE_SCRIPT, str(path), str(remaining)) for _ in range(3)]
    counts = []
    for p in procs:
        out, err = p.communicate(timeout=180)
        assert p.returncode == 0, err
        counts.append(json.loads(out.strip().splitlines()[-1])["reserved"])
    entries = QuotaLedger(path, "groq").entries
    assert sum(counts) == len(entries) == 18  # all capacity used, none over-committed
    assert sum(e["daily_tokens"] for e in entries) <= remaining * 0.9


# --- 3-7: persisted TPM history ----------------------------------------------------------------


async def test_restart_does_not_reset_recent_tpm_usage(tmp_path: Path) -> None:
    path, clock = tmp_path / "ledger.json", FakeClock()
    first = _pacer(path, clock)
    await first.reserve("m", 500, 2000)
    await first.reserve("m", 500, 2000)  # 5,000 of the 6,000/min budget
    clock.advance(10)
    restarted_clock = FakeClock(clock.wall, mono=5.0)  # new process, new monotonic clock
    restarted = _pacer(path, restarted_clock)
    await restarted.reserve("m", 500, 2000)  # must wait for the first reservations to expire
    assert restarted_clock.sleeps == [pytest.approx(50.0)]


async def test_unknown_usage_retains_the_worst_case_tpm_amount(tmp_path: Path) -> None:
    path, clock = tmp_path / "ledger.json", FakeClock()
    pacer = _pacer(path, clock)
    res = await pacer.reserve("m", 500, 2000)
    pacer.settle(res, sent=True, input_tokens=None, output_tokens=None)
    (entry,) = QuotaLedger(path, "groq").entries
    assert entry["status"] == "sent_unknown"
    assert entry["tpm_reserved_tokens"] == entry["daily_tokens"] == 2500
    with QuotaLedger(path, "groq").transaction() as txn:
        assert txn.window(clock.now(), 60) == [(T0, 2500)]


async def test_settled_daily_usage_and_tpm_reservation_are_tracked_separately(
    tmp_path: Path,
) -> None:
    path, clock = tmp_path / "ledger.json", FakeClock()
    pacer = _pacer(path, clock)
    res = await pacer.reserve("m", 500, 2000)
    pacer.settle(res, sent=True, input_tokens=120, output_tokens=180)
    (entry,) = QuotaLedger(path, "groq").entries
    assert entry["status"] == "sent_known"
    assert entry["daily_tokens"] == 300  # actual usage for the daily budget
    assert entry["tpm_reserved_tokens"] == 2500  # worst case kept for the per-minute window
    assert QuotaLedger(path, "groq").tokens_since(T0 - timedelta(minutes=1)) == 300
    # The window still holds 2,500, so a 4,000-token attempt doesn't fit (2,500 + 4,000 > 6,000).
    await pacer.reserve("m", 1000, 3000)
    assert clock.sleeps == [pytest.approx(60.0)]


def test_expired_reservations_leave_the_window_only_after_60_seconds(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = QuotaLedger(path, "groq")
    ledger.add(
        {
            "id": "x",
            "at": T0.isoformat(),
            "reserved_at": T0.isoformat(),
            "model": "m",
            "tpm_reserved_tokens": 2500,
            "daily_tokens": 2500,
            "status": "sent_known",
        }
    )
    with ledger.transaction() as txn:
        assert txn.window(T0 + timedelta(seconds=59.999), 60) == [(T0, 2500)]
        assert txn.window(T0 + timedelta(seconds=60), 60) == []


class RecordingProvider(Provider):
    name = "groq"

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.sent_at: list[datetime] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.sent_at.append(self.clock.wall)
        return ProviderResponse(
            content="ok",
            provider="groq",
            model_id=request.model_id,
            usage=ProviderUsage(10, 10),
            latency_ms=1,
            simulated=False,
        )


async def test_restarted_process_cannot_send_an_attempt_that_does_not_fit_the_window(
    tmp_path: Path,
) -> None:
    path, clock = tmp_path / "ledger.json", FakeClock()
    first = _pacer(path, clock)
    await first.reserve("m", 1000, 4000)  # 5,000 reserved at T0
    clock.advance(1)
    restart_clock = FakeClock(clock.wall, mono=0.0)
    restarted = _pacer(path, restart_clock)
    inner = RecordingProvider(restart_clock)
    request = ProviderRequest(
        model_id="m",
        messages=(ChatMessage(role="user", content="x" * 100),),
        max_output_tokens=2000,
    )
    await PacedProvider(inner, restarted).generate(request)
    # Not sent until the T0 reservation expired (T0 + 60s), despite the restart.
    assert inner.sent_at == [T0 + timedelta(seconds=60)]


async def test_rate_limit_headers_survive_a_restart(tmp_path: Path) -> None:
    path, clock = tmp_path / "ledger.json", FakeClock()
    _pacer(path, clock).observe(
        RateLimitState("m", clock(), remaining_tokens=100, reset_tokens_s=30.0)
    )
    clock.advance(5)
    restart_clock = FakeClock(clock.wall, mono=0.0)
    restarted = _pacer(path, restart_clock)
    await restarted.reserve("m", 500, 500)
    assert restart_clock.sleeps == [pytest.approx(25.0)]  # waits for the persisted reset
    # A lower token limit seen before the restart still tightens the budget afterwards.
    path2 = tmp_path / "ledger2.json"
    _pacer(path2, clock).observe(RateLimitState("m", clock(), limit_tokens=4000))
    with pytest.raises(QuotaExhausted, match="above the 3000/min budget"):
        await _pacer(path2, FakeClock(clock.wall)).reserve("m", 1000, 2500)


async def test_legacy_v5_1_records_are_treated_conservatively(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    # A v5.1-format record: `tokens` was overwritten with actual usage, so its TPM worst case is lost.
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "old",
                        "at": T0.isoformat(),
                        "model": "m",
                        "tokens": 50,
                        "kind": "sent_reported_usage",
                        "provider": "groq",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    clock = FakeClock(T0 + timedelta(seconds=10))
    await _pacer(path, clock).reserve("m", 100, 100)
    assert clock.sleeps == [pytest.approx(50.0)]  # counted as the whole minute's budget


async def test_not_sent_attempts_are_recorded_but_release_both_budgets(tmp_path: Path) -> None:
    path, clock = tmp_path / "ledger.json", FakeClock()
    pacer = _pacer(path, clock)
    res = await pacer.reserve("m", 1000, 4000)
    pacer.settle(res, sent=False, input_tokens=None, output_tokens=None)
    ledger = QuotaLedger(path, "groq")
    assert ledger.entries == [] and [e["status"] for e in ledger.all_entries] == ["not_sent"]
    await pacer.reserve("m", 1000, 4000)  # the released capacity is usable again immediately
    assert clock.sleeps == []


def test_lock_file_is_separate_and_ledger_is_valid_json_after_every_write(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    ledger = QuotaLedger(path, "groq")
    ledger.add({"id": "a", "at": T0.isoformat(), "model": "m", "tokens": 1})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == 2 and data["entries"][0]["status"] == "reserved"
    assert ledger.lock_path.exists() and ledger.lock_path != path
    assert not list(tmp_path.glob(".*.tmp"))  # no stray temporary files


# --- quota scope, framing wording, chain, manifest, CLI --------------------------------------------


def test_quota_constant_makes_no_inference_about_120b_or_the_free_plan() -> None:
    v = GROQ_QUOTA_V5_2["verification"]
    assert "NOT inferred" in v["tokens_per_minute"] and "self-imposed" in v["tokens_per_minute"]
    assert "not inferred" in v["requests_per_day"]
    assert v["framing_allowance_tokens"].startswith("EMPIRICAL, not a guaranteed bound")
    assert "strict" in v["content_bound"]
    assert GROQ_QUOTA_V5_2["operator_must_isolate_quota"] is True
    assert GROQ_QUOTA_V5_2["tokens_per_day"] is None
    for key in (
        "tokens_per_minute",
        "per_minute_safety",
        "requests_per_day",
        "per_day_safety",
        "requests_per_minute_cap",
        "framing_allowance_tokens",
        "window_s",
    ):
        assert GROQ_QUOTA_V5_2[key] == GROQ_QUOTA_V5_1[key]


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


STRATEGIES = ["baseline_premium", "routewise", "routewise_tier_first"]
PACING = {"concurrency": 1, "delay_s": 6.0, "limit_cases": None, "allow_code_exec": False}


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


def test_v5_artefacts_unchanged_and_v5_2_chain_holds() -> None:
    import hashlib

    assert V5.sha256 == V5_SHA
    prereg_path, pinned = load_execution_revision(REVISION, V5)
    prereg, sha = load_preregistration(prereg_path, dataset=V5, pinned_sha256=pinned)
    assert sha == pinned and prereg["revision"] == REVISION and prereg["dataset_sha256"] == V5_SHA
    raw = (EVAL_ROOT / prereg["experiment_manifest"]["file"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == prereg["experiment_manifest"]["sha256"]
    manifest = manifest_mod.load_manifest(EVAL_ROOT / prereg["experiment_manifest"]["file"])[0]
    assert manifest["schema"] == 5
    assert manifest["pinned"]["execution"]["attempt_quota"] == {"groq": GROQ_QUOTA_V5_2}


def test_v5_2_manifest_matches_the_intended_configuration(intended_cli: None) -> None:
    prereg_path, pinned = load_execution_revision(REVISION, V5)
    prereg, _ = load_preregistration(prereg_path, dataset=V5, pinned_sha256=pinned)
    assert manifest_mod.check_manifest(prereg, _intended(), _groq(), STRATEGIES, run_params=PACING)


def _main(*argv: str) -> int:
    from app import cli

    return cli.main(list(argv))


def test_eval_validate_v5_2_fails_closed_without_a_budget(intended_cli: None, capsys: Any) -> None:
    assert _main("eval-validate", "--dataset", "routewise_bench_v5", "--revision", REVISION) == 1
    out = capsys.readouterr().out
    assert "experiment_manifest_routewise_bench_v5.2.yaml: matches" in out
    assert "maximum provider attempts: 378" in out and "preflight: FAILED (fail closed)" in out


def test_eval_validate_v5_2_passes_with_a_verified_budget(
    intended_cli: None, capsys: Any, tmp_path: Path
) -> None:
    assert (
        _main(
            "eval-validate",
            "--dataset",
            "routewise_bench_v5",
            "--revision",
            REVISION,
            "--remaining-daily-tokens",
            "100000000",
            "--daily-budget-source",
            "test",
            "--daily-budget-verified-at",
            datetime.now(UTC).isoformat(),
            "--ledger",
            str(tmp_path / "ledger.json"),
        )
        == 0
    )
    assert "preflight: OK" in capsys.readouterr().out


def test_eval_run_v5_2_refuses_without_a_budget_before_any_network_call(
    intended_cli: None, capsys: Any
) -> None:
    assert (
        _main(
            "eval-run",
            "--dataset",
            "routewise_bench_v5",
            "--revision",
            REVISION,
            "--label",
            "t",
            "--delay-s",
            "6",
        )
        == 2
    )
    assert "quota preflight failed" in capsys.readouterr().err


def test_v5_1_is_refused_on_current_code(intended_cli: None, capsys: Any) -> None:
    assert (
        _main(
            "eval-run",
            "--dataset",
            "routewise_bench_v5",
            "--revision",
            "routewise_bench_v5.1",
            "--label",
            "t",
            "--delay-s",
            "6",
        )
        == 2
    )
    assert (
        "configuration differs from experiment_manifest_routewise_bench_v5.1.yaml"
        in capsys.readouterr().err
    )


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
    # Our own fixed script, run with the current (pinned) interpreter.
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script], cwd=BACKEND_ROOT, capture_output=True, text=True, check=True
    )
    assert set(json.loads(out.stdout)) <= set(manifest_mod.EXECUTION_MODULES_V4)


def test_runs_on_the_pinned_python() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_contending_for_a_fresh_lock_times_out_cleanly(tmp_path: Path) -> None:
    """Regression: the lock file used to get an initial byte written on first use. A second
    contender writing it while the first held the lock got PermissionError (Windows mandatory
    lock). Nothing is written now: the contender just waits and times out."""
    from app.evaluation.pacing import _FileLock

    lock = tmp_path / "fresh.lock"
    with _FileLock(lock, timeout_s=5):
        assert lock.stat().st_size == 0
        with pytest.raises(TimeoutError), _FileLock(lock, timeout_s=0.3):
            pass
    with _FileLock(lock, timeout_s=1):  # free again after release
        pass


def test_read_only_queries_on_a_missing_ledger_create_no_files(tmp_path: Path) -> None:
    ledger = QuotaLedger(tmp_path / "reports" / "quota_ledger.json", "groq")
    assert (
        ledger.entries == [] and ledger.tokens_since(T0) == 0 and ledger.requests_on(T0.date()) == 0
    )
    assert not (tmp_path / "reports").exists()  # no ledger, no lock file, no directory
