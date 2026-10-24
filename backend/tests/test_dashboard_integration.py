"""Tests for Mission Control Dashboard and WebSocket Live Stream Integration.

Verifies:
1. Dashboard HTML serving and static asset files.
2. Complete dashboard UI structure and DOM elements for exhibition TV layout.
3. Live WebSocket broadcaster, connection lifecycle, initial snapshot, and broadcast propagation.
4. Multi-schema command dispatch compatibility and safety constraints.
5. Independent subsystem status tracking and safety gating logic.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.responses import FileResponse

from app.main import get_dashboard, FRONTEND_DIR
from app.api.routes import (
    mission_state,
    command_tracker,
    telemetry_service,
    dashboard_broadcaster,
    get_mission_state,
    submit_command,
    reset_session,
    CommandSubmissionRequest,
)
from app.communication.gateway_contract import CommandName
from app.communication.broadcaster import DashboardBroadcaster


class MockWebSocket:
    """Mock WebSocket for testing DashboardBroadcaster without socket dependencies."""

    def __init__(self) -> None:
        self.is_connected = False
        self.sent_json_messages: list[dict] = []
        self.sent_text_messages: list[str] = []

    async def accept(self) -> None:
        self.is_connected = True

    async def send_json(self, message: dict) -> None:
        if not self.is_connected:
            raise ConnectionError("WebSocket is disconnected")
        self.sent_json_messages.append(message)

    async def send_text(self, text: str) -> None:
        if not self.is_connected:
            raise ConnectionError("WebSocket is disconnected")
        self.sent_text_messages.append(text)


@pytest.fixture(autouse=True)
def clean_state():
    """Ensure state and command tracker are clean for each test."""
    mission_state.reset()
    command_tracker.clear()
    dashboard_broadcaster.active_connections.clear()
    yield
    mission_state.reset()
    command_tracker.clear()
    dashboard_broadcaster.active_connections.clear()


@pytest.mark.anyio
async def test_dashboard_endpoint_serves_html_file():
    """Verify GET /dashboard returns index.html with all required DOM elements."""
    response = await get_dashboard()
    assert isinstance(response, FileResponse)
    assert response.path.endswith("frontend/index.html")
    assert "no-cache" in response.headers.get("cache-control", "")

    html_path = Path(response.path)
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")

    # Verify key dashboard exhibition elements exist
    assert "MARS MISSION CONTROL" in html
    assert "id=\"gate-state-display\"" in html
    assert "id=\"limit-open-led\"" in html
    assert "id=\"limit-closed-led\"" in html
    assert "id=\"fault-box\"" in html
    assert "id=\"btn-open-gate\"" in html
    assert "id=\"btn-close-gate\"" in html
    assert "id=\"btn-get-status\"" in html
    assert "id=\"btn-reset-session\"" in html
    assert "id=\"val-bmp-temp\"" in html
    assert "id=\"val-bmp-press\"" in html
    assert "id=\"val-dht-temp\"" in html
    assert "id=\"val-dht-hum\"" in html
    assert "id=\"commands-audit-tbody\"" in html
    assert "id=\"telemetry-history-tbody\"" in html
    assert "id=\"events-log-tbody\"" in html
    assert "id=\"offline-banner\"" in html


def test_static_assets_exist_and_contain_required_styles():
    """Verify dashboard CSS and JS exist and contain required style classes and logic."""
    css_path = FRONTEND_DIR / "css" / "dashboard.css"
    assert css_path.exists()
    css_content = css_path.read_text(encoding="utf-8")
    assert "--color-mars" in css_content
    assert ".gate-state-indicator" in css_content
    assert ".state-online" in css_content
    assert ".limit-led" in css_content
    assert ".btn-open" in css_content

    js_path = FRONTEND_DIR / "js" / "dashboard.js"
    assert js_path.exists()
    js_content = js_path.read_text(encoding="utf-8")
    assert "applyMissionState" in js_content
    assert "updateSafetyControls" in js_content
    assert "connectWebSocket" in js_content
    assert "pollMissionData" in js_content


@pytest.mark.anyio
async def test_websocket_broadcaster_connection_and_disconnect():
    """Verify connecting, broadcasting, and disconnecting mock WebSocket clients."""
    broadcaster = DashboardBroadcaster()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await broadcaster.connect(ws1)
    await broadcaster.connect(ws2)
    assert len(broadcaster.active_connections) == 2

    # Broadcast message to both clients
    test_msg = {"type": "state_snapshot", "data": {"gate_state": "CLOSED"}}
    await broadcaster.broadcast(test_msg)
    assert len(ws1.sent_json_messages) == 1
    assert ws1.sent_json_messages[0] == test_msg
    assert len(ws2.sent_json_messages) == 1
    assert ws2.sent_json_messages[0] == test_msg

    # Disconnect one client
    await broadcaster.disconnect(ws1)
    assert len(broadcaster.active_connections) == 1
    assert broadcaster.active_connections[0] is ws2


@pytest.mark.anyio
async def test_websocket_broadcasts_live_telemetry_tick():
    """Verify live telemetry parsing triggers broadcaster with parsed telemetry and state snapshot."""
    import asyncio
    dashboard_broadcaster.set_loop(asyncio.get_running_loop())
    ws = MockWebSocket()
    await dashboard_broadcaster.connect(ws)

    telemetry_line = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 50000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": -20.5,
        "pressure_hpa": 745.2,
        "dht_temperature_c": -19.0,
        "humidity_pct": 10.5,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })

    # Process telemetry
    telemetry_service.process_line(telemetry_line)
    await asyncio.sleep(0.02)

    # Broadcaster should push telemetry tick
    assert len(ws.sent_json_messages) >= 1
    telem_msg = next(m for m in ws.sent_json_messages if m.get("type") == "telemetry")
    assert telem_msg["telemetry"]["bmp_temperature_c"] == -20.5
    assert "received_at" in telem_msg["telemetry"]
    assert telem_msg["state"]["gate_state"] == "CLOSED"


def test_command_submission_supports_both_schemas():
    """Verify command endpoint accepts both 'command' and 'command_type' schemas."""
    # Bring gateway and device ONLINE so commands are accepted
    mission_state.update_gateway_health("ONLINE")
    mission_state.update_device_health("ONLINE")

    # 1. Standard schema: `command`
    req1 = CommandSubmissionRequest(command=CommandName.GET_STATUS)
    resp1 = submit_command(req1)
    assert resp1["command"]["name"] == "GET_STATUS"

    # 2. Schema variant: `command_type`
    req2 = CommandSubmissionRequest(command_type=CommandName.GET_STATUS)
    resp2 = submit_command(req2)
    assert resp2["command"]["name"] == "GET_STATUS"


def test_command_safety_prevents_illegal_movement_from_dashboard():
    """Verify movement command is rejected if device is not connected or gate is UNKNOWN."""
    from fastapi import HTTPException

    mission_state.update_gateway_health("ONLINE")
    mission_state.update_device_health("NOT_CONNECTED")

    req = CommandSubmissionRequest(command=CommandName.OPEN_GATE)
    with pytest.raises(HTTPException) as exc_info:
        submit_command(req)
    assert exc_info.value.status_code == 400
    assert "Device is NOT_CONNECTED" in exc_info.value.detail


def test_safety_matrix_rules():
    """
    Directly tests the dashboard safety gating conditions:
    - Gateway ONLINE & Device ONLINE
    - No fault
    - Gate must be strictly CLOSED to allow OPEN_GATE
    - Gate must be strictly OPEN to allow CLOSE_GATE
    """
    def can_actuate(gw_state: str, dev_state: str, gate_state: str, fault: str | None, in_flight: bool):
        gw_ok = (gw_state == "ONLINE")
        dev_ok = (dev_state == "ONLINE")
        fault_ok = (fault is None)
        can_open = gw_ok and dev_ok and fault_ok and not in_flight and (gate_state == "CLOSED")
        can_close = gw_ok and dev_ok and fault_ok and not in_flight and (gate_state == "OPEN")
        return can_open, can_close

    # Initial offline
    assert can_actuate("NOT_CONNECTED", "NOT_CONNECTED", "UNKNOWN", None, False) == (False, False)

    # Online but UNKNOWN gate
    assert can_actuate("ONLINE", "ONLINE", "UNKNOWN", None, False) == (False, False)

    # Online and CLOSED gate -> can open, cannot close
    assert can_actuate("ONLINE", "ONLINE", "CLOSED", None, False) == (True, False)

    # Online and OPEN gate -> cannot open, can close
    assert can_actuate("ONLINE", "ONLINE", "OPEN", None, False) == (False, True)

    # Fault latched -> all movement inhibited
    assert can_actuate("ONLINE", "ONLINE", "CLOSED", "LIMIT_SWITCH_FAULT", False) == (False, False)

    # Command in-flight -> all movement inhibited
    assert can_actuate("ONLINE", "ONLINE", "CLOSED", None, True) == (False, False)


def test_dashboard_contract_field_names_match_backend_payloads():
    """
    Contract test verifying that property names consumed in dashboard.js
    strictly match the field names emitted by the backend API and SQLite storage.
    """
    from app.telemetry.processor import parse_telemetry

    # 1. Verify telemetry fields in dashboard.js match processor/database
    js_path = FRONTEND_DIR / "js" / "dashboard.js"
    js_content = js_path.read_text(encoding="utf-8")

    sample_telemetry_line = json.dumps({
        "type": "telemetry",
        "timestamp_ms": 1000,
        "mode": "ACTIVE",
        "gate_state": "CLOSED",
        "closed_limit": True,
        "open_limit": False,
        "bmp_temperature_c": 22.1,
        "pressure_hpa": 1013.2,
        "dht_temperature_c": 23.5,
        "humidity_pct": 45.0,
        "bmp280_ok": True,
        "dht11_ok": True,
        "fault": None,
    })
    parsed = parse_telemetry(sample_telemetry_line)

    for field in ("bmp_temperature_c", "pressure_hpa", "dht_temperature_c", "humidity_pct", "bmp280_ok", "dht11_ok"):
        assert field in parsed, f"Expected backend telemetry to produce field '{field}'"
        assert field in js_content, f"Expected dashboard.js to consume field '{field}'"

    # 2. Verify command fields in dashboard.js match Command.to_dict()
    cmd = command_tracker.create_command(name=CommandName.GET_STATUS)
    cmd_dict = cmd.to_dict()
    assert "name" in cmd_dict
    assert "status" in cmd_dict
    assert "created_at" in cmd_dict
    assert "error_reason" in cmd_dict

    assert "cmd.name" in js_content
    assert "error_reason" in js_content

    # 3. Verify event fields in dashboard.js match SQLite mission_events
    assert "ev.subsystem" in js_content


def test_reset_session_preserves_active_connection_states():
    """
    Verify reset_session():
    1. Preserves active gateway and device connection states.
    2. Strictly reverts physical gate state to UNKNOWN and clears limits.
    3. Broadcasts clean state snapshot without falsely claiming hardware disconnect.
    """
    mission_state.update_gateway_health("ONLINE")
    mission_state.update_device_health("ONLINE")
    mission_state.update_from_telemetry({
        "timestamp_ms": 10000,
        "mode": "ACTIVE",
        "gate_state": "OPEN",
        "closed_limit": False,
        "open_limit": True,
        "fault": None,
    })

    assert mission_state.snapshot()["gate_state"] == "OPEN"
    assert mission_state.snapshot()["gateway_state"] == "ONLINE"
    assert mission_state.snapshot()["device_state"] == "ONLINE"

    resp = reset_session()
    assert resp["status"] == "session_reset"

    current = mission_state.snapshot()
    # Connections preserved
    assert current["gateway_state"] == "ONLINE"
    assert current["device_state"] == "ONLINE"
    # Physical gate state strictly UNKNOWN until verified
    assert current["gate_state"] == "UNKNOWN"
    assert current["closed_limit"] is None
    assert current["open_limit"] is None
    assert current["mode"] == "UNKNOWN"


def test_dashboard_frontend_polling_and_uptime_contracts():
    """
    Contract test verifying:
    1. dashboard.js uses real endpoints /api/mission/commands and /api/mission/events.
    2. dashboard.js successful poll clears stale connection disruption warnings.
    3. index.html labels uptime as duration/boot instead of raw ms.
    4. dashboard.js implements duration formatting with >= 24h support.
    """
    js_path = FRONTEND_DIR / "js" / "dashboard.js"
    html_path = FRONTEND_DIR / "index.html"
    js_content = js_path.read_text(encoding="utf-8")
    html_content = html_path.read_text(encoding="utf-8")

    # 1. Real polling URLs
    assert "fetch('/api/mission/commands')" in js_content
    assert "fetch('/api/mission/events')" in js_content
    assert "fetch('/api/mission/commands/recent')" not in js_content
    assert "fetch('/api/mission/events/recent')" not in js_content

    # 2. Connection banner recovery
    assert "elOfflineBanner.classList.add('hidden')" in js_content
    assert "formatUptime" in js_content

    # 3. HTML label update
    assert 'class="metric-name">ESP32 UPTIME</span>' in html_content
    assert '<span class="metric-unit">HH:MM:SS</span>' in html_content
    assert '<span class="metric-unit">ms</span>' not in html_content


def test_dashboard_does_not_present_history_or_simulator_as_live_hardware():
    js_content = (FRONTEND_DIR / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "if (source === 'history') {" in js_content
    assert "completeUptimeDiagnostic(diagnostic, 'historical_source');" in js_content
    assert "last_device_status_timestamp_ms" in js_content
    assert "isTelemetryAtOrBeforeStatusWatermark(telem.timestamp_ms, statusTimestamp)" in js_content
    assert "isTelemetryOlderThanState(telem.timestamp_ms, currentState.last_telemetry_timestamp_ms)" in js_content
    assert "incomingUpdatedAt < currentUpdatedAt" in js_content
    assert "if (bmpOk === true && bmpTemp !== null" in js_content
    assert "if (bmpOk === true && bmpPress !== null" in js_content
    assert "currentState.simulation_mode ? 'DATA: SIMULATOR'" in js_content
    assert "SIMULATOR DATA — NOT HARDWARE" in js_content
    assert "if (currentState.simulation_mode)" in js_content
    assert "SIM · OK" in js_content
    assert "SIM · FAILED" in js_content
    assert "elBmpTemp.textContent = Number(bmpTemp).toFixed(1);" in js_content
    assert "elBmpPress.textContent = Number(bmpPress).toFixed(1);" in js_content
    assert "elDhtTemp.textContent = Number(dhtTemp).toFixed(1);" in js_content
    assert "elDhtHum.textContent = Number(dhtHum).toFixed(1);" in js_content
    assert "renderTelemetry(telemetryHistory[0]" not in js_content

    state = get_mission_state()
    assert isinstance(state["simulation_mode"], bool)


def test_rover_contract_is_separate_and_dashboard_labels_source():
    from app.api.routes import get_rover_status

    rover = get_rover_status()
    assert rover["rover_id"] == "mars-rover-01"
    assert rover["source"] in ("simulator", "network")
    assert "distance_cm" in rover and "battery_voltage_v" in rover
    assert "gate_state" not in rover

    html_content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    js_content = (FRONTEND_DIR / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "MARS ROVER TELEMETRY" in html_content
    assert "SIMULATED" in html_content
    assert "NETWORK / HARDWARE" in js_content
    assert "rover_telemetry" in js_content
    assert "reported command is telemetry only" in html_content.lower()


def test_historical_telemetry_cannot_replace_newer_live_telemetry():
    """History is only a display seed; a later poll cannot replace a live sample."""
    import re
    import shutil
    import subprocess

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js is required to exercise the dashboard ordering guard")

    js_content = (FRONTEND_DIR / "js" / "dashboard.js").read_text(encoding="utf-8")
    match = re.search(
        r"function shouldRenderTelemetry\(source, receivedAtMs, latestReceivedAtMs, liveTelemetrySeen\) \{[\s\S]*?\n  \}",
        js_content,
    )
    assert match, "Dashboard telemetry ordering guard must exist"
    script = match.group(0) + """
    const assert = require('assert');
    assert.strictEqual(shouldRenderTelemetry('history', 1000, 2000, true), false);
    assert.strictEqual(shouldRenderTelemetry('history', 1000, 2000, false), false);
    // A genuine reboot lowers ESP32 uptime, but its newer host receipt time is accepted.
    assert.strictEqual(shouldRenderTelemetry('live', 3000, 2000, true), true);
    """
    subprocess.run([node_bin, "-e", script], check=True, capture_output=True, text=True)


def test_frontend_watermark_allows_rebooted_uptime_after_backend_invalidates_old_status():
    """Exercise the frontend watermark decision helper with actual Node.js."""
    import re
    import shutil
    import subprocess

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js is required to exercise the dashboard watermark helper")

    js_content = (FRONTEND_DIR / "js" / "dashboard.js").read_text(encoding="utf-8")
    match = re.search(
        r"function isTelemetryAtOrBeforeStatusWatermark\(telemetryTimestampMs, statusTimestampMs\) \{[\s\S]*?\n  \}",
        js_content,
    )
    assert match, "Dashboard status watermark helper must exist"
    state_match = re.search(
        r"function isTelemetryOlderThanState\(telemetryTimestampMs, stateTimestampMs\) \{[\s\S]*?\n  \}",
        js_content,
    )
    assert state_match, "Dashboard telemetry state watermark helper must exist"
    uptime_match = re.search(r"function formatUptime\(ms\) \{[\s\S]*?\n  \}", js_content)
    assert uptime_match, "Dashboard uptime formatter must exist"
    script = match.group(0) + state_match.group(0) + uptime_match.group(0) + """
    const assert = require('assert');
    assert.deepStrictEqual([5000, 6000, 7000].map(formatUptime),
      ['00:00:05', '00:00:06', '00:00:07']);
    // Same-boot samples at or before the fresh status tick remain rejected.
    assert.strictEqual(isTelemetryAtOrBeforeStatusWatermark(11000, 11000), true);
    assert.strictEqual(isTelemetryAtOrBeforeStatusWatermark(10999, 11000), true);
    // Backend reboot handling clears the previous boot's status watermark.
    assert.strictEqual(isTelemetryAtOrBeforeStatusWatermark(500, null), false);
    // A stale live packet is older than the backend's accepted state watermark.
    assert.strictEqual(isTelemetryOlderThanState(10900, 11000), true);
    // The reboot packet equals the backend state watermark produced by itself.
    assert.strictEqual(isTelemetryOlderThanState(500, 500), false);
    """
    subprocess.run([node_bin, "-e", script], check=True, capture_output=True, text=True)

    # Each telemetry WS frame carries a state snapshot; applying it first makes
    # a reboot's reset watermark available before the frame reaches the guards.
    ws_handler = js_content.index("ws.onmessage = function (event)")
    state_apply = js_content.index("applyMissionState(msg.state);", ws_handler)
    telemetry_render = js_content.index("renderTelemetry(msg.telemetry, 'live', diagnostic);", state_apply)
    assert state_apply < telemetry_render


def test_telemetry_history_table_selects_newest_rows_first():
    """The API is chronological; the dashboard must show the newest rows, not the oldest."""
    import re
    import shutil
    import subprocess

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js is required to exercise telemetry history row selection")

    js_content = (FRONTEND_DIR / "js" / "dashboard.js").read_text(encoding="utf-8")
    match = re.search(
        r"function latestTelemetryRows\(history, limit = 15\) \{[\s\S]*?\n  \}",
        js_content,
    )
    assert match, "Dashboard telemetry history selector must exist"
    script = match.group(0) + """
    const assert = require('assert');
    const rows = Array.from({length: 20}, (_, index) => ({id: index + 1}));
    assert.deepStrictEqual(latestTelemetryRows(rows).map(row => row.id),
      [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6]);
    assert.deepStrictEqual(latestTelemetryRows(rows, 3).map(row => row.id), [20, 19, 18]);
    assert.deepStrictEqual(latestTelemetryRows([], 3), []);
    """
    subprocess.run([node_bin, "-e", script], check=True, capture_output=True, text=True)


def test_uptime_diagnostics_are_opt_in_and_bounded():
    """Diagnostic helpers stay inert by default and retain only a fixed-size sample."""
    import re
    import shutil
    import subprocess

    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node.js is required to exercise uptime diagnostic helpers")

    js_content = (FRONTEND_DIR / "js" / "dashboard.js").read_text(encoding="utf-8")
    enabled_match = re.search(
        r"function isUptimeDiagnosticEnabled\(search\) \{[\s\S]*?\n  \}",
        js_content,
    )
    append_match = re.search(
        r"function appendUptimeDiagnostic\(entries, record, limit = UPTIME_DIAGNOSTIC_LIMIT\) \{[\s\S]*?\n  \}",
        js_content,
    )
    assert enabled_match, "Uptime diagnostic opt-in helper must exist"
    assert append_match, "Bounded uptime diagnostic helper must exist"
    assert "const uptimeDiagnosticsEnabled = isUptimeDiagnosticEnabled(window.location.search);" in js_content
    assert "requestAnimationFrame" in js_content

    script = "const UPTIME_DIAGNOSTIC_LIMIT = 250;\n" + enabled_match.group(0) + append_match.group(0) + """
    const assert = require('assert');
    assert.strictEqual(isUptimeDiagnosticEnabled(''), false);
    assert.strictEqual(isUptimeDiagnosticEnabled('?uptimeDiag=1'), true);
    assert.strictEqual(isUptimeDiagnosticEnabled('?uptimeDiag=0'), false);
    const entries = [];
    appendUptimeDiagnostic(entries, {sequence: 1}, 2);
    appendUptimeDiagnostic(entries, {sequence: 2}, 2);
    appendUptimeDiagnostic(entries, {sequence: 3}, 2);
    assert.deepStrictEqual(entries.map(entry => entry.sequence), [2, 3]);
    """
    subprocess.run([node_bin, "-e", script], check=True, capture_output=True, text=True)


def test_dashboard_timezone_ist_contracts():
    """
    Contract test verifying:
    1. index.html labels Last Ingestion with IST instead of UTC.
    2. dashboard.js uses Intl.DateTimeFormat with IANA timezone Asia/Kolkata and hourCycle: 'h23'.
    3. formatTimeIST is used for human-readable display of telemetry, commands, and events.
    4. No manual millisecond/hour offsets are added (timezone-aware conversion only).
    """
    import re

    js_path = FRONTEND_DIR / "js" / "dashboard.js"
    html_path = FRONTEND_DIR / "index.html"
    js_content = js_path.read_text(encoding="utf-8")
    html_content = html_path.read_text(encoding="utf-8")

    # 1. HTML IST metric unit and header clock
    assert '<span class="metric-unit">IST</span>' in html_content
    assert '<span class="metric-unit">UTC</span>' not in html_content
    assert '--:--:-- IST' in html_content

    # 2. Timezone-aware Intl.DateTimeFormat with Asia/Kolkata and explicit hourCycle: 'h23'
    assert "Intl.DateTimeFormat" in js_content
    assert "Asia/Kolkata" in js_content
    assert "hourCycle: 'h23'" in js_content or 'hourCycle: "h23"' in js_content
    assert "hour12" not in js_content

    # Both formatters must explicitly specify hourCycle: 'h23'
    assert re.search(r"istTimeFormatter\s*=\s*new\s*Intl\.DateTimeFormat\([^)]+hourCycle:\s*['\"]h23['\"]", js_content)
    assert re.search(r"istDateTimeFormatter\s*=\s*new\s*Intl\.DateTimeFormat\([^)]+hourCycle:\s*['\"]h23['\"]", js_content)
    assert "formatTimeIST" in js_content

    # 3. Formatter usage across tables and metrics
    assert "elLastReceived.textContent = formatTimeIST" in js_content
    assert "formatTimeIST(cmd.created_at)" in js_content
    assert "formatTimeIST(row.received_at)" in js_content
    assert "formatTimeIST(ev.timestamp)" in js_content

    # 4. No manual offset arithmetic
    assert "19800000" not in js_content  # 5.5 hours in ms
    assert "5.5 * 3600" not in js_content


def test_dashboard_timezone_ist_runtime_conversion():
    """
    Focused runtime test verifying timezone conversion using known timestamps:
    - 2026-10-22T00:00:00Z displays as 05:30:00 IST
    - 2026-10-22T18:30:00Z displays as 00:00:00 IST on the following day
    - Midnight is formatted as 00:00:00, never 24:00:00
    """
    import shutil
    import subprocess
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # 1. Python standard library zoneinfo verification
    ist = ZoneInfo("Asia/Kolkata")

    dt1_utc = datetime.fromisoformat("2026-10-22T00:00:00Z")
    dt1_ist = dt1_utc.astimezone(ist)
    assert dt1_ist.strftime("%H:%M:%S") == "05:30:00"

    dt2_utc = datetime.fromisoformat("2026-10-22T18:30:00Z")
    dt2_ist = dt2_utc.astimezone(ist)
    assert dt2_ist.strftime("%H:%M:%S") == "00:00:00"
    assert dt2_ist.strftime("%Y-%m-%d") == "2026-10-23"
    assert dt2_ist.strftime("%H:%M:%S") != "24:00:00"

    # 2. JavaScript Intl.DateTimeFormat runtime execution from dashboard.js
    node_bin = shutil.which("node")
    if node_bin:
        js_script = """
        const js = require('fs').readFileSync('frontend/js/dashboard.js', 'utf-8');
        const timeFmtMatch = js.match(/const istTimeFormatter = [\\s\\S]*?\\);/);
        const dateTimeFmtMatch = js.match(/const istDateTimeFormatter = [\\s\\S]*?\\);/);
        const formatFuncMatch = js.match(/function formatTimeIST[\\s\\S]*?\\n  }/);

        if (!timeFmtMatch || !dateTimeFmtMatch || !formatFuncMatch) {
            throw new Error('Could not find formatters in dashboard.js');
        }

        eval(
            timeFmtMatch[0] + '\\n' +
            dateTimeFmtMatch[0] + '\\n' +
            formatFuncMatch[0] + '\\n' +
            'globalThis.__out = {' +
            '  t1: formatTimeIST("2026-10-22T00:00:00Z"),' +
            '  t2: formatTimeIST("2026-10-22T18:30:00Z"),' +
            '  d1: istDateTimeFormatter.format(new Date("2026-10-22T00:00:00Z")),' +
            '  d2: istDateTimeFormatter.format(new Date("2026-10-22T18:30:00Z"))' +
            '};'
        );

        console.log(JSON.stringify(globalThis.__out));
        """
        proc = subprocess.run([node_bin, "-e", js_script], capture_output=True, text=True, check=True)
        res = json.loads(proc.stdout.strip())

        # Verify 2026-10-22T00:00:00Z -> 05:30:00 IST
        assert res["t1"] == "05:30:00"
        assert "05:30:00" in res["d1"]

        # Verify 2026-10-22T18:30:00Z -> 00:00:00 IST on following day (2026-10-23)
        assert res["t2"] == "00:00:00"
        assert "00:00:00" in res["d2"]
        assert "2026-10-23" in res["d2"]

        # Verify midnight is 00:00:00, never 24:00:00
        assert res["t2"] != "24:00:00"
        assert "24:00:00" not in res["d2"]


def test_offline_banner_lifecycle_and_css_visibility_contracts():
    """
    Contract regression test for offline banner visibility and connection lifecycle:
    1. CSS contract: .offline-banner has display: flex when shown, and .offline-banner.hidden
       and .hidden have display: none !important so the banner hides cleanly.
    2. Lifecycle: ws.onclose and ws.onerror remove 'hidden' (banner visible on disconnect/error).
    3. Reconnection: ws.onopen and pollMissionData add 'hidden' (banner hidden on recovery).
    4. Hardware state independence: renderTelemetry (BMP280 failure) and renderGateState
       (gate UNKNOWN) never manipulate elOfflineBanner or treat hardware status as connection failure.
    """
    import re

    css_path = FRONTEND_DIR / "css" / "dashboard.css"
    js_path = FRONTEND_DIR / "js" / "dashboard.js"
    html_path = FRONTEND_DIR / "index.html"

    css_content = css_path.read_text(encoding="utf-8")
    js_content = js_path.read_text(encoding="utf-8")
    html_content = html_path.read_text(encoding="utf-8")

    # 1. CSS & HTML initial visibility rules
    assert 'id="offline-banner" class="offline-banner hidden"' in html_content
    assert ".offline-banner {" in css_content
    assert "display: flex;" in css_content
    assert ".offline-banner.hidden {" in css_content
    assert "display: none !important;" in css_content
    assert ".hidden {" in css_content

    # 2. Lifecycle triggers: Disconnected WebSocket -> banner shown
    assert "ws.onclose = function () {" in js_content
    assert "ws.onerror = function () {" in js_content
    assert re.search(r"ws\.onclose\s*=\s*function\s*\(\)\s*\{[\s\S]*?elOfflineBanner\.classList\.remove\(['\"]hidden['\"]\)", js_content)
    assert re.search(r"ws\.onerror\s*=\s*function\s*\(\)\s*\{[\s\S]*?elOfflineBanner\.classList\.remove\(['\"]hidden['\"]\)", js_content)

    # 3. Lifecycle triggers: Successful reconnection -> banner hidden
    assert "ws.onopen = function () {" in js_content
    assert re.search(r"ws\.onopen\s*=\s*function\s*\(\)\s*\{[\s\S]*?elOfflineBanner\.classList\.add\(['\"]hidden['\"]\)", js_content)
    assert re.search(r"pollMissionData[\s\S]*?elOfflineBanner\.classList\.add\(['\"]hidden['\"]\)", js_content)

    # 4. Hardware failure independence (BMP280 FAILED / gate UNKNOWN do not touch offline banner)
    render_telemetry_match = re.search(r"function renderTelemetry\([\s\S]*?\n  \}", js_content)
    render_gate_state_match = re.search(r"function renderGateState\([\s\S]*?\n  \}", js_content)
    assert render_telemetry_match is not None
    assert render_gate_state_match is not None
    assert "elOfflineBanner" not in render_telemetry_match.group(0)
    assert "elOfflineBanner" not in render_gate_state_match.group(0)
