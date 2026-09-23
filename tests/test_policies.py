import inspect

import pytest

from bench.run import run_episode
from bench.scenarios import SCENARIOS
from replan.clock import VirtualClock
from replan.policies import CancelAllPolicy, NaivePolicy, RePlanPolicy
from replan.runtime import Runtime
from replan.schemas import ExecutionPlan, PlanTask, Proposal
from replan.tools.smarthome import (
    DEVICE_STATE,
    set_temperature,
    start_appliance,
)


PUBLIC_METHODS = (
    "on_partial",
    "on_final",
    "on_proposal",
    "apply_proposal_and_dispatch",
    "tick",
    "checkpoint",
    "restore",
    "pause",
    "resume",
)


@pytest.fixture(autouse=True)
def empty_device_state():
    DEVICE_STATE["temperatures"].clear()
    DEVICE_STATE["appliances"].clear()
    yield
    DEVICE_STATE["temperatures"].clear()
    DEVICE_STATE["appliances"].clear()


def _proposal_from_calls(calls):
    patch = {"slots": {}, "constraints": {}}
    for call in calls:
        args = call["args"]
        if call["tool"] == "set_temperature":
            patch["slots"]["room"] = args["room"]
            patch["constraints"]["temperature"] = args["degrees"]
        elif call["tool"] == "start_appliance":
            patch["slots"]["appliance"] = args["name"]
            patch["constraints"]["mode"] = args["mode"]
    return Proposal(patch=patch)


def _build_plan(state):
    tasks = {
        "set_temperature": PlanTask(
            id="set_temperature",
            tool="set_temperature",
            arg_spec={
                "room": {"$ref": "slots.room"},
                "degrees": {"$ref": "constraints.temperature"},
            },
        )
    }
    if state.slots.get("appliance"):
        tasks["start_appliance"] = PlanTask(
            id="start_appliance",
            tool="start_appliance",
            arg_spec={
                "name": {"$ref": "slots.appliance"},
                "mode": {"$ref": "constraints.mode"},
            },
        )
    return ExecutionPlan(id=f"plan-v{state.version}", tasks=tasks)


async def _run_late_result_episode(policy_class, seed=0):
    scenario = SCENARIOS["smarthome_pivot"](0.6)
    clock = VirtualClock()

    async def temperature_tool(args, idem):
        await clock.sleep(1.0 if args["room"] == "bedroom" else 0.1)
        return await set_temperature(args, idem)

    async def appliance_tool(args, idem):
        await clock.sleep(0.2)
        return await start_appliance(args, idem)

    tools = {
        "set_temperature": temperature_tool,
        "start_appliance": appliance_tool,
    }
    policy = policy_class(clock=clock, seed=seed, tools=tools)
    policy.build_plan = _build_plan

    policy.on_proposal(_proposal_from_calls(scenario["initial"]["tool_calls"]))
    initial_plan = _build_plan(policy.store.current)
    policy.plan = initial_plan
    for task in initial_plan.tasks.values():
        policy.executor.dispatch(task, initial_plan)

    pivot = _proposal_from_calls(scenario["interruption"]["tool_calls"])
    await policy.apply_proposal_and_dispatch(pivot)
    return policy


@pytest.mark.parametrize("policy_class", [NaivePolicy, CancelAllPolicy, RePlanPolicy])
def test_policies_expose_runtime_interface(policy_class):
    for name in PUBLIC_METHODS:
        assert inspect.signature(getattr(policy_class, name)) == inspect.signature(
            getattr(Runtime, name)
        )


@pytest.mark.parametrize("policy_class", [NaivePolicy, CancelAllPolicy, RePlanPolicy])
@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_all_policies_run_every_scenario(policy_class, scenario_name):
    policy_name = {
        NaivePolicy: "naive",
        CancelAllPolicy: "cancel_all",
        RePlanPolicy: "replan",
    }[policy_class]
    row = run_episode(scenario_name, 0.6, "fast", "none", 0, policy_name)

    assert row["replay_ok"] is True
    assert row["trace_coverage"] == 1.0
    assert row["dangling_effects"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", range(8))
async def test_naive_commits_a_stale_result_in_every_late_result_episode(seed):
    policy = await _run_late_result_episode(NaivePolicy, seed)

    assert policy.metrics.stale_commits >= 1
    assert policy.metrics.wrong_actions >= 1
    assert policy.understanding["room"] == "bedroom"
    assert policy.understanding["degrees"] == 18
    assert DEVICE_STATE["temperatures"]["bedroom"] == 18


@pytest.mark.asyncio
async def test_cancel_all_is_correct_but_replan_reuses_unaffected_work():
    cancel_all = await _run_late_result_episode(CancelAllPolicy)
    cancel_calls = cancel_all.metrics.tool_calls
    assert "bedroom" not in DEVICE_STATE["temperatures"]

    DEVICE_STATE["temperatures"].clear()
    DEVICE_STATE["appliances"].clear()
    replan = await _run_late_result_episode(RePlanPolicy)

    assert "bedroom" not in DEVICE_STATE["temperatures"]
    assert cancel_calls > replan.metrics.tool_calls
    assert replan.metrics.wrong_actions == 0
