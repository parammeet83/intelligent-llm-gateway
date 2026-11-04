# Provider Integration

Status: all adapters are implemented and tested against fake HTTP transports. **Groq has been
verified live** with one successful generation on 2026-11-04 (see [Live verification](#live-verification)).
OpenRouter and Ollama have **not** been called live.

## Sources (verified 2026-11-03; Groq re-checked 2026-11-04)

| Provider | What was checked | Source |
|---|---|---|
| Groq | Endpoint, auth, `max_completion_tokens`, usage fields, `/models` | https://console.groq.com/docs/api-reference |
| Groq | Model IDs, context, max output, list prices | https://console.groq.com/docs/models |
| Groq | HTTP status meanings (incl. 422, 498) | https://console.groq.com/docs/errors |
| Groq | JSON object mode on all models; `json_schema` on gpt-oss | https://console.groq.com/docs/structured-outputs |
| Groq | Free plan $0; usage billing only on Developer tier; upgrade needs a payment method | https://console.groq.com/docs/billing-faqs, plans page (via search) |
| Groq | Llama 3.1 8B and Llama 3.3 70B shut down 2026-08-16; replacement `openai/gpt-oss-20b` (2026-11-04) | https://console.groq.com/docs/deprecations |
| Groq | GPT-OSS `reasoning_effort` = `low`/`medium`/`high`; reasoning in a separate `reasoning` field, toggled by `include_reasoning`; `reasoning_format` unsupported (2026-11-04) | https://console.groq.com/docs/reasoning |
| Groq | Rate-limit headers `x-ratelimit-*`; gpt-oss-20b base limits 30 RPM / 1K RPD / 8K TPM / 200K TPD (labelled Developer plan) (2026-11-04) | https://console.groq.com/docs/rate-limits |
| OpenRouter | Free-model limits: 20 req/min; 50 req/day with <10 credits purchased | https://openrouter.ai/docs/api-reference/limits |
| OpenRouter | Error codes; errors inside HTTP 200; Retry-After on 429/503 | https://openrouter.ai/docs/api-reference/errors |
| OpenRouter | `usage` incl. `cost` returned on every response | https://openrouter.ai/docs/use-cases/usage-accounting |
| OpenRouter | Free model IDs, `$0` pricing, paid-variant list prices, `response_format` support | https://openrouter.ai/api/v1/models (public catalog) |
| Ollama | OpenAI-compatible `/v1/chat/completions`, JSON mode, key ignored locally | https://docs.ollama.com/api/openai-compatibility |

**Not documented, so handled conservatively:**
- Whether failed OpenRouter requests count toward the daily free allowance. Assumed yes: the local
  guard counts every request that reaches the network.
- Groq free-plan rate limits. The public page shows Developer-plan limits only; free limits appear
  in the account console. The adapter relies on Groq's 429 + `retry-after` rather than local limits.
- Whether a Groq key is on the Free plan. The gateway can't tell, so `GROQ_BILLING_PLAN=free` must
  be set explicitly before charges are labelled `free_tier`.

## Adapter architecture

```
Provider (base.py)               interface: generate(), list_model_ids(), quota_available()
 ├─ MockProvider (mock.py)        simulated=True, scriptable outcomes, no network
 └─ OpenAICompatibleProvider (http.py)   shared HTTP, normalisation, error classification
     ├─ GroqProvider        max_completion_tokens; reasoning_effort; 422→malformed, 498→server
     ├─ OpenRouterProvider  :free-only guard, quota guard, usage.cost, max_retries=0
     └─ OllamaProvider      localhost-only, no credentials
```

- Each adapter is enabled independently (`GROQ_ENABLED`, `OPENROUTER_ENABLED`, `OLLAMA_ENABLED`,
  `MOCK_PROVIDER_ENABLED`). Enabling Groq or OpenRouter without its key fails at startup.
- Base URLs are constants (Ollama: a validated localhost URL). Clients can't supply endpoints, and
  redirects are never followed (the `Authorization` header must not leave the configured host).
- Provider error messages are truncated to 200 characters and passed through secret redaction.
  Response bodies, prompts, and headers never go into errors or logs.

### Normalisation contract (tested for every adapter in `tests/providers/test_contract.py`)

| Outcome | Result |
|---|---|
| 2xx with non-empty `choices[0].message.content` | `ProviderResponse`; usage ints or `None` (never a guessed 0) |
| Non-JSON / missing or non-string content | `MALFORMED` |
| Empty content (e.g. reasoning model hit the token cap) | `MALFORMED`, **with consumed usage attached** |
| HTTP 200 carrying an `error` object (OpenRouter) | classified by `error.code` |
| 3xx | refused, `BAD_REQUEST` ("unexpected redirect") |
| httpx timeout / transport error | `TIMEOUT` / `NETWORK` |

### Error classification

| Kind | Typical status | Same-model retry | Fallback | Health effect |
|---|---|---|---|---|
| `TIMEOUT` | 408, client timeout | yes (≤ `max_retries`) | yes | breaker failure |
| `SERVER` | 5xx, Groq 498 | yes | yes | breaker failure |
| `NETWORK` | connection errors | yes | yes | breaker failure |
| `RATE_LIMITED` | 429 | **never** | yes | model cooldown (Retry-After or 30 s) |
| `QUOTA_EXHAUSTED` | OpenRouter 402, local guard | never | yes | provider cooldown 1 h (if sent) |
| `AUTH` | 401, Groq 403 | never | yes, other providers | **provider** cooldown 15 min |
| `MODEL_NOT_FOUND` | 404 | never | yes | model unavailable until catalog refresh |
| `MALFORMED` | bad body, Groq 422 | never | yes | breaker failure |
| `BAD_REQUEST` | 400, 413, OpenRouter 403 (moderation) | never | **no** (stop) | none |

DB `request_attempts.status` keeps its original values; `quota_exhausted` maps to `rate_limited`
and `model_not_found` to `bad_request`, with the precise kind in `error_code`. No migration needed.

## Resilience

- **Retries:** transient kinds only, `max_retries` per adapter (Groq 1, Ollama 1, **OpenRouter 0**).
  Exponential backoff with full jitter (`RETRY_BACKOFF_BASE_S` × 2ⁿ, capped at
  `RETRY_BACKOFF_CAP_S`). A `Retry-After` hint is honoured when ≤ cap; a longer hint skips the retry.
- **Deadline:** `REQUEST_DEADLINE_S` bounds the whole request; each attempt's timeout is clipped to
  what remains.
- **Circuit breaker:** per model; opens after `CIRCUIT_FAILURE_THRESHOLD` consecutive failures for
  `CIRCUIT_OPEN_S`, then lets one half-open probe through.
- **Catalog check:** at startup each real provider's `/models` is fetched (15 s cap). A model missing
  from a successful listing is excluded (`MODEL_UNAVAILABLE`). If the listing fails, models stay
  "unverified" rather than excluded.
- Health state is in-memory per process (fine for one instance; see trade-offs in ARCHITECTURE.md).

## OpenRouter specifics

- **Free-only guard:** any model ID without `:free` is refused before a request is made.
- **Quota guard:** `OPENROUTER_FREE_RPM` / `OPENROUTER_FREE_RPD` (20 / 50) are defaults only. At startup the adapter reads
  `GET /api/v1/key → free_model_daily_requests` and adopts the **account's real daily `limit`** (50, or 1000 for accounts
  with ≥10 credits ever purchased) and today's `used` count (best effort; tested with a faked response, not yet against a
  real account). Every network request counts, including failures. The guard is in-memory, so it
  resets on restart; OpenRouter still enforces the real limit, and its 429s are not retried.
- **Ranking:** listed in `fallback_only_providers`, so it's selected only when no Groq/Ollama model
  is eligible (reason `PRIMARY_PROVIDERS_INELIGIBLE`).
- **Usage:** `usage: {include: true}` is sent as requested. OpenRouter's docs mark it deprecated with
  no effect; `usage.cost` is read from every response either way.
- **402** (insufficient credits / negative balance) is `QUOTA_EXHAUSTED`. RouteWise never buys credits.

## Ollama specifics

- Local only: `OLLAMA_BASE_URL` must be localhost, and `OLLAMA_ENABLED` is refused in production.
- Registry model `qwen2.5:1.5b` must be pulled first (`ollama pull qwen2.5:1.5b`). Its timeout is
  120 s for CPU inference. It has no market price, so `list_cost_status = unavailable`: it's excluded
  from strictly budgeted requests and ranks after priced models.

## Model registry (`backend/config/models.yaml`)

| Tier | Model | List price (in/out per Mtok) | Notes |
|---|---|---|---|
| small | groq `openai/gpt-oss-20b` | $0.075 / $0.30 (re-checked 2026-11-04) | reasoning model, `reasoning_effort: low`; small tier since 2026-11-04 (was medium) |
| small | openrouter `liquid/lfm-2.5-2.6b:free` | $0.35 / $0.50 (paid variant) | |
| small | ollama `qwen2.5:1.5b` | — (local) | local only |
| — | groq `llama-3.1-8b-instant` | — (Groq: "Contact Sales") | **disabled**: shut down 2026-08-16; live 404 on 2026-11-04 |
| — | groq `llama-3.3-70b-versatile` | — (Groq: "Contact Sales") | **disabled**: shut down 2026-08-16; absent from the key's `/models` |
| medium | openrouter `google/gemma-4-26b-a4b-it:free` | $0.077 / $0.232 (paid variant) | |
| medium | openrouter `google/gemma-4-31b-it:free` | $0.20 / $0.40 (paid variant) | |
| premium | groq `openai/gpt-oss-120b` | $0.15 / $0.60 | reasoning model |
| premium | openrouter `nvidia/nemotron-3-ultra-550b-a55b:free` | $0.60 / $2.40 (paid variant) | no JSON mode |
| premium | openrouter `nvidia/nemotron-3.5-super-vl:free` | $0.15 / $0.50 (paid variant) | JSON mode; added 2026-11-04 as the JSON-capable premium fallback |
| premium | groq `qwen/qwen3.8-27b` | $0.80 / $4.00 | preview, **disabled** |

Tier assignments are judgement calls based on model size and published capability, not
measurements. Phase 4's benchmark is what tests them. With both Llama models retired, **Groq has no
enabled medium-tier model**: medium-tier requests on Groq go to `gpt-oss-120b` (premium), reported
as `TIER_ESCALATED`. Groq's page still lists both Llama IDs as "Production" with "Contact Sales"
pricing, but its deprecations page, this key's `/models` listing and a live 404 agree they're
unavailable here.

## Live verification

All calls used `GROQ_BILLING_PLAN=free`, with OpenRouter, Ollama and mock disabled, Groq retries set
to 0, and the router limited to one model (no fallback). Prompts were harmless and not stored (hash
and length only). Throwaway scripts outside the repo; tenant `live-smoke` (no budget).

| # | Date | Model | Outcome |
|---|---|---|---|
| 1 | 2026-11-04 | `llama-3.1-8b-instant` (startup catalog check skipped) | **HTTP 404 `model_not_found`**. Auth OK. Classified `MODEL_NOT_FOUND`, no retry, $0 `free_tier`, no usage (rejected before generation), persisted as `failed`. Kept as an audit record |
| 2 | 2026-11-04 | `openai/gpt-oss-20b`, `reasoning_effort: low`, `max_output_tokens` 128 | **Succeeded**: see below |
| 3 | 2026-11-04 16:57 UTC | `openai/gpt-oss-120b`, `reasoning_effort` as registered (none), `max_output_tokens` 256 | **Succeeded**: see below |

Request 2 details (one sample, so not an SLO or benchmark figure):

- **Before generating:** `GET /models` returned 200 with 11 models. `openai/gpt-oss-20b` was
  `active: true`, with a 131,072-token context and 65,536 max completion tokens; neither Llama ID
  was listed. The app's startup catalog check (`refresh_catalogs`) then marked it
  `listed_by_provider: true` and marked both Llamas `MODEL_UNAVAILABLE`.
- **Response:** the provider returned model `openai/gpt-oss-20b`, `finish_reason: stop`, with a
  non-empty 31-character answer.
- **Usage:** 83 input tokens and 21 output tokens, of which **5 were reasoning tokens** (reported in
  `usage.completion_tokens_details.reasoning_tokens`). The input count is high for a 53-character
  prompt, which suggests the model's own prompt overhead.
- **Latency:** 3,775 ms at the provider and 5,678 ms end to end. The gap is mostly Neon round trips
  for rate-limit, pending, finalize and attempt writes.
- **Cost:** actual charge $0 (`free_tier`). Estimated list cost $0.00001253 (`estimated`; 83 ×
  $0.075/M + 21 × $0.30/M), linked to the 2026-11-03 pricing snapshot.
- **Rate-limit headers:** `x-ratelimit-limit-requests: 1000` and `x-ratelimit-limit-tokens: 8000`.
  These match the published base limits, which Groq labels as the Developer plan's, so the headers
  **don't prove which plan the key is on**. Groq exposes no plan or billing API. The Free plan is the
  operator's declaration (`GROQ_BILLING_PLAN=free`), and Groq bills only after a payment method is
  added and the account is upgraded.
- **Neon:** one `request_logs` row (`succeeded`, `fallback_used=false`, policy `rw-2026.11-v1`,
  `decision.execution.reasoning_tokens=[5]`) and one `request_attempts` row. `live-smoke` now has 2
  request rows.

Request 3 (one controlled GPT-OSS 120B call; one sample, not a benchmark figure). It was made
directly through the project's `GroqProvider`, built by `build_providers` from the real
configuration, with no gateway and no database write. The record is
`evaluation/reports/live-smoke-gpt-oss-120b-2026-11-04.json` (git-ignored).

- **Quota check first:** the worst-case reservation was 546 tokens (prompt bytes + 256 framing +
  256 output) and 1 request.
- **Catalog:** one free `GET /models` call listed both `openai/gpt-oss-20b` and `openai/gpt-oss-120b`.
- **Response:** `finish_reason: stop`, answer "ready".
- **Usage:** 78 input and 46 output tokens (36 of them reasoning), 124 in total. This is within the
  reservation.
- **Latency:** 431 ms.
- **Charge:** Groq reported no charge; it reports tokens only. The charge basis is `free_tier`
  (declared Free plan), so the actual charge is $0.
- **Rate-limit headers for 120B (observed, not inferred):** `limit-requests` 1000 per day (999
  remaining) and `limit-tokens` 8000 per minute (7666 remaining). As with 20B, these don't reveal the
  plan. Groq's headers don't include a **daily token** limit, so that must still be read from the
  Groq console.

## Known gaps and risks

- **Reasoning models** spend completion tokens on reasoning. `gpt-oss-20b` now runs with
  `reasoning_effort: low` (registry field, sent only to models with the `reasoning` capability) and
  `include_reasoning: false`, because the reasoning text is never used or stored. `gpt-oss-120b`
  keeps Groq's default effort, which is better for hard tasks. An empty completion is still possible
  with very small output limits; it's classified `MALFORMED` (usage kept) and falls back.
- Reasoning tokens appear in the API `usage.reasoning_tokens` and in
  `request_logs.decision.execution`; there's no dedicated column.
- Free catalogs change: a model that disappeared caused live request 1 to fail. Re-verify the
  registry before each benchmark run, and never bypass the startup catalog check.
- OpenRouter and Ollama are still unverified live.
