"""Genera el material visual del repositorio: banner y GIF animado.

Uso:
    python tools/make_media.py

Salida:
    docs/img/hero.png         banner 1200x420 para el README
    docs/img/icono.gif        el ícono recorriendo todos sus estados
    docs/img/icono-estados.png  tira estática (por si el GIF no carga)

Todo se dibuja con Qt (offscreen) y Pillow; no hay dependencias nuevas.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from miky.ui.icon import FloatingIcon  # noqa: E402

IMG_DIR = ROOT / "docs" / "img"

BG = (11, 14, 19)
CARD = (16, 21, 29)
TEXT = (232, 236, 243)
MUTED = (148, 161, 178)
ACCENT = (53, 194, 240)

# Estados y cuántos cuadros queda mostrando cada uno.
SEQUENCE = [
    ("idle", 8),
    ("listening", 10),
    ("thinking", 10),
    ("working", 10),
    ("speaking", 10),
    ("confirm", 10),
    ("error", 10),
    ("idle", 8),
]

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
]
FONT_REGULAR = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in paths:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _radial_background(size: tuple[int, int], center: tuple[float, float], color: tuple[int, int, int], strength: float = 0.5) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, BG)
    pixels = image.load()
    radius = max(width, height) * 0.75
    for y in range(height):
        for x in range(width):
            dx = (x - center[0]) / radius
            dy = (y - center[1]) / radius
            falloff = max(0.0, 1.0 - (dx * dx + dy * dy) ** 0.5)
            factor = (falloff ** 2) * strength
            pixels[x, y] = (
                int(BG[0] + (color[0] - BG[0]) * factor),
                int(BG[1] + (color[1] - BG[1]) * factor),
                int(BG[2] + (color[2] - BG[2]) * factor),
            )
    return image


def render_frames(size: int = 220, every: int = 3) -> list[Image.Image]:
    app = QApplication.instance() or QApplication([])
    icon = FloatingIcon(size=size)
    icon.show()
    frames: list[Image.Image] = []
    work = Path(tempfile.mkdtemp(prefix="miky_gif_"))
    counter = 0
    for state, ticks in SEQUENCE:
        icon.set_state(state)
        for tick in range(ticks + 6):
            icon._phase = (icon._phase + 0.07) % 6.283
            icon._update_face()
            if tick >= 6 and tick % every == 0:
                path = work / f"frame_{counter:03d}.png"
                counter += 1
                icon.grab().save(str(path))
                frames.append(Image.open(path).convert("RGBA"))
    app.processEvents()
    return frames


def compose_card(frame: Image.Image, size: int, padding: int = 34) -> Image.Image:
    canvas_size = size + padding * 2
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (0, 0, canvas_size - 1, canvas_size - 1),
        radius=canvas_size // 2,
        fill=(*CARD, 255),
        outline=(38, 48, 62, 255),
        width=2,
    )
    canvas.alpha_composite(frame, (padding, padding))
    return canvas


def build_gif(target: Path, size: int = 190, frame_ms: int = 110) -> None:
    frames = [compose_card(frame, size) for frame in render_frames(size)]
    if not frames:
        raise SystemExit("no se pudieron renderizar cuadros")
    # Fondo opaco para que el GIF se vea igual en cualquier tema.
    flat = []
    for frame in frames:
        canvas = Image.new("RGB", frame.size, BG)
        canvas.paste(frame, (0, 0), frame)
        flat.append(canvas)
    flat[0].save(
        target,
        save_all=True,
        append_images=flat[1:],
        duration=frame_ms,
        loop=0,
        optimize=True,
        disposal=2,
    )


def build_strip(target: Path, size: int = 128) -> None:
    """Tira estática con los estados principales, por si el GIF no carga."""
    states = ["idle", "listening", "thinking", "working", "speaking", "confirm", "error", "offline"]
    labels = ["Inactivo", "Escuchando", "Pensando", "Ejecutando", "Hablando", "Confirmar", "Error", "Sin REAPER"]
    app = QApplication.instance() or QApplication([])
    icon = FloatingIcon(size=size)
    icon.show()
    tiles: list[Image.Image] = []
    work = Path(tempfile.mkdtemp(prefix="miky_strip_"))
    for state in states:
        icon.set_state(state)
        for _ in range(10):
            icon._phase = (icon._phase + 0.07) % 6.283
            icon._update_face()
        path = work / f"{state}.png"
        icon.grab().save(str(path))
        tiles.append(Image.open(path).convert("RGBA"))
    app.processEvents()

    gap = 22
    label_h = 34
    width = len(tiles) * (size + gap) + gap
    height = size + label_h + gap * 2
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    small = _font(FONT_REGULAR, 16)
    for index, (tile, label) in enumerate(zip(tiles, labels)):
        x = gap + index * (size + gap)
        canvas.paste(tile, (x, gap), tile)
        text_width = draw.textlength(label, font=small)
        draw.text((x + (size - text_width) / 2, gap + size + 8), label, font=small, fill=MUTED)
    canvas.save(target)


def build_hero(target: Path, width: int = 1200, height: int = 420) -> None:
    # Halo suave: gradiente radial, sin anillos (evita el efecto "mancha").
    canvas = _radial_background((width, height), (width * 0.16, height * 0.5), (26, 88, 120), strength=1.0)
    draw = ImageDraw.Draw(canvas)

    logo_path = ROOT / "src" / "miky" / "data" / "assets" / "logo.png"
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        logo.thumbnail((250, 250), Image.LANCZOS)
        cx, cy = 245, height // 2
        canvas.paste(logo, (cx - logo.width // 2, cy - logo.height // 2), logo)

    title_font = _font(FONT_CANDIDATES, 86)
    tag_font = _font(FONT_CANDIDATES, 32)
    sub_font = _font(FONT_REGULAR, 23)
    chip_font = _font(FONT_CANDIDATES, 15)

    x = 420
    draw.text((x, 92), "Miky", font=title_font, fill=TEXT)
    draw.text((x, 212), "Asistente de voz para REAPER", font=tag_font, fill=ACCENT)
    draw.text((x, 262), "Escucha y habla en tu PC. Razona en la nube.", font=sub_font, fill=MUTED)
    chip = "BETA 0.1"
    chip_width = draw.textlength(chip, font=chip_font) + 24
    draw.rounded_rectangle(
        (x, 308, x + chip_width, 340),
        radius=16,
        outline=(*ACCENT, 255),
        width=2,
    )
    draw.text((x + 12, 313), chip, font=chip_font, fill=ACCENT)
    canvas.save(target)


def main() -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    print("banner…")
    build_hero(IMG_DIR / "hero.png")
    print("tira de estados…")
    build_strip(IMG_DIR / "icono-estados.png")
    print("GIF animado…")
    build_gif(IMG_DIR / "icono.gif")
    for name in ("hero.png", "icono.gif", "icono-estados.png"):
        path = IMG_DIR / name
        print(f"  {name}: {path.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
