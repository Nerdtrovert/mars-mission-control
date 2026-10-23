import json

from app.mission.state import MissionStateManager
from app.telemetry.service import TelemetryService


def test_telemetry_updates_mission_state():
    state_manager = MissionStateManager()
    service = TelemetryService(state_manager)

    message = {
        "type": "telemetry",
        "timestamp_ms": 17140,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": 24.5,
        "pressure_hpa": 1008.2,
        "dht_temperature_c": 25.0,
        "humidity_pct": 60.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    }

    result = service.process_line(json.dumps(message))

    assert result["telemetry"]["timestamp_ms"] == 17140
    assert "received_at" in result["telemetry"]
    assert result["mission_state"]["gate_state"] == "CLOSED"
    assert result["mission_state"]["closed_limit"] is True
    assert result["mission_state"]["open_limit"] is False
    assert result["mission_state"]["fault"] is None
    assert result["mission_state"]["last_telemetry_at"] is not None


def test_telemetry_service_attaches_host_received_at_timestamp():
    state_manager = MissionStateManager()
    service = TelemetryService(state_manager)

    callback_telemetry = None
    def listener(telem: dict, state: dict) -> None:
        nonlocal callback_telemetry
        callback_telemetry = telem

    service.set_telemetry_listener(listener)

    message = {
        "type": "telemetry",
        "timestamp_ms": 25000,
        "mode": "ACTIVE",
        "gate_state": "OPEN",
        "closed_limit": False,
        "open_limit": True,
        "bmp_temperature_c": 21.0,
        "pressure_hpa": 1010.0,
        "dht_temperature_c": 22.0,
        "humidity_pct": 50.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    }

    custom_ts = "2026-10-22T12:30:00+00:00"
    result = service.process_line(json.dumps(message), timestamp=custom_ts)

    assert result["telemetry"]["received_at"] == custom_ts
    assert callback_telemetry is not None
    assert callback_telemetry["received_at"] == custom_ts


def test_host_receipt_order_remains_increasing_when_device_uptime_reboots():
    state_manager = MissionStateManager()
    service = TelemetryService(state_manager)
    base = {
        "type": "telemetry",
        "mode": "ACTIVE",
        "gate_state": "UNKNOWN",
        "closed_limit": False,
        "open_limit": False,
        "bmp_temperature_c": None,
        "pressure_hpa": None,
        "dht_temperature_c": 22.0,
        "humidity_pct": 50.0,
        "bmp280_ok": False,
        "dht11_ok": True,
        "fault": None,
    }

    before_reboot = service.process_line(
        json.dumps({**base, "timestamp_ms": 10_000}),
        timestamp="2026-10-23T10:00:00+00:00",
    )
    after_reboot = service.process_line(
        json.dumps({**base, "timestamp_ms": 500}),
        timestamp="2026-10-23T10:00:01+00:00",
    )

    assert before_reboot["telemetry"]["timestamp_ms"] == 10_000
    assert after_reboot["telemetry"]["timestamp_ms"] == 500
    assert before_reboot["telemetry"]["received_at"] == "2026-10-23T10:00:00+00:00"
    assert after_reboot["telemetry"]["received_at"] == "2026-10-23T10:00:01+00:00"
    assert after_reboot["mission_state"]["last_telemetry_timestamp_ms"] == 500


def test_invalid_telemetry_does_not_update_state():
    state_manager = MissionStateManager()
    service = TelemetryService(state_manager)

    before = state_manager.snapshot()

    try:
        service.process_line("not JSON")
        assert False, "Expected invalid telemetry to raise an exception"
    except ValueError:
        pass

    after = state_manager.snapshot()

    assert after == before
