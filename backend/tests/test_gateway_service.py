import json

from gateway.config import GatewayConfig
from gateway.rover_udp import parse_rover_datagram
from app.communication.gateway_contract import CommandName, CommandRequest, ConnectionState
from app.communication.rover_model import RoverStatus
from gateway.lander_manager import LanderManager


def test_gateway_lander_cache_parses_sensor_telemetry_without_actuator_state():
    config = GatewayConfig()
    from gateway.tcp_transport import LanderTCPTransport
    manager = LanderManager(config, LanderTCPTransport("127.0.0.1", 0))
    manager._device_state = ConnectionState.ONLINE
    manager._update_from_telemetry({
        "timestamp_ms": 25, "mode": "ACTIVE", "bmp280_ok": True, "dht11_ok": True,
    })
    status = manager.get_lander_status().model_dump(mode="json")
    assert status["timestamp_ms"] == 25 and status["bmp280_ok"] is True
    assert "gate_state" not in status and "fault" not in status


def test_udp_and_lander_protocols_remain_separate():
    rover = parse_rover_datagram(b"DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M")
    assert rover == {"distance_cm": 145, "pitch_deg": 12.4, "roll_deg": -3.2, "command": "F", "mode": "M"}
    assert RoverStatus.model_validate({**rover, "source": "network"}).connection_state.value == "OFFLINE"
    request = CommandRequest(command_id="s", command=CommandName.GET_STATUS)
    assert request.command.value == "GET_STATUS"
