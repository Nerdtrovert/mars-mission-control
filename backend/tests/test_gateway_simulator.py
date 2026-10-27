import json

from app.communication.gateway_contract import CommandName, CommandRequest
from app.communication.gateway_simulator import GatewaySimulator


def test_simulator_generates_only_supported_sensor_telemetry():
    simulator = GatewaySimulator()
    packet = json.loads(simulator.generate_telemetry_line())
    assert set(packet) == {
        "type", "timestamp_ms", "mode", "bmp_temperature_c", "pressure_hpa",
        "dht_temperature_c", "humidity_pct", "bmp280_ok", "dht11_ok",
    }
    assert packet["bmp280_ok"] and packet["dht11_ok"]
    old = packet["bmp_temperature_c"]
    simulator.advance_clock(3000)
    assert json.loads(simulator.generate_telemetry_line())["bmp_temperature_c"] != old


def test_sensor_failure_uses_null_and_matching_health_flag():
    simulator = GatewaySimulator()
    simulator.dht11_ok = False
    packet = json.loads(simulator.generate_telemetry_line())
    assert packet["dht_temperature_c"] is None and packet["humidity_pct"] is None
    assert packet["dht11_ok"] is False


def test_simulator_supports_status_and_mode_only():
    simulator = GatewaySimulator()
    response = simulator.handle_command(CommandRequest(command_id="1", command=CommandName.SET_STANDBY))
    assert response.accepted and simulator.mode.value == "STANDBY"
