# Testing

All automated tests use the mock provider or in-memory HTTP transports. **No test calls a real provider or spends
quota.** Results below are from Windows on 2026-11-04.

## Commands (PowerShell)

```powershell
cd backend
uv run ruff check .; uv run ruff format --check .; uv run mypy app tests
uv run pytest -q -W error::RuntimeWarning          # SQLite; PostgreSQL variants need TEST_DATABASE_URL
$env:RUN_LIVE_DB_TESTS = "1"; uv run pytest tests/integration -q; Remove-Item Env:RUN_LIVE_DB_TESTS   # rolled back
cd ..\frontend
npm run lint; npm run typecheck; npm test; npm run build
npx playwright install chromium   # once
npm run test:e2e                  # starts a real backend on a throwaway SQLite DB + the built dashboard
```

## Results (latest CI run, 2026-11-06, commit `61984cd`, GitHub Actions run 42168398327)

| Suite | Result |
|---|---|
| Backend lint / format / mypy strict | clean |
| Backend pytest (SQLite **and** PostgreSQL 17 service) | **1,689 passed, 10 skipped, 27 xfailed** (skips = opt-in live-database checks; xfails = strict markers on superseded benchmark revisions' manifest tests, which must fail) |
| Migrations on PostgreSQL | `0001 → 0002 → 0003` applied in CI before the tests |
| Frontend Vitest | **28 passed** (29 since the 2026-11-07 Evaluation-page fix and its regression test) |
| Playwright E2E (desktop + mobile) | **9 passed** |
| `pip-audit` / production `npm audit` | no known vulnerabilities / 0 vulnerabilities |
| `detect-secrets` | clean against the reviewed baseline |

The same 1,689 backend tests also passed locally against a disposable PostgreSQL 17 on 2026-11-06.

## Earlier results (local run, 2026-11-04, before CI existed)

| Suite | Result |
|---|---|
| Backend lint / format / mypy strict | clean (95 source files) |
| Backend pytest | **363 passed, 85 skipped** (skips = PostgreSQL variants without `TEST_DATABASE_URL`, plus opt-in live checks) |
| Live Neon checks (rolled back) | **10 passed**; table row counts identical before and after |
| Frontend lint / typecheck / build | clean (pages code-split) |
| Frontend Vitest | **28 passed** |
| Playwright E2E (desktop 1366×860 + Pixel 7) | **9 passed, 1 skipped** (a mobile-only test skipped on desktop) |
| `pip-audit` (backend lockfile) | no known vulnerabilities |
| `npm audit --omit=dev` | 0 vulnerabilities |
| `npm audit` (all) | 12 moderate, all from one dev-only `minimatch` advisory via ESLint; the only fix is a breaking downgrade. Accepted |
| `detect-secrets` | 14 findings, all reviewed test fixtures, recorded in `.secrets.baseline`; a planted fake key is detected |

CI now runs on every push to `main` and on pull requests. That's where the PostgreSQL variants run, including
concurrent budget reservations, rate-limit counting and concurrent benchmark execution claims on real PostgreSQL.

## Coverage map

| Area | Tests |
|---|---|
| Provider contract (every adapter): success, usage, timeout, network, 429 + Retry-After, 401, 5xx, 5 malformed shapes, empty completion, secret redaction, truncation, JSON mode, redirects refused, catalog | `tests/providers/test_contract.py` |
| Provider specifics: Groq dialect and status codes; OpenRouter `:free` guard, quota (counts failures; account-level limit from `/key`), `usage.cost`, errors in HTTP 200; Ollama | `tests/providers/test_adapters.py` |
| Routing: determinism, scoring, tiers, client floor/downgrade, high-stakes, exclusions (16 codes), budget/unknown price, latency (observed only), health, simulated rules, fallback-only providers, `lowest_tier_first`, JSON premium fallback, fallbacks obey all constraints | `tests/routing/test_engine.py` |
| Health: breaker closed/open/half-open, cooldowns, provider lockout, catalog availability, p95 | `tests/resilience/test_health.py` |
| Executor: retries, backoff, Retry-After cap, 429 never retried, fallback, bad request stops, total failure, breaker across requests, quota skip, paid guard, deadline, **budget cap** | `tests/services/test_executor.py` |
| Cost: actual vs list, unknown ≠ 0, settlement without double counting | `tests/accounting/test_cost.py` |
| Budgets: reserve/settle, all-or-nothing across periods, limit change, new period, **25 concurrent reservations → exactly 10**, stale release | `tests/accounting/test_budget.py` (SQLite + PG) |
| Rate limit: window, isolation, **12 concurrent hits counted exactly**, prune | `tests/tenancy/test_rate_limit.py` (SQLite + PG) |
| Auth and tenancy: bad keys (6 kinds), suspended tenant, key create/list/revoke/rotate (with and without grace), admin disabled/forged/expired sessions, login throttle, config has no secrets, tenant CRUD, **cross-tenant isolation**, per-tenant idempotency, rate-limit rejection, **budget exhaustion with spend = sum of request costs and reservations released** | `tests/api/test_auth_and_tenancy.py` |
| `/generate` end to end: timeout→retry, 429→fallback, invalid creds→other provider, malformed→fallback, all fail→502, breaker, budget/capability rejection, paid registry refuses start, idempotency, validation, 413, **no secret or prompt leakage in logs, DB or errors** | `tests/api/test_generate.py` |
| Evaluation: dataset integrity, **45 reference pairs (correct passes, wrong fails)**, code sandbox off by default and timeouts, stats, full mock pipeline (interleaving, failures kept, provenance, not publishable) | `tests/evaluation/` |
| Config: paid models refused; production refuses weak secrets and SQLite | `tests/test_config.py` |
| Frontend: sign-in/out, session expiry → sign-in, admin token never stored, every page with data/empty/error, filters, pagination, request detail, one-time key reveal, unknown charges never shown as $0, DEMO banner logic | `src/**/*.test.ts(x)` |
| E2E: key → generate → routing → mock response → accounting → DB → dashboard; 401/402/409; tenant isolation over HTTP; all 8 pages without horizontal overflow on desktop and mobile | `frontend/e2e/` |

## Not covered (honestly)

- Real provider behaviour in automated tests (by design: tests never call real providers). Groq was exercised live
  only by the benchmark; OpenRouter and Ollama never live.
- Docker image build locally (no Docker locally); Render builds it on every deploy.
- Load testing beyond the concurrency unit tests.
