import json
import pytest

from app.telemetry.processor import (
    TelemetryError,
    parse_telemetry,
)


SAMPLE_TELEMETRY = {
    "type": "telemetry",
    "timestamp_ms": 17140,
    "mode": "ACTIVE",
    "gate_state": "UNKNOWN",
    "closed_limit": False,
    "open_limit": False,
    "bmp_temperature_c": None,
    "pressure_hpa": None,
    "dht_temperature_c": None,
    "humidity_pct": None,
    "bmp280_ok": False,
    "dht11_ok": False,
    "fault": None,
}


def test_valid_telemetry():
    result = parse_telemetry(json.dumps(SAMPLE_TELEMETRY))

    assert result["type"] == "telemetry"
    assert result["mode"] == "ACTIVE"
    assert result["gate_state"] == "UNKNOWN"
    assert result["bmp_temperature_c"] is None


def test_valid_numeric_sensor_readings():
    message = SAMPLE_TELEMETRY.copy()
    message.update({
        "bmp_temperature_c": 24.5,
        "pressure_hpa": 1008.2,
        "dht_temperature_c": 25.0,
        "humidity_pct": 60.0,
        "bmp280_ok": True,
        "dht11_ok": True,
    })

    result = parse_telemetry(json.dumps(message))

    assert result["bmp_temperature_c"] == 24.5
    assert result["humidity_pct"] == 60.0


def test_invalid_json():
    with pytest.raises(TelemetryError):
        parse_telemetry("this is not JSON")


def test_rejects_non_telemetry_message():
    message = SAMPLE_TELEMETRY.copy()
    message["type"] = "command_ack"

    with pytest.raises(TelemetryError):
        parse_telemetry(json.dumps(message))


def test_rejects_missing_fields():
    message = SAMPLE_TELEMETRY.copy()
    del message["gate_state"]

    with pytest.raises(TelemetryError):
        parse_telemetry(json.dumps(message))


def test_rejects_invalid_gate_state():
    message = SAMPLE_TELEMETRY.copy()
    message["gate_state"] = "FLYING"

    with pytest.raises(TelemetryError):
        parse_telemetry(json.dumps(message))


def test_rejects_invalid_boolean():
    message = SAMPLE_TELEMETRY.copy()
    message["closed_limit"] = "false"

    with pytest.raises(TelemetryError):
        parse_telemetry(json.dumps(message))