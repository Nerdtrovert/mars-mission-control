"""Tests for Hardware-Free Gateway Simulator."""

import json
from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    ConnectionState,
    GateState,
    OperatingMode,
)
from app.communication.gateway_simulator import GatewaySimulator
from app.telemetry.processor import parse_telemetry


def test_simulator_operates_without_hardware():
    """Requirement 14: Simulator operates fully in-memory without physical hardware."""
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    assert sim.IS_SIMULATOR is True

    health = sim.get_health()
    assert health.status == "healthy"
    assert health.connection_state == ConnectionState.ONLINE
    assert health.device_connected is True

    status = sim.get_lander_status()
    assert status.gate_state == GateState.CLOSED
    assert status.closed_limit is True
    assert status.open_limit is False


def test_simulator_generates_valid_esp32_telemetry():
    """Requirement 3: Simulator generates telemetry that passes the telemetry processor parser."""
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    sim.advance_clock(1000)
    line = sim.generate_telemetry_line()

    parsed = parse_telemetry(line)
    assert parsed["type"] == "telemetry"
    assert parsed["timestamp_ms"] == 2000
    assert parsed["mode"] == "ACTIVE"
    assert parsed["gate_state"] == "CLOSED"
    assert parsed["closed_limit"] is True


def test_simulated_sensor_readings_vary_deterministically_within_plausible_ranges():
    sim = GatewaySimulator()
    sim.advance_clock(1000)
    first = parse_telemetry(sim.generate_telemetry_line())
    sim.advance_clock(1000)
    second = parse_telemetry(sim.generate_telemetry_line())

    assert first["bmp280_ok"] is True and first["dht11_ok"] is True
    assert first["bmp_temperature_c"] != second["bmp_temperature_c"]
    assert first["pressure_hpa"] != second["pressure_hpa"]
    assert first["dht_temperature_c"] != second["dht_temperature_c"]
    assert first["humidity_pct"] != second["humidity_pct"]
    for sample in (first, second):
        assert 20 <= sample["bmp_temperature_c"] <= 30
        assert 990 <= sample["pressure_hpa"] <= 1030
        assert 18 <= sample["dht_temperature_c"] <= 30
        assert 30 <= sample["humidity_pct"] <= 80


def test_simulator_unknown_initial_gate_state_does_not_assume_closed():
    sim = GatewaySimulator(initial_gate_state=None)
    status = sim.get_lander_status()

    assert status.gate_state == GateState.UNKNOWN
    assert status.closed_limit is False
    assert status.open_limit is False


def test_simulator_deterministic_movement_stepping():
    """Simulates physical gate movement deterministically without sleep calls."""
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)

    # Issue OPEN_GATE
    req = CommandRequest(command_id="cmd-1", command=CommandName.OPEN_GATE)
    ack = sim.handle_command(req)
    assert ack.accepted is True
    assert sim.gate_state == GateState.OPENING
    assert sim.closed_limit is False
    assert sim.open_limit is False

    # Step movement ticks deterministically
    sim.step_physical_movement()
    sim.step_physical_movement()
    assert sim.gate_state == GateState.OPENING

    # Final step reaches endpoint
    sim.step_physical_movement()
    assert sim.gate_state == GateState.OPEN
    assert sim.open_limit is True
    assert sim.closed_limit is False


def test_simulator_malformed_telemetry_mode():
    """Simulator can emit malformed lines to test error handling."""
    sim = GatewaySimulator()
    sim.malformed_telemetry = True
    line = sim.generate_telemetry_line()
    assert "MALFORMED" in line
