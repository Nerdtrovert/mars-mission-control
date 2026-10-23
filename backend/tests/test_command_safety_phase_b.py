"""Phase B: Command Correlation, Request ID Mapping, and Safety Tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import pytest

from app.communication.gateway_client import GatewayClient
from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    ConnectionState,
    GateState,
)
from app.communication.gateway_simulator import GatewaySimulator
from app.communication.request_mapper import RequestIdMapper
from app.mission.command import (
    Command,
    CommandSafetyViolation,
    CommandStatus,
    CommandTracker,
    DuplicateCommandError,
)
from app.mission.state import MissionStateManager
from app.telemetry.service import TelemetryService


def test_uuid_to_integer_request_mapping():
    """Task 1: Verify allocation, bidirectional lookup, and lifecycle of request IDs."""
    mapper = RequestIdMapper(max_history=5)

    cmd_id_1 = "11111111-1111-1111-1111-111111111111"
    cmd_id_2 = "22222222-2222-2222-2222-222222222222"

    req_id_1 = mapper.allocate(cmd_id_1)
    req_id_2 = mapper.allocate(cmd_id_2)

    assert isinstance(req_id_1, int)
    assert isinstance(req_id_2, int)
    assert req_id_2 == req_id_1 + 1

    # Re-allocation returns identical mapped integer
    assert mapper.allocate(cmd_id_1) == req_id_1

    # Bidirectional lookups
    assert mapper.get_command_id(req_id_1) == cmd_id_1
    assert mapper.get_command_id(req_id_2) == cmd_id_2
    assert mapper.get_request_id(cmd_id_1) == req_id_1

    # Completion and eviction
    mapper.mark_completed(cmd_id_1)
    assert not mapper.is_active(cmd_id_1)


def test_concurrent_request_id_allocation():
    """Task 1: Verify thread-safe concurrent allocation of integer request IDs."""
    mapper = RequestIdMapper(max_history=500)
    uuids = [f"uuid-{i}" for i in range(100)]

    with ThreadPoolExecutor(max_workers=10) as executor:
        allocated = list(executor.map(mapper.allocate, uuids))

    # All allocated IDs must be unique
    assert len(allocated) == 100
    assert len(set(allocated)) == 100


def test_serial_boundary_rejects_string_request_id():
    """Task 1: The simulated firmware strictly rejects non-integer request IDs."""
    sim = GatewaySimulator()

    # ESP32 firmware protocol requires integer request_id
    bad_payload = {"command": "OPEN_GATE", "request_id": "not-an-int"}
    ack_bad = sim.handle_serial_payload(bad_payload)
    assert ack_bad["accepted"] is False
    assert ack_bad["reason"] == "INVALID_REQUEST"

    # Integer request_id is accepted
    good_payload = {"command": "OPEN_GATE", "request_id": 101}
    ack_good = sim.handle_serial_payload(good_payload)
    assert ack_good["accepted"] is True
    assert ack_good["request_id"] == 101


def test_duplicate_command_id_rejected():
    """Task 3: Prevent duplicate command IDs from creating a second command."""
    tracker = CommandTracker()
    cid = "duplicate-test-uuid"
    cmd1 = tracker.create_command(CommandName.GET_STATUS, command_id=cid)
    assert cmd1.command_id == cid

    # Submitting same ID again raises DuplicateCommandError
    with pytest.raises(DuplicateCommandError):
        tracker.create_command(CommandName.GET_STATUS, command_id=cid)


def test_missing_ack_followed_by_confirmed_endpoint_telemetry():
    """
    Task 2: If command acknowledgement is lost on the wire, but fresh telemetry
    subsequently confirms the requested endpoint, the command is safely reconciled.
    """
    state_mgr = MissionStateManager()
    telem_svc = TelemetryService(state_mgr)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    client = GatewayClient(state_mgr, telem_svc, tracker, sim)

    # Establish initial state
    client.refresh_device_status()
    assert state_mgr.snapshot()["gate_state"] == "CLOSED"

    # Simulate lost acknowledgement
    sim.drop_next_ack = True
    open_cmd = tracker.create_command(CommandName.OPEN_GATE)
    resp = client.dispatch_command(open_cmd)

    # Command is in SENT (unacknowledged), flagged with missing_ack
    assert open_cmd.status == CommandStatus.SENT
    assert open_cmd.missing_ack is True
    assert open_cmd.completed_at is None

    # Step physical movement on the lander
    sim.step_physical_movement()
    sim.step_physical_movement()
    sim.step_physical_movement()
    assert sim.gate_state == GateState.OPEN

    # Telemetry arrives confirming OPEN endpoint
    line = sim.generate_telemetry_line()
    client.ingest_telemetry_line(line)

    # Command must be reconciled to COMPLETED with diagnostic note
    assert open_cmd.status == CommandStatus.COMPLETED
    assert open_cmd.missing_ack is True
    assert "RECONCILED" in (open_cmd.reconciliation_note or "")
    assert open_cmd.completed_at is not None


def test_missing_ack_with_no_confirmed_endpoint():
    """
    Task 2 & 3: If ACK is lost and movement never completes, timeout occurs.
    Status query reconciliation verifies gate did not move and marks FAILED without blind retries.
    """
    state_mgr = MissionStateManager()
    telem_svc = TelemetryService(state_mgr)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    client = GatewayClient(state_mgr, telem_svc, tracker, sim)

    client.refresh_device_status()
    open_cmd = tracker.create_command(CommandName.OPEN_GATE)

    # Command sent, but lander did not move (e.g. wire disconnected)
    open_cmd.mark_sent()
    open_cmd.mark_timed_out("COMMAND_TIMED_OUT")

    assert open_cmd.status == CommandStatus.TIMED_OUT
    assert open_cmd.outcome_resolved is False  # Uncertain until reconciled

    # Reconcile via status query: lander is still CLOSED
    client.refresh_device_status()

    # Command is resolved as failed; no automatic retry was triggered
    assert open_cmd.status == CommandStatus.FAILED
    assert open_cmd.outcome_resolved is True
    assert "STILL_CLOSED" in (open_cmd.error_reason or "")


def test_out_of_order_telemetry_cannot_complete_command():
    """
    Task 2: Stale telemetry from before command dispatch cannot complete a command.
    """
    state_mgr = MissionStateManager()
    telem_svc = TelemetryService(state_mgr)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    client = GatewayClient(state_mgr, telem_svc, tracker, sim)

    # Ingest baseline telemetry at device timestamp 10,000 ms
    telem_svc.process_line(
        '{"type": "telemetry", "timestamp_ms": 10000, "mode": "ACTIVE", "gate_state": "CLOSED", '
        '"closed_limit": true, "open_limit": false, "bmp_temperature_c": 20.0, "pressure_hpa": 1010.0, '
        '"dht_temperature_c": 20.0, "humidity_pct": 50.0, "bmp280_ok": true, "dht11_ok": true, "fault": null}'
    )
    assert state_mgr.snapshot()["last_telemetry_timestamp_ms"] == 10000

    # Dispatch OPEN_GATE at 10,000 ms
    open_cmd = tracker.create_command(CommandName.OPEN_GATE)
    open_cmd.mark_sent(dispatched_at_ms=10000)

    # Simulated stale / out-of-order packet with timestamp 9,000 ms claiming OPEN
    stale_line = (
        '{"type": "telemetry", "timestamp_ms": 9000, "mode": "ACTIVE", "gate_state": "OPEN", '
        '"closed_limit": false, "open_limit": true, "bmp_temperature_c": 20.0, "pressure_hpa": 1010.0, '
        '"dht_temperature_c": 20.0, "humidity_pct": 50.0, "bmp280_ok": true, "dht11_ok": true, "fault": null}'
    )
    client.ingest_telemetry_line(stale_line)

    # State manager must ignore out-of-order telemetry
    assert state_mgr.snapshot()["gate_state"] == "CLOSED"
    assert state_mgr.snapshot()["last_telemetry_timestamp_ms"] == 10000

    # Command must NOT be completed by stale telemetry
    assert open_cmd.status == CommandStatus.SENT
    assert open_cmd.completed_at is None


def test_unrelated_endpoint_telemetry_cannot_complete_command():
    """
    Task 2: OPEN_GATE cannot be completed by CLOSED telemetry.
    """
    tracker = CommandTracker()
    cmd = tracker.create_command(CommandName.OPEN_GATE)
    cmd.mark_sent()
    cmd.mark_acknowledged(accepted=True)

    # Closed telemetry arrives
    tracker.reconcile_movement(endpoint_gate_state="CLOSED", open_limit=False, closed_limit=True)

    # OPEN_GATE is still in progress; NOT completed
    assert cmd.status == CommandStatus.ACKNOWLEDGED
    assert cmd.completed_at is None


def test_conflicting_movement_commands_blocked():
    """
    Task 3: Prevent conflicting movement commands while a previous movement
    command remains unresolved.
    """
    tracker = CommandTracker()
    cmd1 = tracker.create_command(CommandName.OPEN_GATE)
    cmd1.mark_sent()

    cmd2 = tracker.create_command(CommandName.CLOSE_GATE)

    # Attempting to dispatch cmd2 while cmd1 is unresolved must be rejected
    with pytest.raises(CommandSafetyViolation) as exc_info:
        tracker.validate_safety_preconditions(
            command=cmd2,
            gateway_state=ConnectionState.ONLINE,
            device_state=ConnectionState.ONLINE,
            gate_state=GateState.OPEN,
        )
    assert "unresolved" in str(exc_info.value)


def test_no_automatic_movement_retry_after_timeout():
    """
    Task 3: When a command times out, it is not retried automatically.
    Subsequent movement commands remain blocked until status reconciliation resolves the uncertainty.
    """
    tracker = CommandTracker()
    cmd1 = tracker.create_command(CommandName.OPEN_GATE)
    cmd1.mark_sent()
    cmd1.mark_timed_out("TIMEOUT")

    assert cmd1.status == CommandStatus.TIMED_OUT
    assert cmd1.outcome_resolved is False

    # Attempting another movement command before reconciliation is blocked
    cmd2 = tracker.create_command(CommandName.OPEN_GATE)
    with pytest.raises(CommandSafetyViolation) as exc_info:
        tracker.validate_safety_preconditions(
            command=cmd2,
            gateway_state=ConnectionState.ONLINE,
            device_state=ConnectionState.ONLINE,
            gate_state=GateState.CLOSED,
        )
    assert "Status reconciliation required" in str(exc_info.value)
