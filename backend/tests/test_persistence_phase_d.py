from app.storage.event_recorder import MissionEventRecorder
from app.storage.sqlite_storage import SQLiteStorage
import sqlite3


def test_sensor_telemetry_persists_without_retired_gate_columns():
    storage = SQLiteStorage()
    sample = {
        "timestamp_ms": 12, "mode": "ACTIVE", "bmp_temperature_c": 20.1,
        "pressure_hpa": 1000.0, "dht_temperature_c": 20.0, "humidity_pct": 50.0,
        "bmp280_ok": True, "dht11_ok": True,
    }
    storage.insert_telemetry(sample)
    row = storage.get_telemetry_history()[0]
    assert row["mode"] == "ACTIVE" and row["bmp_temperature_c"] == 20.1
    assert "gate_state" not in row and "fault" not in row


def test_event_recorder_preserves_connection_and_sensor_events_only():
    storage = SQLiteStorage()
    recorder = MissionEventRecorder(storage)
    recorder.evaluate_state_transition({}, {
        "gateway_state": "ONLINE", "device_state": "ONLINE", "bmp280_ok": True,
    })
    types = {event["event_type"] for event in storage.get_events()}
    assert types == {"CONNECTION_CHANGE", "SENSOR_HEALTH_CHANGE"}


def test_existing_database_migration_drops_actuator_data_and_keeps_sensors(tmp_path):
    path = tmp_path / "legacy.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE telemetry (
          id INTEGER PRIMARY KEY, received_at TEXT NOT NULL, received_at_epoch REAL NOT NULL,
          timestamp_ms INTEGER NOT NULL, mode TEXT NOT NULL, gate_state TEXT NOT NULL,
          closed_limit INTEGER NOT NULL, open_limit INTEGER NOT NULL, bmp_temperature_c REAL,
          pressure_hpa REAL, dht_temperature_c REAL, humidity_pct REAL, bmp280_ok INTEGER,
          dht11_ok INTEGER, fault TEXT
        );
        INSERT INTO telemetry VALUES (1,'2026-01-01T00:00:00+00:00',1767225600,1,'ACTIVE','CLOSED',1,0,22.0,1000.0,23.0,50.0,1,1,NULL);
        CREATE TABLE mission_events (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, timestamp_epoch REAL NOT NULL,
          event_type TEXT NOT NULL, severity TEXT NOT NULL, subsystem TEXT NOT NULL, description TEXT NOT NULL, details TEXT);
        INSERT INTO mission_events VALUES (1,'2026-01-01T00:00:00+00:00',1767225600,'GATE_STATE_CHANGE','INFO','GATE','old',NULL);
        CREATE TABLE commands (command_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT NOT NULL, acknowledged_at TEXT, completed_at TEXT, error_reason TEXT,
          params TEXT, missing_ack INTEGER NOT NULL DEFAULT 0, reconciliation_note TEXT,
          dispatched_at_ms INTEGER, outcome_resolved INTEGER NOT NULL DEFAULT 0);
        INSERT INTO commands(command_id,name,status,created_at) VALUES ('old','OPEN_GATE','COMPLETED','2026-01-01');
    """)
    connection.close()

    storage = SQLiteStorage(str(path))
    row = storage.get_telemetry_history()[0]
    assert row["bmp_temperature_c"] == 22.0 and "gate_state" not in row
    assert storage.get_events() == []
    assert storage.list_commands() == []
