# Benchmark operator runbook: routewise_bench_v5.2.3, Days 2–4 and the combined report

Use this runbook to run the remaining registered benchmark days from PowerShell without Claude Code.
Everything here uses the committed helpers `scripts\benchmark-day.ps1` and `scripts\benchmark-combine.ps1`.
Don't edit the registered files (`evaluation\*v5.2.3*`, the dataset, the scoring amendment or the attestation),
`.env`, or the production deployment.

## Final Day 4 state (2026-11-07): completed under v5.2.6 (post-incident, exploratory)

- **Day 4 is complete** under `routewise_bench_v5.2.6`, which authorises Day 4 only and declares
  `publishable: false`. It ran 02:51:04–03:02:29 UTC with
  `.\scripts\benchmark-day.ps1 -Revision routewise_bench_v5.2.6 -Day 4 ... -Run`.
  - 36/36 combinations; baseline 12/12, both RouteWise strategies 11/12 (T04 failed).
  - 36 Groq attempts and 11,505 tokens; no retries or fallbacks.
  - Full record: `docs\BENCHMARK_DAY4_CLOSURE_v5.2.6.md`.
- **Day 4 can't run again.** Its claim `7e6ee6dc-1b85-40e5-b4a8-f9b0c72f55f4` refuses any second start. Never
  delete it or the Day 3 claim.
- **No further day is registered.** All four scheduled days have been run once, but the original v5.2.3 four-day
  confirmatory comparison remains incomplete, and no pooled analysis is registered.

## Final Day 3 state (2026-11-06): completed under v5.2.5 (post-incident, exploratory)

- **Day 3 is complete** under `routewise_bench_v5.2.5`, which authorises Day 3 only and declares
  `publishable: false`. It ran 05:11:42–05:21:56 UTC with
  `.\scripts\benchmark-day.ps1 -Revision routewise_bench_v5.2.5 -Day 3 ... -Run`.
  - 33/33 combinations; 11/11 pass for every strategy.
  - 33 Groq attempts and 8,968 tokens; no retries or fallbacks.
  - Full record: `docs\BENCHMARK_DAY3_CLOSURE_v5.2.5.md`.
- **Day 3 can't run again.** The atomic execution claim `d150469c-eb6e-436f-b599-ea386254b734` (Neon table
  `benchmark_execution_claims`, migration 0003) refuses any second start of v5.2.5 day 3. Never delete it.
- **Day 4 is not authorised.** v5.2.5 refuses day 4. Running it needs a new registration, and there is no completed
  four-day confirmatory experiment.

## Final Day 2 state (2026-11-05): completed by a disclosed post-hoc recovery (v5.2.4)

- **Day 2 is complete as a disclosed recovery, not as a clean prospective run.** Revision
  `routewise_bench_v5.2.4`, registered 2026-11-05T08:56:09Z after 11 of Day 2's outcomes had been
  observed, carried over those 11 genuine results unchanged. It ran the 25 missing combinations once
  (09:09–09:18 UTC), with no retries or fallbacks needed.
- **Recovery runs** (all `completed`): baseline_premium `02641677-f97b-4cd4-899f-1d20a8d44d90`,
  routewise `6d930fbe-ccb8-4f23-9159-0baae51a7a82`, routewise_tier_first
  `fcf7088b-b062-40bd-abe9-bb88a297013e`. The three original v5.2.3 runs stay `failed`.
- **Report:** `evaluation\reports\v5.2.4-day2-recovery\` (built from Neon with
  `uv run python -m app.cli eval-recovery-report --dataset routewise_bench_v5 --revision routewise_bench_v5.2.4 --label <name>`).
  - 36/36 combinations, 0 missing, status `complete`, `publishable: false` (post-hoc).
  - Pass rates 12/12 for every strategy.
  - Day 2 used 10,632 Groq tokens in total.
  - Details and hashes are in `evaluation\datasets\routewise_bench_v5.2.4.CHANGELOG.md`.
- **The recovery runs once.** A second `eval-run --revision routewise_bench_v5.2.4 --schedule-day 2` is
  refused, because a run already carries the recovery plan. Never re-run Day 2 under any revision.
- **Runs left `running`** (for example after a database outage during finalisation) are closed with
  `uv run python -m app.cli eval-finalize-runs --run-id <id> [--run-id <id> ...]`, which changes only
  runs that are still `running`.
- **Days 3 and 4 are not run.** The v5.2.3 four-day comparison remains incomplete. Running them, or
  pooling all four days, needs a new registration.

## 0. Status before the recovery (2026-11-05 morning): the registered v5.2.3 comparison is INCOMPLETE

> **Never restart Day 2.** Don't run `.\scripts\benchmark-day.ps1 -Day 2` (or the old Day 2 command) again. Day 2
> started once, was interrupted, and under the registered protocol it can't be resumed or re-run. The helper now
> refuses it, and Days 3–4, before any provider call.

- **Day 1: complete.** 2026-11-04 UTC (21:06–21:17), 30/30 results, report `evaluation\reports\v5.2.3-day1\`
  (hashes in section 6).
- **Day 2: interrupted, never completed.** It started 2026-11-05 06:48:43 UTC.
  - **Failure:** after 11 of its 36 strategy/case combinations, a **Neon database timeout** (`asyncpg`
    TimeoutError) stopped it before the next step's request was sent. The run's finalisation then timed out too
    (`runner.py` line 423), which hid the first error. No provider request was in flight.
  - **Runs:** the three original runs were kept and are now marked **`failed`** (closed 2026-11-05 with the owner's
    approval):
    - baseline_premium `4c2aed09-3b2c-4f56-ac93-24cc0c59019d`
    - routewise `8221d2a2-ef04-4515-8d79-fffa0c60d640`
    - routewise_tier_first `315cc0c9-e8ee-4a2f-946b-843525d4e485`
  - **Preserved:** **11 genuine results**, unchanged in Neon:
    - baseline_premium and routewise: S06 S07 S14 T02
    - routewise_tier_first: S06 S07 S14
  - **Missing: 25 combinations.**
    - baseline_premium and routewise: T08 T09 T14 T15 T18 C01 C06 C08
    - routewise_tier_first: T02 T08 T09 T14 T15 T18 C01 C06 C08
  - **Groq usage:** **1,702 tokens** (gpt-oss-20b 946, gpt-oss-120b 756) over 11 attempts.
  - **Incident record:** `evaluation\reports\v5.2.3-day2\`, marked `incomplete: true`, `publishable: false`. It is
    titled "Day 2 Interrupted — Non-publishable Incident Record" and is not a benchmark result.
  - **Evidence backup:** `evaluation\reports\incident-2026-11-05-day2-evidence\` holds the ledger, the Neon export
    and the registered hashes as they were before the closure.
- **Why it can't be resumed:** the registered schedule and pre-registration say each day runs exactly once,
  nothing is re-run, and a stopped or incomplete day makes the whole comparison incomplete. Resuming would also
  need changes to `runner.py`, which the v5.2.3 manifest pins.
- **Days 3 and 4: blocked.** Running them can't make v5.2.3 complete, so the helper refuses them.
- **A clean four-day comparison needs a new registration** (a new revision with its own schedule, written before
  any of its runs), plus a fix for the database failure handling in the runner.

### Helper hardening (2026-11-05)

`scripts\benchmark-day.ps1` now calls `scripts\benchmark_guard.py` before the preflight and before `-Run`.
The guard refuses, before any provider call, if any of these holds:
- a local report or report folder exists for the day
- the quota ledger already has provider attempts on today's UTC date
- **Neon already has evaluation runs for that day, of any status**, checked read-only with the app's settings
- an earlier day is missing or incomplete
- another day already ran on this UTC date
- the 14-day span is exceeded

If Neon or the ledger can't be read, it refuses (fail closed). The rest of this runbook describes the original
procedure; it applies only to a future, newly registered schedule.

## 1. Dates and quota requirements

| Day | Cases | Needs (smaller model's remaining tokens) | Earliest UTC date | Latest UTC date |
|---|---|---|---|---|
| 2 | S06 S07 S14 T02 T08 T09 T14 T15 T18 C01 C06 C08 | **160,754** | 2026-11-05 | the day before Day 3 |
| 3 | S02 S03 S09 S10 T05 T07 T11 T13 C07 C09 C12 | **157,747** | the day after Day 2 | the day before Day 4 |
| 4 | S01 S04 S12 S13 S15 T01 T04 T10 T12 C02 C04 C05 | **167,285** | the day after Day 3 | **2026-11-18** |

- **One day per UTC date, in order, each run exactly once.** The helper enforces this.
- **14-day span.** Day 4 must run no later than 14 days after Day 1 (2026-11-04), so by 2026-11-18 UTC.
- **Start time.** Start between 00:00 and 22:00 UTC. In India time (UTC+5:30), a UTC date runs from 05:30 IST to
  05:29 IST the next morning, and the latest start is **03:30 IST** the next morning. Day 1 took 11 minutes; allow
  at least 30.

## 2. Before each day

1. **Location:** open PowerShell in `C:\Users\param\Desktop\MyProjects\intelligent-llm-gateway` (this machine).
2. **Repository:** check it is clean: `git status --short` must print nothing.
3. **Other traffic:** stop all other use of the Groq organisation (other scripts, tools, teammates) until the day
   finishes. The deployed demo uses the mock provider only, so it doesn't count.
4. **Models:** check that Groq's Models and Deprecations pages still list `openai/gpt-oss-20b` and
   `openai/gpt-oss-120b` unchanged. If either has changed or is deprecated, **don't run**; the registered
   comparison can't be completed.
5. **Fresh quota reading (every day, never reuse an earlier one):**
   - In the Groq console, open the organisation's limits/usage page.
   - For **both** models, note today's remaining daily tokens (daily limit − tokens used today).
   - Note the exact time you read them, in UTC, for example `2026-11-05T06:10:00+00:00`.
   - The reading must be from the same UTC date as the run and not in the future.

## 3. Preflight (no provider call)

Replace the three values with today's readings:

```powershell
.\scripts\benchmark-day.ps1 -Day 2 -Remaining20B <20B remaining> -Remaining120B <120B remaining> -VerifiedAt <UTC time read>
```

- **Pass:** the output ends with `preflight: OK`, then `Preflight OK for day 2.` and
  `Preflight only. Re-run with -Run to execute day 2.`
- **Refusal:** any error starting `refused` or `preflight FAILED (fail closed)` means don't run. The meanings are
  in section 7.

## 4. Run the day (makes the real Groq calls)

Run the **same command** with `-Run` added, using the same three values:

```powershell
.\scripts\benchmark-day.ps1 -Day 2 -Remaining20B <same> -Remaining120B <same> -VerifiedAt <same> -Run
```

The helper:
- runs the preflight again
- sets `MOCK_PROVIDER_ENABLED=false` for its own process only
- runs the day's cases with the registered pacing (`--delay-s 6`)
- checks afterwards that `.env` is unchanged

**Completed** looks like: `Day 2 finished with exit code 0. Report: evaluation\reports\v5.2.3-day2`.

**Exit code 1** means the warning `day 2 is INCOMPLETE`. The quota guard stopped the day, or it didn't finish.
**Never re-run it**: the registered comparison is then incomplete, by design. Keep everything and record what
happened.

Days 3 and 4 work the same way with `-Day 3` and `-Day 4`, each on its own later UTC date.

## 5. Check the day's output

```powershell
$Day = 2; $dir = "evaluation\reports\v5.2.3-day$Day"
$s = Get-Content "$dir\summary.json" -Raw | ConvertFrom-Json
$rows = @(Get-Content "$dir\results.jsonl" | Where-Object { $_.Trim() })
"day $($s.execution_schedule.day) of $($s.execution_schedule.days) | UTC date $($s.execution_schedule.utc_date) | incomplete $($s.incomplete) | simulated $($s.simulated) | revision $($s.execution_revision) | prereg $($s.preregistration_sha256.Substring(0,12))"
"results: $($rows.Count) rows (expected $(3 * $s.execution_schedule.case_ids.Count)) | provider errors: $(@($rows | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.error_code }).Count)"
$s.metrics.PSObject.Properties | ForEach-Object { "  $($_.Name): answered $($_.Value.answered)/$($_.Value.cases), passed $($_.Value.passed)/$($_.Value.scorable)" }
Get-FileHash "$dir\*" -Algorithm SHA256 | ForEach-Object { "  " + $_.Hash.ToLower() + "  " + (Split-Path $_.Path -Leaf) }
```

The output should show:
- the right day number and today's UTC date
- `incomplete False` and `simulated False`
- revision `routewise_bench_v5.2.3` and pre-registration `116111218e21`
- 36 rows for Day 2, 33 for Day 3 and 36 for Day 4

Provider errors are allowed: the registered rule counts them as missing answers, never as dropped cases.

## 6. Preserve the artifacts

Reports and the quota ledger are git-ignored, so they exist only on this machine (results are also in Neon).
After each day:

1. Copy `evaluation\reports\v5.2.3-day<N>\` and `evaluation\reports\quota_ledger.json` to a backup location,
   for example a dated folder in OneDrive.
2. Save the `Get-FileHash` lines from section 5 in a notes file with the date.

Never edit, rename or delete a day's report, and never delete the ledger. The helper uses both to block repeats.

Day 1 reference hashes:
- `summary.json` `18f292b10ed78a5c4c2bf88ee574fa913c09a5f6167a70e9bc19b4fffaeae64a`
- `results.jsonl` `b5f18de908e20535efc61f5af557e2469b9fe059a121aa8c5fe159c8b3d3ff2b`
- `summary.md` `2f9e3213dea4a46e65beb22f6d6f2b28fe46b3a3243dc490ecf02fd068b8f2fd`

## 7. What a refusal means

| Message | Meaning and what to do |
|---|---|
| `insufficient quota: X < Y` | the smaller model's remaining tokens are below the day's requirement. Don't start; use a later UTC date (within the span) |
| `the quota must be read today (UTC date …)` | the reading is from another UTC date. Take a fresh reading |
| `-VerifiedAt is in the future` / `must include a UTC offset` | use the exact read time, with `+00:00` or `Z` |
| `too late: a day must start at least 2 hours before 00:00 UTC` | it's after 22:00 UTC. Start after 00:00 UTC (05:30 IST) on the next date |
| `day N already ran on <date> (UTC)` | a day already ran on this UTC date. Wait for the next UTC date |
| `day N has not run yet: days run in order` | run the previous day first |
| `day N already has a report` / `report directory … already exists` | that day already ran. Never re-run it |
| `day 1 ran N days ago; the registered span is 14 days` | the window has passed. The registered comparison can't be completed; don't run |
| `preflight FAILED (fail closed)` | read the `PROBLEM:` lines above it. Don't run |
| `refused, day N not started: …` | the guard's reasons follow, separated by `\|`. Each is final; don't work around it |
| `Neon already has … evaluation run(s) for day N` | that day already started (even if it crashed without a report). Never restart it |
| `the quota ledger already records … provider attempt(s) on <date>` | a day already sent requests today. Never restart; a new day needs a new UTC date |
| `day N is recorded as incomplete` | the registered comparison can't be completed; no further day may run |
| `could not check Neon … (fail closed)` / `could not read the quota ledger` | the guard couldn't confirm the day hasn't started. Fix connectivity and check again; never bypass |

## 8. Combined report (after Day 4)

```powershell
.\scripts\benchmark-combine.ps1
```

This needs all four reports and makes no provider call. It pools all 45 cases with the registered analysis:
paired by case, with the registered margins and bootstrap. It writes `evaluation\reports\v5.2.3-combined\` with
`summary.json`, `summary.md` and `results.jsonl`.

The script prints `Combined report: evaluation\reports\v5.2.3-combined (exit N; 0 = complete)`.

- **`exit 0`:** the combined comparison is complete.
- **`exit 1`:** it is incomplete (an incomplete day, a missing result or the span exceeded); it is never publishable.
  Any `schedule violation:` lines above that message say why.
- **Refusal:** a missing day, a duplicate, the wrong registration or dates out of order. The error message names
  the problem.

Only this combined report is the benchmark result. Per-day pass rates are descriptive.

## 9. Requirements on this machine

- `uv` with this project's locked packages cached. The helpers run `uv run --offline --frozen`.
  - If `uv` reports a missing package, run `uv sync --locked` once in `backend\` (this downloads packages and
    calls no LLM).
- `.env` as it is now. It holds the Groq key and the Neon `DATABASE_URL`, with Groq enabled and
  `GROQ_BILLING_PLAN=free`.
  - `MOCK_PROVIDER_ENABLED` stays `true` in `.env`; the helper overrides it for the run only.
- Internet access to Groq and Neon.
