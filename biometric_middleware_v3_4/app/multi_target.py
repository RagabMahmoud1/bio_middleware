"""Opt-in multi-Odoo delivery. The legacy single-target service is unchanged."""
import logging
import re
from datetime import datetime

from .odoo_client import OdooClient
from .version import MIDDLEWARE_VERSION

_logger = logging.getLogger(__name__)
_TARGET_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class MultiTargetRuntime:
    """Collection allowlist is the union; delivery state is per Odoo database."""

    def __init__(self, config, db):
        self.db = db
        raw_targets = config.get("odoo_targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise ValueError("odoo_targets must be a non-empty list")
        legacy_id = config.get("legacy_target_id")
        if not isinstance(legacy_id, str) or not _TARGET_ID.fullmatch(legacy_id):
            raise ValueError("legacy_target_id is required for existing databases")
        self.targets = []
        self._by_device = {}
        ids = set()
        for item in raw_targets:
            if not isinstance(item, dict):
                raise ValueError("odoo_targets entries must be mappings")
            target_id = item.get("id")
            if not isinstance(target_id, str) or not _TARGET_ID.fullmatch(target_id):
                raise ValueError("Each target needs a stable lowercase id")
            if target_id in ids:
                raise ValueError("Duplicate Odoo target id")
            ids.add(target_id)
            if not item.get("enabled", False):
                continue
            if not item.get("base_url") or not item.get("api_token"):
                raise ValueError("Enabled targets require base_url and api_token")
            client = OdooClient(item)
            device_ids = item.get("device_ids")
            if device_ids is not None and not isinstance(device_ids, list):
                raise ValueError("device_ids must be a list when provided")
            start_at = item.get("start_at")
            if target_id != legacy_id and not start_at:
                raise ValueError("New target requires explicit start_at")
            if start_at:
                parsed = datetime.fromisoformat(str(start_at))
                if parsed.tzinfo is None:
                    raise ValueError("start_at requires an explicit timezone offset")
            self.targets.append((target_id, client, set(device_ids) if device_ids is not None else None, start_at))
        if legacy_id not in ids:
            raise ValueError("Legacy target is missing")
        legacy = next(item for item in raw_targets if item["id"] == legacy_id)
        previous_odoo_url = (config.get("odoo") or {}).get("base_url")
        if not previous_odoo_url or previous_odoo_url.rstrip("/").lower() != str(legacy.get("base_url", "")).rstrip("/").lower():
            raise ValueError("Legacy target URL must match existing odoo.base_url")
        if not any(target_id == legacy_id for target_id, *_ in self.targets):
            raise ValueError("Legacy target must stay enabled during migration")
        self.db.initialize_delivery_ledger(legacy_id)

    @property
    def enabled(self):
        return True

    def get_allowed_employee_ids(self, device_id):
        """Fail closed: never advance a device cursor on a partial target lookup."""
        mapping = {}
        union = set()
        for target_id, client, device_ids, start_at in self.targets:
            if device_ids is not None and device_id not in device_ids:
                continue
            codes = set(client.get_allowed_employee_ids(device_id))
            mapping[target_id] = (codes, start_at)
            union.update(codes)
        self._by_device[device_id] = mapping
        return sorted(union)

    def queue_captured(self, device_id):
        for target_id, (codes, start_at) in self._by_device.get(device_id, {}).items():
            self.db.queue_target_device(target_id, device_id, codes, start_at)

    def send_pending(self):
        overall_ok = True
        for target_id, client, _device_ids, _start_at in self.targets:
            while True:
                pending = self.db.pending_for_target(target_id, limit=200)
                if not pending:
                    break
                ids = [row["id"] for row in pending]
                try:
                    result = client.send(pending)
                    accepted = result.get("accepted_ids") or []
                    ignored = result.get("ignored_ids") or []
                    rejected = result.get("rejected_items") or []
                    unhandled = result.get("unhandled_ids") or []
                    self.db.mark_target_delivery(target_id, accepted, "synced")
                    self.db.mark_target_delivery(target_id, ignored, "ignored", "unknown_or_ambiguous_employee_in_odoo")
                    self.db.mark_target_rejected(target_id, rejected)
                    self.db.mark_target_push_success(target_id, accepted + ignored + [row["id"] for row in rejected])
                    _logger.info(
                        "Odoo target=%s accepted=%d ignored=%d rejected=%d unhandled=%d",
                        target_id, len(accepted), len(ignored), len(rejected), len(unhandled),
                    )
                    if unhandled:
                        self.db.mark_target_retry(target_id, unhandled, "Odoo did not acknowledge events")
                        overall_ok = False
                        break
                except Exception as exc:
                    self.db.mark_target_retry(target_id, ids, str(exc))
                    _logger.exception("Odoo target=%s delivery failed", target_id)
                    overall_ok = False
                    break
        return overall_ok

    def send_heartbeat(self):
        all_ok = True
        states = self.db.get_device_states()
        for target_id, client, device_ids, _start_at in self.targets:
            eligible = []
            for state in states:
                device_id = state["device_id"]
                if device_ids is not None and device_id not in device_ids:
                    continue
                stats = self.db.target_queue_stats(target_id, device_id)
                eligible.append({
                    "device_id": device_id,
                    "last_device_fetch_success": state.get("last_device_fetch_success") or state.get("last_successful_sync"),
                    "last_device_event_time": state.get("last_event_time"),
                    "last_odoo_push_success": self.db.target_last_push(target_id, device_id),
                    "last_error": state.get("last_error"),
                    "pending_count": stats["pending"],
                    "failed_count": stats["failed"],
                    "ignored_count": stats["ignored"],
                })
            try:
                result = client.heartbeat({
                    "middleware_version": MIDDLEWARE_VERSION,
                    "queue": self.db.target_queue_stats(target_id),
                    "devices": eligible,
                })
                _logger.info("Odoo target=%s heartbeat accepted devices=%s", target_id, result.get("updated_devices", 0))
            except Exception:
                _logger.exception("Odoo target=%s heartbeat failed", target_id)
                all_ok = False
        return all_ok