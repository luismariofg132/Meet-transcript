from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from classscribe.audio.devices import Device


@dataclass(frozen=True)
class AudioChunk:
    data: bytes
    captured_at: float
    timing_method: str = "portaudio_adc"
    status_flags: int = 0


ChunkHandler = Callable[[AudioChunk], bool]


class CaptureStream(Protocol):
    def start(self) -> None: ...
    def active(self) -> bool: ...
    def close(self) -> None: ...


class AudioBackend(Protocol):
    def devices(self) -> list[Device]: ...
    def open(self, device: Device, receive: ChunkHandler) -> CaptureStream: ...
    def close(self) -> None: ...
