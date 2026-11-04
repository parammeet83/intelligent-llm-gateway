"""Executor: retries, backoff, Retry-After, fallbacks, circuit breaker, deadlines, accounting.

Uses scripted MockProvider instances under two fake provider names ("alpha", "beta") so the
fallback logic is exercised across providers. No network.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.config import BACKEND_ROOT
from app.providers.base import (
    ChatMessage,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from app.providers.catalog import ModelSpec, load_catalog
from app.providers.mock import MockProvider
from app.resilience.health import HealthRegistry
from app.routing.config import load_policy
from app.routing.engine import RoutingDecision, RoutingRequest, route
from app.services.executor import Executor

POLICY = load_policy(BACKEND_ROOT / "config" / "routing_policy.yaml")
_BASE = {m.key: m for m in load_catalog(BACKEND_ROOT / "config" / "models.yaml").models}
E = ProviderErrorKind


def _spec(provider: str, model_id: str, tier: str, base: str, **kw: Any) -> ModelSpec:
    # model_copy skips validation, which is what lets a non-"mock" name stay simulated here.
    return _BASE[base].model_copy(
        update={"provider": provider, "model_id": model_id, "tier": tier, "simulated": True, **kw}
    )


MODELS = [
    _spec("alpha", "a-small", "small", "mock/mock-small"),
    _spec("alpha", "a-medium", "medium", "mock/mock-medium"),
    _spec("beta", "b-medium", "medium", "mock/mock-premium"),
    _spec("beta", "b-premium", "premium", "mock/mock-premium"),
]
BY_KEY = {m.key: m for m in MODELS}
TEMPLATE = ProviderRequest(
    model_id="", messages=(ChatMessage(role="user", content="hi"),), max_output_tokens=32
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Harness:
    def __init__(self, *, deadline_s: float = 60.0, alpha_retries: int = 1) -> None:
        self.clock = Clock()
        self.sleeps: list[float] = []
        self.alpha = MockProvider(name="alpha", max_retries=alpha_retries)
        self.beta = MockProvider(name="beta", max_retries=0)
        self.health = HealthRegistry(failure_threshold=2, open_s=30, clock=self.clock)

        async def sleep(seconds: float) -> None:
            self.sleeps.append(seconds)
            self.clock.now += seconds

        self.executor = Executor(
            {"alpha": self.alpha, "beta": self.beta},
            self.health,
            deadline_s=deadline_s,
            default_timeout_s=10,
            backoff_base_s=0.5,
            backoff_cap_s=4.0,
            sleep=sleep,
            rand=lambda: 1.0,  # deterministic "full jitter" = the ceiling
            clock=self.clock,
        )

    def decide(self, **kw: Any) -> RoutingDecision:
        request = RoutingRequest(
            messages=TEMPLATE.messages, task_type="classification", max_output_tokens=32, **kw
        )
        return route(
            request,
            models=MODELS,
            enabled_providers=frozenset({"alpha", "beta"}),
            simulated_providers=frozenset({"alpha", "beta"}),
            policy=POLICY,
            health=self.health,
        )

    async def run(self, **kw: Any) -> Any:
        decision = self.decide(**kw)
        return decision, await self.executor.run(decision, BY_KEY, TEMPLATE)


def _path(result: Any) -> list[tuple[str, str, str]]:
    return [(f"{a.provider}/{a.model_id}", a.reason_code, a.status) for a in result.attempts]


async def test_primary_success() -> None:
    h = Harness()
    decision, result = await h.run()
    assert result.outcome == "SUCCEEDED"
    assert decision.selected and decision.selected.model_id == "a-small"
    assert _path(result) == [("alpha/a-small", "PRIMARY", "succeeded")]
    assert not result.fallback_used("alpha/a-small")
    attempt = result.attempts[0]
    assert attempt.simulated and attempt.cost.cost_status == "unavailable"
    assert attempt.cost.list_cost_status == "estimated"


async def test_model_reasoning_effort_is_passed_to_the_provider() -> None:
    h = Harness()
    decision = h.decide()
    models = {
        **BY_KEY,
        "alpha/a-small": BY_KEY["alpha/a-small"].model_copy(update={"reasoning_effort": "low"}),
    }
    await h.executor.run(decision, models, TEMPLATE)
    assert h.alpha.calls[-1].reasoning_effort == "low"


async def test_timeout_is_retried_with_backoff_then_succeeds() -> None:
    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(E.TIMEOUT)])
    _, result = await h.run()
    assert _path(result) == [
        ("alpha/a-small", "PRIMARY", "timeout"),
        ("alpha/a-small", "RETRY_AFTER_TIMEOUT", "succeeded"),
    ]
    assert h.sleeps == [0.5]  # base * 2**0, jitter fixed at ceiling


async def test_retry_budget_exhausted_then_fallback() -> None:
    h = Harness(alpha_retries=1)
    h.alpha.script("a-small", [MockProvider.error(E.SERVER)] * 2)
    _, result = await h.run()
    assert _path(result) == [
        ("alpha/a-small", "PRIMARY", "server_error"),
        ("alpha/a-small", "RETRY_AFTER_SERVER_ERROR", "server_error"),
        ("alpha/a-medium", "FALLBACK_AFTER_SERVER_ERROR", "succeeded"),
    ]
    assert result.fallback_used("alpha/a-small")


async def test_rate_limit_is_never_retried_on_same_model() -> None:
    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(E.RATE_LIMITED, retry_after_s=1.0)])
    _, result = await h.run()
    assert _path(result) == [
        ("alpha/a-small", "PRIMARY", "rate_limited"),
        ("alpha/a-medium", "FALLBACK_AFTER_RATE_LIMITED", "succeeded"),
    ]
    assert h.sleeps == []
    assert h.health.exclusion("alpha", "a-small") == "RATE_LIMIT_COOLDOWN"


async def test_retry_after_within_cap_is_honoured() -> None:
    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(E.SERVER, retry_after_s=2.0)])
    _, result = await h.run()
    assert h.sleeps == [2.0]
    assert result.outcome == "SUCCEEDED"


async def test_retry_after_beyond_cap_skips_retry() -> None:
    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(E.SERVER, retry_after_s=60.0)])
    _, result = await h.run()
    assert h.sleeps == []
    assert [r for _, r, _ in _path(result)] == ["PRIMARY", "FALLBACK_AFTER_SERVER_ERROR"]


async def test_invalid_credentials_skip_the_rest_of_that_provider() -> None:
    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(E.AUTH)])
    _, result = await h.run()
    assert _path(result) == [
        ("alpha/a-small", "PRIMARY", "auth_error"),
        ("beta/b-medium", "FALLBACK_AFTER_AUTH_ERROR", "succeeded"),
    ]
    assert {"model": "alpha/a-medium", "reason": "PROVIDER_AUTH_FAILED"} in result.skipped
    assert len(h.alpha.calls) == 1  # never called again with a known-bad key


async def test_malformed_response_falls_back_and_keeps_consumed_tokens() -> None:
    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(E.MALFORMED, usage=ProviderUsage(20, 32))])
    _, result = await h.run()
    first = result.attempts[0]
    assert first.status == "malformed_response"
    assert (first.input_tokens, first.output_tokens) == (20, 32)
    assert first.usage_reported and first.cost.list_cost_status == "estimated"
    assert result.outcome == "SUCCEEDED"


async def test_bad_request_stops_without_fallback() -> None:
    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(E.BAD_REQUEST)])
    _, result = await h.run()
    assert result.outcome == "NON_RETRYABLE_ERROR"
    assert len(result.attempts) == 1
    assert h.beta.calls == []


async def test_all_fallbacks_fail() -> None:
    h = Harness(alpha_retries=0)
    for provider, model in (
        (h.alpha, "a-small"),
        (h.alpha, "a-medium"),
        (h.beta, "b-medium"),
        (h.beta, "b-premium"),
    ):
        provider.script(model, [MockProvider.error(E.SERVER)])
    decision, result = await h.run()
    assert result.outcome == "ALL_CANDIDATES_FAILED"
    assert result.response is None
    assert len(result.attempts) == len(decision.eligible) == 4
    assert all(a.status == "server_error" for a in result.attempts)
    assert [a.attempt_number for a in result.attempts] == [1, 2, 3, 4]


async def test_circuit_opens_and_router_skips_model_next_time() -> None:
    h = Harness(alpha_retries=0)
    for _ in range(2):  # threshold=2
        h.alpha.script("a-small", [MockProvider.error(E.TIMEOUT)])
        await h.run()
    decision, result = await h.run()
    assert "CIRCUIT_OPEN" in decision.reason_codes
    assert result.attempts[0].model_id == "a-medium"

    h.clock.now += 30  # half-open: one probe allowed
    decision, result = await h.run()
    assert decision.selected and decision.selected.model_id == "a-small"
    assert result.outcome == "SUCCEEDED"
    assert h.health.exclusion("alpha", "a-small") is None


async def test_local_quota_refusal_is_skipped_not_an_attempt() -> None:
    h = Harness()
    h.alpha.quota_ok = False
    _, result = await h.run()
    assert all(a.provider == "beta" for a in result.attempts)
    assert {"model": "alpha/a-small", "reason": "QUOTA_EXHAUSTED"} in result.skipped
    assert h.alpha.calls == []


async def test_paid_model_in_chain_is_never_called() -> None:
    h = Harness()
    decision = h.decide()
    paid = {
        **BY_KEY,
        "alpha/a-small": BY_KEY["alpha/a-small"].model_copy(update={"billing": "paid"}),
    }
    result = await h.executor.run(decision, paid, TEMPLATE)
    assert {"model": "alpha/a-small", "reason": "PAID_MODEL_BLOCKED"} in result.skipped
    assert all(c.model_id != "a-small" for c in h.alpha.calls)


async def test_deadline_stops_further_attempts() -> None:
    h = Harness(deadline_s=1.0)
    h.alpha.script("a-small", [MockProvider.error(E.TIMEOUT)])

    async def slow_generate(request: ProviderRequest) -> Any:
        h.clock.now += 0.9  # this attempt eats most of the deadline
        raise MockProvider.error(E.TIMEOUT, provider="alpha")

    h.alpha.generate = slow_generate  # type: ignore[method-assign]
    _, result = await h.run()
    assert result.outcome == "DEADLINE_EXCEEDED"
    assert len(result.attempts) == 1


async def test_attempt_timeout_clipped_to_remaining_deadline() -> None:
    h = Harness(deadline_s=3.0)
    await h.run()
    assert h.alpha.calls[0].timeout_s == 3.0  # min(model default 10s, 3s remaining)


@pytest.mark.parametrize(("retry", "expected"), [(0, 0.5), (1, 1.0), (2, 2.0), (3, 4.0), (6, 4.0)])
def test_backoff_is_exponential_and_capped(retry: int, expected: float) -> None:
    assert Harness().executor.backoff_delay(retry, None) == expected


async def test_budget_cap_stops_attempts_that_could_overspend() -> None:
    from decimal import Decimal

    h = Harness()
    decision = h.decide()
    first = decision.eligible[0]
    assert first.worst_case_list_cost_usd is not None
    cap = Decimal(first.worst_case_list_cost_usd)  # room for exactly one primary attempt
    h.alpha.script("a-small", [MockProvider.error(E.TIMEOUT, usage=ProviderUsage(10, 32))])
    result = await h.executor.run(decision, BY_KEY, TEMPLATE, budget_cap_usd=cap)
    assert len(result.attempts) == 1  # the retry/fallbacks would exceed the reservation
    assert {"model": "alpha/a-small", "reason": "BUDGET_CONSTRAINT"} in result.skipped
    assert result.outcome == "ALL_CANDIDATES_FAILED"


async def test_timeout_without_usage_draws_its_worst_case_not_zero() -> None:
    from decimal import Decimal

    h = Harness()
    decision = h.decide()
    worst = decision.eligible[0].worst_case_list_cost_usd
    assert worst is not None
    h.alpha.script("a-small", [MockProvider.error(E.TIMEOUT)])  # no usage reported
    result = await h.executor.run(decision, BY_KEY, TEMPLATE)
    timed_out, succeeded = result.attempts
    assert timed_out.usage_unknown and timed_out.cost.list_cost_status == "unavailable"
    assert timed_out.budget_draw_usd == Decimal(worst)
    assert not succeeded.usage_unknown
    assert succeeded.budget_draw_usd == succeeded.cost.estimated_list_cost_usd


async def test_unknown_usage_counts_against_the_budget_cap() -> None:
    from decimal import Decimal

    h = Harness()
    decision = h.decide()
    worst = decision.eligible[0].worst_case_list_cost_usd
    assert worst is not None
    # Room for the primary and its retry only if the timeout were (wrongly) free.
    cap = Decimal(worst) * Decimal("1.5")
    h.alpha.script("a-small", [MockProvider.error(E.TIMEOUT)])
    result = await h.executor.run(decision, BY_KEY, TEMPLATE, budget_cap_usd=cap)
    assert len(result.attempts) == 1
    assert {"model": "alpha/a-small", "reason": "BUDGET_CONSTRAINT"} in result.skipped
    assert sum(a.budget_draw_usd or 0 for a in result.attempts) <= cap


@pytest.mark.parametrize("kind", [E.RATE_LIMITED, E.AUTH])
async def test_rejection_before_generation_draws_nothing(kind: ProviderErrorKind) -> None:
    from decimal import Decimal

    h = Harness()
    h.alpha.script("a-small", [MockProvider.error(kind)])
    _, result = await h.run()
    rejected = result.attempts[0]
    assert not rejected.usage_unknown
    assert rejected.budget_draw_usd == Decimal(0)


async def test_success_without_a_usage_block_is_unknown_usage() -> None:
    from dataclasses import replace
    from decimal import Decimal

    class NoUsageProvider(MockProvider):
        async def generate(self, request: ProviderRequest) -> ProviderResponse:
            response = await super().generate(request)
            return replace(response, usage=ProviderUsage(None, None))

    h = Harness()
    h.executor.providers["alpha"] = NoUsageProvider(name="alpha")
    decision = h.decide()
    worst = decision.eligible[0].worst_case_list_cost_usd
    assert worst is not None
    result = await h.executor.run(decision, BY_KEY, TEMPLATE)
    (attempt,) = result.attempts
    assert attempt.status == "succeeded" and attempt.usage_unknown
    assert attempt.budget_draw_usd == Decimal(worst)
