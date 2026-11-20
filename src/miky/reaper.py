"""Descubrimiento de REAPER, instalación del puente y lanzamiento.

Todo lo que la app sabe del sistema operativo está acá: encontrar el ejecutable
de REAPER, su carpeta de recursos, instalar el script del puente y abrir REAPER
con el puente corriendo. Nada más.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from . import __version__, log as log_mod, paths

log = log_mod.get("miky.reaper")

BRIDGE_SUBFOLDER = "Miky"
BRIDGE_FILENAME = "miky_bridge.lua"
STARTUP_FILENAME = "__startup.lua"
STARTUP_BEGIN = "-- >>> Miky bridge (bloque generado: no editar a mano) >>>"
STARTUP_END = "-- <<< Miky bridge <<<"


@dataclass
class ReaperInstall:
    exe: Path | None
    resource_path: Path | None

    @property
    def found(self) -> bool:
        return self.exe is not None

    @property
    def bridge_dir(self) -> Path | None:
        if not self.resource_path:
            return None
        return self.resource_path / "Scripts" / BRIDGE_SUBFOLDER

    @property
    def bridge_path(self) -> Path | None:
        if not self.resource_path:
            return None
        return self.resource_path / "Scripts" / BRIDGE_SUBFOLDER / BRIDGE_FILENAME

    @property
    def installed(self) -> bool:
        path = self.bridge_path
        return bool(path and path.exists())

    def installed_version(self) -> str:
        path = self.bridge_path
        if not path or not path.exists():
            return ""
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for _ in range(6):
                    line = handle.readline()
                    if "Miky bridge v" in line:
                        return line.split("Miky bridge v", 1)[1].strip()
        except OSError:
            return ""
        return ""


# ---------------------------------------------------------------- búsqueda


def _registry_candidates() -> list[Path]:
    if sys.platform != "win32":
        return []
    candidates: list[Path] = []
    try:
        import winreg
    except ImportError:
        return candidates

    for root, key in (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\REAPER"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\REAPER"),
    ):
        try:
            with winreg.OpenKey(root, key) as handle:
                value, _ = winreg.QueryValueEx(handle, "")
            if value:
                candidates.append(Path(value))
        except OSError:
            continue
    return candidates


def _common_candidates() -> list[Path]:
    result = []
    for base in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(r"C:\REAPER"),
    ):
        for name in ("REAPER (x64)", "REAPER"):
            result.append(base / name)
    return result


def find_install(install_path: str = "", resource_path: str = "") -> ReaperInstall:
    exe: Path | None = None
    for candidate in ([Path(install_path)] if install_path else []) + _registry_candidates() + _common_candidates():
        path = candidate / "reaper.exe" if candidate.name.lower() != "reaper.exe" else candidate
        if path.exists():
            exe = path
            break

    resource: Path | None = None
    if resource_path:
        candidate = Path(resource_path)
        if candidate.exists():
            resource = candidate
    if resource is None and exe is not None and (exe.parent / "reaper.ini").exists():
        resource = exe.parent  # instalación portable
    if resource is None:
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate = Path(appdata) / "REAPER"
            if (candidate / "reaper.ini").exists():
                resource = candidate
    return ReaperInstall(exe=exe, resource_path=resource)


# ---------------------------------------------------------------- proceso


class _ProcessEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def reaper_pids() -> list[int]:
    """PIDs de reaper.exe, sin lanzar procesos externos."""
    if sys.platform != "win32":
        return []
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (0, -1):
        return []
    pids: list[int] = []
    entry = _ProcessEntry32()
    entry.dwSize = ctypes.sizeof(_ProcessEntry32)
    try:
        if kernel32.Process32First(snapshot, ctypes.byref(entry)):
            while True:
                if entry.szExeFile.lower() == b"reaper.exe":
                    pids.append(int(entry.th32ProcessID))
                if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return pids


def is_reaper_running() -> bool:
    return bool(reaper_pids())


def launch_reaper(install: ReaperInstall, with_bridge: bool = True) -> bool:
    if not install.exe:
        log.error("no encontré reaper.exe")
        return False
    args = [str(install.exe)]
    if with_bridge and install.bridge_path and install.bridge_path.exists():
        args.append(str(install.bridge_path))
    try:
        subprocess.Popen(args, cwd=str(install.exe.parent), close_fds=True)
    except OSError as exc:
        log.error("no pude abrir REAPER: %s", exc)
        return False
    log.info("REAPER lanzado: %s", "con puente" if len(args) > 1 else "sin puente")
    return True


# ---------------------------------------------------------------- puente


def bridge_source_path() -> Path | None:
    bundled = paths.bundled_bridge()
    if bundled.exists():
        return bundled
    # Respaldo para desarrollo: el archivo generado en el repo.
    repo_build = paths.package_dir().parent.parent / "reaper" / "build" / BRIDGE_FILENAME
    if repo_build.exists():
        return repo_build
    return None


def install_bridge(install: ReaperInstall) -> tuple[bool, str]:
    if not install.resource_path:
        return False, "No encontré la carpeta de recursos de REAPER."
    source = bridge_source_path()
    if source is None:
        return False, "Falta el archivo del puente (miky_bridge.lua). Corré tools/build_lua.py."

    target_dir = install.resource_path / "Scripts" / BRIDGE_SUBFOLDER
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_dir / BRIDGE_FILENAME)
    except OSError as exc:
        return False, f"No pude copiar el puente: {exc}"

    startup_ok, startup_msg = _patch_startup(install.resource_path)
    if not startup_ok:
        return False, startup_msg
    return True, f"Puente instalado en {target_dir}"


def _patch_startup(resource_path: Path) -> tuple[bool, str]:
    """Agrega un bloque al __startup.lua de REAPER (sin tocar lo que ya haya)."""
    startup = resource_path / "Scripts" / STARTUP_FILENAME
    bridge_rel = f"Scripts/{BRIDGE_SUBFOLDER}/{BRIDGE_FILENAME}"
    block = (
        f"{STARTUP_BEGIN}\n"
        "-- Arranca el puente de Miky si está instalado.\n"
        "do\n"
        "  local ok, err\n"
        "  local rp = reaper.GetResourcePath()\n"
        f'  local path = rp .. "/{bridge_rel}"\n'
        '  local f = io.open(path, "r")\n'
        "  if f then\n"
        "    f:close()\n"
        "    ok, err = pcall(dofile, path)\n"
        '    if not ok then reaper.ShowConsoleMsg("[Miky] error al iniciar el puente: " .. tostring(err) .. "\\n") end\n'
        "  end\n"
        "end\n"
        f"{STARTUP_END}\n"
    )
    try:
        if startup.exists():
            current = startup.read_text(encoding="utf-8", errors="replace")
            if STARTUP_BEGIN in current:
                return True, "startup ya configurado"
            if not current.endswith("\n"):
                current += "\n"
            startup.write_text(current + "\n" + block, encoding="utf-8")
        else:
            startup.write_text(block, encoding="utf-8")
    except OSError as exc:
        return False, f"No pude escribir {STARTUP_FILENAME}: {exc}"
    return True, "startup configurado"


def uninstall_bridge(install: ReaperInstall) -> tuple[bool, str]:
    if not install.resource_path:
        return False, "No encontré la carpeta de recursos de REAPER."
    target = install.resource_path / "Scripts" / BRIDGE_SUBFOLDER / BRIDGE_FILENAME
    try:
        target.unlink(missing_ok=True)
        try:
            target.parent.rmdir()
        except OSError:
            pass
    except OSError as exc:
        return False, f"No pude borrar el puente: {exc}"

    startup = install.resource_path / "Scripts" / STARTUP_FILENAME
    if startup.exists():
        try:
            text = startup.read_text(encoding="utf-8", errors="replace")
            if STARTUP_BEGIN in text and STARTUP_END in text:
                before, rest = text.split(STARTUP_BEGIN, 1)
                _, after = rest.split(STARTUP_END, 1)
                startup.write_text(before.rstrip() + "\n" + after.lstrip(), encoding="utf-8")
        except OSError:
            pass
    return True, "Puente desinstalado"


def ensure_bridge_ready(install: ReaperInstall) -> tuple[bool, str]:
    """Instala el puente si hace falta. Devuelve (ok, mensaje)."""
    if not install.resource_path:
        return False, "No encontré la carpeta de recursos de REAPER (¿está instalado?)"
    if install.installed and install.installed_version() == __version__:
        return True, "Puente al día"
    return install_bridge(install)


def wait_for_bridge(client, timeout_s: float = 15.0):
    """Espera a que el puente responda. Devuelve el BridgeStatus final."""
    return client.wait_until_alive(timeout_s=timeout_s)


def sleep_ms(ms: int) -> None:
    time.sleep(ms / 1000.0)
