# Raidat Biometric Middleware 3.5.0 - Local Release Validation

Validation date: 2026-09-29

## Automated results
- Middleware unit/recovery/release tests: 35/35 passed
- Attendance date/finalization logic tests: 4/4 passed
- Total automated tests: 39/39 passed
- Python compileall: passed
- Odoo Python py_compile: passed
- Odoo XML well-formed validation: passed
- YAML config validation: passed
- Odoo git diff --check: passed

## Recovery cases covered locally
- Odoo/network failure keeps queue pending for retry.
- Explicit rejected event is isolated and does not block later events.
- Pending queue survives SQLite close/reopen.
- Missing employee mapping filters all disallowed events.
- Device connection failure is recorded without destroying queue data.
- Heartbeat failure is non-destructive.
- Hikvision cursor recovers from a two-day downtime window with overlap.
- Duplicate/backfill inserts remain idempotent.
- Partial ACK leaves only unacknowledged rows pending.
- Device-specific polling prevents aggressive ZKTeco full-history scans.

## Attendance safeguards covered
- Local-day UTC boundaries for Asia/Riyadh.
- Current local day is not finalized.
- Previous local day can be finalized.
- First/last processing is employee-day based across first_last devices.
- Single-punch day does not create final attendance.
- Existing manual/non-biometric attendance is not overwritten by the automatic path.
- Late biometric punches can recompute an attendance already linked to biometric events.

## Environment limitations
The development host does not currently have an Odoo 16 container matching this project,
and it does not have the customer's physical Hikvision/ZKTeco devices or Windows Service
Control Manager. Therefore the following cannot be truthfully marked as physically executed:
- Odoo 16 module upgrade against the customer's exact database.
- Real device API/network behavior against the customer's hardware.
- Actual Windows Service registration/reboot/recovery on the customer's PC.

These items remain deployment-environment smoke checks, not known code failures.
