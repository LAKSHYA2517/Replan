"""Plan diffing: replace "cancel everything and restart" with selective
reuse. Pure bookkeeping — no cancellation, no tool calls. The caller acts
on the returned lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from replan.depgraph import fingerprint
from replan.schemas import ExecutionPlan, PlanTask, SessionState, TaskStatus
from replan.tools.registry import TOOL_SPECS

_ADOPTABLE = (TaskStatus.RUNNING, TaskStatus.FROZEN)
_INVALIDATABLE = (TaskStatus.RUNNING, TaskStatus.FROZEN, TaskStatus.PENDING)


@dataclass
class Reconciliation:
    adopted: list[PlanTask] = field(default_factory=list)
    reused_from_cache: list[PlanTask] = field(default_factory=list)
    invalidated: list[PlanTask] = field(default_factory=list)
    added: list[PlanTask] = field(default_factory=list)
    compensate: list[PlanTask] = field(default_factory=list)

    @property
    def reuse_ratio(self) -> float:
        denom = len(self.adopted) + len(self.reused_from_cache) + len(self.invalidated) + len(self.added)
        if denom == 0:
            return 0.0
        return (len(self.adopted) + len(self.reused_from_cache)) / denom


def reconcile(old_plan: ExecutionPlan, new_plan: ExecutionPlan, new_state: SessionState,
              cache: dict[str, dict]) -> Reconciliation:
    result = Reconciliation()

    old_by_fp: dict[str, PlanTask] = {
        t.dispatch_fp: t for t in old_plan.tasks.values() if t.dispatch_fp
    }
    new_fps: set[str] = set()

    for task in new_plan.tasks.values():
        fp = fingerprint(task, new_state)
        new_fps.add(fp)

        # 1. cache hit beats adoption: if the work already committed, reuse
        # it for free rather than adopting a running duplicate.
        if fp in cache:
            task.status = TaskStatus.DONE
            task.dispatch_fp = fp
            result.reused_from_cache.append(task)
            continue

        # 2. in-flight donor from the old plan
        donor = old_by_fp.get(fp)
        if donor is not None and donor.status in _ADOPTABLE:
            task.status = TaskStatus.RUNNING
            task.call_id = donor.call_id
            task.dispatch_fp = fp
            donor.status = TaskStatus.DONE  # so it isn't double-counted below
            result.adopted.append(task)
            continue

        # 3. genuinely new work
        result.added.append(task)

    for task in old_plan.tasks.values():
        if task.dispatch_fp in new_fps:
            continue
        if task.status in _INVALIDATABLE:
            task.status = TaskStatus.INVALIDATED
            result.invalidated.append(task)
            compensator = TOOL_SPECS.get(task.tool, {}).get("compensator")
            if compensator and task.dispatch_fp in cache:
                result.compensate.append(task)
        elif task.status is TaskStatus.DONE:
            # The work already committed (e.g. a held reservation) but is
            # no longer wanted under the new state. It isn't "invalidated"
            # — it finished successfully — but its REVERSIBLE effect still
            # needs undoing. This is the case the literal per-status filter
            # above misses on its own: by the time reconcile() runs, a
            # landed effect's task is already DONE, not RUNNING/FROZEN/
            # PENDING. Caught via integration testing through runtime.py —
            # the C2/demo compensation beat depends on this.
            compensator = TOOL_SPECS.get(task.tool, {}).get("compensator")
            if compensator and task.dispatch_fp in cache:
                result.compensate.append(task)

    return result
