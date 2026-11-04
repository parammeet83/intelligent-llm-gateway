# Operations Runbook

Commands run from `backend\` with `uv run python -m app.cli …` against the configured `DATABASE_URL`.

## Routine

| Task | Command / action | Frequency |
|---|---|---|
| Settle abandoned budget reservations (charged in full: their usage is unknown) | `reconcile` (pending requests older than `STALE_RESERVATION_S`, default 600 s) | after crashes; daily is safe |
| Prune rate-limit windows | `prune` (older than 1 day) | daily or weekly |
| Sync registry and record policy | `seed --no-demo` | after editing `models.yaml` / `routing_policy.yaml` |
| Re-verify provider catalog and prices | edit `models.yaml` (`verified_on`, new `effective_date` for price changes) | before each benchmark run |
| Apply migrations | `uv run alembic upgrade head` (also runs at container start) | on deploy |

## SLOs (informational, from the pre-registration)

p95 end-to-end latency ≤ 15 s on the hosted demo (free tiers queue and cold-start). Watch the Overview page:
success rate, p50/p95, fallback rate, rate-limit rejection rate.

## Incidents

| Symptom | Likely cause | Action |
|---|---|---|
| `/ready` 503, `database: unavailable` | Neon compute waking, wrong `DATABASE_URL`, or network | Retry after ~5 s; check the URL in host secrets; check Neon status |
| `/ready` 503, `migrations: pending` | code newer than schema | `alembic upgrade head` |
| Many `ALL_PROVIDERS_FAILED` | provider outage, quota exhausted, or bad key | Providers page: circuit and exclusion per model. `PROVIDER_AUTH_FAILED` means rotate the provider key in host secrets |
| `QUOTA_EXHAUSTED` on OpenRouter | 50/day free allowance used | Expected. It recovers at 00:00 UTC; never buy credits for this project |
| Spike of `RATE_LIMITED` (429) | a tenant exceeding `rate_limit_rpm` | Raise the limit via `PATCH /admin/tenants/{slug}` only if intended |
| Tenant gets `BUDGET_EXHAUSTED` | shadow budget used up | Tenants page: check spent vs reserved. If `reserved` stays high with no traffic, run `reconcile` |
| Tenant key leaked | — | `rotate-api-key KEY_ID` (or `revoke-api-key`), then send the new key out of band |
| Admin token leaked | — | Replace `ADMIN_TOKEN` in host secrets and restart. All dashboard sessions become invalid |
| Pepper changed by mistake | every tenant key stops working | Restore the old `API_KEY_PEPPER`; otherwise reissue every key |

## Data protection

- Never run destructive tests against the main database. The fixture-based PostgreSQL tests drop the schema and only
  run when `TEST_DATABASE_URL` is set; that must be a disposable database (CI container or a Neon branch).
- Non-destructive live checks: `$env:RUN_LIVE_DB_TESTS = "1"; uv run pytest tests/integration -q` (always rolled back).
- Before a risky migration, create a Neon branch to test it on. Check Neon's current docs for the restore and history
  window available on your plan (not verified here).
