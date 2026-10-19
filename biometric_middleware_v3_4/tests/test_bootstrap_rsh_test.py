"""Tests for idempotent, fail-closed RSH TEST bootstrap. No Odoo connection needed."""
import contextlib
import io
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.bootstrap_rsh_test_odoo import bootstrap_rsh_test


class FakeModules:
    def sudo(self):
        return self

    def search(self, domain, limit=1):
        return [True]


class FakeCompanies:
    def sudo(self):
        return self

    def search(self, domain):
        return [SimpleNamespace(
            id=1, name="RAIDAT AL SHARQ FACTORY FOR METAL PRODUCTION ESTABLISHMENT"
        )]


class FakeDevices:
    def __init__(self):
        self.records = {}

    def sudo(self):
        return self

    def search(self, domain, limit=2):
        eid = next(v for k, op, v in domain if k == "external_id")
        return [self.records[eid]] if eid in self.records else []

    def create(self, values):
        for v in values:
            self.records[v["external_id"]] = SimpleNamespace(
                company_id=SimpleNamespace(id=v["company_id"]),
                device_type=v["device_type"],
                processing_strategy=v["processing_strategy"],
                active=v["active"],
            )


class FakeParams:
    def __init__(self):
        self.values = {"asg_biometric_first_last.timezone": "Asia/Riyadh"}

    def sudo(self):
        return self

    def get_param(self, key):
        return self.values.get(key)

    def set_param(self, key, value):
        self.values[key] = value


class FakeCursor:
    def __init__(self, db):
        self.dbname = db
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeEnv:
    def __init__(self, db="test_RSH"):
        self.cr = FakeCursor(db)
        self.modules = FakeModules()
        self.company = FakeCompanies()
        self.devices = FakeDevices()
        self.params = FakeParams()

    def __getitem__(self, key):
        return {
            "ir.module.module": self.modules,
            "res.company": self.company,
            "asg.biometric.device": self.devices,
            "ir.config_parameter": self.params,
        }[key]


class BootstrapTest(unittest.TestCase):
    def test_refuse_any_production_or_unexpected_db_before_access(self):
        for name in ("rsh.raidatalsharq.com", "erp.raidatalsharq.com", "test", "postgres"):
            env = FakeEnv(name)
            with self.assertRaisesRegex(RuntimeError, "REFUSED"):
                bootstrap_rsh_test(env)
            self.assertEqual(env.cr.commits, 0)

    def test_creates_two_devices_and_private_token_without_printing_secret(self):
        env = FakeEnv()
        with tempfile.TemporaryDirectory() as td:
            with patch("scripts.bootstrap_rsh_test_odoo.Path.home", return_value=Path(td)):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    bootstrap_rsh_test(env)
                token = env.params.values["asg_biometric.api_token"]
                private_file = Path(td) / ".config/raidat-biometric/rsh-test-token"
                self.assertTrue(private_file.exists())
                self.assertEqual(private_file.read_text().strip(), token)
                self.assertEqual(stat.S_IMODE(private_file.stat().st_mode), 0o600)
                self.assertNotIn(token, stdout.getvalue())
                self.assertEqual(env.cr.commits, 1)
                self.assertEqual(set(env.devices.records), {"zk_room_1", "hik_room_2"})
                self.assertEqual(env.devices.records["zk_room_1"].processing_strategy, "raw_only")
                with contextlib.redirect_stdout(stdout):
                    bootstrap_rsh_test(env)
                self.assertEqual(env.params.values["asg_biometric.api_token"], token)
                self.assertEqual(len(env.devices.records), 2)
                self.assertEqual(env.cr.commits, 2)

    def test_reject_conflicting_existing_device_without_commit(self):
        env = FakeEnv()
        env.devices.records["zk_room_1"] = SimpleNamespace(
            company_id=SimpleNamespace(id=999),
            device_type="zkteco", processing_strategy="raw_only", active=True
        )
        with self.assertRaisesRegex(RuntimeError, "Conflicting"):
            bootstrap_rsh_test(env)
        self.assertEqual(env.cr.commits, 0)


if __name__ == "__main__":
    unittest.main()
