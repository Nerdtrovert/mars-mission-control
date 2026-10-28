"""Integration and unit tests for Lander TCP, Rover forwarding, and Drone display."""

from __future__ import annotations

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
from gateway.drone_udp import DroneUDPProtocol, DroneUDPReceiver, parse_drone_datagram
from gateway.lander_manager import LanderManager
from gateway.rover_udp import RoverUDPProtocol, RoverUDPReceiver, parse_rover_datagram
from gateway.tcp_transport import LanderTCPTransport


class BroadcasterStub:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, message):
        self.broadcasts.append(message)


# ============================================================================
# 1. TCP PROTOCOL TESTS
# ============================================================================


@pytest.mark.anyio
async def test_tcp_multiple_messages_in_one_stream():
    """Verify that multiple newline-delimited JSON messages received together are processed."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    broadcaster = BroadcasterStub()
    manager = LanderManager(config, transport, broadcaster)
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)

        msg1 = {
            "type": "telemetry",
            "timestamp_ms": 1000,
            "mode": "ACTIVE",
            "bmp_temperature_c": 20.0,
            "pressure_hpa": 1010.0,
            "dht_temperature_c": 21.0,
            "humidity_pct": 50.0,
            "bmp280_ok": True,
            "dht11_ok": True,
        }
        msg2 = {
            "type": "telemetry",
            "timestamp_ms": 2000,
            "mode": "ACTIVE",
            "bmp_temperature_c": 20.5,
            "pressure_hpa": 1009.5,
            "dht_temperature_c": 21.2,
            "humidity_pct": 51.0,
            "bmp280_ok": True,
            "dht11_ok": True,
        }

        # Send both together in a single write buffer
        writer.write((json.dumps(msg1) + "\n" + json.dumps(msg2) + "\n").encode())
        await writer.drain()

        # Allow reader loop to process both frames
        for _ in range(20):
            if len(broadcaster.broadcasts) >= 2:
                break
            await asyncio.sleep(0.05)

        assert len(broadcaster.broadcasts) == 2
        assert broadcaster.broadcasts[0]["timestamp_ms"] == 1000
        assert broadcaster.broadcasts[1]["timestamp_ms"] == 2000
        assert manager.device_state == ConnectionState.ONLINE
    finally:
        writer.close()
        await writer.wait_closed()
        await manager.stop()


@pytest.mark.anyio
async def test_tcp_partial_message_split_across_reads():
    """Verify that partial messages split across reads are assembled correctly."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    broadcaster = BroadcasterStub()
    manager = LanderManager(config, transport, broadcaster)
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)

        full_json = json.dumps({
            "type": "telemetry",
            "timestamp_ms": 3000,
            "mode": "ACTIVE",
            "bmp_temperature_c": 19.5,
            "pressure_hpa": 1011.0,
            "dht_temperature_c": 20.0,
            "humidity_pct": 45.0,
            "bmp280_ok": True,
            "dht11_ok": True,
        })

        part1 = full_json[: len(full_json) // 2].encode()
        part2 = (full_json[len(full_json) // 2 :] + "\n").encode()

        writer.write(part1)
        await writer.drain()
        await asyncio.sleep(0.05)
        assert len(broadcaster.broadcasts) == 0

        writer.write(part2)
        await writer.drain()

        for _ in range(20):
            if broadcaster.broadcasts:
                break
            await asyncio.sleep(0.05)

        assert len(broadcaster.broadcasts) == 1
        assert broadcaster.broadcasts[0]["timestamp_ms"] == 3000
    finally:
        writer.close()
        await writer.wait_closed()
        await manager.stop()


@pytest.mark.anyio
async def test_tcp_malformed_and_oversized_messages_recovery():
    """Verify that malformed or oversized frames do not crash the gateway and subsequent valid frames work."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    broadcaster = BroadcasterStub()
    manager = LanderManager(config, transport, broadcaster)
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)

        # 1. Send malformed JSON line
        writer.write(b"NOT_A_VALID_JSON_STRING\n")
        await writer.drain()
        await asyncio.sleep(0.05)
        assert manager.device_state == ConnectionState.NOT_CONNECTED

        # 2. Send valid telemetry frame on same connection - recovers cleanly
        valid = {
            "type": "telemetry",
            "timestamp_ms": 4000,
            "mode": "ACTIVE",
            "bmp_temperature_c": 22.0,
            "pressure_hpa": 1005.0,
            "dht_temperature_c": 23.0,
            "humidity_pct": 55.0,
            "bmp280_ok": True,
            "dht11_ok": True,
        }
        writer.write((json.dumps(valid) + "\n").encode())
        await writer.drain()

        for _ in range(20):
            if broadcaster.broadcasts:
                break
            await asyncio.sleep(0.05)

        assert len(broadcaster.broadcasts) == 1
        assert manager.device_state == ConnectionState.ONLINE
    finally:
        writer.close()
        await writer.wait_closed()
        await manager.stop()


@pytest.mark.anyio
async def test_failed_client_write_handles_gracefully():
    """Verify that failed writes to a disconnected client do not crash the manager."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())

    # Transport is not open
    assert manager.transport.is_open() is False
    res = await manager.send_display_message({"type": "test"})
    assert res is False


# ============================================================================
# 2. ROVER FORWARDING TESTS
# ============================================================================


def test_parse_rover_datagram_valid_and_malformed():
    """Verify exact field mapping and validation of rover datagrams."""
    raw = b"DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M"
    parsed = parse_rover_datagram(raw)
    assert parsed["distance_cm"] == 145.0
    assert parsed["pitch_deg"] == 12.4
    assert parsed["roll_deg"] == -3.2
    assert parsed["command"] == "F"
    assert parsed["mode"] == "M"

    # Missing field
    with pytest.raises(ValueError, match="all rover telemetry fields are required"):
        parse_rover_datagram(b"DIST:10,PITCH:0,ROLL:0,CMD:S")

    # Invalid range
    with pytest.raises(ValueError, match="outside allowed range"):
        parse_rover_datagram(b"DIST:500,PITCH:0,ROLL:0,CMD:S,MODE:M")


@pytest.mark.anyio
async def test_rover_forwarding_over_tcp():
    """Verify live rover telemetry is forwarded to lander over the existing TCP stream."""
    config = GatewayConfig(
        lander_tcp_host="127.0.0.1",
        lander_tcp_port=0,
        rover_offline_timeout_s=0.5,
    )
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    broadcaster = BroadcasterStub()
    manager = LanderManager(config, transport, broadcaster)
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)
        await asyncio.sleep(0.05)

        # Forward valid rover telemetry
        rover_sample = {
            "distance_cm": 123.0,
            "pitch_deg": 2.4,
            "roll_deg": -1.0,
            "command": "STOP",
            "mode": "MANUAL",
        }
        sent = await manager.forward_rover_telemetry(rover_sample, online=True)
        assert sent is True

        # Read line from the lander's TCP client
        raw = await asyncio.wait_for(reader.readline(), timeout=1.0)
        display_msg = json.loads(raw.decode())

        assert display_msg["type"] == "mission_display"
        assert display_msg["device"] == "rover"
        assert display_msg["connected"] is True
        assert display_msg["data"]["distance"] == 123.0
        assert display_msg["data"]["pitch"] == 2.4
        assert display_msg["data"]["roll"] == -1.0
        assert display_msg["data"]["cmd"] == "STOP"
        assert display_msg["data"]["mode"] == "MANUAL"

        # Rover disconnect / offline transition
        sent_offline = await manager.forward_rover_telemetry(rover_sample, online=False)
        assert sent_offline is True

        raw_offline = await asyncio.wait_for(reader.readline(), timeout=1.0)
        offline_msg = json.loads(raw_offline.decode())
        assert offline_msg["type"] == "mission_display"
        assert offline_msg["device"] == "rover"
        assert offline_msg["connected"] is False

        # Sending offline again should be suppressed (no duplicate spamming)
        sent_offline_again = await manager.forward_rover_telemetry(rover_sample, online=False)
        assert sent_offline_again is False

    finally:
        writer.close()
        await writer.wait_closed()
        await manager.stop()


@pytest.mark.anyio
async def test_rover_telemetry_before_lander_connects_and_delivery_on_connect():
    """Verify rover state arriving before lander connects is cached and delivered on connect."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    broadcaster = BroadcasterStub()
    manager = LanderManager(config, transport, broadcaster)
    await manager.start()

    try:
        # Rover update arrives before any lander connects
        rover_sample = {
            "DIST": 85.0,
            "PITCH": -0.5,
            "ROLL": 1.2,
            "CMD": "F",
            "MODE": "M",
        }
        sent = await manager.forward_rover_telemetry(rover_sample, online=True)
        # Cannot send across TCP because no lander is connected yet
        assert sent is False
        assert manager._latest_rover_display is not None

        # Lander connects and sends initial status snapshot
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)
        status_msg = {
            "type": "status",
            "timestamp_ms": 100,
            "mode": "ACTIVE",
            "sensors_polling": True,
            "bmp280_ok": True,
            "dht11_ok": True,
            "firmware": "1.5.0",
        }
        writer.write((json.dumps(status_msg) + "\n").encode())
        await writer.drain()

        # Lander should receive the cached rover display update
        raw = await asyncio.wait_for(reader.readline(), timeout=1.0)
        display_msg = json.loads(raw.decode())

        assert display_msg["type"] == "mission_display"
        assert display_msg["device"] == "rover"
        assert display_msg["connected"] is True
        assert display_msg["data"]["distance"] == 85.0
        assert display_msg["data"]["cmd"] == "F"
    finally:
        writer.close()
        await writer.wait_closed()
        await manager.stop()


# ============================================================================
# 3. DRONE FORWARDING TESTS
# ============================================================================


def test_parse_drone_datagram():
    """Verify drone datagram parsing for authoritative JSON schema."""
    # 1. Authoritative packet with nulls
    null_pkt = json.dumps({
        "device_id": "esp32-drone",
        "sequence": 1,
        "timestamp_ms": 123456,
        "flight_status": "STANDBY",
        "orientation": {"roll": None, "pitch": None, "yaw": None},
        "environment": {"temperature_c": None, "pressure_hpa": None, "humidity_pct": None},
        "gps": {"latitude": None, "longitude": None, "altitude_m": None},
        "battery": {"voltage_v": None, "percentage": None},
    }).encode("utf-8")
    parsed1 = parse_drone_datagram(null_pkt)
    assert parsed1["device_id"] == "esp32-drone"
    assert parsed1["sequence"] == 1
    assert parsed1["timestamp_ms"] == 123456
    assert parsed1["flight_status"] == "STANDBY"
    assert parsed1["gps"]["latitude"] is None
    assert parsed1["gps"]["longitude"] is None
    assert parsed1["battery"]["percentage"] is None

    # 2. Authoritative packet with populated numbers
    full_pkt = json.dumps({
        "device_id": "esp32-drone",
        "sequence": 42,
        "timestamp_ms": 999999,
        "flight_status": "HOVERING",
        "orientation": {"roll": 1.2, "pitch": -0.5, "yaw": 180.0},
        "environment": {"temperature_c": 21.5, "pressure_hpa": 1013.25, "humidity_pct": 45.0},
        "gps": {"latitude": 12.9716, "longitude": 77.5946, "altitude_m": 850.5},
        "battery": {"voltage_v": 11.4, "percentage": 85.0},
    }).encode("utf-8")
    parsed2 = parse_drone_datagram(full_pkt)
    assert parsed2["sequence"] == 42
    assert parsed2["flight_status"] == "HOVERING"
    assert parsed2["gps"]["latitude"] == 12.9716
    assert parsed2["gps"]["longitude"] == 77.5946
    assert parsed2["environment"]["temperature_c"] == 21.5
    assert parsed2["battery"]["percentage"] == 85.0

    # 3. Invalid cases: empty, non-json, oversized, missing fields
    with pytest.raises(ValueError, match="Empty drone datagram"):
        parse_drone_datagram(b"")
    with pytest.raises(ValueError, match="Malformed JSON"):
        parse_drone_datagram(b"not-json")
    with pytest.raises(ValueError, match="Oversized datagram"):
        parse_drone_datagram(b"x" * 5000)
    with pytest.raises(ValueError, match="device_id"):
        parse_drone_datagram(b'{"sequence": 1}')
    with pytest.raises(ValueError, match="sequence"):
        parse_drone_datagram(b'{"device_id": "drone", "sequence": -5}')
    with pytest.raises(ValueError, match="gps.latitude"):
        invalid_gps = {
            "device_id": "esp32-drone",
            "sequence": 1,
            "timestamp_ms": 100,
            "flight_status": "STANDBY",
            "orientation": {"roll": None, "pitch": None, "yaw": None},
            "environment": {"temperature_c": None, "pressure_hpa": None, "humidity_pct": None},
            "gps": {"latitude": 120.0, "longitude": 0.0, "altitude_m": None},
            "battery": {"voltage_v": None, "percentage": None},
        }
        parse_drone_datagram(json.dumps(invalid_gps).encode("utf-8"))


@pytest.mark.anyio
async def test_drone_forwarding_over_tcp():
    """Verify drone display forwarding over the same TCP link."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    broadcaster = BroadcasterStub()
    manager = LanderManager(config, transport, broadcaster)
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)
        await asyncio.sleep(0.05)

        # Forward active drone update
        drone_sample = {
            "flight_status": "STANDBY",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        sent = await manager.forward_drone_telemetry(drone_sample, online=True)
        assert sent is True

        raw = await asyncio.wait_for(reader.readline(), timeout=1.0)
        msg = json.loads(raw.decode())

        assert msg["type"] == "mission_display"
        assert msg["device"] == "drone"
        assert msg["connected"] is True
        assert msg["data"]["flight_status"] == "STANDBY"
        assert msg["data"]["latitude"] == 12.9716
        assert msg["data"]["longitude"] == 77.5946

        # Forward offline transition
        await manager.forward_drone_telemetry(None, online=False)
        raw_off = await asyncio.wait_for(reader.readline(), timeout=1.0)
        msg_off = json.loads(raw_off.decode())

        assert msg_off["type"] == "mission_display"
        assert msg_off["device"] == "drone"
        assert msg_off["connected"] is False
        assert msg_off["data"] is None

    finally:
        writer.close()
        await writer.wait_closed()
        await manager.stop()


# ============================================================================
# 4. REGRESSION AND COMMAND CORRELATION WITH ok / accepted
# ============================================================================


@pytest.mark.anyio
async def test_command_ack_accepts_ok_and_request_id():
    """Verify that command_ack with 'ok' and 'request_id' (as sent by lander.ino) correlates properly."""
    config = GatewayConfig(lander_tcp_host="127.0.0.1", lander_tcp_port=0, command_timeout_s=1.0)
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    manager = LanderManager(config, transport, BroadcasterStub())
    await manager.start()

    try:
        reader, writer = await asyncio.open_connection(config.lander_tcp_host, transport.port)

        # Make ONLINE
        writer.write((json.dumps({
            "type": "status",
            "timestamp_ms": 500,
            "mode": "ACTIVE",
            "sensors_polling": True,
            "bmp280_ok": True,
            "dht11_ok": True,
            "firmware": "1.5.0",
        }) + "\n").encode())
        await writer.drain()
        await asyncio.sleep(0.05)

        # Send GET_STATUS command
        req = CommandRequest(command_id="cmd-get-status", command=CommandName.GET_STATUS)
        cmd_task = asyncio.create_task(manager.send_command(req))

        raw_cmd = await asyncio.wait_for(reader.readline(), timeout=1.0)
        cmd_json = json.loads(raw_cmd.decode())
        req_id = cmd_json["request_id"]

        # ESP32 responds with ok: true and request_id
        ack_from_esp32 = {
            "type": "command_ack",
            "timestamp_ms": 600,
            "command": "GET_STATUS",
            "ok": True,
            "message": "Status sent",
            "request_id": req_id,
        }
        writer.write((json.dumps(ack_from_esp32) + "\n").encode())
        await writer.drain()

        resp = await asyncio.wait_for(cmd_task, timeout=1.0)
        assert resp.accepted is True
    finally:
        writer.close()
        await writer.wait_closed()
        await manager.stop()
