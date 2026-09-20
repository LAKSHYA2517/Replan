"""Audio I/O, local VAD, and dual-trigger barge-in.

Owned by B. This module produces signals only — no state, no commit gate,
no executor. See AGENTS.md file-ownership table.

Barge-in must fire on whichever comes first: the local VAD detecting speech
while playback is active, or the provider's own interruption signal (fed in
via on_provider_interrupt). Relying on the provider alone is unsafe — some
realtime APIs do not reliably report an interruption if the user is already
speaking as the model's turn begins, which is exactly the scenario this
project's demo depends on.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import sounddevice as sd
import webrtcvad

INPUT_RATE = 16_000
OUTPUT_RATE = 24_000
FRAME_MS = 20
INPUT_FRAME_SAMPLES = INPUT_RATE * FRAME_MS // 1000  # 320 samples @ 16kHz/20ms


class AudioCapture:
    """Opens the default microphone, emits 20ms frames of 16kHz mono int16 PCM."""

    def __init__(self, queue: asyncio.Queue[bytes] | None = None) -> None:
        self.queue: asyncio.Queue[bytes] = queue or asyncio.Queue()
        self._stream: sd.RawInputStream | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        # Runs on PortAudio's own thread. Never touch asyncio state directly here
        # except via call_soon_threadsafe.
        if self._loop is None:
            return
        pcm = bytes(indata)
        self._loop.call_soon_threadsafe(self.queue.put_nowait, pcm)

    def start(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._stream = sd.RawInputStream(
            samplerate=INPUT_RATE,
            blocksize=INPUT_FRAME_SAMPLES,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    async def frames(self):
        while True:
            yield await self.queue.get()


class AudioPlayback:
    """Plays 24kHz mono int16 PCM. stop() flushes queued audio within ~50ms."""

    def __init__(self) -> None:
        self._stream: sd.RawOutputStream | None = None
        self._buffer = bytearray()
        self._active = False

    def start(self) -> None:
        self._stream = sd.RawOutputStream(
            samplerate=OUTPUT_RATE,
            channels=1,
            dtype="int16",
        )
        self._stream.start()
        self._active = True

    def write(self, pcm: bytes) -> None:
        if self._stream is not None and self._active:
            self._stream.write(pcm)

    def stop(self) -> None:
        """Flush queued audio immediately. Must return in well under 50ms."""
        self._active = False
        if self._stream is not None:
            self._stream.abort()  # abort() drops the buffer; stop() would drain it
            self._stream.close()
            self._stream = None

    @property
    def is_active(self) -> bool:
        return self._active


@dataclass
class BargeInDetector:
    """Wraps webrtcvad. Fires on the first voiced frame after prefix_padding_ms
    of speech while playback is active, from either the local VAD or the
    provider's own interruption signal — whichever comes first.
    """

    on_barge_in: Callable[[float], None]
    aggressiveness: int = 2
    prefix_padding_ms: int = 120
    playback_active: bool = False

    _vad: webrtcvad.Vad = field(init=False, repr=False)
    _voiced_run_ms: int = field(default=0, init=False)
    _fired_this_turn: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._vad = webrtcvad.Vad(self.aggressiveness)

    def reset_turn(self) -> None:
        """Call when a new playback turn starts, so barge-in can fire again."""
        self._fired_this_turn = False
        self._voiced_run_ms = 0

    def _fire(self, at: float) -> None:
        if self._fired_this_turn:
            return
        self._fired_this_turn = True
        self.on_barge_in(at)

    def feed(self, frame: bytes, at: float) -> None:
        """Feed one 20ms 16kHz mono int16 PCM frame from the local mic."""
        if not self.playback_active or self._fired_this_turn:
            self._voiced_run_ms = 0
            return
        is_speech = self._vad.is_speech(frame, INPUT_RATE)
        if is_speech:
            self._voiced_run_ms += FRAME_MS
            if self._voiced_run_ms >= self.prefix_padding_ms:
                self._fire(at)
        else:
            self._voiced_run_ms = 0

    def on_provider_interrupt(self, at: float) -> None:
        """Call when the provider's own signal (e.g. server_content.interrupted)
        reports an interruption. Idempotent with the local VAD path.
        """
        if not self.playback_active:
            return
        self._fire(at)


async def measure_barge_in_latency(seconds: float = 5.0) -> float:
    """Manual verification script: play a tone, speak into the mic partway
    through, and report measured latency from first voiced frame to
    playback.stop() returning. Run this by hand, not in CI.
    """
    playback = AudioPlayback()
    capture = AudioCapture()

    latency: dict[str, float] = {}

    def _on_barge_in(at: float) -> None:
        t0 = time.perf_counter()
        playback.stop()
        latency["stop_latency_s"] = time.perf_counter() - t0
        latency["detected_at"] = at

    detector = BargeInDetector(on_barge_in=_on_barge_in)
    detector.playback_active = True

    tone = (np.sin(2 * np.pi * 440 * np.arange(int(OUTPUT_RATE * seconds)) / OUTPUT_RATE) * 8000).astype(np.int16)
    playback.start()
    capture.start()

    async def play_tone():
        chunk = OUTPUT_RATE // 10
        for i in range(0, len(tone), chunk):
            if not playback.is_active:
                return
            playback.write(tone[i : i + chunk].tobytes())
            await asyncio.sleep(0.1)

    async def listen():
        async for frame in capture.frames():
            detector.feed(frame, time.perf_counter())
            if latency:
                return

    play_task = asyncio.create_task(play_tone())
    listen_task = asyncio.create_task(listen())
    await asyncio.wait([play_task, listen_task], timeout=seconds + 1)

    capture.stop()
    if playback.is_active:
        playback.stop()

    return latency.get("stop_latency_s", float("nan"))


if __name__ == "__main__":
    result = asyncio.run(measure_barge_in_latency())
    print(f"measured barge-in stop latency: {result * 1000:.1f} ms")
