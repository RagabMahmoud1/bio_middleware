$ErrorActionPreference = "SilentlyContinue"
Unregister-ScheduledTask -TaskName "OdooBiometricDailySync" -Confirm:$false
Write-Host "Scheduled task removed."
