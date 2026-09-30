# Odoo Biometric Middleware v3

## Architecture

One Windows PC reads both local devices:

- ZKTeco MB1000: 10.0.2.210:4370
- Hikvision DS-K1T502DBFWX-C: 10.0.2.211:80

Attendance events are stored first in local SQLite, deduplicated, then pushed
to Odoo through HTTPS.

## Daily batch mode

Recommended mode for this customer: one daily batch sync plus two safe
retry triggers.

Default:
- 04:00
- 05:00 retry
- 06:00 retry

Install Windows Scheduled Task as Administrator:

```powershell
.\install_daily_task.ps1
```

Custom times:

```powershell
.\install_daily_task.ps1 -PrimaryTime "22:30" -RetryTime1 "23:30" -RetryTime2 "06:00"
```

Because every event has a unique key, retry runs do not create duplicates.

## Odoo

Before enabling Odoo, install the companion module
`asg_biometric_attendance_bridge`.

Then create the two devices in Odoo with External IDs exactly:

- `zk_room_1`
- `hik_room_2`

Create employee mappings for each device.

In Odoo Settings > Technical > System Parameters create:

- Key: `asg_biometric.api_token`
- Value: a long random secret

Then configure `config.yaml`:

```yaml
odoo:
  enabled: true
  base_url: "https://YOUR-ODOO-DOMAIN"
  endpoint: "/biometric/api/v1/events"
  api_token: "THE_SAME_SECRET"
  verify_ssl: true
```

## Important

The Odoo module stores raw events first. It can process them into
`hr.attendance` using the selected processing strategy on each device.


Retry triggers are conditional: after the first successful sync of the day, later retry triggers exit immediately without reading the devices again.
