# Congress Trades - Windows Task Scheduler Setup
# Run this script as Administrator to set up daily sync
#
# Usage:
#   Right-click PowerShell -> Run as Administrator
#   cd C:\path\to\CongressTrades
#   .\scripts\setup_task.ps1

param(
    [string]$Time = "07:00",  # Default: 7 AM
    [switch]$Remove           # Remove the scheduled task
)

$TaskName = "CongressTradesSync"
$Description = "Daily sync of congressional stock trades with push notifications"

# Get the script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$BatchScript = Join-Path $ProjectDir "scripts\sync_trades.bat"

if ($Remove) {
    Write-Host "Removing scheduled task '$TaskName'..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Task removed."
    exit 0
}

Write-Host "Setting up Congress Trades daily sync..."
Write-Host "  Project directory: $ProjectDir"
Write-Host "  Scheduled time: $Time"
Write-Host ""

# Check if batch script exists
if (-not (Test-Path $BatchScript)) {
    Write-Host "ERROR: Batch script not found at $BatchScript" -ForegroundColor Red
    exit 1
}

# Remove existing task if it exists
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Create the action
$Action = New-ScheduledTaskAction -Execute $BatchScript -WorkingDirectory $ProjectDir

# Create the trigger (daily at specified time)
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time

# Create settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -WakeToRun:$false

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description $Description `
        -RunLevel Limited | Out-Null

    Write-Host ""
    Write-Host "SUCCESS: Scheduled task created!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The sync will run daily at $Time"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  - View task: Open Task Scheduler and look for '$TaskName'"
    Write-Host "  - Run now: schtasks /run /tn `"$TaskName`""
    Write-Host "  - Change time: .\scripts\setup_task.ps1 -Time `"08:30`""
    Write-Host "  - Remove task: .\scripts\setup_task.ps1 -Remove"
    Write-Host ""
    Write-Host "NOTE: If your laptop is asleep at $Time, the task will run"
    Write-Host "      when it next wakes up (StartWhenAvailable is enabled)."
}
catch {
    Write-Host "ERROR: Failed to create scheduled task" -ForegroundColor Red
    Write-Host $_.Exception.Message
    Write-Host ""
    Write-Host "Try running PowerShell as Administrator."
    exit 1
}
