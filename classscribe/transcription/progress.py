"""Presentation-independent progress: completed ownership time, not a time estimate."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionProgress:
    stage: str
    processed_seconds: float
    total_seconds: float
    source: str = ""
    current_audio_file: str = ""
    device: str = ""

    @property
    def progress(self) -> float | None:
        if self.stage == "completed":
            return 1.0
        if self.stage != "transcribing" or self.total_seconds <= 0:
            return None
        return min(1.0, self.processed_seconds / self.total_seconds)
