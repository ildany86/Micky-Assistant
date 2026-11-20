"""Arma el script único del puente que se instala en REAPER.

Los módulos de `reaper/src/` se concatenan en `miky_bridge.lua` para que el
usuario final tenga un solo archivo (más fácil de instalar, revisar y versionar).

Uso:
    python tools/build_lua.py            # genera y verifica sintaxis
    python tools/build_lua.py --check    # solo verifica
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "reaper" / "src"
OUT_PATHS = [
    ROOT / "reaper" / "build" / "miky_bridge.lua",
    ROOT / "src" / "miky" / "data" / "miky_bridge.lua",
]

MODULES = [
    "version.lua",
    "json.lua",
    "util.lua",
    "state.lua",
    "cmd_tracks.lua",
    "cmd_fx.lua",
    "cmd_transport.lua",
    "cmd_content.lua",
    "cmd_sends.lua",
    "cmd_items.lua",
    "registry.lua",
    "ipc.lua",
    "main.lua",
]


def project_version() -> str:
    text = (ROOT / "src" / "miky" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("no encontré __version__ en src/miky/__init__.py")
    return match.group(1)


def read_module(name: str) -> str:
    path = SRC / "miky" / name if name != "main.lua" else SRC / "main.lua"
    if not path.exists():
        raise SystemExit(f"falta el módulo {path}")
    return path.read_text(encoding="utf-8").rstrip() + "\n"


def build(version: str) -> str:
    header = (
        f"-- Miky bridge v{version}\n"
        "-- Generado por tools/build_lua.py · no editar a mano.\n"
        "-- Puente de control entre la app Miky (Python) y REAPER (ReaScript).\n"
        "--\n"
        "-- Qué hace: mira la carpeta de pedidos, ejecuta comandos de un catálogo\n"
        "-- cerrado y escribe las respuestas. No abre ventanas, no toca el mouse y\n"
        "-- no ejecuta código que venga de afuera.\n"
        "--\n"
        "-- Carpeta de trabajo: %APPDATA%\\Miky\\ipc\n"
        "--   requests/   pedidos de la app\n"
        "--   responses/  respuestas del puente\n"
        "--   status.json latido (para saber si el puente está vivo)\n"
        "\n"
    )
    parts = [header]
    for name in MODULES:
        source = read_module(name)
        source = re.sub(r"MIKY\.VERSION = '[^']*'", f"MIKY.VERSION = '{version}'", source)
        parts.append(f"-- ===== {name} " + "=" * max(0, 60 - len(name)) + "\n")
        parts.append(source)
        parts.append("\n")
    return "".join(parts)


def syntax_check(source: str) -> bool:
    try:
        import lupa
    except ImportError:
        print("(sin lupa: no verifico sintaxis Lua)")
        return True
    lua = lupa.LuaRuntime()
    compiled = lua.eval("function(src, name) return load(src, name) end")(source, "miky_bridge.lua")
    if isinstance(compiled, tuple):
        chunk, error = compiled[0], compiled[1]
    else:
        chunk, error = compiled, ""
    if chunk is None:
        print(f"ERROR de sintaxis Lua: {error}", file=sys.stderr)
        return False
    print("sintaxis Lua OK")
    return True


def main(argv: list[str]) -> int:
    version = project_version()
    check_only = "--check" in argv
    source = build(version)

    if not syntax_check(source):
        return 1
    if check_only:
        return 0

    for path in OUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        print(f"escrito {path.relative_to(ROOT)} ({len(source) / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
