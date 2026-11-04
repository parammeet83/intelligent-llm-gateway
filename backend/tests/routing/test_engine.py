"""Routing engine: deterministic classification, filtering, ranking, and fallback chains."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_ROOT
from app.providers.base import ChatMessage
from app.providers.catalog import ModelSpec, load_catalog
from app.routing.config import TIER_ORDER, RoutingPolicyConfig, load_policy
from app.routing.engine import RoutingDecision, RoutingRequest, route, worst_case_list_cost

POLICY = load_policy(BACKEND_ROOT / "config" / "routing_policy.yaml")
CATALOG = load_catalog(BACKEND_ROOT / "config" / "models.yaml")
REAL = frozenset({"groq", "openrouter"})


class FakeHealth:
    def __init__(
        self,
        exclusions: dict[str, str] | None = None,
        p95: dict[str, int] | None = None,
    ) -> None:
        self.exclusions = exclusions or {}
        self.p95 = p95 or {}

    def exclusion(self, provider: str, model_id: str) -> str | None:
        return self.exclusions.get(f"{provider}/{model_id}") or self.exclusions.get(provider)

    def p95_ms(self, provider: str, model_id: str, min_samples: int) -> int | None:
        return self.p95.get(f"{provider}/{model_id}")


def req(text: str = "Is this review positive? 'Great product.'", **kw: Any) -> RoutingRequest:
    defaults: dict[str, Any] = {"task_type": "classification", "max_output_tokens": 256}
    defaults.update(kw)
    return RoutingRequest(messages=(ChatMessage(role="user", content=text),), **defaults)


def decide(
    request: RoutingRequest,
    *,
    enabled: frozenset[str] = REAL,
    health: FakeHealth | None = None,
    models: list[ModelSpec] | None = None,
    policy: RoutingPolicyConfig = POLICY,
) -> RoutingDecision:
    return route(
        request,
        models=models if models is not None else CATALOG.models,
        enabled_providers=enabled,
        simulated_providers=frozenset({"mock"}),
        policy=policy,
        health=health or FakeHealth(),
    )


def _cand(decision: RoutingDecision, key: str) -> Any:
    return next(c for c in decision.candidates if f"{c.provider}/{c.model_id}" == key)


HARD = (
    "Prove that the algorithm terminates, then derive its time complexity step by step. "
    "Compare it with merge sort, analyse the trade-offs, and justify which is optimal. "
    "1. State the invariant\n2. Prove it\n3. Conclude. You must be rigorous."
)


# --- determinism & classification ------------------------------------------------------------


def test_same_input_same_decision() -> None:
    a = decide(req(HARD, task_type="reasoning")).to_dict()
    b = decide(req(HARD, task_type="reasoning")).to_dict()
    assert a == b
    json.dumps(a)  # decision is JSON-serialisable for request_logs.decision


def test_simple_request_is_low_complexity() -> None:
    d = decide(req())
    assert d.computed_tier == "small"
    assert d.required_tier == "small"
    assert "LOW_COMPLEXITY" in d.reason_codes
    assert d.contributions[0].feature == "task_type_prior"


def test_hard_reasoning_request_requires_premium() -> None:
    d = decide(req(HARD, task_type="reasoning"))
    assert d.score >= POLICY.tier_thresholds.premium
    assert d.required_tier == "premium"
    assert "HIGH_COMPLEXITY" in d.reason_codes
    assert d.selected is not None and d.selected.tier == "premium"
    features = {c.feature for c in d.contributions}
    assert {"reasoning_terms", "multi_step", "constraints"} <= features


def test_score_is_sum_of_contributions_capped_at_100() -> None:
    d = decide(req(HARD * 20, task_type="reasoning", max_output_tokens=8000))
    assert d.score == min(100.0, round(sum(c.points for c in d.contributions), 2))
    assert d.score <= 100


def test_weights_and_thresholds_are_configurable() -> None:
    strict = POLICY.model_copy(
        update={"tier_thresholds": POLICY.tier_thresholds.model_copy(update={"medium": 1})}
    )
    assert decide(req(), policy=strict).computed_tier == "medium"


@pytest.mark.parametrize(
    "bad",
    [
        {"tier_thresholds": {"medium": 70, "premium": 40}},
        {"task_type_priors": {"chat": 1}},
    ],
)
def test_invalid_policy_config_rejected(bad: dict[str, Any]) -> None:
    data = POLICY.model_dump()
    data.update(bad)
    with pytest.raises(ValidationError):
        RoutingPolicyConfig.model_validate(data)


# --- tier floors & client preferences ------------------------------------------------------


def test_high_quality_is_high_stakes_premium() -> None:
    d = decide(req(quality="high"))
    assert d.required_tier == "premium"
    assert "HIGH_STAKES" in d.reason_codes


def test_preferred_tier_raises_floor() -> None:
    d = decide(req(preferred_tier="medium"))
    assert d.required_tier == "medium"
    assert "CLIENT_TIER_FLOOR" in d.reason_codes


def test_downgrade_only_when_allowed() -> None:
    ignored = decide(req(HARD, task_type="reasoning", preferred_tier="small"))
    assert ignored.required_tier == "premium"
    assert "CLIENT_TIER_IGNORED" in ignored.reason_codes

    allowed = decide(req(HARD, task_type="reasoning", preferred_tier="small", allow_downgrade=True))
    assert allowed.required_tier == "small"
    assert "CLIENT_TIER_DOWNGRADE" in allowed.reason_codes


def test_high_quality_floor_beats_downgrade() -> None:
    d = decide(req(preferred_tier="small", allow_downgrade=True, quality="high"))
    assert d.required_tier == "premium"


# --- selection & ranking --------------------------------------------------------------------


def test_selects_cheapest_eligible_primary_model_and_says_so() -> None:
    d = decide(req())
    assert d.selected is not None
    primary = [
        c
        for c in d.eligible
        if c.worst_case_list_cost_usd is not None
        and c.provider not in POLICY.fallback_only_providers
    ]
    cheapest = min(primary, key=lambda c: Decimal(c.worst_case_list_cost_usd))  # type: ignore[arg-type]
    assert d.selected == cheapest
    assert "CHEAPEST_ELIGIBLE" in d.reason_codes


def test_fallback_only_provider_ranks_after_all_primary_models() -> None:
    d = decide(req())
    providers = [c.provider for c in d.eligible]
    first_openrouter = providers.index("openrouter")
    assert all(p != "openrouter" for p in providers[:first_openrouter])
    assert all(p == "openrouter" for p in providers[first_openrouter:])
    assert "PRIMARY_PROVIDERS_INELIGIBLE" not in d.reason_codes


def test_fallback_only_provider_selected_when_primaries_ineligible() -> None:
    d = decide(req(), health=FakeHealth(exclusions={"groq": "PROVIDER_AUTH_FAILED"}))
    assert d.selected is not None and d.selected.provider == "openrouter"
    assert "PRIMARY_PROVIDERS_INELIGIBLE" in d.reason_codes
    assert "PROVIDER_AUTH_FAILED" in d.reason_codes


def test_unpriced_models_rank_after_priced_without_budget() -> None:
    # Every enabled Groq model is priced today, so add an unpriced one.
    unpriced = next(m for m in CATALOG.models if m.key == "groq/openai/gpt-oss-20b").model_copy(
        update={"model_id": "unpriced-small", "pricing": None}
    )
    d = decide(req(), models=[*CATALOG.models, unpriced])
    # Within the primary-provider group: every priced model before any unpriced one.
    primary = [c for c in d.eligible if c.provider not in POLICY.fallback_only_providers]
    costs = [c.worst_case_list_cost_usd for c in primary]
    assert None in costs
    first_unpriced = costs.index(None)
    assert all(c is not None for c in costs[:first_unpriced])
    assert all(c is None for c in costs[first_unpriced:])


def test_tier_escalation_reported_when_cheapest_is_above_required() -> None:
    d = decide(req())
    assert d.selected is not None
    if TIER_ORDER[d.selected.tier] > TIER_ORDER[d.required_tier]:
        assert "TIER_ESCALATED" in d.reason_codes


def test_high_priority_ranks_by_observed_latency() -> None:
    health = FakeHealth(p95={"groq/openai/gpt-oss-20b": 900, "groq/openai/gpt-oss-120b": 300})
    normal = decide(req(), health=health)
    assert normal.selected is not None and normal.selected.model_id == "openai/gpt-oss-20b"
    fast = decide(req(priority="high"), health=health)
    assert fast.selected is not None and fast.selected.model_id == "openai/gpt-oss-120b"
    assert "LATENCY_PRIORITY" in fast.reason_codes


# --- exclusions -----------------------------------------------------------------------------


def test_disabled_providers_and_preview_models_excluded() -> None:
    d = decide(req())
    assert "PROVIDER_DISABLED" in _cand(d, "ollama/qwen2.5:1.5b").exclusions
    assert "MODEL_DISABLED" in _cand(d, "groq/qwen/qwen3.8-27b").exclusions


def test_paid_model_never_eligible() -> None:
    paid = CATALOG.models[0].model_copy(update={"model_id": "paid-x", "billing": "paid"})
    d = decide(req(), models=[*CATALOG.models, paid])
    assert "PAID_MODEL_BLOCKED" in _cand(d, "groq/paid-x").exclusions
    assert all(c.model_id != "paid-x" for c in d.eligible)


def test_json_requires_json_capability() -> None:
    d = decide(req(quality="high", response_format="json"))
    assert (
        "CAPABILITY_MISSING"
        in _cand(d, "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free").exclusions
    )
    assert all(c.model_id != "nvidia/nemotron-3-ultra-550b-a55b:free" for c in d.eligible)


def test_output_and_context_limits() -> None:
    d = decide(req(max_output_tokens=20000))
    assert "OUTPUT_LIMIT_EXCEEDED" in _cand(d, "openrouter/liquid/lfm-2.5-2.6b:free").exclusions
    long_text = "word " * 300_000  # ~375k tokens
    d = decide(req(long_text))
    assert "CONTEXT_TOO_SMALL" in _cand(d, "groq/openai/gpt-oss-20b").exclusions


def test_budget_excludes_expensive_and_unpriced_models() -> None:
    d = decide(req(quality="high", max_cost_usd=Decimal("0.0002")))
    nemotron = _cand(d, "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free")
    assert "BUDGET_CONSTRAINT" in nemotron.exclusions
    assert "BUDGET_CONSTRAINT" in d.reason_codes
    small = decide(req(max_cost_usd=Decimal("1")))
    assert "PRICE_UNKNOWN" in _cand(small, "groq/llama-3.1-8b-instant").exclusions
    assert "PRICE_UNKNOWN" in small.reason_codes
    for c in small.eligible:
        assert c.worst_case_list_cost_usd is not None
        assert Decimal(c.worst_case_list_cost_usd) <= Decimal("1")


def test_tenant_budget_remaining_is_also_a_limit() -> None:
    d = decide(req(budget_remaining_usd=Decimal("0")))
    assert d.selected is None
    assert "NO_ELIGIBLE_MODEL" in d.reason_codes


def test_worst_case_cost_uses_inflated_input_and_full_output() -> None:
    model = next(m for m in CATALOG.models if m.model_id == "openai/gpt-oss-20b")
    # ceil(1000 * 1.25) * 0.075/M + 500 * 0.30/M
    assert worst_case_list_cost(model, 1000, 500, 1.25) == Decimal("0.00024375")
    unpriced = next(m for m in CATALOG.models if m.model_id == "llama-3.1-8b-instant")
    assert worst_case_list_cost(unpriced, 1000, 500, 1.25) is None


def test_latency_target_uses_observed_p95_only() -> None:
    slow = FakeHealth(p95={"groq/openai/gpt-oss-120b": 5000})
    d = decide(req(quality="high", latency_target_ms=2000), health=slow)
    assert "LATENCY_CONSTRAINT" in _cand(d, "groq/openai/gpt-oss-120b").exclusions
    # No measurements = not excluded (no fabricated latency figures).
    d = decide(req(quality="high", latency_target_ms=2000))
    assert "LATENCY_CONSTRAINT" not in _cand(d, "groq/openai/gpt-oss-120b").exclusions


def test_runtime_health_exclusions_propagate() -> None:
    health = FakeHealth(
        exclusions={"groq/openai/gpt-oss-20b": "CIRCUIT_OPEN", "openrouter": "QUOTA_EXHAUSTED"}
    )
    d = decide(req(), health=health)
    assert "CIRCUIT_OPEN" in _cand(d, "groq/openai/gpt-oss-20b").exclusions
    assert all(c.provider != "openrouter" for c in d.eligible)
    assert {"CIRCUIT_OPEN", "QUOTA_EXHAUSTED"} <= set(d.reason_codes)


def test_allowed_providers_and_models() -> None:
    d = decide(req(allowed_providers=frozenset({"openrouter"})))
    assert d.eligible and all(c.provider == "openrouter" for c in d.eligible)
    d = decide(req(allowed_models=frozenset({"groq/openai/gpt-oss-120b"})))
    assert [f"{c.provider}/{c.model_id}" for c in d.eligible] == ["groq/openai/gpt-oss-120b"]


# --- simulated providers --------------------------------------------------------------------


def test_mock_routable_when_it_is_the_only_provider() -> None:
    d = decide(req(), enabled=frozenset({"mock"}))
    assert d.selected is not None and d.selected.simulated
    assert "SIMULATED_PROVIDER" in d.reason_codes


def test_mock_never_mixed_into_real_routing_unless_requested() -> None:
    d = decide(req(), enabled=frozenset({"mock", "groq"}))
    assert all(not c.simulated for c in d.eligible)
    assert "SIMULATED_EXCLUDED" in _cand(d, "mock/mock-small").exclusions
    d = decide(req(allowed_providers=frozenset({"mock"})), enabled=frozenset({"mock", "groq"}))
    assert d.selected is not None and d.selected.provider == "mock"


# --- fallback chain obeys the same rules ------------------------------------------------


@pytest.mark.parametrize(
    "request_kw",
    [
        {},
        {"quality": "high"},
        {"response_format": "json"},
        {"max_cost_usd": Decimal("0.0005")},
        {"preferred_tier": "medium", "response_format": "json"},
        {"allowed_providers": frozenset({"groq"})},
    ],
)
def test_every_fallback_satisfies_every_constraint(request_kw: dict[str, Any]) -> None:
    request = req(**request_kw)
    d = decide(request)
    for c in d.eligible:
        assert c.eligible and not c.exclusions
        assert TIER_ORDER[c.tier] >= TIER_ORDER[d.required_tier]
        if request.max_cost_usd is not None:
            assert c.worst_case_list_cost_usd is not None
            assert Decimal(c.worst_case_list_cost_usd) <= request.max_cost_usd
        if request.allowed_providers:
            assert c.provider in request.allowed_providers
        assert not c.simulated
    assert d.selected not in d.fallback_chain


def test_no_eligible_model_is_explained() -> None:
    d = decide(req(allowed_providers=frozenset({"nobody"})))
    assert d.selected is None and d.fallback_chain == ()
    assert "NO_ELIGIBLE_MODEL" in d.reason_codes
    assert "No model satisfied" in d.explanation()
    assert all("PROVIDER_NOT_ALLOWED" in c.exclusions for c in d.candidates)


def test_lowest_tier_first_keeps_simple_requests_on_small_models() -> None:
    tier_first = POLICY.model_copy(update={"selection": "lowest_tier_first"})
    d = decide(req(), policy=tier_first)
    assert d.selected is not None and d.selected.tier == "small"
    assert "LOWEST_TIER_FIRST" in d.reason_codes and "TIER_ESCALATED" not in d.reason_codes
    tiers = [
        TIER_ORDER[c.tier] for c in d.eligible if c.provider not in POLICY.fallback_only_providers
    ]
    assert tiers == sorted(tiers)


def test_complex_json_requests_now_have_a_premium_fallback() -> None:
    d = decide(req(HARD, task_type="reasoning", response_format="json"))
    assert d.selected is not None and d.selected.model_id == "openai/gpt-oss-120b"
    chain = [f"{c.provider}/{c.model_id}" for c in d.fallback_chain]
    assert chain == ["openrouter/nvidia/nemotron-3.5-super-vl:free"]
