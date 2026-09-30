import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database


class IdempotencyTests(unittest.TestCase):
    def _event(self, **overrides):
        event = {
            "device_id": "zk_room_1",
            "device_type": "zkteco",
            "employee_code": "101",
            "event_time": "2026-09-29T08:00:00+03:00",
            "event_type": "check_in",
            "source_event_id": None,
            "raw": {},
        }
        event.update(overrides)
        return event

    def test_same_logical_event_has_same_key(self):
        event = self._event()
        self.assertEqual(
            Database.make_event_key(event),
            Database.make_event_key(dict(event)),
        )

    def test_bulk_insert_same_event_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "events.db"))
            event = self._event()
            self.assertEqual(db.add_events_bulk([event]), 1)
            self.assertEqual(db.add_events_bulk([event]), 0)
            self.assertEqual(db.add_events_bulk([event, event]), 0)

    def test_device_is_part_of_event_identity(self):
        first = Database.make_event_key(self._event(device_id="zk_room_1"))
        second = Database.make_event_key(self._event(device_id="hik_room_2"))
        self.assertNotEqual(first, second)

    def test_employee_is_part_of_event_identity(self):
        first = Database.make_event_key(self._event(employee_code="101"))
        second = Database.make_event_key(self._event(employee_code="102"))
        self.assertNotEqual(first, second)

    def test_time_is_part_of_event_identity(self):
        first = Database.make_event_key(
            self._event(event_time="2026-09-29T08:00:00+03:00")
        )
        second = Database.make_event_key(
            self._event(event_time="2026-09-29T08:00:01+03:00")
        )
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
