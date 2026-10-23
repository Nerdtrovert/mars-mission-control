# Mars Mission Control — Engineering Constitution (AGENTS.md)

> **MANDATORY DIRECTIVE FOR ALL CODING AGENTS**  
> This document is the authoritative engineering constitution for the Mars Mission Control repository.  
> Every automated agent, assistant, and engineer MUST read, understand, and strictly follow these rules before inspecting, planning, or modifying any file in this repository.

---

## 1. Project Purpose & Priorities

Mars Mission Control is a **local-first college exhibition project** demonstrating a coordinated planetary landing and monitoring mission.

### System Components
1. **ESP32 Lander Controller**: Embedded microcontroller managing physical gate actuation, limit safety, status indicators, and environmental sensing.
2. **Raspberry Pi 4 Hardware Gateway**: Edge gateway managing the USB serial link to the ESP32 and hosting HTTP and WebSocket APIs for the local network.
3. **MacBook Mission Control**: Central host running the FastAPI backend, mission coordination, SQLite state history, and browser dashboard.
4. **Exhibition Dashboard TV**: Display connected directly to the MacBook over HDMI showing real-time mission telemetry and system status.

### Operational Context
- **Private Local Network**: The system operates entirely over a dedicated local Wi-Fi / wired network. Core device communication, telemetry, command relay, and dashboard display must function without public Wi-Fi or internet access.
- *(Note: External map tiles may optionally use internet access if available, but core mission operations never depend on it).*

### Engineering Priority Hierarchy
When making trade-offs, strictly apply the following priorities in order:
1. **Physical Safety & Device State Integrity** (Prevent mechanical damage, invalid commands, or unverified movements).
2. **Reliability & Recoverability** (Graceful error isolation, safe reconnects, and fault latching).
3. **Correctness & Testability** (Deterministic behavior, hardware-free testing, complete schema validation).
4. **Maintainability** (Clear boundaries, explicit type hints, minimal complexity, preserve working code).
5. **Exhibition Presentation & Convenience** (Visual Polish, dashboard aesthetics, operator convenience).

---

## 2. Non-Negotiable Architecture & Ownership Boundaries

```
 +------------------+   USB Serial   +-----------------------+   Private Local Wi-Fi   +-----------------------+   HDMI   +--------------------+
 |   ESP32 Lander   | <============> | Raspberry Pi 4 Gateway| <=====================> |    MacBook Backend    | <======> |   Exhibition TV    |
 | (Frozen Baseline)|  (115200 8N1)  | (Serial + HTTP/WS)    |     (HTTP / WS JSON)    | & Browser Dashboard   |  Video   |     Dashboard      |
 +------------------+                +-----------------------+                         +-----------------------+          +--------------------+
```

### Component Boundaries
- **ESP32 Lander**:
  - **Owns**: Physical hardware, GPIOs, servo PWM, limit switches, sensor polling, status LEDs, and local safety interlocks.
  - **Serial Protocol**: Communicates with the Raspberry Pi exclusively over USB serial using newline-delimited JSON at 115200 baud (8N1).
  - **Autonomy**: Must function safely regardless of whether the Pi or MacBook backend is connected.
  - **Baseline**: The firmware is **frozen as `v1.3.1-esp32-baseline`**. Do not modify or rewrite firmware casually.
- **Raspberry Pi 4 (Hardware Gateway)**:
  - **Owns**: The single physical USB serial connection to the ESP32.
  - **Responsibilities**: Manages serial reconnection, handles framing, buffers telemetry, validates incoming HTTP commands, and relays messages between the serial bus and the MacBook over HTTP and WebSocket.
  - **Isolation**: Prevents multiple processes or network clients from contending for the raw serial port.
- **MacBook (Mission Control Backend & Dashboard)**:
  - **Owns**: High-level mission state coordination, command tracking and dispatch, SQLite mission logging and telemetry archiving, and dashboard client serving.
  - **Constraint**: **Must NEVER access the ESP32 serial port directly in production.** It communicates exclusively with the Raspberry Pi Gateway over local HTTP/WebSocket.
- **Exhibition TV**:
  - Passive video sink connected via HDMI to the MacBook. Does not participate in device network protocols.

Do not shift responsibilities across these boundaries without explicit explanation, justification, and approval.

---

## 3. Existing Implementation & Preservation Rules

### Current MacBook Backend Baseline
The repository already contains a working FastAPI application structure:
- `backend/app/main.py`: FastAPI application entrypoint.
- `backend/app/api/routes.py`: API endpoints (including `/api/mission/state`).
- `backend/app/mission/state.py`: Thread-safe `MissionStateManager` tracking system mode, gate state, limits, and faults.
- `backend/app/telemetry/processor.py`: JSON line parsing and validation against `TELEMETRY_FIELDS`, `VALID_MODES`, and `VALID_GATE_STATES`.
- `backend/app/telemetry/service.py`: `TelemetryService` linking telemetry ingestion to state updates.
- `backend/tests/`: Pytest suite verifying telemetry parsing and state updates (original baseline: 9 passing tests).

### Rules for Modification
1. **Preserve Functionality**: Do not break, disable, or regress existing passing tests or functional flows.
2. **Inspect First**: Always read the existing implementation, imports, and tests before editing.
3. **Smallest Coherent Change**: Implement focused, minimal edits. Avoid sweeping refactors or reorganizing directories based on personal preference.
4. **Never Overwrite or Duplicate Unnecessarily**: Do not create redundant copies of existing services, routes, or models.
5. **Acknowledge Hardware Reality**: The physical Raspberry Pi gateway may not be connected during backend development. All backend logic must be testable without physical hardware. Do not claim physical hardware has been tested when it has not.

---

## 4. Hardware Pinout & Electrical Safety

The ESP32 pin assignments are established and coordinated across firmware (`lander.ino`) and documentation (`Lander/lander/Mars_Lander_Wiring_Structure.txt`):

| Component / Function | ESP32 GPIO | Electrical / Hardware Notes |
| :--- | :--- | :--- |
| **Servo 1 Signal** | GPIO 18 | PWM signal only; requires external regulated power supply |
| **Servo 2 Signal** | GPIO 19 | PWM signal only; requires external regulated power supply |
| **Physical Gate Button** | GPIO 23 | Active LOW with internal pull-up (`INPUT_PULLUP`), debounced |
| **Open Limit Switch** | GPIO 32 | Digital input, debounced |
| **Closed Limit Switch** | GPIO 33 | Digital input, debounced |
| **Green Status LED** | GPIO 25 | Active HIGH via series current-limiting resistor |
| **Red Status LED** | GPIO 26 | Active HIGH via series current-limiting resistor |
| **WS2812B Data** | GPIO 27 | 3.3V to 5V logic level compatibility must be verified |
| **BMP280 I2C (SDA)** | GPIO 21 | Shared I2C bus (3.3V) |
| **BMP280 I2C (SCL)** | GPIO 22 | Shared I2C bus (3.3V) |
| **20x4 LCD (SDA)** | GPIO 21 | Shared I2C bus (verify backpack address and logic level) |
| **20x4 LCD (SCL)** | GPIO 22 | Shared I2C bus (verify backpack address and logic level) |
| **DHT11 Data** | GPIO 17 | 1-wire digital data pin |
| **Reserved / Unused** | GPIO 16, 13, 14, 4 | Do not connect peripherals |

### Electrical & Board Rules
- **Flash Pins**: GPIO 6–11 are connected to internal SPI flash on classic ESP32 modules. **Never use GPIO 6–11.**
- **Input-Only Pins**: GPIO 34–39 lack internal pull-up/pull-down resistors and cannot be configured as outputs.
- **Voltage Limits**: ESP32 GPIO pins are **3.3V logic and NOT 5V tolerant**. Never connect 5V signals directly to GPIOs.
- **Servo Power Isolation**: Never power MG996R servos from the ESP32 3.3V or 5V regulator rails. Servos must use a dedicated external regulated supply sharing a common ground reference.
- **Hardware Modification Prohibition**: Do not alter this pinout without explicit approval and end-to-end documentation updates.

---

## 5. Safety, State Machine, & Command Handling

### Physical Gate States
The gate state machine recognizes only the following valid states:
`UNKNOWN`, `CLOSED`, `OPEN`, `OPENING`, `CLOSING`, `FAULT`.

### Ground Truth Rules
1. **Physical Hardware is the Sole Truth**: The backend must never assume the physical gate is `CLOSED` or `OPEN` purely because the backend service restarted or initialized.
2. **Initial State is UNKNOWN**: After any backend restart, gateway disconnect, or telemetry timeout, the physical gate state must revert to `UNKNOWN` until verified by fresh telemetry or status query from the device.
3. **No Automatic Movement**:
   - **NEVER** issue movement commands (`OPEN_GATE`, `CLOSE_GATE`) automatically on backend startup.
   - **NEVER** issue movement commands automatically upon gateway or serial reconnection.
4. **No Blind Retries**:
   - Do not retry `OPEN_GATE` or `CLOSE_GATE` automatically after a timeout.
   - Movement command retries are strictly prohibited until end-to-end command IDs, idempotent duplicate suppression, and verification are fully implemented.
5. **Acknowledgement ≠ Completion**:
   - A `command_ack` with `accepted: true` confirms only that the lander validated and accepted the instruction.
   - It **does not mean** the gate has finished moving or reached an endpoint.
   - Completion is confirmed solely when physical limit switches signal `OPEN` or `CLOSED` via `gate_status` or `telemetry`.
6. **No Fabricated Telemetry**:
   - Never invent or fabricate sensor readings, and never substitute `0` or arbitrary values for disconnected sensors.
   - Missing or failing sensor data must be explicitly represented as `null` (`None`) with error states logged.
7. **Fault Latching**:
   - Lander faults are latched in firmware. Software must not attempt to clear or suppress hardware faults without physical verification and proper procedures.
   - Do not invent emergency-stop behaviors not supported by the hardware baseline.
8. **Subsystem Isolation**:
   - A failure or disconnect in one subsystem (e.g., DHT11 sensor failure or gateway disconnect) must never crash unrelated backend services or corrupt unaffected mission state.

---

## 6. Connection & Device Lifecycle Semantics

### Independent Health Tracking
Gateway connectivity and device connectivity are independent:
- Gateway (Raspberry Pi): `ONLINE`, `STALE`, `OFFLINE`, `NOT_CONNECTED`.
- Device (ESP32 Lander): `ONLINE`, `STALE`, `OFFLINE`, `NOT_CONNECTED`.

*A reachable Raspberry Pi does NOT imply a connected or functional ESP32.*

```
                 +-------------------+
                 |   NOT_CONNECTED   |
                 +-------------------+
                           | (initial attempt)
                           v
                     +-----------+
    +--------------> |  ONLINE   | <-------------+
    |                +-----------+               |
    |                      |                     |
    | (telemetry resumes)  | (heartbeat timeout) | (reconnected &
    |                      v                     |  status verified)
    |                +-----------+               |
    +--------------- |   STALE   |               |
                     +-----------+               |
                           |                     |
                           | (extended timeout)  |
                           v                     |
                     +-----------+               |
                     |  OFFLINE  | --------------+
                     +-----------+
```

### Reconnection Protocol
When communication with the gateway or device is restored:
1. Re-establish network/serial session.
2. Request fresh device status (`GET_STATUS`).
3. Validate response schemas and confirm limit switch readings.
4. Synchronize mission state cache with confirmed readings.
5. Resume continuous telemetry streaming.
6. **Never command physical movement during recovery.**
7. Employ bounded exponential backoff to avoid hammering disconnected endpoints.

---

## 7. Coding & Engineering Standards

- **Inspect Before Editing**: Read all related modules, schemas, and tests before writing code.
- **Small, Incremental Changes**: Keep PRs and changesets small, coherent, and reviewable.
- **Explicit Type Hints**: All Python backend code must use explicit type annotations and pass static analysis.
- **Robust Input Validation**: Validate all network and serial payloads against explicit Pydantic or dataclass schemas.
- **Explicit Error Handling**: Catch specific exceptions. Never use bare `except:` or silently swallow errors.
- **Zero Unnecessary Dependencies**: Rely on standard library and existing dependencies (`fastapi`, `uvicorn`, `pyserial`, `pytest`, `websockets`) unless a clear requirement justifies an addition.
- **Hardware-Free Testability**: Provide simulated or mock interfaces for all hardware communications so the entire suite runs in standard CI or local development without physical devices.
- **Deterministic Testing**: Avoid arbitrary `time.sleep()`. Use deterministic clocks, injected timestamps, mock timers, and explicit state triggers.
- **Preserve Documentation & Comments**: Keep existing comments, docstrings, and rationale intact.

---

## 8. Testing Requirements

### Verification Discipline
Every code modification must be verified against the test suite:
1. Run tests for the modified module immediately.
2. Run the complete repository test suite (`PYTHONPATH=backend pytest backend/tests`).
3. Report exact test execution counts and outcomes honestly.
4. Never disable, comment out, or delete a failing test to simulate a green suite.
5. Ensure zero external dependencies for tests: no physical serial port, no Raspberry Pi, no local Wi-Fi, and no public internet.

---

## 9. Dependency & Workspace Hygiene

- **Do Not Commit Artifacts**: Virtual environments (`.venv`), Python byte caches (`__pycache__`), `.pytest_cache`, OS metadata (`.DS_Store`), secrets, and temporary scratch scripts must never be committed to git.
- **Never Overwrite Configuration**: Do not overwrite environment files (`.env`), credentials, or user configuration without explicit instructions.
- **No Destructive Shell Commands**: Do not run recursive deletions or git resets without explicit user confirmation.
- **No Unsolicited Commits**: Do not run `git commit` or `git push` unless specifically requested by the user.

---

## 10. Agent Task Workflow

Every agent must follow this 3-phase workflow for every task:

### Phase 1: Pre-Execution Inspection
1. Read this `AGENTS.md` file.
2. Inspect all relevant directories, source files, and tests.
3. Formulate a minimal, concrete plan.
4. Identify risks, edge cases, and impacted test suites.

### Phase 2: Implementation & Preservation
1. Execute the minimal coherent set of changes.
2. Maintain existing interfaces, schema contracts, and backwards compatibility.
3. Keep code changes clean, documented, and properly typed.
4. Add comprehensive unit and integration tests covering positive, negative, and timeout paths.

### Phase 3: Post-Execution Verification & Reporting
1. Run the full pytest suite and verify 100% pass rate.
2. Inspect the git diff to ensure no accidental file edits or leftover scratch files.
3. Present a concise, honest summary to the user detailing:
   - Files created or modified.
   - Exact test results and counts.
   - Architectural decisions made.
   - Clear identification of what remains simulated vs. what requires physical hardware verification.

---

## 11. Decision Authority & Architectural Changes

The architectural standards defined in this document take precedence over individual agent preferences.

### Requiring Explicit Escalation & Approval:
- Modifying the frozen ESP32 firmware baseline (`v1.3.1-esp32-baseline`).
- Changing hardware pin assignments or electrical wiring assumptions.
- Altering the serial framing protocol or command payload schemas.
- Modifying gateway API contracts or changing ownership boundaries between components.
- Introducing new external services, databases, or heavy framework dependencies.

When an architectural change is approved by the human operator, this `AGENTS.md` and related technical documentation must be updated immediately to maintain consensus across development sessions.
