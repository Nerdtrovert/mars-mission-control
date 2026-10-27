# Gateway and Mission Control API contracts

## Raspberry Pi gateway

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Gateway process health, separate from lander connectivity |
| GET | `/api/devices` | Lander identity and connection state |
| GET | `/api/lander/status` | Lander mode, timestamp, and sensor health |
| GET | `/api/rover/status` | Latest valid rover datagram plus online/stale state |
| POST | `/api/commands` | Send a supported lander status/mode command |
| WebSocket | `/ws/telemetry` | Lander telemetry and rover updates |

The lander status contract contains `gateway_state`, `device_state`,
`timestamp_ms`, `mode` (`ACTIVE`/`STANDBY`), `sensors_polling`, `bmp280_ok`,
`dht11_ok`, `bmp280_state`, `dht11_state`, and `firmware`. The gateway health
endpoint reports gateway process health and a separate device-connected flag;
a reachable gateway does not prove that the ESP32 or rover is online.

The only lander command names are `GET_STATUS`, `SET_ACTIVE`, and
`SET_STANDBY`. Requests contain `command_id`, `command`, and optional `params`.
Responses contain `command_id`, `accepted`, nullable `reason`, and `timestamp`.
The lander Wi-Fi stream carries the JSON message contract documented in
[serial-protocol.md](serial-protocol.md). Despite the historical filename, it
is not an operational serial link.

## Lander ESP32 to Pi Wi-Fi stream

The ESP32 opens a TCP client connection to the Pi at LANDER_TCP_HOST and
LANDER_TCP_PORT (default Pi listener 0.0.0.0:5006). Messages remain
newline-delimited UTF-8 JSON, preserving the existing telemetry schema and
status/mode command messages. Only fully validated messages refresh the
lander receipt timestamp. GATEWAY_STALE_TIMEOUT_S and
GATEWAY_OFFLINE_TIMEOUT_S determine STALE/OFFLINE state. USB serial is reserved
for programming and local debug output.

The MacBook still uses the Pi's existing HTTP and WebSocket APIs. Its
GATEWAY_HTTP_URL and GATEWAY_WS_URL settings are unchanged. Rover telemetry
continues to arrive at the Pi by UDP port 5005.

## Rover UDP and status contract

The Pi listens on `ROVER_UDP_HOST` / `ROVER_UDP_PORT` (default `0.0.0.0:5005`).
The Windows GUI owns the rover COM port and sends ASCII datagrams containing
exactly these fields:

```text
DIST:145,PITCH:12.4,ROLL:-3.2,CMD:F,MODE:M
```

`DIST` is centimetres, `PITCH` and `ROLL` are degrees, `CMD` is one of `F`,
`B`, `L`, `R`, `S`, and `MODE` is `M` or `A`. All fields are required; unknown,
duplicate, missing, non-finite, out-of-range, or invalid enum values are
rejected without changing the last valid sample. No battery, wheel speed, or
encoder fields exist.

The Pi status adds `rover_id`, `connection_state` (`ONLINE`/`OFFLINE`),
`last_seen` (receipt time), and `source: "network"`. It retains last-known
readings when offline while marking them explicitly offline. Valid packets
arrive about every 200 ms; the Pi marks the rover offline after
`ROVER_OFFLINE_TIMEOUT_S` (default 2 seconds).

Both Pi and Mac expose the same public rover fields: `rover_id`, `distance_cm`,
`pitch_deg`, `roll_deg`, `command`, `mode`, `connection_state`, `last_seen`,
`source`, plus nullable simulated-event fields where present. Simulator mode
uses `source: "simulator"`; network mode uses `source: "network"`. Mac
WebSocket updates use `{ "type": "rover_telemetry", "rover": <status> }`.

## MacBook Mission Control API and live updates

The existing `/api/mission/state`, `/api/mission/telemetry/history`,
`/api/mission/commands`, `/api/mission/events`, `/api/mission/session/reset`,
and `/ws/telemetry` endpoints remain. Lander live frames use `telemetry` and
`state_snapshot`; rover frames are separate `rover_telemetry` messages. The
dashboard also polls `/api/rover/status` as a fallback. `GATEWAY_MODE` and
`ROVER_MODE` independently select simulator or network adapters.

There is no drone endpoint or message schema because the drone interface has
not yet been defined.
