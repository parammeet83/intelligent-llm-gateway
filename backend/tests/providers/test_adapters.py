"""Provider-specific behaviour (payload dialect, status semantics, quota, cost reporting)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from app.providers.base import ProviderError, ProviderErrorKind
from app.providers.http import parse_retry_after
from app.providers.openrouter import FreeQuotaGuard
from tests.providers.fakes import (
    FAKE_GROQ_KEY,
    FAKE_OPENROUTER_KEY,
    Recorder,
    completion,
    groq,
    json_response,
    ollama,
    openrouter,
    request,
)

FREE = "google/gemma-4-31b-it:free"

# --- Groq ---------------------------------------------------------------------------------


async def test_groq_payload_and_endpoint() -> None:
    recorder = Recorder(json_response(200, completion()))
    await groq(recorder).generate(request("openai/gpt-oss-20b", max_tokens=99))
    sent = recorder.requests[-1]
    assert str(sent.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {FAKE_GROQ_KEY}"
    body = recorder.last_json()
    assert body["max_completion_tokens"] == 99
    assert "max_tokens" not in body
    assert body["temperature"] == 0.0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


async def test_groq_sends_reasoning_effort_only_when_set() -> None:
    from dataclasses import replace

    recorder = Recorder(json_response(200, completion()))
    provider = groq(recorder)
    await provider.generate(request("openai/gpt-oss-20b"))
    assert "reasoning_effort" not in recorder.last_json()
    assert "include_reasoning" not in recorder.last_json()
    await provider.generate(replace(request("openai/gpt-oss-20b"), reasoning_effort="low"))
    body = recorder.last_json()
    assert body["reasoning_effort"] == "low"
    assert body["include_reasoning"] is False  # reasoning text is never used or stored


async def test_reasoning_tokens_are_parsed_when_reported() -> None:
    body = completion(completion_tokens=50, completion_tokens_details={"reasoning_tokens": 40})
    recorder = Recorder(json_response(200, body))
    response = await groq(recorder).generate(request())
    assert (response.usage.output_tokens, response.usage.reasoning_tokens) == (50, 40)
    recorder = Recorder(json_response(200, completion()))
    assert (await groq(recorder).generate(request())).usage.reasoning_tokens is None


async def test_groq_reports_tokens_but_never_a_dollar_charge() -> None:
    recorder = Recorder(json_response(200, completion(cost=0.5)))  # even if a cost field appeared
    response = await groq(recorder).generate(request())
    assert response.usage.reported_charge_usd is None


@pytest.mark.parametrize("basis", ["free_tier", "unavailable"])
def test_groq_charge_basis_comes_from_operator_config(basis: str) -> None:
    assert groq(Recorder(json_response(200, {})), charge_basis=basis).charge_basis == basis


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (403, ProviderErrorKind.AUTH),
        (404, ProviderErrorKind.MODEL_NOT_FOUND),
        (413, ProviderErrorKind.BAD_REQUEST),
        (422, ProviderErrorKind.MALFORMED),
        (498, ProviderErrorKind.SERVER),
        (502, ProviderErrorKind.SERVER),
    ],
)
async def test_groq_status_mapping(status: int, kind: ProviderErrorKind) -> None:
    recorder = Recorder(json_response(status, {"error": {"message": "x", "type": "t"}}))
    with pytest.raises(ProviderError) as info:
        await groq(recorder).generate(request())
    assert info.value.kind is kind


# --- OpenRouter ---------------------------------------------------------------------------


async def test_openrouter_payload_requests_usage_and_identifies_app() -> None:
    recorder = Recorder(json_response(200, completion()))
    await openrouter(recorder).generate(request(FREE))
    sent = recorder.requests[-1]
    assert str(sent.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {FAKE_OPENROUTER_KEY}"
    assert sent.headers["x-title"] == "RouteWise AI"
    assert recorder.last_json()["usage"] == {"include": True}


async def test_openrouter_reported_cost_is_parsed_exactly() -> None:
    recorder = Recorder(json_response(200, completion(cost=0.0000123)))
    response = await openrouter(recorder).generate(request(FREE))
    assert response.usage.reported_charge_usd == Decimal("0.0000123")


@pytest.mark.parametrize("bad_cost", [-1, "abc", True, None, float("nan")])
async def test_openrouter_invalid_cost_is_unknown(bad_cost: object) -> None:
    recorder = Recorder(json_response(200, completion(cost=bad_cost)))
    response = await openrouter(recorder).generate(request(FREE))
    assert response.usage.reported_charge_usd is None


async def test_openrouter_refuses_non_free_models_without_calling() -> None:
    recorder = Recorder(json_response(200, completion()))
    with pytest.raises(ProviderError) as info:
        await openrouter(recorder).generate(request("openai/gpt-oss-120b"))
    assert info.value.kind is ProviderErrorKind.BAD_REQUEST
    assert info.value.sent is False
    assert recorder.requests == []


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (402, ProviderErrorKind.QUOTA_EXHAUSTED),
        (403, ProviderErrorKind.BAD_REQUEST),  # moderation / guardrail: same request fails anywhere
        (408, ProviderErrorKind.TIMEOUT),
        (502, ProviderErrorKind.SERVER),
    ],
)
async def test_openrouter_status_mapping(status: int, kind: ProviderErrorKind) -> None:
    recorder = Recorder(json_response(status, {"error": {"code": status, "message": "x"}}))
    with pytest.raises(ProviderError) as info:
        await openrouter(recorder).generate(request(FREE))
    assert info.value.kind is kind


async def test_openrouter_error_inside_http_200() -> None:
    body = {"error": {"code": 502, "message": "upstream model failed"}}
    with pytest.raises(ProviderError) as info:
        await openrouter(Recorder(json_response(200, body))).generate(request(FREE))
    assert info.value.kind is ProviderErrorKind.SERVER
    assert info.value.http_status == 502


async def test_openrouter_never_retries_on_same_model() -> None:
    assert openrouter(Recorder(json_response(200, {}))).max_retries == 0


async def test_openrouter_daily_guard_counts_failures_and_stops_calling() -> None:
    recorder = Recorder(
        json_response(503, {"error": {"code": 503, "message": "down"}}),
        json_response(200, completion()),
    )
    provider = openrouter(recorder, per_day=2)
    with pytest.raises(ProviderError):
        await provider.generate(request(FREE))  # failed, but still counted
    await provider.generate(request(FREE))
    assert not provider.quota_available()
    with pytest.raises(ProviderError) as info:
        await provider.generate(request(FREE))
    assert info.value.kind is ProviderErrorKind.QUOTA_EXHAUSTED
    assert info.value.sent is False
    assert len(recorder.requests) == 2


def test_quota_guard_per_minute_window_and_daily_reset() -> None:
    now = [0.0]
    day = [date(2026, 11, 3)]
    guard = FreeQuotaGuard(per_minute=2, per_day=3, clock=lambda: now[0], today=lambda: day[0])
    guard.record()
    guard.record()
    assert not guard.available()  # 2 in the last minute
    now[0] = 61.0
    assert guard.available()
    guard.record()
    assert not guard.available()  # 3 today
    day[0] = date(2026, 11, 4)
    assert guard.available()


async def test_openrouter_sync_quota_from_key_endpoint() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/v1/key"
        return json_response(
            200, {"data": {"free_model_daily_requests": {"used": 50, "limit": 50, "remaining": 0}}}
        )

    provider = openrouter(Recorder(handler))
    await provider.sync_quota()
    assert not provider.quota_available()


async def test_openrouter_sync_quota_ignores_failures() -> None:
    provider = openrouter(Recorder(httpx.ConnectError("down")))
    await provider.sync_quota()
    assert provider.quota_available()


# --- Ollama -------------------------------------------------------------------------------


async def test_ollama_uses_local_v1_endpoint_without_credentials() -> None:
    recorder = Recorder(json_response(200, completion()))
    await ollama(recorder).generate(request("qwen2.5:1.5b"))
    sent = recorder.requests[-1]
    assert str(sent.url) == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in sent.headers
    assert recorder.last_json()["max_tokens"] == 64


# --- Retry-After --------------------------------------------------------------------------


def test_retry_after_parsing() -> None:
    now = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after("Tue, 03 Nov 2026 12:00:30 GMT", now=now) == 30.0
    assert parse_retry_after("Tue, 03 Nov 2026 11:00:00 GMT", now=now) == 0.0
    assert parse_retry_after("soon") is None
    assert parse_retry_after(None) is None


async def test_openrouter_sync_quota_adopts_account_daily_limit() -> None:
    body = {"data": {"free_model_daily_requests": {"used": 3, "limit": 1000, "remaining": 997}}}
    provider = openrouter(Recorder(json_response(200, body)), per_day=50)
    await provider.sync_quota()
    assert provider.quota.per_day == 1000
    assert provider.quota.used_today == 3
