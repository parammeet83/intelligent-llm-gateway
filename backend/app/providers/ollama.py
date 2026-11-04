"""Ollama adapter (local inference only).

Docs (verified 2026-11-03): https://docs.ollama.com/api/openai-compatibility
- Endpoint: {OLLAMA_BASE_URL}/v1/chat/completions; supports max_tokens, temperature, and JSON mode.
- A local server ignores the API key; none is sent.

Settings refuse a non-loopback OLLAMA_BASE_URL and refuse Ollama entirely in production, so a
deployed gateway never depends on, or exposes, a developer's machine.
"""

from __future__ import annotations

import httpx

from app.providers.http import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    name = "ollama"
    max_retries = 1
    # Runs on local hardware: no provider charge exists.
    charge_basis = "free_tier"

    def __init__(self, *, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(base_url=base_url.rstrip("/") + "/v1", api_key=None, transport=transport)
