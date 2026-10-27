from app.mission.state import MissionStateManager


def test_initial_state_contains_connectivity_mode_and_sensor_health_only():
    state = MissionStateManager().snapshot()
    assert state["mode"] == "UNKNOWN"
    assert state["gateway_state"] == "NOT_CONNECTED"
    assert state["device_state"] == "NOT_CONNECTED"
    assert state["bmp280_ok"] is None and state["dht11_ok"] is None
    assert not {"gate_state", "closed_limit", "open_limit", "fault"} & state.keys()


def test_disconnect_marks_device_offline_without_actuator_state():
    manager = MissionStateManager()
    manager.update_gateway_health("ONLINE")
    manager.update_device_health("ONLINE")
    manager.update_device_health("OFFLINE")
    state = manager.snapshot()
    assert state["device_state"] == "OFFLINE"
    assert "gate_state" not in state
