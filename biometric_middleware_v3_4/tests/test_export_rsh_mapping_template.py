"""Offline tests for private RSH TEST mapping roster export."""
import csv
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.export_rsh_test_mapping_template import export_rsh_mapping_template


class DeviceList:
    def __init__(self):
        company = SimpleNamespace(id=8)
        self.entries = [
            SimpleNamespace(external_id="zk_room_1", company_id=company),
            SimpleNamespace(external_id="hik_room_2", company_id=company),
        ]
    def sudo(self):
        return self
    def search(self, domain):
        return self.entries


class Employees:
    def sudo(self):
        return self
    def search(self, domain, order="id"):
        return [
            SimpleNamespace(id=101, name="Employee Alpha",
                            department_id=SimpleNamespace(display_name="Dept A"),
                            pin="1234", barcode="SENSITIVE"),
            SimpleNamespace(id=102, name="Employee Beta",
                            department_id=None, pin="1234", barcode="SECRET"),
        ]


class Env:
    def __init__(self, db="test_RSH"):
        self.cr = SimpleNamespace(dbname=db)
        self.devices = DeviceList()
        self.employees = Employees()
    def __getitem__(self, key):
        return {
            "asg.biometric.device": self.devices,
            "hr.employee": self.employees,
        }[key]


class TemplateTests(unittest.TestCase):
    def test_refuses_production_without_writing(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "roster.csv"
            with self.assertRaisesRegex(RuntimeError, "REFUSED"):
                export_rsh_mapping_template(Env("rsh.raidatalsharq.com"), dest)
            self.assertFalse(dest.exists())

    def test_private_roster_excludes_pins_and_never_guesses_device_ids(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "secure" / "roster.csv"
            export_rsh_mapping_template(Env(), dest)
            self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(dest.parent.stat().st_mode), 0o700)
            with dest.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["employee_name"], "Employee Alpha")
            self.assertEqual(rows[0]["zk_room_1_user_id"], "")
            self.assertEqual(rows[0]["hik_room_2_user_id"], "")
            self.assertEqual(rows[0]["approval_status"], "PENDING")
            contents = dest.read_text(encoding="utf-8-sig")
            self.assertNotIn("SENSITIVE", contents)
            self.assertNotIn("SECRET", contents)
            self.assertNotIn("1234", contents)
            with self.assertRaises(FileExistsError):
                export_rsh_mapping_template(Env(), dest)

    def test_reject_wrong_devices(self):
        with tempfile.TemporaryDirectory() as td:
            env = Env()
            env.devices.entries = [env.devices.entries[0]]
            with self.assertRaisesRegex(RuntimeError, "two active"):
                export_rsh_mapping_template(env, Path(td) / "file.csv")


if __name__ == "__main__":
    unittest.main()
