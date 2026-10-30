/**
 * Mars Mission Control — Surface Rover Dashboard Controller
 * frontend/js/rover-view.js
 *
 * Full integration with Rover Telemetry stream (UDP port 5005 & simulator).
 */

(function () {
  'use strict';

  // --- Clock Updater for Rover Dashboard ---
  const elRoverClock = document.getElementById('rover-clock-display');

  function updateRoverClock() {
    if (elRoverClock && window.MMCFormatters) {
      elRoverClock.textContent = window.MMCFormatters.formatTimeIST(new Date()) + ' IST';
    }
  }

  setInterval(updateRoverClock, 1000);
  updateRoverClock();

  // --- View Panels Reference ---
  const landingView = document.getElementById('landing-view');
  const landerView = document.getElementById('lander-view');
  const roverView = document.getElementById('rover-view');

  function navigateToLanding() {
    if (landingView && roverView) {
      roverView.classList.add('hidden');
      if (landerView) landerView.classList.add('hidden');
      landingView.classList.remove('hidden');
      window.location.hash = '#landing';
      window.scrollTo(0, 0);
    }
  }

  function navigateToLander() {
    if (landerView && roverView) {
      roverView.classList.add('hidden');
      if (landingView) landingView.classList.add('hidden');
      landerView.classList.remove('hidden');
      window.location.hash = '#lander';
      window.scrollTo(0, 0);
    }
  }

  // Bind Navigation Buttons
  const btnRoverBackOverview = document.getElementById('btn-rover-back-overview');
  const btnTabToLander = document.getElementById('btn-tab-rover-to-lander');
  const btnTabToDrone = document.getElementById('btn-tab-rover-to-drone');

  if (btnRoverBackOverview) {
    btnRoverBackOverview.addEventListener('click', (e) => {
      e.preventDefault();
      navigateToLanding();
    });
  }

  if (btnTabToLander) {
    btnTabToLander.addEventListener('click', (e) => {
      e.preventDefault();
      navigateToLander();
    });
  }

  if (btnTabToDrone) {
    btnTabToDrone.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.MMCDroneView) window.MMCDroneView.show();
    });
  }

  // --- DOM Elements ---
  const elConnDot = document.getElementById('rover-conn-dot');
  const elConnText = document.getElementById('rover-conn-text');
  const elSourceText = document.getElementById('rover-source-text');

  const elDistance = document.getElementById('val-rover-distance');
  const elHealthDistance = document.getElementById('health-rover-distance');

  const elRadarFill = document.getElementById('rover-radar-fill');
  const elRadarPill = document.getElementById('rover-radar-pill');
  const elRadarNote = document.getElementById('rover-radar-note');

  const elAttitude = document.getElementById('val-rover-attitude');
  const elHealthAttitude = document.getElementById('health-rover-attitude');

  const elCommand = document.getElementById('val-rover-command');
  const elHealthCommand = document.getElementById('health-rover-command');

  const elMode = document.getElementById('val-rover-mode');
  const elHealthMode = document.getElementById('health-rover-mode');

  const elVoltage = document.getElementById('val-rover-voltage');
  const elHealthVoltage = document.getElementById('health-rover-voltage');

  const elBattery = document.getElementById('val-rover-battery');
  const elHealthBattery = document.getElementById('health-rover-battery');

  const elEventBanner = document.getElementById('rover-event-banner');
  const elAlertBanner = document.getElementById('rover-alert-banner');
  const elBannerIcon = document.getElementById('rover-banner-icon');
  const elBannerText = document.getElementById('rover-banner-text');

  // --- Mars Terrain Map Tactical Canvas (Static Illustration) ---
  const canvas = document.getElementById('terrain-canvas');
  let animationFrameId = null;
  let radarAngle = 0;

  function initTerrainMap() {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
    }

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    function drawTerrain() {
      const w = canvas.getBoundingClientRect().width;
      const h = canvas.getBoundingClientRect().height;
      const cx = w * 0.48;
      const cy = h * 0.52;

      ctx.clearRect(0, 0, w, h);

      // 1. Tactical Gridlines
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.06)';
      ctx.lineWidth = 1;
      const step = 40;
      for (let x = 0; x < w; x += step) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += step) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // 2. Topographic Elevation Contours
      ctx.strokeStyle = 'rgba(224, 86, 56, 0.16)';
      ctx.lineWidth = 1.2;
      const rings = [60, 110, 160, 210];
      rings.forEach((r, idx) => {
        ctx.beginPath();
        ctx.ellipse(cx, cy, r * 1.15, r * 0.75, Math.PI / 12, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = 'rgba(224, 86, 56, 0.35)';
        ctx.font = '9px monospace';
        ctx.fillText(`-${2400 + idx * 50}m`, cx + r * 0.9, cy - r * 0.45);
      });

      // 3. Tactical Range Rings
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.18)';
      ctx.setLineDash([4, 4]);
      [80, 140, 200].forEach((r, idx) => {
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = 'rgba(56, 189, 248, 0.35)';
        ctx.font = '9px monospace';
        ctx.fillText(`${(idx + 1) * 25}m`, cx + 6, cy - r + 12);
      });
      ctx.setLineDash([]);

      // 4. Standby Radar Sweep Arc
      radarAngle = (radarAngle + 0.008) % (Math.PI * 2);
      const gradient = ctx.createRadialGradient(cx, cy, 10, cx, cy, 210);
      gradient.addColorStop(0, 'rgba(56, 189, 248, 0.15)');
      gradient.addColorStop(1, 'transparent');

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, 210, radarAngle, radarAngle + 0.35);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();

      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + Math.cos(radarAngle + 0.35) * 210, cy + Math.sin(radarAngle + 0.35) * 210);
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.restore();

      // 5. Stationary Base Marker (Lander LZ)
      ctx.fillStyle = '#e05638';
      ctx.beginPath();
      ctx.arc(cx - 70, cy + 40, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = '#f1f5f9';
      ctx.font = '10px monospace';
      ctx.fillText('LANDER LZ', cx - 62, cy + 44);

      // 6. Sector Marker
      ctx.fillStyle = '#38bdf8';
      ctx.beginPath();
      ctx.arc(cx + 65, cy - 35, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = '#38bdf8';
      ctx.font = '10px monospace';
      ctx.fillText('ROVER SECTOR 04-JC', cx + 75, cy - 31);

      // 7. Disclaimer
      ctx.fillStyle = 'rgba(148, 163, 184, 0.4)';
      ctx.font = '9px monospace';
      ctx.textAlign = 'right';
      ctx.fillText('STATIC TOPOGRAPHY • NOT LIVE GPS POSITIONING', w - 16, h - 14);
      ctx.textAlign = 'left';

      animationFrameId = requestAnimationFrame(drawTerrain);
    }

    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    animationFrameId = requestAnimationFrame(drawTerrain);
  }

  // --- Render Live Rover Telemetry ---
  function update(rover) {
    if (!rover) return;

    const isOnline = rover.connection_state === 'ONLINE';
    const isSim = rover.source === 'simulator';

    // 1. Connection & Source Badges
    if (elAlertBanner) {
      if (isSim) {
        // In hybrid / simulator mode, suppress connecting alert banner
        elAlertBanner.style.display = 'none';
      } else if (isOnline) {
        elAlertBanner.style.display = 'flex';
        elAlertBanner.className = 'preview-alert-banner banner-nominal';
        if (elBannerIcon) elBannerIcon.innerHTML = '&#x2714;';
        if (elBannerText) elBannerText.innerHTML = '<strong>NOMINAL:</strong> Live telemetry streaming over UDP port 5005.';
      } else {
        elAlertBanner.style.display = 'flex';
        elAlertBanner.className = 'preview-alert-banner banner-disrupted';
        if (elBannerIcon) elBannerIcon.innerHTML = '&#x26A0;';
        if (elBannerText) elBannerText.innerHTML = '<strong>CONNECTING:</strong> Linking to rover telemetry stream (UDP 5005)...';
      }
    }

    if (elConnText && elConnDot) {
      elConnText.textContent = `ROVER: ${isOnline ? 'ONLINE' : 'OFFLINE'}`;
      elConnDot.className = 'pill-dot ' + (isOnline ? 'online' : 'offline');
    }

    if (elSourceText) {
      elSourceText.textContent = isSim ? 'SOURCE: SIMULATOR' : 'SOURCE: HARDWARE';
    }

    // 2. Obstacle Distance & Proximity Radar
    if (rover.distance_cm != null && isOnline) {
      const dist = Number(rover.distance_cm);
      if (elDistance) elDistance.textContent = dist.toFixed(1);
      if (elHealthDistance) {
        elHealthDistance.textContent = dist < 30 ? 'OBSTACLE' : 'CLEAR';
        elHealthDistance.className = 'metric-health ' + (dist < 30 ? 'failed' : 'ok');
      }

      // Radar Bar
      if (elRadarFill) {
        const pct = Math.min(100, Math.max(0, (dist / 200) * 100));
        elRadarFill.style.width = pct + '%';
        elRadarFill.style.background = dist < 30 ? 'var(--red-400)' : (dist < 70 ? 'var(--amber-400)' : 'var(--green-400)');
      }

      if (elRadarPill) {
        if (dist < 30) {
          elRadarPill.textContent = 'RADAR: OBSTACLE DETECTED';
          elRadarPill.style.color = 'var(--red-400)';
          elRadarPill.style.borderColor = 'var(--red-400)';
        } else {
          elRadarPill.textContent = 'RADAR: CLEAR';
          elRadarPill.style.color = 'var(--green-400)';
          elRadarPill.style.borderColor = 'var(--green-400)';
        }
      }

      if (elRadarNote) {
        elRadarNote.textContent = dist < 30
          ? `WARNING: Obstacle at ${dist.toFixed(1)} cm. Drive motion stopped or rerouted.`
          : `Clearance nominal (${dist.toFixed(1)} cm ahead). 5 Hz rangefinder active.`;
      }
    } else {
      if (elDistance) elDistance.textContent = '--';
      if (elHealthDistance) {
        elHealthDistance.textContent = 'STANDBY';
        elHealthDistance.className = 'metric-health standby';
      }
      if (elRadarFill) elRadarFill.style.width = '0%';
      if (elRadarPill) {
        elRadarPill.textContent = 'RADAR: STANDBY';
        elRadarPill.style.color = 'var(--amber-400)';
        elRadarPill.style.borderColor = 'rgba(251, 191, 36, 0.35)';
      }
    }

    // 3. Pitch & Roll Gyro
    if (rover.pitch_deg != null && rover.roll_deg != null && isOnline) {
      if (elAttitude) {
        elAttitude.textContent = `${Number(rover.pitch_deg).toFixed(1)}° / ${Number(rover.roll_deg).toFixed(1)}°`;
      }
      if (elHealthAttitude) {
        elHealthAttitude.textContent = 'OK';
        elHealthAttitude.className = 'metric-health ok';
      }
    } else {
      if (elAttitude) elAttitude.textContent = '-- / --';
      if (elHealthAttitude) {
        elHealthAttitude.textContent = 'STANDBY';
        elHealthAttitude.className = 'metric-health standby';
      }
    }

    // 4. Reported Motion Command
    if (rover.command && isOnline) {
      if (elCommand) elCommand.textContent = rover.command;
      if (elHealthCommand) {
        elHealthCommand.textContent = 'TELEMETRY';
        elHealthCommand.className = 'metric-health ok';
      }
    } else {
      if (elCommand) elCommand.textContent = '--';
      if (elHealthCommand) {
        elHealthCommand.textContent = 'STANDBY';
        elHealthCommand.className = 'metric-health standby';
      }
    }

    // 5. Drive Mode
    if (rover.mode && isOnline) {
      const modeLabel = rover.mode === 'M' ? 'MANUAL' : (rover.mode === 'A' ? 'AUTONOMOUS' : rover.mode);
      if (elMode) elMode.textContent = modeLabel;
      if (elHealthMode) {
        elHealthMode.textContent = 'ACTIVE';
        elHealthMode.className = 'metric-health ok';
      }
    } else {
      if (elMode) elMode.textContent = '--';
      if (elHealthMode) {
        elHealthMode.textContent = 'STANDBY';
        elHealthMode.className = 'metric-health standby';
      }
    }

    // 6. Battery Voltage (if available)
    if (rover.battery_voltage_v != null && isOnline) {
      if (elVoltage) elVoltage.textContent = Number(rover.battery_voltage_v).toFixed(2);
      if (elHealthVoltage) {
        elHealthVoltage.textContent = 'OK';
        elHealthVoltage.className = 'metric-health ok';
      }
    } else {
      if (elVoltage) elVoltage.textContent = '--';
      if (elHealthVoltage) {
        elHealthVoltage.textContent = 'STANDBY';
        elHealthVoltage.className = 'metric-health standby';
      }
    }

    // Battery Capacity is strictly unmapped in current contract
    if (elBattery) elBattery.textContent = '--';
    if (elHealthBattery) {
      elHealthBattery.textContent = 'UNMAPPED';
      elHealthBattery.className = 'metric-health standby';
    }

    // 7. Event Banner
    if (elEventBanner) {
      const eventMsg = rover.event || (isOnline ? 'Nominal rover telemetry stream active.' : 'Waiting for rover telemetry feed.');
      elEventBanner.innerHTML = `<strong>EVENT STATUS:</strong> ${eventMsg}`;
    }
  }

  // Export View Manager
  window.MMCRoverView = {
    show() {
      const droneView = document.getElementById('drone-view');
      if (landingView && roverView) {
        landingView.classList.add('hidden');
        if (landerView) landerView.classList.add('hidden');
        if (droneView) droneView.classList.add('hidden');
        roverView.classList.remove('hidden');
        window.location.hash = '#rover';
        window.scrollTo(0, 0);
        setTimeout(initTerrainMap, 50);
      }
    },
    hide: navigateToLanding,
    update,
  };
})();
