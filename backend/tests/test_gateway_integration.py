"""Integration tests for GatewayClient, Simulator, and MissionStateManager."""

from app.api.routes import get_mission_state, list_commands, submit_command, CommandSubmissionRequest
from app.communication.gateway_client import GatewayClient
from app.communication.gateway_contract import CommandName, GateState
from app.communication.gateway_simulator import GatewaySimulator
from app.mission.command import CommandStatus, CommandTracker
from app.mission.state import MissionStateManager
from app.telemetry.service import TelemetryService


def test_telemetry_propagation_and_command_completion_e2e():
    """Requirements 3 & 7: End-to-end telemetry propagation and limit switch completion."""
    manager = MissionStateManager()
    telemetry_service = TelemetryService(manager)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)

    client = GatewayClient(
        state_manager=manager,
        telemetry_service=telemetry_service,
        command_tracker=tracker,
        simulator=sim,
    )

    # 1. Establish initial status
    client.refresh_device_status()
    state = manager.snapshot()
    assert state["gateway_state"] == "ONLINE"
    assert state["device_state"] == "ONLINE"
    assert state["gate_state"] == "CLOSED"

    # 2. Dispatch OPEN_GATE command
    cmd = tracker.create_command(CommandName.OPEN_GATE)
    ack = client.dispatch_command(cmd)
    assert ack.accepted is True
    assert cmd.status == CommandStatus.ACKNOWLEDGED
    assert cmd.completed_at is None  # Movement still in progress

    # 3. Simulate movement steps and telemetry ingestion
    sim.step_physical_movement()
    line1 = sim.generate_telemetry_line()
    client.ingest_telemetry_line(line1)
    assert manager.snapshot()["gate_state"] == "OPENING"
    assert cmd.status == CommandStatus.ACKNOWLEDGED

    # Step until fully open
    sim.step_physical_movement()
    sim.step_physical_movement()
    line_final = sim.generate_telemetry_line()
    client.ingest_telemetry_line(line_final)

    # State confirmed OPEN by limit switch; command marks completed
    assert manager.snapshot()["gate_state"] == "OPEN"
    assert manager.snapshot()["open_limit"] is True
    assert cmd.status == CommandStatus.COMPLETED
    assert cmd.completed_at is not None


def test_invalid_telemetry_rejection_no_state_corruption():
    """Requirement 4: Invalid telemetry lines are safely rejected without crashing or corrupting state."""
    manager = MissionStateManager()
    telemetry_service = TelemetryService(manager)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)

    client = GatewayClient(
        state_manager=manager,
        telemetry_service=telemetry_service,
        command_tracker=tracker,
        simulator=sim,
    )

    # Ingest valid telemetry first
    valid_line = sim.generate_telemetry_line()
    client.ingest_telemetry_line(valid_line)
    before_state = manager.snapshot()
    assert before_state["gate_state"] == "CLOSED"

    # Ingest malformed non-JSON
    result1 = client.ingest_telemetry_line("GARBAGE_NOT_JSON")
    assert result1 is None
    assert manager.snapshot()["gate_state"] == "CLOSED"

    # Ingest JSON missing required protocol fields
    result2 = client.ingest_telemetry_line('{"type": "telemetry", "mode": "ACTIVE"}')
    assert result2 is None
    assert manager.snapshot()["gate_state"] == "CLOSED"


def test_routes_endpoints_execution():
    """Test API route handlers directly."""
    state = get_mission_state()
    assert "gate_state" in state
    assert "gateway_state" in state
    assert "device_state" in state

    # List commands
    cmds = list_commands()
    assert isinstance(cmds, list)
