"""Interfaz de línea de comandos de Miky.

    miky                 abre el asistente (icono flotante)
    miky doctor          revisa que todo esté en condiciones
    miky status          estado de la conexión con REAPER
    miky send ...        manda un comando suelto al puente
    miky devices         lista micrófonos
    miky voices          lista voces de Windows
    miky tools           muestra el catálogo de comandos
    miky install-bridge  instala el puente en REAPER
    miky listen          prueba de voz en consola
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import APP_NAME, __version__, __version_display__


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------- comandos


def cmd_run(args: argparse.Namespace) -> int:
    from . import log as log_mod, paths
    from .app import MikyApp
    from .config import Config

    config = Config.load()
    # La configuración inicial se escribe con los valores por defecto: los flags
    # de la línea de comandos (--no-voice, --mute) son temporales y no deben
    # quedar guardados.
    if not paths.config_file().exists():
        try:
            Config().save()
            print(f"Configuración inicial creada en {paths.config_file()}")
        except OSError as exc:
            print(f"No pude crear la configuración: {exc}")
        config = Config.load()

    if args.no_voice:
        config.voice.enabled = False
    if args.mute:
        config.voice.speak_replies = False

    log_mod.setup(config.app.log_level)
    core = MikyApp(config, ui_enabled=not args.no_ui)
    core.bootstrap()

    if args.say:
        core.start_background()
        print(core.handle_text(args.say))
        time.sleep(0.6)
        core.stop()
        return 0

    if args.console or args.no_ui:
        return _console_loop(core)

    from .ui.shell import MikyShell

    core.start_background()
    shell = MikyShell(core, config)
    try:
        return shell.run()
    finally:
        core.stop()


def _console_loop(core) -> int:  # noqa: ANN001
    core.start_background()
    print(f"{APP_NAME} {__version_display__} · modo consola")
    print("Escribí una orden y enter. 'salir' para terminar.\n")
    try:
        while True:
            try:
                line = input("miky> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                continue
            if line.lower() in ("salir", "exit", "quit"):
                break
            try:
                print(core.handle_text(line))
            except Exception as exc:  # noqa: BLE001
                print(f"error: {exc}")
    finally:
        core.stop()
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import run_doctor

    return run_doctor(network=args.network)


def cmd_status(_args: argparse.Namespace) -> int:
    from . import paths
    from .bridge import BridgeClient

    client = BridgeClient()
    status = client.read_status()
    print(f"config:  {paths.config_file()}")
    print(f"ipc:     {paths.ipc_root()}")
    print(f"latido:  {status.age_ms / 1000:.1f} s")
    print(f"vivo:    {'sí' if status.alive else 'no'}")
    if status.alive:
        print(f"puente:  {status.bridge_version} (protocolo {status.protocol})")
        print(f"REAPER:  {status.reaper_version}")
        print(f"proyecto:{status.project or ' (sin nombre)'}")
        print(f"ocupado: {'sí' if status.busy else 'no'}")
        if status.last_error:
            print(f"último error: {status.last_error}")
        try:
            from .bridge import ping

            info = ping(client, timeout=3.0)
            print(f"ping:    ok ({info.get('command_count', '?')} comandos)")
        except Exception as exc:  # noqa: BLE001
            print(f"ping:    falló ({exc})")
    else:
        print("El puente no está activo. Abrí REAPER desde el icono de Miky.")
    return 0 if status.alive else 1


def cmd_send(args: argparse.Namespace) -> int:
    from . import paths
    from .bridge import BridgeClient, BridgeError
    from .catalog import Catalog
    from .engine import quick_run

    client = BridgeClient()
    catalog = Catalog.load()
    payload = {}
    if args.args:
        try:
            payload = json.loads(args.args)
        except json.JSONDecodeError as exc:
            print(f"argumentos inválidos: {exc}")
            return 2
    try:
        reply = quick_run(client, catalog, args.command, payload, timeout=args.timeout)
    except BridgeError as exc:
        print(f"error de conexión: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}")
        return 1
    print(json.dumps(
        {
            "ok": reply.ok,
            "elapsed_ms": round(reply.elapsed_ms, 1),
            "steps": [
                {"cmd": step.command, "ok": step.ok, "result": step.result, "error": step.error}
                for step in reply.steps
            ],
            "error": reply.error,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if reply.ok else 1


def cmd_devices(_args: argparse.Namespace) -> int:
    from .voice.audio import list_input_devices, pick_input_device

    devices = list_input_devices()
    if not devices:
        print("No hay dispositivos de entrada disponibles.")
        return 1
    chosen, reason = pick_input_device("")
    for device in devices:
        marker = "->" if device.index == chosen else "  "
        default = " (predeterminado)" if device.is_default else ""
        print(f"{marker} {device.index:3d}  {device.name}  [{device.hostapi}]{default}")
    print(f"\nMiky usaría: {reason}")
    return 0


def cmd_voices(_args: argparse.Namespace) -> int:
    from .voice.tts import list_sapi_voices

    voices = list_sapi_voices()
    if not voices:
        print("No encontré voces SAPI instaladas.")
        return 1
    for voice in voices:
        print(f"- {voice.name}  ({voice.language or 'idioma desconocido'})")
    return 0


def cmd_tools(_args: argparse.Namespace) -> int:
    from .ai.prompt import tools_summary
    from .catalog import Catalog

    catalog = Catalog.load()
    print(tools_summary(catalog))
    print(f"\n{len(catalog.all())} comandos en total.")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    from . import reaper

    install = reaper.find_install()
    if not install.found:
        print("No encontré REAPER instalado.")
        return 1
    if args.remove:
        ok, message = reaper.uninstall_bridge(install)
    else:
        ok, message = reaper.install_bridge(install)
    print(message)
    if ok and not args.remove:
        print("Reiniciá REAPER (o abrilo desde Miky) para que el puente arranque.")
    return 0 if ok else 1


def cmd_listen(args: argparse.Namespace) -> int:
    from . import log as log_mod
    from .config import Config
    from .voice.pipeline import VoicePipeline, VoiceSettings

    config = Config.load()
    log_mod.setup("DEBUG")
    settings = VoiceSettings.from_config(config.voice)

    def on_command(text: str) -> None:
        print(f"\n>>> COMANDO: {text}")

    def on_state(state: str) -> None:
        print(f"[estado] {state}")

    def on_transcript(text: str, activated: bool) -> None:
        print(f"{'*' if activated else ' '} {text}")

    pipeline = VoicePipeline(
        settings,
        on_command=on_command,
        on_state=on_state,
        on_transcript=on_transcript,
        on_error=lambda message: print(f"[error] {message}"),
    )
    print("Cargando modelo de voz... (la primera vez descarga el modelo)")
    pipeline.start()
    print(f"Escuchando. Decí «{settings.wake_word}» y después la orden. Ctrl+C para salir.")
    try:
        while True:
            time.sleep(0.4)
            if pipeline.stt_ready and not getattr(args, "ready_reported", False):
                print("Modelo listo.")
                args.ready_reported = True  # type: ignore[attr-defined]
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    from . import bench
    from .config import Config

    return bench.run(Config.load(), repeat=max(1, int(getattr(args, "repeat", 3))))


def cmd_knowledge(args: argparse.Namespace) -> int:
    """Muestra las fichas técnicas que usa Miky para aconsejar."""
    from . import knowledge

    query = (getattr(args, "query", "") or "").strip()
    if not query:
        print("Fichas técnicas disponibles:")
        for card in knowledge.CARDS:
            print(f"  {card.id:10s} {card.title}  ({len(card.body)} datos)")
        print("\nUsá «miky knowledge -q tema» para ver una ficha completa.")
        return 0
    cards = knowledge.relevant(query, limit=3)
    if not cards:
        print(f"No tengo una ficha para «{query}». Probá con: eq, compresor, voz, batería, mezcla…")
        return 1
    for card in cards:
        print(f"\n## {card.title} ({card.id})")
        for line in card.body:
            print(f"  - {line}")
    return 0


def cmd_plugins(args: argparse.Namespace) -> int:
    """Lista los plugins instalados en REAPER (o busca por descripción)."""
    from .bridge import BridgeClient, BridgeError

    client = BridgeClient()
    query = (getattr(args, "query", "") or "").strip()
    limit = int(getattr(args, "limit", 0) or 0)
    try:
        if query:
            reply = client.call_one("fx.search", {"query": query, "limit": limit or 8}, timeout=8.0)
        else:
            reply = client.call_one("fx.installed", {"limit": limit}, timeout=8.0)
    except BridgeError as exc:
        print(f"REAPER no está respondiendo ({exc})")
        return 1
    if not reply.ok or reply.first is None:
        print(f"No pude: {reply.error_message}")
        return 1
    data = dict(reply.first.result or {})
    if query:
        names = list(data.get("candidates") or [])
        print(f"{data.get('count', len(names))} coincidencias para «{query}»:")
    else:
        names = list(data.get("names") or [])
        print(f"{data.get('count', len(names))} plugins instalados")
        vendors = list(data.get("vendors") or [])
        if vendors:
            print("fabricantes: " + ", ".join(vendors[:20]))
        favorites = list(data.get("favorites") or [])
        if favorites:
            print(f"favoritos ({len(favorites)}):")
            for name in favorites:
                print(f"  ★ {name}")
    for name in names:
        print(f"  {name}")
    if data.get("truncated"):
        print("  (lista recortada; usá --limit para ver más)")
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    from . import paths

    print(f"{APP_NAME} {__version_display__}")
    print(f"config: {paths.config_file()}")
    return 0


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="miky",
        description="Miky: asistente de voz local para REAPER",
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version_display__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="abre el asistente (por defecto)")
    run.add_argument("--console", action="store_true", help="sin interfaz, por consola")
    run.add_argument("--no-ui", action="store_true", help="no crear el icono flotante")
    run.add_argument("--no-voice", action="store_true", help="arrancar sin micrófono")
    run.add_argument("--mute", action="store_true", help="no hablar")
    run.add_argument("--say", metavar="TEXTO", help="ejecutar una orden y salir")
    run.set_defaults(func=cmd_run)

    doctor = sub.add_parser("doctor", help="revisa el entorno y la conexión")
    doctor.add_argument("--network", action="store_true", help="probar también la API de IA")
    doctor.set_defaults(func=cmd_doctor)

    status = sub.add_parser("status", help="estado de la conexión con REAPER")
    status.set_defaults(func=cmd_status)

    send = sub.add_parser("send", help="manda un comando suelto al puente")
    send.add_argument("command")
    send.add_argument("--args", default="{}", help="argumentos en JSON")
    send.add_argument("--timeout", type=float, default=30.0)
    send.set_defaults(func=cmd_send)

    devices = sub.add_parser("devices", help="lista micrófonos")
    devices.set_defaults(func=cmd_devices)

    voices = sub.add_parser("voices", help="lista voces del sistema")
    voices.set_defaults(func=cmd_voices)

    tools = sub.add_parser("tools", help="muestra el catálogo de comandos")
    tools.set_defaults(func=cmd_tools)

    install = sub.add_parser("install-bridge", help="instala el puente en REAPER")
    install.add_argument("--remove", action="store_true", help="desinstalar")
    install.set_defaults(func=cmd_install)

    listen = sub.add_parser("listen", help="prueba de voz en consola")
    listen.set_defaults(func=cmd_listen)

    bench = sub.add_parser("bench", help="mide cuánto tarda cada etapa")
    bench.add_argument("--repeat", type=int, default=3, help="repeticiones por etapa")
    bench.set_defaults(func=cmd_bench)

    plugins = sub.add_parser("plugins", help="lista o busca los plugins instalados")
    plugins.add_argument("--query", "-q", default="", help="buscar por descripción o marca")
    plugins.add_argument("--limit", type=int, default=0, help="cuántos mostrar (0 = todos)")
    plugins.set_defaults(func=cmd_plugins)

    knowledge = sub.add_parser("knowledge", help="fichas técnicas de audio y mezcla")
    knowledge.add_argument("--query", "-q", default="", help="tema: eq, compresor, voz, batería…")
    knowledge.set_defaults(func=cmd_knowledge)

    version = sub.add_parser("version", help="versión y rutas")
    version.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args = parser.parse_args((argv or []) + ["run"])
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
