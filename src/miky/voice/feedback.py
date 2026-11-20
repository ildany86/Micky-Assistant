"""Avisos sonoros cortos: confirman que Miky te escuchó sin mirar la pantalla.

Se generan en memoria (no hay archivos ni dependencias) y se reproducen por el
dispositivo de salida predeterminado. Si Windows no deja, no pasa nada.
"""

from __future__ import annotations

import io
import math
import struct
import sys
import wave

RATE = 22050
_CACHE: dict[str, bytes] = {}


def _tone(frequency: float, ms: int, volume: float = 0.22, fade_ms: int = 6) -> bytes:
    samples = int(RATE * ms / 1000)
    fade = max(1, int(RATE * fade_ms / 1000))
    frames = bytearray()
    for index in range(samples):
        envelope = min(1.0, index / fade, (samples - index) / fade)
        value = volume * envelope * math.sin(2 * math.pi * frequency * index / RATE)
        frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767))
    return bytes(frames)


def _silence(ms: int) -> bytes:
    return b"\x00\x00" * int(RATE * ms / 1000)


def _wav(frames: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(frames)
    return buffer.getvalue()


def _build(kind: str) -> bytes:
    if kind == "error":
        return _wav(_tone(320, 130, volume=0.20) + _silence(40) + _tone(240, 130, volume=0.18))
    if kind == "ok":
        # Dos notas que suben, suaves: "quedó hecho".
        return _wav(_tone(520, 80, volume=0.18) + _silence(30) + _tone(780, 110, volume=0.18))
    if kind == "confirm":
        return _wav(_tone(660, 70) + _silence(30) + _tone(990, 90))
    # wake (por defecto): dos notas cortas y suaves
    return _wav(_tone(880, 60) + _silence(25) + _tone(1320, 70))


def chime(kind: str = "wake") -> None:
    """Suena un aviso corto. Nunca lanza excepción ni bloquea."""
    if sys.platform != "win32":
        return
    try:
        import winsound
    except ImportError:
        return
    data = _CACHE.get(kind)
    if data is None:
        try:
            data = _build(kind)
        except Exception:  # noqa: BLE001
            return
        _CACHE[kind] = data
    try:
        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:  # noqa: BLE001
        pass
