# ClassScribe desktop

## Architecture

```text
QML pages/components → AppController + Qt list models → QThread Job
                                                        ↓
CLI commands ────────────────────────────────→ application services
                                                        ↓
                             existing audio / sessions / transcription core
```

`application/recording.py` owns device selection, session creation and backend lifetime;
both presentations use it. `application/transcription.py` is the shared lazy transcription
entry. `library.py` discovers session/run metadata and reads structured transcript JSON.
`preferences.py` validates and atomically persists desktop preferences. `desktop.py`
composes these operations for the GUI. None imports Qt.

`gui/controller.py` serializes work and owns presentation state. `gui/workers.py` runs
the operation in QThread; queued signals deliver progress to the main thread. The
controller's completion slot is invoked only after QThread emits `finished`. No worker
mutates Qt models. Device discovery, preference I/O, library scanning, transcript reads,
diagnostics, recording and transcription all run outside the UI thread.

The QML boundary uses explicit-role QAbstractListModels for devices, classes, runs,
transcript segments and diagnostic rows. Only small state/preference maps cross as
QVariantMap. QML contains layouts, presentation formatting and interactions, with no
filesystem access or CLI subprocesses. The operating system opens external files using
QDesktopServices. Core diagnostic GPU discovery retains its existing nvidia-smi helper.

Theme.qml centralizes dark/light/system colors, typography, radii and spacing. Shared
buttons, fields, switches, selectors, cards and meters style Qt Quick Controls. Icons
are small original Canvas line drawings with no external icon dependency. The minimum
window is 1000×650; long forms scroll. The sidebar contains Home, Classes and Settings.

## Pages

* Home: course/title, devices, mic toggle, auto-transcription, model/device and Record.
* Recording: elapsed time, system/mic meters, startup/saving states and Stop.
* Recording saved: duration, audio status, transcribe and recording folder.
* Transcribing: stages, processed audio, actual engine device and progress.
* Transcription completed: open Markdown, open folder, view transcript and classes.
* Classes: date-sorted session cards with recording/transcription status.
* Session detail: metadata, audio availability, all runs and transcribe again.
* Transcript: virtualized chronological timestamp/CLASS/ME entries from JSON.
* Settings: themes, devices, transcription, storage and manual diagnostics.

## Recording lifetime

Stop sets a threading.Event. The recorder checks it at approximately 100 ms intervals,
then closes producers, drains writer queues, finalizes WAV headers, saves metadata,
releases the session lock and closes the WASAPI backend. Only then does the worker
finish and the GUI offer or automatically begin transcription. Stop latency also
depends on pending disk writes and backend cleanup; it is not a 100 ms guarantee.

Window close offers Stop and close / Continue recording / Cancel. Stop and close waits
for the same completion boundary, suppressing auto-transcription. A finalization failure
keeps the error/recovery path visible instead of silently exiting. During transcription,
the window can stay open or close when finished; there is no unsafe cancel/terminate.
Concurrent jobs and navigation during active work are blocked by the controller.

Each TrackWriter computes a normalized PCM16 peak from an existing chunk at most 10
times per second, after writing, on its own writer thread. The audio callback still
only enqueues bounded chunks. The recorder forwards two scalar levels at about 10 Hz;
stale levels expire after 300 ms. No waveform/history or persistent extra PCM buffer
is allocated. These meters indicate activity, not calibrated loudness or audio quality.

## Transcription progress

Optional frozen TranscriptionProgress events report loading_model, preparing_audio,
transcribing, merging, publishing and completed. Processed seconds advance after each
window iterator is exhausted, using ownership intervals so overlap is not double-counted.
Total duration is the sum of track frames/sample rates: class and mic are processed
separately, so it can exceed the session wall-clock duration. Progress is coarse (normally
five-minute windows), not an ETA. Loading/preparation/merge/publication are indeterminate.
The core works identically without a callback and has no Qt imports.

Original audio, overlap ownership, durable partial JSONL, transactional publication,
independent runs and explicit CUDA failure behavior remain in the original engine.

## Preferences and devices

The GUI uses QStandardPaths.AppConfigLocation/preferences.json and starts with data in
QStandardPaths.DocumentsLocation/ClassScribe. It does not read or rewrite CLI TOML.
Use absolute storage paths when sharing sessions with the CLI. Changes affect the
current application immediately; Save settings writes atomically for subsequent launches.
An invalid saved configuration is reported in the UI; defaults can be edited and saved.
Window geometry is not persisted in this version.

The default device follows Windows at recording start. Explicit selections persist by
readable name; a refresh clears a disconnected selection and explains the fallback.
Missing microphone blocks recording until it is disabled or a device is connected.
Backend/device errors remain visible and can be retried. Duplicate device names are
rejected by the existing core rather than selecting an arbitrary endpoint.

Diagnostics reuses doctor. Its default check does not load a model or run inference;
the optional inference checkbox may download the model unless offline mode is enabled.
Model-cache status checks for local files and explicitly does not claim successful
loading. CUDA visibility is not presented as proof that inference works.

## Validation

Tests run offline with mocked hardware and engines. `test_application_gui_core.py` runs
without Qt. `test_gui.py` skips if PySide6 is absent and otherwise uses the offscreen
platform. The original Windows/Linux core CI matrix stays lightweight (`.[dev]`);
a separate Windows GUI job installs `.[dev,gui]` and validates Qt lifecycle and QML.

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

QML validation instantiates every page with populated list models in all three themes
at 1000×650, 1366×768 and 1920×1080. On Windows, test code explicitly loads installed
Segoe UI/Consolas fonts because Qt's offscreen plugin lacks the native font database.
Production uses the regular Windows platform plugin and OS fonts. No fonts are bundled.
The README screenshot is an actual Qt render with real device discovery and no capture.

Remaining manual acceptance: multi-hour recording, physical device disconnects, audio
quality, real Whisper/CUDA performance, keyboard/screen-reader review on a native
window, high-DPI multi-monitor behavior and clean-machine executable deployment.
No such checks are implied by offscreen tests.

## Scope limits and next phase

Transcription has no cancellation, playback, seeking, editing or text export beyond
existing Markdown/JSON. There is no study processor or cloud account. Large transcript
rows are virtualized, but the JSON/segments are still loaded into memory. Library
metadata scans are asynchronous but not paginated. Navigation is intentionally locked
during active jobs; transcript reading while another class records is not included.
No executable is built in this change.

Recommend audio playback with clickable transcript timestamps next. Existing audio
file/source offsets provide the basis, and the timestamp column is already separate
from transcript text. This phase is not implemented here.
