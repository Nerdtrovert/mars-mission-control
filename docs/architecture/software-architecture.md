# Software Architecture

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            SOFTWARE COMPONENT ARCHITECTURE                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    BACKEND (Development Machine)                    │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           run.py / FastAPI App                              │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │   │
│  │  │  Lifespan    │  │   Routers    │  │   State      │  │   Services     │  │   │
│  │  │  Manager     │  │  (api/routes)│  │  Managers    │  │                │  │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  │   │
│  │         │                 │                 │                 │            │   │
│  │         ▼                 ▼                 ▼                 ▼            │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    COMMUNICATION LAYER                              │   │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │   │
│  │  │  │NetworkGateway│  │  RoverRunner │  │  DroneRunner │              │   │   │
│  │  │  │   Runner     │  │              │  │              │              │   │   │
│  │  │  │              │  │  ┌────────┐  │  │  ┌────────┐  │              │   │   │
│  │  │  │  ┌────────┐  │  │  │Simulator│  │  │  │Simulator│  │              │   │   │
│  │  │  │  │Simulator│  │  │  │Runner  │  │  │  │Runner  │  │              │   │   │
│  │  │  │  │Runner  │  │  │  └────────┘  │  │  └────────┘  │              │   │   │
│  │  │  │  └────────┘  │  │              │  │              │              │   │   │
│  │  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  │         │                 │                 │                 │            │   │
│  │         ▼                 ▼                 ▼                 ▼            │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                         CORE SERVICES                               │   │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │   │
│  │  │  │Telemetry     │  │MissionState  │  │Command       │              │   │   │
│  │  │  │Service       │  │Manager       │  │Tracker       │              │   │   │
│  │  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │   │   │
│  │  └─────────┼─────────────────┼─────────────────┼──────────────────────┘   │   │
│  │            │                 │                 │                          │   │
│  │            ▼                 ▼                 ▼                          │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                      STORAGE LAYER                                  │   │   │
│  │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │   │
│  │  │  │  SQLite      │  │  In-Memory   │  │  Session     │              │   │   │
│  │  │  │  (Persistent)│  │  (Simulators)│  │  State       │              │   │   │
│  │  │  └──────────────┘  └──────────────┘  └──────────────┘              │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTP 8001 / WS 8001
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              RASPBERRY PI GATEWAY                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           gateway.main (FastAPI)                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │   │
│  │  │  Lifespan    │  │   Routers    │  │   Managers   │  │   Services     │  │   │
│  │  │  Manager     │  │  (routes.py) │  │              │  │                │  │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘  │   │
│  │         │                 │                 │                 │            │   │
│  │         ▼                 ▼                 ▼                 ▼            │   │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                    COMMUNICATION SERVICES                           │   │   │
│  │  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐       │   │   │
│  │  │  │ LanderTCPTrans-│  │ RoverUDPRecei- │  │ DroneUDPRecei- │       │   │   │
│  │  │  │ port           │  │ ver            │  │ ver            │       │   │   │
│  │  │  │                │  │                │  │                │       │   │   │
│  │  │  │ • Connection   │  │ • ASCII Parse  │  │ • JSON Parse   │       │   │   │
│  │  │  │   Management   │  │ • Validation   │  │ • Sequence Val │       │   │   │
│  │  │  │ • JSON Framing │  │ • Staleness    │  │ • Staleness    │       │   │   │
│  │  │  │ • Line Buffer  │  │                │  │                │       │   │   │
│  │  │  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘       │   │   │
│  │  │          │                   │                   │                │   │   │
│  │  │          ▼                   ▼                   ▼                │   │   │
│  │  │  ┌─────────────────────────────────────────────────────────────┐   │   │   │
│  │  │  │                    LanderManager                            │   │   │   │
│  │  │  │  • Command Correlation (request_id)                        │   │   │   │
│  │  │  │  • Staleness (3s STALE, 10s OFFLINE)                       │   │   │   │
│  │  │  │  • mission_display Forwarding (Rover 4Hz, Drone 2Hz)       │   │   │   │
│  │  │  │  • Reconnection Handling                                    │   │   │   │
│  │  │  └─────────────────────────────────────────────────────────────┘   │   │   │
│  │  └─────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
           ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
           │  LANDER      │ │  ROVER       │ │  DRONE       │
           │  (ESP32)     │ │  (Laptop)    │ │  (ESP32)     │
           │              │ │              │ │              │
           │ • SensorTask │ │ • Tkinter    │ │ • Sensor     │
           │ • LCDTask    │ │   GUI        │ │   Task       │
           │ • WiFiTask   │ │ • HC-12 COM  │ │ • UDP Sender │
           │ • Command    │ │ • UDP Sender │ │              │
           └──────────────┘ └──────────────┘ └──────────────┘
```

---

## Backend Module Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, lifespan
│   ├── config.py               # Environment configuration
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py           # All HTTP endpoints + WebSocket
│   ├── communication/
│   │   ├── __init__.py
│   │   ├── network_runner.py   # NetworkGatewayRunner (Pi Gateway WS + HTTP)
│   │   ├── rover_runner.py     # RoverRunner (polls Pi /api/rover/status)
│   │   ├── drone_runner.py     # DroneRunner (polls Pi /api/drone/status)
│   │   ├── simulator_runner.py # SimulatorRunner (GatewaySimulator, RoverSimulator)
│   │   └── base_runner.py      # BaseRunner abstract class
│   ├── services/
│   │   ├── __init__.py
│   │   ├── telemetry_service.py    # Storage, retention, broadcast
│   │   ├── mission_state.py        # Mission state aggregation
│   │   ├── command_tracker.py      # Command history, deduplication
│   │   └── websocket_manager.py    # Dashboard WS connections
│   ├── storage/
│   │   ├── __init__.py
│   │   └── sqlite_storage.py       # SQLite schema + 5-min retention
│   └── models/
│       ├── __init__.py
│       ├── telemetry.py            # Telemetry data classes
│       ├── commands.py             # Command models
│       └── state.py                # Mission state models
└── tests/
    ├── contract/            # Protocol contract tests
    ├── parsers/             # UDP/TCP parser tests
    ├── simulators/          # Simulator behavior tests
    ├── lifecycle/           # Runner lifecycle tests
    ├── gateway/             # Gateway integration tests
    ├── storage/             # SQLite tests
    └── dashboard/           # Frontend contract tests
```

---

## Gateway Module Structure

```
gateway/
├── main.py                   # FastAPI app, lifespan, dependency injection
├── config.py                 # Configuration (ports, timeouts, IPs)
├── routes.py                 # HTTP routes + WebSocket endpoint
├── lander_manager.py         # LanderTCPTransport + LanderManager
├── tcp_transport.py          # TCP framing, connection management
├── rover_udp.py              # RoverUDPReceiver (ASCII parser + validation)
├── drone_udp.py              # DroneUDPReceiver (JSON + sequence validation)
├── ws_manager.py             # WebSocket connection manager + broadcast
└── tests/
    ├── test_*.py
```

---

## Key Design Patterns

### 1. Runner Pattern (Backend)

All communication adapters implement `BaseRunner`:

```python
class BaseRunner(ABC):
    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
    @abstractmethod
    async def get_status(self) -> DeviceStatus: ...
```

**Runner Selection by Mode:**

| Runner | network mode | sim mode |
|--------|--------------|----------|
| Gateway | `NetworkGatewayRunner` | `GatewaySimulatorRunner` |
| Rover | `RoverRunner` (polls Pi) | `RoverSimulatorRunner` |
| Drone | `DroneRunner` (polls Pi) | `DroneSimulatorRunner` |

Mode resolution in `api/routes.py:startup`:
```python
GATEWAY_MODE = os.getenv("GATEWAY_MODE", "simulator")  # network | simulator
ROVER_MODE   = os.getenv("ROVER_MODE", "simulator")
DRONE_MODE   = os.getenv("DRONE_MODE", "simulator")
```

### 2. Transport → Manager Separation (Gateway)

- **Transport**: Raw I/O, framing, connection lifecycle
- **Manager**: Protocol logic, validation, state, correlation

```python
# tcp_transport.py
class LanderTCPTransport:
    async def connect() -> None
    async def send(line: str) -> None
    async def receive() -> str
    def is_connected() -> bool

# lander_manager.py
class LanderManager:
    def __init__(self, transport: LanderTCPTransport):
        self.transport = transport
    async def send_command(cmd: str) -> CommandResponse
    async def forward_mission_display(device: str, data: dict) -> None
    def get_status() -> LanderStatus
```

### 3. Receiver Pattern (Gateway UDP)

Both UDP receivers share structure:

```python
class BaseUDPReceiver:
    def __init__(self, host: str, port: int, staleness_threshold: float):
        self._last_packet_time: float = 0
        self._last_valid_data: Optional[ParsedData] = None
    
    def parse_packet(self, data: bytes) -> ParsedData:  # abstract
    
    def get_status(self) -> DeviceStatus:
        # Common staleness logic
        age = time.time() - self._last_packet_time
        if age > self.staleness_threshold:
            return DeviceStatus.OFFLINE
        return DeviceStatus.ONLINE
```

### 4. Telemetry Service (Backend)

Centralized storage + broadcast:

```python
class TelemetryService:
    def __init__(self, storage: SQLiteStorage, ws_manager: WebSocketManager):
        self.storage = storage
        self.ws_manager = ws_manager
    
    async def ingest(self, source: str, data: dict) -> None:
        # 1. Validate + normalize
        # 2. Store in SQLite (5-min sliding window)
        # 3. Broadcast to WebSocket clients
        # 4. Update MissionStateManager
```

### 5. Mission State Manager

Aggregates latest state from all sources:

```python
class MissionStateManager:
    def __init__(self):
        self._lander: Optional[LanderState] = None
        self._rover: Optional[RoverState] = None
        self._drone: Optional[DroneState] = None
    
    def update_lander(self, data: dict) -> None
    def update_rover(self, data: dict) -> None
    def update_drone(self, data: dict) -> None
    
    def get_snapshot() -> MissionStateSnapshot:
        # Returns combined state for /api/mission/state
```

---

## Data Models

### Backend Models (`backend/app/models/`)

```python
# telemetry.py
@dataclass
class LanderTelemetry:
    timestamp_ms: int
    mode: str                    # ACTIVE | STANDBY
    bmp_temperature_c: float
    pressure_hpa: float
    dht_temperature_c: float
    humidity_pct: float
    bmp280_ok: bool
    dht11_ok: bool

@dataclass
class RoverTelemetry:
    distance_cm: float
    pitch_deg: float
    roll_deg: float
    command: str                 # F | B | L | R | S
    mode: str                    # M | A

@dataclass
class DroneTelemetry:
    sequence: int
    timestamp_ms: int
    flight_status: str
    orientation: Orientation
    environment: Environment
    gps: GPS
    battery: Battery

# state.py
@dataclass
class MissionStateSnapshot:
    lander: Optional[LanderState]
    rover: Optional[RoverState]
    drone: Optional[DroneState]
    timestamp: datetime
    simulation_mode: bool
```

### Gateway Models (internal)

```python
# rover_udp.py
@dataclass
class RoverPacket:
    distance_cm: float
    pitch_deg: float
    roll_deg: float
    command: str
    mode: str

# drone_udp.py
@dataclass
class DronePacket:
    device_id: str
    sequence: int
    timestamp_ms: int
    flight_status: str
    orientation: dict
    environment: dict
    gps: dict
    battery: dict

# lander_manager.py
@dataclass
class LanderStatus:
    mode: str
    sensors_polling: bool
    bmp280_ok: bool
    dht11_ok: bool
    bmp280_state: str
    dht11_state: str
    firmware_version: str
    connection_state: ConnectionState  # CONNECTED | STALE | OFFLINE
    last_telemetry: Optional[LanderTelemetry]
```

---

## Concurrency Model

### Backend (asyncio)

- **FastAPI**: ASGI, async request handling
- **Runners**: Each runs as independent `asyncio.Task`
- **Polling intervals**:
  - Rover: 0.2s (high frequency for responsive control)
  - Drone: 0.5s
  - Gateway health: 1.0s
  - WebSocket broadcast: event-driven
- **Storage**: SQLite with WAL mode, single writer, concurrent readers
- **WebSocket Manager**: Broadcasts to all connected clients per message

### Gateway (asyncio)

- **Lander TCP**: One connection at a time; new connection replaces old
- **Rover UDP**: Single socket, `recvfrom` in async loop
- **Drone UDP**: Single socket, `recvfrom` in async loop
- **HTTP/WebSocket**: FastAPI handles via uvicorn workers
- **Mission Display Forwarding**: Rate-limited tasks per device

### Lander ESP32 (FreeRTOS)

- **Tasks** (priority order):
  1. `sensorTask` (core 0, prio 2): BMP280 + DHT11 polling
  2. `lcdTask` (core 1, prio 1): LCD page rotation + mission_display
  3. `wifiTask` (core 0, prio 3): TCP connection + JSON I/O
  4. `ledTask` (core 1, prio 0): Status LEDs
- **Communication**: FreeRTOS queues between tasks
- **Watchdog**: ESP32 hardware WDT + software timeouts

---

## Configuration Flow

```
Environment Variables (run.py / run_backend.sh)
         │
         ▼
backend/app/config.py  ──►  Settings object (Pydantic BaseSettings)
         │
         ├──────────────────┬──────────────────┬──────────────────┐
         ▼                  ▼                  ▼                  ▼
   GATEWAY_MODE        ROVER_MODE         DRONE_MODE       DATABASE_URL
   (network|sim)       (network|sim)      (network|sim)    (sqlite path)
         │                  │                  │                  │
         ▼                  ▼                  ▼                  ▼
api/routes.py          api/routes.py      api/routes.py     storage/
startup()              startup()          startup()         sqlite_storage.py
         │                  │                  │                  │
         ▼                  ▼                  ▼                  ▼
   Runner Factory       Runner Factory     Runner Factory    SQLiteStorage
   (selects runner)     (selects runner)   (selects runner)  (connects)
```

---

## Startup / Shutdown Sequences

### Network Mode Startup
```
1. run.py → FastAPI lifespan startup
   │
   ├─► TelemetryService.init() → SQLiteStorage.connect()
   ├─► WebSocketManager.init()
   ├─► CommandTracker.init()
   ├─► MissionStateManager.init()
   │
   ├─► NetworkGatewayRunner.start()
   │     └─► WS connect to Pi Gateway + health poll loop
   │
   ├─► RoverRunner.start()
   │     └─► HTTP poll loop (0.2s) to Pi /api/rover/status
   │
   └─► DroneRunner.start()
         └─► HTTP poll loop (0.5s) to Pi /api/drone/status
```

### Sim Mode Startup
```
1. run.py → FastAPI lifespan startup
   │
   ├─► TelemetryService.init() → SQLiteStorage.connect()
   ├─► WebSocketManager.init()
   ├─► CommandTracker.init()
   ├─► MissionStateManager.init()
   │
   ├─► GatewaySimulatorRunner.start()
   │     └─► In-memory lander simulator (generates telemetry)
   │
   ├─► RoverSimulatorRunner.start()
   │     └─► In-memory rover simulator
   │
   └─► DroneSimulatorRunner.start()
         └─► In-memory drone simulator
```

### Shutdown (both modes)
```
1. FastAPI lifespan shutdown
   │
   ├─► All runners: runner.stop() (parallel)
   │     ├─► NetworkGatewayRunner: close WS, cancel polls
   │     ├─► RoverRunner/DroneRunner: cancel polls
   │     └─► SimulatorRunners: cancel generation tasks
   │
   ├─► WebSocketManager: close all client connections
   ├─► TelemetryService: flush pending writes
   └─► SQLiteStorage: close connection
```

---

## Error Handling Strategy

| Layer | Approach |
|-------|----------|
| **Transport** | Retry with backoff, log, emit connection state change |
| **Protocol** | Validate strictly, reject invalid packets, don't crash |
| **Runner** | Catch exceptions, log, emit `DeviceStatus.OFFLINE`, continue polling |
| **Telemetry Service** | Never drop valid data; queue overflow → backpressure |
| **WebSocket** | Client disconnect → clean removal; broadcast errors → log only |
| **SQLite** | WAL mode, transactions, retry on `SQLITE_BUSY` |
| **FastAPI** | Global exception handler → structured error response |

---

## Testing Architecture

```
backend/tests/
├── conftest.py                 # Fixtures: runners, storage, ws
├── contract/
│   ├── test_tcp_protocol.py    # Lander JSON contract
│   ├── test_rover_udp.py       # ASCII packet contract
│   └── test_drone_udp.py       # JSON + sequence contract
├── parsers/
│   ├── test_rover_parser.py    # RoverUDPReceiver parsing
│   └── test_drone_parser.py    # DroneUDPReceiver parsing
├── simulators/
│   ├── test_gateway_sim.py     # GatewaySimulator behavior
│   ├── test_rover_sim.py       # RoverSimulator behavior
│   └── test_drone_sim.py       # DroneSimulator behavior
├── lifecycle/
│   ├── test_runner_start_stop.py
│   └── test_mode_switching.py
├── gateway/
│   ├── test_lander_manager.py
│   ├── test_rover_receiver.py
│   └── test_drone_receiver.py
├── storage/
│   └── test_sqlite_storage.py
└── dashboard/
    └── test_dashboard_api.py
```

---

## Related Documents

- [System Architecture](system-architecture.md) — Component overview
- [Network Architecture](network-architecture.md) — Network topology
- [Data Flow](data-flow.md) — Telemetry flow diagrams
- [Communication Protocols](protocols/communication-overview.md) — Protocol summary
- [TCP Protocol](protocols/tcp-protocol.md) — Lander protocol details