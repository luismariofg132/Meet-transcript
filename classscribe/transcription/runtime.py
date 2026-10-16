"""Process-local CUDA discovery; no machine-wide PATH changes."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_dll_handles: list[Any] = []
_registered: set[Path] = set()


def configure_cuda_libraries() -> None:
    if os.name != "nt":
        return
    roots: list[Path] = []
    for package in ("ctranslate2", "nvidia"):
        spec = importlib.util.find_spec(package)
        if spec:
            if spec.submodule_search_locations:
                roots.extend(Path(path) for path in spec.submodule_search_locations)
            elif getattr(spec, "origin", None):
                roots.append(Path(spec.origin).parent)
    # Packaged application fallback: inspect application root and subdirectories
    app_root = Path(sys.executable).resolve().parent
    for sub in ("ctranslate2", "nvidia"):
        candidate = app_root / sub
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    directories = sorted({dll.parent for root in roots for dll in root.rglob("*.dll")})
    for dll_pattern in ("cublas*.dll", "cudnn*.dll", "ctranslate2.dll"):
        if any(app_root.glob(dll_pattern)) and app_root not in directories:
            directories.append(app_root)
            directories.sort()
            break
    # Windows native dependencies may use LoadLibrary, which also consults PATH.
    # Retain add_dll_directory handles for the entire process lifetime.
    for directory in directories:
        if directory not in _registered:
            _dll_handles.append(os.add_dll_directory(str(directory)))
            os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
            _registered.add(directory)


def query_nvidia() -> str | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def select_compute(requested: str, ct2: Any) -> tuple[str, str]:
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("Device must be auto, cpu, or cuda")
    count = ct2.get_cuda_device_count() if requested != "cpu" else 0
    device = ("cuda" if count else "cpu") if requested == "auto" else requested
    if device == "cuda" and count == 0:
        raise RuntimeError(
            "No compatible NVIDIA GPU detected. Use --device cpu explicitly if needed."
        )
    supported = ct2.get_supported_compute_types(device, device_index=0)
    preferences = (
        ("int8_float16", "float16", "int8_float32", "float32")
        if device == "cuda"
        else ("int8", "int8_float32", "float32")
    )
    for compute in preferences:
        if compute in supported:
            return device, compute
    raise RuntimeError(f"No supported compute type found for {device}: {sorted(supported)}")
