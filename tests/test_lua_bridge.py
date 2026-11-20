"""Pruebas del puente Lua: comandos y protocolo IPC, contra un REAPER simulado."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from lua_harness import LuaHarness


def _set_favorites(harness: LuaHarness, items: list[str], folder: str = "Favoritos") -> None:
    """Escribe un reaper-fxfolders.ini y apunta el REAPER simulado ahí."""
    resource = Path(tempfile.mkdtemp(prefix="miky_fx_")) / "REAPER"
    resource.mkdir(parents=True, exist_ok=True)
    lines = ["[Folder0]"]
    for index, item in enumerate(items):
        lines.append(f"Item{index}={item}")
        lines.append(f"Type{index}=3")
    lines.append(f"Nb={len(items)}")
    lines.extend(["", "[Folders]", "Id0=0", f"Name0={folder}", "NbFolders=1", ""])
    (resource / "reaper-fxfolders.ini").write_text("\n".join(lines), encoding="utf-8")
    harness.lua.execute(f"MOCK.resource_path = [[{resource}]]")


def test_favoritos_de_reaper_se_listan(harness: LuaHarness) -> None:
    _set_favorites(harness, [r"C:\Plugins\Eamut Drums Compressor.vst3"])
    result = harness.run_ok("fx.favorites")
    assert result["count"] == 1
    assert "Eamut Drums Compressor" in result["favorites"][0]


def test_plugin_favorito_se_carga_sin_preguntar(harness: LuaHarness) -> None:
    _set_favorites(harness, [r"C:\Plugins\Eamut Drums Compressor.vst3"])
    harness.run_ok("track.add", {"name": "Batería"})
    result = harness.run_ok("fx.add", {"track": "Batería", "name": "compresor"})
    assert result["from_favorites"] is True
    assert "Eamut Drums Compressor" in result["resolved"]


def test_otra_carpeta_no_cuenta_como_favorito(harness: LuaHarness) -> None:
    _set_favorites(harness, [r"C:\Plugins\Eamut Drums Compressor.vst3"], folder="Mezcla")
    assert harness.run_ok("fx.favorites")["count"] == 0
    harness.run_ok("track.add", {"name": "Batería"})
    error = harness.run_error("fx.add", {"track": "Batería", "name": "compresor"})
    assert error["code"] == "fx_candidates"


def test_sin_archivo_de_favoritos_no_rompe(harness: LuaHarness) -> None:
    assert harness.run_ok("fx.favorites")["count"] == 0


# ---------------------------------------------------------------- catálogo


def test_todos_los_comandos_del_catalogo_tienen_handler(harness: LuaHarness) -> None:
    from pathlib import Path

    catalog_path = Path(__file__).resolve().parent.parent / "src" / "miky" / "data" / "commands.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    declared = {item["id"] for item in catalog["commands"]}
    implemented = set(harness.handler_ids())
    missing = declared - implemented
    assert not missing, f"comandos sin implementar en el puente: {sorted(missing)}"


def test_comandos_internos_disponibles(harness: LuaHarness) -> None:
    ids = set(harness.handler_ids())
    assert {"ping", "state.get", "bridge.info"}.issubset(ids)


# ---------------------------------------------------------------- pistas


def test_crear_pista(harness: LuaHarness) -> None:
    result = harness.run_ok("track.add", {"name": "Guitarra"})
    assert result["index"] == 1
    assert result["name"] == "Guitarra"
    assert result["track_count"] == 1
    assert harness.tracks()[0]["name"] == "Guitarra"


def test_crear_varias_pistas(harness: LuaHarness) -> None:
    result = harness.run_ok("track.add_many", {"names": ["Bombo", "Redo", "Hi-hat"]})
    assert result["count"] == 3
    assert [track["name"] for track in harness.tracks()] == ["Bombo", "Redo", "Hi-hat"]


def test_renombrar_por_nombre_con_acentos(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Batería"})
    result = harness.run_ok("track.rename", {"track": "bateria", "name": "Batería acústica"})
    assert result["name"] == "Batería acústica"


def test_resolver_pista_por_numero(harness: LuaHarness) -> None:
    harness.reset(3)
    result = harness.run_ok("track.set_volume", {"track": "2", "db": -6})
    assert result["index"] == 2
    assert result["volume_db"] == -6


def test_resolver_pista_por_numero_entero(harness: LuaHarness) -> None:
    harness.reset(2)
    result = harness.run_ok("track.mute", {"track": 2, "state": True})
    assert result["index"] == 2
    assert result["mute"] is True


def test_pista_inexistente_da_error_util(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    error = harness.run_error("track.mute", {"track": "bateria"})
    assert error["code"] == "track_not_found"
    assert "Guitarra" in error["message"]


def test_ambiguiedad_de_pista(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra electrica"})
    harness.run_ok("track.add", {"name": "Guitarra acustica"})
    error = harness.run_error("track.mute", {"track": "guitarra"})
    assert error["code"] == "track_ambiguous"


def test_pista_seleccionada_si_no_se_especifica(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    result = harness.run_ok("track.set_pan", {"pan": -50})
    assert result["index"] == 1
    assert result["pan"] == -50


def test_ajustar_volumen_relativo(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Bajo"})
    harness.run_ok("track.set_volume", {"track": "Bajo", "db": -6})
    result = harness.run_ok("track.adjust_volume", {"track": "Bajo", "delta_db": 2})
    assert abs(result["volume_db"] - (-4)) < 0.2


def test_volumen_fuera_de_rango_se_recorta(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Pad"})
    result = harness.run_ok("track.set_volume", {"track": "Pad", "db": 99})
    assert result["volume_db"] == 24


def test_mute_sin_estado_invierte(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    first = harness.run_ok("track.mute", {"track": "Voz"})
    second = harness.run_ok("track.mute", {"track": "Voz"})
    assert first["mute"] is True
    assert second["mute"] is False


def test_armar_pista(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    result = harness.run_ok("track.arm", {"track": "Guitarra", "state": True})
    assert result["armed"] is True


def test_color_de_pista(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Batería"})
    result = harness.run_ok("track.set_color", {"track": "Batería", "color": "rojo"})
    assert result["color"] == "#eb3c3c"


def test_color_hexadecimal(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Pad"})
    result = harness.run_ok("track.set_color", {"track": "Pad", "color": "#3366ff"})
    assert result["color"] == "#3366ff"


def test_color_invalido(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Pad"})
    error = harness.run_error("track.set_color", {"track": "Pad", "color": "turquesa"})
    assert error["code"] == "invalid_arg"


def test_borrar_pista(harness: LuaHarness) -> None:
    harness.reset(2)
    result = harness.run_ok("track.delete", {"track": 1})
    assert result["deleted_index"] == 1
    assert result["track_count"] == 1


def test_duplicar_pista(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    result = harness.run_ok("track.duplicate", {"track": "Voz"})
    assert result["track_count"] == 2
    assert [track["name"] for track in harness.tracks()] == ["Voz", "Voz"]


def test_mover_pista(harness: LuaHarness) -> None:
    harness.run_ok("track.add_many", {"names": ["A", "B", "C"]})
    harness.run_ok("track.move", {"track": "A", "to_index": 3})
    names = [track["name"] for track in harness.tracks()]
    assert names[-1] == "A"


def test_monitoreo(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    result = harness.run_ok("track.set_monitor", {"track": "Voz", "mode": "tape"})
    assert result["monitor"] == "tape"
    assert harness.tracks()[0]["recmon"] == 2


def test_entrada_estereo(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Stereo"})
    harness.run_ok("track.set_input", {"track": "Stereo", "input": "stereo:1"})
    assert harness.tracks()[0]["recinput"] == 1024


def test_entrada_midi(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Synth"})
    harness.run_ok("track.set_input", {"track": "Synth", "input": "midi"})
    assert harness.tracks()[0]["recinput"] == 4096 + (63 << 5)


def test_entrada_invalida(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "X"})
    error = harness.run_error("track.set_input", {"track": "X", "input": "linea"})
    assert error["code"] == "invalid_arg"


# ---------------------------------------------------------------- plugins


def test_cargar_plugin(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    result = harness.run_ok("fx.add", {"track": "Voz", "name": "ReaComp"})
    assert result["index"] == 1
    assert "ReaComp" in result["name"]
    assert result["fx_count"] == 1


def test_cargar_plugin_inexistente(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    error = harness.run_error("fx.add", {"track": "Voz", "name": "NONEXISTENT"})
    assert error["code"] == "fx_not_found"


def test_listar_plugins(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    harness.run_ok("fx.add", {"track": "Voz", "name": "ReaEQ"})
    harness.run_ok("fx.add", {"track": "Voz", "name": "ReaComp"})
    result = harness.run_ok("fx.list", {"track": "Voz"})
    assert len(result["fx"]) == 2
    assert "ReaComp" in result["fx"][1]["name"]


def test_bypass_de_plugin(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    harness.run_ok("fx.add", {"track": "Voz", "name": "ReaComp"})
    result = harness.run_ok("fx.bypass", {"track": "Voz", "fx": "reacomp", "enabled": False})
    assert result["enabled"] is False
    assert harness.tracks()[0]["fx"][0]["enabled"] is False


def test_parametro_por_nombre(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    harness.run_ok("fx.add", {"track": "Voz", "name": "ReaComp"})
    result = harness.run_ok(
        "fx.set_param", {"track": "Voz", "fx": "ReaComp", "param": "threshold", "value": -18}
    )
    assert result["param"] == "Threshold"
    assert result["param_index"] == 1
    params = harness.tracks()[0]["fx"][0]["params"]
    assert -18 in list(params.values())


def test_parametro_inexistente_lista_los_disponibles(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    harness.run_ok("fx.add", {"track": "Voz", "name": "ReaComp"})
    error = harness.run_error(
        "fx.set_param", {"track": "Voz", "fx": "ReaComp", "param": "makeup", "value": 3}
    )
    assert error["code"] == "param_not_found"
    assert "Threshold" in error["message"]


def test_quitar_plugin(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    harness.run_ok("fx.add", {"track": "Voz", "name": "ReaEQ"})
    result = harness.run_ok("fx.remove", {"track": "Voz", "fx": "ReaEQ"})
    assert result["fx_count"] == 0


# ---------------------------------------------------------------- transporte


def test_play_y_stop(harness: LuaHarness) -> None:
    assert harness.run_ok("transport.play")["playing"] is True
    assert harness.run_ok("transport.stop")["playing"] is False


def test_grabar_sin_pista_armada(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    error = harness.run_error("transport.record")
    assert error["code"] == "no_armed_track"


def test_grabar_con_pista_armada(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra", "arm": True})
    result = harness.run_ok("transport.record")
    assert result["recording"] is True
    assert result["armed"] == ["Guitarra"]


def test_posicion_por_compas(harness: LuaHarness) -> None:
    result = harness.run_ok("transport.set_position", {"bar": 3})
    assert abs(result["position"] - 4.0) < 0.01


def test_loop(harness: LuaHarness) -> None:
    result = harness.run_ok("transport.set_loop", {"start": 1.5, "finish": 6.5, "enabled": True})
    assert result["start"] == 1.5
    assert result["enabled"] is True


def test_tempo(harness: LuaHarness) -> None:
    result = harness.run_ok("project.set_tempo", {"bpm": 96})
    assert result["bpm"] == 96


def test_metronomo(harness: LuaHarness) -> None:
    assert harness.run_ok("project.set_metronome", {"enabled": True})["metronome"] is True
    assert harness.run_ok("project.set_metronome", {"enabled": True})["metronome"] is True
    assert harness.run_ok("project.set_metronome", {"enabled": False})["metronome"] is False


def test_proyecto_sin_guardar(harness: LuaHarness) -> None:
    error = harness.run_error("project.save")
    assert error["code"] == "project_unsaved"


def test_guardar_como(harness: LuaHarness) -> None:
    result = harness.run_ok("project.save_as", {"path": "C:\\tmp\\tema.rpp"})
    assert result["saved"] is True
    assert result["path"].endswith("tema.rpp")


# ---------------------------------------------------------------- contenido


def test_marcador(harness: LuaHarness) -> None:
    result = harness.run_ok("marker.add", {"name": "Estribillo", "position": 12.0})
    assert result["position"] == 12.0
    snapshot = harness.run_ok("state.get")
    assert snapshot["markers"][0]["name"] == "Estribillo"


def test_region(harness: LuaHarness) -> None:
    result = harness.run_ok("region.add", {"name": "Coro", "start": 10, "finish": 20})
    assert result["finish"] == 20
    snapshot = harness.run_ok("state.get")
    assert snapshot["regions"][0]["name"] == "Coro"


def test_region_invalida(harness: LuaHarness) -> None:
    error = harness.run_error("region.add", {"name": "X", "start": 10, "finish": 5})
    assert error["code"] == "invalid_arg"


def test_ir_a_marcador(harness: LuaHarness) -> None:
    harness.run_ok("marker.add", {"name": "Estribillo", "position": 30.0})
    result = harness.run_ok("transport.goto_marker", {"name": "estribillo"})
    assert result["position"] == 30.0


def test_marcador_inexistente(harness: LuaHarness) -> None:
    error = harness.run_error("transport.goto_marker", {"name": "Puente"})
    assert error["code"] == "marker_not_found"


def test_render_mezcla(harness: LuaHarness) -> None:
    result = harness.run_ok(
        "render.start",
        {"mode": "mix", "out_dir": "C:\\tmp\\render", "pattern": "mezcla", "format": "wav"},
    )
    assert result["mode"] == "mix"
    assert "render" in result["targets"]
    assert 42230 in harness.commands_run()
    render = harness.mock_state().render
    assert render["RENDER_BOUNDSFLAG"] == 1
    assert render["RENDER_SETTINGS"] == 0


def test_render_stems(harness: LuaHarness) -> None:
    harness.run_ok("render.start", {"mode": "stems", "out_dir": "C:\\tmp\\render"})
    assert harness.mock_state().render["RENDER_SETTINGS"] == 2


def test_render_normalizado(harness: LuaHarness) -> None:
    harness.run_ok("render.start", {"mode": "mix", "out_dir": "C:\\tmp\\r", "normalize_lufs": -14})
    render = harness.mock_state().render
    assert render["RENDER_NORMALIZE"] == 1
    assert abs(render["RENDER_NORMALIZE_TARGET"] - 0.1995) < 0.001


# ---------------------------------------------------------------- pistas parecidas


def test_pista_parecida_copia_todo(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra", "color": "azul", "arm": True})
    harness.run_ok("fx.add", {"track": "Guitarra", "name": "ReaComp"})
    harness.run_ok("fx.add", {"track": "Guitarra", "name": "ReaEQ"})
    harness.run_ok("track.set_input", {"track": "Guitarra", "input": "mono:1"})
    harness.run_ok("track.set_monitor", {"track": "Guitarra", "mode": "normal"})

    result = harness.run_ok("track.add_like", {"track": "Guitarra", "name": "Guitarra 2"})
    assert result["name"] == "Guitarra 2"
    assert result["fx_count"] == 2
    assert result["source"] == "Guitarra"

    tracks = harness.tracks()
    assert [track["name"] for track in tracks] == ["Guitarra", "Guitarra 2"]
    nueva = tracks[1]
    assert nueva["recinput"] == tracks[0]["recinput"] == 0
    assert nueva["recmon"] == 1
    assert nueva["arm"] == 1
    nombres_fx = [fx["name"] for fx in nueva["fx"]]
    assert len(nombres_fx) == 2
    assert "ReaComp" in nombres_fx[0]
    assert "ReaEQ" in nombres_fx[1]


def test_pista_parecida_sin_plugins(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    harness.run_ok("fx.add", {"track": "Voz", "name": "ReaEQ"})
    result = harness.run_ok("track.add_like", {"track": "Voz", "copy_fx": False})
    assert result["fx_count"] == 0
    assert result["name"] == "Voz"


# ---------------------------------------------------------------- envíos


def test_crear_envio(harness: LuaHarness) -> None:
    harness.run_ok("track.add_many", {"names": ["Voz", "Reverb"]})
    result = harness.run_ok("send.add", {"from": "Voz", "to": "Reverb", "level_db": -6})
    assert result["from"] == "Voz"
    assert result["to"] == "Reverb"
    assert result["level_db"] == -6
    tracks = harness.tracks()
    assert len(tracks[0]["sends"]) == 1
    assert tracks[0]["sends"][0]["mode"] == 0


def test_envio_duplicado_avisa(harness: LuaHarness) -> None:
    harness.run_ok("track.add_many", {"names": ["Voz", "Reverb"]})
    harness.run_ok("send.add", {"from": "Voz", "to": "Reverb"})
    error = harness.run_error("send.add", {"from": "Voz", "to": "Reverb"})
    assert error["code"] == "send_exists"


def test_envio_a_si_misma_no(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    error = harness.run_error("send.add", {"from": "Voz", "to": "Voz"})
    assert error["code"] == "invalid_arg"


def test_envio_nivel_y_quitar(harness: LuaHarness) -> None:
    harness.run_ok("track.add_many", {"names": ["Voz", "Reverb"]})
    harness.run_ok("send.add", {"from": "Voz", "to": "Reverb"})
    harness.run_ok("send.set_level", {"from": "Voz", "to": "Reverb", "db": -3})
    tracks = harness.tracks()
    assert abs(tracks[0]["sends"][0]["vol"] - 0.7079) < 0.01
    result = harness.run_ok("send.remove", {"from": "Voz", "to": "Reverb"})
    assert result["sends_left"] == 0
    error = harness.run_error("send.remove", {"from": "Voz", "to": "Reverb"})
    assert error["code"] == "send_not_found"


# ---------------------------------------------------------------- items


def test_recortar_item_entre_marcadores(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.run_ok("marker.add", {"name": "Estrofa", "position": 2.0})
    harness.run_ok("marker.add", {"name": "Estribillo", "position": 6.0})
    harness.lua.eval("MOCK.add_item(1, 0.0, 10.0, true)")

    result = harness.run_ok(
        "item.keep_between", {"start_marker": "Estrofa", "end_marker": "Estribillo"}
    )
    assert result["kept"] == 1
    assert result["trimmed"] == 2
    assert result["start"] == 2.0
    assert result["finish"] == 6.0

    items = harness.lua.eval("MOCK.items")
    assert len(items) == 1
    assert items[1]["pos"] == 2.0
    assert items[1]["len"] == 4.0
    assert items[1]["selected"] is True


def test_recortar_con_tiempos(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.lua.eval("MOCK.add_item(1, 0.0, 10.0, true)")
    result = harness.run_ok("item.keep_between", {"start": 3.0, "end": 4.0})
    assert result["kept"] == 1
    items = harness.lua.eval("MOCK.items")
    assert items[1]["pos"] == 3.0
    assert items[1]["len"] == 1.0


def test_recortar_sin_seleccion(harness: LuaHarness) -> None:
    error = harness.run_error("item.keep_between", {"start": 1.0, "end": 2.0})
    assert error["code"] == "item_required"


def test_recortar_fuera_de_rango(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.lua.eval("MOCK.add_item(1, 0.0, 2.0, true)")
    error = harness.run_error("item.keep_between", {"start": 5.0, "end": 6.0})
    assert error["code"] == "item_out_of_range"


def test_recortar_marcador_inexistente(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.lua.eval("MOCK.add_item(1, 0.0, 10.0, true)")
    error = harness.run_error(
        "item.keep_between", {"start_marker": "NoExiste", "end": 6.0}
    )
    assert error["code"] == "marker_not_found"


def test_cortar_item_en_el_cursor(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.lua.eval("MOCK.add_item(1, 0.0, 10.0, true)")
    harness.run_ok("transport.set_position", {"seconds": 4.0})
    result = harness.run_ok("item.split_at_cursor")
    assert result["splits"] == 1
    items = harness.lua.eval("MOCK.items")
    assert len(items) == 2
    assert items[1]["len"] == 4.0


def test_borrar_items_seleccionados(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.lua.eval("MOCK.add_item(1, 0.0, 5.0, true)")
    harness.lua.eval("MOCK.add_item(1, 6.0, 2.0, false)")
    result = harness.run_ok("item.delete_selected")
    assert result["deleted"] == 1
    assert len(harness.lua.eval("MOCK.items")) == 1


def test_estado_incluye_plugins_y_entrada(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.run_ok("fx.add", {"track": "Guitarra", "name": "ReaComp"})
    harness.run_ok("track.set_input", {"track": "Guitarra", "input": "mono:1"})
    snapshot = harness.run_ok("state.get")
    track = snapshot["tracks"][0]
    assert len(track["fx"]) == 1
    assert "ReaComp" in track["fx"][0]
    assert track["input"] == "mono:1"
    assert track["monitor"] == "off"
    assert track["sends"] == 0


def test_render_no_pisa_sin_permiso(harness: LuaHarness, tmp_path) -> None:
    import json as json_module
    from pathlib import Path

    out_dir = tmp_path / "salida"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "mezcla.wav").write_text("render viejo", encoding="utf-8")

    error = harness.run_error(
        "render.start", {"mode": "mix", "out_dir": str(out_dir), "pattern": "mezcla"}
    )
    assert error["code"] == "render_exists"
    assert "mezcla.wav" in error["message"]
    assert (out_dir / "mezcla.wav").exists()


def test_render_pisa_con_permiso(harness: LuaHarness, tmp_path) -> None:
    out_dir = tmp_path / "salida2"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "mezcla.wav"
    target.write_text("render viejo", encoding="utf-8")

    result = harness.run_ok(
        "render.start",
        {"mode": "mix", "out_dir": str(out_dir), "pattern": "mezcla", "overwrite": True},
    )
    assert result["overwritten"] is True
    assert not target.exists()  # el mock no renderiza, pero el archivo se borró antes
    assert 42230 in harness.commands_run()


# ---------------------------------------------------------------- plugins por descripción


def test_plugin_por_descripcion_unica(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Batería"})
    result = harness.run_ok(
        "fx.add", {"track": "Batería", "name": "compresor estilo bus de SSL"}
    )
    assert "Bus Compressor" in result["name"]
    assert result["requested"] == "compresor estilo bus de SSL"


def test_plugin_por_marca_pultec(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    result = harness.run_ok("fx.add", {"track": "Voz", "name": "eq tipo pultec"})
    assert "Pultec" in result["name"]


def test_plugin_por_marca_fabfilter(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    result = harness.run_ok("fx.add", {"track": "Voz", "name": "ecualizador de FabFilter"})
    assert "Pro-Q" in result["name"]


def test_plugin_ambiguo_ofrece_opciones(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    error = harness.run_error("fx.add", {"track": "Voz", "name": "ecualizador"})
    assert error["code"] == "fx_candidates"
    candidates = error["candidates"]
    assert len(candidates) >= 2
    assert any("Pro-Q" in name for name in candidates)


def test_plugin_compresor_encuentra_reacomp(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Voz"})
    error = harness.run_error("fx.add", {"track": "Voz", "name": "compresor"})
    assert error["code"] == "fx_candidates"
    assert any("ReaComp" in name for name in error["candidates"])


# ---------------------------------------------------------------- vista


def test_mezclador(harness: LuaHarness) -> None:
    result = harness.run_ok("view.mixer", {"visible": True})
    assert result["mixer_visible"] is True
    assert result["state_text"] == "mostrado"
    result = harness.run_ok("view.mixer")
    assert result["mixer_visible"] is False
    assert result["state_text"] == "oculto"


def test_salidas_fisicas_de_una_pista(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Batería"})
    harness.run_ok("track.add", {"name": "Bajo"})

    result = harness.run_ok("track.output", {"track": "Batería", "pair": 2, "level_db": -3})
    assert result["channels"] == "3/4"
    assert result["outputs_total"] == 1
    assert result["level_db"] == -3

    harness.run_ok("track.output", {"track": "Bajo", "pair": 2})
    error = harness.run_error("track.output", {"track": "Batería", "pair": 2})
    assert error["code"] == "output_exists"

    snapshot = harness.run_ok("state.get")
    assert snapshot["audio"]["outputs"]["count"] == 4
    bateria = next(track for track in snapshot["tracks"] if track["name"] == "Batería")
    assert bateria["outputs"] == 1

    cleared = harness.run_ok("track.output_clear", {"track": "Batería"})
    assert cleared["removed"] == 1
    snapshot = harness.run_ok("state.get")
    bateria = next(track for track in snapshot["tracks"] if track["name"] == "Batería")
    assert bateria["outputs"] == 0


def test_buscar_plugins_instalados(harness: LuaHarness) -> None:
    result = harness.run_ok("fx.search", {"query": "compresor"})
    assert result["count"] >= 1
    assert any("Comp" in name for name in result["candidates"])
    error = harness.run_error("fx.search", {"query": "zzzz"})
    assert error["code"] == "fx_not_found"


def test_listar_plugins_instalados(harness: LuaHarness) -> None:
    result = harness.run_ok("fx.installed", {"limit": 2})
    assert result["count"] >= 2
    assert len(result["names"]) == 2
    assert result["truncated"] is True
    assert "Cockos" in result["vendors"]


def test_ventana_de_ruteo(harness: LuaHarness) -> None:
    harness.run_ok("view.routing")
    assert harness.mock_state().routing is True
    harness.run_ok("view.routing")
    assert harness.mock_state().routing is False


# ---------------------------------------------------------------- estado


def test_snapshot_completo(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra", "color": "azul"})
    harness.run_ok("marker.add", {"name": "Intro", "position": 0})
    snapshot = harness.run_ok("state.get")
    assert snapshot["project"]["track_count"] == 1
    assert snapshot["tracks"][0]["name"] == "Guitarra"
    assert snapshot["tracks"][0]["color"] == "#4678eb"
    assert snapshot["transport"]["playing"] is False
    assert snapshot["selected_tracks"] == [1]
    assert snapshot["marker_count"] == 1


def test_comando_desconocido(harness: LuaHarness) -> None:
    error = harness.run_error("track.explode", {})
    assert error["code"] == "unknown_command"


def test_undo_por_comando(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    assert "Crear pista" in harness.undo_descriptions()


def test_transporte_no_genera_undo(harness: LuaHarness) -> None:
    before = len(harness.undo_descriptions())
    harness.run_ok("transport.play")
    assert len(harness.undo_descriptions()) == before


# ---------------------------------------------------------------- IPC


def test_ipc_ida_y_vuelta(harness: LuaHarness) -> None:
    harness.write_request(
        "m1",
        {
            "v": 1,
            "id": "m1",
            "steps": [
                {"cmd": "track.add", "args": {"name": "Guitarra"}},
                {"cmd": "track.add", "args": {"name": "Bajo"}},
            ],
        },
    )
    harness.pump()
    response = harness.read_response("m1")
    assert response["ok"] is True
    assert len(response["results"]) == 2
    assert response["results"][1]["result"]["name"] == "Bajo"
    assert not (harness.request_dir() / "m1.req.json").exists()
    assert len(harness.tracks()) == 2


def test_ipc_error_parcial(harness: LuaHarness) -> None:
    harness.write_request(
        "m2",
        {
            "v": 1,
            "id": "m2",
            "steps": [
                {"cmd": "track.add", "args": {"name": "Guitarra"}},
                {"cmd": "track.mute", "args": {"track": "NoExiste"}},
                {"cmd": "track.add", "args": {"name": "No se ejecuta"}},
            ],
        },
    )
    harness.pump()
    response = harness.read_response("m2")
    assert response["ok"] is False
    assert response["error"]["step"] == 2
    assert response["error"]["code"] == "track_not_found"
    assert len(response["results"]) == 2  # el tercero no se ejecutó
    assert len(harness.tracks()) == 1


def test_ipc_json_invalido(harness: LuaHarness) -> None:
    harness.request_dir().mkdir(parents=True, exist_ok=True)
    (harness.request_dir() / "m3.req.json").write_text("{esto no es json", encoding="utf-8")
    harness.pump()
    response = harness.read_response("m3")
    assert response["ok"] is False
    assert response["error"]["code"] == "bad_request"


def test_ipc_lote_vacio(harness: LuaHarness) -> None:
    harness.write_request("m4", {"v": 1, "id": "m4", "steps": []})
    harness.pump()
    response = harness.read_response("m4")
    assert response["ok"] is False
    assert response["error"]["code"] == "bad_request"


def test_ipc_sin_pedidos_no_rompe(harness: LuaHarness) -> None:
    harness.pump()
    harness.pump()


def test_latido_de_estado(harness: LuaHarness) -> None:
    harness.run_ok("track.add", {"name": "Guitarra"})
    harness.write_status()
    status = json.loads(harness.status_path().read_text(encoding="utf-8"))
    assert status["protocol"] == 1
    assert status["bridge"]
    assert status["busy"] is False
    assert status["command_count"] > 10


def test_nombres_de_archivo_peligrosos_ignorados(harness: LuaHarness) -> None:
    harness.request_dir().mkdir(parents=True, exist_ok=True)
    (harness.request_dir() / "..req.json").write_text("{}", encoding="utf-8")
    harness.pump()  # no debe explotar
