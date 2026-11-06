# Day 3 closure: routewise_bench_v5.2.5 (post-incident, exploratory)

**Status: Day 3 COMPLETE.** All 33 registered combinations are accounted for, and every validation was verified
independently against Neon and the quota ledger.

**Scientific status:** post-incident and exploratory. The registration was written after Days 1–2 had been run
and observed, and it declares `publishable: false`, so this result is **never publishable as a confirmatory
result**. There is **no completed four-day confirmatory experiment**:

| Day | What happened | Status |
|---|---|---|
| Day 1 (v5.2.3, 2026-11-04) | Completed. | Complete |
| Day 2 (v5.2.3) | Interrupted by a Neon timeout. | Incident record |
| Day 2 (v5.2.4 recovery) | Disclosed post-hoc recovery. | Exploratory, non-publishable |
| Day 3 (v5.2.5) | This record. | Exploratory, non-publishable |
| Day 4 | Not run and **not authorised** by v5.2.5. | Not run |

The report's per-day "verdict" lines (non-inferiority, cost rule) are computed mechanically for one day. They
are exploratory observations, not claims.

## Execution

| Item | Value |
|---|---|
| Revision | `routewise_bench_v5.2.5`: revision `27966b436884cc89…`, pre-registration `9b1f17befef2ae93…`, manifest `da3001d6ac9ca5df…` |
| Schedule | `execution_schedule_routewise_bench_v5.2.3.yaml` (`c74699c11ec73ef0…`), day 3 of the pinned schedule |
| Registered window | One UTC date 2026-11-06 … 2026-11-17, started by 22:00 UTC |
| Executed | 2026-11-06, 05:11:42 → 05:21:56 UTC (execution claim taken 05:11:34.888 UTC) |
| Code | Commit `24568142b4c374b35ee1496bf755f2001c2d97f4` (CI run 42161021885 green), deployed to Render as `dep-dbmlal61egvs73cuvf3g` |
| Command | `.\scripts\benchmark-day.ps1 -Revision routewise_bench_v5.2.5 -Day 3 … -Run`: guard, preflight, then `eval-run` (exit 0) |
| Quota reading | Groq console, 05:06:51 UTC: 200,000 of 200,000 TPD remaining on both `gpt-oss-20b` and `gpt-oss-120b`. Required ≥ 157,747; worst case 141,972; usable 180,000 (90%) |
| Workload | 11 cases (S02 S03 S09 S10 T05 T07 T11 T13 C07 C09 C12) × 3 strategies = 33 combinations |
| Requests | 33 expected and 33 sent; 33 succeeded, 0 failed |
| Provider attempts | 33 of a registered maximum of 94 (all `PRIMARY`); 0 retries, 0 fallbacks |
| Tokens | 8,968 in total (input 4,260, output 4,708): `gpt-oss-120b` 6,578 (19 attempts), `gpt-oss-20b` 2,390 (14 attempts) |
| Answer models | baseline_premium: 120B ×11. routewise: 20B ×7, 120B ×4. routewise_tier_first: 20B ×7, 120B ×4 |
| Pass rates | 11/11 for each strategy (all answered). The paired difference against the baseline is 0.0 for both RouteWise strategies |
| Latency (33 results, ms) | min 1,731, median 2,239, mean 2,732.9, p90 4,038, max 7,862. Per strategy, p50/p95: baseline 2,373/5,310; routewise 2,239/7,862; tier-first 2,175/4,038 |
| Actual charge | **$0** (free tier; `cost_status: free_tier` on all 33) |
| Estimated list cost (shadow, not charged) | $0.00314328 in total: baseline $0.00128700, routewise $0.00094194, tier-first $0.00091434. This is never added to actual charges |

Hosted-environment latency (Groq free tier, from a home connection) isn't representative of the gateway itself.

## Neon records

| Record | ID / status |
|---|---|
| Execution claim | `d150469c-eb6e-436f-b599-ea386254b734` (v5.2.5, day 3, label `v5.2.5-day3`), present |
| Run baseline_premium | `4eb0491d-f79d-4b6e-a2ad-1756e5fd27a8`, `completed` |
| Run routewise | `c6c10121-288f-49ea-9d80-2bb4cf4216bf`, `completed` |
| Run routewise_tier_first | `ee968cdb-73d3-4e50-a0c2-0fcc98fe650e`, `completed` |

## Validation (independent, read-only)

25/25 checks passed. Each was recomputed from Neon, the pinned schedule and the ledger, not taken from the runner's
summary:

- **Combinations:** 33 unique (case, strategy) results; 0 missing, 0 duplicate, 0 unexpected against the pinned
  schedule.
- **Runs:**
  - 3 runs, one per strategy, all `completed` with `finished_at`, real (`simulated: false`)
  - no run anywhere `running` or `pending`
  - the report's `run_ids` equal Neon's
- **Claim:** exactly one execution claim, taken before every run. Alembic is at `0003`.
- **Request logs:** every result links to its own request log (33 distinct), all `succeeded`. Each log's
  `attempt_count` equals its `request_attempts` rows.
- **Report vs Neon:** all 33 report rows match Neon field by field (pass, score, model, provider, tier, tokens,
  latency, fallback, error, simulated, cost status, request link, attempt count). The report is complete,
  `publishable: false` and real.
- **Ledger:**
  - 33 entries since the 05:06:51 reading, equal to Neon's 33 provider attempts, all `sent_known`
  - tokens per model match exactly (20B 2,390; 120B 6,578)
  - the 66 earlier entries are byte-identical to the copy in the evidence backup (`5a77c4ec…`)
- **Historical evidence:**
  - md5 fingerprints over all pre-existing evaluation runs, results and cases are identical to the pre-deploy
    baseline
  - the Day 1, Day 2 incident and Day 2 recovery reports are unchanged

## Release and migration

- Migration `0003_benchmark_execution_claims` reached Neon through the deploy. The container log shows
  `Running upgrade 0002 -> 0003` at 04:20:26 UTC, before uvicorn started.
- After the deploy:
  - `/health`: production, providers `["mock"]`, `simulated_only: true`
  - `/ready`: database ok, migrations ok
  - 26/26 mock-only smoke tests passed
  - production stays mock-only
- Neon checkpoint before the migration: branch `br-cold-snow-b35jvc94` (`pre-0003-v5.2.5-20261106`, LSN
  `0/1E6B430`, 2026-11-06 04:17:38 UTC). Verified identical to production.
- Rollback target: commit `4193a94` (local branch `rollback/v5.2.4-plus-0003`). See `docs/DEPLOYMENT.md`; never
  deploy a commit without migration 0003.

## Deliverables (local, git-ignored)

| File | SHA-256 |
|---|---|
| `evaluation/reports/v5.2.5-day3/summary.json` | `267e681839c6b776fa18a6b44bbb45a4f61d36957239d61ea48115d3c2e0dfb0` |
| `evaluation/reports/v5.2.5-day3/results.jsonl` | `0fab189ca77293eb43ea37c023de41a3231300c1676e98fe1b410ccb4f43b337` |
| `evaluation/reports/v5.2.5-day3/summary.md` | `92fa04a8da66a2c299eabb4ec22a8b0e84fc6531b302554d37b06005c5441d8a` |
| `evaluation/reports/quota_ledger.json` (after Day 3) | `217c0d272b61294a911e3bf0dd0aa6c575c6ddec05fa0cb07aba218843097bba` |

The audit trail is in `evaluation/reports/v5.2.5-day3-release/`: the execution log, Neon snapshots, the smoke
tests and `neon_reconciliation_day3.json`. Secret scan of all of these: 0 findings.

## Limitations

- **Exploratory, not confirmatory:** the registration came after Days 1–2 were observed.
- **No four-day result:** Day 4 is not authorised, so no pooled four-day analysis exists. Day 3 stands alone.
- **Small sample:** 11 paired cases, with a pass-rate CI of [74.1%, 100%] per strategy.
- **Quota reading:** the daily quota is the owner's console reading; Groq's API doesn't report daily remaining
  tokens.
- **Latency:** measured over a home connection to Groq's free tier.
