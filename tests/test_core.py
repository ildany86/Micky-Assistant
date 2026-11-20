"""Pruebas del catálogo, el router de comandos directos, la voz y las respuestas."""

from __future__ import annotations

import pytest

from miky import router, speech
from miky.catalog import Catalog, ValidationError
from miky.voice import wake


# ---------------------------------------------------------------- catálogo


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


def test_catalogo_carga(catalog: Catalog) -> None:
    assert len(catalog.all()) >= 35
    ids = catalog.ids()
    assert len(ids) == len(set(ids))
    assert "track.add" in ids
    assert "render.start" in ids


def test_catalogo_nombres_de_herramienta_unicos(catalog: Catalog) -> None:
    tools = [spec.tool_name for spec in catalog.all()]
    assert len(tools) == len(set(tools))
    assert all(tool.replace("_", "").isalnum() for tool in tools)


def test_catalogo_esquema_para_ia(catalog: Catalog) -> None:
    declarations = catalog.function_declarations()
    assert len(declarations) == len(catalog.all())
    for item in declarations:
        assert item["name"]
        assert item["description"]
        assert item["parameters"]["type"] == "object"


def test_validar_argumento_faltante(catalog: Catalog) -> None:
    with pytest.raises(ValidationError):
        catalog.validate("track.add", {})


def test_validar_convierte_numeros(catalog: Catalog) -> None:
    args = catalog.validate("track.set_volume", {"track": "Voz", "db": "-6"})
    assert args["db"] == -6.0
    assert args["track"] == "Voz"


def test_validar_recorta_a_rango(catalog: Catalog) -> None:
    args = catalog.validate("track.set_volume", {"track": "Voz", "db": 100})
    assert args["db"] == 24


def test_validar_booleano_en_texto(catalog: Catalog) -> None:
    args = catalog.validate("track.mute", {"track": "Voz", "state": "sí"})
    assert args["state"] is True
    args = catalog.validate("track.mute", {"track": "Voz", "state": "no"})
    assert args["state"] is False


def test_validar_enum(catalog: Catalog) -> None:
    args = catalog.validate("render.start", {"mode": "stems"})
    assert args["mode"] == "stems"
    with pytest.raises(ValidationError):
        catalog.validate("render.start", {"mode": "stems_y_mezcla"})


def test_validar_descarta_parametros_desconocidos(catalog: Catalog) -> None:
    args = catalog.validate("track.add", {"name": "Guitarra", "colorin": "rojo"})
    assert "colorin" not in args


def test_validar_lista(catalog: Catalog) -> None:
    args = catalog.validate("track.add_many", {"names": ["A", "B"]})
    assert args["names"] == ["A", "B"]


def test_busqueda_por_nombre_de_herramienta(catalog: Catalog) -> None:
    assert catalog.by_tool("track_add").id == "track.add"
    assert catalog.by_tool("no_existe") is None


# ---------------------------------------------------------------- router


@pytest.mark.parametrize(
    ("texto", "comando"),
    [
        ("dale", "transport.play"),
        ("reproducí", "transport.play"),
        ("pará", "transport.stop"),
        ("detené", "transport.stop"),
        ("grabá", "transport.record"),
        ("deshacé", "project.undo"),
        ("guardá", "project.save"),
        ("prendé el metrónomo", "project.set_metronome"),
        ("apagá el click", "project.set_metronome"),
        ("activá el loop", "transport.set_loop"),
    ],
)
def test_router_comandos_simples(texto: str, comando: str) -> None:
    found = router.match(texto)
    assert found is not None, f"«{texto}» debería ser comando directo"
    assert found[0] == comando


@pytest.mark.parametrize(
    ("texto", "comando", "campo", "valor"),
    [
        ("subí la guitarra 2 dB", "track.adjust_volume", "delta_db", 2),
        ("bajá la voz 3 db", "track.adjust_volume", "delta_db", -3),
        ("subile 2 db al bajo", None, "", None),
        ("poné el tempo en 120", "project.set_tempo", "bpm", 120),
        ("silenciá el bajo", "track.mute", "state", True),
    ],
)
def test_router_parametros(texto: str, comando, campo, valor) -> None:
    found = router.match(texto)
    if comando is None:
        assert found is None
        return
    assert found is not None, f"«{texto}» debería ser comando directo"
    assert found[0] == comando
    assert found[1][campo] == valor


def test_router_crear_pista_con_nombre() -> None:
    found = router.match("creá una pista llamada Guitarra")
    assert found is not None
    assert found[0] == "track.add"
    assert found[1]["name"] == "Guitarra"


def test_router_no_adivina_frases_complejas() -> None:
    assert router.match("subí la guitarra 2 dB y después renderizá la mezcla") is None
    assert router.match("abrí el proyecto de ayer") is None
    assert router.match("no me gusta cómo suena la batería, ¿qué puedo hacer?") is None


def test_router_no_captura_varias_ordenes_en_el_nombre() -> None:
    # Este era el bug real: creaba una pista llamada
    # "bateria y activa la grabacioncon la entrada 1".
    assert router.match("crea una pista, nombrala bateria y activa la grabación con la entrada 1") is None


def test_router_limpia_el_verbo_del_nombre() -> None:
    found = router.match("creá una pista nombrala Batería")
    assert found is not None
    assert found[0] == "track.add"
    assert found[1]["name"] == "Batería"


def test_router_render() -> None:
    found = router.match("renderizá la mezcla")
    assert found[0] == "render.start"
    assert found[1]["mode"] == "mix"


def test_router_numeros_en_palabras() -> None:
    assert router.parse_number("dos") == 2
    assert router.parse_number("menos tres") == -3
    assert router.parse_number("dos coma cinco") == 2.5
    assert router.parse_number("veintidos") == 22


# ---------------------------------------------------------------- voz


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Miky, creá una pista", "creá una pista"),
        ("hola miky grabá", "grabá"),
        ("Miqui, pará", "pará"),
        ("Che Miky", ""),
        ("dale Mickey, subí el bajo", "subí el bajo"),
        ("Mike, abrí el mixer", "abrí el mixer"),
        ("Mic, grabá", "grabá"),
        # Formas reales que devolvió el reconocimiento:
        ("Viky, reproducir", "reproducir"),
        ("Biqui el reproducir", "el reproducir"),
        ("MIG.", ""),
        ("Ok miky, renderizá", "renderizá"),
    ],
)
def test_palabra_de_activacion(texto: str, esperado: str) -> None:
    activated, rest = wake.split_wake(texto, "miky")
    assert activated is True
    assert rest == esperado


def test_microfono_no_activa_por_error() -> None:
    # "micrófono" empieza con "mic" pero no es la palabra clave.
    activated, _rest = wake.split_wake("micrófono de la interfaz", "miky")
    assert activated is False


def test_palabras_parecidas_no_activan() -> None:
    for frase in ("mi que el volumen", "muy bueno", "mira la pista", "me gusta"):
        activated, _rest = wake.split_wake(frase, "miky")
        assert activated is False, frase


def test_detecta_respuestas_que_afirman_haber_hecho_algo() -> None:
    from miky.app import _claims_done, _looks_like_action_request

    assert _claims_done("Puse en solo la batería y el bajo.")
    assert _claims_done("Te dejé la pista armada.")
    assert not _claims_done("Podés cargar un ecualizador para darle brillo.")
    assert not _claims_done("")

    assert _looks_like_action_request("quiero que por los auriculares suene solo el bajo")
    assert _looks_like_action_request("dejá el proyecto listo para mastering")
    assert not _looks_like_action_request("¿qué puedo hacer con la batería?")
    assert not _looks_like_action_request("decime cómo mejorar la voz")


def test_pronunciacion_de_reaper() -> None:
    from miky.voice import pronounce

    assert pronounce.apply("REAPER no está abierto") == "Ríper no está abierto"
    assert pronounce.apply("Cargué un reaper") == "Cargué un Ríper"
    # No debe tocar palabras que solo se parecen.
    assert pronounce.apply("renderizá los renders") == "renderizá los renders"


def test_palabra_de_activacion_no_dispara_con_cualquier_cosa() -> None:
    activated, rest = wake.split_wake("creá una pista de guitarra", "miky")
    assert activated is False
    assert rest == ""


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("sí", True),
        ("Sí, dale", True),
        ("dale", True),
        ("confirmo", True),
        ("no", False),
        ("mejor no", False),
        ("cancelalo", False),
        ("no sé", None),
        ("", None),
    ],
)
def test_confirmacion_por_voz(texto: str, esperado) -> None:
    assert wake.parse_yes_no(texto) is esperado


# ---------------------------------------------------------------- respuestas


def test_respuesta_de_un_paso(catalog: Catalog) -> None:
    spec = catalog.get("track.add")
    text = speech.describe_success(spec, {"name": "Guitarra"})
    assert text == "Listo, creé la pista Guitarra."


def test_respuesta_con_numero(catalog: Catalog) -> None:
    spec = catalog.get("track.adjust_volume")
    text = speech.describe_success(spec, {"name": "Bajo", "volume_db": -4.0})
    assert "Bajo" in text
    assert "-4" in text


def test_respuesta_de_varios_pasos(catalog: Catalog) -> None:
    # Dos veces lo mismo se cuenta, no se repite la frase.
    pairs = [
        (catalog.get("track.add"), {"name": "Guitarra"}),
        (catalog.get("track.add"), {"name": "Bajo"}),
    ]
    assert speech.describe_plan(pairs) == "Listo, creé 2 pistas."


def test_respuesta_de_seis_borrados(catalog: Catalog) -> None:
    pairs = [(catalog.get("track.delete"), {"track": name}) for name in "abcdef"]
    assert speech.describe_plan(pairs) == "Listo, borré 6 pistas."


def test_respuesta_de_pasos_distintos(catalog: Catalog) -> None:
    pairs = [
        (catalog.get("track.add"), {"name": "Guitarra"}),
        (catalog.get("fx.add"), {"name": "ReaEQ", "track_name": "Guitarra"}),
    ]
    text = speech.describe_plan(pairs)
    assert text.startswith("Listo: ")
    assert "Guitarra" in text
    assert "ReaEQ" in text


def test_respuesta_de_un_paso_no_cambia(catalog: Catalog) -> None:
    pairs = [(catalog.get("track.add"), {"name": "Guitarra"})]
    assert "Guitarra" in speech.describe_plan(pairs)


def test_respuesta_de_error(catalog: Catalog) -> None:
    spec = catalog.get("track.delete")
    text = speech.describe_failure(spec, "no encontré la pista «Batería»")
    assert text.startswith("No borré nada")


def test_plantilla_con_campo_faltante_no_explota(catalog: Catalog) -> None:
    spec = catalog.get("track.set_volume")
    text = speech.describe_success(spec, {})
    assert isinstance(text, str) and text
