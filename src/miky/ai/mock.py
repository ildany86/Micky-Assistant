"""Proveedor de respaldo sin red.

Sirve para dos cosas:
- que la app funcione (con comandos directos) cuando todavía no hay API key;
- que los tests puedan ejercitar el camino completo sin llamar a internet.
"""

from __future__ import annotations

import time
from typing import Any

from ..catalog import Catalog
from .. import router
from . import AIProvider, AIResult

NO_KEY_MESSAGE = (
    "Estoy sin inteligencia conectada. Configurá una API key en Ajustes "
    "para que entienda pedidos complejos; por ahora solo respondo a las órdenes básicas."
)


class MockProvider(AIProvider):
    name = "mock"
    model = "sin-ia"

    def interpret(self, text: str, context: dict[str, Any], catalog: Catalog) -> AIResult:
        started = time.monotonic()
        found = router.match(text)
        latency = (time.monotonic() - started) * 1000.0
        if found:
            command, args, _rule = found
            return AIResult(
                steps=[(command, args)],
                provider=self.name,
                model=self.model,
                latency_ms=latency,
            )
        return AIResult(question=NO_KEY_MESSAGE, provider=self.name, model=self.model)
