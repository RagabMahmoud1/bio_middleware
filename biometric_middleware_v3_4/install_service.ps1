$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$serviceName = "RaidatBiometricConnector"
$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$serviceScript = (Resolve-Path ".\app\windows_service.py").Path

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator."
}

$oldTask = Get-ScheduledTask -TaskName "OdooBiometricDailySync" -ErrorAction SilentlyContinue
if ($oldTask) {
    Unregister-ScheduledTask -TaskName "OdooBiometricDailySync" -Confirm:$false
}

$existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Status -ne "Stopped") { Stop-Service -Name $serviceName -Force }
    & $python $serviceScript remove
}

& $python $serviceScript --startup auto install
& sc.exe failure $serviceName reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null
& sc.exe failureflag $serviceName 1 | Out-Null
Start-Service -Name $serviceName
Start-Sleep -Seconds 2
Get-Service -Name $serviceName | Format-Table Name, Status, StartType
Write-Host "Raidat Biometric Connector installed and started." -ForegroundColor Green
