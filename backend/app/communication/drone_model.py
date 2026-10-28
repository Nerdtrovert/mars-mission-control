"""Drone telemetry and status models for Mars Mission Control."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class DroneConnectionState(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class DroneSource(str, Enum):
    SIMULATOR = "simulator"
    NETWORK = "network"


class DroneOrientation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roll: Optional[float] = None
    pitch: Optional[float] = None
    yaw: Optional[float] = None


class DroneEnvironment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature_c: Optional[float] = None
    pressure_hpa: Optional[float] = None
    humidity_pct: Optional[float] = None


class DroneGPS(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    altitude_m: Optional[float] = None


class DroneBattery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voltage_v: Optional[float] = Field(None, ge=0.0)
    percentage: Optional[float] = Field(None, ge=0.0, le=100.0)


class DroneTelemetry(BaseModel):
    """Authoritative incoming drone UDP datagram payload."""
    model_config = ConfigDict(extra="forbid")
    device_id: str = "esp32-drone"
    sequence: int = Field(..., ge=0)
    timestamp_ms: int = Field(..., ge=0)
    flight_status: str
    orientation: DroneOrientation = Field(default_factory=DroneOrientation)
    environment: DroneEnvironment = Field(default_factory=DroneEnvironment)
    gps: DroneGPS = Field(default_factory=DroneGPS)
    battery: DroneBattery = Field(default_factory=DroneBattery)


class DroneStatus(BaseModel):
    """Stable public drone state exposed via HTTP and WebSocket."""
    model_config = ConfigDict(extra="forbid")
    drone_id: str = "esp32-drone"
    flight_status: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    battery_percentage: Optional[float] = None
    connection_state: DroneConnectionState = DroneConnectionState.OFFLINE
    last_seen: Optional[str] = None
    source: DroneSource = DroneSource.NETWORK
    telemetry: Optional[DroneTelemetry] = None


def offline_drone_status(source: DroneSource = DroneSource.NETWORK) -> DroneStatus:
    return DroneStatus(
        drone_id="esp32-drone",
        flight_status=None,
        latitude=None,
        longitude=None,
        altitude_m=None,
        battery_percentage=None,
        connection_state=DroneConnectionState.OFFLINE,
        last_seen=None,
        source=source,
        telemetry=None,
    )
