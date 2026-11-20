"""El asistente de primera vez: páginas, navegación y guardado."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from miky.config import Config  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def wizard(app, tmp_path, monkeypatch):
    from miky.ui.wizard import FirstRunWizard

    config = Config()
    config.ai.api_key = ""
    saved: list[bool] = []
    monkeypatch.setattr(config, "save", lambda: saved.append(True), raising=False)
    config._saved = saved  # type: ignore[attr-defined]
    instance = FirstRunWizard(config)
    yield instance
    instance.meter.stop()
    instance.deleteLater()


def test_tiene_los_cinco_pasos(wizard) -> None:
    assert wizard.stack.count() == 5
    assert wizard.stack.currentIndex() == 0


def test_navegacion_avanza_y_vuelve(wizard) -> None:
    wizard._go_next()
    assert wizard.stack.currentIndex() == 1
    wizard._go_back()
    assert wizard.stack.currentIndex() == 0
    assert wizard.back.isEnabled() is False


def test_el_boton_cambia_en_el_ultimo_paso(wizard) -> None:
    for _ in range(4):
        wizard._go_next()
    assert wizard.stack.currentIndex() == 4
    assert wizard.next.text() == "Empezar"


def test_finalizar_marca_onboarded_y_guarda(wizard) -> None:
    for _ in range(4):
        wizard._go_next()
    wizard._finish()
    assert wizard.completed is True
    assert wizard.config.ui.onboarded is True
    assert wizard.config._saved  # type: ignore[attr-defined]


def test_cancelar_con_clave_la_guarda_igual(wizard) -> None:
    wizard.key.setText("clave-de-prueba")
    wizard.reject()
    assert wizard.completed is False
    assert wizard.config.ui.onboarded is False
    assert wizard.config.ai.api_key == "clave-de-prueba"
    assert wizard.config._saved  # type: ignore[attr-defined]


def test_el_microfono_automatico_no_fija_dispositivo(wizard) -> None:
    wizard.mic.setCurrentIndex(0)  # "Automático"
    assert wizard._selected_device() is None
