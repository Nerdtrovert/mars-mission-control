# Mars Mission Control — Engineering Documentation

Welcome to the Mars Mission Control engineering documentation. This suite provides comprehensive technical documentation for the Mars Mission Control system, including architecture, hardware, protocols, deployment, and testing.

## Project Overview

Mars Mission Control is a distributed telemetry and command system for a Mars exploration demonstration. The system consists of three primary hardware subsystems communicating through a Raspberry Pi gateway to a backend server and web dashboard.

### Subsystems

| Subsystem | Role | Communication |
|-----------|------|---------------|
| **Lander (ESP32)** | Sensor platform with BMP280, DHT11, 20x4 LCD | Wi-Fi TCP → Pi Gateway (port 5006) |
| **Rover** | Distance/orientation measurement with HC-SR04, MPU6050 | HC-12 serial → Windows GUI → UDP 5005 → Pi Gateway |
| **Drone** | Flight telemetry with GPS, orientation, environment | Wi-Fi UDP → Pi Gateway (port 5007) |

### Operating Modes

| Mode | Command | Description |
|------|---------|-------------|
| **Network** | `python run.py network` | All physical hardware connected via Pi Gateway |
| **Simulation** | `python run.py sim` | Pure software simulation on development machine |

---

## Documentation Structure

```
docs/
├── README.md                    # This file
├── architecture/
│   ├── system-architecture.md   # Complete system overview
│   ├── software-architecture.md # Software component relationships
│   ├── network-architecture.md  # Network topology and interfaces
│   └── data-flow.md             # Telemetry data flow diagrams
├── hardware/
│   ├── hardware-overview.md     # All subsystems summary
│   ├── lander.md                # Lander ESP32 hardware details
│   ├── rover.md                 # Rover hardware details
│   └── drone.md                 # Drone hardware details
├── wiring/
│   ├── README.md                # Wiring documentation index
│   ├── lander-wiring.md         # Lander ESP32 wiring diagrams
│   ├── rover-wiring.md          # Rover wiring (where available)
│   └── drone-wiring.md          # Drone wiring (where available)
├── protocols/
│   ├── communication-overview.md # All communication paths summary
│   ├── tcp-protocol.md          # Lander TCP protocol
│   ├── rover-udp.md             # Rover UDP protocol
│   ├── drone-udp.md             # Drone UDP protocol
│   └── telemetry-schemas.md     # JSON schema definitions
├── deployment/
│   ├── raspberry-pi-setup.md    # Pi OS, Wi-Fi AP, dependencies
│   ├── gateway-deployment.md    # Gateway service deployment
│   └── local-development.md     # Local development setup
├── testing/
│   ├── testing-strategy.md      # Test organization and approach
│   └── verification-results.md  # Test results and coverage
└── diagrams/
    ├── system-architecture.mmd   # Complete system Mermaid diagram
    ├── network-topology.mmd      # Network topology Mermaid diagram
    ├── software-architecture.mmd # Software component Mermaid diagram
    ├── rover-data-flow.mmd       # Rover telemetry flow
    ├── drone-data-flow.mmd       # Drone telemetry flow
    ├── lander-data-flow.mmd      # Lander telemetry/command flow
    └── sequence-diagrams.mmd     # Sequence diagrams
```

---

## Quick Start

### Network Mode (Hardware)
```bash
# On Raspberry Pi (gateway)
LANDER_TCP_HOST=0.0.0.0 LANDER_TCP_PORT=5006 \
  uvicorn gateway.main:app --host 0.0.0.0 --port 8001

# On development machine (backend)
python run.py network
```

### Simulation Mode (Development)
```bash
# On development machine (no Pi required)
python run.py sim
```

Access the dashboard at `http://127.0.0.1:8000/dashboard`

---

## Key Interfaces

| Interface | Protocol | Port | Endpoint |
|-----------|----------|------|----------|
| Lander → Pi Gateway | TCP (JSON) | 5006 | — |
| Rover GUI → Pi Gateway | UDP (ASCII) | 5005 | — |
| Drone → Pi Gateway | UDP (JSON) | 5007 | — |
| Pi Gateway HTTP API | HTTP | 8001 | `/api/*` |
| Pi Gateway WebSocket | WebSocket | 8001 | `/ws/telemetry` |
| Backend HTTP API | HTTP | 8000 | `/api/*` |
| Backend WebSocket | WebSocket | 8000 | `/ws/telemetry` |

---

## Related Documents

- [System Architecture](architecture/system-architecture.md)
- [Hardware Overview](hardware/hardware-overview.md)
- [Communication Protocols](protocols/communication-overview.md)
- [Deployment Guide](deployment/raspberry-pi-setup.md)
- [Testing Strategy](testing/testing-strategy.md)

---

## Version Information

- **Lander Firmware**: v1.5.0 (see `lander/lander.ino`)
- **Gateway**: FastAPI on Raspberry Pi
- **Backend**: FastAPI on development machine
- **Dashboard**: Vanilla JavaScript frontend

---

*Documentation generated from source code inspection. Accuracy verified against implementation as of 2026-10-30.*