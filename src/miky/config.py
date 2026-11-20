"""Configuración de Miky: dataclasses + lectura/escritura TOML.

Un solo archivo (`%APPDATA%\\Miky\\config.toml`) editables a mano o desde la
interfaz. La API key se guarda cifrada con DPAPI.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from . import paths
from .security import decrypt_secret, encrypt_secret

ENV_KEY_NAMES = ("MIKY_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")

PROVIDERS = ("gemini", "openai", "local", "mock")
STT_MODELS = ("tiny", "base", "small", "medium")
VOICE_MODES = ("always", "push_to_talk")
SECTIONS = ("app", "reaper", "bridge", "ai", "voice", "ui", "safety", "render")


@dataclass
class AppSection:
    language: str = "es"
    log_level: str = "INFO"


@dataclass
class ReaperSection:
    install_path: str = ""
    resource_path: str = ""
    auto_install_bridge: bool = True
    auto_launch: bool = False


@dataclass
class BridgeSection:
    command_timeout_ms: int = 8000
    render_timeout_ms: int = 1_800_000
    heartbeat_stale_ms: int = 3500


@dataclass
class AISection:
    provider: str = "gemini"
    model: str = "gemini-3.5-flash-lite"
    model_strong: str = "gemini-3.5-flash"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.2
    # "off" | "low" | "" (sin tocar). En flash-lite, off da error y low no
    # cambia los tiempos: por defecto no se manda nada.
    thinking: str = ""
    max_steps: int = 12
    timeout_s: int = 15
    direct_commands: bool = True
    recovery: bool = False


@dataclass
class VoiceSection:
    enabled: bool = True
    wake_word: str = "miky"
    mode: str = "always"
    input_device: str = ""
    stt_engine: str = "faster_whisper"
    stt_model: str = "base"
    stt_language: str = "es"
    stt_beam: int = 1
    tts_engine: str = "edge"
    tts_voice: str = ""
    edge_voice: str = "es-AR-TomasNeural"
    tts_rate: int = 0
    output_device: str = ""
    speak_replies: bool = True
    chime: bool = True
    vad_threshold: float = 0.5
    silence_ms: int = 550
    # Palabras propias (marcas de plugins, nombres de proyectos) que conviene
    # sesgar en el reconocimiento: "Eamut", "SSL", "Guitar Rig"…
    vocabulary: tuple[str, ...] = ()
    # Correcciones de transcripción, "lo que dijo mal=lo que quiso decir".
    corrections: tuple[str, ...] = ()
    # Cómo contesta: "voz" (todo hablado), "mixto" (sonido al salir bien, voz
    # en errores y preguntas) o "sonidos" (solo sonidos; habla preguntas).
    feedback: str = "mixto"
    max_utterance_s: float = 20.0
    confirm_timeout_s: float = 12.0
    follow_up_seconds: float = 8.0
    warmup_on_start: bool = True


@dataclass
class UISection:
    position: tuple[int, int] = (-1, -1)
    scale: float = 1.0
    always_on_top: bool = True
    logo: str = ""
    show_tooltips: bool = True
    opacity: float = 1.0


@dataclass
class SafetySection:
    confirm_destructive: bool = True
    ask_before_record: bool = True
    allowed_render_roots: tuple[str, ...] = ()


@dataclass
class RenderSection:
    default_dir: str = ""
    default_pattern: str = "$project"


@dataclass
class Config:
    app: AppSection = field(default_factory=AppSection)
    reaper: ReaperSection = field(default_factory=ReaperSection)
    bridge: BridgeSection = field(default_factory=BridgeSection)
    ai: AISection = field(default_factory=AISection)
    voice: VoiceSection = field(default_factory=VoiceSection)
    ui: UISection = field(default_factory=UISection)
    safety: SafetySection = field(default_factory=SafetySection)
    render: RenderSection = field(default_factory=RenderSection)

    path: Path | None = None
    api_key_from_env: bool = False

    # ---------- persistencia ----------

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        target = path or paths.config_file()
        config = cls()
        if target.exists():
            try:
                raw = tomllib.loads(target.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):
                raw = {}
            config = cls._from_mapping(raw)
        config.path = target
        config._apply_env_key()
        return config

    @classmethod
    def _from_mapping(cls, raw: dict[str, Any]) -> "Config":
        config = cls()
        for section_name in SECTIONS:
            section_obj = getattr(config, section_name)
            values = raw.get(section_name) or {}
            if not isinstance(values, dict):
                continue
            for f in fields(section_obj):
                if f.name not in values:
                    continue
                value = values[f.name]
                try:
                    setattr(section_obj, f.name, _coerce(value, f.default))
                except (TypeError, ValueError):
                    continue
        # Compatibilidad: la key cifrada se descifra al cargar.
        config.ai.api_key = decrypt_secret(config.ai.api_key)
        config._fix_device_names()
        return config

    def _fix_device_names(self) -> None:
        """Descarta pseudo-dispositivos guardados por versiones anteriores."""
        try:
            from .voice.audio import is_pseudo_device
        except Exception:  # noqa: BLE001 - sin audio disponible
            return
        if self.voice.input_device and is_pseudo_device(self.voice.input_device):
            self.voice.input_device = ""

    def _apply_env_key(self) -> None:
        if self.ai.api_key:
            return
        for name in ENV_KEY_NAMES:
            value = os.environ.get(name)
            if value:
                self.ai.api_key = value.strip()
                self.api_key_from_env = True
                return

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path or paths.config_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        serializable = self._as_mapping(for_save=True)
        text = _dump_toml(serializable)
        tmp = target.with_suffix(".toml.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(target)
        self.path = target
        return target

    def _as_mapping(self, for_save: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for section_name in SECTIONS:
            section_obj = getattr(self, section_name)
            values: dict[str, Any] = {}
            for f in fields(section_obj):
                value = getattr(section_obj, f.name)
                if for_save and section_name == "ai" and f.name == "api_key":
                    value = encrypt_secret(value) if value else ""
                if isinstance(value, tuple):
                    value = list(value)
                values[f.name] = value
            out[section_name] = values
        return out

    # ---------- ayudas ----------

    @property
    def has_api_key(self) -> bool:
        return bool(self.ai.api_key)

    def timeout_for(self, command: str) -> float:
        if command.startswith("render."):
            return self.bridge.render_timeout_ms / 1000.0
        return self.bridge.command_timeout_ms / 1000.0


def _coerce(value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "si", "sí", "yes", "on")
        return bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        return int(value)
    if isinstance(default, float):
        return float(value)
    if isinstance(default, tuple):
        if isinstance(value, (list, tuple)):
            return tuple(value)
        return default
    return str(value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def _dump_toml(mapping: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Configuracion de Miky",
        "# Generado por la aplicacion. Se puede editar a mano y reiniciar.",
        "",
    ]
    for section, values in mapping.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines)
