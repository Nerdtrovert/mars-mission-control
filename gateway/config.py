"""Gateway Configuration and Environment Settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GatewayConfig:
    """Runtime configuration for the Raspberry Pi Hardware Gateway."""

    serial_port: str = field(default_factory=lambda: os.getenv("GATEWAY_SERIAL_PORT") or os.getenv("SERIAL_PORT") or "/dev/ttyUSB0")
    baud_rate: int = field(default_factory=lambda: int(os.getenv("GATEWAY_BAUD_RATE") or os.getenv("BAUD_RATE") or "115200"))
    stale_timeout_s: float = field(default_factory=lambda: float(os.getenv("GATEWAY_STALE_TIMEOUT_S") or "3.0"))
    offline_timeout_s: float = field(default_factory=lambda: float(os.getenv("GATEWAY_OFFLINE_TIMEOUT_S") or "5.0"))
    command_timeout_s: float = field(default_factory=lambda: float(os.getenv("GATEWAY_COMMAND_TIMEOUT_S") or "2.0"))
    reconnect_delay_s: float = field(default_factory=lambda: float(os.getenv("GATEWAY_RECONNECT_DELAY_S") or "1.0"))
    version: str = "1.0.0"
    device_id: str = "esp32-lander"
    device_name: str = "ESP32 Lander Controller"
