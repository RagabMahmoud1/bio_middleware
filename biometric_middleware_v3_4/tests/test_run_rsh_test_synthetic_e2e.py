"""Contract unit tests for RSH synthetic E2E isolation and HTTP ACK semantics."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest
from datetime import datetime

TARGET=Path(__file__).resolve().parents[1] / "scripts" / "run_rsh_test_synthetic_e2e.py"
spec=importlib.util.spec_from_file_location("rsh_synthetic_e2e",TARGET)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Env:
    def __init__(self,db):
        self.cr=SimpleNamespace(dbname=db)
        self.models={
            "asg.biometric.device":object(),
            "asg.biometric.employee.mapping":object(),
            "asg.biometric.raw.event":SimpleNamespace(action_process_selected_first_last=True),
            "hr.employee":object(),
            "hr.attendance":object()
        }
    def __getitem__(self,n):
        return self.models[n]

class RshSyntheticE2ETests(unittest.TestCase):
    def test_refuses_live_db(self):
        with self.assertRaisesRegex(RuntimeError,"test_RSH"):
            mod._assert_test_db(Env("rsh"))

    def test_test_db_requires_first_last(self):
        env=Env("test_RSH")
        mod._assert_test_db(env)
        del env.models["asg.biometric.raw.event"].action_process_selected_first_last
        with self.assertRaisesRegex(RuntimeError,"First/Last"):
            mod._assert_test_db(env)

    def test_synthetic_device_ids_do_not_reuse_real_device_ids(self):
        self.assertTrue(all(d.startswith("rsh_e2e_synthetic_") for d in mod.DEVICE_EXTERNAL_IDS))
        self.assertEqual(set(mod.DEVICE_EXTERNAL_IDS).intersection({"zk_room_1","hik_room_2"}),set())
        self.assertNotEqual(mod.DEVICE_EXTERNAL_IDS[0],mod.DEVICE_EXTERNAL_IDS[1])

    def test_event_has_synthetic_marker(self):
        event=mod._event("test-key",mod.DEVICE_EXTERNAL_IDS[0],"RSH_E2E_SYNTH_USER", "2026-10-18T08:15:00+03:00")
        self.assertEqual(event["raw"],{"test_only":True,"synthetic":True})
        self.assertEqual(event["event_key"],"test-key")
        self.assertNotIn("employee_id",event)

    def test_dates_are_completed_in_riyadh(self):
        days=mod._completed_dates()
        self.assertEqual((days[1]-days[0]).days,1)
        self.assertLess(days[1],datetime.now(mod.TZ).date())

    def test_ack_rejects_ignored_or_rejected(self):
        mod._assert_accepted((200,{"ok":True,"accepted_event_keys":["a","b"],"ignored_event_keys":[],"rejected":[]}),["a","b"])
        with self.assertRaisesRegex(RuntimeError,"ignored or rejected"):
            mod._assert_accepted((200,{"ok":True,"accepted_event_keys":["a"],"ignored_event_keys":["b"],"rejected":[]}),["a"])
        with self.assertRaisesRegex(RuntimeError,"unexpected number"):
            mod._assert_accepted((200,{"ok":True,"accepted_event_keys":["b"],"ignored_event_keys":[],"rejected":[]}),["a"])

    def test_post_only_to_localhost_test_endpoint(self):
        fake=MagicMock()
        response=MagicMock(status=200)
        response.read.return_value=b'{"ok":true,"accepted_event_keys":[],"ignored_event_keys":[],"rejected":[]}'
        fake.getresponse.return_value=response
        with patch.object(mod.http.client,"HTTPConnection",return_value=fake) as connection:
            status, body=mod._request_events({"events":[]},"test-token")
        self.assertEqual(status,200)
        connection.assert_called_once_with("127.0.0.1",8070,timeout=15)
        request=fake.request.call_args
        self.assertEqual(request.args[0],"POST")
        self.assertEqual(request.args[1],"/biometric/api/v1/events?db=test_RSH")
        self.assertEqual(request.kwargs["headers"]["Host"],"localhost:8070")

if __name__=="__main__":
    unittest.main()
