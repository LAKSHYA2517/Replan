"""Injectable clock. RealClock and VirtualClock expose an identical
now()/sleep() interface so the rest of the runtime never knows which one
it's driving.

The entire project's testability rests on this: nothing outside this file
may call time.time() or bare asyncio.sleep().
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections.abc import Awaitable


class RealClock:
    """now() is elapsed time since this clock's first use, not the raw
    event-loop monotonic value (which is an arbitrary, often huge, number —
    e.g. seconds since something unrelated like system boot). VirtualClock
    always starts at 0.0; RealClock must match that semantics to be a fair
    drop-in replacement, and anything downstream that renders `t` as if it
    were "seconds since this scenario started" (every Event.t consumer)
    depends on it.
    """

    def __init__(self) -> None:
        self._start: float | None = None

    def now(self) -> float:
        loop_now = asyncio.get_event_loop().time()
        if self._start is None:
            self._start = loop_now
        return loop_now - self._start

    def sleep(self, delay: float) -> Awaitable[None]:
        return asyncio.sleep(delay)


class VirtualClock:
    """Discrete-event scheduler. Time only advances when nothing else can
    make progress, via run_until_idle()."""

    def __init__(self) -> None:
        self._now = 0.0
        self._heap: list[tuple[float, int, asyncio.Future]] = []
        self._seq = itertools.count()
        self._version = 0  # bumped on every sleep(), used to detect progress

    def now(self) -> float:
        return self._now

    def sleep(self, delay: float) -> Awaitable[None]:
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        heapq.heappush(self._heap, (self._now + delay, next(self._seq), future))
        self._version += 1
        return future

    async def run_until_idle(self, yields: int = 8) -> None:
        """Drive the loop until nothing more can happen without advancing
        time, then advance and repeat until nothing is left at all.

        Each pass yields to the loop `yields` times so every coroutine
        unblocked by the last resolution — including one that hasn't run
        its first line yet — can reach its next await point (and possibly
        push a new timer) before we decide the heap is truly stable. The
        heap-empty check happens only after a stable pass, not as the loop
        condition, because a just-scheduled task's first sleep() hasn't
        landed on the heap yet when this method is first entered.
        """
        while True:
            version = self._version
            for _ in range(yields):
                await asyncio.sleep(0)
            if self._version != version:
                continue  # new timers landed during the batch; let it settle further
            if not self._heap:
                return  # stable and nothing pending: truly idle
            deadline, _, future = heapq.heappop(self._heap)
            self._now = deadline
            if not future.done():
                future.set_result(None)
