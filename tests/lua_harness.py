"""Arnés para probar el código Lua del puente sin abrir REAPER.

Carga `tests/lua/mock_reaper.lua` (un REAPER en memoria) y los módulos reales de
`reaper/src/`, y permite ejecutar comandos o simular el ciclo completo del IPC
por archivos.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

lupa = pytest.importorskip("lupa")
from lupa import LuaRuntime  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LUA_SRC = ROOT / "reaper" / "src"
MOCK_LUA = ROOT / "tests" / "lua" / "mock_reaper.lua"

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
]


def _is_lua_table(value: Any) -> bool:
    return hasattr(value, "keys") and hasattr(value, "items") and type(value).__name__.endswith("Table")


def to_python(value: Any) -> Any:
    """Convierte tablas Lua a dict/list de Python."""
    if _is_lua_table(value):
        keys = list(value.keys())
        if keys and all(isinstance(key, int) and key > 0 for key in keys) and set(keys) == set(
            range(1, len(keys) + 1)
        ):
            return [to_python(value[key]) for key in range(1, len(keys) + 1)]
        return {str(key): to_python(value[key]) for key in keys}
    return value


class LuaHarness:
    def __init__(self, appdata: Path) -> None:
        os.environ["APPDATA"] = str(appdata)
        self.appdata = appdata
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("MIKY = {}")

        mock_source = MOCK_LUA.read_text(encoding="utf-8")
        self.reaper = self.lua.execute(mock_source)
        self.lua.globals().reaper = self.reaper
        self.reaper.EnumerateFiles = self._enumerate_files

        for name in MODULES:
            source = (LUA_SRC / "miky" / name).read_text(encoding="utf-8")
            self.lua.execute(source)

        self._run_chunk = self.lua.eval(
            "function(cmd, args) return pcall(MIKY.registry.run_with_undo, {cmd = cmd, args = args}) end"
        )

    # ---------- utilidades ----------

    def _enumerate_files(self, path, index):
        if int(index) == -1:
            return None
        try:
            names = sorted(os.listdir(str(path)))
        except OSError:
            return None
        if 0 <= int(index) < len(names):
            return names[int(index)]
        return None

    def run(self, command: str, args: dict[str, Any] | None = None) -> tuple[bool, Any]:
        lua_args = self._to_lua(args or {})
        ok, value = self._run_chunk(command, lua_args)
        return bool(ok), to_python(value)

    def _to_lua(self, value: Any) -> Any:
        """Convierte dicts y listas de Python (anidados) a tablas Lua."""
        if isinstance(value, dict):
            return self.lua.table_from({key: self._to_lua(item) for key, item in value.items()})
        if isinstance(value, (list, tuple)):
            return self.lua.table_from([self._to_lua(item) for item in value])
        return value

    def run_ok(self, command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        ok, value = self.run(command, args)
        assert ok, f"{command} falló: {value}"
        return value or {}

    def run_error(self, command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        ok, value = self.run(command, args)
        assert not ok, f"{command} debía fallar y devolvió {value}"
        return value or {}

    def reset(self, tracks: int = 0) -> None:
        self.lua.eval(f"MOCK.reset({tracks})")

    def mock_state(self) -> Any:
        return self.lua.eval("MOCK")

    def tracks(self) -> list[dict[str, Any]]:
        tracks = to_python(self.lua.eval("MOCK.tracks"))
        return tracks if isinstance(tracks, list) else []

    def undo_descriptions(self) -> list[str]:
        value = to_python(self.lua.eval("MOCK.undo_descriptions"))
        return value if isinstance(value, list) else []

    def commands_run(self) -> list[int]:
        value = to_python(self.lua.eval("MOCK.commands"))
        return value if isinstance(value, list) else []

    def handler_ids(self) -> list[str]:
        table = self.lua.eval("MIKY.registry.list()")
        return [str(value) for value in table.values()]

    # ---------- IPC ----------

    def setup_ipc(self) -> None:
        self.request_dir().mkdir(parents=True, exist_ok=True)
        self.response_dir().mkdir(parents=True, exist_ok=True)
        self.lua.execute("MIKY.ipc.setup()")

    def pump(self) -> None:
        self.lua.execute("MIKY.ipc.pump()")

    def write_status(self) -> None:
        self.lua.execute("MIKY.ipc.write_status()")

    def request_dir(self) -> Path:
        return self.appdata / "Miky" / "ipc" / "requests"

    def response_dir(self) -> Path:
        return self.appdata / "Miky" / "ipc" / "responses"

    def status_path(self) -> Path:
        return self.appdata / "Miky" / "ipc" / "status.json"

    def write_request(self, request_id: str, payload: dict[str, Any]) -> Path:
        self.request_dir().mkdir(parents=True, exist_ok=True)
        path = self.request_dir() / f"{request_id}.req.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def read_response(self, request_id: str) -> dict[str, Any]:
        path = self.response_dir() / f"{request_id}.res.json"
        assert path.exists(), f"no hay respuesta {path}"
        return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def harness(tmp_path: Path) -> LuaHarness:
    instance = LuaHarness(tmp_path)
    instance.reset(0)
    instance.setup_ipc()
    return instance
