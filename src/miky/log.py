"""Logging de la aplicación: consola + archivo rotativo en %APPDATA%\\Miky\\logs."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from . import paths

_CONFIGURED = False
_FORMAT = "%(asctime)s  %(levelname)-7s %(name)-18s %(message)s"


def setup(level: str = "INFO", log_file: Path | None = None) -> Path:
    global _CONFIGURED
    paths.ensure_runtime_dirs()
    target = log_file or (paths.logs_dir() / "miky.log")

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if _CONFIGURED:
        return target

    formatter = logging.Formatter(_FORMAT, datefmt="%H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(logging.INFO)
    root.addHandler(console)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            target, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
    except OSError:
        root.warning("no se pudo abrir el archivo de log en %s", target)

    # Ruido de librerías de terceros.
    for noisy in ("urllib3", "httpx", "httpcore", "google_genai", "absl"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return target


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
