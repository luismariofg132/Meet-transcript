import struct
import wave
from contextlib import closing

import pytest
from conftest import make_wav

from classscribe.transcription.chunks import AudioWindow, audio_chunks


@pytest.mark.parametrize(
    "duration,starts",
    [
        (0, []),
        (1, [0]),
        (299, [0]),
        (300, [0]),
        (301, [0, 285]),
        (585, [0, 285]),
        (586, [0, 285, 570]),
        (1000, [0, 285, 570, 855]),
    ],
)
def test_default_window_progression_and_no_redundant_tail(tmp_path, duration, starts):
    source = tmp_path / "source.wav"
    make_wav(source, seconds=duration, rate=20)
    windows = []
    for window in audio_chunks(source, tmp_path):
        with wave.open(str(window.path)) as audio:
            assert audio.getnframes() == round(window.duration * 20)
            assert audio.getnframes() <= 300 * 20
        windows.append(window)
    assert [window.start for window in windows] == starts
    assert len(starts) == len(set(starts))
    if windows:
        assert windows[0].keep_start == 0
        assert windows[-1].keep_end == duration
        assert windows[-1].end == duration
        assert sum(window.is_last for window in windows) == 1
        for previous, current in zip(windows, windows[1:], strict=False):
            assert previous.keep_end == current.keep_start
            assert previous.end - current.start == 15
        if len(windows) > 1:
            assert windows[-1].duration > 15  # Context plus new audio, never context alone.
    assert list(tmp_path.iterdir()) == [source]


def test_first_middle_and_last_ownership(tmp_path):
    source = tmp_path / "source.wav"
    make_wav(source, seconds=1000, rate=20)
    windows = list(audio_chunks(source, tmp_path))
    assert [(w.keep_start, w.keep_end) for w in windows] == [
        (0, 292.5),
        (292.5, 577.5),
        (577.5, 862.5),
        (862.5, 1000),
    ]


@pytest.mark.parametrize("overlap", [-1, 300, 301, float("nan"), float("inf")])
def test_invalid_overlap_rejected_before_creating_files(tmp_path, overlap):
    with pytest.raises(ValueError, match="Overlap"):
        list(audio_chunks(tmp_path / "missing.wav", tmp_path, overlap_seconds=overlap))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_invalid_window_rejected(tmp_path, seconds):
    with pytest.raises(ValueError, match="Window duration"):
        list(audio_chunks(tmp_path / "missing.wav", tmp_path, seconds=seconds, overlap_seconds=0))


@pytest.mark.parametrize("seconds,overlap", [(0.01, 0), (1, 0.99)])
def test_subsample_parameters_must_still_produce_valid_stride(tmp_path, seconds, overlap):
    source = tmp_path / "source.wav"
    make_wav(source, rate=20)
    with pytest.raises(ValueError, match="sample rate"):
        list(audio_chunks(source, tmp_path, seconds=seconds, overlap_seconds=overlap))
    assert list(tmp_path.iterdir()) == [source]


def test_zero_overlap_is_sequential_with_complete_ownership(tmp_path):
    source = tmp_path / "source.wav"
    make_wav(source, seconds=7, rate=20)
    windows = list(audio_chunks(source, tmp_path, seconds=3, overlap_seconds=0))
    assert [(w.start, w.end) for w in windows] == [(0, 3), (3, 6), (6, 7)]
    assert all((w.keep_start, w.keep_end) == (w.start, w.end) for w in windows)


def test_large_valid_overlap_still_partitions_ownership(tmp_path):
    source = tmp_path / "source.wav"
    make_wav(source, seconds=7, rate=20)
    windows = list(audio_chunks(source, tmp_path, seconds=3, overlap_seconds=2))
    assert [w.start for w in windows] == [0, 1, 2, 3, 4]
    for tick in range(141):
        point = tick / 20
        assert sum(window.owns(point, point) for window in windows) == 1


def test_overlap_wav_contains_the_original_samples(tmp_path):
    source = tmp_path / "source.wav"
    rate = 20
    pcm = struct.pack("<" + "h" * (301 * rate), *range(301 * rate))
    with wave.open(str(source), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "PCM"))
        audio.writeframes(pcm)
    for window in audio_chunks(source, tmp_path):
        with wave.open(str(window.path)) as audio:
            captured = audio.readframes(audio.getnframes())
        assert captured == pcm[round(window.start * rate) * 2 : round(window.end * rate) * 2]
    assert source.read_bytes()[44:] == pcm


def test_explicit_generator_close_removes_temporary_window(tmp_path):
    source = tmp_path / "source.wav"
    make_wav(source, seconds=301, rate=20)
    with closing(audio_chunks(source, tmp_path)) as windows:
        window = next(windows)
        assert window.path.exists()
    assert not window.path.exists()
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize(
    "start,end,owned",
    [
        (285, 290, False),
        (293, 295, True),
        (291, 295, True),  # Crosses boundary; midpoint 293 belongs to this window.
        (290, 294, False),  # Crosses boundary; midpoint 292 belongs to previous window.
        (291, 294, True),  # Exact midpoint 292.5 belongs to the right-hand window.
        (577, 578, False),  # Exact right boundary belongs to the next window.
        (580, 585, False),
    ],
)
def test_segment_midpoint_ownership(tmp_path, start, end, owned):
    window = AudioWindow(tmp_path / "chunk.wav", 285, 585, 292.5, 577.5, False)
    assert window.owns(start, end) is owned


def test_first_and_last_endpoint_segments_are_owned(tmp_path):
    first = AudioWindow(tmp_path / "chunk.wav", 0, 300, 0, 292.5, False)
    last = AudioWindow(tmp_path / "chunk.wav", 285, 301, 292.5, 301, True)
    assert first.owns(0, 0)
    assert last.owns(301, 301)
    assert not first.owns(292.5, 292.5)
    assert last.owns(292.5, 292.5)
