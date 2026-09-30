import argparse
import logging
import sys
import time

from .config import load_config
from .logging_setup import setup_logging
from .db import Database
from .filters import filter_events
from .odoo_client import OdooClient
from .adapters.zkteco import ZKTecoAdapter
from .adapters.hikvision import HikvisionAdapter
from .cursors import compute_fetch_start
from .version import MIDDLEWARE_VERSION

_logger = logging.getLogger(__name__)


def build_adapter(cfg):
    dtype = cfg.get("type", "").lower()
    if dtype == "zkteco":
        return ZKTecoAdapter(cfg)
    if dtype == "hikvision":
        return HikvisionAdapter(cfg)
    raise ValueError(f"Unsupported device type: {dtype}")


def device_poll_interval(device):
    configured = device.get("poll_interval_seconds")
    if configured is not None:
        return max(60, int(configured))

    dtype = str(device.get("type", "")).lower()
    if dtype == "hikvision":
        return 300
    if dtype == "zkteco":
        return 3600
    return 900


def get_devices(cfg, only_device=None):
    devices = [d for d in cfg.get("devices", []) if d.get("enabled", True)]
    if only_device:
        devices = [d for d in devices if d.get("id") == only_device]
        if not devices:
            raise ValueError(f"Device not found or disabled: {only_device}")
    return devices


def send_pending(db, odoo):
    if not odoo.enabled:
        pending = db.pending(limit=1)
        if pending:
            _logger.info("Pending local events exist (Odoo sync disabled)")
        return True

    all_ok = True
    while True:
        pending = db.pending(limit=200)
        if not pending:
            break

        ids = [r["id"] for r in pending]
        try:
            result = odoo.send(pending)
            accepted_ids = result.get("accepted_ids") or []
            ignored_ids = result.get("ignored_ids") or []
            rejected_items = result.get("rejected_items") or []
            unhandled_ids = result.get("unhandled_ids") or []

            db.mark_synced(accepted_ids)
            db.mark_ignored(
                ignored_ids,
                "unknown_or_ambiguous_employee_in_odoo",
            )
            db.mark_rejected(rejected_items)
            db.mark_odoo_push_success(
                accepted_ids
                + ignored_ids
                + [item["id"] for item in rejected_items]
            )

            _logger.info(
                "Odoo sync accepted=%s ignored=%s rejected=%s unhandled=%s batch=%s",
                len(accepted_ids),
                len(ignored_ids),
                len(rejected_items),
                len(unhandled_ids),
                len(pending),
            )

            if unhandled_ids:
                db.mark_retry_error(
                    unhandled_ids,
                    "Odoo response did not acknowledge these events",
                )
                all_ok = False
                break
        except Exception as exc:
            db.mark_retry_error(ids, exc)
            _logger.exception("Odoo sync failed: %s", exc)
            all_ok = False
            break

    return all_ok


def build_health_payload(db):
    states = db.get_device_states()
    devices = []
    for state in states:
        device_id = state.get("device_id")
        device_stats = db.queue_stats(device_id=device_id)
        devices.append({
            "device_id": device_id,
            "last_device_fetch_success": (
                state.get("last_device_fetch_success")
                or state.get("last_successful_sync")
            ),
            "last_device_event_time": state.get("last_event_time"),
            "last_odoo_push_success": state.get("last_odoo_push_success"),
            "last_error": state.get("last_error"),
            "pending_count": device_stats["pending"],
            "failed_count": device_stats["failed"],
            "ignored_count": device_stats["ignored"],
        })

    return {
        "middleware_version": MIDDLEWARE_VERSION,
        "queue": db.queue_stats(),
        "devices": devices,
    }


def send_heartbeat(db, odoo):
    if not odoo.enabled:
        return True
    try:
        result = odoo.heartbeat(build_health_payload(db))
        _logger.info(
            "Odoo heartbeat accepted devices=%s version=%s",
            result.get("updated_devices", 0),
            MIDDLEWARE_VERSION,
        )
        return True
    except Exception as exc:
        _logger.exception("Odoo heartbeat failed: %s", exc)
        return False


def run_cycle(cfg, db, odoo, only_device=None, from_date_override=None):
    sync_cfg = cfg.get("sync", {})
    configured_go_live = sync_cfg.get("go_live_at")
    if not configured_go_live:
        raise ValueError("sync.go_live_at must be configured before production sync")
    persisted_go_live = db.set_setting("go_live_at", configured_go_live, overwrite=False)
    from_date = persisted_go_live
    if from_date_override:
        from .filters import parse_dt
        if parse_dt(from_date_override) >= parse_dt(persisted_go_live):
            from_date = from_date_override
        else:
            _logger.warning("Requested from-date %s is before production go-live %s; using go-live cutoff.", from_date_override, persisted_go_live)
    to_date = None
    configured_employee_ids = sync_cfg.get("employee_ids") or None
    batch_size = int(sync_cfg.get("batch_size", 5000))
    _logger.info("Production go-live cutoff=%s", persisted_go_live)

    success = True

    for device in get_devices(cfg, only_device):
        adapter = build_adapter(device)
        try:
            if odoo.enabled:
                employee_ids = odoo.get_allowed_employee_ids(device["id"])
                _logger.info(
                    "Device %s allowed employee mappings=%s",
                    device["id"],
                    len(employee_ids),
                )
                if not employee_ids:
                    _logger.warning(
                        "Device %s has no active employee mappings in Odoo; skipping collection.",
                        device["id"],
                    )
                    continue
            else:
                employee_ids = configured_employee_ids

            status = adapter.test_connection()
            _logger.info("Device %s connection OK: %s", device["id"], status)

            cursor_key = f"device_fetch_cursor:{device['id']}"
            is_hikvision = str(device.get("type", "")).lower() == "hikvision"
            if is_hikvision:
                previous_cursor = db.get_setting(cursor_key)
                overlap_minutes = int(
                    device.get("cursor_overlap_minutes", 360)
                )
                fetch_start = compute_fetch_start(
                    floor=from_date,
                    cursor=previous_cursor,
                    overlap_minutes=overlap_minutes,
                )
                _logger.info(
                    "Device %s fetch cursor previous=%s overlap_minutes=%s start=%s",
                    device["id"],
                    previous_cursor or "NONE",
                    overlap_minutes,
                    fetch_start.isoformat(timespec="seconds"),
                )
                raw = adapter.fetch_events(start_time=fetch_start)
            else:
                raw = adapter.fetch_events()

            _logger.info("Device %s raw fetched=%s", device["id"], len(raw))

            filtered = filter_events(
                raw,
                from_date=from_date,
                to_date=to_date,
                employee_ids=employee_ids,
            )
            _logger.info(
                "Device %s after filters=%s from=%s to=%s employees=%s",
                device["id"],
                len(filtered),
                from_date,
                to_date,
                employee_ids if employee_ids is not None else "ALL",
            )

            last_event_time = max(
                (e["event_time"] for e in filtered if e.get("event_time")),
                default=None,
            )

            new_count = db.add_events_bulk(filtered, chunk_size=batch_size)

            if is_hikvision:
                db.set_setting(
                    cursor_key,
                    adapter.last_query_end,
                    overwrite=True,
                )
                _logger.info(
                    "Device %s fetch cursor advanced=%s",
                    device["id"],
                    adapter.last_query_end,
                )

            db.update_device_state(
                device["id"],
                fetched=len(raw),
                new_count=new_count,
                last_event_time=last_event_time,
                error=None,
            )
            _logger.info("Device %s stored new=%s", device["id"], new_count)

        except Exception as exc:
            success = False
            db.update_device_state(
                device.get("id", "unknown"),
                fetched=0,
                new_count=0,
                error=str(exc),
            )
            _logger.exception("Device %s failed: %s", device.get("id"), exc)

    if not send_pending(db, odoo):
        success = False

    if not send_heartbeat(db, odoo):
        success = False

    return success


def show_status(db):
    states = db.get_device_states()
    if not states:
        print("No device sync state yet.")
        return
    for row in states:
        print(row)


def test_device(cfg, device_id):
    device = get_devices(cfg, device_id)[0]
    adapter = build_adapter(device)
    print(device_id, adapter.test_connection())


def main(args):
    cfg = load_config()
    setup_logging(cfg["app"]["log_path"], cfg["app"].get("log_level", "INFO"))
    db = Database(cfg["app"]["database_path"])
    odoo = OdooClient(cfg.get("odoo", {}))

    if args.version:
        print(MIDDLEWARE_VERSION)
        return 0

    if args.status:
        show_status(db)
        return 0

    if args.test_device:
        test_device(cfg, args.test_device)
        return 0

    if args.send_only:
        return 0 if send_pending(db, odoo) else 2

    if args.once:
        ok = run_cycle(
            cfg,
            db,
            odoo,
            only_device=args.device,
            from_date_override=args.from_date,
        )
        return 0 if ok else 2

    loop_interval = max(
        10,
        int(cfg["app"].get("poll_interval_seconds", 30)),
    )
    devices = get_devices(cfg, args.device)
    next_due = {device["id"]: 0.0 for device in devices}

    _logger.info(
        "Middleware service loop started. supervisor_interval=%ss version=%s",
        loop_interval,
        MIDDLEWARE_VERSION,
    )
    for device in devices:
        _logger.info(
            "Device %s collection interval=%ss",
            device["id"],
            device_poll_interval(device),
        )

    while True:
        now = time.monotonic()
        collected = False

        for device in devices:
            if now < next_due[device["id"]]:
                continue

            run_cycle(
                cfg,
                db,
                odoo,
                only_device=device["id"],
                from_date_override=args.from_date,
            )
            next_due[device["id"]] = (
                time.monotonic() + device_poll_interval(device)
            )
            collected = True

        if not collected:
            send_pending(db, odoo)
            send_heartbeat(db, odoo)

        time.sleep(loop_interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--device")
    parser.add_argument("--from-date")
    parser.add_argument("--test-device")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--send-only", action="store_true")
    parser.add_argument("--version", action="store_true")
    sys.exit(main(parser.parse_args()))