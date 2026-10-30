# Mars Mission Control — Portfolio Project Description

## Short Description

Mars Mission Control is a distributed embedded telemetry system integrating a Mars Lander (ESP32), Surface Rover (HC-12 relay), and Aerial Drone (Wi-Fi UDP) through a Raspberry Pi edge gateway to a real-time dashboard. The system demonstrates end-to-end embedded firmware, wireless communication, edge aggregation, backend telemetry processing, and real-time visualization — all with zero external cloud dependencies.

---

## Detailed Description

Mars Mission Control was built as a local-first mission monitoring system for a Mars exploration exhibition. It integrates three independent hardware subsystems — a stationary lander, a mobile surface rover, and an aerial drone — each with distinct physical communication constraints, into a unified real-time monitoring platform.

The **Mars Lander** runs on an ESP32-WROOM-32 with environmental sensors (BMP280, DHT11) and a local 20×4 LCD display. It connects via Wi-Fi to a Raspberry Pi gateway over a persistent TCP stream, sending JSON telemetry at 1 Hz and receiving mode commands.

The **Surface Rover** uses an HC-SR04 ultrasonic sensor and MPU6050 IMU. Its microcontroller transmits ASCII packets at 9600 baud over 433 MHz HC-12 radio to a Windows laptop, which forwards validated UDP datagrams to the Pi gateway.

The **Aerial Drone** employs an ESP32-based flight controller transmitting JSON telemetry (GPS, IMU, environment, battery) directly to the Pi gateway over Wi-Fi UDP with RFC 1982 sequence validation.

The **Raspberry Pi 4 Gateway** runs a standalone FastAPI daemon that ingests all three streams, validates protocol-specific formats, tracks independent staleness states, and exposes a unified HTTP/WebSocket API. It also multiplexes rover and drone telemetry back to the lander's LCD over the existing TCP connection.

The **Development Machine Backend** connects to the gateway via WebSocket, normalizes telemetry, persists a 5-minute sliding window to SQLite, and broadcasts live updates to a vanilla JavaScript dashboard. The dashboard uses WebSocket primary with HTTP polling fallback, supporting graceful degradation.

The entire system operates in two mutually exclusive modes: **Simulation** (zero hardware, deterministic in-memory simulators) and **Network** (physical hardware via Pi gateway). No hybrid mode exists.

---

## Key Engineering Contributions

| Contribution | Description |
|---|---|
| **ESP32 FreeRTOS Firmware** | Four-task architecture (sensor polling, LCD rendering, Wi-Fi/TCP, LED control) with non-blocking I2C, 1-Wire, and LCD page rotation |
| **Multi-Protocol Gateway** | Asyncio TCP transport with line framing, ASCII UDP parser with 5-field validation, JSON UDP receiver with RFC 1982 rollover handling |
| **Runner Pattern Abstraction** | `BaseRunner` interface enabling zero-code-change switching between network and simulator implementations per subsystem |
| **Dual-Layer State Tracking** | Independent gateway health vs. device connectivity states with protocol-appropriate staleness thresholds |
| **Remote LCD Multiplexing** | `mission_display` messages over existing lander TCP connection with rate limiting (rover 4 Hz, drone 2 Hz) and heartbeat |
| **Deterministic Simulators** | Virtual clock, stepped execution, `IS_SIMULATOR` flag — never masquerades as hardware in production |
| **WebSocket + Polling Dashboard** | ES6 module architecture, exponential backoff reconnection, 2 s HTTP fallback, subsystem color coding |
| **rsync Deployment Pipeline** | Selective synchronization preserving Pi `.env`, databases, and firmware; excludes macOS binaries and frontend assets |

---

## Technical Highlights

- **Zero external dependencies** — Runs entirely on private local network; no cloud, MQTT broker, or internet required
- **Three heterogeneous telemetry paths unified** — TCP JSON, ASCII UDP relay, JSON UDP direct → single gateway API
- **Independent per-subsystem mode selection** — `GATEWAY_MODE`, `ROVER_MODE`, `DRONE_MODE` environment variables
- **RFC 1982 sequence validation** — 32-bit rollover handling for drone telemetry duplicate/out-of-order detection
- **5-minute SQLite sliding window** — WAL mode, automatic pruning, session reset without data loss
- **Non-blocking LCD rendering** — 5-page rotation with remote telemetry pages, FreeRTOS queue communication
- **Engineering-grade test suite** — 112 tests (69 backend, 43 gateway) covering parsers, simulators, lifecycle, contracts, integration
- **Bootloader text filtering** — Gateway ignores ESP32 ROM output during TCP connection establishment

---

## Suggested Portfolio Metadata

| Field | Value |
|---|---|
| **Project Title** | Mars Mission Control |
| **Category** | Embedded Systems / Distributed Telemetry / Real-Time Monitoring |
| **Technologies** | ESP32 (C/FreeRTOS), Raspberry Pi 4, Python/FastAPI, SQLite, WebSockets, Vanilla JS, TCP/UDP, HC-12 433 MHz, Wi-Fi |
| **Short Tagline** | Local-first distributed telemetry system for Mars exploration exhibition — lander, rover, drone unified |
| **GitHub Repository** | `<repository-url>` |
| **Live Demo** | Not applicable (local exhibition hardware) |
| **Simulation Demo** | `python run.py sim` → http://localhost:8000/dashboard |
| **Key Metrics** | 112 automated tests, 3 subsystems, 5 communication protocols, 2 operating modes, 0 external services |

---

## Dashboard Screenshots

The following screenshots are available in `docs/assets/screenshots/` and rendered in the root README.md:

| Screenshot | Description | Mode |
|---|---|---|
| `mission-control-dashboard.png` | Main landing screen with three subsystem cards | Simulation |
| `lander-status.png` | Lander environmental telemetry, state, commands, history, events, controls | Simulation |
| `rover-telemetry.png` | Rover terrain map, schematic, radar, telemetry grid | Simulation |
| `drone-telemetry.png` | Drone airspace radar, schematic, attitude, telemetry grid (top section) | Simulation |
| `drone-telemetry-detailed.png` | Drone full telemetry grid: flight status, altitude, GPS, battery, environment sensors | Simulation |

All screenshots captured from simulation mode — telemetry values are synthetic and do not represent physical hardware measurements.

---

## Architecture Diagram Reference

The system architecture diagram is available at:
- `docs/diagrams/system-architecture.mmd` (Mermaid)
- Rendered in the root README.md

---

## Verification Status

| Layer | Automated Verification | Physical Verification Required |
|---|---|---|
| Lander Telemetry Ingestion | ✅ JSON parsing, validation, state updates | ⚠️ ESP32 Wi-Fi reception, sensor accuracy |
| Lander TCP Framing | ✅ Socket buffering, partial lines, reconnection | ⚠️ Antenna performance, brownout handling |
| Rover UDP Ingestion | ✅ ASCII parsing, range bounds, staleness | ⚠️ HC-12 RF reception, COM port reading |
| Drone UDP Ingestion | ✅ JSON parsing, RFC 1982 rollover, staleness | ⚠️ Drone Wi-Fi client, flight controller |
| LCD Remote Updates | ✅ `mission_display` generation, rate limiting | ⚠️ I2C backpack address, contrast pot |
| Dashboard Real-Time | ✅ WS broadcast, reconnection, polling fallback | ⚠️ HDMI resolution, TV rendering |
| Storage Retention | ✅ 5-min sliding window, WAL integrity, reset | ⚠️ Disk endurance on Pi |

---

## Project Links 

- **Repository:** `https://github.com/Nerdtrovert/mars-mission-control`
- **Documentation:** `docs/` directory (see navigation in README)
- **Architecture Decision Records:** `docs/DECISIONS.md`
- **Deployment Guide:** `docs/deployment/gateway-deployment.md`
- **Test Results:** `docs/testing/verification-results.md`