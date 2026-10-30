/**
 * Mars Mission Control — Landing Page Interaction Controller
 * frontend-college/js/landing.js
 */

(function () {
  'use strict';

  // --- Clock Display (Live Indian Standard Time) ---
  const elClock = document.getElementById('clock-display');

  function updateClock() {
    if (elClock && window.MMCFormatters) {
      elClock.textContent = window.MMCFormatters.formatTimeIST(new Date()) + ' IST';
    }
  }

  setInterval(updateClock, 1000);
  updateClock();

  // --- Subsystem Selector Modal Handling ---
  const modalOverlay = document.getElementById('subsystem-modal');
  const modalTitle = document.getElementById('modal-title');
  const modalBody = document.getElementById('modal-body');
  const modalNotice = document.getElementById('modal-notice');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalDismissBtn = document.getElementById('modal-dismiss-btn');

  const subsystemDetails = {
    lander: {
      title: 'LANDER STATION • GATE & SENSORS',
      body: `The Lander Station monitors the primary physical lander platform. It features environmental telemetry from BMP280 (temperature & pressure) and DHT11 (temperature & humidity) sensors, dual limit switches (Open/Closed), and physical servo gate actuation interlocks.`,
      notice: `Stage 1 Landing Screen is complete. The full Lander Dashboard will be rendered upon your review and approval.`
    },
    rover: {
      title: 'SURFACE ROVER • MOBILITY & RADAR',
      body: `The Surface Rover terminal displays tactical Jezero Crater terrain mapping, 5 Hz ultrasonic obstacle rangefinding, pitch/roll attitude gyroscopes, and passive drive commands. Position coordinates and battery percentage remain strictly in passive/unmapped specification.`,
      notice: `Stage 1 Landing Screen is complete. The full Rover Dashboard will be rendered upon your review and approval.`
    },
    drone: {
      title: 'AERIAL DRONE • PHASE 2 SCOUT (COMING SOON)',
      body: `The Aerial Drone scout is an upcoming high-altitude reconnaissance expansion. In strict compliance with project architecture (README-for-AI.md), no flight telemetry is invented or simulated.`,
      notice: `SUBSYSTEM STATUS: NOT IMPLEMENTED / COMING SOON. This view is intentionally locked to Phase 2.`
    }
  };

  function openSubsystemModal(subsystemKey) {
    const data = subsystemDetails[subsystemKey];
    if (!data || !modalOverlay) return;

    modalTitle.textContent = data.title;
    modalBody.textContent = data.body;
    modalNotice.textContent = data.notice;
    modalOverlay.classList.remove('hidden');
  }

  function closeModal() {
    if (modalOverlay) {
      modalOverlay.classList.add('hidden');
    }
  }

  // Attach button triggers
  document.querySelectorAll('[data-subsystem]').forEach(button => {
    button.addEventListener('click', (e) => {
      e.preventDefault();
      const targetSubsystem = button.getAttribute('data-subsystem');
      if (targetSubsystem === 'lander' && window.MMCLanderView) {
        window.MMCLanderView.show();
      } else if (targetSubsystem === 'rover' && window.MMCRoverView) {
        window.MMCRoverView.show();
      } else if (targetSubsystem === 'drone' && window.MMCDroneView) {
        window.MMCDroneView.show();
      } else {
        openSubsystemModal(targetSubsystem);
      }
    });
  });

  // Handle direct hash navigation
  function handleHashNavigation() {
    if (window.location.hash === '#drone' && window.MMCDroneView) {
      window.MMCDroneView.show();
    } else if (window.location.hash === '#rover' && window.MMCRoverView) {
      window.MMCRoverView.show();
    } else if (window.location.hash === '#lander' && window.MMCLanderView) {
      window.MMCLanderView.show();
    } else if (window.location.hash === '#landing') {
      if (window.MMCLanderView) window.MMCLanderView.hide();
      if (window.MMCRoverView) window.MMCRoverView.hide();
      if (window.MMCDroneView) window.MMCDroneView.hide();
    }
  }

  window.addEventListener('hashchange', handleHashNavigation);
  window.addEventListener('DOMContentLoaded', handleHashNavigation);

  // Modal event listeners
  if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
  if (modalDismissBtn) modalDismissBtn.addEventListener('click', closeModal);
  if (modalOverlay) {
    modalOverlay.addEventListener('click', (e) => {
      if (e.target === modalOverlay) closeModal();
    });
  }

  // Escape key to close modal
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalOverlay && !modalOverlay.classList.contains('hidden')) {
      closeModal();
    }
  });

  // --- Live Subsystem Status on Landing Cards ---
  const elLandingDotLander = document.getElementById('landing-dot-lander');
  const elLandingTextLander = document.getElementById('landing-text-lander');
  const elLandingDotRover = document.getElementById('landing-dot-rover');
  const elLandingTextRover = document.getElementById('landing-text-rover');
  const elLandingDotDrone = document.getElementById('landing-dot-drone');
  const elLandingTextDrone = document.getElementById('landing-text-drone');

  function updateSubsystemStatus(landerState, roverState, droneState) {
    if (landerState && elLandingDotLander && elLandingTextLander) {
      const devState = (landerState.device_state || 'NOT_CONNECTED').toUpperCase();
      const isOnline = devState === 'ONLINE';
      elLandingDotLander.className = 'pill-dot ' + (isOnline ? 'online' : (devState === 'STALE' ? 'stale' : 'offline'));
      elLandingTextLander.textContent = devState;
    }
    if (roverState && elLandingDotRover && elLandingTextRover) {
      const isOnline = roverState.connection_state === 'ONLINE' || roverState.connected === true;
      elLandingDotRover.className = 'pill-dot ' + (isOnline ? 'online' : 'offline');
      elLandingTextRover.textContent = isOnline ? (roverState.source === 'simulator' ? 'ONLINE (SIM)' : 'ONLINE') : 'NOT CONNECTED';
    }
    if (droneState && elLandingDotDrone && elLandingTextDrone) {
      const isOnline = droneState.connection_state === 'ONLINE' || droneState.connected === true;
      elLandingDotDrone.className = 'pill-dot ' + (isOnline ? 'online' : 'offline');
      elLandingTextDrone.textContent = isOnline ? (droneState.source === 'simulator' ? 'ONLINE (SIM)' : 'ONLINE') : 'NOT CONNECTED';
    }
  }

  // Public Landing View Export
  window.MMCLandingView = {
    update: updateSubsystemStatus,
  };

})();
