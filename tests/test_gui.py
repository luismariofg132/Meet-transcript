"""Optional offscreen UI tests. No devices, network, inference or visible windows."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import MIC, SYSTEM

os.environ["QT_QPA_PLATFORM"] = "offscreen"
pytest.importorskip("PySide6")
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QThread,
    qInstallMessageHandler,
)
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from shiboken6 import delete

from classscribe.application.preferences import PreferenceStore
from classscribe.gui.app import build_engine
from classscribe.gui.controller import AppController
from classscribe.transcription.progress import TranscriptionProgress


@pytest.fixture(scope="module")
def qt():
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication.instance() or QGuiApplication([])
    # The Windows offscreen plugin has no native font database; do not bundle OS fonts.
    for name in ("segoeui.ttf", "segoeuib.ttf", "segoeuil.ttf", "consola.ttf"):
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    yield app


def spin(qt, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        qt.processEvents()
        time.sleep(0.005)
    assert predicate(), "Qt worker did not reach expected state"


class FakeServices:
    def __init__(self, path):
        self.store = PreferenceStore(path / "prefs.json", path)
        self.recording_entered = threading.Event()
        self.transcription_entered = threading.Event()
        self.allow_finalization = threading.Event()
        self.allow_transcription = threading.Event()
        self.record_thread = None
        self.transcribe_thread = None
        self.finalized = False
        self.fail = False
        self.detail = {
            "session": {
                "identity": "test",
                "title": "Memory cache",
                "course": "Architecture",
                "duration": "00:01:05",
                "recorded": True,
                "date": "2026-10-15",
                "status": "recorded",
                "microphone": False,
                "system_audio": True,
                "directory": str(path),
            },
            "runs": [],
        }

    def discover(self):
        return {"devices": [SYSTEM.to_dict(), MIC.to_dict()], "device_error": ""}

    def initialize(self):
        return {
            "preferences": self.store.load(),
            "sessions": [self.detail["session"]],
            **self.discover(),
        }

    def record(self, values, title, course, stop, emit):
        self.record_thread = QThread.currentThread()
        self.recording_entered.set()
        emit("prepared", self.detail["session"])
        emit("elapsed", 65)
        emit("levels", (0.6, 0.2))
        assert stop.wait(5)
        assert self.allow_finalization.wait(5)
        if self.fail:
            raise RuntimeError("Device disconnected; preserved audio")
        self.finalized = True
        return self.detail

    def transcribe(self, values, identity, emit):
        assert self.finalized
        self.transcribe_thread = QThread.currentThread()
        emit(
            "transcription",
            TranscriptionProgress("transcribing", 50, 100, "system", "system.wav", "cpu"),
        )
        self.transcription_entered.set()
        assert self.allow_transcription.wait(5)
        return {**self.detail, "result": str(self.store.data_root / "result")}


@pytest.fixture
def desktop(qt, tmp_path):
    services = FakeServices(tmp_path)
    controller = AppController(services)
    controller.initialize()
    spin(qt, lambda: controller.job is None)
    yield controller, services
    controller.stop_event.set()
    services.allow_finalization.set()
    services.allow_transcription.set()
    spin(qt, lambda: controller.job is None)
    delete(controller)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_devices_defaults_and_library(desktop):
    controller, _ = desktop
    assert controller.outputs.rowCount() == 1
    assert controller.outputs.get(0)["is_default"]
    assert controller.outputs.get(0)["label"].startswith("Default")
    assert controller.preferences["output_device"] == ""  # Follow changing OS default.
    assert controller.sessions.get(0)["title"] == "Memory cache"


def test_disconnected_device_falls_back_without_crash(desktop):
    controller, _ = desktop
    controller.setPreference("output_device", "Disconnected headset")
    controller.set_devices({"devices": [SYSTEM.to_dict()], "device_error": ""})
    assert controller.preferences["output_device"] == ""
    assert "unavailable" in controller.state["notice"]
    controller.startRecording("Class", "Course")
    assert "No microphone" in controller.state["error"]
    assert controller.job is None


def test_record_thread_progress_stop_and_completion(qt, desktop):
    c, s = desktop
    completed = []
    c.recordingCompleted.connect(completed.append)
    c.startRecording("Memory", "Architecture")
    job = c.job
    c.startRecording("Duplicate", "")
    assert c.job is job
    spin(qt, lambda: c.state["elapsed"] == "00:01:05")
    assert s.record_thread != qt.thread()
    assert c.state["systemLevel"] == 0.6
    c.stopRecording()
    assert c.stop_event.is_set() and c.state["stopping"]
    assert c.job is job and not completed  # Thread remains alive until files are finalized.
    s.allow_finalization.set()
    spin(qt, lambda: c.job is None)
    assert s.finalized and completed == ["test"]
    assert c.state["page"] == "saved"


def test_auto_transcribe_waits_for_finalization_and_runs_off_ui(qt, desktop):
    c, s = desktop
    c.setPreference("auto_transcribe", True)
    c.startRecording("Memory", "")
    spin(qt, s.recording_entered.is_set)
    c.stopRecording()
    assert not s.transcription_entered.is_set()
    s.allow_finalization.set()
    spin(qt, lambda: c.state["progress"] == 0.5)
    assert s.finalized and s.transcribe_thread != qt.thread()
    assert c.state["actualDevice"] == "cpu"
    assert c.state["processed"] == "00:00:50 / 00:01:40"
    assert c.state["stage"] == "Transcribing class audio"
    s.allow_transcription.set()
    spin(qt, lambda: c.job is None)
    assert c.state["page"] == "completed"


def test_close_waits_for_recording_and_suppresses_auto_transcribe(qt, desktop):
    c, s = desktop
    closed = []
    c.closeReady.connect(lambda: closed.append(True))
    c.setPreference("auto_transcribe", True)
    c.startRecording("Memory", "")
    c.stopAndClose()
    assert not closed and c.stop_event.is_set()
    s.allow_finalization.set()
    spin(qt, lambda: bool(closed))
    assert s.finalized and c.job is None and not s.transcription_entered.is_set()


def test_close_failure_keeps_recovery_error_visible(qt, desktop):
    c, s = desktop
    s.fail = True
    closed = []
    c.closeReady.connect(lambda: closed.append(True))
    c.startRecording("Memory", "")
    c.stopAndClose()
    s.allow_finalization.set()
    spin(qt, lambda: c.job is None)
    assert not closed and not c.close_pending
    assert "preserved audio" in c.state["error"]


def test_close_waits_for_transcription(qt, desktop):
    c, s = desktop
    s.finalized = True
    c.update(selected=s.detail["session"])
    closed = []
    c.closeReady.connect(lambda: closed.append(True))
    c.transcribe()
    spin(qt, s.transcription_entered.is_set)
    c.closeWhenFinished()
    assert not closed
    s.allow_transcription.set()
    spin(qt, lambda: bool(closed))
    assert c.state["page"] == "completed"


def test_qt_transcript_model_roles(desktop):
    c, _ = desktop
    c.segments.replace(
        [{"source": "system", "speaker": "CLASS", "time": "00:02:14", "text": "Memory"}]
    )
    role = next(key for key, value in c.segments.roleNames().items() if value == b"speaker")
    assert c.segments.data(c.segments.index(0), role) == "CLASS"
    assert c.segments.rowCount(c.segments.index(0)) == 0


def test_save_preferences_uses_worker(qt, desktop):
    c, s = desktop
    c.setPreference("theme", "light")
    c.savePreferences()
    spin(qt, lambda: c.job is None)
    assert s.store.load()["theme"] == "light"


def test_every_qml_page_loads_with_data_and_themes(qt, desktop):
    c, s = desktop
    messages = []
    previous = qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    engine = build_engine(c)
    try:
        spin(qt, lambda: bool(engine.rootObjects()))
        window = engine.rootObjects()[0]
        c.update(selected=s.detail["session"])
        c.runs.replace(
            [
                {
                    "identity": "run",
                    "model": "small",
                    "device": "cpu",
                    "date": "2026-10-15",
                    "status": "completed",
                    "ready": True,
                    "directory": "example",
                }
            ]
        )
        c.segments.replace(
            [
                {"speaker": "CLASS", "time": "00:02:14", "text": "Memory cache"},
                {"speaker": "ME", "time": "00:04:12", "text": "How does this work?"},
            ]
        )
        c.diagnostics.replace([{"label": "Audio backend", "value": "Mock backend"}])
        # Populate and open deferred ComboBox delegates, which root loading alone misses.
        for combo in window.findChildren(QObject, "appCombo"):
            popup = combo.findChild(QObject, "comboPopup")
            QMetaObject.invokeMethod(popup, "open")
            QTest.qWait(10)
            QMetaObject.invokeMethod(popup, "close")
        for size in [(1000, 650), (1366, 768), (1920, 1080)]:
            window.setWidth(size[0])
            window.setHeight(size[1])
            for theme in ("dark", "light", "system"):
                c.setPreference("theme", theme)
                for page in (
                    "home",
                    "recording",
                    "saved",
                    "transcribing",
                    "completed",
                    "classes",
                    "detail",
                    "viewer",
                    "settings",
                ):
                    c.update(page=page)
                    QTest.qWait(20)
                    assert not window.grabWindow().isNull()
        errors = [m for m in messages if "file:" in m or "failed to load" in m]
        assert errors == []
    finally:
        delete(engine)  # Destroy QML bindings before their Python context object.
        qInstallMessageHandler(previous)


def test_window_close_dialog_keeps_recording_alive(qt, desktop):
    c, s = desktop
    engine = build_engine(c)
    try:
        spin(qt, lambda: bool(engine.rootObjects()))
        window = engine.rootObjects()[0]
        c.startRecording("Memory", "Architecture")
        spin(qt, s.recording_entered.is_set)
        window.close()
        QTest.qWait(30)
        dialog = window.findChild(QObject, "recordingClose")
        assert dialog.property("visible") and window.isVisible()
        assert not c.stop_event.is_set()
        QMetaObject.invokeMethod(dialog, "close")  # Continue recording / Cancel.
        assert not c.stop_event.is_set()
        c.stopAndClose()
        assert c.job is not None
        s.allow_finalization.set()
        spin(qt, lambda: c.job is None)
        assert s.finalized
    finally:
        delete(engine)


def test_gui_startup_does_not_load_whisper():
    script = """
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'faster_whisper', 'ctranslate2'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QTimer
from PySide6.QtQuickControls2 import QQuickStyle
from pathlib import Path
from shiboken6 import delete
from classscribe.gui.app import build_engine
from classscribe.gui.controller import AppController
from classscribe.application.desktop import DesktopServices
from classscribe.application.preferences import PreferenceStore
QQuickStyle.setStyle('Basic')
app=QGuiApplication([])
c=AppController(DesktopServices(PreferenceStore(Path('unused.json'),Path('unused'))))
engine=build_engine(c)
QTimer.singleShot(100,app.quit)
app.exec()
assert engine.rootObjects()
delete(engine)
"""
    subprocess.run([sys.executable, "-c", script], check=True, timeout=30)
