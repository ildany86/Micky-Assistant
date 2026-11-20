"""Administrador de voz: usa el motor principal y cae al respaldo si falla."""

from __future__ import annotations

from .. import log as log_mod

log = log_mod.get("miky.tts")


class TtsManager:
    """Envuelve dos motores para que la app no sepa cuál está hablando."""

    name = "manager"

    def __init__(self, primary, fallback=None) -> None:  # noqa: ANN001
        self.primary = primary
        self.fallback = fallback

    def start(self) -> None:
        try:
            self.primary.start()
        except Exception as exc:  # noqa: BLE001
            log.warning("el motor de voz principal no arrancó: %s", exc)
        if self.fallback is not None:
            try:
                self.fallback.start()
            except Exception:  # noqa: BLE001
                log.debug("el respaldo de voz no arrancó", exc_info=True)

    def close(self) -> None:
        for engine in (self.primary, self.fallback):
            if engine is None:
                continue
            try:
                engine.close()
            except Exception:  # noqa: BLE001
                pass

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        try:
            self.primary.speak(text)
        except Exception as exc:  # noqa: BLE001
            log.warning("falló el motor de voz principal: %s", exc)
            if self.fallback is not None:
                self.fallback.speak(text)

    def stop(self) -> None:
        for engine in (self.primary, self.fallback):
            if engine is None:
                continue
            try:
                engine.stop()
            except Exception:  # noqa: BLE001
                pass

    @property
    def available(self) -> bool:
        return bool(getattr(self.primary, "available", False)) or bool(
            getattr(self.fallback, "available", False)
        )

    @property
    def is_speaking(self) -> bool:
        return any(
            bool(getattr(engine, "is_speaking", False))
            for engine in (self.primary, self.fallback)
            if engine is not None
        )

    @property
    def error(self) -> str:
        return str(getattr(self.primary, "error", "")) or ""

    @property
    def voice_name(self) -> str:
        return str(getattr(self.primary, "voice_name", "")) or ""

    @property
    def output_name(self) -> str:
        return str(getattr(self.primary, "output_name", "")) or ""
