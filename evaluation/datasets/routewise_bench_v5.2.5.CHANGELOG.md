# routewise_bench_v5.2.5 — Post-incident, exploratory Day 3 registration

**Registered 2026-11-06T03:08:50Z; not executed.** This is a **post-incident, exploratory
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
