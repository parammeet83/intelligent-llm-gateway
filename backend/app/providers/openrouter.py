"""OpenRouter adapter, restricted to free (`:free`) models. Treated as a limited fallback.

Docs (verified 2026-11-03):
- Limits: https://openrouter.ai/docs/api-reference/limits. Free models: 20 req/min, and 50 req/day
  for accounts with <10 credits purchased. The docs don't say whether failed requests count, so
  this adapter assumes they do and counts every request that reaches the network.
- Errors: https://openrouter.ai/docs/api-reference/errors. 402 = insufficient credits (never
  wait-and-retry), 403 = moderation/guardrail block, 408 = timeout, 502/503 = upstream
  unavailable. A non-streaming HTTP 200 may carry an `error` object with no `choices`.
- Usage: https://openrouter.ai/docs/use-cases/usage-accounting. `usage` (tokens + `cost`) is
  always returned. `usage: {include: true}` is sent as the project requested, although the docs
  mark it deprecated with no effect.

Safety: any model ID without the `:free` suffix is refused before a request is made, so a
registry mistake can never turn into a paid call.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import UTC, date, datetime
from time import monotonic
from typing import Any, ClassVar

import httpx

from app.providers.base import ProviderErrorKind, ProviderRequest, ProviderUsage
from app.providers.http import DEFAULT_STATUS_MAP, OpenAICompatibleProvider, _charge

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
FREE_SUFFIX = ":free"


class FreeQuotaGuard:
    """Local, conservative mirror of OpenRouter's free-model limits.

    In-memory, so it resets on restart and isn't shared between processes. OpenRouter still
    enforces the real limit (and its 429s are never retried); this guard only avoids spending
    attempts that would certainly fail.
    """

    def __init__(
        self,
        *,
        per_minute: int,
        per_day: int,
        clock: Callable[[], float] = monotonic,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self._clock = clock
        self._today = today
        self._recent: deque[float] = deque()
        self._day = today()
        self.used_today = 0

    def _roll(self) -> None:
        if self._today() != self._day:
            self._day = self._today()
            self.used_today = 0
        cutoff = self._clock() - 60.0
        while self._recent and self._recent[0] <= cutoff:
            self._recent.popleft()

    def available(self) -> bool:
        self._roll()
        return self.used_today < self.per_day and len(self._recent) < self.per_minute

    def record(self) -> None:
        self._roll()
        self._recent.append(self._clock())
        self.used_today += 1

    def sync_used_today(self, used: int) -> None:
        self._roll()
        self.used_today = max(self.used_today, used)


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    # Every retry spends daily allowance; transient failures go to the next candidate instead.
    max_retries = 0
    # Free (`:free`) variants are priced at $0; a reported `usage.cost` overrides this.
    charge_basis = "free_tier"
    status_map: ClassVar[dict[int, ProviderErrorKind]] = {
        **DEFAULT_STATUS_MAP,
        402: ProviderErrorKind.QUOTA_EXHAUSTED,
        403: ProviderErrorKind.BAD_REQUEST,
        408: ProviderErrorKind.TIMEOUT,
    }

    def __init__(
        self,
        *,
        api_key: str,
        quota: FreeQuotaGuard,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            transport=transport,
            extra_headers={"X-Title": "RouteWise AI"},
        )
        self.quota = quota

    def before_send(self, request: ProviderRequest) -> None:
        if not request.model_id.endswith(FREE_SUFFIX):
            raise self._error(
                ProviderErrorKind.BAD_REQUEST,
                "non-free OpenRouter model refused (paid usage is disabled)",
                sent=False,
            )
        if not self.quota.available():
            raise self._error(
                ProviderErrorKind.QUOTA_EXHAUSTED,
                "local free-model quota guard: per-minute or daily allowance used",
                sent=False,
            )

    def after_send(self) -> None:
        self.quota.record()

    def quota_available(self) -> bool:
        return self.quota.available()

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        payload = super().build_payload(request)
        payload["usage"] = {"include": True}
        return payload

    def parse_usage(self, usage: object) -> ProviderUsage:
        base = super().parse_usage(usage)
        cost = _charge(usage.get("cost")) if isinstance(usage, dict) else None
        return ProviderUsage(base.input_tokens, base.output_tokens, reported_charge_usd=cost)

    async def sync_quota(self) -> None:
        """Best effort: seed today's usage from GET /key (`free_model_daily_requests.used`)."""
        try:
            response = await self._client.get("/key", timeout=10.0)
            data = response.json().get("data", {}) if response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError, AttributeError):
            return
        daily = data.get("free_model_daily_requests") if isinstance(data, dict) else None
        if not isinstance(daily, dict):
            return
        # The account's real daily limit (50 or 1000 depending on credits ever purchased) is
        # authoritative; the configured value is only the default until this succeeds.
        limit = daily.get("limit")
        if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
            self.quota.per_day = limit
        used = daily.get("used")
        if isinstance(used, int) and not isinstance(used, bool) and used >= 0:
            self.quota.sync_used_today(used)
