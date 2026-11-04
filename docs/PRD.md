# Product Requirements — RouteWise AI

## Problem

Teams calling LLMs usually hard-code one model per feature. Either they pay premium prices for easy requests, or they
use a cheap model and get poor answers on hard ones. They also rarely know what each tenant or feature costs, and can't
explain why a request went where it did. The spec card's framing: *one endpoint; cheap model by default, premium only
when the task needs it*, with FinOps-grade accounting and a baseline-vs-routed experiment as proof.

## Users

| Persona | Need |
|---|---|
| **SaaS product team** (demo tenant `acme-saas`) | One API for many models; per-tenant budgets and rate limits; an explanation for every routing decision |
| **Document-pipeline operator** (demo tenant `docflow`) | Cheap, reliable extraction and summarisation at volume, with fallbacks when a provider fails |
| **Platform admin** | Dashboard for traffic, cost (actual vs estimated), latency, failures; key and budget management |
| **Reviewer / hiring manager** | Evidence: a reproducible benchmark, documented trade-offs, honest limitations |

## Goals (in scope)

1. `POST /api/v1/generate`: task type, priority, max cost, latency target; tenant from the API key.
2. Deterministic, explainable routing across small/medium/premium tiers, with no LLM call to route.
3. Timeouts, bounded retries with backoff, provider fallback, circuit breakers; never a paid model.
4. Multi-tenancy: hashed API keys, isolation, rate limits, daily/monthly budgets with atomic reservations.
5. Accounting that separates actual charges from estimated list-price cost, and reported, free-tier and unknown.
6. A 45-case benchmark comparing an all-premium baseline with routing, against pre-registered thresholds.
7. An eight-page dashboard connected to the API, usable on mobile.
8. Free-tier deployment.

## Non-goals (v1)

Streaming; response caching (rejected; see TENANCY_AND_SECURITY.md); an LLM or learned router; paid providers; user
accounts beyond one administrator; prompt management; content moderation.

## Success criteria

The spec card's checklist (S2): deployed or one-command run; three numbers (quality, p95, cost per task) from a real run;
trade-offs explained; a 30–50 case dataset reviewed by the owner; five observed failure modes; a comparison with
reference repositories. Status per item: [REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md).

## Constraints

No billing, purchases or paid usage. No fabricated metrics. Mock output always labelled. No secrets in the repo, logs or
browser. Free hosting only.
