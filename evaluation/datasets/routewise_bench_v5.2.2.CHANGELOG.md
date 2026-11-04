# routewise_bench_v5.2.2 — Changelog (publication-gate amendment)

**2026-11-04 (registered 2026-11-04T17:03:15Z, from the system clock).** v5.2.2 is an
administrative amendment of `routewise_bench_v5.2.1`. It changes only how the publication gate
establishes that the dataset is human-reviewed. The dataset, prompts, expected answers, scoring
(including the v5.2.1 amendment for S15, T11 and C12), execution, quota and every quality, cost,
scope and validity rule are unchanged. No benchmark has been run.

## The amendment

A case counts as human-reviewed if either:

1. it has a valid owner-reviewed entry in `reviewed_by` of the pinned v5 metadata (still empty), or
2. it is covered by the exact owner review attestation pinned in the pre-registration:
   `evaluation/reviews/routewise_bench_v5.2.1_HUMAN_REVIEW_ATTESTATION.yaml`, SHA-256
   `b7099444ac312eef336ebacbdb6e93335ba366f9de452be88cb17a97524c59ed` (9,279 bytes, unchanged).

The metadata (`262dde03…`) and the attestation are pinned twice: by raw SHA-256 in the
pre-registration, and as evidence files in the schema-6 manifest. The manifest also pins the
dataset and the scoring amendment. The gate builds an in-memory review overlay; the dataset and
metadata are never modified.

## What the loader verifies (`apply_review_attestation`, `app/evaluation/dataset.py`)

1. **Exact bytes:** the attestation's raw SHA-256 matches the pre-registration. Only the
   pre-registration can name an attestation; the CLI has no attestation option.
2. **Metadata:** the metadata file matches its pinned hash, and it is the metadata the dataset was
   loaded with.
3. **Identity and timing:** the attestation ID, reviewer role ("Project owner"), creation timestamp
   and the three owner confirmations are exactly as registered. Changing the timestamp counts as
   replacing the attestation; there is no time-based expiry.
4. **Dataset:** the dataset name, file and SHA-256 match the actual file, and the metadata hash it
   names matches.
5. **Scoring amendment:** its hash matches the registered amendment and the actual file, and its
   amended-case list equals the amendment's.
6. **v5.2.1 references:** the revision, pre-registration and manifest it names match the actual
   files.
7. **Cases:** all 45 IDs are present exactly once. Duplicate YAML keys are rejected, because
   PyYAML would otherwise keep the last one silently. No unregistered case is allowed.
8. **Decisions:** every case is explicitly approved. S15, T11 and C12, and only they, are
   `approved_after_scoring_amendment`, each with its exact amendment condition. Every
   `case_line_sha256` matches the case's exact dataset line.
9. **Review methods:** these are exactly as registered. T17 is
   `translator_assisted_owner_review`, and no other case has a method.
10. **T17 disclosure:** it names T17, says `none` for native or proficient speaker review and for
    independent linguistic validation, and gives correct answer B, which matches the dataset.
11. **Summary:** the counts match the decisions.

Any failure raises an error, and the run is refused before any network call (fail closed).
Without a pinned attestation, review status comes from the metadata alone, as before.

## Runtime and reporting

- **Snapshot.** `run_benchmark` applies the scoring amendment, then the attestation overlay. It
  records `review_attestation` in every run's config snapshot: the file, SHA-256, reviewer role,
  review methods and disclosures.
- **Report.** The report summary carries `execution_revision`, `scoring_amendment` and
  `review_attestation`. The Markdown report discloses: "T17: translator-assisted owner review
  (…Google Translate); no native-speaker or independent linguistic validation".
- **CLI.** `eval-validate` reports the attestation (45/45 reviewed) and the disclosure.
  `eval-run` validates both the amendment and the attestation before any network call.

## Changed files

The code files are pinned in the v5.2.2 manifest:
- `backend/app/evaluation/dataset.py`: review overlay, attestation loader, duplicate-key-safe YAML loader
- `backend/app/evaluation/manifest.py`: schema 6 (evidence files, paths relative to the evaluation directory)
- `backend/app/evaluation/runner.py`: applies the overlay and records provenance
- `backend/app/evaluation/report.py`: provenance in the summary, T17 disclosure in the Markdown
- `backend/app/cli.py`: `eval-validate` reporting; `eval-run` validates before any network call

Tests and test configuration:
- `backend/tests/evaluation/conftest.py`: marks the four v5.2.1 manifest-match tests as strict xfail
- `backend/tests/evaluation/test_publication_gate_v5_2_2.py` (new)

## v5.2.2 chain (root first)

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.2.revision.yaml` | `66320623bb6d6bc3518f6ebb5bf1b1c1e6c59830bca016d22639f33927de6bf7` |
| `evaluation/preregistration_routewise_bench_v5.2.2.yaml` | `2c8f76fbd3d6fa498d2922ee732481e0ea3f96e567d023228af403b972203b73` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.2.yaml` | `de0117cae450b4038b214857691ff8cdbc33bf201dc08b646bffbcbbe3ce8a20` |

The pre-registration differs from prereg-v5.2.1 only in version, timestamp, revision,
supersedes, amends_revision, the manifest reference, the new `dataset_metadata` and
`review_attestation` blocks, the change list, one preflight sentence and the publication rule.
This was checked by comparing the parsed files.

The chain was generated once before a test found that schema-6 evidence paths depended on the
checkout location, so a relocated copy failed on path rather than content. The code was fixed,
and the three unpublished chain files were deleted and regenerated from the final code. Only the
regenerated chain above exists.

## Preserved

These are byte-identical:
- v5 dataset `76a4d190…` and metadata `262dde03…`
- scoring amendment `bab04a1a…`
- attestation `b7099444…`
- v5.2.1 revision `42666d44…`, pre-registration `2a78174b…` and manifest `dd6b29f8…`
- the corrected v5.2 chain and its superseded first issue
- every v1–v5.1 artefact

v5.2.1, v5.2 and v5.1 are refused on current code, by design.
