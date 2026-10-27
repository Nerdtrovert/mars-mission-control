"""Thread-safe mission connectivity, operating mode, and lander sensor state."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Optional


@dataclass
class MissionState:
    mode: str = "UNKNOWN"
    last_telemetry_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    gateway_state: str = "NOT_CONNECTED"
    device_state: str = "NOT_CONNECTED"
    last_gateway_heartbeat_at: Optional[str] = None
    last_device_telemetry_at: Optional[str] = None
    last_telemetry_timestamp_ms: Optional[int] = None
    last_device_status_timestamp_ms: Optional[int] = None
    bmp280_ok: Optional[bool] = None
    dht11_ok: Optional[bool] = None


class MissionStateManager:
    VALID_MODES = {"ACTIVE", "STANDBY"}
    VALID_CONNECTION_STATES = {"ONLINE", "STALE", "OFFLINE", "NOT_CONNECTED"}

    def __init__(self) -> None:
        self._state = MissionState()
        self._lock = RLock()
        self._listener: Optional[Callable[[dict, dict], None]] = None

    def set_listener(self, listener: Optional[Callable[[dict, dict], None]]) -> None:
        with self._lock:
            self._listener = listener

    def _notify_if_changed(self, previous: dict, current: dict) -> None:
        fields = (
            "mode", "device_state", "gateway_state", "last_device_status_timestamp_ms",
            "bmp280_ok", "dht11_ok",
        )
        if self._listener and any(previous.get(name) != current.get(name) for name in fields):
            try:
                self._listener(previous, current)
            except Exception:
                pass

    def reset(self, preserve_connections: bool = False) -> dict:
        with self._lock:
            previous = self.snapshot()
            if preserve_connections:
                old = self._state
                self._state = MissionState(
                    gateway_state=old.gateway_state,
                    device_state=old.device_state,
                    last_gateway_heartbeat_at=old.last_gateway_heartbeat_at,
                    last_device_telemetry_at=old.last_device_telemetry_at,
                )
            else:
                self._state = MissionState()
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self._state.mode,
                "last_telemetry_at": self._state.last_telemetry_at,
                "updated_at": self._state.updated_at,
                "gateway_state": self._state.gateway_state,
                "device_state": self._state.device_state,
                "last_gateway_heartbeat_at": self._state.last_gateway_heartbeat_at,
                "last_device_telemetry_at": self._state.last_device_telemetry_at,
                "last_telemetry_timestamp_ms": self._state.last_telemetry_timestamp_ms,
                "last_device_status_timestamp_ms": self._state.last_device_status_timestamp_ms,
                "bmp280_ok": self._state.bmp280_ok,
                "dht11_ok": self._state.dht11_ok,
            }

    def update_from_telemetry(self, telemetry: dict, timestamp: Optional[str] = None) -> dict:
        with self._lock:
            previous = self.snapshot()
            incoming_ms = telemetry["timestamp_ms"]
            last_ms = self._state.last_telemetry_timestamp_ms
            rebooted = False
            if last_ms is not None and incoming_ms < last_ms:
                rebooted = self._state.device_state != "ONLINE" or last_ms - incoming_ms > 2000
                if not rebooted:
                    return self.snapshot()
            if rebooted:
                self._state.last_device_status_timestamp_ms = None
            watermark = self._state.last_device_status_timestamp_ms
            if watermark is not None and incoming_ms < watermark:
                return self.snapshot()

            now = timestamp or datetime.now(timezone.utc).isoformat()
            self._state.mode = telemetry["mode"]
            self._state.last_telemetry_timestamp_ms = incoming_ms
            self._state.last_telemetry_at = now
            self._state.last_device_telemetry_at = now
            self._state.updated_at = now
            self._state.device_state = "ONLINE"
            self._state.bmp280_ok = telemetry["bmp280_ok"]
            self._state.dht11_ok = telemetry["dht11_ok"]
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def update_from_device_status(self, status: dict) -> dict:
        with self._lock:
            previous = self.snapshot()
            if status.get("mode") in self.VALID_MODES:
                self._state.mode = status["mode"]
            status_ms = status.get("timestamp_ms")
            if isinstance(status_ms, int) and not isinstance(status_ms, bool) and status_ms >= 0:
                self._state.last_device_status_timestamp_ms = status_ms
            for sensor in ("bmp280_ok", "dht11_ok"):
                value = status.get(sensor)
                setattr(self._state, sensor, value if isinstance(value, bool) else None)
            self._state.device_state = "ONLINE"
            self._state.updated_at = datetime.now(timezone.utc).isoformat()
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def update_gateway_health(self, state: str, timestamp: Optional[str] = None) -> dict:
        with self._lock:
            previous = self.snapshot()
            if state in self.VALID_CONNECTION_STATES:
                self._state.gateway_state = state
                now = timestamp or datetime.now(timezone.utc).isoformat()
                if state == "ONLINE":
                    self._state.last_gateway_heartbeat_at = now
                self._state.updated_at = now
                if state in ("OFFLINE", "NOT_CONNECTED") and self._state.device_state == "ONLINE":
                    self._state.device_state = "OFFLINE"
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def update_device_health(self, state: str, timestamp: Optional[str] = None) -> dict:
        with self._lock:
            previous = self.snapshot()
            if state in self.VALID_CONNECTION_STATES:
                self._state.device_state = state
                now = timestamp or datetime.now(timezone.utc).isoformat()
                if state == "ONLINE":
                    self._state.last_device_telemetry_at = now
                self._state.updated_at = now
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def handle_disconnect(self, subsystem: str) -> dict:
        with self._lock:
            previous = self.snapshot()
            now = datetime.now(timezone.utc).isoformat()
            if subsystem == "gateway":
                self._state.gateway_state = "OFFLINE"
                self._state.device_state = "OFFLINE"
            elif subsystem == "device":
                self._state.device_state = "OFFLINE"
            self._state.updated_at = now
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def handle_reconnect(self, subsystem: str) -> dict:
        with self._lock:
            previous = self.snapshot()
            now = datetime.now(timezone.utc).isoformat()
            if subsystem == "gateway":
                self._state.gateway_state = "ONLINE"
                self._state.last_gateway_heartbeat_at = now
            elif subsystem == "device":
                self._state.device_state = "ONLINE"
                self._state.last_device_telemetry_at = now
            self._state.updated_at = now
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def check_staleness(
        self,
        current_time: datetime,
        stale_threshold_s: float = 3.0,
        offline_threshold_s: float = 10.0,
    ) -> dict:
        with self._lock:
            previous = self.snapshot()
            self._check_one("device_state", "last_device_telemetry_at", current_time, stale_threshold_s, offline_threshold_s)
            self._check_one("gateway_state", "last_gateway_heartbeat_at", current_time, stale_threshold_s, offline_threshold_s)
            if self._state.gateway_state in ("OFFLINE", "NOT_CONNECTED") and self._state.device_state == "ONLINE":
                self._state.device_state = "OFFLINE"
            self._state.updated_at = current_time.isoformat()
            current = self.snapshot()
            self._notify_if_changed(previous, current)
            return current

    def _check_one(self, state_attr: str, timestamp_attr: str, now: datetime, stale_s: float, offline_s: float) -> None:
        state = getattr(self._state, state_attr)
        timestamp = getattr(self._state, timestamp_attr)
        if state not in ("ONLINE", "STALE") or not timestamp:
            return
        elapsed = (now - datetime.fromisoformat(timestamp)).total_seconds()
        if elapsed >= offline_s:
            setattr(self._state, state_attr, "OFFLINE")
        elif elapsed >= stale_s:
            setattr(self._state, state_attr, "STALE")
