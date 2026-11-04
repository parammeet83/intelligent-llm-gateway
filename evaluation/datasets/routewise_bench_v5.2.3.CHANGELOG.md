# routewise_bench_v5.2.3 — Changelog (execution-schedule amendment)

**Registered 2026-11-04T18:25:33Z** (system clock), before any run. v5.2.3 changes only *when* the
registered comparison runs. The dataset, prompts, expected answers, scoring (including the v5.2.1
amendment), the review-attestation gate, the quota guard and every quality, cost, scope, validity
and statistical rule are unchanged from v5.2.2. No provider was called and no benchmark was run.

## Why

The worst case of the registered comparison is **583,738 tokens**:

| Model | Max attempts | Input bound | Output bound | Worst-case tokens |
|---|---|---|---|---|
| `openai/gpt-oss-120b` | 270 | 141,762 | 304,128 | **445,890** |
| `openai/gpt-oss-20b` | 108 | 53,880 | 83,968 | **137,848** |
| Total | 378 | 195,642 | 388,096 | 583,738 |

The observed Groq limits are 200,000 tokens per day, 8,000 tokens per minute and 1,000 requests
per day, per model. The registered guard (unchanged) caps all Groq models together at 90% of the
operator-supplied daily budget, so one day holds at most 180,000 tokens.

- **Minimum under the unchanged guard:** ⌈583,738 / 180,000⌉ = 4 days.
- **Three days:** fit each model separately (120B ≤ 152,868 per day) but not the shared cap
  (about 194,000 per day). They would need a per-model guard, a change to safety-critical code,
  which wasn't made.

## Schedule (`execution_schedule_routewise_bench_v5.2.3.yaml`)

The allocation uses no outcome data:
- stratified by difficulty
- shuffled with seed 20261104
- assigned to the least-loaded day

It is reproducible by a test.

| Day | Cases | Requests | Max attempts (120B / 20B) | Worst-case tokens (120B / 20B) | Remaining needed (÷ 0.9) |
|---|---|---|---|---|---|
| 1 | S05 S08 S11 T03 T06 T16 T17 C03 C10 C11 | 30 | 88 (60 / 28) | 146,532 (107,652 / 38,880) | 162,814 |
| 2 | S06 S07 S14 T02 T08 T09 T14 T15 T18 C01 C06 C08 | 36 | 96 (72 / 24) | 144,678 (115,962 / 28,716) | 160,754 |
| 3 | S02 S03 S09 S10 T05 T07 T11 T13 C07 C09 C12 | 33 | 94 (66 / 28) | 141,972 (104,448 / 37,524) | 157,747 |
| 4 | S01 S04 S12 S13 S15 T01 T04 T10 T12 C02 C04 C05 | 36 | 100 (72 / 28) | 150,556 (117,828 / 32,728) | 167,285 |

Rules (registered in the schedule and the pre-registration):
1. Each case's three strategies run on the same day, in the registered interleaved order.
2. Days run in order on distinct UTC dates, with day 4 at most 14 days after day 1.
3. Each day runs exactly once. Nothing is re-run or excluded. A stopped or incomplete day makes the
   whole comparison incomplete.
4. On each run day, read both models' remaining daily tokens in the Groq console and supply the
   smaller one. The day's preflight must pass.
5. Start at least 2 hours before 00:00 UTC.
6. Both model IDs must stay listed and unchanged across the schedule.
7. The registered analysis is `eval-combine` over all four day reports. Per-day figures are
   descriptive only.

## Code (pinned in the v5.2.3 manifest)

- `dataset.py`: `load_execution_schedule` verifies the hash pin, the dataset, days numbered 1..4,
  every case exactly once and dataset order; duplicate YAML keys are refused. `schedule_day_cases`
  keeps each case's dataset index.
- `runner.py`: `schedule_day` runs one registered day. The preflight covers that day's cases. The
  snapshot records the schedule hash, day, case IDs and UTC date.
- `cli.py`: `--schedule-day` for `eval-validate` (preflight per day) and `eval-run` (required with a
  schedule, checked before any network call). `eval-combine` pools the days.
- `report.py`: `combine_scheduled_reports` refuses a missing or duplicate day, another
  registration, other cases, a non-distinct or out-of-order date, or a differing amendment,
  attestation or simulated status. A span violation, a missing result or an incomplete day makes the
  pooled comparison incomplete; nothing is dropped.
- `manifest.py`: the schedule is a schema-6 evidence file.

Tests: `test_execution_schedule_v5_2_3.py` (50 tests). `conftest.py` now also marks v5.2.2's five
manifest-match tests as strict xfail.

## Chain

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.3.revision.yaml` | `70f0059153b4f66c90780cfbc9d6dad115ad87e629851b170b788fe9f005c4a8` |
| `evaluation/preregistration_routewise_bench_v5.2.3.yaml` | `116111218e212ea4470c3f25d59f525cac00ff31714f34ce7deb3b5b8c7d68e7` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.3.yaml` | `66ecc8556b57263a208916064af5875d14f14b4677d29e61bdaaff589acda4bc` |
| `evaluation/execution_schedule_routewise_bench_v5.2.3.yaml` | `c74699c11ec73ef08e0d883fedf7ffe5b5bc996c84de8ba9abbb0207b94756e6` |

v5.2.2 (`66320623…`, `2c8f76fb…`, `de0117ca…`) and every earlier artefact are byte-identical.
