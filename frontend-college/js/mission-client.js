/**
 * Mars Mission Control — Central Mission Client
 * frontend-college/js/mission-client.js
 *
 * Coordinates live WebSocket feeds, REST polling fallback, and operator command dispatching.
 */

(function () {
  'use strict';

  // --- State Cache ---
  let cachedState = {
    mode: 'UNKNOWN',
    gateway_state: 'NOT_CONNECTED',
    device_state: 'NOT_CONNECTED',
    bmp280_ok: null,
    dht11_ok: null,
    simulation_mode: false,
    last_telemetry: null,
  };

  let cachedTelemetry = null;
  let cachedRover = null;
  let cachedDrone = null;
  let cachedCommands = [];
  let cachedEvents = [];
  let cachedTelemetryHistory = [];

  let ws = null;
  let wsReconnectTimer = null;
  let isWsConnected = false;
  let isCommandInFlight = false;

  // --- DOM Elements ---
  const elWsDot = document.getElementById('lander-ws-dot');
  const elWsText = document.getElementById('lander-ws-text');

  const elAlertBanner = document.getElementById('lander-alert-banner');
  const elBannerIcon = document.getElementById('lander-banner-icon');
  const elBannerText = document.getElementById('lander-banner-text');

  // --- WebSocket Status Pill ---
  function updateWsStatus(status) {
    if (!elWsDot || !elWsText) return;
    if (status === 'connected') {
      elWsDot.className = 'pill-dot online';
      elWsText.textContent = 'WS: CONNECTED';
    } else if (status === 'connecting') {
      elWsDot.className = 'pill-dot stale';
      elWsText.textContent = 'WS: CONNECTING';
    } else {
      elWsDot.className = 'pill-dot offline';
      elWsText.textContent = 'WS: DISCONNECTED';
    }
  }

  // --- Alert Banner Update ---
  function updateAlertBanner() {
    if (!elAlertBanner || !elBannerText) return;

    const devState = (cachedState.device_state || 'NOT_CONNECTED').toUpperCase();
    const gwState = (cachedState.gateway_state || 'NOT_CONNECTED').toUpperCase();

    if (devState === 'ONLINE') {
      elAlertBanner.className = 'preview-alert-banner banner-nominal';
      if (elBannerIcon) elBannerIcon.innerHTML = '&#x2714;';
      elBannerText.innerHTML = '<strong>NOMINAL:</strong> Live telemetry streaming over Wi-Fi TCP port 5006.';
    } else if (gwState === 'ONLINE') {
      elAlertBanner.className = 'preview-alert-banner banner-disrupted';
      if (elBannerIcon) elBannerIcon.innerHTML = '&#x26A0;';
      elBannerText.innerHTML = '<strong>AWAITING LANDER:</strong> Gateway online at 192.168.50.1; awaiting ESP32 TCP connection on port 5006.';
    } else if (!isWsConnected) {
      elAlertBanner.className = 'preview-alert-banner banner-disrupted';
      if (elBannerIcon) elBannerIcon.innerHTML = '&#x26A0;';
      elBannerText.innerHTML = '<strong>DISCONNECTED:</strong> Connecting to Mission Control backend...';
    } else {
      elAlertBanner.className = 'preview-alert-banner banner-disrupted';
      if (elBannerIcon) elBannerIcon.innerHTML = '&#x26A0;';
      elBannerText.innerHTML = '<strong>STANDBY:</strong> Lander state is awaiting fresh telemetry.';
    }
  }

  // --- Broadcast Updates to Views ---
  function dispatchStateUpdates() {
    if (window.MMCLanderView) {
      window.MMCLanderView.update(cachedState, cachedTelemetry);
    }
    updateAlertBanner();
    if (window.MMCLandingView) {
      window.MMCLandingView.update(cachedState, cachedRover, cachedDrone);
    }
  }

  // --- Dynamic Host Resolution ---
  function getApiBase() {
    if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
      if (window.location.port === '8000') {
        return '';
      }
      return `${window.location.protocol}//${window.location.hostname || '127.0.0.1'}:8000`;
    }
    return 'http://127.0.0.1:8000';
  }

  function getWsUrl() {
    if (window.location.protocol === 'https:') {
      const host = window.location.port === '8000' ? window.location.host : `${window.location.hostname || '127.0.0.1'}:8000`;
      return `wss://${host}/ws/telemetry`;
    }
    const host = window.location.port === '8000' ? window.location.host : `${window.location.hostname || '127.0.0.1'}:8000`;
    return `ws://${host}/ws/telemetry`;
  }

  // --- WebSocket Connection ---
  function connectWebSocket() {
    if (ws) {
      try {
        ws.close();
      } catch (e) {}
      ws = null;
    }

    updateWsStatus('connecting');

    const wsUrl = getWsUrl();

    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      scheduleWsReconnect();
      return;
    }

    ws.onopen = function () {
      isWsConnected = true;
      updateWsStatus('connected');
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
      pollAll();
    };

    ws.onmessage = function (event) {
      try {
        const msg = JSON.parse(event.data);
        if (!msg) return;

        if (msg.type === 'state_snapshot') {
          if (msg.data) {
            cachedState = Object.assign({}, cachedState, msg.data);
            if (msg.data.last_telemetry) {
              cachedTelemetry = msg.data.last_telemetry;
            }
          }
          dispatchStateUpdates();
        } else if (msg.type === 'telemetry') {
          if (msg.telemetry) {
            cachedTelemetry = msg.telemetry;
          }
          if (msg.state) {
            cachedState = Object.assign({}, cachedState, msg.state);
          }
          dispatchStateUpdates();
        } else if (msg.type === 'rover_telemetry') {
          if (msg.rover) {
            cachedRover = msg.rover;
            if (window.MMCRoverView) window.MMCRoverView.update(msg.rover);
            if (window.MMCLandingView) window.MMCLandingView.update(cachedState, cachedRover, cachedDrone);
          }
        } else if (msg.type === 'drone_telemetry') {
          if (msg.drone) {
            cachedDrone = msg.drone;
            if (window.MMCDroneView) window.MMCDroneView.update(msg.drone);
            if (window.MMCLandingView) window.MMCLandingView.update(cachedState, cachedRover, cachedDrone);
          }
        } else if (msg.type === 'command_update') {
          fetchCommands();
          fetchState();
        }
      } catch (err) {
        console.warn('WebSocket message parse error:', err);
      }
    };

    ws.onclose = function () {
      isWsConnected = false;
      updateWsStatus('disconnected');
      updateAlertBanner();
      scheduleWsReconnect();
    };

    ws.onerror = function () {
      isWsConnected = false;
      updateWsStatus('disconnected');
      updateAlertBanner();
      try {
        ws.close();
      } catch (e) {}
    };
  }

  function scheduleWsReconnect() {
    if (wsReconnectTimer) return;
    wsReconnectTimer = setTimeout(() => {
      wsReconnectTimer = null;
      connectWebSocket();
    }, 3000);
  }

  // --- REST API Data Fetchers ---
  async function fetchState() {
    try {
      const res = await fetch(`${getApiBase()}/api/mission/state`);
      if (res.ok) {
        const data = await res.json();
        cachedState = Object.assign({}, cachedState, data);
        if (data.last_telemetry) {
          cachedTelemetry = data.last_telemetry;
        }
        dispatchStateUpdates();
      }
    } catch (e) {}
  }

  async function fetchCommands() {
    try {
      const res = await fetch(`${getApiBase()}/api/mission/commands?limit=20`);
      if (res.ok) {
        cachedCommands = await res.json();
        if (window.MMCLanderView) {
          window.MMCLanderView.updateCommands(cachedCommands);
        }
      }
    } catch (e) {}
  }

  async function fetchEvents() {
    try {
      const res = await fetch(`${getApiBase()}/api/mission/events?limit=20`);
      if (res.ok) {
        cachedEvents = await res.json();
        if (window.MMCLanderView) {
          window.MMCLanderView.updateEvents(cachedEvents);
        }
      }
    } catch (e) {}
  }

  async function fetchTelemetryHistory() {
    try {
      const res = await fetch(`${getApiBase()}/api/mission/telemetry/history?limit=20`);
      if (res.ok) {
        cachedTelemetryHistory = await res.json();
        if (window.MMCLanderView) {
          window.MMCLanderView.updateTelemetryHistory(cachedTelemetryHistory);
        }
      }
    } catch (e) {}
  }

  async function fetchRover() {
    try {
      const res = await fetch(`${getApiBase()}/api/rover/status`);
      if (res.ok) {
        cachedRover = await res.json();
        if (window.MMCRoverView) {
          window.MMCRoverView.update(cachedRover);
        }
        if (window.MMCLandingView) {
          window.MMCLandingView.update(cachedState, cachedRover, cachedDrone);
        }
      }
    } catch (e) {}
  }

  async function fetchDrone() {
    try {
      const res = await fetch(`${getApiBase()}/api/drone/status`);
      if (res.ok) {
        cachedDrone = await res.json();
        if (window.MMCDroneView) {
          window.MMCDroneView.update(cachedDrone);
        }
        if (window.MMCLandingView) {
          window.MMCLandingView.update(cachedState, cachedRover, cachedDrone);
        }
      }
    } catch (e) {}
  }

  async function pollAll() {
    await Promise.allSettled([
      fetchState(),
      fetchCommands(),
      fetchEvents(),
      fetchTelemetryHistory(),
      fetchRover(),
      fetchDrone(),
    ]);
  }

  // --- Operator Command Dispatcher ---
  async function sendCommand(commandType) {
    if (isCommandInFlight) {
      if (window.MMCLanderView) {
        window.MMCLanderView.showFeedback('A command is already being dispatched...', true);
      }
      return;
    }

    isCommandInFlight = true;
    if (window.MMCLanderView) {
      window.MMCLanderView.showFeedback(`Dispatching ${commandType}...`, false);
    }

    try {
      const res = await fetch(`${getApiBase()}/api/mission/commands`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command_type: commandType }),
      });

      if (res.ok) {
        const body = await res.json();
        const reqId = body.command && body.command.request_id != null ? `#${body.command.request_id}` : '';
        const msg = `Command ${commandType} accepted ${reqId}`.trim();
        if (window.MMCLanderView) window.MMCLanderView.showFeedback(msg, false);
      } else {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        const reason = err.detail || 'Command rejected by gateway';
        if (window.MMCLanderView) window.MMCLanderView.showFeedback(`Rejected: ${reason}`, true);
      }
    } catch (err) {
      if (window.MMCLanderView) window.MMCLanderView.showFeedback(`Network error: ${err.message}`, true);
    } finally {
      isCommandInFlight = false;
      await Promise.allSettled([fetchCommands(), fetchState(), fetchEvents()]);
    }
  }

  async function resetSession() {
    if (isCommandInFlight) return;
    isCommandInFlight = true;

    if (window.MMCLanderView) {
      window.MMCLanderView.showFeedback('Resetting exhibition session...', false);
    }

    try {
      const res = await fetch(`${getApiBase()}/api/mission/session/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (res.ok) {
        if (window.MMCLanderView) {
          window.MMCLanderView.showFeedback('Exhibition session reset. Awaiting fresh telemetry.', false);
        }
      } else {
        if (window.MMCLanderView) {
          window.MMCLanderView.showFeedback('Failed to reset exhibition session.', true);
        }
      }
    } catch (err) {
      if (window.MMCLanderView) {
        window.MMCLanderView.showFeedback(`Reset failed: ${err.message}`, true);
      }
    } finally {
      isCommandInFlight = false;
      await pollAll();
    }
  }

  // --- Periodic Polling Loop ---
  // Background polling keeps tables & event logs fresh regardless of socket status
  setInterval(pollAll, 3000);

  // Initial connection
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      connectWebSocket();
      pollAll();
    });
  } else {
    connectWebSocket();
    pollAll();
  }

  // Export Central Client
  window.MMCMissionClient = {
    sendCommand,
    resetSession,
    pollAll,
    getState: () => cachedState,
    getTelemetry: () => cachedTelemetry,
    getRover: () => cachedRover,
    getDrone: () => cachedDrone,
  };
})();
