# Drone Hardware Details

## Subsystem Overview

The drone subsystem consists of:
1. **Drone Flight Controller** — ESP32-based controller with sensors (not in this repo)
2. **Pi Gateway** — Receives UDP packets on port 5007

> **Important**: The drone flight controller firmware is **not in this repository**. The Pi gateway `DroneUDPReceiver` implements the expected parser and validator based on the telemetry schema defined here.

---

## Drone Flight Controller (Expected)

> [!WARNING]
> **UNVERIFIED — confirmation required**: The physical drone hardware controller, flight sensors, GPS module, and onboard wiring are not present in this codebase. Only the UDP communication interface (port 5007), packet validation contract, and state management are implemented and verified. Physical hardware details require confirmation with the drone hardware team.

### Hardware Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DRONE FLIGHT CONTROLLER                      │
│                        (ESP32-based)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    ESP32 (Main MCU)                     │   │
│  │  - Dual-core 240 MHz                                    │   │
│  │  - Wi-Fi + Bluetooth                                    │   │
│  │  - Runs sensor fusion + flight control                  │   │
│  └────────────────────┬────────────────────────────────────┘   │
│                       │                                          │
│        ┌──────────────┼──────────────┬──────────────┐           │
│        ▼              ▼              ▼              ▼           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐     │
│  │   GPS    │   │   IMU    │   │  ENV     │   │ BATTERY  │     │
│  │ (UART)   │   │ (I2C)    │   │ (I2C)    │   │ (ADC)    │     │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘     │
│        │              │              │              │           │
│        └──────────────┴──────────────┴──────────────┘           │
│                       │                                          │
│                       ▼                                          │
│            ┌──────────────────┐                                 │
│            │  Sensor Fusion   │                                 │
│            │  + Flight Logic  │                                 │
│            └────────┬─────────┘                                 │
│                     │                                           │
│                     ▼                                           │
│            ┌──────────────────┐                                 │
│            │  Wi-Fi UDP Sender│                                 │
│            │  (Port 5007)     │                                 │
│            └──────────────────┘                                 │
│                     │                                           │
└─────────────────────┼───────────────────────────────────────────┘
                      │
                      ▼ Wi-Fi UDP 5007
             ┌─────────────────┐
             │ RASPBERRY PI    │
             │ GATEWAY         │
             │ DroneUDPReceiver│
             └─────────────────┘
```

### Expected Sensors

| Sensor | Model Options | Interface | Data Provided |
|--------|---------------|-----------|---------------|
| **GPS** | UBLOX NEO-M8N, NEO-6M, SAM-M8Q | UART (9600-115200 baud) | Lat, Lon, Alt, Speed, Course, Satellites, HDOP, Fix type |
| **IMU** | MPU6050, ICM20602, BMI270 | I2C (0x68/0x69) or SPI | Accel (3-axis), Gyro (3-axis), optionally Mag |
| **Environment** | BMP280, BME280, BMP388, DPS310 | I2C (0x76/0x77) | Temperature, Pressure, Humidity (BME280), Altitude |
| **Battery** | ADC + Voltage Divider | ADC (GPIO) | Pack Voltage, Cell Voltages, Current, Percentage |
| **Barometer** | (Integrated in ENV) | — | Pressure altitude |
| **Magnetometer** | (Integrated in IMU or separate) | I2C | Heading (yaw) |

### Expected Pinout (ESP32)

```
          DRONE ESP32 (Typical Pin Assignment)
    ┌─────────────────────────────────────────────────┐
    │                                                 │
    │  GPS (UART2):                                   │
    │    GPS_TX ──────► GPIO16 (UART2_RX)             │
    │    GPS_RX ──────► GPIO17 (UART2_TX)             │
    │    VCC     ──────► 3.3V / 5V                    │
    │    GND     ──────► GND                          │
    │                                                 │
    │  IMU (I2C):                                     │
    │    SDA     ──────► GPIO21 (I2C SDA)             │
    │    SCL     ──────► GPIO22 (I2C SCL)             │
    │    VCC     ──────► 3.3V                         │
    │    GND     ──────► GND                          │
    │                                                 │
    │  ENV Sensor (I2C - shared bus):                 │
    │    SDA     ──────► GPIO21 (I2C SDA)             │
    │    SCL     ──────► GPIO22 (I2C SCL)             │
    │    VCC     ──────► 3.3V                         │
    │    GND     ──────► GND                          │
    │                                                 │
    │  Battery Monitor:                               │
    │    VBAT_ADC ─────► GPIO34 (ADC1_6) via divider  │
    │    (Optional) Current sense ────► GPIO35 (ADC1_7)│
    │                                                 │
    │  Status LED:                                    │
    │    LED     ──────► GPIO2 (built-in) or GPIO5    │
    │                                                 │
    │  Wi-Fi: Internal antenna (keep clear)           │
    │                                                 │
    └─────────────────────────────────────────────────┘
```

### Battery Monitor Circuit

```
        Battery Pack (3S/4S LiPo)
              │
              ▼
         ┌─────────┐
         │ Voltage │
         │ Divider │  (e.g., 100kΩ + 10k÷ for 3S 12.6V max → 1.14V)
         └────┬────┘
              │
              ▼
         GPIO34 (ADC1_6)  ──────► ESP32
              │
             GND
```

**Divider Calculation (3S LiPo, max 12.6V):**
- R1 = 100kΩ, R2 = 10kΩ
- Vout = Vin × R2/(R1+R2) = 12.6 × 10/110 = 1.145V (within ESP32 ADC 0-1.1V or 0-3.3V with attenuation)
- Use ADC_ATTEN_DB_11 (0-3.3V range) for full scale

---

## Telemetry Protocol (UDP 5007)

### Packet Format (JSON)

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

### Field Specifications

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `device_id` | string | Yes | Non-empty, expected "esp32-drone" | Device identifier |
| `sequence` | integer | Yes | ≥0, monotonic (RFC 1982) | Packet sequence number |
| `timestamp_ms` | integer | Yes | ≥0, epoch milliseconds | Sensor timestamp |
| `flight_status` | string | Yes | Non-empty | Flight mode: "ARMED", "DISARMED", "CRUISING", "HOVER", "RTL", "FAILSAFE", etc. |
| `orientation` | object | Yes | See below | Roll, Pitch, Yaw in degrees |
| `environment` | object | Yes | See below | Temperature, Pressure, Humidity |
| `gps` | object | Yes | See below | Latitude, Longitude, Altitude |
| `battery` | object | Yes | See below | Voltage, Percentage |

#### Orientation Object
| Field | Type | Units | Range |
|-------|------|-------|-------|
| `roll` | float | degrees | -180 to +180 |
| `pitch` | float | degrees | -90 to +90 |
| `yaw` | float | degrees | 0 to 360 |

#### Environment Object
| Field | Type | Units | Range |
|-------|------|-------|-------|
| `temperature_c` | float | °C | -40 to +85 |
| `pressure_hpa` | float | hPa | 300-1100 |
| `humidity_pct` | float | % | 0-100 (optional, BME280 only) |

#### GPS Object
| Field | Type | Units | Range |
|-------|------|-------|-------|
| `latitude` | float | degrees | -90 to +90 |
| `longitude` | float | degrees | -180 to +180 |
| `altitude_m` | float | meters | -1000 to +10000 |

#### Battery Object
| Field | Type | Units | Range |
|-------|------|-------|-------|
| `voltage_v` | float | Volts | 0-25 (depends on cell count) |
| `percentage` | float | % | 0-100 |

---

## Sequence Number Handling (RFC 1982)

The drone uses sequence numbers for packet ordering and duplicate detection. The Pi gateway implements RFC 1982 "Serial Number Arithmetic" for rollover handling.

### Implementation (gateway/drone_udp.py)

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

### Rollover Behavior

| Sequence Bits | Max Value | Rollover Point | Half Space |
|---------------|-----------|----------------|------------|
| 16-bit | 65535 | 0 → 65535 | 32768 |
| 32-bit | 4294967295 | 0 → 4294967295 | 2147483648 |

The gateway accepts both 16-bit and 32-bit sequence numbers (detected by value range).

---

## Pi Gateway Reception (DroneUDPReceiver)

### Configuration (gateway/config.py)

```python
DRONE_UDP_HOST = "0.0.0.0"
DRONE_UDP_PORT = 5007
DRONE_STALENESS_THRESHOLD = 10.0  # seconds
DRONE_SEQUENCE_BITS = 32  # or 16
```

### JSON Schema Validation

```python
import json
from typing import Optional

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

### Staleness Monitoring

```python
class DroneUDPReceiver:
    def __init__(self):
        self._last_packet_time = 0
        self._last_valid_packet: Optional[DronePacket] = None
        self._last_sequence: Optional[int] = None
        self._staleness_threshold = 10.0  # seconds
    
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

## Integration Points

| Interface | Protocol | Endpoint | Rate |
|-----------|----------|----------|------|
| Drone → Pi | UDP | 192.168.50.1:5007 | ~2 Hz (configurable) |
| Pi → Backend | HTTP | GET /api/drone/status | 0.5s poll |
| Pi → Backend | WebSocket | /ws/telemetry | Event-driven |

---

## Flight Status Values

Expected `flight_status` strings (extensible):

| Status | Description |
|--------|-------------|
| `DISARMED` | Motors off, safe |
| `ARMED` | Motors armed, ready |
| `TAKEOFF` | Ascending to altitude |
| `HOVER` | Holding position |
| `CRUISING` | Waypoint navigation |
| `RTL` | Return to launch |
| `LANDING` | Descending to land |
| `LANDED` | On ground, disarming |
| `FAILSAFE` | Failsafe triggered (lost link, low battery) |
| `CRITICAL` | Critical battery/emergency |

---

## Testing Without Hardware

### Simulator (backend/app/communication/simulator_runner.py)

```python
class DroneSimulator:
    """Generates realistic drone telemetry for sim mode."""
    
    def __init__(self):
        self._sequence = 0
        self._lat = 12.9716  # Bangalore
        self._lon = 77.5946
        self._alt = 50.0
    
    async def run(self):
        while self._running:
            self._sequence += 1
            
            # Simulate circular flight pattern
            t = time.time()
            self._lat += 0.0001 * math.sin(t * 0.1)
            self._lon += 0.0001 * math.cos(t * 0.1)
            self._alt = 50 + 10 * math.sin(t * 0.2)
            
            telemetry = DroneTelemetry(
                device_id="esp32-drone",
                sequence=self._sequence,
                timestamp_ms=int(time.time() * 1000),
                flight_status="CRUISING",
                orientation={
                    'roll': 5 * math.sin(t * 0.5),
                    'pitch': 3 * math.cos(t * 0.3),
                    'yaw': (t * 10) % 360
                },
                environment={
                    'temperature_c': 25 + 2 * math.sin(t * 0.01),
                    'pressure_hpa': 1013.25,
                    'humidity_pct': 50
                },
                gps={
                    'latitude': self._lat,
                    'longitude': self._lon,
                    'altitude_m': self._alt
                },
                battery={
                    'voltage_v': 11.1 - 0.001 * self._sequence,
                    'percentage': max(0, 100 - 0.01 * self._sequence)
                }
            )
            await self.telemetry_service.ingest('drone', telemetry.to_dict())
            await asyncio.sleep(0.5)  # 2 Hz
```

---

## Related Documents

- [Hardware Overview](hardware-overview.md) — All subsystems summary
- [Drone Wiring](wiring/drone-wiring.md) — Wiring diagrams (where available)
- [Network Architecture](architecture/network-architecture.md) — UDP 5007 details
- [Drone UDP Protocol](protocols/drone-udp.md) — JSON schema and validation
- [Software Architecture](architecture/software-architecture.md) — DroneRunner, DroneSimulator