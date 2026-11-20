"""Palabra de activación ("Miky") y confirmaciones por voz.

El nombre es un problema para el reconocimiento porque no es una palabra del
español: Whisper lo escribe como "Viky", "Biqui", "Miki", "Miggy", "Mi que"…
Por eso, además de una lista de variantes, se compara el primer token con
distancia de edición 1 ("viky" está a una letra de "miky").
"""

from __future__ import annotations

import re
import unicodedata

PREFIXES = (
    "hola",
    "che",
    "oye",
    "ey",
    "dale",
    "ok",
    "okey",
    "okay",
    "bueno",
    "escucha",
    "escuchá",
    "atende",
    "atendé",
)

# Whisper suele escribir el nombre de varias formas.
VARIANTS = {
    "miky": (
        "miky",
        "miki",
        "miqui",
        "micki",
        "mickey",
        "mikey",
        "mike",
        "mig",
        "miggy",
        "miggi",
        "migui",
        "viki",
        "viky",
        "viqui",
        "biki",
        "biqui",
        "niki",
        "bigui",
        "maiki",
        "mayki",
        "miqi",
    ),
    "tuka": ("tuka", "tuca"),
    "beto": ("beto", "veto"),
    "reaper": ("reaper", "riper", "reper"),
}

YES_WORDS = {
    "si",
    "sí",
    "dale",
    "confirmo",
    "confirma",
    "confirmalo",
    "ok",
    "okey",
    "oka",
    "de una",
    "hacelo",
    "hacela",
    "correcto",
    "va",
    "adelante",
    "listo",
    "si dale",
    "obvio",
    "vamos",
}

# Imperativos que también valen como "sí" cuando la respuesta es corta.
YES_IMPERATIVES = {
    "borrala",
    "borralo",
    "borra",
    "eliminala",
    "eliminalo",
    "elimina",
    "mandale",
    "metele",
    "dale",
    "hacelo",
    "hacela",
    "confirma",
    "confirmalo",
}

NO_WORDS = {
    "no",
    "nada",
    "cancela",
    "cancelalo",
    "cancelala",
    "para",
    "pará",
    "deja",
    "dejá",
    "mejor no",
    "olvidate",
    "olvidalo",
    "nooo",
    "negativo",
    "nunca",
}

# Respuestas que no son ni sí ni no: mejor volver a preguntar.
NEUTRAL = {
    "no se",
    "no estoy seguro",
    "quien sabe",
    "que",
    "como",
    "mande",
    "repeti",
}

_TOKEN = re.compile(r"[0-9A-Za-zÁÉÍÓÚÑÜáéíóúñü]+")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def variants_for(wake_word: str) -> tuple[str, ...]:
    key = normalize(wake_word)
    return VARIANTS.get(key, (key,))


def _distance(a: str, b: str) -> int:
    """Distancia de edición (Levenshtein) para palabras cortas."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def split_wake(text: str, wake_word: str) -> tuple[bool, str]:
    """Devuelve (activado, resto_de_la_frase).

    Acepta el nombre al principio, con o sin un prefijo coloquial ("che", "ok"),
    y tolera una letra de diferencia.
    """
    if not text:
        return False, ""

    tokens = list(_TOKEN.finditer(text))
    if not tokens:
        return False, ""

    variants = variants_for(wake_word)
    index = 0
    # Se saltea un saludo inicial ("hola", "che", "ok"…).
    if index < len(tokens) and normalize(tokens[index].group(0)) in PREFIXES:
        index += 1
    if index >= len(tokens):
        return False, ""

    candidate = normalize(tokens[index].group(0))
    if len(candidate) < 3:
        return False, ""

    matched = candidate in variants or any(
        _distance(candidate, variant) <= 1 for variant in variants
    )
    if not matched:
        return False, ""

    rest = text[tokens[index].end() :]
    return True, rest.strip(" ,.:;!?¡¿-–")


def parse_yes_no(text: str) -> bool | None:
    """Interpreta una respuesta de confirmación.

    Mira palabras sueltas, no solo la frase completa: «sí, dale», «dale, borrala»
    y «sí» valen igual. Un «no» en cualquier posición gana.
    """
    normalized = normalize(text)
    if not normalized:
        return None
    if normalized in NEUTRAL:
        return None

    tokens = normalized.split()
    if any(token in NO_WORDS for token in tokens) or normalized in NO_WORDS:
        return False
    if normalized in YES_WORDS:
        return True
    if any(token in YES_WORDS for token in tokens):
        return True
    # «Borrala», «eliminala», «hacelo»: valen si la respuesta es corta.
    if len(tokens) <= 3 and any(token in YES_IMPERATIVES for token in tokens):
        return True
    if tokens[0] == "si":
        return True
    return None
