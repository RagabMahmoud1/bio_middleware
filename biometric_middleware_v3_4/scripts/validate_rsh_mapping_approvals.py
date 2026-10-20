"""Validate RSH TEST biometric mapping approvals OFFLINE; never writes to Odoo.

Inputs:
 - unmodified test employee roster (rsh.csv),
 - original independent device inventories (zk.csv / hik.csv),
 - HR reviewed match file (rsh_review.csv).

Approval requires:
 - approval_status=APPROVED,
 - approved_by not empty,
 - verification_reference not empty (HR independent check, NOT PIN or secrets),
 - employee id AND employee name still match test roster,
 - device IDs exist in the matching original device export,
 - unique device user ID per device across approvals.

The validator reports COUNTS ONLY. It never outputs personal identifiers.
"""
import argparse
import csv
import sys
import unicodedata
from collections import Counter
from pathlib import Path


def read_rows(path, required):
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        header = handle.read(2048)
        handle.seek(0)
        try:
            separator = csv.Sniffer().sniff(header, delimiters=",\t").delimiter
        except csv.Error:
            separator = "\t" if "\t" in header.partition("\n")[0] else ","
        reader = csv.DictReader(handle, delimiter=separator)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError("File is missing required headers")
        return list(reader)


def key(text):
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).casefold().split())


def validate(roster, zk, hik, review):
    required_roster = ("test_employee_id", "employee_name")
    required_device = ("device_id", "user_id")
    required_review = (
        "test_employee_id", "employee_name", "zk_room_1_user_id",
        "hik_room_2_user_id", "approval_status", "approved_by",
    )
    employees = read_rows(roster, required_roster)
    devices_zk = read_rows(zk, required_device)
    devices_hik = read_rows(hik, required_device)
    decisions = read_rows(review, required_review)

    if not employees or not decisions:
        raise ValueError("Employee roster or review file is empty")

    employee_by_id = {}
    for employee in employees:
        employee_id = employee["test_employee_id"].strip()
        if not employee_id or employee_id in employee_by_id:
            raise ValueError("Employee roster has an empty or duplicate ID")
        employee_by_id[employee_id] = employee

    def device_user_ids(rows, device_id):
        ids = set()
        for row in rows:
            if (row["device_id"] or "").strip() != device_id:
                raise ValueError("Device inventory contains an unexpected device ID")
            user_id = (row["user_id"] or "").strip()
            if not user_id or user_id in ids:
                raise ValueError("Device inventory contains missing or duplicate User IDs")
            ids.add(user_id)
        return ids

    known_zk = device_user_ids(devices_zk, "zk_room_1")
    known_hik = device_user_ids(devices_hik, "hik_room_2")

    if len(decisions) != len(employees):
        raise ValueError("Review file must contain all Test employee rows")

    seen_employees = set()
    seen_device = {"zk_room_1": set(), "hik_room_2": set()}
    issues = Counter()
    counts = Counter()
    for decision in decisions:
        employee_id = (decision["test_employee_id"] or "").strip()
        if employee_id in seen_employees or employee_id not in employee_by_id:
            issues["employee_row_mismatch"] += 1
            continue
        seen_employees.add(employee_id)
        if key(decision["employee_name"]) != key(employee_by_id[employee_id]["employee_name"]):
            issues["employee_name_changed"] += 1
            continue

        status = str(decision["approval_status"] or "").strip().upper()
        if status not in {"PENDING", "APPROVED", "REJECTED"}:
            issues["invalid_status"] += 1
            continue
        counts[status.lower()] += 1
        if status != "APPROVED":
            continue

        before = sum(issues.values())
        if key(decision["employee_name"]) == "test":
            issues["test_employee_not_approvable"] += 1
        if not str(decision["approved_by"] or "").strip():
            issues["missing_approver"] += 1
        # Approval evidence is required, but should be a ticket/reference,
        # NOT an iqama number, personal ID, password, or PIN.
        if not str(decision.get("verification_reference") or "").strip():
            issues["missing_verification_reference"] += 1

        values = (
            ("zk_room_1", decision["zk_room_1_user_id"], known_zk),
            ("hik_room_2", decision["hik_room_2_user_id"], known_hik),
        )
        if not any(str(uid or "").strip() for _, uid, _ in values):
            issues["approved_without_device_id"] += 1

        for device_id, raw_uid, known in values:
            uid = str(raw_uid or "").strip()
            if not uid:
                continue
            if uid not in known:
                issues["device_user_id_unknown_or_excel_corrupted"] += 1
            elif uid in seen_device[device_id]:
                issues["device_user_id_reused"] += 1
            else:
                seen_device[device_id].add(uid)
        if sum(issues.values()) == before:
            counts["valid_approved_employees"] += 1

    if len(seen_employees) != len(employees):
        issues["missing_employee_rows"] += 1

    print("TEST employee roster count:", len(employees))
    print("Original device accounts: ZK=%d Hik=%d" % (len(known_zk), len(known_hik)))
    print("Review decisions: APPROVED=%d PENDING=%d REJECTED=%d" % (
        counts["approved"], counts["pending"], counts["rejected"]
    ))
    print("Valid approved employees:", counts["valid_approved_employees"])
    print("Validation issue count:", sum(issues.values()))
    for issue, total in sorted(issues.items()):
        print("  %s: %d" % (issue, total))
    print("Mode: OFFLINE AUDIT ONLY; no Odoo writes or employee mappings.")
    if issues:
        print("RESULT: BLOCKED - correct validation issues before import")
        return 2
    if not counts["valid_approved_employees"]:
        print("RESULT: NOT READY - no independently approved mappings")
        return 3
    print("RESULT: REVIEW APPROVALS VALIDATED - still requires controlled Odoo Test import")
    return 0


def main():
    parser = argparse.ArgumentParser()
    for arg in ("roster", "zk", "hik", "review"):
        parser.add_argument("--" + arg, required=True)
    args = parser.parse_args()
    try:
        return validate(args.roster, args.zk, args.hik, args.review)
    except (OSError, ValueError, UnicodeError) as exc:
        print("RESULT: BLOCKED - private review inputs invalid:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
