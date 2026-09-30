# Raidat Biometric Middleware 3.5.0

## Stable deployment path
Use C:\RaidatBiometric as the active runtime path.

## Preserve these runtime items during upgrades
- config.yaml
- data\middleware.db
- logs\

## Recommended upgrade flow
1. Back up config.yaml and the data directory.
2. Copy the new application files to C:\RaidatBiometric.
3. Keep the existing config.yaml and data directory.
4. Run install.ps1 if dependencies need updating.
5. Run install_service.ps1 as Administrator.
6. Run service_status.ps1.
7. Confirm Odoo Device Health shows Middleware Version 3.5.0 and a fresh heartbeat.

## Rollback
Restore the previous application files together with the backed-up config.yaml and data directory, then reinstall/start the Windows Service.

## Release scope
- Allowed Employee Mapping per Odoo database and device.
- Hikvision cursor + overlap recovery.
- Device + External User ID mapping safety.
- Per-event ACK and rejected-event isolation.
- Idempotent queue behavior.
- Safer First In / Last Out attendance finalization.
- Middleware heartbeat and health monitoring.
- Windows Service operation with per-device polling.
