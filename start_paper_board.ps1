# Live intraday PAPER board (NOT VALIDATED, no orders): refresh daily prices, then run the board until 15:31 IST.
#   .\start_paper_board.ps1            normal run (what the scheduled task starts at 08:40 on weekdays)
# Live quotes use UPSTOX_ANALYTICS_TOKEN from .env (read-only, valid one year; no daily login). The price update
# needs no token. Without a token the board runs without live quotes; fade trades are re-marked next morning.
# Log: logs\paper_board_<date>.log    Board: http://127.0.0.1:5050/equity (top section)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$env:PYTHONUNBUFFERED = "1"   # write log lines as they happen, not at exit
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "logs") | Out-Null
$log = Join-Path $PSScriptRoot ("logs\paper_board_" + (Get-Date -Format "yyyy-MM-dd") + ".log")
"=== $(Get-Date -Format s) daily price update (incremental)" | Out-File $log -Append -Encoding utf8
& $py scripts\equity_daily_live_update.py 2>&1 | Out-File $log -Append -Encoding utf8
"=== $(Get-Date -Format s) paper board (exit code of update: $LASTEXITCODE)" | Out-File $log -Append -Encoding utf8
& $py scripts\equity_paper_board.py 2>&1 | Out-File $log -Append -Encoding utf8
"=== $(Get-Date -Format s) done (exit code $LASTEXITCODE)" | Out-File $log -Append -Encoding utf8
