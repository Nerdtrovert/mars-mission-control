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
| **ADR-003** | Physical Control & Safety | ESP32 Microcontroller | `accepted` | Dedicated embedded controller for GPIOs, servo PWM, limit switches, and local safety interlocks. |
| **ADR-004** | MacBook ↔ Pi Communication | HTTP + WebSocket (JSON) | `accepted` | HTTP for command dispatch and request-response; WebSocket for live telemetry streaming. |
| **ADR-005** | Pi ↔ ESP32 Communication | USB Serial (115200 8N1), newline-delimited JSON | `accepted` | Robust, framed serial protocol. Single-process ownership prevents port contention. |
| **ADR-006** | Historical Telemetry & State Storage | SQLite on MacBook | `accepted` | Embedded, zero-configuration local relational database suitable for exhibition workloads without external services. |
| **ADR-007** | In-Memory Telemetry Retention | 5-minute sliding window | `accepted` | Memory-bounded live telemetry cache for immediate UI charting, backed by persistent SQLite storage. |
| **ADR-008** | Initial & Restart Gate State | Reverts to `UNKNOWN` | `accepted` | Ground truth belongs strictly to physical limit switches. Never infer endpoint position across reboots or disconnects. |
| **ADR-009** | Reconnection Recovery Behavior | Refresh status via `GET_STATUS`; zero automatic movement | `accepted` | Re-establishes link and queries fresh switch readings. Never commands physical motion on reconnect. |
| **ADR-010** | Movement Command Retries | Strictly disabled | `accepted` | Prohibits blind retries of `OPEN_GATE` or `CLOSE_GATE` to prevent mechanical jamming and race conditions. |
| **ADR-011** | ESP32 Firmware Baseline | Freeze `v1.3.1-esp32-baseline` | `accepted` | Stable baseline in `Lander/lander/lander.ino`. No ad-hoc firmware rewriting. |
| **ADR-012** | Exhibition Display Output | TV via direct HDMI from MacBook | `accepted` | Passive display sink connected via HDMI; not a participant in local network communication. |
| **ADR-013** | Network Environment | Private Local Wi-Fi / Ethernet | `accepted` | Core telemetry, command relay, and mission state must operate completely offline without public internet. |
| **ADR-014** | Gateway API Contract Spec | `/health`, `/api/devices`, `/api/lander/status`, `/api/commands`, `/ws/telemetry` | `accepted` | Standard REST/WS gateway interface specifications implemented in `app/communication/gateway_contract.py` and `docs/api-contract.md`. |
| **ADR-015** | Command Lifecycle States | `CREATED` → `SENT` → `ACKNOWLEDGED` → `COMPLETED` / `FAILED` / `REJECTED` / `TIMED_OUT` | `accepted` | Explicit command state machine separating device receipt acknowledgement from physical switch confirmation in `app/mission/command.py`. |
| **ADR-016** | Hardware-Free Simulator Separation | In-memory `GatewaySimulator` with deterministic step clock | `accepted` | Isolated development simulator in `app/communication/gateway_simulator.py`. Never masquerades as real hardware in production. |
| **ADR-017** | Lifespan Background Simulator & Staleness Loop | `SimulatorRunner` managed via FastAPI `lifespan` | `accepted` | Starts and stops continuous background telemetry streaming and staleness checks cleanly without leaking tasks or mutating read-only snapshots. |
| **ADR-018** | Gateway-Boundary Request ID Mapping & Reconciliation | `RequestIdMapper` at serial boundary + telemetry endpoint reconciliation | `accepted` | Maps MacBook UUID command_ids to ESP32 32-bit integer request_ids; reconciles lost-ACK movement commands only via confirmed endpoint telemetry; blocks duplicate/conflicting movement. |
| **ADR-019** | Raspberry Pi Hardware Gateway Daemon | Standalone FastAPI service in `gateway/` with `SerialManager`, `RequestIdMapper`, and broadcast WebSocket | `accepted` | Exposes `/health`, `/api/devices`, `/api/lander/status`, `/api/commands`, `/ws/telemetry`. Manages serial link (115200 8N1), ROM boot text filtering, and safety on disconnect/reconnect. |
| **ADR-020** | SQLite Persistence, 5-Minute Retention, and Session Reset | `SQLiteStorage` in `app/storage/` with `telemetry`, `mission_events`, and `commands` tables | `accepted` | Thread-safe persistence with WAL mode, deterministic 5-minute sliding retention, event transition deduplication, safe restart without auto-movement, and clean session reset. |
| **ADR-021** | Exhibition Dashboard UI & Live WebSocket Broadcast | Vanilla HTML5/CSS3/ES6 in `frontend/` + `WS /ws/telemetry` | `accepted` | Zero-dependency, offline-first dashboard served by FastAPI at `/dashboard`. Dark aerospace HUD layout for exhibition TV, strict safety button gating, historical vs live data distinction, automatic WebSocket reconnect with polling fallback. |
| **ADR-022** | Real Network Gateway Integration (HTTP REST & Persistent WebSocket) | `GatewayClient` with HTTP & `NetworkGatewayRunner` with WebSocket | `accepted` | Connects MacBook backend to standalone Raspberry Pi gateway daemon over local HTTP (`/health`, `/api/lander/status`, `/api/commands`) and persistent WebSocket (`/ws/telemetry`) with bounded exponential backoff. Preserves in-process simulator mode via `GATEWAY_MODE`. |

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
- **Status**: `accepted`
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
- **Status**: `accepted`
- **Context**: Software restarts or reconnects cannot assume the mechanical gate remained in its prior position.
- **Decision**: Upon any startup, restart, or communication interruption, physical gate state initializes strictly as `UNKNOWN`.
- **Consequences**: Software never assumes `CLOSED` or `OPEN` until confirmed by debounced limit switch telemetry or a validated status response.

### ADR-009: Reconnection Recovery Behavior
- **Status**: `accepted`
- **Context**: Re-establishing connection after Wi-Fi drop or serial reset must not trigger unintended physical behavior.
- **Decision**: Reconnection routine requests device status (`GET_STATUS`), verifies limits, and resumes telemetry ingestion. **Zero movement commands are ever issued automatically on reconnect.**
- **Consequences**: Eliminates mechanical collision hazards during network or power transients.

### ADR-010: Movement Command Retries
- **Status**: `accepted`
- **Context**: If a gate movement command times out or drops, blind automatic re-transmission can cause dangerous repeated motor surges or unexpected movement.
- **Decision**: Automatic movement retries are strictly prohibited until end-to-end command IDs, idempotent duplicate suppression, and verification are implemented and physically tested.
- **Consequences**: Failures must be flagged explicitly to the human operator; no hidden retry loops.

### ADR-011: ESP32 Firmware Baseline
- **Status**: `accepted`
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
- **Status**: `accepted`
- **Context**: Defining standard interface contract between MacBook backend and Raspberry Pi gateway.
- **Decision**: Formalized in `app/communication/gateway_contract.py` and `docs/api-contract.md`. Exposes `GET /health`, `GET /api/devices`, `GET /api/lander/status`, `POST /api/commands`, and `WS /ws/telemetry`.
- **Consequences**: Gateway simulator and MacBook backend client use identical Pydantic schemas.

### ADR-015: Command Lifecycle State Machine
- **Status**: `accepted`
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
- **Status**: `accepted`
- **Context**: The MacBook backend tracks commands using UUID strings, but the frozen ESP32 firmware strictly requires 32-bit positive integer `request_id`s (`int32_t`). Furthermore, lost serial acknowledgements must not cause blind movement retries or strand commands when the physical movement actually succeeds.
- **Decision**: Implemented `RequestIdMapper` at the gateway boundary in `app/communication/request_mapper.py` for thread-safe bidirectional allocation. Commands with lost acknowledgements remain in `SENT` or `TIMED_OUT` and can be reconciled to `COMPLETED` strictly if fresh, non-stale telemetry confirms arrival at the target endpoint (`OPEN_GATE` requires `gate_state == OPEN` and `open_limit == True`). Unresolved or conflicting movement commands strictly block subsequent movement until status reconciliation resolves physical state.
- **Consequences**: Avoids sending incompatible string IDs to the ESP32. Prohibits blind movement retries. Explicitly recognizes that the frozen ESP32 firmware lacks an on-chip deduplication cache, so end-to-end exactly-once execution is not claimed.

### ADR-019: Raspberry Pi Hardware Gateway Daemon Architecture
- **Status**: `accepted`
- **Context**: Need a distinct, standalone gateway application running on the Raspberry Pi 4 that owns the physical USB serial port (`/dev/ttyUSB0`) to the ESP32 lander, exposes agreed HTTP and WebSocket endpoints, handles serial framing and ESP32 boot ROM text filtering, translates UUID command IDs to integers, broadcasts live telemetry to network clients, and enforces strict safety invariants upon disconnect and reconnection.
- **Decision**: Implemented standalone edge gateway in `gateway/`:
  - `gateway/config.py`: Environment-driven configuration (`GATEWAY_SERIAL_PORT`, baud rate, timeouts).
  - `gateway/transport.py`: `SerialTransport` abstraction supporting `PySerialTransport` (physical serial) and `SimulatedSerialTransport` (in-memory queues for hardware-free testing).
  - `gateway/serial_manager.py`: Manages serial line framing, background reader/staleness tasks, filters non-JSON bootloader ROM text without crashing, integrates `RequestIdMapper` at serial boundary, tracks ESP32 state (`ONLINE`, `STALE`, `OFFLINE`, `NOT_CONNECTED`), and reverts physical gate state strictly to `UNKNOWN` when disconnected.
  - `gateway/ws_manager.py`: `WebSocketBroadcaster` broadcasting 1 Hz telemetry and asynchronous `gate_status` events to clients, pruning disconnected clients without interrupting serial ingestion.
  - `gateway/routes.py` & `gateway/main.py`: Standalone FastAPI application with lifespan management exposing `GET /health`, `GET /api/devices`, `GET /api/lander/status`, `POST /api/commands`, and `WS /ws/telemetry`.
- **Consequences**: Gateway runs as a standalone service directly testable on macOS without hardware or deployed to the physical Raspberry Pi. Disconnection immediately invalidates gate state to `UNKNOWN`. Reconnection strictly queries fresh status via `GET_STATUS` and never triggers automatic movement. Zero blind retries.

### ADR-021: Mission Control Exhibition Dashboard Architecture, Offline-First Strategy, and Live Broadcast
- **Status**: `accepted`
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
  - **Strict Reconnection & Invariant Safety**: On network link loss, transitions gateway/device to `OFFLINE` and gate state strictly to `UNKNOWN`. Reconnection issues non-movement queries (`GET_STATUS`) only; zero movement commands are ever issued or retried on reconnect.
  - **Thread-Safe `SimulatedSerialTransport`**: Upgraded queue primitives in [`gateway/transport.py`](file:///Users/prajwalnavadagp/Engineering/mars-mission-control/gateway/transport.py) with standard library `queue.Queue` and non-blocking `asyncio.to_thread` calls, enabling multi-threaded cross-loop simulation in real network integration tests.
- **Consequences**: Enables MacBook Mission Control to talk across private Wi-Fi/Ethernet to the physical Raspberry Pi 4 edge gateway, fully tested using real localhost sockets without physical hardware dependencies.
