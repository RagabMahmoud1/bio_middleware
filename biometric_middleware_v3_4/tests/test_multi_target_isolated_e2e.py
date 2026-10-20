"""Comprehensive OFFLINE two-company simulation with SQLite on a temporary path.

Never connects to a real biometric device or Odoo API. Exercises production
Middleware 3.6 runtime code using synthetic employees, device events and Odoo
acknowledgements, including target-specific routing and partial failures.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import Database
from app.main import run_cycle
from app.multi_target import MultiTargetRuntime


def punch(device, employee, minute):
    return {
        "device_id": device,
        "device_type": "zkteco" if device == "zk_room_1" else "hikvision",
        "employee_code": employee,
        "event_time": "2026-10-20T06:%02d:00+03:00" % minute,
        "event_type": "check",
        "source_event_id": "%s-%s-%d" % (device, employee, minute),
        "raw": {"synthetic": True},
    }


class IsolatedOdooClient:
    registry = {}
    allowed = {
        "https://test-erp.invalid": {
            "zk_room_1": {"erp_only", "shared"},
            "hik_room_2": {"shared"},
        },
        "https://test-rsh.invalid": {
            "zk_room_1": {"rsh_only", "shared"},
            "hik_room_2": {"shared"},
        },
    }

    def __init__(self, cfg):
        self.url = cfg["base_url"]
        self.received = []
        self.down = False
        self.lookup_down = False
        IsolatedOdooClient.registry[self.url] = self

    def get_allowed_employee_ids(self, device_id):
        if self.lookup_down:
            raise RuntimeError("synthetic mapping API outage")
        return sorted(self.allowed[self.url].get(device_id, set()))

    def send(self, events):
        if self.down:
            raise RuntimeError("synthetic target HTTP outage")
        self.received.extend([(event["device_id"], event["employee_code"]) for event in events])
        return {
            "accepted_ids": [e["id"] for e in events],
            "ignored_ids": [], "rejected_items": [], "unhandled_ids": [],
        }

    def heartbeat(self, payload):
        return {"updated_devices": len(payload["devices"])}


class SyntheticAdapter:
    def __init__(self, cfg):
        self.device_id = cfg["id"]
        self.last_query_end = "2026-10-20T06:55:00+03:00"
        self.fetched = False
    def test_connection(self):
        return {"ok": True}
    def fetch_events(self, **kwargs):
        self.fetched = True
        if self.device_id == "zk_room_1":
            return [
                punch(self.device_id, "erp_only", 1),
                punch(self.device_id, "rsh_only", 2),
                punch(self.device_id, "shared", 3),
                punch(self.device_id, "neither", 4),
            ]
        return [punch(self.device_id, "shared", 5)]


class MultiTargetIsolatedE2E(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="raidat-mw-isolated-")
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "offline.sqlite"
        self.db = Database(self.path)
        self.cfg = {
            "app": {"database_path": str(self.path)},
            "sync": {"go_live_at": "2026-10-19 00:00:00", "batch_size": 500},
            "odoo": {"base_url": "https://test-erp.invalid"},
            "legacy_target_id": "erp",
            "odoo_targets": [
                {
                    "id": "erp", "enabled": True,
                    "base_url": "https://test-erp.invalid",
                    "api_token": "synthetic",
                    "device_ids": ["zk_room_1", "hik_room_2"],
                },
                {
                    "id": "rsh", "enabled": True,
                    "base_url": "https://test-rsh.invalid",
                    "api_token": "synthetic",
                    "device_ids": ["zk_room_1", "hik_room_2"],
                    "start_at": "2026-10-20T00:00:00+03:00",
                },
            ],
            "devices": [
                {"id": "zk_room_1", "type": "zkteco", "enabled": True},
                {"id": "hik_room_2", "type": "hikvision", "enabled": True},
            ],
        }
        IsolatedOdooClient.registry = {}
        patcher = patch("app.multi_target.OdooClient", IsolatedOdooClient)
        patcher.start()
        self.addCleanup(patcher.stop)
        adapters = patch("app.main.build_adapter", side_effect=SyntheticAdapter)
        adapters.start()
        self.addCleanup(adapters.stop)
        self.runtime = MultiTargetRuntime(self.cfg, self.db)

    def counts(self):
        return (self.db.target_queue_stats("erp"), self.db.target_queue_stats("rsh"))

    def test_two_device_routing_shared_and_separate(self):
        self.assertTrue(run_cycle(self.cfg, self.db, self.runtime))
        erp, rsh = self.counts()
        self.assertEqual(erp["synced"], 3)
        self.assertEqual(rsh["synced"], 3)
        self.assertEqual(self.db.queue_stats()["pending"], 1)
        self.assertEqual(self.db.queue_stats()["synced"], 3)
        clients = IsolatedOdooClient.registry
        self.assertCountEqual(clients["https://test-erp.invalid"].received, [
            ("zk_room_1", "erp_only"), ("zk_room_1", "shared"),
            ("hik_room_2", "shared")
        ])
        self.assertCountEqual(clients["https://test-rsh.invalid"].received, [
            ("zk_room_1", "rsh_only"), ("zk_room_1", "shared"),
            ("hik_room_2", "shared")
        ])
        # A second polling cycle must not resend a previously acknowledged event.
        self.assertTrue(run_cycle(self.cfg, self.db, self.runtime))
        self.assertEqual(len(clients["https://test-erp.invalid"].received), 3)
        self.assertEqual(len(clients["https://test-rsh.invalid"].received), 3)

    def test_rsh_failure_does_not_roll_back_erp_and_recovers_after_restart(self):
        clients = IsolatedOdooClient.registry
        clients["https://test-rsh.invalid"].down = True
        self.assertFalse(run_cycle(self.cfg, self.db, self.runtime))
        erp, rsh = self.counts()
        self.assertEqual(erp["synced"], 3)
        self.assertEqual(rsh["pending"], 3)
        self.assertEqual(len(clients["https://test-erp.invalid"].received), 3)
        # Restart from same local SQLite database without changing Production.
        self.db = Database(self.path)
        self.runtime = MultiTargetRuntime(self.cfg, self.db)
        fresh = IsolatedOdooClient.registry
        self.assertEqual(self.db.target_queue_stats("erp")["pending"], 0)
        self.assertEqual(self.db.target_queue_stats("rsh")["pending"], 3)
        self.assertTrue(self.runtime.send_pending())
        self.assertEqual(len(fresh["https://test-erp.invalid"].received), 0)
        self.assertEqual(len(fresh["https://test-rsh.invalid"].received), 3)
        self.assertEqual(self.db.target_queue_stats("rsh")["pending"], 0)

    def test_rsh_lookup_outage_does_not_fetch_or_advance_hik_cursor(self):
        clients = IsolatedOdooClient.registry
        clients["https://test-rsh.invalid"].lookup_down = True
        self.assertFalse(run_cycle(self.cfg, self.db, self.runtime, only_device="hik_room_2"))
        self.assertIsNone(self.db.get_setting("device_fetch_cursor:hik_room_2"))
        self.assertEqual(self.db.queue_stats()["pending"], 0)
        clients["https://test-rsh.invalid"].lookup_down = False
        self.assertTrue(run_cycle(self.cfg, self.db, self.runtime, only_device="hik_room_2"))
        self.assertEqual(self.db.target_queue_stats("erp")["synced"], 1)
        self.assertEqual(self.db.target_queue_stats("rsh")["synced"], 1)

    def test_legacy_already_synced_not_replayed(self):
        self.db.add_events_bulk([punch("zk_room_1", "shared", 12)])
        self.db.mark_synced([1])
        # Start from new empty database to mimic pre-migration v3 state;
        # reusing migrated DB instead simply retains target delivery statuses.
        with tempfile.TemporaryDirectory() as root:
            fresh_db = Database(Path(root) / "pre_migration.sqlite")
            fresh_db.add_events_bulk([punch("zk_room_1", "shared", 12)])
            fresh_db.mark_synced([1])
            runtime = MultiTargetRuntime(self.cfg, fresh_db)
            runtime.get_allowed_employee_ids("zk_room_1")
            runtime.queue_captured("zk_room_1")
            self.assertEqual(fresh_db.pending_for_target("erp"), [])
            self.assertEqual(len(fresh_db.pending_for_target("rsh")), 1)
            self.assertTrue(runtime.send_pending())
            self.assertEqual(fresh_db.target_queue_stats("erp")["synced"], 1)
            self.assertEqual(fresh_db.target_queue_stats("rsh")["synced"], 1)


if __name__ == "__main__":
    unittest.main()
