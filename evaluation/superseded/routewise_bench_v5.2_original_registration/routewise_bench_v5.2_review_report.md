# RouteWise v5.2 — Execution-safety review report

Written for an independent reviewer. No benchmark result is reported: no provider was called and no
benchmark was run.

## 1. Defects fixed (from the v5.1 review)

| # | v5.1 defect | v5.2 fix |
|---|---|---|
| A | `QuotaLedger` loaded the file once and rewrote it from that copy, so two processes could each load the same old state and overwrite each other's reservations | Every operation is a locked read-modify-write on the latest file state, persisted atomically |
| B | `AttemptPacer`'s per-minute window and header state lived in memory, so a restart got a fresh full-minute budget and forgot headers | Per-attempt TPM reservations and header state are persisted; the window is rebuilt from disk for every reservation |

## 2. Design

- **Lock.** `_FileLock` takes an exclusive lock on a sidecar file (`msvcrt.locking` on Windows,
  `fcntl.flock` on POSIX), retrying non-blockingly until a timeout (30 s by default). The OS
  releases it if the holder dies, so a crash can't leave the ledger locked. Nothing is written to
  the lock file.
- **Transactions.** `QuotaLedger.transaction()` acquires the lock, reads the latest JSON, yields it
  for the decision and mutation, writes atomically if anything changed (temporary file in the same
  directory, fsync, `os.replace`), and releases.
  - `AttemptPacer.reserve()` runs its daily checks, per-minute checks and the record insertion in
    **one** transaction, so two processes can't both pass a check for the last available capacity.
  - If the attempt must wait, the transaction ends first, the pacer sleeps, and the check repeats on
    fresh state. The lock is never held while sleeping.
- **Records.** `reserved_at`, `tpm_reserved_tokens`, `daily_tokens` and `status` are separate fields.
  - Settlement changes only `daily_tokens` and `status`.
  - `not_sent` releases both budgets but stays recorded for audit.
  - `sent_unknown` keeps the worst case in both budgets.
- **Window.** A record is in the rolling window while `now − reserved_at < 60 s`, using UTC wall-clock
  time, so it is consistent across processes and restarts. Monotonic clocks aren't shared between
  processes.
- **Headers.** `observe()` converts the provider's monotonic observation time to wall-clock time and
  persists `limit_*`, `remaining_*` and the reset times per model, keeping the newest observation.
  - A `limit_tokens` value tightens the per-minute cap and doesn't expire (conservative).
  - `remaining_tokens` blocks until its reset time.
  - `remaining_requests` blocks until its reset time, or indefinitely if none was given.

## 3. Token bounds

| Quantity | What it is | Guarantee |
|---|---|---|
| **Strict content-byte bound** | UTF-8 bytes of all message contents | **Strict** for byte-level BPE tokenizers (GPT-OSS uses one): at most one token per byte |
| **Empirical provider-framing allowance** | 256 tokens per attempt for the chat template and any provider-injected preamble | **Not guaranteed.** Derived from one observation (83 input tokens for a 53-byte prompt, so framing ≤ 82; 256 is about 3×). Groq could change its preamble at any time |
| **Output bound** | The case's `max_output_tokens`, sent as Groq's `max_completion_tokens` (which includes reasoning tokens) | As strong as the provider's enforcement of that cap |
| **Provider-reported actual usage** | `usage.prompt_tokens` / `completion_tokens` from the response | Used for the **daily** budget after the attempt, and checked against the reserved bounds. **Never** used to shrink the per-minute (TPM) reservation |

If a response reports more input tokens than content bytes plus 256, or more output tokens than
the cap, the run stops and is marked incomplete. **That attempt has already been sent**, so the
framing allowance is a detected risk, not a prevented one.

## 4. Quota scope and verification status

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

| Limit | Value | Status |
|---|---|---|
| Tokens / minute | 8,000 × 0.75 | Self-imposed aggregate, set at the value observed for gpt-oss-20b (one response). 120B and Free-plan values not inferred |
| Requests / day | 1,000 × 0.9 | Self-imposed aggregate, set at the value observed for gpt-oss-20b. 120B and Free-plan values not inferred |
| Requests / minute | 10 | Self-imposed |
| Tokens / day | none | Not verified; an operator-supplied remaining budget is required (fail closed) |

Preflight (unchanged from v5.1, recomputed by the v5.2 CLI test): 135 gateway requests, at most
**378 provider attempts** (`baseline_premium` 45 × 2; each routing strategy 27 × 4 + 18 × 2), and a
583,738-token worst-case reservation. It fails closed without a verified daily budget.

## 5. Verification performed

- **Full backend suite** (Python 3.12.10, the pinned project environment): 1,269 passed, 91 skipped
  (PostgreSQL-only variants), and 4 strict xfails (the superseded v5.1 manifest-match tests). Ruff,
  format and mypy (strict) are clean.
- **v5.2 tests:** 23 passed, including three tests that use real concurrent OS processes.
- **Concurrency stress:** 40 repetitions of the multi-process ledger tests on the final code gave 0
  failures. Before the lock fix, the race showed in 2 of 8 full runs.
- **Clean room:** the review bundle, extracted to an empty directory with a fresh `uv` environment
  built offline from the bundled lock file, runs the v5, v5.1 and v5.2 test files. Results are in
  the hand-off report.

## 6. Hashes of artefacts that must be unchanged

| File | SHA-256 |
|---|---|
| `evaluation/datasets/routewise_bench_v1.jsonl` | `5b0107d1834736932ea68f3bf5b1a3de9c814031c5b96f74349ff2be874841f7` |
| `evaluation/datasets/routewise_bench_v2.jsonl` | `614e14497b380539baed24ad87f3619e11107d2adc35230004b652dec6994550` |
| `evaluation/datasets/routewise_bench_v3.jsonl` | `c0c58c306cd18671e70e40aeab7bbae8672428369bbbe2cbb140144bc61119c7` |
| `evaluation/datasets/routewise_bench_v4.jsonl` | `715830467f26d833142b073497f2f7fd47cca0f9fa11cc2f7feabc5773987016` |
| `evaluation/datasets/routewise_bench_v5.jsonl` | `76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd` |
| `evaluation/datasets/routewise_bench_v5.meta.yaml` | `262dde03c4018fe1f79c1fe8760f32cfcce3e1624284ea6b56eafed432806ada` |
| `evaluation/datasets/routewise_bench_v5_review.md` | `a1ba82a57de9d05b687053e63745a8c3654a8e0cef25754c6c7e2c982fee14ac` |
| `evaluation/preregistration_routewise_bench_v5.yaml` | `b9087c9c4777251c961bdad3f56c9635c15a9edb4095aa9666cb00c28a91a9c3` |
| `evaluation/experiment_manifest_routewise_bench_v5.yaml` | `bb933a4ef1c377461f768432205774ba239d472d311a759093b4392e7f4933fc` |
| `evaluation/routewise_bench_v5.1.revision.yaml` | `903111c6ff27e7c1fa6cf9f59313847a26a7141973039ee9de1b3dc4f23cbb52` |
| `evaluation/preregistration_routewise_bench_v5.1.yaml` | `731fe50a02e2659d9884830c3450fd82bab0f5efa3155424a05f2951e75e5e0d` |
| `evaluation/experiment_manifest_routewise_bench_v5.1.yaml` | `613ab44c26e73ace3b7785b7203a405ef75e837d9b24f2b84eca76770b0bcd4f` |
| `evaluation/datasets/routewise_bench_v5.1.CHANGELOG.md` | `ba21d70303887a0d011e442c9afc5b1834f4a49ddfe4b8b16fbd1be4cc62dbfe` |
| `evaluation/datasets/routewise_bench_v5.1_review_report.md` | `c9db4bdfc9cb2f35ce161c56c8840738678d6960b4376b2cdd81d4a3faf4c80b` |
| `backend/tests/evaluation/test_execution_v5_1.py` | `7437323782960b2cce73e5734c068f2513e04e3669b893cc151047d8e30de25d` |

## 7. Remaining limitations

- **The framing allowance is empirical** (see §3). An over-bound attempt is detected only after it
  has been sent.
- **Other traffic on the same Groq organisation can't be prevented by the gateway.** It's the
  operator's duty (§4), and the guard learns about it only through headers.
- **The lock is advisory between RouteWise processes only.** It protects the ledger file, not the
  provider quota, from non-RouteWise clients.
- **Network filesystems:** the ledger's lock and atomic replace are designed for a local filesystem.
  Network filesystems with weak locking semantics are not supported.
- **Clock jumps:** the per-minute window uses UTC wall-clock time. A backwards clock adjustment
  lengthens the window (safe); a large forwards jump could shorten it, and isn't protected against.
- **Header semantics** (per-day requests, per-minute tokens) and Groq's daily reset time are taken
  from Groq's documentation and aren't independently verified.
- **v5.1 is unrunnable on current code, by design;** use `--revision routewise_bench_v5.2`.
