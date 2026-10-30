/**
 * Mars Mission Control — Lander Dashboard Controller
 * frontend-college/js/lander-view.js
 *
 * Full integration with Mission Control Backend & WebSocket streams.
 */

(function () {
  'use strict';

  // --- Clock Updater for Lander Dashboard ---
  const elLanderClock = document.getElementById('lander-clock-display');

  function updateLanderClock() {
    if (elLanderClock && window.MMCFormatters) {
      elLanderClock.textContent = window.MMCFormatters.formatTimeIST(new Date()) + ' IST';
    }
  }

  setInterval(updateLanderClock, 1000);
  updateLanderClock();

  // --- View Navigation ---
  const landingView = document.getElementById('landing-view');
  const landerView = document.getElementById('lander-view');
  const btnBackOverview = document.getElementById('btn-back-overview');

  function navigateToLanding() {
    if (landingView && landerView) {
      landerView.classList.add('hidden');
      landingView.classList.remove('hidden');
      window.location.hash = '#landing';
      window.scrollTo(0, 0);
    }
  }

  if (btnBackOverview) {
    btnBackOverview.addEventListener('click', (e) => {
      e.preventDefault();
      navigateToLanding();
    });
  }

  const btnTabToRover = document.getElementById('btn-tab-lander-to-rover');
  if (btnTabToRover) {
    btnTabToRover.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.MMCRoverView) window.MMCRoverView.show();
    });
  }

  const btnTabToDrone = document.getElementById('btn-tab-lander-to-drone');
  if (btnTabToDrone) {
    btnTabToDrone.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.MMCDroneView) window.MMCDroneView.show();
    });
  }

  // --- DOM Elements ---
  const elStatusDisplay = document.getElementById('lander-status-display');
  const elBadgeActive = document.getElementById('state-badge-active');
  const elBadgeInactive = document.getElementById('state-badge-inactive');
  const elBadgeUnrecognized = document.getElementById('state-badge-unrecognized');

  const elSpecLink = document.getElementById('lander-spec-link');
  const elSpecHandshake = document.getElementById('lander-spec-handshake');
  const elInterlockNotice = document.getElementById('lander-interlock-notice');

  const elBmpTemp = document.getElementById('val-lander-bmp-temp');
  const elHealthBmpTemp = document.getElementById('health-lander-bmp-temp');
  const elBmpPress = document.getElementById('val-lander-bmp-press');
  const elHealthBmpPress = document.getElementById('health-lander-bmp-press');

  const elDhtTemp = document.getElementById('val-lander-dht-temp');
  const elHealthDhtTemp = document.getElementById('health-lander-dht-temp');
  const elDhtHum = document.getElementById('val-lander-dht-hum');
  const elHealthDhtHum = document.getElementById('health-lander-dht-hum');

  const elUptime = document.getElementById('val-lander-esp32-uptime');
  const elLastIngestion = document.getElementById('val-lander-last-ingestion');

  const elGwPill = document.getElementById('lander-gw-pill');
  const elGwDot = document.getElementById('lander-gw-dot');
  const elGwText = document.getElementById('lander-gw-text');

  const elDevPill = document.getElementById('lander-dev-pill');
  const elDevDot = document.getElementById('lander-dev-dot');
  const elDevText = document.getElementById('lander-dev-text');

  const elModeText = document.getElementById('lander-mode-text');

  const elTbodyCommands = document.getElementById('tbody-lander-commands');
  const elTbodyTelemetry = document.getElementById('tbody-lander-telemetry');
  const elTbodyEvents = document.getElementById('tbody-lander-events');

  const btnStatus = document.getElementById('btn-cmd-status');
  const btnActive = document.getElementById('btn-cmd-active');
  const btnStandby = document.getElementById('btn-cmd-standby');
  const btnReset = document.getElementById('btn-cmd-reset');
  const elControlNotice = document.getElementById('lander-control-notice');
  const feedbackToast = document.getElementById('lander-control-feedback');

  let feedbackTimer = null;

  function showFeedback(msg, isError = false) {
    if (!feedbackToast) return;
    if (feedbackTimer) {
      clearTimeout(feedbackTimer);
      feedbackTimer = null;
    }
    feedbackToast.textContent = msg;
    feedbackToast.style.borderColor = isError ? 'var(--red-400)' : 'var(--green-400)';
    feedbackToast.style.color = isError ? '#fca5a5' : '#86efac';
    feedbackToast.classList.add('show');
    feedbackTimer = setTimeout(() => {
      feedbackToast.classList.remove('show');
    }, 4500);
  }

  // Bind Diagnostic Control Buttons
  if (btnStatus) {
    btnStatus.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.MMCMissionClient) {
        window.MMCMissionClient.sendCommand('GET_STATUS');
      }
    });
  }

  if (btnActive) {
    btnActive.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.MMCMissionClient) {
        window.MMCMissionClient.sendCommand('SET_ACTIVE');
      }
    });
  }

  if (btnStandby) {
    btnStandby.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.MMCMissionClient) {
        window.MMCMissionClient.sendCommand('SET_STANDBY');
      }
    });
  }

  if (btnReset) {
    btnReset.addEventListener('click', (e) => {
      e.preventDefault();
      if (confirm('Are you sure you want to reset this exhibition session? This clears historical telemetry and command logs.')) {
        if (window.MMCMissionClient) {
          window.MMCMissionClient.resetSession();
        }
      }
    });
  }

  // --- Render State & Telemetry ---
  function update(state, telemetry) {
    if (!state) return;

    const gwState = (state.gateway_state || 'NOT_CONNECTED').toUpperCase();
    const devState = (state.device_state || 'NOT_CONNECTED').toUpperCase();
    const mode = (state.mode || 'UNKNOWN').toUpperCase();
    const isOnline = devState === 'ONLINE';

    // 1. Update Header Pills
    if (elGwText && elGwDot) {
      elGwText.textContent = `GATEWAY: ${gwState}`;
      elGwDot.className = 'pill-dot ' + (gwState === 'ONLINE' ? 'online' : (gwState === 'STALE' ? 'stale' : 'offline'));
    }
    if (elDevText && elDevDot) {
      elDevText.textContent = `LANDER: ${devState}`;
      elDevDot.className = 'pill-dot ' + (devState === 'ONLINE' ? 'online' : (devState === 'STALE' ? 'stale' : 'offline'));
    }
    if (elModeText) {
      elModeText.textContent = `MODE: ${mode}`;
    }

    // 2. Authoritative Status Display
    if (elStatusDisplay) {
      elStatusDisplay.className = 'status-state-display ';
      if (devState === 'ONLINE') {
        if (mode === 'ACTIVE') {
          elStatusDisplay.textContent = 'ACTIVE';
          elStatusDisplay.classList.add('status-state-active');
        } else {
          elStatusDisplay.textContent = 'STANDBY';
          elStatusDisplay.classList.add('status-state-unrecognized');
        }
      } else if (devState === 'OFFLINE') {
        elStatusDisplay.textContent = 'NOT ACTIVE';
        elStatusDisplay.classList.add('status-state-inactive');
      } else {
        elStatusDisplay.textContent = 'UNRECOGNIZED';
        elStatusDisplay.classList.add('status-state-unrecognized');
      }
    }

    // 3. Highlight Matching State Badge
    if (elBadgeActive && elBadgeInactive && elBadgeUnrecognized) {
      elBadgeActive.className = 'state-badge-item state-active-option';
      elBadgeInactive.className = 'state-badge-item state-inactive-option';
      elBadgeUnrecognized.className = 'state-badge-item';

      if (devState === 'ONLINE' && mode === 'ACTIVE') {
        elBadgeActive.classList.add('current-unrecognized');
      } else if (devState === 'OFFLINE' || mode === 'STANDBY') {
        elBadgeInactive.classList.add('current-unrecognized');
      } else {
        elBadgeUnrecognized.classList.add('current-unrecognized');
      }
    }

    // 4. Specs
    if (elSpecLink) {
      elSpecLink.textContent = devState;
      elSpecLink.style.color = isOnline ? 'var(--green-400)' : 'var(--amber-400)';
    }
    if (elSpecHandshake) {
      const handshake = isOnline ? 'VERIFIED' : (gwState === 'ONLINE' ? 'AWAITING ESP32' : 'DISCONNECTED');
      elSpecHandshake.textContent = handshake;
      elSpecHandshake.style.color = isOnline ? 'var(--green-400)' : 'var(--amber-400)';
    }

    if (elInterlockNotice) {
      elInterlockNotice.textContent = isOnline
        ? `Lander connected and streaming nominal telemetry over Wi-Fi TCP port 5006.`
        : `Lander state is ${devState}. Handshake unverified until telemetry arrives.`;
      elInterlockNotice.style.color = isOnline ? 'var(--green-400)' : 'var(--amber-400)';
    }

    // 5. Update Telemetry Metrics
    const telem = telemetry || state.last_telemetry;
    if (telem) {
      // BMP280
      const bmpTemp = telem.bmp_temperature_c != null ? telem.bmp_temperature_c : telem.bmp280_temp_c;
      const bmpPress = telem.pressure_hpa != null ? telem.pressure_hpa : telem.bmp280_pressure_hpa;
      const bmpOk = state.bmp280_ok !== null ? state.bmp280_ok : telem.bmp280_ok;

      if (bmpOk === true && bmpTemp != null) {
        if (elBmpTemp) elBmpTemp.textContent = Number(bmpTemp).toFixed(1);
        if (elHealthBmpTemp) {
          elHealthBmpTemp.textContent = 'OK';
          elHealthBmpTemp.className = 'metric-health ok';
        }
      } else {
        if (elBmpTemp) elBmpTemp.textContent = '--';
        if (elHealthBmpTemp) {
          elHealthBmpTemp.textContent = 'FAILED';
          elHealthBmpTemp.className = 'metric-health failed';
        }
      }

      if (bmpOk === true && bmpPress != null) {
        if (elBmpPress) elBmpPress.textContent = Number(bmpPress).toFixed(1);
        if (elHealthBmpPress) {
          elHealthBmpPress.textContent = 'OK';
          elHealthBmpPress.className = 'metric-health ok';
        }
      } else {
        if (elBmpPress) elBmpPress.textContent = '--';
        if (elHealthBmpPress) {
          elHealthBmpPress.textContent = 'FAILED';
          elHealthBmpPress.className = 'metric-health failed';
        }
      }

      // DHT11
      const dhtTemp = telem.dht_temperature_c != null ? telem.dht_temperature_c : telem.dht11_temp_c;
      const dhtHum = telem.humidity_pct != null ? telem.humidity_pct : telem.dht11_humidity_pct;
      const dhtOk = state.dht11_ok !== null ? state.dht11_ok : telem.dht11_ok;

      if (dhtOk === true && dhtTemp != null) {
        if (elDhtTemp) elDhtTemp.textContent = Number(dhtTemp).toFixed(1);
        if (elHealthDhtTemp) {
          elHealthDhtTemp.textContent = 'OK';
          elHealthDhtTemp.className = 'metric-health ok';
        }
      } else {
        if (elDhtTemp) elDhtTemp.textContent = '--';
        if (elHealthDhtTemp) {
          elHealthDhtTemp.textContent = 'FAILED';
          elHealthDhtTemp.className = 'metric-health failed';
        }
      }

      if (dhtOk === true && dhtHum != null) {
        if (elDhtHum) elDhtHum.textContent = Number(dhtHum).toFixed(1);
        if (elHealthDhtHum) {
          elHealthDhtHum.textContent = 'OK';
          elHealthDhtHum.className = 'metric-health ok';
        }
      } else {
        if (elDhtHum) elDhtHum.textContent = '--';
        if (elHealthDhtHum) {
          elHealthDhtHum.textContent = 'FAILED';
          elHealthDhtHum.className = 'metric-health failed';
        }
      }

      // Uptime
      if (elUptime && window.MMCFormatters) {
        elUptime.textContent = window.MMCFormatters.formatUptime(telem.timestamp_ms);
      }

      // Last Ingestion Host Time
      if (elLastIngestion && window.MMCFormatters) {
        const recvAt = telem.received_at || state.last_telemetry_at || new Date().toISOString();
        elLastIngestion.textContent = window.MMCFormatters.formatTimeIST(recvAt);
      }
    }

    // 6. Diagnostic Controls Availability
    const controlsReady = gwState === 'ONLINE' && devState === 'ONLINE';
    if (btnStatus) btnStatus.disabled = !controlsReady;
    if (btnActive) btnActive.disabled = !controlsReady || mode === 'ACTIVE';
    if (btnStandby) btnStandby.disabled = !controlsReady || mode === 'STANDBY';

    if (elControlNotice) {
      if (controlsReady) {
        elControlNotice.textContent = `Nominal link established. Status and operating mode commands available.`;
        elControlNotice.style.color = 'var(--green-400)';
      } else {
        elControlNotice.textContent = `Gateway or lander unavailable (${devState}). Commands disabled.`;
        elControlNotice.style.color = 'var(--amber-400)';
      }
    }
  }

  // --- Render Commands Audit Table ---
  function updateCommands(commands) {
    if (!elTbodyCommands) return;
    if (!commands || commands.length === 0) {
      elTbodyCommands.innerHTML = `
        <tr>
          <td colspan="7" class="table-empty-row">No commands recorded in this session.</td>
        </tr>`;
      return;
    }

    elTbodyCommands.innerHTML = commands.map((cmd) => {
      const cmdId = (cmd.command_id || '').substring(0, 8);
      const action = cmd.command_type || cmd.command || '--';
      const status = (cmd.status || '').toUpperCase();
      const reqId = cmd.request_id != null ? `#${cmd.request_id}` : '—';
      const created = window.MMCFormatters ? window.MMCFormatters.formatTimeIST(cmd.created_at) : cmd.created_at;

      let statusBadgeClass = 'badge-status-pending';
      if (status === 'COMPLETED' || status === 'ACKNOWLEDGED') statusBadgeClass = 'badge-status-completed';
      else if (status === 'REJECTED' || status === 'FAILED') statusBadgeClass = 'badge-status-rejected';

      const ackText = (cmd.status === 'REJECTED') ? '✖ Rejected' : (cmd.status === 'COMPLETED' || cmd.status === 'ACKNOWLEDGED' ? '✔ Accepted' : 'Pending');
      const details = cmd.error_message || (cmd.status === 'COMPLETED' ? 'Executed successfully' : (cmd.status || '--'));

      return `
        <tr>
          <td style="font-family: var(--font-mono); color: var(--cyan-400);">${cmdId}</td>
          <td><strong>${action}</strong></td>
          <td><span class="badge-status ${statusBadgeClass}">${status}</span></td>
          <td>${reqId}</td>
          <td>${created}</td>
          <td>${ackText}</td>
          <td style="color: var(--slate-400);">${details}</td>
        </tr>`;
    }).join('');
  }

  // --- Render Telemetry History Table ---
  function updateTelemetryHistory(history) {
    if (!elTbodyTelemetry) return;
    if (!history || history.length === 0) {
      elTbodyTelemetry.innerHTML = `
        <tr>
          <td colspan="6" class="table-empty-row">No historical telemetry recorded.</td>
        </tr>`;
      return;
    }

    elTbodyTelemetry.innerHTML = history.slice(0, 15).map((row) => {
      const timeIST = window.MMCFormatters ? window.MMCFormatters.formatTimeIST(row.received_at) : row.received_at;
      const mode = row.mode || 'ACTIVE';
      const bmpTemp = row.bmp_temperature_c != null ? Number(row.bmp_temperature_c).toFixed(1) + '°C' : '--';
      const bmpPress = row.pressure_hpa != null ? Number(row.pressure_hpa).toFixed(1) + ' hPa' : '--';
      const dhtTemp = row.dht_temperature_c != null ? Number(row.dht_temperature_c).toFixed(1) + '°C' : '--';
      const dhtHum = row.humidity_pct != null ? Number(row.humidity_pct).toFixed(1) + '%' : '--';

      return `
        <tr>
          <td>${timeIST}</td>
          <td><span class="badge-status badge-status-ok">${mode}</span></td>
          <td>${bmpTemp}</td>
          <td>${bmpPress}</td>
          <td>${dhtTemp}</td>
          <td>${dhtHum}</td>
        </tr>`;
    }).join('');
  }

  // --- Render Mission Events Table ---
  function updateEvents(events) {
    if (!elTbodyEvents) return;
    if (!events || events.length === 0) {
      elTbodyEvents.innerHTML = `
        <tr>
          <td colspan="5" class="table-empty-row">No mission events recorded.</td>
        </tr>`;
      return;
    }

    elTbodyEvents.innerHTML = events.slice(0, 15).map((evt) => {
      const timeIST = window.MMCFormatters ? window.MMCFormatters.formatTimeIST(evt.timestamp) : evt.timestamp;
      const type = evt.event_type || 'INFO';
      const sev = (evt.severity || 'INFO').toUpperCase();
      const comp = evt.component || 'SYSTEM';
      const desc = evt.message || evt.description || '--';

      let sevClass = 'badge-status-completed';
      if (sev === 'CRITICAL' || sev === 'ERROR') sevClass = 'badge-status-rejected';
      else if (sev === 'WARN' || sev === 'WARNING') sevClass = 'badge-status-created';

      return `
        <tr>
          <td>${timeIST}</td>
          <td><strong>${type}</strong></td>
          <td><span class="badge-status ${sevClass}">${sev}</span></td>
          <td>${comp}</td>
          <td style="color: var(--slate-300);">${desc}</td>
        </tr>`;
    }).join('');
  }

  // Public View Export
  window.MMCLanderView = {
    show() {
      const roverView = document.getElementById('rover-view');
      const droneView = document.getElementById('drone-view');
      if (landingView && landerView) {
        landingView.classList.add('hidden');
        if (roverView) roverView.classList.add('hidden');
        if (droneView) droneView.classList.add('hidden');
        landerView.classList.remove('hidden');
        window.location.hash = '#lander';
        window.scrollTo(0, 0);
      }
    },
    hide: navigateToLanding,
    update,
    updateCommands,
    updateTelemetryHistory,
    updateEvents,
    showFeedback,
  };
})();
