"""Verifica el camino real de captura: bloques de 48 kHz → VAD → texto.

Reproduce el bug que hacía que el ícono "escuchara" pero no pasara nada: el
micrófono entrega bloques de 512 muestras a 48 kHz que, remuestreados a 16 kHz,
quedan en ~171 muestras; el VAD necesita bloques exactos de 512.

Uso: python tools/verify_capture.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from miky.voice.audio import TARGET_RATE, resample  # noqa: E402
from miky.voice.stt import FasterWhisperStt  # noqa: E402
from miky.voice.vad import CHUNK, ChunkBuffer, create_segmenter  # noqa: E402
from voice_selftest import DEFAULT_PHRASE, load_wav, synthesize, word_accuracy  # noqa: E402


def main() -> int:
    phrase = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PHRASE
    work = Path(tempfile.gettempdir()) / "miky_verify_capture"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "frase.wav"

    if synthesize(phrase, wav) is None:
        return 1
    audio, rate = load_wav(wav)
    print(f"[i] frase: «{phrase}»")
    print(f"[i] wav: {audio.size / rate:.2f} s a {rate} Hz")

    # Simulación exacta del dispositivo: 48 kHz y bloques de 512 cuadros.
    device_rate = 48000
    device_audio = resample(audio, rate, device_rate)
    buffer = ChunkBuffer(CHUNK)
    segmenter = create_segmenter(threshold=0.5, min_silence_ms=600, max_speech_s=25)
    segments = []
    blocks = 0
    for start in range(0, device_audio.size - 512, 512):
        native = device_audio[start : start + 512]
        for block in buffer.feed(resample(native, device_rate, TARGET_RATE)):
            blocks += 1
            segments.extend(segmenter.process(block))
    segments.extend(segmenter.flush())

    print(f"[i] bloques de 512 a 16 kHz procesados: {blocks}")
    print(f"[{'ok' if segments else 'x'}] segmentos detectados: {len(segments)}")
    if not segments:
        print("[x] el VAD no detectó voz: el bug sigue")
        return 1

    stt = FasterWhisperStt(model_size="small", language="es")
    stt.ensure_loaded()
    text = stt.transcribe(segments[0].audio)
    accuracy = word_accuracy(phrase, text)
    print(f"[i] transcripción: «{text}»")
    print(f"[{'ok' if accuracy >= 0.6 else 'x'}] coincidencia: {accuracy * 100:.0f}%")
    return 0 if accuracy >= 0.6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
