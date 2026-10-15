import json
import wave
from dataclasses import replace

import pytest
from conftest import make_wav

from classscribe.config import Settings
from classscribe.sessions.models import Status
from classscribe.transcription.chunks import audio_chunks
from classscribe.transcription.engine import RawSegment
from classscribe.transcription.service import transcribe_session
from classscribe.transcription.transcript import Segment, merge_segments


class FakeEngine:
    device = "cpu"
    compute_type = "int8"

    def transcribe(self, path, language):
        with wave.open(str(path)) as audio:
            assert audio.getnframes() > 0
        return iter([RawSegment(0.2, 0.8, " La memoria caché ")]), "es"


def test_structured_transcript_merge_and_retranscription(recorded, tmp_path):
    manager, directory, session = recorded
    settings = Settings(transcripts_dir=tmp_path / "transcripts")
    original_audio = (directory / "system.wav").read_bytes()
    result = transcribe_session(
        manager, directory, session, settings, engine_factory=lambda _: FakeEngine()
    )
    transcript = json.loads((result / "transcript.json").read_text(encoding="utf-8"))
    assert transcript["schema_version"] == 1
    assert transcript["device"] == "cpu"
    assert transcript["detected_languages"] == ["es"]
    assert [s["source"] for s in transcript["segments"]] == ["system", "microphone"]
    assert [s["start"] for s in transcript["segments"]] == pytest.approx([0.3, 0.7])
    assert transcript["segments"][0]["audio_start"] == 0.2
    md = (result / "transcript.md").read_text(encoding="utf-8")
    assert "CLASE" in md and "YO" in md and "Memoria caché" in md
    before = (result / "transcript.json").read_bytes()
    second = transcribe_session(
        manager,
        directory,
        session,
        replace(settings, model="medium"),
        engine_factory=lambda _: FakeEngine(),
    )
    assert result != second
    assert (result / "transcript.json").read_bytes() == before
    assert (directory / "system.wav").read_bytes() == original_audio
    assert len(manager.load(directory).transcription_runs) == 2
    assert manager.load(directory).status == Status.COMPLETED


@pytest.mark.parametrize("failure", [RuntimeError("private transcript text"), KeyboardInterrupt()])
def test_partial_transcript_and_failure_diagnostics(recorded, tmp_path, failure, caplog):
    manager, directory, session = recorded

    class BrokenEngine(FakeEngine):
        def transcribe(self, path, language):
            def generate():
                yield RawSegment(0, 1, "preserved words")
                raise failure

            return generate(), "es"

    settings = Settings(transcripts_dir=tmp_path / "transcripts")
    with pytest.raises(type(failure)):
        transcribe_session(
            manager, directory, session, settings, engine_factory=lambda _: BrokenEngine()
        )
    run = next((settings.transcripts_dir / session.session_id).iterdir())
    assert not (run / "result").exists()
    partial = (run / "segments.partial.jsonl").read_text(encoding="utf-8")
    assert json.loads(partial)["text"] == "preserved words"
    report = json.loads((run / "run.json").read_text())
    assert report["segments_preserved"] == 1
    assert report["status"] == "failed"
    assert "private transcript text" not in (run / "run.json").read_text()
    assert "preserved words" not in caplog.text
    assert manager.load(directory).status == Status.FAILED
    # A failed transcription may be retried; the original audio is finalized.
    result = transcribe_session(
        manager, directory, session, settings, engine_factory=lambda _: FakeEngine()
    )
    assert (result / "transcript.json").exists()


def test_transcription_refuses_active_or_unfinalized_recording(recorded, tmp_path):
    manager, directory, session = recorded
    session.status = Status.RECORDING
    session.recording_finalized = False
    manager.save(directory, session)

    def forbidden(_):
        pytest.fail("Model loaded during recording")

    with pytest.raises(ValueError, match="finalized"):
        transcribe_session(
            manager,
            directory,
            session,
            Settings(transcripts_dir=tmp_path / "t"),
            engine_factory=forbidden,
        )


def test_path_traversal_rejected(recorded, tmp_path):
    manager, directory, session = recorded
    session.tracks["system"]["parts"][0]["file"] = "../outside.wav"
    manager.save(directory, session)
    with pytest.raises(ValueError, match="inside"):
        transcribe_session(
            manager,
            directory,
            session,
            Settings(transcripts_dir=tmp_path / "t"),
            engine_factory=lambda _: FakeEngine(),
        )


def test_model_failure_leaves_run_diagnostics(recorded, tmp_path):
    manager, directory, session = recorded

    def failure(_):
        raise RuntimeError("No CUDA runtime")

    with pytest.raises(RuntimeError):
        transcribe_session(
            manager,
            directory,
            session,
            Settings(transcripts_dir=tmp_path / "t"),
            engine_factory=failure,
        )
    reports = list((tmp_path / "t").glob("*/*/run.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text())["error_type"] == "RuntimeError"


def test_merge_interleaves_sources_and_preserves_overlap():
    segments = [
        Segment("system", 4, 7, "a", "es", "system.wav", 4, 7),
        Segment("microphone", 2, 5, "b", "es", "microphone.wav", 2, 5),
    ]
    assert [s.text for s in merge_segments(segments)] == ["b", "a"]


@pytest.mark.parametrize("start,end", [(-1, 0), (2, 1), (float("nan"), 2), (0, float("inf"))])
def test_invalid_segment_intervals(start, end):
    with pytest.raises(ValueError):
        Segment("system", start, end, "x", "es", "system.wav", 0, 1)


def test_audio_chunks_bound_memory_and_preserve_offsets(tmp_path):
    source = tmp_path / "system.wav"
    make_wav(source, seconds=5, rate=8000)
    offsets = []
    for path, start, duration in audio_chunks(source, tmp_path, seconds=2):
        offsets.append((start, duration))
        with wave.open(str(path)) as audio:
            assert audio.getnframes() <= 16000
    assert offsets == [(0, 2), (2, 2), (4, 1)]
    assert list(tmp_path.iterdir()) == [source]


def test_rotated_part_offsets(recorded, tmp_path):
    manager, directory, session = recorded
    make_wav(directory / "system-0002.wav")
    session.tracks["system"]["parts"].append(
        {"file": "system-0002.wav", "start_frame": 16000, "frames": 16000}
    )
    session.tracks["system"]["frames"] = 32000
    manager.save(directory, session)
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: FakeEngine(),
    )
    segments = json.loads((result / "transcript.json").read_text())["segments"]
    rotated = next(s for s in segments if s["audio_file"] == "system-0002.wav")
    assert rotated["start"] == pytest.approx(2.3)
    assert rotated["audio_start"] == pytest.approx(0.2)
