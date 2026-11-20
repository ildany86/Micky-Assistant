"""Ajustes de pronunciación para la voz en español.

La voz es rioplatense: lee "REAPER" como si fuera una palabra española
("re-a-per"). Escribiéndolo "Ríper" suena como se dice en inglés.
"""

from __future__ import annotations

import re

RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\breaper\b", re.IGNORECASE), "Ríper"),
    (re.compile(r"\bMiky\b", re.IGNORECASE), "Miki"),
)


def apply(text: str) -> str:
    """Devuelve el texto listo para el sintetizador."""
    if not text:
        return ""
    for pattern, replacement in RULES:
        text = pattern.sub(replacement, text)
    return text
