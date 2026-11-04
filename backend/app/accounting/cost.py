"""Per-attempt and per-request cost accounting. Rules: docs/COST_ACCOUNTING.md.

Two figures that are never merged:
  actual_charge_usd       + cost_status       (reported | free_tier | estimated | unavailable)
  estimated_list_cost_usd + list_cost_status  (estimated | unavailable)

Unknown is always None, never 0: a missing price or missing token count can't be costed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.providers.base import ChargeBasis, ProviderUsage
from app.providers.catalog import ModelSpec

_MTOK = Decimal(1_000_000)
_PLACES = Decimal("0.00000001")


@dataclass(frozen=True)
class CostBreakdown:
    actual_charge_usd: Decimal | None
    cost_status: str
    estimated_list_cost_usd: Decimal | None
    list_cost_status: str
    # Pricing provenance for the list cost, when there is one.
    pricing_effective_date: str | None = None
    pricing_source_url: str | None = None


def _q(value: Decimal) -> Decimal:
    return value.quantize(_PLACES, rounding=ROUND_HALF_UP)


def attempt_cost(
    model: ModelSpec,
    usage: ProviderUsage | None,
    *,
    simulated: bool,
    charge_basis: ChargeBasis,
) -> CostBreakdown:
    # Actual charge.
    if simulated:
        actual, status = None, "unavailable"
    elif usage is not None and usage.reported_charge_usd is not None:
        actual, status = _q(usage.reported_charge_usd), "reported"
    elif charge_basis == "free_tier":
        actual, status = Decimal(0), "free_tier"
    else:
        actual, status = None, "unavailable"

    # Shadow list cost: needs both a published price and both token counts.
    pricing = model.pricing
    list_cost: Decimal | None = None
    if (
        pricing is not None
        and usage is not None
        and usage.input_tokens is not None
        and usage.output_tokens is not None
    ):
        list_cost = _q(
            (
                Decimal(usage.input_tokens) * pricing.input_usd_per_mtok
                + Decimal(usage.output_tokens) * pricing.output_usd_per_mtok
            )
            / _MTOK
        )
    return CostBreakdown(
        actual_charge_usd=actual,
        cost_status=status,
        estimated_list_cost_usd=list_cost,
        list_cost_status="estimated" if list_cost is not None else "unavailable",
        pricing_effective_date=pricing.effective_date.isoformat() if pricing else None,
        pricing_source_url=pricing.source_url if pricing else None,
    )


def budget_draw(
    cost: CostBreakdown,
    *,
    usage_unknown: bool,
    rejected_before_generation: bool,
    worst_case_usd: Decimal | None,
) -> Decimal | None:
    """What one attempt takes from the tenant's shadow budget. None = it can't be bounded.

    Known usage draws its list cost. Usage that may have been consumed but wasn't reported (a
    timeout, a 5xx, a success without a usage block) draws the attempt's worst case, the amount
    reserved for it, never 0. Only a rejection before any generation draws nothing.
    """
    if usage_unknown:
        return worst_case_usd
    if cost.list_cost_status == "estimated":
        return cost.estimated_list_cost_usd
    if rejected_before_generation:
        return Decimal(0)
    return None  # usage known but the model is unpriced


def settle_request(
    attempts: Sequence[tuple[CostBreakdown, bool]],
    *,
    succeeded: bool,
    usage_unknown: bool = False,
) -> CostBreakdown:
    """Combine attempts into the request total. Each item is (cost, reported_usage).

    Every attempt is a separate provider call, so summing them doesn't double-count: retries
    and fallbacks really did consume tokens. `usage_unknown`: some attempt may have consumed
    tokens it never reported, so the list cost can't be summed and is `unavailable` rather than
    an understated `estimated`. The actual charge is unaffected: a free-tier plan bills $0
    whatever was consumed, and any other unreported charge is already `unavailable`.
    """
    if not attempts:
        return CostBreakdown(None, "unavailable", None, "unavailable")

    costs = [cost for cost, _ in attempts]
    if any(c.cost_status == "unavailable" for c in costs):
        actual, status = None, "unavailable"
    else:
        actual = _q(sum((c.actual_charge_usd or Decimal(0) for c in costs), Decimal(0)))
        if any(c.cost_status == "reported" for c in costs):
            status = "reported"
        elif any(c.cost_status == "estimated" for c in costs):
            status = "estimated"
        else:
            status = "free_tier"

    # List cost: every attempt that reported usage must be priced, and a successful request
    # must have a priced final attempt. Otherwise a partial sum would understate it.
    final_cost = attempts[-1][0]
    knowable = all(cost.list_cost_status == "estimated" for cost, reported in attempts if reported)
    if succeeded and final_cost.list_cost_status != "estimated":
        knowable = False
    if not succeeded and not any(reported for _, reported in attempts):
        knowable = False
    if usage_unknown:
        knowable = False
    if knowable:
        list_cost: Decimal | None = _q(
            sum((c.estimated_list_cost_usd or Decimal(0) for c in costs), Decimal(0))
        )
        list_status = "estimated"
    else:
        list_cost, list_status = None, "unavailable"

    return CostBreakdown(
        actual_charge_usd=actual,
        cost_status=status,
        estimated_list_cost_usd=list_cost,
        list_cost_status=list_status,
        pricing_effective_date=final_cost.pricing_effective_date,
        pricing_source_url=final_cost.pricing_source_url,
    )
