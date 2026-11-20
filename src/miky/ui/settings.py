"""Panel de ajustes: un popup chico al lado del icono, sin ventana de aplicación."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config as config_mod
from ..config import Config
from ..voice.audio import list_input_devices
from ..voice.tts import list_sapi_outputs, list_sapi_voices
from ..voice.tts_edge import VOICES as EDGE_VOICES
from . import theme

PROVIDER_LABELS = [
    ("gemini", "Google Gemini (recomendado)"),
    ("openai", "OpenAI"),
    ("local", "LM Studio / Ollama (local)"),
    ("mock", "Sin IA (solo comandos directos)"),
]

MODE_LABELS = [
    ("always", "Siempre escuchando (con palabra clave)"),
    ("push_to_talk", "Solo al tocar el icono"),
]

FEEDBACK_MODES = [
    ("mixto", "Sonido si sale bien · voz si hay error"),
    ("sonidos", "Solo sonidos (habla solo preguntas)"),
    ("voz", "Todo hablado"),
]


class SettingsPanel(QWidget):
    saved = Signal(object)
    test_voice = Signal()
    closed = Signal()

    def __init__(self, config: Config, status_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(theme.STYLESHEET)
        self.setFixedWidth(408)
        self._build(status_text)

    # ---------------------------------------------------------------- layout

    def _build(self, status_text: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("MikyPanel")
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Miky · Ajustes")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.status_label = QLabel(status_text or "Sin estado")
        self.status_label.setObjectName("Hint")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addSpacing(4)

        # --- IA ---
        layout.addWidget(_section("Inteligencia (en la nube)"))

        self.provider = QComboBox()
        for value, label in PROVIDER_LABELS:
            self.provider.addItem(label, value)
        _select_data(self.provider, self.config.ai.provider)
        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        layout.addWidget(self.provider)

        self.model = QLineEdit(self.config.ai.model)
        self.model.setPlaceholderText("modelo, ej. gemini-3.5-flash-lite")
        layout.addWidget(self.model)

        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self.api_key = QLineEdit(self.config.ai.api_key)
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("API key")
        key_row.addWidget(self.api_key, 1)
        self.show_key = QCheckBox("ver")
        self.show_key.toggled.connect(
            lambda checked: self.api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self.show_key)
        layout.addLayout(key_row)

        self.base_url = QLineEdit(self.config.ai.base_url)
        self.base_url.setPlaceholderText("URL base (solo OpenAI/local/Groq)")
        layout.addWidget(self.base_url)

        # --- voz ---
        layout.addSpacing(6)
        layout.addWidget(_section("Voz (local)"))

        self.mic = QComboBox()
        self._fill_mics()
        layout.addLayout(_labeled("Micrófono", self.mic))

        self.engine = QComboBox()
        self.engine.addItem("Online · español argentino (recomendado)", "edge")
        self.engine.addItem("Local de Windows", "sapi")
        _select_data(self.engine, self.config.voice.tts_engine)
        self.engine.currentIndexChanged.connect(lambda _index: self._fill_voices())
        layout.addLayout(_labeled("Motor", self.engine))

        self.voice = QComboBox()
        self._fill_voices()
        layout.addLayout(_labeled("Voz", self.voice))

        self.output = QComboBox()
        self._fill_outputs()
        layout.addLayout(_labeled("Salida", self.output))

        wake_row = QHBoxLayout()
        wake_row.setSpacing(8)
        wake_row.addWidget(_hint("Palabra clave"))
        self.wake_word = QLineEdit(self.config.voice.wake_word)
        wake_row.addWidget(self.wake_word, 1)
        layout.addLayout(wake_row)

        self.mode = QComboBox()
        for value, label in MODE_LABELS:
            self.mode.addItem(label, value)
        _select_data(self.mode, self.config.voice.mode)
        layout.addWidget(self.mode)

        self.speak_replies = QCheckBox("Responder en voz alta")
        self.speak_replies.setChecked(self.config.voice.speak_replies)
        layout.addWidget(self.speak_replies)

        self.feedback = QComboBox()
        for value, label in FEEDBACK_MODES:
            self.feedback.addItem(label, value)
        _select_data(self.feedback, self.config.voice.feedback or "mixto")
        layout.addLayout(_labeled("Respuesta", self.feedback))

        self.chime = QCheckBox("Aviso sonoro al escucharme")
        self.chime.setChecked(self.config.voice.chime)
        layout.addWidget(self.chime)

        self.confirm = QCheckBox("Pedir confirmación en acciones destructivas")
        self.confirm.setChecked(self.config.safety.confirm_destructive)
        layout.addWidget(self.confirm)

        # --- botones ---
        layout.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self._on_cancel)
        buttons.addWidget(cancel)

        test = QPushButton("Probar voz")
        test.clicked.connect(self.test_voice.emit)
        buttons.addWidget(test)

        save = QPushButton("Guardar")
        save.setObjectName("Primary")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        hint = QLabel("La API key se guarda cifrada con tu usuario de Windows.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _fill_mics(self) -> None:
        self.mic.clear()
        self.mic.addItem("Automático (recomendado)", "")
        for device in list_input_devices():
            self.mic.addItem(device.label, device.name)
        current = self.config.voice.input_device
        for index in range(self.mic.count()):
            value = self.mic.itemData(index)
            if value and current and current.lower() in str(value).lower():
                self.mic.setCurrentIndex(index)
                return

    def _fill_voices(self) -> None:
        engine = self.engine.currentData() if hasattr(self, "engine") else "sapi"
        self.voice.clear()
        if engine == "edge":
            for short_name, label, _locale in EDGE_VOICES:
                self.voice.addItem(label, short_name)
            current = self.config.voice.edge_voice
        else:
            self.voice.addItem("Automática (primera en español)", "")
            for voice in list_sapi_voices():
                self.voice.addItem(voice.label, voice.name)
            current = self.config.voice.tts_voice
        for index in range(self.voice.count()):
            value = self.voice.itemData(index)
            if value and current and current.lower() in str(value).lower():
                self.voice.setCurrentIndex(index)
                return

    def _fill_outputs(self) -> None:
        self.output.clear()
        self.output.addItem("Predeterminada de Windows", "")
        for name in list_sapi_outputs():
            self.output.addItem(name, name)
        current = self.config.voice.output_device
        for index in range(self.output.count()):
            value = self.output.itemData(index)
            if value and current and current.lower() in str(value).lower():
                self.output.setCurrentIndex(index)
                return

    # ---------------------------------------------------------------- eventos

    def _on_provider_changed(self, _index: int) -> None:
        provider = self.provider.currentData()
        defaults = {
            "gemini": "gemini-3.5-flash-lite",
            "openai": "gpt-4o-mini",
            "local": "local-model",
        }
        if provider in defaults and (not self.model.text().strip() or "gemini" in self.model.text()):
            self.model.setText(defaults[provider])
        needs_url = provider in ("openai", "local")
        self.base_url.setEnabled(needs_url)

    def _on_cancel(self) -> None:
        self.closed.emit()
        self.close()

    def _on_save(self) -> None:
        cfg = self.config
        cfg.ai.provider = str(self.provider.currentData() or "gemini")
        cfg.ai.model = self.model.text().strip() or cfg.ai.model
        cfg.ai.api_key = self.api_key.text().strip()
        cfg.ai.base_url = self.base_url.text().strip()
        cfg.voice.input_device = str(self.mic.currentData() or "")
        engine = str(self.engine.currentData() or "sapi")
        cfg.voice.tts_engine = engine
        if engine == "edge":
            cfg.voice.edge_voice = str(self.voice.currentData() or cfg.voice.edge_voice)
        else:
            cfg.voice.tts_voice = str(self.voice.currentData() or "")
        cfg.voice.output_device = str(self.output.currentData() or "")
        cfg.voice.chime = self.chime.isChecked()
        cfg.voice.wake_word = self.wake_word.text().strip() or cfg.voice.wake_word
        cfg.voice.mode = str(self.mode.currentData() or cfg.voice.mode)
        cfg.voice.speak_replies = self.speak_replies.isChecked()
        cfg.voice.feedback = str(self.feedback.currentData() or cfg.voice.feedback)
        cfg.safety.confirm_destructive = self.confirm.isChecked()
        try:
            cfg.save()
        except OSError as exc:
            self.status_label.setText(f"No pude guardar: {exc}")
            return
        self.saved.emit(cfg)
        self.close()

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def show_near(self, anchor: QWidget) -> None:
        screen = anchor.screen()
        area = screen.availableGeometry() if screen else self.screen().availableGeometry()
        self.adjustSize()
        x = anchor.x() - self.width() - 16
        if x < area.left() + 8:
            x = anchor.x() + anchor.width() + 16
        y = anchor.y() + anchor.height() // 2 - self.height() // 2
        y = max(area.top() + 8, min(y, area.bottom() - self.height() - 8))
        x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
        self.move(QPoint(x, y))
        self.show()
        self.raise_()


def _section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setStyleSheet(
        f"color: {theme.MUTED.name()}; font-size: 10px; font-weight: 600; letter-spacing: 1px;"
    )
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Hint")
    return label


def _labeled(text: str, widget) -> QHBoxLayout:  # noqa: ANN001
    """Etiqueta corta a la izquierda y el control a la derecha."""
    row = QHBoxLayout()
    row.setSpacing(8)
    label = _hint(text)
    label.setFixedWidth(58)
    row.addWidget(label)
    row.addWidget(widget, 1)
    return row


def _select_data(combo: QComboBox, value: str) -> None:
    for index in range(combo.count()):
        if combo.itemData(index) == value:
            combo.setCurrentIndex(index)
            return
