# Architecture

Status: Phases 1–6 implemented and tested locally; Phase 7 (deployment) prepared, awaiting push and hosting access.
Live provider calls are not yet verified (no keys configured).

Phase 3–5 additions: `auth/keys.py` (key lifecycle and authentication), `auth/admin.py` (admin sessions, login throttle),
`tenancy/rate_limit.py`, `accounting/budget.py` (atomic reservations), `accounting/usage.py` (aggregates),
`api/v1/{admin,tenant,views}.py`, `services/factory.py` (one pipeline builder for the API and the benchmark),
`evaluation/` (dataset, scorers, stats, runner, report), and an 8-page React dashboard. The temporary Phase 2 dev-auth
mechanism has been removed. All tenant traffic now uses API keys.

## Components

```
┌──────────────┐  HTTPS + tenant API key  ┌──────────────────────────────────────────────┐
│ Client apps  │ ───────────────────────▶ │ FastAPI gateway (backend/app)               │
└──────────────┘                          │   api/v1      HTTP layer, no business logic │
┌──────────────┐  HTTPS + admin token     │   auth        API keys, admin token         │
│ Dashboard    │ ───────────────────────▶ │   routing     pure, deterministic policy    │
│ React (Vite) │                          │   providers   adapters behind one interface │
└──────────────┘                          │   accounting  cost, budgets, metrics        │
┌──────────────┐  in-process / HTTP       │   db          SQLAlchemy async + Alembic    │
│ Eval runner  │ ───────────────────────▶ └───────┬──────────────────────┬──────────────┘
└──────────────┘                                  │ trusted base URLs    │ asyncpg (TLS)
                                    Groq · OpenRouter · Ollama · Mock     Neon PostgreSQL
```

| Module | Built | Responsibility |
|---|---|---|
| `core/config.py` | ✅ | Typed settings from env / root `.env`. Secrets are `SecretStr`. Refuses `ALLOW_PAID_MODELS=true`. |
| `core/logging.py` | ✅ | JSON logs. Redacts sensitive field names and credential-shaped values. Drops prompt/response content unless `LOG_CONTENT=true`. |
| `core/errors.py` | ✅ | One error envelope for every failure: `{"error": {code, message, request_id, details}}`. Validation errors never echo submitted input. |
| `db/` | ✅ | Async engine, Neon URL normalisation, ORM models, migrations helper. |
| `providers/base.py` | ✅ | `Provider` interface, request/response types, error taxonomy (retryable vs fallback-eligible). |
| `providers/mock.py` | ✅ | Deterministic, scriptable, always `simulated=True`. |
| `providers/catalog.py` | ✅ | Validates `config/models.yaml`. Real models need provenance; enabled paid models are rejected. |
| `providers/http.py` | ✅ | Shared OpenAI-compatible HTTP: normalisation, error classification, no redirects. |
| `providers/{groq,openrouter,ollama}.py` | ✅ (mock-tested; no live call yet) | Provider dialects, status semantics, OpenRouter free-only + quota guards. |
| `routing/` | ✅ | Features → score → required tier → filters (with reasons) → ranking → decision record. Pure. |
| `resilience/health.py` | ✅ | Circuit breakers, cooldowns, provider lockout, latency windows, catalog availability. |
| `services/executor.py` | ✅ | Retries with jittered backoff, Retry-After, deadline, fallback chain, attempt records. |
| `services/gateway.py` | ✅ | Request orchestration, idempotent logging, persistence, response building. |
| `accounting/cost.py` | ✅ | Actual vs estimated list cost per attempt and per request. |
| `tenancy/`, budget reservation | Phase 3 | API-key auth, rate limits, atomic shadow-budget reservation. |
| `api/v1/generate.py`, `catalog.py` | ✅ | `/generate` (temporary dev auth), `/models`, `/providers`. |
| `api/v1/health.py` | ✅ | `/health` (liveness), `/ready` (DB reachable + schema at head). |

## Request path

All ten steps are implemented. Step 7 (cache) is deliberately absent: caching was evaluated and rejected.

1. **Auth.** Hash the presented key and look up the tenant. The tenant is never taken from the request body (C-01).
2. **Rate limit.** Atomic fixed-window counter in `rate_limit_windows`.
3. **Validate and idempotency check.** Unique `(tenant_id, client_request_id)`.
4. **Classify.** Pure function, no I/O, no LLM call.
5. **Candidates.** Registry ∩ capability ∩ health ∩ latency ∩ free-only.
6. **Budget reservation.** Reserve the worst-case *estimated list cost* of the chosen candidate atomically.
7. **Cache lookup.** Off by default; tenant-scoped.
8. **Execute.** Timeout → bounded retry (transient errors only) → next fallback candidate.
9. **Settle.** Move the actual estimated cost from reserved to spent; release the rest.
10. **Persist.** One `request_logs` row plus one `request_attempts` row per provider call.

**Deviation from the spec card's order (S1-02).** The card shows *budget check → cache → router*. A
reservation needs a specific model's price, so the classifier and candidate filter (both pure, with no
side effects) run before the reservation. Budget **enforcement** still happens before any cache read
or provider call, which is the property the card's order protects.

## Key decisions and trade-offs

| Decision | Why | Cost of the choice |
|---|---|---|
| **Async SQLAlchemy + asyncpg** | The gateway spends most of its time waiting on provider HTTP calls. Async keeps one process serving many concurrent requests. asyncpg works on Windows' default event loop, which async psycopg doesn't. | asyncpg rejects libpq URL options (`sslmode`, `channel_binding`), so `normalize_database_url` translates them. |
| **Neon via plain `DATABASE_URL`** | Standard PostgreSQL. No vendor SDK or connector needed. | Neon scales to zero and drops idle connections, hence `pool_pre_ping` and `pool_recycle=300`. Neon's `-pooler` endpoint is PgBouncer, so statement caching is disabled for it. |
| **SQLite for fast tests, PostgreSQL in CI** | Tests run in ~5 s locally with no database server. CI runs the *same* tests against a real Postgres 17 container. | Some behaviour (row-lock concurrency) is only meaningful on Postgres. Those tests will be marked `postgres` and run in CI or against a disposable Neon branch. |
| **Strings + CHECK constraints, not native enums** | Adding a status value is a one-line migration. | Values are validated by the DB but not by the DB type system. |
| **Rules, not an LLM, for routing** *(Phase 2)* | Deterministic, explainable, free, and adds no latency. Satisfies S1-04. | Misses semantic difficulty; documented as a known failure mode. |
| **Non-streaming v1** | Neither screenshot requires streaming; simpler accounting and retries. | Higher time-to-first-token for long outputs. |
| **In-memory provider health** | Zero dependencies; correct for one instance on a free host. | Several instances learn health separately; a restart forgets breakers, latency history, and the OpenRouter quota counter. |
| **Reject duplicate `request_id`, don't replay** | Replaying needs stored response content, which the privacy default forbids. | Clients must handle 409 instead of getting the original response back. |
| **OpenRouter fallback-only** | Its free allowance is 50 requests/day. | Even when it's cheapest on list price, it's used only if Groq can't serve. |
| **No paid fallback, enforced in config** | A hard project constraint. Validated at startup and again at the catalog level. | Fewer fallback options when free quotas run out. That surfaces as a clear error. |

## Configuration and secrets

- Backend settings come from environment variables or the repo-root `.env` (git-ignored). The template is `.env.example`.
- The frontend only receives `VITE_API_BASE_URL`. Every `VITE_*` value is public, so no secret ever goes there.
- Provider base URLs are fixed in code/settings. Clients can't supply a URL.

## Local development

`.\scripts\dev.ps1 -Setup` installs dependencies, migrates, seeds, and starts both servers. Without a
`.env`, the backend falls back to a local SQLite file so the project runs with zero configuration. With
`.env` present, it uses Neon.
