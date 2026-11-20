"""`miky doctor`: chequeo de entorno, instalación y conexión con REAPER.

Es el primer comando que hay que correr cuando algo no anda. No modifica nada:
solo mira y reporta.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__, paths

OK = "ok"
WARN = "warn"
FAIL = "fail"

MARKERS = {OK: "[ok]  ", WARN: "[!]   ", FAIL: "[x]   "}


@dataclass
class Check:
    status: str
    title: str
    detail: str = ""

    def render(self) -> str:
        line = f"{MARKERS[self.status]}{self.title}"
        if self.detail:
            line += f"\n       {self.detail}"
        return line


def _module_version(name: str) -> str:
    try:
        module = __import__(name)
    except ImportError:
        return ""
    return str(getattr(module, "__version__", "instalado"))


def _check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    if sys.version_info < (3, 11):
        return Check(FAIL, f"Python {version}", "Miky necesita Python 3.11 o superior.")
    return Check(OK, f"Python {version}", sys.executable)


def _check_packages() -> list[Check]:
    checks: list[Check] = []
    required = {
        "PySide6": "interfaz (icono flotante)",
        "google.genai": "cliente de Gemini",
        "numpy": "procesamiento de audio",
        "sounddevice": "micrófono",
        "comtypes": "voz de Windows (SAPI)",
    }
    optional = {
        "faster_whisper": "reconocimiento de voz local",
        "onnxruntime": "VAD Silero",
    }
    for module, purpose in required.items():
        version = _module_version(module)
        checks.append(
            Check(OK, f"{module} {version}", purpose)
            if version
            else Check(FAIL, f"falta {module}", f"pip install miky  ({purpose})")
        )
    for module, purpose in optional.items():
        version = _module_version(module)
        checks.append(
            Check(OK, f"{module} {version}", purpose)
            if version
            else Check(WARN, f"falta {module}", f"sin esto no hay {purpose}: pip install {module}")
        )
    return checks


def _check_config() -> list[Check]:
    from .config import Config

    config_path = paths.config_file()
    config = Config.load()
    checks: list[Check] = []
    if config_path.exists():
        checks.append(Check(OK, "configuración", str(config_path)))
    else:
        checks.append(Check(WARN, "configuración sin crear", f"se va a generar en {config_path}"))

    provider = config.ai.provider
    if provider == "mock":
        checks.append(Check(WARN, "IA en modo sin conexión", "solo funcionan los comandos directos"))
    elif config.has_api_key:
        source = "variable de entorno" if config.api_key_from_env else "configuración (cifrada)"
        checks.append(Check(OK, f"IA {provider} · {config.ai.model}", f"API key desde {source}"))
    else:
        checks.append(
            Check(FAIL, f"IA {provider} sin API key", "pegala en Ajustes (clic derecho en el icono)")
        )

    if not config.voice.enabled:
        checks.append(Check(WARN, "voz desactivada", "config.voice.enabled = false"))
    return checks


def _reaper_version(resource: Path | None) -> str:
    if not resource:
        return ""
    for name in ("reaper-install-rev.txt", "reaper-install-rev.txt"):
        candidate = resource / name
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return ""
    return ""


def _check_reaper() -> list[Check]:
    from . import reaper

    install = reaper.find_install()
    checks: list[Check] = []
    if install.exe:
        checks.append(Check(OK, "REAPER instalado", str(install.exe)))
    else:
        checks.append(Check(FAIL, "no encontré reaper.exe", "indicá reaper.install_path en la config"))
        return checks

    if install.resource_path:
        version = _reaper_version(install.resource_path)
        detail = str(install.resource_path) + (f" · versión {version}" if version else "")
        checks.append(Check(OK, "carpeta de recursos", detail))
    else:
        checks.append(Check(FAIL, "no encontré la carpeta de recursos de REAPER", ""))

    if install.installed:
        installed_version = install.installed_version()
        if installed_version == __version__:
            checks.append(Check(OK, "puente instalado y al día", str(install.bridge_path)))
        else:
            checks.append(
                Check(
                    WARN,
                    "puente instalado con otra versión",
                    f"instalado {installed_version or '?'} · esperado {__version__} · corré: miky install-bridge",
                )
            )
    else:
        checks.append(
            Check(WARN, "puente no instalado", "corré: miky install-bridge (o abrilo desde el icono)")
        )

    if reaper.is_reaper_running():
        checks.append(Check(OK, "REAPER está abierto", ""))
    else:
        checks.append(Check(WARN, "REAPER cerrado", "el puente arranca cuando abre REAPER"))
    return checks


def _check_ipc() -> list[Check]:
    from .bridge import BridgeClient
    from .catalog import Catalog

    checks: list[Check] = []
    try:
        paths.ensure_runtime_dirs()
        checks.append(Check(OK, "carpeta de trabajo", str(paths.ipc_root())))
    except OSError as exc:
        checks.append(Check(FAIL, "no puedo crear la carpeta de trabajo", str(exc)))
        return checks

    client = BridgeClient()
    status = client.read_status()
    if not status.alive:
        checks.append(
            Check(
                WARN,
                "puente sin señal",
                f"último latido hace {status.age_ms / 1000:.0f} s · abrí REAPER con Miky",
            )
        )
        return checks

    checks.append(
        Check(
            OK,
            f"puente vivo · v{status.bridge_version}",
            f"REAPER {status.reaper_version} · protocolo {status.protocol}",
        )
    )
    if status.last_error:
        checks.append(Check(WARN, "el puente reportó un error", str(status.last_error)))

    try:
        from .bridge import ping

        info = ping(client, timeout=4.0)
        checks.append(Check(OK, "el puente responde al ping", f"{info.get('command_count')} comandos"))
        bridge_commands = set(info.get("commands") or [])
        catalog = Catalog.load()
        missing = set(catalog.ids()) - bridge_commands
        if missing:
            checks.append(
                Check(
                    FAIL,
                    "el puente no conoce todos los comandos",
                    "faltan: " + ", ".join(sorted(missing)),
                )
            )
        else:
            checks.append(Check(OK, "catálogo y puente coinciden", f"{len(catalog.all())} comandos"))
    except Exception as exc:  # noqa: BLE001
        checks.append(Check(FAIL, "el puente no respondió al ping", str(exc)))
    return checks


def _check_audio() -> list[Check]:
    checks: list[Check] = []
    try:
        from .voice.audio import list_input_devices, pick_input_device

        devices = list_input_devices()
        if not devices:
            checks.append(Check(FAIL, "no hay micrófonos", "Windows no reporta entradas de audio"))
        else:
            index, reason = pick_input_device("")
            checks.append(Check(OK, "micrófono elegido", reason))
            wasapi = [d for d in devices if "wasapi" in d.hostapi.lower()]
            checks.append(
                Check(
                    OK if wasapi else WARN,
                    f"{len(devices)} entradas de audio ({len(wasapi)} por WASAPI)",
                    "conviene WASAPI y un dispositivo distinto al que usa REAPER por ASIO",
                )
            )
    except Exception as exc:  # noqa: BLE001
        checks.append(Check(FAIL, "no pude consultar el audio", str(exc)))
    return checks


def _check_voice() -> list[Check]:
    checks: list[Check] = []
    try:
        from .voice.tts import list_sapi_outputs, list_sapi_voices

        voices = list_sapi_voices()
        spanish = [voice for voice in voices if (voice.language or "").startswith("es")]
        if voices:
            detail = ", ".join(voice.name for voice in voices[:3])
            checks.append(Check(OK, f"{len(voices)} voces SAPI", detail))
        else:
            checks.append(Check(WARN, "sin voces SAPI", "Miky va a responder solo por texto"))
        if voices and not spanish:
            checks.append(
                Check(WARN, "no hay voces en español", "Instalá el paquete de idioma español en Windows")
            )

        outputs = list_sapi_outputs()
        if outputs:
            checks.append(
                Check(OK, f"{len(outputs)} salidas de audio para la voz", ", ".join(outputs[:3]))
            )
        else:
            checks.append(Check(WARN, "no pude listar salidas de audio", "la voz usará la predeterminada"))
    except Exception as exc:  # noqa: BLE001
        checks.append(Check(WARN, "no pude consultar las voces", str(exc)))
    return checks


def _check_network() -> Check:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen("https://aistudio.google.com", timeout=6) as response:
            return Check(OK, "conexión a internet", f"HTTP {response.status}")
    except urllib.error.URLError as exc:
        return Check(WARN, "sin conexión a internet", str(exc.reason))
    except Exception as exc:  # noqa: BLE001
        return Check(WARN, "no pude probar la conexión", str(exc))


def _check_ai_call() -> Check:
    from .ai import AIError, build_provider
    from .catalog import Catalog
    from .config import Config

    config = Config.load()
    if not config.has_api_key:
        return Check(WARN, "no pruebo la IA", "falta la API key")
    provider = build_provider(config.ai)
    try:
        provider.interpret(
            "hola",
            {"assistant": {"name": "Miky"}, "tracks": []},
            Catalog.load(),
        )
        return Check(OK, f"la IA respondió ({provider.description})", "")
    except AIError as exc:
        return Check(FAIL, "la IA no respondió", str(exc))
    except Exception as exc:  # noqa: BLE001
        return Check(FAIL, "la IA falló", str(exc))


def run_doctor(network: bool = False) -> int:
    print(f"Miky {__version__} · diagnóstico\n")

    checks: list[Check] = [_check_python()]
    checks.extend(_check_packages())
    checks.extend(_check_config())
    checks.extend(_check_reaper())
    checks.extend(_check_ipc())
    checks.extend(_check_audio())
    checks.extend(_check_voice())
    if network:
        checks.append(_check_network())
        checks.append(_check_ai_call())

    for check in checks:
        print(check.render())

    failures = sum(1 for check in checks if check.status == FAIL)
    warnings = sum(1 for check in checks if check.status == WARN)
    print()
    if failures:
        print(f"{failures} problema(s) para resolver, {warnings} aviso(s).")
        return 1
    if warnings:
        print(f"Todo lo importante está en orden ({warnings} aviso(s)).")
        return 0
    print("Todo en orden.")
    return 0
