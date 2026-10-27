"""Parser for the supported ESP32 lander telemetry protocol."""

import json
import math
from typing import Any


VALID_MODES = {"ACTIVE", "STANDBY"}
TELEMETRY_FIELDS = {
    "timestamp_ms",
    "mode",
    "bmp_temperature_c",
    "pressure_hpa",
    "dht_temperature_c",
    "humidity_pct",
    "bmp280_ok",
    "dht11_ok",
}


class TelemetryError(ValueError):
    """Raised when an incoming telemetry message is invalid."""


def parse_telemetry(line: str) -> dict[str, Any]:
    """Validate and return one JSON telemetry record."""
    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise TelemetryError("Invalid JSON") from exc
    if not isinstance(message, dict):
        raise TelemetryError("Message must be a JSON object")
    if {"gate_state", "closed_limit", "open_limit", "fault"} & message.keys():
        raise TelemetryError("Retired actuator fields are not part of the lander telemetry contract")
    if message.get("type") != "telemetry":
        raise TelemetryError("Message type is not telemetry")
    missing = TELEMETRY_FIELDS - message.keys()
    if missing:
        raise TelemetryError(f"Missing required fields: {', '.join(sorted(missing))}")
    extra = message.keys() - TELEMETRY_FIELDS - {"type"}
    if extra:
        raise TelemetryError(f"Unsupported telemetry fields: {', '.join(sorted(extra))}")
    if message["mode"] not in VALID_MODES:
        raise TelemetryError("Invalid mode")
    timestamp = message["timestamp_ms"]
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
        raise TelemetryError("timestamp_ms must be a non-negative integer")
    for field in ("bmp280_ok", "dht11_ok"):
        if not isinstance(message[field], bool):
            raise TelemetryError(f"{field} must be a boolean")
    for field in ("bmp_temperature_c", "pressure_hpa", "dht_temperature_c", "humidity_pct"):
        value = message[field]
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise TelemetryError(f"{field} must be a finite number or null")
    ranges = {
        "bmp_temperature_c": (-40.0, 85.0), "pressure_hpa": (300.0, 1100.0),
        "dht_temperature_c": (0.0, 50.0), "humidity_pct": (0.0, 100.0),
    }
    for field, (minimum, maximum) in ranges.items():
        value = message[field]
        if value is not None and not minimum <= value <= maximum:
            raise TelemetryError(f"{field} is outside the supported sensor range")
    return {"type": "telemetry", **{field: message[field] for field in TELEMETRY_FIELDS}}
