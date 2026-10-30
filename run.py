#!/usr/bin/env python3
"""
Mars Mission Control — Unified Backend Mode Launcher
====================================================
Two operating modes: Network (hardware) and Sim (software-only).

Usage:
    python run.py network         # Full Hardware Network Mode (Real Lander, Rover, Drone)
    python run.py sim             # Offline Local Simulator Mode (No Pi needed)
"""

import argparse
import os
from pathlib import Path
import sys

# Ensure repository root and backend directory are in sys.path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"

# Auto-detect and re-exec with backend/.venv if not already active
if not os.environ.get("VIRTUAL_ENV"):
    venv_py = BACKEND_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    if venv_py.is_file() and sys.executable != str(venv_py):
        os.execv(str(venv_py), [str(venv_py)] + sys.argv)

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

GATEWAY_HOST = os.getenv("GATEWAY_HOST", "192.168.50.1")
GATEWAY_PORT = os.getenv("GATEWAY_HTTP_PORT", "8001")

MODES = {
    "network": {
        "name": "FULL HARDWARE NETWORK MODE",
        "description": "All physical devices (Lander, Rover, and Drone hardware)",
        "env": {
            "GATEWAY_MODE": "network",
            "ROVER_MODE": "network",
            "DRONE_MODE": "network",
            "GATEWAY_HTTP_URL": os.getenv("GATEWAY_HTTP_URL", f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"),
            "GATEWAY_WS_URL": os.getenv("GATEWAY_WS_URL", f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}/ws/telemetry"),
            "MISSION_DB_PATH": os.getenv("MISSION_DB_PATH", "data/mission_control.db"),
        },
        "details": [
            "Lander: REAL hardware via Raspberry Pi Gateway (TCP port 5006)",
            "Rover:  REAL hardware via Windows Tkinter GUI / HC-12 (UDP port 5005)",
            "Drone:  REAL hardware via Drone ESP32 client (UDP port 5007)",
            "Output: Awaiting physical telemetry packets across all channels",
        ],
    },
    "sim": {
        "name": "OFFLINE LOCAL SIMULATOR MODE",
        "description": "Zero physical hardware required (pure local development)",
        "env": {
            "GATEWAY_MODE": "simulator",
            "ROVER_MODE": "simulator",
            "DRONE_MODE": "simulator",
            "GATEWAY_HTTP_URL": "http://127.0.0.1:8001",
            "GATEWAY_WS_URL": "ws://127.0.0.1:8001/ws/telemetry",
            "MISSION_DB_PATH": "data/mission_control.db",
        },
        "details": [
            "Lander: In-memory deterministic simulator (synthetic BMP/DHT)",
            "Rover:  In-memory deterministic simulator (autonomous terrain roving)",
            "Drone:  In-memory flight scenario (takeoff, cruising, landing)",
            "Output: Perfect for local UI testing without powering on the Pi",
        ],
    },
}


def main():
    parser = argparse.ArgumentParser(
        description="Mars Mission Control — Backend Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  network      Full Hardware Network Mode (Requires physical Lander, Rover, and Drone)
  sim          Offline Local Simulator Mode (No Pi or ESP32 hardware required)
        """,
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="sim",
        choices=["network", "full-network", "sim", "simulator"],
        help="Backend operating mode (default: sim)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")

    args = parser.parse_args()

    # Normalize aliases
    mode_key = args.mode.lower()
    if mode_key == "full-network":
        mode_key = "network"
    elif mode_key == "simulator":
        mode_key = "sim"

    config = MODES[mode_key]

    # Apply mode environment settings before loading app modules
    for key, val in config["env"].items():
        os.environ[key] = val

    os.environ["PYTHONPATH"] = str(BACKEND_DIR)

    # Print startup banner
    sep = "=" * 70
    print(sep)
    print(f"  MARS MISSION CONTROL — {config['name']}")
    print(f"  {config['description']}")
    print(sep)
    for detail in config["details"]:
        print(f"  • {detail}")
    print(sep)
    print(f"  Main Dashboard:      http://127.0.0.1:{args.port}/dashboard")
    print(f"  WebSocket Feed:      ws://127.0.0.1:{args.port}/ws/telemetry")
    print(sep)
    print("Starting server... Press CTRL+C to quit.\n")

    try:
        import uvicorn
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=not args.no_reload,
            app_dir=str(BACKEND_DIR),
        )
    except KeyboardInterrupt:
        print("\n[INFO] Mission Control Backend stopped cleanly.")


if __name__ == "__main__":
    main()
