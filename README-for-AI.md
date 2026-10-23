# Mars Mission Control — AI and Developer Handoff

Read [AGENTS.md](AGENTS.md), [docs/DECISIONS.md](docs/DECISIONS.md), and [docs/api-contract.md](docs/api-contract.md) before changing code. `AGENTS.md` is the engineering constitution; `docs/DECISIONS.md` records accepted and proposed decisions. This file is a short repository map, not a second setup or API specification.

## Current system and ownership

Mars Mission Control currently implements the lander exhibition path:

1. Frozen ESP32 lander firmware (`v1.3.1-esp32-baseline`) owns GPIOs, sensors, gate movement, limit checks, and local safety interlocks.
2. The Raspberry Pi gateway owns the only USB serial connection and exposes HTTP and WebSocket interfaces.
3. The MacBook FastAPI backend selects either an in-process simulator or the Pi network gateway, owns mission state and SQLite history, and serves the dashboard.
4. The dashboard is a vanilla HTML/CSS/JavaScript client served at `/dashboard`.

Rover and drone integration are future work. No rover or drone implementation or generic device framework exists. Do not shift lander safety or serial ownership into the MacBook backend. Never infer an OPEN/CLOSED gate endpoint from inactive switches; use `UNKNOWN` until authoritative device state establishes an endpoint. Reconnection and backend startup must not issue movement commands.

## Repository map

- `backend/app/`: FastAPI application, REST routes, mission state and command tracking, gateway client/runners, telemetry validation, and SQLite persistence.
- `backend/tests/`: unit and localhost integration tests; no physical hardware is required.
- `gateway/`: Raspberry Pi FastAPI service, serial transport/manager, configuration, routes, and WebSocket broadcaster.
- `frontend/`: dashboard assets. The optional uptime diagnostic is enabled only with `?uptimeDiag=1`, stores a bounded in-memory sample, and is disabled by default.
- `Lander/lander/`: frozen firmware and wiring reference. Do not change the firmware baseline or serial protocol without the approvals required by `AGENTS.md`.
- `docs/`: architecture and future-boundary guidance, implemented API contracts, frozen serial protocol, and decision records.

See [README.md](README.md) for MacBook/Pi setup and [docs/api-contract.md](docs/api-contract.md) for the implemented REST and WebSocket interfaces. `docs/architecture.md` distinguishes the current lander integration from proposed rover/drone principles.

## Configuration and verification

Use `backend/.env.example` for MacBook settings and `gateway/.env.example` for Pi serial settings. The root `.env.example` is a combined reference. Keep real local values in ignored `.env` files; shell environment values take precedence. `GATEWAY_MODE=simulator` is hardware-free and explicitly marked as simulated. `GATEWAY_MODE=network` (or `real`) connects to the configured Pi and does not silently switch to simulated data if the gateway is unreachable.

From the repository root:

```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests
node --check frontend/js/dashboard.js
git diff --check
```

The backend uptime field `timestamp_ms` is ESP32 milliseconds since boot. `received_at` and mission timestamps are host-generated UTC timestamps; only presentation code converts them to IST. The firmware protocol has no boot/session identifier, so a large counter reset is recognized using the existing heuristic and cannot distinguish every long-delayed packet from a reboot. The previously reported two-second visual uptime skip has not been conclusively reproduced.
