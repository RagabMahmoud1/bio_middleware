"""Offline, review-only biometric roster matching for RSH TEST.

Input: three private CSVs: RSH TEST active employees, ZKTeco users, Hikvision users.
Output: a private CSV with ONLY unambiguous exact-name CANDIDATES and a separate
manual-review summary. NO database writes, API calls, PINs, or automated approval.

Names can match between different people. An exact name is a proposed candidate,
NOT proof of identity. HR must approve against a second identifier before import.
"""
import argparse
import csv
import os
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


ROSTER_COLUMNS = (
    "test_employee_id", "employee_name", "department",
    "zk_room_1_user_id", "hik_room_2_user_id",
    "approved_by", "approval_status",
)
REVIEW_COLUMNS = (*ROSTER_COLUMNS, "match_review", "zk_name_matches", "hik_name_matches")


def _normalize_name(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _read_csv(path, required):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("Missing input CSV: " + str(path))
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise ValueError("CSV missing expected headers: " + path.name)
        return list(reader)


def _device_index(path, device_id):
    rows = _read_csv(path, ("device_id", "user_id", "device_display_name"))
    by_name = defaultdict(set)
    ids = defaultdict(set)
    for row in rows:
        if str(row["device_id"]).strip() != device_id:
            raise ValueError("Wrong device ID in CSV: " + path.name)
        user_id = str(row["user_id"] or "").strip()
        name = _normalize_name(row["device_display_name"])
        if not user_id:
            continue
        ids[user_id].add(name)
        if name:
            by_name[name].add(user_id)
    # Only use IDs with exactly one consistent name.
    for name in tuple(by_name):
        by_name[name] = {
            uid for uid in by_name[name]
            if len(ids[uid]) == 1 and next(iter(ids[uid])) == name
        }
    return by_name, len(ids), sum(len(names) > 1 for names in ids.values())


def _safe_csv(value):
    value = str(value or "")
    # CSV user input can include formula-like values. Preserve only escaped text.
    if value.lstrip()[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _write_private(path, rows):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError("Refusing to overwrite private review CSV")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _safe_csv(row.get(k, "")) for k in REVIEW_COLUMNS})
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def build_review(roster_path, zk_path, hik_path, output_path):
    roster = _read_csv(roster_path, ROSTER_COLUMNS)
    employees_per_name = Counter(
        _normalize_name(row["employee_name"])
        for row in roster if _normalize_name(row["employee_name"])
    )
    zk, zk_count, zk_collisions = _device_index(zk_path, "zk_room_1")
    hik, hik_count, hik_collisions = _device_index(hik_path, "hik_room_2")
    approved = []
    summary = Counter()
    for employee in roster:
        row = dict(employee)
        name = _normalize_name(row["employee_name"])
        if row["zk_room_1_user_id"] or row["hik_room_2_user_id"]:
            raise ValueError("Roster already has user IDs; review-only template expected")
        if not name or employees_per_name[name] != 1:
            row["match_review"] = "AMBIGUOUS_EMPLOYEE_NAME"
            row["zk_name_matches"] = str(len(zk.get(name, set())))
            row["hik_name_matches"] = str(len(hik.get(name, set())))
            summary["ambiguous_employees"] += 1
        else:
            zk_users = zk.get(name, set())
            hik_users = hik.get(name, set())
            row["zk_name_matches"] = str(len(zk_users))
            row["hik_name_matches"] = str(len(hik_users))
            if len(zk_users) == 1:
                row["zk_room_1_user_id"] = next(iter(zk_users))
                summary["zk_candidates"] += 1
            elif len(zk_users) > 1:
                summary["ambiguous_zk"] += 1
            if len(hik_users) == 1:
                row["hik_room_2_user_id"] = next(iter(hik_users))
                summary["hik_candidates"] += 1
            elif len(hik_users) > 1:
                summary["ambiguous_hik"] += 1
            if row["zk_room_1_user_id"] or row["hik_room_2_user_id"]:
                row["match_review"] = "EXACT_NAME_CANDIDATE_VERIFY_DEVICE_ID"
                summary["employee_candidates"] += 1
            else:
                row["match_review"] = "NEEDS_MANUAL_DEVICE_IDENTIFICATION"
                summary["manual"] += 1
        row["approval_status"] = "PENDING"
        row["approved_by"] = ""
        approved.append(row)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        output.parent.chmod(0o700)
    _write_private(output, approved)
    print("RSH roster employees:", len(roster))
    print("ZKTeco device IDs:", zk_count, "Hikvision device IDs:", hik_count)
    print("ZK unique-name candidates:", summary["zk_candidates"])
    print("Hik unique-name candidates:", summary["hik_candidates"])
    print("Employees with at least one candidate:", summary["employee_candidates"])
    print("Ambiguous employee names:", summary["ambiguous_employees"])
    print("Ambiguous device-name matches:", summary["ambiguous_zk"] + summary["ambiguous_hik"])
    print("Manual identification needed:", summary["manual"])
    print("Duplicate/conflicting device ID names:", zk_collisions + hik_collisions)
    print("Private review file:", output)
    print("NO approved mappings. No Odoo or device data was modified.")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--roster", required=True)
    parser.add_argument("--zk", required=True)
    parser.add_argument("--hik", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build_review(args.roster, args.zk, args.hik, args.output)
