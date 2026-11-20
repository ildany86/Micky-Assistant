"""Pruebas del parseo de las respuestas de IA y del modo consejo."""

from __future__ import annotations

import pytest

from miky.ai import AIError
from miky.ai.openai import _parse
from miky.catalog import Catalog
from miky.config import Config
from miky.engine import Executor, Plan


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


def _body(tool: str, args: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": tool, "arguments": args}},
                    ]
                }
            }
        ]
    }


def test_parse_comando(catalog: Catalog) -> None:
    result = _parse(_body("track_add", '{"name": "Guitarra"}'), catalog, "openai", "m", 1.0)
    assert result.steps == [("track.add", {"name": "Guitarra"})]
    assert result.answer == ""


def test_parse_consejo(catalog: Catalog) -> None:
    body = _body("miky_respond", '{"text": "Probá un delay corto y paneá las dos tomas."}')
    result = _parse(body, catalog, "openai", "m", 1.0)
    assert result.answer.startswith("Probá un delay")
    assert result.steps == []


def test_parse_pregunta(catalog: Catalog) -> None:
    body = _body("miky_ask", '{"question": "¿Cuál de las dos guitarras?"}')
    result = _parse(body, catalog, "openai", "m", 1.0)
    assert result.question == "¿Cuál de las dos guitarras?"
    assert result.steps == []


def test_parse_herramienta_desconocida(catalog: Catalog) -> None:
    # Una herramienta inventada por el modelo se ignora; no rompe el pedido.
    result = _parse(_body("borrar_disco", "{}"), catalog, "openai", "m", 1.0)
    assert result.steps == []


def test_consejo_no_ejecuta_nada(catalog: Catalog, tmp_path) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        def call(self, steps, timeout=None, require_alive=True):  # noqa: ANN001
            self.calls.append(steps)
            raise AssertionError("no debería llamar al puente")

    client = FakeClient()
    executor = Executor(client, catalog, Config())
    report = executor.execute(Plan(answer="Usá dos micrófonos en vez de uno."))
    assert report.ok
    assert report.speech == "Usá dos micrófonos en vez de uno."
    assert client.calls == []


def test_build_plan_acepta_respuesta(catalog: Catalog) -> None:
    executor = Executor(None, catalog, Config())
    plan = executor.build_plan([], answer="Hacé esto y aquello.")
    assert plan.answer == "Hacé esto y aquello."
    assert plan.empty
