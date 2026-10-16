"""Application service for YouTube metadata inspection and session import."""

import math
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
    parse_youtube_url,
)


def coerce_metadata(
    url: str, raw: YouTubeMetadata | dict[str, Any] | None
) -> YouTubeMetadata | None:
    """Validate optional GUI/caller metadata against the normalized target YouTube URL."""
    if raw is None:
        return None
    try:
        video_id, canonical = parse_youtube_url(url)
    except ValueError:
        return None
    if isinstance(raw, YouTubeMetadata):
        data: dict[str, Any] = raw.to_dict()
    elif isinstance(raw, dict):
        data = raw
    else:
        return None
    raw_url = str(data.get("url") or "").strip()
    raw_id = str(data.get("video_id") or "").strip()
    raw_title = str(data.get("title") or "").strip()
    if not raw_url or not raw_title:
        return None
    try:
        parsed_id, parsed_canonical = parse_youtube_url(raw_url)
    except ValueError:
        return None
    if parsed_id != video_id or parsed_canonical != canonical:
        return None
    if raw_id and raw_id != video_id:
        return None
    raw_duration = data.get("duration_seconds", 0.0)
    duration = (
        float(raw_duration)
        if isinstance(raw_duration, (int, float))
        and not isinstance(raw_duration, bool)
        and math.isfinite(raw_duration)
        and raw_duration >= 0
        else 0.0
    )
    return YouTubeMetadata(
        video_id=video_id,
        url=canonical,
        title=raw_title,
        channel=str(data.get("channel") or "").strip(),
        duration_seconds=duration,
        upload_date=str(data.get("upload_date") or "").strip(),
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
        metadata: YouTubeMetadata | dict[str, Any] | None = None,
        prepared: Callable[[Path, Session, YouTubeMetadata], None] | None = None,
        progress: Callable[[YouTubeImportProgress], None] | None = None,
    ) -> YouTubeImportResult:
        validated_metadata = coerce_metadata(url, metadata)
        client = self.client_factory()
        manager = SessionManager(settings.recordings_dir)
        directory, session = self.importer(
            manager,
            url,
            title=title,
            course=course,
            client=client,
            metadata=validated_metadata,
            prepared=prepared,
            progress=progress,
        )
        meta_dict = session.youtube or {}
        resolved_meta = YouTubeMetadata(
            video_id=meta_dict.get("video_id", ""),
            url=session.source_url or url,
            title=meta_dict.get("title", session.title),
            channel=meta_dict.get("channel", ""),
            duration_seconds=float(meta_dict.get("duration_seconds", session.duration_seconds)),
            upload_date=meta_dict.get("upload_date", ""),
        )
        return YouTubeImportResult(directory, session, resolved_meta)
