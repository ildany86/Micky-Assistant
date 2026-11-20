"""Cliente del puente con REAPER (IPC por archivos).

La app escribe `requests/<id>.req.json` y el puente ReaScript responde con
`responses/<id>.res.json`. El latido (`status.json`) indica si el puente está
vivo, qué proyecto tiene abierto y si está ocupado (por ejemplo, renderizando).

Este módulo no sabe nada de REAPER: solo habla el protocolo.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import log as log_mod
from . import paths

log = log_mod.get("miky.bridge")

PROTOCOL_VERSION = 1
MAX_STEPS = 32
ID_PREFIX = "m"


class BridgeError(RuntimeError):
    """Error de transporte con el puente (no de un comando en particular)."""


class BridgeNotRunning(BridgeError):
    pass


class BridgeTimeout(BridgeError):
    pass


class BridgeProtocolError(BridgeError):
    pass


@dataclass
class StepOutcome:
    command: str
    ok: bool
    result: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    @property
    def message(self) -> str:
        if self.ok:
            return ""
        if self.error:
            return str(self.error.get("message") or self.error.get("code") or "error")
        return "error"


@dataclass
class BridgeReply:
    request_id: str
    ok: bool
    steps: list[StepOutcome]
    error: dict[str, Any] | None = None
    elapsed_ms: float = 0.0

    @property
    def first(self) -> StepOutcome | None:
        return self.steps[0] if self.steps else None

    @property
    def error_message(self) -> str:
        if self.error:
            return str(self.error.get("message") or self.error.get("code") or "")
        failed = next((s for s in self.steps if not s.ok), None)
        return failed.message if failed else ""


@dataclass
class BridgeStatus:
    alive: bool = False
    bridge_version: str = ""
    protocol: int = 0
    reaper_version: str = ""
    project: str = ""
    project_path: str = ""
    busy: bool = False
    playing: bool = False
    recording: bool = False
    age_ms: float = 10**9
    last_error: str | None = None
    command_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        if not self.alive:
            return "REAPER desconectado"
        state = "renderizando" if self.busy else "listo"
        project = self.project or "(sin proyecto)"
        return f"REAPER {self.reaper_version} · {project} · {state}"


class BridgeClient:
    def __init__(
        self,
        request_dir: Path | None = None,
        response_dir: Path | None = None,
        status_path: Path | None = None,
        stale_ms: int = 3500,
        poll_interval: float = 0.008,
    ) -> None:
        self.request_dir = request_dir or paths.requests_dir()
        self.response_dir = response_dir or paths.responses_dir()
        self.status_path = status_path or paths.status_file()
        self.stale_ms = stale_ms
        self.poll_interval = poll_interval
        self._lock = threading.RLock()
        self._counter = 0

    # ---------------- estado ----------------

    def read_status(self, render_timeout_s: float = 1800.0) -> BridgeStatus:
        status = BridgeStatus()
        try:
            mtime = self.status_path.stat().st_mtime
        except OSError:
            return status

        status.age_ms = (time.time() - mtime) * 1000.0
        try:
            raw = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return status
        if not isinstance(raw, dict):
            return status

        status.raw = raw
        status.bridge_version = str(raw.get("bridge") or "")
        status.protocol = int(raw.get("protocol") or 0)
        status.reaper_version = str(raw.get("reaper") or "")
        status.project = str(raw.get("project") or "")
        status.project_path = str(raw.get("project_path") or "")
        status.busy = bool(raw.get("busy"))
        status.playing = bool(raw.get("playing"))
        status.recording = bool(raw.get("recording"))
        status.last_error = raw.get("last_error") or None
        status.command_count = int(raw.get("command_count") or 0)

        if status.busy:
            status.alive = status.age_ms <= render_timeout_s * 1000.0
        else:
            status.alive = status.age_ms <= self.stale_ms
        return status

    def wait_until_alive(self, timeout_s: float = 12.0) -> BridgeStatus:
        deadline = time.monotonic() + timeout_s
        status = self.read_status()
        while time.monotonic() < deadline:
            if status.alive:
                return status
            time.sleep(0.15)
            status = self.read_status()
        return status

    # ---------------- llamadas ----------------

    def call(
        self,
        steps: Sequence[tuple[str, dict[str, Any] | None] | str],
        timeout: float | None = None,
        require_alive: bool = True,
    ) -> BridgeReply:
        normalized: list[tuple[str, dict[str, Any]]] = []
        for step in steps:
            if isinstance(step, str):
                normalized.append((step, {}))
            else:
                command, args = step
                normalized.append((command, dict(args or {})))
        if not normalized:
            raise ValueError("no hay pasos para ejecutar")
        if len(normalized) > MAX_STEPS:
            raise ValueError(f"un pedido admite como máximo {MAX_STEPS} pasos")

        if require_alive:
            status = self.read_status()
            if not status.alive:
                # Pequeña tolerancia: el latido puede tardar un tick si el
                # puente está ejecutando algo pesado.
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline and not status.alive:
                    time.sleep(0.1)
                    status = self.read_status()
                if not status.alive:
                    raise BridgeNotRunning(
                        "El puente de REAPER no está activo. Abrí REAPER con Miky o ejecutá el script del puente."
                    )

        request_id = self._new_id()
        request_path = self.request_dir / f"{request_id}.req.json"
        response_path = self.response_dir / f"{request_id}.res.json"
        payload = {
            "v": PROTOCOL_VERSION,
            "id": request_id,
            "steps": [{"cmd": command, "args": args} for command, args in normalized],
        }

        with self._lock:
            self._ensure_dirs()
            self._write_atomic(request_path, json.dumps(payload, ensure_ascii=False))
            started = time.monotonic()
            effective_timeout = timeout or self._default_timeout(normalized)
            reply = self._await_response(request_path, response_path, request_id, effective_timeout)
            reply.elapsed_ms = (time.monotonic() - started) * 1000.0
            return reply

    def call_one(
        self,
        command: str,
        args: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> BridgeReply:
        return self.call([(command, args or {})], timeout=timeout)

    # ---------------- internos ----------------

    def _new_id(self) -> str:
        self._counter = (self._counter + 1) % 100000
        return f"{ID_PREFIX}{int(time.time() * 1000)}-{os.getpid() % 100000}-{self._counter:05d}"

    def _default_timeout(self, steps: Iterable[tuple[str, dict[str, Any]]]) -> float:
        timeout = 30.0
        for command, _args in steps:
            if command.startswith("render."):
                return 1800.0
        return timeout

    def _ensure_dirs(self) -> None:
        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.response_dir.mkdir(parents=True, exist_ok=True)

    def _write_atomic(self, target: Path, text: str) -> None:
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)

    def _await_response(
        self,
        request_path: Path,
        response_path: Path,
        request_id: str,
        timeout: float,
    ) -> BridgeReply:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if response_path.exists():
                try:
                    raw = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    time.sleep(self.poll_interval)
                    continue
                self._cleanup(response_path, request_path)
                return self._parse_response(raw, request_id)

            if not request_path.exists():
                # El puente tomó el pedido y lo borró, pero todavía no respondió.
                pass
            time.sleep(self.poll_interval)

        self._cleanup(None, request_path)
        raise BridgeTimeout(
            f"REAPER no respondió en {timeout:.1f} s. "
            "Puede estar renderizando, o tener un diálogo abierto (por ejemplo un error de audio): "
            "cerralo y volvé a pedirlo."
        )

    def _cleanup(self, response: Path | None, request: Path | None) -> None:
        for path in (response, request):
            if path is None:
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _parse_response(self, raw: Any, request_id: str) -> BridgeReply:
        if not isinstance(raw, dict):
            raise BridgeProtocolError("respuesta del puente con formato inválido")
        steps_raw = raw.get("results")
        if steps_raw is None:
            steps_raw = []
        if not isinstance(steps_raw, list):
            raise BridgeProtocolError("respuesta del puente sin lista de resultados")

        steps: list[StepOutcome] = []
        for item in steps_raw:
            if not isinstance(item, dict):
                continue
            steps.append(
                StepOutcome(
                    command=str(item.get("cmd") or ""),
                    ok=bool(item.get("ok")),
                    result=item.get("result") if isinstance(item.get("result"), dict) else {},
                    error=item.get("error") if isinstance(item.get("error"), dict) else None,
                )
            )

        error = raw.get("error") if isinstance(raw.get("error"), dict) else None
        return BridgeReply(
            request_id=str(raw.get("id") or request_id),
            ok=bool(raw.get("ok")),
            steps=steps,
            error=error,
            elapsed_ms=float(raw.get("elapsed_ms") or 0.0),
        )


def ping(client: BridgeClient, timeout: float = 3.0) -> dict[str, Any]:
    """Hace un ping y devuelve la info del puente. Lanza BridgeError si falla."""
    reply = client.call_one("ping", timeout=timeout)
    if not reply.ok or reply.first is None:
        raise BridgeError(reply.error_message or "el puente no respondió al ping")
    return reply.first.result
