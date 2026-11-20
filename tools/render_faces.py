"""Vista grande de las expresiones de Miky (para revisar el dibujo)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw  # noqa: E402
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
SIZE = 180
COLS = 4


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    icon = FloatingIcon(size=SIZE)
    icon.set_level(0.3)
    tiles = []
    for state, label in STATES:
        icon.set_state(state)
        icon._phase = 1.1
        icon.snap_face()
        path = OUT / f"cara-{state}.png"
        icon.grab().save(str(path))
        tiles.append((label, Image.open(path).convert("RGBA")))

    rows = (len(tiles) + COLS - 1) // COLS
    pad = 16
    width = pad + COLS * (SIZE + pad)
    height = pad + rows * (SIZE + 34)
    strip = Image.new("RGBA", (width, height), (11, 14, 19, 255))
    draw = ImageDraw.Draw(strip)
    for index, (label, image) in enumerate(tiles):
        col = index % COLS
        row = index // COLS
        x = pad + col * (SIZE + pad)
        y = pad + row * (SIZE + 34)
        strip.alpha_composite(image, (x, y))
        draw.text((x + 6, y + SIZE + 8), label, fill=(160, 178, 200, 255))
    strip.save(OUT / "caras.png")
    print(f"listo: {OUT / 'caras.png'}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
