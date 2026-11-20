"""Las fichas técnicas existen, se buscan bien y llegan al contexto."""

from __future__ import annotations

import pytest

from miky import knowledge


def test_hay_fichas_de_los_temas_basicos() -> None:
    ids = {card.id for card in knowledge.CARDS}
    for tema in ("eq", "dinamica", "niveles", "voz", "bateria", "espacio", "mezcla"):
        assert tema in ids


@pytest.mark.parametrize(
    ("consulta", "esperada"),
    [
        ("¿cómo ecualizo la voz para que no suene nasal?", "eq"),
        ("el compresor me está aplastando la batería", "dinamica"),
        ("¿a cuántos LUFS dejo el master?", "niveles"),
        ("¿qué reverb le pongo a la voz?", "espacio"),
        ("¿cómo empiezo a mezclar el tema?", "mezcla"),
    ],
)
def test_encuentra_la_ficha_correcta(consulta: str, esperada: str) -> None:
    cards = knowledge.relevant(consulta, limit=2)
    assert cards, consulta
    assert esperada in [card.id for card in cards]


def test_sin_tema_no_devuelve_nada() -> None:
    assert knowledge.relevant("abrí el mixer") == []


def test_detecta_consultas_y_no_ordenes() -> None:
    assert knowledge.is_advice_request("¿qué hago con la batería?")
    assert knowledge.is_advice_request("me conviene comprimir el bajo")
    assert knowledge.is_advice_request("la voz suena opaca, ¿qué toco?")
    assert not knowledge.is_advice_request("subí el bajo 2 dB")
    assert not knowledge.is_advice_request("borrá la pista 3")


def test_el_contexto_lleva_los_datos() -> None:
    cards = knowledge.relevant("¿cómo ecualizo la voz?", limit=1)
    payload = knowledge.as_context(cards)
    assert payload and "datos" in payload[0]
    assert any("Hz" in line for line in payload[0]["datos"])


def test_las_fichas_tienen_contenido_y_etiquetas() -> None:
    for card in knowledge.CARDS:
        assert card.title
        assert card.tags
        assert len(card.body) >= 5
        for line in card.body:
            assert line.strip()
