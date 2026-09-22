"""Speculative async executor: dispatch, freeze/thaw, cancel, drain.

Never mutates StateStore and never decides validity — that's the gate's
job. This is the file the playbook warns will hide the subtlest bugs:
CancelledError must be re-raised before any general exception handler, and
the dispatch fingerprint (and the args a tool actually runs against) must be
captured synchronously in dispatch(), before create_task — never inside the
coroutine, where store.current may already have moved.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable

from replan.commit import CommitGate
from replan.depgraph import fingerprint, resolve
from replan.hashing import h
from replan.schemas import Effect, EventType, ExecutionPlan, PlanTask, TaskStatus, ToolResult, Verdict
from replan.state import StateStore
from replan.tools.registry import TOOL_SPECS


class SpeculationRefused(Exception):
    pass


class BudgetGovernor:
    """Three independent caps on speculative work: how many calls may be
    in flight, how much they may cost this turn, and whether they're
    actually paying off (a rolling hit-rate floor, once the window fills)."""

    def __init__(self, max_concurrent: int, max_cost_per_turn: float, hit_rate_floor: float, window: int = 20) -> None:
        self.max_concurrent = max_concurrent
        self.max_cost_per_turn = max_cost_per_turn
        self.hit_rate_floor = hit_rate_floor
        self._window: deque[bool] = deque(maxlen=window)
        self._concurrent = 0
        self._cost_this_turn = 0.0

    def allows(self, cost: float) -> tuple[bool, str]:
        if self._concurrent >= self.max_concurrent:
            return False, f"max_concurrent reached ({self._concurrent}/{self.max_concurrent})"
        if self._cost_this_turn + cost > self.max_cost_per_turn:
            return False, f"max_cost_per_turn would be exceeded ({self._cost_this_turn + cost:.2f} > {self.max_cost_per_turn})"
        if len(self._window) == self._window.maxlen:
            hit_rate = sum(self._window) / len(self._window)
            if hit_rate < self.hit_rate_floor:
                return False, f"hit rate {hit_rate:.2f} below floor {self.hit_rate_floor}"
        return True, "ok"

    def on_launch(self, cost: float) -> None:
        self._concurrent += 1
        self._cost_this_turn += cost

    def on_settle(self, was_useful: bool) -> None:
        self._concurrent -= 1
        self._window.append(was_useful)

    def reset_turn(self) -> None:
        self._cost_this_turn = 0.0


class Executor:
    def __init__(self, tools: dict[str, Callable[[dict, str], Awaitable[dict]]],
                 gate: CommitGate, store: StateStore, clock, governor: BudgetGovernor, recorder) -> None:
        self._tools = tools
        self._gate = gate
        self._store = store
        self._clock = clock
        self._governor = governor
        self._recorder = recorder
        self.results: asyncio.Queue[ToolResult] = asyncio.Queue()
        self._running: dict[str, asyncio.Task] = {}  # call_id -> asyncio.Task
        self._frozen: dict[str, ToolResult] = {}  # call_id -> parked result
        self._call_seq = 0  # deterministic call_id source; NOT uuid4 (unseeded, breaks replay)

    def dispatch(self, task: PlanTask, plan: ExecutionPlan) -> str | None:
        spec = TOOL_SPECS[task.tool]

        if task.speculative and spec["effect"] is Effect.IRREVERSIBLE:
            raise SpeculationRefused(f"{task.tool} is IRREVERSIBLE and cannot be speculated")

        if task.speculative:
            allowed, reason = self._governor.allows(spec["cost"])
            if not allowed:
                self._recorder.log(EventType.SPEC_REFUSED, task_id=task.id, tool=task.tool, reason=reason)
                return None

        # Fingerprint AND the args a tool will actually run against must be
        # captured here, synchronously, against store.current right now —
        # not inside the coroutine below, which may not run until state has
        # already moved.
        fp = fingerprint(task, self._store.current)
        resolved_args = resolve(task.arg_spec, self._store.current)

        if fp in self._gate.cache:
            task.dispatch_fp = fp
            task.status = TaskStatus.DONE
            self._recorder.log(EventType.CACHE_HIT, task_id=task.id, tool=task.tool, fingerprint=fp)
            return None

        self._call_seq += 1
        call_id = f"call-{self._call_seq}"
        idem = h(task.tool, resolved_args, fp)
        task.call_id = call_id
        task.dispatch_fp = fp
        task.status = TaskStatus.RUNNING
        self._recorder.log(
            EventType.TASK_DISPATCH,
            task_id=task.id, call_id=call_id, tool=task.tool, dispatch_fp=fp, idem=idem,
        )

        if task.speculative:
            self._governor.on_launch(spec["cost"])

        async_task = asyncio.create_task(self._run(task.id, task.tool, call_id, fp, resolved_args, idem))
        self._running[call_id] = async_task
        return call_id

    async def _run(self, task_id: str, tool_name: str, call_id: str, fp: str,
                    resolved_args: dict, idem: str) -> None:
        tool = self._tools[tool_name]
        try:
            payload = await tool(resolved_args, idem)
            result = ToolResult(call_id=call_id, task_id=task_id, ok=True, payload=payload, dispatch_fp=fp)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - tool failures become results, not crashes
            result = ToolResult(call_id=call_id, task_id=task_id, ok=False, payload={}, dispatch_fp=fp, error=str(exc))
        await self.results.put(result)

    def freeze(self, task_ids: set[str], plan: ExecutionPlan) -> None:
        for tid in task_ids:
            t = plan.tasks.get(tid)
            if t is not None and t.status == TaskStatus.RUNNING:
                t.status = TaskStatus.FROZEN
        self._recorder.log(EventType.TASK_FREEZE, task_ids=sorted(task_ids))

    def thaw(self, task_ids: set[str], plan: ExecutionPlan) -> None:
        for tid in task_ids:
            t = plan.tasks.get(tid)
            if t is not None and t.status == TaskStatus.FROZEN:
                t.status = TaskStatus.RUNNING
        self._recorder.log(EventType.TASK_THAW, task_ids=sorted(task_ids))

    def cancel(self, task: PlanTask) -> None:
        async_task = self._running.get(task.call_id) if task.call_id else None
        if async_task is not None and not async_task.done():
            async_task.cancel()
        task.status = TaskStatus.CANCELLED
        # NOTE: no EventType fits "cancel" in the frozen schema (see my
        # summary) — logging is deliberately withheld here pending that
        # decision, not forgotten.

    def drain(self, plan: ExecutionPlan) -> list[Verdict]:
        verdicts: list[Verdict] = []
        while not self.results.empty():
            result = self.results.get_nowait()
            task = plan.tasks.get(result.task_id)
            if task is not None and task.status == TaskStatus.FROZEN:
                self._frozen[result.call_id] = result
                continue
            verdict = self._gate.submit(result, plan)
            verdicts.append(verdict)
            if task is not None and task.speculative:
                self._governor.on_settle(verdict is Verdict.COMMIT)
        return verdicts

    def release_frozen(self, plan: ExecutionPlan) -> None:
        for result in self._frozen.values():
            self.results.put_nowait(result)
        self._frozen.clear()
