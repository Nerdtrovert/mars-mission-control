"""Dedicated UDP receiver for rover telemetry broadcast by the Windows GUI."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
import time
from typing import Any, Optional

from app.communication.rover_model import RoverCommand, RoverConnectionState, RoverMode
from gateway.config import GatewayConfig

logger = logging.getLogger("gateway.rover_udp")


def parse_rover_datagram(data: bytes) -> dict[str, Any]:
    """Parse and validate one complete key/value UDP packet."""
    try:
        message = data.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("packet must be ASCII") from exc
    fields: dict[str, str] = {}
    for part in message.split(","):
        if ":" not in part:
            raise ValueError("field must use KEY:VALUE format")
        key, value = (segment.strip() for segment in part.split(":", 1))
        if key not in {"DIST", "PITCH", "ROLL", "CMD", "MODE"} or key in fields or not value:
            raise ValueError("unknown, duplicate, or empty field")
        fields[key] = value
    required = {"DIST", "PITCH", "ROLL", "CMD", "MODE"}
    if fields.keys() != required:
        raise ValueError("all rover telemetry fields are required")

    try:
        distance = float(fields["DIST"])
        pitch = float(fields["PITCH"])
        roll = float(fields["ROLL"])
    except ValueError as exc:
        raise ValueError("numeric rover fields must be valid numbers") from exc
    if not all(math.isfinite(value) for value in (distance, pitch, roll)):
        raise ValueError("numeric rover fields must be finite")
    if not 0 <= distance <= 400 or not -90 <= pitch <= 90 or not -90 <= roll <= 90:
        raise ValueError("rover numeric field is outside allowed range")
    if fields["CMD"] not in {value.value for value in RoverCommand}:
        raise ValueError("unsupported rover command")
    if fields["MODE"] not in {value.value for value in RoverMode}:
        raise ValueError("unsupported rover mode")
    return {
        "distance_cm": distance,
        "pitch_deg": pitch,
        "roll_deg": roll,
        "command": fields["CMD"],
        "mode": fields["MODE"],
    }


class RoverUDPProtocol(asyncio.DatagramProtocol):
    """Validates packets and retains only the latest valid rover sample."""

    def __init__(
        self,
        config: GatewayConfig,
        broadcaster: Any,
        lander_manager: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.broadcaster = broadcaster
        self.lander_manager = lander_manager
        self.transport: Optional[asyncio.DatagramTransport] = None
        self._data: dict[str, Any] = {}
        self._last_seen_mono: Optional[float] = None
        self._last_seen: Optional[str] = None
        self._last_online: Optional[bool] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        logger.info("Rover UDP receiver listening on %s:%s", self.config.rover_udp_host, self.config.rover_udp_port)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            parsed = parse_rover_datagram(data)
        except ValueError as exc:
            logger.warning("Rejected rover UDP packet from %s:%s: %s", addr[0], addr[1], exc)
            return

        self._data = parsed
        self._last_seen_mono = time.monotonic()
        self._last_seen = datetime.now(timezone.utc).isoformat()
        self._last_online = True
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_status())
            if self.lander_manager is not None:
                loop.create_task(
                    self.lander_manager.forward_rover_telemetry(parsed, online=True)
                )
        except RuntimeError:
            # Direct protocol tests may exercise datagram validation synchronously.
            pass

    def error_received(self, exc: Exception) -> None:
        logger.warning("Rover UDP socket error: %s", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            logger.warning("Rover UDP receiver stopped with error: %s", exc)
        self.transport = None

    def status(self) -> dict[str, Any]:
        online = self._last_seen_mono is not None and (
            time.monotonic() - self._last_seen_mono <= self.config.rover_offline_timeout_s
        )
        result: dict[str, Any] = {
            "rover_id": "mars-rover-01",
            "distance_cm": self._data.get("distance_cm"),
            "pitch_deg": self._data.get("pitch_deg"),
            "roll_deg": self._data.get("roll_deg"),
            "command": self._data.get("command"),
            "mode": self._data.get("mode"),
            "connection_state": RoverConnectionState.ONLINE.value if online else RoverConnectionState.OFFLINE.value,
            "last_seen": self._last_seen,
            "source": "network",
            "obstacle_detected": None,
            "event": None,
        }
        return result

    async def _broadcast_status(self) -> None:
        await self.broadcaster.broadcast({"type": "rover_telemetry", "rover": self.status()})

    async def monitor_staleness(self) -> None:
        """Broadcast the online-to-offline transition once per telemetry silence."""
        while True:
            await asyncio.sleep(min(0.25, self.config.rover_offline_timeout_s / 2))
            status = self.status()
            online = status["connection_state"] == RoverConnectionState.ONLINE.value
            if self._last_online is not online:
                self._last_online = online
                await self.broadcaster.broadcast({"type": "rover_telemetry", "rover": status})
                if self.lander_manager is not None:
                    await self.lander_manager.forward_rover_telemetry(self._data, online=online)


class RoverUDPReceiver:
    """Lifecycle wrapper for a UDP transport independent of the serial manager."""

    def __init__(
        self,
        config: GatewayConfig,
        broadcaster: Any,
        lander_manager: Optional[Any] = None,
    ) -> None:
        self.protocol = RoverUDPProtocol(config, broadcaster, lander_manager=lander_manager)
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._monitor_task: Optional[asyncio.Task[None]] = None
        self._simulator_task: Optional[asyncio.Task[None]] = None

    async def _simulator_loop(self) -> None:
        """Simulate rover telemetry when rover_simulator is configured and no external packets arrive."""
        tick = 0
        while True:
            await asyncio.sleep(0.5)
            # Skip if external packet arrived recently
            if self.protocol._last_seen_mono and (
                time.monotonic() - self.protocol._last_seen_mono < self.protocol.config.rover_offline_timeout_s
            ):
                continue
            tick += 1
            dist = max(10.0, round(120.0 - (tick * 0.5) % 100, 1))
            pitch = round(2.5 * math.sin(tick / 6.0), 1)
            roll = round(1.8 * math.cos(tick / 8.0), 1)
            cmd = "F" if (tick // 10) % 2 == 0 else "S"
            mode = "M" if (tick // 20) % 2 == 0 else "A"
            parsed = {
                "distance_cm": dist,
                "pitch_deg": pitch,
                "roll_deg": roll,
                "command": cmd,
                "mode": mode,
            }
            self.protocol._data = parsed
            self.protocol._last_seen_mono = time.monotonic()
            self.protocol._last_seen = datetime.now(timezone.utc).isoformat()
            self.protocol._last_online = True
            await self.protocol._broadcast_status()
            if self.protocol.lander_manager is not None:
                await self.protocol.lander_manager.forward_rover_telemetry(parsed, online=True)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: self.protocol,
            local_addr=(self.protocol.config.rover_udp_host, self.protocol.config.rover_udp_port),
        )
        self._transport = transport  # type: ignore[assignment]
        self._monitor_task = asyncio.create_task(self.protocol.monitor_staleness(), name="rover_udp_staleness")
        if self.protocol.config.rover_simulator:
            self._simulator_task = asyncio.create_task(self._simulator_loop(), name="rover_udp_simulator")

    async def stop(self) -> None:
        for task_attr in ("_monitor_task", "_simulator_task"):
            task = getattr(self, task_attr, None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, task_attr, None)
        if self._transport is not None:
            self._transport.close()
            self._transport = None
