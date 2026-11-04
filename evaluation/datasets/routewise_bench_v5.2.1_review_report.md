# RouteWise v5.2.1 — Scoring amendment review report

Written for an independent reviewer. No benchmark result is reported: no provider was called and no
benchmark was run. The human review decisions this implements were recorded by the project owner
outside this repository. This report is not a sign-off and marks no case as reviewed.

## 1. Scope

There are exactly three scoring corrections, one per conditional approval: **S15**, **T11** and
**C12**. Nothing else changes:
- **Not changed:** the dataset file, prompts, expected answers, metadata, and the scoring of the
  other 42 cases.
- **Not changed:** execution, quota, quality, cost, validity and publication rules.
- **T17** (pending) is unchanged.

## 2. Behaviour before and after

| Case | Example output | v5.2 | v5.2.1 |
|---|---|---|---|
| S15 | `{"name": "Priya", "age": 34}` | pass | pass |
| S15 | `{"name": "Priya", "age": 34.0}` / `3.4e1` / `340e-1` | **pass** | fail |
| S15 | `"34"`, `true`, `null`, `[34]`, `34.5` | fail | fail |
| T11 | `33`, `33.`, `33.00`, `**33**` | pass | pass |
| T11 | `$33`, `$33.00`, `**$33**` | **pass** | fail |
| T11 | `USD 33`, `€33`, `33$`, `$ 33`, `33 dollars`, `3.3e1` | fail | fail |
| C12 | `{"A": "09:30", "B": "10:30", "C": "09:00"}` | pass | pass |
| C12 | `"9:30"`, `" 09:30"`, `"09:30 "`, `"+9:30"`, Arabic-Indic or fullwidth digits | **pass** | fail |
| C12 | `"09:30:00"`, `"0930"`, `"09.30"`, `9.5`, `"24:00"`, `"09:60"` | fail | fail |
| C12 | A valid format but an invalid schedule (overlap, B before A, C after 10:00) | fail | fail |

Each "v5.2 pass → v5.2.1 fail" row is a regression test that asserts both sides. So the tests show
the defect existed under the original spec, as well as showing the fix.

## 3. Design

- **Amendment file.** Each entry lists the case's `original_scoring`, copied verbatim from the
  dataset file by the generator, and its `amended_scoring`. Loading fails if any of these don't
  match:
  - the file's SHA-256 against the pre-registration
  - the dataset name and hash
  - the hash of the corrected v5.2 revision it amends
  - each original spec against the dataset
  - each case ID against the dataset

  An amendment therefore can't silently apply to another dataset version, or to a case whose spec
  has since changed.
- **Applied to a copy.** The specs are replaced in a copy. The loaded `Dataset` isn't mutated
  (tested), and the dataset's SHA-256 stays that of the unchanged JSONL.
- **Existing scorer features where possible.**
  - S15 uses `field_types` (already used by other v5 JSON cases).
  - T11 uses `currency_symbols: []` (already used by v5 non-currency cases).
  - Only C12 needed new code: `meeting_schedule_hhmm` reuses `meeting_schedule` with an opt-in
    strict check, so the original validator's behaviour is unchanged (tested).
- **The time pattern.** `(?:[01][0-9]|2[0-3]):[0-5][0-9]`, applied with `fullmatch`. It uses
  `[0-9]`, not `\d`, so non-ASCII digits fail. `fullmatch` means a trailing newline fails.
- **Fail before any network call.** `eval-run` checks the amendment before anything is sent.
  `run_benchmark` applies it before the manifest check and records it in the run snapshot.
- **DB acceptance spec.** The case rows' `acceptance.scoring` are written from the dataset the run
  uses, so a v5.2.1 run stores the amended specs for S15, T11 and C12.

## 4. Verification performed

- **Full backend suite (Python 3.12.10, pinned environment):**
  - 1,407 passed, 91 skipped (PostgreSQL-only variants), 8 strict xfails (the superseded v5.1
    and v5.2 manifest-match tests).
  - Ruff check, ruff format and mypy (strict) are clean.
- **`test_scoring_v5_2_1.py`: 142 tests, all passing.**
  - Valid and invalid outputs for each of the three cases.
  - For all 42 other cases: an identical spec, and identical results on a fixed set of outputs
    plus each case's own expected text.
  - Tampering: an edited file, a wrong dataset or dataset hash, a wrong original spec, an unknown
    case, and a wrong v5.2 revision hash.
  - The chain, and the manifest matching the intended configuration.
  - `eval-validate` (amendment reported, 378 maximum attempts, fails closed without a budget;
    passes with one).
  - `eval-run` refusals: no budget, a tampered amendment, and v5.2, all before any network call.
  - The runner applying the amended specs.
- **Manifest validation** ran through the CLI under the intended configuration (placeholder key,
  network calls patched to fail). The live `.env` was not read for it.
- **Clean room:** the review bundle, extracted to an empty directory with a fresh `uv` environment
  built offline from the bundled lock file, runs the v5, v5.1, v5.2 and v5.2.1 test files. Results
  are in the hand-off report.

## 5. Hashes

### Changed application files (as pinned, LF-normalised)

| File | v5.2 | v5.2.1 |
|---|---|---|
| `backend/app/cli.py` | `cbae8426aa5995c1ef91636c86916e16c0e5cdeb4dc78e468a56a25e68a72ec2` | `16caf55739992b379966dac1facfa445e10601675ae539e14f065e26f1fe2233` |
| `backend/app/evaluation/dataset.py` | `e5650a03df30eb44e7e5afb0587a292f53c5b18dd56a7f6f1896bd789f184bf1` | `465b5049577737f1da6e6dd5e1cbd4f92577f317277944be7ba408fa8e3b6895` |
| `backend/app/evaluation/runner.py` | `8e2d9d67dd87a238e1b8c9ec5692d5a45fb5b4d354cc48649b7f544dd6e8f4fc` | `137e40725619d545f8113c336aeb6fa5802195aea614a9b711d363309901f1ea` |
| `backend/app/evaluation/scorers.py` | `009ae786c5d454fcca2150dc56121b69a26724c3e6b2baed66943e4e74da332a` | `1f32a37141c30c71e98e5504a54ee9218e3344ab105599bd04c55e0ca3fd9101` |

### Test infrastructure

| File | Before | After |
|---|---|---|
| `backend/tests/evaluation/conftest.py` | `ea6b46b9eaff5925c49c151eec79a9aa5725211b2f3f5b3de114af280e9cb140` | `77cb953255bd3fcea15116476c3220cd497158d84dbb6426309af9b2594a405b` |
| `backend/tests/evaluation/test_scoring_v5_2_1.py` | (new) | `7615943f81d497bc3e220ae660092a201f55ee3ada3e901cd3bd552732356aca` |

### Preserved, byte-identical

| File | SHA-256 |
|---|---|
| `evaluation/datasets/routewise_bench_v5.jsonl` | `76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd` |
| `evaluation/datasets/routewise_bench_v5.meta.yaml` | `262dde03c4018fe1f79c1fe8760f32cfcce3e1624284ea6b56eafed432806ada` |
| `evaluation/routewise_bench_v5.2.revision.yaml` (corrected) | `59257813e1093d512f0f6fb6459e8ee40aebede789d55908f661dca4bb06d347` |
| `evaluation/preregistration_routewise_bench_v5.2.yaml` (corrected) | `2c713e734ed418c31874cffec541831402dc689de56fab18f5c4643fb589976b` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.yaml` (corrected) | `00302285a3d2a1d5d35361fd8eede9065cfc774940e6ade022828c25089aef10` |
| `evaluation/datasets/routewise_bench_v5.2.ERRATUM.md` | `c43642bb49d4af5ca54a0cb6ac4eb79cb33cc6fd34dcc7e1ebce2cd35af522b6` |
| `evaluation/superseded/routewise_bench_v5.2_original_registration/*` | first issue: `a3e0c4b6…`, `41483ce6…`, `d3ff68dc…`, `3dc93704…`, `0bfc80c3…` |
| `backend/tests/evaluation/test_execution_v5_2.py` | `2bb0ecca5eeb435f3e2d3e9dbe196f65700235e8453e68758d79ec7e28e9c1a3` |
| `backend/tests/evaluation/test_execution_v5_1.py` | `7437323782960b2cce73e5734c068f2513e04e3669b893cc151047d8e30de25d` |

v1–v5.1 hashes are as listed in the v5.2 review report and are re-verified unchanged.

## 6. Limitations and notes

- **Pre-existing behaviour kept for other cases.** T11's strict-number check uses Python's `\d`,
  which accepts non-ASCII digits, so fullwidth `３３` passes. This behaviour is shared by every
  strict-number case, and it wasn't part of the agreed corrections. Changing it would change other
  cases, so it's unchanged and flagged here.
- **Extra JSON keys.** S15 and C12 still accept extra keys, as before. The conditions concerned the
  type of `age` and the time format only.
- **v5.2 is unrunnable on current code, by design;** use `--revision routewise_bench_v5.2.1`.
- **Not publishable yet.** Publication still requires `reviewed_by` entries in the immutable
  dataset metadata. None exist, and T17 is pending.
