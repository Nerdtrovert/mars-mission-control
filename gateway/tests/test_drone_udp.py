"""Tests for Raspberry Pi Drone UDP receiver and integration."""

import json
import pytest

from gateway.config import GatewayConfig
from gateway.drone_udp import (
    DroneUDPProtocol,
    is_newer_sequence,
    parse_drone_datagram,
)
from gateway.main import create_gateway_app
from gateway.tcp_transport import LanderTCPTransport


class BroadcasterStub:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, message):
        self.broadcasts.append(message)


class LanderManagerStub:
    def __init__(self):
        self.forwarded = []

    async def forward_drone_telemetry(self, data, online=True):
        self.forwarded.append({"data": data, "online": online})
        return True


def test_parse_drone_datagram_authoritative_nulls():
    pkt = json.dumps({
        "device_id": "esp32-drone",
        "sequence": 1,
        "timestamp_ms": 123456,
        "flight_status": "STANDBY",
        "orientation": {"roll": None, "pitch": None, "yaw": None},
        "environment": {"temperature_c": None, "pressure_hpa": None, "humidity_pct": None},
        "gps": {"latitude": None, "longitude": None, "altitude_m": None},
        "battery": {"voltage_v": None, "percentage": None},
    }).encode("utf-8")

    parsed = parse_drone_datagram(pkt)
    assert parsed["device_id"] == "esp32-drone"
    assert parsed["sequence"] == 1
    assert parsed["timestamp_ms"] == 123456
    assert parsed["flight_status"] == "STANDBY"
    assert parsed["orientation"]["roll"] is None
    assert parsed["environment"]["temperature_c"] is None
    assert parsed["gps"]["latitude"] is None
    assert parsed["battery"]["voltage_v"] is None


def test_parse_drone_datagram_populated_values():
    pkt = json.dumps({
        "device_id": "esp32-drone",
        "sequence": 10,
        "timestamp_ms": 500000,
        "flight_status": "CRUISING",
        "orientation": {"roll": -2.5, "pitch": 1.8, "yaw": 90.0},
        "environment": {"temperature_c": 18.2, "pressure_hpa": 1010.5, "humidity_pct": 52.0},
        "gps": {"latitude": 13.0827, "longitude": 80.2707, "altitude_m": 120.0},
        "battery": {"voltage_v": 11.8, "percentage": 92.0},
    }).encode("utf-8")

    parsed = parse_drone_datagram(pkt)
    assert parsed["device_id"] == "esp32-drone"
    assert parsed["sequence"] == 10
    assert parsed["flight_status"] == "CRUISING"
    assert parsed["orientation"]["roll"] == -2.5
    assert parsed["gps"]["latitude"] == 13.0827
    assert parsed["gps"]["longitude"] == 80.2707
    assert parsed["battery"]["percentage"] == 92.0


@pytest.mark.parametrize("invalid_payload", [
    b"",
    b"not-json",
    b"x" * 5000,
    json.dumps([]).encode(),
    json.dumps({"flight_status": "STANDBY"}).encode(),
    json.dumps({"device_id": "esp32-drone", "sequence": "not-int", "timestamp_ms": 1, "flight_status": "OK"}).encode(),
    json.dumps({"device_id": "esp32-drone", "sequence": -1, "timestamp_ms": 1, "flight_status": "OK"}).encode(),
    json.dumps({"device_id": "esp32-drone", "sequence": 1, "timestamp_ms": -10, "flight_status": "OK"}).encode(),
    json.dumps({
        "device_id": "esp32-drone",
        "sequence": 1,
        "timestamp_ms": 100,
        "flight_status": "STANDBY",
        "orientation": {},
        "environment": {},
        "gps": {"latitude": 95.0, "longitude": 0.0, "altitude_m": 0.0},
        "battery": {},
    }).encode(),
    json.dumps({
        "device_id": "esp32-drone",
        "sequence": 1,
        "timestamp_ms": 100,
        "flight_status": "STANDBY",
        "orientation": {},
        "environment": {},
        "gps": {"latitude": 0.0, "longitude": -195.0, "altitude_m": 0.0},
        "battery": {},
    }).encode(),
])
def test_parse_drone_datagram_invalid_rejected(invalid_payload):
    with pytest.raises(ValueError):
        parse_drone_datagram(invalid_payload)


def test_is_newer_sequence_logic():
    assert is_newer_sequence(0, None) is True
    assert is_newer_sequence(1, 0) is True
    assert is_newer_sequence(10, 5) is True
    assert is_newer_sequence(5, 5) is False
    assert is_newer_sequence(4, 5) is False
    # 16-bit unsigned rollover
    assert is_newer_sequence(0, 65535) is True
    assert is_newer_sequence(10, 65530) is True
    assert is_newer_sequence(65530, 10) is False


def test_drone_protocol_receipt_and_duplicates():
    config = GatewayConfig(drone_offline_timeout_s=2.0)
    broadcaster = BroadcasterStub()
    lander_mgr = LanderManagerStub()
    protocol = DroneUDPProtocol(config, broadcaster, lander_manager=lander_mgr)

    pkt1 = json.dumps({
        "device_id": "esp32-drone",
        "sequence": 1,
        "timestamp_ms": 1000,
        "flight_status": "STANDBY",
        "orientation": {"roll": None, "pitch": None, "yaw": None},
        "environment": {"temperature_c": None, "pressure_hpa": None, "humidity_pct": None},
        "gps": {"latitude": 12.97, "longitude": 77.59, "altitude_m": 10.0},
        "battery": {"voltage_v": 12.0, "percentage": 90.0},
    }).encode("utf-8")

    protocol.datagram_received(pkt1, ("192.168.50.25", 5007))

    st = protocol.status()
    assert st["connection_state"] == "ONLINE"
    assert st["flight_status"] == "STANDBY"
    assert st["latitude"] == 12.97
    assert st["longitude"] == 77.59
    assert st["battery_percentage"] == 90.0
    assert protocol._last_seq == 1
    assert protocol._duplicate_count == 0

    # Duplicate sequence: should be dropped
    protocol.datagram_received(pkt1, ("192.168.50.25", 5007))
    assert protocol._duplicate_count == 1

    # Out-of-order sequence (older seq): should be dropped
    pkt_older = json.dumps({
        "device_id": "esp32-drone",
        "sequence": 0,
        "timestamp_ms": 900,
        "flight_status": "STANDBY",
        "orientation": {"roll": None, "pitch": None, "yaw": None},
        "environment": {"temperature_c": None, "pressure_hpa": None, "humidity_pct": None},
        "gps": {"latitude": None, "longitude": None, "altitude_m": None},
        "battery": {"voltage_v": None, "percentage": None},
    }).encode("utf-8")
    protocol.datagram_received(pkt_older, ("192.168.50.25", 5007))
    assert protocol._out_of_order_count == 1
    assert protocol._last_seq == 1


def test_drone_protocol_staleness_transition(monkeypatch):
    import gateway.drone_udp as drone_udp_module

    config = GatewayConfig(drone_offline_timeout_s=2.0)
    broadcaster = BroadcasterStub()
    protocol = DroneUDPProtocol(config, broadcaster)

    pkt = json.dumps({
        "device_id": "esp32-drone",
        "sequence": 1,
        "timestamp_ms": 1000,
        "flight_status": "STANDBY",
        "orientation": {"roll": None, "pitch": None, "yaw": None},
        "environment": {"temperature_c": None, "pressure_hpa": None, "humidity_pct": None},
        "gps": {"latitude": None, "longitude": None, "altitude_m": None},
        "battery": {"voltage_v": None, "percentage": None},
    }).encode("utf-8")

    protocol.datagram_received(pkt, ("127.0.0.1", 5007))
    assert protocol.status()["connection_state"] == "ONLINE"

    # Advance monotonic clock beyond timeout
    monkeypatch.setattr(drone_udp_module.time, "monotonic", lambda: protocol._last_seen_mono + 3.0)
    st = protocol.status()
    assert st["connection_state"] == "OFFLINE"
    assert st["flight_status"] is None
    assert st["latitude"] is None


@pytest.mark.anyio
async def test_drone_gateway_route_endpoints():
    config = GatewayConfig(
        lander_tcp_host="127.0.0.1",
        lander_tcp_port=0,
        drone_udp_host="127.0.0.1",
        drone_udp_port=0,
    )
    transport = LanderTCPTransport(config.lander_tcp_host, config.lander_tcp_port)
    app = create_gateway_app(config=config, transport=transport)

    drone_rcv = app.state.drone_receiver
    st = drone_rcv.protocol.status()
    assert st["connection_state"] == "OFFLINE"
    assert st["drone_id"] == "esp32-drone"
