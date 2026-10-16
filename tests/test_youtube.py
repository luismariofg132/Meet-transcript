"""Offline unit and integration tests for YouTube audio import and pipeline reuse."""

from __future__ import annotations

import array
import fractions
import json
import math
import os
import subprocess
import sys
import types
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import make_wav
from test_transcription import FakeEngine

from classscribe.application.desktop import DesktopServices
from classscribe.application.library import SessionLibrary
from classscribe.application.preferences import PreferenceStore
from classscribe.application.youtube import YouTubeService, coerce_metadata
from classscribe.cli import commands
from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Session, Status
from classscribe.transcription.engine import RawSegment
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
VIDEO_ID_B = "jNQXAC9IVRw"
CANONICAL_URL_B = f"https://www.youtube.com/watch?v={VIDEO_ID_B}"


def test_yt_dlp_loader_sets_no_lazy_before_import(monkeypatch):
    import builtins

    original_import = builtins.__import__
    sentinel = object()
    monkeypatch.delenv("YTDLP_NO_LAZY_EXTRACTORS", raising=False)

    def checked_import(name, *args, **kwargs):
        if name == "yt_dlp":
            assert os.environ["YTDLP_NO_LAZY_EXTRACTORS"] == "1"
            return types.SimpleNamespace(YoutubeDL=sentinel)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked_import)
    assert YtDlpClient()._load_yt_dlp() is sentinel


def test_core_import_does_not_load_yt_dlp():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import classscribe.youtube, sys; "
            "assert not any(n == 'yt_dlp' or n.startswith('yt_dlp.') for n in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_real_youtube_extractor_without_lazy_registry():
    from importlib.util import find_spec

    if find_spec("yt_dlp") is None:
        pytest.skip("Optional YouTube dependency is not installed")
    # Fresh process: fail on any attempt to import the excluded module, even if
    # yt-dlp would catch ImportError and silently fall back to its normal registry.
    code = """
import sys
class RejectLazy:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'yt_dlp.extractor.lazy_extractors':
            raise AssertionError('Lazy extractor import attempted')
sys.meta_path.insert(0, RejectLazy())
from classscribe.youtube import YtDlpClient
youtube_dl = YtDlpClient()._load_yt_dlp()
with youtube_dl({'quiet': True, 'no_warnings': True}) as downloader:
    extractor = downloader.get_info_extractor('Youtube')
    assert extractor.suitable('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
from yt_dlp.globals import LAZY_EXTRACTORS
assert LAZY_EXTRACTORS.value is False
assert 'yt_dlp.extractor.lazy_extractors' not in sys.modules
"""
    env = os.environ.copy()
    env.pop("YTDLP_NO_LAZY_EXTRACTORS", None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


class FakeYouTubeClient:
    def __init__(self, seconds: int = 3, fail_download: bool = False) -> None:
        self.seconds = seconds
        self.fail_download = fail_download
        self.inspected: list[str] = []
        self.downloaded: list[str] = []

    def _metadata_for(self, url: str) -> YouTubeMetadata:
        vid, canonical = parse_youtube_url(url)
        if vid == VIDEO_ID_B:
            return YouTubeMetadata(
                video_id=vid,
                url=canonical,
                title="Lecture 05: Page Tables",
                channel="OS Kernel Lab",
                duration_seconds=float(self.seconds),
            )
        return YouTubeMetadata(
            video_id=vid,
            url=canonical,
            title="Lecture 04: Virtual Memory",
            channel="CS Systems",
            duration_seconds=float(self.seconds),
        )

    def inspect(self, url: str) -> YouTubeMetadata:
        metadata = self._metadata_for(url)
        self.inspected.append(metadata.url)
        return metadata

    def download_audio(
        self, url: str, directory: Path, progress=None
    ) -> tuple[YouTubeMetadata, Path]:
        metadata = self._metadata_for(url)
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


def test_offline_mode_does_not_block_youtube_acquisition(tmp_path):
    client = FakeYouTubeClient(seconds=2)
    service = YouTubeService(client_factory=lambda: client)
    settings = Settings(
        recordings_dir=tmp_path / "recordings",
        transcripts_dir=tmp_path / "transcripts",
        offline=True,
    )
    inspected = service.inspect(settings, f"https://youtu.be/{VIDEO_ID}")
    assert inspected.video_id == VIDEO_ID
    assert client.inspected == [CANONICAL_URL]

    result = service.import_session(settings, CANONICAL_URL, metadata=inspected)
    assert result.session.status == Status.RECORDED
    assert result.session.recording_finalized is True
    assert (result.directory / "system.wav").is_file()
    assert client.inspected == [CANONICAL_URL]
    assert client.downloaded == [CANONICAL_URL]

    # With a cached local model (FakeEngine), offline transcription succeeds.
    manager = SessionManager(settings.recordings_dir)
    out = transcribe_session(
        manager,
        result.directory,
        result.session,
        settings,
        engine_factory=lambda _: FakeEngine(),
    )
    assert (out / "transcript.json").is_file()


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


def test_store_youtube_audio_missing_pyav_raises_actionable_error(tmp_path, monkeypatch):
    out_dir = tmp_path / "session"
    out_dir.mkdir()
    compressed = out_dir / "audio.webm"
    compressed.write_bytes(b"non-wav-compressed-container")
    monkeypatch.setitem(sys.modules, "av", None)
    with pytest.raises(RuntimeError, match=r'pip install -e "\.\[youtube\]"'):
        store_youtube_audio(compressed, out_dir)


def test_store_youtube_audio_decodes_compressed_container_via_pyav(tmp_path):
    av = pytest.importorskip("av")
    out_dir = tmp_path / "session"
    out_dir.mkdir()
    compressed = out_dir / "audio.ogg"
    sample_rate = 48_000
    total_samples = sample_rate * 2  # 2 seconds
    with av.open(str(compressed), "w") as container:
        stream = container.add_stream("libopus", rate=sample_rate)
        frame = av.AudioFrame(format="s16", layout="mono", samples=total_samples)
        frame.sample_rate = sample_rate
        frame.pts = 0
        frame.time_base = fractions.Fraction(1, sample_rate)
        samples = array.array(
            "h",
            (
                int(math.sin(2.0 * math.pi * 440.0 * idx / sample_rate) * 12000)
                for idx in range(total_samples)
            ),
        )
        frame.planes[0].update(samples.tobytes())
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
    prepared_statuses: list[Status] = []

    directory, session = import_youtube_session(
        manager,
        f"https://youtu.be/{VIDEO_ID}?t=10",
        client=client,
        prepared=lambda _dir, sess, _meta: prepared_statuses.append(sess.status),
        progress=progress_events.append,
    )

    assert prepared_statuses == [Status.IMPORTING]
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
    assert "system" in session.tracks
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
    transcribe_events = []
    result = transcribe_session(
        manager,
        directory,
        session,
        settings,
        engine_factory=lambda _: FakeEngine(),
        progress=transcribe_events.append,
    )
    assert {e.source for e in transcribe_events if e.source} == {"media"}
    transcript = json.loads((result / "transcript.json").read_text(encoding="utf-8"))
    assert transcript["source_kind"] == "youtube"
    assert transcript["source_url"] == CANONICAL_URL
    assert transcript["youtube"]["video_id"] == VIDEO_ID
    assert [s["source"] for s in transcript["segments"]] == ["media"]
    assert transcript["segments"][0]["audio_file"] == "system.wav"
    assert transcript["segments"][0]["text"] == "La memoria caché"

    md = (result / "transcript.md").read_text(encoding="utf-8")
    assert f"Source: {CANONICAL_URL}" in md
    assert "VIDEO = imported media" in md
    assert "[00:00:00] VIDEO" in md
    assert "[00:00:00] CLASE" not in md
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

    # SessionLibrary exposes YouTube metadata and VIDEO transcript segments to GUI/CLI.
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
    assert rows[0]["source"] == "media"
    assert rows[0]["speaker"] == "VIDEO"
    assert rows[0]["time"] == "00:00:00"
    assert rows[0]["text"] == "La memoria caché"


def test_import_youtube_session_failure_marks_session_failed_and_blocks_transcription(tmp_path):
    manager = SessionManager(tmp_path / "recordings")
    client = FakeYouTubeClient(fail_download=True)
    prepared_statuses: list[Status] = []
    with pytest.raises(YouTubeImportError, match="Simulated network failure"):
        import_youtube_session(
            manager,
            CANONICAL_URL,
            title="Custom Title",
            course="Custom Course",
            client=client,
            prepared=lambda _dir, sess, _meta: prepared_statuses.append(sess.status),
        )
    assert prepared_statuses == [Status.IMPORTING]
    dirs = list(manager.root.iterdir())
    assert len(dirs) == 1
    failed_dir = dirs[0]
    failed_session = manager.load(failed_dir)
    assert failed_session.status == Status.FAILED
    assert failed_session.recording_finalized is False
    assert failed_session.tracks == {}
    assert list(failed_dir.glob("source-*")) == []
    assert failed_session.title == "Custom Title"
    assert failed_session.course == "Custom Course"

    with pytest.raises(ValueError, match="finalized"):
        transcribe_session(
            manager,
            failed_dir,
            failed_session,
            Settings(recordings_dir=manager.root, transcripts_dir=tmp_path / "transcripts"),
            engine_factory=lambda _: FakeEngine(),
        )


def test_youtube_media_segments_preserve_repeated_text_across_overlap_windows(tmp_path):
    recordings_dir = tmp_path / "recordings"
    transcripts_dir = tmp_path / "transcripts"
    settings = Settings(recordings_dir=recordings_dir, transcripts_dir=transcripts_dir)
    manager = SessionManager(recordings_dir)
    directory, session = manager.create("Long YouTube Lecture", "CS Systems")
    make_wav(directory / "system.wav", seconds=301, rate=20)
    session.source_kind = "youtube"
    session.source_url = CANONICAL_URL
    session.started_at = "2026-10-15T18:30:00-05:00"
    session.ended_at = "2026-10-15T18:35:01-05:00"
    session.duration_seconds = 301.0
    session.recording_finalized = True
    session.status = Status.RECORDED
    session.tracks = {
        "system": {
            "sample_rate": 20,
            "channels": 1,
            "sample_width_bytes": 2,
            "start_offset_seconds": 0.0,
            "frames": 6020,
            "duration_seconds": 301.0,
            "parts": [{"file": "system.wav", "start_frame": 0, "frames": 6020}],
            "source_kind": "youtube",
            "source_url": CANONICAL_URL,
            "video_id": VIDEO_ID,
            "channel": "CS Systems",
        }
    }
    manager.save(directory, session)

    scripts = [
        [
            RawSegment(290, 291, "Important definition."),
            RawSegment(294, 295, "Important definition."),
        ],
        [RawSegment(5, 6, "Important definition."), RawSegment(9, 10, "Important definition.")],
    ]
    calls = [0]

    class WindowEngine(FakeEngine):
        def transcribe(self, path, language):
            idx = calls[0]
            calls[0] += 1
            return iter(scripts[idx]), "es"

    result = transcribe_session(
        manager, directory, session, settings, engine_factory=lambda _: WindowEngine()
    )
    transcript = json.loads((result / "transcript.json").read_text(encoding="utf-8"))
    segments = transcript["segments"]
    assert [s["source"] for s in segments] == ["media", "media"]
    assert [s["text"] for s in segments] == ["Important definition.", "Important definition."]
    assert [s["audio_start"] for s in segments] == [290, 294]


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


def test_desktop_services_youtube_inspect_and_import_reuses_metadata(tmp_path):
    store = PreferenceStore(tmp_path / "prefs.json", tmp_path / "data")
    client = FakeYouTubeClient(seconds=2)
    desktop = DesktopServices(store, youtube=YouTubeService(client_factory=lambda: client))

    inspected = desktop.inspect_youtube(store.load(), f"https://youtu.be/{VIDEO_ID}")
    assert inspected["video_id"] == VIDEO_ID
    assert inspected["title"] == "Lecture 04: Virtual Memory"
    assert inspected["duration"] == "00:00:02"
    assert client.inspected == [CANONICAL_URL]

    emitted: list[tuple[str, object]] = []
    # Equivalent canonical URL reuses inspected metadata without a second client.inspect() call.
    detail = desktop.import_youtube(
        store.load(),
        CANONICAL_URL,
        "Overridden Title",
        "Overridden Course",
        lambda name, payload: emitted.append((name, payload)),
        inspected_metadata=inspected,
    )
    assert client.inspected == [CANONICAL_URL]
    assert client.downloaded == [CANONICAL_URL]
    assert detail["session"]["title"] == "Overridden Title"
    assert detail["session"]["course"] == "Overridden Course"
    assert detail["session"]["source_kind"] == "youtube"
    assert detail["session"]["source_url"] == CANONICAL_URL
    assert any(name == "youtube" for name, _ in emitted)


def test_desktop_services_youtube_ignores_stale_metadata_when_url_changes(tmp_path):
    store = PreferenceStore(tmp_path / "prefs.json", tmp_path / "data")
    client = FakeYouTubeClient(seconds=2)
    desktop = DesktopServices(store, youtube=YouTubeService(client_factory=lambda: client))

    # 1. Inspect video A
    inspected_a = desktop.inspect_youtube(store.load(), f"https://youtu.be/{VIDEO_ID}")
    assert client.inspected == [CANONICAL_URL]

    # 2. User changes URL to video B; stale metadata A must NOT be reused
    assert coerce_metadata(f"https://youtu.be/{VIDEO_ID_B}", inspected_a) is None
    detail_b = desktop.import_youtube(
        store.load(),
        f"https://youtu.be/{VIDEO_ID_B}",
        "",
        "",
        lambda _name, _payload: None,
        inspected_metadata=inspected_a,
    )
    assert client.inspected == [CANONICAL_URL, CANONICAL_URL_B]
    assert client.downloaded == [CANONICAL_URL_B]
    assert detail_b["session"]["video_id"] == VIDEO_ID_B
    assert detail_b["session"]["source_url"] == CANONICAL_URL_B
    assert detail_b["session"]["title"] == "Lecture 05: Page Tables"
    assert detail_b["session"]["course"] == "OS Kernel Lab"


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
        if fullname.split('.')[0] in {'yt_dlp', 'av', 'PySide6', 'faster_whisper', 'ctranslate2'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
import classscribe.youtube
import classscribe.application.youtube
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=15)


def test_resolve_node_runtime(monkeypatch, tmp_path):
    from classscribe import youtube

    # Test 1: Bundled node found beside executable in bin/
    app_root = tmp_path / "app"
    bin_dir = app_root / "bin"
    bin_dir.mkdir(parents=True)
    exe_name = "node.exe" if sys.platform == "win32" else "node"
    node_file = bin_dir / exe_name
    node_file.write_bytes(b"")

    monkeypatch.setattr(sys, "executable", str(app_root / "ClassScribe.exe"))
    assert youtube.resolve_node_runtime() == str(node_file.resolve())

    # Test 2: Fallback to PATH when no bundled node exists
    empty_root = tmp_path / "empty_app"
    empty_root.mkdir()
    monkeypatch.setattr(sys, "executable", str(empty_root / "ClassScribe.exe"))
    monkeypatch.setattr(
        youtube.shutil, "which", lambda cmd: "/usr/bin/node" if cmd == "node" else None
    )
    assert youtube.resolve_node_runtime() == "/usr/bin/node"
