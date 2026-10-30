from pathlib import Path
import pytest
from app.main import app, FRONTEND_DIR


async def asgi_request(path: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    """Helper to dispatch requests directly to the FastAPI ASGI application."""
    import asyncio
    messages = []
    first = True
    disconnect_event = asyncio.Event()

    async def receive():
        nonlocal first
        if first:
            first = False
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnect_event.wait()
        return {"type": "http.disconnect"}

    async def send(msg):
        messages.append(msg)
        if msg["type"] == "http.response.body" and not msg.get("more_body", False):
            disconnect_event.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"host", b"localhost:8000")],
        "client": ("127.0.0.1", 12345),
        "server": ("localhost", 8000),
    }
    await app(scope, receive, send)

    status_code = messages[0]["status"]
    headers = {k.decode().lower(): v.decode() for k, v in messages[0]["headers"]}
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status_code, headers, body


def test_frontend_directory_and_assets_exist():
    assert FRONTEND_DIR.exists(), f"Frontend dir missing at {FRONTEND_DIR}"
    assert (FRONTEND_DIR / "index.html").is_file()

    # CSS files
    for css_file in ["theme.css", "landing.css", "lander.css", "rover.css", "drone.css"]:
        assert (FRONTEND_DIR / "css" / css_file).is_file(), f"Missing CSS file: {css_file}"

    # JS files
    for js_file in [
        "formatters.js",
        "lander-view.js",
        "rover-view.js",
        "drone-view.js",
        "landing.js",
        "mission-client.js",
    ]:
        assert (FRONTEND_DIR / "js" / js_file).is_file(), f"Missing JS file: {js_file}"


def test_frontend_index_html_contracts():
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")

    # All 4 subsystem views present
    assert 'id="landing-view"' in html
    assert 'id="lander-view"' in html
    assert 'id="rover-view"' in html
    assert 'id="drone-view"' in html

    # Diagnostic action buttons
    assert 'id="btn-cmd-status"' in html
    assert 'id="btn-cmd-active"' in html
    assert 'id="btn-cmd-standby"' in html
    assert 'id="btn-cmd-reset"' in html

    # Script tags in order (served from /static/)
    assert '<script src="/static/js/formatters.js"></script>' in html
    assert '<script src="/static/js/lander-view.js"></script>' in html
    assert '<script src="/static/js/rover-view.js"></script>' in html
    assert '<script src="/static/js/drone-view.js"></script>' in html
    assert '<script src="/static/js/landing.js"></script>' in html
    assert '<script src="/static/js/mission-client.js"></script>' in html


def test_frontend_mission_client_integration():
    client_js = (FRONTEND_DIR / "js" / "mission-client.js").read_text(encoding="utf-8")

    # WebSocket connection & protocol
    assert "/ws/telemetry" in client_js
    assert "state_snapshot" in client_js
    assert "rover_telemetry" in client_js
    assert "drone_telemetry" in client_js
    assert "command_update" in client_js

    # REST APIs
    assert "/api/mission/state" in client_js
    assert "/api/mission/commands" in client_js
    assert "/api/mission/events" in client_js
    assert "/api/mission/telemetry/history" in client_js
    assert "/api/rover/status" in client_js
    assert "/api/drone/status" in client_js
    assert "/api/mission/session/reset" in client_js

    # Exported interface
    assert "window.MMCMissionClient =" in client_js
    assert "sendCommand" in client_js
    assert "resetSession" in client_js


@pytest.mark.anyio
async def test_dashboard_http_serves_html():
    status, headers, body = await asgi_request("/dashboard")
    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    assert "no-cache" in headers.get("cache-control", "")
    assert b"Mars Mission Control" in body


@pytest.mark.anyio
async def test_dashboard_http_serves_mission_client_js():
    # The new frontend serves JS from /static/js/ since it's mounted at /static
    status, headers, body = await asgi_request("/static/js/mission-client.js")
    assert status == 200
    assert "no-cache" in headers.get("cache-control", "")
    assert b"window.MMCMissionClient" in body


@pytest.mark.anyio
async def test_dashboard_http_serves_css():
    status, headers, body = await asgi_request("/static/css/theme.css")
    assert status == 200
    assert "no-cache" in headers.get("cache-control", "")