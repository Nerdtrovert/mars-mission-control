"""Serial Manager for Raspberry Pi Gateway.

Manages USB serial connection to ESP32, framed JSON line reading/writing,
ESP32 boot ROM text filtering, connection health lifecycle, RequestIdMapper correlation,
and live telemetry broadcasting.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Optional

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
from app.communication.request_mapper import RequestIdMapper
from gateway.config import GatewayConfig
from gateway.transport import SerialTransport
from gateway.ws_manager import WebSocketBroadcaster

logger = logging.getLogger(__name__)


class SerialManager:
    """Coordinates serial I/O, device state tracking, command correlation, and telemetry broadcast."""

    def __init__(
        self,
        config: GatewayConfig,
        transport: SerialTransport,
        ws_broadcaster: Optional[WebSocketBroadcaster] = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self.ws_broadcaster = ws_broadcaster or WebSocketBroadcaster()
        self.mapper = RequestIdMapper(max_history=1000)

        # Gateway process metrics
        self._start_time: float = time.time()
        self._gateway_state: ConnectionState = ConnectionState.ONLINE

        # Device connection lifecycle
        self._device_state: ConnectionState = ConnectionState.NOT_CONNECTED
        self._last_seen_timestamp: Optional[float] = None
        self._last_seen_iso: Optional[str] = None

        # Cached lander status fields
        self._timestamp_ms: Optional[int] = None
        self._mode: Optional[OperatingMode] = None
        self._gate_state: GateState = GateState.UNKNOWN
        self._closed_limit: bool = False
        self._open_limit: bool = False
        self._fault: Optional[str] = None
        self._pending_standby: Optional[bool] = None
        self._startup_limits_settled: Optional[bool] = None
        self._limits_established: Optional[bool] = None
        self._sensors_polling: Optional[bool] = False
        self._bmp280_ok: Optional[bool] = None
        self._dht11_ok: Optional[bool] = None
        self._bmp280_state: Optional[str] = None
        self._dht11_state: Optional[str] = None
        self._firmware: Optional[str] = "1.3.1"

        # Concurrency & Command waiting
        self._write_lock = asyncio.Lock()
        self._pending_commands: dict[int, asyncio.Future[dict[str, Any]]] = {}

        # Background tasks
        self._reader_task: Optional[asyncio.Task] = None
        self._staleness_task: Optional[asyncio.Task] = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def device_state(self) -> ConnectionState:
        return self._device_state

    @property
    def gate_state(self) -> GateState:
        return self._gate_state

    async def start(self) -> None:
        """Start the serial transport and background worker loops."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()
        self._gateway_state = ConnectionState.ONLINE

        try:
            await self.transport.open()
            self._device_state = ConnectionState.ONLINE
            # Immediately request device status upon initial connection
            await self._query_fresh_status()
        except Exception as e:
            logger.warning(f"Initial serial transport open failed: {e}. Will retry in background.")
            self._device_state = ConnectionState.NOT_CONNECTED
            self._invalidate_cached_hardware_state()

        self._reader_task = asyncio.create_task(self._reader_loop(), name="serial_reader_loop")
        self._staleness_task = asyncio.create_task(self._staleness_loop(), name="serial_staleness_loop")
        logger.info("SerialManager started successfully.")

    async def stop(self) -> None:
        """Cleanly stop background loops and close the serial transport."""
        if not self._running:
            return

        self._running = False

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._staleness_task is not None:
            self._staleness_task.cancel()
            try:
                await self._staleness_task
            except asyncio.CancelledError:
                pass
            self._staleness_task = None

        # Fail any pending commands
        for req_id, fut in list(self._pending_commands.items()):
            if not fut.done():
                fut.set_result({"accepted": False, "reason": "GATEWAY_SHUTDOWN"})
        self._pending_commands.clear()

        try:
            await self.transport.close()
        except Exception as e:
            logger.warning(f"Error closing serial transport on stop: {e}")

        self._device_state = ConnectionState.NOT_CONNECTED
        self._invalidate_cached_hardware_state()
        logger.info("SerialManager stopped cleanly.")

    def _invalidate_cached_hardware_state(self) -> None:
        """
        Safety invariant: when disconnected, never assume physical gate state.
        Strictly revert to UNKNOWN with both limit switch readings false.
        """
        self._gate_state = GateState.UNKNOWN
        self._closed_limit = False
        self._open_limit = False
        self._mode = None
        self._timestamp_ms = None
        self._fault = None
        self._sensors_polling = False
        self._bmp280_ok = None
        self._dht11_ok = None
        self._bmp280_state = None
        self._dht11_state = None

    async def _query_fresh_status(self) -> None:
        """
        Query device status snapshot via GET_STATUS.
        Strictly non-movement recovery query.
        """
        if not self.transport.is_open():
            return

        req_id = self.mapper.allocate("reconnect-sync-status")
        try:
            cmd_payload = json.dumps({"command": CommandName.GET_STATUS.value, "request_id": req_id})
            async with self._write_lock:
                await self.transport.write_line(cmd_payload)
        except Exception as e:
            logger.warning(f"Failed to transmit status query: {e}")
        finally:
            self.mapper.mark_completed("reconnect-sync-status")

    async def _reader_loop(self) -> None:
        """Background continuous reading loop with JSON framing & reconnect logic."""
        while self._running:
            try:
                if not self.transport.is_open():
                    # Handle disconnect / reconnect cycle
                    self._handle_disconnect()
                    await asyncio.sleep(self.config.reconnect_delay_s)
                    try:
                        await self.transport.open()
                    except Exception:
                        continue

                # If connection was restored, synchronize state and query status
                if self._device_state in (ConnectionState.OFFLINE, ConnectionState.NOT_CONNECTED) and self.transport.is_open():
                    logger.info("Serial transport reconnected successfully.")
                    self._device_state = ConnectionState.ONLINE
                    await self._query_fresh_status()

                # Read line from transport
                line = await self.transport.read_line(timeout=0.1)
                if line is None:
                    continue

                line_str = line.strip()
                if not line_str:
                    continue

                # Process the framed line (liveness updated only on valid JSON from ESP32)
                await self._process_raw_line(line_str)

            except (ConnectionError, OSError) as e:
                logger.warning(f"Serial read error: {e}")
                try:
                    await self.transport.close()
                except Exception:
                    pass
                self._handle_disconnect()
                await asyncio.sleep(self.config.reconnect_delay_s)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in serial reader loop: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    def _handle_disconnect(self) -> None:
        """Handle link loss: mark OFFLINE, invalidate gate state, fail pending commands."""
        if self._device_state != ConnectionState.OFFLINE:
            logger.warning("ESP32 serial connection lost. Transitioning device to OFFLINE.")
            self._device_state = ConnectionState.OFFLINE
            self._invalidate_cached_hardware_state()

            # Reject all pending command futures immediately
            for req_id, fut in list(self._pending_commands.items()):
                if not fut.done():
                    fut.set_result({"accepted": False, "reason": "DEVICE_OFFLINE"})
            self._pending_commands.clear()

    async def _process_raw_line(self, line: str) -> None:
        """
        Parses JSON line. Filters out ESP32 boot/ROM text without crashing.
        Routes telemetry, command_ack, status, and gate_status events.
        """
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            # Filter non-JSON text (e.g. ESP32 ROM boot text, garbage bytes)
            logger.debug(f"Discarding non-JSON serial line: {line}")
            return

        if not isinstance(payload, dict):
            return

        # Verified JSON packet received from ESP32: update liveness metrics
        now = time.time()
        self._last_seen_timestamp = now
        self._last_seen_iso = datetime.now(timezone.utc).isoformat()
        if self._device_state != ConnectionState.ONLINE:
            self._device_state = ConnectionState.ONLINE

        msg_type = payload.get("type")

        # 1. Command Acknowledgement
        if msg_type == "command_ack":
            req_id = payload.get("request_id")
            if req_id is not None and req_id in self._pending_commands:
                fut = self._pending_commands.pop(req_id)
                if not fut.done():
                    fut.set_result(payload)

        # 2. Status Snapshot (response to GET_STATUS)
        elif msg_type == "status":
            self._update_from_status(payload)
            req_id = payload.get("request_id")
            if req_id is not None and req_id in self._pending_commands:
                fut = self._pending_commands.pop(req_id)
                if not fut.done():
                    fut.set_result({"accepted": True, "reason": None, "fault": payload.get("fault")})

        # 3. Periodic Telemetry (approx 1 Hz in ACTIVE mode)
        elif msg_type == "telemetry":
            self._update_from_telemetry(payload)
            await self.ws_broadcaster.broadcast(payload)

        # 4. Gate Status Transition Event
        elif msg_type == "gate_status":
            self._update_from_gate_status(payload)
            await self.ws_broadcaster.broadcast(payload)

    def _update_from_telemetry(self, payload: dict[str, Any]) -> None:
        """Update cached status from periodic telemetry tick."""
        self._timestamp_ms = payload.get("timestamp_ms", self._timestamp_ms)
        mode_val = payload.get("mode")
        if mode_val in (OperatingMode.ACTIVE.value, OperatingMode.STANDBY.value):
            self._mode = OperatingMode(mode_val)

        gate_val = payload.get("gate_state")
        if gate_val in [g.value for g in GateState]:
            self._gate_state = GateState(gate_val)

        self._closed_limit = bool(payload.get("closed_limit", False))
        self._open_limit = bool(payload.get("open_limit", False))
        self._fault = payload.get("fault")
        self._sensors_polling = True
        self._bmp280_ok = payload.get("bmp280_ok")
        self._dht11_ok = payload.get("dht11_ok")

        # Synchronize detailed sensor state strings with fresh telemetry health
        if self._bmp280_ok is True:
            self._bmp280_state = "OK"
        elif self._bmp280_ok is False and self._bmp280_state != "NO_DATA":
            self._bmp280_state = "FAILED"

        if self._dht11_ok is True:
            self._dht11_state = "OK"
        elif self._dht11_ok is False and self._dht11_state != "NO_DATA":
            self._dht11_state = "FAILED"

    def _update_from_gate_status(self, payload: dict[str, Any]) -> None:
        """Update cached state from asynchronous gate movement / fault event."""
        state_val = payload.get("state")
        if state_val in [g.value for g in GateState]:
            self._gate_state = GateState(state_val)

        if "fault" in payload:
            self._fault = payload.get("fault")
        if "closed_limit" in payload:
            self._closed_limit = bool(payload.get("closed_limit"))
        if "open_limit" in payload:
            self._open_limit = bool(payload.get("open_limit"))

    def _update_from_status(self, payload: dict[str, Any]) -> None:
        """Update cached state from GET_STATUS full snapshot."""
        self._timestamp_ms = payload.get("timestamp_ms")
        mode_val = payload.get("mode")
        if mode_val in (OperatingMode.ACTIVE.value, OperatingMode.STANDBY.value):
            self._mode = OperatingMode(mode_val)

        gate_val = payload.get("gate_state")
        if gate_val in [g.value for g in GateState]:
            self._gate_state = GateState(gate_val)

        self._closed_limit = bool(payload.get("closed_limit", False))
        self._open_limit = bool(payload.get("open_limit", False))
        self._fault = payload.get("fault")
        self._pending_standby = payload.get("pending_standby")
        self._startup_limits_settled = payload.get("startup_limits_settled")
        self._limits_established = payload.get("limits_established")
        self._sensors_polling = payload.get("sensors_polling", False)
        self._bmp280_ok = payload.get("bmp280_ok")
        self._dht11_ok = payload.get("dht11_ok")
        self._bmp280_state = payload.get("bmp280_state")
        self._dht11_state = payload.get("dht11_state")
        self._firmware = payload.get("firmware", "1.3.1")

    async def _staleness_loop(self) -> None:
        """Periodic evaluation of telemetry and communication staleness."""
        while self._running:
            try:
                await asyncio.sleep(0.5)
                if self._last_seen_timestamp is None:
                    continue

                elapsed = time.time() - self._last_seen_timestamp

                if elapsed > self.config.offline_timeout_s:
                    if self._device_state != ConnectionState.OFFLINE:
                        logger.warning(f"Lander silence ({elapsed:.1f}s) exceeded offline timeout. Marking OFFLINE.")
                        self._device_state = ConnectionState.OFFLINE
                        self._invalidate_cached_hardware_state()
                elif elapsed > self.config.stale_timeout_s:
                    if self._device_state == ConnectionState.ONLINE:
                        logger.info(f"Lander silence ({elapsed:.1f}s) exceeded stale threshold. Marking STALE.")
                        self._device_state = ConnectionState.STALE

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in staleness loop: {e}", exc_info=True)

    async def send_command(self, cmd_req: CommandRequest) -> CommandResponse:
        """
        Submit a command for transmission across the serial link.
        Allocates integer request_id, writes JSON, and awaits correlated ACK.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Reject if device is not currently ONLINE
        if self._device_state != ConnectionState.ONLINE:
            return CommandResponse(
                command_id=cmd_req.command_id,
                accepted=False,
                reason="DEVICE_OFFLINE",
                fault=None,
                timestamp=now_iso,
            )

        # Allocate integer request_id for ESP32 protocol
        req_id = self.mapper.allocate(cmd_req.command_id)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_commands[req_id] = future

        try:
            payload = json.dumps({"command": cmd_req.command.value, "request_id": req_id})
            async with self._write_lock:
                await self.transport.write_line(payload)

            # Wait for correlated acknowledgement
            ack = await asyncio.wait_for(future, timeout=self.config.command_timeout_s)
            return CommandResponse(
                command_id=cmd_req.command_id,
                accepted=bool(ack.get("accepted", False)),
                reason=ack.get("reason"),
                fault=ack.get("fault"),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except asyncio.TimeoutError:
            self._pending_commands.pop(req_id, None)
            return CommandResponse(
                command_id=cmd_req.command_id,
                accepted=False,
                reason="DEVICE_TIMEOUT",
                fault=None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except (ConnectionError, OSError) as e:
            self._pending_commands.pop(req_id, None)
            logger.warning(f"Failed to write command to serial transport: {e}")
            self._handle_disconnect()
            try:
                await self.transport.close()
            except Exception:
                pass
            return CommandResponse(
                command_id=cmd_req.command_id,
                accepted=False,
                reason="DEVICE_WRITE_ERROR",
                fault=None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            self.mapper.mark_completed(cmd_req.command_id)

    def get_health(self) -> GatewayHealthResponse:
        """GET /health response."""
        uptime = max(0.0, time.time() - self._start_time)
        return GatewayHealthResponse(
            status="healthy" if self._device_state == ConnectionState.ONLINE else "degraded",
            connection_state=self._gateway_state,
            version=self.config.version,
            uptime_seconds=round(uptime, 2),
            serial_port=self.config.serial_port,
            device_connected=(self._device_state == ConnectionState.ONLINE),
        )

    def get_devices(self) -> GatewayDevicesResponse:
        """GET /api/devices response."""
        device = DeviceInfo(
            device_id=self.config.device_id,
            name=self.config.device_name,
            port=self.config.serial_port,
            connection_state=self._device_state,
            firmware_version=self._firmware,
            last_seen_at=self._last_seen_iso,
        )
        return GatewayDevicesResponse(devices=[device])

    def get_lander_status(self) -> LanderStatusResponse:
        """GET /api/lander/status response."""
        if self._device_state != ConnectionState.ONLINE:
            return LanderStatusResponse(
                gateway_state=self._gateway_state,
                device_state=self._device_state,
                timestamp_ms=None,
                mode=None,
                gate_state=GateState.UNKNOWN,
                closed_limit=False,
                open_limit=False,
                fault=None,
                pending_standby=None,
                startup_limits_settled=None,
                limits_established=None,
                sensors_polling=False,
                bmp280_ok=None,
                dht11_ok=None,
                bmp280_state="FAILED",
                dht11_state="FAILED",
                firmware=None,
            )

        bmp_state = (
            "OK" if self._bmp280_ok is True
            else ("FAILED" if (self._bmp280_ok is False and self._bmp280_state != "NO_DATA")
                  else (self._bmp280_state or ("FAILED" if self._bmp280_ok is False else "NO_DATA")))
        )
        dht_state = (
            "OK" if self._dht11_ok is True
            else ("FAILED" if (self._dht11_ok is False and self._dht11_state != "NO_DATA")
                  else (self._dht11_state or ("FAILED" if self._dht11_ok is False else "NO_DATA")))
        )

        return LanderStatusResponse(
            gateway_state=self._gateway_state,
            device_state=self._device_state,
            timestamp_ms=self._timestamp_ms,
            mode=self._mode,
            gate_state=self._gate_state,
            closed_limit=self._closed_limit,
            open_limit=self._open_limit,
            fault=self._fault,
            pending_standby=self._pending_standby,
            startup_limits_settled=self._startup_limits_settled,
            limits_established=self._limits_established,
            sensors_polling=self._sensors_polling,
            bmp280_ok=self._bmp280_ok,
            dht11_ok=self._dht11_ok,
            bmp280_state=bmp_state,
            dht11_state=dht_state,
            firmware=self._firmware,
        )
