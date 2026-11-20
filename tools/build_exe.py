"""Empaqueta Miky en un ejecutable con PyInstaller.

Uso:
    python tools/build_exe.py              # sin consola (el que se distribuye)
    python tools/build_exe.py --console    # con consola (para ver errores)
    python tools/build_exe.py --onefile    # un solo .exe (arranque más lento)

Salida: dist/Miky/Miky.exe
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Módulos de Qt que Miky no usa: sacarlos achica mucho el paquete.
QT_EXCLUDES = (
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "tkinter",
    "matplotlib",
    "PIL",
    "pytest",
    "lupa",
    "torch",
    "torchaudio",
    "torchvision",
    "tensorboard",
    "silero_vad",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye el ejecutable de Miky")
    parser.add_argument("--console", action="store_true", help="mostrar consola")
    parser.add_argument("--onefile", action="store_true", help="un solo archivo")
    parser.add_argument("--keep", action="store_true", help="no borrar dist/ previo")
    args = parser.parse_args()

    if not args.keep:
        for folder in (ROOT / "dist", ROOT / "build" / "Miky"):
            shutil.rmtree(folder, ignore_errors=True)

    icon = ROOT / "src" / "miky" / "data" / "assets" / "logo.ico"
    command = [
        sys.executable,
        "-u",
        "-m",
        "PyInstaller",
        str(ROOT / "tools" / "exe_entry.py"),
        "--name",
        "Miky",
        "--noconfirm",
        "--clean",
        "--noconsole",
        "--paths",
        str(ROOT / "src"),
        "--log-level",
        "WARN",
        # Datos del paquete (catálogo, puente Lua, logo).
        "--add-data",
        f"{ROOT / 'src' / 'miky' / 'data'};miky/data",
        # Solo lo necesario de cada dependencia con archivos propios (collect-all
        # tarda muchísimo y agrega módulos que no se usan).
        "--collect-data",
        "faster_whisper",
        "--collect-binaries",
        "ctranslate2",
        "--collect-binaries",
        "onnxruntime",
        "--collect-binaries",
        "sounddevice",
        "--collect-binaries",
        "miniaudio",
        "--collect-submodules",
        "comtypes",
        "--collect-submodules",
        "edge_tts",
        "--hidden-import",
        "comtypes.stream",
        "--hidden-import",
        "comtypes.client",
        "--hidden-import",
        "sounddevice",
        "--hidden-import",
        "miniaudio",
    ]
    for module in QT_EXCLUDES:
        command += ["--exclude-module", module]
    if icon.exists():
        command += ["--icon", str(icon)]
    command.append("--onefile" if args.onefile else "--onedir")
    if args.console:
        command.append("--console")

    print("Construyendo… (puede tardar varios minutos)", flush=True)
    started = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT)
    elapsed = time.perf_counter() - started
    if result.returncode != 0:
        print(f"Falló el empaquetado (código {result.returncode})", flush=True)
        return result.returncode

    exe = ROOT / "dist" / "Miky" / "Miky.exe"
    if not exe.exists():
        exe = ROOT / "dist" / "Miky.exe"
    if exe.exists():
        size_mb = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file()) / (1024 * 1024)
        print(f"Listo en {elapsed:.0f} s: {exe}", flush=True)
        print(f"Tamaño de la carpeta: {size_mb:.0f} MB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
