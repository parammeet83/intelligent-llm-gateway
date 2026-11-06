# routewise_bench_v5.2.5 — Post-incident, exploratory Day 3 registration

**Registered 2026-11-06T03:08:50Z; executed 2026-11-06 05:11–05:21 UTC (Day 3 complete; see Outcome).** This is a **post-incident, exploratory
registration**, not a prospective, confirmatory one. It was written after Day 1 (complete) and Day 2
(interrupted on 2026-11-05, then completed by the disclosed v5.2.4 recovery) had been run and their
outcomes observed. The pre-registration declares `publishable: false`: its results are **never
publishable as a confirmatory result**. It authorises **Day 3 only**; Day 4 needs its own
authorisation. v5.2.3, v5.2.4 and every earlier artefact are unchanged.

## What v5.2.5 does

- **Runs** the pinned v5.2.3 schedule's Day 3 once: 11 cases (S02 S03 S09 S10 T05 T07 T11 T13 C07 C09
  C12) × 3 strategies = 33 combinations, in the registered interleaved order.
- **Keeps unchanged** the dataset, prompts, expected answers, scoring (including the v5.2.1
  amendment), the review attestation gate, the schedule, strategies, models, routing, pacing, retries
  and fallbacks, the per-attempt quota guard, statistics and the v5.2.4 database reliability rules.
  The v5.2.4 Day 2 recovery plan is not part of this registration.
- **Fixes the execution window** to the original one, which had not expired: one UTC date from
  2026-11-06 to 2026-11-17, started by 22:00 UTC. That leaves room for a Day 4 by 2026-11-18 (14 days
  after Day 1). The runner, `eval-run`, `eval-validate` and the benchmark guard refuse other days and
  dates.
- **Adds run-once protection**, which any revision with a schedule gets:
  - an atomic database claim, one row per (revision, scheduled day), enforced by a unique
    constraint (migration `0003`, table `benchmark_execution_claims`), taken before any run is
    created or provider called
  - a read-only check for existing claims and runs of that revision and day, both in `eval-run`
    before any network call and again in the runner
  - fail closed: if the database can't confirm the day hasn't started (unavailable, missing table,
    ambiguous commit), the run is refused
  - an interrupted Day 3 is never restarted; it stays incomplete
- **Worst case** (recomputed from the pinned schedule): 33 requests, at most 94 provider attempts and
  141,972 tokens (gpt-oss-120b 104,448; gpt-oss-20b 37,524). The tighter model needs at least 157,747
  tokens remaining (90% safety), read by the owner on the run date.
- **Completeness:** all 33 combinations have exactly one persisted result, each linked to its request
  log; the three Day 3 runs are `completed`; no run is left `running`. No pooling with Days 1–2 is
  registered.

## Prerequisites before Day 3 can run (not done by this registration)

- Migration `0003` must be applied to Neon. The deployed API's `/ready` compares the database's
  Alembic revision with its own code head (`0002`), so the migration has to go out together with a
  redeploy of the API that contains it. That needs a separate authorisation.
- The owner's same-day console reading of the remaining tokens for both models.

## Chain

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.5.revision.yaml` | `27966b436884cc89db91c87ad316111b0e0e5e4cc2b7981076526ae8262692e8` |
| `evaluation/preregistration_routewise_bench_v5.2.5.yaml` | `9b1f17befef2ae93409f48ec58807e703e2d19253215391b54411c3d624b1818` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.5.yaml` | `da3001d6ac9ca5df4681230736f784fc72dad618d1f77a0edfd61c59ccd6fca7` |

The pinned schedule is unchanged: `evaluation/execution_schedule_routewise_bench_v5.2.3.yaml`
(`c74699c11ec73ef08e0d883fedf7ffe5b5bc996c84de8ba9abbb0207b94756e6`).

The v5.2.5 manifest pins these changed application files: `app/cli.py`, `app/db/models.py`,
`app/evaluation/report.py` and `app/evaluation/runner.py`. v5.2.4 is now refused at run time; its 4
manifest-dependent tests are strict xfail.

## Outcome (verified against Neon)

Executed 2026-11-06 05:11:42–05:21:56 UTC from commit `24568142` (CI green; deployed with migration 0003).
Full record: `docs/BENCHMARK_DAY3_CLOSURE_v5.2.5.md`.

- **Status:** Day 3 complete. Post-incident and exploratory; `publishable: false`. Day 4 was not run.
- **Execution claim:** `d150469c-eb6e-436f-b599-ea386254b734`, taken 05:11:34 UTC.
- **Runs** (all `completed`):
  - baseline_premium `4eb0491d-f79d-4b6e-a2ad-1756e5fd27a8`
  - routewise `c6c10121-288f-49ea-9d80-2bb4cf4216bf`
  - routewise_tier_first `ee968cdb-73d3-4e50-a0c2-0fcc98fe650e`
- **Matrix:** 33/33 combinations, 0 missing, 0 duplicates; each linked to a `succeeded` request log.
- **Pass rates:** 11/11 for every strategy, so the exploratory paired difference against the baseline is 0.00.
- **Groq usage:** 33 attempts and 8,968 tokens (gpt-oss-120b 6,578; gpt-oss-20b 2,390); 0 retries or fallbacks.
  The ledger agrees exactly.
- **Charge:** $0 actual (free tier). Estimated list cost (shadow) $0.00314328.
- **Report:** `evaluation/reports/v5.2.5-day3/` (git-ignored):
  - `summary.json` `267e681839c6b776fa18a6b44bbb45a4f61d36957239d61ea48115d3c2e0dfb0`
  - `results.jsonl` `0fab189ca77293eb43ea37c023de41a3231300c1676e98fe1b410ccb4f43b337`
  - `summary.md` `92fa04a8da66a2c299eabb4ec22a8b0e84fc6531b302554d37b06005c5441d8a`
