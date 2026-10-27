# Mars Mission Control — Architectural Decision Records (docs/DECISIONS.md)

> This document tracks key architectural, system design, and hardware-interface decisions for Mars Mission Control.
> All decisions record a formal status: **`accepted`**, **`proposed`**, **`superseded`**, or **`rejected`**.
> Coding agents and engineers must consult this record to prevent mistaking ongoing discussions or proposals for approved designs.

---

## Decision Index

| ID | Title / Scope | Accepted Choice / Direction | Status | Rationale / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **ADR-001** | Mission Backend Host | MacBook (macOS) | `accepted` | Centralizes mission coordination, SQLite telemetry logging, dashboard hosting, and TV HDMI output. |
| **ADR-002** | Hardware Edge Gateway | Raspberry Pi 4 | `accepted` | Edge gateway directly connected to ESP32 via USB serial; exposes HTTP and WebSocket APIs. |
| **ADR-003** | Physical Control & Safety | ESP32 Microcontroller | `superseded` | Its ramp actuator scope is retired by ADR-023; sensor and status ownership remains. |
| **ADR-004** | MacBook ↔ Pi Communication | HTTP + WebSocket (JSON) | `accepted` | HTTP for command dispatch and request-response; WebSocket for live telemetry streaming. |
| **ADR-005** | Pi ↔ ESP32 Communication | USB Serial (115200 8N1), newline-delimited JSON | `accepted` | Robust, framed serial protocol. Single-process ownership prevents port contention. |
| **ADR-006** | Historical Telemetry & State Storage | SQLite on MacBook | `accepted` | Embedded, zero-configuration local relational database suitable for exhibition workloads without external services. |
| **ADR-007** | In-Memory Telemetry Retention | 5-minute sliding window | `accepted` | Memory-bounded live telemetry cache for immediate UI charting, backed by persistent SQLite storage. |
| **ADR-008** | Initial & Restart Gate State | Reverts to `UNKNOWN` | `superseded` | Historical actuator state; ADR-023 removes gate state and preserves unknown device/sensor state on loss. |
| **ADR-009** | Reconnection Recovery Behavior | Refresh status via `GET_STATUS`; zero automatic movement | `accepted` | Re-establishes link and queries fresh switch readings. Never commands physical motion on reconnect. |
| **ADR-010** | Movement Command Retries | Strictly disabled | `superseded` | Actuator movement commands were retired by ADR-023; generic no-blind-retry rule remains in AGENTS.md. |
| **ADR-011** | ESP32 Firmware Baseline | `v1.3.1-esp32-baseline` reference | `superseded` | User-authorized ADR-023 updates current firmware while retaining this historical baseline reference. |
| **ADR-012** | Exhibition Display Output | TV via direct HDMI from MacBook | `accepted` | Passive display sink connected via HDMI; not a participant in local network communication. |
| **ADR-013** | Network Environment | Private Local Wi-Fi / Ethernet | `accepted` | Core telemetry, command relay, and mission state must operate completely offline without public internet. |
| **ADR-014** | Gateway API Contract Spec | Gateway HTTP and WebSocket endpoints | `superseded` | Updated lander and rover contracts are documented in `docs/api-contract.md` under ADR-023. |
| **ADR-015** | Command Lifecycle States | `CREATED` → `SENT` → `ACKNOWLEDGED` → terminal state | `superseded` | Actuator completion reconciliation is retired; current status/mode command lifecycle is documented by ADR-023. |
| **ADR-016** | Hardware-Free Simulator Separation | In-memory `GatewaySimulator` with deterministic step clock | `accepted` | Isolated development simulator in `app/communication/gateway_simulator.py`. Never masquerades as real hardware in production. |
| **ADR-017** | Lifespan Background Simulator & Staleness Loop | `SimulatorRunner` managed via FastAPI `lifespan` | `accepted` | Starts and stops continuous background telemetry streaming and staleness checks cleanly without leaking tasks or mutating read-only snapshots. |
| **ADR-018** | Gateway-Boundary Request ID Mapping & Reconciliation | Request ID mapping at serial boundary | `superseded` | Mapping remains; movement reconciliation was removed with the actuator commands by ADR-023. |
| **ADR-019** | Raspberry Pi Hardware Gateway Daemon | Standalone FastAPI service in `gateway/` | `accepted` | Also runs independent rover UDP ingestion on port 5005 as specified by ADR-023. |
| **ADR-020** | SQLite Persistence, 5-Minute Retention, and Session Reset | `SQLiteStorage` in `app/storage/` with `telemetry`, `mission_events`, and `commands` tables | `accepted` | Thread-safe persistence with WAL mode, deterministic 5-minute sliding retention, event transition deduplication, safe restart without auto-movement, and clean session reset. |
| **ADR-021** | Exhibition Dashboard UI & Live WebSocket Broadcast | Vanilla HTML5/CSS3/ES6 in `frontend/` + `WS /ws/telemetry` | `superseded` | Actuator controls and gate presentation retired. Sensor, rover, reconnect, and polling behavior remain in current dashboard. |
| **ADR-022** | Real Network Gateway Integration (HTTP REST & Persistent WebSocket) | `GatewayClient` with HTTP & `NetworkGatewayRunner` with WebSocket | `accepted` | Connects MacBook backend to standalone Raspberry Pi gateway daemon over local HTTP (`/health`, `/api/lander/status`, `/api/commands`) and persistent WebSocket (`/ws/telemetry`) with bounded exponential backoff. Preserves in-process simulator mode via `GATEWAY_MODE`. |
| **ADR-023** | Retired Lander Ramp and Rover Telemetry Contract | Sensor-only lander; Pi UDP rover input on port 5005 | `accepted` | Supersedes actuator-specific decisions below. Keeps lander JSON framing and supported status/mode commands; rover packets are exactly `DIST,PITCH,ROLL,CMD,MODE`. Drone interface remains unspecified. |

> **Current architecture amendment (ADR-023):** The ramp has been removed from
> the physical design. Older gate, servo, limit-switch, and movement decisions
> below are historical records and are superseded wherever they conflict with
> ADR-023. The ESP32 firmware reference baseline is preserved as history; the
> current source is sensor/status-only. The user explicitly authorized this
> cleanup, including the baseline firmware update.

---

## Detailed Decision Records

### ADR-001: Mission Backend Host
- **Status**: `accepted`
- **Context**: Need a central platform capable of serving web dashboard assets, managing state history, orchestrating high-level mission workflows, and driving the external HDMI exhibition display.
- **Decision**: MacBook running Python 3 / FastAPI.
- **Consequences**: MacBook backend does not access raw serial pins or ports directly in production.

### ADR-002: Hardware Edge Gateway
- **Status**: `accepted`
- **Context**: The physical lander sits on an exhibition rig separated from the operator desk. Direct USB connection to the MacBook would constrain physical positioning and risk serial port contention.
- **Decision**: Raspberry Pi 4 deployed at the lander rig acting as the dedicated hardware gateway.
- **Consequences**: The Pi owns the sole USB serial connection to the ESP32.

### ADR-003: Physical Control & Safety
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: Servo actuation, limit switch debouncing, and emergency cutouts require deterministic real-time response that high-level operating systems cannot guarantee.
- **Decision**: ESP32 DevKit V1 microcontroller retains sole authority over hardware actuation and local limit interlocks.
- **Consequences**: Safety interlocks function autonomously even if the Raspberry Pi or MacBook disconnects.

### ADR-004: MacBook ↔ Raspberry Pi Communication
- **Status**: `accepted`
- **Context**: Need a clean network protocol for local communication across private Wi-Fi/Ethernet.
- **Decision**: HTTP REST endpoints for state queries and command dispatch; WebSocket connection (`/ws/telemetry`) for streaming 1 Hz telemetry and link status events.
- **Consequences**: Avoids complex distributed messaging brokers (e.g., ROS, MQTT, Kafka) while remaining lightweight and testable.

### ADR-005: Raspberry Pi ↔ ESP32 Serial Protocol
- **Status**: `accepted`
- **Context**: Need reliable edge serial framing between Pi and ESP32.
- **Decision**: USB serial at 115200 baud, 8 data bits, no parity, 1 stop bit (8N1). Newline-delimited UTF-8 JSON payloads (max 255 bytes RX, 512 bytes TX).
- **Consequences**: Human-readable, easily debugged, validated with Pydantic/dataclass schemas at the gateway layer.

### ADR-006: Historical Telemetry & State Storage
- **Status**: `accepted`
- **Context**: Exhibition logs require durable storage for historical playback, anomaly review, and mission telemetry analysis without requiring external database servers.
- **Decision**: SQLite file-based database managed by the MacBook backend.
- **Consequences**: Zero deployment overhead, crash-resilient ACID compliance, local-first operation.

### ADR-007: In-Memory Telemetry Retention
- **Status**: `accepted`
- **Context**: Browser dashboard requires fast, near-instant rendering of recent sensor time series without querying SQLite for every 1-second tick.
- **Decision**: MacBook backend maintains a sliding in-memory window of five minutes of live telemetry.
- **Consequences**: Bounded memory footprint, instant frontend chart updates, decoupled from long-term SQLite archiving.

### ADR-008: Initial & Restart Gate State
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: Software restarts or reconnects cannot assume the mechanical gate remained in its prior position.
- **Decision**: Upon any startup, restart, or communication interruption, physical gate state initializes strictly as `UNKNOWN`.
- **Consequences**: Software never assumes `CLOSED` or `OPEN` until confirmed by debounced limit switch telemetry or a validated status response.

### ADR-009: Reconnection Recovery Behavior
- **Status**: `accepted`
- **Context**: Re-establishing connection after Wi-Fi drop or serial reset must not trigger unintended physical behavior.
- **Decision**: Reconnection routine requests device status (`GET_STATUS`), verifies limits, and resumes telemetry ingestion. **Zero movement commands are ever issued automatically on reconnect.**
- **Consequences**: Eliminates mechanical collision hazards during network or power transients.

### ADR-010: Movement Command Retries
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: If a gate movement command times out or drops, blind automatic re-transmission can cause dangerous repeated motor surges or unexpected movement.
- **Decision**: Automatic movement retries are strictly prohibited until end-to-end command IDs, idempotent duplicate suppression, and verification are implemented and physically tested.
- **Consequences**: Failures must be flagged explicitly to the human operator; no hidden retry loops.

### ADR-011: ESP32 Firmware Baseline
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: Firmware development must remain stable so backend and gateway integration targets a known, frozen contract.
- **Decision**: Firmware baseline is frozen as `v1.3.1-esp32-baseline` (`Lander/lander/lander.ino`).
- **Consequences**: No casual or unsolicited edits to microcontroller firmware code.

### ADR-012: Exhibition Display Output
- **Status**: `accepted`
- **Context**: Exhibition visitors view a large format screen showing real-time mission telemetry and 3D lander orientation.
- **Decision**: Large TV connected directly to the MacBook over HDMI as a secondary monitor running a full-screen browser view.
- **Consequences**: The TV is a passive video sink and does not participate in network or serial protocols.

### ADR-013: Network Environment
- **Status**: `accepted`
- **Context**: Exhibition venues often have unstable or captive-portal public Wi-Fi.
- **Decision**: Dedicated private local network (router / Wi-Fi AP or Ethernet switch). All mission-critical paths require zero external internet connectivity.
- **Consequences**: Core landing and gate actuation demonstrations are fully immune to internet outages.

### ADR-014: Gateway API Contract Specification
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: Defining standard interface contract between MacBook backend and Raspberry Pi gateway.
- **Decision**: Formalized in `app/communication/gateway_contract.py` and `docs/api-contract.md`. Exposes `GET /health`, `GET /api/devices`, `GET /api/lander/status`, `POST /api/commands`, and `WS /ws/telemetry`.
- **Consequences**: Gateway simulator and MacBook backend client use identical Pydantic schemas.

### ADR-015: Command Lifecycle State Machine
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: Need explicit state tracking for operator commands dispatched from MacBook to ESP32.
- **Decision**: Implemented in `app/mission/command.py`. Lifecycle: `CREATED` → `SENT` → `ACKNOWLEDGED` → `COMPLETED` (or `FAILED` / `REJECTED` / `TIMED_OUT` / `UNKNOWN`). Distinguishes gateway/microcontroller acknowledgement from mechanical limit switch confirmation.
- **Consequences**: Clear audit trail for command execution, duplicate suppression, and safety validation.

### ADR-016: Hardware-Free Gateway Simulator Separation
- **Status**: `accepted`
- **Context**: Backend development and test automation must run locally without physical Raspberry Pi or ESP32 hardware.
- **Decision**: Created `GatewaySimulator` in `app/communication/gateway_simulator.py` with deterministic virtual clock and stepped movement. Simulator is explicitly flagged with `IS_SIMULATOR = True` and never masquerades as production hardware.
- **Consequences**: 100% deterministic, hardware-free testing without sleeping or external dependencies.

### ADR-017: Lifespan Background Simulator & Staleness Loop
- **Status**: `accepted`
- **Context**: The FastAPI backend requires real-time telemetry streaming and automated staleness detection during runtime without mutating state on read-only snapshot queries.
- **Decision**: Implemented `SimulatorRunner` in `app/communication/simulator_runner.py` integrated into FastAPI's `lifespan` handler in `app/main.py`. Startup initializes the background loop cleanly; shutdown cleanly cancels and awaits tasks without leaks.
- **Consequences**: Active server execution automatically streams telemetry and detects disconnect/staleness, while testing can advance step-clocks deterministically.

### ADR-018: Gateway-Boundary Request ID Mapping & Telemetry Reconciliation
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: The MacBook backend tracks commands using UUID strings, but the frozen ESP32 firmware strictly requires 32-bit positive integer `request_id`s (`int32_t`). Furthermore, lost serial acknowledgements must not cause blind movement retries or strand commands when the physical movement actually succeeds.
- **Decision**: Implemented `RequestIdMapper` at the gateway boundary in `app/communication/request_mapper.py` for thread-safe bidirectional allocation. Commands with lost acknowledgements remain in `SENT` or `TIMED_OUT` and can be reconciled to `COMPLETED` strictly if fresh, non-stale telemetry confirms arrival at the target endpoint (`OPEN_GATE` requires `gate_state == OPEN` and `open_limit == True`). Unresolved or conflicting movement commands strictly block subsequent movement until status reconciliation resolves physical state.
- **Consequences**: Avoids sending incompatible string IDs to the ESP32. Prohibits blind movement retries. Explicitly recognizes that the frozen ESP32 firmware lacks an on-chip deduplication cache, so end-to-end exactly-once execution is not claimed.

### ADR-019: Raspberry Pi Hardware Gateway Daemon Architecture
- **Status**: `accepted`
- **Context**: Need a distinct, standalone gateway application running on the Raspberry Pi 4 that owns the physical USB serial port (`/dev/ttyUSB0`) to the ESP32 lander, exposes agreed HTTP and WebSocket endpoints, handles serial framing and ESP32 boot ROM text filtering, translates UUID command IDs to integers, broadcasts live telemetry to network clients, and enforces strict safety invariants upon disconnect and reconnection.
- **Decision**: Implemented standalone edge gateway in `gateway/`:
  - `gateway/config.py`: Environment-driven configuration (`GATEWAY_SERIAL_PORT`, baud rate, timeouts).
  - `gateway/transport.py`: `SerialTransport` abstraction supporting `PySerialTransport` (physical serial) and `SimulatedSerialTransport` (in-memory queues for hardware-free testing).
  - `gateway/serial_manager.py`: Manages serial line framing, background reader/staleness tasks, filters non-JSON bootloader ROM text without crashing, integrates `RequestIdMapper` at serial boundary, and tracks ESP32 state (`ONLINE`, `STALE`, `OFFLINE`, `NOT_CONNECTED`).
  - `gateway/rover_udp.py`: Receives and validates rover GUI datagrams on UDP 5005, tracks last valid receipt, and broadcasts online/offline updates. `gateway.main` starts and stops this receiver beside the serial manager.
  - `gateway/ws_manager.py`: `WebSocketBroadcaster` broadcasting lander telemetry and rover UDP status updates to clients, pruning disconnected clients without interrupting serial ingestion.
  - `gateway/routes.py` & `gateway/main.py`: Standalone FastAPI application with lifespan management exposing `GET /health`, `GET /api/devices`, `GET /api/lander/status`, `POST /api/commands`, and `WS /ws/telemetry`.
- **Consequences**: Gateway runs as a standalone service directly testable on macOS without hardware or deployed to the physical Raspberry Pi. Disconnection clears cached device/sensor state. Reconnection queries fresh status via `GET_STATUS`; it issues no physical action.

### ADR-021: Mission Control Exhibition Dashboard Architecture, Offline-First Strategy, and Live Broadcast
- **Status**: `superseded` (historical; superseded by ADR-023)
- **Context**: Need a responsive, high-contrast mission dashboard view for the exhibition display TV (connected to MacBook over HDMI) and operator console on private Wi-Fi. It must work completely offline without CDN dependencies, distinguish live telemetry from historical/cached data, enforce physical safety gating on actuation buttons, provide an audit log of commands and transitions, and gracefully handle WebSocket disconnects with automatic polling fallback.
- **Decision**:
  - **Zero-Dependency Vanilla Frontend**: Implemented in `frontend/` (`index.html`, `css/dashboard.css`, `js/dashboard.js`). No external npm, webpack, or CDN scripts/styles. Served directly by FastAPI via `StaticFiles(directory="frontend")` and route `GET /dashboard`.
  - **Exhibition HUD Layout**: Dark space theme with high contrast typography (`#f8fafc`, `#94a3b8`), Mars rust accents (`#e05638`), and status glow indicators for 10-foot TV viewing.
  - **Live WebSocket Feed & Polling Fallback**: `WS /ws/telemetry` via `DashboardBroadcaster` in `backend/app/communication/broadcaster.py`. On connection, pushes an initial `state_snapshot`. Streams live telemetry ticks and state transitions in real time. If the WebSocket drops, the client immediately switches to background HTTP polling (`/api/mission/state`, `/api/mission/commands`, `/api/mission/events`, `/api/mission/telemetry/history`) and attempts exponential reconnection.
  - **Strict Safety Control Gating**: Controls for `OPEN_GATE` and `CLOSE_GATE` are physically safety-gated in the UI:
    - Disabled unless `gateway_state == 'ONLINE'` and `device_state == 'ONLINE'`.
    - Disabled if any hardware fault is latched (`latched_fault`).
    - Disabled if any movement command is currently in-flight.
    - `OPEN_GATE` is strictly disabled unless current gate state is verified as `CLOSED`.
    - `CLOSE_GATE` is strictly disabled unless current gate state is verified as `OPEN`.
    - Disables automatic retries. Shows human-readable interlock explanations.
  - **Historical vs. Live Data Discrimination**: Telemetry with a host receipt time older than 5 seconds or received when the device is not `ONLINE` is explicitly flagged as `⚠ HISTORICAL TELEMETRY (CACHED)` rather than active real-time data (matching the current dashboard implementation).
  - **Session Reset Modal**: Requires confirmation before calling `POST /api/mission/session/reset` to prevent accidental history clearance during exhibitions.
- **Consequences**: Completely self-contained, offline-first dashboard running on private exhibition networks with zero external internet requirements. Real-time updates with robust fallbacks, preserving all physical hardware safety invariants.

### ADR-022: Real Network Gateway Integration (HTTP REST & Persistent WebSocket)
- **Status**: `accepted`
- **Context**: The backend required physical network integration with the standalone Raspberry Pi edge gateway daemon (`gateway/`) over local HTTP and WebSocket, while preserving in-process `GatewaySimulator` mode for automated testing and standalone development.
- **Decision**:
  - **Network-Capable `GatewayClient`**: Extended [`backend/app/communication/gateway_client.py`](file:///Users/prajwalnavadagp/Engineering/mars-mission-control/backend/app/communication/gateway_client.py) with zero-dependency synchronous HTTP requests (`urllib.request`) for `check_gateway_health()` (`GET /health`), `refresh_device_status()` (`GET /api/lander/status`), and `dispatch_command()` (`POST /api/commands`).
  - **Persistent `NetworkGatewayRunner`**: Implemented [`backend/app/communication/network_runner.py`](file:///Users/prajwalnavadagp/Engineering/mars-mission-control/backend/app/communication/network_runner.py) maintaining a background WebSocket listener (`WS /ws/telemetry`), bounded exponential backoff reconnection (`reconnect_initial_delay_s=1.0` up to `reconnect_max_delay_s=10.0`), periodic health monitoring, and telemetry TTL pruning.
  - **Mode Selection via Environment**: Configured via `GATEWAY_MODE` (`"simulator"` [default] vs `"network"` / `"real"`), `GATEWAY_HTTP_URL` (default `http://127.0.0.1:8001`), and `GATEWAY_WS_URL` (default `ws://127.0.0.1:8001/ws/telemetry`).
  - **Strict Reconnection & Invariant Safety**: On network link loss, transitions gateway/device to `OFFLINE` and clears stale sensor state. Reconnection issues non-movement queries (`GET_STATUS`) only; zero movement commands are ever issued or retried on reconnect.
  - **Thread-Safe `SimulatedSerialTransport`**: Upgraded queue primitives in [`gateway/transport.py`](file:///Users/prajwalnavadagp/Engineering/mars-mission-control/gateway/transport.py) with standard library `queue.Queue` and non-blocking `asyncio.to_thread` calls, enabling multi-threaded cross-loop simulation in real network integration tests.
- **Consequences**: Enables MacBook Mission Control to talk across private Wi-Fi/Ethernet to the physical Raspberry Pi 4 edge gateway, fully tested using real localhost sockets without physical hardware dependencies.

### ADR-023: Retired Lander Ramp and Rover Telemetry Contract
- **Status**: `accepted`
- **Context**: The physical lander ramp and its actuator components have been removed from the design. The rover's current BOM and telemetry interface support only HC-SR04 distance and MPU6050 attitude readings plus reported command/mode; they have no encoders or battery-voltage sensing circuit. A drone transport/schema is not yet defined.
- **Decision**: Remove ramp-only servo PWM, button, limit-switch logic, movement commands/state/faults, API fields, dashboard controls, and persistence columns. Retain BMP280/DHT11, display, status LEDs, WS2812B, 115200 8N1 framing, and `GET_STATUS`, `SET_ACTIVE`, `SET_STANDBY`. Run the Pi's rover UDP receiver in the existing gateway FastAPI lifecycle on `ROVER_UDP_PORT` (default 5005), separate from the lander serial manager. Validate exactly `DIST`, `PITCH`, `ROLL`, `CMD`, and `MODE`; report offline based on valid packet age and `ROVER_OFFLINE_TIMEOUT_S`. Simulator and network modes expose the same rover status contract. No battery percentage, battery voltage, speed, encoder, or rover command-dispatch behavior is added. Keep drone integration explicitly unimplemented until its owner defines a transport and payload contract.
- **Consequences**: Historical ADR entries remain as records but their actuator-specific decisions are superseded. SQLite migration retains timestamps, mode, sensor readings, and sensor health while dropping retired actuator columns. Firmware source changes are authorized by this cleanup request; physical compilation/hardware acceptance must be reported separately.

### ADR-024: Wi-Fi Lander Telemetry Architecture and Standalone Gateway Transport
- **Status**: `accepted`
- **Context**: The physical USB serial connection between the ESP32 lander controller and Raspberry Pi 4 gateway is replaced by a wireless link over the private local network. Operational serial ingestion on the Pi must be retired while maintaining existing HTTP/WebSocket contracts, rover UDP 5005 ingestion, lander telemetry schemas, and hardware-free testability.
- **Decision**:
  - Replaced `SerialTransport` and `SerialManager` in `gateway/` with `LanderTCPTransport` and `LanderManager` listening on `LANDER_TCP_HOST:LANDER_TCP_PORT` (default `0.0.0.0:5006`).
  - The ESP32 lander initiates a TCP client connection to the Pi gateway over private local Wi-Fi, streaming newline-delimited JSON telemetry at ~1 Hz and receiving status/mode commands (`GET_STATUS`, `SET_ACTIVE`, `SET_STANDBY`).
  - ESP32 USB serial remains active exclusively for firmware flashing and local development debugging; the Raspberry Pi gateway never opens or contends for the serial port.
  - Rover UDP receiver on port 5005 is fully preserved in the gateway application lifecycle.
  - Power architecture: Low-current sensors (BMP280, DHT11) and display (20x4 LCD) are powered safely from ESP32 dev-board rails. WS2812B LED strip (30 LEDs) brightness is strictly capped at 60/255 (~150–300 mA peak) and powered from 5V/VIN (never GPIO). Wi-Fi eliminates the data cable to the Pi, but the ESP32 still requires a stable electrical power supply.
- **Consequences**: Completely wireless operational link for the lander. Removed `pyserial` dependency from gateway. Preserved all REST, WebSocket, dashboard, and simulator contracts.
