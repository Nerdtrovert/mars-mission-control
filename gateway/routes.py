"""Gateway HTTP and WebSocket API Routes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
from fastapi import APIRouter, Depends, Request
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.communication.gateway_contract import (
    CommandRequest,
    CommandResponse,
    GatewayDevicesResponse,
    GatewayHealthResponse,
    LanderStatusResponse,
)

if TYPE_CHECKING:
    from gateway.serial_manager import SerialManager
    from gateway.ws_manager import WebSocketBroadcaster

logger = logging.getLogger(__name__)


def create_gateway_router(
    serial_manager: SerialManager,
    ws_broadcaster: WebSocketBroadcaster,
) -> APIRouter:
    """Creates FastAPI router configured with specific SerialManager and WebSocketBroadcaster."""
    router = APIRouter()

    @router.get("/health", response_model=GatewayHealthResponse)
    async def get_health():
        return serial_manager.get_health()

    @router.get("/api/devices", response_model=GatewayDevicesResponse)
    async def get_devices():
        return serial_manager.get_devices()

    @router.get("/api/lander/status", response_model=LanderStatusResponse)
    async def get_lander_status():
        return serial_manager.get_lander_status()

    @router.post("/api/commands", response_model=CommandResponse)
    async def post_command(command: CommandRequest):
        return await serial_manager.send_command(command)

    @router.websocket("/ws/telemetry")
    async def ws_telemetry(websocket: WebSocket):
        await ws_broadcaster.connect(websocket)
        try:
            while True:
                # Keep connection open; await incoming messages or client disconnect
                _ = await websocket.receive_text()
        except WebSocketDisconnect:
            ws_broadcaster.disconnect(websocket)
        except Exception as e:
            logger.debug(f"WebSocket client terminated: {e}")
            ws_broadcaster.disconnect(websocket)

    return router
