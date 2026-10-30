# Lander TCP Protocol (Port 5006)

## Overview

The Lander communicates with the Raspberry Pi Gateway over a persistent TCP connection using newline-delimited JSON messages.

- **Port**: 5006
- **Initiator**: ESP32 (client) → Pi Gateway (server)
- **Framing**: Newline (`\n`) terminated JSON lines
- **Encoding**: UTF-8
- **Max Line**: 768 bytes (ESP32 TX) / 4096 bytes (Pi RX)
- **Rate**: ~1 Hz telemetry (ACTIVE), ~0.2 Hz (STANDBY)
- **Reconnection**: ESP32 retries every 1s; Pi accepts new connection, closes old

---

## Connection Lifecycle

```
ESP32 (Client)                          Pi Gateway (Server)
────────────────                         ──────────────────
   │                                        │
   │──── TCP SYN ─────────────────────────►│
   │◄─── TCP SYN-ACK ──────────────────────│
   │──── TCP ACK ─────────────────────────►│
   │                                        │
   │──── {"command":"GET_STATUS",          │
   │      "request_id": 1} ──────────────►│
   │                                        │
   │◄─── {"type":"status",                 │
   │      "mode":"STANDBY",                │
   │      "request_id": 1, ...} ──────────│
   │                                        │
   │  (periodic telemetry)                 │
   │──── {"type":"telemetry",              │
   │      "timestamp_ms": 123456,          │
   │      "mode":"ACTIVE", ...} ─────────►│
   │                                        │
   │◄─── {"type":"mission_display",        │
   │      "device":"rover",                │
   │      "connected":true, ...} ─────────│
   │                                        │
   │  (on disconnect)                      │
   │  ESP32: reconnect after 1s            │
   │  Pi: accept new, close old            │
```

---

## ESP32 → Pi Messages

### 1. Telemetry (Periodic, ~1 Hz in ACTIVE)

```json
{
  "type": "telemetry",
  "timestamp_ms": 1234567890,
  "mode": "ACTIVE",
  "bmp_temperature_c": 24.2,
  "pressure_hpa": 1013.5,
  "dht_temperature_c": 24.0,
  "humidity_pct": 58.0,
  "bmp280_ok": true,
  "dht11_ok": true
}
```

| Field | Type | Units | Description |
|-------|------|-------|-------------|
| `type` | string | — | Always `"telemetry"` |
| `timestamp_ms` | integer | ms | ESP32 uptime milliseconds |
| `mode` | string | — | `"ACTIVE"` or `"STANDBY"` |
| `bmp_temperature_c` | float | °C | BMP280 temperature |
| `pressure_hpa` | float | hPa | Barometric pressure |
| `dht_temperature_c` | float | °C | DHT11 temperature |
| `humidity_pct` | float | % | Relative humidity |
| `bmp280_ok` | boolean | — | BMP280 communication OK |
| `dht11_ok` | boolean | — | DHT11 communication OK |

---

### 2. Status Response (To GET_STATUS Command)

```json
{
  "type": "status",
  "timestamp_ms": 1234567890,
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

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"status"` |
| `timestamp_ms` | integer | ESP32 uptime milliseconds |
| `mode` | string | Current mode: `"ACTIVE"` or `"STANDBY"` |
| `sensors_polling` | boolean | Whether sensor task is running |
| `bmp280_ok` | boolean | BMP280 communication OK |
| `dht11_ok` | boolean | DHT11 communication OK |
| `bmp280_state` | string | `"OK"`, `"STALE"`, `"FAILED"` |
| `dht11_state` | string | `"OK"`, `"STALE"`, `"FAILED"` |
| `firmware` | string | Firmware version (e.g., `"1.5.0"`) |
| `request_id` | integer | Matches requesting command |

---

### 3. Mode Status Response (To SET_ACTIVE/SET_STANDBY)

```json
{
  "type": "mode_status",
  "mode": "ACTIVE",
  "request_id": 43
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"mode_status"` |
| `mode` | string | New mode: `"ACTIVE"` or `"STANDBY"` |
| `request_id` | integer | Matches requesting command |

---

### 4. Command Acknowledgment

```json
{
  "type": "command_ack",
  "command": "SET_ACTIVE",
  "ok": true,
  "accepted": true,
  "message": "Lander active, sensors polling",
  "request_id": 44
}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"command_ack"` |
| `command` | string | Echo of command: `"GET_STATUS"`, `"SET_ACTIVE"`, `"SET_STANDBY"` |
| `ok` | boolean | Overall success |
| `accepted` | boolean | Command accepted (vs rejected) |
| `message` | string | Human-readable result |
| `request_id` | integer | Matches requesting command |

---

## Pi → ESP32 Messages

### 1. Command Request

```json
{
  "command": "GET_STATUS",
  "request_id": 42
}
```

```json
{
  "command": "SET_ACTIVE",
  "request_id": 43
}
```

```json
{
  "command": "SET_STANDBY",
  "request_id": 44
}
```

| Field | Type | Description |
|-------|------|-------------|
| `command` | string | `"GET_STATUS"`, `"SET_ACTIVE"`, or `"SET_STANDBY"` |
| `request_id` | integer | Monotonic counter allocated by Pi |

**Command Semantics:**
- `GET_STATUS` — Request full status response (type: `status`)
- `SET_ACTIVE` — Enable sensor polling, 1 Hz telemetry, green LED ON
- `SET_STANDBY` — Disable sensor polling, 0.2 Hz telemetry, green LED OFF

---

### 2. Mission Display Forwarding (Rover Data)

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

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"mission_display"` |
| `device` | string | `"rover"` or `"drone"` |
| `connected` | boolean | Whether device is online |
| `data` | object | Device-specific payload |

**Rover Data Fields:**
| Field | Type | Units | Description |
|-------|------|-------|-------------|
| `distance` | float | cm | HC-SR04 distance |
| `pitch` | float | ° | MPU6050 pitch |
| `roll` | float | ° | MPU6050 roll |
| `cmd` | string | — | Current command: F/B/L/R/S |
| `mode` | string | — | M (Manual) or A (Auto) |

---

### 3. Mission Display Forwarding (Drone Data)

```json
{
  "type": "mission_display",
  "device": "drone",
  "connected": true,
  "data": {
    "flight_status": "CRUISING",
    "latitude": 12.9716,
    "longitude": 77.5946
  }
}
```

**Drone Data Fields:**
| Field | Type | Units | Description |
|-------|------|-------|-------------|
| `flight_status` | string | — | e.g., `"CRUISING"`, `"HOVER"`, `"RTL"` |
| `latitude` | float | ° | GPS latitude |
| `longitude` | float | ° | GPS longitude |

---

## Rate Limiting & Heartbeats (Mission Display)

The Pi Gateway rate-limits `mission_display` messages to avoid flooding the LCD:

| Device | Max Rate | Heartbeat Interval |
|--------|----------|-------------------|
| Rover | 4 Hz | 2.5 seconds |
| Drone | 2 Hz | 2.5 seconds |

- **Heartbeat**: If no new data for `heartbeat_interval`, Pi re-sends last known data with `connected: false` after timeout
- **LCD Pages**: Rover → Page 3, Drone → Page 4 (4s rotation with system pages)

---

## Request Correlation

- Pi Gateway allocates monotonically increasing `request_id` (1, 2, 3...)
- ESP32 echoes `request_id` in response
- Pi matches response to pending request
- Timeout: 5 seconds (then marks command as failed)

---

## Staleness & Connection States

### ESP32 Side (Reported in telemetry/status)
| State | Condition |
|-------|-----------|
| `OK` | Sensor read successful |
| `STALE` | No sensor update for 5s |
| `FAILED` | Sensor communication failed |

### Pi Gateway Side (Connection State)
| State | Condition |
|-------|-----------|
| `CONNECTED` | TCP established, recent telemetry |
| `STALE` | No telemetry for 3 seconds |
| `OFFLINE` | No telemetry for 10 seconds, or TCP disconnected |

---

## Error Handling

| Scenario | ESP32 Behavior | Pi Gateway Behavior |
|----------|----------------|---------------------|
| TCP disconnect | Reconnect every 1s | Accept new connection, close old |
| Invalid JSON | Log, continue | Log, ignore line |
| Unknown command | Send `command_ack` with `ok:false` | N/A |
| Command timeout | N/A | Mark failed, notify backend |
| Sensor failure | Set `*_ok: false`, blink red LED | Reflect in `/api/lander/status` |

---

## Implementation Notes (ESP32)

### TX Buffer Management
```cpp
// Max 768 bytes per line
StaticJsonDocument<768> doc;
// ... populate ...
serializeJson(doc, tcpClient);
tcpClient.println();  // Newline delimiter
```

### RX Buffer Management (Pi Gateway)
```python
# Max 4096 bytes per line
async def read_line(self) -> str:
    line = await self.reader.readline()
    if len(line) > 4096:
        raise ValueError("Line too long")
    return line.decode('utf-8').strip()
```

---

## Example Full Session

```
# Pi starts listening on 0.0.0.0:5006

# ESP32 connects
> {"command":"GET_STATUS","request_id":1}
< {"type":"status","mode":"STANDBY","sensors_polling":false,"bmp280_ok":true,"dht11_ok":true,"bmp280_state":"OK","dht11_state":"OK","firmware":"1.5.0","request_id":1}

# Dashboard user clicks "Activate"
> {"command":"SET_ACTIVE","request_id":2}
< {"type":"mode_status","mode":"ACTIVE","request_id":2}
< {"type":"command_ack","command":"SET_ACTIVE","ok":true,"accepted":true,"message":"Lander active, sensors polling","request_id":2}

# Telemetry starts (~1 Hz)
< {"type":"telemetry","timestamp_ms":123456,"mode":"ACTIVE","bmp_temperature_c":24.2,"pressure_hpa":1013.5,"dht_temperature_c":24.0,"humidity_pct":58.0,"bmp280_ok":true,"dht11_ok":true}
< {"type":"telemetry","timestamp_ms":124456,"mode":"ACTIVE","bmp_temperature_c":24.3,"pressure_hpa":1013.4,"dht_temperature_c":24.1,"humidity_pct":57.8,"bmp280_ok":true,"dht11_ok":true}

# Rover data arrives at Pi, forwarded to Lander LCD
> {"type":"mission_display","device":"rover","connected":true,"data":{"distance":145.0,"pitch":12.4,"roll":-3.2,"cmd":"F","mode":"M"}}

# Drone data arrives at Pi, forwarded to Lander LCD
> {"type":"mission_display","device":"drone","connected":true,"data":{"flight_status":"CRUISING","latitude":12.9716,"longitude":77.5946}}

# Dashboard user clicks "Standby"
> {"command":"SET_STANDBY","request_id":3}
< {"type":"mode_status","mode":"STANDBY","request_id":3}
< {"type":"command_ack","command":"SET_STANDBY","ok":true,"accepted":true,"message":"Lander standby","request_id":3}

# Telemetry slows to ~0.2 Hz
< {"type":"telemetry","timestamp_ms":130456,"mode":"STANDBY","bmp_temperature_c":24.2,"pressure_hpa":1013.5,"dht_temperature_c":24.0,"humidity_pct":58.0,"bmp280_ok":true,"dht11_ok":true}
```

---

## JSON Schema (Reference)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "oneOf": [
    {"$ref": "#/definitions/telemetry"},
    {"$ref": "#/definitions/status"},
    {"$ref": "#/definitions/mode_status"},
    {"$ref": "#/definitions/command_ack"},
    {"$ref": "#/definitions/command_request"},
    {"$ref": "#/definitions/mission_display_rover"},
    {"$ref": "#/definitions/mission_display_drone"}
  ],
  "definitions": {
    "telemetry": {
      "type": "object",
      "required": ["type", "timestamp_ms", "mode", "bmp_temperature_c", "pressure_hpa", "dht_temperature_c", "humidity_pct", "bmp280_ok", "dht11_ok"],
      "properties": {
        "type": {"const": "telemetry"},
        "timestamp_ms": {"type": "integer", "minimum": 0},
        "mode": {"enum": ["ACTIVE", "STANDBY"]},
        "bmp_temperature_c": {"type": "number"},
        "pressure_hpa": {"type": "number"},
        "dht_temperature_c": {"type": "number"},
        "humidity_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "bmp280_ok": {"type": "boolean"},
        "dht11_ok": {"type": "boolean"}
      }
    },
    "status": {
      "type": "object",
      "required": ["type", "timestamp_ms", "mode", "sensors_polling", "bmp280_ok", "dht11_ok", "bmp280_state", "dht11_state", "firmware", "request_id"],
      "properties": {
        "type": {"const": "status"},
        "timestamp_ms": {"type": "integer", "minimum": 0},
        "mode": {"enum": ["ACTIVE", "STANDBY"]},
        "sensors_polling": {"type": "boolean"},
        "bmp280_ok": {"type": "boolean"},
        "dht11_ok": {"type": "boolean"},
        "bmp280_state": {"enum": ["OK", "STALE", "FAILED"]},
        "dht11_state": {"enum": ["OK", "STALE", "FAILED"]},
        "firmware": {"type": "string"},
        "request_id": {"type": "integer", "minimum": 1}
      }
    },
    "mode_status": {
      "type": "object",
      "required": ["type", "mode", "request_id"],
      "properties": {
        "type": {"const": "mode_status"},
        "mode": {"enum": ["ACTIVE", "STANDBY"]},
        "request_id": {"type": "integer", "minimum": 1}
      }
    },
    "command_ack": {
      "type": "object",
      "required": ["type", "command", "ok", "accepted", "message", "request_id"],
      "properties": {
        "type": {"const": "command_ack"},
        "command": {"enum": ["GET_STATUS", "SET_ACTIVE", "SET_STANDBY"]},
        "ok": {"type": "boolean"},
        "accepted": {"type": "boolean"},
        "message": {"type": "string"},
        "request_id": {"type": "integer", "minimum": 1}
      }
    },
    "command_request": {
      "type": "object",
      "required": ["command", "request_id"],
      "properties": {
        "command": {"enum": ["GET_STATUS", "SET_ACTIVE", "SET_STANDBY"]},
        "request_id": {"type": "integer", "minimum": 1}
      }
    },
    "mission_display_rover": {
      "type": "object",
      "required": ["type", "device", "connected", "data"],
      "properties": {
        "type": {"const": "mission_display"},
        "device": {"const": "rover"},
        "connected": {"type": "boolean"},
        "data": {
          "type": "object",
          "required": ["distance", "pitch", "roll", "cmd", "mode"],
          "properties": {
            "distance": {"type": "number", "minimum": 0, "maximum": 10000},
            "pitch": {"type": "number", "minimum": -90, "maximum": 90},
            "roll": {"type": "number", "minimum": -90, "maximum": 90},
            "cmd": {"enum": ["F", "B", "L", "R", "S"]},
            "mode": {"enum": ["M", "A"]}
          }
        }
      }
    },
    "mission_display_drone": {
      "type": "object",
      "required": ["type", "device", "connected", "data"],
      "properties": {
        "type": {"const": "mission_display"},
        "device": {"const": "drone"},
        "connected": {"type": "boolean"},
        "data": {
          "type": "object",
          "required": ["flight_status", "latitude", "longitude"],
          "properties": {
            "flight_status": {"type": "string", "minLength": 1},
            "latitude": {"type": "number", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "minimum": -180, "maximum": 180}
          }
        }
      }
    }
  }
}
```

---

## Related Documents

- [Communication Overview](communication-overview.md) — Protocol summary
- [Network Architecture](architecture/network-architecture.md) — Port assignments
- [Data Flow](architecture/data-flow.md) — Telemetry flow diagrams
- [Software Architecture](architecture/software-architecture.md) — LanderManager implementation