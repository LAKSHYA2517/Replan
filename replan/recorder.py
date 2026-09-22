"""Append-only, hash-chained event log. Every entry links to its
predecessor, so any tampering or gap is detectable via verify_chain().
"""

from __future__ import annotations

from replan.hashing import h
from replan.schemas import Event, EventType


class Recorder:
    def __init__(self, clock, store) -> None:
        self._clock = clock
        self._store = store
        self._seq = 0
        self._prev_hash = ""
        self.events: list[Event] = []

    def log(self, event_type: EventType, **payload) -> Event:
        self._seq += 1
        draft = Event(
            seq=self._seq,
            t=self._clock.now(),
            state_version=self._store.current.version,
            type=event_type,
            payload=payload,
            prev_hash=self._prev_hash,
            hash="",
        )
        # hash over the same dump verify_chain() will recompute from, so the
        # two can never drift apart by construction.
        event_hash = h(self._prev_hash, draft.model_dump(exclude={"hash"}))
        event = draft.model_copy(update={"hash": event_hash})
        self._prev_hash = event_hash
        self.events.append(event)
        return event

    def to_jsonl(self, path: str) -> None:
        with open(path, "w") as f:
            for event in self.events:
                f.write(event.model_dump_json())
                f.write("\n")

    def from_jsonl(self, path: str) -> None:
        with open(path) as f:
            events = [Event.model_validate_json(line) for line in f if line.strip()]
        self.events = events
        self._seq = events[-1].seq if events else 0
        self._prev_hash = events[-1].hash if events else ""

    def verify_chain(self) -> bool:
        prev_hash = ""
        for i, event in enumerate(self.events, start=1):
            if event.seq != i:
                return False  # gapless check
            if event.prev_hash != prev_hash:
                return False
            if h(prev_hash, event.model_dump(exclude={"hash"})) != event.hash:
                return False
            prev_hash = event.hash
        return True
