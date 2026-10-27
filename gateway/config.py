"""Gateway Configuration and Environment Settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GatewayConfig:
    """Runtime configuration for the Raspberry Pi Hardware Gateway."""

    lander_tcp_host: str = field(default_factory=lambda: os.getenv("LANDER_TCP_HOST") or "0.0.0.0")
    lander_tcp_port: int = field(default_factory=lambda: int(os.getenv("LANDER_TCP_PORT") or "5006"))
    stale_timeout_s: float = field(default_factory=lambda: float(os.getenv("GATEWAY_STALE_TIMEOUT_S") or "3.0"))
    offline_timeout_s: float = field(default_factory=lambda: float(os.getenv("GATEWAY_OFFLINE_TIMEOUT_S") or "5.0"))
    command_timeout_s: float = field(default_factory=lambda: float(os.getenv("GATEWAY_COMMAND_TIMEOUT_S") or "2.0"))
    reconnect_delay_s: float = field(default_factory=lambda: float(os.getenv("LANDER_RECONNECT_DELAY_S") or "1.0"))
    rover_udp_host: str = field(default_factory=lambda: os.getenv("ROVER_UDP_HOST") or "0.0.0.0")
    rover_udp_port: int = field(default_factory=lambda: int(os.getenv("ROVER_UDP_PORT") or "5005"))
    rover_offline_timeout_s: float = field(default_factory=lambda: float(os.getenv("ROVER_OFFLINE_TIMEOUT_S") or "2.0"))
    version: str = "1.0.0"
    device_id: str = "esp32-lander"
    device_name: str = "ESP32 Lander Controller"
