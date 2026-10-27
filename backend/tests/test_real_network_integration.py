from app.communication.gateway_contract import LanderStatusResponse, ConnectionState, OperatingMode
from app.communication.rover_model import RoverStatus
from app.communication.rover_runner import RoverRunner


def test_separate_lander_and_rover_network_contracts():
    lander = LanderStatusResponse(
        gateway_state=ConnectionState.ONLINE, device_state=ConnectionState.ONLINE,
        mode=OperatingMode.ACTIVE, bmp280_ok=True, dht11_ok=True,
    )
    rover = RoverStatus(
        distance_cm=145, pitch_deg=12.4, roll_deg=-3.2, command="F", mode="M",
        connection_state="ONLINE", source="network",
    )
    assert lander.mode == OperatingMode.ACTIVE
    assert rover.distance_cm == 145
    assert "battery_voltage_v" not in rover.model_dump()
    assert "gate_state" not in lander.model_dump()


def test_unavailable_pi_returns_offline_rover_snapshot():
    runner = RoverRunner("network", "http://127.0.0.1:1", lambda status: None)
    status = runner._fetch_network_status()
    assert status.connection_state.value == "OFFLINE"
    assert status.source.value == "network"
