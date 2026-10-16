"""Desktop state machine: all service calls execute in a serialized worker."""

import json
from threading import Event
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from classscribe.application.desktop import DesktopServices
from classscribe.application.preferences import defaults
from classscribe.gui.models import RowsModel
from classscribe.gui.workers import Job
from classscribe.storage import timestamp


class AppController(QObject):
    changed = Signal()
    closeReady = Signal()
    recordingStarted = Signal()
    recordingStopping = Signal()
    recordingCompleted = Signal(str)
    recordingFailed = Signal(str)
    youtubeInspected = Signal(str)
    youtubeImported = Signal(str)

    def __init__(self, services: DesktopServices) -> None:
        super().__init__()
        self.services = services
        self._prefs = defaults(services.store.data_root)
        self._state: dict[str, Any] = dict(
            page="home",
            busy=False,
            operation="",
            error="",
            deviceError="",
            elapsed="00:00:00",
            systemLevel=0.0,
            microphoneLevel=0.0,
            stopping=False,
            recordingActive=False,
            selected={},
            youtube={},
            stage="",
            progress=-1.0,
            processed="",
            actualDevice="",
            result="",
            diagnostics="",
            notice="",
        )
        self.outputs = RowsModel(("name", "label", "is_default"), self)
        self.microphones = RowsModel(("name", "label", "is_default"), self)
        self.sessions = RowsModel(
            (
                "identity",
                "title",
                "course",
                "date",
                "duration",
                "status",
                "transcribed",
                "source_kind",
                "source_url",
                "channel",
            ),
            self,
        )
        self.runs = RowsModel(
            ("identity", "model", "device", "date", "status", "ready", "directory"), self
        )
        self.segments = RowsModel(("speaker", "time", "text", "start", "end", "source"), self)
        self.diagnostics = RowsModel(("label", "value"), self)
        self.job: Job | None = None
        self.stop_event = Event()
        self.close_pending = False

    @Property("QVariantMap", notify=changed)
    def state(self):
        return self._state

    @Property("QVariantMap", notify=changed)
    def preferences(self):
        return self._prefs

    @Property(QObject, constant=True)
    def outputModel(self):
        return self.outputs

    @Property(QObject, constant=True)
    def microphoneModel(self):
        return self.microphones

    @Property(QObject, constant=True)
    def sessionModel(self):
        return self.sessions

    @Property(QObject, constant=True)
    def runModel(self):
        return self.runs

    @Property(QObject, constant=True)
    def transcriptModel(self):
        return self.segments

    @Property(QObject, constant=True)
    def diagnosticModel(self):
        return self.diagnostics

    def update(self, **values: Any) -> None:
        self._state.update(values)
        self.changed.emit()

    def launch(self, kind: str, operation) -> bool:
        if self.job is not None:
            return False
        self.update(busy=True, operation=kind, error="", notice="")
        self.job = Job(operation, self)
        self.job.event.connect(self.on_event, Qt.ConnectionType.QueuedConnection)
        self.job.finished.connect(self.on_finished, Qt.ConnectionType.QueuedConnection)
        self.job.start()
        return True

    @Slot()
    def initialize(self) -> None:
        self.launch("initialize", lambda emit: self.services.initialize())

    def set_devices(self, result: dict) -> None:
        for source, model, key in (
            ("system", self.outputs, "output_device"),
            ("microphone", self.microphones, "microphone_device"),
        ):
            rows = [
                {**d, "label": ("Default · " if d["is_default"] else "") + d["name"]}
                for d in result["devices"]
                if d["source"] == source
            ]
            model.replace(rows)
            if self._prefs[key] and not any(d["name"] == self._prefs[key] for d in rows):
                self._state["notice"] = (
                    "A selected device is unavailable. Using the current default."
                )
                self._prefs[key] = ""
        self._state["deviceError"] = result["device_error"]

    @Slot(str, "QVariant")
    def setPreference(self, key: str, value: Any) -> None:
        if not self.job and key in self._prefs:
            self._prefs = {**self._prefs, key: value}
            self.changed.emit()

    @Slot()
    def savePreferences(self) -> None:
        values = dict(self._prefs)
        self.launch("save", lambda emit: self.services.store.save(values))

    @Slot()
    def refreshDevices(self) -> None:
        self.launch("devices", lambda emit: self.services.discover())

    @Slot(str)
    def navigate(self, page: str) -> None:
        if self.job:
            return
        self.update(page=page, error="")
        if page == "classes":
            values = dict(self._prefs)
            self.launch("library", lambda emit: self.services.library(values).list_sessions())

    @Slot(str, str)
    def startRecording(self, title: str, course: str) -> None:
        if self.job:
            return
        if not title.strip():
            self.update(error="Enter a class title before recording.")
            return
        if not self.outputs.rows:
            self.update(
                error="No system audio device is available. Refresh devices or run diagnostics."
            )
            return
        if self._prefs["microphone"] and not self.microphones.rows:
            self.update(error="No microphone is available. Turn off My microphone to continue.")
            return
        self.stop_event = Event()
        values = dict(self._prefs)
        self.update(
            page="recording",
            stopping=False,
            recordingActive=False,
            elapsed="00:00:00",
            systemLevel=0.0,
            microphoneLevel=0.0,
            selected={"title": title, "course": course, "microphone": values["microphone"]},
        )
        self.launch(
            "record",
            lambda emit: self.services.record(
                values, title.strip(), course.strip(), self.stop_event, emit
            ),
        )

    @Slot(str)
    def inspectYoutube(self, url: str) -> None:
        if self.job:
            return
        if not url.strip():
            self.update(error="Enter a YouTube video URL to inspect.")
            return
        values = dict(self._prefs)
        self.launch(
            "inspect_youtube",
            lambda emit: self.services.inspect_youtube(values, url.strip()),
        )

    @Slot(str, str, str)
    def importYoutube(self, url: str, title: str = "", course: str = "") -> None:
        if self.job:
            return
        if not url.strip():
            self.update(error="Enter a YouTube video URL before importing.")
            return
        values = dict(self._prefs)
        self.update(
            page="transcribing",
            stage="Inspecting YouTube metadata",
            progress=-1.0,
            processed="",
            actualDevice="",
            result="",
            selected={
                "title": title.strip() or self._state["youtube"].get("title", "YouTube video"),
                "course": course.strip() or self._state["youtube"].get("channel", ""),
                "microphone": False,
                "source_kind": "youtube",
                "source_url": url.strip(),
            },
        )
        self.launch(
            "import_youtube",
            lambda emit: self.services.import_youtube(
                values, url.strip(), title.strip(), course.strip(), emit
            ),
        )

    @Slot()
    def stopRecording(self) -> None:
        if self.job and self._state["operation"] == "record":
            self.stop_event.set()
            self.update(stopping=True)
            self.recordingStopping.emit()

    @Slot()
    def stopAndClose(self) -> None:
        self.close_pending = True
        self.stopRecording()
        if self.job is None:
            self.closeReady.emit()

    @Slot()
    def closeWhenFinished(self) -> None:
        self.close_pending = True
        if self.job is None:
            self.closeReady.emit()

    @Slot(str)
    def loadSession(self, identity: str) -> None:
        values = dict(self._prefs)
        self.launch("detail", lambda emit: self.services.library(values).detail(identity))

    @Slot()
    def transcribe(self) -> None:
        if self.job or not self._state["selected"].get("identity"):
            return
        identity = self._state["selected"]["identity"]
        values = dict(self._prefs)
        self.update(
            page="transcribing",
            stage="Preparing transcription",
            progress=-1.0,
            processed="",
            actualDevice="",
            result="",
        )
        self.launch("transcribe", lambda emit: self.services.transcribe(values, identity, emit))

    @Slot(str)
    def viewTranscript(self, path: str) -> None:
        values = dict(self._prefs)
        if self.launch("viewer", lambda emit: self.services.transcript(values, path)):
            self._state["result"] = path

    @Slot(bool)
    def runDiagnostics(self, inference: bool) -> None:
        values = dict(self._prefs)
        self.launch("diagnostics", lambda emit: self.services.diagnostics(values, inference))

    @Slot(str)
    def openPath(self, path: str) -> None:
        if path and not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self.update(error="The system could not open this file or folder.")

    @Slot(str, object)
    def on_event(self, name: str, value: Any) -> None:
        if name == "prepared":
            self.update(selected=value)
        elif name == "elapsed":
            if not self._state["recordingActive"]:
                self._state["recordingActive"] = True
                self.recordingStarted.emit()
            self.update(elapsed=timestamp(value))
        elif name == "levels":
            self.update(systemLevel=value[0], microphoneLevel=value[1])
        elif name == "youtube":
            labels = {
                "inspecting": "Inspecting YouTube metadata",
                "downloading": "Downloading YouTube audio",
                "preparing_audio": "Preparing session audio",
                "completed": "Audio imported",
            }
            processed = ""
            if value.stage == "downloading" and value.total_bytes > 0:
                done_mb = value.downloaded_bytes / (1024 * 1024)
                total_mb = value.total_bytes / (1024 * 1024)
                processed = f"{done_mb:.1f} MB / {total_mb:.1f} MB"
            elif value.downloaded_bytes > 0:
                done_mb = value.downloaded_bytes / (1024 * 1024)
                processed = f"{done_mb:.1f} MB"
            self.update(
                stage=labels.get(value.stage, value.stage),
                progress=value.progress if value.progress is not None else -1.0,
                processed=processed,
            )
        elif name == "transcription":
            labels = {
                "loading_model": "Loading Whisper model",
                "preparing_audio": "Preparing audio",
                "transcribing": "Transcribing "
                + ("class audio" if value.source == "system" else "my microphone"),
                "merging": "Combining transcript",
                "publishing": "Saving transcript",
                "completed": "Completed",
            }
            self.update(
                stage=labels.get(value.stage, value.stage),
                progress=value.progress if value.progress is not None else -1.0,
                processed=(
                    f"{timestamp(value.processed_seconds)} / {timestamp(value.total_seconds)}"
                ),
                actualDevice=value.device,
            )

    @Slot()
    def on_finished(self) -> None:
        job = self.job
        if job is None:
            return
        kind, result, error = self._state["operation"], job.result, job.error
        self.job = None
        job.deleteLater()
        self.update(busy=False, operation="", systemLevel=0.0, microphoneLevel=0.0)
        if error:
            self.update(
                error=error,
                page="home" if kind in {"record", "import_youtube"} else self._state["page"],
            )
            if kind == "record":
                self.recordingFailed.emit(error)
        elif kind == "initialize":
            self._prefs = result["preferences"]
            self.set_devices(result)
            self.sessions.replace(result["sessions"])
        elif kind == "devices":
            self.set_devices(result)
        elif kind == "save":
            self._prefs = result
            self.update(notice="Settings saved.")
        elif kind == "library":
            self.sessions.replace(result)
        elif kind == "inspect_youtube":
            self.update(youtube=result, notice=f"YouTube metadata ready: {result['title']}")
            self.youtubeInspected.emit(result["video_id"])
        elif kind in {"record", "import_youtube", "detail", "transcribe"}:
            self.runs.replace(result["runs"])
            self.update(
                selected=result["session"],
                page={
                    "record": "saved",
                    "import_youtube": "saved",
                    "detail": "detail",
                    "transcribe": "completed",
                }[kind],
            )
            if kind == "transcribe":
                self.update(result=result["result"])
            if kind in {"record", "import_youtube"}:
                if kind == "record":
                    self.recordingCompleted.emit(result["session"]["identity"])
                else:
                    self.youtubeImported.emit(result["session"]["identity"])
                if self._prefs["auto_transcribe"] and not self.close_pending:
                    self.transcribe()
        elif kind == "viewer":
            self.segments.replace(result)
            self.update(page="viewer")
        elif kind == "diagnostics":
            self.update(diagnostics=json.dumps(result["report"], indent=2, ensure_ascii=False))
            report = result["report"]
            self.diagnostics.replace(
                [
                    {"label": label, "value": str(report.get(key) or "Unavailable")}
                    for label, key in (
                        ("Audio backend", "audio_backend"),
                        ("System audio", "default_output"),
                        ("Microphone", "default_microphone"),
                        ("YouTube import", "yt-dlp"),
                        ("NVIDIA GPU", "nvidia"),
                        ("CTranslate2", "ctranslate2_import"),
                        ("Whisper model", "model_cache"),
                        ("CUDA inference", "cuda_inference"),
                    )
                ]
            )
        self.changed.emit()
        if self.close_pending and self.job is None:
            if error:
                self.close_pending = (
                    False  # Keep recovery details visible after a failed finalization.
                )
            else:
                self.closeReady.emit()
