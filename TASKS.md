# TASKS — RouteWise AI

Legend: `[x]` done and verified · `[~]` in progress · `[ ]` not started · `[!]` blocked (reason given)

Last updated: 2026-11-03

## Phase 0 — Inspect and plan
- [x] Inspect both reference screenshots and extract requirements
- [x] Inspect workspace, Git state, and local tooling (Python 3.12, Node 24, uv, Ollama; no Docker, no Postgres)
- [x] Initial provider documentation check (Groq, OpenRouter, Render); unverified items listed in plan §2
- [x] `docs/REQUIREMENTS_TRACEABILITY.md` with contradictions C-01…C-14
- [x] `implementation_plan.md`
- [x] `CLAUDE.md` working rules
- [x] Plan decisions approved (Neon, cost model with your amendments)

## Phase 1 — Foundation
Verified 2026-11-03 on Windows: backend **59 passed, 22 skipped** (12 destructive PostgreSQL variants needing
`TEST_DATABASE_URL`, plus 10 opt-in live-DB checks; the latter **passed against Neon** when enabled);
ruff and ruff-format clean; mypy `--strict` clean. Frontend: **13 passed**;
eslint and tsc clean; production build OK; `npm audit --omit=dev` shows 0 vulnerabilities.

- [x] Repo layout (`backend/`, `frontend/`, `evaluation/`, `docs/`, `scripts/`, `.github/workflows/`)
- [x] `.gitignore` (verified: `.env` and `*.db` ignored, `.env.example` tracked); `.env.example` placeholders only
- [x] Backend: uv project + lockfile, FastAPI app factory, pydantic-settings, ruff, mypy strict, pytest
- [x] JSON logging with field-name and credential-pattern redaction; content off by default (`test_logging.py`)
- [x] SQLAlchemy models (12 tables) + Alembic `0001`; drift check and up/down round trip (`test_migrations.py`)
- [x] Seed command, idempotent; keys hashed, plaintext shown once (`test_seed.py`)
- [x] Model registry YAML + validation (provenance required, paid models rejected) (`test_catalog.py`)
- [x] Mock provider, labelled `simulated`, scriptable failures; error taxonomy (`test_mock_provider.py`)
- [x] API-key generation and hashing (HMAC-SHA256 + pepper) (`test_api_keys.py`)
- [x] `/api/v1/health`, `/api/v1/ready` (DB + migration head; no detail leakage) (`test_health.py`)
- [x] Consistent error envelope + `X-Request-ID` (`test_health.py`)
- [x] Neon URL normalisation for asyncpg (TLS verify, pooler handling) (`test_session_url.py`)
- [x] Frontend shell: Vite 8 + React 19 + TS 6 + Tailwind 4 + router; 8 nav pages (honest placeholders),
      live Overview health and readiness, DEMO banner, loading/empty/error states (`App.test.tsx`, `client.test.ts`)
- [x] `scripts/dev.ps1` one-command run. Smoke-tested: migrate → seed ×2 → `/health` 200, `/ready` 200, 404 envelope
- [x] CI workflow (`.github/workflows/ci.yml`): green on GitHub since 2026-11-04 (backend incl. PostgreSQL 17 variants, secrets, frontend, e2e). First runs fixed a nonexistent `setup-uv@v10` tag and a job-wide `APP_ENV` that conflicted with the pinned manifests
- [x] **Neon verified 2026-11-03** (project `routewise-ai`, PostgreSQL 17.11, region ap-southeast-1):
  - `DATABASE_URL` uses the **direct** endpoint (not `-pooler`), `sslmode=require` + `channel_binding=require`, TLS with certificate verification
  - Database was empty before migrating (0 tables, `public` schema only)
  - `alembic upgrade head` → `0001 (head)`; `alembic check` → no drift
  - 12/12 tables present, columns match models; 11 FKs, 11 unique, 19 CHECK constraints; all 18 timestamp columns are `timestamptz`
  - `app.cli seed` ×2: run 1 created 3 models, 3 pricing snapshots, 2 tenants, 2 keys; run 2 created nothing.
    No duplicate slugs/models, exactly one key per tenant, keys stored as 64-char hashes only
  - Backend on Neon: `/api/v1/health` 200, `/api/v1/ready` 200 (`database: ok`, `migrations: ok`); first `/ready` ~2.7 s (cold TLS connection / compute wake); no credentials in server logs
  - Live DB tests (`tests/integration/test_live_database.py`, opt-in, always rolled back): **10 passed**. Row counts identical before and after; no leftover rows
- [!] Destructive PostgreSQL test variants (12, drop/truncate schema): **not run against Neon by design**. They run in CI, or locally only with `TEST_DATABASE_URL` set to a disposable Neon branch
- [ ] Demo API keys from the Neon seed were masked during verification and can't be recovered (only hashes are stored).
      Phase 3 adds a `create-api-key` / `revoke-api-key` command to issue new ones
- [x] Docs: ARCHITECTURE, DATABASE_SCHEMA, COST_ACCOUNTING (model), README (setup only)

Known, accepted: `npm audit` (all deps) reports a moderate `minimatch` advisory in ESLint's dev-only
tooling. The only offered fix is a breaking downgrade of typescript-eslint. Nothing ships to the browser.
Re-check in Phase 6.

## Phase 2 — Gateway core
Verified 2026-11-03 on Windows: backend **264 passed, 55 skipped**. The skips are PostgreSQL variants
waiting for a disposable `TEST_DATABASE_URL`, plus the opt-in live checks, which **passed against Neon
(10/10)**. ruff, ruff-format, and mypy `--strict` are clean. No live provider calls: no keys are configured.

- [x] Provider interface + error taxonomy (9 kinds; retryable vs fallback-eligible; consumed usage on errors) — `test_contract.py`
- [x] Mock provider + **contract suite run against every adapter** (89 tests in `tests/providers` + 12 in
      `tests/test_mock_provider.py`, all on fake transports)
- [x] Groq adapter: `max_completion_tokens`; 422→malformed, 498→server; tokens never treated as a charge — `test_adapters.py`
- [x] OpenRouter adapter: `:free`-only guard (no HTTP call for others), quota guard (20/min, 50/day, counts
      failures), `/key` quota sync, `usage: {include: true}` sent, `usage.cost` parsed, errors inside HTTP 200, `max_retries=0`
- [x] Ollama adapter: localhost-only (settings refuse non-loopback and production), no credentials
- [x] Normalisation + classification: malformed bodies, empty completions, redirects refused, messages truncated + redacted
- [x] Docs verified and cited: Groq models/errors/structured outputs/billing, OpenRouter limits/errors/usage/catalog, Ollama compat
- [x] Groq billing: `free_tier` only when `GROQ_BILLING_PLAN=free` is declared (the plan can't be detected)
- [x] Model registry: 10 real models (7 priced from published sources, 3 unpriced, 1 preview disabled) + 3 mock
- [x] Routing engine `rw-2026.11-v1`: configurable weights/thresholds, 16 exclusion codes, reason codes,
      decision record, fallback-only providers (OpenRouter) — `test_engine.py` (36)
- [x] Fallbacks obey the same constraints (property test across 6 constraint mixes)
- [x] Health: circuit breaker (closed/open/half-open probe), 429 cooldown, provider lockout on auth/quota,
      latency p95 (≥5 samples), catalog availability — `test_health.py` (12)
- [x] Executor: jittered exponential backoff, Retry-After (≤ cap), deadline, 429 never retried, paid guard,
      attempt records — `test_executor.py` (20)
- [x] Cost accounting: actual vs estimated list cost, unknown ≠ 0, per-request settlement — `test_cost.py` (15)
- [x] `POST /api/v1/generate`, `GET /api/v1/models`, `GET /api/v1/providers` — `tests/api/test_generate.py` (33):
      timeout→retry, 429→fallback, invalid creds→other provider, malformed→fallback, all fail→502,
      circuit opens across requests, budget/capability rejection, paid registry refuses startup,
      idempotency (409, provider called once, per-tenant), validation, 413, no secret/prompt leakage
- [x] Temporary dev auth: localhost + admin token + tenant header; production fails closed (tested)
- [x] Neon: no migration needed (`alembic check` clean); registry re-seeded (10 models + 7 pricing snapshots
      added, idempotent on second run); live rolled-back checks 10/10, row counts unchanged
- [x] Real-server smoke test (scratch SQLite, loopback HTTP): 200 simulated generate, 409 duplicate,
      401 wrong token, 422 `tenant_id` in body; no token or prompt in server log
- [x] Docs: PROVIDER_INTEGRATION, ROUTING_METHODOLOGY, API; COST_ACCOUNTING and ARCHITECTURE updated; `.env.example`
- [x] **Groq live verification** (2026-11-04): request 1 → 404 on retired `llama-3.1-8b-instant` (kept as audit record); request 2 →
      `openai/gpt-oss-20b` succeeded after the official `/models` list and the startup catalog check (83 in / 21 out / 5 reasoning
      tokens, 3,775 ms provider, 5,678 ms end to end, `free_tier` $0, est. list $0.00001253, persisted to Neon). docs/PROVIDER_INTEGRATION.md
- [x] Retired Groq Llama 3.1 8B / 3.3 70B disabled; `gpt-oss-20b` moved to small tier with `reasoning_effort: low`; catalog re-seeded
      (14 models updated, pricing snapshots unchanged); Groq now has no medium-tier model (medium → `gpt-oss-120b`)
- [ ] OpenRouter live check: needs `OPENROUTER_API_KEY` (optional)
- [ ] Ollama live check: needs `ollama pull qwen2.5:1.5b`
- [x] Reasoning-model token budgets: per-model `reasoning_effort` (registry), `include_reasoning: false`, reasoning tokens
      parsed and reported. Empty completions remain possible at very small limits (classified `MALFORMED`)

## Phase 3 — Tenancy and accounting (verified 2026-11-04)
- [x] Tenant API-key auth (prefix lookup + constant-time HMAC); generic 401 for every failure — `test_auth_and_tenancy.py`
- [x] Key create / list (prefix only) / revoke / rotate (immediate or grace period) via CLI and admin API; plaintext shown once
- [x] Admin bootstrap: `ADMIN_TOKEN` host secret, fail-closed until set; signed short-lived dashboard sessions; login throttle
- [x] Production refuses weak/default pepper, short admin token, SQLite — `test_config.py`
- [x] Tenant isolation across `/me/*`, request detail (404 cross-tenant), usage, budgets, idempotency keys
- [x] DB-backed fixed-window rate limits (atomic upsert); 12 concurrent hits counted exactly; rejections logged; request_id not consumed
- [x] Daily/monthly shadow budgets: atomic reservation in a SAVEPOINT, budget-capped executor, settlement in the same
      transaction as attempts, crash recovery via `reconcile`; 25 concurrent reservations → exactly 10 (SQLite)
- [x] `402 BUDGET_EXHAUSTED` when the tenant budget binds (bug found and fixed: it previously returned 422)
- [x] Unknown usage (timeout, 5xx, no usage block) is never $0: draws its worst case from the budget cap and the tenant
      budget, makes the list cost `unavailable`; abandoned reservations are charged in full (`ABANDONED_RESERVATION_CHARGED`).
      Regression tests in `test_cost.py`, `test_budget.py`, `test_executor.py`, `test_auth_and_tenancy.py`
- [x] Usage aggregates (totals, provider/model/tier/tenant, time series, latency histogram, rejection and fallback rates)
- [x] Migration `0002` (additive) applied to Neon; `alembic check` clean; registry and policy re-seeded; live checks 10/10
- [x] Caching evaluated and **rejected** (privacy, low hit rate); documented
- [!] PostgreSQL run of the concurrency tests: CI only (no local PostgreSQL by design) — **pending first push**

## Phase 4 — Evaluation (framework verified; live run blocked)
- [x] 45 original cases (15/18/12), provenance meta: **AI-drafted, pending your review**
- [x] Pre-registration (5-pp non-inferiority, CI-supported; cost rule; publication rule) — runner refuses without it
- [x] Deterministic scorers (8 methods), sandboxed code tests (off by default); **45 correct/wrong reference pairs pass**
- [x] Runner: interleaved strategies, fresh health per strategy, config + pricing snapshot, failures kept, DB + report files
- [x] Report: pass rate + Wilson CI, by difficulty, cost per accepted answer, p50/p95, fallback, distributions,
      paired bootstrap, pre-registered verdicts; `publishable` flag
- [x] Mock pipeline check via CLI: 135 requests, all persisted, correctly **not publishable**
- [!] **Live benchmark run** — blocked (2026-11-04): the preflight needs an operator-verified remaining daily token
  budget of at least 648,598 tokens (583,738 worst case / 0.9) from the Groq console; no API exposes it. Registered
  candidate: `routewise_bench_v5.2.2`
- [x] **Dataset v2** (2026-11-04, owner-approved revision of v1; v1 unchanged): fixed 6 false-pass and 9 false-fail
      scoring rules; replaced C10 with an objective task; removed near-duplicates (S02, S03, S05, S10); removed 4 cases
      with confirmed LeetCode example inputs (T09, C03, C04, C05); removed all 6 code-execution cases (no safe isolation
      locally) in favour of non-executable code reasoning; relabelled T14 → simple and C02 → standard; rewrote C06 as
      complex. Distribution 15/18/12 kept. Changelog, review pack and meta in `evaluation/datasets/`
- [x] **prereg-v2** written before any v2 run (validity ≥ 95% answered, baseline floor 0.60, GPT-OSS scope note); hash
      pinned in the v2 meta; runner refuses a mismatch; report enforces the guards
- [x] v2 scoring tests: a reference pair for all 45 cases plus adversarial right/wrong answers for every changed rule
- [x] **Dataset v3** (2026-11-04, after your independent review of v2; v1/v2 unchanged): T03 → fact-extraction JSON;
      T04 → keyed decision/owner/date records; T07 → explicit instruction compliance only; T12 fully anchored;
      T17 → validated accepted translations (needs a Spanish speaker's check); C07 → exactly two unique merged SKUs;
      C09 → round-half-up specified. 15/18/12 kept
- [x] **prereg-v3** + **experiment manifest** (pinned chain meta → prereg → dataset + manifest → config/code); CI-supported
      non-inferiority required for cost claims; unknown cost observations block cost claims; errors = missing; scope statement
- [x] v3 regression tests (`test_dataset_v3.py`): corrections, v2-vs-v3 false-pass evidence, manifest drift, report rules
- [!] **Before a live run:** set `MOCK_PROVIDER_ENABLED=false` in `.env` (the manifest pins Groq-only; `eval-validate` reports the mismatch)
- [x] **Dataset v4** (2026-11-04, after your human review of v3; v1–v3 unchanged): C01 exact ANSWER line; T10/C03/C08/C09
      strict single-number ANSWER; T17 → four-option multiple choice (no native-speaker validation claimed); T03/T04 prompts
      with valid JSON examples and separate permitted values. 15/18/12 kept
- [x] **prereg-v4** + schema-2 manifest: all execution-critical code hashed; pacing pinned (sequential, 6 s, no limit) and
      enforced by `eval-run`; baseline premium-only verified and guarded; conditional pass rate + separate answer availability;
      answering model and every attempt recorded. v3 is now unrunnable on current code (its pinned code changed), by design
- [x] **Dataset v5** (2026-11-04, scoring-only revision of v4; v1–v4 unchanged): exact whole-answer matching (S01/S03/S04/S14);
      strict single numbers with explicit currency policy (S09/S10/T09/T11/T10/C03/C08/C09); T03 exact keys + JSON types
- [x] **prereg-v5** + schema-3 manifest (CLI, pacer, error types, uv.lock, runtime env, quota); token-aware `QuotaPacer` with
      recorded quota provenance; stops incomplete instead of exceeding limits. v4 now unrunnable on current code (by design)
- [!] Erratum: `routewise_bench_v4_review.md` title says "v3" (contents correct; file left unchanged as instructed)
- [!] **Dataset review** — blocked on you (`evaluation/datasets/routewise_bench_v5.meta.yaml` → `reviewed_by`;
      review pack `routewise_bench_v5_review.md`)
- [!] **Five observed failure modes** (S2-05) — 1 observed (retired-model 404, EVALUATION.md); the rest need the live run

## Phase 5 — Dashboard (verified)
- [x] 8 pages on the real API: Overview, Routing Decisions, Providers & Models, Tenants & Budgets, Usage & Cost,
      Request Logs, Evaluation, Settings; lazy-loaded (chart library split out)
- [x] Admin sign-in (session token only in sessionStorage), sign-out, auto sign-out on 401
- [x] Search, filters, sorting, pagination; request detail with score breakdown, exclusions, attempts
- [x] Actual vs estimated vs free-tier always distinct; unknown charges shown as "unknown", never $0 (bug found and fixed)
- [x] DEMO banner driven by `/health.simulated_only`
- [x] Vitest 28 passed; Playwright desktop + Pixel 7: no horizontal overflow on any page

## Phase 6 — Verification (verified locally)
- [x] Backend: ruff, ruff-format, mypy strict clean; **382 passed**, 86 skipped (PG variants + opt-in live) — 2026-11-04 after the accounting fix and catalog change
- [x] Frontend: eslint, tsc clean; Vitest 28 passed; production build OK
- [x] Playwright E2E: **9 passed** (key → generate → routing → mock response → accounting → DB → dashboard; 401/402/409; isolation)
- [x] pip-audit: no known vulnerabilities; `npm audit --omit=dev`: 0; dev-only minimatch advisory accepted
- [x] detect-secrets: 14 reviewed fixtures in `.secrets.baseline`; planted fake key detected
- [x] CI extended: PG tests, pip-audit, secret scan, E2E job
- [!] CI has never run — pending first push

## Phase 7 — Deployment (prepared; blocked)
- [x] Hosting verified from official docs: Render free (15-min sleep, ~1-min wake, SMTP-only outbound blocks); Vercel Hobby non-commercial
- [x] `backend/Dockerfile`, `.dockerignore`, `render.yaml` (API + static dashboard, secrets `sync: false`)
- [x] Production mode verified locally against Neon (health, ready, docs off, auth fail-closed, no secrets in logs)
- [ ] Docker image build — not verified (no Docker locally); first build happens on Render
- [!] Deploy — blocked: needs a push to GitHub, a Render login and Blueprint, and secrets entered (docs/DEPLOYMENT.md)
- [!] Real provider request in production — needs the deployment (Groq verified locally only)
- [x] Real screenshots captured from the running app (labelled simulated demo data)

## Release acceptance still open
1. ~~One real Groq request~~ — done 2026-11-04 (in-process gateway pipeline; not yet over HTTP `/generate`)
2. ~~Owner review of all 45 v5 cases~~ — done 2026-11-04 (attestation `b7099444…`, pinned by v5.2.2; T17
   translator-assisted)
3. Live benchmark run → publishable report → README numbers and résumé bullet
4. Five observed failure modes from real runs (1 of 5)
5. ~~First CI run green (incl. PostgreSQL concurrency)~~ — done 2026-11-04 (1,544 backend tests passed in CI)
6. Deployment verified end to end

## Finalisation (2026-11-04)
- [x] v5.2.2 publication-gate amendment: attestation-aware gate, review overlay, schema-6 manifest pinning the metadata,
  attestation, amendment and dataset; 60 tests (`test_publication_gate_v5_2_2.py`)
- [x] Neon (read-only): PostgreSQL 17.11, migration `0002` = head, `alembic check` clean, 12 tables + indexes present;
  local API against Neon: `/health` 200, `/ready` 200, missing/invalid key 401
- [x] GPT-OSS 120B live smoke test (exactly one request): succeeded, 78 in / 46 out tokens, 431 ms, headers RPD 1000 /
  TPM 8000 (docs/PROVIDER_INTEGRATION.md)
- [x] Security scans: pip-audit 0 known vulnerabilities; `npm audit --omit=dev` 0 (one moderate dev-only advisory:
  minimatch via ESLint); detect-secrets 0 findings
- [x] Deployment configuration: Render API (`render.yaml`) + Vercel dashboard (`frontend/vercel.json`)
- [x] Deployed 2026-11-04 (demo, mock provider only): API https://routewise-api-ggjk.onrender.com, dashboard
  https://routewise-dashboard.vercel.app; 26/26 production API checks and 4/4 browser checks passed (docs/DEPLOYMENT.md)
