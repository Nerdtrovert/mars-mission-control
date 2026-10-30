# Hardware Overview

## Subsystem Summary

| Subsystem | Controller | Key Sensors | Communication | Power |
|-----------|------------|-------------|---------------|-------|
| **Lander** | ESP32-WROOM-32 / DevKit V1 | BMP280, DHT11, 20x4 I2C LCD, 2x LEDs | Wi-Fi STA → TCP 5006 | 5V USB / 3.3V reg |
| **Rover** | Custom (HC-SR04 + MPU6050) | HC-SR04 (ultrasonic), MPU6050 (IMU) | HC-12 433MHz → Laptop → UDP 5005 | 5V/3.3V from rover chassis |
| **Drone** | ESP32-based flight controller | GPS, IMU, Env (temp/pressure/humidity), Battery | Wi-Fi STA → UDP 5007 | LiPo 3S/4S via BEC |

---

## Lander (ESP32-WROOM-32 / DevKit V1)

### Physical Layout
```
                    ESP32 DevKit V1
    ┌─────────────────────────────────────────┐
    │                                         │
    │   ┌─────────────────────────────────┐   │
    │   │ USB-C (Power + Programming)     │   │
    │   └─────────────────────────────────┘   │
    │                                         │
    │  GPIO21 ──────────────► I2C SDA (LCD, BMP280)  │
    │  GPIO22 ──────────────► I2C SCL (LCD, BMP280)  │
    │  GPIO17 ──────────────► DHT11 Data (1-wire)    │
    │  GPIO25 ──────────────► Green LED (ACTIVE Mode)│
    │  GPIO26 ──────────────► Red LED (Sensor Error) │
    │                                         │
    │  3.3V ────────────────► BMP280 VCC, DHT11 VCC  │
    │  5V (VIN) ────────────► 20x4 LCD VCC           │
    │  GND  ────────────────► Common GND Reference   │
    │                                         │
    └─────────────────────────────────────────┘
```

### Pin Assignments (Authoritative — `lander/lander.ino`)

| Pin | Function | Component | Notes |
|-----|----------|-----------|-------|
| GPIO21 | I2C SDA | LCD (0x27), BMP280 (0x76) | 3.3V logic level |
| GPIO22 | I2C SCL | LCD (0x27), BMP280 (0x76) | 3.3V clock (100 kHz) |
| GPIO17 | Digital In/Out | DHT11 Data | 4.7k–10kΩ pullup to 3.3V |
| GPIO25 | Digital Out | Green LED | Active HIGH = ACTIVE mode |
| GPIO26 | Digital Out | Red LED | Blinking = Sensor error in ACTIVE mode |
| 3V3 | Power Out | BMP280, DHT11 | 3.3V regulated rail |
| 5V (VIN) | Power Out | 20x4 LCD Backpack | 5V rail for LCD backlight |
| GND | Ground | All peripherals | Common ground |
### Components Detail

| Component | Model | Interface | Address/Config | Purpose |
|-----------|-------|-----------|----------------|---------|
| **MCU** | ESP32-WROOM-32 | — | Dual-core 240MHz, 4MB Flash | Main controller |
| **Temp/Pressure** | BMP280 | I2C | 0x76 (SDO=GND) | Barometric pressure, temperature |
| **Temp/Humidity** | DHT11 | 1-Wire | GPIO 17 | Ambient temperature, humidity |
| **Display** | 20x4 Char LCD | I2C | 0x27 (PCF8574) | 5-page rotating display |
| **Status LED (Green)** | 5mm LED | GPIO 25 | Active HIGH | Mode indicator (ACTIVE) |
| **Error LED (Red)** | 5mm LED | GPIO 26 | Blink pattern | Sensor fault indicator |
| **RGB LED** | WS2812B | GPIO 27 | Retired / Unconnected | Hardware baseline preserves GPIO only |
| **Wi-Fi** | Internal | 2.4GHz | Station mode | TCP to Pi Gateway |

### LCD Pages (5 pages, 4s rotation)

| Page | Content |
|------|---------|
| 0 | **System Status**: Mode, WiFi RSSI, Uptime, Free heap |
| 1 | **BMP280**: Temperature, Pressure, Altitude, Sensor state |
| 2 | **DHT11**: Temperature, Humidity, Sensor state |
| 3 | **Rover Data** (from Pi): Distance, Pitch, Roll, Command, Mode, Signal |
| 4 | **Drone Data** (from Pi): Flight status, Latitude, Longitude, Signal |

### Power Budget (Estimated)

| Component | Current (typical) |
|-----------|-------------------|
| ESP32 (Wi-Fi active) | 180-250 mA |
| BMP280 | 2.7 µA (sleep) / 3.6 mA (active) |
| DHT11 | 2.5 mA (measuring) |
| LCD (backlight on) | 20-30 mA |
| Green LED | 2-5 mA |
| Red LED | 2-5 mA |
| WS2812B (white, full) | ~20 mA |
| **Total (typical)** | **~250-320 mA @ 5V** |
| **USB Supply Required** | **≥ 500 mA @ 5V** |

---

## Rover Subsystem

### Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        ROVER SUBSYSTEM                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐     HC-12 433MHz     ┌─────────────────────┐  │
│  │  ROVER      │◄────── 9600 baud ────►│  ROVER LAPTOP       │  │
│  │  CHASSIS    │     Serial UART       │  (Windows)          │  │
│  │             │                       │                     │  │
│  │ ┌─────────┐ │                       │ ┌─────────────────┐ │  │
│  │ │ HC-SR04 │ │                       │ │ Tkinter GUI     │ │  │
│  │ │ Trigger │ │                       │ │ - COM Port Read │ │  │
│  │ │ Echo    │ │                       │ │ - Parse ASCII   │ │  │
│  │ └─────────┘ │                       │ │ - Forward UDP   │ │  │
│  │             │                       │ └────────┬────────┘ │  │
│  │ ┌─────────┐ │                       │          │          │  │
│  │ │ MPU6050 │ │                       │          ▼          │  │
│  │ │ SDA/SCL │ │                       │  UDP 5005           │  │
│  │ └─────────┘ │                       │  DIST:145,PITCH:12.4│  │
│  │             │                       │  ROLL:-3.2,CMD:F,   │  │
│  │ ┌─────────┐ │                       │  MODE:M             │  │
│  │ │ HC-12   │ │                       └─────────────────────┘  │
│  │ │ TX/RX   │ │                                                │
│  │ └─────────┘ │                                                │
│  └─────────────┘                                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Rover Sensors

| Sensor | Model | Interface | Specs | Purpose |
|--------|-------|-----------|-------|---------|
| **Distance** | HC-SR04 | GPIO (Trig/Echo) | 2-400 cm, ±3mm | Obstacle detection |
| **Orientation** | MPU6050 | I2C (0x68) | ±2g/±4g/±8g/±16g, ±250°/s | Pitch & Roll |
| **Radio** | HC-12 | UART (9600 baud) | 433MHz, 100m+ range | Telemetry to laptop |

### Rover Laptop (Windows GUI)
- **Software**: Custom Tkinter application
- **Serial**: Reads from COM port (HC-12)
- **Parsing**: Expects rover MCU to send formatted ASCII
- **Forwarding**: UDP to Pi Gateway (port 5005)
- **Packet Format**: `DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M`

> **Note**: The rover chassis MCU and its firmware are not in this repository. Only the laptop GUI forwarding logic and Pi gateway reception are documented here.

---

## Drone Subsystem

### Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        DRONE SUBSYSTEM                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    DRONE FLIGHT CONTROLLER              │   │
│  │                        (ESP32-based)                    │   │
│  │                                                         │   │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌──────────────┐  │   │
│  │  │  GPS   │  │  IMU   │  │  ENV   │  │   BATTERY    │  │   │
│  │  │(UART/I2C)│ │(I2C)   │  │(I2C)   │  │  (ADC)       │  │   │
│  │  └────────┘  └────────┘  └────────┘  └──────────────┘  │   │
│  │         │         │         │              │            │   │
│  │         └─────────┼─────────┼──────────────┘            │   │
│  │                   ▼         ▼                           │   │
│  │            ┌──────────────────┐                         │   │
│  │            │   Sensor Fusion  │                         │   │
│  │            │   + Flight Logic │                         │   │
│  │            └────────┬─────────┘                         │   │
│  │                     │                                   │   │
│  │                     ▼                                   │   │
│  │            ┌──────────────────┐                         │   │
│  │            │   Wi-Fi UDP      │                         │   │
│  │            │   Sender (5007)  │                         │   │
│  │            └──────────────────┘                         │   │
│  │                     │                                   │   │
│  └─────────────────────┼───────────────────────────────────┘   │
│                        │                                       │
│                        ▼                                       │
│               Wi-Fi UDP 5007                                    │
│               JSON Telemetry                                    │
│                        │                                       │
│                        ▼                                       │
│               ┌─────────────────┐                              │
│               │ RASPBERRY PI    │                              │
│               │ GATEWAY         │                              │
│               │ (DroneUDPReceiver)                              │
│               └─────────────────┘                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Drone Sensors (Expected)

| Sensor | Interface | Data Provided |
|--------|-----------|---------------|
| **GPS** | UART / I2C | Latitude, Longitude, Altitude, Speed, Satellites |
| **IMU** | I2C (MPU6050/ICM20602) | Roll, Pitch, Yaw, Angular velocity, Acceleration |
| **Environment** | I2C (BMP280/BME280) | Temperature, Pressure, Humidity, Altitude |
| **Battery** | ADC (voltage divider) | Voltage, Current, Percentage, Cell voltages |
| **Flight Controller** | Internal | Flight mode, Armed status, Failsafe state |

### Telemetry Format (JSON, UDP 5007)

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

> **Note**: The drone flight controller firmware is not in this repository. The Pi gateway `DroneUDPReceiver` implements the expected parser and validator.

---

## Raspberry Pi Gateway

### Hardware
- **Model**: Raspberry Pi 4 Model B (2GB/4GB/8GB)
- **OS**: Raspberry Pi OS (64-bit) Lite
- **Network**: 
  - `wlan0`: Access Point (Mission-Control, 192.168.50.1)
  - `eth0` / `wlan1`: Uplink to development machine
- **Services**: 
  - `hostapd` (Wi-Fi AP)
  - `dnsmasq` (DHCP)
  - Gateway FastAPI app (systemd service)

### Pi GPIO (Not Used)
The Pi gateway is purely a network aggregator — no direct sensor connections.

---

## Development Machine Backend

### Hardware
- **Model**: Development Machine (Apple Silicon or Intel)
- **Role**: Backend server + Dashboard host
- **Network**: Connected to Pi via Ethernet or Wi-Fi
- **Storage**: Local SQLite database

---

## Network Infrastructure

| Device | Role | IP Assignment |
|--------|------|---------------|
| Raspberry Pi | Gateway / AP | 192.168.50.1 (static) |
| Lander ESP32 | Sensor node | DHCP (192.168.50.10-100) |
| Drone ESP32 | Sensor node | DHCP (192.168.50.10-100) |
| Rover Laptop | Telemetry forwarder | DHCP or static |
| Development Machine | Backend | DHCP or static (same subnet) |

---

## Bill of Materials (Key Components)

### Lander
- [ ] ESP32-WROOM-32 DevKit V1
- [ ] BMP280 breakout (I2C, 0x76)
- [ ] DHT11 module (with 10k pullup)
- [ ] 20x4 I2C LCD (PCF8574, 0x27)
- [ ] 5mm Green LED + 220Ω resistor
- [ ] 5mm Red LED + 220Ω resistor
- [ ] WS2812B RGB LED (single)
- [ ] Breadboard / perfboard + jumper wires
- [ ] USB-C cable + 5V/2A power supply

### Rover (Chassis + Laptop)
- [ ] Rover chassis with motors
- [ ] HC-SR04 ultrasonic sensor
- [ ] MPU6050 IMU breakout
- [ ] HC-12 433MHz module (×2: rover + laptop)
- [ ] Arduino/ESP32 for rover MCU (not in repo)
- [ ] Windows laptop with USB-Serial for HC-12

### Drone
- [ ] ESP32-based flight controller (custom or commercial)
- [ ] GPS module (UART/I2C)
- [ ] IMU (MPU6050/ICM20602)
- [ ] Environmental sensor (BMP280/BME280)
- [ ] Battery monitor (ADC + voltage divider)
- [ ] LiPo battery + BEC (5V for ESP32)

### Gateway
- [ ] Raspberry Pi 4 (2GB+)
- [ ] MicroSD (16GB+)
- [ ] 5V/3A USB-C power supply
- [ ] Ethernet cable (to development machine)
- [ ] Case + heatsink/fan recommended

---

## Related Documents

- [Lander Hardware Details](lander.md) — Pinout, wiring, firmware details
- [Rover Hardware Details](rover.md) — Sensors, communication
- [Drone Hardware Details](drone.md) — Expected sensors, telemetry
- [Lander Wiring](wiring/lander-wiring.md) — Schematics and connections
- [Rover Wiring](wiring/rover-wiring.md) — Where available
- [Drone Wiring](wiring/drone-wiring.md) — Where available
- [Network Architecture](architecture/network-architecture.md) — Network topology
- [Communication Protocols](protocols/communication-overview.md) — Protocol summary