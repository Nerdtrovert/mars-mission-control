/*
 * Mars lander ESP32 firmware, sensor and status baseline.   v1.4.0
 * ESP32 DevKit V1; lander telemetry and status commands use a local Wi-Fi TCP
 * connection to the Raspberry Pi. USB serial is for programming/debug text
 * ONLY; no operational JSON is written to it.
 * Hardware has not been physically tested. This source has NOT been compiled
 * by the author of this change (no ESP32 toolchain was available).
 *
 * Arduino libraries: ArduinoJson 7, Adafruit BMP280, Adafruit Unified Sensor,
 * Adafruit BusIO, Adafruit DHT sensor, Adafruit NeoPixel, LiquidCrystal_I2C.
 * (WiFi and Wire come with the ESP32 Arduino core.)
 *
 * ALL configuration lives in this file (SECTION 1). There is no external
 * config header. Do not commit real Wi-Fi credentials to version control.
 *
 * PIN OWNERSHIP (each GPIO is used by exactly one peripheral signal):
 *   GPIO17 DHT11 data        GPIO25 green LED     GPIO26 red LED
 *   GPIO27 WS2812B data      GPIO21 I2C SDA       GPIO22 I2C SCL
 * The I2C bus (21/22) is shared BY DESIGN between the LCD and the BMP280:
 * that is what I2C is for. They are compatible only if their addresses differ
 * (LCD 0x27 or 0x3F; BMP280 0x76 or 0x77). Verify with an I2C scan.
 * Ramp/motor/limit-switch/button functionality is removed; GPIO 18, 19, 23,
 * 32, 33 are therefore unused by this firmware.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <math.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>
#include <Adafruit_NeoPixel.h>
#include <LiquidCrystal_I2C.h>

// ============================================================================
//  SECTION 1: CONFIGURATION (everything lives here)
// ============================================================================

#define FIRMWARE_VERSION "1.4.0"
#define DHT_TYPE DHT11

// ---- Wi-Fi / gateway (FILL IN BEFORE USE) ----------------------------------
// While SSID or host is empty, Wi-Fi/TCP is skipped and the lander still runs
// its sensors, LCD, LEDs and animation locally.
static const char*    WIFI_SSID     = "Mission Control";       // <-- your 2.4 GHz network name
static const char*    WIFI_PASSWORD = "mission@mars";       // <-- your Wi-Fi password
static const char*    GATEWAY_HOST  = "192.168.50.1";       // <-- Raspberry Pi IP or hostname
static const uint16_t GATEWAY_PORT  = 5006;     // Pi TCP listener port

// ---- GPIO assignments (distinct pins, one peripheral per pin) --------------
static const uint8_t PIN_LED_GREEN = 25;
static const uint8_t PIN_LED_RED   = 26;
static const uint8_t PIN_WS2812    = 27;
static const uint8_t PIN_I2C_SDA   = 21;   // shared bus: LCD + BMP280
static const uint8_t PIN_I2C_SCL   = 22;   // shared bus: LCD + BMP280
static const uint8_t PIN_DHT       = 17;

// ---- I2C / LCD -------------------------------------------------------------
static const uint8_t  LCD_I2C_ADDR   = 0x27;   // PROVISIONAL: many backpacks use 0x3F
static const uint8_t  LCD_COLS       = 20;
static const uint8_t  LCD_ROWS       = 4;
static const uint8_t  BMP280_ADDR_A  = 0x76;
static const uint8_t  BMP280_ADDR_B  = 0x77;
static const uint32_t I2C_CLOCK_HZ   = 100000;
static const uint16_t I2C_TIMEOUT_MS = 30;

// ---- Timing ----------------------------------------------------------------
static const uint32_t DEBUG_BAUD           = 115200;  // USB serial: debug only
static const uint32_t SENSOR_POLL_MS       = 2000;
static const uint32_t SENSOR_FIRST_POLL_MS = 1000;
static const uint32_t BMP_RETRY_MS         = 10000;
static const uint32_t TELEMETRY_MS         = 1000;
static const uint32_t LCD_ROTATE_MS        = 6000;
static const uint32_t WIFI_RETRY_MS        = 5000;
static const uint32_t TCP_RETRY_MS         = 1000;
static const uint16_t TCP_CONNECT_TIMEOUT_MS = 50;   // blocks up to this long per attempt
static const uint32_t ANIM_INTERVAL_MS     = 40;

// ---- WS2812B ---------------------------------------------------------------
static const uint8_t NUM_LEDS         = 30;   // PROVISIONAL (approx. 1 m strip)
static const uint8_t STRIP_BRIGHTNESS = 60;   // PROVISIONAL

// ---- Sensor validity ranges ------------------------------------------------
static const float BMP_TEMP_MIN_C = -40.0f, BMP_TEMP_MAX_C = 85.0f;
static const float BMP_PRESS_MIN_HPA = 300.0f, BMP_PRESS_MAX_HPA = 1100.0f;
static const float DHT_TEMP_MIN_C = 0.0f, DHT_TEMP_MAX_C = 50.0f;
static const float DHT_HUM_MIN_PCT = 0.0f, DHT_HUM_MAX_PCT = 100.0f;

// ============================================================================
//  SECTION 2: STATE
// ============================================================================

enum OperatingMode : uint8_t { OPMODE_ACTIVE, OPMODE_STANDBY };
enum SensorState : uint8_t { SENSOR_NO_DATA, SENSOR_OK, SENSOR_FAILED };

static OperatingMode gMode = OPMODE_ACTIVE;
static SensorState gBmpState = SENSOR_NO_DATA;
static SensorState gDhtState = SENSOR_NO_DATA;
static bool gBmpReady = false;
static bool gLcdOk = false;
static uint32_t gLastBmpAttempt = 0;
static uint32_t gLastSensorPoll = 0;
static uint32_t gLastTelemetry = 0;
static uint32_t gLastLcdRotate = 0;
static uint32_t gLastAnimation = 0;
static uint32_t gLastWiFiRetry = 0;
static uint32_t gLastTcpRetry = 0;
static bool gWiFiStarted = false;
static bool gWiFiConfigNoted = false;
static char gCommandBuffer[256];
static size_t gCommandLength = 0;
static uint8_t gLcdPage = 0;
static bool gLcdNeedsRefresh = true;
static uint32_t gClockStart = 0;
static float gBmpTemp = NAN, gPressure = NAN, gDhtTemp = NAN, gHumidity = NAN;

static Adafruit_BMP280 gBmp;
static DHT gDht(PIN_DHT, DHT_TYPE);
static LiquidCrystal_I2C gLcd(LCD_I2C_ADDR, LCD_COLS, LCD_ROWS);
static Adafruit_NeoPixel gStrip(NUM_LEDS, PIN_WS2812, NEO_GRB + NEO_KHZ800);
static WiFiClient gGatewayClient;

// ============================================================================
//  SECTION 3: HELPERS AND OUTPUT
// ============================================================================

static const char* modeName(OperatingMode mode) {
  return mode == OPMODE_ACTIVE ? "ACTIVE" : "STANDBY";
}

static const char* sensorStateName(SensorState state) {
  switch (state) {
    case SENSOR_OK: return "OK";
    case SENSOR_FAILED: return "FAILED";
    default: return "NO_DATA";
  }
}

static bool finiteInRange(float value, float low, float high) {
  return isfinite(value) && value >= low && value <= high;
}

static bool wifiConfigured() {
  return WIFI_SSID[0] != '\0' && GATEWAY_HOST[0] != '\0';
}

// Operational JSON goes to the Wi-Fi/TCP gateway ONLY. USB serial carries
// human-readable debug text only (see debugLog).
static void sendJson(JsonDocument& doc) {
  if (!gGatewayClient.connected()) return;
  serializeJson(doc, gGatewayClient);
  gGatewayClient.print('\n');
}

static void debugLog(const char* msg) {
  Serial.print("[lander] ");
  Serial.println(msg);
}

static void setNullableFloat(JsonDocument& doc, const char* key, bool ok, float value) {
  if (ok && isfinite(value)) doc[key] = value;
  else doc[key] = nullptr;
}

static void sendAck(int32_t requestId, bool hasId, bool accepted, const char* reason = nullptr) {
  JsonDocument doc;
  doc["type"] = "command_ack";
  if (hasId) doc["request_id"] = requestId;
  doc["accepted"] = accepted;
  if (reason) doc["reason"] = reason;
  else doc["reason"] = nullptr;
  sendJson(doc);
}

static void sendModeStatus(int32_t requestId, bool hasId) {
  JsonDocument doc;
  doc["type"] = "mode_status";
  if (hasId) doc["request_id"] = requestId;
  doc["mode"] = modeName(gMode);
  sendJson(doc);
}

static void sendStatus(int32_t requestId, bool hasId) {
  JsonDocument doc;
  doc["type"] = "status";
  if (hasId) doc["request_id"] = requestId;
  doc["timestamp_ms"] = millis() - gClockStart;
  doc["mode"] = modeName(gMode);
  doc["sensors_polling"] = gMode == OPMODE_ACTIVE;
  doc["bmp280_ok"] = gBmpState == SENSOR_OK;
  doc["dht11_ok"] = gDhtState == SENSOR_OK;
  doc["bmp280_state"] = sensorStateName(gBmpState);
  doc["dht11_state"] = sensorStateName(gDhtState);
  doc["firmware"] = FIRMWARE_VERSION;
  sendJson(doc);
}

static void sendTelemetry(uint32_t now) {
  JsonDocument doc;
  doc["type"] = "telemetry";
  doc["timestamp_ms"] = now - gClockStart;
  doc["mode"] = modeName(gMode);
  setNullableFloat(doc, "bmp_temperature_c", gBmpState == SENSOR_OK, gBmpTemp);
  setNullableFloat(doc, "pressure_hpa", gBmpState == SENSOR_OK, gPressure);
  setNullableFloat(doc, "dht_temperature_c", gDhtState == SENSOR_OK, gDhtTemp);
  setNullableFloat(doc, "humidity_pct", gDhtState == SENSOR_OK, gHumidity);
  doc["bmp280_ok"] = gBmpState == SENSOR_OK;
  doc["dht11_ok"] = gDhtState == SENSOR_OK;
  sendJson(doc);
}

// ============================================================================
//  SECTION 4: SENSORS
// ============================================================================

static void pollSensors(uint32_t now) {
  if (gMode != OPMODE_ACTIVE) return;
  if (!gBmpReady && (gLastBmpAttempt == 0 || now - gLastBmpAttempt >= BMP_RETRY_MS)) {
    gLastBmpAttempt = now;
    gBmpReady = gBmp.begin(BMP280_ADDR_A) || gBmp.begin(BMP280_ADDR_B);
    if (!gBmpReady) gBmpState = SENSOR_FAILED;
  }
  if (gBmpReady) {
    const float temperature = gBmp.readTemperature();
    const float pressure = gBmp.readPressure() / 100.0f;
    if (finiteInRange(temperature, BMP_TEMP_MIN_C, BMP_TEMP_MAX_C) &&
        finiteInRange(pressure, BMP_PRESS_MIN_HPA, BMP_PRESS_MAX_HPA)) {
      gBmpTemp = roundf(temperature * 10.0f) / 10.0f;
      gPressure = roundf(pressure * 10.0f) / 10.0f;
      gBmpState = SENSOR_OK;
    } else {
      gBmpTemp = gPressure = NAN;
      gBmpState = SENSOR_FAILED;
      gBmpReady = false;
    }
  }
  const float temperature = gDht.readTemperature();
  const float humidity = gDht.readHumidity();
  if (finiteInRange(temperature, DHT_TEMP_MIN_C, DHT_TEMP_MAX_C) &&
      finiteInRange(humidity, DHT_HUM_MIN_PCT, DHT_HUM_MAX_PCT)) {
    gDhtTemp = roundf(temperature * 10.0f) / 10.0f;
    gHumidity = roundf(humidity * 10.0f) / 10.0f;
    gDhtState = SENSOR_OK;
  } else {
    gDhtTemp = gHumidity = NAN;
    gDhtState = SENSOR_FAILED;
  }
}

// ============================================================================
//  SECTION 5: LCD
// ============================================================================

static void printLcdLine(uint8_t row, const String& text) {
  if (!gLcdOk) return;
  static String cached[4];
  if (row >= LCD_ROWS || (!gLcdNeedsRefresh && cached[row] == text)) return;
  gLcd.setCursor(0, row);
  for (uint8_t column = 0; column < LCD_COLS; ++column) {
    gLcd.print(column < text.length() ? text[column] : ' ');
  }
  cached[row] = text;
}

static void renderLcd(uint32_t now) {
  if (!gLcdOk) return;
  if (now - gLastLcdRotate >= LCD_ROTATE_MS) {
    gLastLcdRotate = now;
    gLcdPage = (gLcdPage + 1) % 4;
    gLcdNeedsRefresh = true;
  }
  if (gMode == OPMODE_STANDBY) {
    printLcdLine(0, "LANDER STANDBY");
    printLcdLine(1, "Sensors paused");
    printLcdLine(2, "Wi-Fi link available");
    printLcdLine(3, "Mission Control");
    gLcdNeedsRefresh = false;
    return;
  }
  if (gLcdPage == 0) {
    printLcdLine(0, "MARS LANDER ACTIVE");
    printLcdLine(1, String("BMP280: ") + sensorStateName(gBmpState));
    printLcdLine(2, String("DHT11 : ") + sensorStateName(gDhtState));
    printLcdLine(3, gGatewayClient.connected() ? "WIFI: CONNECTED" : "WIFI: WAITING");
  } else if (gLcdPage == 1) {
    printLcdLine(0, "BMP280 TEMPERATURE");
    printLcdLine(1, gBmpState == SENSOR_OK ? String(gBmpTemp, 1) + " C" : "-- C");
    printLcdLine(2, "PRESSURE");
    printLcdLine(3, gBmpState == SENSOR_OK ? String(gPressure, 1) + " hPa" : "-- hPa");
  } else if (gLcdPage == 2) {
    printLcdLine(0, "DHT11 TEMPERATURE");
    printLcdLine(1, gDhtState == SENSOR_OK ? String(gDhtTemp, 1) + " C" : "-- C");
    printLcdLine(2, "HUMIDITY");
    printLcdLine(3, gDhtState == SENSOR_OK ? String(gHumidity, 1) + " %" : "-- %");
  } else {
    printLcdLine(0, "MISSION LINK STATUS");
    printLcdLine(1, "LANDER: ACTIVE");
    printLcdLine(2, "ROVER: SEE CONTROL");
    printLcdLine(3, "DRONE: INTERFACE TBD");
  }
  gLcdNeedsRefresh = false;
}

// ============================================================================
//  SECTION 6: WS2812B AND STATUS LEDs
// ============================================================================

static void animateStrip(uint32_t now) {
  if (now - gLastAnimation < ANIM_INTERVAL_MS) return;
  gLastAnimation = now;
  for (uint16_t i = 0; i < NUM_LEDS; ++i) {
    const uint16_t hue = (uint16_t)(42500 + i * 10000UL / NUM_LEDS + now / 8);
    const uint8_t value = (uint8_t)(80 + 65 * (0.5f + 0.5f * sinf((now / 600.0f) + i * 0.5f)));
    gStrip.setPixelColor(i, gStrip.ColorHSV(hue, 220, value));
  }
  gStrip.show();
}

static void updateStatusLeds() {
  digitalWrite(PIN_LED_GREEN, gMode == OPMODE_ACTIVE ? HIGH : LOW);
  // Red indicates a reported sensor fault; STANDBY has no current sensor read.
  const bool sensorFault = gMode == OPMODE_ACTIVE &&
      (gBmpState == SENSOR_FAILED || gDhtState == SENSOR_FAILED);
  digitalWrite(PIN_LED_RED, sensorFault ? HIGH : LOW);
}

// ============================================================================
//  SECTION 7: COMMANDS AND WI-FI / TCP LINK
// ============================================================================

static void processCommand(const char* line) {
  JsonDocument doc;
  if (deserializeJson(doc, line) || !doc.is<JsonObject>()) return;
  const char* command = doc["command"] | "";
  const bool hasId = doc["request_id"].is<int32_t>();
  const int32_t requestId = hasId ? doc["request_id"].as<int32_t>() : 0;
  if (!strcmp(command, "GET_STATUS")) {
    sendAck(requestId, hasId, true);
    sendStatus(requestId, hasId);
  } else if (!strcmp(command, "SET_ACTIVE")) {
    gMode = OPMODE_ACTIVE;
    gLastSensorPoll = 0;
    gLcdNeedsRefresh = true;
    sendAck(requestId, hasId, true);
    sendModeStatus(requestId, hasId);
    updateStatusLeds();
  } else if (!strcmp(command, "SET_STANDBY")) {
    gMode = OPMODE_STANDBY;
    gLcdNeedsRefresh = true;
    gBmpTemp = gPressure = gDhtTemp = gHumidity = NAN;
    gBmpState = gDhtState = SENSOR_NO_DATA;
    sendAck(requestId, hasId, true);
    sendModeStatus(requestId, hasId);
    updateStatusLeds();
  } else {
    sendAck(requestId, hasId, false, "INVALID_COMMAND");
  }
}

static void maintainWiFiLink(uint32_t now) {
  if (!wifiConfigured()) {
    if (!gWiFiConfigNoted) {
      gWiFiConfigNoted = true;
      debugLog("Wi-Fi/gateway not configured in lander.ino; running locally only");
    }
    return;
  }
  if (!gWiFiStarted) {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    gWiFiStarted = true;
  }
  if (WiFi.status() != WL_CONNECTED) {
    if (gGatewayClient.connected()) gGatewayClient.stop();
    if (now - gLastWiFiRetry >= WIFI_RETRY_MS) {
      gLastWiFiRetry = now;
      WiFi.reconnect();
    }
    return;
  }
  if (!gGatewayClient.connected() && now - gLastTcpRetry >= TCP_RETRY_MS) {
    gLastTcpRetry = now;
    gGatewayClient.stop();
    gGatewayClient.setTimeout(TCP_CONNECT_TIMEOUT_MS);
    if (gGatewayClient.connect(GATEWAY_HOST, GATEWAY_PORT)) {
      gLcdNeedsRefresh = true;
      sendStatus(0, false);
    }
  }
  while (gGatewayClient.connected() && gGatewayClient.available() > 0) {
    const char c = (char)gGatewayClient.read();
    if (c == '\n') {
      gCommandBuffer[gCommandLength] = '\0';
      if (gCommandLength > 0) processCommand(gCommandBuffer);
      gCommandLength = 0;
    } else if (c != '\r') {
      if (gCommandLength + 1 < sizeof(gCommandBuffer)) gCommandBuffer[gCommandLength++] = c;
      else gCommandLength = 0;
    }
  }
}

// ============================================================================
//  SECTION 8: setup() / loop()
// ============================================================================

void setup() {
  Serial.begin(DEBUG_BAUD, SERIAL_8N1);   // programming/debug only
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  updateStatusLeds();
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(I2C_CLOCK_HZ);
  Wire.setTimeOut(I2C_TIMEOUT_MS);
  Wire.beginTransmission(LCD_I2C_ADDR);
  if (Wire.endTransmission() == 0) {
    gLcd.init();
    gLcd.backlight();
    gLcdOk = true;
  }
  gStrip.begin();
  gStrip.setBrightness(STRIP_BRIGHTNESS);
  gStrip.clear();
  gStrip.show();
  gDht.begin();
  gClockStart = millis();
  gLastSensorPoll = millis() - SENSOR_FIRST_POLL_MS;
  Serial.println();
  Serial.print("[lander] boot, firmware ");
  Serial.println(FIRMWARE_VERSION);
}

void loop() {
  const uint32_t now = millis();
  maintainWiFiLink(now);
  if (gMode == OPMODE_ACTIVE && now - gLastSensorPoll >= SENSOR_POLL_MS) {
    gLastSensorPoll = now;
    pollSensors(now);
  }
  if (gMode == OPMODE_ACTIVE && now - gLastTelemetry >= TELEMETRY_MS) {
    gLastTelemetry = now;
    sendTelemetry(now);
  }
  updateStatusLeds();
  renderLcd(now);
  animateStrip(now);
}
