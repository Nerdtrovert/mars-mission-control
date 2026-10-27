from pathlib import Path

from app.main import FRONTEND_DIR


def test_dashboard_has_rover_simulation_label_and_no_ramp_controls():
    html = (FRONTEND_DIR / "index.html").read_text()
    js = (FRONTEND_DIR / "js" / "dashboard.js").read_text()
    assert "MARS ROVER TELEMETRY" in html
    assert "SIMULATED DATA" in js
    assert "btn-open-gate" not in html and "btn-close-gate" not in html
    assert "OPEN_GATE" not in js and "CLOSE_GATE" not in js


def test_dashboard_receives_rover_status_over_api_and_websocket():
    js = (FRONTEND_DIR / "js" / "dashboard.js").read_text()
    assert "fetch('/api/rover/status')" in js
    assert "msg.type === 'rover_telemetry'" in js
