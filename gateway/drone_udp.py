"""Dedicated UDP receiver for drone telemetry (UDP port 5007).

Ingests, validates, and stores drone telemetry datagrams, evaluates connection
staleness, and forwards compact display state to the lander over TCP port 5006.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import math
import time
from typing import Any, Optional

from gateway.config import GatewayConfig

logger = logging.getLogger("gateway.drone_udp")

MAX_DATAGRAM_SIZE = 4096


def _validate_numeric(
    value: Any,
    field_name: str,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> Optional[float]:
    """Validate numeric field: returns float or None; rejects bools, non-finite, out-of-range."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number or null")
    f_val = float(value)
    if not math.isfinite(f_val):
        raise ValueError(f"{field_name} must be finite")
    if min_val is not None and f_val < min_val:
        raise ValueError(f"{field_name} is below minimum allowed value ({f_val} < {min_val})")
    if max_val is not None and f_val > max_val:
        raise ValueError(f"{field_name} is above maximum allowed value ({f_val} > {max_val})")
    return f_val


def parse_drone_datagram(data: bytes) -> dict[str, Any]:
    """
    Parse and validate incoming drone datagram against the authoritative schema:
    {
      "device_id": "esp32-drone",
      "sequence": 1,
      "timestamp_ms": 123456,
      "flight_status": "STANDBY",
      "orientation": {"roll": null, "pitch": null, "yaw": null},
      "environment": {"temperature_c": null, "pressure_hpa": null, "humidity_pct": null},
      "gps": {"latitude": null, "longitude": null, "altitude_m": null},
      "battery": {"voltage_v": null, "percentage": null}
    }
    """
    if len(data) > MAX_DATAGRAM_SIZE:
        raise ValueError(f"Oversized datagram ({len(data)} > {MAX_DATAGRAM_SIZE} bytes)")

    try:
        text = data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("Packet must be valid UTF-8") from exc

    if not text:
        raise ValueError("Empty drone datagram")

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed JSON in drone packet") from exc

    if not isinstance(doc, dict):
        raise ValueError("Drone packet must be a JSON object")

    # Required top-level fields
    device_id = doc.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("device_id must be a non-empty string")

    seq = doc.get("sequence")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError("sequence must be a non-negative integer")

    ts = doc.get("timestamp_ms")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts < 0 or not math.isfinite(ts):
        raise ValueError("timestamp_ms must be a non-negative number")

    flight_status = doc.get("flight_status")
    if not isinstance(flight_status, str) or not flight_status.strip():
        raise ValueError("flight_status must be a non-empty string")

    # Validate orientation
    orientation = doc.get("orientation")
    if not isinstance(orientation, dict):
        raise ValueError("orientation must be a JSON object")
    roll = _validate_numeric(orientation.get("roll"), "orientation.roll")
    pitch = _validate_numeric(orientation.get("pitch"), "orientation.pitch")
    yaw = _validate_numeric(orientation.get("yaw"), "orientation.yaw")

    # Validate environment
    environment = doc.get("environment")
    if not isinstance(environment, dict):
        raise ValueError("environment must be a JSON object")
    temp_c = _validate_numeric(environment.get("temperature_c"), "environment.temperature_c", -100.0, 100.0)
    press_hpa = _validate_numeric(environment.get("pressure_hpa"), "environment.pressure_hpa", 0.0, 2000.0)
    hum_pct = _validate_numeric(environment.get("humidity_pct"), "environment.humidity_pct", 0.0, 100.0)

    # Validate gps
    gps = doc.get("gps")
    if not isinstance(gps, dict):
        raise ValueError("gps must be a JSON object")
    lat = _validate_numeric(gps.get("latitude"), "gps.latitude", -90.0, 90.0)
    lon = _validate_numeric(gps.get("longitude"), "gps.longitude", -180.0, 180.0)
    alt_m = _validate_numeric(gps.get("altitude_m"), "gps.altitude_m", -1000.0, 50000.0)

    # Validate battery
    battery = doc.get("battery")
    if not isinstance(battery, dict):
        raise ValueError("battery must be a JSON object")
    voltage_v = _validate_numeric(battery.get("voltage_v"), "battery.voltage_v", 0.0, 100.0)
    percentage = _validate_numeric(battery.get("percentage"), "battery.percentage", 0.0, 100.0)

    return {
        "device_id": device_id.strip(),
        "sequence": seq,
        "timestamp_ms": int(ts),
        "flight_status": flight_status.strip(),
        "orientation": {
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
        },
        "environment": {
            "temperature_c": temp_c,
            "pressure_hpa": press_hpa,
            "humidity_pct": hum_pct,
        },
        "gps": {
            "latitude": lat,
            "longitude": lon,
            "altitude_m": alt_m,
        },
        "battery": {
            "voltage_v": voltage_v,
            "percentage": percentage,
        },
    }


def is_newer_sequence(new_seq: int, last_seq: Optional[int]) -> bool:
    """
    Check if new_seq is newer than last_seq, supporting standard counter rollover (RFC 1982).
    Supports 16-bit unsigned rollover if values are within uint16, and 32-bit otherwise.
    """
    if last_seq is None:
        return True
    if new_seq == last_seq:
        return False

    if new_seq <= 65535 and last_seq <= 65535:
        modulus = 65536
        half = 32768
    else:
        modulus = 4294967296
        half = 2147483648

    diff = (new_seq - last_seq) % modulus
    return 0 < diff < half


class DroneUDPProtocol(asyncio.DatagramProtocol):
    """UDP protocol receiver tracking drone packets, sequence order, and staleness."""

    def __init__(
        self,
        config: GatewayConfig,
        broadcaster: Any,
        lander_manager: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.broadcaster = broadcaster
        self.lander_manager = lander_manager
        self.transport: Optional[asyncio.DatagramTransport] = None

        self._telemetry: Optional[dict[str, Any]] = None
        self._last_seq: Optional[int] = None
        self._last_seen_mono: Optional[float] = None
        self._last_seen: Optional[str] = None
        self._last_online: Optional[bool] = None

        self._duplicate_count: int = 0
        self._out_of_order_count: int = 0

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        logger.info(
            "Drone UDP receiver listening on %s:%s",
            self.config.drone_udp_host,
            self.config.drone_udp_port,
        )

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            parsed = parse_drone_datagram(data)
        except ValueError as exc:
            logger.warning("Rejected drone UDP datagram from %s:%s: %s", addr[0], addr[1], exc)
            return

        seq = parsed["sequence"]
        now_mono = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Update receipt liveness metrics for any schema-valid packet
        self._last_seen_mono = now_mono
        self._last_seen = now_iso
        self._last_online = True

        # Handle sequence ordering and rollover
        if self._last_seq is not None:
            if seq == self._last_seq:
                self._duplicate_count += 1
                logger.debug("Duplicate drone sequence %s from %s:%s", seq, addr[0], addr[1])
                return
            if not is_newer_sequence(seq, self._last_seq):
                self._out_of_order_count += 1
                logger.debug(
                    "Out-of-order drone sequence %s (last seen %s) from %s:%s",
                    seq,
                    self._last_seq,
                    addr[0],
                    addr[1],
                )
                return

        self._last_seq = seq
        self._telemetry = parsed

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast_status())
            if self.lander_manager is not None:
                loop.create_task(
                    self.lander_manager.forward_drone_telemetry(parsed, online=True)
                )
        except RuntimeError:
            pass

    def error_received(self, exc: Exception) -> None:
        logger.warning("Drone UDP socket error: %s", exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            logger.warning("Drone UDP receiver closed with error: %s", exc)
        self.transport = None

    def status(self) -> dict[str, Any]:
        online = self._last_seen_mono is not None and (
            time.monotonic() - self._last_seen_mono <= self.config.drone_offline_timeout_s
        )
        telem = self._telemetry if online else None
        gps = telem.get("gps", {}) if telem else {}
        battery = telem.get("battery", {}) if telem else {}

        return {
            "drone_id": "esp32-drone",
            "flight_status": telem.get("flight_status") if telem else None,
            "latitude": gps.get("latitude"),
            "longitude": gps.get("longitude"),
            "altitude_m": gps.get("altitude_m"),
            "battery_percentage": battery.get("percentage"),
            "connection_state": "ONLINE" if online else "OFFLINE",
            "last_seen": self._last_seen,
            "source": "network",
            "telemetry": self._telemetry,
        }

    async def _broadcast_status(self) -> None:
        await self.broadcaster.broadcast({"type": "drone_telemetry", "drone": self.status()})

    async def monitor_staleness(self) -> None:
        """Evaluate offline staleness and forward transition to lander and WebSocket."""
        while True:
            await asyncio.sleep(min(0.25, self.config.drone_offline_timeout_s / 2))
            st = self.status()
            online = st["connection_state"] == "ONLINE"
            if self._last_online is not online:
                self._last_online = online
                await self.broadcaster.broadcast({"type": "drone_telemetry", "drone": st})
                if self.lander_manager is not None:
                    await self.lander_manager.forward_drone_telemetry(self._telemetry, online=online)


class DroneUDPReceiver:
    """Lifecycle wrapper for the Drone UDP endpoint."""

    def __init__(
        self,
        config: GatewayConfig,
        broadcaster: Any,
        lander_manager: Optional[Any] = None,
    ) -> None:
        self.protocol = DroneUDPProtocol(config, broadcaster, lander_manager=lander_manager)
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._monitor_task: Optional[asyncio.Task[None]] = None
        self._simulator_task: Optional[asyncio.Task[None]] = None

    async def _simulator_loop(self) -> None:
        """Simulate drone telemetry when drone_simulator is configured and no external packets arrive."""
        tick = 0
        phases = ["STANDBY", "TAKEOFF", "CRUISING", "HOVERING", "LANDING"]
        while True:
            await asyncio.sleep(0.5)
            # Skip if external packet arrived recently
            if self.protocol._last_seen_mono and (
                time.monotonic() - self.protocol._last_seen_mono < self.protocol.config.drone_offline_timeout_s
            ):
                continue
            tick += 1
            phase = phases[(tick // 15) % len(phases)]
            lat = round(12.9716 + 0.0001 * math.sin(tick / 5.0), 6)
            lon = round(77.5946 + 0.0001 * math.cos(tick / 5.0), 6)
            alt = round(max(0.0, 50.0 + 10.0 * math.sin(tick / 10.0)) if phase != "STANDBY" else 0.0, 1)
            parsed = {
                "device_id": "esp32-drone",
                "sequence": tick,
                "timestamp_ms": int(time.time() * 1000),
                "flight_status": phase,
                "orientation": {
                    "roll": round(1.5 * math.sin(tick / 3.0), 1),
                    "pitch": round(1.2 * math.cos(tick / 4.0), 1),
                    "yaw": round((tick * 5.0) % 360.0, 1),
                },
                "environment": {
                    "temperature_c": 22.5,
                    "pressure_hpa": 1013.2,
                    "humidity_pct": 48.0,
                },
                "gps": {
                    "latitude": lat,
                    "longitude": lon,
                    "altitude_m": alt,
                },
                "battery": {
                    "voltage_v": round(11.1 + (tick % 100) * 0.015, 2),
                    "percentage": round(100.0 - (tick * 0.1) % 90.0, 1),
                },
            }
            self.protocol._telemetry = parsed
            self.protocol._last_seq = tick
            self.protocol._last_seen_mono = time.monotonic()
            self.protocol._last_seen = datetime.now(timezone.utc).isoformat()
            self.protocol._last_online = True
            await self.protocol._broadcast_status()
            if self.protocol.lander_manager is not None:
                await self.protocol.lander_manager.forward_drone_telemetry(parsed, online=True)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: self.protocol,
                local_addr=(self.protocol.config.drone_udp_host, self.protocol.config.drone_udp_port),
            )
            self._transport = transport  # type: ignore[assignment]
            self._monitor_task = asyncio.create_task(
                self.protocol.monitor_staleness(),
                name="drone_udp_staleness",
            )
            if self.protocol.config.drone_simulator:
                self._simulator_task = asyncio.create_task(
                    self._simulator_loop(),
                    name="drone_udp_simulator",
                )
        except OSError as exc:
            logger.warning("Could not bind drone UDP listener on port %s: %s", self.protocol.config.drone_udp_port, exc)

    async def stop(self) -> None:
        for task_attr in ("_monitor_task", "_simulator_task"):
            task = getattr(self, task_attr, None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, task_attr, None)
        if self._transport is not None:
            self._transport.close()
            self._transport = None
