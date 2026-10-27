from pathlib import Path


FIRMWARE = Path(__file__).resolve().parents[2] / "Lander" / "lander" / "lander.ino"


def test_lander_firmware_keeps_sensor_display_led_and_usb_debug():
    source = FIRMWARE.read_text()
    for retained in (
        "PIN_DHT", "PIN_I2C_SDA", "PIN_I2C_SCL",
        "PIN_LED_GREEN", "PIN_LED_RED", "PIN_WS2812",
        "DEBUG_BAUD", "115200", "Serial.begin(DEBUG_BAUD, SERIAL_8N1)",
        "WiFi.h", "WiFi.begin(WIFI_SSID", "gGatewayClient.connect(GATEWAY_HOST",
        "bmp_temperature_c", "pressure_hpa", "dht_temperature_c", "humidity_pct",
        "LiquidCrystal_I2C", "Adafruit_NeoPixel", "SET_ACTIVE", "SET_STANDBY", "GET_STATUS",
    ):
        assert retained in source
    assert "serializeJson(doc, gGatewayClient)" in source
    assert "while (Serial.available()" not in source


def test_lander_firmware_contains_no_retired_actuator_implementation():
    source = FIRMWARE.read_text().lower()
    for removed in ("esp32servo", "open_gate", "close_gate", "gate_state", "limit_open", "limit_closed", "servo"):
        assert removed not in source
