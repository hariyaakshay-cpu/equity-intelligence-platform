<#
Registers a Windows Task Scheduler job that refreshes the data and sends the Telegram digest on
weekdays at 18:30 (this PC's clock must be IST; the scanner treats a session
as closed at 18:00 IST). Holidays are skipped by the script itself.

Run from the repository root you want scheduled (the task stores this path):
    powershell -ExecutionPolicy Bypass -File scripts\register_telegram_task.ps1
Remove with:  Unregister-ScheduledTask -TaskName EquityTelegramDigest -Confirm:$false
#>
$root = (Get-Location).Path
if (-not (Test-Path (Join-Path $root "scripts\telegram_digest.py"))) { throw "Run from the repository root." }
$python = (Get-Command python).Source
$action = New-ScheduledTaskAction -Execute $python `
    -Argument "scripts\telegram_digest.py --send --only-on-session" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 18:30
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName "EquityTelegramDigest" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Daily equity_intel data refresh and Telegram digest (research only)" -Force
