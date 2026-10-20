"""Fail-closed guards for REAL TEST HTTP synthetic test. Does not use HTTP."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"scripts"/"run_dual_target_http_synthetic_e2e.py"
spec=importlib.util.spec_from_file_location("raidat_http_test",SCRIPT)
subject=importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)

class HttpTestSafetyGuards(unittest.TestCase):
    def test_erp_cron_must_be_disabled(self):
        with patch.object(subject,"read_config",return_value={"valid":True,"settings":{
            "db_name":"test","dbfilter":"^test$","max_cron_threads":"1","http_port":"8081"
        }}):
            with self.assertRaisesRegex(RuntimeError,"disable cron"):
                subject._port(subject.ERP_CONF,"test",require_disabled_cron=True)
    def test_bad_dbfilter_is_refused(self):
        with patch.object(subject,"read_config",return_value={"valid":True,"settings":{
            "db_name":"test","dbfilter":"^test_RSH$","max_cron_threads":"0","http_port":"8081"
        }}):
            with self.assertRaisesRegex(RuntimeError,"dbfilter mismatch"):
                subject._port(subject.ERP_CONF,"test",require_disabled_cron=True)
    def test_rsh_existing_one_cron_thread_is_accepted(self):
        with patch.object(subject,"read_config",return_value={"valid":True,"settings":{
            "db_name":"test_RSH","dbfilter":"^test_RSH$","max_cron_threads":"1","http_port":"8070"
        }}):
            self.assertEqual(subject._port(subject.RSH_CONF,"test_RSH",expected=8070),8070)
    def test_event_population_is_exactly_synthetic(self):
        ev=subject.events()
        self.assertEqual(len(ev),4)
        self.assertEqual(len({r["event_key"] for r in ev}),4)
        self.assertTrue(all(r["device_id"] in subject.SYNTH_DEVICE_IDS for r in ev))
        self.assertTrue(all(r["raw"].get("test_only") for r in ev))
    def test_private_token_is_never_read_if_permissions_are_unsafe(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(subject,"TOKEN_DIR",Path(temp)):
            p=Path(temp)/"erp-test-token"
            p.write_text("X"*50,encoding="utf-8")
            p.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError,"permissions"):
                subject._token(p.name)
    def test_refuse_production_listening_port(self):
        with patch.object(subject,"read_config",return_value={"valid":True,"settings":{
            "db_name":"test","dbfilter":"^test$","max_cron_threads":"0","http_port":"8069"
        }}):
            with self.assertRaisesRegex(RuntimeError,"Production HTTP"):
                subject._port(subject.ERP_CONF,"test",require_disabled_cron=True)

if __name__=="__main__":
    unittest.main()
