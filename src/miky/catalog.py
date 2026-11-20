"""Catálogo cerrado de comandos y validación de argumentos.

El catálogo es la única superficie de control: la IA no puede inventar
comandos ni ejecutar código. Cada comando tiene un id fijo, parámetros tipados
y una plantilla de respuesta hablada.

Este módulo carga `data/commands.json`, valida argumentos y genera los esquemas
que se le pasan a los proveedores de IA.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import paths

SUPPORTED_TYPES = {"string", "number", "integer", "boolean", "array"}


class ValidationError(ValueError):
    """Los argumentos de un comando no son válidos."""

    def __init__(self, message: str, command: str = "") -> None:
        super().__init__(message)
        self.command = command


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str
    description: str = ""
    enum: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    items_type: str | None = None
    max_length: int | None = None

    def json_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"type": self.type, "description": self.description}
        if self.enum:
            schema["enum"] = list(self.enum)
        if self.minimum is not None:
            schema["minimum"] = self.minimum
        if self.maximum is not None:
            schema["maximum"] = self.maximum
        if self.type == "array":
            schema["items"] = {"type": self.items_type or "string"}
        return schema


@dataclass(frozen=True)
class CommandSpec:
    id: str
    category: str
    summary: str
    params: dict[str, ParamSpec] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    danger: bool = False
    speech: str = ""
    pre_speech: str = ""
    examples: tuple[str, ...] = ()

    @property
    def tool_name(self) -> str:
        return self.id.replace(".", "_")

    def schema(self) -> dict[str, Any]:
        properties = {name: spec.json_schema() for name, spec in self.params.items()}
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if self.required:
            schema["required"] = list(self.required)
        return schema

    def llm_description(self) -> str:
        text = self.summary.strip()
        if self.examples:
            sample = self.examples[0]
            text += f' Ejemplo de pedido: «{sample}».'
        return text


class Catalog:
    def __init__(self, commands: Iterable[CommandSpec], version: int = 1) -> None:
        self._by_id = {spec.id: spec for spec in commands}
        self._by_tool = {spec.tool_name: spec for spec in self._by_id.values()}
        self.version = version

    # ---------- carga ----------

    @classmethod
    def load(cls, path: Path | None = None) -> "Catalog":
        target = path or paths.bundled_commands()
        raw = json.loads(target.read_text(encoding="utf-8"))
        specs: list[CommandSpec] = []
        for item in raw.get("commands", []):
            params: dict[str, ParamSpec] = {}
            for name, param in (item.get("params") or {}).items():
                param_type = str(param.get("type") or "string").lower()
                if param_type not in SUPPORTED_TYPES:
                    raise ValueError(f"tipo de parámetro no soportado: {param_type} en {item['id']}.{name}")
                params[name] = ParamSpec(
                    name=name,
                    type=param_type,
                    description=str(param.get("description") or ""),
                    enum=tuple(param.get("enum") or ()),
                    minimum=param.get("minimum"),
                    maximum=param.get("maximum"),
                    items_type=(param.get("items") or {}).get("type"),
                    max_length=param.get("maxLength"),
                )
            specs.append(
                CommandSpec(
                    id=str(item["id"]),
                    category=str(item.get("category") or "otros"),
                    summary=str(item.get("summary") or ""),
                    params=params,
                    required=tuple(item.get("required") or ()),
                    danger=bool(item.get("danger")),
                    speech=str(item.get("speech") or ""),
                    pre_speech=str(item.get("pre_speech") or ""),
                    examples=tuple(item.get("examples") or ()),
                )
            )
        return cls(specs, version=int(raw.get("version") or 1))

    # ---------- consulta ----------

    def get(self, command_id: str) -> CommandSpec | None:
        return self._by_id.get(command_id)

    def by_tool(self, tool_name: str) -> CommandSpec | None:
        return self._by_tool.get(tool_name)

    def all(self) -> list[CommandSpec]:
        return list(self._by_id.values())

    def subset(self, command_ids: Iterable[str] | None) -> "Catalog":
        """Catálogo reducido a esos comandos (mantiene el orden original).

        Se usa para mandarle a la IA solo las herramientas que importan.
        """
        if not command_ids:
            return self
        wanted = set(command_ids)
        selected = [spec for spec in self._by_id.values() if spec.id in wanted]
        return Catalog(selected, version=self.version) if selected else self

    def ids(self) -> list[str]:
        return list(self._by_id.keys())

    def categories(self) -> dict[str, list[CommandSpec]]:
        result: dict[str, list[CommandSpec]] = {}
        for spec in self._by_id.values():
            result.setdefault(spec.category, []).append(spec)
        return result

    # ---------- esquemas para proveedores ----------

    def function_declarations(self) -> list[dict[str, Any]]:
        """Formato neutral: una declaración por comando."""
        return [
            {
                "name": spec.tool_name,
                "description": spec.llm_description(),
                "parameters": spec.schema(),
            }
            for spec in self._by_id.values()
        ]

    def openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.tool_name,
                    "description": spec.llm_description(),
                    "parameters": spec.schema(),
                },
            }
            for spec in self._by_id.values()
        ]

    # ---------- validación ----------

    def validate(self, command_id: str, args: dict[str, Any] | None) -> dict[str, Any]:
        spec = self.get(command_id)
        if spec is None:
            raise ValidationError(f"comando desconocido: {command_id}", command_id)
        args = dict(args or {})

        missing = [name for name in spec.required if args.get(name) in (None, "")]
        if missing:
            raise ValidationError(
                f"falta {', '.join(missing)} para {spec.id}", command_id
            )

        clean: dict[str, Any] = {}
        for name, value in args.items():
            param = spec.params.get(name)
            if param is None:
                # El modelo a veces agrega campos de más: se descartan.
                continue
            if value is None or value == "":
                if name in spec.required:
                    raise ValidationError(f"falta {name} para {spec.id}", command_id)
                continue
            clean[name] = _coerce_param(param, value, spec.id)
        return clean


def _coerce_param(param: ParamSpec, value: Any, command_id: str) -> Any:
    if param.type == "string":
        text = value if isinstance(value, str) else str(value)
        text = text.strip()
        if param.max_length and len(text) > param.max_length:
            text = text[: param.max_length]
        if param.enum:
            lowered = {item.lower(): item for item in param.enum}
            match = lowered.get(text.lower())
            if match is None:
                raise ValidationError(
                    f"valor inválido para {param.name}: «{text}» (opciones: {', '.join(param.enum)})",
                    command_id,
                )
            return match
        return text

    if param.type in ("number", "integer"):
        if isinstance(value, bool):
            raise ValidationError(f"{param.name} debe ser un número", command_id)
        number: float
        if isinstance(value, (int, float)):
            number = float(value)
        else:
            text = str(value).replace(",", ".").strip()
            try:
                number = float(text)
            except ValueError as exc:
                raise ValidationError(f"{param.name} debe ser un número (llegó «{value}»)", command_id) from exc
        if param.minimum is not None and number < param.minimum:
            number = param.minimum
        if param.maximum is not None and number > param.maximum:
            number = param.maximum
        return int(round(number)) if param.type == "integer" else number

    if param.type == "boolean":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "si", "sí", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off"):
            return False
        raise ValidationError(f"{param.name} debe ser verdadero o falso", command_id)

    if param.type == "array":
        if isinstance(value, (str, int, float)):
            value = [value]
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"{param.name} debe ser una lista", command_id)
        items = []
        for item in value:
            if isinstance(item, str):
                items.append(item.strip())
            else:
                items.append(str(item))
        return [item for item in items if item]

    return value
