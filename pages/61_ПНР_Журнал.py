"""
ПНР — Журнал исполнения (MVP-0.5).

Наблюдение истории фактических попыток. Не создаёт и не меняет события.

Запуск (без меню app.py):
    streamlit run pages/61_ПНР_Журнал.py

Регистрация в app.py навигации в этом инкременте не делается.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

# Standalone `streamlit run pages/...` puts this file's directory on sys.path,
# not the repository root. Same bootstrap as form_app / archived standalone scripts.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from services.pnr_service import (
    PnrConfigError,
    PnrServiceError,
    PnrValidationError,
    list_active_objects,
    list_active_operations,
    list_active_systems,
    list_active_work_scopes,
    list_recent_execution_events,
)

# Temporary MVP site timezone. Not a timezone subsystem.
PNR_SITE_TZ = ZoneInfo("Europe/Moscow")

FILTER_ALL = "__all__"
FILTER_ALL_LABEL = "Все"

RESULT_CODE_TO_LABEL = {
    "PASS": "Выполнено",
    "FAIL": "Не выполнено",
    "PARTIAL": "Выполнено частично",
    "BLOCKED": "Заблокировано",
}
RESULT_FILTER_CODES = ["PASS", "FAIL", "PARTIAL", "BLOCKED"]


def format_system_label(row: dict) -> str:
    return f"{row.get('system_code') or ''} — {row.get('system_name') or ''}".strip(" —")


def format_object_label(row: dict) -> str:
    return f"{row.get('object_code') or ''} — {row.get('object_name') or ''}".strip(" —")


def format_operation_label(row: dict) -> str:
    return f"{row.get('operation_code') or ''} — {row.get('operation_name') or ''}".strip(" —")


def format_result_label(result: object) -> str:
    code = str(result or "").strip()
    return RESULT_CODE_TO_LABEL.get(code, code or "—")


def _index_by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {str(row[key]): row for row in rows if row.get(key)}


def parse_event_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_moscow_datetime(value: object) -> str:
    parsed = parse_event_datetime(value)
    if parsed is None:
        return "—"
    return parsed.astimezone(PNR_SITE_TZ).strftime("%d.%m.%Y %H:%M")


def _as_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def format_labor(value: object) -> str:
    number = _as_decimal(value)
    if number is None:
        return "—"
    if number == number.to_integral_value():
        return str(int(number))
    return format(number.normalize(), "f")


def resolve_operation_label(event: dict, operation_map: dict[str, dict]) -> str:
    operation_id = str(event.get("operation_id") or "").strip()
    unmapped = str(event.get("unmapped_operation_name") or "").strip()
    if operation_id and operation_id in operation_map:
        return format_operation_label(operation_map[operation_id])
    if unmapped:
        return unmapped
    if operation_id:
        return "Операция из справочника"
    return "—"


def event_order_key(event: dict) -> tuple:
    occurred = parse_event_datetime(event.get("occurred_at")) or datetime.min.replace(
        tzinfo=timezone.utc
    )
    created = parse_event_datetime(event.get("created_at")) or datetime.min.replace(
        tzinfo=timezone.utc
    )
    return (
        occurred.astimezone(timezone.utc),
        created.astimezone(timezone.utc),
        str(event.get("event_id") or ""),
    )


def sort_events_newest_first(events: list[dict]) -> list[dict]:
    return sorted(events, key=event_order_key, reverse=True)


def filter_events(
    events: list[dict],
    *,
    system_id: str | None = None,
    object_id: str | None = None,
    result: str | None = None,
) -> list[dict]:
    out: list[dict] = []
    for event in events:
        if system_id and str(event.get("system_id") or "") != str(system_id):
            continue
        if object_id and str(event.get("object_id") or "") != str(object_id):
            continue
        if result and str(event.get("result") or "") != str(result):
            continue
        out.append(event)
    return out


def summarize_events(events: list[dict]) -> dict:
    ordered = sort_events_newest_first(events)
    total = Decimal("0")
    for event in ordered:
        labor = _as_decimal(event.get("labor_hours"))
        if labor is not None:
            total += labor
    if not ordered:
        return {
            "current_result": None,
            "current_label": "Нет фактов",
            "attempt_count": 0,
            "total_labor": Decimal("0"),
            "latest_event": None,
        }
    latest = ordered[0]
    result = latest.get("result")
    return {
        "current_result": result,
        "current_label": format_result_label(result),
        "attempt_count": len(ordered),
        "total_labor": total,
        "latest_event": latest,
    }


def build_history_rows(
    events: list[dict],
    *,
    system_map: dict[str, dict],
    object_map: dict[str, dict],
    operation_map: dict[str, dict],
) -> list[dict]:
    rows: list[dict] = []
    for event in sort_events_newest_first(events):
        system_row = system_map.get(str(event.get("system_id") or ""))
        object_row = object_map.get(str(event.get("object_id") or ""))
        rows.append(
            {
                "Дата / время": format_moscow_datetime(event.get("occurred_at")),
                "Система": format_system_label(system_row) if system_row else "—",
                "Объект": format_object_label(object_row) if object_row else "—",
                "Операция": resolve_operation_label(event, operation_map),
                "Результат": format_result_label(event.get("result")),
                "Количество людей": event.get("people_count")
                if event.get("people_count") is not None
                else "—",
                "Продолжительность": format_labor(event.get("duration_hours")),
                "Трудозатраты": format_labor(event.get("labor_hours")),
                "Причина / проблема": event.get("reason") or "—",
                "Комментарий": event.get("comment") or "—",
            }
        )
    return rows


def _safe_user_error(exc: BaseException) -> str:
    if isinstance(exc, (PnrConfigError, PnrValidationError, PnrServiceError)):
        return str(exc)
    return "Не удалось загрузить журнал ПНР. Повторите попытку."


def _load_all_objects(systems: list[dict]) -> list[dict]:
    objects: list[dict] = []
    for system in systems:
        system_id = system.get("system_id")
        if not system_id:
            continue
        objects.extend(list_active_objects(system_id=system_id))
    return objects


def _load_all_operations() -> list[dict]:
    operations: list[dict] = []
    for scope in list_active_work_scopes():
        scope_id = scope.get("work_scope_id")
        if not scope_id:
            continue
        operations.extend(list_active_operations(work_scope_id=scope_id))
    return operations


st.set_page_config(
    page_title="ПНР — Журнал исполнения",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("ПНР — Журнал исполнения")
st.caption("История фактических попыток выполнения пусконаладочных работ.")

try:
    systems = list_active_systems()
    events = list_recent_execution_events()
    objects = _load_all_objects(systems)
    operations = _load_all_operations()
except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
    st.error(_safe_user_error(exc))
    st.stop()
except Exception:
    st.error("Не удалось загрузить журнал ПНР. Повторите попытку.")
    st.stop()

system_map = _index_by_id(systems, "system_id")
object_map = _index_by_id(objects, "object_id")
operation_map = _index_by_id(operations, "operation_id")

system_ids = [FILTER_ALL] + list(system_map.keys())
filter_cols = st.columns(3)
with filter_cols[0]:
    selected_system = st.selectbox(
        "Система",
        system_ids,
        format_func=lambda sid: FILTER_ALL_LABEL
        if sid == FILTER_ALL
        else format_system_label(system_map[sid]),
        key="pnr_journal_system",
    )

object_options = [FILTER_ALL]
if selected_system != FILTER_ALL:
    object_options.extend(
        [
            oid
            for oid, row in object_map.items()
            if str(row.get("system_id") or "") == str(selected_system)
        ]
    )
else:
    object_options.extend(list(object_map.keys()))

with filter_cols[1]:
    selected_object = st.selectbox(
        "Объект",
        object_options,
        format_func=lambda oid: FILTER_ALL_LABEL
        if oid == FILTER_ALL
        else format_object_label(object_map[oid]),
        key="pnr_journal_object",
    )

result_options = [FILTER_ALL] + RESULT_FILTER_CODES
with filter_cols[2]:
    selected_result = st.selectbox(
        "Результат",
        result_options,
        format_func=lambda code: FILTER_ALL_LABEL
        if code == FILTER_ALL
        else format_result_label(code),
        key="pnr_journal_result",
    )

visible_events = filter_events(
    events,
    system_id=None if selected_system == FILTER_ALL else str(selected_system),
    object_id=None if selected_object == FILTER_ALL else str(selected_object),
    result=None if selected_result == FILTER_ALL else str(selected_result),
)
summary = summarize_events(visible_events)

st.caption(
    "Текущее состояние выведено из последней попытки по времени. "
    "История не перезаписывается и не сохраняется как отдельный статус."
)

m1, m2, m3 = st.columns(3)
m1.metric("Текущее состояние", summary["current_label"])
m2.metric("Количество попыток", str(summary["attempt_count"]))
m3.metric("Суммарные трудозатраты, чел·ч", format_labor(summary["total_labor"]))

history_rows = build_history_rows(
    visible_events,
    system_map=system_map,
    object_map=object_map,
    operation_map=operation_map,
)

if not history_rows:
    st.info("Фактов выполнения пока нет.")
else:
    st.subheader("История попыток")
    ordered_events = sort_events_newest_first(visible_events)
    for event, row in zip(ordered_events, history_rows):
        st.markdown(
            f"**{row['Дата / время']}** · {row['Результат']}  \n"
            f"{row['Система']} → {row['Объект']}  \n"
            f"Операция: {row['Операция']}  \n"
            f"Люди: {row['Количество людей']} · "
            f"Продолжительность: {row['Продолжительность']} ч · "
            f"Трудозатраты: {row['Трудозатраты']} чел·ч  \n"
            f"Причина / проблема: {row['Причина / проблема']}  \n"
            f"Комментарий: {row['Комментарий']}"
        )
        st.divider()
    with st.expander("Технические сведения"):
        st.caption("Идентификаторы событий. Не используются как текущий статус.")
        for event in ordered_events:
            st.caption(f"event_id: {event.get('event_id') or '—'}")
