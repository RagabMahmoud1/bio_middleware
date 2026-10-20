"""REAL HTTP dual-target E2E against isolated TEST Odoo services only.

The script NEVER polls biometric devices or production URLs. It uses a fresh
temporary SQLite, previously bootstrapped synthetic TEST mappings, and fixed
synthetic event keys. It fails closed if matching TEST events already exist.

Prerequisites:
 - ERP TEST DB 'test' on its own service/port, max_cron_threads=0
 - RSH TEST DB 'test_RSH' on 8070
 - scripts/bootstrap_dual_target_tests.py executed once on BOTH TEST DBs
 - TEST tokens in /odoo16/.config/raidat-biometric mode 0600
 - read-only PostgreSQL access for test DB evidence
Run from the biometric_middleware_v3_4 directory with Python 3.
"""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
import json
import sqlite3
import stat
import sys
import tempfile
from zoneinfo import ZoneInfo

# Works when launched from anywhere; no production program paths are touched.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.db import Database
from app.multi_target import MultiTargetRuntime
from audit_dual_odoo_test_readonly import read_config, pg_query
from bootstrap_dual_target_tests import SYNTH_CODES, SYNTH_DEVICE_IDS

EVENT_PREFIX = "RAIDAT_DUAL_HTTP_20261020"
ERP_CONF = "/etc/odoo-erp-test.conf"
RSH_CONF = "/etc/odoo-test.conf"
TOKEN_DIR = Path("/odoo16/.config/raidat-biometric")
SUFFIXES = ("SHARED_IN", "SHARED_OUT", "ERP_ONLY", "RSH_ONLY")
TEST_TIMEZONE = ZoneInfo("Asia/Riyadh")
RAW_TABLE = "asg_biometric_raw_event"


def _require(cond, explanation):
    if not cond:
        raise RuntimeError("REFUSED: " + explanation)


def _token(name):
    path = TOKEN_DIR / name
    _require(not path.is_symlink() and path.is_file(),
             "private TEST token file missing or symlinked")
    info = path.stat()
    _require(stat.S_IMODE(info.st_mode) & 0o077 == 0,
             "private TEST token permissions are too permissive")
    token = path.read_text(encoding="utf-8").strip()
    _require(len(token) >= 32, "TEST token too short")
    return token


def _port(config_path, database, expected=None, require_disabled_cron=False):
    info = read_config(config_path)
    _require(info.get("valid"), "missing valid TEST Odoo config")
    settings = info["settings"]
    _require(settings.get("db_name") == database, "TEST db_name mismatch")
    _require(settings.get("dbfilter") == "^" + database + "$",
             "TEST dbfilter mismatch")
    if require_disabled_cron:
        _require(settings.get("max_cron_threads") == "0",
                 "ERP TEST service must disable cron during E2E")
    port = settings.get("http_port")
    _require(port is not None and port.isdigit(), "missing TEST HTTP port")
    number = int(port)
    _require(number not in (80, 443, 8069) and number > 1024,
             "unsafe/Production HTTP port")
    if expected is not None:
        _require(number == expected, "RSH TEST port changed unexpectedly")
    return number


def _count(db):
    query = ("SELECT count(*) FROM " + RAW_TABLE +
             " WHERE event_key IN (" + ",".join(
                 "'" + event["event_key"] + "'" for event in events()
             ) + ")")
    result = pg_query(db, query)
    _require(result.get("ok"), "no read-only SQL access to " + db)
    rows = result["rows"]
    _require(len(rows) == 1 and len(rows[0]) == 1 and rows[0][0].isdigit(),
             "invalid SQL evidence response")
    return int(rows[0][0])


def events():
    # Immutable synthetic date ensures audit keys stay stable across restarts.
    completed = date(2026, 10, 17)
    stamp = lambda h,m: datetime.combine(
        completed, time(h,m), tzinfo=TEST_TIMEZONE
    ).isoformat()
    specs = (
        ("SHARED_IN", SYNTH_DEVICE_IDS[0], SYNTH_CODES["shared"],stamp(8,15)),
        ("SHARED_OUT",SYNTH_DEVICE_IDS[1], SYNTH_CODES["shared"],stamp(17,15)),
        ("ERP_ONLY",  SYNTH_DEVICE_IDS[0], SYNTH_CODES["erp_only"],stamp(9,0)),
        ("RSH_ONLY",  SYNTH_DEVICE_IDS[0], SYNTH_CODES["rsh_only"],stamp(9,20)),
    )
    records = [{
        "device_id": device,
        "device_type": "zkteco" if device == SYNTH_DEVICE_IDS[0] else "hikvision",
        "employee_code": code, "event_time": when,
        "event_type": "check",
        "source_event_id": EVENT_PREFIX + "_" + key,
        "raw": {"synthetic": True, "test_only": True},
    } for key, device, code, when in specs]
    # Database.add_events_bulk computes SHA256, not the explicit event_key.
    # The HTTP test and Odoo ORM verifier must use exactly those hashes.
    for item in records:
        item["event_key"] = Database.make_event_key(item)
    return records


def run_e2e():
    erp_port = _port(ERP_CONF, "test", require_disabled_cron=True)
    rsh_port = _port(RSH_CONF, "test_RSH", expected=8070)
    _require(erp_port != rsh_port, "test services share a port")
    erp_token, rsh_token = _token("erp-test-token"), _token("rsh-test-token")
    _require(erp_token != rsh_token, "ERP and RSH TEST tokens must differ")
    _require(_count("test") == 0 and _count("test_RSH") == 0,
             "these synthetic HTTP events already exist; NEVER replay this test")

    erp_url = "http://127.0.0.1:" + str(erp_port)
    rsh_url = "http://127.0.0.1:" + str(rsh_port)
    cutoff = "2026-10-16T00:00:00+03:00"
    config = {
        "odoo": {"base_url": erp_url}, "legacy_target_id": "erp",
        "odoo_targets": [
            {"id": "erp", "enabled": True, "base_url": erp_url,
             "api_token": erp_token, "endpoint": "/biometric/api/v1/events",
             "device_ids": list(SYNTH_DEVICE_IDS), "timeout_seconds": 8},
            {"id": "rsh", "enabled": True, "base_url": rsh_url,
             "api_token": rsh_token, "endpoint": "/biometric/api/v1/events",
             "device_ids": list(SYNTH_DEVICE_IDS), "timeout_seconds": 8,
             "start_at": cutoff},
        ],
    }

    with tempfile.TemporaryDirectory(prefix="raidat-test-only-http-") as temp:
        db = Database(Path(temp) / "test.sqlite")
        runtime = MultiTargetRuntime(config, db)
        # READ-only allowlist checks happen before the first HTTP POST.
        expected = {
            SYNTH_DEVICE_IDS[0]: set(SYNTH_CODES.values()),
            SYNTH_DEVICE_IDS[1]: {SYNTH_CODES["shared"]},
        }
        for dev_id in SYNTH_DEVICE_IDS:
            allowed = runtime.get_allowed_employee_ids(dev_id)
            _require(set(allowed) == expected[dev_id],
                     "synthetic target mapping/HTTP preflight unexpected")
            isolated = runtime._by_device[dev_id]
            for target in ("erp", "rsh"):
                target_codes = isolated[target][0]
                mandatory = {SYNTH_CODES["shared"]}
                if dev_id == SYNTH_DEVICE_IDS[0]:
                    mandatory.add(SYNTH_CODES[target + "_only"])
                _require(target_codes == mandatory,
                         "wrong target-specific synthetic allowlist")

        entries = events()
        _require(db.add_events_bulk(entries) == 4,
                 "temporary test SQLite event count mismatch")
        for dev_id in SYNTH_DEVICE_IDS:
            runtime.queue_captured(dev_id)
        _require(db.target_queue_stats("erp")["pending"] == 3,
                 "ERP test queue mismatch before push")
        _require(db.target_queue_stats("rsh")["pending"] == 3,
                 "RSH test queue mismatch before push")

        # Simulate RSH HTTP outage by changing ONLY the ephemeral client URL
        # to closed loopback port 1. Neither production nor RSH service stops.
        rsh_client = next(c for i,c,_,_ in runtime.targets if i == "rsh")
        rsh_client.cfg["base_url"] = "http://127.0.0.1:1"
        _require(runtime.send_pending() is False,
                 "expected synthetic loopback RSH delivery failure")
        _require(db.target_queue_stats("erp")["synced"] == 3,
                 "ERP failed to ACK while RSH test target simulated outage")
        _require(db.target_queue_stats("rsh")["pending"] == 3,
                 "RSH pending queue not independently retained")
        _require(_count("test") == 3 and _count("test_RSH") == 0,
                 "actual Odoo TEST rows contradict isolated delivery state")

        # Reopen the real temporary SQLite, rebuild runtime with correct
        # RSH TEST URL. ERP must NOT replay any of the 3 accepted rows.
        rsh_client.cfg["base_url"] = rsh_url
        db = Database(Path(temp) / "test.sqlite")
        runtime = MultiTargetRuntime(config, db)
        _require(len(db.pending_for_target("erp")) == 0,
                 "ERP ACK lost during temporary SQLite reopen")
        _require(runtime.send_pending() is True,
                 "RSH TEST recovery HTTP send failed")
        _require(db.target_queue_stats("erp")["synced"] == 3,
                 "ERP status changed during RSH recovery")
        _require(db.target_queue_stats("rsh")["synced"] == 3,
                 "RSH ACK missing after simulated outage")
        _require(_count("test") == 3 and _count("test_RSH") == 3,
                 "TEST Raw Event rows do not match two-target 3+3 ACKs")

        # Synthetic duplicate POST directly verifies server-side
        # idempotency without resending unrelated (real) device events.
        shared_keys = {r["event_key"] for r in entries[:2]}
        with db.connect() as conn:
            conn.row_factory=sqlite3.Row
            shared_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM events WHERE event_key IN (?,?)",
                tuple(sorted(shared_keys))
            )]
        _require(len(shared_rows)==2, "missing synthetic shared rows")
        for target_id, client, _, _ in runtime.targets:
            response = client.send(shared_rows)
            _require(len(response["accepted_ids"]) == 2 and
                     not response["ignored_ids"] and
                     not response["rejected_items"] and
                     not response["unhandled_ids"],
                     "duplicate TEST event not acknowledged for "+target_id)
        _require(_count("test") == 3 and _count("test_RSH") == 3,
                 "duplicate TEST event was inserted more than once")
        print("PASS: REAL TEST HTTP delivery to ERP and RSH (3 events each)")
        print("PASS: real test API union/per-target allowlists verified")
        print("PASS: ERP ACK isolated from simulated RSH loopback outage")
        print("PASS: separate SQLite deliveries persisted through reopen")
        print("PASS: no ERP replay; RSH recovery; duplicate event API idempotency")
        print("NEXT: process only synthetic Raw Events on both TEST databases")
        print("LIVE: unchanged; PRODUCTION devices: never contacted")


if __name__ == "__main__":
    run_e2e()