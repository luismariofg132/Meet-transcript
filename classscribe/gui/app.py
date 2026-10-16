"""Launch Qt only when requested; the CLI keeps its zero-Qt import path."""

import sys
from pathlib import Path


def build_engine(controller):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("appController", controller)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    return engine


def main() -> int:
    try:
        from PySide6.QtCore import QStandardPaths, QTimer
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQuickControls2 import QQuickStyle
    except ImportError:
        print('Install the GUI extra: pip install -e ".[gui]"', file=sys.stderr)
        return 2

    from classscribe.application.desktop import DesktopServices
    from classscribe.application.preferences import PreferenceStore
    from classscribe.gui.controller import AppController

    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv)
    app.setOrganizationName("ClassScribe")
    app.setApplicationName("ClassScribe")
    config = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    )
    data = (
        Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
        / "ClassScribe"
    )
    controller = AppController(DesktopServices(PreferenceStore(config / "preferences.json", data)))
    engine = build_engine(controller)
    if not engine.rootObjects():
        return 1
    controller.closeReady.connect(app.quit)
    QTimer.singleShot(0, controller.initialize)
    try:
        return app.exec()
    finally:
        from shiboken6 import delete

        # QML bindings must be destroyed while the Python context still exists.
        delete(engine)
