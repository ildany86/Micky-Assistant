"""Verificación del pipeline de voz completo, sin micrófono.

Inyecta una frase (sintetizada) como si viniera del micrófono a 48 kHz en
bloques de 512, y comprueba que el pipeline la detecte, la transcriba, encuentre
la palabra clave y emita el comando.

Uso: python tools/verify_pipeline.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from miky import log as log_mod  # noqa: E402
import miky.voice.pipeline as pipeline_mod  # noqa: E402
from miky.voice.audio import TARGET_RATE, resample  # noqa: E402
from miky.voice.pipeline import VoicePipeline, VoiceSettings  # noqa: E402
from voice_selftest import DEFAULT_PHRASE, load_wav, synthesize, word_accuracy  # noqa: E402

DEVICE_RATE = 48000
BLOCK = 512


class FakeCapture:
    """Se hace pasar por el micrófono entregando un WAV en bloques de 512."""

    def __init__(self, audio: np.ndarray) -> None:
        self.audio = audio
        self.position = 0
        self.level = 0.0

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def read(self, timeout: float = 0.4) -> np.ndarray | None:
        if self.position >= self.audio.size:
            time.sleep(0.05)
            return None
        chunk = self.audio[self.position : self.position + BLOCK]
        self.position += BLOCK
        self.level = float(np.sqrt(np.mean(chunk**2))) if chunk.size else 0.0
        time.sleep(0.005)  # simula el ritmo del dispositivo
        return resample(chunk, DEVICE_RATE, TARGET_RATE)


def main() -> int:
    phrase = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PHRASE
    log_mod.setup("INFO")
    work = Path(tempfile.gettempdir()) / "miky_verify_pipeline"
    work.mkdir(parents=True, exist_ok=True)
    wav = work / "frase.wav"

    if synthesize(phrase, wav) is None:
        return 1
    audio, rate = load_wav(wav)
    device_audio = resample(audio, rate, DEVICE_RATE)
    # 1,5 s de silencio al final: así el VAD cierra la frase como lo haría con
    # el micrófono real.
    device_audio = np.concatenate([device_audio, np.zeros(DEVICE_RATE * 3 // 2, dtype=np.float32)])
    print(f"[i] frase: «{phrase}» ({device_audio.size / DEVICE_RATE:.2f} s a {DEVICE_RATE} Hz)")

    captured: list[str] = []
    states: list[str] = []

    original = pipeline_mod.AudioCapture
    pipeline_mod.AudioCapture = lambda **kwargs: FakeCapture(device_audio)  # type: ignore[assignment]
    try:
        pipeline = VoicePipeline(
            VoiceSettings(mode="always", wake_word="miky", stt_model="small", warmup=False),
            on_command=lambda text: captured.append(text),
            on_state=states.append,
            on_transcript=lambda text, activated: print(f"[i] transcript: «{text}» activado={activated}"),
            on_error=lambda message: print(f"[x] error: {message}"),
        )
        pipeline.start()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not captured:
            time.sleep(0.5)
        pipeline.stop()
    finally:
        pipeline_mod.AudioCapture = original  # type: ignore[assignment]

    if not captured:
        print("[x] el pipeline no emitió ningún comando")
        return 1
    text = captured[0]
    print(f"[ok] comando emitido: «{text}»")
    accuracy = word_accuracy(phrase, text)
    print(f"[i] parecido con la frase original: {accuracy * 100:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
