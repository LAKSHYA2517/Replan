"""Deterministic fault injection for async tools."""

from __future__ import annotations

import asyncio
import inspect

from replan.tools.registry import TOOL_SPECS


PROFILES = {
    "none": {"dup": 0.0, "reorder": 0.0, "fail": 0.0, "stall": 0.0, "jitter": 0.0},
    "mild": {"dup": 0.05, "reorder": 0.10, "fail": 0.0, "stall": 0.0, "jitter": 0.20},
    "severe": {"dup": 0.15, "reorder": 0.25, "fail": 0.10, "stall": 0.10, "jitter": 0.50},
}


class ChaosProxy:
    """Wrap a tool with seeded failures, delays, reordering and duplicates.

    Duplicate sinks receive ``(idem, result)``. Queue-like sinks receive that
    pair as one item; callable sinks receive it as two arguments. Keeping the
    identity unchanged lets the integration layer reproduce the original call
    id when it places the duplicate on the executor's result queue.
    """

    def __init__(self, inner, clock, rng, sink, profile) -> None:
        self.inner = inner
        self.clock = clock
        self.rng = rng
        self.sink = sink
        self.profile = dict(PROFILES[profile] if isinstance(profile, str) else profile)
        missing = set(PROFILES["none"]) - self.profile.keys()
        if missing:
            raise ValueError(f"chaos profile missing: {', '.join(sorted(missing))}")

        tool_name = getattr(inner, "__name__", "")
        registered_latency = TOOL_SPECS.get(tool_name, {}).get("latency", 0.0)
        self.base_latency = float(getattr(inner, "base_latency", registered_latency))
        self._deliveries: set[asyncio.Task] = set()

    async def __call__(self, args: dict, idem: str) -> dict:
        if self.rng.random() < self.profile["fail"]:
            await self.clock.sleep(self.rng.uniform(0.01, 0.10))
            raise RuntimeError("chaos-injected tool failure")

        delay = self.base_latency
        if self.rng.random() < self.profile["stall"]:
            delay *= 8
        jitter = self.profile["jitter"]
        if jitter:
            delay *= self.rng.uniform(1 - jitter, 1 + jitter)
        if self.rng.random() < self.profile["reorder"]:
            delay += self.rng.uniform(0.5, 2.0)
        await self.clock.sleep(max(0.0, delay))

        result = await self.inner(args, idem)
        if self.rng.random() < self.profile["dup"]:
            delivery = asyncio.create_task(self._deliver_duplicate(idem, result))
            self._deliveries.add(delivery)
            delivery.add_done_callback(self._deliveries.discard)
        return result

    async def _deliver_duplicate(self, idem: str, result: dict) -> None:
        await self.clock.sleep(self.rng.uniform(0.01, 0.10))
        if callable(self.sink):
            delivered = self.sink(idem, result)
        elif hasattr(self.sink, "put"):
            delivered = self.sink.put((idem, result))
        else:
            self.sink.append((idem, result))
            return
        if inspect.isawaitable(delivered):
            await delivered
