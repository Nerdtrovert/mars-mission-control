# Local Development & Mode Guide

This guide covers setting up the Mission Control development environment on a workstation (macOS / Linux / Windows) and running the application in its two official operating modes.

---

## 1. Prerequisites

- **Python**: 3.10, 3.11, 3.12, 3.13, or 3.14
- **Git**: For version control
- **Web Browser**: Chrome, Edge, Safari, or Firefox (modern evergreen browser)

---

## 2. Workstation Setup

Clone the repository and set up the Python virtual environment:

```bash
# 1. Clone repository
git clone https://github.com/Nerdtrovert/mars-mission-control.git
cd mars-mission-control

# 2. Create virtual environment inside backend/
python3 -m venv backend/.venv

# 3. Activate virtual environment
# On macOS / Linux:
source backend/.venv/bin/activate
# On Windows (PowerShell):
# .\backend\.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

---

## 3. The Two Operating Modes

Mars Mission Control provides two distinct, mutually exclusive runtime modes managed via `run.py`:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      MISSION CONTROL OPERATING MODES                   │
├────────────────────────────────┬───────────────────────────────────────┤
│    1. SIMULATION MODE (sim)    │       2. NETWORK MODE (network)       │
├────────────────────────────────┼───────────────────────────────────────┤
│ • Zero physical hardware needed│ • Real physical hardware connected    │
│ • Deterministic math models    │ • Raspberry Pi 4 Gateway (192.168.50.1)│
│ • In-memory simulated sensors  │ • ESP32 Lander over Wi-Fi TCP :5006   │
│ • Synthetic rover terrain path │ • Rover Tkinter GUI over UDP :5005    │
│ • Synthetic drone flight loop  │ • Drone ESP32 client over UDP :5007   │
│ • Default mode for development │ • Production exhibition operation     │
└────────────────────────────────┴───────────────────────────────────────┘
```

---

## 4. Launching the Backend

The unified launcher `run.py` (and convenience wrapper `run_backend.sh`) automatically detects your active virtual environment and configures all required environment variables:

### A. Standalone Simulation Mode (`sim` — Default)
Use this mode when working offline without physical hardware or the Raspberry Pi:

```bash
# Using Python directly:
python run.py sim

# Or using the bash wrapper:
./run_backend.sh sim

# Or simply (defaults to sim):
python run.py
```

**What happens behind the scenes:**
- `GATEWAY_MODE=simulator`: Runs in-process `GatewaySimulator` generating synthetic BMP280/DHT11 readings.
- `ROVER_MODE=simulator`: Generates deterministic rover distance, pitch, and roll variations.
- `DRONE_MODE=simulator`: Runs autonomous aerial drone flight trajectory with GPS, IMU, and altitude.
- `GATEWAY_HTTP_URL=http://127.0.0.1:8001` (mocked in-memory).

### B. Full Hardware Network Mode (`network`)
Use this mode during actual exhibition with physical devices powered on and connected to the `Mission-Control` network:

```bash
# Connect development machine Wi-Fi to "Mission-Control" first!
python run.py network

# Or:
./run_backend.sh network
```

**What happens behind the scenes:**
- `GATEWAY_MODE=network`: Backend connects to Raspberry Pi gateway at `192.168.50.1:8001` over HTTP and WebSocket.
- `ROVER_MODE=network`: Ingests real physical telemetry from the Windows Tkinter GUI forwarded to Pi UDP port 5005.
- `DRONE_MODE=network`: Ingests real physical telemetry from the Drone ESP32 client forwarded to Pi UDP port 5007.

**Environment Overrides:**
If your Raspberry Pi is assigned a different IP address, you can override it without editing source files:
```bash
GATEWAY_HOST=192.168.1.150 python run.py network
```

---

## 5. Accessing the User Interfaces

Once the backend is running (`Uvicorn running on http://0.0.0.0:8000`), open your browser:

| Interface | URL | Description |
|---|---|---|
| **Mission Control Dashboard** | `http://localhost:8000/dashboard` | Fullscreen aerospace HUD designed for exhibition presentation |
| **REST API Documentation** | `http://localhost:8000/docs` | Interactive FastAPI Swagger UI |

---

## 6. Running the Test Suite

Always execute the test suite to verify changes before committing:

```bash
PYTHONPATH=.:backend:gateway backend/.venv/bin/pytest
```

The test suite runs 100% offline with zero physical hardware dependencies.
