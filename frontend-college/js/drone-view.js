/**
 * Mars Mission Control — Aerial Drone Dashboard Controller (Stage 2C)
 * frontend-college/js/drone-view.js
 * 
 * Strict compliance with AGENTS.md and drone contract:
 * - Ingests authoritative schema: flight_status, altitude_m, gps, battery, orientation, environment.
 * - Airspace radar rendered in tactical reconnaissance preview mode.
 * - Flight telemetry only; no propulsion/flight commands dispatched from Mission Control.
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
      const cy = h * 0.52;

      ctx.clearRect(0, 0, w, h);

      // 1. Tactical Gridlines
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.08)';
      ctx.lineWidth = 1;

      for (let x = 0; x < w; x += 35) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += 35) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // 2. Concentric Airspace Altitude Rings
      const maxRadius = Math.min(w, h) * 0.44;
      const ringSteps = [0.25, 0.5, 0.75, 1.0];

      ringSteps.forEach((step, idx) => {
        const r = maxRadius * step;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = (idx === ringSteps.length - 1) ? 'rgba(251, 191, 36, 0.35)' : 'rgba(251, 191, 36, 0.15)';
        ctx.lineWidth = 1.2;
        if (idx % 2 === 1) {
          ctx.setLineDash([4, 4]);
        } else {
          ctx.setLineDash([]);
        }
        ctx.stroke();
        ctx.setLineDash([]);

        // Altitude Ring Label
        ctx.fillStyle = 'rgba(251, 191, 36, 0.55)';
        ctx.font = '9px monospace';
        ctx.fillText(`${(step * 100).toFixed(0)}m ALT`, cx + 6, cy - r + 12);
      });

      // 3. Compass Crosshairs
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.25)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx, cy - maxRadius - 10);
      ctx.lineTo(cx, cy + maxRadius + 10);
      ctx.moveTo(cx - maxRadius - 10, cy);
      ctx.lineTo(cx + maxRadius + 10, cy);
      ctx.stroke();

      // Heading Cardinal Labels
      ctx.fillStyle = '#fbbf24';
      ctx.font = '10px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('N (360°)', cx, cy - maxRadius - 14);
      ctx.fillText('S (180°)', cx, cy + maxRadius + 22);
      ctx.textAlign = 'left';
      ctx.fillText('E (090°)', cx + maxRadius + 14, cy + 4);
      ctx.textAlign = 'right';
      ctx.fillText('W (270°)', cx - maxRadius - 14, cy + 4);

      // 4. Reconnaissance Flight Path Corridor (Illustration)
      ctx.strokeStyle = 'rgba(251, 191, 36, 0.45)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(cx - 70, cy + 50);
      ctx.lineTo(cx - 20, cy - 30);
      ctx.lineTo(cx + 40, cy - 60);
      ctx.lineTo(cx + 75, cy + 10);
      ctx.stroke();
      ctx.setLineDash([]);

      // Waypoint dots
      const waypoints = [
        { x: cx - 70, y: cy + 50, label: 'WP-01 (LZ)' },
        { x: cx - 20, y: cy - 30, label: 'WP-02' },
        { x: cx + 40, y: cy - 60, label: 'WP-03 (PEAK)' },
        { x: cx + 75, y: cy + 10, label: 'WP-04' }
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

      // 5. Stationary Lander Position (Red Core)
      ctx.beginPath();
      ctx.arc(cx - 70, cy + 50, 7, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(224, 86, 56, 0.85)';
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // 6. Sweeping Airspace Radar Beam
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

  // --- Public View Coordinator Helper ---
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
    hide: navigateToLanding
  };

})();
