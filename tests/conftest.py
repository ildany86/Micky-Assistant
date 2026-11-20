"""Configuración de pytest: fixture compartido del puente Lua."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from lua_harness import LuaHarness  # noqa: E402


@pytest.fixture()
def harness(tmp_path: Path) -> LuaHarness:
    instance = LuaHarness(tmp_path)
    instance.reset(0)
    instance.setup_ipc()
    return instance
