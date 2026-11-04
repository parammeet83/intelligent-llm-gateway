<#
.SYNOPSIS
  One-command local run for RouteWise AI: migrates the database, starts the API and the dashboard.

.EXAMPLE
  .\scripts\dev.ps1 -Setup     # first run: install deps, migrate, seed demo tenants
  .\scripts\dev.ps1            # later runs: migrate and start

  API:       http://localhost:8000/api/v1/health   (docs at /docs)
  Dashboard: http://localhost:5173
  Press Ctrl+C to stop both.
#>
param(
    [switch]$Setup
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

foreach ($tool in "uv", "npm") {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool is not installed or not on PATH."
    }
}

if (-not (Test-Path (Join-Path $root ".env"))) {
    Write-Warning "No .env found. Using a local SQLite database (backend\routewise-dev.db). Copy .env.example to .env to use Neon."
}

Push-Location $backend
try {
    if ($Setup -or -not (Test-Path ".venv")) { uv sync; if ($LASTEXITCODE) { throw "uv sync failed" } }
    uv run alembic upgrade head
    if ($LASTEXITCODE) { throw "database migration failed" }
    if ($Setup) {
        uv run python -m app.cli seed
        if ($LASTEXITCODE) { throw "seed failed" }
    }
} finally {
    Pop-Location
}

if ($Setup -or -not (Test-Path (Join-Path $frontend "node_modules"))) {
    Push-Location $frontend
    try { npm ci; if ($LASTEXITCODE) { throw "npm ci failed" } } finally { Pop-Location }
}

$api = Start-Process -FilePath "uv" -WorkingDirectory $backend -NoNewWindow -PassThru `
    -ArgumentList "run", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000", "--reload"

try {
    Push-Location $frontend
    npm run dev
} finally {
    Pop-Location
    if ($api -and -not $api.HasExited) {
        # uv spawns uvicorn as a child; stop the whole tree.
        taskkill /PID $api.Id /T /F | Out-Null
    }
}
