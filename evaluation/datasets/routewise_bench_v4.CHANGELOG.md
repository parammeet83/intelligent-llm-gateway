# routewise_bench_v4 — Changelog

**2026-11-04.** Created from `routewise_bench_v3` after the owner's independent human review of v3. v1, v2 and v3, their pre-registrations and the v3 manifest are byte-for-byte unchanged.
No model or provider was called and no benchmark was run. v4 is **not reviewed**: `reviewed_by` is empty. No linguistic (native-speaker) validation has been performed for any case.

| Artifact | SHA-256 |
|---|---|
| `datasets/routewise_bench_v4.jsonl` | `715830467f26d833142b073497f2f7fd47cca0f9fa11cc2f7feabc5773987016` |
| `preregistration_routewise_bench_v4.yaml` | `0752a36358c2aebb2e4985bb3b188ea1b4406f9de2fa5f623b4e5b736219698a` |
| `experiment_manifest_routewise_bench_v4.yaml` (schema 2) | `4817aee4d71bc15e8fb6d8b3150fb840fab1a6b845694181e9f1d3b82f53c0c3` |
| `datasets/routewise_bench_v3.jsonl` (unchanged) | `c0c58c306cd18671e70e40aeab7bbae8672428369bbbe2cbb140144bc61119c7` |

Pinning chain: the meta file pins the pre-registration; the pre-registration pins the dataset and the manifest; the manifest pins configuration, all execution-critical code, and pacing. The runner and `eval-run` check every link and the live configuration before any network call.

## Dataset corrections (review items 1–4)

| Case | Change | Detail |
|---|---|---|
| T03 | prompt improved | Scoring unchanged from v3. The prompt now gives a valid JSON example structure whose values are placeholders (`"HH:MM"`, `"<day name>"`, `0`, …), and lists the permitted values of each key separately (format of `start_time_utc`, day names, one-word feature, integer types, the closed `root_cause` list, an integer without `%`). Copying the placeholder example scores as wrong (tested). |
| T04 | prompt improved | Scoring unchanged from v3. The prompt now gives a valid JSON example with two records (one showing a team owner and a date, one showing `null` for both), and lists permitted values separately: the four topics, a lowercase team name or `null`, and an ISO date or `null`. The rules are stated on their own: one record per decided topic, and omit undecided topics. Copying the example scores as wrong (tested). |
| T10 | strict final answer | v3 took the first number on the ANSWER line, so `7 (indentation)` and `7 or 6` passed. v4: `strict_number`, so the ANSWER value must be exactly one number with no prose. The prompt now says "containing only the number (no words, units or notes)". |
| T17 | replaced with multiple choice | v3's accepted-translation list had not been validated by a native speaker. v4 asks which of four printed translations is correct. B (*La biblioteca abre a las nueve en punto*) is the literal, complete translation. Each distractor changes exactly one content word: A *cierra* (closes), C *diez* (ten), D *librería* (bookshop, a false friend of "library"). The answer goes on an `ANSWER:` line as the letter only. Correctness rests on these word meanings, not on stylistic judgement. **No native-speaker validation has occurred**, and none is claimed. Category → `translation_choice`; task_type → `qa`. |
| C01 | strict final answer | v3's pattern `12:00\s*\W*\s*$` accepted any answer ending in 12:00, including "Not 12:00" and "The train does not catch A at 12:00". v4 requires an `ANSWER:` line whose whole value is exactly `12:00` (exact match). The prompt was updated accordingly. |
| C03 | strict final answer | As T10: first-number scoring → `strict_number`. `11 (sum of gaps)` and `11, not 12` now fail. |
| C08 | strict final answer | As T10. `328 (sum of 15 primes)` and `328 or 329` now fail. |
| C09 | strict final answer | As T10. `$1,157.63` still passes; `1157.63 (rounded half up)`, `1157.63 USD` and `1157.63 or 1157.62` now fail. Round-half-up and the ±0.0001 tolerance are unchanged from v3. |

Distribution preserved: 15 simple / 18 standard / 12 complex (item 10). Complexity labels are unchanged; rationale per case is in the review pack.

Evidence: `test_v3_false_passes_are_fixed_in_v4` runs each wrong answer against the **v3** rule (it passes) and the **v4** rule (it fails): `Not 12:00` and `The train does not catch A at 12:00` (C01), `7 or 6` (T10), `11, not 12` (C03), `328 or 329` (C08) and `1157.63 or 1157.62` (C09). No final-answer numeric case uses first-number scoring any more (tested).

## Scorer addition (opt-in; v1–v3 scoring unchanged)

- `numeric.strict_number`: the value must fully match one number. Allowed: an optional leading `$`, an optional sign, correctly grouped thousands commas, decimals, and one trailing full stop.

## Experiment design (items 5–9, 11)

- **Item 5, baseline name:** investigated, and kept as `baseline_premium` because premium-only generation **is** guaranteed. `preferred_tier=premium` raises the required tier to premium (`_required_tier`); `allow_downgrade` is never set; the router excludes every model below the required tier (`TIER_TOO_LOW`); and the executor only iterates `decision.eligible`. A test routes all 45 v4 prompts with Groq only and with Groq + OpenRouter, and every eligible model is premium. The report enforces it too (`baseline_tier_guard: premium_only`): any baseline attempt outside the premium tier invalidates the run. Renaming would be a one-line change if you prefer the longer name anyway.
- **Item 6, models and attempts:** each case outcome now records:
  - `answer_model`: the model ID reported in the provider's response body (exposed in the API as `provider_reported_model`)
  - the registry model and tier
  - `attempts`: every provider call, with provider, model, tier, reason code, status, error code and latency, including the attempts of failed requests

  These are written to `results.jsonl`. Per-strategy answering-model, attempted-model and attempt-status distributions appear in the summary and the Markdown report.
- **Item 7, conditional pass rates:** `pass_rate_basis: conditional_on_answer_returned`. `answered`, `answer_rate`, `failures` and `failure_codes` are reported separately per strategy, and `pass_rate_unconditional` is shown for transparency. The Markdown report labels the column and explains the basis. The pre-registration requires quoting the conditional label together with the answer rate.
- **Item 8, manifest coverage (schema 2):** the manifest now hashes:
  - the routing engine, features and config
  - the provider interface (`providers/base.py`) and the HTTP adapter with token-usage extraction (`providers/http.py`)
  - the enabled provider's adapter (`providers/groq.py`), the provider registry and the catalog loader
  - the executor (retries, backoff, fallbacks, budget cap), gateway pipeline and factory
  - health and circuit breaker, cost and budget accounting, rate limiting
  - API schemas and settings
  - all evaluation code: scorers, report, runner, loader, statistics and the manifest module itself

  Hashes are taken over LF-normalised text. The v3 manifest keeps schema 1, its original file list, unchanged.
- **Item 9, pacing:** `execution.pacing` pins `concurrency: 1` (the runner is strictly sequential, now a named constant `RUN_CONCURRENCY`), `delay_s: 6.0` after every request, `limit_cases: null` and `allow_code_exec: false`. `eval-run` passes its actual `--delay-s`, `--limit` and `--allow-code-exec` values and is refused on any difference, before any network call. A CLI test proves it: the catalog refresh is never reached. 6 s was chosen from Groq's published base limits for gpt-oss (30 RPM, 8K TPM); it isn't measured.
- **Item 11:** prereg-v4 was written before any v4 run. prereg-v1, -v2 and -v3 are unchanged.

## Consequence for v3 (by design)

v4 changed evaluation code that the v3 manifest pins (`scorers.py`, `report.py`, `runner.py`). v3 therefore **can no longer be run** on current code: the runner refuses it with a file-hash mismatch, which is the intended fail-closed behaviour of a pinned manifest. The v3 files themselves are unchanged. Its test now asserts that every non-code field still matches, and that the only differences are code-file hashes.

## Action needed before a live run

- In `.env`, set `MOCK_PROVIDER_ENABLED=false` (the manifest pins a Groq-only configuration).
- Run `uv run python -m app.cli eval-run --dataset routewise_bench_v4 --label <label> --delay-s 6`. Any other `--delay-s`, any `--limit`, or `--allow-code-exec` is refused.

## Tests (item 8 of deliverables)

`backend/tests/evaluation/test_dataset_v4.py` contains:

- reference pairs for all 45 cases, plus v3's adversarial answers carried over wherever scoring is unchanged
- positive, negative and adversarial answers for every correction, including both C01 examples from the review
- v3-vs-v4 false-pass evidence, and a check that no first-number scoring remains
- strict-number format tests
- T17 multiple-choice structure (four distinct options; only B passes)
- T03/T04 example-JSON validity, and that copying a placeholder example fails
- the baseline premium-only guarantee across all 45 prompts
- the pre-registration and manifest chain
- pacing-drift refusal (delay, limit, concurrency, code execution), and code-drift detection for each execution-critical component
- the CLI refusing mismatched pacing before any network call
- report availability and conditional pass rate, the baseline tier guard, and runner attempt recording (mock provider, scratch database)
