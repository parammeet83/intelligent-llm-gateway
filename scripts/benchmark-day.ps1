<#
.SYNOPSIS
  Run ONE registered day of a registered benchmark schedule safely (default revision
  routewise_bench_v5.2.3; pass -Revision for another, e.g. routewise_bench_v5.2.5).

.DESCRIPTION
  - Runs only the day you name. It never starts another day.
  - Reads that day's registered requirement from the hash-pinned schedule (via the app's own loader).
  - Takes the fresh remaining daily tokens of BOTH Groq models as read in the console today, uses
    the smaller one (the registered rule), and refuses if it is below the day's requirement.
  - Refuses (fail closed, via scripts\benchmark_guard.py) a day that already started: a local report,
    provider attempts in the quota ledger today (UTC), or Neon evaluation runs for that day, of any
    status. Also refuses a day whose earlier day hasn't run or is incomplete, a second day on the
    same UTC date, a 14-day span overrun, a start after 22:00 UTC, or Neon being unreachable.
  - Always runs the read-only preflight first. Without -Run it stops after the preflight.
  - Sets MOCK_PROVIDER_ENABLED=false for this process only; .env is never modified (checked).
  - Results and snapshots go to evaluation\reports\v5.2.3-day<N>\ (and to the database).

.EXAMPLE
  .\scripts\benchmark-day.ps1 -Day 1 -Remaining20B 199800 -Remaining120B 199700 -VerifiedAt 2026-11-05T08:10:00+00:00
  .\scripts\benchmark-day.ps1 -Day 1 -Remaining20B 199800 -Remaining120B 199700 -VerifiedAt 2026-11-05T08:10:00+00:00 -Run
#>
param(
    [Parameter(Mandatory)][ValidateRange(1, 4)][int]$Day,
    [Parameter(Mandatory)][ValidateRange(0, 100000000)][int]$Remaining20B,
    [Parameter(Mandatory)][ValidateRange(0, 100000000)][int]$Remaining120B,
    [Parameter(Mandatory)][string]$VerifiedAt,
    [string]$Source = "Groq console limits page",
    [string]$Revision = "routewise_bench_v5.2.3",
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$reports = Join-Path $root "evaluation\reports"
if ($Revision -notmatch '^routewise_bench_v[0-9.]+$') { throw "-Revision must look like routewise_bench_v5.2.5" }
$label = ($Revision -replace '^routewise_bench_', '') + "-day$Day"
$envFile = Join-Path $root ".env"

# --- verified time: an ISO 8601 instant with an offset, today (UTC), not in the future ---------------
try { $verified = [DateTimeOffset]::Parse($VerifiedAt, [Globalization.CultureInfo]::InvariantCulture) } catch {
    throw "-VerifiedAt must be ISO 8601 with a UTC offset, e.g. 2026-11-05T08:10:00+00:00" }
if ($VerifiedAt -notmatch '(Z|[+-]\d\d:\d\d)$') { throw "-VerifiedAt must include a UTC offset" }
$now = [DateTimeOffset]::UtcNow
if ($verified -gt $now.AddMinutes(1)) { throw "-VerifiedAt is in the future" }
if ($verified.UtcDateTime.Date -ne $now.UtcDateTime.Date) { throw "the quota must be read today (UTC date $($now.UtcDateTime.ToString('yyyy-MM-dd')))" }
if ($now.UtcDateTime.TimeOfDay -gt [TimeSpan]::FromHours(22)) { throw "too late: a day must start at least 2 hours before 00:00 UTC" }

# --- fail-closed guard (scripts/benchmark_guard.py), BEFORE the preflight and before -Run ----------
# A day may never start twice, even after a crash that left no report. Refuses if this day has a local
# report, if the quota ledger already has provider attempts today (UTC), if Neon already has runs for
# this day (any status), if an earlier day is missing or incomplete, if another day ran today, or if
# the 14-day span is exceeded. If any of these can't be checked (e.g. Neon unreachable), it refuses.
$ledgerPath = Join-Path $reports "quota_ledger.json"
Push-Location $backend
try {
    $guardOut = uv run --offline --frozen python (Join-Path $root "scripts\benchmark_guard.py") --day $Day --reports $reports --ledger $ledgerPath --revision $Revision
    if ($LASTEXITCODE) { throw "the safety guard could not run (exit $LASTEXITCODE): day $Day not started (fail closed)" }
} finally { Pop-Location }
try { $info = ($guardOut | Select-Object -Last 1) | ConvertFrom-Json } catch { throw "the safety guard returned no result: day $Day not started (fail closed)" }
if ($null -eq $info.problems) { throw "the safety guard returned no verdict: day $Day not started (fail closed)" }
if (@($info.problems).Count -gt 0) { throw ("refused, day $Day not started: " + (@($info.problems) -join " | ")) }
$remaining = [Math]::Min($Remaining20B, $Remaining120B)
Write-Host "Day $Day of ${Revision}: $($info.cases.Count) cases ($($info.cases -join ' '))"
Write-Host "Worst case $($info.worst_case) tokens; requires remaining >= $($info.required) (smaller model)."
Write-Host "Supplied: 20B $Remaining20B, 120B $Remaining120B -> using $remaining (verified $VerifiedAt)."
if ($remaining -lt $info.required) { throw "insufficient quota: $remaining < $($info.required). Do not start; use a later UTC date." }

# --- preflight, then (only with -Run) the day itself --------------------------------------------------
$envHash = (Get-FileHash $envFile).Hash
$previousMock = $env:MOCK_PROVIDER_ENABLED
$env:MOCK_PROVIDER_ENABLED = "false"   # this process only; .env is not touched
$common = @("--dataset", "routewise_bench_v5", "--revision", $Revision, "--schedule-day", "$Day",
            "--remaining-daily-tokens", "$remaining", "--daily-budget-source", $Source,
            "--daily-budget-verified-at", $VerifiedAt)
Push-Location $backend
try {
    uv run --offline --frozen python -m app.cli eval-validate @common
    if ($LASTEXITCODE) { throw "preflight FAILED (fail closed): day $Day not started" }
    Write-Host "`nPreflight OK for day $Day."
    if (-not $Run) { Write-Host "Preflight only. Re-run with -Run to execute day $Day."; return }
    uv run --offline --frozen python -m app.cli eval-run @common --label $label --delay-s 6
    $code = $LASTEXITCODE
    Write-Host "`nDay $Day finished with exit code $code. Report: evaluation\reports\$label"
    if ($code -eq 1) { Write-Warning "day $Day is INCOMPLETE: the comparison can't be completed (registered rule); do not re-run it." }
    elseif ($code) { throw "eval-run refused or failed before completing (exit $code)" }
} finally {
    Pop-Location
    if ($null -eq $previousMock) { Remove-Item Env:\MOCK_PROVIDER_ENABLED -ErrorAction SilentlyContinue } else { $env:MOCK_PROVIDER_ENABLED = $previousMock }
    if ((Get-FileHash $envFile).Hash -ne $envHash) { Write-Error ".env CHANGED during the run" }
}
