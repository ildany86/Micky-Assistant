"""Genera la referencia del catálogo de comandos a partir de commands.json.

Así la documentación no se desincroniza del código: si se agrega un comando,
se corre este script y el documento queda al día.

Uso: python tools/gen_catalog_doc.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "src" / "miky" / "data" / "commands.json"
OUT = ROOT / "docs" / "03-catalogo-comandos.md"

CATEGORY_TITLES = {
    "pistas": "Pistas",
    "plugins": "Plugins y procesamiento",
    "ruteo": "Ruteo y envíos",
    "edicion": "Edición de items",
    "transporte": "Transporte",
    "proyecto": "Proyecto",
    "contenido": "Marcadores y regiones",
    "vista": "Vista de REAPER",
    "render": "Renderizado",
}

TYPE_NAMES = {
    "string": "texto",
    "number": "número",
    "integer": "entero",
    "boolean": "verdadero/falso",
    "array": "lista",
}


def describe_param(name: str, spec: dict) -> str:
    kind = TYPE_NAMES.get(spec.get("type", "string"), spec.get("type", ""))
    bits = [f"`{name}`", f"({kind})"]
    if spec.get("enum"):
        bits.append("valores: " + ", ".join(f"`{value}`" for value in spec["enum"]))
    elif spec.get("items"):
        bits.append(f"lista de {TYPE_NAMES.get(spec['items'].get('type'), 'texto')}")
    if spec.get("minimum") is not None and spec.get("maximum") is not None:
        bits.append(f"de {spec['minimum']} a {spec['maximum']}")
    elif spec.get("minimum") is not None:
        bits.append(f"mínimo {spec['minimum']}")
    description = (spec.get("description") or "").strip()
    text = " ".join(bits)
    if description:
        text += f": {description}"
    return text


def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    commands = data["commands"]

    lines: list[str] = [
        "# Catálogo de comandos",
        "",
        "> Documento generado desde `src/miky/data/commands.json` con `python tools/gen_catalog_doc.py`.",
        "> No editar a mano: los cambios van en el JSON y se vuelve a generar.",
        "",
        f"La beta expone **{len(commands)} comandos**. Este es el universo cerrado de cosas que Miky",
        "puede hacerle a REAPER. La IA elige entre estos comandos y nada más: no puede ejecutar",
        "código ni inventar operaciones.",
        "",
        "## Cómo se leen las fichas",
        "",
        "- **id**: identificador interno (el que usa el motor y el puente Lua).",
        "- **Parámetros**: lo que acepta el comando. Los marcados con \\* son obligatorios.",
        "- **Pide confirmación**: acciones que no se deshacen con Ctrl+Z (o que escriben archivos).",
        "- **Respuesta hablada**: plantilla de lo que dice Miky al terminar.",
        "",
        "Los índices de pista y de plugin son **1-based** (la primera pista es la 1). Una pista se",
        "puede indicar por número (`\"2\"`) o por nombre (`\"Guitarra\"`); si se omite, se usa la pista",
        "seleccionada en REAPER.",
        "",
        "## Resumen",
        "",
        "| Categoría | Comandos |",
        "|---|---|",
    ]

    by_category: dict[str, list[dict]] = {}
    for command in commands:
        by_category.setdefault(command.get("category", "otros"), []).append(command)
    for category, items in by_category.items():
        lines.append(f"| {CATEGORY_TITLES.get(category, category)} | {len(items)} |")
    lines.append("")

    for category, items in by_category.items():
        lines.append(f"## {CATEGORY_TITLES.get(category, category)}")
        lines.append("")
        for command in items:
            required = set(command.get("required") or [])
            lines.append(f"### `{command['id']}`")
            lines.append("")
            lines.append(command.get("summary", "").strip())
            lines.append("")
            params = command.get("params") or {}
            if params:
                lines.append("**Parámetros**")
                lines.append("")
                for name, spec in params.items():
                    star = "\\*" if name in required else ""
                    lines.append(f"- {describe_param(name, spec)} {star}".rstrip())
                lines.append("")
            else:
                lines.append("_Sin parámetros._")
                lines.append("")
            flags = []
            if command.get("danger"):
                flags.append("**Pide confirmación antes de ejecutar.**")
            speech_template = (command.get("speech") or "").strip()
            if speech_template:
                flags.append(f"Dice: «{speech_template}»")
            if command.get("examples"):
                examples = " · ".join(f"«{item}»" for item in command["examples"])
                flags.append(f"Ejemplos: {examples}")
            if flags:
                lines.extend(flags)
                lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"escrito {OUT.relative_to(ROOT)} ({len(commands)} comandos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
