"""YouTube URL validation, metadata inspection, audio download and WAV session import."""

import array
import logging
import math
import os
import re
import shutil
import sys
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol
from urllib.parse import parse_qs, urlparse

from classscribe.sessions.manager import SessionManager, now_iso
from classscribe.sessions.models import Session, Status
from classscribe.storage import exclusive_lock
from classscribe.transcription.chunks import COPY_BLOCK_SECONDS

logger = logging.getLogger(__name__)

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")
DEFAULT_SAMPLE_RATE = 16000


class YouTubeImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeMetadata:
    video_id: str
    url: str
    title: str
    channel: str = ""
    duration_seconds: float = 0.0
    upload_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class YouTubeImportProgress:
    stage: str
    downloaded_bytes: int = 0
    total_bytes: int = 0
    title: str = ""

    @property
    def progress(self) -> float | None:
        if self.stage == "completed":
            return 1.0
        if self.stage == "downloading" and self.total_bytes > 0:
            return min(1.0, self.downloaded_bytes / self.total_bytes)
        return None


class YouTubeClient(Protocol):
    def inspect(self, url: str) -> YouTubeMetadata: ...

    def download_audio(
        self,
        url: str,
        directory: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> tuple[YouTubeMetadata, Path]: ...


def parse_youtube_url(source: str) -> tuple[str, str]:
    """Validate single-video YouTube URLs and discard playlist or timestamp parameters."""
    cleaned = (source or "").strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("Enter a YouTube video URL.")
    parsed = urlparse(cleaned)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or hostname not in YOUTUBE_HOSTS:
        raise ValueError("Provide a valid YouTube video URL.")
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    video_id = ""
    if hostname == "youtu.be" and len(path_parts) == 1:
        video_id = path_parts[0]
    elif parsed.path.rstrip("/") == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif len(path_parts) == 2 and path_parts[0] in {"shorts", "live", "embed", "v"}:
        video_id = path_parts[1]
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError("The URL must identify one YouTube video, not a playlist or channel.")
    return video_id, f"https://www.youtube.com/watch?v={video_id}"


def normalize_youtube_url(source: str) -> str:
    return parse_youtube_url(source)[1]


def _extract_metadata(video_id: str, url: str, info: Any) -> YouTubeMetadata:
    if not isinstance(info, dict) or not info:
        raise RuntimeError("YouTube did not return video metadata.")
    if info.get("_type") == "playlist":
        raise ValueError("The URL must identify one YouTube video, not a playlist or channel.")
    title = str(info.get("title") or "").strip() or f"YouTube {video_id}"
    channel = str(info.get("channel") or info.get("uploader") or "").strip()
    raw_duration = info.get("duration")
    duration = (
        float(raw_duration)
        if isinstance(raw_duration, (int, float))
        and math.isfinite(raw_duration)
        and raw_duration > 0
        else 0.0
    )
    upload_date = str(info.get("upload_date") or "").strip()
    return YouTubeMetadata(
        video_id=video_id,
        url=url,
        title=title,
        channel=channel,
        duration_seconds=duration,
        upload_date=upload_date,
    )


class YtDlpClient:
    def _load_yt_dlp(self) -> Any:
        try:
            from yt_dlp import YoutubeDL
        except ImportError as exc:
            raise RuntimeError('Install YouTube support: pip install -e ".[youtube]"') from exc
        return YoutubeDL

    def _base_options(self) -> dict[str, Any]:
        bundled_node = Path("bin") / ("node.exe" if os.name == "nt" else "node")
        node_path = str(bundled_node.resolve()) if bundled_node.is_file() else shutil.which("node")
        options: dict[str, Any] = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "overwrites": False,
            "continuedl": True,
            "windowsfilenames": True,
            "retries": 3,
            "socket_timeout": 30,
            "quiet": True,
            "no_warnings": True,
        }
        if node_path:
            options["js_runtimes"] = {"node": {"path": node_path}}
        return options

    def inspect(self, url: str) -> YouTubeMetadata:
        video_id, canonical = parse_youtube_url(url)
        YoutubeDL = self._load_yt_dlp()
        options = {**self._base_options(), "skip_download": True}
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(canonical, download=False)
        return _extract_metadata(video_id, canonical, info)

    def download_audio(
        self,
        url: str,
        directory: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> tuple[YouTubeMetadata, Path]:
        video_id, canonical = parse_youtube_url(url)
        YoutubeDL = self._load_yt_dlp()

        def hook(status: dict[str, Any]) -> None:
            if progress is not None and status.get("status") == "downloading":
                downloaded = int(status.get("downloaded_bytes") or 0)
                total = int(status.get("total_bytes") or status.get("total_bytes_estimate") or 0)
                progress(max(0, downloaded), max(0, total))

        options = {
            **self._base_options(),
            "outtmpl": str(directory / "source-%(id)s.%(ext)s"),
            "progress_hooks": [hook],
        }
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(canonical, download=True)
            metadata = _extract_metadata(video_id, canonical, info)
            media_path = Path(downloader.prepare_filename(info)).resolve()
        if media_path.parent != directory.resolve() or not media_path.is_file():
            raise FileNotFoundError(f"Downloaded YouTube audio was not found: {media_path}")
        return metadata, media_path


class _PcmPartWriter:
    def __init__(
        self,
        directory: Path,
        sample_rate: int,
        channels: int,
        max_part_bytes: int = 1024**3,
    ) -> None:
        self.directory = directory
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_bytes = 2 * channels
        self.max_part_frames = max_part_bytes // self.frame_bytes
        if self.max_part_frames < 1:
            raise ValueError("WAV part size must hold at least one frame")
        self.parts: list[dict[str, Any]] = []
        self.frames = 0
        self.raw: BinaryIO | None = None
        self.wav: wave.Wave_write | None = None
        self._open_part()

    def _open_part(self) -> None:
        number = len(self.parts) + 1
        suffix = "" if number == 1 else f"-{number:04}"
        filename = f"system{suffix}.wav"
        self.raw = (self.directory / filename).open("xb")
        self.wav = wave.open(self.raw, "wb")
        self.wav.setparams((self.channels, 2, self.sample_rate, 0, "NONE", "PCM"))
        self.wav.writeframes(b"")
        self.parts.append({"file": filename, "start_frame": self.frames, "frames": 0})

    def write(self, data: bytes | memoryview) -> None:
        remaining = memoryview(data)
        if len(remaining) % self.frame_bytes:
            raise ValueError("Incomplete PCM16 frame in decoded audio")
        while remaining:
            if self.parts[-1]["frames"] == self.max_part_frames:
                self.close_current()
                self._open_part()
            frames = min(
                len(remaining) // self.frame_bytes,
                self.max_part_frames - self.parts[-1]["frames"],
            )
            size = frames * self.frame_bytes
            assert self.wav is not None and self.raw is not None
            self.wav.writeframes(remaining[:size])
            self.frames += frames
            self.parts[-1]["frames"] += frames
            remaining = remaining[size:]

    def close_current(self) -> None:
        try:
            if self.wav is not None:
                self.wav.close()
        finally:
            if self.raw is not None:
                try:
                    self.raw.flush()
                    os.fsync(self.raw.fileno())
                finally:
                    self.raw.close()
            self.wav = None
            self.raw = None


def _is_pcm16_wav(path: Path) -> bool:
    if path.suffix.lower() != ".wav":
        return False
    try:
        with wave.open(str(path), "rb") as handle:
            return (
                handle.getsampwidth() == 2
                and handle.getcomptype() == "NONE"
                and handle.getframerate() > 0
                and handle.getnchannels() >= 1
            )
    except (wave.Error, OSError, EOFError):
        return False


def store_youtube_audio(
    source_path: Path,
    directory: Path,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    max_part_bytes: int = 1024**3,
) -> dict[str, Any]:
    """Convert downloaded media into durable PCM16 WAV session part(s) without external FFmpeg."""
    resolved = source_path.resolve()
    if resolved.parent != directory.resolve() or not resolved.is_file():
        raise ValueError("Downloaded audio must reside inside the session directory")
    if (directory / "system.wav").exists():
        raise FileExistsError("Session audio system.wav already exists")

    writer: _PcmPartWriter | None = None
    try:
        if _is_pcm16_wav(resolved):
            with wave.open(str(resolved), "rb") as wav_in:
                rate = wav_in.getframerate()
                channels = wav_in.getnchannels()
                total = wav_in.getnframes()
                writer = _PcmPartWriter(directory, rate, channels, max_part_bytes=max_part_bytes)
                remaining = total
                block = max(1, COPY_BLOCK_SECONDS * rate)
                while remaining > 0:
                    count = min(remaining, block)
                    data = wav_in.readframes(count)
                    actual = len(data) // (channels * 2)
                    if actual != count:
                        raise ValueError("Downloaded WAV data is truncated")
                    writer.write(data)
                    remaining -= actual
        else:
            try:
                import av
            except ImportError as exc:
                raise RuntimeError(
                    'Install YouTube audio decoding support: pip install -e ".[youtube]"'
                ) from exc
            writer = _PcmPartWriter(
                directory, sample_rate, channels=1, max_part_bytes=max_part_bytes
            )
            with av.open(str(resolved)) as container:
                if not container.streams.audio:
                    raise ValueError("Downloaded YouTube media does not contain an audio stream")
                resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
                for frame in container.decode(audio=0):
                    for out_frame in resampler.resample(frame):
                        _write_av_frame(writer, out_frame)
                for out_frame in resampler.resample(None):
                    _write_av_frame(writer, out_frame)
    finally:
        if writer is not None:
            writer.close_current()

    if writer is None or writer.frames < 1:
        raise ValueError("Downloaded YouTube media contains no decodable audio frames")

    return {
        "sample_rate": writer.sample_rate,
        "channels": writer.channels,
        "sample_width_bytes": 2,
        "start_offset_seconds": 0.0,
        "frames": writer.frames,
        "duration_seconds": writer.frames / writer.sample_rate,
        "parts": [dict(part) for part in writer.parts],
    }


def _write_av_frame(writer: _PcmPartWriter, frame: Any) -> None:
    size = int(frame.samples) * 2
    if size <= 0:
        return
    raw = memoryview(frame.planes[0])[:size]
    if sys.byteorder != "little":
        samples = array.array("h", raw)
        samples.byteswap()
        writer.write(samples.tobytes())
    else:
        writer.write(raw)


def _matching_metadata(
    video_id: str, canonical: str, metadata: YouTubeMetadata | None
) -> YouTubeMetadata | None:
    if metadata is None or not metadata.title.strip():
        return None
    try:
        meta_id, meta_canonical = parse_youtube_url(metadata.url)
    except ValueError:
        return None
    if meta_id != video_id or meta_canonical != canonical:
        return None
    if metadata.video_id and metadata.video_id != video_id:
        return None
    return YouTubeMetadata(
        video_id=video_id,
        url=canonical,
        title=metadata.title.strip(),
        channel=metadata.channel.strip(),
        duration_seconds=(
            float(metadata.duration_seconds)
            if isinstance(metadata.duration_seconds, (int, float))
            and not isinstance(metadata.duration_seconds, bool)
            and math.isfinite(metadata.duration_seconds)
            and metadata.duration_seconds >= 0
            else 0.0
        ),
        upload_date=metadata.upload_date.strip(),
    )


def import_youtube_session(
    manager: SessionManager,
    url: str,
    *,
    title: str = "",
    course: str = "",
    client: YouTubeClient | None = None,
    metadata: YouTubeMetadata | None = None,
    prepared: Callable[[Path, Session, YouTubeMetadata], None] | None = None,
    progress: Callable[[YouTubeImportProgress], None] | None = None,
    max_part_bytes: int = 1024**3,
) -> tuple[Path, Session]:
    video_id, canonical = parse_youtube_url(url)
    yt = client or YtDlpClient()

    def notify(stage: str, downloaded: int = 0, total: int = 0, label: str = "") -> None:
        if progress is not None:
            progress(YouTubeImportProgress(stage, downloaded, total, label))

    notify("inspecting", label=title.strip())
    validated = _matching_metadata(video_id, canonical, metadata)
    metadata = validated if validated is not None else yt.inspect(canonical)
    resolved_title = title.strip() or metadata.title.strip() or f"YouTube {video_id}"
    resolved_course = course.strip() or metadata.channel.strip()
    directory, session = manager.create(resolved_title, resolved_course)

    error: BaseException | None = None
    raw_path: Path | None = None
    with exclusive_lock(directory):
        try:
            session.started_at = now_iso()
            session.source_kind = "youtube"
            session.source_url = canonical
            session.youtube = metadata.to_dict()
            session.system_audio_device = {
                "name": f"YouTube ({metadata.video_id})",
                "source": "youtube",
                "url": canonical,
                "channel": metadata.channel,
            }
            session.microphone_device = None
            session.microphone_audio_file = None
            session.transition(Status.IMPORTING)
            manager.save(directory, session)
            if prepared is not None:
                prepared(directory, session, metadata)
            notify("downloading", label=session.title)
            downloaded_meta, raw_path = yt.download_audio(
                canonical,
                directory,
                progress=lambda done, total: notify("downloading", done, total, session.title),
            )
            metadata = YouTubeMetadata(
                video_id=video_id,
                url=canonical,
                title=downloaded_meta.title or metadata.title,
                channel=downloaded_meta.channel or metadata.channel,
                duration_seconds=downloaded_meta.duration_seconds or metadata.duration_seconds,
                upload_date=downloaded_meta.upload_date or metadata.upload_date,
            )
            session.youtube = metadata.to_dict()
            notify("preparing_audio", label=session.title)
            track = store_youtube_audio(raw_path, directory, max_part_bytes=max_part_bytes)
            if raw_path != (directory / "system.wav"):
                raw_path.unlink(missing_ok=True)
            session.tracks = {
                "system": {
                    **track,
                    "source_kind": "youtube",
                    "source_url": canonical,
                    "video_id": metadata.video_id,
                    "channel": metadata.channel,
                }
            }
            session.duration_seconds = track["duration_seconds"]
        except BaseException as exc:
            error = exc
        finally:
            if error is not None:
                for temp_file in directory.glob("source-*"):
                    if temp_file.is_file() and temp_file.name != "system.wav":
                        temp_file.unlink(missing_ok=True)
            session.ended_at = now_iso()
            session.recording_finalized = error is None and "system" in session.tracks
            session.error = f"{type(error).__name__}: {error}" if error else None
            session.transition(Status.FAILED if error else Status.RECORDED)
            manager.save(directory, session)
    if error is not None:
        logger.error("YouTube import failed in session %s", session.session_id)
        raise YouTubeImportError(
            f"YouTube import failed: {session.error}. Session preserved in {directory}"
        ) from error
    notify("completed", label=session.title)
    return directory, session
