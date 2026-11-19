# One-time: register the weekday 08:40 task "Equity Paper Board" (runs start_paper_board.ps1 as you, when logged on).
#   .\register_paper_board_task.ps1          create or replace the task
#   Unregister-ScheduledTask -TaskName "Equity Paper Board"      remove it
$script = Join-Path $PSScriptRoot "start_paper_board.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $PSScriptRoot `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "08:40"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 8) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "Equity Paper Board" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Live intraday PAPER board (not validated, no orders). Equity - intraday repo." -Force | Out-Null
Get-ScheduledTask -TaskName "Equity Paper Board" | Select-Object TaskName, State, @{n="Next run"; e={(Get-ScheduledTaskInfo $_).NextRunTime}}
