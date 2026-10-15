"""Read-only device diagnostics; inference is opt-in and uses synthetic silence."""

import importlib.metadata
import platform
import sys
from collections.abc import Callable
from typing import Any

from classscribe.audio.interfaces import AudioBackend
from classscribe.audio.wasapi import WasapiBackend
from classscribe.config import Settings
from classscribe.transcription.engine import CUDA_HELP, WhisperEngine, load_engine
from classscribe.transcription.runtime import configure_cuda_libraries, query_nvidia


def diagnose(
    settings: Settings,
    *,
    inference: bool = False,
    backend_factory: Callable[[], AudioBackend] = WasapiBackend,
    engine_factory: Callable[[Settings], WhisperEngine] = load_engine,
) -> tuple[dict[str, Any], bool]:
    report: dict[str, Any] = {
        "python": sys.version.split()[0],
        "operating_system": f"{platform.system()} {platform.release()}",
        "audio_backend": "unavailable",
        "default_output": None,
        "default_microphone": None,
        "nvidia": query_nvidia(),
        "cuda_inference": "not tested",
    }
    for package in ("PyAudioWPatch", "faster-whisper", "ctranslate2"):
        try:
            report[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report[package] = "not installed"
    try:
        backend = backend_factory()
        try:
            devices = backend.devices()
            report["audio_backend"] = "WASAPI available (capture not tested)"
            for source, key in (("system", "default_output"), ("microphone", "default_microphone")):
                report[key] = next(
                    (d.name for d in devices if d.source == source and d.is_default), None
                )
        finally:
            backend.close()
    except Exception as exc:
        report["audio_error"] = str(exc)
    try:
        configure_cuda_libraries()
        import ctranslate2

        report["cuda_device_count"] = ctranslate2.get_cuda_device_count()
        report["ctranslate2_import"] = "ok; GPU visibility alone does not validate inference"
    except Exception as exc:
        report["ctranslate2_import"] = f"failed ({type(exc).__name__}); check installation"
    ok = report["faster-whisper"] != "not installed" and "cuda_device_count" in report
    if platform.system() == "Windows":
        ok = ok and "audio_error" not in report and report["default_output"] is not None
    if inference:
        try:
            engine = engine_factory(settings)
            engine.diagnose()
            report["inference"] = (
                f"passed: {engine.device} / {engine.compute_type} / {settings.model}"
            )
            if engine.device == "cuda":
                report["cuda_inference"] = (
                    "passed: real inference, VAD disabled, generator exhausted"
                )
        except Exception as exc:
            report["inference"] = f"FAILED ({type(exc).__name__}): {exc}"
            report["help"] = CUDA_HELP
            ok = False
    return report, ok
