"""SpeechAgent backed by freellmapi (OpenAI-compatible proxy at
FREELLMAPI_BASE_URL). One adapter covers STT + TTS; LLM proposal
extraction is layered on top separately (B4), not here.

/v1/audio/transcriptions is a batch endpoint, not a streaming one — there
is no rolling partial-transcript feed like faster-whisper would give.
Endpointing is therefore done locally: this module runs its own VAD over
incoming frames, emits a partial transcription every PARTIAL_WINDOW_MS of
continuous speech, and a final transcription after END_SILENCE_MS of
silence following speech. The barge-in path (replan/agents/audio.py) is
unaffected — it is driven by BargeInDetector, not by this module.

No wall-clock reads happen here — timestamps come from an injected
`clock` with a `.now() -> float` method, per AGENTS.md. Pass
replan.clock.RealClock() for live use, a VirtualClock or a stub for
tests.
"""

from __future__ import annotations

import asyncio
import io
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

import httpx
import webrtcvad

from replan.agents.audio import FRAME_MS, INPUT_RATE, OUTPUT_RATE
from replan.agents.base import SpeechAgent, Transcript

PARTIAL_WINDOW_MS = 700
END_SILENCE_MS = 600


class Clock(Protocol):
    def now(self) -> float: ...


class PlaybackSink(Protocol):
    def write(self, pcm: bytes) -> None: ...


class FreellmapiError(RuntimeError):
    """Raised on a malformed or unexpected response. Never silently degrade."""


@dataclass
class FreellmapiConfig:
    base_url: str
    api_key: str
    stt_model: str
    tts_model: str


def _build_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _pcm_from_wav(wav_bytes: bytes, expected_rate: int) -> bytes:
    buf = io.BytesIO(wav_bytes)
    try:
        w = wave.open(buf, "rb")
    except wave.Error as exc:
        raise FreellmapiError(
            f"TTS response is not a valid WAV file ({exc}). "
            "The configured TTS model likely returns a compressed format "
            "(mp3/opus) instead of PCM/WAV — pick a model that returns WAV."
        ) from exc
    if w.getnchannels() != 1 or w.getsampwidth() != 2:
        raise FreellmapiError(
            f"TTS response is {w.getnchannels()}ch/{w.getsampwidth() * 8}bit, "
            "expected mono 16-bit. Pick a different TTS model or add resampling."
        )
    if w.getframerate() != expected_rate:
        raise FreellmapiError(
            f"TTS response sample rate is {w.getframerate()}Hz, expected "
            f"{expected_rate}Hz. Pick a different TTS model or add resampling."
        )
    return w.readframes(w.getnframes())


@dataclass
class FreellmapiSpeechAgent(SpeechAgent):
    config: FreellmapiConfig
    clock: Clock
    playback: PlaybackSink | None = None
    vad_aggressiveness: int = 2

    _client: httpx.AsyncClient = field(init=False, repr=False)
    _vad: webrtcvad.Vad = field(init=False, repr=False)
    _queue: asyncio.Queue[Transcript] = field(default_factory=asyncio.Queue, init=False)
    _buffer: bytearray = field(default_factory=bytearray, init=False)
    _speech_started: bool = field(default=False, init=False)
    _voiced_ms_since_partial: int = field(default=0, init=False)
    _silence_run_ms: int = field(default=0, init=False)
    _context: list[dict] = field(default_factory=list, init=False)
    _tasks: set[asyncio.Task] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        self._client = httpx.AsyncClient(base_url=self.config.base_url, headers=headers, timeout=30.0)
        self._vad = webrtcvad.Vad(self.vad_aggressiveness)

    async def start_session(self) -> None:
        self._buffer.clear()
        self._speech_started = False
        self._voiced_ms_since_partial = 0
        self._silence_run_ms = 0

    async def send_audio(self, frame: bytes) -> None:
        is_speech = self._vad.is_speech(frame, INPUT_RATE)
        self._buffer.extend(frame)

        if is_speech:
            self._speech_started = True
            self._silence_run_ms = 0
            self._voiced_ms_since_partial += FRAME_MS
            if self._voiced_ms_since_partial >= PARTIAL_WINDOW_MS:
                self._voiced_ms_since_partial = 0
                self._spawn_transcribe(bytes(self._buffer), is_final=False)
        elif self._speech_started:
            self._silence_run_ms += FRAME_MS
            if self._silence_run_ms >= END_SILENCE_MS:
                pending = bytes(self._buffer)
                self._buffer.clear()
                self._speech_started = False
                self._voiced_ms_since_partial = 0
                self._silence_run_ms = 0
                self._spawn_transcribe(pending, is_final=True)

    def _spawn_transcribe(self, pcm: bytes, is_final: bool) -> None:
        task = asyncio.create_task(self._transcribe(pcm, is_final))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _transcribe(self, pcm: bytes, is_final: bool) -> None:
        wav_bytes = _build_wav(pcm, INPUT_RATE)
        try:
            resp = await self._client.post(
                "/audio/transcriptions",
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data={"model": self.config.stt_model},
            )
        except httpx.HTTPError as exc:
            raise FreellmapiError(f"STT request failed: {exc}") from exc
        if resp.status_code != 200:
            raise FreellmapiError(f"STT returned {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if "text" not in body:
            raise FreellmapiError(f"STT response missing 'text' field: {body}")
        await self._queue.put(Transcript(text=body["text"], is_final=is_final, t=self.clock.now()))

    async def transcripts(self) -> AsyncIterator[Transcript]:
        while True:
            yield await self._queue.get()

    async def send_context(self, results: list[dict]) -> None:
        self._context = results

    async def say(self, text: str) -> bytes:
        try:
            resp = await self._client.post(
                "/audio/speech",
                json={"model": self.config.tts_model, "input": text},
            )
        except httpx.HTTPError as exc:
            raise FreellmapiError(f"TTS request failed: {exc}") from exc
        if resp.status_code != 200:
            raise FreellmapiError(f"TTS returned {resp.status_code}: {resp.text[:300]}")
        pcm = _pcm_from_wav(resp.content, OUTPUT_RATE)
        if self.playback is not None:
            self.playback.write(pcm)
        return pcm

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self._client.aclose()
