"""Unit tests for offline, fail-closed RSH employee approval validation."""
import contextlib
import csv
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

module_path = Path(__file__).resolve().parents[1] / "scripts" / "validate_rsh_mapping_approvals.py"
spec = importlib.util.spec_from_file_location("raidat_validator", module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write_csv(path, rows, delimiter=","):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)


class ApprovalValidatorTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.p = Path(self.dir.name)
        self.r = self.p / "rsh.csv"
        self.z = self.p / "zk.csv"
        self.h = self.p / "hik.csv"
        self.v = self.p / "review.csv"
        self.roster = [
            {"test_employee_id": "1", "employee_name": "A Employee", "department": "Production"},
            {"test_employee_id": "2", "employee_name": "B Employee", "department": "HR"},
        ]
        self.zk = [{"device_id": "zk_room_1", "user_id": "0012", "device_display_name": "A Employee"}]
        self.hik = [{"device_id": "hik_room_2", "user_id": "0788", "device_display_name": "B Employee"}]
        self.review = [
            {"test_employee_id": "1", "employee_name": "A Employee",
             "zk_room_1_user_id": "0012", "hik_room_2_user_id": "",
             "approval_status": "PENDING", "approved_by": "",
             "verification_reference": ""},
            {"test_employee_id": "2", "employee_name": "B Employee",
             "zk_room_1_user_id": "", "hik_room_2_user_id": "0788",
             "approval_status": "PENDING", "approved_by": "",
             "verification_reference": ""},
        ]
        self.write()

    def write(self):
        write_csv(self.r, self.roster)
        write_csv(self.z, self.zk)
        write_csv(self.h, self.hik)
        write_csv(self.v, self.review)

    def check(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = mod.validate(self.r, self.z, self.h, self.v)
        return result, out.getvalue()

    def test_uploaded_style_pending_is_not_ready(self):
        self.review[0].pop("verification_reference")
        self.review[1].pop("verification_reference")
        self.write()
        status, message = self.check()
        self.assertEqual(status, 3)
        self.assertIn("PENDING=2", message)
        self.assertIn("no independently approved", message)
        self.assertNotIn("A Employee", message)

    def test_valid_approvals_do_not_write_anything(self):
        self.review[0].update(approval_status="APPROVED", approved_by="HR Head", verification_reference="HR-TEST-001")
        self.write()
        status, message = self.check()
        self.assertEqual(status, 0)
        self.assertIn("Valid approved employees: 1", message)
        self.assertIn("no Odoo writes", message)

    def test_missing_verification_proof_rejected(self):
        self.review[0].update(approval_status="APPROVED", approved_by="HR", verification_reference="")
        self.write()
        status, message = self.check()
        self.assertEqual(status, 2)
        self.assertIn("missing_verification_reference", message)

    def test_excel_lost_leading_zeros_rejected(self):
        self.review[0].update(approval_status="APPROVED", approved_by="HR", verification_reference="HR-1", zk_room_1_user_id="12")
        self.write()
        status, message = self.check()
        self.assertEqual(status, 2)
        self.assertIn("device_user_id_unknown_or_excel_corrupted", message)

    def test_duplicate_user_id_rejected(self):
        self.review[0].update(approval_status="APPROVED", approved_by="HR", verification_reference="HR-1")
        self.review[1].update(approval_status="APPROVED", approved_by="HR", verification_reference="HR-2", zk_room_1_user_id="0012")
        self.write()
        status, message = self.check()
        self.assertEqual(status, 2)
        self.assertIn("device_user_id_reused", message)

    def test_changed_employee_name_rejected(self):
        self.review[0]["employee_name"] = "Another Employee"
        self.write()
        status, message = self.check()
        self.assertEqual(status, 2)
        self.assertIn("employee_name_changed", message)

    def test_tsv_format_supported(self):
        write_csv(self.v, self.review, delimiter="\t")
        status, _ = self.check()
        self.assertEqual(status, 3)


if __name__ == "__main__":
    unittest.main()
