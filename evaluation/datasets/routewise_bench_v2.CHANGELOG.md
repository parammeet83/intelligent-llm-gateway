# routewise_bench_v2 — Changelog

**2026-11-04.** Created from `routewise_bench_v1` after the owner-approved review (`routewise_bench_v1_review.md`). v1 is unchanged and keeps `preregistration.yaml`.
v2 SHA-256 `614e14497b380539baed24ad87f3619e11107d2adc35230004b652dec6994550`; pre-registration `preregistration_routewise_bench_v2.yaml` SHA-256 `d90fb48cc1e62fe0a1bfa709b5acff85e39a12d56072ba4b63c33607f07b945f`.
No model or provider was called and no benchmark was run. v2 is **not reviewed**: `reviewed_by` is empty.

## Summary

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

Distribution preserved: 15 simple / 18 standard / 12 complex. Unchanged cases are byte-identical to v1 (tested).

## Per-case changes

| v2 ID | Change | Detail |
|---|---|---|
| S01 | unchanged | Kept as the only sentiment case. |
| S02 | replaced | v1 S02 (negative sentiment) removed as a near-duplicate of S01. New: alphabetical sort (transformation), exact match with a no-space variant accepted. |
| S03 | replaced | v1 S03 (neutral sentiment) removed: a near-duplicate of S01 with an ambiguous label. New: mammal identification (choice). |
| S04 | unchanged | Kept; billing is unambiguous. |
| S05 | moved | v1 S05 (technical ticket) removed as a near-duplicate of S04. This slot now holds v1 T14 (E.164 phone formatting), relabelled simple. Prompt and scoring unchanged. |
| S06 | unchanged | — |
| S07 | scoring fixed | False fail: the regex rejected `2026-03-14.`, so it's now `exact` (which strips punctuation). The prompt now says "quarterly review" to match the text. |
| S08 | unchanged | — |
| S09 | scoring fixed | False fail: `17 x 23 = 391` failed because it has several numbers. Now `last_number`. |
| S10 | replaced | v1 S10 (km to m) removed as a near-duplicate arithmetic skill. New: decimal comparison 0.9 vs 0.11 (numeric). |
| S11 | unchanged | — |
| S12 | prompt + scoring fixed | False pass: `Not spam` matched `spam`. Labels are now spam / legitimate, and scoring is `exact`, so negations and extra words fail. |
| S13 | unchanged | — |
| S14 | prompt fixed | False fail on a pedantic correct answer. Now asks "at standard atmospheric pressure (1 atm) … approximately 100 °C". |
| S15 | unchanged | — |
| T01 | unchanged | Label kept as standard (see rationale). |
| T02 | scoring fixed | False pass: roles weren't checked. Now checks each name→role pair (with a `back-end` variant) and exactly 3 people. |
| T03 | scoring fixed | False pass: the two-sentence limit wasn't checked. `max_sentences: 2` added. |
| T04 | prompt + scoring fixed | False fail on `June 2`, false pass when pricing was listed. Each date now accepts day-first, month-first and ordinal forms; the prompt forbids undecided topics and the scorer rejects the words pricing/price. |
| T05 | prompt + scoring fixed | "Happened on … slipped" was contradictory, so it now says "were scheduled for". `contains` → `exact`, so hedged answers ("Tuesday or Thursday") fail. |
| T06 | prompt fixed | Account vs technical was ambiguous. The prompt now defines every category (account = sign-in, passwords, access) and every urgency level. |
| T07 | prompt + scoring fixed | False fail on polite wording missing from the keyword list. Now an explicit instruction-following rewrite: must contain the whole word `please` and `report`, must not contain the whole words `now`/`late`, ≤ 60 words. |
| T08 | scoring fixed | False fail on table aliases. A new anchored pattern allows aliases, `AS`, `ASC`, a trailing `;` and code fences, but rejects extra columns, `DESC` and a missing `ORDER BY`. |
| T09 | replaced | v1 T09 (palindrome; LeetCode 125 example inputs; executed model code) removed. New: predict a short program's output (non-executable code reasoning). |
| T10 | replaced | v1 T10 (FizzBuzz; ubiquitous; executed model code) removed. New: find the buggy line in a numbered function, with the answer on an `ANSWER:` line. |
| T11 | scoring fixed | False fail when the working was restated. Now `last_number`. |
| T12 | moved | v1 T12 (one-step syllogism) removed as too easy for standard. This slot now holds v1 C02 (dice probability), relabelled standard, with an `ANSWER:` line, which fixes the v1 false pass where 5/36 could appear anywhere. |
| T13 | unchanged | Label kept as standard (see rationale). |
| T14 | replaced | v1 T14 moved to S05. New: normalise four dates in mixed formats to ISO 8601 (JSON list). |
| T15 | task_type changed | task_type `extraction` → `reasoning` (it's arithmetic). Prompt and scoring unchanged. |
| T16 | unchanged | — |
| T17 | scoring fixed | False pass on a wrong verb. The scorer now requires biblioteca + abre + nueve/9 and rejects `cierra`. |
| T18 | prompt fixed | `zip` vs `zipper`: the part must now be written exactly as in the review. |
| C01 | unchanged | Label kept as complex (see rationale). |
| C02 | replaced | v1 C02 moved to T12. New: tank fill problem with piecewise rates and a distractor event, answered on an `ANSWER:` line. |
| C03 | replaced | v1 C03 (merge intervals; LeetCode 56 example input; executed model code) removed. New: trace a program that sums gaps between repeated values. |
| C04 | replaced | v1 C04 (Roman numerals; LeetCode 13 example inputs; executed model code) removed. New: apply 8 ledger events with a rejection rule (JSON). |
| C05 | replaced | v1 C05 (top-k words; LeetCode 692 example inputs verbatim; executed model code) removed. New: predict a GROUP BY / HAVING / ORDER BY query result over given rows (JSON). |
| C06 | rewritten | v1 4-person puzzle relabel investigated: 3 clues was standard-level. Rewritten as a 5-person, 6-constraint puzzle with a unique solution (brute-force checked), answered on an `ANSWER:` line. |
| C07 | unchanged | — |
| C08 | prompt + scoring fixed | False fail on `328 (from 15 primes)`. Now `ANSWER:` line + first number on it. |
| C09 | prompt + scoring fixed | Same `ANSWER:` convention, so a trailing note such as "to 2 d.p." can't be misread as the answer. |
| C10 | replaced | v1 C10 (subjective concurrency essay, human-graded) removed. New: critical-path duration and path (JSON, unique longest path). |
| C11 | replaced | v1 C11 (duration parser; executed model code; under-tested) removed. New: apply five password rules to eight candidates (JSON list). |
| C12 | unchanged | The constraints admit exactly one schedule (09:30 / 10:30 / 09:00, brute-force checked at 1-minute granularity); the validator accepts any valid schedule. |

## Removed v1 cases

| v1 ID | Reason |
|---|---|
| S02, S03 | Near-duplicates of S01 (same sentiment template); S03's label was ambiguous |
| S05 | Near-duplicate of S04 (same ticket template) |
| S10 | Near-duplicate arithmetic skill with S09 |
| T09, C03, C04, C05 | Public-exercise contamination (confirmed) and executed model code |
| T10, C11 | Executed model code (T10 is also ubiquitous FizzBuzz) |
| T12 | One-step syllogism, too easy for standard |
| C10 | Subjective essay that needed human grading |
| (moved, not removed) T14 → S05, C02 → T12 | Relabelled |

## Contamination investigation (item 6)

Distinctive test inputs of the four suspected v1 cases were searched on 2026-11-04. All four matched public LeetCode problem examples:

- **v1 T09:** https://github.com/grandyang/leetcode/issues/125 (LeetCode 125 examples: "A man, a plan, a canal: Panama" → true, "race a car" → false)
- **v1 C03:** https://zhenchaogan.gitbook.io/leetcode-solution/leetcode-56-merge-intervals (LeetCode 56 example [[1,3],[2,6],[8,10],[15,18]] → [[1,6],[8,10],[15,18]]; touching [[1,4],[4,5]] → [[1,5]])
- **v1 C04:** https://github.com/grandyang/leetcode/issues/13 (LeetCode 13 examples LVIII → 58, MCMXCIV → 1994)
- **v1 C05:** https://peichengliu.github.io/LeetCode/leetcode-692-top-k-frequent-words (LeetCode 692 examples ["i","love","leetcode",…] k=2 and ["the","day","is","sunny",…] k=4)

All four are removed. The v1 meta file's claim, "no examples copied from public benchmarks", was therefore wrong for these cases. The v2 meta states originality only as far as it was checked: the 12 new cases were written for this dataset but weren't exhaustively searched, and the unchanged generic cases weren't individually searched.

## Code-execution safety (item 12)

v1's six code cases ran model-generated code in a `python -I -S` subprocess, inside a temporary directory, with a stripped environment and a 10 s timeout. That is **not isolation**: the code could still read and write the operator's files, open network connections, spawn processes and use unbounded memory. No OS-level sandbox (container, VM, seccomp/AppContainer) is available on the development machine (Docker isn't installed), so proper isolation can't be guaranteed.

**Decision:** v2 has no code-execution cases. The code category is kept with non-executable tasks: output prediction (T09, C03), bug location (T10) and SQL result prediction (C05). The meta file sets `code_execution: false`, and the loader refuses any `code` case while that's set. v1's code scorer is unchanged and stays off by default.

## Complexity labels (item 7)

Rubric:

- **Simple:** one step. The answer is stated in or read directly off the prompt, or is one fact or one arithmetic operation, with a single-token or single-field output.
- **Standard:** two or three steps, or a structured output with several typed fields, or one inference beyond the text (date arithmetic, conditional logic, normalising several values).
- **Complex:** four or more dependent steps, several interacting constraints or rules, state that must be tracked over a sequence, or a distractor that must be recognised.
- Labels describe the reasoning required, not how often models fail. They only group the report; the router computes its own complexity score.

| Case | Flag in v1 review | Decision | Rationale |
|---|---|---|---|
| v1 T01 | arguably simple | **kept standard** (v2 T01) | Investigated (flagged arguably simple). Kept standard: three fields, each needing normalisation ("EUR 1,250.00" → number 1250 and ISO code EUR; ignore the due date), into typed JSON. That's more than reading one span. |
| v1 T10 | arguably simple | **removed** | FizzBuzz, and it executed model code; replaced by a standard bug-location task |
| v1 T12 | arguably simple | **removed** | One-step syllogism; the simple slots are filled by more diverse tasks |
| v1 T14 | arguably simple | **moved to simple** (v2 S05) | Moved from standard: one mechanical reformat (prefix +1, strip punctuation). Investigated: it needs only knowing the E.164 shape, not multi-step reasoning. |
| v1 C01 | arguably standard | **kept complex** (v2 C01) | Investigated (flagged arguably standard). Kept complex: head start (0.75 h × 120 = 90 km), closing speed (30 km/h), catch-up time (3 h) and clock addition. That's four dependent steps in mixed units. |
| v1 C02 | arguably standard | **moved to standard** (v2 T12) | Moved from complex. Investigated: enumerate the five outcomes and reduce 5/36; that's two steps, standard. |
| v1 C04 | arguably standard | **removed** | Contaminated and executed model code; replaced by a complex ledger task |
| v1 C06 | arguably standard | **rewritten as complex** (v2 C06) | 3 clues / 4 people was standard-level; now 5 people / 6 constraints |
| v1 T13 | possibly complex | **kept standard** (v2 T13) | Investigated (flagged possibly complex). Kept standard: one anchor date plus one modular-arithmetic step. Its difficulty for models comes from computing without tools, not from reasoning depth. That's noted as a fairness point, not a label change. |

Every final label's rationale is recorded per case in the review pack.

## Scorer changes (backward compatible; v1 scoring is unaffected)

- `exact`: `accept` (equally correct variants).
- `regex`: `strip_fences`.
- `numeric`: `first_number`.
- `contains`: `groups` (one of each), `all_words` / `none_words` (whole-word), `max_sentences`.
- `json`: `list_pairs` (key → value with alternatives), `list_length`.
- All methods: `final_answer: true` scores only the last `ANSWER:` line (missing line = fail).

## Pre-registration (item 11)

`preregistration_routewise_bench_v2.yaml` (prereg-v2) was written before any v2 run; no live benchmark of any version has ever run. Compared with prereg-v1:

- the primary population is all 45 cases
- run validity requires ≥ 95% answered per strategy (else the run is invalid and not publishable)
- a baseline floor of 0.60 applies (below it, no quality claim is made either way)
- per-difficulty results are descriptive only
- there is a scope statement on the GPT-OSS comparison

The margin (5 pp) and the CI rule are unchanged. The report enforces the validity and floor rules (`claims_allowed`, `claims_blocked_reasons`). The file's hash is pinned in the meta file, and the runner refuses a modified file.

## Tests (item 14)

`backend/tests/evaluation/test_dataset_v2.py` contains:

- a correct/wrong reference pair for every case
- adversarial answers for every changed rule (including every v1 probe that exposed a false pass or false fail)
- a test that every changed case has adversarial coverage
- a test that unchanged cases are byte-identical to v1
- pre-registration pinning and dataset-mismatch tests
- report-guard tests on synthetic outcomes
