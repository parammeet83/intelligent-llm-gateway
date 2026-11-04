# routewise_bench_v5.2 — Changelog (execution-safety hotfix)

**2026-11-04.** v5.2 is an execution revision of the unchanged dataset `routewise_bench_v5`. It fixes
two blocking defects found in the independent v5.1 review. No provider was called, no benchmark
was run, `.env` was not changed, and nothing was committed, pushed or deployed.

## Registration correction (re-issued 2026-11-04T13:38:24Z)

The first issue of the v5.2 registration recorded **2026-11-05**, a date in the future when it was
written (2026-11-04). The registration was re-issued with the correct date, and the first-issue
chain is **superseded because of this metadata error**. Only dates and disclosure metadata changed:
code, tests, pinned files, the dataset and every rule are unchanged. Neither the original nor the
corrected registration has been used for a benchmark run. Details, the superseded hashes and how to
verify them are in [`routewise_bench_v5.2.ERRATUM.md`](routewise_bench_v5.2.ERRATUM.md).

## Unchanged

- **Datasets and earlier revisions:** v1–v5 datasets, prompts, expected answers and scoring rules,
  and every v5.1 artefact (revision file, pre-registration, manifest, changelog, review report and
  `test_execution_v5_1.py`) are byte-identical. Hashes are in the review report.
- **v5.1 is refused on current code.** Its manifest no longer matches, so it fails closed before
  any network call.
- **Superseded v5.1 tests.** Four v5.1 tests assert that v5.1 still matches the code. A new
  `tests/evaluation/conftest.py` marks exactly those four as **strict xfail**, each with its
  expected exception, so they must fail and thereby assert that v5.1 is refused. The v5.1 test file
  itself is unchanged, and its other 19 tests (all per-attempt, retry and fallback reservation
  tests) pass unchanged on the v5.2 code.

## New v5.2 chain (root first, corrected re-issue)

| File | SHA-256 |
|---|---|
| `evaluation/routewise_bench_v5.2.revision.yaml` | `59257813e1093d512f0f6fb6459e8ee40aebede789d55908f661dca4bb06d347` |
| `evaluation/preregistration_routewise_bench_v5.2.yaml` | `2c713e734ed418c31874cffec541831402dc689de56fab18f5c4643fb589976b` |
| `evaluation/experiment_manifest_routewise_bench_v5.2.yaml` | `00302285a3d2a1d5d35361fd8eede9065cfc774940e6ade022828c25089aef10` |

The superseded first-issue hashes (`a3e0c4b6…`, `41483ce6…`, `d3ff68dc…`) are listed in the erratum.

Revision → `prereg-v5.2` → dataset (unchanged) + schema-5 manifest → 54 pinned files (the 50-module
execution closure, `pyproject.toml`, `uv.lock` and the two config files), runtime, pacing, and the
v5.2 per-attempt quota. Select it with `--revision routewise_bench_v5.2`.

## Fix A — transactional ledger (`app/evaluation/pacing.py`)

Every reservation, settlement, release and header update is a transaction:

1. acquire an exclusive OS file lock on `quota_ledger.json.lock`
2. re-read the latest saved ledger
3. recalculate capacity
4. add or update the record
5. persist atomically (temporary file, fsync, `os.replace`)
6. release the lock

The lock uses `msvcrt` on Windows and `fcntl` on POSIX (stdlib only, so `uv.lock` is unchanged).
The OS releases it if the holding process dies. No decision uses an in-memory copy, and waiting
always happens outside the lock.

**Found and fixed during v5.2 testing (1 of 2):** the first version wrote an initial byte into an empty lock
file. Under contention on Windows, that write could hit another process's mandatory byte-range lock
and raise `PermissionError`; this occurred in 2 of 8 full test runs. Nothing is written to the lock
file now. A deterministic regression test covers it: the old logic reproduces the error every time,
and the new code times out cleanly. After the fix, 40 stress repetitions of the multi-process tests
gave 0 failures.

**Found and fixed during v5.2 testing (2 of 2):** read-only queries (the `eval-validate`
preflight) took the lock, and taking the lock created a sidecar file. A test run therefore left an
empty `evaluation/reports/quota_ledger.json.lock` in the project. No ledger data was involved, and
the file was removed. Read-only queries on a ledger that doesn't exist yet now return an empty view
without touching the filesystem (regression-tested).

## Fix B — persisted per-minute (TPM) history

Each attempt record keeps separate fields:

| Field | Meaning |
|---|---|
| `reserved_at` | UTC wall-clock time of the reservation |
| `tpm_reserved_tokens` | worst case held in the rolling window; **never overwritten** |
| `daily_tokens` | worst case until settled, then reported usage (or the worst case if usage is unknown) |
| `status` | `reserved`, `sent_known`, `sent_unknown` or `not_sent` |

The legacy `tokens`/`kind` fields are mirrored for compatibility.

- **Rolling window:** rebuilt from the ledger for every reservation. A reservation leaves the window
  only once 60 seconds have passed since `reserved_at`.
- **Restarts:** a restarted process sees the recent per-minute usage and waits; it never gets a
  fresh full-minute budget.
- **Header state:** the latest rate-limit state is persisted per model with wall-clock reset times,
  so it constrains attempts after a restart and in other processes.
- **Legacy v5.1 records:** these carry no separate TPM field, because v5.1 overwrote `tokens` with
  actual usage. While inside the window, each counts as the whole per-minute budget (conservative).
- **Not-sent attempts:** kept as an audit record with status `not_sent`; they release both budgets.

## Fix D — token bounds (method unchanged; wording corrected)

| Quantity | What it is | Guarantee |
|---|---|---|
| **Strict content-byte bound** | UTF-8 bytes of all message contents | **Strict** for byte-level BPE tokenizers (GPT-OSS uses one): at most one token per byte |
| **Empirical provider-framing allowance** | 256 tokens per attempt for the chat template and any provider-injected preamble | **Not guaranteed.** Derived from one observation (83 input tokens for a 53-byte prompt, so framing ≤ 82; 256 is about 3×). Groq could change its preamble at any time |
| **Output bound** | The case's `max_output_tokens`, sent as Groq's `max_completion_tokens` (which includes reasoning tokens) | As strong as the provider's enforcement of that cap |
| **Provider-reported actual usage** | `usage.prompt_tokens` / `completion_tokens` from the response | Used for the **daily** budget after the attempt, and checked against the reserved bounds. **Never** used to shrink the per-minute (TPM) reservation |

If a response reports more input tokens than content bytes plus 256, or more output tokens than
the cap, the run stops and is marked incomplete. **That attempt has already been sent**, so the
framing allowance is a detected risk, not a prevented one.

## Fix E — quota scope

- The per-minute (8,000 × 0.75) and per-day (1,000 × 0.9) caps are **self-imposed aggregates across
  all Groq models**. They are set at the one value observed for `openai/gpt-oss-20b` on this key.
  **Nothing about `gpt-oss-120b` or the Free plan is inferred from that observation.** Both are
  unknown until verified in the Groq console, or until a response header reports them (headers can
  only tighten the caps).
- Requests per minute: a self-imposed cap of 10, because Groq doesn't expose RPM in its headers.
- Tokens per day: **not verified.** You must supply the remaining daily budget, its source and the
  time you checked it (same UTC day); otherwise the run fails closed.
- **The operator must keep all other traffic off the same Groq organisation's quota for the whole
  run.** That includes other scripts, the dashboard and teammates. The guard sees other traffic only
  after the fact, through rate-limit headers. Your operator-supplied budget can't account for
  traffic that starts after you checked it.

## Tests

`backend/tests/evaluation/test_execution_v5_2.py` (23 tests, self-contained) covers:

| Required | Test |
|---|---|
| 1 | two ledger instances, and three concurrent OS processes × 40 writes, lose nothing |
| 2 | three concurrent processes reserving against a shared budget commit exactly the 18 attempts that fit, never more |
| 3 | a restart keeps recent per-minute usage (waits 50 s) |
| 4 | unknown usage keeps the 2,500-token worst case in both budgets |
| 5 | daily usage 300 vs per-minute reservation 2,500, and the next attempt still waits |
| 6 | a reservation is in the window at 59.999 s and out at 60 s |
| 7 | a restarted process doesn't send until the earlier reservation expires |
| 8 | the existing v5.1 retry, fallback and per-attempt tests: 19 pass unchanged |

It also covers persisted headers, legacy records, not-sent records, file format, quota wording,
the chain, the manifest, the CLI, v5.1 refusal, the import closure, the pinned Python, the lock
race, and read-only queries on a missing ledger creating no files. Everything is mocked; no
provider is called.
