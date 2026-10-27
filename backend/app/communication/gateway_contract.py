"""HTTP, WebSocket, and lander Wi-Fi stream contracts for Mission Control."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConnectionState(str, Enum):
    ONLINE = "ONLINE"
    STALE = "STALE"
    OFFLINE = "OFFLINE"
    NOT_CONNECTED = "NOT_CONNECTED"


class OperatingMode(str, Enum):
    ACTIVE = "ACTIVE"
    STANDBY = "STANDBY"


class CommandName(str, Enum):
    GET_STATUS = "GET_STATUS"
    SET_ACTIVE = "SET_ACTIVE"
    SET_STANDBY = "SET_STANDBY"


class DeviceInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(..., description="Unique device identifier")
    name: str = Field(..., description="Human-readable device name")
    connection_state: ConnectionState = ConnectionState.NOT_CONNECTED
    firmware_version: Optional[str] = None
    last_seen_at: Optional[str] = None


class GatewayHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "healthy"
    connection_state: ConnectionState
    version: str = "1.0.0"
    uptime_seconds: float = Field(..., ge=0.0)
    device_connected: bool = False


class GatewayDevicesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    devices: list[DeviceInfo] = Field(default_factory=list)


class LanderStatusResponse(BaseModel):
    """Lander connectivity, operating mode, and sensor health; no actuator state."""

    model_config = ConfigDict(extra="forbid")

    gateway_state: ConnectionState
    device_state: ConnectionState
    timestamp_ms: Optional[int] = Field(None, ge=0)
    mode: Optional[OperatingMode] = None
    sensors_polling: Optional[bool] = None
    bmp280_ok: Optional[bool] = None
    dht11_ok: Optional[bool] = None
    bmp280_state: Optional[str] = None
    dht11_state: Optional[str] = None
    firmware: Optional[str] = None


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(..., min_length=1)
    command: CommandName
    params: Optional[dict[str, Any]] = None


class CommandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str
    accepted: bool
    reason: Optional[str] = None
    timestamp: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
    code: str
    timestamp: str


class LanderCommandMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: CommandName
    request_id: int = Field(..., ge=1, le=2147483647)


class LanderAckMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "command_ack"
    request_id: int = Field(..., ge=0)
    accepted: bool
    reason: Optional[str] = None
