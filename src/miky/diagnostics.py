"""Paquete de diagnóstico: todo lo que hace falta para entender un problema.

No incluye audio, ni la API key, ni rutas de proyectos: solo versiones, el
resultado de `miky doctor`, la configuración sin secretos y los últimos logs.
"""

from __future__ import annotations

import contextlib
import io
import platform
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__, paths, reaper

MAX_LOG_LINES = 400
MAX_LOG_FILES = 6


def _redact_config(text: str) -> str:
    # Nunca sale la clave, ni cifrada ni en claro.
    text = re.sub(r'(api_key\s*=\s*")[^"]*(")', r"\1<oculta>\2", text)
    text = re.sub(r"(api_key\s*=\s*')[^']*(')", r"\1<oculta>\2", text)
    return _redact_paths(text)


def _redact_paths(text: str) -> str:
    """Reemplaza la carpeta del usuario por %USERPROFILE%."""
    home = str(Path.home())
    for variant in {home, home.replace("\\", "/")}:
        text = text.replace(variant, "%USERPROFILE%")
    return text


def _tail(path: Path, lines: int = MAX_LOG_LINES) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def _info() -> str:
    install = reaper.find_install()
    lines = [        f"miky: {__version__}",
        f"python: {sys.version.split()[0]} ({platform.python_implementation()})",
        f"windows: {platform.platform()}",
        f"arquitectura: {platform.machine()}",
        f"config: {paths.config_file()}",
        f"logs: {paths.logs_dir()}",
        f"ipc: {paths.ipc_root()}",
        f"reaper exe: {install.exe}",
        f"reaper recursos: {install.resource_path}",
    ]
    try:
        from .config import Config

        cfg = Config.load()
        lines.extend(
            [
                f"api key configurada: {'sí' if cfg.ai.api_key else 'no'}",
                f"proveedor: {cfg.ai.provider} · modelo: {cfg.ai.model}",
                f"stt: {cfg.voice.stt_model} · beam {cfg.voice.stt_beam}",
                f"tts: {cfg.voice.tts_engine} · voz: {cfg.voice.edge_voice}",
                f"entrada: {cfg.voice.input_device or 'automática'}",
                f"salida: {cfg.voice.output_device or 'predeterminada'}",
                f"modo: {cfg.voice.mode} · respuesta: {cfg.voice.feedback}",
                f"vocabulario propio: {len(cfg.voice.vocabulary)} palabras",
            ]
        )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"config: error al leer ({exc})")
    return _redact_paths("\n".join(lines) + "\n")


def _doctor() -> str:
    from .doctor import run_doctor

    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            run_doctor(network=False)
    except Exception as exc:  # noqa: BLE001
        buffer.write(f"\n[!] doctor falló: {exc}\n")
    return buffer.getvalue()


def _devices() -> str:
    lines = []
    try:
        import sounddevice as sd

        for index, device in enumerate(sd.query_devices()):
            lines.append(
                f"[{index}] {device.get('name')} · in {device.get('max_input_channels')} "
                f"· out {device.get('max_output_channels')} · {int(device.get('default_samplerate') or 0)} Hz"
            )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"no pude listar dispositivos: {exc}")
    return "\n".join(lines) + "\n"


def collect(destination: Path | None = None) -> Path:
    """Arma el ZIP y devuelve su ruta."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    work = Path(tempfile.mkdtemp(prefix="miky_diag_"))
    folder = work / f"miky-diagnostico-{stamp}"
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "info.txt").write_text(_info(), encoding="utf-8")
    (folder / "doctor.txt").write_text(_doctor(), encoding="utf-8")
    (folder / "dispositivos-audio.txt").write_text(_devices(), encoding="utf-8")

    config = paths.config_file()
    if config.exists():
        try:
            original = config.read_text(encoding="utf-8", errors="replace")
            (folder / "config-sin-clave.toml").write_text(_redact_config(original), encoding="utf-8")
        except OSError:
            pass

    logs = paths.logs_dir()
    if logs.exists():
        target = folder / "logs"
        target.mkdir(exist_ok=True)
        files = sorted(logs.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        for log_file in files[:MAX_LOG_FILES]:
            (target / log_file.name).write_text(_tail(log_file), encoding="utf-8")

    ipc = paths.ipc_root()
    if ipc.exists():
        target = folder / "puente"
        target.mkdir(exist_ok=True)
        status = ipc / "status.json"
        if status.exists():
            shutil.copy2(status, target / "status.json")
        bridge_log = ipc / "bridge.log"
        if bridge_log.exists():
            (target / "bridge.log").write_text(_tail(bridge_log, 300), encoding="utf-8")

    if destination is None:
        desktop = Path.home() / "Desktop"
        base = desktop if desktop.exists() else Path.cwd()
        destination = base / f"Miky-diagnostico-{stamp}.zip"
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in folder.rglob("*"):
            if item.is_file():
                archive.write(item, item.relative_to(folder.parent))
    shutil.rmtree(work, ignore_errors=True)
    return destination
