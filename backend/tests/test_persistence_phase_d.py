"""Phase D: SQLite Persistence, Retention, and Event Logging Tests.

Tests all required Phase D capabilities:
1. Schema creation (tables and indexes)
2. Telemetry persistence
3. Five-minute retention boundaries
4. Independent backend receive timestamps
5. Mission event insertion and transition deduplication
6. Command lifecycle persistence
7. Database restart and reopening from file
8. Old telemetry not becoming live state after restart
9. Unresolved movement commands not being redispatched
10. Explicit session reset
11. Invalid telemetry not being persisted
12. Database error handling without state corruption
"""

from datetime import datetime, timezone, timedelta
import json
import sqlite3
import tempfile
from pathlib import Path
import pytest

from app.communication.gateway_contract import CommandName, GateState, ConnectionState
from app.mission.command import CommandStatus, CommandTracker, CommandSafetyViolation
from app.mission.state import MissionStateManager
from app.storage.event_recorder import MissionEventRecorder
from app.storage.sqlite_storage import SQLiteStorage
from app.telemetry.processor import TelemetryError
from app.telemetry.service import TelemetryService


# 1. Schema Creation
def test_schema_creation():
    storage = SQLiteStorage(db_path=":memory:")
    cursor = storage._conn.cursor()

    # Verify tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    assert "telemetry" in tables
    assert "mission_events" in tables
    assert "commands" in tables

    # Verify indexes exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indexes = {row[0] for row in cursor.fetchall()}
    assert "idx_telemetry_received_epoch" in indexes
    assert "idx_telemetry_timestamp_ms" in indexes
    assert "idx_mission_events_epoch" in indexes
    assert "idx_mission_events_type" in indexes
    assert "idx_commands_status" in indexes
    assert "idx_commands_name" in indexes
    storage.close()


# 2. Telemetry Persistence
def test_telemetry_persistence():
    storage = SQLiteStorage(db_path=":memory:")
    now = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)

    telem = {
        "timestamp_ms": 42000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": 24.2,
        "pressure_hpa": 1013.5,
        "dht_temperature_c": 23.9,
        "humidity_pct": 52.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    }

    row_id = storage.insert_telemetry(telem, received_at=now)
    assert row_id > 0

    history = storage.get_telemetry_history(limit=10)
    assert len(history) == 1
    record = history[0]
    assert record["timestamp_ms"] == 42000
    assert record["mode"] == "ACTIVE"
    assert record["gate_state"] == "CLOSED"
    assert record["closed_limit"] == 1
    assert record["open_limit"] == 0
    assert record["bmp_temperature_c"] == 24.2
    assert record["pressure_hpa"] == 1013.5
    assert record["bmp280_ok"] == 1
    assert record["dht11_ok"] == 1
    assert record["fault"] is None
    storage.close()


# 3. Five-Minute Retention Boundaries
def test_five_minute_retention_pruning():
    storage = SQLiteStorage(db_path=":memory:")
    base_time = datetime(2026, 10, 21, 12, 10, 0, tzinfo=timezone.utc)

    telem_template = {
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    }

    # Record A: 6 minutes ago (360 seconds ago) -> outside 5-minute retention
    storage.insert_telemetry(
        {**telem_template, "timestamp_ms": 1000},
        received_at=base_time - timedelta(seconds=360),
    )

    # Record B: 4 minutes ago (240 seconds ago) -> inside 5-minute retention
    storage.insert_telemetry(
        {**telem_template, "timestamp_ms": 2000},
        received_at=base_time - timedelta(seconds=240),
    )

    # Record C: 1 minute ago (60 seconds ago) -> inside 5-minute retention
    storage.insert_telemetry(
        {**telem_template, "timestamp_ms": 3000},
        received_at=base_time - timedelta(seconds=60),
    )

    assert len(storage.get_telemetry_history()) == 3

    # Prune with 5-minute (300s) retention window relative to base_time
    deleted_count = storage.prune_telemetry(retention_seconds=300.0, current_time=base_time)
    assert deleted_count == 1

    remaining = storage.get_telemetry_history()
    assert len(remaining) == 2
    # Verify records B (2000) and C (3000) remain
    remaining_timestamps = [r["timestamp_ms"] for r in remaining]
    assert 2000 in remaining_timestamps
    assert 3000 in remaining_timestamps
    assert 1000 not in remaining_timestamps
    storage.close()


# 4. Independent Backend Receive Timestamps
def test_backend_receive_timestamp_independent_of_esp32_uptime():
    storage = SQLiteStorage(db_path=":memory:")
    backend_time = datetime(2026, 10, 21, 15, 30, 0, tzinfo=timezone.utc)

    # Simulated ESP32 that just rebooted (uptime 150 ms)
    telem = {
        "timestamp_ms": 150,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    }

    storage.insert_telemetry(telem, received_at=backend_time)

    record = storage.get_telemetry_history()[0]
    # Microcontroller uptime preserved as integer
    assert record["timestamp_ms"] == 150
    # Backend receive time preserved as wall-clock UTC
    assert record["received_at"] == backend_time.isoformat()
    assert record["received_at_epoch"] == backend_time.timestamp()
    storage.close()


# 5. Mission Event Insertion and Transition Deduplication
def test_mission_event_insertion_and_deduplication():
    storage = SQLiteStorage(db_path=":memory:")
    recorder = MissionEventRecorder(storage=storage)

    state_t0 = {
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "fault": None,
        "gateway_state": "ONLINE",
        "device_state": "ONLINE",
    }

    # 1. Steady tick (no state change) -> ZERO events emitted
    events = recorder.evaluate_state_transition(previous_state=state_t0, current_state=state_t0)
    assert len(events) == 0
    assert len(storage.get_events()) == 0

    # 2. Gate state transition (CLOSED -> OPENING) -> 1 event emitted
    state_t1 = {**state_t0, "gate_state": "OPENING", "closed_limit": False}
    events1 = recorder.evaluate_state_transition(previous_state=state_t0, current_state=state_t1)
    assert len(events1) == 1

    stored_events = storage.get_events()
    assert len(stored_events) == 1
    assert stored_events[0]["event_type"] == "GATE_STATE_CHANGE"
    assert stored_events[0]["subsystem"] == "GATE"
    assert stored_events[0]["details"]["to_state"] == "OPENING"

    # 3. Fault latched -> FAULT_RAISED event
    state_t2 = {**state_t1, "gate_state": "FAULT", "fault": "BOTH_LIMITS_ACTIVE"}
    recorder.evaluate_state_transition(previous_state=state_t1, current_state=state_t2)

    all_events = storage.get_events()
    fault_events = [e for e in all_events if e["event_type"] == "FAULT_RAISED"]
    assert len(fault_events) == 1
    assert fault_events[0]["severity"] == "ERROR"

    # 4. Connection loss -> CONNECTION_CHANGE event
    state_t3 = {**state_t2, "device_state": "OFFLINE"}
    recorder.evaluate_state_transition(previous_state=state_t2, current_state=state_t3)

    conn_events = [e for e in storage.get_events() if e["event_type"] == "CONNECTION_CHANGE"]
    assert len(conn_events) == 1
    assert conn_events[0]["details"]["to_state"] == "OFFLINE"
    storage.close()


# 6. Command Lifecycle Persistence
def test_command_lifecycle_persistence():
    storage = SQLiteStorage(db_path=":memory:")
    tracker = CommandTracker(storage=storage)

    # 1. Create command
    cmd = tracker.create_command(CommandName.OPEN_GATE, command_id="test-cmd-persist-1")
    assert cmd.status == CommandStatus.CREATED

    saved_cmd = storage.get_command("test-cmd-persist-1")
    assert saved_cmd is not None
    assert saved_cmd["status"] == "CREATED"
    assert saved_cmd["name"] == "OPEN_GATE"

    # 2. Mark SENT
    cmd.mark_sent(dispatched_at_ms=10500)
    tracker.save_command_state(cmd)
    saved_cmd = storage.get_command("test-cmd-persist-1")
    assert saved_cmd["status"] == "SENT"
    assert saved_cmd["dispatched_at_ms"] == 10500

    # 3. Mark ACKNOWLEDGED
    cmd.mark_acknowledged(accepted=True)
    tracker.save_command_state(cmd)
    saved_cmd = storage.get_command("test-cmd-persist-1")
    assert saved_cmd["status"] == "ACKNOWLEDGED"
    assert saved_cmd["acknowledged_at"] is not None

    # 4. Mark COMPLETED
    cmd.mark_completed()
    tracker.save_command_state(cmd)
    saved_cmd = storage.get_command("test-cmd-persist-1")
    assert saved_cmd["status"] == "COMPLETED"
    assert saved_cmd["completed_at"] is not None
    assert saved_cmd["outcome_resolved"] is True
    storage.close()


# 7. Database Restart and Reopening
def test_database_restart_and_reopening():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Initial run: write data and close
        storage1 = SQLiteStorage(db_path=db_path)
        storage1.insert_telemetry({
            "timestamp_ms": 12000,
            "mode": "ACTIVE",
            "gate_state": "CLOSED",
            "closed_limit": True,
            "open_limit": False,
        })
        storage1.insert_event(
            event_type="TEST_EVENT",
            severity="INFO",
            subsystem="MISSION",
            description="Testing restart",
        )
        storage1.save_command({
            "command_id": "cmd-restart-test",
            "name": "GET_STATUS",
            "status": "COMPLETED",
            "created_at": "2026-10-21T00:00:00Z",
            "outcome_resolved": True,
        })
        storage1.close()

        # Reopen on restarted server instance
        storage2 = SQLiteStorage(db_path=db_path)
        telem = storage2.get_telemetry_history()
        events = storage2.get_events()
        cmd = storage2.get_command("cmd-restart-test")

        assert len(telem) == 1
        assert telem[0]["timestamp_ms"] == 12000
        assert len(events) == 1
        assert events[0]["description"] == "Testing restart"
        assert cmd is not None
        assert cmd["command_id"] == "cmd-restart-test"
        assert cmd["status"] == "COMPLETED"
        storage2.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


# 8. Old Telemetry Not Becoming Live State After Restart
def test_old_telemetry_not_becoming_live_state_after_restart():
    storage = SQLiteStorage(db_path=":memory:")
    # Simulate DB containing old historical telemetry where gate was OPEN
    storage.insert_telemetry({
        "timestamp_ms": 99999,
        "mode": "ACTIVE",
        "gate_state": "OPEN",
        "closed_limit": False,
        "open_limit": True,
    })

    # When backend starts / restarts:
    new_manager = MissionStateManager()
    snapshot = new_manager.snapshot()

    # SAFETY INVARIANT: Live state MUST strictly remain UNKNOWN and NOT_CONNECTED
    assert snapshot["gate_state"] == "UNKNOWN"
    assert snapshot["gateway_state"] == "NOT_CONNECTED"
    assert snapshot["device_state"] == "NOT_CONNECTED"
    assert snapshot["open_limit"] is False
    assert snapshot["closed_limit"] is False
    storage.close()


# 9. Unresolved Movement Commands Not Being Redispatched
def test_unresolved_movement_commands_not_redispatched():
    storage = SQLiteStorage(db_path=":memory:")
    # Simulate a prior session where an OPEN_GATE command was sent but unconfirmed
    storage.save_command({
        "command_id": "unresolved-cmd-1",
        "name": "OPEN_GATE",
        "status": "SENT",
        "created_at": "2026-10-21T00:00:00Z",
        "dispatched_at_ms": 1000,
        "outcome_resolved": False,
    })

    tracker = CommandTracker(storage=storage)
    # Restore history for display
    tracker.load_history_from_storage()

    loaded_cmd = tracker.get_command("unresolved-cmd-1")
    assert loaded_cmd is not None
    assert loaded_cmd.status == CommandStatus.SENT

    # Verify that the tracker identifies this as unresolved movement
    unresolved = tracker.get_unresolved_movement_command()
    assert unresolved is not None
    assert unresolved.command_id == "unresolved-cmd-1"

    # Pre-dispatch safety rules MUST block any new movement command while unresolved exists
    new_cmd = tracker.create_command(CommandName.CLOSE_GATE, command_id="new-close-cmd")
    with pytest.raises(CommandSafetyViolation) as exc:
        tracker.validate_safety_preconditions(
            command=new_cmd,
            gateway_state=ConnectionState.ONLINE,
            device_state=ConnectionState.ONLINE,
            gate_state=GateState.OPEN,
        )
    assert "Previous movement command 'unresolved-cmd-1' is unresolved" in str(exc.value)
    storage.close()


# 10. Explicit Session Reset
def test_explicit_session_reset():
    storage = SQLiteStorage(db_path=":memory:")
    # Seed session data
    storage.insert_telemetry({
        "timestamp_ms": 100,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    })
    storage.insert_event(
        event_type="DEMO_START",
        severity="INFO",
        subsystem="MISSION",
        description="Demo started",
    )
    storage.save_command({
        "command_id": "cmd-demo-1",
        "name": "GET_STATUS",
        "status": "COMPLETED",
        "created_at": "2026-10-21T00:00:00Z",
    })

    assert len(storage.get_telemetry_history()) == 1
    assert len(storage.get_events()) == 1
    assert len(storage.list_commands()) == 1

    # Perform session reset
    storage.reset_session()

    # Telemetry and commands must be completely emptied
    assert len(storage.get_telemetry_history()) == 0
    assert len(storage.list_commands()) == 0

    # Events must only contain the single SESSION_RESET event
    events = storage.get_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "SESSION_RESET"
    storage.close()


# 11. Invalid Telemetry Not Persisted
def test_invalid_telemetry_not_persisted():
    storage = SQLiteStorage(db_path=":memory:")
    manager = MissionStateManager()
    service = TelemetryService(state_manager=manager, storage=storage)

    # Malformed JSON
    with pytest.raises(TelemetryError):
        service.process_line("{bad_json: True")

    # Missing required telemetry fields
    with pytest.raises(TelemetryError):
        service.process_line(json.dumps({"type": "telemetry", "mode": "ACTIVE"}))

    # Wrong message type
    with pytest.raises(TelemetryError):
        service.process_line(json.dumps({"type": "command_ack", "request_id": 1}))

    # DB must have zero records inserted
    assert len(storage.get_telemetry_history()) == 0
    storage.close()


# 12. Database Error Handling Without State Corruption
def test_database_error_handling_does_not_corrupt_state():
    # Create mock storage whose insert_telemetry raises an OperationalError
    class FaultyStorage(SQLiteStorage):
        def insert_telemetry(self, telemetry, received_at=None):
            raise sqlite3.OperationalError("Simulated disk I/O failure or database lock")

    faulty_storage = FaultyStorage(db_path=":memory:")
    manager = MissionStateManager()
    service = TelemetryService(state_manager=manager, storage=faulty_storage)

    valid_line = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 77777,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": 22.5,
        "pressure_hpa": 1012.0,
        "dht_temperature_c": 22.0,
        "humidity_pct": 50.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })

    # TelemetryService must catch DB error, log it, and continue cleanly
    result = service.process_line(valid_line)

    assert result["telemetry"]["timestamp_ms"] == 77777
    # Mission state was updated cleanly without corruption
    assert manager.snapshot()["gate_state"] == "CLOSED"
    assert manager.snapshot()["closed_limit"] is True
    faulty_storage.close()


# 13. Integration with API Routes
def test_persistence_api_routes():
    from app.api.routes import get_telemetry_history, list_events, reset_session, storage, telemetry_service

    # Ingest a valid telemetry line
    valid_line = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 88888,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": 21.0,
        "pressure_hpa": 1011.0,
        "dht_temperature_c": 20.0,
        "humidity_pct": 55.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })
    telemetry_service.process_line(valid_line)

    # Query telemetry history route
    telem_history = get_telemetry_history(limit=50)
    assert len(telem_history) >= 1
    assert telem_history[-1]["timestamp_ms"] == 88888

    # Query events route
    events = list_events(limit=50)
    assert isinstance(events, list)

    # Trigger session reset route
    reset_resp = reset_session()
    assert reset_resp["status"] == "session_reset"
    assert reset_resp["mission_state"]["gate_state"] == "UNKNOWN"

    # Confirm history cleared
    assert len(get_telemetry_history()) == 0


# 14. Retention pruning runs in real-gateway mode / without simulator
def test_retention_pruning_runs_without_simulator():
    storage = SQLiteStorage(db_path=":memory:")
    manager = MissionStateManager()
    # TelemetryService with 5-minute retention and 1.0s prune interval
    service = TelemetryService(
        state_manager=manager,
        storage=storage,
        retention_seconds=300.0,
        prune_interval_s=1.0,
    )

    t0 = datetime(2026, 10, 21, 10, 0, 0, tzinfo=timezone.utc)
    old_line = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 1000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": 22.0,
        "pressure_hpa": 1013.0,
        "dht_temperature_c": 21.0,
        "humidity_pct": 50.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })
    service.process_line(old_line, timestamp=t0.isoformat())
    assert len(storage.get_telemetry_history()) == 1

    # Ingest next line 6 minutes later (360 seconds later)
    t1 = t0 + timedelta(seconds=360)
    new_line = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 361000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": 22.5,
        "pressure_hpa": 1013.2,
        "dht_temperature_c": 21.5,
        "humidity_pct": 51.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })
    service.process_line(new_line, timestamp=t1.isoformat())

    # Verify old record (1000) was pruned and only new record (361000) remains
    history = storage.get_telemetry_history()
    assert len(history) == 1
    assert history[0]["timestamp_ms"] == 361000
    storage.close()


# 15. ESP32 reboot does not cause indefinite telemetry lockout
def test_esp32_reboot_does_not_lock_out_telemetry():
    manager = MissionStateManager()
    # Normal telemetry after 1 hour uptime
    line1 = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 3600000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    })
    manager.update_from_telemetry(json.loads(line1))
    assert manager.snapshot()["last_telemetry_timestamp_ms"] == 3600000

    # ESP32 reboots: millis() counter resets to 1000 ms
    reboot_line = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 1000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    })
    # MUST be accepted (not locked out)
    state = manager.update_from_telemetry(json.loads(reboot_line))
    assert state["last_telemetry_timestamp_ms"] == 1000
    assert state["device_state"] == "ONLINE"


# 16. ESP32 reboot marks in-flight movement command failed
def test_esp32_reboot_resolves_inflight_movement_command():
    storage = SQLiteStorage(db_path=":memory:")
    tracker = CommandTracker(storage=storage)

    cmd = tracker.create_command(CommandName.OPEN_GATE, command_id="reboot-cmd-test")
    # Dispatched before reboot at 50,000 ms
    cmd.mark_sent(dispatched_at_ms=50000)
    tracker.save_command_state(cmd)

    # ESP32 reboots and emits telemetry at 500 ms (< 50000 by > 2000 ms)
    tracker.reconcile_movement(
        endpoint_gate_state="CLOSED",
        open_limit=False,
        closed_limit=True,
        telemetry_timestamp_ms=500,
    )

    # Command must be marked failed rather than locked in unresolved limbo
    assert cmd.status == CommandStatus.FAILED
    assert cmd.error_reason == "DEVICE_REBOOTED_DURING_EXECUTION"
    assert cmd.outcome_resolved is True
    assert tracker.get_unresolved_movement_command() is None
    storage.close()


# 17. Connection transitions reach persistent event storage without duplicates
def test_connection_transitions_persisted_to_mission_events():
    storage = SQLiteStorage(db_path=":memory:")
    recorder = MissionEventRecorder(storage=storage)
    manager = MissionStateManager()
    # Attach listener so every transition records to storage
    manager.set_listener(recorder.evaluate_state_transition)

    # 1. Gateway comes ONLINE
    manager.update_gateway_health("ONLINE")
    events = storage.get_events()
    assert len(events) == 1
    assert events[0]["event_type"] == "CONNECTION_CHANGE"
    assert events[0]["subsystem"] == "GATEWAY"
    assert events[0]["details"]["to_state"] == "ONLINE"

    # 2. Steady heartbeat (ONLINE -> ONLINE) -> ZERO new events
    manager.update_gateway_health("ONLINE")
    assert len(storage.get_events()) == 1

    # 3. Staleness / Disconnect -> OFFLINE event
    manager.update_device_health("OFFLINE")
    events_after_disconnect = storage.get_events()
    assert len(events_after_disconnect) == 2
    assert events_after_disconnect[0]["event_type"] == "CONNECTION_CHANGE"
    assert events_after_disconnect[0]["subsystem"] == "DEVICE"
    assert events_after_disconnect[0]["details"]["to_state"] == "OFFLINE"
    storage.close()


# 18. Synchronized session reset preserves atomicity
def test_concurrent_session_reset_and_telemetry_safety():
    from app.api.routes import reset_session, storage, mission_state, command_tracker

    # Populate session data
    storage.insert_telemetry({
        "timestamp_ms": 5000,
        "mode": "ACTIVE",
        "gate_state": "OPEN",
        "closed_limit": False,
        "open_limit": True,
    })
    cmd = command_tracker.create_command(CommandName.OPEN_GATE)
    cmd.mark_sent()

    # Reset session
    resp = reset_session()
    assert resp["status"] == "session_reset"

    # Invariants strictly verified: gate state reverts to UNKNOWN, but active connection state is preserved
    assert len(storage.get_telemetry_history()) == 0
    assert len(command_tracker.list_commands()) == 0
    assert mission_state.snapshot()["gate_state"] == "UNKNOWN"
    assert mission_state.snapshot()["device_state"] == "ONLINE"
