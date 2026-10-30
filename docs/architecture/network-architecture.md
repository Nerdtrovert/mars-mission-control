# Network Architecture

## Network Topology

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         MISSION CONTROL NETWORK TOPOLOGY                     │
└──────────────────────────────────────────────────────────────────────────────┘

                    MISSION-CONTROL Wi-Fi NETWORK (Pi in AP mode set to 192.168.50.1)
                    SSID: "Mission-Control"  |  PSK: "YOUR_WIFI_PASSWORD"
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
       ┌────────────┐  ┌────────────┐  ┌────────────┐
       │   LANDER   │  │    DRONE   │  │  ROVER     │
       │  (ESP32)   │  │  (ESP32)   │  │  (HC-12)   │
       │            │  │            │  │            │
       │ 192.168.50.│  │ 192.168.50.│  │(via Laptop)│
       │    DHCP    │  │    DHCP    │  │            │
       └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
             │               │               │
             │ TCP :5006     │ UDP :5007     │
             │               │               │
             └───────────────┼───────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ RASPBERRY PI   │
                    │   GATEWAY      │
                    │ 192.168.50.1   │
                    │ (Static IP)    │
                    │                │
                    │ • TCP :5006    │◄── Lander ESP32
                    │ • UDP :5005    │◄── Rover Laptop (via HC-12)
                    │ • UDP :5007    │◄── Drone ESP32
                    │ • HTTP:8001    │──► Backend API
                    │ • WS  :8001    │◄──► Backend WS
                    └───────┬────────┘
                            │
                    ┌───────┴───────┐
                    │   ETHERNET    │
                    │   / Wi-Fi     │
                    │(Dev Machine)  │
                    └───────┬───────┘
                            │
                            ▼
                   ┌────────────────┐
                   │  DEV MACHINE   │
                   │   BACKEND      │
                   │ 127.0.0.1:8000 │
                   │                │
                   │ • HTTP :8000   │──► Dashboard
                   │ • WS   :8000   │◄──► Dashboard
                   │ • SQLite       │
                   └────────────────┘
```

## Interface Summary

| Connection | Protocol | Port | Direction | Description |
|------------|----------|------|-----------|-------------|
| Lander → Pi | TCP | 5006 | ESP32 → Pi | JSON telemetry & commands |
| Rover Laptop → Pi | UDP | 5005 | Laptop → Pi | ASCII telemetry packets |
| Drone → Pi | UDP | 5007 | Drone → Pi | JSON telemetry packets |
| Pi → Backend | HTTP | 8001 | Pi → Dev Machine | REST API polling |
| Pi → Backend | WebSocket | 8001 | Pi ↔ Dev Machine | Live telemetry stream |
| Backend → Dashboard | HTTP | 8000 | Dev Machine → Browser | Dashboard assets + API |
| Backend → Dashboard | WebSocket | 8000 | Dev Machine ↔ Browser | Live telemetry stream |

## Raspberry Pi Network Configuration

### Wi-Fi Access Point
The Pi operates as a Wi-Fi access point for the ESP32 devices:

```bash
# SSID and Password (from lander.ino / lander_config.h)
SSID: "Mission-Control"
Password: "YOUR_WIFI_PASSWORD"

# Pi Static IP (from lander.ino GATEWAY_HOST)
Gateway IP: 192.168.50.1
```

### Pi Network Interfaces
| Interface | Role | Configuration |
|-----------|------|---------------|
| `wlan0` | Access Point | Static 192.168.50.1/24, hosts Mission-Control SSID |
| `eth0` / `wlan1` | Uplink | DHCP or static to development machine network |

### Gateway Service Binding
```python
# gateway/config.py defaults
LANDER_TCP_HOST = "0.0.0.0"   # Listen all interfaces
LANDER_TCP_PORT = 5006
ROVER_UDP_HOST = "0.0.0.0"
ROVER_UDP_PORT = 5005
DRONE_UDP_HOST = "0.0.0.0"
DRONE_UDP_PORT = 5007
GATEWAY_HOST = "0.0.0.0"      # HTTP/WS bind
GATEWAY_PORT = 8001
```

## Development Machine Backend Network Configuration

### Environment Variables (from run.py)
```bash
# Network Mode
GATEWAY_HTTP_URL=http://192.168.50.1:8001
GATEWAY_WS_URL=ws://192.168.50.1:8001/ws/telemetry

# Simulation Mode
GATEWAY_HTTP_URL=http://127.0.0.1:8001
GATEWAY_WS_URL=ws://127.0.0.1:8001/ws/telemetry
```

### Backend Service Binding
```python
# run.py defaults
HOST = "0.0.0.0"      # Bind all interfaces
PORT = 8000           # HTTP/WS port
```

## Communication Matrix

### Lander ↔ Pi Gateway (TCP 5006)
| Aspect | Detail |
|--------|--------|
| **Initiator** | ESP32 (client) → Pi (server) |
| **Framing** | Newline-delimited JSON (`\n` terminated) |
| **Encoding** | UTF-8 |
| **Max Line** | 768 bytes (ESP32) / 4096 bytes (Pi) |
| **Telemetry Rate** | ~1 Hz (ACTIVE mode) |
| **Commands** | `GET_STATUS`, `SET_ACTIVE`, `SET_STANDBY` |
| **Request Correlation** | Integer `request_id` allocated by Pi |
| **Reconnection** | ESP32 retries every 1s; Pi accepts new connection, closes old |

**ESP32 → Pi Messages:**
```json
{"type":"telemetry","timestamp_ms":123456,"mode":"ACTIVE","bmp_temperature_c":24.2,"pressure_hpa":1013.5,"dht_temperature_c":24.0,"humidity_pct":58.0,"bmp280_ok":true,"dht11_ok":true}
{"type":"status","timestamp_ms":123456,"mode":"ACTIVE","sensors_polling":true,"bmp280_ok":true,"dht11_ok":true,"bmp280_state":"OK","dht11_state":"OK","firmware":"1.5.0","request_id":42}
{"type":"mode_status","mode":"ACTIVE","request_id":43}
{"type":"command_ack","command":"SET_ACTIVE","ok":true,"accepted":true,"message":"Lander active...","request_id":44}
```

**Pi → ESP32 Messages:**
```json
{"command":"GET_STATUS","request_id":42}
{"command":"SET_ACTIVE","request_id":43}
{"type":"mission_display","device":"rover","connected":true,"data":{"distance":145.0,"pitch":12.4,"roll":-3.2,"cmd":"F","mode":"M"}}
{"type":"mission_display","device":"drone","connected":true,"data":{"flight_status":"CRUISING","latitude":12.9716,"longitude":77.5946}}
```

### Rover Laptop → Pi Gateway (UDP 5005)
| Aspect | Detail |
|--------|--------|
| **Initiator** | Rover Laptop (Windows GUI) → Pi (server) |
| **Format** | ASCII key:value pairs, comma-separated |
| **Fields** | `DIST`, `PITCH`, `ROLL`, `CMD`, `MODE` (all required) |
| **Example** | `DIST:145.0,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M` |
| **Rate** | ~5 Hz |
| **Validation** | All 5 fields required, numeric ranges, enum values |
| **Staleness** | OFFLINE after 2s silence (configurable) |

**Packet Structure:**
```
DIST:<float>,PITCH:<float>,ROLL:<float>,CMD:<F|B|L|R|S>,MODE:<M|A>
```

**Field Constraints:**
- `DIST`: 0–10000 cm
- `PITCH`: -90 to +90°
- `ROLL`: -90 to +90°
- `CMD`: F, B, L, R, S
- `MODE`: M, A

### Drone → Pi Gateway (UDP 5007)
| Aspect | Detail |
|--------|--------|
| **Initiator** | Drone ESP32 → Pi (server) |
| **Format** | JSON (UTF-8) |
| **Max Size** | 4096 bytes |
| **Sequence** | Monotonic integer, RFC 1982 rollover (16/32-bit) |
| **Rate** | ~2 Hz (configurable) |
| **Staleness** | OFFLINE after 10s silence (configurable) |

**Packet Schema:**
```json
{
  "device_id": "esp32-drone",
  "sequence": 123,
  "timestamp_ms": 1234567890,
  "flight_status": "CRUISING",
  "orientation": {"roll": 1.2, "pitch": -0.5, "yaw": 180.0},
  "environment": {"temperature_c": 26.8, "pressure_hpa": 1013.2, "humidity_pct": 48.0},
  "gps": {"latitude": 12.9716, "longitude": 77.5946, "altitude_m": 50.0},
  "battery": {"voltage_v": 11.1, "percentage": 85.0}
}
```

**Validation Rules:**
- `device_id`: non-empty string (expected "esp32-drone")
- `sequence`: non-negative integer, newer than last (RFC 1982)
- `timestamp_ms`: non-negative integer
- `flight_status`: non-empty string
- All numeric fields: finite, within defined ranges
- Rejected packets do NOT overwrite last valid state

### Pi Gateway HTTP API (Port 8001)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Gateway process health |
| `/api/devices` | GET | Lander device info + connection state |
| `/api/lander/status` | GET | Full lander status (mode, sensors, firmware) |
| `/api/rover/status` | GET | Rover status from UDP receiver |
| `/api/drone/status` | GET | Drone status from UDP receiver |
| `/api/rover/display` | POST | Forward rover data to lander LCD |
| `/api/drone/display` | POST | Forward drone data to lander LCD |
| `/api/commands` | POST | Send command to lander (GET_STATUS, SET_ACTIVE, SET_STANDBY) |
| `/ws/telemetry` | WS | Live telemetry broadcast (all devices) |

### Backend HTTP API (Port 8000)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Application info + simulation_mode flag |
| `/health` | GET | Health check + simulation_mode flag |
| `/dashboard` | GET | Main dashboard HTML |
| `/api/mission/state` | GET | Current mission state snapshot |
| `/api/rover/status` | GET | Rover status (normalized source) |
| `/api/drone/status` | GET | Drone status (normalized source) |
| `/api/mission/commands` | GET | Command history |
| `/api/mission/commands` | POST | Submit command to lander |
| `/api/mission/events` | GET | Mission events log |
| `/api/mission/telemetry/history` | GET | Telemetry history (5-min window) |
| `/api/mission/session/reset` | POST | Clear session data |
| `/ws/telemetry` | WS | Live telemetry + state + commands |

---

## Wi-Fi Access Point Setup (Raspberry Pi)

The Pi must host the `Mission-Control` access point. Typical setup:

```bash
# /etc/hostapd/hostapd.conf
interface=wlan0
driver=nl80211
ssid=Mission-Control
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=YOUR_WIFI_PASSWORD
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP

# /etc/dnsmasq.conf
interface=wlan0
dhcp-range=192.168.50.10,192.168.50.100,255.255.255.0,24h

# Static IP for wlan0 in /etc/dhcpcd.conf
interface wlan0
static ip_address=192.168.50.1/24
nohook wpa_supplicant
```

---

## Firewall & Port Requirements

| Host | Port | Protocol | Direction | Purpose |
|------|------|----------|-----------|---------|
| Pi | 5006 | TCP | Inbound | Lander ESP32 telemetry |
| Pi | 5005 | UDP | Inbound | Rover laptop telemetry |
| Pi | 5007 | UDP | Inbound | Drone telemetry |
| Pi | 8001 | TCP | Inbound | HTTP API + WebSocket |
| Dev Machine | 8000 | TCP | Inbound | Backend API + Dashboard |
| Dev Machine | 8001 | TCP | Outbound | Backend → Pi Gateway |

---

## Verification Commands

```bash
# Verify Pi Gateway is reachable
curl http://192.168.50.1:8001/health
curl http://192.168.50.1:8001/api/lander/status
curl http://192.168.50.1:8001/api/rover/status
curl http://192.168.50.1:8001/api/drone/status

# Test WebSocket
websocat ws://192.168.50.1:8001/ws/telemetry

# Verify Backend
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/mission/state
```

---

## Related Documents

- [System Architecture](system-architecture.md) — Component overview
- [TCP Protocol](protocols/tcp-protocol.md) — Lander message formats
- [Rover UDP](protocols/rover-udp.md) — ASCII packet details
- [Drone UDP](protocols/drone-udp.md) — JSON schema and validation
- [Deployment](deployment/raspberry-pi-setup.md) — Pi setup instructions