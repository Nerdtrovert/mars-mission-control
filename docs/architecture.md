# Mars Mission Control — System Architecture & Component Boundaries (docs/architecture.md)

This document details the high-level architecture, subsystem boundaries, data flows, and hardware interaction models for the Mars Mission Control exhibition project.

---

## 1. Physical Architecture Topology

```
 +--------------------------------------------------------------------------------------------------------------------+
 |                                          EXHIBITION RIG / LANDER PLATFORM                                          |
 |                                                                                                                    |
 |   +------------------------------------+             USB Serial              +----------------------------------+  |
 |   |        ESP32 Lander Controller     | <=================================> |    Raspberry Pi 4 Edge Gateway   |  |
 |   | - Servo PWM (MG996R pair)          |          (115200 8N1 JSON)          | - Serial framed port owner       |  |
 |   | - Debounced Limit Switches         |                                     | - HTTP REST API                  |  |
 |   | - Environmental Sensors (BMP, DHT) |                                     | - WebSocket Telemetry Broadcaster|  |
 |   | - WS2812B & LCD Status Output      |                                     +----------------------------------+  |
 |   +------------------------------------+                                                       ||                  |
 +------------------------------------------------------------------------------------------------||------------------+
                                                                                                  || Private Local Wi-Fi
                                                                                                  || (No internet required)
 +------------------------------------------------------------------------------------------------||------------------+
 |                                               OPERATOR & MISSION CONTROL STATION               ||                  |
 |                                                                                                \/                  |
 |   +------------------------------------+                                     +----------------------------------+  |
 |   |          Exhibition TV             | <================================== |      MacBook Mission Backend     |  |
 |   | - Passive secondary video monitor  |             HDMI Video              | - FastAPI Mission Coordinator    |  |
 |   | - Full-screen dashboard UI         |                                     | - Gateway Client Adapter         |  |
 |   | - Mission status dashboard         |                                     | - SQLite Mission History        |  |
 |   +------------------------------------+                                     | - Operator Web Dashboard Host    |  |
 |                                                                              +----------------------------------+  |
 +--------------------------------------------------------------------------------------------------------------------+
```

---

## 2. Component Ownership Boundaries

### 2.1 ESP32 Lander Controller
- **Physical Ownership**: Controls GPIOs 18 & 19 (servo signals), GPIO 23 (button), GPIOs 32 & 33 (limits), GPIOs 25 & 26 (LEDs), GPIO 27 (WS2812B), GPIO 17 (DHT11), and GPIOs 21 & 22 (I2C bus).
- **Autonomous Safety**: Evaluates mechanical switch debouncing and servo ramp limits locally. If network communication drops, local limit switch protection remains 100% active.
- **Frozen Firmware**: The microcontroller runs `v1.3.1-esp32-baseline` from `Lander/lander/lander.ino`.

### 2.2 Raspberry Pi 4 Edge Gateway
- **Physical Link**: Sole process holding the ESP32 USB serial link (commonly `/dev/ttyACM0` or `/dev/ttyUSB0`).
- **Framing & Relay**: Deserializes raw newline-delimited bytes into structured JSON objects, buffers telemetry, verifies incoming command schemas, and handles USB disconnects/reconnects.
- **Isolation**: Prevents race conditions and multiple processes contending for the single serial port.

### 2.3 MacBook Mission Control Backend
- **State Coordination**: Aggregates telemetry, monitors command lifecycles (`CREATED` → `SENT` → `ACKNOWLEDGED` → `COMPLETED`), detects stale timeouts, and logs state transitions into SQLite.
- **Dashboard API**: Serves web assets and WebSocket telemetry to the browser dashboard.
- **Constraint**: Must NEVER attempt to access the ESP32 serial port directly in production.

### 2.4 Exhibition TV
- **Display Sink**: Connected directly to the MacBook over HDMI as a second screen running the exhibition dashboard in full-screen mode. Does not participate in network protocols.

---

## 3. Data Flow & Communication Lifecycle

### 3.1 Normal Telemetry Streaming (1 Hz)
1. ESP32 loops every 1000 ms, reads BMP280 and DHT11 sensors, reads limit switches.
2. Emits `{"type": "telemetry", ...}\n` over USB serial at 115200 baud.
3. Raspberry Pi reads line, checks framing, and broadcasts over WebSocket `/ws/telemetry`.
4. MacBook `GatewayClient` ingests JSON line, passes to `TelemetryService`, and updates `MissionStateManager`.
5. The browser dashboard renders current mission state, live sensor values, command history, and telemetry history.

### 3.2 Safe Movement Command Sequence (`OPEN_GATE`)
```
Operator         MacBook Backend                 Raspberry Pi                     ESP32 Lander
   |                    |                              |                               |
   |--- Submit Command -|                              |                               |
   |                    |-- Validate Safety Precond. --|                               |
   |                    |   (Gate must be CLOSED,      |                               |
   |                    |    Device must be ONLINE)    |                               |
   |                    |                              |                               |
   |                    |-- POST /api/commands ------->|                               |
   |                    |   {"command": "OPEN_GATE"}   |-- Serial JSON Line ---------->|
   |                    |                              |   {"command": "OPEN_GATE"}    |
   |                    |                              |<-- Ack Line (accepted: true) -|
   |                    |<-- Ack HTTP Response --------|   (Movement starts: OPENING)  |
   |                    |   (Status: ACKNOWLEDGED)     |                               |
   |                    |   [NOT COMPLETED YET]        |                               |
   |                    |                              |                               |
   |                    |                              |<-- gate_status: "OPENING" ----|
   |                    |<-- WS: gate_status ----------|                               |
   |                    |                                       ... (Servos ramp) ...  |
   |                    |                              |<-- gate_status: "OPEN" -------|
   |                    |<-- WS: gate_status ----------|   (Open limit switch hit!)    |
   |                    |-- Mark COMPLETED ------------|                               |
   |<-- UI Updates -----|                                                              |
```

---

## 4. Subsystem Isolation & Fault Handling

- **Latched Hardware Faults**: Faults reported by the ESP32 (`FAULT_BOTH_LIMITS_ACTIVE`, `FAULT_OPEN_TIMEOUT`, etc.) are latched in firmware. Software cannot blindly reset a hardware fault.
- **Network Degradation**: If the Pi gateway or Wi-Fi drops, the lander continues running its autonomous safety routines. The MacBook transitions device state to `OFFLINE` and physical gate state to `UNKNOWN`.
- **Sensor Fault Tolerance**: If the DHT11 or BMP280 fails or disconnects, the field is reported as `null` with sensor state `FAILED`. Unrelated telemetry and gate actuation continue safely.

---

## 5. Future Device Integration Boundary (Proposed; Not Implemented)

The current application integrates only the ESP32 lander. `MissionStateManager`, the lander command set, the Pi serial service, and the dashboard gate controls are lander-specific. The gateway's current `/api/devices` response describes the connected lander; it is not a general rover/drone registry. Do not treat this proposal as an API contract or as implemented capability.

Future rover or drone work should be added beside the lander path through an explicitly reviewed design, preserving current lander behavior:

- **Identity and type:** Assign each physical unit a stable, unique `device_id` independent of its network address, plus a separately defined device type and declared capabilities. Do not reuse `esp32-lander` or infer identity from the transport address.
- **Independent lifecycle:** Track connection, freshness, and faults per device. A failure or stale stream from one vehicle must not mark another vehicle offline or alter the lander's verified gate state.
- **Device-specific telemetry:** Keep each device's measurements and schema explicit and versioned. A rover or drone payload must not be forced into lander-only fields. Preserve the distinction between the device clock/uptime and host receipt time, and mark simulated records as simulated.
- **Transport ownership:** Use a device-appropriate adapter with a single clear owner for each physical transport. The existing Pi remains the sole owner of the lander's USB serial port; a new integration must not open that port from the MacBook or compete with the gateway.
- **Commands and acknowledgements:** Define which component validates and dispatches each command. Correlate requests and responses, distinguish accepted/acknowledged from completed, and never add automatic movement or flight retries without a separately accepted safety design. Reconnect by querying state; do not resume physical action automatically.
- **Simulation and acceptance:** Provide deterministic hardware-free tests for schema validation, ordering, disconnect/reconnect, timeouts, and safety boundaries. Before hardware acceptance, test each device's transport and local safety behavior on the relevant physical unit; simulator success alone is not hardware verification.
- **Safety isolation:** Keep device-specific emergency behavior and interlocks under the device controller's authority. A generic dashboard or backend must not invent a safety capability that the device does not expose.

These principles are a planning boundary only. No generic device framework, additional API fields/endpoints, or rover/drone code is introduced by this document.
