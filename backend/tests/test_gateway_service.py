"""Phase C: Raspberry Pi Hardware Gateway Tests.

Tests all 12 required scenarios using hardware-free SimulatedSerialTransport:
1. Gateway startup and /health
2. Device inventory /api/devices (Pi gateway vs ESP32 status)
3. ESP32 serial reading and WebSocket telemetry broadcasting
4. Command dispatch via POST /api/commands (UUID -> int -> ESP32 -> ack -> UUID)
5. Command rejection when ESP32 is OFFLINE
6. Malformed line / bootloader text handling without crashing
7. Reconnection flow: bounded retry, status query on reconnect, zero auto-movement
8. Gate state invalidation to UNKNOWN on disconnect
9. WebSocket client connect/disconnect without disrupting serial read
10. Serial port concurrency: multiple commands do not corrupt framing
11. Timeout handling when ESP32 does not ACK in time
12. Hardware-free simulated transport end-to-end operation
"""

import asyncio
import json
import pytest

from starlette.websockets import WebSocketState

from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    ConnectionState,
    GateState,
    OperatingMode,
)
from gateway.config import GatewayConfig
from gateway.main import create_gateway_app
from gateway.serial_manager import SerialManager
from gateway.transport import SimulatedSerialTransport
from gateway.ws_manager import WebSocketBroadcaster


class MockWebSocket:
    """Mock WebSocket for testing WebSocketBroadcaster without network sockets."""

    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTING
        self.received_messages: list[str] = []

    async def accept(self) -> None:
        self.client_state = WebSocketState.CONNECTED

    async def send_text(self, text: str) -> None:
        if self.client_state != WebSocketState.CONNECTED:
            raise ConnectionError("WebSocket is not connected")
        self.received_messages.append(text)


@pytest.fixture
def gateway_setup():
    """Create a configured gateway with SimulatedSerialTransport."""
    config = GatewayConfig(
        serial_port="/dev/ttyUSB0",
        command_timeout_s=0.2,
        stale_timeout_s=0.5,
        offline_timeout_s=1.0,
        reconnect_delay_s=0.1,
    )
    transport = SimulatedSerialTransport()
    app = create_gateway_app(config=config, transport=transport)
    manager: SerialManager = app.state.serial_manager
    ws_broadcaster: WebSocketBroadcaster = app.state.ws_broadcaster
    return app, manager, transport, ws_broadcaster, config


# 1. Gateway startup and /health
@pytest.mark.anyio
async def test_gateway_startup_and_health(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    assert manager.is_running is False
    await manager.start()
    try:
        assert manager.is_running is True
        health = manager.get_health()
        assert health.status == "healthy"
        assert health.connection_state == ConnectionState.ONLINE
        assert health.version == "1.0.0"
        assert health.uptime_seconds >= 0.0
        assert health.serial_port == "/dev/ttyUSB0"
        assert health.device_connected is True
    finally:
        await manager.stop()
        assert manager.is_running is False


# 2. Device inventory /api/devices
@pytest.mark.anyio
async def test_gateway_devices_inventory(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        devices_resp = manager.get_devices()
        assert len(devices_resp.devices) == 1
        dev = devices_resp.devices[0]
        assert dev.device_id == "esp32-lander"
        assert dev.name == "ESP32 Lander Controller"
        assert dev.port == "/dev/ttyUSB0"
        assert dev.connection_state == ConnectionState.ONLINE
        assert dev.firmware_version == "1.3.1"
    finally:
        await manager.stop()


# 3. ESP32 serial reading and WebSocket telemetry broadcasting
@pytest.mark.anyio
async def test_serial_reading_and_websocket_telemetry_broadcast(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    mock_ws = MockWebSocket()
    await ws_broadcaster.connect(mock_ws)

    await manager.start()
    try:
        # Drain the initial GET_STATUS emitted on startup
        _ = await transport.get_tx_line(timeout=0.2)

        # Inject periodic telemetry from ESP32
        telem = {
            "type": "telemetry",
            "timestamp_ms": 12345,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
            "bmp_temperature_c": 24.5,
            "pressure_hpa": 1013.2,
            "dht_temperature_c": 24.0,
            "humidity_pct": 55.0,
            "bmp280_ok": True,
            "dht11_ok": True,
            "fault": None,
        }
        transport.inject_rx_line(json.dumps(telem))

        # Give reader loop a moment to ingest and broadcast
        await asyncio.sleep(0.05)

        # Verify broadcast
        assert len(mock_ws.received_messages) == 1
        received = json.loads(mock_ws.received_messages[0])
        assert received["type"] == "telemetry"
        assert received["gate_state"] == "CLOSED"
        assert received["bmp_temperature_c"] == 24.5

        # Verify cached status in SerialManager
        status = manager.get_lander_status()
        assert status.gate_state == GateState.CLOSED
        assert status.closed_limit is True
        assert status.open_limit is False
        assert status.mode == OperatingMode.ACTIVE
        assert status.timestamp_ms == 12345
    finally:
        await manager.stop()


# 4. Command dispatch via POST /api/commands (UUID -> int -> ESP32 -> ack -> UUID)
@pytest.mark.anyio
async def test_command_dispatch_uuid_to_int_and_ack_correlation(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)  # discard startup status query

        cmd_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        cmd_req = CommandRequest(command_id=cmd_uuid, command=CommandName.OPEN_GATE)

        async def responder():
            # Await the line sent over serial
            raw_tx = await transport.get_tx_line(timeout=0.5)
            data = json.loads(raw_tx)
            # ESP32 receives command and integer request_id (NEVER the UUID)
            assert data["command"] == "OPEN_GATE"
            assert isinstance(data["request_id"], int)
            req_id = data["request_id"]

            # ESP32 responds with command_ack
            ack_line = json.dumps({
                "type": "command_ack",
                "request_id": req_id,
                "accepted": True,
                "reason": None,
                "fault": None,
            })
            transport.inject_rx_line(ack_line)

        # Run command dispatch and responder concurrently
        async with asyncio.TaskGroup() as tg:
            tg.create_task(responder())
            cmd_task = tg.create_task(manager.send_command(cmd_req))

        response = cmd_task.result()
        # Gateway mapped back to original UUID
        assert response.command_id == cmd_uuid
        assert response.accepted is True
        assert response.reason is None
    finally:
        await manager.stop()


# 5. Command rejection when ESP32 is OFFLINE
@pytest.mark.anyio
async def test_command_rejected_when_offline(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # Disconnect transport
        transport.disconnect()
        # Trigger disconnect in manager
        manager._handle_disconnect()
        assert manager.device_state == ConnectionState.OFFLINE

        cmd_req = CommandRequest(command_id="cmd-offline-test", command=CommandName.OPEN_GATE)
        response = await manager.send_command(cmd_req)

        assert response.accepted is False
        assert response.reason == "DEVICE_OFFLINE"
        assert transport.tx_queue.empty()
    finally:
        await manager.stop()


# 6. Malformed line / bootloader text handling without crashing
@pytest.mark.anyio
async def test_malformed_and_bootloader_text_filtering(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # Inject typical ESP32 ROM bootloader outputs and malformed noise
        transport.inject_rx_line("rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)")
        transport.inject_rx_line("configsip: 0, SPIWP:0xee")
        transport.inject_rx_line("clk_drv:0x00,q_drv:0x00,d_drv:0x00,cs0_drv:0x00")
        transport.inject_rx_line("{malformed non-json: line, []")
        transport.inject_rx_line("random garbage byte noise\x00\x01\xff")

        await asyncio.sleep(0.05)
        # Ensure manager is still running smoothly and did not crash
        assert manager.is_running is True
        assert manager.device_state == ConnectionState.ONLINE

        # Subsequent valid telemetry is parsed normally
        valid_telem = {
            "type": "telemetry",
            "timestamp_ms": 20000,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
        }
        transport.inject_rx_line(json.dumps(valid_telem))
        await asyncio.sleep(0.05)

        status = manager.get_lander_status()
        assert status.timestamp_ms == 20000
        assert status.gate_state == GateState.CLOSED
    finally:
        await manager.stop()


# 7. Reconnection flow: bounded retry, status query on reconnect, zero auto-movement
@pytest.mark.anyio
async def test_reconnection_flow_queries_status_zero_auto_movement(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # Simulate disconnect
        transport.disconnect()
        manager._handle_disconnect()
        assert manager.device_state == ConnectionState.OFFLINE
        assert manager.gate_state == GateState.UNKNOWN

        # Reconnect
        transport.reconnect()
        # Reader loop will discover reconnection and issue fresh GET_STATUS
        await asyncio.sleep(0.15)

        # Check line emitted upon reconnect
        tx_line = await transport.get_tx_line(timeout=0.5)
        cmd_data = json.loads(tx_line)
        # MUST strictly be GET_STATUS
        assert cmd_data["command"] == "GET_STATUS"
        # Zero movement commands
        assert cmd_data["command"] not in ("OPEN_GATE", "CLOSE_GATE")
        assert transport.tx_queue.empty()
    finally:
        await manager.stop()


# 8. Gate state invalidation to UNKNOWN on disconnect
@pytest.mark.anyio
async def test_gate_state_invalidated_to_unknown_on_disconnect(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # Establish verified CLOSED state
        telem = {
            "type": "telemetry",
            "timestamp_ms": 5000,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
        }
        transport.inject_rx_line(json.dumps(telem))
        await asyncio.sleep(0.05)
        assert manager.get_lander_status().gate_state == GateState.CLOSED

        # Disconnect ESP32
        transport.disconnect()
        manager._handle_disconnect()

        # Gate state must strictly revert to UNKNOWN with limits False
        status = manager.get_lander_status()
        assert status.device_state == ConnectionState.OFFLINE
        assert status.gate_state == GateState.UNKNOWN
        assert status.closed_limit is False
        assert status.open_limit is False
        assert status.mode is None
        assert status.timestamp_ms is None
    finally:
        await manager.stop()


# 9. WebSocket client connect/disconnect without disrupting serial read
@pytest.mark.anyio
async def test_websocket_client_disconnect_does_not_disrupt_serial(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    client_a = MockWebSocket()
    client_b = MockWebSocket()

    await ws_broadcaster.connect(client_a)
    await ws_broadcaster.connect(client_b)
    assert ws_broadcaster.active_connections_count == 2

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # Abruptly disconnect client A
        client_a.client_state = WebSocketState.DISCONNECTED

        # Inject telemetry
        telem = {
            "type": "telemetry",
            "timestamp_ms": 100,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
        }
        transport.inject_rx_line(json.dumps(telem))
        await asyncio.sleep(0.05)

        # Client B received message, client A was pruned
        assert len(client_b.received_messages) == 1
        assert ws_broadcaster.active_connections_count == 1
        assert manager.is_running is True
    finally:
        await manager.stop()


# 10. Serial port concurrency: multiple commands do not corrupt framing
@pytest.mark.anyio
async def test_serial_concurrency_no_corrupted_framing(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        commands_to_send = [
            ("uuid-1", CommandName.GET_STATUS),
            ("uuid-2", CommandName.SET_ACTIVE),
            ("uuid-3", CommandName.GET_STATUS),
            ("uuid-4", CommandName.SET_ACTIVE),
        ]

        async def responder():
            for _ in range(len(commands_to_send)):
                tx_line = await transport.get_tx_line(timeout=1.0)
                # Verify framing: must be valid JSON object with command and request_id
                data = json.loads(tx_line)
                assert "command" in data
                assert "request_id" in data
                # Return ACK
                transport.inject_rx_line(json.dumps({
                    "type": "command_ack",
                    "request_id": data["request_id"],
                    "accepted": True,
                    "reason": None,
                }))

        async def send_cmd(cid, cname):
            req = CommandRequest(command_id=cid, command=cname)
            return await manager.send_command(req)

        async with asyncio.TaskGroup() as tg:
            tg.create_task(responder())
            tasks = [tg.create_task(send_cmd(cid, cname)) for cid, cname in commands_to_send]

        responses = [t.result() for t in tasks]
        for idx, resp in enumerate(responses):
            assert resp.command_id == commands_to_send[idx][0]
            assert resp.accepted is True
    finally:
        await manager.stop()


# 11. Timeout handling when ESP32 does not ACK in time
@pytest.mark.anyio
async def test_command_timeout_when_no_ack_received(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup
    config.command_timeout_s = 0.05  # Fast timeout for test

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # Send command, but simulated lander produces NO ACK
        cmd_req = CommandRequest(command_id="cmd-timeout-test", command=CommandName.OPEN_GATE)
        resp = await manager.send_command(cmd_req)

        assert resp.command_id == "cmd-timeout-test"
        assert resp.accepted is False
        assert resp.reason == "DEVICE_TIMEOUT"

        # Verify mapper freed active state
        assert not manager.mapper.is_active("cmd-timeout-test")
    finally:
        await manager.stop()


# 12. Hardware-free simulated transport end-to-end operation
@pytest.mark.anyio
async def test_hardware_free_simulated_transport_e2e(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    mock_ws = MockWebSocket()
    await ws_broadcaster.connect(mock_ws)

    await manager.start()
    try:
        # 1. Startup triggers GET_STATUS
        tx_line = await transport.get_tx_line(timeout=0.5)
        startup_req = json.loads(tx_line)
        assert startup_req["command"] == "GET_STATUS"

        # Respond to initial status
        transport.inject_rx_line(json.dumps({
            "type": "status",
            "request_id": startup_req["request_id"],
            "timestamp_ms": 1000,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
            "fault": None,
            "bmp280_ok": True,
            "dht11_ok": True,
        }))
        await asyncio.sleep(0.05)

        status1 = manager.get_lander_status()
        assert status1.gate_state == GateState.CLOSED
        assert status1.closed_limit is True

        # 2. Gate starts opening (asynchronous gate_status event)
        transport.inject_rx_line(json.dumps({
            "type": "gate_status",
            "state": "OPENING",
            "closed_limit": False,
            "open_limit": False,
        }))
        await asyncio.sleep(0.05)

        status2 = manager.get_lander_status()
        assert status2.gate_state == GateState.OPENING
        assert status2.closed_limit is False

        # 3. Gate reaches fully open
        transport.inject_rx_line(json.dumps({
            "type": "gate_status",
            "state": "OPEN",
            "closed_limit": False,
            "open_limit": True,
        }))
        await asyncio.sleep(0.05)

        status3 = manager.get_lander_status()
        assert status3.gate_state == GateState.OPEN
        assert status3.open_limit is True

        # 4. Fault occurs (both limit switches active)
        transport.inject_rx_line(json.dumps({
            "type": "gate_status",
            "state": "FAULT",
            "fault": "BOTH_LIMITS_ACTIVE",
            "closed_limit": True,
            "open_limit": True,
        }))
        await asyncio.sleep(0.05)

        status4 = manager.get_lander_status()
        assert status4.gate_state == GateState.FAULT
        assert status4.fault == "BOTH_LIMITS_ACTIVE"

        # Verify all 3 events were broadcast to WebSocket
        assert len(mock_ws.received_messages) == 3
    finally:
        await manager.stop()


# 13. Serial write error fails gracefully without 500 or unhandled crash
@pytest.mark.anyio
async def test_serial_write_error_fails_gracefully(gateway_setup):
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        manager._device_state = ConnectionState.ONLINE

        # Unplug transport right before write
        transport.disconnect()

        cmd_req = CommandRequest(command_id="cmd-write-err-test", command=CommandName.OPEN_GATE)
        resp = await manager.send_command(cmd_req)

        assert resp.command_id == "cmd-write-err-test"
        assert resp.accepted is False
        assert resp.reason == "DEVICE_WRITE_ERROR"
        assert manager.device_state == ConnectionState.OFFLINE
    finally:
        await manager.stop()


# 14. Sensor state reconciliation: FAILED to OK, OK to FAILED, NO_DATA, and BMP280/DHT11 consistency
@pytest.mark.anyio
async def test_sensor_state_transitions_failed_to_ok_via_telemetry(gateway_setup):
    """Verify that when a sensor was FAILED at boot, fresh telemetry with ok=True updates state to OK."""
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # 1. Boot status: DHT11 is FAILED (cold boot settle), BMP280 is FAILED
        transport.inject_rx_line(json.dumps({
            "type": "status",
            "request_id": 1,
            "timestamp_ms": 500,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
            "fault": None,
            "bmp280_ok": False,
            "dht11_ok": False,
            "bmp280_state": "FAILED",
            "dht11_state": "FAILED",
        }))
        await asyncio.sleep(0.05)

        status_init = manager.get_lander_status()
        assert status_init.dht11_ok is False
        assert status_init.dht11_state == "FAILED"
        assert status_init.bmp280_ok is False
        assert status_init.bmp280_state == "FAILED"

        # 2. Telemetry arrives 2 seconds later: DHT11 power settled, read succeeded!
        # Note: Telemetry frames in ESP32 v1.3.1 firmware omit the state strings.
        transport.inject_rx_line(json.dumps({
            "type": "telemetry",
            "timestamp_ms": 2500,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
            "bmp_temperature_c": None,
            "pressure_hpa": None,
            "dht_temperature_c": 22.5,
            "humidity_pct": 48.0,
            "bmp280_ok": False,
            "dht11_ok": True,
            "fault": None,
        }))
        await asyncio.sleep(0.05)

        # DHT11 state MUST now be "OK" (not stale "FAILED") while BMP280 remains "FAILED"
        status_updated = manager.get_lander_status()
        assert status_updated.dht11_ok is True
        assert status_updated.dht11_state == "OK"
        assert status_updated.bmp280_ok is False
        assert status_updated.bmp280_state == "FAILED"

        # 3. Sensor failure occurs later: DHT11 is unplugged, telemetry arrives with dht11_ok: False
        transport.inject_rx_line(json.dumps({
            "type": "telemetry",
            "timestamp_ms": 3500,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
            "bmp_temperature_c": None,
            "pressure_hpa": None,
            "dht_temperature_c": None,
            "humidity_pct": None,
            "bmp280_ok": False,
            "dht11_ok": False,
            "fault": None,
        }))
        await asyncio.sleep(0.05)

        # DHT11 state MUST transition to "FAILED" and not remain stale "OK"
        status_failed = manager.get_lander_status()
        assert status_failed.dht11_ok is False
        assert status_failed.dht11_state == "FAILED"
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_sensor_state_preserves_no_data_semantics(gateway_setup):
    """Verify that NO_DATA semantics are preserved before initial polling."""
    app, manager, transport, ws_broadcaster, config = gateway_setup

    await manager.start()
    try:
        _ = await transport.get_tx_line(timeout=0.2)

        # Status reports NO_DATA for DHT11 (e.g. before first active session poll)
        transport.inject_rx_line(json.dumps({
            "type": "status",
            "request_id": 1,
            "timestamp_ms": 100,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
            "fault": None,
            "bmp280_ok": False,
            "dht11_ok": False,
            "bmp280_state": "FAILED",
            "dht11_state": "NO_DATA",
        }))
        await asyncio.sleep(0.05)

        status = manager.get_lander_status()
        assert status.dht11_ok is False
        assert status.dht11_state == "NO_DATA"

        # Telemetry arrives with dht11_ok=True -> transitions to OK
        transport.inject_rx_line(json.dumps({
            "type": "telemetry",
            "timestamp_ms": 1200,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
            "bmp_temperature_c": 21.0,
            "pressure_hpa": 1013.2,
            "dht_temperature_c": 21.5,
            "humidity_pct": 50.0,
            "bmp280_ok": True,
            "dht11_ok": True,
            "fault": None,
        }))
        await asyncio.sleep(0.05)

        status_after = manager.get_lander_status()
        assert status_after.bmp280_ok is True
        assert status_after.bmp280_state == "OK"
        assert status_after.dht11_ok is True
        assert status_after.dht11_state == "OK"
    finally:
        await manager.stop()
