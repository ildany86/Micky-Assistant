"""Prueba de humo: todos los módulos importan.

Atrapa errores de sintaxis en archivos que los tests funcionales no tocan (por
ejemplo un módulo de voz que solo se carga cuando hay micrófono).
"""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "miky",
    "miky.__main__",
    "miky.app",
    "miky.bridge",
    "miky.catalog",
    "miky.config",
    "miky.doctor",
    "miky.engine",
    "miky.log",
    "miky.paths",
    "miky.reaper",
    "miky.router",
    "miky.security",
    "miky.speech",
    "miky.ai",
    "miky.ai.gemini",
    "miky.ai.mock",
    "miky.ai.openai",
    "miky.ai.prompt",
    "miky.voice.audio",
    "miky.voice.feedback",
    "miky.voice.pipeline",
    "miky.voice.stt",
    "miky.voice.tts",
    "miky.voice.vad",
    "miky.voice.wake",
    "miky.ui.theme",
    "miky.ui.logo",
    "miky.ui.icon",
    "miky.ui.settings",
    "miky.ui.confirm",
    "miky.ui.shell",
    "miky.ui.tray",
]


@pytest.mark.parametrize("name", MODULES)
def test_importa(name: str) -> None:
    assert importlib.import_module(name) is not None
