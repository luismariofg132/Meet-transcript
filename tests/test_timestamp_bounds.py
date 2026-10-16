import json

import pytest
from test_overlap_service import ScriptedEngine, prepare_tracks

from classscribe.config import Settings
from classscribe.sessions.models import Status
from classscribe.transcription.engine import RawSegment
from classscribe.transcription.service import transcribe_session
from classscribe.transcription.timestamps import audio_interval


@pytest.mark.parametrize(
    "start,end,duration,expected",
    [
        (296.5, 301.86, 300, (296.5, 300)),
        (1, 2.05, 2, (1, 2)),
        (1, 2, 2, (1, 2)),
        (1, 32, 2, (1, 2)),
        (2, 3, 2, None),
        (3, 4, 2, None),
    ],
)
def test_audio_interval_bounds(start, end, duration, expected):
    assert audio_interval(start, end, duration) == expected


@pytest.mark.parametrize(
    "start,end",
    [
        (-0.01, 1),
        (2, 1),
        (float("nan"), 1),
        (1, float("inf")),
        (float("-inf"), 1),
        (1, float("nan")),
        (1, 330.01),
        (500, 501),
    ],
)
def test_corrupt_estimates_still_fail(start, end):
    with pytest.raises(ValueError, match="invalid chunk timestamp"):
        audio_interval(start, end, 300)


@pytest.mark.parametrize("source_kind", ["recording", "youtube"])
def test_reproduced_tail_moves_to_next_window_without_duplicate(recorded, tmp_path, source_kind):
    manager, directory, session = prepare_tracks(recorded)
    session.source_kind = source_kind
    manager.save(directory, session)
    original = (directory / "system.wav").read_bytes()
    engine = ScriptedEngine(
        [
            [RawSegment(280, 282, "Before"), RawSegment(296.5, 301.86, "Boundary speech")],
            [RawSegment(11.5, 16, "Boundary speech")],
        ]
    )
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    data = json.loads((result / "transcript.json").read_text())
    assert [s["text"] for s in data["segments"]] == ["Before", "Boundary speech"]
    expected_source = "media" if source_kind == "youtube" else "system"
    assert {s["source"] for s in data["segments"]} == {expected_source}
    assert data["segments"][-1]["audio_start"] == 296.5
    assert data["segments"][-1]["audio_end"] == 301
    assert manager.load(directory).status == Status.COMPLETED
    assert (directory / "system.wav").read_bytes() == original
    report = json.loads((result.parent / "run.json").read_text())
    assert report["timestamp_adjustments"]["clipped_ends"] == 1


def test_final_window_retains_tail_and_drops_only_padding(recorded, tmp_path):
    manager, directory, session = recorded
    engine = ScriptedEngine(
        [
            [RawSegment(0.5, 3.86, "Last real speech"), RawSegment(2, 4, "Padding")],
            [RawSegment(1, 2.05, "Mic tail")],
        ]
    )
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    rows = json.loads((result / "transcript.json").read_text())["segments"]
    assert [s["text"] for s in rows] == ["Last real speech", "Mic tail"]
    assert [s["audio_end"] for s in rows] == [2, 2]
    assert [s["end"] for s in rows] == [2.1, 2.5]
    report = json.loads((result.parent / "run.json").read_text())
    assert report["timestamp_adjustments"] == {"clipped_ends": 2, "padding_segments_dropped": 1}


def test_owned_crossing_tail_is_bounded_without_splitting_text(recorded, tmp_path):
    manager, directory, session = prepare_tracks(recorded)
    engine = ScriptedEngine([[RawSegment(280, 301.86, "Complete sentence")], []])
    result = transcribe_session(
        manager,
        directory,
        session,
        Settings(transcripts_dir=tmp_path / "t"),
        engine_factory=lambda _: engine,
    )
    rows = json.loads((result / "transcript.json").read_text())["segments"]
    assert len(rows) == 1 and rows[0]["text"] == "Complete sentence"
    assert rows[0]["audio_end"] == 300


def test_invalid_tail_preserves_partial_and_numeric_diagnostics(recorded, tmp_path):
    manager, directory, session = recorded
    engine = ScriptedEngine([[RawSegment(0, 1, "Preserved"), RawSegment(1, 100, "Private")]])
    settings = Settings(transcripts_dir=tmp_path / "t")
    with pytest.raises(ValueError, match="invalid chunk timestamp"):
        transcribe_session(manager, directory, session, settings, engine_factory=lambda _: engine)
    report_path = next(settings.transcripts_dir.glob("*/*/run.json"))
    report = json.loads(report_path.read_text())
    assert report["invalid_timestamp"] == {"start": "1", "end": "100", "window_duration": 2}
    assert "Private" not in report_path.read_text()
    assert report["segments_preserved"] == 1
    assert not (report_path.parent / "result").exists()
    assert manager.load(directory).status == Status.FAILED
