# Rover UDP Protocol (Port 5005)

## Overview

The Rover telemetry is forwarded from the Rover Laptop (Windows Tkinter GUI) to the Raspberry Pi Gateway via UDP.

- **Port**: 5005
- **Initiator**: Rover Laptop → Pi Gateway (server)
- **Format**: ASCII key:value pairs, comma-separated
- **Framing**: Single UDP datagram = one packet
- **Encoding**: ASCII
- **Rate**: ~5 Hz (forwarded from ~50 Hz serial)
- **Staleness**: OFFLINE after 2 seconds silence

---

## Packet Format

```
DIST:<float>,PITCH:<float>,ROLL:<float>,CMD:<F|B|L|R|S>,MODE:<M|A>
```

### Example Packets

```
DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
DIST:143.2,PITCH:12.1,ROLL:-3.5,CMD:F,MODE:M
DIST:141.8,PITCH:11.8,ROLL:-3.7,CMD:L,MODE:M
DIST:140.5,PITCH:11.5,ROLL:-4.0,CMD:L,MODE:M
DIST:139.1,PITCH:11.2,ROLL:-4.2,CMD:F,MODE:M
DIST:138.0,PITCH:10.9,ROLL:-4.5,CMD:S,MODE:A
DIST:137.5,PITCH:10.7,ROLL:-4.6,CMD:S,MODE:A
```

---

## Field Specifications

| Field | Key | Type | Range | Required | Description |
|-------|-----|------|-------|----------|-------------|
| Distance | `DIST` | float | 0–10000 | Yes | HC-SR04 distance in cm |
| Pitch | `PITCH` | float | -90 to +90 | Yes | MPU6050 pitch angle in degrees |
| Roll | `ROLL` | float | -90 to +90 | Yes | MPU6050 roll angle in degrees |
| Command | `CMD` | enum | F,B,L,R,S | Yes | Current rover command |
| Mode | `MODE` | enum | M,A | Yes | Rover mode: Manual/Autonomous |

### Command Enum Values

| Value | Meaning |
|-------|---------|
| `F` | Forward |
| `B` | Backward |
| `L` | Left turn |
| `R` | Right turn |
| `S` | Stop |

### Mode Enum Values

| Value | Meaning |
|-------|---------|
| `M` | Manual (human controlled) |
| `A` | Autonomous |

---

## Parsing Rules

1. **Split by comma** → 5 key:value pairs
2. **Split each by first colon** → key and value
3. **Trim whitespace** from key and value
4. **Validate all 5 keys present**: DIST, PITCH, ROLL, CMD, MODE
5. **Parse numeric values** as float
6. **Validate enums** against allowed values
7. **Validate ranges** for numeric fields

---

## Validation Implementation (Pi Gateway)

```python
# From gateway/rover_udp.py
def parse_rover_packet(data: bytes) -> RoverPacket:
    """Parse ASCII packet: DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M"""
    text = data.decode('ascii').strip()
    parts = text.split(',')
    
    if len(parts) != 5:
        raise ValueError(f"Expected 5 fields, got {len(parts)}")
    
    fields = {}
    for part in parts:
        key, value = part.split(':', 1)
        fields[key.strip()] = value.strip()
    
    # Required fields
    required = ['DIST', 'PITCH', 'ROLL', 'CMD', 'MODE']
    for req in required:
        if req not in fields:
            raise ValueError(f"Missing field: {req}")
    
    # Parse and validate
    distance = float(fields['DIST'])
    pitch = float(fields['PITCH'])
    roll = float(fields['ROLL'])
    cmd = fields['CMD']
    mode = fields['MODE']
    
    # Range checks
    if not (0 <= distance <= 10000):
        raise ValueError(f"Distance out of range: {distance}")
    if not (-90 <= pitch <= 90):
        raise ValueError(f"Pitch out of range: {pitch}")
    if not (-90 <= roll <= 90):
        raise ValueError(f"Roll out of range: {roll}")
    if cmd not in {'F', 'B', 'L', 'R', 'S'}:
        raise ValueError(f"Invalid command: {cmd}")
    if mode not in {'M', 'A'}:
        raise ValueError(f"Invalid mode: {mode}")
    
    return RoverPacket(
        distance_cm=distance,
        pitch_deg=pitch,
        roll_deg=roll,
        command=cmd,
        mode=mode
    )
```

---

## Error Handling

| Error Condition | Pi Gateway Action |
|-----------------|-------------------|
| Invalid ASCII | Log warning, drop packet |
| Not 5 fields | Log warning, drop packet |
| Missing field | Log warning, drop packet |
| Non-numeric DIST/PITCH/ROLL | Log warning, drop packet |
| Value out of range | Log warning, drop packet |
| Invalid CMD enum | Log warning, drop packet |
| Invalid MODE enum | Log warning, drop packet |
| Valid packet | Update state, reset staleness timer |

**Important**: Invalid packets do NOT overwrite the last valid state. The last known good values are retained until a valid packet arrives or staleness timeout occurs.

---

## Staleness Monitoring

```python
class RoverUDPReceiver:
    def __init__(self):
        self._last_packet_time = 0
        self._last_valid_packet: Optional[RoverPacket] = None
        self._staleness_threshold = 2.0  # seconds
    
    def on_packet(self, packet: RoverPacket):
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
| `ONLINE` | Valid packet received within 2s |
| `OFFLINE` | No valid packet for >2s, or never received |

---

## Data Flow

```
Rover MCU                          Rover Laptop                    Pi Gateway
──────────                          ───────────                    ──────────
  │                                    │                             │
  │ HC-SR04 + MPU6050                  │                             │
  │ ~50 Hz sampling                    │                             │
  │                                    │                             │
  │ Serial 9600 baud                   │                             │
  │ "DIST:145,PITCH:12.4,             │                             │
  │  ROLL:-3.2,CMD:F,MODE:M" ────────►│                             │
  │                                    │                             │
  │                    (Tkinter GUI)   │                             │
  │                    - Parse COM     │                             │
  │                    - Validate      │                             │
  │                                    │                             │
  │                    UDP 5005        │                             │
  │                    "DIST:145,..." ─┼──────────────────────────►│
  │                                    │                             │
  │                                    │              (RoverUDPReceiver)
  │                                    │              - Parse ASCII
  │                                    │              - Validate 5 fields
  │                                    │              - Range checks
  │                                    │              - Enum checks
  │                                    │                             │
  │                                    │◄─── /api/rover/status ─────┤ (poll 0.2s)
  │                                    │                             │
  │                                    │◄─── WS /ws/telemetry ──────┤ (push)
```

---

## Pi Gateway API Response (`/api/rover/status`)

```json
{
  "connected": true,
  "last_update": 1234567890.123,
  "data": {
    "distance_cm": 145.0,
    "pitch_deg": 12.4,
    "roll_deg": -3.2,
    "command": "F",
    "mode": "M"
  },
  "staleness": 0.05
}
```

| Field | Type | Description |
|-------|------|-------------|
| `connected` | boolean | `ONLINE`/`OFFLINE` status |
| `last_update` | float | Unix timestamp of last valid packet |
| `data` | object | Last valid parsed packet (null if OFFLINE) |
| `staleness` | float | Seconds since last packet |

---

## WebSocket Broadcast (`/ws/telemetry`)

```json
{
  "type": "rover_telemetry",
  "source": "network",
  "data": {
    "distance_cm": 145.0,
    "pitch_deg": 12.4,
    "roll_deg": -3.2,
    "command": "F",
    "mode": "M"
  },
  "timestamp": 1234567890123
}
```

---

## Serial Protocol (Rover MCU → Laptop)

The rover MCU sends data over HC-12 serial (9600 baud) to the laptop. Expected format:

```
DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
DIST:143.2,PITCH:12.1,ROLL:-3.5,CMD:F,MODE:M
...
```

### MCU Implementation Notes

```cpp
// Arduino/ESP32 pseudo-code for rover MCU
void sendTelemetry() {
    float distance = readHC_SR04();
    float pitch, roll;
    readMPU6050(pitch, roll);  // Complementary filter
    
    char buf[128];
    snprintf(buf, sizeof(buf),
        "DIST:%.1f,PITCH:%.1f,ROLL:%.1f,CMD:%c,MODE:%c\n",
        distance, pitch, roll, currentCommand, currentMode);
    
    Serial.print(buf);  // HC-12 connected to Serial
}

// Call at ~10-50 Hz
```

---

## Testing

### Unit Test Vectors

```python
# Valid packets
assert parse(b"DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M") == RoverPacket(145.0, 12.4, -3.2, 'F', 'M')
assert parse(b"DIST:0,PITCH:-90,ROLL:90,CMD:S,MODE:A") == RoverPacket(0, -90, 90, 'S', 'A')
assert parse(b"DIST:10000,PITCH:0,ROLL:0,CMD:B,MODE:M") == RoverPacket(10000, 0, 0, 'B', 'M')

# Invalid - should raise ValueError
try: parse(b"DIST:145,PITCH:12.4")  # Only 2 fields
try: parse(b"DIST:145,PITCH:12.4,ROLL:-3.2,CMD:X,MODE:M")  # Bad CMD
try: parse(b"DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:X")  # Bad MODE
try: parse(b"DIST:-1,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M")  # Negative distance
try: parse(b"DIST:145,PITCH:100,ROLL:-3.2,CMD:F,MODE:M")  # Pitch > 90
try: parse(b"DIST:145,PITCH:12.4,ROLL:-100,CMD:F,MODE:M")  # Roll < -90
try: parse(b"DIST:10001,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M")  # Distance > 10000
try: parse(b"not,a,valid,packet,format")  # Non-numeric
```

### Simulator Test (backend/tests/simulators/test_rover_sim.py)

```python
async def test_rover_simulator_generates_valid_data():
    sim = RoverSimulator()
    telemetry = await sim.generate()
    
    assert 0 <= telemetry.distance_cm <= 10000
    assert -90 <= telemetry.pitch_deg <= 90
    assert -90 <= telemetry.roll_deg <= 90
    assert telemetry.command in {'F', 'B', 'L', 'R', 'S'}
    assert telemetry.mode in {'M', 'A'}
```

---

## JSON Schema (Reference)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Rover UDP Packet",
  "type": "object",
  "required": ["DIST", "PITCH", "ROLL", "CMD", "MODE"],
  "properties": {
    "DIST": {
      "type": "number",
      "minimum": 0,
      "maximum": 10000,
      "description": "Distance in centimeters from HC-SR04"
    },
    "PITCH": {
      "type": "number",
      "minimum": -90,
      "maximum": 90,
      "description": "Pitch angle in degrees from MPU6050"
    },
    "ROLL": {
      "type": "number",
      "minimum": -90,
      "maximum": 90,
      "description": "Roll angle in degrees from MPU6050"
    },
    "CMD": {
      "type": "string",
      "enum": ["F", "B", "L", "R", "S"],
      "description": "Current rover command"
    },
    "MODE": {
      "type": "string",
      "enum": ["M", "A"],
      "description": "Rover mode: Manual or Autonomous"
    }
  },
  "additionalProperties": false
}
```

---

## Related Documents

- [Communication Overview](communication-overview.md) — Protocol summary
- [Network Architecture](architecture/network-architecture.md) — Port assignments
- [Rover Hardware](hardware/rover.md) — Sensor and laptop GUI details
- [Rover Wiring](wiring/rover-wiring.md) — Wiring diagrams
- [Data Flow](architecture/data-flow.md) — Rover telemetry flow