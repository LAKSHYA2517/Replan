"""Contract-level acceptance tests derived from the RePlan playbook."""

import asyncio
from random import Random

import pytest

from replan.agents.proposals import extract_proposal
from replan.clock import VirtualClock
from replan.commit import CommitGate
from replan.depgraph import fingerprint
from replan.executor import BudgetGovernor, Executor, SpeculationRefused
from replan.recorder import Recorder
from replan.reconcile import reconcile
from replan.replay import replay, verify
from replan.runtime import Policy, Runtime
from replan.schemas import (
    EventType,
    ExecutionPlan,
    PlanTask,
    Proposal,
    SessionState,
    TaskStatus,
    ToolResult,
    Verdict,
)
from replan.state import StateStore
from replan.tools.vision import analyze_image
from replan.tools.chaos import ChaosProxy


SEED = 2026


def _system(initial=None):
    clock = VirtualClock()
    store = StateStore(initial or SessionState())
    recorder = Recorder(clock, store)
    return clock, store, recorder, CommitGate(store, recorder)


def _task(task_id="search", tool="search_hotels", path="slots.locality"):
    return PlanTask(
        id=task_id,
        tool=tool,
        arg_spec={"value": {"$ref": path}},
    )


def test_01_noop_patch_does_not_create_a_state_version():
    """Applying values already committed leaves version and chain hash unchanged."""
    store = StateStore(
        SessionState(slots={"locality": "Juhu"}, constraints={"budget": 5000})
    )
    before = store.current.model_dump_json()
    before_hash = store.chain_hash()

    state, changed = store.apply(
        {"slots": {"locality": "Juhu"}, "constraints": {"budget": 5000}}
    )

    assert changed == set()
    assert state.version == 0
    assert state.model_dump_json() == before
    assert store.chain_hash() == before_hash


def test_02_restore_appends_history_instead_of_truncating_it():
    """Restoring a checkpoint creates a new version with the checkpoint's values."""
    store = StateStore(SessionState(slots={"locality": "Juhu"}))
    store.checkpoint("chosen")
    store.apply({"slots": {"locality": "Bandra"}})
    changed_hash = store.chain_hash()

    restored = store.restore("chosen")

    assert restored.version == 2
    assert restored.slots == {"locality": "Juhu"}
    assert store.at(1).slots == {"locality": "Bandra"}
    assert store.chain_hash() != changed_hash


def test_03_late_changed_dependency_is_stale_and_state_is_unchanged():
    """A v1 result arriving after its dependency changes is STALE and cannot mutate state."""
    _, store, recorder, gate = _system(SessionState(slots={"locality": "Juhu"}))
    task = _task()
    task.dispatch_fp = fingerprint(task, store.current)
    task.status = TaskStatus.RUNNING
    plan = ExecutionPlan(id="plan-v1", tasks={task.id: task})
    store.apply({"slots": {"locality": "Bandra"}})
    before = store.current.model_dump_json()
    before_hash = store.chain_hash()

    verdict = gate.submit(
        ToolResult(
            call_id="call-1",
            task_id=task.id,
            ok=True,
            payload={"hotels": ["old result"]},
            dispatch_fp=task.dispatch_fp,
        ),
        plan,
    )

    assert verdict is Verdict.STALE
    assert store.current.model_dump_json() == before
    assert store.chain_hash() == before_hash
    assert recorder.events[-1].type is EventType.VERDICT
    assert recorder.events[-1].payload["verdict"] == Verdict.STALE.value


def test_04_reconcile_invalidates_only_tasks_with_changed_dependencies():
    """Changing locality invalidates locality work while unrelated work is adopted."""
    old_state = SessionState(slots={"locality": "Juhu", "member": "member-7"})
    search = _task()
    loyalty = _task("loyalty", "loyalty_status", "slots.member")
    for call_id, task in enumerate((search, loyalty), start=1):
        task.status = TaskStatus.RUNNING
        task.call_id = f"call-{call_id}"
        task.dispatch_fp = fingerprint(task, old_state)
    new_state = old_state.model_copy(deep=True)
    new_state.version = 1
    new_state.slots["locality"] = "Bandra"
    next_search = _task()
    next_loyalty = _task("loyalty", "loyalty_status", "slots.member")

    reconcile(
        ExecutionPlan(id="old", tasks={search.id: search, loyalty.id: loyalty}),
        ExecutionPlan(
            id="new", tasks={next_search.id: next_search, next_loyalty.id: next_loyalty}
        ),
        new_state,
        {},
    )

    assert search.status is TaskStatus.INVALIDATED
    assert next_search.status is TaskStatus.PENDING
    assert next_loyalty.status is TaskStatus.RUNNING
    assert next_loyalty.call_id == loyalty.call_id


def test_05_equal_fingerprint_adopts_inflight_work_across_plans():
    """Equivalent work in a new plan adopts the running call instead of restarting it."""
    state = SessionState(slots={"locality": "Juhu"})
    old = _task()
    old.status = TaskStatus.RUNNING
    old.call_id = "call-7"
    old.dispatch_fp = fingerprint(old, state)
    new = _task()

    reconcile(
        ExecutionPlan(id="old", tasks={old.id: old}),
        ExecutionPlan(id="new", tasks={new.id: new}),
        state,
        {},
    )

    assert new.status is TaskStatus.RUNNING
    assert new.call_id == "call-7"
    assert new.dispatch_fp == old.dispatch_fp
    assert old.status is TaskStatus.DONE


def test_06_pivot_back_reuses_committed_fingerprint_before_adoption():
    """Returning to a prior intent reuses its committed result immediately."""
    store = StateStore(SessionState(slots={"locality": "Juhu"}))
    cached_task = _task()
    cached_fp = fingerprint(cached_task, store.current)
    store.apply({"slots": {"locality": "Bandra"}})
    store.apply({"slots": {"locality": "Juhu"}})
    donor = _task()
    donor.status = TaskStatus.RUNNING
    donor.call_id = "redundant-call"
    donor.dispatch_fp = cached_fp
    returned = _task()

    reconcile(
        ExecutionPlan(id="old", tasks={donor.id: donor}),
        ExecutionPlan(id="returned", tasks={returned.id: returned}),
        store.current,
        {cached_fp: {"hotels": ["cached"]}},
    )

    assert returned.status is TaskStatus.DONE
    assert returned.dispatch_fp == cached_fp
    assert returned.call_id is None


def test_07_second_delivery_of_same_call_is_duplicate():
    """A repeated call id is classified DUPLICATE and produces no second commit."""
    _, store, recorder, gate = _system(SessionState(slots={"locality": "Juhu"}))
    task = _task()
    task.status = TaskStatus.RUNNING
    task.dispatch_fp = fingerprint(task, store.current)
    plan = ExecutionPlan(id="plan", tasks={task.id: task})
    result = ToolResult(
        call_id="call-duplicate",
        task_id=task.id,
        ok=True,
        payload={"hotels": ["Sea View"]},
        dispatch_fp=task.dispatch_fp,
    )

    assert gate.submit(result, plan) is Verdict.COMMIT
    assert gate.submit(result, plan) is Verdict.DUPLICATE
    assert task.status is TaskStatus.DONE
    verdicts = [
        event.payload["verdict"]
        for event in recorder.events
        if event.type is EventType.VERDICT
    ]
    assert verdicts == [Verdict.COMMIT.value, Verdict.DUPLICATE.value]


@pytest.mark.asyncio
async def test_08_pause_freezes_work_and_resume_commits_valid_results():
    """Pause freezes running work after checkpointing; resume releases valid results."""
    clock = VirtualClock()

    async def search(args, idem):
        await clock.sleep(0.5)
        return {"hotels": [args["value"]]}

    runtime = Runtime(
        clock,
        seed=SEED,
        policy=Policy.REPLAN,
        tools={"search_hotels": search},
    )
    runtime.on_proposal(Proposal(patch={"slots": {"locality": "Juhu"}}))
    task = _task()
    plan = ExecutionPlan(id="plan", tasks={task.id: task})
    runtime.plan = plan
    runtime.executor.dispatch(task, plan)

    runtime.pause()
    paused_status = task.status
    if paused_status is not TaskStatus.FROZEN:
        runtime.executor.cancel(task)
        await clock.run_until_idle()
    assert paused_status is TaskStatus.FROZEN
    await clock.run_until_idle()
    assert runtime.tick() == []
    runtime.resume()

    assert runtime.tick() == [Verdict.COMMIT]
    assert task.status is TaskStatus.DONE
    control_events = [
        event.type
        for event in runtime.recorder.events
        if event.type in (EventType.CHECKPOINT, EventType.PAUSE, EventType.RESUME)
    ]
    assert control_events == [EventType.CHECKPOINT, EventType.PAUSE, EventType.RESUME]


def test_09_cancelled_task_result_cannot_commit():
    """A result for a CANCELLED task receives CANCELLED and changes no committed state."""
    _, store, recorder, gate = _system(SessionState(slots={"locality": "Juhu"}))
    task = _task()
    task.status = TaskStatus.CANCELLED
    task.dispatch_fp = fingerprint(task, store.current)
    plan = ExecutionPlan(id="plan", tasks={task.id: task})
    before = store.chain_hash()

    verdict = gate.submit(
        ToolResult(
            call_id="cancelled-call",
            task_id=task.id,
            ok=True,
            payload={"hotels": ["must not commit"]},
            dispatch_fp=task.dispatch_fp,
        ),
        plan,
    )

    assert verdict is Verdict.CANCELLED
    assert store.chain_hash() == before
    assert task.status is TaskStatus.CANCELLED
    assert recorder.events[-1].payload["verdict"] == Verdict.CANCELLED.value


@pytest.mark.asyncio
async def test_14_proposal_validator_rejects_paths_outside_state_allowlist():
    """LLM output touching an unknown state section becomes an empty safe proposal."""
    class FixedResponse:
        async def get_or_call(self, prompt, call):
            return '{"patch":{"secrets":{"token":"x"}},"confidence":1.0}'

    async def llm(prompt):
        return "unused"

    proposal = await extract_proposal(
        "hello there", SessionState(), llm, FixedResponse()
    )

    assert proposal.kind == "state_patch"
    assert proposal.patch == {}
    assert set(proposal.patch) <= {"slots", "constraints", "policy"}


def test_15_runtime_checkpoint_restore_is_logged_and_append_only():
    """Restoring a named checkpoint appends a version and records both control events."""
    runtime = Runtime(
        VirtualClock(), seed=SEED, policy=Policy.REPLAN, tools={}
    )
    runtime.on_proposal(Proposal(patch={"constraints": {"budget": 5000}}))
    assert runtime.checkpoint("before-change") == 1
    runtime.on_proposal(Proposal(patch={"constraints": {"budget": 3000}}))

    restored = runtime.restore("before-change")

    assert restored.version == 3
    assert restored.constraints["budget"] == 5000
    assert runtime.store.at(2).constraints["budget"] == 3000
    controls = [
        event.type
        for event in runtime.recorder.events
        if event.type in (EventType.CHECKPOINT, EventType.RESTORE)
    ]
    assert controls == [EventType.CHECKPOINT, EventType.RESTORE]


def test_10_irreversible_tool_is_never_dispatched_speculatively():
    """An irreversible tool marked speculative is refused before any dispatch event."""
    clock, store, recorder, gate = _system()

    async def confirm(args, idem):
        return {"confirmed": True}

    executor = Executor(
        {"confirm_room": confirm},
        gate,
        store,
        clock,
        BudgetGovernor(5, 10.0, 0.0),
        recorder,
    )
    task = PlanTask(id="confirm", tool="confirm_room", speculative=True)
    plan = ExecutionPlan(id="plan", tasks={task.id: task})
    before = store.chain_hash()

    with pytest.raises(SpeculationRefused):
        executor.dispatch(task, plan)

    assert task.status is TaskStatus.PENDING
    assert store.chain_hash() == before
    assert not any(event.type is EventType.TASK_DISPATCH for event in recorder.events)


@pytest.mark.asyncio
async def test_11_landed_reversible_effect_is_compensated_when_removed():
    """A committed reversible effect removed by replanning dispatches its compensator."""
    clock = VirtualClock()
    released = []

    async def reserve(args, idem):
        return {"reservation_id": "res-0001"}

    async def release(args, idem):
        released.append(args["reservation_id"])
        return {"released": True}

    runtime = Runtime(
        clock,
        seed=SEED,
        policy=Policy.REPLAN,
        tools={"reserve_room": reserve, "release_room": release},
    )
    include_reservation = True

    def build_plan(state):
        tasks = {}
        if include_reservation:
            tasks["reserve"] = PlanTask(
                id="reserve",
                tool="reserve_room",
                arg_spec={"hotel": {"$ref": "slots.hotel"}},
            )
        return ExecutionPlan(id=f"plan-v{state.version}", tasks=tasks)

    runtime.build_plan = build_plan
    await runtime.apply_proposal_and_dispatch(
        Proposal(patch={"slots": {"hotel": "Sea View"}})
    )
    include_reservation = False
    await runtime.apply_proposal_and_dispatch(
        Proposal(patch={"policy": {"booking_enabled": False}})
    )

    assert released == ["res-0001"]
    assert any(event.type is EventType.COMPENSATING for event in runtime.recorder.events)
    assert runtime.metrics.dangling_effects == 0


@pytest.mark.asyncio
async def test_12_frozen_task_withholds_its_result_from_the_gate():
    """A result landing while its task is FROZEN is parked with no verdict event."""
    clock, store, recorder, gate = _system(SessionState(slots={"locality": "Juhu"}))

    async def search(args, idem):
        await clock.sleep(0.5)
        return {"hotels": [args["value"]]}

    executor = Executor(
        {"search_hotels": search},
        gate,
        store,
        clock,
        BudgetGovernor(5, 10.0, 0.0),
        recorder,
    )
    task = _task()
    plan = ExecutionPlan(id="plan", tasks={task.id: task})
    executor.dispatch(task, plan)
    executor.freeze({task.id}, plan)
    await clock.run_until_idle()

    assert executor.drain(plan) == []
    assert task.status is TaskStatus.FROZEN
    assert not any(event.type is EventType.VERDICT for event in recorder.events)


@pytest.mark.asyncio
async def test_13_thaw_releases_valid_parked_result_exactly_once():
    """Thawing a frozen task releases its parked valid result to a single COMMIT."""
    clock, store, recorder, gate = _system(SessionState(slots={"locality": "Juhu"}))

    async def search(args, idem):
        await clock.sleep(0.5)
        return {"hotels": [args["value"]]}

    executor = Executor(
        {"search_hotels": search},
        gate,
        store,
        clock,
        BudgetGovernor(5, 10.0, 0.0),
        recorder,
    )
    task = _task()
    plan = ExecutionPlan(id="plan", tasks={task.id: task})
    executor.dispatch(task, plan)
    executor.freeze({task.id}, plan)
    await clock.run_until_idle()
    executor.drain(plan)
    executor.thaw({task.id}, plan)
    executor.release_frozen(plan)

    assert executor.drain(plan) == [Verdict.COMMIT]
    assert task.status is TaskStatus.DONE
    verdict_events = [event for event in recorder.events if event.type is EventType.VERDICT]
    assert [event.payload["verdict"] for event in verdict_events] == [Verdict.COMMIT.value]


def test_16_replay_reproduces_the_recorded_state_chain_hash():
    """Replaying recorded external inputs with the same seed reproduces state history."""
    async def record():
        runtime = Runtime(
            VirtualClock(), seed=SEED, policy=Policy.REPLAN, tools={}
        )
        await runtime.apply_proposal_and_dispatch(
            Proposal(
                patch={
                    "slots": {"locality": "Juhu"},
                    "constraints": {"budget": 5000},
                }
            )
        )
        return runtime

    original = asyncio.run(record())
    reproduced = replay(original.recorder.events, SEED)

    assert verify(original.recorder.events, SEED)
    assert reproduced.store.chain_hash() == original.store.chain_hash()
    assert reproduced.store.current.model_dump() == original.store.current.model_dump()


@pytest.mark.asyncio
async def test_17_image_budget_patch_invalidates_only_budget_branch():
    """A validated image budget change preserves in-flight locality-only work."""
    store = StateStore(
        SessionState(slots={"locality": "Juhu"}, constraints={"budget": 8000})
    )
    budget = _task("budget", "search_hotels", "constraints.budget")
    locality = _task("locality", "availability", "slots.locality")
    for index, task in enumerate((budget, locality), start=1):
        task.status = TaskStatus.RUNNING
        task.call_id = f"call-{index}"
        task.dispatch_fp = fingerprint(task, store.current)
    old_plan = ExecutionPlan(
        id="old", tasks={budget.id: budget, locality.id: locality}
    )
    proposal = Proposal.model_validate(
        await analyze_image(
            {
                "image": "tests/fixtures/competitor_listing.jpg",
                "currency": "INR",
            },
            "vision",
        )
    )
    new_state, changed = store.apply(proposal.patch)
    next_budget = _task("budget", "search_hotels", "constraints.budget")
    next_locality = _task("locality", "availability", "slots.locality")

    reconcile(
        old_plan,
        ExecutionPlan(
            id="new",
            tasks={next_budget.id: next_budget, next_locality.id: next_locality},
        ),
        new_state,
        {},
    )

    assert changed == {"constraints.budget"}
    assert budget.status is TaskStatus.INVALIDATED
    assert next_budget.status is TaskStatus.PENDING
    assert next_locality.status is TaskStatus.RUNNING
    assert next_locality.call_id == locality.call_id


def test_18_seeded_severe_chaos_preserves_safety_and_replay():
    """A severe-chaos episode has no unsafe commit/effect and remains replayable."""
    async def episode():
        clock = VirtualClock()

        async def inner(args, idem):
            return {"hotels": [args["value"]]}

        inner.__name__ = "search_hotels"
        inner.base_latency = 0.1
        proxy = ChaosProxy(inner, clock, Random(SEED), [], "severe")
        runtime = Runtime(
            clock,
            seed=SEED,
            policy=Policy.REPLAN,
            tools={"search_hotels": proxy},
        )
        runtime.build_plan = lambda state: ExecutionPlan(
            id=f"plan-v{state.version}",
            tasks={"search": _task()},
        )
        await runtime.apply_proposal_and_dispatch(
            Proposal(patch={"slots": {"locality": "Juhu"}})
        )
        return runtime

    runtime = asyncio.run(episode())

    assert runtime.metrics.stale_commits == 0
    assert runtime.metrics.wrong_actions == 0
    assert runtime.metrics.dangling_effects == 0
    assert runtime.recorder.verify_chain()
    assert verify(runtime.recorder.events, SEED)


@pytest.mark.asyncio
async def test_19_trace_is_gapless_hash_chained_and_causally_joinable():
    """State, dispatch and verdict events form a gapless verifiable causal record."""
    clock = VirtualClock()

    async def search(args, idem):
        return {"hotels": [args["value"]]}

    runtime = Runtime(
        clock,
        seed=SEED,
        policy=Policy.REPLAN,
        tools={"search_hotels": search},
    )
    runtime.build_plan = lambda state: ExecutionPlan(
        id=f"plan-v{state.version}", tasks={"search": _task()}
    )
    await runtime.apply_proposal_and_dispatch(
        Proposal(patch={"slots": {"locality": "Juhu"}})
    )

    events = runtime.recorder.events
    assert runtime.recorder.verify_chain()
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    state_event = next(event for event in events if event.type is EventType.STATE_PATCH)
    dispatch = next(event for event in events if event.type is EventType.TASK_DISPATCH)
    verdict = next(event for event in events if event.type is EventType.VERDICT)
    assert state_event.state_version == runtime.store.current.version
    assert state_event.payload["chain_hash"] == runtime.store.chain_hash()
    assert verdict.payload["call_id"] == dispatch.payload["call_id"]
    assert verdict.payload["task_id"] == dispatch.payload["task_id"]


@pytest.mark.asyncio
async def test_20_speculation_budget_refuses_excess_concurrent_work():
    """The speculation governor refuses excess work and records the refusal reason."""
    clock, store, recorder, gate = _system(SessionState(slots={"locality": "Juhu"}))

    async def search(args, idem):
        await clock.sleep(1.0)
        return {"hotels": []}

    executor = Executor(
        {"search_hotels": search},
        gate,
        store,
        clock,
        BudgetGovernor(max_concurrent=1, max_cost_per_turn=10.0, hit_rate_floor=0.0),
        recorder,
    )
    first = _task("first")
    first.speculative = True
    second = _task("second")
    second.speculative = True
    plan = ExecutionPlan(id="plan", tasks={first.id: first, second.id: second})

    assert executor.dispatch(first, plan) == "call-1"
    assert executor.dispatch(second, plan) is None
    assert first.status is TaskStatus.RUNNING
    assert second.status is TaskStatus.PENDING
    refusal = next(event for event in recorder.events if event.type is EventType.SPEC_REFUSED)
    assert refusal.payload["task_id"] == second.id
    assert "max_concurrent" in refusal.payload["reason"]
    executor.cancel(first)
    await clock.run_until_idle()
