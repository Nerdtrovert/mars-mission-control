import pytest
from pydantic import ValidationError

from app.communication.gateway_contract import (
    CommandName, CommandRequest, ConnectionState, LanderStatusResponse, OperatingMode,
)


def test_lander_status_contract_has_no_retired_actuator_fields():
    status = LanderStatusResponse(
        gateway_state=ConnectionState.ONLINE, device_state=ConnectionState.ONLINE,
        mode=OperatingMode.ACTIVE, bmp280_ok=True, dht11_ok=True,
    )
    assert status.model_dump()["mode"] == OperatingMode.ACTIVE
    assert "gate_state" not in status.model_dump()
    with pytest.raises(ValidationError):
        LanderStatusResponse(gateway_state="ONLINE", device_state="ONLINE", gate_state="OPEN")


def test_command_contract_only_accepts_status_and_operating_modes():
    assert {c.value for c in CommandName} == {"GET_STATUS", "SET_ACTIVE", "SET_STANDBY"}
    assert CommandRequest(command_id="1", command="GET_STATUS").command == CommandName.GET_STATUS
    with pytest.raises(ValidationError):
        CommandRequest(command_id="2", command="CLOSE_GATE")
