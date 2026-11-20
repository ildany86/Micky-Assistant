"""Captura de micrófono con sounddevice (WASAPI en Windows).

Regla de oro: el micrófono del asistente NO puede ser el mismo dispositivo que
REAPER está usando por ASIO en modo exclusivo. Por eso la selección automática
prefiere WASAPI y, si puede, el micrófono interno de la notebook antes que la
interfaz que está usando el DAW.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np

from .. import log as log_mod

log = log_mod.get("miky.audio")

TARGET_RATE = 16000
BLOCK = 512

PREFERRED_NAME_HINTS = ("realtek", "microfono", "micrófono", "microphone", "mic ")

# Pseudo-dispositivos que Windows agrega y que redirigen al predeterminado del
# sistema. Elegirlos es una trampa: el "Asignador de sonido" terminó haciendo
# que Miky escuche por la interfaz (el dispositivo predeterminado) en vez del
# micrófono interno.
PSEUDO_DEVICE_HINTS = (
    "sound mapper",
    "asignador de sonido",
    "primary sound",
    "controlador primario",
    "default device",
    "dispositivo predeterminado",
    "mezcla estéreo",
    "mezcla estereo",
    "stereo mix",
    "what u hear",
    "loopback",
    "loop-back",
)


def is_pseudo_device(name: str) -> bool:
    lowered = (name or "").lower()
    return any(hint in lowered for hint in PSEUDO_DEVICE_HINTS)


@dataclass
class Device:
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    default_samplerate: float
    is_default: bool = False

    @property
    def label(self) -> str:
        return f"{self.index}: {self.name} [{self.hostapi}]"


def _sounddevice():
    import sounddevice as sd

    return sd


def list_input_devices() -> list[Device]:
    try:
        sd = _sounddevice()
        hostapis = sd.query_hostapis()
        default_input = sd.default.device[0]
        devices: list[Device] = []
        for index, info in enumerate(sd.query_devices()):
            if info["max_input_channels"] <= 0:
                continue
            name = str(info["name"]).strip()
            if is_pseudo_device(name):
                continue
            devices.append(
                Device(
                    index=index,
                    name=name,
                    hostapi=str(hostapis[info["hostapi"]]["name"]),
                    max_input_channels=int(info["max_input_channels"]),
                    default_samplerate=float(info["default_samplerate"]),
                    is_default=(index == default_input),
                )
            )
        return devices
    except Exception as exc:  # noqa: BLE001 - sin audio disponible
        log.warning("no pude enumerar dispositivos de audio: %s", exc)
        return []


def pick_input_device(preferred: str = "") -> tuple[int | None, str]:
    """Devuelve (índice, motivo). Prioriza WASAPI y el micrófono interno."""
    devices = list_input_devices()
    if not devices:
        return None, "no hay dispositivos de entrada"

    if preferred and is_pseudo_device(preferred):
        preferred = ""

    if preferred:
        needle = preferred.lower()
        for device in devices:
            if needle in device.name.lower():
                return device.index, f"elegido por configuración: {device.label}"

    wasapi = [d for d in devices if "wasapi" in d.hostapi.lower()]
    for device in wasapi:
        if any(hint in device.name.lower() for hint in PREFERRED_NAME_HINTS):
            return device.index, f"micrófono interno por WASAPI: {device.label}"

    # Si solo hay una interfaz (por ejemplo, una placa sin micrófono interno),
    # se usa igual, pero se avisa en el motivo.
    if wasapi:
        device = next((d for d in wasapi if d.is_default), wasapi[0])
        return device.index, f"primer WASAPI disponible: {device.label}"

    default = next((d for d in devices if d.is_default), devices[0])
    return default.index, f"dispositivo por defecto del sistema: {default.label}"


def resample(audio: np.ndarray, source_rate: int, target_rate: int = TARGET_RATE) -> np.ndarray:
    """Resampleo simple y suficiente para voz."""
    if source_rate == target_rate or audio.size == 0:
        return audio.astype(np.float32, copy=False)

    ratio = source_rate / target_rate
    if abs(ratio - round(ratio)) < 1e-6 and round(ratio) > 1:
        factor = int(round(ratio))
        usable = (audio.size // factor) * factor
        if usable == 0:
            return np.zeros(0, dtype=np.float32)
        filtered = audio[:usable].reshape(-1, factor).mean(axis=1)
        return filtered.astype(np.float32, copy=False)

    duration = audio.size / float(source_rate)
    target_size = max(1, int(duration * target_rate))
    source_positions = np.linspace(0.0, duration, num=audio.size, endpoint=False)
    target_positions = np.linspace(0.0, duration, num=target_size, endpoint=False)
    return np.interp(target_positions, source_positions, audio).astype(np.float32, copy=False)


class AudioCapture:
    """Lee el micrófono en bloques de 512 muestras a 16 kHz."""

    def __init__(
        self,
        device_index: int | None = None,
        samplerate: int = TARGET_RATE,
        blocksize: int = BLOCK,
    ) -> None:
        self.device_index = device_index
        self.requested_rate = samplerate
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=64)
        self._stream: Any = None
        self._lock = threading.Lock()
        self._level = 0.0

    # ---------- ciclo de vida ----------

    def start(self) -> None:
        sd = _sounddevice()
        with self._lock:
            if self._stream is not None:
                return
            errors: list[str] = []
            for rate in (self.requested_rate, 48000, 44100):
                try:
                    stream = sd.InputStream(
                        device=self.device_index,
                        samplerate=rate,
                        channels=1,
                        dtype="float32",
                        blocksize=self.blocksize,
                        callback=self._callback,
                    )
                    stream.start()
                    self._stream = stream
                    self.samplerate = rate
                    log.info("micrófono abierto a %d Hz (device=%s)", rate, self.device_index)
                    return
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{rate} Hz: {exc}")
            raise RuntimeError("no pude abrir el micrófono: " + " | ".join(errors))

    def stop(self) -> None:
        with self._lock:
            if self._stream is None:
                return
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        return self._level

    # ---------- datos ----------

    def _callback(self, indata, _frames, _time, status) -> None:  # noqa: ANN001
        if status:
            log.debug("audio status: %s", status)
        chunk = np.asarray(indata[:, 0], dtype=np.float32).copy()
        self._level = float(np.sqrt(np.mean(chunk**2)) + 1e-9)
        try:
            self.queue.put_nowait(chunk)
        except queue.Full:
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(chunk)
            except queue.Empty:
                pass

    def read(self, timeout: float = 0.5) -> np.ndarray | None:
        """Devuelve el siguiente bloque ya remuestreado a 16 kHz."""
        try:
            chunk = self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if self.samplerate != TARGET_RATE:
            chunk = resample(chunk, self.samplerate, TARGET_RATE)
        return chunk
