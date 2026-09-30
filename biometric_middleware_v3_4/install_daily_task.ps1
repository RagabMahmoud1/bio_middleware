param(
    [string]$PrimaryTime = "04:00",
    [string]$RetryTime1 = "05:00",
    [string]$RetryTime2 = "06:00"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$taskName = "OdooBiometricDailySync"
$scriptPath = (Resolve-Path ".\run_daily.ps1").Path
$powershell = (Get-Command powershell.exe).Source

$action = New-ScheduledTaskAction `
    -Execute $powershell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$t1 = New-ScheduledTaskTrigger -Daily -At $PrimaryTime
$t2 = New-ScheduledTaskTrigger -Daily -At $RetryTime1
$t3 = New-ScheduledTaskTrigger -Daily -At $RetryTime2

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($t1, $t2, $t3) `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Scheduled task installed: $taskName" -ForegroundColor Green
Write-Host "Triggers: $PrimaryTime, $RetryTime1, $RetryTime2"
Write-Host "Deduplication makes retry runs safe."
