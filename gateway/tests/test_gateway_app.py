"""Integration tests for the Raspberry Pi Gateway router and application lifecycle."""

import asyncio
import pytest

from starlette.websockets import WebSocketState

from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    ConnectionState,
)
from gateway.config import GatewayConfig
from gateway.main import create_gateway_app
from gateway.routes import create_gateway_router
from gateway.tcp_transport import LanderTCPTransport
from gateway.ws_manager import WebSocketBroadcaster


class MockWebSocket:
    """Mock WebSocket for testing broadcaster registration and messaging."""

    def __init__(self):
        self.accepted = False
        self.messages = []
        self.client_state = WebSocketState.CONNECTED

    async def accept(self):
        self.accepted = True

    async def send_text(self, text: str):
        self.messages.append(text)


@pytest.mark.anyio
async def test_gateway_app_lifespan_starts_and_stops_cleanly():
    config = GatewayConfig(
        lander_tcp_host="127.0.0.1",
        lander_tcp_port=0,
        rover_udp_host="127.0.0.1",
        rover_udp_port=0,
    )
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    app = create_gateway_app(config=config, transport=transport)

    assert app.state.lander_manager is not None
    assert app.state.rover_receiver is not None

    async with app.router.lifespan_context(app):
        assert app.state.lander_manager.is_running is True
        assert app.state.rover_receiver._transport is not None

    assert app.state.lander_manager.is_running is False
    assert app.state.rover_receiver._transport is None


@pytest.mark.anyio
async def test_gateway_router_endpoints_match_contracts():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    broadcaster = WebSocketBroadcaster()
    app = create_gateway_app(config=config, transport=transport)
    lander_mgr = app.state.lander_manager

    # 1. Health endpoint
    health = lander_mgr.get_health()
    assert health.status == "healthy"
    assert health.connection_state == ConnectionState.ONLINE
    assert health.device_connected is False

    # 2. Devices endpoint
    devices_resp = lander_mgr.get_devices()
    assert len(devices_resp.devices) == 1
    assert devices_resp.devices[0].device_id == "esp32-lander"
    assert devices_resp.devices[0].connection_state == ConnectionState.NOT_CONNECTED
    assert devices_resp.devices[0].firmware_version is None

    # 3. Lander status endpoint
    status_resp = lander_mgr.get_lander_status()
    assert status_resp.gateway_state == ConnectionState.ONLINE
    assert status_resp.device_state == ConnectionState.NOT_CONNECTED
    assert status_resp.timestamp_ms is None
    assert status_resp.firmware is None

    # 4. Command endpoint while OFFLINE
    cmd_req = CommandRequest(command_id="cmd-offline-test", command=CommandName.GET_STATUS)
    cmd_resp = await lander_mgr.send_command(cmd_req)
    assert cmd_resp.accepted is False
    assert cmd_resp.reason == "DEVICE_OFFLINE"


@pytest.mark.anyio
async def test_gateway_websocket_broadcaster_dispatch():
    broadcaster = WebSocketBroadcaster()
    mock_ws = MockWebSocket()

    await broadcaster.connect(mock_ws)
    assert broadcaster.active_connections_count == 1
    assert mock_ws.accepted is True

    await broadcaster.broadcast({"type": "telemetry_test", "seq": 42})
    assert len(mock_ws.messages) == 1
    assert "telemetry_test" in mock_ws.messages[0]

    broadcaster.disconnect(mock_ws)
    assert broadcaster.active_connections_count == 0
