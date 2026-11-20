"""Bandeja del sistema: la única forma prolija de salir y de llegar a Ajustes."""

from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class MikyTray(QSystemTrayIcon):
    def __init__(self, icon: QIcon, menu: QMenu, tooltip: str = "Miky") -> None:
        super().__init__(icon)
        self.setToolTip(tooltip)
        self.setContextMenu(menu)
        self._menu = menu

    def show_message(self, title: str, message: str, seconds: int = 3) -> None:
        try:
            self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, seconds * 1000)
        except Exception:  # noqa: BLE001
            pass
