"""Prepara el logo de Miky para la interfaz flotante.

El arte original (Micky-clear.png) ya viene con fondo transparente: es el anillo
con el micrófono. Acá solo se recorta al contenido, se centra en un cuadrado y
se exporta en los tamaños que usa la app.

Entrada:  Micky-clear.png
Salida:   src/miky/data/assets/logo.png      (512x512)
          src/miky/data/assets/logo@2x.png   (1024x1024)
          src/miky/data/assets/logo.ico      (para el acceso directo / instalador)
          src/miky/data/assets/preview.png   (control visual sobre claro y oscuro)

Uso: python tools/prepare_logo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Micky-clear.png"
ASSETS = ROOT / "src" / "miky" / "data" / "assets"
REFERENCE = ROOT / "assets-src"

ALPHA_THRESHOLD = 8
PADDING = 0.012


def content_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    alpha = np.asarray(image.getchannel("A"))
    ys, xs = np.nonzero(alpha > ALPHA_THRESHOLD)
    if xs.size == 0:
        return (0, 0, image.width, image.height)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def normalize(image: Image.Image, size: int) -> Image.Image:
    """Recorta al contenido, lo centra en un cuadrado y lo escala."""
    left, top, right, bottom = content_bbox(image)
    cx = (left + right) / 2
    cy = (top + bottom) / 2
    half = max(right - left, bottom - top) / 2
    half *= 1 + PADDING

    box = (cx - half, cy - half, cx + half, cy + half)
    # Si la caja se sale de la imagen, se rellena con transparencia.
    canvas = Image.new("RGBA", (int(half * 2) + 2, int(half * 2) + 2), (0, 0, 0, 0))
    offset = (int(round(half - cx)), int(round(half - cy)))
    canvas.paste(image, offset)
    return canvas.resize((size, size), Image.LANCZOS)


def build_preview(logo: Image.Image) -> Image.Image:
    """Muestra el logo en los tamaños reales sobre fondo oscuro y claro."""
    width, height = 900, 300
    canvas = Image.new("RGBA", (width, height), (11, 14, 19, 255))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([450, 0, width, height], fill=(238, 241, 245, 255))
    draw.text((24, 12), "sobre fondo oscuro (escritorio tipico)", fill=(150, 168, 190, 255))
    draw.text((474, 12), "sobre fondo claro", fill=(70, 82, 98, 255))

    sizes = [(96, 60), (128, 60), (180, 60)]
    x = 30
    for size, y in sizes:
        canvas.alpha_composite(logo.resize((size, size), Image.LANCZOS), (x, y))
        x += size + 26
    x = 480
    for size, y in sizes:
        canvas.alpha_composite(logo.resize((size, size), Image.LANCZOS), (x, y))
        x += size + 26
    return canvas


def main() -> int:
    if not SOURCE.exists():
        print(f"No encontré {SOURCE}", file=sys.stderr)
        return 1

    ASSETS.mkdir(parents=True, exist_ok=True)
    REFERENCE.mkdir(parents=True, exist_ok=True)

    original = Image.open(SOURCE).convert("RGBA")
    bbox = content_bbox(original)
    print(f"original {original.width}x{original.height} · contenido {bbox}")

    logo = normalize(original, 512)
    logo.save(ASSETS / "logo.png", optimize=True)
    normalize(original, 1024).save(ASSETS / "logo@2x.png", optimize=True)

    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    logo.save(ASSETS / "logo.ico", sizes=ico_sizes)

    build_preview(logo).save(ASSETS / "preview.png")
    original.save(REFERENCE / "logo-original.png")

    for name in ("logo.png", "logo@2x.png", "logo.ico", "preview.png"):
        path = ASSETS / name
        print(f"{name}: {path.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
