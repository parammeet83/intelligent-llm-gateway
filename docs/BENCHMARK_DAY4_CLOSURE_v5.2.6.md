# Day 4 closure: routewise_bench_v5.2.6 (post-incident, exploratory)

**Status: Day 4 COMPLETE.** All 36 registered combinations are accounted for, and every validation was verified
independently against Neon and the quota ledger (27/27 checks).

**Scientific status:** post-incident and exploratory. The registration was written on 2026-11-07, after Days 1–3
had been run and observed, and it declares `publishable: false`, so this result is **never publishable as a
confirmatory result**. All four scheduled days have now been run once, but **the original v5.2.3 four-day
confirmatory experiment remains incomplete**:

| Day | Revision | What happened | Status |
|---|---|---|---|
| Day 1 | v5.2.3 | Completed | Prospective (registered before Day 1) |
| Day 2 | v5.2.3 | Interrupted by a Neon timeout | Incident record |
| Day 2 | v5.2.4 | Separate disclosed recovery; accounted for all 36 combinations | Exploratory |
| Day 3 | v5.2.5 | Completed | Exploratory |
| Day 4 | v5.2.6 | This record | Exploratory |

No pooled four-day analysis is registered.

## Execution

| Item | Value |
|---|---|
| Revision | `routewise_bench_v5.2.6`: revision `3da3cd938c1435c3…`, pre-registration `3dac0e69c672e086…`, manifest `68a1e8cbc6e01331…` |
| Registered | 2026-11-07T02:35:15Z; committed as `60a3740` (CI run 42330582354 green) before the first provider call |
| Schedule | `execution_schedule_routewise_bench_v5.2.3.yaml` (`c74699c11ec73ef0…`), day 4 of the pinned schedule |
| Registered window | One UTC date 2026-11-07 … 2026-11-18, started by 22:00 UTC |
| Executed | 2026-11-07, 02:51:04 → 03:02:29 UTC (execution claim taken 02:50:57.285 UTC) |
| Code | Unchanged since v5.2.5; production API still `2456814` (mock only); the benchmark ran from the CLI |
| Command | `.\scripts\benchmark-day.ps1 -Revision routewise_bench_v5.2.6 -Day 4 … -Run`: guard, preflight, then `eval-run` (exit 0) |
| Quota reading | Owner's Groq console reading at 02:35:47 UTC: organization limit 200,000 TPD and 0 used for both `gpt-oss-20b` and `gpt-oss-120b`, so 200,000 remaining each. A project-level limit was not reported separately. Required ≥ 167,285; worst case 150,556; usable 180,000 (90%) |
| Workload | 12 cases (S01 S04 S12 S13 S15 T01 T04 T10 T12 C02 C04 C05) × 3 strategies = 36 combinations |
| Requests | 36 expected and 36 sent; 36 succeeded, 0 failed |
| Provider attempts | 36 of a registered maximum of 100 (all `PRIMARY`); 0 retries, 0 fallbacks |
| Tokens | 11,505 in total (input 5,898, output 5,607): `gpt-oss-120b` 8,985 (22 attempts), `gpt-oss-20b` 2,520 (14 attempts) |
| Answer models | baseline_premium: 120B ×12. routewise: 20B ×7, 120B ×5. routewise_tier_first: 20B ×7, 120B ×5 |
| Pass rates | baseline 12/12 (Wilson 75.8%–100%); routewise 11/12 and routewise_tier_first 11/12 (64.6%–98.5%). All 36 answered |
| Failed case | **T04** (standard), for both RouteWise strategies, routed to `gpt-oss-20b` |
| Pre-registered verdicts | Pass-rate difference −0.083 (bootstrap CI −0.25 to 0.00) for both. The quality rule **did not hold**, so the cost rule **did not hold** either (cost-per-accepted ratio 0.77) |
| Latency (36 results, ms) | min 1,700, median 2,398, mean 2,441.6, p90 3,231, max 3,394. Per strategy, p50/p95: baseline 2,467/3,394; routewise 2,222/3,265; tier-first 2,195/3,339 |
| Actual charge | **$0** (free tier; `cost_status: free_tier` on all 36) |
| Estimated list cost (shadow, not charged) | $0.00394024 in total. Per accepted answer: baseline $0.00013572, routewise and tier-first $0.00010507. Never added to actual charges |

## Neon records

| Record | ID / status |
|---|---|
| Execution claim | `7e6ee6dc-1b85-40e5-b4a8-f9b0c72f55f4` (v5.2.6, day 4, label `v5.2.6-day4`), present |
| Day 3 claim | `d150469c-eb6e-436f-b599-ea386254b734`, unchanged; these are the only two claims |
| Run baseline_premium | `c1165060-d370-4026-8a7e-11ff933e6105`, `completed` |
| Run routewise | `ad234f79-254a-4862-8666-42d9e6455235`, `completed` |
| Run routewise_tier_first | `6b10911e-be48-48b5-ad11-ed63dbbf62ce`, `completed` |

## Validation (independent, read-only): 27/27 checks passed

The Day 3 checks, adapted for Day 4, plus a check that the Day 3 claim is unchanged and that the Day 3 report is
unchanged:

- **Combinations:** 36 unique (case, strategy) results; 0 missing, 0 duplicate, 0 unexpected against the pinned
  schedule.
- **Runs:**
  - 3 runs, one per strategy, all `completed` with `finished_at`, real
  - no run anywhere `running` or `pending`
  - the report's `run_ids` equal Neon's
- **Claims:** exactly one v5.2.6 day-4 claim, taken before every run; the Day 3 claim unchanged; Alembic `0003`.
- **Request logs:** every result links to its own request log (36 distinct), all `succeeded`; `attempt_count`
  equals the `request_attempts` rows.
- **Report vs Neon:** all 36 report rows match Neon field by field. The report is complete, `publishable: false`
  and real.
- **Ledger:** 36 entries since the 02:35:47 reading, equal to Neon's 36 provider attempts, all `sent_known`;
  tokens per model match exactly (120B 8,985; 20B 2,520).
- **Historical evidence:**
  - md5 fingerprints over all pre-existing runs, results and cases are identical to the pre-run snapshot
  - the Day 1, Day 2 incident, Day 2 recovery and Day 3 reports are unchanged

## Deliverables (local, git-ignored)

| File | SHA-256 |
|---|---|
| `evaluation/reports/v5.2.6-day4/summary.json` | `9336c6e88a206c3dbdc15da40adff97cb8b7f028f9cb87b4140f958f923513f2` |
| `evaluation/reports/v5.2.6-day4/results.jsonl` | `f235932897098edc709f1935f64743f84103af49af07312c09cd82d5820052a6` |
| `evaluation/reports/v5.2.6-day4/summary.md` | `a6c9e92d4bf744a6e4a7a123da0348b1a4a9d63c9b85b1dddcc4bc4be619de26` |

The audit trail is in `evaluation/reports/v5.2.6-day4-release/`: the pre-run Neon snapshot and
`neon_reconciliation_day4.json`.

## Limitations

- **Exploratory:** the registration came after Days 1–3 were observed.
- **No four-day confirmatory result:** the original protocol's Day 2 stays an interrupted incident, and no pooled
  analysis is registered.
- **Small sample:** 12 paired cases.
- **Strategies not distinguishable:** the two RouteWise strategies again chose the same model on every case.
- **Quota reading:** the daily quota is the owner's console reading (organization level).
- **Latency:** measured over a home connection to Groq's free tier.
