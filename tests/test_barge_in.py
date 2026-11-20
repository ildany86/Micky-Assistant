"""Barge-in: si el usuario habla mientras Miky habla, se corta la respuesta."""

from __future__ import annotations

from miky.voice.pipeline import BARGE_IN_BLOCKS, VoicePipeline, VoiceSettings


class _Tts:
    def __init__(self, speaking: bool = True) -> None:
        self.speaking = speaking
        self.stopped = 0

    @property
    def is_speaking(self) -> bool:
        return self.speaking

    def stop(self) -> None:
        self.stopped += 1
        self.speaking = False


def _pipeline(tts: _Tts, *, enabled: bool = True, level: float = 0.12) -> VoicePipeline:
    settings = VoiceSettings(barge_in=enabled, barge_in_level=level, mode="always")
    return VoicePipeline(settings, on_command=lambda _text: None, tts=tts)


def test_un_ruido_corto_no_corta_la_respuesta() -> None:
    tts = _Tts()
    pipeline = _pipeline(tts)
    assert pipeline._check_barge_in(0.5) is False
    assert tts.stopped == 0


def test_voz_sostenida_corta_la_respuesta() -> None:
    tts = _Tts()
    pipeline = _pipeline(tts)
    for _ in range(BARGE_IN_BLOCKS - 1):
        assert pipeline._check_barge_in(0.4) is False
    assert pipeline._check_barge_in(0.4) is True
    assert tts.stopped == 1
    # La frase que viene después es una orden: no hace falta la palabra clave.
    assert pipeline._awaiting_command is True


def test_el_silencio_reinicia_la_cuenta() -> None:
    tts = _Tts()
    pipeline = _pipeline(tts)
    for _ in range(BARGE_IN_BLOCKS - 1):
        pipeline._check_barge_in(0.4)
    pipeline._check_barge_in(0.0)
    for _ in range(BARGE_IN_BLOCKS - 1):
        assert pipeline._check_barge_in(0.4) is False
    assert tts.stopped == 0


def test_desactivado_no_corta() -> None:
    tts = _Tts()
    pipeline = _pipeline(tts, enabled=False)
    for _ in range(BARGE_IN_BLOCKS * 2):
        assert pipeline._check_barge_in(0.9) is False
    assert tts.stopped == 0


def test_umbral_alto_ignora_voz_baja() -> None:
    tts = _Tts()
    pipeline = _pipeline(tts, level=0.5)
    for _ in range(BARGE_IN_BLOCKS * 2):
        assert pipeline._check_barge_in(0.2) is False
    assert tts.stopped == 0


def test_si_no_esta_hablando_no_hace_nada() -> None:
    tts = _Tts(speaking=False)
    pipeline = _pipeline(tts)
    for _ in range(BARGE_IN_BLOCKS * 2):
        assert pipeline._check_barge_in(0.9) is False
    assert tts.stopped == 0
