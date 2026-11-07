# Demo guide: RouteWise AI in 5–7 minutes

A scripted live demonstration for interviews and recruiter calls. It uses only the deployed demo, which is
**mock-only**, so it never depends on a live Groq request. Every expected value below was checked against the
code: the example requests were dry-run through the real app with the mock provider.

Links:
- dashboard: https://routewise-dashboard.vercel.app
- API: https://routewise-api-ggjk.onrender.com

## Before the call (10 minutes ahead)

1. **Wake the API.** The free Render instance sleeps after 15 idle minutes and takes about a minute to wake. Open
   https://routewise-api-ggjk.onrender.com/api/v1/ready and wait for `{"status":"ready",...}`.
2. **Sign in to the dashboard** with your production `ADMIN_TOKEN`. It's in your local file
   `%USERPROFILE%\.routewise-production-secrets.env`. Never show that file or paste the token on screen.
3. **Issue a key for this demonstration.**

   > **This writes to production Neon.** Creating a tenant adds rows to `tenants` and `tenant_budgets`; creating a
   > key adds a row to `api_keys`; every demo request adds rows to `request_logs` and `request_attempts`, which
   > then appear in the dashboard's totals. They are mock-provider rows marked `simulated`. Nothing here touches the
   > benchmark tables.

   - **Already done (2026-11-07):** the dedicated tenant `interview-demo` now exists in production; skip this.
     For reference, it was created once like this: *Tenants & Budgets* → a dedicated tenant `interview-demo` (name
     "Interview demo"), for example with a daily budget of 1.00. **Reuse it for every later demo.** Creating the
     same slug again is refused (`409 CONFLICT`), and creating a new tenant each time would clutter production.
   - **Every demo:** on the `interview-demo` card, click **Create key** to issue a fresh key just for this session.
     The plaintext key is shown **once**; copy it into PowerShell (step 4), never into a file, chat or screenshot.
     Don't reuse a key from an earlier demo.
4. **Prepare PowerShell** (keep this window off-screen while you paste the key):

   ```powershell
   $api = "https://routewise-api-ggjk.onrender.com/api/v1"
   $key = Read-Host "Paste the demo API key"          # stays in memory only
   $h   = @{ Authorization = "Bearer $key" }
   function Ask($body) { Invoke-RestMethod "$api/generate" -Method Post -Headers $h -ContentType application/json -Body ($body | ConvertTo-Json -Depth 5) }
   ```

5. Open the browser tabs in this order: the dashboard (*Overview*), the GitHub repository, and
   [`docs/BENCHMARK_RESULTS.md`](BENCHMARK_RESULTS.md) on GitHub.

**After the call:**
1. In *Tenants & Budgets*, revoke the key you issued for this session. The `interview-demo` tenant stays for next
   time.
2. Close the PowerShell window, or run `Remove-Variable key, h`, so the key isn't left in memory or history.

Revoked keys stay listed (status *revoked*) as an audit trail; that's expected.

## The script

| # | Time | Screen | Action | Point out | Say |
|---|---|---|---|---|---|
| 1 | 0:00–0:30 | GitHub README | Scroll past the title and the "production is mock-only" note | Live links, status table | "RouteWise is an LLM gateway project I designed and built: FastAPI backend, React dashboard, Neon PostgreSQL, deployed on Render and Vercel, with a GitHub Actions pipeline that runs the tests against a real PostgreSQL on every push." |
| 2 | 0:30–1:00 | README → *The problem* | — | Overpaying vs under-serving | "If every request goes to the biggest model you overpay; if everything goes to a small one, hard tasks fail. A gateway decides per request, enforces budgets, and explains every decision." |
| 3 | 1:00–1:30 | Dashboard → *Overview* | Point at the banner and KPIs | **DEMO — simulated responses** banner; request counts; actual charges vs estimated list cost | "Production runs a mock provider on purpose, so public traffic can't use the free Groq quota my benchmark needed. The UI labels that honestly: actual charges and estimated list-price cost are separate numbers." |
| 4 | 1:30–2:30 | PowerShell | Run the **simple** request (below) | `model: mock-small`, `routing.score` ≈ 5, `required_tier: small`, `reason_codes` | "A short classification task scores about 5 out of 100, so it needs only the small tier and goes to the cheapest eligible model. The response says why: low complexity, cheapest eligible." |
| 5 | 2:30–3:15 | PowerShell | Run the **complex** request, then the **high-quality** request | Complex: score ≈ 68 → `premium` → `mock-premium`. High quality: score ≈ 25 but `HIGH_STAKES` forces premium | "Multi-step reasoning crosses the premium threshold. And a caller can mark a request high-stakes: the score is low, but the policy forces premium. Same rules, different outcome, all explained." |
| 6 | 3:15–3:45 | Dashboard → *Routing Decisions*, then open one request in *Request Logs* | Click the request you just sent | Reason codes, score contributions, the candidates table ("Eligible / excluded because"; the disabled Groq and OpenRouter models show `PROVIDER_DISABLED`), and the attempts | "Every decision is stored. Here you can see every model that was *not* chosen and why, plus the fallback chain the executor would use if the first model failed." |
| 7 | 3:45–4:30 | GitHub → `backend/app/` | Open `routing/engine.py`, then `services/executor.py` (just the top docstring) | Thin API layer; pure router; executor rules | "The router is a pure function: no I/O, same input, same decision, so it's easy to test. The executor handles timeouts, one retry with jittered backoff, circuit breakers and fallbacks. Budgets are reserved atomically in PostgreSQL before any provider call." |
| 8 | 4:30–5:30 | `docs/BENCHMARK_RESULTS.md` (not the dashboard *Evaluation* page until its fix is deployed) | Show the day-by-day table | Day 1: 9/10 vs 10/10; Day 3: 33/33 combinations, 25/25 checks; "exploratory" labels | "The benchmark ran against real Groq models under a four-day protocol registered before Day 1. Day 1, routing lost one case, so the quality rule failed that day. Day 2 was interrupted by a database timeout; it stays recorded as an incident instead of being hidden, and a separate recovery later accounted for all 36 of its combinations. Day 3 ran cleanly with 25 independent checks. But those later days were registered after I'd seen earlier results, so they're exploratory, and Day 4 wasn't run. I don't claim routing is proven better." |
| 9 | 5:30–6:15 | `docs/PROJECT_OVERVIEW.md` → *Atomic benchmark execution claims* diagram | — | Unique constraint; concurrent claimants → exactly 1 winner (tests race 4 claims; a stress check raced 20) | "After the incident, a database-level guarantee was added: a benchmark day takes a claim row with a unique constraint before any provider call, so it can never run twice, even with two processes racing. If the database is uncertain, it refuses." |
| 10 | 6:15–7:00 | README → *Limitations* | — | Mock-only production; heuristic routing; in-memory health | "Limitations: production is a demo, the router is a keyword heuristic, and health state is per process. Next steps would be shared state for scaling, streaming, and a fresh prospective benchmark with more cases. Happy to go deeper on any part." |

### Requests for steps 4–5

```powershell
$id = [guid]::NewGuid().ToString()   # unique across every demo, so requests never collide (a repeat returns 409)

# Step 4: simple
$r = Ask @{ prompt = "Classify the sentiment of this review as positive or negative: The battery lasts all day and the screen is gorgeous."; task_type = "classification"; request_id = "demo-simple-$id" }
$r | Select-Object provider, model, tier, simulated, latency_ms
$r.routing | Select-Object score, computed_tier, required_tier, reason_codes, explanation

# Step 5: complex
$r = Ask @{ prompt = "Step 1: compare a monolith and microservices for a 5-person startup. Step 2: analyse the trade-offs in cost, latency and team skills. Step 3: justify a recommendation and explain why the alternatives fail."; task_type = "reasoning"; max_output_tokens = 800; request_id = "demo-complex-$id" }
$r.routing | Select-Object score, required_tier, reason_codes
$r.model

# Step 5: high quality (low score, forced premium)
$r = Ask @{ prompt = "Summarise this in one sentence: RouteWise routes LLM requests by cost and capability."; task_type = "summarization"; quality = "high"; request_id = "demo-hq-$id" }
$r.routing | Select-Object score, computed_tier, required_tier, reason_codes
```

**Expected values** (dry-run with the production configuration: mock provider only, policy `rw-2026.11-v1`). On
production the `interview-demo` tenant has a daily budget, so `PRICE_UNKNOWN` is also listed: models with no
published price are excluded under a budget. The live request on 2026-11-07 returned exactly that for the complex
prompt: score 68.16, `mock/mock-premium`, `HIGH_COMPLEXITY`, `PRICE_UNKNOWN`, `CHEAPEST_ELIGIBLE`, `SIMULATED_PROVIDER`.

| Request | Score | Computed → required tier | Model | Reason codes |
|---|---|---|---|---|
| Simple | 5.09 | small → small | `mock/mock-small` | `LOW_COMPLEXITY`, `CHEAPEST_ELIGIBLE`, `SIMULATED_PROVIDER` |
| Complex | 68.16 | premium → premium | `mock/mock-premium` | `HIGH_COMPLEXITY`, `CHEAPEST_ELIGIBLE`, `SIMULATED_PROVIDER` |
| High quality | 25.07 | small → **premium** | `mock/mock-premium` | `LOW_COMPLEXITY`, `HIGH_STAKES`, `CHEAPEST_ELIGIBLE`, `SIMULATED_PROVIDER` |

The `content` of each response starts with `[SIMULATED] Response from mock-…`. Say so plainly if asked: it's a
placeholder, not a model answer.

**Optional extras** (if there's time):
- Re-send the same `request_id` → `409 DUPLICATE_REQUEST_ID` (idempotency).
- Send a request with a made-up key → `401 UNAUTHORIZED`.
- Open https://routewise-api-ggjk.onrender.com/api/v1/health → `"simulated_only": true`.

## What to say for each area (short versions)

- **Backend:** "FastAPI, fully async. The HTTP layer only validates; a service layer orchestrates auth, rate
  limiting, routing, budget reservation, execution and persistence. One factory builds the pipeline for both the
  API and the benchmark."
- **Database:** "Neon PostgreSQL with Alembic migrations. One row per request and one per provider attempt. Budgets
  use a conditional `UPDATE`, so concurrent requests can't overspend: tested with 25 concurrent requests against a
  limit that fits 10, and exactly 10 succeed."
- **Evaluation:** "45 cases with deterministic scorers, three strategies interleaved, thresholds pre-registered and
  the code pinned by hashes, so I can't tune after seeing results."
- **Deployment:** "Docker on Render, the dashboard on Vercel, CI on GitHub Actions with a real PostgreSQL service.
  The container migrates the schema before starting, and I deploy manually after CI passes."
- **Security:** "API keys are stored only as HMAC hashes, the tenant always comes from the key, and admin access
  uses short-lived sessions with login throttling. No secrets in code or in frontend variables; CI scans for them."

## Pitfalls to avoid

- **Don't** say the live site calls Groq or real models. It is mock-only.
- **Don't** say routing "saves 30%" or "is proven non-inferior". The confirmatory experiment is incomplete; quote
  only exploratory figures, with that word.
- **The dashboard *Evaluation* page:** it shows a green *publishable* badge on the `v5.2.3-day1` and
  `v5.2.4-day2-recovery-run` groups. That badge comes from per-run summaries and is misleading: no day is a
  publishable confirmatory result. If you show the page, say so, or show
  [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) instead (see [KNOWN_ISSUES.md](KNOWN_ISSUES.md)). The page header
  also still says the dataset is "pending human review", which is out of date.
- **If the API is cold**, the first request can take about a minute. Wake it beforehand.
- **Never** show `.env`, the production secrets file, the Render dashboard's environment page, or a full API key.
