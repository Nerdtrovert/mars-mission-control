/**
 * Mars Mission Control — Precision Formatting Utilities
 * frontend/js/formatters.js
 * 
 * Complies strictly with frontend-api.md Section 7 & 10.
 */

// 1. Timezone Formatter: Indian Standard Time (IST, UTC+05:30) in 24-hour cycle
const istTimeFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

const istDateTimeFormatter = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

/**
 * Formats a Date object or ISO string into IST 24-hour time string (HH:mm:ss).
 * @param {Date|string|number} val 
 * @returns {string} e.g. "14:15:30"
 */
function formatTimeIST(val) {
  if (!val) return '--:--:--';
  try {
    const d = val instanceof Date ? val : new Date(val);
    return isNaN(d.getTime()) ? '--:--:--' : istTimeFormatter.format(d);
  } catch (e) {
    return '--:--:--';
  }
}

/**
 * Formats a Date object or ISO string into a full IST date and time string.
 * @param {Date|string|number} val 
 * @returns {string} e.g. "28 Oct 2026, 14:15:30"
 */
function formatFullDateTimeIST(val) {
  if (!val) return '--';
  try {
    const d = val instanceof Date ? val : new Date(val);
    return isNaN(d.getTime()) ? '--' : istDateTimeFormatter.format(d);
  } catch (e) {
    return '--';
  }
}

/**
 * Duration Formatter for ESP32 Boot Uptime (timestamp_ms).
 * Strictly formats milliseconds into elapsed duration (HH:MM:SS or Xd HH:MM:SS).
 * MUST NEVER be treated as wall-clock time.
 * @param {number} uptimeMs 
 * @returns {string} e.g. "02:45:10" or "1d 04:12:00"
 */
function formatUptime(uptimeMs) {
  if (!Number.isFinite(uptimeMs) || uptimeMs < 0) return '--:--:--';
  const totalSec = Math.floor(uptimeMs / 1000);
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

// Export for global browser use
window.MMCFormatters = {
  formatTimeIST,
  formatFullDateTimeIST,
  formatUptime,
};
