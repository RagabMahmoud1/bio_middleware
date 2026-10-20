"""Read-only local HTTP check of RSH TEST Allowed Employees API.

Run on the Linux Odoo TEST host as user odoo16, not inside Odoo shell.
Only connects to 127.0.0.1:8070, GET, with explicit db=test_RSH.
Never prints or stores API token or employee IDs. No Odoo writes.
"""
import http.client
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import urlencode

DB = "test_RSH"
HOST = "127.0.0.1"
PORT = 8070
SECRET_PATH = Path("/odoo16/.config/raidat-biometric/rsh-test-token")
EXPECTED = {"zk_room_1": 19, "hik_room_2": 46}


def load_test_token():
    if SECRET_PATH.is_symlink() or not SECRET_PATH.is_file():
        raise RuntimeError("Test-only token file is absent or unsafe")
    mode = stat.S_IMODE(SECRET_PATH.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError("Test token must be owner-readable only")
    token = SECRET_PATH.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("Test token length is insufficient")
    return token


def fetch_allowed(device_id, token):
    query = urlencode({"db": DB, "device_id": device_id})
    url = "/biometric/api/v1/allowed-employees?" + query
    conn = http.client.HTTPConnection(HOST, PORT, timeout=8)
    try:
        conn.request("GET", url, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Host": "localhost:8070",
        })
        response = conn.getresponse()
        # Cap response size and avoid logging raw body, which contains employee IDs.
        body = response.read(65537)
        if len(body) > 65536:
            raise RuntimeError("API response exceeded safe size")
        return response.status, body
    finally:
        conn.close()


def parse_allowed_response(device_id, expected_count, status, body):
    if status != 200:
        raise RuntimeError("Allowed Employees returned HTTP " + str(status))
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise RuntimeError("Allowed Employees returned non-JSON content")
    if not isinstance(data, dict):
        raise RuntimeError("API returned an invalid object")
    if data.get("ok") is not True or data.get("device_id") != device_id:
        raise RuntimeError("API returned unexpected database/device payload")
    ids = data.get("allowed_employee_ids")
    if not isinstance(ids, list) or not all(isinstance(x, str) and x.strip() for x in ids):
        raise RuntimeError("API response has malformed employee IDs")
    if len(set(ids)) != len(ids):
        raise RuntimeError("API returned duplicate device IDs")
    if data.get("count") != len(ids) or len(ids) != expected_count:
        raise RuntimeError("API count does not match verified RSH Test ORM mapping count")
    return len(ids)


def main():
    token = load_test_token()
    for device_id, expected_count in EXPECTED.items():
        # Negative auth check first. Never log response body.
        rejected_status, _ = fetch_allowed(device_id, "invalid-test-auth-probe")
        if rejected_status != 401:
            raise RuntimeError(
                "Negative-auth test did not yield HTTP 401 for " + device_id
                + " (HTTP " + str(rejected_status) + ")"
            )
        status, body = fetch_allowed(device_id, token)
        count = parse_allowed_response(device_id, expected_count, status, body)
        print("TEST DB=%s device=%s unauthorized=401 authorized=200 allowed_count=%d PASS" %
              (DB, device_id, count))
    print("RESULT: PASS — both TEST allowed-employees GET endpoints match ORM counts")
    print("No attendance/event POST, no Odoo writes, no employee IDs or tokens printed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        # Never print exception payload from http.client, URLs, or tokens.
        print("RESULT: BLOCKED —", str(exc))
        print("Do not infer success or change Production settings.")
        sys.exit(2)
