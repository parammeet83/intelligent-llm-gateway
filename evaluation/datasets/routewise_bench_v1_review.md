# RouteWise Bench v1 — Review Pack

- **Dataset:** `evaluation/datasets/routewise_bench_v1.jsonl`, 45 cases, SHA-256 `5b0107d1834736932ea68f3bf5b1a3de9c814031c5b96f74349ff2be874841f7`
- **Status:** `draft-pending-human-review`. This file **does not** mark anything as reviewed, and the dataset was not changed.
- **Generated:** 2026-11-04 from the dataset file. Prompts, expected answers and scoring specs are copied verbatim; acceptance criteria are a plain-English reading of the scorer code (`backend/app/evaluation/scorers.py`).
- **Flags** are the AI drafter's own critique. Every `SCORE` flag was checked by running the real scorer on a handwritten sample answer (no model or provider calls). Contamination (`FAV`) notes are from memory and must be verified by you.

## How to use

1. For each case, check that the prompt is unambiguous, the expected answer is correct, and the acceptance criteria accept **all and only** correct answers.
2. Tick a decision per case. Edits go into the `.jsonl` (ask and they can be applied), followed by the reference-answer tests (`uv run pytest tests/evaluation`).
3. When every case is accepted or fixed, record the review in `routewise_bench_v1.meta.yaml` → `reviewed_by` (one entry per case). Only then can a report be publishable.

## Flag summary

| Code | Meaning | Cases |
|---|---|---|
| `DUP` | Duplicate / near-duplicate | 9: S01, S02, S03, S04, S05, S09, S10, S15, T06 |
| `AMB` | Ambiguous prompt or acceptance criteria | 13: S03, S07, S14, T05, T06, T09, T10, T18, C03, C04, C05, C10, C11 |
| `SCORE` | Scorer accepts a wrong answer or rejects a right one | 12: S07, S09, S12, T02, T03, T04, T07, T08, T11, T17, C02, C08 |
| `LABEL` | Complexity label questionable | 9: T01, T10, T12, T13, T14, C01, C02, C04, C06 |
| `FAV` | May unfairly favour a model (incl. contamination) | 6: T09, T10, T13, C03, C04, C05 |
| `SUBJ` | Not objectively evaluable by the scorer | 4: T03, T07, T17, C10 |
| `TASK` | task_type differs from category | 5: S13, T07, T14, T15, T17 |

Unflagged cases (7): S06, S08, S11, T16, C07, C09, C12.

### Highest-priority issues

1. **False passes** (wrong answers scored correct): S12 (`Not spam`), T02 (roles unchecked), T03 (sentence limit unchecked), T04 (undecided pricing listed), T17 (wrong verb), C02 (unanchored pattern), C10 (keyword-only). These inflate pass rates for every strategy and hide quality differences.
2. **False fails** (right answers scored wrong): S07 (trailing period), T04 (US date order), T06 (defensible `technical`), T07 (polite wording off-list), T08 (table alias), S14 (pedantic answer), plus strict single-number rules (S09, T11, C08). These penalise verbose or differently formatted but correct models.
3. **Possible contamination:** T09, C03, C04 and C05 use test inputs that match well-known public coding exercises (C05 contains the word "leetcode"). This conflicts with the meta file's licence line, "no examples copied from public benchmarks". Suggest replacing them with original inputs.
4. **Questionable complexity labels:** T01, T10, T12 and T14 look simple; C01, C02, C04 and C06 look standard; T13 may be complex. The labels only group the report (the router computes its own score), but they shape the by-difficulty results.
5. **Not objectively evaluable:** C10 (needs a human grade), T07, T03 and T17 (keyword proxies for quality). Consider removing C10 from the automatic pass rate or grading it by hand.

### Dataset-wide notes

- **Code cases** (T09, T10, C03, C04, C05, C11; 6 of 45) are scored only with `--allow-code-exec`. Without it they're reported as not scorable, which shrinks the effective sample to 39.
- **Near-duplicate templates** (S01–S03 sentiment; S04/S05/T06 tickets; S09/S10 arithmetic) reduce the number of independent signals, which matters with only 45 cases.
- **Model favouritism:** no prompt targets a vendor-specific feature. The current Groq tiers are one model family (`gpt-oss-20b` small vs `gpt-oss-120b` premium), so the benchmark will mostly compare model size within that family. Strict "reply with X only" formats reward instruction-following; that's intended, but it combines with the false fails above.
- **task_type**: the router has no `transformation` or `math` task type, so math cases use `qa`/`reasoning` by design. The choice looks debatable in S13, T07, T14, T15 and T17 (flagged `TASK`). task_type feeds the router's score, so check that you agree with each.

## Case index

| ID | Complexity | Category | Scoring | Flags |
|---|---|---|---|---|
| [S01](#s01) | simple | classification | choice | DUP |
| [S02](#s02) | simple | classification | choice | DUP |
| [S03](#s03) | simple | classification | choice | AMB, DUP |
| [S04](#s04) | simple | classification | choice | DUP |
| [S05](#s05) | simple | classification | choice | DUP |
| [S06](#s06) | simple | extraction | exact | — |
| [S07](#s07) | simple | extraction | regex | AMB, SCORE |
| [S08](#s08) | simple | qa | exact | — |
| [S09](#s09) | simple | math | numeric | DUP, SCORE |
| [S10](#s10) | simple | math | numeric | DUP |
| [S11](#s11) | simple | classification | exact | — |
| [S12](#s12) | simple | classification | choice | SCORE |
| [S13](#s13) | simple | transformation | exact | TASK |
| [S14](#s14) | simple | qa | choice | AMB |
| [S15](#s15) | simple | extraction | json | DUP |
| [T01](#t01) | standard | extraction | json | LABEL |
| [T02](#t02) | standard | extraction | json | SCORE |
| [T03](#t03) | standard | summarization | contains | SCORE, SUBJ |
| [T04](#t04) | standard | summarization | contains | SCORE |
| [T05](#t05) | standard | qa | contains | AMB |
| [T06](#t06) | standard | classification | json | AMB, DUP |
| [T07](#t07) | standard | transformation | contains | SCORE, SUBJ, TASK |
| [T08](#t08) | standard | code | regex | SCORE |
| [T09](#t09) | standard | code | code | AMB, FAV |
| [T10](#t10) | standard | code | code | AMB, FAV, LABEL |
| [T11](#t11) | standard | math | numeric | SCORE |
| [T12](#t12) | standard | reasoning | choice | LABEL |
| [T13](#t13) | standard | reasoning | exact | FAV, LABEL |
| [T14](#t14) | standard | transformation | exact | LABEL, TASK |
| [T15](#t15) | standard | math | json | TASK |
| [T16](#t16) | standard | qa | exact | — |
| [T17](#t17) | standard | transformation | contains | SCORE, SUBJ, TASK |
| [T18](#t18) | standard | classification | json | AMB |
| [C01](#c01) | complex | math | regex | LABEL |
| [C02](#c02) | complex | math | regex | LABEL, SCORE |
| [C03](#c03) | complex | code | code | AMB, FAV |
| [C04](#c04) | complex | code | code | AMB, FAV, LABEL |
| [C05](#c05) | complex | code | code | AMB, FAV |
| [C06](#c06) | complex | reasoning | regex | LABEL |
| [C07](#c07) | complex | extraction | json | — |
| [C08](#c08) | complex | math | numeric | SCORE |
| [C09](#c09) | complex | math | numeric | — |
| [C10](#c10) | complex | analysis | contains | AMB, SUBJ |
| [C11](#c11) | complex | code | code | AMB |
| [C12](#c12) | complex | reasoning | validator | — |

## Simple (15)

### S01

| Field | Value |
|---|---|
| Case ID | `S01` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |
| Flags | DUP |

**Full prompt** (verbatim):

~~~text
Classify the sentiment of this review as positive, negative, or neutral. Reply with one word.
Review: The battery lasts two full days and the screen is gorgeous.
~~~

**Expected answer characteristics:** The single label 'positive'.

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `positive`, `negative`, `neutral` (longest first).
- Exactly one distinct label may appear, and it must be `positive`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["positive", "negative", "neutral"], "answer": "positive"}
~~~

**Review flags:**

- **DUP**: S01–S03 use the same sentiment template and differ only in the review sentence.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S02

| Field | Value |
|---|---|
| Case ID | `S02` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |
| Flags | DUP |

**Full prompt** (verbatim):

~~~text
Classify the sentiment of this review as positive, negative, or neutral. Reply with one word.
Review: The package arrived crushed and support never replied to my emails.
~~~

**Expected answer characteristics:** The single label 'negative'.

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `positive`, `negative`, `neutral` (longest first).
- Exactly one distinct label may appear, and it must be `negative`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["positive", "negative", "neutral"], "answer": "negative"}
~~~

**Review flags:**

- **DUP**: Same template as S01/S03.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S03

| Field | Value |
|---|---|
| Case ID | `S03` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |
| Flags | AMB, DUP |

**Full prompt** (verbatim):

~~~text
Classify the sentiment of this review as positive, negative, or neutral. Reply with one word.
Review: The parcel was delivered on Tuesday.
~~~

**Expected answer characteristics:** The single label 'neutral' (a factual statement with no opinion).

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `positive`, `negative`, `neutral` (longest first).
- Exactly one distinct label may appear, and it must be `neutral`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["positive", "negative", "neutral"], "answer": "neutral"}
~~~

**Review flags:**

- **DUP**: Same template as S01/S02.
- **AMB**: Low risk: "delivered on Tuesday" is factual, but a model could read timely delivery as mildly positive.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S04

| Field | Value |
|---|---|
| Case ID | `S04` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |
| Flags | DUP |

**Full prompt** (verbatim):

~~~text
Classify this support ticket into exactly one category: billing, technical, shipping, account. Reply with the category only.
Ticket: I was charged twice for my March invoice.
~~~

**Expected answer characteristics:** The label 'billing'.

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `billing`, `technical`, `shipping`, `account` (longest first).
- Exactly one distinct label may appear, and it must be `billing`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["billing", "technical", "shipping", "account"], "answer": "billing"}
~~~

**Review flags:**

- **DUP**: S04, S05 and T06 share the support-ticket template and categories.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S05

| Field | Value |
|---|---|
| Case ID | `S05` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |
| Flags | DUP |

**Full prompt** (verbatim):

~~~text
Classify this support ticket into exactly one category: billing, technical, shipping, account. Reply with the category only.
Ticket: The app crashes every time I open the camera screen.
~~~

**Expected answer characteristics:** The label 'technical'.

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `billing`, `technical`, `shipping`, `account` (longest first).
- Exactly one distinct label may appear, and it must be `technical`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["billing", "technical", "shipping", "account"], "answer": "technical"}
~~~

**Review flags:**

- **DUP**: Same template as S04.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S06

| Field | Value |
|---|---|
| Case ID | `S06` |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |
| Flags | none |

**Full prompt** (verbatim):

~~~text
Extract the email address from this text. Reply with the address only.
Text: For refunds contact Maria at maria.lopez@example.org before Friday.
~~~

**Expected answer characteristics:** Exactly maria.lopez@example.org.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal `maria.lopez@example.org` (case-insensitive).

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "maria.lopez@example.org"}
~~~

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S07

| Field | Value |
|---|---|
| Case ID | `S07` |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | regular expression |
| Flags | AMB, SCORE |

**Full prompt** (verbatim):

~~~text
On what date is the meeting? Reply in YYYY-MM-DD format only.
Text: The quarterly review moved to 14 March 2026 at 10:00.
~~~

**Expected answer characteristics:** 2026-03-14.

**Acceptance criteria:**

- The whole answer, ignoring surrounding whitespace, must be exactly `2026-03-14`. Nothing else is allowed, not even a trailing period.
- Pattern (searched in the trimmed answer): `^\s*2026-03-14\s*$`

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "^\\s*2026-03-14\\s*$"}
~~~

**Review flags:**

- **SCORE**: **False fail:** a correct `2026-03-14.` (trailing period) fails, because this regex doesn't strip punctuation the way `exact` does. Probe confirmed.
- **AMB**: Minor: the prompt asks for "the meeting" but the text says "quarterly review".

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S08

| Field | Value |
|---|---|
| Case ID | `S08` |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |
| Flags | none |

**Full prompt** (verbatim):

~~~text
What is the capital city of Australia? Reply with the city name only.
~~~

**Expected answer characteristics:** Canberra.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal `canberra` (case-insensitive).

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "canberra"}
~~~

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S09

| Field | Value |
|---|---|
| Case ID | `S09` |
| Task category | math (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | numeric |
| Flags | DUP, SCORE |

**Full prompt** (verbatim):

~~~text
What is 17 multiplied by 23? Reply with the number only.
~~~

**Expected answer characteristics:** 391.

**Acceptance criteria:**

- The answer must contain **exactly one** number (thousands commas ignored); several numbers fail as ambiguous.
- It must equal 391 within ±0.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 391, "tolerance": 0}
~~~

**Review flags:**

- **SCORE**: **False fail:** a correct `17 x 23 = 391` fails, because with several numbers the scorer refuses to guess. The prompt does say "number only", so this is arguably fair but strict. Probe confirmed.
- **DUP**: Near-duplicate skill with S10 (one-step arithmetic).

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S10

| Field | Value |
|---|---|
| Case ID | `S10` |
| Task category | math (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | numeric |
| Flags | DUP |

**Full prompt** (verbatim):

~~~text
Convert 2.5 kilometres to metres. Reply with the number only.
~~~

**Expected answer characteristics:** 2500.

**Acceptance criteria:**

- The answer must contain **exactly one** number (thousands commas ignored); several numbers fail as ambiguous.
- It must equal 2500 within ±0.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 2500, "tolerance": 0}
~~~

**Review flags:**

- **DUP**: Near-duplicate skill with S09. (`2,500` is accepted; probe confirmed.)

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S11

| Field | Value |
|---|---|
| Case ID | `S11` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |
| Flags | none |

**Full prompt** (verbatim):

~~~text
Which language is this sentence written in? Reply with the language name in English only.
Sentence: Je voudrais un café, s'il vous plaît.
~~~

**Expected answer characteristics:** French.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal `french` (case-insensitive).

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "french"}
~~~

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S12

| Field | Value |
|---|---|
| Case ID | `S12` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |
| Flags | SCORE |

**Full prompt** (verbatim):

~~~text
Label this message as spam or not_spam. Reply with the label only.
Message: Congratulations! You won a $1,000 gift card. Click here to claim now.
~~~

**Expected answer characteristics:** spam.

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `spam`, `not_spam` (longest first).
- Exactly one distinct label may appear, and it must be `spam`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["spam", "not_spam"], "answer": "spam"}
~~~

**Review flags:**

- **SCORE**: **False pass (high):** the wrong answer `Not spam` (space instead of underscore) passes, because whole-word matching finds `spam` inside it. Probe confirmed. Suggested fix: use `exact` scoring, or labels that can't contain each other.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S13

| Field | Value |
|---|---|
| Case ID | `S13` |
| Task category | transformation (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | exact match |
| Flags | TASK |

**Full prompt** (verbatim):

~~~text
Rewrite the following text in uppercase letters only. Reply with the rewritten text only.
Text: ship it today
~~~

**Expected answer characteristics:** SHIP IT TODAY (case-sensitive).

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal `SHIP IT TODAY` (case-sensitive).

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "SHIP IT TODAY", "case_sensitive": true}
~~~

**Review flags:**

- **TASK**: Category is transformation, but task_type is `extraction`.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S14

| Field | Value |
|---|---|
| Case ID | `S14` |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **simple** |
| Response format | `text` · max output tokens 512 |
| Scoring method | choice (label match) |
| Flags | AMB |

**Full prompt** (verbatim):

~~~text
At sea level, does pure water boil at 100 degrees Celsius? Answer yes or no.
~~~

**Expected answer characteristics:** yes.

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `yes`, `no` (longest first).
- Exactly one distinct label may appear, and it must be `yes`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["yes", "no"], "answer": "yes"}
~~~

**Review flags:**

- **AMB**: **False fail:** a pedantic correct answer ("No, about 99.97 °C at 1 atm") fails, and "sea level" pressure varies. Probe confirmed. Suggest "at standard atmospheric pressure, approximately 100 °C?".

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### S15

| Field | Value |
|---|---|
| Case ID | `S15` |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **simple** |
| Response format | `json` · max output tokens 512 |
| Scoring method | JSON structure |
| Flags | DUP |

**Full prompt** (verbatim):

~~~text
Return a JSON object with the keys "name" (string) and "age" (integer) for this person: Priya is 34 years old.
~~~

**Expected answer characteristics:** {"name": "Priya", "age": 34}.

**Acceptance criteria:**

- The answer must parse as JSON. The first fenced code block is unwrapped if present; prose around unfenced JSON fails.
- field `name` = `"Priya"`
- field `age` = `34`
- Comparison rules: strings are trimmed and compared case-insensitively; numbers are compared numerically; booleans must be real JSON booleans; extra keys are ignored.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"name": "Priya", "age": 34}}
~~~

**Review flags:**

- **DUP**: Near-duplicate skill with T01 and C07 (JSON field extraction); acceptable as a difficulty ladder.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

## Standard (18)

### T01

| Field | Value |
|---|---|
| Case ID | `T01` |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |
| Flags | LABEL |

**Full prompt** (verbatim):

~~~text
Extract invoice_number (string), total_amount (number) and currency (ISO 4217 code) from the text and return them as a JSON object.
Text: Invoice INV-2026-0042 - amount due: EUR 1,250.00 by 30 April.
~~~

**Expected answer characteristics:** invoice_number INV-2026-0042, total_amount 1250, currency EUR.

**Acceptance criteria:**

- The answer must parse as JSON. The first fenced code block is unwrapped if present; prose around unfenced JSON fails.
- field `invoice_number` = `"INV-2026-0042"`
- field `total_amount` = `1250`
- field `currency` = `"EUR"`
- Comparison rules: strings are trimmed and compared case-insensitively; numbers are compared numerically; booleans must be real JSON booleans; extra keys are ignored.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"invoice_number": "INV-2026-0042", "total_amount": 1250, "currency": "EUR"}}
~~~

**Review flags:**

- **LABEL**: Three-field extraction from one line; arguably **simple**.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T02

| Field | Value |
|---|---|
| Case ID | `T02` |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |
| Flags | SCORE |

**Full prompt** (verbatim):

~~~text
Extract every person and their role. Return JSON shaped like {"people": [{"name": "...", "role": "..."}]}.
Text: The kickoff included Dana Kim (product manager), Luis Ortega (backend engineer) and Aiko Sato (designer).
~~~

**Expected answer characteristics:** Three people: Dana Kim, Luis Ortega, Aiko Sato, with their roles.

**Acceptance criteria:**

- The answer must parse as JSON. The first fenced code block is unwrapped if present; prose around unfenced JSON fails.
- `people[].name` includes `Dana Kim`, `Luis Ortega`, `Aiko Sato`
- Comparison rules: strings are trimmed and compared case-insensitively; numbers are compared numerically; booleans must be real JSON booleans; extra keys are ignored.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "list_contains": {"path": "people", "key": "name", "values": ["Dana Kim", "Luis Ortega", "Aiko Sato"]}}
~~~

**Review flags:**

- **SCORE**: **False pass:** the expected answer says "with their roles", but only the names are checked. Wrong roles pass. Probe confirmed.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T03

| Field | Value |
|---|---|
| Case ID | `T03` |
| Task category | summarization (router `task_type`: `summarization`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |
| Flags | SCORE, SUBJ |

**Full prompt** (verbatim):

~~~text
Summarise this incident report in at most two sentences.
Report: On Monday at 09:12 UTC the primary database ran out of disk space, causing checkout failures for 45 minutes. Engineers expanded the storage volume, restored service, and added an alert that fires when disk usage passes 80%.
~~~

**Expected answer characteristics:** Mentions the disk running out, the 45-minute impact, and the new alert; short.

**Acceptance criteria:**

- Case-insensitive substring checks; all must hold:
- contains `disk`
- contains `45`
- contains `alert`
- at most 70 words

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "all": ["disk", "45", "alert"], "max_words": 70}
~~~

**Review flags:**

- **SCORE**: **False pass:** the prompt's "at most two sentences" isn't checked, only the 70-word cap, so a five-sentence answer passes. Probe confirmed.
- **SUBJ**: Summary quality is approximated by three keywords.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T04

| Field | Value |
|---|---|
| Case ID | `T04` |
| Task category | summarization (router `task_type`: `summarization`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |
| Flags | SCORE |

**Full prompt** (verbatim):

~~~text
List the decisions made in these meeting notes as a short bulleted list.
Notes: We agreed to move the launch to 2 June. Marketing will own the press release. We discussed pricing but postponed a decision. Engineering will freeze features on 20 May.
~~~

**Expected answer characteristics:** The three decisions (launch 2 June, marketing owns press release, feature freeze 20 May); pricing not listed as decided.

**Acceptance criteria:**

- Case-insensitive substring checks; all must hold:
- contains `2 June`
- contains `press release`
- contains `20 May`

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "all": ["2 June", "press release", "20 May"]}
~~~

**Review flags:**

- **SCORE**: **False fail:** correct decisions written US-style (`June 2`, `May 20`) fail. Probe confirmed.
- **SCORE**: **False pass:** the expected answer says pricing must not be listed as decided, but listing it isn't penalised. Probe confirmed.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T05

| Field | Value |
|---|---|
| Case ID | `T05` |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |
| Flags | AMB |

**Full prompt** (verbatim):

~~~text
Answer the question using the passage. Reply with the day only.
Passage: The team ships a release every other week. This month's releases happened on Tuesday the 3rd and Tuesday the 17th, but the second one slipped by two days because of a failed test run.
Question: On which day of the week did the second release of the month actually happen?
~~~

**Expected answer characteristics:** Thursday (Tuesday plus two days).

**Acceptance criteria:**

- Case-insensitive substring checks; all must hold:
- contains `thursday`

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "all": ["thursday"]}
~~~

**Review flags:**

- **AMB**: The passage says the releases "happened on Tuesday the 3rd and Tuesday the 17th" and then that the second one slipped, which is self-contradictory. Suggest "were scheduled for".

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T06

| Field | Value |
|---|---|
| Case ID | `T06` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |
| Flags | AMB, DUP |

**Full prompt** (verbatim):

~~~text
Classify this ticket. Return JSON with "category" (one of billing, technical, shipping, account) and "urgency" (one of low, medium, high).
Ticket: Our whole team has been locked out of our accounts since this morning and we have a client demo in an hour.
~~~

**Expected answer characteristics:** category account, urgency high.

**Acceptance criteria:**

- The answer must parse as JSON. The first fenced code block is unwrapped if present; prose around unfenced JSON fails.
- field `category` = `"account"`
- field `urgency` = `"high"`
- Comparison rules: strings are trimmed and compared case-insensitively; numbers are compared numerically; booleans must be real JSON booleans; extra keys are ignored.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"category": "account", "urgency": "high"}}
~~~

**Review flags:**

- **AMB**: Being locked out could defensibly be `technical`; that answer fails. Probe confirmed. Either accept both, or make the prompt say "login/permissions issues are account".
- **DUP**: Same ticket template as S04/S05.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T07

| Field | Value |
|---|---|
| Case ID | `T07` |
| Task category | transformation (router `task_type`: `creative`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |
| Flags | SCORE, SUBJ, TASK |

**Full prompt** (verbatim):

~~~text
Rewrite this message so it is polite and professional, keeping the same request. Reply with the rewritten message only.
Message: Send me the report now, you are already late.
~~~

**Expected answer characteristics:** A polite request for the report, no insults.

**Acceptance criteria:**

- Case-insensitive substring checks; all must hold:
- contains `report`
- contains at least one of `please`, `could you`, `would you`, `kindly`, `appreciate`
- does not contain `you are already late`

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "any": ["please", "could you", "would you", "kindly", "appreciate"], "none": ["you are already late"], "all": ["report"]}
~~~

**Review flags:**

- **SUBJ**: Politeness is judged by a keyword list.
- **SCORE**: **False fail:** "I would be grateful if you could send the report…" fails, because none of the listed phrases appear. Probe confirmed.
- **TASK**: task_type `creative` for a rewrite.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T08

| Field | Value |
|---|---|
| Case ID | `T08` |
| Task category | code (router `task_type`: `code`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | regular expression |
| Flags | SCORE |

**Full prompt** (verbatim):

~~~text
Write a SQL query that returns the name column of every row in the customers table whose country is 'Germany', sorted by name ascending. Reply with the SQL only.
~~~

**Expected answer characteristics:** SELECT name FROM customers WHERE country = 'Germany' ORDER BY name.

**Acceptance criteria:**

- Case-insensitive. The answer must contain, in this order: `SELECT` … `name` … `FROM customers` … `WHERE` … `country = 'Germany'` (single quotes) … `ORDER BY name` (or `customers.name`).
- Pattern (searched in the trimmed answer): `(?is)select\s+.*\bname\b.*\bfrom\s+customers\b.*\bwhere\b.*country\s*=\s*'germany'.*\border\s+by\s+(customers\.)?name\b`

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "(?is)select\\s+.*\\bname\\b.*\\bfrom\\s+customers\\b.*\\bwhere\\b.*country\\s*=\\s*'germany'.*\\border\\s+by\\s+(customers\\.)?name\\b"}
~~~

**Review flags:**

- **SCORE**: **False fail:** correct SQL using a table alias (`ORDER BY c.name`) fails. Probe confirmed.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T09

| Field | Value |
|---|---|
| Case ID | `T09` |
| Task category | code (router `task_type`: `code`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | code execution with unit tests |
| Flags | AMB, FAV |

**Full prompt** (verbatim):

~~~text
Write a Python function is_palindrome(s: str) -> bool that ignores case and any non-alphanumeric characters. Reply with only the code in a single ```python block.
~~~

**Expected answer characteristics:** A correct is_palindrome function.

**Acceptance criteria:**

- Runs only with `--allow-code-exec`; otherwise the case is reported as **not scorable**, never as a pass.
- The first fenced code block (or the whole answer) runs in an isolated `python -I -S` subprocess with a 10 s timeout, followed by these tests, all of which must pass:
- `assert is_palindrome('A man, a plan, a canal: Panama')`
- `assert not is_palindrome('race a car')`
- `assert is_palindrome('')`
- `assert is_palindrome('No lemon, no melon')`

**Scoring spec** (verbatim):

~~~json
{"method": "code", "tests": ["assert is_palindrome('A man, a plan, a canal: Panama')", "assert not is_palindrome('race a car')", "assert is_palindrome('')", "assert is_palindrome('No lemon, no melon')"]}
~~~

**Review flags:**

- **FAV**: The test inputs "A man, a plan, a canal: Panama" and "race a car" match a well-known public coding-exercise example (from memory; please verify). This creates contamination risk and conflicts with the meta file's "no examples copied" claim.
- **AMB**: Unscored unless the benchmark runs with `--allow-code-exec` (reported as not scorable, never as a pass).

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T10

| Field | Value |
|---|---|
| Case ID | `T10` |
| Task category | code (router `task_type`: `code`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | code execution with unit tests |
| Flags | AMB, FAV, LABEL |

**Full prompt** (verbatim):

~~~text
Write a Python function fizzbuzz(n: int) -> list[str] that returns the strings for 1..n where multiples of 3 are 'Fizz', multiples of 5 are 'Buzz', multiples of both are 'FizzBuzz', and other numbers are their decimal string. Reply with only the code in a single ```python block.
~~~

**Expected answer characteristics:** A correct fizzbuzz function.

**Acceptance criteria:**

- Runs only with `--allow-code-exec`; otherwise the case is reported as **not scorable**, never as a pass.
- The first fenced code block (or the whole answer) runs in an isolated `python -I -S` subprocess with a 10 s timeout, followed by these tests, all of which must pass:
- `assert fizzbuzz(5) == ['1', '2', 'Fizz', '4', 'Buzz']`
- `assert fizzbuzz(15)[-1] == 'FizzBuzz'`
- `assert fizzbuzz(0) == []`

**Scoring spec** (verbatim):

~~~json
{"method": "code", "tests": ["assert fizzbuzz(5) == ['1', '2', 'Fizz', '4', 'Buzz']", "assert fizzbuzz(15)[-1] == 'FizzBuzz'", "assert fizzbuzz(0) == []"]}
~~~

**Review flags:**

- **FAV**: FizzBuzz is ubiquitous in training data, so it says little about model capability.
- **LABEL**: Arguably **simple**.
- **AMB**: Unscored unless `--allow-code-exec` is set.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T11

| Field | Value |
|---|---|
| Case ID | `T11` |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | numeric |
| Flags | SCORE |

**Full prompt** (verbatim):

~~~text
A shirt costs $40. It is discounted by 25%, then a 10% tax is added to the discounted price. What is the final price in dollars? Reply with the number only.
~~~

**Expected answer characteristics:** 33 (40 x 0.75 = 30; 30 x 1.10 = 33).

**Acceptance criteria:**

- The answer must contain **exactly one** number (thousands commas ignored); several numbers fail as ambiguous.
- It must equal 33 within ±0.001.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 33, "tolerance": 0.001}
~~~

**Review flags:**

- **SCORE**: Same single-number strictness as S09: restating the working fails.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T12

| Field | Value |
|---|---|
| Case ID | `T12` |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | choice (label match) |
| Flags | LABEL |

**Full prompt** (verbatim):

~~~text
If all bloops are razzies and all razzies are lazzies, are all bloops definitely lazzies? Answer yes or no.
~~~

**Expected answer characteristics:** yes (transitive syllogism).

**Acceptance criteria:**

- Case-insensitive, whole-word search for the labels `yes`, `no` (longest first).
- Exactly one distinct label may appear, and it must be `yes`. Mentioning two different labels fails.

**Scoring spec** (verbatim):

~~~json
{"method": "choice", "labels": ["yes", "no"], "answer": "yes"}
~~~

**Review flags:**

- **LABEL**: A one-step syllogism; arguably **simple**.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T13

| Field | Value |
|---|---|
| Case ID | `T13` |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | exact match |
| Flags | FAV, LABEL |

**Full prompt** (verbatim):

~~~text
What day of the week was 1 January 2026? Reply with the day name only.
~~~

**Expected answer characteristics:** Thursday.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal `thursday` (case-insensitive).

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "thursday"}
~~~

**Review flags:**

- **FAV**: Calendar arithmetic without tools favours reasoning models. Every currently enabled Groq model is a reasoning model, so this mainly matters if non-reasoning models are added.
- **LABEL**: Models often get this wrong; arguably **complex**. The expected answer (Thursday) was checked: 2025-01-01 was a Wednesday and 2025 isn't a leap year.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T14

| Field | Value |
|---|---|
| Case ID | `T14` |
| Task category | transformation (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | exact match |
| Flags | LABEL, TASK |

**Full prompt** (verbatim):

~~~text
Format this US phone number in E.164 format. Reply with the formatted number only.
Number: (415) 555-0132
~~~

**Expected answer characteristics:** +14155550132.

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal `+14155550132` (case-insensitive).

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "+14155550132"}
~~~

**Review flags:**

- **LABEL**: Mechanical reformatting; arguably **simple**.
- **TASK**: Category is transformation, but task_type is `extraction`.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T15

| Field | Value |
|---|---|
| Case ID | `T15` |
| Task category | math (router `task_type`: `extraction`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |
| Flags | TASK |

**Full prompt** (verbatim):

~~~text
Compute the order total from these line items and return JSON {"total": number}.
Items: 3 notebooks at $2.50 each; 2 pens at $1.20 each.
~~~

**Expected answer characteristics:** {"total": 9.9}.

**Acceptance criteria:**

- The answer must parse as JSON. The first fenced code block is unwrapped if present; prose around unfenced JSON fails.
- `total` is a JSON number equal to 9.9 ± 0.001
- Comparison rules: strings are trimmed and compared case-insensitively; numbers are compared numerically; booleans must be real JSON booleans; extra keys are ignored.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "numeric": {"path": "total", "answer": 9.9, "tolerance": 0.001}}
~~~

**Review flags:**

- **TASK**: Category is math, but task_type is `extraction`.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T16

| Field | Value |
|---|---|
| Case ID | `T16` |
| Task category | qa (router `task_type`: `qa`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | exact match |
| Flags | none |

**Full prompt** (verbatim):

~~~text
Answer using only the context. If the answer is not in the context, reply exactly: NOT_IN_CONTEXT
Context: Our office is open Monday to Friday, 9am to 5pm, and closed on public holidays.
Question: What is the office phone number?
~~~

**Expected answer characteristics:** NOT_IN_CONTEXT (the context has no phone number).

**Acceptance criteria:**

- The answer is normalised: whitespace trimmed and collapsed, wrapping backticks removed, and leading/trailing `.` `!` `"` `'` stripped.
- It must then equal `NOT_IN_CONTEXT` (case-sensitive).

**Scoring spec** (verbatim):

~~~json
{"method": "exact", "answer": "NOT_IN_CONTEXT", "case_sensitive": true}
~~~

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T17

| Field | Value |
|---|---|
| Case ID | `T17` |
| Task category | transformation (router `task_type`: `creative`) |
| Complexity | **standard** |
| Response format | `text` · max output tokens 1024 |
| Scoring method | keyword checks |
| Flags | SCORE, SUBJ, TASK |

**Full prompt** (verbatim):

~~~text
Translate into Spanish. Reply with the translation only.
Text: The library opens at nine o'clock.
~~~

**Expected answer characteristics:** A Spanish sentence using 'biblioteca' and nine.

**Acceptance criteria:**

- Case-insensitive substring checks; all must hold:
- contains `biblioteca`
- contains at least one of `nueve`, `9`

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "all": ["biblioteca"], "any": ["nueve", "9"]}
~~~

**Review flags:**

- **SUBJ**: Translation quality is approximated by two keywords.
- **SCORE**: **False pass:** a wrong translation ("La biblioteca *cierra* a las 9.", meaning "closes") passes. Probe confirmed.
- **TASK**: task_type `creative` for a translation.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### T18

| Field | Value |
|---|---|
| Case ID | `T18` |
| Task category | classification (router `task_type`: `classification`) |
| Complexity | **standard** |
| Response format | `json` · max output tokens 1024 |
| Scoring method | JSON structure |
| Flags | AMB |

**Full prompt** (verbatim):

~~~text
Decide whether this product review mentions a defect. Return JSON {"defect": true or false, "part": the defective part as a lowercase word, or null}.
Review: Love the colour, but the zipper broke after one week.
~~~

**Expected answer characteristics:** defect true, part zipper.

**Acceptance criteria:**

- The answer must parse as JSON. The first fenced code block is unwrapped if present; prose around unfenced JSON fails.
- field `defect` = `true`
- field `part` = `"zipper"`
- Comparison rules: strings are trimmed and compared case-insensitively; numbers are compared numerically; booleans must be real JSON booleans; extra keys are ignored.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"defect": true, "part": "zipper"}}
~~~

**Review flags:**

- **AMB**: British `zip` instead of `zipper` fails. Decide whether to accept it.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

## Complex (12)

### C01

| Field | Value |
|---|---|
| Case ID | `C01` |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | regular expression |
| Flags | LABEL |

**Full prompt** (verbatim):

~~~text
Train A leaves a station at 08:15 travelling at 120 km/h. Train B leaves the same station at 09:00 on a parallel track in the same direction at 150 km/h. At what time does train B draw level with train A? Show your reasoning briefly, then give the final answer on the last line as HH:MM (24-hour).
~~~

**Expected answer characteristics:** 12:00 (A is 90 km ahead at 09:00; closing speed 30 km/h; 3 hours).

**Acceptance criteria:**

- The answer must end with `12:00`, optionally followed only by punctuation or markdown (e.g. `12:00.` or `**12:00**`).
- Pattern (searched in the trimmed answer): `12:00\s*\W*\s*$`

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "12:00\\s*\\W*\\s*$"}
~~~

**Review flags:**

- **LABEL**: A two-step relative-speed problem; arguably **standard**.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C02

| Field | Value |
|---|---|
| Case ID | `C02` |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | regular expression |
| Flags | LABEL, SCORE |

**Full prompt** (verbatim):

~~~text
Two fair six-sided dice are rolled. What is the probability that their sum is 8? Explain briefly, then give the answer as a reduced fraction on the last line.
~~~

**Expected answer characteristics:** 5/36.

**Acceptance criteria:**

- `5/36` (spaces around `/` allowed) must appear anywhere in the answer.
- Pattern (searched in the trimmed answer): `\b5\s*/\s*36\b`

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "\\b5\\s*/\\s*36\\b"}
~~~

**Review flags:**

- **SCORE**: **False pass:** the pattern isn't anchored to the last line, so "Not 5/36; the answer is 1/6" passes. Probe confirmed. Suggest anchoring it like C01.
- **LABEL**: Introductory probability; arguably **standard**.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C03

| Field | Value |
|---|---|
| Case ID | `C03` |
| Task category | code (router `task_type`: `code`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | code execution with unit tests |
| Flags | AMB, FAV |

**Full prompt** (verbatim):

~~~text
Write a Python function merge_intervals(intervals: list[list[int]]) -> list[list[int]] that merges all overlapping (or touching) closed intervals and returns them sorted by start. The input may be unsorted. Reply with only the code in a single ```python block.
~~~

**Expected answer characteristics:** A correct interval-merging function.

**Acceptance criteria:**

- Runs only with `--allow-code-exec`; otherwise the case is reported as **not scorable**, never as a pass.
- The first fenced code block (or the whole answer) runs in an isolated `python -I -S` subprocess with a 10 s timeout, followed by these tests, all of which must pass:
- `assert merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]`
- `assert merge_intervals([[1,4],[4,5]]) == [[1,5]]`
- `assert merge_intervals([[5,7],[1,2]]) == [[1,2],[5,7]]`
- `assert merge_intervals([]) == []`
- `assert merge_intervals([[1,10],[2,3],[4,5]]) == [[1,10]]`

**Scoring spec** (verbatim):

~~~json
{"method": "code", "tests": ["assert merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]", "assert merge_intervals([[1,4],[4,5]]) == [[1,5]]", "assert merge_intervals([[5,7],[1,2]]) == [[1,2],[5,7]]", "assert merge_intervals([]) == []", "assert merge_intervals([[1,10],[2,3],[4,5]]) == [[1,10]]"]}
~~~

**Review flags:**

- **FAV**: The first test input `[[1,3],[2,6],[8,10],[15,18]]` matches a well-known public coding-exercise example (from memory; please verify).
- **AMB**: Unscored unless `--allow-code-exec` is set.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C04

| Field | Value |
|---|---|
| Case ID | `C04` |
| Task category | code (router `task_type`: `code`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | code execution with unit tests |
| Flags | AMB, FAV, LABEL |

**Full prompt** (verbatim):

~~~text
Write a Python function roman_to_int(s: str) -> int that converts a valid Roman numeral (I, V, X, L, C, D, M, including subtractive forms like IV and CM) to an integer. Reply with only the code in a single ```python block.
~~~

**Expected answer characteristics:** A correct Roman numeral converter.

**Acceptance criteria:**

- Runs only with `--allow-code-exec`; otherwise the case is reported as **not scorable**, never as a pass.
- The first fenced code block (or the whole answer) runs in an isolated `python -I -S` subprocess with a 10 s timeout, followed by these tests, all of which must pass:
- `assert roman_to_int('III') == 3`
- `assert roman_to_int('LVIII') == 58`
- `assert roman_to_int('MCMXCIV') == 1994`
- `assert roman_to_int('MMXXVI') == 2026`
- `assert roman_to_int('XLIX') == 49`

**Scoring spec** (verbatim):

~~~json
{"method": "code", "tests": ["assert roman_to_int('III') == 3", "assert roman_to_int('LVIII') == 58", "assert roman_to_int('MCMXCIV') == 1994", "assert roman_to_int('MMXXVI') == 2026", "assert roman_to_int('XLIX') == 49"]}
~~~

**Review flags:**

- **FAV**: Test inputs `LVIII` and `MCMXCIV` match a well-known public coding-exercise example (from memory; please verify).
- **LABEL**: A widely known easy exercise; arguably **standard**.
- **AMB**: Unscored unless `--allow-code-exec` is set.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C05

| Field | Value |
|---|---|
| Case ID | `C05` |
| Task category | code (router `task_type`: `code`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | code execution with unit tests |
| Flags | AMB, FAV |

**Full prompt** (verbatim):

~~~text
Write a Python function top_k_frequent(words: list[str], k: int) -> list[str] returning the k most frequent words, ordered by frequency descending and alphabetically for ties. Reply with only the code in a single ```python block.
~~~

**Expected answer characteristics:** A correct, tie-aware top-k function.

**Acceptance criteria:**

- Runs only with `--allow-code-exec`; otherwise the case is reported as **not scorable**, never as a pass.
- The first fenced code block (or the whole answer) runs in an isolated `python -I -S` subprocess with a 10 s timeout, followed by these tests, all of which must pass:
- `assert top_k_frequent(['i','love','leetcode','i','love','coding'], 2) == ['i','love']`
- `assert top_k_frequent(['the','day','is','sunny','the','the','the','sunny','is','is'], 4) == ['the','is','sunny','day']`
- `assert top_k_frequent(['b','a','c'], 2) == ['a','b']`

**Scoring spec** (verbatim):

~~~json
{"method": "code", "tests": ["assert top_k_frequent(['i','love','leetcode','i','love','coding'], 2) == ['i','love']", "assert top_k_frequent(['the','day','is','sunny','the','the','the','sunny','is','is'], 4) == ['the','is','sunny','day']", "assert top_k_frequent(['b','a','c'], 2) == ['a','b']"]}
~~~

**Review flags:**

- **FAV**: Both main test inputs (`['i','love','leetcode',…]` and `['the','day','is','sunny',…]`) match a well-known public coding-exercise example almost verbatim (from memory; please verify). One literally contains the word "leetcode". This conflicts with the meta file's "no examples copied from public benchmarks".
- **AMB**: Unscored unless `--allow-code-exec` is set.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C06

| Field | Value |
|---|---|
| Case ID | `C06` |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | regular expression |
| Flags | LABEL |

**Full prompt** (verbatim):

~~~text
Four friends - Ana, Ben, Cy and Di - each have a different favourite colour: red, blue, green or yellow. Ana's favourite is neither red nor blue. Ben's favourite is green. Cy's favourite is not red. Whose favourite colour is red? Reason it through, then give only the name on the last line.
~~~

**Expected answer characteristics:** Di (Ben green; Ana yellow; Cy blue; Di red).

**Acceptance criteria:**

- Case-insensitive. The last word of the answer must be `Di`, optionally followed only by punctuation.
- Pattern (searched in the trimmed answer): `(?i)\bdi\b\W*$`

**Scoring spec** (verbatim):

~~~json
{"method": "regex", "pattern": "(?i)\\bdi\\b\\W*$"}
~~~

**Review flags:**

- **LABEL**: Three clues, four people; arguably **standard**.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C07

| Field | Value |
|---|---|
| Case ID | `C07` |
| Task category | extraction (router `task_type`: `extraction`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | JSON structure |
| Flags | none |

**Full prompt** (verbatim):

~~~text
Extract the order from this email as JSON with keys "customer" (string), "items" (list of {"sku": string, "quantity": integer}) and "total_units" (integer, the sum of all quantities). Merge repeated SKUs.
Email: Hi, this is Omar Haddad. Please send 2 units of SKU-118 and 5 of SKU-204. Actually, add 3 more of SKU-118 as well. Thanks!
~~~

**Expected answer characteristics:** customer Omar Haddad; SKU-118 x5, SKU-204 x5; total_units 10.

**Acceptance criteria:**

- The answer must parse as JSON. The first fenced code block is unwrapped if present; prose around unfenced JSON fails.
- field `customer` = `"Omar Haddad"`
- field `total_units` = `10`
- `items[].sku` includes `SKU-118`, `SKU-204`
- summing `quantity` per `sku` in `items`: `SKU-118` → 5, `SKU-204` → 5
- Comparison rules: strings are trimmed and compared case-insensitively; numbers are compared numerically; booleans must be real JSON booleans; extra keys are ignored.

**Scoring spec** (verbatim):

~~~json
{"method": "json", "expected_subset": {"customer": "Omar Haddad", "total_units": 10}, "list_contains": {"path": "items", "key": "sku", "values": ["SKU-118", "SKU-204"]}, "list_values": {"path": "items", "key": "sku", "value_key": "quantity", "expected": {"SKU-118": 5, "SKU-204": 5}}}
~~~

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C08

| Field | Value |
|---|---|
| Case ID | `C08` |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |
| Flags | SCORE |

**Full prompt** (verbatim):

~~~text
What is the sum of all prime numbers less than 50? Work it out, then give only the number on the last line.
~~~

**Expected answer characteristics:** 328.

**Acceptance criteria:**

- The **last** number in the answer is used (thousands commas ignored).
- It must equal 328 within ±0.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 328, "tolerance": 0, "last_number": true}
~~~

**Review flags:**

- **SCORE**: **False fail:** a correct answer followed by another number ("328 (from 15 primes)") fails, because the last number is taken. Probe confirmed. The prompt does ask for the number only on the last line.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C09

| Field | Value |
|---|---|
| Case ID | `C09` |
| Task category | math (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | numeric |
| Flags | none |

**Full prompt** (verbatim):

~~~text
$1,000 is invested at 5% annual interest, compounded annually, for 3 years. What is the final amount in dollars, rounded to 2 decimal places? Show the calculation briefly, then give only the number on the last line.
~~~

**Expected answer characteristics:** 1157.63 (1000 x 1.05^3 = 1157.625).

**Acceptance criteria:**

- The **last** number in the answer is used (thousands commas ignored).
- It must equal 1157.63 within ±0.006.

**Scoring spec** (verbatim):

~~~json
{"method": "numeric", "answer": 1157.63, "tolerance": 0.006, "last_number": true}
~~~

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C10

| Field | Value |
|---|---|
| Case ID | `C10` |
| Task category | analysis (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | keyword checks |
| Flags | AMB, SUBJ |

**Full prompt** (verbatim):

~~~text
Compare optimistic and pessimistic concurrency control for a heavily contended inventory counter that many requests decrement at once. Analyse the trade-offs, recommend one approach, and justify it in 3 to 6 sentences.
~~~

**Expected answer characteristics:** Discusses both approaches, notes retry storms/aborts under high contention for optimistic locking, and makes a justified recommendation (typically pessimistic locking or an atomic conditional update).

**Acceptance criteria:**

- Case-insensitive substring checks; all must hold:
- contains `optimistic`
- contains `pessimistic`
- contains at least one of `contention`, `retry`, `retries`, `conflict`
- **Needs human review.** Rubric: 2 = both approaches explained, contention cost of optimistic retries identified, clear justified recommendation; 1 = mostly correct but shallow or unjustified; 0 = wrong or missing recommendation.

**Scoring spec** (verbatim):

~~~json
{"method": "contains", "all": ["optimistic", "pessimistic"], "any": ["contention", "retry", "retries", "conflict"], "needs_human_review": true, "rubric": "2 = both approaches explained, contention cost of optimistic retries identified, clear justified recommendation; 1 = mostly correct but shallow or unjustified; 0 = wrong or missing recommendation."}
~~~

**Review flags:**

- **SUBJ**: Marked `needs_human_review`. The automatic check is three keywords, so a one-line, unjustified answer passes. Probe confirmed.
- **AMB**: The expected answer prefers pessimistic locking or an atomic update, but optimistic control with backoff, or a single atomic decrement, is defensible. The rubric should accept any well-justified choice. Consider excluding this case from the automatic pass rate.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C11

| Field | Value |
|---|---|
| Case ID | `C11` |
| Task category | code (router `task_type`: `code`) |
| Complexity | **complex** |
| Response format | `text` · max output tokens 2048 |
| Scoring method | code execution with unit tests |
| Flags | AMB |

**Full prompt** (verbatim):

~~~text
Write a Python function parse_duration(text: str) -> int that converts strings like '1h30m15s', '45m', '2h' or '90s' into a total number of seconds. Units are h, m and s, each optional but in that order. Raise ValueError for an empty or malformed string. Reply with only the code in a single ```python block.
~~~

**Expected answer characteristics:** A correct parser with validation.

**Acceptance criteria:**

- Runs only with `--allow-code-exec`; otherwise the case is reported as **not scorable**, never as a pass.
- The first fenced code block (or the whole answer) runs in an isolated `python -I -S` subprocess with a 10 s timeout, followed by these tests, all of which must pass:
- `assert parse_duration('1h30m15s') == 5415`
- `assert parse_duration('45m') == 2700`
- `assert parse_duration('2h') == 7200`
- `assert parse_duration('90s') == 90`
- `import pytest_shim; pytest_shim.raises(ValueError, parse_duration, '')`
- `import pytest_shim; pytest_shim.raises(ValueError, parse_duration, 'abc')`

**Scoring spec** (verbatim):

~~~json
{"method": "code", "tests": ["assert parse_duration('1h30m15s') == 5415", "assert parse_duration('45m') == 2700", "assert parse_duration('2h') == 7200", "assert parse_duration('90s') == 90", "import pytest_shim; pytest_shim.raises(ValueError, parse_duration, '')", "import pytest_shim; pytest_shim.raises(ValueError, parse_duration, 'abc')"]}
~~~

**Review flags:**

- **AMB**: Malformed input is tested only with `''` and `'abc'`. Wrong unit order (`30m1h`), repeats (`1h1h`) and junk around valid input aren't tested, so a lax parser passes despite "in that order".
- **AMB**: Unscored unless `--allow-code-exec` is set.

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

### C12

| Field | Value |
|---|---|
| Case ID | `C12` |
| Task category | reasoning (router `task_type`: `reasoning`) |
| Complexity | **complex** |
| Response format | `json` · max output tokens 2048 |
| Scoring method | custom validator (`meeting_schedule`) |
| Flags | none |

**Full prompt** (verbatim):

~~~text
Schedule three meetings between 09:00 and 11:00 with no overlaps: A lasts 60 minutes, B lasts 30 minutes, C lasts 30 minutes. A must start before B. C must end by 10:00. Return JSON {"A": "HH:MM", "B": "HH:MM", "C": "HH:MM"} giving each meeting's start time.
~~~

**Expected answer characteristics:** Any valid schedule, e.g. C 09:00, A 09:30, B 10:30.

**Acceptance criteria:**

- The answer must parse as JSON with keys `A`, `B` and `C` holding `HH:MM` start times. All of these must hold:
- every meeting is within 09:00–11:00 (A 60 min, B 30 min, C 30 min)
- no two meetings overlap
- A starts before B
- C ends by 10:00
- Any schedule that satisfies all four passes. Worked through by hand, the constraints admit exactly one schedule: **C 09:00, A 09:30, B 10:30**. B needs 30 minutes after A ends by 11:00, so A starts by 09:30, and C must end by 10:00 without overlapping A, so it comes first. The expected answer's "any valid schedule, e.g." is therefore unique in practice.

**Scoring spec** (verbatim):

~~~json
{"method": "validator", "name": "meeting_schedule"}
~~~

**Reviewer decision:** ☐ accept as is · ☐ edit (notes below) · ☐ replace · ☐ drop

Notes:

---

## Sign-off

Record in `routewise_bench_v1.meta.yaml` after review, e.g. `S01: {reviewer: "<name>", date: "YYYY-MM-DD", notes: ""}`.
Until all 45 entries exist, `DATASET.fully_reviewed` stays false and no report is publishable.
