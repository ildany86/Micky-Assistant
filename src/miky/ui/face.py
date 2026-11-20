"""La cara de Miky: ojos y cejas que cambian con el estado.

El logo es un micrófono; la cara se pinta encima de la cápsula. Cada estado
tiene una expresión (ojos más abiertos, cejas levantadas o fruncidas) y el
pasaje entre estados es suave, con parpadeo cada tanto.

Todo se dibuja con QPainter para que escale con el ícono (72–220 px).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from . import theme


@dataclass(frozen=True)
class Expression:
    """Parámetros de la cara. Todo en proporción al rectángulo del logo."""

    eye_open: float = 0.85  # 0 = cerrado, 1 = abierto, >1 = sorprendido
    eye_size: float = 1.0
    pupil_x: float = 0.0  # desplazamiento de la pupila (en radios)
    pupil_y: float = 0.0
    brow_lift: float = 0.0  # >0 levanta las cejas
    brow_tilt: float = 0.0  # >0 enoja (extremos internos abajo), <0 preocupa
    look_down: float = 0.0

    def blend(self, other: "Expression", t: float) -> "Expression":
        t = max(0.0, min(1.0, t))
        return Expression(
            eye_open=self.eye_open + (other.eye_open - self.eye_open) * t,
            eye_size=self.eye_size + (other.eye_size - self.eye_size) * t,
            pupil_x=self.pupil_x + (other.pupil_x - self.pupil_x) * t,
            pupil_y=self.pupil_y + (other.pupil_y - self.pupil_y) * t,
            brow_lift=self.brow_lift + (other.brow_lift - self.brow_lift) * t,
            brow_tilt=self.brow_tilt + (other.brow_tilt - self.brow_tilt) * t,
            look_down=self.look_down + (other.look_down - self.look_down) * t,
        )


EXPRESSIONS: dict[str, Expression] = {
    # Sin REAPER: ojos cerrados, cejas caídas. Duerme.
    "offline": Expression(eye_open=0.0, brow_lift=-2.2, brow_tilt=-3.0),
    # Escuchando: tranquilo, atento.
    "idle": Expression(eye_open=0.82, brow_lift=0.2),
    # Te escucho: ojos bien abiertos y cejas arriba.
    "listening": Expression(eye_open=1.16, eye_size=1.06, brow_lift=2.6, brow_tilt=-5.0),
    # Pensando: mira para arriba, una ceja más alta que la otra.
    "thinking": Expression(
        eye_open=0.92, pupil_x=1.1, pupil_y=-0.9, brow_lift=1.1, brow_tilt=-8.0
    ),
    "working": Expression(
        eye_open=0.9, pupil_x=0.6, pupil_y=-0.5, brow_lift=0.9, brow_tilt=-6.0
    ),
    # Hablando: ojos entornados, cara amable.
    "speaking": Expression(eye_open=0.66, brow_lift=2.0, brow_tilt=-2.0),
    # Confirmá: ojos grandes, cejas bien arriba.
    "confirm": Expression(eye_open=1.22, eye_size=1.08, brow_lift=3.4, brow_tilt=-9.0),
    # Error: ceño fruncido y ojos achicados.
    "error": Expression(eye_open=0.55, brow_lift=0.2, brow_tilt=10.0),
}

EYE_Y = 0.296  # centro de los ojos, relativo al logo
EYE_GAP = 0.083  # mitad de la distancia entre ojos
EYE_RADIUS = 0.060  # radio horizontal
BROW_GAP = 0.036  # separación entre ojo y ceja

_SCLERA = QColor(244, 249, 255, 242)
_PUPIL = QColor(16, 22, 32, 255)
_OUTLINE = QColor(9, 14, 22, 215)


def _eye_path(center: QPointF, rx: float, ry: float) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(center, rx, max(0.3, ry))
    return path


def paint_face(
    painter: QPainter,
    rect: QRectF,
    expression: Expression,
    color: QColor,
    blink: float = 1.0,
    look: tuple[float, float] = (0.0, 0.0),
    level: float = 0.0,
) -> None:
    """Dibuja ojos, cejas y boca dentro de `rect` (el rectángulo del logo).

    `look` mueve las pupilas hacia donde está el mouse (valores -1..1) y
    `level` (nivel del micrófono) levanta un poco las cejas cuando escucha.
    """
    width = rect.width()
    height = rect.height()
    if width < 40:
        return

    # En íconos chicos la cara se achica un poco para no comerse el micrófono.
    shrink = 1.0 if width >= 100 else max(0.84, 0.84 + (width - 60) * 0.004)

    listening = expression.brow_lift > 1.5
    lift_extra = min(2.2, max(0.0, level) * 26.0) if listening else 0.0
    pupil_extra_x = 0.9 * look[0] if look else 0.0
    pupil_extra_y = 0.9 * look[1] if look else 0.0

    openness = max(0.0, expression.eye_open * blink)
    rx = width * EYE_RADIUS * expression.eye_size * shrink
    ry = height * EYE_RADIUS * 1.28 * expression.eye_size * openness * shrink
    cy = rect.top() + height * (EYE_Y - expression.look_down * 0.01)
    center_x0 = rect.center().x() - width * EYE_GAP * shrink
    center_x1 = rect.center().x() + width * EYE_GAP * shrink

    # Cejas primero, para que los ojos queden limpios encima.
    brow_color = QColor(color)
    brow_color.setAlpha(210)
    if expression.brow_tilt > 6:
        # Enojo: la ceja se oscurece un poco para marcar el ceño.
        brow_color = brow_color.darker(135)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    lift = height * (0.100 + (expression.brow_lift + lift_extra) * 0.011)
    paths: list[QPainterPath] = []
    for side in (-1, 1):
        center_x = center_x0 if side < 0 else center_x1
        inner = center_x - side * width * 0.028 * shrink
        outer = center_x + side * width * 0.031 * shrink
        # El extremo interno sube o baja según brow_tilt (enojo/preocupación).
        tilt = math.radians(expression.brow_tilt)
        dy_inner = math.tan(tilt) * width * 0.028 * shrink
        dy_outer = -math.tan(tilt) * width * 0.031 * shrink
        y_inner = cy - lift + dy_inner
        y_outer = cy - lift + dy_outer
        path = QPainterPath(QPointF(inner, y_inner))
        path.quadTo(
            QPointF((inner + outer) / 2, min(y_inner, y_outer) - height * 0.012),
            QPointF(outer, y_outer),
        )
        paths.append(path)

    # Dos pasadas: borde oscuro y encima el color del estado. Así la ceja se
    # despega del aro y del metal, y sigue cambiando de color con el estado.
    thick = max(2.0, width * 0.025 * shrink)
    outline_pen = QPen(QColor(9, 13, 20, 225))
    outline_pen.setWidthF(thick + max(1.4, width * 0.012))
    outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(outline_pen)
    for path in paths:
        painter.drawPath(path)

    color_pen = QPen(brow_color)
    color_pen.setWidthF(thick)
    color_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(color_pen)
    for path in paths:
        painter.drawPath(path)

    # Ojos.
    for side in (-1, 1):
        center_x = center_x0 if side < 0 else center_x1
        center = QPointF(center_x, cy)
        if ry < 0.8:
            # Ojo cerrado: una línea curva gruesa, como dormido.
            closed = QPainterPath(QPointF(center_x - rx, cy - height * 0.004))
            closed.quadTo(
                QPointF(center_x, cy + ry + height * 0.016),
                QPointF(center_x + rx, cy - height * 0.004),
            )
            painter.setPen(
                QPen(_OUTLINE, max(2.0, width * 0.020), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(closed)
            continue

        painter.setPen(QPen(_OUTLINE, max(0.9, width * 0.008)))
        painter.setBrush(_SCLERA)
        painter.drawPath(_eye_path(center, rx, ry))

        # Pupila, un poco más chica cuando la luz es mucha (sorpresa).
        pupil_rx = rx * (0.38 if expression.eye_open < 1.0 else 0.33)
        pupil_ry = ry * 0.52
        if listening:
            # Mientras le hablás, la pupila se agranda: parece que te mira.
            pupil_rx *= 1.0 + 0.28 * min(1.0, max(0.0, level) * 6.0)
            pupil_rx = min(pupil_rx, rx * 0.54)
        px = center_x + (expression.pupil_x + pupil_extra_x) * rx * 0.55
        py = cy + (expression.pupil_y + pupil_extra_y) * ry * 0.45
        # La pupila no puede salirse del ojo.
        px = max(center_x - rx * 0.55, min(center_x + rx * 0.55, px))
        py = max(cy - ry * 0.55, min(cy + ry * 0.55, py))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_PUPIL)
        painter.drawEllipse(QPointF(px, py), pupil_rx, pupil_ry)

        # Brillo.
        highlight = QColor(255, 255, 255, 200)
        painter.setBrush(highlight)
        painter.drawEllipse(
            QPointF(px - pupil_rx * 0.35, py - pupil_ry * 0.42),
            max(0.6, pupil_rx * 0.28),
            max(0.6, pupil_ry * 0.28),
        )


def expression_for(state: str) -> Expression:
    return EXPRESSIONS.get(state, EXPRESSIONS["idle"])


__all__ = ["Expression", "EXPRESSIONS", "expression_for", "paint_face", "theme"]
