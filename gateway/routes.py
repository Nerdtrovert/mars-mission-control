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
from app.communication.rover_model import RoverSource, RoverStatus

if TYPE_CHECKING:
    from gateway.rover_udp import RoverUDPReceiver
    from gateway.drone_udp import DroneUDPReceiver
    from gateway.lander_manager import LanderManager
    from gateway.ws_manager import WebSocketBroadcaster

logger = logging.getLogger(__name__)


def create_gateway_router(
    lander_manager: LanderManager,
    ws_broadcaster: WebSocketBroadcaster,
    rover_receiver: Optional["RoverUDPReceiver"] = None,
    drone_receiver: Optional["DroneUDPReceiver"] = None,
) -> APIRouter:
    """Creates FastAPI router configured with the lander manager, broadcaster, rover, and drone receivers."""
    router = APIRouter()

    @router.get("/health", response_model=GatewayHealthResponse)
    async def get_health():
        return lander_manager.get_health()

    @router.get("/api/devices", response_model=GatewayDevicesResponse)
    async def get_devices():
        return lander_manager.get_devices()

    @router.get("/api/lander/status", response_model=LanderStatusResponse)
    async def get_lander_status():
        return lander_manager.get_lander_status()

    @router.get("/api/rover/status")
    async def get_rover_status():
        if rover_receiver is None:
            return RoverStatus(source=RoverSource.NETWORK).model_dump(mode="json")
        return rover_receiver.protocol.status()

    @router.get("/api/drone/status")
    async def get_drone_status():
        if drone_receiver is None:
            return {
                "drone_id": "mars-drone-01",
                "flight_status": None,
                "latitude": None,
                "longitude": None,
                "connection_state": "OFFLINE",
                "last_seen": None,
                "source": "network",
            }
        return drone_receiver.protocol.status()

    @router.post("/api/drone/display")
    async def post_drone_display(payload: dict):
        connected = bool(payload.get("connected", True))
        data = payload.get("data")
        sent = await lander_manager.forward_drone_telemetry(data, online=connected)
        return {"sent": sent}

    @router.post("/api/commands", response_model=CommandResponse)
    async def post_command(command: CommandRequest):
        return await lander_manager.send_command(command)

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
