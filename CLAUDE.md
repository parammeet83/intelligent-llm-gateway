# CLAUDE.md — RouteWise AI (intelligent-llm-gateway)

Cost-aware, explainable LLM gateway with tenant auth, shadow budgets, a pre-registered benchmark and an 8-page dashboard.
Plan: `implementation_plan.md`. Progress: `TASKS.md`. Requirement IDs: `docs/REQUIREMENTS_TRACEABILITY.md`.

## Hard rules
- No paid APIs, no billing, no account creation for the user. `ALLOW_PAID_MODELS` stays `false`.
- Never fabricate prices, limits, latency, quality, savings, or benchmark results. Unverified values say so.
- Mock output is always labelled `simulated` and never reported as a result. Benchmark reports are publishable only
  from non-simulated runs on a fully human-reviewed dataset.
- No secrets in code, logs, docs, or frontend env vars. `.env` stays git-ignored. Update `.secrets.baseline` only after
  reviewing each new finding.
- **Never commit, push, amend, or rewrite history unless the user explicitly asks.** No Claude co-author trailers.
- Never drop, truncate or reset the Neon database. Destructive tests run only on `TEST_DATABASE_URL` (disposable).
- Shell instructions given to the user must be Windows PowerShell-compatible.

## Layout
- `backend/` — FastAPI (`app/`): `routing/` (pure), `providers/`, `resilience/`, `services/` (gateway, executor,
  factory), `accounting/` (cost, budget, usage), `auth/`, `tenancy/`, `evaluation/`, `api/v1/`. Alembic, tests. `uv`.
- `frontend/` — Vite + React + TS + Tailwind + Recharts; `e2e/` Playwright (throwaway backend).
- `evaluation/` — dataset (+ provenance meta), pre-registration, reports (git-ignored except `published/`).
- `docs/` — design and operations docs.

## Conventions
- Routing is pure and deterministic; any change to `routing_policy.yaml` bumps `version` (seed refuses otherwise).
- API handlers hold no business logic; build the pipeline only via `services/factory.build_gateway`.
- Unknown cost is `None`, never 0. Actual charges and estimated list cost are never summed together.
- Automated tests never call real providers (mock provider or `httpx.MockTransport`).
- Run before finishing: backend `ruff check`, `ruff format --check`, `mypy app tests`, `pytest`; frontend `lint`,
  `typecheck`, `test`, `build`, `test:e2e`.
