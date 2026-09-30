import json
import requests


class OdooClient:
    def __init__(self, cfg):
        self.cfg = cfg

    @property
    def enabled(self):
        return bool(self.cfg.get("enabled"))

    def _headers(self):
        token = self.cfg.get("api_token", "")
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "OdooBiometricMiddleware/3.4",
        }

    def _url(self, endpoint):
        return (
            self.cfg["base_url"].rstrip("/")
            + "/"
            + endpoint.lstrip("/")
        )

    def get_allowed_employee_ids(self, device_id):
        """Return the active external user IDs mapped in this Odoo database.

        This call is fail-closed by design: if Odoo cannot provide the mapping
        list, the caller must not collect/store biometric events for the device.
        """
        if not self.enabled:
            return None

        endpoint = self.cfg.get(
            "allowed_employees_endpoint",
            "/biometric/api/v1/allowed-employees",
        )
        resp = requests.get(
            self._url(endpoint),
            params={"device_id": str(device_id)},
            headers=self._headers(),
            timeout=int(self.cfg.get("timeout_seconds", 20)),
            verify=bool(self.cfg.get("verify_ssl", True)),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(
                "Odoo allowed employee lookup failed: "
                + json.dumps(data, ensure_ascii=False)
            )

        raw_ids = data.get("allowed_employee_ids")
        if not isinstance(raw_ids, list):
            raise RuntimeError("Odoo returned invalid allowed_employee_ids")

        return sorted({
            str(value).strip()
            for value in raw_ids
            if value is not None and str(value).strip()
        })

    def heartbeat(self, payload):
        if not self.enabled:
            return None

        endpoint = self.cfg.get(
            "heartbeat_endpoint",
            "/biometric/api/v1/heartbeat",
        )
        resp = requests.post(
            self._url(endpoint),
            json=payload,
            headers=self._headers(),
            timeout=int(self.cfg.get("timeout_seconds", 20)),
            verify=bool(self.cfg.get("verify_ssl", True)),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(
                "Odoo heartbeat failed: "
                + json.dumps(data, ensure_ascii=False)
            )
        return data

    def send(self, rows):
        if not self.enabled or not rows:
            return []

        url = self._url(self.cfg["endpoint"])

        payload = {
            "events": [
                {
                    "event_key": r["event_key"],
                    "device_id": r["device_id"],
                    "device_type": r["device_type"],
                    "employee_code": r["employee_code"],
                    "event_time": r["event_time"],
                    "event_type": r["event_type"],
                    "raw": json.loads(r["raw_json"] or "{}"),
                }
                for r in rows
            ]
        }

        resp = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=int(self.cfg.get("timeout_seconds", 20)),
            verify=bool(self.cfg.get("verify_ssl", True)),
        )
        resp.raise_for_status()
        data = resp.json()

        accepted_keys = set(data.get("accepted_event_keys") or [])
        ignored_keys = set(data.get("ignored_event_keys") or [])
        rejected = data.get("rejected") or []

        accepted_ids = [
            r["id"]
            for r in rows
            if r["event_key"] in accepted_keys
        ]
        ignored_ids = [
            r["id"]
            for r in rows
            if r["event_key"] in ignored_keys
        ]

        rejected_by_key = {
            str(item.get("event_key") or ""): str(item.get("error") or "rejected")
            for item in rejected
            if isinstance(item, dict) and item.get("event_key")
        }
        rejected_items = [
            {
                "id": r["id"],
                "event_key": r["event_key"],
                "error": rejected_by_key[r["event_key"]],
            }
            for r in rows
            if r["event_key"] in rejected_by_key
        ]

        handled_ids = set(accepted_ids) | set(ignored_ids) | {
            item["id"] for item in rejected_items
        }
        unhandled_ids = [
            r["id"] for r in rows if r["id"] not in handled_ids
        ]

        return {
            "accepted_ids": accepted_ids,
            "ignored_ids": ignored_ids,
            "rejected_items": rejected_items,
            "unhandled_ids": unhandled_ids,
            "ignored": data.get("ignored") or [],
        }