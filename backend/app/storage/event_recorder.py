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

        # 1. Gate State Transition
        prev_gate = previous_state.get("gate_state")
        curr_gate = current_state.get("gate_state")
        if curr_gate and prev_gate != curr_gate:
            severity = "WARNING" if curr_gate == "FAULT" else "INFO"
            event_id = self.storage.insert_event(
                event_type="GATE_STATE_CHANGE",
                severity=severity,
                subsystem="GATE",
                description=f"Gate transitioned from {prev_gate} to {curr_gate}",
                details={
                    "from_state": prev_gate,
                    "to_state": curr_gate,
                    "closed_limit": current_state.get("closed_limit"),
                    "open_limit": current_state.get("open_limit"),
                },
                timestamp=now,
            )
            inserted_event_ids.append(event_id)

        # 2. Hardware Faults
        prev_fault = previous_state.get("fault")
        curr_fault = current_state.get("fault")
        if curr_fault != prev_fault:
            if curr_fault:
                event_id = self.storage.insert_event(
                    event_type="FAULT_RAISED",
                    severity="ERROR",
                    subsystem="DEVICE",
                    description=f"Hardware fault latched: {curr_fault}",
                    details={"fault": curr_fault},
                    timestamp=now,
                )
                inserted_event_ids.append(event_id)
            else:
                event_id = self.storage.insert_event(
                    event_type="FAULT_CLEARED",
                    severity="INFO",
                    subsystem="DEVICE",
                    description="Hardware fault cleared or reset",
                    details={"previous_fault": prev_fault},
                    timestamp=now,
                )
                inserted_event_ids.append(event_id)

        # 3. Gateway Connection Transition
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

        # 4. Device Connection Transition
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
