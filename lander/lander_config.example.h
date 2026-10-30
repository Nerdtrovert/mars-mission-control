// ==============================================================================
// Mars Mission Control — ESP32 Lander Network Configuration Template
// ==============================================================================
// Copy this file to 'lander_config.h' and customize with your local Wi-Fi
// credentials and Raspberry Pi Gateway host IP address.
// 'lander_config.h' is ignored by Git to prevent committing credentials.
// ==============================================================================

#pragma once

#ifndef LANDER_CONFIG_H
#define LANDER_CONFIG_H

static const char *WIFI_SSID = "Mission-Control";
static const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD_HERE";

static const char *GATEWAY_HOST = "192.168.50.1";
static constexpr uint16_t GATEWAY_TCP_PORT = 5006;

#endif // LANDER_CONFIG_H
