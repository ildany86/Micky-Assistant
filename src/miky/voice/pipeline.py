"""Orquestador de voz: micrófono → VAD → texto → palabra de activación → comando.

Tres modos de uso:
- `always`: escucha siempre, pero solo reacciona cuando decís "Miky".
- `push_to_talk`: solo escucha cuando apretás el icono.
- `off`: desactivado.

La app decide qué hacer con el comando; este módulo no ejecuta nada.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from .. import log as log_mod
from ..config import VoiceSection
from . import correct, wake
from .audio import AudioCapture, pick_input_device
from .feedback import chime
from .stt import FasterWhisperStt, SttError
from .vad import CHUNK, ChunkBuffer, Segment, create_segmenter

log = log_mod.get("miky.voice")

IDLE = "idle"
LISTENING = "listening"
THINKING = "thinking"
ERROR = "error"
OFFLINE = "offline"

# Nivel mínimo (RMS) para gastar una transcripción. Debajo de esto Whisper
# alucina frases sobre el ruido de fondo.
MIN_SEGMENT_RMS = 0.006

# Transcripción especulativa: si la frase se quedó callada un momento, se
# empieza a transcribir YA, mientras el VAD todavía espera para cerrar. Si el
# usuario sigue hablando, se descarta y se usa el audio completo.
SPECULATION_SILENCE_S = 0.18
SPECULATION_MIN_AUDIO_S = 0.5
SPECULATION_TOLERANCE_S = 0.5


@dataclass
class VoiceSettings:
    mode: str = "always"
    wake_word: str = "miky"
    input_device: str = ""
    stt_model: str = "base"
    stt_language: str = "es"
    stt_beam: int = 5
    vad_threshold: float = 0.5
    silence_ms: int = 650
    max_utterance_s: float = 20.0
    warmup: bool = True
    chime: bool = True
    follow_up_seconds: float = 8.0
    corrections: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, voice: VoiceSection) -> "VoiceSettings":
        return cls(
            mode=voice.mode,
            wake_word=voice.wake_word,
            input_device=voice.input_device,
            stt_model=voice.stt_model,
            stt_language=voice.stt_language,
            stt_beam=voice.stt_beam,
            vad_threshold=voice.vad_threshold,
            silence_ms=voice.silence_ms,
            max_utterance_s=voice.max_utterance_s,
            warmup=voice.warmup_on_start,
            chime=voice.chime,
            follow_up_seconds=voice.follow_up_seconds,
            corrections=tuple(getattr(voice, "corrections", ()) or ()),
        )


class VoicePipeline:
    def __init__(
        self,
        settings: VoiceSettings,
        on_command: Callable[[str], None],
        on_state: Callable[[str], None] | None = None,
        on_transcript: Callable[[str, bool], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        tts=None,
        allow_speculation: Callable[[], bool] | None = None,
    ) -> None:
        self.settings = settings
        self.on_command = on_command
        self.on_state = on_state or (lambda _state: None)
        self.on_transcript = on_transcript or (lambda _text, _wake: None)
        self.on_error = on_error or (lambda _message: None)
        self.tts = tts
        self._allow_speculation = allow_speculation

        self.capture: AudioCapture | None = None
        self.segmenter = None
        self.stt = FasterWhisperStt(
            model_size=settings.stt_model,
            language=settings.stt_language,
            beam_size=settings.stt_beam,
        )
        self._hotwords = ""
        self._terms: list[str] = []
        self._blocks = ChunkBuffer(CHUNK)
        self._follow_up_until = 0.0
        self._last_rejection = ""
        self._spec: dict[str, Any] | None = None

        self._running = False
        self._thread: threading.Thread | None = None
        self._preload_thread: threading.Thread | None = None
        self._state = IDLE
        self._muted = False
        self._awaiting_command = False
        self._processing_lock = threading.Lock()
        self._confirm_event: threading.Event | None = None
        self._confirm_answer: bool | None = None
        self._confirm_deadline = 0.0
        self._last_transcript = ""

    # ---------- ciclo de vida ----------

    @property
    def running(self) -> bool:
        return self._running

    @property
    def state(self) -> str:
        return self._state

    @property
    def stt_ready(self) -> bool:
        return self.stt.loaded

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="miky-voice", daemon=True)
        self._thread.start()
        if self.settings.warmup:
            self._preload_thread = threading.Thread(
                target=self._warmup, name="miky-voice-warmup", daemon=True
            )
            self._preload_thread.start()

    def stop(self) -> None:
        self._running = False
        if self.capture is not None:
            self.capture.stop()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._set_state(OFFLINE)

    def _warmup(self) -> None:
        try:
            self.on_state(LISTENING)
            self.stt.ensure_loaded()
            if self.settings.warmup:
                self.stt.warmup()
            log.info("modelo de voz listo")
        except (SttError, Exception) as exc:  # noqa: BLE001
            log.error("no pude preparar el modelo de voz: %s", exc)
            self.on_error(f"No pude cargar el modelo de voz: {exc}")
            self._set_state(ERROR)
            return
        finally:
            if self._state == LISTENING and not self._running:
                self._set_state(OFFLINE)
        self._set_state(IDLE)

    # ---------- control externo ----------

    def trigger(self) -> None:
        """Push-to-talk o clic en el icono: el próximo pedazo de voz es un comando."""
        self._awaiting_command = True
        self._muted = False
        self._set_state(LISTENING)

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._spec = None
        if muted and self.segmenter is not None:
            self.segmenter.reset()

    def expect_confirmation(self, speak_text: str = "", timeout: float = 12.0) -> bool:
        """Espera un sí/no por voz. Devuelve False si no hubo respuesta a tiempo.

        La ventana arranca cuando Miky terminó de hablar: mientras habla, el
        audio del micrófono se descarta (si no, se escucharía a sí mismo), así
        que empezar a contar antes hacía que la respuesta se perdiera.
        """
        if self.tts is not None and speak_text:
            self.tts.speak(speak_text)

        if self.tts is not None:
            deadline = time.monotonic() + 15.0
            while self.tts.is_speaking and time.monotonic() < deadline:
                time.sleep(0.05)

        if self.segmenter is not None:
            self.segmenter.reset()
        self._blocks.reset()
        self._confirm_answer = None
        self._confirm_event = threading.Event()
        self._confirm_deadline = time.monotonic() + timeout
        self._muted = False
        self._set_state(LISTENING)
        log.info("esperando confirmación por voz (%0.0f s)", timeout)

        try:
            answered = self._confirm_event.wait(timeout=timeout)
        finally:
            self._muted = True
            self._confirm_event = None
        self._set_state(THINKING if answered else IDLE)
        return bool(self._confirm_answer) if answered else False

    def answer_confirmation(self, answer: bool) -> None:
        if self._confirm_event is None:
            return
        self._confirm_answer = answer
        self._confirm_event.set()

    @property
    def awaiting_confirmation(self) -> bool:
        return self._confirm_event is not None

    @property
    def last_transcript(self) -> str:
        return self._last_transcript

    def feed_text(self, text: str, as_command: bool = False) -> None:
        """Entra texto como si viniera del micrófono (tests y modo consola)."""
        if as_command:
            self._dispatch(text)
        else:
            self._handle_text(text)

    # ---------- bucle ----------

    def _loop(self) -> None:
        device_index, reason = pick_input_device(self.settings.input_device)
        log.info("micrófono: %s", reason)
        self.capture = AudioCapture(device_index=device_index)
        try:
            self.capture.start()
        except Exception as exc:  # noqa: BLE001
            log.warning("no pude abrir el dispositivo elegido (%s): %s", device_index, exc)
            # Segundo intento: elegir automáticamente (evita quedar sordo por una
            # configuración vieja o por un dispositivo que Windows no comparte).
            fallback_index, fallback_reason = pick_input_device("")
            if fallback_index is None or fallback_index == device_index:
                self._fail_microphone(exc)
                return
            log.info("reintento con: %s", fallback_reason)
            self.capture = AudioCapture(device_index=fallback_index)
            try:
                self.capture.start()
            except Exception as exc2:  # noqa: BLE001
                self._fail_microphone(exc2)
                return

        self.segmenter = create_segmenter(
            threshold=self.settings.vad_threshold,
            min_silence_ms=self.settings.silence_ms,
            max_speech_s=self.settings.max_utterance_s,
        )
        self._set_state(IDLE)

        loud_samples = 0
        last_warning = 0.0

        while self._running:
            try:
                chunk = self.capture.read(timeout=0.4)
                if chunk is None:
                    # El dispositivo dejó de entregar audio (o se desconectó):
                    # cerramos lo que haya en curso para no perder la frase.
                    for segment in self.segmenter.flush():
                        self._handle_segment(segment)
                    self._blocks.reset()
                    continue
                if self._muted or (self.tts is not None and self.tts.is_speaking):
                    self.segmenter.reset()
                    self._blocks.reset()
                    continue

                # Diagnóstico: si entra audio fuerte y el VAD no cierra nada en
                # 15 s, se avisa (es el síntoma de un problema de bloques/muestreo).
                if self.capture is not None and self.capture.level > 0.015:
                    loud_samples += chunk.size
                else:
                    loud_samples = max(0, loud_samples - chunk.size)

                produced = False
                for block in self._blocks.feed(chunk):
                    for segment in self.segmenter.process(block):
                        produced = True
                        self._handle_segment(segment)
                if produced:
                    loud_samples = 0
                else:
                    # La frase está en curso y se quedó callada: se puede empezar
                    # a transcribir mientras el VAD termina de cerrar.
                    self._maybe_speculate()

                if loud_samples > 16000 * 15 and time.monotonic() - last_warning > 120:
                    log.warning(
                        "entra audio (%d muestras) pero el VAD no cierra segmentos; "
                        "revisá el dispositivo de entrada y el umbral",
                        loud_samples,
                    )
                    last_warning = time.monotonic()
                    loud_samples = 0
            except Exception as exc:  # noqa: BLE001 - el bucle no debe morir
                log.error("error en el bucle de voz: %s", exc)
                self.on_error(str(exc))
                time.sleep(0.2)

        if self.capture is not None:
            self.capture.stop()

    def _fail_microphone(self, exc: Exception) -> None:
        log.error("no pude abrir el micrófono: %s", exc)
        self.on_error(
            "No pude abrir el micrófono. Si REAPER está usando esa interfaz por ASIO, "
            "Windows no la comparte: elegí otro dispositivo en Ajustes (clic derecho en el ícono)."
        )
        self._set_state(ERROR)
        self._running = False

    # ---------- transcripción especulativa ----------

    def _maybe_speculate(self) -> None:
        """Arranca una transcripción mientras el VAD todavía espera cerrar.

        Cuando la frase lleva ~180 ms de silencio, el final ya está dicho: se
        transcribe el audio acumulado en un hilo aparte. Si el usuario sigue
        hablando, el resultado se descarta y se usa el audio completo.
        """
        if self._spec is not None or self.segmenter is None:
            return
        # Mientras graba no se lanzan hilos extra: el audio de REAPER manda.
        if self._allow_speculation is not None:
            try:
                if not self._allow_speculation():
                    return
            except Exception:  # noqa: BLE001
                return
        try:
            if not self.segmenter.active:
                return
            if self.segmenter.silence_samples < int(SPECULATION_SILENCE_S * 16000):
                return
            audio = self.segmenter.pending_audio()
        except Exception:  # noqa: BLE001
            return
        if audio.size < int(SPECULATION_MIN_AUDIO_S * 16000):
            return
        entry: dict[str, Any] = {"length": int(audio.size), "text": None, "thread": None}
        thread = threading.Thread(
            target=self._run_speculation, args=(audio.copy(), entry), name="miky-spec", daemon=True
        )
        entry["thread"] = thread
        self._spec = entry
        thread.start()
        log.debug("transcripción especulativa (%.2f s)", audio.size / 16000)

    def _run_speculation(self, audio: "np.ndarray", entry: dict[str, Any]) -> None:
        try:
            entry["text"] = self.stt.transcribe(audio, hotwords=self._hotwords or None)
        except Exception as exc:  # noqa: BLE001
            log.debug("la transcripción especulativa falló: %s", exc)
            entry["text"] = ""

    def _take_speculation(self, audio: "np.ndarray") -> str | None:
        """Devuelve el texto especulado si corresponde a este segmento."""
        entry = self._spec
        self._spec = None
        if entry is None:
            return None
        difference = abs(int(entry["length"]) - int(audio.size)) / 16000
        if difference > SPECULATION_TOLERANCE_S:
            log.debug("especulación descartada (diferencia %.2f s)", difference)
            return None
        thread = entry.get("thread")
        if thread is not None and thread.is_alive():
            thread.join(timeout=10.0)
        return entry.get("text") or None

    def _handle_segment(self, segment: Segment) -> None:
        if segment.duration_s < 0.35:
            log.debug("segmento descartado por corto (%.2f s)", segment.duration_s)
            self._spec = None
            return
        level = float(np.sqrt(np.mean(segment.audio**2))) if segment.audio.size else 0.0
        if level < MIN_SEGMENT_RMS:
            # Sin este filtro, con ruido de fondo Whisper "inventa" frases.
            log.debug("segmento descartado por bajo nivel (rms %.4f)", level)
            self._spec = None
            return
        log.debug("segmento de %.2f s (rms %.3f)", segment.duration_s, level)

        text = self._take_speculation(segment.audio)
        if text is not None:
            log.debug("se usó la transcripción especulativa")
            if text:
                self._handle_corrected_text(text)
            return
        try:
            text = self.stt.transcribe(segment.audio, hotwords=self._hotwords or None)
        except SttError as exc:
            log.warning("transcripción falló: %s", exc)
            return
        except Exception as exc:  # noqa: BLE001
            log.error("error inesperado al transcribir: %s", exc)
            return
        if text:
            self._handle_corrected_text(text)
        else:
            log.info("escuché un segmento de %.1f s pero no entendí texto", segment.duration_s)

    def _handle_corrected_text(self, text: str) -> None:
        """Corrige marcas y nombres propios antes de interpretar."""
        corrected, changes = correct.correct_text(text, self._terms, self.settings.corrections)
        if changes:
            log.info(
                "corregido: «%s» (%s)",
                corrected,
                ", ".join(f"{before}→{after}" for before, after in changes[:4]),
            )
        self._handle_text(corrected)

    def set_hotwords(self, names: list[str] | str) -> None:
        """Sesga el reconocimiento con los nombres reales de las pistas.

        El nombre del asistente NO va acá: si aparece como hotword, Whisper lo
        interpreta como contexto ya dicho y lo borra de la transcripción.
        """
        if isinstance(names, str):
            terms = [part.strip() for part in names.split(",") if part.strip()]
        else:
            terms = [name.strip() for name in names if name and name.strip()]
        self._terms = terms[:60]
        self._hotwords = ", ".join(terms)[:400]

    def _handle_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self._last_transcript = text
        log.info("escuché: %s", text)

        # ¿Es la respuesta a una confirmación?
        if self._confirm_event is not None:
            answer = wake.parse_yes_no(text)
            self.on_transcript(text, False)
            if answer is not None:
                self.answer_confirmation(answer)
            return

        activated, remainder = wake.split_wake(text, self.settings.wake_word)
        self.on_transcript(text, activated)

        if self.settings.mode == "always":
            if activated:
                if self.settings.chime:
                    chime("wake")
                self._awaiting_command = True
                if remainder:
                    self._dispatch(remainder)
                else:
                    self._set_state(LISTENING)
                return
            # Ventana de seguimiento: después de responder, se aceptan órdenes
            # sin repetir "Miky" durante unos segundos.
            if self._awaiting_command or time.monotonic() < self._follow_up_until:
                self._dispatch(text)
            return

        # push_to_talk: todo lo que se dice después del clic es comando
        if self._awaiting_command:
            self._dispatch(text)
        else:
            self._set_state(IDLE)

    def _dispatch(self, text: str) -> None:
        text = text.strip()
        if not text:
            self._awaiting_command = False
            self._set_state(IDLE)
            return
        self._awaiting_command = False
        self._set_state(THINKING)
        threading.Thread(
            target=self._run_command, args=(text,), name="miky-command", daemon=True
        ).start()

    def _run_command(self, text: str) -> None:
        # Si ya hay una orden en curso (por ejemplo un render largo), no se
        # encola en silencio: se avisa al instante.
        if not self._processing_lock.acquire(blocking=False):
            log.info("orden ignorada, hay otra en curso: %s", text)
            self.on_transcript(text, True)
            self._last_rejection = (
                "Estoy ocupado con una tarea larga. Si es un render, "
                "podés cancelarlo en la ventana de REAPER."
            )
            self.on_error(self._last_rejection)
            return
        self._muted = True
        try:
            self.on_command(text)
        except Exception as exc:  # noqa: BLE001
            log.error("error ejecutando el comando: %s", exc)
            self.on_error(str(exc))
        finally:
            self._muted = False
            self._processing_lock.release()
            if self._state == THINKING:
                self._set_state(IDLE)
            # Se queda escuchando "de seguido" por si el usuario encadena otra
            # orden sin volver a decir la palabra clave.
            self._follow_up_until = time.monotonic() + self.settings.follow_up_seconds

    # ---------- estado ----------

    def _set_state(self, state: str) -> None:
        if self._state == state:
            return
        self._state = state
        try:
            self.on_state(state)
        except Exception:  # noqa: BLE001
            log.debug("on_state falló", exc_info=True)
