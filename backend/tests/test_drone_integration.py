"""Tests for backend drone models, runner, and routes."""

from app.communication.drone_model import (
    DroneBattery,
    DroneEnvironment,
    DroneGPS,
    DroneOrientation,
    DroneStatus,
    DroneTelemetry,
    offline_drone_status,
)
from app.communication.drone_runner import DroneRunner


def test_drone_model_authoritative_contract_nulls():
    telem = DroneTelemetry(
        device_id="esp32-drone",
        sequence=1,
        timestamp_ms=123456,
        flight_status="STANDBY",
        orientation=DroneOrientation(roll=None, pitch=None, yaw=None),
        environment=DroneEnvironment(temperature_c=None, pressure_hpa=None, humidity_pct=None),
        gps=DroneGPS(latitude=None, longitude=None, altitude_m=None),
        battery=DroneBattery(voltage_v=None, percentage=None),
    )
    status = DroneStatus(
        drone_id="esp32-drone",
        flight_status="STANDBY",
        latitude=None,
        longitude=None,
        altitude_m=None,
        battery_percentage=None,
        connection_state="ONLINE",
        last_seen="2026-10-28T12:00:00Z",
        source="network",
        telemetry=telem,
    )
    dump = status.model_dump(mode="json")
    assert dump["drone_id"] == "esp32-drone"
    assert dump["flight_status"] == "STANDBY"
    assert dump["latitude"] is None
    assert dump["longitude"] is None
    assert dump["telemetry"]["gps"]["latitude"] is None
    assert dump["telemetry"]["battery"]["voltage_v"] is None


def test_offline_drone_status_helper():
    off = offline_drone_status(source="network")
    assert off.drone_id == "esp32-drone"
    assert off.connection_state.value == "OFFLINE"
    assert off.flight_status is None
    assert off.latitude is None
    assert off.longitude is None
    assert off.telemetry is None


def test_drone_runner_network_fallback_when_pi_offline():
    published = []
    runner = DroneRunner(
        mode="network",
        http_url="http://127.0.0.1:1",  # Guaranteed unreachable port
        publish=lambda s: published.append(s),
        interval_s=0.1,
    )
    status = runner._fetch_network_status()
    assert status.connection_state.value == "OFFLINE"
    assert status.source.value == "network"
    assert status.flight_status is None


def test_drone_runner_simulator_mode():
    published = []
    runner = DroneRunner(
        mode="simulator",
        http_url="",
        publish=lambda s: published.append(s),
        interval_s=0.1,
    )
    snap = runner.snapshot()
    assert snap.connection_state.value == "ONLINE"
    assert snap.source.value == "simulator"
    assert snap.flight_status in ("STANDBY", "TAKEOFF", "CRUISING", "HOVERING", "LANDING")
