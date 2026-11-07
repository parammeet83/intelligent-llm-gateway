# Benchmark results

**Bottom line:** all four scheduled days have now been run once against real Groq models, but under four
separate registrations.
- Day 1 completed (v5.2.3). Routing lost one case and its pre-registered rules did not hold.
- Day 2 (v5.2.3) was interrupted and remains an incident record. A separate, disclosed v5.2.4 recovery later
  accounted for all 36 Day 2 combinations.
- Day 3 completed cleanly and was independently reconciled (v5.2.5).
- Day 4 completed and was independently reconciled (v5.2.6). Routing lost one case and its pre-registered rules
  did not hold.

The original four-day confirmatory experiment is still **incomplete**: its own Day 2 was interrupted, and the
recovery, Day 3 and Day 4 registrations are post-incident and exploratory. No confirmatory claim is made that
routing is better, non-inferior or cheaper. Figures below are descriptive or exploratory.

Sources (the numbers here are copied or computed from these files):
- reports in `evaluation/reports/` (local and git-ignored; their SHA-256 hashes are recorded in the changelogs)
- the registrations in [`evaluation/`](../evaluation/)
- the changelogs in [`evaluation/datasets/`](../evaluation/datasets/)
- the [Day 3 closure](BENCHMARK_DAY3_CLOSURE_v5.2.5.md) and the [Day 4 closure](BENCHMARK_DAY4_CLOSURE_v5.2.6.md)

Method details: [EVALUATION.md](EVALUATION.md).

## 1. Purpose

Test whether RouteWise routing keeps answer quality while lowering cost, compared with sending every request to
the premium model.
- The **quality** question: is the routed pass rate no more than 5 percentage points below the baseline's?
- The **cost** question: is the estimated list-price cost per accepted answer lower?

Both rules were written and hashed **before Day 1**, in the original four-day protocol `routewise_bench_v5.2.3`
(registered 2026-11-04 18:25:33 UTC; Day 1 started 21:06:23 UTC). That protocol is the prospective part.

The three later registrations reused the same rules but were written **post-incident**, after earlier results had
been observed, so they are **exploratory**:
- `v5.2.4` (Day 2 recovery), registered 2026-11-05 08:56:09 UTC
- `v5.2.5` (Day 3), registered 2026-11-06 03:08:50 UTC
- `v5.2.6` (Day 4), registered 2026-11-07 02:35:15 UTC

## 2. Setup

| Item | Value |
|---|---|
| Dataset | `routewise_bench_v5`: 45 cases (15 simple, 18 standard, 12 complex), deterministic scorers (exact, numeric, JSON, regex, contains, validator); SHA-256 `76a4d1906b3e…` |
| Human review | Owner attestation for all 45 cases (`b7099444ac31…`). Case T17 (Spanish) was checked with Google Translate; no native-speaker validation |
| Strategies | `baseline_premium`: every case forced to the premium tier. `routewise`: policy with `cheapest_capable`. `routewise_tier_first`: same policy with `lowest_tier_first` |
| Models | Groq free tier: `openai/gpt-oss-20b` (small) and `openai/gpt-oss-120b` (premium). Groq has no medium model, so medium-tier requests go to 120B |
| Schedule | The 45 cases split over 4 UTC days (10, 12, 11, 12 cases); each day runs all three strategies interleaved, once |
| Pacing | Concurrency 1, at least 6 s between requests, worst-case token reservation per attempt in a persistent ledger |
| Primary metric | Pass rate, conditional on an answer being returned |
| Quality rule | Non-inferior if within 5 points of the baseline; "supported" only if the paired bootstrap 95% CI's lower bound is above −0.05 |
| Cost rule | Lower cost per accepted answer, **and** CI-supported non-inferiority, no unknown costs, a valid run and a baseline pass rate ≥ 0.60 |
| Statistics | Wilson 95% CI per strategy; paired bootstrap (10,000 resamples, seed 20261104) |

## 3. Results by day

### Day 1: completed (v5.2.3, 2026-11-04, 21:06–21:17 UTC)

Cases: S05 S08 S11 T03 T06 T16 T17 C03 C10 C11 (10 cases × 3 strategies = 30/30 results).

| Strategy | Pass | Wilson 95% CI | p50 / p95 latency | Est. list cost per accepted answer | Models used |
|---|---|---|---|---|---|
| baseline_premium | 10/10 | 72.2%–100% | 2,451 / 3,612 ms | $0.00018002 | 120B ×10 |
| routewise | 9/10 | 59.6%–98.2% | 2,678 / 4,389 ms | $0.00015570 | 20B ×7, 120B ×3 |
| routewise_tier_first | 9/10 | 59.6%–98.2% | 2,568 / 3,571 ms | $0.00016557 | 20B ×7, 120B ×3 |

- Both RouteWise strategies failed **T03**, a standard case that was routed to `gpt-oss-20b`.
- **Pre-registered verdicts:**
  - The pass-rate difference was −0.10 for both strategies (bootstrap CI −0.30 to 0.00).
  - The quality rule **did not hold**, so the cost rule **did not hold** either, even though the cost per
    accepted answer was lower (ratios 0.86 and 0.92).
- **Usage:** 30 provider attempts, 12,223 tokens (120B 9,537; 20B 2,686), no retries or fallbacks, $0 actual
  charge.
- Day 1's numbers come from the runner's report. No separate reconciliation like Day 3's was recorded for Day 1;
  its rows were later confirmed unchanged by fingerprint.

### Day 2: interrupted, remains an incident (v5.2.3, 2026-11-05)

- **What happened:**
  - Started 06:48:43 UTC.
  - After 11 of 36 combinations, a Neon database timeout stopped the run, and the run's finalisation also timed
    out.
  - No provider request was in flight.
- **What was recorded:** 11 attempts, 1,702 tokens. The three runs are marked `failed` and kept as an
  **incident record** (`evaluation/reports/v5.2.3-day2/`), titled "Day 2 Interrupted — Non-publishable Incident
  Record".
- **Why it wasn't simply re-run:** the protocol says a stopped day is never restarted or resumed. Under v5.2.3,
  the four-day comparison can no longer be completed.
- **Status today:** still an interrupted incident. The recovery below didn't change this record or its `failed`
  runs; it is a separate registration.

### Day 2 recovery: separate registration, exploratory (v5.2.4, 2026-11-05, 09:09–09:18 UTC)

- **How it was done:** a separate, **disclosed post-hoc** registration.
  - It was written after the first 11 outcomes (all passes) had been seen.
  - It carried those 11 genuine results over unchanged.
  - It ran the 25 missing combinations once, in the registered order.
- **Coverage:** the recovery accounted for **all 36** Day 2 combinations (11 carried over + 25 run), 0 missing. The recovery attempts were 25, using 8,930 tokens; all of Day 2
  used 10,632 tokens. No retries or fallbacks.
- **Pass rates:** 12/12 for every strategy, so the exploratory paired difference is 0.00.
- **Verification:** at the time, against Neon and the ledger (recorded in the v5.2.4 changelog).
- **Status:** **non-publishable**. It is post-hoc; there is a ~2.5-hour gap between the carried-over and recovered
  results; and one case (T02) is split across the two sets of runs.

The database reliability fixes (bounded retries, idempotent writes, verified finalisation) were added in this
revision.

### Day 3: completed, post-incident exploratory (v5.2.5, 2026-11-06, 05:11:42–05:21:56 UTC)

- **Registration:** `routewise_bench_v5.2.5` was created **after Days 1 and 2 had been run and observed**, so it is
  **exploratory**. It declares `publishable: false`, authorises Day 3 only, and reuses the pinned schedule
  unchanged.
- **Workload:** **11 cases per strategy** (S02 S03 S09 S10 T05 T07 T11 T13 C07 C09 C12) × 3 = 33 combinations.
  **33/33 accounted for.**

| Strategy | Pass | Wilson 95% CI | p50 / p95 latency | Est. list cost per accepted answer | Models used |
|---|---|---|---|---|---|
| baseline_premium | 11/11 | 74.1%–100% | 2,373 / 5,310 ms | $0.00011700 | 120B ×11 |
| routewise | 11/11 | 74.1%–100% | 2,239 / 7,862 ms | $0.00008563 | 20B ×7, 120B ×4 |
| routewise_tier_first | 11/11 | 74.1%–100% | 2,175 / 4,038 ms | $0.00008312 | 20B ×7, 120B ×4 |

- **Usage:**
  - 33 requests, all succeeded, using 33 provider attempts (the registered maximum was 94).
  - No retries or fallbacks.
  - 8,968 tokens (input 4,260; output 4,708): 120B 6,578; 20B 2,390.
- **Latency over all 33 results:** median 2,239 ms, p90 4,038 ms, maximum 7,862 ms.
- **Cost:**
  - Actual charge **$0** (free tier).
  - Estimated list-price (shadow) cost $0.00314328 in total.
  - Exploratory cost-per-accepted ratio vs the baseline: 0.73 (`routewise`) and 0.71 (`routewise_tier_first`).
- **Quota:** an owner reading of 200,000 tokens/day remaining on both models at 05:06:51 UTC; required ≥ 157,747
  for the worst case.
- **Protection:** the run took an atomic database execution claim
  (`d150469c-eb6e-436f-b599-ea386254b734`) before any run or provider call.
- **Independent reconciliation: 25/25 checks passed.** Checks were read-only against Neon and the quota ledger:
  - 33 unique combinations, none missing or unexpected
  - 3 runs `completed`
  - every result linked to a `succeeded` request log
  - the report matches Neon field by field
  - 33 ledger entries with per-model tokens equal to Neon's
  - the claim present
  - all earlier runs and reports unchanged

### Day 4: completed, post-incident exploratory (v5.2.6, 2026-11-07, 02:51:04–03:02:29 UTC)

- **Registration:** `routewise_bench_v5.2.6`, registered 2026-11-07T02:35:15Z after Days 1–3 had been observed,
  so it is **exploratory**. It declares `publishable: false`, authorises Day 4 only, reuses the pinned schedule and
  pinned code unchanged, and was committed (`60a3740`) before the first provider call.
- **Workload:** 12 cases per strategy (S01 S04 S12 S13 S15 T01 T04 T10 T12 C02 C04 C05) × 3 = 36 combinations.
  **36/36 accounted for.**

| Strategy | Pass | Wilson 95% CI | p50 / p95 latency | Est. list cost per accepted answer | Models used |
|---|---|---|---|---|---|
| baseline_premium | 12/12 | 75.8%–100% | 2,467 / 3,394 ms | $0.00013572 | 120B ×12 |
| routewise | 11/12 | 64.6%–98.5% | 2,222 / 3,265 ms | $0.00010507 | 20B ×7, 120B ×5 |
| routewise_tier_first | 11/12 | 64.6%–98.5% | 2,195 / 3,339 ms | $0.00010507 | 20B ×7, 120B ×5 |

- Both RouteWise strategies failed **T04**, a standard case that was routed to `gpt-oss-20b`.
- **Pre-registered verdicts:** the pass-rate difference was −0.083 for both (bootstrap CI −0.25 to 0.00). The
  quality rule **did not hold**, so the cost rule **did not hold** either (cost-per-accepted ratio 0.77).
- **Usage:**
  - 36 requests, all succeeded, using 36 provider attempts (the registered maximum was 100).
  - No retries or fallbacks.
  - 11,505 tokens (input 5,898; output 5,607): 120B 8,985; 20B 2,520.
- **Latency over all 36 results:** median 2,398 ms, p90 3,231 ms, maximum 3,394 ms.
- **Cost:** actual charge **$0** (free tier); estimated list-price (shadow) cost $0.00394024 in total.
- **Quota:** an owner reading at 02:35:47 UTC of 200,000 tokens/day remaining on both models (organization limit,
  0 used); required ≥ 167,285 for the worst case.
- **Protection:** the atomic execution claim `7e6ee6dc-1b85-40e5-b4a8-f9b0c72f55f4` was taken before any run or
  provider call; the Day 3 claim is unchanged.
- **Independent reconciliation: 27/27 checks passed**: the Day 3 checks plus an unchanged Day 3 claim and Day 3
  report.

## 4. Descriptive totals (Days 1–4; not a registered analysis)

| | baseline_premium | routewise | routewise_tier_first |
|---|---|---|---|
| Passes | 45/45 | 43/45 | 43/45 |

- Total Groq usage: 30 + 36 + 33 + 36 = 135 provider attempts, 43,328 tokens, $0 actual charge.
- RouteWise sent the small model 7 of 10 (Day 1), 6 of 12 (Day 2), 7 of 11 (Day 3) and 7 of 12 (Day 4) requests.
- Both routing losses (T03 on Day 1, T04 on Day 4) were standard cases sent to the small model.

These totals mix four registrations, including post-hoc and post-incident ones. They are **not** a pooled
analysis, and no pooled analysis is registered.

## 5. Limitations

**Statistics:**
- 10–12 cases per day give very wide confidence intervals; 11/11 still has a lower bound of 74.1%.
- When every case passes, the bootstrap difference interval collapses to [0, 0]. That says little about
  non-inferiority with this few cases.
- The two RouteWise strategies chose the **same model on every case** on all four days. With only two Groq
  models enabled, `cheapest_capable` and `lowest_tier_first` make the same choices; they differ only when
  OpenRouter or Ollama models are eligible. The data can't distinguish them.
- "Premium" means the largest *free* Groq model, and both models are from one family (GPT-OSS 20B vs 120B), not
  independent model families.

**Exploratory vs confirmatory:**
- Only the **original v5.2.3 four-day plan** was prospective, and it can't be completed: its Day 2 was interrupted.
  Day 4 was run later under its own exploratory registration (v5.2.6), which doesn't complete the original plan.
- The Day 2 recovery (v5.2.4), Day 3 (v5.2.5) and Day 4 (v5.2.6) were registered after earlier outcomes were known. They are
  **exploratory**: useful for describing behaviour, not for confirming a hypothesis.
- Day 1 on its own is a single day of a plan meant to be analysed only after all four days are pooled.

**Publication:**
- No day is publishable as a confirmatory result.
- Costs are **estimated list prices** (shadow cost); actual charges were $0 on the free tier.
- Latency was measured from a home connection to Groq's free tier, so it isn't representative of the gateway.
- Results apply only to this fixed 45-case suite and pinned configuration, not to production workloads.

## 6. What would make it confirmatory

A new, fully prospective registration, written before any data is seen, with:
- more cases per strategy
- more than two distinct model families
- all days run on schedule
- one pre-registered pooled analysis

The run-once claims, database retries and quota guard built during this project are designed for exactly that.
