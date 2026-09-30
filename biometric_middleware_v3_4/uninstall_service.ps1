param(
    [string]$ServiceName = "RaidatBiometricConnector"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator."
}

$nssmCommand = Get-Command nssm.exe -ErrorAction SilentlyContinue
if (-not $nssmCommand) {
    $nssmCommand = Get-Command nssm -ErrorAction SilentlyContinue
}
if (-not $nssmCommand) {
    throw "NSSM was not found in PATH."
}
$nssm = $nssmCommand.Source

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne "Stopped") {
    Stop-Service -Name $ServiceName -Force
}
if ($service) {
    & $nssm remove $ServiceName confirm | Out-Null
}
Write-Host "Raidat Biometric Connector removed." -ForegroundColor Green
