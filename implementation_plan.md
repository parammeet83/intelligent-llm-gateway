# RouteWise AI — Implementation Plan

Status (2026-11-04): **Phases 1–6 implemented and tested locally; Phase 7 prepared.** Blocked on: provider keys (live
verification and benchmark), your dataset review, and a push plus Render access (CI and deployment). See TASKS.md.
Sections below are the original Phase 0 plan, kept for traceability. Where they differ, the docs in `docs/` describe what
was actually built (e.g. dev auth was replaced by tenant API keys, and the cache was rejected).
Date: 2026-11-03

> **Decisions recorded 2026-11-03 (supersede §5 and §9 where they differ):**
> - Database: **Neon PostgreSQL**, a new dedicated project `routewise-ai`, connected via `DATABASE_URL`.
>   No local PostgreSQL. CI uses its own Postgres container.
> - Cost: separate `actual_charge_usd` and `estimated_list_cost_usd`, with `cost_status` ∈
>   {`reported`, `estimated`, `free_tier`, `unavailable`} plus `list_cost_status`. Shadow budgets and
>   benchmarks use the estimated list cost, which is never presented as actual spend or savings. See
>   [docs/COST_ACCOUNTING.md](docs/COST_ACCOUNTING.md).
> - Providers: no OpenRouter credits, no Groq upgrade. OpenRouter is a limited fallback
>   (20 req/min, 50 req/day; failed requests assumed to count). Rate-limit errors are never retried on
>   the same model.
> - Async DB driver is **asyncpg** (works on Windows' default event loop; psycopg async does not).

This plan turns the two reference screenshots and the master prompt into a buildable
design. Requirement IDs (S1-xx, S2-xx, P-xx, C-xx) refer to
[docs/REQUIREMENTS_TRACEABILITY.md](docs/REQUIREMENTS_TRACEABILITY.md).

---

## 1. Workspace findings (Phase 0 inspection)

| Item | Finding | Consequence |
|---|---|---|
| Repository | Empty, branch `main`, no commits, `origin` → `github.com/parammeet83/intelligent-llm-gateway` | Start from scratch. No commits until you ask. |
| Local Git identity | Already set *in this repo only*: `Parammeet <parammeet92@gmail.com>` | Left unchanged. Confirm this is the email you want on GitHub commits. |
| Python | 3.12.10 (+ uv 0.12.9) | Backend on Python 3.12, managed with **uv** (fast, lockfile, Windows-friendly). |
| Node | 24.19 / npm 11.17 | Frontend on Vite + React + TS. |
| Ollama | 0.40.13 installed, **no models pulled** | Local tier needs `ollama pull` (§9, Q3). |
| RAM | ~8 GB | Local models are limited to ~0.5–3B parameters. Ollama is good for dev and fallback testing, not as the premium tier. |
| Docker | Not installed | No docker-compose dev stack. CI uses a GitHub Actions Postgres service container. |
| PostgreSQL | Not installed locally | Resolved: Neon for dev; SQLite for fast local tests; Postgres 17 in CI. |

## 2. Provider research (verified 2026-11-03, re-verify before the live benchmark)

| Provider | What was verified | Still unverified | Role |
|---|---|---|---|
| **Groq** | OpenAI-compatible API. Rate-limit headers and `retry-after` on 429. Current catalog includes `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b` ([rate-limits doc](https://console.groq.com/docs/rate-limits)). | **Free-plan limits** (the public page shows Developer-plan limits only; free limits are shown in the account console). Per-token list prices (the pricing page didn't render them). Whether a card is required. | Primary live provider for all three tiers. |
| **OpenRouter** | `:free` models: 20 req/min, **50 req/day** with <10 credits purchased ([limits doc](https://openrouter.ai/docs/api-reference/limits)). Every response includes `usage` with token counts and **`cost`** ([usage accounting](https://openrouter.ai/docs/use-cases/usage-accounting)). 429s include `Retry-After` when available. | Which `:free` models exist on the day of the run. | Secondary / fallback provider. Its reported `cost` gives a real `reported` cost status. |
| **Ollama** | Installed locally; OpenAI-compatible `/v1/chat/completions`. | Model choice that fits in 8 GB. | Local dev, offline demo, fallback testing. Never deployed. |
| **Mock** | — | — | Deterministic, scriptable failures. Every response is labelled `simulated: true`. Used by all automated tests. |

**Quota impact:** 45 cases × 2 strategies = 90 calls per run, plus retries. That fits easily in Groq's free
plan (to be confirmed). It would use almost all of OpenRouter's 50/day, so OpenRouter is a fallback in the
benchmark, not a primary.

**Hosting (to finalise in Phase 7):** Render's free web service sleeps after 15 minutes idle and takes ~1 minute
to wake ([Render changelog](https://render-www.onrender.com/changelog/free-web-services-now-remain-active-while-receiving-websocket-messages)).
That's acceptable for a portfolio demo, but the rest of Render's free-tier details came from third-party blogs
that disagree, so I'll verify them against official pages before choosing. Candidates: Render free web
service, Hugging Face Spaces (Docker), Koyeb free. Frontend on Vercel Hobby (static build). Database on Neon free.
**No host is chosen until its official docs confirm: no card required, outbound HTTPS allowed, request timeout
≥ 60 s.**

## 3. Architecture

```
                 ┌──────────────────────── FastAPI backend ─────────────────────────────┐
Client ──POST──▶ │ /api/v1/generate                                                      │
 (tenant key)    │  1 Auth (hashed key → tenant)                                        │
                 │  2 Rate limit (DB fixed window, atomic upsert)                        │
                 │  3 Validate + idempotency check (tenant_id, request_id)               │
                 │  4 Classify (deterministic features → complexity score → tier)        │
                 │  5 Candidates (registry ∩ capability ∩ health ∩ latency ∩ free-only)  │
                 │  6 Budget reservation (atomic, worst-case cost of chosen candidate)   │
                 │  7 Cache lookup (off by default; tenant-scoped key)                   │
                 │  8 Execute: timeout → bounded retry+backoff → next fallback candidate │
                 │  9 Settle: actual cost, release unused reservation                    │
                 │ 10 Persist request_log + request_attempts + usage_record              │
                 └───────┬──────────────────┬───────────────────┬────────────────────────┘
                         │ adapters         │                   │ SQLAlchemy
               Groq · OpenRouter · Ollama · Mock          PostgreSQL (Neon)
                                                                 ▲
React dashboard (Vercel) ──admin token──▶ /api/v1/admin/* ───────┘
Evaluation runner (CLI) ──tenant key──▶ same gateway code path (in-process or HTTP)
```

Order note (S1-02): the screenshot puts budget check before cache and router. The budget must be
reserved against a *specific* model's worst-case price, so the classifier and candidate filter run first.
They're pure functions with no I/O. Budget **enforcement** still happens before any cache read or provider
call, which is what the screenshot's order protects. A cache hit releases the reservation. This is documented
as a deliberate deviation in `docs/ARCHITECTURE.md#request-path`.

### Backend modules (`backend/app/`)

| Module | Responsibility |
|---|---|
| `api/v1/` | HTTP only: request parsing, status codes, error envelope. No business logic. |
| `auth/` | API-key hashing (SHA-256 with server pepper; keys are high-entropy so a slow KDF isn't needed), prefix lookup, admin token. |
| `tenancy/` | Tenant resolution, rate limiting. |
| `routing/` | `features.py` (extraction), `classifier.py` (score → tier), `policy.py` (candidates, ranking, fallback chain), `decision.py` (structured record). Pure and unit-testable. |
| `providers/` | `base.py` interface + error taxonomy, `openai_compat.py` shared HTTP logic, `groq.py`, `openrouter.py`, `ollama.py`, `mock.py`. |
| `resilience/` | Retry/backoff, `Retry-After`, circuit breaker. |
| `accounting/` | Cost calculation and status, budget reservation/settlement, metrics (percentiles, rates). |
| `cache/` | Optional response cache (DB table, TTL). |
| `services/gateway.py` | Orchestrates the 10 steps above. |
| `db/` | Models, session, Alembic migrations, seed command. |

## 4. Routing policy v1 (`policy_version = "rw-2026.11-v1"`)

**Not an AI classifier.** It's a transparent weighted heuristic, documented with its limitations.

1. **Features** (no LLM call): declared `task_type`; estimated input tokens (`chars/4`, upgraded to a
   tokenizer later if justified); `max_output_tokens`; `response_format=json`; complexity markers
   (multi-step instructions, number of explicit constraints, code blocks, math expressions, "prove / derive /
   compare / trade-off" verbs); `quality` (`low | standard | high`); `latency_target_ms`; `max_cost_usd`.
2. **Complexity score 0–100** = task-type prior + weighted feature contributions. The weights live in
   `config/routing_policy.yaml`, not in code. Thresholds: `< 35 → small`, `35–64 → medium`, `≥ 65 → premium`.
   `quality=high` sets a minimum of medium (`HIGH_STAKES`). Each contribution is kept in the decision record so the
   score is fully explainable.
3. **Candidate filter.** Each excluded model gets a reason: disabled, `MODEL_UNAVAILABLE` (circuit open or
   missing from the live catalog), `CONTEXT_TOO_SMALL`, `CAPABILITY_MISSING` (e.g. JSON mode),
   `LATENCY_CONSTRAINT` (observed p95 above the target), `BUDGET_CONSTRAINT` (worst-case cost above
   `max_cost_usd` or remaining budget), `PAID_MODEL_BLOCKED`.
4. **Ranking.** Lowest tier ≥ required tier first, then reference cost, then observed p95 latency, then
   provider health. Escalating *upward* is allowed when the required tier has no eligible model
   (`TIER_ESCALATED`). Downgrading is allowed only if the request sets `allow_downgrade=true` (`TIER_DOWNGRADED`).
5. **Fallback chain** = the remaining ranked candidates. Each one was already filtered, so a fallback can never
   break budget or policy constraints. Reason codes on the attempts include `FALLBACK_AFTER_TIMEOUT`,
   `FALLBACK_AFTER_RATE_LIMIT`, and `FALLBACK_AFTER_ERROR`.
6. **Paid-model guard.** `ALLOW_PAID_MODELS=false` by default. Models with `billing: paid` are excluded at
   load time *and* re-checked in the executor right before the HTTP call (defence in depth).

## 5. Cost model (key FinOps decision)

Free-tier calls are billed at $0, so a naive "savings %" would be meaningless (C-03). Each attempt records:

| Field | Meaning |
|---|---|
| `billed_cost_usd` + `billed_cost_status` | What was actually charged. `reported` when the provider returns it (OpenRouter `usage.cost`), `estimated` when computed from a verified free-tier price of $0, `unavailable` otherwise. |
| `reference_cost_usd` + `reference_cost_status` | Tokens × the provider's **published pay-as-you-go list price** for that model (`pricing_version`, `effective_date`, `source_url`). This is what the routing policy optimises and what the evaluation compares. It's always labelled *estimated*. If no verified price exists, the status is `unavailable` and the model is ranked last on cost. |

Tenant budgets are enforced on `reference_cost_usd` (configurable), plus an optional daily token cap. Reservation
uses the worst case (input estimate + `max_output_tokens`) at list price via
`UPDATE tenant_budgets SET reserved = reserved + :r WHERE id = :id AND spent + reserved + :r <= limit`.
That's atomic in PostgreSQL, so concurrent requests can't jointly overspend. Settlement moves the actual cost
from `reserved` to `spent`. Retries are attempt-level rows. Only the final successful attempt (plus any
provider-billed failed attempts) contributes to spend.

## 6. Database (Alembic-managed)

`tenants`, `api_keys` (prefix, sha256 hash, revoked_at), `tenant_budgets` (period, limit, spent, reserved),
`rate_limit_windows` (tenant, window_start, count — *added: needed for P-14 without Redis*),
`provider_models` (registry snapshot incl. pricing, verified_on), `routing_policies` (version, config JSON),
`request_logs` (one per client request: decision JSON, status, latency, totals, prompt hash),
`request_attempts` (one per provider call), `usage_records` (settled cost per request, per tenant and period),
`response_cache` (optional), `evaluation_cases`, `evaluation_runs` (config snapshot, preregistration hash),
`evaluation_results`. All tenant-owned tables carry `tenant_id` with an index and an `ON DELETE` rule.
Uniqueness: `(tenant_id, client_request_id)`. Full design goes in `docs/DATABASE_SCHEMA.md` in Phase 1.

## 7. Evaluation design

- **Dataset:** 45 original cases. 15 simple (classification, extraction, formatting), 18 standard (summaries
  with required facts, multi-field JSON extraction, short reasoning), and 12 complex (multi-step math, code with
  unit tests, constraint satisfaction). Each case has acceptance criteria, `max_cost_usd`, and `max_latency_ms`.
- **Scorers (deterministic):** exact/normalised match, regex, JSON Schema + field equality, required-content
  checks, numeric tolerance, and Python unit tests run in a subprocess with a timeout and no network
  (local only; risk documented). Subjective cases get a written rubric and a human-review CSV. **No LLM judge.**
- **Pre-registration (S1-12):** `preregistration.yaml` holds the quality rule *before* any live run. For example:
  "RouteWise pass rate ≥ baseline − 5 pp and every case meets its `max_latency_ms`". The file hash is stored on
  the run, and the runner refuses to start without it.
- **Strategies:** A = strongest eligible free model for every case. B = RouteWise policy. Optionally C =
  small-only, as a lower bound to show the router adds value. Same cases, same parameters, temperature 0,
  same run date.
- **Outputs:** `evaluation/reports/<run_id>/results.jsonl` + `summary.json` + `summary.md`, with Wilson/bootstrap
  CIs. The dashboard Evaluation page reads them from the DB. Mock runs are stamped `simulated` and are never shown
  as results.

## 8. Phases and exit criteria

| Phase | Scope | Exit criterion (verified, not assumed) |
|---|---|---|
| 1 Foundation | Repo layout, uv/pyproject, ruff/mypy, FastAPI skeleton, settings, structured logging with redaction, SQLAlchemy models, Alembic initial migration, seed command, mock provider, health/ready, Vite+React+Tailwind shell, `.env.example`, `.gitignore`, CI skeleton | `pytest` + `ruff` + `mypy` + `npm run build` pass locally; migration applies to Postgres |
| 2 Gateway core | Adapters (Groq, OpenRouter, Ollama, Mock), registry, routing engine, executor with retry/backoff/circuit breaker/fallback, `/generate`, catalog endpoints | Routing unit tests and failure modes 1, 2, 3, 5 pass with mocks; one real Ollama call works locally |
| 3 Tenancy and accounting | API keys, auth, rate limits, budget reservation, cost accounting, usage aggregation, admin endpoints, idempotency, optional cache | Isolation, concurrency (Postgres), budget (failure mode 4), and no-double-count tests pass |
| 4 Evaluation | Dataset, scorers, runner, reports, pre-registration, **live run (needs your keys)** | Mock benchmark test passes; live report generated, or marked "not yet performed" |
| 5 Dashboard | 8 pages on real API, loading/empty/error states, responsive, demo banner | Vitest + Playwright (desktop + mobile) pass |
| 6 Verification | Full test suite, lint, types, audits (`pip-audit`, `npm audit`), secret scan (gitleaks), e2e | All green, with results recorded in `TASKS.md` |
| 7 Deployment | Verify hosts, deploy, real screenshots, README numbers from reports | Live health, DB, and one real provider request verified |

## 9. Decisions needed from you

1. **Local PostgreSQL** (needed in Phase 1). Recommended: install PostgreSQL 17 locally with
   `winget install PostgreSQL.PostgreSQL.17` (free; the installer asks for admin rights and a superuser password).
   Alternative: a Neon free project used as the dev DB (needs a Neon account; the Neon MCP connector in this
   session also needs authorizing first). Either way, CI uses its own Postgres container. Unit tests use SQLite
   for speed; concurrency and integration tests require Postgres.
2. **Cost model in §5.** Approve budgets and routing on *reference list-price cost*, with billed cost tracked
   separately.
3. **Provider keys.** Not needed until the end of Phase 2. You'll create a free Groq key and, optionally, a free
   OpenRouter key yourself, and put them in `backend/.env` (never in chat). Before you sign up, I'll check the
   official terms for any card requirement.
4. **Ollama model.** Later, I'll ask you to run `ollama pull qwen2.5:1.5b` (~1 GB) for local tests.

## 10. Top risks

| Risk | Mitigation |
|---|---|
| Free-tier catalogs change mid-project | Registry verified at startup; run reports snapshot the config |
| Router shows no benefit when the strongest free model is cheap and fast | Report honestly; this is a valid result. Strategy C and per-tier analysis show where the router helps |
| Heuristic misroutes short but hard prompts | Documented as an observed failure mode (S2-05); policy is versioned so v2 can be compared |
| Free host cold starts skew latency | Benchmark runs locally against the real providers; hosted latency is reported separately |
| Running model-generated code in scorers | Subprocess, timeout, temp dir, no network, local only; documented |
