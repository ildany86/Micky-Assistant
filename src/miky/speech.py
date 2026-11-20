"""Texto hablado: plantillas de respuesta para cada comando.

Las respuestas se arman localmente (sin gastar cuota de IA ni sumar latencia).
"""

from __future__ import annotations

from typing import Any

from .catalog import CommandSpec

DEFAULT_OK = "Listo."
DEFAULT_ERROR = "No pude hacerlo."


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:  # noqa: D105
        return ""


def _numbers_to_text(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def render_template(template: str, values: dict[str, Any]) -> str:
    if not template:
        return ""
    safe = _SafeDict({k: _numbers_to_text(v) for k, v in values.items() if not isinstance(v, (list, dict))})
    try:
        text = template.format_map(safe)
    except (KeyError, IndexError, ValueError):
        return template
    return " ".join(text.split())


def describe_success(spec: CommandSpec, result: dict[str, Any]) -> str:
    if not spec.speech:
        return DEFAULT_OK
    values = dict(result or {})
    # El nombre de la pista a veces viene como "name" y a veces no viene.
    if "track_name" not in values and "name" in values:
        values["track_name"] = values["name"]
    text = render_template(spec.speech, values)
    return text or DEFAULT_OK


def describe_failure(spec: CommandSpec | None, message: str) -> str:
    message = (message or "").strip().rstrip(".")
    if not message:
        return DEFAULT_ERROR

    # Errores técnicos: se traducen a algo que se pueda decir en voz alta.
    if message.startswith("falta track para"):
        return "¿Qué pista querés?"
    if message.startswith("falta name para"):
        return "¿Cómo querés que se llame?"
    message = message.replace("no encontre", "no encontré").replace("no existe la pista", "no existe la pista")
    message = _shorten_track_list(message)

    if spec and spec.id == "track.delete":
        return f"No borré nada: {message}."
    return f"No pude: {message}."


def _shorten_track_list(message: str) -> str:
    """'… pistas actuales: 1=voz, 2=bajo' -> '… Las que hay: voz, bajo.'"""
    marker = "pistas actuales:"
    if marker not in message:
        return message
    head, _, tail = message.partition(marker)
    names = []
    for item in tail.split(","):
        item = item.strip()
        if "=" in item:
            item = item.split("=", 1)[1]
        if item:
            names.append(item.strip().strip("'").strip('"'))
    head = head.strip().rstrip(".").strip()
    if not names:
        return head
    return f"{head}. Las que hay: {', '.join(names[:6])}"


def describe_plan(specs_and_results: list[tuple[CommandSpec, dict[str, Any]]]) -> str:
    """Resumen de un plan de varios pasos.

    No se encadena una frase por paso: se agrupa por comando y se cuenta.
    Seis borrados suenan «Listo, borré 6 pistas», no seis veces «borré».
    """
    if not specs_and_results:
        return DEFAULT_OK
    if len(specs_and_results) == 1:
        spec, result = specs_and_results[0]
        return describe_success(spec, result)

    # Agrupar por comando conservando el orden de aparición.
    groups: list[tuple[str, list[tuple[CommandSpec, dict[str, Any]]]]] = []
    for spec, result in specs_and_results:
        for command, items in groups:
            if command == spec.id:
                items.append((spec, result))
                break
        else:
            groups.append((spec.id, [(spec, result)]))

    if len(groups) == 1:
        command, items = groups[0]
        if len(items) > 1:
            phrase = _action_phrase(command, len(items))
            if phrase:
                return f"Listo, {phrase}."
        return DEFAULT_OK

    parts: list[str] = []
    for command, items in groups[:3]:
        if len(items) == 1:
            phrase = _short(describe_success(items[0][0], items[0][1]))
            # "Dale." o "Grabando." sueltos suenan raros en una lista: se cambia
            # por una frase con verbo ("arranqué la reproducción").
            if len(phrase) <= 12:
                phrase = _action_phrase(command, 1) or phrase
            parts.append(phrase)
        else:
            parts.append(_action_phrase(command, len(items)) or f"toqué {len(items)} cosas")
    if len(groups) > 3:
        parts.append("el resto")
    text = _join(parts)
    return f"Listo: {text}."


# Verbo, objeto singular y plural para resumir varios pasos.
ACTIONS: dict[str, tuple[str, str, str]] = {
    "track.add": ("creé", "la pista", "pistas"),
    "track.add_like": ("copié", "la pista", "pistas"),
    "track.delete": ("borré", "la pista", "pistas"),
    "track.rename": ("renombré", "la pista", "pistas"),
    "track.mute": ("silencié", "la pista", "pistas"),
    "track.arm": ("armé", "la pista", "pistas"),
    "track.solo": ("dejé en solo", "la pista", "pistas"),
    "track.duplicate": ("dupliqué", "la pista", "pistas"),
    "track.move": ("moví", "la pista", "pistas"),
    "fx.add": ("cargué", "el plugin", "plugins"),
    "fx.remove": ("saqué", "el plugin", "plugins"),
    "fx.bypass": ("bypaseé", "el plugin", "plugins"),
    "send.add": ("armé", "el envío", "envíos"),
    "send.remove": ("saqué", "el envío", "envíos"),
    "item.keep_between": ("recorté", "el ítem", "ítems"),
    "marker.add": ("puse", "el marcador", "marcadores"),
    "region.add": ("puse", "la región", "regiones"),
    "transport.play": ("arranqué", "la reproducción", ""),
    "transport.stop": ("paré", "la reproducción", ""),
    "transport.pause": ("pausé", "la reproducción", ""),
    "transport.record": ("arranqué a grabar", "", ""),
    "view.mixer": ("mostré", "el mezclador", ""),
    "view.routing": ("mostré", "la ventana de ruteo", ""),
}


def _action_phrase(command: str, count: int) -> str:
    action = ACTIONS.get(command)
    if not action:
        return ""
    verb, singular, plural = action
    if count <= 1:
        return f"{verb} {singular}".strip()
    if not plural:
        return verb
    return f"{verb} {count} {plural}"


def _short(phrase: str) -> str:
    """'Listo, borré la pista Voz.' -> 'borré la pista Voz'."""
    text = (phrase or "").strip()
    for prefix in ("Listo, ", "Listo. ", "Listo: "):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.rstrip(".")
    return text[:1].lower() + text[1:] if text else text


def _join(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " y " + parts[-1]


def describe_status(status) -> str:
    if not status.alive:
        return "No estoy conectado a REAPER."
    parts = [f"REAPER {status.reaper_version}"]
    if status.project:
        parts.append(status.project)
    if status.busy:
        parts.append("ocupado renderizando")
    return " · ".join(parts)
