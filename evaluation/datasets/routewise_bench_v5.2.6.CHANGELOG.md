# routewise_bench_v5.2.6 — Post-incident, exploratory Day 4 registration

**Registered 2026-11-07T02:35:15Z; executed 2026-11-07 02:51–03:02 UTC (Day 4 complete; see Outcome).** This is a **post-incident, exploratory registration**,
not a prospective, confirmatory one. It was written after Days 1–3 had been run and observed:
- Day 1 completed under v5.2.3.
- Day 2 was interrupted and remains an incident record; the disclosed v5.2.4 recovery separately accounted for its
  36 combinations.
- Day 3 completed under v5.2.5 (exploratory).

The pre-registration declares `publishable: false`: its results are **never publishable as a confirmatory
result**. It authorises **Day 4 only**. The original v5.2.3 four-day confirmatory comparison remains incomplete.
v5.2.3, v5.2.4, v5.2.5 and every earlier artefact are unchanged.

## What v5.2.6 does

- **Runs** the pinned v5.2.3 schedule's Day 4 once: 12 cases (S01 S04 S12 S13 S15 T01 T04 T10 T12 C02 C04
  C05) × 3 strategies = 36 combinations, in the registered interleaved order.
- **Keeps unchanged** everything in v5.2.5 except the authorised day and its window:
  - the dataset, prompts and expected answers
  - scoring, including the v5.2.1 amendment
  - the review attestation gate
  - the schedule, strategies, models, routing, pacing, retries and fallbacks
  - the per-attempt quota guard, statistics and database reliability rules
  - the pinned application code: the manifest's `pinned` section is identical to v5.2.5's, because no
    application file changed
- **Fixes the execution window** to the original one, which has not expired: one UTC date from 2026-11-07 (the
  day after Day 3) to 2026-11-18 (14 days after Day 1), started by 22:00 UTC.
- **Uses the run-once protection** from v5.2.5:
  - an atomic database claim, unique per (revision, scheduled day) (migration `0003`), taken before any run or
    provider call
  - a read-only check for existing claims and runs
  - fail closed on any database doubt
  - an interrupted Day 4 is never restarted
- **Worst case** (from the pinned schedule): 36 requests, at most 100 provider attempts and 150,556 tokens
  (gpt-oss-120b 117,828; gpt-oss-20b 32,728). The tighter model needs at least **167,285** tokens remaining (90%
  safety), read by the owner on the run date.
- **Completeness:** all 36 combinations have exactly one persisted result, each linked to its request log; the
  three Day 4 runs are `completed`; no run is left `running`. No pooling with Days 1–3 is registered.

## Chain

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.6.revision.yaml` | `3da3cd938c1435c3904d96312a185c154d0e53352ea4882ec7cffefda287d480` |
| `evaluation/preregistration_routewise_bench_v5.2.6.yaml` | `3dac0e69c672e08626353353d06994e231fe04530df36a22dd19473d0572e56d` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.6.yaml` | `68a1e8cbc6e0133144174256c0f6ee9f40b668ca71bc5b355233b5643e870e19` |

The pinned schedule is unchanged: `evaluation/execution_schedule_routewise_bench_v5.2.3.yaml`
(`c74699c11ec73ef08e0d883fedf7ffe5b5bc996c84de8ba9abbb0207b94756e6`). v5.2.5 remains valid code-wise but
authorises Day 3 only, which is complete and claimed, so it can't run again.

## Outcome (verified against Neon)

Executed 2026-11-07 02:51:04–03:02:29 UTC (registration commit `60a3740`, CI green). Full record:
`docs/BENCHMARK_DAY4_CLOSURE_v5.2.6.md`.

- **Status:** Day 4 complete. Post-incident and exploratory; `publishable: false`. No other day was run.
- **Execution claim:** `7e6ee6dc-1b85-40e5-b4a8-f9b0c72f55f4`, taken 02:50:57 UTC. The Day 3 claim is unchanged.
- **Runs** (all `completed`):
  - baseline_premium `c1165060-d370-4026-8a7e-11ff933e6105`
  - routewise `ad234f79-254a-4862-8666-42d9e6455235`
  - routewise_tier_first `6b10911e-be48-48b5-ad11-ed63dbbf62ce`
- **Matrix:** 36/36 combinations, 0 missing, 0 duplicates; each linked to a `succeeded` request log. Independent
  reconciliation: 27/27 checks.
- **Pass rates:** baseline 12/12; routewise and routewise_tier_first 11/12 (T04 failed on `gpt-oss-20b`). The
  registered quality rule did not hold (difference −0.083, CI −0.25 to 0.00), so the cost rule did not hold either.
- **Groq usage:** 36 attempts and 11,505 tokens (gpt-oss-120b 8,985; gpt-oss-20b 2,520); 0 retries or fallbacks.
  The ledger agrees exactly.
- **Charge:** $0 actual (free tier). Estimated list cost (shadow) $0.00394024.
- **Report:** `evaluation/reports/v5.2.6-day4/` (git-ignored):
  - `summary.json` `9336c6e88a206c3dbdc15da40adff97cb8b7f028f9cb87b4140f958f923513f2`
  - `results.jsonl` `f235932897098edc709f1935f64743f84103af49af07312c09cd82d5820052a6`
  - `summary.md` `a6c9e92d4bf744a6e4a7a123da0348b1a4a9d63c9b85b1dddcc4bc4be619de26`
