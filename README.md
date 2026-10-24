# Mars Mission Control

Local-first mission control for the Mars lander exhibition. Rover and drone integration are future work; neither is currently implemented.

See [AGENTS.md](AGENTS.md) for the mandatory engineering constitution and architectural rules.
See [docs/DECISIONS.md](docs/DECISIONS.md) for Architectural Decision Records (ADRs).

---

## System Architecture

```
 +------------------+   USB Serial   +-----------------------+   Private Local Wi-Fi   +-----------------------+   HDMI   +--------------------+
 |   ESP32 Lander   | <============> | Raspberry Pi 4 Gateway| <=====================> |    MacBook Backend    | <======> |   Exhibition TV    |
 | (Frozen Baseline)|  (115200 8N1)  | (Serial + HTTP/WS)    |     (HTTP / WS JSON)    | & Browser Dashboard   |  Video   |     Dashboard      |
 +------------------+                +-----------------------+                         +-----------------------+          +--------------------+
```

- **ESP32 Lander Controller**: Microcontroller running frozen firmware baseline `v1.3.1-esp32-baseline` managing servo PWM, limit switches, and sensors.
- **Raspberry Pi 4 Gateway**: Dedicated edge host managing USB serial connection (`/dev/ttyACM0` or `/dev/ttyUSB0`) and hosting HTTP/WebSocket APIs.
- **MacBook Mission Control**: Central host running the FastAPI mission state manager, SQLite persistence, and dashboard web server.
- **Exhibition TV**: Large-screen HDMI video sink displaying real-time mission status.

---

## 1. Raspberry Pi 4 Hardware Gateway Setup

### Prerequisites on Raspberry Pi OS (Debian 13 Trixie / Python 3.13)
Ensure user belongs to `dialout` group to access the USB serial port without root:
```bash
sudo usermod -a -G dialout $USER
```
*(Log out and log back in for group changes to take effect).*

### Installation & Virtual Environment
From the repository root on the Raspberry Pi:
```bash
# 1. Create and activate a dedicated virtual environment
python3 -m venv gateway/.venv
source gateway/.venv/bin/activate

# 2. Install gateway dependencies
pip install --upgrade pip
pip install -r gateway/requirements.txt
```

### Configuration & Starting the Gateway Daemon
The ESP32 serial device is commonly `/dev/ttyACM0` or `/dev/ttyUSB0`. Confirm the actual node after connecting the board:
```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

Set the serial port explicitly when starting the gateway. It listens on the private network so the MacBook can reach it:
```bash
GATEWAY_SERIAL_PORT=/dev/ttyACM0 gateway/.venv/bin/uvicorn gateway.main:app --host 0.0.0.0 --port 8001
```

The gateway reads `GATEWAY_SERIAL_PORT` (or legacy `SERIAL_PORT`) and `GATEWAY_BAUD_RATE` (or legacy `BAUD_RATE`), plus its timeout settings. To use a local env file instead, copy `gateway/.env.example` to `gateway/.env` only when there is no root `.env`; a root `.env` is read first when starting from the repository root. Existing shell variables take precedence over values in env files.

To verify the gateway is responding on the Pi:
```bash
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8001/api/lander/status
```
`/health` reports gateway process/link health; check `/api/lander/status` for independent ESP32 state. A reachable gateway does not mean the lander is online. For `PermissionError`, check `id -nG`, the device node permissions, and the `dialout` membership. For a missing device node, reconnect the board and check `dmesg`; do not start a second gateway process against the same serial port.

---

## 2. MacBook Mission Control Setup

### Installation & Virtual Environment
From the repository root on the MacBook:
```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

### Option A: Real Network Mode (Connecting to Raspberry Pi)
Replace `<PI_IP_ADDRESS>` with the Pi's address on the private network. Network mode does not fall back to simulator mode if the Pi is unavailable.
```bash
GATEWAY_MODE=network \
ROVER_MODE=network \
GATEWAY_HTTP_URL=http://<PI_IP_ADDRESS>:8001 \
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```
*(Note: `GATEWAY_WS_URL` is automatically derived as `ws://<PI_IP_ADDRESS>:8001/ws/telemetry`).*

### Option B: Hardware-Free Simulator Mode (Local Testing)
Runs with deterministic in-memory simulator without physical hardware or Raspberry Pi:
```bash
GATEWAY_MODE=simulator ROVER_MODE=simulator PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend settings are `GATEWAY_MODE`, `GATEWAY_HTTP_URL`, optional `GATEWAY_WS_URL`, and `MISSION_DB_PATH`. Use `backend/.env.example` for MacBook-only settings; the root `.env.example` is a combined reference for both component configurations. The backend loads the first applicable `.env` (root working-directory `.env` before `backend/.env`) without overriding existing shell environment variables. Keep local values in ignored `.env` files; examples contain no credentials.

### Rover Mode (independent of the lander gateway mode)

The backend setting `ROVER_MODE` is independent of `GATEWAY_MODE`. It defaults to `simulator`, which runs repeatable rover telemetry locally without a Pi or hardware. To use the Pi UDP receiver instead, set `ROVER_MODE=network` and point `GATEWAY_HTTP_URL` at the Pi. The Pi listens on `ROVER_UDP_HOST` (default `0.0.0.0`) and `ROVER_UDP_PORT` (default `5005`); `ROVER_OFFLINE_TIMEOUT_S` defaults to `2.0`.

On the Pi, start the existing gateway command as usual; its separate UDP service starts with it:
```bash
ROVER_UDP_HOST=0.0.0.0 ROVER_UDP_PORT=5005 gateway/.venv/bin/uvicorn gateway.main:app --host 0.0.0.0 --port 8001
```
The rover team's Tkinter GUI must broadcast a UDP datagram about five times per second to the Pi, for example `DIST:145,PITCH:2.5,ROLL:-1.0,CMD:F,MODE:M,VOLT:11.8`. A hardware-free packet check from another machine on the LAN is:
```bash
python3 -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.sendto(b"DIST:145,PITCH:2.5,ROLL:-1.0,CMD:F,MODE:M,VOLT:11.8", ("<PI_IP_ADDRESS>", 5005))'
curl http://<PI_IP_ADDRESS>:8001/api/rover/status
```
Only valid packets update rover state. The API marks telemetry `OFFLINE` after the configured silence timeout. The dashboard receives rover updates through its existing backend WebSocket. Battery percentage remains null until a defensible mapping for the installed 3S LiPo is established.

---

## 3. Exhibition Dashboard Display

Open a web browser on the MacBook driving the HDMI display:
```
http://localhost:8000/dashboard
```
- Real-time telemetry, limit switch status indicators, and latched fault annunciators.
- Physical safety-gated gate controls (`OPEN_GATE`, `CLOSE_GATE`).
- Live WebSocket stream with polling fallback and historical event timeline.

---

## 4. Running Automated Tests

Run the complete test suite (including localhost-only integration tests; no Pi or ESP32 is required):
```bash
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests
```

See [docs/api-contract.md](docs/api-contract.md) for the implemented REST and WebSocket interfaces, [docs/architecture.md](docs/architecture.md) for current component boundaries and proposed future-device principles, and [docs/serial-protocol.md](docs/serial-protocol.md) for the frozen ESP32 link.
