"""Miky mide los niveles reales del medidor (solo con el transporte andando)."""

from __future__ import annotations

from types import SimpleNamespace

from miky.app import MikyApp


class _Reply:
    def __init__(self, result: dict | None) -> None:
        self.ok = result is not None
        self.first = SimpleNamespace(result=result) if result is not None else None


class _Client:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls = 0

    def call_one(self, command: str, args: dict | None = None, timeout: float = 0.0):
        self.calls += 1
        if not self.payloads:
            return _Reply(None)
        return _Reply(self.payloads.pop(0))


def _app(payloads: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(client=_Client(payloads))


def _frame(voz: float, bateria: float, master: float, playing: bool = True) -> dict:
    return {
        "playing": playing,
        "recording": False,
        "master": {"peak": 0.0, "peak_db": master},
        "tracks": [
            {"index": 1, "name": "Voz", "peak_db": voz},
            {"index": 2, "name": "Batería", "peak_db": bateria},
        ],
    }


def test_toma_el_maximo_de_varias_muestras() -> None:
    app = _app([_frame(-12, -20, -6), _frame(-6, -18, -6), _frame(-9, -16, -6)])
    levels = MikyApp._session_levels(app, spacing=0)
    assert levels is not None
    assert levels["picos"]["Voz"] == -6.0
    assert levels["picos"]["Batería"] == -16.0
    assert levels["picos"]["master"] == -6.0


def test_con_el_transporte_parado_no_hay_niveles() -> None:
    app = _app([_frame(-12, -20, -6, playing=False)])
    assert MikyApp._session_levels(app, spacing=0) is None


def test_sin_puente_devuelve_none() -> None:
    app = _app([])
    assert MikyApp._session_levels(app, spacing=0) is None


def test_descarta_el_silencio_absoluto() -> None:
    app = _app([_frame(-120, -120, -120)])
    assert MikyApp._session_levels(app, spacing=0) is None
