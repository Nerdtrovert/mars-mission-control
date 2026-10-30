# Lander Hardware Details

## ESP32-WROOM-32 / DevKit V1

### Pinout Reference

```
          ESP32 DevKit V1 (30-pin)
    ┌─────────────────────────────────────────┐
    │                                         │
    │  3V3  (1)  ●──────────────────●  (30) 5V (USB / VIN)
    │  EN   (2)  ●                  ●  (29) GND
    │  VP   (3)  ● (GPIO36, Input)  ●  (28) GPIO23
    │  VN   (4)  ● (GPIO39, Input)  ●  (27) GPIO22 (I2C SCL) ──── BMP280, LCD
    │  D34  (5)  ● (GPIO34, Input)  ●  (26) GPIO1 (TX0)
    │  D35  (6)  ● (GPIO35, Input)  ●  (25) GPIO3 (RX0)
    │  D32  (7)  ●                  ●  (24) GPIO21 (I2C SDA) ──── BMP280, LCD
    │  D33  (8)  ●                  ●  (23) GPIO19
    │  D25  (9)  ●────── Green LED  ●  (22) GPIO18
    │  D26  (10) ●────── Red LED    ●  (21) GPIO5
    │  D27  (11) ●                  ●  (20) GPIO17 ────────────── DHT11 Data
    │  D14  (12) ●                  ●  (19) GPIO16
    │  D12  (13) ●                  ●  (18) GPIO4
    │  GND  (14) ●                  ●  (17) GPIO0 (Boot)
    │  D13  (15) ●                  ●  (16) GPIO2 (Onboard LED)
    │                                         │
    └─────────────────────────────────────────┘
```

### Lander Pin Assignments (Authoritative — lander.ino & Mars_Lander_Wiring_Structure.txt)

| Component / Function | ESP32 GPIO | Direction | Electrical & Wiring Notes |
|----------------------|------------|-----------|---------------------------|
| **Green Status LED** | GPIO 25 | OUTPUT | Active HIGH via series resistor (220–330Ω). Indicates ACTIVE operating mode. |
| **Red Status LED** | GPIO 26 | OUTPUT | Active HIGH via series resistor (220–330Ω). Blinks 300ms on sensor fault. |
| **DHT11 Environmental** | GPIO 17 | BIDIR | 1-wire digital data pin (4.7kΩ–10kΩ pull-up to 3.3V). |
| **BMP280 I2C (SDA)** | GPIO 21 | BIDIR | Shared I2C bus (3.3V logic level). |
| **BMP280 I2C (SCL)** | GPIO 22 | OUTPUT | Shared I2C bus (3.3V clock, 100 kHz). |
| **20x4 LCD I2C (SDA)** | GPIO 21 | BIDIR | Shared I2C bus with BMP280 (address 0x27 or 0x3F). |
| **20x4 LCD I2C (SCL)** | GPIO 22 | OUTPUT | Shared I2C bus with BMP280. |
| **BMP280 VCC** | 3V3 Rail | POWER | 3.3V power rail (< 1 mA). |
| **DHT11 VCC** | 3V3 Rail | POWER | 3.3V power rail (1–2.5 mA). |
| **20x4 LCD VCC** | 5V / VIN | POWER | 5V rail for PCF8574 backlight and contrast (20–50 mA). |
| **Common Ground** | GND | GROUND | Common ground shared by ESP32 and all peripherals. |
| **USB Serial** | USB UART | BIDIR | 115200 baud, 8N1. Local programming and debug output only. |

### Reserved & Prohibited Pins

- **Prohibited (Internal Flash)**: GPIO 6–11 are hardwired internally to the SPI flash memory on ESP32-WROOM-32. Never connect external components to GPIO 6–11.
- **Input-Only Pins**: GPIO 34, 35, 36 (VP), 39 (VN) lack internal pull-up/pull-down resistors and cannot output signals.
- **Retired Pins**: GPIO 18, 19, 23, 27 (former WS2812B), 32, 33 (former ramp/servo/switch pins) were retired in ADR-023 and must remain disconnected.
- **Voltage Limits**: ESP32 GPIO pins are **strictly 3.3V logic and NOT 5V tolerant**. Never connect 5V logic directly to GPIOs.

---

## Sensor Specifications

### BMP280 (Temperature & Pressure)

| Parameter | Value |
|-----------|-------|
| **Interface** | I2C |
| **Address** | 0x76 (SDO tied to GND) |
| **Supply** | 3.3V |
| **Temperature Range** | -40°C to +85°C |
| **Temperature Accuracy** | ±1.0°C |
| **Pressure Range** | 300-1100 hPa |
| **Pressure Accuracy** | ±1.0 hPa (absolute) |
| **Sampling Rate** | Configurable, ~1 Hz used |
| **Oversampling** | Temperature x1, Pressure x16 (firmware) |
| **IIR Filter** | Coefficient 4 (firmware) |

**Wiring:**
```
BMP280          ESP32
─────────────────────────
VCC    ──────► 3V3 (Pin 1)
GND    ──────► GND (Pin 2/17)
SCL    ──────► GPIO22 (Pin 28)
SDA    ──────► GPIO21 (Pin 27)
SDO    ──────► GND (for 0x76 address)
CSB    ──────► 3V3 (I2C mode)
```

### DHT11 (Temperature & Humidity)

| Parameter | Value |
|-----------|-------|
| **Interface** | Single-wire (proprietary) |
| **Supply** | 5V (or 3.3V) |
| **Temperature Range** | 0°C to 50°C |
| **Temperature Accuracy** | ±2°C |
| **Humidity Range** | 20-90% RH |
| **Humidity Accuracy** | ±5% RH |
| **Sampling Period** | ≥ 1s (firmware uses 2s) |
| **Signal** | Open-drain, needs pullup |

**Wiring:**
```
DHT11           ESP32
─────────────────────────
VCC    ──────► 5V (Pin 30)  [or 3V3]
GND    ──────► GND
DATA   ──────► GPIO4 (Pin 21) ──► 10kΩ ───► 3V3
```

---

## Display & Indicators

### 20x4 I2C Character LCD

| Parameter | Value |
|-----------|-------|
| **Controller** | HD44780 via PCF8574 backpack |
| **Interface** | I2C |
| **Address** | 0x27 (default, A0-A2 open) |
| **Supply** | 5V (backlight) / 3.3V (logic) |
| **Columns** | 20 |
| **Rows** | 4 |
| **Backlight** | PWM controllable via backpack |

**Wiring:**
```
LCD (PCF8574)   ESP32
─────────────────────────
VCC    ──────► 3V3 (Pin 1)  [or 5V for brighter backlight]
GND    ──────► GND
SDA    ──────► GPIO21 (Pin 27)
SCL    ──────► GPIO22 (Pin 28)
```

### LED Indicators

| LED | GPIO | Color | Purpose | Behavior |
|-----|------|-------|---------|----------|
| **Mode** | GPIO5 | Green | Operation mode | ON = ACTIVE, OFF = STANDBY |
| **Error** | GPIO18 | Red | Sensor health | Blink = sensor failure, OFF = OK |
| **RGB Status** | GPIO19 | RGB (WS2812B) | Composite status | See firmware for patterns |

**Wiring (Discrete LEDs):**
```
Green LED:     GPIO5 ──► 220Ω ──► LED Anode
               LED Cathode ──► GND

Red LED:       GPIO18 ──► 220Ω ──► LED Anode
               LED Cathode ──► GND
```

### WS2812B RGB LED

| Parameter | Value |
|-----------|-------|
| **Type** | Single WS2812B (5050 package) |
| **Data Pin** | GPIO19 |
| **Supply** | 5V (from USB) |
| **Logic Level** | 3.3V (works but level shifter recommended) |
| **Protocol** | 800 kHz timing-critical |

**Wiring:**
```
WS2812B         ESP32
─────────────────────────
VDD    ──────► 5V (Pin 30)
GND    ──────► GND
DIN    ──────► GPIO19 (Pin 26)  [add 330Ω series resistor]
```

> **Note**: For reliable WS2812B operation at 3.3V logic, add a 330Ω series resistor on DIN and consider a 74AHCT125 level shifter for production.

---

## Wi-Fi Configuration

### Station Mode (Connects to Pi AP)

```cpp
// From lander.ino
const char* WIFI_SSID = "Mission-Control";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* GATEWAY_HOST = "192.168.50.1";
const uint16_t GATEWAY_PORT = 5006;
```

- **Mode**: Wi-Fi Station (STA)
- **Band**: 2.4 GHz only
- **Security**: WPA2-PSK
- **Reconnection**: Automatic, 1s retry interval
- **IP**: DHCP from Pi (192.168.50.10-100)

---

## Firmware Architecture (lander.ino v1.5.0)

### FreeRTOS Tasks

| Task | Core | Priority | Period | Function |
|------|------|----------|--------|----------|
| `sensorTask` | 0 | 2 | 1000ms (ACTIVE) / 5000ms (STANDBY) | Read BMP280 + DHT11, build telemetry |
| `lcdTask` | 1 | 1 | 4000ms (page rotate) / event-driven | LCD pages 0-4, mission_display |
| `wifiTask` | 0 | 3 | Event-driven | TCP connection, JSON I/O, commands |
| `ledTask` | 1 | 0 | 500ms / event-driven | Green/Red/WS2812B patterns |

### Task Communication (FreeRTOS Queues)

```
sensorTask ──────► [telemetryQueue] ──────► wifiTask
                       (10 items)
                       
wifiTask ─────────► [displayQueue] ──────► lcdTask
                       (5 items)
                       mission_display messages

ledTask ◄────────── [statusQueue] ◄────── wifiTask/sensorTask
                       (5 items)
                       mode changes, sensor health
```

### LCD Pages (5 pages, 4-second rotation)

| Page | Title | Content |
|------|-------|---------|
| **0** | SYSTEM | Mode, WiFi RSSI, Uptime, Free Heap |
| **1** | BMP280 | Temp, Pressure, Altitude, Sensor State |
| **2** | DHT11 | Temp, Humidity, Sensor State |
| **3** | ROVER | Distance, Pitch, Roll, CMD, Mode, Signal |
| **4** | DRONE | Flight Status, Latitude, Longitude, Signal |

### Sensor Health Monitoring

```cpp
// Staleness thresholds (ms)
#define BMP280_STALE_MS   5000
#define DHT11_STALE_MS    5000

// Health states
enum SensorState { OK, STALE, FAILED };

// Red LED blink patterns:
// - 2 blinks: BMP280 failed
// - 3 blinks: DHT11 failed  
// - 4 blinks: Both failed
// - Solid ON: Critical error
```

### TCP Protocol Implementation

**Connection Management:**
- ESP32 initiates TCP connection to `192.168.50.1:5006`
- Persistent connection; reconnects on disconnect (1s retry)
- Pi Gateway accepts new connection, closes old one

**Framing:**
- Newline-delimited JSON (`\n` terminated)
- Max TX buffer: 768 bytes
- Max RX buffer: 4096 bytes (Pi side)

**Telemetry Rate:**
- ACTIVE mode: ~1 Hz
- STANDBY mode: ~0.2 Hz (every 5s)

---

## Power Supply Design

### Requirements

| Rail | Voltage | Max Current | Sources |
|------|---------|-------------|---------|
| **5V** | 5.0V ±5% | 500mA | USB-C (VBUS) |
| **3.3V** | 3.3V ±3% | 300mA | ESP32 onboard LDO (AMS1117-3.3) |

### Power Budget

| Component | 5V Rail | 3.3V Rail |
|-----------|---------|-----------|
| ESP32 (Wi-Fi TX) | — | 250mA peak |
| ESP32 (idle) | — | 80mA |
| BMP280 | — | 3.6mA (measuring) |
| DHT11 | 2.5mA | — |
| LCD (backlight on) | 30mA | — |
| Green LED | — | 5mA |
| Red LED | — | 5mA |
| WS2812B (white) | 20mA | — |
| **Total (typical)** | **~52mA** | **~260mA** |
| **Total (peak Wi-Fi)** | **~52mA** | **~400mA** |

### Power Sequencing
1. USB 5V applied → ESP32 onboard LDO enables 3.3V
2. 3.3V stable → ESP32 boots
3. Firmware initializes I2C, GPIOs, Wi-Fi
4. Sensors powered continuously from 3.3V/5V

---

## Mechanical / Mounting

### Suggested Layout (Perfboard 7x9 cm)

```
    ┌─────────────────────────────────────┐
    │  USB-C                              │
    │  ┌─────────────────────────────┐    │
    │  │ ESP32 DevKit V1             │    │
    │  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │    │
    │  └─────────────────────────────┘    │
    │                                     │
    │  ┌─────────┐  ┌─────────────────┐  │
    │  │ BMP280  │  │    DHT11        │  │
    │  │  (I2C)  │  │   (GPIO4)       │  │
    │  └─────────┘  └─────────────────┘  │
    │                                     │
    │  ┌─────────────────────────────┐    │
    │  │     20x4 LCD (I2C)          │    │
    │  └─────────────────────────────┘    │
    │                                     │
    │  ● Green  ● Red  ● WS2812B          │
    │                                     │
    └─────────────────────────────────────┘
```

### Enclosure Considerations
- **Ventilation**: BMP280 and DHT11 need airflow for accurate readings
- **LCD Visibility**: Mount with viewing angle ~0-30° from horizontal
- **LED Visibility**: Status LEDs should be visible from top/side
- **Antenna**: Keep ESP32 PCB antenna clear of metal (≥10mm)
- **USB Access**: Programming port accessible for firmware updates

---

## Firmware Build & Flash

### PlatformIO (Recommended)
```ini
; platformio.ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps = 
    adafruit/Adafruit BMP280 Library @ ^2.6.0
    adafruit/DHT sensor library @ ^1.4.6
    bblanchon/ArduinoJson @ ^7.0.4
    fastled/FastLED @ ^3.6.0
    liquidcrystal-i2c / LiquidCrystal I2C @ ^1.1.0
build_flags = 
    -DCORE_DEBUG_LEVEL=0
```

### Arduino IDE
1. Install ESP32 board package: `https://dl.espressif.com/dl/package_esp32_index.json`
2. Board: **ESP32 Dev Module**
3. Libraries: Adafruit BMP280, DHT, ArduinoJson, FastLED, LiquidCrystal_I2C
4. Upload speed: 921600

### Flash Command
```bash
pio run -t upload
# or
idf.py flash monitor
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| No Wi-Fi connection | Wrong SSID/Password | Check `lander.ino` constants match Pi AP |
| LCD shows garbage | Wrong I2C address | Scan I2C: `Wire.scan()` — use 0x27 or 0x3F |
| BMP280 not found | Wiring / Address | Check SDA/SCL, SDO=GND for 0x76 |
| DHT11 NaN readings | Timing / Pullup | 10kΩ pullup, ≥2s between reads |
| Red LED blinking | Sensor failure | Check specific blink pattern (2=BMP, 3=DHT, 4=both) |
| TCP connection drops | Pi Gateway restart | ESP32 auto-reconnects (1s retry) |
| WS2812B wrong colors | Logic level | Add 330Ω series + level shifter |
| Brownout reset | Insufficient 5V | Use 5V/2A+ supply, short USB cable |

---

## Related Documents

- [Hardware Overview](hardware-overview.md) — All subsystems summary
- [Lander Wiring](wiring/lander-wiring.md) — Schematics and connection diagrams
- [Network Architecture](architecture/network-architecture.md) — Wi-Fi and TCP details
- [TCP Protocol](protocols/tcp-protocol.md) — JSON message formats
- [Software Architecture](architecture/software-architecture.md) — Firmware task structure