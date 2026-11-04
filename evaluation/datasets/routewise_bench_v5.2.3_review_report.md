# RouteWise v5.2.3 — Execution-schedule review report

Written for an independent reviewer. No benchmark result is reported.

## Quota

The figures, the reason for four days and the full allocation are in the changelog. The binding
constraint is daily tokens; the other limits have wide margins:

| Limit | Largest day | Cap |
|---|---|---|
| Tokens per day | 150,556 tokens | 180,000 shared cap |
| Requests per day | 100 attempts | 900 |
| Tokens per minute | about 25 minutes at 6,000 per minute | pacing only, not a blocker |
| Largest single attempt | 2,788 tokens | 6,000 per minute |

## Statistical validity of four days

- **Pairing preserved.** Every paired comparison (baseline vs each RouteWise strategy, per case)
  happens within one day, in the registered interleaved order. A shift that affects all strategies
  on a day equally cancels in the within-case differences.
- **Allocation is outcome-blind and registered before any run.** It is stratified by difficulty,
  so each day has simple, standard and complex cases, and it is reproducible from the seed.
- **No selective exclusion.** No day, case or strategy can be re-run or dropped. An incomplete day,
  a missing result or a span violation makes the pooled comparison incomplete and not publishable.
  Provider errors are missing, under the existing rule.
- **Analysis unchanged.** The same primary metric, margins and paired bootstrap (seed 20261104)
  over all 45 cases. Per-day pass rates and answering-model distributions are reported only as a
  drift check.
- **Provenance per day.** Each day records the UTC date, start and finish times, the schedule hash
  and day, the provider-reported model per answer, every attempt's model, and the attestation and
  amendment hashes.

## Residual risks

- **Model drift between days.** Groq exposes only model IDs, not versions or fingerprints, and
  none is recorded. A silent server-side update between days could affect strategies unequally:
  routewise uses 20B more often than the baseline does. Mitigations: model IDs are checked each day,
  the span is capped at 14 days (recommended: consecutive days), and the per-day table is
  descriptive.
- **Quota semantics.** Groq's reset header (86.4 s after one request, or 86,400 / 1,000) suggests
  a continuously replenishing daily window, not a midnight reset (unverified). The guard's model
  is conservative under either: it reads the budget once on the run day and subtracts all ledger
  usage since.
- **Prior usage.** It is accounted for by reading each model's remaining tokens on the run day and
  supplying the smaller value. The persistent ledger subtracts every attempt made since that
  reading, across processes and restarts. Other traffic on the organisation must be stopped.
