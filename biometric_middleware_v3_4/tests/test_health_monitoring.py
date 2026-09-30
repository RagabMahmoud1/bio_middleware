import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database
from app.main import build_health_payload
from app.version import MIDDLEWARE_VERSION


def event(device_id, source, when="2026-09-29T08:00:00+03:00"):
    return {
        "device_id": device_id,
        "device_type": "hikvision",
        "employee_code": "101",
        "event_time": when,
        "event_type": "punch",
        "source_event_id": source,
        "raw": {},
    }


class HealthMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / "health.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_queue_stats_count_statuses(self):
        self.db.add_events_bulk([
            event("hik_room_2", "a"),
            event("hik_room_2", "b", "2026-09-29T08:01:00+03:00"),
        ])
        pending = self.db.pending(limit=10)
        self.db.mark_synced([pending[0]["id"]])
        stats = self.db.queue_stats("hik_room_2")
        self.assertEqual(stats["synced"], 1)
        self.assertEqual(stats["pending"], 1)

    def test_fetch_and_push_timestamps_are_separate(self):
        self.db.add_events_bulk([event("hik_room_2", "a")])
        self.db.update_device_state(
            "hik_room_2",
            fetched=1,
            new_count=1,
            last_event_time="2026-09-29T08:00:00+03:00",
            error=None,
        )
        row = self.db.pending(limit=1)[0]
        self.db.mark_odoo_push_success([row["id"]])
        state = self.db.get_device_states()[0]
        self.assertTrue(state["last_device_fetch_success"])
        self.assertTrue(state["last_odoo_push_success"])

    def test_health_payload_contains_version_and_device_stats(self):
        self.db.add_events_bulk([event("hik_room_2", "a")])
        self.db.update_device_state(
            "hik_room_2",
            fetched=1,
            new_count=1,
            last_event_time="2026-09-29T08:00:00+03:00",
            error=None,
        )
        payload = build_health_payload(self.db)
        self.assertEqual(payload["middleware_version"], MIDDLEWARE_VERSION)
        self.assertEqual(len(payload["devices"]), 1)
        self.assertEqual(payload["devices"][0]["device_id"], "hik_room_2")
        self.assertEqual(payload["devices"][0]["pending_count"], 1)


if __name__ == "__main__":
    unittest.main()
