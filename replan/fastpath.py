"""Three-tier latency response to a live utterance:

  T0 (<50ms)   audio already stopped by the VAD/provider signal itself
               (see replan/agents/audio.py BargeInDetector) — this tier
               just records that it happened. Signal processing, not a
               decision.
  T1 (<150ms)  classify the partial (replan.hypothesis, pure regex) and
               branch: BACKCHANNEL resumes playback, CLARIFY answers from
               committed state with no replan, PIVOT/REFINE freezes the
               blast radius and emits a filler while T2 runs.
  T2 (1-2s)    the full LLM path — handled by on_final, not here.

Everything this needs (playback control, the speech agent, how to answer
a clarification, what "on_final" does) is injected, so this stays
testable with stub callables — no mic, no network, no real Runtime
required.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from replan.freeze import FreezeController
from replan.hypothesis import hypothesise
from replan.schemas import EventType, ExecutionPlan, Interruption

FILLER_TEXT = "got it—"


class FastPath:
    def __init__(
        self,
        freeze_controller: FreezeController,
        get_plan: Callable[[], ExecutionPlan],
        speak: Callable[[str], Awaitable[None]],
        resume_playback: Callable[[], None],
        answer_clarify: Callable[[], Awaitable[str]],
        on_final: Callable[[str, float], Awaitable[object]],
        recorder=None,
    ) -> None:
        self.freeze_controller = freeze_controller
        self.get_plan = get_plan
        self.speak = speak
        self.resume_playback = resume_playback
        self.answer_clarify = answer_clarify
        self._on_final = on_final
        self.recorder = recorder

    def on_interrupt_signal(self, t: float) -> None:
        """T0. No classification, no decision — audio is already stopped
        by the time this fires."""
        if self.recorder is not None:
            self.recorder.log(EventType.BARGE_IN, t=t)

    def on_partial(self, text: str, t: float) -> None:
        """T1. Synchronous and fast: hypothesise() is pure regex, and
        FreezeController.on_partial only calls into the executor's status
        flips — no network here. Speaking (filler or clarify answer) is
        fired as a background task so this call itself stays instant."""
        hyp = hypothesise(text, t)
        if hyp is None:
            return

        if hyp.kind is Interruption.BACKCHANNEL:
            self.resume_playback()
            return

        if hyp.kind is Interruption.CLARIFY:
            asyncio.create_task(self._answer_and_speak())
            return

        plan = self.get_plan()
        radius = self.freeze_controller.on_partial(hyp, plan)
        if radius:
            asyncio.create_task(self.speak(FILLER_TEXT))

    async def _answer_and_speak(self) -> None:
        answer = await self.answer_clarify()
        await self.speak(answer)

    async def on_final(self, text: str, t: float):
        """T2. Hands off to the runtime's own on_final — this class owns
        none of the LLM/proposal/dispatch path."""
        return await self._on_final(text, t)
