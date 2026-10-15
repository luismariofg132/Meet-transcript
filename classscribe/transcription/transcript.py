import math
from dataclasses import asdict, dataclass
from typing import Any

from classscribe.storage import timestamp


@dataclass(frozen=True)
class Segment:
    source: str
    start: float
    end: float
    text: str
    language: str
    audio_file: str
    audio_start: float
    audio_end: float

    def __post_init__(self) -> None:
        if self.source not in {"system", "microphone"}:
            raise ValueError("Unknown audio source")
        if not all(
            math.isfinite(v) for v in (self.start, self.end, self.audio_start, self.audio_end)
        ):
            raise ValueError("Non-finite segment timestamp")
        if (
            self.start < 0
            or self.end < self.start
            or self.audio_start < 0
            or self.audio_end < self.audio_start
        ):
            raise ValueError("Invalid segment interval")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def merge_segments(segments: list[Segment]) -> list[Segment]:
    return sorted(segments, key=lambda segment: (segment.start, segment.end, segment.source))


def markdown(transcript: dict[str, Any]) -> str:
    lines = [
        f"# {transcript['course'] or 'ClassScribe'}",
        f"## {transcript['title']}",
        "",
        f"Date: {transcript['started_at']}",
        f"Duration: {timestamp(transcript['duration_seconds'])}",
        f"Model: {transcript['model']}",
        f"Device: {transcript['device']} ({transcript['compute_type']})",
        "",
        "Automatic transcript; timestamps and recognition may be imperfect.",
        "CLASE = all system playback. YO = microphone; these are sources, not speaker identities.",
        "",
        "### Transcript",
        "",
    ]
    for segment in transcript["segments"]:
        label = "CLASE" if segment["source"] == "system" else "YO"
        lines.extend([f"[{timestamp(segment['start'])}] {label}", segment["text"], ""])
    if not transcript["segments"]:
        lines.append("No transcribable speech was detected.")
    return "\n".join(lines) + "\n"
