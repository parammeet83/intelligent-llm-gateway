"""Deterministic routing: classify -> required tier -> filter candidates -> rank -> decide.

Pure functions over (request, policy, registry, health view). No I/O, no LLM calls, no clock
reads except through the health view. The same inputs always produce the same decision.

Selection rule (policy rw-2026.11-v1): among models that pass every filter, pick the one with the
lowest worst-case estimated list cost whose tier is at or above the required tier. Tier is a
capability floor, not a target. Providers listed as fallback-only (OpenRouter, with its 50/day
free allowance) rank after every primary-provider model. Ties go to lower tier, then lower
observed p95, then name. With priority=high, latency is ranked before cost. This is a
transparent heuristic; it makes no claim of producing optimal routes.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal, Protocol

from app.providers.base import ChatMessage
from app.providers.catalog import ModelSpec
from app.routing.config import TIER_ORDER, RoutingPolicyConfig, TaskType, Tier
from app.routing.features import Features, extract_features

Quality = Literal["low", "standard", "high"]
Priority = Literal["low", "normal", "high"]
_MTOK = Decimal(1_000_000)
_USD_PLACES = Decimal("0.00000001")
_COMPLEXITY_CODE: dict[str, str] = {
    "small": "LOW_COMPLEXITY",
    "medium": "MEDIUM_COMPLEXITY",
    "premium": "HIGH_COMPLEXITY",
}
_SURFACED_EXCLUSIONS = (
    "BUDGET_CONSTRAINT",
    "PRICE_UNKNOWN",
    "LATENCY_CONSTRAINT",
    "MODEL_UNAVAILABLE",
    "CIRCUIT_OPEN",
    "RATE_LIMIT_COOLDOWN",
    "QUOTA_EXHAUSTED",
    "PROVIDER_AUTH_FAILED",
)


class HealthView(Protocol):
    def exclusion(self, provider: str, model_id: str) -> str | None: ...
    def p95_ms(self, provider: str, model_id: str, min_samples: int) -> int | None: ...


@dataclass(frozen=True)
class RoutingRequest:
    messages: tuple[ChatMessage, ...]
    task_type: TaskType
    max_output_tokens: int
    response_format: Literal["text", "json"] = "text"
    quality: Quality = "standard"
    priority: Priority = "normal"
    preferred_tier: Tier | None = None
    allow_downgrade: bool = False
    latency_target_ms: int | None = None
    max_cost_usd: Decimal | None = None
    allowed_providers: frozenset[str] | None = None
    allowed_models: frozenset[str] | None = None
    # Remaining tenant shadow budget (Phase 3). None = not enforced for this request.
    budget_remaining_usd: Decimal | None = None


@dataclass(frozen=True)
class Contribution:
    feature: str
    points: float
    detail: str


@dataclass(frozen=True)
class Candidate:
    provider: str
    model_id: str
    tier: str
    eligible: bool
    exclusions: tuple[str, ...]
    worst_case_list_cost_usd: str | None
    observed_p95_ms: int | None
    simulated: bool


@dataclass(frozen=True)
class RoutingDecision:
    policy_version: str
    task_type: str
    score: float
    computed_tier: str
    required_tier: str
    contributions: tuple[Contribution, ...]
    reason_codes: tuple[str, ...]
    selected: Candidate | None
    fallback_chain: tuple[Candidate, ...]
    candidates: tuple[Candidate, ...]
    constraints: dict[str, Any] = field(default_factory=dict)

    @property
    def eligible(self) -> tuple[Candidate, ...]:
        return (self.selected, *self.fallback_chain) if self.selected else ()

    def explanation(self) -> str:
        head = (
            f"Complexity score {self.score:g}/100 -> {self.computed_tier} tier; "
            f"required tier {self.required_tier}."
        )
        if not self.selected:
            return f"{head} No model satisfied every constraint."
        excluded = sum(1 for c in self.candidates if not c.eligible)
        return (
            f"{head} Selected {self.selected.provider}/{self.selected.model_id} "
            f"({self.selected.tier}), the top-ranked of {len(self.eligible)} eligible model(s) "
            f"under policy {self.policy_version}; {excluded} excluded; "
            f"{len(self.fallback_chain)} fallback(s) available."
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["explanation"] = self.explanation()
        return data


# --- classification --------------------------------------------------------------------------


def _tier_for_score(score: float, policy: RoutingPolicyConfig) -> Tier:
    if score >= policy.tier_thresholds.premium:
        return "premium"
    if score >= policy.tier_thresholds.medium:
        return "medium"
    return "small"


def score_features(
    task_type: TaskType, features: Features, policy: RoutingPolicyConfig
) -> tuple[float, tuple[Contribution, ...]]:
    w = policy.weights
    parts: list[Contribution] = [
        Contribution("task_type_prior", policy.task_type_priors[task_type], task_type)
    ]

    def add(name: str, points: float, detail: str) -> None:
        if points > 0:
            parts.append(Contribution(name, round(points, 2), detail))

    tokens = features.estimated_input_tokens
    add(
        "input_length",
        min(w.input_tokens_max, tokens / 1000 * w.input_tokens_per_1k),
        f"~{tokens} input tokens",
    )
    if features.max_output_tokens > 4096:
        add("output_length", w.output_over_4096, f"max_output_tokens={features.max_output_tokens}")
    elif features.max_output_tokens > 1024:
        add("output_length", w.output_over_1024, f"max_output_tokens={features.max_output_tokens}")
    if features.json_output:
        add("structured_output", w.json_output, "JSON output requested")
    for name, count, per, cap in (
        ("multi_step", features.multi_step_matches, w.multi_step_per_match, w.multi_step_max),
        ("constraints", features.constraint_matches, w.constraint_per_match, w.constraint_max),
        ("reasoning_terms", features.reasoning_matches, w.reasoning_per_match, w.reasoning_max),
        ("math_terms", features.math_matches, w.math_per_match, w.math_max),
    ):
        add(name, min(cap, count * per), f"{count} match(es)")
    if features.has_code_block:
        add("code_block", w.code_block, "code block present")

    score = min(100.0, round(sum(p.points for p in parts), 2))
    return score, tuple(parts)


def _required_tier(
    request: RoutingRequest, computed: Tier, policy: RoutingPolicyConfig, reasons: list[str]
) -> Tier:
    required = computed
    if request.preferred_tier:
        preferred = request.preferred_tier
        if TIER_ORDER[preferred] > TIER_ORDER[required]:
            required = preferred
            reasons.append("CLIENT_TIER_FLOOR")
        elif TIER_ORDER[preferred] < TIER_ORDER[required]:
            if request.allow_downgrade:
                required = preferred
                reasons.append("CLIENT_TIER_DOWNGRADE")
            else:
                reasons.append("CLIENT_TIER_IGNORED")
    if request.quality == "high":
        floor = policy.high_quality_floor
        if TIER_ORDER[floor] > TIER_ORDER[required]:
            required = floor
        reasons.append("HIGH_STAKES")
    return required


# --- candidate filtering ---------------------------------------------------------------------


def worst_case_list_cost(
    model: ModelSpec, input_tokens: int, max_output_tokens: int, safety_factor: float
) -> Decimal | None:
    if model.pricing is None:
        return None
    inflated_input = Decimal(math.ceil(input_tokens * safety_factor))
    cost = (
        inflated_input * model.pricing.input_usd_per_mtok
        + Decimal(max_output_tokens) * model.pricing.output_usd_per_mtok
    ) / _MTOK
    return cost.quantize(_USD_PLACES, rounding=ROUND_HALF_UP)


def _budget_limit(request: RoutingRequest) -> Decimal | None:
    limits = [v for v in (request.max_cost_usd, request.budget_remaining_usd) if v is not None]
    return min(limits) if limits else None


def evaluate_candidate(
    model: ModelSpec,
    *,
    request: RoutingRequest,
    features: Features,
    required_tier: Tier,
    enabled_providers: frozenset[str],
    simulated_allowed: bool,
    policy: RoutingPolicyConfig,
    health: HealthView,
) -> tuple[Candidate, Decimal | None]:
    exclusions: list[str] = []
    if model.provider not in enabled_providers:
        exclusions.append("PROVIDER_DISABLED")
    if not model.enabled:
        exclusions.append("MODEL_DISABLED")
    if model.billing != "free":
        exclusions.append("PAID_MODEL_BLOCKED")
    if model.simulated and not simulated_allowed:
        exclusions.append("SIMULATED_EXCLUDED")
    if request.allowed_providers is not None and model.provider not in request.allowed_providers:
        exclusions.append("PROVIDER_NOT_ALLOWED")
    if request.allowed_models is not None and model.key not in request.allowed_models:
        exclusions.append("MODEL_NOT_ALLOWED")
    if TIER_ORDER[model.tier] < TIER_ORDER[required_tier]:
        exclusions.append("TIER_TOO_LOW")
    if request.response_format == "json" and "json_mode" not in model.capabilities:
        exclusions.append("CAPABILITY_MISSING")
    if request.max_output_tokens > model.max_output_tokens:
        exclusions.append("OUTPUT_LIMIT_EXCEEDED")
    if features.estimated_input_tokens + request.max_output_tokens > model.context_window:
        exclusions.append("CONTEXT_TOO_SMALL")

    runtime = health.exclusion(model.provider, model.model_id)
    if runtime and "PROVIDER_DISABLED" not in exclusions:
        exclusions.append(runtime)

    cost = worst_case_list_cost(
        model,
        features.estimated_input_tokens,
        request.max_output_tokens,
        policy.budget.input_estimate_safety_factor,
    )
    limit = _budget_limit(request)
    if limit is not None:
        if cost is None:
            # Unknown price can't be bounded, so a strict budget can't admit it.
            exclusions.append("PRICE_UNKNOWN")
        elif cost > limit:
            exclusions.append("BUDGET_CONSTRAINT")

    p95 = health.p95_ms(model.provider, model.model_id, policy.latency.min_samples)
    if (
        request.latency_target_ms is not None
        and p95 is not None
        and p95 > request.latency_target_ms
    ):
        exclusions.append("LATENCY_CONSTRAINT")

    candidate = Candidate(
        provider=model.provider,
        model_id=model.model_id,
        tier=model.tier,
        eligible=not exclusions,
        exclusions=tuple(exclusions),
        worst_case_list_cost_usd=str(cost) if cost is not None else None,
        observed_p95_ms=p95,
        simulated=model.simulated,
    )
    return candidate, cost


def _rank_key(
    candidate: Candidate,
    cost: Decimal | None,
    priority: Priority,
    fallback_only: frozenset[str],
    selection: str,
) -> tuple[Any, ...]:
    provider_key = 1 if candidate.provider in fallback_only else 0
    cost_key = (0, cost) if cost is not None else (1, Decimal(0))  # unpriced ranks after priced
    latency_key = (
        (0, candidate.observed_p95_ms) if candidate.observed_p95_ms is not None else (1, 0)
    )
    tier_key = TIER_ORDER[candidate.tier]
    name_key = f"{candidate.provider}/{candidate.model_id}"
    if priority == "high":
        return (provider_key, latency_key, cost_key, tier_key, name_key)
    if selection == "lowest_tier_first":
        return (provider_key, tier_key, cost_key, latency_key, name_key)
    return (provider_key, cost_key, tier_key, latency_key, name_key)


def route(
    request: RoutingRequest,
    *,
    models: list[ModelSpec],
    enabled_providers: frozenset[str],
    simulated_providers: frozenset[str],
    policy: RoutingPolicyConfig,
    health: HealthView,
) -> RoutingDecision:
    features = extract_features(
        request.messages,
        max_output_tokens=request.max_output_tokens,
        json_output=request.response_format == "json",
    )
    score, contributions = score_features(request.task_type, features, policy)
    computed = _tier_for_score(score, policy)
    reasons: list[str] = [_COMPLEXITY_CODE[computed]]
    required = _required_tier(request, computed, policy, reasons)

    # Simulated (mock) models are only routable when nothing real is enabled, or when the
    # caller explicitly restricts the request to a simulated provider.
    only_simulated = enabled_providers <= simulated_providers
    explicitly_simulated = bool(
        request.allowed_providers and request.allowed_providers & simulated_providers
    )
    simulated_allowed = only_simulated or explicitly_simulated

    evaluated = [
        evaluate_candidate(
            model,
            request=request,
            features=features,
            required_tier=required,
            enabled_providers=enabled_providers,
            simulated_allowed=simulated_allowed,
            policy=policy,
            health=health,
        )
        for model in models
    ]
    fallback_only = frozenset(policy.fallback_only_providers)
    eligible = sorted(
        ((c, cost) for c, cost in evaluated if c.eligible),
        key=lambda pair: _rank_key(
            pair[0], pair[1], request.priority, fallback_only, policy.selection
        ),
    )
    candidates = tuple(c for c, _ in evaluated)

    # Constraint-driven exclusions are surfaced as decision-level reasons too.
    excluded_codes = {code for c in candidates for code in c.exclusions}
    reasons.extend(code for code in _SURFACED_EXCLUSIONS if code in excluded_codes)

    selected = eligible[0][0] if eligible else None
    if selected is None:
        reasons.append("NO_ELIGIBLE_MODEL")
    else:
        if request.priority == "high":
            reasons.append("LATENCY_PRIORITY")
        elif policy.selection == "lowest_tier_first":
            reasons.append("LOWEST_TIER_FIRST")
        else:
            reasons.append("CHEAPEST_ELIGIBLE")
        if TIER_ORDER[selected.tier] > TIER_ORDER[required]:
            reasons.append("TIER_ESCALATED")
        if selected.simulated:
            reasons.append("SIMULATED_PROVIDER")
        if selected.provider in fallback_only:
            reasons.append("PRIMARY_PROVIDERS_INELIGIBLE")

    limit = _budget_limit(request)
    return RoutingDecision(
        policy_version=policy.version,
        task_type=request.task_type,
        score=score,
        computed_tier=computed,
        required_tier=required,
        contributions=contributions,
        reason_codes=tuple(dict.fromkeys(reasons)),
        selected=selected,
        fallback_chain=tuple(c for c, _ in eligible[1:]),
        candidates=candidates,
        constraints={
            "quality": request.quality,
            "priority": request.priority,
            "preferred_tier": request.preferred_tier,
            "allow_downgrade": request.allow_downgrade,
            "latency_target_ms": request.latency_target_ms,
            "budget_limit_usd": str(limit) if limit is not None else None,
            "response_format": request.response_format,
            "estimated_input_tokens": features.estimated_input_tokens,
        },
    )
