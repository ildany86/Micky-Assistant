"""Asistente de primera vez: micrófono, API key y puente en un solo flujo.

Se muestra la primera vez que se abre Miky (o si falta la API key). Al terminar
guarda todo y no vuelve a aparecer.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, log as log_mod, reaper
from ..config import Config
from . import theme
from .logo import resolve_logo

log = log_mod.get("miky.ui.wizard")

PAGES = ("Bienvenida", "Micrófono", "API key", "REAPER", "Listo")


class _LevelMeter:
    """Mide el nivel del micrófono para el paso 2 (sin abrir el pipeline)."""

    def __init__(self) -> None:
        self.level = 0.0
        self._stream: Any = None

    def start(self, device: int | None) -> None:
        self.stop()
        try:
            import numpy as np
            import sounddevice as sd

            def callback(indata, _frames, _time_info, _status) -> None:  # noqa: ANN001
                self.level = float(np.sqrt(np.mean(np.square(indata))))

            self._stream = sd.InputStream(
                device=device,
                channels=1,
                samplerate=16000,
                blocksize=512,
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:  # noqa: BLE001
            log.warning("no pude abrir el micrófono para la prueba: %s", exc)
            self._stream = None

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        self.level = 0.0


def _title(text: str) -> QLabel:
    label = QLabel(text)
    font = QFont()
    font.setPointSize(16)
    font.setBold(True)
    label.setFont(font)
    return label


def _body(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.MUTED.name()};")
    return label


class FirstRunWizard(QDialog):
    def __init__(self, config: Config) -> None:
        super().__init__()
        self.config = config
        self.meter = _LevelMeter()
        self.completed = False

        self.setWindowTitle(f"Miky {__version__} · primeros pasos")
        self.setMinimumWidth(560)
        self.setStyleSheet(theme.STYLESHEET)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_microphone())
        self.stack.addWidget(self._page_key())
        self.stack.addWidget(self._page_reaper())
        self.stack.addWidget(self._page_done())

        self.back = QPushButton("Atrás")
        self.back.clicked.connect(self._go_back)
        self.next = QPushButton("Siguiente")
        self.next.setDefault(True)
        self.next.clicked.connect(self._go_next)
        self.cancel = QPushButton("Cancelar")
        self.cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.cancel)
        buttons.addStretch(1)
        buttons.addWidget(self.back)
        buttons.addWidget(self.next)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(self.stack)
        layout.addLayout(buttons)

        self._update_buttons()
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick_meter)
        self._timer.start()

    # ------------------------------------------------------------- páginas

    def _page_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        logo = resolve_logo()
        if logo:
            pixmap = QPixmap(str(logo))
            if not pixmap.isNull():
                label = QLabel()
                label.setPixmap(
                    pixmap.scaled(
                        120,
                        120,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(label)

        layout.addWidget(_title("Bienvenido a Miky"))
        layout.addWidget(
            _body(
                "Miky maneja REAPER con la voz: pistas, plugins, envíos, grabación y render.\n\n"
                "Son tres pasos y un minuto: elegir el micrófono, pegar la API key y "
                "conectar REAPER."
            )
        )
        layout.addStretch(1)
        return page

    def _page_microphone(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.addWidget(_title("Micrófono"))
        layout.addWidget(
            _body(
                "Elegí con qué micrófono te va a escuchar. Si usás una interfaz de audio "
                "con REAPER en ASIO, conviene el micrófono interno: REAPER toma la "
                "interfaz en exclusiva."
            )
        )
        self.mic = QComboBox()
        self._fill_devices()
        layout.addWidget(self.mic)

        self.level_bar = QProgressBar()
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(10)
        layout.addWidget(self.level_bar)
        self.level_hint = _body("Hablá algo: la barra tiene que moverse.")
        layout.addWidget(self.level_hint)

        row = QHBoxLayout()
        test = QPushButton("Probar sonido")
        test.clicked.connect(self._play_test)
        row.addWidget(test)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        self.mic.currentIndexChanged.connect(self._restart_meter)
        return page

    def _page_key(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.addWidget(_title("API key de Gemini"))
        layout.addWidget(
            _body(
                "La clave es gratis y se saca en aistudio.google.com/apikey. Se guarda "
                "cifrada con tu usuario de Windows y no sale de la computadora.\n"
                "Solo el texto de tus órdenes viaja a la nube: el audio nunca."
            )
        )
        row = QHBoxLayout()
        self.key = QLineEdit(self.config.ai.api_key)
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Pegá tu API key acá")
        row.addWidget(self.key, 1)
        show = QPushButton("Ver")
        show.setCheckable(True)
        show.toggled.connect(
            lambda visible: self.key.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
            )
        )
        row.addWidget(show)
        layout.addLayout(row)

        test_row = QHBoxLayout()
        self.test_key = QPushButton("Probar conexión")
        self.test_key.clicked.connect(self._test_key)
        test_row.addWidget(self.test_key)
        self.key_status = _body("")
        test_row.addWidget(self.key_status, 1)
        layout.addLayout(test_row)
        layout.addStretch(1)
        return page

    def _page_reaper(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.addWidget(_title("Conectar REAPER"))
        layout.addWidget(
            _body(
                "Miky instala un pequeño puente dentro de REAPER (un script que se inicia "
                "solo). No es un plugin y podés quitarlo cuando quieras."
            )
        )
        self.bridge_status = _body("")
        layout.addWidget(self.bridge_status)
        row = QHBoxLayout()
        install = QPushButton("Instalar puente")
        install.clicked.connect(self._install_bridge)
        row.addWidget(install)
        open_reaper = QPushButton("Abrir REAPER")
        open_reaper.clicked.connect(self._open_reaper)
        row.addWidget(open_reaper)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _page_done(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)
        layout.addWidget(_title("Todo listo"))
        layout.addWidget(
            _body(
                "Miky va a quedar como un ícono flotante. Decí:\n\n"
                "«Miky, creá una pista de guitarra»\n"
                "«Miky, subí el bajo dos dB»\n"
                "«Miky, grabá»\n\n"
                "Clic derecho en el ícono para los ajustes y para abrir REAPER."
            )
        )
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------- lógica

    def _input_devices(self) -> list[tuple[int, str]]:
        devices: list[tuple[int, str]] = []
        try:
            import sounddevice as sd

            for index, device in enumerate(sd.query_devices()):
                if int(device.get("max_input_channels") or 0) > 0:
                    devices.append((index, str(device.get("name"))))
        except Exception:  # noqa: BLE001
            pass
        return devices

    def _fill_devices(self) -> None:
        self.mic.addItem("Automático (recomendado)", -1)
        for index, name in self._input_devices():
            self.mic.addItem(f"{index}: {name}", index)
        configured = self.config.voice.input_device
        if configured:
            for position in range(self.mic.count()):
                if configured in self.mic.itemText(position):
                    self.mic.setCurrentIndex(position)
                    break

    def _selected_device(self) -> int | None:
        data = self.mic.currentData()
        return None if data in (None, -1) else int(data)

    def _restart_meter(self, *_args: Any) -> None:
        self.meter.start(self._selected_device())

    def _tick_meter(self) -> None:
        if self.stack.currentIndex() != 1:
            if self.meter._stream is not None:
                self.meter.stop()
            return
        if self.meter._stream is None:
            self.meter.start(self._selected_device())
        level = min(1.0, self.meter.level * 6.0)
        self.level_bar.setValue(int(level * 100))

    def _play_test(self) -> None:
        from ..voice.feedback import chime

        threading.Thread(target=chime, args=("wake",), daemon=True).start()

    def _test_key(self) -> None:
        key = self.key.text().strip()
        if not key:
            self.key_status.setText("Pegá la clave primero.")
            return
        self.key_status.setText("Probando…")
        QApplication.processEvents()
        self.config.ai.api_key = key
        try:
            from ..ai import build_provider
            from ..catalog import Catalog

            provider = build_provider(self.config.ai)
            catalog = Catalog.load().subset(["miky_respond"])
            started = time.perf_counter()
            result = provider.interpret("Respondé solo: listo", {"assistant": {"name": "Miky"}}, catalog)
            elapsed = time.perf_counter() - started
            if result.answer or result.steps:
                self.key_status.setText(f"Funciona ({elapsed:.1f} s).")
            else:
                self.key_status.setText("Respondió vacío; probá de nuevo.")
        except Exception as exc:  # noqa: BLE001
            self.key_status.setText(f"No funcionó: {str(exc)[:90]}")

    def _install_bridge(self) -> None:
        try:
            install = reaper.find_install(
                self.config.reaper.install_path, self.config.reaper.resource_path
            )
            if not install.found:
                self.bridge_status.setText("No encontré REAPER instalado en esta computadora.")
                return
            ok, message = reaper.ensure_bridge_ready(install)
            self.bridge_status.setText(("✓ " if ok else "✗ ") + message)
        except Exception as exc:  # noqa: BLE001
            self.bridge_status.setText(f"No pude instalar el puente: {exc}")

    def _open_reaper(self) -> None:
        try:
            install = reaper.find_install(
                self.config.reaper.install_path, self.config.reaper.resource_path
            )
            reaper.launch_reaper(install, with_bridge=True)
            self.bridge_status.setText("Abriendo REAPER…")
        except Exception as exc:  # noqa: BLE001
            self.bridge_status.setText(f"No pude abrir REAPER: {exc}")

    def _update_buttons(self) -> None:
        index = self.stack.currentIndex()
        self.back.setEnabled(index > 0)
        self.next.setText("Empezar" if index == len(PAGES) - 1 else "Siguiente")

    def _go_back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._update_buttons()

    def _go_next(self) -> None:
        index = self.stack.currentIndex()
        if index == 1:
            device = self._selected_device()
            self.config.voice.input_device = (
                self.mic.currentText().split(": ", 1)[-1] if device is not None else ""
            )
        if index == 2:
            self.config.ai.api_key = self.key.text().strip()
        if index == len(PAGES) - 1:
            self._finish()
            return
        self.stack.setCurrentIndex(index + 1)
        self._update_buttons()

    def _finish(self) -> None:
        self.config.ui.onboarded = True
        try:
            self.config.save()
        except OSError as exc:
            log.warning("no pude guardar la configuración del asistente: %s", exc)
        self.completed = True
        self.meter.stop()
        self.accept()

    def reject(self) -> None:
        self.meter.stop()
        # Si ya eligió una key, se guarda igual: no perder el trabajo.
        key = self.key.text().strip()
        if key:
            self.config.ai.api_key = key
            try:
                self.config.save()
            except OSError:
                pass
        super().reject()


def show_first_run(config: Config) -> bool:
    """Muestra el asistente. Devuelve True si terminó (y quedó configurado)."""
    app = QApplication.instance() or QApplication(sys.argv)
    wizard = FirstRunWizard(config)
    wizard.exec()
    return wizard.completed
