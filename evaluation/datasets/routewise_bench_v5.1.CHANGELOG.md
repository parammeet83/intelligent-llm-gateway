# routewise_bench_v5.1 — Changelog (execution-safety revision)

**2026-11-04.** v5.1 is an **execution revision** of the unchanged dataset `routewise_bench_v5`. It
changes how the benchmark would be executed (quota safety), not what it measures. No provider was
called, no benchmark was run, nothing was committed, pushed or deployed, and `.env` was not changed.

## Unchanged (immutable)

The v5 dataset JSONL, its 45 prompts, expected answers, metadata, review document and scoring rules
are byte-identical, as are all v1–v5 datasets, metadata, pre-registrations and manifests (hashes in
the review report). `routewise_bench_v5.meta.yaml` still pins `prereg-v5`. That pre-registration
loads, but is **refused at run time**: its manifest no longer matches the code, and its schema-3
quota is explicitly rejected.

**One v5 file was edited:** `backend/tests/evaluation/test_dataset_v5.py`. It isn't one of the
protected artefacts. Four tests that asserted v5's now-superseded execution behaviour were
changed to assert that v5 is refused:

- `test_v5_manifest_matches_the_intended_configuration`
- `test_v5_manifest_detects_quota_and_proxy_and_cli_changes`
- `test_runner_stops_incomplete_instead_of_exceeding_the_quota`
- `test_eval_validate_prints_the_quota_preflight`

All other v5 tests, including every scoring test, are unchanged. SHA-256 before
`bb0597e5ec9d1fcfbfe2abefb289d27f21deb995937e263325b6d2fc37113bc1`, after
`29b3fd666146872631774525e0dcd7458f3afd1c6192338e8b0d12ac92c438de`.

## New v5.1 artefacts (hash chain root first)

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.1.revision.yaml` | `903111c6ff27e7c1fa6cf9f59313847a26a7141973039ee9de1b3dc4f23cbb52` |
| `evaluation/preregistration_routewise_bench_v5.1.yaml` | `731fe50a02e2659d9884830c3450fd82bab0f5efa3155424a05f2951e75e5e0d` |
| `evaluation/experiment_manifest_routewise_bench_v5.1.yaml` | `613ab44c26e73ace3b7785b7203a405ef75e837d9b24f2b84eca76770b0bcd4f` |

Chain: revision file → `prereg-v5.1` → dataset `routewise_bench_v5` (unchanged) + schema-4 manifest
→ 54 pinned files, configuration, runtime, pacing and per-attempt quota.
Select it with `--revision routewise_bench_v5.1`.

## Fixes

1. **Every provider attempt reserves quota before transmission.** `PacedProvider`
   (`app/evaluation/pacing.py`) wraps the quota-limited provider that the executor calls. Every
   `generate()` call (initial, same-model retry, fallback) makes exactly one reservation before the
   network request. The runner no longer reserves per gateway request, so nothing is reserved twice;
   it only waits beforehand for the first attempt's capacity.
   - A reservation is released only if the attempt was refused locally before sending.
   - If the attempt was transmitted with unknown usage, the worst case is kept.
   - Once the pacer is exhausted, `quota_available()` returns false, so the executor's next
     fallback isn't attempted.
2. **Correct worst-case preflight** (`app/evaluation/preflight.py`). It counts maximum provider
   **attempts** from the executor's control flow (each eligible model × (1 + max_retries)), not
   gateway requests. It reports the input, output and total reservations, the TPM/RPM/RPD
   constraints and the daily budget after prior usage, and refuses if any retry limit isn't a
   bounded integer.
3. **No unverified daily quota.** The 200,000 tokens/day assumption is gone (`tokens_per_day:
   null`). An operator-supplied remaining daily budget is required, either `--remaining-daily-tokens`
   or `--daily-token-limit` with `--tokens-used-today`, plus `--daily-budget-source` and
   `--daily-budget-verified-at`, verified on the same UTC day. Without it, `eval-validate` exits 1
   and `eval-run` refuses before any network call. No daily token information is inferred from
   request headers.
4. **Token bound.** The ~4 characters/token estimate is replaced by **UTF-8 bytes + 256 framing
   tokens** per attempt.
   - Content: a byte-level BPE tokenizer emits at most one token per byte, so this part is a strict
     bound.
   - Framing: an empirical allowance, about 3× the one observed request's framing.
   - Output: the full `max_output_tokens` cap.
   - If a response reports more tokens than reserved, the run stops as incomplete.
5. **Daily accounting.** A persistent ledger (`evaluation/reports/quota_ledger.json`) records each
   attempt's worst case **before** sending, then settles it to reported usage, keeps it, or removes
   it. A crash or restart therefore can't reset the allowance, and prior usage on the ledger since
   the budget's verification time is subtracted.
   - An attempt that doesn't fit is never sent; the pacer is exhausted and the run is marked
     incomplete.
   - A run is complete only if every case ran and no reservation was refused or exceeded.
   - Rate-limit headers can only tighten limits.
6. **Manifest completeness (schema 4).** The manifest pins all 50 application modules loaded on the
   execution path. These include `core/logging.py`, whose absence broke the v5 bundle, plus
   `db/*`, `auth/*`, `seed.py` and every adapter. It also pins `pyproject.toml`, `uv.lock`, the
   Python version and implementation. A test asserts that the runtime import closure stays a
   subset of the pinned list.
7. **CLI.** `eval-validate` now exits non-zero on a manifest mismatch or a failed preflight.
   `eval-run` exits non-zero when a run is incomplete.

## Worst-case preflight (intended Groq-only configuration, no budget supplied)

```
gateway requests: 135
maximum provider attempts: 378 (per request up to 4; distribution {2: 81, 4: 54}; bounded: True)
input reservation (bytes + framing): 195642 tokens
output reservation (full max_output_tokens): 388096 tokens
total conservative reservation: 583738 tokens
  baseline_premium: 45 requests, 90 max attempts, 148630 tokens
  routewise: 45 requests, 144 max attempts, 217554 tokens
  routewise_tier_first: 45 requests, 144 max attempts, 217554 tokens
tpm_budget: 6000.0                 (8000 observed x 0.75)
largest_attempt_tokens: 2788       (fits the per-minute budget)
min_minutes_by_tpm: 97.3
rpm_cap: 10                        (self-imposed)
min_minutes_by_rpm: 37.8
rpd_budget: 900.0                  (1000 observed x 0.9)
requests_already_today_in_ledger: 0
rpd_remaining: 900.0               (378 max attempts fit)
daily_budget: UNVERIFIED (none supplied)
PROBLEM: no operator-verified remaining daily token budget ...
preflight: FAILED (fail closed)
```

## Tests

`backend/tests/evaluation/test_execution_v5_1.py` is self-contained and covers:

- per-attempt reservation before transmission, for retries and fallbacks
- blocking the next attempt once quota is exhausted
- unknown usage never counting as zero
- a reported-usage bound violation stopping the run
- preflight attempt counting (independently recomputed, and refused when unbounded)
- an unverified, stale or timezone-less budget failing
- a worst case that doesn't fit failing, or passing with a warning when the risk is accepted
- prior usage, and ledger restarts
- header tightening
- the run stopping incomplete rather than over budget, and completing within budget when it fits
- CLI exit codes
- the v5 refusal
- the revision chain, and import-closure completeness

All of these run with mocked providers only.
