"""Miky: asistente de voz local para REAPER.

La app corre en Windows, escucha y habla localmente, y usa una API en la nube
(Gemini por defecto) solo para interpretar las ordenes. Todo el control de
REAPER se hace por un puente ReaScript propio.
"""

from __future__ import annotations

__version__ = "0.1.0b3"
__version_display__ = "0.1.0 beta 3"

APP_NAME = "Miky"
APP_TAGLINE = "Asistente de grabación para REAPER"

__all__ = ["__version__", "__version_display__", "APP_NAME", "APP_TAGLINE"]
