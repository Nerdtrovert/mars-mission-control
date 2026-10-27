# Mars Mission Control

Local-first lander and rover telemetry for the Mars exhibition. The MacBook
backend serves the dashboard, mission API, and SQLite history. The Raspberry
Pi gateway receives lander telemetry over private Wi-Fi TCP and rover telemetry
over UDP. Drone telemetry is not implemented because its transport and payload
contract are still TBD.

See [AGENTS.md](AGENTS.md) for engineering constraints,
[docs/DECISIONS.md](docs/DECISIONS.md) for architectural decisions, and
[docs/architecture.md](docs/architecture.md) for component boundaries.

## Raspberry Pi gateway

```bash
python3 -m venv gateway/.venv
gateway/.venv/bin/pip install -r gateway/requirements.txt
LANDER_TCP_HOST=0.0.0.0 LANDER_TCP_PORT=5006 \
  gateway/.venv/bin/uvicorn gateway.main:app --host 0.0.0.0 --port 8001
```

This single process starts the lander TCP listener, rover UDP receiver, HTTP
API, and WebSocket endpoint. The Pi does not open either ESP32's USB serial
port or the Windows rover GUI's COM port. Rover settings are
ROVER_UDP_HOST=0.0.0.0, ROVER_UDP_PORT=5005, and
ROVER_OFFLINE_TIMEOUT_S=2.0. The rover GUI sends
DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M at about 5 Hz. Verify rover status
with:

```bash
curl http://<PI_IP_ADDRESS>:8001/api/rover/status
curl http://<PI_IP_ADDRESS>:8001/api/lander/status
```

The repository has no systemd unit. An installed service should invoke the
single Uvicorn command above so both listeners share one managed lifecycle.

## Lander Wi-Fi setup

Copy Lander/lander/lander_config.example.h to
Lander/lander/lander_config.h. Set the private Wi-Fi SSID/password and the
Pi's LAN address. The real config is ignored by git. Join the ESP32 and Pi to
the same private local Wi-Fi network. The ESP32 opens a TCP connection to the
Pi (default port 5006) and streams the existing newline-delimited JSON telemetry
at about 1 Hz. Status/mode commands share this stream. The existing Pi HTTP and
WebSocket interfaces remain on port 8001 by default. The project does not set
Wi-Fi credentials, prescribe a static IP plan, or configure the Pi access
point. USB serial remains available for ESP32 flashing and local debugging,
but the Pi does not use it operationally.

Wi-Fi removes the lander-to-Pi data cable; it does not supply power to the
ESP32. Avoid unnecessary separate power supplies unless electrical requirements
strictly require one. Low-current sensors (BMP280, DHT11) and 20x4 LCD logic can
run safely from ESP32 dev-board rails. The WS2812B LED strip (30 LEDs) has its
brightness strictly clamped to 60/255 in firmware (~150–300 mA peak) and is
powered from 5V/VIN (never GPIO). Ensure the host USB power supply provides
1A–1.5A to prevent brownouts during Wi-Fi transmission bursts.

## MacBook backend and dashboard

Install backend dependencies:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

Hardware-free operation:

```bash
GATEWAY_MODE=simulator ROVER_MODE=simulator PYTHONPATH=backend \
  backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Network operation through the Pi:

```bash
GATEWAY_MODE=network ROVER_MODE=network \
GATEWAY_HTTP_URL=http://<PI_IP_ADDRESS>:8001 \
PYTHONPATH=backend backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/dashboard. Lander and rover simulator/network
modes are configured independently. Network mode gets both device streams
through the Pi; the Mac never opens a device serial port or listens on UDP 5005.

## Firmware and verification

The source is [Lander/lander/lander.ino](Lander/lander/lander.ino), targeting
ESP32 DevKit V1 / ESP32-WROOM-32 with Arduino. Required libraries are
ArduinoJson 7, Adafruit BMP280, Adafruit Unified Sensor, Adafruit DHT sensor,
Adafruit NeoPixel, and LiquidCrystal_I2C. No PlatformIO or Arduino CLI build
configuration is committed. Physical hardware verification has not been
performed.

Run backend tests with:

```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests
```

The drone's identity, transport, packet format, telemetry fields/units, update
rate, and connection timeout need agreement before implementation.
