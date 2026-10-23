"""Gateway API Contract and Schema Definitions.

Defines the explicit schemas for communication between the MacBook backend
and the Raspberry Pi hardware gateway over HTTP and WebSocket.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ConnectionState(str, Enum):
    """Connection lifecycle states for the gateway and attached devices."""
    ONLINE = "ONLINE"
    STALE = "STALE"
    OFFLINE = "OFFLINE"
    NOT_CONNECTED = "NOT_CONNECTED"


class GateState(str, Enum):
    """Physical lander gate states."""
    UNKNOWN = "UNKNOWN"
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    OPENING = "OPENING"
    CLOSING = "CLOSING"
    FAULT = "FAULT"


class OperatingMode(str, Enum):
    """ESP32 operating mode."""
    ACTIVE = "ACTIVE"
    STANDBY = "STANDBY"


class CommandName(str, Enum):
    """Currently supported or relevant command names."""
    GET_STATUS = "GET_STATUS"
    SET_ACTIVE = "SET_ACTIVE"
    SET_STANDBY = "SET_STANDBY"
    OPEN_GATE = "OPEN_GATE"
    CLOSE_GATE = "CLOSE_GATE"


class DeviceInfo(BaseModel):
    """Information regarding a peripheral connected to the gateway."""
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., description="Unique device identifier (e.g. esp32-lander)")
    name: str = Field(..., description="Human-readable device name")
    port: Optional[str] = Field(None, description="Physical USB or serial port (e.g. /dev/ttyUSB0)")
    connection_state: ConnectionState = Field(
        default=ConnectionState.NOT_CONNECTED,
        description="Health and communication state of the device"
    )
    firmware_version: Optional[str] = Field(None, description="Reported firmware version")
    last_seen_at: Optional[str] = Field(None, description="ISO8601 timestamp of last message")


class GatewayHealthResponse(BaseModel):
    """Response format for GET /health on the Raspberry Pi gateway."""
    model_config = ConfigDict(extra="forbid")

    status: str = Field("healthy", description="Gateway daemon operational status")
    connection_state: ConnectionState = Field(..., description="Gateway connectivity state")
    version: str = Field("1.0.0", description="Gateway daemon software version")
    uptime_seconds: float = Field(..., ge=0.0, description="Daemon uptime in seconds")
    serial_port: Optional[str] = Field(None, description="Configured serial port path")
    device_connected: bool = Field(False, description="True if serial connection to ESP32 is open")


class GatewayDevicesResponse(BaseModel):
    """Response format for GET /api/devices."""
    model_config = ConfigDict(extra="forbid")

    devices: list[DeviceInfo] = Field(default_factory=list, description="List of attached peripherals")


class LanderStatusResponse(BaseModel):
    """Response format for GET /api/lander/status."""
    model_config = ConfigDict(extra="forbid")

    gateway_state: ConnectionState = Field(..., description="Raspberry Pi gateway reachability state")
    device_state: ConnectionState = Field(..., description="ESP32 serial connection state")
    timestamp_ms: Optional[int] = Field(None, ge=0, description="Device millis() timestamp")
    mode: Optional[OperatingMode] = Field(None, description="Current operating mode")
    gate_state: GateState = Field(GateState.UNKNOWN, description="Verified physical gate state")
    closed_limit: bool = Field(False, description="Closed limit switch contact state")
    open_limit: bool = Field(False, description="Open limit switch contact state")
    fault: Optional[str] = Field(None, description="Active latched fault code, if any")
    pending_standby: Optional[bool] = Field(None, description="Whether standby mode transition is pending")
    startup_limits_settled: Optional[bool] = Field(None, description="Whether limit switches settled at startup")
    limits_established: Optional[bool] = Field(None, description="Whether limit noise recovery has completed")
    sensors_polling: Optional[bool] = Field(None, description="Whether sensors are actively polled")
    bmp280_ok: Optional[bool] = Field(None, description="BMP280 sensor health")
    dht11_ok: Optional[bool] = Field(None, description="DHT11 sensor health")
    bmp280_state: Optional[str] = Field(None, description="BMP280 sensor state string (OK/NO_DATA/FAILED)")
    dht11_state: Optional[str] = Field(None, description="DHT11 sensor state string (OK/NO_DATA/FAILED)")
    firmware: Optional[str] = Field(None, description="Firmware version string")


class CommandRequest(BaseModel):
    """Request payload for POST /api/commands."""
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(..., min_length=1, description="Unique command identifier (e.g. UUID)")
    command: CommandName = Field(..., description="Operation to execute")
    params: Optional[dict[str, Any]] = Field(default=None, description="Optional command parameters")


class CommandResponse(BaseModel):
    """Response payload for POST /api/commands (command acknowledgement)."""
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(..., description="Matches the requested command_id")
    accepted: bool = Field(..., description="Whether the command was accepted by the gateway/device")
    reason: Optional[str] = Field(None, description="Rejection reason if accepted is false")
    fault: Optional[str] = Field(None, description="Fault code if rejection was due to GATE_FAULT")
    timestamp: str = Field(..., description="ISO8601 timestamp of acknowledgement")


class ErrorResponse(BaseModel):
    """Standard error response format for gateway API errors."""
    model_config = ConfigDict(extra="forbid")

    detail: str = Field(..., description="Human-readable error explanation")
    code: str = Field(..., description="Machine-readable error classification code")
    timestamp: str = Field(..., description="ISO8601 timestamp of error occurrence")


class SerialCommandMessage(BaseModel):
    """JSON serial format sent to the ESP32 (e.g. {"command": "OPEN_GATE", "request_id": 101})."""
    model_config = ConfigDict(extra="forbid")

    command: CommandName = Field(..., description="Lander command operation")
    request_id: int = Field(..., ge=1, le=2147483647, description="32-bit positive integer request ID")


class SerialAckMessage(BaseModel):
    """JSON serial format received from the ESP32 (e.g. {"type": "command_ack", "request_id": 101, ...})."""
    model_config = ConfigDict(extra="forbid")

    type: str = Field("command_ack", description="Protocol message type")
    request_id: int = Field(..., ge=0, description="Correlated 32-bit request ID")
    accepted: bool = Field(..., description="Whether command was accepted")
    reason: Optional[str] = Field(None, description="Rejection reason string")
    fault: Optional[str] = Field(None, description="Fault code if reason is GATE_FAULT")
