# Phase 1 - Daily Biometric Integration

Phase 1 imports biometric events from the production Go-Live cutoff forward only. Historical events before that cutoff are intentionally excluded for a separate Phase 2 quotation/migration.

## Activate production baseline

```powershell
.\prepare_production.ps1 -GoLiveAt "2026-08-29 00:00:00"
```

This archives the current test SQLite DB, clears the daily-success marker, and stores the cutoff in config. On the first production run the same cutoff is persisted inside SQLite, so normal daily runs cannot silently move backwards into historical data.

Then run:

```powershell
.\run_daily.ps1 -Force
.\show_status.ps1
.\show_production_state.ps1
```

After Odoo API is configured and verified, install the scheduled task:

```powershell
.\install_daily_task.ps1 -PrimaryTime "04:00" -RetryTime1 "05:00" -RetryTime2 "06:00"
```

Retries are conditional; after the first successful run of the day later retry triggers exit without reading the devices again.
