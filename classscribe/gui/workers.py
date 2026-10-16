"""Cooperative jobs. QThread completion is the resource-lifetime boundary."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThread, Signal


class Job(QThread):
    event = Signal(str, object)

    def __init__(self, operation: Callable, parent=None) -> None:
        super().__init__(parent)
        self.operation = operation
        self.result: Any = None
        self.error = ""

    def run(self) -> None:
        try:
            self.result = self.operation(self.event.emit)
        except Exception as exc:
            self.error = str(exc) or type(exc).__name__
