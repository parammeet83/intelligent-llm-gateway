# routewise_bench_v5.2.1 — Changelog (scoring amendment)

**2026-11-04 (registered 2026-11-04T14:22:54Z, from the system clock).** v5.2.1 is a narrow
scoring amendment of execution revision `routewise_bench_v5.2` for the **unchanged** dataset
`routewise_bench_v5`. It implements the three conditions from the project owner's human review
(recorded outside this repository; this changelog is not a sign-off) and changes nothing else. No
provider was called, no benchmark was run, `.env` was not changed, and nothing was committed,
pushed or deployed.

## The three scoring corrections

| Case | Review condition | Before (v5.2) | After (v5.2.1) |
|---|---|---|---|
| S15 | `age` must be a JSON integer | `age` compared numerically, so `34.0`, `3.4e1` and `340e-1` passed | `field_types: {age: integer}` is added; `34` passes, and any float, string, boolean or null fails |
| T11 | Number only; no currency symbols | `currency_symbols: ["$"]`, so `$33` passed | `currency_symbols: []`; only the bare number passes (`33`, `33.`, `33.00`, or with markdown emphasis) |
| C12 | Strict `HH:MM` | Each start time was split on `:` and passed to `int()`, so `9:30`, ` 09:30`, `+9:30` and non-ASCII digits passed | New validator `meeting_schedule_hhmm`: every start must be a JSON string matching `HH:MM` exactly (ASCII digits, 00–23 and 00–59). The schedule constraints are unchanged |

**T17** (pending Spanish-speaker validation) and every other case are scored exactly as the
dataset file specifies. The dataset metadata still has no `reviewed_by` entries, so the
publication gate is unchanged: no run is publishable.

## How it works

- **Separate amendment file.** `evaluation/scoring_amendment_routewise_bench_v5.2.1.yaml` holds
  each case's original spec and its amended spec. The dataset JSONL isn't touched.
- **Checks before use.** At run time, `apply_scoring_amendment` (in `app/evaluation/dataset.py`)
  refuses to proceed if any of these fail:
  - the amendment's SHA-256 matches the pre-registration
  - the amendment names the dataset and its hash
  - the amendment names the corrected v5.2 revision file and its hash
  - every listed original spec matches the dataset exactly
  - every listed case exists
- **Applied to a copy.** The amended specs replace the originals in an in-memory copy of the
  dataset. The dataset's recorded SHA-256 stays that of the unchanged file.
- **Where it runs.** `eval-run` checks the amendment before any network call. `run_benchmark`
  applies it and records `scoring_amendment` (file, hash, cases) in each run's config snapshot.
  `eval-validate` reports it.

## Changed files

| File | Change | SHA-256 before (v5.2 pin) → after (v5.2.1 pin; LF-normalised) |
|---|---|---|
| `backend/app/evaluation/scorers.py` | Adds `meeting_schedule_hhmm` and an opt-in `strict_hhmm` flag; `meeting_schedule` is unchanged | `009ae786…` → `1f32a371…` |
| `backend/app/evaluation/dataset.py` | Adds `apply_scoring_amendment` | `e5650a03…` → `465b5049…` |
| `backend/app/evaluation/runner.py` | Applies the amendment and records it in the snapshot | `8e2d9d67…` → `137e4072…` |
| `backend/app/cli.py` | `eval-validate` reports the amendment; `eval-run` checks it before any network call | `cbae8426…` → `16caf557…` |
| `backend/tests/evaluation/conftest.py` | Also marks the four v5.2 manifest-match tests as strict xfail | `ea6b46b9…` → `77cb9532…` |

The full before and after hashes are in the review report.

New files:
- `backend/tests/evaluation/test_scoring_v5_2_1.py`
- `evaluation/scoring_amendment_routewise_bench_v5.2.1.yaml`
- `evaluation/experiment_manifest_routewise_bench_v5.2.1.yaml`
- `evaluation/preregistration_routewise_bench_v5.2.1.yaml`
- `evaluation/routewise_bench_v5.2.1.revision.yaml`
- this changelog and the review report

## v5.2.1 chain (root first)

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.1.revision.yaml` | `42666d44eddac1a1b9395384ba92183be0f7025ac91d867e7261b64af265a6e7` |
| `evaluation/preregistration_routewise_bench_v5.2.1.yaml` | `2a78174bc1ebd7ea78e692d31ca1097623dd6edd144416a486fcdc15f5db9070` |
| `evaluation/scoring_amendment_routewise_bench_v5.2.1.yaml` | `bab04a1a24f2f7d52538d49472edd52579ce08ded0ed10460225498b4a4c8431` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.1.yaml` | `dd6b29f870abf4b93fa7b21fba007ac05d115496bad30568414f16ab125b850e` |

The links run as follows:
- **Revision** pins the pre-registration and the amendment, and names the amended v5.2 revision
  (`59257813…`) and the dataset (`76a4d190…`).
- **Pre-registration** pins the dataset, the amendment and the manifest.
- **Amendment** pins the dataset and the v5.2 revision.
- **Manifest** is schema 5: the same configuration, pacing and quota as v5.2. Only the four
  changed files' hashes differ.

Select it with `--revision routewise_bench_v5.2.1`. Every other part of prereg-v5.2 is carried over
unchanged. The generator checked this by comparing the parsed files: only version, dates,
revision, supersedes, amends_revision, the manifest reference, the amendment reference, the
change list and the preflight sentence differ. v5.2's own `registration_correction` block isn't
carried over; it documents the v5.2 date erratum.

## v5.2 is preserved and now refused

The corrected v5.2 chain (revision `59257813…`, pre-registration `2c713e73…`, manifest
`00302285…`), its superseded first issue, the v5 dataset and every earlier artefact are
byte-identical. `test_execution_v5_2.py` is unchanged. Its four tests asserting that v5.2's
manifest matches the code are now strict xfail, so they must fail; v5.2 is refused before any
network call. Its other tests pass unchanged.
