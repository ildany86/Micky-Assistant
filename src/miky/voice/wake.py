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
        "vicky",
        "vicki",
        "viqui",
        "biki",
        "biqui",
        "bicky",
        "niki",
        "bigui",
        "maiki",
        "mayki",
        "miqi",
        "miki",
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

# Cuando el nombre se parte en dos ("mi que"), solo se acepta si lo que sigue
# parece una orden. Si sigue un artículo o preposición, es una frase cualquiera.
_NON_COMMAND_STARTS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "que", "y", "a", "al", "en", "con", "por", "para",
    "mi", "tu", "su", "es", "esta", "este", "eso", "lo", "se", "te", "me",
    "muy", "más", "mas", "no", "sí", "si",
}


def _starts_like_command(rest: str) -> bool:
    tokens = _TOKEN.findall(rest or "")
    if not tokens:
        return False
    return normalize(tokens[0]) not in _NON_COMMAND_STARTS


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


def _phonetic(word: str) -> str:
    """Reduce la palabra a cómo suena, para que "vicky" y "miky" se parezcan.

    Whisper escribe lo que oye: v/b, c/qu/k, y/i son la misma cosa para el
    oído. Normalizando antes de comparar, una sola lista de variantes cubre
    decenas de transcripciones posibles.
    """
    word = normalize(word)
    word = word.replace("qu", "k").replace("ck", "k").replace("cc", "k")
    word = word.replace("v", "b")
    word = word.replace("z", "s")
    word = word.replace("y", "i")
    word = re.sub(r"c(?=[ei])", "s", word)
    word = re.sub(r"(.)\1+", r"\1", word)  # "mikki" -> "miki"
    return word


def _matches(candidate: str, variants: tuple[str, ...]) -> bool:
    if not candidate:
        return False
    folded = normalize(candidate)
    if folded in variants:
        return True
    # Forma fonética: "biqui" y "vicky" terminan siendo "biki"/"biki".
    sounds = _phonetic(candidate)
    for variant in variants:
        if sounds == _phonetic(variant):
            return True
        if _distance(sounds, _phonetic(variant)) <= 1:
            return True
    return any(_distance(folded, variant) <= 1 for variant in variants)


def split_wake(text: str, wake_word: str) -> tuple[bool, str]:
    """Devuelve (activado, resto_de_la_frase).

    Acepta el nombre al principio, con o sin un prefijo coloquial ("che", "ok"),
    y tolera variantes de pronunciación ("Vicky", "Biqui", "Migui").
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

    # Primero una palabra; si no, dos juntas ("mi que", "mig ui").
    for span in (1, 2):
        if index + span > len(tokens):
            continue
        candidate = "".join(tokens[index + offset].group(0) for offset in range(span))
        if len(normalize(candidate)) < 3:
            continue
        if not _matches(candidate, variants):
            continue
        rest = text[tokens[index + span - 1].end() :]
        rest = rest.strip(" ,.:;!?¡¿-–")
        # "mi que el volumen" no es una orden: se descarta.
        if span == 2 and rest and not _starts_like_command(rest):
            continue
        return True, rest
    return False, ""


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
