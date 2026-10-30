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
        # Cycle distance smoothly so it never gets permanently stuck at 0.0
        distance = max(12.0, 145.0 - (self.tick % 360) * 0.35)
        # Dynamic terrain angles oscillating up to ~27°
        pitch = round(18.5 * math.sin(self.tick / 6.0) + 8.5 * math.cos(self.tick / 14.0), 1)
        roll = round(14.0 * math.cos(self.tick / 8.0) - 10.0 * math.sin(self.tick / 18.0), 1)

        self._status = RoverStatus(
            distance_cm=round(distance, 1),
            pitch_deg=pitch,
            roll_deg=roll,
            command=command,
            mode=mode,
            connection_state=RoverConnectionState.ONLINE,
            last_seen=current,
            source=RoverSource.SIMULATOR,
            obstacle_detected=obstacle,
            event=event,
        )
        return self.snapshot()

    def snapshot(self) -> RoverStatus:
        return self._status.model_copy(deep=True)
