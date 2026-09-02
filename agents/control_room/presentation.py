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
    AgentRunSummary,
    AgentStageOccurrenceView,
    DerivationState,
    HandoffStatus,
    StageDisplayState,
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
