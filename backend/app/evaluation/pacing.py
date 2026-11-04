"""Quota-aware pacing for benchmark runs.

Two generations live here:

- **v5.1+ (current): `AttemptPacer` + `PacedProvider`.** Every actual provider attempt (initial,
  retry, fallback) reserves its own quota before transmission. The input bound is UTF-8 bytes +
  framing allowance; daily tokens come from an operator-verified budget plus a persistent ledger.
  See the section "v5.1 execution safety" below.
- **v5 (superseded, kept so the immutable v5 record and its tests stay meaningful):
  `QuotaPacer` / `GROQ_FREE_QUOTA`.** Not used by the runner any more; a schema-3 (v5) quota
  configuration is refused. Its known defects (retries and fallbacks unreserved, a ~4 chars/token
  estimate, an unverified 200K tokens/day) are documented in the v5.1 changelog.

v5 description, kept as it was:

A fixed delay between requests doesn't guarantee staying under a tokens-per-minute limit, so the
pacer budgets tokens explicitly:

- Every provider call is charged its **worst case** in the per-minute window: estimated input
  tokens + a fixed overhead + the case's max_output_tokens. Groq counts reasoning tokens as
  output, and may account for requested output before generation, so actual usage isn't trusted
  for the per-minute budget.
- Per-day totals use reported usage when the request made exactly one call, else the worst case.
- Limits are pinned (see GROQ_FREE_QUOTA) and applied to all Groq models **combined**. Groq's
  limits are per model, so this is stricter. Rate-limit headers can only make pacing stricter:
  the effective limit is min(pinned, header), and a header showing too few remaining tokens or
  requests makes the pacer wait for the reported reset, or stop.
- If a pinned or reported daily budget would be exceeded, the pacer raises QuotaExhausted. The
  runner then stops and marks the run incomplete (never publishable); it never exceeds the limit.

Retries inside one gateway request (Groq max_retries = 1, transient errors only) happen without
pacing; the pacer charges them afterwards as extra worst-case calls.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any

from app.providers.base import (
    Provider,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
    RateLimitState,
    estimate_tokens,
)

# Verified status recorded with each value. "observed" values come from x-ratelimit headers
# returned to this account's key (one response, openai/gpt-oss-20b, 2026-11-04). "published"
# values come from Groq's rate-limits page, which labels them as Developer-plan base limits; they
# are not verified for the Free plan and are treated as upper bounds only.
_PUBLISHED = (
    "published Developer-plan base limit (console.groq.com/docs/rate-limits, 2026-11-04); "
    "not verified for the Free plan"
)
GROQ_FREE_QUOTA: dict[str, Any] = {
    "scope": "all Groq models combined (Groq's limits are per model, so this is stricter)",
    "tokens_per_minute": 8000,
    "requests_per_day": 1000,
    "requests_per_minute": 30,
    "tokens_per_day": 200000,
    "per_minute_safety": 0.75,
    "per_day_safety": 0.9,
    "input_overhead_tokens": 100,
    "window_s": 60.0,
    "provenance": {
        "tokens_per_minute": (
            "observed: x-ratelimit-limit-tokens=8000 (openai/gpt-oss-20b, this key, 2026-11-04)"
        ),
        "requests_per_day": (
            "observed: x-ratelimit-limit-requests=1000 (openai/gpt-oss-20b, this key, 2026-11-04)"
        ),
        "requests_per_minute": _PUBLISHED,
        "tokens_per_day": _PUBLISHED,
        "openai/gpt-oss-120b": "no limits observed; assumed no higher than the values above",
    },
}


class QuotaExhausted(Exception):
    """Continuing would exceed a pinned or provider-reported daily limit."""


class QuotaPacer:
    def __init__(
        self,
        quota: dict[str, Any],
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.quota = copy.deepcopy(quota)
        self._clock = clock
        self._sleep = sleep
        self._window: deque[tuple[float, int]] = deque()  # (time, tokens) per provider call
        self.day_requests = 0
        self.day_tokens = 0
        self.waits: list[float] = []
        self._headers: dict[str, RateLimitState] = {}

    # --- budgets ------------------------------------------------------------------------

    def worst_case_tokens(self, prompt: str, max_output_tokens: int) -> int:
        return (
            estimate_tokens(prompt) + int(self.quota["input_overhead_tokens"]) + max_output_tokens
        )

    def _limit(self, pinned_key: str, header_attr: str) -> float:
        pinned = float(self.quota[pinned_key])
        reported = [getattr(h, header_attr) for h in self._headers.values()]
        reported = [r for r in reported if r is not None]
        return min([pinned, *map(float, reported)])

    def _prune(self, now: float) -> None:
        while self._window and now - self._window[0][0] >= float(self.quota["window_s"]):
            self._window.popleft()

    async def acquire(self, tokens: int) -> None:
        """Wait until a call costing `tokens` fits every budget, then reserve it."""
        minute_safety = float(self.quota["per_minute_safety"])
        day_safety = float(self.quota["per_day_safety"])
        tpm = self._limit("tokens_per_minute", "limit_tokens") * minute_safety
        rpm = float(self.quota["requests_per_minute"]) * minute_safety
        rpd = self._limit("requests_per_day", "limit_requests") * day_safety
        tpd = float(self.quota["tokens_per_day"]) * day_safety
        if tokens > tpm:
            raise QuotaExhausted(f"one call needs {tokens} tokens, above the {tpm:.0f}/min budget")
        if self.day_requests + 1 > rpd or self.day_tokens + tokens > tpd:
            raise QuotaExhausted(
                f"daily budget reached ({self.day_requests} requests, {self.day_tokens} tokens)"
            )
        for state in self._headers.values():
            # Keep (1 - per_day_safety) of the provider's daily requests in reserve.
            reserve = (1 - day_safety) * (state.limit_requests or 0)
            if state.remaining_requests is not None and state.remaining_requests - 1 < reserve:
                raise QuotaExhausted(
                    f"provider reports {state.remaining_requests} requests left today"
                )
        window_s = float(self.quota["window_s"])
        while True:
            now = self._clock()
            self._prune(now)
            wait = 0.0
            used = sum(t for _, t in self._window)
            if used + tokens > tpm or len(self._window) + 1 > rpm:
                # The earliest moment enough of the window has expired for this call to fit.
                remaining_used, remaining_count = used, len(self._window)
                for at, spent in self._window:
                    remaining_used -= spent
                    remaining_count -= 1
                    if remaining_used + tokens <= tpm and remaining_count + 1 <= rpm:
                        wait = at + window_s - now
                        break
            for state in self._headers.values():
                if state.remaining_tokens is not None and state.remaining_tokens < tokens:
                    reset_at = state.observed_at + (state.reset_tokens_s or window_s)
                    wait = max(wait, reset_at - now)
            if wait <= 0:
                break
            self.waits.append(wait)
            await self._sleep(wait)
            # Header state is stale after its reset; drop it so it can't block forever.
            for key, state in list(self._headers.items()):
                if self._clock() >= state.observed_at + (state.reset_tokens_s or 0):
                    self._headers[key] = RateLimitState(
                        model_id=state.model_id,
                        observed_at=state.observed_at,
                        limit_requests=state.limit_requests,
                        remaining_requests=state.remaining_requests,
                        limit_tokens=state.limit_tokens,
                    )
        self._window.append((self._clock(), tokens))
        self.day_requests += 1

    def record(
        self,
        *,
        calls: int,
        reserved_tokens: int,
        reported_tokens: int | None,
        headers: list[RateLimitState],
    ) -> None:
        """Account for what actually happened after the request."""
        extra = max(0, calls - 1)
        now = self._clock()
        for _ in range(extra):  # retries/fallbacks inside the gateway request
            self._window.append((now, reserved_tokens))
        self.day_requests += extra
        known = reported_tokens if calls == 1 and reported_tokens is not None else None
        self.day_tokens += known if known is not None else reserved_tokens * max(calls, 1)
        for state in headers:
            self._headers[state.model_id] = state


# ================================================================================================
# v5.1 execution safety
# ================================================================================================

# Limits used by v5.1. Each carries its verification status; nothing here is inferred from the
# billing-plan setting or from Developer-plan documentation.
GROQ_QUOTA_V5_1: dict[str, Any] = {
    "scope": "all Groq models combined (stricter than Groq's per-model limits)",
    "tokens_per_minute": 8000,
    "per_minute_safety": 0.75,
    "requests_per_day": 1000,
    "per_day_safety": 0.9,
    # Groq's headers expose requests-per-day and tokens-per-minute, not requests-per-minute, and no
    # RPM value has been verified for this account. This is a self-imposed conservative cap, not a
    # claimed limit.
    "requests_per_minute_cap": 10,
    # Not verified for this account: the operator must supply a remaining daily token budget with
    # its source and verification time (DailyBudget). The run refuses to start otherwise.
    "tokens_per_day": None,
    "operator_daily_budget_required": True,
    # Input upper bound per attempt = UTF-8 bytes of all message contents + this allowance.
    "framing_allowance_tokens": 256,
    "window_s": 60.0,
    "verification": {
        "tokens_per_minute": (
            "observed: x-ratelimit-limit-tokens=8000 (openai/gpt-oss-20b, this key, 2026-11-04, one"
            " response); openai/gpt-oss-120b not observed (assumed no higher; headers tighten it at"
            " run time)"
        ),
        "requests_per_day": (
            "observed: x-ratelimit-limit-requests=1000 (openai/gpt-oss-20b, this key, 2026-11-04, "
            "one response); openai/gpt-oss-120b not observed"
        ),
        "requests_per_minute_cap": (
            "self-imposed; Groq's RPM for this account is not verified and not exposed in headers"
        ),
        "tokens_per_day": "NOT verified; operator-supplied remaining budget required",
        "framing_allowance_tokens": (
            "empirical: one observed request reported 83 input tokens for a 53-byte prompt (framing"
            " <= 82); 256 is ~3x that. Not guaranteed: a reported input above the bound stops the "
            "run"
        ),
    },
}


def input_token_bound(contents: list[str], framing_allowance: int) -> int:
    """Upper bound on input tokens for one attempt.

    Byte-level BPE tokenizers (GPT-OSS uses one) emit at most one token per UTF-8 byte of text,
    so the content part is a strict bound. The chat-template framing (role markers, the
    provider-injected system preamble) is not visible to us. It is covered by an empirical
    allowance, and the run stops if a response ever reports more input tokens than reserved.
    """
    return sum(len(c.encode("utf-8")) for c in contents) + framing_allowance


@dataclass(frozen=True)
class DailyBudget:
    """Operator-supplied remaining daily token budget for the provider organisation."""

    remaining_tokens: int
    verified_at: datetime  # timezone-aware UTC
    source: str
    daily_token_limit: int | None = None
    tokens_used_at_verification: int | None = None

    @classmethod
    def from_limit_and_usage(
        cls, *, limit: int, used: int, verified_at: datetime, source: str
    ) -> DailyBudget:
        return cls(
            remaining_tokens=max(0, limit - used),
            verified_at=verified_at,
            source=source,
            daily_token_limit=limit,
            tokens_used_at_verification=used,
        )

    def problems(self, now: datetime) -> list[str]:
        out = []
        if self.verified_at.tzinfo is None:
            out.append("verified_at must include a timezone (UTC)")
        elif self.verified_at > now:
            out.append("verified_at is in the future")
        elif self.verified_at.astimezone(UTC).date() != now.astimezone(UTC).date():
            out.append("budget was not verified today (UTC); daily usage may have changed")
        if not self.source.strip():
            out.append("budget source is empty")
        if self.remaining_tokens < 0:
            out.append("remaining tokens is negative")
        return out


# v5.2: ledger record format. Each attempt keeps SEPARATE fields for the per-minute (TPM) worst-case
# reservation and the settled daily usage, so settling never shrinks the per-minute history.
LEDGER_FORMAT = 2
STATUS_KIND = {  # status -> legacy v5.1 `kind` label (kept for compatibility)
    "reserved": "reserved_worst_case",
    "sent_known": "sent_reported_usage",
    "sent_unknown": "sent_usage_unknown_worst_case_kept",
    "not_sent": "not_sent_released",
}
_KIND_STATUS = {kind: status for status, kind in STATUS_KIND.items()}
CONSUMING = ("reserved", "sent_known", "sent_unknown")  # count toward TPM and daily budgets
LOCK_TIMEOUT_S = 30.0


class _FileLock:
    """Exclusive, cross-process lock on a sidecar file (stdlib only: msvcrt on Windows, fcntl on
    POSIX). The OS releases it if the holding process dies, so a crash can't leave it stuck."""

    def __init__(self, path: Path, timeout_s: float) -> None:
        self.path = path
        self.timeout_s = timeout_s
        self._fh: Any = None

    def __enter__(self) -> _FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Nothing is ever written to the lock file: on Windows, locking byte 0 beyond end-of-file is
        # allowed, and a write would race with another process's (mandatory) lock on that byte.
        fh = open(self.path, "a+b")  # held open for the lifetime of the lock
        deadline = monotonic() + self.timeout_s
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if monotonic() > deadline:
                    fh.close()
                    raise TimeoutError(
                        f"could not lock {self.path} within {self.timeout_s}s"
                    ) from None
                time.sleep(0.01)
        self._fh = fh
        return self

    def __exit__(self, *exc: object) -> None:
        fh, self._fh = self._fh, None
        try:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """Bring a record to format 2. Legacy v5.1 records have no separate TPM field (v5.1 overwrote
    `tokens` with actual usage), so their TPM reservation is unknown: `None`, which the window
    treats as the whole per-minute budget (conservative)."""
    status = entry.get("status") or _KIND_STATUS.get(entry.get("kind", ""), "reserved")
    reserved_at = entry.get("reserved_at") or entry["at"]
    daily = int(entry.get("daily_tokens", entry.get("tokens", 0)))
    tpm = entry.get("tpm_reserved_tokens")
    return {
        **entry,
        "status": status,
        "reserved_at": reserved_at,
        "tpm_reserved_tokens": tpm,
        "daily_tokens": daily,
        # legacy mirrors
        "kind": STATUS_KIND[status],
        "tokens": daily,
        "at": reserved_at,
    }


class LedgerTxn:
    """The ledger's latest on-disk state, read under the lock. Mutations are written atomically
    when the transaction closes."""

    def __init__(self, data: dict[str, Any], provider: str) -> None:
        self.data = data
        self.provider = provider
        self.dirty = False

    def entries(self, *, include_released: bool = False) -> list[dict[str, Any]]:
        return [
            e
            for e in self.data["entries"]
            if e.get("provider") == self.provider and (include_released or e["status"] in CONSUMING)
        ]

    def add(self, entry: dict[str, Any]) -> None:
        self.data["entries"].append(_normalize({**entry, "provider": self.provider}))
        self.dirty = True

    def update(self, entry_id: str, **fields: Any) -> None:
        for i, e in enumerate(self.data["entries"]):
            if e.get("provider") == self.provider and e["id"] == entry_id:
                merged = {**e, **fields}
                if "status" in fields:
                    merged["kind"] = STATUS_KIND[fields["status"]]
                if "daily_tokens" in fields:
                    merged["tokens"] = fields["daily_tokens"]
                self.data["entries"][i] = merged
        self.dirty = True

    def remove(self, entry_id: str) -> None:
        self.data["entries"] = [
            e
            for e in self.data["entries"]
            if not (e.get("provider") == self.provider and e["id"] == entry_id)
        ]
        self.dirty = True

    def tokens_since(self, since: datetime) -> int:
        return sum(
            int(e["daily_tokens"])
            for e in self.entries()
            if datetime.fromisoformat(e["reserved_at"]) >= since
        )

    def requests_on(self, day: date) -> int:
        return sum(
            1 for e in self.entries() if datetime.fromisoformat(e["reserved_at"]).date() == day
        )

    def window(self, now: datetime, window_s: float) -> list[tuple[datetime, int | None]]:
        """Consuming reservations still inside the rolling window, oldest first. A reservation
        leaves the window only once `window_s` seconds have passed since it was made."""
        out = []
        for e in self.entries():
            at = datetime.fromisoformat(e["reserved_at"])
            if (now - at).total_seconds() < window_s:
                out.append((at, e["tpm_reserved_tokens"]))
        return sorted(out, key=lambda x: x[0])

    def headers(self) -> dict[str, dict[str, Any]]:
        all_headers: dict[str, dict[str, Any]] = self.data.setdefault("headers", {})
        mine: dict[str, Any] = all_headers.setdefault(self.provider, {})
        return mine


class QuotaLedger:
    """Persistent, cross-process-safe per-attempt ledger (v5.2).

    Every read-modify-write runs as a transaction: acquire an exclusive file lock, read the latest
    saved state, decide (e.g. recalculate available capacity), mutate, persist atomically
    (temporary file + fsync + os.replace), release. No decision uses a stale in-memory copy.

    Each attempt record keeps: `reserved_at` (wall-clock UTC), `tpm_reserved_tokens` (the
    worst case held in the rolling per-minute window; never overwritten), `daily_tokens` (worst
    case until settled, then reported usage, or the worst case if usage is unknown) and `status`
    (`reserved`, `sent_known`, `sent_unknown`, `not_sent`). The latest provider rate-limit headers
    are persisted too, so a restart neither gets a fresh per-minute budget nor forgets headers.
    """

    def __init__(
        self, path: Path, provider: str, *, lock_timeout_s: float = LOCK_TIMEOUT_S
    ) -> None:
        self.path = path
        self.provider = provider
        self.lock_path = path.with_name(path.name + ".lock")
        self.lock_timeout_s = lock_timeout_s

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"format": LEDGER_FORMAT, "entries": [], "headers": {}}
        data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        data["entries"] = [_normalize(e) for e in data.get("entries", [])]
        data.setdefault("headers", {})
        data["format"] = LEDGER_FORMAT
        return data

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    @contextmanager
    def transaction(self) -> Iterator[LedgerTxn]:
        with _FileLock(self.lock_path, self.lock_timeout_s):
            txn = LedgerTxn(self._read(), self.provider)
            yield txn
            if txn.dirty:
                self._write(txn.data)

    @contextmanager
    def _view(self) -> Iterator[LedgerTxn]:
        """Read-only view. If no ledger exists yet there is nothing to read or race with, so no
        file (not even the lock) is created; otherwise it reads under the lock like a write."""
        if not self.path.exists():
            yield LedgerTxn({"format": LEDGER_FORMAT, "entries": [], "headers": {}}, self.provider)
            return
        with self.transaction() as txn:
            yield txn

    # --- single-operation conveniences (each is its own transaction) ----------------------------

    @property
    def entries(self) -> list[dict[str, Any]]:
        with self._view() as txn:
            return txn.entries()

    @property
    def all_entries(self) -> list[dict[str, Any]]:
        with self._view() as txn:
            return txn.entries(include_released=True)

    def add(self, entry: dict[str, Any]) -> None:
        with self.transaction() as txn:
            txn.add(entry)

    def update(self, entry_id: str, **fields: Any) -> None:
        with self.transaction() as txn:
            txn.update(entry_id, **fields)

    def remove(self, entry_id: str) -> None:
        with self.transaction() as txn:
            txn.remove(entry_id)

    def tokens_since(self, since: datetime) -> int:
        with self._view() as txn:
            return txn.tokens_since(since)

    def requests_on(self, day: date) -> int:
        with self._view() as txn:
            return txn.requests_on(day)


@dataclass
class Reservation:
    id: str
    model_id: str
    tokens: int
    input_bound: int
    output_bound: int
    window_at: float


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class AttemptPacer:
    """Reserves quota for every provider attempt before it is transmitted (v5.2: all state is
    read from and written to the transactional ledger, so it survives restarts and is shared
    safely between processes)."""

    def __init__(
        self,
        quota: dict[str, Any],
        budget: DailyBudget | None,
        ledger: QuotaLedger,
        *,
        clock: Callable[[], float] = monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.quota = copy.deepcopy(quota)
        self.budget = budget
        self.ledger = ledger
        self._clock = clock
        self._now = now
        self._sleep = sleep
        self.exhausted: str | None = None  # set once; no further attempt is allowed
        self.attempts = 0
        self.waits: list[float] = []

    # --- bounds -------------------------------------------------------------------------------

    def attempt_tokens(self, contents: list[str], max_output_tokens: int) -> tuple[int, int]:
        return (
            input_token_bound(contents, int(self.quota["framing_allowance_tokens"])),
            max_output_tokens,
        )

    # --- capacity (evaluated on the latest ledger state, under its lock) ------------------------

    def _stop(self, reason: str) -> QuotaExhausted:
        if self.exhausted is None:
            self.exhausted = reason
        return QuotaExhausted(reason)

    def _check(self, txn: LedgerTxn, tokens: int, model_id: str | None) -> float:
        """Raise if a daily budget can't take one more attempt of `tokens`; otherwise return how
        many seconds to wait until the per-minute budgets can (0 = now)."""
        if self.exhausted is not None:
            raise QuotaExhausted(self.exhausted)
        now = self._now()
        if self.budget is None:
            raise self._stop("no operator-verified daily token budget")
        problems = self.budget.problems(now)
        if problems:
            raise self._stop("daily budget invalid: " + "; ".join(problems))
        day_safety = float(self.quota["per_day_safety"])
        allowed = self.budget.remaining_tokens * day_safety
        used = txn.tokens_since(self.budget.verified_at)
        if used + tokens > allowed:
            raise self._stop(
                f"daily token budget: {used} used since verification + {tokens} needed "
                f"> {allowed:.0f}"
            )
        rpd = float(self.quota["requests_per_day"]) * day_safety
        if txn.requests_on(now.astimezone(UTC).date()) + 1 > rpd:
            raise self._stop("daily request budget reached")
        headers = txn.headers()
        for model, h in headers.items():
            reset = _dt(h.get("reset_requests_at"))
            if (
                h.get("limit_requests") is not None
                and h.get("remaining_requests") is not None
                and (reset is None or reset > now)
            ):
                reserve = (1 - day_safety) * int(h["limit_requests"])
                if int(h["remaining_requests"]) - 1 < reserve:
                    raise self._stop(
                        f"provider reports {h['remaining_requests']} requests left today ({model})"
                    )
        # Per-minute budget from the persisted window (survives restarts; shared by processes).
        window_s = float(self.quota["window_s"])
        tpm = float(self.quota["tokens_per_minute"])
        for h in headers.values():
            if h.get("limit_tokens") is not None:
                tpm = min(tpm, float(h["limit_tokens"]))  # headers only tighten
        budget = tpm * float(self.quota["per_minute_safety"])
        rpm = float(self.quota["requests_per_minute_cap"])
        if tokens > budget:
            raise self._stop(
                f"one attempt needs {tokens} tokens, above the {budget:.0f}/min budget"
            )
        window = [
            (at, budget if spent is None else float(spent))
            for at, spent in txn.window(now, window_s)
        ]
        wait = 0.0
        used_minute = sum(spent for _, spent in window)
        if used_minute + tokens > budget or len(window) + 1 > rpm:
            remaining_used, remaining_count = used_minute, len(window)
            for at, spent in window:
                remaining_used -= spent
                remaining_count -= 1
                if remaining_used + tokens <= budget and remaining_count + 1 <= rpm:
                    wait = (at - now).total_seconds() + window_s
                    break
        model_header = headers.get(model_id or "")
        if (
            model_header is not None
            and model_header.get("remaining_tokens") is not None
            and int(model_header["remaining_tokens"]) < tokens
        ):
            observed = _dt(model_header["observed_at"]) or now
            reset_at = _dt(model_header.get("reset_tokens_at")) or observed + timedelta(
                seconds=window_s
            )
            wait = max(wait, (reset_at - now).total_seconds())
        return max(0.0, wait)

    async def wait_for(self, tokens: int, model_id: str | None = None) -> None:
        """Wait until an attempt of `tokens` fits; raise if a daily budget can't take it.
        Doesn't reserve (the lock is never held while sleeping)."""
        while True:
            with self.ledger.transaction() as txn:
                wait = self._check(txn, tokens, model_id)
            if wait <= 0:
                return
            self.waits.append(wait)
            await self._sleep(wait)

    async def reserve(self, model_id: str, input_bound: int, output_bound: int) -> Reservation:
        """Atomically check capacity on the latest ledger state and record the reservation."""
        tokens = input_bound + output_bound
        while True:
            with self.ledger.transaction() as txn:
                wait = self._check(txn, tokens, model_id)
                if wait <= 0:
                    res = Reservation(
                        id=uuid.uuid4().hex,
                        model_id=model_id,
                        tokens=tokens,
                        input_bound=input_bound,
                        output_bound=output_bound,
                        window_at=self._clock(),
                    )
                    txn.add(
                        {
                            "id": res.id,
                            "at": self._now().isoformat(),
                            "reserved_at": self._now().isoformat(),
                            "model": model_id,
                            "tpm_reserved_tokens": tokens,
                            "daily_tokens": tokens,
                            "status": "reserved",
                            "pid": os.getpid(),
                        }
                    )
                    self.attempts += 1
                    return res
            self.waits.append(wait)
            await self._sleep(wait)

    def settle(
        self,
        res: Reservation,
        *,
        sent: bool,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        """Record the outcome. Only `daily_tokens` and `status` change; `tpm_reserved_tokens`
        (the per-minute worst case) is never overwritten."""
        with self.ledger.transaction() as txn:
            if not sent:
                # Refused locally before transmission: nothing consumed, and it leaves both budgets.
                txn.update(res.id, status="not_sent", daily_tokens=0)
                self.attempts -= 1
                return
            if input_tokens is None or output_tokens is None:
                # Transmitted but usage unknown: the worst case stays in both budgets (never zero).
                txn.update(res.id, status="sent_unknown")
                return
            txn.update(
                res.id, status="sent_known", daily_tokens=max(input_tokens + output_tokens, 0)
            )
        if input_tokens > res.input_bound or output_tokens > res.output_bound:
            self._stop(
                f"reported usage ({input_tokens} in / {output_tokens} out) exceeded the reserved "
                f"bound ({res.input_bound} / {res.output_bound}); the token bound is not safe"
            )

    def observe(self, state: RateLimitState | None) -> None:
        """Persist the latest rate-limit headers (wall-clock), so they constrain later attempts in
        this and any other process, and after a restart."""
        if state is None:
            return
        now = self._now()
        observed = now - timedelta(seconds=max(0.0, self._clock() - state.observed_at))
        record = {
            "observed_at": observed.isoformat(),
            "limit_tokens": state.limit_tokens,
            "remaining_tokens": state.remaining_tokens,
            "reset_tokens_at": _iso(
                observed + timedelta(seconds=state.reset_tokens_s)
                if state.reset_tokens_s is not None
                else None
            ),
            "limit_requests": state.limit_requests,
            "remaining_requests": state.remaining_requests,
            "reset_requests_at": _iso(
                observed + timedelta(seconds=state.reset_requests_s)
                if state.reset_requests_s is not None
                else None
            ),
        }
        with self.ledger.transaction() as txn:
            headers = txn.headers()
            previous = headers.get(state.model_id)
            if previous is None or _dt(previous["observed_at"]) <= observed:  # type: ignore[operator]
                headers[state.model_id] = record
                txn.dirty = True


class PacedProvider(Provider):
    """Wraps a provider so that every `generate()` call (initial, retry or fallback attempt, as
    issued by the executor) reserves its own quota before the network request."""

    def __init__(self, inner: Provider, pacer: AttemptPacer) -> None:
        self.inner = inner
        self.pacer = pacer
        self.name = inner.name
        self.simulated = inner.simulated
        self.charge_basis = inner.charge_basis
        self.max_retries = inner.max_retries
        self.last_rate_limit = inner.last_rate_limit

    def quota_available(self) -> bool:
        # Exhaustion blocks any further network call, including the executor's next fallback.
        return self.pacer.exhausted is None and self.inner.quota_available()

    async def list_model_ids(self) -> set[str] | None:
        return await self.inner.list_model_ids()

    async def aclose(self) -> None:
        await self.inner.aclose()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        input_bound, output_bound = self.pacer.attempt_tokens(
            [m.content for m in request.messages], request.max_output_tokens
        )
        try:
            res = await self.pacer.reserve(request.model_id, input_bound, output_bound)
        except QuotaExhausted as error:
            raise ProviderError(
                kind=ProviderErrorKind.QUOTA_EXHAUSTED,
                message=f"local quota guard: {error}",
                provider=self.name,
                sent=False,
            ) from None
        try:
            response = await self.inner.generate(request)
        except ProviderError as error:
            usage = error.usage
            self.pacer.settle(
                res,
                sent=error.sent,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
            )
            self.last_rate_limit = self.inner.last_rate_limit
            self.pacer.observe(self.inner.last_rate_limit)
            raise
        except BaseException:
            self.pacer.settle(res, sent=True, input_tokens=None, output_tokens=None)
            raise
        self.pacer.settle(
            res,
            sent=True,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        self.last_rate_limit = self.inner.last_rate_limit
        self.pacer.observe(self.inner.last_rate_limit)
        return response


# v5.2: same numeric limits as v5.1, re-registered with the transactional ledger. The provenance
# text
# makes no inference about gpt-oss-120b or the Free plan from the gpt-oss-20b observation: the
# per-minute and per-day caps are a SELF-IMPOSED aggregate across all Groq models, set at the one
# observed per-model value.
GROQ_QUOTA_V5_2: dict[str, Any] = {
    **copy.deepcopy(GROQ_QUOTA_V5_1),
    "ledger_format": LEDGER_FORMAT,
    "ledger_concurrency": (
        "exclusive OS file lock per transaction; latest state re-read under the lock"
    ),
    "operator_must_isolate_quota": True,
    "verification": {
        "tokens_per_minute": (
            "self-imposed aggregate cap across all Groq models = 8000, the value observed in "
            "x-ratelimit-limit-tokens for openai/gpt-oss-20b on this key (2026-11-04, one "
            "response). "
            "openai/gpt-oss-120b's and the Free plan's limits are NOT known and NOT inferred "
            "from it; "
            "a lower header value tightens the cap at run time"
        ),
        "requests_per_day": (
            "self-imposed aggregate cap = 1000, the value observed in x-ratelimit-limit-requests "
            "for "
            "openai/gpt-oss-20b (one response); 120B / Free-plan limits not known, not inferred"
        ),
        "requests_per_minute_cap": "self-imposed; Groq's RPM for this account is not verified",
        "tokens_per_day": "NOT verified; operator-supplied remaining budget required",
        "framing_allowance_tokens": (
            "EMPIRICAL, not a guaranteed bound: one observed request reported 83 input tokens "
            "for a "
            "53-byte prompt (framing <= 82); 256 is ~3x that. A reported input above the bound "
            "stops the run after that attempt"
        ),
        "content_bound": "strict for byte-level BPE: at most one token per UTF-8 byte of content",
        "quota_scope": (
            "the operator must ensure no other traffic uses the same Groq organisation's quota "
            "during the run; other traffic is otherwise visible only through rate-limit headers"
        ),
    },
}
