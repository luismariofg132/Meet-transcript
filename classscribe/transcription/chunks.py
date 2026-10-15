"""Bounded temporary audio windows; never decode a multi-hour track at once."""

import wave
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory


def audio_chunks(
    path: Path, work_dir: Path, seconds: int = 300
) -> Iterator[tuple[Path, float, float]]:
    if seconds < 1:
        raise ValueError("Chunk duration must be positive")
    with (
        wave.open(str(path), "rb") as source,
        TemporaryDirectory(prefix="audio-", dir=work_dir) as tmp,
    ):
        rate = source.getframerate()
        if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise ValueError("Expected PCM16 WAV recording")
        total = source.getnframes()
        start = 0
        chunk = Path(tmp) / "chunk.wav"
        while start < total:
            frames = min(seconds * rate, total - start)
            remaining = frames
            with wave.open(str(chunk), "wb") as output:
                output.setparams(source.getparams())
                while remaining:
                    count = min(remaining, 5 * rate)
                    data = source.readframes(count)
                    actual = len(data) // (source.getnchannels() * source.getsampwidth())
                    if actual != count:
                        raise ValueError(
                            "WAV data is truncated; original recording has been preserved"
                        )
                    output.writeframes(data)
                    remaining -= actual
            yield chunk, start / rate, frames / rate
            start += frames
