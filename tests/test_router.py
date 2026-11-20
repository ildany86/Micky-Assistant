"""El router convierte pedidos comunes en comandos sin consultar a la IA.

Cada fila es una frase real (o una forma de decirla) y el comando esperado.
Si alguien agrega un patrón nuevo, agrega acá su frase.
"""

from __future__ import annotations

import pytest

from miky import router

CASES: list[tuple[str, str | None]] = [
    # --- transporte
    ("dale", "transport.play"),
    ("reproducí", "transport.play"),
    ("pará", "transport.stop"),
    ("detené la reproducción", "transport.stop"),
    ("pará la grabación", "transport.stop"),
    ("pausá", "transport.pause"),
    ("grabá", "transport.record"),
    ("dale, grabemos", "transport.record"),
    ("andá al inicio", "transport.goto_start"),
    ("volvé al principio del proyecto", "transport.goto_start"),
    ("andá al final", "transport.goto_end"),
    ("andá al compás 5", "transport.set_position"),
    ("anda al compas 12", "transport.set_position"),
    ("andá al marcador estribillo", "transport.goto_marker"),
    ("activá el loop", "transport.set_loop"),
    ("desactivá el loop", "transport.set_loop"),
    # --- proyecto
    ("deshacé", "project.undo"),
    ("rehacé", "project.redo"),
    ("guardá", "project.save"),
    ("guardá el proyecto", "project.save"),
    ("prendé el metrónomo", "project.set_metronome"),
    ("apagá el click", "project.set_metronome"),
    ("poné el tempo en 120", "project.set_tempo"),
    ("ajustá el tiempo de la sesión a 80 BPM", "project.set_tempo"),
    ("renderizá la mezcla", "render.start"),
    ("exportá el proyecto", "render.start"),
    ("renderizá los stems", "render.start"),
    ("exportá las pistas por separado", "render.start"),
    ("renderizá la selección", "render.start"),
    ("exportá a -14 LUFS", "render.start"),
    # --- variantes reales del habla
    ("el volumen de la pista 2, subilo 3 dB", "track.adjust_volume"),
    ("mutear la batería", "track.mute"),
    ("poné mute en la voz", "track.mute"),
    ("dejá el bajo en solo", "track.solo"),
    ("borrá la 3", "track.delete"),
    ("pintá la pista 2 de violeta", "track.set_color"),
    # deshacer / abrir proyecto
    ("deshacé lo último", "project.undo"),
    ("volvé atrás", "project.undo"),
    ("rehacé", "project.redo"),
    ("abrí el proyecto Free From Adiction", "project.open"),
    # frases reales del registro de voz
    ("la pista 23, un decibel más bajo", "track.adjust_volume"),
    ("la batería, un decibel más arriba", "track.adjust_volume"),
    ("agregá 10 pistas de audio", "track.add_many"),
    ("sumale cuatro pistas", "track.add_many"),
    # --- vista
    ("abrí el mixer", "view.mixer"),
    ("mostrame el mezclador", "view.mixer"),
    ("cerrá el mixer", "view.mixer"),
    ("abrí la matriz de ruteo", "view.routing"),
    ("cerrá la ventana de ruteo", "view.routing"),
    # --- pistas
    ("subí la guitarra 2 dB", "track.adjust_volume"),
    ("bajá el volumen de la pista voz 3 decibeles", "track.adjust_volume"),
    ("poné el bajo en -6 dB", "track.set_volume"),
    ("paneá la guitarra a la izquierda", "track.set_pan"),
    ("paneá la voz a -30", "track.set_pan"),
    ("silenciá el bajo", "track.mute"),
    ("desilenciá el bajo", "track.mute"),
    ("solo en la batería", "track.solo"),
    ("sacá el solo de la batería", "track.solo"),
    ("armá la guitarra", "track.arm"),
    ("desarmá la guitarra", "track.arm"),
    ("renombrá la pista 2 como Batería", "track.rename"),
    ("creá una pista llamada Guitarra", "track.add"),
    ("agregá una pista", "track.add"),
    ("borrá la pista 3", "track.delete"),
    ("duplicá la voz", "track.duplicate"),
    ("mandá la batería a las salidas 3 y 4", "track.output"),
    ("sacá las salidas físicas de la batería", "track.output_clear"),
    ("seleccioná la voz", "track.select"),
    # --- plugins
    ("cargá ReaEQ en la voz", "fx.add"),
    ("poné un compresor en la batería", "fx.add"),
    ("insertá ReaComp en la pista bajo", "fx.add"),
    ("sacá el ReaEQ de la voz", "fx.remove"),
    ("bypaseá el compresor en la voz", "fx.bypass"),
    ("¿qué plugins tiene la voz?", "fx.list"),
    # --- envíos
    ("mandá la voz al reverb", "send.add"),
    ("sacá el envío de la voz al reverb", "send.remove"),
    # --- ítems
    ("borrá los ítems seleccionados", "item.delete_selected"),
    ("cortá en el cursor", "item.split_at_cursor"),
    ("poné un marcador", "marker.add"),
    ("poné un marcador llamado coro", "marker.add"),
    # --- estas NO son comando directo: las resuelve la IA
    ("quiero que por los auriculares solo se escuche el bajo y la batería", None),
    ("prepara las dos pistas para grabación", None),
    ("no me gusta como suena la batería", None),
    ("mi que el volumen de la pistada", None),
    ("agregá una pista y ponele un compresor", None),
    ("abrí el mixer y mostrame los ruteos", None),
    ("solo quiero escuchar el bajo", None),
    ("cargá el proyecto", None),
    ("guardá el proyecto como otro", None),
]


@pytest.mark.parametrize(("texto", "esperado"), CASES)
def test_router(texto: str, esperado: str | None) -> None:
    hit = router.match(texto)
    got = hit[0] if hit else None
    assert got == esperado, f"{texto!r}: esperaba {esperado}, obtuve {got} {hit[1] if hit else ''}"


def test_argumentos_de_algunos_casos() -> None:
    assert router.match("subí la guitarra 2 dB")[1] == {"track": "guitarra", "delta_db": 2.0}
    assert router.match("bajá el volumen de la pista voz 3 decibeles")[1] == {
        "track": "voz",
        "delta_db": -3.0,
    }
    assert router.match("poné el bajo en -6 dB")[1] == {"track": "bajo", "db": -6.0}
    assert router.match("renombrá la pista 2 como Batería")[1] == {"track": "2", "name": "Batería"}
    assert router.match("abrí el proyecto Free From Adiction")[1] == {"name": "Free From Adiction"}
    assert router.match("abrí el proyecto el Tema Nuevo")[1] == {"name": "Tema Nuevo"}
    assert router.match("mandá la batería a las salidas 3 y 4")[1]["pair"] == 2
    assert router.match("creá una pista llamada Guitarra")[1] == {"name": "Guitarra"}
    assert router.match("agregá una pista")[1] == {}
    assert router.match("paneá la guitarra a la izquierda")[1]["pan"] == -100.0
    assert router.match("paneá la voz a -30")[1]["pan"] == -30.0


def test_todas_las_reglas_tienen_ejemplo() -> None:
    reglas = router.describe_rules()
    assert len(reglas) >= 45
    for name, example in reglas:
        assert example, name
        hit = router.match(example)
        assert hit is not None, f"la regla {name} no matchea su propio ejemplo: {example!r}"
