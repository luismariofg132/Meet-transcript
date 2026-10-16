"""Application service for YouTube metadata inspection and session import."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Session
from classscribe.storage import timestamp
from classscribe.youtube import (
    YouTubeClient,
    YouTubeImportProgress,
    YouTubeMetadata,
    YtDlpClient,
    import_youtube_session,
)


@dataclass(frozen=True)
class YouTubeImportResult:
    directory: Path
    session: Session
    metadata: YouTubeMetadata


class YouTubeService:
    def __init__(
        self,
        client_factory: Callable[[], YouTubeClient] = YtDlpClient,
        importer: Callable[..., tuple[Path, Session]] = import_youtube_session,
    ) -> None:
        self.client_factory = client_factory
        self.importer = importer

    def inspect(self, settings: Settings, url: str) -> YouTubeMetadata:
        if settings.offline:
            raise RuntimeError(
                "YouTube inspection is unavailable in offline mode. Disable offline mode first."
            )
        return self.client_factory().inspect(url)

    def inspect_dict(self, settings: Settings, url: str) -> dict[str, Any]:
        meta = self.inspect(settings, url)
        return {
            **meta.to_dict(),
            "duration": timestamp(meta.duration_seconds),
        }

    def import_session(
        self,
        settings: Settings,
        url: str,
        title: str = "",
        course: str = "",
        *,
        prepared: Callable[[Path, Session, YouTubeMetadata], None] | None = None,
        progress: Callable[[YouTubeImportProgress], None] | None = None,
    ) -> YouTubeImportResult:
        if settings.offline:
            raise RuntimeError(
                "YouTube import is unavailable in offline mode. Disable offline mode first."
            )
        client = self.client_factory()
        manager = SessionManager(settings.recordings_dir)
        directory, session = self.importer(
            manager,
            url,
            title=title,
            course=course,
            client=client,
            prepared=prepared,
            progress=progress,
        )
        meta_dict = session.youtube or {}
        metadata = YouTubeMetadata(
            video_id=meta_dict.get("video_id", ""),
            url=session.source_url or url,
            title=meta_dict.get("title", session.title),
            channel=meta_dict.get("channel", ""),
            duration_seconds=float(meta_dict.get("duration_seconds", session.duration_seconds)),
            upload_date=meta_dict.get("upload_date", ""),
        )
        return YouTubeImportResult(directory, session, metadata)
