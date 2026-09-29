"""LiveKit lifecycle adapter: routes AgentSession callbacks into Runtime's
existing methods.

This formalizes the exact pattern B9's agent.py already proved live
in-line, per that file's own note that A7 would extract Runtime
construction/reset and the settle loop here. Nothing here changes B9's
behaviour — it's the same three pieces (fresh Runtime per scenario, route
a partial transcript, route a model-requested tool call through
Executor/CommitGate, drain and speak on commit), pulled out so any
LiveKit tool-calling surface gets them for free instead of
reimplementing them inline, and so they're provable without a live
LiveKit session (see the __main__ demo at the bottom).

runtime.py stays LiveKit-agnostic — no LiveKit imports in it, per
AGENTS.md and this package's own constraint. This file may import LiveKit
SDK types (agent.py does), but nothing below actually needs to: every
function here takes plain Runtime/dict/callable arguments, never an
AgentSession, so it stays testable with no LiveKit dependency running.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable

from replan.clock import RealClock
from replan.runtime import Policy, Runtime
from replan.schemas import Proposal, Verdict


def build_scenario_runtime(
    tools: dict, *, policy: Policy = Policy.REPLAN, seed: int | None = None, scenario_id: str | None = None
) -> Runtime:
    """THE scenario-boundary hook (A10): construct a FRESH Runtime for one
    scenario. Call this at the start of EVERY scenario — never once per
    LiveKit job/process and reused across two different scenario ids, even
    if the harness reuses one room or process for the whole sweep.

    Pass scenario_id whenever one is known (the FDB-v3 scenario/example
    id). Runtime.__init__ already builds a fresh StateStore, CommitGate
    cache, rng, clock and recorder every call — re-instantiating here is
    enough for all of those, nothing to separately reset. The one thing
    that needs scenario_id explicitly is the LLM response cache, which
    without it would default to one file shared across every scenario in
    the process; see the comment in runtime.py.
    """
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
    return Runtime(clock=RealClock(), seed=seed, policy=policy, tools=tools, scenario_id=scenario_id)


def route_partial_transcript(runtime: Runtime, text: str) -> None:
    """On a partial transcript event from LiveKit's STT/turn pipeline."""
    runtime.on_partial(text)


async def route_final_transcript(runtime: Runtime, text: str) -> list[Verdict]:
    """On a final transcript / end-of-turn event — the literal brief line.
    Not currently called by agent.py: B9's tool-calling-first design routes
    self-correction through route_tool_call_via_state instead (sufficient
    for FDB-v3's per-tool-call domain, and already proven live), so the
    full extract_proposal -> build_plan -> reconcile path this drives
    currently goes unused there. Provided so any integration that does
    want it — including the original hotel/extension scenarios, which
    still rely on it — has it available without reimplementing the call.
    """
    return await runtime.on_final(text)


def on_turn_complete(runtime: Runtime) -> list[Verdict]:
    """Call this from LiveKit's own turn-completion event instead of
    settle_loop's timer, once the chosen template exposes one — the
    literal "tick() on LiveKit's own turn cadence" the brief asks for.
    Not currently wired by agent.py, which uses settle_loop's polling
    fallback below instead; this is the primitive to switch to the moment
    a real turn-boundary event is available to call it from.
    """
    return runtime.tick()


def route_tool_call_via_state(runtime: Runtime, tool: str, args: dict, *, speculative: bool = False) -> str | None:
    """The one path a tool-calling surface should use to turn a
    model-requested call into a dispatch: write its args into SessionState
    under a per-tool namespace FIRST, then dispatch a task whose arg_spec
    references that state via $ref — never a literal value — so a later
    correction that re-patches the same slot path makes this task's
    fingerprint go stale on arrival, exactly like every other dispatch in
    this project. This is B9's _dispatch_via_state pattern, proved live in
    agent.py; formalized here so it isn't reimplemented per template.
    """
    slot_patch = {f"{tool}__{key}": value for key, value in args.items()}
    runtime.on_proposal(Proposal(kind="state_patch", patch={"slots": slot_patch}))
    arg_spec = {key: {"$ref": f"slots.{tool}__{key}"} for key in args}
    return runtime.dispatch_new_task(tool, arg_spec, speculative=speculative)


async def settle_loop(
    runtime: Runtime,
    on_commit: Callable[[list[dict]], Awaitable[None]],
    *,
    tick_interval: float = 0.2,
) -> None:
    """Background loop: drains the executor on the caller's own cadence,
    and calls on_commit with the newly committed (tool, payload) pairs the
    moment CommitGate actually adjudicates them — never before, and never
    for a result that lands STALE. Runs forever; the caller cancels it
    when the session ends.
    """
    seen: set[str] = set()
    while True:
        await runtime.clock.sleep(tick_interval)
        verdicts = runtime.tick()
        if Verdict.COMMIT not in verdicts:
            continue
        new_fps = set(runtime.gate.cache) - seen
        if not new_fps:
            continue
        seen |= new_fps
        committed = [
            {"tool": task.tool, "payload": runtime.gate.cache[task.dispatch_fp]}
            for task in runtime.plan.tasks.values()
            if task.dispatch_fp in new_fps and task.status.value == "done"
        ]
        if committed:
            await on_commit(committed)


async def _run_demo() -> None:
    """make demo's equivalent for the LiveKit path: no WebSocket loop, no
    live LiveKit session — the same signature self-correction scenario
    (a tool call, then a mid-call pivot to the same tool with different
    args), driven purely through this adapter's own functions, printing
    the verdict ledger. Uses real FDB-v3 tools (via A9), same discipline
    as runtime.py's own demo.
    """
    import asyncio

    from replan.tools.fdb_contract import FDB_TOOLS, make_fdb_tool
    from replan.tools.registry import TOOL_SPECS

    async def commit_printer(committed: list[dict]) -> None:
        for c in committed:
            print(f"  spoken: committed {c['tool']} -> {c['payload']}")

    clock = RealClock()
    tools = {name: make_fdb_tool(name, clock, TOOL_SPECS[name]["latency"]) for name in FDB_TOOLS}
    runtime = build_scenario_runtime(tools, seed=7)
    settle_task = asyncio.create_task(settle_loop(runtime, commit_printer, tick_interval=0.1))

    print("=== LiveKit adapter demo: self-correction on search_flights ===")
    route_partial_transcript(runtime, "Find me a flight to")  # T1 fast path, no-op until B5/B6 land
    route_tool_call_via_state(runtime, "search_flights", {"destination": "Chicago", "date": "2026-07-15"})
    await runtime.clock.sleep(0.05)  # a later correction, before the first call has settled
    route_tool_call_via_state(runtime, "search_flights", {"destination": "Boston", "date": "2026-07-15"})

    await runtime.clock.sleep(2.0)  # let both settle
    settle_task.cancel()

    print(f"\nverdict ledger ({len(runtime.gate.ledger)} decisions):")
    for d in runtime.gate.ledger:
        print(f"  {d.call_id:>10} | {d.verdict.value:>7} | {d.reason}")
    print(f"final state: {dict(runtime.store.current.slots)}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(_run_demo())
