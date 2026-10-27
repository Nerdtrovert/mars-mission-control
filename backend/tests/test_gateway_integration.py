import json

from app.communication.gateway_client import GatewayClient
from app.communication.gateway_contract import CommandName
from app.communication.gateway_simulator import GatewaySimulator
from app.mission.command import CommandTracker
from app.mission.state import MissionStateManager
from app.storage.sqlite_storage import SQLiteStorage
from app.telemetry.service import TelemetryService


def test_simulated_lander_sensor_telemetry_flows_into_mission_state_and_history():
    state = MissionStateManager()
    storage = SQLiteStorage()
    service = TelemetryService(state, storage=storage)
    simulator = GatewaySimulator()
    state.update_gateway_health("ONLINE")
    state.update_device_health("ONLINE")
    client = GatewayClient(state, service, CommandTracker(storage), simulator=simulator)
    result = client.ingest_telemetry_line(simulator.generate_telemetry_line())
    assert result is not None
    assert state.snapshot()["mode"] == "ACTIVE"
    rows = storage.get_telemetry_history()
    assert len(rows) == 1 and rows[0]["bmp_temperature_c"] is not None
    assert "gate_state" not in rows[0]


def test_non_actuating_mode_command_reaches_simulator():
    state = MissionStateManager()
    state.update_gateway_health("ONLINE")
    state.update_device_health("ONLINE")
    simulator = GatewaySimulator()
    client = GatewayClient(state, TelemetryService(state), CommandTracker(), simulator=simulator)
    command = client.command_tracker.create_command(CommandName.SET_STANDBY)
    assert client.dispatch_command(command).accepted
    assert simulator.mode.value == "STANDBY"
