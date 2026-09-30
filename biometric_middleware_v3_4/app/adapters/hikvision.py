import logging
import uuid
from datetime import datetime, timedelta, timezone

import requests
from requests.auth import HTTPDigestAuth

from .base import DeviceAdapter

_logger = logging.getLogger(__name__)


class HikvisionAdapter(DeviceAdapter):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.base = f"{cfg.get('scheme', 'http')}://{cfg['ip']}:{int(cfg.get('port', 80))}"
        self.timeout = int(cfg.get("timeout_seconds", 15))
        self.verify = bool(cfg.get("verify_ssl", False))

        self.username = cfg["username"]
        self.password = cfg["password"]

        self.event_endpoint = cfg.get(
            "event_endpoint",
            "/ISAPI/AccessControl/AcsEvent?format=json",
        )
        self.event_major = int(cfg.get("event_major", 5))
        self.max_results = max(1, min(int(cfg.get("max_results", 200)), 200))
        self.only_employee_events = bool(cfg.get("only_employee_events", True))

        offset = str(cfg.get("timezone_offset", "+03:00")).strip()
        sign = -1 if offset.startswith("-") else 1
        hh, mm = offset.lstrip("+-").split(":")
        self.tz = timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))

    def _auth(self):
        # IMPORTANT:
        # Use a fresh Digest auth object per request.
        #
        # This Hikvision firmware challenges each protected request with its
        # own nonce. Reusing the same HTTPDigestAuth object after a previous
        # authenticated GET can lead to badAuthorization on a following POST.
        # curl --digest works because it performs a fresh 401 challenge/retry
        # for the POST request. We mirror that behavior here.
        return HTTPDigestAuth(self.username, self.password)

    def _get(self, path):
        return requests.get(
            self.base + path,
            auth=self._auth(),
            headers={
                "Accept": "application/json",
                "User-Agent": "OdooBiometricMiddleware/2.2",
            },
            timeout=self.timeout,
            verify=self.verify,
        )

    def _post(self, path, body):
        return requests.post(
            self.base + path,
            json=body,
            auth=self._auth(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "OdooBiometricMiddleware/2.2",
            },
            timeout=self.timeout,
            verify=self.verify,
        )

    def test_connection(self):
        r = self._get("/ISAPI/System/deviceInfo")
        r.raise_for_status()
        return {"ok": True, "http_status": r.status_code}

    @staticmethod
    def _event_employee(item):
        return (
            item.get("employeeNoString")
            or item.get("employeeNo")
            or item.get("cardNo")
            or item.get("personNo")
        )

    def _normalize_event(self, item):
        employee = self._event_employee(item)
        if self.only_employee_events and employee is None:
            # Ignore door/alarm/internal events that are not tied to a person.
            return None

        event_time = (
            item.get("time")
            or item.get("dateTime")
            or item.get("eventTime")
        )
        if not event_time:
            return None

        event_type = (
            item.get("attendanceStatus")
            or item.get("currentVerifyMode")
            or "punch"
        )

        source_id = (
            item.get("serialNo")
            or item.get("eventID")
            or item.get("eventId")
        )

        return {
            "device_id": self.device_id,
            "device_type": "hikvision",
            "employee_code": str(employee) if employee is not None else None,
            "event_time": str(event_time),
            "event_type": str(event_type),
            "source_event_id": str(source_id) if source_id is not None else None,
            "raw": item,
        }

    def _as_device_time(self, value):
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(
                str(value).strip().replace("Z", "+00:00")
            )

        if dt.tzinfo is None:
            return dt.replace(tzinfo=self.tz)
        return dt.astimezone(self.tz)

    def fetch_events(self, start_time=None, end_time=None):
        end = self._as_device_time(end_time) or datetime.now(self.tz)
        start = self._as_device_time(start_time)
        if start is None:
            # Backward-compatible fallback. Production code should provide
            # an explicit cursor-based start_time.
            start = end - timedelta(
                minutes=int(self.cfg.get("lookback_minutes", 180))
            )

        if start > end:
            raise ValueError("Hikvision fetch start_time is after end_time")

        self.last_query_start = start.isoformat(timespec="seconds")
        self.last_query_end = end.isoformat(timespec="seconds")
        _logger.info(
            "Hikvision %s: fetch window start=%s end=%s",
            self.device_id,
            self.last_query_start,
            self.last_query_end,
        )

        search_id = f"odoo-{uuid.uuid4().hex[:16]}"
        position = 0
        all_events = []
        total_matches = None

        while True:
            body = {
                "AcsEventCond": {
                    "searchID": search_id,
                    "searchResultPosition": position,
                    "maxResults": self.max_results,
                    "major": self.event_major,
                    "minor": 0,
                    "startTime": start.isoformat(timespec="seconds"),
                    "endTime": end.isoformat(timespec="seconds"),
                }
            }

            r = self._post(self.event_endpoint, body)

            if r.status_code >= 400:
                _logger.error(
                    "Hikvision event search failed: HTTP %s body=%s",
                    r.status_code,
                    r.text[:4000],
                )
            r.raise_for_status()

            data = r.json()
            info = data.get("AcsEvent", data)
            items = info.get("InfoList") or info.get("infoList") or []
            if isinstance(items, dict):
                items = [items]

            if total_matches is None:
                try:
                    total_matches = int(info.get("totalMatches", len(items)))
                except Exception:
                    total_matches = len(items)

                _logger.info(
                    "Hikvision %s: total matches reported by device=%s",
                    self.device_id,
                    total_matches,
                )

            page_employee_count = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                ev = self._normalize_event(item)
                if ev:
                    all_events.append(ev)
                    page_employee_count += 1

            raw_count = len(items)
            _logger.info(
                "Hikvision %s: position=%s raw=%s employee_events=%s status=%s",
                self.device_id,
                position,
                raw_count,
                page_employee_count,
                info.get("responseStatusStrg"),
            )

            if raw_count == 0:
                break

            position += raw_count
            status = str(info.get("responseStatusStrg", "")).upper()

            if status != "MORE":
                break
            if total_matches is not None and position >= total_matches:
                break
            if position > 300000:
                raise RuntimeError("Hikvision pagination exceeded safety limit")

        _logger.info(
            "Hikvision %s: normalized employee events=%s",
            self.device_id,
            len(all_events),
        )
        return all_events