#!/usr/bin/env bash
# ==============================================================================
# Mars Mission Control — Raspberry Pi Edge Gateway Deployment Script
# ==============================================================================
# Deploys gateway files from MacBook Mission Control to Raspberry Pi 4 via rsync.
# Adheres strictly to AGENTS.md and safe deployment guidelines:
# - Does not run git on the Raspberry Pi.
# - Preserves existing .env, service configurations, SQLite DBs, and runtime state.
# - Explicit exclusion of build artifacts, virtualenvs, caches, and secrets.
# ==============================================================================

set -euo pipefail

PI_HOST="${PI_HOST:-192.168.50.1}"
PI_USER="${PI_USER:-pi}"
PI_DEST="${PI_DEST:-/home/pi/mars-mission-control}"
DRY_RUN="${1:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Mars Mission Control Gateway Deployment ==="
echo "Source:      ${REPO_ROOT}"
echo "Destination: ${PI_USER}@${PI_HOST}:${PI_DEST}"

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
    --exclude='Lander/lander/lander.ino'
    --exclude='Lander/lander/lander_config.h'
    --exclude='.pio/'
)

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
    echo "[INFO] Running in DRY-RUN mode. No remote files will be modified."
    RSYNC_OPTS+=(--dry-run)
fi

echo "--- Synchronizing files via rsync ---"
rsync "${RSYNC_OPTS[@]}" \
    "${REPO_ROOT}/gateway/" "${PI_USER}@${PI_HOST}:${PI_DEST}/gateway/"

rsync "${RSYNC_OPTS[@]}" \
    "${REPO_ROOT}/backend/app/" "${PI_USER}@${PI_HOST}:${PI_DEST}/app/"

if [[ "${DRY_RUN}" == "--dry-run" ]]; then
    echo "[INFO] Dry run complete."
    exit 0
fi

echo "--- Verifying Gateway Service Status on Remote Host ---"
ssh -o ConnectTimeout=5 "${PI_USER}@${PI_HOST}" bash << 'EOF'
    if systemctl is-active --quiet mars-gateway.service 2>/dev/null; then
        echo "[INFO] Restarting mars-gateway service..."
        sudo systemctl restart mars-gateway.service
        sleep 2
        sudo systemctl status mars-gateway.service --no-pager
    else
        echo "[NOTE] mars-gateway.service is not running via systemd. If running uvicorn manually, restart it."
    fi
EOF

echo "=== Deployment complete ==="
