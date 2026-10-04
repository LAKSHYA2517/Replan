"""B9 — LiveKit realtime-template agent entrypoint.

Uses Gemini's native realtime model (audio in, audio out, one hosted
call) rather than the original cascaded freellmapi pipeline. The
original cascaded setup pointed its STT/LLM/TTS stages at
FREELLMAPI_BASE_URL=http://127.0.0.1:31415 — a loopback address, i.e.
a server running on the developer's own machine. The official Theme 05
guide is explicit: "Don't call your own servers at evaluation time;
all agent logic lives in the submission" — and "if your script does
not reproduce [on our machine], this portion scores zero." A judge's
machine has nothing listening on that port, so the old setup would
fail the reproduction script outright. Gemini's realtime model only
needs GOOGLE_API_KEY (a real, free-tier, externally-reachable hosted
API — the same one already proven working for the FDB-v3 benchmark
run), so it's both a compliance fix and the only way to get a result
that means anything off this machine.

Swapping the model backend is not a one-line change: Gemini's realtime
model does not set RealtimeCapabilities.supports_say (confirmed by
reading livekit-plugins-google's own source), so AgentSession.say()
raises at runtime without a separate TTS configured. The fix used here
is session.generate_reply(instructions=...) instead of say() — verified
compatible with any RealtimeModel, since it goes through the model's
own generation path rather than attempting to inject text directly.
_compose_response() below is a deterministic, local, no-network
grounding step (replacing the old compose_response() call out to
freellmapi) — it fixes the facts before generate_reply() ever runs, so
Gemini can only phrase them, not invent new ones.

Architecture rule this file exists to enforce (per AGENTS.md and the B9
brief): the model's own native tool-calling is NEVER allowed to decide
whether a tool call actually happened. Every FDB-v3 tool is wrapped as a
function_tool whose body does not execute anything — it writes the
call's arguments into SessionState (Runtime.on_proposal, the same
Proposal path B4's extract_proposal produces from a transcript) and
dispatches a task with a $ref-based arg_spec against that state, then
returns an immediate acknowledgment. This is deliberate, not a
shortcut: FDB-v3's tools take literal arguments with no natural
$ref-shaped state reference, but the project's entire predictive-freeze
mechanism (B5/B6) depends on deps(task) actually resolving to state
paths. Routing every tool call through a state patch first is what
makes a mid-call correction ("actually, make that Chicago") produce a
real fingerprint mismatch on the in-flight task instead of silently
never triggering staleness detection at all.

The real committed result reaches the conversation only once CommitGate
actually commits it (via a background settle loop below).

A7 (A's package) will formalize Runtime construction/reset into
replan/livekit_agent.py, including A10's cross-scenario reset guarantee
(a fresh Runtime per scenario, never reused). This file constructs one
Runtime per LiveKit job for now, using only Runtime's existing public
interface (on_partial, on_proposal, tick) — it does not modify
runtime.py, matching the ownership rule in AGENTS.md.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import google

from replan.clock import RealClock
from replan.runtime import Policy, Runtime
from replan.schemas import PlanTask, Proposal, TaskStatus, Verdict
from replan.tools.fdb_contract import FDB_TOOLS, make_fdb_tool
from replan.tools.registry import TOOL_SPECS

load_dotenv()
logger = logging.getLogger("replan.agent")
logger.setLevel(logging.INFO)

_TICK_INTERVAL = 0.2  # seconds between settle-loop drains while a session is live
_ANNOUNCE_ATTEMPTS = 3
_ANNOUNCE_RETRY_DELAY = 1.0  # seconds, via the injected clock
_ANNOUNCE_POLL = 0.2  # seconds between checks for the agent to go idle
_ANNOUNCE_MAX_WAIT = 15.0  # seconds to wait for idle before speaking anyway

TOOL_DESCRIPTIONS: dict[str, str] = {
    "search_flights": "Search available flights to a destination on a given date.",
    "book_flight": "Book a flight for a passenger, optionally on a specific flight id.",
    "update_identity_doc": "Update the traveler's identity document on file.",
    "get_card_benefits": "Look up the benefits for a given card type.",
    "get_exchange_rate": "Convert an amount from one currency to another.",
    "modify_autopay": "Change the funding source for an autopay bill.",
    "search_apartments": "Search apartments in a city under a max price with a bedroom count.",
    "calculate_commute": "Estimate commute duration between two addresses.",
    "update_search_filter": "Update one named search filter to a new value.",
    "track_order": "Look up the shipping status of an order by id.",
    "search_products": "Search products matching a query, optionally under a max price.",
    "add_to_cart": "Add a product and quantity to the cart.",
}


@dataclass
class SessionData:
    """Per-session state, reachable from every tool call via
    RunContext.userdata. task_counter guarantees unique task ids across
    the whole session without reusing plan.tasks' own size (which can
    shrink if a task is ever removed — a counter never goes backwards)."""

    runtime: Runtime
    task_counter: itertools.count = field(default_factory=itertools.count)
    seen_dispatch_fps: set[str] = field(default_factory=set)
    room_name: str = ""


def _build_runtime() -> Runtime:
    clock = RealClock()
    tools = {name: make_fdb_tool(name, clock, TOOL_SPECS[name]["latency"]) for name in FDB_TOOLS}
    import random

    return Runtime(clock=clock, seed=random.SystemRandom().randrange(2**31), policy=Policy.REPLAN, tools=tools)


def _compose_response(committed_results: list[dict]) -> str:
    """Deterministic, local summary of what CommitGate just committed —
    no network call, no LLM, so there is nothing here that can invent a
    fact beyond what actually committed. Handed to generate_reply() as
    instructions so the model only has to phrase it, not decide it.
    """
    if not committed_results:
        return "Nothing has been confirmed yet."
    return " ".join(
        f"{item['tool'].replace('_', ' ')} result: {_describe(item['payload'])}." for item in committed_results
    )


def _describe(value) -> str:
    if isinstance(value, dict):
        parts = [f"{k.replace('_', ' ')} {_describe(v)}" for k, v in value.items() if not (k == "status" and v == "success")]
        return ", ".join(parts) or "done"
    if isinstance(value, list):
        return "; ".join(_describe(v) for v in value) or "none"
    return str(value)


_TOOL_CALL_TELEMETRY = "/tmp/agent_tool_calls.log"


def _record_tool_call(room_name: str, tool_name: str, args: dict) -> None:
    """Append the call where FDB-v3's scorer collects actual tool calls
    (run_tool_benchmark.py reads this exact path and room-name key). Without
    it every example scores as 'no tool called', regardless of what the
    agent actually did.
    """
    now = time.time()
    record = {"room": room_name, "call": {"function": tool_name, "args": args, "timestamp_start": now, "timestamp_end": now}}
    with open(_TOOL_CALL_TELEMETRY, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


async def _dispatch_via_state(session_data: SessionData, tool_name: str, args: dict) -> str:
    """Write the call's args into SessionState under a per-tool namespace,
    then dispatch a task whose arg_spec references that state via $ref —
    never literal values — so a later correction that re-patches the same
    slot path makes this task's fingerprint go stale, exactly like every
    other tool dispatch in this project.
    """
    runtime = session_data.runtime
    slot_patch = {f"{tool_name}__{key}": value for key, value in args.items()}
    runtime.on_proposal(Proposal(kind="state_patch", patch={"slots": slot_patch}))

    arg_spec = {key: {"$ref": f"slots.{tool_name}__{key}"} for key in args}
    task_id = f"{tool_name}-{next(session_data.task_counter)}"
    task = PlanTask(id=task_id, tool=tool_name, arg_spec=arg_spec, status=TaskStatus.PENDING)
    runtime.plan.tasks[task_id] = task
    runtime.executor.dispatch(task, runtime.plan)
    _record_tool_call(session_data.room_name, tool_name, args)
    logger.info("dispatch %s args=%s", task_id, args)
    return "On it — I'll let you know as soon as that's done."


def _make_tool(name: str):
    """Builds one @function_tool per FDB-v3 tool, with real typed
    parameters taken from Full-Duplex-Bench's own v3/mock_apis.py (not
    the published paper's table, which names several of these
    differently — confirmed against the actual repo, same discipline A9
    already applied). The body never calls the real mock function
    directly; see _dispatch_via_state.
    """
    description = TOOL_DESCRIPTIONS[name]

    if name == "search_flights":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], destination: str, date: str) -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"destination": destination, "date": date})

    elif name == "book_flight":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], passenger_name: str, flight_id: str = "FL123") -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"passenger_name": passenger_name, "flight_id": flight_id})

    elif name == "update_identity_doc":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], doc_type: str, doc_number: str) -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"doc_type": doc_type, "doc_number": doc_number})

    elif name == "get_card_benefits":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], card_type: str) -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"card_type": card_type})

    elif name == "get_exchange_rate":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], amount: float, from_currency: str, to_currency: str) -> str:
            return await _dispatch_via_state(
                ctx.userdata, name, {"amount": amount, "from_currency": from_currency, "to_currency": to_currency}
            )

    elif name == "modify_autopay":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], bill_type: str, source_account: str) -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"bill_type": bill_type, "source_account": source_account})

    elif name == "search_apartments":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], city: str, bedrooms: int, max_price: float) -> str:
            return await _dispatch_via_state(
                ctx.userdata, name, {"city": city, "bedrooms": bedrooms, "max_price": max_price}
            )

    elif name == "calculate_commute":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], origin_address: str, destination_address: str, mode: str = "driving") -> str:
            return await _dispatch_via_state(
                ctx.userdata, name,
                {"origin_address": origin_address, "destination_address": destination_address, "mode": mode},
            )

    elif name == "update_search_filter":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], filter_name: str, value: str) -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"filter_name": filter_name, "value": value})

    elif name == "track_order":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], order_id: str) -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"order_id": order_id})

    elif name == "search_products":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], query: str, max_price: Optional[float] = None) -> str:
            args = {"query": query}
            if max_price is not None:
                args["max_price"] = max_price
            return await _dispatch_via_state(ctx.userdata, name, args)

    elif name == "add_to_cart":

        @function_tool(name=name, description=description)
        async def _tool(ctx: RunContext[SessionData], product_id: str, quantity: int) -> str:
            return await _dispatch_via_state(ctx.userdata, name, {"product_id": product_id, "quantity": quantity})

    else:
        raise ValueError(f"No wrapper defined for FDB tool: {name!r}")

    return _tool


def build_tools() -> list:
    return [_make_tool(name) for name in FDB_TOOLS]


async def _settle_loop(session: AgentSession, session_data: SessionData) -> None:
    """Background loop: drains the executor, and the moment a result
    actually commits, speaks it — grounded in the committed payload only
    (_compose_response is a deterministic local function, no network, no
    LLM), handed to the realtime model via generate_reply() so it can
    phrase it naturally without being able to invent new facts. Never
    speaks from a task the gate hasn't adjudicated.

    generate_reply(), not say(): Gemini's realtime model does not set
    RealtimeCapabilities.supports_say, so say() would raise at runtime
    without a separate TTS configured (confirmed against the installed
    livekit-plugins-google source before writing this).
    """
    runtime = session_data.runtime
    logged_decisions = 0
    announcements: set[asyncio.Task] = set()
    while True:
        await runtime.clock.sleep(_TICK_INTERVAL)
        verdicts = runtime.tick()
        for decision in runtime.gate.ledger[logged_decisions:]:
            logger.info("verdict %s %s: %s", decision.call_id, decision.verdict.value, decision.reason)
        logged_decisions = len(runtime.gate.ledger)
        if Verdict.COMMIT not in verdicts:
            continue

        new_fps = set(runtime.gate.cache) - session_data.seen_dispatch_fps
        if not new_fps:
            continue
        session_data.seen_dispatch_fps |= new_fps

        committed_results = []
        for task in runtime.plan.tasks.values():
            if task.dispatch_fp in new_fps and task.status.value == "done":
                committed_results.append({"tool": task.tool, "payload": runtime.gate.cache[task.dispatch_fp]})
        if not committed_results:
            continue

        text = _compose_response(committed_results)
        announcement = asyncio.create_task(_announce(session, runtime.clock, text))
        announcements.add(announcement)
        announcement.add_done_callback(announcements.discard)


async def _announce(session: AgentSession, clock, text: str) -> None:
    """Speak one committed result, retrying if the realtime model fails to
    generate it (observed live: 'generate_reply timed out waiting for
    generation_created' right after a tool call, which silently dropped
    that answer). Runs as its own task so a slow generation never stalls
    the settle loop's ticks.
    """
    instructions = (
        "Say one natural spoken sentence that states the following confirmed "
        "facts. Do not read out field names or labels, and do not add, infer, "
        f"or embellish anything not listed here: {text}"
    )
    waited = 0.0
    while session.agent_state in ("speaking", "thinking") and waited < _ANNOUNCE_MAX_WAIT:
        await clock.sleep(_ANNOUNCE_POLL)
        waited += _ANNOUNCE_POLL
    for attempt in range(_ANNOUNCE_ATTEMPTS):
        handle = session.generate_reply(instructions=instructions)
        await handle
        if handle.exception() is None:
            return
        logger.warning("announcement attempt %d failed: %r", attempt + 1, handle.exception())
        await clock.sleep(_ANNOUNCE_RETRY_DELAY)
    logger.error("giving up on announcement after %d attempts: %s", _ANNOUNCE_ATTEMPTS, text)


async def entrypoint(ctx: JobContext) -> None:
    logger.info("job entered, connecting to room")
    await ctx.connect()
    logger.info("connected to room")

    runtime = _build_runtime()
    session_data = SessionData(runtime=runtime, room_name=ctx.room.name)

    session: AgentSession[SessionData] = AgentSession(
        userdata=session_data,
        llm=google.realtime.RealtimeModel(
            model=os.environ.get("GOOGLE_REALTIME_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"),
            voice=os.environ.get("GOOGLE_VOICE", "Puck"),
        ),
    )

    @session.on("user_input_transcribed")
    def _on_transcript(event) -> None:
        # T1 fast path (B5/B6): drives the predictive-freeze hypothesis
        # classifier on every partial. LiveKit's own turn detection
        # already handles barge-in (B1) — this is purely the freeze
        # decision, not audio control.
        logger.info("user transcript (final=%s): %s", event.is_final, event.transcript)
        if not event.is_final:
            runtime.on_partial(event.transcript)

    settle_task = asyncio.create_task(_settle_loop(session, session_data))
    settle_task.add_done_callback(
        lambda t: logger.error("settle loop died: %r", t.exception())
        if not t.cancelled() and t.exception() is not None
        else None
    )

    @session.on("close")
    def _on_close(_event) -> None:
        settle_task.cancel()

    await session.start(
            agent=Agent(
                instructions=(
                    "You are a helpful assistant for travel, finance, housing, "
                    "and e-commerce tasks. The user speaks English. "
                    "Every request that asks for a search, a lookup, a booking, "
                    "a change, or an addition needs a tool call. Call the "
                    "matching tool in that same turn, before saying anything "
                    "else, even if the request is long or has several parts; "
                    "for several parts, call one tool for each part. Do not "
                    "ask follow-up questions before searching: once you know "
                    "what the user wants, call the tool with the details they "
                    "have given, and fill any missing detail with the most "
                    "reasonable value. Only ask about missing details after "
                    "you have results to show. Never say "
                    "you are searching, booking, or changing something unless "
                    "you have actually called the tool. "
                    "When you fill in tool arguments, copy values exactly as the "
                    "user said them: keep identifiers, order numbers, document "
                    "numbers, card names, and product names word for word, with "
                    "no added or removed hyphens, spaces, or letters. Keep dates "
                    "exactly as the user said them, without adding a year. "
                    "Write amounts and counts as plain numbers, without currency "
                    "symbols or words. After calling a tool, tell the user you're "
                    "working on it — the actual result will be reported back "
                    "to them separately once it's ready."
                ),
                tools=build_tools(),
            ),
            room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
