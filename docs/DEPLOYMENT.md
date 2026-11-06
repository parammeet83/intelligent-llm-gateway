# Deployment

Status (2026-11-04, verified): **deployed as a demo (mock provider only).**

- API (Render free, Singapore, Docker): https://routewise-api-ggjk.onrender.com (service `routewise-api`)
- Dashboard (Vercel Hobby): https://routewise-dashboard.vercel.app (project `routewise-dashboard`)
- Database: the existing Neon project (migrations at head)
- Production checks (2026-11-04 ~20:17 UTC): 26/26 API checks and 4/4 real-browser checks passed. These covered health,
  readiness, admin rejection and sign-in, a temporary tenant key (created, used, revoked, then rejected), invalid-key
  rejection, mock generation with a routing decision, duplicate-ID rejection, tenant isolation, CORS (dashboard origin
  allowed, foreign origin refused), the dashboard bundle targeting the API, SPA deep links and security headers.
- Production uses `MOCK_PROVIDER_ENABLED=true` and `GROQ_ENABLED=false` until the registered benchmark is finished, so
  production traffic never uses its Groq quota.
- The production `ADMIN_TOKEN` and `API_KEY_PEPPER` were generated randomly and are kept only in Render and in the
  owner's local file `%USERPROFILE%\.routewise-production-secrets.env` (never in the repository).
- The Vercel project is not linked to GitHub, because the Vercel GitHub integration isn't installed. It was deployed
  from `frontend/` with the Vercel CLI. To get automatic deploys, install the integration and connect the repository
  (root directory `frontend`).
- Render `autoDeploy` is off: deploy a new commit from the Render dashboard (*Manual Deploy*).
- The first Render deploy failed because the image flattened `backend/` into `/app`, so the app looked for
  `/backend/config/models.yaml`. The Dockerfile now mirrors the repository layout (`/app/backend`).

## Target (free tier only)

| Part | Host | Why |
|---|---|---|
| API | Render **Free** web service, Docker, Singapore | Long-running HTTP server, outbound HTTPS allowed, next to the Neon region |
| Dashboard | **Vercel** Hobby (free), `frontend/vercel.json` | Owner's chosen target (2026-11-04); SPA rewrite and security headers |
| Database | **Neon** project `routewise-ai` (existing) | Render's free Postgres expires after 30 days |
| CI | GitHub Actions | Already defined in `.github/workflows/ci.yml` |

**Verified from official docs (2026-11-04)** ([Render free](https://render.com/docs/free), [Vercel Hobby](https://vercel.com/docs/plans/hobby)):
- Render free web services spin down after **15 minutes** without traffic and take **about a minute** to wake. 750
  instance-hours per workspace per month. Outbound traffic is blocked only on ports 25/465/587, so provider APIs (443)
  and Neon (5432) work. Render says free instances are **not for production**, which suits a portfolio demo.
- The Render free-tier page doesn't say whether a card is required. **If Render asks for a payment method, stop;
  don't add one.**
- Vercel Hobby is free but **non-commercial, personal use only**, which fits this personal portfolio project. If the
  project ever becomes commercial, the dashboard must move (e.g. back to a Render static site).
- Not verified: Render's per-request timeout. The gateway's own deadline is 60 s (`REQUEST_DEADLINE_S`).

## What was verified locally

- Production mode, booted locally against Neon with `APP_ENV=production` and test-only secrets: `/health` 200, `/ready` 200
  (database ok, migrations at head), `/docs` 404, `/generate` without or with a bogus key 401, admin without a session 401,
  wrong admin token 401, admin with a session 200. No token or credentials in logs.
- Production refuses to start with a weak or default `API_KEY_PEPPER`, a short `ADMIN_TOKEN`, or SQLite (unit-tested).
- **Not verified:** the Docker image build. Docker isn't installed on the development machine; the first Render build
  is the first real build. The CI E2E job exercises the same app code with a real server and browser.

## Steps (exact actions)

1. **Push the repository to GitHub.** CI then runs. Check that all four jobs (backend, secrets, frontend, e2e) pass.
2. **Render (API):** sign in at dashboard.render.com → *New* → *Blueprint* → pick
   `parammeet83/intelligent-llm-gateway`. Render reads `render.yaml` and creates `routewise-api`.
3. **Enter secrets in Render** (prompted because of `sync: false`):
   - `DATABASE_URL`: the Neon connection string (direct or pooled; both work)
   - `ADMIN_TOKEN`, `API_KEY_PEPPER`: new values, 48+ characters each:
     `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Store them in a password manager.
   - `CORS_ORIGINS`: the Vercel dashboard URL (step 4), e.g. `https://routewise-dashboard.vercel.app`
   - Leave `GROQ_API_KEY` / `OPENROUTER_API_KEY` empty for a demo deployment.
4. **Vercel (dashboard):** sign in at vercel.com → *Add New* → *Project* → import the repository, set the **Root
   Directory** to `frontend` (it reads `frontend/vercel.json`), and add the environment variable
   `VITE_API_BASE_URL` = the Render API URL (e.g. `https://routewise-api.onrender.com`; public, not a secret).
   Then set the deployed Vercel URL as `CORS_ORIGINS` in Render and redeploy the API.
5. The API container runs `alembic upgrade head` (additive and idempotent) before starting.
6. **Verify** (PowerShell), using the URLs Render and Vercel show:
   ```powershell
   $api = "https://routewise-api.onrender.com/api/v1"   # replace with yours
   Invoke-RestMethod "$api/health"; Invoke-RestMethod "$api/ready"
   # Create a tenant and key through the admin API (prints the key once):
   $admin = @{ Authorization = "Bearer <ADMIN_TOKEN>" }
   Invoke-RestMethod "$api/admin/tenants" -Method Post -Headers $admin -ContentType application/json -Body '{"slug":"demo","name":"Demo"}'
   Invoke-RestMethod "$api/admin/tenants/demo/keys" -Method Post -Headers $admin -ContentType application/json -Body '{"name":"demo"}'
   ```
   Then call `/generate` with that key, open the dashboard, sign in, and confirm the request appears under Request Logs.
   Check mobile layout on a phone.

Use the admin API on the deployed app to create keys. Keys created locally only work if the local
`API_KEY_PEPPER` matches production's.

## Migration 0003 (v5.2.5): deploy, rollback and recovery

Migration `0003_benchmark_execution_claims` only adds the `benchmark_execution_claims` table (one row per
benchmark revision and scheduled day, enforced by a unique constraint). It reaches Neon only through a deploy:
the image's `CMD` runs `alembic upgrade head` and starts uvicorn only if that succeeds. Render has no pre-deploy
command, and its health check (`/api/v1/health`) never touches the database. `/api/v1/ready` compares Neon's
Alembic version with the image's head.

**Rules once Neon is at 0003:**

- Never deploy a commit that lacks `0003`. That includes Render's *Rollback* to any deploy before the v5.2.5
  release (e.g. `e294fec`). Such an image fails at start with "Can't locate revision identified by '0003'", and
  the old instance it replaces dies at its next restart, which on the free plan happens after 15 idle minutes.
  `tests/test_migrations.py::test_no_applied_migration_is_ever_dropped` keeps the file from being removed.
- Never downgrade 0003. Dropping the table destroys the execution claims, which are the run-once evidence.

**Rollback target:** commit `4193a94a7a3ca6443e2a8be48db72c8656c53ac7` (local branch
`rollback/v5.2.4-plus-0003`). It is `51ef984` (the verified v5.2.4 code) plus only the 0003 migration file, so
its head is 0003, its `alembic upgrade head` is a no-op and `/ready` passes. This was verified on a disposable
PostgreSQL 17 with a claim present: `/ready` returned 200 and the claim was intact. Its model-vs-migration drift
test fails by design, because `models.py` is v5.2.4's. Use it only to restore the API.

**Procedure if the v5.2.5 release must be rolled back:**

1. Push the rollback target to `main` as a new commit, e.g. `git revert` of the release commit's application
   changes, keeping `backend/alembic/versions/0003_benchmark_execution_claims.py`. Render deploys commits on
   `main`.
2. In Render, run *Manual Deploy* of that exact commit and watch the log: `alembic upgrade head` must be a no-op,
   then uvicorn starts.
3. Verify `/api/v1/health` (200, mock only) and `/api/v1/ready` (200, `migrations: ok`).
4. Then fix forward. The claims and all other data stay untouched; a Neon branch restore is a last resort and
   discards everything written after the checkpoint.

## Demo vs live

With only the mock provider, the deployment is a **demo**: the dashboard shows the *DEMO — simulated responses* banner,
and every response and record is marked `simulated`. To make it a live gateway, set `GROQ_API_KEY`, `GROQ_ENABLED=true`
(and `GROQ_BILLING_PLAN=free` if the key is on Groq's Free plan) in Render, redeploy, and verify one real request.
The banner then disappears automatically, because `/health` reports `simulated_only: false`.

## Cold starts

The first request after 15 idle minutes waits about a minute while Render wakes the instance. Neon may also be waking
its compute (the first `/ready` locally took ~2.7 s). Latency measured on the hosted demo is not representative of the
gateway itself.
