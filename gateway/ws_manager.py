"""WebSocket Broadcast Manager for Raspberry Pi Gateway."""

from __future__ import annotations

import json
import logging
from typing import Any, Union
from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)


class WebSocketBroadcaster:
    """Thread-safe and async-safe WebSocket connection broadcaster."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    @property
    def active_connections_count(self) -> int:
        return len(self._connections)

    async def connect(self, ws: WebSocket) -> None:
        """Register an incoming WebSocket client."""
        await ws.accept()
        self._connections.add(ws)
        logger.info(f"WebSocket client connected. Total active: {len(self._connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket client."""
        self._connections.discard(ws)
        logger.info(f"WebSocket client removed. Total active: {len(self._connections)}")

    async def broadcast(self, message: Union[dict[str, Any], str]) -> None:
        """
        Broadcast a message to all active WebSocket clients.
        Silently prunes stale or disconnected clients without failing.
        """
        if not self._connections:
            return

        payload = message if isinstance(message, str) else json.dumps(message)
        dead: list[WebSocket] = []

        for ws in list(self._connections):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(payload)
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._connections.discard(ws)
