# Requirements Traceability — RouteWise AI

S1 = spec card (screenshot 1), S2 = acceptance checklist (screenshot 2), P = master prompt, C = flagged contradiction.

**Status legend:** **Verified** = automated tests or recorded evidence pass · **Verified (mock)** = tested with the mock
provider or fake transports, not yet against a real provider · **Implemented** = built, not fully verified ·
**Blocked** = needs your action · **N/A** = not applicable (reason given).

Last updated: 2026-11-07 (deployed; all four benchmark days run once under four registrations; the original four-day confirmatory experiment remains incomplete). Earlier rows keep their original evidence.

## Screenshot 1 — Project specification

| ID | Requirement | Component | Doc | Verification | Status |
|---|---|---|---|---|---|
| S1-01 | One `/generate` endpoint: task type, tenant, priority, max cost, latency target | `api/v1/generate.py`, `schemas.py`; tenant from key (C-01) | API.md | `tests/api/test_generate.py`, E2E | Verified (mock) |
| S1-02 | Path: auth + rate limit → budget → (cache) → router → tier | `services/gateway.py` | ARCHITECTURE.md | API and tenancy tests | Verified (mock); cache N/A (rejected, documented) |
| S1-03 | Three tiers; complex or high-stakes → premium | `routing/engine.py` | ROUTING_METHODOLOGY.md | `test_engine.py` | Verified |
| S1-04 | Rules, not an LLM, to route | `routing/` (pure, no I/O) | ROUTING_METHODOLOGY.md | determinism tests | Verified |
| S1-05/06 | Timeout → retry + backoff → fallback → response with model, tokens, cost | `services/executor.py` | PROVIDER_INTEGRATION.md | `test_executor.py`, API tests | Verified (mock) |
| S1-07 | Rate limits and per-tenant budgets | `tenancy/rate_limit.py`, `accounting/budget.py` | TENANCY_AND_SECURITY.md | tenancy, budget and concurrency tests | Verified (SQLite); PostgreSQL concurrency run pending CI |
| S1-08 | Log prompt version, model, tokens, latency, success, cost, fallback | `request_logs`, `request_attempts` | DATABASE_SCHEMA.md | API tests; live Neon checks | Verified (prompt stored as hash only, C-02) |
| S1-09 | Cost dashboard per tenant, per tier | `/admin/usage`, Usage & Cost page | COST_ACCOUNTING.md | Vitest + E2E | Verified (mock data) |
| S1-10 | Routing eval: baseline vs routed | `app/evaluation/`, Evaluation page | EVALUATION.md | evaluation tests, CLI pipeline check | Implemented; **live run Blocked** (no provider keys) |
| S1-11 | SLOs p50/p95 | `accounting/usage.py`, Overview page | OPERATIONS_RUNBOOK.md | usage tests | Verified (mock) |
| S1-12 | All-premium baseline first; threshold set before the experiment | `evaluation/preregistration.yaml`; runner refuses without it | EVALUATION.md | `test_preregistration_exists…` | Verified |
| S1-13 | Metrics: cost per successful task, success vs baseline, p50/p95, fallback rate, rate-limit rejection rate, % traffic per tier | `accounting/usage.py`, `evaluation/report.py` | EVALUATION.md, COST_ACCOUNTING.md | usage and report tests | Verified (mock); real values Blocked |
| S1-14 | 30–50 item benchmark with quality bar and max cost/latency per item | `routewise_bench_v2.jsonl` (45; v1 kept), per-difficulty limits, prereg-v2 | EVALUATION.md, v2 changelog | `test_dataset_v2.py`: 45 reference pairs + adversarial answers | Verified; **owner review Blocked** (C-05) |
| S1-15/16 | Gateway, rules, adapters, telemetry; dashboard, limits, budgets, experiment, deploy, results | Phases 2–7 | implementation_plan.md | this table | Deploy and results Blocked |
| S1-17 | Résumé bullet with real [X]% / [Y]% | from a publishable report only | README.md | — | Blocked: live Days 1–4 ran, but no publishable confirmatory report exists (the original protocol's Day 2 was interrupted; later days are exploratory; see BENCHMARK_RESULTS.md) |
| S1-18 | Reference repositories | README comparison section | README.md | review | Implemented |
| S1-19 | SaaS gateway / document-pipeline framing | demo tenants `acme-saas`, `docflow` | PRD.md | seed tests | Verified |
| S1-20 | FinOps thinking | actual vs estimated, four statuses, shadow budgets | COST_ACCOUNTING.md | cost and budget tests | Verified |

## Screenshot 2 — Acceptance checklist

| ID | Requirement | Status |
|---|---|---|
| S2-01 | Deployed, or one-command local run | **One-command local run: Verified** (`scripts/dev.ps1`; E2E harness). Deployment: **Verified** (2026-11-04: Render + Vercel + Neon, mock only; redeployed 2026-11-06 with migration 0003) |
| S2-02 | Three numbers: quality, p95, cost per task | **Blocked**: needs a live benchmark run. The pipeline that produces them is verified |
| S2-03 | Trade-offs explained | **Verified** (ARCHITECTURE.md, ROUTING_METHODOLOGY.md, TENANCY_AND_SECURITY.md). "Hybrid vs vector" and "human approval" are N/A (C-06) |
| S2-04 | 30–50 labelled examples you wrote, in the repo | 45 AI-drafted cases in the repo; **your review Blocked** (C-05) |
| S2-05 | Five real failure modes | **1 of 5 observed** (retired Groq model → 404, live smoke test); the rest must come from live runs (C-07); the table is in EVALUATION.md |
| S2-06 | What changed from the reference repos | Implemented (README "Comparison with reference repositories", C-08) |

## Master prompt — engineering requirements

| ID | Requirement | Status |
|---|---|---|
| P-01 | Independent adapters, enable via env | Verified (mock). **Groq verified live** (2026-11-04: one success, one 404 on a retired model; PROVIDER_INTEGRATION.md). OpenRouter and Ollama live: not verified |
| P-02 | Registry with provenance and pricing | Verified; synced to Neon |
| P-03 | Bounded retries, backoff, Retry-After, no retry on permanent errors | Verified (mock) |
| P-04 | Circuit breaker | Verified (mock) |
| P-05 | No paid fallback | Verified (config, catalog, router, executor, OpenRouter guard) |
| P-06 | Decision with policy version and reason codes, in API and dashboard | Verified |
| P-07 | Health, ready, models, providers, protected admin | Verified (incl. production mode on Neon) |
| P-08 | Idempotency | Verified (API, DB constraint, E2E) |
| P-09 | Cost statuses, pricing provenance, no double counting | Verified |
| P-10 | Hashed keys, prefixes, isolation, rotation | Verified |
| P-11 | Concurrency-safe budgets | Verified on SQLite (25 parallel → exactly 10); PostgreSQL run pending CI |
| P-12 | Safe cache | N/A: evaluated and rejected (documented) |
| P-13 | No secrets or prompts in logs, DB, errors, browser | Verified (tests + detect-secrets + production log check) |
| P-14 | Failure scenarios: timeout, 429, invalid creds, budget exhausted, all fallbacks fail (+ malformed, breaker, concurrency, duplicate ID) | Verified (mock) |
| P-15 | Evaluation framework vs best-model baseline | Implemented and tested; live run Blocked |
| P-16 | 8-page dashboard, responsive, loading/empty/error | Verified (Vitest + Playwright desktop and mobile) |
| P-17 | CI: lint, types, tests, audits, secret scan, E2E | Implemented; **first run pending push** |
| P-18 | Free-tier deployment, verified | **Verified** (Render free + Vercel Hobby + Neon; 26/26 production checks) |

## Contradictions and limits (flagged)

| ID | Issue | Resolution |
|---|---|---|
| C-01 | Card says the endpoint "accepts tenant ID" | Tenant derived from the API key; a body `tenant_id` is rejected |
| C-02 | Card logs "prompt"; privacy forbids it | `prompt_sha256` + length + client `prompt_version`; content never stored |
| C-03 | "Cut cost 60%" and [X]/[Y] are placeholders; free tier bills $0 | Shadow list-price cost, labelled estimated; numbers only from a publishable report |
| C-04 | 48-hour plan vs full scope | Treated as build order; phased plan |
| C-05 | "Examples you wrote yourself"; cases are AI-drafted | Marked `draft-pending-human-review`; reports not publishable until you review every case |
| C-06 | Checklist trade-off examples belong to other projects | N/A; replaced with this project's trade-offs |
| C-07 | Five *observed* failure modes ≠ five tested scenarios | Both. Observed ones need live runs |
| C-08 | "Changes from the reference repo" assumes a fork | README comparison section instead |
| C-09 | Free catalogs and limits change | Registry `verified_on`, startup catalog check, OpenRouter limit read from the account |
| C-10 | 45 cases, low power | Wilson and bootstrap CIs; non-inferiority must be CI-supported |
| C-11 | "Premium" = best free model, not frontier | Stated in EVALUATION.md limitations |
| C-12 | Hosted backend can't reach local Ollama | Ollama refused in production |
| C-13 | Streaming not required | Non-streaming v1, documented |
| C-14 | Rate limits without Redis | DB fixed-window upsert |
