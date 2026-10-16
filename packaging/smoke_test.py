"""Automated bundle validation and smoke tests for packaged ClassScribe."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def validate_bundle(bundle_dir: Path) -> list[str]:
    errors: list[str] = []

    if not bundle_dir.is_dir():
        return [f"Bundle directory does not exist: {bundle_dir}"]

    # 1. Main executable
    exe = bundle_dir / "ClassScribe.exe"
    if not exe.is_file():
        errors.append(f"Missing main executable: {exe}")

    # 2. QML files and structure
    qml_root = bundle_dir / "classscribe" / "gui" / "qml"
    required_qml = [
        qml_root / "Main.qml",
        qml_root / "components" / "Theme.qml",
        qml_root / "components" / "qmldir",
        qml_root / "components" / "AppButton.qml",
        qml_root / "pages" / "HomePage.qml",
        qml_root / "pages" / "SettingsPage.qml",
    ]
    for qml_file in required_qml:
        if not qml_file.is_file():
            errors.append(f"Missing required QML file: {qml_file}")

    # 3. Qt Windows platform plugin
    qwindows = list(bundle_dir.rglob("qwindows.dll"))
    if not qwindows:
        errors.append("Missing Qt Windows platform plugin (qwindows.dll)")

    # 4. CTranslate2 native libraries
    ct2_binaries = list(bundle_dir.rglob("ctranslate2.dll")) + list(bundle_dir.rglob("*_ext*.pyd"))
    if not ct2_binaries:
        errors.append("Missing CTranslate2 native libraries (ctranslate2.dll or _ext*.pyd)")

    # 5. PyAV native binaries
    av_binaries = list(bundle_dir.rglob("avcodec*.dll")) + list(bundle_dir.rglob("*_core*.pyd"))
    if not av_binaries:
        errors.append("Missing PyAV native binaries (avcodec*.dll or _core*.pyd)")

    # 6. PyAudioWPatch / PortAudio
    pyaudio_pyd = list(bundle_dir.rglob("*portaudio*.pyd"))
    if not pyaudio_pyd:
        errors.append("Missing PyAudioWPatch native extension (_portaudiowpatch*.pyd)")

    # 7. yt-dlp package
    ytdlp = list(bundle_dir.rglob("yt_dlp"))
    if not ytdlp:
        errors.append("Missing yt_dlp package in bundle")

    # 8. faster-whisper VAD assets
    vad_assets = list(bundle_dir.rglob("silero_vad_v6.onnx"))
    if not vad_assets:
        errors.append("Missing faster-whisper VAD asset (silero_vad_v6.onnx)")

    # 9. Verify NO model weights are bundled
    model_weights = [
        f
        for f in bundle_dir.rglob("*")
        if f.suffix in {".safetensors", ".bin"} and "silero" not in f.name.lower()
    ]
    if model_weights:
        errors.append(f"Model weights must NOT be bundled: {[str(m) for m in model_weights]}")

    # 10. Verify NO user data, tests, or git
    forbidden_dirs = [".git", "tests", "recordings", "transcripts", "models"]
    for forbidden in forbidden_dirs:
        if (bundle_dir / forbidden).exists():
            errors.append(f"Forbidden directory bundled: {forbidden}")

    return errors


def run_smoke_execution(bundle_dir: Path, working_dir: Path | None = None) -> tuple[int, str, str]:
    """Check real YouTube extractor resolution, then launch the GUI in smoke mode."""
    exe = bundle_dir / "ClassScribe.exe"
    env = os.environ.copy()
    env["CLASSSCRIBE_SMOKE_TEST"] = "1"
    # Allow offscreen if headless/CI
    if "QT_QPA_PLATFORM" not in env:
        env["QT_QPA_PLATFORM"] = "windows"

    cwd = str(working_dir) if working_dir else str(bundle_dir)
    proc = subprocess.run(
        [str(exe)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    bundle_path = Path("dist/ClassScribe").resolve()
    if len(sys.argv) > 1:
        bundle_path = Path(sys.argv[1]).resolve()

    print(f"=== Validating ClassScribe standalone bundle at: {bundle_path} ===")
    errors = validate_bundle(bundle_path)
    if errors:
        print("FAIL: Bundle structural validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("PASS: Bundle structural validation succeeded.")

    print("\n=== Executing packaged app smoke test (inside bundle dir) ===")
    code, stdout, stderr = run_smoke_execution(bundle_path, working_dir=bundle_path)
    if code != 0:
        print(f"FAIL: App execution failed with exit code {code}")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return code
    print("PASS: App launched and exited cleanly with code 0.")

    print("\n=== Executing packaged app smoke test from external directory (C:\\) ===")
    code, stdout, stderr = run_smoke_execution(bundle_path, working_dir=Path("C:\\"))
    if code != 0:
        print(f"FAIL: External CWD execution failed with exit code {code}")
        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")
        return code
    print(
        "PASS: App launched from external working directory (C:\\) and exited cleanly with code 0."
    )

    print("\nAll smoke tests passed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
