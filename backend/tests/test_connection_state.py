"""Tests for independent connection states, timeouts, and recovery semantics."""

from datetime import datetime, timezone, timedelta
from app.mission.state import MissionStateManager


def test_backend_restart_initial_state():
    """Requirement 8: After backend restart, gate state begins UNKNOWN."""
    manager = MissionStateManager()
    state = manager.snapshot()

    assert state["gate_state"] == "UNKNOWN"
    assert state["gateway_state"] == "NOT_CONNECTED"
    assert state["device_state"] == "NOT_CONNECTED"
    assert state["closed_limit"] is False
    assert state["open_limit"] is False
    assert state["fault"] is None


def test_pi_online_esp32_offline_independent_health():
    """Requirement 2: Pi gateway can be ONLINE while ESP32 lander is OFFLINE."""
    manager = MissionStateManager()
    manager.update_gateway_health("ONLINE")
    manager.update_device_health("OFFLINE")

    state = manager.snapshot()
    assert state["gateway_state"] == "ONLINE"
    assert state["device_state"] == "OFFLINE"
    assert state["gate_state"] == "UNKNOWN"


def test_stale_telemetry_detection():
    """Requirement 9: Telemetry staleness detected deterministically without sleeps."""
    manager = MissionStateManager()
    t0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Ingest fresh telemetry at t0
    manager.update_from_telemetry({
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    })
    # Overwrite timestamp with controlled t0 for deterministic test
    manager._state.last_device_telemetry_at = t0.isoformat()
    manager.update_device_health("ONLINE", timestamp=t0.isoformat())

    # Advance clock by 4 seconds (> stale threshold of 3.0s, < offline threshold of 10.0s)
    t1 = t0 + timedelta(seconds=4)
    state_after_4s = manager.check_staleness(current_time=t1, stale_threshold_s=3.0, offline_threshold_s=10.0)
    assert state_after_4s["device_state"] == "STALE"
    assert state_after_4s["gate_state"] == "CLOSED"  # Remains last known while merely STALE

    # Advance clock by 12 seconds (> offline threshold of 10.0s)
    t2 = t0 + timedelta(seconds=12)
    state_after_12s = manager.check_staleness(current_time=t2, stale_threshold_s=3.0, offline_threshold_s=10.0)
    assert state_after_12s["device_state"] == "OFFLINE"
    # When device goes OFFLINE, gate state MUST revert to UNKNOWN
    assert state_after_12s["gate_state"] == "UNKNOWN"


def test_gateway_disconnect_and_reconnect():
    """Requirement 10: Gateway disconnect marks subsystems offline; reconnect restores online."""
    manager = MissionStateManager()
    manager.update_gateway_health("ONLINE")
    manager.update_device_health("ONLINE")

    # Gateway disconnects
    manager.handle_disconnect("gateway")
    state = manager.snapshot()
    assert state["gateway_state"] == "OFFLINE"
    assert state["device_state"] == "OFFLINE"
    assert state["gate_state"] == "UNKNOWN"

    # Gateway reconnects
    manager.handle_reconnect("gateway")
    reconnected = manager.snapshot()
    assert reconnected["gateway_state"] == "ONLINE"
    # Note: Device remains OFFLINE until device session is independently confirmed
    assert reconnected["device_state"] == "OFFLINE"
    assert reconnected["gate_state"] == "UNKNOWN"


def test_esp32_disconnect_while_pi_remains_online():
    """Requirement 11: ESP32 disconnects while Raspberry Pi remains ONLINE."""
    manager = MissionStateManager()
    manager.update_gateway_health("ONLINE")
    manager.update_device_health("ONLINE")

    # Only device disconnects (e.g. USB cable pulled)
    manager.handle_disconnect("device")
    state = manager.snapshot()
    assert state["gateway_state"] == "ONLINE"
    assert state["device_state"] == "OFFLINE"
    assert state["gate_state"] == "UNKNOWN"


def test_no_automatic_movement_after_reconnection():
    """Requirement 12: Reconnection never commands movement; gate state remains UNKNOWN until verified."""
    manager = MissionStateManager()
    manager.handle_disconnect("device")
    assert manager.snapshot()["gate_state"] == "UNKNOWN"

    # Reconnect device
    manager.handle_reconnect("device")
    state = manager.snapshot()
    assert state["device_state"] == "ONLINE"
    # Gate state is strictly UNKNOWN until fresh GET_STATUS response arrives
    assert state["gate_state"] == "UNKNOWN"


def test_fresh_device_status_blocks_older_telemetry_and_preserves_sensor_health():
    """A current status response wins over delayed telemetry from an earlier device tick."""
    manager = MissionStateManager()
    manager.update_from_telemetry({
        "timestamp_ms": 10_115_100,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp280_ok": True,
        "dht11_ok": True,
    })

    current_status = manager.update_from_device_status({
        "timestamp_ms": 10_115_113,
        "mode": "ACTIVE",
        "gate_state": "UNKNOWN",
        "closed_limit": False,
        "open_limit": False,
        "fault": None,
        "bmp280_ok": False,
        "dht11_ok": True,
    })
    assert current_status["gate_state"] == "UNKNOWN"
    assert current_status["bmp280_ok"] is False
    assert current_status["dht11_ok"] is True

    stale = manager.update_from_telemetry({
        "timestamp_ms": 10_115_112,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": False,
        "open_limit": False,
        "bmp280_ok": True,
        "dht11_ok": True,
    })

    assert stale["gate_state"] == "UNKNOWN"
    assert stale["closed_limit"] is False
    assert stale["open_limit"] is False
    assert stale["last_telemetry_timestamp_ms"] == 10_115_100
    assert stale["bmp280_ok"] is False
    assert stale["dht11_ok"] is True


def test_reboot_clears_old_status_watermark_before_stale_check():
    manager = MissionStateManager()
    manager.update_from_telemetry({"timestamp_ms": 10_115_100, "mode": "ACTIVE"})
    manager.update_from_device_status({"timestamp_ms": 10_115_113, "mode": "ACTIVE"})

    rebooted = manager.update_from_telemetry({"timestamp_ms": 500, "mode": "ACTIVE"})

    assert rebooted["last_telemetry_timestamp_ms"] == 500
    assert rebooted["last_device_status_timestamp_ms"] is None
    assert rebooted["device_state"] == "ONLINE"

    fresh_status = manager.update_from_device_status({"timestamp_ms": 700, "mode": "ACTIVE"})
    assert fresh_status["last_device_status_timestamp_ms"] == 700
    next_sample = manager.update_from_telemetry({"timestamp_ms": 1500, "mode": "ACTIVE"})
    assert next_sample["last_telemetry_timestamp_ms"] == 1500


def test_telemetry_ordering_accepts_increasing_and_status_equal_but_rejects_same_boot_delay():
    manager = MissionStateManager()
    manager.update_from_telemetry({"timestamp_ms": 10_000, "mode": "ACTIVE"})
    increasing = manager.update_from_telemetry({"timestamp_ms": 11_000, "mode": "STANDBY"})
    assert increasing["last_telemetry_timestamp_ms"] == 11_000
    assert increasing["mode"] == "STANDBY"

    # A small counter regression follows the established same-boot stale rule.
    delayed = manager.update_from_telemetry({"timestamp_ms": 10_900, "mode": "ACTIVE"})
    assert delayed["last_telemetry_timestamp_ms"] == 11_000
    assert delayed["mode"] == "STANDBY"

    manager.update_from_device_status({"timestamp_ms": 11_500, "mode": "ACTIVE"})
    equal_to_status = manager.update_from_telemetry({"timestamp_ms": 11_500, "mode": "STANDBY"})
    # Backend's established watermark contract rejects strictly older frames;
    # equality can occur at millisecond resolution and remains accepted.
    assert equal_to_status["last_telemetry_timestamp_ms"] == 11_500
    assert equal_to_status["mode"] == "STANDBY"


def test_gate_endpoint_requires_its_limit_switch_confirmation():
    """An endpoint state without its corresponding active limit remains UNKNOWN."""
    manager = MissionStateManager()
    state = manager.update_from_device_status({
        "timestamp_ms": 500,
        "gate_state": "CLOSED",
        "closed_limit": False,
        "open_limit": False,
    })
    assert state["gate_state"] == "UNKNOWN"

    # Now simulate verified GET_STATUS response
    manager.update_from_device_status({
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "fault": None,
    })
    verified = manager.snapshot()
    assert verified["gate_state"] == "CLOSED"
    assert verified["closed_limit"] is True
