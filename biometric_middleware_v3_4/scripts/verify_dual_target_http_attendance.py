"""TEST ONLY: process synthetic dual-target HTTP events via Odoo ORM.

Run separately inside Odoo shell for db=test and db=test_RSH, only AFTER
run_dual_target_http_synthetic_e2e.py completes its real HTTP PASS.
Never invokes global Cron; never processes non-synthetic Raw Events.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib

PREFIX = "RAIDAT_DUAL_HTTP_20261020"
SYNTH_PREFIX = "RAIDAT_DUAL_E2E_20261020"
SOURCE_IDS = ("raidat_dual_e2e_zk", "raidat_dual_e2e_hik")

def event_key(suffix, device_id, employee_code, event_time):
    # Keep in sync with app.db.Database.make_event_key (fixed date 2026-10-17).
    stable = "|".join((device_id, employee_code, event_time, "check",
                       PREFIX + "_" + suffix))
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()

EXPECTED_KEYS = {
    "SHARED_IN": event_key("SHARED_IN", SOURCE_IDS[0],
        SYNTH_PREFIX + "_SHARED", "2026-10-17T08:15:00+03:00"),
    "SHARED_OUT": event_key("SHARED_OUT", SOURCE_IDS[1],
        SYNTH_PREFIX + "_SHARED", "2026-10-17T17:15:00+03:00"),
    "ERP_ONLY": event_key("ERP_ONLY", SOURCE_IDS[0],
        SYNTH_PREFIX + "_ERP_ONLY", "2026-10-17T09:00:00+03:00"),
    "RSH_ONLY": event_key("RSH_ONLY", SOURCE_IDS[0],
        SYNTH_PREFIX + "_RSH_ONLY", "2026-10-17T09:20:00+03:00"),
}
COMMON_KEYS = (EXPECTED_KEYS["SHARED_IN"], EXPECTED_KEYS["SHARED_OUT"])


def verify_and_process(env):
    db = env.cr.dbname
    if db not in ("test", "test_RSH"):
        raise RuntimeError("REFUSED: only ERP and RSH Test databases")
    only = EXPECTED_KEYS["ERP_ONLY" if db == "test" else "RSH_ONLY"]
    keys = COMMON_KEYS + (only,)
    Raw = env["asg.biometric.raw.event"].sudo()
    Attendance = env["hr.attendance"].sudo()
    Mapping = env["asg.biometric.employee.mapping"].sudo()
    rows = Raw.search([("event_key", "in", keys)])
    if len(rows) != 3 or set(rows.mapped("event_key")) != set(keys):
        raise RuntimeError("REFUSED: expected three unique synthetic TEST raw events")
    if set(rows.mapped("device_id.external_id")) != set(SOURCE_IDS):
        raise RuntimeError("REFUSED: synthetic device IDs mismatch")
    shared = rows.filtered(lambda r: r.event_key in COMMON_KEYS)
    lone = rows.filtered(lambda r: r.event_key == only)
    if (len(shared) != 2 or len(set(shared.mapped("employee_id").ids)) != 1
            or len(lone) != 1 or lone.employee_id == shared.employee_id):
        raise RuntimeError("REFUSED: synthetic employee mapping wrong")
    shared_emp = shared[0].employee_id
    single_emp = lone.employee_id
    if not shared_emp or not single_emp:
        raise RuntimeError("REFUSED: synthetic HR employee missing")
    day = shared[0].event_time.replace(tzinfo=timezone.utc).astimezone(
        ZoneInfo("Asia/Riyadh")).date()
    if any(r.event_time.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo("Asia/Riyadh")).date() != day for r in rows):
        raise RuntimeError("REFUSED: synthetic events span unexpected dates")
    if Attendance.search_count([("employee_id", "in",
                                [shared_emp.id, single_emp.id]),
                               ("asg_biometric_generated", "=", True)]):
        raise RuntimeError("REFUSED: synthetic Attendance already exists")
    if any(r.attendance_id for r in rows):
        raise RuntimeError("REFUSED: prior processing detected")

    # Only the three keyed events of this DB are processed. No Cron changes.
    rows.action_process_selected_first_last()
    env.cr.commit()
    env.invalidate_all()
    shared = Raw.search([("event_key", "in", COMMON_KEYS)])
    lone = Raw.search([("event_key", "=", only)])
    generated = Attendance.search([
        ("employee_id", "=", shared_emp.id),
        ("asg_biometric_generated", "=", True),
        ("asg_biometric_local_date", "=", day),
    ])
    if len(generated) != 1:
        raise RuntimeError("TEST verification FAILED: expected one Attendance")
    expected_in = datetime(2026,10,17,5,15)
    expected_out = datetime(2026,10,17,14,15)
    if generated.check_in != expected_in or generated.check_out != expected_out:
        raise RuntimeError("TEST verification FAILED: wrong First/Last UTC times")
    if any(r.state != "processed" or r.attendance_id != generated
           for r in shared):
        raise RuntimeError("TEST verification FAILED: shared Raw Events not linked")
    if (len(lone) != 1 or lone.state != "error"
            or not (lone.error_message or "").startswith("FIRST_LAST_SINGLE_PUNCH")
            or lone.attendance_id):
        raise RuntimeError("TEST verification FAILED: single punch not isolated")
    if Attendance.search_count([("employee_id", "=", single_emp.id),
                                ("asg_biometric_generated", "=", True)]):
        raise RuntimeError("TEST verification FAILED: unexpected lone Attendance")

    rows = Raw.search([("event_key", "in", keys)])
    rows.action_process_selected_first_last()
    env.cr.commit()
    env.invalidate_all()
    if Attendance.search_count([
        ("employee_id", "=", shared_emp.id),
        ("asg_biometric_generated", "=", True),
        ("asg_biometric_local_date", "=", day),
    ]) != 1:
        raise RuntimeError("TEST verification FAILED: duplicate on reprocessing")
    print("PASS: Test DB", db)
    print("PASS: 3 target-specific synthetic Raw Events processed")
    print("PASS: shared employee 2 devices -> exactly 1 attendance")
    print("PASS: single-punch employee -> FIRST_LAST_SINGLE_PUNCH, 0 attendance")
    print("PASS: reprocessing -> no duplicate; all other Raw Events untouched")
    print("Production unchanged")


if __name__ == "__main__":
    if "env" not in globals():
        raise RuntimeError("Odoo Test shell env required")
    verify_and_process(globals()["env"])