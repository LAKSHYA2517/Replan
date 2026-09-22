"""Versioned, append-only session state. Every mutation produces a new
immutable version; a no-op patch produces none — that's what gives the rest
of the system idempotence for free.
"""

from __future__ import annotations

from typing import Any

from replan.hashing import h
from replan.schemas import SessionState

_SECTIONS = ("slots", "constraints", "policy")


class StateStore:
    def __init__(self, initial: SessionState) -> None:
        initial = initial.model_copy(deep=True)
        initial.version = 0
        self._versions: list[SessionState] = [initial]
        self._checkpoints: dict[str, int] = {}

    @property
    def current(self) -> SessionState:
        return self._versions[-1]

    def at(self, version: int) -> SessionState:
        # list index == version number: apply()/restore() only ever assign
        # the next index as the new version, and history is never truncated.
        return self._versions[version]

    def apply(self, patch: dict[str, dict[str, Any]]) -> tuple[SessionState, set[str]]:
        base = self.current
        next_state = base.model_copy(deep=True)
        changed_paths: set[str] = set()

        for section in _SECTIONS:
            updates = patch.get(section)
            if not updates:
                continue
            current_section = getattr(base, section)
            next_section = getattr(next_state, section)
            for key, value in updates.items():
                if current_section.get(key) != value:
                    changed_paths.add(f"{section}.{key}")
                    next_section[key] = value

        if not changed_paths:
            return self.current, set()

        next_state.version = len(self._versions)
        self._versions.append(next_state)
        return next_state, changed_paths

    def checkpoint(self, name: str) -> int:
        version = self.current.version
        self._checkpoints[name] = version
        return version

    def restore(self, name: str) -> SessionState:
        version = self._checkpoints[name]
        restored = self.at(version).model_copy(deep=True)
        restored.version = len(self._versions)
        self._versions.append(restored)  # append, never truncate
        return restored

    def chain_hash(self) -> str:
        return h(*(v.model_dump() for v in self._versions))
