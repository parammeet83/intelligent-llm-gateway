# routewise_bench_v5.2.6 — Post-incident, exploratory Day 4 registration

**Registered 2026-11-07T02:35:15Z; not executed.** This is a **post-incident, exploratory registration**,
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
