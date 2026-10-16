"""Headless regressions for shared services and GUI-facing core events."""

import json
import subprocess
import sys
import wave
from threading import Event

import pytest
from conftest import MIC, SYSTEM, FakeBackend
from test_transcription import FakeEngine

from classscribe.application.library import SessionLibrary
from classscribe.application.preferences import PreferenceStore
from classscribe.application.recording import RecordingService
from classscribe.audio.interfaces import AudioChunk
from classscribe.audio.recorder import record_session
from classscribe.audio.writer import TrackWriter
from classscribe.config import Settings
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Status
from classscribe.transcription.progress import TranscriptionProgress
from classscribe.transcription.service import transcribe_session


def test_headless_imports_do_not_require_qt_or_whisper():
    script = """
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'PySide6', 'faster_whisper', 'ctranslate2', 'yt_dlp', 'av'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
import classscribe.gui.app
import classscribe.cli.commands
import classscribe.application.desktop
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=15)


def test_explicit_stop_drains_and_finalizes(tmp_path):
    manager = SessionManager(tmp_path)
    directory, session = manager.create("Graceful stop")
    backend = FakeBackend()
    stop = Event()
    levels = []

    def on_levels(system, mic):
        levels.append((system, mic))
        stop.set()

    record_session(
        manager,
        directory,
        session,
        backend,
        [SYSTEM, MIC],
        clock=lambda: 100,
        stop_event=stop,
        levels=on_levels,
    )
    saved = manager.load(directory)
    assert saved.status == Status.RECORDED and saved.recording_finalized
    assert all(stream.closed for stream in backend.streams)
    assert len(levels) == 1
    for source in ("system", "microphone"):
        with wave.open(str(directory / f"{source}.wav")) as audio:
            assert audio.getnframes() == saved.tracks[source]["frames"] == 800


def test_meter_uses_written_pcm_and_expires(tmp_path, monkeypatch):
    from classscribe.audio import writer as module

    clock = [100.0]
    monkeypatch.setattr(module.time, "perf_counter", lambda: clock[0])
    writer = TrackWriter(tmp_path, MIC, 100)
    writer.receive(AudioChunk(b"\x00\x40" * 80, 100))
    writer.finish()
    assert writer.error is None
    assert writer.audio_level() == 0.5
    clock[0] += 0.4
    assert writer.audio_level() == 0


def test_shared_recording_service_closes_backend(tmp_path):
    backend = FakeBackend()
    stop = Event()
    stop.set()

    def recorder(*args, **kwargs):
        return record_session(*args, **kwargs, clock=lambda: 100)

    result = RecordingService(backend_factory=lambda: backend, recorder=recorder).record(
        Settings(recordings_dir=tmp_path), "Service", microphone=False, stop_event=stop
    )
    assert result.session.recording_finalized
    assert backend.events[-1] == "backend:close"


def test_progress_stages_are_optional_and_monotonic(recorded, tmp_path):
    manager, directory, session = recorded
    events = []
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "transcripts"),
        engine_factory=lambda _: FakeEngine(),
        progress=events.append,
    )
    assert events[0].stage == "loading_model" and events[0].progress is None
    assert [e.stage for e in events[-3:]] == ["merging", "publishing", "completed"]
    assert events[-1].processed_seconds == events[-1].total_seconds == 4
    assert events[-1].progress == 1
    assert [e.processed_seconds for e in events] == sorted(e.processed_seconds for e in events)
    assert {e.source for e in events if e.source} == {"system", "microphone"}
    assert events[-1].device == "cpu"
    assert (result / "transcript.json").is_file()


def test_unknown_progress_is_indeterminate():
    assert TranscriptionProgress("transcribing", 0, 0).progress is None
    assert TranscriptionProgress("loading_model", 0, 100).progress is None


def test_library_repeated_runs_and_source_mapping(recorded, tmp_path):
    manager, directory, session = recorded
    settings = Settings(recordings_dir=manager.root, transcripts_dir=tmp_path / "transcripts")
    for _ in range(2):
        result = transcribe_session(
            manager, directory, session, settings, engine_factory=lambda _: FakeEngine()
        )
    library = SessionLibrary(settings)
    assert len(library.detail(session.session_id)["runs"]) == 2
    assert library.list_sessions()[0]["transcribed"]
    segments = library.transcript(result)
    assert [row["speaker"] for row in segments] == ["CLASS", "ME"]
    assert segments[0]["time"] == "00:00:00"
    assert segments[0]["text"] == "La memoria caché"


def test_preferences_persist_without_touching_cli(tmp_path):
    store = PreferenceStore(tmp_path / "gui" / "preferences.json", tmp_path / "data")
    values = store.load()
    values.update(theme="light", microphone=False, model="medium", device="cpu", language="auto")
    store.save(values)
    assert store.load() == values
    assert not (tmp_path / "classscribe.toml").exists()


@pytest.mark.parametrize(
    "key,value",
    [("theme", "invalid"), ("auto_transcribe", "yes"), ("recordings_dir", ""), ("model", "bad")],
)
def test_invalid_preferences_preserve_saved_file(tmp_path, key, value):
    store = PreferenceStore(tmp_path / "preferences.json", tmp_path)
    values = store.save(store.load())
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save({**values, key: value})
    assert store.path.read_bytes() == before


def test_library_skips_corrupt_metadata_and_rejects_external_transcript(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "session.json").write_text(json.dumps({"schema_version": 999}))
    t_dir = tmp_path / "t"
    library = SessionLibrary(Settings(recordings_dir=tmp_path, transcripts_dir=t_dir))
    assert library.list_sessions() == []
    with pytest.raises(ValueError, match="inside"):
        library.transcript(tmp_path)

    run_res = t_dir / "session" / "run" / "result"
    run_res.mkdir(parents=True)
    (run_res / "transcript.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "segments": [
                    {"source": "system", "start": 0.0, "end": 1.0, "text": "Class"},
                    {"source": "microphone", "start": 1.0, "end": 2.0, "text": "Me"},
                    {"source": "media", "start": 2.0, "end": 3.0, "text": "Video"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert [row["speaker"] for row in library.transcript(run_res)] == ["CLASS", "ME", "VIDEO"]

    (run_res / "transcript.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "segments": [{"source": "unknown", "start": 0.0, "end": 1.0, "text": "Bad"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown transcript segment source"):
        library.transcript(run_res)
