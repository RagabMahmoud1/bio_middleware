"""Read-only evidence collector for Raidat ERP/RSH TEST service separation.

Run ON THE ODOO LINUX HOST using Python 3. No secrets or record-level HR data
are read. This tool never creates files, connects to devices, changes database
records, restarts services, or contacts Production URLs.
"""
from __future__ import annotations

import ast
import configparser
import json
import os
from pathlib import Path
import re
import subprocess
import sys

DATABASES = ("test", "test_RSH")
MODULES = (
    "hr_attendance",
    "rm_hr_attendance_sheet",
    "rgb_biometric_attendance_bridge",
    "rgb_biometric_first_last_attendance",
)
CONFIG_KEYS = ("http_port", "addons_path", "db_name", "dbfilter",
               "max_cron_threads", "workers", "http_interface")
CONFIG_FILES = (
    "/etc/odoo-test.conf", "/etc/odoo16-server.conf",
    "/etc/odoo-erp-test.conf",
)
MODULE_SQL = (
    "SELECT name,state,COALESCE(latest_version,'') "
    "FROM ir_module_module WHERE name IN ("
    + ",".join("'" + x + "'" for x in MODULES)
    + ") ORDER BY name"
)
_DB_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def run(argv, timeout=15):
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, check=False)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__}
    return {
        "ok": p.returncode == 0,
        "exit_code": p.returncode,
        "stdout": p.stdout[:12000] if p.returncode == 0 else "",
        # Never print stderr, which may include usernames, credentials or DSNs.
        "error": None if p.returncode == 0 else "command_failed",
    }


def read_config(path):
    p = Path(path)
    if not p.is_file():
        return {"present": False}
    try:
        # Odoo configs are INI files with [options]; inspect a strict key allowlist.
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(path, encoding="utf-8")
        if not parser.has_section("options"):
            return {"present": True, "readable": True, "valid": False}
        opts = parser["options"]
        return {
            "present": True, "readable": True, "valid": True,
            "settings": {key: opts.get(key) for key in CONFIG_KEYS if key in opts},
        }
    except (OSError, UnicodeError, configparser.Error):
        return {"present": True, "readable": False}


def module_source(addons_path, name):
    for root in addons_path.split(","):
        root = root.strip()
        if not root:
            continue
        p = Path(root) / name / "__manifest__.py"
        if p.is_file():
            try:
                data = ast.literal_eval(p.read_text(encoding="utf-8"))
                return {"path": str(p.parent),
                        "version": str(data.get("version", "")),
                        "depends": data.get("depends", []),
                        "installable": bool(data.get("installable", False))}
            except (OSError, UnicodeError, ValueError, SyntaxError):
                return {"path": str(p.parent), "manifest_unreadable": True}
    return None


def pg_query(db, sql):
    if not _DB_PATTERN.fullmatch(db):
        return {"ok": False, "error": "invalid_database"}
    cmd = ["psql", "-X", "-A", "-F", "|", "-t", "-v",
           "ON_ERROR_STOP=1", "-d", db, "-c", sql]
    # Explicitly read only; no SQL commands from user data.
    result = run(["sudo", "-n", "-u", "postgres", *cmd], timeout=20)
    if not result["ok"]:
        result = run(cmd, timeout=20)
    if not result["ok"]:
        return {"ok": False, "error": "no_database_read_access"}
    return {"ok": True, "rows": [x.split("|") for x in
                                result["stdout"].splitlines() if x.strip()]}


def collect():
    result = {"schema": "raidat-erp-rsh-readonly-audit-v1",
              "safety": "READ_ONLY", "host": os.uname().nodename,
              "configured_services": {}, "module_states": {},
              "module_sources": {}, "ports": {}, "warnings": []}
    service = run(["systemctl", "list-units", "--type=service", "--all",
                   "--no-pager", "--no-legend"])
    if service["ok"]:
        result["configured_services"] = {
            "odoo_units": [
                unit
                for line in service["stdout"].splitlines()
                for unit in line.strip().split()
                if unit.endswith(".service") and "odoo" in unit.lower()
            ]
        }
    else:
        result["warnings"].append("Unable to list systemd services")

    sockets = run(["ss", "-lntH"])
    if sockets["ok"]:
        listening = []
        for line in sockets["stdout"].splitlines():
            cells = line.split()
            if len(cells) >= 4:
                listening.append(cells[3])
        result["ports"] = {
            "listen": listening,
            "candidate_8081_listening": any(
                addr.rsplit(":", 1)[-1] == "8081" for addr in listening
            ),
        }
    else:
        result["warnings"].append("Unable to inspect listening ports")

    configs = {path: read_config(path) for path in CONFIG_FILES}
    result["configs"] = configs
    for path, entry in configs.items():
        if not entry.get("valid"):
            continue
        addons = entry["settings"].get("addons_path", "")
        result["module_sources"][path] = {
            name: module_source(addons, name)
            for name in MODULES[2:]
        }

    for db in DATABASES:
        result["module_states"][db] = pg_query(db, MODULE_SQL)

    # This is the only readiness decision: it is NOT permission to install.
    rsh = configs["/etc/odoo-test.conf"].get("settings", {})
    result["rsh_service_matches_handoff"] = (
        rsh.get("db_name") == "test_RSH"
        and rsh.get("dbfilter") == "^test_RSH$"
        and rsh.get("http_port") == "8070"
    )
    erp = configs["/etc/odoo-erp-test.conf"].get("settings", {})
    result["erp_service_config_independent"] = (
        erp.get("db_name") == "test"
        and erp.get("dbfilter") == "^test$"
        and erp.get("http_port") not in (None, "", "8070")
        and erp.get("max_cron_threads") == "0"
    )
    if not result["erp_service_config_independent"]:
        result["warnings"].append(
            "ERP TEST isolated config not verified; do not reuse RSH service")
    return result


def main():
    evidence = collect()
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())