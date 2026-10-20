"""RSH TEST-only importer for PROVISIONAL exact-name device mappings.

Default is read-only preview. Apply requires an explicit function call with
apply=True and confirm="IMPORT-PROVISIONAL-ON-test_RSH". No Attendance or cron
is touched. Provisional mappings are NOT validated HR mappings: never use
this script for Production, and do not push real punches until independently
verifying employee identity.
"""
import csv
import os
import stat
import unicodedata
from collections import Counter
from pathlib import Path

PRIVATE_DIR = Path("/odoo16/.local/share/raidat-biometric")
EXPECTED_COUNTS = {"employees": 51, "zk_room_1": 19, "hik_room_2": 46}
APPROVAL_PHRASE = "IMPORT-PROVISIONAL-ON-test_RSH"
DEVICES = ("zk_room_1", "hik_room_2")


def _normalize(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _secure_read(path, required):
    path = Path(path)
    if path.parent.resolve() != PRIVATE_DIR:
        raise RuntimeError("REFUSED: input must be placed in odoo16 private test directory")
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("REFUSED: private input must be a regular file")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError("REFUSED: input CSV must not be group/world-readable")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise RuntimeError("REFUSED: missing columns from private CSV")
        rows = list(reader)
    if not rows:
        raise RuntimeError("REFUSED: input CSV empty")
    return rows


def _inventory(rows, expected_device):
    names = {}
    for row in rows:
        if str(row["device_id"]).strip() != expected_device:
            raise RuntimeError("REFUSED: incorrect device inventory")
        uid = str(row["user_id"] or "").strip()
        name = _normalize(row["device_display_name"])
        if not uid or uid in names or not name:
            raise RuntimeError("REFUSED: ambiguous or empty device inventory")
        names[uid] = name
    return names


def _check_context(env):
    if env.cr.dbname != "test_RSH":
        raise RuntimeError("REFUSED: this importer only supports test_RSH")
    Device = env["asg.biometric.device"].sudo()
    devices = Device.search([("external_id", "in", list(DEVICES)), ("active", "=", True)])
    if len(devices) != 2 or {d.external_id for d in devices} != set(DEVICES):
        raise RuntimeError("REFUSED: expected exactly two active test devices")
    by_key = {d.external_id: d for d in devices}
    if len({d.company_id.id for d in devices}) != 1:
        raise RuntimeError("REFUSED: devices in different companies")
    for d in devices:
        if d.processing_strategy != "raw_only":
            raise RuntimeError("REFUSED: wrong device strategy")
    return by_key, devices[0].company_id.id


def preview_rsh_test_mappings(env, *, apply=False, confirm=None, private_dir=None):
    """Compare candidate mappings against Odoo and both device inventories.

    Only creates mappings in test_RSH when apply=True and confirm string matches.
    Commits only after full validation and creation; rolls back on any failure.
    """
    if env.cr.dbname != "test_RSH":
        raise RuntimeError("REFUSED: production database")
    if apply and confirm != APPROVAL_PHRASE:
        raise RuntimeError("REFUSED: explicit test-only confirmation required")
    base = Path(private_dir) if private_dir is not None else PRIVATE_DIR
    if base.resolve() != PRIVATE_DIR:
        raise RuntimeError("REFUSED: private_dir must be the dedicated test directory")
    paths = {
        "review": base / "rsh_review_test.csv",
        "zk_room_1": base / "zk_test.csv",
        "hik_room_2": base / "hik_test.csv",
    }
    review = _secure_read(
        paths["review"],
        ("test_employee_id", "employee_name", "zk_room_1_user_id",
         "hik_room_2_user_id", "approval_status", "approved_by", "match_review"),
    )
    inventory = {
        device_id: _inventory(
            _secure_read(paths[device_id], ("device_id", "user_id", "device_display_name")),
            device_id,
        )
        for device_id in DEVICES
    }
    if len(inventory["zk_room_1"]) != 396 or len(inventory["hik_room_2"]) != 130:
        raise RuntimeError("REFUSED: device inventory counts differ from verified exports")
    devices, company_id = _check_context(env)
    Employee = env["hr.employee"].sudo()
    Mapping = env["asg.biometric.employee.mapping"].sudo()

    # Check every CSV row and the complete candidate set before any ORM write.
    seen_emp = set()
    seen_keys = set()
    pending = []
    counted = Counter()
    candidate_ids = set()
    for row in review:
        emp_text = str(row["test_employee_id"] or "").strip()
        if not emp_text.isdecimal() or emp_text in seen_emp:
            raise RuntimeError("REFUSED: invalid/duplicate Test employee ID")
        seen_emp.add(emp_text)
        employee = Employee.browse(int(emp_text))
        if (not employee.exists() or not employee.active
                or employee.company_id.id != company_id
                or _normalize(employee.name) != _normalize(row["employee_name"])):
            raise RuntimeError("REFUSED: Test employee missing, changed, or wrong company")

        status = str(row["approval_status"] or "").strip().upper()
        if status != "PENDING" or str(row["approved_by"] or "").strip():
            raise RuntimeError("REFUSED: input is not original unapproved candidate review")
        values = {
            "zk_room_1": str(row["zk_room_1_user_id"] or "").strip(),
            "hik_room_2": str(row["hik_room_2_user_id"] or "").strip(),
        }
        if any(values.values()):
            if str(row["match_review"]).strip() != "EXACT_NAME_CANDIDATE_VERIFY_DEVICE_ID":
                raise RuntimeError("REFUSED: device ID present without exact-name candidate marker")
            if _normalize(employee.name) == "test":
                raise RuntimeError("REFUSED: test dummy employee candidate")
            candidate_ids.add(emp_text)
            for device_id, uid in values.items():
                if not uid:
                    continue
                if uid not in inventory[device_id] or inventory[device_id][uid] != _normalize(employee.name):
                    raise RuntimeError("REFUSED: candidate name or ID not in original device inventory")
                key = (device_id, uid)
                if key in seen_keys:
                    raise RuntimeError("REFUSED: duplicated device mapping candidate")
                seen_keys.add(key)
                counted[device_id] += 1
                pending.append((devices[device_id], employee, uid))
        elif str(row["match_review"]).strip() not in (
            "NEEDS_MANUAL_DEVICE_IDENTIFICATION", "AMBIGUOUS_EMPLOYEE_NAME"
        ):
            raise RuntimeError("REFUSED: unexpected empty-device review status")

    counted["employees"] = len(candidate_ids)
    if len(review) != 138 or any(counted[k] != v for k, v in EXPECTED_COUNTS.items()):
        raise RuntimeError("REFUSED: candidate totals changed; manual review required")

    # Fail closed on conflicts with already configured device user mappings.
    to_create = []
    already_present = 0
    for device, employee, uid in pending:
        records = Mapping.with_context(active_test=False).search([
            ("device_id", "=", device.id),
            "|",
            ("external_user_id", "=", uid),
            ("employee_id", "=", employee.id),
        ])
        if not records:
            to_create.append({
                "device_id": device.id,
                "employee_id": employee.id,
                "external_user_id": uid,
                "active": True,
            })
        elif (len(records) == 1
              and records[0].employee_id.id == employee.id
              and records[0].external_user_id == uid
              and records[0].active):
            already_present += 1
        else:
            raise RuntimeError("REFUSED: conflicting existing Test mapping")

    print("Database: test_RSH (verified)")
    print("Candidate employees:", counted["employees"])
    print("Candidate mappings: ZK=%d Hik=%d Total=%d" % (
        counted["zk_room_1"], counted["hik_room_2"], len(pending)))
    print("Existing matching mappings:", already_present)
    print("Mappings to create:", len(to_create))
    print("Scope: provisional TEST only; no Attendance or cron changes")
    if not apply:
        print("RESULT: PREVIEW ONLY; no Odoo records written")
        return {"to_create": len(to_create), "already_present": already_present}
    try:
        if to_create:
            Mapping.create(to_create)
        env.cr.commit()
    except BaseException:
        env.cr.rollback()
        raise
    print("RESULT: TEST mappings created:", len(to_create))
    print("CAUTION: provisional name-based mappings; no real punch processing approved")
    return {"created": len(to_create), "already_present": already_present}


if __name__ == "__main__":
    if "env" not in globals():
        raise RuntimeError("Run inside Odoo shell with env")
    preview_rsh_test_mappings(globals()["env"])