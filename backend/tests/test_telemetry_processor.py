import json
import pytest

from app.telemetry.processor import TelemetryError, parse_telemetry


SAMPLE = {
    "type": "telemetry", "timestamp_ms": 100, "mode": "ACTIVE",
    "bmp_temperature_c": None, "pressure_hpa": None, "dht_temperature_c": None,
    "humidity_pct": None, "bmp280_ok": False, "dht11_ok": False,
}


def test_valid_sensor_packet_has_no_actuator_fields():
    packet = parse_telemetry(json.dumps(SAMPLE))
    assert packet["mode"] == "ACTIVE" and packet["bmp_temperature_c"] is None
    assert "gate_state" not in packet


@pytest.mark.parametrize("changes", [
    {"mode": "BROKEN"}, {"timestamp_ms": True}, {"bmp280_ok": "false"},
    {"pressure_hpa": float("nan")}, {"humidity_pct": -1}, {"gate_state": "OPEN"},
])
def test_invalid_sensor_packet_rejected(changes):
    with pytest.raises(TelemetryError):
        parse_telemetry(json.dumps({**SAMPLE, **changes}))


def test_missing_required_sensor_field_rejected():
    packet = {**SAMPLE}
    del packet["dht11_ok"]
    with pytest.raises(TelemetryError):
        parse_telemetry(json.dumps(packet))
