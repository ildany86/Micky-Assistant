"""Prueba de integración real contra REAPER.

Abre una instancia nueva de REAPER con el puente, ejecuta una batería de
comandos contra la API real (no el mock) y cierra todo al final.

Uso:
    python tools/live_test.py            # prueba completa
    python tools/live_test.py --keep     # no cierra REAPER al terminar

Escribe un informe en `research/live_test_report.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from miky import reaper  # noqa: E402
from miky.bridge import BridgeClient, BridgeError, BridgeTimeout  # noqa: E402

REPORT = ROOT / "research" / "live_test_report.json"


class LiveTest:
    def __init__(self, keep: bool = False) -> None:
        self.keep = keep
        self.client = BridgeClient()
        self.results: list[dict] = []
        self.failures = 0
        self.install = reaper.find_install()
        self.temp = Path(os.environ.get("TEMP", ".")) / "miky_live_test"
        # Arrancar siempre limpio: si quedan renders viejos, REAPER abre el
        # diálogo de "el archivo ya existe" y congela el puente.
        if self.temp.exists():
            import shutil

            shutil.rmtree(self.temp, ignore_errors=True)
        self.temp.mkdir(parents=True, exist_ok=True)
        self.project_file = self.temp / "miky_live_test.rpp"
        self.render_dir = self.temp / "render"

    # ---------- helpers ----------

    def call(self, command: str, args: dict | None = None, timeout: float = 30.0) -> dict:
        started = time.monotonic()
        try:
            reply = self.client.call([(command, args or {})], timeout=timeout)
        except (BridgeTimeout, BridgeError) as exc:
            self.results.append(
                {
                    "command": command,
                    "args": args or {},
                    "ok": False,
                    "error": str(exc),
                    "ms": round((time.monotonic() - started) * 1000, 1),
                }
            )
            self.failures += 1
            print(f"  [x] {command:<22} {exc}")
            return {"ok": False, "error": str(exc)}
        elapsed = round((time.monotonic() - started) * 1000, 1)
        first = reply.first
        ok = reply.ok and first is not None and first.ok
        entry = {
            "command": command,
            "args": args or {},
            "ok": ok,
            "ms": elapsed,
            "result": first.result if first else None,
            "error": (first.error if first and first.error else reply.error),
        }
        self.results.append(entry)
        if ok:
            summary = _summarize(first.result if first else {})
            print(f"  [ok] {command:<22} {elapsed:5.0f} ms  {summary}")
        else:
            self.failures += 1
            message = ""
            if first and first.error:
                message = first.error.get("message", "")
            elif reply.error:
                message = reply.error.get("message", "")
            print(f"  [x] {command:<22} {elapsed:5.0f} ms  {message}")
        return entry

    def expect_fail(self, command: str, args: dict | None = None, code: str = "") -> None:
        entry = self.call(command, args)
        error = entry.get("error") or {}
        got = error.get("code", "") if isinstance(error, dict) else ""
        if entry.get("ok"):
            self.failures += 1
            print(f"  [x] {command}: debía fallar y funcionó")
        elif code and got != code:
            self.failures += 1
            print(f"  [x] {command}: se esperaba {code} y llegó {got}")
        else:
            # Un fallo esperado no cuenta como falla de la prueba.
            self.failures -= 1
            entry["expected_failure"] = True
            print(f"  [ok] {command:<22} error esperado: {got}")

    def accept_any(self, command: str, args: dict | None = None, codes: tuple[str, ...] = ()) -> dict:
        """Como call(), pero un error de esos códigos también es un resultado válido."""
        entry = self.call(command, args)
        error = entry.get("error") or {}
        code = error.get("code", "") if isinstance(error, dict) else ""
        if not entry.get("ok") and code in codes:
            self.failures -= 1
            entry["accepted"] = code
            print(f"  [ok] {command:<22} devolvió {code} (esperado)")
        return entry

    # ---------- ciclo ----------

    def launch(self) -> bool:
        if reaper.is_reaper_running():
            pids = reaper.reaper_pids()
            print(f"[!] REAPER ya está corriendo (pid {pids}); cerralo para la prueba.")
            return False
        if not self.install.exe:
            print("[x] no encontré reaper.exe")
            return False
        bridge = self.install.bridge_path
        if not bridge or not bridge.exists():
            ok, message = reaper.install_bridge(self.install)
            print(f"[i] {message}")
            if not ok:
                return False
            bridge = self.install.bridge_path
        assert bridge is not None
        args = [str(self.install.exe), "-new", str(bridge)]
        print(f"[i] abriendo REAPER: {' '.join(args)}")
        subprocess.Popen(args, cwd=str(self.install.exe.parent), close_fds=True)
        return True

    def wait_bridge(self, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.client.read_status()
            if status.alive:
                print(f"[i] puente vivo en {time.monotonic() - (deadline - timeout):.1f} s")
                return True
            time.sleep(0.3)
        return False

    def run(self) -> int:
        print("=== Miky · prueba real contra REAPER ===\n")
        if not self.install.found:
            print("[x] REAPER no encontrado")
            return 2

        ok, message = reaper.ensure_bridge_ready(self.install)
        print(f"[i] puente: {message}")
        if not ok:
            return 2

        if not self.launch():
            return 2
        try:
            if not self.wait_bridge():
                print("[x] el puente no arrancó. Revisá si REAPER abrió una ventana de error.")
                return 1

            print("\n--- conexión y estado ---")
            self.call("ping")
            self.call("bridge.info")
            state = self.call("state.get")
            tracks = (state.get("result") or {}).get("tracks") or []
            print(f"[i] el proyecto arrancó con {len(tracks)} pistas")

            print("\n--- pistas ---")
            self.call("track.add", {"name": "Guitarra", "color": "azul"})
            self.call("track.add", {"name": "Batería", "color": "rojo"})
            self.call("track.add_many", {"names": ["Bombo", "Redo", "Hi-hat"]})
            self.call("track.rename", {"track": "Guitarra", "name": "Guitarra rítmica"})
            self.call("track.set_volume", {"track": "Batería", "db": -6})
            self.call("track.adjust_volume", {"track": "Batería", "delta_db": 2})
            self.call("track.set_pan", {"track": "Hi-hat", "pan": 35})
            self.call("track.set_input", {"track": "Guitarra rítmica", "input": "mono:1"})
            self.call("track.mute", {"track": "Redo", "state": True})
            self.call("track.solo", {"track": "Bombo", "state": True})
            self.call("track.arm", {"track": "Guitarra rítmica", "state": True})
            self.call("track.duplicate", {"track": "Bombo"})
            self.call("track.move", {"track": "Hi-hat", "to_index": 1})
            self.call("track.select", {"tracks": ["Guitarra rítmica", "Batería"]})
            self.call("track.set_monitor", {"track": "Guitarra rítmica", "mode": "normal"})
            self.expect_fail("track.mute", {"track": "Teclados"}, "track_not_found")

            print("\n--- plugins ---")
            self.call("fx.add", {"track": "Guitarra rítmica", "name": "ReaEQ"})
            self.call("fx.add", {"track": "Guitarra rítmica", "name": "ReaComp"})
            self.call("fx.list", {"track": "Guitarra rítmica"})
            self.call(
                "fx.set_param",
                {"track": "Guitarra rítmica", "fx": "ReaComp", "param": "threshold", "value": -18},
            )
            self.call("fx.bypass", {"track": "Guitarra rítmica", "fx": "ReaEQ", "enabled": False})
            self.expect_fail("fx.add", {"track": "Guitarra rítmica", "name": "PluginQueNoExiste"}, "fx_not_found")
            # Copia la pista con sus plugins ya cargados.
            self.call("track.add_like", {"track": "Guitarra rítmica", "name": "Guitarra doble"})

            print("\n--- transporte y proyecto ---")
            self.call("project.set_tempo", {"bpm": 96})
            self.call("project.set_metronome", {"enabled": True})
            self.call("transport.set_loop", {"start": 0.0, "finish": 4.0, "enabled": True})
            self.call("transport.set_position", {"bar": 3})
            self.call("transport.play")
            time.sleep(0.3)
            self.call("transport.stop")
            self.call("transport.goto_start")
            self.call("project.save_as", {"path": str(self.project_file)})
            self.call("project.undo")
            self.call("project.redo")

            print("\n--- ruteo ---")
            self.call("send.add", {"from": "Guitarra rítmica", "to": "Batería", "level_db": -12})
            self.call("send.set_level", {"from": "Guitarra rítmica", "to": "Batería", "db": -6})
            self.call("send.remove", {"from": "Guitarra rítmica", "to": "Batería"})
            self.expect_fail("send.remove", {"from": "Guitarra rítmica", "to": "Batería"}, "send_not_found")

            print("\n--- salidas físicas (monitoreo) ---")
            self.call("track.output", {"track": "Batería", "pair": 2, "level_db": -3})
            self.call("track.output", {"track": "Bombo", "pair": 2})
            self.expect_fail("track.output", {"track": "Batería", "pair": 2}, "output_exists")
            self.call("track.output_clear", {"track": "Batería"})
            self.call("track.output_clear", {"track": "Bombo"})

            print("\n--- marcadores ---")
            self.call("marker.add", {"name": "Estribillo"})
            self.call("region.add", {"name": "Coro", "start": 1.0, "finish": 3.0})
            self.call("transport.goto_marker", {"name": "estribillo"})
            self.expect_fail("transport.goto_marker", {"name": "Puente"}, "marker_not_found")

            print("\n--- grabar (0,5 s) ---")
            self.call("transport.record")
            time.sleep(0.5)
            self.call("transport.stop")

            print("\n--- edición de items ---")
            self.call("marker.add", {"name": "Corte", "position": 0.2})
            # El proyecto de prueba no tiene ítems: los comandos deben avisar
            # que hay que seleccionar uno, no romperse.
            self.expect_fail(
                "item.split_at_cursor", {"position": 0.25, "track": "Guitarra rítmica"}, "item_required"
            )
            self.expect_fail(
                "item.keep_between",
                {"track": "Guitarra rítmica", "start_marker": "Corte", "end": 1.0},
                "item_required",
            )

            print("\n--- render ---")
            self.call(
                "render.start",
                {
                    "mode": "entire",
                    "out_dir": str(self.render_dir),
                    "pattern": "miky_test",
                    "format": "wav",
                },
                timeout=180.0,
            )

            print("\n--- vista ---")
            self.call("view.mixer", {"visible": True})
            self.call("view.mixer", {"visible": False})
            self.call("view.routing", {"visible": True})
            self.call("view.routing", {"visible": False})

            print("\n--- renombrar por número ---")
            self.call("track.add", {"name": "Prueba numero"})
            self.call("track.rename", {"track": "-1", "name": "Renombrada por numero"})
            self.expect_fail("track.rename", {"track": "99", "name": "No existe"}, "track_not_found")

            print("\n--- plugins por descripción ---")
            self.accept_any("fx.add", {"track": "Guitarra rítmica", "name": "compresor"}, ("fx_candidates",))
            self.accept_any("fx.add", {"track": "Guitarra rítmica", "name": "ecualizador"}, ("fx_candidates",))

            print("\n--- índice de plugins ---")
            self.call("fx.installed", {"limit": 3})
            self.call("fx.search", {"query": "compresor", "limit": 3})
            self.expect_fail("fx.search", {"query": "zzzz"}, "fx_not_found")

            print("\n--- parámetros reales de un plugin ---")
            self.call("fx.add", {"track": "Guitarra rítmica", "name": "ReaComp"})
            self.call("fx.params", {"track": "Guitarra rítmica", "fx": "ReaComp", "limit": 6})

            print("\n--- niveles del medidor ---")
            self.call("transport.play")
            time.sleep(0.6)
            self.call("levels.get")
            self.call("transport.stop")

            print("\n--- limpieza ---")
            self.call("fx.remove", {"track": "Guitarra rítmica", "fx": "ReaEQ"})
            self.call("track.delete", {"track": "Hi-hat"})
            final = self.call("state.get")
            self.call("project.save")

            if not self.keep:
                print("\n--- cierre ---")
                self.call("app.quit", timeout=5.0)
                self._wait_exit()
            self._report(final)
        finally:
            if not self.keep:
                self._force_close()
        return 0 if self.failures == 0 else 1

    def _wait_exit(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not reaper.is_reaper_running():
                print("[i] REAPER cerró solo")
                return
            time.sleep(0.4)
        print("[!] REAPER no se cerró; lo cierro a la fuerza")

    def _force_close(self) -> None:
        if not reaper.is_reaper_running():
            return
        for pid in reaper.reaper_pids():
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
            except OSError:
                pass
        time.sleep(1.0)

    def _report(self, final: dict) -> None:
        rendered = sorted(str(path) for path in self.render_dir.glob("*")) if self.render_dir.exists() else []
        project_exists = self.project_file.exists()
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reaper_version": self.install.installed_version(),
            "bridge": self.install.bridge_path and str(self.install.bridge_path),
            "commands": self.results,
            "failures": self.failures,
            "rendered_files": rendered,
            "project_saved": project_exists,
            "final_state": (final or {}).get("result"),
        }
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[i] informe: {REPORT}")
        if rendered:
            print("[i] renderizó:")
            for path in rendered:
                size = Path(path).stat().st_size
                print(f"     {path}  ({size / 1024:.0f} KB)")
        else:
            print("[!] no aparecieron archivos renderizados")
        print(f"[i] proyecto guardado: {project_exists}")
        print(f"\n=== {'OK' if self.failures == 0 else str(self.failures) + ' fallas'} ===")


def _summarize(result: dict | None) -> str:
    if not result:
        return ""
    keys = ("name", "index", "track_count", "volume_db", "pan", "fx_count", "bpm", "position", "mode", "targets", "path")
    parts = [f"{key}={result[key]}" for key in keys if key in result]
    if not parts and "tracks" in result:
        parts = [f"tracks={len(result['tracks'])}"]
    if not parts and "fx" in result:
        parts = [f"fx={len(result['fx'])}"]
    if not parts and "results" in result:
        parts = [f"results={len(result['results'])}"]
    text = " ".join(str(part) for part in parts)
    return text[:80]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="no cerrar REAPER al terminar")
    args = parser.parse_args()
    return LiveTest(keep=args.keep).run()


if __name__ == "__main__":
    raise SystemExit(main())
