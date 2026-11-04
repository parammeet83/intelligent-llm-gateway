<#
.SYNOPSIS
  Run ONE registered day of the routewise_bench_v5.2.3 four-day schedule, safely.

.DESCRIPTION
  - Runs only the day you name. It never starts another day.
  - Reads that day's registered requirement from the hash-pinned schedule (via the app's own loader).
  - Takes the fresh remaining daily tokens of BOTH Groq models as read in the console today, uses
    the smaller one (the registered rule), and refuses if it is below the day's requirement.
  - Refuses a day that already has a report, a day whose earlier day hasn't run, a second day on
    the same UTC date, a schedule span over 14 days, or a start later than 22:00 UTC.
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
    [switch]$Run
)

$ErrorActionPreference = "Stop"
$Revision = "routewise_bench_v5.2.3"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$reports = Join-Path $root "evaluation\reports"
$label = "v5.2.3-day$Day"
$envFile = Join-Path $root ".env"

# --- verified time: an ISO 8601 instant with an offset, today (UTC), not in the future ---------------
try { $verified = [DateTimeOffset]::Parse($VerifiedAt, [Globalization.CultureInfo]::InvariantCulture) } catch {
    throw "-VerifiedAt must be ISO 8601 with a UTC offset, e.g. 2026-11-05T08:10:00+00:00" }
if ($VerifiedAt -notmatch '(Z|[+-]\d\d:\d\d)$') { throw "-VerifiedAt must include a UTC offset" }
$now = [DateTimeOffset]::UtcNow
if ($verified -gt $now.AddMinutes(1)) { throw "-VerifiedAt is in the future" }
if ($verified.UtcDateTime.Date -ne $now.UtcDateTime.Date) { throw "the quota must be read today (UTC date $($now.UtcDateTime.ToString('yyyy-MM-dd')))" }
if ($now.UtcDateTime.TimeOfDay -gt [TimeSpan]::FromHours(22)) { throw "too late: a day must start at least 2 hours before 00:00 UTC" }

# --- registered requirement and earlier days (read through the app's own verified loaders) -----------
$probe = @'
import json, sys
from pathlib import Path
from app.evaluation.dataset import load_dataset, load_execution_revision, load_preregistration, load_execution_schedule
import yaml
day, reports = int(sys.argv[1]), Path(sys.argv[2])
v5 = load_dataset("routewise_bench_v5")
path, pinned = load_execution_revision("routewise_bench_v5.2.3", v5)
prereg, sha = load_preregistration(path, dataset=v5, pinned_sha256=pinned)
schedule = load_execution_schedule(v5, prereg)
raw = yaml.safe_load((path.parent / schedule["file"]).read_text(encoding="utf-8"))
done = {}
for summary in reports.glob("*/summary.json"):
    s = json.loads(summary.read_text(encoding="utf-8"))
    info = s.get("execution_schedule") or {}
    if s.get("execution_revision") == "routewise_bench_v5.2.3" and info.get("day") is not None:
        done.setdefault(int(info["day"]), []).append({"dir": summary.parent.name, "utc_date": info.get("utc_date"),
                                                      "incomplete": bool(s.get("incomplete")), "simulated": bool(s.get("simulated"))})
print(json.dumps({"required": raw["day_worst_case"][day]["required_remaining_daily_tokens"],
                  "worst_case": raw["day_worst_case"][day]["worst_case_tokens"],
                  "cases": schedule["days"][day], "max_span_days": schedule["max_span_days"],
                  "schedule_sha256": schedule["sha256"], "done": done}))
'@
Push-Location $backend
try {
    $info = ($probe | uv run --offline --frozen python - $Day $reports) | ConvertFrom-Json
    if ($LASTEXITCODE) { throw "could not read the registered schedule" }
} finally { Pop-Location }

$done = @{}; foreach ($p in $info.done.PSObject.Properties) { $done[[int]$p.Name] = $p.Value }
if ($done.ContainsKey($Day)) { throw "day $Day already has a report ($($done[$Day].dir)): each day runs exactly once" }
if (Test-Path (Join-Path $reports $label)) { throw "report directory $label already exists: each day runs exactly once" }
for ($d = 1; $d -lt $Day; $d++) { if (-not $done.ContainsKey($d)) { throw "day $d has not run yet: days run in order" } }
$today = $now.UtcDateTime.ToString("yyyy-MM-dd")
foreach ($d in $done.Keys) {
    if ($done[$d].utc_date -eq $today) { throw "day $d already ran on $today (UTC): each day needs its own UTC date" }
}
if ($done.ContainsKey(1)) {
    $span = ([datetime]$today - [datetime]$done[1].utc_date).Days
    if ($span -gt $info.max_span_days) { throw "day 1 ran $span days ago; the registered span is $($info.max_span_days) days" }
}

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
