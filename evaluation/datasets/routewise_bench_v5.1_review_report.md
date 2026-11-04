# RouteWise v5.1 — Execution-safety review report

Written for an independent reviewer. It covers what changed, why, what is and isn't verified, and
what remains. Nothing here reports a benchmark result: no provider was called and no benchmark was
run.

## 1. Defects found in v5 (from inspecting runner → executor → providers)

| # | Defect | Effect |
|---|---|---|
| 1 | Quota was acquired once per gateway request in `runner.py`. Retries (`executor.py`, up to `max_retries` = 1 per Groq model) and fallbacks (each further eligible model) called `provider.generate()` without any reservation | Up to 4 network attempts per request, only 1 of them reserved in advance |
| 2 | The preflight multiplied 135 requests by one worst case and described retries as "up to 270 calls" | Fallbacks were ignored; the real maximum is 378 attempts |
| 3 | 200,000 tokens/day was used as a limit | That's a Developer-plan figure, not verified for this account or plan |
| 4 | `estimate_tokens` = len/4 | An average, not an upper bound; it could under-reserve |
| 5 | Daily usage lived in memory only | A restart reset it; prior usage by other traffic was invisible |
| 6 | `core/logging.py` (and other transitive imports) weren't pinned or bundled | The v5 review bundle couldn't run its tests |

## 2. Design of the fix

- **Where the guard sits.** The executor is the only caller of `provider.generate()`. A
  `PacedProvider` wrapper around the quota-limited provider means *every* call the executor makes
  (initial, retry, fallback) passes through `AttemptPacer.reserve()` immediately before the inner
  adapter transmits.
  - Exactly one reservation per network attempt.
  - Released only if the inner adapter refuses before sending (`ProviderError.sent=False`, a known
    zero).
  - Kept at the worst case if transmitted with unknown usage.
  - Settled to reported usage otherwise, for the daily ledger. The per-minute window keeps the worst
    case, because the provider may count requested output up front.
- **Refusal.** If a reservation doesn't fit, nothing is sent:
  - the wrapper raises `QUOTA_EXHAUSTED` with `sent=False`
  - `quota_available()` turns false, so the executor skips every remaining candidate
  - the runner stops and marks the run incomplete
- **Input bound.** Byte-level BPE emits at most one token per UTF-8 byte, so the bytes of every
  message's content strictly bound the content tokens. The chat framing (role markers, the
  provider-injected system preamble) is invisible to us, so it gets an empirical 256-token
  allowance. One observed request reported 83 input tokens for a 53-byte prompt, which puts its
  framing at ≤ 82. The bound is therefore **not claimed to be guaranteed**: a reported input above
  it stops the run. Output is bounded by the enforced `max_completion_tokens` cap (which includes
  reasoning tokens); a reported output above it also stops the run.
- **Daily budget.** No daily token limit is assumed.
  - The operator supplies the remaining budget (or limit and usage) with its source and
    verification time, on the same UTC day.
  - Usable = remaining × 0.9 − ledger tokens since verification.
  - The ledger persists every attempt's worst case before sending.
  - Other traffic in the same Groq organisation shows up only in the operator figure and in
    `x-ratelimit-*` headers. Headers only tighten limits and are never used to infer daily tokens.

## 3. Maximum-attempt calculation (exact)

From `executor.py`: for a gateway request, the executor iterates `decision.eligible` in order. Each
model gets 1 attempt plus at most `provider.max_retries` same-model retries (transient errors only).
It moves on only after a fallback-eligible error, and it never revisits a model. So

    max_attempts(request) = Σ over eligible models (1 + max_retries) = 2 × |eligible|   (Groq max_retries = 1)

Health exclusions, the deadline and Retry-After can only lower this. The preflight routes every case
with the real router and no health data, which gives an upper bound.

- `baseline_premium`: eligible = {gpt-oss-120b}, so 2 attempts × 45 = **90**.
- `routewise` and `routewise_tier_first`: 27 small-tier cases have eligible = {gpt-oss-20b,
  gpt-oss-120b}, so 4 attempts each. 18 medium/premium cases have {gpt-oss-120b}, so 2 each.
  That's 27 × 4 + 18 × 2 = **144** per strategy.
- Total: 90 + 144 + 144 = **378 provider attempts** for 135 gateway requests. Distribution: 81
  requests with ≤ 2 attempts, 54 with ≤ 4.

## 4. Revised preflight

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

Each line of the preflight is computed as follows:

- **Input reservation:** Σ attempts × (UTF-8 bytes of the prompt + 256).
- **Output reservation:** Σ attempts × `max_output_tokens`.
- **Largest single attempt:** 2,788 tokens, below the 6,000/min budget.
- **Run time:** at least about 97 minutes, set by the tokens-per-minute budget if every attempt
  happened. Real runs make fewer attempts (retries and fallbacks are rare), so they're shorter.
- **Daily tokens:** with no verified budget the preflight fails closed. With one, the 583,738-token
  worst case must fit 0.9 × the remaining budget minus prior ledger usage. Otherwise it fails,
  unless `--accept-incomplete-risk` is given, in which case the run stops incomplete rather than
  exceed the budget.

## 5. Verified vs unverified limits

| Limit | Value used | Status |
|---|---|---|
| Tokens per minute | 8,000 × 0.75 | **Observed** for `openai/gpt-oss-20b` on this key (`x-ratelimit-limit-tokens`, one response, 2026-11-04). `gpt-oss-120b`: **not observed**, assumed no higher, and headers tighten it at run time |
| Requests per day | 1,000 × 0.9 | **Observed** for `gpt-oss-20b` (`x-ratelimit-limit-requests`); `gpt-oss-120b` not observed |
| Requests per minute | cap 10 | **Self-imposed**. Groq's RPM for this account is not verified and isn't in the headers |
| Tokens per day | none | **Not verified.** An operator-supplied remaining budget is required (fail closed) |
| Framing allowance | 256 tokens | **Empirical**, from one observation; violations stop the run |
| Content token bound | UTF-8 bytes | Strict for byte-level BPE |

## 6. Hashes of immutable benchmark artefacts (unchanged)

| File | SHA-256 |
|---|---|
| `evaluation/datasets/routewise_bench_v1.jsonl` | `5b0107d1834736932ea68f3bf5b1a3de9c814031c5b96f74349ff2be874841f7` |
| `evaluation/datasets/routewise_bench_v1.meta.yaml` | `86662104ed9d9981b6962df8c365b584753cb0f21efaac0662c3d3957a2496e4` |
| `evaluation/preregistration.yaml` | `30df1259ef43d94d742cbb21da17b6c8ebea10ca2150a97609f78febe74667eb` |
| `evaluation/datasets/routewise_bench_v2.jsonl` | `614e14497b380539baed24ad87f3619e11107d2adc35230004b652dec6994550` |
| `evaluation/datasets/routewise_bench_v2.meta.yaml` | `2b00edd9f212ea2c9a6251199c42ee1ca63b23c82b5a8695be92c37b8e1e3c55` |
| `evaluation/preregistration_routewise_bench_v2.yaml` | `d90fb48cc1e62fe0a1bfa709b5acff85e39a12d56072ba4b63c33607f07b945f` |
| `evaluation/datasets/routewise_bench_v3.jsonl` | `c0c58c306cd18671e70e40aeab7bbae8672428369bbbe2cbb140144bc61119c7` |
| `evaluation/datasets/routewise_bench_v3.meta.yaml` | `de049f87500cd0eb64706462dbdc66784a0b906a27e430feda26e086b0bb458f` |
| `evaluation/preregistration_routewise_bench_v3.yaml` | `c3172bd6a0bd32bae01910b025706668d2f2cd00f1bf63043ecd4eba264aeaea` |
| `evaluation/experiment_manifest_routewise_bench_v3.yaml` | `de45f809f0e0673c76d878dc09921f85fc576f768b6c921b20f6916f7c160f8f` |
| `evaluation/datasets/routewise_bench_v4.jsonl` | `715830467f26d833142b073497f2f7fd47cca0f9fa11cc2f7feabc5773987016` |
| `evaluation/datasets/routewise_bench_v4.meta.yaml` | `303369b85cd79860c3cad745005b12c3a8f0e963474733acec683cca53d707a8` |
| `evaluation/preregistration_routewise_bench_v4.yaml` | `0752a36358c2aebb2e4985bb3b188ea1b4406f9de2fa5f623b4e5b736219698a` |
| `evaluation/experiment_manifest_routewise_bench_v4.yaml` | `4817aee4d71bc15e8fb6d8b3150fb840fab1a6b845694181e9f1d3b82f53c0c3` |
| `evaluation/datasets/routewise_bench_v5.jsonl` | `76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd` |
| `evaluation/datasets/routewise_bench_v5.meta.yaml` | `262dde03c4018fe1f79c1fe8760f32cfcce3e1624284ea6b56eafed432806ada` |
| `evaluation/datasets/routewise_bench_v5_review.md` | `a1ba82a57de9d05b687053e63745a8c3654a8e0cef25754c6c7e2c982fee14ac` |
| `evaluation/datasets/routewise_bench_v5.CHANGELOG.md` | `8b176680b874cb0f6e9d2a8d39fa93909d9058d60aa53f984ecca0846d13c5d1` |
| `evaluation/preregistration_routewise_bench_v5.yaml` | `b9087c9c4777251c961bdad3f56c9635c15a9edb4095aa9666cb00c28a91a9c3` |
| `evaluation/experiment_manifest_routewise_bench_v5.yaml` | `bb933a4ef1c377461f768432205774ba239d472d311a759093b4392e7f4933fc` |

## 7. Remaining limitations

- **The framing allowance is empirical.** If Groq's injected preamble grew past 256 tokens, a
  reservation could undercount. The run detects this after the response and stops, but that one
  attempt has already been sent.
- **Per-model limits are combined.** Limits are treated as one shared budget across all Groq models,
  which is conservative. `gpt-oss-120b`'s own limits are unobserved until its first response.
- **Header semantics are assumed from Groq's documentation:** `*-requests` are per day and
  `*-tokens` are per minute. The daily reset time is not verified, so the budget is valid only for
  the UTC day it was verified.
- **The catalog refresh isn't reserved.** `eval-run` refreshes the provider catalog (`GET /models`)
  before the run. That's a network call, but not a generation, and it isn't reserved.
- **Retry and fallback waits affect latency.** A wait for a retry or fallback reservation happens
  inside the request and is included in its latency. The first attempt's wait is excluded.
- **Unknown concurrent use.** Other clients using the same key during the run are seen only through
  headers.
- **Wrong operator figures.** A wrong operator-supplied budget makes the guard wrong too; the
  guard can't verify the figure.
- **v5 is unrunnable.** The v5 manifest no longer matches the code, by design, and the v5 test file
  was edited to assert this (see the changelog).
