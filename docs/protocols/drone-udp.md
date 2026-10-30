# Drone UDP Protocol (Port 5007)

## Overview

The Drone telemetry is sent directly from the Drone ESP32 flight controller to the Raspberry Pi Gateway via UDP.

- **Port**: 5007
- **Initiator**: Drone ESP32 → Pi Gateway (server)
- **Format**: JSON (UTF-8)
- **Framing**: Single UDP datagram = one JSON object
- **Max Packet**: 4096 bytes
- **Rate**: ~2 Hz (configurable)
- **Staleness**: OFFLINE after 10 seconds silence
- **Sequence**: Monotonic integer with RFC 1982 rollover handling

---

## Packet Schema

```json
{
  "device_id": "esp32-drone",
  "sequence": 123,
  "timestamp_ms": 1234567890,
  "flight_status": "CRUISING",
  "orientation": {
    "roll": 1.2,
    "pitch": -0.5,
    "yaw": 180.0
  },
  "environment": {
    "temperature_c": 26.8,
    "pressure_hpa": 1013.2,
    "humidity_pct": 48.0
  },
  "gps": {
    "latitude": 12.9716,
    "longitude": 77.5946,
    "altitude_m": 50.0
  },
  "battery": {
    "voltage_v": 11.1,
    "percentage": 85.0
  }
}
```

---

## Field Specifications

### Root Fields

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `device_id` | string | Yes | Non-empty, expected "esp32-drone" | Device identifier |
| `sequence` | integer | Yes | ≥0, monotonic (RFC 1982) | Packet sequence number |
| `timestamp_ms` | integer | Yes | ≥0, epoch milliseconds | Sensor timestamp |
| `flight_status` | string | Yes | Non-empty | Flight mode string |
| `orientation` | object | Yes | See below | Roll, Pitch, Yaw |
| `environment` | object | Yes | See below | Temp, Pressure, Humidity |
| `gps` | object | Yes | See below | Lat, Lon, Alt |
| `battery` | object | Yes | See below | Voltage, Percentage |

### Orientation Object

| Field | Type | Units | Range | Description |
|-------|------|-------|-------|-------------|
| `roll` | float | degrees | -180 to +180 | Roll angle (positive = right wing down) |
| `pitch` | float | degrees | -90 to +90 | Pitch angle (positive = nose up) |
| `yaw` | float | degrees | 0 to 360 | Yaw/heading (0 = North) |

### Environment Object

| Field | Type | Units | Range | Description |
|-------|------|-------|-------|-------------|
| `temperature_c` | float | °C | -40 to +85 | Ambient temperature |
| `pressure_hpa` | float | hPa | 300–1100 | Barometric pressure |
| `humidity_pct` | float | % | 0–100 | Relative humidity (BME280 only) |

### GPS Object

| Field | Type | Units | Range | Description |
|-------|------|-------|-------|-------------|
| `latitude` | float | degrees | -90 to +90 | GPS latitude (WGS84) |
| `longitude` | float | degrees | -180 to +180 | GPS longitude (WGS84) |
| `altitude_m` | float | meters | -1000 to +10000 | GPS altitude (MSL) |

### Battery Object

| Field | Type | Units | Range | Description |
|-------|------|-------|-------|-------------|
| `voltage_v` | float | Volts | 0–25 | Pack voltage |
| `percentage` | float | % | 0–100 | Estimated remaining capacity |

---

## Flight Status Values

| Status | Description |
|--------|-------------|
| `DISARMED` | Motors off, safe state |
| `ARMED` | Motors armed, ready for takeoff |
| `TAKEOFF` | Ascending to target altitude |
| `HOVER` | Holding position/altitude |
| `CRUISING` | Waypoint navigation |
| `RTL` | Return to launch |
| `LANDING` | Descending to land |
| `LANDED` | On ground, disarming |
| `FAILSAFE` | Failsafe triggered (lost link, low battery) |
| `CRITICAL` | Critical battery/emergency |

*Extensible — unknown statuses are accepted but logged*

---

## Sequence Number Handling (RFC 1982)

The drone includes a monotonically increasing `sequence` number for:
- Packet ordering
- Duplicate detection
- Loss detection

### Rollover Handling

The Pi Gateway implements RFC 1982 "Serial Number Arithmetic" for sequence comparison:

```python
# RFC 1982: Serial Number Arithmetic
# For 32-bit sequence space: 2^31 = 2147483648

def is_newer(seq_new: int, seq_old: int, bits: int = 32) -> bool:
    """Return True if seq_new is newer than seq_old per RFC 1982."""
    max_seq = 1 << bits
    half = max_seq >> 1
    
    diff = (seq_new - seq_old) & (max_seq - 1)
    return 0 < diff < half

# Usage in DroneUDPReceiver:
def on_packet(self, packet: DronePacket) -> bool:
    if self._last_sequence is not None:
        if not is_newer(packet.sequence, self._last_sequence):
            # Duplicate or stale packet - reject
            self._stats.rejected_duplicates += 1
            return False
    
    self._last_sequence = packet.sequence
    self._last_packet_time = time.time()
    self._last_valid_packet = packet
    return True
```

### Sequence Space

| Bits | Max Value | Half Space (Rollover Threshold) |
|------|-----------|----------------------------------|
| 16-bit | 65,535 | 32,768 |
| 32-bit | 4,294,967,295 | 2,147,483,648 |

The gateway auto-detects 16-bit vs 32-bit based on value range.

---

## Validation Implementation (Pi Gateway)

```python
# From gateway/drone_udp.py
def parse_drone_packet(data: bytes) -> DronePacket:
    """Parse and validate drone JSON telemetry packet."""
    try:
        obj = json.loads(data.decode('utf-8'))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    
    # Required fields
    required = ['device_id', 'sequence', 'timestamp_ms', 'flight_status',
                'orientation', 'environment', 'gps', 'battery']
    for field in required:
        if field not in obj:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate device_id
    device_id = obj['device_id']
    if not isinstance(device_id, str) or not device_id:
        raise ValueError("device_id must be non-empty string")
    
    # Validate sequence
    sequence = obj['sequence']
    if not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be non-negative integer")
    
    # Validate timestamp
    timestamp_ms = obj['timestamp_ms']
    if not isinstance(timestamp_ms, int) or timestamp_ms < 0:
        raise ValueError("timestamp_ms must be non-negative integer")
    
    # Validate flight_status
    flight_status = obj['flight_status']
    if not isinstance(flight_status, str) or not flight_status:
        raise ValueError("flight_status must be non-empty string")
    
    # Validate orientation
    orient = obj['orientation']
    if not isinstance(orient, dict):
        raise ValueError("orientation must be object")
    roll = float(orient.get('roll', 0))
    pitch = float(orient.get('pitch', 0))
    yaw = float(orient.get('yaw', 0))
    if not (-180 <= roll <= 180):
        raise ValueError(f"Roll out of range: {roll}")
    if not (-90 <= pitch <= 90):
        raise ValueError(f"Pitch out of range: {pitch}")
    if not (0 <= yaw <= 360):
        raise ValueError(f"Yaw out of range: {yaw}")
    
    # Validate environment
    env = obj['environment']
    if not isinstance(env, dict):
        raise ValueError("environment must be object")
    temp = float(env.get('temperature_c', 0))
    pressure = float(env.get('pressure_hpa', 0))
    humidity = float(env.get('humidity_pct', 0))
    if not (-40 <= temp <= 85):
        raise ValueError(f"Temperature out of range: {temp}")
    if not (300 <= pressure <= 1100):
        raise ValueError(f"Pressure out of range: {pressure}")
    if not (0 <= humidity <= 100):
        raise ValueError(f"Humidity out of range: {humidity}")
    
    # Validate GPS
    gps = obj['gps']
    if not isinstance(gps, dict):
        raise ValueError("gps must be object")
    lat = float(gps.get('latitude', 0))
    lon = float(gps.get('longitude', 0))
    alt = float(gps.get('altitude_m', 0))
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitude out of range: {lat}")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitude out of range: {lon}")
    if not (-1000 <= alt <= 10000):
        raise ValueError(f"Altitude out of range: {alt}")
    
    # Validate battery
    bat = obj['battery']
    if not isinstance(bat, dict):
        raise ValueError("battery must be object")
    voltage = float(bat.get('voltage_v', 0))
    pct = float(bat.get('percentage', 0))
    if not (0 <= voltage <= 25):
        raise ValueError(f"Voltage out of range: {voltage}")
    if not (0 <= pct <= 100):
        raise ValueError(f"Percentage out of range: {pct}")
    
    return DronePacket(
        device_id=device_id,
        sequence=sequence,
        timestamp_ms=timestamp_ms,
        flight_status=flight_status,
        orientation={'roll': roll, 'pitch': pitch, 'yaw': yaw},
        environment={'temperature_c': temp, 'pressure_hpa': pressure, 'humidity_pct': humidity},
        gps={'latitude': lat, 'longitude': lon, 'altitude_m': alt},
        battery={'voltage_v': voltage, 'percentage': pct}
    )
```

---

## Error Handling

| Error Condition | Pi Gateway Action |
|-----------------|-------------------|
| Invalid UTF-8 | Log warning, drop packet |
| Invalid JSON | Log warning, drop packet |
| Missing required field | Log warning, drop packet |
| Wrong type for field | Log warning, drop packet |
| Value out of range | Log warning, drop packet |
| Sequence not newer (RFC 1982) | Log warning, drop packet, increment duplicate counter |
| Valid packet, sequence OK | Update state, reset staleness timer |

**Critical**: Rejected packets do NOT overwrite the last valid state. The last known good telemetry is retained until a valid packet arrives or staleness timeout occurs.

---

## Staleness Monitoring

```python
class DroneUDPReceiver:
    def __init__(self):
        self._last_packet_time = 0
        self._last_valid_packet: Optional[DronePacket] = None
        self._last_sequence: Optional[int] = None
        self._staleness_threshold = 10.0  # seconds
    
    def on_packet(self, packet: DronePacket):
        self._last_packet_time = time.time()
        self._last_valid_packet = packet
    
    def get_status(self) -> DeviceStatus:
        age = time.time() - self._last_packet_time
        if age > self._staleness_threshold:
            return DeviceStatus.OFFLINE
        elif self._last_valid_packet is None:
            return DeviceStatus.OFFLINE
        return DeviceStatus.ONLINE
```

| State | Condition |
|-------|-----------|
| `ONLINE` | Valid packet received within 10s |
| `OFFLINE` | No valid packet for >10s, or never received |

---

## Data Flow

```
Drone ESP32                          Pi Gateway                     Backend
───────────                          ──────────                     ────────
  │                                    │                              │
  │ GPS + IMU + ENV + Battery          │                              │
  │ ~10-50 Hz sensor fusion            │                              │
  │                                    │                              │
  │ UDP 5007 JSON                      │                              │
  │ {seq:123, ts:1234567890, ─────────►│                              │
  │  flight_status:"CRUISING",         │                              │
  │  orientation:{...},                │                              │
  │  environment:{...},                │                              │
  │  gps:{...},                        │                              │
  │  battery:{...}}                    │                              │
  │                                    │                              │
  │              (DroneUDPReceiver)    │                              │
  │              - JSON parse          │                              │
  │              - Schema validation   │                              │
  │              - RFC 1982 sequence   │                              │
  │              - Staleness 10s       │                              │
  │                                    │                              │
  │                                    │── HTTP /api/drone/status ──►│ (poll 0.5s)
  │                                    │                              │
  │                                    │── WS /ws/telemetry ────────►│ (push)
  │                                    │                              │
  │                                    │              (DroneRunner)   │
  │                                    │              - HTTP poll 0.5s│
  │                                    │              - Normalize     │
  │                                    │                              │
  │                                    │                              │── TelemetryService
  │                                    │                              │      - SQLite store
  │                                    │                              │      - WS broadcast
```

---

## Pi Gateway API Response (`/api/drone/status`)

```json
{
  "connected": true,
  "last_update": 1234567890.123,
  "data": {
    "device_id": "esp32-drone",
    "sequence": 123,
    "timestamp_ms": 1234567890,
    "flight_status": "CRUISING",
    "orientation": {"roll": 1.2, "pitch": -0.5, "yaw": 180.0},
    "environment": {"temperature_c": 26.8, "pressure_hpa": 1013.2, "humidity_pct": 48.0},
    "gps": {"latitude": 12.9716, "longitude": 77.5946, "altitude_m": 50.0},
    "battery": {"voltage_v": 11.1, "percentage": 85.0}
  },
  "staleness": 0.2
}
```

---

## WebSocket Broadcast (`/ws/telemetry`)

```json
{
  "type": "drone_telemetry",
  "source": "network",
  "data": {
    "device_id": "esp32-drone",
    "sequence": 123,
    "timestamp_ms": 1234567890,
    "flight_status": "CRUISING",
    "orientation": {"roll": 1.2, "pitch": -0.5, "yaw": 180.0},
    "environment": {"temperature_c": 26.8, "pressure_hpa": 1013.2, "humidity_pct": 48.0},
    "gps": {"latitude": 12.9716, "longitude": 77.5946, "altitude_m": 50.0},
    "battery": {"voltage_v": 11.1, "percentage": 85.0}
  },
  "timestamp": 1234567890123
}
```

---

## ESP32 Implementation Notes

### JSON Serialization (ArduinoJson)

```cpp
#include <ArduinoJson.h>

void sendTelemetry() {
    StaticJsonDocument<1024> doc;
    
    doc["device_id"] = "esp32-drone";
    doc["sequence"] = sequence++;
    doc["timestamp_ms"] = millis();
    doc["flight_status"] = flightStatus;  // "CRUISING", etc.
    
    JsonObject orient = doc.createNestedObject("orientation");
    orient["roll"] = roll;
    orient["pitch"] = pitch;
    orient["yaw"] = yaw;
    
    JsonObject env = doc.createNestedObject("environment");
    env["temperature_c"] = temperature;
    env["pressure_hpa"] = pressure;
    env["humidity_pct"] = humidity;
    
    JsonObject gps = doc.createNestedObject("gps");
    gps["latitude"] = latitude;
    gps["longitude"] = longitude;
    gps["altitude_m"] = altitude;
    
    JsonObject bat = doc.createNestedObject("battery");
    bat["voltage_v"] = batteryVoltage;
    bat["percentage"] = batteryPercentage;
    
    String output;
    serializeJson(doc, output);
    
    udp.beginPacket(gatewayIP, 5007);
    udp.write((const uint8_t*)output.c_str(), output.length());
    udp.endPacket();
}
```

### Sequence Counter

```cpp
uint32_t sequence = 0;  // 32-bit, wraps at 4.29B

void sendTelemetry() {
    // ... populate doc ...
    doc["sequence"] = sequence++;
    // ...
}
```

---

## Testing

### Unit Test Vectors

```python
# Valid packet
valid_packet = {
    "device_id": "esp32-drone",
    "sequence": 123,
    "timestamp_ms": 1234567890,
    "flight_status": "CRUISING",
    "orientation": {"roll": 1.2, "pitch": -0.5, "yaw": 180.0},
    "environment": {"temperature_c": 26.8, "pressure_hpa": 1013.2, "humidity_pct": 48.0},
    "gps": {"latitude": 12.9716, "longitude": 77.5946, "altitude_m": 50.0},
    "battery": {"voltage_v": 11.1, "percentage": 85.0}
}

# Sequence rollover test (32-bit)
assert is_newer(0, 4294967295) == True      # Rollover
assert is_newer(100, 4294967200) == True    # Near rollover
assert is_newer(4294967295, 100) == False   # Old packet
assert is_newer(123, 123) == False          # Duplicate
```

### Simulator Test

```python
async def test_drone_simulator_generates_valid_data():
    sim = DroneSimulator()
    telemetry = await sim.generate()
    
    assert telemetry.device_id == "esp32-drone"
    assert telemetry.sequence >= 0
    assert telemetry.timestamp_ms > 0
    assert telemetry.flight_status in {"DISARMED", "ARMED", "TAKEOFF", "HOVER", 
                                        "CRUISING", "RTL", "LANDING", "LANDED", 
                                        "FAILSAFE", "CRITICAL"}
    assert -180 <= telemetry.orientation.roll <= 180
    assert -90 <= telemetry.orientation.pitch <= 90
    assert 0 <= telemetry.orientation.yaw <= 360
    assert -40 <= telemetry.environment.temperature_c <= 85
    assert 300 <= telemetry.environment.pressure_hpa <= 1100
    assert 0 <= telemetry.environment.humidity_pct <= 100
    assert -90 <= telemetry.gps.latitude <= 90
    assert -180 <= telemetry.gps.longitude <= 180
    assert -1000 <= telemetry.gps.altitude_m <= 10000
    assert 0 <= telemetry.battery.voltage_v <= 25
    assert 0 <= telemetry.battery.percentage <= 100
```

---

## JSON Schema (Reference)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Drone UDP Telemetry",
  "type": "object",
  "required": ["device_id", "sequence", "timestamp_ms", "flight_status",
               "orientation", "environment", "gps", "battery"],
  "properties": {
    "device_id": {
      "type": "string",
      "minLength": 1,
      "description": "Device identifier"
    },
    "sequence": {
      "type": "integer",
      "minimum": 0,
      "description": "Monotonic sequence number (RFC 1982)"
    },
    "timestamp_ms": {
      "type": "integer",
      "minimum": 0,
      "description": "Epoch timestamp in milliseconds"
    },
    "flight_status": {
      "type": "string",
      "minLength": 1,
      "description": "Flight mode status"
    },
    "orientation": {
      "type": "object",
      "required": ["roll", "pitch", "yaw"],
      "properties": {
        "roll": {"type": "number", "minimum": -180, "maximum": 180},
        "pitch": {"type": "number", "minimum": -90, "maximum": 90},
        "yaw": {"type": "number", "minimum": 0, "maximum": 360}
      }
    },
    "environment": {
      "type": "object",
      "required": ["temperature_c", "pressure_hpa", "humidity_pct"],
      "properties": {
        "temperature_c": {"type": "number", "minimum": -40, "maximum": 85},
        "pressure_hpa": {"type": "number", "minimum": 300, "maximum": 1100},
        "humidity_pct": {"type": "number", "minimum": 0, "maximum": 100}
      }
    },
    "gps": {
      "type": "object",
      "required": ["latitude", "longitude", "altitude_m"],
      "properties": {
        "latitude": {"type": "number", "minimum": -90, "maximum": 90},
        "longitude": {"type": "number", "minimum": -180, "maximum": 180},
        "altitude_m": {"type": "number", "minimum": -1000, "maximum": 10000}
      }
    },
    "battery": {
      "type": "object",
      "required": ["voltage_v", "percentage"],
      "properties": {
        "voltage_v": {"type": "number", "minimum": 0, "maximum": 25},
        "percentage": {"type": "number", "minimum": 0, "maximum": 100}
      }
    }
  },
  "additionalProperties": false
}
```

---

## Related Documents

- [Communication Overview](communication-overview.md) — Protocol summary
- [Network Architecture](architecture/network-architecture.md) — Port assignments
- [Drone Hardware](hardware/drone.md) — Sensor specs and flight controller
- [Drone Wiring](wiring/drone-wiring.md) — Wiring diagrams
- [Data Flow](architecture/data-flow.md) — Drone telemetry flow