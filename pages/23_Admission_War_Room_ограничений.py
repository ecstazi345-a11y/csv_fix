from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from services.monthly_passport_service import create_monthly_passport
import services.monthly_passport_service as monthly_passport_service
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

# --- War Room V2 (executive layer, plan-line grain) ---
TABLE_V2_PLAN_LINES = "monthly_plan_lines_v2"
V2_STATUS_SENT = "SENT_TO_ADMISSION"

WR2_OUTCOME_BLOCKED = "Заблокировано"
WR2_OUTCOME_WAITING = "Ожидает проверки"
WR2_OUTCOME_RISK = "Допущено с риском"
WR2_OUTCOME_OK = "Допущено"
WR2_OUTCOME_NO_CHECKS = "Нет проверок"

WR2_OUTCOME_FILTER_OPTIONS = [
    "Все",
    WR2_OUTCOME_OK,
    WR2_OUTCOME_RISK,
    WR2_OUTCOME_BLOCKED,
    WR2_OUTCOME_WAITING,
    WR2_OUTCOME_NO_CHECKS,
]

WR2_OUTCOME_SORT = {
    WR2_OUTCOME_BLOCKED: 0,
    WR2_OUTCOME_WAITING: 1,
    WR2_OUTCOME_NO_CHECKS: 2,
    WR2_OUTCOME_RISK: 3,
    WR2_OUTCOME_OK: 4,
}

WR2_OUTCOME_BG = {
    WR2_OUTCOME_OK: "background-color: #ecfdf5;",
    WR2_OUTCOME_RISK: "background-color: #fefce8;",
    WR2_OUTCOME_BLOCKED: "background-color: #ffedd5;",
    WR2_OUTCOME_WAITING: "background-color: #f0f9ff;",
    WR2_OUTCOME_NO_CHECKS: "background-color: #f4f4f5;",
}

# Колонка UI → responsible_department в constraints
WR2_DEPT_COLUMNS: List[tuple[str, str]] = [
    ("ПТО", "ПТО"),
    ("МТО", "МТО"),
    ("QA/QC", "QAQC"),
    ("HSE", "ОТиТБ"),
    ("Производство", "Участок"),
    ("Коммерческий контроль", "Коммерческий отдел"),
    ("ПНР", "Руководство"),
]

WR2_BOARD_DEPT_COLUMNS = ["ПТО", "МТО", "QA/QC", "HSE"]

WR2_DEPT_BADGE = {
    "PASS": "Допущено",
    "WARNING": "Риск",
    "HOLD": "Заблокировано",
    "FAIL": "Заблокировано",
    "ОЖИДАЕТ": "Ожидает",
}

WR2_DEPT_BADGE_BG = {
    "Допущено": "background-color: #ecfdf5;",
    "Риск": "background-color: #fefce8;",
    "Заблокировано": "background-color: #ffedd5;",
    "Ожидает": "background-color: #f0f9ff;",
}

WR2_MGMT_INCLUDE = "Включить"
WR2_MGMT_INCLUDE_RISK = "Включить с риском"
WR2_MGMT_EXCLUDE = "Не включать"
WR2_MGMT_LEAVE_REWORK = "Оставить на доработке"

WR2_MGMT_NON_CLEAN_OPTIONS = [
    WR2_MGMT_EXCLUDE,
    WR2_MGMT_INCLUDE_RISK,
    WR2_MGMT_LEAVE_REWORK,
]

WR2_NON_CLEAN_OUTCOMES = [
    WR2_OUTCOME_BLOCKED,
    WR2_OUTCOME_WAITING,
    WR2_OUTCOME_RISK,
]

WR2_RISK_REASON_PLACEHOLDER = (
    "Например: «Звено будет в простое, принято решение запускать работы параллельно "
    "снятию ограничения»; «Ограничение не блокирует фактический старт работ»; "
    "«Риск принят руководством проекта»; «Работы можно выполнять при условии "
    "последующего закрытия замечаний»."
)

WR2_SOURCE_DISPLAY = {
    "v2": "V2 Конструктор",
    "legacy_queue": "Старый контур",
    "constraints": "Ограничения",
}

WR2_FILTER_KEYS = {
    "project": "wr2_filter_project",
    "month": "wr2_filter_month",
    "queue": "wr2_filter_queue",
    "title": "wr2_filter_title",
    "discipline": "wr2_filter_discipline",
    "department": "wr2_filter_department",
    "outcome": "wr2_filter_outcome",
    "check_status": "wr2_filter_check_status",
    "overdue": "wr2_filter_overdue",
    "search_boq": "wr2_filter_search_boq",
}

# Как в 10B / Page 21 — полный список месяцев, не только месяцы из БД
PLANNING_MONTH_OPTIONS = [
    "январь-2026",
    "февраль-2026",
    "март-2026",
    "апрель-2026",
    "май-2026",
    "июнь-2026",
    "июль-2026",
    "август-2026",
    "сентябрь-2026",
    "октябрь-2026",
    "ноябрь-2026",
    "декабрь-2026",
]

WR2_QUEUE_OPTIONS = ["Все", "1 очередь", "2 очередь"]

TABLE_BOQ_MASTER = "boq_master_api"

# Порядок колонок главной таблицы War Room V2
WR2_BOARD_DEPT_DISPLAY: List[tuple[str, str]] = [
    ("Участок", "Участок"),
    ("МТО", "МТО"),
    ("ПТО", "ПТО"),
    ("QA/QC", "QA/QC"),
    ("ОТиТБ / HSE", "ОТиТБ"),
    ("Коммерческий блок", "Коммерческий блок"),
    ("Проектное управление", "Проектное управление"),
]

WR2_BOARD_TABLE_COLUMNS = [
    "Проект",
    "Очередь",
    "Титул",
    "Система",
    "Пакет",
    "BOQ-код",
    "Наименование",
    *[label for label, _ in WR2_BOARD_DEPT_DISPLAY],
    "Звено",
    "Плановый объём",
    "Плановая стоимость",
    "Итог допуска",
    "Логика итога",
    "Что нужно сделать",
    "Причина блокировки / риска",
    "HOLD count",
    "FAIL count",
    "WARNING count",
    "WAITING count",
    "% проверок",
    "Включать в паспорт",
]


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


@st.cache_data(ttl=300)
def load_v2_plan_lines() -> pd.DataFrame:
    try:
        response = (
            supabase.table(TABLE_V2_PLAN_LINES).select("*").limit(10000).execute()
        )
        return pd.DataFrame(response.data or [])
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def money_ru_compact(value: Any) -> str:
    try:
        amount = abs(float(value or 0))
        if amount >= 1_000_000:
            return f"{amount / 1_000_000:,.1f} млн ₽".replace(",", " ")
        if amount >= 1_000:
            return f"{amount / 1_000:,.0f} тыс ₽".replace(",", " ")
        return money_ru(value)
    except Exception:  # noqa: BLE001
        return "0 ₽"


def derive_construction_queue_from_facility(facility: str) -> str:
    """Та же логика, что Page 21 derive_construction_queue_from_facility."""
    text = str(facility or "")
    if "16160-13" in text or "16160-17" in text:
        return "1 очередь"
    if "26160-13" in text or "26160-17" in text:
        return "2 очередь"
    return "Не определено"


def wr2_month_filter_options() -> List[str]:
    return ["Все", *PLANNING_MONTH_OPTIONS]


def wr2_default_month(full_board: pd.DataFrame) -> str:
    if not full_board.empty and "month_key" in full_board.columns:
        data_months = {
            safe_str(m)
            for m in full_board["month_key"].dropna().astype(str).str.strip().unique()
            if safe_str(m)
        }
        for month in reversed(PLANNING_MONTH_OPTIONS):
            if month in data_months:
                return month
    return "июнь-2026"


def wr2_init_filter_defaults(full_board: pd.DataFrame) -> None:
    month_opts = wr2_month_filter_options()
    default_month = wr2_default_month(full_board)
    if WR2_FILTER_KEYS["month"] not in st.session_state:
        st.session_state[WR2_FILTER_KEYS["month"]] = (
            default_month if default_month in month_opts else "июнь-2026"
        )
    elif st.session_state[WR2_FILTER_KEYS["month"]] not in month_opts:
        st.session_state[WR2_FILTER_KEYS["month"]] = default_month

    defaults: Dict[str, Any] = {
        WR2_FILTER_KEYS["project"]: "Все",
        WR2_FILTER_KEYS["queue"]: "Все",
        WR2_FILTER_KEYS["title"]: "Все",
        WR2_FILTER_KEYS["discipline"]: "Все",
        WR2_FILTER_KEYS["department"]: "Все",
        WR2_FILTER_KEYS["outcome"]: "Все",
        WR2_FILTER_KEYS["check_status"]: "Все",
        WR2_FILTER_KEYS["overdue"]: False,
        WR2_FILTER_KEYS["search_boq"]: "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def wr2_outcome_for_classic(outcome: str) -> str:
    mapping = {
        WR2_OUTCOME_OK: ADMISSION_OK,
        WR2_OUTCOME_RISK: ADMISSION_RISK,
        WR2_OUTCOME_BLOCKED: ADMISSION_BLOCKED,
        WR2_OUTCOME_WAITING: ADMISSION_WAITING,
        WR2_OUTCOME_NO_CHECKS: ADMISSION_NO_CHECKS,
    }
    return mapping.get(outcome, ADMISSION_WAITING)


def wr2_checks_percent(counts: Dict[str, int]) -> str:
    completed = counts["pass"] + counts["warning"] + counts["hold"] + counts["fail"]
    return f"{round(100.0 * completed / len(WR2_DEPT_COLUMNS)):.0f}%"


def wr2_dept_db_for_filter_label(label: str) -> str:
    for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
        if col_label == label:
            return dept_db
    for col_label, dept_db in WR2_DEPT_COLUMNS:
        if col_label == label:
            return dept_db
    return label


def wr2_plan_facility(row: Dict[str, Any]) -> str:
    return safe_str(
        row.get("facility")
        or row.get("facility_building")
        or row.get("title_display")
    )


def wr2_plan_discipline(row: Dict[str, Any]) -> str:
    return safe_str(
        row.get("discipline") or row.get("construction_discipline")
    )


def wr2_plan_crew(row: Dict[str, Any]) -> str:
    return safe_str(row.get("crew") or row.get("crew_id"))


def wr2_dept_badge_for_group(group: pd.DataFrame, dept_db: str) -> str:
    if group.empty or "responsible_department" not in group.columns:
        return WR2_DEPT_BADGE["ОЖИДАЕТ"]
    subset = group[group["responsible_department"].astype(str) == dept_db]
    if subset.empty:
        return WR2_DEPT_BADGE["ОЖИДАЕТ"]
    keys = [norm_check_status_key(v) for v in subset["check_status"]]
    worst = worst_check_status(keys)
    return WR2_DEPT_BADGE.get(worst, WR2_DEPT_BADGE["ОЖИДАЕТ"])


def resolve_war_room_line_outcome(counts: Dict[str, int], group: pd.DataFrame) -> str:
    """Итоговый статус кода (только RU) — агрегация решений Page 21."""
    if counts["total"] == 0:
        return WR2_OUTCOME_WAITING
    if counts["hold"] > 0 or counts["fail"] > 0:
        return WR2_OUTCOME_BLOCKED
    if counts["waiting"] > 0 or counts["total"] < len(WR2_DEPT_COLUMNS):
        return WR2_OUTCOME_WAITING
    if counts["warning"] > 0:
        return WR2_OUTCOME_RISK
    if counts["pass"] == counts["total"]:
        return WR2_OUTCOME_OK
    return WR2_OUTCOME_WAITING


def wr2_action_needed(outcome: str) -> str:
    return {
        WR2_OUTCOME_BLOCKED: "Снять блокировку в допуске",
        WR2_OUTCOME_WAITING: "Завершить проверки",
        WR2_OUTCOME_RISK: "Управленческое решение",
        WR2_OUTCOME_OK: "Готово к включению",
        WR2_OUTCOME_NO_CHECKS: "Отправить код в допуск",
    }.get(outcome, "—")


def wr2_critical_department(group: pd.DataFrame) -> str:
    worst_prio = -1
    worst_label = "—"
    for label, dept_db in WR2_DEPT_COLUMNS:
        subset = (
            group[group["responsible_department"].astype(str) == dept_db]
            if not group.empty and "responsible_department" in group.columns
            else pd.DataFrame()
        )
        if subset.empty:
            prio = STATUS_PRIORITY["ОЖИДАЕТ"]
        else:
            keys = [norm_check_status_key(v) for v in subset["check_status"]]
            worst_key = worst_check_status(keys)
            prio = STATUS_PRIORITY.get(worst_key, 0)
        if prio > worst_prio:
            worst_prio = prio
            worst_label = label
    return worst_label


def wr2_line_has_overdue(group: pd.DataFrame) -> bool:
    if group.empty:
        return False
    if "is_overdue" in group.columns:
        return bool(group["is_overdue"].astype(bool).any())
    if "is_promise_overdue" in group.columns:
        return bool(group["is_promise_overdue"].astype(bool).any())
    return False


def wr2_passport_auto_label(outcome: str) -> str:
    if outcome == WR2_OUTCOME_OK:
        return "Включить"
    if outcome == WR2_OUTCOME_RISK:
        return "Требует решения"
    return "Не включать"


def wr2_mgmt_session_key(plan_line_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in plan_line_id)
    return f"wr2_mgmt_{safe}"


def wr2_risk_reason_text_key(plan_line_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in plan_line_id)
    return f"wr2_risk_reason_text_{safe}"


def wr2_source_display_label(source: Any) -> str:
    raw = safe_str(source)
    return WR2_SOURCE_DISPLAY.get(raw, raw or "—")


def wr2_default_mgmt_decision(outcome: str) -> str:
    if outcome == WR2_OUTCOME_OK:
        return WR2_MGMT_INCLUDE
    return WR2_MGMT_EXCLUDE


def wr2_get_mgmt_decision(row: pd.Series) -> str:
    outcome = safe_str(row.get("outcome"))
    if outcome == WR2_OUTCOME_OK:
        return WR2_MGMT_INCLUDE
    mgmt_key = wr2_mgmt_session_key(safe_str(row.get("plan_line_id")))
    stored = safe_str(st.session_state.get(mgmt_key))
    if stored in WR2_MGMT_NON_CLEAN_OPTIONS:
        return stored
    return wr2_default_mgmt_decision(outcome)


def wr2_get_risk_reason_text(plan_line_id: str) -> str:
    return safe_str(st.session_state.get(wr2_risk_reason_text_key(plan_line_id)))


def wr2_effective_passport_label(row: pd.Series) -> str:
    decision = wr2_get_mgmt_decision(row)
    if decision == WR2_MGMT_INCLUDE:
        return "Включить"
    if decision == WR2_MGMT_INCLUDE_RISK:
        return "С риском"
    if decision == WR2_MGMT_LEAVE_REWORK:
        return "На доработке"
    return "Не включать"


def wr2_row_in_passport_inclusion(row: pd.Series) -> bool:
    outcome = safe_str(row.get("outcome"))
    decision = wr2_get_mgmt_decision(row)
    if decision in (WR2_MGMT_EXCLUDE, WR2_MGMT_LEAVE_REWORK):
        return False
    if outcome == WR2_OUTCOME_OK and decision == WR2_MGMT_INCLUDE:
        return True
    if decision == WR2_MGMT_INCLUDE_RISK:
        return bool(wr2_get_risk_reason_text(safe_str(row.get("plan_line_id"))))
    return False


def wr2_validate_management_decisions(board_df: pd.DataFrame) -> List[str]:
    errors: List[str] = []
    if board_df.empty:
        return errors
    for _, row in board_df.iterrows():
        boq = display_dash(row.get("boq_code"))
        pid = safe_str(row.get("plan_line_id"))
        decision = wr2_get_mgmt_decision(row)
        if decision == WR2_MGMT_INCLUDE_RISK and not wr2_get_risk_reason_text(pid):
            errors.append(
                f"{boq}: для «Включить с риском» укажите основание управленческого решения."
            )
    return errors


def wr2_build_passport_override_payload(
    board_df: pd.DataFrame,
    created_by: str,
) -> Dict[str, Dict[str, Any]]:
    now_iso = datetime.now(timezone.utc).isoformat()
    overrides: Dict[str, Dict[str, Any]] = {}
    for _, row in board_df.iterrows():
        if not wr2_row_in_passport_inclusion(row):
            continue
        pid = safe_str(row.get("plan_line_id"))
        if not pid:
            continue
        outcome = safe_str(row.get("outcome"))
        decision = wr2_get_mgmt_decision(row)
        if outcome == WR2_OUTCOME_OK and decision == WR2_MGMT_INCLUDE:
            continue
        if decision != WR2_MGMT_INCLUDE_RISK:
            continue
        reason = wr2_get_risk_reason_text(pid)
        overrides[pid] = {
            "management_override": True,
            "override_by": created_by,
            "override_at": now_iso,
            "override_reason": reason,
            "override_risk_comment": reason,
            "override_basis": "War Room management override",
        }
    return overrides


def wr2_compute_passport_inclusion_rows(board_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, row in board_df.iterrows():
        included = wr2_row_in_passport_inclusion(row)
        rows.append(
            {
                "BOQ-код": display_dash(row.get("boq_code")),
                "Итог допуска": safe_str(row.get("outcome")),
                "Управленческое решение": wr2_get_mgmt_decision(row),
                "Включать в паспорт": "Да" if included else "Нет",
                "Основание": (
                    wr2_get_risk_reason_text(safe_str(row.get("plan_line_id")))
                    if wr2_get_mgmt_decision(row) == WR2_MGMT_INCLUDE_RISK
                    else "—"
                ),
            }
        )
    return pd.DataFrame(rows)


def wr2_create_monthly_passport_with_overrides(
    project_code: str,
    month_key: str,
    created_by: str,
    board_df: pd.DataFrame,
) -> Dict[str, Any]:
    overrides_by_line = wr2_build_passport_override_payload(board_df, created_by)
    inclusion_ids = {
        safe_str(row.get("plan_line_id"))
        for _, row in board_df.iterrows()
        if wr2_row_in_passport_inclusion(row) and safe_str(row.get("plan_line_id"))
    }
    original_read = monthly_passport_service._read_override_from_queue
    original_resolve = monthly_passport_service._resolve_admission_status
    ctx: Dict[str, str] = {"line_id": ""}

    def _patched_read_override(queue_row: Dict[str, Any]) -> Dict[str, Any]:
        ctx["line_id"] = safe_str(queue_row.get("line_id"))
        data = original_read(queue_row)
        patch = overrides_by_line.get(ctx["line_id"])
        if patch:
            data.update(patch)
        return data

    def _patched_resolve(counts: Any, has_override: bool) -> str:
        lid = ctx["line_id"]
        if lid and inclusion_ids and lid not in inclusion_ids:
            return "BLOCKED"
        if lid in overrides_by_line:
            has_override = True
        status = original_resolve(counts, has_override)
        if lid in overrides_by_line and status in ("BLOCKED", "WAITING_CHECKS"):
            return "APPROVED_BY_OVERRIDE"
        return status

    monthly_passport_service._read_override_from_queue = _patched_read_override
    monthly_passport_service._resolve_admission_status = _patched_resolve
    try:
        return create_monthly_passport(
            project_code=project_code,
            month_key=month_key,
            created_by=created_by,
        )
    finally:
        monthly_passport_service._read_override_from_queue = original_read
        monthly_passport_service._resolve_admission_status = original_resolve


def build_war_room_read_model(
    constraints_df: pd.DataFrame,
    v2_df: pd.DataFrame,
    queue_df: pd.DataFrame,
) -> pd.DataFrame:
    """1 строка = 1 plan_line_id. v2 first, legacy queue fallback."""
    constraints_by_line = build_constraints_by_line_id(constraints_df)
    plan_meta: Dict[str, Dict[str, Any]] = {}

    if not v2_df.empty:
        for _, row in v2_df.iterrows():
            status = safe_str(row.get("status"))
            if status and status != V2_STATUS_SENT:
                continue
            pid = safe_str(row.get("plan_line_id"))
            if not pid:
                continue
            facility = wr2_plan_facility(row.to_dict())
            plan_meta[pid] = {
                "plan_line_id": pid,
                "project_code": safe_str(row.get("project_code")),
                "month_key": safe_str(row.get("month_key")),
                "boq_code": safe_str(row.get("boq_code")),
                "boq_name": safe_str(row.get("boq_name")),
                "crew": wr2_plan_crew(row.to_dict()),
                "facility": facility,
                "discipline": wr2_plan_discipline(row.to_dict()),
                "planned_qty": safe_num(row.get("planned_qty")),
                "plan_value": safe_num(row.get("plan_value")),
                "queue_display": derive_construction_queue_from_facility(facility),
                "title_display": facility,
                "system_display": display_dash(row.get("system")),
                "package_display": display_dash(row.get("iwp")),
                "source": "v2",
            }

    for line_id, group in constraints_by_line.items():
        if line_id in plan_meta:
            continue
        first = group.iloc[0]
        facility = wr2_plan_facility(first.to_dict())
        plan_meta[line_id] = {
            "plan_line_id": line_id,
            "project_code": safe_str(first.get("project_code")),
            "month_key": safe_str(first.get("month_key")),
            "boq_code": safe_str(first.get("boq_code")),
            "boq_name": safe_str(first.get("boq_name")),
            "crew": wr2_plan_crew(first.to_dict()),
            "facility": facility,
            "discipline": wr2_plan_discipline(first.to_dict()),
            "planned_qty": safe_num(first.get("planned_qty")),
            "plan_value": safe_num(first.get("plan_value")),
            "queue_display": derive_construction_queue_from_facility(facility),
            "title_display": facility,
            "system_display": "—",
            "package_display": "—",
            "source": "constraints",
        }

    if not queue_df.empty:
        for _, qrow in queue_df.iterrows():
            lid = safe_str(qrow.get("line_id"))
            if not lid or lid in plan_meta:
                continue
            facility = wr2_plan_facility(qrow.to_dict())
            plan_meta[lid] = {
                "plan_line_id": lid,
                "project_code": safe_str(qrow.get("project_code")),
                "month_key": safe_str(qrow.get("month_key")),
                "boq_code": safe_str(qrow.get("boq_code")),
                "boq_name": safe_str(qrow.get("boq_name")),
                "crew": wr2_plan_crew(qrow.to_dict()),
                "facility": facility,
                "discipline": wr2_plan_discipline(qrow.to_dict()),
                "planned_qty": safe_num(qrow.get("planned_qty")),
                "plan_value": safe_num(qrow.get("plan_value")),
                "queue_display": derive_construction_queue_from_facility(facility),
                "title_display": facility,
                "system_display": "—",
                "package_display": "—",
                "source": "legacy_queue",
            }

    rows: List[Dict[str, Any]] = []
    for pid, meta in plan_meta.items():
        group = constraints_by_line.get(pid, pd.DataFrame())
        counts = count_line_constraint_statuses(group)
        outcome = resolve_war_room_line_outcome(counts, group)
        classic_outcome = wr2_outcome_for_classic(outcome)
        check_statuses = (
            [norm_check_status_key(v) for v in group["check_status"]]
            if not group.empty and "check_status" in group.columns
            else []
        )
        row_data: Dict[str, Any] = {
            **meta,
            "plan_value_num": meta.get("plan_value", 0.0),
            "outcome": outcome,
            "classic_outcome": classic_outcome,
            "logic_outcome": build_admission_logic_explanation(counts, group),
            "action_needed": build_action_needed(classic_outcome),
            "critical_department": wr2_critical_department(group),
            "has_overdue": wr2_line_has_overdue(group),
            "passport_include": passport_includes_outcome(classic_outcome),
            "reason": line_reason_summary(group, classic_outcome),
            "hold_count": counts["hold"],
            "fail_count": counts["fail"],
            "warning_count": counts["warning"],
            "waiting_count": counts["waiting"],
            "checks_percent": wr2_checks_percent(counts),
            "_check_statuses": check_statuses,
            "_sort": WR2_OUTCOME_SORT.get(outcome, 99),
        }
        for col_label, dept_db in WR2_DEPT_COLUMNS:
            row_data[f"dept_{col_label}"] = wr2_dept_badge_for_group(group, dept_db)
        for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
            row_data[f"classic_{col_label}"] = dept_status_for_group(group, dept_db)
        rows.append(row_data)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    return result.sort_values(["_sort", "plan_value_num"], ascending=[True, False])


def apply_war_room_plan_filters(
    board_df: pd.DataFrame,
    *,
    project: str,
    month: str,
    queue: str,
    title: str,
    discipline: str,
    department: str,
    outcome: str,
    check_status: str,
    overdue_only: bool,
    search_boq: str,
) -> pd.DataFrame:
    if board_df.empty:
        return board_df
    result = board_df.copy()
    if project != "Все":
        result = result[result["project_code"].astype(str) == project]
    if month != "Все":
        result = result[result["month_key"].astype(str) == month]
    if queue != "Все":
        result = result[result["queue_display"].astype(str) == queue]
    if title != "Все":
        result = result[result["title_display"].astype(str) == title]
    if discipline != "Все":
        result = result[result["discipline"].astype(str) == discipline]
    if outcome != "Все":
        result = result[result["outcome"].astype(str) == outcome]
    if department != "Все":
        classic_col = f"classic_{department}"
        if classic_col in result.columns:
            result = result[
                result[classic_col].astype(str).isin(
                    ["Риск", "Удержание", "Не пройдено", "Ожидает проверки", DEPT_STATUS_NO_CHECK]
                )
            ]
        else:
            dept_db = wr2_dept_db_for_filter_label(department)
            result = result[
                result["_check_statuses"].apply(
                    lambda statuses, db=dept_db: any(
                        norm_check_status_key(s) in {"HOLD", "FAIL", "WARNING", "ОЖИДАЕТ"}
                        for s in statuses
                    )
                )
            ]
    if check_status != "Все" and "_check_statuses" in result.columns:
        result = result[
            result["_check_statuses"].apply(lambda statuses: check_status in statuses)
        ]
    if overdue_only:
        result = result[result["has_overdue"].astype(bool)]
    if search_boq.strip():
        q = search_boq.strip().lower()
        mask = (
            result["boq_code"].astype(str).str.lower().str.contains(q, na=False)
            | result["boq_name"].astype(str).str.lower().str.contains(q, na=False)
        )
        result = result[mask]
    return result


def wr2_filter_opts(df: pd.DataFrame, col: str) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


@st.cache_data(ttl=300)
def load_boq_scope_disciplines() -> List[str]:
    """Дисциплины из BOQ scope — тот же источник, что Constructor v2 (boq_master_api)."""
    try:
        response = (
            supabase.table(TABLE_BOQ_MASTER)
            .select("construction_discipline")
            .limit(10000)
            .execute()
        )
        return sorted(
            {
                safe_str(row.get("construction_discipline"))
                for row in (response.data or [])
                if safe_str(row.get("construction_discipline"))
            }
        )
    except Exception:  # noqa: BLE001
        return []


def wr2_discipline_filter_options(
    constraints_df: pd.DataFrame,
    v2_df: pd.DataFrame,
) -> List[str]:
    """Как Page 21 package_filter_options(discipline_display) + BOQ scope из 10B."""
    data_values: List[str] = []
    for df, col in (
        (v2_df, "discipline"),
        (constraints_df, "construction_discipline"),
    ):
        if df.empty or col not in df.columns:
            continue
        data_values.extend(
            df[col].dropna().astype(str).str.strip().tolist()
        )
    merged = list(
        dict.fromkeys(
            [
                *load_boq_scope_disciplines(),
                *sorted({value for value in data_values if value and value != "—"}),
            ]
        )
    )
    return ["Все"] + merged


def inject_war_room_v2_styles() -> None:
    st.markdown(
        """
        <style>
        .war-room-v2-filters [data-testid="stSelectbox"] > div > div,
        .war-room-v2-filters [data-testid="stTextInput"] input {
            min-height: 2.05rem;
            font-size: 0.86rem;
        }
        .war-room-v2-kpi [data-testid="stMetric"] {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.35rem 0.5rem;
        }
        .war-room-v2-kpi [data-testid="stMetricLabel"] {
            font-size: 0.78rem;
        }
        .war-room-v2-kpi [data-testid="stMetricValue"] {
            font-size: 1.05rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def style_war_room_board_table(df_in: pd.DataFrame):
    dept_cols = [label for label, _ in WR2_BOARD_DEPT_DISPLAY if label in df_in.columns]
    styled_cols = dept_cols.copy()
    if "Итог допуска" in df_in.columns:
        styled_cols.append("Итог допуска")

    def _bg(value: Any) -> str:
        text = safe_str(value)
        if text in ADMISSION_OUTCOME_BG:
            return ADMISSION_OUTCOME_BG[text]
        if text in WR2_OUTCOME_BG:
            return WR2_OUTCOME_BG[text]
        if text in DEPT_STATUS_BG:
            return DEPT_STATUS_BG[text]
        return ""

    styler = df_in.style
    if not styled_cols:
        return styler
    bg_fn = lambda v: _bg(v)  # noqa: E731
    subset = pd.IndexSlice[:, styled_cols]
    if hasattr(styler, "map"):
        return styler.map(bg_fn, subset=subset)
    return styler.applymap(bg_fn, subset=subset)


def render_war_room_v2_kpis(board_df: pd.DataFrame) -> None:
    if board_df.empty:
        st.caption("Нет кодов в выбранном срезе.")
        return
    total = len(board_df)
    ok_cnt = int((board_df["outcome"] == WR2_OUTCOME_OK).sum())
    risk_cnt = int((board_df["outcome"] == WR2_OUTCOME_RISK).sum())
    blocked_cnt = int((board_df["outcome"] == WR2_OUTCOME_BLOCKED).sum())
    wait_cnt = int(
        (board_df["outcome"].isin([WR2_OUTCOME_WAITING, WR2_OUTCOME_NO_CHECKS])).sum()
    )
    value_ok = float(
        board_df.loc[board_df["outcome"] == WR2_OUTCOME_OK, "plan_value_num"].sum()
    )
    value_risk = float(
        board_df.loc[
            board_df["outcome"].isin([WR2_OUTCOME_RISK, WR2_OUTCOME_BLOCKED, WR2_OUTCOME_WAITING]),
            "plan_value_num",
        ].sum()
    )
    st.markdown('<div class="war-room-v2-kpi">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Всего кодов", total)
    c2.metric("Допущено", ok_cnt)
    c3.metric("Допущено с риском", risk_cnt)
    c4.metric("Заблокировано", blocked_cnt)
    c5.metric("Ожидает проверки", wait_cnt)
    c6.metric("Стоимость допущено", money_ru_compact(value_ok))
    c7.metric("Стоимость ограничений", money_ru_compact(value_risk))
    st.markdown("</div>", unsafe_allow_html=True)


def render_war_room_v2_filters(
    full_board: pd.DataFrame,
    constraints_df: pd.DataFrame,
    v2_df: pd.DataFrame,
) -> Dict[str, Any]:
    wr2_init_filter_defaults(full_board)
    check_status_opts = filter_options_ru(
        constraints_df, "check_status", CHECK_STATUS_RU
    )
    discipline_opts = wr2_discipline_filter_options(constraints_df, v2_df)
    if st.session_state.get(WR2_FILTER_KEYS["discipline"]) not in discipline_opts:
        st.session_state[WR2_FILTER_KEYS["discipline"]] = "Все"

    inject_war_room_v2_styles()
    st.markdown("### Срез War Room")
    with st.container(border=True):
        st.markdown('<div class="war-room-v2-filters">', unsafe_allow_html=True)
        r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns(6)
        r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns([1.0, 1.1, 0.7, 1.3, 0.6])

        project_sel = r1c1.selectbox(
            "Проект",
            wr2_filter_opts(full_board, "project_code"),
            key=WR2_FILTER_KEYS["project"],
        )
        month_sel = r1c2.selectbox(
            "Месяц",
            wr2_month_filter_options(),
            key=WR2_FILTER_KEYS["month"],
        )
        queue_sel = r1c3.selectbox(
            "Очередь",
            WR2_QUEUE_OPTIONS,
            key=WR2_FILTER_KEYS["queue"],
        )
        title_sel = r1c4.selectbox(
            "Титул",
            wr2_filter_opts(full_board, "title_display"),
            key=WR2_FILTER_KEYS["title"],
        )
        discipline_sel = r1c5.selectbox(
            "Дисциплина",
            discipline_opts,
            key=WR2_FILTER_KEYS["discipline"],
        )
        outcome_sel = r1c6.selectbox(
            "Итог допуска",
            WR2_OUTCOME_FILTER_OPTIONS,
            key=WR2_FILTER_KEYS["outcome"],
        )

        dept_opts = ["Все"] + [label for label, _ in ADMISSION_DEPT_COLUMNS]
        department_sel = r2c1.selectbox(
            "Отдел",
            dept_opts,
            key=WR2_FILTER_KEYS["department"],
        )
        check_status_sel = r2c2.selectbox(
            "Статус проверки",
            check_status_opts,
            format_func=lambda v: CHECK_STATUS_RU.get(v, v) if v != "Все" else "Все",
            key=WR2_FILTER_KEYS["check_status"],
        )
        overdue_only = r2c3.checkbox(
            "Просрочка",
            key=WR2_FILTER_KEYS["overdue"],
        )
        search_boq = r2c4.text_input(
            "Поиск BOQ",
            key=WR2_FILTER_KEYS["search_boq"],
            placeholder="Код / наименование",
        )
        if r2c5.button("Сбросить", key="wr2_filter_reset"):
            for sk in WR2_FILTER_KEYS.values():
                if sk == WR2_FILTER_KEYS["overdue"]:
                    st.session_state[sk] = False
                elif sk == WR2_FILTER_KEYS["search_boq"]:
                    st.session_state[sk] = ""
                elif sk == WR2_FILTER_KEYS["month"]:
                    st.session_state[sk] = wr2_default_month(full_board)
                else:
                    st.session_state[sk] = "Все"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    return {
        "project": project_sel,
        "month": month_sel,
        "queue": queue_sel,
        "title": title_sel,
        "discipline": discipline_sel,
        "department": department_sel,
        "outcome": outcome_sel,
        "check_status": check_status_sel,
        "overdue_only": overdue_only,
        "search_boq": search_boq,
    }


def render_war_room_v2_board(board_df: pd.DataFrame) -> None:
    st.markdown("### Строки месячного плана — итог допуска")
    st.caption(
        "Одна строка = один код месячного плана (`plan_line_id`). "
        "Агрегация решений отделов из Page 21. Редактирование допуска — только на Page 21."
    )
    if board_df.empty:
        st.info("Нет кодов по выбранным фильтрам.")
        return

    display_rows: List[Dict[str, Any]] = []
    for _, row in board_df.iterrows():
        pid = safe_str(row.get("plan_line_id"))
        outcome_display = safe_str(row.get("classic_outcome") or row.get("outcome"))
        row_dict: Dict[str, Any] = {
            "Проект": display_dash(row.get("project_code")),
            "Очередь": display_dash(row.get("queue_display")),
            "Титул": display_dash(row.get("title_display")),
            "Система": display_dash(row.get("system_display")),
            "Пакет": display_dash(row.get("package_display")),
            "BOQ-код": display_dash(row.get("boq_code")),
            "Наименование": display_dash(row.get("boq_name")),
            "Звено": display_dash(row.get("crew")),
            "Плановый объём": (
                f"{safe_num(row.get('planned_qty')):,.3f}".replace(",", " ")
                if safe_num(row.get("planned_qty"))
                else "—"
            ),
            "Плановая стоимость": money_ru(row.get("plan_value_num")),
            "Итог допуска": outcome_display,
            "Логика итога": display_dash(row.get("logic_outcome")),
            "Что нужно сделать": display_dash(row.get("action_needed")),
            "Причина блокировки / риска": display_dash(row.get("reason")),
            "HOLD count": int(safe_num(row.get("hold_count"))),
            "FAIL count": int(safe_num(row.get("fail_count"))),
            "WARNING count": int(safe_num(row.get("warning_count"))),
            "WAITING count": int(safe_num(row.get("waiting_count"))),
            "% проверок": safe_str(row.get("checks_percent")),
            "Включать в паспорт": wr2_effective_passport_label(row),
            "_plan_line_id": pid,
        }
        for display_label, classic_label in WR2_BOARD_DEPT_DISPLAY:
            row_dict[display_label] = safe_str(row.get(f"classic_{classic_label}"))
        display_rows.append(row_dict)

    show = pd.DataFrame(display_rows)
    show = show[[col for col in WR2_BOARD_TABLE_COLUMNS if col in show.columns]]
    st.caption(f"Показано {len(show)} кодов.")
    st.dataframe(
        style_war_room_board_table(show),
        use_container_width=True,
        hide_index=True,
        height=min(560, 80 + 35 * max(len(show), 1)),
    )

    with st.expander("Технические идентификаторы", expanded=False):
        ids = board_df[["boq_code", "plan_line_id", "month_key", "source"]].copy()
        ids["Источник"] = ids["source"].apply(wr2_source_display_label)
        ids = ids.drop(columns=["source"])
        ids.columns = ["BOQ-код", "plan_line_id", "Месяц", "Источник"]
        st.dataframe(ids, use_container_width=True, hide_index=True)


def render_war_room_v2_management_panel(board_df: pd.DataFrame) -> None:
    st.markdown("### Управленческое решение по паспорту")
    st.info(
        "**Назначение блока:** управленческий выбор — какие коды включить в Monthly Passport Plan, "
        "если итог допуска отделов не является чистым «Допущено».\n\n"
        "Это **не** допуск отдела и **не** Page 21. Здесь нельзя менять `check_status`, "
        "решения отделов и статусы проверок. Блок фиксирует только управленческое решение "
        "руководства по включению в паспорт (пока в `session_state`, без записи в БД)."
    )
    st.caption(
        "Отдельный управленческий слой. Не изменяет `check_status` и не дублирует Page 21. "
        "Сохранение в БД — в следующих фазах."
    )
    if board_df.empty:
        return

    clean = board_df[board_df["outcome"] == WR2_OUTCOME_OK]
    non_clean = board_df[board_df["outcome"].isin(WR2_NON_CLEAN_OUTCOMES)]

    if not clean.empty:
        st.success(
            f"Автоматически включаются в паспорт: **{len(clean)}** код(ов) с итогом «Допущено»."
        )

    if non_clean.empty:
        st.info("Нет кодов, требующих управленческого решения по паспорту.")
        return

    for _, row in non_clean.iterrows():
        pid = safe_str(row.get("plan_line_id"))
        outcome = safe_str(row.get("outcome"))
        boq = display_dash(row.get("boq_code"))
        mgmt_key = wr2_mgmt_session_key(pid)
        reason_key = wr2_risk_reason_text_key(pid)
        if mgmt_key not in st.session_state:
            st.session_state[mgmt_key] = wr2_default_mgmt_decision(outcome)

        st.markdown(f"**{boq}** — {outcome}")
        c1, c2 = st.columns([1.2, 1.8])
        with c1:
            choice = st.selectbox(
                "Управленческое решение",
                WR2_MGMT_NON_CLEAN_OPTIONS,
                key=mgmt_key,
            )
        with c2:
            if choice == WR2_MGMT_INCLUDE_RISK:
                st.text_area(
                    "Основание управленческого решения",
                    placeholder=WR2_RISK_REASON_PLACEHOLDER,
                    key=reason_key,
                    height=80,
                )
            elif choice == WR2_MGMT_LEAVE_REWORK:
                st.caption("Код остаётся вне паспорта до завершения доработки отделами.")
            else:
                st.caption("Код исключён из паспорта управленческим решением.")

        if outcome == WR2_OUTCOME_BLOCKED and choice == WR2_MGMT_INCLUDE_RISK:
            st.warning(
                "Код заблокирован отделом допуска. Включение возможно только как управленческий риск."
            )
            mgmt_reason = wr2_get_risk_reason_text(pid) or "— (укажите основание)"
            st.markdown(
                f"- **BOQ:** {boq}\n"
                f"- **Критичный отдел:** {display_dash(row.get('critical_department'))}\n"
                f"- **Причина блокировки:** {display_dash(row.get('reason'))}\n"
                f"- **Основание руководства:** {mgmt_reason}"
            )
        st.markdown("---")


def render_war_room_v2_executive(
    constraints_df: pd.DataFrame,
    v2_df: pd.DataFrame,
    queue_df: pd.DataFrame,
) -> None:
    full_board = build_war_room_read_model(constraints_df, v2_df, queue_df)
    if full_board.empty:
        st.info(
            "Нет кодов для War Room. Отправьте план из конструктора 10B в допуск "
            "или сформируйте проверки в контуре допуска."
        )
        return

    filters = render_war_room_v2_filters(full_board, constraints_df, v2_df)
    board_df = apply_war_room_plan_filters(
        full_board,
        project=filters["project"],
        month=filters["month"],
        queue=filters["queue"],
        title=filters["title"],
        discipline=filters["discipline"],
        department=filters["department"],
        outcome=filters["outcome"],
        check_status=filters["check_status"],
        overdue_only=filters["overdue_only"],
        search_boq=filters["search_boq"],
    )

    render_war_room_v2_kpis(board_df)
    st.markdown("---")
    render_war_room_v2_board(board_df)
    st.markdown("---")
    render_war_room_v2_management_panel(board_df)
    st.session_state["wr2_passport_board_df"] = board_df.copy()


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


def render_passport_formation(
    project_sel: str,
    month_sel: str,
    board_df: Optional[pd.DataFrame] = None,
) -> None:
    st.markdown("### Формирование паспорта месяца")
    st.info(
        "**Назначение кнопки:** сформировать / создать Monthly Plan Passport по выбранному "
        "проекту и месяцу с учётом управленческих решений War Room.\n\n"
        "**Включаются:** чисто допущенные коды (`Допущено`) и коды с решением "
        "«Включить с риском» при заполненном основании.\n\n"
        "**Исключаются:** «Не включать», «Оставить на доработке», заблокированные и "
        "ожидающие коды без управленческого override."
    )
    st.caption(
        "После снятия HOLD/FAIL ограничений можно сформировать Approved Monthly Plan Passport. "
        "Управленческий override не меняет итог допуска отделов — только состав паспорта."
    )

    if project_sel == "Все" or month_sel == "Все":
        st.warning("Выберите конкретный проект и месяц для формирования паспорта.")
        return

    scoped_board = board_df
    if scoped_board is None:
        scoped_board = st.session_state.get("wr2_passport_board_df")
    if scoped_board is None or scoped_board.empty:
        st.warning("Нет данных War Room для формирования паспорта по выбранным фильтрам.")
        return

    scoped_board = scoped_board[
        (scoped_board["project_code"].astype(str) == project_sel)
        & (scoped_board["month_key"].astype(str) == month_sel)
    ].copy()
    if scoped_board.empty:
        st.warning(
            f"Нет кодов War Room для проекта {project_sel} и месяца {month_sel} "
            "по текущим фильтрам."
        )
        return

    inclusion_preview = wr2_compute_passport_inclusion_rows(scoped_board)
    included_cnt = int((inclusion_preview["Включать в паспорт"] == "Да").sum())
    st.markdown("#### Состав паспорта (по управленческим решениям)")
    st.caption(f"Будет включено строк: {included_cnt} из {len(inclusion_preview)}.")
    st.dataframe(inclusion_preview, use_container_width=True, hide_index=True)

    validation_errors = wr2_validate_management_decisions(scoped_board)
    if validation_errors:
        for err in validation_errors:
            st.error(err)

    created_by = st.text_input(
        "Кто утверждает (created_by / approved_by)",
        value="Пользователь Streamlit",
        key="passport_created_by",
    )

    can_submit = not validation_errors and included_cnt > 0
    if not can_submit and not validation_errors:
        st.warning("Нет строк для включения в паспорт по текущим управленческим решениям.")

    if st.button(
        "Сформировать Monthly Plan Passport",
        key="create_monthly_passport_btn",
        disabled=not can_submit,
    ):
        summary = wr2_create_monthly_passport_with_overrides(
            project_code=project_sel,
            month_key=month_sel,
            created_by=created_by.strip() or "Пользователь Streamlit",
            board_df=scoped_board,
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


def render_legacy_war_room(
    base_df: pd.DataFrame,
    project_sel: str,
    month_sel: str,
    facility_sel: str,
    discipline_sel: str,
    gate_sel: str,
    department_sel: str,
    check_status_sel: str,
    resolution_sel: str,
    overdue_only: bool,
) -> None:
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

    render_admission_plan_summary(
        base_df,
        queue_df,
        project_sel,
        month_sel,
        facility_sel,
        discipline_sel,
    )

    st.markdown("### KPI по ограничениям")
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


def main() -> None:
    st.title("War Room ограничений")
    st.caption(
        "Итог допуска месячного плана и готовность кодов к формированию паспорта. "
        "Решения отделов принимаются на Page 21; здесь — агрегированный executive-слой."
    )

    base_df = load_constraints()
    if base_df.empty:
        st.info(EMPTY_MSG)
        return

    v2_df = load_v2_plan_lines()
    queue_df = load_review_queue()

    render_war_room_v2_executive(base_df, v2_df, queue_df)

    st.markdown("---")
    render_passport_formation(
        st.session_state.get(WR2_FILTER_KEYS["project"], "Все"),
        st.session_state.get(WR2_FILTER_KEYS["month"], "Все"),
        board_df=st.session_state.get("wr2_passport_board_df"),
    )

    with st.expander(
        "Классический War Room — детализация по ограничениям (legacy)",
        expanded=False,
    ):
        st.markdown("### Фильтры (ограничения)")
        f1, f2, f3, f4 = st.columns(4)
        f5, f6, f7, f8, f9 = st.columns(5)

        project_sel = f1.selectbox(
            "Проект",
            filter_options(base_df, "project_code"),
            key="legacy_wr_project",
        )
        month_sel = f2.selectbox(
            "Месяц",
            filter_options(base_df, "month_key"),
            key="legacy_wr_month",
        )
        facility_sel = f3.selectbox(
            "Здание / объект",
            filter_options(base_df, "facility_building"),
            key="legacy_wr_facility",
        )
        discipline_sel = f4.selectbox(
            "Дисциплина",
            filter_options(base_df, "construction_discipline"),
            key="legacy_wr_discipline",
        )
        gate_sel = f5.selectbox(
            "Контур допуска",
            filter_options_ru(base_df, "gate_layer", GATE_LAYER_RU),
            format_func=lambda v: ru_label(v, GATE_LAYER_RU),
            key="legacy_wr_gate",
        )
        department_sel = f6.selectbox(
            "Отдел",
            filter_options(base_df, "responsible_department"),
            format_func=lambda v: dept_ui(v) if v != "Все" else "Все",
            key="legacy_wr_department",
        )
        check_status_sel = f7.selectbox(
            "Статус проверки",
            filter_options_ru(base_df, "check_status", CHECK_STATUS_RU),
            format_func=lambda v: ru_label(v, CHECK_STATUS_RU),
            key="legacy_wr_check_status",
        )
        resolution_sel = f8.selectbox(
            "Статус устранения",
            filter_options_ru(base_df, "resolution_status", RESOLUTION_RU),
            format_func=lambda v: ru_label(v, RESOLUTION_RU),
            key="legacy_wr_resolution",
        )
        overdue_only = f9.checkbox("Только просроченные", key="legacy_wr_overdue")

        render_legacy_war_room(
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


if __name__ == "__main__":
    main()
