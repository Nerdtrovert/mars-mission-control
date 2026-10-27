from app.communication.gateway_contract import CommandName, ConnectionState
from app.mission.command import CommandSafetyViolation, CommandTracker


def test_status_and_mode_commands_have_lifecycle_and_storage():
    tracker = CommandTracker()
    command = tracker.create_command(CommandName.SET_ACTIVE)
    command.mark_sent()
    command.mark_acknowledged(True)
    command.mark_completed()
    tracker.save_command_state(command)
    assert tracker.get_command(command.command_id).status.value == "COMPLETED"


def test_command_requires_online_gateway_and_lander():
    tracker = CommandTracker()
    command = tracker.create_command(CommandName.GET_STATUS)
    try:
        tracker.validate_safety_preconditions(command, ConnectionState.ONLINE, ConnectionState.OFFLINE)
    except CommandSafetyViolation:
        pass
    else:
        raise AssertionError("offline device must reject command")


def test_command_enum_contains_no_actuator_commands():
    assert {item.value for item in CommandName} == {"GET_STATUS", "SET_ACTIVE", "SET_STANDBY"}
