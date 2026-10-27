from app.communication.gateway_contract import CommandName, CommandRequest
from app.communication.gateway_simulator import GatewaySimulator


def test_simulated_status_and_mode_commands_do_not_actuate_hardware():
    simulator = GatewaySimulator()
    for command in (CommandName.GET_STATUS, CommandName.SET_STANDBY, CommandName.SET_ACTIVE):
        response = simulator.handle_command(CommandRequest(command_id=command.value, command=command))
        assert response.accepted is True
    assert simulator.mode.value == "ACTIVE"
    assert "gate_state" not in simulator.get_lander_status().model_dump()


def test_retired_movement_commands_are_rejected_by_contract():
    try:
        CommandRequest(command_id="old", command="OPEN_GATE")
    except Exception:
        pass
    else:
        raise AssertionError("retired actuator command must not validate")
