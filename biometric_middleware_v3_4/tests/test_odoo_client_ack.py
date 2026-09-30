import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.odoo_client import OdooClient


class OdooClientAckTests(unittest.TestCase):
    def _client(self):
        return OdooClient({
            "enabled": True,
            "base_url": "https://example.test",
            "endpoint": "/biometric/api/v1/events",
            "api_token": "secret",
            "timeout_seconds": 20,
            "verify_ssl": True,
        })

    def _rows(self):
        return [
            {
                "id": 1,
                "event_key": "a",
                "device_id": "zk_room_1",
                "device_type": "zkteco",
                "employee_code": "101",
                "event_time": "2026-09-29T08:00:00+03:00",
                "event_type": "check_in",
                "raw_json": json.dumps({}),
            },
            {
                "id": 2,
                "event_key": "b",
                "device_id": "zk_room_1",
                "device_type": "zkteco",
                "employee_code": "102",
                "event_time": "2026-09-29T08:01:00+03:00",
                "event_type": "check_in",
                "raw_json": json.dumps({}),
            },
            {
                "id": 3,
                "event_key": "c",
                "device_id": "zk_room_1",
                "device_type": "zkteco",
                "employee_code": "103",
                "event_time": "2026-09-29T08:02:00+03:00",
                "event_type": "check_in",
                "raw_json": json.dumps({}),
            },
        ]

    def _response(self, payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    def test_mixed_response_maps_each_event_without_batch_exception(self):
        payload = {
            "ok": True,
            "accepted_event_keys": ["a"],
            "ignored_event_keys": ["b"],
            "ignored": [{"event_key": "b", "reason": "unknown_employee"}],
            "rejected": [{"event_key": "c", "error": "bad_event"}],
        }
        with patch(
            "app.odoo_client.requests.post",
            return_value=self._response(payload),
        ):
            result = self._client().send(self._rows())

        self.assertEqual(result["accepted_ids"], [1])
        self.assertEqual(result["ignored_ids"], [2])
        self.assertEqual(
            result["rejected_items"],
            [{"id": 3, "event_key": "c", "error": "bad_event"}],
        )
        self.assertEqual(result["unhandled_ids"], [])

    def test_missing_ack_is_reported_as_unhandled(self):
        payload = {
            "ok": True,
            "accepted_event_keys": ["a"],
            "ignored_event_keys": [],
            "ignored": [],
            "rejected": [],
        }
        with patch(
            "app.odoo_client.requests.post",
            return_value=self._response(payload),
        ):
            result = self._client().send(self._rows())

        self.assertEqual(result["accepted_ids"], [1])
        self.assertEqual(result["unhandled_ids"], [2, 3])


if __name__ == "__main__":
    unittest.main()
