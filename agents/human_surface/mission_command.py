"""Thin launch port from a confirmed mission draft to the existing Constructor runtime.

Does not contain Constructor business logic. Does not write product tables.
A launch happens only when this function is called.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from agents.human_surface.mission_draft import (
    CONSTRUCTOR_AGENT_CODE,
    MissionDraft,
    WorkingContext,
    mission_from_context,
)
from agents.human_surface.work_context import WorkContextCatalog


_FIELD_RU = {
    "project": "проект",
    "planning_month": "месяц",
    "queue": "очередь",
    "titles": "титулы",
    "discipline": "дисциплина",
    "systems": "системы",
}

_LAUNCH_LOCK = threading.Lock()
_LAUNCHES: dict[str, "MissionLaunchResult"] = {}
_IN_FLIGHT: set[str] = set()
_RETAINED: list[object] = []
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class MissionCommandError(ValueError):
    """The draft is not ready to launch. Nothing was started."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class MissionLaunchResult:
    run_id: str
    mission_id: str
    status: str
    started_at: str


def mission_gaps(context: WorkingContext) -> tuple[str, ...]:
    from agents.human_surface.workforce import contour_by_code, employee_by_code

    draft = mission_from_context(context, context.intent or "")
    gaps: list[str] = []
    contour = contour_by_code(context.contour_code)
    if contour is None or not contour.connected:
        gaps.append("подключённый профессиональный контур")
    employee = employee_by_code(context.agent_code)
    if (
        employee is None
        or not employee.connected
        or context.agent_code != CONSTRUCTOR_AGENT_CODE
    ):
        gaps.append("подключённый цифровой сотрудник")
    if not str(context.intent or "").strip():
        gaps.append("поручение")
    for name in draft.unresolved_fields:
        label = _FIELD_RU.get(name, name)
        if label not in gaps:
            gaps.append(label)
    return tuple(gaps)


def mission_idempotency_key(context: WorkingContext) -> str:
    payload = "|".join(
        (
            str(context.agent_code or ""),
            str(context.project or ""),
            str(context.planning_month or ""),
            str(context.queue or ""),
            ",".join(context.titles),
            str(context.discipline or ""),
            ",".join(context.systems),
            str(context.packages or ""),
            str(context.intent or ""),
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"hs-{digest}"


def formal_mission(context: WorkingContext) -> MissionDraft:
    return mission_from_context(context, context.intent or "")


def mission_preview_lines(context: WorkingContext) -> tuple[str, ...]:
    from agents.human_surface.workforce import contour_title, employee_title

    return (
        f"Цифровой сотрудник: {employee_title(context.agent_code)}",
        f"Контур: {contour_title(context.contour_code)}",
        f"Проект: {context.project or '—'}",
        f"Месяц: {context.planning_month or '—'}",
        f"Очередь: {context.queue or 'Все очереди'}",
        f"Титулы: {', '.join(context.titles) if context.titles else 'Все титулы'}",
        f"Дисциплина: {context.discipline or 'Все дисциплины'}",
        f"Системы: {', '.join(context.systems) if context.systems else 'Все системы'}",
        f"Пакеты: {context.packages or 'Все пакеты'}",
        f"Поручение: {context.intent or '—'}",
    )


def launch_status_label(status: str) -> str:
    from agents.control_room.presentation import operational_status_ru

    label = operational_status_ru(status)
    if not label or label == str(status or "").strip():
        return "Запущена"
    return label


def different_mission_state(
    current_identity: str,
    launched_identity: Optional[str],
    shown_run_id: Optional[str],
    active_run_id: Optional[str],
) -> bool:
    """True only when the shown run is not the unchanged mission that was launched."""
    if launched_identity and current_identity == launched_identity:
        return bool(active_run_id and shown_run_id and shown_run_id != active_run_id)
    if launched_identity and current_identity != launched_identity:
        return True
    return bool(shown_run_id)


def active_result_run_id(stored: object) -> Optional[str]:
    """The run this workspace may show. A blank value does not fall back to an older run."""
    text = str(stored or "").strip()
    if not text or text.lower() == "none":
        return None
    return text


def reset_launch_memory_for_tests() -> None:
    with _LAUNCH_LOCK:
        _LAUNCHES.clear()
        _IN_FLIGHT.clear()


def launch_monthly_plan_mission(
    context: WorkingContext,
    catalog: WorkContextCatalog,
    *,
    starter: Optional[Callable[..., MissionLaunchResult]] = None,
) -> MissionLaunchResult:
    """Start one Constructor run. A repeated key returns the same result."""
    gaps = mission_gaps(context)
    if gaps:
        raise MissionCommandError("Чтобы запустить задачу, не хватает: " + ", ".join(gaps) + ".")
    if context.agent_code != CONSTRUCTOR_AGENT_CODE:
        raise MissionCommandError("Запуск доступен только для инженера формирования месячного плана.")
    project_code = _project_code(catalog, context.project or "")
    if not project_code:
        raise MissionCommandError("Для выбранного проекта нет authoritative project_code.")
    key = mission_idempotency_key(context)
    with _LAUNCH_LOCK:
        cached = _LAUNCHES.get(key)
        if cached is not None:
            return cached
        if key in _IN_FLIGHT:
            raise MissionCommandError("Запуск этой задачи уже выполняется.")
        _IN_FLIGHT.add(key)
    try:
        start_input = _constructor_start_input(context, catalog, project_code, key)
        launch = starter or _start_with_existing_runtime
        result = launch(start_input)
        if not isinstance(result, MissionLaunchResult) or not str(result.run_id or "").strip():
            raise MissionCommandError("Запуск не вернул run_id.")
        with _LAUNCH_LOCK:
            existing = _LAUNCHES.get(key)
            if existing is not None:
                return existing
            _LAUNCHES[key] = result
        return result
    except MissionCommandError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MissionCommandError("Запуск задачи не выполнен.") from exc
    finally:
        with _LAUNCH_LOCK:
            _IN_FLIGHT.discard(key)


def _project_code(catalog: WorkContextCatalog, label: str) -> str:
    codes = {
        item.project_code
        for item in catalog.facts
        if item.project_label == label and item.project_code
    }
    if len(codes) == 1:
        return next(iter(codes))
    return ""


def _stored_month_key(display: str) -> str:
    return " ".join(str(display or "").split()).replace(" ", "-")


def _catalog_facilities(catalog: WorkContextCatalog, project_label: str, queue: str) -> list[str]:
    found: list[str] = []
    for item in catalog.facts:
        if item.project_label != project_label or item.queue != queue:
            continue
        facility = str(item.facility or item.title or "").strip()
        if facility and facility not in found:
            found.append(facility)
    return found


def _facilities_for_constructor(
    context: WorkingContext,
    catalog: WorkContextCatalog,
) -> Optional[list[str]]:
    """Resolve one facility list. A selected queue never becomes queue_scope.

    The approved Constructor read tool cannot enforce queue. Empty queue and
    empty titles stay unrestricted: the facility key is omitted, not sent empty.
    """
    queue = str(context.queue or "").strip()
    titles = [str(item).strip() for item in context.titles if str(item).strip()]
    if not queue:
        return titles or None
    known = _catalog_facilities(catalog, str(context.project or ""), queue)
    if not known:
        raise MissionCommandError(f"Для очереди {queue} нет титулов в рабочем контексте.")
    if not titles:
        return known
    outside = [item for item in titles if item not in known]
    if outside:
        raise MissionCommandError(
            f"Титулы {', '.join(outside)} не относятся к очереди {queue}."
        )
    chosen = [item for item in known if item in titles]
    if not chosen:
        raise MissionCommandError(f"Для очереди {queue} нет титулов в выбранном рабочем контексте.")
    return chosen


def _constructor_start_input(
    context: WorkingContext,
    catalog: WorkContextCatalog,
    project_code: str,
    idempotency_key: str,
):
    from agents.observability.contracts import InitiatorType, TriggerType
    from agents.run_control.contracts import ManagedRunStartInput

    scope: dict[str, object] = {}
    facilities = _facilities_for_constructor(context, catalog)
    if facilities:
        scope["facility"] = facilities
    if context.discipline:
        scope["discipline"] = context.discipline
    if context.systems:
        scope["system"] = list(context.systems)
    if context.packages:
        scope["iwp"] = [part.strip() for part in str(context.packages).split(",") if part.strip()]
    return ManagedRunStartInput(
        agent_code=CONSTRUCTOR_AGENT_CODE,
        initiator_type=InitiatorType.HUMAN,
        initiator_id="human-surface",
        trigger_type=TriggerType.MANUAL,
        trigger_reason=str(context.intent or "").strip()[:180],
        project_code=project_code,
        month_key=_stored_month_key(context.planning_month or ""),
        requested_mission_id="mission-" + idempotency_key,
        idempotency_key=idempotency_key,
        scope_request=scope,
    )


def _start_with_existing_runtime(start_input: object) -> MissionLaunchResult:
    from agents.control_room.factory import resolve_observability_db_path
    from agents.monthly_plan_constructor.shadow_checkpoint_store import (
        bootstrap_constructor_shadow_checkpoint_store,
    )
    from agents.monthly_plan_constructor.shadow_composition import (
        build_constructor_shadow_composition,
    )
    from agents.monthly_plan_constructor.shadow_handoff_store import (
        bootstrap_constructor_shadow_handoff_store,
    )
    from agents.monthly_plan_constructor.shadow_hitl_store import (
        bootstrap_constructor_shadow_hitl_store,
    )

    observability = resolve_observability_db_path()
    root = _REPOSITORY_ROOT

    def checkpointer_factory() -> object:
        store = bootstrap_constructor_shadow_checkpoint_store(repository_root=root)
        _RETAINED.append(store)
        return store.checkpointer

    composition = build_constructor_shadow_composition(
        observability_db_path=observability,
        checkpointer_factory=checkpointer_factory,
        hitl_store_factory=lambda: bootstrap_constructor_shadow_hitl_store(repository_root=root),
        handoff_store_factory=lambda: bootstrap_constructor_shadow_handoff_store(repository_root=root),
    )
    _RETAINED.append(composition)
    started = datetime.now(timezone.utc)
    result = composition.start(start_input)
    status = result.agent_run.operational_status
    status_text = status.value if hasattr(status, "value") else str(status)
    return MissionLaunchResult(
        run_id=str(result.agent_run.run_id),
        mission_id=str(result.agent_run.mission_id or getattr(start_input, "requested_mission_id", "")),
        status=status_text,
        started_at=started.isoformat(),
    )
