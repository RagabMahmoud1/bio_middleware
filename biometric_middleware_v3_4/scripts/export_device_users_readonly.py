"""One-shot read-only roster inventory from biometric devices.

This utility does NOT read attendance events, SQLite, Odoo API tokens, or
modify middleware configuration. It connects separately to one chosen device
to list enrolled users. Do not run in parallel or repeatedly if a device
cannot support concurrent sessions with the existing Windows service.

Usage (PowerShell, one line):
& "C:\\RaidatBiometric\\.venv\\Scripts\\python.exe" "$env:TEMP\\export_device_users_readonly.py" --config "C:\\RaidatBiometric\\config.yaml" --device zk_room_1

Reports counts only on stdout. Names/IDs are retained only in a local CSV
inside the current Windows profile for offline HR verification.
"""
import argparse
import csv
import os
from pathlib import Path
import sys
from datetime import datetime
import uuid

import yaml

FIELDS = ("device_id", "user_id", "device_display_name", "source")


def _safe_text(value):
    """Prevent spreadsheet formula interpretation of device-supplied names/IDs."""
    text = str(value).strip() if value is not None else ""
    if text.lstrip()[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _valid_id(value):
    return str(value).strip() if value is not None else ""


def list_zkteco_users(config, adapter_type):
    adapter = adapter_type(config)
    conn = None
    try:
        conn = adapter._connect()
        users = conn.get_users()
        if users is None:
            raise RuntimeError("ZKTeco user listing returned no result")
        result = []
        for user in users:
            employee_code = _valid_id(getattr(user, "user_id", None))
            if not employee_code:
                # Attendance adapter uses 'uid' only as a fallback.
                employee_code = _valid_id(getattr(user, "uid", None))
            if not employee_code:
                continue
            result.append({
                "device_id": str(config["id"]),
                "user_id": employee_code,
                "device_display_name": _safe_text(getattr(user, "name", None)),
                "source": "zkteco_get_users",
            })
        return result
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                pass


def list_hikvision_users(config, adapter_type, page_size=30, max_users=10000):
    """ISAPI/AccessControl/UserInfo/Search is a read-only search operation."""
    adapter = adapter_type(config)
    search_id = "rsh-audit-" + uuid.uuid4().hex[:16]
    position = 0
    users = []
    seen = set()
    while position < max_users:
        body = {
            "UserInfoSearchCond": {
                "searchID": search_id,
                "searchResultPosition": position,
                "maxResults": page_size,
            }
        }
        response = adapter._post("/ISAPI/AccessControl/UserInfo/Search?format=json", body)
        response.raise_for_status()
        data = response.json()
        data = data.get("UserInfoSearch", data)
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Hikvision user-search response")
        page = data.get("UserInfo") or data.get("userInfo") or []
        if isinstance(page, dict):
            page = [page]
        if not isinstance(page, list):
            raise RuntimeError("Invalid Hikvision UserInfo result")
        total = data.get("totalMatches")
        if total is not None:
            total = int(total)
        for person in page:
            if not isinstance(person, dict):
                continue
            employee_code = _valid_id(
                person.get("employeeNo")
                or person.get("employeeNoString")
                or person.get("employeeNoLong")
            )
            if not employee_code:
                continue
            if employee_code in seen:
                continue
            seen.add(employee_code)
            users.append({
                "device_id": str(config["id"]),
                "user_id": employee_code,
                "device_display_name": _safe_text(person.get("name")),
                "source": "hikvision_user_info_search",
            })
        count = len(page)
        if not count:
            if total is not None and position < total:
                raise RuntimeError("Hikvision search stopped before totalMatches")
            break
        position += count
        if total is not None and position >= total:
            break
        if len(users) > max_users:
            raise RuntimeError("Hikvision roster exceeds safety limit")
        if total is None and count < page_size:
            break
    else:
        raise RuntimeError("Hikvision listing exceeded safety limit")
    return users


def export_device_users(config_path, device_id, output_dir=None):
    cfg_file = Path(config_path)
    if not cfg_file.is_file():
        raise ValueError("Config path was not found")
    # Use the installed production adapter only for its read-only connection code.
    sys.path.insert(0, str(cfg_file.resolve().parent))
    from app.adapters.zkteco import ZKTecoAdapter
    from app.adapters.hikvision import HikvisionAdapter

    with cfg_file.open(encoding="utf-8") as stream:
        cfg = yaml.safe_load(stream) or {}
    matches = [d for d in cfg.get("devices", []) if d.get("id") == device_id]
    if len(matches) != 1:
        raise ValueError("Device ID must appear exactly once in config")
    device = matches[0]
    if device.get("enabled") is not True:
        raise ValueError("Device must be enabled")
    dtype = device.get("type")
    if dtype == "zkteco":
        records = list_zkteco_users(device, ZKTecoAdapter)
    elif dtype == "hikvision":
        records = list_hikvision_users(device, HikvisionAdapter)
    else:
        raise ValueError("Unsupported device type")

    if not records:
        raise RuntimeError("No registered users were returned; no CSV generated")

    output = Path(output_dir) if output_dir else (
        Path.home() / "Documents" / "RaidatBiometricPrivate"
    )
    output.mkdir(parents=True, exist_ok=True)
    filename = output / (
        "device_users_" + device_id + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        + ".csv"
    )
    # Exclusive file creation protects existing inventory exports.
    with filename.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)

    print("Device:", device_id)
    print("Registered users:", len(records))
    print("Unique device User IDs:", len({r["user_id"] for r in records}))
    print("Inventory CSV:", filename)
    print("Contains device user names and IDs; keep for authorized HR review only.")
    print("Middleware service/config/SQLite not modified by this tool.")
    return filename


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--device", required=True, choices=("zk_room_1", "hik_room_2"))
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    try:
        export_device_users(args.config, args.device, args.output_dir)
    except Exception as exc:
        print("Device roster export failed:", type(exc).__name__)
        print("No service change or attendance fetch was requested.")
        sys.exit(2)
