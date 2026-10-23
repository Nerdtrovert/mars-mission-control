from datetime import datetime, timezone
import logging
from typing import Any, Callable, Optional

from app.mission.state import MissionStateManager
from app.telemetry.processor import parse_telemetry
from app.storage.sqlite_storage import SQLiteStorage
from app.storage.event_recorder import MissionEventRecorder

logger = logging.getLogger(__name__)


class TelemetryService:
    def __init__(
        self,
        state_manager: MissionStateManager,
        storage: Optional[SQLiteStorage] = None,
        event_recorder: Optional[MissionEventRecorder] = None,
        retention_seconds: float = 300.0,
        prune_interval_s: float = 5.0,
        telemetry_listener: Optional[Callable[[dict, dict], None]] = None,
    ):
        self.state_manager = state_manager
        self.storage = storage
        self.event_recorder = event_recorder
        self.retention_seconds = retention_seconds
        self.prune_interval_s = prune_interval_s
        self._last_prune_epoch: float = 0.0
        self._telemetry_listener = telemetry_listener

    def set_telemetry_listener(self, listener: Optional[Callable[[dict, dict], None]]) -> None:
        """Register a callback invoked when telemetry is ingested and validated."""
        self._telemetry_listener = listener

    def process_line(self, line: str, timestamp: Optional[str] = None) -> dict[str, Any]:
        telemetry = parse_telemetry(line)
        prev_snapshot = self.state_manager.snapshot()
        state = self.state_manager.update_from_telemetry(telemetry, timestamp=timestamp)

        if timestamp:
            try:
                recv_dt = datetime.fromisoformat(timestamp)
            except Exception:
                recv_dt = datetime.now(timezone.utc)
        else:
            recv_dt = datetime.now(timezone.utc)

        # Attach host receipt timestamp to the telemetry dictionary before storage & broadcasting
        telemetry["received_at"] = recv_dt.isoformat()

        if self.storage is not None:
            try:
                self.storage.insert_telemetry(telemetry, received_at=recv_dt)
                # Deterministic telemetry retention pruning operates in both simulator and real gateway modes
                now_epoch = recv_dt.timestamp()
                if (now_epoch - self._last_prune_epoch) >= self.prune_interval_s:
                    self.storage.prune_telemetry(retention_seconds=self.retention_seconds, current_time=recv_dt)
                    self._last_prune_epoch = now_epoch
            except Exception as e:
                logger.error(f"Failed to persist or prune telemetry: {e}")

        if self.event_recorder is not None:
            try:
                self.event_recorder.evaluate_state_transition(prev_snapshot, state, timestamp=recv_dt)
            except Exception as e:
                logger.error(f"Failed to record event transition: {e}")

        if self._telemetry_listener is not None:
            try:
                self._telemetry_listener(telemetry, state)
            except Exception as e:
                logger.error(f"Failed to notify telemetry listener: {e}")

        return {
            "telemetry": telemetry,
            "mission_state": state,
        }
