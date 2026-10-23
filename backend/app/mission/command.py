"""Mission Command Model and Lifecycle Management.

Defines the stateful command model, lifecycle state transitions,
safety verification rules, and duplicate suppression logic for Mars Mission Control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from threading import RLock
from typing import Any, Optional, TYPE_CHECKING
import uuid

logger = logging.getLogger(__name__)

from app.communication.gateway_contract import CommandName, ConnectionState, GateState

if TYPE_CHECKING:
    from app.storage.sqlite_storage import SQLiteStorage


class CommandStatus(str, Enum):
    """Lifecycle status of a dispatched or queued command."""
    CREATED = "CREATED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    UNKNOWN = "UNKNOWN"


class CommandAvailability(str, Enum):
    """Implementation readiness classification for commands."""
    SUPPORTED = "SUPPORTED"
    PLANNED = "PLANNED"
    UNAVAILABLE = "UNAVAILABLE"


# Registry of command capabilities
COMMAND_CAPABILITIES: dict[CommandName, CommandAvailability] = {
    CommandName.GET_STATUS: CommandAvailability.SUPPORTED,
    CommandName.SET_ACTIVE: CommandAvailability.SUPPORTED,
    CommandName.SET_STANDBY: CommandAvailability.SUPPORTED,
    CommandName.OPEN_GATE: CommandAvailability.SUPPORTED,
    CommandName.CLOSE_GATE: CommandAvailability.SUPPORTED,
}

MOVEMENT_COMMANDS = {CommandName.OPEN_GATE, CommandName.CLOSE_GATE}


class CommandError(Exception):
    """Base exception for command validation or transition errors."""


class CommandSafetyViolation(CommandError):
    """Raised when a command violates physical safety or connectivity rules."""


class DuplicateCommandError(CommandError):
    """Raised when attempting to submit a duplicate command."""


class InvalidStateTransitionError(CommandError):
    """Raised when a command lifecycle transition is illegal."""


@dataclass
class Command:
    """Represents a mission command and its full lifecycle history."""
    name: CommandName
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: CommandStatus = CommandStatus.CREATED
    acknowledged_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_reason: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    missing_ack: bool = False
    reconciliation_note: Optional[str] = None
    dispatched_at_ms: Optional[int] = None
    outcome_resolved: bool = False

    def mark_sent(self, dispatched_at_ms: Optional[int] = None) -> None:
        """Transition CREATED -> SENT upon transmission."""
        if self.status != CommandStatus.CREATED:
            raise InvalidStateTransitionError(
                f"Cannot transition to SENT from {self.status.value}"
            )
        self.status = CommandStatus.SENT
        self.dispatched_at_ms = dispatched_at_ms

    def mark_acknowledged(self, accepted: bool, reason: Optional[str] = None) -> None:
        """
        Record gateway or device acknowledgement.
        Note: An acknowledgement indicates acceptance to execute, NOT physical completion.
        """
        if self.status != CommandStatus.SENT:
            raise InvalidStateTransitionError(
                f"Cannot acknowledge command in state {self.status.value}"
            )

        now = datetime.now(timezone.utc).isoformat()
        self.acknowledged_at = now
        if accepted:
            self.status = CommandStatus.ACKNOWLEDGED
        else:
            self.status = CommandStatus.REJECTED
            self.error_reason = reason or "REJECTED_BY_DEVICE"
            self.outcome_resolved = True

    def mark_completed(self) -> None:
        """
        Transition ACKNOWLEDGED -> COMPLETED.
        For movement commands, this must ONLY be called when physical limit switches
        have confirmed the destination endpoint.
        """
        if self.status != CommandStatus.ACKNOWLEDGED:
            raise InvalidStateTransitionError(
                f"Cannot complete command in state {self.status.value}"
            )
        self.status = CommandStatus.COMPLETED
        self.outcome_resolved = True
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, reason: str) -> None:
        """Transition ACKNOWLEDGED, SENT, or TIMED_OUT -> FAILED."""
        if self.status not in (CommandStatus.SENT, CommandStatus.ACKNOWLEDGED, CommandStatus.TIMED_OUT):
            raise InvalidStateTransitionError(
                f"Cannot mark failed from state {self.status.value}"
            )
        self.status = CommandStatus.FAILED
        self.error_reason = reason
        self.outcome_resolved = True
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def mark_timed_out(self, reason: str = "COMMAND_TIMEOUT") -> None:
        """Transition SENT or ACKNOWLEDGED -> TIMED_OUT."""
        if self.status not in (CommandStatus.SENT, CommandStatus.ACKNOWLEDGED):
            raise InvalidStateTransitionError(
                f"Cannot time out command in state {self.status.value}"
            )
        self.status = CommandStatus.TIMED_OUT
        self.error_reason = reason
        # Non-movement commands resolve immediately on timeout;
        # movement commands remain outcome_resolved = False until reconciled with physical state
        self.outcome_resolved = (self.name not in MOVEMENT_COMMANDS)
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def reconcile_with_telemetry(self, endpoint_confirmed: bool, note: str) -> None:
        """
        Reconcile a command whose outcome was uncertain or whose ACK was lost,
        when fresh telemetry confirms the requested endpoint.
        """
        if not endpoint_confirmed:
            return
        if self.status == CommandStatus.COMPLETED:
            return
        if self.status not in (CommandStatus.SENT, CommandStatus.ACKNOWLEDGED, CommandStatus.TIMED_OUT):
            raise InvalidStateTransitionError(
                f"Cannot reconcile command in state {self.status.value}"
            )
        if self.status in (CommandStatus.SENT, CommandStatus.TIMED_OUT):
            self.missing_ack = True
        self.status = CommandStatus.COMPLETED
        self.reconciliation_note = note
        self.outcome_resolved = True
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def resolve_timeout_as_failed(self, reason: str) -> None:
        """Mark a timed-out movement command as failed after status reconciliation confirms no move."""
        if self.status == CommandStatus.TIMED_OUT:
            self.status = CommandStatus.FAILED
            self.error_reason = reason
            self.outcome_resolved = True

    def to_dict(self) -> dict[str, Any]:
        """Convert command state to a dictionary representation."""
        return {
            "command_id": self.command_id,
            "name": self.name.value,
            "created_at": self.created_at,
            "status": self.status.value,
            "acknowledged_at": self.acknowledged_at,
            "completed_at": self.completed_at,
            "error_reason": self.error_reason,
            "params": self.params,
            "missing_ack": self.missing_ack,
            "reconciliation_note": self.reconciliation_note,
            "dispatched_at_ms": self.dispatched_at_ms,
            "outcome_resolved": self.outcome_resolved,
        }


class CommandTracker:
    """
    Tracks command history, enforces idempotency, prevents duplicate execution,
    and enforces pre-dispatch physical safety invariants.
    """

    def __init__(self, storage: Optional[SQLiteStorage] = None) -> None:
        self.storage = storage
        self._lock = RLock()
        self._commands: dict[str, Command] = {}

    def save_command_state(self, cmd: Command) -> None:
        """Persist latest command status to storage if configured."""
        if self.storage is not None:
            try:
                self.storage.save_command(cmd.to_dict())
            except Exception as e:
                logger.error(f"Failed to persist command {cmd.command_id}: {e}")

    def clear(self) -> None:
        """Clear in-memory command tracking."""
        with self._lock:
            self._commands.clear()

    def load_history_from_storage(self) -> None:
        """
        Restore historical commands from SQLite for display and diagnostics.
        SAFETY INVARIANT: Never redispatches pending or unresolved commands!
        """
        if self.storage is None:
            return
        records = self.storage.list_commands(limit=500)
        records.sort(key=lambda r: r.get("created_at", ""))
        with self._lock:
            for r in records:
                cid = r["command_id"]
                if cid in self._commands:
                    continue
                name_enum = CommandName(r["name"])
                status_enum = CommandStatus(r["status"])
                cmd = Command(
                    name=name_enum,
                    command_id=cid,
                    created_at=r["created_at"],
                    status=status_enum,
                    acknowledged_at=r.get("acknowledged_at"),
                    completed_at=r.get("completed_at"),
                    error_reason=r.get("error_reason"),
                    params=r.get("params"),
                    missing_ack=bool(r.get("missing_ack")),
                    reconciliation_note=r.get("reconciliation_note"),
                    dispatched_at_ms=r.get("dispatched_at_ms"),
                    outcome_resolved=bool(r.get("outcome_resolved")),
                )
                self._commands[cid] = cmd

    def create_command(
        self,
        name: CommandName,
        command_id: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Command:
        """Create and register a new command with duplicate ID suppression."""
        cid = command_id or str(uuid.uuid4())
        with self._lock:
            if cid in self._commands:
                existing = self._commands[cid]
                if not existing.outcome_resolved:
                    raise DuplicateCommandError(f"Command with ID {cid} is already pending or active")
                raise DuplicateCommandError(f"Command with ID {cid} has already been executed")

            cmd = Command(name=name, command_id=cid, params=params)
            self._commands[cid] = cmd
        self.save_command_state(cmd)
        return cmd

    def get_command(self, command_id: str) -> Optional[Command]:
        """Retrieve a command by ID."""
        with self._lock:
            return self._commands.get(command_id)

    def list_commands(self) -> list[Command]:
        """Return all tracked commands ordered by creation."""
        with self._lock:
            return list(self._commands.values())

    def get_unresolved_movement_command(self) -> Optional[Command]:
        """Return any active or uncertain movement command."""
        with self._lock:
            for cmd in self._commands.values():
                if cmd.name in MOVEMENT_COMMANDS and not cmd.outcome_resolved:
                    return cmd
            return None

    def reconcile_movement(
        self,
        endpoint_gate_state: str,
        open_limit: bool,
        closed_limit: bool,
        telemetry_timestamp_ms: Optional[int] = None,
    ) -> list[Command]:
        """
        Reconcile in-flight or timed-out movement commands against confirmed limit switch telemetry.
        Stale telemetry or unrelated transitions cannot complete commands.
        """
        reconciled = []
        with self._lock:
            for cmd in self._commands.values():
                if cmd.name not in MOVEMENT_COMMANDS or cmd.outcome_resolved:
                    continue

                # Stale check: telemetry timestamp must not precede command dispatch
                if (
                    telemetry_timestamp_ms is not None
                    and cmd.dispatched_at_ms is not None
                    and telemetry_timestamp_ms < cmd.dispatched_at_ms
                ):
                    # Check if ESP32 rebooted during movement execution
                    if (cmd.dispatched_at_ms - telemetry_timestamp_ms) > 2000:
                        cmd.mark_failed("DEVICE_REBOOTED_DURING_EXECUTION")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)
                    continue

                # OPEN_GATE requires gate_state == OPEN and open_limit == True
                if cmd.name == CommandName.OPEN_GATE:
                    if endpoint_gate_state == "OPEN" and open_limit:
                        if cmd.status == CommandStatus.ACKNOWLEDGED:
                            cmd.mark_completed()
                        else:
                            cmd.reconcile_with_telemetry(
                                endpoint_confirmed=True,
                                note="RECONCILED_OPEN_CONFIRMED_BY_ENDPOINT_TELEMETRY",
                            )
                        reconciled.append(cmd)
                        self.save_command_state(cmd)
                    elif endpoint_gate_state == "FAULT":
                        cmd.mark_failed("GATE_FAULT_ENCOUNTERED")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)

                # CLOSE_GATE requires gate_state == CLOSED and closed_limit == True
                elif cmd.name == CommandName.CLOSE_GATE:
                    if endpoint_gate_state == "CLOSED" and closed_limit:
                        if cmd.status == CommandStatus.ACKNOWLEDGED:
                            cmd.mark_completed()
                        else:
                            cmd.reconcile_with_telemetry(
                                endpoint_confirmed=True,
                                note="RECONCILED_CLOSED_CONFIRMED_BY_ENDPOINT_TELEMETRY",
                            )
                        reconciled.append(cmd)
                        self.save_command_state(cmd)
                    elif endpoint_gate_state == "FAULT":
                        cmd.mark_failed("GATE_FAULT_ENCOUNTERED")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)

        return reconciled

    def reconcile_with_status_response(
        self,
        gate_state: GateState,
        closed_limit: bool,
        open_limit: bool,
    ) -> list[Command]:
        """Reconcile pending/timed-out movement commands using a verified fresh status query."""
        reconciled = []
        with self._lock:
            for cmd in self._commands.values():
                if cmd.name not in MOVEMENT_COMMANDS or cmd.outcome_resolved:
                    continue

                if cmd.name == CommandName.OPEN_GATE:
                    if gate_state == GateState.OPEN and open_limit:
                        cmd.reconcile_with_telemetry(True, "STATUS_QUERY_CONFIRMED_OPEN")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)
                    elif gate_state == GateState.CLOSED and closed_limit:
                        cmd.resolve_timeout_as_failed("STATUS_QUERY_CONFIRMED_GATE_STILL_CLOSED")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)
                    elif gate_state == GateState.FAULT:
                        cmd.mark_failed("GATE_IN_FAULT")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)

                elif cmd.name == CommandName.CLOSE_GATE:
                    if gate_state == GateState.CLOSED and closed_limit:
                        cmd.reconcile_with_telemetry(True, "STATUS_QUERY_CONFIRMED_CLOSED")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)
                    elif gate_state == GateState.OPEN and open_limit:
                        cmd.resolve_timeout_as_failed("STATUS_QUERY_CONFIRMED_GATE_STILL_OPEN")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)
                    elif gate_state == GateState.FAULT:
                        cmd.mark_failed("GATE_IN_FAULT")
                        reconciled.append(cmd)
                        self.save_command_state(cmd)

        return reconciled

    def validate_safety_preconditions(
        self,
        command: Command,
        gateway_state: ConnectionState,
        device_state: ConnectionState,
        gate_state: GateState,
    ) -> None:
        """
        Enforce strict safety rules before dispatching commands to the gateway:
        1. Gateway must be ONLINE.
        2. Device must be ONLINE.
        3. Movement commands (OPEN_GATE, CLOSE_GATE) require a known, stationary physical gate state:
           - OPEN_GATE requires gate_state == CLOSED.
           - CLOSE_GATE requires gate_state == OPEN.
        4. Rejects movement if gate_state is UNKNOWN, FAULT, OPENING, or CLOSING.
        5. Movement retries are disabled.
        6. Conflicting or unresolved movement commands block new movement until reconciled.
        """
        # Capability check
        capability = COMMAND_CAPABILITIES.get(command.name, CommandAvailability.UNAVAILABLE)
        if capability != CommandAvailability.SUPPORTED:
            raise CommandSafetyViolation(
                f"Command {command.name.value} is {capability.value} and cannot be dispatched"
            )

        # Gateway connectivity
        if gateway_state != ConnectionState.ONLINE:
            raise CommandSafetyViolation(
                f"Cannot dispatch {command.name.value}: Gateway is {gateway_state.value} (must be ONLINE)"
            )

        # Device connectivity
        if device_state != ConnectionState.ONLINE:
            raise CommandSafetyViolation(
                f"Cannot dispatch {command.name.value}: Device is {device_state.value} (must be ONLINE)"
            )

        # Movement safety rules
        if command.name in MOVEMENT_COMMANDS:
            # Check for any unresolved movement in progress or uncertain after timeout
            unresolved = self.get_unresolved_movement_command()
            if unresolved is not None and unresolved.command_id != command.command_id:
                raise CommandSafetyViolation(
                    f"Cannot dispatch {command.name.value}: Previous movement command '{unresolved.command_id}' "
                    f"is unresolved (status {unresolved.status.value}). Status reconciliation required before dispatching new movement."
                )

            # Gate state must be fully established and verified
            if gate_state == GateState.UNKNOWN:
                raise CommandSafetyViolation(
                    "Safety rejection: Physical gate state is UNKNOWN. Fresh verification required before movement."
                )
            if gate_state == GateState.FAULT:
                raise CommandSafetyViolation(
                    "Safety rejection: Physical gate is in FAULT state. Movement strictly prohibited."
                )
            if gate_state in (GateState.OPENING, GateState.CLOSING):
                raise CommandSafetyViolation(
                    f"Safety rejection: Gate is already moving ({gate_state.value})."
                )

            if command.name == CommandName.OPEN_GATE and gate_state != GateState.CLOSED:
                raise CommandSafetyViolation(
                    f"Safety rejection: OPEN_GATE requires gate state to be CLOSED (currently {gate_state.value})."
                )
            if command.name == CommandName.CLOSE_GATE and gate_state != GateState.OPEN:
                raise CommandSafetyViolation(
                    f"Safety rejection: CLOSE_GATE requires gate state to be OPEN (currently {gate_state.value})."
                )
