import json
from typing import Any


VALID_MODES = {"ACTIVE", "STANDBY"}

VALID_GATE_STATES = {
    "UNKNOWN",
    "CLOSED",
    "OPEN",
    "OPENING",
    "CLOSING",
    "FAULT",
}

TELEMETRY_FIELDS = {
    "timestamp_ms",
    "mode",
    "gate_state",
    "closed_limit",
    "open_limit",
    "bmp_temperature_c",
    "pressure_hpa",
    "dht_temperature_c",
    "humidity_pct",
    "bmp280_ok",
    "dht11_ok",
    "fault",
}


class TelemetryError(ValueError):
    """Raised when an incoming telemetry message is invalid."""


def parse_telemetry(line: str) -> dict[str, Any]:
    """Parse and validate one ESP32 telemetry JSON line."""

    try:
        message = json.loads(line)
    except json.JSONDecodeError as exc:
        raise TelemetryError("Invalid JSON") from exc

    if not isinstance(message, dict):
        raise TelemetryError("Message must be a JSON object")

    if message.get("type") != "telemetry":
        raise TelemetryError("Message type is not telemetry")

    missing = TELEMETRY_FIELDS - message.keys()
    if missing:
        raise TelemetryError(
            f"Missing required fields: {', '.join(sorted(missing))}"
        )

    if message["mode"] not in VALID_MODES:
        raise TelemetryError("Invalid mode")

    if message["gate_state"] not in VALID_GATE_STATES:
        raise TelemetryError("Invalid gate_state")

    if (
        isinstance(message["timestamp_ms"], bool)
        or not isinstance(message["timestamp_ms"], int)
        or message["timestamp_ms"] < 0
    ):
        raise TelemetryError("timestamp_ms must be a non-negative integer")

    for field in ("closed_limit", "open_limit", "bmp280_ok", "dht11_ok"):
        if not isinstance(message[field], bool):
            raise TelemetryError(f"{field} must be a boolean")

    numeric_fields = (
        "bmp_temperature_c",
        "pressure_hpa",
        "dht_temperature_c",
        "humidity_pct",
    )

    for field in numeric_fields:
        value = message[field]

        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise TelemetryError(f"{field} must be a number or null")

    if message["fault"] is not None and not isinstance(
        message["fault"], str
    ):
        raise TelemetryError("fault must be a string or null")

    # Return only the recognized protocol fields.
    return {
        "type": "telemetry",
        **{
            field: message[field]
            for field in TELEMETRY_FIELDS
        },
    }