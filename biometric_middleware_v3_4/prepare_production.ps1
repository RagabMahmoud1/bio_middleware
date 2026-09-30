param([Parameter(Mandatory=$true)][string]$GoLiveAt)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "=== Prepare Production Baseline ===" -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m app.production_init --go-live-at "$GoLiveAt"
if ($LASTEXITCODE -ne 0) { throw "Production preparation failed." }
Write-Host "Next: .\run_daily.ps1 -Force" -ForegroundColor Green
