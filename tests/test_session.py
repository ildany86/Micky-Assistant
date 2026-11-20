"""Miky lee los parámetros reales de los plugins de la sesión."""

from __future__ import annotations

from types import SimpleNamespace

from miky.app import MikyApp


class _Reply:
    def __init__(self, result: dict | None) -> None:
        self.ok = result is not None
        self.first = SimpleNamespace(result=result) if result is not None else None


class _Client:
    def __init__(self, payloads: dict[str, dict]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[str, dict]] = []

    def call_one(self, command: str, args: dict | None = None, timeout: float = 0.0):
        self.calls.append((command, dict(args or {})))
        return _Reply(self.payloads.get(command))


def _app(payloads: dict[str, dict]) -> SimpleNamespace:
    return SimpleNamespace(client=_Client(payloads))


def _params_payload() -> dict:
    return {
        "track_name": "Voz",
        "plugins": [
            {
                "name": "VST: ReaComp (Cockos)",
                "preset": "",
                "params": [
                    {"name": "Threshold", "value": "-18.0 dB"},
                    {"name": "Ratio", "value": "8.0"},
                    {"name": "Attack", "value": "1 ms"},
                    {"name": "Release", "value": "100 ms"},
                ],
            }
        ],
    }


def test_lee_los_parametros_de_la_pista_con_plugins() -> None:
    app = _app({"fx.params": _params_payload()})
    tracks = [{"name": "Voz", "fx_count": 1, "selected": True}]
    settings = MikyApp._session_fx_settings(app, tracks)
    assert settings
    assert settings[0]["pista"] == "Voz"
    plugin = settings[0]["plugins"][0]
    assert plugin["nombre"] == "VST: ReaComp (Cockos)"
    assert plugin["parametros"]["Ratio"] == "8.0"
    assert app.client.calls[0][0] == "fx.params"
    assert app.client.calls[0][1]["track"] == "Voz"


def test_sin_plugins_no_llama_al_puente() -> None:
    app = _app({})
    assert MikyApp._session_fx_settings(app, [{"name": "Voz", "fx_count": 0}]) == []
    assert app.client.calls == []


def test_prioriza_la_pista_seleccionada() -> None:
    app = _app({"fx.params": _params_payload()})
    tracks = [
        {"name": "Batería", "fx_count": 2, "selected": False},
        {"name": "Voz", "fx_count": 1, "selected": True},
    ]
    MikyApp._session_fx_settings(app, tracks)
    assert app.client.calls[0][1]["track"] == "Voz"


def test_si_el_puente_falla_devuelve_vacio() -> None:
    app = _app({})
    tracks = [{"name": "Voz", "fx_count": 1}]
    assert MikyApp._session_fx_settings(app, tracks) == []
