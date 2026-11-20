"""Proveedor compatible con OpenAI (OpenAI, Groq, OpenRouter, LM Studio, Ollama).

Permite que cada usuario elija su API sin tocar el motor: cualquier servicio que
hable `/chat/completions` con `tools` sirve.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from ..catalog import Catalog
from .. import log as log_mod
from . import AIError, AIProvider, AIResult
from .gemini import ASK_DECLARATION, ASK_TOOL, FRIENDLY_ERRORS, RESPOND_DECLARATION, RESPOND_TOOL
from .prompt import build_system_instruction, build_user_message

log = log_mod.get(__name__)

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "local": "http://127.0.0.1:1234/v1",
}


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "",
        temperature: float = 0.2,
        timeout_s: int = 30,
        name: str = "openai",
    ) -> None:
        self.name = name
        self.model = model
        self.api_key = api_key or ""
        self.base_url = (base_url or DEFAULT_BASE_URLS.get(name, "")).rstrip("/")
        self.temperature = temperature
        self.timeout_s = timeout_s

    def available(self) -> bool:
        return bool(self.base_url) and (bool(self.api_key) or self.name == "local")

    def interpret(self, text: str, context: dict[str, Any], catalog: Catalog) -> AIResult:
        if not self.base_url:
            raise AIError("Falta la URL base del proveedor (base_url).", kind="setup")

        tools = catalog.openai_tools()
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": ASK_TOOL,
                    "description": ASK_DECLARATION["description"],
                    "parameters": ASK_DECLARATION["parameters"],
                },
            }
        )
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": RESPOND_TOOL,
                    "description": RESPOND_DECLARATION["description"],
                    "parameters": RESPOND_DECLARATION["parameters"],
                },
            }
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": build_system_instruction(context, catalog, 12)},
                {"role": "user", "content": build_user_message(text)},
            ],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": self.temperature,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise AIError(FRIENDLY_ERRORS["network"], kind="network") from exc
        except TimeoutError as exc:
            raise AIError(FRIENDLY_ERRORS["timeout"], kind="timeout") from exc
        except json.JSONDecodeError as exc:
            raise AIError(FRIENDLY_ERRORS["schema"], kind="schema") from exc

        latency = (time.monotonic() - started) * 1000.0
        return _parse(body, catalog, self.name, self.model, latency)


def _parse(
    body: dict[str, Any],
    catalog: Catalog,
    provider: str,
    model: str,
    latency_ms: float,
) -> AIResult:
    result = AIResult(provider=provider, model=model, latency_ms=latency_ms)
    choices = body.get("choices") or []
    if not choices:
        result.question = "La IA no devolvió respuesta."
        return result

    message = choices[0].get("message") or {}
    tool_calls = message.get("tool_calls") or []
    for call in tool_calls:
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        raw_args = function.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (ValueError, TypeError):
            raise AIError(
                f"La IA devolvió argumentos inválidos para «{name}».", kind="schema"
            ) from None
        if name == ASK_TOOL:
            result.question = str(args.get("question") or "").strip()
            continue
        if name == RESPOND_TOOL:
            result.answer = str(args.get("text") or "").strip()
            continue
        spec = catalog.by_tool(name)
        if spec is None:
            log.warning("la IA llamó a una herramienta inexistente: %s", name)
            continue
        result.steps.append((spec.id, args))

    if not result.steps and not result.question and not result.answer:
        content = message.get("content") or ""
        result.question = str(content).strip() or "No entendí el pedido."
    elif result.question or result.answer:
        result.steps = []
    return result


def _http_error(exc: urllib.error.HTTPError) -> AIError:
    try:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
    except Exception:  # noqa: BLE001
        detail = ""
    if exc.code == 429:
        return AIError(FRIENDLY_ERRORS["quota"], kind="quota")
    if exc.code in (401, 403):
        return AIError(FRIENDLY_ERRORS["auth"], kind="auth")
    if exc.code >= 500:
        return AIError("El proveedor de IA está con problemas. Probá en un rato.", kind="network")
    return AIError(f"El proveedor rechazó el pedido ({exc.code}). {detail}".strip(), kind="schema")
