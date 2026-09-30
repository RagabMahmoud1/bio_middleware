param([Parameter(Mandatory=$true)][string]$DeviceId)
Set-Location $PSScriptRoot
& ".\.venv\Scripts\python.exe" -m app.main --test-device $DeviceId
