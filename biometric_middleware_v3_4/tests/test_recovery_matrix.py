import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database
from app.filters import filter_events
from app.main import run_cycle, send_heartbeat


def event(device_id="hik_room_2", source="a"):
    return {
        "device_id": device_id,
        "device_type": "hikvision",
        "employee_code": "101",
        "event_time": "2026-09-29T08:00:00+03:00",
        "event_type": "punch",
        "source_event_id": source,
        "raw": {},
    }


class FakeDisabledOdoo:
    enabled = False


class RecoveryMatrixTests(unittest.TestCase):
    def test_pending_queue_survives_database_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "queue.db")
            first = Database(path)
            first.add_events_bulk([event()])
            self.assertEqual(len(first.pending(limit=10)), 1)

            second = Database(path)
            self.assertEqual(len(second.pending(limit=10)), 1)

    def test_failed_event_does_not_block_new_pending_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "queue.db"))
            db.add_events_bulk([
                event(source="bad"),
                event(source="good"),
            ])
            rows = db.pending(limit=10)
            db.mark_rejected([{
                "id": rows[0]["id"],
                "error": "malformed",
            }])

            pending = db.pending(limit=10)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["event_key"], rows[1]["event_key"])

    def test_empty_mapping_filters_all_employee_events(self):
        events = [
            event(source="a"),
            {
                **event(source="b"),
                "employee_code": "202",
            },
        ]
        self.assertEqual(
            filter_events(events, employee_ids=[]),
            [],
        )

    def test_device_failure_is_recorded_without_crashing_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "queue.db"))
            cfg = {
                "sync": {
                    "go_live_at": "2026-09-01 00:00:00",
                    "employee_ids": ["101"],
                    "batch_size": 100,
                },
                "devices": [{
                    "id": "hik_room_2",
                    "enabled": True,
                    "type": "hikvision",
                }],
            }

            adapter = Mock()
            adapter.test_connection.side_effect = RuntimeError(
                "device offline"
            )

            with patch("app.main.build_adapter", return_value=adapter):
                ok = run_cycle(
                    cfg,
                    db,
                    FakeDisabledOdoo(),
                    only_device="hik_room_2",
                )

            self.assertFalse(ok)
            states = db.get_device_states()
            self.assertEqual(len(states), 1)
            self.assertIn("device offline", states[0]["last_error"])

    def test_heartbeat_failure_is_non_destructive(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(str(Path(tmp) / "queue.db"))
            db.add_events_bulk([event()])

            odoo = Mock()
            odoo.enabled = True
            odoo.heartbeat.side_effect = RuntimeError("odoo offline")

            self.assertFalse(send_heartbeat(db, odoo))
            self.assertEqual(len(db.pending(limit=10)), 1)


if __name__ == "__main__":
    unittest.main()
