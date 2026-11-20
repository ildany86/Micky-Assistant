"""Voz de respuesta local con SAPI5 (Windows), sin descargas ni internet.

Se usa un hilo propio que es dueño del objeto COM, así no hay problemas de
apartamento y se puede cortar la voz en cualquier momento.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from .. import log as log_mod
from . import pronounce

log = log_mod.get("miky.tts")

SVSF_ASYNC = 1
SVSF_PURGE = 2
SRSE_IS_SPEAKING = 2


@dataclass
class VoiceInfo:
    name: str
    language: str
    gender: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.language})"


class TtsError(RuntimeError):
    pass


def list_sapi_voices() -> list[VoiceInfo]:
    """Lista las voces SAPI5 instaladas (bloquea ~100 ms)."""
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        return []

    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    try:
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        tokens = voice.GetVoices()
        result: list[VoiceInfo] = []
        for index in range(tokens.Count):
            token = tokens.Item(index)
            description = str(token.GetDescription())
            language = ""
            try:
                attributes = token.GetAttribute("Language")
                language = _language_name(int(attributes)) if attributes else ""
            except Exception:  # noqa: BLE001
                pass
            gender = ""
            try:
                raw_gender = token.GetAttribute("Gender")
                gender = {1: "femenina", 2: "masculina"}.get(int(raw_gender), "") if raw_gender else ""
            except Exception:  # noqa: BLE001
                pass
            result.append(VoiceInfo(name=description, language=language or _guess_language(description), gender=gender))
        return result
    except Exception as exc:  # noqa: BLE001
        log.debug("no pude listar voces SAPI: %s", exc)
        return []
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


def _language_name(code: int) -> str:
    mapping = {0x40A: "es-ES", 0x80A: "es-MX", 0x540A: "es-AR", 0x409: "en-US", 0x809: "en-GB"}
    return mapping.get(code, f"0x{code:X}")


def _guess_language(description: str) -> str:
    lowered = description.lower()
    if "spanish" in lowered or "español" in lowered or "espanol" in lowered:
        if "mex" in lowered:
            return "es-MX"
        return "es-ES"
    if "english" in lowered:
        return "en-US"
    return ""


def list_sapi_outputs() -> list[str]:
    """Salidas de audio que SAPI puede usar para hablar (auriculares, placa, etc.)."""
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        return []
    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    try:
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        outputs = voice.GetAudioOutputs()
        return [str(outputs.Item(index).GetDescription()) for index in range(outputs.Count)]
    except Exception as exc:  # noqa: BLE001
        log.debug("no pude listar salidas SAPI: %s", exc)
        return []
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


class SapiTts:
    """Cola de habla con un hilo dedicado y posibilidad de interrumpir."""

    def __init__(
        self,
        voice_hint: str = "",
        rate: int = 0,
        volume: int = 100,
        output_hint: str = "",
    ) -> None:
        self.voice_hint = voice_hint
        self.output_hint = output_hint
        self.rate = max(-10, min(10, int(rate)))
        self.volume = max(0, min(100, int(volume)))
        self._queue: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._speaking = threading.Event()
        self._cancel = threading.Event()
        self._ready = threading.Event()
        self._error: str = ""
        self._voice_name: str = ""
        self._output_name: str = ""
        self._com_ready = False

    # ---------- ciclo de vida ----------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="miky-tts", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=4.0)

    def close(self) -> None:
        self._running = False
        self._cancel.set()
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
        return self._com_ready

    @property
    def error(self) -> str:
        return self._error

    @property
    def voice_name(self) -> str:
        return self._voice_name

    @property
    def output_name(self) -> str:
        return self._output_name

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._thread is None:
            self.start()
        if not self._com_ready:
            log.warning("TTS no disponible: %s", self._error or "SAPI no inicializó")
            return
        self._cancel.clear()
        self._queue.put(("speak", text))

    def stop(self) -> None:
        self._cancel.set()
        self._queue.put(("stop", ""))

    # ---------- hilo ----------

    def _run(self) -> None:
        voice = None
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            voice = comtypes.client.CreateObject("SAPI.SpVoice")
            voice.Rate = self.rate
            voice.Volume = self.volume
            self._select_output(voice)
            self._select_voice(voice)
            self._com_ready = True
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            log.error("no pude inicializar SAPI: %s", exc)
        finally:
            self._ready.set()

        while self._running:
            try:
                item = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            if item is None:
                break
            kind, text = item
            if kind == "stop":
                if voice is not None:
                    try:
                        voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
                    except Exception:  # noqa: BLE001
                        pass
                continue
            if kind != "speak" or voice is None:
                continue
            try:
                self._speaking.set()
                self._cancel.clear()
                voice.Speak(pronounce.apply(text), SVSF_ASYNC)
                while not self._cancel.is_set():
                    try:
                        state = int(voice.Status.RunningState)
                    except Exception:  # noqa: BLE001
                        break
                    if state != SRSE_IS_SPEAKING:
                        break
                    time.sleep(0.03)
                if self._cancel.is_set():
                    try:
                        voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as exc:  # noqa: BLE001
                log.warning("error al hablar: %s", exc)
            finally:
                self._speaking.clear()

        if voice is not None:
            try:
                voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
            except Exception:  # noqa: BLE001
                pass

    def _select_output(self, voice) -> None:
        """Elige por qué dispositivo habla (si el usuario configuró uno)."""
        hint = self.output_hint.lower().strip()
        if not hint:
            return
        try:
            outputs = voice.GetAudioOutputs()
        except Exception:  # noqa: BLE001
            return
        for index in range(outputs.Count):
            token = outputs.Item(index)
            description = str(token.GetDescription())
            if hint in description.lower():
                try:
                    voice.AudioOutput = token
                    self._output_name = description
                    log.info("salida de voz: %s", description)
                except Exception as exc:  # noqa: BLE001
                    log.debug("no pude fijar la salida de voz: %s", exc)
                return
        log.warning("no encontré la salida de voz «%s»; uso la predeterminada", self.output_hint)

    def _select_voice(self, voice) -> None:
        try:
            tokens = voice.GetVoices()
        except Exception:  # noqa: BLE001
            return
        chosen = None
        spanish = None
        first = None
        hint = self.voice_hint.lower().strip()
        for index in range(tokens.Count):
            token = tokens.Item(index)
            description = str(token.GetDescription())
            lowered = description.lower()
            if first is None:
                first = token
            if hint and hint in lowered:
                chosen = token
                break
            if spanish is None and (
                "spanish" in lowered or "español" in lowered or "espanol" in lowered
            ):
                spanish = token
        # Preferencia: la voz pedida, después cualquier voz en español.
        token = chosen or spanish or first
        if token is not None:
            try:
                voice.Voice = token
                self._voice_name = str(token.GetDescription())
                log.info("voz seleccionada: %s", self._voice_name)
            except Exception as exc:  # noqa: BLE001
                log.debug("no pude fijar la voz: %s", exc)


class NullTts:
    """Respaldo cuando no hay SAPI: no habla, pero no rompe la app."""

    available = False
    error = "TTS no disponible"
    voice_name = ""
    is_speaking = False

    def start(self) -> None:
        pass

    def close(self) -> None:
        pass

    def speak(self, text: str) -> None:
        log.info("[voz desactivada] %s", text)

    def stop(self) -> None:
        pass
