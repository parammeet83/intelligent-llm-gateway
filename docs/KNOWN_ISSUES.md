# Known issues

Genuine defects found during the documentation reviews on 2026-11-06 and 2026-11-07. They are recorded here instead of being
silently fixed: the review was documentation-only. None affects routing, tenancy, budgets or the benchmark data
itself.

## KI-1: the Evaluation page shows "publishable" for non-publishable runs

**Status: FIXED and deployed** (release commit `43a2394` (CI run 42336926673 green), deployed once to Vercel production as `dpl_27aHL1rWd8rWgzuikZmx9dG97TTa` on 2026-11-07). Verified on production (19/19 read-only checks).
- Each group shows its execution status and its publication eligibility as separate badges, taken from the
  registration recorded in its runs' `config_snapshot`; no scheduled day or recovery is badged "publishable".
- The recovery shows 36/36 combinations accounted for: 11 carried over + 25 newly executed, per strategy too.
- A page notice states that v5.2.3's interrupted Day 2 leaves its four-day comparison incomplete.

Regression tests are in `App.test.tsx`. No backend, schema or benchmark record changed. The description below is
the original defect.

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

**Fix (in source; not deployed):** the badge now says `post-hoc recovery · not publishable`, `interrupted ·
incident record` or `not publishable` for any scheduled day, and the recovery group explains "25 executed + 11 carried over
= 36". The original proposal was:
1. Show a per-label status from the registration (`publishable`, `kind`) rather than the run summary.
2. Hide or relabel the per-run "publishable" badge for scheduled days and recoveries.
3. For the recovery, show the 36-combination totals from the official report instead of the per-run summaries.

## KI-2: the Evaluation page header is out of date

**Status: FIXED and deployed** (same release as KI-1). The page now shows the review status from the persisted
attestation: 45 cases attested by the project owner (`b7099444ac31`), with the T17 translator-assisted disclosure.

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

**Fact:** a pooled four-day analysis can't be produced, because the original v5.2.3 Day 2 is an interrupted
incident and Days 2 (recovery), 3 and 4 ran under separate exploratory registrations; no pooled analysis is registered. The text is generic schedule output, so the reports were **not** edited (they are hash-recorded evidence).
[BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) states the correct status.

## KI-4: the DEMO banner overstates "no real model was called"

**Status: FIXED and deployed** (same release as KI-1). The banner now reads: "DEMO — simulated responses.
Interactive production requests use simulated responses through the mock provider. Historical evaluation
records may include real provider calls; those records are not live production traffic."

**Where:** [`frontend/src/components/DemoBanner.tsx`](../frontend/src/components/DemoBanner.tsx).

**Text:** "Only the mock provider is enabled. No real model was called and no figures here describe real usage."

**Fact:** the deployed API only serves the mock provider, but the benchmark CLI writes its real Groq requests
(tenant `eval-runner`, Days 1–4) to the same Neon database. They appear in Overview totals, Request Logs and
Usage & Cost. So the banner's second sentence is wrong for the historical data shown.

**Found:** while capturing the production screenshots on 2026-11-07.

**Original proposal:** a rewording along these lines; the deployed text above is the final version.

## Not defects, but worth knowing

- `tenants.cache_enabled` exists in the schema but is unused (caching was rejected by design).
- Provider health, circuit breakers and the OpenRouter quota counter are per process, so they reset on restart. On
  Render's free tier the instance restarts after idling.
