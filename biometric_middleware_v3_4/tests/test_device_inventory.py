"""Device user inventory must remain read-only and not touch the production service."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.export_device_users_readonly import (
    list_zkteco_users, list_hikvision_users, export_device_users,
)


class ZKConnection:
    def __init__(self):
        self.disconnected = False
        self.requested_users = False

    def get_users(self):
        self.requested_users = True
        return [
            SimpleNamespace(user_id="0012", uid=12, name="Operator A"),
            SimpleNamespace(user_id="0023", uid=23, name="=excel"),
        ]

    def disconnect(self):
        self.disconnected = True


class FakeZKAdapter:
    def __init__(self, config):
        self.cfg = config
        self.conn = ZKConnection()
    def _connect(self):
        return self.conn


class HikResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return self.payload


class FakeHik:
    requests = []
    def __init__(self, config):
        self.cfg = config
    def _post(self, path, body):
        assert path == "/ISAPI/AccessControl/UserInfo/Search?format=json"
        index = body["UserInfoSearchCond"]["searchResultPosition"]
        self.requests.append((path, body))
        page = [
            {"employeeNo": "31005", "name": "Engineer X"},
            {"employeeNoString": "31006", "name": "+CSV"},
        ] if index == 0 else [{"employeeNo": "31007", "name": "Engineer Z"}]
        return HikResponse({"UserInfoSearch": {
            "totalMatches": 3, "UserInfo": page,
            "responseStatusStrg": "MORE" if index == 0 else "OK",
        }})


class DeviceExportTests(unittest.TestCase):
    def test_zkteco_user_ids_with_leading_zeros_and_disconnect(self):
        record = []
        def factory(cfg):
            a = FakeZKAdapter(cfg)
            record.append(a)
            return a
        rows = list_zkteco_users({"id": "zk_room_1"}, factory)
        self.assertEqual([r["user_id"] for r in rows], ["0012", "0023"])
        self.assertEqual(rows[1]["device_display_name"], "'=excel")
        self.assertTrue(record[0].conn.requested_users)
        self.assertTrue(record[0].conn.disconnected)

    def test_hikvision_user_pages_are_read_only_searches(self):
        FakeHik.requests = []
        rows = list_hikvision_users({"id": "hik_room_2"}, FakeHik, page_size=2)
        self.assertEqual([r["user_id"] for r in rows], ["31005", "31006", "31007"])
        self.assertEqual(rows[1]["device_display_name"], "'+CSV")
        self.assertEqual(len(FakeHik.requests), 2)
        self.assertEqual(FakeHik.requests[0][1]["UserInfoSearchCond"]["searchResultPosition"], 0)
        self.assertEqual(FakeHik.requests[1][1]["UserInfoSearchCond"]["searchResultPosition"], 2)

    def test_config_export_only_selected_device_and_no_sqlite(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "app").mkdir()
            config = base / "config.yaml"
            config.write_text(yaml.safe_dump({
                "devices": [
                    {"id": "zk_room_1", "enabled": True, "type": "zkteco"},
                    {"id": "hik_room_2", "enabled": True, "type": "hikvision"},
                ]
            }))
            output = base / "exports"
            with patch("app.adapters.zkteco.ZKTecoAdapter", FakeZKAdapter):
                filename = export_device_users(config, "zk_room_1", output)
            with filename.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["user_id"], "0012")
            self.assertFalse((base / "data").exists())
            with self.assertRaises(ValueError):
                export_device_users(config, "not_a_device", output)

    def test_device_inventory_will_not_modify_legacy_config(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "app").mkdir()
            config = base / "config.yaml"
            data = "devices:\n- id: zk_room_1\n  type: zkteco\n  enabled: true\n"
            config.write_text(data)
            with patch("app.adapters.zkteco.ZKTecoAdapter", FakeZKAdapter):
                export_device_users(config, "zk_room_1", base / "export")
            self.assertEqual(config.read_text(), data)


if __name__ == "__main__":
    unittest.main()
