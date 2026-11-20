"""Mide qué tan bien entiende Miky: sintetiza frases, las transcribe y compara.

Uso:
    python tools/voice_accuracy.py                 # motor edge (voz real)
    python tools/voice_accuracy.py --engine sapi   # sin internet
    python tools/voice_accuracy.py --audio-dir audio/  # WAVs propios (001.wav…)

Mide dos cosas distintas:
- **WER**: qué tan bien transcribe (errores de palabra).
- **Acierto**: qué porcentaje de las frases termina en el comando correcto,
  que es lo que importa (el router tolera conjugaciones y sinónimos).
"""

from __future__ import annotations

import argparse
import asyncio
import re
import statistics
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from miky.bench import _load_wav  # noqa: E402
from miky.config import Config  # noqa: E402
from miky.router import match as router_match  # noqa: E402
from miky.voice.audio import resample  # noqa: E402
from miky.voice.stt import FasterWhisperStt  # noqa: E402
from miky.voice.wake import split_wake  # noqa: E402

# (frase, comando esperado). Frases reales del registro de voz y del catálogo.
PHRASES: list[tuple[str, str]] = [
    ("Miky, creá una pista de guitarra", "track.add"),
    ("Miky, subí el bajo dos dB", "track.adjust_volume"),
    ("Miky, bajá la voz un decibel", "track.adjust_volume"),
    ("Miky, poné el tempo en 96", "project.set_tempo"),
    ("Miky, activá el metrónomo", "project.set_metronome"),
    ("Miky, grabá", "transport.record"),
    ("Miky, detené la grabación", "transport.stop"),
    ("Miky, insertá un compresor en la voz", "fx.add"),
    ("Miky, borrá la pista tres", "track.delete"),
    ("Miky, muteá la batería", "track.mute"),
    ("Miky, dejá el bajo en solo", "track.solo"),
    ("Miky, abrí el mixer", "view.mixer"),
    ("Miky, abrí la matriz de ruteo", "view.routing"),
    ("Miky, paneá la guitarra a la izquierda", "track.pan"),
    ("Miky, renderizá la mezcla", "render.start"),
    ("Miky, guardá el proyecto", "project.save"),
    ("Miky, deshacé lo último", "project.undo"),
    ("Miky, mandá la voz al bus de voces", "send.add"),
    ("Miky, cargá el compresor de Eamut en la batería", "fx.add"),
    ("Miky, subile el volumen a la batería dos dB", "track.adjust_volume"),
]


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def _strip_wake(text: str) -> str:
    folded = _fold(text)
    return re.sub(
        r"^(hola |che |ok |okay |dale )?(miky|miki|miqui|vicky|biqui|maki|mickey|niki)\s+",
        "",
        folded,
    )


def _distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, word_a in enumerate(a, start=1):
        current = [i]
        for j, word_b in enumerate(b, start=1):
            cost = 0 if word_a == word_b else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def _synth_edge(text: str, path: Path, voice: str) -> bool:
    try:
        import edge_tts
    except ImportError:
        return False
    try:
        asyncio.run(edge_tts.Communicate(text, voice).save(str(path)))
        return path.exists() and path.stat().st_size > 1000
    except Exception as exc:  # noqa: BLE001
        print(f"  (edge falló: {exc})")
        return False


def _synth_sapi(text: str, path: Path) -> bool:
    from miky.bench import _synth_sapi as sapi

    return sapi(text, path)


def _read_audio(path: Path):  # noqa: ANN201
    import numpy as np

    if path.suffix.lower() == ".wav":
        try:
            audio, rate = _load_wav(path)
            return audio if rate == 16000 else resample(audio, rate, 16000)
        except Exception:  # noqa: BLE001 - puede ser MP3 con extensión .wav
            pass
    import miniaudio

    decoded = miniaudio.decode_file(
        str(path),
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=16000,
    )
    return np.array(decoded.samples, dtype=np.int16).astype(np.float32) / 32768.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Precisión del reconocimiento de Miky")
    parser.add_argument("--engine", choices=("edge", "sapi"), default="edge")
    parser.add_argument("--voice", default="es-AR-TomasNeural")
    parser.add_argument("--audio-dir", default="", help="carpeta con 001.wav, 002.wav…")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    config = Config.load()
    stt = FasterWhisperStt(
        model_size=config.voice.stt_model,
        language=config.voice.stt_language,
        beam_size=config.voice.stt_beam,
    )
    started = time.perf_counter()
    stt.ensure_loaded()
    print(f"modelo {config.voice.stt_model} cargado en {time.perf_counter() - started:.1f} s\n")

    work = Path(tempfile.mkdtemp(prefix="miky_acc_"))
    phrases = PHRASES[: args.limit] if args.limit else PHRASES
    rows: list[tuple[str, str, str, float, float, bool]] = []
    exact = 0
    resolved = 0
    resolvable = 0
    word_errors = 0
    word_total = 0
    times: list[float] = []

    for index, (phrase, expected) in enumerate(phrases, start=1):
        if args.audio_dir:
            path = Path(args.audio_dir) / f"{index:03d}.wav"
            if not path.exists():
                continue
        else:
            suffix = ".mp3" if args.engine == "edge" else ".wav"
            path = work / f"{index:03d}{suffix}"
            ok = (
                _synth_edge(phrase, path, args.voice)
                if args.engine == "edge"
                else _synth_sapi(phrase, path)
            )
            if not ok:
                print(f"[{index:02d}] no se pudo sintetizar: {phrase}")
                continue

        audio = _read_audio(path)
        started = time.perf_counter()
        heard = stt.transcribe(audio)
        elapsed = time.perf_counter() - started
        times.append(elapsed)

        reference = _strip_wake(phrase)
        hypothesis = _strip_wake(heard)
        distance = _distance(reference.split(), hypothesis.split())
        word_total += len(reference.split())
        word_errors += distance
        if reference == hypothesis:
            exact += 1

        # ¿El router llega al comando correcto con lo que entendió?
        activated, command_text = split_wake(heard, "miky")
        hit = router_match(command_text) if activated else None
        got = hit[0] if hit else "-"
        resolvable += 1
        if got == expected:
            resolved += 1
        rows.append((phrase, heard, got, elapsed, distance / max(1, len(reference.split())), got == expected))

    if not rows:
        print("no hay frases para medir")
        return 1

    print(f"{'frase':44s} {'reconocido':44s} {'router':26s} {'WER':>5s} {'s':>5s}")
    print("-" * 132)
    for phrase, heard, got, elapsed, wer, ok in rows:
        mark = " " if ok else "!"
        print(f"{mark}{phrase:43s} {heard:44s} {got:26s} {wer * 100:4.0f}% {elapsed:5.2f}")

    total_wer = word_errors / max(1, word_total)
    print("-" * 132)
    print(f"exactas (texto): {exact}/{len(rows)} ({exact / len(rows) * 100:.0f} %)")
    print(f"WER: {total_wer * 100:.1f} %")
    print(f"comando correcto: {resolved}/{resolvable} ({resolved / max(1, resolvable) * 100:.0f} %)")
    if times:
        print(
            f"reconocimiento: mediana {statistics.median(times):.2f} s "
            f"(min {min(times):.2f}, max {max(times):.2f})"
        )
    return 0 if resolved / max(1, resolvable) >= 0.9 else 2


if __name__ == "__main__":
    raise SystemExit(main())
