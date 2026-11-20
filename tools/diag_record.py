"""Diagnóstico: ¿qué ventana abre REAPER cuando se manda grabar?

Levanta REAPER con el puente, arma una pista, manda `transport.record` y lista
las ventanas visibles del proceso cada medio segundo. Sirve para descubrir
diálogos modales que bloquean el puente.

Uso: python tools/diag_record.py
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from miky import reaper  # noqa: E402
from miky.bridge import BridgeClient, BridgeError, BridgeTimeout  # noqa: E402

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def visible_windows(pids: set[int]) -> list[str]:
    found: list[str] = []

    def callback(hwnd, _lparam):  # noqa: ANN001
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            title = buffer.value.strip()
            if title:
                found.append(f"{title}  (hwnd={hwnd}, pid={pid.value})")
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def main() -> int:
    install = reaper.find_install()
    if not install.exe or not install.bridge_path:
        print("REAPER o puente no encontrados")
        return 2
    if reaper.is_reaper_running():
        print("Cerrá REAPER antes de correr esto")
        return 2

    print("abriendo REAPER…")
    subprocess.Popen(
        [str(install.exe), "-new", str(install.bridge_path)],
        cwd=str(install.exe.parent),
        close_fds=True,
    )
    client = BridgeClient()
    if not client.wait_until_alive(timeout_s=30).alive:
        print("el puente no arrancó")
        return 1

    pids = set(reaper.reaper_pids())
    print("pids:", pids)

    def call(command: str, args: dict | None = None, timeout: float = 10.0):
        try:
            reply = client.call([(command, args or {})], timeout=timeout)
            print(f"  {command}: ok={reply.ok} {reply.first.result if reply.first else ''}")
            return reply
        except (BridgeTimeout, BridgeError) as exc:
            print(f"  {command}: FALLÓ ({exc})")
            return None

    call("track.add", {"name": "Prueba", "arm": True})
    call("track.set_input", {"track": "Prueba", "input": "mono:1"})

    print("\nventanas antes de grabar:")
    for line in visible_windows(pids):
        print("  -", line)

    print("\nmandando grabar…")
    call("transport.record", timeout=10.0)
    for step in range(3):
        time.sleep(0.5)
        windows = visible_windows(pids)
        print(f"  [{step * 0.5:.1f}s] {len(windows)} ventana(s)")
        for line in windows:
            print("      -", line)

    print("\nmandando parar…")
    call("transport.stop", timeout=15.0)
    for step in range(4):
        time.sleep(0.5)
        windows = visible_windows(pids)
        print(f"  [{step * 0.5:.1f}s] {len(windows)} ventana(s)")
        for line in windows:
            print("      -", line)
    call("state.get", timeout=8.0)

    print("\nrevisando si el puente sigue vivo…")
    status = client.read_status()
    print(f"  alive={status.alive} age={status.age_ms:.0f} ms last_error={status.last_error}")

    for pid in reaper.reaper_pids():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
