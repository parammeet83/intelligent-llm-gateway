import json

import pytest

from app.providers.base import ChatMessage, ProviderError, ProviderErrorKind, ProviderRequest
from app.providers.mock import SIMULATED_PREFIX, MockProvider


def _request(model: str = "mock-small", fmt: str = "text") -> ProviderRequest:
    return ProviderRequest(
        model_id=model,
        messages=(ChatMessage(role="user", content="What is 2+2?"),),
        max_output_tokens=64,
        response_format=fmt,  # type: ignore[arg-type]
    )


async def test_default_reply_is_labelled_and_deterministic() -> None:
    provider = MockProvider()
    first = await provider.generate(_request())
    second = await provider.generate(_request())
    assert first.simulated is True
    assert first.content.startswith(SIMULATED_PREFIX)
    assert first.content == second.content
    assert first.usage.input_tokens and first.usage.output_tokens
    assert first.usage.reported_charge_usd is None


async def test_json_mode_stays_parseable_and_flags_simulation() -> None:
    response = await MockProvider().generate(_request(fmt="json"))
    assert json.loads(response.content)["simulated"] is True
    assert response.simulated is True


async def test_scripted_failures_then_success() -> None:
    provider = MockProvider()
    provider.script(
        "mock-small",
        [
            MockProvider.error(ProviderErrorKind.TIMEOUT),
            MockProvider.error(ProviderErrorKind.RATE_LIMITED, retry_after_s=2.0),
        ],
    )
    with pytest.raises(ProviderError) as timeout:
        await provider.generate(_request())
    assert timeout.value.kind is ProviderErrorKind.TIMEOUT

    with pytest.raises(ProviderError) as limited:
        await provider.generate(_request())
    assert limited.value.http_status == 429
    assert limited.value.retry_after_s == 2.0

    ok = await provider.generate(_request())
    assert ok.simulated
    assert len(provider.calls) == 3


async def test_scripts_are_per_model() -> None:
    provider = MockProvider()
    provider.script("mock-premium", [MockProvider.error(ProviderErrorKind.SERVER)])
    assert (await provider.generate(_request("mock-small"))).simulated
    with pytest.raises(ProviderError):
        await provider.generate(_request("mock-premium"))


@pytest.mark.parametrize(
    ("kind", "retryable", "fallback"),
    [
        (ProviderErrorKind.TIMEOUT, True, True),
        (ProviderErrorKind.SERVER, True, True),
        (ProviderErrorKind.NETWORK, True, True),
        # Rate limits are never retried on the same model (they burn free-tier allowance).
        (ProviderErrorKind.RATE_LIMITED, False, True),
        (ProviderErrorKind.QUOTA_EXHAUSTED, False, True),
        (ProviderErrorKind.AUTH, False, True),
        (ProviderErrorKind.MALFORMED, False, True),
        (ProviderErrorKind.BAD_REQUEST, False, False),
    ],
)
def test_error_taxonomy(kind: ProviderErrorKind, retryable: bool, fallback: bool) -> None:
    error = MockProvider.error(kind)
    assert error.retryable is retryable
    assert error.fallback_eligible is fallback
