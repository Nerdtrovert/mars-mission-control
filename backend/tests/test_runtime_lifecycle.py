import asyncio

from app.communication.rover_runner import RoverRunner
from app.communication.rover_model import RoverStatus


def test_rover_simulator_runner_starts_publishes_and_stops():
    async def run():
        updates: list[RoverStatus] = []
        runner = RoverRunner("simulator", "http://127.0.0.1:8001", updates.append, interval_s=0.01)
        await runner.start()
        await asyncio.sleep(0)
        await runner.stop()
        assert updates and updates[0].source.value == "simulator"
        assert not runner.is_running
    asyncio.run(run())
