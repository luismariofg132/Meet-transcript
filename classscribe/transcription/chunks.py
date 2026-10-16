"""Bounded temporary audio windows; never decode a multi-hour track at once."""

import math
import wave
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

TRANSCRIPTION_WINDOW_SECONDS = 300
TRANSCRIPTION_OVERLAP_SECONDS = 15
COPY_BLOCK_SECONDS = 5


@dataclass(frozen=True)
class AudioWindow:
    """All bounds are seconds into the original WAV part, not the temporary file.

    Ownership is [keep_start, keep_end), except the final audio endpoint is included.
    The remaining left/right regions are inference context only. The temporary path
    is reused by the iterator: consume this window before requesting the next one.
    """

    path: Path
    start: float
    end: float
    keep_start: float
    keep_end: float
    is_last: bool

    @property
    def duration(self) -> float:
        return self.end - self.start

    def owns(self, absolute_start: float, absolute_end: float) -> bool:
        midpoint = (absolute_start + absolute_end) / 2
        return self.keep_start <= midpoint and (
            midpoint < self.keep_end or (self.is_last and midpoint == self.keep_end)
        )


def chunking_metadata() -> dict[str, int | str]:
    return {
        "window_seconds": TRANSCRIPTION_WINDOW_SECONDS,
        "overlap_seconds": TRANSCRIPTION_OVERLAP_SECONDS,
        "deduplication": "midpoint_ownership",
    }


def audio_chunks(
    path: Path,
    work_dir: Path,
    seconds: float = TRANSCRIPTION_WINDOW_SECONDS,
    overlap_seconds: float = TRANSCRIPTION_OVERLAP_SECONDS,
) -> Iterator[AudioWindow]:
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Window duration must be finite and positive")
    if not math.isfinite(overlap_seconds) or not 0 <= overlap_seconds < seconds:
        raise ValueError("Overlap must satisfy 0 <= overlap < window duration")
    with (
        wave.open(str(path), "rb") as source,
        TemporaryDirectory(prefix="audio-", dir=work_dir) as tmp,
    ):
        rate = source.getframerate()
        if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise ValueError("Expected PCM16 WAV recording")
        total = source.getnframes()
        window_frames = round(seconds * rate)
        overlap_frames = round(overlap_seconds * rate)
        if window_frames < 1 or not 0 <= overlap_frames < window_frames:
            raise ValueError("Window and overlap must remain valid at the WAV sample rate")
        stride = window_frames - overlap_frames
        start = 0
        chunk = Path(tmp) / "chunk.wav"
        while start < total:
            end = min(start + window_frames, total)
            is_last = end == total
            # Adjacent windows split their overlap at its midpoint. Computing in
            # frames avoids cumulative drift; half-frame boundaries are allowed.
            keep_start = 0.0 if start == 0 else (start + overlap_frames / 2) / rate
            keep_end = end / rate if is_last else (end - overlap_frames / 2) / rate
            remaining = end - start
            source.setpos(start)
            with wave.open(str(chunk), "wb") as output:
                output.setparams(source.getparams())
                while remaining:
                    count = min(remaining, COPY_BLOCK_SECONDS * rate)
                    data = source.readframes(count)
                    actual = len(data) // (source.getnchannels() * source.getsampwidth())
                    if actual != count:
                        raise ValueError(
                            "WAV data is truncated; original recording has been preserved"
                        )
                    output.writeframes(data)
                    remaining -= actual
            yield AudioWindow(chunk, start / rate, end / rate, keep_start, keep_end, is_last)
            if is_last:
                break  # No extra decode of an overlap already covered through EOF.
            start += stride
