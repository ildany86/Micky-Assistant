"""El icono flotante: toda la interfaz visible de Miky.

No tiene barra de título, no aparece en la barra de tareas y no le roba el foco
a REAPER (clave: si robara el foco, grabar con el teclado se volvería un
infierno). Se arrastra con el mouse y la posición queda guardada.

Lenguaje visual:
- punto de estado abajo a la derecha: color = qué está pasando;
- halo: respira cuando está escuchando, gira cuando piensa, se pone rojo si hay error;
- logo al 50% de opacidad cuando no hay conexión con REAPER.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QIcon,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from . import face, theme
from .logo import load_logo_pixmap, paint_mic_glyph

DEFAULT_SIZE = 104
GLOW_RATIO = 0.10
BLINK_DURATION = 0.16


class FloatingIcon(QWidget):
    clicked = Signal()
    double_clicked = Signal()
    context_menu_requested = Signal(QPoint)
    drag_finished = Signal(int, int)

    def __init__(self, size: int = DEFAULT_SIZE, logo_path: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = max(72, int(size))
        self._logo_path = logo_path
        self._logo: QPixmap | None = None
        self._state = "offline"
        self._tooltip = "Miky"
        self._phase = 0.0
        self._level = 0.0
        # Cara: expresión actual, objetivo y parpadeo.
        self._expression = face.expression_for("offline")
        self._target = self._expression
        self._blink = 1.0
        self._blink_t = 0.0
        self._blinking = False
        self._next_blink = 3.2
        self._dragging = False
        self._moved = False
        self._press_pos = QPoint()
        self._window_start = QPoint()

        self.setFixedSize(self._size, self._size)
        self.setWindowTitle("Miky")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._tooltip)
        self._reload_logo()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    # ---------------------------------------------------------------- estado

    def _reload_logo(self) -> None:
        target = int(self._size * 2.4)  # margen para HiDPI y escalado suave
        self._logo = load_logo_pixmap(self._logo_path, target)
        self.update()

    def reload_logo(self, logo_path: str | None = None) -> None:
        if logo_path is not None:
            self._logo_path = logo_path
        self._reload_logo()

    def set_size(self, size: int) -> None:
        size = max(72, min(220, int(size)))
        if size == self._size:
            return
        center = self.frameGeometry().center()
        self._size = size
        self.setFixedSize(size, size)
        self.move(center.x() - size // 2, center.y() - size // 2)
        self._reload_logo()
        self._clamp_to_screen()

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._target = face.expression_for(state)
        self.update()

    def _look_direction(self) -> tuple[float, float]:
        """Hacia dónde mira: sigue al mouse cuando está atento."""
        if self._state in ("offline", "thinking", "working", "error"):
            return (0.0, 0.0)
        try:
            cursor = QCursor.pos()
        except Exception:  # noqa: BLE001
            return (0.0, 0.0)
        center = self.mapToGlobal(self.rect().center())
        dx = (cursor.x() - center.x()) / max(1.0, self.width() * 0.5)
        dy = (cursor.y() - center.y()) / max(1.0, self.height() * 0.5)
        # Zona muerta: si el mouse está cerca del centro, mira al frente.
        dx = 0.0 if abs(dx) < 0.35 else max(-1.0, min(1.0, dx))
        dy = 0.0 if abs(dy) < 0.35 else max(-1.0, min(1.0, dy))
        return (dx, dy)

    def snap_face(self) -> None:
        """Salta a la expresión del estado actual (para renders y pruebas)."""
        self._target = face.expression_for(self._state)
        self._expression = self._target
        self._blink = 1.0
        self._blinking = False
        self.update()

    @property
    def state(self) -> str:
        return self._state

    @property
    def has_logo(self) -> bool:
        return self._logo is not None and not self._logo.isNull()

    def set_tooltip(self, text: str) -> None:
        self._tooltip = text
        self.setToolTip(text)

    def set_level(self, level: float) -> None:
        new_level = max(0.0, min(1.0, float(level)))
        if abs(new_level - self._level) > 0.01:
            self._level = new_level

    def render_pixmap(self, size: int = 64) -> QPixmap:
        """Versión limpia (sin halo ni punto) para la bandeja del sistema."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(1, 1, size - 2, size - 2)
        if self.has_logo:
            painter.drawPixmap(rect.toRect(), self._logo)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(20, 26, 37, 240))
            painter.drawEllipse(rect)
            paint_mic_glyph(painter, rect.adjusted(size * 0.24, size * 0.24, -size * 0.24, -size * 0.24), QColor(theme.TEXT))
        painter.end()
        return pixmap

    def render_icon(self) -> QIcon:
        return QIcon(self.render_pixmap(64))

    # ---------------------------------------------------------------- animación

    def _tick(self) -> None:
        self._phase = (self._phase + 0.07) % (math.pi * 2)
        self._update_face()
        if self._state in ("listening", "thinking", "working", "speaking", "idle", "confirm", "error"):
            self.update()

    def _update_face(self) -> None:
        # Transición suave entre expresiones.
        self._expression = self._expression.blend(self._target, 0.22)

        # Parpadeo cada tanto (no cuando duerme o piensa fijo).
        if self._blinking:
            self._blink_t += 0.033
            if self._blink_t >= BLINK_DURATION:
                self._blinking = False
                self._blink = 1.0
                self._next_blink = random.uniform(3.5, 7.5)
            else:
                self._blink = abs(math.cos(math.pi * self._blink_t / BLINK_DURATION))
        else:
            self._next_blink -= 0.033
            if self._next_blink <= 0 and self._state not in ("offline",):
                self._blinking = True
                self._blink_t = 0.0

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        color = theme.STATE_COLORS.get(self._state, theme.STATE_COLORS["idle"])
        if self.has_logo:
            self._paint_with_logo(painter, rect, color)
        else:
            self._paint_placeholder(painter, rect, color)
        self._paint_badge(painter, rect, color)
        painter.end()

    def _paint_badge(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        """Globito con «?» mientras piensa y «!» si algo falló.

        Los símbolos se dibujan como formas (no como texto): así se ven igual
        en cualquier equipo, sin depender de las fuentes instaladas.
        """
        symbol = {"thinking": "?", "working": "?", "error": "!"}.get(self._state)
        if not symbol:
            return
        size = rect.width()
        radius = size * 0.16
        center = QPointF(rect.right() - radius * 0.9, rect.top() + radius * 0.9)
        fill = QColor(color)
        fill.setAlpha(238)
        painter.setPen(QPen(QColor(10, 14, 22, 170), max(1.0, size * 0.008)))
        painter.setBrush(fill)
        painter.drawEllipse(center, radius, radius)

        ink = QColor(10, 14, 22, 245)
        if symbol == "?":
            pen = QPen(ink, max(1.4, radius * 0.30))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = radius * 0.42
            box = QRectF(center.x() - r, center.y() - r * 1.15, r * 2, r * 2)
            path = QPainterPath()
            path.arcMoveTo(box, 165)
            path.arcTo(box, 165, -235)
            path.lineTo(QPointF(center.x() + r * 0.12, center.y() + r * 0.35))
            painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            dot = max(1.0, radius * 0.15)
            painter.drawEllipse(QPointF(center.x() + r * 0.12, center.y() + r * 0.95), dot, dot)
        else:
            pen = QPen(ink, max(1.6, radius * 0.32))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(center.x(), center.y() - radius * 0.48),
                QPointF(center.x(), center.y() + radius * 0.12),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ink)
            dot = max(1.2, radius * 0.16)
            painter.drawEllipse(QPointF(center.x(), center.y() + radius * 0.52), dot, dot)

    # ---------------------------------------------------------------- logo real

    def _paint_with_logo(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        center = rect.center()
        radius = rect.width() / 2
        pad = max(7.0, rect.width() * GLOW_RATIO)
        logo_rect = rect.adjusted(pad, pad, -pad, -pad)

        if self._state != "offline":
            halo = QRadialGradient(center, radius)
            alpha = self._glow_alpha()
            inner = QColor(color)
            inner.setAlpha(int(alpha))
            halo.setColorAt(0.0, inner)
            inner_mid = QColor(color)
            inner_mid.setAlpha(int(alpha * 0.45))
            halo.setColorAt(0.62, inner_mid)
            transparent = QColor(color)
            transparent.setAlpha(0)
            halo.setColorAt(1.0, transparent)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(center, radius, radius)

            # sombra suave debajo del logo
            shadow = QRadialGradient(QPointF(center.x(), center.y() + rect.height() * 0.05), radius * 0.95)
            shadow.setColorAt(0.0, QColor(0, 0, 0, 90))
            shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(shadow)
            painter.drawEllipse(
                QPointF(center.x(), center.y() + rect.height() * 0.05),
                radius * 0.95,
                radius * 0.95,
            )

        painter.setOpacity(0.5 if self._state == "offline" else 1.0)
        painter.drawPixmap(logo_rect.toRect(), self._logo)
        # La cara va sobre el logo, con la misma opacidad.
        face.paint_face(
            painter,
            logo_rect,
            self._expression,
            color,
            self._blink,
            look=self._look_direction(),
            level=self._level,
        )
        painter.setOpacity(1.0)

        self._paint_arcs(painter, rect, logo_rect, color)
        self._paint_status_dot(painter, rect, color)

    def _glow_alpha(self) -> float:
        if self._state == "idle":
            # Late suave y además se aviva con el nivel del micrófono: así se ve
            # que está escuchando aunque no haya dicho la palabra clave.
            return 46 + 26 * (0.5 + 0.5 * math.sin(self._phase * 0.75)) + min(45.0, self._level * 500)
        if self._state == "listening":
            return 110 + 55 * (0.5 + 0.5 * math.sin(self._phase * 2.2))
        if self._state in ("thinking", "working", "confirm"):
            return 80
        if self._state == "speaking":
            return 95 + 35 * (0.5 + 0.5 * math.sin(self._phase * 3.4))
        if self._state == "error":
            return 120
        return 0.0

    def _paint_arcs(self, painter: QPainter, rect: QRectF, logo_rect: QRectF, color: QColor) -> None:
        ring = logo_rect.adjusted(-2.5, -2.5, 2.5, 2.5)

        if self._state == "idle":
            # Latido lento + arco con el nivel del micrófono: se ve que escucha.
            breathe = 0.5 + 0.5 * math.sin(self._phase * 0.75)
            pen = QPen(QColor(color.red(), color.green(), color.blue(), int(70 + 60 * breathe)))
            pen.setWidthF(1.8)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring)
            if self._level > 0.006:
                level_pen = QPen(QColor(color.red(), color.green(), color.blue(), 210))
                level_pen.setWidthF(2.4)
                level_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(level_pen)
                span = int(min(1.0, self._level * 8.0) * 300 * 16)
                painter.drawArc(ring, 90 * 16, -span)
            return

        if self._state in ("thinking", "working"):
            pen = QPen(color)
            pen.setWidthF(3.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            start = int((-self._phase * 95) * 16) % (360 * 16)
            painter.drawArc(ring, start, 100 * 16)
            return

        if self._state == "listening":
            base = QPen(QColor(color.red(), color.green(), color.blue(), 120))
            base.setWidthF(1.6)
            painter.setPen(base)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring)
            if self._level > 0.004:
                level_pen = QPen(QColor(color.red(), color.green(), color.blue(), 235))
                level_pen.setWidthF(3.0)
                level_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(level_pen)
                span = int(min(1.0, self._level * 7.0) * 300 * 16)
                painter.drawArc(ring, 90 * 16, -span)
            return

        if self._state == "confirm":
            pen = QPen(color)
            pen.setWidthF(2.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring)
            return

        if self._state == "error":
            pen = QPen(color)
            pen.setWidthF(2.6)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring)

    def _paint_status_dot(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        diameter = max(9.0, rect.width() * 0.115)
        margin = diameter * 0.45
        dot = QRectF(
            rect.right() - diameter - margin + 1,
            rect.bottom() - diameter - margin + 1,
            diameter,
            diameter,
        )
        painter.setPen(QPen(QColor(9, 12, 17, 235), max(1.6, diameter * 0.22)))
        painter.setBrush(color)
        painter.drawEllipse(dot)

    # ---------------------------------------------------------------- provisorio

    def _paint_placeholder(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        center = rect.center()
        radius = rect.width() / 2 - 3

        halo = QRadialGradient(center, radius * 1.1)
        halo_color = QColor(color)
        halo_color.setAlpha(int(self._glow_alpha() * 0.8) if self._state != "offline" else 20)
        halo.setColorAt(0.0, halo_color)
        halo_color.setAlpha(0)
        halo.setColorAt(1.0, halo_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(center, radius * 1.1, radius * 1.1)

        disc = QRadialGradient(center, radius)
        disc.setColorAt(0.0, QColor(28, 36, 51, 242))
        disc.setColorAt(0.75, QColor(15, 19, 27, 242))
        disc.setColorAt(1.0, QColor(9, 12, 17, 242))
        painter.setBrush(disc)
        painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))

        inner = QRectF(
            center.x() - radius * 0.52,
            center.y() - radius * 0.52,
            radius * 1.04,
            radius * 1.04,
        )
        paint_mic_glyph(painter, inner, QColor(theme.TEXT))

        pen = QPen(QColor(color.red(), color.green(), color.blue(), 190))
        pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))

        self._paint_status_dot(painter, rect, color)

    # ---------------------------------------------------------------- ratón

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._moved = False
            self._press_pos = event.globalPosition().toPoint()
            self._window_start = self.pos()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging:
            return
        delta = event.globalPosition().toPoint() - self._press_pos
        if not self._moved and delta.manhattanLength() < 4:
            return
        self._moved = True
        self.move(self._window_start + delta)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self._moved:
                self._clamp_to_screen()
                self.drag_finished.emit(self.x(), self.y())
            else:
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: ANN001
        self.context_menu_requested.emit(event.globalPos())
        event.accept()

    def wheelEvent(self, event) -> None:  # noqa: ANN001
        # Ctrl + rueda cambia el tamaño del icono.
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            step = 8 if event.angleDelta().y() > 0 else -8
            new_size = max(72, min(200, self._size + step))
            center = self.frameGeometry().center()
            self._size = new_size
            self.setFixedSize(new_size, new_size)
            self.move(center.x() - new_size // 2, center.y() - new_size // 2)
            self._reload_logo()
            self._clamp_to_screen()
            self.drag_finished.emit(self.x(), self.y())
            event.accept()
            return
        super().wheelEvent(event)

    # ---------------------------------------------------------------- posición

    def place_initial(self, x: int, y: int) -> None:
        if x >= 0 and y >= 0:
            self.move(x, y)
            self._clamp_to_screen()
            return
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 24, area.bottom() - self.height() - 90)

    def _clamp_to_screen(self) -> None:
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        x = min(max(self.x(), area.left()), area.right() - self.width())
        y = min(max(self.y(), area.top()), area.bottom() - self.height())
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)
