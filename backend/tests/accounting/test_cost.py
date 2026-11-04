from decimal import Decimal

import pytest

from app.accounting.cost import CostBreakdown, attempt_cost, budget_draw, settle_request
from app.core.config import BACKEND_ROOT
from app.providers.base import ProviderUsage
from app.providers.catalog import load_catalog

MODELS = {m.key: m for m in load_catalog(BACKEND_ROOT / "config" / "models.yaml").models}
GPT20 = MODELS["groq/openai/gpt-oss-20b"]  # $0.075 in / $0.30 out per Mtok
LLAMA8 = MODELS["groq/llama-3.1-8b-instant"]  # no published price
GEMMA = MODELS["openrouter/google/gemma-4-31b-it:free"]
MOCK = MODELS["mock/mock-small"]


def test_groq_free_plan_is_free_tier_with_estimated_list_cost() -> None:
    cost = attempt_cost(GPT20, ProviderUsage(1000, 500), simulated=False, charge_basis="free_tier")
    assert cost.actual_charge_usd == Decimal(0)
    assert cost.cost_status == "free_tier"
    # 1000 * 0.075/M + 500 * 0.30/M
    assert cost.estimated_list_cost_usd == Decimal("0.00022500")
    assert cost.list_cost_status == "estimated"
    assert cost.pricing_source_url == "https://console.groq.com/docs/models"
    assert cost.pricing_effective_date == "2026-11-03"


def test_groq_tokens_are_not_a_reported_charge_when_plan_unknown() -> None:
    cost = attempt_cost(
        GPT20, ProviderUsage(1000, 500), simulated=False, charge_basis="unavailable"
    )
    assert cost.actual_charge_usd is None
    assert cost.cost_status == "unavailable"
    assert cost.list_cost_status == "estimated"  # shadow cost is still computable


def test_reported_charge_wins() -> None:
    usage = ProviderUsage(10, 10, reported_charge_usd=Decimal("0.0000001"))
    cost = attempt_cost(GEMMA, usage, simulated=False, charge_basis="free_tier")
    assert cost.cost_status == "reported"
    assert cost.actual_charge_usd == Decimal("0.00000010")


def test_unpriced_model_list_cost_is_unavailable_not_zero() -> None:
    cost = attempt_cost(LLAMA8, ProviderUsage(1000, 500), simulated=False, charge_basis="free_tier")
    assert cost.estimated_list_cost_usd is None
    assert cost.list_cost_status == "unavailable"


@pytest.mark.parametrize("usage", [None, ProviderUsage(None, 5), ProviderUsage(5, None)])
def test_missing_tokens_mean_unknown_list_cost(usage: ProviderUsage | None) -> None:
    cost = attempt_cost(GPT20, usage, simulated=False, charge_basis="free_tier")
    assert cost.estimated_list_cost_usd is None
    assert cost.list_cost_status == "unavailable"


def test_simulated_calls_have_no_actual_charge() -> None:
    cost = attempt_cost(MOCK, ProviderUsage(100, 100), simulated=True, charge_basis="free_tier")
    assert cost.actual_charge_usd is None
    assert cost.cost_status == "unavailable"


def _c(actual: str | None, status: str, listed: str | None) -> CostBreakdown:
    return CostBreakdown(
        Decimal(actual) if actual else None,
        status,
        Decimal(listed) if listed else None,
        "estimated" if listed else "unavailable",
    )


def test_settle_sums_each_attempt_once() -> None:
    attempts = [
        (_c("0", "free_tier", "0.0001"), True),  # failed but consumed tokens
        (_c("0", "free_tier", "0.0002"), True),  # success
    ]
    total = settle_request(attempts, succeeded=True)
    assert total.estimated_list_cost_usd == Decimal("0.00030000")
    assert total.actual_charge_usd == Decimal(0)
    assert total.cost_status == "free_tier"


def test_settle_ignores_failed_attempts_without_usage() -> None:
    attempts = [(_c("0", "free_tier", None), False), (_c("0", "free_tier", "0.0002"), True)]
    total = settle_request(attempts, succeeded=True)
    assert total.estimated_list_cost_usd == Decimal("0.00020000")
    assert total.list_cost_status == "estimated"


def test_settle_unavailable_when_any_charge_unknown() -> None:
    attempts = [(_c(None, "unavailable", "0.0001"), True), (_c("0", "free_tier", "0.0002"), True)]
    total = settle_request(attempts, succeeded=True)
    assert total.actual_charge_usd is None
    assert total.cost_status == "unavailable"


def test_settle_reported_dominates_free_tier() -> None:
    attempts = [
        (_c("0", "free_tier", "0.0001"), True),
        (_c("0.0000005", "reported", "0.0002"), True),
    ]
    total = settle_request(attempts, succeeded=True)
    assert total.cost_status == "reported"
    assert total.actual_charge_usd == Decimal("0.00000050")


def test_settle_list_cost_unknown_if_final_model_unpriced() -> None:
    attempts = [(_c("0", "free_tier", "0.0001"), True), (_c("0", "free_tier", None), True)]
    total = settle_request(attempts, succeeded=True)
    assert total.estimated_list_cost_usd is None
    assert total.list_cost_status == "unavailable"


def test_settle_failed_request_without_any_usage() -> None:
    total = settle_request([(_c("0", "free_tier", None), False)], succeeded=False)
    assert total.list_cost_status == "unavailable"
    assert total.cost_status == "free_tier"


def test_settle_with_unknown_usage_never_reports_a_partial_list_cost() -> None:
    # A timeout without usage, then a priced success: summing only the success would understate.
    attempts = [(_c("0", "free_tier", None), False), (_c("0", "free_tier", "0.0002"), True)]
    total = settle_request(attempts, succeeded=True, usage_unknown=True)
    assert total.estimated_list_cost_usd is None
    assert total.list_cost_status == "unavailable"
    # The actual charge is a plan fact, not a usage fact: free tier bills $0 either way.
    assert total.actual_charge_usd == Decimal(0) and total.cost_status == "free_tier"


def test_settle_unknown_usage_on_a_non_free_basis_stays_unavailable() -> None:
    attempts = [(_c(None, "unavailable", None), False), (_c("0", "free_tier", "0.0002"), True)]
    total = settle_request(attempts, succeeded=True, usage_unknown=True)
    assert total.actual_charge_usd is None and total.cost_status == "unavailable"


@pytest.mark.parametrize(
    ("cost", "unknown", "rejected", "worst", "expected"),
    [
        # Unknown usage draws the worst case, never 0.
        (_c("0", "free_tier", None), True, False, Decimal("0.0005"), Decimal("0.0005")),
        # Unknown usage on an unpriced model can't be bounded.
        (_c("0", "free_tier", None), True, False, None, None),
        # Known, priced usage draws its list cost (even if the attempt failed).
        (_c("0", "free_tier", "0.0001"), False, False, Decimal("0.0005"), Decimal("0.0001")),
        # Rejected before generation (429, auth, 400): nothing consumed.
        (_c("0", "free_tier", None), False, True, Decimal("0.0005"), Decimal(0)),
        # Known usage on an unpriced model can't be bounded either.
        (_c("0", "free_tier", None), False, False, Decimal("0.0005"), None),
    ],
)
def test_budget_draw(
    cost: CostBreakdown,
    unknown: bool,
    rejected: bool,
    worst: Decimal | None,
    expected: Decimal | None,
) -> None:
    draw = budget_draw(
        cost, usage_unknown=unknown, rejected_before_generation=rejected, worst_case_usd=worst
    )
    assert draw == expected


def test_cost_note_explains_unknown_usage() -> None:
    from app.services.gateway import cost_note

    total = settle_request(
        [(_c("0", "free_tier", None), False), (_c("0", "free_tier", "0.0002"), True)],
        succeeded=True,
        usage_unknown=True,
    )
    note = cost_note(total, simulated=False, usage_unknown=1)
    assert "$0 under the provider's free tier" in note
    assert "1 attempt(s) may have consumed tokens" in note


def test_settle_no_attempts() -> None:
    total = settle_request([], succeeded=False)
    assert total.cost_status == "unavailable" and total.actual_charge_usd is None
