"""Development-Only Gateway and Lander Simulator.

Simulates the Raspberry Pi hardware gateway and ESP32 lander for offline,
deterministic testing without physical hardware or serial ports.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Any, Optional

from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    CommandResponse,
    ConnectionState,
    DeviceInfo,
    GateState,
    GatewayDevicesResponse,
    GatewayHealthResponse,
    LanderStatusResponse,
    OperatingMode,
    SerialAckMessage,
    SerialCommandMessage,
)
from app.communication.request_mapper import RequestIdMapper


class GatewaySimulator:
    """
    In-memory development simulator for the Raspberry Pi Gateway and ESP32 Lander.
    Explicitly marked as simulated; never masquerades as production hardware.
    """

    IS_SIMULATOR: bool = True

    def __init__(
        self,
        gateway_connected: bool = True,
        device_connected: bool = True,
        initial_gate_state: Optional[GateState] = GateState.CLOSED,
    ) -> None:
        self.gateway_connected = gateway_connected
        self.device_connected = device_connected
        self.mode = OperatingMode.ACTIVE
        self.gate_state = initial_gate_state if initial_gate_state is not None else GateState.UNKNOWN
        self.closed_limit = (self.gate_state == GateState.CLOSED)
        self.open_limit = (self.gate_state == GateState.OPEN)
        self.fault: Optional[str] = None
        self.bmp280_ok = True
        self.dht11_ok = True
        self.bmp_temp = 24.2
        self.pressure = 1013.5
        self.dht_temp = 24.0
        self.humidity = 58.0
        self.clock_ms: int = 1000
        self.start_time: str = datetime.now(timezone.utc).isoformat()
        self.malformed_telemetry: bool = False
        self.drop_next_ack: bool = False
        self.response_delay_ms: int = 0
        self.movement_step_counter: int = 0
        self.movement_steps_needed: int = 3  # deterministic ticks to complete move
        self.request_mapper = RequestIdMapper()

    def advance_clock(self, delta_ms: int) -> None:
        """Deterministically advance virtual time."""
        self.clock_ms += max(0, delta_ms)
        seconds = self.clock_ms / 1000.0
        # Smooth, bounded demonstration variation with plausible ambient values.
        # The virtual clock keeps simulator output repeatable in tests.
        self.bmp_temp = round(24.2 + 1.2 * math.sin(seconds / 7.0), 1)
        self.pressure = round(1013.5 + 3.0 * math.cos(seconds / 11.0), 1)
        self.dht_temp = round(24.0 + 1.0 * math.sin(seconds / 9.0 + 0.6), 1)
        self.humidity = round(58.0 + 6.0 * math.sin(seconds / 13.0 + 1.1), 1)

    def trigger_disconnect(self, target: str = "gateway") -> None:
        """Simulate physical network or serial disconnection."""
        if target == "gateway":
            self.gateway_connected = False
        elif target == "device":
            self.device_connected = False

    def trigger_reconnect(self, target: str = "gateway") -> None:
        """Simulate reconnection of gateway or device."""
        if target == "gateway":
            self.gateway_connected = True
        elif target == "device":
            self.device_connected = True

    def step_physical_movement(self) -> None:
        """
        Advance simulated mechanical movement deterministically by one tick.
        Does NOT rely on arbitrary sleeps.
        """
        if self.gate_state == GateState.OPENING:
            self.closed_limit = False
            self.movement_step_counter += 1
            if self.movement_step_counter >= self.movement_steps_needed:
                self.gate_state = GateState.OPEN
                self.open_limit = True
                self.movement_step_counter = 0

        elif self.gate_state == GateState.CLOSING:
            self.open_limit = False
            self.movement_step_counter += 1
            if self.movement_step_counter >= self.movement_steps_needed:
                self.gate_state = GateState.CLOSED
                self.closed_limit = True
                self.movement_step_counter = 0

    def generate_telemetry_line(self) -> str:
        """Generate one line of ESP32 JSON telemetry conforming to protocol."""
        if self.malformed_telemetry:
            return "MALFORMED_TELEMETRY_PAYLOAD_NOT_JSON"

        payload = {
            "type": "telemetry",
            "timestamp_ms": self.clock_ms,
            "mode": self.mode.value,
            "gate_state": self.gate_state.value,
            "closed_limit": self.closed_limit,
            "open_limit": self.open_limit,
            "bmp_temperature_c": self.bmp_temp if self.bmp280_ok else None,
            "pressure_hpa": self.pressure if self.bmp280_ok else None,
            "dht_temperature_c": self.dht_temp if self.dht11_ok else None,
            "humidity_pct": self.humidity if self.dht11_ok else None,
            "bmp280_ok": self.bmp280_ok,
            "dht11_ok": self.dht11_ok,
            "fault": self.fault,
        }
        return json.dumps(payload)

    def get_health(self) -> GatewayHealthResponse:
        """Simulate GET /health endpoint."""
        gw_state = ConnectionState.ONLINE if self.gateway_connected else ConnectionState.OFFLINE
        return GatewayHealthResponse(
            status="healthy" if self.gateway_connected else "unhealthy",
            connection_state=gw_state,
            version="1.0.0-simulator",
            uptime_seconds=float(self.clock_ms) / 1000.0,
            serial_port="/dev/simulated-serial" if self.device_connected else None,
            device_connected=self.gateway_connected and self.device_connected,
        )

    def get_devices(self) -> GatewayDevicesResponse:
        """Simulate GET /api/devices endpoint."""
        dev_state = (
            ConnectionState.ONLINE
            if (self.gateway_connected and self.device_connected)
            else ConnectionState.OFFLINE
        )
        return GatewayDevicesResponse(
            devices=[
                DeviceInfo(
                    device_id="esp32-lander",
                    name="ESP32 Lander Controller (Simulated)",
                    port="/dev/simulated-serial",
                    connection_state=dev_state,
                    firmware_version="1.3.1-sim",
                    last_seen_at=datetime.now(timezone.utc).isoformat(),
                )
            ]
        )

    def get_lander_status(self) -> LanderStatusResponse:
        """Simulate GET /api/lander/status endpoint."""
        gw_state = ConnectionState.ONLINE if self.gateway_connected else ConnectionState.OFFLINE
        dev_state = (
            ConnectionState.ONLINE
            if (self.gateway_connected and self.device_connected)
            else ConnectionState.OFFLINE
        )

        # If device is disconnected, gate state cannot be verified and defaults to UNKNOWN
        reported_gate_state = self.gate_state if dev_state == ConnectionState.ONLINE else GateState.UNKNOWN
        reported_closed = self.closed_limit if dev_state == ConnectionState.ONLINE else False
        reported_open = self.open_limit if dev_state == ConnectionState.ONLINE else False

        return LanderStatusResponse(
            gateway_state=gw_state,
            device_state=dev_state,
            timestamp_ms=self.clock_ms if dev_state == ConnectionState.ONLINE else None,
            mode=self.mode if dev_state == ConnectionState.ONLINE else None,
            gate_state=reported_gate_state,
            closed_limit=reported_closed,
            open_limit=reported_open,
            fault=self.fault if dev_state == ConnectionState.ONLINE else None,
            pending_standby=False,
            startup_limits_settled=True,
            limits_established=True,
            bmp280_ok=self.bmp280_ok if dev_state == ConnectionState.ONLINE else None,
            dht11_ok=self.dht11_ok if dev_state == ConnectionState.ONLINE else None,
            bmp280_state="OK" if self.bmp280_ok else "FAILED",
            dht11_state="OK" if self.dht11_ok else "FAILED",
            firmware="1.3.1-sim",
        )

    def handle_command(self, req: CommandRequest) -> CommandResponse:
        """
        Simulate POST /api/commands handling and firmware validation rules.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Gateway boundary maps UUID to integer request_id for ESP32 protocol
        integer_req_id = self.request_mapper.allocate(req.command_id)

        if not self.gateway_connected:
            return CommandResponse(
                command_id=req.command_id,
                accepted=False,
                reason="GATEWAY_OFFLINE",
                fault=None,
                timestamp=now_iso,
            )

        if not self.device_connected:
            return CommandResponse(
                command_id=req.command_id,
                accepted=False,
                reason="DEVICE_OFFLINE",
                fault=None,
                timestamp=now_iso,
            )

        # Simulate lost / dropped acknowledgement if enabled
        if self.drop_next_ack:
            self.drop_next_ack = False
            # On physical device, the command was received and executed, but ACK was lost on wire
            if req.command == CommandName.OPEN_GATE and self.gate_state == GateState.CLOSED and self.mode == OperatingMode.ACTIVE:
                self.gate_state = GateState.OPENING
                self.closed_limit = False
                self.movement_step_counter = 0
            elif req.command == CommandName.CLOSE_GATE and self.gate_state == GateState.OPEN and self.mode == OperatingMode.ACTIVE:
                self.gate_state = GateState.CLOSING
                self.open_limit = False
                self.movement_step_counter = 0

            return CommandResponse(
                command_id=req.command_id,
                accepted=False,
                reason="SIMULATED_DROPPED_ACK",
                fault=None,
                timestamp=now_iso,
            )

        if req.command == CommandName.GET_STATUS:
            return CommandResponse(
                command_id=req.command_id,
                accepted=True,
                reason=None,
                fault=None,
                timestamp=now_iso,
            )

        if req.command == CommandName.SET_ACTIVE:
            self.mode = OperatingMode.ACTIVE
            return CommandResponse(
                command_id=req.command_id,
                accepted=True,
                reason=None,
                fault=None,
                timestamp=now_iso,
            )

        if req.command == CommandName.SET_STANDBY:
            self.mode = OperatingMode.STANDBY
            return CommandResponse(
                command_id=req.command_id,
                accepted=True,
                reason=None,
                fault=None,
                timestamp=now_iso,
            )

        if req.command == CommandName.OPEN_GATE:
            if self.mode != OperatingMode.ACTIVE:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="INVALID_STATE",
                    fault=None,
                    timestamp=now_iso,
                )
            if self.gate_state in (GateState.OPENING, GateState.CLOSING):
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="GATE_BUSY",
                    fault=None,
                    timestamp=now_iso,
                )
            if self.gate_state == GateState.FAULT:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="GATE_FAULT",
                    fault=self.fault,
                    timestamp=now_iso,
                )
            if self.gate_state == GateState.UNKNOWN:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="GATE_UNKNOWN",
                    fault=None,
                    timestamp=now_iso,
                )
            if self.gate_state != GateState.CLOSED:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="INVALID_STATE",
                    fault=None,
                    timestamp=now_iso,
                )

            # Accepted: start moving
            self.gate_state = GateState.OPENING
            self.closed_limit = False
            self.movement_step_counter = 0
            return CommandResponse(
                command_id=req.command_id,
                accepted=True,
                reason=None,
                fault=None,
                timestamp=now_iso,
            )

        if req.command == CommandName.CLOSE_GATE:
            if self.mode != OperatingMode.ACTIVE:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="INVALID_STATE",
                    fault=None,
                    timestamp=now_iso,
                )
            if self.gate_state in (GateState.OPENING, GateState.CLOSING):
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="GATE_BUSY",
                    fault=None,
                    timestamp=now_iso,
                )
            if self.gate_state == GateState.FAULT:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="GATE_FAULT",
                    fault=self.fault,
                    timestamp=now_iso,
                )
            if self.gate_state == GateState.UNKNOWN:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="GATE_UNKNOWN",
                    fault=None,
                    timestamp=now_iso,
                )
            if self.gate_state != GateState.OPEN:
                return CommandResponse(
                    command_id=req.command_id,
                    accepted=False,
                    reason="INVALID_STATE",
                    fault=None,
                    timestamp=now_iso,
                )

            # Accepted: start moving
            self.gate_state = GateState.CLOSING
            self.open_limit = False
            self.movement_step_counter = 0
            return CommandResponse(
                command_id=req.command_id,
                accepted=True,
                reason=None,
                fault=None,
                timestamp=now_iso,
            )

        return CommandResponse(
            command_id=req.command_id,
            accepted=False,
            reason="INVALID_COMMAND",
            fault=None,
            timestamp=now_iso,
        )

    def handle_serial_payload(self, raw_payload: dict) -> dict:
        """
        Simulate the exact ESP32 v1.3.1 firmware processLine():
        Requires doc["request_id"].is<int32_t>().
        Rejects string request_id with INVALID_REQUEST.
        """
        req_id = raw_payload.get("request_id")
        if not isinstance(req_id, int) or isinstance(req_id, bool):
            return {
                "type": "command_ack",
                "request_id": 0,
                "accepted": False,
                "reason": "INVALID_REQUEST",
            }

        cmd_name = raw_payload.get("command")
        if not isinstance(cmd_name, str):
            return {
                "type": "command_ack",
                "request_id": req_id,
                "accepted": False,
                "reason": "INVALID_REQUEST",
            }

        return {
            "type": "command_ack",
            "request_id": req_id,
            "accepted": True,
            "reason": None,
        }
