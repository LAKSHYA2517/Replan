"""RePlan WebSocket event bridge server.

Drives one real Runtime instance through the signature scenario and
broadcasts its actual recorder events to connected browser consoles.
"inject_late_result" arrives as a WebSocket message (the frontend used to
send it as an HTTP POST, which this server never implemented — fixed on
the frontend side in useEventStream.ts to match the transport this file
already spoke, rather than bolting an HTTP route onto a WebSocket server
for a feature that didn't need one).
"""

from __future__ import annotations

import asyncio
import json
import logging
from random import Random
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

from bench.scenarios import hotel_locality_pivot
from replan.clock import RealClock
from replan.runtime import Policy, Runtime, _demo_plan
from replan.schemas import Event, Proposal, ToolResult
from replan.tools.mocks import make_mock_tool

logger = logging.getLogger("replan.server")

_TICK_INTERVAL = 0.15  # seconds; how often we drain settled tool results while live


class EventBridgeServer:
    """Async WebSocket server that broadcasts a live Runtime's events to
    browser consoles, and injects a late result on request."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.injected_late_results: asyncio.Queue[dict] = asyncio.Queue()

        self._runtime: Runtime | None = None
        self._scenario: dict | None = None
        self._late_dispatch_fp: str | None = None
        self._last_emitted = 0
        self._scenario_task: asyncio.Task | None = None

    async def register(self, websocket: WebSocketServerProtocol) -> None:
        """Register a new connected client."""
        self.clients.add(websocket)
        logger.info("Browser client connected (%d active)", len(self.clients))
        if self._scenario_task is None:
            # Start on first connection, not at process startup: emit_event()
            # is a no-op with zero clients, so anything broadcast before a
            # client exists is lost — a client connecting after would just
            # see nothing.
            self._scenario_task = asyncio.create_task(self._run_scenario())

    async def unregister(self, websocket: WebSocketServerProtocol) -> None:
        """Unregister a disconnected client."""
        self.clients.discard(websocket)
        logger.info("Browser client disconnected (%d active)", len(self.clients))

    async def broadcast(self, event_data: dict) -> None:
        """Broadcast an event payload to all connected clients."""
        if not self.clients:
            return
        message = json.dumps(event_data)
        # Send concurrently to all connected clients
        await asyncio.gather(
            *[client.send(message) for client in self.clients],
            return_exceptions=True,
        )

    async def emit_event(self, event: Event) -> None:
        """Emit a schema Event object to the broadcast queue."""
        event_dict = event.model_dump(mode="json")
        await self.broadcast(event_dict)

    async def _emit_new_events(self) -> None:
        assert self._runtime is not None
        for event in self._runtime.recorder.events[self._last_emitted:]:
            await self.emit_event(event)
        self._last_emitted = len(self._runtime.recorder.events)

    async def _run_scenario(self) -> None:
        """Drive the real signature scenario end to end, broadcasting every
        event as it's actually produced — not narrated, not pre-recorded."""
        clock = RealClock()
        rng = Random(7)
        tools = {
            name: make_mock_tool(name, clock, rng, 0.4)
            for name in ("search_hotels", "loyalty_status")
        }
        runtime = Runtime(clock=clock, seed=7, policy=Policy.REPLAN, tools=tools)
        scenario = hotel_locality_pivot(interrupt_offset=3.0)
        desired = {c["tool"]: c for c in scenario["initial"]["tool_calls"]}
        runtime.build_plan = lambda state: _demo_plan(state, desired)

        self._runtime = runtime
        self._scenario = scenario

        new_state, _ = runtime.on_proposal(Proposal(patch=scenario["initial"]["patch"]))
        runtime.plan = runtime.build_plan(new_state)
        for task in runtime.plan.tasks.values():
            runtime.executor.dispatch(task, runtime.plan)
        # Capture the fingerprint the late result is dispatched under RIGHT
        # NOW, before the interrupt below replaces runtime.plan — looking it
        # up later would silently pick up the new fingerprint and the "late,
        # stale" result would wrongly commit (hit this exact bug building
        # make demo; same fix applies here).
        late = scenario["late_result"]
        self._late_dispatch_fp = runtime.plan.tasks[late["tool"]].dispatch_fp
        await self._emit_new_events()

        elapsed = 0.0
        while elapsed < scenario["interruption"]["at"]:
            await clock.sleep(_TICK_INTERVAL)
            elapsed += _TICK_INTERVAL
            runtime.tick()
            await self._emit_new_events()

        # Update the plan-builder's desired tool_calls to the interruption's
        # BEFORE rebuilding the plan, or build_plan reuses the old (Bandra)
        # literal args, which happen to fingerprint-match the already-cached
        # result -- reconcile() then "correctly" treats it as a cache-hit
        # reuse and never dispatches anything new at all. Same pattern
        # bench/run.py already gets right; missed it here on the first pass.
        desired.update({c["tool"]: c for c in scenario["interruption"]["tool_calls"]})
        await runtime.apply_proposal_and_dispatch(Proposal(patch=scenario["interruption"]["patch"]))
        await self._emit_new_events()

        # Keep draining indefinitely: the post-interrupt dispatch still has
        # to settle, and a manually injected late result needs an ongoing
        # tick() loop as a backstop even though _inject_late_result also
        # ticks immediately for a responsive click.
        while True:
            await clock.sleep(_TICK_INTERVAL)
            runtime.tick()
            await self._emit_new_events()

    async def _inject_late_result(self) -> None:
        if self._runtime is None or self._scenario is None or self._late_dispatch_fp is None:
            logger.warning("inject_late_result requested before the scenario has dispatched anything")
            return
        late = self._scenario["late_result"]
        self._runtime.executor.results.put_nowait(
            ToolResult(
                call_id="late-live", task_id=late["tool"], ok=True,
                payload=dict(late["args"]), dispatch_fp=self._late_dispatch_fp,
            )
        )
        self._runtime.tick()
        await self._emit_new_events()

    async def handler(self, websocket: WebSocketServerProtocol, path: str = "/") -> None:
        """Main WebSocket connection handler."""
        await self.register(websocket)
        try:
            async for message in websocket:
                # Handle any incoming commands from client
                try:
                    data = json.loads(message)
                    if data.get("type") == "inject_late_result":
                        await self.injected_late_results.put(data)
                        await self._inject_late_result()
                except Exception as e:
                    logger.warning("Error processing client message: %s", e)
        except websockets.ConnectionClosed:
            pass
        finally:
            await self.unregister(websocket)

    async def start(self) -> None:
        """Start the WebSocket server loop."""
        logger.info("Starting RePlan Event Bridge on ws://%s:%d/events", self.host, self.port)
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()  # run forever


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server = EventBridgeServer()
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
