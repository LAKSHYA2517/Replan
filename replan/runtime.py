"""The orchestrator. The only module permitted to import from every other
module — everyone else asks A for a wiring line rather than editing this
file directly.

Several genuine gaps in the spec are resolved here, flagged inline and in
the accompanying summary rather than silently invented:
  - no package anywhere builds an ExecutionPlan from a SessionState (a
    "planner"); see build_plan below.
  - task ids must stay stable across plan versions (one task per tool, id
    == tool name) or reconcile()'s adoption breaks the gate's task_id
    lookup on late results — a real cross-package bug this file surfaces.
  - B5 (hypothesis.py) and B6 (freeze.py) don't exist on main yet; both are
    imported defensively so this module — and Runtime construction itself
    — still works today, with on_partial's predictive path a documented
    no-op until they land.
"""

from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from replan.agents.proposals import CacheMiss, LLMCache, extract_proposal
from replan.commit import CommitGate
from replan.executor import BudgetGovernor, Executor, SpeculationRefused
from replan.reconcile import Reconciliation, reconcile
from replan.recorder import Recorder
from replan.schemas import EventType, ExecutionPlan, PlanTask, Proposal, SessionState, TaskStatus, Verdict
from replan.state import StateStore
from replan.tools.registry import TOOL_SPECS

try:
    from replan.hypothesis import hypothesise  # B5 — not built yet
except ImportError:
    hypothesise = None

try:
    from replan.freeze import FreezeController  # B6 — not built yet
except ImportError:
    FreezeController = None


class Policy(str, Enum):
    NAIVE = "naive"
    CANCEL_ALL = "cancel_all"
    REPLAN = "replan"


@dataclass
class Metrics:
    stale_commits: int = 0
    wrong_actions: int = 0  # always 0 here by construction: the commit gate
    # protects every policy identically. Nonzero only in a SEPARATE,
    # deliberately non-gated baseline (C6's NaivePolicy) — comparing
    # against that is the point of the metric, not something this class
    # can ever show nonzero for its own commits.
    dangling_effects: int = 0
    reuse_ratio: float = 0.0
    tool_calls: int = 0
    wasted_tool_seconds: float = 0.0  # not yet computed — needs per-call cost
    # tracked alongside hit/miss outcome, which BudgetGovernor's window
    # doesn't currently carry. Flagged, not faked.
    speculation_hit_rate: float = 0.0
    freeze_lead_time: float | None = None  # needs FreezeController (B6)
    cancellation_latency: float | None = None  # needs a CANCEL event (gap #1)
    time_to_first_valid_result: float | None = None
    trace_coverage: float = 0.0


class Runtime:
    def __init__(self, clock, seed: int, policy: Policy, tools: dict,
                 llm=None, chaos: str = "none", recorder=None) -> None:
        self.clock = clock
        self.policy = policy
        self.rng = random.Random(seed)
        self.llm = llm
        self.chaos = chaos  # stub: real chaos-wrapping needs C5 (replan/tools/chaos.py), not built yet

        self.store = StateStore(SessionState())
        self.recorder = recorder if recorder is not None else Recorder(clock, self.store)
        self.gate = CommitGate(self.store, self.recorder)
        self.governor = BudgetGovernor(max_concurrent=5, max_cost_per_turn=10.0, hit_rate_floor=0.3)
        self.executor = Executor(tools, self.gate, self.store, clock, self.governor, self.recorder)
        self.freeze_controller = FreezeController(self.executor) if FreezeController is not None else None

        cache_path = Path(os.environ.get("REPLAN_LLM_CACHE", "tests/fixtures/llm_cache.json"))
        cache_mode = os.environ.get("REPLAN_LLM_MODE", "replay")
        self._llm_cache = LLMCache(cache_path, cache_mode)

        self.plan = ExecutionPlan(id="plan-v0", tasks={})
        self.paused = False
        self._deferred: list[tuple[str, str]] = []  # (method, text), queued while paused
        self._paused_task_ids: set[str] = set()
        self._pending_compensations: set[str] = set()  # task ids of unfinished compensators
        self._last_reconciliation: Reconciliation | None = None
        self.metrics = Metrics()

        # No package builds ExecutionPlans from SessionState anywhere in the
        # brief — a genuine gap, not assigned to A/B/C/D. Default is a safe
        # no-op (dispatches nothing) rather than a guess at real tool
        # arg_specs. Override post-construction: runtime.build_plan = ...
        self.build_plan = self._default_build_plan

    def _default_build_plan(self, state: SessionState) -> ExecutionPlan:
        return ExecutionPlan(id=f"plan-v{state.version}", tasks={})

    # ------------------------------------------------------------------
    # public interface — identical under all three policies
    # ------------------------------------------------------------------

    def on_partial(self, text: str) -> None:
        if self.paused:
            self._deferred.append(("partial", text))
            return  # NOTE: "log that it was deferred" needs an EventType that
            # doesn't exist (same gap as Executor.cancel() — see A4 summary)
        if hypothesise is None or self.freeze_controller is None:
            return  # B5/B6 not available yet
        hyp = hypothesise(text, self.clock.now())
        if hyp is not None:
            self.freeze_controller.on_partial(hyp, self.plan)

    async def on_final(self, text: str) -> list[Verdict]:
        if self.paused:
            self._deferred.append(("final", text))
            return []
        proposal = await self._get_proposal(text)
        return await self.apply_proposal_and_dispatch(proposal)

    def on_proposal(self, proposal: Proposal) -> tuple[SessionState, set[str]]:
        if proposal.kind != "state_patch" or not proposal.patch:
            return self.store.current, set()
        return self._apply_patch(proposal)

    async def apply_proposal_and_dispatch(self, proposal: Proposal) -> list[Verdict]:
        """Shared by on_final (live, text -> LLM -> proposal) and replay
        (recorded, STATE_PATCH event -> proposal directly, no LLM call) so
        the two paths can never diverge in how they plan/dispatch/reconcile."""
        new_state, changed_paths = self._apply_patch(proposal)
        old_plan = self.plan
        new_plan = self.build_plan(new_state)

        if self.policy is Policy.NAIVE:
            self._dispatch_tasks(list(new_plan.tasks.values()), new_plan)
        elif self.policy is Policy.CANCEL_ALL:
            for task in old_plan.tasks.values():
                if task.status in (TaskStatus.RUNNING, TaskStatus.FROZEN):
                    self.executor.cancel(task)
            self._dispatch_tasks(list(new_plan.tasks.values()), new_plan)
        else:  # REPLAN
            if self.freeze_controller is not None:
                self.freeze_controller.confirm(changed_paths, self.clock.now())
            r = reconcile(old_plan, new_plan, new_state, self.gate.cache)
            self._last_reconciliation = r
            for task in r.invalidated:
                self.executor.cancel(task)
            for task in r.compensate:
                self._fire_compensator(task, new_plan)
            self._dispatch_tasks(r.added, new_plan)

        self.plan = new_plan
        # let every just-dispatched asyncio.Task actually run (a freshly
        # created task hasn't executed a single line yet — only scheduled)
        # before we drain, or this turn's results simply aren't there yet.
        await self.clock.run_until_idle()
        verdicts = self.tick()
        return verdicts

    def _apply_patch(self, proposal: Proposal) -> tuple[SessionState, set[str]]:
        new_state, changed_paths = self.store.apply(proposal.patch)
        if changed_paths:
            self.recorder.log(
                EventType.STATE_PATCH,
                patch=proposal.patch, changed_paths=sorted(changed_paths),
                version=new_state.version, chain_hash=self.store.chain_hash(),
            )
        return new_state, changed_paths

    def tick(self) -> list[Verdict]:
        verdicts = self.executor.drain(self.plan)
        self._refresh_metrics()
        return verdicts

    def checkpoint(self, name: str) -> int:
        version = self.store.checkpoint(name)
        self.recorder.log(EventType.CHECKPOINT, name=name, version=version)
        return version

    def restore(self, name: str) -> SessionState:
        state = self.store.restore(name)
        self.recorder.log(EventType.RESTORE, name=name, version=state.version)
        return state

    def pause(self) -> None:
        self._paused_task_ids = {
            task.id for task in self.plan.tasks.values()
            if task.status is TaskStatus.RUNNING
        }
        checkpoint = f"auto-pause-{self.store.current.version}"
        self.checkpoint(checkpoint)
        self.executor.freeze(self._paused_task_ids, self.plan)
        self.paused = True
        self.recorder.log(
            EventType.PAUSE,
            checkpoint=checkpoint,
            task_ids=sorted(self._paused_task_ids),
        )

    def resume(self) -> None:
        task_ids = set(self._paused_task_ids)
        self.executor.thaw(task_ids, self.plan)
        self.executor.release_frozen(self.plan)
        self._paused_task_ids.clear()
        self.paused = False
        self.recorder.log(EventType.RESUME, task_ids=sorted(task_ids))

        deferred, self._deferred = self._deferred, []
        if deferred:
            async def drain_deferred() -> None:
                for method, text in deferred:
                    if method == "partial":
                        self.on_partial(text)
                    else:
                        await self.on_final(text)

            asyncio.create_task(drain_deferred())

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    async def _get_proposal(self, text: str) -> Proposal:
        try:
            return await extract_proposal(text, self.store.current, self.llm, self._llm_cache)
        except CacheMiss:
            raise  # visible failure: a demo run should never hit an uncached prompt

    def _dispatch_tasks(self, tasks: list[PlanTask], plan: ExecutionPlan) -> None:
        for task in tasks:
            try:
                self.executor.dispatch(task, plan)
            except SpeculationRefused:
                pass  # tool is IRREVERSIBLE; nothing more to do with this task here

    def _fire_compensator(self, task: PlanTask, plan: ExecutionPlan) -> None:
        compensator_name = TOOL_SPECS.get(task.tool, {}).get("compensator")
        if not compensator_name:
            return
        landed_payload = self.gate.cache.get(task.dispatch_fp, {})
        comp_task = PlanTask(id=f"compensate-{task.id}", tool=compensator_name, arg_spec=dict(landed_payload))
        plan.tasks[comp_task.id] = comp_task
        self.recorder.log(EventType.COMPENSATING, task_id=task.id, compensator=compensator_name)
        self._pending_compensations.add(comp_task.id)
        try:
            call_id = self.executor.dispatch(comp_task, plan)
            if call_id is None and comp_task.status is TaskStatus.DONE:
                self._pending_compensations.discard(comp_task.id)
        except SpeculationRefused:
            pass

    def _refresh_metrics(self) -> None:
        ledger = self.gate.ledger
        self.metrics.stale_commits = sum(1 for d in ledger if d.verdict is Verdict.STALE)
        self.metrics.tool_calls = sum(1 for e in self.recorder.events if e.type is EventType.TASK_DISPATCH)
        self.metrics.speculation_hit_rate = self.governor.hit_rate
        self.metrics.trace_coverage = 1.0 if self.recorder.verify_chain() else 0.0
        if self._last_reconciliation is not None:
            self.metrics.reuse_ratio = self._last_reconciliation.reuse_ratio
        commits = [d for d in ledger if d.verdict is Verdict.COMMIT]
        if commits and self.metrics.time_to_first_valid_result is None:
            self.metrics.time_to_first_valid_result = commits[0].t
        for decision in ledger:
            if decision.verdict is Verdict.COMMIT:
                self._pending_compensations.discard(decision.task_id)
        self.metrics.dangling_effects = len(self._pending_compensations)
