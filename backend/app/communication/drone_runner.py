"""Drone telemetry runner for Mission Control backend."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import math
import os
import socket
import time
from typing import Any, Callable, Optional
import urllib.error
import urllib.request
from urllib.parse import urlparse

from app.communication.drone_model import (
    DroneBattery,
    DroneConnectionState,
    DroneEnvironment,
    DroneGPS,
    DroneOrientation,
    DroneSource,
    DroneStatus,
    DroneTelemetry,
    offline_drone_status,
)

logger = logging.getLogger("mars.drone_runner")


class DroneRunner:
    """Publishes drone snapshots from the Pi HTTP status endpoint or simulator mode."""

    def __init__(
        self,
        mode: str,
        http_url: str,
        publish: Callable[[DroneStatus], None],
        interval_s: float = 0.5,
        forward_udp: Optional[bool] = None,
        udp_host: Optional[str] = None,
        udp_port: int = 5007,
    ) -> None:
        self.mode = mode
        self.http_url = http_url.rstrip("/")
        self.publish = publish
        self.interval_s = interval_s
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self.is_running = False
        self._sim_tick = 0

        # Forwarding simulated UDP to gateway so connected lander ESP receives mission_display
        if forward_udp is None:
            env_fwd = os.getenv("FORWARD_SIMULATED_UDP", "true").strip().lower()
            self.forward_udp = env_fwd in ("true", "1", "yes")
        else:
            self.forward_udp = forward_udp

        parsed_host = urlparse(self.http_url).hostname if self.http_url else None
        self.udp_host = udp_host or parsed_host or "127.0.0.1"
        self.udp_port = udp_port
        self._udp_sock: Optional[socket.socket] = None
        if self.forward_udp and self.mode == "simulator":
            try:
                self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            except Exception as e:
                logger.debug("Failed to create drone UDP forwarding socket: %s", e)

        if mode == "simulator":
            self._last_status: DroneStatus = self.step_simulator()
        else:
            self._last_status = offline_drone_status(DroneSource.NETWORK)

    def step_simulator(self) -> DroneStatus:
        """Advance deterministic simulated drone scenario."""
        self._sim_tick += 1
        phases = ["STANDBY", "TAKEOFF", "CRUISING", "HOVERING", "LANDING"]
        phase = phases[(self._sim_tick // 15) % len(phases)]
        lat = 12.9716 + 0.0001 * math.sin(self._sim_tick / 5.0)
        lon = 77.5946 + 0.0001 * math.cos(self._sim_tick / 5.0)
        alt = max(0.0, 50.0 + 10.0 * math.sin(self._sim_tick / 10.0)) if phase != "STANDBY" else 0.0
        batt = max(10.0, 100.0 - (self._sim_tick * 0.1) % 90.0)

        telem = DroneTelemetry(
            device_id="esp32-drone",
            sequence=self._sim_tick,
            timestamp_ms=int(time.time() * 1000),
            flight_status=phase,
            orientation=DroneOrientation(
                roll=round(12.5 * math.sin(self._sim_tick / 4.0), 1),
                pitch=round(15.2 * math.cos(self._sim_tick / 5.0), 1),
                yaw=round((self._sim_tick * 6.0) % 360.0, 1),
            ),
            environment=DroneEnvironment(
                temperature_c=round(26.8 + 0.8 * math.sin(self._sim_tick / 7.0), 1),
                pressure_hpa=round(1013.2 + 2.4 * math.cos(self._sim_tick / 11.0), 1),
                humidity_pct=round(48.0 + 3.0 * math.sin(self._sim_tick / 9.0), 1),
            ),
            gps=DroneGPS(
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                altitude_m=round(alt, 1),
            ),
            battery=DroneBattery(
                voltage_v=round(11.1 + (batt / 100.0) * 1.5, 2),
                percentage=round(batt, 1),
            ),
        )
        status = DroneStatus(
            drone_id="esp32-drone",
            flight_status=phase,
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            altitude_m=round(alt, 1),
            battery_percentage=round(batt, 1),
            connection_state=DroneConnectionState.ONLINE,
            last_seen=datetime.now(timezone.utc).isoformat(),
            source=DroneSource.SIMULATOR,
            telemetry=telem,
        )
        self._last_status = status
        return status

    def snapshot(self) -> DroneStatus:
        return self._last_status.model_copy(deep=True)

    def update_from_payload(self, payload: dict[str, Any]) -> None:
        """Update runner status from a live payload (e.g. from WebSocket)."""
        try:
            status = DroneStatus.model_validate(payload)
            self._last_status = status
            self.publish(status)
        except Exception as exc:
            logger.debug("Failed to validate drone status payload: %s", exc)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self.is_running = True
        self._task = asyncio.create_task(self._run(), name="drone_runner")
        await asyncio.sleep(0)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._udp_sock is not None:
            try:
                self._udp_sock.close()
            except Exception:
                pass
            self._udp_sock = None
        self.is_running = False

    def _forward_udp(self, status: DroneStatus) -> None:
        """Forward simulated drone JSON datagram to the hardware gateway listener."""
        if not self._udp_sock or not self.udp_host or not status.telemetry:
            return
        try:
            payload = status.telemetry.model_dump(mode="json")
            data_bytes = json.dumps(payload).encode("utf-8")
            self._udp_sock.sendto(data_bytes, (self.udp_host, self.udp_port))
        except Exception as exc:
            logger.debug("Simulated drone UDP forward to %s:%s failed: %s", self.udp_host, self.udp_port, exc)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            if self.mode in ("network", "real"):
                status = await asyncio.to_thread(self._fetch_network_status)
                self._last_status = status
                self.publish(status)
            elif self.mode == "simulator":
                status = self.step_simulator()
                if self.forward_udp and status.telemetry is not None:
                    self._forward_udp(status)
                self.publish(status)
            await asyncio.sleep(self.interval_s)

    def _fetch_network_status(self) -> DroneStatus:
        url = f"{self.http_url}/api/drone/status"
        try:
            raw = self._fetch(url)
            payload = json.loads(raw)
            status = DroneStatus.model_validate(payload)
            if status.source != DroneSource.NETWORK:
                status = status.model_copy(update={"source": DroneSource.NETWORK})
            return status
        except Exception:
            return offline_drone_status(DroneSource.NETWORK)

    def _fetch(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "MarsMissionControl/1.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=1.0) as response:
            return response.read()
