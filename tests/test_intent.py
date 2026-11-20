"""Clasificación de intención: qué herramientas se le mandan a la IA."""

from __future__ import annotations

import pytest

from miky import intent
from miky.catalog import Catalog


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.mark.parametrize(
    ("texto", "familia"),
    [
        ("cargá un compresor en la voz", "fx"),
        ("abrí el mixer", "vista"),
        ("subí el bajo 2 dB", "pista_nivel"),
        ("poné el tempo en 120", "proyecto"),
        ("borrá la pista 3", "pista_crear"),
        ("mandá la batería a las salidas 3 y 4", "envio"),
        ("renderizá la mezcla", "render"),
        ("poné un marcador en el estribillo", "marcador"),
        ("cortá el ítem en el cursor", "item"),
    ],
)
def test_familia_detectada(texto: str, familia: str) -> None:
    assert familia in intent.families_for(texto)


def test_pedido_sin_familia_usa_todo(catalog: Catalog) -> None:
    assert intent.commands_for_text("hola, ¿cómo andás?") is None
    assert catalog.subset(None) is catalog


def test_el_subconjunto_es_chico_y_trae_lo_necesario(catalog: Catalog) -> None:
    ids = intent.commands_for_text("cargá un compresor en la voz")
    assert ids is not None
    subset = catalog.subset(ids)
    assert len(subset.all()) < 15
    assert subset.get("fx.add") is not None
    assert subset.get("fx.remove") is not None
    # Los comandos transversales siempre viajan.
    assert subset.get("project.undo") is not None
    assert subset.get("transport.stop") is not None
    # miky_ask/miky_respond no están en el catálogo: las agrega el proveedor.


def test_familias_se_suman(catalog: Catalog) -> None:
    names = intent.families_for("creá una pista y cargale un compresor")
    assert "pista_crear" in names
    assert "fx" in names
    ids = intent.commands_for_text("creá una pista y cargale un compresor")
    subset = catalog.subset(ids)
    assert subset.get("track.add") is not None
    assert subset.get("fx.add") is not None


def test_no_ofrece_comandos_que_no_existen(catalog: Catalog) -> None:
    for familia in intent.FAMILIES:
        for command in familia.commands:
            assert catalog.get(command) is not None, f"{familia.name}: {command} no existe"


def test_los_comandos_del_core_existen(catalog: Catalog) -> None:
    for command in intent.CORE:
        # "miky_ask" y "miky_respond" son herramientas de la IA, no del catálogo.
        if command.startswith("miky_"):
            continue
        assert catalog.get(command) is not None
