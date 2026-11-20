"""Prueba de humo de la interfaz real: levanta el icono y cierra solo.

Sirve para verificar que Qt, la bandeja, el menú y los popups arrancan sin
excepciones. Usa la voz desactivada para no cargar el modelo de reconocimiento.

Uso: python tools/ui_smoke.py [segundos]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from miky import log as log_mod  # noqa: E402
from miky.app import MikyApp  # noqa: E402
from miky.config import Config  # noqa: E402


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    config = Config.load()
    config.voice.enabled = False
    config.voice.speak_replies = False
    if config.ui.position == (-1, -1):
        config.ui.position = (240, 240)

    log_mod.setup("INFO")
    core = MikyApp(config, ui_enabled=True)
    core.bootstrap()
    core.start_background()

    from miky.ui.shell import MikyShell

    shell = MikyShell(core, config)
    print(f"levantando interfaz por {seconds:.1f} s...")
    try:
        code = shell.run(quit_after=seconds)
    finally:
        core.stop()
    print(f"interfaz cerrada con código {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
