"""Raspberry Pi Hardware Gateway Application Entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI

from gateway.config import GatewayConfig
from gateway.routes import create_gateway_router
from gateway.lander_manager import LanderManager
from gateway.tcp_transport import LanderTCPTransport
from gateway.ws_manager import WebSocketBroadcaster
from gateway.rover_udp import RoverUDPReceiver


def create_gateway_app(
    config: Optional[GatewayConfig] = None,
    transport: Optional[LanderTCPTransport] = None,
) -> FastAPI:
    """Factory creating configured FastAPI edge gateway application."""
    cfg = config or GatewayConfig()
    ws_broadcaster = WebSocketBroadcaster()
    trans = transport or LanderTCPTransport(host=cfg.lander_tcp_host, port=cfg.lander_tcp_port)
    lander_mgr = LanderManager(config=cfg, transport=trans, ws_broadcaster=ws_broadcaster)
    rover_receiver = RoverUDPReceiver(config=cfg, broadcaster=ws_broadcaster)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await lander_mgr.start()
        try:
            await rover_receiver.start()
            yield
        finally:
            await rover_receiver.stop()
            await lander_mgr.stop()

    app = FastAPI(
        title="Mars Mission Control — Hardware Edge Gateway",
        description="Raspberry Pi edge gateway receiving lander telemetry over Wi-Fi TCP and rover telemetry over UDP.",
        version=cfg.version,
        lifespan=lifespan,
    )

    # Attach instances to app.state for testing and inspection
    app.state.config = cfg
    app.state.transport = trans
    app.state.lander_manager = lander_mgr
    app.state.ws_broadcaster = ws_broadcaster
    app.state.rover_receiver = rover_receiver

    # Include routes
    router = create_gateway_router(lander_mgr, ws_broadcaster, rover_receiver)
    app.include_router(router)

    return app


# Default app instance for uvicorn execution (e.g. uvicorn gateway.main:app)
app = create_gateway_app()
