"""Lifecycle tracking for the lander's status and operating-mode commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from threading import RLock
from typing import Any, Optional, TYPE_CHECKING
import uuid

from app.communication.gateway_contract import CommandName, ConnectionState

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.storage.sqlite_storage import SQLiteStorage


class CommandStatus(str, Enum):
    CREATED = "CREATED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    UNKNOWN = "UNKNOWN"


class CommandAvailability(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNAVAILABLE = "UNAVAILABLE"


COMMAND_CAPABILITIES: dict[CommandName, CommandAvailability] = {
    command: CommandAvailability.SUPPORTED for command in CommandName
}


class CommandError(Exception):
    """Base class for command errors."""


class CommandSafetyViolation(CommandError):
    """Raised when connectivity or supported-command requirements fail."""


class DuplicateCommandError(CommandError):
    """Raised when a command identifier has already been used."""


class InvalidStateTransitionError(CommandError):
    """Raised when a command lifecycle transition is illegal."""


@dataclass
class Command:
    name: CommandName
    command_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
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
        if self.status != CommandStatus.CREATED:
            raise InvalidStateTransitionError(f"Cannot transition to SENT from {self.status.value}")
        self.status = CommandStatus.SENT
        self.dispatched_at_ms = dispatched_at_ms

    def mark_acknowledged(self, accepted: bool, reason: Optional[str] = None) -> None:
        if self.status != CommandStatus.SENT:
            raise InvalidStateTransitionError(f"Cannot acknowledge command in state {self.status.value}")
        self.acknowledged_at = datetime.now(timezone.utc).isoformat()
        self.status = CommandStatus.ACKNOWLEDGED if accepted else CommandStatus.REJECTED
        self.error_reason = None if accepted else (reason or "REJECTED_BY_DEVICE")
        self.outcome_resolved = not accepted

    def mark_completed(self) -> None:
        if self.status != CommandStatus.ACKNOWLEDGED:
            raise InvalidStateTransitionError(f"Cannot complete command in state {self.status.value}")
        self.status = CommandStatus.COMPLETED
        self.outcome_resolved = True
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, reason: str) -> None:
        if self.status not in (CommandStatus.SENT, CommandStatus.ACKNOWLEDGED, CommandStatus.TIMED_OUT):
            raise InvalidStateTransitionError(f"Cannot mark failed from state {self.status.value}")
        self.status = CommandStatus.FAILED
        self.error_reason = reason
        self.outcome_resolved = True
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def mark_timed_out(self, reason: str = "COMMAND_TIMEOUT") -> None:
        if self.status not in (CommandStatus.SENT, CommandStatus.ACKNOWLEDGED):
            raise InvalidStateTransitionError(f"Cannot time out command in state {self.status.value}")
        self.status = CommandStatus.TIMED_OUT
        self.error_reason = reason
        self.outcome_resolved = True
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
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
    def __init__(self, storage: Optional[SQLiteStorage] = None) -> None:
        self.storage = storage
        self._lock = RLock()
        self._commands: dict[str, Command] = {}

    def save_command_state(self, command: Command) -> None:
        if self.storage is not None:
            try:
                self.storage.save_command(command.to_dict())
            except Exception as exc:
                logger.error("Failed to persist command %s: %s", command.command_id, exc)

    def clear(self) -> None:
        with self._lock:
            self._commands.clear()

    def load_history_from_storage(self) -> None:
        if self.storage is None:
            return
        records = sorted(self.storage.list_commands(limit=500), key=lambda row: row.get("created_at", ""))
        with self._lock:
            for row in records:
                command_id = row["command_id"]
                if command_id in self._commands:
                    continue
                self._commands[command_id] = Command(
                    name=CommandName(row["name"]),
                    command_id=command_id,
                    created_at=row["created_at"],
                    status=CommandStatus(row["status"]),
                    acknowledged_at=row.get("acknowledged_at"),
                    completed_at=row.get("completed_at"),
                    error_reason=row.get("error_reason"),
                    params=row.get("params"),
                    missing_ack=bool(row.get("missing_ack")),
                    reconciliation_note=row.get("reconciliation_note"),
                    dispatched_at_ms=row.get("dispatched_at_ms"),
                    outcome_resolved=bool(row.get("outcome_resolved")),
                )

    def create_command(
        self,
        name: CommandName,
        command_id: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Command:
        identifier = command_id or str(uuid.uuid4())
        with self._lock:
            if identifier in self._commands:
                raise DuplicateCommandError(f"Command ID {identifier} has already been used")
            command = Command(name=name, command_id=identifier, params=params)
            self._commands[identifier] = command
        self.save_command_state(command)
        return command

    def get_command(self, command_id: str) -> Optional[Command]:
        with self._lock:
            return self._commands.get(command_id)

    def list_commands(self) -> list[Command]:
        with self._lock:
            return list(self._commands.values())

    def validate_safety_preconditions(
        self,
        command: Command,
        gateway_state: ConnectionState,
        device_state: ConnectionState,
    ) -> None:
        if COMMAND_CAPABILITIES.get(command.name) != CommandAvailability.SUPPORTED:
            raise CommandSafetyViolation(f"Command {command.name.value} is unavailable")
        if gateway_state != ConnectionState.ONLINE:
            raise CommandSafetyViolation(f"Gateway is {gateway_state.value}; must be ONLINE")
        if device_state != ConnectionState.ONLINE:
            raise CommandSafetyViolation(f"Lander is {device_state.value}; must be ONLINE")
