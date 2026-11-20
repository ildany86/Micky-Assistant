"""Medición de cada etapa de Miky en la máquina del usuario.

Sirve para decidir con números: cuánto tarda el reconocimiento, la IA, la voz y
el puente. No toca REAPER (solo le pregunta si está abierto) ni modifica nada.

Uso: python -m miky bench
"""

from __future__ import annotations

import tempfile
import time
import wave
from pathlib import Path

from . import log as log_mod
from .config import Config

BENCH_PHRASE = "Miky, subí el bajo dos decibeles y armá la pista"


def _synth_sapi(text: str, target: Path) -> bool:
    """Escribe la frase a WAV con la voz SAPI (sin internet)."""
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        return False
    try:
        comtypes.CoInitialize()
    except OSError:
        pass
    try:
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        stream = comtypes.client.CreateObject("SAPI.SpFileStream")
        stream.Open(str(target), 3, False)  # SSFMCreateForWrite
        voice.AudioOutputStream = stream
        voice.Speak(text, 0)
        stream.Close()
        voice.AudioOutputStream = None
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  no pude sintetizar la frase de prueba: {exc}")
        return False
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


def _load_wav(path: Path) -> tuple["object", int]:
    import numpy as np

    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        data = handle.readframes(handle.getnframes())
    if width == 2:
        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        audio = np.frombuffer(data, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, rate


def _bench_router() -> float:
    from . import router

    started = time.perf_counter()
    for _ in range(500):
        router.match("subí la guitarra 2 dB")
    return (time.perf_counter() - started) / 500 * 1000


def _bench_stt(config: Config, prepared: dict | None = None) -> tuple[float, float, str]:
    from .voice.audio import resample
    from .voice.stt import FasterWhisperStt

    if prepared is None:
        work = Path(tempfile.mkdtemp(prefix="miky_bench_"))
        wav = work / "frase.wav"
        if not _synth_sapi(BENCH_PHRASE, wav):
            return 0.0, 0.0, ""
        audio, rate = _load_wav(wav)
        audio = resample(audio, rate, 16000)
        stt = FasterWhisperStt(
            model_size=config.voice.stt_model,
            language=config.voice.stt_language,
            beam_size=config.voice.stt_beam,
        )
        started = time.perf_counter()
        stt.ensure_loaded()
        load_s = time.perf_counter() - started
        prepared = {
            "stt": stt,
            "audio": audio,
            "load": load_s,
            "note": f"{stt.transcribe(audio)[:70]} (carga {load_s:.1f} s)",
        }

    stt = prepared["stt"]
    audio = prepared["audio"]
    started = time.perf_counter()
    text = stt.transcribe(audio)
    seconds = time.perf_counter() - started
    prepared["note"] = f"{text[:70]} (carga {prepared['load']:.1f} s)"
    return seconds, audio.size / 16000, prepared["note"]


def _bench_tts(config: Config) -> float:
    from .voice.tts import SapiTts
    from .voice.tts_edge import EdgeTts

    phrase = "Listo, borré seis pistas."
    if config.voice.tts_engine in ("edge", "auto"):
        tts = EdgeTts(voice=config.voice.edge_voice, output_device=config.voice.output_device)
        tts._available = True
        started = time.perf_counter()
        try:
            import asyncio

            asyncio.run(tts._synthesize(phrase))
        except Exception as exc:  # noqa: BLE001
            print(f"  la voz online falló ({exc}); mido la local")
        else:
            return (time.perf_counter() - started) * 1000
    sapi = SapiTts(voice_hint=config.voice.tts_voice, output_device=config.voice.output_device)
    sapi.start()
    started = time.perf_counter()
    sapi.speak(phrase)
    elapsed = (time.perf_counter() - started) * 1000
    sapi.close()
    return elapsed


def _bench_ai(config: Config) -> tuple[float, str]:
    from . import intent
    from .ai import build_provider
    from .catalog import Catalog

    provider = build_provider(config.ai)
    if not provider.available():
        return 0.0, "sin API key"
    catalog = Catalog.load()
    phrase = "cargá un compresor en la voz"
    # Igual que la app: solo las herramientas de la familia detectada.
    ids = intent.commands_for_text(phrase)
    limited = catalog.subset(ids) if ids else catalog
    context = {
        "assistant": {"name": "Miky"},
        "tracks": [{"index": 1, "name": "Bajo"}, {"index": 2, "name": "Voz"}],
    }
    started = time.perf_counter()
    try:
        result = provider.interpret(phrase, context, limited)
    except Exception as exc:  # noqa: BLE001
        return (time.perf_counter() - started) * 1000, f"error: {exc}"
    elapsed = (time.perf_counter() - started) * 1000
    return elapsed, (
        f"{len(result.steps)} pasos · {result.prompt_tokens} tokens de entrada"
        f" · {len(limited.all())} herramientas"
    )


def _bench_bridge() -> tuple[float, str]:
    from . import reaper
    from .bridge import BridgeClient

    if not reaper.is_reaper_running():
        return 0.0, "REAPER cerrado"
    client = BridgeClient()
    started = time.perf_counter()
    reply = client.call_one("ping", timeout=3.0)
    elapsed = (time.perf_counter() - started) * 1000
    return elapsed, "ok" if reply.ok else "sin respuesta"


def run(config: Config | None = None, repeat: int = 3) -> int:
    log_mod.setup("WARNING")
    config = config or Config.load()

    print("Miky · medición de tiempos (no modifica nada)\n")
    print(f"  modelo de voz: {config.voice.stt_model} · voz: {config.voice.tts_engine}")
    print(f"  repeticiones por etapa: {repeat} (se informa la mediana)\n")

    def median(values: list[float]) -> float:
        ordered = sorted(values)
        if not ordered:
            return 0.0
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2

    router_ms = _bench_router()
    print(f"  router local        {router_ms:7.2f} ms   (pedido que no usa IA)")

    try:
        times: list[float] = []
        note = ""
        audio_s = 0.0
        prepared: dict | None = None
        for _ in range(max(1, repeat)):
            seconds, audio_s, note = _bench_stt(config, prepared)
            if seconds:
                times.append(seconds)
        if times:
            best = median(times)
            rtf = best / audio_s if audio_s else 0
            print(
                f"  reconocimiento      {best:7.2f} s    {audio_s:.1f} s de audio"
                f" · {rtf:.2f}× tiempo real"
            )
            print(f"      → {note}")
    except Exception as exc:  # noqa: BLE001
        print(f"  reconocimiento      error: {exc}")

    try:
        voces = [_bench_tts(config) for _ in range(max(1, repeat))]
        print(f"  voz (síntesis)      {median(voces):7.0f} ms")
    except Exception as exc:  # noqa: BLE001
        print(f"  voz (síntesis)      error: {exc}")

    try:
        values: list[float] = []
        note = ""
        for _ in range(max(1, repeat)):
            ai_ms, note = _bench_ai(config)
            if ai_ms:
                values.append(ai_ms)
        if values:
            print(f"  IA (una llamada)    {median(values):7.0f} ms   {note}")
        else:
            print(f"  IA (una llamada)      s/d      {note}")
    except Exception as exc:  # noqa: BLE001
        print(f"  IA (una llamada)    error: {exc}")

    try:
        bridge_ms, note = _bench_bridge()
        print(f"  puente REAPER       {bridge_ms:7.1f} ms   {note}")
    except Exception as exc:  # noqa: BLE001
        print(f"  puente REAPER       error: {exc}")

    print("\n  Referencia: una orden hablada suma silencio + reconocimiento + IA + voz.")
    return 0


__all__ = ["run", "BENCH_PHRASE"]
