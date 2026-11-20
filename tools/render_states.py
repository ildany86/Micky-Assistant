"""Renderiza el icono flotante en todos sus estados, sin mostrar ventanas.

Sirve para revisar el lenguaje visual (y para la documentación) sin molestar a
nadie: usa la plataforma "offscreen" de Qt.

Uso: python tools/render_states.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from miky.ui.icon import FloatingIcon  # noqa: E402

STATES = [
    ("offline", "Sin REAPER"),
    ("idle", "Escuchando"),
    ("listening", "Te escucho"),
    ("thinking", "Pensando"),
    ("working", "Ejecutando"),
    ("speaking", "Hablando"),
    ("confirm", "Confirmá"),
    ("error", "Error"),
]

OUT = ROOT / "docs" / "img"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)

    icon = FloatingIcon(size=104)
    icon.set_level(0.35)
    tiles: list[tuple[str, Image.Image]] = []
    for state, label in STATES:
        icon.set_state(state)
        icon._phase = 1.1  # fase fija para que el render sea reproducible
        icon.snap_face()
        pixmap = icon.grab()
        path = OUT / f"estado-{state}.png"
        pixmap.save(str(path))
        tiles.append((label, Image.open(path).convert("RGBA")))

    big = FloatingIcon(size=160)
    big.set_state("listening")
    big._phase = 1.1
    big.grab().save(str(OUT / "icono-160.png"))

    # Tira comparativa sobre fondo oscuro
    padding = 18
    tile = 104
    width = padding + len(tiles) * (tile + padding)
    height = tile + 64
    strip = Image.new("RGBA", (width, height), (11, 14, 19, 255))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(strip)
    for index, (label, image) in enumerate(tiles):
        x = padding + index * (tile + padding)
        strip.alpha_composite(image, (x, 16))
        draw.text((x + 4, tile + 44), label, fill=(150, 168, 190, 255))
    strip.save(OUT / "estados.png")
    print(f"listo: {OUT / 'estados.png'}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
