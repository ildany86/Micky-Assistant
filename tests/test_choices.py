"""Pruebas del flujo de "elegí una opción" cuando hay varios plugins."""

from __future__ import annotations

import pytest

from miky.app import MikyApp, _short_fx_name
from miky.bridge import BridgeReply, StepOutcome
from miky.catalog import Catalog
from miky.config import Config
from miky.engine import Executor


class StubClient:
    def __init__(self) -> None:
        self.calls: list[list[tuple[str, dict]]] = []

    def call(self, steps, timeout=None, require_alive=True):  # noqa: ANN001
        self.calls.append([(command, args) for command, args in steps])
        return BridgeReply(
            request_id="x",
            ok=True,
            steps=[StepOutcome(command=steps[0][0], ok=True, result={"name": steps[0][1].get("name")})],
        )


class Stub:
    """Lo mínimo que necesita `_resolve_pending_choice` para funcionar."""

    def __init__(self, options: list[str]) -> None:
        config = Config()
        self.catalog = Catalog.load()
        self.client = StubClient()
        self.executor = Executor(self.client, self.catalog, config)
        self._pending_choice = {
            "command": "fx.add",
            "base_args": {"track": "Voz"},
            "options": options,
        }
        self.spoken: list[str] = []
        self.remembered: list[tuple] = []

    def _say(self, text: str, speak: bool = True) -> None:
        self.spoken.append(text)

    def _remember(self, plan, report, request: str = "") -> None:  # noqa: ANN001
        self.remembered.append((plan, report))


OPTIONS = [
    "VST: SSL Native Bus Compressor (SSL)",
    "VST: ReaComp (Cockos)",
    "VST: FabFilter Pro-C 2 (FabFilter)",
]


def test_nombre_corto_de_plugin() -> None:
    assert _short_fx_name("VST: FabFilter Pro-Q 4 (FabFilter)") == "FabFilter Pro-Q 4"
    assert _short_fx_name("VST3i: Amplitube 5 (IK Multimedia)") == "Amplitube 5"
    assert _short_fx_name("ReaEQ") == "ReaEQ"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("el 2", "VST: ReaComp (Cockos)"),
        ("dos", "VST: ReaComp (Cockos)"),
        ("la opción 3", "VST: FabFilter Pro-C 2 (FabFilter)"),
        ("el del SSL", "VST: SSL Native Bus Compressor (SSL)"),
        ("ponele el fabfilter", "VST: FabFilter Pro-C 2 (FabFilter)"),
    ],
)
def test_eleccion_por_numero_o_nombre(texto: str, esperado: str) -> None:
    stub = Stub(list(OPTIONS))
    result = MikyApp._resolve_pending_choice(stub, texto)
    assert result is not None
    assert stub._pending_choice is None
    assert stub.client.calls[0][0][0] == "fx.add"
    assert stub.client.calls[0][0][1]["name"] == esperado


def test_eleccion_cancelada_no_carga_nada() -> None:
    stub = Stub(list(OPTIONS))
    result = MikyApp._resolve_pending_choice(stub, "no, dejalo")
    assert result == "Listo, no cargo nada."
    assert stub.client.calls == []
    assert stub._pending_choice is None


def test_eleccion_no_relacionada_sigue_el_flujo_normal() -> None:
    stub = Stub(list(OPTIONS))
    result = MikyApp._resolve_pending_choice(stub, "subí el bajo 2 dB")
    assert result is None
    assert stub.client.calls == []
    assert stub._pending_choice is None


def test_fuera_de_rango_no_elige() -> None:
    stub = Stub(list(OPTIONS))
    result = MikyApp._resolve_pending_choice(stub, "el 9")
    assert result is None
    assert stub.client.calls == []


def test_eleccion_indica_otra_pista() -> None:
    stub = Stub(list(OPTIONS))
    result = MikyApp._resolve_pending_choice(stub, "quiero el uno en la pista de bajo")
    assert result is not None
    args = stub.client.calls[0][0][1]
    assert args["name"] == "VST: SSL Native Bus Compressor (SSL)"
    assert args["track"] == "bajo"


def test_eleccion_nombre_del_plugin_con_numero_de_pista() -> None:
    stub = Stub(list(OPTIONS))
    stub._pending_choice["base_args"] = {"track": "voz"}
    result = MikyApp._resolve_pending_choice(stub, "el del SSL")
    assert result is not None
    assert stub.client.calls[0][0][1]["track"] == "voz"
