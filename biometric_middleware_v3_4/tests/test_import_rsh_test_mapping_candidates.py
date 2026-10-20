"""RSH provisional mapping importer: 7 isolated tests, zero real Odoo writes."""
import csv
import importlib.util
import io
import contextlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts" / "import_rsh_test_mapping_candidates.py"
spec = importlib.util.spec_from_file_location("raidat_rsh_provisional", FILE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class OdooRecord(SimpleNamespace):
    def exists(self):
        return self


class FakeDeviceModel:
    def __init__(self, records):
        self.records = records
    def sudo(self):
        return self
    def search(self, domain):
        return self.records


class FakeEmployeeModel:
    def __init__(self, records):
        self.records = {e.id: e for e in records}
    def sudo(self):
        return self
    def browse(self, employee_id):
        if employee_id not in self.records:
            return SimpleNamespace(exists=lambda: False)
        return self.records[employee_id]


class FakeMappingModel:
    def __init__(self):
        self.records = []
        self.create_calls = 0
    def sudo(self):
        return self
    def with_context(self, **kwargs):
        return self
    def search(self, domain):
        device_id = domain[0][2]
        uid = domain[2][2]
        employee_id = domain[3][2]
        return [
            r for r in self.records
            if r.device_id.id == device_id and (
                r.external_user_id == uid or r.employee_id.id == employee_id
            )
        ]
    def create(self, batch):
        self.create_calls += 1
        self.records.extend([
            OdooRecord(
                id=i + 1, device_id=self.env.devices_by_id[row["device_id"]],
                employee_id=self.env.employees_by_id[row["employee_id"]],
                external_user_id=row["external_user_id"], active=row["active"]
            ) for i, row in enumerate(batch)
        ])


class FakeEnv:
    def __init__(self, employees):
        company = OdooRecord(id=4)
        self.devices = [
            OdooRecord(id=1, external_id="zk_room_1", active=True,
                       company_id=company, processing_strategy="raw_only"),
            OdooRecord(id=2, external_id="hik_room_2", active=True,
                       company_id=company, processing_strategy="raw_only"),
        ]
        self.devices_by_id = {d.id: d for d in self.devices}
        self.employees_by_id = {e.id: e for e in employees}
        self.mappings = FakeMappingModel()
        self.mappings.env = self
        self.cr = OdooRecord(dbname="test_RSH", commits=0, rollbacks=0)
        self.cr.commit = lambda: setattr(self.cr, "commits", self.cr.commits + 1)
        self.cr.rollback = lambda: setattr(self.cr, "rollbacks", self.cr.rollbacks + 1)
        self.models = {
            "asg.biometric.device": FakeDeviceModel(self.devices),
            "hr.employee": FakeEmployeeModel(employees),
            "asg.biometric.employee.mapping": self.mappings,
        }
    def __getitem__(self, key):
        return self.models[key]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    path.chmod(0o600)


class ProvisionalMappingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.base = Path(self.folder.name)
        self.original_base = mod.PRIVATE_DIR
        mod.PRIVATE_DIR = self.base
        self.addCleanup(lambda: setattr(mod, "PRIVATE_DIR", self.original_base))
        company = OdooRecord(id=4)
        self.employees = [
            OdooRecord(id=i + 10, name="Worker %03d" % i, active=True,
                       company_id=company)
            for i in range(138)
        ]
        self.env = FakeEnv(self.employees)
        self.rows = []
        for i, employee in enumerate(self.employees):
            zk_id = "ZK-%04d" % i if i < 19 else ""
            hik_id = "HIK-%04d" % i if 5 <= i < 51 else ""
            self.rows.append({
                "test_employee_id": str(employee.id),
                "employee_name": employee.name,
                "zk_room_1_user_id": zk_id,
                "hik_room_2_user_id": hik_id,
                "approved_by": "",
                "approval_status": "PENDING",
                "match_review": (
                    "EXACT_NAME_CANDIDATE_VERIFY_DEVICE_ID"
                    if zk_id or hik_id else "NEEDS_MANUAL_DEVICE_IDENTIFICATION"
                ),
            })
        self.zk = [
            {"device_id": "zk_room_1", "user_id": "ZK-%04d" % i,
             "device_display_name": "Worker %03d" % i}
            for i in range(19)
        ] + [
            {"device_id": "zk_room_1", "user_id": "X-%04d" % i,
             "device_display_name": "Other %03d" % i}
            for i in range(396 - 19)
        ]
        self.hik = [
            {"device_id": "hik_room_2", "user_id": "HIK-%04d" % i,
             "device_display_name": "Worker %03d" % i}
            for i in range(5, 51)
        ] + [
            {"device_id": "hik_room_2", "user_id": "Y-%04d" % i,
             "device_display_name": "Other %03d" % i}
            for i in range(130 - 46)
        ]
        self.save()

    def save(self):
        write_csv(self.base / "rsh_review_test.csv", self.rows)
        write_csv(self.base / "zk_test.csv", self.zk)
        write_csv(self.base / "hik_test.csv", self.hik)

    def run_preview(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            outcome = mod.preview_rsh_test_mappings(self.env, private_dir=self.base, **kwargs)
        return outcome, stream.getvalue()

    def test_preview_is_read_only_and_counts_exact(self):
        result, message = self.run_preview()
        self.assertEqual(result["to_create"], 65)
        self.assertIn("Candidate employees: 51", message)
        self.assertEqual(self.env.mappings.create_calls, 0)
        self.assertEqual(self.env.cr.commits, 0)

    def test_refuse_live_before_reading_files(self):
        self.env.cr.dbname = "rsh"
        with self.assertRaisesRegex(RuntimeError, "production"):
            self.run_preview()

    def test_apply_needs_exact_confirmation(self):
        with self.assertRaisesRegex(RuntimeError, "confirmation"):
            self.run_preview(apply=True)

    def test_apply_is_idempotent_and_test_only(self):
        first, _ = self.run_preview(apply=True, confirm=mod.APPROVAL_PHRASE)
        self.assertEqual(first["created"], 65)
        self.assertEqual(len(self.env.mappings.records), 65)
        self.assertEqual(self.env.cr.commits, 1)
        second, _ = self.run_preview(apply=True, confirm=mod.APPROVAL_PHRASE)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["already_present"], 65)
        self.assertEqual(self.env.cr.commits, 2)

    def test_refuse_changed_employee_name(self):
        self.rows[0]["employee_name"] = "Different Employee"
        self.save()
        with self.assertRaisesRegex(RuntimeError, "employee"):
            self.run_preview()
        self.assertEqual(self.env.mappings.create_calls, 0)

    def test_refuse_wrong_device_user_id(self):
        self.rows[0]["zk_room_1_user_id"] = "NO-SUCH-DEVICE-ID"
        self.save()
        with self.assertRaisesRegex(RuntimeError, "original device inventory"):
            self.run_preview()
        self.assertEqual(self.env.mappings.create_calls, 0)

    def test_refuse_duplicated_mapping(self):
        self.rows[1]["zk_room_1_user_id"] = self.rows[0]["zk_room_1_user_id"]
        self.save()
        with self.assertRaisesRegex(RuntimeError, "original device inventory"):
            self.run_preview()
        self.assertEqual(self.env.mappings.create_calls, 0)

    def test_refuse_world_readable_input(self):
        (self.base / "zk_test.csv").chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "readable"):
            self.run_preview()

    def test_refuse_existing_conflicting_mapping(self):
        self.env.mappings.records.append(
            OdooRecord(
                device_id=self.env.devices_by_id[1],
                employee_id=self.env.employees_by_id[10],
                external_user_id="SHADOW", active=True
            )
        )
        with self.assertRaisesRegex(RuntimeError, "conflicting existing"):
            self.run_preview()
        self.assertEqual(self.env.mappings.create_calls, 0)


if __name__ == "__main__":
    unittest.main()
