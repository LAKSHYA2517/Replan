import asyncio
from random import Random

import pytest

from replan.clock import VirtualClock
from replan.policies import RePlanPolicy
from replan.replay import verify
from replan.schemas import EventType, ExecutionPlan, PlanTask, Proposal, ToolResult
from replan.tools.chaos import PROFILES, ChaosProxy


class ScriptedRng:
    def __init__(self, draws, uniforms):
        self.draws = iter(draws)
        self.uniforms = iter(uniforms)

    def random(self):
        return next(self.draws)

    def uniform(self, start, end):
        value = next(self.uniforms)
        assert start <= value <= end
        return value


async def _drive(clock, awaitable):
    task = asyncio.create_task(awaitable)
    await clock.run_until_idle()
    return await task


@pytest.mark.asyncio
async def test_stall_jitter_reorder_and_duplicate_use_injected_dependencies():
    clock = VirtualClock()
    sink = []
    calls = []

    async def inner(args, idem):
        calls.append((args, idem))
        return {"call_id": idem, "value": args["value"]}

    inner.base_latency = 0.2
    rng = ScriptedRng(
        draws=[1.0, 0.0, 0.0, 0.0],
        uniforms=[1.5, 1.0, 0.05],
    )
    proxy = ChaosProxy(
        inner,
        clock,
        rng,
        sink,
        {"dup": 1.0, "reorder": 1.0, "fail": 0.0, "stall": 1.0, "jitter": 0.5},
    )

    result = await _drive(clock, proxy({"value": 7}, "call-7"))

    assert result == {"call_id": "call-7", "value": 7}
    assert calls == [({"value": 7}, "call-7")]
    assert sink == [("call-7", result)]
    assert clock.now() == pytest.approx(3.45)


@pytest.mark.asyncio
async def test_failure_waits_on_injected_clock_and_skips_inner():
    clock = VirtualClock()
    called = False

    async def inner(args, idem):
        nonlocal called
        called = True
        return {}

    proxy = ChaosProxy(
        inner,
        clock,
        ScriptedRng(draws=[0.0], uniforms=[0.04]),
        [],
        {"dup": 0.0, "reorder": 0.0, "fail": 1.0, "stall": 0.0, "jitter": 0.0},
    )

    with pytest.raises(RuntimeError, match="chaos-injected"):
        await _drive(clock, proxy({}, "failed-call"))

    assert called is False
    assert clock.now() == pytest.approx(0.04)


@pytest.mark.parametrize("profile", PROFILES)
def test_named_profiles_are_seed_reproducible(profile):
    async def run():
        clock = VirtualClock()
        sink = []

        async def inner(args, idem):
            return {"seeded": args["seeded"]}

        inner.base_latency = 0.1
        proxy = ChaosProxy(inner, clock, Random(19), sink, profile)
        try:
            result = await _drive(clock, proxy({"seeded": True}, "same-id"))
        except RuntimeError as exc:
            result = str(exc)
        return result, sink, clock.now()

    assert asyncio.run(run()) == asyncio.run(run())


class ExecutorDuplicateSink:
    def __init__(self):
        self.runtime = None

    async def __call__(self, idem, payload):
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


async def _severe_episode(seed):
    clock = VirtualClock()
    sink = ExecutorDuplicateSink()

    async def inner(args, idem):
        return {"hotels": [{"name": "Deterministic", "price": args["budget"]}]}

    inner.__name__ = "search_hotels"
    inner.base_latency = 0.01
    proxy = ChaosProxy(inner, clock, Random(seed), sink, "severe")
    runtime = RePlanPolicy(
        clock=clock,
        seed=seed,
        tools={"search_hotels": proxy},
    )
    sink.runtime = runtime
    runtime.build_plan = lambda state: ExecutionPlan(
        id=f"plan-v{state.version}",
        tasks={
            "search": PlanTask(
                id="search",
                tool="search_hotels",
                arg_spec={"budget": {"$ref": "constraints.budget"}},
            )
        },
    )
    await runtime.apply_proposal_and_dispatch(
        Proposal(patch={"constraints": {"budget": 5000 + seed}})
    )
    return runtime


def test_500_severe_chaos_episodes_preserve_safety_and_replay():
    for seed in range(500):
        runtime = asyncio.run(_severe_episode(seed))
        assert runtime.metrics.stale_commits == 0
        assert runtime.metrics.wrong_actions == 0
        assert runtime.metrics.dangling_effects == 0
        assert runtime.recorder.verify_chain()
        assert verify(runtime.recorder.events, seed)
