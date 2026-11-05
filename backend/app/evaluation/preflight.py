"""Worst-case quota preflight for a benchmark run (v5.1+). Offline: no network, no provider calls.

Maximum provider attempts per gateway request, derived from the executor's control flow
(services/executor.py): the executor iterates the decision's eligible models in order; each model
gets one attempt plus at most `provider.max_retries` same-model retries (transient errors only);
it moves to the next model only on a fallback-eligible error; and it never revisits a model. So

    max_attempts(request) = sum over eligible models m of (1 + max_retries(provider(m)))

Health exclusions, the deadline and Retry-After can only reduce this, never increase it, so the
routing decision computed here with no health data is an upper bound for the live run. Each
attempt reserves input_token_bound(prompt) + the case's max_output_tokens (the executor sends the
case's max_output_tokens unchanged on every attempt).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.evaluation.dataset import Dataset
from app.evaluation.pacing import DailyBudget, QuotaLedger, input_token_bound
from app.providers.base import ChatMessage, Provider
from app.providers.catalog import load_catalog
from app.routing.config import load_policy
from app.routing.engine import RoutingRequest, route

MAX_SANE_RETRIES = 10


class _NoHealth:
    def exclusion(self, provider: str, model_id: str) -> None:
        return None

    def p95_ms(self, provider: str, model_id: str, min_samples: int) -> None:
        return None


@dataclass
class Preflight:
    gateway_requests: int = 0
    max_provider_attempts: int = 0
    input_reservation_tokens: int = 0
    output_reservation_tokens: int = 0
    largest_attempt_tokens: int = 0
    max_attempts_per_request: int = 0
    per_strategy: dict[str, dict[str, int]] = field(default_factory=dict)
    attempts_histogram: dict[int, int] = field(default_factory=dict)
    bounded: bool = True
    constraints: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_reservation_tokens(self) -> int:
        return self.input_reservation_tokens + self.output_reservation_tokens

    @property
    def ok(self) -> bool:
        return not self.problems


def plan(
    dataset: Dataset,
    strategies: list[str],
    settings: Settings,
    providers: dict[str, Provider],
    quota: dict[str, Any],
    *,
    only: set[tuple[str, str]] | None = None,
) -> Preflight:
    """Attempt and token bounds for every (strategy, case) under the live routing configuration.
    `only` (v5.2.4 recovery) restricts the plan to these (case ID, strategy) combinations."""
    from app.evaluation.runner import STRATEGIES

    out = Preflight()
    for name, p in providers.items():
        if not isinstance(p.max_retries, int) or not 0 <= p.max_retries <= MAX_SANE_RETRIES:
            out.bounded = False
            out.problems.append(f"provider {name}: max_retries {p.max_retries!r} is not bounded")
    if not out.bounded:
        return out
    catalog = load_catalog(settings.model_registry_path, allow_paid=settings.allow_paid_models)
    models = [m for m in catalog.models if m.enabled and m.provider in providers]
    base_policy = load_policy(settings.routing_policy_path)
    framing = int(quota["framing_allowance_tokens"])
    for strategy in strategies:
        policy_overrides, request_overrides = STRATEGIES[strategy]
        policy = base_policy.model_copy(update=policy_overrides)
        totals = {"requests": 0, "attempts": 0, "input": 0, "output": 0}
        for case in dataset.cases:
            if only is not None and (case.id, strategy) not in only:
                continue
            decision = route(
                RoutingRequest(
                    messages=(ChatMessage(role="user", content=case.prompt),),
                    task_type=case.task_type,
                    max_output_tokens=case.max_output_tokens,
                    response_format=case.response_format,
                    **request_overrides,
                ),
                models=models,
                enabled_providers=frozenset(providers),
                simulated_providers=frozenset(n for n, p in providers.items() if p.simulated),
                policy=policy,
                health=_NoHealth(),
            )
            attempts = sum(1 + providers[c.provider].max_retries for c in decision.eligible)
            in_bound = input_token_bound([case.prompt], framing)
            out_bound = case.max_output_tokens
            totals["requests"] += 1
            totals["attempts"] += attempts
            totals["input"] += attempts * in_bound
            totals["output"] += attempts * out_bound
            out.max_attempts_per_request = max(out.max_attempts_per_request, attempts)
            out.attempts_histogram[attempts] = out.attempts_histogram.get(attempts, 0) + 1
            if attempts:
                out.largest_attempt_tokens = max(out.largest_attempt_tokens, in_bound + out_bound)
        out.per_strategy[strategy] = totals
        out.gateway_requests += totals["requests"]
        out.max_provider_attempts += totals["attempts"]
        out.input_reservation_tokens += totals["input"]
        out.output_reservation_tokens += totals["output"]
    return out


def evaluate(
    pre: Preflight,
    quota: dict[str, Any],
    budget: DailyBudget | None,
    ledger: QuotaLedger,
    *,
    now: datetime | None = None,
    accept_incomplete_risk: bool = False,
) -> Preflight:
    """Check the plan against every quota constraint; fill `constraints` and `problems`."""
    now = now or datetime.now(UTC)
    minute_budget = float(quota["tokens_per_minute"]) * float(quota["per_minute_safety"])
    day_safety = float(quota["per_day_safety"])
    rpd_budget = float(quota["requests_per_day"]) * day_safety
    requests_today = ledger.requests_on(now.astimezone(UTC).date())
    c = pre.constraints
    c["tpm_budget"] = minute_budget
    c["largest_attempt_tokens"] = pre.largest_attempt_tokens
    c["min_minutes_by_tpm"] = round(pre.total_reservation_tokens / minute_budget, 1)
    c["rpm_cap"] = quota["requests_per_minute_cap"]
    c["min_minutes_by_rpm"] = round(
        pre.max_provider_attempts / float(quota["requests_per_minute_cap"]), 1
    )
    c["rpd_budget"] = rpd_budget
    c["requests_already_today_in_ledger"] = requests_today
    c["rpd_remaining"] = rpd_budget - requests_today
    if pre.largest_attempt_tokens > minute_budget:
        pre.problems.append(
            f"a single attempt may need {pre.largest_attempt_tokens} tokens, above the "
            f"{minute_budget:.0f}/min budget"
        )
    if pre.max_provider_attempts > rpd_budget - requests_today:
        pre.problems.append(
            f"up to {pre.max_provider_attempts} attempts exceed the remaining daily request budget "
            f"({rpd_budget - requests_today:.0f})"
        )
    if budget is None:
        c["daily_budget"] = "UNVERIFIED (none supplied)"
        pre.problems.append(
            "no operator-verified remaining daily token budget: supply "
            "--remaining-daily-tokens (or "
            "--daily-token-limit and --tokens-used-today) with --daily-budget-source and "
            "--daily-budget-verified-at"
        )
        return pre
    budget_problems = budget.problems(now)
    c["daily_budget"] = {
        "remaining_tokens_at_verification": budget.remaining_tokens,
        "daily_token_limit": budget.daily_token_limit,
        "tokens_used_at_verification": budget.tokens_used_at_verification,
        "verified_at": budget.verified_at.isoformat(),
        "source": budget.source,
    }
    pre.problems += [f"daily budget: {p}" for p in budget_problems]
    used_since = ledger.tokens_since(budget.verified_at)
    usable = budget.remaining_tokens * day_safety - used_since
    c["ledger_tokens_since_verification"] = used_since
    c["usable_daily_tokens"] = usable
    c["worst_case_fits_daily_budget"] = pre.total_reservation_tokens <= usable
    if pre.total_reservation_tokens > usable:
        message = (
            f"worst-case reservation {pre.total_reservation_tokens} exceeds the usable daily "
            "budget "
            f"{usable:.0f}; the run may stop incomplete (it can't exceed the budget)"
        )
        if accept_incomplete_risk:
            pre.warnings.append(message + " (accepted with --accept-incomplete-risk)")
        else:
            pre.problems.append(message + "; pass --accept-incomplete-risk to start anyway")
    return pre


def format_report(pre: Preflight) -> list[str]:
    lines = [
        f"gateway requests: {pre.gateway_requests}",
        f"maximum provider attempts: {pre.max_provider_attempts} "
        f"(per request up to {pre.max_attempts_per_request}; distribution "
        f"{dict(sorted(pre.attempts_histogram.items()))}; bounded: {pre.bounded})",
        f"input reservation (bytes + framing): {pre.input_reservation_tokens} tokens",
        f"output reservation (full max_output_tokens): {pre.output_reservation_tokens} tokens",
        f"total conservative reservation: {pre.total_reservation_tokens} tokens",
    ]
    for name, totals in pre.per_strategy.items():
        lines.append(
            f"  {name}: {totals['requests']} requests, {totals['attempts']} max attempts, "
            f"{totals['input'] + totals['output']} tokens"
        )
    for key, value in pre.constraints.items():
        lines.append(f"{key}: {value}")
    lines += [f"WARNING: {w}" for w in pre.warnings]
    lines += [f"PROBLEM: {p}" for p in pre.problems]
    lines.append("preflight: " + ("OK" if pre.ok else "FAILED (fail closed)"))
    return lines
