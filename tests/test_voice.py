"""Pruebas del troceado de audio y del detector de voz."""

from __future__ import annotations

import numpy as np
import pytest

from miky.voice.pipeline import VoicePipeline, VoiceSettings
from miky.voice.vad import CHUNK, ChunkBuffer, EnergySegmenter, Segment


def test_chunk_buffer_reagrupa_en_bloques_exactos() -> None:
    buffer = ChunkBuffer(CHUNK)
    signal = np.arange(17100, dtype=np.float32) / 17100.0
    blocks: list[np.ndarray] = []
    cursor = 0
    while cursor < signal.size:
        piece = signal[cursor : cursor + 171]
        cursor += piece.size
        blocks.extend(buffer.feed(piece))

    assert blocks, "debería haber producido bloques"
    assert all(block.size == CHUNK for block in blocks)
    esperados = (signal.size // CHUNK) * CHUNK
    reconstruido = np.concatenate(blocks)
    assert reconstruido.size == esperados
    assert np.allclose(reconstruido, signal[:esperados])
    assert buffer.pending_samples == signal.size - esperados


def test_chunk_buffer_con_un_bloque_grande() -> None:
    buffer = ChunkBuffer(CHUNK)
    blocks = buffer.feed(np.zeros(CHUNK * 3, dtype=np.float32))
    assert len(blocks) == 3
    assert buffer.pending_samples == 0


def test_chunk_buffer_reset() -> None:
    buffer = ChunkBuffer(CHUNK)
    buffer.feed(np.zeros(100, dtype=np.float32))
    assert buffer.pending_samples == 100
    buffer.reset()
    assert buffer.pending_samples == 0


def test_chunk_buffer_no_crece_sin_limite() -> None:
    buffer = ChunkBuffer(CHUNK)
    for _ in range(1000):
        buffer.feed(np.zeros(1, dtype=np.float32))
    assert buffer.pending_samples <= CHUNK * 200


def test_energy_segmenter_detecta_un_bloque_de_voz() -> None:
    segmenter = EnergySegmenter(threshold=0.5, min_silence_ms=400, min_speech_ms=200)
    # 200 ms de silencio, 1 s de ruido fuerte (simula voz), 600 ms de silencio
    rng = np.random.default_rng(0)
    silencio = np.zeros(CHUNK, dtype=np.float32)
    ruido = (rng.standard_normal(CHUNK) * 0.15).astype(np.float32)

    segments: list[Segment] = []
    for _ in range(7):
        segments.extend(segmenter.process(silencio))
    for _ in range(31):
        segments.extend(segmenter.process(ruido))
    for _ in range(20):
        segments.extend(segmenter.process(silencio))
    segments.extend(segmenter.flush())

    assert len(segments) == 1
    assert segments[0].duration_s > 0.8


def test_energy_segmenter_ignora_silencio() -> None:
    segmenter = EnergySegmenter()
    silence = np.zeros(CHUNK, dtype=np.float32)
    segments: list[Segment] = []
    for _ in range(100):
        segments.extend(segmenter.process(silence))
    assert segments == []


# ------------------------------------------------------------------ confirmación


def _pipeline() -> VoicePipeline:
    return VoicePipeline(
        VoiceSettings(mode="always", wake_word="miky", stt_model="base", warmup=False),
        on_command=lambda text: None,
    )


def _wait_window(pipeline: VoicePipeline, timeout: float = 3.0) -> None:
    """Espera a que la ventana de confirmación esté abierta (sin sleeps fijos)."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pipeline._confirm_event is not None:
            return
        time.sleep(0.01)
    raise AssertionError("la ventana de confirmación no se abrió")


@pytest.mark.parametrize(
    "respuesta",
    ["Sí", "sí, dale", "Borrala", "eliminala", "Dale, borrala", "Sí, confirmo", "ok"],
)
def test_confirmacion_por_voz_acepta_varias_formas(respuesta: str) -> None:
    import threading

    pipeline = _pipeline()
    result: list[bool] = []
    worker = threading.Thread(
        target=lambda: result.append(pipeline.expect_confirmation("", timeout=3)),
        daemon=True,
    )
    worker.start()
    _wait_window(pipeline)
    pipeline.feed_text(respuesta)
    worker.join(timeout=4)
    assert result == [True], respuesta


def test_confirmacion_por_voz_rechaza_con_no() -> None:
    import threading

    pipeline = _pipeline()
    result: list[bool] = []
    worker = threading.Thread(
        target=lambda: result.append(pipeline.expect_confirmation("", timeout=3)),
        daemon=True,
    )
    worker.start()
    _wait_window(pipeline)
    pipeline.feed_text("No, dejá")
    worker.join(timeout=4)
    assert result == [False]


def test_confirmacion_sin_respuesta_devuelve_falso() -> None:
    pipeline = _pipeline()
    assert pipeline.expect_confirmation("", timeout=0.2) is False


# ------------------------------------------------------------------ especulación


class _FakeSegmenter:
    """Se hace pasar por el VAD con una frase abierta y silencio al final."""

    def __init__(self, seconds: float = 1.0, silence_s: float = 0.3) -> None:
        self._audio = np.zeros(int(seconds * 16000), dtype=np.float32)
        self._silence = int(silence_s * 16000)

    @property
    def active(self) -> bool:
        return True

    @property
    def silence_samples(self) -> int:
        return self._silence

    def pending_audio(self) -> np.ndarray:
        return self._audio


class _FakeStt:
    def __init__(self, text: str = "hola mundo") -> None:
        self.text = text
        self.calls: list[int] = []

    def transcribe(self, audio, hotwords=None):  # noqa: ANN001
        self.calls.append(int(audio.size))
        return self.text


def test_especulacion_se_usa_si_coincide_el_audio() -> None:
    pipeline = _pipeline()
    pipeline.stt = _FakeStt()
    pipeline.segmenter = _FakeSegmenter(seconds=1.0)
    pipeline._maybe_speculate()
    assert pipeline._spec is not None
    pipeline._spec["thread"].join(timeout=2)

    audio = np.full(16000, 0.2, dtype=np.float32)
    text = pipeline._take_speculation(audio)
    assert text == "hola mundo"
    assert len(pipeline.stt.calls) == 1


def test_especulacion_se_descarta_si_siguio_hablando() -> None:
    pipeline = _pipeline()
    pipeline.stt = _FakeStt()
    pipeline.segmenter = _FakeSegmenter(seconds=1.0)
    pipeline._maybe_speculate()
    pipeline._spec["thread"].join(timeout=2)

    # El segmento final es 1,5 s más largo: la especulación no sirve.
    audio = np.full(16000 * 2, 0.2, dtype=np.float32)
    assert pipeline._take_speculation(audio) is None
    assert pipeline._spec is None


def test_especulacion_no_arranca_sin_silencio() -> None:
    pipeline = _pipeline()
    pipeline.stt = _FakeStt()
    pipeline.segmenter = _FakeSegmenter(seconds=1.0, silence_s=0.05)
    pipeline._maybe_speculate()
    assert pipeline._spec is None


def test_especulacion_no_arranca_con_audio_corto() -> None:
    pipeline = _pipeline()
    pipeline.stt = _FakeStt()
    pipeline.segmenter = _FakeSegmenter(seconds=0.2, silence_s=0.3)
    pipeline._maybe_speculate()
    assert pipeline._spec is None


def test_handle_segment_usa_la_especulacion_y_no_repite() -> None:
    hechos: list[str] = []
    pipeline = VoicePipeline(
        VoiceSettings(mode="always", wake_word="miky", stt_model="base", warmup=False),
        on_command=hechos.append,
    )
    pipeline.stt = _FakeStt("Miky, reproducir")
    pipeline.segmenter = _FakeSegmenter(seconds=1.0)
    pipeline._maybe_speculate()
    pipeline._spec["thread"].join(timeout=2)

    audio = np.full(16000, 0.2, dtype=np.float32)
    pipeline._handle_segment(Segment(audio=audio, duration_s=1.0))

    assert pipeline.stt.calls == [16000]  # una sola transcripción
    assert hechos == ["reproducir"]


def test_precalienta_frases_y_las_guarda(monkeypatch) -> None:
    import time

    from miky.voice.tts_edge import EdgeTts

    tts = EdgeTts(voice="es-AR-TomasNeural")
    tts._available = True
    tts._running = True
    generadas: list[str] = []

    async def fake_synthesize(text: str) -> bytes:
        generadas.append(text)
        return b"mp3"

    monkeypatch.setattr(tts, "_synthesize", fake_synthesize)
    tts.prewarm(["Listo.", "Dale."])
    for _ in range(50):
        if len(tts._cache) >= 2:
            break
        time.sleep(0.02)
    assert generadas == ["Listo.", "Dale."]
    assert set(tts._cache) == {"Listo.", "Dale."}


def test_cache_no_crece_sin_limite() -> None:
    from miky.voice.tts_edge import MAX_CACHE_ITEMS, EdgeTts

    tts = EdgeTts(voice="es-AR-TomasNeural")
    for index in range(MAX_CACHE_ITEMS + 10):
        tts._remember(f"frase {index}", b"x")
    assert len(tts._cache) <= MAX_CACHE_ITEMS


def test_no_guarda_audio_gigante() -> None:
    from miky.voice.tts_edge import MAX_CACHE_BYTES, EdgeTts

    tts = EdgeTts(voice="es-AR-TomasNeural")
    tts._remember("larga", b"x" * (MAX_CACHE_BYTES + 1))
    assert "larga" not in tts._cache


def test_una_orden_cualquiera_no_confirma() -> None:
    import threading

    pipeline = _pipeline()
    result: list[bool] = []
    worker = threading.Thread(
        target=lambda: result.append(pipeline.expect_confirmation("", timeout=0.6)),
        daemon=True,
    )
    worker.start()
    _wait_window(pipeline)
    pipeline.feed_text("poné un compresor en la batería")
    worker.join(timeout=2)
    assert result == [False]
