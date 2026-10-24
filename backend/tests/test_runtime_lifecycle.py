"""Tests for FastAPI Runtime Lifecycle, SimulatorRunner, and Staleness Integration."""

from datetime import datetime, timezone, timedelta
import pytest

from app.communication.gateway_client import GatewayClient
from app.communication.gateway_contract import ConnectionState, GateState
from app.communication.gateway_simulator import GatewaySimulator
from app.communication.simulator_runner import SimulatorRunner
from app.main import app, health_check, lifespan, root
from app.mission.command import CommandTracker
from app.mission.state import MissionStateManager
from app.telemetry.service import TelemetryService


@pytest.mark.anyio
async def test_lifespan_startup_and_shutdown_no_task_leaks():
    """Verify that lifespan starts the runner and cleans up without leaking tasks."""
    from app.api.routes import simulator_runner
    from app.api.routes import rover_runner

    assert simulator_runner.is_running is False

    async with lifespan(app):
        assert simulator_runner.is_running is True
        assert simulator_runner._task is not None
        assert not simulator_runner._task.done()
        assert rover_runner.is_running is True

    # After lifespan exit, the task must be cleanly stopped and cancelled
    assert simulator_runner.is_running is False
    assert simulator_runner._task is None
    assert rover_runner.is_running is False
    assert rover_runner._task is None


def test_startup_does_not_invent_verified_gate_state():
    """
    Requirement 3: Verify that before device telemetry is received,
    the gate state is strictly UNKNOWN.
    """
    state_mgr = MissionStateManager()
    assert state_mgr.snapshot()["gate_state"] == "UNKNOWN"
    assert state_mgr.snapshot()["gateway_state"] == "NOT_CONNECTED"
    assert state_mgr.snapshot()["device_state"] == "NOT_CONNECTED"


def test_telemetry_loss_leads_to_stale_and_offline_deterministically():
    """
    Requirements 5 & 6: Verify that when telemetry stops arriving,
    staleness evaluation transitions device to STALE, then OFFLINE,
    and invalidates the physical gate state to UNKNOWN.
    """
    state_mgr = MissionStateManager()
    telem_svc = TelemetryService(state_mgr)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    client = GatewayClient(state_mgr, telem_svc, tracker, sim)

    runner = SimulatorRunner(
        gateway_client=client,
        simulator=sim,
        state_manager=state_mgr,
        stale_threshold_s=3.0,
        offline_threshold_s=10.0,
    )

    t0 = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)

    # Step at t0: healthy ingestion
    runner.step(now=t0)
    snap0 = state_mgr.snapshot()
    assert snap0["gateway_state"] == "ONLINE"
    assert snap0["device_state"] == "ONLINE"
    assert snap0["gate_state"] == "CLOSED"

    # Simulate device losing serial connection / stopping telemetry
    sim.trigger_disconnect("device")

    # Step at t0 + 4s: past stale threshold (3s), before offline (10s)
    t1 = t0 + timedelta(seconds=4)
    runner.step(now=t1)
    snap1 = state_mgr.snapshot()
    assert snap1["gateway_state"] == "ONLINE"  # Gateway is still ONLINE
    assert snap1["device_state"] == "STALE"    # Device is STALE
    assert snap1["gate_state"] == "CLOSED"     # Preserves last known while merely STALE

    # Step at t0 + 12s: past offline threshold (10s)
    t2 = t0 + timedelta(seconds=12)
    runner.step(now=t2)
    snap2 = state_mgr.snapshot()
    assert snap2["gateway_state"] == "ONLINE"
    assert snap2["device_state"] == "OFFLINE"
    # Physical gate state MUST revert to UNKNOWN when device is OFFLINE
    assert snap2["gate_state"] == "UNKNOWN"


def test_gateway_disconnect_invalidates_device_and_gate_state():
    """
    Requirement 7: Gateway disconnection cascades to device OFFLINE
    and gate state UNKNOWN, but keeps state models separate.
    """
    state_mgr = MissionStateManager()
    telem_svc = TelemetryService(state_mgr)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    client = GatewayClient(state_mgr, telem_svc, tracker, sim)

    runner = SimulatorRunner(client, sim, state_mgr)
    t0 = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)
    runner.step(now=t0)
    assert state_mgr.snapshot()["gate_state"] == "CLOSED"

    # Disconnect gateway
    sim.trigger_disconnect("gateway")
    runner.step(now=t0 + timedelta(seconds=1))

    snap = state_mgr.snapshot()
    assert snap["gateway_state"] == "OFFLINE"
    assert snap["device_state"] == "OFFLINE"
    assert snap["gate_state"] == "UNKNOWN"


def test_reconnection_refreshes_status_without_initiating_movement():
    """
    Requirement 8: Reconnection never issues movement commands.
    Gate state updates only from physical readings.
    """
    state_mgr = MissionStateManager()
    telem_svc = TelemetryService(state_mgr)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    client = GatewayClient(state_mgr, telem_svc, tracker, sim)
    runner = SimulatorRunner(client, sim, state_mgr)

    t0 = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)
    # Start in disconnected state
    sim.trigger_disconnect("device")
    runner.step(now=t0)
    assert state_mgr.snapshot()["gate_state"] == "UNKNOWN"

    # Reconnect device
    sim.trigger_reconnect("device")
    runner.step(now=t0 + timedelta(seconds=1))

    # Reconnection refreshes status from switch readings
    snap = state_mgr.snapshot()
    assert snap["device_state"] == "ONLINE"
    assert snap["gate_state"] == "CLOSED"

    # Verify zero movement commands were created or dispatched
    assert len(tracker.list_commands()) == 0


def test_invalid_telemetry_does_not_corrupt_state():
    """Verify that corrupt incoming telemetry is safely ignored."""
    state_mgr = MissionStateManager()
    telem_svc = TelemetryService(state_mgr)
    tracker = CommandTracker()
    sim = GatewaySimulator(initial_gate_state=GateState.CLOSED)
    client = GatewayClient(state_mgr, telem_svc, tracker, sim)
    runner = SimulatorRunner(client, sim, state_mgr)

    t0 = datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)
    runner.step(now=t0)
    assert state_mgr.snapshot()["gate_state"] == "CLOSED"

    # Trigger malformed telemetry
    sim.malformed_telemetry = True
    runner.step(now=t0 + timedelta(seconds=1))

    # State must remain CLOSED and not crash
    assert state_mgr.snapshot()["gate_state"] == "CLOSED"


@pytest.mark.anyio
async def test_root_and_health_indicate_simulation_mode():
    """Requirement 9: Simulator mode is explicitly identifiable in API endpoints."""
    r = await root()
    assert r["status"] == "online"
    assert r["simulation_mode"] is True

    h = await health_check()
    assert h["status"] == "healthy"
    assert h["simulation_mode"] is True


def test_snapshot_does_not_mutate_application_state():
    """
    Ensure snapshot() remains a pure read-only inspection
    and never mutates application state as a side effect.
    """
    state_mgr = MissionStateManager()
    snap1 = state_mgr.snapshot()
    snap2 = state_mgr.snapshot()
    assert snap1 == snap2
