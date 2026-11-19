# Equity signals dashboard: one-step start.
#   .\start_equity_dashboard.ps1            refresh data, build today's list, start dashboard
#   .\start_equity_dashboard.ps1 -NoRefresh  just start the dashboard with the last list
# Needs a valid Upstox token for the refresh (run: python scripts\upstox_auth.py once each morning).
param([switch]$NoRefresh)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not $NoRefresh) {
    Write-Host "1/3 Updating daily prices (only new days, a few minutes)..."
    & $py scripts\equity_daily_live_update.py
    if ($LASTEXITCODE -ne 0) { Write-Host "Refresh failed - is the Upstox token fresh? Starting dashboard with the last list."; }
    else {
        Write-Host "2/3 Building today's momentum list..."
        & $py scripts\equity_momentum_signals.py
    }
}
Write-Host "3/3 Starting dashboard - open http://127.0.0.1:5050/equity/signals  (Ctrl+C to stop)"
Start-Job { Start-Sleep 4; Start-Process "http://127.0.0.1:5050/equity/signals" } | Out-Null
& $py -m dashboard.app
