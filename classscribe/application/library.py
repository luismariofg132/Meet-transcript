"""Read-only session/run discovery and structured transcript loading."""

import json
import logging
from pathlib import Path
from typing import Any

from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager
from classscribe.storage import timestamp

logger = logging.getLogger(__name__)


class SessionLibrary:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = SessionManager(settings.recordings_dir)

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = []
        for path in self.settings.recordings_dir.glob("*/session.json"):
            try:
                session = self.manager.load(path.parent)
                rows.append(self.summary(path.parent, session.to_dict()))
            except (OSError, ValueError, TypeError, KeyError):
                logger.warning("Skipping invalid session metadata")
        return sorted(rows, key=lambda row: row["date"], reverse=True)

    def summary(self, directory: Path, data: dict[str, Any]) -> dict[str, Any]:
        runs = self.runs(data["session_id"])
        return {
            "identity": data["session_id"],
            "title": data["title"],
            "course": data["course"],
            "date": data["started_at"] or data["created_at"],
            "duration": timestamp(data["duration_seconds"]),
            "status": data["status"],
            "recorded": data["recording_finalized"],
            "transcribed": any(row["ready"] for row in runs),
            "directory": str(directory.resolve()),
            "microphone": data["microphone_audio_file"] is not None,
            "system_audio": (directory / data["system_audio_file"]).is_file(),
        }

    def detail(self, identity: str) -> dict[str, Any]:
        directory, session = self.manager.find(identity)
        return {"session": self.summary(directory, session.to_dict()), "runs": self.runs(identity)}

    def runs(self, identity: str) -> list[dict[str, Any]]:
        rows = []
        for path in (self.settings.transcripts_dir / identity).glob("*/run.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                result = path.parent / "result"
                rows.append(
                    {
                        "identity": path.parent.name,
                        "model": data["model"],
                        "device": data.get("device", data.get("requested_device", "auto")),
                        "date": data["started_at"],
                        "status": data["status"],
                        "ready": (result / "transcript.json").is_file(),
                        "directory": str(result.resolve()),
                    }
                )
            except (OSError, ValueError, KeyError, TypeError):
                logger.warning("Skipping invalid transcription run metadata")
        return sorted(rows, key=lambda row: row["date"], reverse=True)

    def transcript(self, directory: Path) -> list[dict[str, Any]]:
        root = self.settings.transcripts_dir.resolve()
        directory = directory.resolve()
        if not directory.is_relative_to(root):
            raise ValueError("Transcript must be inside the configured transcripts directory")
        data = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported transcript schema")
        return [
            {
                **segment,
                "speaker": "CLASS" if segment["source"] == "system" else "ME",
                "time": timestamp(segment["start"]),
            }
            for segment in data["segments"]
        ]
