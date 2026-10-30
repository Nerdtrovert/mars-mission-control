"""Gateway Client Adapter for Mars Mission Control.

Acts as the development machine backend adapter to interface with the Raspberry Pi
hardware gateway (or the in-process GatewaySimulator during development and testing).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
import urllib.error
import urllib.request

from app.communication.gateway_contract import (
    CommandName,
    CommandRequest,
    CommandResponse,
    ConnectionState,
    GatewayHealthResponse,
    LanderStatusResponse,
)
from app.communication.gateway_simulator import GatewaySimulator
from app.mission.command import (
    Command,
    CommandTracker,
)
from app.mission.state import MissionStateManager
from app.telemetry.processor import TelemetryError
from app.telemetry.service import TelemetryService

logger = logging.getLogger(__name__)


def _http_get_json(url: str, timeout: float = 3.0) -> dict[str, Any]:
    """Execute a synchronous HTTP GET request returning parsed JSON."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, data: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """Execute a synchronous HTTP POST request with JSON payload returning parsed JSON."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class GatewayClient:
    """
    Adapter used by the development machine backend to interact with the Raspberry Pi gateway.
    Can be backed by an in-memory GatewaySimulator or network HTTP/WebSocket requests.
    """

    def __init__(
        self,
        state_manager: MissionStateManager,
        telemetry_service: TelemetryService,
        command_tracker: CommandTracker,
        simulator: Optional[GatewaySimulator] = None,
        http_url: Optional[str] = None,
        http_timeout: float = 3.0,
    ) -> None:
        self.state_manager = state_manager
        self.telemetry_service = telemetry_service
        self.command_tracker = command_tracker
        self.simulator = simulator
        self.http_url = http_url.rstrip("/") if http_url else None
        self.http_timeout = http_timeout

    def check_gateway_health(self, timestamp: Optional[str] = None) -> GatewayHealthResponse:
        """Query gateway daemon health and update state manager."""
        if self.simulator is not None:
            resp = self.simulator.get_health()
        elif self.http_url is not None:
            try:
                data = _http_get_json(f"{self.http_url}/health", timeout=self.http_timeout)
                resp = GatewayHealthResponse.model_validate(data)
            except Exception as e:
                logger.debug(f"Gateway health query to {self.http_url}/health failed: {e}")
                resp = GatewayHealthResponse(
                    status="unhealthy",
                    connection_state=ConnectionState.OFFLINE,
                    version="unknown",
                    uptime_seconds=0.0,
                    device_connected=False,
                )
        else:
            resp = GatewayHealthResponse(
                status="unhealthy",
                connection_state=ConnectionState.NOT_CONNECTED,
                version="unknown",
                uptime_seconds=0.0,
                device_connected=False,
            )

        self.state_manager.update_gateway_health(resp.connection_state.value, timestamp=timestamp)
        return resp

    def refresh_device_status(self) -> LanderStatusResponse:
        """
        Request fresh status from device (GET /api/lander/status or GET_STATUS command).
        Updates state manager deterministically without commanding physical movement.
        """
        if self.simulator is not None:
            resp = self.simulator.get_lander_status()
        elif self.http_url is not None:
            try:
                data = _http_get_json(f"{self.http_url}/api/lander/status", timeout=self.http_timeout)
                resp = LanderStatusResponse.model_validate(data)
            except Exception as e:
                logger.warning(f"Lander status query to {self.http_url}/api/lander/status failed: {e}")
                resp = LanderStatusResponse(
                    gateway_state=ConnectionState.OFFLINE,
                    device_state=ConnectionState.OFFLINE,
                )
        else:
            resp = LanderStatusResponse(
                gateway_state=ConnectionState.NOT_CONNECTED,
                device_state=ConnectionState.NOT_CONNECTED,
            )

        self.state_manager.update_gateway_health(resp.gateway_state.value)
        self.state_manager.update_device_health(resp.device_state.value)

        if resp.device_state == ConnectionState.ONLINE:
            self.state_manager.update_from_device_status({
                "mode": resp.mode.value if resp.mode else "ACTIVE",
                "timestamp_ms": resp.timestamp_ms,
                "bmp280_ok": resp.bmp280_ok,
                "dht11_ok": resp.dht11_ok,
            })

        return resp

    def dispatch_command(self, cmd: Command) -> CommandResponse:
        """
        Submit a command to the gateway following strict safety rules.
        """
        snapshot = self.state_manager.snapshot()
        gw_state = ConnectionState(snapshot["gateway_state"])
        dev_state = ConnectionState(snapshot["device_state"])

        # 1. Pre-dispatch safety invariants check
        self.command_tracker.validate_safety_preconditions(
            command=cmd,
            gateway_state=gw_state,
            device_state=dev_state,
        )

        # 2. Mark command as SENT with current device timestamp
        dev_time_ms = snapshot.get("last_telemetry_timestamp_ms")
        cmd.mark_sent(dispatched_at_ms=dev_time_ms)
        self.command_tracker.save_command_state(cmd)

        # 3. Transmit to gateway / simulator
        req = CommandRequest(
            command_id=cmd.command_id,
            command=cmd.name,
            params=cmd.params,
        )

        if self.simulator is not None:
            resp = self.simulator.handle_command(req)
        elif self.http_url is not None:
            try:
                data = _http_post_json(
                    f"{self.http_url}/api/commands",
                    req.model_dump(),
                    timeout=self.http_timeout,
                )
                resp = CommandResponse.model_validate(data)
            except Exception as e:
                logger.error(f"Command dispatch to {self.http_url}/api/commands failed: {e}")
                resp = CommandResponse(
                    command_id=cmd.command_id,
                    accepted=False,
                    reason="GATEWAY_NETWORK_ERROR",
                    timestamp=snapshot["updated_at"],
                )
        else:
            resp = CommandResponse(
                command_id=cmd.command_id,
                accepted=False,
                reason="GATEWAY_CLIENT_NOT_CONNECTED",
                timestamp=snapshot["updated_at"],
            )

        # 4. Record acknowledgement (or flag dropped ACK condition)
        if resp.reason == "SIMULATED_DROPPED_ACK":
            cmd.missing_ack = True
        else:
            cmd.mark_acknowledged(accepted=resp.accepted, reason=resp.reason)
        self.command_tracker.save_command_state(cmd)

        # Supported status and mode commands complete on acceptance.
        if resp.accepted and cmd.name in (CommandName.GET_STATUS, CommandName.SET_ACTIVE, CommandName.SET_STANDBY):
            cmd.mark_completed()
            self.command_tracker.save_command_state(cmd)

        return resp

    def ingest_telemetry_line(self, line: str, timestamp: Optional[str] = None) -> Optional[dict]:
        """
        Ingest a line of telemetry, updating mission state.
        Invalid telemetry is rejected and logged without corrupting current state.
        """
        try:
            result = self.telemetry_service.process_line(line, timestamp=timestamp)
        except (TelemetryError, ValueError):
            # Safe isolation: invalid telemetry must never corrupt state or crash application
            return None

        return result
