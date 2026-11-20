"""Pruebas del motor de ejecución y del cliente del puente, sin REAPER."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from miky.bridge import BridgeClient, BridgeNotRunning, BridgeReply, BridgeTimeout, StepOutcome
from miky.catalog import Catalog
from miky.config import Config
from miky.engine import Executor, Plan, PlanError


class FakeClient:
    """Cliente falso: registra lo que le mandan y devuelve lo que se le pide."""

    def __init__(self, reply: BridgeReply | None = None, error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[list[tuple[str, dict]]] = []

    def call(self, steps, timeout=None, require_alive=True):  # noqa: ANN001
        normalized = [(command, args) for command, args in steps]
        self.calls.append(normalized)
        if self.error is not None:
            raise self.error
        if self.reply is not None:
            return self.reply
        # Respuesta del tamaño justo: una salida por paso.
        return ok_reply(*[{} for _ in normalized])


@pytest.fixture()
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture()
def config() -> Config:
    cfg = Config()
    cfg.voice.speak_replies = False
    return cfg


def ok_reply(*results: dict) -> BridgeReply:
    steps = [
        StepOutcome(command="paso", ok=True, result=result) for result in results
    ]
    return BridgeReply(request_id="x", ok=True, steps=steps)


# ---------------------------------------------------------------- planes


def test_plan_arma_pasos_validos(catalog: Catalog, config: Config) -> None:
    executor = Executor(FakeClient(), catalog, config)
    plan = executor.build_plan([("track.add", {"name": "Guitarra", "colorin": "x"})])
    assert len(plan.steps) == 1
    assert plan.steps[0].args == {"name": "Guitarra"}


def test_plan_rechaza_comando_desconocido(catalog: Catalog, config: Config) -> None:
    executor = Executor(FakeClient(), catalog, config)
    with pytest.raises(PlanError):
        executor.build_plan([("track.explode", {})])


def test_plan_rechaza_argumentos_invalidos(catalog: Catalog, config: Config) -> None:
    executor = Executor(FakeClient(), catalog, config)
    with pytest.raises(PlanError):
        executor.build_plan([("track.add", {})])


def test_plan_respeta_el_maximo_de_pasos(catalog: Catalog, config: Config) -> None:
    config.ai.max_steps = 2
    executor = Executor(FakeClient(), catalog, config)
    with pytest.raises(PlanError):
        executor.build_plan([("track.add", {"name": str(index)}) for index in range(3)])


def test_render_completa_carpeta_y_patron(catalog: Catalog, config: Config, tmp_path: Path, monkeypatch) -> None:
    config.render.default_dir = str(tmp_path / "renders")
    config.render.default_pattern = "$project-mezcla"
    executor = Executor(FakeClient(), catalog, config)
    plan = executor.build_plan([("render.start", {"mode": "mix"})])
    args = plan.steps[0].args
    assert args["out_dir"] == str(tmp_path / "renders")
    assert args["pattern"] == "$project-mezcla"
    assert (tmp_path / "renders").is_dir()


def test_render_respeta_carpetas_permitidas(catalog: Catalog, config: Config, tmp_path: Path) -> None:
    config.safety.allowed_render_roots = (str(tmp_path / "permitida"),)
    executor = Executor(FakeClient(), catalog, config)
    with pytest.raises(PlanError):
        executor.build_plan([("render.start", {"mode": "mix", "out_dir": str(tmp_path / "otra")})])


# ---------------------------------------------------------------- ejecución


def test_ejecucion_exitosa(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({"name": "Guitarra", "index": 1, "track_count": 1}))
    executor = Executor(client, catalog, config)
    plan = executor.build_plan([("track.add", {"name": "Guitarra"})])
    report = executor.execute(plan)
    assert report.ok
    assert "Guitarra" in report.speech
    assert client.calls == [[("track.add", {"name": "Guitarra"})]]


def test_error_del_puente_se_explica(catalog: Catalog, config: Config) -> None:
    reply = BridgeReply(
        request_id="x",
        ok=False,
        steps=[
            StepOutcome(
                command="track.mute",
                ok=False,
                error={"code": "track_not_found", "message": "no encontré la pista «Teclados»"},
            )
        ],
        error={"code": "track_not_found", "message": "no encontré la pista «Teclados»"},
    )
    executor = Executor(FakeClient(reply), catalog, config)
    plan = executor.build_plan([("track.mute", {"track": "Teclados"})])
    report = executor.execute(plan)
    assert not report.ok
    assert "No pude" in report.speech
    assert "Teclados" in report.speech


def test_error_parcial_avisa_lo_que_si_paso(catalog: Catalog, config: Config) -> None:
    reply = BridgeReply(
        request_id="x",
        ok=False,
        steps=[
            StepOutcome(command="track.add", ok=True, result={"name": "Guitarra", "index": 1}),
            StepOutcome(command="track.mute", ok=False, error={"code": "track_not_found", "message": "no está"}),
        ],
        error={"code": "track_not_found", "message": "no está"},
    )
    executor = Executor(FakeClient(reply), catalog, config)
    plan = executor.build_plan(
        [("track.add", {"name": "Guitarra"}), ("track.mute", {"track": "X"})]
    )
    report = executor.execute(plan)
    assert not report.ok
    assert report.speech.startswith("Hice parte")
    assert report.executed == 1


def test_puente_caido_se_informa(catalog: Catalog, config: Config) -> None:
    executor = Executor(FakeClient(error=BridgeNotRunning("no está")), catalog, config)
    plan = executor.build_plan([("transport.play", {})])
    report = executor.execute(plan)
    assert not report.ok
    assert "REAPER no está abierto" in report.speech
    assert "abrí REAPER" in report.speech


def test_timeout_se_informa(catalog: Catalog, config: Config) -> None:
    executor = Executor(FakeClient(error=BridgeTimeout("tarde")), catalog, config)
    plan = executor.build_plan([("transport.play", {})])
    report = executor.execute(plan)
    assert not report.ok
    assert "no respondió" in report.speech.lower()


def test_confirmacion_denegada_no_ejecuta(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({}))
    preguntas: list[str] = []

    def confirmar(question: str, step) -> bool:  # noqa: ANN001
        preguntas.append(question)
        return False

    executor = Executor(client, catalog, config, confirm=confirmar)
    plan = executor.build_plan([("track.delete", {"track": "Guitarra"})])
    report = executor.execute(plan)
    assert not report.ok
    assert report.speech == "Cancelado."
    assert client.calls == []
    assert preguntas and "Borro" in preguntas[0]


def test_confirmacion_aceptada_ejecuta(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({"deleted_name": "Guitarra", "deleted_index": 1}))
    executor = Executor(client, catalog, config, confirm=lambda question, step: True)
    plan = executor.build_plan([("track.delete", {"track": "Guitarra"})])
    report = executor.execute(plan)
    assert report.ok
    assert client.calls


def test_confirmacion_se_puede_desactivar_en_config(catalog: Catalog, config: Config) -> None:
    config.safety.confirm_destructive = False
    client = FakeClient(ok_reply({"deleted_name": "X", "deleted_index": 1}))

    def confirmar(question: str, step) -> bool:  # noqa: ANN001
        raise AssertionError("no debería preguntar")

    executor = Executor(client, catalog, config, confirm=confirmar)
    plan = executor.build_plan([("track.delete", {"track": "X"})])
    assert executor.execute(plan).ok


def test_borrados_por_indice_se_ordenan_de_mayor_a_menor(catalog: Catalog, config: Config) -> None:
    executor = Executor(FakeClient(), catalog, config)
    plan = executor.build_plan(
        [
            ("transport.stop", {}),
            ("track.delete", {"track": "1"}),
            ("track.delete", {"track": "2"}),
            ("track.delete", {"track": "3"}),
        ]
    )
    orden = [step.args.get("track") for step in plan.steps if step.command == "track.delete"]
    assert orden == ["3", "2", "1"]
    # El resto de los pasos conserva su lugar.
    assert plan.steps[0].command == "transport.stop"


def test_borrados_por_nombre_no_se_reordenan(catalog: Catalog, config: Config) -> None:
    executor = Executor(FakeClient(), catalog, config)
    plan = executor.build_plan(
        [("track.delete", {"track": "voz"}), ("track.delete", {"track": "bajo"})]
    )
    assert [step.args["track"] for step in plan.steps] == ["voz", "bajo"]


def test_router_rechaza_varias_pistas() -> None:
    from miky import router

    for frase in (
        "prepara las dos pistas para grabación",
        "armá todas las pistas",
        "silenciá todos los canales",
    ):
        assert router.match(frase) is None, frase


def test_grabar_pregunta_antes_y_arranca_en_silencio(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({"recording": True}))
    preguntas: list[str] = []

    def confirmar(question: str, step) -> bool:  # noqa: ANN001
        preguntas.append(question)
        return True

    executor = Executor(client, catalog, config, confirm=confirmar)
    plan = executor.build_plan([("transport.record", {})])
    report = executor.execute(plan)
    assert report.ok
    assert report.speech == ""  # no habla: ya está grabando
    assert preguntas == ["¿Estás listo para grabar?"]
    assert client.calls == [[("transport.record", {})]]


def test_grabar_cancelado_no_graba(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({"recording": True}))
    executor = Executor(client, catalog, config, confirm=lambda question, step: False)
    plan = executor.build_plan([("transport.record", {})])
    report = executor.execute(plan)
    assert not report.ok
    assert report.speech == "Cancelado. No grabé nada."
    assert client.calls == []


def test_grabar_con_pasos_previos_habla_antes(catalog: Catalog, config: Config) -> None:
    client = FakeClient()
    dicho: list[str] = []
    executor = Executor(
        client,
        catalog,
        config,
        confirm=lambda question, step: True,
        say=dicho.append,
    )
    plan = executor.build_plan([("project.set_metronome", {"enabled": True}), ("transport.record", {})])
    report = executor.execute(plan)
    assert report.ok
    assert report.speech == ""
    assert len(client.calls) == 2  # primero el metrónomo, después la grabación
    assert said_metronome(dicho)


def said_metronome(dicho: list[str]) -> bool:
    return any("metrónomo" in text for text in dicho)


def test_grabar_sin_confirmacion_ejecuta_normal(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({"recording": True}))
    executor = Executor(client, catalog, config)
    plan = executor.build_plan([("transport.record", {})])
    report = executor.execute(plan)
    assert report.ok
    assert report.speech  # en consola sí avisa


def test_render_avisa_antes_de_arrancar(catalog: Catalog, config: Config) -> None:
    client = FakeClient()
    dicho: list[str] = []
    executor = Executor(
        client,
        catalog,
        config,
        confirm=lambda question, step: True,
        say=dicho.append,
    )
    plan = executor.build_plan([("render.start", {"mode": "mix"})])
    report = executor.execute(plan)
    assert report.ok
    assert any("Renderizando" in text for text in dicho), dicho
    assert report.speech == "Listo, terminó el render."


def test_borrar_varias_pistas_pregunta_una_vez(catalog: Catalog, config: Config) -> None:
    client = FakeClient()
    preguntas: list[str] = []

    def confirmar(question: str, step) -> bool:  # noqa: ANN001
        preguntas.append(question)
        return True

    executor = Executor(client, catalog, config, confirm=confirmar)
    plan = executor.build_plan(
        [
            ("track.delete", {"track": "Voz"}),
            ("track.delete", {"track": "Bajo"}),
            ("track.delete", {"track": "Batería"}),
        ]
    )
    report = executor.execute(plan)
    assert preguntas == ["¿Borro 3 pistas?"]
    assert report.ok
    assert report.speech == "Listo, borré 3 pistas."


def test_pregunta_no_ejecuta_nada(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({}))
    executor = Executor(client, catalog, config)
    plan = Plan(question="¿Cuál de las dos guitarras?", source="ia")
    report = executor.execute(plan)
    assert report.ok
    assert report.speech == "¿Cuál de las dos guitarras?"
    assert client.calls == []


def test_orden_de_los_pasos_se_respeta(catalog: Catalog, config: Config) -> None:
    client = FakeClient(ok_reply({"name": "A"}, {"name": "B"}))
    executor = Executor(client, catalog, config)
    plan = executor.build_plan([("track.add", {"name": "A"}), ("track.add", {"name": "B"})])
    executor.execute(plan)
    assert [call[1]["name"] for call in client.calls[0]] == ["A", "B"]


# ---------------------------------------------------------------- cliente real (con puente falso)


class FakeBridge(threading.Thread):
    """Escribe respuestas leyendo los pedidos, como haría el puente Lua."""

    def __init__(self, request_dir: Path, response_dir: Path, status_path: Path) -> None:
        super().__init__(daemon=True)
        self.request_dir = request_dir
        self.response_dir = response_dir
        self.status_path = status_path
        self.running = True

    def run(self) -> None:
        while self.running:
            for path in self.request_dir.glob("*.req.json"):
                try:
                    request = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                results = [
                    {"cmd": step["cmd"], "ok": True, "result": {"echo": step.get("args", {})}}
                    for step in request.get("steps", [])
                ]
                response = {
                    "v": 1,
                    "id": request["id"],
                    "ok": True,
                    "results": results,
                    "error": None,
                    "elapsed_ms": 1.0,
                }
                (self.response_dir / f"{request['id']}.res.json").write_text(
                    json.dumps(response), encoding="utf-8"
                )
                path.unlink(missing_ok=True)
            time.sleep(0.01)


@pytest.fixture()
def live_dirs(tmp_path: Path):
    request_dir = tmp_path / "requests"
    response_dir = tmp_path / "responses"
    status_path = tmp_path / "status.json"
    request_dir.mkdir()
    response_dir.mkdir()
    status_path.write_text(json.dumps({"bridge": "test", "protocol": 1, "command_count": 1}), encoding="utf-8")
    return request_dir, response_dir, status_path


def test_cliente_habla_el_protocolo(live_dirs) -> None:
    request_dir, response_dir, status_path = live_dirs
    bridge = FakeBridge(request_dir, response_dir, status_path)
    bridge.start()
    try:
        client = BridgeClient(request_dir, response_dir, status_path, stale_ms=5000)
        reply = client.call_one("track.add", {"name": "Guitarra"})
        assert reply.ok
        assert reply.steps[0].result["echo"]["name"] == "Guitarra"
        assert not list(request_dir.glob("*.req.json"))
        assert not list(response_dir.glob("*.res.json"))
    finally:
        bridge.running = False


def test_cliente_sin_puente_avisa(live_dirs) -> None:
    request_dir, response_dir, status_path = live_dirs
    status_path.unlink()
    client = BridgeClient(request_dir, response_dir, status_path, stale_ms=200)
    with pytest.raises(BridgeNotRunning):
        client.call_one("ping")


def test_cliente_latido_viejo_no_cuenta(live_dirs) -> None:
    request_dir, response_dir, status_path = live_dirs
    import os

    old = time.time() - 60
    os.utime(status_path, (old, old))
    client = BridgeClient(request_dir, response_dir, status_path, stale_ms=1000)
    assert client.read_status().alive is False


def test_cliente_timeout(live_dirs) -> None:
    request_dir, response_dir, status_path = live_dirs
    client = BridgeClient(request_dir, response_dir, status_path, stale_ms=5000, poll_interval=0.01)
    with pytest.raises(BridgeTimeout):
        client.call_one("ping", timeout=0.2)
