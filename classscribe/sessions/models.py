from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from classscribe import __version__


class Status(StrEnum):
    CREATED = "created"
    RECORDING = "recording"
    IMPORTING = "importing"
    RECORDED = "recorded"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"


TRANSITIONS = {
    Status.CREATED: {Status.RECORDING, Status.IMPORTING, Status.FAILED},
    Status.RECORDING: {Status.RECORDED, Status.FAILED},
    Status.IMPORTING: {Status.RECORDED, Status.FAILED},
    Status.RECORDED: {Status.TRANSCRIBING},
    Status.TRANSCRIBING: {Status.COMPLETED, Status.FAILED},
    Status.COMPLETED: {Status.TRANSCRIBING},
    Status.FAILED: {Status.TRANSCRIBING},
}


@dataclass
class Session:
    session_id: str
    title: str
    course: str
    created_at: str
    platform: str
    schema_version: int = 1
    application_version: str = __version__
    status: Status = Status.CREATED
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float = 0
    system_audio_device: dict[str, Any] | None = None
    microphone_device: dict[str, Any] | None = None
    system_audio_file: str = "system.wav"
    microphone_audio_file: str | None = None
    tracks: dict[str, Any] = field(default_factory=dict)
    recording_finalized: bool = False
    error: str | None = None
    transcription_runs: list[str] = field(default_factory=list)
    source_kind: str = "recording"
    source_url: str | None = None
    youtube: dict[str, Any] | None = None

    def transition(self, target: Status) -> None:
        if target not in TRANSITIONS[self.status]:
            raise ValueError(f"Invalid session transition: {self.status} -> {target}")
        self.status = target

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if value.get("schema_version") != 1:
            raise ValueError("Unsupported session schema")
        data = dict(value)
        identity = data.get("session_id", "")
        if not isinstance(identity, str) or UUID(identity).hex != identity:
            raise ValueError("Invalid session identity; expected a canonical UUID hex string")
        if data.get("source_kind", "recording") not in {"recording", "youtube"}:
            raise ValueError("Unsupported session source kind")
        data["status"] = Status(data["status"])
        return cls(**data)
