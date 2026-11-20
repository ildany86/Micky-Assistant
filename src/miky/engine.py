"""Ejecución de planes: validación, confirmaciones, envío al puente y respuesta.

Un "plan" es una lista ordenada de comandos del catálogo. Llega desde la IA
(como llamadas a herramientas) o desde el router de comandos directos. Acá se
valida entero antes de tocar REAPER: si un paso está mal, no se ejecuta nada.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from . import log as log_mod, paths, speech
from .bridge import BridgeClient, BridgeError, BridgeReply, BridgeTimeout, StepOutcome
from .catalog import Catalog, CommandSpec, ValidationError
from .config import Config

log = log_mod.get("miky.engine")

ConfirmCallback = Callable[[str, "Step"], bool]
StateCallback = Callable[[str], None]
SayCallback = Callable[[str], None]

CONFIRM_QUESTIONS = {
    "track.delete": "¿Borro la pista {track}?",
    "render.start": "¿Arranco el render?",
    "project.save_as": "¿Guardo el proyecto en esa ruta?",
}

# Para varios pasos iguales: una sola pregunta, en plural.
CONFIRM_PLURALS = {
    "track.delete": "¿Borro {n} pistas?",
    "item.delete_selected": "¿Borro lo seleccionado?",
}

# Antes de grabar se pregunta: así la voz de Miky no entra en la toma.
RECORD_QUESTION = "¿Estás listo para grabar?"


@dataclass
class Step:
    command: str
    args: dict[str, Any]
    spec: CommandSpec

    @property
    def label(self) -> str:
        return self.spec.summary.rstrip(".")


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)
    question: str = ""
    answer: str = ""
    note: str = ""
    source: str = "ai"

    @property
    def empty(self) -> bool:
        return not self.steps

    @property
    def needs_confirmation(self) -> bool:
        return any(step.spec.danger for step in self.steps)


@dataclass
class ExecutionReport:
    ok: bool
    speech: str
    plan: Plan
    outcomes: list[StepOutcome] = field(default_factory=list)
    error: str = ""
    error_data: dict[str, Any] | None = None
    duration_ms: float = 0.0
    executed: int = 0

    @property
    def failed_step(self) -> StepOutcome | None:
        for outcome in self.outcomes:
            if not outcome.ok:
                return outcome
        return None


class PlanError(ValueError):
    pass


class Executor:
    def __init__(
        self,
        client: BridgeClient,
        catalog: Catalog,
        config: Config,
        confirm: ConfirmCallback | None = None,
        on_state: StateCallback | None = None,
        say: SayCallback | None = None,
    ) -> None:
        self.client = client
        self.catalog = catalog
        self.config = config
        self.confirm = confirm
        self.on_state = on_state
        self.say = say

    # ---------------------------------------------------------------- planes

    def build_plan(
        self,
        raw_steps: Sequence[tuple[str, dict[str, Any]] | tuple[str, dict[str, Any], str]],
        source: str = "ai",
        question: str = "",
        note: str = "",
        answer: str = "",
    ) -> Plan:
        specs: list[Step] = []
        errors: list[str] = []

        for raw in raw_steps:
            command = raw[0]
            args = raw[1] if len(raw) > 1 else {}
            spec = self.catalog.get(command)
            if spec is None:
                errors.append(f"«{command}» no es un comando del catálogo")
                continue
            try:
                clean = self.catalog.validate(command, args)
                clean = self._apply_defaults(spec, clean)
            except (ValidationError, PlanError) as exc:
                errors.append(str(exc))
                continue
            specs.append(Step(command=command, args=clean, spec=spec))

        if errors:
            raise PlanError("; ".join(errors))
        if not specs and not question and not answer:
            raise PlanError("el plan quedó vacío")
        if len(specs) > self.config.ai.max_steps:
            raise PlanError(
                f"el plan tiene {len(specs)} pasos y el máximo es {self.config.ai.max_steps}"
            )
        specs = _order_deletes(specs)
        return Plan(steps=specs, question=question, answer=answer, note=note, source=source)

    def _apply_defaults(self, spec: CommandSpec, args: dict[str, Any]) -> dict[str, Any]:
        if spec.id == "render.start":
            args = self._prepare_render(args)
        return args

    def _prepare_render(self, args: dict[str, Any]) -> dict[str, Any]:
        out_dir = str(args.get("out_dir") or "").strip()
        if not out_dir:
            configured = self.config.render.default_dir.strip()
            out_dir = configured or str(paths.default_render_dir())
        target = Path(out_dir).expanduser()
        if not target.is_absolute():
            target = Path.home() / target
        roots = self.config.safety.allowed_render_roots
        if roots:
            allowed = [Path(root).expanduser().resolve() for root in roots]
            resolved = target.resolve()
            if not any(resolved == root or root in resolved.parents for root in allowed):
                raise PlanError(
                    f"la carpeta de render {target} no está dentro de las carpetas permitidas"
                )
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PlanError(f"no pude crear la carpeta de render {target}: {exc}") from exc

        args = dict(args)
        args["out_dir"] = str(target)
        if not str(args.get("pattern") or "").strip():
            args["pattern"] = self.config.render.default_pattern or "$project"
        return args

    # ---------------------------------------------------------------- ejecución

    def execute(self, plan: Plan) -> ExecutionReport:
        started = time.monotonic()
        if plan.answer and not plan.steps:
            # Solo una respuesta hablada: no se toca REAPER.
            return ExecutionReport(ok=True, speech=plan.answer, plan=plan, duration_ms=0.0)
        if plan.question:
            return ExecutionReport(ok=True, speech=plan.question, plan=plan, duration_ms=0.0)
        if plan.empty:
            return ExecutionReport(ok=False, speech="No entendí qué hacer.", plan=plan, error="plan vacío")

        record_index = self._record_index(plan)
        if record_index is not None and self._should_gate_record():
            return self._execute_with_record_gate(plan, record_index, started)

        return self._execute_steps(plan, plan.steps, started)

    def _record_index(self, plan: Plan) -> int | None:
        for index, step in enumerate(plan.steps):
            if step.command == "transport.record":
                return index
        return None

    def _should_gate_record(self) -> bool:
        if self.confirm is None:
            return False
        return bool(getattr(self.config.safety, "ask_before_record", True))

    def _execute_with_record_gate(
        self, plan: Plan, record_index: int, started: float
    ) -> ExecutionReport:
        """Ejecuta lo previo, pregunta si está listo y recién ahí graba.

        La respuesta positiva arranca la grabación en silencio (para que la voz
        de Miky no quede dentro de la toma). Una negativa cancela todo.
        """
        prefix = plan.steps[:record_index]
        record_step = plan.steps[record_index]

        if prefix:
            prefix_report = self._execute_steps(
                Plan(steps=prefix, source=plan.source), prefix, time.monotonic()
            )
            if not prefix_report.ok:
                return prefix_report
            if prefix_report.speech and self.say is not None:
                self.say(prefix_report.speech)

        self._emit_state("confirm")
        if not self.confirm(RECORD_QUESTION, record_step):
            self._emit_state("idle")
            return ExecutionReport(
                ok=False,
                speech="Cancelado. No grabé nada.",
                plan=plan,
                error="grabación cancelada por el usuario",
                duration_ms=(time.monotonic() - started) * 1000.0,
            )

        report = self._execute_steps(
            Plan(steps=[record_step], source=plan.source), [record_step], time.monotonic(), silent=True
        )
        report.plan = plan
        report.duration_ms = (time.monotonic() - started) * 1000.0
        if report.ok:
            # Nada de voz: la grabación ya está corriendo.
            report.speech = ""
        return report

    def _execute_steps(
        self,
        plan: Plan,
        steps: Sequence[Step],
        started: float,
        silent: bool = False,
    ) -> ExecutionReport:

        # 1. Confirmaciones (antes de tocar nada). Se agrupan por comando: borrar
        # seis pistas se pregunta una sola vez, no seis.
        if self.config.safety.confirm_destructive and self.confirm is not None:
            groups: list[tuple[CommandSpec, list[Step]]] = []
            for step in steps:
                if not step.spec.danger:
                    continue
                for spec, items in groups:
                    if spec.id == step.spec.id:
                        items.append(step)
                        break
                else:
                    groups.append((step.spec, [step]))
            for spec, items in groups:
                question = self._confirm_question(items[0], count=len(items))
                if not self.confirm(question, items[0]):
                    self._emit_state("idle")
                    return ExecutionReport(
                        ok=False,
                        speech="Cancelado.",
                        plan=plan,
                        error="cancelado por el usuario",
                        duration_ms=(time.monotonic() - started) * 1000.0,
                    )

        # 2. Envío al puente.
        for step in steps:
            if step.spec.pre_speech and self.say is not None and not silent:
                self.say(step.spec.pre_speech)
        self._emit_state("working")
        try:
            reply = self.client.call(
                [(step.command, step.args) for step in steps],
                timeout=self._timeout_for(plan, steps),
            )
        except BridgeTimeout as exc:
            self._emit_state("error")
            return ExecutionReport(
                ok=False,
                speech="REAPER no respondió a tiempo.",
                plan=plan,
                error=str(exc),
                duration_ms=(time.monotonic() - started) * 1000.0,
            )
        except BridgeError as exc:
            self._emit_state("error")
            return ExecutionReport(
                ok=False,
                speech=(
                    "REAPER no está abierto. Abrilo desde el menú del ícono "
                    "o decime: Miky, abrí REAPER."
                ),
                plan=plan,
                error=str(exc),
                duration_ms=(time.monotonic() - started) * 1000.0,
            )

        report = self._report_from_reply(plan, reply, steps)
        report.duration_ms = (time.monotonic() - started) * 1000.0
        if silent:
            report.speech = ""
        elif plan.answer and steps is not None and len(steps) == len(plan.steps):
            # La IA puede ejecutar y además explicar (por ejemplo: lo hice así,
            # pero esto otro necesita un bus de monitoreo).
            report.speech = f"{report.speech} {plan.answer}".strip()
        self._emit_state("idle" if report.ok else "error")
        log.info(
            "plan %s: %s (%.0f ms)",
            plan.source,
            "ok" if report.ok else f"error: {report.error}",
            report.duration_ms,
        )
        return report

    def _report_from_reply(
        self, plan: Plan, reply: BridgeReply, steps: Sequence[Step] | None = None
    ) -> ExecutionReport:
        specs_by_index = list(steps) if steps is not None else plan.steps
        outcomes: list[StepOutcome] = []

        for index, outcome in enumerate(reply.steps):
            if index < len(specs_by_index):
                outcome.command = outcome.command or specs_by_index[index].command
            outcomes.append(outcome)

        ok_count = sum(1 for outcome in outcomes if outcome.ok)
        report = ExecutionReport(
            ok=reply.ok and ok_count == len(plan.steps),
            speech="",
            plan=plan,
            outcomes=outcomes,
            executed=ok_count,
        )

        if report.ok:
            pairs = []
            for index, outcome in enumerate(outcomes):
                spec = specs_by_index[index].spec if index < len(specs_by_index) else None
                if spec is not None and outcome.ok:
                    pairs.append((spec, outcome.result))
            report.speech = speech.describe_plan(pairs)
            return report

        failed = next((outcome for outcome in outcomes if not outcome.ok), None)
        failed_index = outcomes.index(failed) if failed is not None else -1
        failed_spec = (
            specs_by_index[failed_index].spec
            if 0 <= failed_index < len(specs_by_index)
            else None
        )
        message = reply.error_message or (failed.message if failed else "error desconocido")
        report.error = message
        report.error_data = (failed.error if failed else None) or reply.error

        prefix = ""
        if ok_count:
            done = speech.describe_plan(
                [
                    (specs_by_index[i].spec, outcome.result)
                    for i, outcome in enumerate(outcomes)
                    if outcome.ok and i < len(specs_by_index)
                ]
            )
            # "Hice parte: Listo, borré 2 pistas." suena mal: se limpia el prefijo.
            for lead in ("Listo, ", "Listo: ", "Listo. "):
                if done.startswith(lead):
                    done = done[len(lead) :]
                    break
            done = done.rstrip(".")
            prefix = f"Hice parte: {done}. "
        report.speech = prefix + speech.describe_failure(failed_spec, message)
        return report

    def _confirm_question(self, step: Step, count: int = 1) -> str:
        if count > 1:
            plural = CONFIRM_PLURALS.get(step.command)
            if plural:
                return plural.format(n=count)
        template = CONFIRM_QUESTIONS.get(step.command)
        if not template:
            return f"¿Confirmás {step.label.lower()}?"
        try:
            return template.format_map(_SafeFormat(step.args))
        except (KeyError, ValueError):
            return f"¿Confirmás {step.label.lower()}?"

    def _timeout_for(self, plan: Plan, steps: Sequence[Step] | None = None) -> float:
        timeout = 5.0
        for step in steps if steps is not None else plan.steps:
            timeout = max(timeout, self.config.timeout_for(step.command))
        return timeout

    def _emit_state(self, state: str) -> None:
        if self.on_state is not None:
            try:
                self.on_state(state)
            except Exception:  # noqa: BLE001 - la UI nunca debe romper el motor
                log.debug("on_state falló", exc_info=True)


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:  # noqa: D105
        return ""


def _index_of(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _order_deletes(steps: list[Step]) -> list[Step]:
    """Borra pistas por índice de mayor a menor.

    Si la IA manda `track.delete 1` y después `track.delete 2`, al ejecutar el
    primero la pista 2 pasa a ser la 1 y el segundo borrado apunta a otra pista
    (o falla porque ya no existe). Ordenar descendente evita las dos cosas.
    Se conservan las posiciones del resto de los pasos.
    """
    slots = [
        index
        for index, step in enumerate(steps)
        if step.command == "track.delete" and _index_of(step.args.get("track")) is not None
    ]
    if len(slots) < 2:
        return steps
    ordered = sorted(
        (steps[index] for index in slots),
        key=lambda step: _index_of(step.args.get("track")) or 0,
        reverse=True,
    )
    result = list(steps)
    for slot, step in zip(slots, ordered):
        result[slot] = step
    return result


def quick_run(
    client: BridgeClient,
    catalog: Catalog,
    command: str,
    args: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> BridgeReply:
    """Atajo para CLI/doctor: manda un comando suelto sin pasar por la IA."""
    spec = catalog.get(command)
    if spec is None:
        raise PlanError(f"comando desconocido: {command}")
    clean = catalog.validate(command, args or {})
    return client.call([(command, clean)], timeout=timeout)
