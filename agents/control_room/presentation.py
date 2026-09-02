"""
Increment 10.7 — pure Control Room presentation helpers.

No Streamlit. No Query Port reads. No DB. Russian operator labels only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from agents.control_room.dtos import (
    AgentEventView,
    AgentHumanDecisionSurfaceView,
    AgentProfessionalExecutionPathView,
    AgentRunSummary,
    AgentStageOccurrenceView,
    DerivationState,
    HandoffStatus,
    ProfessionalExecutionState,
    ProfessionalExecutionStepKind,
    ProfessionalExecutionStepView,
    StageArtifactView,
    StageDisplayState,
    StageToolExecutionView,
)
from agents.observability.contracts import OperationalStatus

_MOSCOW = ZoneInfo("Europe/Moscow")

OPERATIONAL_STATUS_RU: dict[str, str] = {
    OperationalStatus.REQUESTED.value: "Запрошен",
    OperationalStatus.AUTHORIZING.value: "Проверка допуска",
    OperationalStatus.AUTHORIZATION_DENIED.value: "Допуск отклонён",
    OperationalStatus.STARTING.value: "Запуск",
    OperationalStatus.RUNNING.value: "Выполняется",
    OperationalStatus.WAITING_FOR_HUMAN.value: "Ожидает решения человека",
    OperationalStatus.RETRYING.value: "Повторная попытка",
    OperationalStatus.COMPLETED.value: "Завершён",
    OperationalStatus.FAILED.value: "Ошибка",
    OperationalStatus.ABORTED.value: "Остановлен решением",
}

STAGE_DISPLAY_STATE_RU: dict[str, str] = {
    StageDisplayState.RUNNING.value: "Выполняется",
    StageDisplayState.COMPLETED.value: "Завершена",
    StageDisplayState.FAILED.value: "Ошибка",
}

HANDOFF_STATUS_RU: dict[str, str] = {
    HandoffStatus.NOT_STARTED.value: "Не начата",
    HandoffStatus.CREATED.value: "Создана",
    HandoffStatus.PERSISTED.value: "Сохранена",
    HandoffStatus.PERSIST_FAILED.value: "Ошибка сохранения",
}

EVENT_TYPE_RU: dict[str, str] = {
    "RUN_REQUESTED": "Запуск запрошен",
    "RUN_AUTHORIZATION_STARTED": "Проверка допуска начата",
    "RUN_AUTHORIZED": "Допуск подтверждён",
    "RUN_DENIED": "Допуск отклонён",
    "RUN_STARTED": "Запуск начат",
    "RUN_ADVANCING": "Выполнение продвигается",
    "RUN_COMPLETED": "Запуск завершён",
    "RUN_FAILED": "Ошибка выполнения",
    "RUN_ABORTED": "Остановлен решением",
    "MISSION_BOUND": "Миссия привязана",
    "STAGE_STARTED": "Стадия начата",
    "STAGE_COMPLETED": "Стадия завершена",
    "STAGE_FAILED": "Стадия завершилась ошибкой",
    "HUMAN_WAIT_STARTED": "Ожидание решения человека",
    "HUMAN_DECISION_RECEIVED": "Решение человека получено",
    "RUN_RESUMED": "Выполнение возобновлено",
    "HANDOFF_CREATED": "Передача создана",
    "HANDOFF_PERSISTED": "Передача сохранена",
    "HANDOFF_PERSIST_FAILED": "Ошибка сохранения передачи",
    "TOOL_CALL_STARTED": "Вызов инструмента начат",
    "TOOL_CALL_COMPLETED": "Вызов инструмента завершён",
    "TOOL_CALL_DENIED": "Вызов инструмента отклонён",
    "ARTIFACT_CREATED": "Результат создан",
    "REALITY_REFRESH_STARTED": "Повторная проверка реальности начата",
    "REALITY_REFRESH_COMPLETED": "Повторная проверка реальности завершена",
}

STATUS_ICON: dict[str, str] = {
    "neutral": "○",
    "active": "●",
    "waiting": "⏸",
    "success": "✓",
    "failure": "✕",
    "aborted": "⊘",
}

DERIVATION_STAGE_INCOMPLETE_RU = (
    "История стадий неполная. Показаны только данные из доступного окна событий."
)
DERIVATION_STAGE_INCONSISTENT_RU = (
    "Обнаружено противоречие в истории стадий. "
    "Текущее состояние не интерпретируется автоматически."
)
RUNS_COMPLETE_FALSE_RU = (
    "Показана ограниченная выборка запусков. "
    "Полный реестр может содержать другие записи."
)
CATALOG_INCOMPLETE_FILTER_RU = (
    "Доступна ограниченная выборка запусков. "
    "Список значений фильтров также может быть неполным."
)
EVENTS_COMPLETE_FALSE_RU = (
    "Показана только часть истории событий. "
    "Интерпретация стадий и ленты может быть неполной."
)
EMPTY_RUNS_RU = "Пока нет доступных зарегистрированных запусков цифровых сотрудников."
EMPTY_RUNS_INCOMPLETE_CATALOG_RU = "В доступной выборке нет запусков."
WAITING_FOR_HUMAN_RU = "Ожидает решения человека"

PROFESSIONAL_STAGE_ID_RU: dict[str, str] = {
    "AUTHORIZATION": "Проверка допуска",
    "MISSION_BINDING": "Привязка миссии",
    "REALITY_READ": "Чтение производственной реальности",
    "CANDIDATE_ASSEMBLY": "Формирование пакета кандидатов",
    "LABOR_NORM_RESOLUTION": "Проверка норм труда",
    "EXCEPTION_ANALYSIS": "Анализ исключений",
    "HUMAN_GATE": "Требуется решение человека",
    "REALITY_REVALIDATION": "Повторная проверка производственной реальности",
    "HANDOFF_PREPARATION": "Подготовка передачи",
    "HANDOFF_PERSISTENCE": "Сохранение передачи",
    "RUN_COMPLETION": "Завершение выполнения",
}

DECISION_CODE_RU: dict[str, str] = {
    "CLARIFY_SCOPE": "Уточнить область миссии",
    "ABORT_RUN": "Прервать выполнение",
}

TOOL_NAME_RU: dict[str, str] = {
    "load_constructor_scope": "Чтение области миссии",
}

ARTIFACT_TYPE_RU: dict[str, str] = {
    "snapshot": "Снимок производственной реальности",
    "package": "Пакет кандидатов",
}

PROFESSIONAL_EXECUTION_STATE_RU: dict[str, str] = {
    ProfessionalExecutionState.COMPLETED.value: "Завершён",
    ProfessionalExecutionState.RUNNING.value: "Выполняется",
    ProfessionalExecutionState.WAITING_FOR_HUMAN.value: "Ожидает решения человека",
    ProfessionalExecutionState.FAILED.value: "Ошибка",
    ProfessionalExecutionState.INCOMPLETE.value: "Неполные данные",
    ProfessionalExecutionState.INCONSISTENT.value: "Противоречие",
}

EXECUTION_PATH_INCOMPLETE_RU = (
    "Показана доступная часть истории выполнения."
)
EXECUTION_PATH_INCONSISTENT_RU = (
    "Обнаружено противоречие в профессиональном маршруте выполнения. "
    "Показана только подтверждённая часть."
)
HITL_LEGACY_CONTEXT_UNAVAILABLE_RU = (
    "Профессиональный контекст ожидания недоступен для этой исторической записи."
)
AUTHORITY_NOT_MODELED_RU = (
    "Полномочия решения системой пока не формализованы."
)
HUMAN_DECISION_HEADER_RU = "ТРЕБУЕТСЯ РЕШЕНИЕ ЧЕЛОВЕКА"
POST_DECISION_HEADER_RU = "ПОСЛЕ РЕШЕНИЯ"
REALITY_REFRESH_TITLE_RU = "Повторная проверка производственной реальности"


def operational_status_ru(code: str) -> str:
    text = str(code or "").strip()
    return OPERATIONAL_STATUS_RU.get(text, text)


def stage_display_state_ru(code: str) -> str:
    text = str(code or "").strip()
    if isinstance(code, StageDisplayState):
        text = code.value
    return STAGE_DISPLAY_STATE_RU.get(text, text)


def handoff_status_ru(code: str) -> str:
    text = str(code or "").strip()
    if isinstance(code, HandoffStatus):
        text = code.value
    return HANDOFF_STATUS_RU.get(text, text)


def event_type_ru(code: str) -> str:
    text = str(code or "").strip()
    return EVENT_TYPE_RU.get(text, text)


def status_visual_category(code: str) -> str:
    text = str(code or "").strip()
    if text in {
        OperationalStatus.REQUESTED.value,
        OperationalStatus.AUTHORIZING.value,
        OperationalStatus.STARTING.value,
    }:
        return "neutral"
    if text in {OperationalStatus.RUNNING.value, OperationalStatus.RETRYING.value}:
        return "active"
    if text == OperationalStatus.WAITING_FOR_HUMAN.value:
        return "waiting"
    if text == OperationalStatus.COMPLETED.value:
        return "success"
    if text in {OperationalStatus.FAILED.value, OperationalStatus.AUTHORIZATION_DENIED.value}:
        return "failure"
    if text == OperationalStatus.ABORTED.value:
        return "aborted"
    return "neutral"


def status_icon(code: str) -> str:
    return STATUS_ICON.get(status_visual_category(code), "○")


def format_timestamp_moscow(value: Optional[datetime]) -> str:
    if value is None:
        return "—"
    aware = value
    if aware.tzinfo is None:
        from datetime import timezone

        aware = aware.replace(tzinfo=timezone.utc)
    local = aware.astimezone(_MOSCOW)
    return local.strftime("%d.%m.%Y %H:%M")


def short_run_id(run_id: str) -> str:
    text = str(run_id or "").strip()
    if len(text) <= 8:
        return text
    return f"…{text[-8:]}"


def run_radio_label(summary: AgentRunSummary) -> str:
    status = operational_status_ru(summary.operational_status)
    icon = status_icon(summary.operational_status)
    return (
        f"{icon} {summary.agent_code} · {summary.project_code} · "
        f"{summary.month_key} · {status} · {short_run_id(summary.run_id)}"
    )


def all_operational_status_options() -> tuple[tuple[str, str], ...]:
    return tuple(
        (operational_status_ru(status.value), status.value)
        for status in OperationalStatus
    )


def catalog_filter_values(
    summaries: Iterable[AgentRunSummary],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    agents: set[str] = set()
    projects: set[str] = set()
    months: set[str] = set()
    for item in summaries:
        agents.add(item.agent_code)
        projects.add(item.project_code)
        months.add(item.month_key)
    return (
        tuple(sorted(agents)),
        tuple(sorted(projects)),
        tuple(sorted(months)),
    )


def stage_history_rows(
    occurrences: Iterable[AgentStageOccurrenceView],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in occurrences:
        state = item.display_state.value if isinstance(item.display_state, StageDisplayState) else str(item.display_state)
        rows.append(
            {
                "Стадия": item.stage_id,
                "Состояние": stage_display_state_ru(state),
                "Начало": format_timestamp_moscow(item.started_at) + " МСК",
                "Завершение": (
                    format_timestamp_moscow(item.completed_at) + " МСК"
                    if item.completed_at is not None
                    else "—"
                ),
                "Попытка": str(item.attempt_n),
                "Возобновление": str(item.resume_n),
            }
        )
    return tuple(rows)


def timeline_rows(events: Iterable[AgentEventView]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in events:
        rows.append(
            {
                "Время": format_timestamp_moscow(item.occurred_at) + " МСК",
                "Событие": event_type_ru(item.event_type),
                "Статус": item.status,
                "Стадия": item.stage_id or "—",
                "Название": item.title,
            }
        )
    return tuple(rows)


def derivation_stage_warning(state: DerivationState) -> Optional[str]:
    if state is DerivationState.INCOMPLETE:
        return DERIVATION_STAGE_INCOMPLETE_RU
    if state is DerivationState.INCONSISTENT:
        return DERIVATION_STAGE_INCONSISTENT_RU
    return None


def derivation_execution_path_warning(state: DerivationState) -> Optional[str]:
    if state is DerivationState.INCONSISTENT:
        return EXECUTION_PATH_INCONSISTENT_RU
    return None


def professional_stage_id_ru(stage_id: Optional[str]) -> str:
    if stage_id is None:
        return "—"
    text = str(stage_id).strip()
    return PROFESSIONAL_STAGE_ID_RU.get(text, text)


def decision_code_ru(code: str) -> str:
    text = str(code or "").strip()
    return DECISION_CODE_RU.get(text, text)


def tool_name_ru(name: str) -> str:
    text = str(name or "").strip()
    return TOOL_NAME_RU.get(text, text)


def artifact_type_ru(artifact_type: str) -> str:
    text = str(artifact_type or "").strip()
    return ARTIFACT_TYPE_RU.get(text, f"Артефакт: {text}")


def professional_execution_state_ru(state: ProfessionalExecutionState | str) -> str:
    text = state.value if isinstance(state, ProfessionalExecutionState) else str(state)
    return PROFESSIONAL_EXECUTION_STATE_RU.get(text, text)


def format_duration_seconds(
    started_at: Optional[datetime],
    ended_at: Optional[datetime],
) -> str:
    if started_at is None or ended_at is None:
        return "—"
    if ended_at < started_at:
        return "—"
    total_seconds = int((ended_at - started_at).total_seconds())
    if total_seconds < 60:
        return f"{total_seconds} с"
    minutes, seconds = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes} мин {seconds} с"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин"


def stage_step_duration(
    step: ProfessionalExecutionStepView,
    *,
    read_at: datetime,
) -> str:
    if step.professional_state in {
        ProfessionalExecutionState.INCOMPLETE,
        ProfessionalExecutionState.INCONSISTENT,
    }:
        return "—"
    end_at = step.completed_at
    if end_at is None and step.professional_state is ProfessionalExecutionState.RUNNING:
        end_at = read_at
    return format_duration_seconds(step.started_at, end_at)


def execution_step_title(step: ProfessionalExecutionStepView) -> str:
    if step.step_kind is ProfessionalExecutionStepKind.HUMAN_DECISION:
        return PROFESSIONAL_STAGE_ID_RU.get(step.stage_id or "HUMAN_GATE", step.stage_id or "HUMAN_GATE")
    if step.step_kind is ProfessionalExecutionStepKind.REALITY_REFRESH:
        return REALITY_REFRESH_TITLE_RU
    if step.step_kind is ProfessionalExecutionStepKind.HANDOFF_MARKER:
        return "Передача результата"
    return professional_stage_id_ru(step.stage_id)


def execution_step_state_icon(state: ProfessionalExecutionState) -> str:
    mapping = {
        ProfessionalExecutionState.COMPLETED: "✓",
        ProfessionalExecutionState.RUNNING: "●",
        ProfessionalExecutionState.WAITING_FOR_HUMAN: "⏸",
        ProfessionalExecutionState.FAILED: "✕",
        ProfessionalExecutionState.INCOMPLETE: "○",
        ProfessionalExecutionState.INCONSISTENT: "!",
    }
    return mapping.get(state, "○")


def human_decision_reason_text(surface: AgentHumanDecisionSurfaceView) -> str:
    request = surface.request
    if request is None:
        return HITL_LEGACY_CONTEXT_UNAVAILABLE_RU
    if request.human_readable_reason:
        return request.human_readable_reason
    if request.reason_code:
        return request.reason_code
    if request.derivation_state is DerivationState.INCOMPLETE:
        return HITL_LEGACY_CONTEXT_UNAVAILABLE_RU
    return "—"


def post_decision_lines(surface: AgentHumanDecisionSurfaceView) -> tuple[str, ...]:
    consequence = surface.consequence
    if consequence is None:
        return ()
    lines: list[str] = []
    if consequence.decision_received_at is not None:
        lines.append("Решение получено")
    if consequence.closed_by is not None:
        if consequence.closed_by.value == "RESUMED":
            lines.append("Выполнение возобновлено")
        else:
            lines.append("Выполнение прервано")
    if consequence.reality_refresh_started_at is not None:
        lines.append("Повторная проверка реальности начата")
    if consequence.reality_refresh_completed_at is not None:
        lines.append("Производственная реальность повторно проверена.")
    if consequence.reality_refresh_failed_at is not None:
        lines.append("Повторная проверка реальности завершилась ошибкой")
    if consequence.next_stage_id is not None:
        lines.append(f"Следующий этап: {professional_stage_id_ru(consequence.next_stage_id)}")
    return tuple(lines)


def execution_path_summary_rows(
    path: AgentProfessionalExecutionPathView,
    *,
    read_at: datetime,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for step in path.steps:
        rows.append(
            {
                "Состояние": execution_step_state_icon(step.professional_state),
                "Этап": execution_step_title(step),
                "Статус": professional_execution_state_ru(step.professional_state),
                "Начало": format_timestamp_moscow(step.started_at) + " МСК",
                "Окончание": (
                    format_timestamp_moscow(step.completed_at) + " МСК"
                    if step.completed_at is not None
                    else "—"
                ),
                "Длительность": stage_step_duration(step, read_at=read_at),
                "Попытка": str(step.attempt_n) if step.attempt_n > 1 else "—",
            }
        )
    return tuple(rows)


def tool_summary_rows(tools: tuple[StageToolExecutionView, ...]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "Инструмент": tool_name_ru(tool.tool_name),
            "Статус": tool.status.value,
        }
        for tool in tools
    )


def artifact_summary_rows(
    artifacts: tuple[StageArtifactView, ...],
) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "Тип": artifact_type_ru(artifact.artifact_type),
            "ID": artifact.artifact_id,
        }
        for artifact in artifacts
    )
