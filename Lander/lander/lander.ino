/*
 * ============================================================================
 *  MARS LANDER FIRMWARE  -  lander.ino   (single file)   v1.3.1
 *  Board : ESP32 DevKit V1 (ESP32-WROOM-32), Arduino IDE
 *  Host  : Raspberry Pi 4 over USB serial, newline-delimited JSON, 115200 8N1
 *
 *  STATUS: NOT hardware tested. NOT compiled with the real ESP32 toolchain by
 *  the author of this revision. Everything marked "PROVISIONAL" must be
 *  calibrated on the assembled mechanism. Compiling is not proof of safety.
 *
 *  REQUIRED LIBRARIES (Library Manager):
 *    - ESP32Servo   (needs bool attached(); present in current releases, 3.x)
 *    - ArduinoJson 7.x
 *    - Adafruit BMP280 Library, Adafruit Unified Sensor, Adafruit BusIO
 *    - DHT sensor library (Adafruit)
 *    - Adafruit NeoPixel
 *    - LiquidCrystal_I2C (Frank de Brabander)
 *
 *  SERIAL: max incoming line 255 chars; one JSON object per line; no debug
 *  text. ESP32 ROM boot text at reset is not JSON; the Pi must ignore it.
 *
 *  FAULT RECOVERY POLICY: faults are LATCHED. No fault-reset command exists.
 *  Inspect the mechanism and switches, correct the problem, then reset or
 *  power-cycle the ESP32. Faults never clear because switches "look normal".
 *
 *  SERVO INITIALISATION LIMITATION:
 *  The MG996R servos have no position feedback. The firmware does not know
 *  where the horns actually are. At the first movement the servos are attached
 *  and commanded starting from the angle CONFIGURED for the confirmed starting
 *  endpoint; if the real horn position differs, the servos will move toward
 *  that angle at full speed on attach. Software ramping afterwards does NOT
 *  remove this initial jerk. The servos are never attached or driven at boot.
 *  A successful attach() only means the PWM channel was allocated; it does NOT
 *  prove a servo is wired, powered or moving. Commission with the ramp
 *  mechanically free and the horns unattached first.
 *
 *  STOP SEMANTICS (three different things):
 *   1. Stop updating the commanded angle: servos keep receiving PWM for the
 *      LAST commanded angle and keep actively holding it (and can stall/heat
 *      against an obstruction).
 *   2. Detach PWM (SERVO_DETACH_AFTER_MOVE, or after an attach failure):
 *      signal stops; an MG996R goes limp and the ramp can be back-driven. This
 *      is NOT a brake or safety, and says nothing about what a servo that is
 *      powered but unwired/miswired will do.
 *   3. Remove servo power: the only way to remove drive entirely. Software here
 *      cannot do it. Use a physical power switch/relay if you need it.
 *
 *  SWITCH LIMITS: two limit switches cannot detect every failure (a switch
 *  stuck inactive, a broken wire, a switch triggering before the real end of
 *  travel, or mechanical slip with the switch still pressed).
 * ============================================================================
 */

#include <Arduino.h>
#include <stdarg.h>
#include <math.h>
#include <Wire.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>
#include <Adafruit_NeoPixel.h>
#include <LiquidCrystal_I2C.h>

// ============================================================================
//  SECTION 1: CONFIGURATION AND GPIO CONSTANTS
// ============================================================================

#define FIRMWARE_VERSION "1.3.1"

// ---- GPIO map (Mars_Lander_Wiring_Structure.txt, GPIO Map V1) --------------
static const uint8_t PIN_SERVO1       = 18;  // Servo 1 signal
static const uint8_t PIN_SERVO2       = 19;  // Servo 2 signal
static const uint8_t PIN_GATE_BUTTON  = 23;  // Button to GND, INPUT_PULLUP
static const uint8_t PIN_LIMIT_OPEN   = 32;  // Open limit switch
static const uint8_t PIN_LIMIT_CLOSED = 33;  // Closed limit switch
static const uint8_t PIN_LED_GREEN    = 25;  // Green status LED (series resistor)
static const uint8_t PIN_LED_RED      = 26;  // Red status LED (series resistor)
static const uint8_t PIN_WS2812       = 27;  // WS2812B data (check level shifting)
static const uint8_t PIN_I2C_SDA      = 21;  // Shared: LCD + BMP280
static const uint8_t PIN_I2C_SCL      = 22;  // Shared: LCD + BMP280
static const uint8_t PIN_DHT          = 17;  // DHT11 data
// Reserved/unused per wiring file: GPIO 16, 13, 14, 4

// ---- Switch logic ----------------------------------------------------------
// Assumption (VERIFY DURING ASSEMBLY): each switch connects its GPIO to GND
// when active, using INPUT_PULLUP, so active = LOW. Whether the physical
// contacts are NO or NC is NOT known; an NC switch with a broken wire would
// read "active" or "inactive" depending on this choice. Confirm by testing.
static const uint8_t  LIMIT_ACTIVE_LEVEL  = LOW;
static const uint8_t  BUTTON_ACTIVE_LEVEL = LOW;
static const uint16_t LIMIT_DEBOUNCE_MS   = 30;   // PROVISIONAL
static const uint16_t BUTTON_DEBOUNCE_MS  = 40;   // PROVISIONAL
// Startup: both limit readings must be unchanged for STARTUP_STABLE_MS before
// the initial gate state is derived. If they do not settle within
// STARTUP_MAX_WAIT_MS, setup() records "startup limits NOT settled" and the
// gate starts UNKNOWN with movement disabled.
static const uint16_t STARTUP_STABLE_MS   = 100;  // PROVISIONAL
static const uint16_t STARTUP_MAX_WAIT_MS = 500;  // PROVISIONAL
// Recovery after a failed startup settle (runs in loop(), no reboot needed):
// an explicit timer starts only while BOTH limit inputs have raw == debounced,
// and is restarted by ANY transition or any input still debouncing. Only after
// both inputs stay synchronised and unchanged for this long are the limits
// "established" and the gate state derived from the switches (one active ->
// that endpoint, none -> UNKNOWN, both -> latched FAULT). Time alone never
// establishes an endpoint, and nothing moves during recovery.
static const uint16_t LIMIT_RECOVERY_STABLE_MS = 500;  // PROVISIONAL

// ---- Servo calibration (ALL PROVISIONAL - CALIBRATE ON REAL MECHANISM) -----
static const int      SERVO_CLOSED_ANGLE  = 30;     // PROVISIONAL degrees
static const int      SERVO_OPEN_ANGLE    = 110;    // PROVISIONAL degrees
static const bool     SERVO2_INVERT       = false;  // PROVISIONAL: true -> servo 2 gets 180-angle
static const int      SERVO_MIN_US        = 600;    // PROVISIONAL pulse width at 0 deg
static const int      SERVO_MAX_US        = 2400;   // PROVISIONAL pulse width at 180 deg
static const float    SERVO_SPEED_DEG_S   = 30.0f;  // PROVISIONAL ramp speed
static const uint16_t SERVO_UPDATE_MS     = 20;
static const uint32_t MOVE_TIMEOUT_MS     = 10000;  // PROVISIONAL total movement timeout

// Start-switch release timeout (PROVISIONAL, independent parameter).
// After a move begins, the START endpoint switch must be seen released within
// this time or the gate faults with START_NOT_RELEASED. Too short: slow
// mechanisms cause nuisance faults. Too long: a stuck start switch is detected
// late. Choose it from commissioning measurements (final switch placement,
// angles and speed); successful compilation says nothing about its suitability.
// It is NOT derived from servo speed or angles. Must satisfy:
// 0 < value <= MOVE_TIMEOUT_MS.
static const uint32_t START_RELEASE_TIMEOUT_MS = 5000;

// If true, a start switch that re-activates after releasing (and before the
// destination is reached) is a fault. Set false if commissioning shows nuisance
// trips from rebound at the start end-stop.
static const bool     FAULT_ON_START_REACTIVATION = true;
// false: keep PWM running after a move (servos hold the last commanded angle).
// true : detach PWM after a move/fault (servos go limp; see STOP SEMANTICS).
static const bool     SERVO_DETACH_AFTER_MOVE = false;

// ---- Sensors ---------------------------------------------------------------
static const uint32_t SENSOR_POLL_MS       = 2000;
static const uint32_t SENSOR_FIRST_POLL_MS = 1000;   // DHT11 power-up settle
static const uint32_t BMP_RETRY_MS         = 10000;  // init retry, from previous attempt
static const uint8_t  BMP280_ADDR_A        = 0x76;
static const uint8_t  BMP280_ADDR_B        = 0x77;
static const float    BMP_TEMP_MIN_C = -40.0f, BMP_TEMP_MAX_C = 85.0f;
static const float    BMP_PRES_MIN_HPA = 300.0f, BMP_PRES_MAX_HPA = 1100.0f;
static const float    DHT_TEMP_MIN_C = 0.0f,  DHT_TEMP_MAX_C = 50.0f;   // DHT11 spec
static const float    DHT_HUM_MIN_PCT = 0.0f, DHT_HUM_MAX_PCT = 100.0f;
#define DHT_TYPE DHT11

// ---- LCD / I2C -------------------------------------------------------------
static const uint8_t  LCD_I2C_ADDR        = 0x27;   // PROVISIONAL: many backpacks use 0x3F
static const uint8_t  LCD_COLS            = 20;
static const uint8_t  LCD_ROWS            = 4;
static const uint32_t LCD_ROTATE_MS       = 6000;
static const uint32_t LCD_ROW_INTERVAL_MS = 20;
static const uint32_t I2C_CLOCK_HZ        = 100000;
static const uint16_t I2C_TIMEOUT_MS      = 30;
static const uint32_t LINK_TIMEOUT_MS     = 15000;

// ---- Status LEDs -----------------------------------------------------------
static const uint16_t RED_MOVE_PERIOD_MS  = 500;
static const uint16_t RED_MOVE_ON_MS      = 250;
static const uint16_t RED_FAULT_PERIOD_MS = 1000;   // double-blink
static const uint16_t RED_FAULT_PULSE_MS  = 100;

// ---- WS2812B ---------------------------------------------------------------
static const uint16_t NUM_LEDS            = 30;     // PROVISIONAL (approx. 1 m strip)
static const uint8_t  STRIP_BRIGHTNESS    = 60;     // PROVISIONAL, keep modest
static const uint16_t ANIM_INTERVAL_MS    = 40;
static const float    HUE_CENTER          = 42500.0f;
static const float    HUE_SPREAD          = 10000.0f;
static const float    VAL_MID             = 110.0f;
static const float    VAL_SWING           = 70.0f;
static const uint8_t  STAR_SPAWN_ODDS     = 15;
static const uint8_t  STAR_DECAY          = 8;

// ---- Serial / protocol -----------------------------------------------------
static const uint32_t SERIAL_BAUD         = 115200;
static const size_t   RX_MAX_LEN          = 255;
static const size_t   TX_MAX_LEN          = 512;
static const uint32_t TELEMETRY_MS        = 1000;

// ---- Compile-time sanity checks on configuration ---------------------------
static_assert(SERVO_CLOSED_ANGLE >= 0 && SERVO_CLOSED_ANGLE <= 180, "closed angle out of range");
static_assert(SERVO_OPEN_ANGLE   >= 0 && SERVO_OPEN_ANGLE   <= 180, "open angle out of range");
static_assert(SERVO_MIN_US < SERVO_MAX_US, "servo pulse range invalid");
static_assert(MOVE_TIMEOUT_MS > 0, "movement timeout must be > 0");
static_assert(START_RELEASE_TIMEOUT_MS > 0, "start-release timeout must be > 0");
static_assert(START_RELEASE_TIMEOUT_MS <= MOVE_TIMEOUT_MS, "start-release timeout must not exceed movement timeout");
static_assert(STARTUP_STABLE_MS >= LIMIT_DEBOUNCE_MS, "startup window must cover debounce");
static_assert(STARTUP_MAX_WAIT_MS > STARTUP_STABLE_MS, "startup max wait too short");
static_assert(LIMIT_RECOVERY_STABLE_MS >= STARTUP_STABLE_MS, "recovery window must be >= startup window");

// ============================================================================
//  SECTION 2: STATE DEFINITIONS
// ============================================================================

enum OperatingMode : uint8_t { OPMODE_ACTIVE, OPMODE_STANDBY };

enum GateState : uint8_t {
  GATE_UNKNOWN, GATE_CLOSED, GATE_OPENING, GATE_OPEN, GATE_CLOSING, GATE_FAULT
};

enum FaultCode : uint8_t {
  FAULT_NONE,
  FAULT_BOTH_LIMITS_ACTIVE,   // both switches active while stationary / at startup
  FAULT_OPEN_TIMEOUT,         // open limit not confirmed within MOVE_TIMEOUT_MS
  FAULT_CLOSE_TIMEOUT,        // closed limit not confirmed within MOVE_TIMEOUT_MS
  FAULT_LIMIT_CONFLICT,       // both switches active during movement AFTER the start switch had released
  FAULT_START_NOT_RELEASED,   // start switch never released within START_RELEASE_TIMEOUT_MS
  FAULT_START_REACTIVATED,    // start switch re-activated before destination reached
  FAULT_DEST_BEFORE_RELEASE,  // destination active while start switch never seen released
  FAULT_SERVO_ATTACH          // one or both servo PWM channels failed to attach
};

enum RejectReason : uint8_t {
  REJ_NONE, REJ_GATE_BUSY, REJ_INVALID_STATE, REJ_GATE_UNKNOWN,
  REJ_GATE_FAULT, REJ_INVALID_COMMAND, REJ_INVALID_REQUEST
};

// NO_DATA = not read yet in this ACTIVE session; OK = fresh valid reading;
// FAILED = init failed or the last reading was invalid.
enum SensorState : uint8_t { SENSOR_NO_DATA, SENSOR_OK, SENSOR_FAILED };

struct DebouncedInput {
  uint8_t  pin;
  uint8_t  activeLevel;
  uint16_t debounceMs;
  bool     rawActive;
  bool     stableActive;
  uint32_t lastChangeMs;
  uint32_t transitions;     // counts every raw change and every stable change
  bool     activatedEdge;   // set when stable state goes inactive -> active
};

// ============================================================================
//  SECTION 3: GLOBAL VARIABLES
// ============================================================================

static OperatingMode gMode           = OPMODE_ACTIVE;
static GateState     gGateState      = GATE_UNKNOWN;
static FaultCode     gFault          = FAULT_NONE;
static bool          gPendingStandby = false;

// Startup / limit-switch stabilisation tracking
static bool gStartupLimitsSettled = false;  // result of the boot-time settle (recorded, never cleared)
static bool gLimitsEstablished    = false;  // true once limits passed a stability window (startup or recovery)

// Loop-time recovery window (only used while !gLimitsEstablished)
static bool     gRecTimerRunning = false;
static uint32_t gRecStartMs      = 0;
static uint32_t gRecOpenTrans    = 0;       // transition counters when the timer (re)started
static uint32_t gRecClosedTrans  = 0;

// Movement tracking
static uint32_t gMoveStartMs   = 0;
static bool     gStartReleased = false;     // start switch seen released during THIS move

static DebouncedInput gLimitOpen, gLimitClosed, gButton;

// Servos
static Servo    gServo1, gServo2;
static bool     gServosAttached = false;    // true only if BOTH attached successfully
static bool     gServoMoving    = false;
static float    gServoAngle     = 0.0f;
static float    gServoTarget    = 0.0f;
static uint32_t gServoLastMs    = 0;

// Sensors
static Adafruit_BMP280 gBmp(&Wire);
static DHT             gDht(PIN_DHT, DHT_TYPE);
static SensorState gBmpState = SENSOR_FAILED;
static SensorState gDhtState = SENSOR_NO_DATA;
static bool     gBmpInitialized = false;
static float    gBmpTemp = NAN, gPressure = NAN, gDhtTemp = NAN, gHumidity = NAN;
static uint32_t gNextSensorPollMs = 0;
static uint32_t gNextBmpInitMs    = 0;   // earliest next init attempt

// Telemetry
static uint32_t gNextTelemetryMs = 0;

// Serial RX
static char     gRxBuf[RX_MAX_LEN + 1];
static size_t   gRxLen = 0;
static bool     gRxOverflow = false;
static bool     gLinkSeen = false;
static uint32_t gLastValidCmdMs = 0;

// LCD
static LiquidCrystal_I2C gLcd(LCD_I2C_ADDR, 20, 4);
static bool     gLcdOk = false;
static char     gLcdLines[4][21];
static char     gLcdShadow[4][21];
static bool     gLcdShadowValid = false;
static uint8_t  gLcdScreen = 0;
static uint32_t gLcdScreenSinceMs = 0;
static uint32_t gLcdLastWriteMs = 0;

// WS2812B
static Adafruit_NeoPixel gStrip(NUM_LEDS, PIN_WS2812, NEO_GRB + NEO_KHZ800);
static uint8_t  gStar[NUM_LEDS];
static uint32_t gLastAnimMs = 0;

// ============================================================================
//  SECTION 4: SMALL HELPERS AND NAME TABLES
// ============================================================================

static bool timeReached(uint32_t now, uint32_t target) {   // rollover-safe
  return (int32_t)(now - target) >= 0;
}

// Elapsed time since 'then', clamped to 0 if 'then' is slightly AFTER 'now'.
// loop() samples 'now' once at the top, but handlers that run later in the same
// pass (serial commands, button) timestamp events with a fresh millis(). A plain
// (now - then) would then underflow to ~4e9 ms and trip timeouts / jump the
// servo ramp immediately. Rollover-safe for any real elapsed time < ~24 days.
static uint32_t elapsedSince(uint32_t now, uint32_t then) {
  int32_t d = (int32_t)(now - then);
  return (d < 0) ? 0u : (uint32_t)d;
}

static float round1(float v) { return roundf(v * 10.0f) / 10.0f; }

static const char* modeName(OperatingMode m) {
  return (m == OPMODE_ACTIVE) ? "ACTIVE" : "STANDBY";
}

static const char* gateStateName(GateState s) {
  switch (s) {
    case GATE_UNKNOWN: return "UNKNOWN";
    case GATE_CLOSED:  return "CLOSED";
    case GATE_OPENING: return "OPENING";
    case GATE_OPEN:    return "OPEN";
    case GATE_CLOSING: return "CLOSING";
    case GATE_FAULT:   return "FAULT";
  }
  return "UNKNOWN";
}

static const char* faultName(FaultCode f) {   // nullptr when no fault -> JSON null
  switch (f) {
    case FAULT_NONE:                return nullptr;
    case FAULT_BOTH_LIMITS_ACTIVE:  return "BOTH_LIMITS_ACTIVE";
    case FAULT_OPEN_TIMEOUT:        return "OPEN_TIMEOUT";
    case FAULT_CLOSE_TIMEOUT:       return "CLOSE_TIMEOUT";
    case FAULT_LIMIT_CONFLICT:      return "LIMIT_CONFLICT";
    case FAULT_START_NOT_RELEASED:  return "START_NOT_RELEASED";
    case FAULT_START_REACTIVATED:   return "START_REACTIVATED";
    case FAULT_DEST_BEFORE_RELEASE: return "DEST_BEFORE_RELEASE";
    case FAULT_SERVO_ATTACH:        return "SERVO_ATTACH_FAILED";
  }
  return "UNKNOWN_FAULT";
}

static const char* rejectName(RejectReason r) {
  switch (r) {
    case REJ_NONE:            return nullptr;
    case REJ_GATE_BUSY:       return "GATE_BUSY";
    case REJ_INVALID_STATE:   return "INVALID_STATE";
    case REJ_GATE_UNKNOWN:    return "GATE_UNKNOWN";
    case REJ_GATE_FAULT:      return "GATE_FAULT";
    case REJ_INVALID_COMMAND: return "INVALID_COMMAND";
    case REJ_INVALID_REQUEST: return "INVALID_REQUEST";
  }
  return "INVALID_REQUEST";
}

static const char* sensorStateText(SensorState s) {   // for LCD
  switch (s) {
    case SENSOR_OK:      return "OK";
    case SENSOR_NO_DATA: return "WAIT";
    case SENSOR_FAILED:  return "FAIL";
  }
  return "FAIL";
}

static const char* sensorStateName(SensorState s) {   // for JSON
  switch (s) {
    case SENSOR_OK:      return "OK";
    case SENSOR_NO_DATA: return "NO_DATA";
    case SENSOR_FAILED:  return "FAILED";
  }
  return "FAILED";
}

static bool gateIsMoving() {
  return gGateState == GATE_OPENING || gGateState == GATE_CLOSING;
}

static bool bmpValid() { return gBmpState == SENSOR_OK; }
static bool dhtValid() { return gDhtState == SENSOR_OK; }

// Single place that maps switch readings to a stationary gate state.
static GateState gateStateFromLimits(bool closedActive, bool openActive) {
  if (closedActive && openActive) return GATE_FAULT;   // contradictory
  if (closedActive) return GATE_CLOSED;
  if (openActive)   return GATE_OPEN;
  return GATE_UNKNOWN;                                  // never assume
}

// ============================================================================
//  SECTION 5: SERIAL COMMUNICATION + JSON SERIALIZATION
// ============================================================================
// Protocol meaning:
//   command_ack accepted=true   -> command accepted (NOT movement completed)
//   gate_status OPENING/CLOSING -> movement started
//   gate_status OPEN/CLOSED     -> movement completed AND endpoint confirmed
//   command_ack accepted=false  -> command rejected, with reason
//   gate_status FAULT           -> fault latched (fault code + switch states)
// The Pi should treat GET_STATUS / telemetry as the source of truth.
// Additive since v1.1.0: boot.startup_limits_settled, status.startup_limits_settled,
// status.limits_established, status.bmp280_state, status.dht11_state, and fault
// strings DEST_BEFORE_RELEASE and SERVO_ATTACH_FAILED.
// Additive since v1.3.1: command_ack carries an extra "fault" field ONLY when
// reason is GATE_FAULT (the fault code that caused the rejection).
// If a servo fails to attach, the gate command is rejected with GATE_FAULT
// (ack.fault = SERVO_ATTACH_FAILED) and is followed by gate_status FAULT
// (fault = SERVO_ATTACH_FAILED). For a contradictory-limits command rejection,
// gate_status FAULT precedes the ack.

static void sendJson(const JsonDocument& doc) {
  if (measureJson(doc) >= TX_MAX_LEN) return;   // never emit truncated JSON
  char buf[TX_MAX_LEN];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  Serial.write((const uint8_t*)buf, n);
  Serial.write('\n');
}

static void setNullableFloat(JsonDocument& doc, const char* key, bool ok, float v) {
  if (ok) doc[key] = round1(v);
  else    doc[key] = nullptr;
}

static void setFault(JsonDocument& doc) {
  const char* f = faultName(gFault);
  if (f) doc["fault"] = f; else doc["fault"] = nullptr;
}

// 'faultForAck' is reported only when reason == REJ_GATE_FAULT.
static void sendAckEx(bool hasId, int32_t id, RejectReason reason, FaultCode faultForAck) {
  JsonDocument doc;
  doc["type"] = "command_ack";
  if (hasId) doc["request_id"] = id; else doc["request_id"] = nullptr;
  doc["accepted"] = (reason == REJ_NONE);
  const char* r = rejectName(reason);
  if (r) doc["reason"] = r; else doc["reason"] = nullptr;
  if (reason == REJ_GATE_FAULT) {
    const char* f = faultName(faultForAck);
    if (f) doc["fault"] = f; else doc["fault"] = nullptr;
  }
  sendJson(doc);
}

static void sendAck(bool hasId, int32_t id, RejectReason reason) {
  sendAckEx(hasId, id, reason, gFault);
}

static void sendGateStatus() {
  JsonDocument doc;
  doc["type"] = "gate_status";
  doc["state"] = gateStateName(gGateState);
  if (gGateState == GATE_FAULT) {            // diagnostics only on fault events
    setFault(doc);
    doc["closed_limit"] = gLimitClosed.stableActive;
    doc["open_limit"] = gLimitOpen.stableActive;
  }
  sendJson(doc);
}

static void sendModeStatus() {
  JsonDocument doc;   // extension message; Pi may ignore it
  doc["type"] = "mode_status";
  doc["mode"] = modeName(gMode);
  doc["pending_standby"] = gPendingStandby;
  sendJson(doc);
}

static void sendBoot() {
  JsonDocument doc;   // extension message so the Pi can detect an ESP32 reboot
  doc["type"] = "boot";
  doc["firmware"] = FIRMWARE_VERSION;
  doc["timestamp_ms"] = millis();
  doc["startup_limits_settled"] = gStartupLimitsSettled;
  sendJson(doc);
}

static void sendStatus(int32_t id) {
  JsonDocument doc;
  doc["type"] = "status";
  doc["request_id"] = id;
  doc["timestamp_ms"] = millis();
  doc["mode"] = modeName(gMode);
  doc["gate_state"] = gateStateName(gGateState);
  doc["closed_limit"] = gLimitClosed.stableActive;
  doc["open_limit"] = gLimitOpen.stableActive;
  setFault(doc);
  doc["pending_standby"] = gPendingStandby;
  doc["startup_limits_settled"] = gStartupLimitsSettled;
  doc["limits_established"] = gLimitsEstablished;
  doc["sensors_polling"] = (gMode == OPMODE_ACTIVE);   // false in STANDBY
  doc["bmp280_ok"] = bmpValid();
  doc["dht11_ok"] = dhtValid();
  doc["bmp280_state"] = sensorStateName(gBmpState);    // OK / NO_DATA / FAILED
  doc["dht11_state"] = sensorStateName(gDhtState);
  doc["firmware"] = FIRMWARE_VERSION;
  sendJson(doc);
}

static void sendTelemetry(uint32_t now) {
  JsonDocument doc;
  doc["type"] = "telemetry";
  doc["timestamp_ms"] = now;   // millis() since boot (wraps ~49.7 days), NOT wall-clock
  doc["mode"] = modeName(gMode);
  doc["gate_state"] = gateStateName(gGateState);
  doc["closed_limit"] = gLimitClosed.stableActive;
  doc["open_limit"] = gLimitOpen.stableActive;
  setNullableFloat(doc, "bmp_temperature_c", bmpValid(), gBmpTemp);
  setNullableFloat(doc, "pressure_hpa",      bmpValid(), gPressure);
  setNullableFloat(doc, "dht_temperature_c", dhtValid(), gDhtTemp);
  setNullableFloat(doc, "humidity_pct",      dhtValid(), gHumidity);
  doc["bmp280_ok"] = bmpValid();
  doc["dht11_ok"] = dhtValid();
  setFault(doc);
  sendJson(doc);
}

// ============================================================================
//  SECTION 6: DEBOUNCED INPUTS (button + limit switches)
// ============================================================================

static bool readActive(uint8_t pin, uint8_t activeLevel) {
  return digitalRead(pin) == activeLevel;
}

static void inputInit(DebouncedInput& in, uint8_t pin, uint8_t activeLevel,
                      uint16_t debounceMs, bool initialStableActive) {
  in.pin = pin;
  in.activeLevel = activeLevel;
  in.debounceMs = debounceMs;
  in.rawActive = readActive(pin, activeLevel);
  in.stableActive = initialStableActive;
  in.lastChangeMs = millis();
  in.transitions = 0;
  in.activatedEdge = false;
}

static void inputUpdate(DebouncedInput& in, uint32_t now) {
  bool raw = readActive(in.pin, in.activeLevel);
  if (raw != in.rawActive) {
    in.rawActive = raw;
    in.lastChangeMs = now;
    in.transitions++;
  } else if (raw != in.stableActive && elapsedSince(now, in.lastChangeMs) >= in.debounceMs) {
    in.stableActive = raw;
    in.transitions++;
    if (raw) in.activatedEdge = true;
  }
}

static void inputsUpdate(uint32_t now) {
  inputUpdate(gLimitOpen, now);
  inputUpdate(gLimitClosed, now);
  inputUpdate(gButton, now);
}

// setup()-only: wait until both limit readings are unchanged for
// STARTUP_STABLE_MS. Returns false if they never settle within
// STARTUP_MAX_WAIT_MS (chatter/noise). Blocks at most STARTUP_MAX_WAIT_MS,
// before the main loop starts; no servo is ever driven here.
static bool startupSettleLimits(bool& openActive, bool& closedActive) {
  uint32_t t0 = millis();
  openActive   = readActive(PIN_LIMIT_OPEN,   LIMIT_ACTIVE_LEVEL);
  closedActive = readActive(PIN_LIMIT_CLOSED, LIMIT_ACTIVE_LEVEL);
  uint32_t stableSince = t0;
  while ((millis() - t0) < STARTUP_MAX_WAIT_MS) {
    delay(1);   // acceptable: setup only
    bool o = readActive(PIN_LIMIT_OPEN,   LIMIT_ACTIVE_LEVEL);
    bool c = readActive(PIN_LIMIT_CLOSED, LIMIT_ACTIVE_LEVEL);
    if (o != openActive || c != closedActive) {
      openActive = o;
      closedActive = c;
      stableSince = millis();
    } else if ((millis() - stableSince) >= STARTUP_STABLE_MS) {
      return true;
    }
  }
  return false;
}

// NOTE: the loop-time recovery timer (limitsRecoveryUpdate) lives in
// SECTION 10 because it needs gateResyncFromLimits().

// ============================================================================
//  SECTION 7: SERVO CONTROL (coordinated pair)
// ============================================================================

static void servoWritePair(float angle) {
  if (angle < 0) angle = 0;
  if (angle > 180) angle = 180;
  int a1 = (int)lroundf(angle);
  int a2 = SERVO2_INVERT ? (180 - a1) : a1;   // simple mirror; may need trim on real hardware
  gServo1.write(a1);
  gServo2.write(a2);
}

static void servoSetup() {
  // Reserve PWM timers only. Servos are NOT attached and NOT driven at boot.
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);
}

// Step 1 of starting a move: make sure BOTH servos are attached. Returns false
// if either failed (both are then detached and neither is commanded, so a
// single servo never moves the shared ramp on its own). Does NOT change the
// gate state and does NOT start the ramp; the caller must NOT commit the move
// on false and must latch FAULT_SERVO_ATTACH. Called only after the starting
// endpoint has been confirmed by a limit switch.
//
// attach() success means a PWM channel was allocated; it does NOT prove a servo
// is connected, powered, or moving. We check attached() (bool attached() exists
// in ESP32Servo 3.x) because the return-value convention of attach() differs
// between versions. Detaching after a failure only stops PWM output from this
// firmware; it is NOT a mechanical safety measure and does not remove servo
// power.
static bool servoPrepare(bool opening) {
  gServoTarget = opening ? (float)SERVO_OPEN_ANGLE : (float)SERVO_CLOSED_ANGLE;
  if (gServosAttached) return true;

  // Defensive: never start from a half-attached state.
  if (gServo1.attached()) gServo1.detach();
  if (gServo2.attached()) gServo2.detach();

  gServo1.setPeriodHertz(50);
  gServo2.setPeriodHertz(50);
  gServo1.attach(PIN_SERVO1, SERVO_MIN_US, SERVO_MAX_US);
  gServo2.attach(PIN_SERVO2, SERVO_MIN_US, SERVO_MAX_US);

  if (!gServo1.attached() || !gServo2.attached()) {
    // Partial or total failure: release BOTH, command NEITHER.
    if (gServo1.attached()) gServo1.detach();
    if (gServo2.attached()) gServo2.detach();
    gServosAttached = false;
    gServoMoving = false;
    return false;
  }

  // LIMITATION: the servo has no position feedback. We ASSUME the horn sits at
  // the angle configured for the confirmed starting endpoint. On first attach
  // the servos move toward that angle at full speed; software ramping does NOT
  // remove this initial jerk. Keep the ramp mechanically free until calibrated.
  gServoAngle = opening ? (float)SERVO_CLOSED_ANGLE : (float)SERVO_OPEN_ANGLE;
  gServosAttached = true;
  servoWritePair(gServoAngle);
  return true;
}

// Both servos always get the same (optionally mirrored) angle, ramped at a
// fixed speed, so they follow one logical movement profile.
static void servoUpdate(uint32_t now) {
  if (!gServosAttached || !gServoMoving) return;
  uint32_t dt = elapsedSince(now, gServoLastMs);
  if (dt < SERVO_UPDATE_MS) return;
  gServoLastMs = now;
  float step = SERVO_SPEED_DEG_S * ((float)dt / 1000.0f);
  float diff = gServoTarget - gServoAngle;
  if (fabsf(diff) <= step) {
    gServoAngle = gServoTarget;
    gServoMoving = false;          // ramp finished; servos keep holding this angle
  } else {
    gServoAngle += (diff > 0) ? step : -step;
  }
  servoWritePair(gServoAngle);
}

// Stops UPDATING the commanded angle (target := current). It does NOT remove
// load, does NOT brake, and does NOT guarantee the ramp cannot move. Unless
// SERVO_DETACH_AFTER_MOVE is true, PWM keeps holding the last commanded angle.
static void servoStop() {
  gServoMoving = false;
  gServoTarget = gServoAngle;
  if (SERVO_DETACH_AFTER_MOVE && gServosAttached) {
    gServo1.detach();
    gServo2.detach();
    gServosAttached = false;
  }
}

// ============================================================================
//  SECTION 8: FAULT HANDLING
// ============================================================================

// Latching: the first fault wins and nothing clears it except a reset.
static void enterFault(FaultCode code) {
  if (gGateState == GATE_FAULT) return;
  servoStop();
  bool hadPending = gPendingStandby;
  gPendingStandby = false;          // movement failed -> FAULT instead of STANDBY
  gFault = code;
  gGateState = GATE_FAULT;
  sendGateStatus();
  if (hadPending) sendModeStatus(); // tell the Pi the standby request was dropped
}

// ============================================================================
//  SECTION 9: SENSOR STATE HELPERS (needed by mode transitions)
// ============================================================================

static void sensorsInvalidate() {
  // Never let old readings be mistaken for current ones.
  gBmpTemp = gPressure = gDhtTemp = gHumidity = NAN;
  if (gBmpInitialized) gBmpState = SENSOR_NO_DATA;   // uninitialised stays FAILED
  gDhtState = SENSOR_NO_DATA;
}

// ============================================================================
//  SECTION 10: GATE CONTROL STATE MACHINE
// ============================================================================

static void setGateState(GateState s) {
  if (gGateState == s) return;
  gGateState = s;
  sendGateStatus();
}

// Stationary state comes ONLY from the debounced switches, and only once the
// limit readings have been established as stable.
static void gateResyncFromLimits() {
  if (gGateState == GATE_FAULT || gateIsMoving()) return;
  if (!gLimitsEstablished) return;   // startup chatter: stay as-is (UNKNOWN) until stable
  GateState target = gateStateFromLimits(gLimitClosed.stableActive, gLimitOpen.stableActive);
  if (target == GATE_FAULT) { enterFault(FAULT_BOTH_LIMITS_ACTIVE); return; }
  setGateState(target);
}

// Loop-time recovery after a failed startup settle. Explicit timer:
//  - it runs only while BOTH limit inputs are synchronised (raw == debounced);
//  - any input still debouncing stops it (reset);
//  - any transition on either input (raw or debounced change, tracked by the
//    transition counters) restarts it from now;
//  - only when it has run the full LIMIT_RECOVERY_STABLE_MS are the limits
//    "established". Then the gate state is derived strictly from the switches
//    by gateResyncFromLimits(): exactly one active -> that endpoint, neither
//    -> UNKNOWN, both -> latched FAULT_BOTH_LIMITS_ACTIVE.
// Elapsed time alone never establishes an endpoint, and no servo is touched
// here: recovery never moves the gate. Once established it stays so; later
// changes are handled by ordinary debouncing.
static void limitsRecoveryUpdate(uint32_t now) {
  if (gLimitsEstablished) return;

  const bool synced = (gLimitOpen.rawActive   == gLimitOpen.stableActive) &&
                      (gLimitClosed.rawActive == gLimitClosed.stableActive);
  if (!synced) {                       // still debouncing: window cannot run
    gRecTimerRunning = false;
    return;
  }
  if (!gRecTimerRunning ||
      gLimitOpen.transitions   != gRecOpenTrans ||
      gLimitClosed.transitions != gRecClosedTrans) {
    gRecTimerRunning = true;           // (re)start the window from now
    gRecStartMs      = millis();
    gRecOpenTrans    = gLimitOpen.transitions;
    gRecClosedTrans  = gLimitClosed.transitions;
    return;
  }
  if (elapsedSince(now, gRecStartMs) >= LIMIT_RECOVERY_STABLE_MS) {
    gLimitsEstablished = true;
    gRecTimerRunning = false;
    gateResyncFromLimits();            // state from switches only; NO movement
  }
}

// Called before any gate command or button press is evaluated: if the stable
// switch readings are contradictory while the gate is stationary, latch the
// fault NOW so no movement can be accepted against it.
static void gateLatchContradiction() {
  if (gGateState == GATE_FAULT || gateIsMoving()) return;
  if (!gLimitsEstablished) return;   // recovery window not complete yet
  if (gLimitClosed.stableActive && gLimitOpen.stableActive) {
    enterFault(FAULT_BOTH_LIMITS_ACTIVE);
  }
}

// Side-effect-free validation (ack is sent before movement state events).
static RejectReason validateGateMove(bool opening) {
  const bool c = gLimitClosed.stableActive;
  const bool o = gLimitOpen.stableActive;
  if (gMode != OPMODE_ACTIVE)              return REJ_INVALID_STATE;
  if (gateIsMoving() || gPendingStandby)   return REJ_GATE_BUSY;
  if (gGateState == GATE_FAULT)            return REJ_GATE_FAULT;
  if (!gLimitsEstablished)                 return REJ_GATE_UNKNOWN;  // switches not yet stable
  if (c && o)                              return REJ_GATE_FAULT;    // backstop; callers latch it first
  if (gGateState == GATE_UNKNOWN)          return REJ_GATE_UNKNOWN;
  if (opening  && gGateState != GATE_CLOSED) return REJ_INVALID_STATE;
  if (!opening && gGateState != GATE_OPEN)   return REJ_INVALID_STATE;
  // Re-check the switches themselves: the start endpoint must still be
  // confirmed and the destination must NOT already be active.
  const bool startActive = opening ? c : o;
  const bool destActive  = opening ? o : c;
  if (!startActive || destActive)          return REJ_GATE_UNKNOWN;
  return REJ_NONE;
}

// Step 2 of starting a move. Precondition: validateGateMove() returned REJ_NONE
// AND servoPrepare() returned true. Only here does the gate report movement.
static void commitMove(bool opening) {
  const uint32_t startMs = millis();
  gMoveStartMs = startMs;
  gStartReleased = false;
  gServoMoving = true;
  gServoLastMs = startMs;
  setGateState(opening ? GATE_OPENING : GATE_CLOSING);
}

// Used by the physical button (no ack involved).
static void startMoveNow(bool opening) {
  if (!servoPrepare(opening)) { enterFault(FAULT_SERVO_ATTACH); return; }
  commitMove(opening);
}

static void enterStandby() {
  gMode = OPMODE_STANDBY;
  gPendingStandby = false;
  gButton.activatedEdge = false;
  sensorsInvalidate();               // no stale data across standby
  sendModeStatus();
}

static void enterActive() {
  gMode = OPMODE_ACTIVE;
  gPendingStandby = false;
  gButton.activatedEdge = false;
  gateResyncFromLimits();            // re-read switches; NO movement
  sensorsInvalidate();
  gNextSensorPollMs = millis();      // poll immediately (before the next telemetry)
  gNextTelemetryMs = millis() + 100;
  gLcdScreen = 0;
  gLcdScreenSinceMs = millis();
  sendModeStatus();
}

static void gateUpdateMovement(uint32_t now) {
  const bool opening = (gGateState == GATE_OPENING);
  const bool c = gLimitClosed.stableActive;
  const bool o = gLimitOpen.stableActive;
  const bool startActive = opening ? c : o;
  const bool destActive  = opening ? o : c;
  const uint32_t moveElapsed = elapsedSince(now, gMoveStartMs);

  // 1. Both switches active: latch FAULT, no reversal, no retry. Report WHICH
  //    situation it is:
  //    - start switch never seen released -> the destination became active
  //      while the start switch was still active (stuck/mis-wired switch, or
  //      mechanism bridging both). Specific fault: DEST_BEFORE_RELEASE.
  //    - start switch had released earlier -> generic contradictory readings.
  if (c && o) {
    enterFault(gStartReleased ? FAULT_LIMIT_CONFLICT : FAULT_DEST_BEFORE_RELEASE);
    return;
  }

  // 2. Track the start switch.
  if (!startActive) {
    gStartReleased = true;
  } else if (gStartReleased && FAULT_ON_START_REACTIVATION) {
    enterFault(FAULT_START_REACTIVATED);
    return;
  }

  // 3. Destination confirmed. Not both-active (step 1), so the start switch is
  //    inactive here and gStartReleased is true: release was observed during
  //    this move (possibly in the same loop pass as the destination, which
  //    debounce cannot separate). Never accepted from timing or angle alone.
  if (destActive) {
    servoStop();
    setGateState(opening ? GATE_OPEN : GATE_CLOSED);
    if (gPendingStandby) enterStandby();
    return;
  }

  // 4. Start switch must release within its own configurable timeout.
  if (!gStartReleased && moveElapsed >= START_RELEASE_TIMEOUT_MS) {
    enterFault(FAULT_START_NOT_RELEASED);
    return;
  }

  // 5. Overall movement timeout (no retry, no reversal).
  if (moveElapsed >= MOVE_TIMEOUT_MS) {
    enterFault(opening ? FAULT_OPEN_TIMEOUT : FAULT_CLOSE_TIMEOUT);
    return;
  }

  servoUpdate(now);
}

static void gateUpdate(uint32_t now) {
  if (gateIsMoving()) gateUpdateMovement(now);
  else gateResyncFromLimits();
}

// ============================================================================
//  SECTION 11: PHYSICAL BUTTON
// ============================================================================

static void buttonUpdate() {
  if (!gButton.activatedEdge) return;
  gButton.activatedEdge = false;                 // always consume: presses are never queued
  if (gMode != OPMODE_ACTIVE) return;            // STANDBY: disabled
  if (gPendingStandby || gateIsMoving()) return;
  gateLatchContradiction();                      // contradictory limits -> FAULT before any move
  if (gGateState == GATE_CLOSED && validateGateMove(true) == REJ_NONE) startMoveNow(true);
  else if (gGateState == GATE_OPEN && validateGateMove(false) == REJ_NONE) startMoveNow(false);
  // UNKNOWN / FAULT: ignored
}

// ============================================================================
//  SECTION 12: COMMAND PROCESSING
// ============================================================================

static void handleGateCommand(bool opening, int32_t id) {
  gateLatchContradiction();                      // latch first so ack and state agree
  RejectReason r = validateGateMove(opening);
  bool servoFail = false;
  if (r == REJ_NONE && !servoPrepare(opening)) {
    servoFail = true;
    r = REJ_GATE_FAULT;                          // existing reason; fault code is in ack.fault
  }
  if (servoFail) {
    // Rejected: the move is NOT committed. Ack first (carrying the fault that
    // is about to be latched), then the latched gate_status FAULT event.
    sendAckEx(true, id, REJ_GATE_FAULT, FAULT_SERVO_ATTACH);
    enterFault(FAULT_SERVO_ATTACH);
    return;
  }
  sendAck(true, id, r);                          // acceptance, NOT completion
  if (r == REJ_NONE) commitMove(opening);
}

static void handleCommand(const char* cmd, int32_t id) {
  if (strcmp(cmd, "OPEN_GATE") == 0) {
    handleGateCommand(true, id);
  } else if (strcmp(cmd, "CLOSE_GATE") == 0) {
    handleGateCommand(false, id);
  } else if (strcmp(cmd, "SET_ACTIVE") == 0) {
    sendAck(true, id, REJ_NONE);
    if (gMode == OPMODE_STANDBY) enterActive();
    else if (gPendingStandby) { gPendingStandby = false; sendModeStatus(); }  // cancels pending standby
  } else if (strcmp(cmd, "SET_STANDBY") == 0) {
    sendAck(true, id, REJ_NONE);
    if (gMode == OPMODE_ACTIVE) {
      if (gateIsMoving()) { gPendingStandby = true; sendModeStatus(); }
      else enterStandby();
    }
  } else if (strcmp(cmd, "GET_STATUS") == 0) {
    sendAck(true, id, REJ_NONE);
    sendStatus(id);
  } else {
    sendAck(true, id, REJ_INVALID_COMMAND);
  }
}

static void processLine(const char* line, size_t len) {
  JsonDocument doc;
  DeserializationError err =
      deserializeJson(doc, line, len, DeserializationOption::NestingLimit(4));
  if (err || !doc.is<JsonObject>()) {
    sendAck(false, 0, REJ_INVALID_REQUEST);
    return;
  }
  bool hasId = doc["request_id"].is<int32_t>();
  int32_t id = hasId ? doc["request_id"].as<int32_t>() : 0;
  const char* cmd = doc["command"].as<const char*>();   // nullptr if missing / not a string
  if (!hasId || cmd == nullptr) {
    sendAck(hasId, id, REJ_INVALID_REQUEST);
    return;
  }
  gLinkSeen = true;
  gLastValidCmdMs = millis();
  handleCommand(cmd, id);
}

static void serialPoll() {
  int budget = 256;   // bound work per loop iteration
  while (Serial.available() > 0 && budget-- > 0) {
    int c = Serial.read();
    if (c < 0) break;
    if (c == '\n') {
      if (gRxOverflow) {
        sendAck(false, 0, REJ_INVALID_REQUEST);
      } else if (gRxLen > 0) {
        gRxBuf[gRxLen] = '\0';
        processLine(gRxBuf, gRxLen);
      }
      gRxLen = 0;
      gRxOverflow = false;
    } else if (c == '\r') {
      // ignore
    } else if (gRxOverflow) {
      // discard until newline
    } else if (gRxLen < RX_MAX_LEN) {
      gRxBuf[gRxLen++] = (char)c;
    } else {
      gRxOverflow = true;
    }
  }
}

// ============================================================================
//  SECTION 13: SENSOR MANAGEMENT
// ============================================================================

// Records the attempt time; next attempt is BMP_RETRY_MS after THIS attempt.
static bool bmpTryInit(uint32_t now) {
  bool ok = gBmp.begin(BMP280_ADDR_A) || gBmp.begin(BMP280_ADDR_B);
  gNextBmpInitMs = now + BMP_RETRY_MS;
  return ok;
}

static void bmpMarkFailed() {
  gBmpState = SENSOR_FAILED;
  gBmpTemp = NAN;
  gPressure = NAN;
}

// Recovery strategy (simple and explicit): an invalid reading marks the sensor
// FAILED and uninitialised; initialisation is retried every BMP_RETRY_MS (from
// the previous attempt) while ACTIVE. A successful read returns it to OK.
static void pollBmp(uint32_t now) {
  if (!gBmpInitialized) {
    if (!timeReached(now, gNextBmpInitMs)) { bmpMarkFailed(); return; }
    gBmpInitialized = bmpTryInit(now);
    if (!gBmpInitialized) { bmpMarkFailed(); return; }
  }
  float t = gBmp.readTemperature();
  float p = gBmp.readPressure() / 100.0f;   // Pa -> hPa
  if (isnan(t) || isnan(p) || t < BMP_TEMP_MIN_C || t > BMP_TEMP_MAX_C ||
      p < BMP_PRES_MIN_HPA || p > BMP_PRES_MAX_HPA) {
    bmpMarkFailed();
    gBmpInitialized = false;
    gNextBmpInitMs = now + BMP_RETRY_MS;
    return;
  }
  gBmpTemp = t;
  gPressure = p;
  gBmpState = SENSOR_OK;
}

// DHT11: a bad poll marks FAILED immediately (values cleared); the next valid
// poll restores OK. NO_DATA only means "not polled yet this ACTIVE session".
static void pollDht() {
  float h = gDht.readHumidity();      // library blocks briefly (~tens of ms)
  float t = gDht.readTemperature();
  if (isnan(t) || isnan(h) || t < DHT_TEMP_MIN_C || t > DHT_TEMP_MAX_C ||
      h < DHT_HUM_MIN_PCT || h > DHT_HUM_MAX_PCT) {
    gDhtState = SENSOR_FAILED;
    gDhtTemp = NAN;
    gHumidity = NAN;
    return;
  }
  gDhtTemp = t;
  gHumidity = h;
  gDhtState = SENSOR_OK;
}

static void sensorsUpdate(uint32_t now) {
  if (gMode != OPMODE_ACTIVE) return;          // no polling in STANDBY
  if (!timeReached(now, gNextSensorPollMs)) return;
  gNextSensorPollMs = now + SENSOR_POLL_MS;
  pollBmp(now);
  pollDht();
}

static void telemetryUpdate(uint32_t now) {
  if (gMode != OPMODE_ACTIVE) return;          // no sensor telemetry in STANDBY
  if (!timeReached(now, gNextTelemetryMs)) return;
  gNextTelemetryMs = now + TELEMETRY_MS;
  sendTelemetry(now);
}

// ============================================================================
//  SECTION 14: LCD MANAGEMENT
// ============================================================================

static void lcdSet(uint8_t row, const char* fmt, ...) {
  char tmp[48];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(tmp, sizeof(tmp), fmt, ap);
  va_end(ap);
  memset(gLcdLines[row], ' ', LCD_COLS);
  gLcdLines[row][LCD_COLS] = '\0';
  size_t n = strlen(tmp);
  if (n > LCD_COLS) n = LCD_COLS;
  memcpy(gLcdLines[row], tmp, n);
}

static void lcdScreenStatus() {
  const char* sys = (gFault != FAULT_NONE) ? "FAULT"
                  : gateIsMoving() ? "MOVING"
                  : !gLimitsEstablished ? "LIMIT NOISE"
                  : (gGateState == GATE_UNKNOWN) ? "GATE UNKNOWN" : "READY";
  lcdSet(0, "MARS LANDER");
  lcdSet(1, "MODE: %s", modeName(gMode));
  lcdSet(2, "GATE: %s", gateStateName(gGateState));
  lcdSet(3, "SYSTEM: %s", sys);
}

static void lcdScreenBmp() {
  lcdSet(0, "BMP280 SENSOR");
  if (bmpValid()) {
    lcdSet(1, "Temp: %.1f C", gBmpTemp);
    lcdSet(2, "Pres: %.1f hPa", gPressure);
  } else {
    lcdSet(1, "Temp: --");
    lcdSet(2, "Pres: --");
  }
  lcdSet(3, "Health: %s", sensorStateText(gBmpState));
}

static void lcdScreenDht() {
  lcdSet(0, "DHT11 SENSOR");
  if (dhtValid()) {
    lcdSet(1, "Temp: %.1f C", gDhtTemp);
    lcdSet(2, "Humidity: %.0f %%", gHumidity);
  } else {
    lcdSet(1, "Temp: --");
    lcdSet(2, "Humidity: --");
  }
  lcdSet(3, "Health: %s", sensorStateText(gDhtState));
}

static void lcdScreenMission(uint32_t now) {
  // Rover/drone data is not available to the ESP32 (no serial command for it),
  // so it is shown as WAITING rather than invented.
  const char* link = !gLinkSeen ? "WAITING"
                   : (elapsedSince(now, gLastValidCmdMs) <= LINK_TIMEOUT_MS ? "LINK OK" : "LINK LOST");
  lcdSet(0, "MISSION STATUS");
  lcdSet(1, "ROVER: WAITING");
  lcdSet(2, "DRONE: WAITING");
  lcdSet(3, "USB: %s", link);
}

static void lcdScreenStandby() {
  const char* f = faultName(gFault);
  lcdSet(0, "STANDBY MODE");
  lcdSet(1, "GATE: %s", gateStateName(gGateState));
  if (f) lcdSet(2, "%s", f);
  else   lcdSet(2, "Sensors: PAUSED");
  lcdSet(3, "Send SET_ACTIVE");
}

static void lcdScreenFault() {
  const char* f = faultName(gFault);
  lcdSet(0, "!! GATE FAULT !!");
  lcdSet(1, "%s", f ? f : "UNKNOWN");
  lcdSet(2, "Gate motion locked");
  lcdSet(3, "Reset ESP32 to clear");
}

static void lcdBuild(uint32_t now) {
  if (gMode == OPMODE_STANDBY) { lcdScreenStandby(); return; }
  if (gFault != FAULT_NONE)    { lcdScreenFault(); gLcdScreenSinceMs = now; return; }
  if (gateIsMoving())          { lcdScreenStatus(); gLcdScreenSinceMs = now; return; }

  if (elapsedSince(now, gLcdScreenSinceMs) >= LCD_ROTATE_MS) {
    gLcdScreen = (gLcdScreen + 1) % 4;
    gLcdScreenSinceMs = now;
  }
  switch (gLcdScreen) {
    case 0: lcdScreenStatus(); break;
    case 1: lcdScreenBmp(); break;
    case 2: lcdScreenDht(); break;
    default: lcdScreenMission(now); break;
  }
}

// Writes at most ONE changed row per call so I2C time never starves the loop.
static void lcdRefresh(uint32_t now) {
  if (!gLcdOk) return;
  if (elapsedSince(now, gLcdLastWriteMs) < LCD_ROW_INTERVAL_MS) return;
  lcdBuild(now);
  for (uint8_t r = 0; r < LCD_ROWS; r++) {
    if (!gLcdShadowValid || memcmp(gLcdLines[r], gLcdShadow[r], LCD_COLS) != 0) {
      gLcd.setCursor(0, r);
      gLcd.print(gLcdLines[r]);
      memcpy(gLcdShadow[r], gLcdLines[r], LCD_COLS + 1);
      gLcdLastWriteMs = now;
      if (r == LCD_ROWS - 1) gLcdShadowValid = true;
      return;
    }
  }
  gLcdShadowValid = true;
}

// An ACK at the address proves only that SOMETHING answers there, not that it
// is the right display. If nothing answers, the LCD is skipped (no retry).
static void lcdSetup() {
  Wire.beginTransmission(LCD_I2C_ADDR);
  gLcdOk = (Wire.endTransmission() == 0);
  if (!gLcdOk) return;
  gLcd.init();
  gLcd.backlight();
  gLcd.clear();
  gLcdShadowValid = false;
}

// ============================================================================
//  SECTION 15: STATUS LEDs
// ============================================================================

static void ledUpdate(uint32_t now) {
  bool green = (gMode == OPMODE_ACTIVE) && (gFault == FAULT_NONE);
  bool red = false;
  if (gMode == OPMODE_ACTIVE) {
    if (gateIsMoving()) {
      red = (now % RED_MOVE_PERIOD_MS) < RED_MOVE_ON_MS;
    } else if (gFault != FAULT_NONE) {
      uint32_t p = now % RED_FAULT_PERIOD_MS;   // double blink
      red = (p < RED_FAULT_PULSE_MS) ||
            (p >= 2 * RED_FAULT_PULSE_MS && p < 3 * RED_FAULT_PULSE_MS);
    }
  }
  digitalWrite(PIN_LED_GREEN, green ? HIGH : LOW);
  digitalWrite(PIN_LED_RED, red ? HIGH : LOW);   // both OFF in STANDBY (even with a fault)
}

// ============================================================================
//  SECTION 16: WS2812B ANIMATION (runs in ACTIVE and STANDBY)
// ============================================================================

static void animationUpdate(uint32_t now) {
  if ((now - gLastAnimMs) < ANIM_INTERVAL_MS) return;
  gLastAnimMs = now;
  float t = (float)now * 0.001f;

  if (random(0, STAR_SPAWN_ODDS) == 0) gStar[random(0, NUM_LEDS)] = 255;

  for (uint16_t i = 0; i < NUM_LEDS; i++) {
    float w1 = sinf(t * 0.35f + (float)i * 0.30f);
    float w2 = sinf(t * 0.60f - (float)i * 0.22f);
    uint16_t hue = (uint16_t)(HUE_CENTER + HUE_SPREAD * w1);
    uint8_t  val = (uint8_t)(VAL_MID + VAL_SWING * w2);
    uint32_t c = gStrip.ColorHSV(hue, 255, val);
    uint8_t r = (c >> 16) & 0xFF, g = (c >> 8) & 0xFF, b = c & 0xFF;

    uint8_t s = gStar[i];
    if (s) {
      r = r + (uint8_t)(((uint16_t)(255 - r) * s) >> 8);
      g = g + (uint8_t)(((uint16_t)(255 - g) * s) >> 8);
      b = b + (uint8_t)(((uint16_t)(255 - b) * s) >> 8);
      gStar[i] = (s > STAR_DECAY) ? (s - STAR_DECAY) : 0;
    }
    gStrip.setPixelColor(i, r, g, b);
  }
  gStrip.show();
}

// ============================================================================
//  SECTION 17: setup()
// ============================================================================

void setup() {
  Serial.setRxBufferSize(512);
  Serial.begin(SERIAL_BAUD);

  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  digitalWrite(PIN_LED_GREEN, LOW);
  digitalWrite(PIN_LED_RED, LOW);

  pinMode(PIN_GATE_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LIMIT_OPEN, INPUT_PULLUP);
  pinMode(PIN_LIMIT_CLOSED, INPUT_PULLUP);

  // Debounced startup read of the limit switches, with the outcome recorded.
  bool openA = false, closedA = false;
  gStartupLimitsSettled = startupSettleLimits(openA, closedA);
  gLimitsEstablished    = gStartupLimitsSettled;
  gRecTimerRunning      = false;
  // If the readings never settled, both limits start as inactive (conservative)
  // and the gate stays UNKNOWN, with movement disabled, until
  // limitsRecoveryUpdate() sees both inputs synchronised and unchanged for
  // LIMIT_RECOVERY_STABLE_MS.
  inputInit(gLimitOpen,   PIN_LIMIT_OPEN,   LIMIT_ACTIVE_LEVEL,  LIMIT_DEBOUNCE_MS,
            gStartupLimitsSettled ? openA : false);
  inputInit(gLimitClosed, PIN_LIMIT_CLOSED, LIMIT_ACTIVE_LEVEL,  LIMIT_DEBOUNCE_MS,
            gStartupLimitsSettled ? closedA : false);
  inputInit(gButton,      PIN_GATE_BUTTON,  BUTTON_ACTIVE_LEVEL, BUTTON_DEBOUNCE_MS,
            readActive(PIN_GATE_BUTTON, BUTTON_ACTIVE_LEVEL));   // held at boot -> no edge

  servoSetup();   // timers only; servos are NOT attached or driven at boot

  gStrip.begin();
  gStrip.setBrightness(STRIP_BRIGHTNESS);
  gStrip.clear();
  gStrip.show();
  memset(gStar, 0, sizeof(gStar));

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(I2C_CLOCK_HZ);
  Wire.setTimeOut(I2C_TIMEOUT_MS);
  lcdSetup();

  gBmpInitialized = bmpTryInit(millis());          // records attempt time
  gBmpState = gBmpInitialized ? SENSOR_NO_DATA : SENSOR_FAILED;
  gDht.begin();
  gDhtState = SENSOR_NO_DATA;
  gNextSensorPollMs = millis() + SENSOR_FIRST_POLL_MS;
  gNextTelemetryMs  = gNextSensorPollMs;           // loop() polls before telemetry

  // Startup gate state from debounced switches ONLY. No movement, no servo use.
  if (gStartupLimitsSettled) {
    gGateState = gateStateFromLimits(gLimitClosed.stableActive, gLimitOpen.stableActive);
    if (gGateState == GATE_FAULT) gFault = FAULT_BOTH_LIMITS_ACTIVE;
  } else {
    gGateState = GATE_UNKNOWN;   // chatter at boot: never assume an endpoint
  }

  gMode = OPMODE_ACTIVE;
  gLcdScreenSinceMs = millis();
  sendBoot();
  sendGateStatus();
}

// ============================================================================
//  SECTION 18: loop()   (non-blocking; no delay())
// ============================================================================

void loop() {
  uint32_t now = millis();

  inputsUpdate(now);
  limitsRecoveryUpdate(now);
  serialPoll();
  buttonUpdate();
  gateUpdate(now);
  sensorsUpdate(now);
  telemetryUpdate(now);
  ledUpdate(now);
  lcdRefresh(now);
  animationUpdate(now);
}