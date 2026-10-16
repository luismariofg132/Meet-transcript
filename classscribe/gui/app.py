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
    import logging
    import os
    from logging.handlers import RotatingFileHandler

    try:
        from PySide6.QtCore import QStandardPaths, QTimer
        from PySide6.QtGui import QGuiApplication, QIcon
        from PySide6.QtQuickControls2 import QQuickStyle
    except ImportError:
        print('Install the GUI extra: pip install -e ".[gui]"', file=sys.stderr)
        return 2

    from classscribe import __version__
    from classscribe.application.desktop import DesktopServices
    from classscribe.application.preferences import PreferenceStore
    from classscribe.gui.controller import AppController

    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv)
    app.setOrganizationName("ClassScribe")
    app.setApplicationName("ClassScribe")
    app.setApplicationDisplayName("ClassScribe")
    app.setApplicationVersion(__version__)

    config = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    )
    data = (
        Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))
        / "ClassScribe"
    )

    # Configure user log file: AppConfigLocation/logs/classscribe.log
    try:
        logs_dir = config / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "classscribe.log"
        handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            root_logger.setLevel(logging.INFO)
            root_logger.addHandler(handler)
        else:
            root_logger.addHandler(handler)
    except Exception:
        pass

    def _handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical(
            "Uncaught GUI startup/runtime error",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = _handle_exception

    # Set application icon
    icon_candidates = [
        Path(__file__).resolve().parent / "assets" / "classscribe.ico",
        Path(__file__).resolve().parent.parent.parent / "assets" / "classscribe.ico",
        Path(sys.executable).resolve().parent / "assets" / "classscribe.ico",
        Path(sys.executable).resolve().parent / "classscribe.ico",
    ]
    for candidate in icon_candidates:
        if candidate.is_file():
            app.setWindowIcon(QIcon(str(candidate)))
            break

    controller = AppController(DesktopServices(PreferenceStore(config / "preferences.json", data)))
    engine = build_engine(controller)
    if not engine.rootObjects():
        return 1
    controller.closeReady.connect(app.quit)
    QTimer.singleShot(0, controller.initialize)

    # Hidden smoke test mode for automated build validation
    if os.environ.get("CLASSSCRIBE_SMOKE_TEST") == "1":
        QTimer.singleShot(500, app.quit)

    try:
        return app.exec()
    finally:
        from shiboken6 import delete

        # QML bindings must be destroyed while the Python context still exists.
        delete(engine)
