"""Groq adapter. Docs (verified 2026-11-03): https://console.groq.com/docs/api-reference

- Endpoint: https://api.groq.com/openai/v1/chat/completions (OpenAI-compatible).
- `max_completion_tokens` replaces the deprecated `max_tokens`.
- Usage reports tokens only, never dollars. The actual charge is `free_tier` only when the
  operator declares the key is on Groq's Free plan (GROQ_BILLING_PLAN=free); otherwise unknown.
- Status codes: https://console.groq.com/docs/errors. 422 is documented as "semantic problems or
  model hallucinations ... or retry", treated as a malformed model output (fallback, no retry).
  498 means Flex-tier capacity, treated as a transient server error.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from app.providers.base import ChargeBasis, ProviderErrorKind, ProviderRequest
from app.providers.http import DEFAULT_STATUS_MAP, OpenAICompatibleProvider

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    max_retries = 1
    status_map: ClassVar[dict[int, ProviderErrorKind]] = {
        **DEFAULT_STATUS_MAP,
        422: ProviderErrorKind.MALFORMED,
        498: ProviderErrorKind.SERVER,
    }

    def __init__(
        self,
        *,
        api_key: str,
        charge_basis: ChargeBasis,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base_url=GROQ_BASE_URL, api_key=api_key, transport=transport)
        self.charge_basis = charge_basis

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        payload = super().build_payload(request)
        payload["max_completion_tokens"] = payload.pop("max_tokens")
        if request.reasoning_effort is not None:
            # GPT-OSS only (https://console.groq.com/docs/reasoning): `reasoning_format` isn't
            # supported there, `include_reasoning` is. The reasoning text is never used or stored,
            # so it isn't requested.
            payload["reasoning_effort"] = request.reasoning_effort
            payload["include_reasoning"] = False
        return payload
