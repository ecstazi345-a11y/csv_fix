"""
Реестр ограничений допуска месячного плана — read-only UI (R1 Stage 3).

Источник: services.monthly_plan_constraint_registry_service
RPC закрытия / формы редактирования — не подключены.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pandas as pd
import streamlit as st

from services.monthly_plan_constraint_registry_service import (
    build_registry_summary,
    clear_constraint_registry_caches,
    load_constraint_events,
    load_constraint_registry,
    resolve_constraint,
)

st.set_page_config(layout="wide", page_title="Реестр ограничений допуска")

ALL = "Все"
OPEN_ONLY = "Только открытые"
MODE_ALL = "Все"
OPEN_RESOLUTIONS = frozenset({"OPEN", "IN_PROGRESS"})
CLOSED_RESOLUTIONS = frozenset({"RESOLVED", "CANCELLED"})

ADMISSION_OUTCOME_MESSAGES = {
    "READY": "BOQ допущен и доступен для включения в месячный паспорт",
    "READY_WITH_RISK": "Ограничение снято, но по BOQ остаются риски",
    "BLOCKED": "Ограничение снято, но по BOQ остаются блокирующие ограничения",
    "WAITING": "Ограничение снято, но BOQ ожидает проверки/решения других отделов",
}

CHECK_STATUS_OPTIONS = ["ОЖИДАЕТ", "PASS", "WARNING", "HOLD", "FAIL"]
RESOLUTION_STATUS_OPTIONS = ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"]

# Display-only labels (filters / DataFrame / DB keep technical values)
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

# Colors aligned with page 21 admission palette
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

EMPTY_AUTHOR = "Не заполнено автором"
COMMENT_TABLE_MAX_LEN = 80

TABLE_COLUMNS = [
    ("project_code", "Проект", 120),
    ("month_key", "Месяц", 110),
    ("constraint_created_at", "Дата фиксации", 110),
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
    ("problem_summary", "Суть проблемы", 280),
    ("problem_owner", "Владелец проблемы", 150),
    ("owner_name", "Ответственный", 140),
    ("required_action", "Требуемое действие", 220),
    ("target_resolution_date", "Плановая дата устранения", 130),
    ("actual_resolution_date", "Фактическая дата устранения", 130),
    ("delay_days", "Задержка, дней", 100),
    ("value_at_risk", "Стоимость под риском", 140),
    ("comment", "Примечание", 240),
    ("resolved_by", "Кто снял", 120),
    ("last_action_at", "Дата последнего действия", 200),
]


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
    """UI-only empty marker; never written to DB."""
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


def _style_status_cell(styles: dict[str, str], value: Any) -> str:
    return styles.get(str(value).strip(), "")


def style_registry_display(df: pd.DataFrame):
    """Color status columns only; display labels already applied."""
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


def risk_value(row: pd.Series) -> float:
    raw = row.get("value_at_risk")
    if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
        return safe_num(raw)
    return safe_num(row.get("plan_value"))


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
    result["_sort_delay"] = (
        -pd.to_numeric(result["delay_days"], errors="coerce").fillna(0)
        if "delay_days" in result.columns
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
        rows.append(
            {
                "Проект": display_dash(row.get("project_code")),
                "Месяц": display_dash(row.get("month_key")),
                "Дата фиксации": format_date_ru(row.get("constraint_created_at")),
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
                "Суть проблемы": display_dash(row.get("problem_summary")),
                "Владелец проблемы": display_author_empty(row.get("problem_owner")),
                "Ответственный": display_author_empty(row.get("owner_name")),
                "Требуемое действие": display_author_empty(row.get("required_action")),
                "Плановая дата устранения": format_date_author_empty(
                    row.get("target_resolution_date")
                ),
                "Фактическая дата устранения": format_date_ru(
                    row.get("actual_resolution_date")
                ),
                "Задержка, дней": int(safe_num(row.get("delay_days"))),
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
        if label == "Задержка, дней":
            config[label] = st.column_config.NumberColumn(label, width=width, format="%d")
        elif label == "Дата последнего действия":
            config[label] = st.column_config.TextColumn(
                "Дата последнего действия",
                width=width,
                help="Дата последнего действия по ограничению",
            )
        elif label == "Примечание":
            config[label] = st.column_config.TextColumn(
                label,
                width=width,
                help="В таблице — сокращённый текст; полный комментарий в карточке ниже",
            )
        else:
            config[label] = st.column_config.TextColumn(
                label,
                width=width if label in wide or width >= 180 else width,
            )
    return config


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

# Keep selectbox values valid after data changes
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

for key, options in (
    ("reg_facility", facilities),
    ("reg_discipline", disciplines),
    ("reg_department", departments),
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

f9, f10 = st.columns(2)
with f9:
    resolution_status = st.selectbox(
        "Статус устранения",
        options=[ALL] + RESOLUTION_STATUS_OPTIONS,
        format_func=format_resolution_filter_option,
        key="reg_resolution_status",
        disabled=(open_mode == OPEN_ONLY),
        help="В режиме «Только открытые» показываются OPEN и IN_PROGRESS (технические значения фильтра).",
    )
with f10:
    st.caption("Выберите строку в таблице → карточка и снятие ограничения ниже")

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
)
filtered = sort_registry_rows(filtered)
kpi = build_registry_summary(filtered)

# Success banner from previous resolve (before rerun reload)
success_payload = st.session_state.pop("reg_resolve_success", None)
if isinstance(success_payload, dict):
    st.success("Ограничение снято")
    new_check = display_check_status(success_payload.get("new_check_status"))
    new_res = display_resolution_status(success_payload.get("new_resolution_status"))
    line_summary = success_payload.get("line_summary") or {}
    if not isinstance(line_summary, dict):
        line_summary = {}
    outcome = safe_str(line_summary.get("admission_outcome") or success_payload.get("admission_outcome")).upper()
    blockers = success_payload.get("remaining_blockers") or []
    if not isinstance(blockers, list):
        blockers = []
    st.write(
        f"Новый статус ограничения: **{new_check}** / **{new_res}**"
    )
    st.write(
        f"Итог по BOQ (admission_outcome): **{outcome or '—'}** · "
        f"оставшихся blockers: **{len(blockers)}**"
    )
    outcome_msg = ADMISSION_OUTCOME_MESSAGES.get(outcome)
    if outcome_msg:
        st.info(outcome_msg)
    st.caption("BOQ не добавляется в паспорт автоматически — только доступен для контролируемого включения.")

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
    display_df = build_display_table(filtered)
    # Keep stable positional index for selection → constraint_id mapping
    display_df = display_df.reset_index(drop=True)
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

    # Fallback / explicit picker by exact constraint_id
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

    # Sync picker before widget creation (dataframe selection wins)
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

# Resolve selected row from full_df (fresh fields even if filtered mode changes)
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
    c1, c2, c3 = st.columns(3)
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
            f"**Суть проблемы:** {display_dash(selected_row.get('problem_summary'))}"
        )
        st.markdown(
            f"**Владелец проблемы:** {display_author_empty(selected_row.get('problem_owner'))}"
        )
        st.markdown(
            f"**Ответственный:** {display_author_empty(selected_row.get('owner_name'))}"
        )
    with c3:
        st.markdown(
            f"**Требуемое действие:** {display_author_empty(selected_row.get('required_action'))}"
        )
        st.markdown(
            f"**Плановая дата устранения:** {format_date_author_empty(selected_row.get('target_resolution_date'))}"
        )
        st.markdown(
            f"**Дата фиксации:** {format_date_ru(selected_row.get('constraint_created_at'))}"
        )
        st.markdown(
            f"**Дней открыто:** {int(safe_num(selected_row.get('days_open')))}"
        )
        risk = selected_row.get("value_at_risk")
        if risk is None or (isinstance(risk, float) and pd.isna(risk)):
            risk = selected_row.get("plan_value")
        st.markdown(f"**Стоимость под риском:** {money_ru(risk)}")
        st.markdown(
            f"**Evidence count:** {int(safe_num(selected_row.get('evidence_count')))}"
        )

    st.markdown("**Последний комментарий**")
    st.text(display_dash(selected_row.get("comment")))

    resolution_now = safe_str(selected_row.get("resolution_status")).upper()
    can_resolve = resolution_now not in CLOSED_RESOLUTIONS

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
                # Extra clear for page 21/23 helpers if already loaded
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
            hist = pd.DataFrame(
                {
                    "performed_at": [
                        format_datetime_ru(v)
                        for v in events_df.get(
                            "performed_at", pd.Series(dtype=object)
                        ).tolist()
                    ],
                    "event_type": events_df.get("event_type", pd.Series(dtype=object)).map(
                        display_dash
                    ),
                    "old_check_status": events_df.get(
                        "old_check_status", pd.Series(dtype=object)
                    ).map(display_dash),
                    "new_check_status": events_df.get(
                        "new_check_status", pd.Series(dtype=object)
                    ).map(display_dash),
                    "old_resolution_status": events_df.get(
                        "old_resolution_status", pd.Series(dtype=object)
                    ).map(display_dash),
                    "new_resolution_status": events_df.get(
                        "new_resolution_status", pd.Series(dtype=object)
                    ).map(display_dash),
                    "performed_by": events_df.get(
                        "performed_by", pd.Series(dtype=object)
                    ).map(display_dash),
                    "event_comment": events_df.get(
                        "event_comment", pd.Series(dtype=object)
                    ).map(display_dash),
                }
            )
            st.dataframe(
                hist,
                use_container_width=True,
                hide_index=True,
                height=min(280, 80 + 28 * max(len(hist), 1)),
            )
else:
    st.markdown("### Карточка ограничения")
    st.info("Выберите строку в реестре, чтобы открыть карточку и форму снятия.")
