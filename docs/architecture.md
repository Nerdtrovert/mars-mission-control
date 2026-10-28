# Mars Mission Control architecture

## Components and ownership

```text
Lander ESP32 --private Wi-Fi, TCP/JSON (5006)--> Raspberry Pi gateway --HTTP/WebSocket (8001)--> Mac backend
                                                   ^  ^                                           | SQLite + dashboard
                                    UDP 5005       |  |  UDP 5007                                 v
Rover ESP32 --HC-12 9600--> Windows GUI ----------+  |                                       Browser / exhibition TV
Drone ESP32 --local-network UDP 5007 ----------------+
```

- **Lander ESP32** owns BMP280, DHT11, 20x4 LCD, status LEDs, and operating mode.
  It initiates a persistent newline-delimited JSON TCP connection to the Pi on
  the private local Wi-Fi network. USB serial remains for programming/debugging
  only. Status query and ACTIVE/STANDBY commands use the Wi-Fi stream. The LCD
  rotates through 5 non-blocking pages: Lander status (2.5s), Lander sensors (2.5s),
  Rover (5s), Drone (5s), and Mars fun fact (5s).
- **Raspberry Pi 4** owns the lander TCP listener (port 5006), an independent UDP
  receiver for rover GUI telemetry (port 5005), and a drone UDP receiver (port 5007).
  The gateway forwards live rover and drone display messages to the connected lander
  over TCP. All receivers are managed within the gateway FastAPI lifespan.
  Gateway process health is separate from device connectivity.
- **MacBook backend** owns mission state, SQLite persistence, command auditing,
  API, and dashboard WebSocket/polling. In network mode it obtains lander and
  rover telemetry from the Pi; it never opens device serial ports.
- **Dashboard** shows separate lander, rover, and drone status. A reported rover
  command does not prove physical movement. Drone telemetry is display-only;
  no commands are dispatched to the drone.

## Lander path

The ESP32 connects as a TCP client to LANDER_TCP_HOST:LANDER_TCP_PORT (default
Pi bind address 0.0.0.0:5006) and sends the existing newline-delimited JSON
telemetry at about 1 Hz in ACTIVE mode. The gateway validates each frame,
updates device status only for valid messages, and broadcasts telemetry through
its existing /ws/telemetry endpoint. After GATEWAY_OFFLINE_TIMEOUT_S without a
valid frame, the device is OFFLINE and cached sensor values are cleared. The
Mac NetworkGatewayRunner processes the same message contract as simulator
mode, persists it, and broadcasts dashboard updates. Sensor failures remain
null with false health flags.

Configure the lander locally by copying
Lander/lander/lander_config.example.h to lander_config.h and entering the
private Wi-Fi SSID/password and Pi address. The real configuration header is
ignored by git. The ESP32 and Pi must join the same private LAN. The project
does not invent Wi-Fi credentials or a static IP plan, and it does not configure
the Pi's access point. Removing the lander-to-Pi data cable does not power the
ESP32; the controller still needs a suitable board power source.

The simulator emits the same sensor contract, deterministic bounded readings,
and simulated-source labels without hardware access. GATEWAY_MODE=simulator or
network selects the lander source.

## Rover path

The Windows GUI owns the HC-12 USB-TTL COM port and forwards parsed readings
to the Pi by UDP. A packet has exactly these five fields:

```text
DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
```

The Pi validates required fields, numeric ranges, and command/mode values,
stores only the latest valid packet, adds its receipt timestamp, and reports
ONLINE until ROVER_OFFLINE_TIMEOUT_S elapses without another valid packet.
Invalid packets do not overwrite state. The Pi exposes /api/rover/status and
publishes rover_telemetry updates. ROVER_MODE=simulator or network independently
selects the Mac's deterministic rover simulator or Pi polling adapter. No
battery, speed, or encoder values are part of the rover schema.

## Power and peripheral limits

1. **Central Controller & Supply**:
   - The lander ESP32 DevKit V1 is powered via USB (5V) or regulated 5V to the `VIN` pin.
   - Enabling Wi-Fi introduces transmission current spikes (typically 200–300 mA peak). The upstream power source must maintain voltage stability under load to prevent brownouts.
   - Wi-Fi eliminates the serial data cable between the lander and Raspberry Pi; it does **not** eliminate the lander's power cable. The lander requires its own stable power feed.

2. **Low-Current Environmental Sensors**:
   - **BMP280**: Operates at 3.3V logic and supply; draws < 1 mA. Powered directly from the ESP32 `3V3` regulator pin.
   - **DHT11**: Operates at 3.3V to 5V; draws 1–2.5 mA during polling. Powered safely from the ESP32 `3V3` or `5V` rail.

3. **Status Indicators**:
   - **Green LED (GPIO 25)** and **Red LED (GPIO 26)**: Driven directly from GPIOs through series current-limiting resistors (~5–10 mA each), well within the safe 12 mA per-pin rating of the ESP32.

4. **Display**:
   - **20x4 Character LCD (I2C / PCF8574 backpack)**: Backlight and HD44780 contrast typically require 5V (`VIN` rail), drawing ~20–50 mA total. Backpack I2C lines (`SDA` GPIO 21, `SCL` GPIO 22) must remain 3.3V logic compatible.

5. **Addressable LED Strip (WS2812B)**:
   - Contains 30 NeoPixels with data on GPIO 27.
   - Full-white unthrottled draw (30 × 60 mA = 1.8 A) would exceed onboard regulator limits and typical USB ports.
   - In firmware (`lander.ino`), brightness is explicitly clamped to `60` / 255 (`gStrip.setBrightness(60)`) and runs dynamic HSV space animations, constraining current to ~150–300 mA peak.
   - Power must be drawn from the 5V / `VIN` rail (or a dedicated 5V supply sharing common ground if the USB supply is constrained), **never from an ESP32 GPIO pin**.
   - ESP32 GPIO pins provide logic signals only and must never be used to power active peripherals. Avoid redundant separate power supplies when the host 5V feed and onboard rails safely meet these verified budgets.

## Drone interface status

Drone telemetry is implemented and integrated:

- **Transport**: UDP on port 5007 to the Raspberry Pi gateway (`gateway/drone_udp.py`).
- **Schema**: Authoritative JSON datagram with device_id, sequence, timestamp_ms, flight_status, orientation (roll/pitch/yaw), environment (temperature_c, pressure_hpa, humidity_pct), gps (latitude, longitude, altitude_m), battery (voltage_v, percentage).
- **Validation**: Full field validation with numeric range checking (`gateway/drone_udp.py:parse_drone_datagram`).
- **Staleness**: `DRONE_OFFLINE_TIMEOUT_S` (default 10s) determines ONLINE/OFFLINE state; staleness monitor runs at half the timeout interval.
- **Forwarding**: Compact display state (flight_status, latitude, longitude) forwarded to lander LCD via `mission_display` TCP message (`gateway/lander_manager.py`).
- **Simulator**: Deterministic simulator in `backend/app/communication/drone_runner.py` with phases (STANDBY, TAKEOFF, CRUISING, HOVERING, LANDING).
- **Backend API**: `GET /api/drone/status` and WebSocket `drone_telemetry` messages.
- **Frontend**: Dedicated drone telemetry card in dashboard.
- **No commands**: Drone is telemetry-only; no command dispatch from Mission Control.
