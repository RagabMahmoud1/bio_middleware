"""Isolated RSH TEST-only synthetic Events API + First/Last E2E.

Run inside Odoo shell connected to db test_RSH:
 exec(open('/odoo16/.local/share/raidat-biometric/run_rsh_test_synthetic_e2e.py', encoding='utf-8').read(), {'env': env, '__name__': '__main__'})

Test writes are deliberate and confined to test_RSH:
 1 fake HR employee, 2 fake biometric devices, 2 fake mappings,
 3 accepted fake raw events (2 on one completed day, one on another),
 1 biometric Attendance from different devices and 1 single-punch error.
No changes to real device IDs, real employee mapping, cron, or Windows middleware.
Preserves synthetic test records as evidence. Does not log API tokens/real IDs.
"""
from datetime import date, timedelta, datetime, time
import http.client
import json
import secrets
import stat
from pathlib import Path

import pytz

DB = "test_RSH"
HOST = "127.0.0.1"
PORT = 8070
TZ = pytz.timezone("Asia/Riyadh")
TOKEN_FILE = Path("/odoo16/.config/raidat-biometric/rsh-test-token")
PREFIX = "RSH_E2E_SYNTH_"
DEVICE_EXTERNAL_IDS = (
    "rsh_e2e_synthetic_zk",
    "rsh_e2e_synthetic_hik",
)


def _assert_test_db(env):
    if env.cr.dbname != DB:
        raise RuntimeError("REFUSED: the E2E can only run in test_RSH")
    required = (
        "asg.biometric.device", "asg.biometric.employee.mapping",
        "asg.biometric.raw.event", "hr.employee", "hr.attendance",
    )
    for name in required:
        try:
            env[name]
        except KeyError:
            raise RuntimeError("Required RSH TEST model missing")
    if not hasattr(env["asg.biometric.raw.event"], "action_process_selected_first_last"):
        raise RuntimeError("First/Last addon not available on Test")


def _private_token():
    if TOKEN_FILE.is_symlink() or not TOKEN_FILE.is_file():
        raise RuntimeError("RSH TEST token missing")
    if stat.S_IMODE(TOKEN_FILE.stat().st_mode) & 0o077:
        raise RuntimeError("RSH TEST token permissions unsafe")
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("RSH TEST token length insufficient")
    return token


def _request_events(payload, token):
    conn = http.client.HTTPConnection(HOST, PORT, timeout=15)
    try:
        conn.request(
            "POST", "/biometric/api/v1/events?db=test_RSH",
            body=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Host": "localhost:8070",
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        response = conn.getresponse()
        body = response.read(65537)
        if len(body) > 65536:
            raise RuntimeError("RSH TEST API returned oversized response")
        try:
            response_json = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise RuntimeError("RSH TEST API returned non-JSON response")
        if not isinstance(response_json, dict):
            raise RuntimeError("RSH TEST API returned an invalid JSON object")
        return response.status, response_json
    finally:
        conn.close()


def _event(key, device_id, code, when):
    return {
        "event_key": key,
        "device_id": device_id,
        "employee_code": code,
        "event_time": when,
        "event_type": "synthetic-e2e",
        "raw": {"test_only": True, "synthetic": True},
    }


def _assert_accepted(result, expected_keys):
    status, response = result
    if status != 200 or response.get("ok") is not True:
        raise RuntimeError("RSH TEST API failed to accept synthetic request")
    actual = response.get("accepted_event_keys")
    if not isinstance(actual, list) or set(actual) != set(expected_keys):
        raise RuntimeError("RSH TEST API accepted unexpected number of synthetic events")
    if response.get("ignored_event_keys") or response.get("rejected"):
        raise RuntimeError("RSH TEST API ignored or rejected synthetic mapped event")


def _completed_dates():
    # Choose completed Riyadh days relative to run date, not the current day.
    today = datetime.now(TZ).date()
    return today - timedelta(days=3), today - timedelta(days=2)


def run(env):
    _assert_test_db(env)
    token = _private_token()

    Device = env["asg.biometric.device"].sudo()
    Employee = env["hr.employee"].sudo()
    Mapping = env["asg.biometric.employee.mapping"].sudo()
    Raw = env["asg.biometric.raw.event"].sudo()
    Attendance = env["hr.attendance"].sudo()

    # Fail closed rather than mixing synthetic E2E with prior test records.
    if Raw.search_count([]):
        raise RuntimeError("REFUSED: RSH Test already contains Raw Events; inspect existing test data first")
    if Device.with_context(active_test=False).search([
        ("external_id", "in", list(DEVICE_EXTERNAL_IDS))
    ]):
        raise RuntimeError("REFUSED: reserved E2E device IDs already exist; no overwrite")

    production_devices = Device.search([
        ("external_id", "in", ["zk_room_1", "hik_room_2"]),
        ("active", "=", True),
    ])
    if (len(production_devices) != 2 or
        len(set(production_devices.mapped("company_id").ids)) != 1):
        raise RuntimeError("REFUSED: RSH TEST expected source device configuration missing")
    company = production_devices[0].company_id

    # Check the existing real-device mapping baseline but do not touch it.
    real_mapping_counts = {
        external_id: Mapping.search_count([
            ("device_id", "=", Device.search([
                ("external_id", "=", external_id),
                ("active", "=", True)
            ], limit=1).id),
            ("active", "=", True),
        ])
        for external_id in ("zk_room_1", "hik_room_2")
    }
    if real_mapping_counts != {"zk_room_1": 19, "hik_room_2": 46}:
        raise RuntimeError("REFUSED: baseline real-device mappings changed")

    nonce = secrets.token_hex(7)
    synthetic_name = PREFIX + nonce
    code = PREFIX + "USER_" + nonce
    test_days = _completed_dates()
    print("TEST_DB=test_RSH baseline RawEvents=0 mappings ZK=19 Hik=46")
    print("Creating isolated synthetic employee and synthetic device pair...")

    # Test-only bootstrap is committed so the independent HTTP request can read it.
    employee = Employee.create({
        "name": synthetic_name,
        "company_id": company.id,
        "active": True,
    })
    devices = Device.create([
        {
            "name": PREFIX + "DEVICE_ZK",
            "external_id": DEVICE_EXTERNAL_IDS[0],
            "device_type": "zkteco",
            "processing_strategy": "raw_only",
            "company_id": company.id,
            "active": True,
        },
        {
            "name": PREFIX + "DEVICE_HIK",
            "external_id": DEVICE_EXTERNAL_IDS[1],
            "device_type": "hikvision",
            "processing_strategy": "raw_only",
            "company_id": company.id,
            "active": True,
        },
    ])
    Mapping.create([
        {"device_id": d.id, "employee_id": employee.id, "external_user_id": code,
         "active": True}
        for d in devices
    ])
    env.cr.commit()

    # Event dates in Asia/Riyadh: same employee, two devices, one completed day.
    main_day, single_day = test_days
    def as_iso(local_day, hour, minute):
        return TZ.localize(datetime.combine(local_day, time(hour, minute))).isoformat()

    first_key = PREFIX + "FIRST_" + nonce
    last_key = PREFIX + "LAST_" + nonce
    single_key = PREFIX + "SINGLE_" + nonce
    first = _event(first_key, DEVICE_EXTERNAL_IDS[0], code, as_iso(main_day, 8, 15))
    last = _event(last_key, DEVICE_EXTERNAL_IDS[1], code, as_iso(main_day, 17, 15))
    single = _event(single_key, DEVICE_EXTERNAL_IDS[0], code, as_iso(single_day, 9, 0))
    keys = [first_key, last_key, single_key]

    _assert_accepted(_request_events({"events": [first, last, single]}, token), keys)
    print("E2E Events API: 3 synthetic events accepted (2 on same day across both devices)")
    _assert_accepted(_request_events({"events": [first, last, single]}, token), keys)
    print("E2E Idempotency: re-sending 3 events acknowledged without duplication")

    env.invalidate_all()
    rows = Raw.search([("event_key", "in", keys)], order="event_time asc")
    if len(rows) != 3 or len(set(rows.mapped("event_key"))) != 3:
        raise RuntimeError("E2E Raw Event count mismatch")
    if set(rows.mapped("employee_id").ids) != {employee.id}:
        raise RuntimeError("E2E Raw Events assigned to wrong employee")
    if set(rows.mapped("device_id").ids) != set(devices.ids):
        raise RuntimeError("E2E Raw Events not collected from two synthetic devices")

    # Target ONLY these synthetic rows. Never invoke the global cron.
    rows.action_process_selected_first_last()
    env.cr.commit()
    env.invalidate_all()

    rows = Raw.search([("event_key", "in", keys)])
    generated = Attendance.search([
        ("employee_id", "=", employee.id),
        ("asg_biometric_generated", "=", True),
        ("asg_biometric_local_date", "=", main_day),
    ])
    singles = Attendance.search([
        ("employee_id", "=", employee.id),
        ("asg_biometric_local_date", "=", single_day),
    ])
    main_rows = rows.filtered(
        lambda item: item.event_key in (first_key, last_key)
    )
    single_row = rows.filtered(lambda item: item.event_key == single_key)
    if (len(generated) != 1 or len(singles) != 0 or
        len(main_rows) != 2 or len(single_row) != 1):
        raise RuntimeError("E2E First/Last generated unexpected number of records")

    expected_first = datetime.combine(main_day, time(5, 15))
    expected_last = datetime.combine(main_day, time(14, 15))
    if generated.check_in != expected_first or generated.check_out != expected_last:
        raise RuntimeError("E2E First/Last UTC conversion wrong")
    if any(r.attendance_id.id != generated.id or r.state != "processed"
           for r in main_rows):
        raise RuntimeError("E2E main-day raw event link failed")
    if (single_row.state != "error" or
        not (single_row.error_message or "").startswith("FIRST_LAST_SINGLE_PUNCH") or
        single_row.attendance_id):
        raise RuntimeError("E2E single-punch test created invalid Attendance")

    print("E2E First/Last: one Attendance, correct Riyadh 08:15/17:15, two devices PASS")
    print("E2E single-punch previous day: no Attendance; FIRST_LAST_SINGLE_PUNCH PASS")

    rows.action_process_selected_first_last()
    env.cr.commit()
    env.invalidate_all()
    if Attendance.search_count([
        ("employee_id", "=", employee.id),
        ("asg_biometric_generated", "=", True),
    ]) != 1:
        raise RuntimeError("E2E rerun duplicated Attendance")

    if {external_id: Mapping.search_count([
        ("device_id", "=", Device.search([
            ("external_id", "=", external_id),
            ("active", "=", True)
        ], limit=1).id),
        ("active", "=", True),
    ]) for external_id in ("zk_room_1", "hik_room_2")} != real_mapping_counts:
        raise RuntimeError("E2E modified real-device mappings")

    print("E2E processing rerun: no duplicate Attendance PASS")
    print("Real-device mappings unchanged: ZK=19 Hik=46 PASS")
    print("RESULT: PASS — RSH TEST synthetic Events API + First/Last end-to-end")
    print("Synthetic employee/devices/events/attendance preserved ONLY in test_RSH for audit")
    print("No real employee attendance, Windows middleware, or cron modified.")
    return True


if __name__ == "__main__":
    if "env" not in globals():
        raise RuntimeError("Run in RSH TEST Odoo shell with env")
    run(globals()["env"])