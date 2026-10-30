import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from gateway.config import GatewayConfig
from gateway.rover_udp import RoverUDPReceiver
from gateway.drone_udp import DroneUDPReceiver
from backend.app.communication.rover_runner import RoverRunner
from backend.app.communication.drone_runner import DroneRunner


@pytest.mark.anyio
async def test_rover_runner_forwards_udp_in_simulator_mode():
    received_packets = []

    class MockUDPProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            received_packets.append(data.decode("ascii"))

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        MockUDPProtocol,
        local_addr=("127.0.0.1", 0),
    )
    port = transport.get_extra_info("sockname")[1]

    published = []
    runner = RoverRunner(
        mode="simulator",
        http_url=f"http://127.0.0.1:{port}",
        publish=lambda status: published.append(status),
        interval_s=0.05,
        forward_udp=True,
        udp_host="127.0.0.1",
        udp_port=port,
    )

    await runner.start()
    await asyncio.sleep(0.15)
    await runner.stop()
    transport.close()

    assert len(published) > 0
    assert len(received_packets) > 0
    packet = received_packets[0]
    assert "DIST:" in packet
    assert "PITCH:" in packet
    assert "ROLL:" in packet
    assert "CMD:" in packet
    assert "MODE:" in packet


@pytest.mark.anyio
async def test_drone_runner_forwards_udp_in_simulator_mode():
    received_packets = []

    class MockUDPProtocol(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            received_packets.append(json.loads(data.decode("utf-8")))

    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        MockUDPProtocol,
        local_addr=("127.0.0.1", 0),
    )
    port = transport.get_extra_info("sockname")[1]

    published = []
    runner = DroneRunner(
        mode="simulator",
        http_url=f"http://127.0.0.1:{port}",
        publish=lambda status: published.append(status),
        interval_s=0.05,
        forward_udp=True,
        udp_host="127.0.0.1",
        udp_port=port,
    )

    await runner.start()
    await asyncio.sleep(0.15)
    await runner.stop()
    transport.close()

    assert len(published) > 0
    assert len(received_packets) > 0
    packet = received_packets[0]
    assert packet.get("device_id") == "esp32-drone"
    assert "flight_status" in packet
    assert "orientation" in packet
    assert "gps" in packet


@pytest.mark.anyio
async def test_gateway_rover_udp_internal_simulator():
    lander_mgr = MagicMock()
    lander_mgr.forward_rover_telemetry = AsyncMock(return_value=True)

    broadcaster = MagicMock()
    broadcaster.broadcast = AsyncMock()

    cfg = GatewayConfig(
        rover_udp_host="127.0.0.1",
        rover_udp_port=0,
        rover_simulator=True,
    )

    receiver = RoverUDPReceiver(config=cfg, broadcaster=broadcaster, lander_manager=lander_mgr)
    await receiver.start()
    await asyncio.sleep(0.7)
    await receiver.stop()

    assert lander_mgr.forward_rover_telemetry.await_count > 0
    args, kwargs = lander_mgr.forward_rover_telemetry.call_args
    assert "distance_cm" in args[0]
    assert "pitch_deg" in args[0]
    assert kwargs.get("online") is True

@pytest.mark.anyio
async def test_gateway_drone_udp_internal_simulator():
    lander_mgr = MagicMock()
    lander_mgr.forward_drone_telemetry = AsyncMock(return_value=True)

    broadcaster = MagicMock()
    broadcaster.broadcast = AsyncMock()

    cfg = GatewayConfig(
        drone_udp_host="127.0.0.1",
        drone_udp_port=0,
        drone_simulator=True,
    )

    receiver = DroneUDPReceiver(config=cfg, broadcaster=broadcaster, lander_manager=lander_mgr)
    await receiver.start()
    await asyncio.sleep(0.7)
    await receiver.stop()

    assert lander_mgr.forward_drone_telemetry.await_count > 0
    args, kwargs = lander_mgr.forward_drone_telemetry.call_args
    assert "flight_status" in args[0]
    assert "gps" in args[0]
    assert kwargs.get("online") is True
