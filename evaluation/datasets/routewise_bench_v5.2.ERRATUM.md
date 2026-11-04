# routewise_bench_v5.2 — Registration erratum

**Status:** the first issue of the v5.2 registration is **superseded because of a metadata error**.
**Correction date:** 2026-11-04. **Correction timestamp:** `2026-11-04T13:38:24Z` (UTC, read from the
system clock when the corrected registration was finalised). The corrected registration is **not**
backdated to the original files' creation time.

## What was wrong

The original v5.2 registration recorded the date **2026-11-05**, which was in the future when the
files were written. File-system timestamps show they were created and last written on
**2026-11-04, between 08:22:52 and 08:56:30 UTC** (13:52–14:26 India Standard Time, still 2026-11-04
locally). The system clock was synchronised with `time.windows.com` that day.

| File (first issue) | Erroneous text |
|---|---|
| `evaluation/routewise_bench_v5.2.revision.yaml` | `created_on: 2026-11-05` |
| `evaluation/preregistration_routewise_bench_v5.2.yaml` | `# Written on 2026-11-05 BEFORE any run.` and `registered_on: 2026-11-05` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.yaml` | `created_on: '2026-11-05'` |
| `evaluation/datasets/routewise_bench_v5.2.CHANGELOG.md` | `**2026-11-05.**` |
| `BUNDLE_INDEX.md` in `routewise_v5_2_review_bundle.zip` | `Generated 2026-11-05.` |

**Cause:** the date was typed by hand into the scripts that generated these files, instead of
being read from the system clock.

## What was not affected

- **No benchmark run.** Neither the original nor the corrected registration has been used for a
  benchmark run. No live benchmark of any version has been run, and no provider was called for this
  correction.
- **No logic change.** Code, tests, the dataset (`routewise_bench_v5`), prompts, expected answers,
  scoring rules, thresholds, the quota rules and all 54 manifest-pinned files are unchanged. The
  manifest's `pinned` section is identical to the first issue. v1–v5.1 artefacts are unchanged.
- **Real date unchanged.** v5.2 was written on 2026-11-04, the same day as v5.1 (07:29–07:37 UTC),
  about an hour later. It was never a day later.

## Superseded first-issue hashes

| Artefact | SHA-256 |
|---|---|
| Revision `routewise_bench_v5.2.revision.yaml` | `a3e0c4b64c01db4104bc084333f278b5f98acf7515761c9d7ea242e245253ee3` |
| Pre-registration `preregistration_routewise_bench_v5.2.yaml` | `41483ce611626eec22747dbfc0c85e72ac768d69e876c838e51bc600db4662df` |
| Manifest `experiment_manifest_routewise_bench_v5.2.yaml` | `d3ff68dc07e789451a89920ea0679a50d192423daf5ac0e3230e81c940ad7cbf` |
| Changelog `routewise_bench_v5.2.CHANGELOG.md` | `3dc937041476eee4157edafdae9162973cb9923414391a355efca59a10efcd26` |
| Review report `routewise_bench_v5.2_review_report.md` | `0bfc80c3fd0fa12c9d382d5200c43f121313cbef9595715f806c4519dc202d24` |
| Review ZIP `routewise_v5_2_review_bundle.zip` (317,336 bytes) | `35f80f730b790d7a81223ec4a4f5e87f65751f1634a385b15008e9bf14db6127` |

Byte-identical copies of the five files are kept in
`evaluation/superseded/routewise_bench_v5.2_original_registration/`. The original ZIP is kept
unchanged beside the project. The copies still refer to each other by their original file names,
which now hold the corrected chain, so the first-issue chain can only be checked against the hashes
above or inside the original ZIP.

## Corrected chain (re-issue)

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.revision.yaml` | `59257813e1093d512f0f6fb6459e8ee40aebede789d55908f661dca4bb06d347` |
| `evaluation/preregistration_routewise_bench_v5.2.yaml` | `2c713e734ed418c31874cffec541831402dc689de56fab18f5c4643fb589976b` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.yaml` | `00302285a3d2a1d5d35361fd8eede9065cfc774940e6ade022828c25089aef10` |

The revision pins the pre-registration, which pins the unchanged dataset
(`76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd`) and the manifest. This erratum
sits outside the chain, because it records the chain's own hashes.

### What changed in each re-issued file

- **Manifest:** `created_on` is now `2026-11-04`; `reissued_at_utc` was added; one note was added
  disclosing the correction. `pinned` is unchanged.
- **Pre-registration:** the header line and `registered_on` are now `2026-11-04`;
  `registered_at_utc` and a `registration_correction` block were added; the manifest hash was
  updated.
- **Revision:** `created_on` is now `2026-11-04`; `registered_at_utc` and a
  `registration_correction` block (with the superseded hashes) were added; the pre-registration
  hash was updated.
- **Changelog:** the date and the chain table were corrected, and a correction section was added.
- **Review report:** a correction note was added.

## Occurrences of 2026-11-05 left unchanged deliberately

- `backend/app/cli.py`: an example in the `--label` help text (`2026-11-05-live`). It isn't a
  registration date, and the file is manifest-pinned code.
- `backend/tests/evaluation/test_execution_v5_2.py`: an arbitrary timestamp in a test ledger record.
  It isn't a registration date, and no test validates registration dates.
- The preserved first-issue copies and the original ZIP, which must stay byte-identical.

## Known non-date wording error (not corrected)

The pre-registration's header comment says "What v5.1 is:", carried over from v5.1, where it
should say v5.2. It's a comment only and doesn't affect the chain or any rule. It was left as-is
because this correction is limited to the date error.

## How to verify (PowerShell, from the repository root)

```powershell
Get-FileHash evaluation\routewise_bench_v5.2.revision.yaml, evaluation\preregistration_routewise_bench_v5.2.yaml, evaluation\experiment_manifest_routewise_bench_v5.2.yaml -Algorithm SHA256
Get-FileHash evaluation\superseded\routewise_bench_v5.2_original_registration\* -Algorithm SHA256
Select-String -Path evaluation\routewise_bench_v5.2.revision.yaml, evaluation\preregistration_routewise_bench_v5.2.yaml -Pattern "sha256:"
```
