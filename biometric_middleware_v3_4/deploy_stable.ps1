param([string]$Target = "C:\\RaidatBiometric")
$ErrorActionPreference = "Stop"
$source = (Resolve-Path $PSScriptRoot).Path
$targetFull = [System.IO.Path]::GetFullPath($Target)
New-Item -ItemType Directory -Force -Path $targetFull | Out-Null

$sourceConfig = Join-Path $source "config.yaml"
$targetConfig = Join-Path $targetFull "config.yaml"
if ((-not (Test-Path $targetConfig)) -and (Test-Path $sourceConfig)) {
    Copy-Item $sourceConfig $targetConfig -Force
}

$sourceData = Join-Path $source "data"
$targetData = Join-Path $targetFull "data"
if ((-not (Test-Path $targetData)) -and (Test-Path $sourceData)) {
    Copy-Item $sourceData $targetData -Recurse -Force
}

$preserve = @("config.yaml", "data", "logs", ".venv", "backup")
if ($source -ne $targetFull) {
    Get-ChildItem -Path $source -Force | ForEach-Object {
        if ($preserve -contains $_.Name) { return }
        $destination = Join-Path $targetFull $_.Name
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $destination | Out-Null
            Get-ChildItem -Path $_.FullName -Force | ForEach-Object {
                Copy-Item $_.FullName $destination -Recurse -Force
            }
        } else {
            Copy-Item $_.FullName $destination -Force
        }
    }
}
Set-Location $targetFull
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    & ".\install.ps1"
} else {
    & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
    New-Item -ItemType Directory -Force -Path ".\data" | Out-Null
    New-Item -ItemType Directory -Force -Path ".\logs" | Out-Null
    if (-not (Test-Path ".\config.yaml")) { Copy-Item ".\config.example.yaml" ".\config.yaml" }
}
$version = & ".\.venv\Scripts\python.exe" -m app.main --version
Write-Host "Installed middleware version: $version" -ForegroundColor Cyan
Write-Host "Stable runtime path: $targetFull" -ForegroundColor Green
Write-Host "config.yaml, data, logs and .venv are preserved on upgrades." -ForegroundColor Green