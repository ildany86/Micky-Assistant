"""Cáscara de interfaz: solo el icono flotante, la bandeja y dos popups.

No hay ventana principal. Todo lo que se ve son tres cosas: el logo flotante,
un menú contextual y un panel de ajustes que aparece pegado al icono.
"""

from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import __version__, log as log_mod, paths
from ..config import Config
from . import theme
from .confirm import ConfirmPopup
from .icon import FloatingIcon
from .logo import resolve_logo
from .settings import SettingsPanel
from .tray import MikyTray

log = log_mod.get("miky.ui")

ICON_BASE_SIZE = 104


class _UiBridge(QObject):
    """Señales puente para hablar con el núcleo desde cualquier hilo."""

    confirm_requested = Signal(str)
    confirm_closed = Signal()
    notice = Signal(str)


class MikyShell:
    def __init__(self, core: Any, config: Config) -> None:
        self.core = core
        self.config = config
        self.ui_bridge = _UiBridge()
        self.app: QApplication | None = None
        self.icon: FloatingIcon | None = None
        self.tray: MikyTray | None = None
        self.menu: QMenu | None = None
        self.settings: SettingsPanel | None = None
        self.confirm_popup: ConfirmPopup | None = None
        self._last_state = ""
        self._last_tooltip = ""
        self._status_action: QAction | None = None
        self._listen_action: QAction | None = None

    # ---------------------------------------------------------------- arranque

    def run(self, quit_after: float | None = None) -> int:
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setApplicationName("Miky")
        self.app.setApplicationDisplayName("Miky")
        self.app.setOrganizationName("Miky")
        self.app.setApplicationVersion(__version__)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyleSheet(theme.STYLESHEET)

        self._build_icon()
        self._build_menu()
        self._build_tray()
        self._build_confirm()
        self._wire_core()

        self.app.setWindowIcon(self.icon.render_icon())
        self.icon.show()

        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(120)

        self._first_run_notice()
        log.info("interfaz lista")
        if quit_after:
            QTimer.singleShot(int(quit_after * 1000), self.quit)
        return self.app.exec()

    def _build_icon(self) -> None:
        scale = max(0.6, min(2.0, float(self.config.ui.scale or 1.0)))
        size = int(ICON_BASE_SIZE * scale)
        self.icon = FloatingIcon(size=size, logo_path=self.config.ui.logo)
        self.icon.place_initial(*self.config.ui.position)
        self.icon.set_state("offline")

        self.icon.clicked.connect(self._on_icon_clicked)
        self.icon.double_clicked.connect(self._open_settings)
        self.icon.context_menu_requested.connect(self._show_menu_at)
        self.icon.drag_finished.connect(self._on_icon_moved)

    def _build_menu(self) -> None:
        menu = QMenu()
        self._listen_action = menu.addAction("Escuchar ahora")
        self._listen_action.triggered.connect(self._on_listen)

        settings = menu.addAction("Ajustes…")
        settings.triggered.connect(self._open_settings)

        self._status_action = menu.addAction("Estado…")
        self._status_action.setEnabled(False)

        menu.addSeparator()
        faster = menu.addAction("Abrir REAPER con Miky")
        faster.triggered.connect(self._on_open_reaper)

        reinstall = menu.addAction("Reinstalar puente")
        reinstall.triggered.connect(self._on_reinstall_bridge)

        whats = menu.addAction("¿Qué puedo pedirte?")
        whats.triggered.connect(self._on_help)

        menu.addSeparator()
        quit_action = menu.addAction("Salir")
        quit_action.triggered.connect(self.quit)

        menu.aboutToShow.connect(self._update_menu)
        self.menu = menu

    def _build_tray(self) -> None:
        if not self.icon:
            return
        self.tray = MikyTray(self.icon.render_icon(), self.menu, tooltip="Miky")
        self.tray.setToolTip(f"Miky {__version__}")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_confirm(self) -> None:
        self.confirm_popup = ConfirmPopup()
        self.confirm_popup.answered.connect(self._on_confirm_answer)

    def _wire_core(self) -> None:
        # El núcleo pide confirmaciones; desde un hilo de trabajo se pasa por señal.
        self.core._request_confirmation = lambda question: self.ui_bridge.confirm_requested.emit(question)
        self.core._close_confirmation = lambda: self.ui_bridge.confirm_closed.emit()
        self.ui_bridge.confirm_requested.connect(self._show_confirm)
        self.ui_bridge.confirm_closed.connect(self._hide_confirm)
        self.ui_bridge.notice.connect(self._on_notice)

    # ---------------------------------------------------------------- refresco

    def _refresh(self) -> None:
        if self.icon is None:
            return
        state = self.core.compute_state()
        if state != self._last_state:
            self.icon.set_state(state)
            self._last_state = state
        tooltip = self.core.tooltip()
        if tooltip != self._last_tooltip:
            self.icon.set_tooltip(tooltip)
            self._last_tooltip = tooltip
            if self.tray is not None:
                self.tray.setToolTip(tooltip.splitlines()[0] if tooltip else "Miky")
        pipeline = getattr(self.core, "pipeline", None)
        capture = getattr(pipeline, "capture", None) if pipeline is not None else None
        self.icon.set_level(getattr(capture, "level", 0.0) if capture is not None else 0.0)

    # ---------------------------------------------------------------- confirmación

    def _show_confirm(self, question: str) -> None:
        if self.icon is None or self.confirm_popup is None:
            return
        try:
            self.core.tts.speak(question)
        except Exception:  # noqa: BLE001
            pass
        self.confirm_popup.ask(question, self.icon)

    def _hide_confirm(self) -> None:
        if self.confirm_popup is not None:
            self.confirm_popup.dismiss()

    def _on_confirm_answer(self, value: bool) -> None:
        self.core.respond_confirmation(value)

    # ---------------------------------------------------------------- acciones

    def _on_icon_clicked(self) -> None:
        if self.core.tts.is_speaking:
            self.core.stop_speaking()
            return
        self.core.trigger_listen()

    def _on_icon_moved(self, x: int, y: int) -> None:
        self.config.ui.position = (int(x), int(y))
        try:
            self.config.save()
        except OSError:
            log.debug("no pude guardar la posición del icono")

    def _show_menu_at(self, position: QPoint) -> None:
        if self.menu is None:
            return
        self.menu.popup(position)

    def _on_tray_activated(self, reason) -> None:  # noqa: ANN001
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open_settings()

    def _open_settings(self) -> None:
        if self.icon is None:
            return
        if self.settings is not None and self.settings.isVisible():
            self.settings.close()
            return
        status = self.core.status
        status_text = status.summary + (
            f" · {self.core.provider.description}" if getattr(self.core, "provider", None) else ""
        )
        if not self.config.has_api_key:
            status_text += " · falta la API key"
        panel = SettingsPanel(self.config, status_text)
        panel.saved.connect(self._on_settings_saved)
        panel.test_voice.connect(self._test_voice)
        panel.closed.connect(lambda: None)
        self.settings = panel
        panel.show_near(self.icon)

    def _on_settings_saved(self, config: Config) -> None:
        log.info("ajustes guardados")
        self.config = config
        self.core.apply_config(config)
        if self.icon is not None:
            scale = max(0.6, min(2.0, float(config.ui.scale or 1.0)))
            self.icon.set_size(int(ICON_BASE_SIZE * scale))
            self.icon.reload_logo(config.ui.logo)
        self._last_state = ""
        self._last_tooltip = ""
        self._refresh()

    def _test_voice(self) -> None:
        phrase = "Hola, soy Miky. Estoy escuchando la sesión."
        try:
            self.core.tts.speak(phrase)
        except Exception:  # noqa: BLE001
            log.warning("no pude probar la voz", exc_info=True)

    def _on_listen(self) -> None:
        self.core.trigger_listen()

    def _on_open_reaper(self) -> None:
        self.core.open_reaper()

    def _on_reinstall_bridge(self) -> None:
        self.core.reinstall_bridge()

    def _on_help(self) -> None:
        self.core.say_help()

    def _update_menu(self) -> None:
        if self._status_action is None:
            return
        status = self.core.status
        self._status_action.setText(f"Estado: {status.summary}")
        pipeline = getattr(self.core, "pipeline", None)
        listening = bool(pipeline is not None and pipeline.running)
        if self._listen_action is not None:
            self._listen_action.setEnabled(listening)

    def _first_run_notice(self) -> None:
        if not self.config.has_api_key:
            if self.tray is not None:
                self.tray.show_message(
                    "Miky",
                    "Pegá tu API key de Gemini en Ajustes (clic derecho en el icono) para que entienda pedidos complejos.",
                    6,
                )
            return
        if self.tray is not None:
            self.tray.show_message("Miky", f"Listo. {self.core.status.summary}", 3)

    def _on_notice(self, text: str) -> None:
        log.debug("aviso: %s", text)

    # ---------------------------------------------------------------- cierre

    def quit(self) -> None:
        log.info("cerrando Miky")
        try:
            self.core.stop()
        except Exception:  # noqa: BLE001
            log.debug("error al cerrar el núcleo", exc_info=True)
        if self.tray is not None:
            self.tray.hide()
        if self.icon is not None:
            self.icon.hide()
        if self.app is not None:
            self.app.quit()
