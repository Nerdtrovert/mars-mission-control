"""Lander network manager for the Raspberry Pi gateway.

Manages the ESP32's Wi-Fi TCP stream, newline-delimited JSON, connection health,
command correlation, and live telemetry broadcasting.
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
    GatewayDevicesResponse,
    GatewayHealthResponse,
    LanderStatusResponse,
    OperatingMode,
)
from app.communication.request_mapper import RequestIdMapper
from app.telemetry.processor import TelemetryError, parse_telemetry
from gateway.config import GatewayConfig
from gateway.tcp_transport import LanderTCPTransport
from gateway.ws_manager import WebSocketBroadcaster

logger = logging.getLogger(__name__)


class LanderManager:
    """Coordinates lander TCP I/O, device state, command correlation, and telemetry broadcast."""

    def __init__(
        self,
        config: GatewayConfig,
        transport: LanderTCPTransport,
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

        # Cached lander status fields (no stale defaults; None until validated from status)
        self._timestamp_ms: Optional[int] = None
        self._mode: Optional[OperatingMode] = None
        self._sensors_polling: Optional[bool] = False
        self._bmp280_ok: Optional[bool] = None
        self._dht11_ok: Optional[bool] = None
        self._bmp280_state: Optional[str] = None
        self._dht11_state: Optional[str] = None
        self._firmware: Optional[str] = None

        # Concurrency & Command waiting
        self._write_lock = asyncio.Lock()
        self._pending_commands: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._valid_message_event = asyncio.Event()

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

    async def start(self) -> None:
        """Start the TCP listener and background worker loops."""
        if self._running:
            return

        self._running = True
        self._start_time = time.time()
        self._gateway_state = ConnectionState.ONLINE

        try:
            await self.transport.open()
        except Exception as e:
            logger.warning("Initial lander TCP listener start failed: %s. Will retry in background.", e)
            self._device_state = ConnectionState.NOT_CONNECTED
            self._invalidate_cached_hardware_state()

        self._reader_task = asyncio.create_task(self._reader_loop(), name="lander_reader_loop")
        self._staleness_task = asyncio.create_task(self._staleness_loop(), name="lander_staleness_loop")
        logger.info("LanderManager started successfully.")

    async def stop(self) -> None:
        """Cleanly stop background loops and close the TCP listener."""
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

        # Fail any pending commands promptly
        for req_id, fut in list(self._pending_commands.items()):
            if not fut.done():
                fut.set_result({"accepted": False, "reason": "GATEWAY_SHUTDOWN"})
        self._pending_commands.clear()

        try:
            await self.transport.close()
        except Exception as e:
            logger.warning("Error closing lander TCP listener on stop: %s", e)

        self._device_state = ConnectionState.NOT_CONNECTED
        self._invalidate_cached_hardware_state()
        logger.info("LanderManager stopped cleanly.")

    def _invalidate_cached_hardware_state(self) -> None:
        """Clear cached device and sensor state after disconnect or offline timeout."""
        self._mode = None
        self._timestamp_ms = None
        self._sensors_polling = False
        self._bmp280_ok = None
        self._dht11_ok = None
        self._bmp280_state = None
        self._dht11_state = None
        self._firmware = None

    async def _query_fresh_status(self) -> None:
        """
        Query device status snapshot via GET_STATUS.
        Strictly non-movement recovery query. Permitted whenever the TCP link is open.
        """
        if not self.transport.is_open():
            return

        cmd = CommandRequest(
            command_id=f"reconnect-sync-{int(time.time() * 1000)}",
            command=CommandName.GET_STATUS,
        )
        try:
            await self.send_command(cmd)
        except Exception as e:
            logger.warning("Failed to execute reconnect status query: %s", e)

    async def _reader_loop(self) -> None:
        """Continuously read framed JSON and wait for Wi-Fi reconnections."""
        while self._running:
            current_conn = self.transport.current_conn_id
            try:
                if self.transport.server is None:
                    try:
                        await self.transport.open()
                    except Exception as e:
                        logger.warning("Failed to open lander TCP listener: %s", e)
                        await asyncio.sleep(self.config.reconnect_delay_s)
                        continue

                # Read line from transport (waits up to timeout for a client or data)
                line = await self.transport.read_line(timeout=0.1)
                if line is None:
                    continue

                line_str = line.strip()
                if not line_str:
                    continue

                # Process the framed line (liveness updated only on valid JSON from ESP32)
                await self._process_raw_line(line_str)

            except (ConnectionError, OSError) as e:
                logger.warning("Lander TCP stream error: %s", e)
                try:
                    await self.transport.disconnect_client(conn_id=current_conn)
                except Exception:
                    pass
                self._handle_disconnect(conn_id=current_conn)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Unexpected error in lander TCP reader loop: %s", e, exc_info=True)
                await asyncio.sleep(0.1)

    def _handle_disconnect(self, conn_id: Optional[int] = None) -> None:
        """Handle link loss: mark OFFLINE, clear cached device state, fail pending commands."""
        # If a newer connection has already taken over, do not invalidate state
        if conn_id is not None and self.transport.current_conn_id != conn_id:
            return

        if self._device_state not in (ConnectionState.OFFLINE, ConnectionState.NOT_CONNECTED):
            logger.warning("ESP32 Wi-Fi connection lost.")
            self._device_state = (
                ConnectionState.OFFLINE if self._last_seen_timestamp is not None
                else ConnectionState.NOT_CONNECTED
            )
            self._invalidate_cached_hardware_state()

            # Reject all pending command futures immediately
            for req_id, fut in list(self._pending_commands.items()):
                if not fut.done():
                    fut.set_result({"accepted": False, "reason": "DEVICE_OFFLINE"})
            self._pending_commands.clear()

    async def _process_raw_line(self, line: str) -> None:
        """Validates JSON messages before refreshing liveness or broadcasting them."""
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Discarding malformed lander JSON message")
            return

        if not isinstance(payload, dict):
            return

        # Explicitly reject messages with retired actuator fields
        if {"gate_state", "closed_limit", "open_limit", "fault"} & payload.keys():
            logger.warning("Discarding message with retired actuator fields")
            return

        msg_type = payload.get("type")
        if msg_type == "telemetry":
            try:
                parse_telemetry(line)
            except TelemetryError as exc:
                logger.warning("Discarding invalid lander telemetry: %s", exc)
                return

        elif msg_type == "status":
            required = {"timestamp_ms", "mode", "sensors_polling", "bmp280_ok", "dht11_ok"}
            if not required.issubset(payload):
                return
            ts = payload.get("timestamp_ms")
            if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
                return
            if payload.get("mode") not in (OperatingMode.ACTIVE.value, OperatingMode.STANDBY.value):
                return
            if not isinstance(payload.get("sensors_polling"), bool):
                return
            if not isinstance(payload.get("bmp280_ok"), bool):
                return
            if not isinstance(payload.get("dht11_ok"), bool):
                return
            if "bmp280_state" in payload and payload["bmp280_state"] is not None and not isinstance(payload["bmp280_state"], str):
                return
            if "dht11_state" in payload and payload["dht11_state"] is not None and not isinstance(payload["dht11_state"], str):
                return
            if "firmware" in payload and payload["firmware"] is not None and not isinstance(payload["firmware"], str):
                return
            if "request_id" in payload and payload["request_id"] is not None:
                req_id = payload["request_id"]
                if isinstance(req_id, bool) or not isinstance(req_id, int) or req_id < 0:
                    return

        elif msg_type == "mode_status":
            if payload.get("mode") not in (OperatingMode.ACTIVE.value, OperatingMode.STANDBY.value):
                return
            if "request_id" in payload and payload["request_id"] is not None:
                req_id = payload["request_id"]
                if isinstance(req_id, bool) or not isinstance(req_id, int) or req_id < 0:
                    return

        elif msg_type == "command_ack":
            if not isinstance(payload.get("accepted"), bool):
                return
            if "request_id" in payload and payload["request_id"] is not None:
                req_id = payload["request_id"]
                if isinstance(req_id, bool) or not isinstance(req_id, int) or req_id < 0:
                    return
            if "reason" in payload and payload["reason"] is not None and not isinstance(payload["reason"], str):
                return

        else:
            return

        # Only validated device messages refresh liveness metrics.
        now = time.time()
        self._last_seen_timestamp = now
        self._last_seen_iso = datetime.now(timezone.utc).isoformat()
        self._valid_message_event.set()
        if self._device_state != ConnectionState.ONLINE:
            self._device_state = ConnectionState.ONLINE

        # 1. Command Acknowledgement
        if msg_type == "command_ack":
            req_id = payload.get("request_id")
            if req_id is not None and req_id in self._pending_commands:
                fut = self._pending_commands.get(req_id)
                if fut is not None and not fut.done():
                    fut.set_result(payload)

        # 2. Status Snapshot (response to GET_STATUS or on-connect status)
        elif msg_type == "status":
            self._update_from_status(payload)
            req_id = payload.get("request_id")
            if req_id is not None and req_id in self._pending_commands:
                fut = self._pending_commands.get(req_id)
                if fut is not None and not fut.done():
                    fut.set_result({"accepted": True, "reason": None})

        # 3. Mode Status Update
        elif msg_type == "mode_status":
            mode_val = payload.get("mode")
            if mode_val in (OperatingMode.ACTIVE.value, OperatingMode.STANDBY.value):
                self._mode = OperatingMode(mode_val)
            await self.ws_broadcaster.broadcast(payload)

        # 4. Periodic Telemetry (approx 1 Hz in ACTIVE mode)
        elif msg_type == "telemetry":
            self._update_from_telemetry(payload)
            await self.ws_broadcaster.broadcast(payload)

    def _update_from_telemetry(self, payload: dict[str, Any]) -> None:
        """Update cached status from periodic telemetry tick."""
        self._timestamp_ms = payload.get("timestamp_ms", self._timestamp_ms)
        mode_val = payload.get("mode")
        if mode_val in (OperatingMode.ACTIVE.value, OperatingMode.STANDBY.value):
            self._mode = OperatingMode(mode_val)

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

    def _update_from_status(self, payload: dict[str, Any]) -> None:
        """Update cached state from GET_STATUS full snapshot."""
        self._timestamp_ms = payload.get("timestamp_ms")
        mode_val = payload.get("mode")
        if mode_val in (OperatingMode.ACTIVE.value, OperatingMode.STANDBY.value):
            self._mode = OperatingMode(mode_val)

        self._sensors_polling = payload.get("sensors_polling", False)
        self._bmp280_ok = payload.get("bmp280_ok")
        self._dht11_ok = payload.get("dht11_ok")
        self._bmp280_state = payload.get("bmp280_state")
        self._dht11_state = payload.get("dht11_state")
        self._firmware = payload.get("firmware")

    async def _staleness_loop(self) -> None:
        """Periodic evaluation of telemetry and communication staleness."""
        while self._running:
            try:
                await asyncio.sleep(0.5)
                self._evaluate_staleness()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in staleness loop: %s", e, exc_info=True)

    def _evaluate_staleness(self, now: Optional[float] = None) -> None:
        """Apply receipt-time thresholds without treating gateway health as device health."""
        if self._last_seen_timestamp is None:
            return
        elapsed = (time.time() if now is None else now) - self._last_seen_timestamp
        if elapsed > self.config.offline_timeout_s:
            if self._device_state != ConnectionState.OFFLINE:
                logger.warning("Lander telemetry silence exceeded offline timeout.")
                self._device_state = ConnectionState.OFFLINE
                self._invalidate_cached_hardware_state()
        elif elapsed > self.config.stale_timeout_s and self._device_state == ConnectionState.ONLINE:
            self._device_state = ConnectionState.STALE

    async def send_command(self, cmd_req: CommandRequest) -> CommandResponse:
        """
        Submit a status or operating-mode command across the TCP stream.
        Allocates integer request_id, writes JSON, and awaits correlated ACK.
        GET_STATUS is permitted as a synchronization query whenever the TCP link is open.
        Operating mode changes (SET_ACTIVE, SET_STANDBY) require the device to be ONLINE.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        is_open = self.transport.is_open()
        is_online = self._device_state == ConnectionState.ONLINE

        if not is_open or (cmd_req.command != CommandName.GET_STATUS and not is_online):
            return CommandResponse(
                command_id=cmd_req.command_id,
                accepted=False,
                reason="DEVICE_OFFLINE",
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
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except asyncio.TimeoutError:
            return CommandResponse(
                command_id=cmd_req.command_id,
                accepted=False,
                reason="DEVICE_TIMEOUT",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except (ConnectionError, OSError) as e:
            logger.warning("Failed to write command to lander TCP stream: %s", e)
            try:
                await self.transport.disconnect_client()
            except Exception:
                pass
            self._handle_disconnect()
            return CommandResponse(
                command_id=cmd_req.command_id,
                accepted=False,
                reason="DEVICE_WRITE_ERROR",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            fut = self._pending_commands.pop(req_id, None)
            if fut is not None and not fut.done():
                fut.cancel()
            self.mapper.mark_completed(cmd_req.command_id)

    def get_health(self) -> GatewayHealthResponse:
        """GET /health response."""
        uptime = max(0.0, time.time() - self._start_time)
        return GatewayHealthResponse(
            status="healthy" if self._gateway_state == ConnectionState.ONLINE else "unhealthy",
            connection_state=self._gateway_state,
            version=self.config.version,
            uptime_seconds=round(uptime, 2),
            device_connected=(self._device_state == ConnectionState.ONLINE),
        )

    def get_devices(self) -> GatewayDevicesResponse:
        """GET /api/devices response."""
        device = DeviceInfo(
            device_id=self.config.device_id,
            name=self.config.device_name,
            connection_state=self._device_state,
            firmware_version=self._firmware,
            last_seen_at=self._last_seen_iso,
        )
        return GatewayDevicesResponse(devices=[device])

    def get_lander_status(self) -> LanderStatusResponse:
        """GET /api/lander/status response."""
        if self._device_state not in (ConnectionState.ONLINE, ConnectionState.STALE):
            return LanderStatusResponse(
                gateway_state=self._gateway_state,
                device_state=self._device_state,
                timestamp_ms=None,
                mode=None,
                sensors_polling=False,
                bmp280_ok=None,
                dht11_ok=None,
                bmp280_state="NO_DATA",
                dht11_state="NO_DATA",
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
            sensors_polling=self._sensors_polling,
            bmp280_ok=self._bmp280_ok,
            dht11_ok=self._dht11_ok,
            bmp280_state=bmp_state,
            dht11_state=dht_state,
            firmware=self._firmware,
        )
