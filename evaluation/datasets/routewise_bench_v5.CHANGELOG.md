# routewise_bench_v5 — Changelog

**2026-11-04.** A targeted, scoring-only revision of `routewise_bench_v4` after the owner's independent review. v1–v4, their pre-registrations and their manifests are byte-for-byte unchanged.
No model or provider was called and no benchmark was run. v5 is **not reviewed**: `reviewed_by` is empty. No linguistic validation has been performed for any case.

| Artifact | SHA-256 |
|---|---|
| `datasets/routewise_bench_v5.jsonl` | `76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd` |
| `preregistration_routewise_bench_v5.yaml` | `b9087c9c4777251c961bdad3f56c9635c15a9edb4095aa9666cb00c28a91a9c3` |
| `experiment_manifest_routewise_bench_v5.yaml` (schema 3) | `bb933a4ef1c377461f768432205774ba239d472d311a759093b4392e7f4933fc` |
| `datasets/routewise_bench_v4.jsonl` (unchanged) | `715830467f26d833142b073497f2f7fd47cca0f9fa11cc2f7feabc5773987016` |

Pinning chain: meta → pre-registration → dataset + manifest → configuration, execution code (now including the CLI), dependency lock, runtime environment, pacing and quota. The runner and `eval-run` check every link before any network call.

## Scoring corrections (sections A–C)

| Case | Change | Detail |
|---|---|---|
| S01 | exact scoring | v4 used label search (`choice`), which accepted "Not positive" because the word *positive* appears. v5 requires the whole answer to equal `positive` after normalisation (case, surrounding whitespace, backticks, quotes, trailing `.`/`!`). Extra words, negations and second labels fail. |
| S03 | exact scoring | As S01: "Not dolphin" passed in v4. v5: the whole answer must be `dolphin`. "a dolphin" also fails, since the prompt asks for the name only. |
| S04 | exact scoring | As S01: "Not billing" passed in v4. v5: the whole answer must be `billing`. |
| S14 | exact scoring | As S01: "Not yes" passed in v4. v5: the whole answer must be `yes`. An elaborated yes ("Yes, about 99.97 °C …") now fails, since the prompt asks for yes or no. |
| S09 | strict number | v4 used `last_number`, so "not 391" passed. v5: the whole answer must be exactly one number, with no currency symbol. Shown working (`17 x 23 = 391`) now fails, since the prompt asks for the number only. |
| S10 | strict number | v4 required one number, but "Not 0.9" still passed. v5: strict, no currency. |
| T09 | strict number | "That is not 14" passed in v4. v5: strict, no currency (`$14` fails). |
| T11 | strict number | v4 `last_number` accepted "It is not 33, but final number is 33". v5: strict; `$` is allowed because the answer is a price in dollars (`$33`, `$33.00`). `33 dollars` and `€33` fail. |
| T10 | currency policy | Strict final answer unchanged; `currency_symbols: []` added, so `ANSWER: $7` (a line number) now fails. It passed in v4. |
| C03 | currency policy | Strict final answer unchanged; no currency allowed (`ANSWER: $11` fails). |
| C08 | currency policy | Strict final answer unchanged; no currency allowed (`ANSWER: $328` fails). |
| C09 | currency policy | Strict final answer unchanged; `currency_symbols: ["$"]` made explicit (a dollar amount): `$1,157.63` passes, `€1,157.63` fails. |
| T03 | exact keys + types | v4 checked the six values but ignored extra keys. v5 adds `exact_keys` (exactly the six keys; missing or extra fail) and `field_types` (`duration_minutes` and `alert_threshold_percent` must be JSON integers; the other four must be strings). Values and semantics are unchanged; key order is irrelevant. |

Only scoring rules changed. Every prompt, expected answer, label and category is identical to v4 (tested). Distribution: 15 / 18 / 12.

No case uses `choice`, `last_number` or `first_number` any more, and every strict-number case states its currency policy explicitly (tested). Only T11 and C09, the two dollar answers, allow `$`.

Evidence (`test_v4_false_passes_are_fixed_in_v5`): each answer below passes the **v4** rule and fails the **v5** rule:

- `Not positive` (S01), `Not dolphin` (S03), `Not billing` (S04), `Not yes` (S14)
- `not 391` (S09), `Not 0.9` (S10), `That is not 14` (T09), `It is not 33, but final number is 33` (T11)
- `ANSWER: $7` (T10)
- an extra key (T03)

Scorer additions are opt-in, so v1–v4 scoring is unchanged:

- `numeric.currency_symbols`: when absent, v4's optional `$` still applies; a test confirms v4 behaviour is unchanged.
- `json.exact_keys`.
- `json.field_types` (`integer`, `number`, `string`, `boolean`, `null`).

## Manifest and execution audit (section D)

Manifest **schema 3** adds the following to schema 2:

- `backend/app/cli.py` (argument handling and the preflight check)
- `app/evaluation/pacing.py` (quota pacer)
- `app/core/errors.py` (failure codes and messages that flow into outcomes)
- `backend/uv.lock` (dependency versions; httpx, pydantic and SQLAlchemy behaviour can change results)
- `app_env`
- `execution.runtime`: the Python major.minor version, and whether `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `SSL_CERT_FILE` and `SSL_CERT_DIR` are set (presence only, never values). These can reroute or alter provider traffic through httpx's environment handling.
- `execution.quota`

**Audited and deliberately excluded**, because they don't affect execution configuration or results:

- `core/logging.py`: logging only.
- `db/*` and `seed.py`: persistence. Results come from in-memory outcomes; costs come from the pinned YAML registry, not from database rows.
- The HTTP API layer (`api/v1/*` except the pinned schemas, `api/deps.py`) and `main.py`: the benchmark runs in-process.
- `accounting/usage.py`: dashboard aggregates.
- `auth/*`: the runner uses an internal tenant without key authentication.
- Disabled providers' adapters: pinned automatically whenever a provider is enabled.
- Secret settings (keys, pepper, admin token) and `database_url`: never pinned.
- `openrouter_free_*` and `ollama_base_url`: their providers are disabled, and that is pinned.

## Quota safety (section D, items 3–6)

- **The fixed delay is no longer treated as a guarantee.** `delay_s: 6.0` stays pinned as a floor. Token-per-minute compliance is enforced by the new `QuotaPacer` (`app/evaluation/pacing.py`), integrated into the runner for manifests that pin `execution.quota`.
- **Recorded quota assumptions** (manifest `execution.quota.groq` and prereg `quota`):
  - tokens/minute 8,000 and requests/day 1,000: **observed** in `x-ratelimit-*` headers for this account (`openai/gpt-oss-20b`, one response, 2026-11-04)
  - requests/minute 30 and tokens/day 200,000: Groq's **published Developer-plan base limits**, not verified for the Free plan and used only as upper bounds
  - `gpt-oss-120b`: no limits observed; assumed no higher
- **Pacing rules:**
  - All Groq models share one budget, which is stricter than Groq's per-model limits.
  - Each provider call reserves its **worst case**: input estimate + 100 overhead tokens + `max_output_tokens`.
  - Safety factors: 0.75 per minute, 0.9 per day.
  - Rate-limit headers, captured from every provider response (including 429s) by the HTTP adapter, can only make pacing stricter. The effective limit is min(pinned, header); a header showing insufficient remaining tokens makes the pacer wait for the reported reset; fewer than 10% of daily requests remaining stops the run.
  - Daily tokens count reported usage for single-call requests and the worst case otherwise (never zero).
  - Gateway-internal retries are charged afterwards.
  - If a daily budget would be exceeded, the run **stops and is marked incomplete** (not publishable) instead of exceeding it.
- **Design preserved:** 135 gateway requests, strictly sequential and interleaved, one concurrency slot. `eval-validate` prints the worst-case quota use of a full run.
- **Residual risk:** Groq's exact Free-plan per-minute request limit and daily token limit for these models are unverified. Retries inside one gateway request aren't paced in advance, though they're bounded by `max_retries = 1` and charged afterwards. Usage by other clients of the same key on the same day is learned only from headers after the first response.

## Erratum (earlier version, not modified)

The title line of `routewise_bench_v4_review.md` reads "RouteWise Bench v3 — Review Pack", a template error. Its contents (dataset `routewise_bench_v4.jsonl` and its SHA-256, all 45 cases, acceptance criteria) are correct and were verified against v4. Per the instruction to keep v4 unchanged, the file isn't edited. The v5 verifier now also checks the title.

## Consequence for v4 (by design)

v5 changed code that the v4 manifest pins (scorers, provider interface and HTTP adapter, runner, manifest). v4 can therefore no longer be run on current code; the runner refuses it with file-hash mismatches. The v4 files are unchanged, and its test now asserts that only code-file hashes differ.

## Action needed before a live run

- In `.env`, set `MOCK_PROVIDER_ENABLED=false`. Leave proxy and certificate environment variables unset, as pinned.
- Run `uv run python -m app.cli eval-validate --dataset routewise_bench_v5`. It should report `matches` and print the quota preflight.
- Run `uv run python -m app.cli eval-run --dataset routewise_bench_v5 --label <label> --delay-s 6`.

## Tests

`backend/tests/evaluation/test_dataset_v5.py` contains:

- reference pairs for all 45 cases, plus v4's adversarial answers carried over wherever scoring is unchanged
- every negative example from the review, valid answers and adversarial answers for each correction
- v4-vs-v5 false-pass evidence; a check that v4's strict-number behaviour is unchanged; the currency-policy rules
- T03 exact-key and type tests
- duration and rate-limit header parsing, and adapter header capture on success and on 429
- pacer tests with a fake clock: per-minute tokens and requests; headers that can only tighten; waiting for a reported reset; stopping at daily limits; unknown usage never zero
- the runner stopping incomplete instead of exceeding a pinned quota
- the schema-3 manifest chain, plus drift detection for pacing, quota values, proxy environment and `cli.py`
- the CLI refusing mismatched pacing before any network call, and the `eval-validate` quota preflight
