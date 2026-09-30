$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "=== Raidat Biometric Middleware Setup ===" -ForegroundColor Cyan
$hasPy = $false
try { py -3 --version *> $null; if ($LASTEXITCODE -eq 0) { $hasPy = $true } } catch {}
if ($hasPy) { py -3 -m venv .venv } else { python -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\pip.exe" install -r requirements.txt
New-Item -ItemType Directory -Force -Path data | Out-Null
New-Item -ItemType Directory -Force -Path logs | Out-Null
if (-not (Test-Path "config.yaml")) { Copy-Item "config.example.yaml" "config.yaml" }
Write-Host "Installation completed." -ForegroundColor Green
$version = & ".\.venv\Scripts\python.exe" -m app.main --version
Write-Host "Installed version: $version" -ForegroundColor Cyan
