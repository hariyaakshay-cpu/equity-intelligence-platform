# Live intraday PAPER board (NOT VALIDATED, no orders): refresh daily prices, then run the board until 15:31 IST.
#   .\start_paper_board.ps1            normal run (what the scheduled task starts at 08:40 on weekdays)
# Needs a fresh Upstox token each morning (python scripts\upstox_auth.py) - without it the refresh fails and
# the board runs without live quotes; fade trades are then re-marked from official prices the next morning.
# Log: logs\paper_board_<date>.log    Board: http://127.0.0.1:5050/equity (top section)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$env:PYTHONUNBUFFERED = "1"   # write log lines as they happen, not at exit
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "logs") | Out-Null
$log = Join-Path $PSScriptRoot ("logs\paper_board_" + (Get-Date -Format "yyyy-MM-dd") + ".log")
"=== $(Get-Date -Format s) daily price refresh" | Out-File $log -Append -Encoding utf8
& $py scripts\equity_daily_history_fetch.py --start 2025-06-01 --out-dir data\daily_live --refresh 2>&1 | Out-File $log -Append -Encoding utf8
"=== $(Get-Date -Format s) paper board (exit code of refresh: $LASTEXITCODE)" | Out-File $log -Append -Encoding utf8
& $py scripts\equity_paper_board.py 2>&1 | Out-File $log -Append -Encoding utf8
"=== $(Get-Date -Format s) done (exit code $LASTEXITCODE)" | Out-File $log -Append -Encoding utf8
