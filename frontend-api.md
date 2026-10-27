# Mars Mission Control — Frontend Integration Contract (`frontend-api.md`)

> **Authoritative API & Integration Contract for Dashboard UI Development**  
> Target Audience: College Frontend Development Team building or replacing the Mission Control dashboard.  
> Status: Implemented & Verified against Backend Baseline v1.0.0.

> [!WARNING]
> **STRICT ARCHITECTURAL BOUNDARY: DO NOT MODIFY THE EXISTING FRONTEND BASELINE**  
> The existing frontend files (`frontend/index.html`, `frontend/css/dashboard.css`, and `frontend/js/dashboard.js`) constitute the **protected working reference implementation** and verified integration baseline.  
> The college frontend team **MUST NOT** edit, overwrite, delete, rename, move, append code to, or replace these three files.  
> The new frontend is an **independent deliverable** developed in a separate directory (e.g., React/Vite running on `http://localhost:5173`).  
> All integration occurs **exclusively through the documented backend REST and WebSocket contracts**.

> [!IMPORTANT]
> **MANDATORY DIRECTIVE: SIMULATOR-FIRST FRONTEND DEVELOPMENT**  
> All frontend development, visual styling, component replacement, and user-flow testing **must be executed against the backend simulator mode (`GATEWAY_MODE=simulator`)**.  
> The physical Raspberry Pi 4 edge gateway and ESP32 lander hardware must **not** be used for initial frontend development or routine debugging.  
> Demonstration of complete, error-free operation in simulator mode is a mandatory milestone required before any frontend code is connected to physical exhibition hardware.

---

## Table of Contents
1. [Purpose & System Architecture](#1-purpose--system-architecture)
2. [Strict Frontend Boundary & College Workspace Rules](#2-strict-frontend-boundary--college-workspace-rules)
3. [Mandatory: Simulator-First Frontend Development](#3-mandatory-simulator-first-frontend-development)
4. [Connection & Initialization](#4-connection--initialization)
5. [REST API Reference](#5-rest-api-reference)
6. [WebSocket Contract](#6-websocket-contract)
7. [Telemetry Contract & Data Dictionary](#7-telemetry-contract--data-dictionary)
8. [Command Submission & Lifecycle](#8-command-submission--lifecycle)
9. [Data Freshness, Health & Connection Semantics](#9-data-freshness-health--connection-semantics)
10. [Recommended Frontend Integration Pattern (Vanilla JS / React / Vite)](#10-recommended-frontend-integration-pattern-vanilla-js--react--vite)
11. [Frontend Implementation & Safety Rules](#11-frontend-implementation--safety-rules)
12. [Simulator Acceptance & Hardware Promotion Checklist](#12-simulator-acceptance--hardware-promotion-checklist)

---

## 1. Purpose & System Architecture

Mars Mission Control demonstrates a coordinated planetary landing and monitoring mission for a college exhibition. The frontend dashboard presents real-time telemetry from the lander (DHT11 temperature/humidity, BMP280 temperature/pressure, LCD status, status LEDs) and rover (HC-SR04 distance, MPU6050 pitch/roll, mode/command), tracks mission command states (`GET_STATUS`, `SET_ACTIVE`, `SET_STANDBY`), and renders independent gateway, lander, and rover health states.

### Communication Topology
```
 +------------------------+   WebSocket & HTTP JSON   +------------------------------------+
 |   Frontend Dashboard   | <=======================> |       MacBook Mission Backend      |
 |  (Browser / React /    |       (Port 8000)         |  - FastAPI State Coordinator       |
 |   Vanilla JS Client)   |                           |  - SQLite Persistent Storage       |
 +------------------------+                           |  - Dashboard Broadcaster           |
                                                      +------------------------------------+
                                                                        ||
                                                                        || Private Local Wi-Fi
                                                                        || HTTP / WebSocket (Port 8001)
                                                                        \/
                                                      +------------------------------------+
                                                      |    Raspberry Pi 4 Edge Gateway     |
                                                      |  - Lander Wi-Fi TCP (Port 5006)    |
                                                      |  - Rover UDP Receiver (Port 5005)  |
                                                      +------------------------------------+
                                                         //                            \\
                            Private Local Wi-Fi (TCP 5006)                              UDP 5005
                                                       //                                \\
                                     +--------------------+                     +--------------------+
                                     |    ESP32 Lander    |                     | Windows Rover GUI  |
                                     | - DHT11, BMP280    |                     | (HC-12 9600 Serial)|
                                     | - 20x4 LCD, LEDs   |                     +--------------------+
                                     +--------------------+
```

### Critical Architecture Boundaries
- **Backend Host**: The frontend communicates **exclusively** with the MacBook Mission Control backend.
- **Gateway Isolation**: The frontend **must never** attempt to contact the Raspberry Pi Edge Gateway (port 8001), lander TCP port (5006), or rover UDP port (5005) directly.
- **Zero Internet Requirement**: Core mission telemetry, command relay, state synchronization, and dashboard rendering operate completely offline over a private local network.
- **Execution Modes (`simulation_mode`)**:
  - `GATEWAY_MODE=simulator`: The backend generates synthetic lander telemetry with an internal virtual lander.
  - `GATEWAY_MODE=network`: The backend relays real lander telemetry from the Raspberry Pi hardware gateway.
  - `ROVER_MODE=simulator`: The backend generates deterministic rover telemetry.
  - `ROVER_MODE=network`: The backend reads rover status from the Raspberry Pi hardware gateway.
  - The backend attaches `"simulation_mode": true/false` to every state snapshot. The UI **must visibly distinguish** simulator data from physical hardware measurements.

### Base URLs & Ports
| Environment | Protocol | Host / Port | Notes |
| :--- | :--- | :--- | :--- |
| **MacBook Mission Backend (REST)** | HTTP | `http://localhost:8000` | Served by MacBook FastAPI application |
| **MacBook Mission Backend (WebSocket)** | WebSocket | `ws://localhost:8000/ws/telemetry` | Live telemetry & state streaming |
| **College Team React / Vite Dev Server** | HTTP | `http://localhost:5173` | Typical React/Vite development server (port 5173) |
| **Raspberry Pi Gateway (HTTP/WS)** | HTTP / WS | `http://<pi-ip>:8001` | Gateway API (Mac-to-Pi internal; not for frontend) |
| **Raspberry Pi Lander TCP Receiver** | TCP | `<pi-ip>:5006` | Ingests ESP32 lander telemetry over Wi-Fi |
| **Raspberry Pi Rover UDP Receiver** | UDP | `<pi-ip>:5005` | Ingests rover datagrams from Windows GUI |
| **Exhibition Local Wi-Fi (Backend)** | HTTP | `http://<macbook-ip>:8000` | Dynamic IP assigned on local router |
| **Exhibition Local Wi-Fi (WebSocket)** | WebSocket | `ws://<macbook-ip>:8000/ws/telemetry` | Same host as HTTP, protocol switch |

---

## 2. Strict Frontend Boundary & College Workspace Rules

### 2.1 The Protected Reference Baseline
The existing frontend consists of exactly three files:
- `frontend/index.html`
- `frontend/css/dashboard.css`
- `frontend/js/dashboard.js`

These three files constitute the **existing reference dashboard and integration baseline**. They represent verified, tested behavior that guarantees exhibition readiness, HDMI display compatibility, and hardware safety interlocks.

> [!CAUTION]
> **CRITICAL MANDATE: THE EXISTING FRONTEND IS NOT A TEMPLATE TO EDIT**  
> The existing frontend is a **working reference implementation**, **NOT a starter template** that the college team is expected or allowed to edit.  
> The new frontend is a **separate deliverable**. Integration must happen through the existing backend contract, not by merging code into the three protected files.

The college frontend team **must not** edit, overwrite, delete, rename, move, or replace these files. Specifically, you **must not**:
1. Add new UI components, markup, or templates to `frontend/index.html`.
2. Modify or append custom CSS rules to `frontend/css/dashboard.css`.
3. Modify, refactor, reorganize, or replace `frontend/js/dashboard.js`.
4. Alter existing dashboard element IDs, CSS classes, DOM structures, event handlers, or frontend logic.
5. Request or implement backend API or WebSocket contract changes to accommodate custom UI styling or state shortcuts.
6. Use the existing `frontend/` directory as your development workspace or scratch pad.

---

### 2.2 How the College Frontend Team Must Work

All new frontend development must follow these operational rules:

1. **Independent Directory & Workspace**:
   Develop the new frontend in a completely separate, dedicated directory (for example, `frontend-college/`, `ui/`, `dashboard-v2/`, or a standalone React/Vite workspace).
2. **Independent Dependencies & Assets**:
   Maintain your own `package.json`, build configuration, HTML entrypoint, stylesheets, components, and frontend-specific assets completely separate from the baseline `frontend/` folder.
3. **Modern Frameworks & Dev Server Port (e.g. React + Vite on Port 5173)**:
   - When using modern frontend stacks (React, Vite, Vue, Svelte, Next.js), your development server typically runs on **Port 5173** (e.g., `http://localhost:5173` or `http://127.0.0.1:5173`).
   - The development architecture consists of two independent processes:
     - **Frontend Application Dev Server**: `http://localhost:5173` (serves and hot-reloads your React components).
     - **Mission Control Backend**: `http://127.0.0.1:8000` (FastAPI REST endpoints) and `ws://127.0.0.1:8000/ws/telemetry` (live telemetry WebSocket).
   - Configure your frontend client to connect to port 8000:
     - **Direct Environment Configuration**:
       Set environment variables such as `VITE_API_BASE_URL=http://127.0.0.1:8000` and `VITE_WS_URL=ws://127.0.0.1:8000/ws/telemetry`.
     - **Vite Development Proxy (`vite.config.js`)**:
       Alternatively, configure Vite's development proxy so requests to `/api`, `/health`, and `/ws` are forwarded to the Mission Control backend:
       ```javascript
       // vite.config.js (in your separate frontend directory)
       import { defineConfig } from 'vite';
       import react from '@vitejs/plugin-react';

       export default defineConfig({
         plugins: [react()],
         server: {
           port: 5173,
           proxy: {
             '/api': 'http://127.0.0.1:8000',
             '/health': 'http://127.0.0.1:8000',
             '/ws': {
               target: 'ws://127.0.0.1:8000',
               ws: true,
             },
           },
         },
       });
       ```
4. **Contract-Driven Integration**:
   Treat this document (`frontend-api.md`) as your authoritative contract. If a data field, command payload, or status code is documented here, use it as specified.
5. **Simulator-Mode Testing**:
   Start the Mission Control backend in simulator mode (`GATEWAY_MODE=simulator`). Develop and test all UI flows against the simulator without requiring physical hardware.
6. **Exclusive Backend Communication**:
   Communicate exclusively with the MacBook Mission Control backend on port 8000. Never attempt to contact the Raspberry Pi edge gateway (port 8001) or connect to raw serial ports directly.
7. **Zero Backend/Firmware Alterations**:
   Do not modify backend routes, database schemas, gateway code, or ESP32 firmware without explicit authorization from the project owner.
8. **Hardware-Free Reproducibility**:
   Ensure your frontend build and test suites run completely offline and hardware-free in standard local development.

---

### 2.3 Integration & Simulator Acceptance Criteria

The new frontend is a **separate deliverable**. Integration is achieved exclusively through the documented backend contract, not by merging your code into the three protected baseline files.

Before any demonstration to stakeholders or request for physical hardware integration, the new frontend must demonstrate in simulator mode that it can:

1. **Initial State Ingestion**:
   Load initial state cleanly on startup via `GET /api/mission/state` or the initial WebSocket `state_snapshot`.
2. **Live WebSocket Telemetry**:
   Receive and process live 1 Hz `telemetry` frames, updating indicators without memory leaks or stutter.
3. **Accurate Telemetry & Indicator Rendering**:
   Accurately render telemetry fields, duration-formatted uptime (`HH:MM:SS`), independent Gateway and Lander status badges, sensor failure indicators (`--` for missing sensors), and latched hardware faults.
4. **Command Submission & Lifecycle Tracking**:
   Submit supported commands (`POST /api/mission/commands`) and accurately track their progression through `CREATED` → `SENT` → `ACKNOWLEDGED` → `COMPLETED`.
5. **Disconnection & Reconnection Handling**:
   Gracefully detect WebSocket or backend disconnections, display a prominent disruption warning, and automatically recover upon backend restart without getting permanently stuck.
6. **Isolated Operation**:
   Operate 100% cleanly against the simulator without modifying any part of the existing baseline dashboard (`frontend/index.html`, `frontend/css/dashboard.css`, `frontend/js/dashboard.js`).

> [!NOTE]
> Physical hardware integration (connecting to the physical Raspberry Pi 4 gateway and ESP32 lander platform) is a separate, formal stage scheduled only after full simulator acceptance is demonstrated and approved.

---

## 3. Mandatory: Simulator-First Frontend Development

### 3.1 The Simulator-First Mandate
The college frontend development team must develop, style, and verify all dashboard components primarily using Mission Control's built-in **Simulator Mode**. 

Physical hardware (the Raspberry Pi 4 edge gateway, ESP32 lander controller, and rover radio transceiver) is scarce and sensitive to setup variations. Directing untested frontend code against physical hardware introduces unnecessary delays and misleading debugging sessions caused by network or hardware setup issues rather than UI bugs.

The Mission Control backend features a high-fidelity, deterministic in-memory simulator (`GatewaySimulator`, `SimulatorRunner`, and `RoverSimulator`) that faithfully implements the REST contracts, WebSocket telemetry stream, device status reporting, and rover dynamics. Developing against this simulator guarantees rapid, hardware-free iteration and clean architecture boundaries.

---

### 3.2 Development Environment & Startup Commands

#### Starting the Backend in Simulator Mode
Frontend developers must start the backend in simulator mode using the following verified command executed from the repository root:

```bash
# Terminal (MacBook / Linux from repository root):
GATEWAY_MODE=simulator ROVER_MODE=simulator PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

*Note: If activating the Python virtual environment in your shell first:*
```bash
source backend/.venv/bin/activate
GATEWAY_MODE=simulator ROVER_MODE=simulator PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

#### Verified URLs & Verification Points
| Resource | URL | Verification Expectation |
| :--- | :--- | :--- |
| **Dashboard Asset Host** | `http://127.0.0.1:8000/dashboard` | Serves dashboard HTML/CSS/JS |
| **Backend Health Check** | `http://127.0.0.1:8000/health` | Returns JSON with `"simulation_mode": true`, `"status": "healthy"` |
| **Rover Status Endpoint** | `http://127.0.0.1:8000/api/rover/status` | Returns JSON with rover telemetry and `"source": "simulator"` |
| **Root Endpoint** | `http://127.0.0.1:8000/` | Returns JSON with `"simulation_mode": true` |
| **Telemetry WebSocket** | `ws://127.0.0.1:8000/ws/telemetry` | Emits `state_snapshot` followed by 1 Hz `telemetry` |

#### How to Verify Simulator Mode is Active
1. **HTTP Verification**:
   Query `http://127.0.0.1:8000/health`. The backend response confirms `"simulation_mode": true`:
   ```json
   {
     "status": "healthy",
     "simulation_mode": true
   }
   ```
   Querying `http://127.0.0.1:8000/api/mission/state` confirms subsystem states under simulator mode:
   ```json
   {
     "mode": "ACTIVE",
     "gateway_state": "ONLINE",
     "device_state": "ONLINE",
     "bmp280_ok": true,
     "dht11_ok": true,
     "simulation_mode": true
   }
   ```
2. **Dashboard UI Verification**:
   On the dashboard page (`http://127.0.0.1:8000/dashboard`), observe the mode badge in the header. When running in simulator mode, it must explicitly display:
   ```
   [SIMULATION]  or  [SIMULATOR DATA — NOT HARDWARE]
   ```
3. **Architecture Reminder**:
   The frontend communicates **solely** with the FastAPI backend on port 8000. The frontend never communicates directly with the simulator internals, Python classes, or Raspberry Pi gateway port 8001.

---

### 3.3 What Frontend Developers Must Test in Simulator Mode

The frontend team must systematically verify the following 9 capabilities against the simulator before requesting hardware access:

| # | Test Capability | Expected Simulator Behavior & UI Requirement |
| :- | :--- | :--- |
| **1** | **Initial State & Cold Loading** | On initial load or after session reset, `mode` is initialized and WebSocket immediately delivers a `state_snapshot` message with current connection and mission state. |
| **2** | **Live Telemetry Streaming** | Receives ~1 Hz telemetry messages over WebSocket (`ws://127.0.0.1:8000/ws/telemetry`). The `timestamp_ms` increases by 1000 ms each tick. The UI must format `timestamp_ms` as `HH:MM:SS` (duration), **never** as raw milliseconds. |
| **3** | **Sensor Readings & Failures** | Simulator emits synthetic nominal sensor values (`bmp_temperature_c: 24.2`, `pressure_hpa: 1013.5`, `dht_temperature_c: 24.0`, `humidity_pct: 58.0`). If a sensor reports failure (`bmp280_ok: false`), the UI must display `--` and a `FAILED` badge; it must **never** display `0` or keep frozen previous numbers. |
| **4** | **Subsystem Status Badges** | Gateway, Lander, and Rover report status independently. Badges must be rendered independently (Gateway Badge, Lander Badge, and Rover Badge). |
| **5** | **Operating Mode Commands** | Submit mode commands (`SET_ACTIVE`, `SET_STANDBY`, `GET_STATUS`) via `POST /api/mission/commands`. Verify state transitions between `ACTIVE` (sensors polling) and `STANDBY` (sensors paused, readings `null`). |
| **6** | **Rover Telemetry Streaming** | Ingest live `rover_telemetry` messages over WebSocket and poll `GET /api/rover/status`. Accurately render `distance_cm`, `pitch_deg`, `roll_deg`, `command`, `mode`, and obstacle alerts. |
| **7** | **WebSocket Disruption Recovery** | Stop the backend server (`Ctrl+C`). Within seconds, the UI must display the red `CONNECTION DISRUPTED: RECONNECTING TO MISSION BACKEND...` banner. Restart the backend: the client must automatically reconnect, receive a fresh `state_snapshot`, and automatically hide the banner. |
| **8** | **Command Submission Lifecycle** | Post commands to `POST /api/mission/commands`. The UI must track the lifecycle states: `CREATED` → `SENT` → `ACKNOWLEDGED` → `COMPLETED`. |
| **9** | **Mission History & IST Timezones** | Polling `/api/mission/commands`, `/api/mission/events`, and `/api/mission/telemetry/history` must display human-readable timestamps in Indian Standard Time (IST, UTC+05:30) with 24-hour `hourCycle: 'h23'` format (`HH:mm:ss`). History polling must never overwrite newer live telemetry. |

---

### 3.4 Simulator Capabilities vs. Realities & Limitations

To prevent false assumptions during frontend development, understand what the simulator implements versus physical realities:

#### What the Simulator Implements:
- **Deterministic Environmental Telemetry**: Emits nominal temperature, pressure, and humidity sensor readings.
- **Operating Mode Transitions**: Transitions cleanly between `ACTIVE` and `STANDBY`.
- **Rover Telemetry Simulation**: Emits simulated rover attitude (pitch/roll), distance, motion commands, and obstacle warnings.
- **Standard Protocol Compliance**: Emits identical JSON telemetry fields (`TELEMETRY_FIELDS`), WebSocket envelopes, and HTTP response structures as the physical Pi gateway and ESP32.
- **Request ID Tracking**: Full UUID tracking and acknowledgement mapping between frontend requests and virtual lander responses.
- **Staleness Tracking**: Evaluates gateway, lander, and rover staleness if telemetry ticks cease.

#### What the Simulator Does NOT Implement (Physical Realities):
- **No Physical Sensor Noise or Bus Dropouts**: In hardware, the BMP280 can fail to respond over I2C (address 0x76/0x77), and DHT11 digital one-wire reads can encounter checksum timeouts.
- **No Wi-Fi Packet Jitter or Disconnects**: In hardware, the lander ESP32 communicates over Wi-Fi TCP, subject to RF interference or router reconnects.
- **No Rover Radio Link Fluctuations**: In hardware, the rover sends HC-12 9600-baud packets to a Windows PC, which forwards datagrams over UDP port 5005. Packets may drop when out of range.

---

### 3.5 Simulator vs. Physical Hardware: Operating Principles

1. **Default & Mandatory Iteration Target**:  
   Simulator mode is the **default, expected environment** for all UI development, styling adjustments, refactoring, and automated testing.
2. **Synthetic Data Disclaimer**:  
   Telemetry values observed in simulator mode are completely **synthetic**. They must **never** be cited or recorded as proof of lander sensor calibration, mechanical transit timing, or exhibition flight readiness.
3. **Prerequisite, Not Proof**:  
   Flawless execution in simulator mode is a **mandatory prerequisite** before physical hardware access, but it does **not prove physical hardware readiness**. Physical verification is a separate, deliberate stage.

---

### 3.6 Acceptance Criteria Before Physical Hardware Integration

Before the frontend team is granted integration access to the physical Raspberry Pi 4 edge gateway and ESP32 lander hardware, the frontend implementation must pass the following milestone verification in simulator mode:

- [ ] **Clean Zero-Error Console**: Zero unhandled JavaScript exceptions, WebSocket connection loop crashes, or React/DOM rendering errors during 10 minutes of continuous simulator operation.
- [ ] **100% Simulator Test Coverage**: All 9 capabilities in Section 3.3 demonstrated and verified.
- [ ] **Visual Simulation Indicator**: UI clearly displays `SIMULATION` / `SIMULATOR DATA` when `simulation_mode === true`.
- [ ] **Safety Interlocks Enforced**: UI refuses to emit `OPEN_GATE` or `CLOSE_GATE` unless prerequisite states (`CLOSED` or `OPEN`) are verified by authoritative limit telemetry.
- [ ] **Reconnection Stability**: UI demonstrates disconnect and recovery without getting stuck in a permanent reconnect banner or frozen state.
- [ ] **Timestamp Integrity**: All displayed clocks and event logs render in IST (`Asia/Kolkata`, 24h `HH:mm:ss`) without UTC offset drift.

---

## 4. Connection & Initialization

### Lifecycle Overview
```
           +-----------------------------+
           | 1. Page Load & Assets       |
           |    GET /dashboard           |
           +-----------------------------+
                          |
                          v
           +-----------------------------+
           | 2. Open WebSocket           |
           |    ws://<host>:8000/ws/telem|
           +-----------------------------+
                          |
            (Immediate server snapshot)
                          v
           +-----------------------------+
           | 3. Handle 'state_snapshot'  |
           |    Seed badges, gate, modes |
           +-----------------------------+
                          |
             (Concurrent HTTP fallback)
                          v
           +-----------------------------+
           | 4. Fetch History via REST   |
           |    /api/mission/commands    |
           |    /api/mission/events      |
           |    /api/mission/telemetry/hist
           +-----------------------------+
                          |
                          v
           +-----------------------------+
           | 5. Stream Live 'telemetry'  |
           |    Updates HUD at ~1 Hz     |
           +-----------------------------+
```

### Guaranteed Initial State Snapshot
Upon opening the WebSocket connection to `/ws/telemetry`, the backend **guarantees** an immediate `state_snapshot` message before any periodic telemetry frames:
```json
{
  "type": "state_snapshot",
  "data": {
    "mode": "ACTIVE",
    "last_telemetry_at": "2026-10-23T10:00:00.000000+00:00",
    "updated_at": "2026-10-23T10:00:00.000000+00:00",
    "gateway_state": "ONLINE",
    "device_state": "ONLINE",
    "last_gateway_heartbeat_at": "2026-10-23T10:00:00.000000+00:00",
    "last_device_telemetry_at": "2026-10-23T10:00:00.000000+00:00",
    "last_telemetry_timestamp_ms": 124500,
    "last_device_status_timestamp_ms": 124500,
    "bmp280_ok": true,
    "dht11_ok": true,
    "simulation_mode": false
  }
}
```

### Initial State & Disconnected Representation
When starting up or after a communication failure:
- **`mode`** defaults to `"UNKNOWN"`. The UI displays `UNKNOWN` until fresh telemetry or status query confirms device mode (`ACTIVE` or `STANDBY`).
- **`gateway_state`** and **`device_state`** default to `"NOT_CONNECTED"`.
- If the gateway or device is `OFFLINE` or `NOT_CONNECTED`, the UI must show amber/red status pills and mark telemetry as stale.

---

## 5. REST API Reference

All REST endpoints return JSON with standard HTTP status codes.

### 5.1 Backend Status (`GET /`)
- **Method**: `GET`
- **Path**: `/`
- **Purpose**: Root service discovery and backend status.
- **Request Body / Parameters**: None.
- **Response (`200 OK`)**:
  ```json
  {
    "application": "Mars Mission Control",
    "status": "online",
    "version": "1.0.0",
    "simulation_mode": false
  }
  ```

### 5.2 Backend Health Check (`GET /health`)
- **Method**: `GET`
- **Path**: `/health`
- **Purpose**: Liveness probe for the MacBook backend service.
- **Request Body / Parameters**: None.
- **Response (`200 OK`)**:
  ```json
  {
    "status": "healthy",
    "simulation_mode": false
  }
  ```

### 5.3 Dashboard Asset Host (`GET /dashboard`)
- **Method**: `GET`
- **Path**: `/dashboard`
- **Purpose**: Returns the single-page HTML client (`frontend/index.html`). Includes `no-cache` headers.

### 5.4 Consolidated Mission State (`GET /api/mission/state`)
- **Method**: `GET`
- **Path**: `/api/mission/state`
- **Purpose**: Fetches the authoritative in-memory mission state snapshot. Used for initial UI seeding or polling fallback.
- **Request Body / Parameters**: None.
- **Response (`200 OK`)**:
  ```json
  {
    "mode": "ACTIVE",
    "last_telemetry_at": "2026-10-23T10:14:02.124581+00:00",
    "updated_at": "2026-10-23T10:14:02.124581+00:00",
    "gateway_state": "ONLINE",
    "device_state": "ONLINE",
    "last_gateway_heartbeat_at": "2026-10-23T10:14:01.000000+00:00",
    "last_device_telemetry_at": "2026-10-23T10:14:02.124581+00:00",
    "last_telemetry_timestamp_ms": 8452000,
    "last_device_status_timestamp_ms": 8400000,
    "bmp280_ok": false,
    "dht11_ok": true,
    "simulation_mode": false
  }
  ```

### 5.5 Independent Rover Status (`GET /api/rover/status`)
- **Method**: `GET`
- **Path**: `/api/rover/status`
- **Purpose**: Fetches the latest validated rover telemetry snapshot. Independent from lander telemetry.
- **Request Body / Parameters**: None.
- **Response (`200 OK`)**:
  ```json
  {
    "rover_id": "mars-rover-01",
    "distance_cm": 145.0,
    "pitch_deg": 12.4,
    "roll_deg": -3.2,
    "command": "F",
    "mode": "M",
    "connection_state": "ONLINE",
    "last_seen": "2026-10-23T10:14:02.100000+00:00",
    "source": "simulator",
    "obstacle_detected": false,
    "event": null
  }
  ```

### 5.6 List Tracked Commands (`GET /api/mission/commands`)
- **Method**: `GET`
- **Path**: `/api/mission/commands`
- **Purpose**: Returns the list of all recorded commands in chronological order.
- **Request Body / Parameters**: None.
- **Response (`200 OK`)**:
  ```json
  [
    {
      "command_id": "7b09bf93-6b3a-4efb-8611-37d45a995c64",
      "name": "SET_ACTIVE",
      "status": "COMPLETED",
      "created_at": "2026-10-23T10:12:00.100000+00:00",
      "acknowledged_at": "2026-10-23T10:12:00.220000+00:00",
      "completed_at": "2026-10-23T10:12:00.350000+00:00",
      "error_reason": null,
      "params": null,
      "missing_ack": false,
      "reconciliation_note": null,
      "dispatched_at_ms": 8432000,
      "outcome_resolved": true
    }
  ]
  ```

### 5.7 Submit Command (`POST /api/mission/commands`)
- **Method**: `POST`
- **Path**: `/api/mission/commands`
- **Purpose**: Submits an operator command (`GET_STATUS`, `SET_ACTIVE`, `SET_STANDBY`) for edge dispatch and lifecycle tracking.
- **Headers**: `Content-Type: application/json`
- **Request Body Schema**:
  | Field | Type | Required | Description |
  | :--- | :--- | :--- | :--- |
  | `command` | `string` | Optional* | Supported command name (`"GET_STATUS"`, `"SET_ACTIVE"`, `"SET_STANDBY"`). |
  | `command_type` | `string` | Optional* | Alternative field name for backwards compatibility. *One of `command` or `command_type` is required.* |
  | `command_id` | `string` | Optional | Client-generated UUID. If omitted, backend generates one. |
  | `params` | `object` | Optional | Optional key-value parameters dictionary. |

  *Example Request Body:*
  ```json
  {
    "command": "SET_ACTIVE",
    "command_id": "9d4f0d38-6f68-466d-8687-8849b2533ca9"
  }
  ```

- **Response (`200 OK` — Command Accepted for Execution)**:
  ```json
  {
    "command": {
      "command_id": "9d4f0d38-6f68-466d-8687-8849b2533ca9",
      "name": "SET_ACTIVE",
      "status": "ACKNOWLEDGED",
      "created_at": "2026-10-23T10:15:30.100000+00:00",
      "acknowledged_at": "2026-10-23T10:15:30.250000+00:00",
      "completed_at": null,
      "error_reason": null,
      "params": null,
      "missing_ack": false,
      "reconciliation_note": null,
      "dispatched_at_ms": 8452000,
      "outcome_resolved": false
    },
    "gateway_response": {
      "command_id": "9d4f0d38-6f68-466d-8687-8849b2533ca9",
      "accepted": true,
      "reason": null,
      "fault": null,
      "timestamp": "2026-10-23T10:15:30.250000+00:00"
    }
  }
  ```

- **Error Responses (`400 Bad Request`)**:
  Returned when an invalid command name or duplicate active command ID is submitted.
  ```json
  {
    "detail": "Invalid command name: UNKNOWN_CMD"
  }
  ```

### 5.8 Query Mission Events (`GET /api/mission/events`)
- **Method**: `GET`
- **Path**: `/api/mission/events`
- **Purpose**: Fetches system transitions, connection changes, and status events from persistent SQLite storage.
- **Query Parameters**:
  | Parameter | Type | Default | Description |
  | :--- | :--- | :--- | :--- |
  | `limit` | `integer` | `100` | Maximum number of events to return (ordered newest first). |
  | `event_type` | `string` | `null` | Optional filter (e.g. `"STATE_TRANSITION"`, `"FAULT"`, `"COMMAND"`). |

- **Response (`200 OK`)**:
  ```json
  [
    {
      "id": 142,
      "timestamp": "2026-10-23T10:12:03.450000+00:00",
      "timestamp_epoch": 1792750323.45,
      "event_type": "STATE_TRANSITION",
      "severity": "INFO",
      "subsystem": "LANDER",
      "description": "Operating mode changed from STANDBY to ACTIVE",
      "details": {
        "prev_mode": "STANDBY",
        "new_mode": "ACTIVE"
      }
    }
  ]
  ```

### 5.9 Query Telemetry History (`GET /api/mission/telemetry/history`)
- **Method**: `GET`
- **Path**: `/api/mission/telemetry/history`
- **Purpose**: Retrieves historical telemetry samples within the backend's sliding 5-minute window for table display or charts.
- **Query Parameters**:
  | Parameter | Type | Default | Description |
  | :--- | :--- | :--- | :--- |
  | `limit` | `integer` | `300` | Maximum number of records (ordered chronologically ascending). |
  | `since_epoch` | `float` | `null` | Filter records with `received_at_epoch >= since_epoch`. |

- **Response (`200 OK`)**:
  ```json
  [
    {
      "id": 9801,
      "received_at": "2026-10-23T10:14:01.120000+00:00",
      "received_at_epoch": 1792750441.12,
      "timestamp_ms": 8451000,
      "mode": "ACTIVE",
      "bmp_temperature_c": null,
      "pressure_hpa": null,
      "dht_temperature_c": 24.5,
      "humidity_pct": 45.0,
      "bmp280_ok": 0,
      "dht11_ok": 1
    }
  ]
  ```
  *(Note: In the SQLite response, boolean flags like `bmp280_ok` and `dht11_ok` are integers `1` / `0` / `null`).*

### 5.10 Reset Mission Demo Session (`POST /api/mission/session/reset`)
- **Method**: `POST`
- **Path**: `/api/mission/session/reset`
- **Purpose**: Exhibition reset button. Clears commands, events, and telemetry from SQLite; resets mission mode and sensor health in memory. **Preserves active connection states (`gateway_state`, `device_state`)** so live hardware is not falsely marked offline.
- **Request Body**: None.
- **Response (`200 OK`)**:
  ```json
  {
    "status": "session_reset",
    "message": "Demo session data cleared. Device and sensor state are awaiting fresh telemetry.",
    "mission_state": {
      "mode": "UNKNOWN",
      "last_telemetry_at": null,
      "updated_at": "2026-10-23T10:16:00.000000+00:00",
      "gateway_state": "ONLINE",
      "device_state": "ONLINE",
      "last_gateway_heartbeat_at": "2026-10-23T10:15:59.000000+00:00",
      "last_device_telemetry_at": "2026-10-23T10:15:59.000000+00:00",
      "last_telemetry_timestamp_ms": null,
      "last_device_status_timestamp_ms": null,
      "bmp280_ok": null,
      "dht11_ok": null,
      "simulation_mode": false
    }
  }
  ```
  ```

---

## 6. WebSocket Contract

### Endpoint URL
- Local: `ws://localhost:8000/ws/telemetry`
- Network: `ws://<backend-ip>:8000/ws/telemetry`
- Over TLS: `wss://<backend-domain>:8000/ws/telemetry`

### Protocol Messages (Server → Client)
All messages are JSON objects containing a `"type"` discriminator field.

#### Message Type 1: `state_snapshot`
Sent immediately on connection, after state transitions, or after session reset.
```json
{
  "type": "state_snapshot",
  "data": {
    "mode": "ACTIVE",
    "last_telemetry_at": "2026-10-23T10:14:02.124581+00:00",
    "updated_at": "2026-10-23T10:14:02.124581+00:00",
    "gateway_state": "ONLINE",
    "device_state": "ONLINE",
    "last_gateway_heartbeat_at": "2026-10-23T10:14:01.000000+00:00",
    "last_device_telemetry_at": "2026-10-23T10:14:02.124581+00:00",
    "last_telemetry_timestamp_ms": 8452000,
    "last_device_status_timestamp_ms": 8400000,
    "bmp280_ok": false,
    "dht11_ok": true,
    "simulation_mode": false
  }
}
```

#### Message Type 2: `telemetry`
Broadcast on every received live telemetry tick (approx. 1 Hz when lander is `ONLINE`).
```json
{
  "type": "telemetry",
  "telemetry": {
    "type": "telemetry",
    "timestamp_ms": 8453000,
    "mode": "ACTIVE",
    "bmp_temperature_c": null,
    "pressure_hpa": null,
    "dht_temperature_c": 24.5,
    "humidity_pct": 45.0,
    "bmp280_ok": false,
    "dht11_ok": true,
    "received_at": "2026-10-23T10:14:03.120000+00:00"
  },
  "state": {
    "mode": "ACTIVE",
    "last_telemetry_at": "2026-10-23T10:14:03.120000+00:00",
    "updated_at": "2026-10-23T10:14:03.120000+00:00",
    "gateway_state": "ONLINE",
    "device_state": "ONLINE",
    "last_gateway_heartbeat_at": "2026-10-23T10:14:01.000000+00:00",
    "last_device_telemetry_at": "2026-10-23T10:14:03.120000+00:00",
    "last_telemetry_timestamp_ms": 8453000,
    "last_device_status_timestamp_ms": 8400000,
    "bmp280_ok": false,
    "dht11_ok": true,
    "simulation_mode": false
  }
}
```

#### Message Type 3: `rover_telemetry`
Broadcast on rover telemetry updates received from the UDP stream or simulator.
```json
{
  "type": "rover_telemetry",
  "rover": {
    "rover_id": "mars-rover-01",
    "distance_cm": 145.0,
    "pitch_deg": 12.4,
    "roll_deg": -3.2,
    "command": "F",
    "mode": "M",
    "connection_state": "ONLINE",
    "last_seen": "2026-10-23T10:14:03.120000+00:00",
    "source": "simulator",
    "obstacle_detected": false,
    "event": null
  }
}
```

#### Message Type 4: `command_update`
Broadcast when a command is accepted and submitted.
```json
{
  "type": "command_update",
  "command": {
    "command_id": "9d4f0d38-6f68-466d-8687-8849b2533ca9",
    "name": "SET_ACTIVE",
    "status": "ACKNOWLEDGED",
    "created_at": "2026-10-23T10:15:30.100000+00:00",
    "acknowledged_at": "2026-10-23T10:15:30.250000+00:00",
    "completed_at": null,
    "error_reason": null,
    "params": null,
    "missing_ack": false,
    "reconciliation_note": null,
    "dispatched_at_ms": 8452000,
    "outcome_resolved": false
  }
}
```

### Protocol Messages (Client → Server Heartbeat)
To maintain the WebSocket connection through reverse proxies or browser idle timeouts:
- Client sends string: `"ping"`
- Server replies with string: `"pong"`

---

## 7. Telemetry Contract & Data Dictionary

### Lander Telemetry Field Specification (`msg.telemetry`)
| Field Name | Type | Nullable | Units / Allowed Values | Description |
| :--- | :--- | :--- | :--- | :--- |
| `timestamp_ms` | `integer` | No | Milliseconds (ms) | **ESP32 microcontroller `millis()` uptime**. Wraps at ~49.7 days; resets to 0 on reboot. |
| `received_at` | `string` | No | ISO 8601 (UTC) | **Host-side receipt timestamp**. Used for display and time-ordering. |
| `mode` | `string` | No | `"ACTIVE"`, `"STANDBY"` | Current ESP32 operating mode. |
| `bmp_temperature_c`| `number` | **Yes** | Degrees Celsius (°C) | Barometric sensor temperature. `null` if sensor disconnected or failed. |
| `pressure_hpa` | `number` | **Yes** | Hectopascals (hPa) | Barometric pressure. `null` if sensor disconnected or failed. |
| `dht_temperature_c`| `number` | **Yes** | Degrees Celsius (°C) | 1-wire digital sensor temperature. `null` if sensor disconnected or failed. |
| `humidity_pct` | `number` | **Yes** | Percent (%) | Relative humidity. `null` if sensor disconnected or failed. |
| `bmp280_ok` | `boolean` | No | `true` / `false` | BMP280 hardware health status. |
| `dht11_ok` | `boolean` | No | `true` / `false` | DHT11 hardware health status. |

### Rover Telemetry Field Specification (`msg.rover`)
| Field Name | Type | Nullable | Units / Allowed Values | Description |
| :--- | :--- | :--- | :--- | :--- |
| `rover_id` | `string` | No | string (`"mars-rover-01"`) | Identifier for the rover unit. |
| `distance_cm` | `number` | **Yes** | 0 to 400 cm | HC-SR04 ultrasonic rangefinder obstacle distance. |
| `pitch_deg` | `number` | **Yes** | -90.0 to 90.0 degrees | MPU6050 attitude pitch angle. |
| `roll_deg` | `number` | **Yes** | -90.0 to 90.0 degrees | MPU6050 attitude roll angle. |
| `command` | `string` | **Yes** | `"F"`, `"B"`, `"L"`, `"R"`, `"S"` | Current motion command (Forward, Back, Left, Right, Stop). |
| `mode` | `string` | **Yes** | `"M"`, `"A"` | Rover control mode (Manual or Autonomous). |
| `connection_state` | `string` | No | `"ONLINE"`, `"OFFLINE"` | Independent rover link health based on UDP packet arrival. |
| `obstacle_detected` | `boolean`| **Yes** | `true` / `false` | Indicates whether distance is below obstacle safety threshold (< 30 cm). |

### The Critical Timestamp Distinction
> [!IMPORTANT]
> **`timestamp_ms` vs `received_at`:**
> 1. **`timestamp_ms` is NOT wall-clock time.** It is raw microcontroller milliseconds since boot. It must only be formatted as a duration (e.g. `HH:MM:SS` or `Xd HH:MM:SS`).
> 2. **`received_at` IS wall-clock time.** It is generated in UTC by the MacBook host upon receiving the serial/network frame.
> 3. **Timezone Display**: Convert `received_at` to **Indian Standard Time (IST, UTC+05:30)** using timezone-aware formatters (`Asia/Kolkata` with 24-hour `hourCycle: 'h23'`). Never add static hour/millisecond arithmetic manually.

### Sensor Nullability & Health Contract
- When `bmp280_ok` is `false`: `bmp_temperature_c` and `pressure_hpa` are strictly `null`.
- When `dht11_ok` is `false`: `dht_temperature_c` and `humidity_pct` are strictly `null`.
- **Never fabricate or substitute `0` or `0.0` for missing sensors.** Display `--` with a `FAILED` health badge.

---

## 8. Command Submission & Lifecycle

### Supported Commands
| Command Name | Description | Preconditions | Effect |
| :--- | :--- | :--- | :--- |
| `GET_STATUS` | Non-intrusive status query | Gateway must be `ONLINE` | Requests fresh status and mode from lander |
| `SET_ACTIVE` | Transitions lander to ACTIVE mode | Gateway must be `ONLINE` | Starts sensor polling (2s) and telemetry streaming (1 Hz) |
| `SET_STANDBY` | Transitions lander to STANDBY mode | Gateway must be `ONLINE` | Pauses sensor polling; holds link available |

### Command State Machine
```
   [Operator Click]
          |
          v
     +---------+
     | CREATED |
     +---------+
          | (validated by MacBook safety rules)
          v
     +---------+
     |  SENT   | --------(Device rejects or Safety violation)--------> [ REJECTED ]
     +---------+
          |
          | (ESP32 acknowledges request over Wi-Fi TCP)
          v
   +--------------+
   | ACKNOWLEDGED | --------(Timeout / Movement fails)-----------------> [ TIMED_OUT / FAILED ]
   +--------------+
          |
          | (Mode change or status response confirmed)
          v
    +-----------+
    | COMPLETED |
    +-----------+
```

### Acknowledgement & Verification
- An HTTP response of `accepted: true` confirms that the gateway received and dispatched the command.
- Status transitions to `ACKNOWLEDGED` when the ESP32 lander acknowledges the command over the Wi-Fi TCP stream.
- Transition to `COMPLETED` occurs when the confirmed mode status (`mode_status` or `status`) is reported by the device.

---

## 9. Data Freshness, Health & Connection Semantics

### Independent Health Hierarchy
```
                        +--------------------------+
                        |  Backend (MacBook Host)  |
                        |      (HTTP / WS API)     |
                        +--------------------------+
                                     |
                +--------------------+--------------------+
                |                                         |
                v                                         v
   +-------------------------+               +-------------------------+
   |  Raspberry Pi Gateway   |               |      ESP32 Lander       |
   |     gateway_state       |               |      device_state       |
   | (ONLINE / STALE /       |               | (ONLINE / STALE /       |
   |  OFFLINE / NOT_CONN)    |               |  OFFLINE / NOT_CONN)    |
   +-------------------------+               +-------------------------+
                |
                v (UDP 5005)
   +-------------------------+
   |       Mars Rover        |
   |    connection_state     |
   |   (ONLINE / OFFLINE)    |
   +-------------------------+
```
A reachable Raspberry Pi does **NOT** imply a connected or functional ESP32 lander or rover. The UI must render separate, independent status badges for Gateway, Lander, and Rover.

### Staleness & Freshness Thresholds
- **Lander Telemetry Freshness (UI Live Indicator)**:
  `age = Date.now() - new Date(received_at).getTime()`
  - **Live**: `age < 5.0 seconds` AND `device_state === 'ONLINE'`.
  - **Historical / Stale**: `age >= 5.0 seconds` OR `device_state !== 'ONLINE'`.
- **Backend Connection Staleness Evaluator**:
  - `stale_threshold_s` = `3.0s`: Evaluated against elapsed time since `last_device_telemetry_at` (for `device_state`) and `last_gateway_heartbeat_at` (for `gateway_state`). Transitions an `ONLINE` state to `STALE`.
  - `offline_threshold_s` = `10.0s`: Evaluated against elapsed time since `last_device_telemetry_at` and `last_gateway_heartbeat_at`. Transitions the subsystem to `OFFLINE`.
  - When `gateway_state` becomes `OFFLINE`, `device_state` also cascades to `OFFLINE`.
- **Rover Staleness**:
  - Rover UDP packets are sent at ~5 Hz. If no valid packet arrives within `2.0 seconds` (`ROVER_OFFLINE_TIMEOUT_S`), the rover `connection_state` transitions to `OFFLINE`. Stored readings are preserved with explicit offline indicators.

---

## 10. Recommended Frontend Integration Pattern (Vanilla JS / React / Vite)

This pattern uses clean, framework-agnostic JavaScript suitable for vanilla JS or modern frameworks like React and Vite.

```javascript
// --- Mission Control Client Architecture ---

const CONFIG = {
  // When running on React / Vite development server (port 5173), point to backend port 8000:
  httpBase: window.location.port === '5173' ? 'http://localhost:8000' : window.location.origin,
  wsUrl: window.location.port === '5173'
    ? 'ws://localhost:8000/ws/telemetry'
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/telemetry`,
  pollIntervalMs: 2000,
};

let currentState = {
  simulation_mode: false,
  gateway_state: 'NOT_CONNECTED',
  device_state: 'NOT_CONNECTED',
  mode: 'UNKNOWN',
  updated_at: null,
};

let latestDisplayedReceivedAtMs = null;
let ws = null;

// 1. Timezone Formatter (IST 24-hour format)
const istTimeFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

function formatTimeIST(isoString) {
  if (!isoString) return '--';
  const d = new Date(isoString);
  return isNaN(d.getTime()) ? '--' : istTimeFormatter.format(d);
}

// 2. Duration Formatter for ESP32 Uptime
function formatUptime(uptimeMs) {
  if (!Number.isFinite(uptimeMs) || uptimeMs < 0) return '--';
  const totalSec = Math.floor(uptimeMs / 1000);
  const totalHours = Math.floor(totalSec / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  const mmss = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  if (totalHours >= 24) {
    const days = Math.floor(totalHours / 24);
    return `${days}d ${String(totalHours % 24).padStart(2, '0')}:${mmss}`;
  }
  return `${String(totalHours).padStart(2, '0')}:${mmss}`;
}

// 3. Telemetry Ingestion Guard
function shouldRenderTelemetry(receivedAtMs) {
  if (Number.isFinite(receivedAtMs) && Number.isFinite(latestDisplayedReceivedAtMs)) {
    if (receivedAtMs < latestDisplayedReceivedAtMs) return false; // Prevent out-of-order regression
  }
  return true;
}

// 4. State Merging
function applyMissionState(stateData) {
  if (!stateData) return;
  const incomingTime = stateData.updated_at ? new Date(stateData.updated_at).getTime() : NaN;
  const currentTime = currentState.updated_at ? new Date(currentState.updated_at).getTime() : NaN;

  if (Number.isFinite(incomingTime) && Number.isFinite(currentTime) && incomingTime < currentTime) {
    return; // Reject stale state snapshots
  }

  currentState = { ...currentState, ...stateData };
  renderHeaderBadges(currentState);
  renderModeControls(currentState);
}

// 5. Telemetry Rendering
function renderTelemetry(telem) {
  if (!telem) return;
  const recvAtMs = telem.received_at ? new Date(telem.received_at).getTime() : NaN;
  if (!shouldRenderTelemetry(recvAtMs)) return;
  if (Number.isFinite(recvAtMs)) latestDisplayedReceivedAtMs = recvAtMs;

  // Render Uptime (Duration) & Ingestion Clock (IST)
  document.getElementById('val-esp32-uptime').textContent = formatUptime(telem.timestamp_ms);
  document.getElementById('val-last-received').textContent = formatTimeIST(telem.received_at);

  // Render Sensor Metrics (Safe Null Handling)
  renderSensorMetric('bmp-temp', telem.bmp_temperature_c, telem.bmp280_ok, '°C');
  renderSensorMetric('bmp-press', telem.pressure_hpa, telem.bmp280_ok, 'hPa');
  renderSensorMetric('dht-temp', telem.dht_temperature_c, telem.dht11_ok, '°C');
  renderSensorMetric('dht-hum', telem.humidity_pct, telem.dht11_ok, '%');
}

function renderSensorMetric(elementPrefix, value, isOk, unit) {
  const valEl = document.getElementById(`val-${elementPrefix}`);
  const healthEl = document.getElementById(`health-${elementPrefix}`);
  if (isOk && value !== null && value !== undefined) {
    valEl.textContent = `${Number(value).toFixed(1)} ${unit}`;
    healthEl.textContent = 'OK';
    healthEl.className = 'metric-health ok';
  } else {
    valEl.textContent = '--';
    healthEl.textContent = 'FAILED';
    healthEl.className = 'metric-health failed';
  }
}

// 6. Command Dispatch
async function submitCommand(commandName) {
  try {
    const res = await fetch(`${CONFIG.httpBase}/api/mission/commands`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: commandName }),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(`Command Rejected: ${data.detail || res.statusText}`);
    } else {
      console.log('Command Dispatched:', data.command);
    }
  } catch (err) {
    alert(`Network Error: ${err.message}`);
  }
}

// 7. WebSocket Stream Management with Reconnect
function initWebSocket() {
  ws = new WebSocket(CONFIG.wsUrl);

  ws.onopen = () => {
    document.getElementById('offline-banner').classList.add('hidden');
    pollMissionData(); // Synchronize initial state
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'state_snapshot') {
        applyMissionState(msg.data);
      } else if (msg.type === 'telemetry') {
        if (msg.state) applyMissionState(msg.state);
        if (msg.telemetry) renderTelemetry(msg.telemetry);
      } else if (msg.type === 'rover_telemetry') {
        if (msg.rover) renderRoverTelemetry(msg.rover);
      }
    } catch (e) {
      console.error('Failed to parse WS payload:', e);
    }
  };

  ws.onclose = () => {
    document.getElementById('offline-banner').classList.remove('hidden');
    setTimeout(initWebSocket, 3000); // Bounded retry
  };
}

// 8. REST Polling Fallback
async function pollMissionData() {
  try {
    const [resState, resRover, resCmds, resEvents, resTelem] = await Promise.all([
      fetch(`${CONFIG.httpBase}/api/mission/state`),
      fetch(`${CONFIG.httpBase}/api/rover/status`),
      fetch(`${CONFIG.httpBase}/api/mission/commands`),
      fetch(`${CONFIG.httpBase}/api/mission/events`),
      fetch(`${CONFIG.httpBase}/api/mission/telemetry/history`),
    ]);
    if (resState.ok) applyMissionState(await resState.json());
    if (resRover.ok) renderRoverTelemetry(await resRover.json());
    // Render commands, events, and telemetry tables from responses...
  } catch (err) {
    console.warn('Poll failed:', err);
  }
}

// Startup
initWebSocket();
setInterval(pollMissionData, CONFIG.pollIntervalMs);
```

---

## 11. Frontend Implementation & Safety Rules

Every frontend implementation or replacement must strictly abide by these rules:

1. **Protected Reference Baseline Preservation**:
   The three existing reference files (`frontend/index.html`, `frontend/css/dashboard.css`, `frontend/js/dashboard.js`) are the protected integration baseline. Frontend developers **must not** edit, overwrite, delete, rename, or append code to these files. All new code belongs in a separate workspace directory.
2. **Strict Interface Boundary**:
   The documented FastAPI backend is the sole interface boundary. Frontend engineers **must not** modify backend routes, change serial framing, alter firmware, or connect directly to the Raspberry Pi gateway.
3. **Physical Hardware is the Sole Truth**:
   - Initial lander mode is `UNKNOWN` until confirmed by fresh telemetry or status query.
   - Command acknowledgement confirms request reception; device-reported mode confirms state.
4. **Command Gating**:
   - Disable command submission buttons if the Raspberry Pi gateway is not `ONLINE`.
   - Disable submission while a previous command is in-flight.
5. **Never Fabricate Sensor Readings**:
   - When sensors fail, display `--`. Do not substitute `0` or keep frozen previous numbers.
6. **No Automatic Commands**:
   - Never issue hardware commands automatically on page load, WebSocket connect, or reconnect.
7. **Subsystem Isolation**:
   - A failure in one subsystem (e.g. BMP280 failure or rover disconnect) must never crash the UI or disrupt the other telemetry feeds.
8. **Explicit Simulation Warning**:
   - When `simulation_mode === true`, the dashboard must display a prominent amber banner: `⚠ SIMULATOR DATA — NOT HARDWARE`.

---

## 12. Simulator Acceptance & Hardware Promotion Checklist

Before any frontend implementation is granted approval for connection to physical exhibition hardware (Raspberry Pi 4 gateway & ESP32 lander), the frontend team must systematically demonstrate that the UI works cleanly against the backend simulator mode (`GATEWAY_MODE=simulator`).

Use this mandatory acceptance checklist:

### Stage 1: Simulator Mode Verification (Required Prerequisite)
- [ ] **Startup Verification**: Backend starts in simulator mode (`GATEWAY_MODE=simulator`) and UI correctly accesses `http://127.0.0.1:8000/dashboard`.
- [ ] **Simulation Warning Banner**: UI displays a clear, prominent amber badge indicating `SIMULATION` / `SIMULATOR DATA — NOT HARDWARE` whenever `simulation_mode === true`.
- [ ] **Console Hygiene**: 10 minutes of active UI testing produces zero uncaught exceptions, zero console errors, and zero memory leak warnings.
- [ ] **Immediate State Seeding**: On initial WebSocket connect or page refresh, UI ingests `state_snapshot` and seeds all badges before any telemetry arrives.
- [ ] **Clock & Uptime Formatting**:
  - `timestamp_ms` displays as formatted elapsed duration (`HH:MM:SS` or `Xd HH:MM:SS`), **never** raw milliseconds.
  - Clocks and event timestamps display in **Indian Standard Time (IST, UTC+05:30)** using 24-hour `hourCycle: 'h23'` format (`HH:mm:ss`).
- [ ] **Live Telemetry Stream**: Telemetry ticks increment smoothly at 1 Hz without UI stutter, flashing DOM rebuilds, or dropped frames.
- [ ] **Sensor Failure Presentation**: When synthetic sensors are null or report failure (`bmp280_ok: false`), values render as `--` and health badges show `FAILED`.
- [ ] **Operating Mode Transitions**:
  - Initial mode defaults to `UNKNOWN`; transitions cleanly to `ACTIVE` or `STANDBY` on command dispatch.
  - In `STANDBY`, sensor polling is paused and telemetry renders `--` with appropriate status badges.
- [ ] **Rover Telemetry Streaming**:
  - Live `rover_telemetry` messages render distance, pitch, roll, command, mode, and obstacle detection accurately.
  - Disconnecting rover stream marks rover `OFFLINE` without breaking lander telemetry.
- [ ] **Command Lifecycle & Error Handling**:
  - Valid commands transition cleanly through `CREATED` → `SENT` → `ACKNOWLEDGED` → `COMPLETED`.
  - Invalid commands return HTTP 400 Bad Request; UI displays an informative alert and remains operational.
- [ ] **Network Disconnect & Reconnect**:
  - Stopping the backend server reveals the red `CONNECTION DISRUPTED: RECONNECTING TO MISSION BACKEND...` banner.
  - Restoring the backend automatically clears the warning banner and reconciles current mission state.
- [ ] **Session Reset**:
  - Clicking `RESET SESSION` triggers `POST /api/mission/session/reset`, clears history logs, resets mission mode and sensor state to awaiting fresh telemetry, and maintains active connection status without false disconnect alerts.
- [ ] **Zero Unsolicited Commands**: Page refreshes, reconnects, and poll cycles never issue unauthorized hardware commands.

### Stage 2: Hardware Promotion Sign-Off
- [ ] **Simulator Milestone Completed**: All Stage 1 items verified and signed off by frontend lead.
- [ ] **Hardware Team Escalation**: Formal request submitted to mission engineering team to schedule integration testing on physical hardware.
- [ ] **Physical Hardware Verification**: Verified on physical hardware (Raspberry Pi 4 + ESP32 lander) under direct supervision of the hardware lead.
