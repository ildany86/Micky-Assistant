"""Corrección de la transcripción antes de interpretarla.

Whisper entiende bien el español general pero inventa las palabras que no
conoce: marcas de plugins, nombres de pistas, siglas. Acá se corrigen dos cosas:

1. Un diccionario explícito del usuario (`voice.corrections`): "eamoot=Eamut".
2. Coincidencia difusa contra el vocabulario: si una palabra (o dos, o tres
   juntas) se parece mucho a un término conocido, se reemplaza por el término.
   Así "e amut" / "eamoot" / "EAMOOT" terminan todas en "Eamut".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MIN_TERM_LEN = 3
MAX_SPAN_TOKENS = 3

_TOKEN = re.compile(r"[0-9A-Za-zÁÉÍÓÚÑÜáéíóúñü]+")


def _fold(text: str) -> str:
    """Minúsculas, sin acentos y sin separadores: para comparar."""
    decomposed = unicodedata.normalize("NFD", text or "")
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^0-9a-z]", "", without_marks.lower())


def _distance(a: str, b: str) -> int:
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


def _allowed_distance(length: int) -> int:
    if length >= 8:
        return 2
    if length >= 4:
        return 1
    return 0


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    term: str
    distance: int


def correct_text(text: str, terms: list[str] | tuple[str, ...], rules: list[str] | None = None) -> tuple[str, list[tuple[str, str]]]:
    """Devuelve (texto_corregido, cambios).

    `rules` son pares "malo=bueno" que se aplican tal cual antes de la difusa.
    """
    if not text:
        return text, []
    changes: list[tuple[str, str]] = []
    result = text

    for rule in rules or []:
        if "=" not in rule:
            continue
        wrong, _, right = rule.partition("=")
        wrong = wrong.strip()
        right = right.strip()
        if not wrong or not right:
            continue
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        if pattern.search(result):
            result = pattern.sub(right, result)
            changes.append((wrong, right))

    vocabulary = [term.strip() for term in terms if term and len(_fold(term)) >= MIN_TERM_LEN]
    if not vocabulary:
        return result, changes

    tokens = [(match.start(), match.end(), match.group(0)) for match in _TOKEN.finditer(result)]
    if not tokens:
        return result, changes

    folded_terms = [
        (_fold(term), term, [_fold(word) for word in term.split()] or [_fold(term)])
        for term in vocabulary
    ]
    candidates: list[Match] = []
    for index in range(len(tokens)):
        for span in range(1, MAX_SPAN_TOKENS + 1):
            if index + span > len(tokens):
                break
            piece_tokens = tokens[index : index + span]
            folded = _fold("".join(token[2] for token in piece_tokens))
            if len(folded) < MIN_TERM_LEN:
                continue
            best: Match | None = None
            for folded_term, term, words in folded_terms:
                if span == len(words):
                    # Comparación palabra por palabra: evita comerse palabras
                    # vecinas ("el monitorcorrect" no es "MonitorCorrect").
                    distance = 0
                    compatible = True
                    for position in range(span):
                        token_folded = _fold(piece_tokens[position][2])
                        word_folded = words[position]
                        allowed_word = _allowed_distance(len(token_folded))
                        gap = _distance(token_folded, word_folded)
                        if gap > allowed_word:
                            compatible = False
                            break
                        distance += gap
                    if not compatible:
                        continue
                elif folded == folded_term:
                    # Mismo texto con otros espacios: "monitor correct" y
                    # "monitorcorrect" valen igual.
                    distance = 0
                else:
                    continue
                # Que no sea "parecido" a cualquier cosa: proporción razonable.
                if distance / max(1, len(folded_term)) > 0.34:
                    continue
                if best is None or distance < best.distance:
                    best = Match(
                        piece_tokens[0][0], piece_tokens[-1][1], term, distance
                    )
            if best is not None:
                candidates.append(best)

    # Se aplican de mayor a menor longitud y sin solaparse.
    candidates.sort(key=lambda item: (-(item.end - item.start), item.distance))
    used: list[tuple[int, int]] = []
    accepted: list[Match] = []
    for candidate in candidates:
        if any(candidate.start < end and candidate.end > start for start, end in used):
            continue
        used.append((candidate.start, candidate.end))
        accepted.append(candidate)

    if not accepted:
        return result, changes

    accepted.sort(key=lambda item: item.start)
    pieces: list[str] = []
    cursor = 0
    for match in accepted:
        original = result[match.start : match.end]
        pieces.append(result[cursor : match.start])
        pieces.append(match.term)
        if original != match.term:
            changes.append((original, match.term))
        cursor = match.end
    pieces.append(result[cursor:])
    return "".join(pieces), changes
