"""Raspberry Pi Hardware Gateway Application Entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI

from gateway.config import GatewayConfig
from gateway.routes import create_gateway_router
from gateway.serial_manager import SerialManager
from gateway.transport import PySerialTransport, SerialTransport
from gateway.ws_manager import WebSocketBroadcaster
from gateway.rover_udp import RoverUDPReceiver


def create_gateway_app(
    config: Optional[GatewayConfig] = None,
    transport: Optional[SerialTransport] = None,
) -> FastAPI:
    """Factory creating configured FastAPI edge gateway application."""
    cfg = config or GatewayConfig()
    ws_broadcaster = WebSocketBroadcaster()
    trans = transport or PySerialTransport(port=cfg.serial_port, baud_rate=cfg.baud_rate)
    serial_mgr = SerialManager(config=cfg, transport=trans, ws_broadcaster=ws_broadcaster)
    rover_receiver = RoverUDPReceiver(config=cfg, broadcaster=ws_broadcaster)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await serial_mgr.start()
        await rover_receiver.start()
        try:
            yield
        finally:
            await rover_receiver.stop()
            await serial_mgr.stop()

    app = FastAPI(
        title="Mars Mission Control — Hardware Edge Gateway",
        description="Raspberry Pi edge gateway managing USB serial communication with the ESP32 lander.",
        version=cfg.version,
        lifespan=lifespan,
    )

    # Attach instances to app.state for testing and inspection
    app.state.config = cfg
    app.state.transport = trans
    app.state.serial_manager = serial_mgr
    app.state.ws_broadcaster = ws_broadcaster
    app.state.rover_receiver = rover_receiver

    # Include routes
    router = create_gateway_router(serial_mgr, ws_broadcaster, rover_receiver)
    app.include_router(router)

    return app


# Default app instance for uvicorn execution (e.g. uvicorn gateway.main:app)
app = create_gateway_app()
