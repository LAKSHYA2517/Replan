"""Policy implementations with the same public interface as Runtime."""

from __future__ import annotations

from replan.depgraph import fingerprint
from replan.executor import Executor
from replan.runtime import Policy, Runtime
from replan.schemas import CommitDecision, EventType, TaskStatus, Verdict


class _NaiveCommitter:
    """Accept every arrival and record when that acceptance was stale."""

    def __init__(self, store, recorder, understanding: dict) -> None:
        self._store = store
        self._recorder = recorder
        self._understanding = understanding
        self.cache: dict[str, dict] = {}
        self.ledger: list[CommitDecision] = []
        self.stale_commits = 0
        self.wrong_actions = 0

    def submit(self, result, plan) -> Verdict:
        task = plan.tasks.get(result.task_id)
        stale = task is None or result.dispatch_fp != fingerprint(task, self._store.current)
        if stale:
            self.stale_commits += 1
            self.wrong_actions += 1

        if task is not None:
            task.status = TaskStatus.DONE
        self._understanding.update(result.payload)
        reason = (
            "committed without a validity check; dispatch fingerprint was stale"
            if stale
            else "committed without a validity check"
        )
        event = self._recorder.log(
            EventType.VERDICT,
            call_id=result.call_id,
            task_id=result.task_id,
            verdict=Verdict.COMMIT.value,
            reason=reason,
            ok=result.ok,
            payload=result.payload,
            error=result.error,
        )
        self.ledger.append(
            CommitDecision(
                call_id=result.call_id,
                task_id=result.task_id,
                verdict=Verdict.COMMIT,
                reason=reason,
                t=event.t,
            )
        )
        return Verdict.COMMIT


class NaivePolicy(Runtime):
    """The standard agent loop, included as an honest comparison baseline.

    It uses the same planner, tools, latency, model and seed as RePlan. A final
    transcript updates its understanding and launches the resulting calls. It
    leaves in-flight work running and accepts every arrival without checking
    whether the result still matches the user's current request.
    """

    def __init__(self, clock, seed: int, tools: dict, llm=None, chaos="none", recorder=None) -> None:
        super().__init__(clock, seed, Policy.NAIVE, tools, llm, chaos, recorder)
        self.understanding: dict = {}
        self.gate = _NaiveCommitter(self.store, self.recorder, self.understanding)
        self.executor = Executor(
            tools, self.gate, self.store, clock, self.governor, self.recorder
        )
        self.freeze_controller = None

    def on_partial(self, text: str) -> None:
        if self.paused:
            self._deferred.append(("partial", text))

    def _refresh_metrics(self) -> None:
        super()._refresh_metrics()
        self.metrics.stale_commits = self.gate.stale_commits
        self.metrics.wrong_actions = self.gate.wrong_actions


class CancelAllPolicy(Runtime):
    """Correct baseline that cancels all running work and starts again."""

    def __init__(self, clock, seed: int, tools: dict, llm=None, chaos="none", recorder=None) -> None:
        super().__init__(clock, seed, Policy.CANCEL_ALL, tools, llm, chaos, recorder)


class RePlanPolicy(Runtime):
    """Dependency-aware policy delegated to Runtime's reconciler path."""

    def __init__(self, clock, seed: int, tools: dict, llm=None, chaos="none", recorder=None) -> None:
        super().__init__(clock, seed, Policy.REPLAN, tools, llm, chaos, recorder)
