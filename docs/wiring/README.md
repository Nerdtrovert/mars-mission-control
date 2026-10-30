# Wiring Documentation Index

This directory contains wiring diagrams and connection guides for each subsystem.

## Files

| File | Subsystem | Status |
|------|-----------|--------|
| [lander-wiring.md](lander-wiring.md) | Lander ESP32 | ✅ Complete |
| [rover-wiring.md](rover-wiring.md) | Rover Chassis | ⚠️ Partial (MCU not in repo) |
| [drone-wiring.md](drone-wiring.md) | Drone Controller | ⚠️ Partial (MCU not in repo) |

## Quick Reference

### Lander (ESP32) — Complete Wiring

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LANDER WIRING SUMMARY                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ESP32 DevKit V1                                                    │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  GPIO21 ───► I2C SDA ───► LCD (0x27) + BMP280 (0x76)       │   │
│  │  GPIO22 ───► I2C SCL ───► LCD (0x27) + BMP280 (0x76)       │   │
│  │  GPIO17 ───► DHT11 Data (4.7k–10kΩ pullup to 3.3V)          │   │
│  │  GPIO25 ───► Green LED (+220–330Ω to GND)                   │   │
│  │  GPIO26 ───► Red LED (+220–330Ω to GND)                     │   │
│  │  3.3V   ───► BMP280 VCC, DHT11 VCC                          │   │
│  │  5V     ───► 20x4 LCD VCC (VIN)                             │   │
│  │  GND    ───► All grounds                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  I2C Bus:                                                           │
│  ┌─────────┐     ┌─────────┐     ┌─────────┐                       │
│  │  ESP32  │────►│  BMP280 │     │   LCD   │                       │
│  │ (Master)│     │  0x76   │     │  0x27   │                       │
│  └─────────┘     └─────────┘     └─────────┘                       │
│       │              │              │                                │
│       └──────────────┴──────────────┘                                │
│                  4.7kΩ pullups on SDA/SCL                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Rover — Partial Wiring (Chassis MCU not in repo)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ROVER WIRING (TYPICAL)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ROVER MCU (Arduino/ESP32)                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  HC-SR04:                                                   │   │
│  │    Trig ──► Digital Out                                     │   │
│  │    Echo ──► Digital In                                      │   │
│  │    VCC  ──► 5V                                              │   │
│  │    GND  ──► GND                                             │   │
│  │                                                              │   │
│  │  MPU6050:                                                   │   │
│  │    SDA  ──► I2C SDA                                         │   │
│  │    SCL  ──► I2C SCL                                         │   │
│  │    VCC  ──► 3.3V                                            │   │
│  │    GND  ──► GND                                             │   │
│  │                                                              │   │
│  │  HC-12:                                                     │   │
│  │    VCC  ──► 3.3V                                            │   │
│  │    GND  ──► GND                                             │   │
│  │    TX   ──► MCU RX                                          │   │
│  │    RX   ──► MCU TX                                          │   │
│  │    SET  ──► GND (transparent mode)                          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Laptop Side:                                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  HC-12 USB Adapter ──► USB Port ──► Tkinter GUI             │   │
│  │  (9600 baud, 8N1)                                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Drone — Partial Wiring (Flight Controller not in repo)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DRONE WIRING (TYPICAL)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  DRONE ESP32                                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  GPS (UART2):                                               │   │
│  │    GPS_TX ──► GPIO16 (UART2_RX)                             │   │
│  │    GPS_RX ──► GPIO17 (UART2_TX)                             │   │
│  │                                                              │   │
│  │  IMU + ENV (I2C shared):                                    │   │
│  │    SDA    ──► GPIO21                                        │   │
│  │    SCL    ──► GPIO22                                        │   │
│  │    VCC    ──► 3.3V                                          │   │
│  │    GND    ──► GND                                           │   │
│  │                                                              │   │
│  │  Battery Monitor:                                           │   │
│  │    VBAT ──► Divider (100k/10k) ──► GPIO34 (ADC1_6)         │   │
│  │                                                              │   │
│  │  Status LED:                                                │   │
│  │    LED    ──► GPIO2 (built-in) or GPIO5                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Conventions

- All diagrams show **logical connections** — physical layout may vary
- GPIO numbers refer to **ESP32 GPIO numbers**, not pin numbers
- I2C pullups: 4.7kΩ to 3.3V (one set per bus, not per device)
- LED current limiting: 220Ω for 5mm LEDs @ 3.3V
- WS2812B: 330Ω series resistor on DIN, level shifter recommended
- HC-12: 3.3V logic only, do not connect directly to 5V MCU pins

## Related Documents

- [Lander Hardware](hardware/lander.md) — Detailed pinout and specs
- [Rover Hardware](hardware/rover.md) — Sensor details
- [Drone Hardware](hardware/drone.md) — Expected sensor configuration
- [Hardware Overview](hardware/hardware-overview.md) — Bill of materials