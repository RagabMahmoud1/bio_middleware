import logging
import time
from datetime import timedelta, timezone

from .base import DeviceAdapter

log = logging.getLogger(__name__)


class ZKTecoAdapter(DeviceAdapter):
    def __init__(self, cfg):
        super().__init__(cfg)

        # ZKTeco/pyzk returns naive datetimes. The device in this deployment
        # stores local Saudi time, so attach the configured offset before
        # sending the event to Odoo.
        offset = str(cfg.get("timezone_offset", "+03:00")).strip()
        sign = -1 if offset.startswith("-") else 1

        try:
            hh, mm = offset.lstrip("+-").split(":")
            self.tz = timezone(
                sign * timedelta(hours=int(hh), minutes=int(mm))
            )
        except Exception as exc:
            raise ValueError(
                f"Invalid timezone_offset for {self.device_id}: {offset}. "
                "Expected format like +03:00"
            ) from exc

    def _connect(self):
        from zk import ZK

        zk = ZK(
            self.cfg["ip"],
            port=int(self.cfg.get("port", 4370)),
            timeout=int(self.cfg.get("timeout_seconds", 10)),
            password=int(self.cfg.get("comm_key", 0)),
            force_udp=bool(self.cfg.get("force_udp", False)),
            ommit_ping=False,
        )
        return zk.connect()

    def test_connection(self):
        conn = None
        try:
            conn = self._connect()
            try:
                firmware = conn.get_firmware_version()
            except Exception:
                firmware = None

            return {
                "ok": True,
                "firmware": firmware,
                "timezone_offset": self.cfg.get(
                    "timezone_offset",
                    "+03:00",
                ),
            }
        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass

    def fetch_events(self):
        conn = None
        started = time.monotonic()

        try:
            conn = self._connect()

            log.info(
                "ZKTeco %s: requesting attendance history...",
                self.device_id,
            )

            rows = conn.get_attendance() or []

            log.info(
                "ZKTeco %s: device returned %s rows in %.1f sec",
                self.device_id,
                len(rows),
                time.monotonic() - started,
            )

            events = []

            for row in rows:
                ts = getattr(row, "timestamp", None)
                if not ts:
                    continue

                # pyzk returns a naive datetime for this device.
                # Treat it as device-local time and make it ISO-8601 aware.
                if ts.tzinfo is None:
                    ts_aware = ts.replace(tzinfo=self.tz)
                else:
                    ts_aware = ts

                user_id = (
                    getattr(row, "user_id", None)
                    or getattr(row, "uid", None)
                )

                status = getattr(row, "status", None)
                punch = getattr(row, "punch", None)

                # Preserve the existing interpretation for display only.
                # Final attendance processing remains Raw Events Only until
                # the customer's attendance rule is confirmed.
                if status in (0, "0"):
                    event_type = "check_in"
                elif status in (1, "1"):
                    event_type = "check_out"
                else:
                    event_type = "punch"

                events.append(
                    {
                        "device_id": self.device_id,
                        "device_type": "zkteco",
                        "employee_code": (
                            str(user_id)
                            if user_id is not None
                            else None
                        ),
                        "event_time": ts_aware.isoformat(
                            timespec="seconds"
                        ),
                        "event_type": event_type,
                        # Keep the production event identity backward
                        # compatible. This device/pyzk combination does not
                        # expose a guaranteed attendance-row identifier.
                        "source_event_id": None,
                        "raw": {
                            "uid": getattr(row, "uid", None),
                            "user_id": getattr(
                                row,
                                "user_id",
                                None,
                            ),
                            "status": status,
                            "punch": punch,
                            "timestamp": str(ts),
                            "timezone_offset": self.cfg.get(
                                "timezone_offset",
                                "+03:00",
                            ),
                        },
                    }
                )

            return events

        finally:
            if conn:
                try:
                    conn.disconnect()
                except Exception:
                    pass