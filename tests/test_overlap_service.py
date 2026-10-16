import json
import wave
from pathlib import Path

import pytest
from conftest import make_wav

from classscribe.config import Settings
from classscribe.sessions.models import Status
from classscribe.transcription.engine import RawSegment
from classscribe.transcription.service import transcribe_session

CHUNKING = {
    "window_seconds": 300,
    "overlap_seconds": 15,
    "deduplication": "midpoint_ownership",
}


class ScriptedEngine:
    device = "cpu"
    compute_type = "int8"

    def __init__(self, scripts: list[list[RawSegment | BaseException]]) -> None:
        self.scripts = scripts
        self.paths: list[Path] = []
        self.durations: list[float] = []

    def transcribe(self, path: Path, language: str):
        script = self.scripts[len(self.paths)]
        self.paths.append(path)
        with wave.open(str(path)) as audio:
            self.durations.append(audio.getnframes() / audio.getframerate())

        def generate():
            for item in script:
                if isinstance(item, BaseException):
                    raise item
                yield item

        return generate(), "es"


def prepare_tracks(recorded, sources=("system",), parts=1):
    manager, directory, session = recorded
    session.tracks = {}
    for source in sources:
        part_metadata = []
        for number in range(parts):
            name = f"{source}.wav" if number == 0 else f"{source}-{number + 1:04}.wav"
            make_wav(directory / name, seconds=301, rate=20)
            part_metadata.append({"file": name, "start_frame": number * 6020, "frames": 6020})
        session.tracks[source] = {
            "sample_rate": 20,
            "channels": 1,
            "frames": 6020 * parts,
            "start_offset_seconds": 7.25 if source == "system" else 7.5,
            "parts": part_metadata,
        }
    session.duration_seconds = 7.5 + 301 * parts
    manager.save(directory, session)
    return manager, directory, session


def read_journal(run):
    return [json.loads(line) for line in (run / "segments.partial.jsonl").read_text().splitlines()]


def boundary_script():
    return [
        [
            RawSegment(0, 1, "start"),
            RawSegment(10, 11, "Remember this."),
            RawSegment(290, 291, "left"),
            RawSegment(291, 295, "complete crossing sentence"),
            RawSegment(296, 297, "right"),
        ],
        [
            RawSegment(5, 6, "left"),
            RawSegment(6, 10, "complete crossing sentence"),
            RawSegment(11, 12, "right"),
            RawSegment(14, 15, "Remember this."),
            RawSegment(15, 16, "end"),
        ],
    ]


def test_owned_boundary_segments_and_original_timestamps(recorded, tmp_path):
    manager, directory, session = prepare_tracks(recorded)
    original = (directory / "system.wav").read_bytes()
    engine = ScriptedEngine(boundary_script())
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    transcript = json.loads((result / "transcript.json").read_text())
    segments = transcript["segments"]
    assert [s["text"] for s in segments] == [
        "start",
        "Remember this.",
        "left",
        "complete crossing sentence",
        "right",
        "Remember this.",
        "end",
    ]
    crossing = segments[3]
    assert (crossing["audio_start"], crossing["audio_end"]) == (291, 295)
    assert (crossing["start"], crossing["end"]) == (298.25, 302.25)
    assert crossing["audio_file"] == "system.wav"
    assert segments[-1]["audio_end"] == 301
    assert engine.durations == [300, 16]
    assert read_journal(result.parent) == segments
    assert transcript["chunking"] == CHUNKING
    report = json.loads((result.parent / "run.json").read_text())
    assert report["chunking"] == CHUNKING
    assert report["segments_preserved"] == 7
    assert (report["keep_start_seconds"], report["keep_end_seconds"]) == (292.5, 301)
    assert (directory / "system.wav").read_bytes() == original
    assert not any(path.exists() for path in engine.paths)


def test_identical_text_on_both_sides_of_boundary_is_not_text_deduplicated(recorded, tmp_path):
    manager, directory, session = prepare_tracks(recorded)
    engine = ScriptedEngine(
        [
            [RawSegment(290, 291, "Repeat."), RawSegment(294, 295, "Repeat.")],
            [RawSegment(5, 6, "Repeat."), RawSegment(9, 10, "Repeat.")],
        ]
    )
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    segments = json.loads((result / "transcript.json").read_text())["segments"]
    assert [s["text"] for s in segments] == ["Repeat.", "Repeat."]
    assert [s["audio_start"] for s in segments] == [290, 294]


def test_sources_keep_identical_overlapping_speech_and_merge_chronologically(recorded, tmp_path):
    manager, directory, session = prepare_tracks(recorded, sources=("system", "microphone"))
    scripts = [
        [RawSegment(290, 291, "Same words"), RawSegment(293, 295, "Same words")],
        [RawSegment(5, 6, "Same words"), RawSegment(8, 10, "Same words")],
    ]
    engine = ScriptedEngine(scripts * 2)
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    segments = json.loads((result / "transcript.json").read_text())["segments"]
    assert [s["source"] for s in segments] == ["system", "microphone", "system", "microphone"]
    assert [s["start"] for s in segments] == [297.25, 297.5, 300.25, 300.5]
    assert [s["text"] for s in segments] == ["Same words"] * 4
    assert segments[0]["end"] > segments[1]["start"]
    assert len(read_journal(result.parent)) == 4


def test_rotated_parts_restart_windows_and_preserve_part_offsets(recorded, tmp_path):
    manager, directory, session = prepare_tracks(recorded, parts=2)
    scripts = [
        [RawSegment(0, 1, "start"), RawSegment(293, 295, "boundary")],
        [RawSegment(8, 10, "boundary"), RawSegment(15, 16, "end")],
    ]
    engine = ScriptedEngine(scripts * 2)
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    segments = json.loads((result / "transcript.json").read_text())["segments"]
    assert engine.durations == [300, 16, 300, 16]
    assert [s["audio_file"] for s in segments] == ["system.wav"] * 3 + ["system-0002.wav"] * 3
    assert [s["audio_start"] for s in segments] == [0, 293, 300] * 2
    assert [s["start"] for s in segments] == [7.25, 300.25, 307.25, 308.25, 601.25, 608.25]
    assert [s["audio_end"] for s in segments] == [1, 295, 301] * 2


@pytest.mark.parametrize("failure", [RuntimeError("late failure"), KeyboardInterrupt()])
def test_later_chunk_failure_keeps_only_owned_journal_and_retry_is_new(recorded, tmp_path, failure):
    manager, directory, session = prepare_tracks(recorded)
    original = (directory / "system.wav").read_bytes()
    engine = ScriptedEngine(
        [
            [RawSegment(290, 291, "left"), RawSegment(293, 295, "right")],
            [RawSegment(5, 6, "left"), RawSegment(8, 10, "right"), failure],
        ]
    )
    settings = Settings(transcripts_dir=tmp_path / "t")
    with pytest.raises(type(failure)):
        transcribe_session(manager, directory, session, settings, engine_factory=lambda _: engine)
    run = next((settings.transcripts_dir / session.session_id).iterdir())
    partial_before = (run / "segments.partial.jsonl").read_bytes()
    assert [s["text"] for s in read_journal(run)] == ["left", "right"]
    assert not (run / "result").exists()
    assert not list(run.glob("audio-*"))
    assert not any(path.exists() for path in engine.paths)
    report = json.loads((run / "run.json").read_text())
    assert report["status"] == "failed"
    assert report["segments_preserved"] == 2
    assert report["chunk_start_seconds"] == 285
    assert report["chunking"] == CHUNKING
    assert manager.load(directory).status == Status.FAILED
    retry = ScriptedEngine(boundary_script())
    result = transcribe_session(
        manager, directory, session, settings, engine_factory=lambda _: retry
    )
    assert result.parent != run
    assert (run / "segments.partial.jsonl").read_bytes() == partial_before
    assert (directory / "system.wav").read_bytes() == original
    assert manager.load(directory).status == Status.COMPLETED


def test_single_window_results_match_normal_decode(recorded, tmp_path):
    manager, directory, session = recorded
    engine = ScriptedEngine([[RawSegment(0, 2, "full short recording")]] * 2)
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    segments = json.loads((result / "transcript.json").read_text())["segments"]
    assert engine.durations == [2, 2]
    assert [s["audio_start"] for s in segments] == [0, 0]
    assert [s["audio_end"] for s in segments] == [2, 2]
    assert [s["start"] for s in segments] == [0.1, 0.5]
    assert [s["end"] for s in segments] == [2.1, 2.5]
