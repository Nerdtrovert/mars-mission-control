"""Tests for Gateway API Contract and Schemas."""

import pytest
from pydantic import ValidationError

from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    CommandResponse,
    ConnectionState,
    DeviceInfo,
    GateState,
    GatewayDevicesResponse,
    GatewayHealthResponse,
    LanderStatusResponse,
    OperatingMode,
)


def test_gateway_health_response_schema():
    """Requirement 1: Gateway health response validation."""
    data = {
        "status": "healthy",
        "connection_state": "ONLINE",
        "version": "1.0.0",
        "uptime_seconds": 123.4,
        "serial_port": "/dev/ttyUSB0",
        "device_connected": True,
    }
    resp = GatewayHealthResponse(**data)
    assert resp.status == "healthy"
    assert resp.connection_state == ConnectionState.ONLINE
    assert resp.device_connected is True
    assert resp.uptime_seconds == 123.4


def test_gateway_health_rejects_negative_uptime():
    """Negative uptime must be rejected."""
    with pytest.raises(ValidationError):
        GatewayHealthResponse(
            status="healthy",
            connection_state=ConnectionState.ONLINE,
            version="1.0.0",
            uptime_seconds=-1.0,
            device_connected=False,
        )


def test_device_status_pi_online_esp32_offline():
    """Requirement 2: Device status when Pi is online but ESP32 is offline."""
    data = {
        "gateway_state": "ONLINE",
        "device_state": "OFFLINE",
        "timestamp_ms": None,
        "mode": None,
        "gate_state": "UNKNOWN",
        "closed_limit": False,
        "open_limit": False,
    }
    status = LanderStatusResponse(**data)
    assert status.gateway_state == ConnectionState.ONLINE
    assert status.device_state == ConnectionState.OFFLINE
    assert status.gate_state == GateState.UNKNOWN
    assert status.closed_limit is False
    assert status.open_limit is False


def test_gateway_client_copies_fresh_status_health_and_device_timestamp(monkeypatch):
    """The backend state snapshot must carry the gateway's current hardware status."""
    import app.communication.gateway_client as gateway_client_module
    from app.communication.gateway_client import GatewayClient
    from app.mission.command import CommandTracker
    from app.mission.state import MissionStateManager
    from app.telemetry.service import TelemetryService

    manager = MissionStateManager()
    client = GatewayClient(
        state_manager=manager,
        telemetry_service=TelemetryService(manager),
        command_tracker=CommandTracker(),
        http_url="http://pi-gateway:8001",
    )
    monkeypatch.setattr(
        gateway_client_module,
        "_http_get_json",
        lambda _url, timeout: {
            "gateway_state": "ONLINE",
            "device_state": "ONLINE",
            "timestamp_ms": 10_115_113,
            "mode": "ACTIVE",
            "gate_state": "UNKNOWN",
            "closed_limit": False,
            "open_limit": False,
            "fault": None,
            "bmp280_ok": False,
            "dht11_ok": True,
            "bmp280_state": "FAILED",
            "dht11_state": "OK",
            "firmware": "1.3.1",
        },
    )

    client.refresh_device_status()
    state = manager.snapshot()
    assert state["gateway_state"] == "ONLINE"
    assert state["device_state"] == "ONLINE"
    assert state["gate_state"] == "UNKNOWN"
    assert state["last_device_status_timestamp_ms"] == 10_115_113
    assert state["bmp280_ok"] is False
    assert state["dht11_ok"] is True


def test_command_request_schema_validation():
    """Requirement 5: Command schema validation."""
    req = CommandRequest(
        command_id="cmd-1234",
        command=CommandName.OPEN_GATE,
        params={"speed": 30},
    )
    assert req.command_id == "cmd-1234"
    assert req.command == CommandName.OPEN_GATE
    assert req.params == {"speed": 30}


def test_command_request_rejects_invalid_command():
    """Requirement 6: Invalid or unsupported command rejection."""
    with pytest.raises(ValidationError):
        CommandRequest(
            command_id="cmd-1234",
            command="EXPLODE_LANDER",  # type: ignore
        )


def test_command_response_schema():
    """Command acknowledgement response schema validation."""
    ack = CommandResponse(
        command_id="cmd-5678",
        accepted=True,
        reason=None,
        fault=None,
        timestamp="2026-10-20T10:00:00Z",
    )
    assert ack.command_id == "cmd-5678"
    assert ack.accepted is True
    assert ack.reason is None


def test_gateway_config_environment_variable_precedence(monkeypatch):
    """Verify GatewayConfig reads SERIAL_PORT and BAUD_RATE fallbacks."""
    from gateway.config import GatewayConfig

    # Test SERIAL_PORT fallback
    monkeypatch.delenv("GATEWAY_SERIAL_PORT", raising=False)
    monkeypatch.setenv("SERIAL_PORT", "/dev/ttyACM0")
    monkeypatch.delenv("GATEWAY_BAUD_RATE", raising=False)
    monkeypatch.setenv("BAUD_RATE", "57600")

    cfg = GatewayConfig()
    assert cfg.serial_port == "/dev/ttyACM0"
    assert cfg.baud_rate == 57600

    # Test GATEWAY_SERIAL_PORT takes precedence
    monkeypatch.setenv("GATEWAY_SERIAL_PORT", "/dev/ttyUSB1")
    cfg2 = GatewayConfig()
    assert cfg2.serial_port == "/dev/ttyUSB1"


def test_derive_ws_url_derivation():
    """Verify backend routes derive correct WebSocket URLs from HTTP URLs."""
    from app.api.routes import _derive_ws_url

    assert _derive_ws_url("http://192.168.1.50:8001") == "ws://192.168.1.50:8001/ws/telemetry"
    assert _derive_ws_url("http://192.168.1.50:8001/") == "ws://192.168.1.50:8001/ws/telemetry"
    assert _derive_ws_url("https://gateway.local:8001") == "wss://gateway.local:8001/ws/telemetry"


def test_env_example_files_exist_and_cover_all_variables():
    """Verify .env.example files exist and document all configuration variables."""
    from pathlib import Path

    root_dir = Path(__file__).resolve().parent.parent.parent
    root_example = root_dir / ".env.example"
    backend_example = root_dir / "backend" / ".env.example"
    gateway_example = root_dir / "gateway" / ".env.example"

    assert root_example.is_file(), "Root .env.example must exist"
    assert backend_example.is_file(), "backend/.env.example must exist"
    assert gateway_example.is_file(), "gateway/.env.example must exist"

    root_content = root_example.read_text(encoding="utf-8")
    backend_content = backend_example.read_text(encoding="utf-8")
    gateway_content = gateway_example.read_text(encoding="utf-8")

    # Required variables
    assert "GATEWAY_MODE=simulator" in root_content
    assert "GATEWAY_HTTP_URL=" in root_content
    assert "GATEWAY_WS_URL=" in root_content
    assert "MISSION_DB_PATH=" in root_content
    assert "GATEWAY_SERIAL_PORT=" in root_content
    assert "GATEWAY_BAUD_RATE=" in root_content

    assert "GATEWAY_MODE=simulator" in backend_content
    assert "MISSION_DB_PATH=" in backend_content

    assert "GATEWAY_SERIAL_PORT=" in gateway_content
    assert "GATEWAY_BAUD_RATE=" in gateway_content


def test_dotenv_loading_preserves_existing_environment(tmp_path, monkeypatch):
    """Verify .env loader loads unset variables and preserves existing variables."""
    import os
    from app import _load_env

    # Set up an existing variable that must NOT be overwritten
    monkeypatch.setenv("EXISTING_TEST_VAR", "preset_value")
    monkeypatch.delenv("NEW_ENV_FILE_VAR", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        "EXISTING_TEST_VAR=overwritten_bad\n"
        "NEW_ENV_FILE_VAR=loaded_good\n"
        "# Comment line\n"
        "\n",
        encoding="utf-8",
    )

    # Change working directory to tmp_path where .env resides
    monkeypatch.chdir(tmp_path)
    _load_env()

    assert os.environ.get("EXISTING_TEST_VAR") == "preset_value"
    assert os.environ.get("NEW_ENV_FILE_VAR") == "loaded_good"
