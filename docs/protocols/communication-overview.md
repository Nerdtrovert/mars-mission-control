# Communication Protocols Overview

## Protocol Summary

| Path | Protocol | Port | Format | Rate | Direction |
|------|----------|------|--------|------|-----------|
| Lander ↔ Pi Gateway | TCP | 5006 | JSON (newline-delimited) | ~1 Hz | Bidirectional |
| Rover Laptop → Pi Gateway | UDP | 5005 | ASCII (key:value) | ~5 Hz | Laptop → Pi |
| Drone → Pi Gateway | UDP | 5007 | JSON | ~2 Hz | Drone → Pi |
| Pi Gateway → Backend | HTTP + WS | 8001 | JSON | Poll/Event | Pi → Backend |
| Backend → Dashboard | HTTP + WS | 8000 | JSON | Poll/Event | Backend → Browser |

---

## Lander TCP Protocol (Port 5006)

### Connection
- **Initiator**: ESP32 (client) → Pi Gateway (server)
- **Address**: 192.168.50.1:5006 (network) or 127.0.0.1:5006 (sim)
- **Reconnection**: ESP32 retries every 1s; Pi accepts new, closes old

### Framing
- Newline-delimited JSON (`\n` terminated)
- Max line: 768 bytes (ESP32) / 4096 bytes (Pi)
- Encoding: UTF-8

### Message Types (ESP32 → Pi)

| Type | Description | Fields |
|------|-------------|--------|
| `telemetry` | Sensor readings | timestamp_ms, mode, bmp_temperature_c, pressure_hpa, dht_temperature_c, humidity_pct, bmp280_ok, dht11_ok |
| `status` | Full status response | timestamp_ms, mode, sensors_polling, bmp280_ok, dht11_ok, bmp280_state, dht11_state, firmware, request_id |
| `mode_status` | Mode change ack | mode, request_id |
| `command_ack` | Command response | command, ok, accepted, message, request_id |

### Message Types (Pi → ESP32)

| Type | Description | Fields |
|------|-------------|--------|
| `command` | Control command | command (GET_STATUS/SET_ACTIVE/SET_STANDBY), request_id |
| `mission_display` | Forward rover/drone data to LCD | device (rover/drone), connected, data |

### Commands
- `GET_STATUS` — Request full status
- `SET_ACTIVE` — Enable sensor polling, 1 Hz telemetry
- `SET_STANDBY` — Disable sensor polling, 0.2 Hz telemetry

---

## Rover UDP Protocol (Port 5005)

### Connection
- **Initiator**: Rover Laptop (Windows GUI) → Pi Gateway (server)
- **Address**: 192.168.50.1:5005

### Format
- ASCII key:value pairs, comma-separated
- Single line per packet
- No framing delimiter (UDP datagram boundary)

### Packet Structure
```
DIST:<float>,PITCH:<float>,ROLL:<float>,CMD:<F|B|L|R|S>,MODE:<M|A>
```

### Field Specifications

| Field | Type | Range | Required |
|-------|------|-------|----------|
| DIST | float | 0–10000 cm | Yes |
| PITCH | float | -90 to +90° | Yes |
| ROLL | float | -90 to +90° | Yes |
| CMD | enum | F, B, L, R, S | Yes |
| MODE | enum | M, A | Yes |

### Example
```
DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
```

### Validation (Pi Gateway)
1. Exactly 5 fields present
2. All keys match expected (DIST, PITCH, ROLL, CMD, MODE)
3. Numeric values within range
4. CMD ∈ {F,B,L,R,S}
5. MODE ∈ {M,A}
6. Staleness: OFFLINE after 2s silence

---

## Drone UDP Protocol (Port 5007)

### Connection
- **Initiator**: Drone ESP32 → Pi Gateway (server)
- **Address**: 192.168.50.1:5007

### Format
- JSON (UTF-8)
- Max packet: 4096 bytes
- One JSON object per datagram

### Schema

```json
{
  "device_id": "esp32-drone",
  "sequence": 123,
  "timestamp_ms": 1234567890,
  "flight_status": "CRUISING",
  "orientation": {"roll": 1.2, "pitch": -0.5, "yaw": 180.0},
  "environment": {"temperature_c": 26.8, "pressure_hpa": 1013.2, "humidity_pct": 48.0},
  "gps": {"latitude": 12.9716, "longitude": 77.5946, "altitude_m": 50.0},
  "battery": {"voltage_v": 11.1, "percentage": 85.0}
}
```

### Validation (Pi Gateway)
1. Valid JSON parse
2. All required fields present
3. `device_id` non-empty string
4. `sequence` non-negative integer, newer than last (RFC 1982 rollover)
4. `timestamp_ms` non-negative integer
5. `flight_status` non-empty string
6. Numeric ranges for all sensor values
7. Rejected packets do NOT overwrite last valid state
8. Staleness: OFFLINE after 10s silence

### Sequence Number Handling (RFC 1982)
- 32-bit sequence space (supports 16-bit too)
- `is_newer(new, old)` = `0 < (new - old) mod 2^32 < 2^31`
- Handles rollover at 2^32 boundary

---

## Pi Gateway HTTP API (Port 8001)

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Process health check |
| `/api/devices` | GET | Lander device info + connection state |
| `/api/lander/status` | GET | Full lander status |
| `/api/rover/status` | GET | Rover status from UDP receiver |
| `/api/drone/status` | GET | Drone status from UDP receiver |
| `/api/rover/display` | POST | Forward rover data to lander LCD |
| `/api/drone/display` | POST | Forward drone data to lander LCD |
| `/api/commands` | POST | Send command to lander |
| `/ws/telemetry` | WS | Live telemetry broadcast |

### Response Format (Example: `/api/lander/status`)
```json
{
  "mode": "ACTIVE",
  "sensors_polling": true,
  "bmp280_ok": true,
  "dht11_ok": true,
  "bmp280_state": "OK",
  "dht11_state": "OK",
  "firmware_version": "1.5.0",
  "connection_state": "CONNECTED",
  "last_telemetry": {
    "timestamp_ms": 1234567890,
    "bmp_temperature_c": 24.2,
    "pressure_hpa": 1013.5,
    "dht_temperature_c": 24.0,
    "humidity_pct": 58.0
  }
}
```

---

## Backend HTTP API (Port 8000)

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | App info + simulation_mode |
| `/health` | GET | Health check + simulation_mode |
| `/dashboard` | GET | Main dashboard HTML |
| `/api/mission/state` | GET | Mission state snapshot |
| `/api/rover/status` | GET | Rover status (normalized source) |
| `/api/drone/status` | GET | Drone status (normalized source) |
| `/api/mission/commands` | GET | Command history |
| `/api/mission/commands` | POST | Submit command to lander |
| `/api/mission/events` | GET | Mission events log |
| `/api/mission/telemetry/history` | GET | Telemetry history (5-min window) |
| `/api/mission/session/reset` | POST | Clear session data |
| `/ws/telemetry` | WS | Live telemetry + state + commands |

### WebSocket Message Types (Backend → Dashboard)

| Type | Payload | Description |
|------|---------|-------------|
| `state_snapshot` | MissionStateSnapshot | Full state on connect |
| `lander_telemetry` | LanderTelemetry | Lander sensor data |
| `rover_telemetry` | RoverTelemetry | Rover data |
| `drone_telemetry` | DroneTelemetry | Drone data |
| `command_ack` | CommandAck | Command response |
| `event` | MissionEvent | Log event |
| `heartbeat` | {timestamp} | Keepalive |

---

## Operating Modes & Protocol Mapping

### Network Mode
| Subsystem | Backend Runner | Pi Gateway | Hardware |
|-----------|----------------|------------|----------|
| Lander | NetworkGatewayRunner (WS + HTTP) | LanderManager (TCP 5006) | ESP32 |
| Rover | RoverRunner (HTTP poll 0.2s) | RoverUDPReceiver (UDP 5005) | Laptop GUI |
| Drone | DroneRunner (HTTP poll 0.5s) | DroneUDPReceiver (UDP 5007) | ESP32 |

### Simulation Mode
| Subsystem | Backend Runner | Source |
|-----------|----------------|--------|
| Lander | GatewaySimulatorRunner | In-memory |
| Rover | RoverSimulatorRunner | In-memory |
| Drone | DroneSimulatorRunner | In-memory |

---

## Error Handling Summary

| Layer | Lander (TCP) | Rover (UDP) | Drone (UDP) |
|-------|--------------|-------------|-------------|
| **Transport** | Auto-reconnect 1s | Stateless | Stateless |
| **Framing** | Newline JSON | Datagram = packet | Datagram = packet |
| **Validation** | JSON schema | 5-field ASCII | JSON schema + sequence |
| **Staleness** | 3s STALE, 10s OFFLINE | 2s OFFLINE | 10s OFFLINE |
| **Duplicates** | Request ID correlation | N/A (no seq) | RFC 1982 sequence |
| **Invalid Data** | Log, ignore | Log, ignore | Log, reject, keep last valid |

---

## Related Documents

- [TCP Protocol](tcp-protocol.md) — Lander message formats
- [Rover UDP](rover-udp.md) — ASCII packet details
- [Drone UDP](drone-udp.md) — JSON schema and validation
- [Telemetry Schemas](telemetry-schemas.md) — JSON Schema definitions
- [Network Architecture](architecture/network-architecture.md) — Port assignments
- [Data Flow](architecture/data-flow.md) — Flow diagrams