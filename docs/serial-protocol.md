# Lander Wi-Fi stream and USB debugging

## Operational connection

Operational lander telemetry and status/mode commands use a TCP connection
initiated by the ESP32 over the private local Wi-Fi network. The Raspberry Pi
listens on LANDER_TCP_HOST (default 0.0.0.0) and LANDER_TCP_PORT (default 5006).
The connection carries newline-delimited UTF-8 JSON in both directions. The
Pi validates messages and updates lander connectivity only from valid,
recent device messages. A Pi process health response alone does not mark the
lander online.

Configure the ESP32 by copying
lander/lander_config.example.h to lander_config.h and setting the local
Wi-Fi SSID/password plus the Pi's LAN address. Keep this real config local;
the filename is git-ignored. Join both devices to the same private network.
The ESP32 retries Wi-Fi and TCP connections without stopping local sensor,
display, or LED updates.

## Message contract

ACTIVE telemetry is sent about once per second:

```json
{
  "type": "telemetry",
  "timestamp_ms": 17140,
  "mode": "ACTIVE",
  "bmp_temperature_c": 24.5,
  "pressure_hpa": 1008.2,
  "dht_temperature_c": 25.0,
  "humidity_pct": 60.0,
  "bmp280_ok": true,
  "dht11_ok": true
}
```

Unavailable or invalid sensor readings are null, with the matching health flag
false. The Pi rejects malformed, unsupported, or out-of-range telemetry without
refreshing the device receipt timestamp or overwriting its latest valid state.
After GATEWAY_OFFLINE_TIMEOUT_S without valid messages, lander status is
OFFLINE and stale sensor values are cleared.

The Pi sends GET_STATUS, SET_ACTIVE, and SET_STANDBY commands using the same
newline-delimited JSON framing. The ESP32 returns command_ack; GET_STATUS also
returns status, and mode changes return mode_status. These are status and
sensor-mode operations only; no physical movement commands exist.

## Remote mission display forwarding

The Raspberry Pi forwards live rover and drone status to the lander ESP32 across
the same TCP stream to populate dedicated remote display pages on the 20x4 LCD:

### Rover display message

```json
{
  "type": "mission_display",
  "device": "rover",
  "connected": true,
  "data": {
    "distance": 145.0,
    "pitch": 12.4,
    "roll": -3.2,
    "cmd": "F",
    "mode": "M"
  }
}
```

Field mapping from rover UDP:
- `DIST` -> `data.distance` (cm, float)
- `PITCH` -> `data.pitch` (deg, float)
- `ROLL` -> `data.roll` (deg, float)
- `CMD` -> `data.cmd` (command code, string)
- `MODE` -> `data.mode` (operating mode, string)

### Drone display message

```json
{
  "type": "mission_display",
  "device": "drone",
  "connected": true,
  "data": {
    "flight_status": "STANDBY",
    "latitude": 12.9716,
    "longitude": 77.5946,
    "altitude_m": 50.0
  }
}
```

### Staleness and connection rules
- The gateway rate-limits rover forwarding to at most 4 Hz during high-frequency changes, with a 2.5s heartbeat refresh when idle.
- When rover datagrams stop for `ROVER_OFFLINE_TIMEOUT_S` (2.0s), the gateway immediately sends a `mission_display` packet with `connected: false`.
- The lander firmware independently marks remote data `OFFLINE` if no packet arrives within 10 seconds (`REMOTE_TIMEOUT_MS`).
- When a lander connects or reconnects, the gateway immediately transmits the latest cached rover and drone display state.

## Serial and USB interfaces

1. **Lander ESP32 USB Serial**:
   - The ESP32 USB port operates at 115200 baud, 8N1 for firmware flashing and local development diagnostics.
   - Firmware mirrors JSON status/telemetry to USB serial for development convenience, but does not accept operational commands over USB serial.
   - The Raspberry Pi gateway never opens the lander's USB port. Operational lander telemetry is migrated entirely to Wi-Fi TCP (port 5006).

2. **Rover HC-12 Wireless Serial**:
   - The rover ESP32 communicates wirelessly with a dedicated HC-12 transceiver on the operator Windows PC at 9600 baud.
   - The Windows Tkinter GUI owns the local COM port, parses the serial packet, and forwards it to the Raspberry Pi gateway over UDP port 5005. The Pi gateway does not open the rover COM port.
