"""
ПНР — Фиксация факта (MVP-0.4).

Создаёт НОВУЮ попытку выполнения операции. Не редактирует статус.

Запуск поля (без меню app.py):
    streamlit run pages/60_ПНР_Фиксация_факта.py

Регистрация в app.py навигации в этом инкременте не делается.
"""

from __future__ import annotations

import sys
from datetime import datetime, time
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
    create_execution_event,
    list_active_objects,
    list_active_operations,
    list_active_systems,
    list_active_work_scopes,
)

# Temporary MVP site timezone. Not a timezone subsystem.
PNR_SITE_TZ = ZoneInfo("Europe/Moscow")

MODE_CATALOG = "Операция из справочника"
MODE_UNMAPPED = "Другая операция"

RESULT_LABEL_TO_CODE = {
    "Выполнено": "PASS",
    "Не выполнено": "FAIL",
    "Выполнено частично": "PARTIAL",
    "Заблокировано": "BLOCKED",
}
RESULT_LABELS = list(RESULT_LABEL_TO_CODE.keys())
REASON_EMPHASIS_RESULTS = frozenset({"FAIL", "PARTIAL", "BLOCKED"})


def format_system_label(row: dict) -> str:
    return f"{row.get('system_code') or ''} — {row.get('system_name') or ''}".strip(" —")


def format_object_label(row: dict) -> str:
    return f"{row.get('object_code') or ''} — {row.get('object_name') or ''}".strip(" —")


def format_scope_label(row: dict) -> str:
    return str(row.get("scope_name") or row.get("scope_code") or "")


def format_operation_label(row: dict) -> str:
    return f"{row.get('operation_code') or ''} — {row.get('operation_name') or ''}".strip(" —")


def compute_labor_preview(people_count: int, duration_hours: float | int | Decimal) -> Decimal:
    return Decimal(int(people_count)) * Decimal(str(duration_hours))


def submit_fingerprint(
    *,
    system_id: str,
    object_id: str,
    operation_id: str | None,
    unmapped_operation_name: str | None,
    result: str,
    occurred_at: datetime,
    people_count: int,
    duration_hours: Decimal,
) -> tuple:
    return (
        system_id,
        object_id,
        operation_id,
        unmapped_operation_name,
        result,
        occurred_at.isoformat(),
        people_count,
        str(duration_hours),
    )


def build_create_kwargs(
    *,
    system_id: str,
    object_id: str,
    operation_mode: str,
    operation_id: str | None,
    unmapped_operation_name: str | None,
    result_code: str,
    occurred_at: datetime,
    people_count: int,
    duration_hours: Decimal,
    reason: str | None,
    comment: str | None,
) -> dict:
    labor = compute_labor_preview(people_count, duration_hours)
    kwargs: dict = {
        "system_id": system_id,
        "object_id": object_id,
        "result": result_code,
        "occurred_at": occurred_at,
        "people_count": people_count,
        "duration_hours": duration_hours,
        "labor_hours": labor,
        "reason": reason,
        "comment": comment,
        "source": "STREAMLIT",
    }
    if operation_mode == MODE_UNMAPPED:
        kwargs["operation_id"] = None
        kwargs["unmapped_operation_name"] = (unmapped_operation_name or "").strip() or None
    else:
        kwargs["operation_id"] = operation_id
        kwargs["unmapped_operation_name"] = None
    return kwargs


def _safe_user_error(exc: BaseException) -> str:
    if isinstance(exc, (PnrConfigError, PnrValidationError, PnrServiceError)):
        return str(exc)
    return "Не удалось сохранить факт ПНР. Повторите попытку."


def _index_by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {str(row[key]): row for row in rows if row.get(key)}


st.set_page_config(
    page_title="ПНР — Фиксация факта",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("ПНР — Фиксация факта")
st.caption(
    "Фиксация фактической попытки выполнения операции пусконаладочных работ. "
    "Каждое сохранение создаёт новую запись. Статус предыдущей попытки не изменяется."
)

try:
    systems = list_active_systems()
except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
    st.error(_safe_user_error(exc))
    st.stop()
except Exception:
    st.error("Не удалось загрузить список систем.")
    st.stop()

if not systems:
    st.warning("Нет активных систем. Обратитесь к администратору.")
    st.stop()

system_map = _index_by_id(systems, "system_id")
system_ids = list(system_map.keys())
system_id = st.selectbox(
    "Система",
    system_ids,
    format_func=lambda sid: format_system_label(system_map[sid]),
)

try:
    objects = list_active_objects(system_id=system_id)
except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
    st.error(_safe_user_error(exc))
    st.stop()
except Exception:
    st.error("Не удалось загрузить список объектов.")
    st.stop()

if not objects:
    st.warning("Для выбранной системы нет активных объектов.")
    st.stop()

object_map = _index_by_id(objects, "object_id")
object_ids = list(object_map.keys())
object_id = st.selectbox(
    "Объект",
    object_ids,
    format_func=lambda oid: format_object_label(object_map[oid]),
)

try:
    scopes = list_active_work_scopes()
except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
    st.error(_safe_user_error(exc))
    st.stop()
except Exception:
    st.error("Не удалось загрузить разделы работ.")
    st.stop()

scope_map = _index_by_id(scopes, "work_scope_id")
scope_ids = list(scope_map.keys())
work_scope_id = None
if scope_ids:
    work_scope_id = st.selectbox(
        "Раздел работ",
        scope_ids,
        format_func=lambda wid: format_scope_label(scope_map[wid]),
    )
else:
    st.info("Справочник разделов работ пуст. Можно зафиксировать «Другую операцию».")

operations: list[dict] = []
if work_scope_id:
    try:
        operations = list_active_operations(work_scope_id=work_scope_id)
    except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
        st.error(_safe_user_error(exc))
        st.stop()
    except Exception:
        st.error("Не удалось загрузить операции.")
        st.stop()

operation_mode = st.radio(
    "Операция",
    [MODE_CATALOG, MODE_UNMAPPED],
    index=0,
    horizontal=True,
    key="pnr_operation_mode",
)

operation_id = None
unmapped_name = None
if operation_mode == MODE_CATALOG:
    if not operations:
        st.warning(
            "В выбранном разделе нет операций справочника. "
            "Выберите «Другая операция» или обратитесь к администратору."
        )
    else:
        operation_map = _index_by_id(operations, "operation_id")
        operation_ids = list(operation_map.keys())
        operation_id = st.selectbox(
            "Операция из справочника",
            operation_ids,
            format_func=lambda oid: format_operation_label(operation_map[oid]),
        )
else:
    unmapped_name = st.text_input("Наименование операции", placeholder="Что выполнялось на площадке")

result_label = st.radio("Результат", RESULT_LABELS, index=0, key="pnr_result")
result_code = RESULT_LABEL_TO_CODE[result_label]

now_local = datetime.now(PNR_SITE_TZ)
work_date = st.date_input("Дата выполнения", value=now_local.date())
work_time = st.time_input(
    "Время выполнения",
    value=time(now_local.hour, now_local.minute),
)
occurred_at = datetime.combine(work_date, work_time, tzinfo=PNR_SITE_TZ)

people_count = st.number_input("Количество людей", min_value=1, step=1, value=1)
duration_hours = st.number_input(
    "Продолжительность, ч",
    min_value=0.0,
    step=0.5,
    value=1.0,
    format="%.2f",
)

try:
    labor_preview = compute_labor_preview(int(people_count), duration_hours)
except (InvalidOperation, ValueError, TypeError):
    labor_preview = Decimal("0")

st.text_input(
    "Трудозатраты, чел·ч",
    value=str(labor_preview),
    disabled=True,
    help="Считается автоматически: люди × продолжительность. Пользователь не редактирует.",
)

reason_label = "Причина / проблема"
if result_code in REASON_EMPHASIS_RESULTS:
    reason_label = "Причина / проблема (важно для этого результата)"
reason = st.text_area(reason_label, height=80)
comment = st.text_area("Комментарий", height=80)

submitted = st.button("СОХРАНИТЬ ФАКТ", type="primary")

if submitted:
    if operation_mode == MODE_CATALOG and not operation_id:
        st.error("Выберите операцию из справочника или режим «Другая операция».")
    elif operation_mode == MODE_UNMAPPED and not (unmapped_name or "").strip():
        st.error("Укажите наименование операции.")
    elif result_code in REASON_EMPHASIS_RESULTS and not (reason or "").strip():
        st.error("Укажите причину / проблему.")
    else:
        duration_dec = Decimal(str(duration_hours))
        kwargs = build_create_kwargs(
            system_id=str(system_id),
            object_id=str(object_id),
            operation_mode=operation_mode,
            operation_id=str(operation_id) if operation_id else None,
            unmapped_operation_name=unmapped_name,
            result_code=result_code,
            occurred_at=occurred_at,
            people_count=int(people_count),
            duration_hours=duration_dec,
            reason=(reason or "").strip() or None,
            comment=(comment or "").strip() or None,
        )
        fingerprint = submit_fingerprint(
            system_id=kwargs["system_id"],
            object_id=kwargs["object_id"],
            operation_id=kwargs.get("operation_id"),
            unmapped_operation_name=kwargs.get("unmapped_operation_name"),
            result=kwargs["result"],
            occurred_at=kwargs["occurred_at"],
            people_count=kwargs["people_count"],
            duration_hours=kwargs["duration_hours"],
        )
        last = st.session_state.get("pnr_last_submit_fingerprint")
        if last == fingerprint:
            st.warning(
                "Этот же факт только что отправлен. "
                "Для новой попытки измените результат или другие данные."
            )
        else:
            try:
                created = create_execution_event(**kwargs)
            except (PnrConfigError, PnrValidationError, PnrServiceError) as exc:
                st.error(_safe_user_error(exc))
            except Exception:
                st.error("Не удалось сохранить факт ПНР. Повторите попытку.")
            else:
                st.session_state.pnr_last_submit_fingerprint = fingerprint
                st.success("Факт ПНР сохранён.")
                event_id = (created or {}).get("event_id")
                if event_id:
                    with st.expander("Технические сведения"):
                        st.caption(f"event_id: {event_id}")
