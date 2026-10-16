from collections.abc import Callable
from pathlib import Path

from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Session
from classscribe.transcription.progress import TranscriptionProgress


def transcribe(
    settings: Settings,
    directory: Path,
    session: Session,
    progress: Callable[[TranscriptionProgress], None] | None = None,
) -> Path:
    from classscribe.transcription.service import transcribe_session

    manager = SessionManager(settings.recordings_dir)
    if progress is None:
        return transcribe_session(manager, directory, session, settings)
    return transcribe_session(manager, directory, session, settings, progress=progress)
