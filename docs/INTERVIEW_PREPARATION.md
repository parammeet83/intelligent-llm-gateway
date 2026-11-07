# Interview preparation: RouteWise AI

Answers are written to be spoken: about 4–6 lines each, technically accurate, and checked against the code. Where
a number is quoted, its source is in [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) or
[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).

**Three rules for every answer:**
1. Production is **mock-only**. Real Groq calls happened only in the benchmark.
2. The benchmark is **incomplete and exploratory**. Never say routing is "proven" better.
3. If you don't know something, say what you'd check and where in the code.

## 60-second introduction

"RouteWise AI is an LLM gateway: one API that sits in front of several model providers and decides, per request,
which model should answer. It scores how complex the request is with transparent rules, picks the cheapest model
that's capable enough, and records an explanation of every decision. Around that it adds what a real gateway
needs: API keys per tenant, rate limits, atomic budget reservations, retries, fallbacks and circuit breakers. It
uses FastAPI and async SQLAlchemy on Neon PostgreSQL, plus a React dashboard, deployed on Render and Vercel, with
a GitHub Actions pipeline that runs the tests against a real PostgreSQL. I also ran a benchmark against real Groq
models, under a four-day protocol registered before the first day. The honest result: routing used the small
model on about half to two-thirds of requests and lost one case on Day 1. The four-day plan is incomplete, and the
later days ran under registrations written after earlier results, so those are exploratory."

## Two-minute explanation

"The problem is that applications often hard-code one model. Sending everything to the biggest model wastes
money; sending everything to a small one fails hard tasks.

RouteWise exposes `POST /api/v1/generate`. A request goes through these steps:
- It's authenticated by an API key that's stored only as an HMAC hash.
- It's rate-limited per tenant with an atomic database counter.
- It passes to a pure routing function. That function extracts features like length, JSON output, code blocks
  and reasoning words, turns them into a 0–100 complexity score, and maps the score to a small, medium or premium
  tier.
- The router checks every model, recording all the reasons a model is excluded, and ranks the eligible ones by
  worst-case cost.
- The gateway reserves the worst-case cost against the tenant's budget with a conditional SQL update, so
  concurrent requests can't overspend.
- An executor calls the provider with timeouts, one jittered retry for transient errors, fallbacks to the next
  model, circuit breakers and an overall deadline.
- Afterwards it settles the cost, keeping actual charges separate from estimated list price, and stores one row
  per request and one per provider attempt.

The React dashboard shows traffic, costs, routing decisions and benchmark runs.

For evaluation there's a 45-case benchmark with deterministic scorers. The original four-day protocol, v5.2.3,
fixed the thresholds and pinned the code by hashes **before Day 1**; that part was prospective. Day 1 ran
cleanly, but routing failed one case, so the quality rule didn't hold. Day 2 was interrupted by a database
timeout, and under that protocol it stays an incident record. The system was then hardened:
- database retries
- idempotent writes
- an atomic claim table, so a benchmark day can never start twice

A separate recovery registration later accounted for all 36 Day 2 combinations. Day 3 ran 33 out of 33 and
passed 25 independent reconciliation checks. Both of those registrations were written after I'd seen earlier
results, so they are exploratory, not proof."

## 1. Project overview

**Q1. What is RouteWise in one sentence?**
A cost-aware LLM gateway: one API that picks a capable but cheap model for each request, enforces tenant budgets
and rate limits, handles provider failures, and explains every routing decision. It has a React dashboard and a
pre-registered benchmark that tests whether routing actually saves cost without losing quality.

**Q2. What did you personally build?**

> Be exact here; interviewers probe this. This repository was developed with an AI coding assistant (Claude Code;
> see [`CLAUDE.md`](../CLAUDE.md)). Say so, then describe what you directly owned. Adjust the answer to your real
> contribution, and never claim you hand-wrote code you didn't.

"It's my project: I defined what it should do, made the design decisions, and built it with an AI coding
assistant, Claude Code, which generated much of the implementation under my direction. My own work was:
- setting the requirements and constraints, like no paid APIs and a mock-only production
- approving each step
- the human review of the 45 benchmark cases
- running the deployments and the benchmark days, including supplying the quota readings
- deciding to record the Day 2 failure as an incident instead of re-running it

I've read through the code, and I can walk through any module and explain why it works the way it does."

**Q3. What is the current state of the project?**
- **Deployed and working:** Render for the API, Vercel for the dashboard, Neon for the database.
- **CI:** runs on every push to `main`. The latest verified run, 42168398327 on commit `61984cd`, passed all four
  jobs.
- **Production is mock-only:** responses are simulated, so public traffic can't use the free Groq quota.
- **Benchmark:** all four scheduled days have been run once, but under four registrations; the original
  four-day confirmatory experiment is incomplete.

## 2. Why an LLM gateway?

**Q4. Why not just call the model API directly from the application?**
You can, but each application then has to solve the same problems on its own: choosing models, handling rate
limits and outages, tracking cost per customer, and enforcing budgets. A gateway does this once, consistently, and
keeps an audit trail. It also lets you change models or providers without touching application code.

**Q5. How does routing save money?**
Most requests are simple: classification, extraction, short answers. A small model handles them at a fraction of
a large model's price. RouteWise sends those to the small tier and reserves the premium model for requests that
score as complex or are marked high-quality. In the benchmark, routing sent 50–70% of requests to the small
model; on Day 3 its estimated cost per accepted answer was about 0.71–0.73 times the baseline's. That's an
exploratory figure.

## 3. FastAPI and backend architecture

**Q6. Why FastAPI, and why async?**
The gateway spends most of its time waiting on network calls to providers and the database. With async, one
process can handle many requests while they wait, instead of blocking a thread each. FastAPI gives typed request
validation with Pydantic, automatic error handling, and dependency injection for authentication.

**Q7. How is the backend structured?**
In layers:
- **API routes (`api/v1`)** only validate input and call services; there's no business logic there.
- **The gateway service** orchestrates the request.
- **The routing engine** is a pure function.
- **The executor** handles provider calls.
- **Accounting** handles cost and budgets.

One factory, `build_gateway`, wires all of it, and both the API and the benchmark use it. So the benchmark tests
the real pipeline.

**Q8. How do you handle errors consistently?**
- **One envelope:** every error returns the same JSON shape: `error` with a code, message, request ID and
  details.
- **Clear status codes:** 401 bad key, 402 budget exhausted, 409 duplicate request ID, 422 no eligible model,
  429 rate limited, 502 when every provider failed.
- **No leaks:** validation errors never echo the submitted input, and logs redact anything that looks like a
  credential.

## 4. React frontend

**Q9. What does the dashboard do?**
Eight pages: Overview, Routing Decisions, Providers & Models, Tenants & Budgets, Usage & Cost, Request Logs,
Evaluation and Settings. An admin can create tenants and keys, look at the full decision record of any request,
see cost and latency charts, and review benchmark runs. It's React 19 with TypeScript, Vite, Tailwind and
Recharts, and pages are lazy-loaded.

**Q10. How does the dashboard authenticate, and why not store the admin token?**
The admin types the token once. The app exchanges it for a short-lived session token through
`/admin/session`, which is throttled to five attempts a minute. Only the session token is kept, so a leaked
browser state doesn't expose the long-lived secret. The frontend's only configuration is the public API base URL;
no secret ever goes into a `VITE_` variable.

**Q11. How did you test the frontend?**
- **Vitest component tests (28):** sign-in, session expiry, every page's data, empty and error states, and that
  unknown costs never display as $0.
- **Playwright end-to-end tests:** start a real backend on a throwaway database, create a key, send a request
  and check it appears in the dashboard, on desktop and mobile.

## 5. PostgreSQL and database design

**Q12. Walk me through the main tables.**
- **Tenancy:** tenants, API keys stored as hashes, budget periods with limit, spent and reserved, and rate-limit
  windows.
- **Traffic:** `request_logs` holds one row per request with the full decision as JSON; `request_attempts` holds
  one row per provider call, so retries and fallbacks are visible.
- **Catalog:** models, append-only price snapshots and versioned routing policies.
- **Benchmark:** cases, runs, results, and the execution-claims table.

That's 13 tables, managed by Alembic.

**Q13. How do you stop concurrent requests from overspending a budget?**
The reservation is a single conditional `UPDATE`: add the amount to `reserved` only where `spent + reserved +
amount` is still within the limit. PostgreSQL locks the row and re-checks that condition against the latest
committed value, so concurrent requests serialise on it. A test runs this on real PostgreSQL in CI: 25 concurrent
reservations against a budget that fits 10, and exactly 10 succeed.

**Q14. How does idempotency work?**
`request_logs` has a unique constraint on tenant plus client request ID. If a client retries with the same ID,
the insert fails and the API returns 409 instead of calling the model twice. The design deliberately doesn't replay the original
response, because that would require storing response content, and the privacy default is not to store prompts
or responses.

## 6. LLM integration and provider abstraction

**Q15. How do you support multiple providers?**
Every provider implements one interface: take a normalised request, return a normalised response or a typed
error. There are adapters for Groq, OpenRouter, Ollama and a mock. Errors are classified once, as retryable or
fallback-eligible, so the executor doesn't need provider-specific logic. Adding a provider means writing one
adapter and adding its models to `models.yaml`.

**Q16. Which providers actually work live?**
- **Groq:** worked live; about a hundred real requests ran through the gateway pipeline in the benchmark.
- **OpenRouter and Ollama:** tested only with fake HTTP transports.
- **Production:** uses only the mock provider, which is deterministic and marks every response as simulated.

I'm careful to say that distinction explicitly.

**Q17. How do you guarantee you never use a paid model?**
It's enforced in four places:
1. startup refuses `ALLOW_PAID_MODELS=true` and any enabled paid model
2. the router excludes paid models
3. the executor re-checks before each call
4. the OpenRouter adapter only allows `:free` model IDs

## 7. Routing strategies

**Q18. How does the router decide?**
It extracts features (estimated tokens, output length, JSON, code blocks, multi-step markers, reasoning and math
words) and adds them to a task-type prior to get a score from 0 to 100. Below 35 is small, below 65 medium,
otherwise premium. `quality: high` forces premium. Then it checks every model against tier, capability, context,
health, budget and latency, and ranks the eligible ones.

**Q19. What's the difference between your two routing strategies?**
- **`cheapest_capable`** ranks eligible models by worst-case cost, so the tier is only a floor: a bigger model
  can win if it's cheaper.
- **`lowest_tier_first`** prefers the required tier first.

In the benchmark, with only two Groq models, both strategies picked the same model every time. So the data can't
tell them apart, and I say that openly.

**Q20. Why rules instead of using an LLM to route?**
- **Cost and latency:** rules add almost no latency and no cost. An LLM router would add a model call to every
  request.
- **Testability:** rules are deterministic, so they're easy to test.
- **Explainability:** every point in the score can be explained.
- **The trade-off:** keywords miss semantic difficulty and can be gamed. The benchmark showed exactly that risk:
  on Day 1 the router sent a case to the small model and it failed.

## 8. Evaluation and benchmarking

**Q21. How did you design the benchmark?**
- **Cases:** 45, each with a deterministic scorer.
- **Strategies:** three, interleaved: always premium, and the two routing strategies.
- **Pre-registration:** the original four-day protocol, v5.2.3, was registered **before Day 1**. It fixed the
  thresholds (within 5 percentage points of the baseline, supported by a bootstrap confidence interval) and pinned
  the code, configuration and dataset by SHA-256 hashes. If the code changes, a registration refuses to run.
- **Later registrations:** the Day 2 recovery (v5.2.4) and Day 3 (v5.2.5) were registered after incidents and
  after earlier results were known, so they are exploratory, not prospective.
- **Statistics:** Wilson intervals per strategy and a paired bootstrap for the difference.

**Q22. What were the results?**
- **Day 1:** the baseline passed 10/10 and both routing strategies 9/10, so the pre-registered quality rule did
  not hold.
- **Day 2:** the original run was interrupted by a Neon timeout after 11 of 36 combinations and remains an
  incident record. A separate, disclosed recovery registration later accounted for all 36 combinations, 12/12
  for everyone.
- **Day 3:** 33/33 combinations, all 11/11, with 25 of 25 independent reconciliation checks passing.
- **Day 4:** 36/36 combinations under its own registration, 27 of 27 checks. The baseline passed 12/12 and routing
  11/12 (case T04 on the small model), so the quality rule did not hold again.

The recovery, Day 3 and Day 4 registrations were all made after seeing earlier data, and the original protocol's
Day 2 stays an incident. So these are exploratory results, not a confirmatory finding.

**Q23. Why do you call Day 3 "exploratory" if it passed everything?**
Because the Day 3 registration was written after Days 1 and 2 had been run and observed. A confirmatory test has to
be fixed before you see any data; otherwise you could, consciously or not, shape it around what you saw. Also,
11 cases is a small sample: 11 out of 11 still has a confidence interval down to 74%.

## 9. Reliability and error handling

**Q24. What happens when a provider fails mid-request?**
- **Timeout or 5xx:** the executor retries the same model once, with jittered exponential backoff.
- **Rate limit, auth error or missing model:** it moves to the next model in the fallback chain. That chain is
  the router's own ranked list, so fallbacks obey the same budget and tier rules.
- **Repeated failures:** these open a circuit breaker for that model.
- **Deadline:** an overall deadline of 60 seconds by default caps the whole request.

**Q25. Tell me about the Day 2 incident.**
- **What happened:** during Day 2, a Neon database timeout stopped the run after 11 of 36 combinations, and the
  attempt to mark the runs finished timed out too.
- **How I recorded it:** the protocol says a stopped day is never restarted, so I recorded it as an incident.
- **What I fixed:** bounded database retries, idempotent writes, verified finalisation, and a rule that a
  combination is retried only if the quota ledger proves no provider request was sent.
- **The recovery:** I ran it under a separate, openly post-hoc registration.

**Q26. How do you make sure a benchmark day can't run twice?**
- **The guarantee:** a table with a unique constraint on revision plus day number. Before creating runs or
  calling any provider, the runner inserts a claim. If processes race, the database lets exactly one insert
  succeed. The automated tests race several claims and runner starts on PostgreSQL in CI, and a one-off stress
  check with 20 simultaneous claimants also produced exactly one winner.
- **Fail closed:** if the database is unreachable or the table is missing, it refuses to start.

## 10. Deployment

**Q27. How is it deployed?**
- **API:** a Docker container on Render's free tier. On start it runs `alembic upgrade head` and only then starts
  uvicorn.
- **Dashboard:** a static React build on Vercel.
- **Database:** Neon PostgreSQL.
- **CI:** GitHub Actions runs lint, type checks, tests against a real PostgreSQL 17 service, Playwright and a
  secret scan.

Auto-deploy is off, so deploys are manual. The migration `0003` release, for example, went out only after CI
passed on that exact commit (run 42161021885).

**Q28. What did you learn about migrations and rollbacks?**
After migration `0003`, rolling back to the old image is impossible, because that image doesn't know revision
`0003` and Alembic refuses to start. That was tested on a disposable PostgreSQL before deploying. So a rollback
commit was prepared, the previous code plus only the new migration file, and a Neon branch was created as a
checkpoint before migrating.

## 11. Security

**Q29. How do you secure tenants and secrets?**
- **Keys:** API keys are random and stored only as HMAC-SHA256 hashes with a server-side pepper.
- **Tenant identity:** always comes from the key, never from the request body; unknown fields are rejected.
  Another tenant's request ID returns 404.
- **Production checks:** startup refuses weak secrets or SQLite, `/docs` is hidden, and CORS only allows the
  dashboard.
- **No content at rest:** prompts aren't stored, only a hash and length.
- **CI:** scans for secrets against a reviewed baseline.

## 12. Limitations and future scope

**Q30. What are the main limitations, and what would you do next?**
**Limitations:**
- Production is a demo with simulated responses.
- The router is a keyword heuristic.
- Provider health is kept in memory per process, so it doesn't scale to several instances.
- The benchmark is small and incomplete.

**Next steps:**
- shared state like Redis for health and rate limits
- streaming responses
- a better complexity estimator validated on the benchmark
- a fresh, fully prospective benchmark with more cases and more model families

## Quick facts to memorise

| Fact | Value |
|---|---|
| Stack | FastAPI, async SQLAlchemy, Alembic, Neon PostgreSQL 17, React 19 + TypeScript, Render, Vercel, GitHub Actions |
| Tables / migration head | 13 / `0003` |
| Routing thresholds | < 35 small, < 65 medium, else premium; policy `rw-2026.11-v1` |
| Reliability defaults | 30 s provider timeout, 60 s request deadline, 1 retry, breaker at 3 failures for 30 s |
| Tests | Backend 1,689 passed in CI (e.g. run 42330582354 on `60a3740`, with the Day 4 tests added); 29 Vitest; 9 Playwright |
| Benchmark | Original v5.2.3 protocol registered before Day 1. Day 1 30/30 (routing 9/10 vs 10/10). Day 2 interrupted (incident record); separate v5.2.4 recovery accounted for all 36. Day 3 (v5.2.5) 33/33, 25/25 checks. Day 4 (v5.2.6) 36/36, 27/27 checks. Recovery, Day 3 and Day 4 are exploratory |
| Groq usage | 135 attempts, 43,328 tokens over four days, $0 actual charge |
| Day 4 | v5.2.6 (exploratory): 36/36, 27/27 checks; baseline 12/12, routing 11/12 (T04 failed on the small model), so the quality rule did not hold |
