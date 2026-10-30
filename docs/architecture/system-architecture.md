# System Architecture

## Overview

Mars Mission Control is a distributed telemetry and command system consisting of three independent hardware subsystems that communicate through a central Raspberry Pi gateway to a backend server and web-based dashboard.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MARS MISSION CONTROL SYSTEM                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐      ┌─────────────────┐      ┌──────────────────────┐  │
│  │   LANDER     │      │  RASPBERRY PI   │      │  DEVELOPMENT MACHINE │  │
│  │   (ESP32)    │      │   GATEWAY       │      │     BACKEND          │  │
│  │              │      │                 │      │                      │  │
│  │ • BMP280     │      │ • TCP :5006     │      │ • FastAPI :8000      │  │
│  │ • DHT11      │◄────►│   (Lander)      │◄────►│ • SQLite Storage     │  │
│  │ • 20x4 LCD   │      │ • UDP :5005     │      │ • Telemetry Service  │  │
│  │ • LEDs       │      │   (Rover)       │      │ • Mission State      │  │
│  │ • Wi-Fi STA  │      │ • UDP :5007     │      │ • Command Tracker    │  │
│  │              │      │   (Drone)       │      │ • Simulators         │  │
│  └──────────────┘      │ • HTTP :8001    │      │ • WebSocket          │  │
│         ▲              │ • WS  :8001     │      └──────────┬───────────┘  │
│         │              └────────┬────────┘                 │              │
│         │                       │                          │              │
│         │        ┌──────────────┴──────────────┐          │              │
│         │        │                             │          │              │
│         ▼        ▼                             ▼          ▼              │
│  ┌──────────────┐                    ┌──────────────────┐                │
│  │   ROVER      │                    │     DRONE        │                │
│  │  (Physical)  │                    │   (Physical)     │                │
│  │              │                    │                  │                │
│  │ • HC-SR04    │                    │ • ESP32 + Sensors│                │
│  │ • MPU6050    │                    │ • Wi-Fi UDP      │                │
│  │ • HC-12      │                    │ • GPS, IMU, Env  │                │
│  │              │                    │                  │                │
│  └──────┬───────┘                    └──────────────────┘                │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │  ROVER       │                                                        │
│  │  LAPTOP      │                                                        │
│  │  (Windows    │                                                        │
│  │   Tkinter    │                                                        │
│  │   GUI)       │                                                        │
│  │              │                                                        │
│  │ • COM Port   │                                                        │
│  │ • HC-12      │                                                        │
│  │ • UDP → Pi   │                                                        │
│  └──────────────┘                                                        │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### Lander (ESP32-WROOM-32 / DevKit V1)
- **Sensors**: BMP280 (temperature, pressure), DHT11 (temperature, humidity)
- **Display**: 20x4 I2C character LCD with 5 rotating pages
- **Indicators**: Green LED (mode), Red LED (sensor error blink)
- **Communication**: Wi-Fi Station → TCP to Pi Gateway (port 5006)
- **Protocol**: Newline-delimited JSON telemetry (~1 Hz in ACTIVE mode)
- **Commands**: `GET_STATUS`, `SET_ACTIVE`, `SET_STANDBY`
- **Remote Display**: Receives `mission_display` messages for rover/drone pages on LCD

### Rover Subsystem
- **Physical Sensors**: HC-SR04 (distance), MPU6050 (pitch/roll)
- **Wireless Link**: HC-12 9600 baud serial to Rover Laptop
- **Rover Laptop**: Windows Tkinter GUI reads COM port, parses serial, forwards UDP to Pi (port 5005)
- **Telemetry Format**: `DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M` (ASCII, ~5 Hz)
- **No on-board ESP32** — rover telemetry originates from laptop GUI

### Drone Subsystem
- **Controller**: ESP32-based drone controller
- **Sensors**: GPS (lat/lon/alt), IMU (roll/pitch/yaw), Environment (temp/pressure/humidity), Battery
- **Communication**: Wi-Fi UDP directly to Pi Gateway (port 5007)
- **Telemetry Format**: JSON with sequence numbers, timestamp, flight status, orientation, GPS, battery
- **Sequence Validation**: RFC 1982 rollover handling (16/32-bit)

### Raspberry Pi Gateway
- **Role**: Edge gateway aggregating all three telemetry streams
- **Services**:
  - `LanderTCPTransport`: Accepts ESP32 TCP connections, frames JSON lines
  - `LanderManager`: TCP I/O, command correlation, staleness, display forwarding
  - `RoverUDPReceiver`: Parses ASCII packets, validates, staleness monitoring
  - `DroneUDPReceiver`: Parses JSON, sequence validation, staleness monitoring
  - HTTP API (FastAPI) + WebSocket broadcaster on port 8001
- **Forwarding**: Rover/Drone telemetry → `mission_display` over TCP to Lander LCD

### Development Machine Backend
- **Role**: Mission control server, dashboard host, historical storage
- **Services**:
  - `NetworkGatewayRunner`: Persistent WebSocket to Pi Gateway + health polling
  - `SimulatorRunner`: In-memory lander/rover/drone simulators (sim mode)
  - `RoverRunner` / `DroneRunner`: Poll Pi HTTP or run local simulators
  - SQLite storage (5-minute sliding window retention)
  - WebSocket broadcaster for live dashboard updates
- **Operating Modes**: `network` (all hardware) or `sim` (all simulated)

### Dashboard Frontend
- **Technology**: Vanilla JavaScript (ES6 modules), CSS custom properties
- **Real-time**: WebSocket primary, 2s HTTP polling fallback
- **Components**: Lander status, Rover card, Drone card, Commands table, Events log, Telemetry history
- **Visual Distinction**: Lander (Mars red), Rover (Cyan), Drone (Amber)

---

## Data Flow Summary

### Rover Telemetry Path
```
Rover ESP32 (HC-SR04 + MPU6050)
    │ HC-12 9600 baud serial
    ▼
Rover Laptop Tkinter GUI (parses COM port)
    │ UDP 5005 ASCII: DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
    ▼
Raspberry Pi Gateway (RoverUDPReceiver)
    │ Validates 5 fields, enum checks, range checks
    ▼
Pi HTTP /api/rover/status + WebSocket /ws/telemetry
    │ Backend RoverRunner polls HTTP (0.2s) or WebSocket
    ▼
Development Machine Backend (RoverRunner → TelemetryService → Storage + WebSocket)
    ▼
Dashboard (WebSocket rover_telemetry + polling fallback)
```

### Drone Telemetry Path
```
Drone ESP32 (GPS + IMU + Env + Battery)
    │ Wi-Fi UDP 5007 JSON
    ▼
Raspberry Pi Gateway (DroneUDPReceiver)
    │ JSON schema validation, RFC 1982 sequence rollover
    ▼
Pi HTTP /api/drone/status + WebSocket /ws/telemetry
    │ Backend DroneRunner polls HTTP (0.5s) or WebSocket
    ▼
Development Machine Backend (DroneRunner → TelemetryService → Storage + WebSocket)
    ▼
Dashboard (WebSocket drone_telemetry + polling fallback)
```

### Lander Telemetry & Command Path
```
Lander ESP32 (BMP280 + DHT11)
    │ Wi-Fi TCP 5006 JSON (newline-delimited)
    ▼
Raspberry Pi Gateway (LanderTCPTransport → LanderManager)
    │ Validation, staleness (STALE 3s, OFFLINE 10s), command correlation
    ▼
Pi HTTP /api/lander/status + WebSocket /ws/telemetry
    │ Backend NetworkGatewayRunner WebSocket + health polling
    ▼
Development Machine Backend (TelemetryService → MissionStateManager → Storage + WebSocket)
    ▼
Dashboard (WebSocket telemetry + state_snapshot + polling fallback)
    
Commands (Dashboard → Backend → Pi Gateway → Lander TCP):
  GET_STATUS, SET_ACTIVE, SET_STANDBY
```

### Remote Display Forwarding (Pi Gateway → Lander LCD)
```
Pi Gateway receives Rover/Drone telemetry (UDP)
    │ LanderManager formats mission_display
    ▼
TCP 5006 to Lander ESP32
    │ {type:"mission_display", device:"rover|drone", connected:bool, data:{...}}
    ▼
Lander ESP32 renders on LCD Page 3 (Rover) / Page 4 (Drone)
    │ Rate-limited: Rover 4 Hz + 2.5s heartbeat, Drone 2 Hz + 2.5s heartbeat
    ▼
LCD shows live rover distance/pitch/roll/cmd/mode and drone flight_status/lat/lon
```

---

## Operating Modes

### Network Mode (`python run.py network`)
All physical hardware connected:
- `GATEWAY_MODE=network` → Backend connects to Pi Gateway via WebSocket/HTTP
- `ROVER_MODE=network` → Backend polls Pi `/api/rover/status`
- `DRONE_MODE=network` → Backend polls Pi `/api/drone/status`
- Pi Gateway must be running and accessible at configured IP

### Simulation Mode (`python run.py sim`)
Zero hardware required:
- `GATEWAY_MODE=simulator` → Backend uses in-memory `GatewaySimulator`
- `ROVER_MODE=simulator` → Backend uses in-memory `RoverSimulator`
- `DRONE_MODE=simulator` → Backend uses in-memory `DroneRunner` simulator
- All telemetry generated deterministically in backend process
- No Pi Gateway, no ESP32, no physical sensors needed

---

## Configuration Independence

Each subsystem mode is independently configurable via environment variables:

| Variable | Default | Values | Scope |
|----------|---------|--------|-------|
| `GATEWAY_MODE` | simulator | simulator, network | Lander |
| `ROVER_MODE` | simulator | simulator, network | Rover |
| `DRONE_MODE` | simulator | simulator, network | Drone |
| `GATEWAY_HTTP_URL` | http://127.0.0.1:8001 | URL | Backend→Pi |
| `GATEWAY_WS_URL` | ws://127.0.0.1:8001/ws/telemetry | URL | Backend→Pi |

This allows mixed configurations (e.g., real lander + simulated rover + simulated drone).

---

## Failure Handling & Staleness

| Layer | Rover | Drone | Lander |
|-------|-------|-------|--------|
| **Physical Link** | HC-12 serial | ESP32 Wi-Fi | ESP32 Wi-Fi |
| **Gateway Ingress** | UDP 5005 ASCII | UDP 5007 JSON | TCP 5006 JSON |
| **Validation** | 5-field parse, enums | Full JSON schema, ranges | JSON schema, sensor health |
| **Sequence** | N/A (ASCII) | RFC 1982 32-bit rollover | N/A (timestamp) |
| **Gateway Staleness** | 2s OFFLINE | 10s OFFLINE | 3s STALE, 10s OFFLINE |
| **Backend Polling** | 0.2s interval | 0.5s interval | WebSocket + 1s health |
| **LCD Forward** | 4 Hz + 2.5s HB | 2 Hz + 2.5s HB | N/A |

---

## Related Documents

- [Network Architecture](network-architecture.md) — Network topology and port assignments
- [Software Architecture](software-architecture.md) — Code organization and component relationships
- [Data Flow](data-flow.md) — Detailed telemetry flow diagrams
- [Lander Hardware](hardware/lander.md) — ESP32 pinout, sensors, wiring
- [Rover Hardware](hardware/rover.md) — Sensors and communication
- [Drone Hardware](hardware/drone.md) — Drone controller and sensors
- [TCP Protocol](protocols/tcp-protocol.md) — Lander JSON message formats
- [Rover UDP](protocols/rover-udp.md) — ASCII packet format and validation
- [Drone UDP](protocols/drone-udp.md) — JSON schema and sequence handling