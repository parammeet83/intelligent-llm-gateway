# Evaluation

Status (2026-11-06): **live benchmark Days 1–3 run on Groq; Day 4 not run; the four-day confirmatory
experiment is incomplete.**
- Day 1 completed (v5.2.3).
- Day 2 was interrupted, then completed by a disclosed post-hoc recovery (v5.2.4, exploratory).
- Day 3 completed under a post-incident exploratory registration (v5.2.5, 33/33, 25/25 reconciliation checks).

Results and limitations: [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md). This file documents the method and the
history of dataset revisions; the revision notes below were written at the time and describe the state then.

**Current dataset: `routewise_bench_v5`** (pending your review), a scoring-only revision of v4. v1–v4
are kept unchanged, with their own pre-registrations and manifests. Changes:
[`routewise_bench_v5.CHANGELOG.md`](../evaluation/datasets/routewise_bench_v5.CHANGELOG.md). Review pack:
[`routewise_bench_v5_review.md`](../evaluation/datasets/routewise_bench_v5_review.md).

**v5 additions** ([`preregistration_routewise_bench_v5.yaml`](../evaluation/preregistration_routewise_bench_v5.yaml)):

- Whole-answer exact matching replaces label search (S01, S03, S04, S14).
- Strict single numbers with an explicit currency policy (`$` only for T11 and C09).
- T03 exact keys and JSON types.
- A schema-3 manifest that also pins the CLI, the quota pacer, error types, `uv.lock` and the runtime environment.
- **Token-aware quota pacing:** worst-case token reservation per call, all Groq models combined, with rate-limit headers that can only tighten it. A run stops incomplete rather than exceed a limit. The 6 s delay is a floor, not a guarantee. Only 8K tokens/min and 1K requests/day are observed for this account; 30 RPM and 200K tokens/day are unverified published values.

The v4 additions below still apply:

v4 superseded v3 after your
independent review. v1, v2 and v3 are kept unchanged, with their own pre-registrations. Changes:
[`routewise_bench_v4.CHANGELOG.md`](../evaluation/datasets/routewise_bench_v4.CHANGELOG.md). Review pack:
[`routewise_bench_v4_review.md`](../evaluation/datasets/routewise_bench_v4_review.md).

**v4 additions** ([`preregistration_routewise_bench_v4.yaml`](../evaluation/preregistration_routewise_bench_v4.yaml)):

- Strict `ANSWER:` lines, which must hold exactly one value.
- T17 as multiple choice.
- `baseline_premium` premium-only generation, verified and enforced per attempt.
- Pass rates labelled conditional on an answer being returned, with answer availability reported separately.
- The answering model and every attempt recorded per case.
- A schema-2 manifest that hashes every execution-critical module and pins pacing (`--delay-s 6`, sequential, no limit). `eval-run` refuses any other pacing.

Because v4 changed code that v3 pinned, v3 can no longer be run on current code (fail-closed by design).

The v3 rules below still apply in v4:



- A lower-cost claim needs **CI-supported** quality non-inferiority.
- Any **unknown cost observation** blocks cost claims. This includes unavailable list cost and every request that returned no answer; unknown is never treated as zero.
- Provider errors are **missing, not failed**.
- An **experiment manifest** ([`experiment_manifest_routewise_bench_v3.yaml`](../evaluation/experiment_manifest_routewise_bench_v3.yaml)) pins policy and weights, model registry, provider model IDs, pricing snapshots, code hashes and execution settings. The runner refuses any configuration drift before a network call.

> **Scope.** Results apply only to this fixed 45-case suite and the pinned configuration. They
> cannot establish general performance on production workloads.

> **What a live run measures.** Every enabled Groq model is OpenAI GPT-OSS: `gpt-oss-20b` serves
> the small tier and `gpt-oss-120b` the premium tier, and there's no medium-tier model. The live
> comparison is therefore mainly **between two sizes of one model family**, not across independent
> model families. Results must not be generalised beyond that. (Recorded in the v2
> pre-registration's `scope`.)

## What is compared

| Strategy | Definition |
|---|---|
| `baseline_premium` | Every case forced to the premium tier (`preferred_tier=premium`): the "all-premium baseline" the spec card asks for first (S1-12) |
| `routewise` | Policy `rw-2026.11-v1` as configured (`selection: cheapest_capable`) |
| `routewise_tier_first` | Same policy with `selection: lowest_tier_first`. Tests carried issue 1: does keeping simple tasks on small models trade quality for cost? |

Same 45 cases, same gateway pipeline (routing, retries, fallbacks, accounting, logging), and
temperature 0. Strategies are **interleaved per case** with alternating order, so provider load and
time effects hit all strategies alike. Each strategy has its own fresh provider-health state. An
evaluation tenant with no budget keeps budgets from changing model choice.

## Pre-registration (S1-12)

Each dataset version has its own pre-registration, written **before any live run**:
[`preregistration.yaml`](../evaluation/preregistration.yaml) (prereg-v1, for v1) and
[`preregistration_routewise_bench_v2.yaml`](../evaluation/preregistration_routewise_bench_v2.yaml)
(prereg-v2, for v2). The runner loads the one registered for the dataset being run and refuses one
registered for another dataset. For v2 it also refuses a file whose SHA-256 differs from the hash
pinned in `routewise_bench_v2.meta.yaml`, so thresholds can't be edited after results exist. A change
needs a new pre-registration version, recorded before the run. The SHA-256 is stored on every run.

prereg-v2 keeps the rules below and adds three that the report enforces (`claims_allowed`,
`claims_blocked_reasons`):

- **run validity:** at least 95% of cases must be answered per strategy, otherwise the run is invalid and not publishable
- **baseline floor:** if the baseline's pass rate is below 0.60, the comparison is uninformative and no quality claim is made
- **per-difficulty results:** descriptive only

- **Quality rule:** RouteWise is non-inferior if its pass rate is within **5 percentage points** of
  the baseline's. "Supported" only if the lower bound of the paired-bootstrap 95% CI of the
  difference is above −0.05.
- **Cost rule:** claim lower estimated cost only if the quality point estimate holds **and**
  estimated list cost per accepted answer is lower.
- **Publication:** only from `simulated=false` runs on a fully human-reviewed dataset.

## Dataset (`evaluation/datasets/routewise_bench_v2.jsonl`; v1 kept for the record)

45 cases: 15 simple, 18 standard, 12 complex, labelled with a written complexity rubric (rationale
per case in the review pack). Categories cover classification, extraction, summarisation, QA, maths,
reasoning, transformation, planning, and code reasoning. Each case has an ID,
category, difficulty, task type, prompt, expected-answer description, scoring rule, and output
budget. Per-difficulty cost and latency limits are in the pre-registration.

**Originality:** v1's T09, C03, C04 and C05 used inputs identical to public LeetCode examples
(confirmed by search; sources in the changelog), so they're removed in v2. The 12 new v2 cases were
written for this dataset but not exhaustively searched against public sources, so no stronger
originality claim is made.

**Provenance (S2-04 / C-05): AI-drafted (Claude) on 2026-11-04, pending your review.** The metadata
file records `status: draft-pending-human-review` and an empty `reviewed_by` map. Until every case has
a reviewer entry, reports are marked not publishable. To review a case, check that the prompt is
unambiguous, the expected answer is right, and the scorer accepts all and only correct answers. Then
add `S01: {reviewer: "...", date: "...", notes: "..."}` under `reviewed_by`.

## Scoring (deterministic; no LLM judge)

| Method | v2 cases | Rule |
|---|---|---|
| `choice` | 4 | exactly one allowed label present (ambiguous answers fail) |
| `exact` | 13 | normalised string equality, with optional accepted variants (case-sensitive where specified) |
| `regex` | 3 | anchored pattern match, optionally inside a code fence |
| `numeric` | 8 | one unambiguous number, or the last number, or the first number on the `ANSWER:` line, within tolerance |
| `json` | 12 | valid JSON; field subset, exact lists, list membership, name→value pairs, list length, per-key sums |
| `contains` | 4 | required / one-of groups / forbidden terms (whole-word where specified), word and sentence caps |
| `validator` | 1 | named checker (meeting-schedule constraints) |

`final_answer: true` (7 cases: T10, T12, C02, C03, C06, C08, C09) scores only the value on the last `ANSWER:` line, so working shown
above it can't be mistaken for the answer, and a missing line fails.

**Scorer validation:** `tests/evaluation/test_dataset_v2.py` has a correct/wrong reference pair for
every v2 case, plus adversarial answers for every changed rule. Those are wrong answers that used
to pass and right answers that used to fail in v1, each pinned to its required outcome. v1 keeps its
own 45 pairs in `test_dataset_and_scorers.py`.

**No code execution and no human grading in v2.** v1 ran model-generated code in a `python -I -S`
subprocess, which isn't real isolation: the code could still reach files, the network and processes,
and no OS sandbox is available locally. So v2 uses only non-executable code tasks (output prediction,
bug location, SQL result prediction), and its meta sets `code_execution: false`, which the loader
enforces. v1's subjective C10 essay is replaced by an objective critical-path task.

## Metrics per strategy

Pass rate with Wilson 95% CI (overall and by difficulty), failures and failure codes, estimated
list cost (total, per request, per accepted answer), requests with unknown list cost, actual-charge
status counts, input/output tokens, p50/p95 latency, fallback rate, provider/model/tier
distribution, and per-case limit violations. Comparisons against the baseline: paired pass-rate
difference with a seeded bootstrap CI (10,000 resamples, seed 20261104), cost-per-accepted ratio, and
the pre-registered verdicts. Failed and incomplete runs are kept in the report, never dropped.

## Running it (PowerShell, from `backend\`)

```powershell
uv run python -m app.cli eval-validate --dataset routewise_bench_v5   # manifest check + quota preflight
# Live run (needs real provider keys in .env and your go-ahead). Pause between requests for free-tier limits:
uv run python -m app.cli eval-run --dataset routewise_bench_v5 --label 2026-11-xx-live --delay-s 6
# Pipeline check with only the mock provider (labelled simulated, never a result):
uv run python -m app.cli eval-run --label pipeline-check --allow-simulated
```

Outputs go to `evaluation/reports/<label>/` (`summary.json`, `summary.md`, `results.jsonl`, plus
`evaluation_runs` and `evaluation_results` rows). Simulated runs get a `simulated-` prefix.
`evaluation/reports/` is git-ignored except `published/`. Copy a run there only after it meets the
publication rule.

**Quota planning:** a full run is 45 × 3 = 135 gateway requests, plus retries. That fits Groq's free
plan per day only if its limits allow, and must be checked in the Groq console. OpenRouter's
50/day free allowance is a fallback reserve only.

## Pipeline check performed (2026-11-04, mock provider, scratch SQLite)

45 cases × 3 strategies = 135 requests completed, with all results persisted and a report written.
This was v1, before the v2 revision. Every mock answer failed scoring (0/38 auto-scorable). That's expected, since mock text answers no
question, and it confirms the scorers don't hand out false passes. The run was correctly marked
**not publishable** (simulated; dataset unreviewed).

## Limitations and external validity

- 45 cases is a small sample: a 5-point difference is within noise. The CIs will be wide.
- AI-drafted cases may share blind spots with AI models; your review is the mitigation.
- "Premium" means the strongest *free* model available, not a frontier model.
- Small and premium tiers are currently two sizes of one family (GPT-OSS 20B vs 120B), so the
  comparison doesn't measure routing across independent model families.
- Costs are shadow list prices observed on 2026-11-03/04. Free-tier calls really cost $0.
- Free-tier latency includes queueing and rate limits, so it differs from paid tiers.
- Running live doesn't make results stable. Provider catalogs and behaviour change, so results are
  tied to the run date and the stored config snapshot.

## Observed failure modes (S2-05)

The table is filled only from real request IDs. One has been observed so far, from the live smoke
test rather than the benchmark. Candidates still to check, not yet observed: short-but-hard prompts
scored as simple; reasoning models returning empty completions under small `max_output_tokens`;
JSON wrapped in prose; free-tier 429s during a run; OpenRouter's daily cap.

| # | Case | Strategy | What broke | Why | Request ID |
|---|---|---|---|---|---|
| 1 | live smoke (not a benchmark case) | single model, no fallback | Routed to `groq/llama-3.1-8b-instant`, got HTTP 404 `model_not_found`. Correctly classified, no retry, $0, persisted | Groq shut the model down on 2026-08-16. The registry was stale, and the smoke script skipped the startup catalog check that would have excluded it. Fix: model disabled, and the check is no longer bypassed | `f97f51fc-8e78-41c3-9a7b-53e5e413fe33` |
