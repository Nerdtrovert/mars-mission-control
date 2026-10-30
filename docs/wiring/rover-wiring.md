# Rover Wiring Diagrams

> [!WARNING]
> **UNVERIFIED — confirmation required**: The rover chassis MCU firmware and physical circuit connections are not maintained in this repository. These diagrams illustrate typical wiring patterns for HC-SR04 ultrasonic sensors, MPU6050 IMUs, and HC-12 transceivers based on standard reference designs. Exact pinouts and power routing must be verified on the physical rover build.

---

## Rover Chassis — Typical Wiring

### MCU Options

| MCU | I2C Pins | Serial Pins | Notes |
|-----|----------|-------------|-------|
| Arduino Nano | A4 (SDA), A5 (SCL) | D0/D1 (Hardware), D2/D3 (SoftwareSerial) | 5V logic, level shift for 3.3V sensors |
| Arduino Uno | A4 (SDA), A5 (SCL) | D0/D1 (Hardware), D2/D3 (SoftwareSerial) | 5V logic |
| ESP32 DevKit | GPIO21 (SDA), GPIO22 (SCL) | GPIO16/17 (UART2), any (SoftwareSerial) | 3.3V logic, native Wi-Fi not used here |
| STM32 Blue Pill | PB7 (SDA), PB6 (SCL) | PA2/PA3 (USART2), any | 3.3V logic |

---

## HC-SR04 Ultrasonic Distance Sensor

### Wiring (5V Version)

```
HC-SR04                MCU (5V Logic, e.g., Arduino Nano)
─────────────────────────────────────────────────────────────
VCC      ────────────► 5V
Trig     ────────────► Digital Out (e.g., D2)
Echo     ────────────► Digital In  (e.g., D3) ──► 1kΩ ──┐
GND      ────────────► GND                                   │
                                                         │ 2kΩ
                                                         ▼
                                                      GND
                    (Voltage divider: 5V Echo → 3.3V MCU if needed)
```

### Wiring (3.3V Compatible Version)

```
HC-SR04 (3.3V compatible)   MCU (3.3V Logic, e.g., ESP32)
─────────────────────────────────────────────────────────────
VCC      ────────────► 3.3V (or 5V if module has regulator)
Trig     ────────────► GPIO Out (e.g., GPIO25)
Echo     ────────────► GPIO In  (e.g., GPIO26)
GND      ────────────► GND
```

### Timing Requirements

| Parameter | Value |
|-----------|-------|
| Trigger Pulse | ≥10 µs HIGH |
| Echo Pulse | 150 µs – 25 ms (proportional to distance) |
| Measurement Cycle | ≥60 ms between triggers |
| Distance Formula | `distance_cm = echo_time_us × 0.0343 / 2` |

---

## MPU6050 IMU (Accelerometer + Gyroscope)

### Wiring

```
MPU6050                MCU
─────────────────────────────────────────────────────────────
VCC      ────────────► 3.3V (or 5V if module has regulator)
GND      ────────────► GND
SCL      ────────────► I2C SCL (A5 on Nano, GPIO22 on ESP32)
SDA      ────────────► I2C SDA (A4 on Nano, GPIO21 on ESP32)
XDA      ────────────► NC (aux I2C for magnetometer)
XCL      ────────────► NC
AD0      ────────────► GND (for I2C address 0x68) or 3.3V (0x69)
INT      ────────────► Optional: GPIO In for data ready interrupt
```

### I2C Address

| AD0 Pin | Address |
|---------|---------|
| GND | 0x68 (default) |
| 3.3V | 0x69 |

### Key Registers

| Register | Address | Description |
|----------|---------|-------------|
| WHO_AM_I | 0x75 | Device ID (returns 0x68) |
| PWR_MGMT_1 | 0x6B | Power management (clear sleep bit) |
| ACCEL_CONFIG | 0x1C | Accelerometer range (±2g/±4g/±8g/±16g) |
| GYRO_CONFIG | 0x1B | Gyroscope range (±250/±500/±1000/±2000 °/s) |
| ACCEL_XOUT_H | 0x3B | Accelerometer data (6 bytes: X,Y,Z) |
| GYRO_XOUT_H | 0x43 | Gyroscope data (6 bytes: X,Y,Z) |
| TEMP_OUT_H | 0x41 | Temperature data (2 bytes) |

### Sensor Fusion for Pitch/Roll

```cpp
// Complementary filter (simple, effective for rover)
float pitch = 0, roll = 0;
float alpha = 0.98;  // Weight for gyro vs accel

void updateOrientation() {
    // Read raw values
    int16_t ax, ay, az, gx, gy, gz;
    mpu.readAccelGyro(ax, ay, az, gx, gy, gz);
    
    // Convert to physical units
    float accelPitch = atan2(ay, sqrt(ax*ax + az*az)) * RAD_TO_DEG;
    float accelRoll  = atan2(-ax, sqrt(ay*ay + az*az)) * RAD_TO_DEG;
    float gyroPitchRate = gx / 131.0;  // ±250°/s → 131 LSB/°/s
    float gyroRollRate  = gy / 131.0;
    
    // Time delta
    float dt = (millis() - lastTime) / 1000.0;
    lastTime = millis();
    
    // Complementary filter
    pitch = alpha * (pitch + gyroPitchRate * dt) + (1 - alpha) * accelPitch;
    roll  = alpha * (roll  + gyroRollRate  * dt) + (1 - alpha) * accelRoll;
}
```

---

## HC-12 433MHz Radio Module

### Wiring

```
HC-12                  MCU (3.3V Logic)
─────────────────────────────────────────────────────────────
VCC      ────────────► 3.3V (HC-12 is 3.3V logic only!)
GND      ────────────► GND
TX       ────────────► MCU RX (Hardware Serial preferred)
RX       ────────────► MCU TX
SET      ────────────► GND (transparent mode) or GPIO (for AT commands)
```

### For 5V MCU (Arduino Nano/Uno) — Level Shifting Required

```
HC-12                  Level Shifter              Arduino Nano
────────────────────────────────────────────────────────────────────
VCC      ────────────► HV (5V)                    5V
GND      ────────────► GND                        GND
TX       ────────────► LV1 (TX) ──► HV1 (RX) ────► D0 (RX) / D2 (SoftwareSerial RX)
RX       ────────────► LV2 (RX) ──► HV2 (TX) ────► D1 (TX) / D3 (SoftwareSerial TX)
SET      ────────────► GND (or GPIO via shifter)  GND / D4
```

### HC-12 Configuration (AT Commands)

Enter command mode: SET pin HIGH, wait 40ms, send `AT` commands at 9600 baud.

| Command | Description | Example |
|---------|-------------|---------|
| `AT` | Test communication | Returns `OK` |
| `AT+Bxxxx` | Set serial baud | `AT+B9600` |
| `AT+Pn` | Set TX power (1-8) | `AT+P8` (max) |
| `AT+Cxxx` | Set channel (001-127) | `AT+C001` (433.4 MHz) |
| `AT+FUn` | Set format | `AT+FU3` (8N1) |
| `AT+Ux` | Set air baud rate | `AT+U3` (default) |
| `AT+Dn` | Set transmit mode | `AT+D0` (transparent) |
| `AT+Rx` | Set receive mode | `AT+R0` (transparent) |
| `AT+V` | Query version | Returns version string |
| `AT+S` | Sleep mode | `AT+SLEEP` |

**Default Settings (transparent mode):**
- Baud: 9600
- Channel: 1 (433.4 MHz)
- Power: 8 (max)
- Format: 8N1

---

## Complete Rover Chassis Wiring (Arduino Nano Example)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ROVER CHASSIS — ARDUINO NANO                         │
└─────────────────────────────────────────────────────────────────────────────┘

                           Arduino Nano
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                         │
    │   USB ◄────────────────────────────────────── Programming/Power        │
    │                                                                         │
    │   5V  ──────────────────────────────────────────────────────┐          │
    │         │                                                    │          │
    │         ├──► HC-SR04 VCC                                     │          │
    │         ├──► MPU6050 VCC (if 5V tolerant)                    │          │
    │         ├──► HC-12 VCC ──► Level Shifter HV                   │          │
    │         │                                                    │          │
    │   3.3V ──────────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         ├──► MPU6050 VCC (if 3.3V only)                      │          │
    │         ├──► HC-12 VCC (if direct 3.3V)                      │          │
    │         ├──► Level Shifter LV                                 │          │
    │         │                                                    │          │
    │   GND ────────────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         ├──► All component GND                               │          │
    │         └──► Level Shifter GND                                │          │
    │                                                                         │
    │   A4 (SDA) ──────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         └──► MPU6050 SDA                                     │          │
    │                                                                         │
    │   A5 (SCL) ──────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         └──► MPU6050 SCL                                     │          │
    │                                                                         │
    │   D2 ────────────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         └──► HC-SR04 Trig                                    │          │
    │                                                                         │
    │   D3 ────────────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         └──► HC-SR04 Echo ──► 1kΩ ──► D3                     │          │
    │                    │                              │          │          │
    │                    └── 2kΩ ──► GND                      │          │
    │                                                                         │
    │   D4 ────────────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         └──► HC-12 SET (optional, for AT commands)           │          │
    │                                                                         │
    │   D0 (RX) ───────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         └──► Level Shifter HV1 (RX) ──► LV1 (TX) ──► HC-12 TX │          │
    │                                                                         │
    │   D1 (TX) ───────────────────────────────────────────────────┤          │
    │         │                                                    │          │
    │         └──► Level Shifter HV2 (TX) ──► LV2 (RX) ──► HC-12 RX │          │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘
```

---

## Laptop Side — HC-12 USB Adapter

```
HC-12 Module           USB-Serial Adapter       Laptop
─────────────────────────────────────────────────────────────
VCC      ────────────► 3.3V / 5V (check adapter)  USB Port
GND      ────────────► GND
TX       ────────────► RX
RX       ────────────► TX
SET      ────────────► GND (transparent mode)
```

### Serial Settings (Tkinter GUI)

```python
# In rover laptop GUI
SERIAL_PORT = "COM3"      # Check Device Manager
BAUD_RATE = 9600
BYTESIZE = 8
PARITY = 'N'
STOPBITS = 1
TIMEOUT = 1
```

---

## Expected Serial Output (Rover MCU → Laptop)

The rover MCU should send ASCII lines at ~50 Hz:

```
DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
DIST:143.2,PITCH:12.1,ROLL:-3.5,CMD:F,MODE:M
DIST:141.8,PITCH:11.8,ROLL:-3.7,CMD:L,MODE:M
DIST:140.5,PITCH:11.5,ROLL:-4.0,CMD:L,MODE:M
DIST:139.1,PITCH:11.2,ROLL:-4.2,CMD:F,MODE:M
...
```

| Field | Source | Rate |
|-------|--------|------|
| `DIST` | HC-SR04 | ~10 Hz |
| `PITCH` | MPU6050 (complementary filter) | ~50 Hz |
| `ROLL` | MPU6050 (complementary filter) | ~50 Hz |
| `CMD` | Rover control logic | On change |
| `MODE` | Rover control logic | On change |

---

## Testing Without Rover Hardware

### Simulated Serial Data (for GUI testing)

```python
# test_rover_serial.py - Run on laptop to simulate rover data
import serial
import time
import random
import math

# Use a virtual COM port pair (com0com on Windows, socat on Linux)
# Or connect two USB-serial adapters back-to-back

ser = serial.Serial('COM3', 9600, timeout=1)

t = 0
while True:
    # Simulate circular movement
    distance = 100 + 50 * math.sin(t * 0.5)
    pitch = 5 * math.sin(t * 0.3)
    roll = 3 * math.cos(t * 0.4)
    cmd = random.choice(['F', 'F', 'F', 'F', 'L', 'R', 'S'])
    mode = 'M'
    
    line = f"DIST:{distance:.1f},PITCH:{pitch:.1f},ROLL:{roll:.1f},CMD:{cmd},MODE:{mode}\n"
    ser.write(line.encode('ascii'))
    print(f"Sent: {line.strip()}")
    
    t += 0.1
    time.sleep(0.1)  # ~10 Hz
```

---

## Related Documents

- [Rover Hardware](hardware/rover.md) — Sensor specs, laptop GUI, Pi gateway
- [Wiring Index](README.md) — All wiring docs
- [Hardware Overview](hardware/hardware-overview.md) — BOM and summary
- [Rover UDP Protocol](protocols/rover-udp.md) — ASCII packet format
- [Network Architecture](architecture/network-architecture.md) — UDP 5005 details