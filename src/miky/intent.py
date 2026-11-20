"""Clasificación de intención: qué familia de comandos necesita este pedido.

La IA recibe 53 herramientas en cada llamada. Eso son miles de tokens que se
pagan en latencia y que además confunden a los modelos chicos. Si sabemos de
antemano que el pedido habla de plugins, alcanza con mandarle las 6 de plugins.

La clasificación es local, por palabras clave, y falla "hacia el lado seguro":
si no reconoce nada, se manda el catálogo completo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import router


@dataclass(frozen=True)
class Family:
    name: str
    keywords: re.Pattern[str]
    commands: tuple[str, ...]


# Comandos que siempre conviene tener a mano, en cualquier pedido.
CORE = ("miky_ask", "miky_respond", "transport.stop", "project.undo")

FAMILIES: tuple[Family, ...] = (
    Family(
        "vista",
        re.compile(r"\b(mixer|mezclador|ruteo|matriz|enrutamiento|ventana)\b"),
        ("view.mixer", "view.routing"),
    ),
    Family(
        "transporte",
        re.compile(
            r"\b(play|reproduc|reproduce|dale|para|pausa|grab|record|loop|cursor|"
            r"compas|inicio|principio|final|posicion|transporte)\b"
        ),
        (
            "transport.play",
            "transport.stop",
            "transport.pause",
            "transport.record",
            "transport.set_position",
            "transport.goto_start",
            "transport.goto_end",
            "transport.goto_marker",
            "transport.set_loop",
        ),
    ),
    Family(
        "proyecto",
        re.compile(r"\b(guarda|guardar|salva|deshace|rehace|tempo|bpm|metronomo|click|proyecto)\b"),
        (
            "project.save",
            "project.save_as",
            "project.undo",
            "project.redo",
            "project.set_tempo",
            "project.set_metronome",
        ),
    ),
    Family(
        "pista_crear",
        re.compile(
            r"\b(crea|crear|agrega|agregar|suma|sumar|anadi|nueva|nuevo|duplica|clona|"
            r"renombra|borra|elimina|quita|saca|mueve|mover|ordena)\b"
        ),
        (
            "track.add",
            "track.add_many",
            "track.add_like",
            "track.rename",
            "track.delete",
            "track.duplicate",
            "track.move",
        ),
    ),
    Family(
        "pista_nivel",
        re.compile(
            r"\b(volumen|ganancia|nivel|db|decibeles|panea|pan|silencia|mutea|mute|solo|"
            r"arma|desarma|armado|color|entrada|monitor|selecciona|seleccion)\b"
        ),
        (
            "track.set_volume",
            "track.adjust_volume",
            "track.set_pan",
            "track.mute",
            "track.solo",
            "track.arm",
            "track.set_color",
            "track.set_monitor",
            "track.set_input",
            "track.select",
        ),
    ),
    Family(
        "fx",
        re.compile(
            r"\b(plugin|plugins|fx|efecto|efectos|compresor|compresion|ecualizador|eq|"
            r"reverb|delay|limitador|autotune|inserta|insertar|bypasea|bypass|parametro)\b"
        ),
        ("fx.add", "fx.remove", "fx.bypass", "fx.set_param", "fx.list", "fx.open"),
    ),
    Family(
        "envio",
        re.compile(r"\b(envio|envios|envia|manda|mandar|rutea|ruteo|salida|salidas|bus|auxiliar)\b"),
        (
            "send.add",
            "send.remove",
            "send.set_level",
            "track.output",
            "track.output_clear",
        ),
    ),
    Family(
        "item",
        re.compile(r"\b(item|items|toma|tomas|corta|cortar|split|divide|parti|fade|recorta)\b"),
        ("item.keep_between", "item.split_at_cursor", "item.delete_selected"),
    ),
    Family(
        "marcador",
        re.compile(r"\b(marcador|marcadores|marca|region|regiones)\b"),
        ("marker.add", "region.add", "transport.goto_marker"),
    ),
    Family(
        "render",
        re.compile(r"\b(render|renderiza|renderizar|exporta|exportar|mastering|mezcla|stems|wav|mp3)\b"),
        ("render.start", "project.save_as"),
    ),
)


def families_for(text: str) -> tuple[str, ...]:
    """Nombres de las familias que activa el pedido."""
    normalized = router.normalize(text or "")
    if not normalized:
        return ()
    found: list[str] = []
    for family in FAMILIES:
        if family.keywords.search(normalized):
            found.append(family.name)
    return tuple(found)


def commands_for_families(names: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    by_name = {family.name: family for family in FAMILIES}
    selected: list[str] = []
    for name in names:
        family = by_name.get(name)
        if family is None:
            continue
        for command in family.commands:
            if command not in selected:
                selected.append(command)
    for command in CORE:
        if command not in selected:
            selected.append(command)
    return tuple(selected)


def commands_for_text(text: str) -> tuple[str, ...] | None:
    """Comandos a ofrecerle a la IA. None = mandar el catálogo completo."""
    names = families_for(text)
    if not names:
        return None
    return commands_for_families(names)
