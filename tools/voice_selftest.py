"""Autotest del camino de voz, sin micrófono ni parlantes.

1. Sintetiza una frase con la voz de Windows a un WAV (SAPI).
2. La pasa por el detector de voz (Silero) y verifica que encuentre un segmento.
3. La transcribe con faster-whisper y compara contra el texto original.

Sirve para validar TTS, VAD y STT después de cualquier cambio, sin molestar a
nadie y sin depender del ruido del cuarto.

Uso: python tools/voice_selftest.py ["frase de prueba"]
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from miky.voice.audio import TARGET_RATE, resample  # noqa: E402
from miky.voice.stt import FasterWhisperStt  # noqa: E402
from miky.voice.vad import CHUNK, create_segmenter  # noqa: E402

DEFAULT_PHRASE = "Miky, crea una pista llamada guitarra y armala para grabar"


def _pick_spanish_voice(voice) -> str:  # noqa: ANN001
    """Elige una voz en español (y devuelve su descripción)."""
    try:
        tokens = voice.GetVoices()
    except Exception:  # noqa: BLE001
        return ""
    fallback = ""
    for index in range(tokens.Count):
        token = tokens.Item(index)
        description = str(token.GetDescription())
        lowered = description.lower()
        if "spanish" in lowered or "español" in lowered or "espanol" in lowered:
            try:
                voice.Voice = token
            except Exception:  # noqa: BLE001
                continue
            return description
        if not fallback:
            fallback = description
    return fallback


def synthesize(text: str, target: Path) -> Path | None:
    """Escribe la frase a un WAV usando la voz SAPI por defecto."""
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        print("[x] comtypes no está instalado")
        return None

    try:
        comtypes.CoInitialize()
    except OSError:
        pass

    try:
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        chosen = _pick_spanish_voice(voice)
        stream = comtypes.client.CreateObject("SAPI.SpFileStream")
        # SSFMCreateForWrite = 3
        stream.Open(str(target), 3, False)
        voice.AudioOutputStream = stream
        print("[i] sintetizando con la voz:", chosen or "voz por defecto")
        voice.Speak(text, 0)  # sincrónico
        stream.Close()
        voice.AudioOutputStream = None
        return target
    except Exception as exc:  # noqa: BLE001
        print(f"[x] no pude sintetizar: {exc}")
        return None
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())
    if width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        audio = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def normalize_words(text: str) -> list[str]:
    import unicodedata

    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    for char in ",.;:!?¡¿":
        text = text.replace(char, " ")
    return [word for word in text.split() if word]


def word_accuracy(reference: str, hypothesis: str) -> float:
    expected = normalize_words(reference)
    got = normalize_words(hypothesis)
    if not expected:
        return 0.0
    matches = 0
    remaining = list(got)
    for word in expected:
        if word in remaining:
            matches += 1
            remaining.remove(word)
    return matches / len(expected)


def main() -> int:
    phrase = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PHRASE
    out_dir = Path(__import__("os").environ.get("TEMP", ".")) / "miky_voice_selftest"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "frase.wav"

    print(f"[i] frase: «{phrase}»")
    if synthesize(phrase, wav) is None:
        return 1

    audio, rate = load_wav(wav)
    print(f"[i] wav: {audio.size / rate:.2f} s a {rate} Hz")
    audio16 = resample(audio, rate, TARGET_RATE)

    # --- VAD ---
    started = time.monotonic()
    segmenter = create_segmenter(threshold=0.5, min_silence_ms=500, max_speech_s=25)
    segments = []
    for start in range(0, audio16.size - CHUNK, CHUNK):
        segments.extend(segmenter.process(audio16[start : start + CHUNK]))
    segments.extend(segmenter.flush())
    vad_ms = (time.monotonic() - started) * 1000
    print(f"[{ 'ok' if segments else 'x'}] VAD: {len(segments)} segmento(s) en {vad_ms:.0f} ms")
    for index, segment in enumerate(segments):
        print(f"      segmento {index + 1}: {segment.duration_s:.2f} s")

    if not segments:
        print("[!] el VAD no detectó voz; pruebo transcribir el audio completo igual")

    # --- STT ---
    stt = FasterWhisperStt(model_size="base", language="es")
    load_started = time.monotonic()
    try:
        stt.ensure_loaded()
    except Exception as exc:  # noqa: BLE001
        print(f"[x] no pude cargar el modelo: {exc}")
        return 1
    print(f"[i] modelo cargado en {time.monotonic() - load_started:.1f} s ({stt.description})")

    started = time.monotonic()
    text = stt.transcribe(segments[0].audio if segments else audio16)
    stt_ms = (time.monotonic() - started) * 1000
    print(f"[i] transcripción ({stt_ms:.0f} ms): «{text}»")

    accuracy = word_accuracy(phrase, text)
    status = "ok" if accuracy >= 0.6 else "x"
    print(f"[{status}] coincidencia de palabras: {accuracy * 100:.0f}%")

    started = time.monotonic()
    stt.transcribe(audio16)
    second = (time.monotonic() - started) * 1000
    print(f"[i] segunda pasada (modelo ya cargado): {second:.0f} ms")

    return 0 if accuracy >= 0.6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
