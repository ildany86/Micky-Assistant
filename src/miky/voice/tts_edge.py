"""Voz de respuesta con voces neuronales de Microsoft (edge-tts).

Ventaja: hay voces en español rioplatense y masculinas (`es-AR-TomasNeural`),
mucho mejores que las SAPI de Windows. Requiere internet, por eso siempre se usa
con la voz local como respaldo.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from typing import Callable

import numpy as np

from .. import log as log_mod
from . import pronounce

log = log_mod.get("miky.tts.edge")

DEFAULT_VOICE = "es-AR-TomasNeural"

# Voces curadas (las que suenan bien para un asistente).
VOICES: list[tuple[str, str, str]] = [
    ("es-AR-TomasNeural", "Tomás (Argentina, masculina)", "es-AR"),
    ("es-AR-ElenaNeural", "Elena (Argentina, femenina)", "es-AR"),
    ("es-MX-JorgeNeural", "Jorge (México, masculina)", "es-MX"),
    ("es-MX-DaliaNeural", "Dalia (México, femenina)", "es-MX"),
    ("es-ES-AlvaroNeural", "Álvaro (España, masculina)", "es-ES"),
    ("es-ES-ElviraNeural", "Elvira (España, femenina)", "es-ES"),
    ("es-PY-MarioNeural", "Mario (Paraguay, masculina)", "es-PY"),
]

VOICE_LABELS = {name: label for name, label, _locale in VOICES}

MAX_CACHE_ITEMS = 48
MAX_CACHE_BYTES = 400_000

# Frases que se repiten todo el tiempo: se sintetizan al arrancar para que la
# primera respuesta no espere. Se guardan como audio ya listo.
COMMON_PHRASES = [
    "Listo.",
    "Dale.",
    "Paré.",
    "Grabando.",
    "Listo, ya está.",
    "No pude hacerlo.",
    "Cancelado.",
    "Te escucho.",
    "No entendí.",
    "¿Estás listo para grabar?",
    "Listo, terminó el render.",
    "¿Arranco el render?",
]


def split_sentences(text: str, min_chars: int = 18) -> list[str]:
    """Parte el texto en oraciones razonables para hablar por partes.

    Las oraciones muy cortas se pegan a la siguiente: hablar de a tres palabras
    suena entrecortado.
    """
    import re

    raw = re.split(r"(?<=[.!?…:])\s+", (text or "").strip())
    parts: list[str] = []
    buffer = ""
    for piece in raw:
        piece = piece.strip()
        if not piece:
            continue
        buffer = f"{buffer} {piece}".strip() if buffer else piece
        if len(buffer) >= min_chars:
            parts.append(buffer)
            buffer = ""
    if buffer:
        if parts:
            parts[-1] = f"{parts[-1]} {buffer}".strip()
        else:
            parts.append(buffer)
    return parts or ([text.strip()] if text and text.strip() else [])


class EdgeTts:
    """Sintetiza en la nube y reproduce localmente por el dispositivo elegido."""

    name = "edge"

    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        rate: int = 0,
        output_device: str = "",
        fallback: Callable[[str], None] | None = None,
    ) -> None:
        self.voice = voice or DEFAULT_VOICE
        self.rate = max(-10, min(10, int(rate)))
        self.output_device = output_device
        self.fallback = fallback
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._speaking = threading.Event()
        self._cancel = threading.Event()
        self._available = False
        self._error = ""
        self._device_index: int | None = None
        self._rate_hint = f"{self.rate * 6:+d}%"
        self._cache: dict[str, bytes] = {}

    # ---------- ciclo de vida ----------

    def start(self) -> None:
        if self._thread is not None:
            return
        try:
            import edge_tts  # noqa: F401
            import miniaudio  # noqa: F401
        except ImportError as exc:
            self._error = f"falta edge-tts o miniaudio: {exc}"
            log.warning(self._error)
            return
        self._available = True
        self._resolve_device()
        self._running = True
        self._thread = threading.Thread(target=self._run, name="miky-tts-edge", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._running = False
        self._cancel.set()
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._thread is not None:
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
            self._thread.join(timeout=2.0)
            self._thread = None

    # ---------- API ----------

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str:
        return self._error

    @property
    def voice_name(self) -> str:
        return VOICE_LABELS.get(self.voice, self.voice)

    @property
    def output_name(self) -> str:
        return self.output_device

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._thread is None:
            self.start()
        if not self._available:
            self._to_fallback(text)
            return
        self._cancel.clear()
        try:
            self._queue.put_nowait(("speak", text))
        except queue.Full:
            self._to_fallback(text)

    def stop(self) -> None:
        self._cancel.set()
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:  # noqa: BLE001
            pass

    # ---------- interno ----------

    def _to_fallback(self, text: str) -> None:
        if self.fallback is not None:
            try:
                self.fallback(text)
            except Exception:  # noqa: BLE001
                log.debug("el respaldo de voz también falló", exc_info=True)

    def _resolve_device(self) -> None:
        if not self.output_device:
            try:
                import sounddevice as sd

                default_index = sd.default.device[1]
                if default_index is not None and default_index >= 0:
                    info = sd.query_devices(default_index)
                    log.info("salida de la voz: %s (predeterminada del sistema)", info["name"])
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            import sounddevice as sd

            needle = self.output_device.lower()
            for index, info in enumerate(sd.query_devices()):
                if info["max_output_channels"] > 0 and needle in str(info["name"]).lower():
                    self._device_index = index
                    log.info("salida de la voz: %s", info["name"])
                    return
        except Exception:  # noqa: BLE001
            pass
        log.warning("no encontré la salida «%s» para la voz; uso la predeterminada", self.output_device)

    def _run(self) -> None:
        while self._running:
            try:
                item = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            if item is None:
                break
            _kind, text = item
            text = pronounce.apply(text)
            try:
                self._speaking.set()
                self._cancel.clear()
                cached = self._cache.get(text)
                if cached is not None:
                    # Frase ya sintetizada: suena al instante.
                    if self._cancel.is_set():
                        continue
                    played = self._play(cached)
                    log.info("dije «%s» (0 ms, en caché, %0.2f s)", text[:60], played)
                    continue
                started = time.monotonic()
                audio = asyncio.run(self._synthesize(text))
                synth_ms = (time.monotonic() - started) * 1000
                if self._cancel.is_set():
                    continue
                self._remember(text, audio)
                played = self._play(audio)
                log.info(
                    "dije «%s» (%0.0f ms de síntesis, %0.2f s de audio)",
                    text[:60],
                    synth_ms,
                    played,
                )
            except Exception as exc:  # noqa: BLE001
                self._error = str(exc)
                log.warning("no pude hablar con edge-tts (%s); uso la voz local", exc)
                self._to_fallback(text)
            finally:
                self._speaking.clear()

    # ---------- caché de frases ----------

    def _remember(self, text: str, audio: bytes) -> None:
        if len(audio) > MAX_CACHE_BYTES or len(self._cache) >= MAX_CACHE_ITEMS:
            return
        self._cache[text] = audio

    def prewarm(self, phrases: list[str] | None = None) -> None:
        """Sintetiza las frases más comunes en segundo plano.

        Así la primera respuesta corta no espera 1-2 s de síntesis.
        """
        if not self._available:
            return
        phrases = phrases or COMMON_PHRASES

        def worker() -> None:
            for phrase in phrases:
                if not self._running:
                    return
                text = pronounce.apply(phrase)
                if text in self._cache:
                    continue
                try:
                    audio = asyncio.run(self._synthesize(text))
                    self._remember(text, audio)
                    log.debug("frase en caché: %s", text)
                except Exception as exc:  # noqa: BLE001
                    log.debug("no pude precalentar «%s»: %s", text, exc)

        threading.Thread(target=worker, name="miky-tts-warm", daemon=True).start()

    async def _synthesize(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, self.voice, rate=self._rate_hint)
        chunks = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks += chunk["data"]
        if not chunks:
            raise RuntimeError("edge-tts no devolvió audio")
        return bytes(chunks)

    def _play(self, mp3: bytes) -> float:
        import miniaudio
        import sounddevice as sd

        decoded = miniaudio.decode(
            mp3,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=2,
            sample_rate=44100,
        )
        samples = np.frombuffer(bytes(decoded.samples), dtype=np.int16)
        samples = samples.reshape(-1, decoded.nchannels)
        started = time.monotonic()
        stream = sd.OutputStream(
            samplerate=decoded.sample_rate,
            channels=decoded.nchannels,
            dtype="int16",
            device=self._device_index,
        )
        stream.start()
        try:
            block = 1024
            for start in range(0, samples.shape[0], block):
                if self._cancel.is_set():
                    break
                stream.write(samples[start : start + block])
        finally:
            stream.stop()
            stream.close()
        return time.monotonic() - started
