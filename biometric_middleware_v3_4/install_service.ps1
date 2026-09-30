param(
    [string]$ServiceName = "RaidatBiometricConnector"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator."
}

$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$nssmCommand = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $nssmCommand) {
    $nssmCommand = Get-Command nssm -ErrorAction SilentlyContinue
}
if (-not $nssmCommand) {
    throw "NSSM is required. Install it first, for example: winget install NSSM.NSSM"
}
$nssm = $nssmCommand.Source

$oldTask = Get-ScheduledTask -TaskName "OdooBiometricDailySync" -ErrorAction SilentlyContinue
if ($oldTask) {
    Unregister-ScheduledTask -TaskName "OdooBiometricDailySync" -Confirm:$false
}

$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Status -ne "Stopped") {
        Stop-Service -Name $ServiceName -Force
    }
    & $nssm remove $ServiceName confirm | Out-Null
}

New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null
$stdoutLog = (Join-Path $PSScriptRoot "logs\service_stdout.log")
$stderrLog = (Join-Path $PSScriptRoot "logs\service_stderr.log")

& $nssm install $ServiceName $python "-m app.main" | Out-Null
& $nssm set $ServiceName AppDirectory $PSScriptRoot | Out-Null
& $nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
& $nssm set $ServiceName AppExit Default Restart | Out-Null
& $nssm set $ServiceName AppRestartDelay 5000 | Out-Null
& $nssm set $ServiceName AppStdout $stdoutLog | Out-Null
& $nssm set $ServiceName AppStderr $stderrLog | Out-Null
& $nssm set $ServiceName AppRotateFiles 1 | Out-Null
& $nssm set $ServiceName AppRotateOnline 1 | Out-Null
& $nssm set $ServiceName AppRotateBytes 10485760 | Out-Null

Start-Service -Name $ServiceName
Start-Sleep -Seconds 3

$service = Get-Service -Name $ServiceName
$service | Format-Table Name, Status, StartType

if ($service.Status -ne "Running") {
    throw "Service was installed but is not running. Check logs\service_stderr.log."
}

Write-Host "Raidat Biometric Connector installed with NSSM and started." -ForegroundColor Green
