/**
 * Mars Mission Control — Surface Rover Dashboard Controller (Stage 2B)
 * frontend-college/js/rover-view.js
 * 
 * Strict compliance with AGENTS.md, api-contract.md, and user adjustments:
 * - Terrain map rendered strictly as static tactical illustration (not live positioning).
 * - Radar sweep rendered in standby clearance mode without live telemetry.
 * - Decorative graphics clearly distinguished from actual sensor data.
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

      // 2. Topographic Elevation Contours (Jezero Crater Sector Illustration)
      ctx.strokeStyle = 'rgba(224, 86, 56, 0.16)';
      ctx.lineWidth = 1.2;
      const rings = [60, 110, 160, 210];
      rings.forEach((r, idx) => {
        ctx.beginPath();
        ctx.ellipse(cx, cy, r * 1.15, r * 0.75, Math.PI / 12, 0, Math.PI * 2);
        ctx.stroke();

        // Contour elevation labels
        ctx.fillStyle = 'rgba(224, 86, 56, 0.35)';
        ctx.font = '9px monospace';
        ctx.fillText(`-${2400 + idx * 50}m`, cx + r * 0.9, cy - r * 0.45);
      });

      // 3. Tactical Range Rings (Metric Scale)
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

      // 4. Standby Radar Sweep Arc (Gentle decorative rotation in standby mode)
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

      // 6. Static Sector Marker (Rover Exploration Sector)
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

      // 7. Explicit Static Disclaimer on Canvas
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
    hide: navigateToLanding
  };

})();
