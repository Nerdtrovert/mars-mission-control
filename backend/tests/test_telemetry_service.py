import json

from app.mission.state import MissionStateManager
from app.telemetry.service import TelemetryService


def packet(timestamp=100):
    return {
        "type": "telemetry", "timestamp_ms": timestamp, "mode": "ACTIVE",
        "bmp_temperature_c": 24.5, "pressure_hpa": 1008.2,
        "dht_temperature_c": 25.0, "humidity_pct": 60.0,
        "bmp280_ok": True, "dht11_ok": True,
    }


def test_telemetry_updates_mode_sensor_health_and_receipt_timestamp():
    manager = MissionStateManager()
    service = TelemetryService(manager)
    result = service.process_line(json.dumps(packet()), timestamp="2026-10-22T12:30:00+00:00")
    assert result["mission_state"]["mode"] == "ACTIVE"
    assert result["mission_state"]["bmp280_ok"] is True
    assert result["telemetry"]["received_at"] == "2026-10-22T12:30:00+00:00"
    assert "gate_state" not in result["mission_state"]


def test_rebooted_device_uptime_does_not_break_receipt_order():
    manager = MissionStateManager()
    service = TelemetryService(manager)
    first = service.process_line(json.dumps(packet(10000)), timestamp="2026-10-23T10:00:00+00:00")
    second = service.process_line(json.dumps(packet(500)), timestamp="2026-10-23T10:00:01+00:00")
    assert first["telemetry"]["received_at"] < second["telemetry"]["received_at"]
    assert second["mission_state"]["last_telemetry_timestamp_ms"] == 500
