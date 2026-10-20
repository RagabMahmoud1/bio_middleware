"""Offline unit tests: exact candidate matching only, no silent auto-approval."""
import csv
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts" / "match_rsh_device_users_offline.py"
spec = importlib.util.spec_from_file_location("raidat_match_rsh", FILE)
matching = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matching)


def save_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.roster = self.root / "rsh.csv"
        self.zk = self.root / "zk.csv"
        self.hik = self.root / "hik.csv"
        self.output = self.root / "private" / "review.csv"
        self.workers = [
            {"test_employee_id": "4", "employee_name": "محمد السيد", "department": "Electric",
             "zk_room_1_user_id": "", "hik_room_2_user_id": "",
             "approved_by": "", "approval_status": "PENDING"},
            {"test_employee_id": "5", "employee_name": "RASHID", "department": "Service",
             "zk_room_1_user_id": "", "hik_room_2_user_id": "",
             "approved_by": "", "approval_status": "PENDING"},
        ]
        self.zk_users = [
            {"device_id": "zk_room_1", "user_id": "0014", "device_display_name": "  محمد   السيد ", "source": "zkteco_get_users"},
            {"device_id": "zk_room_1", "user_id": "9999", "device_display_name": "Unknown", "source": "zkteco_get_users"},
        ]
        self.hik_users = [
            {"device_id": "hik_room_2", "user_id": "41005", "device_display_name": "rashid", "source": "hikvision_user_info_search"},
        ]

    def write(self):
        save_csv(self.roster, self.workers)
        save_csv(self.zk, self.zk_users)
        save_csv(self.hik, self.hik_users)

    def output_rows(self):
        with self.output.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_exact_candidate_but_never_approval(self):
        self.write()
        summary = matching.build_review(self.roster, self.zk, self.hik, self.output)
        rows = self.output_rows()
        self.assertEqual(rows[0]["zk_room_1_user_id"], "0014")
        self.assertEqual(rows[1]["hik_room_2_user_id"], "41005")
        self.assertEqual(rows[0]["approval_status"], "PENDING")
        self.assertEqual(rows[0]["approved_by"], "")
        self.assertEqual(summary["employee_candidates"], 2)
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(self.output.parent.stat().st_mode), 0o700)

    def test_duplicate_employee_names_rejected(self):
        self.workers[1]["employee_name"] = self.workers[0]["employee_name"]
        self.write()
        summary = matching.build_review(self.roster, self.zk, self.hik, self.output)
        self.assertEqual(summary["ambiguous_employees"], 2)
        self.assertEqual(self.output_rows()[0]["zk_room_1_user_id"], "")

    def test_multiple_device_ids_same_name_not_silently_selected(self):
        self.zk_users.append({
            "device_id": "zk_room_1", "user_id": "0045",
            "device_display_name": "محمد السيد", "source": "zkteco_get_users",
        })
        self.write()
        summary = matching.build_review(self.roster, self.zk, self.hik, self.output)
        self.assertEqual(summary["ambiguous_zk"], 1)
        self.assertEqual(self.output_rows()[0]["zk_room_1_user_id"], "")

    def test_wrong_device_csv_refused(self):
        self.zk_users[0]["device_id"] = "hik_room_2"
        self.write()
        with self.assertRaises(ValueError):
            matching.build_review(self.roster, self.zk, self.hik, self.output)
        self.assertFalse(self.output.exists())

    def test_pre_filled_mapping_input_refused(self):
        self.workers[0]["zk_room_1_user_id"] = "999"
        self.write()
        with self.assertRaises(ValueError):
            matching.build_review(self.roster, self.zk, self.hik, self.output)
        self.assertFalse(self.output.exists())

    def test_never_overwrite_reviewer_csv(self):
        self.write()
        matching.build_review(self.roster, self.zk, self.hik, self.output)
        with self.assertRaises(FileExistsError):
            matching.build_review(self.roster, self.zk, self.hik, self.output)


if __name__ == "__main__":
    unittest.main()
