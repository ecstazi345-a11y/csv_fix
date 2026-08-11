"""
Реестр ограничений допуска месячного плана — Page 24 (R2.1).

Источник: services.monthly_plan_constraint_registry_service
- update OPEN/IN_PROGRESS: update_constraint
- resolve: resolve_constraint
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pandas as pd
import streamlit as st

from services.monthly_plan_constraint_registry_service import (
    CONSTRAINT_PRIORITY_DISPLAY,
    DEADLINE_SOURCE_DISPLAY,
    DEADLINE_STATUS_DISPLAY,
    build_registry_summary,
    clear_constraint_registry_caches,
    clear_registry_read_caches,
    display_constraint_priority,
    display_deadline_source,
    display_deadline_status,
    load_constraint_events,
    load_constraint_registry,
    parse_constraint_event_payload,
    resolve_constraint,
    update_constraint,
)

st.set_page_config(layout="wide", page_title="Реестр ограничений допуска")

ALL = "Все"
OPEN_ONLY = "Только открытые"
MODE_ALL = "Все"
OPEN_RESOLUTIONS = frozenset({"OPEN", "IN_PROGRESS"})
CLOSED_RESOLUTIONS = frozenset({"RESOLVED", "CANCELLED"})
EMPTY_AUTHOR = "Не заполнено автором"
COMMENT_TABLE_MAX_LEN = 80
EMPTY_MARKERS = frozenset({"", "—", "-", "–"})

DATE_MODE_KEEP = "Не менять"
DATE_MODE_SET = "Указать дату"
DATE_MODE_CLEAR = "Очистить"
DATE_MODES = [DATE_MODE_KEEP, DATE_MODE_SET, DATE_MODE_CLEAR]

UPDATE_TEXT_FIELDS = [
    "problem_owner",
    "owner_name",
    "subcontractor_coordinator",
    "constraint_category",
    "problem_description",
    "problem_impact",
    "required_action",
]
UPDATE_DATE_FIELDS = [
    "constraint_occurred_at",
    "target_resolution_date",
    "next_control_date",
]
UPDATE_ENUM_FIELDS = {
    "constraint_priority": list(CONSTRAINT_PRIORITY_DISPLAY.keys()),
    "deadline_status": [
        "NOT_SET",
        "REQUESTED",
        "ESTIMATED",
        "CONFIRMED",
        "RESCHEDULED",
    ],
    "deadline_source": list(DEADLINE_SOURCE_DISPLAY.keys()),
}

ADMISSION_OUTCOME_MESSAGES = {
    "READY": "BOQ допущен и доступен для включения в месячный паспорт",
    "READY_WITH_RISK": "Ограничение снято, но по BOQ остаются риски",
    "BLOCKED": "Ограничение снято, но по BOQ остаются блокирующие ограничения",
    "WAITING": "Ограничение снято, но BOQ ожидает проверки/решения других отделов",
}

CHECK_STATUS_OPTIONS = ["ОЖИДАЕТ", "PASS", "WARNING", "HOLD", "FAIL"]
RESOLUTION_STATUS_OPTIONS = ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"]

CHECK_STATUS_DISPLAY = {
    "ОЖИДАЕТ": "Ожидает проверки",
    "WARNING": "Требует уточнения",
    "HOLD": "Удержание",
    "FAIL": "Заблокировано",
    "PASS": "Проверка пройдена",
}
RESOLUTION_STATUS_DISPLAY = {
    "OPEN": "Открыто",
    "IN_PROGRESS": "В работе",
    "RESOLVED": "Снято",
    "CANCELLED": "Отменено",
}
CHECK_STATUS_BG = {
    "Ожидает проверки": "background-color: #f3f4f6; color: #374151;",
    "Проверка пройдена": "background-color: #dcfce7; color: #166534;",
    "Требует уточнения": "background-color: #fef9c3; color: #854d0e;",
    "Удержание": "background-color: #ffedd5; color: #9a3412;",
    "Заблокировано": "background-color: #fee2e2; color: #991b1b;",
}
RESOLUTION_STATUS_BG = {
    "Открыто": "background-color: #f3f4f6; color: #374151;",
    "В работе": "background-color: #dbeafe; color: #1e40af;",
    "Снято": "background-color: #dcfce7; color: #166534;",
    "Отменено": "background-color: #f3f4f6; color: #6b7280;",
}

TABLE_COLUMNS = [
    ("project_code", "Проект", 120),
    ("month_key", "Месяц", 110),
    ("constraint_created_at", "Дата фиксации", 110),
    ("constraint_occurred_at", "Дата возникновения", 120),
    ("queue", "Очередь", 100),
    ("facility_building", "Титул", 180),
    ("construction_discipline", "Дисциплина", 130),
    ("boq_code", "BOQ-код", 140),
    ("boq_name", "Наименование работ", 260),
    ("work_package", "Пакет работ / IWP", 160),
    ("system", "Система", 140),
    ("unit", "Ед. изм.", 80),
    ("planned_qty", "Плановый объём", 110),
    ("plan_value", "Плановая стоимость", 140),
    ("responsible_department", "Отдел", 140),
    ("check_status", "Статус проверки", 160),
    ("resolution_status", "Статус устранения", 120),
    ("constraint_category", "Тип ограничения", 140),
    ("constraint_priority", "Приоритет", 110),
    ("problem_summary", "Суть проблемы", 280),
    ("problem_owner", "Владелец проблемы", 150),
    ("owner_name", "Исполнитель устранения", 160),
    ("subcontractor_coordinator", "Координатор", 140),
    ("required_action", "Требуемое действие", 220),
    ("deadline_status", "Статус срока", 130),
    ("effective_deadline_status", "Эффективный статус срока", 150),
    ("target_resolution_date", "Плановая дата устранения", 130),
    ("next_control_date", "Следующий контроль", 130),
    ("actual_resolution_date", "Фактическая дата устранения", 130),
    ("days_open_real", "Дней открыто (real)", 120),
    ("delay_days", "Задержка, дней", 100),
    ("value_at_risk", "Стоимость под риском", 140),
    ("comment", "Примечание", 240),
    ("resolved_by", "Кто снял", 120),
    ("last_action_at", "Дата последнего действия", 200),
]


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------


def safe_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "<na>"}:
        return ""
    return text


def safe_num(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_date(value: Any) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = safe_str(value)
    if not text:
        return None
    try:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:  # noqa: BLE001
        return None


def format_date_ru(value: Any) -> str:
    d = safe_date(value)
    return d.strftime("%d.%m.%Y") if d else "—"


def format_datetime_ru(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return display_dash(value)
        if getattr(parsed, "tzinfo", None) is not None:
            parsed = parsed.tz_convert(None)
        return parsed.strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return display_dash(value)


def money_ru(value: Any) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        amount = float(value)
        sign = "-" if amount < 0 else ""
        amount = abs(amount)
        whole, frac = f"{amount:.2f}".split(".")
        whole_fmt = f"{int(whole):,}".replace(",", " ")
        return f"{sign}{whole_fmt},{frac} ₽"
    except Exception:  # noqa: BLE001
        return "—"


def qty_ru(value: Any) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
    except Exception:  # noqa: BLE001
        return "—"


def display_dash(value: Any) -> str:
    text = safe_str(value)
    return text if text else "—"


def display_author_empty(value: Any) -> str:
    text = safe_str(value)
    return text if text else EMPTY_AUTHOR


def format_date_author_empty(value: Any) -> str:
    d = safe_date(value)
    return d.strftime("%d.%m.%Y") if d else EMPTY_AUTHOR


def display_check_status(value: Any) -> str:
    key = safe_str(value).upper()
    if not key:
        return "—"
    return CHECK_STATUS_DISPLAY.get(key, safe_str(value))


def display_resolution_status(value: Any) -> str:
    key = safe_str(value).upper()
    if not key:
        return "—"
    return RESOLUTION_STATUS_DISPLAY.get(key, safe_str(value))


def format_check_filter_option(opt: str) -> str:
    if opt == ALL:
        return ALL
    return CHECK_STATUS_DISPLAY.get(opt, opt)


def format_resolution_filter_option(opt: str) -> str:
    if opt == ALL:
        return ALL
    return RESOLUTION_STATUS_DISPLAY.get(opt, opt)


def truncate_comment(value: Any, max_len: int = COMMENT_TABLE_MAX_LEN) -> str:
    text = safe_str(value)
    if not text:
        return "—"
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)] + "…"


def normalize_text_for_compare(value: Any) -> Optional[str]:
    text = safe_str(value)
    if text in EMPTY_MARKERS:
        return None
    return text or None


def extract_update_baseline(row: Any) -> dict[str, Any]:
    """Snapshot of editable fields for dirty-patch compare / hydrate."""
    get = row.get if hasattr(row, "get") else lambda k, d=None: row[k] if k in row else d
    baseline: dict[str, Any] = {}
    for key in UPDATE_TEXT_FIELDS:
        baseline[key] = normalize_text_for_compare(get(key))
    for key in UPDATE_DATE_FIELDS:
        baseline[key] = safe_date(get(key))
    for key in UPDATE_ENUM_FIELDS:
        raw = safe_str(get(key)).upper()
        baseline[key] = raw or None
        if key == "deadline_source" and not raw:
            baseline[key] = None
        if key == "deadline_status" and not raw:
            baseline[key] = "NOT_SET"
        if key == "constraint_priority" and not raw:
            baseline[key] = "NORMAL"
    baseline["actual_resolution_date"] = safe_date(get("actual_resolution_date"))
    return baseline


def build_dirty_patch(
    baseline: dict[str, Any],
    *,
    text_values: dict[str, Any],
    enum_values: dict[str, Any],
    date_modes: dict[str, str],
    date_values: dict[str, Optional[date]],
) -> dict[str, Any]:
    """
    Build RPC patch with only changed keys.
    Date modes: KEEP → omit; SET → date/None; CLEAR → null.
    """
    patch: dict[str, Any] = {}

    for key in UPDATE_TEXT_FIELDS:
        new_val = normalize_text_for_compare(text_values.get(key))
        old_val = baseline.get(key)
        if new_val != old_val:
            patch[key] = new_val

    for key in UPDATE_ENUM_FIELDS:
        new_raw = safe_str(enum_values.get(key)).upper()
        new_val = new_raw or None
        if key == "deadline_source" and not new_raw:
            new_val = None
        if key == "deadline_status" and not new_raw:
            new_val = "NOT_SET"
        if key == "constraint_priority" and not new_raw:
            new_val = "NORMAL"
        old_val = baseline.get(key)
        if new_val != old_val:
            patch[key] = new_val

    for key in UPDATE_DATE_FIELDS:
        mode = date_modes.get(key, DATE_MODE_KEEP)
        if mode == DATE_MODE_KEEP:
            continue
        if mode == DATE_MODE_CLEAR:
            if baseline.get(key) is not None:
                patch[key] = None
            continue
        # SET
        new_date = date_values.get(key)
        old_date = baseline.get(key)
        if new_date != old_date:
            patch[key] = new_date.isoformat() if new_date is not None else None

    return patch


def validate_update_submission(
    *,
    updated_by: Any,
    update_comment: Any,
    patch: dict[str, Any],
    baseline: dict[str, Any],
) -> Optional[str]:
    actor = safe_str(updated_by)
    comment = safe_str(update_comment)
    if not actor or actor in EMPTY_MARKERS:
        return "Укажите, кто обновил ограничение"
    if not comment or comment in EMPTY_MARKERS:
        return "Укажите комментарий обновления"

    occurred = patch.get("constraint_occurred_at", "__missing__")
    if occurred != "__missing__":
        new_occurred = safe_date(occurred) if occurred is not None else None
    else:
        new_occurred = baseline.get("constraint_occurred_at")
    actual = baseline.get("actual_resolution_date")
    if new_occurred is not None and actual is not None and new_occurred > actual:
        return "Дата возникновения не может быть позже фактической даты устранения"
    return None


def format_field_label(field: str) -> str:
    labels = {
        "constraint_occurred_at": "Дата возникновения",
        "problem_owner": "Владелец проблемы",
        "owner_name": "Исполнитель устранения",
        "subcontractor_coordinator": "Координатор",
        "constraint_category": "Категория",
        "constraint_priority": "Приоритет",
        "problem_description": "Описание проблемы",
        "problem_impact": "Последствия",
        "required_action": "Требуемое действие",
        "deadline_status": "Статус срока",
        "deadline_source": "Источник срока",
        "target_resolution_date": "Плановая дата",
        "next_control_date": "Следующий контроль",
    }
    return labels.get(field, field)


def format_value_for_history(field: str, value: Any) -> str:
    if value is None or safe_str(value) in EMPTY_MARKERS:
        return "∅"
    if field in UPDATE_DATE_FIELDS or field.endswith("_date"):
        return format_date_ru(value)
    if field == "deadline_status":
        return display_deadline_status(value)
    if field == "deadline_source":
        return display_deadline_source(value)
    if field == "constraint_priority":
        return display_constraint_priority(value)
    return safe_str(value)


def format_updated_event_lines(event_payload: Any) -> list[str]:
    parsed = parse_constraint_event_payload(event_payload)
    lines: list[str] = []
    changed = parsed.get("changed_fields") or []
    old_values = parsed.get("old_values") or {}
    new_values = parsed.get("new_values") or {}
    if not changed:
        return ["Изменённые поля не указаны в payload"]
    for field in changed:
        key = str(field)
        old_v = format_value_for_history(key, old_values.get(key))
        new_v = format_value_for_history(key, new_values.get(key))
        lines.append(f"{format_field_label(key)}: {old_v} → {new_v}")
    return lines


def can_edit_constraint(resolution_status: Any) -> bool:
    return safe_str(resolution_status).upper() in OPEN_RESOLUTIONS


def update_form_prefix(constraint_id: str) -> str:
    return f"reg_upd_{constraint_id}"


# ---------------------------------------------------------------------------
# Display / filters
# ---------------------------------------------------------------------------


def _style_status_cell(styles: dict[str, str], value: Any) -> str:
    return styles.get(str(value).strip(), "")


def style_registry_display(df: pd.DataFrame):
    styler = df.style

    def style_check(val: Any) -> str:
        return _style_status_cell(CHECK_STATUS_BG, val)

    def style_resolution(val: Any) -> str:
        return _style_status_cell(RESOLUTION_STATUS_BG, val)

    check_col = "Статус проверки"
    res_col = "Статус устранения"
    if check_col in df.columns:
        if hasattr(styler, "map"):
            styler = styler.map(style_check, subset=pd.IndexSlice[:, [check_col]])
        else:
            styler = styler.applymap(style_check, subset=pd.IndexSlice[:, [check_col]])
    if res_col in df.columns:
        if hasattr(styler, "map"):
            styler = styler.map(style_resolution, subset=pd.IndexSlice[:, [res_col]])
        else:
            styler = styler.applymap(
                style_resolution, subset=pd.IndexSlice[:, [res_col]]
            )
    return styler


def unique_sorted(series: pd.Series) -> list[str]:
    values = {safe_str(v) for v in series.dropna().tolist() if safe_str(v)}
    return sorted(values)


def apply_filters(
    df: pd.DataFrame,
    *,
    project: str,
    month: str,
    facility: str,
    discipline: str,
    department: str,
    check_status: str,
    resolution_status: str,
    open_mode: str,
    search: str,
    problem_owner: str = ALL,
    owner_name: str = ALL,
    coordinator: str = ALL,
    priority: str = ALL,
    effective_deadline_status: str = ALL,
    deadline_overdue_only: bool = False,
    next_control_overdue_only: bool = False,
) -> pd.DataFrame:
    if df.empty:
        return df

    result = df.copy()

    if project != ALL and "project_code" in result.columns:
        result = result[result["project_code"].astype(str) == project]
    if month != ALL and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month]
    if facility != ALL and "facility_building" in result.columns:
        result = result[result["facility_building"].astype(str) == facility]
    if discipline != ALL and "construction_discipline" in result.columns:
        result = result[result["construction_discipline"].astype(str) == discipline]
    if department != ALL and "responsible_department" in result.columns:
        result = result[result["responsible_department"].astype(str) == department]
    if check_status != ALL and "check_status" in result.columns:
        result = result[
            result["check_status"].astype(str).str.strip().str.upper()
            == check_status.strip().upper()
        ]
    if resolution_status != ALL and "resolution_status" in result.columns:
        result = result[
            result["resolution_status"].astype(str).str.strip().str.upper()
            == resolution_status.strip().upper()
        ]
    if open_mode == OPEN_ONLY and "resolution_status" in result.columns:
        res = result["resolution_status"].astype(str).str.strip().str.upper()
        result = result[res.isin(OPEN_RESOLUTIONS)]

    if problem_owner != ALL and "problem_owner" in result.columns:
        result = result[result["problem_owner"].map(safe_str) == problem_owner]
    if owner_name != ALL and "owner_name" in result.columns:
        result = result[result["owner_name"].map(safe_str) == owner_name]
    if coordinator != ALL and "subcontractor_coordinator" in result.columns:
        result = result[
            result["subcontractor_coordinator"].map(safe_str) == coordinator
        ]
    if priority != ALL and "constraint_priority" in result.columns:
        result = result[
            result["constraint_priority"].astype(str).str.strip().str.upper()
            == priority.strip().upper()
        ]
    if effective_deadline_status != ALL and "effective_deadline_status" in result.columns:
        result = result[
            result["effective_deadline_status"].astype(str).str.strip().str.upper()
            == effective_deadline_status.strip().upper()
        ]
    if deadline_overdue_only and "is_deadline_overdue" in result.columns:
        result = result[result["is_deadline_overdue"].fillna(False).astype(bool)]
    if next_control_overdue_only and "is_next_control_overdue" in result.columns:
        result = result[result["is_next_control_overdue"].fillna(False).astype(bool)]

    q = search.strip().lower()
    if q:
        boq = (
            result["boq_code"].astype(str).str.lower()
            if "boq_code" in result.columns
            else pd.Series("", index=result.index)
        )
        name = (
            result["boq_name"].astype(str).str.lower()
            if "boq_name" in result.columns
            else pd.Series("", index=result.index)
        )
        result = result[boq.str.contains(q, na=False) | name.str.contains(q, na=False)]

    return result


def sort_registry_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    result["_sort_block"] = (
        (~result["is_blocking"].fillna(False).astype(bool)).astype(int)
        if "is_blocking" in result.columns
        else 1
    )
    result["_sort_open"] = (
        (~result["is_open"].fillna(False).astype(bool)).astype(int)
        if "is_open" in result.columns
        else 1
    )
    delay_col = (
        "deadline_days_overdue"
        if "deadline_days_overdue" in result.columns
        else "delay_days"
    )
    result["_sort_delay"] = (
        -pd.to_numeric(result[delay_col], errors="coerce").fillna(0)
        if delay_col in result.columns
        else 0
    )
    result["_sort_created"] = pd.to_datetime(
        result["constraint_created_at"] if "constraint_created_at" in result.columns else None,
        errors="coerce",
    )
    result = result.sort_values(
        by=["_sort_block", "_sort_open", "_sort_delay", "_sort_created"],
        ascending=[True, True, True, False],
        kind="mergesort",
    )
    return result.drop(columns=[c for c in result.columns if c.startswith("_sort_")])


def build_display_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[label for _, label, _ in TABLE_COLUMNS])

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        risk = row.get("value_at_risk")
        if risk is None or (isinstance(risk, float) and pd.isna(risk)):
            risk = row.get("plan_value")
        days_real = row.get("days_open_real")
        if days_real is None or (isinstance(days_real, float) and pd.isna(days_real)):
            days_real = row.get("days_open")
        rows.append(
            {
                "Проект": display_dash(row.get("project_code")),
                "Месяц": display_dash(row.get("month_key")),
                "Дата фиксации": format_date_ru(row.get("constraint_created_at")),
                "Дата возникновения": format_date_author_empty(
                    row.get("constraint_occurred_at")
                ),
                "Очередь": display_dash(row.get("queue")),
                "Титул": display_dash(row.get("facility_building")),
                "Дисциплина": display_dash(row.get("construction_discipline")),
                "BOQ-код": display_dash(row.get("boq_code")),
                "Наименование работ": display_dash(row.get("boq_name")),
                "Пакет работ / IWP": display_dash(
                    row.get("work_package") or row.get("iwp")
                ),
                "Система": display_dash(row.get("system")),
                "Ед. изм.": display_dash(row.get("unit")),
                "Плановый объём": qty_ru(row.get("planned_qty")),
                "Плановая стоимость": money_ru(row.get("plan_value")),
                "Отдел": display_dash(row.get("responsible_department")),
                "Статус проверки": display_check_status(row.get("check_status")),
                "Статус устранения": display_resolution_status(
                    row.get("resolution_status")
                ),
                "Тип ограничения": display_dash(row.get("constraint_category")),
                "Приоритет": display_constraint_priority(row.get("constraint_priority")),
                "Суть проблемы": display_dash(row.get("problem_summary")),
                "Владелец проблемы": display_author_empty(row.get("problem_owner")),
                "Исполнитель устранения": display_author_empty(row.get("owner_name")),
                "Координатор": display_author_empty(
                    row.get("subcontractor_coordinator")
                ),
                "Требуемое действие": display_author_empty(row.get("required_action")),
                "Статус срока": display_deadline_status(row.get("deadline_status")),
                "Эффективный статус срока": display_deadline_status(
                    row.get("effective_deadline_status")
                ),
                "Плановая дата устранения": format_date_author_empty(
                    row.get("target_resolution_date")
                ),
                "Следующий контроль": format_date_author_empty(
                    row.get("next_control_date")
                ),
                "Фактическая дата устранения": format_date_ru(
                    row.get("actual_resolution_date")
                ),
                "Дней открыто (real)": int(safe_num(days_real)),
                "Задержка, дней": int(
                    safe_num(
                        row.get("deadline_days_overdue")
                        if row.get("deadline_days_overdue") is not None
                        else row.get("delay_days")
                    )
                ),
                "Стоимость под риском": money_ru(risk),
                "Примечание": truncate_comment(row.get("comment")),
                "Кто снял": display_dash(row.get("resolved_by")),
                "Дата последнего действия": format_date_ru(row.get("last_action_at")),
            }
        )
    return pd.DataFrame(rows)


def build_column_config() -> dict[str, Any]:
    config: dict[str, Any] = {}
    wide = {
        "Наименование работ",
        "Суть проблемы",
        "Требуемое действие",
        "Примечание",
        "Титул",
        "Пакет работ / IWP",
        "Дата последнего действия",
    }
    for _, label, width in TABLE_COLUMNS:
        if label in {"Задержка, дней", "Дней открыто (real)"}:
            config[label] = st.column_config.NumberColumn(label, width=width, format="%d")
        else:
            config[label] = st.column_config.TextColumn(
                label,
                width=width if label in wide or width >= 180 else width,
            )
    return config


def hydrate_update_form_session(constraint_id: str, row: pd.Series) -> dict[str, Any]:
    """Hydrate widget defaults only when selected constraint changes."""
    baseline = extract_update_baseline(row)
    active = safe_str(st.session_state.get("reg_upd_active_cid"))
    prefix = update_form_prefix(constraint_id)
    if active == constraint_id and st.session_state.get(f"{prefix}__baseline") is not None:
        return st.session_state[f"{prefix}__baseline"]

    st.session_state["reg_upd_active_cid"] = constraint_id
    st.session_state[f"{prefix}__baseline"] = baseline

    for key in UPDATE_TEXT_FIELDS:
        st.session_state[f"{prefix}_{key}"] = baseline.get(key) or ""
    for key, options in UPDATE_ENUM_FIELDS.items():
        current = baseline.get(key)
        if key == "deadline_source":
            st.session_state[f"{prefix}_{key}"] = current if current in options else ""
        elif current in options:
            st.session_state[f"{prefix}_{key}"] = current
        else:
            st.session_state[f"{prefix}_{key}"] = options[0]
    for key in UPDATE_DATE_FIELDS:
        st.session_state[f"{prefix}_{key}_mode"] = DATE_MODE_KEEP
        st.session_state[f"{prefix}_{key}_value"] = baseline.get(key) or date.today()
    if f"{prefix}_updated_by" not in st.session_state:
        st.session_state[f"{prefix}_updated_by"] = st.session_state.get(
            "reg_last_updated_by", ""
        )
    st.session_state[f"{prefix}_update_comment"] = ""
    return baseline


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("РЕЕСТР ОГРАНИЧЕНИЙ ДОПУСКА МЕСЯЧНОГО ПЛАНА")
st.caption(
    "Рабочий реестр ограничений, выявленных отделами при допуске BOQ-кодов в месячный план."
)

try:
    with st.spinner("Загрузка реестра ограничений…"):
        full_df = load_constraint_registry()
except Exception as exc:  # noqa: BLE001
    st.error(f"Не удалось загрузить реестр ограничений: {exc}")
    st.stop()

if full_df is None or full_df.empty:
    st.info("В реестре пока нет ограничений.")
    st.stop()

projects = unique_sorted(full_df["project_code"]) if "project_code" in full_df.columns else []
months_all = unique_sorted(full_df["month_key"]) if "month_key" in full_df.columns else []

default_project = projects[0] if projects else ALL
default_month = "август-2026" if "август-2026" in months_all else (months_all[0] if months_all else ALL)

if "reg_project" not in st.session_state:
    st.session_state["reg_project"] = default_project
if "reg_month" not in st.session_state:
    st.session_state["reg_month"] = default_month
if "reg_open_mode" not in st.session_state:
    st.session_state["reg_open_mode"] = OPEN_ONLY

if st.session_state["reg_project"] not in projects and projects:
    st.session_state["reg_project"] = default_project
if st.session_state["reg_month"] not in months_all and months_all:
    st.session_state["reg_month"] = default_month

f1, f2, f3, f4 = st.columns(4)
with f1:
    project = st.selectbox("Проект", options=projects or [ALL], key="reg_project")
with f2:
    month = st.selectbox("Месяц", options=months_all or [ALL], key="reg_month")
with f3:
    open_mode = st.selectbox(
        "Режим",
        options=[OPEN_ONLY, MODE_ALL],
        key="reg_open_mode",
    )
with f4:
    search = st.text_input(
        "Поиск по BOQ-коду или наименованию",
        value="",
        key="reg_search",
    )

scoped = full_df
if project != ALL and "project_code" in scoped.columns:
    scoped = scoped[scoped["project_code"].astype(str) == project]
if month != ALL and "month_key" in scoped.columns:
    scoped = scoped[scoped["month_key"].astype(str) == month]

facilities = [ALL] + (
    unique_sorted(scoped["facility_building"])
    if "facility_building" in scoped.columns
    else []
)
disciplines = [ALL] + (
    unique_sorted(scoped["construction_discipline"])
    if "construction_discipline" in scoped.columns
    else []
)
departments = [ALL] + (
    unique_sorted(scoped["responsible_department"])
    if "responsible_department" in scoped.columns
    else []
)
problem_owners = [ALL] + (
    unique_sorted(scoped["problem_owner"]) if "problem_owner" in scoped.columns else []
)
executors = [ALL] + (
    unique_sorted(scoped["owner_name"]) if "owner_name" in scoped.columns else []
)
coordinators = [ALL] + (
    unique_sorted(scoped["subcontractor_coordinator"])
    if "subcontractor_coordinator" in scoped.columns
    else []
)
priorities = [ALL] + list(CONSTRAINT_PRIORITY_DISPLAY.keys())
eff_deadline_opts = [ALL] + list(DEADLINE_STATUS_DISPLAY.keys())

for key, options in (
    ("reg_facility", facilities),
    ("reg_discipline", disciplines),
    ("reg_department", departments),
    ("reg_problem_owner", problem_owners),
    ("reg_executor", executors),
    ("reg_coordinator", coordinators),
    ("reg_priority", priorities),
    ("reg_eff_deadline", eff_deadline_opts),
):
    if st.session_state.get(key) not in options:
        st.session_state[key] = ALL

f5, f6, f7, f8 = st.columns(4)
with f5:
    facility = st.selectbox("Титул", options=facilities, key="reg_facility")
with f6:
    discipline = st.selectbox("Дисциплина", options=disciplines, key="reg_discipline")
with f7:
    department = st.selectbox("Отдел", options=departments, key="reg_department")
with f8:
    check_status = st.selectbox(
        "Статус проверки",
        options=[ALL] + CHECK_STATUS_OPTIONS,
        format_func=format_check_filter_option,
        key="reg_check_status",
    )

f9, f10, f11, f12 = st.columns(4)
with f9:
    resolution_status = st.selectbox(
        "Статус устранения",
        options=[ALL] + RESOLUTION_STATUS_OPTIONS,
        format_func=format_resolution_filter_option,
        key="reg_resolution_status",
        disabled=(open_mode == OPEN_ONLY),
    )
with f10:
    problem_owner_f = st.selectbox(
        "Владелец проблемы",
        options=problem_owners,
        key="reg_problem_owner",
    )
with f11:
    owner_name_f = st.selectbox(
        "Исполнитель устранения",
        options=executors,
        key="reg_executor",
    )
with f12:
    coordinator_f = st.selectbox(
        "Координатор",
        options=coordinators,
        key="reg_coordinator",
    )

f13, f14, f15, f16 = st.columns(4)
with f13:
    priority_f = st.selectbox(
        "Приоритет",
        options=priorities,
        format_func=lambda x: ALL if x == ALL else display_constraint_priority(x),
        key="reg_priority",
    )
with f14:
    eff_deadline_f = st.selectbox(
        "Эффективный статус срока",
        options=eff_deadline_opts,
        format_func=lambda x: ALL if x == ALL else display_deadline_status(x),
        key="reg_eff_deadline",
    )
with f15:
    deadline_overdue_only = st.checkbox(
        "Только просрочка срока",
        value=False,
        key="reg_deadline_overdue",
    )
with f16:
    next_control_overdue_only = st.checkbox(
        "Только просрочка контроля",
        value=False,
        key="reg_next_control_overdue",
    )

st.caption("Выберите строку в таблице → карточка, обновление и снятие ниже")

filtered = apply_filters(
    full_df,
    project=project,
    month=month,
    facility=facility,
    discipline=discipline,
    department=department,
    check_status=check_status,
    resolution_status=resolution_status if open_mode != OPEN_ONLY else ALL,
    open_mode=open_mode,
    search=search,
    problem_owner=problem_owner_f,
    owner_name=owner_name_f,
    coordinator=coordinator_f,
    priority=priority_f,
    effective_deadline_status=eff_deadline_f,
    deadline_overdue_only=deadline_overdue_only,
    next_control_overdue_only=next_control_overdue_only,
)
filtered = sort_registry_rows(filtered)
kpi = build_registry_summary(filtered)

success_payload = st.session_state.pop("reg_resolve_success", None)
if isinstance(success_payload, dict):
    st.success("Ограничение снято")
    new_check = display_check_status(success_payload.get("new_check_status"))
    new_res = display_resolution_status(success_payload.get("new_resolution_status"))
    line_summary = success_payload.get("line_summary") or {}
    if not isinstance(line_summary, dict):
        line_summary = {}
    outcome = safe_str(
        line_summary.get("admission_outcome") or success_payload.get("admission_outcome")
    ).upper()
    blockers = success_payload.get("remaining_blockers") or []
    if not isinstance(blockers, list):
        blockers = []
    st.write(f"Новый статус ограничения: **{new_check}** / **{new_res}**")
    st.write(
        f"Итог по BOQ (admission_outcome): **{outcome or '—'}** · "
        f"оставшихся blockers: **{len(blockers)}**"
    )
    outcome_msg = ADMISSION_OUTCOME_MESSAGES.get(outcome)
    if outcome_msg:
        st.info(outcome_msg)

update_success = st.session_state.pop("reg_update_success", None)
if isinstance(update_success, dict):
    changed = update_success.get("changed_fields") or []
    st.success(
        f"Ограничение обновлено · изменено полей: {len(changed) if isinstance(changed, list) else changed}"
    )

update_info = st.session_state.pop("reg_update_info", None)
if update_info:
    st.info(str(update_info))

update_error = st.session_state.pop("reg_update_error", None)
if update_error:
    st.error(str(update_error))

resolve_error = st.session_state.pop("reg_resolve_error", None)
if resolve_error:
    st.error(str(resolve_error))

st.markdown("### Показатели")
st.caption("Слой 1 · Ограничения (по constraint_id)")
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("Всего ограничений", kpi["constraints_total"])
k2.metric("Открытых", kpi["constraints_open"])
k3.metric("HOLD", kpi["constraints_hold"])
k4.metric("FAIL", kpi["constraints_fail"])
k5.metric("WARNING", kpi["constraints_warning"])
k6.metric("Просроченных", kpi["constraints_overdue"])
k7.metric("Снятых", kpi["constraints_resolved"])

st.caption("Слой 2 · BOQ под ограничениями (уникальный plan_line_id)")
b1, b2, b3, b4, b5, b6 = st.columns(6)
b1.metric("BOQ под ограничением", kpi["boq_under_constraint_count"])
b2.metric("Стоимость BOQ под риском", money_ru(kpi["boq_cost_at_risk"]))
b3.metric("Уникальных титулов", kpi["unique_facility_count"])
b4.metric("Уникальных дисциплин", kpi["unique_discipline_count"])
b5.metric("Уникальных систем", kpi["unique_system_count"])
b6.metric("Уникальных IWP", kpi["unique_iwp_count"])

st.markdown("### Реестр")
st.caption(f"Строк в таблице: {len(filtered)} · выберите одну строку")

selected_constraint_id: Optional[str] = None

if filtered.empty:
    st.info("По выбранным фильтрам ограничений нет.")
else:
    display_df = build_display_table(filtered).reset_index(drop=True)
    filtered_indexed = filtered.reset_index(drop=True)

    table_state = st.dataframe(
        style_registry_display(display_df),
        use_container_width=True,
        hide_index=True,
        height=560,
        column_config=build_column_config(),
        on_select="rerun",
        selection_mode="single-row",
        key="reg_dataframe",
    )

    selected_rows: list[int] = []
    try:
        selected_rows = list(table_state.selection.rows or [])
    except Exception:  # noqa: BLE001
        selected_rows = []

    if selected_rows:
        row_idx = int(selected_rows[0])
        if 0 <= row_idx < len(filtered_indexed):
            selected_constraint_id = safe_str(
                filtered_indexed.iloc[row_idx].get("constraint_id")
            )
            st.session_state["reg_selected_constraint_id"] = selected_constraint_id

    id_labels: dict[str, str] = {}
    for _, row in filtered_indexed.iterrows():
        cid = safe_str(row.get("constraint_id"))
        if not cid:
            continue
        reason = safe_str(row.get("problem_summary")) or safe_str(row.get("block_reason"))
        if len(reason) > 60:
            reason = reason[:57] + "…"
        id_labels[cid] = (
            f"{safe_str(row.get('boq_code'))} · "
            f"{safe_str(row.get('responsible_department'))} · "
            f"{display_check_status(row.get('check_status'))} · "
            f"{reason or '—'} · "
            f"{cid[:8]}"
        )

    label_options = ["— не выбрано —"] + list(id_labels.values())
    label_to_id = {v: k for k, v in id_labels.items()}
    current_id = safe_str(
        selected_constraint_id or st.session_state.get("reg_selected_constraint_id")
    )
    default_label = id_labels.get(current_id, "— не выбрано —")
    if default_label not in label_options:
        default_label = "— не выбрано —"

    if selected_rows and current_id in id_labels:
        st.session_state["reg_constraint_picker"] = id_labels[current_id]
    elif st.session_state.get("reg_constraint_picker") not in label_options:
        st.session_state["reg_constraint_picker"] = default_label

    pick_label = st.selectbox(
        "Выбранное ограничение (по constraint_id)",
        options=label_options,
        key="reg_constraint_picker",
        help="Точный выбор по constraint_id. Не по BOQ-коду.",
    )
    if pick_label != "— не выбрано —":
        selected_constraint_id = label_to_id.get(pick_label)
        if selected_constraint_id:
            st.session_state["reg_selected_constraint_id"] = selected_constraint_id
    else:
        selected_constraint_id = None
        st.session_state.pop("reg_selected_constraint_id", None)

selected_row: Optional[pd.Series] = None
if selected_constraint_id:
    matches = full_df[full_df["constraint_id"].astype(str) == selected_constraint_id]
    if not matches.empty:
        selected_row = matches.iloc[0]
    else:
        st.warning("Выбранное ограничение не найдено в текущей загрузке реестра.")
        selected_constraint_id = None

if selected_row is not None and selected_constraint_id:
    st.markdown("### Карточка ограничения")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"**constraint_id:** `{selected_constraint_id}`")
        st.markdown(f"**Проект:** {display_dash(selected_row.get('project_code'))}")
        st.markdown(f"**Месяц:** {display_dash(selected_row.get('month_key'))}")
        st.markdown(f"**Титул:** {display_dash(selected_row.get('facility_building'))}")
        st.markdown(
            f"**Дисциплина:** {display_dash(selected_row.get('construction_discipline'))}"
        )
        st.markdown(f"**BOQ-код:** {display_dash(selected_row.get('boq_code'))}")
        st.markdown(
            f"**Наименование работ:** {display_dash(selected_row.get('boq_name'))}"
        )
    with c2:
        st.markdown(
            f"**Отдел:** {display_dash(selected_row.get('responsible_department'))}"
        )
        st.markdown(f"**Проверка:** {display_dash(selected_row.get('check_name'))}")
        st.markdown(
            f"**Статус проверки:** {display_check_status(selected_row.get('check_status'))}"
        )
        st.markdown(
            f"**Статус устранения:** {display_resolution_status(selected_row.get('resolution_status'))}"
        )
        st.markdown(
            f"**Категория:** {display_author_empty(selected_row.get('constraint_category'))}"
        )
        st.markdown(
            f"**Приоритет:** {display_constraint_priority(selected_row.get('constraint_priority'))}"
        )
        st.markdown(
            f"**Суть проблемы:** {display_dash(selected_row.get('problem_summary'))}"
        )
    with c3:
        st.markdown(
            f"**Дата возникновения:** {format_date_author_empty(selected_row.get('constraint_occurred_at'))}"
        )
        st.markdown(
            f"**Дата регистрации:** {format_date_ru(selected_row.get('constraint_created_at'))}"
        )
        st.markdown(
            f"**Дней открыто (real):** {int(safe_num(selected_row.get('days_open_real') if selected_row.get('days_open_real') is not None else selected_row.get('days_open')))}"
        )
        st.markdown(
            f"**Владелец проблемы:** {display_author_empty(selected_row.get('problem_owner'))}"
        )
        st.markdown(
            f"**Исполнитель устранения:** {display_author_empty(selected_row.get('owner_name'))}"
        )
        st.markdown(
            f"**Координатор:** {display_author_empty(selected_row.get('subcontractor_coordinator'))}"
        )
    with c4:
        st.markdown(
            f"**Описание:** {display_author_empty(selected_row.get('problem_description'))}"
        )
        st.markdown(
            f"**Последствия:** {display_author_empty(selected_row.get('problem_impact'))}"
        )
        st.markdown(
            f"**Требуемое действие:** {display_author_empty(selected_row.get('required_action'))}"
        )
        st.markdown(
            f"**Статус срока:** {display_deadline_status(selected_row.get('deadline_status'))}"
        )
        st.markdown(
            f"**Эффективный статус срока:** {display_deadline_status(selected_row.get('effective_deadline_status'))}"
        )
        st.markdown(
            f"**Источник срока:** {display_deadline_source(selected_row.get('deadline_source'))}"
        )
        st.markdown(
            f"**Плановая дата:** {format_date_author_empty(selected_row.get('target_resolution_date'))}"
        )
        st.markdown(
            f"**Следующий контроль:** {format_date_author_empty(selected_row.get('next_control_date'))}"
        )
        overdue_flag = bool(selected_row.get("is_deadline_overdue"))
        control_flag = bool(selected_row.get("is_next_control_overdue"))
        st.markdown(
            f"**Просрочка срока:** {'Да' if overdue_flag else 'Нет'} "
            f"({int(safe_num(selected_row.get('deadline_days_overdue') if selected_row.get('deadline_days_overdue') is not None else selected_row.get('delay_days')))} дн.)"
        )
        st.markdown(f"**Просрочка контроля:** {'Да' if control_flag else 'Нет'}")
        risk = selected_row.get("value_at_risk")
        if risk is None or (isinstance(risk, float) and pd.isna(risk)):
            risk = selected_row.get("plan_value")
        st.markdown(f"**Стоимость под риском:** {money_ru(risk)}")

    st.markdown("**Последний комментарий**")
    st.text(display_dash(selected_row.get("comment")))

    resolution_now = safe_str(selected_row.get("resolution_status")).upper()
    can_update = can_edit_constraint(resolution_now)
    can_resolve = can_update

    # ------------------------------------------------------------------
    # Update form
    # ------------------------------------------------------------------
    st.markdown("### Обновить ограничение")
    if not can_update:
        st.info(
            f"Обновление недоступно для статуса {display_resolution_status(resolution_now)}. "
            "Редактируются только OPEN / IN_PROGRESS."
        )
    else:
        baseline = hydrate_update_form_session(selected_constraint_id, selected_row)
        prefix = update_form_prefix(selected_constraint_id)
        category_options = unique_sorted(
            full_df["constraint_category"]
            if "constraint_category" in full_df.columns
            else pd.Series(dtype=object)
        )
        with st.form(f"{prefix}_form", clear_on_submit=False):
            u1, u2 = st.columns(2)
            with u1:
                problem_owner_v = st.text_input(
                    "Владелец проблемы",
                    key=f"{prefix}_problem_owner",
                    help="Чья зона ответственности или кто создал ограничение",
                )
                owner_name_v = st.text_input(
                    "Исполнитель устранения",
                    key=f"{prefix}_owner_name",
                    help="Кто должен фактически выдать решение, поставить МТР, выпустить РД или устранить проблему",
                )
                coordinator_v = st.text_input(
                    "Координатор от субподрядчика",
                    key=f"{prefix}_subcontractor_coordinator",
                    help="Кто сопровождает вопрос, контролирует срок и эскалирует",
                )
                category_v = st.text_input(
                    "Категория ограничения",
                    key=f"{prefix}_constraint_category",
                    help="Свободный текст. Примеры live: "
                    + (", ".join(category_options[:8]) if category_options else "—"),
                )
                priority_v = st.selectbox(
                    "Приоритет",
                    options=UPDATE_ENUM_FIELDS["constraint_priority"],
                    format_func=display_constraint_priority,
                    key=f"{prefix}_constraint_priority",
                )
            with u2:
                deadline_status_v = st.selectbox(
                    "Статус срока",
                    options=UPDATE_ENUM_FIELDS["deadline_status"],
                    format_func=display_deadline_status,
                    key=f"{prefix}_deadline_status",
                )
                source_options = [""] + UPDATE_ENUM_FIELDS["deadline_source"]
                deadline_source_v = st.selectbox(
                    "Источник срока",
                    options=source_options,
                    format_func=lambda x: "— не указан —"
                    if x == ""
                    else display_deadline_source(x),
                    key=f"{prefix}_deadline_source",
                )
                required_action_v = st.text_area(
                    "Требуемое действие",
                    key=f"{prefix}_required_action",
                    height=80,
                )
                problem_description_v = st.text_area(
                    "Подробное описание проблемы",
                    key=f"{prefix}_problem_description",
                    height=80,
                )
                problem_impact_v = st.text_area(
                    "Последствия",
                    key=f"{prefix}_problem_impact",
                    height=80,
                )

            st.markdown("**Даты**")
            d1, d2, d3 = st.columns(3)
            date_modes: dict[str, str] = {}
            date_values: dict[str, Optional[date]] = {}
            date_labels = {
                "constraint_occurred_at": "Дата возникновения ограничения",
                "target_resolution_date": "Плановая дата устранения",
                "next_control_date": "Дата следующего контроля",
            }
            for col, field in zip((d1, d2, d3), UPDATE_DATE_FIELDS):
                with col:
                    mode = st.radio(
                        date_labels[field],
                        options=DATE_MODES,
                        key=f"{prefix}_{field}_mode",
                        horizontal=False,
                    )
                    date_modes[field] = mode
                    if mode == DATE_MODE_SET:
                        date_values[field] = st.date_input(
                            f"Значение · {date_labels[field]}",
                            key=f"{prefix}_{field}_value",
                        )
                    else:
                        date_values[field] = None
                        st.caption(
                            f"Сейчас в карточке: {format_date_author_empty(baseline.get(field))}"
                        )

            updated_by_v = st.text_input(
                "Кто обновил",
                key=f"{prefix}_updated_by",
            )
            update_comment_v = st.text_area(
                "Комментарий обновления",
                key=f"{prefix}_update_comment",
                height=90,
            )

            text_values = {
                "problem_owner": problem_owner_v,
                "owner_name": owner_name_v,
                "subcontractor_coordinator": coordinator_v,
                "constraint_category": category_v,
                "problem_description": problem_description_v,
                "problem_impact": problem_impact_v,
                "required_action": required_action_v,
            }
            enum_values = {
                "constraint_priority": priority_v,
                "deadline_status": deadline_status_v,
                "deadline_source": deadline_source_v,
            }
            preview_patch = build_dirty_patch(
                baseline,
                text_values=text_values,
                enum_values=enum_values,
                date_modes=date_modes,
                date_values=date_values,
            )
            st.caption(f"Будет изменено полей: {len(preview_patch)}")
            submitted_update = st.form_submit_button(
                "Сохранить обновление",
                type="primary",
            )

        if submitted_update:
            patch = build_dirty_patch(
                baseline,
                text_values=text_values,
                enum_values=enum_values,
                date_modes=date_modes,
                date_values=date_values,
            )
            if not patch:
                st.session_state["reg_update_info"] = "Изменений нет"
                st.rerun()
            else:
                err = validate_update_submission(
                    updated_by=updated_by_v,
                    update_comment=update_comment_v,
                    patch=patch,
                    baseline=baseline,
                )
                if err:
                    st.session_state["reg_update_error"] = err
                    st.rerun()
                else:
                    st.session_state["reg_last_updated_by"] = safe_str(updated_by_v)
                    with st.spinner("Сохранение обновления…"):
                        result = update_constraint(
                            constraint_id=selected_constraint_id,
                            updated_by=updated_by_v,
                            update_comment=update_comment_v,
                            patch=patch,
                        )
                    clear_registry_read_caches()
                    if result.get("ok"):
                        status = safe_str(result.get("status"))
                        if status == "no_changes":
                            st.session_state["reg_update_info"] = "Изменений нет"
                        else:
                            st.session_state["reg_update_success"] = result.get("data") or {}
                            # force rehydrate from DB on next load
                            st.session_state.pop("reg_upd_active_cid", None)
                        st.rerun()
                    else:
                        st.session_state["reg_update_error"] = (
                            result.get("error") or "Не удалось обновить ограничение"
                        )
                        st.rerun()

    # ------------------------------------------------------------------
    # Resolve form (unchanged business logic)
    # ------------------------------------------------------------------
    if can_resolve:
        st.markdown("### Снять ограничение")
        confirm = st.checkbox(
            "Подтверждаю, что причина ограничения фактически устранена",
            value=False,
            key="reg_resolve_confirm",
        )
        with st.form("reg_resolve_form", clear_on_submit=False):
            actual_date = st.date_input(
                "Фактическая дата устранения",
                value=date.today(),
                key="reg_resolve_actual_date",
            )
            closed_by = st.text_input(
                "Кто закрывает",
                value="",
                key="reg_resolve_closed_by",
            )
            resolution_comment = st.text_area(
                "Комментарий об устранении",
                value="",
                height=120,
                key="reg_resolve_comment",
            )
            submitted = st.form_submit_button(
                "Подтвердить снятие ограничения",
                type="primary",
                disabled=not confirm,
            )

        if submitted:
            if not confirm:
                st.warning("Нужно подтверждение снятия ограничения.")
            elif not safe_str(closed_by):
                st.error("Укажите, кто закрывает ограничение.")
            elif not safe_str(resolution_comment):
                st.error("Укажите комментарий об устранении.")
            elif actual_date is None:
                st.error("Укажите фактическую дату устранения.")
            else:
                with st.spinner("Снятие ограничения…"):
                    result = resolve_constraint(
                        constraint_id=selected_constraint_id,
                        actual_resolution_date=actual_date,
                        resolution_comment=resolution_comment,
                        closed_by=closed_by,
                        evidence_payload=None,
                    )
                clear_constraint_registry_caches()
                if result.get("ok"):
                    st.session_state["reg_resolve_success"] = result.get("data") or {}
                    st.session_state.pop("reg_selected_constraint_id", None)
                    st.session_state.pop("reg_resolve_confirm", None)
                    st.rerun()
                else:
                    st.error(result.get("error") or "Не удалось снять ограничение")
    else:
        st.info(
            f"Ограничение уже закрыто ({resolution_now}). Форма снятия недоступна."
        )

    with st.expander("История событий ограничения", expanded=False):
        try:
            events_df = load_constraint_events(selected_constraint_id)
        except Exception as exc:  # noqa: BLE001
            st.warning(f"Не удалось загрузить историю событий: {exc}")
            events_df = pd.DataFrame()

        if events_df is None or events_df.empty:
            st.caption("История событий пока отсутствует")
        else:
            for _, ev in events_df.iterrows():
                ev_type = safe_str(ev.get("event_type")).upper()
                st.markdown(
                    f"**{ev_type or '—'}** · {format_datetime_ru(ev.get('performed_at'))} · "
                    f"{display_dash(ev.get('performed_by'))}"
                )
                st.caption(display_dash(ev.get("event_comment")))
                if ev_type == "UPDATED":
                    for line in format_updated_event_lines(ev.get("event_payload")):
                        st.write(f"- {line}")
                else:
                    st.write(
                        f"check: {display_dash(ev.get('old_check_status'))} → "
                        f"{display_dash(ev.get('new_check_status'))}; "
                        f"resolution: {display_dash(ev.get('old_resolution_status'))} → "
                        f"{display_dash(ev.get('new_resolution_status'))}"
                    )
                st.divider()
else:
    st.markdown("### Карточка ограничения")
    st.info(
        "Выберите строку в реестре, чтобы открыть карточку, форму обновления и снятия."
    )
