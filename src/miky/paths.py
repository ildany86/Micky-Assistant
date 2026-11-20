"""Rutas de la aplicación: datos de usuario, IPC, logs, config y assets."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

APP_DIR_NAME = "Miky"


def appdata_root() -> Path:
    """Carpeta de datos del usuario (debe coincidir con la que usa el puente Lua)."""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    # Respaldo para tests o entornos sin APPDATA.
    return Path.home() / ".miky"


def ipc_root() -> Path:
    """Canal de comunicación con el puente.

    `MIKY_IPC_ROOT` permite aislar el canal (tests o una segunda instancia de
    REAPER). El puente Lua lee la misma variable de entorno.
    """
    override = os.environ.get("MIKY_IPC_ROOT")
    if override:
        return Path(override)
    return appdata_root() / "ipc"


def requests_dir() -> Path:
    return ipc_root() / "requests"


def responses_dir() -> Path:
    return ipc_root() / "responses"


def status_file() -> Path:
    return ipc_root() / "status.json"


def logs_dir() -> Path:
    return appdata_root() / "logs"


def config_file() -> Path:
    return appdata_root() / "config.toml"


def models_dir() -> Path:
    return appdata_root() / "models"


def default_render_dir() -> Path:
    return Path.home() / "Documents" / "Miky Renders"


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    return package_dir() / "data"


def bundled_bridge() -> Path:
    return data_dir() / "miky_bridge.lua"


def bundled_commands() -> Path:
    return data_dir() / "commands.json"


def assets_dir() -> Path:
    return data_dir() / "assets"


def ensure_runtime_dirs() -> None:
    for path in (appdata_root(), ipc_root(), requests_dir(), responses_dir(), logs_dir()):
        path.mkdir(parents=True, exist_ok=True)


def clean_ipc(max_age_seconds: float = 300.0) -> int:
    """Borra pedidos/respuestas viejos de sesiones anteriores. Devuelve cuántos borró."""
    removed = 0
    cutoff = time.time() - max_age_seconds
    for directory in (requests_dir(), responses_dir()):
        if not directory.exists():
            continue
        for entry in directory.iterdir():
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
            except OSError:
                continue
    return removed


def copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        target = dst / item.relative_to(src)
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            shutil.copy2(item, target)
