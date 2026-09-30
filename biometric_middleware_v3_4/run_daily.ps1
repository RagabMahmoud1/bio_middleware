param(
    [switch]$Force
)

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

New-Item -ItemType Directory -Force -Path ".\data" | Out-Null
$marker = ".\data\last_daily_success.txt"
$today = Get-Date -Format "yyyy-MM-dd"

if ((-not $Force) -and (Test-Path $marker)) {
    $last = (Get-Content $marker -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
    if ($last -eq $today) {
        Write-Host "Daily biometric sync already succeeded today ($today). Skipping retry trigger." -ForegroundColor Green
        exit 0
    }
}

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "=== Daily biometric sync started: $stamp ===" -ForegroundColor Cyan

& ".\.venv\Scripts\python.exe" -m app.main --once
$code = $LASTEXITCODE

if ($code -eq 0) {
    Set-Content -Path $marker -Value $today -Encoding ascii
    Write-Host "=== Daily biometric sync completed successfully ===" -ForegroundColor Green
    exit 0
}

Write-Host "Daily biometric sync failed with exit code $code. A later scheduled retry may run." -ForegroundColor Yellow
exit $code
