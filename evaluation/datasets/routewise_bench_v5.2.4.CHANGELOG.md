# routewise_bench_v5.2.4 — Disclosed post-hoc Day 2 recovery

**Registered 2026-11-05T08:56:09Z; executed 2026-11-05 09:09–09:18 UTC.** This is a **post-hoc
recovery amendment**, not a clean prospective registration. It was written after Day 2 of v5.2.3 was
interrupted (a Neon timeout at about 06:50 UTC) and after 11 of Day 2's 36 outcomes, all passes, had
been observed. Its results are exploratory and **never publishable as a confirmatory result**. The
v5.2.3 registration, its Day 2 incident record and every earlier artefact are unchanged.

## What v5.2.4 does

- **Carries over** the 11 genuine results of the interrupted v5.2.3 runs unchanged, registered by
  evaluation-result and request-log ID. The three original runs stay `failed`.
- **Executes** the 25 missing combinations once, in the registered Day 2 order (continuing at
  routewise_tier_first/T02), as one recovery run per strategy. It uses the registered configuration,
  pacing (concurrency 1, delay 6 s), retries and fallbacks, and the per-attempt quota guard.
- **Defines** completeness: all 36 combinations accounted for from Neon, every recovery run
  `completed`, the original runs `failed`, and no validation problem. Publishability: never as a
  confirmatory result.
- **Fixes** database reliability in the runner:
  - bounded backoff on database operations
  - idempotent result persistence
  - a combination is retried only when the quota ledger proves no provider attempt was sent
  - finalisation is retried and never hides the original error
  - persisted results are verified before a run can be `completed`
  - `eval-finalize-runs` closes runs left `running`
  - **any** exception now marks runs `failed`; before, any exception other than a quota stop
    would have let finalisation mark interrupted runs `completed`

Disclosed limitations (also in the recovery plan):
- it is post-hoc
- there is a time gap of about 2.5 hours between the carried-over and recovered results
- T02 is split: two strategies come from the interrupted runs and one from the recovery
- Day 2 results come from two sets of runs
- the scope is Day 2 only; the v5.2.3 four-day comparison remains incomplete

## Chain

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.4.revision.yaml` | `eed5b11c0650c916860805ac9c5537182eda8d73ea93738ac2bae7d0502c8ec6` |
| `evaluation/preregistration_routewise_bench_v5.2.4.yaml` | `b041f94a2fa0ad8e53cc4530e6f45568da9fe4dedbf708ba2750c99267515619` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.4.yaml` | `d6efb0d9ec9d12d25a132ccb9fb1ee929d776783a50a3d68ebbdee6e483099b2` |
| `evaluation/execution_recovery_routewise_bench_v5.2.4.yaml` | `e3c46ba492fd5cf5ba33cb13b672c2771d273563ec01ca2b64e5082472f7a1da` |

Changed application files, pinned by the v5.2.4 manifest: `app/cli.py`,
`app/evaluation/dataset.py`, `manifest.py`, `preflight.py`, `report.py` and `runner.py`. v5.2.3 is now
refused at run time; its 6 manifest-dependent tests are strict xfail.

## Outcome (verified against Neon)

- **Recovery runs** (all `completed`): baseline_premium `02641677-f97b-4cd4-899f-1d20a8d44d90`,
  routewise `6d930fbe-ccb8-4f23-9159-0baae51a7a82`, routewise_tier_first
  `fcf7088b-b062-40bd-abe9-bb88a297013e`.
- **Matrix:** 36/36 combinations (11 carried over + 25 recovered), 0 missing, 0 duplicates; each
  linked to a `succeeded` request log.
- **Pass rates:** 12/12 for every strategy, so the exploratory paired difference is 0.00 for both
  RouteWise strategies against the baseline.
- **Groq usage:**
  - recovery: 25 attempts and 8,930 tokens (gpt-oss-20b 1,140; gpt-oss-120b 7,790), with no retries
    or fallbacks; the ledger agrees exactly
  - all of Day 2: 10,632 tokens (gpt-oss-20b 2,086; gpt-oss-120b 8,546)
- **Charge:** $0 actual (free tier).
- **Report:** `evaluation/reports/v5.2.4-day2-recovery/` (git-ignored; built from Neon by
  `eval-recovery-report`):
  - `summary.json` `df534e522b466e048292f0efb067bb7c32d48e2284128d0c1fa06ba528aa22de`
  - `results.jsonl` `83eb056853e4f03d9048f1c1ddba3dd2e3d5aa6296ebba837ea24b6e00d1a923`
  - `summary.md` `7d2a345431f855ca4f3a82e9e890d498b5fb1a0b7832cd17bf310f423e0dbc6c`
- **Provider-reported answer model:** stored from v5.2.4 on, so it's available for the 25 recovered
  results. It wasn't stored for the 11 carried-over results.
