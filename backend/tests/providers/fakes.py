"""Builders for provider adapters wired to an in-memory HTTP transport (no network)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from app.providers.base import ChatMessage, Provider, ProviderRequest
from app.providers.groq import GroqProvider
from app.providers.ollama import OllamaProvider
from app.providers.openrouter import FreeQuotaGuard, OpenRouterProvider

FAKE_GROQ_KEY = "gsk_testkeyAAAAAAAAAAAAAAAAAAAAAA"
FAKE_OPENROUTER_KEY = "sk-or-v1-testkeyBBBBBBBBBBBBBBBBBBBB"

Handler = Callable[[httpx.Request], httpx.Response]


def completion(
    content: str | None = "Hello there.",
    *,
    model: str = "m",
    prompt_tokens: int | None = 12,
    completion_tokens: int | None = 5,
    finish_reason: str = "stop",
    **usage_extra: Any,
) -> dict[str, Any]:
    usage: dict[str, Any] = {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}
    usage.update(usage_extra)
    return {
        "id": "cmpl-1",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage,
    }


def json_response(status: int, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body).encode(), headers=headers or {})


class Recorder:
    """A transport handler that records requests and replays queued responses."""

    def __init__(self, *responses: httpx.Response | Exception | Handler) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, httpx.Response):
            return item(request)
        return item

    def last_json(self) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[-1].content)
        return body


def groq(recorder: Recorder, *, charge_basis: str = "free_tier") -> GroqProvider:
    return GroqProvider(
        api_key=FAKE_GROQ_KEY,
        charge_basis=charge_basis,  # type: ignore[arg-type]
        transport=httpx.MockTransport(recorder),
    )


def openrouter(
    recorder: Recorder, *, per_minute: int = 20, per_day: int = 50
) -> OpenRouterProvider:
    return OpenRouterProvider(
        api_key=FAKE_OPENROUTER_KEY,
        quota=FreeQuotaGuard(per_minute=per_minute, per_day=per_day),
        transport=httpx.MockTransport(recorder),
    )


def ollama(recorder: Recorder) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://localhost:11434", transport=httpx.MockTransport(recorder)
    )


def request(
    model: str = "m", *, fmt: str = "text", max_tokens: int = 64, timeout_s: float = 5.0
) -> ProviderRequest:
    return ProviderRequest(
        model_id=model,
        messages=(
            ChatMessage(role="system", content="Be brief."),
            ChatMessage(role="user", content="Say hello."),
        ),
        max_output_tokens=max_tokens,
        response_format=fmt,  # type: ignore[arg-type]
        timeout_s=timeout_s,
    )


HTTP_ADAPTERS: dict[str, Callable[[Recorder], Provider]] = {
    "groq": groq,
    "openrouter": openrouter,
    "ollama": ollama,
}
# Model IDs each adapter accepts (OpenRouter refuses anything without `:free`).
MODEL_FOR = {
    "groq": "openai/gpt-oss-20b",
    "openrouter": "google/gemma-4-31b-it:free",
    "ollama": "qwen2.5:1.5b",
}
