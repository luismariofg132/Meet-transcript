from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from classscribe.audio.devices import Device, select_device
from classscribe.audio.interfaces import AudioBackend
from classscribe.audio.recorder import record_session
from classscribe.audio.wasapi import WasapiBackend
from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Session


@dataclass(frozen=True)
class RecordingResult:
    directory: Path
    session: Session


class RecordingService:
    def __init__(
        self,
        backend_factory: Callable[[], AudioBackend] = WasapiBackend,
        recorder: Callable[..., Session] = record_session,
    ) -> None:
        self.backend_factory = backend_factory
        self.recorder = recorder

    def devices(self) -> list[Device]:
        backend = self.backend_factory()
        try:
            return backend.devices()
        finally:
            backend.close()

    def record(
        self,
        settings: Settings,
        title: str,
        course: str = "",
        *,
        output_device: str | None = None,
        microphone_device: str | None = None,
        microphone: bool | None = None,
        prepared: Callable[[Path, Session, list[Device]], None] | None = None,
        progress: Callable[[float], None] = lambda _: None,
        stop_event: Event | None = None,
        levels: Callable[[float, float], None] | None = None,
        duration: float | None = None,
    ) -> RecordingResult:
        backend = self.backend_factory()
        manager = SessionManager(settings.recordings_dir)
        try:
            available = backend.devices()
            devices = [select_device(available, "system", output_device)]
            enabled = settings.microphone if microphone is None else microphone
            if microphone_device is not None:
                if microphone is False:
                    raise ValueError("--microphone-device cannot be combined with --no-microphone")
                enabled = True
            if enabled:
                devices.append(select_device(available, "microphone", microphone_device))
            directory, session = manager.create(title, course)
            if prepared:
                prepared(directory, session, devices)
            optional: dict[str, Any] = {}
            if stop_event is not None:
                optional["stop_event"] = stop_event
            if levels is not None:
                optional["levels"] = levels
            self.recorder(
                manager,
                directory,
                session,
                backend,
                devices,
                progress=progress,
                duration=duration,
                **optional,
            )
        finally:
            backend.close()
        return RecordingResult(directory, session)
