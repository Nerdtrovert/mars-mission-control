"""SQLite Schema Definitions for Mars Mission Control Storage."""

CREATE_TELEMETRY_TABLE = """
CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    received_at_epoch REAL NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    mode TEXT NOT NULL,
    bmp_temperature_c REAL,
    pressure_hpa REAL,
    dht_temperature_c REAL,
    humidity_pct REAL,
    bmp280_ok INTEGER,
    dht11_ok INTEGER
);
"""

CREATE_TELEMETRY_INDEX_EPOCH = """
CREATE INDEX IF NOT EXISTS idx_telemetry_received_epoch ON telemetry(received_at_epoch);
"""

CREATE_TELEMETRY_INDEX_MS = """
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp_ms ON telemetry(timestamp_ms);
"""

CREATE_MISSION_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS mission_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    timestamp_epoch REAL NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    description TEXT NOT NULL,
    details TEXT
);
"""

CREATE_MISSION_EVENTS_INDEX_EPOCH = """
CREATE INDEX IF NOT EXISTS idx_mission_events_epoch ON mission_events(timestamp_epoch);
"""

CREATE_MISSION_EVENTS_INDEX_TYPE = """
CREATE INDEX IF NOT EXISTS idx_mission_events_type ON mission_events(event_type);
"""

CREATE_COMMANDS_TABLE = """
CREATE TABLE IF NOT EXISTS commands (
    command_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    completed_at TEXT,
    error_reason TEXT,
    params TEXT,
    missing_ack INTEGER NOT NULL DEFAULT 0,
    reconciliation_note TEXT,
    dispatched_at_ms INTEGER,
    outcome_resolved INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_COMMANDS_INDEX_STATUS = """
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
"""

CREATE_COMMANDS_INDEX_NAME = """
CREATE INDEX IF NOT EXISTS idx_commands_name ON commands(name);
"""

ALL_SCHEMA_STATEMENTS = [
    CREATE_TELEMETRY_TABLE,
    CREATE_TELEMETRY_INDEX_EPOCH,
    CREATE_TELEMETRY_INDEX_MS,
    CREATE_MISSION_EVENTS_TABLE,
    CREATE_MISSION_EVENTS_INDEX_EPOCH,
    CREATE_MISSION_EVENTS_INDEX_TYPE,
    CREATE_COMMANDS_TABLE,
    CREATE_COMMANDS_INDEX_STATUS,
    CREATE_COMMANDS_INDEX_NAME,
]
