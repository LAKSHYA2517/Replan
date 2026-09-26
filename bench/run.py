"""Deterministic full-factorial RePlan benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path
from random import Random

from bench.latency import LATENCY_PROFILES
from bench.scenarios import SCENARIOS
from replan.clock import VirtualClock
from replan.policies import CancelAllPolicy, NaivePolicy, RePlanPolicy
from replan.replay import verify
from replan.schemas import Effect, EventType, ExecutionPlan, PlanTask, Proposal, ToolResult
from replan.tools.chaos import PROFILES, ChaosProxy
from replan.tools.registry import TOOL_SPECS


OFFSETS = (0.3, 0.6, 0.9, 1.2, 1.8, 2.4)
SEEDS = range(8)
POLICIES = {
    "naive": NaivePolicy,
    "cancel_all": CancelAllPolicy,
    "replan": RePlanPolicy,
}
RESULTS_PATH = Path(__file__).with_name("results.jsonl")

_ARG_PATHS = {
    "locality": "slots.locality",
    "city": "slots.locality",
    "member": "slots.member",
    "hotel": "slots.hotel",
    "room": "slots.room",
    "name": "slots.appliance",
    "destination": "slots.destination",
    "budget": "constraints.budget",
    "breakfast": "constraints.breakfast",
    "degrees": "constraints.temperature",
    "mode": "constraints.mode",
    "booking_enabled": "policy.booking_enabled",
}


class _DuplicateSink:
    def __init__(self) -> None:
        self.runtime = None

    async def __call__(self, idem: str, payload: dict) -> None:
        dispatch = next(
            event
            for event in reversed(self.runtime.recorder.events)
            if event.type is EventType.TASK_DISPATCH and event.payload["idem"] == idem
        )
        self.runtime.executor.results.put_nowait(
            ToolResult(
                call_id=dispatch.payload["call_id"],
                task_id=dispatch.payload["task_id"],
                ok=True,
                payload=payload,
                dispatch_fp=dispatch.payload["dispatch_fp"],
            )
        )
        if TOOL_SPECS[dispatch.payload["tool"]]["compensator"] is None:
            self.runtime.tick()


def _arg_spec(args: dict, state) -> dict:
    spec = {}
    for key, value in args.items():
        path = _ARG_PATHS.get(key)
        spec[key] = {"$ref": path} if path and state.read(path) == value else value
    return spec


def _plan(state, calls: dict[str, dict]) -> ExecutionPlan:
    tasks = {}
    for name, call in calls.items():
        effect = TOOL_SPECS[name]["effect"]
        tasks[name] = PlanTask(
            id=name,
            tool=name,
            arg_spec=_arg_spec(call["args"], state),
            speculative=effect is not Effect.IRREVERSIBLE,
        )
    return ExecutionPlan(id=f"plan-v{state.version}", tasks=tasks)


def _make_tools(clock, rng, profile_name, latency_name, holder, sink):
    tools = {}
    for name in TOOL_SPECS:
        latency = LATENCY_PROFILES[latency_name][name]

        async def inner(args, idem, tool_name=name):
            payload = {
                "tool": tool_name,
                "args": args,
                "value": rng.randrange(1_000_000),
            }

            if TOOL_SPECS[tool_name]["compensator"] is None:
                async def drain_after_delivery():
                    await clock.sleep(0.0)
                    holder["runtime"].tick()

                asyncio.create_task(drain_after_delivery())
            return payload

        inner.__name__ = name
        inner.base_latency = latency
        tools[name] = ChaosProxy(inner, clock, rng, sink, profile_name)
    return tools


async def _drive_episode(scenario_name, offset, latency_name, chaos_name, seed, policy_name):
    clock = VirtualClock()
    rng = Random(seed)
    holder = {}
    sink = _DuplicateSink()
    tools = _make_tools(clock, rng, chaos_name, latency_name, holder, sink)
    runtime = POLICIES[policy_name](clock=clock, seed=seed, tools=tools, chaos=chaos_name)
    holder["runtime"] = runtime
    sink.runtime = runtime

    scenario = SCENARIOS[scenario_name](offset)
    desired = {call["tool"]: call for call in scenario["initial"]["tool_calls"]}
    runtime.build_plan = lambda state: _plan(state, desired)
    runtime.on_proposal(Proposal(patch=scenario["initial"]["patch"]))
    initial_plan = runtime.build_plan(runtime.store.current)
    runtime.plan = initial_plan
    for task in initial_plan.tasks.values():
        runtime.executor.dispatch(task, initial_plan)

    late = scenario["late_result"]
    late_task = initial_plan.tasks[late["tool"]]

    async def inject_late_result():
        await clock.sleep(late["at"])
        runtime.executor.results.put_nowait(
            ToolResult(
                call_id=f"late-{scenario_name}",
                task_id=late_task.id,
                ok=True,
                payload=dict(late["args"]),
                dispatch_fp=late_task.dispatch_fp,
            )
        )
        runtime.tick()

    async def interrupt():
        await clock.sleep(offset)
        desired.update(
            {call["tool"]: call for call in scenario["interruption"]["tool_calls"]}
        )
        await runtime.apply_proposal_and_dispatch(
            Proposal(patch=scenario["interruption"]["patch"])
        )

    interruption = asyncio.create_task(interrupt())
    late_delivery = asyncio.create_task(inject_late_result())
    await clock.run_until_idle()
    await interruption
    await late_delivery
    runtime.tick()
    return runtime


def run_episode(scenario, offset, latency_profile, chaos, seed, policy) -> dict:
    runtime = asyncio.run(
        _drive_episode(scenario, offset, latency_profile, chaos, seed, policy)
    )
    metrics = runtime.metrics
    replay_ok = verify(runtime.recorder.events, seed)
    return {
        "scenario": scenario,
        "interrupt_offset": offset,
        "latency_profile": latency_profile,
        "chaos": chaos,
        "seed": seed,
        "policy": policy,
        "stale_commits": metrics.stale_commits,
        "wrong_actions": metrics.wrong_actions,
        "dangling_effects": metrics.dangling_effects,
        "reuse_ratio": metrics.reuse_ratio,
        "tool_calls": metrics.tool_calls,
        "wasted_tool_s": metrics.wasted_tool_seconds,
        "spec_hit_rate": metrics.speculation_hit_rate,
        "spec_waste_ratio": 1.0 - metrics.speculation_hit_rate,
        "freeze_lead_s": metrics.freeze_lead_time,
        "cancel_latency_s": metrics.cancellation_latency,
        "ttfvr_s": metrics.time_to_first_valid_result,
        "trace_coverage": metrics.trace_coverage,
        "replay_ok": replay_ok,
    }


def run_sweep(
    scenarios=SCENARIOS,
    offsets=OFFSETS,
    latency_profiles=LATENCY_PROFILES,
    chaos_profiles=PROFILES,
    seeds=SEEDS,
    policies=POLICIES,
    output=RESULTS_PATH,
) -> list[dict]:
    coordinates = [
        (scenario, offset, latency, chaos, seed, policy)
        for scenario in scenarios
        for offset in offsets
        for latency in latency_profiles
        for chaos in chaos_profiles
        for seed in seeds
        for policy in policies
    ]
    rows = []
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for index, coordinate in enumerate(coordinates, start=1):
            row = run_episode(*coordinate)
            rows.append(row)
            stream.write(json.dumps(row, sort_keys=True) + "\n")
            if index % 500 == 0 or index == len(coordinates):
                print(f"completed {index}/{len(coordinates)} episodes", flush=True)
    return rows


def print_summary(rows: list[dict]) -> None:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["policy"]].append(row)
    print("\npolicy      episodes  wrong_actions  tool_calls  reuse_ratio  replay_ok")
    for policy in POLICIES:
        values = grouped[policy]
        mean = lambda key: sum(float(row[key] or 0.0) for row in values) / len(values)
        replay_rate = sum(row["replay_ok"] for row in values) / len(values)
        print(
            f"{policy:<11} {len(values):>8}  {mean('wrong_actions'):>13.3f}  "
            f"{mean('tool_calls'):>10.3f}  {mean('reuse_ratio'):>11.3f}  {replay_rate:>9.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RESULTS_PATH)
    args = parser.parse_args()
    rows = run_sweep(output=args.output)
    print_summary(rows)


if __name__ == "__main__":
    main()
