"""Unit tests for the safe RSH events API probe."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

FILE=Path(__file__).resolve().parents[1]/"scripts"/"check_rsh_test_events_api_safe.py"
spec=importlib.util.spec_from_file_location("safe_rsh_events_probe",FILE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class Tests(unittest.TestCase):
    def test_http_local_test_db_post_only(self):
        mock=MagicMock()
        response=MagicMock(status=401)
        response.read.return_value=b'{"ok":false,"error":"unauthorized"}'
        mock.getresponse.return_value=response
        with patch.object(mod.http.client,"HTTPConnection",return_value=mock) as cn:
            status,payload=mod.post_events("INVALID",{"events":[]})
        self.assertEqual(status,401)
        self.assertEqual(payload["error"],"unauthorized")
        cn.assert_called_once_with("127.0.0.1",8070,timeout=8)
        call=mock.request.call_args
        self.assertEqual(call.args[0],"POST")
        self.assertEqual(call.args[1],"/biometric/api/v1/events?db=test_RSH")
        self.assertIn("INVALID",call.kwargs["headers"]["Authorization"])

    def test_only_three_safe_cases_and_second_ignored(self):
        calls=[]
        def fake(token,payload):
            calls.append((token,payload))
            if token.startswith("invalid"):
                return 401,{"ok":False,"error":"unauthorized"}
            if isinstance(payload["events"],str):
                return 400,{"ok":False,"error":"events_must_be_a_list"}
            item=payload["events"][0]
            return 200,{"ok":True,"accepted_event_keys":[],"ignored_event_keys":[item["event_key"]],
                        "ignored":[{"event_key":item["event_key"],"reason":"unknown_employee"}],
                        "rejected":[]}
        with patch.object(mod,"private_token",return_value="test-token"),patch.object(mod,"post_events",side_effect=fake):
            self.assertEqual(mod.main(),0)
        self.assertEqual(len(calls),4)
        self.assertEqual(calls[2][1]["events"][0],calls[3][1]["events"][0])
        self.assertEqual(calls[2][1]["events"][0]["device_id"],"zk_room_1")
        self.assertTrue(calls[2][1]["events"][0]["employee_code"].startswith("RSH_TEST_NONEXISTENT_"))

    def test_unexpected_acceptance_blocks(self):
        def fake(token,payload):
            if token.startswith("invalid"):
                return 401,{"error":"unauthorized"}
            if isinstance(payload["events"],str):
                return 400,{"error":"events_must_be_a_list"}
            return 200,{"ok":True,"accepted_event_keys":["SOME_ID"],"ignored_event_keys":[],"rejected":[]}
        with patch.object(mod,"private_token",return_value="token"),patch.object(mod,"post_events",side_effect=fake):
            with self.assertRaisesRegex(RuntimeError,"accepted"):
                mod.main()

    def test_invalid_wrong_token_response_blocks(self):
        def fake(token,payload):
            return 200,{"ok":True}
        with patch.object(mod,"private_token",return_value="token"),patch.object(mod,"post_events",side_effect=fake):
            with self.assertRaisesRegex(RuntimeError,"HTTP status"):
                mod.main()

if __name__=="__main__":
    unittest.main()
