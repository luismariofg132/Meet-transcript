import logging
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from classscribe.config import Settings
from classscribe.transcription.runtime import configure_cuda_libraries, select_compute

logger = logging.getLogger(__name__)
CUDA_HELP = (
    "Check the NVIDIA driver, CUDA 12 cuBLAS and cuDNN 9 libraries; run doctor --device cuda. "
    "For limited VRAM use --model small or tiny. To use CPU, explicitly pass --device cpu."
)


@dataclass(frozen=True)
class RawSegment:
    start: float
    end: float
    text: str


class Engine(Protocol):
    device: str
    compute_type: str

    def transcribe(self, path: Path, language: str) -> tuple[Iterable[RawSegment], str]: ...


class WhisperEngine:
    def __init__(self, model: Any, device: str, compute_type: str) -> None:
        self.model = model
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, path: Path, language: str) -> tuple[Iterable[RawSegment], str]:
        try:
            segments, info = self.model.transcribe(
                str(path),
                language=None if language == "auto" else language,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=True,
            )
        except Exception as exc:
            raise RuntimeError(self._error()) from exc

        def consume() -> Iterator[RawSegment]:
            try:
                for segment in segments:
                    yield RawSegment(segment.start, segment.end, segment.text)
            except Exception as exc:
                raise RuntimeError(self._error()) from exc

        return consume(), info.language

    def _error(self) -> str:
        return f"Whisper inference failed on {self.device}. " + (
            CUDA_HELP if self.device == "cuda" else "Check the audio and available memory."
        )

    def diagnose(self) -> None:
        import numpy as np

        # VAD must be disabled: filtering silence would bypass actual inference.
        segments, _ = self.model.transcribe(
            np.zeros(16000, dtype=np.float32), language="es", vad_filter=False, beam_size=1
        )
        for _ in segments:
            pass


def load_engine(settings: Settings) -> WhisperEngine:
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    configure_cuda_libraries()
    try:
        import ctranslate2
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
        from huggingface_hub.errors import LocalEntryNotFoundError
    except ImportError as exc:
        raise RuntimeError(
            'Install transcription support: pip install -e ".[transcription]"'
        ) from exc
    try:
        device, compute = select_compute(settings.device, ctranslate2)
    except Exception as exc:
        raise RuntimeError(f"Cannot select inference device. {CUDA_HELP}") from exc
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    try:
        model_path = download_model(
            settings.model, cache_dir=str(settings.models_dir), local_files_only=True
        )
    except LocalEntryNotFoundError as exc:
        if settings.offline:
            raise RuntimeError(
                "Model is not cached; run once without --offline to download it."
            ) from exc
        logger.info("Downloading model weights to local cache")
        model_path = download_model(settings.model, cache_dir=str(settings.models_dir))
    logger.info("Loading model=%s device=%s compute_type=%s", settings.model, device, compute)
    try:
        model = WhisperModel(
            model_path,
            device=device,
            compute_type=compute,
            cpu_threads=min(8, os.cpu_count() or 1),
            num_workers=1,
            local_files_only=True,
        )
    except Exception as exc:
        hint = CUDA_HELP if device == "cuda" else "Check model cache and available RAM."
        raise RuntimeError(f"Model could not load on {device}. {hint}") from exc
    return WhisperEngine(model, device, compute)
