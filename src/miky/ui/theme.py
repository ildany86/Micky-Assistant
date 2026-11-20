"""Paleta y tipografías de Miky."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

BG = QColor("#0B0E13")
CARD = QColor("#141922")
CARD_SOFT = QColor("#1B2230")
BORDER = QColor("#2A3343")
TEXT = QColor("#E8ECF3")
MUTED = QColor("#8E9AAF")
ACCENT = QColor("#35C2F0")

STATE_COLORS = {
    "offline": QColor("#6B7280"),
    # "idle" es el estado normal: micrófono abierto y esperando. Va en celeste
    # para que se vea de un vistazo que está escuchando.
    "idle": QColor("#3FBEEA"),
    "listening": QColor("#35C2F0"),
    "thinking": QColor("#C08BFF"),
    "working": QColor("#C08BFF"),
    "speaking": QColor("#55E0A3"),
    "error": QColor("#FF5C5C"),
    "confirm": QColor("#FFC65C"),
}

STATE_LABELS = {
    "offline": "Desconectado",
    "idle": "Escuchando",
    "listening": "Te escucho",
    "thinking": "Pensando",
    "working": "Ejecutando",
    "speaking": "Hablando",
    "error": "Error",
    "confirm": "Confirmá",
}

FONT_FAMILY = "Segoe UI"


def font(size: int = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    value = QFont(FONT_FAMILY, size)
    value.setWeight(weight)
    return value


STYLESHEET = f"""
QWidget#MikyPanel {{
    background: {CARD.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 16px;
}}
QLabel {{ color: {TEXT.name()}; font-family: '{FONT_FAMILY}'; font-size: 12px; }}
QLabel#Title {{ font-size: 15px; font-weight: 600; }}
QLabel#Hint {{ color: {MUTED.name()}; font-size: 11px; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {CARD_SOFT.name()};
    color: {TEXT.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 8px;
    padding: 6px 8px;
    font-family: '{FONT_FAMILY}';
    font-size: 12px;
    selection-background-color: {ACCENT.name()};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT.name()}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: {CARD_SOFT.name()};
    color: {TEXT.name()};
    border: 1px solid {BORDER.name()};
    selection-background-color: {ACCENT.name()};
}}
QCheckBox {{ color: {TEXT.name()}; font-family: '{FONT_FAMILY}'; font-size: 12px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid {BORDER.name()};
    background: {CARD_SOFT.name()};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT.name()};
    border: 1px solid {ACCENT.name()};
}}
QPushButton {{
    background: {CARD_SOFT.name()};
    color: {TEXT.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 8px;
    padding: 7px 14px;
    font-family: '{FONT_FAMILY}';
    font-size: 12px;
}}
QPushButton:hover {{ border: 1px solid {ACCENT.name()}; }}
QPushButton#Primary {{
    background: {ACCENT.name()};
    color: #06121A;
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #5FD3F7; }}
QMenu {{
    background: {CARD.name()};
    color: {TEXT.name()};
    border: 1px solid {BORDER.name()};
    border-radius: 10px;
    padding: 6px;
    font-family: '{FONT_FAMILY}';
    font-size: 12px;
}}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {CARD_SOFT.name()}; }}
QMenu::separator {{ height: 1px; background: {BORDER.name()}; margin: 5px 8px; }}
"""
