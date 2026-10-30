# Raspberry Pi Gateway Deployment Workflow

This document describes the deployment protocol used to deploy the Gateway software from the development machine to the physical Raspberry Pi 4.

---

## 1. Architectural Principles

Per **Section 2 & 9 of the Engineering Constitution (`AGENTS.md`)**:
- **No Git on the Pi**: The Raspberry Pi runs strictly production services. It does not pull code directly from Git or contain build pipelines.
- **Rsync Deployment**: Synchronized pushes from the development machine using `deploy/deploy_gateway.sh` are the authoritative delivery mechanism.
- **State Preservation**: Deployment synchronizations must **never overwrite** live remote configuration (`.env`), active SQLite databases, logs, virtual environments (`.venv`), or runtime state.

---

## 2. Deployment Script: `deploy/deploy_gateway.sh`

The deployment script resides at `deploy/deploy_gateway.sh`. It synchronizes the repository gateway code to the Pi using `rsync` over SSH.

### Configurable Variables
The script uses standard shell parameter expansion with sensible defaults:

```bash
PI_HOST="${PI_HOST:-192.168.50.1}"
PI_USER="${PI_USER:-pi}"
PI_DEST="${PI_DEST:-/home/pi/mars-mission-control}"
DRY_RUN="${1:-}"
```

| Variable | Default Value | Description |
|---|---|---|
| `PI_HOST` | `192.168.50.1` | IP address or hostname of the Raspberry Pi |
| `PI_USER` | `pi` | SSH user account on the Raspberry Pi |
| `PI_DEST` | `/home/pi/mars-mission-control` | Absolute destination path on the Pi |
| `DRY_RUN` | *(empty)* | Pass `--dry-run` to preview actions without modifying files |

---

## 3. Exclusion Rules

The rsync options explicitly exclude files that should not be transferred to or deleted from the Pi:

```bash
RSYNC_OPTS=(
    -avz
    --delete
    --exclude='.git/'
    --exclude='.github/'
    --exclude='.venv/'
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='.pytest_cache/'
    --exclude='.DS_Store'
    --exclude='.env'
    --exclude='*.db'
    --exclude='*.db-wal'
    --exclude='*.db-shm'
    --exclude='backend/data/'
    --exclude='data/'
    --exclude='frontend/'
    --exclude='lander/lander.ino'
    --exclude='lander/lander_config.h'
    --exclude='lander/lander_config.example.h'
    --exclude='.pio/'
)
```

**Why these exclusions matter:**
- `--exclude='.env'`: Prevents the local development machine `.env` from overwriting the Pi gateway's local `gateway/.env`.
- `--exclude='*.db*'`: Preserves historical telemetry and audit logs on both ends.
- `--exclude='.venv/'`: Prevents macOS compiled binary wheels from corrupting the Linux ARM64 virtual environment.
- `--exclude='lander/*'`: ESP32 firmware is compiled and flashed via USB on the development workstation; it is not executed on the Pi.

---

## 4. How to Execute Deployment

### Step 1: Connect to Mission-Control Wi-Fi
Ensure the development machine Wi-Fi interface is connected to the `Mission-Control` network (or connected over Ethernet) so `192.168.50.1` is reachable:

```bash
ping -c 3 192.168.50.1
```

### Step 2: Dry Run Preview (Recommended)
Verify which files will be synchronized without making any changes:

```bash
./deploy/deploy_gateway.sh --dry-run
```

### Step 3: Perform Live Deployment
Run the deployment script:

```bash
./deploy/deploy_gateway.sh
```

To deploy to a custom host or IP:
```bash
PI_HOST=192.168.1.120 ./deploy/deploy_gateway.sh
```

---

## 5. Post-Deployment Verification

After the files are synced, the script prompts for or executes remote health checks:

1. **Restart the Gateway Daemon**:
   ```bash
   ssh pi@192.168.50.1 "sudo systemctl restart mars-gateway.service"
   ```

2. **Verify Daemon Health**:
   From your development machine terminal:
   ```bash
   curl -s http://192.168.50.1:8001/health | jq .
   ```
   Expected response:
   ```json
   {
     "status": "healthy",
     "connection_state": "ONLINE",
     "version": "1.0.0",
     "uptime_seconds": 2.1,
     "device_connected": false
   }
   ```

3. **Check Live Gateway Journal Logs**:
   ```bash
   ssh pi@192.168.50.1 "journalctl -u mars-gateway.service -n 50 --no-pager"
   ```
