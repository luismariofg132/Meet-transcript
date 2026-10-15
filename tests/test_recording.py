import queue
import wave

import pytest
from conftest import MIC, SYSTEM, FakeBackend

from classscribe.audio.interfaces import AudioChunk
from classscribe.audio.recorder import RecordingError, record_session
from classscribe.audio.writer import TrackWriter
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Status


def stop(_):
    raise KeyboardInterrupt


@pytest.mark.parametrize("microphone", [True, False])
def test_recording_ctrl_c_and_microphone_disabled(tmp_path, microphone):
    manager = SessionManager(tmp_path)
    directory, session = manager.create("Clase")
    backend = FakeBackend()
    devices = [SYSTEM, MIC] if microphone else [SYSTEM]
    record_session(manager, directory, session, backend, devices, wait=stop, clock=lambda: 100)
    loaded = manager.load(directory)
    assert loaded.status == Status.RECORDED and loaded.recording_finalized
    assert len(loaded.tracks) == len(devices)
    assert all(stream.closed for stream in backend.streams)
    assert (directory / "microphone.wav").exists() == microphone
    for device in devices:
        with wave.open(str(directory / f"{device.source}.wav")) as audio:
            assert audio.getnframes() == 800
            assert audio.getnchannels() == device.channels
    assert loaded.tracks["system"]["start_offset_seconds"] == pytest.approx(0.1)
    if microphone:
        assert loaded.tracks["microphone"]["start_offset_seconds"] == pytest.approx(0.25)
        assert backend.events[:2] == ["open:system", "open:microphone"]


def test_recording_duration_stop(tmp_path):
    manager = SessionManager(tmp_path)
    directory, session = manager.create("Clase")
    times = iter([100, 100.2, 101, 101])
    record_session(
        manager,
        directory,
        session,
        FakeBackend(),
        [SYSTEM],
        clock=lambda: next(times),
        wait=lambda _: None,
        duration=1,
    )
    assert session.duration_seconds == 1


def test_failure_finalizes_audio(tmp_path):
    manager = SessionManager(tmp_path)
    directory, session = manager.create("Clase")

    def fail(_):
        raise OSError("Device disconnected")

    with pytest.raises(RecordingError, match="Device disconnected"):
        record_session(
            manager, directory, session, FakeBackend(), [SYSTEM], clock=lambda: 100, wait=fail
        )
    assert manager.load(directory).status == Status.FAILED
    with wave.open(str(directory / "system.wav")) as audio:
        assert audio.getnframes() == 800


def test_second_device_open_failure_closes_first(tmp_path):
    manager = SessionManager(tmp_path)
    directory, session = manager.create("Clase")

    class Broken(FakeBackend):
        def open(self, device, receive):
            if device.source == "microphone":
                raise OSError("Unsupported microphone format")
            return super().open(device, receive)

    backend = Broken()
    with pytest.raises(RecordingError):
        record_session(manager, directory, session, backend, [SYSTEM, MIC], clock=lambda: 100)
    assert backend.streams[0].closed
    assert session.status == Status.FAILED


def test_existing_audio_is_never_overwritten(tmp_path):
    manager = SessionManager(tmp_path)
    directory, session = manager.create("Clase")
    path = directory / "system.wav"
    path.write_bytes(b"previous audio")
    with pytest.raises(RecordingError):
        record_session(manager, directory, session, FakeBackend(), [SYSTEM], clock=lambda: 100)
    assert path.read_bytes() == b"previous audio"


def test_wav_rotation_and_silence_gap(tmp_path):
    writer = TrackWriter(tmp_path, MIC, 100, max_part_bytes=16000)
    assert writer.receive(AudioChunk(bytes(16000), 100.25))
    assert writer.receive(AudioChunk(bytes(16000), 102.25))
    writer.finish()
    assert writer.error is None
    metadata = writer.metadata()
    assert metadata["inserted_silence_frames"] == 8000
    assert metadata["frames"] == 24000
    assert [part["start_frame"] for part in metadata["parts"]] == [0, 8000, 16000]
    for part in metadata["parts"]:
        with wave.open(str(tmp_path / part["file"])) as audio:
            assert audio.getnframes() == 8000


@pytest.mark.parametrize("mode", ["queue", "portaudio", "invalid_frame", "clock"])
def test_capture_errors_are_not_silently_dropped(tmp_path, monkeypatch, mode):
    writer = TrackWriter(tmp_path, MIC, 100)
    if mode == "queue":

        def full(_):
            raise queue.Full

        monkeypatch.setattr(writer.queue, "put_nowait", full)
        assert not writer.receive(AudioChunk(b"\0\0", 100))
    elif mode == "portaudio":
        assert not writer.receive(AudioChunk(b"\0\0", 100, status_flags=2))
    elif mode == "invalid_frame":
        writer.receive(AudioChunk(b"\0", 100))
    else:
        writer.receive(AudioChunk(bytes(16000), 100))
        writer.receive(AudioChunk(bytes(16000), 100))
    writer.finish()
    assert writer.error is not None
    with wave.open(str(tmp_path / "microphone.wav")) as audio:
        assert audio.getnchannels() == 1
