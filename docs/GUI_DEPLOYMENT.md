# Windows desktop bundle

The supported development entry points are `classscribe-gui` and
`python -m classscribe.gui`. Install with 64-bit Python 3.12:

```powershell
python -m pip install -e ".[audio,transcription,cuda,gui]"
classscribe-gui
```

The GUI extra is optional; CLI-only users need no Qt. QML lives inside the `classscribe`
package and is included in wheels. The GUI launcher resolves QML relative to its own
module, not the process working directory. Data and models live outside the application.

## Preparing a bundle

Use [Qt for Python's official pyside6-deploy workflow](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html).
It wraps Nuitka and generates a `pysidedeploy.spec` configuration. Work in a dedicated
Windows build environment with a supported C/C++ compiler and the intended dependencies:

```powershell
python -m pip install -e ".[audio,transcription,cuda,gui]"
pyside6-deploy packaging/desktop.py --init
# Inspect and adjust the generated pysidedeploy.spec before building.
pyside6-deploy -c pysidedeploy.spec --dry-run
pyside6-deploy -c pysidedeploy.spec
```

Use the generated spec's project directory and QML file list to include **all**
`classscribe/gui/qml/**/*.qml` plus `components/qmldir`. Inspect the dry-run Nuitka
command for package data inclusion. If discovery does not include them, add the
equivalent Nuitka `--include-data-dir=classscribe/gui/qml=classscribe/gui/qml` option
through the spec's Nuitka extra arguments. Preserve the relative directory structure.
Review module/plugin inclusion for QtQuick, QtQuick.Controls, QtQuick.Layouts and the
Windows platform plugin. A standalone directory bundle is easier to inspect before
trying a one-file executable; select the mode in the generated deployment configuration.

Whisper, CTranslate2 and PyAudioWPatch use lazy imports/native dependencies. Verify
their inclusion explicitly in the deployment report; QML scanning alone will not
find every Python audio/inference dependency. Include the faster-whisper VAD assets,
PyAV libraries, onnxruntime and any required CTranslate2 native libraries. CUDA drivers
remain a machine prerequisite. Follow [Windows CUDA setup](TRANSCRIPTION_WINDOWS.md)
for cuBLAS/cuDNN; do not assume a working development environment proves portability.

Do not include model weights, recordings, transcripts, preferences, credentials, the
virtual environment, or `.tools` in a distributable. Models download into the configured
per-user cache when requested (or use offline mode with a prepared cache). Review Qt
and third-party redistribution licenses and notices for the chosen distribution.

## Release acceptance

This repository prepares an entry script and packaging layout; **no Windows executable
has been built or validated**. Before releasing, test the bundle on a clean Windows
machine without Python: open every screen, discover devices, record/stop, close while
recording, transcribe on CPU, retry, open old transcripts and persist settings. Validate
CUDA separately on a compatible machine. Check large/high-DPI displays and deployment
paths containing spaces/non-ASCII characters. Ship only after those checks pass.

Generated specs/build folders/executables should remain outside version control.
