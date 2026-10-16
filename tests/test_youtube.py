"""Offline unit and integration tests for YouTube audio import and pipeline reuse."""

from __future__ import annotations

import fractions
import json
import subprocess
import sys
import types
import wave
from dataclasses import replace
from pathlib import Path

import av
import numpy as np
import pytest
from conftest import make_wav
from test_transcription import FakeEngine

from classscribe.application.desktop import DesktopServices
from classscribe.application.library import SessionLibrary
from classscribe.application.preferences import PreferenceStore
from classscribe.application.youtube import YouTubeService
from classscribe.cli import commands
from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Session, Status
from classscribe.transcription.service import transcribe_session
from classscribe.youtube import (
    YouTubeImportError,
    YouTubeImportProgress,
    YouTubeMetadata,
    YtDlpClient,
    import_youtube_session,
    normalize_youtube_url,
    parse_youtube_url,
    store_youtube_audio,
)

VIDEO_ID = "dQw4w9WgXcQ"
CANONICAL_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"


class FakeYouTubeClient:
    def __init__(self, seconds: int = 3, fail_download: bool = False) -> None:
        self.seconds = seconds
        self.fail_download = fail_download
        self.inspected: list[str] = []
        self.downloaded: list[str] = []

    def inspect(self, url: str) -> YouTubeMetadata:
        vid, canonical = parse_youtube_url(url)
        self.inspected.append(canonical)
        return YouTubeMetadata(
            video_id=vid,
            url=canonical,
            title="Lecture 04: Virtual Memory",
            channel="CS Systems",
            duration_seconds=float(self.seconds),
        )

    def download_audio(
        self, url: str, directory: Path, progress=None
    ) -> tuple[YouTubeMetadata, Path]:
        metadata = self.inspect(url)
        self.downloaded.append(metadata.url)
        if progress:
            progress(500, 1000)
        raw_path = directory / f"source-{metadata.video_id}.wav"
        make_wav(raw_path, seconds=self.seconds, channels=1, rate=8000)
        if self.fail_download:
            raise RuntimeError("Simulated network failure during download.")
        if progress:
            progress(1000, 1000)
        return metadata, raw_path


@pytest.mark.parametrize(
    "raw_url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}&list=PL123&t=45s",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=shared123",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}?feature=share",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/v/{VIDEO_ID}",
    ],
)
def test_parse_and_normalize_valid_youtube_urls(raw_url: str):
    video_id, canonical = parse_youtube_url(raw_url)
    assert video_id == VIDEO_ID
    assert canonical == CANONICAL_URL
    assert normalize_youtube_url(raw_url) == CANONICAL_URL


@pytest.mark.parametrize(
    "invalid_url",
    [
        "",
        "   ",
        "not-a-url",
        f"ftp://www.youtube.com/watch?v={VIDEO_ID}",
        "https://vimeo.com/123456789",
        "https://evil-youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/playlist?list=PL1234567890",
        "https://www.youtube.com/@mitocw",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch",
        "https://youtu.be/",
    ],
)
def test_reject_invalid_or_non_video_youtube_urls(invalid_url: str):
    with pytest.raises(ValueError):
        parse_youtube_url(invalid_url)


def test_offline_mode_blocks_youtube_before_client_access(tmp_path):
    client = FakeYouTubeClient()
    service = YouTubeService(client_factory=lambda: client)
    settings = Settings(
        recordings_dir=tmp_path / "recordings",
        transcripts_dir=tmp_path / "transcripts",
        offline=True,
    )
    with pytest.raises(RuntimeError, match="offline mode"):
        service.inspect(settings, CANONICAL_URL)
    with pytest.raises(RuntimeError, match="offline mode"):
        service.import_session(settings, CANONICAL_URL)
    assert client.inspected == []
    assert client.downloaded == []


def test_store_youtube_audio_rotates_wav_parts_and_preserves_pcm(tmp_path):
    out_dir = tmp_path / "session"
    out_dir.mkdir()
    source = out_dir / "source.wav"
    make_wav(source, seconds=4, channels=1, rate=8000)
    # 8000 Hz * 2 bytes * 4s = 64000 bytes; max_part_bytes=25000 forces multiple WAV parts.
    track = store_youtube_audio(source, out_dir, max_part_bytes=25_000)
    assert track["sample_rate"] == 8000
    assert track["channels"] == 1
    assert track["frames"] == 32_000
    assert len(track["parts"]) == 3
    assert [p["file"] for p in track["parts"]] == [
        "system.wav",
        "system-0002.wav",
        "system-0003.wav",
    ]
    total_frames = 0
    for part in track["parts"]:
        with wave.open(str(out_dir / part["file"])) as handle:
            assert handle.getsampwidth() == 2
            assert handle.getnchannels() == 1
            assert handle.getnframes() == part["frames"]
            total_frames += handle.getnframes()
    assert total_frames == 32_000


def test_store_youtube_audio_decodes_compressed_container_via_pyav(tmp_path):
    out_dir = tmp_path / "session"
    out_dir.mkdir()
    compressed = out_dir / "audio.ogg"
    sample_rate = 48_000
    total_samples = sample_rate * 2  # 2 seconds
    with av.open(str(compressed), "w") as container:
        stream = container.add_stream("libopus", rate=sample_rate)
        samples = (np.sin(np.linspace(0, 440 * 2 * np.pi, total_samples)) * 12000).astype(np.int16)
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = sample_rate
        frame.pts = 0
        frame.time_base = fractions.Fraction(1, sample_rate)
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)

    track = store_youtube_audio(compressed, out_dir)
    assert track["sample_rate"] == 16_000
    assert track["channels"] == 1
    # 2 seconds @ 16 kHz ~= 32000 frames (Opus priming adds a tiny number of samples).
    assert 31_000 <= track["frames"] <= 33_000
    with wave.open(str(out_dir / "system.wav")) as wav_file:
        assert wav_file.getframerate() == 16_000
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() == track["frames"]


def test_import_youtube_session_pipeline_and_retranscription(tmp_path):
    recordings_dir = tmp_path / "recordings"
    transcripts_dir = tmp_path / "transcripts"
    settings = Settings(recordings_dir=recordings_dir, transcripts_dir=transcripts_dir)
    manager = SessionManager(recordings_dir)
    client = FakeYouTubeClient(seconds=3)
    progress_events: list[YouTubeImportProgress] = []

    directory, session = import_youtube_session(
        manager,
        f"https://youtu.be/{VIDEO_ID}?t=10",
        client=client,
        progress=progress_events.append,
    )

    assert session.status == Status.RECORDED
    assert session.recording_finalized is True
    assert session.source_kind == "youtube"
    assert session.source_url == CANONICAL_URL
    assert session.title == "Lecture 04: Virtual Memory"
    assert session.course == "CS Systems"
    assert session.youtube == {
        "video_id": VIDEO_ID,
        "url": CANONICAL_URL,
        "title": "Lecture 04: Virtual Memory",
        "channel": "CS Systems",
        "duration_seconds": 3.0,
        "upload_date": "",
    }
    assert (directory / "system.wav").is_file()
    assert list(directory.glob("source-*")) == []
    assert [e.stage for e in progress_events] == [
        "inspecting",
        "downloading",
        "downloading",
        "downloading",
        "preparing_audio",
        "completed",
    ]

    # Send the imported YouTube session through the EXISTING transcription pipeline.
    result = transcribe_session(
        manager, directory, session, settings, engine_factory=lambda _: FakeEngine()
    )
    transcript = json.loads((result / "transcript.json").read_text(encoding="utf-8"))
    assert transcript["source_kind"] == "youtube"
    assert transcript["source_url"] == CANONICAL_URL
    assert transcript["youtube"]["video_id"] == VIDEO_ID
    assert [s["source"] for s in transcript["segments"]] == ["system"]
    assert transcript["segments"][0]["text"] == "La memoria caché"

    md = (result / "transcript.md").read_text(encoding="utf-8")
    assert f"Source: {CANONICAL_URL}" in md
    assert "[00:00:00] CLASE" in md
    assert "La memoria caché" in md

    # Re-transcribing uses local system.wav without re-downloading from YouTube.
    downloads_before = list(client.downloaded)
    second_result = transcribe_session(
        manager,
        directory,
        manager.load(directory),
        replace(settings, model="medium"),
        engine_factory=lambda _: FakeEngine(),
    )
    assert second_result != result
    assert client.downloaded == downloads_before

    # SessionLibrary exposes YouTube metadata and transcript segments to GUI/CLI.
    library = SessionLibrary(settings)
    summaries = library.list_sessions()
    assert len(summaries) == 1
    assert summaries[0]["source_kind"] == "youtube"
    assert summaries[0]["source_url"] == CANONICAL_URL
    assert summaries[0]["channel"] == "CS Systems"
    assert summaries[0]["video_id"] == VIDEO_ID
    assert summaries[0]["transcribed"] is True
    detail = library.detail(session.session_id)
    assert len(detail["runs"]) == 2
    rows = library.transcript(result)
    assert len(rows) == 1
    assert rows[0]["speaker"] == "CLASS"
    assert rows[0]["time"] == "00:00:00"
    assert rows[0]["text"] == "La memoria caché"


def test_import_youtube_session_failure_marks_session_failed(tmp_path):
    manager = SessionManager(tmp_path / "recordings")
    client = FakeYouTubeClient(fail_download=True)
    with pytest.raises(YouTubeImportError, match="Simulated network failure"):
        import_youtube_session(
            manager, CANONICAL_URL, title="Custom Title", course="Custom Course", client=client
        )
    dirs = list(manager.root.iterdir())
    assert len(dirs) == 1
    failed_session = manager.load(dirs[0])
    assert failed_session.status == Status.FAILED
    assert failed_session.recording_finalized is False
    assert failed_session.title == "Custom Title"
    assert failed_session.course == "Custom Course"


def test_session_model_validates_source_kind():
    session = Session(
        session_id="0123456789abcdef0123456789abcdef",
        title="Valid",
        course="CS",
        created_at="2026-10-15T18:30:00-05:00",
        platform="Windows",
        source_kind="youtube",
        source_url=CANONICAL_URL,
    )
    loaded = Session.from_dict(session.to_dict())
    assert loaded.source_kind == "youtube"
    assert loaded.source_url == CANONICAL_URL
    with pytest.raises(ValueError, match="Unsupported session source kind"):
        Session.from_dict({**session.to_dict(), "source_kind": "podcast"})


def test_ytdlp_client_inspect_and_download_with_fake_module(tmp_path, monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            assert self.opts["noplaylist"] is True
            info = {
                "id": VIDEO_ID,
                "title": "Compilers Lecture",
                "channel": "MIT OCW",
                "duration": 125,
                "webpage_url": CANONICAL_URL,
                "ext": "webm",
            }
            if download:
                out = tmp_path / f"source-{VIDEO_ID}.webm"
                out.write_bytes(b"fake-audio")
                for hook in self.opts.get("progress_hooks", []):
                    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
                    hook({"status": "finished", "total_bytes": 100})
                info["requested_downloads"] = [{"filepath": str(out)}]
            return info

        def prepare_filename(self, info):
            return str(tmp_path / f"source-{info['id']}.{info['ext']}")

    fake_module = types.ModuleType("yt_dlp")
    fake_module.YoutubeDL = FakeYoutubeDL
    monkeypatch.setitem(sys.modules, "yt_dlp", fake_module)

    client = YtDlpClient()
    meta = client.inspect(CANONICAL_URL)
    assert meta.video_id == VIDEO_ID
    assert meta.title == "Compilers Lecture"
    assert meta.channel == "MIT OCW"
    assert meta.duration_seconds == 125

    progress_tuples: list[tuple[int, int]] = []
    meta2, path = client.download_audio(
        CANONICAL_URL,
        tmp_path,
        progress=lambda done, total: progress_tuples.append((done, total)),
    )
    assert meta2 == meta
    assert path.is_file()
    assert progress_tuples == [(50, 100)]


def test_desktop_services_youtube_inspect_and_import(tmp_path):
    store = PreferenceStore(tmp_path / "prefs.json", tmp_path / "data")
    client = FakeYouTubeClient(seconds=2)
    desktop = DesktopServices(store, youtube=YouTubeService(client_factory=lambda: client))

    inspected = desktop.inspect_youtube(store.load(), f"https://youtu.be/{VIDEO_ID}")
    assert inspected["video_id"] == VIDEO_ID
    assert inspected["title"] == "Lecture 04: Virtual Memory"
    assert inspected["duration"] == "00:00:02"

    emitted: list[tuple[str, object]] = []
    detail = desktop.import_youtube(
        store.load(),
        CANONICAL_URL,
        "Overridden Title",
        "Overridden Course",
        lambda name, payload: emitted.append((name, payload)),
    )
    assert detail["session"]["title"] == "Overridden Title"
    assert detail["session"]["course"] == "Overridden Course"
    assert detail["session"]["source_kind"] == "youtube"
    assert detail["session"]["source_url"] == CANONICAL_URL
    assert any(name == "youtube" for name, _ in emitted)


def test_cli_youtube_inspect_import_and_transcribe(tmp_path, monkeypatch, capsys):
    client = FakeYouTubeClient(seconds=2)
    monkeypatch.setattr(commands, "YtDlpClient", lambda: client)
    monkeypatch.setattr(
        commands,
        "transcribe",
        lambda settings, directory, session, **kwargs: transcribe_session(
            SessionManager(settings.recordings_dir),
            directory,
            session,
            settings,
            engine_factory=lambda _: FakeEngine(),
        ),
    )

    rec_dir = tmp_path / "recordings"
    tr_dir = tmp_path / "transcripts"

    # 1. --inspect
    code = commands.main(
        [
            "youtube",
            CANONICAL_URL,
            "--inspect",
            "--recordings-dir",
            str(rec_dir),
            "--transcripts-dir",
            str(tr_dir),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["video_id"] == VIDEO_ID
    assert payload["title"] == "Lecture 04: Virtual Memory"

    # 2. Import + --transcribe
    code = commands.main(
        [
            "youtube",
            CANONICAL_URL,
            "--title",
            "CLI Imported Lecture",
            "--course",
            "Operating Systems",
            "--transcribe",
            "--recordings-dir",
            str(rec_dir),
            "--transcripts-dir",
            str(tr_dir),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "YouTube audio saved:" in out
    assert "Transcript:" in out


def test_youtube_module_import_does_not_load_ytdlp_or_heavy_deps():
    script = """
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'yt_dlp', 'PySide6', 'faster_whisper', 'ctranslate2'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
import classscribe.youtube
import classscribe.application.youtube
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=15)
