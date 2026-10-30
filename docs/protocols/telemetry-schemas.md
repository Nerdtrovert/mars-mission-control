# Telemetry & API Schemas Reference

This document provides the authoritative schema definitions for all messages, datagrams, REST API models, and WebSocket event payloads across Mars Mission Control.

---

## 1. Lander TCP Protocol (Port 5006)

All messages over the Lander Wi-Fi TCP socket are framed as single-line, newline-delimited (`\n`) JSON strings.

### A. Telemetry Packet (`ESP32 -> Pi Gateway`)
Emitted periodically (~1 Hz) when the lander is in `ACTIVE` operating mode.

```json
{
  "type": "telemetry",
  "timestamp_ms": 104250,
  "mode": "ACTIVE",
  "bmp_temperature_c": 24.2,
  "pressure_hpa": 1013.5,
  "dht_temperature_c": 24.0,
  "humidity_pct": 58.0,
  "bmp280_ok": true,
  "dht11_ok": true
}
```

| Field | Type | Range / Values | Description |
|---|---|---|---|
| `type` | string | `"telemetry"` | Identifies payload as streaming telemetry |
| `timestamp_ms` | integer | `ge=0` | ESP32 monotonic boot uptime in milliseconds |
| `mode` | string | `"ACTIVE"`, `"STANDBY"` | Current operating mode |
| `bmp_temperature_c` | float / null | `-40.0` to `85.0` | Ambient temperature from BMP280 |
| `pressure_hpa` | float / null | `300.0` to `1100.0` | Barometric pressure from BMP280 |
| `dht_temperature_c` | float / null | `0.0` to `50.0` | Ambient temperature from DHT11 |
| `humidity_pct` | float / null | `20.0` to `90.0` | Relative humidity percentage from DHT11 |
| `bmp280_ok` | boolean | `true`, `false` | Hardware health flag for BMP280 |
| `dht11_ok` | boolean | `true`, `false` | Hardware health flag for DHT11 |

### B. Status Query Response (`ESP32 -> Pi Gateway`)
Emitted by the lander in response to a `GET_STATUS` command.

```json
{
  "type": "status",
  "timestamp_ms": 104250,
  "mode": "ACTIVE",
  "sensors_polling": true,
  "bmp280_ok": true,
  "dht11_ok": true,
  "bmp280_state": "OK",
  "dht11_state": "OK",
  "firmware": "1.5.0",
  "request_id": 42
}
```

### C. Mode Status Notification (`ESP32 -> Pi Gateway`)
Emitted upon mode transitions (`SET_ACTIVE` or `SET_STANDBY`).

```json
{
  "type": "mode_status",
  "mode": "ACTIVE",
  "request_id": 43
}
```

### D. Command Request (`Pi Gateway -> ESP32`)
Dispatched by the Gateway to command mode changes or query state.

```json
{
  "command": "GET_STATUS",
  "request_id": 42
}
```

Supported commands:
- `"GET_STATUS"`: Queries full telemetry and health status without altering state.
- `"SET_ACTIVE"`: Enables sensor polling (~1 Hz telemetry emission).
- `"SET_STANDBY"`: Pauses sensor polling; reduces telemetry emission rate.

### E. Command Acknowledgement (`ESP32 -> Pi Gateway`)
Returned by ESP32 immediately after parsing an incoming command line.

```json
{
  "type": "command_ack",
  "command": "SET_ACTIVE",
  "ok": true,
  "accepted": true,
  "message": "Lander active; sensor polling enabled",
  "request_id": 43
}
```

### F. Mission Display Relay (`Pi Gateway -> ESP32`)
Forwarded by Pi Gateway to ESP32 over TCP 5006 to display Rover and Drone telemetry on LCD Pages 3 and 4.

```json
{
  "type": "mission_display",
  "device": "rover",
  "connected": true,
  "data": {
    "distance": 145.2,
    "pitch": 0.5,
    "roll": -0.8,
    "cmd": "F",
    "mode": "M"
  }
}
```

```json
{
  "type": "mission_display",
  "device": "drone",
  "connected": true,
  "data": {
    "flight_status": "STABILIZED",
    "latitude": 18.4431,
    "longitude": 77.5833
  }
}
```

---

## 2. Rover UDP Protocol (Port 5005)

Telemetry is transmitted as an ASCII datagram over UDP from the Windows Tkinter GUI to the Raspberry Pi.

### Raw Datagram Format
```text
DIST:<float>,PITCH:<float>,ROLL:<float>,CMD:<cmd>,MODE:<mode>
```

Example packet:
```text
DIST:145.2,PITCH:0.5,ROLL:-0.8,CMD:F,MODE:M
```

| Token | Data Type | Permitted Values | Meaning |
|---|---|---|---|
| `DIST` | float | `0.0` to `400.0` cm | HC-SR04 ultrasonic distance |
| `PITCH`| float | `-90.0` to `90.0` deg | MPU6050 pitch inclination |
| `ROLL` | float | `-90.0` to `90.0` deg | MPU6050 roll inclination |
| `CMD`  | char  | `F`, `B`, `L`, `R`, `S` | Forward, Backward, Left, Right, Stop |
| `MODE` | char  | `M`, `A` | Manual or Autonomous mode |

### Internal Backend / Gateway Schema (`RoverStatus`)
Exposed over `GET /api/rover/status` and WebSocket broadcasts:

```json
{
  "rover_id": "mars-rover-01",
  "distance_cm": 145.2,
  "pitch_deg": 0.5,
  "roll_deg": -0.8,
  "command": "F",
  "mode": "M",
  "connection_state": "ONLINE",
  "last_seen": "2026-10-30T14:30:00.123456+00:00",
  "source": "network",
  "obstacle_detected": false,
  "event": "Nominal rover telemetry stream active."
}
```

---

## 3. Drone UDP Protocol (Port 5007)

Telemetry is transmitted as a single JSON datagram over UDP port 5007 from the Drone ESP32 to the Raspberry Pi.

### Authoritative UDP Datagram Schema (`DroneTelemetry`)

```json
{
  "device_id": "esp32-drone",
  "sequence": 1042,
  "timestamp_ms": 524100,
  "flight_status": "CRUISING",
  "orientation": {
    "roll": 1.5,
    "pitch": -0.8,
    "yaw": 182.4
  },
  "environment": {
    "temperature_c": 24.5,
    "pressure_hpa": 1012.8,
    "humidity_pct": 52.0
  },
  "gps": {
    "latitude": 18.5204,
    "longitude": 73.8567,
    "altitude_m": 12.5
  },
  "battery": {
    "voltage_v": 11.85,
    "percentage": 82.0
  }
}
```

### Internal Backend / Gateway Schema (`DroneStatus`)
Exposed over `GET /api/drone/status` and WebSocket broadcasts:

```json
{
  "drone_id": "esp32-drone",
  "flight_status": "CRUISING",
  "latitude": 18.5204,
  "longitude": 73.8567,
  "altitude_m": 12.5,
  "battery_percentage": 82.0,
  "connection_state": "ONLINE",
  "last_seen": "2026-10-30T14:30:00.123456+00:00",
  "source": "network",
  "telemetry": { ... }
}
```

---

## 4. Gateway REST API Contracts (Port 8001)

### `GET /health` -> `GatewayHealthResponse`
```json
{
  "status": "healthy",
  "connection_state": "ONLINE",
  "version": "1.0.0",
  "uptime_seconds": 3612.4,
  "device_connected": true
}
```

### `GET /api/lander/status` -> `LanderStatusResponse`
```json
{
  "gateway_state": "ONLINE",
  "device_state": "ONLINE",
  "timestamp_ms": 104250,
  "mode": "ACTIVE",
  "sensors_polling": true,
  "bmp280_ok": true,
  "dht11_ok": true,
  "bmp280_state": "OK",
  "dht11_state": "OK",
  "firmware": "1.5.0"
}
```

### `POST /api/lander/command`
Request:
```json
{
  "command_id": "c3a1e2f0-1234-4567-89ab-cdef01234567",
  "command": "SET_ACTIVE"
}
```
Response (`CommandResponse`):
```json
{
  "command_id": "c3a1e2f0-1234-4567-89ab-cdef01234567",
  "accepted": true,
  "reason": null,
  "fault": null,
  "timestamp": "2026-10-30T14:30:00.123456+00:00"
}
```

---

## 5. Backend REST API Contracts (Port 8000)

### `GET /api/mission/state`
Returns the thread-safe `MissionStateManager` snapshot:

```json
{
  "mode": "ACTIVE",
  "gateway_state": "ONLINE",
  "device_state": "ONLINE",
  "last_telemetry_at": "2026-10-30T14:30:00.123456+00:00",
  "last_gateway_heartbeat_at": "2026-10-30T14:30:00.123456+00:00",
  "last_device_telemetry_at": "2026-10-30T14:30:00.123456+00:00",
  "last_telemetry_timestamp_ms": 104250,
  "last_device_status_timestamp_ms": 104250,
  "bmp280_ok": true,
  "dht11_ok": true,
  "updated_at": "2026-10-30T14:30:00.123456+00:00",
  "simulation_mode": false
}
```

### `GET /api/mission/telemetry/history?limit=20`
Returns the recent sliding window history from SQLite storage:

```json
[
  {
    "received_at": "2026-10-30T14:30:00.123456+00:00",
    "timestamp_ms": 104250,
    "mode": "ACTIVE",
    "bmp_temperature_c": 24.2,
    "pressure_hpa": 1013.5,
    "dht_temperature_c": 24.0,
    "humidity_pct": 58.0,
    "bmp280_ok": true,
    "dht11_ok": true
  }
]
```

---

## 6. WebSocket Live Stream (`ws://<host>:<port>/ws/telemetry`)

Both the Gateway and the Development Machine backend expose `/ws/telemetry`. Frames are JSON-formatted with a top-level `"type"` attribute:

1. **`telemetry`**: Lander readings and mission state update.
2. **`rover_telemetry`**: Surface rover sensor reading.
3. **`drone_telemetry`**: Aerial drone status and sensor reading.
4. **`state_snapshot`**: Subsystem connectivity and mode change.
5. **`command_update`**: Dispatched command acknowledgement or state transition.
