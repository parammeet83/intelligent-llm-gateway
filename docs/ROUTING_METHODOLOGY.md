# Routing Methodology

Policy version: **`rw-2026.11-v1`**. Code: `backend/app/routing/`. Config:
`backend/config/routing_policy.yaml`. Any config change must bump `version`.

**What this is:** a deterministic, hand-weighted heuristic. **What it isn't:** an AI classifier, a
learned model, or a provably optimal router. Its weights are starting values. Whether they save cost
without losing quality is for the Phase 4 benchmark to show, and no such claim is made before then.

## Why rules, not an LLM router (spec card S1-04)

| | Rules (chosen) | LLM-as-router |
|---|---|---|
| Added latency | ~0 ms, no I/O | a full model call per request |
| Added cost | none | a second paid/quota-consuming call |
| Determinism | same input → same decision (tested) | sampling-dependent |
| Explainability | every point traceable to a feature | opaque |
| Weakness | misses semantic difficulty; keyword-gameable | better at nuance |

## Pipeline

1. **Features** (`features.py`). Estimated input tokens (~4 chars/token), requested output length, JSON
   output, and regex counts over *user* messages: multi-step markers, constraint words, reasoning
   verbs, math terms, code fences.
2. **Score** (`engine.score_features`). Task-type prior plus capped feature contributions, clipped to 100.
   Every contribution is returned in the API response and stored in `request_logs.decision`.
3. **Tier.** `score < 35 → small`, `< 65 → medium`, else `premium` (`LOW/MEDIUM/HIGH_COMPLEXITY`).
4. **Required tier.** Adjusted by the client and stakes:
   - `preferred_tier` above computed → floor raised (`CLIENT_TIER_FLOOR`)
   - below computed → applied only with `allow_downgrade=true` (`CLIENT_TIER_DOWNGRADE`), else ignored (`CLIENT_TIER_IGNORED`)
   - `quality=high` → at least premium (`HIGH_STAKES`); beats any downgrade
5. **Candidate filter.** Every model is evaluated, and *every* exclusion reason is recorded (not just the first).
6. **Rank** eligible models; the first is selected, the rest form the fallback chain.

## Exclusion codes

| Code | Meaning |
|---|---|
| `PROVIDER_DISABLED` | provider not enabled in `.env` |
| `MODEL_DISABLED` | registry `enabled: false` (e.g. preview models) |
| `PAID_MODEL_BLOCKED` | `billing: paid` (also rejected at startup) |
| `SIMULATED_EXCLUDED` | mock model while real providers are enabled (unless explicitly requested) |
| `PROVIDER_NOT_ALLOWED` / `MODEL_NOT_ALLOWED` | outside the request's `constraints` |
| `TIER_TOO_LOW` | below the required tier |
| `CAPABILITY_MISSING` | JSON requested, model lacks `json_mode` |
| `OUTPUT_LIMIT_EXCEEDED` / `CONTEXT_TOO_SMALL` | token limits |
| `MODEL_UNAVAILABLE` | missing from provider's live catalog, or returned 404 |
| `CIRCUIT_OPEN` / `RATE_LIMIT_COOLDOWN` | runtime health |
| `PROVIDER_AUTH_FAILED` / `QUOTA_EXHAUSTED` | provider-wide lockout |
| `PRICE_UNKNOWN` | a budget applies and the model has no published price (unknown ≠ $0) |
| `BUDGET_CONSTRAINT` | worst-case list cost exceeds `max_cost_usd` (or, from Phase 3, remaining tenant budget) |
| `LATENCY_CONSTRAINT` | **observed** p95 (≥ 5 samples) exceeds `latency_target_ms` |

**Worst-case list cost** = ⌈est. input tokens × 1.25⌉ × input price + `max_output_tokens` × output
price. The 1.25 factor covers the rough token estimate.

**Latency** uses only measured p95 from successful calls in this process. With fewer than 5
samples, latency is unknown and never excludes a model. No latency figures are configured or invented.

## Ranking

Default key (`selection: cheapest_capable`): `(fallback-only provider?, worst-case list cost [unpriced last], tier, observed p95 [unknown last], name)`.
With `selection: lowest_tier_first`: `(fallback-only?, tier, cost, p95, name)`, so simple tasks stay on small models.
With `priority=high`, p95 comes first after the provider class.

**Carried issue 1 (simple tasks escalating to medium).** Complexity scoring only decides the *required tier*; the
`selection` setting decides the *economic ranking*. These are deliberately separate. Until 2026-11-04 the cheapest
capable Groq model was a medium-tier one (`gpt-oss-20b`), because Llama 8B had no published price. Since Groq retired
both Llama models (shut down 2026-08-16), `gpt-oss-20b` is the **small-tier** Groq model (Groq's named replacement for
Llama 8B), so simple Groq traffic no longer escalates. Groq now has **no medium-tier model**, so medium-tier requests
escalate to `gpt-oss-120b`. The two `selection` policies now differ mainly in how they treat OpenRouter and Ollama models.
Which is better is still a benchmark question (`routewise` vs `routewise_tier_first` against the all-premium baseline).
In the live benchmark (Days 1–3) the two policies chose the same Groq model on every case, so the data can't
distinguish them; see [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md).

**Carried issue 2 (complex + JSON had no fallback).** Resolved by adding `nvidia/nemotron-3.5-super-vl:free` (OpenRouter;
120B-total MoE; catalog lists `response_format`) as a premium JSON-capable fallback. Its tier is a judgement call. If a
request's constraints still exclude every model, the API returns `422 NO_ELIGIBLE_MODEL` listing each exclusion.

**Tenant budgets (Phase 3)** feed `budget_remaining_usd`: models whose worst case exceeds the tenant's headroom are
excluded (`BUDGET_CONSTRAINT`), as are unpriced models (`PRICE_UNKNOWN`). If the tenant budget is the binding limit, the
API returns `402 BUDGET_EXHAUSTED`.

- **Tier is a floor, not a target.** If a higher-tier model is cheaper, it wins (`TIER_ESCALATED`).
  On Groq this now happens for medium-tier requests, which go to `gpt-oss-120b` because Groq has no
  enabled medium model. Small-tier requests stay on `gpt-oss-20b` (small since 2026-11-04).
- **Fallback-only providers** (`openrouter`) rank after all primary-provider models, to protect its
  50/day free allowance. Selecting it adds `PRIMARY_PROVIDERS_INELIGIBLE`.
- **Fallbacks obey the same rules by construction.** The chain *is* the filtered, ranked list, so
  every fallback already passed the tier, capability, budget, provider, and paid-model checks
  (property-tested across constraint mixes). The executor re-checks health and the paid guard
  before each call.

## Decision record

Stored in `request_logs.decision` and returned in `routing` on every response: `policy_version`,
`score`, `contributions[]`, `computed_tier`, `required_tier`, `reason_codes[]`, selected model,
`fallback_chain[]`, every candidate with its exclusions and worst-case cost, the constraints used,
a one-line `explanation`, and (after execution) `execution.outcome` and `execution.skipped`.

Observed on 2026-11-03 with Groq + OpenRouter enabled (fake transports):

| Request | Score | Required | Selected | Fallbacks |
|---|---|---|---|---|
| "Is this review positive?" (classification) | 5.03 | small | groq gpt-oss-20b (TIER_ESCALATED) | 7 |
| Multi-step proof + trade-off analysis (reasoning) | 82.18 | premium | groq gpt-oss-120b | nemotron (OpenRouter) |
| same, with JSON output | 87.18 | premium | groq gpt-oss-120b | nemotron-3.5-super-vl (added 2026-11-04; previously none) |

The table above predates the 2026-11-04 catalog change. On the current catalog (Groq only, local check):
`preferred_tier` small → `gpt-oss-20b`; medium → `gpt-oss-120b` (`TIER_ESCALATED`); premium → `gpt-oss-120b`.
Live request: "In one short sentence, what is the capital of France?" (qa) scored 20.04, needed the
small tier, and selected `gpt-oss-20b` (`LOW_COMPLEXITY`, `CHEAPEST_ELIGIBLE`).

## Known limitations

- English-only keyword lists. A short but hard question ("is 2^31 − 1 prime?") can score low.
- Easy to game by adding keywords. Fine for a tenant routing its own traffic; not adversarially robust.
- Token estimates are approximate. The worst-case factor compensates for budgets but not for context checks.
- Health and latency are per process. A restart forgets circuit state and latency history.
- Tier labels are judgement calls, not measured capability.
