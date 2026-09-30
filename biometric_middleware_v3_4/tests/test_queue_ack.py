import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Database
from app.main import send_pending


def event(device, employee, when, source):
    return {
        "device_id": device,
        "device_type": "hikvision",
        "employee_code": employee,
        "event_time": when,
        "event_type": "punch",
        "source_event_id": source,
        "raw": {"source": source},
    }


class QueueAckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / "queue.db"))
        self.db.add_events_bulk([
            event("hik_room_2", "101", "2026-09-29T08:00:00+03:00", "a"),
            event("hik_room_2", "102", "2026-09-29T08:01:00+03:00", "b"),
            event("hik_room_2", "103", "2026-09-29T08:02:00+03:00", "c"),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def _rows(self):
        with self.db.connect() as conn:
            conn.row_factory = __import__("sqlite3").Row
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM events ORDER BY id"
                ).fetchall()
            ]

    def test_mixed_ack_does_not_block_batch(self):
        pending = self.db.pending(limit=200)
        client = Mock()
        client.enabled = True
        client.send.return_value = {
            "accepted_ids": [pending[0]["id"]],
            "ignored_ids": [pending[1]["id"]],
            "rejected_items": [{
                "id": pending[2]["id"],
                "event_key": pending[2]["event_key"],
                "error": "malformed_event",
            }],
            "unhandled_ids": [],
        }

        self.assertTrue(send_pending(self.db, client))
        rows = self._rows()
        self.assertEqual(
            [row["sync_status"] for row in rows],
            ["synced", "ignored", "failed"],
        )
        self.assertEqual(self.db.pending(limit=200), [])

    def test_network_failure_keeps_batch_pending_for_retry(self):
        client = Mock()
        client.enabled = True
        client.send.side_effect = RuntimeError("odoo offline")

        self.assertFalse(send_pending(self.db, client))
        rows = self._rows()
        self.assertEqual(
            [row["sync_status"] for row in rows],
            ["pending", "pending", "pending"],
        )
        self.assertTrue(all(row["sync_attempts"] == 1 for row in rows))

    def test_unhandled_only_remains_pending(self):
        pending = self.db.pending(limit=200)
        client = Mock()
        client.enabled = True
        client.send.return_value = {
            "accepted_ids": [pending[0]["id"]],
            "ignored_ids": [pending[1]["id"]],
            "rejected_items": [],
            "unhandled_ids": [pending[2]["id"]],
        }

        self.assertFalse(send_pending(self.db, client))
        rows = self._rows()
        self.assertEqual(
            [row["sync_status"] for row in rows],
            ["synced", "ignored", "pending"],
        )
        self.assertEqual(rows[2]["sync_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
