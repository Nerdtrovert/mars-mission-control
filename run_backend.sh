#!/usr/bin/env bash
# ==============================================================================
# Mars Mission Control — Backend Launcher
# ==============================================================================
# Usage:
#   ./run_backend.sh            # Runs Sim mode (Default)
#   ./run_backend.sh network    # Full Hardware Network Mode
#   ./run_backend.sh sim        # Offline Local Simulator Mode
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

MODE="${1:-sim}"

# Activate virtualenv if present
if [[ -f "backend/.venv/bin/activate" ]]; then
    source "backend/.venv/bin/activate"
fi

python3 run.py "${MODE}" "${@:2}"
