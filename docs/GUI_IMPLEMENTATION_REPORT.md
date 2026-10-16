# Desktop implementation report

## GUI architecture

Qt Quick/QML renders the application. AppController owns the presentation state machine;
RowsModel provides explicit Qt roles. Serialized QThread jobs invoke presentation-neutral
application services, which call the existing recording/session/transcription core.
CLI and GUI share recording orchestration and the lazy transcription entry point.
The core and application packages have no Qt dependency; the GUI never invokes the CLI.

## Screens implemented

Home, Recording, Recording saved, Transcribing, Transcription completed, Classes,
Session detail, Transcript viewer and Settings. Shared components provide styled
buttons/fields/selectors/cards/switches, audio meters and original line icons.
Centralized tokens support dark (default), light and system themes.

## Threading model

Device discovery, preference I/O, library and transcript reads, diagnostics, audio
capture and Whisper run in QThread jobs. Queued events update main-thread models and
state. Only one operation is admitted at a time. Completion is handled after the
worker's finished signal. Startup imports no Whisper/CTranslate2 and runs no inference.

## Graceful stop

Stop sets a threading.Event. The existing recorder closes capture streams, drains
queues, finalizes WAV files and persists metadata, then the application service closes
the backend. Worker completion unlocks the saved screen/automatic transcription.
Closing during recording has Stop and close / Continue recording / Cancel. Stop and
close suppresses automatic transcription and waits for completion. Finalization errors
remain visible. No worker is forcefully terminated.

## Audio meter

PCM16 peak levels are computed on the writer threads from short-lived existing chunks
at most 10 times per second. The audio callback remains an enqueue-only producer.
The UI receives two scalar levels at about 10 Hz; stale values expire after 300 ms.
There is no waveform buffer or audio history for visualization.

## Transcription progress

Optional frozen progress events cover loading, preparing, transcribing, merging,
publishing and completed stages. Percentages count completed ownership intervals,
avoiding overlap double-counting. Total audio includes both tracks; it can exceed
wall-clock duration. Window completion produces coarse progress, not an ETA.
Stages with unknown duration use indeterminate presentation.

## Files created

* `classscribe/application/{recording,transcription,library,preferences,desktop}.py`:
  shared orchestration, read models, persistence and desktop composition.
* `classscribe/gui/{app,__main__,controller,models,workers}.py`: optional entry points,
  controller, Qt models and worker lifetime.
* `classscribe/gui/qml/Main.qml`, `components/`, `pages/`: 20 QML files plus singleton
  registration. All pages are instantiated by the root for startup validation.
* `classscribe/transcription/progress.py`: presentation-neutral progress contract.
* `tests/test_application_gui_core.py`, `tests/test_gui.py`: 25 new tests.
* `docs/GUI.md`, `GUI_DEPLOYMENT.md`, this report, `docs/images/gui-home.png`,
  `packaging/desktop.py`: documentation, actual screenshot and deployment entry script.

## Files modified

* Audio recorder/writer: cooperative stop and scalar meter snapshots.
* Transcription service: optional progress notifications, preserving its existing engine.
* CLI commands: shared application services with retained flags/output behavior.
* `pyproject.toml`: optional GUI extra and GUI executable entry point.
* CI: original Windows/Linux core matrix plus a separate Windows offscreen GUI job.
* README/validation documentation and ignore rules for deployment outputs. The user's
  pre-existing `graphify-out/` ignore entry was preserved.

## Dependencies

`gui = ["PySide6>=6.8,<7"]`. Tested with PySide6 6.12.0 and Python 3.12.14. Headless
installations remain Qt-free. The existing audio/transcription/CUDA extras are unchanged.
The local editable installation now exposes `classscribe-gui.exe`.

## CLI compatibility

Existing devices, doctor, record and transcribe command tests pass, including Ctrl+C,
no-microphone behavior, delayed model imports, partial recovery, repeated runs, original
audio preservation, explicit CUDA errors and overlap ownership. CLI help was executed.
No real recording or inference was used as a compatibility test.

## Tests and validation

**155 passed**: 130 existing regression tests, 13 new headless application/core tests,
12 GUI tests. Ruff lint and format checks passed; git diff whitespace checks passed.
Qt's formatter processed all 20 QML files. Offscreen QML tests cover populated models,
combo popup delegates, close dialog, all pages/themes and three laptop/desktop sizes.
No QML syntax/runtime warnings were reported in those tests.

A Python wheel was built and inspected for all QML resources, qmldir and both entry
points, with no local recordings/models/cache included. Actual non-recording WASAPI
discovery found two outputs and one microphone. The README screenshot is an actual
render of Home after that discovery. No Windows executable was built; remote CI was
not run. No microphone/system capture, model download or CPU/CUDA inference was performed.

## Known limitations

No inference cancellation: close waits for completion. No audio playback/seek, transcript
editing, study processing or cloud sync. Window geometry is not persisted. Desktop
preferences are independent of CLI TOML; shared sessions require matching storage paths.
Navigation is locked during active jobs. Library discovery is asynchronous but unpaginated;
the transcript list is virtualized while its JSON remains in memory. Duplicate audio
device names still require resolution outside this GUI. Real-device endurance, native
accessibility/high-DPI testing, inference quality and clean-machine bundles remain manual
acceptance work. See the detailed architecture and deployment documents.

## Next recommended phase

Audio playback with clickable transcript timestamps, using existing source/audio offsets.
It is not implemented in this change.
