"""Rover simulator and Pi-gateway polling runners, independent of lander control."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional
import urllib.error
import urllib.request
from urllib.parse import urlparse

from app.communication.rover_model import (
    RoverSource,
    RoverStatus,
    offline_status,
)
from app.communication.rover_simulator import RoverSimulator

logger = logging.getLogger("mars.rover_runner")


class RoverRunner:
    """Publishes rover snapshots from a local simulator or Pi HTTP status endpoint."""

    def __init__(
        self,
        mode: str,
        http_url: str,
        publish: Callable[[RoverStatus], None],
        interval_s: float = 0.2,
        simulator: Optional[RoverSimulator] = None,
        udp_host: Optional[str] = None,
        udp_port: int = 5005,
    ) -> None:
        self.mode = mode
        self.http_url = http_url.rstrip("/")
        self.publish = publish
        self.interval_s = interval_s
        self.simulator = simulator or RoverSimulator()
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self.is_running = False
        self._last_status: RoverStatus = offline_status(
            RoverSource.SIMULATOR if mode == "simulator" else RoverSource.NETWORK
        )

        # UDP forwarding removed - no hybrid mode
        self.udp_host = udp_host or (urlparse(self.http_url).hostname if self.http_url else "127.0.0.1")
        self.udp_port = udp_port

    def snapshot(self) -> RoverStatus:
        return self._last_status.model_copy(deep=True)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self.is_running = True
        self._task = asyncio.create_task(self._run(), name="rover_runner")
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
        self.is_running = False

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                if self.mode == "simulator":
                    self._last_status = self.simulator.step()
                else:
                    self._last_status = await asyncio.to_thread(self._fetch_network_status)
                self.publish(self.snapshot())
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_s)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        finally:
            self.is_running = False

    def _fetch_network_status(self) -> RoverStatus:
        try:
            request = urllib.request.Request(
                f"{self.http_url}/api/rover/status",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=min(2.0, self.interval_s + 0.8)) as response:
                raw: Any = json.loads(response.read().decode("utf-8"))
            parsed = RoverStatus.model_validate(raw)
            if parsed.source != RoverSource.NETWORK:
                parsed = parsed.model_copy(update={"source": RoverSource.NETWORK})
            return parsed
        except (OSError, urllib.error.URLError, ValueError, TypeError) as exc:
            logger.debug("Rover status unavailable from Pi gateway: %s", exc)
            return offline_status(RoverSource.NETWORK, self._last_status.last_seen)
