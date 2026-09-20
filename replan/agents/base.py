"""Abstract SpeechAgent interface. Every speech backend conforms to this;
the runtime never knows which one is behind it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class Transcript:
    text: str
    is_final: bool
    t: float


class SpeechAgent(ABC):
    @abstractmethod
    async def start_session(self) -> None: ...

    @abstractmethod
    async def send_audio(self, frame: bytes) -> None: ...

    @abstractmethod
    def transcripts(self) -> AsyncIterator[Transcript]: ...

    @abstractmethod
    async def send_context(self, results: list[dict]) -> None: ...

    @abstractmethod
    async def say(self, text: str) -> bytes:
        """Synthesize speech for text. Returns raw PCM bytes at the output
        contract rate (24kHz mono s16le) and, if a playback sink was given
        at construction, also writes them there."""
        ...

    @abstractmethod
    async def close(self) -> None: ...
