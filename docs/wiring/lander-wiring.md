# Lander ESP32 Wiring Diagrams

## Complete Schematic

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LANDER ESP32 — COMPLETE WIRING                       │
└─────────────────────────────────────────────────────────────────────────────┘

                           ESP32 DevKit V1 (30-pin)
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                         │
    │   USB-C ◄────────────────────────────────────────── 5V / Programming    │
    │                                                                         │
    │   3V3  (Pin 1)  ──────────────────► 3.3V Rail (BMP280 VCC, DHT11 VCC)    │
    │   EN   (Pin 2)                                                          │
    │   VP   (Pin 3)  (GPIO36, Input only)                                    │
    │   VN   (Pin 4)  (GPIO39, Input only)                                    │
    │   D34  (Pin 5)  (GPIO34, Input only)                                    │
    │   D35  (Pin 6)  (GPIO35, Input only)                                    │
    │   D32  (Pin 7)                                                          │
    │   D33  (Pin 8)                                                          │
    │   D25  (Pin 9)  ──► GREEN LED Anode ──► 220Ω ──► GND (Active HIGH)      │
    │   D26  (Pin 10) ──► RED LED Anode   ──► 220Ω ──► GND (Fault blink)      │
    │   D27  (Pin 11) (Reserved / Unused)                                     │
    │   D14  (Pin 12)                                                         │
    │   D12  (Pin 13)                                                         │
    │   GND  (Pin 14) ──────────────────► Common GND Bus                      │
    │   D13  (Pin 15)                                                         │
    │                                                                         │
    │   D23  (Pin 28)                                                         │
    │   D22  (Pin 27) ──► I2C SCL ──────┬──► BMP280 SCL (0x76)                │
    │                                   └──► 20x4 LCD SCL (PCF8574, 0x27)     │
    │   D21  (Pin 24) ──► I2C SDA ──────┬──► BMP280 SDA (0x76)                │
    │                                   └──► 20x4 LCD SDA (PCF8574, 0x27)     │
    │   D19  (Pin 23) (Reserved / Unused)                                     │
    │   D18  (Pin 22) (Reserved / Unused)                                     │
    │   D5   (Pin 21)                                                         │
    │   D17  (Pin 20) ──► DHT11 DATA ───┬──► 1-wire Sensor Data               │
    │                                   └──► 4.7kΩ–10kΩ Pullup to 3.3V        │
    │   D16  (Pin 19)                                                         │
    │   D4   (Pin 18)                                                         │
    │   GND  (Pin 29) ──────────────────► Common GND Bus                      │
    │   5V   (Pin 30) ──────────────────► 5V VIN Rail (20x4 LCD VCC)          │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘
                                        │                    │
                                ┌───────┴───────┐    ┌──────┴──────┐
                                │   BMP280      │    │    DHT11    │
                                │   (0x76)      │    │             │
                                │ ┌───────────┐ │    │ ┌─────────┐ │
                                │ │ VCC ──► 3V3 │ │    │ │ VCC ──► 3V3 │ │
                                │ │ GND ──► GND │ │    │ │ GND ──► GND │ │
                                │ │ SDA ──► GPIO21   │ │ DATA ──► GPIO17│
                                │ │ SCL ──► GPIO22   │ │   (10k↑ 3.3V) │ │
                                │ │ SDO ──► GND │ │    │ └─────────┘ │
                                │ │ CSB ──► 3V3 │ │    │             │
                                │ └───────────┘ │    └─────────────┘
                                └───────────────┘
                                    │
                                    │
                            ┌───────┴───────┐
                            │   20x4 LCD    │
                            │  (PCF8574)    │
                            │ ┌───────────┐ │
                            │ │ VCC ──► 3V3 │ │  (or 5V for brighter backlight)
                            │ │ GND ──► GND │ │
                            │ │ SDA ──► SDA │ │
                            │ │ SCL ──► SCL │ │
                            │ │ A0-A2=NC    │ │  (Address 0x27)
                            │ └───────────┘ │
                            └───────────────┘
```

---

## I2C Bus Detail

### Bus Topology

```
                    I2C BUS (GPIO21=SDA, GPIO22=SCL)
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │    3V3 ──┬───────── 4.7kΩ ────────┬───────── 4.7kΩ ───────┐│
    │          │                         │                       ││
    │         SDA                       SCL                      ││
    │          │                         │                       ││
    │    ┌─────┴─────┐           ┌──────┴──────┐                ││
    │    │           │           │             │                ││
    │  BMP280     LCD (0x27)    (other        (other            ││
    │  (0x76)                    devices)      devices)         ││
    │                                                             ││
    │    Total capacitance < 400pF for standard mode (100kHz)    ││
    │    Total capacitance < 100pF for fast mode (400kHz)        ││
    │                                                             ││
    └─────────────────────────────────────────────────────────────┘
```

### I2C Address Verification

Run I2C scanner on ESP32 to verify addresses:

```cpp
// I2C Scanner - run once at startup
void scanI2C() {
    Wire.begin(21, 22);  // SDA, SCL
    Serial.println("Scanning I2C bus...");
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("Found device at 0x%02X\n", addr);
        }
    }
}

// Expected output:
// Found device at 0x27  (LCD PCF8574)
// Found device at 0x76  (BMP280, SDO=GND)
// OR 0x77 (BMP280, SDO=3V3)
```

---

## Power Distribution

### Power Rails

```
                    POWER DISTRIBUTION
    ┌─────────────────────────────────────────────────────────────┐
    │                                                             │
    │   USB 5V (VBUS) ◄──────────────────────────────────────┐   │
    │        │                                                │   │
    │        ├──► ESP32 Pin 30 (5V)                           │   │
    │        │                                                │   │
    │        ├──► DHT11 VCC                                   │   │
    │        │                                                │   │
    │        ├──► WS2812B VDD                                 │   │
    │        │                                                │   │
    │        └──► LCD Backlight (via PCF8574, if 5V tolerant) │   │
    │                                                             │
    │   ESP32 Onboard LDO (AMS1117-3.3)                        │   │
    │        │                                                │   │
    │        ├──► ESP32 Pin 1 (3V3) ──► BMP280 VCC            │   │
    │        │                     ├──► LCD VCC (logic)       │   │
    │        │                     ├──► I2C Pullups (4.7kΩ)   │   │
    │        │                     └──► DHT11 Pullup (10kΩ)    │   │
    │        │                                                │   │
    │        └──► Green LED (via 220Ω)                        │   │
    │             Red LED (via 220Ω)                          │   │
    │                                                             │
    │   GND ◄──────────────────────────────────────────────────┘   │
    │        │                                                │   │
    │        ├──► All component GND pins                       │   │
    │        └──► ESP32 Pins 2, 17                             │   │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
```

### Current Budget

| Rail | Component | Current (typ) | Current (max) |
|------|-----------|---------------|---------------|
| **5V** | DHT11 | 2.5 mA | 2.5 mA |
| | WS2812B (white) | 20 mA | 60 mA |
| | LCD Backlight | 20-30 mA | 40 mA |
| **5V Total** | | **~43 mA** | **~103 mA** |
| **3.3V** | ESP32 (Wi-Fi TX) | 180 mA | 250 mA |
| | ESP32 (idle) | 80 mA | 120 mA |
| | BMP280 | 3.6 μA | 3.6 mA |
| | LCD Logic | 1 mA | 2 mA |
| | Green LED | 5 mA | 10 mA |
| | Red LED | 5 mA | 10 mA |
| | I2C Pullups (3x 4.7kΩ) | 2.1 mA | 2.1 mA |
| | DHT11 Pullup (10kΩ) | 0.33 mA | 0.33 mA |
| **3.3V Total** | | **~197 mA** | **~298 mA** |

> **Power Supply Recommendation**: 5V / 2A minimum (USB-C 5V/3A preferred)

---

## Component Wiring Details

### BMP280 Breakout

```
BMP280 Module          ESP32
──────────────────────────────────
VCC      ──────────► 3V3 (Pin 1)
GND      ──────────► GND
SCL      ──────────► GPIO22 (Pin 28)
SDA      ──────────► GPIO21 (Pin 27)
SDO      ──────────► GND (for I2C addr 0x76)
CSB      ──────────► 3V3 (I2C mode)
```

**Note**: If your BMP280 module has no SDO pin exposed, it may default to 0x77. Check with I2C scanner.

### DHT11 Module

```
DHT11 Module           ESP32
──────────────────────────────────
VCC      ──────────► 5V (Pin 30)  [or 3V3]
GND      ──────────► GND
DATA     ──────────► GPIO4 (Pin 21)
                │
                └── 10kΩ ──► 3V3 (pullup)
```

**Note**: Some DHT11 modules have onboard pullup resistor. If readings are unreliable, add external 10kΩ.

### 20x4 I2C LCD (PCF8574 Backpack)

```
LCD Module             ESP32
──────────────────────────────────
VCC      ──────────► 3V3 (Pin 1)  [or 5V]
GND      ──────────► GND
SDA      ──────────► GPIO21 (Pin 27)
SCL      ──────────► GPIO22 (Pin 28)

Backpack Jumpers (A0, A1, A2):
  All OPEN (NC) = Address 0x27  (default)
  A0 closed = 0x26
  A1 closed = 0x25
  A2 closed = 0x23
```

**Contrast Adjustment**: Potentiometer on backpack — adjust for visibility.

### WS2812B RGB LED

```
WS2812B (Single)       ESP32
──────────────────────────────────
VDD      ──────────► 5V (Pin 30)
GND      ──────────► GND
DIN      ──────────► 330Ω ──► GPIO19 (Pin 26)
                         │
                      (optional)
                      74AHCT125
                      Level Shifter
                      (3.3V → 5V logic)
```

**Level Shifter Recommended**: WS2812B requires ~0.7×VDD for logic HIGH. At 5V VDD, that's 3.5V — ESP32 3.3V may be marginal.

```
    ESP32 GPIO19 ──► 330Ω ──► 74AHCT125 1A
                                    │
                    5V ────────────┼────► 74AHCT125 VCC
                                    │
                    GND ────────────┼────► 74AHCT125 GND
                                    │
                    1Y ─────────────┼────► WS2812B DIN
```

### Discrete LEDs (Green/Red)

```
GREEN LED (Mode)       ESP32
──────────────────────────────────
Anode  (+)  ─────────► 220Ω ──► GPIO5 (Pin 23)
Cathode (-) ──────────► GND

RED LED (Error)        ESP32
──────────────────────────────────
Anode  (+)  ─────────► 220Ω ──► GPIO18 (Pin 25)
Cathode (-) ──────────► GND
```

---

## Perfboard Layout Suggestion

### 7×9 cm Perfboard (2.54mm pitch)

```
    ┌─────────────────────────────────────────────────────────────────┐
    │  COLUMNS: 1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18│
    │ ROWS                                                             │
    │ A  USB-C ◄──────────────────────────────────────────────────►  │
    │ B                                                                 │
    │ C  ESP32 DevKit V1 (spans rows C-H, cols 2-17)                │
    │ D                                                                 │
    │ E                                                                 │
    │ F                                                                 │
    │ G                                                                 │
    │ H                                                                 │
    │ I                                                                 │
    │ J  BMP280 (cols 2-5)     DHT11 (cols 7-9)                      │
    │ K                                                                 │
    │ L  LCD (cols 1-18, rows L-N)                                   │
    │ M                                                                 │
    │ N                                                                 │
    │ O  ● GREEN  ● RED  ● WS2812B  (cols 2, 5, 8)                  │
    │ P                                                                 │
    └─────────────────────────────────────────────────────────────────┘
```

### Wiring Order (Recommended)

1. **Power rails** — Run 5V and GND along board edges
2. **3.3V rail** — Run from ESP32 Pin 1 along opposite edge
3. **I2C bus** — SDA/SCL from ESP32 to BMP280 to LCD (daisy chain)
4. **DHT11** — Single wire + pullup
5. **LEDs** — Resistors on perfboard, LEDs on edge for visibility
6. **WS2812B** — Place near ESP32, add level shifter if used

---

## Testing Connections

### Continuity Checklist

| Connection | Test | Expected |
|------------|------|----------|
| ESP32 Pin 1 (3V3) → BMP280 VCC | Continuity | ✓ |
| ESP32 Pin 1 (3V3) → LCD VCC | Continuity | ✓ |
| ESP32 Pin 1 (3V3) → I2C Pullups | Continuity | ✓ |
| ESP32 Pin 30 (5V) → DHT11 VCC | Continuity | ✓ |
| ESP32 Pin 30 (5V) → WS2812B VDD | Continuity | ✓ |
| ESP32 Pin 30 (5V) → LCD Backlight | Continuity | ✓ |
| ESP32 Pin 2/17 (GND) → All GND | Continuity | ✓ |
| ESP32 Pin 27 (GPIO21) → BMP280 SDA | Continuity | ✓ |
| ESP32 Pin 27 (GPIO21) → LCD SDA | Continuity | ✓ |
| ESP32 Pin 28 (GPIO22) → BMP280 SCL | Continuity | ✓ |
| ESP32 Pin 28 (GPIO22) → LCD SCL | Continuity | ✓ |
| ESP32 Pin 21 (GPIO4) → DHT11 DATA | Continuity | ✓ |
| ESP32 Pin 23 (GPIO5) → Green LED Anode | Continuity | ✓ |
| ESP32 Pin 25 (GPIO18) → Red LED Anode | Continuity | ✓ |
| ESP32 Pin 26 (GPIO19) → WS2812B DIN | Continuity | ✓ |
| BMP280 SDO → GND | Continuity | ✓ (for 0x76) |
| DHT11 DATA → 10kΩ → 3V3 | Resistance | ~10kΩ |
| I2C SDA → 4.7kΩ → 3V3 | Resistance | ~4.7kΩ |
| I2C SCL → 4.7kΩ → 3V3 | Resistance | ~4.7kΩ |
| Green LED Cathode → GND | Continuity | ✓ |
| Red LED Cathode → GND | Continuity | ✓ |
| WS2812B GND → GND | Continuity | ✓ |

### Functional Tests

```bash
# 1. I2C Scan
# Upload I2C scanner sketch, open Serial Monitor at 115200
# Should see: 0x27 (LCD), 0x76 (BMP280)

# 2. LCD Test
# Upload LiquidCrystal_I2C HelloWorld example
# Should display text on all 4 rows

# 3. BMP280 Test
# Upload Adafruit BMP280 test example
# Should print temperature, pressure, altitude

# 4. DHT11 Test
# Upload DHT test example
# Should print temperature, humidity (may show NaN if wiring wrong)

# 5. LED Test
# Blink GPIO5, GPIO18, GPIO19 (WS2812B color cycle)
# All should respond

# 6. Full Firmware
# Upload lander.ino
# Check Serial Monitor for:
#   - WiFi connected to "Mission-Control"
#   - TCP connected to 192.168.50.1:5006
#   - Telemetry sending every 1s (ACTIVE)
#   - LCD cycling pages 0-4 every 4s
```

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| LCD shows blocks/garbage | Wrong I2C address | Scan bus, use 0x27 or 0x3F |
| LCD blank | Contrast not set | Adjust potentiometer on backpack |
| BMP280 not found | SDO floating | Tie SDO to GND for 0x76 |
| DHT11 NaN | Timing/pullup | 10kΩ pullup, 2s min between reads |
| WS2812B wrong colors | Logic level | Add 74AHCT125 level shifter |
| Red LED blinking | Sensor failure | Check specific sensor (blink code) |
| WiFi won't connect | Credentials | Check SSID "Mission-Control", PSK "YOUR_WIFI_PASSWORD" |
| TCP connection fails | Pi not running | Verify Pi gateway on 192.168.50.1:5006 |

---

## Related Documents

- [Lander Hardware](hardware/lander.md) — Pinout, specs, firmware details
- [Wiring Index](README.md) — All wiring docs
- [Hardware Overview](hardware/hardware-overview.md) — BOM and summary
- [Network Architecture](architecture/network-architecture.md) — Wi-Fi and TCP config