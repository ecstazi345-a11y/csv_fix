"""
Increment 10.7 — pure Control Room presentation helpers.

No Streamlit. No Query Port reads. No DB. Russian operator labels only.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from agents.control_room.dtos import (
    ConstructorCandidateResultView,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    constructor_row_awaits_human_review,
    AgentEventView,
    AgentHumanDecisionSurfaceView,
    AgentProfessionalExecutionPathView,
    AgentRunSummary,
    AgentStageOccurrenceView,
    DerivationState,
    DigitalOrganizationExecutionView,
    HandoffStatus,
    ProfessionalExecutionState,
    ProfessionalExecutionStepKind,
    ProfessionalExecutionStepView,
    ProfessionalResultAvailability,
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

AGENT_ROLE_RU: dict[str, str] = {
    "MONTHLY_PLAN_CONSTRUCTOR": "Конструктор месячного плана",
    "MONTHLY_PLAN_ADMISSION_AGENT": "Агент допуска",
}

HANDOFF_TYPE_RU: dict[str, str] = {
    "CONSTRUCTOR_TO_ADMISSION": "Передача Конструктор → Агент допуска",
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

DIGITAL_ORG_SECTION_TITLE_RU = "Цифровая организация"
DIGITAL_ORG_SECTION_SUBTITLE_RU = "Передача профессионального результата"
SOURCE_ROLE_COMPLETED_RU = (
    "Цифровой сотрудник завершил свою профессиональную работу."
)
HANDOFF_CREATED_ORG_RU = "Передача сформирована."
HANDOFF_CREATED_NOT_PERSISTED_RU = (
    "Долговременное сохранение в доступном наблюдаемом состоянии не подтверждено."
)
HANDOFF_PERSISTED_ORG_RU = "Передача сохранена."
HANDOFF_PERSISTED_SUPPORT_RU = "Долговременное сохранение подтверждено системой."
HANDOFF_PERSIST_FAILED_ORG_RU = "Передача не сохранена."
TARGET_ROLE_LABEL_RU = "Предназначенная профессиональная роль"
RECEIVER_START_NOT_CONFIRMED_RU = (
    "Запуск получателя в текущем наблюдаемом контуре не подтверждён."
)
RECEIVER_ACCEPTANCE_NOT_CONFIRMED_RU = (
    "Принятие результата получателем в текущем наблюдаемом контуре не подтверждено."
)
OWNERSHIP_NOT_PROVEN_RU = (
    "Переход профессиональной ответственности получателю системой пока не подтверждён."
)
HANDOFF_LEGACY_INCOMPLETE_RU = (
    "Профессиональный контекст передачи недоступен для этой исторической записи."
)
HANDOFF_INCONSISTENT_RU = "В истории передачи обнаружено противоречие."
HANDOFF_NOT_OBSERVED_RU = (
    "Передача профессионального результата в доступной истории не зафиксирована."
)
HANDOFF_NOT_CONFIRMED_INCOMPLETE_RU = (
    "В доступной части истории передача не подтверждена."
)
DIGITAL_ORG_HISTORY_INCOMPLETE_RU = "Показана доступная часть истории выполнения."
NO_NEXT_TRANSFER_RU = "Передача следующему цифровому сотруднику не выполнялась."
PROFESSIONAL_WORK_COMPLETED_RU = "Работа завершена"
PROFESSIONAL_RESULT_UNAVAILABLE_RU = "Профессиональный результат этого запуска недоступен."
PROFESSIONAL_RESULT_INCONSISTENT_RU = (
    "Профессиональное состояние не удалось прочитать согласованно."
)
CONSTRUCTOR_EMPLOYEE_TITLE_RU = "Конструктор месячного плана"
CONSTRUCTOR_EMPLOYEE_SUBTITLE_RU = (
    "Цифровой сотрудник формирования кандидатного состава месячного плана."
)
CONSTRUCTOR_WORK_TITLE_RU = "Что сделал цифровой сотрудник"
CONSTRUCTOR_PATH_TITLE_RU = "Профессиональный путь"
CONSTRUCTOR_MISSION_TITLE_RU = "Миссия"
CONSTRUCTOR_RESULT_TITLE_RU = "Результат обработки"
CONSTRUCTOR_CANDIDATES_TITLE_RU = "Кандидаты Constructor"
CONSTRUCTOR_AGENT_RECOMMENDATION_TITLE_RU = "Рекомендация цифрового сотрудника"
CONSTRUCTOR_HUMAN_TITLE_RU = "Решения человека"
CONSTRUCTOR_HUMAN_REQUEST_RU = "Цифровой сотрудник запросил решение."
CONSTRUCTOR_OUTCOME_TITLE_RU = "Итог Constructor"
CONSTRUCTOR_COMPLETED_LINE_RU = "Профессиональная работа завершена"
CONSTRUCTOR_NEXT_TRANSFER_RU = "Следующему цифровому сотруднику: не передавалось."
CONSTRUCTOR_EXCLUDED_BY_HUMAN_RU = (
    "Исключено из текущего кандидатного состава решением человека."
)
CONSTRUCTOR_QUANTITY_CAPTION_RU = (
    "Количества показаны так, как сохранены в профессиональном расчёте."
)
CONSTRUCTOR_SCALE_TITLE_RU = "Масштаб обработки"
CONSTRUCTOR_SCALE_SOURCE_NOT_STORED_RU = (
    "Исходный массив шире этого запуска в сохранённом снимке не зафиксирован."
)
CONSTRUCTOR_SCALE_SCOPE_SCAN_GAP_RU = (
    "Между релевантным scope и сканом нет сохранённой причины исключения: {count}"
)
CONSTRUCTOR_SCALE_UNACCOUNTED_RU = (
    "Сохранённые счётчики пакета не закрывают скан: {count}"
)
CONSTRUCTOR_EVIDENCE_TITLE_RU = "Технические доказательства и аудит"

PROFESSIONAL_STATUS_RU: dict[str, str] = {
    "PROFESSIONAL_WORK_COMPLETED": PROFESSIONAL_WORK_COMPLETED_RU,
}

HUMAN_REVIEW_DECISION_RU: dict[str, str] = {
    "REMOVE": "Исключить из текущего кандидатного состава",
    "REQUIRES_CLARIFICATION": "Требуется уточнение",
    "ADD": "Включить",
}

HUMAN_CONFIRM_DECISION_RU: dict[str, str] = {
    "CONFIRM": "Подтверждено человеком",
}

DISPOSITION_RU: dict[str, str] = {
    "INCLUDED": "Включено",
    "EXCLUDED": "Исключено",
    "UNRESOLVED": "Требует решения",
}

LABOR_STATUS_RU: dict[str, str] = {
    "VALIDATED": "Норма подтверждена",
    "PROVISIONAL": "Норма предварительная",
    "UNRESOLVED": "Норма труда не определена",
    "NOT_AVAILABLE": "Норма недоступна",
}

RECOMMENDATION_RU: dict[str, str] = {
    "HUMAN_REVIEW_REQUIRED": "Требуется решение человека",
    "RECOMMEND_ADD": "Рекомендовано к включению",
}

HUMAN_REVIEW_DECISION_SHORT_RU: dict[str, str] = {
    "REMOVE": "Исключить",
    "REQUIRES_CLARIFICATION": "Требует уточнения",
    "ADD": "Включить",
}

LABOR_STATUS_HEADLINE_RU: dict[str, str] = {
    "VALIDATED": "Подтверждена",
    "PROVISIONAL": "Предварительная",
    "UNRESOLVED": "Не определена",
    "NOT_AVAILABLE": "Недоступна",
}

_QUANTITY_UNIT_DISPLAY: dict[str, str] = {
    "м2": "м²",
    "m2": "м²",
    "м²": "м²",
    "м3": "м³",
    "m3": "м³",
    "м³": "м³",
}

PROFESSIONAL_PATH_STATUS_RU: dict[str, str] = {
    "MISSION_BOUND": "Миссия получена",
    "REALITY_LOADED": "Реальность прочитана",
    "PACKAGE_BUILT": "Кандидаты сформированы",
    "LABOR_RESOLVED": "Нормы труда проверены",
    "WAITING_FOR_HUMAN_REVIEW": "Запрошено решение человека",
    "APPLYING_HUMAN_REVIEW": "Решение человека применено",
    "REVIEWED_PACKAGE_READY": "Итоговый пакет сформирован",
    "WAITING_FOR_HUMAN_CONFIRM": "Запрошено подтверждение человека",
    "APPLYING_HUMAN_CONFIRM": "Подтверждено человеком",
    "PROFESSIONAL_WORK_COMPLETED": "Работа завершена",
}

_WORK_NARRATIVE_RU: dict[str, str] = {
    "MISSION_BOUND": "Получил миссию.",
    "REALITY_LOADED": "Прочитал доступную производственную реальность.",
    "PACKAGE_BUILT": "Сформировал кандидатный состав.",
    "LABOR_RESOLVED": "Проверил нормы труда.",
    "WAITING_FOR_HUMAN_REVIEW": "Обнаружил позиции, требующие решения человека.",
    "APPLYING_HUMAN_REVIEW": "Получил решения человека.",
    "REVIEWED_PACKAGE_READY": "Сформировал итоговый пакет.",
    "WAITING_FOR_HUMAN_CONFIRM": "Запросил подтверждение человека.",
    "APPLYING_HUMAN_CONFIRM": "Получил подтверждение человека.",
    "PROFESSIONAL_WORK_COMPLETED": "Завершил профессиональную работу.",
}


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


def constructor_project_short(project_code: str) -> str:
    text = str(project_code or "").strip()
    prefix = "PRJ_001_"
    if text.startswith(prefix) and text[len(prefix):].strip():
        return text[len(prefix):].strip()
    return text or "—"


def constructor_month_display(month_key: str) -> str:
    text = str(month_key or "").strip()
    if "-" in text:
        month_name, year = text.split("-", 1)
        if year.isdigit() and len(year) == 4 and month_name.strip():
            return f"{month_name.strip()} {year}"
    return text or "—"


def constructor_discipline_display(discipline: str) -> str:
    text = str(discipline or "").strip()
    if text.casefold() == "вентиляция":
        return "Вентиляция"
    return text or "—"


def run_radio_label(summary: AgentRunSummary) -> str:
    if summary.agent_code == "MONTHLY_PLAN_CONSTRUCTOR":
        status = (
            "Завершено"
            if summary.operational_status == "COMPLETED"
            else operational_status_ru(summary.operational_status)
        )
        return (
            "Конструктор месячного плана · "
            f"{constructor_project_short(summary.project_code)} · "
            f"{constructor_month_display(summary.month_key)} · {status}"
        )
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


def agent_role_ru(code: str) -> str:
    text = str(code or "").strip()
    return AGENT_ROLE_RU.get(text, text)


def handoff_type_ru(code: str) -> str:
    text = str(code or "").strip()
    return HANDOFF_TYPE_RU.get(text, text)


def digital_org_handoff_status_lines(status: HandoffStatus | str) -> tuple[str, ...]:
    value = status.value if isinstance(status, HandoffStatus) else str(status or "").strip()
    if value == HandoffStatus.CREATED.value:
        return (HANDOFF_CREATED_ORG_RU, HANDOFF_CREATED_NOT_PERSISTED_RU)
    if value == HandoffStatus.PERSISTED.value:
        return (HANDOFF_PERSISTED_ORG_RU, HANDOFF_PERSISTED_SUPPORT_RU)
    if value == HandoffStatus.PERSIST_FAILED.value:
        return (HANDOFF_PERSIST_FAILED_ORG_RU,)
    return (handoff_status_ru(value),)


def digital_org_source_completion_line(
    view: DigitalOrganizationExecutionView,
) -> Optional[str]:
    if view.source_operational_status == OperationalStatus.COMPLETED.value:
        return SOURCE_ROLE_COMPLETED_RU
    return None


def digital_org_receiver_honesty_lines() -> tuple[str, ...]:
    return (
        RECEIVER_START_NOT_CONFIRMED_RU,
        RECEIVER_ACCEPTANCE_NOT_CONFIRMED_RU,
        OWNERSHIP_NOT_PROVEN_RU,
    )


def _labeled(mapping: dict[str, str], code: str) -> str:
    text = str(code or "").strip()
    if not text:
        return "—"
    return mapping.get(text, text)


def professional_status_ru(code: str) -> str:
    return _labeled(PROFESSIONAL_STATUS_RU, code)


def human_review_decision_ru(code: str) -> str:
    return _labeled(HUMAN_REVIEW_DECISION_RU, code)


def human_review_decision_short_ru(code: str) -> str:
    return _labeled(HUMAN_REVIEW_DECISION_SHORT_RU, code)


def labor_status_headline_ru(code: str) -> str:
    return _labeled(LABOR_STATUS_HEADLINE_RU, code)


def constructor_unit_display(unit: str) -> str:
    text = str(unit or "").strip()
    if not text:
        return "—"
    compact = text.casefold().replace(" ", "")
    if "м³" in text or "м3" in compact or "m3" in compact:
        return "м³"
    if "м²" in text or "м2" in compact or "m2" in compact:
        return "м²"
    return _QUANTITY_UNIT_DISPLAY.get(text, text)


def constructor_quantity_display(stored: str, unit: str) -> str:
    """Readable quantity for the workbench. The stored DTO text is not rewritten."""
    text = str(stored or "").strip()
    unit_label = constructor_unit_display(unit)
    suffix = f" {unit_label}" if unit_label != "—" else ""
    if not text:
        return "—"
    try:
        value = Decimal(text)
    except InvalidOperation:
        return f"{text}{suffix}"
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == 0 and value != 0:
        number = "≈ 0"
    else:
        number = f"{rounded:.2f}".replace(".", ",")
    return f"{number}{suffix}"


def human_confirm_decision_ru(code: str) -> str:
    return _labeled(HUMAN_CONFIRM_DECISION_RU, code)


def disposition_ru(code: str) -> str:
    return _labeled(DISPOSITION_RU, code)


def labor_status_ru(code: str) -> str:
    return _labeled(LABOR_STATUS_RU, code)


def recommendation_ru(code: str) -> str:
    return _labeled(RECOMMENDATION_RU, code)


def professional_path_status_ru(code: str) -> str:
    return _labeled(PROFESSIONAL_PATH_STATUS_RU, code)


def constructor_work_lines(result: ConstructorProfessionalResultView) -> tuple[str, ...]:
    lines: list[str] = []
    for status in result.path_statuses:
        sentence = _WORK_NARRATIVE_RU.get(str(status))
        if sentence:
            lines.append(sentence)
    return tuple(lines)


def constructor_path_labels(result: ConstructorProfessionalResultView) -> tuple[str, ...]:
    labels: list[str] = []
    for status in result.path_statuses:
        label = PROFESSIONAL_PATH_STATUS_RU.get(str(status))
        if label:
            labels.append(label)
    return tuple(labels)


def constructor_candidate_rows(
    result: ConstructorProfessionalResultView,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in result.candidates:
        rows.append(
            {
                "Работа / BOQ": item.boq_code,
                "Наименование": item.name,
                "Ед.": item.unit or "—",
                "Остаток": item.remaining_qty,
                "Уже запланировано": item.already_planned_qty,
                "Доступно": item.available_qty,
                "Норма труда": labor_status_ru(item.labor_status),
                "Рекомендация Constructor": recommendation_ru(item.recommendation),
                "Решение человека": human_review_decision_ru(item.human_review_decision),
                "Итог": disposition_ru(item.final_disposition),
            }
        )
    return tuple(rows)


def constructor_management_scale_lines(
    result: ConstructorProfessionalResultView,
) -> tuple[str, ...]:
    """Compact processing result for the primary workbench. No unexplained gaps."""
    if result.availability is not ProfessionalResultAvailability.AVAILABLE:
        return ()
    lines: list[str] = []
    if result.mission_scope_row_count is not None:
        lines.append(f"В scope: {result.mission_scope_row_count}")
    if result.scanned_count is not None:
        lines.append(f"Просканировано: {result.scanned_count}")
    if result.package_candidate_count is not None:
        lines.append(f"Кандидатов Constructor: {result.package_candidate_count}")
    return tuple(lines)


def constructor_human_outcome_lines(
    result: ConstructorProfessionalResultView,
) -> tuple[str, ...]:
    included = "—" if result.included_count is None else str(result.included_count)
    excluded = "—" if result.excluded_count is None else str(result.excluded_count)
    unresolved = "—" if result.unresolved_count is None else str(result.unresolved_count)
    return (
        f"Включено: {included}",
        f"Исключено: {excluded}",
        f"Требует уточнения: {unresolved}",
    )


def constructor_final_outcome_lines(
    result: ConstructorProfessionalResultView,
) -> tuple[str, ...]:
    included = "—" if result.included_count is None else str(result.included_count)
    excluded = "—" if result.excluded_count is None else str(result.excluded_count)
    unresolved = "—" if result.unresolved_count is None else str(result.unresolved_count)
    return (
        f"Включено: {included}",
        f"Исключено: {excluded}",
        f"Требует решения: {unresolved}",
    )


def constructor_candidate_quantity_lines(
    item: ConstructorCandidateResultView,
) -> tuple[str, ...]:
    return (
        f"Остаток: {constructor_quantity_display(item.remaining_qty, item.unit)}",
        f"Уже запланировано: {constructor_quantity_display(item.already_planned_qty, item.unit)}",
        f"Доступно по расчёту: {constructor_quantity_display(item.available_qty, item.unit)}",
    )


def constructor_human_decision_lines(
    result: ConstructorProfessionalResultView,
) -> tuple[str, ...]:
    lines = [
        f"{item.boq_code} → {human_review_decision_short_ru(item.human_review_decision)}"
        for item in result.candidates
    ]
    if result.confirm_decision:
        lines.append(
            f"Итоговое подтверждение: {human_confirm_decision_ru(result.confirm_decision)}"
        )
    else:
        lines.append("Итоговое подтверждение: —")
    return tuple(lines)


def constructor_stored_quantity_lines(
    result: ConstructorProfessionalResultView,
) -> tuple[str, ...]:
    lines: list[str] = []
    for item in result.candidates:
        lines.append(f"{item.boq_code} остаток, как сохранено: {item.remaining_qty}")
        lines.append(
            f"{item.boq_code} уже запланировано, как сохранено: {item.already_planned_qty}"
        )
        lines.append(f"{item.boq_code} доступно, как сохранено: {item.available_qty}")
    return tuple(lines)


def constructor_processing_scale_lines(
    result: ConstructorProfessionalResultView,
) -> tuple[str, ...]:
    """Stored processing scale only. Does not invent a source universe."""
    if result.availability is not ProfessionalResultAvailability.AVAILABLE:
        return ()
    lines: list[str] = []
    has_scale = any(
        value is not None
        for value in (
            result.mission_scope_row_count,
            result.scanned_count,
            result.excluded_completed_count,
            result.excluded_no_remainder_count,
            result.already_planned_count,
            result.package_candidate_count,
        )
    )
    if not has_scale:
        return ()
    lines.append(CONSTRUCTOR_SCALE_SOURCE_NOT_STORED_RU)
    if result.mission_scope_row_count is not None:
        lines.append(f"В релевантном scope: {result.mission_scope_row_count}")
    if result.scanned_count is not None:
        lines.append(f"Просканировано при сборке кандидатов: {result.scanned_count}")
    if result.excluded_completed_count is not None:
        lines.append(f"Исключено выполненное: {result.excluded_completed_count}")
    if result.excluded_no_remainder_count is not None:
        lines.append(f"Исключено без остатка: {result.excluded_no_remainder_count}")
    if result.already_planned_count is not None:
        lines.append(f"Учтено уже запланированное: {result.already_planned_count}")
    if result.package_candidate_count is not None:
        lines.append(f"Кандидатов на рассмотрение: {result.package_candidate_count}")
    if (
        result.included_count is not None
        and result.excluded_count is not None
        and result.unresolved_count is not None
    ):
        lines.append(
            "После Human Review: "
            f"{result.included_count} включено / "
            f"{result.excluded_count} исключено / "
            f"{result.unresolved_count} нерешённых"
        )
    if (
        result.mission_scope_row_count is not None
        and result.scanned_count is not None
        and result.mission_scope_row_count > result.scanned_count
    ):
        lines.append(
            CONSTRUCTOR_SCALE_SCOPE_SCAN_GAP_RU.format(
                count=result.mission_scope_row_count - result.scanned_count
            )
        )
    if (
        result.scanned_count is not None
        and result.excluded_completed_count is not None
        and result.excluded_no_remainder_count is not None
        and result.already_planned_count is not None
        and result.package_candidate_count is not None
    ):
        accounted = (
            result.excluded_completed_count
            + result.excluded_no_remainder_count
            + result.already_planned_count
            + result.package_candidate_count
        )
        residual = result.scanned_count - accounted
        if residual > 0:
            lines.append(CONSTRUCTOR_SCALE_UNACCOUNTED_RU.format(count=residual))
    return tuple(lines)


CONSTRUCTOR_HITL_QUESTION_RU = "Включить эту позицию в итоговый пакет Constructor?"
CONSTRUCTOR_HITL_WRITE_UNAVAILABLE_RU = (
    "Запись решения через существующий Human Review contract на эту страницу ещё не подключена."
)
CONSTRUCTOR_ROW_HISTORY_GAP_RU = (
    "Доступные детальные позиции: {detailed} из {scope}. "
    "Построчная судьба остальных строк в сохранённом снимке не зафиксирована."
)
CONSTRUCTOR_MISSING_ROW_ARTIFACT_RU = (
    "Для полного списка не хватает сохранённого построчного результата классификации: "
    "снимок миссии хранит код, наименование и единицу, без количеств и без причины исключения."
)
CONSTRUCTOR_SCOPE_SCAN_WARNING_RU = (
    "{count} строк: детальная причина перехода в сохранённых данных не подтверждена"
)
CONSTRUCTOR_SCAN_CLASSIFICATION_WARNING_RU = (
    "{count} проверенная строка: классификация не зафиксирована"
)
CONSTRUCTOR_ALREADY_PLANNED_GAP_RU = (
    "Счётчик «уже в плане» сохранён, но построчный список этих позиций не сохранён."
)
CONSTRUCTOR_REGISTRY_TITLE_RU = "РЕЕСТР РЕШЕНИЙ CONSTRUCTOR"
CONSTRUCTOR_FINAL_PACKAGE_TITLE_RU = "ИТОГОВЫЙ ПАКЕТ CONSTRUCTOR"
CONSTRUCTOR_FINAL_PACKAGE_UNCONFIRMED_RU = "итоговый пакет: ещё не подтверждён"

_ROW_OUTCOME_RU = {
    "CANDIDATE": "Кандидат Constructor",
    "EXCLUDED_COMPLETED": "Не включать · работа выполнена",
    "EXCLUDED_NO_REMAINDER": "Не включать · остатка нет",
    "EXCLUDED_ALREADY_PLANNED": "Уже включено в план",
    "EXCLUDED_INVALID": "Не включать · исходные данные невалидны",
    "EXCLUDED_OVERRUN": "Не включать · выявлено превышение",
    "EXCLUDED_INCONSISTENT_QUANTITIES": (
        "Не включать · already_planned превышает физический остаток"
    ),
}

_ROW_OUTCOME_TILE_RU = {
    "EXCLUDED_COMPLETED": "ВЫПОЛНЕНО",
    "EXCLUDED_NO_REMAINDER": "БЕЗ ОСТАТКА",
    "EXCLUDED_ALREADY_PLANNED": "УЖЕ В ПЛАНЕ",
    "EXCLUDED_INVALID": "НЕВАЛИДНЫЕ",
    "EXCLUDED_OVERRUN": "ПРЕВЫШЕНИЕ",
    "EXCLUDED_INCONSISTENT_QUANTITIES": "НЕСОГЛАСОВАННЫЕ ОБЪЁМЫ",
    "CANDIDATE": "КАНДИДАТА",
}

_ROW_OUTCOME_FILTER_RU = {
    "CANDIDATE": "Кандидаты",
    "EXCLUDED_COMPLETED": "Выполнено",
    "EXCLUDED_NO_REMAINDER": "Без остатка",
    "EXCLUDED_ALREADY_PLANNED": "Уже в плане",
    "EXCLUDED_INVALID": "Невалидные",
    "EXCLUDED_OVERRUN": "Превышение",
    "EXCLUDED_INCONSISTENT_QUANTITIES": "Несогласованные объёмы",
}

_HITL_ACTION_TO_REVIEW_DECISION = {
    "OK": "ADD",
    "NOT_OK": "REMOVE",
    "NEED_DATA": "REQUIRES_CLARIFICATION",
}

_SAVED_HUMAN_DECISION_RU = {
    "ADD": "✓ ОК / включено",
    "REMOVE": "✕ НЕ ОК / исключено",
    "REQUIRES_CLARIFICATION": "Нужны данные",
}


def constructor_hitl_review_decision(action: str) -> str:
    """Presentation mapping only. Does not create a runtime enum."""
    key = str(action or "").strip()
    if key not in _HITL_ACTION_TO_REVIEW_DECISION:
        raise ValueError("unknown human action")
    return _HITL_ACTION_TO_REVIEW_DECISION[key]


def constructor_saved_decision_label(decision: str) -> str:
    return _labeled(_SAVED_HUMAN_DECISION_RU, decision)


def constructor_hitl_actions_visible(professional_status: str) -> bool:
    return str(professional_status or "").strip() == "WAITING_FOR_HUMAN_REVIEW"


def constructor_final_confirm_allowed(
    professional_status: str,
    *,
    candidates_decided: int,
    candidate_count: int,
    write_path_available: bool,
) -> bool:
    return (
        write_path_available
        and constructor_hitl_actions_visible(professional_status)
        and candidate_count > 0
        and candidates_decided == candidate_count
    )


def constructor_stop_reason(item: ConstructorCandidateResultView) -> str:
    if item.labor_status == "UNRESOLVED" or "LABOR_NORM_UNRESOLVED" in item.exception_codes:
        return "Нет подтверждённой нормы труда."
    if item.recommendation == "HUMAN_REVIEW_REQUIRED":
        return "Конструктор запросил решение человека."
    return "—"


def constructor_detail_gap_line(result: ConstructorProfessionalResultView) -> Optional[str]:
    detailed = len(result.candidates)
    scope = result.mission_scope_row_count
    if scope is None or scope == detailed:
        return None
    return CONSTRUCTOR_ROW_HISTORY_GAP_RU.format(detailed=detailed, scope=scope)


def constructor_funnel_steps(
    result: ConstructorProfessionalResultView,
) -> tuple[tuple[str, str], ...]:
    decided = sum(1 for item in result.candidates if str(item.human_review_decision or "").strip())
    candidate_count = (
        result.package_candidate_count
        if result.package_candidate_count is not None
        else len(result.candidates)
    )
    included = "—" if result.included_count is None else str(result.included_count)
    return (
        ("В контуре миссии", _count_text(result.mission_scope_row_count)),
        ("Проверено", _count_text(result.scanned_count)),
        ("Уже в плане", _count_text(result.already_planned_count)),
        ("Кандидатов Constructor", str(candidate_count)),
        ("Решено человеком", f"{decided} / {len(result.candidates)}"),
        ("В итоговом пакете", included),
    )


def constructor_funnel_warnings(
    result: ConstructorProfessionalResultView,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if result.mission_scope_row_count is not None and result.scanned_count is not None:
        gap = result.mission_scope_row_count - result.scanned_count
        if gap > 0:
            warnings.append(CONSTRUCTOR_SCOPE_SCAN_WARNING_RU.format(count=gap))
    if (
        result.scanned_count is not None
        and result.excluded_completed_count is not None
        and result.excluded_no_remainder_count is not None
        and result.already_planned_count is not None
        and result.package_candidate_count is not None
    ):
        accounted = (
            result.excluded_completed_count
            + result.excluded_no_remainder_count
            + result.already_planned_count
            + result.package_candidate_count
        )
        residual = result.scanned_count - accounted
        if residual > 0:
            text = CONSTRUCTOR_SCAN_CLASSIFICATION_WARNING_RU.format(count=residual)
            if residual != 1:
                text = f"{residual} проверенных строк: классификация не зафиксирована"
            warnings.append(text)
    return tuple(warnings)


def constructor_workspace_views(
    result: ConstructorProfessionalResultView,
) -> tuple[tuple[str, str], ...]:
    detailed = len(result.candidates)
    decided = sum(1 for item in result.candidates if str(item.human_review_decision or "").strip())
    included = "—" if result.included_count is None else str(result.included_count)
    views = [
        ("candidates", f"Кандидаты ({detailed})"),
        ("reviewed", f"Проверено человеком ({decided} / {detailed})"),
        ("final", f"Итоговый пакет ({included})"),
    ]
    if result.already_planned_count is not None:
        views.append(("already_planned", f"Уже в плане ({result.already_planned_count})"))
    views.append(("data_gap", "Проблемы данных"))
    return tuple(views)


def constructor_rows_for_view(
    result: ConstructorProfessionalResultView,
    view_id: str,
) -> tuple[ConstructorCandidateResultView, ...]:
    if view_id == "reviewed":
        return tuple(
            item for item in result.candidates if str(item.human_review_decision or "").strip()
        )
    if view_id == "final":
        return tuple(item for item in result.candidates if item.final_disposition == "INCLUDED")
    if view_id in {"already_planned", "data_gap"}:
        return ()
    return tuple(result.candidates)


def constructor_row_outcome_label(outcome: str) -> str:
    return _labeled(_ROW_OUTCOME_RU, outcome)


def constructor_decision_summary_tiles(
    registry: ConstructorDecisionRegistryView,
) -> tuple[tuple[str, str], ...]:
    counts = dict(registry.outcome_counts)
    tiles = [("РАБОТ В МИССИИ", str(registry.total_count))]
    for outcome in (
        "EXCLUDED_COMPLETED",
        "EXCLUDED_NO_REMAINDER",
        "EXCLUDED_ALREADY_PLANNED",
        "EXCLUDED_INVALID",
        "EXCLUDED_OVERRUN",
        "EXCLUDED_INCONSISTENT_QUANTITIES",
        "CANDIDATE",
    ):
        count = counts.get(outcome, 0)
        if count:
            tiles.append((_ROW_OUTCOME_TILE_RU[outcome], str(count)))
    return tuple(tiles)


def constructor_registry_filter_options(
    registry: ConstructorDecisionRegistryView,
) -> tuple[tuple[str, str], ...]:
    counts = dict(registry.outcome_counts)
    options = [("all", f"Все ({registry.total_count})")]
    for outcome, label in _ROW_OUTCOME_FILTER_RU.items():
        count = counts.get(outcome, 0)
        if count:
            options.append((outcome, f"{label} ({count})"))
    if registry.attention_count:
        options.append(
            ("attention", f"Требуют решения человека ({registry.attention_count})")
        )
    return tuple(options)


def constructor_registry_query(filter_id: str) -> dict[str, object]:
    if filter_id == "attention":
        return {"attention_only": True}
    if filter_id and filter_id != "all":
        return {"outcome": filter_id}
    return {}


def constructor_decision_table_rows(
    records: tuple[ConstructorRowDecisionView, ...] | list[ConstructorRowDecisionView],
    professional: ConstructorProfessionalResultView,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for record in records:
        rows.append(
            {
                "Система": record.system or "—",
                "BOQ": record.boq_code,
                "Наименование": record.name,
                "Ед.": constructor_unit_display(record.unit),
                "Остаток": _decision_quantity(record.remaining_qty, record.unit),
                "Уже в плане": _decision_quantity(record.already_planned_qty, record.unit),
                "Доступно": _decision_quantity(record.available_qty, record.unit),
                "Решение Constructor": constructor_row_outcome_label(record.outcome),
                "Основание": record.reason_text or "—",
                "Требуется человек": _human_attention_label(record, professional),
                "Итог": _decision_result_label(record, professional),
            }
        )
    return tuple(rows)


def constructor_context_system(registry: ConstructorDecisionRegistryView) -> str:
    if len(registry.known_systems) == 1:
        return registry.known_systems[0]
    return "—"


def constructor_final_package_lines(
    registry: ConstructorDecisionRegistryView,
) -> tuple[str, ...]:
    professional = registry.professional
    candidate_count = dict(registry.outcome_counts).get(
        "CANDIDATE",
        professional.package_candidate_count or 0,
    )
    decided = sum(
        1
        for item in professional.candidates
        if str(item.human_review_decision or "").strip()
    )
    confirmed = bool(str(professional.confirm_decision or "").strip())
    if confirmed and professional.included_count is not None:
        return (
            f"кандидатов: {candidate_count}",
            f"решений человека: {decided} / {len(professional.candidates)}",
            f"итоговый пакет: {professional.included_count} работ",
        )
    return (
        f"кандидатов: {candidate_count}",
        f"решений человека: {decided} / {len(professional.candidates) or candidate_count}",
        CONSTRUCTOR_FINAL_PACKAGE_UNCONFIRMED_RU,
    )


def _decision_quantity(stored: Optional[str], unit: str) -> str:
    if stored is None:
        return "—"
    return constructor_quantity_display(stored, unit)


def _human_attention_label(
    record: ConstructorRowDecisionView,
    professional: ConstructorProfessionalResultView,
) -> str:
    if constructor_row_awaits_human_review(record, professional):
        return "Да"
    if record.requires_human is False:
        return "Нет"
    return "—"


def _decision_result_label(
    record: ConstructorRowDecisionView,
    professional: ConstructorProfessionalResultView,
) -> str:
    if constructor_row_awaits_human_review(record, professional):
        return "Ожидает решения"
    matched = next(
        (
            item
            for item in professional.candidates
            if (record.candidate_id and item.candidate_id == record.candidate_id)
            or item.boq_code == record.boq_code
        ),
        None,
    )
    if matched is not None and str(matched.human_review_decision or "").strip():
        return constructor_saved_decision_label(matched.human_review_decision)
    if record.candidate_created:
        return "В кандидатном составе"
    return "Не в пакете"


def constructor_work_table_rows(
    items: tuple[ConstructorCandidateResultView, ...] | list[ConstructorCandidateResultView],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in items:
        rows.append(
            {
                "BOQ": item.boq_code,
                "Наименование": item.name,
                "Ед.": constructor_unit_display(item.unit),
                "Остаток": constructor_quantity_display(item.remaining_qty, item.unit),
                "Уже в плане": constructor_quantity_display(item.already_planned_qty, item.unit),
                "Доступно": constructor_quantity_display(item.available_qty, item.unit),
                "Норма труда": labor_status_headline_ru(item.labor_status),
                "Статус Constructor": recommendation_ru(item.recommendation),
                "Решение человека": constructor_saved_decision_label(item.human_review_decision),
                "Итог": disposition_ru(item.final_disposition),
            }
        )
    return tuple(rows)


def constructor_package_summary_lines(
    result: ConstructorProfessionalResultView,
    *,
    handoff_absent: bool,
) -> tuple[str, ...]:
    included = "—" if result.included_count is None else str(result.included_count)
    excluded = "—" if result.excluded_count is None else str(result.excluded_count)
    unresolved = "—" if result.unresolved_count is None else str(result.unresolved_count)
    confirm = (
        human_confirm_decision_ru(result.confirm_decision)
        if result.confirm_decision
        else "Не подтверждено"
    )
    lines = [
        f"Кандидатов Constructor: {len(result.candidates)}",
        f"Включено человеком: {included}",
        f"Исключено: {excluded}",
        f"Нужны данные: {unresolved}",
        f"Итоговый пакет: {included} работ",
        f"Human Confirm: {confirm}",
    ]
    if handoff_absent:
        lines.append("Передача следующему цифровому сотруднику: Не выполнялась")
    return tuple(lines)


def _count_text(value: Optional[int]) -> str:
    return "—" if value is None else str(value)


def constructor_exclusion_line(item: ConstructorCandidateResultView) -> Optional[str]:
    if item.human_review_decision == "REMOVE" and item.final_disposition == "EXCLUDED":
        return CONSTRUCTOR_EXCLUDED_BY_HUMAN_RU
    return None
