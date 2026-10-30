from pathlib import Path

from app.main import FRONTEND_DIR


def test_rover_view_has_telemetry_title_and_no_gate_controls():
    html = (FRONTEND_DIR / "index.html").read_text()
    rover_js = (FRONTEND_DIR / "js" / "rover-view.js").read_text()
    mission_client_js = (FRONTEND_DIR / "js" / "mission-client.js").read_text()

    # Rover view title in HTML
    assert "MARS TERRAIN MAP" in html
    assert "SECTOR 04" in html

    # SIMULATED DATA source indicator in rover-view.js
    assert "SOURCE: SIMULATOR" in rover_js
    assert "SOURCE: HARDWARE" in rover_js

    # No gate/actuator controls in HTML or JS
    assert "btn-open-gate" not in html and "btn-close-gate" not in html
    assert "OPEN_GATE" not in rover_js and "CLOSE_GATE" not in rover_js
    assert "OPEN_GATE" not in mission_client_js and "CLOSE_GATE" not in mission_client_js


def test_mission_client_fetches_rover_status_and_handles_websocket():
    mission_client_js = (FRONTEND_DIR / "js" / "mission-client.js").read_text()

    # REST API fetch for rover status
    assert "fetch(`${getApiBase()}/api/rover/status`)" in mission_client_js

    # WebSocket message handler for rover_telemetry
    assert "msg.type === 'rover_telemetry'" in mission_client_js
