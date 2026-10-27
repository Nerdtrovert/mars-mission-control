"""Independent rover telemetry contract shared by simulator and network modes."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import math
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RoverConnectionState(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class RoverSource(str, Enum):
    SIMULATOR = "simulator"
    NETWORK = "network"


class RoverMode(str, Enum):
    MANUAL = "M"
    AUTONOMOUS = "A"


class RoverCommand(str, Enum):
    FORWARD = "F"
    BACKWARD = "B"
    LEFT = "L"
    RIGHT = "R"
    STOP = "S"


class RoverStatus(BaseModel):
    """Stable public rover state, separate from ESP32 lander telemetry."""

    model_config = ConfigDict(extra="forbid")

    rover_id: str = "mars-rover-01"
    distance_cm: Optional[float] = Field(None, ge=0, le=400)
    pitch_deg: Optional[float] = Field(None, ge=-90, le=90)
    roll_deg: Optional[float] = Field(None, ge=-90, le=90)
    command: Optional[RoverCommand] = None
    mode: Optional[RoverMode] = None
    connection_state: RoverConnectionState = RoverConnectionState.OFFLINE
    last_seen: Optional[str] = None
    source: RoverSource
    obstacle_detected: Optional[bool] = None
    event: Optional[str] = None

    @field_validator("distance_cm", "pitch_deg", "roll_deg")
    @classmethod
    def reject_non_finite(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("Rover numeric telemetry must be finite")
        return value


def offline_status(source: RoverSource, last_seen: Optional[str] = None) -> RoverStatus:
    return RoverStatus(source=source, connection_state=RoverConnectionState.OFFLINE, last_seen=last_seen)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
