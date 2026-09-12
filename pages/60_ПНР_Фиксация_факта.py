"""
ПНР — Фиксация факта (FIELD-1C).

Контролируемый ввод физического факта выполнения ПНР.
Каждое сохранение создаёт новую запись. История не редактируется.

Запуск поля (без меню app.py):
    streamlit run pages/60_ПНР_Фиксация_факта.py
"""

from __future__ import annotations

import sys
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
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
    WORK_TYPE_CODE_PNR,
    create_structured_execution_event,
    get_work_type_by_code,
    list_active_objects,
    list_active_operations,
    list_active_projects,
    list_active_titles,
    list_active_work_scopes,
    list_context_disciplines,
    list_system_work_contexts,
    resolve_object_functional_position_id,
)

PNR_SITE_TZ = ZoneInfo("Europe/Moscow")
PREFERRED_PROJECT_CODE = "PRJ_001_SLM"
PREFERRED_TITLE_CODE = "УКПГ2-011"

MODE_CATALOG = "Операция из справочника"
MODE_UNMAPPED = "Другая операция"

DONE_COMPLETED = "Выполнена"
DONE_PARTIAL = "Выполнена частично"
DONE_BLOCKED = "Работа заблокирована"
DONE_NOT_COMPLETED = "Не выполнена"
DONE_OPTIONS = [DONE_COMPLETED, DONE_PARTIAL, DONE_BLOCKED, DONE_NOT_COMPLETED]

EVAL_CONFORMS = "Соответствует"
EVAL_DOES_NOT_CONFORM = "Не соответствует"
EVAL_NOT_EVALUATED = "Пока не оценивалось"
EVAL_OPTIONS = [EVAL_CONFORMS, EVAL_DOES_NOT_CONFORM, EVAL_NOT_EVALUATED]

OTHER_WORK_YES = "Да"
OTHER_WORK_NO = "Нет"
OTHER_WORK_UNKNOWN = "Не могу определить"
OTHER_WORK_OPTIONS = [OTHER_WORK_YES, OTHER_WORK_NO, OTHER_WORK_UNKNOWN]

BLOCKED_CATEGORY_OTHER_LABEL = "Другое"
BLOCKED_CATEGORY_LABEL_TO_CODE = {
    "Проектная/рабочая документация": "DOCUMENTATION",
    "Строительная готовность": "CONSTRUCTION_READINESS",
    "Смежные работы": "ADJACENT_WORK",
    "Материалы": "MATERIALS",
    "Оборудование": "EQUIPMENT",
    "Электропитание": "POWER_SUPPLY",
    "Теплоноситель / рабочая среда": "WORKING_MEDIUM",
    "Доступ к объекту": "OBJECT_ACCESS",
    "Допуск и безопасность": "PERMIT_SAFETY",
    "Персонал": "PERSONNEL",
    "Инструмент / измерительный прибор": "INSTRUMENT",
    "Автоматизация / ПО / настройки": "AUTOMATION_SOFTWARE",
    "Решение другой стороны": "THIRD_PARTY_DECISION",
    "Погодные / внешние условия": "WEATHER_EXTERNAL",
    BLOCKED_CATEGORY_OTHER_LABEL: "OTHER",
}
BLOCKED_CATEGORY_LABELS = list(BLOCKED_CATEGORY_LABEL_TO_CODE.keys())


def format_project_label(row: dict) -> str:
    return str(row.get("project_name") or row.get("project_code") or "")


def format_title_label(row: dict) -> str:
    return str(row.get("title_name") or row.get("title_code") or "")


def format_discipline_label(row: dict) -> str:
    return str(row.get("discipline_name") or "")


def format_system_context_label(row: dict) -> str:
    return str(row.get("context_system_code") or "")


def format_object_label(row: dict) -> str:
    return str(row.get("object_name") or row.get("object_code") or "")


def format_scope_label(row: dict) -> str:
    return str(row.get("scope_name") or "")


def format_operation_label(row: dict) -> str:
    return str(row.get("operation_name") or "")


def compute_labor_preview(people_count: int, duration_hours: float | int | Decimal) -> Decimal:
    return Decimal(int(people_count)) * Decimal(str(duration_hours))


def preferred_index(ids: list[str], row_map: dict[str, dict], field: str, preferred: str) -> int:
    for index, row_id in enumerate(ids):
        if row_map[row_id].get(field) == preferred:
            return index
    return 0


def map_execution_evaluation(
    done_label: str, evaluation_label: str | None
) -> tuple[str, str]:
    if done_label == DONE_COMPLETED:
        evaluation_map = {
            EVAL_CONFORMS: "CONFORMS",
            EVAL_DOES_NOT_CONFORM: "DOES_NOT_CONFORM",
            EVAL_NOT_EVALUATED: "NOT_EVALUATED",
        }
        if evaluation_label not in evaluation_map:
            raise ValueError("Не выбрана оценка соответствия.")
        return "COMPLETED", evaluation_map[evaluation_label]
    if done_label == DONE_PARTIAL:
        return "PARTIAL", "NOT_EVALUATED"
    if done_label == DONE_BLOCKED:
        return "BLOCKED", "NOT_EVALUATED"
    if done_label == DONE_NOT_COMPLETED:
        return "NOT_COMPLETED", "NOT_EVALUATED"
    raise ValueError("Не выбран фактический результат.")


def map_other_work_available(label: str) -> bool | None:
    if label == OTHER_WORK_YES:
        return True
    if label == OTHER_WORK_NO:
        return False
    if label == OTHER_WORK_UNKNOWN:
        return None
    raise ValueError("Не выбран ответ про другие работы.")


def map_blocked_category(label: str) -> str:
    code = BLOCKED_CATEGORY_LABEL_TO_CODE.get(label)
    if not code:
        raise ValueError("Не выбрана категория препятствия.")
    return code


def build_partial_detail(completed_text: str, remaining_text: str) -> dict[str, str]:
    completed = (completed_text or "").strip()
    remaining = (remaining_text or "").strip()
    if not completed:
        raise ValueError("Укажите, что выполнено.")
    if not remaining:
        raise ValueError("Укажите, что осталось выполнить.")
    return {"completed_text": completed, "remaining_text": remaining}


def build_blocked_detail(
    category_label: str,
    description: str,
    other_work_label: str,
) -> dict[str, Any]:
    category = map_blocked_category(category_label)
    text = (description or "").strip()
    if category == "OTHER" and not text:
        raise ValueError("Для категории «Другое» укажите, что конкретно препятствует работе.")
    return {
        "constraint_category": category,
        "constraint_description": text or None,
        "other_work_available": map_other_work_available(other_work_label),
    }


def measurements_from_rows(
    rows: list[dict[str, Any]],
    recorded_at: datetime,
) -> list[dict[str, Any]]:
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("Время измерения должно содержать часовой пояс.")
    prepared: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        name = str(row.get("parameter_name") or "").strip()
        unit = str(row.get("unit") or "").strip()
        point = str(row.get("measurement_point") or "").strip()
        instrument = str(row.get("instrument_text") or "").strip()
        raw_value = row.get("value")
        empty_identity = not name and not unit and not point and not instrument
        if empty_identity:
            continue
        if not name or not unit or raw_value is None or raw_value == "":
            raise ValueError(
                f"Измерение {index}: укажите параметр, значение и единицу измерения."
            )
        prepared.append(
            {
                "parameter_name": name,
                "measurement_point": point or None,
                "value": Decimal(str(raw_value)),
                "unit": unit,
                "instrument_text": instrument or None,
                "recorded_at": recorded_at,
            }
        )
    return prepared


def submit_fingerprint(kwargs: dict[str, Any]) -> tuple:
    measurements = kwargs.get("measurements") or []
    return (
        kwargs.get("system_id"),
        kwargs.get("object_id"),
        kwargs.get("functional_position_id"),
        kwargs.get("operation_id"),
        kwargs.get("unmapped_operation_name"),
        kwargs.get("execution_status"),
        kwargs.get("evaluation_status"),
        kwargs.get("observation_text"),
        str(kwargs.get("partial_detail")),
        str(kwargs.get("blocked_detail")),
        tuple(
            (
                item.get("parameter_name"),
                str(item.get("value")),
                item.get("unit"),
            )
            for item in measurements
        ),
        kwargs["occurred_at"].isoformat(),
        kwargs.get("people_count"),
        str(kwargs.get("duration_hours")),
    )


def build_structured_kwargs(
    *,
    system_id: str,
    object_id: str,
    functional_position_id: str | None,
    operation_mode: str,
    operation_id: str | None,
    unmapped_operation_name: str | None,
    execution_status: str,
    evaluation_status: str,
    occurred_at: datetime,
    people_count: int,
    duration_hours: Decimal,
    observation_text: str | None,
    measurements: list[dict[str, Any]] | None,
    blocked_detail: dict[str, Any] | None,
    partial_detail: dict[str, Any] | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "system_id": system_id,
        "object_id": object_id,
        "functional_position_id": functional_position_id,
        "execution_status": execution_status,
        "evaluation_status": evaluation_status,
        "occurred_at": occurred_at,
        "people_count": people_count,
        "duration_hours": duration_hours,
        "observation_text": (observation_text or "").strip() or None,
        "measurements": measurements or [],
        "blocked_detail": blocked_detail,
        "partial_detail": partial_detail,
        "source": "STREAMLIT",
    }
    if operation_mode == MODE_UNMAPPED:
        kwargs["operation_id"] = None
        kwargs["unmapped_operation_name"] = (unmapped_operation_name or "").strip() or None
    else:
        kwargs["operation_id"] = operation_id
        kwargs["unmapped_operation_name"] = None
    return kwargs


def build_review_lines(
    *,
    project_name: str,
    title_name: str,
    discipline_name: str,
    system_label: str,
    object_label: str,
    scope_label: str | None,
    work_label: str,
    done_label: str,
    evaluation_label: str | None,
    observation_text: str | None,
    partial_detail: dict[str, Any] | None,
    blocked_detail_label: str | None,
    blocked_description: str | None,
    other_work_label: str | None,
    measurements: list[dict[str, Any]],
    people_count: int,
    duration_hours: Decimal,
    labor_preview: Decimal,
) -> list[str]:
    lines = [
        f"Проект: {project_name}",
        f"Титул: {title_name}",
        "Вид работ: ПНР",
        f"Дисциплина: {discipline_name}",
        f"Система: {system_label}",
        f"Физический объект: {object_label}",
        f"Раздел работ: {scope_label or '—'}",
        f"Работа: {work_label}",
        f"Что произошло: {done_label}",
    ]
    if evaluation_label:
        lines.append(f"Оценка: {evaluation_label}")
    if observation_text:
        lines.append(f"Наблюдение: {observation_text}")
    if partial_detail:
        lines.append(f"Что выполнено: {partial_detail.get('completed_text')}")
        lines.append(f"Что осталось: {partial_detail.get('remaining_text')}")
    if blocked_detail_label:
        lines.append(f"Препятствие: {blocked_detail_label}")
        if blocked_description:
            lines.append(f"Что конкретно препятствует: {blocked_description}")
        if other_work_label:
            lines.append(f"Можно выполнять другие работы: {other_work_label}")
    if measurements:
        compact = ", ".join(
            f"{item['parameter_name']} {item['value']} {item['unit']}"
            for item in measurements
        )
        lines.append(f"Измерения ({len(measurements)}): {compact}")
    else:
        lines.append("Измерения: нет")
    lines.append(f"Количество специалистов: {people_count}")
    lines.append(f"Продолжительность: {duration_hours} ч")
    lines.append(f"Трудозатраты: {labor_preview} чел·ч")
    return lines


def _safe_user_error(exc: BaseException) -> str:
    if isinstance(exc, (PnrConfigError, PnrValidationError, PnrServiceError)):
        return str(exc)
    return "Не удалось сохранить факт ПНР. Повторите попытку."


def _index_by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {str(row[key]): row for row in rows if row.get(key)}


def _load_or_stop(loader, empty_warning: str, fail_message: str):
    try:
        rows = loader()
    except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
        st.error(_safe_user_error(exc))
        st.stop()
    except Exception:
        st.error(fail_message)
        st.stop()
    if not rows:
        st.warning(empty_warning)
        st.stop()
    return rows


st.set_page_config(
    page_title="ПНР — Фиксация факта",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.title("ПНР — Фиксация факта")
st.caption("Фиксация физического факта выполнения. Каждое сохранение — новая запись.")

st.markdown("### Контекст")

projects = _load_or_stop(
    list_active_projects,
    "Нет активных проектов. Обратитесь к администратору.",
    "Не удалось загрузить список проектов.",
)
project_map = _index_by_id(projects, "project_id")
project_ids = list(project_map.keys())
project_id = st.selectbox(
    "Проект",
    project_ids,
    index=preferred_index(project_ids, project_map, "project_code", PREFERRED_PROJECT_CODE),
    format_func=lambda pid: format_project_label(project_map[pid]),
    key="pnr_project_id",
)
project_row = project_map[str(project_id)]

titles = _load_or_stop(
    lambda: list_active_titles(project_id=project_id),
    "Для выбранного проекта нет активных титулов.",
    "Не удалось загрузить список титулов.",
)
title_map = _index_by_id(titles, "title_id")
title_ids = list(title_map.keys())
title_id = st.selectbox(
    "Титул",
    title_ids,
    index=preferred_index(title_ids, title_map, "title_code", PREFERRED_TITLE_CODE),
    format_func=lambda tid: format_title_label(title_map[tid]),
    key="pnr_title_id",
)
title_row = title_map[str(title_id)]

try:
    pnr_work_type = get_work_type_by_code(work_type_code=WORK_TYPE_CODE_PNR)
except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
    st.error(_safe_user_error(exc))
    st.stop()
except Exception:
    st.error("Не удалось определить вид работ ПНР.")
    st.stop()

if not pnr_work_type:
    st.error("Не найден активный вид работ ПНР.")
    st.stop()

st.markdown("**Вид работ: ПНР**")
work_type_id = pnr_work_type["work_type_id"]

disciplines = _load_or_stop(
    lambda: list_context_disciplines(title_id=title_id, work_type_id=work_type_id),
    "Для выбранного титула нет дисциплин в контексте ПНР.",
    "Не удалось загрузить список дисциплин.",
)
discipline_map = _index_by_id(disciplines, "discipline_id")
discipline_ids = list(discipline_map.keys())
discipline_id = st.selectbox(
    "Дисциплина",
    discipline_ids,
    format_func=lambda did: format_discipline_label(discipline_map[did]),
    key="pnr_discipline_id",
)
discipline_row = discipline_map[str(discipline_id)]

try:
    contexts = list_system_work_contexts(
        title_id=title_id,
        work_type_id=work_type_id,
        discipline_id=discipline_id,
    )
except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
    st.error(_safe_user_error(exc))
    st.stop()
except Exception:
    st.error("Не удалось загрузить список систем.")
    st.stop()

context_map = _index_by_id(contexts, "system_work_context_id")
context_ids = list(context_map.keys())
if not context_ids:
    st.selectbox("Система", ["—"], key="pnr_system_empty")
    st.warning("Нет систем для выбранного контекста.")
    st.stop()

context_id = st.selectbox(
    "Система",
    context_ids,
    format_func=lambda cid: format_system_context_label(context_map[cid]),
    key="pnr_system_context_id",
)
context_row = context_map[str(context_id)]
system_id = str(context_row["system_id"])

st.markdown("### Физический объект")

objects = _load_or_stop(
    lambda: list_active_objects(system_id=system_id),
    "Для выбранной системы нет активных физических объектов.",
    "Не удалось загрузить список объектов.",
)
object_map = _index_by_id(objects, "object_id")
object_ids = list(object_map.keys())
object_id = st.selectbox(
    "Физический объект",
    object_ids,
    format_func=lambda oid: format_object_label(object_map[oid]),
    key="pnr_object_id",
)
object_row = object_map[str(object_id)]

try:
    functional_position_id = resolve_object_functional_position_id(object_id=object_id)
except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
    st.error(_safe_user_error(exc))
    st.stop()
except Exception:
    st.error("Не удалось определить функциональную позицию объекта.")
    st.stop()

st.markdown("### Работа")

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
        key="pnr_work_scope_id",
    )
else:
    st.info("Справочник разделов работ пуст. Можно зафиксировать другую работу.")

operations: list[dict] = []
if work_scope_id:
    try:
        operations = list_active_operations(work_scope_id=work_scope_id)
    except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
        st.error(_safe_user_error(exc))
        st.stop()
    except Exception:
        st.error("Не удалось загрузить работы.")
        st.stop()

operation_mode = st.radio(
    "Как указать работу",
    [MODE_CATALOG, MODE_UNMAPPED],
    index=0,
    key="pnr_operation_mode",
)

operation_id = None
unmapped_name = None
work_label = ""
if operation_mode == MODE_CATALOG:
    if not operations:
        st.warning(
            "В выбранном разделе нет работ справочника. Выберите «Другая операция»."
        )
    else:
        operation_map = _index_by_id(operations, "operation_id")
        operation_ids = list(operation_map.keys())
        operation_id = st.selectbox(
            "Работа",
            operation_ids,
            format_func=lambda oid: format_operation_label(operation_map[oid]),
            key="pnr_operation_id",
        )
        work_label = format_operation_label(operation_map[str(operation_id)])
else:
    unmapped_name = st.text_input("Наименование работы", placeholder="Что выполнялось")
    work_label = (unmapped_name or "").strip()

st.markdown("### Фактический результат")

done_label = st.radio(
    "Работа выполнена?",
    DONE_OPTIONS,
    index=0,
    key="pnr_done",
)

evaluation_label = None
if done_label == DONE_COMPLETED:
    evaluation_label = st.radio(
        "Полученный результат соответствует требованию?",
        EVAL_OPTIONS,
        index=0,
        key="pnr_evaluation",
    )

execution_status, evaluation_status = map_execution_evaluation(done_label, evaluation_label)

observation_text = None
partial_detail = None
blocked_detail = None
blocked_category_label = None
blocked_description = None
other_work_label = None
_partial_completed_draft = ""
_partial_remaining_draft = ""

if execution_status == "COMPLETED" and evaluation_status == "DOES_NOT_CONFORM":
    observation_text = st.text_area("Что обнаружено?", height=80, key="pnr_observation")
elif execution_status == "PARTIAL":
    _partial_completed_draft = st.text_area("Что выполнено?", height=80, key="pnr_partial_done")
    _partial_remaining_draft = st.text_area(
        "Что осталось выполнить?", height=80, key="pnr_partial_left"
    )
    try:
        partial_detail = build_partial_detail(
            _partial_completed_draft, _partial_remaining_draft
        )
    except ValueError:
        partial_detail = None
elif execution_status == "BLOCKED":
    blocked_category_label = st.selectbox(
        "Что препятствует выполнению?",
        BLOCKED_CATEGORY_LABELS,
        key="pnr_blocked_category",
    )
    blocked_description = st.text_area(
        "Что конкретно препятствует работе?",
        height=80,
        key="pnr_blocked_description",
    )
    other_work_label = st.radio(
        "Можно выполнять другие работы?",
        OTHER_WORK_OPTIONS,
        index=0,
        key="pnr_other_work",
    )
    try:
        blocked_detail = build_blocked_detail(
            blocked_category_label,
            blocked_description,
            other_work_label,
        )
    except ValueError:
        blocked_detail = None
elif execution_status == "NOT_COMPLETED":
    observation_text = st.text_area(
        "Комментарий к фактическому состоянию (необязательно)",
        height=80,
        key="pnr_not_completed_note",
    )

st.markdown("### Структурированные данные")
st.caption("Измерения необязательны.")

if "pnr_meas_count" not in st.session_state:
    st.session_state.pnr_meas_count = 0

meas_cols = st.columns(2)
if meas_cols[0].button("Добавить измерение", key="pnr_meas_add"):
    st.session_state.pnr_meas_count = int(st.session_state.pnr_meas_count) + 1
    st.rerun()
if meas_cols[1].button("Убрать последнее", key="pnr_meas_remove"):
    current = int(st.session_state.pnr_meas_count)
    if current > 0:
        st.session_state.pnr_meas_count = current - 1
        st.rerun()

measurement_rows: list[dict[str, Any]] = []
for index in range(int(st.session_state.pnr_meas_count)):
    st.markdown(f"**Измерение {index + 1}**")
    measurement_rows.append(
        {
            "parameter_name": st.text_input("Параметр", key=f"pnr_meas_param_{index}"),
            "measurement_point": st.text_input(
                "Точка измерения", key=f"pnr_meas_point_{index}"
            ),
            "value": st.number_input(
                "Значение",
                key=f"pnr_meas_value_{index}",
                step=0.001,
                format="%.3f",
                value=0.0,
            ),
            "unit": st.text_input("Единица измерения", key=f"pnr_meas_unit_{index}"),
            "instrument_text": st.text_input("Прибор", key=f"pnr_meas_instr_{index}"),
        }
    )

st.markdown("### Трудозатраты")

now_local = datetime.now(PNR_SITE_TZ)
work_date = st.date_input("Дата выполнения", value=now_local.date())
work_time = st.time_input(
    "Время выполнения",
    value=time(now_local.hour, now_local.minute),
)
occurred_at = datetime.combine(work_date, work_time, tzinfo=PNR_SITE_TZ)

people_count = st.number_input(
    "Количество специалистов",
    min_value=1,
    step=1,
    value=1,
    key="pnr_people_count",
)
duration_hours = st.number_input(
    "Продолжительность, ч",
    min_value=0.0,
    step=0.5,
    value=1.0,
    format="%.2f",
    key="pnr_duration_hours",
)

try:
    labor_preview = compute_labor_preview(int(people_count), duration_hours)
except (InvalidOperation, ValueError, TypeError):
    labor_preview = Decimal("0")

st.markdown(f"**Трудозатраты:** {labor_preview} чел·ч")
st.caption("Считается автоматически. Значение нельзя изменить вручную.")

try:
    preview_measurements = measurements_from_rows(measurement_rows, occurred_at)
    measurement_error = None
except ValueError as exc:
    preview_measurements = []
    measurement_error = str(exc)

st.markdown("### Проверка")
review_lines = build_review_lines(
    project_name=format_project_label(project_row),
    title_name=format_title_label(title_row),
    discipline_name=format_discipline_label(discipline_row),
    system_label=format_system_context_label(context_row),
    object_label=format_object_label(object_row),
    scope_label=format_scope_label(scope_map[str(work_scope_id)]) if work_scope_id else None,
    work_label=work_label or "—",
    done_label=done_label,
    evaluation_label=evaluation_label,
    observation_text=(observation_text or "").strip() or None,
    partial_detail=partial_detail,
    blocked_detail_label=blocked_category_label,
    blocked_description=(blocked_description or "").strip() or None,
    other_work_label=other_work_label,
    measurements=preview_measurements,
    people_count=int(people_count),
    duration_hours=Decimal(str(duration_hours)),
    labor_preview=labor_preview,
)
st.markdown("\n".join(f"- {line}" for line in review_lines))

submitted = st.button("Сохранить факт", type="primary")

if submitted:
    error_message = None
    if operation_mode == MODE_CATALOG and not operation_id:
        error_message = "Выберите работу из справочника или режим «Другая операция»."
    elif operation_mode == MODE_UNMAPPED and not (unmapped_name or "").strip():
        error_message = "Укажите наименование работы."
    elif execution_status == "COMPLETED" and evaluation_status == "DOES_NOT_CONFORM":
        if not (observation_text or "").strip():
            error_message = "Укажите, что обнаружено."
    elif execution_status == "PARTIAL":
        try:
            partial_detail = build_partial_detail(
                _partial_completed_draft, _partial_remaining_draft
            )
        except ValueError as exc:
            error_message = str(exc)
    elif execution_status == "BLOCKED":
        try:
            blocked_detail = build_blocked_detail(
                blocked_category_label or "",
                blocked_description or "",
                other_work_label or "",
            )
        except ValueError as exc:
            error_message = str(exc)
    if error_message is None and measurement_error:
        error_message = measurement_error

    if error_message:
        st.error(error_message)
    else:
        duration_dec = Decimal(str(duration_hours))
        kwargs = build_structured_kwargs(
            system_id=system_id,
            object_id=str(object_id),
            functional_position_id=functional_position_id,
            operation_mode=operation_mode,
            operation_id=str(operation_id) if operation_id else None,
            unmapped_operation_name=unmapped_name,
            execution_status=execution_status,
            evaluation_status=evaluation_status,
            occurred_at=occurred_at,
            people_count=int(people_count),
            duration_hours=duration_dec,
            observation_text=observation_text,
            measurements=preview_measurements,
            blocked_detail=blocked_detail,
            partial_detail=partial_detail,
        )
        fingerprint = submit_fingerprint(kwargs)
        last = st.session_state.get("pnr_last_submit_fingerprint")
        if last == fingerprint:
            st.warning(
                "Этот же факт только что отправлен. "
                "Для новой попытки измените результат или другие данные."
            )
        else:
            try:
                created = create_structured_execution_event(**kwargs)
            except (PnrConfigError, PnrValidationError, PnrServiceError) as exc:
                st.error(_safe_user_error(exc))
            except Exception:
                st.error("Не удалось сохранить факт ПНР. Повторите попытку.")
            else:
                st.session_state.pnr_last_submit_fingerprint = fingerprint
                st.success("Факт выполнения сохранён.")
                event_id = (created or {}).get("event_id")
                if event_id:
                    with st.expander("Технические сведения"):
                        st.caption(f"Идентификатор записи: {event_id}")
