"""Confirmación pegada al icono: dos botones, sin diálogos del sistema."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme


class ConfirmPopup(QWidget):
    answered = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(theme.STYLESHEET)
        self.setFixedWidth(300)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("MikyPanel")
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        self.question = QLabel("¿Confirmás?")
        self.question.setWordWrap(True)
        layout.addWidget(self.question)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.no_button = QPushButton("No")
        self.no_button.clicked.connect(lambda: self._answer(False))
        row.addWidget(self.no_button)
        self.yes_button = QPushButton("Sí")
        self.yes_button.setObjectName("Primary")
        self.yes_button.clicked.connect(lambda: self._answer(True))
        row.addWidget(self.yes_button)
        layout.addLayout(row)

        self._answered = False

    def ask(self, question: str, anchor: QWidget) -> None:
        self._answered = False
        self.question.setText(question)
        screen = anchor.screen()
        area = screen.availableGeometry() if screen else self.screen().availableGeometry()
        self.adjustSize()
        x = anchor.x() - self.width() - 16
        if x < area.left() + 8:
            x = anchor.x() + anchor.width() + 16
        y = anchor.y() + anchor.height() // 2 - self.height() // 2
        y = max(area.top() + 8, min(y, area.bottom() - self.height() - 8))
        self.move(QPoint(max(area.left() + 8, x), y))
        self.show()
        self.raise_()
        self.yes_button.setFocus()

    def _answer(self, value: bool) -> None:
        if self._answered:
            return
        self._answered = True
        self.hide()
        self.answered.emit(value)

    def dismiss(self) -> None:
        if self.isVisible():
            self._answered = True
            self.hide()
