from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from services.monthly_passport_service import create_monthly_passport
from services.supabase_client import supabase

st.set_page_config(layout="wide")

TABLE_CONSTRAINTS = "monthly_plan_constraints"
VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"
VIEW_DASHBOARD_V1 = "monthly_plan_constraints_dashboard_v1"

GATE_LAYER_RU = {
    "EXECUTABILITY": "Исполнимый фронт",
    "ACCEPTABILITY": "Признаваемость",
    "CREW_ECONOMICS": "Экономика звена",
}

CHECK_STATUS_RU = {
    "ОЖИДАЕТ": "Ожидает проверки",
    "PASS": "Пройдено",
    "WARNING": "Риск / требуется уточнение",
    "HOLD": "Удержание / блокировка",
    "FAIL": "Не пройдено",
}

RESOLUTION_RU = {
    "OPEN": "Открыто",
    "IN_PROGRESS": "В работе",
    "RESOLVED": "Закрыто",
    "CANCELLED": "Отменено",
}

CHECK_STATUS_OPTIONS = ["ОЖИДАЕТ", "PASS", "WARNING", "HOLD", "FAIL"]
RESOLUTION_OPTIONS = ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"]
OPEN_RESOLUTION = {"OPEN", "IN_PROGRESS"}

DEPARTMENT_RU = {
    "Участок": "Линейное управление / Field Construction Management",
    "ПТО": "ПТО / Engineering & Work Packaging",
    "МТО": "МТО / Procurement & Materials",
    "ОТиТБ": "HSE / ОТиПБ",
    "QAQC": "QA/QC",
    "Коммерческий отдел": "Коммерческий контроль / Contract & Commercial",
    "Руководство": "Проектное управление / Project Management",
}

CHECK_STATUS_BG_RU = {
    "Ожидает проверки": "background-color: #f3f4f6;",
    "Пройдено": "background-color: #dcfce7;",
    "Риск / требуется уточнение": "background-color: #fef9c3;",
    "Удержание / блокировка": "background-color: #ffedd5;",
    "Не пройдено": "background-color: #fee2e2;",
}

EMPTY_MSG = (
    "Ограничений пока нет. Сформируйте проверки на странице "
    "**Контур допуска месячного плана**."
)

TABLE_REVIEW_QUEUE = "monthly_plan_review_queue"

ADMISSION_OK = "Допущено"
ADMISSION_RISK = "Допущено с риском"
ADMISSION_BLOCKED = "Заблокировано"
ADMISSION_WAITING = "Ожидает проверки"
ADMISSION_NO_CHECKS = "Нет проверок"

# Мягкие фоны для колонки «Итог допуска» (read-only UI)
ADMISSION_OUTCOME_BG = {
    ADMISSION_OK: "background-color: #ecfdf5;",
    ADMISSION_RISK: "background-color: #fefce8;",
    ADMISSION_BLOCKED: "background-color: #ffedd5;",
    ADMISSION_WAITING: "background-color: #f0f9ff;",
    ADMISSION_NO_CHECKS: "background-color: #f4f4f5;",
}

DEPT_STATUS_NO_CHECK = "Нет проверки"

# Отображение в ячейках отделов (только RU)
DEPT_STATUS_LABEL = {
    "PASS": "Пройдено",
    "WARNING": "Риск",
    "HOLD": "Удержание",
    "FAIL": "Не пройдено",
    "ОЖИДАЕТ": "Ожидает проверки",
}

DEPT_STATUS_BG = {
    "Пройдено": "background-color: #ecfdf5;",
    "Риск": "background-color: #fefce8;",
    "Удержание": "background-color: #fff7ed;",
    "Не пройдено": "background-color: #fef2f2;",
    "Ожидает проверки": "background-color: #f0f9ff;",
    DEPT_STATUS_NO_CHECK: "background-color: #f4f4f5;",
}

PASSPORT_INCLUDE_OUTCOMES = frozenset({ADMISSION_OK, ADMISSION_RISK})

ADMISSION_FILTER_OPTIONS = [
    "Все",
    ADMISSION_OK,
    ADMISSION_RISK,
    ADMISSION_BLOCKED,
    ADMISSION_WAITING,
    ADMISSION_NO_CHECKS,
]

ADMISSION_RULE_TEXT = (
    "**Правило расчёта:**\n"
    "HOLD/FAIL блокирует строку.\n"
    "WAITING не допускает строку в паспорт.\n"
    "WARNING допускает строку с риском.\n"
    "Все PASS допускают строку.\n"
    "В паспорт попадают только «Допущено» и «Допущено с риском»."
)

# Колонка таблицы → responsible_department в constraints
ADMISSION_DEPT_COLUMNS: List[tuple[str, str]] = [
    ("Участок", "Участок"),
    ("ПТО", "ПТО"),
    ("МТО", "МТО"),
    ("ОТиТБ", "ОТиТБ"),
    ("QA/QC", "QAQC"),
    ("Коммерческий блок", "Коммерческий отдел"),
    ("Проектное управление", "Руководство"),
]

STATUS_PRIORITY = {"FAIL": 5, "HOLD": 4, "WARNING": 3, "ОЖИДАЕТ": 2, "PASS": 1}


def safe_str(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def safe_num(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0


def safe_date(value: Any) -> Optional[date]:
    if value is None or pd.isna(value) or safe_str(value) == "":
        return None
    try:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return pd.to_datetime(value).date()
    except Exception:  # noqa: BLE001
        return None


def money_ru(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "0,00 ₽"
        amount = float(value)
        sign = "-" if amount < 0 else ""
        amount = abs(amount)
        whole, frac = f"{amount:.2f}".split(".")
        whole_fmt = f"{int(whole):,}".replace(",", " ")
        return f"{sign}{whole_fmt},{frac} ₽"
    except Exception:  # noqa: BLE001
        return "0,00 ₽"


def display_dash(value: Any) -> str:
    text = safe_str(value)
    return text if text else "—"


def reverse_map(mapping: Dict[str, str]) -> Dict[str, str]:
    return {v: k for k, v in mapping.items()}


def ru_label(tech: str, mapping: Dict[str, str]) -> str:
    if tech == "Все":
        return "Все"
    return mapping.get(tech, tech)


def norm_tech_value(
    value: Any,
    tech_options: List[str],
    mapping: Dict[str, str],
    default: str,
) -> str:
    if value is None or pd.isna(value):
        return default
    raw = str(value).strip()
    if raw in tech_options:
        return raw
    rev = reverse_map(mapping)
    if raw in rev:
        return rev[raw]
    upper = raw.upper()
    if upper in tech_options:
        return upper
    return default


def norm_check_status_key(value: Any) -> str:
    return norm_tech_value(value, CHECK_STATUS_OPTIONS, CHECK_STATUS_RU, "ОЖИДАЕТ")


def dept_ui(db_value: Any) -> str:
    return DEPARTMENT_RU.get(safe_str(db_value), safe_str(db_value))


def row_risk_value(row: pd.Series) -> float:
    if "value_at_risk" in row.index and not pd.isna(row.get("value_at_risk")):
        return safe_num(row.get("value_at_risk"))
    return safe_num(row.get("plan_value"))


def reason_text(row: pd.Series) -> str:
    for col in ("block_reason", "root_cause", "constraint_category", "comment"):
        text = safe_str(row.get(col))
        if text:
            return text
    return "—"


def unique_risk_sum(df_part: pd.DataFrame) -> float:
    if df_part.empty:
        return 0.0
    key_cols: List[str] = []
    if "line_id" in df_part.columns:
        key_cols = ["line_id"]
    else:
        key_cols = [
            "project_code",
            "month_key",
            "facility_building",
            "construction_discipline",
            "boq_code",
            "crew_id",
        ]
        key_cols = [c for c in key_cols if c in df_part.columns]
    risk_col = "_risk_val"
    if key_cols:
        return float(df_part.drop_duplicates(subset=key_cols)[risk_col].sum())
    return float(df_part[risk_col].sum())


def owner_label(value: Any) -> str:
    text = safe_str(value)
    return text if text else "Не назначен"


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    created_col = (
        "constraint_created_at"
        if "constraint_created_at" in result.columns
        else "created_at"
    )

    if "days_overdue" not in result.columns or "is_overdue" not in result.columns:
        overdue_days: List[int] = []
        overdue_flags: List[bool] = []
        for _, row in result.iterrows():
            status = safe_str(row.get("resolution_status")).upper()
            target = safe_date(row.get("target_resolution_date"))
            if status in {"RESOLVED", "CANCELLED"} or target is None or target >= date.today():
                overdue_days.append(0)
                overdue_flags.append(False)
            else:
                overdue_days.append((date.today() - target).days)
                overdue_flags.append(True)
        if "days_overdue" not in result.columns:
            result["days_overdue"] = overdue_days
        if "is_overdue" not in result.columns:
            result["is_overdue"] = overdue_flags

    result["_risk_val"] = result.apply(row_risk_value, axis=1)
    return result


@st.cache_data(ttl=300)
def load_review_queue() -> pd.DataFrame:
    try:
        response = (
            supabase.table(TABLE_REVIEW_QUEUE).select("*").limit(10000).execute()
        )
        return pd.DataFrame(response.data or [])
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_constraints() -> pd.DataFrame:
    for table in (VIEW_DASHBOARD_V2, VIEW_DASHBOARD_V1, TABLE_CONSTRAINTS):
        try:
            response = supabase.table(table).select("*").limit(10000).execute()
            df = enrich_dataframe(pd.DataFrame(response.data or []))
            if not df.empty:
                return df
        except Exception:  # noqa: BLE001
            continue
    return pd.DataFrame()


def filter_options(df: pd.DataFrame, col: str) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def filter_options_ru(df: pd.DataFrame, col: str, mapping: Dict[str, str]) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals, key=lambda v: ru_label(v, mapping))


def apply_structural_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
) -> pd.DataFrame:
    """Фильтры среза плана без отсечения по отдельным проверкам (для итога допуска строк)."""
    return apply_filters(
        df,
        project,
        month,
        facility,
        discipline,
        gate_layer="Все",
        department="Все",
        check_status="Все",
        resolution_status="Все",
        overdue_only=False,
    )


def apply_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
    gate_layer: str,
    department: str,
    check_status: str,
    resolution_status: str,
    overdue_only: bool,
) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    if project != "Все" and "project_code" in result.columns:
        result = result[result["project_code"].astype(str) == project]
    if month != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month]
    if facility != "Все" and "facility_building" in result.columns:
        result = result[result["facility_building"].astype(str) == facility]
    if discipline != "Все" and "construction_discipline" in result.columns:
        result = result[result["construction_discipline"].astype(str) == discipline]
    if gate_layer != "Все" and "gate_layer" in result.columns:
        result = result[result["gate_layer"].astype(str) == gate_layer]
    if department != "Все" and "responsible_department" in result.columns:
        result = result[result["responsible_department"].astype(str) == department]
    if check_status != "Все" and "check_status" in result.columns:
        result = result[result["check_status"].astype(str) == check_status]
    if resolution_status != "Все" and "resolution_status" in result.columns:
        result = result[result["resolution_status"].astype(str) == resolution_status]
    if overdue_only and "is_overdue" in result.columns:
        result = result[result["is_overdue"].astype(bool)]
    return result


def style_status_table(df_in: pd.DataFrame, status_col: str):
    styler = df_in.style
    if status_col in df_in.columns:
        fn = lambda v: CHECK_STATUS_BG_RU.get(str(v), "")  # noqa: E731
        if hasattr(styler, "map"):
            styler = styler.map(fn, subset=pd.IndexSlice[:, [status_col]])
        else:
            styler = styler.applymap(fn, subset=pd.IndexSlice[:, [status_col]])
    return styler


def translate_check_status(series: pd.Series) -> pd.Series:
    return series.apply(
        lambda v: CHECK_STATUS_RU.get(norm_check_status_key(v), safe_str(v))
    )


def translate_resolution(series: pd.Series) -> pd.Series:
    return series.apply(
        lambda v: RESOLUTION_RU.get(
            norm_tech_value(v, RESOLUTION_OPTIONS, RESOLUTION_RU, safe_str(v)),
            safe_str(v),
        )
    )


def filter_admission_scope(
    df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
) -> pd.DataFrame:
    """Срез плана для итога допуска: project + month (+ титул/объект, дисциплина)."""
    if df.empty:
        return df
    result = df.copy()
    if project != "Все" and "project_code" in result.columns:
        result = result[result["project_code"].astype(str) == project]
    if month != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month]
    if facility != "Все":
        if "facility_building" in result.columns:
            result = result[result["facility_building"].astype(str) == facility]
        elif "facility_label" in result.columns:
            result = result[result["facility_label"].astype(str) == facility]
    if discipline != "Все" and "construction_discipline" in result.columns:
        result = result[result["construction_discipline"].astype(str) == discipline]
    return result


def queue_row_key(row: pd.Series) -> str:
    line_id = safe_str(row.get("line_id"))
    if line_id:
        return f"line:{line_id}"
    return "row:" + "|".join(
        [
            safe_str(row.get("draft_id")),
            safe_str(row.get("project_code")),
            safe_str(row.get("month_key")),
            safe_str(row.get("boq_code")),
            safe_str(row.get("crew_id")),
            safe_str(row.get("facility_building")),
        ]
    )


def count_line_constraint_statuses(group: pd.DataFrame) -> Dict[str, int]:
    counts = {"hold": 0, "fail": 0, "warning": 0, "waiting": 0, "pass": 0, "total": 0}
    if group.empty or "check_status" not in group.columns:
        return counts
    for status in group["check_status"].apply(norm_check_status_key):
        counts["total"] += 1
        if status == "HOLD":
            counts["hold"] += 1
        elif status == "FAIL":
            counts["fail"] += 1
        elif status == "WARNING":
            counts["warning"] += 1
        elif status == "ОЖИДАЕТ":
            counts["waiting"] += 1
        elif status == "PASS":
            counts["pass"] += 1
    return counts


def resolve_line_admission_outcome(counts: Dict[str, int]) -> str:
    if counts["total"] == 0:
        return ADMISSION_NO_CHECKS
    if counts["hold"] > 0 or counts["fail"] > 0:
        return ADMISSION_BLOCKED
    if counts["waiting"] > 0:
        return ADMISSION_WAITING
    if counts["warning"] > 0:
        return ADMISSION_RISK
    if counts["pass"] == counts["total"]:
        return ADMISSION_OK
    return ADMISSION_WAITING


def worst_check_status(status_keys: List[str]) -> str:
    if not status_keys:
        return ""
    return max(status_keys, key=lambda k: STATUS_PRIORITY.get(k, 0))


def dept_status_for_group(group: pd.DataFrame, dept_db: str) -> str:
    if group.empty or "responsible_department" not in group.columns:
        return DEPT_STATUS_NO_CHECK
    subset = group[group["responsible_department"].astype(str) == dept_db]
    if subset.empty:
        return DEPT_STATUS_NO_CHECK
    keys = [norm_check_status_key(v) for v in subset["check_status"]]
    worst = worst_check_status(keys)
    if not worst:
        return DEPT_STATUS_NO_CHECK
    return DEPT_STATUS_LABEL.get(worst, DEPT_STATUS_NO_CHECK)


def depts_with_statuses(group: pd.DataFrame, status_keys: frozenset[str]) -> List[str]:
    names: List[str] = []
    if group.empty or "responsible_department" not in group.columns:
        return names
    for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
        subset = group[group["responsible_department"].astype(str) == dept_db]
        if subset.empty:
            continue
        for raw in subset["check_status"]:
            if norm_check_status_key(raw) in status_keys:
                names.append(col_label)
                break
    return names


def build_admission_logic_explanation(counts: Dict[str, int], group: pd.DataFrame) -> str:
    if counts["total"] == 0:
        return "Нет проверок → Нет проверок"
    hold_depts = depts_with_statuses(group, frozenset({"HOLD"}))
    if hold_depts:
        return f"Есть HOLD от {', '.join(hold_depts)} → Заблокировано"
    fail_depts = depts_with_statuses(group, frozenset({"FAIL"}))
    if fail_depts:
        return f"Есть FAIL от {', '.join(fail_depts)} → Заблокировано"
    waiting_depts = depts_with_statuses(group, frozenset({"ОЖИДАЕТ"}))
    if waiting_depts:
        return f"Есть WAITING от {', '.join(waiting_depts)} → Ожидает проверки"
    if counts["waiting"] > 0:
        return "Есть WAITING → Ожидает проверки"
    warning_depts = depts_with_statuses(group, frozenset({"WARNING"}))
    if warning_depts:
        return (
            f"Есть WARNING от {', '.join(warning_depts)}, HOLD/FAIL нет → Допущено с риском"
        )
    if counts["warning"] > 0:
        return "Есть WARNING, HOLD/FAIL нет → Допущено с риском"
    return "Все отделы PASS → Допущено"


def build_action_needed(outcome: str) -> str:
    return {
        ADMISSION_BLOCKED: "Закрыть HOLD / снять блокировку",
        ADMISSION_WAITING: "Дождаться проверки отделов",
        ADMISSION_RISK: "Принять риск или закрыть замечания",
        ADMISSION_OK: "Готово к паспорту",
        ADMISSION_NO_CHECKS: "Сформировать проверки в контуре допуска",
    }.get(outcome, "—")


def passport_includes_outcome(outcome: str) -> str:
    return "Да" if outcome in PASSPORT_INCLUDE_OUTCOMES else "Нет"


def line_reason_summary(group: pd.DataFrame, outcome: str) -> str:
    if group.empty or outcome in (ADMISSION_OK, ADMISSION_NO_CHECKS):
        return "—"
    if "check_status" not in group.columns:
        return "—"
    statuses = group["check_status"].apply(norm_check_status_key)
    if outcome == ADMISSION_BLOCKED:
        mask = statuses.isin(["HOLD", "FAIL"])
    elif outcome == ADMISSION_WAITING:
        mask = statuses == "ОЖИДАЕТ"
    elif outcome == ADMISSION_RISK:
        mask = statuses == "WARNING"
    else:
        mask = pd.Series(True, index=group.index)
    parts: List[str] = []
    seen: set[str] = set()
    for _, row in group[mask].iterrows():
        text = reason_text(row)
        if text != "—" and text not in seen:
            seen.add(text)
            parts.append(text)
    return "; ".join(parts) if parts else "—"


def line_plan_value(row: pd.Series) -> float:
    if "plan_value" in row.index and not pd.isna(row.get("plan_value")):
        return safe_num(row.get("plan_value"))
    return safe_num(row.get("_risk_val"))


def build_constraints_by_line_id(constraints_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    by_line: Dict[str, pd.DataFrame] = {}
    if constraints_df.empty or "line_id" not in constraints_df.columns:
        return by_line
    line_series = constraints_df["line_id"]
    valid = line_series.notna() & (line_series.astype(str).str.strip() != "")
    for line_id, part in constraints_df.loc[valid].groupby(
        line_series.loc[valid].astype(str), dropna=False
    ):
        lid = safe_str(line_id)
        if lid:
            by_line[lid] = part
    return by_line


def build_admission_lines_table(
    admission_constraints: pd.DataFrame,
    queue_df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
) -> pd.DataFrame:
    """Все строки review_queue в срезе; проверки — по line_id (не по BOQ-коду)."""
    queue = filter_admission_scope(queue_df, project, month, facility, discipline)
    constraints = filter_admission_scope(
        admission_constraints, project, month, facility, discipline
    )
    constraints_by_line = build_constraints_by_line_id(constraints)

    rows: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()

    for _, qrow in queue.iterrows():
        row_key = queue_row_key(qrow)
        if row_key in seen_keys:
            continue
        seen_keys.add(row_key)

        lid = safe_str(qrow.get("line_id"))
        c_group = constraints_by_line.get(lid, pd.DataFrame()) if lid else pd.DataFrame()
        counts = count_line_constraint_statuses(c_group)
        outcome = resolve_line_admission_outcome(counts)

        row_data: Dict[str, Any] = {
            "BOQ-код": display_dash(qrow.get("boq_code")),
            "Наименование": display_dash(qrow.get("boq_name")),
            "Звено": display_dash(qrow.get("crew_id")),
            "Плановый объём": safe_num(qrow.get("planned_qty")),
            "Плановая стоимость": line_plan_value(qrow),
            "Итог допуска": outcome,
            "Логика итога": build_admission_logic_explanation(counts, c_group),
            "Что нужно сделать": build_action_needed(outcome),
            "Причина блокировки / риска": line_reason_summary(c_group, outcome),
            "HOLD count": counts["hold"],
            "FAIL count": counts["fail"],
            "WARNING count": counts["warning"],
            "WAITING count": counts["waiting"],
            "Что попадёт в паспорт": passport_includes_outcome(outcome),
            "_outcome": outcome,
        }
        for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
            row_data[col_label] = dept_status_for_group(c_group, dept_db)
        rows.append(row_data)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    sort_order = {
        ADMISSION_BLOCKED: 0,
        ADMISSION_WAITING: 1,
        ADMISSION_RISK: 2,
        ADMISSION_OK: 3,
        ADMISSION_NO_CHECKS: 4,
    }
    result["_sort"] = result["_outcome"].map(sort_order).fillna(99)
    return result.sort_values(
        ["_sort", "Плановая стоимость"], ascending=[True, False]
    )


def admission_cell_background(value: Any) -> str:
    text = safe_str(value)
    if text in DEPT_STATUS_BG:
        return DEPT_STATUS_BG[text]
    if text in ADMISSION_OUTCOME_BG:
        return ADMISSION_OUTCOME_BG[text]
    return ""


def style_admission_table(df_in: pd.DataFrame):
    """Подсветка колонок отделов и «Итог допуска» через pandas Styler."""
    dept_cols = [label for label, _ in ADMISSION_DEPT_COLUMNS if label in df_in.columns]
    styled_cols = dept_cols.copy()
    if "Итог допуска" in df_in.columns:
        styled_cols.append("Итог допуска")
    if not styled_cols:
        return df_in.style

    styler = df_in.style
    bg_fn = lambda v: admission_cell_background(v)  # noqa: E731
    subset = pd.IndexSlice[:, styled_cols]
    if hasattr(styler, "map"):
        return styler.map(bg_fn, subset=subset)
    return styler.applymap(bg_fn, subset=subset)


def render_admission_plan_summary(
    base_constraints: pd.DataFrame,
    queue_df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
) -> None:
    st.markdown("### Итог допуска месячного плана")
    st.caption(
        "По каждой строке `review_queue` (уникальный line_id / звено / объём). "
        "Итог — по всем проверкам отделов на эту строку."
    )

    if project == "Все" or month == "Все":
        st.warning(
            "Для полного итога допуска выберите конкретный **проект** и **месяц** "
            "(все строки очереди review_queue в этом срезе)."
        )

    queue_scope = filter_admission_scope(queue_df, project, month, facility, discipline)
    queue_rows_total = len(queue_scope)

    lines = build_admission_lines_table(
        base_constraints, queue_df, project, month, facility, discipline
    )
    if lines.empty:
        st.info(
            "Нет строк в monthly_plan_review_queue по выбранным фильтрам. "
            "Отправьте черновик в контур допуска на странице конструктора."
        )
        return

    outcome_col = lines["_outcome"]
    value_col = lines["Плановая стоимость"].astype(float)

    def sum_value(mask: pd.Series) -> float:
        return float(value_col[mask].sum())

    total_lines = len(lines)
    admitted = int((outcome_col == ADMISSION_OK).sum())
    risk = int((outcome_col == ADMISSION_RISK).sum())
    blocked = int((outcome_col == ADMISSION_BLOCKED).sum())
    waiting = int((outcome_col == ADMISSION_WAITING).sum())
    no_checks = int((outcome_col == ADMISSION_NO_CHECKS).sum())
    status_sum = admitted + risk + blocked + waiting + no_checks

    k1, k2, k3, k4 = st.columns(4)
    k5, k6, k7, k8, k9 = st.columns(5)
    k1.metric("Всего строк плана", total_lines)
    k2.metric("Допущено", admitted)
    k3.metric("Допущено с риском", risk)
    k4.metric("Заблокировано", blocked)
    k5.metric("Ожидает проверки", waiting)
    k6.metric("Нет проверок", no_checks)
    k7.metric("Стоимость допущено", money_ru(sum_value(outcome_col == ADMISSION_OK)))
    k8.metric("Стоимость с риском", money_ru(sum_value(outcome_col == ADMISSION_RISK)))
    k9.metric("Стоимость заблокировано", money_ru(sum_value(outcome_col == ADMISSION_BLOCKED)))

    if status_sum != total_lines:
        st.warning(
            f"Сумма статусов ({status_sum}) не равна числу строк ({total_lines}). "
            "Проверьте данные constraints / review_queue."
        )
    if queue_rows_total != total_lines:
        st.warning(
            f"Строк в review_queue: {queue_rows_total}, в таблице итога: {total_lines}. "
            "Возможны дубликаты line_id в очереди."
        )

    st.markdown(ADMISSION_RULE_TEXT)

    outcome_filter = st.selectbox(
        "Итог допуска",
        ADMISSION_FILTER_OPTIONS,
        key="war_room_admission_outcome_filter",
    )

    display = lines.drop(columns=["_outcome", "_sort"], errors="ignore").copy()
    if outcome_filter != "Все":
        mask = lines["_outcome"] == outcome_filter
        display = lines.loc[mask].drop(columns=["_outcome", "_sort"], errors="ignore").copy()

    display["Плановый объём"] = display["Плановый объём"].apply(
        lambda v: f"{safe_num(v):,.3f}".replace(",", " ") if safe_num(v) else "—"
    )
    display["Плановая стоимость"] = display["Плановая стоимость"].apply(money_ru)

    st.markdown("#### Строки месячного плана — итог допуска")
    st.caption(
        f"Показано {len(display)} из {total_lines} строк очереди "
        f"(проект={project}, месяц={month}"
        + (f", объект={facility}" if facility != "Все" else "")
        + (f", дисциплина={discipline}" if discipline != "Все" else "")
        + ")."
    )
    st.dataframe(
        style_admission_table(display),
        use_container_width=True,
        hide_index=True,
        height=min(560, 80 + 35 * max(len(display), 1)),
    )


def render_passport_formation(project_sel: str, month_sel: str) -> None:
    st.markdown("### Формирование паспорта месяца")
    st.caption(
        "После снятия HOLD/FAIL ограничений можно сформировать Approved Monthly Plan Passport. "
        "В паспорт попадут только строки, готовые к выполнению, либо строки, допущенные "
        "управленческим override."
    )

    if project_sel == "Все" or month_sel == "Все":
        st.warning("Выберите конкретный проект и месяц для формирования паспорта.")
        return

    created_by = st.text_input(
        "Кто утверждает (created_by / approved_by)",
        value="Пользователь Streamlit",
        key="passport_created_by",
    )

    if st.button("Сформировать Monthly Plan Passport", key="create_monthly_passport_btn"):
        summary = create_monthly_passport(
            project_code=project_sel,
            month_key=month_sel,
            created_by=created_by.strip() or "Пользователь Streamlit",
        )
        status = summary.get("status")

        if status == "created":
            st.success("Паспорт месяца сформирован")
            c1, c2, c3, c4 = st.columns(4)
            c5, c6, c7, c8 = st.columns(4)
            c1.metric("passport_id", display_dash(summary.get("passport_id")))
            c2.metric("Строк включено", summary.get("created_lines", 0))
            c3.metric("Пропущено (BLOCKED)", summary.get("skipped_blocked", 0))
            c4.metric("BLOCKED без override", summary.get("blocked_without_override", 0))
            c5.metric("Override включено", summary.get("override_included_rows", 0))
            c6.metric("Пропущено (ожидание)", summary.get("skipped_waiting", 0))
            c7.metric("Стоимость плана", money_ru(summary.get("total_value")))
            c8.metric("Трудозатраты, ч", f"{safe_num(summary.get('total_hours')):,.1f}".replace(",", " "))
            st.cache_data.clear()
        elif status == "already_exists":
            st.info("Паспорт месяца уже существует")
            st.caption(f"passport_id: {display_dash(summary.get('passport_id'))}")
        elif status in ("no_eligible_lines", "no_source_rows", "no_approved_lines"):
            st.warning("Нет строк, готовых для формирования паспорта месяца")
        else:
            st.error(f"Не удалось сформировать паспорт (status={status}).")

        errors = summary.get("errors") or []
        if errors:
            for err in errors:
                st.error(err)
            with st.expander("Подробности ошибок"):
                st.json(errors)


def render_kpis(df: pd.DataFrame) -> None:
    total = len(df)
    open_cnt = (
        len(df[df["resolution_status"].astype(str).isin(OPEN_RESOLUTION)])
        if "resolution_status" in df.columns
        else 0
    )
    hold_cnt = (
        len(df[df["check_status"].astype(str) == "HOLD"]) if "check_status" in df.columns else 0
    )
    fail_cnt = (
        len(df[df["check_status"].astype(str) == "FAIL"]) if "check_status" in df.columns else 0
    )
    overdue_cnt = int(df["is_overdue"].astype(bool).sum()) if "is_overdue" in df.columns else 0
    risk_sum = unique_risk_sum(df)
    overdue_series = (
        df.loc[df["days_overdue"].astype(float) > 0, "days_overdue"].astype(float)
        if "days_overdue" in df.columns
        else pd.Series(dtype=float)
    )
    avg_overdue = float(overdue_series.mean()) if not overdue_series.empty else 0.0
    if "owner_name" in df.columns:
        owners = df["owner_name"].apply(lambda v: safe_str(v)).replace("", pd.NA).dropna().unique()
        owner_cnt = len(owners)
    else:
        owner_cnt = 0

    c1, c2, c3, c4 = st.columns(4)
    c5, c6, c7, c8 = st.columns(4)
    c1.metric("Всего ограничений", total)
    c2.metric("Открыто", open_cnt)
    c3.metric("HOLD", hold_cnt)
    c4.metric("FAIL", fail_cnt)
    c5.metric("Просрочено", overdue_cnt)
    c6.metric("Стоимость под риском", money_ru(risk_sum))
    c7.metric("Средняя просрочка, дней", f"{avg_overdue:.1f}")
    c8.metric("Владельцев ограничений", owner_cnt)


def render_department_summary(df: pd.DataFrame) -> None:
    st.markdown("### Сводка по отделам")
    if df.empty or "responsible_department" not in df.columns:
        st.caption("Нет данных.")
        return

    tmp = df.copy()
    tmp["_hold"] = tmp["check_status"].astype(str) == "HOLD" if "check_status" in tmp.columns else False
    tmp["_fail"] = tmp["check_status"].astype(str) == "FAIL" if "check_status" in tmp.columns else False
    tmp["_overdue"] = tmp["is_overdue"].astype(bool) if "is_overdue" in tmp.columns else False

    rows: List[Dict[str, Any]] = []
    for dept, part in tmp.groupby("responsible_department", dropna=False):
        rows.append(
            {
                "Отдел": dept_ui(dept),
                "Всего": len(part),
                "HOLD": int(part["_hold"].sum()),
                "FAIL": int(part["_fail"].sum()),
                "Просрочено": int(part["_overdue"].sum()),
                "Стоимость под риском": money_ru(unique_risk_sum(part)),
            }
        )
    show = pd.DataFrame(rows)
    st.dataframe(show, use_container_width=True, hide_index=True)


def render_top10(df: pd.DataFrame) -> None:
    st.markdown("### ТОП-10 ограничений по стоимости под риском")
    if df.empty:
        st.caption("Нет данных.")
        return

    top = df.sort_values("_risk_val", ascending=False).head(10).copy()
    top["Статус"] = translate_check_status(top["check_status"]) if "check_status" in top.columns else "—"
    top["Срок закрытия"] = top["target_resolution_date"].apply(
        lambda v: safe_date(v).isoformat() if safe_date(v) else "—"
    ) if "target_resolution_date" in top.columns else "—"
    top["Просрочка"] = top["days_overdue"].apply(lambda v: int(safe_num(v))) if "days_overdue" in top.columns else 0
    top["Причина"] = top.apply(reason_text, axis=1)

    table = pd.DataFrame(
        {
            "BOQ-код": top["boq_code"].apply(display_dash) if "boq_code" in top.columns else "—",
            "Наименование": top["boq_name"].apply(display_dash) if "boq_name" in top.columns else "—",
            "Отдел": top["responsible_department"].apply(dept_ui),
            "Проверка": top["check_name"].apply(display_dash) if "check_name" in top.columns else "—",
            "Статус": top["Статус"],
            "Владелец": top["owner_name"].apply(display_dash) if "owner_name" in top.columns else "—",
            "Срок закрытия": top["Срок закрытия"],
            "Просрочка": top["Просрочка"],
            "Стоимость под риском": top["_risk_val"].apply(money_ru),
            "Причина": top["Причина"],
        }
    )
    st.dataframe(style_status_table(table, "Статус"), use_container_width=True, hide_index=True)


def render_overdue(df: pd.DataFrame) -> None:
    st.markdown("### Просроченные ограничения")
    if df.empty:
        st.caption("Нет данных.")
        return

    overdue = df[df["days_overdue"].astype(float) > 0].copy() if "days_overdue" in df.columns else pd.DataFrame()
    if overdue.empty:
        st.caption("Просроченных ограничений нет.")
        return

    overdue = overdue.sort_values("days_overdue", ascending=False)
    overdue["Статус"] = translate_check_status(overdue["check_status"]) if "check_status" in overdue.columns else "—"
    overdue["Причина"] = overdue.apply(reason_text, axis=1)

    table = pd.DataFrame(
        {
            "BOQ-код": overdue["boq_code"].apply(display_dash) if "boq_code" in overdue.columns else "—",
            "Отдел": overdue["responsible_department"].apply(dept_ui),
            "Проверка": overdue["check_name"].apply(display_dash) if "check_name" in overdue.columns else "—",
            "Владелец": overdue["owner_name"].apply(display_dash) if "owner_name" in overdue.columns else "—",
            "Срок закрытия": overdue["target_resolution_date"].apply(
                lambda v: safe_date(v).isoformat() if safe_date(v) else "—"
            ) if "target_resolution_date" in overdue.columns else "—",
            "Просрочка, дней": overdue["days_overdue"].apply(lambda v: int(safe_num(v))),
            "Статус": overdue["Статус"],
            "Причина": overdue["Причина"],
        }
    )
    st.dataframe(style_status_table(table, "Статус"), use_container_width=True, hide_index=True)


def render_owners(df: pd.DataFrame) -> None:
    st.markdown("### Владельцы ограничений")
    if df.empty:
        st.caption("Нет данных.")
        return

    tmp = df.copy()
    tmp["_owner"] = (
        tmp["owner_name"].apply(owner_label) if "owner_name" in tmp.columns else "Не назначен"
    )
    tmp["_overdue"] = tmp["is_overdue"].astype(bool) if "is_overdue" in tmp.columns else False

    rows: List[Dict[str, Any]] = []
    for owner, part in tmp.groupby("_owner", dropna=False):
        risk_num = unique_risk_sum(part)
        rows.append(
            {
                "Владелец": owner,
                "Ограничений": len(part),
                "Просрочено": int(part["_overdue"].sum()),
                "_risk_num": risk_num,
                "Стоимость под риском": money_ru(risk_num),
                "Макс. просрочка, дн.": int(part["days_overdue"].max()) if "days_overdue" in part.columns else 0,
            }
        )
    agg = (
        pd.DataFrame(rows)
        .sort_values("_risk_num", ascending=False)
        .drop(columns=["_risk_num"])
    )
    agg["Макс. просрочка, дн."] = agg["Макс. просрочка, дн."].apply(lambda v: int(safe_num(v)))
    st.dataframe(agg, use_container_width=True, hide_index=True)


def render_gate_layers(df: pd.DataFrame) -> None:
    st.markdown("### Контуры допуска")
    st.caption(
        "Стоимость по контурам считается внутри каждого контура; "
        "одна строка плана может входить в несколько контуров."
    )
    if df.empty or "gate_layer" not in df.columns:
        st.caption("Нет данных.")
        return

    rows: List[Dict[str, Any]] = []
    for gate, part in df.groupby("gate_layer", dropna=False):
        rows.append(
            {
                "Контур допуска": GATE_LAYER_RU.get(safe_str(gate), safe_str(gate)),
                "Количество": len(part),
                "Стоимость под риском": money_ru(unique_risk_sum(part)),
            }
        )
    show = pd.DataFrame(rows)
    st.dataframe(show, use_container_width=True, hide_index=True)


def main() -> None:
    st.title("War Room ограничений")
    st.caption(
        "Совещание по блокировкам месячного плана: ТОП по стоимости, просрочки, "
        "владельцы и контуры допуска."
    )

    base_df = load_constraints()
    if base_df.empty:
        st.info(EMPTY_MSG)
        return

    st.markdown("### Фильтры")
    f1, f2, f3, f4 = st.columns(4)
    f5, f6, f7, f8, f9 = st.columns(5)

    project_sel = f1.selectbox("Проект", filter_options(base_df, "project_code"))
    month_sel = f2.selectbox("Месяц", filter_options(base_df, "month_key"))
    facility_sel = f3.selectbox("Здание / объект", filter_options(base_df, "facility_building"))
    discipline_sel = f4.selectbox("Дисциплина", filter_options(base_df, "construction_discipline"))
    gate_sel = f5.selectbox(
        "Контур допуска",
        filter_options_ru(base_df, "gate_layer", GATE_LAYER_RU),
        format_func=lambda v: ru_label(v, GATE_LAYER_RU),
    )
    department_sel = f6.selectbox(
        "Отдел",
        filter_options(base_df, "responsible_department"),
        format_func=lambda v: dept_ui(v) if v != "Все" else "Все",
    )
    check_status_sel = f7.selectbox(
        "Статус проверки",
        filter_options_ru(base_df, "check_status", CHECK_STATUS_RU),
        format_func=lambda v: ru_label(v, CHECK_STATUS_RU),
    )
    resolution_sel = f8.selectbox(
        "Статус устранения",
        filter_options_ru(base_df, "resolution_status", RESOLUTION_RU),
        format_func=lambda v: ru_label(v, RESOLUTION_RU),
    )
    overdue_only = f9.checkbox("Только просроченные")

    df = apply_filters(
        base_df,
        project_sel,
        month_sel,
        facility_sel,
        discipline_sel,
        gate_sel,
        department_sel,
        check_status_sel,
        resolution_sel,
        overdue_only,
    )

    queue_df = load_review_queue()

    st.markdown("---")
    render_admission_plan_summary(
        base_df,
        queue_df,
        project_sel,
        month_sel,
        facility_sel,
        discipline_sel,
    )

    st.markdown("### KPI")
    if df.empty:
        st.info("По выбранным фильтрам ограничений нет.")
    else:
        render_kpis(df)

    st.markdown("---")
    render_passport_formation(project_sel, month_sel)

    if df.empty:
        return

    st.markdown("---")
    render_department_summary(df)
    st.markdown("---")
    render_top10(df)
    st.markdown("---")
    render_overdue(df)
    st.markdown("---")
    render_owners(df)
    st.markdown("---")
    render_gate_layers(df)


if __name__ == "__main__":
    main()
