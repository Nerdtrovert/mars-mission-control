import os
from threading import RLock
from fastapi import APIRouter, HTTPException, status, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Any, Optional

from app.communication.broadcaster import DashboardBroadcaster
from app.communication.gateway_client import GatewayClient
from app.communication.gateway_contract import CommandName
from app.communication.gateway_simulator import GatewaySimulator
from app.communication.network_runner import NetworkGatewayRunner
from app.communication.simulator_runner import SimulatorRunner
from app.communication.rover_model import RoverSource, RoverStatus, offline_status
from app.communication.rover_runner import RoverRunner
from app.communication.drone_model import DroneStatus, offline_drone_status
from app.communication.drone_runner import DroneRunner
from app.mission.command import (
    CommandSafetyViolation,
    CommandTracker,
    DuplicateCommandError,
)
from app.mission.state import MissionStateManager
from app.storage.event_recorder import MissionEventRecorder
from app.storage.sqlite_storage import SQLiteStorage
from app.telemetry.service import TelemetryService

router = APIRouter()

# Global session synchronization lock
session_lock = RLock()

# Live dashboard WebSocket broadcaster
dashboard_broadcaster = DashboardBroadcaster()

# Storage and Event Recording
db_path = os.getenv("MISSION_DB_PATH", "data/mission_control.db")
storage = SQLiteStorage(db_path=db_path)
event_recorder = MissionEventRecorder(storage=storage)

# Preserved baseline instances
mission_state = MissionStateManager()


def _dashboard_state(state: dict) -> dict:
    """Attach the active data source so simulated values are never ambiguous."""
    active = globals().get("active_runner")
    return {**state, "simulation_mode": bool(getattr(active, "IS_SIMULATOR", True))}


def _on_state_transition(prev: dict, curr: dict) -> None:
    event_recorder.evaluate_state_transition(prev, curr)
    dashboard_broadcaster.broadcast_sync({
        "type": "state_snapshot",
        "data": _dashboard_state(curr),
    })


# Wire event recorder & live dashboard broadcaster to state transitions
mission_state.set_listener(_on_state_transition)

telemetry_service = TelemetryService(
    mission_state,
    storage=storage,
    event_recorder=event_recorder,
)


def _on_telemetry_received(telemetry: dict, state: dict) -> None:
    dashboard_broadcaster.broadcast_sync({
        "type": "telemetry",
        "telemetry": telemetry,
        "state": _dashboard_state(state),
    })


telemetry_service.set_telemetry_listener(_on_telemetry_received)

command_tracker = CommandTracker(storage=storage)
command_tracker.load_history_from_storage()

# Gateway Mode Selection: "simulator" (default) or "network" ("real")
GATEWAY_MODE = (os.getenv("GATEWAY_MODE") or "simulator").strip().rstrip("\\").strip().lower()
GATEWAY_HTTP_URL = (os.getenv("GATEWAY_HTTP_URL") or "http://127.0.0.1:8001").strip().rstrip("\\").strip()


def _derive_ws_url(http_url: str) -> str:
    url = http_url.rstrip("/")
    if url.startswith("https://"):
        return f"wss://{url[8:]}/ws/telemetry"
    elif url.startswith("http://"):
        return f"ws://{url[7:]}/ws/telemetry"
    return f"ws://{url}/ws/telemetry"


GATEWAY_WS_URL = os.getenv("GATEWAY_WS_URL") or _derive_ws_url(GATEWAY_HTTP_URL)
ROVER_MODE = (os.getenv("ROVER_MODE") or "simulator").strip().rstrip("\\").strip().lower()
if ROVER_MODE not in ("simulator", "network"):
    raise ValueError("ROVER_MODE must be 'simulator' or 'network'")


def _publish_rover_status(status: RoverStatus) -> None:
    dashboard_broadcaster.broadcast_sync({
        "type": "rover_telemetry",
        "rover": status.model_dump(mode="json"),
    })

# Default in-memory simulator for hardware-free development and tests
gateway_simulator = GatewaySimulator()

if GATEWAY_MODE in ("network", "real"):
    gateway_client = GatewayClient(
        state_manager=mission_state,
        telemetry_service=telemetry_service,
        command_tracker=command_tracker,
        http_url=GATEWAY_HTTP_URL,
    )
    active_runner = NetworkGatewayRunner(
        gateway_client=gateway_client,
        state_manager=mission_state,
        ws_url=GATEWAY_WS_URL,
        http_url=GATEWAY_HTTP_URL,
        storage=storage,
        broadcaster=dashboard_broadcaster,
    )
    simulator_runner = SimulatorRunner(
        gateway_client=GatewayClient(
            state_manager=mission_state,
            telemetry_service=telemetry_service,
            command_tracker=command_tracker,
            simulator=gateway_simulator,
        ),
        simulator=gateway_simulator,
        state_manager=mission_state,
        storage=storage,
    )
else:
    gateway_client = GatewayClient(
        state_manager=mission_state,
        telemetry_service=telemetry_service,
        command_tracker=command_tracker,
        simulator=gateway_simulator,
    )
    simulator_runner = SimulatorRunner(
        gateway_client=gateway_client,
        simulator=gateway_simulator,
        state_manager=mission_state,
        storage=storage,
    )
    active_runner = simulator_runner

rover_runner = RoverRunner(
    mode=ROVER_MODE,
    http_url=GATEWAY_HTTP_URL,
    publish=_publish_rover_status,
)

DRONE_MODE = (os.getenv("DRONE_MODE") or "simulator").strip().rstrip("\\").strip().lower()
if DRONE_MODE not in ("simulator", "network"):
    raise ValueError("DRONE_MODE must be 'simulator' or 'network'")


def _publish_drone_status(status: DroneStatus) -> None:
    dashboard_broadcaster.broadcast_sync({
        "type": "drone_telemetry",
        "drone": status.model_dump(mode="json"),
    })


drone_runner = DroneRunner(
    mode=DRONE_MODE,
    http_url=GATEWAY_HTTP_URL,
    publish=_publish_drone_status,
)


class CommandSubmissionRequest(BaseModel):
    command: Optional[CommandName] = None
    command_type: Optional[CommandName] = None
    command_id: Optional[str] = None
    params: Optional[dict[str, Any]] = None

    def resolved_command(self) -> CommandName:
        cmd = self.command or self.command_type
        if not cmd:
            raise ValueError("Field 'command' or 'command_type' is required.")
        return cmd


@router.get("/api/mission/state")
def get_mission_state():
    """Preserved baseline endpoint returning the current mission state snapshot."""
    return _dashboard_state(mission_state.snapshot())


@router.get("/api/rover/status")
def get_rover_status():
    """Return independent rover state using the common simulator/network contract."""
    return rover_runner.snapshot().model_dump(mode="json")


@router.get("/api/drone/status")
def get_drone_status():
    """Return independent drone state using the common simulator/network contract."""
    return drone_runner.snapshot().model_dump(mode="json")


@router.get("/api/mission/commands")
def list_commands():
    """List tracked commands and their lifecycle statuses."""
    return [cmd.to_dict() for cmd in command_tracker.list_commands()]


@router.post("/api/mission/commands", status_code=status.HTTP_200_OK)
def submit_command(req: CommandSubmissionRequest):
    """Submit a command following strict safety rules."""
    with session_lock:
        try:
            cmd_name = req.resolved_command()
            cmd = command_tracker.create_command(
                name=cmd_name,
                command_id=req.command_id,
                params=req.params,
            )
            resp = gateway_client.dispatch_command(cmd)
            result = {
                "command": cmd.to_dict(),
                "gateway_response": resp.model_dump(),
            }
            dashboard_broadcaster.broadcast_sync({
                "type": "command_update",
                "command": cmd.to_dict(),
            })
            return result
        except (DuplicateCommandError, CommandSafetyViolation, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )


@router.get("/api/mission/events")
def list_events(
    limit: int = 100,
    event_type: Optional[str] = None,
):
    """Query recent mission events."""
    actual_limit = getattr(limit, "default", limit)
    return storage.get_events(limit=actual_limit, event_type=event_type)


@router.get("/api/mission/telemetry/history")
def get_telemetry_history(
    limit: int = 300,
    since_epoch: Optional[float] = None,
):
    """Query historical telemetry (within 5-minute sliding retention)."""
    actual_limit = getattr(limit, "default", limit)
    return storage.get_telemetry_history(limit=actual_limit, since_epoch=since_epoch)


@router.post("/api/mission/session/reset", status_code=status.HTTP_200_OK)
def reset_session():
    """
    Explicit demo session reset.
    Clears current session telemetry, events, and commands from SQLite,
    clears in-memory command tracking, and resets mission mode and sensor state.
    Preserves active gateway and device connection states so live exhibition
    hardware is not falsely marked disconnected.
    Synchronized against concurrent telemetry ingestion and command dispatch.
    """
    with session_lock:
        storage.reset_session()
        command_tracker.clear()
        state = _dashboard_state(mission_state.reset(preserve_connections=True))
    dashboard_broadcaster.broadcast_sync({
        "type": "state_snapshot",
        "data": state,
    })
    return {
        "status": "session_reset",
        "message": "Demo session data cleared. Device and sensor state are awaiting fresh telemetry.",
        "mission_state": state,
    }


@router.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """Live WebSocket feed broadcasting telemetry, state transitions, and command updates."""
    await dashboard_broadcaster.connect(websocket)
    try:
        # Send initial snapshot immediately upon connection
        await websocket.send_json({
            "type": "state_snapshot",
            "data": _dashboard_state(mission_state.snapshot()),
        })
        while True:
            # Await client pings or messages to maintain connection
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await dashboard_broadcaster.disconnect(websocket)
    except Exception:
        await dashboard_broadcaster.disconnect(websocket)
