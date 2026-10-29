/**
 * Mars Mission Control — Lander Dashboard Controller (Stage 2A)
 * frontend-college/js/lander-view.js
 * 
 * Strict compliance with AGENTS.md and Stage 2A constraints:
 * - Gate state strictly UNKNOWN.
 * - Limit switches initialized as UNKNOWN (Correction 1).
 * - All controls explicitly PREVIEW ONLY — NO COMMAND SENT.
 * - Zero fabricated telemetry, zero simulated movement without backend.
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

  // --- View Navigation: Back to Mission Overview ---
  const btnBackOverview = document.getElementById('btn-back-overview');
  const landingView = document.getElementById('landing-view');
  const landerView = document.getElementById('lander-view');

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

  // Quick switch tab from Lander to Rover or Drone
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

  // --- Preview Controls Interaction (PREVIEW ONLY — NO COMMAND SENT) ---
  const feedbackToast = document.getElementById('lander-control-feedback');
  let feedbackTimer = null;

  function triggerPreviewFeedback(actionName) {
    if (!feedbackToast) return;

    if (feedbackTimer) {
      clearTimeout(feedbackTimer);
      feedbackTimer = null;
    }

    feedbackToast.textContent = `PREVIEW ONLY — NO COMMAND SENT for [${actionName}]. Lander status remains UNRECOGNIZED in standalone preview. Command dispatch requires backend gateway integration.`;
    feedbackToast.classList.add('show');

    feedbackTimer = setTimeout(() => {
      feedbackToast.classList.remove('show');
    }, 4500);
  }

  // Bind preview buttons (Diagnostic controls at bottom of page)
  const previewButtons = [
    { id: 'btn-preview-status', action: 'QUERY_STATUS' },
    { id: 'btn-preview-reset', action: 'RESET_SESSION' }
  ];

  previewButtons.forEach(({ id, action }) => {
    const btn = document.getElementById(id);
    if (btn) {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        triggerPreviewFeedback(action);
      });
    }
  });

  // Export navigation helper to window for coordinator access
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
    hide: navigateToLanding
  };

})();
