"""Provider contract: every adapter normalises success and failure the same way.

Runs each HTTP adapter against an in-memory transport. No network, no quota, no keys.
"""

from __future__ import annotations

import httpx
import pytest

from app.providers.base import (
    ATTEMPT_STATUS_FOR_KIND,
    ProviderError,
    ProviderErrorKind,
    ProviderResponse,
)
from app.providers.mock import MockProvider
from tests.providers.fakes import (
    FAKE_GROQ_KEY,
    FAKE_OPENROUTER_KEY,
    HTTP_ADAPTERS,
    MODEL_FOR,
    Recorder,
    completion,
    json_response,
    request,
)

ADAPTERS = sorted(HTTP_ADAPTERS)


def _build(name: str, *responses: httpx.Response | Exception) -> tuple[Recorder, object]:
    recorder = Recorder(*responses)
    return recorder, HTTP_ADAPTERS[name](recorder)


async def _fails(name: str, *responses: httpx.Response | Exception) -> ProviderError:
    _, provider = _build(name, *responses)
    with pytest.raises(ProviderError) as info:
        await provider.generate(request(MODEL_FOR[name]))  # type: ignore[attr-defined]
    assert info.value.provider == name
    return info.value


@pytest.mark.parametrize("name", ADAPTERS)
async def test_success_is_normalised(name: str) -> None:
    model = MODEL_FOR[name]
    _, provider = _build(name, json_response(200, completion("Hi!", model=model)))
    response: ProviderResponse = await provider.generate(request(model))  # type: ignore[attr-defined]
    assert response.content == "Hi!"
    assert response.provider == name
    assert response.model_id == model
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 5
    assert response.simulated is False
    assert response.finish_reason == "stop"
    assert response.latency_ms >= 0


@pytest.mark.parametrize("name", ADAPTERS)
async def test_missing_usage_is_none_not_zero(name: str) -> None:
    body = completion("Hi!")
    del body["usage"]
    _, provider = _build(name, json_response(200, body))
    response = await provider.generate(request(MODEL_FOR[name]))  # type: ignore[attr-defined]
    assert response.usage.input_tokens is None
    assert response.usage.output_tokens is None


@pytest.mark.parametrize("name", ADAPTERS)
async def test_timeout(name: str) -> None:
    error = await _fails(name, httpx.ReadTimeout("slow"))
    assert error.kind is ProviderErrorKind.TIMEOUT
    assert error.retryable or name == "openrouter"
    assert error.fallback_eligible


@pytest.mark.parametrize("name", ADAPTERS)
async def test_network_error(name: str) -> None:
    error = await _fails(name, httpx.ConnectError("refused"))
    assert error.kind is ProviderErrorKind.NETWORK


@pytest.mark.parametrize("name", ADAPTERS)
async def test_rate_limit_with_retry_after(name: str) -> None:
    error = await _fails(
        name,
        json_response(429, {"error": {"message": "slow down"}}, headers={"Retry-After": "7"}),
    )
    assert error.kind is ProviderErrorKind.RATE_LIMITED
    assert error.http_status == 429
    assert error.retry_after_s == 7.0
    assert not error.retryable  # never retried on the same model
    assert error.fallback_eligible


@pytest.mark.parametrize("name", ADAPTERS)
async def test_invalid_credentials(name: str) -> None:
    error = await _fails(name, json_response(401, {"error": {"message": "Invalid API Key"}}))
    assert error.kind is ProviderErrorKind.AUTH
    assert not error.retryable
    assert error.fallback_eligible


@pytest.mark.parametrize("name", ADAPTERS)
async def test_server_error(name: str) -> None:
    error = await _fails(name, json_response(503, {"error": {"message": "overloaded"}}))
    assert error.kind is ProviderErrorKind.SERVER
    assert error.retryable


@pytest.mark.parametrize("name", ADAPTERS)
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"<html>not json</html>"),
        httpx.Response(200, content=b"[1, 2, 3]"),
        json_response(200, {"choices": []}),
        json_response(200, {"choices": [{"message": {"content": 42}}]}),
        json_response(200, {"choices": [{"message": {}}]}),
    ],
    ids=["html", "json-array", "no-choices", "non-string-content", "no-content"],
)
async def test_malformed_responses(name: str, response: httpx.Response) -> None:
    error = await _fails(name, response)
    assert error.kind is ProviderErrorKind.MALFORMED
    assert error.fallback_eligible
    assert not error.retryable


@pytest.mark.parametrize("name", ADAPTERS)
async def test_empty_completion_keeps_consumed_usage(name: str) -> None:
    body = completion("   ", completion_tokens=64, finish_reason="length")
    error = await _fails(name, json_response(200, body))
    assert error.kind is ProviderErrorKind.MALFORMED
    assert error.usage is not None and error.usage.output_tokens == 64


@pytest.mark.parametrize("name", ADAPTERS)
async def test_provider_error_text_never_leaks_credentials(name: str) -> None:
    echoed = f"Invalid key {FAKE_GROQ_KEY} / {FAKE_OPENROUTER_KEY}"
    error = await _fails(name, json_response(401, {"error": {"message": echoed}}))
    rendered = f"{error} {error.message} {error!r}"
    assert FAKE_GROQ_KEY not in rendered
    assert FAKE_OPENROUTER_KEY not in rendered


@pytest.mark.parametrize("name", ADAPTERS)
async def test_long_provider_messages_truncated(name: str) -> None:
    error = await _fails(name, json_response(400, {"error": {"message": "x" * 5000}}))
    assert len(error.message) <= 200


@pytest.mark.parametrize("name", ADAPTERS)
async def test_json_mode_requested(name: str) -> None:
    recorder, provider = _build(name, json_response(200, completion('{"a": 1}')))
    await provider.generate(request(MODEL_FOR[name], fmt="json"))  # type: ignore[attr-defined]
    assert recorder.last_json()["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("name", ADAPTERS)
async def test_redirects_are_not_followed(name: str) -> None:
    recorder, provider = _build(
        name, httpx.Response(307, headers={"Location": "https://evil.example/collect"})
    )
    with pytest.raises(ProviderError) as info:
        await provider.generate(request(MODEL_FOR[name]))  # type: ignore[attr-defined]
    assert info.value.kind is ProviderErrorKind.BAD_REQUEST
    assert "redirect" in info.value.message
    assert [str(r.url.host) for r in recorder.requests] != ["evil.example"]
    assert len(recorder.requests) == 1


@pytest.mark.parametrize("name", ADAPTERS)
async def test_list_model_ids(name: str) -> None:
    _, provider = _build(name, json_response(200, {"data": [{"id": "a"}, {"id": "b"}]}))
    assert await provider.list_model_ids() == {"a", "b"}  # type: ignore[attr-defined]


@pytest.mark.parametrize("name", ADAPTERS)
async def test_list_model_ids_unknown_on_failure(name: str) -> None:
    _, provider = _build(name, httpx.ConnectError("down"))
    assert await provider.list_model_ids() is None  # type: ignore[attr-defined]


def test_every_error_kind_maps_to_a_db_attempt_status() -> None:
    assert set(ATTEMPT_STATUS_FOR_KIND) == set(ProviderErrorKind)


async def test_mock_provider_meets_the_same_contract() -> None:
    provider = MockProvider()
    response = await provider.generate(request("mock-small"))
    assert response.provider == "mock" and response.simulated is True
    assert response.content.strip()
    provider.script("mock-small", [MockProvider.error(ProviderErrorKind.TIMEOUT)])
    with pytest.raises(ProviderError) as info:
        await provider.generate(request("mock-small"))
    assert info.value.kind is ProviderErrorKind.TIMEOUT
