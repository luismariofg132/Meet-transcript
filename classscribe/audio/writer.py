"""Bounded PCM disk writer with independently playable WAV parts."""

import os
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Any, BinaryIO

from classscribe.audio.devices import Device
from classscribe.audio.interfaces import AudioChunk


class TrackWriter:
    def __init__(
        self,
        directory: Path,
        device: Device,
        origin: float,
        *,
        max_part_bytes: int = 1024**3,
        queue_size: int = 128,
    ) -> None:
        self.directory = directory
        self.device = device
        self.origin = origin
        self.frame_bytes = 2 * device.channels
        self.max_part_frames = max_part_bytes // self.frame_bytes
        if self.max_part_frames < 1:
            raise ValueError("WAV part size must hold at least one frame")
        self.queue: queue.Queue[AudioChunk] = queue.Queue(maxsize=queue_size)
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.error: Exception | None = None
        self.parts: list[dict[str, Any]] = []
        self.offset: float | None = None
        self.frames = 0
        self.inserted_silence_frames = 0
        self.methods: set[str] = set()
        self.last_timing_error = 0.0
        self.raw: BinaryIO | None = None
        self.wav: wave.Wave_write | None = None
        self.last_sync = time.perf_counter()
        try:
            self._open_part()
        except Exception:
            self._close_part()
            raise
        self.thread = threading.Thread(target=self._run, name=f"write-{device.source}")
        self.thread.start()

    def _open_part(self) -> None:
        number = len(self.parts) + 1
        suffix = "" if number == 1 else f"-{number:04}"
        filename = f"{self.device.source}{suffix}.wav"
        self.raw = (self.directory / filename).open("xb")
        self.wav = wave.open(self.raw, "wb")
        self.wav.setparams((self.device.channels, 2, self.device.sample_rate, 0, "NONE", "PCM"))
        self.wav.writeframes(b"")
        self.parts.append({"file": filename, "start_frame": self.frames, "frames": 0})

    def _close_part(self) -> None:
        try:
            if self.wav is not None:
                self.wav.close()
        finally:
            if self.raw is not None:
                try:
                    self.raw.flush()
                    os.fsync(self.raw.fileno())
                finally:
                    self.raw.close()
            self.wav = None
            self.raw = None

    def receive(self, chunk: AudioChunk) -> bool:
        if self.error is not None or self.done.is_set():
            return False
        if chunk.status_flags:
            self.error = RuntimeError(f"PortAudio capture status flags: {chunk.status_flags}")
            return False
        try:
            self.queue.put_nowait(chunk)
            return True
        except queue.Full:
            self.error = RuntimeError(
                "Disk writer queue overflow; capture stopped to avoid silent loss"
            )
            return False

    def _write(self, data: bytes) -> None:
        remaining = memoryview(data)
        while remaining:
            if self.parts[-1]["frames"] == self.max_part_frames:
                self._close_part()
                self._open_part()
            frames = min(
                len(remaining) // self.frame_bytes,
                self.max_part_frames - self.parts[-1]["frames"],
            )
            size = frames * self.frame_bytes
            assert self.wav is not None and self.raw is not None
            # writeframes patches the RIFF sizes each time, limiting damage after a crash.
            self.wav.writeframes(remaining[:size])
            self.frames += frames
            self.parts[-1]["frames"] += frames
            remaining = remaining[size:]
            self.raw.flush()
            if time.perf_counter() - self.last_sync >= 1:
                os.fsync(self.raw.fileno())
                self.last_sync = time.perf_counter()

    def _consume(self, chunk: AudioChunk) -> None:
        if not chunk.data:
            return
        if len(chunk.data) % self.frame_bytes:
            raise ValueError("Incomplete PCM frame received")
        self.methods.add(chunk.timing_method)
        if self.offset is None:
            self.offset = max(0.0, chunk.captured_at - self.origin)
        expected = self.origin + self.offset + self.frames / self.device.sample_rate
        delta = chunk.captured_at - expected
        self.last_timing_error = delta
        # Some loopback endpoints stop sending data while playback is silent.
        # Preserve such gaps instead of pulling later speech earlier on the timeline.
        if delta > 0.1:
            missing = round(delta * self.device.sample_rate)
            self.inserted_silence_frames += missing
            while missing:
                count = min(missing, 4096)
                self._write(bytes(count * self.frame_bytes))
                missing -= count
        elif delta < -0.1:
            raise RuntimeError("Audio clock moved backwards by over 100 ms; inspect track timing")
        self._write(chunk.data)

    def _run(self) -> None:
        try:
            while not self.done.is_set() or not self.queue.empty():
                try:
                    chunk = self.queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                with self.lock:
                    self._consume(chunk)
        except Exception as exc:
            self.error = exc
        finally:
            try:
                self._close_part()
            except Exception as exc:
                self.error = self.error or exc

    def finish(self) -> None:
        self.done.set()
        self.thread.join()

    def metadata(self) -> dict[str, Any]:
        with self.lock:
            return {
                "sample_rate": self.device.sample_rate,
                "channels": self.device.channels,
                "sample_width_bytes": 2,
                "start_offset_seconds": self.offset,
                "frames": self.frames,
                "duration_seconds": self.frames / self.device.sample_rate,
                "parts": [dict(part) for part in self.parts],
                "timing_methods": sorted(self.methods),
                "last_timing_error_seconds": self.last_timing_error,
                "inserted_silence_frames": self.inserted_silence_frames,
                "alignment_guarantee": (
                    "approximate; independent hardware clocks; no drift resampling"
                ),
            }
