"""Unit and integration tests for LanderManager logic on Raspberry Pi Gateway."""

import asyncio
from datetime import datetime, timezone
import json
import pytest

from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    ConnectionState,
    OperatingMode,
)
from gateway.config import GatewayConfig
from gateway.lander_manager import LanderManager
from gateway.tcp_transport import LanderTCPTransport


class BroadcasterStub:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, message):
        self.broadcasts.append(message)


def valid_telemetry():
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


def valid_status():
    return {
        "type": "status",
        "timestamp_ms": 1000,
        "mode": "ACTIVE",
        "sensors_polling": True,
        "bmp280_ok": True,
        "dht11_ok": True,
        "bmp280_state": "OK",
        "dht11_state": "OK",
        "firmware": "1.4.0",
    }


@pytest.mark.anyio
async def test_manager_liveness_only_refreshed_by_valid_messages():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())

    assert manager.device_state == ConnectionState.NOT_CONNECTED

    # 1. Invalid JSON string
    await manager._process_raw_line("NOT_JSON")
    assert manager.device_state == ConnectionState.NOT_CONNECTED
    assert manager._last_seen_timestamp is None

    # 2. Unknown message type
    await manager._process_raw_line(json.dumps({"type": "unknown_type"}))
    assert manager.device_state == ConnectionState.NOT_CONNECTED

    # 3. Message containing retired actuator fields
    bad_telem = valid_telemetry()
    bad_telem["gate_state"] = "OPEN"
    await manager._process_raw_line(json.dumps(bad_telem))
    assert manager.device_state == ConnectionState.NOT_CONNECTED

    # 4. Message with boolean where integer expected (timestamp_ms: True)
    bad_status = valid_status()
    bad_status["timestamp_ms"] = True
    await manager._process_raw_line(json.dumps(bad_status))
    assert manager.device_state == ConnectionState.NOT_CONNECTED

    # 5. Message with boolean where integer expected in request_id
    bad_ack = {"type": "command_ack", "request_id": False, "accepted": True}
    await manager._process_raw_line(json.dumps(bad_ack))
    assert manager.device_state == ConnectionState.NOT_CONNECTED

    # 6. Valid telemetry restores ONLINE
    await manager._process_raw_line(json.dumps(valid_telemetry()))
    assert manager.device_state == ConnectionState.ONLINE
    assert manager._last_seen_timestamp is not None

    # 7. Another malformed message does not crash or disconnect
    await manager._process_raw_line("MALFORMED")
    assert manager.device_state == ConnectionState.ONLINE


@pytest.mark.anyio
async def test_status_snapshot_synchronization_and_firmware_version():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())

    # Initial state has no stale firmware default
    assert manager.get_devices().devices[0].firmware_version is None
    assert manager.get_lander_status().firmware is None

    # Receive status snapshot as emitted by ESP32 on connect
    status_msg = valid_status()
    await manager._process_raw_line(json.dumps(status_msg))

    assert manager.device_state == ConnectionState.ONLINE
    assert manager.get_devices().devices[0].firmware_version == "1.4.0"
    status_resp = manager.get_lander_status()
    assert status_resp.firmware == "1.4.0"
    assert status_resp.mode == OperatingMode.ACTIVE
    assert status_resp.bmp280_ok is True
    assert status_resp.dht11_ok is True
    assert status_resp.bmp280_state == "OK"
    assert status_resp.dht11_state == "OK"


@pytest.mark.anyio
async def test_command_dispatch_and_correlation():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0, command_timeout_s=1.0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)

        # Make device ONLINE first
        writer.write((json.dumps(valid_status()) + "\n").encode())
        await writer.drain()
        await asyncio.sleep(0.05)
        assert manager.device_state == ConnectionState.ONLINE

        # Dispatch SET_STANDBY command
        req = CommandRequest(command_id="cmd-101", command=CommandName.SET_STANDBY)
        cmd_task = asyncio.create_task(manager.send_command(req))

        raw_cmd = await asyncio.wait_for(reader.readline(), timeout=1.0)
        cmd_json = json.loads(raw_cmd.decode())
        assert cmd_json["command"] == "SET_STANDBY"
        assert isinstance(cmd_json["request_id"], int)

        # Reply with correlated ACK
        ack_payload = {
            "type": "command_ack",
            "request_id": cmd_json["request_id"],
            "accepted": True,
            "reason": None,
        }
        writer.write((json.dumps(ack_payload) + "\n").encode())
        await writer.drain()

        resp = await asyncio.wait_for(cmd_task, timeout=1.0)
        assert resp.accepted is True
        assert resp.command_id == "cmd-101"

        # Check pending futures cleaned up
        assert len(manager._pending_commands) == 0
        assert not manager.mapper.is_active("cmd-101")

        writer.close()
        await writer.wait_closed()
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_command_timeout_cleans_up_future_and_mapper():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0, command_timeout_s=0.1)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)
        writer.write((json.dumps(valid_status()) + "\n").encode())
        await writer.drain()
        await asyncio.sleep(0.05)

        req = CommandRequest(command_id="cmd-timeout", command=CommandName.GET_STATUS)
        # Client does NOT reply -> should timeout
        resp = await manager.send_command(req)

        assert resp.accepted is False
        assert resp.reason == "DEVICE_TIMEOUT"
        assert len(manager._pending_commands) == 0
        assert not manager.mapper.is_active("cmd-timeout")

        writer.close()
        await writer.wait_closed()
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_client_disconnect_fails_pending_commands_and_cleans_state():
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0, command_timeout_s=2.0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)
        writer.write((json.dumps(valid_status()) + "\n").encode())
        await writer.drain()
        await asyncio.sleep(0.05)

        # Dispatch command
        req = CommandRequest(command_id="cmd-disconnect", command=CommandName.SET_ACTIVE)
        cmd_task = asyncio.create_task(manager.send_command(req))

        await reader.readline()

        # Abruptly close client connection
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(0.05)

        resp = await asyncio.wait_for(cmd_task, timeout=1.0)
        assert resp.accepted is False
        assert resp.reason == "DEVICE_OFFLINE"
        assert manager.device_state in (ConnectionState.OFFLINE, ConnectionState.NOT_CONNECTED)
        assert len(manager._pending_commands) == 0
        assert manager.get_lander_status().timestamp_ms is None
    finally:
        await manager.stop()


def test_staleness_and_offline_transitions():
    config = GatewayConfig(stale_timeout_s=1.0, offline_timeout_s=3.0)
    transport = LanderTCPTransport("127.0.0.1", 0)
    manager = LanderManager(config, transport, BroadcasterStub())

    manager._last_seen_timestamp = 100.0
    manager._device_state = ConnectionState.ONLINE
    manager._timestamp_ms = 5000
    manager._bmp280_ok = True
    manager._firmware = "1.4.0"

    # At 100.5s -> still ONLINE
    manager._evaluate_staleness(now=100.5)
    assert manager.device_state == ConnectionState.ONLINE

    # At 101.5s -> elapsed 1.5s > stale_timeout_s (1.0s) -> STALE
    manager._evaluate_staleness(now=101.5)
    assert manager.device_state == ConnectionState.STALE
    # STALE preserves last known telemetry
    assert manager.get_lander_status().timestamp_ms == 5000

    # At 103.5s -> elapsed 3.5s > offline_timeout_s (3.0s) -> OFFLINE
    manager._evaluate_staleness(now=103.5)
    assert manager.device_state == ConnectionState.OFFLINE
    # OFFLINE invalidates cached hardware state
    status = manager.get_lander_status()
    assert status.timestamp_ms is None
    assert status.mode is None
    assert status.firmware is None
    assert status.bmp280_state == "NO_DATA"


def test_gateway_health_independent_of_device_connection():
    config = GatewayConfig()
    transport = LanderTCPTransport("127.0.0.1", 0)
    manager = LanderManager(config, transport, BroadcasterStub())

    # Gateway process is ONLINE, device is NOT_CONNECTED
    health = manager.get_health()
    assert health.status == "healthy"
    assert health.connection_state == ConnectionState.ONLINE
    assert health.device_connected is False

    # Device becomes ONLINE
    manager._device_state = ConnectionState.ONLINE
    health = manager.get_health()
    assert health.status == "healthy"
    assert health.device_connected is True

    # Device becomes OFFLINE
    manager._device_state = ConnectionState.OFFLINE
    health = manager.get_health()
    assert health.status == "healthy"
    assert health.device_connected is False


@pytest.mark.anyio
async def test_get_status_synchronization_while_device_not_online():
    """Verify GET_STATUS is permitted when link is open even before device is ONLINE."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0, command_timeout_s=1.0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)
        await asyncio.sleep(0.05)

        # Device is NOT_CONNECTED / not yet ONLINE
        assert manager.device_state == ConnectionState.NOT_CONNECTED
        assert transport.is_open() is True

        # State-changing commands (e.g. SET_ACTIVE) should be rejected
        set_active_req = CommandRequest(command_id="cmd-mode-fail", command=CommandName.SET_ACTIVE)
        resp = await manager.send_command(set_active_req)
        assert resp.accepted is False
        assert resp.reason == "DEVICE_OFFLINE"

        # But GET_STATUS (discovery/sync query) is permitted across open link!
        sync_req = CommandRequest(command_id="sync-status", command=CommandName.GET_STATUS)
        sync_task = asyncio.create_task(manager.send_command(sync_req))

        raw_cmd = await asyncio.wait_for(reader.readline(), timeout=1.0)
        cmd_json = json.loads(raw_cmd.decode())
        assert cmd_json["command"] == "GET_STATUS"
        req_id = cmd_json["request_id"]

        # ESP32 responds with status snapshot carrying the matching request_id
        status_with_id = valid_status()
        status_with_id["request_id"] = req_id
        writer.write((json.dumps(status_with_id) + "\n").encode())
        await writer.drain()

        resp = await asyncio.wait_for(sync_task, timeout=1.0)
        assert resp.accepted is True
        assert manager.device_state == ConnectionState.ONLINE
        assert manager.get_lander_status().firmware == "1.4.0"

        writer.close()
        await writer.wait_closed()
    finally:
        await manager.stop()

