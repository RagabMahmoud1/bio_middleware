"""Unit tests for read-only RSH TEST HTTP Allowed Employees probe."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

TARGET=Path(__file__).resolve().parents[1] / "scripts" / "check_rsh_test_allowed_api.py"
spec=importlib.util.spec_from_file_location("rsh_allowed_probe", TARGET)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class AllowedProbeTests(unittest.TestCase):
    def test_valid_count_with_leading_zero_strings(self):
        body=b'{"ok":true,"device_id":"zk_room_1","count":2,"allowed_employee_ids":["0001","0042"]}'
        self.assertEqual(mod.parse_allowed_response("zk_room_1",2,200,body),2)

    def test_count_mismatch_rejected(self):
        body=b'{"ok":true,"device_id":"hik_room_2","count":1,"allowed_employee_ids":["0001"]}'
        with self.assertRaisesRegex(RuntimeError, "count"):
            mod.parse_allowed_response("hik_room_2",46,200,body)

    def test_duplicate_id_rejected(self):
        body=b'{"ok":true,"device_id":"zk_room_1","count":2,"allowed_employee_ids":["0001","0001"]}'
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            mod.parse_allowed_response("zk_room_1",2,200,body)

    def test_unexpected_device_rejected(self):
        body=b'{"ok":true,"device_id":"other","count":1,"allowed_employee_ids":["1"]}'
        with self.assertRaisesRegex(RuntimeError, "database/device"):
            mod.parse_allowed_response("zk_room_1",1,200,body)

    def test_failed_http_status_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
            mod.parse_allowed_response("zk_room_1",19,302,b"")

    def test_request_is_get_localhost_with_test_db_and_no_redirect(self):
        fake=MagicMock()
        response=MagicMock(status=401)
        response.read.return_value=b'{"ok":false}'
        fake.getresponse.return_value=response
        with patch.object(mod.http.client, "HTTPConnection", return_value=fake) as conn:
            code, body=mod.fetch_allowed("zk_room_1","invalid-test-auth-probe")
        self.assertEqual(code,401)
        self.assertEqual(body,b'{"ok":false}')
        conn.assert_called_once_with("127.0.0.1",8070,timeout=8)
        args,kwargs=fake.request.call_args
        self.assertEqual(args[0],"GET")
        self.assertIn("db=test_RSH",args[1])
        self.assertIn("device_id=zk_room_1",args[1])
        self.assertEqual(kwargs["headers"]["Host"],"localhost:8070")


if __name__ == "__main__":
    unittest.main()
