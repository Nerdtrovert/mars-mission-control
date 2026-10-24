"""Deterministic tests for the independent rover simulator and public model."""

from datetime import datetime, timezone
import pytest

from app.communication.rover_model import RoverConnectionState, RoverSource
from app.communication.rover_runner import RoverRunner
from app.communication.rover_simulator import RoverSimulator


def test_rover_simulator_initializes_and_updates_bounded_telemetry():
    simulator = RoverSimulator()
    initial = simulator.snapshot()
    assert initial.rover_id == "mars-rover-01"
    assert initial.source == RoverSource.SIMULATOR
    assert initial.connection_state == RoverConnectionState.OFFLINE

    sample = simulator.step(datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert sample.connection_state == RoverConnectionState.ONLINE
    assert sample.distance_cm == 144.7
    assert sample.battery_percentage is None
    assert sample.source == RoverSource.SIMULATOR
    assert -90 <= sample.pitch_deg <= 90
    assert -90 <= sample.roll_deg <= 90


def test_obstacle_and_telemetry_interruption_are_repeatable():
    simulator = RoverSimulator()
    simulator.tick = 10
    obstacle = simulator.step(datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert obstacle.obstacle_detected is True
    assert obstacle.command == "S"
    assert obstacle.event == "Simulated obstacle detected"

    simulator.set_telemetry_enabled(False)
    interrupted = simulator.step()
    assert interrupted.connection_state == RoverConnectionState.OFFLINE
    assert interrupted.event == "Simulated telemetry interruption"
    assert interrupted.last_seen == obstacle.last_seen


@pytest.mark.anyio
async def test_runner_publishes_local_simulator_source():
    published = []
    runner = RoverRunner("simulator", "http://127.0.0.1:8001", published.append, interval_s=0.01)
    await runner.start()
    await runner.stop()
    assert published
    assert published[0].source == RoverSource.SIMULATOR
    assert runner.is_running is False


def test_network_runner_normalizes_gateway_source(monkeypatch):
    runner = RoverRunner("network", "http://pi:8001", lambda _: None)
    from app.communication.rover_model import RoverStatus

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"rover_id":"mars-rover-01","source":"simulator","connection_state":"ONLINE"}'

    captured = {}

    def fake_urlopen(request, **_kwargs):
        captured["url"] = request.full_url
        return Response()

    monkeypatch.setattr("app.communication.rover_runner.urllib.request.urlopen", fake_urlopen)
    fetched = runner._fetch_network_status()
    assert captured["url"] == "http://pi:8001/api/rover/status"
    assert fetched.source == RoverSource.NETWORK
    assert fetched.connection_state == RoverConnectionState.ONLINE


def test_network_runner_returns_offline_when_gateway_is_unavailable(monkeypatch):
    runner = RoverRunner("network", "http://pi:8001", lambda _: None)
    monkeypatch.setattr(
        "app.communication.rover_runner.urllib.request.urlopen",
        lambda *_a, **_kw: (_ for _ in ()).throw(OSError("offline")),
    )
    fetched = runner._fetch_network_status()
    assert fetched.connection_state == RoverConnectionState.OFFLINE
    assert fetched.source == RoverSource.NETWORK
