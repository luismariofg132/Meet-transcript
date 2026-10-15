import socket
import wave
from pathlib import Path

import pytest

from classscribe.audio.devices import Device
from classscribe.audio.interfaces import AudioChunk, ChunkHandler
from classscribe.sessions.manager import SessionManager
from classscribe.sessions.models import Status

SYSTEM = Device(10, "Speakers [Loopback]", "system", 8000, 2, True)
MIC = Device(4, "Microphone", "microphone", 8000, 1, True)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Offline tests must not access the network")

    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)


def make_wav(path: Path, seconds: int = 2, channels: int = 1, rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setparams((channels, 2, rate, 0, "NONE", "PCM"))
        handle.writeframes(b"\x01\x00" * channels * rate * seconds)


class FakeStream:
    def __init__(self, device: Device, receive: ChunkHandler, events: list[str]) -> None:
        self.device = device
        self.receive = receive
        self.events = events
        self.running = False
        self.closed = False

    def start(self) -> None:
        self.events.append(f"start:{self.device.source}")
        self.running = True
        offset = 0.1 if self.device.source == "system" else 0.25
        self.receive(AudioChunk(bytes(2 * self.device.channels * 800), 100 + offset))

    def active(self) -> bool:
        return self.running

    def close(self) -> None:
        self.running = False
        self.closed = True
        self.events.append(f"close:{self.device.source}")


class FakeBackend:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.streams: list[FakeStream] = []

    def devices(self) -> list[Device]:
        return [SYSTEM, MIC]

    def open(self, device: Device, receive: ChunkHandler) -> FakeStream:
        self.events.append(f"open:{device.source}")
        stream = FakeStream(device, receive, self.events)
        self.streams.append(stream)
        return stream

    def close(self) -> None:
        self.events.append("backend:close")


@pytest.fixture
def recorded(tmp_path):
    manager = SessionManager(tmp_path / "recordings")
    directory, session = manager.create("Memoria caché", "Arquitectura")
    session.transition(Status.RECORDING)
    session.started_at = "2026-10-15T18:30:00-05:00"
    session.ended_at = "2026-10-15T18:30:03-05:00"
    session.duration_seconds = 3
    for source, offset in (("system", 0.1), ("microphone", 0.5)):
        make_wav(directory / f"{source}.wav")
        session.tracks[source] = {
            "sample_rate": 8000,
            "channels": 1,
            "frames": 16000,
            "start_offset_seconds": offset,
            "parts": [{"file": f"{source}.wav", "start_frame": 0, "frames": 16000}],
        }
    session.recording_finalized = True
    session.transition(Status.RECORDED)
    manager.save(directory, session)
    return manager, directory, session
