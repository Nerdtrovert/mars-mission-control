/**
 * Mars Mission Control — Aerial Drone Dashboard Controller
 * frontend/js/drone-view.js
 *
 * Full integration with Drone Telemetry stream (UDP port 5007 & simulator).
 */

(function () {
  'use strict';

  // --- Clock Updater for Drone Dashboard ---
  const elDroneClock = document.getElementById('drone-clock-display');

  function updateDroneClock() {
    if (elDroneClock && window.MMCFormatters) {
      elDroneClock.textContent = window.MMCFormatters.formatTimeIST(new Date()) + ' IST';
    }
  }

  setInterval(updateDroneClock, 1000);
  updateDroneClock();

  // --- View Panels Reference ---
  const landingView = document.getElementById('landing-view');
  const landerView = document.getElementById('lander-view');
  const roverView = document.getElementById('rover-view');
  const droneView = document.getElementById('drone-view');

  function navigateToLanding() {
    if (landingView && droneView) {
      droneView.classList.add('hidden');
      if (landerView) landerView.classList.add('hidden');
      if (roverView) roverView.classList.add('hidden');
      landingView.classList.remove('hidden');
      window.location.hash = '#landing';
      window.scrollTo(0, 0);
    }
  }

  function navigateToLander() {
    if (landerView && droneView) {
      droneView.classList.add('hidden');
      if (landingView) landingView.classList.add('hidden');
      if (roverView) roverView.classList.add('hidden');
      landerView.classList.remove('hidden');
      window.location.hash = '#lander';
      window.scrollTo(0, 0);
    }
  }

  function navigateToRover() {
    if (roverView && droneView) {
      droneView.classList.add('hidden');
      if (landingView) landingView.classList.add('hidden');
      if (landerView) landerView.classList.add('hidden');
      roverView.classList.remove('hidden');
      window.location.hash = '#rover';
      window.scrollTo(0, 0);
    }
  }

  // Bind Navigation Buttons
  const btnDroneBackOverview = document.getElementById('btn-drone-back-overview');
  const btnTabToLander = document.getElementById('btn-tab-drone-to-lander');
  const btnTabToRover = document.getElementById('btn-tab-drone-to-rover');

  if (btnDroneBackOverview) {
    btnDroneBackOverview.addEventListener('click', (e) => {
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

  if (btnTabToRover) {
    btnTabToRover.addEventListener('click', (e) => {
      e.preventDefault();
      navigateToRover();
    });
  }

  // --- DOM Elements ---
  const elConnDot = document.getElementById('drone-conn-dot');
  const elConnText = document.getElementById('drone-conn-text');
  const elSourceText = document.getElementById('drone-source-text');

  const elAttitudePill = document.getElementById('drone-attitude-pill');
  const elRoll = document.getElementById('val-drone-roll');
  const elPitch = document.getElementById('val-drone-pitch');
  const elYaw = document.getElementById('val-drone-yaw');

  const elFlightStatus = document.getElementById('val-drone-flight-status');
  const elHealthFlightStatus = document.getElementById('health-drone-flight-status');

  const elAltitude = document.getElementById('val-drone-altitude');
  const elHealthAltitude = document.getElementById('health-drone-altitude');

  const elGPS = document.getElementById('val-drone-gps');
  const elHealthGPS = document.getElementById('health-drone-gps');

  const elBatteryPct = document.getElementById('val-drone-battery-pct');
  const elHealthBatteryPct = document.getElementById('health-drone-battery-pct');

  const elTemp = document.getElementById('val-drone-temp');
  const elHealthTemp = document.getElementById('health-drone-temp');

  const elPressure = document.getElementById('val-drone-pressure');
  const elHealthPressure = document.getElementById('health-drone-pressure');

  const elHumidity = document.getElementById('val-drone-humidity');
  const elHealthHumidity = document.getElementById('health-drone-humidity');

  const elVoltage = document.getElementById('val-drone-voltage');
  const elHealthVoltage = document.getElementById('health-drone-voltage');

  const elEventBanner = document.getElementById('drone-event-banner');
  const elAlertBanner = document.getElementById('drone-alert-banner');
  const elBannerIcon = document.getElementById('drone-banner-icon');
  const elBannerText = document.getElementById('drone-banner-text');

  // --- Airspace Reconnaissance Radar Canvas ---
  const canvas = document.getElementById('airspace-canvas');
  let animationFrameId = null;
  let radarAngle = 0;

  function initAirspaceRadar() {
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

    function drawRadar() {
      const w = canvas.getBoundingClientRect().width;
      const h = canvas.getBoundingClientRect().height;
      const cx = w * 0.5;
      const cy = h * 0.5;
      const maxRadius = Math.min(cx, cy) - 20;

      ctx.clearRect(0, 0, w, h);

      // 1. Concentric Altitude Range Rings
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.18)';
      ctx.lineWidth = 1;
      const rings = [0.25, 0.5, 0.75, 1.0];
      rings.forEach((ratio, idx) => {
        ctx.beginPath();
        ctx.arc(cx, cy, maxRadius * ratio, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = 'rgba(251, 191, 36, 0.45)';
        ctx.font = '9px monospace';
        ctx.fillText(`${(idx + 1) * 50}m`, cx + 6, cy - maxRadius * ratio + 12);
      });

      // 2. Crosshairs
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.12)';
      ctx.beginPath();
      ctx.moveTo(cx, cy - maxRadius);
      ctx.lineTo(cx, cy + maxRadius);
      ctx.moveTo(cx - maxRadius, cy);
      ctx.lineTo(cx + maxRadius, cy);
      ctx.stroke();

      // 3. Drone Waypoint illustration
      const waypoints = [
        { x: cx + 45, y: cy - 60, label: 'WP-1' },
        { x: cx - 60, y: cy - 30, label: 'WP-2' },
        { x: cx + 70, y: cy + 40, label: 'WP-3' }
      ];

      waypoints.forEach((wp) => {
        ctx.beginPath();
        ctx.arc(wp.x, wp.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(251, 191, 36, 0.9)';
        ctx.fill();

        ctx.fillStyle = '#f1f5f9';
        ctx.font = '8px monospace';
        ctx.textAlign = 'left';
        ctx.fillText(wp.label, wp.x + 8, wp.y + 3);
      });

      // 4. Stationary Lander Position
      ctx.beginPath();
      ctx.arc(cx - 70, cy + 50, 7, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(224, 86, 56, 0.85)';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // 5. Sweeping Airspace Radar Beam
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(radarAngle);

      const sweepGradient = ctx.createRadialGradient(0, 0, 0, 0, 0, maxRadius);
      sweepGradient.addColorStop(0, 'rgba(251, 191, 36, 0.28)');
      sweepGradient.addColorStop(1, 'rgba(251, 191, 36, 0.0)');

      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, maxRadius, 0, Math.PI / 4);
      ctx.closePath();
      ctx.fillStyle = sweepGradient;
      ctx.fill();

      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(maxRadius, 0);
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.85)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.restore();

      radarAngle += 0.02;
      animationFrameId = requestAnimationFrame(drawRadar);
    }

    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    animationFrameId = requestAnimationFrame(drawRadar);
  }

  // --- Render Live Drone Telemetry ---
  function update(drone) {
    if (!drone) return;

    const isOnline = drone.connection_state === 'ONLINE';
    const isSim = drone.source === 'simulator';
    const telem = drone.telemetry;

    // 1. Connection & Source Badges
    if (elAlertBanner) {
      if (isSim) {
        // In hybrid / simulator mode, suppress connecting alert banner
        elAlertBanner.style.display = 'none';
      } else if (isOnline) {
        elAlertBanner.style.display = 'flex';
        elAlertBanner.className = 'preview-alert-banner banner-nominal';
        if (elBannerIcon) elBannerIcon.innerHTML = '&#x2714;';
        if (elBannerText) elBannerText.innerHTML = '<strong>NOMINAL:</strong> Live telemetry streaming over UDP port 5007.';
      } else {
        elAlertBanner.style.display = 'flex';
        elAlertBanner.className = 'preview-alert-banner banner-disrupted';
        if (elBannerIcon) elBannerIcon.innerHTML = '&#x26A0;';
        if (elBannerText) elBannerText.innerHTML = '<strong>CONNECTING:</strong> Linking to drone telemetry stream (UDP 5007)...';
      }
    }

    if (elConnText && elConnDot) {
      elConnText.textContent = `DRONE: ${isOnline ? 'ONLINE' : 'OFFLINE'}`;
      elConnDot.className = 'pill-dot ' + (isOnline ? 'online' : 'offline');
    }

    if (elSourceText) {
      elSourceText.textContent = isSim ? 'SOURCE: SIMULATOR' : 'SOURCE: HARDWARE';
    }

    // 2. Gyro & Flight Attitude
    if (telem && telem.orientation && isOnline) {
      const o = telem.orientation;
      if (elRoll) elRoll.textContent = o.roll != null ? `${Number(o.roll).toFixed(1)}°` : '--°';
      if (elPitch) elPitch.textContent = o.pitch != null ? `${Number(o.pitch).toFixed(1)}°` : '--°';
      if (elYaw) elYaw.textContent = o.yaw != null ? `${Number(o.yaw).toFixed(1)}°` : '--°';
      if (elAttitudePill) {
        elAttitudePill.textContent = drone.flight_status || 'STABILIZED';
        elAttitudePill.style.color = 'var(--amber-400)';
      }
    } else {
      if (elRoll) elRoll.textContent = '--°';
      if (elPitch) elPitch.textContent = '--°';
      if (elYaw) elYaw.textContent = '--°';
      if (elAttitudePill) elAttitudePill.textContent = 'STANDBY';
    }

    // 3. Flight Status
    const statusVal = drone.flight_status || (telem ? telem.flight_status : null);
    if (statusVal && isOnline) {
      if (elFlightStatus) elFlightStatus.textContent = statusVal;
      if (elHealthFlightStatus) {
        elHealthFlightStatus.textContent = 'NOMINAL';
        elHealthFlightStatus.className = 'metric-health ok';
      }
    } else {
      if (elFlightStatus) elFlightStatus.textContent = '--';
      if (elHealthFlightStatus) {
        elHealthFlightStatus.textContent = 'STANDBY';
        elHealthFlightStatus.className = 'metric-health standby';
      }
    }

    // 4. Altitude
    const altVal = drone.altitude_m != null ? drone.altitude_m : (telem && telem.gps ? telem.gps.altitude_m : null);
    if (altVal != null && isOnline) {
      if (elAltitude) elAltitude.textContent = Number(altVal).toFixed(1);
      if (elHealthAltitude) {
        elHealthAltitude.textContent = 'OK';
        elHealthAltitude.className = 'metric-health ok';
      }
    } else {
      if (elAltitude) elAltitude.textContent = '--';
      if (elHealthAltitude) {
        elHealthAltitude.textContent = 'STANDBY';
        elHealthAltitude.className = 'metric-health standby';
      }
    }

    // 5. GPS Coordinates
    const lat = drone.latitude != null ? drone.latitude : (telem && telem.gps ? telem.gps.latitude : null);
    const lon = drone.longitude != null ? drone.longitude : (telem && telem.gps ? telem.gps.longitude : null);
    if (lat != null && lon != null && isOnline) {
      if (elGPS) elGPS.textContent = `${Number(lat).toFixed(6)} / ${Number(lon).toFixed(6)}`;
      if (elHealthGPS) {
        elHealthGPS.textContent = 'FIX';
        elHealthGPS.className = 'metric-health ok';
      }
    } else {
      if (elGPS) elGPS.textContent = '-- / --';
      if (elHealthGPS) {
        elHealthGPS.textContent = 'NO FIX';
        elHealthGPS.className = 'metric-health standby';
      }
    }

    // 6. Battery Capacity (%)
    const battPct = drone.battery_percentage != null ? drone.battery_percentage : (telem && telem.battery ? telem.battery.percentage : null);
    if (battPct != null && isOnline) {
      if (elBatteryPct) elBatteryPct.textContent = Number(battPct).toFixed(1);
      if (elHealthBatteryPct) {
        elHealthBatteryPct.textContent = 'OK';
        elHealthBatteryPct.className = 'metric-health ok';
      }
    } else {
      if (elBatteryPct) elBatteryPct.textContent = '--';
      if (elHealthBatteryPct) {
        elHealthBatteryPct.textContent = 'STANDBY';
        elHealthBatteryPct.className = 'metric-health standby';
      }
    }

    // 7. Environment (Temp, Pressure, Humidity)
    if (telem && telem.environment && isOnline) {
      const env = telem.environment;
      if (elTemp) elTemp.textContent = env.temperature_c != null ? Number(env.temperature_c).toFixed(1) : '--';
      if (elHealthTemp) elHealthTemp.className = env.temperature_c != null ? 'metric-health ok' : 'metric-health standby';

      if (elPressure) elPressure.textContent = env.pressure_hpa != null ? Number(env.pressure_hpa).toFixed(1) : '--';
      if (elHealthPressure) elHealthPressure.className = env.pressure_hpa != null ? 'metric-health ok' : 'metric-health standby';

      if (elHumidity) elHumidity.textContent = env.humidity_pct != null ? Number(env.humidity_pct).toFixed(1) : '--';
      if (elHealthHumidity) elHealthHumidity.className = env.humidity_pct != null ? 'metric-health ok' : 'metric-health standby';
    } else {
      if (elTemp) elTemp.textContent = '--';
      if (elPressure) elPressure.textContent = '--';
      if (elHumidity) elHumidity.textContent = '--';
    }

    // 8. Battery Voltage
    const volt = telem && telem.battery ? telem.battery.voltage_v : null;
    if (volt != null && isOnline) {
      if (elVoltage) elVoltage.textContent = Number(volt).toFixed(2);
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

    // 9. Event Banner
    if (elEventBanner) {
      const msg = isOnline
        ? (drone.last_seen ? `Streaming drone telemetry (Last seen ${window.MMCFormatters ? window.MMCFormatters.formatTimeIST(drone.last_seen) : ''} IST).` : 'Streaming drone telemetry.')
        : 'Waiting for drone telemetry feed (UDP port 5007).';
      elEventBanner.innerHTML = `<strong>EVENT STATUS:</strong> ${msg}`;
    }
  }

  // Export View Manager
  window.MMCDroneView = {
    show() {
      if (landingView && droneView) {
        landingView.classList.add('hidden');
        if (landerView) landerView.classList.add('hidden');
        if (roverView) roverView.classList.add('hidden');
        droneView.classList.remove('hidden');
        window.location.hash = '#drone';
        window.scrollTo(0, 0);
        setTimeout(initAirspaceRadar, 60);
      }
    },
    hide: navigateToLanding,
    update,
  };
})();
