"""Pi UDP rover receiver parsing and stale-state tests."""

import pytest

from gateway.config import GatewayConfig
from gateway.main import create_gateway_app
from gateway.rover_udp import RoverUDPProtocol, RoverUDPReceiver, parse_rover_datagram
from gateway.transport import SimulatedSerialTransport


class BroadcasterStub:
    async def broadcast(self, message):
        return None


def test_parse_valid_rover_udp_packet():
    parsed = parse_rover_datagram(b"DIST:145,PITCH:2.5,ROLL:-1.0,CMD:F,MODE:M,VOLT:11.8")
    assert parsed == {
        "distance_cm": 145.0,
        "pitch_deg": 2.5,
        "roll_deg": -1.0,
        "command": "F",
        "mode": "M",
        "battery_voltage_v": 11.8,
    }


@pytest.mark.parametrize("packet", [
    b"garbage",
    b"DIST:12,PITCH:0,ROLL:0,CMD:X,MODE:M,VOLT:11.7",
    b"DIST:12,PITCH:0,ROLL:0,CMD:S,MODE:X,VOLT:11.7",
    b"DIST:12,PITCH:nope,ROLL:0,CMD:S,MODE:A,VOLT:11.7",
    b"DIST:12,PITCH:0,CMD:S,MODE:A,VOLT:11.7",
    b"DIST:NaN,PITCH:0,ROLL:0,CMD:S,MODE:A,VOLT:11.7",
])
def test_malformed_or_invalid_packet_rejected(packet):
    with pytest.raises(ValueError):
        parse_rover_datagram(packet)


def test_invalid_packet_does_not_overwrite_valid_state(monkeypatch):
    config = GatewayConfig(rover_offline_timeout_s=2.0)
    protocol = RoverUDPProtocol(config, BroadcasterStub())
    protocol.datagram_received(b"DIST:12,PITCH:0,ROLL:0,CMD:S,MODE:A,VOLT:11.7", ("127.0.0.1", 1))
    valid = protocol.status()
    protocol.datagram_received(b"DIST:broken", ("127.0.0.1", 1))
    assert protocol.status() == valid


def test_rover_status_transitions_offline_when_packet_is_stale(monkeypatch):
    import gateway.rover_udp as rover_udp

    config = GatewayConfig(rover_offline_timeout_s=2.0)
    protocol = RoverUDPProtocol(config, BroadcasterStub())
    protocol.datagram_received(b"DIST:12,PITCH:0,ROLL:0,CMD:S,MODE:A,VOLT:11.7", ("127.0.0.1", 1))
    monkeypatch.setattr(rover_udp.time, "monotonic", lambda: protocol._last_seen_mono + 3.0)
    status = protocol.status()
    assert status["connection_state"] == "OFFLINE"
    assert status["last_seen"] is not None
    assert status["distance_cm"] == 12.0


def test_gateway_rover_status_api_uses_udp_receiver_without_real_serial():
    import asyncio

    app = create_gateway_app(
        config=GatewayConfig(rover_udp_host="127.0.0.1", rover_udp_port=0),
        transport=SimulatedSerialTransport(),
    )
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/rover/status")
    status = asyncio.run(route.endpoint())
    assert status["rover_id"] == "mars-rover-01"
    assert status["connection_state"] == "OFFLINE"
    assert status["source"] == "network"


def test_gateway_status_api_returns_latest_valid_udp_sample_and_stales_it(monkeypatch):
    import asyncio
    import gateway.rover_udp as rover_udp

    app = create_gateway_app(
        config=GatewayConfig(rover_udp_host="127.0.0.1", rover_udp_port=5005, rover_offline_timeout_s=2.0),
        transport=SimulatedSerialTransport(),
    )
    receiver = app.state.rover_receiver
    route = next(route for route in app.routes if getattr(route, "path", None) == "/api/rover/status")
    receiver.protocol.datagram_received(
        b"DIST:12,PITCH:0.0,ROLL:0.5,CMD:S,MODE:A,VOLT:11.7",
        ("127.0.0.1", 5005),
    )
    online = asyncio.run(route.endpoint())
    assert online["connection_state"] == "ONLINE"
    assert online["distance_cm"] == 12.0
    assert online["mode"] == "A"
    assert online["battery_voltage_v"] == 11.7

    last_seen = receiver.protocol._last_seen_mono
    monkeypatch.setattr(rover_udp.time, "monotonic", lambda: last_seen + 3.0)
    offline = asyncio.run(route.endpoint())
    assert offline["connection_state"] == "OFFLINE"
    assert offline["distance_cm"] == 12.0  # retained as last-known, explicitly offline


@pytest.mark.anyio
async def test_gateway_lifespan_starts_rover_receiver_with_lander_gateway(monkeypatch):
    app = create_gateway_app(transport=SimulatedSerialTransport())
    started = {"lander": False, "rover": False}
    stopped = {"lander": False, "rover": False}

    async def start_lander():
        started["lander"] = True

    async def stop_lander():
        stopped["lander"] = True

    async def start_rover():
        started["rover"] = True

    async def stop_rover():
        stopped["rover"] = True

    monkeypatch.setattr(app.state.serial_manager, "start", start_lander)
    monkeypatch.setattr(app.state.serial_manager, "stop", stop_lander)
    monkeypatch.setattr(app.state.rover_receiver, "start", start_rover)
    monkeypatch.setattr(app.state.rover_receiver, "stop", stop_rover)

    async with app.router.lifespan_context(app):
        assert started == {"lander": True, "rover": True}
    assert stopped == {"lander": True, "rover": True}


@pytest.mark.anyio
async def test_receiver_binds_configured_udp_address_and_port(monkeypatch):
    import asyncio

    config = GatewayConfig(rover_udp_host="0.0.0.0", rover_udp_port=5005)
    receiver = RoverUDPReceiver(config, BroadcasterStub())
    bound = {}

    class FakeTransport:
        def close(self):
            return None

    async def fake_create_datagram_endpoint(protocol_factory, local_addr):
        bound["local_addr"] = local_addr
        return FakeTransport(), protocol_factory()

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "create_datagram_endpoint", fake_create_datagram_endpoint)
    await receiver.start()
    try:
        assert bound["local_addr"] == ("0.0.0.0", 5005)
    finally:
        await receiver.stop()
