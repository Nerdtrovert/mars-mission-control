/**
 * Mars Mission Control — Exhibition Dashboard Controller
 * Local-First, Zero-Dependency Architecture.
 */

(function () {
  'use strict';

  // --- State Cache ---
  let currentState = {
    mode: 'UNKNOWN',
    gateway_state: 'NOT_CONNECTED',
    device_state: 'NOT_CONNECTED',
    last_telemetry_timestamp_ms: null,
    last_telemetry: null,
    last_telemetry_time: null,
    last_device_status_timestamp_ms: null,
    bmp280_ok: null,
    dht11_ok: null,
    simulation_mode: false,
    updated_at: null
  };

  let recentCommands = [];
  let recentEvents = [];
  let telemetryHistory = [];
  let isCommandInFlight = false;
  let ws = null;
  let wsReconnectTimer = null;
  let pollingInterval = null;
  let isWsConnected = false;
  let hasLiveTelemetry = false;
  let latestDisplayedReceivedAtMs = null;

  const UPTIME_DIAGNOSTIC_LIMIT = 250;
  const uptimeDiagnosticEntries = [];
  let uptimeDiagnosticSequence = 0;

  function isUptimeDiagnosticEnabled(search) {
    return new URLSearchParams(search).get('uptimeDiag') === '1';
  }

  function appendUptimeDiagnostic(entries, record, limit = UPTIME_DIAGNOSTIC_LIMIT) {
    entries.push(record);
    if (entries.length > limit) entries.splice(0, entries.length - limit);
  }

  const uptimeDiagnosticsEnabled = isUptimeDiagnosticEnabled(window.location.search);
  if (uptimeDiagnosticsEnabled) {
    window.__MARS_UPTIME_DIAGNOSTICS__ = {
      entries: uptimeDiagnosticEntries,
      clear() {
        uptimeDiagnosticEntries.length = 0;
      },
      print() {
        console.table(uptimeDiagnosticEntries);
        return uptimeDiagnosticEntries;
      },
      exportJson() {
        return JSON.stringify(uptimeDiagnosticEntries, null, 2);
      }
    };
  }

  function completeUptimeDiagnostic(record, rejectionReason = null, rendered = false) {
    if (!record) return;

    record.rejection_reason = rejectionReason;
    record.render_completed = rendered;
    record.uptime_after_render = elEspUptime.textContent;
    appendUptimeDiagnostic(uptimeDiagnosticEntries, record);

    if (rendered) {
      // This callback indicates an animation-frame opportunity after the DOM update,
      // not proof that the value was visibly painted on screen.
      requestAnimationFrame(() => {
        record.next_animation_frame_perf_ms = performance.now();
        record.uptime_at_next_animation_frame = elEspUptime.textContent;
        record.visibility_at_next_animation_frame = document.visibilityState;
      });
    }
  }

  // --- DOM Elements ---
  const elClock = document.getElementById('clock-display');
  const elWsBadge = document.getElementById('ws-status-badge');
  const elGwBadge = document.getElementById('gw-status-badge');
  const elDevBadge = document.getElementById('device-status-badge');
  const elModeBadge = document.getElementById('mode-badge');
  const elOfflineBanner = document.getElementById('offline-banner');

  const elLanderMode = document.getElementById('lander-mode-display');
  const elBtnStatus = document.getElementById('btn-get-status');
  const elBtnActive = document.getElementById('btn-set-active');
  const elBtnStandby = document.getElementById('btn-set-standby');
  const elBtnReset = document.getElementById('btn-reset-session');
  const elControlNotice = document.getElementById('control-status-notice');

  const elLiveIndicator = document.getElementById('telemetry-live-indicator');
  const elBmpTemp = document.getElementById('val-bmp-temp');
  const elBmpPress = document.getElementById('val-bmp-press');
  const elDhtTemp = document.getElementById('val-dht-temp');
  const elDhtHum = document.getElementById('val-dht-hum');
  const elEspUptime = document.getElementById('val-esp32-uptime');
  const elLastReceived = document.getElementById('val-last-received');

  const elHealthBmpTemp = document.getElementById('health-bmp-temp');
  const elHealthBmpPress = document.getElementById('health-bmp-press');
  const elHealthDhtTemp = document.getElementById('health-dht-temp');
  const elHealthDhtHum = document.getElementById('health-dht-hum');

  const elCommandsTbody = document.getElementById('commands-audit-tbody');
  const elTelemetryTbody = document.getElementById('telemetry-history-tbody');
  const elEventsTbody = document.getElementById('events-log-tbody');

  const elResetModal = document.getElementById('modal-reset-session');
  const elModalCancel = document.getElementById('modal-btn-cancel');
  const elModalConfirm = document.getElementById('modal-btn-confirm');

  const roverElements = {
    connection: document.getElementById('rover-connection'),
    source: document.getElementById('rover-source'),
    lastSeen: document.getElementById('rover-last-seen'),
    distance: document.getElementById('rover-distance'),
    attitude: document.getElementById('rover-attitude'),
    command: document.getElementById('rover-command'),
    mode: document.getElementById('rover-mode'),
    event: document.getElementById('rover-event')
  };

  function renderRoverStatus(rover) {
    if (!rover || rover.rover_id !== 'mars-rover-01') return;
    const online = rover.connection_state === 'ONLINE';
    roverElements.connection.textContent = online ? 'ONLINE' : 'OFFLINE';
    roverElements.connection.className = 'rover-connection ' + (online ? 'online' : 'offline');
    roverElements.source.textContent = rover.source === 'simulator' ? 'SIMULATED DATA' : 'NETWORK / HARDWARE';
    roverElements.lastSeen.textContent = rover.last_seen
      ? `LAST VALID PACKET ${formatTimeIST(rover.last_seen)} IST${online ? '' : ' • STALE'}`
      : 'NO VALID PACKETS';
    roverElements.distance.textContent = rover.distance_cm == null ? '--' : Number(rover.distance_cm).toFixed(1);
    roverElements.attitude.textContent = rover.pitch_deg == null || rover.roll_deg == null
      ? '-- / --'
      : `${Number(rover.pitch_deg).toFixed(1)} / ${Number(rover.roll_deg).toFixed(1)}`;
    roverElements.command.textContent = rover.command || '--';
    roverElements.mode.textContent = rover.mode === 'M' ? 'MANUAL' : rover.mode === 'A' ? 'AUTONOMOUS' : '--';
    roverElements.event.textContent = rover.event || (rover.obstacle_detected ? 'Obstacle detected' : 'No active rover event.');
  }

  // --- Indian Standard Time (IST, UTC+05:30) Timezone Formatters ---
  const istTimeFormatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });

  const istDateTimeFormatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });

  function formatTimeIST(val) {
    if (!val) return '--';
    try {
      const d = val instanceof Date ? val : new Date(val);
      if (isNaN(d.getTime())) return '--';
      return istTimeFormatter.format(d);
    } catch (e) {
      return '--';
    }
  }

  // --- Clock (IST) ---
  function updateClock() {
    const now = new Date();
    elClock.textContent = istDateTimeFormatter.format(now).replace(',', '') + ' IST';
  }
  setInterval(updateClock, 1000);
  updateClock();

  // --- Badge State Helpers ---
  function setConnectionBadge(el, prefix, state) {
    el.className = 'badge';
    const textEl = el.querySelector('.badge-text');
    const s = (state || 'NOT_CONNECTED').toUpperCase();
    textEl.textContent = `${prefix}: ${s}`;

    switch (s) {
      case 'ONLINE':
        el.classList.add('state-online');
        break;
      case 'STALE':
        el.classList.add('state-stale');
        break;
      case 'OFFLINE':
        el.classList.add('state-offline');
        break;
      default:
        el.classList.add('state-not-connected');
    }
  }

  // --- Non-actuating Lander Status Controls ---
  function updateControlAvailability() {
    const gwOnline = currentState.gateway_state === 'ONLINE';
    const devOnline = currentState.device_state === 'ONLINE';
    isCommandInFlight = recentCommands.some(
      c => c.status === 'CREATED' || c.status === 'SENT' || c.status === 'ACKNOWLEDGED'
    );
    const ready = gwOnline && devOnline && !isCommandInFlight;
    elBtnStatus.disabled = !ready;
    elBtnActive.disabled = !ready;
    elBtnStandby.disabled = !ready;
    elControlNotice.textContent = ready ? 'Status and operating-mode commands available.' : 'Gateway or lander unavailable, or command in flight.';
    elControlNotice.style.color = ready ? 'var(--color-green)' : 'var(--color-amber)';
    elLanderMode.textContent = currentState.mode || 'UNKNOWN';
    elLanderMode.className = 'lander-mode-indicator ' + String(currentState.mode || '').toLowerCase();
  }

  // --- Duration Formatter for ESP32 Uptime ---
  function formatUptime(ms) {
    if (ms === undefined || ms === null || isNaN(ms) || ms < 0) {
      return '--';
    }
    const totalSec = Math.floor(ms / 1000);
    const totalHours = Math.floor(totalSec / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    const secs = totalSec % 60;
    const mmss = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    if (totalHours >= 24) {
      const days = Math.floor(totalHours / 24);
      const remHours = totalHours % 24;
      return `${days}d ${String(remHours).padStart(2, '0')}:${mmss}`;
    }
    return `${String(totalHours).padStart(2, '0')}:${mmss}`;
  }

  // History may seed the display, but it must never replace data already
  // received on the live stream. Compare host receipt times, not ESP32 uptime:
  // a genuine reboot resets uptime while its receipt time continues forward.
  function shouldRenderTelemetry(source, receivedAtMs, latestReceivedAtMs, liveTelemetrySeen) {
    if (source === 'history' && liveTelemetrySeen) return false;
    if (Number.isFinite(receivedAtMs) && Number.isFinite(latestReceivedAtMs) &&
        receivedAtMs < latestReceivedAtMs) return false;
    return true;
  }

  function isTelemetryAtOrBeforeStatusWatermark(telemetryTimestampMs, statusTimestampMs) {
    return Number.isFinite(statusTimestampMs) &&
      Number.isFinite(Number(telemetryTimestampMs)) &&
      Number(telemetryTimestampMs) <= statusTimestampMs;
  }

  function isTelemetryOlderThanState(telemetryTimestampMs, stateTimestampMs) {
    return Number.isFinite(stateTimestampMs) &&
      Number.isFinite(Number(telemetryTimestampMs)) &&
      Number(telemetryTimestampMs) < stateTimestampMs;
  }

  // --- Render Telemetry ---
  function renderTelemetry(telem, source = 'live', diagnostic = null) {
    if (diagnostic) {
      diagnostic.render_entered = true;
      diagnostic.uptime_before_render = elEspUptime.textContent;
      diagnostic.status_watermark_at_render = currentState.last_device_status_timestamp_ms;
    }
    if (!telem) {
      completeUptimeDiagnostic(diagnostic, 'missing_telemetry_payload');
      return;
    }

    const recvAt = telem.received_at || currentState.last_telemetry_at;
    const receivedAtMs = recvAt ? new Date(recvAt).getTime() : NaN;
    if (source === 'history') {
      completeUptimeDiagnostic(diagnostic, 'historical_source');
      return;
    }
    if (isTelemetryOlderThanState(telem.timestamp_ms, currentState.last_telemetry_timestamp_ms)) {
      if (diagnostic) diagnostic.telemetry_watermark_rejected = true;
      completeUptimeDiagnostic(diagnostic, 'timestamp_ms_older_than_current_state');
      return;
    }
    const statusTimestamp = currentState.last_device_status_timestamp_ms;
    if (isTelemetryAtOrBeforeStatusWatermark(telem.timestamp_ms, statusTimestamp)) {
      if (diagnostic) diagnostic.status_watermark_rejected = true;
      completeUptimeDiagnostic(diagnostic, 'timestamp_ms_not_newer_than_status_watermark');
      return;
    }
    if (!shouldRenderTelemetry(source, receivedAtMs, latestDisplayedReceivedAtMs, hasLiveTelemetry)) {
      if (diagnostic) diagnostic.receipt_time_order_rejected = true;
      const reason = Number.isFinite(receivedAtMs) && Number.isFinite(latestDisplayedReceivedAtMs) &&
        receivedAtMs < latestDisplayedReceivedAtMs
        ? 'received_at_older_than_latest_displayed'
        : 'should_render_telemetry_rejected';
      completeUptimeDiagnostic(diagnostic, reason);
      return;
    }
    if (Number.isFinite(receivedAtMs)) latestDisplayedReceivedAtMs = receivedAtMs;
    if (source === 'live') hasLiveTelemetry = true;

    // Check freshness: if older than 5 seconds or device not ONLINE, mark HISTORICAL
    const now = Date.now();
    let isLive = false;

    if (recvAt) {
      const recTime = new Date(recvAt).getTime();
      const ageSeconds = (now - recTime) / 1000;
      isLive = ageSeconds < 5.0 && currentState.device_state === 'ONLINE';
      elLastReceived.textContent = formatTimeIST(recvAt);
    } else if (elLastReceived.textContent === '--' || !elLastReceived.textContent) {
      elLastReceived.textContent = '--';
    }

    if (currentState.simulation_mode) {
      elLiveIndicator.textContent = '⚠ SIMULATOR DATA — NOT HARDWARE';
      elLiveIndicator.classList.add('historical-indicator');
      elLiveIndicator.style.color = 'var(--color-amber)';
    } else if (isLive) {
      elLiveIndicator.textContent = '● LIVE TELEMETRY FEED';
      elLiveIndicator.classList.remove('historical-indicator');
      elLiveIndicator.style.color = 'var(--color-green)';
    } else {
      elLiveIndicator.textContent = '⚠ HISTORICAL TELEMETRY (CACHED)';
      elLiveIndicator.classList.add('historical-indicator');
      elLiveIndicator.style.color = 'var(--color-amber)';
    }

    // BMP280
    const bmpTemp = telem.bmp_temperature_c !== undefined && telem.bmp_temperature_c !== null
      ? telem.bmp_temperature_c
      : telem.bmp280_temp_c;
    const bmpPress = telem.pressure_hpa !== undefined && telem.pressure_hpa !== null
      ? telem.pressure_hpa
      : telem.bmp280_pressure_hpa;
    const bmpOk = currentState.bmp280_ok !== null
      ? currentState.bmp280_ok
      : (telem.bmp280_ok !== undefined ? Boolean(telem.bmp280_ok) : (bmpTemp !== null && bmpTemp !== undefined));

    if (bmpOk === true && bmpTemp !== null && bmpTemp !== undefined) {
      elBmpTemp.textContent = Number(bmpTemp).toFixed(1);
      elHealthBmpTemp.textContent = 'OK';
      elHealthBmpTemp.className = 'metric-health ok';
    } else {
      elBmpTemp.textContent = '--';
      elHealthBmpTemp.textContent = 'FAILED';
      elHealthBmpTemp.className = 'metric-health failed';
    }

    if (bmpOk === true && bmpPress !== null && bmpPress !== undefined) {
      elBmpPress.textContent = Number(bmpPress).toFixed(1);
      elHealthBmpPress.textContent = 'OK';
      elHealthBmpPress.className = 'metric-health ok';
    } else {
      elBmpPress.textContent = '--';
      elHealthBmpPress.textContent = 'FAILED';
      elHealthBmpPress.className = 'metric-health failed';
    }

    // DHT11
    const dhtTemp = telem.dht_temperature_c !== undefined && telem.dht_temperature_c !== null
      ? telem.dht_temperature_c
      : telem.dht11_temp_c;
    const dhtHum = telem.humidity_pct !== undefined && telem.humidity_pct !== null
      ? telem.humidity_pct
      : telem.dht11_humidity_pct;
    const dhtOk = currentState.dht11_ok !== null
      ? currentState.dht11_ok
      : (telem.dht11_ok !== undefined ? Boolean(telem.dht11_ok) : (dhtTemp !== null && dhtTemp !== undefined));

    if (dhtOk === true && dhtTemp !== null && dhtTemp !== undefined) {
      elDhtTemp.textContent = Number(dhtTemp).toFixed(1);
      elHealthDhtTemp.textContent = 'OK';
      elHealthDhtTemp.className = 'metric-health ok';
    } else {
      elDhtTemp.textContent = '--';
      elHealthDhtTemp.textContent = 'FAILED';
      elHealthDhtTemp.className = 'metric-health failed';
    }

    if (dhtOk === true && dhtHum !== null && dhtHum !== undefined) {
      elDhtHum.textContent = Number(dhtHum).toFixed(1);
      elHealthDhtHum.textContent = 'OK';
      elHealthDhtHum.className = 'metric-health ok';
    } else {
      elDhtHum.textContent = '--';
      elHealthDhtHum.textContent = 'FAILED';
      elHealthDhtHum.className = 'metric-health failed';
    }

    if (currentState.simulation_mode) {
      const simulatedSensorStatus = (healthy) => healthy ? 'SIM · OK' : 'SIM · FAILED';
      [
        [elHealthBmpTemp, bmpOk && bmpTemp !== null && bmpTemp !== undefined],
        [elHealthBmpPress, bmpOk && bmpPress !== null && bmpPress !== undefined],
        [elHealthDhtTemp, dhtOk && dhtTemp !== null && dhtTemp !== undefined],
        [elHealthDhtHum, dhtOk && dhtHum !== null && dhtHum !== undefined]
      ].forEach(([el, healthy]) => {
        el.textContent = simulatedSensorStatus(healthy);
        el.className = healthy ? 'metric-health ok' : 'metric-health failed';
      });
    }
    // Uptime formatted as duration (HH:MM:SS or Xd HH:MM:SS)
    if (telem.timestamp_ms !== undefined && telem.timestamp_ms !== null) {
      elEspUptime.textContent = formatUptime(telem.timestamp_ms);
    } else {
      elEspUptime.textContent = '--';
    }
    completeUptimeDiagnostic(diagnostic, null, true);
  }

  // --- Render Commands Table ---
  function renderCommands(commands) {
    if (!commands || commands.length === 0) {
      elCommandsTbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
            No commands recorded in this session.
          </td>
        </tr>`;
      return;
    }

    elCommandsTbody.innerHTML = commands.map(cmd => {
      const statusClass = `pill-${(cmd.status || '').toLowerCase()}`;
      const shortId = (cmd.command_id || '').substring(0, 8);
      const reqId = cmd.request_id !== null && cmd.request_id !== undefined ? `#${cmd.request_id}` : '—';
      const created = formatTimeIST(cmd.created_at);
      let ackText = '—';
      if (cmd.status === 'REJECTED') {
        ackText = '✖ Rejected';
      } else if (cmd.acknowledged_at || cmd.status === 'ACKNOWLEDGED' || cmd.status === 'COMPLETED') {
        ackText = '✔ Accepted';
      }
      const outcome = cmd.error_reason || cmd.error_message || (cmd.completed_at ? 'Completed' : '—');
      const actionName = cmd.name || cmd.command_type || cmd.command || '—';

      return `
        <tr>
          <td style="font-family: var(--font-mono); font-weight: 600;" title="${cmd.command_id}">${shortId}…</td>
          <td><strong>${actionName}</strong></td>
          <td><span class="status-pill ${statusClass}">${cmd.status}</span></td>
          <td style="font-family: var(--font-mono);">${reqId}</td>
          <td style="font-family: var(--font-mono);">${created}</td>
          <td>${ackText}</td>
          <td style="color: ${(cmd.error_reason || cmd.error_message) ? 'var(--color-red)' : 'var(--text-secondary)'}; font-size: 0.8rem;">
            ${outcome}
          </td>
        </tr>`;
    }).join('');
  }

  function latestTelemetryRows(history, limit = 15) {
    if (!Array.isArray(history) || limit <= 0) return [];
    return history.slice(-limit).reverse();
  }

  // --- Render Telemetry History Table ---
  function renderTelemetryHistory(history) {
    if (!history || history.length === 0) {
      elTelemetryTbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
            Awaiting telemetry samples...
          </td>
        </tr>`;
      return;
    }

    elTelemetryTbody.innerHTML = latestTelemetryRows(history).map(row => {
      const ts = formatTimeIST(row.received_at);
      const rawBTemp = row.bmp_temperature_c !== undefined && row.bmp_temperature_c !== null ? row.bmp_temperature_c : row.bmp280_temp_c;
      const rawPress = row.pressure_hpa !== undefined && row.pressure_hpa !== null ? row.pressure_hpa : row.bmp280_pressure_hpa;
      const rawDTemp = row.dht_temperature_c !== undefined && row.dht_temperature_c !== null ? row.dht_temperature_c : row.dht11_temp_c;
      const rawHum = row.humidity_pct !== undefined && row.humidity_pct !== null ? row.humidity_pct : row.dht11_humidity_pct;

      const bTemp = (rawBTemp !== null && rawBTemp !== undefined) ? `${Number(rawBTemp).toFixed(1)}°C` : '—';
      const press = (rawPress !== null && rawPress !== undefined) ? `${Number(rawPress).toFixed(1)} hPa` : '—';
      const dTemp = (rawDTemp !== null && rawDTemp !== undefined) ? `${Number(rawDTemp).toFixed(1)}°C` : '—';
      const hum = (rawHum !== null && rawHum !== undefined) ? `${Number(rawHum).toFixed(1)}%` : '—';

      return `
        <tr>
          <td style="font-family: var(--font-mono);">${ts}</td>
          <td><span class="status-pill">${row.mode || 'UNKNOWN'}</span></td>
          <td>${bTemp}</td>
          <td>${press}</td>
          <td>${dTemp}</td>
          <td>${hum}</td>
        </tr>`;
    }).join('');
  }

  // --- Render Events Table ---
  function renderEvents(events) {
    if (!events || events.length === 0) {
      elEventsTbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">
            No mission events recorded.
          </td>
        </tr>`;
      return;
    }

    elEventsTbody.innerHTML = events.slice(0, 15).map(ev => {
      const ts = formatTimeIST(ev.timestamp);
      const sevClass = `sev-${(ev.severity || 'info').toLowerCase()}`;
      const comp = ev.subsystem || ev.component || 'system';

      return `
        <tr>
          <td style="font-family: var(--font-mono);">${ts}</td>
          <td style="font-family: var(--font-mono); font-size: 0.8rem;">${ev.event_type}</td>
          <td><span class="severity-pill ${sevClass}">${ev.severity}</span></td>
          <td>${comp}</td>
          <td style="font-size: 0.8rem;">${ev.description}</td>
        </tr>`;
    }).join('');
  }

  // --- Process Unified Mission State ---
  function applyMissionState(stateData) {
    if (!stateData) return;

    const incomingUpdatedAt = stateData.updated_at ? new Date(stateData.updated_at).getTime() : NaN;
    const currentUpdatedAt = currentState.updated_at ? new Date(currentState.updated_at).getTime() : NaN;
    if (Number.isFinite(incomingUpdatedAt) && Number.isFinite(currentUpdatedAt) &&
        incomingUpdatedAt < currentUpdatedAt) return;
    if (Number.isFinite(incomingUpdatedAt)) currentState.updated_at = stateData.updated_at;

    currentState.mode = stateData.mode || currentState.mode;
    currentState.gateway_state = stateData.gateway_state || currentState.gateway_state;
    currentState.device_state = stateData.device_state || currentState.device_state;
    if (stateData.last_telemetry_timestamp_ms !== undefined) {
      currentState.last_telemetry_timestamp_ms = stateData.last_telemetry_timestamp_ms;
    }
    if (stateData.last_device_status_timestamp_ms !== undefined) {
      currentState.last_device_status_timestamp_ms = stateData.last_device_status_timestamp_ms;
    }
    if (stateData.bmp280_ok === true || stateData.bmp280_ok === false) {
      currentState.bmp280_ok = stateData.bmp280_ok;
      if (!stateData.bmp280_ok) {
        elBmpTemp.textContent = '--';
        elBmpPress.textContent = '--';
        elHealthBmpTemp.textContent = 'FAILED';
        elHealthBmpPress.textContent = 'FAILED';
        elHealthBmpTemp.className = 'metric-health failed';
        elHealthBmpPress.className = 'metric-health failed';
      }
    }
    if (stateData.dht11_ok === true || stateData.dht11_ok === false) {
      currentState.dht11_ok = stateData.dht11_ok;
      if (!stateData.dht11_ok) {
        elDhtTemp.textContent = '--';
        elDhtHum.textContent = '--';
        elHealthDhtTemp.textContent = 'FAILED';
        elHealthDhtHum.textContent = 'FAILED';
        elHealthDhtTemp.className = 'metric-health failed';
        elHealthDhtHum.className = 'metric-health failed';
      }
    }
    if (typeof stateData.simulation_mode === 'boolean') {
      currentState.simulation_mode = stateData.simulation_mode;
    }

    // Header Badges
    setConnectionBadge(elGwBadge, 'GATEWAY', currentState.gateway_state);
    setConnectionBadge(elDevBadge, 'LANDER', currentState.device_state);

    const modeText = elModeBadge.querySelector('.badge-text');
    modeText.textContent = currentState.simulation_mode ? 'DATA: SIMULATOR' : `MODE: ${currentState.mode}`;
    elModeBadge.className = 'badge ' + (currentState.simulation_mode ? 'state-stale' : 'state-online');

    // Latest Telemetry if present in state snapshot
    if (stateData.last_telemetry) {
      renderTelemetry(stateData.last_telemetry, 'snapshot');
    }

    updateControlAvailability();
  }

  // --- API Fetch Polling Fallback ---
  async function pollMissionData() {
    try {
      const [resState, resCmds, resEvents, resTelem, resRover] = await Promise.all([
        fetch('/api/mission/state'),
        fetch('/api/mission/commands'),
        fetch('/api/mission/events'),
        fetch('/api/mission/telemetry/history'),
        fetch('/api/rover/status')
      ]);

      if (resState.ok) {
        const state = await resState.json();
        applyMissionState(state);
      }
      if (resCmds.ok) {
        recentCommands = await resCmds.json();
        renderCommands(recentCommands);
        updateControlAvailability();
      }
      if (resEvents.ok) {
        recentEvents = await resEvents.json();
        renderEvents(recentEvents);
      }
      if (resTelem.ok) {
        telemetryHistory = await resTelem.json();
        renderTelemetryHistory(telemetryHistory);
      }
      if (resRover.ok) renderRoverStatus(await resRover.json());

      // Successful poll clears any stale connection disruption warning
      elOfflineBanner.classList.add('hidden');
    } catch (err) {
      console.warn('Dashboard poll error:', err);
      elOfflineBanner.classList.remove('hidden');
    }
  }

  // --- WebSocket Connection ---
  function connectWebSocket() {
    if (ws) {
      try { ws.close(); } catch (e) {}
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    ws = new WebSocket(wsUrl);

    ws.onopen = function () {
      isWsConnected = true;
      elWsBadge.className = 'badge state-ws-connected';
      elWsBadge.querySelector('.badge-text').textContent = 'WS: CONNECTED';
      elOfflineBanner.classList.add('hidden');

      // Clear any reconnect retry timer
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }

      // Initial data fetch
      pollMissionData();
    };

    ws.onmessage = function (event) {
      const wsReceivedPerfMs = uptimeDiagnosticsEnabled ? performance.now() : null;
      try {
        const msg = JSON.parse(event.data);
        if (!msg) return;

        if (msg.type === 'state_snapshot') {
          applyMissionState(msg.data);
        } else if (msg.type === 'telemetry') {
          const diagnostic = uptimeDiagnosticsEnabled ? {
            sequence: ++uptimeDiagnosticSequence,
            timestamp_ms: msg.telemetry ? msg.telemetry.timestamp_ms : null,
            received_at: msg.telemetry ? msg.telemetry.received_at : null,
            ws_received_performance_ms: wsReceivedPerfMs,
            visibility_at_ws_receipt: document.visibilityState,
            status_watermark_before_state: currentState.last_device_status_timestamp_ms,
            render_entered: false,
            status_watermark_rejected: false,
            telemetry_watermark_rejected: false,
            receipt_time_order_rejected: false,
            uptime_before_render: elEspUptime.textContent,
            uptime_after_render: null,
            rejection_reason: null
          } : null;
          if (msg.state) {
            applyMissionState(msg.state);
          }
          if (msg.telemetry) {
            renderTelemetry(msg.telemetry, 'live', diagnostic);
          } else if (diagnostic) {
            completeUptimeDiagnostic(diagnostic, 'missing_telemetry_payload');
          }
        } else if (msg.type === 'rover_telemetry') {
          renderRoverStatus(msg.rover);
        } else if (msg.type === 'command_update') {
          pollMissionData();
        } else if (msg.type === 'event') {
          pollMissionData();
        }
      } catch (e) {
        console.error('Failed to parse WS message:', e);
      }
    };

    ws.onclose = function () {
      isWsConnected = false;
      elWsBadge.className = 'badge state-offline';
      elWsBadge.querySelector('.badge-text').textContent = 'WS: DISCONNECTED (POLLING)';
      elOfflineBanner.classList.remove('hidden');

      // Schedule reconnect
      if (!wsReconnectTimer) {
        wsReconnectTimer = setTimeout(connectWebSocket, 3000);
      }
    };

    ws.onerror = function () {
      isWsConnected = false;
      elWsBadge.className = 'badge state-offline';
      elWsBadge.querySelector('.badge-text').textContent = 'WS: ERROR';
      elOfflineBanner.classList.remove('hidden');
    };
  }

  // --- Command Dispatch ---
  async function sendCommand(commandType) {
    if (isCommandInFlight && commandType !== 'GET_STATUS') {
      alert('Another command is currently in flight.');
      return;
    }

    try {
      const res = await fetch('/api/mission/commands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command_type: commandType })
      });

      const data = await res.json();
      if (!res.ok) {
        const errMsg = data.detail || `Command rejected with status ${res.status}`;
        alert(`Command Failed: ${errMsg}`);
      } else {
        // Refresh immediately to show CREATED/SENT state
        pollMissionData();
      }
    } catch (err) {
      alert(`Network error sending command: ${err.message}`);
    }
  }

  // --- Reset Session ---
  async function resetSession() {
    try {
      const res = await fetch('/api/mission/session/reset', {
        method: 'POST'
      });
      if (res.ok) {
        elLastReceived.textContent = '--';
        pollMissionData();
      } else {
        alert('Failed to reset mission session.');
      }
    } catch (err) {
      alert(`Network error during reset: ${err.message}`);
    }
  }

  // --- Event Listeners ---
  elBtnStatus.addEventListener('click', () => sendCommand('GET_STATUS'));
  elBtnActive.addEventListener('click', () => sendCommand('SET_ACTIVE'));
  elBtnStandby.addEventListener('click', () => sendCommand('SET_STANDBY'));

  elBtnReset.addEventListener('click', () => {
    elResetModal.classList.remove('hidden');
  });

  elModalCancel.addEventListener('click', () => {
    elResetModal.classList.add('hidden');
  });

  elModalConfirm.addEventListener('click', () => {
    elResetModal.classList.add('hidden');
    resetSession();
  });

  // --- Initialization ---
  connectWebSocket();

  // Baseline polling loop ensures background refresh regardless of WS status
  pollingInterval = setInterval(pollMissionData, 2000);
  pollMissionData();

})();
