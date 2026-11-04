"""Deterministic mock provider for development and tests.

Every response carries `simulated=True`, and text responses start with "[SIMULATED]", so mock output
can't be mistaken for a real model response anywhere it surfaces (API, DB, dashboard, reports).

Tests can script outcomes per model: a queue of either ProviderError instances (raised) or
strings (returned as content). When a model's queue is empty, the default reply is used.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict, deque
from collections.abc import Iterable
from time import perf_counter

from app.providers.base import (
    Provider,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
    estimate_tokens,
)

Outcome = ProviderError | str

SIMULATED_PREFIX = "[SIMULATED]"


class MockProvider(Provider):
    name = "mock"
    simulated = True

    def __init__(
        self,
        *,
        latency_s: float = 0.0,
        name: str = "mock",
        max_retries: int = 1,
        quota_ok: bool = True,
    ) -> None:
        # `name` lets tests stand up several independent fake providers. They stay simulated.
        self.name = name
        self.max_retries = max_retries
        self.quota_ok = quota_ok
        self.latency_s = latency_s
        self._scripts: defaultdict[str, deque[Outcome]] = defaultdict(deque)
        self.calls: list[ProviderRequest] = []

    def script(self, model_id: str, outcomes: Iterable[Outcome]) -> None:
        self._scripts[model_id].extend(outcomes)

    def quota_available(self) -> bool:
        return self.quota_ok

    @staticmethod
    def error(
        kind: ProviderErrorKind,
        *,
        retry_after_s: float | None = None,
        usage: ProviderUsage | None = None,
        provider: str = "mock",
    ) -> ProviderError:
        status = {
            ProviderErrorKind.RATE_LIMITED: 429,
            ProviderErrorKind.AUTH: 401,
            ProviderErrorKind.BAD_REQUEST: 400,
            ProviderErrorKind.SERVER: 503,
        }.get(kind)
        return ProviderError(
            kind=kind,
            message=f"simulated {kind.value}",
            provider=provider,
            http_status=status,
            retry_after_s=retry_after_s,
            usage=usage,
        )

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        started = perf_counter()
        if self.latency_s:
            await asyncio.sleep(self.latency_s)

        queue = self._scripts.get(request.model_id)
        outcome: Outcome | None = queue.popleft() if queue else None
        if isinstance(outcome, ProviderError):
            outcome.provider = self.name
            raise outcome

        prompt = "\n".join(m.content for m in request.messages)
        content = outcome if outcome is not None else self._default_reply(request, prompt)
        # JSON-mode output must stay parseable, so it relies on the `simulated` flag instead.
        if request.response_format == "text" and not content.startswith(SIMULATED_PREFIX):
            content = f"{SIMULATED_PREFIX} {content}"

        output_tokens = min(estimate_tokens(content), request.max_output_tokens)
        return ProviderResponse(
            content=content,
            provider=self.name,  # simulated=True below, whatever the name
            model_id=request.model_id,
            usage=ProviderUsage(input_tokens=estimate_tokens(prompt), output_tokens=output_tokens),
            latency_ms=int((perf_counter() - started) * 1000),
            simulated=True,
            finish_reason="stop",
        )

    @staticmethod
    def _default_reply(request: ProviderRequest, prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        if request.response_format == "json":
            return f'{{"simulated": true, "model": "{request.model_id}", "digest": "{digest}"}}'
        return f"{SIMULATED_PREFIX} Response from {request.model_id} (prompt digest {digest})."
