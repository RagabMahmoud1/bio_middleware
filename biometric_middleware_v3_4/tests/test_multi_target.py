"""Offline regression tests for safe two-company delivery."""
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Database
from app.multi_target import MultiTargetRuntime
from app.main import run_cycle


def event(code, device="zk_room_1", minute=1):
    return {
        "device_id": device, "device_type": "zkteco",
        "employee_code": code,
        "event_time": "2026-10-19T08:%02d:00+03:00" % minute,
        "event_type": "check",
        "source_event_id": "%s-%d" % (code, minute),
        "raw": {},
    }


class StubOdoo:
    def __init__(self, cfg):
        self.base_url = cfg["base_url"]
        self.allowed = set()
        self.fail = False
        self.received = []
        self.heartbeats = []

    def get_allowed_employee_ids(self, device):
        if self.fail:
            raise RuntimeError("Target unavailable")
        return sorted(self.allowed)

    def send(self, events):
        if self.fail:
            raise RuntimeError("Target unavailable")
        self.received.extend(row["event_key"] for row in events)
        return {
            "accepted_ids": [row["id"] for row in events],
            "ignored_ids": [], "rejected_items": [], "unhandled_ids": [],
        }

    def heartbeat(self, payload):
        self.heartbeats.append(payload)
        return {"updated_devices": len(payload["devices"])}


class MultiTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Database(Path(self.temp.name) / "test.db")
        self.db.add_events_bulk([
            event("erp_only", minute=1),
            event("rsh_only", minute=2),
            event("both", minute=3),
        ])
        self.db.mark_synced([1, 3])
        self.db.mark_ignored([2])
        self.config = {
            "odoo": {"base_url": "https://erp.example/"},
            "legacy_target_id": "erp",
            "odoo_targets": [
                {"id": "erp", "enabled": True, "base_url": "https://erp.example",
                 "api_token": "example", "device_ids": ["zk_room_1"]},
                {"id": "rsh", "enabled": True, "base_url": "https://rsh.example",
                 "api_token": "example", "device_ids": ["zk_room_1"],
                 "start_at": "2026-10-19T00:00:00+03:00"},
            ],
        }
        self.created = {}

        def new_client(cfg):
            client = StubOdoo(cfg)
            self.created[cfg["base_url"]] = client
            return client

        self.patcher = patch("app.multi_target.OdooClient", side_effect=new_client)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def runtime(self):
        result = MultiTargetRuntime(self.config, self.db)
        self.created["https://erp.example"].allowed = {"erp_only", "both"}
        self.created["https://rsh.example"].allowed = {"rsh_only", "both"}
        return result

    def test_migrate_legacy_ack_without_resending_to_erp(self):
        runtime = self.runtime()
        self.assertEqual(self.db.target_queue_stats("erp")["synced"], 2)
        self.assertEqual(self.db.target_queue_stats("erp")["ignored"], 1)
        self.assertEqual(self.db.pending_for_target("erp"), [])
        runtime.get_allowed_employee_ids("zk_room_1")
        runtime.queue_captured("zk_room_1")
        self.assertEqual(len(self.db.pending_for_target("rsh")), 2)
        self.assertEqual(self.db.pending_for_target("erp"), [])
        self.assertTrue(runtime.send_pending())
        self.assertEqual(len(self.created["https://rsh.example"].received), 2)
        self.assertEqual(len(self.created["https://erp.example"].received), 0)
        self.assertEqual(self.db.target_queue_stats("rsh")["synced"], 2)
        self.assertEqual(self.db.queue_stats()["ignored"], 1)
        self.assertEqual(self.db.queue_stats()["synced"], 2)

    def test_dual_receivers_independent_for_new_events(self):
        runtime = self.runtime()
        runtime.get_allowed_employee_ids("zk_room_1")
        self.db.add_events_bulk([event("both", minute=9)])
        runtime.queue_captured("zk_room_1")
        self.assertEqual(len(self.db.pending_for_target("erp")), 1)
        self.assertEqual(len(self.db.pending_for_target("rsh")), 3)
        self.assertTrue(runtime.send_pending())
        self.assertEqual(len(self.created["https://erp.example"].received), 1)
        self.assertEqual(len(self.created["https://rsh.example"].received), 3)

    def test_failed_target_does_not_block_other(self):
        runtime = self.runtime()
        runtime.get_allowed_employee_ids("zk_room_1")
        runtime.queue_captured("zk_room_1")
        self.created["https://rsh.example"].fail = True
        self.assertFalse(runtime.send_pending())
        self.assertEqual(len(self.db.pending_for_target("rsh")), 2)
        self.assertEqual(self.db.target_queue_stats("erp")["synced"], 2)
        self.created["https://rsh.example"].fail = False
        self.assertTrue(runtime.send_pending())
        self.assertEqual(self.db.target_queue_stats("rsh")["pending"], 0)

    def test_unavailable_target_prevents_cursor_collection(self):
        runtime = self.runtime()
        self.created["https://rsh.example"].fail = True
        with self.assertRaises(RuntimeError):
            runtime.get_allowed_employee_ids("zk_room_1")

    def test_one_time_legacy_migration_cannot_be_reassigned(self):
        self.runtime()
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM integration_state WHERE key='multi_target_legacy_seeded'").fetchone()
        self.assertEqual(row[0], "erp")
        self.config["legacy_target_id"] = "rsh"
        with self.assertRaises(ValueError):
            self.runtime()

    def test_require_explicit_backfill_date_for_new_target(self):
        del self.config["odoo_targets"][1]["start_at"]
        with self.assertRaises(ValueError):
            self.runtime()

    def test_source_legacy_url_must_match(self):
        self.config["odoo"]["base_url"] = "https://another.example"
        with self.assertRaises(ValueError):
            self.runtime()

    def test_historical_cutoff(self):
        self.config["odoo_targets"][1]["start_at"] = "2026-10-20T00:00:00+03:00"
        runtime = self.runtime()
        runtime.get_allowed_employee_ids("zk_room_1")
        runtime.queue_captured("zk_room_1")
        self.assertEqual(self.db.pending_for_target("rsh"), [])


    def test_cycle_collects_rsh_only_employee_without_resending_erp_history(self):
        runtime = self.runtime()
        cfg = {
            "sync": {"go_live_at": "2026-07-19 00:00:00", "batch_size": 500},
            "devices": [{"id": "zk_room_1", "type": "zkteco", "enabled": True}],
        }
        with patch("app.main.build_adapter") as adapter_factory:
            adapter = adapter_factory.return_value
            adapter.test_connection.return_value = {"ok": True}
            adapter.fetch_events.return_value = [event("rsh_only", minute=8)]
            self.assertTrue(run_cycle(cfg, self.db, runtime))
        self.assertEqual(self.db.queue_stats()["pending"], 1)
        self.assertEqual(self.db.target_queue_stats("erp")["pending"], 0)
        self.assertEqual(self.db.target_queue_stats("rsh")["synced"], 3)
        self.assertEqual(len(self.created["https://erp.example"].received), 0)

    def test_mapping_outage_does_not_fetch_or_advance_hikvision(self):
        runtime = self.runtime()
        self.created["https://rsh.example"].fail = True
        cfg = {
            "sync": {"go_live_at": "2026-07-19 00:00:00"},
            "devices": [{"id": "zk_room_1", "type": "zkteco", "enabled": True}],
        }
        with patch("app.main.build_adapter") as adapter_factory:
            self.assertFalse(run_cycle(cfg, self.db, runtime))
            adapter_factory.return_value.fetch_events.assert_not_called()
        self.assertIsNone(self.db.get_setting("device_fetch_cursor:zk_room_1"))

    def test_heartbeat_isolated_per_target(self):
        runtime = self.runtime()
        runtime.get_allowed_employee_ids("zk_room_1")
        runtime.queue_captured("zk_room_1")
        self.assertTrue(runtime.send_heartbeat())
        erp = self.created["https://erp.example"].heartbeats[0]["queue"]
        rsh = self.created["https://rsh.example"].heartbeats[0]["queue"]
        self.assertEqual(erp["pending"], 0)
        self.assertEqual(rsh["pending"], 2)


if __name__ == "__main__":
    unittest.main()