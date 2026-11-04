# Database Schema

Managed by Alembic (`backend/alembic/versions/`). Current head: **`0002`**, applied to Neon on 2026-11-04 with no drift.

| Revision | Change |
|---|---|
| `0001` | Initial schema (12 tables) |
| `0002` | Additive: `api_keys.expires_at` (rotation grace period), `request_logs.budget_reservation` JSON (crash-safe reservation release) |

Notes: `tenants.cache_enabled` exists from `0001` but is **unused**, because caching was rejected (TENANCY_AND_SECURITY.md).
`routing_policies` is written by `app.cli seed`: each policy version is stored once, and editing a recorded version
without bumping it is refused. `evaluation_*` tables are written by `app.cli eval-run`.
Source of truth for columns: `backend/app/db/models.py`. CI (and the `test_migrations_match_models`
test) fails if models and migrations drift apart.

## Commands (PowerShell, from `backend\`)

```powershell
uv run alembic upgrade head          # apply migrations to DATABASE_URL
uv run alembic downgrade -1          # roll back one revision
uv run alembic upgrade head --sql    # print the SQL without connecting
uv run python -m app.cli seed        # sync model registry + demo tenants (idempotent)
```

## Tables

| Table | Purpose | Ownership / deletion |
|---|---|---|
| `tenants` | Tenant config: status, rate limit (RPM), daily/monthly **shadow budgets** (USD, list-price), cache opt-in. | Root. Suspend rather than delete. |
| `api_keys` | `key_prefix` (public, unique) and `key_hash` (HMAC-SHA256, unique). `revoked_at` for revocation. No plaintext. | `CASCADE` from tenant |
| `tenant_budgets` | Per-period ledger: `limit_usd`, `spent_usd`, `reserved_usd`. Unique `(tenant_id, period, period_start)`. CHECKs keep both amounts ≥ 0. | `CASCADE` from tenant |
| `rate_limit_windows` | Fixed-window counters. PK `(tenant_id, window_start)`, updated with an atomic upsert. | `CASCADE` from tenant |
| `pricing_snapshots` | Append-only list prices: per-Mtok input/output, `effective_date`, `retrieved_on`, `source_url`, `simulated`. Unique `(provider, model_id, effective_date)`. | Never edited; a price change is a new row |
| `provider_models` | Model registry synced from `config/models.yaml`: tier, billing class, context window, capabilities, `verified_on`, `source_url`, current pricing snapshot. | `SET NULL` if a snapshot is removed |
| `routing_policies` | Versioned routing configs (`version` unique, one `is_active`). | — |
| `request_logs` | One row per client request: status, decision JSON, policy version, settled tokens and cost, `prompt_sha256` (no content), `simulated`. Unique `(tenant_id, client_request_id)` for idempotency. | `RESTRICT` from tenant (audit trail) |
| `request_attempts` | One row per provider call, including retries and fallbacks: reason code, status, HTTP status, `retry_after_s`, tokens, cost, pricing snapshot. Unique `(request_id, attempt_number)`. | `CASCADE` from request |
| `evaluation_cases` | Benchmark cases. Unique `(dataset_version, case_key)`. | — |
| `evaluation_runs` | One run per strategy: config snapshot, `preregistration_sha256`, `simulated`. | — |
| `evaluation_results` | Per-case outcome: pass/score, model, tier, cost, latency, scorer details. Unique `(run_id, case_id)`. | `CASCADE` from run |

### Considered and not added

- **`usage_records`.** Settled per-request totals already live on `request_logs`, and budget spend
  lives in `tenant_budgets`. A third copy would need to be kept consistent with both. Aggregates are
  computed by query (indexed by `(tenant_id, created_at)`). A rollup table can be added later if
  dashboard queries get slow.
- **`response_cache`.** Deferred to Phase 3. The cache is off by default and may not be needed.

## Cost columns (shared by `request_logs`, `request_attempts`, `evaluation_results`)

| Column | Meaning |
|---|---|
| `input_tokens`, `output_tokens` | As reported by the provider. NULL if not reported. |
| `actual_charge_usd` | What the provider actually charged. NULL unless known. |
| `cost_status` | Provenance of `actual_charge_usd`: `reported` · `free_tier` · `estimated` · `unavailable` |
| `estimated_list_cost_usd` | Shadow cost at published list price. Used for budgets and benchmarks. |
| `list_cost_status` | `estimated` (computed from a pricing snapshot) · `unavailable` (no verified price) |
| `simulated` | True for mock-provider rows. They are excluded from real-usage reporting. |

Defaults are deliberately pessimistic: a new row has `actual_charge_usd = NULL` and both statuses set
to `unavailable`, so nothing claims a cost it doesn't know (tested in `test_db_constraints.py`).
Full rules are in [COST_ACCOUNTING.md](COST_ACCOUNTING.md).

## Indexes

`request_logs(tenant_id, created_at)` for tenant dashboards, `request_logs(created_at)` for global time
series, `request_logs(status)`, `request_attempts(request_id)`, `request_attempts(provider, started_at)`
for provider health and latency, `api_keys(tenant_id)`, and `evaluation_results(run_id)`. Unique
constraints provide the rest.

## Verification on Neon (2026-11-03)

Target: Neon project `routewise-ai`, PostgreSQL 17.11, `ap-southeast-1`, direct (non-pooler) endpoint.

| Check | Result |
|---|---|
| State before migrating | Empty: 0 tables, `public` schema only |
| `alembic upgrade head` | `0001 (head)` |
| `alembic check` (live schema vs models) | No drift |
| Tables | 12 of 12, all columns match the models, no unexpected tables |
| Constraints | 12 PKs, 11 FKs, 11 unique, 19 CHECK; `request_logs` FKs: tenants `RESTRICT`, api_keys `SET NULL` |
| Types | 7 JSONB columns; money columns `NUMERIC(18,8)`; 18 of 18 timestamps `timestamptz` |
| Seed run twice | Run 2: 0 created. 2 tenants, 2 keys (one each), 3 models, 3 pricing snapshots, no duplicates |
| Live integration tests | 10 passed, all inside a rolled-back transaction; row counts unchanged |

### Running the live checks again (non-destructive)

```powershell
cd backend
$env:RUN_LIVE_DB_TESTS = "1"; uv run pytest tests/integration -q; Remove-Item Env:RUN_LIVE_DB_TESTS
```

These tests use `DATABASE_URL`, run every statement inside one outer transaction that is always rolled
back, and never truncate, drop, or migrate. They check: schema at head with no drift, timezone-aware
timestamps, seeded registry consistency, hashed keys, the idempotency unique constraint, status CHECK
constraints, `RESTRICT` on tenants with history, and `CASCADE` from requests to attempts.

The **other** PostgreSQL tests (parametrised `database_url` fixture) drop and recreate the schema. They
only use `TEST_DATABASE_URL`, refuse to run if it equals `DATABASE_URL`, and must never point at the
main Neon database.

## Engine notes

- **Neon:** TLS with certificate verification. `pool_pre_ping` + `pool_recycle=300` because Neon
  suspends idle computes. Pooler (`-pooler`) hosts get statement caching disabled.
- **SQLite (tests and zero-config dev):** `PRAGMA foreign_keys=ON` on every connection, so CASCADE and
  RESTRICT behave like they do on PostgreSQL.
