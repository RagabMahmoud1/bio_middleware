import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.filters import filter_events
from app.odoo_client import OdooClient


class AllowedEmployeeFilterTests(unittest.TestCase):
    def setUp(self):
        self.events = [
            {
                "employee_code": "101",
                "event_time": "2026-09-28 08:00:00",
            },
            {
                "employee_code": "202",
                "event_time": "2026-09-28 08:05:00",
            },
        ]

    def test_only_mapped_employee_is_kept(self):
        result = filter_events(self.events, employee_ids=["101"])
        self.assertEqual(
            [event["employee_code"] for event in result],
            ["101"],
        )

    def test_empty_mapping_list_allows_nobody(self):
        result = filter_events(self.events, employee_ids=[])
        self.assertEqual(result, [])

    def test_none_preserves_legacy_unfiltered_mode(self):
        result = filter_events(self.events, employee_ids=None)
        self.assertEqual(len(result), 2)


class AllowedEmployeeOdooClientTests(unittest.TestCase):
    def _client(self):
        return OdooClient({
            "enabled": True,
            "base_url": "https://example.test",
            "api_token": "secret",
            "timeout_seconds": 20,
            "verify_ssl": True,
        })

    def test_allowed_employee_ids_are_normalized(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "ok": True,
            "allowed_employee_ids": [" 101 ", "202", "101"],
        }

        with patch(
            "app.odoo_client.requests.get",
            return_value=response,
        ) as get:
            result = self._client().get_allowed_employee_ids(
                "zk_room_1"
            )

        self.assertEqual(result, ["101", "202"])
        self.assertEqual(
            get.call_args.kwargs["params"]["device_id"],
            "zk_room_1",
        )

    def test_empty_mapping_list_stays_empty(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "ok": True,
            "allowed_employee_ids": [],
        }

        with patch(
            "app.odoo_client.requests.get",
            return_value=response,
        ):
            result = self._client().get_allowed_employee_ids(
                "hik_room_2"
            )

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
