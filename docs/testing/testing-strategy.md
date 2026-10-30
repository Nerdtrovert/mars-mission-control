# Testing Strategy & Engineering Discipline

This document details the test architecture, methodologies, and verification disciplines established for Mars Mission Control in adherence to the Engineering Constitution (`AGENTS.md`).

---

## 1. Testing Philosophy & Priorities

In accordance with Section 1 and Section 7 of `AGENTS.md`, all verification follows strict priorities:

1. **Hardware-Free Determinism**: All automated unit and integration tests must execute without physical hardware (no ESP32, no Raspberry Pi, no local Wi-Fi, and no public internet).
2. **Never Fabricate Hardware Claims**: Passing software unit tests verify software contracts, schemas, and state transitions. They must **never** be cited as proof of physical hardware testing.
3. **Deterministic Clocks**: Avoid arbitrary `time.sleep()`. Tests utilize injected timestamps, virtual monotonic clocks, and explicit event triggers.
4. **Strict Isolation**: Sensor errors, dropped sockets, and invalid UDP datagrams must be safely isolated; they must never corrupt unrelated state or crash application workers.

---

## 2. Test Architecture & Directory Layout

The automated test suite is split across two main packages:

```
├── backend/tests/                          # 69 tests: Backend & Core Application
│   ├── test_college_frontend.py           # Consolidated frontend routes & asset existence (6 tests)
│   ├── test_command_model.py              # Command dataclass transitions & immutability (3 tests)
│   ├── test_command_safety_phase_b.py     # Pre-dispatch safety invariants (2 tests)
│   ├── test_connection_state.py           # Independent gateway & device state machines (2 tests)
│   ├── test_dashboard_integration.py      # Telemetry WebSocket broadcasting (2 tests)
│   ├── test_drone_integration.py          # Drone runner, parser & UDP receiver (4 tests)
│   ├── test_firmware_contract.py          # Static analysis of lander.ino pinout & contracts (2 tests)
│   ├── test_gateway_contract.py           # Pydantic schemas for Gateway REST endpoints (2 tests)
│   ├── test_gateway_integration.py        # GatewayClient with simulator backend (2 tests)
│   ├── test_gateway_service.py            # TelemetryService state integration (2 tests)
│   ├── test_gateway_simulator.py          # Deterministic in-memory simulator behavior (3 tests)
│   ├── test_lander_wifi_gateway.py        # Lander TCP framing & connection lifecycle (4 tests)
│   ├── test_persistence_phase_d.py        # SQLite history sliding window & pruning (3 tests)
│   ├── test_real_network_integration.py   # HTTP client timeout handling (2 tests)
│   ├── test_rover_gateway_udp.py          # Rover UDP parsing, validation & staleness (14 tests)
│   ├── test_rover_simulator.py            # Rover terrain math & cycle continuity (5 tests)
│   ├── test_runtime_lifecycle.py          # Startup lifespan & background task termination (1 test)
│   ├── test_telemetry_processor.py        # JSON line validation & sensor range limits (8 tests)
│   └── test_telemetry_service.py          # MissionStateManager listener callbacks (2 tests)
│
└── gateway/tests/                          # 43 tests: Raspberry Pi Edge Gateway Daemon
    ├── test_drone_udp.py                  # Drone UDP protocol, rollover & staleness (16 tests)
    ├── test_gateway_app.py                # Gateway FastAPI routes (/health, /api/lander/status) (3 tests)
    ├── test_lander_manager.py             # TCP client session management & forwarding (8 tests)
    ├── test_mission_display_and_integration.py # Relay to LCD Page 3 & Page 4 (10 tests)
    └── test_tcp_transport.py              # Asyncio TCP framing, partial lines, max buffer (6 tests)
```

---

## 3. Key Testing Paradigms

### A. Asyncio TCP Stream Simulation
In `gateway/tests/test_tcp_transport.py` and `test_lander_manager.py`, the test harness uses real `asyncio` server-client loopback sockets bound to ephemeral localhost ports. This tests actual socket framing, partial message buffering, backpressure, and TCP teardown without physical Wi-Fi.

### B. RFC 1982 Sequence Rollover Verification
In `gateway/tests/test_drone_udp.py`, drone UDP packet sequences are validated against RFC 1982 serial number arithmetic (both 16-bit and 32-bit integer representations). The suite validates:
- In-order datagram delivery.
- Out-of-order and duplicate datagram rejection.
- Clean transition across sequence boundary (`65535 -> 0` and `0xFFFFFFFF -> 0`).

### C. Sensor Range Clamping & Malformed JSON Isolation
In `backend/tests/test_telemetry_processor.py`, sensor limits are rigorously verified:
- Temperatures outside `[-40.0, 85.0] °C` (BMP280) or `[0.0, 50.0] °C` (DHT11) are rejected without corrupting state.
- Pressures outside `[300.0, 1100.0] hPa` are rejected.
- Non-finite numbers (`NaN`, `Infinity`, `-Infinity`) trigger validation errors.
- Malformed strings, partial JSON lines, or non-JSON input return clean rejection `None` instead of raising unhandled exceptions.

### D. Static Firmware Contract Analysis
In `backend/tests/test_firmware_contract.py`, the actual C++ firmware source (`lander/lander.ino`) is read as text and validated statically to ensure:
- Pins matching hardware architecture (`PIN_DHT`, `PIN_I2C_SDA`, `PIN_I2C_SCL`, `PIN_LED_GREEN`, `PIN_LED_RED`).
- 115200 serial debug baud.
- All retired actuator code (servos, ramps, spool motor) remains absent.

---

## 4. Execution Commands

Run the full unified test suite from repository root:

```bash
PYTHONPATH=.:backend:gateway backend/.venv/bin/pytest
```

Run backend tests only:
```bash
PYTHONPATH=.:backend backend/.venv/bin/pytest backend/tests
```

Run gateway tests only:
```bash
PYTHONPATH=.:gateway backend/.venv/bin/pytest gateway/tests
```

Run with verbose output and timing:
```bash
PYTHONPATH=.:backend:gateway backend/.venv/bin/pytest -v --durations=10
```
