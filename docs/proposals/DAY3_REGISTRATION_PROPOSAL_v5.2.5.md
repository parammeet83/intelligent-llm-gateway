# PROPOSAL (NOT REGISTERED): Day 3 execution registration `routewise_bench_v5.2.5`

**Status: draft for the owner's decision. Nothing here is registered, hashed or authorised.** It is
deliberately kept outside `evaluation/` so that no tool can treat it as a registration. No provider
call was made to prepare it.

## Why Day 3 is blocked today (verified 2026-11-06 02:5x UTC, read-only)

| Registration | What happens for Day 3 | Basis |
|---|---|---|
| `routewise_bench_v5.2.3` | **Refused.** `scripts/benchmark_guard.py`: "day 2 is recorded as incomplete … no further day may run" | The schedule rules say each day runs exactly once and a stopped or incomplete day makes the comparison incomplete. Day 2 stopped on 2026-11-05 |
| `routewise_bench_v5.2.4` | **Refused.** `eval-validate --schedule-day 3`: "the registered recovery is for day 2, not day 3" | Its pre-registration says "Scope: Day 2 only … Days 3-4 need their own registration" |

Current facts: Neon has no Day 3 runs or results; the quota ledger has no attempts after 2026-11-05;
no evaluation run is `running`.

## Proposed registration

- **Revision:** `routewise_bench_v5.2.5`, a **post-incident, exploratory** execution registration for
  **Day 3 only**. It is written after Days 1–2 outcomes were observed (Day 1: 28/30 passes; Day 2:
  36/36 via the disclosed recovery), so it is **not prospective** and **never publishable as a
  confirmatory result**.
- **What stays unchanged (pinned by hash, not edited):** dataset `routewise_bench_v5` (`76a4d190…`),
  metadata, scoring amendment, review attestation, the v5.2.3 execution schedule (`c74699c1…`),
  strategies, routing policy, model registry, pacing (concurrency 1, delay 6 s), retries and
  fallbacks (Groq max_retries 1; eligible-model fallbacks), the quota guard (GROQ_QUOTA_V5_2) and
  the statistics.
- **Day 3 cases** (from the pinned schedule): S02 S03 S09 S10 T05 T07 T11 T13 C07 C09 C12. That is
  **11 cases × 3 strategies = 33 combinations**, run in the registered interleaved order.
- **Worst case** (recomputed with the current code; identical to the registered schedule):
  - 33 requests, at most **94 attempts** (120B 66, 20B 28)
  - **141,972 tokens** (120B 104,448; 20B 37,524)
  - required remaining on the tighter model: **157,747** (at 90% safety)
- **Execution window:** one UTC date chosen at registration time. Start between 00:00 and 22:00 UTC
  on that date, with a fresh owner-verified console reading taken on the same UTC date.
- **Runs once:** never re-run, including after an interruption. An interrupted Day 3 stays
  incomplete. Any recovery would need its own disclosed registration.
- **Incidents:** the v5.2.4 reliability rules apply:
  - bounded database backoff
  - idempotent persistence
  - a combination is retried only when the ledger proves nothing was sent; otherwise the run stops
  - finalisation never hides the original error
  - `eval-finalize-runs` for runs left `running`
- **Complete only if:** all 33 combinations have exactly one persisted result, each linked to its
  request log; all three Day 3 runs are `completed`; no run is `running`; and a report built from
  Neon matches it field by field.
- **Publishable:** never as a confirmatory result. **Day 4 is not authorised by this registration.**
- **Pooling:** none. Pooling Days 1–4 would need yet another disclosed registration, and would mix a
  prospective day, an incident and recovery, and post-incident days.

## Required code change before registering (needs your authorisation)

The v5.2.4 runner has no "this scheduled day already started" check. Today that protection lives
only in `scripts/benchmark_guard.py`, which is hard-wired to v5.2.3. Under a v5.2.5 registration,
`eval-run --schedule-day 3` could be started twice. The proposed fix:

1. In `backend/app/evaluation/runner.py`, before creating runs, refuse (fail closed, read-only) if
   Neon already has a run for the same revision and scheduled day, of any status. This mirrors the
   v5.2.4 `_refuse_started_recovery` check.
2. Make the helper and guard revision-aware: `-Revision routewise_bench_v5.2.5`, with labels
   `v5.2.5-day3`.
3. Add tests (a refusal with an existing run of any status; a refusal when Neon is unreachable).

Because `runner.py` is pinned, this must be done **before** the v5.2.5 manifest is generated. It also
makes v5.2.4 refuse at run time, which is fine: v5.2.4 has completed its only purpose.

## Steps once authorised

1. Make the code change and tests above; run the suite.
2. Generate and verify the v5.2.5 chain: revision, pre-registration, manifest. It reuses the pinned
   schedule; there's no recovery plan.
3. On the chosen UTC date, the owner reads both models' remaining tokens. Then run the read-only
   preflight (`eval-validate --revision routewise_bench_v5.2.5 --schedule-day 3` with the verified
   budget), and only then run once (`eval-run … --schedule-day 3`).
4. Build the Day 3 report from Neon and verify it field by field, along with the ledger and hashes.
   Then commit and push, and let CI run.
