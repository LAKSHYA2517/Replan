"""The commit gate. THE ONLY component permitted to mutate committed state.

For every arriving tool result, judge() decides — pure, no side effects —
whether it is still allowed to matter, and submit() applies the consequence.
No override, no force: there is no legitimate reason to bypass this gate.
"""

from __future__ import annotations

from replan.depgraph import fingerprint
from replan.schemas import (
    CommitDecision,
    EventType,
    ExecutionPlan,
    PlanTask,
    TaskStatus,
    ToolResult,
    Verdict,
)
from replan.state import StateStore

_FP_DISPLAY = 8  # truncation width for fingerprints inside reason strings


def _version_dispatched_at(store: StateStore, task: PlanTask, dispatch_fp: str) -> int | None:
    """Find the earliest history version whose fingerprint for this task
    matches dispatch_fp, so the STALE reason can name it. A plain linear
    scan over already-retained history — not a cache, just a read.
    """
    for v in range(store.current.version + 1):
        if fingerprint(task, store.at(v)) == dispatch_fp:
            return v
    return None


class CommitGate:
    def __init__(self, store: StateStore, recorder) -> None:
        self._store = store
        self._recorder = recorder
        self.cache: dict[str, dict] = {}
        self._adjudicated: set[str] = set()
        self.ledger: list[CommitDecision] = []

    def judge(self, result: ToolResult, plan: ExecutionPlan) -> tuple[Verdict, str]:
        if result.call_id in self._adjudicated:
            return Verdict.DUPLICATE, f"call {result.call_id} already adjudicated"

        task = plan.tasks.get(result.task_id)
        if task is None:
            return Verdict.STALE, f"task {result.task_id} not in active plan"

        if task.status in (TaskStatus.CANCELLED, TaskStatus.INVALIDATED):
            return Verdict.CANCELLED, f"task {result.task_id} is {task.status.value}"

        if not result.ok:
            return Verdict.INVALID, result.error or f"tool reported failure for task {result.task_id}"

        current_fp = fingerprint(task, self._store.current)
        if result.dispatch_fp != current_fp:
            at = _version_dispatched_at(self._store, task, result.dispatch_fp)
            dispatched_label = f"v{at}" if at is not None else "an untracked state"
            return Verdict.STALE, (
                f"dispatch fp {result.dispatch_fp[:_FP_DISPLAY]}... != "
                f"current {current_fp[:_FP_DISPLAY]}... "
                f"(dispatched at {dispatched_label}, now v{self._store.current.version})"
            )

        return Verdict.COMMIT, "fingerprint matches current state"

    def submit(self, result: ToolResult, plan: ExecutionPlan) -> Verdict:
        verdict, reason = self.judge(result, plan)
        self._adjudicated.add(result.call_id)

        if verdict is Verdict.COMMIT:
            self.cache[result.dispatch_fp] = result.payload
            plan.tasks[result.task_id].status = TaskStatus.DONE

        event = self._recorder.log(
            EventType.VERDICT,
            call_id=result.call_id,
            task_id=result.task_id,
            verdict=verdict.value,
            reason=reason,
        )
        self.ledger.append(
            CommitDecision(
                call_id=result.call_id,
                task_id=result.task_id,
                verdict=verdict,
                reason=reason,
                t=event.t,
            )
        )
        return verdict
