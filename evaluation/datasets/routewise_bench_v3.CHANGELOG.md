# routewise_bench_v3 — Changelog

**2026-11-04.** Created from `routewise_bench_v2` after the owner's independent review of the v2 files. v1, v2 and their pre-registrations are unchanged.
No model or provider was called and no benchmark was run. v3 is **not reviewed**: `reviewed_by` is empty.

| Artifact | SHA-256 |
|---|---|
| `datasets/routewise_bench_v3.jsonl` | `c0c58c306cd18671e70e40aeab7bbae8672428369bbbe2cbb140144bc61119c7` |
| `preregistration_routewise_bench_v3.yaml` | `c3172bd6a0bd32bae01910b025706668d2f2cd00f1bf63043ecd4eba264aeaea` |
| `experiment_manifest_routewise_bench_v3.yaml` | `de45f809f0e0673c76d878dc09921f85fc576f768b6c921b20f6916f7c160f8f` |
| `datasets/routewise_bench_v2.jsonl` (unchanged) | `614e14497b380539baed24ad87f3619e11107d2adc35230004b652dec6994550` |

Pinning chain: the meta file pins the pre-registration; the pre-registration pins the dataset and the manifest; the manifest pins the configuration and code files. The runner checks every link and the live configuration before any network call.

## Dataset corrections (review items 1–7)

| Case | Change | Detail |
|---|---|---|
| T03 | replaced scoring + prompt | v2: keyword checks (`disk`, `45`, `alert`) + word/sentence caps. Keywords pass negated or unrelated text ("Disk not full; 45 people; no alert."), and the sentence counter split at abbreviations. v3: extraction of six facts to typed JSON, each checked exactly (`start_time_utc`, `day`, `affected_feature`, `duration_minutes`, `root_cause` from a closed list, `alert_threshold_percent`). Category summarization → extraction; response format text → json. The abbreviation-aware sentence counter is also implemented (opt-in `sentence_rules: abbreviation_aware`) and tested, but no v3 case needs sentence counting. |
| T04 | replaced scoring + prompt | v2: required dates and "press release" as keywords, so swapped owners passed ("Engineering owns the press release"). v3: keyed JSON records `{topic, owner, date}`, with `exact` keys (exactly launch_date, press_release, feature_freeze; pricing excluded), no duplicates, each owner and ISO date checked (launch owner must be null). Years added to the notes so ISO dates are well-defined. Category summarization → extraction. |
| T07 | rewritten as pure instruction compliance | v2 still described the target as "polite and professional" without evaluating it. v3 states five explicit rules and scores only those: starts with the word "Please", contains the words "the report" (whole words), not the words "now"/"late", ≤ 15 words, ends with ".". Category → `instruction_following`. Tone and writing quality are explicitly **not** evaluated. |
| T12 | scoring fixed | v2 pattern `^5\s*/\s*36\b` accepted trailing wrong text ("5/36 or 1/6"). v3 anchors the whole value: `^5\s*/\s*36\.?$`. |
| T17 | scoring replaced | v2 keyword groups accepted negation ("no abre") and scrambled order. v3 uses exact match against 8 accepted translations (normalised for case, surrounding whitespace and final punctuation). The list was compiled by the AI drafter, **not by a native speaker**; please validate it. Any valid translation that isn't listed fails (a known false-negative risk, accepted in exchange for no false positives). |
| C07 | scoring fixed | v2 summed quantities per SKU, so unmerged duplicate entries passed. v3 requires exactly two unique SKU records (SKU-118 ×5, SKU-204 ×5), no duplicates, no extra SKUs, integer quantities, plus customer and total_units 10. The prompt now says each SKU must appear exactly once. |
| C09 | prompt + scoring fixed | The prompt now specifies round-half-up. The exact value 1000 × 1.05³ = 1157.625 gives 1157.63 half-up and 1157.62 half-even (checked with Python `decimal`). The tolerance is tightened from ±0.006 (which accepted the unrounded 1157.625) to ±0.0001. |

Distribution preserved: 15 simple / 18 standard / 12 complex (item 13). The complexity labels of the changed cases are unchanged; the rationale is in the review pack.

Evidence: `test_v2_false_passes_are_fixed_in_v3` runs each wrong answer against the **v2** rule (it passes) and the **v3** rule (it fails), for T04 (swapped owners), T12 (`5/36 or 1/6`), T17 (negation and scrambled order), C07 (unmerged duplicates) and C09 (unrounded 1157.625). T03's keyword weakness is covered by adversarial tests (negated keywords and prose fail the JSON rule).

## Scorer additions (opt-in; v1 and v2 scoring unchanged, guarded by their test suites)

- `json.list_records`: keyed records with per-field equality, duplicate rejection, and `exact` key sets.
- `contains.starts_with_word` / `contains.ends_with`: answer-level start and end rules.
- `contains.sentence_rules: abbreviation_aware`: sentence counting that ignores full stops in common abbreviations (e.g., i.e., etc., Dr., a.m., …) and initials. Known limit: a sentence that genuinely ends with such an abbreviation followed by a capitalised word is merged with the next one. No v3 case relies on sentence counting.

## Methodology changes (items 9–12, 14)

- **Item 9, cost claims:** a lower-cost claim needs **CI-supported** quality non-inferiority (paired bootstrap lower bound above −5 pp), not just a point estimate (`cost_rule.requires_ci_supported_non_inferiority: true`). The report enforces it and lists `cost_rule_blocked_reasons`.
- **Item 10, unknown cost:** an unknown cost observation is any request with unavailable list cost, including every request that returned no answer. These are counted per strategy (`unknown_cost_observations`), never treated as zero or imputed, and any non-zero count blocks the cost claim (`unknown_cost_observations: block`).
- **Missing vs failed:** provider errors are excluded from the pass-rate denominator and from the paired comparison (`run_validity.provider_errors: missing`). prereg-v2 already said this in prose, but the report code counted errors as failures. v3 makes the rule machine-readable and enforced; v2's pre-registration is left untouched.
- **Item 11, experiment manifest:** `experiment_manifest_routewise_bench_v3.yaml` (new module `app/evaluation/manifest.py`) records LF-normalised SHA-256 hashes of the routing policy, model registry, scorers, report, runner and dataset loader, plus:
  - the full routing policy, including weights
  - each enabled model's provider model ID, tier, reasoning effort and pricing snapshot
  - provider retries and charge basis
  - execution settings (deadline, timeouts, backoff, circuit breaker, enabled providers, Groq plan, paid-model block, catalog check), temperature and strategies

  `eval-run` and the runner refuse any difference before any network call. A run answered by a model outside `expected_models` is invalid. The code is uncommitted, so file hashes identify its version rather than a git commit.
- **Item 12, scope:** `scope.generalisation` states that results apply only to this fixed suite and configuration and can't establish general production performance. Publication requires stating it next to any result.
- **Item 14:** prereg-v3 was written before any v3 run. prereg-v1 and prereg-v2 are byte-for-byte unchanged.

## Action needed before a live run

The manifest pins the intended live configuration: Groq only, with the mock provider disabled. The current local `.env` has `MOCK_PROVIDER_ENABLED=true`, so `eval-validate --dataset routewise_bench_v3` reports a manifest mismatch until you set it to `false`. This is the intended fail-closed behaviour.

## Tests (item 8)

`backend/tests/evaluation/test_dataset_v3.py` contains:

- reference pairs for all 45 cases
- positive, negative and adversarial answers for each of the seven corrections
- v2's adversarial answers, carried over for every unchanged case
- v2-vs-v3 false-pass evidence
- sentence-counter tests
- pre-registration and manifest pinning, plus configuration-drift tests (mock enabled, deadline, backoff, strategies, retries, file contents, edited manifest, line endings)
- report-rule tests on synthetic outcomes (errors as missing, CI-gated cost claim, unknown-cost blocking for unpriced and failed requests, off-manifest model)
