"""Prueba de "proactividad": qué plan arma la IA para un pedido con intención.

Usa la API real configurada, con un proyecto simulado (no toca REAPER).

Uso: python tools/probe_intent.py "quiero que por los auriculares solo se escuche el bajo y la batería"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from miky.ai import build_provider  # noqa: E402
from miky.catalog import Catalog  # noqa: E402
from miky.config import Config  # noqa: E402

STATE = {
    "project": "tema nuevo tanguero",
    "tracks": [
        {"index": 1, "name": "Batería", "volume_db": 0.0, "pan": 0.0, "mute": False, "solo": False,
         "armed": False, "selected": False, "fx": [], "sends": []},
        {"index": 2, "name": "Bajo", "volume_db": -2.0, "pan": 0.0, "mute": False, "solo": False,
         "armed": False, "selected": False, "fx": [], "sends": []},
        {"index": 3, "name": "Guitarra", "volume_db": -1.0, "pan": -0.2, "mute": False, "solo": False,
         "armed": False, "selected": False, "fx": [], "sends": []},
        {"index": 4, "name": "Voz", "volume_db": 0.0, "pan": 0.0, "mute": False, "solo": False,
         "armed": True, "selected": True, "fx": [], "sends": []},
    ],
    "master": {"volume_db": 0.0, "mute": False},
    "transport": {"playing": False, "recording": False, "position": 0.0},
    "audio": {"outputs": {"count": 2, "pairs": ["Salida 1 / Salida 2"]}},
}

CONTEXT = {
    "assistant": {"name": "Miky", "version": "0.1.0b1"},
    "state": STATE,
    "render_defaults": {"dir": "C:/Users/Dani/Music", "pattern": "$project"},
}


def main() -> int:
    pedido = sys.argv[1] if len(sys.argv) > 1 else (
        "quiero que por los auriculares solo se escuche el bajo y la batería"
    )
    config = Config.load()
    catalog = Catalog.load()
    if len(sys.argv) > 2:
        config.ai.model = sys.argv[2]
    # Simular una placa con más salidas: MIKY_PROBE_OUTPUTS=8
    import os

    salidas = int(os.environ.get("MIKY_PROBE_OUTPUTS", "2"))
    STATE["audio"] = {
        "outputs": {
            "count": salidas,
            "pairs": [f"Salida {i + 1} / Salida {i + 2}" for i in range(0, salidas, 2)],
        }
    }
    provider = build_provider(config.ai)
    print(f"[i] proveedor: {config.ai.provider}/{config.ai.model} · disponible: {provider.available}")
    print(f"[i] pedido: «{pedido}»")

    resultado = provider.interpret(pedido, CONTEXT, catalog)

    # Misma verificación que hace la app: si dice que hizo algo sin ejecutar
    # ningún comando, se le pide una segunda respuesta.
    from miky.ai import AIResult
    from miky.app import CLAIM_RETRY_NOTE, _claims_done, _looks_like_action_request

    if not resultado.steps and _looks_like_action_request(pedido) and _claims_done(resultado.answer):
        print("\n[!] la respuesta afirma haber hecho algo sin ejecutar comandos: REINTENTO")
        reintento = provider.interpret(CLAIM_RETRY_NOTE + pedido, CONTEXT, catalog)
        if reintento.steps or not _claims_done(reintento.answer):
            resultado = reintento
        else:
            print("[!] el reintento tampoco ejecutó: se pide una explicación")
            from miky.app import EXPLAIN_NOTE

            explicacion = provider.interpret(EXPLAIN_NOTE + pedido, CONTEXT, catalog)
            if explicacion.answer and not _claims_done(explicacion.answer):
                resultado = explicacion
            else:
                resultado = AIResult(
                    answer=(
                        "Eso no lo ejecuté: todavía no tengo un comando que lo haga tal cual. "
                        "Decímelo de otra forma y lo intento."
                    )
                )

    print(f"\n[i] proveedor devolvió: {resultado.provider}/{resultado.model}")
    if resultado.note:
        print(f"[i] nota: {resultado.note}")
    if resultado.question:
        print(f"[?] PREGUNTA AL USUARIO: {resultado.question}")
    if resultado.answer:
        print(f"[>] RESPUESTA: {resultado.answer}")
    if not resultado.steps:
        print("[i] no propuso pasos")
    for command, args in resultado.steps:
        spec = catalog.get(command)
        print(f"[+] {command} {json.dumps(args, ensure_ascii=False)}")
        print(f"      ({spec.summary if spec else '??'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
