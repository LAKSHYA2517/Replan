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


def pending_reservation_ids(reservation_book) -> list[str]:
    """Adapter for FastPath's get_pending_reservation_ids over a real
    replan.tools.reservation.ReservationBook (C2) — unconfirmed held
    reservations only. A confirmed-but-not-yet-released reservation is no
    longer "pending"; nothing left to confirm on it."""
    return [rid for rid, r in reservation_book.held.items() if not r.confirmed]


def make_user_confirmed_emitter(recorder) -> Callable[[str], None]:
    """Adapter for FastPath's emit_user_confirmed. Logs USER_CONFIRMED
    only — never calls ReservationBook.confirm() directly. Per the
    two-phase design, this package only produces the event; the runtime
    consults may_confirm (fingerprint + policy + this event) and
    dispatches confirm_room itself."""

    def _emit(reservation_id: str) -> None:
        recorder.log(EventType.USER_CONFIRMED, reservation_id=reservation_id)

    return _emit


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
        get_pending_reservation_ids: Callable[[], list[str]] | None = None,
        emit_user_confirmed: Callable[[str], None] | None = None,
    ) -> None:
        self.freeze_controller = freeze_controller
        self.get_plan = get_plan
        self.speak = speak
        self.resume_playback = resume_playback
        self.answer_clarify = answer_clarify
        self._on_final = on_final
        self.recorder = recorder
        # B7 — both injected, defaulting to "nothing pending". Wire the
        # real thing with pending_reservation_ids(book) and
        # make_user_confirmed_emitter(recorder), defined below.
        self.get_pending_reservation_ids = get_pending_reservation_ids or (lambda: [])
        self.emit_user_confirmed = emit_user_confirmed or (lambda reservation_id: None)

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

        if hyp.kind is Interruption.CONFIRM:
            self._handle_confirm()
            return

        plan = self.get_plan()
        radius = self.freeze_controller.on_partial(hyp, plan)
        if radius:
            asyncio.create_task(self.speak(FILLER_TEXT))

    async def _answer_and_speak(self) -> None:
        answer = await self.answer_clarify()
        await self.speak(answer)

    def _handle_confirm(self) -> None:
        """A confirmation must apply to one named reservation, never to
        the session at large — if there's more than one pending, ask
        rather than guess, and emit nothing."""
        pending = self.get_pending_reservation_ids()
        if len(pending) == 1:
            self.emit_user_confirmed(pending[0])
        elif len(pending) > 1:
            asyncio.create_task(self.speak("Which reservation would you like me to confirm?"))
        # zero pending: nothing to confirm, silently no-op

    async def on_final(self, text: str, t: float):
        """T2. Hands off to the runtime's own on_final — this class owns
        none of the LLM/proposal/dispatch path."""
        return await self._on_final(text, t)
