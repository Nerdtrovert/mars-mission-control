"""Background runner for the development Gateway Simulator.

Periodically advances the simulator, emits telemetry, checks gateway health,
and evaluates staleness within the FastAPI application runtime.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Optional, TYPE_CHECKING

from app.communication.gateway_client import GatewayClient
from app.communication.gateway_simulator import GatewaySimulator
from app.mission.state import MissionStateManager

if TYPE_CHECKING:
    from app.storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger("mars.simulator_runner")


class SimulatorRunner:
    """Manages the background telemetry streaming and staleness checking loop."""

    IS_SIMULATOR: bool = True

    def __init__(
        self,
        gateway_client: GatewayClient,
        simulator: GatewaySimulator,
        state_manager: MissionStateManager,
        interval_s: float = 1.0,
        stale_threshold_s: float = 3.0,
        offline_threshold_s: float = 10.0,
        storage: Optional[SQLiteStorage] = None,
    ) -> None:
        self.gateway_client = gateway_client
        self.simulator = simulator
        self.state_manager = state_manager
        self.interval_s = interval_s
        self.stale_threshold_s = stale_threshold_s
        self.offline_threshold_s = offline_threshold_s
        self.storage = storage

        self._task: Optional[asyncio.Task] = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self.is_running: bool = False

    def step(self, now: Optional[datetime] = None) -> None:
        """
        Execute one deterministic cycle:
        1. Check and update gateway health independently.
        2. If gateway and device are connected, advance virtual sensor time,
           generate telemetry, and ingest via gateway client.
        3. Explicitly evaluate connection staleness against the provided or current time.
        """
        current_time = now or datetime.now(timezone.utc)
        now_iso = current_time.isoformat()

        # 1. Update gateway health independently
        self.gateway_client.check_gateway_health(timestamp=now_iso)

        # 2. Ingest telemetry if gateway and device are connected
        if self.simulator.gateway_connected and self.simulator.device_connected:
            self.simulator.advance_clock(int(self.interval_s * 1000))
            self.simulator.step_physical_movement()
            line = self.simulator.generate_telemetry_line()
            self.gateway_client.ingest_telemetry_line(line, timestamp=now_iso)

        # 3. Explicitly evaluate connection staleness (never mutates in read-only snapshot)
        self.state_manager.check_staleness(
            current_time=current_time,
            stale_threshold_s=self.stale_threshold_s,
            offline_threshold_s=self.offline_threshold_s,
        )

        # 4. Deterministic telemetry retention pruning (5-minute sliding window)
        if self.storage is not None:
            try:
                self.storage.prune_telemetry(retention_seconds=300.0, current_time=current_time)
            except Exception as e:
                logger.error(f"Error during retention pruning: {e}")

    async def run_loop(self) -> None:
        """Continuous background execution loop."""
        self.is_running = True
        self._stop_event.clear()
        try:
            while not self._stop_event.is_set():
                self.step()
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.interval_s,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            self.is_running = False

    async def start(self) -> None:
        """Start the managed background task."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run_loop())
        # Yield once to the event loop so startup initiates cleanly
        await asyncio.sleep(0)

    async def stop(self) -> None:
        """Cleanly cancel and await the background task."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.is_running = False
