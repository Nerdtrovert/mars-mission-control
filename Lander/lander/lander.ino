/*
 * Mars Lander Firmware v1.5.0
 * ESP32-WROOM-32 / DevKit V1
 *
 * Features:
 * - Wi-Fi station connection to Mission Control
 * - TCP connection to Raspberry Pi, port 5006
 * - Newline-delimited JSON telemetry and commands
 * - Rover and drone display-message handlers
 * - BMP280 and DHT11 sensor polling
 * - 20x4 I2C LCD with rotating pages
 * - Green/red status LEDs
 *
 * Libraries:
 * - ArduinoJson
 * - LiquidCrystal_I2C
 * - Adafruit BMP280 Library
 * - Adafruit Unified Sensor
 * - DHT sensor library
 */

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>
#include <math.h>

// ============================================================
// CONFIGURATION
// ============================================================

static const char *FIRMWARE_VERSION = "1.5.0";

static const char *WIFI_SSID = "Mission-Control";
static const char *WIFI_PASSWORD =
    "mission@mars";

static const char *GATEWAY_HOST = "192.168.50.1";
static constexpr uint16_t GATEWAY_TCP_PORT = 5006;

static constexpr uint8_t PIN_GREEN_LED = 25;
static constexpr uint8_t PIN_RED_LED = 26;
static constexpr uint8_t PIN_LED_GREEN = PIN_GREEN_LED;
static constexpr uint8_t PIN_LED_RED = PIN_RED_LED;
static const uint32_t DEBUG_BAUD = 115200;

static constexpr uint8_t PIN_DHT = 17;
static constexpr uint8_t DHT_TYPE = DHT11;

static constexpr uint8_t PIN_I2C_SDA = 21;
static constexpr uint8_t PIN_I2C_SCL = 22;

static constexpr uint8_t LCD_ADDRESS = 0x27;
static constexpr uint8_t LCD_COLUMNS = 20;
static constexpr uint8_t LCD_ROWS = 4;

static constexpr uint32_t SENSOR_POLL_MS = 2000;
static constexpr uint32_t BMP_RETRY_MS = 10000;
static constexpr uint32_t TELEMETRY_MS = 1000;

static constexpr uint32_t WIFI_RETRY_MS = 10000;
static constexpr uint32_t TCP_RETRY_MS = 1000;

static constexpr uint32_t REMOTE_TIMEOUT_MS = 10000;

static constexpr uint32_t LCD_LANDER_MS = 3200;
static constexpr uint32_t LCD_REMOTE_MS = 3750;
static constexpr uint32_t LCD_FACT_MS = 3750;

static constexpr size_t TCP_BUFFER_SIZE = 768;

// ============================================================
// ENUMS
// ============================================================

enum OperatingMode : uint8_t {
  OPMODE_ACTIVE,
  OPMODE_STANDBY
};

enum SensorState : uint8_t {
  SENSOR_NO_DATA,
  SENSOR_OK,
  SENSOR_FAILED
};

enum LcdPage : uint8_t {
  PAGE_LANDER_STATUS,
  PAGE_LANDER_SENSORS,
  PAGE_ROVER,
  PAGE_DRONE,
  PAGE_MARS_FACT,
  PAGE_COUNT
};

// ============================================================
// REMOTE DISPLAY DATA
// ============================================================

struct RoverData {
  bool hasUpdate = false;
  bool connected = false;

  uint32_t lastUpdateMs = 0;

  bool distanceValid = false;
  bool pitchValid = false;
  bool rollValid = false;

  float distance = NAN;
  float pitch = NAN;
  float roll = NAN;

  String command = "";
  String mode = "";
};

struct DroneData {
  bool hasUpdate = false;
  bool connected = false;

  uint32_t lastUpdateMs = 0;

  String flightStatus = "";

  bool latitudeValid = false;
  bool longitudeValid = false;

  float latitude = NAN;
  float longitude = NAN;
};

// ============================================================
// HARDWARE OBJECTS
// ============================================================

WiFiClient gGatewayClient;

LiquidCrystal_I2C gLcd(
    LCD_ADDRESS,
    LCD_COLUMNS,
    LCD_ROWS
);

Adafruit_BMP280 gBmp;

DHT gDht(
    PIN_DHT,
    DHT_TYPE
);

// ============================================================
// GLOBAL STATE
// ============================================================

OperatingMode gMode = OPMODE_ACTIVE;

SensorState gBmpState = SENSOR_NO_DATA;
SensorState gDhtState = SENSOR_NO_DATA;

bool gLcdPresent = false;
bool gBmpReady = false;
bool gWifiConnecting = false;

float gBmpTemperatureC = NAN;
float gPressureHpa = NAN;

float gDhtTemperatureC = NAN;
float gHumidityPct = NAN;

uint32_t gLastSensorPollMs = 0;
uint32_t gLastTelemetryMs = 0;

uint32_t gLastWifiAttemptMs = 0;
uint32_t gLastTcpAttemptMs = 0;

uint32_t gLastBmpRetryMs = 0;
uint32_t gLastLcdPageChangeMs = 0;

LcdPage gLcdPage = PAGE_LANDER_STATUS;

size_t gMarsFactIndex = 0;

RoverData gRover;
DroneData gDrone;

char gTcpLine[TCP_BUFFER_SIZE];

size_t gTcpLineLength = 0;

bool gTcpLineOverflow = false;

char gLcdCache[LCD_ROWS][LCD_COLUMNS + 1] = {{0}};

// ============================================================
// MARS FUN FACTS
// ============================================================

struct MarsFact {
  const char *line3;
  const char *line4;
};

const MarsFact gMarsFacts[] = {
  {"A DAY ON MARS", "LASTS 24H 39M (SOL)"},
  {"A YEAR ON MARS", "ABOUT 687 EARTH DAYS"},
  {"MARS HAS 2 MOONS", "PHOBOS AND DEIMOS"},
  {"MARS LOOKS RED", "IRON-RICH DUST"},
  {"OLYMPUS MONS", "A GIANT VOLCANO"},
  {"VALLES MARINERIS", "A VAST MARTIAN CANYON"},
  {"MARS IS COLD", "AVG ABOUT -63 C"},
  {"AIR IS VERY THIN", "MOSTLY CARBON DIOXIDE"},
  {"PERSEVERANCE", "LANDED IN 2021"},
  {"INGENUITY", "FIRST POWERED MARS FLIGHT"},
  {"MANGALYAAN", "MARS ORBIT IN 2014"},
  {"ISRO'S MARS PROBE", "INDIA: 4TH TO REACH MARS"},
  {"EARTH-MARS GAP", "CHANGES AS THEY ORBIT"},
  {"MARS FROM SUN", "AVG ABOUT 228 MILLION KM"},
  {"MARS GRAVITY", "ABOUT 38% OF EARTH'S"},
  {"SUNLIGHT TO MARS", "TAKES ABOUT 13 MIN AVG"},
  {"MARS HAS SEASONS", "AXIS TILTS LIKE EARTH"},
  {"DUST STORMS", "CAN SPREAD VERY WIDE"},
  {"WATER ICE EXISTS", "NEAR THE POLAR REGIONS"},
  {"MARS HAS NO", "GLOBAL MAGNETIC FIELD"}
};

static constexpr size_t MARS_FACT_COUNT =
    sizeof(gMarsFacts) / sizeof(gMarsFacts[0]);

// ============================================================
// GENERAL HELPERS
// ============================================================

const char *modeName() {
  return gMode == OPMODE_ACTIVE ? "ACTIVE" : "STANDBY";
}

const char *sensorStateName(SensorState state) {
  switch (state) {
    case SENSOR_OK:
      return "OK";

    case SENSOR_FAILED:
      return "FAILED";

    default:
      return "NO_DATA";
  }
}

bool finiteValue(float value) {
  return !isnan(value) && !isinf(value);
}

float round1(float value) {
  return roundf(value * 10.0f) / 10.0f;
}

void clearSensorValues() {
  gBmpTemperatureC = NAN;
  gPressureHpa = NAN;

  gDhtTemperatureC = NAN;
  gHumidityPct = NAN;

  gBmpState = SENSOR_NO_DATA;
  gDhtState = SENSOR_NO_DATA;
}

void setNullableFloat(
    JsonDocument &doc,
    const char *key,
    float value,
    bool valid
) {
  if (valid && finiteValue(value)) {
    doc[key] = round1(value);
  } else {
    doc[key] = nullptr;
  }
}

// ============================================================
// TCP JSON OUTPUT
// ============================================================

bool sendJson(JsonDocument &doc) {
  if (!gGatewayClient.connected()) {
    return false;
  }

  if (serializeJson(doc, gGatewayClient) == 0) {
    return false;
  }

  gGatewayClient.write('\n');

  return true;
}

void sendAck(
    const char *command,
    bool ok,
    const char *message,
    int32_t requestId = -1
) {
  JsonDocument doc;

  doc["type"] = "command_ack";
  doc["timestamp_ms"] = millis();
  doc["command"] = command;
  doc["ok"] = ok;
  doc["accepted"] = ok;
  doc["message"] = message;
  doc["reason"] = message;
  if (requestId >= 0) {
    doc["request_id"] = requestId;
  }

  sendJson(doc);
}

void sendModeStatus(int32_t requestId = -1) {
  JsonDocument doc;

  doc["type"] = "mode_status";
  doc["timestamp_ms"] = millis();
  doc["mode"] = modeName();
  if (requestId >= 0) {
    doc["request_id"] = requestId;
  }

  sendJson(doc);
}

void sendStatus(int32_t requestId = -1) {
  JsonDocument doc;

  doc["type"] = "status";
  doc["timestamp_ms"] = millis();
  if (requestId >= 0) {
    doc["request_id"] = requestId;
  }

  doc["mode"] = modeName();

  doc["sensors_polling"] =
      gMode == OPMODE_ACTIVE;

  doc["bmp280_ok"] =
      gBmpState == SENSOR_OK;

  doc["dht11_ok"] =
      gDhtState == SENSOR_OK;

  doc["bmp280_state"] =
      sensorStateName(gBmpState);

  doc["dht11_state"] =
      sensorStateName(gDhtState);

  doc["firmware"] = FIRMWARE_VERSION;

  sendJson(doc);
}

void sendTelemetry() {
  JsonDocument doc;

  doc["type"] = "telemetry";
  doc["timestamp_ms"] = millis();
  doc["mode"] = modeName();

  setNullableFloat(
      doc,
      "bmp_temperature_c",
      gBmpTemperatureC,
      gBmpState == SENSOR_OK
  );

  setNullableFloat(
      doc,
      "pressure_hpa",
      gPressureHpa,
      gBmpState == SENSOR_OK
  );

  setNullableFloat(
      doc,
      "dht_temperature_c",
      gDhtTemperatureC,
      gDhtState == SENSOR_OK
  );

  setNullableFloat(
      doc,
      "humidity_pct",
      gHumidityPct,
      gDhtState == SENSOR_OK
  );

  doc["bmp280_ok"] =
      gBmpState == SENSOR_OK;

  doc["dht11_ok"] =
      gDhtState == SENSOR_OK;

  sendJson(doc);
}

// ============================================================
// JSON INPUT HELPERS
// ============================================================

bool readNumber(
    JsonVariantConst value,
    float &out
) {
  if (value.isNull()) {
    return false;
  }

  if (!(value.is<float>() ||
        value.is<double>() ||
        value.is<int>() ||
        value.is<long>() ||
        value.is<unsigned int>() ||
        value.is<unsigned long>())) {
    return false;
  }

  float number = value.as<float>();

  if (!finiteValue(number)) {
    return false;
  }

  out = number;

  return true;
}

// ============================================================
// ROVER / DRONE DISPLAY MESSAGE HANDLING
// ============================================================

void handleMissionDisplay(JsonObjectConst root) {
  const char *device = root["device"] | "";

  const bool connected =
      root["connected"] | false;

  JsonObjectConst data =
      root["data"].as<JsonObjectConst>();

  if (strcmp(device, "rover") == 0) {
    gRover.hasUpdate = true;
    gRover.connected = connected;
    gRover.lastUpdateMs = millis();

    if (!data.isNull()) {
      gRover.distanceValid =
          readNumber(data["distance"], gRover.distance);

      gRover.pitchValid =
          readNumber(data["pitch"], gRover.pitch);

      gRover.rollValid =
          readNumber(data["roll"], gRover.roll);

      gRover.command =
          data["cmd"].is<const char *>()
              ? data["cmd"].as<String>()
              : "";

      gRover.mode =
          data["mode"].is<const char *>()
              ? data["mode"].as<String>()
              : "";
    }
  }

  else if (strcmp(device, "drone") == 0) {
    gDrone.hasUpdate = true;
    gDrone.connected = connected;
    gDrone.lastUpdateMs = millis();

    if (!data.isNull()) {
      gDrone.flightStatus =
          data["flight_status"].is<const char *>()
              ? data["flight_status"].as<String>()
              : "";

      gDrone.latitudeValid =
          readNumber(data["latitude"], gDrone.latitude);

      gDrone.longitudeValid =
          readNumber(data["longitude"], gDrone.longitude);
    }
  }
}

// ============================================================
// COMMAND HANDLING
// ============================================================

void setActiveMode() {
  gMode = OPMODE_ACTIVE;

  clearSensorValues();

  uint32_t now = millis();

  gLastSensorPollMs =
      now - SENSOR_POLL_MS + 1000;

  gLastTelemetryMs = now;

  gLcdPage = PAGE_LANDER_STATUS;

  gLastLcdPageChangeMs = now;
}

void processIncomingJson(char *line) {
  JsonDocument doc;

  DeserializationError error =
      deserializeJson(doc, line);

  if (error) {
    Serial.printf(
        "[TCP] Invalid JSON: %s\n",
        error.c_str()
    );

    return;
  }

  const char *type =
      doc["type"] | "";

  // New additive message type for remote LCD pages.
  if (strcmp(type, "mission_display") == 0) {
    handleMissionDisplay(
        doc.as<JsonObjectConst>()
    );

    return;
  }

  // Existing gateway command format remains supported.
  const char *command =
      doc["command"] | "";

  const bool hasId = doc["request_id"].is<int32_t>();
  const int32_t requestId = hasId ? doc["request_id"].as<int32_t>() : -1;

  if (strcmp(command, "GET_STATUS") == 0) {
    sendAck(
        command,
        true,
        "Status sent",
        requestId
    );

    sendStatus(requestId);
    sendModeStatus(requestId);
  }

  else if (strcmp(command, "SET_ACTIVE") == 0) {
    setActiveMode();

    sendAck(
        command,
        true,
        "Lander active; sensor polling enabled",
        requestId
    );

    sendModeStatus(requestId);
    sendStatus(requestId);
  }

  else if (strcmp(command, "SET_STANDBY") == 0) {
    gMode = OPMODE_STANDBY;

    clearSensorValues();

    gLcdPage = PAGE_LANDER_STATUS;
    gLastLcdPageChangeMs = millis();

    sendAck(
        command,
        true,
        "Lander standby; sensor polling paused",
        requestId
    );

    sendModeStatus(requestId);
    sendStatus(requestId);
  }

  else if (command[0] != '\0') {
    sendAck(
        command,
        false,
        "Unknown command",
        requestId
    );
  }

  else {
    Serial.println(
        "[TCP] JSON message had no recognized type/command"
    );
  }
}

// ============================================================
// TCP INPUT
// ============================================================

void readTcpMessages() {
  while (
      gGatewayClient.connected() &&
      gGatewayClient.available()
  ) {
    int incoming = gGatewayClient.read();

    if (incoming < 0) {
      break;
    }

    char c = static_cast<char>(incoming);

    if (c == '\n') {
      if (!gTcpLineOverflow &&
          gTcpLineLength > 0) {

        gTcpLine[gTcpLineLength] = '\0';

        // Accept CRLF and LF.
        if (gTcpLineLength > 0 &&
            gTcpLine[gTcpLineLength - 1] == '\r') {
          gTcpLine[gTcpLineLength - 1] = '\0';
        }

        processIncomingJson(gTcpLine);
      }

      gTcpLineLength = 0;
      gTcpLineOverflow = false;
    }

    else if (!gTcpLineOverflow) {
      if (gTcpLineLength + 1 < TCP_BUFFER_SIZE) {
        gTcpLine[gTcpLineLength++] = c;
      }

      else {
        gTcpLineOverflow = true;
        gTcpLineLength = 0;

        Serial.println(
            "[TCP] Oversized JSON line discarded"
        );
      }
    }
  }
}

// ============================================================
// WIFI EVENTS
// ============================================================

void onWiFiEvent(WiFiEvent_t event) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_START:
      Serial.println("[WiFi] Station started");
      break;

    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      Serial.println("[WiFi] Associated with access point");
      gWifiConnecting = false;
      break;

    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      Serial.print("[WiFi] IP: ");
      Serial.println(WiFi.localIP());

      gWifiConnecting = false;
      break;

    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
      Serial.println("[WiFi] Disconnected");

      gWifiConnecting = false;

      gGatewayClient.stop();
      break;

    default:
      break;
  }
}

void scanWiFiNetworks() {
  Serial.println("[WiFi] Scanning...");

  int count = WiFi.scanNetworks(false, true);

  bool found = false;

  if (count < 0) {
    Serial.println("[WiFi] Scan failed");
    return;
  }

  for (int i = 0; i < count; ++i) {
    String ssid = WiFi.SSID(i);

    Serial.printf(
        "[WiFi] %s (%d dBm)\n",
        ssid.c_str(),
        WiFi.RSSI(i)
    );

    if (ssid == WIFI_SSID) {
      found = true;
    }
  }

  Serial.println(
      found
          ? "[WiFi] Mission-Control found"
          : "[WiFi] Mission-Control not found"
  );

  WiFi.scanDelete();
}

void startWiFiConnection() {
  gLastWifiAttemptMs = millis();

  gWifiConnecting = true;

  Serial.printf(
      "[WiFi] Connecting to '%s'\n",
      WIFI_SSID
  );

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  if (!gWifiConnecting &&
      millis() - gLastWifiAttemptMs >= WIFI_RETRY_MS) {
    startWiFiConnection();
  }
}

// ============================================================
// TCP CONNECTION MANAGEMENT
// ============================================================

void maintainTcpConnection() {
  if (WiFi.status() != WL_CONNECTED) {
    gGatewayClient.stop();
    return;
  }

  if (gGatewayClient.connected()) {
    readTcpMessages();
    return;
  }

  gGatewayClient.stop();

  uint32_t now = millis();

  if (now - gLastTcpAttemptMs < TCP_RETRY_MS) {
    return;
  }

  gLastTcpAttemptMs = now;

  Serial.printf(
      "[TCP] Connecting to %s:%u\n",
      GATEWAY_HOST,
      GATEWAY_TCP_PORT
  );

  gGatewayClient.setNoDelay(true);
  gGatewayClient.setTimeout(100);

  if (gGatewayClient.connect(GATEWAY_HOST, GATEWAY_TCP_PORT)) {
    Serial.println("[TCP] Gateway connected");

    gTcpLineLength = 0;
    gTcpLineOverflow = false;

    sendStatus();
    sendModeStatus();
  }

  else {
    Serial.println("[TCP] Connection failed");
  }
}

// ============================================================
// BMP280 INITIALIZATION
// ============================================================

bool beginBmpSensor() {
  if (gBmp.begin(0x76)) {
    Serial.println("[BMP280] Found at 0x76");
    return true;
  }

  if (gBmp.begin(0x77)) {
    Serial.println("[BMP280] Found at 0x77");
    return true;
  }

  Serial.println(
      "[BMP280] Not found at 0x76 or 0x77"
  );

  return false;
}

// ============================================================
// SENSOR POLLING
// ============================================================

void pollSensors() {
  if (gMode != OPMODE_ACTIVE) {
    return;
  }

  uint32_t now = millis();

  if (now - gLastSensorPollMs < SENSOR_POLL_MS) {
    return;
  }

  gLastSensorPollMs = now;

  // Retry BMP280 initialization after failure.
  if (!gBmpReady &&
      now - gLastBmpRetryMs >= BMP_RETRY_MS) {
    gLastBmpRetryMs = now;

    gBmpReady = beginBmpSensor();
  }

  // BMP280: temperature and pressure.
  if (gBmpReady) {
    float temp = gBmp.readTemperature();
    float pressurePa = gBmp.readPressure();

    if (finiteValue(temp) &&
        temp >= -40 &&
        temp <= 85 &&
        finiteValue(pressurePa) &&
        pressurePa >= 30000 &&
        pressurePa <= 110000) {

      gBmpTemperatureC = round1(temp);

      gPressureHpa =
          round1(pressurePa / 100.0f);

      gBmpState = SENSOR_OK;
    }

    else {
      gBmpTemperatureC = NAN;
      gPressureHpa = NAN;

      gBmpState = SENSOR_FAILED;
      gBmpReady = false;

      gLastBmpRetryMs = now;
    }
  }

  else {
    gBmpState = SENSOR_FAILED;
  }

  // DHT11: temperature and humidity.
  float temp = gDht.readTemperature();
  float humidity = gDht.readHumidity();

  if (finiteValue(temp) &&
      temp >= -10 &&
      temp <= 60 &&
      finiteValue(humidity) &&
      humidity >= 0 &&
      humidity <= 100) {

    gDhtTemperatureC = round1(temp);
    gHumidityPct = round1(humidity);

    gDhtState = SENSOR_OK;
  }

  else {
    gDhtTemperatureC = NAN;
    gHumidityPct = NAN;

    gDhtState = SENSOR_FAILED;
  }

  Serial.printf(
      "[Sensors] BMP=%s DHT=%s\n",
      sensorStateName(gBmpState),
      sensorStateName(gDhtState)
  );
}

// ============================================================
// PERIODIC TELEMETRY
// ============================================================

void maintainTelemetry() {
  uint32_t now = millis();

  if (now - gLastTelemetryMs >= TELEMETRY_MS) {
    gLastTelemetryMs = now;

    sendTelemetry();
  }
}

// ============================================================
// LCD HELPERS
// ============================================================

String fitLine(String text) {
  if (text.length() > LCD_COLUMNS) {
    text.remove(LCD_COLUMNS);
  }

  while (text.length() < LCD_COLUMNS) {
    text += ' ';
  }

  return text;
}

void lcdLine(uint8_t row, String text) {
  if (!gLcdPresent || row >= LCD_ROWS) {
    return;
  }

  text = fitLine(text);

  if (strncmp(
          gLcdCache[row],
          text.c_str(),
          LCD_COLUMNS
      ) == 0) {
    return;
  }

  memcpy(
      gLcdCache[row],
      text.c_str(),
      LCD_COLUMNS
  );

  gLcdCache[row][LCD_COLUMNS] = '\0';

  gLcd.setCursor(0, row);
  gLcd.print(text);
}

void renderLines(
    String line1,
    String line2,
    String line3,
    String line4
) {
  lcdLine(0, line1);
  lcdLine(1, line2);
  lcdLine(2, line3);
  lcdLine(3, line4);
}

String valueOrNA(
    float value,
    bool valid,
    uint8_t decimals = 1
) {
  if (!valid || !finiteValue(value)) {
    return "N/A";
  }

  return String(value, (unsigned int)decimals);
}

String remoteState(
    bool hasData,
    bool connected,
    uint32_t lastUpdate
) {
  if (!hasData) {
    return "WAIT";
  }

  if (!connected ||
      millis() - lastUpdate > REMOTE_TIMEOUT_MS) {
    return "OFFLINE";
  }

  return "OK";
}

// ============================================================
// LCD PAGE 1: LANDER STATUS
// ============================================================

void renderLanderStatus() {
  renderLines(
      "MARS LANDER",
      String("MODE: ") + modeName(),
      String("WIFI: ") +
          (WiFi.status() == WL_CONNECTED
               ? "CONNECTED"
               : "OFFLINE"),
      String("GATEWAY TCP: ") +
          (gGatewayClient.connected()
               ? "OK"
               : "WAIT")
  );
}

// ============================================================
// LCD PAGE 2: LANDER SENSORS
// ============================================================

void renderLanderSensors() {
  renderLines(
      "MARS LANDER",

      String("DHT TEMP: ") +
          valueOrNA(
              gDhtTemperatureC,
              gDhtState == SENSOR_OK
          ) + " C",

      String("HUMIDITY: ") +
          valueOrNA(
              gHumidityPct,
              gDhtState == SENSOR_OK
          ) + " %",

      String("BMP PRESS: ") +
          valueOrNA(
              gPressureHpa,
              gBmpState == SENSOR_OK
          ) + " hPa"
  );
}

// ============================================================
// LCD PAGE 3: ROVER
// ============================================================

void renderRover() {
  String state = remoteState(
      gRover.hasUpdate,
      gRover.connected,
      gRover.lastUpdateMs
  );

  String line3;
  String line4;

  if (state == "WAIT") {
    line3 = "WAITING FOR DATA";
    line4 = "NO ROVER TELEMETRY";
  }

  else if (state == "OFFLINE") {
    line3 = "LINK OFFLINE";
    line4 = "LAST DATA NOT LIVE";
  }

  else {
    line3 =
        String("DIST: ") +
        valueOrNA(
            gRover.distance,
            gRover.distanceValid,
            1
        );

    line4 =
        String("P:") +
        valueOrNA(
            gRover.pitch,
            gRover.pitchValid,
            1
        ) +
        " R:" +
        valueOrNA(
            gRover.roll,
            gRover.rollValid,
            1
        );
  }

  renderLines(
      "MARS ROVER",
      String("CONNECTION: ") + state,
      line3,
      line4
  );
}

// ============================================================
// LCD PAGE 4: DRONE
// ============================================================

void renderDrone() {
  String state = remoteState(
      gDrone.hasUpdate,
      gDrone.connected,
      gDrone.lastUpdateMs
  );

  String line2;
  String line3;
  String line4;

  if (state == "WAIT") {
    line2 = "STATUS: WAIT";
    line3 = "WAITING FOR DATA";
    line4 = "DRONE LINK PENDING";
  }

  else if (state == "OFFLINE") {
    line2 = "STATUS: OFFLINE";
    line3 = "LINK OFFLINE";
    line4 = "LAST DATA NOT LIVE";
  }

  else {
    line2 =
        gDrone.flightStatus.length()
            ? (String("STATUS: ") + gDrone.flightStatus)
            : "STATUS: OK";

    if (gDrone.latitudeValid &&
        gDrone.longitudeValid) {

      line3 =
          String("LAT: ") +
          String(gDrone.latitude, 4);

      line4 =
          String("LON: ") +
          String(gDrone.longitude, 4);
    }

    else {
      line3 = "GPS: NOT AVAILABLE";
      line4 = "NO COORDINATES";
    }
  }

  renderLines(
      "MARS DRONE",
      line2,
      line3,
      line4
  );
}

// ============================================================
// LCD PAGE ROTATION
// ============================================================

void advanceLcdPage() {
  gLcdPage = static_cast<LcdPage>(
      (static_cast<uint8_t>(gLcdPage) + 1) %
      static_cast<uint8_t>(PAGE_COUNT)
  );

  if (gLcdPage == PAGE_MARS_FACT) {
    gMarsFactIndex =
        (gMarsFactIndex + 1) % MARS_FACT_COUNT;
  }

  gLastLcdPageChangeMs = millis();
}

uint32_t pageDuration() {
  if (gLcdPage == PAGE_LANDER_STATUS ||
      gLcdPage == PAGE_LANDER_SENSORS) {
    return LCD_LANDER_MS;
  }

  if (gLcdPage == PAGE_ROVER ||
      gLcdPage == PAGE_DRONE) {
    return LCD_REMOTE_MS;
  }

  return LCD_FACT_MS;
}

void updateLcd() {
  if (!gLcdPresent) {
    return;
  }

  if (gMode == OPMODE_STANDBY) {
    renderLines(
        "MARS LANDER",
        "MODE: STANDBY",
        "SENSORS: PAUSED",
        gGatewayClient.connected()
            ? "GATEWAY TCP: OK"
            : "GATEWAY TCP: WAIT"
    );

    return;
  }

  if (millis() - gLastLcdPageChangeMs >= pageDuration()) {
    advanceLcdPage();
  }

  switch (gLcdPage) {
    case PAGE_LANDER_STATUS:
      renderLanderStatus();
      break;

    case PAGE_LANDER_SENSORS:
      renderLanderSensors();
      break;

    case PAGE_ROVER:
      renderRover();
      break;

    case PAGE_DRONE:
      renderDrone();
      break;

    case PAGE_MARS_FACT: {
      const MarsFact &fact =
          gMarsFacts[gMarsFactIndex % MARS_FACT_COUNT];

      renderLines(
          "MARS FUN FACT",
          "DID YOU KNOW?",
          fact.line3,
          fact.line4
      );

      break;
    }

    default:
      gLcdPage = PAGE_LANDER_STATUS;
      gLastLcdPageChangeMs = millis();
      break;
  }
}

// ============================================================
// LED STATUS
// ============================================================

void updateLeds() {
  digitalWrite(
      PIN_GREEN_LED,
      gMode == OPMODE_ACTIVE ? HIGH : LOW
  );

  bool sensorError =
      gMode == OPMODE_ACTIVE &&
      (
          gBmpState == SENSOR_FAILED ||
          gDhtState == SENSOR_FAILED
      );

  digitalWrite(
      PIN_RED_LED,
      sensorError && ((millis() / 300) % 2)
          ? HIGH
          : LOW
  );
}

// ============================================================
// SETUP
// ============================================================

void setup() {
  Serial.begin(DEBUG_BAUD, SERIAL_8N1);

  delay(200);

  Serial.println();
  Serial.println("========================================");
  Serial.println("MARS LANDER FIRMWARE");
  Serial.printf("Version: %s\n", FIRMWARE_VERSION);
  Serial.println("========================================");

  pinMode(PIN_GREEN_LED, OUTPUT);
  pinMode(PIN_RED_LED, OUTPUT);

  digitalWrite(PIN_GREEN_LED, LOW);
  digitalWrite(PIN_RED_LED, LOW);

  // Wi-Fi setup.
  WiFi.onEvent(onWiFiEvent);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  scanWiFiNetworks();
  startWiFiConnection();

  // I2C setup.
  Wire.begin(
      PIN_I2C_SDA,
      PIN_I2C_SCL
  );

  Wire.setClock(100000);
  Wire.setTimeOut(30);

  // LCD detection.
  Wire.beginTransmission(LCD_ADDRESS);

  uint8_t lcdError = Wire.endTransmission();

  if (lcdError == 0) {
    gLcdPresent = true;

    gLcd.init();
    gLcd.backlight();
    gLcd.clear();

    memset(
        gLcdCache,
        0,
        sizeof(gLcdCache)
    );

    renderLines(
        "MARS LANDER",
        "INITIALIZING...",
        "SENSORS: STARTING",
        "MISSION CONTROL"
    );

    Serial.println(
        "[LCD] 20x4 display found at 0x27"
    );
  }

  else {
    Serial.printf(
        "[LCD] Not found at 0x27 (I2C error %u)\n",
        lcdError
    );
  }

  // Sensor initialization.
  gBmpReady = beginBmpSensor();

  gLastBmpRetryMs = millis();

  gDht.begin();

  // Timer initialization.
  uint32_t now = millis();

  gLastSensorPollMs =
      now - SENSOR_POLL_MS + 1000;

  gLastTelemetryMs = now;

  gLastWifiAttemptMs = now;
  gLastTcpAttemptMs = now;

  gLastLcdPageChangeMs = now;

  gLcdPage = PAGE_LANDER_STATUS;

  Serial.println("[BOOT] Setup complete");
}

// ============================================================
// MAIN LOOP
// ============================================================

void loop() {
  maintainWiFi();

  maintainTcpConnection();

  pollSensors();

  maintainTelemetry();

  updateLeds();

  updateLcd();

  delay(2);
}
