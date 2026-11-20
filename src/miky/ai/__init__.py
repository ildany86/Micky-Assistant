"""Interfaz común de proveedores de IA y fábrica de instancias.

El motor no sabe qué proveedor hay detrás: recibe un `AIResult` con pasos del
catálogo. Cambiar de Gemini a OpenAI/Groq/OpenRouter/LM Studio es cambiar la
configuración, no el código del asistente.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from ..catalog import Catalog
from ..config import AISection


class AIError(RuntimeError):
    """Falla al interpretar el pedido con la IA."""

    def __init__(self, message: str, kind: str = "unknown") -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class AIResult:
    steps: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    question: str = ""
    answer: str = ""
    note: str = ""
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    output_tokens: int = 0
    raw_text: str = ""

    @property
    def empty(self) -> bool:
        return not self.steps and not self.question and not self.answer


class AIProvider(abc.ABC):
    name: str = "base"
    model: str = ""

    @abc.abstractmethod
    def interpret(self, text: str, context: dict[str, Any], catalog: Catalog) -> AIResult:
        """Traduce una frase a pasos del catálogo o a una pregunta."""

    def available(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return f"{self.name}:{self.model}"


def build_provider(ai_config: AISection) -> AIProvider:
    from .gemini import GeminiProvider
    from .mock import MockProvider
    from .openai import OpenAICompatibleProvider

    provider = (ai_config.provider or "gemini").lower()
    if provider == "mock":
        return MockProvider()
    if provider in ("openai", "local", "groq", "openrouter"):
        return OpenAICompatibleProvider(
            api_key=ai_config.api_key,
            model=ai_config.model,
            base_url=ai_config.base_url,
            temperature=ai_config.temperature,
            timeout_s=ai_config.timeout_s,
            name=provider,
        )
    return GeminiProvider(
        api_key=ai_config.api_key,
        model=ai_config.model,
        temperature=ai_config.temperature,
        timeout_s=ai_config.timeout_s,
        thinking=getattr(ai_config, "thinking", "off"),
    )
