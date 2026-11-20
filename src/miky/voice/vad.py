"""Detección de actividad de voz (VAD) y segmentación de frases.

Se usa Silero VAD por ONNX (2 MB, ~1 ms por bloque de 32 ms, sin torch). Si el
modelo o onnxruntime no están, cae a un detector por energía que funciona
aceptablemente en un cuarto silencioso.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from .. import log as log_mod

log = log_mod.get("miky.vad")

TARGET_RATE = 16000
CHUNK = 512  # muestras por bloque a 16 kHz (32 ms)


@dataclass
class Segment:
    audio: np.ndarray
    duration_s: float

    @property
    def samples(self) -> int:
        return int(self.audio.size)


class ChunkBuffer:
    """Reagrupa el audio en bloques exactos de 512 muestras.

    El micrófono suele entregar bloques de 512 muestras *a 48 kHz* que, al
    remuestrearse a 16 kHz, quedan en ~171 muestras. El VAD de Silero exige
    bloques de 512 a 16 kHz; si se le pasan bloques cortos rellenados con
    silencio, las probabilidades caen y no detecta nada (el ícono "escucha"
    pero nunca pasa nada).
    """

    def __init__(self, size: int = CHUNK) -> None:
        self.size = size
        self._pending = np.zeros(0, dtype=np.float32)

    def feed(self, samples: np.ndarray) -> list[np.ndarray]:
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return []
        if self._pending.size:
            self._pending = np.concatenate((self._pending, samples))
        else:
            self._pending = samples
        blocks: list[np.ndarray] = []
        while self._pending.size >= self.size:
            blocks.append(self._pending[: self.size].copy())
            self._pending = self._pending[self.size :]
        # Si el consumidor se atrasó, no acumular memoria sin límite.
        if self._pending.size > self.size * 200:
            self._pending = self._pending[-self.size :]
        return blocks

    def reset(self) -> None:
        self._pending = np.zeros(0, dtype=np.float32)

    @property
    def pending_samples(self) -> int:
        return int(self._pending.size)


def find_silero_model() -> Path | None:
    """Busca el modelo ONNX del VAD.

    Se empaqueta con Miky (`data/models/silero_vad.onnx`) para no depender del
    paquete `silero_vad`, que arrastra PyTorch entero. Si alguien quiere usar
    otra versión, puede dejarla en `%APPDATA%\\Miky\\models`.
    """
    from .. import paths

    for candidate in (
        paths.data_dir() / "models" / "silero_vad.onnx",
        paths.models_dir() / "silero_vad.onnx",
    ):
        if candidate.exists():
            return candidate
    return None


class _BaseSegmenter:
    def process(self, chunk: np.ndarray) -> list[Segment]:  # pragma: no cover
        raise NotImplementedError

    def reset(self) -> None:  # pragma: no cover
        pass

    def flush(self) -> list[Segment]:
        return []

    # ---------- para la transcripción especulativa ----------

    @property
    def active(self) -> bool:
        """¿Hay una frase en curso?"""
        return bool(getattr(self, "_active", False))

    @property
    def silence_samples(self) -> int:
        """Cuántas muestras de silencio lleva la frase en curso."""
        return int(getattr(self, "_silence", 0))

    def pending_audio(self) -> np.ndarray:
        """Audio acumulado de la frase en curso (copia)."""
        buffer = getattr(self, "_buffer", None)
        if not buffer:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(list(buffer)).astype(np.float32, copy=False)


class EnergySegmenter(_BaseSegmenter):
    """Respaldo simple por energía con piso de ruido adaptativo."""

    def __init__(
        self,
        threshold: float = 0.5,
        min_silence_ms: int = 650,
        min_speech_ms: int = 220,
        pre_roll_ms: int = 260,
        max_speech_s: float = 20.0,
    ) -> None:
        self.min_silence_samples = int(min_silence_ms / 1000 * TARGET_RATE)
        self.min_speech_samples = int(min_speech_ms / 1000 * TARGET_RATE)
        self.pre_roll_chunks = max(1, int(pre_roll_ms / 1000 * TARGET_RATE / CHUNK))
        self.max_speech_samples = int(max_speech_s * TARGET_RATE)
        self.floor = 0.006
        self.factor = 2.2 + (0.5 - threshold) * 2.0
        self._pre: collections.deque[np.ndarray] = collections.deque(maxlen=self.pre_roll_chunks)
        self._active = False
        self._buffer: list[np.ndarray] = []
        self._silence = 0
        self._speech = 0

    def reset(self) -> None:
        self._pre.clear()
        self._buffer.clear()
        self._active = False
        self._silence = 0
        self._speech = 0

    def process(self, chunk: np.ndarray) -> list[Segment]:
        rms = float(np.sqrt(np.mean(chunk**2)) + 1e-9)
        self.floor = min(max(self.floor * 0.995 + rms * 0.005, 0.0008), 0.08)
        is_speech = rms > max(self.floor * self.factor, 0.0055)

        finished: list[Segment] = []

        if not self._active:
            self._pre.append(chunk)
            if is_speech:
                self._speech = chunk.size
                self._active = True
                self._buffer = list(self._pre)
                self._pre.clear()
                self._silence = 0
            return finished

        self._buffer.append(chunk)
        if is_speech:
            self._speech += chunk.size
            self._silence = 0
        else:
            self._silence += chunk.size

        total = sum(item.size for item in self._buffer)
        if self._silence >= self.min_silence_samples or total >= self.max_speech_samples:
            segment = self._close()
            if segment is not None:
                finished.append(segment)
        return finished

    def flush(self) -> list[Segment]:
        segment = self._close()
        return [segment] if segment is not None else []

    def _close(self) -> Segment | None:
        audio = np.concatenate(self._buffer) if self._buffer else np.zeros(0, dtype=np.float32)
        speech_samples = self._speech
        self._buffer = []
        self._active = False
        self._silence = 0
        self._speech = 0
        self._pre.clear()
        if speech_samples < self.min_speech_samples or audio.size == 0:
            return None
        return Segment(audio=audio, duration_s=audio.size / TARGET_RATE)


class SileroSegmenter(_BaseSegmenter):
    """Silero VAD v5 sobre onnxruntime, con máquina de estados propia.

    Detalle importante del modelo v5: no recibe 512 muestras, recibe 512 más las
    últimas 64 del bloque anterior (contexto). Si se le pasan solo 512, devuelve
    probabilidades bajísimas y el VAD no detecta nada.
    """

    CONTEXT = 64

    def __init__(
        self,
        model_path: Path,
        threshold: float = 0.5,
        min_silence_ms: int = 650,
        min_speech_ms: int = 220,
        pre_roll_ms: int = 260,
        max_speech_s: float = 20.0,
    ) -> None:
        import onnxruntime

        # Un solo hilo: el VAD tiene que convivir con el hilo de audio de REAPER.
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"], sess_options=options
        )
        self._input_names = {item.name for item in self._session.get_inputs()}
        self.threshold = threshold
        self.neg_threshold = max(0.15, threshold - 0.15)
        self.min_silence_samples = int(min_silence_ms / 1000 * TARGET_RATE)
        self.min_speech_samples = int(min_speech_ms / 1000 * TARGET_RATE)
        self.pre_roll_chunks = max(1, int(pre_roll_ms / 1000 * TARGET_RATE / CHUNK))
        self.max_speech_samples = int(max_speech_s * TARGET_RATE)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(self.CONTEXT, dtype=np.float32)
        self._pre: collections.deque[np.ndarray] = collections.deque(maxlen=self.pre_roll_chunks)
        self._buffer: list[np.ndarray] = []
        self._active = False
        self._silence = 0
        self._speech = 0

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(self.CONTEXT, dtype=np.float32)
        self._pre.clear()
        self._buffer.clear()
        self._active = False
        self._silence = 0
        self._speech = 0

    def _probability(self, chunk: np.ndarray) -> float:
        audio = chunk.astype(np.float32, copy=False)
        if audio.size != CHUNK:
            audio = np.pad(audio, (0, max(0, CHUNK - audio.size)))[:CHUNK]
        window = np.concatenate([self._context, audio]).reshape(1, -1)
        feeds: dict[str, Any] = {"input": window}
        if "state" in self._input_names:
            feeds["state"] = self._state
        if "sr" in self._input_names:
            feeds["sr"] = np.array(TARGET_RATE, dtype=np.int64)
        outputs = self._session.run(None, feeds)
        probability = float(np.asarray(outputs[0]).reshape(-1)[0])
        if len(outputs) > 1:
            self._state = np.asarray(outputs[1], dtype=np.float32)
        self._context = window[0, -self.CONTEXT :].copy()
        return probability

    def process(self, chunk: np.ndarray) -> list[Segment]:
        probability = self._probability(chunk)
        finished: list[Segment] = []

        if not self._active:
            self._pre.append(chunk)
            if probability >= self.threshold:
                self._active = True
                self._speech = chunk.size
                self._buffer = list(self._pre)
                self._pre.clear()
                self._silence = 0
            return finished

        self._buffer.append(chunk)
        if probability >= self.threshold:
            self._speech += chunk.size
            self._silence = 0
        else:
            self._silence += chunk.size
            if probability < self.neg_threshold:
                self._speech += 0

        total = sum(item.size for item in self._buffer)
        if self._silence >= self.min_silence_samples or total >= self.max_speech_samples:
            segment = self._close()
            if segment is not None:
                finished.append(segment)
        return finished

    def flush(self) -> list[Segment]:
        if not self._active:
            return []
        segment = self._close()
        return [segment] if segment is not None else []

    def _close(self) -> Segment | None:
        audio = np.concatenate(self._buffer) if self._buffer else np.zeros(0, dtype=np.float32)
        speech_samples = self._speech
        self._buffer = []
        self._active = False
        self._silence = 0
        self._speech = 0
        self._pre.clear()
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(self.CONTEXT, dtype=np.float32)
        if speech_samples < self.min_speech_samples or audio.size == 0:
            return None
        return Segment(audio=audio, duration_s=audio.size / TARGET_RATE)


def create_segmenter(
    threshold: float = 0.5,
    min_silence_ms: int = 650,
    min_speech_ms: int = 220,
    pre_roll_ms: int = 260,
    max_speech_s: float = 20.0,
) -> _BaseSegmenter:
    model = find_silero_model()
    if model is not None:
        try:
            segmenter = SileroSegmenter(
                model,
                threshold=threshold,
                min_silence_ms=min_silence_ms,
                min_speech_ms=min_speech_ms,
                pre_roll_ms=pre_roll_ms,
                max_speech_s=max_speech_s,
            )
            log.info("VAD: Silero ONNX (%s)", model.name)
            return segmenter
        except Exception as exc:  # noqa: BLE001
            log.warning("no pude cargar Silero VAD (%s), uso detector por energía", exc)
    else:
        log.warning("no encontré silero_vad.onnx, uso detector por energía")
    return EnergySegmenter(
        threshold=threshold,
        min_silence_ms=min_silence_ms,
        min_speech_ms=min_speech_ms,
        pre_roll_ms=pre_roll_ms,
        max_speech_s=max_speech_s,
    )
