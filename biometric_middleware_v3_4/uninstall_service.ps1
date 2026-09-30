$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$serviceName = "RaidatBiometricConnector"
$python = (Resolve-Path ".\.venv\Scripts\python.exe").Path
$serviceScript = (Resolve-Path ".\app\windows_service.py").Path
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne "Stopped") { Stop-Service -Name $serviceName -Force }
if ($service) { & $python $serviceScript remove }
Write-Host "Raidat Biometric Connector removed." -ForegroundColor Green
