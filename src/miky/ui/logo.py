"""Logo de Miky: usa el arte del usuario o dibuja un ícono provisorio."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

from .. import paths

# El @2x primero: se escala para abajo y queda nítido en pantallas HiDPI.
LOGO_FILENAMES = ("logo@2x.png", "logo.png", "logo.webp", "logo.jpg", "logo.jpeg", "logo.svg")


def resolve_logo(configured: str = "") -> Path | None:
    """Busca el logo en la ruta configurada o en data/assets."""
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_dir():
            for name in LOGO_FILENAMES:
                inner = candidate / name
                if inner.exists():
                    return inner
        elif candidate.exists():
            return candidate
    for folder in (paths.assets_dir(), paths.appdata_root() / "assets"):
        if not folder.exists():
            continue
        for name in LOGO_FILENAMES:
            candidate = folder / name
            if candidate.exists():
                return candidate
    return None


def load_logo_pixmap(configured: str = "", size: int = 256) -> QPixmap | None:
    path = resolve_logo(configured)
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def paint_mic_glyph(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Micrófono minimalista para cuando todavía no hay logo."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    cx = rect.center().x()
    cy = rect.center().y()
    width = rect.width()
    height = rect.height()

    body_width = width * 0.26
    body_height = height * 0.40
    body = QRectF(cx - body_width / 2, cy - body_height * 0.62, body_width, body_height)

    path = QPainterPath()
    radius = body_width / 2
    path.addRoundedRect(body, radius, radius)

    pen = QPen(color, max(1.6, width * 0.035))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)

    arc_rect = QRectF(cx - width * 0.19, cy - height * 0.10, width * 0.38, height * 0.34)
    painter.drawArc(arc_rect, 180 * 16, 180 * 16)
    painter.drawLine(QPointF(cx, arc_rect.bottom()), QPointF(cx, arc_rect.bottom() + height * 0.10))
    painter.drawLine(
        QPointF(cx - width * 0.10, arc_rect.bottom() + height * 0.10),
        QPointF(cx + width * 0.10, arc_rect.bottom() + height * 0.10),
    )
    painter.restore()
