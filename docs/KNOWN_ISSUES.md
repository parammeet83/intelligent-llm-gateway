# Known issues

Genuine defects found during the documentation review on 2026-11-06. They are recorded here instead of being
silently fixed: the review was documentation-only. None affects routing, tenancy, budgets or the benchmark data
itself.

## KI-1: the Evaluation page shows "publishable" for non-publishable runs

**Where:** [`frontend/src/pages/Evaluation.tsx`](../frontend/src/pages/Evaluation.tsx) (`RunGroup`), together with
the per-run summaries stored in `evaluation_runs`.

**What happens:** each label group's badge comes from its first run's stored `summary.publishable`.

| Group on the page | Stored summary says | Correct status |
|---|---|---|
| `v5.2.3-day1` | `publishable: true`. It passed its per-day gates, but the plan says a day is analysed only after all four are pooled | Not a publishable result on its own; the four-day plan is incomplete |
| `v5.2.4-day2-recovery-run` | `publishable: true`, with metrics for only the 25 recovered combinations (9/9, 8/8, 8/8) | **Non-publishable** post-hoc recovery. The official report, built from Neon by `eval-recovery-report`, covers all 36 combinations and says so |
| `v5.2.3-day2` | No summary (runs `failed`) | Incident record |
| `v5.2.5-day3` | `publishable: false` | Correct |

**Verified:** read-only through `GET /api/v1/admin/evaluation/runs` on production, 2026-11-06.

**Impact:** a viewer could read the green badge as a publishable result.

**Workaround for demos:** show [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md), or only the `v5.2.5-day3` group, and
say why.

**Proposed fix (not applied):**
1. Show a per-label status from the registration (`publishable`, `kind`) rather than the run summary.
2. Hide or relabel the per-run "publishable" badge for scheduled days and recoveries.
3. For the recovery, show the 36-combination totals from the official report instead of the per-run summaries.

## KI-2: the Evaluation page header is out of date

**Where:** the same file, the `PageHeader` description.

**Text:** "The dataset is AI-drafted and pending human review, so no run is publishable yet."

**Fact:** the owner attestation covers all 45 cases (`reviews/routewise_bench_v5.2.1_HUMAN_REVIEW_ATTESTATION.yaml`).
Runs are non-publishable for other reasons: an incomplete four-day plan, and post-hoc or post-incident
registrations.

**Proposed fix:** replace the sentence with one stating that no day is a publishable confirmatory result, and link
the reasons.

## KI-3: per-day report text suggests pooling

**Where:** the `summary.md` reports generated per scheduled day.

**Text:** "day N of 4 … pool all days with `eval-combine`".

**Fact:** a pooled four-day analysis can't be produced, because Day 2 (v5.2.3) is incomplete and Day 4 was not
run. The text is generic schedule output, so the reports were **not** edited (they are hash-recorded evidence).
[BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) states the correct status.

## Not defects, but worth knowing

- `tenants.cache_enabled` exists in the schema but is unused (caching was rejected by design).
- Provider health, circuit breakers and the OpenRouter quota counter are per process, so they reset on restart. On
  Render's free tier the instance restarts after idling.
