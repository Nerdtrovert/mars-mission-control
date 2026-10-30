# Repository guide for coding agents

Read [AGENTS.md](AGENTS.md) and [docs/DECISIONS.md](docs/DECISIONS.md) before
planning or editing. The current accepted design is recorded in ADR-023 and ADR-024.

## Components

- `Lander/lander/lander.ino`: ESP32 sensor/status firmware; DHT11, BMP280, LCD,
  LEDs, WS2812B. Operational telemetry and commands run over private local Wi-Fi TCP (port 5006);
  USB serial is retained for programming/debug. No lander actuator exists.
- `gateway/`: Raspberry Pi FastAPI app. `LanderManager` receives lander telemetry
  over Wi-Fi TCP (port 5006); `RoverUDPReceiver` independently receives GUI telemetry on UDP 5005.
  Both are started and stopped by `gateway.main`'s app lifespan.
- `backend/app/`: Mac FastAPI API, mission state, SQLite, simulator and Pi
  network adapters. `GATEWAY_MODE` and `ROVER_MODE` are independent.
- `frontend/`: dashboard with separate lander and rover data displays.
- `backend/tests/`: hardware-free contract, parser, simulator, lifecycle,
  gateway, storage, and dashboard tests.

## Rover packet contract

Windows GUI owns the rover COM port and forwards exactly:

```text
DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
```

Do not add speed, encoder, battery voltage, or battery percentage fields. The
UDP listener runs only on the Pi; network-mode Mac backend reads the Pi's
`/api/rover/status`. The drone is not implemented; its transport and telemetry
schema are unresolved.

See [README.md](README.md) for startup commands and docs for API/serial details.


  with a single command:
  ──────
  ### How to Run the Two Modes

  #### 🚀 Mode 1: Hybrid Exhibition Mode (Recommended Right Now)

  • What it does: Connects to the real Raspberry Pi gateway & physical Lander ESP32, while running live simulated Rover &
  Drone data.
  • Why: The physical Lander ESP32's LCD display will show real environmental sensors on Page 1 & 2, and live active Rover &
  Drone simulation pages on Page 3 & 4. Your web dashboard displays live gauges for all three without any empty stats.
    ./run_backend.sh hybrid
    # or
    python run.py hybrid

  #### 🌐 Mode 2: Full Hardware Network Mode

  • What it does: Listens purely for real physical hardware packets across all three subsystems (Lander on TCP 5006, Rover on
  UDP 5005, Drone on UDP 5007).
  • When to use: Once your physical Rover and Drone hardware builds are finished and transmitting live.

    ./run_backend.sh network
    # or
    python run.py network

  #### 💻 Mode 3: Offline Local Simulator Mode (Bonus)

  • What it does: Runs all subsystems in local memory on your MacBook.
  • When to use: Testing the web dashboard at home when you don't have the Raspberry Pi or ESP32 with you.

    ./run_backend.sh sim
    # or
    python run.py sim