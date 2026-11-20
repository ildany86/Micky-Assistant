"""Fichas de conocimiento técnico para los consejos de Miky.

El modelo sabe de audio en general, pero en un modelo chico los números se
inventan. Estas fichas son texto curado y verificable: cuando el pedido es una
consulta de criterio, se inyectan las más relevantes en el contexto y la IA
tiene datos concretos para responder (frecuencias, ratios, niveles).

Formato: cada ficha tiene id, título, etiquetas (para buscar) y cuerpo en
viñetas cortas. Todo el contenido es propio, resumido de fuentes públicas
(manual de REAPER, documentación de fabricantes, bibliografía de mezcla).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    id: str
    title: str
    tags: tuple[str, ...]
    body: tuple[str, ...]


CARDS: tuple[Card, ...] = (
    Card(
        "eq",
        "Ecualización",
        ("eq", "ecualizar", "ecualizacion", "frecuencia", "brillo", "opaco", "barro",
         "corte", "realce", "agudo", "grave", "filtro"),
        (
            "20 Hz–20 kHz: por debajo de 40 Hz casi todo es ruido o aire; filtrá con high-pass.",
            "80–120 Hz: peso del bombo y del bajo. 200–400 Hz: «caja/barro», el rango que más se recorta.",
            "500 Hz–1 kHz: cuerpo y «nasalidad». 2–5 kHz: presencia y ataque (donde el oído es más sensible).",
            "6–10 kHz: sibilancias y de-esser. 10–16 kHz: «aire»; subilo con shelf suave.",
            "High-pass a 70–100 Hz en voz, guitarra y overheads; en bombo/bajo a 20–30 Hz.",
            "Regla práctica: cortá antes de realzar. Un realce de 3 dB con un corte previo de 2 dB suena más limpio.",
            "Q: 0,5–1 para tono general; 3–8 para corregir un problema puntual (una resonancia).",
            "Bell para corregir, shelf para dar color, filtro para limpiar. Menos de 30 % de las pistas necesitan EQ.",
        ),
    ),
    Card(
        "dinamica",
        "Compresión y dinámica",
        ("compresor", "compresion", "dinamica", "ratio", "ataque", "release", "threshold",
         "limitador", "puerta", "gate", "pegar", "aplastar"),
        (
            "Threshold: punto donde empieza a comprimir. Ratio 2:1–4:1 para mezcla; 6:1–10:1 para control duro.",
            "Attack 10–30 ms deja pasar el transiente (pegada); 1–5 ms lo frena (control).",
            "Release 100–300 ms en voz y bajo; 20–50 ms en bombo (que respire con el tempo).",
            "Reducción típica: 2–4 dB en pistas, 1–3 dB en el bus de mezcla. Si el medidor está siempre pasado, bajá el threshold o el ratio antes que subir el make-up.",
            "Make-up: compensá la reducción para que el nivel percibido no cambie; compará A/B con el bypass al mismo volumen.",
            "Knee suave para voz y buses; duro para control de picos.",
            "Compresión en paralelo: copia muy comprimida debajo de la original; suma pegada sin perder transientes.",
            "Sidechain con filtro pasa-altos en el detector: evita que el bombo dispare la compresión del bajo.",
            "Si comprimís la suma, no comprimas también cada pista: se acumula y suena aplastado.",
        ),
    ),
    Card(
        "niveles",
        "Ganancia y niveles",
        (
            "ganancia", "nivel", "db", "dbfs", "lufs", "clipping", "master", "volumen",
            "headroom", "mezcla",
        ),
        (
            "Grabá a 24 bits, 48 kHz. Picos de entrada alrededor de -12 dBFS: nunca toques el 0.",
            "Mezcla: promedio -18 dBFS, picos -6 dBFS. Eso deja headroom para el master.",
            "Master final: pico máximo -1 dBTP y loudness -14 LUFS para streaming; -9 a -12 para club/electrónica.",
            "Monitoreá a un nivel constante (~80 dB SPL) para que las decisiones no dependan del volumen.",
            "El «loudness war» ya no: si comprimís más de 3 dB en el master para ganar volumen, perdés transientes.",
        ),
    ),
    Card(
        "voz",
        "Voz",
        ("voz", "vocal", "cantante", "vocalista", "coro", "armonia"),
        (
            "High-pass 80–100 Hz; corte de 250–400 Hz si suena «nasal» o embarrada.",
            "De-esser en 5–8 kHz si las eses silban; mejor un de-esser dedicado que un EQ estático.",
            "Compresión 3:1 con 3–6 dB de reducción y ataque 15 ms: mantiene naturalidad.",
            "Presencia: realce suave de 1–2 dB en 3 kHz. Aire: shelf de 1–2 dB desde 10 kHz.",
            "Reverb: placa corta (1,2–1,8 s) con pre-delay 20–30 ms y EQ cortando por debajo de 200 Hz en el envío.",
            "Doblá la voz principal en vez de comprimirla más: dos tomas suenan más grandes que una aplastada.",
        ),
    ),
    Card(
        "bateria",
        "Batería",
        ("bateria", "bombo", "caja", "redo", "snare", "kick", "overheads", "platos", "drums"),
        (
            "Bombo: peso en 50–80 Hz, corte en 300–400 Hz, ataque en 3–5 kHz.",
            "Caja: cuerpo 180–250 Hz, «crac» 4–6 kHz; cuidado con el 400–600 Hz (caja de cartón).",
            "Overheads: high-pass 200–300 Hz y paneo amplio; definen la imagen de la batería.",
            "Compresión de bombo: ratio 4:1, ataque 20–30 ms, release 50–80 ms, 3–5 dB de reducción.",
            "Paralela para pegada: comprimí fuerte (10:1) y mezclá al 20–30 %.",
            "Alineá fases entre bombo y overheads antes de ecualizar: muchos problemas de «flojo» son de fase.",
        ),
    ),
    Card(
        "espacio",
        "Reverb, delay y espacio",
        ("reverb", "delay", "eco", "espacio", "ambiente", "profundidad", "sala", "plate"),
        (
            "Pre-delay 20–40 ms separa la fuente de la cola y da sensación de sala más grande.",
            "Envíos en paralelo (send), no reverb insertado: permite ajustar la cantidad por pista.",
            "Cortá graves en el envío (high-pass 200–400 Hz): evita que el reverb enturbie la mezcla.",
            "Delay: 1/8 o 1/4 con el tempo, con filtro y realimentación baja (20–30 %).",
            "Un solo reverb para el «pegamento» y otro distinto para el protagonista evita el barro.",
        ),
    ),
    Card(
        "grabacion",
        "Grabación y sala",
        ("grabar", "grabacion", "microfono", "mic", "ruido", "latencia", "toma", "monitoreo"),
        (
            "Cuando dudes, grabá más limpio: es más fácil ensuciar que limpiar.",
            "Picos de entrada en -12 dBFS; si ves rojo, bajá la ganancia del pre.",
            "Latencia total por debajo de 10 ms para tocar cómodo; monitoreo directo de la placa si hay dudas.",
            "Ruido: alejá la fuente de la computadora y apagá luces dimerizables; un gate no arregla un mal sitio.",
            "Tres tomas buenas valen más que diez regulares: comping después, no durante.",
        ),
    ),
    Card(
        "mezcla",
        "Método de mezcla",
        (
            "mezclar", "mezcla", "balance", "orden", "proceso", "metodo", "referencia",
            "mezclador", "bus",
        ),
        (
            "Orden: balance de faders en mono → paneo → EQ correctivo → dinámica → efectos → automatización.",
            "Empezá por la pista más importante (voz o bombo) y construí alrededor; no mezcles todo a la vez.",
            "Usá referencias comerciales del mismo género al mismo volumen percibido.",
            "Buses: batería, bajos, guitarras, voces. Procesá el bus cuando la suma lo necesite.",
            "Si todo suena importante, nada lo es: dejá un elemento protagonista por rango.",
            "Descansá 10 minutos cada hora: el oído se adapta y las decisiones se tuercen.",
        ),
    ),
)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_marks.lower()).strip()


def score_card(card: Card, normalized: str) -> int:
    score = 0
    words = set(normalized.split())
    for tag in card.tags:
        key = _fold(tag)
        if not key:
            continue
        if len(key) <= 3:
            if key in words:
                score += 2
        elif key in normalized:
            score += 2
        else:
            # Raíz de la palabra: "ecualizar" también encuentra "ecualizo".
            stem = key[:5]
            if stem in normalized:
                score += 2
    title = _fold(card.title)
    if title and (title in normalized or title[:5] in normalized):
        score += 3
    for line in card.body:
        for word in _fold(line).split():
            if len(word) >= 5 and word in normalized:
                score += 1
                break
    return score


def relevant(text: str, limit: int = 2) -> list[Card]:
    """Fichas que mejor responden a la consulta (vacío si no hay match)."""
    normalized = _fold(text)
    if not normalized:
        return []
    scored = [(score_card(card, normalized), card) for card in CARDS]
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: -pair[0])
    return [card for _score, card in scored[:limit]]


def as_context(cards: list[Card]) -> list[dict[str, object]]:
    return [{"tema": card.title, "datos": list(card.body)} for card in cards]


def is_advice_request(text: str) -> bool:
    """¿Parece una consulta de criterio y no una orden?"""
    normalized = _fold(text)
    if not normalized:
        return False
    if "?" in (text or ""):
        return True
    starts = ("que ", "como ", "por que", "para que", "me conviene", "esta bien",
              "conviene", "deberia", "recomenda", "aconseja", "sirve")
    if normalized.startswith(starts):
        return True
    return any(word in normalized for word in ("suena", "consejo", "recomendas", "opinion", "mejorar"))
