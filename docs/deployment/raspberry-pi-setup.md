# Raspberry Pi 4 Gateway Setup Guide

This guide details the prerequisites, operating system setup, private access point configuration, dependencies, and systemd service creation for the Raspberry Pi 4 Hardware Gateway.

---

## 1. Hardware & OS Requirements

| Specification | Requirement |
|---|---|
| **Board** | Raspberry Pi 4 Model B (2 GB RAM or higher recommended) |
| **Operating System** | Raspberry Pi OS (64-bit Bookworm / Bullseye recommended) |
| **Storage** | 16 GB+ MicroSD card (Class 10 / A1 or better) |
| **Power** | Official 5V 3.0A USB-C Power Supply |
| **Interfaces** | Integrated 2.4 GHz / 5.0 GHz Wi-Fi (for `Mission-Control` AP) |

---

## 2. Private Wi-Fi Access Point Configuration

The Raspberry Pi functions as the dedicated local wireless router for Mars Mission Control. It broadcasts a private Wi-Fi network without requiring public internet access.

- **SSID**: `Mission-Control`
- **WPA2 Password**: `YOUR_WIFI_PASSWORD` *(configured in deployment)*
- **Gateway IP**: `192.168.50.1`
- **Subnet**: `255.255.255.0` (`/24`)
- **DHCP Pool**: `192.168.50.10` to `192.168.50.100`

### NetworkManager Configuration (Bookworm / Recommended)
On Raspberry Pi OS Bookworm, configure the access point via `nmcli`:

```bash
sudo nmcli connection add \
  type wifi \
  ifname wlan0 \
  con-name "Mission-Control-AP" \
  autoconnect yes \
  ssid "Mission-Control" \
  mode ap \
  802-11-wireless.band bg \
  802-11-wireless-security.key-mgmt wpa-psk \
  802-11-wireless-security.psk "YOUR_WIFI_PASSWORD" \
  ipv4.method shared \
  ipv4.addresses 192.168.50.1/24

sudo nmcli connection up "Mission-Control-AP"
```

Verify the interface:
```bash
ip addr show wlan0
# Output should show inet 192.168.50.1/24
```

---

## 3. Network Port Allocations

The Gateway daemon binds to all interfaces (`0.0.0.0`) on the Pi. Ensure local firewall rules (`ufw` or `iptables`) allow traffic on these ports:

| Port | Protocol | Ingestion Target | Purpose |
|---|---|---|---|
| **5006** | TCP | `0.0.0.0:5006` | ESP32 Lander newline-delimited JSON connection |
| **5005** | UDP | `0.0.0.0:5005` | Surface Rover ASCII datagrams from Laptop Tkinter GUI |
| **5007** | UDP | `0.0.0.0:5007` | Aerial Drone JSON datagrams from ESP32 client |
| **8001** | HTTP / WS | `0.0.0.0:8001` | Gateway REST API (`/health`, `/api/*`) & WebSocket (`/ws/telemetry`) |
| **22** | SSH | `0.0.0.0:22` | Deployment and maintenance via `deploy_gateway.sh` |

---

## 4. Python Environment & Dependencies

On the Raspberry Pi:

```bash
# 1. Install system prerequisites
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip rsync

# 2. Prepare deployment directory
mkdir -p /home/pi/mars-mission-control
cd /home/pi/mars-mission-control

# 3. Create dedicated virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 4. Install production dependencies
pip install --upgrade pip
pip install fastapi uvicorn websockets pydantic
```

---

## 5. Gateway Configuration (`gateway/.env`)

Copy the template from `gateway/.env.example` into `gateway/.env`:

```bash
cp /home/pi/mars-mission-control/gateway/.env.example /home/pi/mars-mission-control/gateway/.env
```

Ensure the configuration specifies the server bind addresses:
```env
LANDER_TCP_HOST=0.0.0.0
LANDER_TCP_PORT=5006
GATEWAY_STALE_TIMEOUT_S=3.0
GATEWAY_OFFLINE_TIMEOUT_S=5.0
GATEWAY_COMMAND_TIMEOUT_S=2.0
LANDER_RECONNECT_DELAY_S=1.0

ROVER_UDP_HOST=0.0.0.0
ROVER_UDP_PORT=5005
ROVER_OFFLINE_TIMEOUT_S=2.0

DRONE_UDP_HOST=0.0.0.0
DRONE_UDP_PORT=5007
DRONE_OFFLINE_TIMEOUT_S=5.0

ROVER_SIMULATOR=false
DRONE_SIMULATOR=false
```

---

## 6. Systemd Service Setup (`mars-gateway.service`)

Create a systemd unit file to ensure the Gateway runs on boot and automatically restarts upon failures:

```bash
sudo tee /etc/systemd/system/mars-gateway.service > /dev/null << 'EOF'
[Unit]
Description=Mars Mission Control — Raspberry Pi Edge Gateway Daemon
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/mars-mission-control
EnvironmentFile=-/home/pi/mars-mission-control/gateway/.env
ExecStart=/home/pi/mars-mission-control/.venv/bin/uvicorn gateway.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=3s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mars-gateway.service
sudo systemctl start mars-gateway.service
```

---

## 7. Status & Health Verification

Check service status:
```bash
systemctl status mars-gateway.service
```

Inspect live service logs:
```bash
journalctl -u mars-gateway.service -f
```

Query the local HTTP health check:
```bash
curl -s http://127.0.0.1:8001/health | jq .
```
Expected output:
```json
{
  "status": "healthy",
  "connection_state": "ONLINE",
  "version": "1.0.0",
  "uptime_seconds": 12.4,
  "device_connected": false
}
```
*(Note: `device_connected` becomes `true` once the ESP32 establishes its TCP socket on port 5006).*
