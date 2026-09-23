import pytest

from bench.scenarios import SCENARIOS, smarthome_pivot
from replan.schemas import Effect
from replan.tools.registry import TOOL_SPECS
from replan.tools.smarthome import (
    DEVICE_STATE,
    restore_temperature,
    set_temperature,
    start_appliance,
    stop_appliance,
)


@pytest.fixture(autouse=True)
def empty_device_state():
    DEVICE_STATE["temperatures"].clear()
    DEVICE_STATE["appliances"].clear()
    yield
    DEVICE_STATE["temperatures"].clear()
    DEVICE_STATE["appliances"].clear()


@pytest.mark.asyncio
async def test_temperature_state_and_compensation():
    initial = await set_temperature({"room": "bedroom", "degrees": 18}, "set-1")
    changed = await set_temperature({"room": "bedroom", "degrees": 24}, "set-2")

    assert initial == {"room": "bedroom", "degrees": 18, "previous_degrees": None}
    assert changed == {"room": "bedroom", "degrees": 24, "previous_degrees": 18}
    assert DEVICE_STATE["temperatures"] == {"bedroom": 24}

    assert await restore_temperature(changed, "restore-1") == {
        "room": "bedroom",
        "degrees": 18,
        "restored": True,
    }
    assert DEVICE_STATE["temperatures"] == {"bedroom": 18}

    await restore_temperature(initial, "restore-2")
    assert DEVICE_STATE["temperatures"] == {}


@pytest.mark.asyncio
async def test_appliance_state_and_stop_compensator():
    started = await start_appliance({"name": "washer", "mode": "cotton"}, "start")

    assert started == {"name": "washer", "mode": "cotton", "running": True}
    assert DEVICE_STATE["appliances"] == {
        "washer": {"mode": "cotton", "running": True}
    }

    stopped = await stop_appliance(started, "stop")
    assert stopped == {"name": "washer", "running": False, "stopped": True}
    assert DEVICE_STATE["appliances"] == {
        "washer": {"mode": "cotton", "running": False}
    }


@pytest.mark.asyncio
async def test_stopping_absent_appliance_is_safe_and_visible():
    result = await stop_appliance({"name": "washer", "mode": "cotton"}, "stop")

    assert result == {"name": "washer", "running": False, "stopped": False}
    assert DEVICE_STATE["appliances"] == {
        "washer": {"mode": "cotton", "running": False}
    }


@pytest.mark.parametrize("offset", [0.0, 0.3, 1.2, 2.4])
def test_smarthome_pivot_has_configurable_interrupt_and_late_result(offset):
    scenario = smarthome_pivot(offset)

    assert scenario["interruption"]["at"] == offset
    assert scenario["late_result"]["at"] == offset + 0.5
    assert scenario["late_result"]["at"] > scenario["interruption"]["at"]
    assert scenario["late_result"]["tool"] == "set_temperature"
    assert scenario["late_result"]["args"] == {"room": "bedroom", "degrees": 18}


def test_smarthome_pivot_contains_exact_demo_actions():
    scenario = SCENARIOS["smarthome_pivot"](0.6)

    assert scenario["initial"]["utterance"] == (
        "Set the AC in the bedroom to 18 and start the washer on cotton."
    )
    assert scenario["initial"]["tool_calls"] == [
        {"tool": "set_temperature", "args": {"room": "bedroom", "degrees": 18}},
        {"tool": "start_appliance", "args": {"name": "washer", "mode": "cotton"}},
    ]
    assert scenario["interruption"]["utterance"] == (
        "No — the living room, and make it 24."
    )
    assert scenario["interruption"]["tool_calls"] == [
        {"tool": "set_temperature", "args": {"room": "living room", "degrees": 24}}
    ]


def test_smarthome_pivot_rejects_negative_offset():
    with pytest.raises(ValueError, match="non-negative"):
        smarthome_pivot(-0.1)


def test_smarthome_registry_contract():
    assert TOOL_SPECS["set_temperature"]["effect"] is Effect.REVERSIBLE
    assert TOOL_SPECS["set_temperature"]["compensator"] == "restore_temperature"
    assert TOOL_SPECS["start_appliance"]["effect"] is Effect.REVERSIBLE
    assert TOOL_SPECS["start_appliance"]["compensator"] == "stop_appliance"
