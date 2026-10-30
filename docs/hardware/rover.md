# Rover Hardware Details

## Subsystem Overview

The rover subsystem consists of three distinct parts:
1. **Rover Chassis** — Physical robot with sensors and HC-12 radio
2. **Rover Laptop** — Windows machine running Tkinter GUI that reads HC-12 serial and forwards UDP
3. **Pi Gateway** — Receives UDP packets on port 5005

> **Important**: The rover chassis MCU firmware is **not in this repository**. Only the laptop GUI forwarding and Pi gateway reception are implemented here.

---

## Rover Chassis (Physical Robot)

### Sensors

| Sensor | Model | Interface | Specifications | Purpose |
|--------|-------|-----------|----------------|---------|
| **Distance** | HC-SR04 | 2x GPIO (Trig, Echo) | 2-400 cm, ±3mm, 40kHz | Obstacle detection, distance measurement |
| **Orientation** | MPU6050 | I2C (0x68) | ±2g/±4g/±8g/±16g, ±250°/s | Pitch and roll measurement |
| **Radio** | HC-12 | UART (9600 baud) | 433MHz, 100m+ range, LoRa-like | Telemetry to laptop |

### Expected MCU Pinout (Typical Arduino/ESP32)

> [!WARNING]
> **UNVERIFIED — confirmation required**: The physical rover chassis MCU type, board pinout, and onboard schematics are not maintained in this repository. The diagram below illustrates a standard interfacing pattern for HC-SR04, MPU6050, and HC-12. Physical hardware connections must be confirmed with the rover build team.

```
          ROVER MCU (Arduino Nano / ESP32 / etc.)
    ┌─────────────────────────────────────────────────┐
    │                                                 │
    │  HC-SR04:                                       │
    │    Trig ──────► GPIO D2 (or any digital)        │
    │    Echo ──────► GPIO D3 (or any digital)        │
    │    VCC  ──────► 5V                              │
    │    GND  ──────► GND                             │
    │                                                 │
    │  MPU6050:                                       │
    │    VCC  ──────► 3.3V (or 5V with regulator)     │
    │    GND  ──────► GND                             │
    │    SDA  ──────► I2C SDA (A4 on Nano, GPIO21)    │
    │    SCL  ──────► I2C SCL (A5 on Nano, GPIO22)    │
    │                                                 │
    │  HC-12:                                         │
    │    VCC  ──────► 3.3V (HC-12 is 3.3V logic)      │
    │    GND  ──────► GND                             │
    │    TX   ──────► MCU RX (Serial1, or SoftwareSerial)│
    │    RX   ──────► MCU TX (Serial1, or SoftwareSerial)│
    │    SET  ──────► GND (transparent mode) or GPIO   │
    │                                                 │
    └─────────────────────────────────────────────────┘
```

### HC-12 Configuration

| Parameter | Value |
|-----------|-------|
| **Frequency** | 433.4-473.0 MHz (default 433.4 MHz) |
| **Baud Rate** | 9600 baud (air rate configurable via AT commands) |
| **Mode** | Transparent (SET pin = GND) or Command (SET pin = HIGH) |
| **Transmit Power** | Up to 100mW (20 dBm) |
| **Range** | 100m-1km line-of-sight |
| **Antenna** | Spring antenna or SMA external |

**AT Commands (if needed):**
```
AT+B9600     # Set serial baud to 9600
AT+P8        # Max transmit power
AT+C001      # Channel 1 (433.4 MHz)
AT+FU3       # Format: 8N1
AT+U3        # Air baud rate
```

---

## Rover Laptop (Windows Tkinter GUI)

### Software Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ROVER LAPTOP APPLICATION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    Serial (COM)    ┌─────────────────────┐  │
│  │  HC-12 USB   │◄────── 9600 baud ──►│  ROVER MCU          │  │
│  │  Adapter     │                     │  (sends ASCII)      │  │
│  └──────┬───────┘                     └─────────────────────┘  │
│         │                                                          │
│         ▼                                                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Tkinter GUI Application                                   │  │
│  │  - Serial reader thread (COM port)                        │  │
│  │  - ASCII parser: DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M│  │
│  │  - Validation: 5 fields, ranges, enums                    │  │
│  │  - UDP sender to Pi Gateway (port 5005)                   │  │
│  │  - Connection status display                               │  │
│  └────────────────────┬──────────────────────────────────────┘  │
│                       │                                          │
│                       ▼ UDP 5005                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  RASPBERRY PI GATEWAY                                      │  │
│  │  - RoverUDPReceiver listens on 0.0.0.0:5005               │  │
│  │  - Parses, validates, tracks staleness                    │  │
│  │  - Exposes /api/rover/status + WebSocket                  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Serial Protocol (MCU → Laptop)

The rover MCU is expected to send ASCII lines at ~50 Hz:

```
DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
DIST:143.2,PITCH:12.1,ROLL:-3.5,CMD:F,MODE:M
DIST:141.8,PITCH:11.8,ROLL:-3.7,CMD:L,MODE:M
...
```

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `DIST` | float | 0-10000 | Distance in cm from HC-SR04 |
| `PITCH` | float | -90 to +90 | Pitch angle in degrees |
| `ROLL` | float | -90 to +90 | Roll angle in degrees |
| `CMD` | enum | F,B,L,R,S | Current command: Forward, Back, Left, Right, Stop |
| `MODE` | enum | M,A | Mode: Manual, Autonomous |

### Tkinter GUI Responsibilities

1. **COM Port Selection** — Dropdown to select HC-12 USB serial port
2. **Baud Rate** — Fixed at 9600
3. **Line Parser** — Splits by `,`, then by `:` for each field
4. **Validation** — All 5 fields present, numeric ranges, enum values
5. **UDP Forward** — Sends validated packet to Pi Gateway IP:5005
6. **Status Display** — Shows parsed values, connection state, packet rate
7. **Error Handling** — Logs parse errors, shows last valid data

### UDP Forwarding (Laptop → Pi)

```python
# Simplified forwarding logic
import socket

PI_GATEWAY_IP = "192.168.50.1"
PI_GATEWAY_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def forward_packet(parsed_data: dict):
    # Reconstruct ASCII packet
    packet = f"DIST:{parsed_data['distance']:.1f}," \
             f"PITCH:{parsed_data['pitch']:.1f}," \
             f"ROLL:{parsed_data['roll']:.1f}," \
             f"CMD:{parsed_data['command']}," \
             f"MODE:{parsed_data['mode']}"
    sock.sendto(packet.encode('ascii'), (PI_GATEWAY_IP, PI_GATEWAY_PORT))
```

---

## Pi Gateway Reception (RoverUDPReceiver)

### Configuration (gateway/config.py)

```python
ROVER_UDP_HOST = "0.0.0.0"
ROVER_UDP_PORT = 5005
ROVER_STALENESS_THRESHOLD = 2.0  # seconds
```

### Packet Parsing (gateway/rover_udp.py)

```python
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
    
    # Validate required fields
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

### Staleness Monitoring

```python
class RoverUDPReceiver:
    def __init__(self):
        self._last_packet_time = 0
        self._last_valid_packet: Optional[RoverPacket] = None
        self._staleness_threshold = 2.0  # seconds
    
    def get_status(self) -> DeviceStatus:
        age = time.time() - self._last_packet_time
        if age > self._staleness_threshold:
            return DeviceStatus.OFFLINE
        elif self._last_valid_packet is None:
            return DeviceStatus.OFFLINE
        return DeviceStatus.ONLINE
```

---

## Data Flow Summary

```
Rover MCU                          Laptop GUI                     Pi Gateway
──────────                          ────────                      ──────────
  │                                    │                            │
  │ HC-SR04 + MPU6050                  │                            │
  │  ~50 Hz sampling                   │                            │
  │                                    │                            │
  │ Serial 9600 baud                   │                            │
  │ "DIST:145,PITCH:12.4,             │                            │
  │  ROLL:-3.2,CMD:F,MODE:M" ────────►│                            │
  │                                    │                            │
  │                    Parse + Validate│                            │
  │                                    │                            │
  │                    UDP 5005        │                            │
  │                    "DIST:145,..." ─┼─────────────────────────►│
  │                                    │                            │
  │                                    │              Parse ASCII   │
  │                                    │              Validate 5 fields
  │                                    │              Range checks
  │                                    │              Enum checks
  │                                    │                            │
  │                                    │◄─── /api/rover/status ────┤ (poll 0.2s)
  │                                    │                            │
  │                                    │◄─── WS /ws/telemetry ─────┤ (push)
```

---

## Integration Points

| Interface | Protocol | Endpoint | Rate |
|-----------|----------|----------|------|
| MCU → Laptop | Serial UART | COM port, 9600 baud | ~50 Hz |
| Laptop → Pi | UDP | 192.168.50.1:5005 | ~5 Hz (forwarded) |
| Pi → Backend | HTTP | GET /api/rover/status | 0.2s poll |
| Pi → Backend | WebSocket | /ws/telemetry | Event-driven |

---

## Testing Without Hardware

### Simulator (backend/app/communication/simulator_runner.py)

```python
class RoverSimulator:
    """Generates realistic rover telemetry for sim mode."""
    
    async def run(self):
        while self._running:
            # Simulate movement pattern
            distance = 100 + 50 * math.sin(time.time() * 0.5)
            pitch = 5 * math.sin(time.time() * 0.3)
            roll = 3 * math.cos(time.time() * 0.4)
            cmd = random.choice(['F', 'F', 'F', 'L', 'R', 'S'])
            mode = 'M'
            
            telemetry = RoverTelemetry(
                distance_cm=distance,
                pitch_deg=pitch,
                roll_deg=roll,
                command=cmd,
                mode=mode
            )
            await self.telemetry_service.ingest('rover', telemetry.to_dict())
            await asyncio.sleep(0.2)  # 5 Hz
```

---

## Related Documents

- [Hardware Overview](hardware-overview.md) — All subsystems summary
- [Rover Wiring](wiring/rover-wiring.md) — Wiring diagrams (where available)
- [Network Architecture](architecture/network-architecture.md) — UDP 5005 details
- [Rover UDP Protocol](protocols/rover-udp.md) — ASCII packet format
- [Software Architecture](architecture/software-architecture.md) — RoverRunner, RoverSimulator