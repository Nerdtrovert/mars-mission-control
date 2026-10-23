"""Tests for Command Lifecycle, Acknowledgement vs Completion, and Safety Constraints."""

import pytest
from app.communication.gateway_contract import (
    CommandName,
    ConnectionState,
    GateState,
)
from app.mission.command import (
    Command,
    CommandSafetyViolation,
    CommandStatus,
    CommandTracker,
    DuplicateCommandError,
    InvalidStateTransitionError,
)


def test_command_lifecycle_transitions():
    """Verify standard CREATED -> SENT -> ACKNOWLEDGED -> COMPLETED transition."""
    cmd = Command(name=CommandName.GET_STATUS)
    assert cmd.status == CommandStatus.CREATED

    cmd.mark_sent()
    assert cmd.status == CommandStatus.SENT

    cmd.mark_acknowledged(accepted=True)
    assert cmd.status == CommandStatus.ACKNOWLEDGED
    assert cmd.acknowledged_at is not None

    cmd.mark_completed()
    assert cmd.status == CommandStatus.COMPLETED
    assert cmd.completed_at is not None


def test_command_rejection_transition():
    """Verify transition to REJECTED when accepted is False."""
    cmd = Command(name=CommandName.OPEN_GATE)
    cmd.mark_sent()
    cmd.mark_acknowledged(accepted=False, reason="GATE_BUSY")

    assert cmd.status == CommandStatus.REJECTED
    assert cmd.error_reason == "GATE_BUSY"

    # Cannot complete a rejected command
    with pytest.raises(InvalidStateTransitionError):
        cmd.mark_completed()


def test_command_acknowledgement_vs_physical_completion():
    """
    Requirement 7: A command acknowledgement confirms only that the device
    accepted the command, NOT that physical movement has finished.
    """
    cmd = Command(name=CommandName.OPEN_GATE)
    cmd.mark_sent()

    # Device acknowledges receipt and validation of OPEN_GATE
    cmd.mark_acknowledged(accepted=True)
    assert cmd.status == CommandStatus.ACKNOWLEDGED
    # At this point, the command is NOT completed; servos are still in motion!
    assert cmd.completed_at is None
    assert cmd.status != CommandStatus.COMPLETED

    # Only when physical limit switch triggers destination is completion marked
    cmd.mark_completed()
    assert cmd.status == CommandStatus.COMPLETED
    assert cmd.completed_at is not None


def test_safety_rejects_movement_when_device_offline():
    """Movement command rejected if device is not ONLINE."""
    tracker = CommandTracker()
    cmd = tracker.create_command(CommandName.OPEN_GATE)

    with pytest.raises(CommandSafetyViolation) as exc_info:
        tracker.validate_safety_preconditions(
            command=cmd,
            gateway_state=ConnectionState.ONLINE,
            device_state=ConnectionState.OFFLINE,
            gate_state=GateState.CLOSED,
        )
    assert "Device is OFFLINE" in str(exc_info.value)


def test_safety_rejects_movement_when_gate_state_unknown():
    """Movement command rejected if physical gate state is UNKNOWN."""
    tracker = CommandTracker()
    cmd = tracker.create_command(CommandName.OPEN_GATE)

    with pytest.raises(CommandSafetyViolation) as exc_info:
        tracker.validate_safety_preconditions(
            command=cmd,
            gateway_state=ConnectionState.ONLINE,
            device_state=ConnectionState.ONLINE,
            gate_state=GateState.UNKNOWN,
        )
    assert "Physical gate state is UNKNOWN" in str(exc_info.value)


def test_safety_rejects_movement_when_in_fault():
    """Movement command rejected if physical gate is in FAULT."""
    tracker = CommandTracker()
    cmd = tracker.create_command(CommandName.CLOSE_GATE)

    with pytest.raises(CommandSafetyViolation) as exc_info:
        tracker.validate_safety_preconditions(
            command=cmd,
            gateway_state=ConnectionState.ONLINE,
            device_state=ConnectionState.ONLINE,
            gate_state=GateState.FAULT,
        )
    assert "FAULT" in str(exc_info.value)


def test_no_duplicate_command_submission_after_timeout():
    """
    Requirement 13: Duplicate command submission with the same ID
    or redundant movement after timeout is strictly prevented.
    """
    tracker = CommandTracker()
    cmd1 = tracker.create_command(CommandName.OPEN_GATE, command_id="test-cmd-001")
    cmd1.mark_sent()
    cmd1.mark_timed_out("SIMULATED_TIMEOUT")

    assert cmd1.status == CommandStatus.TIMED_OUT

    # Attempting to re-submit with the exact same ID must be rejected
    with pytest.raises(DuplicateCommandError):
        tracker.create_command(CommandName.OPEN_GATE, command_id="test-cmd-001")
