# Cost Accounting

Status: implemented and tested. Per-attempt and per-request calculation is in `accounting/cost.py`. Tenant
shadow-budget enforcement (atomic reservation, budget-capped execution, settlement in the same transaction as the
attempt rows) is in `accounting/budget.py` (see TENANCY_AND_SECURITY.md). Aggregates are in `accounting/usage.py`; the
dashboard always shows actual charges and estimated list cost separately, and shows "unknown" (never $0) when no
charge is known.

## The problem this solves

RouteWise only calls free-tier models, so the real bill is $0 whatever the routing does. A "savings %"
computed from actual charges would always be 0 → 0 and would say nothing. Routing, budgets, and the
benchmark therefore use a **shadow cost**: what the same tokens would cost at each provider's
published pay-as-you-go list price. The actual charge is tracked separately and never mixed in.

## Two figures, never conflated

| | `actual_charge_usd` | `estimated_list_cost_usd` |
|---|---|---|
| Meaning | What the provider charged for this call | Tokens × published list price (pricing snapshot) |
| Used for | Reporting real spend (expected ≈ $0) | Shadow budgets, routing cost ranking, benchmark comparison |
| Status field | `cost_status` | `list_cost_status` |
| May be presented as actual spending? | Yes, when `cost_status` is `reported` or `free_tier` | **Never.** Always labelled "estimated at list price as of <date>" |

## `cost_status` (provenance of the actual charge)

| Value | When | Example |
|---|---|---|
| `reported` | The provider returned a dollar amount for this call | OpenRouter `usage.cost` |
| `free_tier` | $0, established by the provider's free-plan billing terms, with no per-call dollar figure | A Groq free-plan call |
| `estimated` | The provider bills, but doesn't report per call, so the charge is computed from verified prices | Not expected in this project (no paid usage) |
| `unavailable` | Unknown | Mock calls; failed calls with no billing signal |

Rules:
- **Token counts are not a charge.** Groq reports `usage` tokens but no dollar amount, and the Groq
  adapter never sets a reported charge, even if a `cost` field appeared (tested).
- Groq is `free_tier` ($0) **only when `GROQ_BILLING_PLAN=free`**. Groq's plans page lists the Free
  plan at $0, and usage billing applies only to the Developer tier (which needs a payment method). But
  the gateway can't see which plan a key is on, so the operator must declare it. Default `unknown` →
  `unavailable`.
- OpenRouter `:free` models are `free_tier` unless `usage.cost` is present, in which case it's `reported`.
- Ollama (local hardware) is `free_tier`.
- Mock rows are `simulated = true` and `cost_status = unavailable`. Their list prices are fabricated and
  flagged `simulated`, so they're useful only for testing the arithmetic.

## `list_cost_status`

- `estimated`: computed from a pricing snapshot (`pricing_snapshot_id` is recorded on the attempt).
- `unavailable`: no verified list price for the model. Such a model ranks last on cost and can't be
  admitted under a shadow budget (it can't be bounded).

## Pricing snapshots

`pricing_snapshots` rows are append-only and carry `source_url`, `effective_date`, and `retrieved_on`.
Each attempt references the snapshot it was costed with, so historical costs don't change when prices
do. A price change is a new YAML entry with a new `effective_date`, synced by `app.cli seed`.

## Per-attempt rules (implemented)

- **Actual charge:** simulated → `unavailable`; provider reported a dollar amount → `reported`;
  provider's charge basis is free tier → `0` / `free_tier`; otherwise `unavailable`.
- **List cost:** needs a published price **and** both token counts. Missing either → `None` /
  `unavailable`, never 0.
- Failed attempts keep any usage the provider reported (e.g. an empty completion that used the
  whole token budget), so their list cost counts too.

## Request totals and double counting (implemented)

- Each provider call is a `request_attempts` row with its own tokens and cost. Summing attempts
  isn't double counting: each retry or fallback really consumed tokens.
- `request_logs` cost = sum over attempts. Actual charge is `unavailable` if any attempt's is unknown;
  otherwise `reported` if any attempt was reported, else `free_tier`.
- List cost is only `estimated` when every attempt that reported usage was priced and (for successes)
  the final model is priced. Otherwise it's `unavailable`, because a partial sum would understate it.
- **Unknown usage is never $0.** An attempt that may have consumed tokens but didn't report them (a
  timeout, a 5xx, a network error after sending, a malformed body, or a success without a usage block)
  makes the request's list cost `unavailable` instead of an understated partial sum. The response
  note says so, and `fallback.failed_attempts_without_usage` gives the count. Its actual charge
  follows the charge basis: `free_tier` stays $0, since the Free plan bills nothing whatever was
  consumed, and any other basis is `unavailable`.
- **Shadow-budget draw** per attempt (`accounting.cost.budget_draw`):

  | Case | Draw |
  |---|---|
  | Known, priced usage | its list cost |
  | Unknown usage | the attempt's worst case, which is what was reserved for it |
  | Can't be bounded (unpriced model) | the whole reservation |
  | Rejected before generation (429, 401, 400, 404) | 0 |

  The executor counts the same draws against the cap, so an unknown-usage attempt can't make room
  for more attempts. The request row's `decision.execution` records `usage_unknown_attempts` and
  `budget_charged_usd`.
- Response `usage` = the final attempt. Response `cost` = all attempts.
- Shadow-budget reservation happens once per request (up to 3× the largest eligible worst case, capped by headroom),
  then settles once. Retries and fallbacks draw on the same reservation; the executor won't start an attempt that
  could exceed it, so spend ≤ reservation ≤ budget.
- Free-tier **quota** is separate from dollars. The OpenRouter guard counts every network request,
  including failures (undocumented, so assumed). See PROVIDER_INTEGRATION.md.

## Strict budgets and unknown prices

When a budget applies (`max_cost_usd`, and the tenant's remaining budget from Phase 3), a model
without a published price is **excluded** (`PRICE_UNKNOWN`). Its worst-case cost can't be bounded, so
it is never treated as $0. Without a budget, unpriced models stay eligible but rank after priced ones.

## Provider specifics (verified 2026-11-03)

| Provider | Usage reporting | Actual charge | List price source |
|---|---|---|---|
| OpenRouter | tokens + `cost` on every response ([docs](https://openrouter.ai/docs/use-cases/usage-accounting)); `usage: {include: true}` also sent (deprecated no-op) | `usage.cost` → `reported`; else `free_tier` | paid variant of the same model on OpenRouter |
| Groq | `prompt_tokens`, `completion_tokens` | `free_tier` iff `GROQ_BILLING_PLAN=free`, else `unavailable` | [Groq models page](https://console.groq.com/docs/models); Llama models "Contact Sales" → none |
| Ollama | OpenAI-compatible `usage` if returned | `free_tier` (local) | none (no market price) |
| Mock | char-based estimates | `unavailable` (simulated) | fabricated, flagged `simulated` |
