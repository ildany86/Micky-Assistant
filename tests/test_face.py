"""Pruebas de la cara del ícono (ojos y cejas)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from miky.ui import face, theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def test_todos_los_estados_tienen_cara() -> None:
    for state in theme.STATE_COLORS:
        expression = face.expression_for(state)
        assert isinstance(expression, face.Expression)


def test_estado_desconocido_cae_en_la_cara_normal() -> None:
    assert face.expression_for("inventado") == face.expression_for("idle")


@pytest.mark.parametrize("size", [40, 72, 104, 220])
@pytest.mark.parametrize("blink", [1.0, 0.5, 0.0])
def test_dibujar_la_cara_no_falla(app, size: int, blink: float) -> None:
    pixmap = QPixmap(size, size)
    pixmap.fill()
    painter = QPainter(pixmap)
    try:
        for state in theme.STATE_COLORS:
            face.paint_face(
                painter,
                pixmap.rect().toRectF().adjusted(4, 4, -4, -4),
                face.expression_for(state),
                QColor(theme.STATE_COLORS[state]),
                blink,
            )
    finally:
        painter.end()
    assert not pixmap.isNull()


def test_mezcla_de_expresiones() -> None:
    abierta = face.Expression(eye_open=1.2, brow_lift=3.0, brow_tilt=-5.0)
    cerrada = face.Expression(eye_open=0.0, brow_lift=0.0, brow_tilt=0.0)
    medio = abierta.blend(cerrada, 0.5)
    assert medio.eye_open == pytest.approx(0.6)
    assert medio.brow_lift == pytest.approx(1.5)
    assert abierta.blend(cerrada, 0.0) == abierta
    assert abierta.blend(cerrada, 1.0) == cerrada
    # t fuera de rango se recorta.
    assert abierta.blend(cerrada, 2.0) == cerrada


def test_la_cara_cambia_entre_estados(app) -> None:
    from miky.ui.icon import FloatingIcon

    icon = FloatingIcon(size=104)
    icon.set_state("speaking")
    icon.snap_face()
    hablando = icon._expression
    icon.set_state("error")
    icon.snap_face()
    enojo = icon._expression
    assert hablando.eye_open != enojo.eye_open
    assert hablando.brow_tilt != enojo.brow_tilt


def test_parpadeo_baja_y_vuelve(app) -> None:
    from miky.ui.icon import BLINK_DURATION, FloatingIcon

    icon = FloatingIcon(size=104)
    icon.set_state("idle")
    icon.snap_face()
    icon._blinking = True
    # _update_face suma un cuadro (0.033 s) antes de calcular el parpadeo.
    icon._blink_t = BLINK_DURATION / 2 - 0.033
    icon._update_face()
    assert icon._blink < 0.05
    icon._blink_t = 99
    icon._update_face()
    assert icon._blink == 1.0
    assert icon._blinking is False
