"""Tests for safe TEST environment audit helpers (no server calls)."""
import importlib.util
import tempfile
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_dual_odoo_test_readonly.py"
spec = importlib.util.spec_from_file_location("raidat_readonly_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

class ReadonlyAuditTests(unittest.TestCase):
    def test_no_password_or_api_token_config_export(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.conf"
            p.write_text("[options]\nhttp_port = 8081\ndb_name = test\ndbfilter = ^test$\nmax_cron_threads=0\nadmin_passwd = DONTLEAK\nasg_biometric.api_token = DONTLEAK\n", encoding="utf-8")
            out = audit.read_config(str(p))
            self.assertTrue(out["valid"])
            self.assertEqual(out["settings"]["db_name"], "test")
            self.assertNotIn("DONTLEAK", str(out))
            self.assertNotIn("admin_passwd", str(out))
            self.assertNotIn("api_token", str(out))
    def test_missing_config_stays_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(audit.read_config(str(Path(d) / "missing.conf")), {"present": False})
    def test_module_source_found_only_under_addons_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fake_module"
            p.mkdir()
            (p / "__manifest__.py").write_text("{'version':'16.0.1','depends':['hr_attendance'],'installable':True}", encoding="utf-8")
            got = audit.module_source(d, "fake_module")
            self.assertEqual(got["version"], "16.0.1")
            self.assertEqual(got["depends"], ["hr_attendance"])
            self.assertIsNone(audit.module_source(d, "missing_module"))
    def test_invalid_database_cannot_be_queried(self):
        self.assertFalse(audit.pg_query("test;DROP", audit.MODULE_SQL)["ok"])

if __name__ == "__main__":
    unittest.main()
