"""SQLite Storage Layer for Mars Mission Control.

Provides thread-safe persistence for:
1. Validated telemetry (5-minute sliding retention)
2. Mission events (connection, sensor-health, and recovery transitions)
3. Command lifecycle history
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Optional

from app.storage.schema import ALL_SCHEMA_STATEMENTS

logger = logging.getLogger(__name__)


class SQLiteStorage:
    """Thread-safe SQLite storage repository for Mars Mission Control."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = RLock()

        # Ensure parent directory exists for file-based database
        if self.db_path != ":memory:":
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode / manual transactions
        )
        self._conn.row_factory = sqlite3.Row

        self._initialize_database()

    def _initialize_database(self) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys = ON;")
                cursor.execute("PRAGMA busy_timeout = 5000;")
                if self.db_path != ":memory:":
                    cursor.execute("PRAGMA journal_mode = WAL;")
                    cursor.execute("PRAGMA synchronous = NORMAL;")

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetry'")
                if cursor.fetchone() is not None:
                    columns = {row[1] for row in cursor.execute("PRAGMA table_info(telemetry)")}
                    if "gate_state" in columns or "closed_limit" in columns or "fault" in columns:
                        cursor.execute("BEGIN")
                        cursor.execute("""CREATE TABLE telemetry_clean (
                            id INTEGER PRIMARY KEY AUTOINCREMENT, received_at TEXT NOT NULL,
                            received_at_epoch REAL NOT NULL, timestamp_ms INTEGER NOT NULL,
                            mode TEXT NOT NULL, bmp_temperature_c REAL, pressure_hpa REAL,
                            dht_temperature_c REAL, humidity_pct REAL, bmp280_ok INTEGER, dht11_ok INTEGER
                        )""")
                        retained = [name for name in ("id", "received_at", "received_at_epoch", "timestamp_ms", "mode",
                            "bmp_temperature_c", "pressure_hpa", "dht_temperature_c", "humidity_pct", "bmp280_ok", "dht11_ok") if name in columns]
                        names = ", ".join(retained)
                        cursor.execute(f"INSERT INTO telemetry_clean ({names}) SELECT {names} FROM telemetry")
                        cursor.execute("DROP TABLE telemetry")
                        cursor.execute("ALTER TABLE telemetry_clean RENAME TO telemetry")
                        cursor.execute("COMMIT")

                for statement in ALL_SCHEMA_STATEMENTS:
                    cursor.execute(statement)
                # These persisted records describe a mechanism removed from the
                # project. Device connection, sensor, recovery, and other event
                # history remains available.
                cursor.execute("DELETE FROM mission_events WHERE event_type IN ('GATE_STATE_CHANGE', 'FAULT_RAISED', 'FAULT_CLEARED')")
                cursor.execute("DELETE FROM commands WHERE name IN ('OPEN_GATE', 'CLOSE_GATE')")
            finally:
                cursor.close()

    def insert_telemetry(
        self,
        telemetry: dict[str, Any],
        received_at: Optional[datetime] = None,
    ) -> int:
        """
        Persist a validated telemetry line with independent backend receive timestamp.
        """
        now = received_at or datetime.now(timezone.utc)
        recv_iso = now.isoformat()
        recv_epoch = now.timestamp()

        # Validate mandatory telemetry fields are present
        required_fields = ("timestamp_ms", "mode")
        for field in required_fields:
            if field not in telemetry:
                raise ValueError(f"Missing required telemetry field for persistence: {field}")

        query = """
        INSERT INTO telemetry (
            received_at, received_at_epoch, timestamp_ms, mode, bmp_temperature_c, pressure_hpa,
            dht_temperature_c, humidity_pct, bmp280_ok, dht11_ok
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        params = (
            recv_iso,
            recv_epoch,
            int(telemetry["timestamp_ms"]),
            str(telemetry["mode"]),
            telemetry.get("bmp_temperature_c"),
            telemetry.get("pressure_hpa"),
            telemetry.get("dht_temperature_c"),
            telemetry.get("humidity_pct"),
            1 if telemetry.get("bmp280_ok") else 0 if telemetry.get("bmp280_ok") is False else None,
            1 if telemetry.get("dht11_ok") else 0 if telemetry.get("dht11_ok") is False else None,
        )

        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(query, params)
                inserted_id = cursor.lastrowid
                return inserted_id or 0
            finally:
                cursor.close()

    def get_telemetry_history(
        self,
        limit: int = 300,
        since_epoch: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """Query historical telemetry ordered chronologically."""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                if since_epoch is not None:
                    query = """
                    SELECT * FROM telemetry
                    WHERE received_at_epoch >= ?
                    ORDER BY received_at_epoch ASC
                    LIMIT ?;
                    """
                    cursor.execute(query, (since_epoch, limit))
                else:
                    query = """
                    SELECT * FROM telemetry
                    ORDER BY received_at_epoch DESC
                    LIMIT ?;
                    """
                    cursor.execute(query, (limit,))

                rows = cursor.fetchall()
            finally:
                cursor.close()

            results = [dict(row) for row in rows]
            if since_epoch is None:
                results.reverse()  # Chronological order
            return results

    def prune_telemetry(
        self,
        retention_seconds: float = 300.0,
        current_time: Optional[datetime] = None,
    ) -> int:
        """
        Deterministic retention cleanup.
        Prunes all telemetry older than retention_seconds relative to current_time.
        """
        now = current_time or datetime.now(timezone.utc)
        cutoff_epoch = now.timestamp() - retention_seconds

        query = "DELETE FROM telemetry WHERE received_at_epoch < ?;"
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(query, (cutoff_epoch,))
                return cursor.rowcount
            finally:
                cursor.close()

    def insert_event(
        self,
        event_type: str,
        severity: str,
        subsystem: str,
        description: str,
        details: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Persist a significant mission event."""
        now = timestamp or datetime.now(timezone.utc)
        ts_iso = now.isoformat()
        ts_epoch = now.timestamp()
        details_json = json.dumps(details) if details is not None else None

        query = """
        INSERT INTO mission_events (
            timestamp, timestamp_epoch, event_type, severity, subsystem, description, details
        ) VALUES (?, ?, ?, ?, ?, ?, ?);
        """
        params = (ts_iso, ts_epoch, event_type, severity, subsystem, description, details_json)

        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(query, params)
                inserted_id = cursor.lastrowid
                return inserted_id or 0
            finally:
                cursor.close()

    def get_events(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Query mission events ordered newest first."""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                if event_type is not None:
                    query = """
                    SELECT * FROM mission_events
                    WHERE event_type = ?
                    ORDER BY timestamp_epoch DESC
                    LIMIT ?;
                    """
                    cursor.execute(query, (event_type, limit))
                else:
                    query = """
                    SELECT * FROM mission_events
                    ORDER BY timestamp_epoch DESC
                    LIMIT ?;
                    """
                    cursor.execute(query, (limit,))

                rows = cursor.fetchall()
            finally:
                cursor.close()

            results = []
            for row in rows:
                item = dict(row)
                if item.get("details"):
                    try:
                        item["details"] = json.loads(item["details"])
                    except Exception:
                        pass
                results.append(item)
            return results

    def save_command(self, cmd_data: dict[str, Any]) -> None:
        """Upsert command and its latest lifecycle status."""
        query = """
        INSERT INTO commands (
            command_id, name, status, created_at, acknowledged_at, completed_at,
            error_reason, params, missing_ack, reconciliation_note, dispatched_at_ms,
            outcome_resolved
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(command_id) DO UPDATE SET
            status = excluded.status,
            acknowledged_at = excluded.acknowledged_at,
            completed_at = excluded.completed_at,
            error_reason = excluded.error_reason,
            params = excluded.params,
            missing_ack = excluded.missing_ack,
            reconciliation_note = excluded.reconciliation_note,
            dispatched_at_ms = excluded.dispatched_at_ms,
            outcome_resolved = excluded.outcome_resolved;
        """
        params_json = json.dumps(cmd_data.get("params")) if cmd_data.get("params") is not None else None
        params = (
            str(cmd_data["command_id"]),
            str(cmd_data["name"]),
            str(cmd_data["status"]),
            str(cmd_data["created_at"]),
            cmd_data.get("acknowledged_at"),
            cmd_data.get("completed_at"),
            cmd_data.get("error_reason"),
            params_json,
            1 if cmd_data.get("missing_ack") else 0,
            cmd_data.get("reconciliation_note"),
            cmd_data.get("dispatched_at_ms"),
            1 if cmd_data.get("outcome_resolved") else 0,
        )

        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute(query, params)
            finally:
                cursor.close()

    def get_command(self, command_id: str) -> Optional[dict[str, Any]]:
        """Query a single command by ID."""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("SELECT * FROM commands WHERE command_id = ?;", (command_id,))
                row = cursor.fetchone()
            finally:
                cursor.close()

            if not row:
                return None
            res = dict(row)
            if res.get("params"):
                try:
                    res["params"] = json.loads(res["params"])
                except Exception:
                    pass
            res["missing_ack"] = bool(res.get("missing_ack", 0))
            res["outcome_resolved"] = bool(res.get("outcome_resolved", 0))
            return res

    def list_commands(self, limit: int = 100) -> list[dict[str, Any]]:
        """Query commands ordered newest first."""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("SELECT * FROM commands ORDER BY created_at DESC LIMIT ?;", (limit,))
                rows = cursor.fetchall()
            finally:
                cursor.close()

            results = []
            for row in rows:
                item = dict(row)
                if item.get("params"):
                    try:
                        item["params"] = json.loads(item["params"])
                    except Exception:
                        pass
                item["missing_ack"] = bool(item.get("missing_ack", 0))
                item["outcome_resolved"] = bool(item.get("outcome_resolved", 0))
                results.append(item)
            return results

    def reset_session(self) -> None:
        """
        Explicit session reset. Clears current demo session's telemetry, events,
        and command history without deleting unrelated database files.
        """
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE;")
                cursor.execute("DELETE FROM telemetry;")
                cursor.execute("DELETE FROM mission_events;")
                cursor.execute("DELETE FROM commands;")
                cursor.execute("COMMIT;")
            except Exception:
                cursor.execute("ROLLBACK;")
                raise
            finally:
                cursor.close()

            # Record session reset event
            self.insert_event(
                event_type="SESSION_RESET",
                severity="INFO",
                subsystem="MISSION",
                description="Demo session history reset completed.",
            )

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
