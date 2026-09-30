import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key TEXT NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    device_type TEXT NOT NULL,
    employee_code TEXT,
    event_time TEXT NOT NULL,
    event_type TEXT,
    raw_json TEXT,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    sync_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    synced_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_status
    ON events(sync_status);

CREATE INDEX IF NOT EXISTS idx_events_time
    ON events(event_time);

CREATE INDEX IF NOT EXISTS idx_events_device_time
    ON events(device_id, event_time);

CREATE TABLE IF NOT EXISTS device_sync_state (
    device_id TEXT PRIMARY KEY,
    last_event_time TEXT,
    last_successful_sync TEXT,
    last_device_fetch_success TEXT,
    last_odoo_push_success TEXT,
    last_fetch_count INTEGER NOT NULL DEFAULT 0,
    last_new_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS integration_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_legacy_schema(conn)

    def connect(self):
        return sqlite3.connect(self.path, timeout=60)

    def _migrate_legacy_schema(self, conn):
        """
        Make older v2/v3 SQLite files compatible with the current code.
        This is intentionally additive and does not delete existing data.
        """
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(events)").fetchall()
        }

        migrations = [
            ("sync_attempts", "ALTER TABLE events ADD COLUMN sync_attempts INTEGER NOT NULL DEFAULT 0"),
            ("last_error", "ALTER TABLE events ADD COLUMN last_error TEXT"),
            ("synced_at", "ALTER TABLE events ADD COLUMN synced_at TEXT"),
        ]

        for column, sql in migrations:
            if column not in cols:
                conn.execute(sql)

        state_cols = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(device_sync_state)"
            ).fetchall()
        }
        state_migrations = [
            (
                "last_device_fetch_success",
                "ALTER TABLE device_sync_state "
                "ADD COLUMN last_device_fetch_success TEXT",
            ),
            (
                "last_odoo_push_success",
                "ALTER TABLE device_sync_state "
                "ADD COLUMN last_odoo_push_success TEXT",
            ),
        ]
        for column, sql in state_migrations:
            if column not in state_cols:
                conn.execute(sql)

        conn.commit()

    @staticmethod
    def make_event_key(event):
        stable = "|".join(
            [
                str(event.get("device_id", "")),
                str(event.get("employee_code", "")),
                str(event.get("event_time", "")),
                str(event.get("event_type", "")),
                str(event.get("source_event_id", "")),
            ]
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    # Backward-compatible alias used by some earlier builds.
    @staticmethod
    def key(event):
        return Database.make_event_key(event)

    def get_setting(self, key):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM integration_state WHERE key = ?",
                (key,),
            ).fetchone()
            return row[0] if row else None

    def set_setting(self, key, value, overwrite=False):
        now = datetime.now(timezone.utc).isoformat()

        with self.connect() as conn:
            existing = conn.execute(
                "SELECT value FROM integration_state WHERE key = ?",
                (key,),
            ).fetchone()

            if existing and not overwrite:
                return existing[0]

            conn.execute(
                """
                INSERT INTO integration_state
                    (key, value, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, str(value), now, now),
            )
            conn.commit()

        return str(value)

    def add_events_bulk(
        self,
        events,
        chunk_size=5000,
        batch_size=None,
    ):
        if not events:
            return 0

        if batch_size is not None:
            chunk_size = batch_size

        chunk_size = max(1, int(chunk_size))
        now = datetime.now(timezone.utc).isoformat()

        rows = [
            (
                self.make_event_key(event),
                event.get("device_id"),
                event.get("device_type"),
                event.get("employee_code"),
                event.get("event_time"),
                event.get("event_type"),
                json.dumps(
                    event.get("raw", {}),
                    ensure_ascii=False,
                    default=str,
                ),
                now,
            )
            for event in events
        ]

        total_new = 0

        with self.connect() as conn:
            conn.execute("PRAGMA synchronous=NORMAL")

            for start in range(0, len(rows), chunk_size):
                chunk = rows[start : start + chunk_size]
                before = conn.total_changes

                conn.executemany(
                    """
                    INSERT OR IGNORE INTO events (
                        event_key,
                        device_id,
                        device_type,
                        employee_code,
                        event_time,
                        event_type,
                        raw_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    chunk,
                )

                total_new += conn.total_changes - before

            conn.commit()

        return total_new

    def update_device_state(
        self,
        device_id,
        fetched,
        new_count,
        last_event_time=None,
        error=None,
    ):
        now = datetime.now(timezone.utc).isoformat()

        with self.connect() as conn:
            previous = conn.execute(
                """
                SELECT last_event_time, last_successful_sync
                FROM device_sync_state
                WHERE device_id = ?
                """,
                (device_id,),
            ).fetchone()

            previous_last_event = previous[0] if previous else None
            previous_success = previous[1] if previous else None

            effective_last_event = (
                last_event_time or previous_last_event
            )
            effective_success = (
                now if not error else previous_success
            )

            conn.execute(
                """
                INSERT INTO device_sync_state (
                    device_id,
                    last_event_time,
                    last_successful_sync,
                    last_device_fetch_success,
                    last_fetch_count,
                    last_new_count,
                    last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    last_event_time = excluded.last_event_time,
                    last_successful_sync = excluded.last_successful_sync,
                    last_device_fetch_success = excluded.last_device_fetch_success,
                    last_fetch_count = excluded.last_fetch_count,
                    last_new_count = excluded.last_new_count,
                    last_error = excluded.last_error
                """,
                (
                    device_id,
                    effective_last_event,
                    effective_success,
                    effective_success,
                    fetched,
                    new_count,
                    error,
                ),
            )
            conn.commit()

    def mark_odoo_push_success(self, ids):
        if not ids:
            return

        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as conn:
            device_rows = conn.execute(
                f"""
                SELECT DISTINCT device_id
                FROM events
                WHERE id IN ({placeholders})
                """,
                list(ids),
            ).fetchall()
            for row in device_rows:
                conn.execute(
                    """
                    INSERT INTO device_sync_state (
                        device_id,
                        last_odoo_push_success,
                        last_fetch_count,
                        last_new_count
                    )
                    VALUES (?, ?, 0, 0)
                    ON CONFLICT(device_id) DO UPDATE SET
                        last_odoo_push_success = excluded.last_odoo_push_success
                    """,
                    (row[0], now),
                )
            conn.commit()

    def queue_stats(self, device_id=None):
        where = ""
        params = []
        if device_id:
            where = " WHERE device_id = ?"
            params.append(str(device_id))

        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT sync_status, COUNT(*)
                FROM events
                {where}
                GROUP BY sync_status
                """,
                params,
            ).fetchall()

        counts = {str(status): int(count) for status, count in rows}
        return {
            "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0),
            "ignored": counts.get("ignored", 0),
            "synced": counts.get("synced", 0),
        }

    # Backward-compatible alias used by older builds.
    def update_state(
        self,
        device_id,
        fetched,
        new,
        last_event=None,
        error=None,
    ):
        return self.update_device_state(
            device_id=device_id,
            fetched=fetched,
            new_count=new,
            last_event_time=last_event,
            error=error,
        )

    def get_device_states(self):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT *
                FROM device_sync_state
                ORDER BY device_id
                """
            ).fetchall()
            return [dict(row) for row in rows]

    # Backward-compatible alias.
    def states(self):
        return self.get_device_states()

    def pending(self, limit=200):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT *
                FROM events
                WHERE sync_status = 'pending'
                ORDER BY id
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

            return [dict(row) for row in rows]

    def mark_synced(self, ids):
        if not ids:
            return

        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in ids)

        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE events
                SET
                    sync_status = 'synced',
                    synced_at = ?,
                    last_error = NULL
                WHERE id IN ({placeholders})
                """,
                [now, *ids],
            )
            conn.commit()

    def mark_ignored(self, ids, reason="ignored_by_odoo"):
        if not ids:
            return

        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in ids)

        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE events
                SET
                    sync_status = 'ignored',
                    synced_at = ?,
                    last_error = ?
                WHERE id IN ({placeholders})
                """,
                [now, str(reason)[:2000], *ids],
            )
            conn.commit()

    def mark_retry_error(self, ids, error):
        """Record a transient delivery failure and keep events pending."""
        if not ids:
            return

        placeholders = ",".join("?" for _ in ids)

        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE events
                SET
                    sync_attempts = sync_attempts + 1,
                    last_error = ?
                WHERE id IN ({placeholders})
                """,
                [str(error)[:2000], *ids],
            )
            conn.commit()

    def mark_rejected(self, items):
        """Permanently isolate events explicitly rejected by Odoo."""
        if not items:
            return

        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            for item in items:
                conn.execute(
                    """
                    UPDATE events
                    SET
                        sync_status = 'failed',
                        sync_attempts = sync_attempts + 1,
                        synced_at = ?,
                        last_error = ?
                    WHERE id = ?
                    """,
                    (
                        now,
                        str(item.get("error") or "rejected_by_odoo")[:2000],
                        int(item["id"]),
                    ),
                )
            conn.commit()

    # Backward-compatible name: transient errors remain pending.
    def mark_failed(self, ids, error):
        return self.mark_retry_error(ids, error)