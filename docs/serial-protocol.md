# ESP32 Lander — Serial Protocol Specification (docs/serial-protocol.md)

This document formalizes the serial communication protocol between the ESP32 lander and the Raspberry Pi hardware edge gateway, corresponding to the frozen firmware baseline `v1.3.1-esp32-baseline` in `Lander/lander/lander.ino`.

---

## 1. Physical & Framing Specification

- **Baud Rate**: `115200`
- **Data Bits**: `8`
- **Parity**: `None`
- **Stop Bits**: `1` (8N1)
- **Flow Control**: None
- **Framing**: UTF-8 encoded, newline-delimited JSON (`\n` terminated).
- **Buffer Constraints**:
  - Maximum RX line buffer: 255 characters.
  - Maximum TX line buffer: 512 characters.
- **Bootloader Output**: ESP32 ROM boot text emitted on reset is non-JSON. The Raspberry Pi serial reader must discard lines that do not parse as valid JSON objects.

---

## 2. Inbound Messages (Raspberry Pi -> ESP32)

All inbound requests are single-line JSON objects with a mandatory `request_id` (integer) and `command` (string):

```json
{"command": "OPEN_GATE", "request_id": 101}
```

### Supported Commands
| Command Name | Description | Preconditions |
| :--- | :--- | :--- |
| `GET_STATUS` | Requests an immediate status snapshot | None |
| `SET_ACTIVE` | Enters ACTIVE mode (sensor polling & gate actuation enabled) | None |
| `SET_STANDBY` | Enters STANDBY mode (disables polling & movement) | Gate must not be moving |
| `OPEN_GATE` | Ramps servos toward open position | Mode must be ACTIVE; Gate must be CLOSED |
| `CLOSE_GATE` | Ramps servos toward closed position | Mode must be ACTIVE; Gate must be OPEN |

---

## 3. Outbound Messages (ESP32 -> Raspberry Pi)

### 3.1 Command Acknowledgement (`command_ack`)
Emitted immediately upon processing an incoming command:

```json
{
  "type": "command_ack",
  "request_id": 101,
  "accepted": true,
  "reason": null
}
```

If rejected:
```json
{
  "type": "command_ack",
  "request_id": 101,
  "accepted": false,
  "reason": "INVALID_STATE",
  "fault": null
}
```

Rejection reasons:
- `GATE_BUSY`: Gate is already moving or standby is pending.
- `INVALID_STATE`: Gate not in valid position for movement, or mode is STANDBY.
- `GATE_UNKNOWN`: Limits not yet settled or noisy.
- `GATE_FAULT`: A fault is latched.
- `INVALID_COMMAND`: Unknown command string.
- `INVALID_REQUEST`: Missing `request_id`, malformed JSON, or buffer overflow.

---

### 3.2 Periodic Telemetry (`telemetry`)
Emitted approximately once per second while in `ACTIVE` mode:

```json
{
  "type": "telemetry",
  "timestamp_ms": 48200,
  "mode": "ACTIVE",
  "gate_state": "CLOSED",
  "closed_limit": true,
  "open_limit": false,
  "bmp_temperature_c": 23.4,
  "pressure_hpa": 1014.1,
  "dht_temperature_c": 23.0,
  "humidity_pct": 52.0,
  "bmp280_ok": true,
  "dht11_ok": true,
  "fault": null
}
```

---

### 3.3 Gate State Transitions (`gate_status`)
Emitted whenever the physical gate changes state:

```json
{
  "type": "gate_status",
  "state": "OPENING"
}
```

When entering a fault, limit states and the fault code are included:
```json
{
  "type": "gate_status",
  "state": "FAULT",
  "fault": "BOTH_LIMITS_ACTIVE",
  "closed_limit": true,
  "open_limit": true
}
```

---

### 3.4 Full Device Status (`status`)
Emitted in response to `GET_STATUS`:

```json
{
  "type": "status",
  "request_id": 101,
  "timestamp_ms": 48350,
  "mode": "ACTIVE",
  "gate_state": "CLOSED",
  "closed_limit": true,
  "open_limit": false,
  "fault": null,
  "pending_standby": false,
  "startup_limits_settled": true,
  "limits_established": true,
  "sensors_polling": true,
  "bmp280_ok": true,
  "dht11_ok": true,
  "bmp280_state": "OK",
  "dht11_state": "OK",
  "firmware": "1.3.1"
}
```
