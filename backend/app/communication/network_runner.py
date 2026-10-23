"""Persistent Network Gateway Runner for Mars Mission Control.

Manages persistent WebSocket telemetry streaming, periodic gateway health checks,
and staleness evaluation when connected to the Raspberry Pi edge gateway daemon.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Optional, TYPE_CHECKING
import websockets

from app.communication.gateway_client import GatewayClient
from app.mission.state import MissionStateManager

if TYPE_CHECKING:
    from app.storage.sqlite_storage import SQLiteStorage

logger = logging.getLogger("mars.network_runner")


class NetworkGatewayRunner:
    """Manages persistent WebSocket telemetry stream and health monitoring across the network."""

    IS_SIMULATOR: bool = False

    def __init__(
        self,
        gateway_client: GatewayClient,
        state_manager: MissionStateManager,
        ws_url: str = "ws://127.0.0.1:8001/ws/telemetry",
        http_url: Optional[str] = "http://127.0.0.1:8001",
        interval_s: float = 1.0,
        stale_threshold_s: float = 3.0,
        offline_threshold_s: float = 10.0,
        reconnect_initial_delay_s: float = 1.0,
        reconnect_max_delay_s: float = 10.0,
        reconnect_backoff_factor: float = 1.5,
        storage: Optional[SQLiteStorage] = None,
    ) -> None:
        self.gateway_client = gateway_client
        self.state_manager = state_manager
        self.ws_url = ws_url
        self.http_url = http_url
        self.interval_s = interval_s
        self.stale_threshold_s = stale_threshold_s
        self.offline_threshold_s = offline_threshold_s
        self.reconnect_initial_delay_s = reconnect_initial_delay_s
        self.reconnect_max_delay_s = reconnect_max_delay_s
        self.reconnect_backoff_factor = reconnect_backoff_factor
        self.storage = storage

        self._ws_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
        self._stop_event: asyncio.Event = asyncio.Event()
        self.is_running: bool = False

    async def start(self) -> None:
        """Start background WebSocket subscriber and health monitoring loops."""
        if self.is_running:
            return

        self.is_running = True
        self._stop_event.clear()

        # Initial health query
        try:
            self.gateway_client.check_gateway_health()
        except Exception as e:
            logger.debug(f"Initial gateway health check: {e}")

        self._ws_task = asyncio.create_task(self._ws_listener_loop(), name="network_ws_listener")
        self._health_task = asyncio.create_task(self._health_monitor_loop(), name="network_health_monitor")
        logger.info(f"NetworkGatewayRunner started (WS: {self.ws_url}, HTTP: {self.http_url}).")

    async def stop(self) -> None:
        """Cleanly stop all background network tasks."""
        if not self.is_running:
            return

        self.is_running = False
        self._stop_event.set()

        for task in (self._ws_task, self._health_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._ws_task = None
        self._health_task = None
        logger.info("NetworkGatewayRunner stopped cleanly.")

    async def _ws_listener_loop(self) -> None:
        """Persistent WebSocket loop with bounded exponential backoff."""
        delay = self.reconnect_initial_delay_s

        while not self._stop_event.is_set():
            try:
                logger.info(f"Connecting to Gateway WebSocket: {self.ws_url}")
                async with websockets.connect(self.ws_url) as ws:
                    # Successful connection: reset backoff delay
                    delay = self.reconnect_initial_delay_s
                    # Synchronize fresh device status via non-movement query
                    self.gateway_client.refresh_device_status()

                    while not self._stop_event.is_set():
                        try:
                            msg_text = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue

                        if not msg_text:
                            continue

                        now_iso = datetime.now(timezone.utc).isoformat()
                        try:
                            payload = json.loads(msg_text)
                            if not isinstance(payload, dict):
                                continue

                            msg_type = payload.get("type")
                            if msg_type == "telemetry":
                                self.gateway_client.ingest_telemetry_line(msg_text, timestamp=now_iso)
                            elif msg_type == "gate_status":
                                self.gateway_client.ingest_gate_status(payload)
                        except Exception as e:
                            logger.error(f"Error processing gateway WS message: {e}")

            except (websockets.exceptions.WebSocketException, OSError, ConnectionError) as exc:
                if self._stop_event.is_set():
                    break
                logger.warning(f"Gateway WebSocket dropped: {exc}. Reconnecting in {delay:.1f}s...")
                # Link lost: transition state deterministically
                self.state_manager.handle_disconnect("gateway")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(self.reconnect_max_delay_s, delay * self.reconnect_backoff_factor)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.error(f"Unexpected error in gateway WS listener: {exc}", exc_info=True)
                await asyncio.sleep(delay)

    async def _health_monitor_loop(self) -> None:
        """Periodically evaluates gateway health, connection staleness, and retention."""
        while not self._stop_event.is_set():
            try:
                now = datetime.now(timezone.utc)
                # Check gateway HTTP health
                self.gateway_client.check_gateway_health(timestamp=now.isoformat())
                # Check connection staleness
                self.state_manager.check_staleness(
                    current_time=now,
                    stale_threshold_s=self.stale_threshold_s,
                    offline_threshold_s=self.offline_threshold_s,
                )
                # Prune telemetry retention (5-minute window)
                if self.storage is not None:
                    try:
                        self.storage.prune_telemetry(retention_seconds=300.0, current_time=now)
                    except Exception:
                        pass

                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_s)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in network health monitor loop: {e}")
                await asyncio.sleep(self.interval_s)
