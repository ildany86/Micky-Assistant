"""El corrector arregla marcas y nombres propios sin comerse palabras."""

from __future__ import annotations

import pytest

from miky.voice.correct import correct_text

TERMS = ["Eamut", "MonitorCorrect", "Guitar Rig", "Batería", "ReaEQ", "SSL Comp"]


@pytest.mark.parametrize(
    ("dicho", "esperado"),
    [
        ("inserta el plugin de e amut monitor correct en la pista",
         "inserta el plugin de Eamut MonitorCorrect en la pista"),
        ("insertar el efecto guitar rig", "insertar el efecto Guitar Rig"),
        ("subi la bateria 2 db", "subi la Batería 2 db"),
        ("poné reaec en la voz", "poné ReaEQ en la voz"),
        ("el monitorcorrect en el master", "el MonitorCorrect en el master"),
        ("poné el ssl comp en la voz", "poné el SSL Comp en la voz"),
    ],
)
def test_corrige_marcas(dicho: str, esperado: str) -> None:
    assert correct_text(dicho, TERMS)[0] == esperado


def test_variantes_dificiles_van_por_regla_explicita() -> None:
    # "eamoot" está a dos letras: no se adivina, se declara en voice.corrections.
    dicho = "carga el eamoot en el master"
    assert correct_text(dicho, TERMS)[0] == dicho
    salida, _ = correct_text(dicho, TERMS, ["eamoot=Eamut"])
    assert salida == "carga el Eamut en el master"


@pytest.mark.parametrize(
    "texto",
    [
        "subile el volumen a la pista de bajo",
        "esto no tiene nada que corregir",
        "la pista 3 de bajo",
        "poné el ssl con en la voz",  # "con" no es "comp"
    ],
)
def test_no_toca_lo_que_esta_bien(texto: str) -> None:
    assert correct_text(texto, TERMS)[0] == texto


def test_no_se_come_palabras_vecinas() -> None:
    # Antes "la bateria" se reemplazaba por "Batería" y se perdía el artículo.
    salida, _cambios = correct_text("subí la bateria", TERMS)
    assert salida == "subí la Batería"


def test_reglas_explicitas_del_usuario() -> None:
    salida, cambios = correct_text("ponele el compresor de waves", TERMS, ["compresor de waves=Waves Compressor"])
    assert "Waves Compressor" in salida
    assert cambios


def test_vocabulario_vacio_no_cambia_nada() -> None:
    texto = "cargá el plugin en la voz"
    assert correct_text(texto, [])[0] == texto


def test_texto_vacio() -> None:
    assert correct_text("", TERMS) == ("", [])
