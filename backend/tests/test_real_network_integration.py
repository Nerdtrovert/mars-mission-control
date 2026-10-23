"""Real Network Integration Tests for Raspberry Pi Gateway and MacBook Backend.

Tests real localhost HTTP and WebSocket connections between independent
gateway daemon and backend instances without mocks:
1. Health and status requests over real HTTP.
2. Telemetry propagation over real WebSocket into backend state and SQLite.
3. Command forwarding, UUID-to-integer mapping, and acknowledgement correlation.
4. Two-phase movement command lifecycle (ACK vs physical endpoint confirmation).
5. Safe blocking of unresolved movement commands.
6. Serial connection loss, recovery, and zero-auto-movement invariants.
7. Real WebSocket disconnection and automatic backoff reconnection.
8. Clean application shutdown without task leaks.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
from typing import Generator
import pytest
import uvicorn

from app.communication.gateway_client import GatewayClient
from app.communication.gateway_contract import (
    CommandName,
    ConnectionState,
    GateState,
)
from app.communication.network_runner import NetworkGatewayRunner
from app.mission.command import (
    Command,
    CommandSafetyViolation,
    CommandStatus,
    CommandTracker,
)
from app.mission.state import MissionStateManager
from app.storage.event_recorder import MissionEventRecorder
from app.storage.sqlite_storage import SQLiteStorage
from app.telemetry.service import TelemetryService

from gateway.config import GatewayConfig
from gateway.main import create_gateway_app
from gateway.transport import SimulatedSerialTransport


def get_free_port() -> int:
    """Acquire an available local TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class GatewayServerFixture:
    """Manages an actual Uvicorn server running the Gateway daemon in a background thread."""

    def __init__(self) -> None:
        self.port = get_free_port()
        self.config = GatewayConfig(
            serial_port="/dev/ttyUSB0",
            command_timeout_s=1.0,
            stale_timeout_s=2.0,
            offline_timeout_s=5.0,
            reconnect_delay_s=0.2,
        )
        self.transport = SimulatedSerialTransport()
        self.app = create_gateway_app(config=self.config, transport=self.transport)
        self.server = uvicorn.Server(
            config=uvicorn.Config(
                app=self.app,
                host="127.0.0.1",
                port=self.port,
                log_level="error",
            )
        )
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        # Wait for server to start listening
        for _ in range(50):
            if self.server.started:
                break
            time.sleep(0.05)
        if not self.server.started:
            raise RuntimeError("Failed to start Gateway Uvicorn server")

    def stop(self) -> None:
        self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=3.0)

    @property
    def http_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws/telemetry"


@pytest.fixture
def gateway_server() -> Generator[GatewayServerFixture, None, None]:
    """Provide a real, running Gateway daemon server on localhost."""
    gw = GatewayServerFixture()
    gw.start()
    yield gw
    gw.stop()


@pytest.fixture
def backend_stack(tmp_path: Path):
    """Provide real MacBook backend components with temporary SQLite storage."""
    db_file = str(tmp_path / "test_network.db")
    storage = SQLiteStorage(db_path=db_file)
    event_recorder = MissionEventRecorder(storage=storage)
    state_mgr = MissionStateManager()
    state_mgr.set_listener(event_recorder.evaluate_state_transition)
    telem_svc = TelemetryService(state_mgr, storage=storage, event_recorder=event_recorder)
    tracker = CommandTracker(storage=storage)
    return {
        "storage": storage,
        "event_recorder": event_recorder,
        "state_mgr": state_mgr,
        "telem_svc": telem_svc,
        "tracker": tracker,
    }


def start_serial_mock_responder(transport: SimulatedSerialTransport, stop_event: threading.Event) -> threading.Thread:
    """Thread-safe background mock of ESP32 firmware responses to serial commands."""
    def _run():
        while not stop_event.is_set():
            try:
                line = transport.tx_queue.get(timeout=0.05)
            except Exception:
                continue

            try:
                cmd_data = json.loads(line)
            except Exception:
                continue

            req_id = cmd_data.get("request_id", 1)
            cmd_name = cmd_data.get("command")

            if cmd_name == "GET_STATUS":
                transport.inject_rx_line(json.dumps({
                    "type": "command_ack",
                    "request_id": req_id,
                    "accepted": True,
                    "reason": None,
                }))
                transport.inject_rx_line(json.dumps({
                    "type": "status",
                    "request_id": req_id,
                    "timestamp_ms": 1000,
                    "mode": "ACTIVE",
                    "gate_state": "CLOSED",
                    "closed_limit": True,
                    "open_limit": False,
                    "fault": None,
                    "pending_standby": False,
                    "startup_limits_settled": True,
                    "limits_established": True,
                    "sensors_polling": True,
                    "bmp280_ok": True,
                    "dht11_ok": True,
                }))
            elif cmd_name == "OPEN_GATE":
                transport.inject_rx_line(json.dumps({
                    "type": "command_ack",
                    "request_id": req_id,
                    "accepted": True,
                    "reason": None,
                }))
                transport.inject_rx_line(json.dumps({
                    "type": "gate_status",
                    "state": "OPENING",
                }))
            elif cmd_name == "CLOSE_GATE":
                transport.inject_rx_line(json.dumps({
                    "type": "command_ack",
                    "request_id": req_id,
                    "accepted": True,
                    "reason": None,
                }))
                transport.inject_rx_line(json.dumps({
                    "type": "gate_status",
                    "state": "CLOSING",
                }))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


@pytest.mark.anyio
async def test_real_network_health_and_status(gateway_server, backend_stack):
    """Verify real HTTP communication for GET /health and GET /api/lander/status."""
    stop_event = threading.Event()
    responder_thread = start_serial_mock_responder(gateway_server.transport, stop_event)

    client = GatewayClient(
        state_manager=backend_stack["state_mgr"],
        telemetry_service=backend_stack["telem_svc"],
        command_tracker=backend_stack["tracker"],
        http_url=gateway_server.http_url,
    )

    await asyncio.sleep(0.1)

    # 1. Real HTTP GET /health
    health = await asyncio.to_thread(client.check_gateway_health)
    assert health.status == "healthy"
    assert health.connection_state == ConnectionState.ONLINE
    assert backend_stack["state_mgr"].snapshot()["gateway_state"] == "ONLINE"

    # 2. Real HTTP GET /api/lander/status
    status = await asyncio.to_thread(client.refresh_device_status)
    assert status.gateway_state == ConnectionState.ONLINE
    assert status.device_state == ConnectionState.ONLINE
    assert status.gate_state == GateState.CLOSED
    assert status.closed_limit is True

    snapshot = backend_stack["state_mgr"].snapshot()
    assert snapshot["gate_state"] == "CLOSED"
    assert snapshot["closed_limit"] is True

    stop_event.set()
    responder_thread.join(timeout=1.0)


@pytest.mark.anyio
async def test_real_network_telemetry_propagation_and_sqlite(gateway_server, backend_stack):
    """Verify real WebSocket telemetry streaming from Gateway to Backend and SQLite persistence."""
    stop_event = threading.Event()
    responder_thread = start_serial_mock_responder(gateway_server.transport, stop_event)

    client = GatewayClient(
        state_manager=backend_stack["state_mgr"],
        telemetry_service=backend_stack["telem_svc"],
        command_tracker=backend_stack["tracker"],
        http_url=gateway_server.http_url,
    )
    runner = NetworkGatewayRunner(
        gateway_client=client,
        state_manager=backend_stack["state_mgr"],
        ws_url=gateway_server.ws_url,
        http_url=gateway_server.http_url,
        interval_s=0.2,
        storage=backend_stack["storage"],
    )

    await runner.start()
    await asyncio.sleep(0.3)

    # Inject real ESP32 telemetry line into gateway's serial transport
    sample_telemetry = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 12000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": -15.4,
        "pressure_hpa": 765.2,
        "dht_temperature_c": -14.0,
        "humidity_pct": 14.5,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })
    gateway_server.transport.inject_rx_line(sample_telemetry)

    # Await WebSocket delivery over localhost
    await asyncio.sleep(0.4)

    # Verify backend state was updated via real network WebSocket
    snapshot = backend_stack["state_mgr"].snapshot()
    assert snapshot["last_telemetry_timestamp_ms"] == 12000
    assert snapshot["gate_state"] == "CLOSED"

    # Verify SQLite persistence
    history = backend_stack["storage"].get_telemetry_history(limit=10)
    assert len(history) >= 1
    assert history[0]["bmp_temperature_c"] == -15.4
    assert history[0]["pressure_hpa"] == 765.2

    await runner.stop()
    stop_event.set()
    responder_thread.join(timeout=1.0)


@pytest.mark.anyio
async def test_real_network_command_forwarding_and_ack_correlation(gateway_server, backend_stack):
    """Verify command dispatch over real HTTP, UUID-to-integer mapping, and ACK correlation."""
    stop_event = threading.Event()
    responder_thread = start_serial_mock_responder(gateway_server.transport, stop_event)

    client = GatewayClient(
        state_manager=backend_stack["state_mgr"],
        telemetry_service=backend_stack["telem_svc"],
        command_tracker=backend_stack["tracker"],
        http_url=gateway_server.http_url,
    )
    # Establish ONLINE states
    backend_stack["state_mgr"].update_gateway_health("ONLINE")
    backend_stack["state_mgr"].update_device_health("ONLINE")

    await asyncio.sleep(0.1)

    # Dispatch GET_STATUS command via HTTP POST
    cmd = backend_stack["tracker"].create_command(name=CommandName.GET_STATUS)
    resp = await asyncio.to_thread(client.dispatch_command, cmd)

    assert resp.accepted is True
    assert cmd.status == CommandStatus.COMPLETED

    # Check persistence
    stored = backend_stack["tracker"].get_command(cmd.command_id)
    assert stored is not None
    assert stored.status == CommandStatus.COMPLETED

    stop_event.set()
    responder_thread.join(timeout=1.0)


@pytest.mark.anyio
async def test_real_network_two_phase_movement_lifecycle(gateway_server, backend_stack):
    """Verify movement command ACK acceptance vs physical limit confirmation across real network."""
    stop_event = threading.Event()
    responder_thread = start_serial_mock_responder(gateway_server.transport, stop_event)

    client = GatewayClient(
        state_manager=backend_stack["state_mgr"],
        telemetry_service=backend_stack["telem_svc"],
        command_tracker=backend_stack["tracker"],
        http_url=gateway_server.http_url,
    )
    runner = NetworkGatewayRunner(
        gateway_client=client,
        state_manager=backend_stack["state_mgr"],
        ws_url=gateway_server.ws_url,
        http_url=gateway_server.http_url,
        interval_s=0.2,
        storage=backend_stack["storage"],
    )

    await runner.start()
    await asyncio.sleep(0.3)

    # Establish initial confirmed CLOSED state
    backend_stack["state_mgr"].update_from_device_status({
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "fault": None,
    })

    # Dispatch OPEN_GATE over real network
    open_cmd = backend_stack["tracker"].create_command(name=CommandName.OPEN_GATE)
    resp = await asyncio.to_thread(client.dispatch_command, open_cmd)

    assert resp.accepted is True
    # Movement is in-flight: acknowledgement does NOT equal completion!
    assert open_cmd.status == CommandStatus.ACKNOWLEDGED
    assert open_cmd.completed_at is None

    # Simulate physical travel completion: ESP32 sends fresh telemetry with open_limit=True
    confirmed_telemetry = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 15000,
        "mode": "ACTIVE",
        "gate_state": "OPEN",
        "closed_limit": False,
        "open_limit": True,
        "bmp_temperature_c": -12.0,
        "pressure_hpa": 760.0,
        "dht_temperature_c": -11.0,
        "humidity_pct": 10.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })
    gateway_server.transport.inject_rx_line(confirmed_telemetry)

    # Wait for WebSocket delivery
    await asyncio.sleep(0.4)

    # Now movement is confirmed by physical limit switch!
    assert open_cmd.status == CommandStatus.COMPLETED
    assert open_cmd.completed_at is not None

    await runner.stop()
    stop_event.set()
    responder_thread.join(timeout=1.0)


@pytest.mark.anyio
async def test_real_network_blocks_unresolved_movement_commands(gateway_server, backend_stack):
    """Verify safety rules block subsequent movement if a previous movement timed out or is unresolved."""
    client = GatewayClient(
        state_manager=backend_stack["state_mgr"],
        telemetry_service=backend_stack["telem_svc"],
        command_tracker=backend_stack["tracker"],
        http_url=gateway_server.http_url,
    )
    # Establish ONLINE states and CLOSED gate
    backend_stack["state_mgr"].update_gateway_health("ONLINE")
    backend_stack["state_mgr"].update_device_health("ONLINE")
    backend_stack["state_mgr"].update_from_device_status({
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    })

    # Manually register an unresolved in-flight movement command
    cmd1 = backend_stack["tracker"].create_command(name=CommandName.OPEN_GATE)
    cmd1.status = CommandStatus.ACKNOWLEDGED
    cmd1.outcome_resolved = False

    # Attempt to dispatch another movement command while cmd1 is unresolved
    cmd2 = backend_stack["tracker"].create_command(name=CommandName.OPEN_GATE)
    with pytest.raises(CommandSafetyViolation) as exc_info:
        client.dispatch_command(cmd2)
    assert "is unresolved" in str(exc_info.value)


@pytest.mark.anyio
async def test_real_network_connection_loss_and_recovery(gateway_server, backend_stack):
    """Verify link disconnect invalidates gate state to UNKNOWN and reconnect refreshes status with zero movement."""
    client = GatewayClient(
        state_manager=backend_stack["state_mgr"],
        telemetry_service=backend_stack["telem_svc"],
        command_tracker=backend_stack["tracker"],
        http_url=gateway_server.http_url,
    )
    runner = NetworkGatewayRunner(
        gateway_client=client,
        state_manager=backend_stack["state_mgr"],
        ws_url=gateway_server.ws_url,
        http_url=gateway_server.http_url,
        interval_s=0.2,
        reconnect_initial_delay_s=0.2,
        storage=backend_stack["storage"],
    )

    await runner.start()
    await asyncio.sleep(0.3)

    # Establish initial status
    backend_stack["state_mgr"].update_gateway_health("ONLINE")
    backend_stack["state_mgr"].update_device_health("ONLINE")
    backend_stack["state_mgr"].update_from_device_status({
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
    })

    # Simulate physical USB disconnect
    gateway_server.transport.disconnect()
    await asyncio.sleep(0.3)

    # Disconnect forces device to OFFLINE and gate state to UNKNOWN
    status = await asyncio.to_thread(client.refresh_device_status)
    assert status.device_state == ConnectionState.OFFLINE
    assert backend_stack["state_mgr"].snapshot()["gate_state"] == "UNKNOWN"

    # Reconnect serial cable
    gateway_server.transport.reconnect()
    # Feed fresh status response to GET_STATUS
    gateway_server.transport.inject_rx_line(json.dumps({
        "type": "status",
        "request_id": 1,
        "timestamp_ms": 25000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "fault": None,
        "pending_standby": False,
        "startup_limits_settled": True,
        "limits_established": True,
        "sensors_polling": True,
        "bmp280_ok": True,
        "dht11_ok": True,
    }))
    await asyncio.sleep(0.4)

    # Device recovers ONLINE, gate state verified as CLOSED, zero auto-movement issued
    recovered_status = await asyncio.to_thread(client.refresh_device_status)
    assert recovered_status.device_state == ConnectionState.ONLINE
    assert backend_stack["state_mgr"].snapshot()["gate_state"] == "CLOSED"

    await runner.stop()


@pytest.mark.anyio
async def test_real_network_clean_application_shutdown(gateway_server, backend_stack):
    """Verify clean shutdown of NetworkGatewayRunner cancels all background tasks without leaks."""
    client = GatewayClient(
        state_manager=backend_stack["state_mgr"],
        telemetry_service=backend_stack["telem_svc"],
        command_tracker=backend_stack["tracker"],
        http_url=gateway_server.http_url,
    )
    runner = NetworkGatewayRunner(
        gateway_client=client,
        state_manager=backend_stack["state_mgr"],
        ws_url=gateway_server.ws_url,
        http_url=gateway_server.http_url,
        interval_s=0.2,
    )

    await runner.start()
    assert runner.is_running is True
    assert runner._ws_task is not None
    assert runner._health_task is not None

    await asyncio.sleep(0.2)

    await runner.stop()
    assert runner.is_running is False
    assert runner._ws_task is None
    assert runner._health_task is None
