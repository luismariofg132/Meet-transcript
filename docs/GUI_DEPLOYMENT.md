# Windows Desktop Deployment and Packaging Guide

ClassScribe is packaged as a reproducible standalone Windows desktop application using [PySide6](https://doc.qt.io/qtforpython-6/) and [Nuitka](https://nuitka.net/) underneath the official `pyside6-deploy` tooling.

---

## 1. Prerequisites and Build Environment

The packaging pipeline targets **Windows 10/11 x64** and **64-bit Python 3.12**.

### Setting Up a Clean Build Environment

From a fresh clone in PowerShell:

```powershell
# Create dedicated clean build virtual environment
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install --upgrade pip

# Install full application runtime extras
.\.venv-build\Scripts\python.exe -m pip install -e ".[audio,transcription,cuda,gui,youtube]"

# Install packaging tooling
.\.venv-build\Scripts\python.exe -m pip install "Nuitka==4.3.1" zstandard

# Verify compiler version (expected: 4.3.1)
.\.venv-build\Scripts\python.exe -m nuitka --version
```

> [!NOTE]
> Packaging previously failed under Nuitka 4.1.1 with an internal compiler assertion (`AssertionError: assert micro_passes == 0`). Nuitka 4.3.1 is now the supported and recommended project build version. Actual build success still depends on running the packaging pipeline.
>
> When compiling for the first time on a machine without MSVC in PATH, Nuitka will automatically download and cache a portable MinGW64 (GCC 15) toolchain. No manual compiler configuration is required.

---

## 2. Standalone Directory Build

The primary release format is a **standalone directory bundle** (`dist/ClassScribe/`). Standalone mode preserves dynamic linking, separates native DLLs for inspection and debugging, and complies with Qt LGPL relinking requirements.

### One-Command Build

Execute the build script from the repository root, explicitly specifying the dedicated build environment to prevent accidentally reusing the development `.venv`:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\build.ps1 `
    -Python ".\.venv-build\Scripts\python.exe" `
    -ProduceZip
```

This script:
1. Verifies the Windows OS and 64-bit Python 3.12 environment.
2. Cleans prior build artifacts (`dist/ClassScribe`, `packaging/deployment`).
3. Generates multi-resolution application icons (`assets/classscribe.ico` and `packaging/assets/classscribe.ico`).
4. Invokes `pyside6-deploy packaging/desktop.py -c packaging/pysidedeploy.spec --no-install`.
5. Organizes the output into `dist/ClassScribe/`.
6. Executes automated bundle integrity and smoke tests (`packaging/smoke_test.py`).
7. Creates `dist/ClassScribe-<version>-win64-portable.zip` and its `*.sha256` checksum file.

---

## 3. Bundle Structure

The built directory at `dist/ClassScribe/` contains:

```text
dist/
└── ClassScribe/
    ├── ClassScribe.exe                      # Main GUI binary (Windows GUI subsystem; no console window)
    ├── classscribe.ico                      # Application icon
    ├── LICENSE                              # MIT license
    ├── THIRD_PARTY_NOTICES.txt              # Redistribution notices and Qt LGPL compliance details
    ├── classscribe/
    │   └── gui/
    │       ├── assets/                      # Application icons
    │       └── qml/                         # Preserved QML tree (Main.qml, pages/, components/)
    ├── faster_whisper/
    │   └── assets/
    │       └── silero_vad_v6.onnx           # VAD model required for transcription
    ├── ctranslate2/                         # CTranslate2 native DLLs and Python extension
    ├── nvidia/                              # CUDA 12 cuBLAS and cuDNN 9 runtime DLLs
    │   ├── cublas/bin/                      # cublas64_12.dll, cublasLt64_12.dll
    │   └── cudnn/bin/                       # cudnn64_9.dll, cudnn_ops64_9.dll, etc.
    ├── PySide6/                             # Qt 6 DLLs (QtCore, QtGui, QtQml, QtQuick, etc.)
    ├── platforms/                           # Qt platform plugin (qwindows.dll)
    ├── styles/                              # Qt Quick Controls styles
    ├── imageformats/                        # Qt image format plugins
    ├── onnxruntime/                         # ONNX Runtime binaries
    ├── av.libs/                             # PyAV / FFmpeg shared libraries
    └── _portaudiowpatch*.pyd                # WASAPI loopback audio capture extension
```

---

## 4. Runtime Behavior and Safety

### Model Weights are NOT Bundled
- The bundle contains zero Whisper model weights (`.safetensors`, `.bin`).
- When the user transcribes for the first time, models download to writable user storage (`Documents/ClassScribe/models`).
- In offline mode, pre-cached models in that folder are loaded without internet access.
- Reinstalling or updating the application will never delete user models or recordings.

### Application Paths & Program Files Safety
The application never writes data beside `ClassScribe.exe`, allowing safe installation into `C:\Program Files\ClassScribe`:
- **Configuration**: `QStandardPaths.AppConfigLocation` (`%LOCALAPPDATA%\ClassScribe\ClassScribe`)
- **Diagnostic Logs**: `%LOCALAPPDATA%\ClassScribe\ClassScribe\logs\classscribe.log` (rotating, max 1MB)
- **User Data**: `Documents\ClassScribe\` (`recordings/`, `transcripts/`, `models/`)

### CUDA and CPU Compatibility
- The bundle includes optional CUDA 12 (`cublas64_12.dll`) and cuDNN 9 (`cudnn64_9.dll`) runtime binaries.
- CUDA discovery (`classscribe/transcription/runtime.py`) dynamically detects bundled DLLs in `nvidia/` and `ctranslate2/` directories without modifying machine PATH.
- If an NVIDIA GPU and compatible driver (>= 525) are present, GPU acceleration is used when requested.
- **On CPU-only machines**, the application starts up immediately, records WASAPI audio, imports YouTube sessions, and runs CPU transcription without error. CUDA libraries are never loaded eagerly.

### Node.js Handling
- YouTube audio downloads via `yt-dlp` resolve Node.js using `resolve_node_runtime()`:
  1. `<ApplicationRoot>/bin/node.exe` (if bundled in the future)
  2. System PATH (`shutil.which("node")`)
  3. Graceful fallback if Node is absent.

---

## 5. Automated Bundle Smoke Testing

Run the smoke test suite against any built standalone directory:

```powershell
python packaging/smoke_test.py dist/ClassScribe
```

Checks verified automatically:
1. `ClassScribe.exe` exists and is valid.
2. All required QML resources (`Main.qml`, `pages/`, `components/`, `qmldir`, `Theme.qml`) exist with preserved hierarchy.
3. Qt Windows platform plugin (`qwindows.dll`) is present.
4. CTranslate2 native binary and extension exist.
5. PyAV / FFmpeg shared libraries exist.
6. PyAudioWPatch (`_portaudiowpatch*.pyd`) WASAPI extension exists.
7. `yt_dlp` package is present.
8. Silero VAD asset (`silero_vad_v6.onnx`) is present.
9. No model weights (`.safetensors`, `.bin`) or user recordings are bundled.
10. Headless smoke execution with `CLASSSCRIBE_SMOKE_TEST=1` launches the QML engine, initializes controller and desktop services, and exits cleanly with code 0.
11. Execution from a completely different working directory (e.g. `C:\`) verifies that all asset and QML resolution is working-directory independent.

---

## 6. Clean-Machine Acceptance Checklist

Validate the standalone bundle on a clean Windows machine without Python, Git, or developer tools:

- [ ] **Startup**: Double-click `ClassScribe.exe` from Explorer; GUI opens without any command prompt window.
- [ ] **Home Screen**: Navigation between Home, Classes, Sessions, and Settings works smoothly.
- [ ] **Device Discovery**: Input (microphones) and output (WASAPI loopback) devices are enumerated.
- [ ] **Audio Recording**: Record 2 minutes of system audio and microphone; verify live audio meters bounce.
- [ ] **Graceful Stop**: Stop recording; verify WAV files are finalized in `Documents\ClassScribe\recordings\`.
- [ ] **Close While Recording**: Attempting to close the window during active recording prompts a confirmation modal.
- [ ] **CPU Transcription**: Transcribe a recording using CPU; model downloads automatically on first run to `Documents\ClassScribe\models\`.
- [ ] **Transcript Viewer**: Open completed transcript; inspect segments, timestamps, and export options.
- [ ] **Preferences Persistence**: Change theme or recording settings in Settings page; restart application and verify settings persist.
- [ ] **YouTube Import**: Paste a YouTube video URL; inspect metadata, download audio, decode via PyAV, and transcribe.
- [ ] **Spaces in Path**: Extract bundle to a folder path with spaces (e.g., `C:\Users\Test\Desktop\Class Scribe\`) and verify full functionality.
- [ ] **NVIDIA GPU Machine**: On a machine with an NVIDIA GPU, verify CUDA device detection and GPU transcription.

---

## 7. Windows Installer (Inno Setup)

An Inno Setup compiler script is provided at `packaging/installer/ClassScribe.iss`.

### Building the Installer
With [Inno Setup 6](https://jrsoftware.org/isdl.php) installed:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging/installer/ClassScribe.iss
```

The installer:
- Installs to `C:\Program Files\ClassScribe` (64-bit mode).
- Creates Start Menu and optional Desktop shortcuts with `classscribe.ico`.
- Registers a clean uninstaller in Windows Settings / Apps.
- Leaves user recordings, transcripts, and downloaded models in `Documents\ClassScribe` intact upon uninstall.
- Generates `dist/ClassScribe-Setup-0.1.0.exe`.

---

## 8. Code Signing Readiness

To sign the application with a Microsoft Authenticode certificate:

1. Sign `ClassScribe.exe` and any bundled `.dll` / `.pyd` files before creating the installer:
   ```powershell
   signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "dist\ClassScribe\ClassScribe.exe"
   ```
2. Build the installer (`ISCC.exe packaging/installer/ClassScribe.iss`).
3. Sign the installer:
   ```powershell
   signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a "dist\ClassScribe-Setup-0.1.0.exe"
   ```

---

## 9. Third-Party Redistribution and Licensing

ClassScribe is MIT-licensed. The standalone distribution includes third-party software subject to other licenses:

- **Qt 6 & PySide6**: Licensed under LGPLv3. The standalone application dynamically links to Qt `.dll` files. Users may replace or relink Qt DLLs in the bundle directory. Source code for Qt is available at [qt.io](https://download.qt.io/).
- **CTranslate2**: MIT License.
- **faster-whisper**: MIT License (Silero VAD: MIT License).
- **PyAV & FFmpeg DLLs**: BSD 3-Clause (PyAV) and LGPLv2.1+ (bundled FFmpeg libraries).
- **yt-dlp**: The Unlicense (Public Domain).
- **NumPy**: BSD 3-Clause License.
- **PyAudioWPatch & PortAudio**: MIT / PortAudio License.
- **NVIDIA CUDA Packages**: NVIDIA CUDA Toolkit EULA. Host driver is required.

See `THIRD_PARTY_NOTICES.txt` in the root and bundle directory for full texts.
