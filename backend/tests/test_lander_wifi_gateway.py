"""Hardware-free tests of the Pi lander Wi-Fi stream receiver."""

import asyncio
import json
import time

import pytest

from app.communication.gateway_contract import CommandName, CommandRequest, ConnectionState
from gateway.config import GatewayConfig
from gateway.lander_manager import LanderManager
from gateway.tcp_transport import LanderTCPTransport


class BroadcasterStub:
    async def broadcast(self, message):
        return None


def telemetry_message():
    return {
        "type": "telemetry",
        "timestamp_ms": 1000,
        "mode": "ACTIVE",
        "bmp_temperature_c": 22.5,
        "pressure_hpa": 1004.2,
        "dht_temperature_c": 23.0,
        "humidity_pct": 42.0,
        "bmp280_ok": True,
        "dht11_ok": True,
    }


@pytest.mark.anyio
async def test_pi_tcp_listener_accepts_valid_telemetry_and_correlated_commands():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())
    await manager.start()
    reader = writer = None
    try:
        assert manager.get_health().connection_state == ConnectionState.ONLINE
        assert manager.device_state == ConnectionState.NOT_CONNECTED
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)
        assert manager.device_state == ConnectionState.NOT_CONNECTED

        writer.write((json.dumps(telemetry_message()) + "\n").encode())
        await writer.drain()
        await asyncio.wait_for(manager._valid_message_event.wait(), timeout=1.0)
        assert manager.device_state == ConnectionState.ONLINE
        status = manager.get_lander_status()
        assert status.timestamp_ms == 1000
        assert status.bmp280_ok is True

        request = CommandRequest(command_id="test-status", command=CommandName.GET_STATUS)
        command_task = asyncio.create_task(manager.send_command(request))
        command = json.loads((await asyncio.wait_for(reader.readline(), 1.0)).decode())
        assert command["command"] == "GET_STATUS"
        writer.write((json.dumps({
            "type": "command_ack", "request_id": command["request_id"],
            "accepted": True, "reason": None,
        }) + "\n").encode())
        await writer.drain()
        response = await asyncio.wait_for(command_task, 1.0)
        assert response.accepted is True
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        await manager.stop()


@pytest.mark.anyio
async def test_invalid_telemetry_does_not_mark_lander_online_or_replace_state():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    manager = LanderManager(config, LanderTCPTransport("127.0.0.1", 0), BroadcasterStub())
    await manager._process_raw_line('{"type":"telemetry","timestamp_ms":3}')
    assert manager.device_state == ConnectionState.NOT_CONNECTED
    assert manager._last_seen_timestamp is None
    await manager._process_raw_line(json.dumps(telemetry_message()))
    before = manager.get_lander_status()
    await manager._process_raw_line('{"type":"telemetry","timestamp_ms":3}')
    assert manager.get_lander_status() == before
    assert manager.device_state == ConnectionState.ONLINE


def test_valid_receipt_timeout_marks_lander_offline_and_clears_live_readings():
    config = GatewayConfig(stale_timeout_s=3.0, offline_timeout_s=5.0)
    manager = LanderManager(config, LanderTCPTransport("127.0.0.1", 0), BroadcasterStub())
    manager._last_seen_timestamp = 10.0
    manager._device_state = ConnectionState.ONLINE
    manager._timestamp_ms = 1000
    manager._bmp280_ok = True
    manager._evaluate_staleness(now=16.0)
    assert manager.device_state == ConnectionState.OFFLINE
    assert manager.get_lander_status().timestamp_ms is None


@pytest.mark.anyio
async def test_tcp_gateway_listener_lifecycle_is_separate_from_device_presence():
    transport = LanderTCPTransport("127.0.0.1", 0)
    await transport.open()
    try:
        assert transport.server is not None
        assert transport.is_open() is False
    finally:
        await transport.close()
