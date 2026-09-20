"""Manual verification script for B1 — not part of the core runtime, so it
lives outside replan/ and is free to use the real wall clock. Run by hand:

    python scripts/measure_barge_in.py

Plays a tone, speak into the mic partway through, and prints measured
latency from first voiced frame to playback.stop() returning.
"""

from __future__ import annotations

import asyncio
import time

import numpy as np

from replan.agents.audio import OUTPUT_RATE, AudioCapture, AudioPlayback, BargeInDetector


async def measure_barge_in_latency(seconds: float = 5.0) -> float:
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
