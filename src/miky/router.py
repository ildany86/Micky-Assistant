"""Comandos directos: los pedidos más comunes se ejecutan sin consultar a la IA.

Ahorra cuota, baja la latencia a ~40 ms y hace que el asistente siga sirviendo
si se cae internet. Solo se activa cuando la frase entera coincide con un
patrón conocido; cualquier otra cosa va a la IA.

Detalle importante: la comparación se hace sobre el texto normalizado (sin
acentos, en minúsculas), pero los nombres que se capturan se recuperan del
texto ORIGINAL. Así «creá una pista llamada Batería» crea "Batería" y no
"bateria".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

MAX_CHARS = 90
ARTICLES = ("la ", "el ", "los ", "las ", "un ", "una ", "de ", "del ", "al ")
NAME_PREFIXES = re.compile(r"^(que se llame|llamada|llamado|de|para)\s+", re.IGNORECASE)
NAME_VERBS = re.compile(
    r"^(nombrala|nombra|llamala|llamála|llama|ponele|ponle|que se llame|de nombre|de)\s+",
    re.IGNORECASE,
)

# Si la frase tiene más de una orden, el router no adivina: va a la IA, que sabe
# encadenar varios pasos. Antes, "creá una pista, nombrala batería y activá la
# grabación" terminaba creando una pista llamada "batería y activá la grabación".
SECOND_CLAUSE_MARKERS = (
    " y ",
    " e ",
    " despues ",
    " luego ",
    " tambien ",
    " ademas ",
    " y que ",
)

# Cuando el pedido apunta a varias pistas ("las dos pistas", "todas"), el router
# no debe agarrar una sola: lo resuelve la IA con varios pasos.
MULTI_TARGET_MARKERS = (
    " pistas ",
    " todas las ",
    " todos los ",
    " las dos ",
    " los dos ",
    " ambas ",
    " ambos ",
    " cada pista ",
    " las tres ",
)


# ---------------------------------------------------------------- texto


def normalize_with_index(text: str) -> tuple[str, list[int]]:
    """Normaliza y devuelve el mapa de cada carácter a su posición original."""
    out: list[str] = []
    index_map: list[int] = []
    for position, char in enumerate(text or ""):
        lowered = char.lower()
        if unicodedata.category(lowered).startswith("P"):
            # Un separador decimal entre dígitos se conserva ("1,5" -> "1.5"),
            # si no, "1.5 dB" se convierte en "1 5 dB" y se pierde el número.
            if (
                lowered in ".,"
                and 0 < position < len(text) - 1
                and text[position - 1].isdigit()
                and text[position + 1].isdigit()
            ):
                out.append(".")
                index_map.append(position)
                continue
            lowered = " "
        decomposed = unicodedata.normalize("NFD", lowered)
        for piece in decomposed:
            if unicodedata.category(piece) == "Mn":
                continue
            if piece == " ":
                if out and out[-1] == " ":
                    continue
            out.append(piece)
            index_map.append(position)
    # recorta espacios de los extremos manteniendo el mapa alineado
    while out and out[0] == " ":
        out.pop(0)
        index_map.pop(0)
    while out and out[-1] == " ":
        out.pop()
        index_map.pop()
    return "".join(out), index_map


def normalize(text: str) -> str:
    return normalize_with_index(text)[0]


def strip_article(name: str) -> str:
    name = name.strip()
    for article in ARTICLES:
        if name.lower().startswith(article):
            return name[len(article) :].strip()
    return name


# ---------------------------------------------------------------- números

_NUMBER_WORDS = {
    "cero": 0, "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintisiete": 27,
    "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "medio": 0.5,
}


def parse_number(text: str) -> float | None:
    """Convierte números escritos con palabras o con coma decimal."""
    if text is None:
        return None
    raw = str(text).strip()
    negative = False
    # El signo se mira ANTES de normalizar: normalize() borra los guiones.
    if raw.startswith("-"):
        negative = True
        raw = raw[1:].strip()

    cleaned = normalize(raw).strip()
    if not cleaned:
        return None

    if cleaned.startswith("menos "):
        negative = True
        cleaned = cleaned[len("menos ") :].strip()

    cleaned = cleaned.replace("coma", ".")

    match = re.fullmatch(r"\d+(?:\.\d+)?", cleaned)
    if match:
        value = float(cleaned)
        return -value if negative else value

    if cleaned in _NUMBER_WORDS:
        value = float(_NUMBER_WORDS[cleaned])
        return -value if negative else value

    # "dos coma cinco" -> "dos . cinco"
    decimal = re.fullmatch(r"(\w+)\s*\.\s*(\w+)", cleaned)
    if decimal:
        whole = _word_or_digits(decimal.group(1))
        fraction = _word_or_digits(decimal.group(2))
        if whole is not None and fraction is not None:
            digits = len(str(int(fraction))) if fraction >= 1 else 1
            value = whole + fraction / (10**digits)
            return -value if negative else value

    # "treinta y dos", "cuarenta y cinco"
    parts = cleaned.replace(" y ", " ").split()
    total = 0.0
    found = False
    for part in parts:
        if part in _NUMBER_WORDS:
            total += _NUMBER_WORDS[part]
            found = True
    if found:
        return -total if negative else total
    return None


def _word_or_digits(token: str) -> float | None:
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        return float(token)
    if token in _NUMBER_WORDS:
        return float(_NUMBER_WORDS[token])
    return None


# ---------------------------------------------------------------- reglas


@dataclass
class Rule:
    name: str
    pattern: re.Pattern[str]
    build: Callable[[re.Match[str], Callable[[str], str]], tuple[str, dict[str, Any]] | None]
    example: str = ""
    # Algunas frases legítimas usan plural ("10 pistas") sin ser varias órdenes.
    allow_multi: bool = False


def _track(match: re.Match[str], orig: Callable[[str], str]) -> str:
    return strip_article(orig("track"))


def _clean(name: str) -> str:
    return strip_article((name or "").strip())


def _build_track_command(command: str):
    def build(match, orig):
        track = _track(match, orig)
        if not track:
            return None
        return command, {"track": track}

    return build


def _build_with_state(command: str, state: bool):
    def build(match, orig):
        track = _track(match, orig)
        if not track:
            return None
        return command, {"track": track, "state": state}

    return build


def _build_volume(match, orig):
    track = _track(match, orig)
    db = parse_number(match.group("db"))
    if not track or db is None:
        return None
    if match.group("dir").startswith("baj") or match.group("dir").startswith("reduc"):
        db = -abs(db)
    else:
        db = abs(db)
    return "track.adjust_volume", {"track": track, "delta_db": db}


def _build_volume_abs(match, orig):
    track = _track(match, orig)
    db = parse_number(match.group("db"))
    if not track or db is None:
        return None
    # El "-" de "-6" se pierde al normalizar: se mira el texto original.
    before = orig.before("db").strip()
    if before.endswith("-") or before.endswith("menos") or before.endswith("−"):
        db = -abs(db)
    return "track.set_volume", {"track": track, "db": db}


def _build_pan(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    side = match.group("side")
    amount = match.group("amount")
    value = abs(float(amount)) if amount else 100.0
    if side == "centro":
        value = 0.0
    elif side == "izquierda":
        value = -value
    return "track.set_pan", {"track": track, "pan": value}


def _build_pan_number(match, orig):
    track = _track(match, orig)
    value = parse_number(match.group("pan"))
    if not track or value is None:
        return None
    before = orig.before("pan").strip()
    if before.endswith("-") or before.endswith("−") or before.endswith("menos"):
        value = -abs(value)
    return "track.set_pan", {"track": track, "pan": max(-100.0, min(100.0, value))}


def _build_create_track(match, orig):
    name = orig("name").strip()
    name = NAME_PREFIXES.sub("", name)
    name = NAME_VERBS.sub("", name)
    name = strip_article(name)
    # "agregá una pista" sin nombre también vale: REAPER la nombra solo.
    return "track.add", ({"name": name} if name else {})


def _build_rename(match, orig):
    track = _track(match, orig)
    name = _clean(orig("name"))
    if not track or not name:
        return None
    return "track.rename", {"track": track, "name": name}


def _build_open_project(match, orig):
    raw = (orig("name") or "").strip()
    # "el proyecto de ayer" no es un nombre: que lo resuelva la IA (o pregunte).
    if re.match(r"^(?:de |del |que )", raw, flags=re.IGNORECASE):
        return None
    name = re.sub(r"^(?:el|la)\s+", "", raw, flags=re.IGNORECASE).strip()
    name = strip_article(name)
    if len(name) < 3:
        return None
    return "project.open", {"name": name}


def _build_tempo(match, orig):
    bpm = parse_number(match.group("bpm"))
    if bpm is None or bpm <= 0:
        return None
    return "project.set_tempo", {"bpm": bpm}


def _build_render(match, orig):
    return "render.start", {"mode": "mix"}


def _build_delete(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    return "track.delete", {"track": track}


def _build_duplicate(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    return "track.duplicate", {"track": track}


def _build_mixer(visible: bool):
    def build(match, orig):
        return "view.mixer", {"visible": visible}

    return build


def _build_output(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    first = int(match.group("pair"))
    # REAPER numera pares: 1/2 = par 1, 3/4 = par 2, 5/6 = par 3.
    pair = (first + 1) // 2
    return "track.output", {"track": track, "pair": max(1, pair)}


def _build_output_clear(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    return "track.output_clear", {"track": track}


def _build_fx_add(match, orig):
    track = _track(match, orig)
    fx = _clean(orig("fx"))
    if not track or not fx:
        return None
    return "fx.add", {"track": track, "name": fx}


def _build_fx_remove(match, orig):
    track = _track(match, orig)
    fx = _clean(orig("fx"))
    if not track or not fx:
        return None
    return "fx.remove", {"track": track, "fx": fx}


def _build_fx_bypass(match, orig):
    track = _track(match, orig)
    fx = _clean(orig("fx"))
    if not track or not fx:
        return None
    enabled = not match.group("off")
    return "fx.bypass", {"track": track, "fx": fx, "enabled": enabled}


def _build_fx_list(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    return "fx.list", {"track": track}


def _build_send_add(match, orig):
    source = _clean(orig("from"))
    target = _clean(orig("to"))
    if not source or not target:
        return None
    return "send.add", {"from": source, "to": target}


def _build_send_remove(match, orig):
    source = _clean(orig("from"))
    target = _clean(orig("to"))
    if not source or not target:
        return None
    return "send.remove", {"from": source, "to": target}


def _build_position(match, orig):
    bar = parse_number(match.group("bar"))
    if bar is None or bar < 1:
        return None
    return "transport.set_position", {"bar": int(bar)}


def _build_goto_marker(match, orig):
    name = _clean(orig("name"))
    if not name:
        return None
    return "transport.goto_marker", {"name": name}


def _build_select(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    return "track.select", {"track": track}


def _build_marker(match, orig):
    name = _clean(orig("name")) if match.groupdict().get("name") else ""
    if name:
        return "marker.add", {"name": name}
    return "marker.add", {}


def _build_render_stems(match, orig):
    return "render.start", {"mode": "stems"}


def _build_render_selection(match, orig):
    return "render.start", {"mode": "time_selection"}


def _build_render_lufs(match, orig):
    value = parse_number(match.group("lufs"))
    if value is None:
        return None
    # Los objetivos de loudness son negativos: "-14 LUFS".
    return "render.start", {"mode": "mix", "normalize_lufs": -abs(value)}


def _build_color(match, orig):
    track = _track(match, orig)
    color = (match.group("color") or "").strip()
    if not track or not color:
        return None
    return "track.set_color", {"track": track, "color": color}


def _build_solo_in(match, orig):
    track = _track(match, orig)
    if not track:
        return None
    return "track.solo", {"track": track, "state": True}


def _build_step_volume(match, orig):
    """«la pista 23, un decibel más bajo» -> ajuste de ±1 dB."""
    track = _track(match, orig)
    if not track:
        return None
    direction = match.group("dir")
    delta = -1.0 if direction.startswith(("baj", "abaj")) else 1.0
    return "track.adjust_volume", {"track": track, "delta_db": delta}


def _build_add_many(match, orig):
    count = parse_number(match.group("count"))
    if count is None:
        return None
    total = int(count)
    if total < 2 or total > 64:
        return None
    return "track.add_many", {"count": total}


def _const(command: str, args: dict[str, Any] | None = None):
    def build(match, orig):
        return command, dict(args or {})

    return build


# El orden importa: lo más específico primero. Por ejemplo "poné el tempo en 120"
# tiene que resolverse antes que el patrón genérico "poné X en Y".
RULES: list[Rule] = [
    # ---------------------------------------------------------------- transporte
    Rule(
        "play",
        re.compile(r"(?:dale|dele|reproduci|reproducir|play|arranca|empeza|va|pone play|dale play)"),
        _const("transport.play"),
        "dale",
    ),
    Rule(
        "stop",
        re.compile(
            r"(?:para|parar|stop|detene|detener|frena|frenar)"
            r"(?: la reproduccion| la grabacion| la musica| todo| el transporte)?"
        ),
        _const("transport.stop"),
        "pará",
    ),
    Rule("pause", re.compile(r"(?:pausa|pausar|pausala)"), _const("transport.pause"), "pausá"),
    Rule(
        "record",
        re.compile(
            r"(?:dale )?(?:graba|grabar|record|a grabar|empeza a grabar|arranca a grabar|"
            r"empecemos a grabar|grabemos|grabale)"
        ),
        _const("transport.record"),
        "grabá",
    ),
    Rule(
        "goto_start",
        re.compile(r"(?:(?:anda|ve|volve|vuelve|ir) )?(?:(?:al|a el) )?(?:inicio|principio|comienzo)(?: del proyecto)?"),
        _const("transport.goto_start"),
        "andá al inicio",
    ),
    Rule(
        "goto_end",
        re.compile(r"(?:(?:anda|ve|volve|vuelve|ir) )?(?:(?:al|a el) )?(?:final|fin|terminar)(?: del proyecto)?"),
        _const("transport.goto_end"),
        "andá al final",
    ),
    Rule(
        "position",
        re.compile(
            r"(?:(?:anda|ve|volve|vuelve|salta|posicionate|ponete|ir) )?"
            r"(?:al|a el|en el|a) compas (?P<bar>\d+)"
        ),
        _build_position,
        "andá al compás 5",
    ),
    Rule(
        "goto_marker",
        re.compile(r"(?:(?:anda|ve|salta|ir) )?(?:al|a la) (?:marcador|marca) (?P<name>.+)"),
        _build_goto_marker,
        "andá al marcador estribillo",
    ),
    Rule(
        "loop_on",
        re.compile(r"(?:prende|activa|enciende) el loop"),
        _const("transport.set_loop", {"enabled": True}),
        "activá el loop",
    ),
    Rule(
        "loop_off",
        re.compile(r"(?:apaga|desactiva|saca) el loop"),
        _const("transport.set_loop", {"enabled": False}),
        "desactivá el loop",
    ),
    # ---------------------------------------------------------------- proyecto
    Rule(
        "undo",
        re.compile(
            r"(?:deshace|deshacer|deshacelo|deshace eso|deshace lo ultimo|undo|"
            r"volve atras|volver atras|un paso atras|paso atras)"
        ),
        _const("project.undo"),
        "deshacé lo último",
    ),
    Rule(
        "redo",
        re.compile(r"(?:rehace|rehacer|rehacelo|rehace eso|redo)"),
        _const("project.redo"),
        "rehacé",
    ),
    Rule(
        "open_project",
        re.compile(
            r"(?:abri|abrime|abre|abrir|carga|cargame|cargar|abrime) (?:el |la )?proyecto (?P<name>.+)"
        ),
        _build_open_project,
        "abrí el proyecto Free From Adiction",
    ),
    Rule(
        "save",
        re.compile(r"(?:guarda|guardar|salva|salvar)(?: los cambios| el proyecto)?"),
        _const("project.save"),
        "guardá",
    ),
    Rule(
        "metronome_on",
        re.compile(r"(?:prende|activa|enciende) (?:el|al) (?:metronomo|click)"),
        _const("project.set_metronome", {"enabled": True}),
        "prendé el metrónomo",
    ),
    Rule(
        "metronome_off",
        re.compile(r"(?:apaga|desactiva|saca) (?:el|al) (?:metronomo|click)"),
        _const("project.set_metronome", {"enabled": False}),
        "apagá el click",
    ),
    Rule(
        "tempo",
        re.compile(
            r"(?:pon|pone|pones|cambia|cambiale|setea|set|ajusta|deja) (?:el )?(?:tempo|tiempo|bpm) "
            r"(?:en |a )?(?P<bpm>[\w.,]+)"
        ),
        _build_tempo,
        "poné el tempo en 120",
    ),
    Rule(
        "tempo_session",
        re.compile(r".*?(?P<bpm>\d+(?:[.,]\d+)?) bpm"),
        _build_tempo,
        "ajustá la sesión a 80 BPM",
    ),
    Rule(
        "render_stems",
        re.compile(
            r"(?:renderiza|renderizar|exporta|exportar) (?:los |las )?"
            r"(?:stems|pistas por separado|todas las pistas|pistas individuales)"
        ),
        _build_render_stems,
        "renderizá los stems",
        allow_multi=True,
    ),
    Rule(
        "render_selection",
        re.compile(
            r"(?:renderiza|renderizar|exporta|exportar) (?:la )?"
            r"(?:seleccion|seleccion de tiempo|parte seleccionada)"
        ),
        _build_render_selection,
        "renderizá la selección",
    ),
    Rule(
        "render_lufs",
        re.compile(
            r"(?:renderiza|renderizar|exporta|exportar) (?:la mezcla |el proyecto |todo )?"
            r"(?:a|en) (?P<lufs>\d+(?:[.,]\d+)?) ?lufs"
        ),
        _build_render_lufs,
        "exportá a -14 LUFS",
    ),
    Rule("render", re.compile(r"(?:renderiza|renderizar|render|exporta|exportar)(?: la mezcla| el proyecto| todo)?"), _build_render, "renderizá la mezcla"),
    # ---------------------------------------------------------------- vista
    Rule(
        "mixer_on",
        re.compile(r"(?:abri|abre|abrime|mostrame|mostra|mostrar|desplega) el (?:mixer|mezclador)"),
        _build_mixer(True),
        "abrí el mixer",
    ),
    Rule(
        "mixer_off",
        re.compile(r"(?:cerra|cierra|cerrame|oculta|ocultame|esconde) el (?:mixer|mezclador)"),
        _build_mixer(False),
        "cerrá el mixer",
    ),
    Rule(
        "routing_on",
        re.compile(
            r"(?:abri|abre|abrime|mostrame|mostra|desplega) (?:la )?"
            r"(?:matriz de ruteo|ventana de ruteo|matriz de enrutamiento|matriz de ruteo|ruteo)"
        ),
        _const("view.routing"),
        "abrí la matriz de ruteo",
    ),
    Rule(
        "routing_off",
        re.compile(
            r"(?:cerra|cierra|cerrame|oculta|esconde) (?:la )?"
            r"(?:matriz de ruteo|ventana de ruteo|matriz de enrutamiento|ruteo)"
        ),
        _const("view.routing"),
        "cerrá la matriz de ruteo",
    ),
    # ---------------------------------------------------------------- pistas
    Rule(
        "volume",
        re.compile(
            r"(?P<dir>subi|sube|subile|subele|baja|bajale|bajale|aumenta|reduce|reducele) "
            r"(?:el |la )?(?:volumen|ganancia|nivel)? ?(?:de |del |de la )?"
            r"(?:la pista |el |la )?(?P<track>.+?) (?P<db>-?[\w.,]+)(?: db| decibeles)?"
        ),
        _build_volume,
        "subí la guitarra 2 dB",
    ),
    Rule(
        "volume_abs",
        re.compile(
            r"(?:pone|pon|deja|dejale|setea|fija|ajusta|pones) (?:el |la )?"
            r"(?:volumen|ganancia|nivel)? ?(?:de |del |de la )?(?:la pista |el |la )?"
            r"(?P<track>.+?) (?:en|a) (?P<db>-?[\w.,]+) ?(?:db|decibeles)"
        ),
        _build_volume_abs,
        "poné el bajo en -6 dB",
    ),
    Rule(
        "volume_step",
        re.compile(
            r"(?:la pista |el |la )?(?P<track>.+?),? (?:un|1) (?:decibel|db) mas (?P<dir>bajo|abajo|alto|arriba)"
        ),
        _build_step_volume,
        "la pista 23, un decibel más bajo",
    ),
    Rule(
        "volume_inverted",
        re.compile(
            r"(?:el |la )?volumen (?:de |del |de la )?(?:la pista |el |la )?(?P<track>.+?) "
            r"(?P<dir>subilo|subile|subi|bajalo|bajale|baja) (?P<db>-?[\w.,]+)(?: db| decibeles)?"
        ),
        _build_volume,
        "el volumen de la pista 2, subilo 3 dB",
    ),
    Rule(
        "pan_side",
        re.compile(
            r"(?:panea|paneale|pone|pon|deja|manda) (?:la pista |el |la )?(?P<track>.+?) "
            r"(?P<amount>\d+)? ?%? ?(?:a la |a |al |hacia la |hacia el )?(?P<side>izquierda|derecha|centro)"
        ),
        _build_pan,
        "paneá la guitarra a la izquierda",
    ),
    Rule(
        "pan_number",
        re.compile(r"(?:panea|paneale|pone|pon) (?:la pista |el |la )?(?P<track>.+?) (?:a|en) (?P<pan>-?\d+)"),
        _build_pan_number,
        "paneá la voz a -30",
    ),
    Rule(
        "mute",
        re.compile(
            r"(?:silencia|silencio|mutea|mute|muteale|mutear|silenciala|pon mute en|pone mute en|ponle mute a) "
            r"(?:la pista |el |la )?(?P<track>.+)"
        ),
        _build_with_state("track.mute", True),
        "silenciá el bajo",
    ),
    Rule(
        "unmute",
        re.compile(
            r"(?:desilencia|desmutea|dessilencia|quita el mute de|saca el mute de|activa) "
            r"(?:la pista |el |la )?(?P<track>.+)"
        ),
        _build_with_state("track.mute", False),
        "desilenciá el bajo",
    ),
    Rule(
        "solo",
        re.compile(r"(?:solo en|hace solo en|hacele solo a|pon solo en|aisla) (?:la pista |el |la )?(?P<track>.+)"),
        _build_with_state("track.solo", True),
        "solo en la batería",
    ),
    Rule(
        "solo_in",
        re.compile(
            r"(?:deja|dejale|pone|pon|ponle) (?:la pista |el |la )?(?P<track>.+?) (?:en|al) solo"
        ),
        _build_solo_in,
        "dejá el bajo en solo",
    ),
    Rule(
        "unsolo",
        re.compile(r"(?:saca el solo|quita el solo)(?: de)? (?:la pista |el |la )?(?P<track>.+)"),
        _build_with_state("track.solo", False),
        "sacá el solo de la batería",
    ),
    Rule(
        "arm",
        re.compile(r"(?:arma|armala|prepara|preparala) (?:la pista |el |la )?(?P<track>.+?)(?: para grabar)?"),
        _build_with_state("track.arm", True),
        "armá la guitarra",
    ),
    Rule(
        "disarm",
        re.compile(r"(?:desarma|desarmala|saca el armado de|quita el armado de) (?:la pista |el |la )?(?P<track>.+)"),
        _build_with_state("track.arm", False),
        "desarmá la guitarra",
    ),
    Rule(
        "rename",
        re.compile(
            r"(?:renombra|renombrala|renombra la pista|cambia el nombre de|ponele nombre a) "
            r"(?:la pista |el |la )?(?P<track>.+?) (?:a|como|por) (?P<name>.+)"
        ),
        _build_rename,
        "renombrá la pista 2 como Batería",
    ),
    Rule(
        "add_many_tracks",
        re.compile(
            r"(?:agrega|agregale|crea|creale|suma|sumale|anadi|anadile) "
            r"(?P<count>\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez) pistas?(?: de audio)?"
        ),
        _build_add_many,
        "agregá 10 pistas",
        allow_multi=True,
    ),
    Rule(
        "create_track",
        re.compile(
            r"(?:crea|creale|agrega|agregale|anadi|suma) (?:una|un) pista"
            r"(?: (?:llamada|que se llame|de|para))? ?(?P<name>.+)?"
        ),
        _build_create_track,
        "creá una pista llamada Guitarra",
    ),
    Rule(
        "delete_track",
        re.compile(r"(?:borra|elimina|saca|quita) la pista (?P<track>.+)"),
        _build_delete,
        "borrá la pista 3",
    ),
    Rule("duplicate", re.compile(r"(?:duplica|clona|duplicame) (?:la pista )?(?P<track>.+)"), _build_duplicate, "duplicá la voz"),
    Rule(
        "delete_number",
        re.compile(r"(?:borra|elimina|saca|quita) (?:la|el) (?P<track>\d+)"),
        _build_delete,
        "borrá la 3",
    ),
    Rule(
        "color",
        re.compile(
            r"(?:pinta|pintale|colorea|coloreale|ponele color a|pone color a) (?:la pista |el |la )?"
            r"(?P<track>.+?) (?:de |en )?(?P<color>rojo|naranja|amarillo|verde|celeste|azul|violeta|rosa|blanco|gris|negro)"
        ),
        _build_color,
        "pintá la pista 2 de violeta",
    ),
    Rule(
        "output",
        re.compile(
            r"(?:manda|mandale|rutea|ruteale|asigna|asignale|manda la salida de) (?:la pista |el |la )?"
            r"(?P<track>.+?) a (?:las salidas|los canales|la salida|las output) (?P<pair>\d+)"
            r"(?: (?:y|e) (?P<pair2>\d+))?"
        ),
        _build_output,
        "mandá la batería a las salidas 3 y 4",
    ),
    Rule(
        "output_clear",
        re.compile(
            r"(?:saca|quita|elimina|limpia) (?:las salidas|el ruteo de monitoreo|la salida fisica|las salidas fisicas)"
            r"(?: fisicas)? (?:de|del) (?:la pista |el |la )?(?P<track>.+)"
        ),
        _build_output_clear,
        "sacá las salidas físicas de la batería",
    ),
    Rule(
        "select",
        re.compile(r"(?:selecciona|seleccionale|seleccionar|marca) (?:la pista |el |la )?(?P<track>.+)"),
        _build_select,
        "seleccioná la voz",
    ),
    # ---------------------------------------------------------------- plugins
    Rule(
        "fx_list",
        re.compile(
            r"(?:que (?:plugins|fx|efectos) (?:tiene|tiene cargados|hay en)|"
            r"lista(?:me)? (?:los )?(?:plugins|fx|efectos) (?:de |en )?)"
            r"(?:la pista |el |la )?(?P<track>.+)"
        ),
        _build_fx_list,
        "¿qué plugins tiene la voz?",
    ),
    Rule(
        "send_remove",
        re.compile(
            r"(?:saca|quita|elimina) el envio de (?:la pista |el |la )?(?P<from>.+?) (?:a|al|a la) "
            r"(?:la pista |el |la )?(?P<to>.+)"
        ),
        _build_send_remove,
        "sacá el envío de la voz al reverb",
    ),
    Rule(
        "send_add",
        re.compile(
            r"(?:manda|mandale|envia|enviale|rutea) (?:la pista |el |la )?(?P<from>.+?) (?:a|al|a la) "
            r"(?:la pista |el |la )?(?P<to>.+)"
        ),
        _build_send_add,
        "mandá la voz al reverb",
    ),
    Rule(
        "fx_add",
        re.compile(
            r"(?:carga|cargale|inserta|insertale|pone|pon|ponle|agrega|agregale|sumale|suma) "
            r"(?:el |la |un |una )?(?P<fx>.+?) (?:en|a) (?:la pista |el |la )?(?P<track>.+)"
        ),
        _build_fx_add,
        "cargá ReaEQ en la voz",
    ),
    Rule(
        "fx_remove",
        re.compile(
            r"(?:saca|quita|elimina|borra|sacale|quitale) (?:el |la )?(?!envio)(?P<fx>.+?) de "
            r"(?:la pista |el |la )?(?P<track>.+)"
        ),
        _build_fx_remove,
        "sacá el ReaEQ de la voz",
    ),
    Rule(
        "fx_bypass",
        re.compile(
            r"(?P<off>bypasea|bypaseale|bypass|desactiva|apaga|activa|prende) (?:el |la )?"
            r"(?P<fx>.+?) en (?:la pista |el |la )?(?P<track>.+)"
        ),
        _build_fx_bypass,
        "bypaseá el compresor en la voz",
    ),
    # ---------------------------------------------------------------- ítems y marcadores
    Rule(
        "item_delete",
        re.compile(r"(?:borra|elimina|saca) (?:los items|los items seleccionados|lo seleccionado|los items selecionados)"),
        _const("item.delete_selected"),
        "borrá los ítems seleccionados",
    ),
    Rule(
        "item_split",
        re.compile(r"(?:corta|cortale|parti|parte|dividi|divide) (?:en|por) el cursor"),
        _const("item.split_at_cursor", {}),
        "cortá en el cursor",
    ),
    Rule(
        "marker_add",
        re.compile(r"(?:pone|pon|agrega|marca|marcame) (?:un )?marcador(?: (?:llamado|que se llame|de nombre))?(?: (?P<name>.+))?"),
        _build_marker,
        "poné un marcador",
    ),
]


class _Original:
    """Recupera el texto original de un grupo y su contexto."""

    def __init__(self, text: str, index_map: list[int], found: re.Match[str]) -> None:
        self._text = text
        self._index_map = index_map
        self._found = found

    def __call__(self, name: str) -> str:
        try:
            start, end = self._found.span(name)
        except (IndexError, KeyError):
            return ""
        if start < 0 or end < 0 or not self._index_map:
            return ""
        start = min(start, len(self._index_map) - 1)
        end = min(end - 1, len(self._index_map) - 1)
        if end < start:
            return ""
        return self._text[self._index_map[start] : self._index_map[end] + 1].strip()

    def before(self, name: str, window: int = 12) -> str:
        """Texto original inmediatamente anterior al grupo."""
        try:
            start, _end = self._found.span(name)
        except (IndexError, KeyError):
            return ""
        if start < 0 or start >= len(self._index_map):
            return ""
        # Posición en el texto original del primer carácter del grupo.
        position = self._index_map[start]
        return self._text[max(0, position - window) : position]


def match(text: str) -> tuple[str, dict[str, Any], str] | None:
    """Devuelve (comando, args, nombre_regla) si la frase es un comando directo."""
    if not text:
        return None
    normalized, index_map = normalize_with_index(text)
    if not normalized or len(normalized) > MAX_CHARS:
        return None
    padded = f" {normalized} "
    # "3 y 4" (salidas) no es una segunda orden: se neutraliza para el chequeo.
    check = re.sub(r"(?<=\d) y (?=\d)", " ", padded)
    multi_clause = any(marker in check for marker in SECOND_CLAUSE_MARKERS)
    multi_target = any(marker in check for marker in MULTI_TARGET_MARKERS)

    for rule in RULES:
        if (multi_clause or multi_target) and not rule.allow_multi:
            continue
        found = rule.pattern.fullmatch(normalized)
        if not found:
            continue
        original = _Original(text, index_map, found)
        try:
            built = rule.build(found, original)
        except (AttributeError, TypeError, ValueError):
            built = None
        if built is None:
            continue
        command, args = built
        return command, args, rule.name
    return None


def describe_rules() -> list[tuple[str, str]]:
    return [(rule.name, rule.example) for rule in RULES if rule.example]
