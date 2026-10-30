# Drone Wiring Diagrams

> [!WARNING]
> **UNVERIFIED — confirmation required**: The drone flight controller firmware and physical circuit wiring are not present in this repository. These diagrams illustrate typical wiring patterns for an ESP32 flight controller with GPS, IMU, environmental sensors, and battery telemetry. Actual physical connections must be confirmed with the drone hardware team.

---

## Drone Flight Controller — Typical Wiring (ESP32-Based)

### MCU: ESP32-WROOM-32 / DevKit V1

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DRONE FLIGHT CONTROLLER — ESP32                          │
└─────────────────────────────────────────────────────────────────────────────┘

                           ESP32 DevKit V1
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                         │
    │   USB-C ◄────────────────────────────────────────── 5V / Data          │
    │                                                                         │
    │   3V3  (Pin 1)  ──────────────────────────────────────────┐            │
    │                                                            │            │
    │   GPIO36 (Pin 4)  VP                                        │            │
    │   GPIO39 (Pin 5)  VN                                        │            │
    │   GPIO34 (Pin 7)  ◄── Battery Voltage ADC (via divider)    │            │
    │   GPIO35 (Pin 8)  ◄── Battery Current ADC (optional)       │            │
    │   GPIO32 (Pin 9)                                              │            │
    │   GPIO33 (Pin 10)                                             │            │
    │   GPIO25 (Pin 11)                                             │            │
    │   GPIO26 (Pin 12)                                             │            │
    │   GPIO27 (Pin 13)                                             │            │
    │   GPIO14 (Pin 14)                                             │            │
    │   GPIO12 (Pin 15)                                             │            │
    │   GPIO13 (Pin 16)                                             │            │
    │   GND  (Pin 17)  ──────────────────────────────────────────┼───────────┐│
    │                                                            │           ││
    │   GPIO2  (Pin 19)  ──► Status LED (built-in or external)   │           ││
    │                                                            │           ││
    │   GPIO4  (Pin 21)                                           │           ││
    │   GPIO5  (Pin 23)                                           │           ││
    │   GPIO18 (Pin 25)                                           │           ││
    │   GPIO19 (Pin 26)                                           │           ││
    │   GPIO21 (Pin 27) ──► I2C SDA ────────────────────────────┼───────────┤│
    │                    │                                       │           ││
    │                    ├──► IMU SDA (MPU6050/ICM20602 0x68)    │           ││
    │                    │                                       │           ││
    │                    ├──► ENV SDA (BMP280/BME280 0x76/0x77)  │           ││
    │                    │                                       │           ││
    │                    └──► (Magnetometer if separate)         │           ││
    │                                                            │           ││
    │   GPIO22 (Pin 28) ──► I2C SCL ────────────────────────────┼───────────┤│
    │                    │                                       │           ││
    │                    ├──► IMU SCL                             │           ││
    │                    │                                       │           ││
    │                    ├──► ENV SCL                             │           ││
    │                    │                                       │           ││
    │                    └──► (Magnetometer if separate)         │           ││
    │                                                            │           ││
    │   GPIO23 (Pin 29)                                           │           ││
    │                                                            │           ││
    │   5V   (Pin 30)  ──────────────────────────────────────────┼───────────┤│
    │                                                            │           ││
    │   GPIO16 (Pin 22) ◄── GPS UART2 RX ───────────────────────┤           ││
    │   GPIO17 (Pin 23) ──► GPS UART2 TX ───────────────────────┤           ││
    │                                                            │           ││
    │   GND  (Pin 2/17) ◄────────────────────────────────────────┘           │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘
                                    │                    │
                                    │                    │
                            ┌───────┴───────┐    ┌──────┴──────┐
                            │     IMU       │    │    ENV      │
                            │  (MPU6050/    │    │  (BMP280/   │
                            │   ICM20602)   │    │   BME280)   │
                            │ ┌───────────┐ │    │ ┌─────────┐ │
                            │ │ VCC ──► 3V3 │ │    │ │ VCC ──► 3V3 │ │
                            │ │ GND ──► GND │ │    │ │ GND ──► GND │ │
                            │ │ SDA ──► SDA │ │    │ │ SDA ──► SDA │ │
                            │ │ SCL ──► SCL │ │    │ │ SCL ──► SCL │ │
                            │ │ AD0 ──► GND │ │    │ │ SDO ──► GND │ │
                            │ │ INT ──► GPIO│ │    │ └─────────┘ │
                            │ └───────────┘ │    └─────────────┘
                            └───────────────┘
                                    │
                                    │
                            ┌───────┴───────┐
                            │     GPS       │
                            │  (UBLOX etc)  │
                            │ ┌───────────┐ │
                            │ │ VCC ──► 3V3 │ │
                            │ │ GND ──► GND │ │
                            │ │ TX  ──► RX2 │ │  (ESP32 GPIO16)
                            │ │ RX  ──► TX2 │ │  (ESP32 GPIO17)
                            │ └───────────┘ │
                            └───────────────┘
```

---

## GPS Module (UART)

### Common GPS Modules

| Module | Interface | Default Baud | Protocol |
|--------|-----------|--------------|----------|
| UBLOX NEO-M8N | UART | 9600 | NMEA + UBX |
| UBLOX NEO-6M | UART | 9600 | NMEA + UBX |
| UBLOX SAM-M8Q | UART/I2C | 9600 | NMEA + UBX |
| Beitian BN-880 | UART | 9600 | NMEA |
| Holybro M8N | UART | 9600 | NMEA + UBX |

### Wiring (UART)

```
GPS Module             ESP32
─────────────────────────────────────────────────────────────
VCC      ────────────► 3.3V (Pin 1)
GND      ────────────► GND
TX       ────────────► GPIO16 (UART2_RX, Pin 22)
RX       ────────────► GPIO17 (UART2_TX, Pin 23)
PPS      ────────────► Optional: GPIO for time sync
```

### GPS Configuration (UBX Commands for NEO-M8N)

```cpp
// Disable NMEA, enable UBX binary protocol
// Set update rate to 5 Hz (200ms)

// UBX-CFG-PRT (Port Configuration) - Set UART2 to 115200 baub, UBX only
// UBX-CFG-RATE (Navigation Rate) - 200ms measurement rate
// UBX-CFG-MSG (Message Rate) - Enable NAV-PVT, disable NMEA

// Example: Enable NAV-PVT at 5 Hz
uint8_t cfg_msg[] = {
    0xB5, 0x62,       // Sync
    0x06, 0x01,       // Class/ID: CFG-MSG
    0x08, 0x00,       // Length: 8
    0x01, 0x07,       // MSG Class: NAV (0x01), MSG ID: PVT (0x07)
    0x00, 0x01, 0x00, 0x00, 0x00, 0x00,  // Rates: UART1=1, USB=0, SPI=0, I2C=0
    0x12, 0x71        // Checksum
};
```

### NMEA Sentences (if using NMEA)

| Sentence | Description | Key Fields |
|----------|-------------|------------|
| `$GNGGA` | Fix data | Time, Lat, Lon, Quality, Sats, HDOP, Alt |
| `$GNRMC` | Recommended minimum | Time, Status, Lat, Lon, Speed, Course, Date |
| `$GNGSA` | Satellite status | Mode, Fix type, PRNs, PDOP, HDOP, VDOP |
| `$GNGSV` | Satellites in view | Total sats, PRN, Elevation, Azimuth, SNR |

---

## IMU (Inertial Measurement Unit)

### Common IMUs

| Module | Interface | Address | Sensors | Notes |
|--------|-----------|---------|---------|-------|
| MPU6050 | I2C | 0x68/0x69 | 3-axis accel + gyro | Basic, cheap |
| MPU6500 | I2C/SPI | 0x68/0x69 | 3-axis accel + gyro | Better noise |
| ICM20602 | I2C/SPI | 0x68/0x69 | 3-axis accel + gyro | Low noise, high rate |
| BMI270 | I2C/SPI | 0x68/0x69 | 3-axis accel + gyro | Ultra-low power |
| ICM20948 | I2C/SPI | 0x68/0x69 | 9-DoF (accel+gyro+mag) | All-in-one |

### Wiring (I2C — MPU6050 Example)

```
MPU6050                ESP32
─────────────────────────────────────────────────────────────
VCC      ────────────► 3.3V (Pin 1)
GND      ────────────► GND
SCL      ────────────► GPIO22 (Pin 28)
SDA      ────────────► GPIO21 (Pin 27)
AD0      ────────────► GND (for address 0x68)
INT      ────────────► Optional: GPIO (data ready interrupt)
```

### Sensor Fusion (Mahony/Maxwell Filter)

```cpp
// Mahony Filter for orientation estimation
#include <MahonyAHRS.h>

Mahony filter;
float roll, pitch, yaw;

void setup() {
    filter.begin(100);  // 100 Hz update rate
}

void updateIMU() {
    // Read raw data
    int16_t ax, ay, az, gx, gy, gz;
    mpu.readAccelGyro(ax, ay, az, gx, gy, gz);
    
    // Convert to SI units
    float accX = ax * 9.81 / 16384.0;  // ±2g = 16384 LSB/g
    float accY = ay * 9.81 / 16384.0;
    float accZ = az * 9.81 / 16384.0;
    float gyroX = gx * DEG_TO_RAD / 131.0;  // ±250°/s = 131 LSB/°/s
    float gyroY = gy * DEG_TO_RAD / 131.0;
    float gyroZ = gz * DEG_TO_RAD / 131.0;
    
    // Update filter
    filter.updateIMU(gyroX, gyroY, gyroZ, accX, accY, accZ);
    
    // Get Euler angles
    roll = filter.getRoll();
    pitch = filter.getPitch();
    yaw = filter.getYaw();
}
```

---

## Environmental Sensor (Temperature, Pressure, Humidity)

### Common Sensors

| Module | Interface | Address | Measures | Notes |
|--------|-----------|---------|----------|-------|
| BMP280 | I2C/SPI | 0x76/0x77 | Temp, Pressure | No humidity |
| BME280 | I2C/SPI | 0x76/0x77 | Temp, Pressure, Humidity | Popular |
| BMP388 | I2C/SPI | 0x76/0x77 | Temp, Pressure | Higher precision |
| DPS310 | I2C/SPI | 0x76/0x77 | Temp, Pressure | Small package |

### Wiring (I2C — BME280 Example)

```
BME280                 ESP32
─────────────────────────────────────────────────────────────
VCC      ────────────► 3.3V (Pin 1)
GND      ────────────► GND
SCL      ────────────► GPIO22 (Pin 28)
SDA      ────────────► GPIO21 (Pin 27)
SDO      ────────────► GND (for address 0x76) or 3.3V (0x77)
CSB      ────────────► 3.3V (I2C mode)
```

---

## Battery Monitoring

### Voltage Divider for 3S/4S LiPo

```
        Battery Pack (3S = 12.6V max, 4S = 16.8V max)
              │
              ▼
         ┌─────────┐
         │ Voltage │
         │ Divider │
         │         │
    VBAT ──►│ R1    │──► ADC_GPIO (GPIO34)
         │ 100kΩ  │
         │       │
         │    R2 │──► GND
         │ 10kΩ  │
         └───────┘
```

### Divider Calculations

| Battery | Max Voltage | R1 | R2 | Vout_max | ADC Attenuation |
|---------|-------------|-----|-----|----------|-----------------|
| 3S LiPo | 12.6V | 100kΩ | 10kΩ | 1.15V | ADC_ATTEN_DB_11 (0-3.3V) |
| 4S LiPo | 16.8V | 150kΩ | 10kΩ | 1.05V | ADC_ATTEN_DB_11 (0-3.3V) |
| 4S LiPo | 16.8V | 100kΩ | 6.8kΩ | 1.07V | ADC_ATTEN_DB_11 (0-3.3V) |

### ADC Reading Code

```cpp
// ESP32 ADC setup for battery voltage
const int BATTERY_ADC_PIN = 34;  // ADC1_6 (input only, no output)
const float R1 = 100000.0;       // 100kΩ
const float R2 = 10000.0;        // 10kΩ
const float DIVIDER_RATIO = (R1 + R2) / R2;  // 11.0 for 100k/10k

// ADC calibration (ESP32 ADC is non-linear)
// Use esp_adc_cal_characterize() for accurate readings

float readBatteryVoltage() {
    uint32_t adc_reading = 0;
    const int SAMPLES = 64;
    for (int i = 0; i < SAMPLES; i++) {
        adc_reading += analogRead(BATTERY_ADC_PIN);
    }
    adc_reading /= SAMPLES;
    
    // Convert to voltage (with attenuation 11dB = 0-3.3V range)
    float voltage = adc_reading * 3.3 / 4095.0 * DIVIDER_RATIO;
    
    return voltage;
}

// Battery percentage estimation (3S LiPo)
float voltageToPercentage(float voltage) {
    // 3S LiPo: 12.6V (100%) to 9.0V (0%) under load
    // Per cell: 4.2V to 3.0V
    float cell_voltage = voltage / 3.0;
    if (cell_voltage >= 4.2) return 100.0;
    if (cell_voltage <= 3.0) return 0.0;
    
    // Approximate curve
    float pct = (cell_voltage - 3.0) / (4.2 - 3.0) * 100.0;
    
    // Flatten middle region (typical LiPo discharge curve)
    if (pct > 90) pct = 90 + (pct - 90) * 0.5;
    if (pct < 10) pct = pct * 0.5;
    
    return constrain(pct, 0, 100);
}
```

### Current Sensing (Optional)

```
        Battery Pack
              │
              ▼
         ┌─────────┐
         │ Current │
         │ Sensor  │  (e.g., INA219 I2C, ACS758 analog, or shunt + amp)
         └────┬────┘
              │
              ▼
         ADC_GPIO (GPIO35)  or  I2C
```

---

## Power Distribution

### Drone Power System

```
                    DRONE POWER DISTRIBUTION
    ┌─────────────────────────────────────────────────────────────────────┐
    │                                                                     │
    │   LiPo Battery (3S/4S)                                              │
    │        │                                                            │
    │        ├──► BEC / UBEC (5V, 3A+) ──► ESC + Servos                  │
    │        │                                                            │
    │        ├──► BEC / UBEC (3.3V, 500mA+) ──► ESP32 + Sensors         │
    │        │       │                                                    │
    │        │       ├──► ESP32 5V Pin (if BEC is 5V)                    │
    │        │       ├──► ESP32 3.3V Pin (if BEC is 3.3V)               │
    │        │       ├──► GPS VCC                                         │
    │        │       ├──► IMU VCC                                         │
    │        │       ├──► ENV Sensor VCC                                  │
    │        │       └──► Voltage Divider (for ADC)                      │
    │        │                                                            │
    │        └──► Voltage Divider ──► ESP32 ADC (GPIO34)                 │
    │                                                                     │
    │   Common GND ────────────────────────────────────────────────────┐  │
    │                                                                  │  │
    └──────────────────────────────────────────────────────────────────┘  │
```

---

## Complete Drone Wiring Summary

### Pin Assignment Table

| ESP32 Pin | GPIO | Function | Component | Notes |
|-----------|------|----------|-----------|-------|
| 1 | 3V3 | Power Out | All sensors VCC | Max ~500mA |
| 2/17 | GND | Ground | All GND | Common |
| 4 | GPIO36 | ADC1_0 | — | Input only |
| 5 | GPIO39 | ADC1_3 | — | Input only |
| 7 | GPIO34 | ADC1_6 | Battery Voltage | Input only, via divider |
| 8 | GPIO35 | ADC1_7 | Battery Current | Input only, optional |
| 16 | GPIO16 | UART2_RX | GPS TX | |
| 17 | GPIO17 | UART2_TX | GPS RX | |
| 19 | GPIO2 | Digital Out | Status LED | Built-in LED on some boards |
| 21 | GPIO4 | — | — | Available |
| 23 | GPIO5 | — | — | Available |
| 25 | GPIO18 | — | — | Available |
| 26 | GPIO19 | — | — | Available |
| 27 | GPIO21 | I2C SDA | IMU, ENV, Mag | 4.7kΩ pullup |
| 28 | GPIO22 | I2C SCL | IMU, ENV, Mag | 4.7kΩ pullup |
| 29 | GPIO23 | — | — | Available |
| 30 | 5V | Power In | From BEC (5V) | USB alternative |

### I2C Bus (Shared)

```
I2C Bus (GPIO21=SDA, GPIO22=SCL, 4.7kΩ pullups to 3.3V)
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │  3V3 ──┬──── 4.7kΩ ────┬──── 4.7kΩ ────┐                   │
    │        │               │               │                   │
    │       SDA             SCL             (other)             │
    │        │               │               │                   │
    │  ┌─────┴─────┐  ┌──────┴──────┐  ┌─────┴─────┐           │
    │  │           │  │             │  │           │           │
    │ IMU       ENV Sensor    Magnetometer  (other)           │
    │ (0x68)    (0x76/0x77)   (0x0C/0x1E)                    │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```

### UART (GPS)

```
UART2 (GPIO16=RX, GPIO17=TX)
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │  GPS TX ──────► GPIO16 (UART2_RX)                          │
    │  GPS RX ──────► GPIO17 (UART2_TX)                          │
    │                                                             │
    │  Baud: 9600 (default) or 115200 (configured via UBX)       │
    │  Protocol: NMEA or UBX binary                               │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```

---

## Antenna Placement

### GPS Antenna
- Mount on top of drone frame, clear view of sky
- Keep away from ESC/motor wires (EMI)
- Use ceramic patch or active antenna with LNA

### ESP32 Wi-Fi Antenna
- PCB antenna on ESP32 module — keep clear of metal
- Minimum 10mm clearance from carbon fiber, batteries, motors
- Orient vertically for best ground station reception

### HC-12 Alternative (if using 433MHz instead of Wi-Fi)
- Spring antenna or SMA whip
- Mount vertically on tail/frame
- Keep away from carbon fiber

---

## Testing Checklist

### Bench Testing (Before Flight)

| Test | Method | Expected |
|------|--------|----------|
| I2C Scan | `Wire.scan()` | 0x68 (IMU), 0x76/0x77 (ENV), 0x0C/0x1E (Mag) |
| GPS Fix | Serial monitor UBX/NMEA | Valid lat/lon, ≥6 satellites |
| IMU Data | Read accel/gyro | Reasonable values, responds to movement |
| ENV Data | Read temp/pressure | ~25°C, ~1013 hPa |
| Battery ADC | Measure known voltage | Matches multimeter ±0.1V |
| Wi-Fi Connect | Connect to Pi AP | RSSI > -70 dBm |
| UDP Send | Wireshark on Pi | Packets arriving at 192.168.50.1:5007 |
| Sequence Numbers | Check Pi logs | Monotonically increasing |
| JSON Validation | Pi gateway logs | No parse errors |

### In-Flight Telemetry Verification

```bash
# On Pi Gateway - monitor incoming drone packets
tcpdump -i wlan0 -n udp port 5007 -A

# Or use the gateway API
curl http://192.168.50.1:8001/api/drone/status

# Expected JSON response:
{
  "device_id": "esp32-drone",
  "sequence": 1234,
  "timestamp_ms": 1234567890123,
  "flight_status": "CRUISING",
  "orientation": {"roll": 1.2, "pitch": -0.5, "yaw": 180.0},
  "environment": {"temperature_c": 26.8, "pressure_hpa": 1013.2, "humidity_pct": 48.0},
  "gps": {"latitude": 12.9716, "longitude": 77.5946, "altitude_m": 50.0},
  "battery": {"voltage_v": 11.1, "percentage": 85.0}
}
```

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| GPS no fix | Antenna blocked / indoor | Move outdoors, check antenna connection |
| GPS wrong baud | Module default ≠ code | Use UBX to configure, or match baud in code |
| IMU not found | Wrong I2C address | Scan bus, check AD0 pin (GND=0x68, 3.3V=0x69) |
| IMU drift | No calibration | Calibrate gyro bias at startup, use magnetometer for yaw |
| Battery voltage wrong | Divider ratio wrong | Measure R1/R2 actual values, recalculate |
| Wi-Fi disconnects | Antenna blocked / EMI | Reposition ESP32, add shielding, check power |
| UDP packets lost | Network congestion | Reduce telemetry rate, check Pi CPU load |
| Sequence rollover | 16-bit counter | Use 32-bit sequence, handle RFC 1982 in gateway |

---

## Related Documents

- [Drone Hardware](hardware/drone.md) — Sensor specs, telemetry format, Pi gateway
- [Wiring Index](README.md) — All wiring docs
- [Hardware Overview](hardware/hardware-overview.md) — BOM and summary
- [Drone UDP Protocol](protocols/drone-udp.md) — JSON schema and sequence validation
- [Network Architecture](architecture/network-architecture.md) — UDP 5007 details