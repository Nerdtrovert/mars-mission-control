"""Dashboard WebSocket Broadcaster for Mars Mission Control.

Manages active WebSocket connections from dashboard frontends and
broadcasts live telemetry, state snapshots, and event/command updates.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("mars.broadcaster")


class DashboardBroadcaster:
    """Manages active dashboard WebSocket subscribers."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = asyncio.Lock()

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"Dashboard client connected. Active connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"Dashboard client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self.active_connections)

        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)

    def broadcast_sync(self, message: dict[str, Any]) -> None:
        """Safe synchronous broadcast trigger callable from sync methods or background threads."""
        if not self.active_connections:
            return

        try:
            loop = self._loop
            if loop is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass

            if loop is not None and loop.is_running():
                try:
                    current_loop = asyncio.get_running_loop()
                    if current_loop is loop:
                        loop.create_task(self.broadcast(message))
                        return
                except RuntimeError:
                    pass
                asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
        except Exception as e:
            logger.debug(f"Could not broadcast message: {e}")
