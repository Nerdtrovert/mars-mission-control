from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Optional


@dataclass
class MissionState:
    mode: str = "ACTIVE"
    gate_state: str = "UNKNOWN"
    closed_limit: bool = False
    open_limit: bool = False
    fault: Optional[str] = None
    last_telemetry_at: Optional[str] = None
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Independent subsystem connectivity states
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
    VALID_GATE_STATES = {
        "UNKNOWN",
        "CLOSED",
        "OPEN",
        "OPENING",
        "CLOSING",
        "FAULT",
    }
    VALID_CONNECTION_STATES = {
        "ONLINE",
        "STALE",
        "OFFLINE",
        "NOT_CONNECTED",
    }

    def __init__(self):
        self._state = MissionState()
        self._lock = RLock()
        self._listener: Optional[Callable[[dict, dict], None]] = None

    def set_listener(self, listener: Optional[Callable[[dict, dict], None]]) -> None:
        """Register a callback invoked when significant state fields change."""
        with self._lock:
            self._listener = listener

    def _notify_if_changed(self, prev: dict, curr: dict) -> None:
        if self._listener is not None:
            if (
                prev.get("gate_state") != curr.get("gate_state")
                or prev.get("fault") != curr.get("fault")
                or prev.get("device_state") != curr.get("device_state")
                or prev.get("gateway_state") != curr.get("gateway_state")
                or prev.get("last_device_status_timestamp_ms") != curr.get("last_device_status_timestamp_ms")
                or prev.get("bmp280_ok") != curr.get("bmp280_ok")
                or prev.get("dht11_ok") != curr.get("dht11_ok")
            ):
                try:
                    self._listener(prev, curr)
                except Exception:
                    pass

    def reset(self, preserve_connections: bool = False) -> dict:
        """
        Reset state manager to initial state.
        If preserve_connections is True, active gateway and device connection states
        and heartbeat timestamps are preserved, while physical gate state is strictly
        reset to UNKNOWN and hardware limits/modes are cleared until fresh status is received.
        """
        with self._lock:
            prev = self.snapshot()
            if preserve_connections:
                gw_state = self._state.gateway_state
                dev_state = self._state.device_state
                last_gw = self._state.last_gateway_heartbeat_at
                last_dev = self._state.last_device_telemetry_at
                now = datetime.now(timezone.utc).isoformat()
                self._state = MissionState(
                    mode="UNKNOWN",
                    gate_state="UNKNOWN",
                    closed_limit=None,
                    open_limit=None,
                    fault=None,
                    last_telemetry_at=None,
                    updated_at=now,
                    gateway_state=gw_state,
                    device_state=dev_state,
                    last_gateway_heartbeat_at=last_gw,
                    last_device_telemetry_at=last_dev,
                    last_telemetry_timestamp_ms=None,
                    last_device_status_timestamp_ms=None,
                    bmp280_ok=None,
                    dht11_ok=None,
                )
            else:
                self._state = MissionState()
            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr

    def snapshot(self) -> dict:
        with self._lock:
            return {
                # Baseline fields preserved for backwards compatibility
                "mode": self._state.mode,
                "gate_state": self._state.gate_state,
                "closed_limit": self._state.closed_limit,
                "open_limit": self._state.open_limit,
                "fault": self._state.fault,
                "last_telemetry_at": self._state.last_telemetry_at,
                "updated_at": self._state.updated_at,
                # Extended connection and lifecycle state
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
            prev = self.snapshot()
            incoming_ms = telemetry.get("timestamp_ms")
            is_reboot = False

            # Compare against the previous telemetry clock first. The status
            # watermark belongs to that same boot and must not reject a reset
            # counter before the existing reboot heuristic can run.
            if (
                incoming_ms is not None
                and self._state.last_telemetry_timestamp_ms is not None
                and incoming_ms < self._state.last_telemetry_timestamp_ms
            ):
                is_reboot = (
                    self._state.device_state != "ONLINE"
                    or (self._state.last_telemetry_timestamp_ms - incoming_ms) > 2000
                )
                if not is_reboot:
                    # Minor jitter / out-of-order frame: reject to prevent state regression
                    return self.snapshot()

            if is_reboot:
                # A confirmed counter reset invalidates status from the old boot.
                self._state.last_device_status_timestamp_ms = None

            if (
                incoming_ms is not None
                and self._state.last_device_status_timestamp_ms is not None
                and incoming_ms < self._state.last_device_status_timestamp_ms
            ):
                # A fresh status response establishes a device-clock watermark.
                # Delayed telemetry older than it cannot replace verified state.
                return self.snapshot()

            if incoming_ms is not None:
                self._state.last_telemetry_timestamp_ms = incoming_ms

            if telemetry.get("mode") in self.VALID_MODES:
                self._state.mode = telemetry["mode"]

            if telemetry.get("gate_state") in self.VALID_GATE_STATES:
                reported_gate = telemetry["gate_state"]
                if (reported_gate == "CLOSED" and telemetry.get("closed_limit") is not True) or (
                    reported_gate == "OPEN" and telemetry.get("open_limit") is not True
                ):
                    reported_gate = "UNKNOWN"
                self._state.gate_state = reported_gate

            if isinstance(telemetry.get("closed_limit"), bool):
                self._state.closed_limit = telemetry["closed_limit"]

            if isinstance(telemetry.get("open_limit"), bool):
                self._state.open_limit = telemetry["open_limit"]

            for sensor in ("bmp280_ok", "dht11_ok"):
                if isinstance(telemetry.get(sensor), bool):
                    setattr(self._state, sensor, telemetry[sensor])

            if "fault" in telemetry:
                self._state.fault = telemetry["fault"]

            now = timestamp or datetime.now(timezone.utc).isoformat()
            self._state.last_telemetry_at = now
            self._state.last_device_telemetry_at = now
            self._state.updated_at = now
            # Successful telemetry implies the ESP32 is ONLINE
            self._state.device_state = "ONLINE"

            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr

    def update_from_device_status(self, status: dict) -> dict:
        """Update mission state from a validated GET_STATUS response."""
        with self._lock:
            prev = self.snapshot()
            if status.get("mode") in self.VALID_MODES:
                self._state.mode = status["mode"]

            if status.get("gate_state") in self.VALID_GATE_STATES:
                reported_gate = status["gate_state"]
                if (reported_gate == "CLOSED" and status.get("closed_limit") is not True) or (
                    reported_gate == "OPEN" and status.get("open_limit") is not True
                ):
                    reported_gate = "UNKNOWN"
                self._state.gate_state = reported_gate

            if isinstance(status.get("closed_limit"), bool):
                self._state.closed_limit = status["closed_limit"]

            if isinstance(status.get("open_limit"), bool):
                self._state.open_limit = status["open_limit"]

            if "fault" in status:
                self._state.fault = status["fault"]

            status_ms = status.get("timestamp_ms")
            if isinstance(status_ms, int) and not isinstance(status_ms, bool) and status_ms >= 0:
                self._state.last_device_status_timestamp_ms = status_ms

            for sensor in ("bmp280_ok", "dht11_ok"):
                if sensor in status:
                    value = status[sensor]
                    setattr(self._state, sensor, value if isinstance(value, bool) else None)

            now = datetime.now(timezone.utc).isoformat()
            self._state.updated_at = now
            self._state.device_state = "ONLINE"

            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr

    def update_gateway_health(self, state: str, timestamp: Optional[str] = None) -> dict:
        """Update the Raspberry Pi edge gateway connection state independently."""
        with self._lock:
            prev = self.snapshot()
            if state in self.VALID_CONNECTION_STATES:
                self._state.gateway_state = state
                now = timestamp or datetime.now(timezone.utc).isoformat()
                if state == "ONLINE":
                    self._state.last_gateway_heartbeat_at = now
                self._state.updated_at = now

                # If gateway went offline, device through gateway is also unreachable
                if state in ("OFFLINE", "NOT_CONNECTED") and self._state.device_state == "ONLINE":
                    self._state.device_state = "OFFLINE"
                    # Lost device connection invalidates physical gate state assumptions
                    self._state.gate_state = "UNKNOWN"

            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr

    def update_device_health(self, state: str, timestamp: Optional[str] = None) -> dict:
        """Update the ESP32 lander connection state independently."""
        with self._lock:
            prev = self.snapshot()
            if state in self.VALID_CONNECTION_STATES:
                self._state.device_state = state
                now = timestamp or datetime.now(timezone.utc).isoformat()
                if state == "ONLINE":
                    self._state.last_device_telemetry_at = now
                elif state in ("OFFLINE", "NOT_CONNECTED"):
                    # Physical gate state cannot be assumed when device is disconnected
                    self._state.gate_state = "UNKNOWN"
                self._state.updated_at = now

            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr

    def handle_disconnect(self, subsystem: str) -> dict:
        """Explicitly record a disconnection event for a subsystem."""
        with self._lock:
            prev = self.snapshot()
            now = datetime.now(timezone.utc).isoformat()
            if subsystem == "gateway":
                self._state.gateway_state = "OFFLINE"
                self._state.device_state = "OFFLINE"
                self._state.gate_state = "UNKNOWN"
            elif subsystem == "device":
                self._state.device_state = "OFFLINE"
                self._state.gate_state = "UNKNOWN"
            self._state.updated_at = now
            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr

    def handle_reconnect(self, subsystem: str) -> dict:
        """
        Record a reconnection event.
        SAFETY RULE: Reconnection must NEVER initiate physical movement,
        and gate state remains UNKNOWN until fresh status is explicitly received.
        """
        with self._lock:
            prev = self.snapshot()
            now = datetime.now(timezone.utc).isoformat()
            if subsystem == "gateway":
                self._state.gateway_state = "ONLINE"
                self._state.last_gateway_heartbeat_at = now
            elif subsystem == "device":
                self._state.device_state = "ONLINE"
                self._state.last_device_telemetry_at = now
                # Retain UNKNOWN until verified by GET_STATUS response or fresh telemetry
                if self._state.gate_state not in ("CLOSED", "OPEN"):
                    self._state.gate_state = "UNKNOWN"
            self._state.updated_at = now
            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr

    def check_staleness(
        self,
        current_time: datetime,
        stale_threshold_s: float = 3.0,
        offline_threshold_s: float = 10.0,
    ) -> dict:
        """
        Evaluate time since last telemetry / heartbeat and update states deterministically.
        """
        with self._lock:
            prev = self.snapshot()
            # Check device staleness
            if self._state.device_state == "ONLINE" and self._state.last_device_telemetry_at:
                last_dt = datetime.fromisoformat(self._state.last_device_telemetry_at)
                elapsed = (current_time - last_dt).total_seconds()
                if elapsed >= offline_threshold_s:
                    self._state.device_state = "OFFLINE"
                    self._state.gate_state = "UNKNOWN"
                elif elapsed >= stale_threshold_s:
                    self._state.device_state = "STALE"

            elif self._state.device_state == "STALE" and self._state.last_device_telemetry_at:
                last_dt = datetime.fromisoformat(self._state.last_device_telemetry_at)
                elapsed = (current_time - last_dt).total_seconds()
                if elapsed >= offline_threshold_s:
                    self._state.device_state = "OFFLINE"
                    self._state.gate_state = "UNKNOWN"

            # Check gateway staleness
            if self._state.gateway_state == "ONLINE" and self._state.last_gateway_heartbeat_at:
                last_gt = datetime.fromisoformat(self._state.last_gateway_heartbeat_at)
                elapsed = (current_time - last_gt).total_seconds()
                if elapsed >= offline_threshold_s:
                    self._state.gateway_state = "OFFLINE"
                    if self._state.device_state == "ONLINE":
                        self._state.device_state = "OFFLINE"
                        self._state.gate_state = "UNKNOWN"
                elif elapsed >= stale_threshold_s:
                    self._state.gateway_state = "STALE"

            self._state.updated_at = current_time.isoformat()
            curr = self.snapshot()
            self._notify_if_changed(prev, curr)
            return curr
