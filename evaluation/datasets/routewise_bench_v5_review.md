# RouteWise Bench v5 — Review Pack

- **Dataset (used by the runner):** `evaluation/datasets/routewise_bench_v5.jsonl`, 45 cases (15 simple, 18 standard, 12 complex), SHA-256 `76a4d1906b3e90bff6ed504f67067bf891923332fa00256227e303c11dea27bd`
- **Pre-registration:** `evaluation/preregistration_routewise_bench_v5.yaml`, SHA-256 `b9087c9c4777251c961bdad3f56c9635c15a9edb4095aa9666cb00c28a91a9c3` (pinned in `routewise_bench_v5.meta.yaml`)
- **Experiment manifest:** `evaluation/experiment_manifest_routewise_bench_v5.yaml`, SHA-256 `bb933a4ef1c377461f768432205774ba239d472d311a759093b4392e7f4933fc` (pinned in the pre-registration)
- **v4 kept unchanged:** SHA-256 `715830467f26d833142b073497f2f7fd47cca0f9fa11cc2f7feabc5773987016`, with its own pre-registration.
- **Status:** `draft-pending-human-review`. Nothing is marked reviewed. Changes: [`routewise_bench_v5.CHANGELOG.md`](routewise_bench_v5.CHANGELOG.md).
- **Generated:** 2026-11-04 from the dataset file. Prompts and scoring specs are verbatim; acceptance criteria are a plain-English reading of `backend/app/evaluation/scorers.py`. **No model or provider was called.**

## Scope of any result

- **Fixed suite only.** Results apply to this fixed 45-case suite (this exact file), the pinned configuration, and the run date. They **cannot establish general performance on production workloads**, other prompts or tenants, other models or providers, or later dates.
- **Baseline semantics.** `baseline_premium` requests `preferred_tier=premium`. Premium-only generation is guaranteed by construction: the tier floor raises the required tier to premium, downgrade is never allowed, lower tiers are excluded (`TIER_TOO_LOW`), and the executor only calls eligible models. Retries and fallbacks are therefore premium-only; under the manifest that means one model, `groq/openai/gpt-oss-120b`. The report also checks every baseline attempt and invalidates the run if any is non-premium. The name is therefore accurate and kept.
- **Pass rates are conditional on an answer being returned.** Answer availability (`answered`, `answer_rate`, failures) is reported separately for each strategy, with `pass_rate_unconditional` alongside. Every case records the answering model as reported by the provider and every attempt (model, tier, status, error, latency), including attempts of failed requests.
- **One model family.** Every pinned model is OpenAI GPT-OSS on Groq: `gpt-oss-20b` (small tier) and `gpt-oss-120b` (premium tier), with no medium-tier model. The comparison is between **two sizes of one family**, not independent model families. "Premium" means the best free model, not a frontier model.

## Changed from v4

| Case | Change |
|---|---|
| [S01](#s01) | exact scoring |
| [S03](#s03) | exact scoring |
| [S04](#s04) | exact scoring |
| [S14](#s14) | exact scoring |
| [S09](#s09) | strict number |
| [S10](#s10) | strict number |
| [T09](#t09) | strict number |
| [T11](#t11) | strict number |
| [T10](#t10) | currency policy |
| [C03](#c03) | currency policy |
| [C08](#c08) | currency policy |
| [C09](#c09) | currency policy |
| [T03](#t03) | exact keys + types |

All other 32 cases are byte-identical to v4, and the 13 changed cases differ from v4 only in their scoring rule; every prompt is identical (tested).

## Pinned configuration (from the experiment manifest, schema 3)

| Model key | Provider model ID | Tier | Reasoning effort | Pricing snapshot |
|---|---|---|---|---|
| `groq/openai/gpt-oss-20b` | `openai/gpt-oss-20b` | small | low | $0.075 / $0.30 per Mtok (2026-11-03) |
| `groq/openai/gpt-oss-120b` | `openai/gpt-oss-120b` | premium | provider default | $0.15 / $0.60 per Mtok (2026-11-03) |

| Setting | Value |
|---|---|
| `request_deadline_s` | `60.0` |
| `provider_timeout_s` | `30.0` |
| `retry_backoff_base_s` | `0.5` |
| `retry_backoff_cap_s` | `4.0` |
| `circuit_failure_threshold` | `3` |
| `circuit_open_s` | `30.0` |
| `allow_paid_models` | `False` |
| `verify_model_catalog` | `True` |
| `groq_enabled` | `True` |
| `groq_billing_plan` | `free` |
| `openrouter_enabled` | `False` |
| `ollama_enabled` | `False` |
| `mock_provider_enabled` | `False` |
| `app_env` | `development` |
| `temperature` | `0.0` |
| `runtime` | `{'python': '3.12', 'network_env_present': {'HTTP_PROXY': False, 'HTTPS_PROXY': False, 'ALL_PROXY': False, 'NO_PROXY': False, 'SSL_CERT_FILE': False, 'SSL_CERT_DIR': False}}` |

Quota (pinned, `execution.quota.groq`): `tokens_per_minute` = `8000`, `requests_per_day` = `1000`, `requests_per_minute` = `30`, `tokens_per_day` = `200000`, `per_minute_safety` = `0.75`, `per_day_safety` = `0.9`, `input_overhead_tokens` = `100`, `window_s` = `60.0`. Provenance: tokens_per_minute: observed: x-ratelimit-limit-tokens=8000 (openai/gpt-oss-20b, this key, 2026-11-04); requests_per_day: observed: x-ratelimit-limit-requests=1000 (openai/gpt-oss-20b, this key, 2026-11-04); requests_per_minute: published Developer-plan base limit (console.groq.com/docs/rate-limits, 2026-11-04); not verified for the Free plan; tokens_per_day: published Developer-plan base limit (console.groq.com/docs/rate-limits, 2026-11-04); not verified for the Free plan; openai/gpt-oss-120b: no limits observed; assumed no higher than the values above. All Groq models share one budget (stricter than per-model limits); rate-limit headers can only tighten it.

Pacing (pinned): `concurrency` = `1`, `delay_s` = `6.0`, `limit_cases` = `None`, `allow_code_exec` = `False`. `eval-run` refuses any other `--delay-s`, `--limit` or `--allow-code-exec`.

Strategies: `baseline_premium` (policy {}, request {'preferred_tier': 'premium'}), `routewise` (policy {}, request {}), `routewise_tier_first` (policy {'selection': 'lowest_tier_first'}, request {}).

Routing policy `rw-2026.11-v1`, selection `cheapest_capable`; its full contents, including feature weights and tier thresholds, are in the manifest.

| File | Path | SHA-256 (LF-normalised) |
|---|---|---|
| routing_policy | `backend/config/routing_policy.yaml` | `271106eaa7116211cc198ef5eddc8205f2e3b38e32e7d5fb6ceb37f3a0bb48dc` |
| model_registry | `backend/config/models.yaml` | `c5fc037793d0e80bf4dc9568a137dd7587229f3f14adc83a1bb48af9c7cc7dd0` |
| scorers | `backend/app/evaluation/scorers.py` | `009ae786c5d454fcca2150dc56121b69a26724c3e6b2baed66943e4e74da332a` |
| report | `backend/app/evaluation/report.py` | `45d1a8ddef19f549cbace8366df1353895c7f4f03d991fe23a280262535b4ad4` |
| runner | `backend/app/evaluation/runner.py` | `ba93d15dfe59306b178b30981dd6928f52a75153dac2a3e495684cc620176920` |
| dataset_loader | `backend/app/evaluation/dataset.py` | `a82653c6b23d133c8638a21fb28e5dc7a374ee8324401e0cb493bf3a9c0a862b` |
| evaluation_stats | `backend/app/evaluation/stats.py` | `38fc74dd77f9353e55f22b11c23a6cdb7c997cc8d1dbc54639ee16ed294f5be6` |
| manifest | `backend/app/evaluation/manifest.py` | `c0e05da1b2858f02177265a5889abddb06742267f58aaf2c998102a639b5d54d` |
| routing_engine | `backend/app/routing/engine.py` | `9f2b74a0037cb548f40a8b6446f6738cd242fbbe5be36e2ee1d82bac8ac45ca5` |
| routing_features | `backend/app/routing/features.py` | `0207d8a7dbd52a6e950ebc35299ce15e777b2e2024e2349655db2e6685521526` |
| routing_config | `backend/app/routing/config.py` | `1b3c01e89ed60182743d14e0a534162f450ee5d467e30f491f76617f0697e81e` |
| provider_interface | `backend/app/providers/base.py` | `9b6245d8927a9e856f9467879dc1acc54efc0ad5090e15f1057f2815a6282673` |
| provider_http_and_usage_extraction | `backend/app/providers/http.py` | `31896a87102118618233ff2d4b8d203ed9fedb8b74bac47c5f634fcbe639d1bb` |
| provider_registry | `backend/app/providers/registry.py` | `df756286d75bd913ed2af102a97cf7dc477fe608853ca40622c458a2e10d2192` |
| model_catalog_loader | `backend/app/providers/catalog.py` | `5ad51a507f9474c0004fed624bdf555b93f94767348d7d2f16edbe94375f7be2` |
| executor_retries_fallbacks | `backend/app/services/executor.py` | `3d55a773aa201d1433b0b9252b4e78d9bf6c97f8f9c42d84a6dd8727c0ee0dbb` |
| gateway_pipeline | `backend/app/services/gateway.py` | `a85721de3a0a0d5811e13149de8eab16e463ed77dd5be3bef11720c42167263a` |
| gateway_factory | `backend/app/services/factory.py` | `1bbcd31821303a441a95ff5674c6d03260f2afc5364ff490b31a0e1a25a9aaeb` |
| health_circuit_breaker | `backend/app/resilience/health.py` | `d7f1db6b1612f810560dfb75c2b65b69de2cc85f2ff473e5d5d6d957dc65a1ed` |
| cost_accounting | `backend/app/accounting/cost.py` | `844071eacc3217ad9582b48d0bf8bf2eb40a7a68e48ee89408bb612582791a9d` |
| budget_accounting | `backend/app/accounting/budget.py` | `7dd2d736ab530f77d463a592eb4faee1aaf21cb5a8ac8f301a1270574861895f` |
| rate_limiting | `backend/app/tenancy/rate_limit.py` | `ec557144552a0a6575eb2079bfd50462237ec837bd15f5bfb3704dc8e22f53b6` |
| api_schemas | `backend/app/api/v1/schemas.py` | `afea365265f83d0b5b19deca3018dc62ff235d2b0d2b95ca1387400ff802a63a` |
| settings | `backend/app/core/config.py` | `8c9c684e0e8e3f1690a905c9e66d62ea5673559ee380004db01ca2796d5b3c98` |
| cli | `backend/app/cli.py` | `4129f52d502dae1bd3e80c0fc893551dfc5eabb035e1da38938aa1febf727d11` |
| quota_pacing | `backend/app/evaluation/pacing.py` | `95096644057b94205420851e7c76a5aab06b20c48ac73223d852379c119e837b` |
| error_types | `backend/app/core/errors.py` | `a751caa9f3d9fa59d0c8c51e8f83536828fc8fee86a1926ae0c401fa449c51bd` |
| dependency_lock | `backend/uv.lock` | `da6b69d674d389cd764fb72de3015cfb22f7f4a59fda01cb70a62d24fa5bf955` |
| provider_adapter_groq | `backend/app/providers/groq.py` | `8d673abe0591b5d214c921de10cfe83a6383084dd31fcafb68308051bcf5e88b` |

## Complexity rubric

- **Simple:** one step. The answer is stated in or read directly off the prompt, or is one fact or one arithmetic operation, with a single-token or single-field output.
- **Standard:** two or three steps, or a structured output with several typed fields, or one inference beyond the text (date arithmetic, conditional logic, normalising several values).
- **Complex:** four or more dependent steps, several interacting constraints or rules, state that must be tracked over a sequence, or a distractor that must be recognised.
- Labels describe the reasoning required, not how often models fail. They only group the report; the router computes its own complexity score.

## Case index

| ID | Complexity | Category | Scoring | Change from v4 |
|---|---|---|---|---|
| [S01](#s01) | simple | classification | exact | exact scoring |
| [S02](#s02) | simple | transformation | exact | unchanged |
| [S03](#s03) | simple | classification | exact | exact scoring |
| [S04](#s04) | simple | classification | exact | exact scoring |
| [S05](#s05) | simple | transformation | exact | unchanged |
| [S06](#s06) | simple | extraction | exact | unchanged |
| [S07](#s07) | simple | extraction | exact | unchanged |
| [S08](#s08) | simple | qa | exact | unchanged |
| [S09](#s09) | simple | math | numeric | strict number |
| [S10](#s10) | simple | math | numeric | strict number |
| [S11](#s11) | simple | classification | exact | unchanged |
| [S12](#s12) | simple | classification | exact | unchanged |
| [S13](#s13) | simple | transformation | exact | unchanged |
| [S14](#s14) | simple | qa | exact | exact scoring |
| [S15](#s15) | simple | extraction | json | unchanged |
| [T01](#t01) | standard | extraction | json | unchanged |
| [T02](#t02) | standard | extraction | json | unchanged |
| [T03](#t03) | standard | extraction | json | exact keys + types |
| [T04](#t04) | standard | extraction | json | unchanged |
| [T05](#t05) | standard | qa | exact | unchanged |
| [T06](#t06) | standard | classification | json | unchanged |
| [T07](#t07) | standard | instruction_following | contains | unchanged |
| [T08](#t08) | standard | code | regex | unchanged |
| [T09](#t09) | standard | code | numeric | strict number |
| [T10](#t10) | standard | code | numeric + ANSWER line | currency policy |
| [T11](#t11) | standard | math | numeric | strict number |
| [T12](#t12) | standard | math | regex + ANSWER line | unchanged |
| [T13](#t13) | standard | reasoning | exact | unchanged |
| [T14](#t14) | standard | transformation | json | unchanged |
| [T15](#t15) | standard | math | json | unchanged |
| [T16](#t16) | standard | qa | exact | unchanged |
| [T17](#t17) | standard | translation_choice | regex + ANSWER line | unchanged |
| [T18](#t18) | standard | classification | json | unchanged |
| [C01](#c01) | complex | math | exact + ANSWER line | unchanged |
| [C02](#c02) | complex | math | exact + ANSWER line | unchanged |
| [C03](#c03) | complex | code | numeric + ANSWER line | currency policy |
| [C04](#c04) | complex | reasoning | json | unchanged |
| [C05](#c05) | complex | code | json | unchanged |
| [C06](#c06) | complex | reasoning | exact + ANSWER line | unchanged |
| [C07](#c07) | complex | extraction | json | unchanged |
| [C08](#c08) | complex | math | numeric + ANSWER line | currency policy |
| [C09](#c09) | complex | math | numeric + ANSWER line | currency policy |
| [C10](#c10) | complex | planning | json | unchanged |
| [C11](#c11) | complex | classification | json | unchanged |
| [C12](#c12) | complex | reasoning | validator | unchanged |

## Simple (15)

### S01

| Field | Value |
|---|---|
| Case ID | `S01` |
| Change from v4 | **exact scoring** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Classify the sentiment of this review as positive, negative, or neutral. Reply with one word.
Review: The battery lasts two full days and the screen is gorgeous.
~~~

**Expected answer characteristics:** The single label 'positive'.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `positive` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** Read one sentiment off one sentence.

**What changed from v4:** v4 used label search (`choice`), which accepted "Not positive" because the word *positive* appears. v5 requires the whole answer to equal `positive` after normalisation (case, surrounding whitespace, backticks, quotes, trailing `.`/`!`). Extra words, negations and second labels fail.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "positive"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S02

| Field | Value |
|---|---|
| Case ID | `S02` |
| Change from v4 | **unchanged from v4** |
| Task category | transformation (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Sort these words into alphabetical order. Reply with the sorted words separated by commas only.
Words: pear, apple, mango
~~~

**Expected answer characteristics:** apple, mango, pear.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `apple, mango, pear`; `apple,mango,pear` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One operation on three words.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "apple, mango, pear", "accept": ["apple,mango,pear"]}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S03

| Field | Value |
|---|---|
| Case ID | `S03` |
| Change from v4 | **exact scoring** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Which one of these animals is a mammal: shark, dolphin, trout? Reply with the animal's name only.
~~~

**Expected answer characteristics:** dolphin.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `dolphin` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One fact.

**What changed from v4:** As S01: "Not dolphin" passed in v4. v5: the whole answer must be `dolphin`. "a dolphin" also fails, since the prompt asks for the name only.

**Remaining notes:**

- "a dolphin" and "dolphins" fail; the prompt asks for the animal's name only.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "dolphin"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S04

| Field | Value |
|---|---|
| Case ID | `S04` |
| Change from v4 | **exact scoring** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Classify this support ticket into exactly one category: billing, technical, shipping, account. Reply with the category only.
Ticket: I was charged twice for my March invoice.
~~~

**Expected answer characteristics:** The label 'billing'.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `billing` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One label, with an explicit keyword ("charged").

**What changed from v4:** As S01: "Not billing" passed in v4. v5: the whole answer must be `billing`.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "billing"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S05

| Field | Value |
|---|---|
| Case ID | `S05` |
| Change from v4 | **unchanged from v4** |
| Task category | transformation (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Format this US phone number in E.164 format. Reply with the formatted number only.
Number: (415) 555-0132
~~~

**Expected answer characteristics:** +14155550132.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `+14155550132` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One mechanical reformat (prefix +1, strip punctuation).

**Remaining notes:**

- Strict: the E.164 form only (no spaces or dashes), as the prompt asks.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "+14155550132"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S06

| Field | Value |
|---|---|
| Case ID | `S06` |
| Change from v4 | **unchanged from v4** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Extract the email address from this text. Reply with the address only.
Text: For refunds contact Maria at maria.lopez@example.org before Friday.
~~~

**Expected answer characteristics:** Exactly maria.lopez@example.org.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `maria.lopez@example.org` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** Copy one span.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "maria.lopez@example.org"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S07

| Field | Value |
|---|---|
| Case ID | `S07` |
| Change from v4 | **unchanged from v4** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
On what date is the quarterly review? Reply in YYYY-MM-DD format only.
Text: The quarterly review moved to 14 March 2026 at 10:00.
~~~

**Expected answer characteristics:** 2026-03-14.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `2026-03-14` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One reformat of a stated date.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "2026-03-14"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S08

| Field | Value |
|---|---|
| Case ID | `S08` |
| Change from v4 | **unchanged from v4** |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
What is the capital city of Australia? Reply with the city name only.
~~~

**Expected answer characteristics:** Canberra.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `canberra` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One fact.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "canberra"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S09

| Field | Value |
|---|---|
| Case ID | `S09` |
| Change from v4 | **strict number** |
| Task category | math (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
What is 17 multiplied by 23? Reply with the number only.
~~~

**Expected answer characteristics:** 391.

**Acceptance criteria:**

- **Strict:** The whole answer must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. **No currency symbol is allowed** (e.g. `$7` fails). Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 391 within ±0.

**Complexity rationale:** One multiplication.

**What changed from v4:** v4 used `last_number`, so "not 391" passed. v5: the whole answer must be exactly one number, with no currency symbol. Shown working (`17 x 23 = 391`) now fails, since the prompt asks for the number only.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 391, "tolerance": 0, "strict_number": true, "currency_symbols": []}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S10

| Field | Value |
|---|---|
| Case ID | `S10` |
| Change from v4 | **strict number** |
| Task category | math (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
Which number is larger, 0.9 or 0.11? Reply with the number only.
~~~

**Expected answer characteristics:** 0.9.

**Acceptance criteria:**

- **Strict:** The whole answer must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. **No currency symbol is allowed** (e.g. `$7` fails). Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 0.9 within ±0.

**Complexity rationale:** One comparison.

**What changed from v4:** v4 required one number, but "Not 0.9" still passed. v5: strict, no currency.

**Remaining notes:**

- Decimal comparison is a widely discussed model failure, so it may be represented in training data.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 0.9, "tolerance": 0, "strict_number": true, "currency_symbols": []}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S11

| Field | Value |
|---|---|
| Case ID | `S11` |
| Change from v4 | **unchanged from v4** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Which language is this sentence written in? Reply with the language name in English only.
Sentence: Je voudrais un café, s'il vous plaît.
~~~

**Expected answer characteristics:** French.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `french` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One recognition.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "french"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S12

| Field | Value |
|---|---|
| Case ID | `S12` |
| Change from v4 | **unchanged from v4** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Label this message as spam or legitimate. Reply with one word only.
Message: Congratulations! You won a $1,000 gift card. Click here to claim now.
~~~

**Expected answer characteristics:** spam.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `spam` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One label.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "spam"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S13

| Field | Value |
|---|---|
| Case ID | `S13` |
| Change from v4 | **unchanged from v4** |
| Task category | transformation (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Rewrite the following text in uppercase letters only. Reply with the rewritten text only.
Text: ship it today
~~~

**Expected answer characteristics:** SHIP IT TODAY (case-sensitive).

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `SHIP IT TODAY` (case-sensitive). Anything else fails, including extra words.

**Complexity rationale:** One mechanical transform.

**Remaining notes:**

- task_type is `extraction` because the router has no `transformation` type.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "SHIP IT TODAY", "case_sensitive": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S14

| Field | Value |
|---|---|
| Case ID | `S14` |
| Change from v4 | **exact scoring** |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
At standard atmospheric pressure (1 atm), does pure water boil at approximately 100 degrees Celsius? Answer yes or no.
~~~

**Expected answer characteristics:** yes (about 99.97 °C, i.e. approximately 100 °C).

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `yes` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One fact.

**What changed from v4:** As S01: "Not yes" passed in v4. v5: the whole answer must be `yes`. An elaborated yes ("Yes, about 99.97 °C …") now fails, since the prompt asks for yes or no.

**Remaining notes:**

- Only `yes`/`no` (any case, optional trailing punctuation) are accepted; any elaboration fails.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "yes"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S15

| Field | Value |
|---|---|
| Case ID | `S15` |
| Change from v4 | **unchanged from v4** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `json` · max output tokens 512 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Return a JSON object with the keys "name" (string) and "age" (integer) for this person: Priya is 34 years old.
~~~

**Expected answer characteristics:** {"name": "Priya", "age": 34}.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `name` = `"Priya"`
- `age` = `34`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Two fields copied from one short sentence, JSON-typed.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"name": "Priya", "age": 34}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

## Standard (18)

### T01

| Field | Value |
|---|---|
| Case ID | `T01` |
| Change from v4 | **unchanged from v4** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Extract invoice_number (string), total_amount (number) and currency (ISO 4217 code) from the text and return them as a JSON object.
Text: Invoice INV-2026-0042 - amount due: EUR 1,250.00 by 30 April.
~~~

**Expected answer characteristics:** invoice_number INV-2026-0042, total_amount 1250, currency EUR.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `invoice_number` = `"INV-2026-0042"`
- `total_amount` = `1250`
- `currency` = `"EUR"`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Three fields, each needing normalisation ("EUR 1,250.00" → number 1250 and ISO code EUR), into typed JSON.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"invoice_number": "INV-2026-0042", "total_amount": 1250, "currency": "EUR"}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T02

| Field | Value |
|---|---|
| Case ID | `T02` |
| Change from v4 | **unchanged from v4** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Extract every person and their role. Return JSON shaped like {"people": [{"name": "...", "role": "..."}]}.
Text: The kickoff included Dana Kim (product manager), Luis Ortega (backend engineer) and Aiko Sato (designer).
~~~

**Expected answer characteristics:** Exactly three people, each with the role given in the text: Dana Kim (product manager), Luis Ortega (backend engineer), Aiko Sato (designer).

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `people` has exactly 3 items
- the item with `name` = `Dana Kim` has `role` `product manager`
- the item with `name` = `Luis Ortega` has `role` `backend engineer` or `back-end engineer`
- the item with `name` = `Aiko Sato` has `role` `designer`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** List extraction with name→role pairing and an exact count.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "list_length": {"path": "people", "equals": 3}, "list_pairs": {"path": "people", "key": "name", "value_key": "role", "expected": {"Dana Kim": ["product manager"], "Luis Ortega": ["backend engineer", "back-end engineer"], "Aiko Sato": ["designer"]}}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T03

| Field | Value |
|---|---|
| Case ID | `T03` |
| Change from v4 | **exact keys + types** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Extract facts from the incident report below. Return one JSON object with exactly these keys, shaped like this example (the values shown are placeholders, not answers):
{"start_time_utc": "HH:MM", "day": "<day name>", "affected_feature": "<word>", "duration_minutes": 0, "root_cause": "<cause>", "alert_threshold_percent": 0}
Permitted values:
- start_time_utc: a 24-hour time as a string "HH:MM" (two-digit hour)
- day: an English day name, Monday to Sunday
- affected_feature: one lowercase word naming the feature that failed
- duration_minutes: an integer
- root_cause: exactly one of "disk_full", "network", "deploy", "memory"
- alert_threshold_percent: an integer (no % sign)
Report: On Monday at 09:12 UTC the primary database ran out of disk space, causing checkout failures for 45 minutes. Engineers expanded the storage volume, restored service, and added an alert that fires when disk usage passes 80%.
~~~

**Expected answer characteristics:** start_time_utc 09:12, day Monday, affected_feature checkout, duration_minutes 45, root_cause disk_full, alert_threshold_percent 80.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- The object must have **exactly** these keys: `start_time_utc`, `day`, `affected_feature`, `duration_minutes`, `root_cause`, `alert_threshold_percent`. Missing or extra keys fail.
- `start_time_utc` = `"09:12"`
- `day` = `"Monday"`
- `affected_feature` = `"checkout"`
- `duration_minutes` = `45`
- `root_cause` = `"disk_full"`
- `alert_threshold_percent` = `80`
- `start_time_utc` must be a JSON string
- `day` must be a JSON string
- `affected_feature` must be a JSON string
- `duration_minutes` must be a JSON integer (so `45.0` or `"45"` fail)
- `root_cause` must be a JSON string
- `alert_threshold_percent` must be a JSON integer (so `45.0` or `"45"` fail)
-  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Six typed facts from a three-sentence report, including one mapping to a closed vocabulary (root cause) and time/number normalisation. Kept standard; the change from summarisation to extraction doesn't change the step count.

**What changed from v4:** v4 checked the six values but ignored extra keys. v5 adds `exact_keys` (exactly the six keys; missing or extra fail) and `field_types` (`duration_minutes` and `alert_threshold_percent` must be JSON integers; the other four must be strings). Values and semantics are unchanged; key order is irrelevant.

**Remaining notes:**

- `"day": "monday"` passes (strings compare case-insensitively); `"day": "Mon"` fails.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"start_time_utc": "09:12", "day": "Monday", "affected_feature": "checkout", "duration_minutes": 45, "root_cause": "disk_full", "alert_threshold_percent": 80}, "exact_keys": true, "field_types": {"start_time_utc": "string", "day": "string", "affected_feature": "string", "duration_minutes": "integer", "root_cause": "string", "alert_threshold_percent": "integer"}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T04

| Field | Value |
|---|---|
| Case ID | `T04` |
| Change from v4 | **unchanged from v4** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
From the meeting notes below, list only the decisions that were made. Return one JSON object shaped like this example (the values shown are placeholders, not answers):
{"decisions": [{"topic": "<topic>", "owner": "<team>", "date": "YYYY-MM-DD"}, {"topic": "<topic>", "owner": null, "date": null}]}
Permitted values:
- topic: exactly one of "launch_date", "press_release", "feature_freeze", "pricing"
- owner: the responsible team in lowercase as named in the notes, or null if no team is named
- date: a date as a string "YYYY-MM-DD", or null if the decision has no date
Rules: include one record per decided topic (each topic at most once), and omit topics that were discussed but left undecided.
Notes: We agreed to move the launch to 2 June 2026. Marketing will own the press release. We discussed pricing but postponed a decision. Engineering will freeze features on 20 May 2026.
~~~

**Expected answer characteristics:** Exactly three decisions: launch_date (owner null, 2026-06-02), press_release (owner marketing, date null), feature_freeze (owner engineering, 2026-05-20). Pricing is absent.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `decisions` is a list of objects keyed by `topic` (trimmed, case-insensitive); each key appears **at most once** (duplicates fail); the keys must be **exactly** `launch_date`, `press_release`, `feature_freeze` (missing or extra keys fail)
- record `launch_date`: `owner` = `null`, `date` = `"2026-06-02"`
- record `press_release`: `owner` = `"marketing"`, `date` = `null`
- record `feature_freeze`: `owner` = `"engineering"`, `date` = `"2026-05-20"`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Separate decisions from a non-decision, attribute each decision to its owner (or none), and normalise dates into keyed JSON records. Kept standard.

**Remaining notes:**

- A model naming the launch owner as "we" or "team" fails; the prompt says null when no team is named.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "list_records": {"path": "decisions", "key": "topic", "exact": true, "expected": {"launch_date": {"owner": null, "date": "2026-06-02"}, "press_release": {"owner": "marketing", "date": null}, "feature_freeze": {"owner": "engineering", "date": "2026-05-20"}}}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T05

| Field | Value |
|---|---|
| Case ID | `T05` |
| Change from v4 | **unchanged from v4** |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Answer the question using the passage. Reply with the day of the week only.
Passage: The team ships a release every other week. This month's releases were scheduled for Tuesday the 3rd and Tuesday the 17th, but the second one slipped by two days because of a failed test run.
Question: On which day of the week did the second release of the month actually happen?
~~~

**Expected answer characteristics:** Thursday (Tuesday plus two days).

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `thursday` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** Passage reading plus one date-arithmetic step.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "thursday"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T06

| Field | Value |
|---|---|
| Case ID | `T06` |
| Change from v4 | **unchanged from v4** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Classify this support ticket. Categories: billing (charges, invoices, refunds), technical (bugs, crashes, errors in the product), shipping (deliveries), account (sign-in, passwords, access and permissions). Urgency: high if work is blocked right now, medium if work is impaired but possible, low otherwise. Return JSON with "category" and "urgency".
Ticket: Our whole team has been locked out of our accounts since this morning and we have a client demo in an hour.
~~~

**Expected answer characteristics:** category account, urgency high.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `category` = `"account"`
- `urgency` = `"high"`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Two independent classifications against given definitions.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"category": "account", "urgency": "high"}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T07

| Field | Value |
|---|---|
| Case ID | `T07` |
| Change from v4 | **unchanged from v4** |
| Task category | instruction_following (router `task_type`: `creative`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword / rule checks |

**Full prompt** (verbatim):

~~~text
Rewrite the message below as a request for the report that follows ALL of these rules: (1) it starts with the word "Please"; (2) it contains the words "the report"; (3) it does not contain the words "now" or "late"; (4) it is at most 15 words long; (5) it ends with a full stop. Reply with the rewritten message only.
Message: Send me the report now, you are already late.
~~~

**Expected answer characteristics:** A message that satisfies all five explicit rules. Only rule compliance is evaluated; tone and writing quality are not.

**Acceptance criteria:**

- All of these must hold (case-insensitive):
- the answer (ignoring surrounding quotes and markdown) starts with the word `please`
- contains the whole word(s) `the report`
- does not contain the whole word `now`
- does not contain the whole word `late`
- at most 15 words (split on whitespace)
- the answer (ignoring surrounding quotes and markdown) ends with `.`

**Complexity rationale:** Satisfy five explicit, independent rules at once (start word, required phrase, two banned words, length, final punctuation). Kept standard.

**Remaining notes:**

- Measures rule compliance only. Words are split on whitespace, so "e-mail" counts as one word.

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "starts_with_word": "please", "all_words": ["the report"], "none_words": ["now", "late"], "max_words": 15, "ends_with": "."}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T08

| Field | Value |
|---|---|
| Case ID | `T08` |
| Change from v4 | **unchanged from v4** |
| Task category | code (router `task_type`: `code`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | regular expression |

**Full prompt** (verbatim):

~~~text
Write a SQL query that returns the name column of every row in the customers table whose country is 'Germany', sorted by name ascending. Reply with the SQL only.
~~~

**Expected answer characteristics:** SELECT name FROM customers WHERE country = 'Germany' ORDER BY name (a table alias and ASC are fine; no extra columns).

**Acceptance criteria:**

- Pattern searched in inside the first fenced code block if present, else the trimmed answer: `(?is)^\s*select\s+(?:\w+\.)?name\s+from\s+customers(?:\s+(?:as\s+)?(?!where\b)\w+)?\s+where\s+(?:\w+\.)?country\s*=\s*'germany'\s+order\s+by\s+(?:\w+\.)?name(?:\s+asc)?\s*;?\s*$`
- In plain terms: exactly `SELECT [alias.]name FROM customers [[AS] alias] WHERE [alias.]country = 'Germany' ORDER BY [alias.]name [ASC] [;]`, case-insensitive, any whitespace or newlines.

**Complexity rationale:** Compose a query with three clauses.

**Remaining notes:**

- Equivalent but unusual SQL (subqueries, `IN ('Germany')`) fails; the prompt asks for a straightforward query.

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "strip_fences": true, "pattern": "(?is)^\\s*select\\s+(?:\\w+\\.)?name\\s+from\\s+customers(?:\\s+(?:as\\s+)?(?!where\\b)\\w+)?\\s+where\\s+(?:\\w+\\.)?country\\s*=\\s*'germany'\\s+order\\s+by\\s+(?:\\w+\\.)?name(?:\\s+asc)?\\s*;?\\s*$"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T09

| Field | Value |
|---|---|
| Case ID | `T09` |
| Change from v4 | **strict number** |
| Task category | code (router `task_type`: `code`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
What does this Python program print? Reply with the printed output only.
```python
values = [5, 8, 2, 10, 6]
result = sorted(values, reverse=True)[1:3]
print(sum(result))
```
~~~

**Expected answer characteristics:** 14 (sorted descending: 10, 8, 6, 5, 2; slice [1:3] is 8 and 6).

**Acceptance criteria:**

- **Strict:** The whole answer must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. **No currency symbol is allowed** (e.g. `$7` fails). Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 14 within ±0.

**Complexity rationale:** Trace three statements (sort, slice, sum).

**What changed from v4:** "That is not 14" passed in v4. v5: strict, no currency (`$14` fails).

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 14, "tolerance": 0, "strict_number": true, "currency_symbols": []}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T10

| Field | Value |
|---|---|
| Case ID | `T10` |
| Change from v4 | **currency policy** |
| Task category | code (router `task_type`: `code`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
The function below should return the average of the positive numbers in a list, or 0.0 if there are none, but one line has a bug. Which line number contains the bug? Explain briefly. End your reply with a final line of the form ANSWER: <line number>, containing only the number (no words, units or notes).
1  def average_positive(nums):
2      total = 0
3      count = 0
4      for n in nums:
5          if n > 0:
6              total += n
7          count += 1
8      return total / count if count else 0.0
~~~

**Expected answer characteristics:** Line 7: `count += 1` is outside the `if`, so negative numbers are counted.

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- **Strict:** The ANSWER value must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. **No currency symbol is allowed** (e.g. `$7` fails). Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 7 within ±0.

**Complexity rationale:** Read eight lines, compare them with the stated intent, and locate the faulty line.

**What changed from v4:** Strict final answer unchanged; `currency_symbols: []` added, so `ANSWER: $7` (a line number) now fails. It passed in v4.

**Remaining notes:**

- `ANSWER: 07` is accepted as 7 (leading zeros are a valid number).

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 7, "tolerance": 0, "final_answer": true, "strict_number": true, "currency_symbols": []}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T11

| Field | Value |
|---|---|
| Case ID | `T11` |
| Change from v4 | **strict number** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
A shirt costs $40. It is discounted by 25%, then a 10% tax is added to the discounted price. What is the final price in dollars? Reply with the number only.
~~~

**Expected answer characteristics:** 33 (40 x 0.75 = 30; 30 x 1.10 = 33).

**Acceptance criteria:**

- **Strict:** The whole answer must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. Currency symbols allowed in front: `$`. Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 33 within ±0.001.

**Complexity rationale:** Two chained percentage operations.

**What changed from v4:** v4 `last_number` accepted "It is not 33, but final number is 33". v5: strict; `$` is allowed because the answer is a price in dollars (`$33`, `$33.00`). `33 dollars` and `€33` fail.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 33, "tolerance": 0.001, "strict_number": true, "currency_symbols": ["$"]}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T12

| Field | Value |
|---|---|
| Case ID | `T12` |
| Change from v4 | **unchanged from v4** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | regular expression |

**Full prompt** (verbatim):

~~~text
Two fair six-sided dice are rolled. What is the probability that their sum is 8? Explain briefly. End your reply with a final line of the form ANSWER: <reduced fraction>.
~~~

**Expected answer characteristics:** 5/36 (2+6, 3+5, 4+4, 5+3, 6+2).

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- Pattern searched in the trimmed answer (or the ANSWER value): `^5\s*/\s*36\.?$`
- In plain terms: the whole ANSWER value must be `5/36` (spaces around `/` and one trailing full stop allowed). Nothing else may follow.

**Complexity rationale:** Enumerate the five outcomes and reduce 5/36.

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "^5\\s*/\\s*36\\.?$", "final_answer": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T13

| Field | Value |
|---|---|
| Case ID | `T13` |
| Change from v4 | **unchanged from v4** |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
What day of the week was 1 January 2026? Reply with the day name only.
~~~

**Expected answer characteristics:** Thursday.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `thursday` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** One anchor date plus one modular-arithmetic step.

**Remaining notes:**

- Calendar arithmetic without tools favours reasoning models; all pinned models are GPT-OSS reasoning models.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "thursday"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T14

| Field | Value |
|---|---|
| Case ID | `T14` |
| Change from v4 | **unchanged from v4** |
| Task category | transformation (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Convert each date to ISO 8601 format (YYYY-MM-DD), keeping the original order. Return JSON {"dates": [...]}.
Dates: 3 Feb 2026; February 14, 2026; 2026/03/01; 1st of April 2026
~~~

**Expected answer characteristics:** {"dates": ["2026-02-03", "2026-02-14", "2026-03-01", "2026-04-01"]}.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `dates` = `["2026-02-03", "2026-02-14", "2026-03-01", "2026-04-01"]` (list must match exactly, including order)
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Four values in three input formats, normalised and kept in order.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"dates": ["2026-02-03", "2026-02-14", "2026-03-01", "2026-04-01"]}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T15

| Field | Value |
|---|---|
| Case ID | `T15` |
| Change from v4 | **unchanged from v4** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Compute the order total from these line items and return JSON {"total": number}.
Items: 3 notebooks at $2.50 each; 2 pens at $1.20 each.
~~~

**Expected answer characteristics:** {"total": 9.9}.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Two multiplications and a sum, as typed JSON.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "numeric": {"path": "total", "answer": 9.9, "tolerance": 0.001}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T16

| Field | Value |
|---|---|
| Case ID | `T16` |
| Change from v4 | **unchanged from v4** |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Answer using only the context. If the answer is not in the context, reply exactly: NOT_IN_CONTEXT
Context: Our office is open Monday to Friday, 9am to 5pm, and closed on public holidays.
Question: What is the office phone number?
~~~

**Expected answer characteristics:** NOT_IN_CONTEXT (the context has no phone number).

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `NOT_IN_CONTEXT` (case-sensitive). Anything else fails, including extra words.

**Complexity rationale:** Recognise that the answer is absent and follow an exact refusal format.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "NOT_IN_CONTEXT", "case_sensitive": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T17

| Field | Value |
|---|---|
| Case ID | `T17` |
| Change from v4 | **unchanged from v4** |
| Task category | translation_choice (router `task_type`: `qa`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | regular expression |

**Full prompt** (verbatim):

~~~text
Which option is the correct Spanish translation of the English sentence "The library opens at nine o'clock."?
A) La biblioteca cierra a las nueve en punto.
B) La biblioteca abre a las nueve en punto.
C) La biblioteca abre a las diez en punto.
D) La librería abre a las nueve en punto.
End your reply with a final line of the form ANSWER: <letter>, containing only the letter.
~~~

**Expected answer characteristics:** B. A says "closes" (cierra), C says "ten" (diez), and D says "bookshop" (librería, a false friend). Each distractor differs from the source in exactly one content word.

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- Pattern searched in the trimmed answer (or the ANSWER value): `^\(?[Bb]\)?\.?$`
- In plain terms: the whole ANSWER value must be the letter `B` (either case), optionally as `(B)` or `B)`, with an optional trailing full stop. Nothing else may follow.

**Complexity rationale:** Faithful translation of one sentence (an accepted-answer list is checked).

**Remaining notes:**

- The accepted-translation list needs validation by a Spanish speaker before publication.

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "^\\(?[Bb]\\)?\\.?$", "final_answer": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T18

| Field | Value |
|---|---|
| Case ID | `T18` |
| Change from v4 | **unchanged from v4** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Decide whether this product review mentions a defect. Return JSON {"defect": true or false, "part": the defective part written exactly as it appears in the review, in lowercase, or null}.
Review: Love the colour, but the zipper broke after one week.
~~~

**Expected answer characteristics:** defect true, part zipper.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `defect` = `true`
- `part` = `"zipper"`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Two judgements (defect yes/no, which part) as typed JSON.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"defect": true, "part": "zipper"}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

## Complex (12)

### C01

| Field | Value |
|---|---|
| Case ID | `C01` |
| Change from v4 | **unchanged from v4** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Train A leaves a station at 08:15 travelling at 120 km/h. Train B leaves the same station at 09:00 on a parallel track in the same direction at 150 km/h. At what time does train B draw level with train A? Show your reasoning briefly. End your reply with a final line of the form ANSWER: HH:MM (24-hour), containing only the time.
~~~

**Expected answer characteristics:** 12:00 (A is 90 km ahead at 09:00; closing speed 30 km/h; 3 hours).

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `12:00` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** Head start, closing speed, catch-up time and clock addition: four dependent steps in mixed units.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "12:00", "final_answer": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C02

| Field | Value |
|---|---|
| Case ID | `C02` |
| Change from v4 | **unchanged from v4** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
A 1,200-litre tank is empty at 08:00. Pipe A fills it at 40 litres per minute and drain C empties it at 15 litres per minute; both are open from 08:00. Pipe B, which fills at 25 litres per minute, is opened at 08:20. Pipe A is closed at 08:40. At what time is the tank first full? Show your working briefly. End your reply with a final line of the form ANSWER: HH:MM (24-hour).
~~~

**Expected answer characteristics:** 08:34 (500 L by 08:20; then 50 L/min, so 700 L more takes 14 minutes; pipe A closing at 08:40 is a distractor).

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `08:34`; `8:34` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** Three phases with different net rates, a threshold crossing inside a phase, and a distractor event.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "08:34", "accept": ["8:34"], "final_answer": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C03

| Field | Value |
|---|---|
| Case ID | `C03` |
| Change from v4 | **currency policy** |
| Task category | code (router `task_type`: `code`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
What does this Python program print? Trace it step by step. End your reply with a final line of the form ANSWER: <number>, containing only the number (no words, units or notes).
```python
def f(items):
    seen = {}
    total = 0
    for i, x in enumerate(items):
        if x in seen:
            total += i - seen[x]
        seen[x] = i
    return total

print(f([3, 1, 3, 2, 1, 3, 2]))
```
~~~

**Expected answer characteristics:** 11 (gaps between repeats: 2 + 3 + 3 + 3).

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- **Strict:** The ANSWER value must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. **No currency symbol is allowed** (e.g. `$7` fails). Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 11 within ±0.

**Complexity rationale:** Track a dict and an accumulator over seven iterations.

**What changed from v4:** Strict final answer unchanged; no currency allowed (`ANSWER: $11` fails).

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 11, "tolerance": 0, "final_answer": true, "strict_number": true, "currency_symbols": []}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C04

| Field | Value |
|---|---|
| Case ID | `C04` |
| Change from v4 | **unchanged from v4** |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Apply these account events in order. Every balance starts at 0. A withdrawal or transfer that would make the sender's balance negative is rejected and has no effect.
1. Ana deposits 100
2. Ben deposits 50
3. Ana transfers 30 to Ben
4. Ben withdraws 70
5. Cara deposits 20
6. Ben transfers 25 to Cara
7. Ana withdraws 60
8. Cara transfers 20 to Ana
Return JSON {"Ana": number, "Ben": number, "Cara": number, "rejected": number of rejected events}.
~~~

**Expected answer characteristics:** {"Ana": 30, "Ben": 10, "Cara": 0, "rejected": 1} (event 6 is rejected: Ben has 10).

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `Ana` = `30`
- `Ben` = `10`
- `Cara` = `0`
- `rejected` = `1`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Track three balances over eight events with a conditional rejection rule.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"Ana": 30, "Ben": 10, "Cara": 0, "rejected": 1}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C05

| Field | Value |
|---|---|
| Case ID | `C05` |
| Change from v4 | **unchanged from v4** |
| Task category | code (router `task_type`: `code`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Table orders has these rows (id, customer, amount, status):
(1, 'Abe', 40, 'paid'), (2, 'Cara', 70, 'paid'), (3, 'Abe', 35, 'paid'), (4, 'Dev', 90, 'refunded'), (5, 'Cara', 50, 'paid'), (6, 'Dev', 30, 'paid'), (7, 'Abe', 20, 'refunded')
What does this query return?
SELECT customer, SUM(amount) AS total FROM orders WHERE status = 'paid' GROUP BY customer HAVING SUM(amount) > 50 ORDER BY total DESC;
Return JSON {"rows": [[customer, total], ...]} in the order the query returns them.
~~~

**Expected answer characteristics:** {"rows": [["Cara", 120], ["Abe", 75]]} (Dev's paid total is 30).

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `rows` = `[["Cara", 120], ["Abe", 75]]` (list must match exactly, including order)
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Filter, group, aggregate, apply HAVING and sort, by hand over seven rows.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"rows": [["Cara", 120], ["Abe", 75]]}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C06

| Field | Value |
|---|---|
| Case ID | `C06` |
| Change from v4 | **unchanged from v4** |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | exact match |

**Full prompt** (verbatim):

~~~text
Five friends (Ana, Ben, Cy, Di and Eli) each have a different favourite colour: red, blue, green, yellow or white. Ana's favourite is not red, blue or white. Ben's favourite is green. Cy's favourite is neither red nor white. Di's favourite is neither yellow nor white. Eli's favourite is blue or white. Whose favourite colour is white? Reason it through. End your reply with a final line of the form ANSWER: <name>.
~~~

**Expected answer characteristics:** Eli (Ben green; Ana yellow; Cy blue; Eli white; Di red). Unique solution, checked by brute force.

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal one of: `Eli` (case-insensitive). Anything else fails, including extra words.

**Complexity rationale:** Five variables and six constraints; about four chained deductions.

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "Eli", "final_answer": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C07

| Field | Value |
|---|---|
| Case ID | `C07` |
| Change from v4 | **unchanged from v4** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Extract the order from this email as JSON with keys "customer" (string), "items" (list of {"sku": string, "quantity": integer}) and "total_units" (integer, the sum of all quantities). Merge repeated SKUs so that each SKU appears exactly once.
Email: Hi, this is Omar Haddad. Please send 2 units of SKU-118 and 5 of SKU-204. Actually, add 3 more of SKU-118 as well. Thanks!
~~~

**Expected answer characteristics:** customer Omar Haddad; exactly two items, SKU-118 x5 and SKU-204 x5; total_units 10.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `customer` = `"Omar Haddad"`
- `total_units` = `10`
- `items` is a list of objects keyed by `sku` (trimmed, case-insensitive); each key appears **at most once** (duplicates fail); the keys must be **exactly** `SKU-118`, `SKU-204` (missing or extra keys fail)
- record `SKU-118`: `quantity` = `5`
- record `SKU-204`: `quantity` = `5`
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Extract, merge repeated SKUs into unique records, sum, and emit nested typed JSON.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"customer": "Omar Haddad", "total_units": 10}, "list_records": {"path": "items", "key": "sku", "exact": true, "expected": {"SKU-118": {"quantity": 5}, "SKU-204": {"quantity": 5}}}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C08

| Field | Value |
|---|---|
| Case ID | `C08` |
| Change from v4 | **currency policy** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
What is the sum of all prime numbers less than 50? Work it out. End your reply with a final line of the form ANSWER: <number>, containing only the number (no words, units or notes).
~~~

**Expected answer characteristics:** 328.

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- **Strict:** The ANSWER value must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. **No currency symbol is allowed** (e.g. `$7` fails). Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 328 within ±0.

**Complexity rationale:** Enumerate 15 primes and sum them.

**What changed from v4:** Strict final answer unchanged; no currency allowed (`ANSWER: $328` fails).

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 328, "tolerance": 0, "final_answer": true, "strict_number": true, "currency_symbols": []}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C09

| Field | Value |
|---|---|
| Case ID | `C09` |
| Change from v4 | **currency policy** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
$1,000 is invested at 5% annual interest, compounded annually, for 3 years. What is the final amount in dollars, rounded to 2 decimal places using round-half-up (a third decimal digit of 5 or more rounds the second decimal up)? Show the calculation briefly. End your reply with a final line of the form ANSWER: <number>, containing only the number (no words, units or notes).
~~~

**Expected answer characteristics:** 1157.63 (1000 x 1.05^3 = 1157.625, which rounds half up to 1157.63; round-half-even would give 1157.62).

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- **Strict:** The ANSWER value must be exactly one number and nothing else. Allowed: correctly grouped thousands commas (`1,157.63`), a minus sign, and one trailing full stop. Currency symbols allowed in front: `$`. Any words, units, notes, negations, or a second number fail (e.g. `not 391`, `7 (indentation)`, `328 or 329`).
- It must equal 1157.63 within ±0.0001.

**Complexity rationale:** Three compounding steps plus a specified rounding rule.

**What changed from v4:** Strict final answer unchanged; `currency_symbols: ["$"]` made explicit (a dollar amount): `$1,157.63` passes, `€1,157.63` fails.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 1157.63, "tolerance": 0.0001, "final_answer": true, "strict_number": true, "currency_symbols": ["$"]}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C10

| Field | Value |
|---|---|
| Case ID | `C10` |
| Change from v4 | **unchanged from v4** |
| Task category | planning (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
A project has these tasks (duration in days; a task can start only when all its prerequisites have finished; tasks without a shared dependency can run in parallel):
A: 3 days, no prerequisites
B: 1 day, after A
C: 4 days, after A
D: 2 days, after B
E: 3 days, after C and D
G: 2 days, after B
F: 1 day, after E and G
What is the minimum total project duration, and which tasks form the critical path? Return JSON {"duration": number of days, "critical_path": [task letters in order]}.
~~~

**Expected answer characteristics:** {"duration": 11, "critical_path": ["A", "C", "E", "F"]} (unique longest path; A-B-D-E-F is 10 days).

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `duration` = `11`
- `critical_path` = `["A", "C", "E", "F"]` (list must match exactly, including order)
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** A seven-task dependency graph with parallel branches and a longest-path comparison.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"duration": 11, "critical_path": ["A", "C", "E", "F"]}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C11

| Field | Value |
|---|---|
| Case ID | `C11` |
| Change from v4 | **unchanged from v4** |
| Task category | classification (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Rules for a valid password: at least 10 characters, at least one digit, at least one uppercase letter, no spaces, and it must not contain the username "kai" in any letter case. Which of these candidates are valid?
1. Harbor2026Tide
2. sunset42meadow
3. Kai2026Rivers
4. Blue Fox 7781
5. Pine7
6. Quartz88Lantern
7. MAPLELEAFTRAIL
8. Orbit9StoneArc
Return JSON {"valid": [the valid passwords, exactly as written, in the order listed]}.
~~~

**Expected answer characteristics:** {"valid": ["Harbor2026Tide", "Quartz88Lantern", "Orbit9StoneArc"]}.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails.
- `valid` = `["Harbor2026Tide", "Quartz88Lantern", "Orbit9StoneArc"]` (list must match exactly, including order)
- Extra keys are ignored unless stated.  Strings are trimmed and compared case-insensitively; numbers numerically (so 80.0 = 80, but "80" ≠ 80); `null` must be JSON null; booleans must be JSON booleans.

**Complexity rationale:** Five rules × eight candidates.

**Remaining notes:**

- Character-level checks; candidate lengths (5, 13–15) are far from the 10-character boundary.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"valid": ["Harbor2026Tide", "Quartz88Lantern", "Orbit9StoneArc"]}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C12

| Field | Value |
|---|---|
| Case ID | `C12` |
| Change from v4 | **unchanged from v4** |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | custom validator (`meeting_schedule`) |

**Full prompt** (verbatim):

~~~text
Schedule three meetings between 09:00 and 11:00 with no overlaps: A lasts 60 minutes, B lasts 30 minutes, C lasts 30 minutes. A must start before B. C must end by 10:00. Return JSON {"A": "HH:MM", "B": "HH:MM", "C": "HH:MM"} giving each meeting's start time.
~~~

**Expected answer characteristics:** Any valid schedule, e.g. C 09:00, A 09:30, B 10:30.

**Acceptance criteria:**

- JSON with `A`, `B` and `C` start times (`HH:MM`). Every meeting must be within 09:00–11:00, with no overlaps, A must start before B, and C must end by 10:00.
- The only schedule that satisfies these is C 09:00, A 09:30, B 10:30.

**Complexity rationale:** Three intervals under four interacting constraints.

**Remaining notes:**

- The expected answer says "any valid schedule"; the constraints admit exactly one.

**Scoring spec** (verbatim):

~~~json
{"method": "validator", "name": "meeting_schedule"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

## Sign-off

After reviewing, record each case in `routewise_bench_v5.meta.yaml` → `reviewed_by`, e.g. `S01: {reviewer: "<name>", date: "YYYY-MM-DD", notes: ""}`.
Recording reviews edits only the meta file, so the dataset and pre-registration hashes stay valid. Editing any **case** changes the dataset hash, which then requires a new dataset version and pre-registration (before any run).
