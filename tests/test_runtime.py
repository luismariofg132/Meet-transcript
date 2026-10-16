import sys
from types import SimpleNamespace

import pytest

from classscribe.config import Settings
from classscribe.transcription.engine import WhisperEngine, load_engine
from classscribe.transcription.runtime import select_compute


def fake_ct2(count=1, supported=None):
    return SimpleNamespace(
        get_cuda_device_count=lambda: count,
        get_supported_compute_types=lambda *a, **kw: (
            supported or {"int8_float16", "int8", "float32"}
        ),
    )


@pytest.mark.parametrize(
    "requested,count,expected",
    [("cuda", 1, "cuda"), ("auto", 1, "cuda"), ("auto", 0, "cpu"), ("cpu", 1, "cpu")],
)
def test_device_and_compute_selection(requested, count, expected):
    device, compute = select_compute(requested, fake_ct2(count))
    assert device == expected
    assert compute == ("int8_float16" if expected == "cuda" else "int8")


def test_explicit_cuda_never_falls_back():
    with pytest.raises(RuntimeError, match="No compatible NVIDIA"):
        select_compute("cuda", fake_ct2(0))


def test_compute_fallback_stays_on_gpu():
    assert select_compute("cuda", fake_ct2(supported={"float32"})) == ("cuda", "float32")


@pytest.mark.parametrize("requested", ["cuda", "auto"])
def test_model_load_cuda_error_never_retries_cpu(monkeypatch, tmp_path, requested):
    from classscribe.transcription import engine

    calls = []

    def broken_model(path, **kwargs):
        calls.append(kwargs["device"])
        raise RuntimeError("CUDA allocation error")

    monkeypatch.setattr(engine, "configure_cuda_libraries", lambda: None)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2())
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=broken_model))
    monkeypatch.setitem(
        sys.modules,
        "faster_whisper.utils",
        SimpleNamespace(download_model=lambda *a, **k: str(tmp_path)),
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub.errors",
        SimpleNamespace(LocalEntryNotFoundError=FileNotFoundError),
    )
    with pytest.raises(RuntimeError, match="could not load on cuda"):
        load_engine(Settings(device=requested, models_dir=tmp_path))
    assert calls == ["cuda"]


def test_diagnostic_disables_vad_and_exhausts_generator(monkeypatch):
    events = []

    class Model:
        def transcribe(self, audio, **kwargs):
            assert kwargs["vad_filter"] is False
            assert kwargs["language"] == "es"

            def generate():
                events.append("real-inference")
                yield object()
                events.append("exhausted")

            return generate(), None

    monkeypatch.setitem(
        sys.modules, "numpy", SimpleNamespace(zeros=lambda *a, **k: "silence", float32="float32")
    )
    WhisperEngine(Model(), "cuda", "int8_float16").diagnose()
    assert events == ["real-inference", "exhausted"]


def test_lazy_inference_error_does_not_retry_cpu(tmp_path):
    calls = []

    class Model:
        def transcribe(self, path, **kwargs):
            calls.append(path)

            def fail():
                raise RuntimeError("CUDA error")
                yield

            return fail(), SimpleNamespace(language="es")

    segments, _ = WhisperEngine(Model(), "cuda", "int8_float16").transcribe(
        tmp_path / "x.wav", "es"
    )
    with pytest.raises(RuntimeError, match="Whisper inference failed on cuda"):
        list(segments)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "cached,offline", [(True, True), (True, False), (False, True), (False, False)]
)
def test_model_cache_and_offline_behavior(monkeypatch, tmp_path, cached, offline):
    from classscribe.transcription import engine

    downloads = []

    def download(*args, **kwargs):
        downloads.append(kwargs.get("local_files_only", False))
        if kwargs.get("local_files_only") and not cached:
            raise FileNotFoundError("cache missing")
        return str(tmp_path)

    monkeypatch.setattr(engine, "configure_cuda_libraries", lambda: None)
    monkeypatch.setitem(sys.modules, "ctranslate2", fake_ct2(count=0))
    monkeypatch.setitem(
        sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *a, **k: object())
    )
    monkeypatch.setitem(
        sys.modules, "faster_whisper.utils", SimpleNamespace(download_model=download)
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub.errors",
        SimpleNamespace(LocalEntryNotFoundError=FileNotFoundError),
    )
    settings = Settings(models_dir=tmp_path, offline=offline)
    if offline and not cached:
        with pytest.raises(RuntimeError, match="not cached"):
            load_engine(settings)
    else:
        assert load_engine(settings).device == "cpu"
    assert downloads == ([True, False] if not cached and not offline else [True])


def test_windows_dll_handles_retained_and_registration_idempotent(monkeypatch, tmp_path):
    from classscribe.transcription import runtime

    cublas_dir = tmp_path / "nvidia" / "cublas" / "bin"
    cudnn_dir = tmp_path / "nvidia" / "cudnn" / "bin"
    cublas_dir.mkdir(parents=True)
    cudnn_dir.mkdir(parents=True)
    (cublas_dir / "cublas64_12.dll").write_bytes(b"")
    (cudnn_dir / "cudnn64_9.dll").write_bytes(b"")
    handles = []

    def register(path):
        handle = object()
        handles.append(handle)
        return handle

    fake_os = SimpleNamespace(
        name="nt", pathsep=";", environ={"PATH": "existing"}, add_dll_directory=register
    )
    monkeypatch.setattr(runtime, "os", fake_os)
    monkeypatch.setattr(runtime, "_registered", set())
    monkeypatch.setattr(runtime, "_dll_handles", [])
    monkeypatch.setattr(
        runtime.importlib.util,
        "find_spec",
        lambda pkg: (
            SimpleNamespace(submodule_search_locations=[str(tmp_path / "nvidia")])
            if pkg == "nvidia"
            else None
        ),
    )
    runtime.configure_cuda_libraries()
    runtime.configure_cuda_libraries()
    assert len(handles) == 2
    assert runtime._dll_handles == handles
    assert str(cublas_dir) in fake_os.environ["PATH"]
    assert str(cudnn_dir) in fake_os.environ["PATH"]


def test_pyproject_cuda_extra_includes_windows_cudnn():
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    cuda_deps = data["project"]["optional-dependencies"]["cuda"]
    assert any(
        dep.startswith("nvidia-cublas-cu12") and "sys_platform" not in dep for dep in cuda_deps
    )
    assert any(
        dep.startswith("nvidia-cudnn-cu12") and "sys_platform" not in dep for dep in cuda_deps
    )


def test_configure_cuda_libraries_packaged_app_fallback(monkeypatch, tmp_path):
    from classscribe.transcription import runtime

    app_root = tmp_path / "ClassScribe"
    cublas_dir = app_root / "nvidia" / "cublas" / "bin"
    cublas_dir.mkdir(parents=True)
    (cublas_dir / "cublas64_12.dll").write_bytes(b"")

    ct2_dir = app_root / "ctranslate2"
    ct2_dir.mkdir(parents=True)
    (ct2_dir / "ctranslate2.dll").write_bytes(b"")

    handles = []

    def register(path):
        handle = object()
        handles.append(handle)
        return handle

    fake_os = SimpleNamespace(
        name="nt", pathsep=";", environ={"PATH": "existing"}, add_dll_directory=register
    )
    monkeypatch.setattr(runtime, "os", fake_os)
    monkeypatch.setattr(runtime, "_registered", set())
    monkeypatch.setattr(runtime, "_dll_handles", [])
    monkeypatch.setattr(runtime.importlib.util, "find_spec", lambda pkg: None)
    monkeypatch.setattr(runtime.sys, "executable", str(app_root / "ClassScribe.exe"))

    runtime.configure_cuda_libraries()
    assert len(handles) == 2
    assert str(cublas_dir) in fake_os.environ["PATH"]
    assert str(ct2_dir) in fake_os.environ["PATH"]
