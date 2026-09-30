param([string]$Destination = ".\\backup")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $Destination $stamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
if (Test-Path ".\config.yaml") { Copy-Item ".\config.yaml" (Join-Path $backupDir "config.yaml") -Force }
if (Test-Path ".\data") { Copy-Item ".\data" (Join-Path $backupDir "data") -Recurse -Force }
$version = & ".\.venv\Scripts\python.exe" -m app.main --version
Set-Content -Path (Join-Path $backupDir "version.txt") -Value $version -Encoding ascii
Write-Host "Backup created: $backupDir" -ForegroundColor Green
