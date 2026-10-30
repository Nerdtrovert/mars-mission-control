/**
 * Mars Mission Control — Landing Page Interaction Controller
 * frontend/js/landing.js
 */

(function () {
  'use strict';

  // --- Clock Display (Live Indian Standard Time) ---
  const elFooterClock = document.getElementById('footer-clock');
  const elLanderClock = document.getElementById('lander-clock-display');
  const elRoverClock = document.getElementById('rover-clock-display');
  const elDroneClock = document.getElementById('drone-clock-display');

  function updateClock() {
    if (window.MMCFormatters) {
      const timeStr = window.MMCFormatters.formatTimeIST(new Date()) + ' IST';
      if (elFooterClock) elFooterClock.textContent = timeStr;
      if (elLanderClock) elLanderClock.textContent = timeStr;
      if (elRoverClock) elRoverClock.textContent = timeStr;
      if (elDroneClock) elDroneClock.textContent = timeStr;
    }
  }

  setInterval(updateClock, 1000);
  updateClock();

  // --- System Initialization Indicator ---
  const elSystemInitDot = document.getElementById('system-init-dot');
  const elSystemInitText = document.getElementById('system-init-text');
  const elOperatingMode = document.getElementById('operating-mode');
  const elFooterMode = document.getElementById('footer-mode');
  const elFooterModeLabel = document.getElementById('footer-mode-label');

  // --- Footer Status Indicators ---
  const elNetworkDot = document.getElementById('network-dot');
  const elNetworkText = document.getElementById('network-text');
  const elGatewayDot = document.getElementById('gateway-dot');
  const elGatewayText = document.getElementById('gateway-text');

  // Track initialization state
  let systemInitialized = false;
  let currentMode = 'SIMULATION';

  function setSystemInitializing() {
    if (elSystemInitDot && elSystemInitText) {
      elSystemInitDot.className = 'status-dot initializing';
      elSystemInitText.textContent = 'SYSTEM INITIALIZING';
    }
    systemInitialized = false;
  }

  function setSystemOnline(mode) {
    if (elSystemInitDot && elSystemInitText) {
      elSystemInitDot.className = 'status-dot online';
      elSystemInitText.textContent = 'SYSTEM ONLINE';
    }
    systemInitialized = true;
    if (mode) {
      setOperatingMode(mode);
    }
  }

  function setSystemOffline() {
    if (elSystemInitDot && elSystemInitText) {
      elSystemInitDot.className = 'status-dot offline';
      elSystemInitText.textContent = 'SYSTEM OFFLINE';
    }
    systemInitialized = false;
  }

  function setOperatingMode(mode) {
    currentMode = mode;
    const modeText = mode === 'NETWORK' ? 'NETWORK' : 'SIMULATION';
    if (elOperatingMode) elOperatingMode.textContent = modeText;
    if (elFooterMode) elFooterMode.textContent = modeText;
    if (elFooterModeLabel) elFooterModeLabel.textContent = 'MODE';
  }

  function updateNetworkStatus(connected) {
    if (elNetworkDot && elNetworkText) {
      if (connected) {
        elNetworkDot.className = 'status-dot online';
        elNetworkText.textContent = 'CONNECTED';
      } else {
        elNetworkDot.className = 'status-dot offline';
        elNetworkText.textContent = 'DISCONNECTED';
      }
    }
  }

  function updateGatewayStatus(connected) {
    if (elGatewayDot && elGatewayText) {
      if (connected) {
        elGatewayDot.className = 'status-dot online';
        elGatewayText.textContent = 'CONNECTED';
      } else {
        elGatewayDot.className = 'status-dot offline';
        elGatewayText.textContent = 'DISCONNECTED';
      }
    }
  }

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
      body: 'The Lander Station monitors the primary physical lander platform. It features environmental telemetry from BMP280 (temperature & pressure) and DHT11 (temperature & humidity) sensors, dual limit switches (Open/Closed), and physical servo gate actuation interlocks.',
      notice: 'Stage 1 Landing Screen is complete. The full Lander Dashboard will be rendered upon your review and approval.'
    },
    rover: {
      title: 'SURFACE ROVER • MOBILITY & RADAR',
      body: 'The Surface Rover terminal displays tactical Jezero Crater terrain mapping, 5 Hz ultrasonic obstacle rangefinding, pitch/roll attitude gyroscopes, and passive drive commands. Position coordinates and battery percentage remain strictly in passive/unmapped specification.',
      notice: 'Stage 1 Landing Screen is complete. The full Rover Dashboard will be rendered upon your review and approval.'
    },
    drone: {
      title: 'AERIAL DRONE • PHASE 2 SCOUT (COMING SOON)',
      body: 'The Aerial Drone scout is an upcoming high-altitude reconnaissance expansion. In strict compliance with project architecture (README-for-AI.md), no flight telemetry is invented or simulated.',
      notice: 'SUBSYSTEM STATUS: NOT IMPLEMENTED / COMING SOON. This view is intentionally locked to Phase 2.'
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

  // --- Public API for Mission Client ---
  function handleBackendStatus(status) {
    if (!status) return;

    // Update system initialization based on backend connectivity
    if (status.backend_connected || status.ws_connected) {
      setSystemOnline(status.mode || currentMode);
      updateNetworkStatus(true);
      updateGatewayStatus(status.gateway_connected || false);
    } else {
      setSystemInitializing();
      updateNetworkStatus(false);
      updateGatewayStatus(false);
    }

    // Update operating mode if provided
    if (status.mode) {
      setOperatingMode(status.mode);
    }
  }

  // Public Landing View Export
  window.MMCLandingView = {
    update: updateSubsystemStatus,
    setSystemInitializing: setSystemInitializing,
    setSystemOnline: setSystemOnline,
    setSystemOffline: setSystemOffline,
    setOperatingMode: setOperatingMode,
    updateNetworkStatus: updateNetworkStatus,
    updateGatewayStatus: updateGatewayStatus,
    handleBackendStatus: handleBackendStatus
  };

  // Initialize as initializing
  setSystemInitializing();

})();