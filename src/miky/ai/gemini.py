"""Proveedor Gemini (google-genai).

Se usa function calling manual: el SDK no ejecuta nada por su cuenta, solo
devuelve qué función llamó el modelo. Nosotros validamos contra el catálogo y
mandamos los pasos al puente.
"""

from __future__ import annotations

import time
from typing import Any

from ..catalog import Catalog
from .. import log as log_mod
from . import AIError, AIProvider, AIResult
from .prompt import build_system_instruction, build_user_message

log = log_mod.get(__name__)

ASK_TOOL = "miky_ask"
RESPOND_TOOL = "miky_respond"

ASK_DECLARATION = {
    "name": ASK_TOOL,
    "description": (
        "Hace una pregunta corta al usuario cuando falta un dato, hay ambigüedad "
        "o el pedido no tiene que ver con la sesión de REAPER."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Pregunta breve, en español rioplatense, para decir en voz alta.",
            }
        },
        "required": ["question"],
    },
}

RESPOND_DECLARATION = {
    "name": RESPOND_TOOL,
    "description": (
        "Explica algo o contesta una duda en una o dos frases. Usalo SOLO si no hay "
        "ningún comando que ejecutar (consejos, diagnósticos) o como comentario FINAL, "
        "después de haber llamado a los comandos en este mismo turno. Si en el texto "
        "decís que hiciste algo, ese algo tiene que estar hecho con una herramienta: "
        "no alcanza con decirlo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": (
                    "Respuesta breve (2 o 3 frases), concreta y en español rioplatense, "
                    "pensada para escucharse."
                ),
            }
        },
        "required": ["text"],
    },
}

FRIENDLY_ERRORS = {
    "quota": "Se agotó la cuota de la API por ahora. Probá de nuevo en unos minutos.",
    "auth": "La API key no es válida o no tiene permisos. Revisala en Ajustes.",
    "network": "No pude conectar con la IA. Fijate la conexión a internet.",
    "timeout": "La IA tardó demasiado en responder.",
    "schema": "La IA devolvió una respuesta que no pude interpretar.",
}


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.5-flash-lite",
        temperature: float = 0.2,
        timeout_s: int = 30,
        thinking: str = "off",
    ) -> None:
        self.api_key = api_key or ""
        self.model = model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.thinking = thinking
        self._client = None
        self._tool = None
        self._tool_catalog_id: int | None = None

    # ---------- infraestructura ----------

    def available(self) -> bool:
        return bool(self.api_key)

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise AIError("Falta la API key de Gemini.", kind="auth")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise AIError(
                "Falta el paquete google-genai. Instalalo con: pip install google-genai",
                kind="setup",
            ) from exc

        try:
            http_options = types.HttpOptions(timeout=int(self.timeout_s * 1000))
            self._client = genai.Client(api_key=self.api_key, http_options=http_options)
        except Exception:  # noqa: BLE001 - versiones viejas del SDK
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _ensure_tool(self, catalog: Catalog):
        cache_key = id(catalog)
        if self._tool is not None and self._tool_catalog_id == cache_key:
            return self._tool
        from google.genai import types

        declarations = [
            _make_declaration(types, item) for item in catalog.function_declarations()
        ]
        declarations.append(_make_declaration(types, ASK_DECLARATION))
        declarations.append(_make_declaration(types, RESPOND_DECLARATION))
        self._tool = types.Tool(function_declarations=declarations)
        self._tool_catalog_id = cache_key
        return self._tool

    # ---------- API ----------

    def interpret(self, text: str, context: dict[str, Any], catalog: Catalog) -> AIResult:
        from google.genai import types

        client = self._ensure_client()
        tool = self._ensure_tool(catalog)

        config_kwargs: dict[str, Any] = {
            "system_instruction": build_system_instruction(context, catalog, 12),
            "tools": [tool],
            "temperature": self.temperature,
        }
        # Para un asistente que tiene que contestar ya, el "pensamiento" interno
        # del modelo es tiempo perdido: se apaga.
        if self.thinking in ("off", "low") and hasattr(types, "ThinkingConfig"):
            try:
                if self.thinking == "off":
                    config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                else:
                    config_kwargs["thinking_config"] = types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.LOW
                    )
            except Exception:  # noqa: BLE001
                log.debug("este modelo no acepta configuración de pensamiento")
        try:
            config_kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
                disable=True
            )
        except AttributeError:  # pragma: no cover
            pass

        started = time.monotonic()
        try:
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=build_user_message(text),
                    config=types.GenerateContentConfig(**config_kwargs),
                )
            except Exception as exc:  # noqa: BLE001
                if "thinking_config" not in config_kwargs:
                    raise
                # Algunos modelos rechazan la configuración de pensamiento:
                # se reintenta sin ella en vez de romper el pedido.
                log.warning("el modelo rechazó la configuración de pensamiento; reintento sin ella")
                config_kwargs.pop("thinking_config", None)
                response = client.models.generate_content(
                    model=self.model,
                    contents=build_user_message(text),
                    config=types.GenerateContentConfig(**config_kwargs),
                )
        except Exception as exc:  # noqa: BLE001 - se traduce a mensaje humano
            raise _translate_exception(exc) from exc

        latency = (time.monotonic() - started) * 1000.0
        result = AIResult(provider=self.name, model=self.model, latency_ms=latency)
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            result.prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
            result.output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)

        calls = getattr(response, "function_calls", None) or []
        for call in calls:
            name = getattr(call, "name", "") or ""
            args = _plain(getattr(call, "args", {}) or {})
            if name == ASK_TOOL:
                result.question = str(args.get("question") or "").strip()
                continue
            if name == RESPOND_TOOL:
                result.answer = str(args.get("text") or "").strip()
                continue
            spec = catalog.by_tool(name)
            if spec is None:
                # El modelo a veces inventa nombres de herramienta: se ignora
                # esa llamada en vez de romper todo el pedido.
                log.warning("la IA llamó a una herramienta inexistente: %s", name)
                continue
            result.steps.append((spec.id, args))

        if not result.steps and not result.question and not result.answer:
            text_reply = _safe_text(response)
            result.question = text_reply.strip() or "No entendí el pedido."
        elif result.steps and (result.question or result.answer):
            # Si pidió datos o contestó algo, no se ejecutan los pasos.
            result.steps = []
        return result


def _make_declaration(types, item: dict[str, Any]):
    """Arma una FunctionDeclaration tolerando diferencias entre versiones del SDK."""
    try:
        return types.FunctionDeclaration(
            name=item["name"],
            description=item["description"],
            parameters_json_schema=item["parameters"],
        )
    except (TypeError, ValueError):
        return types.FunctionDeclaration(
            name=item["name"],
            description=item["description"],
            parameters=_to_gemini_schema(types, item["parameters"]),
        )


def _to_gemini_schema(types, schema: dict[str, Any]):
    type_map = {
        "object": "OBJECT",
        "string": "STRING",
        "number": "NUMBER",
        "integer": "INTEGER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
    }
    kwargs: dict[str, Any] = {"type": type_map.get(schema.get("type", "string"), "STRING")}
    if schema.get("description"):
        kwargs["description"] = schema["description"]
    if schema.get("enum"):
        kwargs["enum"] = [str(value) for value in schema["enum"]]
    if schema.get("minimum") is not None:
        kwargs["minimum"] = float(schema["minimum"])
    if schema.get("maximum") is not None:
        kwargs["maximum"] = float(schema["maximum"])
    if schema.get("items"):
        kwargs["items"] = _to_gemini_schema(types, schema["items"])
    if schema.get("properties"):
        kwargs["properties"] = {
            name: _to_gemini_schema(types, value)
            for name, value in schema["properties"].items()
        }
    if schema.get("required"):
        kwargs["required"] = list(schema["required"])
    return types.Schema(**kwargs)


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "items"):
        try:
            return {str(key): _plain(item) for key, item in value.items()}
        except Exception:  # noqa: BLE001
            return value
    return value


def _safe_text(response) -> str:
    try:
        return response.text or ""
    except Exception:  # noqa: BLE001 - el SDK tira ValueError si no hay texto
        return ""


def _translate_exception(exc: Exception) -> AIError:
    message = str(exc)
    lowered = message.lower()
    if "429" in message or "resource_exhausted" in lowered or "quota" in lowered:
        return AIError(FRIENDLY_ERRORS["quota"], kind="quota")
    if (
        "401" in message
        or "403" in message
        or "api key" in lowered
        or "unauthenticated" in lowered
        or "permission" in lowered
    ):
        return AIError(FRIENDLY_ERRORS["auth"], kind="auth")
    if "timeout" in lowered or "timed out" in lowered:
        return AIError(FRIENDLY_ERRORS["timeout"], kind="timeout")
    if (
        "connection" in lowered
        or "network" in lowered
        or "getaddrinfo" in lowered
        or "ssl" in lowered
    ):
        return AIError(FRIENDLY_ERRORS["network"], kind="network")
    if "400" in message or "invalid_argument" in lowered:
        return AIError(
            "La consulta a Gemini fue rechazada (400). Puede ser el modelo elegido o el esquema de funciones.",
            kind="schema",
        )
    return AIError(f"Error de la IA: {message}", kind="unknown")
