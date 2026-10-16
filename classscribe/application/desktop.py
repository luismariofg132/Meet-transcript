"""Small facade for desktop operations; every method is safe to run off the UI thread."""

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from classscribe.application.library import SessionLibrary
from classscribe.application.preferences import PreferenceStore
from classscribe.application.recording import RecordingService
from classscribe.application.transcription import transcribe
from classscribe.config import load_settings


class DesktopServices:
    def __init__(self, store: PreferenceStore, recording: RecordingService | None = None) -> None:
        self.store = store
        self.recording = recording or RecordingService()

    def discover(self) -> dict[str, Any]:
        try:
            return {"devices": [d.to_dict() for d in self.recording.devices()], "device_error": ""}
        except Exception as exc:
            return {"devices": [], "device_error": str(exc)}

    def initialize(self) -> dict[str, Any]:
        values = self.store.load()
        return {
            "preferences": values,
            **self.discover(),
            "sessions": self.library(values).list_sessions(),
        }

    def library(self, values: dict[str, Any]) -> SessionLibrary:
        return SessionLibrary(load_settings(None, values))

    def record(
        self,
        values: dict[str, Any],
        title: str,
        course: str,
        stop: Event,
        emit: Callable[[str, Any], None],
    ) -> dict[str, Any]:
        result = self.recording.record(
            load_settings(None, values),
            title,
            course,
            output_device=values.get("output_device") or None,
            microphone_device=(values.get("microphone_device") or None)
            if values["microphone"]
            else None,
            microphone=values["microphone"],
            stop_event=stop,
            prepared=lambda path, session, devices: emit(
                "prepared",
                {
                    "identity": session.session_id,
                    "directory": str(path.resolve()),
                    "title": title,
                    "course": course,
                    "microphone": len(devices) > 1,
                },
            ),
            progress=lambda elapsed: emit("elapsed", elapsed),
            levels=lambda system, mic: emit("levels", (system, mic)),
        )
        return self.library(values).detail(result.session.session_id)

    def transcribe(
        self, values: dict[str, Any], identity: str, emit: Callable[[str, Any], None]
    ) -> dict[str, Any]:
        library = self.library(values)
        directory, session = library.manager.find(identity)
        result = transcribe(
            load_settings(None, values),
            directory,
            session,
            progress=lambda value: emit("transcription", value),
        )
        return {**library.detail(identity), "result": str(result.resolve())}

    def diagnostics(self, values: dict[str, Any], inference: bool) -> dict[str, Any]:
        from classscribe.doctor import diagnose

        report, ok = diagnose(load_settings(None, values), inference=inference)
        # Read the existing cache only; do not import Whisper or fetch any weights here.
        cache = Path(values["models_dir"]) / f"models--Systran--faster-whisper-{values['model']}"
        cached = any(
            (path / "model.bin").is_file()
            and (path / "config.json").is_file()
            and (path / "tokenizer.json").is_file()
            for path in (cache / "snapshots").glob("*")
        )
        report["model_cache"] = (
            f"{values['model']}: cache files present (load not validated)"
            if cached
            else f"{values['model']}: no complete local cache found"
        )
        return {"report": report, "ok": ok}

    def transcript(self, values: dict[str, Any], path: str) -> list[dict[str, Any]]:
        return self.library(values).transcript(Path(path))
