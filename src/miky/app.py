"""Orquestador de Miky: une voz, IA, motor de comandos, puente y interfaz."""

from __future__ import annotations

import collections
import re
import sys
import threading
import time
from typing import Any

from . import __version__, knowledge, log as log_mod, paths, reaper, router, speech
from .ai import AIError, AIProvider, AIResult, build_provider
from .bridge import BridgeClient, BridgeError, BridgeStatus
from .catalog import Catalog
from .config import Config
from .engine import Executor, Plan, PlanError
from .voice import wake
from .voice.feedback import chime
from .voice.stt import FasterWhisperStt, is_available as stt_available
from .voice.tts import NullTts, SapiTts
from .voice.tts_edge import EdgeTts
from .voice.tts_manager import TtsManager
from .voice.pipeline import VoicePipeline, VoiceSettings

log = log_mod.get("miky.app")

NO_KEY_MESSAGE = (
    "Todavía no tengo una API key configurada. Abrí los ajustes desde el icono "
    "y pegala; sin eso solo entiendo órdenes básicas."
)

FX_PREFIXES = ("VST3i: ", "VST3: ", "VSTi: ", "VST: ", "AU: ", "JS: ", "DX: ", "CLAP: ", "LV2: ")

CHOICE_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "al", "que", "con",
    "ponele", "pone", "pon", "dale", "carga", "cargá", "usa", "usá", "quiero",
    "opcion", "opción", "numero", "número", "ese", "esa", "este", "esta",
    "plugin", "el", "primero", "segundo", "tercero",
}

# "abrí REAPER", "abre el reaper": no es un comando de REAPER, es una acción de
# la app (el puente todavía no existe si REAPER está cerrado).
OPEN_REAPER_PATTERN = re.compile(r"\b(abri|abre|abrime|abreme|inicia|arranca)\b.*\breaper\b")

# Verbos en pasado con los que el modelo suele afirmar que hizo algo. Si
# aparecen en una respuesta sin ningún comando ejecutado, es una alucinación.
_ACTION_CLAIM = re.compile(
    r"\b(hice|puse|deje|cargue|cambie|arme|borre|movi|silencie|abri|cerre|"
    r"asigne|renombre|duplique|renderice|exporte|acomode|ordene|guarde|"
    r"mande|rutee|conecte|derive)\b",
    re.IGNORECASE,
)

_QUESTION_STARTS = (
    "que ", "como ", "por que", "para que", "decime", "explicame", "contame",
    "cual ", "cuando", "donde", "cuanto", "hay ", "tenes ", "podes ",
)

EXPLAIN_NOTE = (
    "[No ejecutes ninguna herramienta ahora. Explicá en una o dos frases qué falta para "
    "cumplir el pedido y cuál sería el paso siguiente, hablando en condicional y sin decir "
    "que ya lo hiciste.]\n\nPedido: "
)

CLAIM_RETRY_NOTE = (
    "[CORRECCIÓN: en el turno anterior dijiste que habías hecho algo pero no llamaste "
    "a ninguna herramienta, así que no se ejecutó nada. Resolvé el pedido de nuevo usando "
    "SOLO las herramientas del catálogo (no inventes nombres): si hay comandos que logran "
    "el resultado o parte de él, llamalos ahora. Recién después explicá lo que falte. Si "
    "no hay ningún comando posible, contestá en condicional y sin decir que ya lo "
    "hiciste.]\n\nPedido: "
)


def _claims_done(answer: str) -> bool:
    """¿La respuesta afirma haber ejecutado algo?"""
    if not answer:
        return False
    return bool(_ACTION_CLAIM.search(router.normalize(answer)))


def _looks_like_action_request(text: str) -> bool:
    """Un pedido de acción, no una consulta: solo ahí vale la verificación."""
    normalized = router.normalize(text or "")
    if "?" in (text or ""):
        return False
    return not normalized.startswith(_QUESTION_STARTS)


def _short_fx_name(name: str) -> str:
    """'VST: FabFilter Pro-Q 4 (FabFilter)' -> 'FabFilter Pro-Q 4'."""
    text = (name or "").strip()
    for prefix in FX_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    match = re.match(r"^(.*?)\s+\([^()]*\)$", text)
    if match:
        text = match.group(1)
    return text.strip() or name


CHOICE_NUMBERS = {
    "uno": 1, "un": 1, "primero": 1, "1": 1,
    "dos": 2, "segundo": 2, "2": 2,
    "tres": 3, "tercero": 3, "3": 3,
    "cuatro": 4, "cuarto": 4, "4": 4,
    "cinco": 5, "quinto": 5, "5": 5,
}


UNIT_WORDS = {
    "db", "bpm", "hz", "khz", "ms", "seg", "segs", "segundos", "segundo",
    "compas", "compases", "grado", "grados", "porciento", "veces",
}


def _choice_number(normalized: str, total: int) -> int | None:
    """Busca 'el 2', 'la opción tres', 'quiero el uno' dentro de la frase.

    Se ignoran los números que son medidas ("2 dB", "120 bpm"): si no, cualquier
    pedido con un valor numérico se tomaría como elección.
    """
    tokens = re.findall(r"[a-z0-9]+", normalized)
    for position, word in enumerate(tokens):
        value = CHOICE_NUMBERS.get(word)
        if value is None or not (1 <= value <= total):
            continue
        following = tokens[position + 1] if position + 1 < len(tokens) else ""
        if following in UNIT_WORDS or following == "%":
            continue
        return value - 1
    return None


TRACK_HINT = re.compile(r"(?:en|a|para|sobre)\s+(?:la\s+|el\s+)?pista\s+(.+)$")


def _track_hint(text: str) -> str:
    """Extrae 'bajo' de '... en la pista de bajo'."""
    match = TRACK_HINT.search(router.normalize(text))
    if not match:
        return ""
    name = re.sub(r"^(de|del|la|el)\s+", "", match.group(1).strip())
    return name.strip(" .,!?")

STATE_PRIORITY = ("error", "confirm", "working", "thinking", "speaking", "listening", "offline", "idle")


class MikyApp:
    """Núcleo sin dependencia de Qt (la UI se engancha por callbacks)."""

    def __init__(self, config: Config, ui_enabled: bool = True) -> None:
        self.config = config
        self.ui_enabled = ui_enabled
        self.install = reaper.find_install(config.reaper.install_path, config.reaper.resource_path)
        self.client = BridgeClient(stale_ms=config.bridge.heartbeat_stale_ms)
        self.catalog = Catalog.load()
        self.provider: AIProvider = build_provider(config.ai)
        self.executor = Executor(
            self.client,
            self.catalog,
            config,
            confirm=self._confirm,
            on_state=self._on_exec_state,
            say=self._say,
        )

        self.tts = self._build_tts()
        self.pipeline: VoicePipeline | None = None
        self.stt_probe = FasterWhisperStt(model_size=config.voice.stt_model, language=config.voice.stt_language)

        self._running = False
        self._monitor_thread: threading.Thread | None = None
        self._status = BridgeStatus()
        self._busy = False
        self._voice_state = "idle"
        self._error_until = 0.0
        self._last_actions: collections.deque[dict[str, Any]] = collections.deque(maxlen=6)
        self._confirm_event: threading.Event | None = None
        self._confirm_answer: bool | None = None
        self._pending_choice: dict[str, Any] | None = None
        self._pending_approx: str = ""
        self._strong = None
        self._history: list[dict[str, Any]] = []
        self._fx_index: dict[str, Any] = {}
        self._notify_hooks: list[Any] = []

    # ---------------------------------------------------------------- arranque

    def bootstrap(self) -> None:
        paths.ensure_runtime_dirs()
        paths.clean_ipc(max_age_seconds=60)
        log.info("Miky %s iniciando", __version__)
        log.info("REAPER: %s", self.install.exe or "no encontrado")
        log.info("recursos: %s", self.install.resource_path or "no encontrados")

        if self.install.found and self.config.reaper.auto_install_bridge:
            ok, message = reaper.ensure_bridge_ready(self.install)
            log.info("puente: %s", message)
            if not ok:
                log.warning("no pude instalar el puente: %s", message)

        if self.config.reaper.auto_launch and not reaper.is_reaper_running():
            log.info("REAPER cerrado y auto_launch activo: lo abro con el puente")
            reaper.launch_reaper(self.install, with_bridge=True)

        if self.config.voice.enabled and not stt_available():
            log.warning("faster-whisper no está instalado: la voz no va a funcionar")

    def start_background(self) -> None:
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="miky-bridge-monitor", daemon=True
        )
        self._monitor_thread.start()
        self.start_voice()

    def start_voice(self) -> None:
        if not self.config.voice.enabled:
            return
        if self.pipeline is not None:
            return
        settings = VoiceSettings.from_config(self.config.voice)
        self.tts.start() if hasattr(self.tts, "start") else None
        # Frases cortas listas para sonar sin esperar síntesis.
        for engine in (getattr(self.tts, "primary", None), self.tts):
            if engine is not None and hasattr(engine, "prewarm"):
                try:
                    engine.prewarm()
                except Exception:  # noqa: BLE001
                    log.debug("no pude precalentar la voz", exc_info=True)
                break
        self.pipeline = VoicePipeline(
            settings,
            on_command=self.handle_text,
            on_state=self._on_voice_state,
            on_transcript=self._on_transcript,
            on_error=self._on_voice_error,
            tts=self.tts,
            # Mientras graba no se lanzan transcripciones especulativas: el CPU
            # es de REAPER.
            allow_speculation=lambda: not bool(self._status.recording),
        )
        try:
            self.pipeline.start()
        except Exception as exc:  # noqa: BLE001
            log.error("no pude iniciar la voz: %s", exc)
            self.pipeline = None

    def stop(self) -> None:
        self._running = False
        self._pending_choice = None
        self._pending_approx = ""
        self.stop_voice()
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=2.0)
            self._monitor_thread = None

    def stop_voice(self) -> None:
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:  # noqa: BLE001
                log.debug("error al detener la voz", exc_info=True)
            self.pipeline = None
        if hasattr(self.tts, "close"):
            try:
                self.tts.close()
            except Exception:  # noqa: BLE001
                log.debug("error al cerrar el TTS", exc_info=True)

    def apply_config(self, config: Config) -> None:
        """Recarga la configuración sin reiniciar la app."""
        self.config = config
        self.executor.config = config
        self.client.stale_ms = config.bridge.heartbeat_stale_ms
        self.provider = build_provider(config.ai)
        self.stop_voice()
        self.tts = self._build_tts()
        if config.voice.enabled:
            self.start_voice()
        log.info(
            "configuración aplicada · IA %s · voz %s",
            self.provider.description,
            config.voice.mode,
        )

    HELP_TEXT = (
        "Puedo crear, renombrar, duplicar y borrar pistas; cargar plugins y cambiar sus parámetros; "
        "armar y grabar; ajustar volumen y paneo; poner marcadores y regiones; cambiar el tempo; "
        "deshacer, guardar y renderizar. Por ejemplo: Miky, creá una pista de guitarra. "
        "O: Miky, subí el bajo dos dB."
    )

    def say_help(self) -> None:
        self._say(self.HELP_TEXT)

    # ---------------------------------------------------------------- núcleo

    def handle_text(self, text: str) -> str:
        """Procesa una orden (voz o consola) y devuelve lo que se dijo."""
        text = (text or "").strip()
        if not text:
            return ""

        # ¿Está respondiendo a una lista de opciones que dio Miky?
        if self._pending_choice is not None:
            resolved = self._resolve_pending_choice(text)
            if resolved is not None:
                return resolved

        # "abrí REAPER" se resuelve en la app, no en el puente.
        if OPEN_REAPER_PATTERN.search(router.normalize(text)):
            return self.open_reaper()

        # Mientras el puente está ocupado (render, grabación larga) no se puede
        # encolar otra orden: se avisa al instante en vez de dejarlo esperando.
        if self._status.busy:
            message = (
                "Estoy ocupado con una tarea larga y no puedo atenderte hasta que termine. "
                "Si es un render, podés cancelarlo en la ventana de REAPER."
            )
            log.info("pedido ignorado: puente ocupado (%s)", text)
            self._say(message)
            return message

        log.info("pedido: %s", text)
        try:
            plan = self._plan_for(text)
        except PlanError as exc:
            message = f"No pude interpretar el pedido: {exc}."
            self._say(message)
            return message
        except AIError as exc:
            self._say(str(exc))
            return str(exc)
        except BridgeError:
            message = "No estoy conectado a REAPER."
            self._say(message)
            return message

        if plan.empty and not plan.question and not plan.answer:
            self._say("No entendí.")
            return "No entendí."

        report = self.executor.execute(plan)
        self._remember(plan, report, text)

        offered = self._offer_choices(report)
        if offered is not None:
            return offered

        if self._should_speak(plan, report):
            self._say(report.speech, speak=True)
        else:
            # Sin voz: un sonido distinto para bien y para mal.
            chime("ok" if report.ok else "error")
            self._say(report.speech, speak=False)
        return report.speech

    def _should_speak(self, plan: Plan, report) -> bool:
        """Decide si el resultado se dice con voz o alcanza con un sonido."""
        mode = (self.config.voice.feedback or "mixto").strip().lower()
        if mode == "voz":
            return True
        # Preguntas y consejos necesitan voz: hay que escucharlos completos.
        if plan.question or plan.answer:
            return True
        if mode == "sonidos":
            return False
        return not report.ok

    # ---------------------------------------------------------------- opciones

    def _offer_choices(self, report) -> str | None:
        """Si REAPER devolvió varias coincidencias, las ofrece y espera elección."""
        data = report.error_data or {}
        if data.get("code") != "fx_candidates":
            return None
        candidates = [str(item) for item in (data.get("candidates") or []) if item][:5]
        if not candidates:
            return None
        step_index = int(data.get("step") or 1) - 1
        if not (0 <= step_index < len(report.plan.steps)):
            return None
        step = report.plan.steps[step_index]
        base = {key: value for key, value in step.args.items() if key != "name"}
        self._pending_choice = {"command": "fx.add", "base_args": base, "options": candidates}

        options_text = "; ".join(
            f"{index + 1}, {_short_fx_name(name)}" for index, name in enumerate(candidates)
        )
        message = f"Encontré {len(candidates)}: {options_text}. ¿Cuál querés?"
        self._say(message)
        if self.pipeline is not None and self.pipeline.running:
            # Queda escuchando para que la respuesta no necesite la palabra clave.
            self.pipeline.trigger()
        return message

    def _resolve_pending_choice(self, text: str) -> str | None:
        pending = self._pending_choice
        if pending is None:
            return None
        options: list[str] = pending["options"]
        normalized = router.normalize(text)

        index: int | None = None

        # 1) número ("el 2", "la opción 3", "dos", "quiero el uno")
        index = _choice_number(normalized, len(options))

        # 2) nombre completo o parte del nombre
        if index is None:
            for position, name in enumerate(options):
                short = router.normalize(_short_fx_name(name))
                if short and (short in normalized or normalized in short):
                    index = position
                    break

        # 3) cancelar
        if index is None:
            cancelled = wake.parse_yes_no(text) is False or any(
                word in normalized for word in ("cancela", "dejalo", "dejala", "nada", "olvidate")
            )
            if cancelled:
                self._pending_choice = None
                message = "Listo, no cargo nada."
                self._say(message)
                return message

        # 4) palabras sueltas que identifiquen una opción ("el del SSL")
        if index is None:
            tokens = [
                token
                for token in re.split(r"[^\wáéíóúñü]+", normalized)
                if token and token not in CHOICE_STOPWORDS and not token.isdigit()
            ]
            best_score = 0
            for position, name in enumerate(options):
                short = router.normalize(_short_fx_name(name))
                score = sum(1 for token in tokens if token in short)
                if score > best_score:
                    best_score = score
                    index = position

        if index is None:
            self._pending_choice = None
            return None

        self._pending_choice = None
        args = dict(pending["base_args"])
        args["name"] = options[index]
        hint = _track_hint(text)
        if hint:
            # "el dos, pero en la pista de bajo": se respeta la pista nueva.
            args["track"] = hint
        try:
            plan = self.executor.build_plan([("fx.add", args)], source="eleccion")
        except PlanError as exc:
            message = f"No pude cargarlo: {exc}"
            self._say(message)
            return message
        report = self.executor.execute(plan)
        self._remember(plan, report, text)
        self._say(report.speech)
        return report.speech

    def _plan_for(self, text: str) -> Plan:
        if self.config.ai.direct_commands:
            hit = router.match(text)
            if hit is not None:
                command, args, rule = hit
                log.info("comando directo: %s (%s)", command, rule)
                return self.executor.build_plan([(command, args)], source=f"directo:{rule}")

        if not self.provider.available():
            raise AIError(NO_KEY_MESSAGE, kind="auth")

        # Primer intento: solo las herramientas de la familia que parece necesitar.
        from . import intent

        families = intent.families_for(text)
        context = self.build_context(families, text)

        command_ids = intent.commands_for_text(text)
        limited = self.catalog.subset(command_ids) if command_ids else self.catalog
        log.info(
            "intención: %s (%d de %d herramientas)",
            ", ".join(families) or "sin clasificar",
            len(limited.all()),
            len(self.catalog.all()),
        )

        result: AIResult = self.provider.interpret(text, context, limited)
        log.info(
            "IA %s devolvió %d pasos (%0.0f ms, %d tokens de entrada)",
            self.provider.description,
            len(result.steps),
            result.latency_ms,
            result.prompt_tokens,
        )

        # Si con el subconjunto no salió nada, se prueba el catálogo completo.
        if limited is not self.catalog and not result.steps and not result.answer and not result.question:
            log.info("el subconjunto no alcanzó; reintento con el catálogo completo")
            result = self.provider.interpret(text, context, self.catalog)

        # El modelo a veces contesta "ya lo hice" sin haber llamado a ninguna
        # herramienta. Se detecta y se le pide una segunda respuesta.
        if (
            not result.steps
            and _looks_like_action_request(text)
            and _claims_done(result.answer)
        ):
            log.warning("la IA afirmó haber hecho algo sin ejecutar comandos; reintento")
            retry = self.provider.interpret(CLAIM_RETRY_NOTE + text, context, self.catalog)
            if retry.steps or not _claims_done(retry.answer):
                result = retry
                log.info(
                    "reintento: %d pasos, respuesta %s",
                    len(retry.steps),
                    "sí" if retry.answer else "no",
                )
            else:
                log.warning("el reintento tampoco ejecutó nada; se pide una explicación")
                explicacion = self.provider.interpret(EXPLAIN_NOTE + text, context, self.catalog)
                if explicacion.answer and not _claims_done(explicacion.answer):
                    result = explicacion
                else:
                    # Última carta: el modelo grande, que a veces resuelve lo
                    # que el rápido no pudo.
                    salvaged = None
                    strong = self._strong_provider()
                    if strong is not None:
                        log.info("pruebo el modelo de respaldo (%s)", strong.description)
                        try:
                            salvaged = strong.interpret(
                                EXPLAIN_NOTE + text, context, self.catalog
                            )
                        except AIError as exc:
                            log.warning("el modelo de respaldo falló: %s", exc)
                    if salvaged is not None and (salvaged.steps or salvaged.answer):
                        result = salvaged
                    else:
                        result = AIResult(
                            answer=(
                                "Eso no lo ejecuté: todavía no tengo un comando que lo haga tal cual. "
                                "Decímelo de otra forma y lo intento."
                            ),
                            provider=result.provider,
                            model=result.model,
                            latency_ms=result.latency_ms + retry.latency_ms,
                        )

        # Último recurso: el modelo chico no devolvió nada útil. Se prueba el
        # modelo grande una sola vez (si está configurado).
        if (
            not result.steps
            and not result.answer
            and not result.question
            and len(text.split()) >= 3
        ):
            strong = self._strong_provider()
            if strong is not None:
                log.info("el modelo rápido no respondió nada; pruebo %s", strong.description)
                try:
                    result = strong.interpret(text, context, self.catalog)
                except AIError as exc:
                    log.warning("el modelo de respaldo falló: %s", exc)

        if result.answer and not result.steps:
            return Plan(answer=result.answer, source="ia")
        if result.question and not result.steps:
            return Plan(question=result.question, source="ia")
        return self.executor.build_plan(
            result.steps, source="ia", question=result.question, answer=result.answer
        )

    def _strong_provider(self):
        """Proveedor de respaldo (modelo más grande), creado una sola vez."""
        name = (self.config.ai.model_strong or "").strip()
        if not name or name == self.config.ai.model:
            return None
        if self._strong is None:
            try:
                from dataclasses import replace

                from .ai import build_provider

                self._strong = build_provider(replace(self.config.ai, model=name))
            except Exception as exc:  # noqa: BLE001
                log.warning("no pude crear el modelo de respaldo: %s", exc)
                self._strong = None
        return self._strong

    def build_context(self, families: tuple[str, ...] | None = None, text: str = "") -> dict[str, Any]:
        context: dict[str, Any] = {
            "assistant": {"name": "Miky", "version": __version__},
            "render_defaults": {
                "dir": self.config.render.default_dir or str(paths.default_render_dir()),
                "pattern": self.config.render.default_pattern,
            },
        }
        # Consulta de criterio: se inyectan fichas técnicas con números reales.
        if text and knowledge.is_advice_request(text):
            cards = knowledge.relevant(text, limit=2)
            if cards:
                context["knowledge"] = knowledge.as_context(cards)
                log.debug("fichas técnicas: %s", ", ".join(card.id for card in cards))
        # Solo si el pedido habla de plugins se manda la lista real (recortada).
        if families is None or "fx" in families:
            index = self._fx_index
            if index and index.get("names"):
                context["fx_installed"] = {
                    "count": index["count"],
                    "vendors": index["vendors"][:40],
                    "names": index["names"][:120],
                    "truncated": index["count"] > 120,
                }
                if index.get("favorites"):
                    context["fx_favorites"] = index["favorites"][:30]
        try:
            reply = self.client.call_one("state.get", timeout=3.0)
            if reply.ok and reply.first is not None:
                state = dict(reply.first.result)
                tracks = state.get("tracks")
                if isinstance(tracks, list):
                    keep = (
                        "index",
                        "name",
                        "volume_db",
                        "pan",
                        "mute",
                        "solo",
                        "armed",
                        "selected",
                        "fx_count",
                        "color",
                    )
                    state["tracks"] = [
                        {key: track[key] for key in keep if key in track} for track in tracks
                    ]
                context.update(state)
                # Los nombres de las pistas sesgan el reconocimiento de voz:
                # "guitarra", "batería", "bombo" se transcriben bien.
                tracks = state.get("tracks")
                if isinstance(tracks, list) and self.pipeline is not None:
                    names = [str(track.get("name")) for track in tracks if track.get("name")]
                    # Se suman las palabras propias (marcas de plugins, etc.).
                    names.extend(word for word in self.config.voice.vocabulary if word)
                    if names:
                        self.pipeline.set_hotwords(names)
                # Para consejos, se leen los parámetros reales de los plugins:
                # así opina sobre SU sesión y no sobre un caso genérico.
                if text and knowledge.is_advice_request(text):
                    settings = self._session_fx_settings(tracks)
                    if settings:
                        context["fx_settings"] = settings
                    levels = self._session_levels()
                    if levels:
                        context["levels"] = levels
        except BridgeError as exc:
            log.debug("sin estado del proyecto: %s", exc)
        context["last_actions"] = list(self._last_actions)
        # Últimos intercambios, para que "y a esa ponele un compresor" tenga sentido.
        context["history"] = list(self._history[-6:])
        return context

    def _remember(self, plan: Plan, report, request: str = "") -> None:
        for index, step in enumerate(plan.steps):
            outcome = report.outcomes[index] if index < len(report.outcomes) else None
            entry: dict[str, Any] = {"command": step.command, "args": step.args, "ok": bool(outcome and outcome.ok)}
            if outcome is not None and outcome.ok:
                entry["result"] = {
                    key: value
                    for key, value in (outcome.result or {}).items()
                    if not isinstance(value, (list, dict))
                }
            self._last_actions.append(entry)
        self._remember_exchange(request, report)

    def _remember_exchange(self, request: str, report) -> None:
        """Guarda el ida y vuelta para que la IA tenga contexto conversacional."""
        try:
            score = "ok" if getattr(report, "ok", False) else "error"
            self._history.append(
                {
                    "pedido": (request or "")[:160],
                    "miky": (getattr(report, "speech", "") or "")[:180],
                    "resultado": score,
                }
            )
            del self._history[:-6]
        except Exception:  # noqa: BLE001
            pass

    # ---------------------------------------------------------------- voz

    def _say(self, text: str, speak: bool = True) -> None:
        text = (text or "").strip()
        if not text:
            return
        log.info("Miky: %s", text)
        self._notify(text)
        if speak and self.config.voice.speak_replies:
            try:
                self.tts.speak(text)
            except Exception:  # noqa: BLE001
                log.debug("no pude hablar", exc_info=True)

    def _build_tts(self):
        if not self.config.voice.enabled or not self.config.voice.speak_replies:
            return NullTts()

        sapi = SapiTts(
            voice_hint=self.config.voice.tts_voice,
            rate=self.config.voice.tts_rate,
            output_hint=self.config.voice.output_device,
        )
        sapi.start()
        if not sapi.available:
            log.warning("SAPI no disponible: %s", sapi.error)
            sapi = None

        edge = None
        if self.config.voice.tts_engine in ("edge", "auto"):
            edge = EdgeTts(
                voice=self.config.voice.edge_voice,
                rate=self.config.voice.tts_rate,
                output_device=self.config.voice.output_device,
            )
            if sapi is not None:
                edge.fallback = sapi.speak
            edge.start()
            if not edge.available:
                log.warning("voz online no disponible: %s", edge.error)
                edge = None

        if edge is not None:
            log.info("voz: online (%s)", edge.voice_name)
            return TtsManager(edge, sapi) if sapi is not None else edge
        if sapi is not None:
            log.info("voz: local (%s)", sapi.voice_name)
            return sapi
        return NullTts()

    def _on_voice_state(self, state: str) -> None:
        self._voice_state = state
        if state == "error":
            self._error_until = time.monotonic() + 3.0

    def _on_transcript(self, text: str, activated: bool) -> None:
        log.debug("transcripción (%s): %s", "activado" if activated else "descartado", text)

    def _on_voice_error(self, message: str) -> None:
        log.warning("error de voz: %s", message)
        self._notify(message)

    def _on_exec_state(self, state: str) -> None:
        if state in ("working",):
            self._busy = True
        elif state in ("idle", "error"):
            self._busy = False
            if state == "error":
                self._error_until = time.monotonic() + 2.5

    # ---------------------------------------------------------------- confirmación

    def _confirm(self, question: str, step) -> bool:
        """Pregunta y espera. La voz y los botones compiten por la misma respuesta."""
        log.info("confirmación requerida: %s", question)
        self._confirm_answer = None
        self._confirm_event = threading.Event()
        self._request_confirmation(question)

        pipeline = self.pipeline
        timeout = self.config.voice.confirm_timeout_s
        try:
            # Si ya tocaron un botón mientras se mostraba el aviso, no se espera.
            if self._confirm_answer is not None:
                return bool(self._confirm_answer)

            if pipeline is not None and pipeline.running:
                # Se espera en este mismo hilo: el pipeline es quien recibe el
                # texto del micrófono y libera la espera.
                answer = pipeline.expect_confirmation("", timeout=timeout)
                # Si mientras tanto tocaron un botón, gana el botón.
                if self._confirm_answer is not None:
                    answer = bool(self._confirm_answer)
                log.info("confirmación por voz: %s", "sí" if answer else "no")
                return answer

            answered = self._confirm_event.wait(timeout=timeout)
            return bool(self._confirm_answer) if answered else False
        finally:
            self._close_confirmation()
            self._confirm_event = None

    def respond_confirmation(self, value: bool) -> None:
        if self._confirm_event is None:
            return
        self._confirm_answer = value
        self._confirm_event.set()
        # Si la respuesta vino de un botón, se libera también la espera del
        # pipeline para que no siga escuchando.
        if self.pipeline is not None:
            self.pipeline.answer_confirmation(value)

    # Enganches que la UI reemplaza ------------------------------------------------

    def _request_confirmation(self, question: str) -> None:
        self._say(question, speak=True)

    def _close_confirmation(self) -> None:
        pass

    def _notify(self, text: str) -> None:
        for hook in self._notify_hooks:
            try:
                hook(text)
            except Exception:  # noqa: BLE001
                pass

    def add_notify_hook(self, hook) -> None:
        self._notify_hooks.append(hook)

    # ---------------------------------------------------------------- monitor

    def _monitor_loop(self) -> None:
        refreshed = False
        while self._running:
            try:
                status = self.client.read_status(
                    render_timeout_s=self.config.bridge.render_timeout_ms / 1000.0
                )
                if status.alive != self._status.alive or status.project != self._status.project:
                    log.info("puente: %s", status.summary)
                self._status = status
                # Al conectar, se indexan los plugins instalados una sola vez.
                if status.alive and not refreshed:
                    refreshed = True
                    self._refresh_fx_index()
                elif not status.alive:
                    refreshed = False
            except Exception:  # noqa: BLE001
                log.debug("fallo el monitor del puente", exc_info=True)
            time.sleep(0.9)

    def _refresh_fx_index(self) -> None:
        """Pide a REAPER la lista de plugins instalados y la deja en memoria."""
        try:
            reply = self.client.call_one("fx.installed", {"limit": 0}, timeout=6.0)
        except Exception as exc:  # noqa: BLE001
            log.debug("no pude indexar los plugins: %s", exc)
            return
        if not reply.ok or reply.first is None:
            return
        data = dict(reply.first.result or {})
        names = [str(name) for name in (data.get("names") or []) if name]
        vendors = [str(vendor) for vendor in (data.get("vendors") or []) if vendor]
        favorites = [str(name) for name in (data.get("favorites") or []) if name]
        missing = [str(name) for name in (data.get("missing_favorites") or []) if name]
        self._fx_index = {
            "count": int(data.get("count") or len(names)),
            "names": names,
            "vendors": vendors,
            "favorites": favorites,
        }
        log.info(
            "plugins instalados: %d · favoritos: %d%s",
            self._fx_index["count"],
            len(favorites),
            (" (" + ", ".join(favorites[:3]) + ")") if favorites else "",
        )
        if missing:
            log.warning(
                "favoritos marcados que ya no están instalados: %s", ", ".join(missing[:5])
            )

    def _session_fx_settings(self, tracks: Any, max_tracks: int = 2) -> list[dict[str, Any]]:
        """Lee los parámetros reales de los plugins cargados en la sesión.

        Solo se piden para consultas de criterio: es información valiosa para
        aconsejar («tu compresor tiene ratio 8:1») pero no hace falta para
        ejecutar una orden.
        """
        if not isinstance(tracks, list):
            return []
        candidates: list[dict[str, Any]] = []
        for track in tracks:
            if not isinstance(track, dict):
                continue
            count = int(track.get("fx_count") or 0)
            if count <= 0 or not track.get("name"):
                continue
            candidates.append(track)
        if not candidates:
            return []
        # Primero las pistas seleccionadas, después las primeras con plugins.
        candidates.sort(key=lambda t: 0 if t.get("selected") else 1)
        settings: list[dict[str, Any]] = []
        for track in candidates[:max_tracks]:
            try:
                reply = self.client.call_one(
                    "fx.params", {"track": track["name"], "limit": 10}, timeout=3.0
                )
            except Exception:  # noqa: BLE001
                continue
            if not reply.ok or reply.first is None:
                continue
            data = dict(reply.first.result or {})
            plugins = []
            for plugin in (data.get("plugins") or [])[:2]:
                params = {}
                for param in (plugin.get("params") or [])[:10]:
                    name = str(param.get("name") or "").strip()
                    if name:
                        params[name] = str(param.get("value") or "")
                plugins.append(
                    {
                        "nombre": plugin.get("name"),
                        "preset": plugin.get("preset") or "",
                        "parametros": params,
                    }
                )
            if plugins:
                settings.append({"pista": data.get("track_name") or track["name"], "plugins": plugins})
        return settings

    def _session_levels(self, samples: int = 3, spacing: float = 0.08) -> dict[str, Any] | None:
        """Mide los niveles del medidor durante un instante y devuelve el máximo.

        Solo tiene sentido con el transporte andando: parado, el medidor baja a
        cero y cualquier conclusión sería falsa.
        """
        best: dict[str, Any] | None = None
        for sample in range(max(1, samples)):
            try:
                reply = self.client.call_one("levels.get", {}, timeout=3.0)
            except Exception:  # noqa: BLE001
                break
            if not reply.ok or reply.first is None:
                break
            data = dict(reply.first.result or {})
            if not data.get("playing") and not data.get("recording"):
                return None
            master = data.get("master") or {}
            peaks: dict[str, float] = {}
            if isinstance(master.get("peak_db"), (int, float)):
                peaks["master"] = float(master["peak_db"])
            for track in data.get("tracks") or []:
                value = track.get("peak_db")
                name = str(track.get("name") or "")
                if name and isinstance(value, (int, float)):
                    peaks[name] = max(peaks.get(name, float("-inf")), float(value))
            if sample == 0:
                best = {"reproduciendo": True, "picos": dict(peaks)}
            elif best is not None:
                for name, value in peaks.items():
                    best["picos"][name] = max(best["picos"].get(name, float("-inf")), value)
            if spacing:
                time.sleep(spacing)
        if not best or not best.get("picos"):
            return None
        # Redondeo para que el contexto sea legible y barato; se descarta el
        # silencio absoluto (el medidor lo marca como -120).
        picos: dict[str, float] = {}
        for name, value in best["picos"].items():
            number = float(value)
            if number > -119.0:
                picos[name] = round(number, 1)
        if not picos:
            return None
        best["picos"] = picos
        return best

    @property
    def status(self) -> BridgeStatus:
        return self._status

    def compute_state(self) -> str:
        if time.monotonic() < self._error_until:
            return "error"
        if self._confirm_event is not None:
            return "confirm"
        if self._busy:
            return "working"
        if self._voice_state in ("thinking", "listening"):
            return self._voice_state
        try:
            if self.tts.is_speaking:
                return "speaking"
        except Exception:  # noqa: BLE001
            pass
        if not self._status.alive:
            return "offline"
        return "idle"

    def tooltip(self) -> str:
        from .ui import theme

        lines = [f"Miky · {theme.STATE_LABELS.get(self.compute_state(), '')}"]
        if self._status.alive:
            lines.append(self._status.summary)
        else:
            lines.append("REAPER desconectado")
        if self.pipeline is not None and self.pipeline.last_transcript:
            lines.append(f"«{self.pipeline.last_transcript}»")
        return "\n".join(lines)

    # ---------------------------------------------------------------- acciones de UI

    def trigger_listen(self) -> None:
        if self.pipeline is not None and self.pipeline.running:
            self.pipeline.trigger()
            self._say("Te escucho.", speak=False)
        else:
            self._say("La voz está desactivada.", speak=False)

    def stop_speaking(self) -> None:
        try:
            self.tts.stop()
        except Exception:  # noqa: BLE001
            pass

    def open_reaper(self) -> str:
        ok, message = reaper.ensure_bridge_ready(self.install)
        if not ok:
            self._say(message)
            return message
        if reaper.is_reaper_running():
            message = "REAPER ya está abierto. Si no me responde, cerralo y abrilo desde acá."
            self._say(message)
            return message
        launched = reaper.launch_reaper(self.install, with_bridge=True)
        message = "Abriendo REAPER." if launched else "No pude abrir REAPER."
        self._say(message)
        return message

    def reinstall_bridge(self) -> None:
        ok, message = reaper.install_bridge(self.install)
        self._say(message if ok else f"Falló: {message}")
