"""Reconocimiento de voz local con faster-whisper (CPU, int8).

El modelo se carga una sola vez y se reutiliza. Nunca manda audio a internet.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from .. import log as log_mod

log = log_mod.get("miky.stt")

DEFAULT_MODEL = "base"
STUDIO_PROMPT = (
    # Ojo: no poner el nombre del asistente acá. Whisper lo toma como texto ya
    # dicho y directamente lo omite de la transcripción ("crea una pista…" sin
    # "Miky"), con lo cual la palabra clave deja de detectarse.
    "Órdenes de estudio de grabación en español rioplatense. "
    "REAPER, pista, pistas, canal, guitarra, bajo, batería, bombo, redo, hi-hat, "
    "overheads, voz, compresor, compresión, EQ, ecualizador, reverb, plugin, "
    "render, exportar, dB, BPM, compás, loop, monitoreo, armado, silenciar, paneo, "
    "ítem, ítems, toma, tomas, ruteo, matriz de ruteo, envío, envíos, envolvente, "
    "marcador, región, mezclador, master, MIDI, autotune."
)

_MODEL_HINTS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
}


class SttError(RuntimeError):
    pass


class FasterWhisperStt:
    def __init__(
        self,
        model_size: str = DEFAULT_MODEL,
        language: str = "es",
        compute_type: str = "int8",
        cpu_threads: int = 4,
        beam_size: int = 1,
    ) -> None:
        self.model_size = model_size if model_size in _MODEL_HINTS else DEFAULT_MODEL
        self.language = language
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.beam_size = beam_size
        self._model = None
        self._load_seconds = 0.0
        # El modelo no es thread-safe: la transcripción especulativa y la normal
        # comparten una sola instancia.
        self._lock = threading.Lock()

    # ---------- ciclo de vida ----------

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def description(self) -> str:
        return f"faster-whisper {self.model_size} ({self.compute_type})"

    def ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SttError(
                "Falta faster-whisper. Instalalo con: pip install faster-whisper"
            ) from exc

        started = time.monotonic()
        log.info("cargando modelo de voz %s (la primera vez puede tardar por la descarga)", self.model_size)
        try:
            self._model = WhisperModel(
                _MODEL_HINTS[self.model_size],
                device="cpu",
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
                num_workers=1,
            )
        except Exception as exc:  # noqa: BLE001
            raise SttError(f"No pude cargar el modelo de voz: {exc}") from exc
        self._load_seconds = time.monotonic() - started
        log.info("modelo de voz listo en %.1f s", self._load_seconds)

    def warmup(self) -> None:
        """Transcribe un segundo de silencio para que el primer pedido no pague la carga."""
        try:
            self.ensure_loaded()
            self.transcribe(np.zeros(16000, dtype=np.float32))
        except Exception as exc:  # noqa: BLE001
            log.debug("warmup de voz falló: %s", exc)

    # ---------- transcripción ----------

    def transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        hotwords: str | None = None,
    ) -> str:
        with self._lock:
            return self._transcribe(audio, language=language, hotwords=hotwords)

    def _transcribe(
        self,
        audio: np.ndarray,
        language: str | None = None,
        hotwords: str | None = None,
    ) -> str:
        self.ensure_loaded()
        if audio is None or audio.size == 0:
            return ""
        audio = np.asarray(audio, dtype=np.float32)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 0:
            audio = audio / max(peak, 0.2) * 0.9

        try:
            segments, _info = self._model.transcribe(
                audio,
                language=language or self.language,
                beam_size=self.beam_size,
                condition_on_previous_text=False,
                vad_filter=False,
                without_timestamps=True,
                initial_prompt=STUDIO_PROMPT,
                hotwords=hotwords or None,
                temperature=0.0,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except TypeError:
            # Versiones viejas de faster-whisper no aceptan hotwords.
            segments, _info = self._model.transcribe(
                audio,
                language=language or self.language,
                beam_size=self.beam_size,
                condition_on_previous_text=False,
                vad_filter=False,
                without_timestamps=True,
                initial_prompt=STUDIO_PROMPT,
                temperature=0.0,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:  # noqa: BLE001
            raise SttError(f"Error al transcribir: {exc}") from exc
        return _clean(text)


def _clean(text: str) -> str:
    text = " ".join(text.split())
    for prefix in ("Miky,", "Miky:", "miky,"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    return text


def is_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False
