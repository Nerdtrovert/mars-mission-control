"""Mission Event Recorder for Mars Mission Control.

Detects state transitions and persists structured events with deduplication.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Optional

from app.storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger(__name__)


class MissionEventRecorder:
    """Evaluates state snapshots and records non-duplicate mission events."""

    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def evaluate_state_transition(
        self,
        previous_state: dict[str, Any],
        current_state: dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> list[int]:
        """
        Compare previous and current state snapshots.
        Inserts events only when a meaningful transition occurs.
        """
        now = timestamp or datetime.now(timezone.utc)
        inserted_event_ids: list[int] = []

        # Gateway Connection Transition
        prev_gw = previous_state.get("gateway_state")
        curr_gw = current_state.get("gateway_state")
        if curr_gw and prev_gw != curr_gw:
            severity = "WARNING" if curr_gw in ("OFFLINE", "STALE") else "INFO"
            event_id = self.storage.insert_event(
                event_type="CONNECTION_CHANGE",
                severity=severity,
                subsystem="GATEWAY",
                description=f"Gateway health transitioned from {prev_gw} to {curr_gw}",
                details={"from_state": prev_gw, "to_state": curr_gw},
                timestamp=now,
            )
            inserted_event_ids.append(event_id)

        # Device Connection Transition
        prev_dev = previous_state.get("device_state")
        curr_dev = current_state.get("device_state")
        if curr_dev and prev_dev != curr_dev:
            severity = "WARNING" if curr_dev in ("OFFLINE", "STALE") else "INFO"
            event_id = self.storage.insert_event(
                event_type="CONNECTION_CHANGE",
                severity=severity,
                subsystem="DEVICE",
                description=f"ESP32 device health transitioned from {prev_dev} to {curr_dev}",
                details={"from_state": prev_dev, "to_state": curr_dev},
                timestamp=now,
            )
            inserted_event_ids.append(event_id)

        for field, label in (("bmp280_ok", "BMP280"), ("dht11_ok", "DHT11")):
            previous = previous_state.get(field)
            current = current_state.get(field)
            if current is not None and previous != current:
                event_id = self.storage.insert_event(
                    event_type="SENSOR_HEALTH_CHANGE",
                    severity="INFO" if current else "WARNING",
                    subsystem=label,
                    description=f"{label} sensor state changed to {'OK' if current else 'FAILED'}",
                    details={"sensor": label, "healthy": current},
                    timestamp=now,
                )
                inserted_event_ids.append(event_id)

        return inserted_event_ids

    def record_recovery(
        self,
        subsystem: str,
        description: str,
        details: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Record a verified recovery event."""
        return self.storage.insert_event(
            event_type="RECOVERY",
            severity="INFO",
            subsystem=subsystem,
            description=description,
            details=details,
            timestamp=timestamp,
        )
