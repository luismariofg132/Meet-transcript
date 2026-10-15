import sys
from types import SimpleNamespace

import pytest
from conftest import SYSTEM, FakeBackend
from test_runtime import fake_ct2

from classscribe.audio.wasapi import WasapiBackend
from classscribe.config import Settings
from classscribe.doctor import diagnose


@pytest.mark.parametrize(
    "adc,current,expected,method",
    [
        (400.0, 400.04, 99.96, "portaudio_adc"),
        (0.0, 1.0, 99.872, "callback_minus_buffer"),
    ],
)
def test_wasapi_callback_maps_clock_epochs(monkeypatch, adc, current, expected, method):
    from classscribe.audio import wasapi

    monkeypatch.setattr(wasapi.sys, "platform", "win32")
    monkeypatch.setattr(wasapi.time, "perf_counter", lambda: 100)
    opened = {}

    class Audio:
        def open(self, **kwargs):
            opened.update(kwargs)
            return object()

    module = SimpleNamespace(PyAudio=Audio, paInt16=8, paContinue=0, paAbort=2)
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", module)
    backend = WasapiBackend()
    received = []
    backend.open(SYSTEM, lambda chunk: received.append(chunk) or True)
    assert opened["input_device_index"] == SYSTEM.id
    assert opened["start"] is False
    result = opened["stream_callback"](
        bytes(4096), 1024, {"input_buffer_adc_time": adc, "current_time": current}, 0
    )
    assert result == (None, 0)
    assert received[0].captured_at == pytest.approx(expected)
    assert received[0].timing_method == method


def test_doctor_gpu_visibility_is_not_inference(monkeypatch):
    from classscribe import doctor

    monkeypatch.setattr(doctor, "query_nvidia", lambda: "NVIDIA test GPU")
    monkeypatch.setattr(doctor, "configure_cuda_libraries", lambda: None)
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda _: "test-version")
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2())
    report, ok = diagnose(
        Settings(),
        backend_factory=FakeBackend,
        engine_factory=lambda _: pytest.fail("Model should not load"),
    )
    assert ok
    assert report["cuda_inference"] == "not tested"
    assert report["default_output"] == SYSTEM.name


def test_doctor_actual_inference_failure_is_failure(monkeypatch):
    from classscribe import doctor

    monkeypatch.setattr(doctor, "query_nvidia", lambda: "NVIDIA test GPU")
    monkeypatch.setattr(doctor, "configure_cuda_libraries", lambda: None)
    monkeypatch.setattr(doctor.importlib.metadata, "version", lambda _: "test-version")
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2())

    class Broken:
        device = "cuda"
        compute_type = "int8_float16"

        def diagnose(self):
            raise RuntimeError("missing CUDA DLL")

    report, ok = diagnose(
        Settings(device="cuda"),
        inference=True,
        backend_factory=FakeBackend,
        engine_factory=lambda _: Broken(),
    )
    assert not ok
    assert report["inference"].startswith("FAILED")
    assert report["cuda_inference"] == "not tested"
