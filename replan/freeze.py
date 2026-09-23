"""Turns a hypothesis into a freeze, then either confirms it (the
prediction resolves — what actually changed is left to reconcile()) or
thaws it (release everything, zero cost — this IS the mechanism that
makes a wrong interruption guess free, and the same one A8's pause/resume
reuses). Pure bookkeeping plus executor calls — never mutates state
directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from replan.depgraph import blast_radius
from replan.executor import Executor
from replan.schemas import ExecutionPlan, Hypothesis, Interruption

THRESHOLD = 0.55


@dataclass
class _Pending:
    hypothesis: Hypothesis
    task_ids: set[str]
    plan: ExecutionPlan


class FreezeController:
    def __init__(self, executor: Executor) -> None:
        self.executor = executor
        self.frozen: set[str] = set()
        self._pending: _Pending | None = None
        self.freezes = 0
        self.confirms = 0
        self.thaws = 0
        self.correct_predictions = 0

    def on_partial(self, hyp: Hypothesis, plan: ExecutionPlan) -> set[str]:
        """Freeze the blast radius of a REFINE/PIVOT hypothesis above
        THRESHOLD confidence. Anything else (including a hypothesis this
        controller doesn't recognize as replan-worthy) is a no-op."""
        if hyp.kind not in (Interruption.REFINE, Interruption.PIVOT) or hyp.confidence < THRESHOLD:
            return set()

        radius = blast_radius(plan, hyp.changed_paths)
        self.frozen |= radius
        self._pending = _Pending(hypothesis=hyp, task_ids=radius, plan=plan)
        self.freezes += 1
        if radius:
            self.executor.freeze(radius, plan)
        return radius

    def confirm(self, actual_paths: set[str], at: float) -> tuple[set[str], float | None]:
        """The utterance finished — record what actually changed against
        what was predicted. Does not itself decide which frozen tasks
        survive: that's reconcile()'s job, using the new state's
        fingerprints, which runs right after this in runtime.py."""
        self.confirms += 1
        if self._pending is None:
            return set(), None

        pending = self._pending
        self._pending = None
        self.frozen -= pending.task_ids

        lead_seconds = at - pending.hypothesis.at
        if pending.hypothesis.changed_paths & actual_paths:
            self.correct_predictions += 1
        return pending.task_ids, lead_seconds

    def thaw(self, at: float) -> set[str]:
        """False alarm — release the frozen tasks with zero cost: put them
        back to RUNNING and requeue any result that arrived while frozen so
        it reaches the gate normally on the next drain()."""
        self.thaws += 1
        if self._pending is None or not self._pending.task_ids:
            self._pending = None
            return set()

        pending = self._pending
        self._pending = None
        self.frozen -= pending.task_ids
        self.executor.thaw(pending.task_ids, pending.plan)
        self.executor.release_frozen(pending.plan)
        return pending.task_ids
