# RouteWise Bench v2 — Review Pack

- **Dataset:** `evaluation/datasets/routewise_bench_v2.jsonl`, 45 cases (15 simple, 18 standard, 12 complex), SHA-256 `614e14497b380539baed24ad87f3619e11107d2adc35230004b652dec6994550`
- **Pre-registration:** `evaluation/preregistration_routewise_bench_v2.yaml`, SHA-256 `d90fb48cc1e62fe0a1bfa709b5acff85e39a12d56072ba4b63c33607f07b945f` (pinned in the meta file; the runner refuses a mismatch)
- **v1 kept unchanged:** `routewise_bench_v1.jsonl`, SHA-256 `5b0107d1834736932ea68f3bf5b1a3de9c814031c5b96f74349ff2be874841f7`
- **Status:** `draft-pending-human-review`. Nothing is marked reviewed. Changes: [`routewise_bench_v2.CHANGELOG.md`](routewise_bench_v2.CHANGELOG.md).
- **Generated:** 2026-11-04. Prompts and scoring specs are copied verbatim from the dataset; acceptance criteria are a plain-English reading of `backend/app/evaluation/scorers.py`.
- **No model or provider was called.** Every scoring rule is covered by local tests with correct, incorrect and edge-case answers written by hand (`backend/tests/evaluation/test_dataset_v2.py`). Every expected answer for a new case was computed independently by a local script.

## What the live comparison measures

With the current configuration, every enabled Groq model is OpenAI **GPT-OSS**: `gpt-oss-20b` (small tier) and `gpt-oss-120b` (premium tier), with no medium-tier model. A live run therefore compares **two sizes of one model family**, not independent model families. Results say nothing about routing across vendors, and "premium" means the best free model, not a frontier model. This is recorded in the pre-registration (`scope`).

## Change summary

| Change | Cases | IDs |
|---|---|---|
| unchanged | 13 | S01, S04, S06, S08, S11, S13, S15, T01, T13, T16, C01, C07, C12 |
| replaced | 12 | S02, S03, S10, T09, T10, T14, C02, C03, C04, C05, C10, C11 |
| moved | 2 | S05, T12 |
| scoring fixed | 7 | S07, S09, T02, T03, T08, T11, T17 |
| prompt + scoring fixed | 6 | S12, T04, T05, T07, C08, C09 |
| prompt fixed | 3 | S14, T06, T18 |
| task_type changed | 1 | T15 |
| rewritten | 1 | C06 |

## Complexity rubric

- **Simple:** one step. The answer is stated in or read directly off the prompt, or is one fact or one arithmetic operation, with a single-token or single-field output.
- **Standard:** two or three steps, or a structured output with several typed fields, or one inference beyond the text (date arithmetic, conditional logic, normalising several values).
- **Complex:** four or more dependent steps, several interacting constraints or rules, state that must be tracked over a sequence, or a distractor that must be recognised.
- Labels describe the reasoning required, not how often models fail. They only group the report; the router computes its own complexity score.

## Case index

| ID | Complexity | Category | Scoring | Change |
|---|---|---|---|---|
| [S01](#s01) | simple | classification | choice | unchanged |
| [S02](#s02) | simple | transformation | exact | replaced |
| [S03](#s03) | simple | classification | choice | replaced |
| [S04](#s04) | simple | classification | choice | unchanged |
| [S05](#s05) | simple | transformation | exact | moved |
| [S06](#s06) | simple | extraction | exact | unchanged |
| [S07](#s07) | simple | extraction | exact | scoring fixed |
| [S08](#s08) | simple | qa | exact | unchanged |
| [S09](#s09) | simple | math | numeric | scoring fixed |
| [S10](#s10) | simple | math | numeric | replaced |
| [S11](#s11) | simple | classification | exact | unchanged |
| [S12](#s12) | simple | classification | exact | prompt + scoring fixed |
| [S13](#s13) | simple | transformation | exact | unchanged |
| [S14](#s14) | simple | qa | choice | prompt fixed |
| [S15](#s15) | simple | extraction | json | unchanged |
| [T01](#t01) | standard | extraction | json | unchanged |
| [T02](#t02) | standard | extraction | json | scoring fixed |
| [T03](#t03) | standard | summarization | contains | scoring fixed |
| [T04](#t04) | standard | summarization | contains | prompt + scoring fixed |
| [T05](#t05) | standard | qa | exact | prompt + scoring fixed |
| [T06](#t06) | standard | classification | json | prompt fixed |
| [T07](#t07) | standard | transformation | contains | prompt + scoring fixed |
| [T08](#t08) | standard | code | regex | scoring fixed |
| [T09](#t09) | standard | code | numeric | replaced |
| [T10](#t10) | standard | code | numeric + ANSWER line | replaced |
| [T11](#t11) | standard | math | numeric | scoring fixed |
| [T12](#t12) | standard | math | regex + ANSWER line | moved |
| [T13](#t13) | standard | reasoning | exact | unchanged |
| [T14](#t14) | standard | transformation | json | replaced |
| [T15](#t15) | standard | math | json | task_type changed |
| [T16](#t16) | standard | qa | exact | unchanged |
| [T17](#t17) | standard | transformation | contains | scoring fixed |
| [T18](#t18) | standard | classification | json | prompt fixed |
| [C01](#c01) | complex | math | regex | unchanged |
| [C02](#c02) | complex | math | exact + ANSWER line | replaced |
| [C03](#c03) | complex | code | numeric + ANSWER line | replaced |
| [C04](#c04) | complex | reasoning | json | replaced |
| [C05](#c05) | complex | code | json | replaced |
| [C06](#c06) | complex | reasoning | exact + ANSWER line | rewritten |
| [C07](#c07) | complex | extraction | json | unchanged |
| [C08](#c08) | complex | math | numeric + ANSWER line | prompt + scoring fixed |
| [C09](#c09) | complex | math | numeric + ANSWER line | prompt + scoring fixed |
| [C10](#c10) | complex | planning | json | replaced |
| [C11](#c11) | complex | classification | json | replaced |
| [C12](#c12) | complex | reasoning | validator | unchanged |

## Simple (15)

### S01

| Field | Value |
|---|---|
| Case ID | `S01` |
| Change from v1 | **unchanged** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |

**Full prompt** (verbatim):

~~~text
Classify the sentiment of this review as positive, negative, or neutral. Reply with one word.
Review: The battery lasts two full days and the screen is gorgeous.
~~~

**Expected answer characteristics:** The single label 'positive'.

**Acceptance criteria:**

- Case-insensitive, whole-word search for `positive`, `negative`, `neutral`.
- Exactly one distinct label may appear, and it must be `positive`; two different labels fail.

**Complexity rationale:** Read one sentiment off one sentence.

**What changed:** Kept as the only sentiment case.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["positive", "negative", "neutral"], "answer": "positive"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S02

| Field | Value |
|---|---|
| Case ID | `S02` |
| Change from v1 | **replaced** |
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
- It must then equal `apple, mango, pear` or `apple,mango,pear` (case-insensitive). Extra words fail.

**Complexity rationale:** One operation on three words.

**What changed:** v1 S02 (negative sentiment) removed as a near-duplicate of S01. New: alphabetical sort (transformation), exact match with a no-space variant accepted.

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
| Change from v1 | **replaced** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |

**Full prompt** (verbatim):

~~~text
Which one of these animals is a mammal: shark, dolphin, trout? Reply with the animal's name only.
~~~

**Expected answer characteristics:** dolphin.

**Acceptance criteria:**

- Case-insensitive, whole-word search for `shark`, `dolphin`, `trout`.
- Exactly one distinct label may appear, and it must be `dolphin`; two different labels fail.

**Complexity rationale:** One fact.

**What changed:** v1 S03 (neutral sentiment) removed: a near-duplicate of S01 with an ambiguous label. New: mammal identification (choice).

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["shark", "dolphin", "trout"], "answer": "dolphin"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S04

| Field | Value |
|---|---|
| Case ID | `S04` |
| Change from v1 | **unchanged** |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |

**Full prompt** (verbatim):

~~~text
Classify this support ticket into exactly one category: billing, technical, shipping, account. Reply with the category only.
Ticket: I was charged twice for my March invoice.
~~~

**Expected answer characteristics:** The label 'billing'.

**Acceptance criteria:**

- Case-insensitive, whole-word search for `billing`, `technical`, `shipping`, `account`.
- Exactly one distinct label may appear, and it must be `billing`; two different labels fail.

**Complexity rationale:** One label, with an explicit keyword ("charged").

**What changed:** Kept; billing is unambiguous.

**Remaining notes:**

- Shares the ticket domain with T06, but at a different difficulty (one label vs label + urgency with definitions).

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["billing", "technical", "shipping", "account"], "answer": "billing"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S05

| Field | Value |
|---|---|
| Case ID | `S05` |
| Change from v1 | **moved** |
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
- It must then equal `+14155550132` (case-insensitive). Extra words fail.

**Complexity rationale:** Moved from standard: one mechanical reformat (prefix +1, strip punctuation). Investigated: it needs only knowing the E.164 shape, not multi-step reasoning.

**What changed:** v1 S05 (technical ticket) removed as a near-duplicate of S04. This slot now holds v1 T14 (E.164 phone formatting), relabelled simple. Prompt and scoring unchanged.

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
| Change from v1 | **unchanged** |
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
- It must then equal `maria.lopez@example.org` (case-insensitive). Extra words fail.

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
| Change from v1 | **scoring fixed** |
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
- It must then equal `2026-03-14` (case-insensitive). Extra words fail.

**Complexity rationale:** One reformat of a stated date.

**What changed:** False fail: the regex rejected `2026-03-14.`, so it's now `exact` (which strips punctuation). The prompt now says "quarterly review" to match the text.

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
| Change from v1 | **unchanged** |
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
- It must then equal `canberra` (case-insensitive). Extra words fail.

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
| Change from v1 | **scoring fixed** |
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

- The **last** number in the answer is used (thousands commas ignored), so restated working is fine.
- It must equal 391 within ±0.

**Complexity rationale:** One multiplication.

**What changed:** False fail: `17 x 23 = 391` failed because it has several numbers. Now `last_number`.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 391, "tolerance": 0, "last_number": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S10

| Field | Value |
|---|---|
| Case ID | `S10` |
| Change from v1 | **replaced** |
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

- The answer must contain **exactly one** number (thousands commas ignored).
- It must equal 0.9 within ±0.

**Complexity rationale:** One comparison (a known LLM pitfall, but one step).

**What changed:** v1 S10 (km to m) removed as a near-duplicate arithmetic skill. New: decimal comparison 0.9 vs 0.11 (numeric).

**Remaining notes:**

- Decimal comparison is a widely discussed model failure, so it may be represented in training data; kept because it's objective and one step.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 0.9, "tolerance": 0}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S11

| Field | Value |
|---|---|
| Case ID | `S11` |
| Change from v1 | **unchanged** |
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
- It must then equal `french` (case-insensitive). Extra words fail.

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
| Change from v1 | **prompt + scoring fixed** |
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
- It must then equal `spam` (case-insensitive). Extra words fail.

**Complexity rationale:** One label.

**What changed:** False pass: `Not spam` matched `spam`. Labels are now spam / legitimate, and scoring is `exact`, so negations and extra words fail.

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
| Change from v1 | **unchanged** |
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
- It must then equal `SHIP IT TODAY` (case-sensitive). Extra words fail.

**Complexity rationale:** One mechanical transform.

**Remaining notes:**

- task_type is `extraction` because the router has no `transformation` type; kept for consistency with v1.

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
| Change from v1 | **prompt fixed** |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |

**Full prompt** (verbatim):

~~~text
At standard atmospheric pressure (1 atm), does pure water boil at approximately 100 degrees Celsius? Answer yes or no.
~~~

**Expected answer characteristics:** yes (about 99.97 °C, i.e. approximately 100 °C).

**Acceptance criteria:**

- Case-insensitive, whole-word search for `yes`, `no`.
- Exactly one distinct label may appear, and it must be `yes`; two different labels fail.

**Complexity rationale:** One fact.

**What changed:** False fail on a pedantic correct answer. Now asks "at standard atmospheric pressure (1 atm) … approximately 100 °C".

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["yes", "no"], "answer": "yes"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S15

| Field | Value |
|---|---|
| Case ID | `S15` |
| Change from v1 | **unchanged** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `name` = `"Priya"`
- `age` = `34`
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

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
| Change from v1 | **unchanged** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `invoice_number` = `"INV-2026-0042"`
- `total_amount` = `1250`
- `currency` = `"EUR"`
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Investigated (flagged arguably simple). Kept standard: three fields, each needing normalisation ("EUR 1,250.00" → number 1250 and ISO code EUR; ignore the due date), into typed JSON. That's more than reading one span.

**What changed:** Label kept as standard (see rationale).

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
| Change from v1 | **scoring fixed** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `people` has exactly 3 items
- the item with `name` = `Dana Kim` has `role` `product manager`
- the item with `name` = `Luis Ortega` has `role` `backend engineer` or `back-end engineer`
- the item with `name` = `Aiko Sato` has `role` `designer`
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** List extraction with name→role pairing and an exact count.

**What changed:** False pass: roles weren't checked. Now checks each name→role pair (with a `back-end` variant) and exactly 3 people.

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
| Change from v1 | **scoring fixed** |
| Task category | summarization (router `task_type`: `summarization`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |

**Full prompt** (verbatim):

~~~text
Summarise this incident report in at most two sentences.
Report: On Monday at 09:12 UTC the primary database ran out of disk space, causing checkout failures for 45 minutes. Engineers expanded the storage volume, restored service, and added an alert that fires when disk usage passes 80%.
~~~

**Expected answer characteristics:** Mentions the disk running out, the 45-minute impact, and the new alert; short.

**Acceptance criteria:**

- Case-insensitive checks; all must hold:
- contains `disk`
- contains `45`
- contains `alert`
- at most 70 words
- at most 2 sentences (a sentence ends at `.`, `!` or `?` followed by a space or the end)

**Complexity rationale:** Select three key facts and compress under two constraints (≤ 2 sentences, ≤ 70 words).

**What changed:** False pass: the two-sentence limit wasn't checked. `max_sentences: 2` added.

**Remaining notes:**

- Still a keyword proxy for summary quality: it checks that the key facts are present and the length limits are met, not fluency.
- Abbreviations such as "e.g." count as sentence ends, so a summary using them could be over-counted (a false fail).

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "all": ["disk", "45", "alert"], "max_words": 70, "max_sentences": 2}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T04

| Field | Value |
|---|---|
| Case ID | `T04` |
| Change from v1 | **prompt + scoring fixed** |
| Task category | summarization (router `task_type`: `summarization`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |

**Full prompt** (verbatim):

~~~text
List only the decisions that were made in these meeting notes, as a short bulleted list. Do not mention topics that were discussed but left undecided.
Notes: We agreed to move the launch to 2 June. Marketing will own the press release. We discussed pricing but postponed a decision. Engineering will freeze features on 20 May.
~~~

**Expected answer characteristics:** The three decisions (launch on 2 June, marketing owns the press release, feature freeze on 20 May), with no mention of pricing.

**Acceptance criteria:**

- Case-insensitive checks; all must hold:
- contains one of `2 june`, `june 2`, `2nd june`, `june 2nd`
- contains one of `press release`
- contains one of `20 may`, `may 20`, `20th may`, `may 20th`
- does not contain the whole word `pricing`
- does not contain the whole word `price`
- does not contain the whole word `prices`

**Complexity rationale:** Separate decisions from non-decisions (one inference) and list three items.

**What changed:** False fail on `June 2`, false pass when pricing was listed. Each date now accepts day-first, month-first and ordinal forms; the prompt forbids undecided topics and the scorer rejects the words pricing/price.

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "groups": [["2 june", "june 2", "2nd june", "june 2nd"], ["press release"], ["20 may", "may 20", "20th may", "may 20th"]], "none_words": ["pricing", "price", "prices"]}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T05

| Field | Value |
|---|---|
| Case ID | `T05` |
| Change from v1 | **prompt + scoring fixed** |
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
- It must then equal `thursday` (case-insensitive). Extra words fail.

**Complexity rationale:** Passage reading plus one date-arithmetic step.

**What changed:** "Happened on … slipped" was contradictory, so it now says "were scheduled for". `contains` → `exact`, so hedged answers ("Tuesday or Thursday") fail.

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
| Change from v1 | **prompt fixed** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `category` = `"account"`
- `urgency` = `"high"`
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Two independent classifications against given definitions.

**What changed:** Account vs technical was ambiguous. The prompt now defines every category (account = sign-in, passwords, access) and every urgency level.

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
| Change from v1 | **prompt + scoring fixed** |
| Task category | transformation (router `task_type`: `creative`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |

**Full prompt** (verbatim):

~~~text
Rewrite this message so it is polite and professional while keeping the same request. Requirements: include the word "please", mention the report, and do not use the words "now" or "late". Reply with the rewritten message only.
Message: Send me the report now, you are already late.
~~~

**Expected answer characteristics:** A polite request for the report that contains "please" and avoids the words "now" and "late".

**Acceptance criteria:**

- Case-insensitive checks; all must hold:
- contains `report`
- contains the whole word `please`
- does not contain the whole word `now`
- does not contain the whole word `late`
- at most 60 words

**Complexity rationale:** Rewrite under four explicit constraints.

**What changed:** False fail on polite wording missing from the keyword list. Now an explicit instruction-following rewrite: must contain the whole word `please` and `report`, must not contain the whole words `now`/`late`, ≤ 60 words.

**Remaining notes:**

- Measures following explicit rewrite instructions, not politeness quality.

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "all": ["report"], "all_words": ["please"], "none_words": ["now", "late"], "max_words": 60}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T08

| Field | Value |
|---|---|
| Case ID | `T08` |
| Change from v1 | **scoring fixed** |
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

**What changed:** False fail on table aliases. A new anchored pattern allows aliases, `AS`, `ASC`, a trailing `;` and code fences, but rejects extra columns, `DESC` and a missing `ORDER BY`.

**Remaining notes:**

- Equivalent but unusual SQL (subqueries, `IN ('Germany')`, double-quoted strings) fails; the prompt asks for a straightforward query.

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
| Change from v1 | **replaced** |
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

- The answer must contain **exactly one** number (thousands commas ignored).
- It must equal 14 within ±0.

**Complexity rationale:** Trace three statements (sort, slice, sum).

**What changed:** v1 T09 (palindrome; LeetCode 125 example inputs; executed model code) removed. New: predict a short program's output (non-executable code reasoning).

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 14, "tolerance": 0}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T10

| Field | Value |
|---|---|
| Case ID | `T10` |
| Change from v1 | **replaced** |
| Task category | code (router `task_type`: `code`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
The function below should return the average of the positive numbers in a list, or 0.0 if there are none, but one line has a bug. Which line number contains the bug? Explain briefly. End your reply with a final line of the form ANSWER: <line number>.
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
- The **first** number on the ANSWER line is used, so a trailing note is fine.
- It must equal 7 within ±0.

**Complexity rationale:** Read eight lines, compare them with the stated intent, and locate the faulty line.

**What changed:** v1 T10 (FizzBuzz; ubiquitous; executed model code) removed. New: find the buggy line in a numbered function, with the answer on an `ANSWER:` line.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 7, "tolerance": 0, "final_answer": true, "first_number": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T11

| Field | Value |
|---|---|
| Case ID | `T11` |
| Change from v1 | **scoring fixed** |
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

- The **last** number in the answer is used (thousands commas ignored), so restated working is fine.
- It must equal 33 within ±0.001.

**Complexity rationale:** Two chained percentage operations.

**What changed:** False fail when the working was restated. Now `last_number`.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 33, "tolerance": 0.001, "last_number": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T12

| Field | Value |
|---|---|
| Case ID | `T12` |
| Change from v1 | **moved** |
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
- Pattern searched in the trimmed answer (or the ANSWER value): `^5\s*/\s*36\b`
- In plain terms: the ANSWER value must start with `5/36` (spaces around `/` allowed).

**Complexity rationale:** Moved from complex. Investigated: enumerate the five outcomes and reduce 5/36; that's two steps, standard.

**What changed:** v1 T12 (one-step syllogism) removed as too easy for standard. This slot now holds v1 C02 (dice probability), relabelled standard, with an `ANSWER:` line, which fixes the v1 false pass where 5/36 could appear anywhere.

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "^5\\s*/\\s*36\\b", "final_answer": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T13

| Field | Value |
|---|---|
| Case ID | `T13` |
| Change from v1 | **unchanged** |
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
- It must then equal `thursday` (case-insensitive). Extra words fail.

**Complexity rationale:** Investigated (flagged possibly complex). Kept standard: one anchor date plus one modular-arithmetic step. Its difficulty for models comes from computing without tools, not from reasoning depth. That's noted as a fairness point, not a label change.

**What changed:** Label kept as standard (see rationale).

**Remaining notes:**

- Calendar arithmetic without tools favours reasoning models. All currently enabled Groq models are reasoning models (GPT-OSS).

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
| Change from v1 | **replaced** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `dates` = `["2026-02-03", "2026-02-14", "2026-03-01", "2026-04-01"]` (lists must match exactly, including order)
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Four values in three different input formats, normalised and kept in order.

**What changed:** v1 T14 moved to S05. New: normalise four dates in mixed formats to ISO 8601 (JSON list).

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
| Change from v1 | **task_type changed** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `total` is a JSON number equal to 9.9 ± 0.001
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Two multiplications and a sum, as typed JSON.

**What changed:** task_type `extraction` → `reasoning` (it's arithmetic). Prompt and scoring unchanged.

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
| Change from v1 | **unchanged** |
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
- It must then equal `NOT_IN_CONTEXT` (case-sensitive). Extra words fail.

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
| Change from v1 | **scoring fixed** |
| Task category | transformation (router `task_type`: `creative`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |

**Full prompt** (verbatim):

~~~text
Translate into Spanish. Reply with the translation only.
Text: The library opens at nine o'clock.
~~~

**Expected answer characteristics:** A Spanish sentence saying the library (biblioteca) opens (abre) at nine (nueve / 9).

**Acceptance criteria:**

- Case-insensitive checks; all must hold:
- contains one of `biblioteca`
- contains one of `abre`
- contains one of `nueve`, `9`
- does not contain the whole word `cierra`

**Complexity rationale:** Translation of one sentence with three content words checked.

**What changed:** False pass on a wrong verb. The scorer now requires biblioteca + abre + nueve/9 and rejects `cierra`.

**Remaining notes:**

- A keyword proxy for translation: it checks subject, verb and time, not grammar.

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "groups": [["biblioteca"], ["abre"], ["nueve", "9"]], "none_words": ["cierra"]}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T18

| Field | Value |
|---|---|
| Case ID | `T18` |
| Change from v1 | **prompt fixed** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `defect` = `true`
- `part` = `"zipper"`
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Two judgements (defect yes/no, which part) as typed JSON.

**What changed:** `zip` vs `zipper`: the part must now be written exactly as in the review.

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
| Change from v1 | **unchanged** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | regular expression |

**Full prompt** (verbatim):

~~~text
Train A leaves a station at 08:15 travelling at 120 km/h. Train B leaves the same station at 09:00 on a parallel track in the same direction at 150 km/h. At what time does train B draw level with train A? Show your reasoning briefly, then give the final answer on the last line as HH:MM (24-hour).
~~~

**Expected answer characteristics:** 12:00 (A is 90 km ahead at 09:00; closing speed 30 km/h; 3 hours).

**Acceptance criteria:**

- Pattern searched in the trimmed answer (or the ANSWER value): `12:00\s*\W*\s*$`
- In plain terms: the answer must end with `12:00`, optionally followed only by punctuation or markdown.

**Complexity rationale:** Investigated (flagged arguably standard). Kept complex: head start (0.75 h × 120 = 90 km), closing speed (30 km/h), catch-up time (3 h) and clock addition. That's four dependent steps in mixed units.

**What changed:** Label kept as complex (see rationale).

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "12:00\\s*\\W*\\s*$"}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C02

| Field | Value |
|---|---|
| Case ID | `C02` |
| Change from v1 | **replaced** |
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
- It must then equal `08:34` or `8:34` (case-insensitive). Extra words fail.

**Complexity rationale:** Three phases with different net rates, a threshold crossing inside a phase, and a distractor event after the answer.

**What changed:** v1 C02 moved to T12. New: tank fill problem with piecewise rates and a distractor event, answered on an `ANSWER:` line.

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
| Change from v1 | **replaced** |
| Task category | code (router `task_type`: `code`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
What does this Python program print? Trace it step by step. End your reply with a final line of the form ANSWER: <number>.
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
- The **first** number on the ANSWER line is used, so a trailing note is fine.
- It must equal 11 within ±0.

**Complexity rationale:** Track a dict and an accumulator over seven iterations (state over a sequence).

**What changed:** v1 C03 (merge intervals; LeetCode 56 example input; executed model code) removed. New: trace a program that sums gaps between repeated values.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 11, "tolerance": 0, "final_answer": true, "first_number": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C04

| Field | Value |
|---|---|
| Case ID | `C04` |
| Change from v1 | **replaced** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `Ana` = `30`
- `Ben` = `10`
- `Cara` = `0`
- `rejected` = `1`
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Track three balances over eight events with a conditional rejection rule.

**What changed:** v1 C04 (Roman numerals; LeetCode 13 example inputs; executed model code) removed. New: apply 8 ledger events with a rejection rule (JSON).

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
| Change from v1 | **replaced** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `rows` = `[["Cara", 120], ["Abe", 75]]` (lists must match exactly, including order)
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Filter, group, aggregate, apply HAVING and sort, by hand over seven rows.

**What changed:** v1 C05 (top-k words; LeetCode 692 example inputs verbatim; executed model code) removed. New: predict a GROUP BY / HAVING / ORDER BY query result over given rows (JSON).

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
| Change from v1 | **rewritten** |
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
- It must then equal `Eli` (case-insensitive). Extra words fail.

**Complexity rationale:** Five variables and six constraints; elimination needs about four chained deductions.

**What changed:** v1 4-person puzzle relabel investigated: 3 clues was standard-level. Rewritten as a 5-person, 6-constraint puzzle with a unique solution (brute-force checked), answered on an `ANSWER:` line.

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
| Change from v1 | **unchanged** |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | JSON structure |

**Full prompt** (verbatim):

~~~text
Extract the order from this email as JSON with keys "customer" (string), "items" (list of {"sku": string, "quantity": integer}) and "total_units" (integer, the sum of all quantities). Merge repeated SKUs.
Email: Hi, this is Omar Haddad. Please send 2 units of SKU-118 and 5 of SKU-204. Actually, add 3 more of SKU-118 as well. Thanks!
~~~

**Expected answer characteristics:** customer Omar Haddad; SKU-118 x5, SKU-204 x5; total_units 10.

**Acceptance criteria:**

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `customer` = `"Omar Haddad"`
- `total_units` = `10`
- `items[].sku` includes `SKU-118`, `SKU-204`
- summing `quantity` per `sku`: `SKU-118` → 5, `SKU-204` → 5
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Extract, merge repeated SKUs, sum, and emit nested typed JSON.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"customer": "Omar Haddad", "total_units": 10}, "list_contains": {"path": "items", "key": "sku", "values": ["SKU-118", "SKU-204"]}, "list_values": {"path": "items", "key": "sku", "value_key": "quantity", "expected": {"SKU-118": 5, "SKU-204": 5}}}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C08

| Field | Value |
|---|---|
| Case ID | `C08` |
| Change from v1 | **prompt + scoring fixed** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
What is the sum of all prime numbers less than 50? Work it out. End your reply with a final line of the form ANSWER: <number>.
~~~

**Expected answer characteristics:** 328.

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- The **first** number on the ANSWER line is used, so a trailing note is fine.
- It must equal 328 within ±0.

**Complexity rationale:** Enumerate 15 primes and sum them (long bookkeeping).

**What changed:** False fail on `328 (from 15 primes)`. Now `ANSWER:` line + first number on it.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 328, "tolerance": 0, "final_answer": true, "first_number": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C09

| Field | Value |
|---|---|
| Case ID | `C09` |
| Change from v1 | **prompt + scoring fixed** |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |

**Full prompt** (verbatim):

~~~text
$1,000 is invested at 5% annual interest, compounded annually, for 3 years. What is the final amount in dollars, rounded to 2 decimal places? Show the calculation briefly. End your reply with a final line of the form ANSWER: <number>.
~~~

**Expected answer characteristics:** 1157.63 (1000 x 1.05^3 = 1157.625).

**Acceptance criteria:**

- Only the value on the **last `ANSWER:` line** is scored (markdown such as `**ANSWER:** x` is tolerated). A missing `ANSWER:` line fails.
- The **first** number on the ANSWER line is used, so a trailing note is fine.
- It must equal 1157.63 within ±0.006.

**Complexity rationale:** Three compounding steps plus rounding.

**What changed:** Same `ANSWER:` convention, so a trailing note such as "to 2 d.p." can't be misread as the answer.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 1157.63, "tolerance": 0.006, "final_answer": true, "first_number": true}
~~~

**Reviewer decision:** ☐ accept · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C10

| Field | Value |
|---|---|
| Case ID | `C10` |
| Change from v1 | **replaced** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `duration` = `11`
- `critical_path` = `["A", "C", "E", "F"]` (lists must match exactly, including order)
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** A dependency graph with seven tasks, parallel branches and a longest-path comparison.

**What changed:** v1 C10 (subjective concurrency essay, human-graded) removed. New: critical-path duration and path (JSON, unique longest path).

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
| Change from v1 | **replaced** |
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

- The answer must parse as JSON. A fenced block is unwrapped; prose around unfenced JSON fails. Extra keys are ignored.
- `valid` = `["Harbor2026Tide", "Quartz88Lantern", "Orbit9StoneArc"]` (lists must match exactly, including order)
- Strings are trimmed and compared case-insensitively; numbers numerically; booleans must be JSON booleans; list values are compared exactly (case-sensitive).

**Complexity rationale:** Five rules × eight candidates, including a case-insensitive substring rule and a space rule.

**What changed:** v1 C11 (duration parser; executed model code; under-tested) removed. New: apply five password rules to eight candidates (JSON list).

**Remaining notes:**

- Involves character-level checks. The candidate lengths (5, 13–15) are deliberately far from the 10-character boundary to reduce sensitivity to tokenisation.

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
| Change from v1 | **unchanged** |
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

**Complexity rationale:** Three intervals under four interacting constraints (search for a feasible schedule).

**What changed:** The constraints admit exactly one schedule (09:30 / 10:30 / 09:00, brute-force checked at 1-minute granularity); the validator accepts any valid schedule.

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

After reviewing, record each case in `routewise_bench_v2.meta.yaml` → `reviewed_by`, e.g. `S01: {reviewer: "<name>", date: "YYYY-MM-DD", notes: ""}`.
Until all 45 entries exist, the dataset isn't fully reviewed and no report is publishable. Editing any case changes the dataset hash. The pre-registration is pinned to that hash, so record a new pre-registration version (before any run) if you edit cases.
