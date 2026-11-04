<#
.SYNOPSIS
  Pool the four v5.2.3 day reports into the registered analysis (offline; no provider call).

.DESCRIPTION
  Needs all four reports (evaluation\reports\v5.2.3-day1 .. -day4). eval-combine itself refuses a
  missing or duplicate day, another registration, other cases, or dates out of order, and marks the
  comparison incomplete (never publishable) if any day was incomplete or the span exceeds 14 days.

.EXAMPLE
  .\scripts\benchmark-combine.ps1
#>
param([string]$Label = "v5.2.3-combined")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$reports = Join-Path $root "evaluation\reports"
$days = 1..4 | ForEach-Object { Join-Path $reports "v5.2.3-day$_" }
$missing = $days | Where-Object { -not (Test-Path (Join-Path $_ "summary.json")) }
if ($missing) { throw "missing day reports: $($missing -join ', ')" }
if (Test-Path (Join-Path $reports $Label)) { throw "$Label already exists" }

Push-Location (Join-Path $root "backend")
try {
    uv run --offline --frozen python -m app.cli eval-combine --dataset routewise_bench_v5 `
        --revision routewise_bench_v5.2.3 --label $Label --reports @days
    Write-Host "Combined report: evaluation\reports\$Label (exit $LASTEXITCODE; 0 = complete)"
} finally { Pop-Location }
