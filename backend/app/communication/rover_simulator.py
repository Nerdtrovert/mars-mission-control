"""Deterministic, hardware-free rover telemetry simulator."""

from __future__ import annotations

from datetime import datetime, timezone
import math

from app.communication.rover_model import (
    RoverCommand,
    RoverConnectionState,
    RoverMode,
    RoverSource,
    RoverStatus,
)


class RoverSimulator:
    """Repeatable 5 Hz rover scenario; it has no transport or command output."""

    IS_SIMULATOR = True

    def __init__(self) -> None:
        self.tick = 0
        self.telemetry_enabled = True
        self._status = RoverStatus(
            source=RoverSource.SIMULATOR,
            connection_state=RoverConnectionState.OFFLINE,
            event="Awaiting simulated telemetry",
        )

    def set_telemetry_enabled(self, enabled: bool) -> None:
        self.telemetry_enabled = enabled

    def step(self, now: datetime | None = None) -> RoverStatus:
        self.tick += 1
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        if not self.telemetry_enabled:
            self._status = self._status.model_copy(update={
                "connection_state": RoverConnectionState.OFFLINE,
                "event": "Simulated telemetry interruption",
            })
            return self.snapshot()

        # Fixed deterministic scenario: pause for an obstacle every 30 ticks;
        # alternate manual/autonomous drive segments without issuing commands.
        obstacle = self.tick % 30 in range(11, 16)
        if obstacle:
            command = RoverCommand.STOP
            event = "Simulated obstacle detected"
        else:
            segment = (self.tick // 20) % 4
            command = (RoverCommand.FORWARD, RoverCommand.LEFT, RoverCommand.FORWARD, RoverCommand.RIGHT)[segment]
            event = None
        mode = RoverMode.MANUAL if (self.tick // 40) % 2 == 0 else RoverMode.AUTONOMOUS
        distance = max(0.0, 145.0 - self.tick * 0.35)
        voltage = max(9.6, 12.6 - self.tick * 0.001)
        self._status = RoverStatus(
            distance_cm=round(distance, 1),
            pitch_deg=round(3.2 * math.sin(self.tick / 8), 1),
            roll_deg=round(2.4 * math.cos(self.tick / 11), 1),
            command=command,
            mode=mode,
            battery_voltage_v=round(voltage, 2),
            battery_percentage=None,
            connection_state=RoverConnectionState.ONLINE,
            last_seen=current,
            source=RoverSource.SIMULATOR,
            obstacle_detected=obstacle,
            event=event,
        )
        return self.snapshot()

    def snapshot(self) -> RoverStatus:
        return self._status.model_copy(deep=True)
