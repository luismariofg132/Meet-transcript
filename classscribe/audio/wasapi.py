"""The only module that knows about PyAudioWPatch and WASAPI."""

import math
import sys
import time
from typing import Any

from classscribe.audio.devices import Device, map_devices
from classscribe.audio.interfaces import AudioChunk, ChunkHandler


class WasapiStream:
    def __init__(self, stream: Any) -> None:
        self.stream = stream

    def start(self) -> None:
        self.stream.start_stream()

    def active(self) -> bool:
        return bool(self.stream.is_active())

    def close(self) -> None:
        try:
            if self.stream.is_active():
                self.stream.stop_stream()
        finally:
            self.stream.close()


class WasapiBackend:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Audio capture requires Windows 10/11 WASAPI")
        try:
            import pyaudiowpatch
        except ImportError as exc:
            raise RuntimeError('Install audio support: pip install -e ".[audio]"') from exc
        self.module = pyaudiowpatch
        self.audio = pyaudiowpatch.PyAudio()

    def devices(self) -> list[Device]:
        host = self.audio.get_host_api_info_by_type(self.module.paWASAPI)
        default_loopback = -1
        try:
            default_loopback = int(self.audio.get_default_wasapi_loopback()["index"])
        except (OSError, ValueError):
            pass
        records = list(self.audio.get_device_info_generator())
        return map_devices(
            records, int(host["index"]), default_loopback, int(host["defaultInputDevice"])
        )

    def open(self, device: Device, receive: ChunkHandler) -> WasapiStream:
        def callback(
            data: bytes, frame_count: int, times: dict[str, float], flags: int
        ) -> tuple[None, int]:
            # PortAudio clocks need not share an epoch across streams. Map their ADC
            # age onto perf_counter at each callback, rather than equating epochs.
            now = time.perf_counter()
            adc = times.get("input_buffer_adc_time", 0.0)
            current = times.get("current_time", 0.0)
            age = current - adc
            valid = adc > 0 and math.isfinite(age) and 0 <= age <= 10
            method = "portaudio_adc" if valid else "callback_minus_buffer"
            captured_at = now - (age if valid else frame_count / device.sample_rate)
            accepted = receive(AudioChunk(data, captured_at, method, flags))
            return None, self.module.paContinue if accepted else self.module.paAbort

        stream = self.audio.open(
            format=self.module.paInt16,
            channels=device.channels,
            rate=device.sample_rate,
            input=True,
            input_device_index=device.id,
            frames_per_buffer=1024,
            stream_callback=callback,
            start=False,
        )
        return WasapiStream(stream)

    def close(self) -> None:
        self.audio.terminate()
