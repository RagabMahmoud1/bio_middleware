"""Test RSH Events API without creating biometric raw events.

Requires valid TEST token from private file; sends ONLY:
- invalid-token POST (401 expected),
- valid-token malformed payload (400 expected),
- valid-token fabricated unmapped employee event (ignored expected),
- same fabricated event again (ignored, no persistence expected).
Never sends events for any user ID present on the real devices.
Never prints IDs or token; does not touch middleware service or SQLite.
"""
import http.client
import json
import secrets
import stat
import sys
from pathlib import Path

DB = "test_RSH"
HOST = "127.0.0.1"
PORT = 8070
PATH = "/biometric/api/v1/events?db=test_RSH"
TOKEN_PATH = Path("/odoo16/.config/raidat-biometric/rsh-test-token")


def private_token():
    if TOKEN_PATH.is_symlink() or not TOKEN_PATH.is_file():
        raise RuntimeError("Private RSH TEST API token file unavailable")
    if stat.S_IMODE(TOKEN_PATH.stat().st_mode) & 0o077:
        raise RuntimeError("RSH TEST API token file has unsafe permissions")
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("RSH TEST API token is too short")
    return token


def post_events(token, payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    conn = http.client.HTTPConnection(HOST, PORT, timeout=8)
    try:
        conn.request("POST", PATH, body=body, headers={
            "Host": "localhost:8070",
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        resp = conn.getresponse()
        content = resp.read(65537)
        if len(content) > 65536:
            raise RuntimeError("Unexpected oversized API response")
        try:
            result = json.loads(content.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise RuntimeError("API returned non-JSON response")
        if not isinstance(result, dict):
            raise RuntimeError("API response is not a JSON object")
        return resp.status, result
    finally:
        conn.close()


def check_response(status, body, expected_status, error=None):
    if status != expected_status:
        raise RuntimeError("Unexpected HTTP status: " + str(status))
    if error and body.get("error") != error:
        raise RuntimeError("Unexpected error type in response")
    return True


def main():
    token = private_token()
    status, body = post_events("invalid-test-auth-probe", {"events": []})
    check_response(status, body, 401, "unauthorized")
    print("RSH TEST events wrong token: HTTP 401 PASS")

    status, body = post_events(token, {"events": "not-a-list"})
    check_response(status, body, 400, "events_must_be_a_list")
    print("RSH TEST events malformed list: HTTP 400 PASS")

    nonce = secrets.token_hex(20)
    key = "RSH_TEST_UNMAPPED_NO_WRITE_" + nonce
    employee_code = "RSH_TEST_NONEXISTENT_" + nonce
    event = {
        "event_key": key,
        "device_id": "zk_room_1",
        "employee_code": employee_code,
        "event_time": "2026-10-18T10:00:00+03:00",
        "event_type": "test_unmapped",
        "raw": {"test_only": True},
    }
    for attempt in (1, 2):
        status, body = post_events(token, {"events": [event]})
        if status != 200 or body.get("ok") is not True:
            raise RuntimeError("Unmapped event returned incorrect success status")
        if body.get("accepted_event_keys") != []:
            raise RuntimeError("Unmapped event was unexpectedly accepted")
        if body.get("ignored_event_keys") != [key]:
            raise RuntimeError("Unmapped event not ignored")
        if body.get("rejected") != []:
            raise RuntimeError("Unexpected rejected events")
        if body.get("ignored") != [{"event_key": key, "reason": "unknown_employee"}]:
            raise RuntimeError("Unmapped reason did not match expected behavior")
        print("RSH TEST unmapped synthetic event attempt %d: HTTP 200 IGNORE PASS" % attempt)

    print("RESULT: PASS — RSH TEST API auth, payload validation, unmapped filtering")
    print("No real device User ID used; no accepted event sent; no attendance processing.")
    print("NEXT: separately verify RawEvent row counts through test_RSH ORM.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError) as exc:
        # Exceptions here are self-authored, never contain employee IDs or tokens.
        print("RESULT: BLOCKED —", type(exc).__name__, str(exc))
        sys.exit(2)
