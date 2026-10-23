# Raspberry Pi Hardware Gateway — API Contract (docs/api-contract.md)

This document specifies the HTTP and WebSocket API contract exposed by the Raspberry Pi hardware edge gateway to the MacBook backend over the private local Wi-Fi / Ethernet network.

---

## 1. Overview & Connection Architecture

The Raspberry Pi 4 edge gateway manages the physical USB serial connection to the ESP32 lander. It exposes a local HTTP REST API and a WebSocket stream to the MacBook backend.

```
 +----------------------+       HTTP / REST (Commands & Status)      +-----------------------+
 |    MacBook Backend   | -----------------------------------------> |  Raspberry Pi Gateway |
 |   (Gateway Client)   | <========================================= |    (HTTP / WS Daemon) |
 +----------------------+             WebSocket (Telemetry)          +-----------------------+
```

### Base URL
- HTTP Base URL: `http://<raspberry-pi-ip>:8001`
- WebSocket URL: `ws://<raspberry-pi-ip>:8001/ws/telemetry`

---

## 2. Gateway Endpoints

### 2.1 GET /health
Queries the health and status of the gateway daemon and its serial link to the ESP32.

#### Response (200 OK)
```json
{
  "status": "healthy",
  "connection_state": "ONLINE",
  "version": "1.0.0",
  "uptime_seconds": 3612.4,
  "serial_port": "/dev/ttyUSB0",
  "device_connected": true
}
```

#### Fields
- `status` (`string`): `"healthy"`, `"degraded"`, or `"unhealthy"`.
- `connection_state` (`string`): `"ONLINE"`, `"STALE"`, `"OFFLINE"`, or `"NOT_CONNECTED"`.
- `version` (`string`): Gateway software version string.
- `uptime_seconds` (`number`): Gateway process uptime in seconds (non-negative).
- `serial_port` (`string | null`): Serial device path in use (e.g. `/dev/ttyUSB0`).
- `device_connected` (`boolean`): Whether the serial link to the ESP32 is open.

---

### 2.2 GET /api/devices
Returns the peripheral list managed by the edge gateway. The current implementation reports the ESP32 lander; this endpoint is not a general rover/drone registry.

#### Response (200 OK)
```json
{
  "devices": [
    {
      "device_id": "esp32-lander",
      "name": "ESP32 Lander Controller",
      "port": "/dev/ttyUSB0",
      "connection_state": "ONLINE",
      "firmware_version": "1.3.1",
      "last_seen_at": "2026-10-20T12:00:00Z"
    }
  ]
}
```

---

### 2.3 GET /api/lander/status
Queries the latest confirmed state of the ESP32 lander.

#### Response (200 OK)
```json
{
  "gateway_state": "ONLINE",
  "device_state": "ONLINE",
  "timestamp_ms": 142500,
  "mode": "ACTIVE",
  "gate_state": "CLOSED",
  "closed_limit": true,
  "open_limit": false,
  "fault": null,
  "pending_standby": false,
  "startup_limits_settled": true,
  "limits_established": true,
  "bmp280_ok": true,
  "dht11_ok": true,
  "bmp280_state": "OK",
  "dht11_state": "OK",
  "firmware": "1.3.1"
}
```

#### Device Disconnected Behavior
When the Pi is reachable but the ESP32 is unplugged or offline:
```json
{
  "gateway_state": "ONLINE",
  "device_state": "OFFLINE",
  "timestamp_ms": null,
  "mode": null,
  "gate_state": "UNKNOWN",
  "closed_limit": false,
  "open_limit": false,
  "fault": null,
  "pending_standby": null,
  "startup_limits_settled": null,
  "limits_established": null,
  "bmp280_ok": null,
  "dht11_ok": null,
  "bmp280_state": "FAILED",
  "dht11_state": "FAILED",
  "firmware": null
}
```

---

### 2.4 POST /api/commands
Submits a command for relay to the ESP32 lander.

#### Request Format
```json
{
  "command_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "command": "OPEN_GATE",
  "params": null
}
```

#### Supported Commands
- `GET_STATUS`: Queries device status snapshot.
- `SET_ACTIVE`: Enters ACTIVE operating mode (sensor polling, gate actuation enabled).
- `SET_STANDBY`: Enters STANDBY operating mode (stops movement, sensor polling disabled).
- `OPEN_GATE`: Commands gate ramp to open (requires gate to be confirmed `CLOSED`).
- `CLOSE_GATE`: Commands gate ramp to close (requires gate to be confirmed `OPEN`).

#### Response Format (Acknowledgement)
```json
{
  "command_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "accepted": true,
  "reason": null,
  "fault": null,
  "timestamp": "2026-10-20T12:00:01Z"
}
```

#### Acknowledgement vs Completion Semantics
> [!IMPORTANT]
> A `command_ack` with `accepted: true` confirms only that the gateway and lander validated and accepted the instruction.
> It **does not mean** the gate has completed moving. Physical movement completion is confirmed strictly when the destination limit switch reports active via subsequent `gate_status` or `telemetry`.

#### Rejection Response Example
```json
{
  "command_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "accepted": false,
  "reason": "GATE_BUSY",
  "fault": null,
  "timestamp": "2026-10-20T12:00:01Z"
}
```

#### Rejection Reasons
- `GATE_BUSY`: Gate is currently in motion (`OPENING` or `CLOSING`).
- `INVALID_STATE`: Mode is `STANDBY`, or destination already matched (`OPEN_GATE` when already `OPEN`).
- `GATE_UNKNOWN`: Physical endpoint not established by limit switches.
- `GATE_FAULT`: Lander is in a latched fault state.
- `DEVICE_OFFLINE`: ESP32 serial link is disconnected.
- `INVALID_COMMAND`: Command not recognized by firmware.

---

### 2.5 WS /ws/telemetry
Continuous WebSocket stream broadcasting ESP32 telemetry lines and status events.

#### Message Payload: Telemetry Tick (approx. 1 Hz)
```json
{
  "type": "telemetry",
  "timestamp_ms": 143500,
  "mode": "ACTIVE",
  "gate_state": "CLOSED",
  "closed_limit": true,
  "open_limit": false,
  "bmp_temperature_c": 24.5,
  "pressure_hpa": 1013.2,
  "dht_temperature_c": 24.0,
  "humidity_pct": 58.0,
  "bmp280_ok": true,
  "dht11_ok": true,
  "fault": null
}
```

#### Message Payload: Gate Status Transition Event
```json
{
  "type": "gate_status",
  "state": "OPENING"
}
```

---

## 3. Errors and Disconnected States

The gateway routes use FastAPI request validation, which returns HTTP `422` for invalid request bodies, and HTTP `404` for unknown routes. The gateway routes do not install a custom error-response handler. For a well-formed command that cannot be carried out, `POST /api/commands` returns the `CommandResponse` schema with HTTP `200` and `accepted: false` plus a `reason` such as `DEVICE_OFFLINE`, `GATE_UNKNOWN`, or `GATE_FAULT`. Gateway/device connectivity is also reported in health/status responses; an unavailable gateway does not produce simulated readings.

---

## 4. Connection State & Reconnection Rules

1. **Independent Tracking**: The gateway's health and the ESP32's health are tracked independently.
2. **Fresh Status Upon WebSocket Reconnect**: After the MacBook network runner establishes its gateway WebSocket connection, it queries `GET /api/lander/status` before trusting physical state. Periodic HTTP `/health` checks update gateway connectivity; HTTP health recovery by itself does not trigger a device-status refresh.
3. **No Automatic Movement**: Reconnection routines MUST NEVER dispatch movement commands (`OPEN_GATE`, `CLOSE_GATE`).

The Pi serial manager defaults to `STALE` after more than 3 seconds without a JSON object from the device and `OFFLINE` after more than 5 seconds; `GATEWAY_STALE_TIMEOUT_S` and `GATEWAY_OFFLINE_TIMEOUT_S` configure these thresholds. The MacBook network runner separately defaults to `STALE` after 3 seconds and `OFFLINE` after 10 seconds without device telemetry. These states describe freshness/connection; gateway reachability and sensor health remain independent.

For the separate MacBook Mission Control API, invalid or unsafe command submissions return HTTP `400`; its status and telemetry endpoints expose connection and sensor health in their response bodies.

---

## 5. MacBook Mission Control API (Dashboard)

This is the separate FastAPI service on the MacBook, normally at `http://127.0.0.1:8000`. The implementation is in `backend/app/main.py` and `backend/app/api/routes.py`.

### REST endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Application status and `simulation_mode` flag. |
| `GET` | `/health` | Backend health and `simulation_mode` flag. |
| `GET` | `/dashboard` | Serves the dashboard HTML. |
| `GET` | `/api/mission/state` | Current mission snapshot, including gateway/device state, gate/limits, faults, sensor health, UTC host timestamps, and `simulation_mode`. |
| `GET` | `/api/mission/commands` | Tracked command records. |
| `POST` | `/api/mission/commands` | Submit a command using `command` or `command_type`; backend safety/duplicate rejection returns HTTP 400, while schema validation errors return HTTP 422. |
| `GET` | `/api/mission/events?limit=100&event_type=...` | Mission event records; `event_type` is optional. |
| `GET` | `/api/mission/telemetry/history?limit=300&since_epoch=...` | Persisted telemetry history; `since_epoch` is an optional Unix epoch filter. |
| `POST` | `/api/mission/session/reset` | Clear session telemetry, events, and commands; gate state resets to `UNKNOWN`. |

#### Mission command request and lifecycle

`POST /api/mission/commands` accepts a JSON object with one supported `command` (or the compatibility field `command_type`), and optional `command_id` and object-valued `params`. Supported names are `GET_STATUS`, `SET_ACTIVE`, `SET_STANDBY`, `OPEN_GATE`, and `CLOSE_GATE`.

On dispatch, HTTP `200` returns `{ "command": <tracked command>, "gateway_response": <gateway acknowledgement> }`. A gateway/device rejection is represented in `gateway_response.accepted` and its `reason`; duplicate IDs, missing both command fields, or backend safety rejection returns HTTP `400` with FastAPI's `detail`. FastAPI schema validation failures (for example, an unsupported enum value or invalid field type) return HTTP `422`. `GET /api/mission/commands` returns tracked records with lifecycle statuses `CREATED`, `SENT`, `ACKNOWLEDGED`, `COMPLETED`, `FAILED`, `REJECTED`, `TIMED_OUT`, or `UNKNOWN`.

An accepted acknowledgement moves a command to `ACKNOWLEDGED`; it does not establish physical completion. `OPEN_GATE` and `CLOSE_GATE` complete only after fresh telemetry or a status query confirms the matching endpoint limit. The backend broadcasts a `command_update` after command submission; later lifecycle changes are available through the command list polling endpoint. Movement commands are not retried automatically, and unresolved movement blocks another movement command until reconciliation.

### Dashboard WebSocket: `ws://127.0.0.1:8000/ws/telemetry`

On connect, the service sends `{ "type": "state_snapshot", "data": <mission state> }`. It then broadcasts:

- `state_snapshot`: `data` contains mission state. Includes `simulation_mode`.
- `telemetry`: `telemetry` contains the validated telemetry record plus `received_at`; `state` contains the corresponding mission state and `simulation_mode`.
- `command_update`: `command` contains the updated command record.

The backend also answers a text `ping` with text `pong`. It does not currently broadcast a message with type `event`; event records are retrieved through the REST history endpoint. A telemetry message includes the state snapshot used for that ingestion, including `last_telemetry_timestamp_ms`; this field is still device uptime, while `received_at` remains host receipt time.

### Telemetry and timestamp semantics

| Field | Meaning |
| --- | --- |
| `type` | Message discriminator; telemetry records use `telemetry`. |
| `timestamp_ms` | ESP32 millisecond counter since boot; not wall-clock time. |
| `mode` | ESP32 operating mode: `ACTIVE` or `STANDBY`. |
| `gate_state` | `UNKNOWN`, `CLOSED`, `OPEN`, `OPENING`, `CLOSING`, or `FAULT`. |
| `closed_limit`, `open_limit` | Current boolean limit-switch states; inactive switches do not establish a gate endpoint. |
| `bmp_temperature_c`, `pressure_hpa` | BMP280 temperature and pressure. May be `null` if unavailable. |
| `dht_temperature_c`, `humidity_pct` | DHT11 temperature and humidity. May be `null` if unavailable. |
| `bmp280_ok`, `dht11_ok` | Independent boolean sensor health values. A failed sensor does not make its measurement valid. |
| `fault` | Latched device fault string, or `null` when no fault is reported. |
| `received_at` | Added by the MacBook backend at receipt; UTC ISO 8601 timestamp. |

`received_at`, mission-state timestamps, and event timestamps are created by the MacBook backend in UTC and serialized as ISO 8601 timestamps. Convert them for local display only. Simulator snapshots and telemetry state carry `simulation_mode: true`; this flag identifies simulated data and is not a hardware-health indicator.

The ESP32 protocol has no boot/session identifier. `timestamp_ms` resets after a reboot, so consumers must treat it as a per-boot counter and use host receipt ordering separately. The current backend uses its existing timestamp-regression/connection-state heuristic to recognize resets; a sufficiently delayed old packet cannot always be distinguished from a reboot without a protocol-level boot identifier.

The telemetry history endpoint returns stored rows. Rows do not include an individual data-source/provenance field; the current `simulation_mode` identifies only the active backend source, not the source of each historical row. The database is retained across backend restarts, so history can include records produced in an earlier simulator or network session. The dashboard's live sensor cards hide simulator measurements and mark them `SIM`; the history table can still show stored values and does not tag each row by source. Avoid reusing a database across simulator and live sessions when per-row provenance matters.

Gateway/device disconnection is reflected as connection states (`STALE`, `OFFLINE`, or `NOT_CONNECTED`) in mission state; gate state returns to `UNKNOWN` when hardware state cannot be verified. Sensor health can be `null` when unknown, `false` when failed, or `true` when healthy. The Mission Control network runner does not switch to simulator mode when the configured gateway is unavailable.

### Hardware-free simulator startup

From the repository root, create the backend virtual environment and install `backend/requirements.txt`, then run:

```bash
GATEWAY_MODE=simulator PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Runtime dependencies are listed in `backend/requirements.txt` (`fastapi`, `uvicorn[standard]`, `pyserial`, and `websockets`). To run the test suite, install `backend/requirements-dev.txt`, which includes the runtime dependencies and `pytest`. Dashboard WebSockets use FastAPI/Starlette's native WebSocket support; no Socket.IO protocol is implemented. `GATEWAY_MODE` accepts `simulator` (default), `network`, or `real`; network mode uses `GATEWAY_HTTP_URL` (default `http://127.0.0.1:8001`) and optional `GATEWAY_WS_URL` (derived from the HTTP URL if omitted). `MISSION_DB_PATH` selects the SQLite file (default `data/mission_control.db`). The root and backend `.env.example` files preserve these example settings; keep real credentials and local overrides in ignored `.env` files.

Open `http://127.0.0.1:8000/dashboard`. The simulator advances telemetry and ESP32 uptime once per second. Its sensor readings are fixed demonstration values; the dashboard's live sensor cards hide them and mark them `SIM`. The simulator starts with gate state `UNKNOWN`, supports deterministic in-memory command/movement scenarios, and never contacts the Pi or ESP32. It does not expose HTTP controls for injecting sensor failures or disconnecting simulated components; those scenarios are currently available only through Python tests/direct simulator use.

The current HTTP and WebSocket contracts are lander-specific. Proposed principles for future rover/drone integrations are documented in [docs/architecture.md](architecture.md); they do not add endpoints, fields, or implemented device support to this contract.
