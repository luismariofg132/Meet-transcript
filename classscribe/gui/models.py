"""Explicit role models; updates always belong to the Qt main thread."""

from typing import Any

from PySide6.QtCore import QAbstractListModel, Qt, Slot


class RowsModel(QAbstractListModel):
    def __init__(self, roles: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.rows: list[dict[str, Any]] = []
        self.roles = {int(Qt.ItemDataRole.UserRole) + i + 1: name for i, name in enumerate(roles)}

    def roleNames(self) -> dict[int, bytes]:
        return {role: name.encode() for role, name in self.roles.items()}

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        return self.rows[index.row()].get(self.roles.get(role, ""))

    def replace(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict[str, Any]:
        return self.rows[row] if 0 <= row < len(self.rows) else {}
