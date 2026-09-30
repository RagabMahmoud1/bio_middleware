$serviceName = "RaidatBiometricConnector"
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Host "Service is not installed." -ForegroundColor Yellow
    exit 2
}
$service | Format-Table Name, Status, StartType
Write-Host ""
Write-Host "Middleware Version:"
& ".\.venv\Scripts\python.exe" -m app.main --version
Write-Host ""
& ".\.venv\Scripts\python.exe" -m app.main --status