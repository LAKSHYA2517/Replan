"""Deterministic replay: feed a recorded trace back through a fresh
Runtime and get a byte-identical state history. No network calls, no live
tool or LLM calls — every external effect is played back from the trace.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from replan.clock import VirtualClock
from replan.schemas import Event, EventType, Proposal
from replan.tools.registry import TOOL_SPECS

# The one EventType that unambiguously means "an interruption happened" in
# the current schema. Broaden this set if the team later wants
# TASK_FREEZE (a predicted interruption) shifted too.
INTERRUPTION_EVENT_TYPES = frozenset({EventType.BARGE_IN})


class ReplayCacheMiss(Exception):
    pass


def _index_trace(trace: list[Event]) -> dict[str, dict]:
    """Join TASK_DISPATCH and VERDICT events sharing a call_id into one
    record per idempotency key (what a tool callable actually receives),
    holding the payload/ok/error it produced and the latency it took."""
    dispatches: dict[str, dict] = {}
    for e in trace:
        if e.type == EventType.TASK_DISPATCH:
            dispatches[e.payload["call_id"]] = {
                "idem": e.payload["idem"],
                "t": e.t,
            }

    by_idem: dict[str, dict] = {}
    for e in trace:
        if e.type == EventType.VERDICT:
            dispatch = dispatches.get(e.payload.get("call_id"))
            if dispatch is None:
                continue
            by_idem[dispatch["idem"]] = {
                "ok": e.payload.get("ok", True),
                "payload": e.payload.get("payload", {}),
                "error": e.payload.get("error"),
                "latency": max(0.0, e.t - dispatch["t"]),
            }
    return by_idem


def _make_replaying_tools(clock: VirtualClock, trace: list[Event]) -> dict[str, Callable[[dict, str], Awaitable[dict]]]:
    by_idem = _index_trace(trace)

    async def replay_tool(args: dict, idem: str) -> dict:
        record = by_idem.get(idem)
        if record is None:
            raise ReplayCacheMiss(f"no recorded outcome for idempotency key {idem}")
        await clock.sleep(record["latency"])
        if not record["ok"]:
            raise RuntimeError(record["error"] or "replayed tool failure")
        return record["payload"]

    return {name: replay_tool for name in TOOL_SPECS}


def replay(trace: list[Event], seed: int):
    """Build a fresh Runtime whose tool layer replays trace exactly, then
    feed the trace's STATE_PATCH/CHECKPOINT/RESTORE events (the actual
    external inputs that drove the original run) back through it in
    sequence order. TASK_DISPATCH/VERDICT/etc are outputs, re-derived for
    real by Runtime's own logic — not re-injected.

    Policy defaults to REPLAN (replay()'s own two-arg signature has no room
    for a third parameter, and REPLAN is what every replay-fidelity claim
    in this project is actually about); a trace recorded under a different
    policy is a known limitation, not silently handled.
    """
    from replan.runtime import Policy, Runtime  # lazy: sidesteps any import
    # cycle risk (Runtime never needs to import this leaf module).

    async def _drive() -> "Runtime":
        clock = VirtualClock()
        tools = _make_replaying_tools(clock, trace)
        runtime = Runtime(clock=clock, seed=seed, policy=Policy.REPLAN, tools=tools, chaos="none")
        for event in trace:
            if event.type == EventType.STATE_PATCH:
                proposal = Proposal(kind="state_patch", patch=event.payload["patch"])
                await runtime.apply_proposal_and_dispatch(proposal)  # drains internally
            elif event.type == EventType.CHECKPOINT:
                runtime.checkpoint(event.payload["name"])
            elif event.type == EventType.RESTORE:
                runtime.restore(event.payload["name"])
        return runtime

    return asyncio.run(_drive())


def verify(trace: list[Event], seed: int) -> bool:
    """Replay and compare the final StateStore.chain_hash() against the
    value recorded on the trace's last STATE_PATCH event."""
    original = [e.payload["chain_hash"] for e in trace if e.type == EventType.STATE_PATCH]
    if not original:
        return True  # nothing that changed state; trivially consistent
    runtime = replay(trace, seed)
    return runtime.store.chain_hash() == original[-1]


def _shift_interruptions(trace: list[Event], shift_interrupt: float) -> list[Event]:
    """Offset every interruption-class event's timestamp by shift_interrupt,
    re-sort by t, reassign sequence numbers. Pure; no clock/network/Runtime."""
    shifted = [
        e.model_copy(update={"t": e.t + shift_interrupt}) if e.type in INTERRUPTION_EVENT_TYPES else e
        for e in trace
    ]
    shifted.sort(key=lambda e: (e.t, e.seq))
    return [e.model_copy(update={"seq": i}) for i, e in enumerate(shifted, start=1)]


def replay_counterfactual(trace: list[Event], seed: int, shift_interrupt: float):
    return replay(_shift_interruptions(trace, shift_interrupt), seed)
