"""Hardware-free simulator for the Raspberry Pi gateway and lander sensors."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Any

from app.communication.gateway_contract import (
    CommandName, CommandRequest, CommandResponse, ConnectionState, DeviceInfo,
    GatewayDevicesResponse, GatewayHealthResponse, LanderStatusResponse,
    OperatingMode,
)
from app.communication.request_mapper import RequestIdMapper


class GatewaySimulator:
    """Deterministic simulator with no hardware connections or actuator commands."""

    IS_SIMULATOR = True

    def __init__(self, gateway_connected: bool = True, device_connected: bool = True) -> None:
        self.gateway_connected = gateway_connected
        self.device_connected = device_connected
        self.mode = OperatingMode.ACTIVE
        self.bmp280_ok = True
        self.dht11_ok = True
        self.bmp_temp = 24.2
        self.pressure = 1013.5
        self.dht_temp = 24.0
        self.humidity = 58.0
        self.clock_ms = 1000
        self.start_time = datetime.now(timezone.utc).isoformat()
        self.malformed_telemetry = False
        self.drop_next_ack = False
        self.response_delay_ms = 0
        self.request_mapper = RequestIdMapper()

    def advance_clock(self, delta_ms: int) -> None:
        self.clock_ms += max(0, delta_ms)
        seconds = self.clock_ms / 1000.0
        self.bmp_temp = round(24.2 + 1.2 * math.sin(seconds / 7.0), 1)
        self.pressure = round(1013.5 + 3.0 * math.cos(seconds / 11.0), 1)
        self.dht_temp = round(24.0 + 1.0 * math.sin(seconds / 9.0 + 0.6), 1)
        self.humidity = round(58.0 + 6.0 * math.sin(seconds / 13.0 + 1.1), 1)

    def trigger_disconnect(self, target: str = "gateway") -> None:
        if target == "gateway":
            self.gateway_connected = False
        elif target == "device":
            self.device_connected = False

    def trigger_reconnect(self, target: str = "gateway") -> None:
        if target == "gateway":
            self.gateway_connected = True
        elif target == "device":
            self.device_connected = True

    def generate_telemetry_line(self) -> str:
        if self.malformed_telemetry:
            return "MALFORMED_TELEMETRY_PAYLOAD_NOT_JSON"
        return json.dumps({
            "type": "telemetry", "timestamp_ms": self.clock_ms,
            "mode": self.mode.value,
            "bmp_temperature_c": self.bmp_temp if self.bmp280_ok else None,
            "pressure_hpa": self.pressure if self.bmp280_ok else None,
            "dht_temperature_c": self.dht_temp if self.dht11_ok else None,
            "humidity_pct": self.humidity if self.dht11_ok else None,
            "bmp280_ok": self.bmp280_ok, "dht11_ok": self.dht11_ok,
        })

    def get_health(self) -> GatewayHealthResponse:
        connected = self.gateway_connected
        device = connected and self.device_connected
        return GatewayHealthResponse(
            status="healthy" if connected else "unhealthy",
            connection_state=ConnectionState.ONLINE if connected else ConnectionState.OFFLINE,
            version="1.0.0-simulator", uptime_seconds=self.clock_ms / 1000.0,
            device_connected=device,
        )

    def get_devices(self) -> GatewayDevicesResponse:
        state = ConnectionState.ONLINE if self.gateway_connected and self.device_connected else ConnectionState.OFFLINE
        return GatewayDevicesResponse(devices=[DeviceInfo(
            device_id="esp32-lander", name="ESP32 Lander Controller (Simulated)",
            connection_state=state,
            firmware_version="1.3.1-sim", last_seen_at=datetime.now(timezone.utc).isoformat(),
        )])

    def get_lander_status(self) -> LanderStatusResponse:
        gw = ConnectionState.ONLINE if self.gateway_connected else ConnectionState.OFFLINE
        dev = ConnectionState.ONLINE if self.gateway_connected and self.device_connected else ConnectionState.OFFLINE
        return LanderStatusResponse(
            gateway_state=gw, device_state=dev,
            timestamp_ms=self.clock_ms if dev == ConnectionState.ONLINE else None,
            mode=self.mode if dev == ConnectionState.ONLINE else None,
            bmp280_ok=self.bmp280_ok if dev == ConnectionState.ONLINE else None,
            dht11_ok=self.dht11_ok if dev == ConnectionState.ONLINE else None,
            bmp280_state="OK" if self.bmp280_ok else "FAILED",
            dht11_state="OK" if self.dht11_ok else "FAILED", firmware="1.3.1-sim",
        )

    def handle_command(self, req: CommandRequest) -> CommandResponse:
        now = datetime.now(timezone.utc).isoformat()
        self.request_mapper.allocate(req.command_id)
        if not self.gateway_connected:
            accepted, reason = False, "GATEWAY_OFFLINE"
        elif not self.device_connected:
            accepted, reason = False, "DEVICE_OFFLINE"
        elif self.drop_next_ack:
            self.drop_next_ack = False
            accepted, reason = False, "SIMULATED_DROPPED_ACK"
        elif req.command == CommandName.GET_STATUS:
            accepted, reason = True, None
        elif req.command == CommandName.SET_ACTIVE:
            self.mode = OperatingMode.ACTIVE
            accepted, reason = True, None
        elif req.command == CommandName.SET_STANDBY:
            self.mode = OperatingMode.STANDBY
            accepted, reason = True, None
        else:
            accepted, reason = False, "INVALID_COMMAND"
        return CommandResponse(command_id=req.command_id, accepted=accepted, reason=reason, timestamp=now)
