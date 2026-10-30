# Data Flow Diagrams

## Complete Telemetry Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                            COMPLETE TELEMETRY DATA FLOW                              │
└──────────────────────────────────────────────────────────────────────────────────────┘

  LANDER                          ROVER                          DRONE
  ──────                          ──────                          ──────
     │                              │                              │
     │  BMP280 + DHT11              │  HC-SR04 + MPU6050           │  GPS + IMU + Env + Battery
     │  ~1 Hz (ACTIVE)              │  ~50 Hz (sensors)            │  ~2 Hz
     │                              │  HC-12 9600 baud serial      │  Wi-Fi UDP
     ▼                              ▼                              ▼
┌─────────┐                   ┌─────────────┐                 ┌────────────┐
│  ESP32  │                   │ Rover ESP32 │                 │ Drone ESP32│
│ Firmware│                   │             │                 │ Firmware   │
└────┬────┘                   └──────┬──────┘                 └─────┬──────┘
     │                               │                              │
     │ TCP 5006 JSON                 │ HC-12 Serial                 │ UDP 5007 JSON
     │ {"type":"telemetry",...}      │ "DIST:145,PITCH:12.4..."     │ {seq,ts,orient,...}
     ▼                               ▼                              ▼
     │                              ┌─────────────┐                 │
     │                              │  ROVER      │                 │
     │                              │  LAPTOP     │                 │
     │                              │  (Windows)  │                 │
     │                              │  Tkinter GUI│                 │
     │                              │  COM Port   │                 │
     │                              └──────┬──────┘                 │
     │                                     │                        │
     │                                     │ UDP 5005 ASCII         │
     │                                     │ DIST:145,PITCH:12.4... │
     │                                     ▼                        │
     │                              ┌─────────────┐                 │
     │                              │   RASPBERRY │                 │
     │                              │     PI      │◄────────────────┘
     │                              │   GATEWAY   │
     │                              │             │
     │                              │ ┌─────────┐ │
     │                              │ │LanderTCP│ │
     │                              │ │Transport│ │
     │                              │ └────┬────┘ │
     │                              │      │      │
     │                              │ ┌────┴────┐ │
     │                              │ │LanderMgr│ │
     │                              │ └────┬────┘ │
     │                              │      │      │
     │                              │ ┌────┴────┐ │
     │                              │ │RoverUDP │ │
     │                              │ │Receiver │ │
     │                              │ └────┬────┘ │
     │                              │      │      │
     │                              │ ┌────┴────┐ │
     │                              │ │DroneUDP │ │
     │                              │ │Receiver │ │
     │                              │ └────┬────┘ │
     │                              │      │      │
     │                              └──────┼──────┘
     │                                     │
     │         ┌───────────────────────────┼───────────────────────────┐
     │         │                           │                           │
     │         ▼                           ▼                           ▼
     │  ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
     │  │ /api/lander/ │           │ /api/rover/  │           │ /api/drone/  │
     │  │    status    │           │    status    │           │    status    │
     │  └──────┬───────┘           └──────┬───────┘           └──────┬───────┘
     │         │                           │                           │
     │         │              ┌────────────┴────────────┐             │
     │         │              │                         │             │
     │         ▼              ▼                         ▼             ▼
     │  ┌──────────────────────────────────────────────────────────────┐  │
     │  │              Pi Gateway WebSocket /ws/telemetry              │  │
     │  │  {type:"lander_telemetry",...} {type:"rover_telemetry",...} │  │
     │  │  {type:"drone_telemetry",...} {type:"command_ack",...}     │  │
     │  └────────────────────────────┬────────────────────────────────┘  │
     │                               │                                    │
     └───────────────────────────────┼────────────────────────────────────┘
                                     │
                                     │ HTTP 8001 + WS 8001
                                     ▼
                          ┌─────────────────────┐
                          │ DEVELOPMENT MACHINE │
                          │      BACKEND        │
                          │                     │
                          │ ┌─────────────────┐ │
                          │ │NetworkGatewayRun│ │◄── WS + HTTP Poll
                          │ │    (Network)    │ │
                          │ └────────┬────────┘ │
                          │          │          │
                          │ ┌────────┴────────┐ │
                          │ │  RoverRunner    │ │◄── HTTP Poll 0.2s
                          │ │  (Network)      │ │
                          │ └────────┬────────┘ │
                          │          │          │
                          │ ┌────────┴────────┐ │
                          │ │  DroneRunner    │ │◄── HTTP Poll 0.5s
                          │ │  (Network)      │ │
                          │ └────────┬────────┘ │
                          │          │          │
                          │ ┌────────┴────────┐ │
                          │ │ SimulatorRunner │ │◄── In-memory (sim mode)
                          │ └────────┬────────┘ │
                          │          │          │
                          └──────────┼──────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │   TELEMETRY SERVICE │
                          │                     │
                          │ • Normalize         │
                          │ • Validate          │
                          │ • SQLite Store      │
                          │ • WS Broadcast      │
                          │ • MissionState Mgr  │
                          └──────────┬──────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │   SQLITE DATABASE   │
                          │                     │
                          │ lander_telemetry    │
                          │ rover_telemetry     │
                          │ drone_telemetry     │
                          │ commands            │
                          │ events              │
                          │ (5-min retention)   │
                          └─────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                 ┌───────────────┐       ┌───────────────┐
                 │  WebSocket    │       │  HTTP Polling │
                 │  /ws/telemetry│       │  /api/*       │
                 └───────┬───────┘       └───────┬───────┘
                         │                       │
                         ▼                       ▼
                ┌──────────────────┐    ┌──────────────────┐
                │  DASHBOARD JS    │    │  DASHBOARD JS    │
                │  (Primary)       │    │  (Fallback 2s)   │
                └──────────────────┘    └──────────────────┘
```

---

## Lander Telemetry Flow (Detail)

```
ESP32 Firmware                          Pi Gateway                         Backend
─────────────                          ──────────                         ────────
   │                                        │                                 │
   │─ connect TCP 5006 ──────────────────►│                                 │
   │                                        │                                 │
   │◄─── TCP connected ───────────────────│                                 │
   │                                        │                                 │
   ├─ loop ────────────────────────────────►│                                 │
   │  BMP280.read()                         │                                 │
   │  DHT11.read()                          │                                 │
   │                                        │                                 │
   │─ JSON telemetry ─────────────────────►│                                 │
   │  {"type":"telemetry",                  │                                 │
   │   "timestamp_ms":123456,               │                                 │
   │   "mode":"ACTIVE",                     │                                 │
   │   "bmp_temperature_c":24.2,            │                                 │
   │   "pressure_hpa":1013.5,               │                                 │
   │   "dht_temperature_c":24.0,            │                                 │
   │   "humidity_pct":58.0,                 │                                 │
   │   "bmp280_ok":true,                    │                                 │
   │   "dht11_ok":true}                     │                                 │
   │                                        │                                 │
   │              (LanderTCPTransport)      │                                 │
   │              - newline delimited       │                                 │
   │              - buffer up to 4096B      │                                 │
   │                                        │                                 │
   │              (LanderManager)           │                                 │
   │              - validate JSON           │                                 │
   │              - update last_telemetry   │                                 │
   │              - staleness: 3s STALE     │                                 │
   │              - staleness: 10s OFFLINE  │                                 │
   │                                        │                                 │
   │                                        │── HTTP /api/lander/status ──►│ (poll)
   │                                        │                                 │
   │                                        │── WS /ws/telemetry ────────►│ (push)
   │                                        │                                 │
   │                                        │              (NetworkGatewayRunner)
   │                                        │              - WS persistent
   │                                        │              - health poll 1s
   │                                        │                                 │
   │                                        │                                 │── TelemetryService.ingest()
   │                                        │                                 │      - normalize
   │                                        │                                 │      - SQLite INSERT
   │                                        │                                 │      - WS broadcast
   │                                        │                                 │      - MissionStateMgr.update()
   │                                        │                                 │
   │◄───────────────────────────────────────│                                 │
   │  (optional command response)           │                                 │
   │                                        │                                 │
```

---

## Rover Telemetry Flow (Detail)

```
Rover ESP32                              Rover Laptop                      Pi Gateway                    Backend
────────────                              ───────────                      ──────────                    ────────
   │                                        │                                 │                              │
   │─ HC-SR04 trig/echo ──► distance        │                                 │                              │
   │─ MPU6050 I2C ──────► pitch/roll        │                                 │                              │
   │                                        │                                 │                              │
   │─ Serial 9600 ────────────────────────►│                                 │                              │
   │  "DIST:145,PITCH:12.4,ROLL:-3.2,      │                                 │                              │
   │   CMD:F,MODE:M"                        │                                 │                              │
   │                                        │                                 │                              │
   │                    (Tkinter GUI)       │                                 │                              │
   │                    - parse COM port    │                                 │                              │
   │                    - validate 5 fields │                                 │                              │
   │                    - forward UDP 5005  │                                 │                              │
   │                                        │                                 │                              │
   │                                        │── UDP 5005 ──────────────────►│                              │
   │                                        │  "DIST:145,PITCH:12.4,         │                              │
   │                                        │   ROLL:-3.2,CMD:F,MODE:M"     │                              │
   │                                        │                                 │                              │
   │                                        │              (RoverUDPReceiver) │                              │
   │                                        │              - parse ASCII     │                              │
   │                                        │              - validate 5 fields│                             │
   │                                        │              - range checks    │                              │
   │                                        │              - enum checks     │                              │
   │                                        │              - staleness 2s    │                              │
   │                                        │                                 │                              │
   │                                        │── HTTP /api/rover/status ──►│ (poll 0.2s)                   │
   │                                        │                                 │                              │
   │                                        │── WS /ws/telemetry ────────►│ (push)                        │
   │                                        │                                 │                              │
   │                                        │                                 │              (RoverRunner)
   │                                        │                                 │              - HTTP poll 0.2s
   │                                        │                                 │              - normalize source
   │                                        │                                 │                              │
   │                                        │                                 │── TelemetryService.ingest()
   │                                        │                                 │      - normalize
   │                                        │                                 │      - SQLite INSERT
   │                                        │                                 │      - WS broadcast
   │                                        │                                 │      - MissionStateMgr.update()
```

---

## Drone Telemetry Flow (Detail)

```
Drone ESP32                              Pi Gateway                         Backend
──────────                              ──────────                         ────────
   │                                        │                                 │
   │─ GPS.read()                            │                                 │
   │─ IMU.read()                            │                                 │
   │─ Env.read()                            │                                 │
   │─ Battery.read()                        │                                 │
   │                                        │                                 │
   │─ UDP 5007 ──────────────────────────►│                                 │
   │  {"device_id":"esp32-drone",          │                                 │
   │   "sequence":123,                     │                                 │
   │   "timestamp_ms":1234567890,          │                                 │
   │   "flight_status":"CRUISING",         │                                 │
   │   "orientation":{"roll":1.2,          │                                 │
   │     "pitch":-0.5,"yaw":180.0},        │                                 │
   │   "environment":{...},                │                                 │
   │   "gps":{...},                        │                                 │
   │   "battery":{...}}                    │                                 │
   │                                        │                                 │
   │              (DroneUDPReceiver)        │                                 │
   │              - parse JSON             │                                 │
   │              - validate schema        │                                 │
   │              - RFC 1982 sequence      │                                 │
   │              - staleness 10s          │                                 │
   │                                        │                                 │
   │                                        │── HTTP /api/drone/status ──►│ (poll 0.5s)
   │                                        │                                 │
   │                                        │── WS /ws/telemetry ────────►│ (push)
   │                                        │                                 │
   │                                        │                                 │              (DroneRunner)
   │                                        │                                 │              - HTTP poll 0.5s
   │                                        │                                 │              - normalize source
   │                                        │                                 │                              │
   │                                        │                                 │── TelemetryService.ingest()
   │                                        │                                 │      - normalize
   │                                        │                                 │      - SQLite INSERT
   │                                        │                                 │      - WS broadcast
   │                                        │                                 │      - MissionStateMgr.update()
```

---

## Command Flow (Dashboard → Lander)

```
Dashboard                              Backend                            Pi Gateway                         Lander ESP32
──────────                              ────────                            ──────────                         ─────────────
   │                                        │                                 │                                  │
   │─ POST /api/mission/commands ────────►│                                 │                                  │
   │  {"command":"SET_ACTIVE",            │                                 │                                  │
   │   "source":"dashboard"}              │                                 │                                  │
   │                                        │                                 │                                  │
   │                                        │── CommandTracker.record()       │                                  │
   │                                        │                                 │                                  │
   │◄── 202 Accepted ─────────────────────│                                 │                                  │
   │  {"command_id": "cmd_123",           │                                 │                                  │
   │   "status": "pending"}               │                                 │                                  │
   │                                        │                                 │                                  │
   │                                        │              (NetworkGatewayRunner)                            │
   │                                        │              - WS send command                                 │
   │                                        │                                 │                                  │
   │                                        │                                 │── WS /ws/telemetry ─────────►│
   │                                        │                                 │  {type:"command",             │
   │                                        │                                 │   "command":"SET_ACTIVE",   │
   │                                        │                                 │   "request_id": 42}         │
   │                                        │                                 │                                  │
   │                                        │                                 │              (LanderManager)    │
   │                                        │                                 │              - send_command()  │
   │                                        │                                 │              - allocates request_id│
   │                                        │                                 │              - awaits ack      │
   │                                        │                                 │                                  │
   │                                        │                                 │── TCP 5006 ────────────────►│
   │                                        │                                 │  {"command":"SET_ACTIVE",    │
   │                                        │                                 │   "request_id": 42}         │
   │                                        │                                 │                                  │
   │                                        │                                 │                                  │
   │                                        │                                 │◄─────────────────────────────│
   │                                        │                                 │  {"type":"command_ack",      │
   │                                        │                                 │   "command":"SET_ACTIVE",   │
   │                                        │                                 │   "ok":true,                │
   │                                        │                                 │   "accepted":true,          │
   │                                        │                                 │   "message":"...",          │
   │                                        │                                 │   "request_id": 42}         │
   │                                        │                                 │                                  │
   │                                        │                                 │              (LanderManager)    │
   │                                        │                                 │              - matches request_id│
   │                                        │                                 │              - updates state     │
   │                                        │                                 │                                  │
   │                                        │                                 │── WS /ws/telemetry ─────────►│
   │                                        │                                 │  {type:"command_ack",...}    │
   │                                        │                                 │                                  │
   │                                        │              (NetworkGatewayRunner)                            │
   │                                        │              - receives WS                                          │
   │                                        │              - CommandTracker.update_status()                      │
   │                                        │                                 │                                  │
   │                                        │                                 │                                  │
   │                                        │◄── WS command_ack ─────────────│                                  │
   │                                        │                                 │                                  │
   │                                        │                                 │                                  │
```

---

## Remote Display Forwarding (Pi → Lander LCD)

```
Pi Gateway                              Lander ESP32
──────────                              ─────────────
   │                                        │
   │  (Rover telemetry received)            │
   │                                        │
   │── LanderManager.forward_mission_display("rover", data)          │
   │                                        │
   │     Rate Limited:                      │
   │     - Rover: 4 Hz + 2.5s heartbeat     │
   │     - Drone: 2 Hz + 2.5s heartbeat     │
   │                                        │
   │── TCP 5006 ──────────────────────────►│
   │  {"type":"mission_display",            │
   │   "device":"rover",                    │
   │   "connected":true,                    │
   │   "data":{                             │
   │     "distance":145.0,                  │
   │     "pitch":12.4,                      │
   │     "roll":-3.2,                       │
   │     "cmd":"F",                         │
   │     "mode":"M"                         │
   │   }}                                   │
   │                                        │
   │                              (wifiTask)│
   │                              - parses JSON                            │
   │                              - queue to lcdTask                       │
   │                                        │
   │                              (lcdTask)                               │
   │                              - renders Page 3                         │
   │                              - shows: DIST, PITCH, ROLL, CMD, MODE    │
   │                              - heartbeat resets on timeout            │
   │                                        │
   │                              LCD Page 3:                             │
   │                              ┌────────────────────┐                  │
   │                              │ ROVER:  145 cm     │                  │
   │                              │ P: 12.4  R: -3.2   │                  │
   │                              │ CMD: F  MODE: M    │                  │
   │                              │ ████████░░░░░░░░░░ │  signal strength │
   │                              └────────────────────┘                  │
   │                                        │
   │                                        │
   │  (Drone telemetry received)            │
   │                                        │
   │── LanderManager.forward_mission_display("drone", data)          │
   │                                        │
   │── TCP 5006 ──────────────────────────►│
   │  {"type":"mission_display",            │
   │   "device":"drone",                    │
   │   "connected":true,                    │
   │   "data":{                             │
   │     "flight_status":"CRUISING",        │
   │     "latitude":12.9716,                │
   │     "longitude":77.5946                │
   │   }}                                   │
   │                                        │
   │                              (lcdTask)                               │
   │                              - renders Page 4                         │
   │                              - shows: FLIGHT_STATUS, LAT, LON         │
   │                              - heartbeat resets on timeout            │
   │                                        │
   │                              LCD Page 4:                             │
   │                              ┌────────────────────┐                  │
   │                              │ DRONE: CRUISING    │                  │
   │                              │ LAT: 12.9716       │                  │
   │                              │ LON: 77.5946       │                  │
   │                              │ ████████░░░░░░░░░░ │  signal strength │
   │                              └────────────────────┘                  │
```

---

## Storage Flow (SQLite 5-Minute Window)

```
TelemetryService.ingest(source, data)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SQLiteStorage.store()                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  INSERT INTO telemetry (source, timestamp, data_json)              │
│  VALUES (?, ?, ?)                                                   │
│                                                                      │
│  -- Immediate cleanup (async, non-blocking)                         │
│  DELETE FROM telemetry                                              │
│  WHERE timestamp < datetime('now', '-5 minutes')                   │
│                                                                      │
│  -- Also cleanup old commands                                       │
│  DELETE FROM commands                                               │
│  WHERE timestamp < datetime('now', '-5 minutes')                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
         │
         ▼
   ┌─────────────┐
   │   SQLite    │
   │   (WAL)     │
   └─────────────┘

Schema:
──────
CREATE TABLE telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,           -- 'lander' | 'rover' | 'drone'
    timestamp INTEGER NOT NULL,     -- epoch milliseconds
    data_json TEXT NOT NULL,        -- full telemetry JSON
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_telemetry_source_ts ON telemetry(source, timestamp);

CREATE TABLE commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id TEXT UNIQUE NOT NULL,
    command TEXT NOT NULL,          -- 'GET_STATUS' | 'SET_ACTIVE' | 'SET_STANDBY'
    source TEXT NOT NULL,           -- 'dashboard' | 'api'
    status TEXT NOT NULL,           -- 'pending' | 'sent' | 'acked' | 'failed'
    request_id INTEGER,
    timestamp INTEGER NOT NULL,
    response_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,       -- 'mode_change' | 'connection' | 'error'
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## WebSocket Broadcast Flow

```
TelemetryService.ingest()
         │
         ├──────────────────┬──────────────────┐
         ▼                  ▼                  ▼
   ┌──────────┐       ┌──────────┐       ┌──────────┐
   │ Client 1 │       │ Client 2 │       │ Client N │
   │  (WS)    │       │  (WS)    │       │  (WS)    │
   └────┬─────┘       └────┬─────┘       └────┬─────┘
        │                  │                  │
        ▼                  ▼                  ▼
   {"type":"lander_telemetry",     {"type":"rover_telemetry",     {"type":"drone_telemetry",
    "source":"network",            "source":"network",             "source":"simulator",
    "data":{...},                  "data":{...},                   "data":{...},
    "timestamp":1234567890}        "timestamp":1234567890}         "timestamp":1234567890}
        │                  │                  │
        └──────────────────┴──────────────────┘
                           │
                           ▼
                    Dashboard JS
                    - Updates lander card
                    - Updates rover card
                    - Updates drone card
                    - Appends to events log
                    - Updates telemetry history chart
```

---

## Simulation Mode Data Flow

```
BACKEND (sim mode)                          DASHBOARD
───────────────                              ──────────
   │                                             │
   ├─ GatewaySimulatorRunner ──────────────────►│ (via TelemetryService → WS)
   │  - Generates lander telemetry              │
   │  - Simulates mode changes                  │
   │  - Responds to commands                    │
   │                                             │
   ├─ RoverSimulatorRunner ────────────────────►│
   │  - Generates DIST/PITCH/ROLL/CMD/MODE      │
   │  - Simulates movement patterns             │
   │                                             │
   └─ DroneSimulatorRunner ────────────────────►│
      - Generates flight status, GPS, IMU       │
      - Simulates flight path                   │
                                                │
   All runners:                                  │
   - Run as asyncio tasks                        │
   - Generate at configured rates                │
   - Call TelemetryService.ingest()              │
   - No network, no hardware                     │
```

---

## Rate Summary

| Path | Rate | Trigger |
|------|------|---------|
| Lander sensors → ESP32 | ~1 Hz | Timer (ACTIVE mode) |
| ESP32 → Pi TCP | ~1 Hz | Sensor loop |
| Rover sensors → ESP32 | ~50 Hz | Sensor interrupts |
| Rover ESP32 → Laptop | ~50 Hz | Serial 9600 baud |
| Laptop → Pi UDP | ~5 Hz | GUI forwarding |
| Drone sensors → ESP32 | ~10 Hz | Sensor fusion |
| Drone ESP32 → Pi UDP | ~2 Hz | Telemetry timer |
| Pi → Backend HTTP | 0.2s (Rover) / 0.5s (Drone) / 1s (Health) | Polling timer |
| Pi → Backend WS | Event-driven | New telemetry |
| Backend → SQLite | Per ingest | TelemetryService |
| Backend → Dashboard WS | Event-driven | TelemetryService.broadcast |
| Dashboard HTTP fallback | 2s | setInterval |
| LCD forward (Rover) | 4 Hz + 2.5s HB | LanderManager timer |
| LCD forward (Drone) | 2 Hz + 2.5s HB | LanderManager timer |

---

## Related Documents

- [System Architecture](system-architecture.md) — Component overview
- [Network Architecture](network-architecture.md) — Network topology
- [Software Architecture](software-architecture.md) — Code organization
- [Communication Protocols](protocols/communication-overview.md) — Protocol summary