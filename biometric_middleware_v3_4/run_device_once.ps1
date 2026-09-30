param(
  [Parameter(Mandatory=$true)][string]$DeviceId,
  [Parameter(Mandatory=$false)][string]$FromDate
)
Set-Location $PSScriptRoot
if ($FromDate) {
  & ".\.venv\Scripts\python.exe" -m app.main --once --device $DeviceId --from-date "$FromDate"
} else {
  & ".\.venv\Scripts\python.exe" -m app.main --once --device $DeviceId
}
