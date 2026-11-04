# RouteWise v5.2.2 — Publication-gate amendment review report

Written for an independent reviewer. No benchmark result is reported: no benchmark has been run.

## 1. Problem

The publication gate (`report.py`: `publishable` requires `dataset_fully_reviewed`) used only
`reviewed_by` in the immutable v5 metadata, which is empty. The owner's review was recorded in a
separate attestation, which no code read. Worse, the metadata wasn't covered by any registered
hash, so editing `reviewed_by` would have opened the gate with no chain failure.

## 2. Fix

- **Two pins.** The v5.2.2 pre-registration pins both the metadata (`262dde03…`) and the
  attestation (`b7099444…`) by raw SHA-256. The schema-6 manifest pins them again as evidence
  files, together with the dataset and the scoring amendment.
- **Overlay.** `apply_review_attestation` verifies every claim in the attestation against the
  actual files (the changelog lists all checks) and returns a copy of the dataset with
  `attested_case_ids` set. `Dataset.reviewed_case_ids` is the metadata's `reviewed_by` keys plus
  `attested_case_ids`.
- **Fail closed.** Any inconsistency refuses the run before any network call.
- **Provenance.** The attestation's hash, reviewer role, review methods and the T17 disclosure
  are stored in every run snapshot and shown in the report.

## 3. T17

The owner checked the Spanish options using Google Translate; the correct answer is B, "La
biblioteca abre a las nueve en punto." This is recorded, verified and reported as
**translator-assisted owner review**. The loader refuses any version that claims native-speaker
or independent linguistic validation, or assigns the method to another case.

## 4. Verification

| Check | Result |
|---|---|
| `test_publication_gate_v5_2_2.py` | 60 passed |
| Full backend suite (Python 3.12.10) | 1,463 passed, 91 skipped (PostgreSQL-only; they run in CI), 12 strict xfails |
| Ruff, ruff format, mypy (strict) | clean |
| Frontend lint, typecheck, unit tests, build | clean; 28/28 unit tests |
| Playwright | 9 passed, 1 skipped (mobile-only test on desktop) |

The 12 strict xfails are the four manifest-match tests each of v5.1, v5.2 and v5.2.1. They must
fail, which proves those revisions are refused.

The new tests cover:
- the valid attestation and the overlay, with no mutation of the dataset or metadata
- tampered bytes
- wrong dataset, metadata or amendment hashes
- a missing, extra or duplicate case
- a wrong case-line hash
- a missing, rejected or pending approval
- a wrong reviewer
- wrong S15/T11/C12 amendment references
- T17 method or disclosure changes
- a wrong creation time or identity, and wrong v5.2.1 references
- modified metadata, dataset or amendment, which the loader refuses and the manifest also refuses
- a round-trip control
- report provenance and the T17 disclosure
- the gate failing closed without the attestation
- the CLI rejecting an attestation path
- refusal of historical revisions
- the runner applying the overlay

## 5. Preflight (recomputed from the implementation)

- 135 gateway requests.
- At most 378 provider attempts.
- Worst-case reservation of 583,738 tokens.
- The run therefore needs at least 648,598 operator-verified remaining daily tokens on the run
  day, because of the 0.9 safety factor.
- Requests: 900 usable per day.
- Pace: at least 97.3 minutes by tokens per minute, and 37.8 minutes by requests per minute.
- Without a verified daily budget the preflight fails closed.

## 6. Limitations

- The attestation records the owner's statements; the recorder did not review the cases.
- T17 has no native-speaker or independent linguistic validation.
- Publication still also requires a non-simulated, complete and valid run.
