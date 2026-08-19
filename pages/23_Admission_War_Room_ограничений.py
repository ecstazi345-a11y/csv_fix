from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from services.constraint_display import (
    constraint_block_substance,
    constraint_decision_line_compact,
    is_generic_block_reason,
    registry_specific_block_reason,
)
from services.monthly_passport_service import create_monthly_passport
import services.monthly_passport_service as monthly_passport_service
from services.constraints_loader import fetch_all_constraints
from services.monthly_plan_labor_service import load_labor_lines
from services.monthly_plan_management_decisions import (
    DECISION_DEFER,
    DECISION_EXCLUDE,
    DECISION_INCLUDE,
    DECISION_INCLUDE_RISK,
    apply_management_decision,
    build_commitment_snapshots,
    cancel_management_decision,
    clear_management_decisions_cache,
    load_management_decisions,
    merge_commitment_payload,
    normalize_decision_code,
    optional_float,
    validate_approved_commitment_qty,
)
from services.monthly_plan_resource_economic_service import (
    theoretical_feasible_qty_by_plan_line,
)
from services.monthly_resource_plan_service import load_approved_capacity
from services.perf_audit import finish_page, stage, start_page
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

# Отображение в ячейках отделов (только RU) — источник данных, без изменений
DEPT_STATUS_LABEL = {
    "PASS": "Пройдено",
    "WARNING": "Риск",
    "HOLD": "Удержание",
    "FAIL": "Не пройдено",
    "ОЖИДАЕТ": "Ожидает проверки",
}

# Единый display mapping статусов — aligned with Page 21 DECISION_REGISTRY_CHECK_STATUS_DISPLAY
WR2_REGISTRY_ADMISSION_TEXT_STYLE = {
    "Проверяется": "color: #2E5B9A;",
    "Допущено": "color: #2F6B4F;",
    "Заблокировано": "color: #9B3D3D;",
    "Требует уточнения": "color: #92610E;",
}

# Итоговое управленческое решение (колонка реестра + корзины драфта)
WR2_FINAL_DECISION_PENDING = "Ожидает решения"
WR2_FINAL_DECISION_IN_OBLIGATION = "В обязательстве"
WR2_FINAL_DECISION_IN_OBLIGATION_RISK = "В обязательстве с риском"
WR2_FINAL_DECISION_DEFERRED = "Отложено"
WR2_FINAL_DECISION_EXCLUDED = "Исключено"

WR2_FINAL_DECISION_BG = {
    WR2_FINAL_DECISION_PENDING: "background-color: #f0f9ff;",
    WR2_FINAL_DECISION_IN_OBLIGATION: "background-color: #ecfdf5;",
    WR2_FINAL_DECISION_IN_OBLIGATION_RISK: "background-color: #fefce8;",
    WR2_FINAL_DECISION_DEFERRED: "background-color: #f4f4f5;",
    WR2_FINAL_DECISION_EXCLUDED: "background-color: #ffedd5;",
}

WR2_BASKET_COMMENT_EMPTY = "Не заполнен"
WR2_BASKET_DEADLINE_EMPTY = "Не определён"
WR2_BASKET_COMMENT_DISPLAY_MAX = 100

WR2_FINAL_DECISION_COLUMN_HELP = (
    "Последнее управленческое решение, принятое после проверки допуска по отделам."
)

# Display-only: membership in the approved/current monthly passport snapshot
WR2_PASSPORT_STATUS_NOT_IN = "Не включён"
WR2_PASSPORT_STATUS_IN = "Включён"
WR2_PASSPORT_STATUS_IN_RISK = "Включён с риском"
WR2_PASSPORT_STATUS_COLUMN = "Статус в паспорте"
WR2_PASSPORT_STATUS_COLUMN_HELP = (
    "Факт включения кода в действующий паспорт месяца (snapshot). "
    "Не заменяет управленческое решение."
)
WR2_PASSPORT_CONFLICT_MARK = "⚠"
WR2_PASSPORT_CONFLICT_HELP = (
    "Текущее управленческое решение не совпадает с действующим паспортом месяца."
)
WR2_SESSION_PASSPORT_STATUS_INDEX = "wr2_passport_status_index"

WR2_PASSPORT_STATUS_BG = {
    WR2_PASSPORT_STATUS_IN: "background-color: #ecfdf5;",
    WR2_PASSPORT_STATUS_IN_RISK: "background-color: #fefce8;",
    WR2_PASSPORT_STATUS_NOT_IN: "background-color: #f4f4f5;",
}

WR2_REGISTRY_STATUS_DISPLAY: Dict[str, str] = {
    "Ожидает проверки": "ПРОВЕРЯЕТСЯ",
    "ОЖИДАЕТ": "ПРОВЕРЯЕТСЯ",
    "Пройдено": "ПРОЙДЕНО",
    "PASS": "ПРОЙДЕНО",
    "Риск / требуется уточнение": "УТОЧНЕНИЕ",
    "WARNING": "УТОЧНЕНИЕ",
    "Риск": "УТОЧНЕНИЕ",
    "Удержание / блокировка": "УДЕРЖАНИЕ",
    "HOLD": "УДЕРЖАНИЕ",
    "Удержание": "УДЕРЖАНИЕ",
    "Не пройдено": "ЗАБЛОКИРОВАНО",
    "FAIL": "ЗАБЛОКИРОВАНО",
    "Нет проверки": "НЕТ ПРОВЕРКИ",
    DEPT_STATUS_NO_CHECK: "НЕТ ПРОВЕРКИ",
    ADMISSION_OK: "ПРОЙДЕНО",
    ADMISSION_RISK: "ДОПУЩЕНО С РИСКОМ",
    ADMISSION_BLOCKED: "ЗАБЛОКИРОВАНО",
    ADMISSION_WAITING: "ПРОВЕРЯЕТСЯ",
    ADMISSION_NO_CHECKS: "НЕТ ПРОВЕРКИ",
    WR2_FINAL_DECISION_PENDING: "ОЖИДАЕТ РЕШЕНИЯ",
    WR2_FINAL_DECISION_IN_OBLIGATION: "В ОБЯЗАТЕЛЬСТВЕ",
    WR2_FINAL_DECISION_IN_OBLIGATION_RISK: "В ОБЯЗАТЕЛЬСТВЕ С РИСКОМ",
    WR2_FINAL_DECISION_DEFERRED: "ОТЛОЖЕНО",
    WR2_FINAL_DECISION_EXCLUDED: "ИСКЛЮЧЕНО",
    WR2_PASSPORT_STATUS_NOT_IN: "НЕ ВКЛЮЧЁН",
    WR2_PASSPORT_STATUS_IN: "ВКЛЮЧЁН",
    WR2_PASSPORT_STATUS_IN_RISK: "ВКЛЮЧЁН С РИСКОМ",
}

WR2_REGISTRY_STATUS_TEXT_STYLE = {
    "ПРОВЕРЯЕТСЯ": WR2_REGISTRY_ADMISSION_TEXT_STYLE["Проверяется"],
    "ПРОЙДЕНО": WR2_REGISTRY_ADMISSION_TEXT_STYLE["Допущено"],
    "УТОЧНЕНИЕ": WR2_REGISTRY_ADMISSION_TEXT_STYLE["Требует уточнения"],
    "УДЕРЖАНИЕ": WR2_REGISTRY_ADMISSION_TEXT_STYLE["Заблокировано"],
    "ЗАБЛОКИРОВАНО": WR2_REGISTRY_ADMISSION_TEXT_STYLE["Заблокировано"],
    "НЕ ПРОЙДЕНО": WR2_REGISTRY_ADMISSION_TEXT_STYLE["Заблокировано"],
    "ДОПУЩЕНО С РИСКОМ": WR2_REGISTRY_ADMISSION_TEXT_STYLE["Требует уточнения"],
    "НЕТ ПРОВЕРКИ": "color: #64748b;",
    "ОЖИДАЕТ РЕШЕНИЯ": "color: #475569;",
    "В ОБЯЗАТЕЛЬСТВЕ": "color: #166534;",
    "В ОБЯЗАТЕЛЬСТВЕ С РИСКОМ": "color: #a16207;",
    "ОТЛОЖЕНО": "color: #64748b;",
    "ИСКЛЮЧЕНО": "color: #9a3412;",
    "НЕ ВКЛЮЧЁН": "color: #64748b;",
    "ВКЛЮЧЁН": "color: #166534;",
    "ВКЛЮЧЁН С РИСКОМ": "color: #a16207;",
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

WR2_OUTCOME_TEXT_COLOR = {
    WR2_OUTCOME_BLOCKED: "#9a3412",
    WR2_OUTCOME_OK: "#166534",
    WR2_OUTCOME_RISK: "#a16207",
    WR2_OUTCOME_WAITING: "#475569",
    WR2_OUTCOME_NO_CHECKS: "#6b7280",
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

WR2_MGMT_INCLUDE = "Включить в паспорт"
WR2_MGMT_INCLUDE_RISK = "Включить с риском"
WR2_MGMT_POSTPONE = "Отложить"
WR2_MGMT_EXCLUDE = "Исключить"

WR2_MGMT_OPTIONS = [
    WR2_MGMT_INCLUDE,
    WR2_MGMT_INCLUDE_RISK,
    WR2_MGMT_POSTPONE,
    WR2_MGMT_EXCLUDE,
]

WR2_PASSPORT_DECISIONS = frozenset({WR2_MGMT_INCLUDE, WR2_MGMT_INCLUDE_RISK})

WR2_AUTO_INCLUDE_BASIS = "Авто: чистый допуск"
WR2_BLANK_REASON_MARKERS = frozenset({"", "—", "-", "–", "nan", "None"})

# Обратная совместимость внутренних проверок
WR2_MGMT_LEAVE_REWORK = WR2_MGMT_POSTPONE
WR2_MGMT_NON_CLEAN_OPTIONS = [
    WR2_MGMT_EXCLUDE,
    WR2_MGMT_INCLUDE_RISK,
    WR2_MGMT_POSTPONE,
]

WR2_NON_CLEAN_OUTCOMES = [
    WR2_OUTCOME_BLOCKED,
    WR2_OUTCOME_WAITING,
    WR2_OUTCOME_RISK,
]

WR2_SESSION_COMPOSITION = "wr2_passport_composition"
WR2_SESSION_AUDIT = "wr2_decision_audit_log"
WR2_SESSION_DRAFT = "wr2_passport_is_draft"
WR2_SESSION_FORMED = "wr2_passport_is_formed"
WR2_SESSION_FORMING = "wr2_passport_forming_lock"
WR2_SESSION_SELECTED = "wr2_selected_plan_line_id"
WR2_SESSION_DEFERRED = "wr2_deferred_decisions"
WR2_SESSION_EXCLUDED = "wr2_excluded_decisions"
WR2_SESSION_MGMT_SCOPE = "wr2_mgmt_scope"
WR2_SESSION_MGMT_REHYDRATED_COUNT = "wr2_mgmt_rehydrated_count"
WR2_SESSION_MGMT_REHYDRATED_NOTICE = "wr2_mgmt_rehydrated_notice"
WR2_SESSION_MONTH_BOARD = "wr2_month_board_df"

# DB EN codes → Page 23 session RU labels
WR2_DECISION_EN_TO_SESSION = {
    DECISION_INCLUDE: WR2_MGMT_INCLUDE,
    DECISION_INCLUDE_RISK: WR2_MGMT_INCLUDE_RISK,
    DECISION_EXCLUDE: WR2_MGMT_EXCLUDE,
    DECISION_DEFER: WR2_MGMT_POSTPONE,
}

WR2_MGMT_LABELS = {
    WR2_MGMT_INCLUDE: "Включить в паспорт",
    WR2_MGMT_INCLUDE_RISK: "Включить с риском",
    WR2_MGMT_POSTPONE: "Отложить рассмотрение",
    WR2_MGMT_EXCLUDE: "Исключить из паспорта",
}

WR2_PRIORITY_P1 = "P1 — Критический"
WR2_PRIORITY_P2 = "P2 — Требует решения"
WR2_PRIORITY_P3 = "P3 — Ожидает"
WR2_PRIORITY_ORDER = {
    WR2_PRIORITY_P1: 0,
    WR2_PRIORITY_P2: 1,
    WR2_PRIORITY_P3: 2,
}

WR2_REGISTRY_TABLE_HEIGHT_PX = 36 * 25 + 38  # ~25 visible rows — как «Реестр решений» Page 21
WR2_REGISTRY_SELECT_KEY = "wr2_unified_registry_select"
WR2_PRODUCTIVE_HOURS_PER_PERSON_SHIFT = 8.0

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
    "Итог допуска",
    "Итоговое решение",
    WR2_PASSPORT_STATUS_COLUMN,
    "Почему не допущен",
    "Проект",
    "Очередь",
    "Титул",
    "Дисциплина",
    "Система",
    "Пакет",
    "BOQ-код",
    "Наименование работы",
    *[label for label, _ in WR2_BOARD_DEPT_DISPLAY],
    "Плановый объём",
    "Плановая стоимость",
    "Звено",
    "Людей в звене",
    "Трудозатраты, чел·ч",
    "Длительность, смен",
    "Норма выработки",
    "Стоимость труда / стоимость звена",
    "Труд / стоимость работ, %",
    "Возраст ограничения",
]

# Active blocking-reason aggregation (display-only; does not change outcome logic)
CLOSED_RESOLUTION_STATUSES = frozenset({"RESOLVED", "CANCELLED"})
BLOCKING_REASON_DISPLAY_MAX = 160
BLOCKING_REASON_EMPTY = "Активные причины не зафиксированы"
BLOCKING_REASON_MISSING = "Причина не указана"
ACTIVE_CONSTRAINT_STATUS_RU = {
    "ОЖИДАЕТ": "Ожидает проверки",
    "WARNING": "Требует уточнения",
    "HOLD": "Удержание",
    "FAIL": "Заблокировано",
}
ACTIVE_BLOCKING_STATUS_PRIORITY = {
    "FAIL": 0,
    "HOLD": 1,
    "WARNING": 2,
    "ОЖИДАЕТ": 3,
}


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
    substance = constraint_block_substance(row)
    if substance:
        return substance
    category = safe_str(row.get("constraint_category"))
    return category or "—"


def concrete_blocking_reason_text(row: Any) -> str:
    """Short concrete reason for registry: block_reason → substance (non-generic)."""
    specific = registry_specific_block_reason(row)
    if specific:
        return specific
    substance = constraint_block_substance(row)
    if substance and not is_generic_block_reason(substance):
        return substance
    return ""


def format_blocking_reason_due(row: Any) -> str:
    due = None
    if hasattr(row, "get"):
        due = safe_date(row.get("target_resolution_date"))
        if due is None:
            due = safe_date(row.get("effective_promised_date"))
    return due.strftime("%d.%m.%Y") if due else "Не определён"


def truncate_blocking_reason_display(
    text: str, max_len: int = BLOCKING_REASON_DISPLAY_MAX
) -> str:
    cleaned = safe_str(text)
    if not cleaned:
        return BLOCKING_REASON_EMPTY
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max(0, max_len - 1)] + "…"


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
    import time as _time

    from services.perf_audit import log_supabase_query, perf_audit_enabled

    try:
        t0 = _time.perf_counter()
        response = (
            supabase.table(TABLE_REVIEW_QUEUE).select("*").limit(10000).execute()
        )
        data = response.data or []
        if perf_audit_enabled():
            log_supabase_query(TABLE_REVIEW_QUEUE, _time.perf_counter() - t0, len(data))
        return pd.DataFrame(data)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_constraints() -> pd.DataFrame:
    for table in (VIEW_DASHBOARD_V2, VIEW_DASHBOARD_V1, TABLE_CONSTRAINTS):
        try:
            rows = fetch_all_constraints(supabase, table)
            df = enrich_dataframe(pd.DataFrame(rows))
            if not df.empty:
                return df
        except Exception:  # noqa: BLE001
            continue
    return pd.DataFrame()


@st.cache_data(ttl=300)
def load_v2_plan_lines() -> pd.DataFrame:
    import time as _time

    from services.perf_audit import log_supabase_query, perf_audit_enabled

    try:
        t0 = _time.perf_counter()
        response = (
            supabase.table(TABLE_V2_PLAN_LINES).select("*").limit(10000).execute()
        )
        data = response.data or []
        if perf_audit_enabled():
            log_supabase_query(TABLE_V2_PLAN_LINES, _time.perf_counter() - t0, len(data))
        return pd.DataFrame(data)
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


def wr2_plan_economics(row: Dict[str, Any]) -> Dict[str, float]:
    hours = safe_num(row.get("labor_hours") or row.get("required_hours"))
    cost = safe_num(row.get("labor_cost"))
    qty = safe_num(row.get("planned_qty"))
    plan_val = safe_num(row.get("plan_value"))
    norm = (hours / qty) if qty > 0 else 0.0
    return {
        "labor_hours": hours,
        "labor_cost": cost,
        "norm_hours_per_unit": norm,
        "plan_value_num": plan_val,
        "margin_num": plan_val - cost,
    }


def wr2_format_hours(value: float) -> str:
    if value <= 0:
        return "—"
    return f"{value:,.1f}".replace(",", " ")


def wr2_format_norm(value: float) -> str:
    if value <= 0:
        return "—"
    return f"{value:,.3f}".replace(",", " ")


def wr2_format_crew_size_display(value: Any) -> str:
    crew_size = int(max(safe_num(value), 0))
    if crew_size <= 0:
        return "—"
    return str(crew_size)


def wr2_format_duration_shifts_display(labor_hours: Any, crew_size: Any) -> str:
    safe_hours = safe_num(labor_hours)
    safe_crew_raw = safe_num(crew_size)
    if safe_hours <= 0 or safe_crew_raw <= 0:
        return "—"
    duration = safe_hours / (safe_crew_raw * WR2_PRODUCTIVE_HOURS_PER_PERSON_SHIFT)
    if duration <= 0:
        return "—"
    return f"{duration:,.1f}".replace(",", " ").replace(".", ",") + " смен"


def wr2_format_labor_to_plan_pct_display(labor_cost: Any, plan_value: Any) -> str:
    cost = safe_num(labor_cost)
    plan_val = safe_num(plan_value)
    if plan_val <= 0:
        return "—"
    pct = cost / plan_val * 100.0
    return f"{pct:.1f}".replace(".", ",") + " %"


def wr2_registry_admission_reason_display(row: pd.Series) -> str:
    reason = display_dash(row.get("reason"))
    if reason != "—":
        return reason
    return display_dash(row.get("outcome_status_reason"))


def wr2_outcome_status_reason(group: pd.DataFrame, counts: Dict[str, int]) -> str:
    if counts["total"] == 0:
        return "Проверки не сформированы"
    blockers = depts_with_statuses(group, frozenset({"HOLD", "FAIL"}))
    if blockers:
        return f"Блокируют: {', '.join(blockers)}"
    hold_depts = depts_with_statuses(group, frozenset({"HOLD"}))
    if hold_depts:
        return f"HOLD: {', '.join(hold_depts)}"
    fail_depts = depts_with_statuses(group, frozenset({"FAIL"}))
    if fail_depts:
        return f"FAIL: {', '.join(fail_depts)}"
    waiting_depts = depts_with_statuses(group, frozenset({"ОЖИДАЕТ"}))
    no_check: List[str] = []
    if group.empty or "responsible_department" not in group.columns:
        for col_label, _ in ADMISSION_DEPT_COLUMNS:
            no_check.append(col_label)
    else:
        for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
            subset = group[group["responsible_department"].astype(str) == dept_db]
            if subset.empty:
                no_check.append(col_label)
    if waiting_depts or no_check or counts["waiting"] > 0:
        parts: List[str] = []
        if waiting_depts:
            parts.append(f"Ожидают проверки: {', '.join(waiting_depts)}")
        elif counts["waiting"] > 0:
            parts.append("Ожидают проверки отделов")
        if no_check:
            parts.append(f"Нет проверки: {', '.join(no_check)}")
        return "; ".join(parts)
    if counts["warning"] > 0:
        warn_depts = depts_with_statuses(group, frozenset({"WARNING"}))
        if warn_depts:
            return f"Риск / уточнение: {', '.join(warn_depts)}"
        return "Есть замечания WARNING"
    return "Все проверки пройдены"


def wr2_blocking_departments_text(group: pd.DataFrame) -> str:
    blockers = depts_with_statuses(group, frozenset({"HOLD", "FAIL"}))
    if blockers:
        return ", ".join(blockers)
    warn = depts_with_statuses(group, frozenset({"WARNING"}))
    if warn:
        return f"Риск: {', '.join(warn)}"
    waiting = depts_with_statuses(group, frozenset({"ОЖИДАЕТ"}))
    if waiting:
        return f"Ожидают: {', '.join(waiting)}"
    return "—"


def wr2_init_passport_session() -> None:
    st.session_state.setdefault(WR2_SESSION_COMPOSITION, {})
    st.session_state.setdefault(WR2_SESSION_AUDIT, [])
    st.session_state.setdefault(WR2_SESSION_DRAFT, False)
    st.session_state.setdefault(WR2_SESSION_FORMED, False)
    st.session_state.setdefault(WR2_SESSION_FORMING, False)
    st.session_state.setdefault(WR2_SESSION_DEFERRED, {})
    st.session_state.setdefault(WR2_SESSION_EXCLUDED, {})
    st.session_state.setdefault(WR2_SESSION_MGMT_SCOPE, "")
    st.session_state.setdefault(WR2_SESSION_MGMT_REHYDRATED_COUNT, 0)
    st.session_state.setdefault(WR2_SESSION_MGMT_REHYDRATED_NOTICE, False)


def wr2_mgmt_scope_token(project_code: str, month_key: str) -> str:
    return f"{safe_str(project_code)}|{safe_str(month_key)}"


def wr2_is_concrete_mgmt_scope(project_code: str, month_key: str) -> bool:
    project = safe_str(project_code)
    month = safe_str(month_key)
    return bool(project and month and project != "Все" and month != "Все")


def wr2_clear_session_decision_caches() -> None:
    """Clear UI decision caches only. Does not touch DB."""
    st.session_state[WR2_SESSION_COMPOSITION] = {}
    st.session_state[WR2_SESSION_DEFERRED] = {}
    st.session_state[WR2_SESSION_EXCLUDED] = {}


def wr2_db_decision_to_session_record(db_row: Dict[str, Any]) -> Dict[str, Any]:
    en = normalize_decision_code(db_row.get("decision"))
    ru = WR2_DECISION_EN_TO_SESSION.get(en, WR2_MGMT_EXCLUDE)
    return {
        "boq_code": safe_str(db_row.get("boq_code")),
        "boq_name": safe_str(db_row.get("boq_name")),
        "decision": ru,
        "outcome": safe_str(db_row.get("admission_outcome_at_decision")) or "—",
        "override": bool(db_row.get("management_override")),
        "basis": safe_str(db_row.get("decision_basis")),
        "responsible": safe_str(db_row.get("responsible_person")),
        "review_deadline": safe_str(db_row.get("review_deadline")),
        "comment": safe_str(db_row.get("decision_comment")),
        "risk_description": safe_str(db_row.get("risk_description")),
        "risk_impact": safe_str(db_row.get("risk_impact")),
        "risk_mitigation_owner": safe_str(db_row.get("risk_mitigation_owner")),
        "risk_mitigation_deadline": safe_str(db_row.get("risk_mitigation_deadline")),
        "risk_acceptance_basis": safe_str(db_row.get("risk_acceptance_basis")),
        "risk_manager_comment": safe_str(db_row.get("risk_manager_comment")),
        "risk_deadline": safe_str(db_row.get("risk_mitigation_deadline")) or "—",
        "risk_blocker": safe_str(db_row.get("risk_blocker")) or "—",
        "plan_value": 0.0,
        "labor_hours": 0.0,
        "requested_qty_snapshot": optional_float(db_row.get("requested_qty_snapshot")),
        "feasible_qty_snapshot": optional_float(db_row.get("feasible_qty_snapshot")),
        "approved_commitment_qty": optional_float(db_row.get("approved_commitment_qty")),
        "committed_work_value": optional_float(db_row.get("committed_work_value")),
        "committed_required_hours": optional_float(db_row.get("committed_required_hours")),
        "committed_labor_cost": optional_float(db_row.get("committed_labor_cost")),
        "added_at": safe_str(db_row.get("decided_at")) or datetime.now(timezone.utc).isoformat(),
        "decided_by": safe_str(db_row.get("decided_by")),
        "from_db": True,
    }


def wr2_apply_rehydrate_from_rows(rows: List[Dict[str, Any]]) -> int:
    """Replace session decision baskets from ACTIVE DB rows (SoT)."""
    comp: Dict[str, Any] = {}
    deferred: Dict[str, Any] = {}
    excluded: Dict[str, Any] = {}
    for db_row in rows:
        pid = safe_str(db_row.get("plan_line_id"))
        if not pid:
            continue
        en = normalize_decision_code(db_row.get("decision"))
        record = wr2_db_decision_to_session_record(db_row)
        ru = safe_str(record.get("decision"))
        st.session_state[wr2_mgmt_session_key(pid)] = ru
        if en in (DECISION_INCLUDE, DECISION_INCLUDE_RISK):
            comp[pid] = record
        elif en == DECISION_EXCLUDE:
            excluded[pid] = record
        elif en == DECISION_DEFER:
            deferred[pid] = record
    st.session_state[WR2_SESSION_COMPOSITION] = comp
    st.session_state[WR2_SESSION_DEFERRED] = deferred
    st.session_state[WR2_SESSION_EXCLUDED] = excluded
    st.session_state[WR2_SESSION_MGMT_REHYDRATED_COUNT] = len(rows)
    return len(rows)


def wr2_rehydrate_management_decisions(project_code: str, month_key: str) -> int:
    """
    Load ACTIVE decisions for concrete project+month into session_state.
    Project/Month = «Все» → no-op (does not clear).
    """
    if not wr2_is_concrete_mgmt_scope(project_code, month_key):
        return int(st.session_state.get(WR2_SESSION_MGMT_REHYDRATED_COUNT) or 0)

    scope = wr2_mgmt_scope_token(project_code, month_key)
    prev = safe_str(st.session_state.get(WR2_SESSION_MGMT_SCOPE))
    if prev != scope:
        wr2_clear_session_decision_caches()
        st.session_state[WR2_SESSION_MGMT_SCOPE] = scope
        st.session_state[WR2_SESSION_MGMT_REHYDRATED_NOTICE] = True

    rows = load_management_decisions(project_code, month_key)
    count = wr2_apply_rehydrate_from_rows(rows)
    if prev != scope:
        st.session_state[WR2_SESSION_MGMT_REHYDRATED_NOTICE] = True
    return count


def wr2_build_mgmt_rpc_payload(
    row: pd.Series,
    *,
    decision: str,
    basis: str,
    responsible: str,
    review_deadline: str,
    comment: str,
    risk_description: str = "",
    risk_impact: str = "",
    risk_mitigation_owner: str = "",
    risk_mitigation_deadline: str = "",
    risk_acceptance_basis: str = "",
    risk_manager_comment: str = "",
    override: bool = False,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "boq_code": safe_str(row.get("boq_code")),
        "boq_name": safe_str(row.get("boq_name")),
        "facility_building": wr2_plan_facility(row.to_dict()),
        "construction_discipline": wr2_plan_discipline(row.to_dict()),
        "admission_outcome_at_decision": safe_str(row.get("outcome")),
        "management_override": bool(override),
        "decision_basis": wr2_normalize_form_value(basis),
        "decision_comment": wr2_normalize_form_value(comment),
        "responsible_person": wr2_normalize_form_value(responsible),
        "review_deadline": wr2_normalize_form_value(review_deadline),
        "risk_blocker": safe_str(row.get("blocking_departments")) or "",
    }
    if decision == WR2_MGMT_INCLUDE_RISK:
        payload["management_override"] = True
        payload.update(
            {
                "risk_description": wr2_normalize_form_value(risk_description),
                "risk_impact": wr2_normalize_form_value(risk_impact),
                "risk_mitigation_owner": wr2_normalize_form_value(risk_mitigation_owner),
                "risk_mitigation_deadline": wr2_normalize_form_value(
                    risk_mitigation_deadline
                ),
                "risk_acceptance_basis": wr2_normalize_form_value(risk_acceptance_basis),
                "risk_manager_comment": wr2_normalize_form_value(risk_manager_comment),
            }
        )
    else:
        # Non-risk decisions must not carry stale risk widget values into RPC.
        payload.update(
            {
                "risk_description": "",
                "risk_impact": "",
                "risk_mitigation_owner": "",
                "risk_mitigation_deadline": "",
                "risk_acceptance_basis": "",
                "risk_manager_comment": "",
            }
        )
    return payload


def wr2_resolve_decided_by(responsible: str) -> str:
    """Prefer form responsible; fallback to passport_created_by if set."""
    actor = safe_str(responsible)
    if actor and actor not in WR2_BLANK_REASON_MARKERS:
        return actor
    created_by = safe_str(st.session_state.get("passport_created_by"))
    if created_by and created_by not in WR2_BLANK_REASON_MARKERS:
        return created_by
    return ""


def wr2_render_saved_decisions_indicator(project_code: str, month_key: str) -> None:
    if not wr2_is_concrete_mgmt_scope(project_code, month_key):
        return
    n = int(st.session_state.get(WR2_SESSION_MGMT_REHYDRATED_COUNT) or 0)
    st.caption(f"Сохранённые управленческие решения: {n}")
    if st.session_state.get(WR2_SESSION_MGMT_REHYDRATED_NOTICE):
        st.caption("Состав восстановлен из Supabase")
        st.session_state[WR2_SESSION_MGMT_REHYDRATED_NOTICE] = False


def wr2_cancel_all_active_scope_decisions(
    project_code: str,
    month_key: str,
    cancelled_by: str,
) -> List[str]:
    """Cancel every ACTIVE decision in concrete scope. Returns error messages."""
    errors: List[str] = []
    actor = safe_str(cancelled_by)
    if not actor:
        return ["Укажите «Кто утверждает» перед очисткой состава."]
    rows = load_management_decisions(project_code, month_key)
    for db_row in rows:
        pid = safe_str(db_row.get("plan_line_id"))
        if not pid:
            continue
        result = cancel_management_decision(
            project_code=project_code,
            month_key=month_key,
            plan_line_id=pid,
            cancelled_by=actor,
            reason="Очистка состава обязательства",
        )
        if not result.get("ok"):
            errors.append(
                f"{safe_str(db_row.get('boq_code')) or pid}: "
                f"{result.get('error') or 'ошибка отмены'}"
            )
    clear_management_decisions_cache()
    return errors


def wr2_sid(plan_line_id: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in plan_line_id)


def wr2_risk_responsible_key(plan_line_id: str) -> str:
    return f"wr2_risk_responsible_{wr2_sid(plan_line_id)}"


def wr2_risk_deadline_key(plan_line_id: str) -> str:
    return f"wr2_risk_deadline_{wr2_sid(plan_line_id)}"


def wr2_risk_comment_key(plan_line_id: str) -> str:
    return f"wr2_risk_comment_{wr2_sid(plan_line_id)}"


def wr2_decision_basis_key(plan_line_id: str) -> str:
    return f"wr2_decision_basis_{wr2_sid(plan_line_id)}"


def wr2_decision_responsible_key(plan_line_id: str) -> str:
    return f"wr2_decision_responsible_{wr2_sid(plan_line_id)}"


def wr2_decision_review_deadline_key(plan_line_id: str) -> str:
    return f"wr2_decision_review_deadline_{wr2_sid(plan_line_id)}"


def wr2_decision_comment_key(plan_line_id: str) -> str:
    return f"wr2_decision_comment_{wr2_sid(plan_line_id)}"


def wr2_commitment_qty_key(plan_line_id: str) -> str:
    return f"wr2_commitment_qty_{wr2_sid(plan_line_id)}"


@st.cache_data(ttl=120, show_spinner=False)
def wr2_load_feasible_qty_map(project_code: str, month_key: str) -> Dict[str, Optional[float]]:
    if not wr2_is_concrete_mgmt_scope(project_code, month_key):
        return {}
    try:
        lines = load_labor_lines(project_code, month_key)
        capacity = load_approved_capacity(
            project_code=project_code,
            month_key=month_key,
        )
        return theoretical_feasible_qty_by_plan_line(lines, capacity)
    except Exception:  # noqa: BLE001
        return {}


def wr2_current_feasible_qty(row: pd.Series) -> Optional[float]:
    pid = safe_str(row.get("plan_line_id"))
    project_code = safe_str(row.get("project_code"))
    month_key = safe_str(row.get("month_key"))
    if not pid:
        return None
    mapping = wr2_load_feasible_qty_map(project_code, month_key)
    return mapping.get(pid)


def wr2_format_qty_with_unit(qty: Any, unit: Any) -> str:
    value = optional_float(qty)
    unit_txt = display_dash(unit)
    if unit_txt == "—":
        unit_txt = ""
    if value is None:
        return "—"
    qty_txt = f"{value:,.3f}".replace(",", " ").rstrip("0").rstrip(".")
    return f"{qty_txt} {unit_txt}".strip()


def wr2_commitment_status_label(record: Optional[Dict[str, Any]]) -> str:
    if not record:
        return "ОБЪЁМ НЕ ПРИНЯТ"
    qty = optional_float(record.get("approved_commitment_qty"))
    if qty is None or qty <= 0:
        return "ОБЪЁМ НЕ ПРИНЯТ"
    return "ОБЪЁМ УТВЕРЖДЁН"


def wr2_risk_impact_key(plan_line_id: str) -> str:
    return f"wr2_risk_impact_{wr2_sid(plan_line_id)}"


def wr2_risk_acceptance_basis_key(plan_line_id: str) -> str:
    return f"wr2_risk_acceptance_basis_{wr2_sid(plan_line_id)}"


def wr2_mgmt_display_label(decision: str) -> str:
    return WR2_MGMT_LABELS.get(decision, decision)


def wr2_get_decision_record(plan_line_id: str) -> Dict[str, Any]:
    comp = st.session_state.get(WR2_SESSION_COMPOSITION, {})
    if plan_line_id in comp:
        return comp[plan_line_id]
    deferred = st.session_state.get(WR2_SESSION_DEFERRED, {})
    if plan_line_id in deferred:
        return deferred[plan_line_id]
    excluded = st.session_state.get(WR2_SESSION_EXCLUDED, {})
    if plan_line_id in excluded:
        return excluded[plan_line_id]
    return {}


def wr2_normalize_form_value(value: Any) -> str:
    """Strip blank UI markers («—») so they never become real field values."""
    text = safe_str(value).strip()
    if text in WR2_BLANK_REASON_MARKERS:
        return ""
    return text


def wr2_previous_decision_type_key(plan_line_id: str) -> str:
    return f"wr2_previous_decision_type_{wr2_sid(plan_line_id)}"


def wr2_hydrate_marker_key(plan_line_id: str) -> str:
    return f"wr2_form_hydrated_{wr2_sid(plan_line_id)}"


def wr2_common_form_keys(plan_line_id: str) -> List[str]:
    return [
        wr2_decision_basis_key(plan_line_id),
        wr2_decision_responsible_key(plan_line_id),
        wr2_decision_review_deadline_key(plan_line_id),
        wr2_decision_comment_key(plan_line_id),
    ]


def wr2_risk_form_keys(plan_line_id: str) -> List[str]:
    return [
        wr2_risk_reason_text_key(plan_line_id),
        wr2_risk_impact_key(plan_line_id),
        wr2_risk_responsible_key(plan_line_id),
        wr2_risk_deadline_key(plan_line_id),
        wr2_risk_acceptance_basis_key(plan_line_id),
        wr2_risk_comment_key(plan_line_id),
    ]


def wr2_clear_widget_keys(keys: List[str]) -> None:
    for key in keys:
        st.session_state[key] = ""


def wr2_set_widget_defaults(
    defaults: Dict[str, str],
    *,
    force: bool = False,
) -> None:
    for key, value in defaults.items():
        clean = wr2_normalize_form_value(value)
        if not clean:
            if force:
                st.session_state[key] = ""
            continue
        if force or key not in st.session_state:
            st.session_state[key] = clean


def wr2_hydrate_decision_widgets(
    plan_line_id: str,
    *,
    live_decision: str = "",
    force: bool = False,
) -> None:
    """
    Seed form widgets from durable/session record.

    - Common fields hydrate from any durable decision.
    - Risk fields hydrate ONLY when durable decision is INCLUDE_RISK
      and live decision is also INCLUDE_RISK.
    - No risk_description←basis / risk_comment←comment fallback.
    - «—» is never written as a real value.
    - One-shot per (sid, live_decision) unless force=True.
    """
    marker = wr2_hydrate_marker_key(plan_line_id)
    live = live_decision or safe_str(st.session_state.get(wr2_live_decision_key(plan_line_id)))
    if not force and safe_str(st.session_state.get(marker)) == live and live:
        return

    record = wr2_get_decision_record(plan_line_id)
    record_decision = safe_str(record.get("decision")) if record else ""

    if record:
        common = {
            wr2_decision_basis_key(plan_line_id): safe_str(record.get("basis")),
            wr2_decision_responsible_key(plan_line_id): safe_str(record.get("responsible")),
            wr2_decision_review_deadline_key(plan_line_id): safe_str(
                record.get("review_deadline") or record.get("risk_deadline")
            ),
            wr2_decision_comment_key(plan_line_id): safe_str(record.get("comment")),
        }
        wr2_set_widget_defaults(common, force=force)
        saved_commitment = optional_float(record.get("approved_commitment_qty"))
        qty_key = wr2_commitment_qty_key(plan_line_id)
        if saved_commitment is not None and saved_commitment > 0:
            if force or qty_key not in st.session_state:
                st.session_state[qty_key] = float(saved_commitment)

        if (
            record_decision == WR2_MGMT_INCLUDE_RISK
            and live == WR2_MGMT_INCLUDE_RISK
        ):
            risk = {
                wr2_risk_reason_text_key(plan_line_id): safe_str(
                    record.get("risk_description")
                ),
                wr2_risk_impact_key(plan_line_id): safe_str(record.get("risk_impact")),
                wr2_risk_responsible_key(plan_line_id): safe_str(
                    record.get("risk_mitigation_owner")
                ),
                wr2_risk_deadline_key(plan_line_id): safe_str(
                    record.get("risk_mitigation_deadline") or record.get("risk_deadline")
                ),
                wr2_risk_acceptance_basis_key(plan_line_id): safe_str(
                    record.get("risk_acceptance_basis")
                ),
                wr2_risk_comment_key(plan_line_id): safe_str(
                    record.get("risk_manager_comment")
                ),
            }
            wr2_set_widget_defaults(risk, force=force)

    if live:
        st.session_state[marker] = live


def wr2_on_decision_type_changed(
    plan_line_id: str,
    previous: str,
    current: str,
) -> None:
    """Controlled reset when radio decision type changes for one plan_line_id."""
    record = wr2_get_decision_record(plan_line_id)
    record_decision = safe_str(record.get("decision")) if record else ""

    if current == WR2_MGMT_INCLUDE_RISK:
        # Never inherit DEFER/EXCLUDE text into risk protocol.
        wr2_clear_widget_keys(wr2_risk_form_keys(plan_line_id))
        if record_decision == WR2_MGMT_INCLUDE_RISK:
            wr2_hydrate_decision_widgets(
                plan_line_id,
                live_decision=current,
                force=True,
            )
        else:
            st.session_state[wr2_hydrate_marker_key(plan_line_id)] = current
        return

    # Leaving INCLUDE_RISK (or switching non-risk types): drop stale risk widgets
    # so they cannot leak into a later INCLUDE_RISK payload by accident.
    if previous == WR2_MGMT_INCLUDE_RISK or current != WR2_MGMT_INCLUDE_RISK:
        wr2_clear_widget_keys(wr2_risk_form_keys(plan_line_id))

    if record_decision == current and current in WR2_MGMT_OPTIONS:
        wr2_hydrate_decision_widgets(
            plan_line_id,
            live_decision=current,
            force=True,
        )
    else:
        st.session_state[wr2_hydrate_marker_key(plan_line_id)] = current


def wr2_sync_decision_type_change(plan_line_id: str, current_decision: str) -> bool:
    """
    Detect real radio change for plan_line_id.
    Returns True when type changed this run.
    """
    prev_key = wr2_previous_decision_type_key(plan_line_id)
    previous = safe_str(st.session_state.get(prev_key))
    current = safe_str(current_decision)
    if not previous:
        st.session_state[prev_key] = current
        wr2_hydrate_decision_widgets(plan_line_id, live_decision=current)
        return False
    if previous == current:
        wr2_hydrate_decision_widgets(plan_line_id, live_decision=current)
        return False
    wr2_on_decision_type_changed(plan_line_id, previous, current)
    st.session_state[prev_key] = current
    return True


def wr2_field_from_record_or_widget(
    plan_line_id: str,
    widget_key: str,
    *record_fields: str,
) -> str:
    """
    Apply priority: live widget value first; durable/session record only if
    widget key is absent from session_state.
    """
    if widget_key in st.session_state:
        return wr2_normalize_form_value(st.session_state.get(widget_key))
    record = wr2_get_decision_record(plan_line_id)
    if record:
        for field in record_fields:
            value = wr2_normalize_form_value(record.get(field))
            if value:
                return value
    return ""


def wr2_get_decision_basis(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_decision_basis_key(plan_line_id),
        "basis",
    )


def wr2_get_decision_responsible(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_decision_responsible_key(plan_line_id),
        "responsible",
    )


def wr2_get_decision_review_deadline(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_decision_review_deadline_key(plan_line_id),
        "review_deadline",
        "risk_deadline",
    )


def wr2_get_decision_comment(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_decision_comment_key(plan_line_id),
        "comment",
    )


def wr2_get_risk_impact(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_risk_impact_key(plan_line_id),
        "risk_impact",
    )


def wr2_get_risk_acceptance_basis(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_risk_acceptance_basis_key(plan_line_id),
        "risk_acceptance_basis",
    )


def wr2_get_risk_responsible(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_risk_responsible_key(plan_line_id),
        "risk_mitigation_owner",
    )


def wr2_get_risk_deadline(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_risk_deadline_key(plan_line_id),
        "risk_mitigation_deadline",
    )


def wr2_get_risk_comment(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_risk_comment_key(plan_line_id),
        "risk_manager_comment",
    )


def wr2_risk_fields_complete(plan_line_id: str) -> bool:
    return bool(
        wr2_get_risk_reason_text(plan_line_id)
        and wr2_get_risk_responsible(plan_line_id)
        and wr2_get_risk_deadline(plan_line_id)
        and wr2_get_risk_comment(plan_line_id)
    )


def wr2_append_audit(entry: Dict[str, Any]) -> None:
    log = st.session_state.setdefault(WR2_SESSION_AUDIT, [])
    log.append(entry)


def wr2_sync_auto_admitted_composition(board_df: pd.DataFrame) -> None:
    comp = dict(st.session_state.get(WR2_SESSION_COMPOSITION, {}))
    deferred = dict(st.session_state.get(WR2_SESSION_DEFERRED, {}))
    excluded = dict(st.session_state.get(WR2_SESSION_EXCLUDED, {}))
    now_iso = datetime.now(timezone.utc).isoformat()
    changed = False
    for _, row in board_df.iterrows():
        if safe_str(row.get("outcome")) != WR2_OUTCOME_OK:
            continue
        pid = safe_str(row.get("plan_line_id"))
        if not pid or pid in comp or pid in deferred or pid in excluded:
            continue
        comp[pid] = {
            "boq_code": safe_str(row.get("boq_code")),
            "boq_name": safe_str(row.get("boq_name")),
            "decision": WR2_MGMT_INCLUDE,
            "outcome": safe_str(row.get("outcome")),
            "override": False,
            "basis": WR2_AUTO_INCLUDE_BASIS,
            "responsible": "",
            "review_deadline": "",
            "risk_deadline": "",
            "comment": "",
            "risk_blocker": safe_str(row.get("blocking_departments")) or "—",
            "plan_value": safe_num(row.get("plan_value_num")),
            "labor_hours": safe_num(row.get("labor_hours")),
            "added_at": now_iso,
        }
        changed = True
    if changed:
        st.session_state[WR2_SESSION_COMPOSITION] = comp


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


def wr2_live_decision_key(plan_line_id: str) -> str:
    return f"wr2_decision_radio_{wr2_sid(plan_line_id)}"


def wr2_get_live_decision(row: pd.Series) -> str:
    pid = safe_str(row.get("plan_line_id"))
    radio_key = wr2_live_decision_key(pid)
    stored = safe_str(st.session_state.get(radio_key))
    if stored in WR2_MGMT_OPTIONS:
        return stored
    return wr2_get_mgmt_decision(row)


def wr2_render_outcome_status(outcome: str) -> None:
    color = WR2_OUTCOME_TEXT_COLOR.get(outcome, "#374151")
    st.markdown(
        f'<p style="margin:0 0 0.25rem 0;font-size:0.78rem;color:rgba(49,51,63,0.6);">'
        f"Итог допуска</p>"
        f'<p style="margin:0;font-size:1.05rem;font-weight:600;color:{color};">'
        f"{outcome}</p>",
        unsafe_allow_html=True,
    )


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
    pid = safe_str(row.get("plan_line_id"))
    deferred = st.session_state.get(WR2_SESSION_DEFERRED, {})
    if pid and pid in deferred:
        return WR2_MGMT_POSTPONE
    excluded = st.session_state.get(WR2_SESSION_EXCLUDED, {})
    if pid and pid in excluded:
        return WR2_MGMT_EXCLUDE
    comp = st.session_state.get(WR2_SESSION_COMPOSITION, {})
    if pid and pid in comp:
        return safe_str(comp[pid].get("decision")) or WR2_MGMT_EXCLUDE
    outcome = safe_str(row.get("outcome"))
    if outcome == WR2_OUTCOME_OK:
        return WR2_MGMT_INCLUDE
    mgmt_key = wr2_mgmt_session_key(pid)
    stored = safe_str(st.session_state.get(mgmt_key))
    if stored in WR2_MGMT_OPTIONS:
        return stored
    return wr2_default_mgmt_decision(outcome)


def wr2_needs_management_review(row: pd.Series) -> bool:
    outcome = safe_str(row.get("outcome"))
    decision = wr2_get_mgmt_decision(row)
    if decision in (WR2_MGMT_POSTPONE, WR2_MGMT_EXCLUDE):
        return True
    if outcome == WR2_OUTCOME_OK:
        return False
    return outcome in (
        WR2_OUTCOME_RISK,
        WR2_OUTCOME_BLOCKED,
        WR2_OUTCOME_WAITING,
        WR2_OUTCOME_NO_CHECKS,
    )


def wr2_review_priority(row: pd.Series) -> str:
    outcome = safe_str(row.get("outcome"))
    if outcome == WR2_OUTCOME_BLOCKED or bool(row.get("has_overdue")):
        return WR2_PRIORITY_P1
    if outcome == WR2_OUTCOME_RISK:
        return WR2_PRIORITY_P2
    return WR2_PRIORITY_P3


def wr2_primary_constraint(row: pd.Series) -> str:
    reason = safe_str(row.get("reason"))
    if reason and reason != "—":
        return reason
    blocking = safe_str(row.get("blocking_departments"))
    if blocking and blocking != "—":
        return blocking
    return safe_str(row.get("outcome_status_reason")) or "—"


def wr2_registry_dept_short_label(db_value: Any) -> str:
    db = safe_str(db_value)
    for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
        if dept_db == db:
            return col_label
    mapped = dept_ui(db)
    return mapped if mapped else "—"


def wr2_constraint_decision_timestamp(row: pd.Series) -> Optional[pd.Timestamp]:
    for col in ("last_action_at", "updated_at", "constraint_created_at", "created_at"):
        if col not in row.index:
            continue
        raw = row.get(col)
        if raw is None or pd.isna(raw):
            continue
        try:
            parsed = pd.to_datetime(raw, utc=True)
            if pd.isna(parsed):
                continue
            return parsed
        except Exception:  # noqa: BLE001
            continue
    return None


def wr2_format_registry_decision_datetime(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        parsed = pd.to_datetime(value, utc=True)
        if pd.isna(parsed):
            return ""
        if parsed.tzinfo is not None:
            parsed = parsed.tz_convert("Europe/Moscow")
        return parsed.strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return ""


def wr2_latest_hold_constraint(group: pd.DataFrame) -> Optional[pd.Series]:
    if group.empty or "check_status" not in group.columns:
        return None
    holds = group[group["check_status"].apply(norm_check_status_key) == "HOLD"]
    if holds.empty:
        return None
    ranked = holds.copy()
    ranked["_hold_sort_ts"] = ranked.apply(wr2_constraint_decision_timestamp, axis=1)
    ranked = ranked.sort_values("_hold_sort_ts", ascending=False, na_position="last")
    return ranked.iloc[0]


def wr2_format_constraint_reason_text(row: pd.Series) -> str:
    substance = constraint_block_substance(row)
    if substance and not is_generic_block_reason(substance):
        return substance
    specific = registry_specific_block_reason(row)
    if specific:
        return specific
    return ""


def wr2_format_last_constraint_display(constraint_row: Optional[pd.Series]) -> str:
    if constraint_row is None:
        return "—"
    dept = wr2_registry_dept_short_label(constraint_row.get("responsible_department"))
    actor = (
        safe_str(constraint_row.get("updated_by"))
        or safe_str(constraint_row.get("owner_name"))
        or "—"
    )
    decided_at = ""
    for col in ("last_action_at", "updated_at"):
        decided_at = wr2_format_registry_decision_datetime(constraint_row.get(col))
        if decided_at:
            break
    reason = wr2_format_constraint_reason_text(constraint_row)
    header_parts = [dept, actor]
    if decided_at:
        header_parts.append(decided_at)
    header = " | ".join(header_parts)
    if reason:
        return f"{header}\n{reason}"
    if dept != "—" or actor != "—" or decided_at:
        return header
    return "—"


def wr2_format_constraint_age_days(constraint_row: Optional[pd.Series]) -> str:
    if constraint_row is None:
        return "—"
    hold_ts = wr2_constraint_decision_timestamp(constraint_row)
    if hold_ts is None or pd.isna(hold_ts):
        hold_date = None
        for col in ("last_action_at", "updated_at", "constraint_created_at", "created_at"):
            hold_date = safe_date(constraint_row.get(col))
            if hold_date:
                break
    else:
        hold_date = hold_ts.tz_convert("Europe/Moscow").date() if hold_ts.tzinfo else hold_ts.date()
    if hold_date is None:
        return "—"
    days = max((date.today() - hold_date).days, 0)
    return f"{days} дн."


def wr2_build_unified_registry_df(
    board_df: pd.DataFrame,
    constraints_df: pd.DataFrame,
) -> pd.DataFrame:
    """Полный реестр кодов месяца для War Room (1 строка = 1 plan_line_id)."""
    if board_df.empty:
        return pd.DataFrame()

    constraints_by_line = build_constraints_by_line_id(constraints_df)
    display_rows: List[Dict[str, Any]] = []
    for _, row in board_df.iterrows():
        pid = safe_str(row.get("plan_line_id"))
        last_hold = wr2_latest_hold_constraint(constraints_by_line.get(pid, pd.DataFrame()))
        boq = display_dash(row.get("boq_code"))
        outcome_display = safe_str(row.get("classic_outcome") or row.get("outcome"))
        needs_review = wr2_needs_management_review(row)
        priority = wr2_review_priority(row)
        labor_hours = safe_num(row.get("labor_hours"))
        labor_cost = safe_num(row.get("labor_cost"))
        crew_size_raw = safe_num(row.get("crew_size"))
        plan_value_num = safe_num(row.get("plan_value_num"))
        final_decision = wr2_final_decision_label_for_row(row)
        passport_index = wr2_passport_status_index_from_session()
        passport_status = wr2_passport_status_for_row(row, passport_index)
        passport_conflict = wr2_passport_decision_conflict(
            final_decision,
            passport_status,
            has_active_passport=bool(passport_index.get("has_passport")),
        )
        row_dict: Dict[str, Any] = {
            "_plan_line_id": pid,
            "_needs_review_sort": 0 if needs_review else 1,
            "_priority_sort": WR2_PRIORITY_ORDER.get(priority, 9),
            "_plan_value_num": plan_value_num,
            "_passport_decision_conflict": passport_conflict,
            "Итог допуска": outcome_display,
            "Итоговое решение": final_decision,
            WR2_PASSPORT_STATUS_COLUMN: wr2_format_passport_status_display(
                passport_status, conflict=passport_conflict
            ),
            "Почему не допущен": truncate_blocking_reason_display(
                safe_str(row.get("blocking_reason_summary"))
            ),
            "Проект": display_dash(row.get("project_code")),
            "Очередь": display_dash(row.get("queue_display")),
            "Титул": display_dash(row.get("title_display")),
            "Дисциплина": display_dash(row.get("discipline")),
            "Система": display_dash(row.get("system_display")),
            "Пакет": display_dash(row.get("package_display")),
            "BOQ-код": boq,
            "Наименование работы": display_dash(row.get("boq_name")),
            "Плановый объём": (
                f"{safe_num(row.get('planned_qty')):,.3f}".replace(",", " ")
                if safe_num(row.get("planned_qty"))
                else "—"
            ),
            "Плановая стоимость": money_ru(plan_value_num),
            "Звено": display_dash(row.get("crew")),
            "Людей в звене": wr2_format_crew_size_display(crew_size_raw),
            "Трудозатраты, чел·ч": wr2_format_hours(labor_hours),
            "Длительность, смен": wr2_format_duration_shifts_display(
                labor_hours, crew_size_raw
            ),
            "Норма выработки": wr2_format_norm(safe_num(row.get("norm_hours_per_unit"))),
            "Стоимость труда / стоимость звена": money_ru(labor_cost),
            "Труд / стоимость работ, %": wr2_format_labor_to_plan_pct_display(
                labor_cost, plan_value_num
            ),
            "Причина итогового допуска": wr2_registry_admission_reason_display(row),
            "Последнее ограничение": wr2_format_last_constraint_display(last_hold),
            "Возраст ограничения": wr2_format_constraint_age_days(last_hold),
        }
        for display_label, classic_label in WR2_BOARD_DEPT_DISPLAY:
            row_dict[display_label] = safe_str(row.get(f"classic_{classic_label}"))
        display_rows.append(row_dict)

    result = pd.DataFrame(display_rows)
    return result.sort_values(
        ["_needs_review_sort", "_priority_sort", "_plan_value_num"],
        ascending=[True, True, False],
        kind="stable",
    ).reset_index(drop=True)


def wr2_resolve_unified_registry_selection(registry_df: pd.DataFrame) -> Optional[str]:
    if registry_df.empty:
        return None

    line_ids = registry_df["_plan_line_id"].astype(str).tolist()
    selected_pid: Optional[str] = None

    sel_state = st.session_state.get(WR2_REGISTRY_SELECT_KEY)
    if isinstance(sel_state, dict):
        rows_sel = sel_state.get("selection", {}).get("rows", [])
        if rows_sel:
            idx = int(rows_sel[0])
            if 0 <= idx < len(line_ids):
                selected_pid = line_ids[idx]

    if not selected_pid:
        stored = safe_str(st.session_state.get(WR2_SESSION_SELECTED))
        if stored in line_ids:
            selected_pid = stored

    if not selected_pid:
        needs_review = registry_df[registry_df["_needs_review_sort"] == 0]
        if not needs_review.empty:
            selected_pid = safe_str(needs_review.iloc[0].get("_plan_line_id"))
        else:
            selected_pid = line_ids[0]

    if selected_pid:
        st.session_state[WR2_SESSION_SELECTED] = selected_pid
    return selected_pid


def wr2_build_decision_record(
    row: pd.Series,
    decision: str,
    *,
    basis: str,
    responsible: str,
    review_deadline: str,
    comment: str,
    risk_description: str = "",
    risk_impact: str = "",
    risk_mitigation_owner: str = "",
    risk_mitigation_deadline: str = "",
    risk_acceptance_basis: str = "",
    risk_manager_comment: str = "",
) -> Dict[str, Any]:
    outcome = safe_str(row.get("outcome"))
    override = decision == WR2_MGMT_INCLUDE_RISK and outcome != WR2_OUTCOME_OK
    return {
        "boq_code": safe_str(row.get("boq_code")),
        "boq_name": safe_str(row.get("boq_name")),
        "decision": decision,
        "outcome": outcome,
        "override": override,
        "basis": basis,
        "responsible": responsible,
        "review_deadline": review_deadline,
        "comment": comment,
        "risk_description": risk_description,
        "risk_impact": risk_impact,
        "risk_mitigation_owner": risk_mitigation_owner,
        "risk_mitigation_deadline": risk_mitigation_deadline,
        "risk_acceptance_basis": risk_acceptance_basis,
        "risk_manager_comment": risk_manager_comment,
        "risk_deadline": risk_mitigation_deadline,
        "risk_blocker": safe_str(row.get("blocking_departments")) or "—",
        "plan_value": safe_num(row.get("plan_value_num")),
        "labor_hours": safe_num(row.get("labor_hours")),
        "requested_qty_snapshot": optional_float(row.get("requested_qty_snapshot")),
        "feasible_qty_snapshot": optional_float(row.get("feasible_qty_snapshot")),
        "approved_commitment_qty": optional_float(row.get("approved_commitment_qty")),
        "committed_work_value": optional_float(row.get("committed_work_value")),
        "committed_required_hours": optional_float(row.get("committed_required_hours")),
        "committed_labor_cost": optional_float(row.get("committed_labor_cost")),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }


def wr2_apply_management_decision(
    row: pd.Series,
    decision: str,
    *,
    basis: str = "",
    responsible: str = "",
    review_deadline: str = "",
    comment: str = "",
    risk_description: str = "",
    risk_impact: str = "",
    risk_mitigation_owner: str = "",
    risk_mitigation_deadline: str = "",
    risk_acceptance_basis: str = "",
    risk_manager_comment: str = "",
    commitment_qty: Any = None,
) -> List[str]:
    errors: List[str] = []
    pid = safe_str(row.get("plan_line_id"))
    if not pid:
        return ["Не выбран plan_line_id."]
    project_code = safe_str(row.get("project_code"))
    month_key = safe_str(row.get("month_key"))
    if not wr2_is_concrete_mgmt_scope(project_code, month_key):
        return [
            "Для сохранения решения выберите конкретный проект и месяц в фильтрах."
        ]
    outcome = safe_str(row.get("outcome"))

    basis = wr2_normalize_form_value(basis)
    responsible = wr2_normalize_form_value(responsible)
    review_deadline = wr2_normalize_form_value(review_deadline)
    comment = wr2_normalize_form_value(comment)
    risk_description = wr2_normalize_form_value(risk_description)
    risk_impact = wr2_normalize_form_value(risk_impact)
    risk_mitigation_owner = wr2_normalize_form_value(risk_mitigation_owner)
    risk_mitigation_deadline = wr2_normalize_form_value(risk_mitigation_deadline)
    risk_acceptance_basis = wr2_normalize_form_value(risk_acceptance_basis)
    risk_manager_comment = wr2_normalize_form_value(risk_manager_comment)

    if decision != WR2_MGMT_INCLUDE_RISK:
        risk_description = ""
        risk_impact = ""
        risk_mitigation_owner = ""
        risk_mitigation_deadline = ""
        risk_acceptance_basis = ""
        risk_manager_comment = ""

    if not basis:
        errors.append("Укажите основание решения.")
    if not responsible:
        errors.append("Укажите ответственного.")

    if decision == WR2_MGMT_INCLUDE_RISK:
        if not risk_description:
            errors.append("Укажите описание риска.")
        if not risk_impact:
            errors.append("Укажите возможные последствия.")
        if not risk_mitigation_owner:
            errors.append("Укажите ответственного за устранение.")
        if not risk_mitigation_deadline:
            errors.append("Укажите срок устранения.")
        if not risk_acceptance_basis:
            errors.append("Укажите основание принятия риска.")
        if not risk_manager_comment:
            errors.append("Укажите комментарий руководителя.")

    decided_by = wr2_resolve_decided_by(responsible)
    if not decided_by:
        errors.append(
            "Не указан автор решения. Заполните «Ответственный» "
            "или поле «Кто утверждает»."
        )

    decision_code = normalize_decision_code(decision)
    if not decision_code:
        errors.append(f"Некорректное решение: {decision}")

    snapshots: Optional[Dict[str, Optional[float]]] = None
    if decision in WR2_PASSPORT_DECISIONS:
        raw_commitment = commitment_qty
        if raw_commitment is None:
            raw_commitment = st.session_state.get(wr2_commitment_qty_key(pid))
        parsed_commitment = optional_float(raw_commitment)
        if parsed_commitment is not None and parsed_commitment > 0:
            feasible_now = wr2_current_feasible_qty(row)
            qty_error = validate_approved_commitment_qty(raw_commitment, feasible_now)
            if qty_error:
                errors.append(qty_error)
            else:
                snapshots = build_commitment_snapshots(
                    requested_qty=row.get("planned_qty"),
                    feasible_qty=feasible_now,
                    approved_commitment_qty=raw_commitment,
                    unit_price=row.get("unit_price"),
                    plan_value=row.get("plan_value_num") or row.get("plan_value"),
                    labor_hours=row.get("labor_hours"),
                    labor_rate_per_hour=row.get("labor_rate_per_hour"),
                )

    if errors:
        return errors

    old_decision = wr2_get_mgmt_decision(row)
    now_iso = datetime.now(timezone.utc).isoformat()
    record = wr2_build_decision_record(
        row,
        decision,
        basis=basis,
        responsible=responsible,
        review_deadline=review_deadline,
        comment=comment,
        risk_description=risk_description,
        risk_impact=risk_impact,
        risk_mitigation_owner=risk_mitigation_owner,
        risk_mitigation_deadline=risk_mitigation_deadline,
        risk_acceptance_basis=risk_acceptance_basis,
        risk_manager_comment=risk_manager_comment,
    )
    if snapshots:
        record.update(snapshots)
    else:
        previous = wr2_get_decision_record(pid)
        if previous:
            for key in (
                "requested_qty_snapshot",
                "feasible_qty_snapshot",
                "approved_commitment_qty",
                "committed_work_value",
                "committed_required_hours",
                "committed_labor_cost",
            ):
                if previous.get(key) is not None:
                    record[key] = previous.get(key)
    override = bool(record.get("override"))
    payload = wr2_build_mgmt_rpc_payload(
        row,
        decision=decision,
        basis=basis,
        responsible=responsible,
        review_deadline=review_deadline,
        comment=comment,
        risk_description=risk_description,
        risk_impact=risk_impact,
        risk_mitigation_owner=risk_mitigation_owner,
        risk_mitigation_deadline=risk_mitigation_deadline,
        risk_acceptance_basis=risk_acceptance_basis,
        risk_manager_comment=risk_manager_comment,
        override=override,
    )
    payload = merge_commitment_payload(payload, snapshots)

    # DB first — session updates only after successful RPC
    rpc_result = apply_management_decision(
        project_code=project_code,
        month_key=month_key,
        plan_line_id=pid,
        decision=decision_code,
        decided_by=decided_by,
        payload=payload,
    )
    if not rpc_result.get("ok"):
        return [
            f"Не удалось сохранить решение в Supabase: "
            f"{rpc_result.get('error') or 'неизвестная ошибка'}"
        ]

    comp = dict(st.session_state.get(WR2_SESSION_COMPOSITION, {}))
    deferred = dict(st.session_state.get(WR2_SESSION_DEFERRED, {}))
    excluded = dict(st.session_state.get(WR2_SESSION_EXCLUDED, {}))

    if decision in WR2_PASSPORT_DECISIONS:
        deferred.pop(pid, None)
        excluded.pop(pid, None)
        comp[pid] = record
    elif decision == WR2_MGMT_POSTPONE:
        comp.pop(pid, None)
        excluded.pop(pid, None)
        deferred[pid] = record
    elif decision == WR2_MGMT_EXCLUDE:
        comp.pop(pid, None)
        deferred.pop(pid, None)
        excluded[pid] = record
    elif pid in comp:
        del comp[pid]

    st.session_state[WR2_SESSION_COMPOSITION] = comp
    st.session_state[WR2_SESSION_DEFERRED] = deferred
    st.session_state[WR2_SESSION_EXCLUDED] = excluded
    st.session_state[wr2_mgmt_session_key(pid)] = decision
    st.session_state[WR2_SESSION_MGMT_SCOPE] = wr2_mgmt_scope_token(
        project_code, month_key
    )
    # Refresh count from cache-cleared load after apply
    st.session_state[WR2_SESSION_MGMT_REHYDRATED_COUNT] = len(
        load_management_decisions(project_code, month_key)
    )

    wr2_append_audit(
        {
            "datetime": now_iso,
            "boq_code": safe_str(row.get("boq_code")),
            "plan_line_id": pid,
            "old_outcome": outcome,
            "old_decision": old_decision,
            "decision": decision,
            "override": override,
            "basis": basis.strip(),
            "responsible": responsible.strip(),
            "comment": comment.strip(),
            "persisted": True,
        }
    )
    return []


def wr2_remove_from_passport(pid: str, boq_code: str, outcome: str) -> List[str]:
    """Remove line from draft via cancel RPC, then update session."""
    scope = safe_str(st.session_state.get(WR2_SESSION_MGMT_SCOPE))
    parts = scope.split("|", 1) if scope else []
    project_code = parts[0] if len(parts) == 2 else ""
    month_key = parts[1] if len(parts) == 2 else ""
    if not wr2_is_concrete_mgmt_scope(project_code, month_key):
        return [
            "Нельзя убрать код: выберите конкретный проект и месяц."
        ]
    actor = wr2_resolve_decided_by(
        safe_str(st.session_state.get("passport_created_by"))
    )
    if not actor:
        return [
            "Укажите «Кто утверждает» перед удалением кода из состава."
        ]

    formed = bool(st.session_state.get(WR2_SESSION_FORMED))
    note = (
        "Код исключён из паспорта управленческим решением"
        if formed
        else "Код убран из черновика состава паспорта"
    )
    rpc_result = cancel_management_decision(
        project_code=project_code,
        month_key=month_key,
        plan_line_id=pid,
        cancelled_by=actor,
        reason=note,
    )
    if not rpc_result.get("ok"):
        return [
            f"Не удалось отменить решение в Supabase: "
            f"{rpc_result.get('error') or 'неизвестная ошибка'}"
        ]

    comp = dict(st.session_state.get(WR2_SESSION_COMPOSITION, {}))
    deferred = dict(st.session_state.get(WR2_SESSION_DEFERRED, {}))
    excluded = dict(st.session_state.get(WR2_SESSION_EXCLUDED, {}))
    comp.pop(pid, None)
    deferred.pop(pid, None)
    excluded.pop(pid, None)
    st.session_state[WR2_SESSION_COMPOSITION] = comp
    st.session_state[WR2_SESSION_DEFERRED] = deferred
    st.session_state[WR2_SESSION_EXCLUDED] = excluded
    st.session_state.pop(wr2_mgmt_session_key(pid), None)
    st.session_state[WR2_SESSION_MGMT_REHYDRATED_COUNT] = len(
        load_management_decisions(project_code, month_key)
    )
    wr2_append_audit(
        {
            "datetime": datetime.now(timezone.utc).isoformat(),
            "boq_code": boq_code,
            "plan_line_id": pid,
            "old_outcome": outcome,
            "decision": "CANCEL",
            "override": False,
            "basis": note,
            "responsible": actor,
            "comment": note,
            "persisted": True,
        }
    )
    return []


def wr2_get_risk_reason_text(plan_line_id: str) -> str:
    return wr2_field_from_record_or_widget(
        plan_line_id,
        wr2_risk_reason_text_key(plan_line_id),
        "risk_description",
    )


def wr2_effective_passport_label(row: pd.Series) -> str:
    decision = wr2_get_mgmt_decision(row)
    if decision == WR2_MGMT_INCLUDE:
        return "Включить"
    if decision == WR2_MGMT_INCLUDE_RISK:
        return "С риском"
    if decision == WR2_MGMT_POSTPONE:
        return "Отложено"
    return "Исключить"


def wr2_row_in_passport_inclusion(
    row: pd.Series,
    *,
    allow_risk: bool = True,
) -> bool:
    decision = wr2_get_mgmt_decision(row)
    pid = safe_str(row.get("plan_line_id"))
    if decision == WR2_MGMT_INCLUDE:
        return True
    if decision == WR2_MGMT_INCLUDE_RISK and allow_risk:
        return wr2_risk_fields_complete(pid)
    return False


def wr2_validate_management_decisions(
    board_df: pd.DataFrame,
    *,
    allow_risk: bool = True,
) -> List[str]:
    errors: List[str] = []
    if board_df.empty:
        return errors
    for _, row in board_df.iterrows():
        if not wr2_row_in_passport_inclusion(row, allow_risk=allow_risk):
            continue
        boq = display_dash(row.get("boq_code"))
        pid = safe_str(row.get("plan_line_id"))
        decision = wr2_get_mgmt_decision(row)
        if decision == WR2_MGMT_INCLUDE_RISK and allow_risk:
            if not wr2_get_risk_reason_text(pid):
                errors.append(f"{boq}: укажите основание управленческого решения.")
            if not wr2_get_risk_responsible(pid):
                errors.append(f"{boq}: укажите ответственного за риск.")
            if not wr2_get_risk_deadline(pid):
                errors.append(f"{boq}: укажите срок снятия риска.")
            if not wr2_get_risk_comment(pid):
                errors.append(f"{boq}: укажите комментарий.")
    return errors


def wr2_is_blank_reason(value: Any) -> bool:
    text = safe_str(value).strip()
    return text in WR2_BLANK_REASON_MARKERS


def wr2_line_is_fully_admitted(row: pd.Series) -> bool:
    return safe_str(row.get("outcome")) == WR2_OUTCOME_OK


def wr2_writer_needs_override_for_row(row: pd.Series) -> bool:
    """True when create_monthly_passport would skip the line without management override."""
    outcome = safe_str(row.get("outcome"))
    if wr2_line_is_fully_admitted(row):
        return False
    # RISK → READY_WITH_RISK enters passport without override.
    if outcome == WR2_OUTCOME_RISK:
        return False
    return True


def wr2_composition_record(plan_line_id: str) -> Dict[str, Any]:
    comp = st.session_state.get(WR2_SESSION_COMPOSITION, {})
    record = comp.get(plan_line_id) if plan_line_id else None
    return dict(record) if isinstance(record, dict) else {}


def wr2_manual_include_override_reason(plan_line_id: str) -> Tuple[str, str, str]:
    """Return (reason, comment, basis_text) from existing War Room decision fields."""
    record = wr2_composition_record(plan_line_id)
    reason = wr2_get_decision_basis(plan_line_id) or safe_str(record.get("basis"))
    comment = wr2_get_decision_comment(plan_line_id) or safe_str(record.get("comment"))
    responsible = wr2_get_decision_responsible(plan_line_id) or safe_str(
        record.get("responsible")
    )
    deadline = wr2_get_decision_review_deadline(plan_line_id) or safe_str(
        record.get("review_deadline") or record.get("risk_deadline")
    )
    basis_parts = [part for part in (reason, comment) if not wr2_is_blank_reason(part)]
    if responsible and not wr2_is_blank_reason(responsible):
        basis_parts.append(f"Ответственный: {responsible}")
    if deadline and not wr2_is_blank_reason(deadline):
        basis_parts.append(f"Срок: {deadline}")
    basis_text = " | ".join(basis_parts) if basis_parts else reason
    return reason, comment, basis_text


def wr2_collect_passport_override_errors(
    board_df: pd.DataFrame,
    *,
    allow_risk: bool = True,
) -> List[str]:
    """Validate that forced draft inclusions have a decision basis before passport write."""
    errors: List[str] = []
    for _, row in board_df.iterrows():
        if not wr2_row_in_passport_inclusion(row, allow_risk=allow_risk):
            continue
        pid = safe_str(row.get("plan_line_id"))
        if not pid:
            continue
        if not wr2_writer_needs_override_for_row(row):
            continue
        decision = wr2_get_mgmt_decision(row)
        boq = display_dash(row.get("boq_code"))
        outcome = safe_str(row.get("outcome"))
        if decision == WR2_MGMT_INCLUDE_RISK:
            if not wr2_risk_fields_complete(pid):
                errors.append(
                    f"{boq}: для включения с риском заполните основание, "
                    "ответственного, срок и комментарий."
                )
            continue
        if decision != WR2_MGMT_INCLUDE:
            continue
        reason, _comment, _basis = wr2_manual_include_override_reason(pid)
        if wr2_is_blank_reason(reason):
            if outcome == WR2_OUTCOME_BLOCKED:
                errors.append(
                    "Для принудительного включения заблокированной строки "
                    f"укажите основание решения ({boq})."
                )
            else:
                errors.append(
                    f"{boq}: для принудительного включения укажите основание "
                    "управленческого решения."
                )
    return errors


def wr2_build_passport_override_payload(
    board_df: pd.DataFrame,
    created_by: str,
    *,
    allow_risk: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """
    Build management_override patches keyed by plan_line_id.

    - Fully admitted INCLUDE → no override.
    - INCLUDE_RISK → existing risk metadata.
    - Manual INCLUDE of incomplete admission → override from composition/session fields.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    overrides: Dict[str, Dict[str, Any]] = {}
    for _, row in board_df.iterrows():
        if not wr2_row_in_passport_inclusion(row, allow_risk=allow_risk):
            continue
        pid = safe_str(row.get("plan_line_id"))
        if not pid:
            continue
        # Only draft composition rows (board_df is already the passport scope/draft).
        if pid not in st.session_state.get(WR2_SESSION_COMPOSITION, {}):
            continue
        decision = wr2_get_mgmt_decision(row)

        if decision == WR2_MGMT_INCLUDE and wr2_line_is_fully_admitted(row):
            continue

        if decision == WR2_MGMT_INCLUDE_RISK:
            reason = wr2_get_risk_reason_text(pid)
            comment = wr2_get_risk_comment(pid)
            overrides[pid] = {
                "management_override": True,
                "override_by": created_by,
                "override_at": now_iso,
                "override_reason": reason,
                "override_risk_comment": comment or reason,
                "override_basis": (
                    f"{reason} | Ответственный: {wr2_get_risk_responsible(pid)} | "
                    f"Срок: {wr2_get_risk_deadline(pid)}"
                ),
            }
            continue

        if decision != WR2_MGMT_INCLUDE:
            continue

        # Manual INCLUDE of incomplete admission (WAITING/BLOCKED/…) must carry override.
        if not wr2_writer_needs_override_for_row(row):
            continue

        reason, comment, basis_text = wr2_manual_include_override_reason(pid)
        if wr2_is_blank_reason(reason):
            continue
        overrides[pid] = {
            "management_override": True,
            "override_by": created_by,
            "override_at": now_iso,
            "override_reason": reason,
            "override_risk_comment": comment or reason,
            "override_basis": basis_text or reason,
        }
    return overrides


def wr2_passport_draft_coverage_gaps(
    board_df: pd.DataFrame,
    overrides_by_line: Dict[str, Dict[str, Any]],
    *,
    allow_risk: bool = True,
) -> List[str]:
    """BOQ codes that are in draft but would be skipped by writer without coverage."""
    gaps: List[str] = []
    for _, row in board_df.iterrows():
        if not wr2_row_in_passport_inclusion(row, allow_risk=allow_risk):
            continue
        pid = safe_str(row.get("plan_line_id"))
        if not pid:
            continue
        if not wr2_writer_needs_override_for_row(row):
            continue
        if pid in overrides_by_line:
            continue
        gaps.append(display_dash(row.get("boq_code")))
    return gaps


def wr2_compute_passport_composition_table(board_df: pd.DataFrame) -> pd.DataFrame:
    comp = st.session_state.get(WR2_SESSION_COMPOSITION, {})
    if not comp:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    board_by_id = {
        safe_str(r.get("plan_line_id")): r for _, r in board_df.iterrows()
    }
    for pid, item in comp.items():
        row = board_by_id.get(pid)
        rows.append(
            {
                "_plan_line_id": pid,
                "BOQ-код": display_dash(item.get("boq_code")),
                "Наименование": display_dash(item.get("boq_name")),
                "Управленческое решение": safe_str(item.get("decision")),
                "Плановая стоимость": money_ru(
                    item.get("plan_value") or (row.get("plan_value_num") if row is not None else 0)
                ),
                "Трудозатраты": wr2_format_hours(
                    safe_num(item.get("labor_hours") or (row.get("labor_hours") if row is not None else 0))
                ),
                "Риск / блокер": safe_str(item.get("risk_blocker")) or "—",
                "Основание": safe_str(item.get("basis")) or "—",
                "Ответственный": safe_str(item.get("responsible")) or "—",
            }
        )
    return pd.DataFrame(rows)


def wr2_compute_passport_inclusion_rows(
    board_df: pd.DataFrame,
    *,
    allow_risk: bool = True,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, row in board_df.iterrows():
        included = wr2_row_in_passport_inclusion(row, allow_risk=allow_risk)
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
    *,
    allow_risk: bool = True,
) -> Dict[str, Any]:
    if st.session_state.get(WR2_SESSION_FORMING):
        return {
            "status": "error",
            "passport_id": None,
            "created_lines": 0,
            "skipped_blocked": 0,
            "blocked_without_override": 0,
            "override_included_rows": 0,
            "skipped_waiting": 0,
            "total_value": 0.0,
            "total_hours": 0.0,
            "errors": [
                "Формирование паспорта уже выполняется. Дождитесь завершения текущего вызова."
            ],
            "warnings": [],
            "source_kind": None,
            "expected_included_count": 0,
            "previous_rows": 0,
            "current_rows": 0,
        }

    inclusion_rows = [
        row
        for _, row in board_df.iterrows()
        if wr2_row_in_passport_inclusion(row, allow_risk=allow_risk)
        and safe_str(row.get("plan_line_id"))
    ]
    inclusion_ids = {
        safe_str(row.get("plan_line_id")) for row in inclusion_rows
    }
    expected_included_count = len(inclusion_ids)
    boq_by_line_id = {
        safe_str(row.get("plan_line_id")): row.get("boq_code")
        for row in inclusion_rows
    }

    empty_summary: Dict[str, Any] = {
        "status": "error",
        "passport_id": None,
        "created_lines": 0,
        "skipped_blocked": 0,
        "blocked_without_override": 0,
        "override_included_rows": 0,
        "skipped_waiting": 0,
        "total_value": 0.0,
        "total_hours": 0.0,
        "errors": [],
        "warnings": [],
        "source_kind": None,
        "expected_included_count": expected_included_count,
        "previous_rows": 0,
        "current_rows": 0,
    }

    preflight = monthly_passport_service.preflight_new_passport(
        project_code,
        month_key,
        inclusion_line_ids=sorted(inclusion_ids),
        boq_by_line_id=boq_by_line_id,
    )
    if not preflight.get("ok"):
        empty_summary["status"] = str(preflight.get("status") or "error")
        empty_summary["passport_id"] = preflight.get("passport_id")
        empty_summary["errors"] = list(preflight.get("errors") or [])
        return empty_summary

    validation_errors = wr2_collect_passport_override_errors(
        board_df, allow_risk=allow_risk
    )
    if validation_errors:
        empty_summary["errors"] = validation_errors
        return empty_summary

    overrides_by_line = wr2_build_passport_override_payload(
        board_df, created_by, allow_risk=allow_risk
    )

    coverage_gaps = wr2_passport_draft_coverage_gaps(
        board_df, overrides_by_line, allow_risk=allow_risk
    )
    if coverage_gaps:
        codes = ", ".join(coverage_gaps)
        empty_summary["errors"] = [
            "Формирование остановлено: в драфте обязательства есть коды без "
            "полного допуска и без management override. "
            f"BOQ: {codes}. Укажите основание решения или включите с риском."
        ]
        return empty_summary

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

    st.session_state[WR2_SESSION_FORMING] = True
    monthly_passport_service._read_override_from_queue = _patched_read_override
    monthly_passport_service._resolve_admission_status = _patched_resolve
    try:
        summary = create_monthly_passport(
            project_code=project_code,
            month_key=month_key,
            created_by=created_by,
        )
    finally:
        monthly_passport_service._read_override_from_queue = original_read
        monthly_passport_service._resolve_admission_status = original_resolve
        st.session_state[WR2_SESSION_FORMING] = False

    if not isinstance(summary, dict):
        return empty_summary

    summary.setdefault("warnings", [])
    summary["expected_included_count"] = expected_included_count
    created_lines = int(summary.get("created_lines") or summary.get("current_rows") or 0)
    if summary.get("status") in ("created", "rebuilt") and created_lines != expected_included_count:
        included_boqs = {
            display_dash(row.get("boq_code"))
            for row in inclusion_rows
        }
        missing_hint = (
            f"Ожидалось строк драфта: {expected_included_count}, "
            f"в паспорт записано: {created_lines}. "
            f"BOQ в драфте: {', '.join(sorted(included_boqs))}."
        )
        summary["warnings"].append(
            "Расхождение состава драфта и паспорта. " + missing_hint
        )
    return summary


@dataclass
class LineConstraintIndex:
    """Pre-aggregated constraint state for one plan_line_id (department grain)."""

    counts: Dict[str, int] = field(
        default_factory=lambda: {
            "hold": 0,
            "fail": 0,
            "warning": 0,
            "waiting": 0,
            "pass": 0,
            "total": 0,
        }
    )
    check_statuses: List[str] = field(default_factory=list)
    # responsible_department (as str, matching DataFrame.astype(str)) → status keys
    dept_keys: Dict[str, List[str]] = field(default_factory=dict)
    has_overdue: bool = False
    # (status_key, blocked_compact_text, reason_text) in original row order
    reason_items: List[Tuple[str, str, str]] = field(default_factory=list)
    # Active (non-closed) FAIL/HOLD/WARNING/ОЖИДАЕТ details for reason column + work zone
    active_blocking_details: List[Dict[str, Any]] = field(default_factory=list)
    first_row: Optional[Dict[str, Any]] = None


_EMPTY_LINE_CONSTRAINT_INDEX = LineConstraintIndex()


def build_constraint_department_index(
    constraints_df: pd.DataFrame,
) -> Dict[str, LineConstraintIndex]:
    """One-pass line_id → department aggregation for War Room read-model.

    Replaces repeated constraints_df / group filters inside the plan-line loop.
    """
    index: Dict[str, LineConstraintIndex] = {}
    if constraints_df.empty or "line_id" not in constraints_df.columns:
        return index

    line_series = constraints_df["line_id"]
    valid = line_series.notna() & (line_series.astype(str).str.strip() != "")
    if not valid.any():
        return index

    has_check = "check_status" in constraints_df.columns
    has_dept = "responsible_department" in constraints_df.columns
    has_overdue_col = "is_overdue" in constraints_df.columns
    has_promise_overdue_col = "is_promise_overdue" in constraints_df.columns
    has_resolution = "resolution_status" in constraints_df.columns

    for line_id, part in constraints_df.loc[valid].groupby(
        line_series.loc[valid].astype(str), dropna=False
    ):
        lid = safe_str(line_id)
        if not lid:
            continue

        counts = {
            "hold": 0,
            "fail": 0,
            "warning": 0,
            "waiting": 0,
            "pass": 0,
            "total": 0,
        }
        check_statuses: List[str] = []
        dept_keys: Dict[str, List[str]] = {}
        reason_items: List[Tuple[str, str, str]] = []
        active_blocking_details: List[Dict[str, Any]] = []
        first_row: Optional[Dict[str, Any]] = None

        if has_overdue_col:
            has_overdue = bool(part["is_overdue"].astype(bool).any())
        elif has_promise_overdue_col:
            has_overdue = bool(part["is_promise_overdue"].astype(bool).any())
        else:
            has_overdue = False

        for _, row in part.iterrows():
            if first_row is None:
                first_row = row.to_dict()

            if not has_check:
                continue

            status = norm_check_status_key(row.get("check_status"))
            check_statuses.append(status)
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

            if has_dept:
                # Match group[col].astype(str) used by legacy filters (NaN → "nan")
                dept_db = str(row.get("responsible_department"))
                dept_keys.setdefault(dept_db, []).append(status)

            reason_items.append(
                (
                    status,
                    constraint_decision_line_compact(row, dept_ui),
                    reason_text(row),
                )
            )

            # Display-only active reasons (does not affect outcome counts)
            resolution = (
                safe_str(row.get("resolution_status")).upper()
                if has_resolution
                else ""
            )
            if resolution in CLOSED_RESOLUTION_STATUSES:
                continue
            if status == "PASS" or status not in ACTIVE_BLOCKING_STATUS_PRIORITY:
                continue
            concrete = concrete_blocking_reason_text(row)
            if status == "ОЖИДАЕТ" and not concrete:
                continue
            dept_label = wr2_registry_dept_short_label(
                row.get("responsible_department")
            )
            if not dept_label or dept_label == "—":
                dept_label = safe_str(row.get("responsible_department")) or "—"
            owner = safe_str(row.get("owner_name")) or "Не заполнено автором"
            active_blocking_details.append(
                {
                    "dept": dept_label,
                    "status": status,
                    "status_ru": ACTIVE_CONSTRAINT_STATUS_RU.get(status, status),
                    "reason": concrete or BLOCKING_REASON_MISSING,
                    "owner": owner,
                    "due": format_blocking_reason_due(row),
                    "priority": ACTIVE_BLOCKING_STATUS_PRIORITY[status],
                }
            )

        index[lid] = LineConstraintIndex(
            counts=counts,
            check_statuses=check_statuses,
            dept_keys=dept_keys,
            has_overdue=has_overdue,
            reason_items=reason_items,
            active_blocking_details=active_blocking_details,
            first_row=first_row,
        )

    return index


def _indexed_depts_with_statuses(
    line_state: LineConstraintIndex, status_keys: frozenset[str]
) -> List[str]:
    names: List[str] = []
    for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
        keys = line_state.dept_keys.get(dept_db, [])
        if any(k in status_keys for k in keys):
            names.append(col_label)
    return names


def _indexed_admission_logic_explanation(
    counts: Dict[str, int], line_state: LineConstraintIndex
) -> str:
    if counts["total"] == 0:
        return "Нет проверок → Нет проверок"
    hold_depts = _indexed_depts_with_statuses(line_state, frozenset({"HOLD"}))
    if hold_depts:
        return f"Есть HOLD от {', '.join(hold_depts)} → Заблокировано"
    fail_depts = _indexed_depts_with_statuses(line_state, frozenset({"FAIL"}))
    if fail_depts:
        return f"Есть FAIL от {', '.join(fail_depts)} → Заблокировано"
    waiting_depts = _indexed_depts_with_statuses(line_state, frozenset({"ОЖИДАЕТ"}))
    if waiting_depts:
        return f"Есть WAITING от {', '.join(waiting_depts)} → Ожидает проверки"
    if counts["waiting"] > 0:
        return "Есть WAITING → Ожидает проверки"
    warning_depts = _indexed_depts_with_statuses(line_state, frozenset({"WARNING"}))
    if warning_depts:
        return (
            f"Есть WARNING от {', '.join(warning_depts)}, HOLD/FAIL нет → Допущено с риском"
        )
    if counts["warning"] > 0:
        return "Есть WARNING, HOLD/FAIL нет → Допущено с риском"
    return "Все отделы PASS → Допущено"


def _indexed_blocking_departments_text(line_state: LineConstraintIndex) -> str:
    blockers = _indexed_depts_with_statuses(line_state, frozenset({"HOLD", "FAIL"}))
    if blockers:
        return ", ".join(blockers)
    warn = _indexed_depts_with_statuses(line_state, frozenset({"WARNING"}))
    if warn:
        return f"Риск: {', '.join(warn)}"
    waiting = _indexed_depts_with_statuses(line_state, frozenset({"ОЖИДАЕТ"}))
    if waiting:
        return f"Ожидают: {', '.join(waiting)}"
    return "—"


def _indexed_outcome_status_reason(
    line_state: LineConstraintIndex, counts: Dict[str, int]
) -> str:
    if counts["total"] == 0:
        return "Проверки не сформированы"
    blockers = _indexed_depts_with_statuses(line_state, frozenset({"HOLD", "FAIL"}))
    if blockers:
        return f"Блокируют: {', '.join(blockers)}"
    hold_depts = _indexed_depts_with_statuses(line_state, frozenset({"HOLD"}))
    if hold_depts:
        return f"HOLD: {', '.join(hold_depts)}"
    fail_depts = _indexed_depts_with_statuses(line_state, frozenset({"FAIL"}))
    if fail_depts:
        return f"FAIL: {', '.join(fail_depts)}"
    waiting_depts = _indexed_depts_with_statuses(line_state, frozenset({"ОЖИДАЕТ"}))
    no_check: List[str] = []
    # Missing responsible_department column ⇒ dept_keys empty ⇒ все отделы «Нет проверки»
    for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
        if not line_state.dept_keys.get(dept_db):
            no_check.append(col_label)
    if waiting_depts or no_check or counts["waiting"] > 0:
        parts: List[str] = []
        if waiting_depts:
            parts.append(f"Ожидают проверки: {', '.join(waiting_depts)}")
        elif counts["waiting"] > 0:
            parts.append("Ожидают проверки отделов")
        if no_check:
            parts.append(f"Нет проверки: {', '.join(no_check)}")
        return "; ".join(parts)
    if counts["warning"] > 0:
        warn_depts = _indexed_depts_with_statuses(line_state, frozenset({"WARNING"}))
        if warn_depts:
            return f"Риск / уточнение: {', '.join(warn_depts)}"
        return "Есть замечания WARNING"
    return "Все проверки пройдены"


def _indexed_dept_badge(line_state: LineConstraintIndex, dept_db: str) -> str:
    keys = line_state.dept_keys.get(dept_db, [])
    if not keys:
        return WR2_DEPT_BADGE["ОЖИДАЕТ"]
    worst = worst_check_status(keys)
    return WR2_DEPT_BADGE.get(worst, WR2_DEPT_BADGE["ОЖИДАЕТ"])


def _indexed_classic_dept_status(line_state: LineConstraintIndex, dept_db: str) -> str:
    keys = line_state.dept_keys.get(dept_db, [])
    if not keys:
        return DEPT_STATUS_NO_CHECK
    worst = worst_check_status(keys)
    if not worst:
        return DEPT_STATUS_NO_CHECK
    return DEPT_STATUS_LABEL.get(worst, DEPT_STATUS_NO_CHECK)


def _indexed_critical_department(line_state: LineConstraintIndex) -> str:
    worst_prio = -1
    worst_label = "—"
    for label, dept_db in WR2_DEPT_COLUMNS:
        keys = line_state.dept_keys.get(dept_db, [])
        if not keys:
            prio = STATUS_PRIORITY["ОЖИДАЕТ"]
        else:
            worst_key = worst_check_status(keys)
            prio = STATUS_PRIORITY.get(worst_key, 0)
        if prio > worst_prio:
            worst_prio = prio
            worst_label = label
    return worst_label


def _indexed_line_reason_summary(
    line_state: LineConstraintIndex, outcome: str
) -> str:
    if line_state.counts["total"] == 0 or outcome in (
        ADMISSION_OK,
        ADMISSION_NO_CHECKS,
    ):
        return "—"
    if outcome == ADMISSION_BLOCKED:
        wanted: Optional[frozenset[str]] = frozenset({"HOLD", "FAIL"})
        use_blocked = True
    elif outcome == ADMISSION_WAITING:
        wanted = frozenset({"ОЖИДАЕТ"})
        use_blocked = False
    elif outcome == ADMISSION_RISK:
        wanted = frozenset({"WARNING"})
        use_blocked = False
    else:
        wanted = None
        use_blocked = False

    parts: List[str] = []
    seen: set[str] = set()
    for status, blocked_text, rtext in line_state.reason_items:
        if wanted is not None and status not in wanted:
            continue
        text = blocked_text if use_blocked else rtext
        if text != "—" and text not in seen:
            seen.add(text)
            parts.append(text)
    return "; ".join(parts) if parts else "—"


def _indexed_blocking_reason_summary(
    line_state: LineConstraintIndex,
) -> Tuple[str, int, List[Dict[str, Any]]]:
    """Aggregate active dept reasons for registry + work zone (display-only)."""
    details = sorted(
        line_state.active_blocking_details,
        key=lambda item: (
            int(item.get("priority", 99)),
            safe_str(item.get("dept")),
            safe_str(item.get("reason")),
        ),
    )
    parts: List[str] = []
    seen: set[str] = set()
    ordered_details: List[Dict[str, Any]] = []
    for item in details:
        dept = safe_str(item.get("dept")) or "—"
        reason = safe_str(item.get("reason")) or BLOCKING_REASON_MISSING
        label = f"{dept}: {reason}"
        if label in seen:
            continue
        seen.add(label)
        parts.append(label)
        ordered_details.append(item)
    if not parts:
        return BLOCKING_REASON_EMPTY, 0, []
    return "; ".join(parts), len(parts), ordered_details


@st.cache_data(ttl=300, show_spinner=False)
def build_war_room_read_model(
    constraints_df: pd.DataFrame,
    v2_df: pd.DataFrame,
    queue_df: pd.DataFrame,
) -> pd.DataFrame:
    """1 строка = 1 plan_line_id. v2 first, legacy queue fallback.

    Pure read-model builder (no session_state, no Supabase writes).
    Cached for Streamlit reruns; invalidate via clear_war_room_data_caches().
    """
    constraint_index = build_constraint_department_index(constraints_df)
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
                "labor_hours": safe_num(row.get("labor_hours")),
                "labor_cost": safe_num(row.get("labor_cost")),
                "crew_size": safe_num(row.get("crew_size")),
                "queue_display": derive_construction_queue_from_facility(facility),
                "title_display": facility,
                "system_display": display_dash(row.get("system")),
                "package_display": display_dash(row.get("iwp")),
                "source": "v2",
            }

    for line_id, line_state in constraint_index.items():
        if line_id in plan_meta:
            continue
        first = line_state.first_row or {}
        facility = wr2_plan_facility(first)
        plan_meta[line_id] = {
            "plan_line_id": line_id,
            "project_code": safe_str(first.get("project_code")),
            "month_key": safe_str(first.get("month_key")),
            "boq_code": safe_str(first.get("boq_code")),
            "boq_name": safe_str(first.get("boq_name")),
            "crew": wr2_plan_crew(first),
            "facility": facility,
            "discipline": wr2_plan_discipline(first),
            "planned_qty": safe_num(first.get("planned_qty")),
            "plan_value": safe_num(first.get("plan_value")),
            "labor_hours": safe_num(first.get("labor_hours") or first.get("required_hours")),
            "labor_cost": safe_num(first.get("labor_cost")),
            "crew_size": safe_num(first.get("crew_size")),
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
                "labor_hours": safe_num(qrow.get("labor_hours") or qrow.get("required_hours")),
                "labor_cost": safe_num(qrow.get("labor_cost")),
                "crew_size": safe_num(qrow.get("crew_size")),
                "queue_display": derive_construction_queue_from_facility(facility),
                "title_display": facility,
                "system_display": "—",
                "package_display": "—",
                "source": "legacy_queue",
            }

    rows: List[Dict[str, Any]] = []
    empty_state = _EMPTY_LINE_CONSTRAINT_INDEX
    for pid, meta in plan_meta.items():
        line_state = constraint_index.get(pid, empty_state)
        counts = line_state.counts
        outcome = resolve_war_room_line_outcome(counts, pd.DataFrame())
        classic_outcome = wr2_outcome_for_classic(outcome)
        reason_summary, reason_count, reason_details = _indexed_blocking_reason_summary(
            line_state
        )
        row_data: Dict[str, Any] = {
            **meta,
            **wr2_plan_economics(meta),
            "outcome": outcome,
            "classic_outcome": classic_outcome,
            "logic_outcome": _indexed_admission_logic_explanation(counts, line_state),
            "action_needed": build_action_needed(classic_outcome),
            "critical_department": _indexed_critical_department(line_state),
            "blocking_departments": _indexed_blocking_departments_text(line_state),
            "outcome_status_reason": _indexed_outcome_status_reason(line_state, counts),
            "has_overdue": line_state.has_overdue,
            "passport_include": passport_includes_outcome(classic_outcome),
            "reason": _indexed_line_reason_summary(line_state, classic_outcome),
            "blocking_reason_summary": reason_summary,
            "blocking_reason_count": reason_count,
            "active_blocking_details": reason_details,
            "hold_count": counts["hold"],
            "fail_count": counts["fail"],
            "warning_count": counts["warning"],
            "waiting_count": counts["waiting"],
            "checks_percent": wr2_checks_percent(counts),
            "_check_statuses": list(line_state.check_statuses),
            "_sort": WR2_OUTCOME_SORT.get(outcome, 99),
        }
        for col_label, dept_db in WR2_DEPT_COLUMNS:
            row_data[f"dept_{col_label}"] = _indexed_dept_badge(line_state, dept_db)
        for col_label, dept_db in ADMISSION_DEPT_COLUMNS:
            row_data[f"classic_{col_label}"] = _indexed_classic_dept_status(
                line_state, dept_db
            )
        rows.append(row_data)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    return result.sort_values(
        ["_sort", "plan_value_num"], ascending=[True, False]
    ).copy()


def clear_war_room_data_caches() -> None:
    """Точечная инвалидация read-model / loader caches (без глобального clear)."""
    load_constraints.clear()
    load_v2_plan_lines.clear()
    load_review_queue.clear()
    build_war_room_read_model.clear()


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
        .admission-plan-list-kpi-panel {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #f8fafc;
            padding: 0.75rem 0.85rem 0.65rem;
            margin: 0.35rem 0 0.85rem 0;
        }
        .v2-kpi-row {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.85rem 0 1rem 0;
        }
        .admission-plan-list-kpi-panel .v2-kpi-row {
            margin: 0;
        }
        .v2-kpi-card {
            display: flex;
            align-items: flex-start;
            gap: 0.65rem;
            padding: 0.85rem 0.95rem;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #ffffff;
            min-height: 78px;
        }
        .v2-kpi-card-icon {
            flex: 0 0 34px;
            width: 34px;
            height: 34px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            font-weight: 700;
        }
        .v2-kpi-card--total .v2-kpi-card-icon { background: #E8EEF5; color: #475F7B; }
        .v2-kpi-card--open .v2-kpi-card-icon { background: #E6EEF8; color: #2E5B9A; }
        .v2-kpi-card--ready .v2-kpi-card-icon { background: #E7F5EE; color: #2F6B4F; }
        .v2-kpi-card--blocked .v2-kpi-card-icon { background: #FEE2E2; color: #B91C1C; }
        .v2-kpi-card--risk .v2-kpi-card-icon { background: #F9EDE8; color: #A65F45; }
        .v2-kpi-card--muted .v2-kpi-card-icon {
            background: #f1f5f9;
            color: #64748b;
        }
        .v2-kpi-card-label {
            font-size: 0.72rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.15rem;
        }
        .v2-kpi-card-value {
            font-size: 1.35rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.15;
        }
        .admission-plan-list-kpi-row--risk {
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 0.55rem;
            margin-bottom: 0.15rem;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card {
            min-height: 66px;
            padding: 0.6rem 0.7rem;
            gap: 0.5rem;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card-icon {
            flex: 0 0 28px;
            width: 28px;
            height: 28px;
            font-size: 0.75rem;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card-label {
            font-size: 0.62rem;
            line-height: 1.2;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card-value {
            font-size: 1.05rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _apply_wr2_registry_cell_style(styler, func, column: str):
    if column not in styler.data.columns:
        return styler
    if hasattr(styler, "map"):
        return styler.map(func, subset=pd.IndexSlice[:, [column]])
    return styler.applymap(func, subset=pd.IndexSlice[:, [column]])


def format_wr2_registry_status_display(val: Any) -> str:
    """Display-only uppercase labels — aligned with Page 21 decision registry."""
    text = safe_str(val)
    if not text or text == "—":
        return "—"
    conflict_prefix = ""
    mark = f"{WR2_PASSPORT_CONFLICT_MARK} "
    if text.startswith(mark):
        conflict_prefix = mark
        text = text[len(mark) :].strip()
    mapped = WR2_REGISTRY_STATUS_DISPLAY.get(text)
    if mapped:
        return f"{conflict_prefix}{mapped}"
    upper = WR2_REGISTRY_STATUS_DISPLAY.get(text.upper(), text.upper())
    return f"{conflict_prefix}{upper}"


def style_wr2_registry_status_text(val: Any) -> str:
    text = wr2_strip_passport_conflict_mark(val).strip().upper()
    if not text or text == "—":
        return "color: #64748b;"
    return WR2_REGISTRY_STATUS_TEXT_STYLE.get(text, "color: #475569;")


def wr2_registry_status_column_names(df: pd.DataFrame) -> List[str]:
    cols = ["Итог допуска", "Итоговое решение", WR2_PASSPORT_STATUS_COLUMN]
    cols.extend(label for label, _ in WR2_BOARD_DEPT_DISPLAY if label in df.columns)
    return [c for c in cols if c in df.columns]


def prepare_wr2_registry_display_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in wr2_registry_status_column_names(out):
        out[col] = out[col].apply(format_wr2_registry_status_display)
    return out


def style_war_room_board_table(df_in: pd.DataFrame):
    styler = df_in.style
    for col in wr2_registry_status_column_names(df_in):
        styler = _apply_wr2_registry_cell_style(styler, style_wr2_registry_status_text, col)
        if col == WR2_PASSPORT_STATUS_COLUMN:
            styler = _apply_wr2_registry_cell_style(
                styler, wr2_passport_status_cell_background, col
            )
    return styler


def wr2_passport_status_cell_background(val: Any) -> str:
    base = wr2_strip_passport_conflict_mark(val)
    bg = WR2_PASSPORT_STATUS_BG.get(base, "")
    if safe_str(val).startswith(WR2_PASSPORT_CONFLICT_MARK):
        # Keep status color; conflict is shown via marker + caption.
        return bg or "background-color: #fff7ed;"
    return bg


def _war_room_plan_summary_kpi_card_html(label: str, value: str, variant: str) -> str:
    icons = {
        "total": "∑",
        "open": "○",
        "ready": "✓",
        "blocked": "!",
        "risk": "₽",
        "muted": "·",
    }
    icon = icons.get(variant, "·")
    return (
        f'<div class="v2-kpi-card v2-kpi-card--{variant}">'
        f'<div class="v2-kpi-card-icon">{icon}</div>'
        f"<div>"
        f'<div class="v2-kpi-card-label">{label}</div>'
        f'<div class="v2-kpi-card-value">{value}</div>'
        f"</div></div>"
    )


def wr2_build_registry_column_config(show_cols: List[str]) -> Dict[str, Any]:
    """Display-only column config for unified registry (tooltip on final decision)."""
    config: Dict[str, Any] = {}
    for col in show_cols:
        if col == "Итоговое решение":
            config[col] = st.column_config.TextColumn(
                col,
                help=WR2_FINAL_DECISION_COLUMN_HELP,
                disabled=True,
            )
        elif col == WR2_PASSPORT_STATUS_COLUMN:
            config[col] = st.column_config.TextColumn(
                col,
                help=(
                    f"{WR2_PASSPORT_STATUS_COLUMN_HELP} "
                    f"{WR2_PASSPORT_CONFLICT_MARK} = {WR2_PASSPORT_CONFLICT_HELP}"
                ),
                disabled=True,
            )
        else:
            config[col] = st.column_config.TextColumn(col, disabled=True)
    return config


def render_war_room_v3_summary(board_df: pd.DataFrame) -> None:
    st.markdown("### Сводка по месячному плану")
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
        board_df.loc[board_df["outcome"] == WR2_OUTCOME_RISK, "plan_value_num"].sum()
    )
    value_blocked = float(
        board_df.loc[board_df["outcome"] == WR2_OUTCOME_BLOCKED, "plan_value_num"].sum()
    )
    wait_value = float(
        board_df.loc[
            board_df["outcome"].isin([WR2_OUTCOME_WAITING, WR2_OUTCOME_NO_CHECKS]),
            "plan_value_num",
        ].sum()
    )
    summary_cards = "".join(
        [
            _war_room_plan_summary_kpi_card_html("Всего кодов", str(total), "total"),
            _war_room_plan_summary_kpi_card_html("Допущено", str(ok_cnt), "ready"),
            _war_room_plan_summary_kpi_card_html(
                "Допущено с риском", str(risk_cnt), "open"
            ),
            _war_room_plan_summary_kpi_card_html(
                "Заблокировано", str(blocked_cnt), "blocked"
            ),
            _war_room_plan_summary_kpi_card_html(
                "Стоимость допущенных работ",
                money_ru_compact(value_ok),
                "ready",
            ),
            _war_room_plan_summary_kpi_card_html(
                "Стоимость работ под риском",
                money_ru_compact(value_risk),
                "risk",
            ),
            _war_room_plan_summary_kpi_card_html(
                "Стоимость заблокированных работ",
                money_ru_compact(value_blocked),
                "blocked",
            ),
        ]
    )
    st.markdown(
        f"""
        <div class="admission-plan-list-kpi-panel">
            <div class="v2-kpi-row admission-plan-list-kpi-row--risk">{summary_cards}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        f"Ожидает проверки: {wait_cnt} код(ов) · Стоимость: {money_ru_compact(wait_value)}"
    )


def render_war_room_v3_filters(
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
    st.markdown("### Срез месячного плана")
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


def render_war_room_v3_unified_registry(
    board_df: pd.DataFrame,
    constraints_df: pd.DataFrame,
) -> Optional[str]:
    st.markdown("### Единый реестр кодов месяца")
    st.caption(
        "Полный реестр месячного плана по итогу допуска. "
        "Выберите строку для управленческого решения. "
        "Редактирование допуска — только на странице «Допуск месячного плана»."
    )
    if board_df.empty:
        st.info("Нет кодов по выбранным фильтрам.")
        return st.session_state.get(WR2_SESSION_SELECTED)

    registry_df = wr2_build_unified_registry_df(board_df, constraints_df)
    if registry_df.empty:
        st.info("Нет кодов по выбранным фильтрам.")
        return st.session_state.get(WR2_SESSION_SELECTED)

    needs_review_cnt = int((registry_df["_needs_review_sort"] == 0).sum())
    total_cnt = len(registry_df)
    conflict_cnt = 0
    if "_passport_decision_conflict" in registry_df.columns:
        conflict_cnt = int(registry_df["_passport_decision_conflict"].astype(bool).sum())
    st.caption(
        f"Показано {total_cnt} кодов · Требует рассмотрения: {needs_review_cnt}. "
        "Выберите строку для управленческого решения."
    )
    if conflict_cnt:
        st.caption(
            f"⚠ Расхождений intent/паспорт: {conflict_cnt}. "
            f"{WR2_PASSPORT_CONFLICT_HELP}"
        )

    show_cols = [c for c in WR2_BOARD_TABLE_COLUMNS if c in registry_df.columns]
    show = prepare_wr2_registry_display_table(registry_df[show_cols])
    st.dataframe(
        style_war_room_board_table(show),
        use_container_width=True,
        hide_index=True,
        height=WR2_REGISTRY_TABLE_HEIGHT_PX,
        on_select="rerun",
        selection_mode="single-row",
        key=WR2_REGISTRY_SELECT_KEY,
        column_config=wr2_build_registry_column_config(show_cols),
    )
    return wr2_resolve_unified_registry_selection(registry_df)


def render_war_room_v3_code_card(row: pd.Series) -> None:
    boq = display_dash(row.get("boq_code"))
    boq_name = display_dash(row.get("boq_name"))
    pid = safe_str(row.get("plan_line_id"))
    label = f"Карточка кода · {boq}"
    if boq_name != "—":
        label = f"{label} — {boq_name}"

    with st.expander(label, expanded=False):
        st.markdown(f"**{boq}** — {boq_name}")
        wr2_render_outcome_status(safe_str(row.get("outcome")))
        st.markdown(f"**Система:** {display_dash(row.get('system_display'))}")
        st.markdown(f"**Титул:** {display_dash(row.get('title_display'))}")
        qty = safe_num(row.get("planned_qty"))
        st.markdown(
            f"**Объём:** {f'{qty:,.3f}'.replace(',', ' ') if qty else '—'}"
        )
        st.markdown(f"**Стоимость:** {money_ru(row.get('plan_value_num'))}")

        dept_parts: List[str] = []
        for display_label, classic_label in WR2_BOARD_DEPT_DISPLAY:
            status = safe_str(row.get(f"classic_{classic_label}"))
            if status and status != "—":
                dept_parts.append(f"**{display_label}:** {status}")
        if dept_parts:
            st.markdown("**Статусы отделов**")
            for part in dept_parts:
                st.markdown(part)

        st.markdown("**Активные ограничения по отделам**")
        details_raw = row.get("active_blocking_details")
        details: List[Dict[str, Any]] = []
        if isinstance(details_raw, list):
            details = [item for item in details_raw if isinstance(item, dict)]
        if not details:
            st.caption("Активные ограничения отсутствуют")
        else:
            detail_rows = [
                {
                    "Отдел": safe_str(item.get("dept")) or "—",
                    "Статус": safe_str(item.get("status_ru"))
                    or ACTIVE_CONSTRAINT_STATUS_RU.get(
                        safe_str(item.get("status")), safe_str(item.get("status"))
                    )
                    or "—",
                    "Причина": safe_str(item.get("reason")) or BLOCKING_REASON_MISSING,
                    "Ответственный": safe_str(item.get("owner"))
                    or "Не заполнено автором",
                    "Срок": safe_str(item.get("due")) or "Не определён",
                }
                for item in details
            ]
            st.dataframe(
                pd.DataFrame(detail_rows),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("**Основные ограничения**")
        st.markdown(display_dash(row.get("blocking_departments")))
        reason = display_dash(row.get("reason"))
        if reason != "—":
            st.markdown(f"**Причина ограничения:** {reason}")
        summary = safe_str(row.get("blocking_reason_summary"))
        if summary and summary != BLOCKING_REASON_EMPTY:
            st.markdown(f"**Почему не допущен:** {summary}")
        st.caption(display_dash(row.get("outcome_status_reason")))

        st.markdown(
            f"**Проект:** {display_dash(row.get('project_code'))} · "
            f"**Месяц:** {display_dash(row.get('month_key'))} · "
            f"**Источник:** {wr2_source_display_label(row.get('source'))}"
        )
        st.markdown(
            f"**Критичный отдел:** {display_dash(row.get('critical_department'))} · "
            f"**plan_line_id:** `{pid}`"
        )


def render_war_room_v3_decision_panel(row: pd.Series) -> None:
    st.markdown("#### Управленческое решение")
    pid = safe_str(row.get("plan_line_id"))
    outcome = safe_str(row.get("outcome"))
    durable_decision = wr2_get_mgmt_decision(row)
    default_decision = durable_decision
    if outcome == WR2_OUTCOME_OK and default_decision not in WR2_MGMT_OPTIONS:
        default_decision = WR2_MGMT_INCLUDE

    if wr2_has_durable_mgmt_decision(pid) and durable_decision in WR2_MGMT_OPTIONS:
        st.markdown(
            f"**Текущее решение:** {wr2_mgmt_display_label(durable_decision)}"
        )

    st.radio(
        "Вариант решения",
        WR2_MGMT_OPTIONS,
        index=WR2_MGMT_OPTIONS.index(default_decision)
        if default_decision in WR2_MGMT_OPTIONS
        else 0,
        format_func=wr2_mgmt_display_label,
        key=wr2_live_decision_key(pid),
        horizontal=True,
    )

    live_decision = wr2_get_live_decision(row)
    if (
        wr2_has_durable_mgmt_decision(pid)
        and durable_decision in WR2_MGMT_OPTIONS
        and live_decision in WR2_MGMT_OPTIONS
        and live_decision != durable_decision
    ):
        st.markdown(
            f"**Новое решение:** {wr2_mgmt_display_label(live_decision)}"
        )


def render_war_room_v3_decision_basis(row: pd.Series, decision: str) -> None:
    st.markdown("#### Обоснование принятого решения")
    pid = safe_str(row.get("plan_line_id"))
    b1, b2 = st.columns(2)
    with b1:
        st.text_area(
            "Основание решения",
            key=wr2_decision_basis_key(pid),
            height=80,
        )
        st.text_input(
            "Ответственный",
            key=wr2_decision_responsible_key(pid),
        )
    with b2:
        st.text_input(
            "Срок пересмотра",
            placeholder="например: 15.07.2026",
            key=wr2_decision_review_deadline_key(pid),
        )
        st.text_area(
            "Комментарий",
            key=wr2_decision_comment_key(pid),
            height=80,
        )
    if decision == WR2_MGMT_INCLUDE_RISK:
        outcome_is_blocked = safe_str(row.get("outcome")) == WR2_OUTCOME_BLOCKED
        st.caption(
            f"Причина блокировки: {display_dash(row.get('reason'))} | "
            f"Критичный отдел: {display_dash(row.get('critical_department'))}"
        )
        if outcome_is_blocked:
            st.warning(
                "Код заблокирован отделом допуска. Включение возможно только как управленческий риск."
            )


def render_war_room_v3_risk_protocol(row: pd.Series) -> None:
    st.markdown("#### Протокол принятия риска")
    pid = safe_str(row.get("plan_line_id"))
    r1, r2 = st.columns(2)
    with r1:
        st.text_area(
            "Описание риска",
            placeholder=WR2_RISK_REASON_PLACEHOLDER,
            key=wr2_risk_reason_text_key(pid),
            height=80,
        )
        st.text_area(
            "Возможные последствия",
            key=wr2_risk_impact_key(pid),
            height=80,
        )
        st.text_input(
            "Ответственный за устранение",
            key=wr2_risk_responsible_key(pid),
        )
    with r2:
        st.text_input(
            "Срок устранения",
            placeholder="например: 15.07.2026",
            key=wr2_risk_deadline_key(pid),
        )
        st.text_area(
            "Основание принятия риска",
            key=wr2_risk_acceptance_basis_key(pid),
            height=80,
        )
        st.text_area(
            "Комментарий руководителя",
            key=wr2_risk_comment_key(pid),
            height=80,
        )


def wr2_is_auto_clean_admitted(row: pd.Series) -> bool:
    """UI-only: чистый допуск уже в composition."""
    if safe_str(row.get("outcome")) != WR2_OUTCOME_OK:
        return False
    pid = safe_str(row.get("plan_line_id"))
    return pid in st.session_state.get(WR2_SESSION_COMPOSITION, {})


def wr2_has_durable_mgmt_decision(plan_line_id: str) -> bool:
    """True when sid has a saved decision in composition / deferred / excluded."""
    pid = safe_str(plan_line_id)
    if not pid:
        return False
    if pid in st.session_state.get(WR2_SESSION_COMPOSITION, {}):
        return True
    if pid in st.session_state.get(WR2_SESSION_DEFERRED, {}):
        return True
    if pid in st.session_state.get(WR2_SESSION_EXCLUDED, {}):
        return True
    return False


def wr2_apply_button_label(row: pd.Series, live_decision: str) -> str:
    pid = safe_str(row.get("plan_line_id"))
    if not wr2_has_durable_mgmt_decision(pid):
        return "Применить управленческое решение"
    durable = wr2_get_mgmt_decision(row)
    if live_decision != durable:
        return "Пересмотреть решение"
    return "Обновить решение"


def render_war_room_v3_commitment_qty(row: pd.Series, decision: str) -> None:
    pid = safe_str(row.get("plan_line_id"))
    unit = row.get("unit") or row.get("unit_of_measure")
    requested = optional_float(row.get("planned_qty"))
    feasible = wr2_current_feasible_qty(row)
    record = wr2_get_decision_record(pid)
    saved_commitment = optional_float(record.get("approved_commitment_qty")) if record else None
    st.markdown("#### Объём месячного обязательства")
    st.markdown(f"**Исходно запрошено:** {wr2_format_qty_with_unit(requested, unit)}")
    st.markdown(f"**Реально выполнимо:** {wr2_format_qty_with_unit(feasible, unit)}")
    st.markdown(f"**Рекомендуемый объём:** {wr2_format_qty_with_unit(feasible, unit)}")
    if decision in WR2_PASSPORT_DECISIONS:
        st.number_input(
            "Утверждённое обязательство",
            min_value=0.0,
            step=0.001,
            format="%.3f",
            key=wr2_commitment_qty_key(pid),
        )
        live_commitment = optional_float(st.session_state.get(wr2_commitment_qty_key(pid)))
        if live_commitment is not None and live_commitment > 0 and requested is not None:
            remainder = requested - live_commitment
            st.markdown(f"**Остаток:** {wr2_format_qty_with_unit(remainder, unit)}")
        elif saved_commitment is not None and saved_commitment > 0 and requested is not None:
            remainder = requested - saved_commitment
            st.markdown(f"**Остаток:** {wr2_format_qty_with_unit(remainder, unit)}")
        else:
            st.caption("Решение по объёму не принято.")
    else:
        st.caption("Количественное обязательство задаётся только для включения в драфт.")
    if wr2_commitment_status_label(record) == "ОБЪЁМ УТВЕРЖДЁН":
        st.caption("Объём утверждён.")
    else:
        st.caption("Объём обязательства не принят")


def wr2_render_management_decision_form(row: pd.Series) -> None:
    pid = safe_str(row.get("plan_line_id"))
    boq = display_dash(row.get("boq_code"))
    render_war_room_v3_decision_panel(row)
    decision = wr2_get_live_decision(row)
    # Controlled type-change + one-shot hydrate BEFORE widgets bind keys.
    wr2_sync_decision_type_change(pid, decision)
    render_war_room_v3_decision_basis(row, decision)
    if decision == WR2_MGMT_INCLUDE_RISK:
        render_war_room_v3_risk_protocol(row)
    render_war_room_v3_commitment_qty(row, decision)

    apply_label = wr2_apply_button_label(row, decision)
    if st.button(apply_label, key=f"wr2_apply_{wr2_sid(pid)}"):
        apply_decision = wr2_get_live_decision(row)
        errors = wr2_apply_management_decision(
            row,
            apply_decision,
            basis=wr2_get_decision_basis(pid),
            responsible=wr2_get_decision_responsible(pid),
            review_deadline=wr2_get_decision_review_deadline(pid),
            comment=wr2_get_decision_comment(pid),
            risk_description=wr2_get_risk_reason_text(pid),
            risk_impact=wr2_get_risk_impact(pid),
            risk_mitigation_owner=wr2_get_risk_responsible(pid),
            risk_mitigation_deadline=wr2_get_risk_deadline(pid),
            risk_acceptance_basis=wr2_get_risk_acceptance_basis(pid),
            risk_manager_comment=wr2_get_risk_comment(pid),
        )
        if errors:
            for err in errors:
                st.error(err)
        else:
            # Keep previous-type marker aligned with newly saved decision.
            st.session_state[wr2_previous_decision_type_key(pid)] = apply_decision
            st.session_state[wr2_hydrate_marker_key(pid)] = apply_decision
            st.success(f"Решение по {boq} сохранено.")
            st.rerun()


def wr2_build_obligation_table_from_scope(full_scope: pd.DataFrame) -> pd.DataFrame:
    if full_scope.empty:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for _, row in full_scope.iterrows():
        pid = safe_str(row.get("plan_line_id"))
        record = wr2_get_decision_record(pid)
        decision = wr2_get_mgmt_decision(row)
        rows.append(
            {
                "_plan_line_id": pid,
                "BOQ-код": display_dash(row.get("boq_code")),
                "Наименование": display_dash(row.get("boq_name")),
                "Итог допуска": safe_str(row.get("outcome")),
                "Решение": wr2_mgmt_display_label(decision),
                "Стоимость": money_ru(row.get("plan_value_num")),
                "Трудозатраты, чел·ч": wr2_format_hours(safe_num(row.get("labor_hours"))),
                "Основание": safe_str(record.get("basis")) or "—",
            }
        )
    return pd.DataFrame(rows)


def wr2_compute_obligation_labor_kpis(full_scope: pd.DataFrame) -> Dict[str, Any]:
    if full_scope.empty:
        return {
            "planned_qty": 0.0,
            "labor_hours": 0.0,
            "labor_cost": 0.0,
            "crew_size_sum": 0,
            "duration_shifts_sum": 0.0,
        }
    planned_qty = float(full_scope["planned_qty"].apply(safe_num).sum()) if "planned_qty" in full_scope.columns else 0.0
    labor_hours = float(full_scope["labor_hours"].apply(safe_num).sum()) if "labor_hours" in full_scope.columns else 0.0
    labor_cost = float(full_scope["labor_cost"].apply(safe_num).sum()) if "labor_cost" in full_scope.columns else 0.0
    crew_size_sum = 0
    duration_shifts_sum = 0.0
    if "crew_size" in full_scope.columns:
        for _, row in full_scope.iterrows():
            crew = safe_num(row.get("crew_size"))
            hours = safe_num(row.get("labor_hours"))
            if crew > 0:
                crew_size_sum += int(crew)
                duration_shifts_sum += hours / (crew * WR2_PRODUCTIVE_HOURS_PER_PERSON_SHIFT)
    return {
        "planned_qty": planned_qty,
        "labor_hours": labor_hours,
        "labor_cost": labor_cost,
        "crew_size_sum": crew_size_sum,
        "duration_shifts_sum": duration_shifts_sum,
    }


def wr2_format_obligation_qty(value: float) -> str:
    if value <= 0:
        return "—"
    return f"{value:,.3f}".replace(",", " ")


def wr2_format_obligation_duration_sum(value: float) -> str:
    if value <= 0:
        return "—"
    return f"{value:,.1f}".replace(",", " ").replace(".", ",") + " смен"


def wr2_verify_passport_in_storage(
    passport_id: str,
    project_code: str,
    month_key: str,
) -> List[str]:
    """UI-only: проверка записи паспорта в Supabase после формирования."""
    checks: List[str] = []
    pid = safe_str(passport_id)
    if not pid or pid == "—":
        return ["passport_id не создан — проверка БД пропущена."]
    try:
        header_resp = (
            supabase.table("monthly_plan_passports")
            .select(
                "passport_id, project_code, month_key, total_plan_value, "
                "total_required_hours, total_labor_cost, rows_count"
            )
            .eq("passport_id", pid)
            .limit(1)
            .execute()
        )
        header_rows = header_resp.data or []
        if not header_rows:
            return [f"В monthly_plan_passports нет записи passport_id={pid}."]
        header = header_rows[0]
        if safe_str(header.get("project_code")) == project_code:
            checks.append("project_code в шапке паспорта заполнен")
        else:
            checks.append(
                f"project_code в шапке: {display_dash(header.get('project_code'))} "
                f"(ожидался {project_code})"
            )
        if safe_str(header.get("month_key")) == month_key:
            checks.append("month_key в шапке паспорта заполнен")
        else:
            checks.append(
                f"month_key в шапке: {display_dash(header.get('month_key'))} "
                f"(ожидался {month_key})"
            )
        if safe_num(header.get("total_plan_value")) > 0:
            checks.append("total_plan_value заполнен")
        if safe_num(header.get("total_required_hours")) >= 0:
            checks.append("total_required_hours заполнен")
        if safe_num(header.get("total_labor_cost")) >= 0:
            checks.append("total_labor_cost заполнен")

        lines_resp = (
            supabase.table("monthly_plan_passport_lines")
            .select(
                "passport_line_id, admission_status, management_override, override_reason"
            )
            .eq("passport_id", pid)
            .limit(10000)
            .execute()
        )
        line_rows = lines_resp.data or []
        if line_rows:
            checks.append(f"monthly_plan_passport_lines: {len(line_rows)} строк(и)")
            if any(safe_str(r.get("admission_status")) for r in line_rows):
                checks.append("admission_status присутствует в строках")
            override_rows = [r for r in line_rows if r.get("management_override")]
            if override_rows:
                if all(safe_str(r.get("override_reason")) for r in override_rows):
                    checks.append("management_override / override_reason без ошибок")
                else:
                    checks.append(
                        "management_override есть, override_reason заполнен не у всех строк"
                    )
        else:
            checks.append("monthly_plan_passport_lines: строк не найдено")

        view_resp = (
            supabase.table("monthly_plan_passport_dashboard_v1")
            .select("passport_id")
            .eq("passport_id", pid)
            .limit(1)
            .execute()
        )
        if view_resp.data:
            checks.append("monthly_plan_passport_dashboard_v1: данные доступны для Page 12")
        else:
            checks.append("monthly_plan_passport_dashboard_v1: строк не найдено")
    except Exception as exc:  # noqa: BLE001
        return [f"Ошибка проверки Supabase: {exc}"]
    return checks


def render_war_room_v3_management_workspace(
    board_df: pd.DataFrame,
    selected_pid: Optional[str],
) -> None:
    st.markdown("### Рабочая зона управленческого решения")
    if board_df.empty or not selected_pid:
        st.info("Выберите строку в едином реестре кодов месяца.")
        return

    match = board_df[board_df["plan_line_id"].astype(str) == selected_pid]
    if match.empty:
        st.warning("Выбранный код не найден в текущем срезе.")
        return

    row = match.iloc[0]
    pid = safe_str(row.get("plan_line_id"))
    st.session_state[WR2_SESSION_SELECTED] = pid
    # Hydrate runs inside wr2_render_management_decision_form via
    # wr2_sync_decision_type_change (after live radio is known).

    render_war_room_v3_code_card(row)

    if wr2_is_auto_clean_admitted(row):
        st.info(
            "Код включён в драфт месячного обязательства автоматически по чистому допуску."
        )
        with st.expander("Изменить решение вручную", expanded=False):
            wr2_render_management_decision_form(row)
    else:
        wr2_render_management_decision_form(row)


def wr2_final_decision_label_for_row(row: pd.Series) -> str:
    """Итоговое управленческое решение из session baskets (durable + auto-include)."""
    pid = safe_str(row.get("plan_line_id"))
    if not pid:
        return WR2_FINAL_DECISION_PENDING
    deferred = st.session_state.get(WR2_SESSION_DEFERRED, {})
    if pid in deferred:
        return WR2_FINAL_DECISION_DEFERRED
    excluded = st.session_state.get(WR2_SESSION_EXCLUDED, {})
    if pid in excluded:
        return WR2_FINAL_DECISION_EXCLUDED
    comp = st.session_state.get(WR2_SESSION_COMPOSITION, {})
    if pid in comp:
        decision = safe_str(comp[pid].get("decision"))
        if decision == WR2_MGMT_INCLUDE_RISK:
            return WR2_FINAL_DECISION_IN_OBLIGATION_RISK
        return WR2_FINAL_DECISION_IN_OBLIGATION
    return WR2_FINAL_DECISION_PENDING


def wr2_empty_passport_status_index() -> Dict[str, Any]:
    return {
        "scope": "",
        "has_passport": False,
        "passport_id": None,
        "by_line_id": {},
        "by_boq_unique": {},
        "lines_loaded": 0,
        "load_calls": 0,
    }


def wr2_passport_line_status_label(line: Dict[str, Any]) -> str:
    override = bool(line.get("management_override"))
    admission = safe_str(line.get("admission_status")).upper()
    if override or admission == "APPROVED_BY_OVERRIDE":
        return WR2_PASSPORT_STATUS_IN_RISK
    return WR2_PASSPORT_STATUS_IN


def wr2_pick_active_passport_header(headers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not headers:
        return None
    approved = [
        h
        for h in headers
        if safe_str(h.get("passport_status")).upper() == "APPROVED"
    ]
    pool = approved or list(headers)

    def _ts(row: Dict[str, Any]) -> str:
        return safe_str(row.get("updated_at") or row.get("approved_at") or row.get("created_at"))

    return sorted(pool, key=_ts, reverse=True)[0]


def wr2_load_passport_status_index(
    project_code: str,
    month_key: str,
) -> Dict[str, Any]:
    """
    One bulk load of the acting passport lines for concrete project+month.
    Indexed by line_id (= plan_line_id). Unique-boq fallback only when pid absent.
    """
    index = wr2_empty_passport_status_index()
    index["load_calls"] = 1
    if not wr2_is_concrete_mgmt_scope(project_code, month_key):
        return index

    scope = wr2_mgmt_scope_token(project_code, month_key)
    index["scope"] = scope
    try:
        headers_resp = (
            supabase.table("monthly_plan_passports")
            .select(
                "passport_id,passport_status,created_at,updated_at,approved_at,rows_count"
            )
            .eq("project_code", project_code)
            .eq("month_key", month_key)
            .limit(50)
            .execute()
        )
    except Exception:  # noqa: BLE001
        return index

    header = wr2_pick_active_passport_header(list(headers_resp.data or []))
    if not header:
        return index

    passport_id = safe_str(header.get("passport_id"))
    if not passport_id:
        return index

    index["has_passport"] = True
    index["passport_id"] = passport_id
    try:
        lines_resp = (
            supabase.table("monthly_plan_passport_lines")
            .select("line_id,boq_code,admission_status,management_override")
            .eq("passport_id", passport_id)
            .limit(10000)
            .execute()
        )
    except Exception:  # noqa: BLE001
        return index

    lines = list(lines_resp.data or [])
    index["lines_loaded"] = len(lines)
    by_line: Dict[str, str] = {}
    boq_to_statuses: Dict[str, List[str]] = {}
    for line in lines:
        status = wr2_passport_line_status_label(line)
        lid = safe_str(line.get("line_id"))
        if lid:
            by_line[lid] = status
        boq = safe_str(line.get("boq_code"))
        if boq:
            boq_to_statuses.setdefault(boq, []).append(status)
    index["by_line_id"] = by_line
    index["by_boq_unique"] = {
        boq: statuses[0]
        for boq, statuses in boq_to_statuses.items()
        if len(statuses) == 1
    }
    return index


def wr2_store_passport_status_index(index: Dict[str, Any]) -> None:
    st.session_state[WR2_SESSION_PASSPORT_STATUS_INDEX] = index


def wr2_passport_status_index_from_session() -> Dict[str, Any]:
    stored = st.session_state.get(WR2_SESSION_PASSPORT_STATUS_INDEX)
    if isinstance(stored, dict) and "by_line_id" in stored:
        return stored
    return wr2_empty_passport_status_index()


def wr2_passport_status_for_row(
    row: pd.Series,
    index: Optional[Dict[str, Any]] = None,
) -> str:
    """Display-only passport membership label. Never empty."""
    idx = index if index is not None else wr2_passport_status_index_from_session()
    pid = safe_str(row.get("plan_line_id"))
    by_line = idx.get("by_line_id") or {}
    if pid:
        return safe_str(by_line.get(pid)) or WR2_PASSPORT_STATUS_NOT_IN
    # Fallback by boq only when plan_line_id is missing and BOQ is unique in passport.
    boq = safe_str(row.get("boq_code"))
    by_boq = idx.get("by_boq_unique") or {}
    if boq and boq in by_boq:
        return safe_str(by_boq.get(boq)) or WR2_PASSPORT_STATUS_NOT_IN
    return WR2_PASSPORT_STATUS_NOT_IN


def wr2_passport_decision_conflict(
    final_decision: str,
    passport_status: str,
    *,
    has_active_passport: bool,
) -> bool:
    """
    Intent vs snapshot mismatch.
    Legacy: no ACTIVE decision + passport line → NOT a conflict.
    """
    in_passport = passport_status in (
        WR2_PASSPORT_STATUS_IN,
        WR2_PASSPORT_STATUS_IN_RISK,
    )
    if final_decision in (
        WR2_FINAL_DECISION_EXCLUDED,
        WR2_FINAL_DECISION_DEFERRED,
    ) and in_passport:
        return True
    if (
        final_decision
        in (
            WR2_FINAL_DECISION_IN_OBLIGATION,
            WR2_FINAL_DECISION_IN_OBLIGATION_RISK,
        )
        and passport_status == WR2_PASSPORT_STATUS_NOT_IN
        and has_active_passport
    ):
        return True
    return False


def wr2_format_passport_status_display(status: str, *, conflict: bool) -> str:
    label = safe_str(status) or WR2_PASSPORT_STATUS_NOT_IN
    if conflict:
        return f"{WR2_PASSPORT_CONFLICT_MARK} {label}"
    return label


def wr2_strip_passport_conflict_mark(val: Any) -> str:
    text = safe_str(val)
    prefix = f"{WR2_PASSPORT_CONFLICT_MARK} "
    if text.startswith(prefix):
        return text[len(prefix) :].strip()
    return text


def wr2_slice_month_board(
    full_board: pd.DataFrame,
    project_code: str,
    month_key: str,
) -> pd.DataFrame:
    """Project+month slice without war-room display filters."""
    if full_board.empty or not wr2_is_concrete_mgmt_scope(project_code, month_key):
        # Preserve read-model columns (incl. plan_line_id) for empty scope.
        return full_board.head(0).copy()
    return full_board[
        (full_board["project_code"].astype(str) == project_code)
        & (full_board["month_key"].astype(str) == month_key)
    ].copy()


def wr2_month_board_from_session() -> pd.DataFrame:
    board = st.session_state.get(WR2_SESSION_MONTH_BOARD)
    if isinstance(board, pd.DataFrame):
        return board.copy()
    return pd.DataFrame()


def wr2_board_row_lookup(month_board: pd.DataFrame) -> Dict[str, pd.Series]:
    if month_board.empty:
        return {}
    return {
        safe_str(row.get("plan_line_id")): row
        for _, row in month_board.iterrows()
        if safe_str(row.get("plan_line_id"))
    }


def wr2_display_basket_comment(record: Dict[str, Any]) -> str:
    text = wr2_normalize_form_value(record.get("comment"))
    if not text:
        return WR2_BASKET_COMMENT_EMPTY
    return wr2_truncate_display_text(text, WR2_BASKET_COMMENT_DISPLAY_MAX)


def wr2_display_basket_review_deadline(record: Dict[str, Any]) -> str:
    text = wr2_normalize_form_value(record.get("review_deadline"))
    return text if text else WR2_BASKET_DEADLINE_EMPTY


def wr2_truncate_display_text(text: str, max_len: int) -> str:
    clean = safe_str(text)
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rstrip() + "…"


def wr2_plan_value_for_pid(
    plan_line_id: str,
    record: Dict[str, Any],
    board_lookup: Dict[str, pd.Series],
) -> float:
    board_row = board_lookup.get(plan_line_id)
    if board_row is not None:
        return safe_num(board_row.get("plan_value_num"))
    return safe_num(record.get("plan_value"))


def wr2_labor_hours_for_pid(
    plan_line_id: str,
    record: Dict[str, Any],
    board_lookup: Dict[str, pd.Series],
) -> float:
    board_row = board_lookup.get(plan_line_id)
    if board_row is not None:
        if "planned_direct_hours" in board_row.index:
            val = safe_num(board_row.get("planned_direct_hours"))
            if val:
                return val
        return safe_num(board_row.get("labor_hours"))
    return safe_num(record.get("labor_hours"))


def wr2_workers_for_pid(
    plan_line_id: str,
    board_lookup: Dict[str, pd.Series],
) -> float:
    board_row = board_lookup.get(plan_line_id)
    if board_row is None:
        return 0.0
    if "planned_workers" in board_row.index:
        return safe_num(board_row.get("planned_workers"))
    if "crew_size" in board_row.index:
        return safe_num(board_row.get("crew_size"))
    return 0.0


def wr2_compute_basket_metrics(
    records: Dict[str, Dict[str, Any]],
    board_lookup: Dict[str, pd.Series],
) -> Dict[str, Any]:
    """Unique plan_line_id aggregates for one basket."""
    count = 0
    cost = 0.0
    labor = 0.0
    workers = 0.0
    seen: set[str] = set()
    for pid in records:
        if not pid or pid in seen:
            continue
        seen.add(pid)
        count += 1
        item = records[pid]
        cost += wr2_plan_value_for_pid(pid, item, board_lookup)
        labor += wr2_labor_hours_for_pid(pid, item, board_lookup)
        workers += wr2_workers_for_pid(pid, board_lookup)
    return {
        "count": count,
        "cost": cost,
        "labor_hours": labor,
        "workers": workers,
    }


def wr2_build_basket_table(
    records: Dict[str, Dict[str, Any]],
    board_lookup: Dict[str, pd.Series],
    *,
    include_risk_columns: bool = False,
) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    rows: List[Dict[str, Any]] = []
    for pid, item in records.items():
        board_row = board_lookup.get(pid)
        title = "—"
        discipline = "—"
        if board_row is not None:
            title = display_dash(
                board_row.get("title_display") or board_row.get("facility")
            )
            discipline = display_dash(
                board_row.get("discipline")
                or board_row.get("construction_discipline")
            )
        row_dict: Dict[str, Any] = {
            "_plan_line_id": pid,
            "BOQ-код": display_dash(item.get("boq_code")),
            "Наименование": display_dash(item.get("boq_name")),
            "Титул": title,
            "Дисциплина": discipline,
            "Стоимость": money_ru(
                wr2_plan_value_for_pid(pid, item, board_lookup)
            ),
            "Ответственный": display_dash(
                wr2_normalize_form_value(item.get("responsible")) or "—"
            ),
            "Срок пересмотра": wr2_display_basket_review_deadline(item),
            "Комментарий": wr2_display_basket_comment(item),
        }
        if include_risk_columns:
            row_dict["Описание риска"] = display_dash(item.get("risk_description"))
            row_dict["Последствия"] = display_dash(item.get("risk_impact"))
            row_dict["Основание принятия риска"] = display_dash(
                item.get("risk_acceptance_basis")
            )
            row_dict["Ответственный за устранение"] = display_dash(
                item.get("risk_mitigation_owner")
            )
        rows.append(row_dict)
    return pd.DataFrame(rows)


WR2_PRE_R16_OBLIGATION_COLUMNS = (
    "BOQ-код",
    "Наименование",
    "Титул",
    "Дисциплина",
    "Стоимость",
    "Ответственный",
    "Срок пересмотра",
    "Комментарий",
)

WR2_R16_OBLIGATION_COLUMNS = (
    "Исходно запрошено",
    "Реально выполнимо",
    "Утверждённое обязательство",
    "Остаток",
    "Стоимость утверждённых работ",
    "Трудозатраты обязательства",
    "Стоимость труда",
    "Статус объёма",
)


def wr2_passport_line_ids_from_session() -> set:
    """Read-only plan_line_id set already in the acting passport. No DB write."""
    index = wr2_passport_status_index_from_session()
    by_line = index.get("by_line_id") or {}
    return {safe_str(pid) for pid in by_line.keys() if safe_str(pid)}


def wr2_filter_draft_only_records(
    records: Dict[str, Dict[str, Any]],
    passport_line_ids: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Working draft = INCLUDE/INCLUDE_RISK records whose plan_line_id
    is not already in monthly_plan_passport_lines.
    Does not mutate the source dict and does not cancel decisions.
    """
    ids = {safe_str(pid) for pid in (passport_line_ids or []) if safe_str(pid)}
    if not ids:
        return dict(records)
    return {
        pid: item
        for pid, item in records.items()
        if pid and pid not in ids
    }


def wr2_build_draft_summary_and_tables(
    month_board: pd.DataFrame,
    *,
    composition: Dict[str, Dict[str, Any]],
    deferred: Dict[str, Dict[str, Any]],
    excluded: Dict[str, Dict[str, Any]],
    passport_line_ids: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build four basket tables + per-basket KPIs from session state (no extra DB)."""
    board_lookup = wr2_board_row_lookup(month_board)
    draft_composition = wr2_filter_draft_only_records(
        composition, passport_line_ids
    )
    risk_records = {
        pid: item
        for pid, item in draft_composition.items()
        if item.get("decision") == WR2_MGMT_INCLUDE_RISK
    }
    tables = {
        "obligation": wr2_build_obligation_qty_table(
            draft_composition, board_lookup
        ),
        "risk": wr2_build_basket_table(
            risk_records, board_lookup, include_risk_columns=True
        ),
        "deferred": wr2_build_basket_table(deferred, board_lookup),
        "excluded": wr2_build_basket_table(excluded, board_lookup),
    }
    summary = {
        "obligation": wr2_compute_basket_metrics(draft_composition, board_lookup),
        "risk": wr2_compute_basket_metrics(risk_records, board_lookup),
        "deferred": wr2_compute_basket_metrics(deferred, board_lookup),
        "excluded": wr2_compute_basket_metrics(excluded, board_lookup),
    }
    return {
        "tables": tables,
        "summary": summary,
        "board_lookup": board_lookup,
        "draft_composition": draft_composition,
    }


def wr2_uncommitted_qty_display(requested: Any, commitment: Any) -> str:
    req = optional_float(requested)
    cmt = optional_float(commitment)
    if cmt is None or cmt <= 0:
        return "Решение по объёму не принято"
    if req is None:
        return "—"
    return f"{(req - cmt):,.3f}".replace(",", " ").rstrip("0").rstrip(".")


def wr2_build_obligation_qty_table(
    records: Dict[str, Dict[str, Any]],
    board_lookup: Dict[str, pd.Series],
) -> pd.DataFrame:
    """PRE-R1.6 basket columns plus additive R1.6 commitment columns."""
    base = wr2_build_basket_table(records, board_lookup)
    if base.empty:
        return base
    qty_by_pid: Dict[str, Dict[str, str]] = {}
    for pid, item in records.items():
        board_row = board_lookup.get(pid)
        unit = ""
        requested = optional_float(item.get("requested_qty_snapshot"))
        if board_row is not None:
            unit = safe_str(board_row.get("unit") or board_row.get("unit_of_measure"))
            if requested is None:
                requested = optional_float(board_row.get("planned_qty"))
        feasible = optional_float(item.get("feasible_qty_snapshot"))
        if feasible is None and board_row is not None:
            feasible = wr2_current_feasible_qty(board_row)
        commitment = optional_float(item.get("approved_commitment_qty"))
        qty_by_pid[pid] = {
            "Исходно запрошено": wr2_format_qty_with_unit(requested, unit),
            "Реально выполнимо": wr2_format_qty_with_unit(feasible, unit),
            "Утверждённое обязательство": (
                wr2_format_qty_with_unit(commitment, unit)
                if commitment is not None and commitment > 0
                else "—"
            ),
            "Остаток": wr2_uncommitted_qty_display(requested, commitment),
            "Стоимость утверждённых работ": (
                money_ru(item.get("committed_work_value"))
                if optional_float(item.get("committed_work_value")) is not None
                else "—"
            ),
            "Трудозатраты обязательства": (
                wr2_format_hours(float(item.get("committed_required_hours") or 0))
                if optional_float(item.get("committed_required_hours")) is not None
                else "—"
            ),
            "Стоимость труда": (
                money_ru(item.get("committed_labor_cost"))
                if optional_float(item.get("committed_labor_cost")) is not None
                else "—"
            ),
            "Статус объёма": wr2_commitment_status_label(item),
        }
    out = base.copy()
    for col in WR2_R16_OBLIGATION_COLUMNS:
        out[col] = [
            qty_by_pid.get(safe_str(pid), {}).get(col, "—")
            for pid in out["_plan_line_id"].astype(str)
        ]
    return out


def wr2_compute_commitment_kpis(
    records: Dict[str, Dict[str, Any]],
    board_lookup: Dict[str, pd.Series],
) -> Dict[str, Any]:
    draft_count = 0
    with_qty = 0
    without_qty = 0
    work_value = 0.0
    hours = 0.0
    labor_cost = 0.0
    crews: set[str] = set()
    for pid, item in records.items():
        if not pid:
            continue
        draft_count += 1
        commitment = optional_float(item.get("approved_commitment_qty"))
        if commitment is None or commitment <= 0:
            without_qty += 1
            continue
        with_qty += 1
        work_value += optional_float(item.get("committed_work_value")) or 0.0
        hours += optional_float(item.get("committed_required_hours")) or 0.0
        labor_cost += optional_float(item.get("committed_labor_cost")) or 0.0
        board_row = board_lookup.get(pid)
        crew = wr2_plan_crew(board_row.to_dict()) if board_row is not None else ""
        if crew:
            crews.add(crew)
    return {
        "draft_count": draft_count,
        "with_qty": with_qty,
        "without_qty": without_qty,
        "committed_work_value": work_value,
        "committed_required_hours": hours,
        "committed_labor_cost": labor_cost,
        "crew_count": len(crews),
    }


def wr2_render_draft_basket_summary(
    label: str,
    metrics: Dict[str, Any],
    *,
    show_workers: bool,
) -> None:
    st.markdown(f"**{label}**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Кодов", metrics.get("count", 0))
    c2.metric("Стоимость", money_ru_compact(metrics.get("cost", 0)))
    c3.metric("Чел·ч", wr2_format_hours(metrics.get("labor_hours", 0)))
    if show_workers:
        workers = metrics.get("workers", 0)
        if workers > 0:
            st.caption(f"Рабочие: {int(workers) if workers == int(workers) else workers}")


def wr2_render_basket_dataframe(table: pd.DataFrame) -> None:
    if table.empty:
        st.info("Нет кодов в этой группе.")
        return
    st.dataframe(
        table.drop(columns=["_plan_line_id"], errors="ignore"),
        use_container_width=True,
        hide_index=True,
    )


def wr2_render_basket_with_review(
    table: pd.DataFrame,
    *,
    basket_key: str,
) -> None:
    """Deferred / Excluded: select row → open existing decision form above."""
    wr2_render_basket_dataframe(table)
    if table.empty:
        return
    options: List[Tuple[str, str]] = []
    for _, row in table.iterrows():
        pid = safe_str(row.get("_plan_line_id"))
        boq = safe_str(row.get("BOQ-код"))
        if pid:
            options.append((pid, boq or pid))
    if not options:
        return
    labels = [f"{boq}" for _, boq in options]
    idx = st.selectbox(
        "Выберите код для пересмотра",
        range(len(options)),
        format_func=lambda i: labels[i],
        key=f"wr2_review_select_{basket_key}",
    )
    if st.button(
        "Пересмотреть решение",
        key=f"wr2_review_btn_{basket_key}",
    ):
        st.session_state[WR2_SESSION_SELECTED] = options[idx][0]
        st.rerun()


def wr2_records_to_table(
    records: Dict[str, Dict[str, Any]],
    board_df: pd.DataFrame,
) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    board_by_id = {
        safe_str(r.get("plan_line_id")): r for _, r in board_df.iterrows()
    }
    rows: List[Dict[str, Any]] = []
    for pid, item in records.items():
        board_row = board_by_id.get(pid)
        rows.append(
            {
                "_plan_line_id": pid,
                "BOQ-код": display_dash(item.get("boq_code")),
                "Наименование": display_dash(item.get("boq_name")),
                "Стоимость": money_ru(
                    item.get("plan_value")
                    or (board_row.get("plan_value_num") if board_row is not None else 0)
                ),
                "Основание": safe_str(item.get("basis")) or "—",
            }
        )
    return pd.DataFrame(rows)


def render_war_room_v3_passport_basket(board_df: pd.DataFrame) -> None:
    st.markdown("### Состав паспорта месяца")
    st.caption(
        "Будущий состав паспорта по управленческим решениям. "
        "Чисто допущенные коды включаются автоматически."
    )
    comp = st.session_state.get(WR2_SESSION_COMPOSITION, {})
    deferred = st.session_state.get(WR2_SESSION_DEFERRED, {})
    excluded = st.session_state.get(WR2_SESSION_EXCLUDED, {})

    included = {pid: item for pid, item in comp.items() if item.get("decision") == WR2_MGMT_INCLUDE}
    risk = {pid: item for pid, item in comp.items() if item.get("decision") == WR2_MGMT_INCLUDE_RISK}

    tabs = st.tabs(
        [
            "Допущено",
            "Допущено с риском",
            "Отложено",
            "Исключено",
        ]
    )
    groups = [
        (tabs[0], included, True),
        (tabs[1], risk, True),
        (tabs[2], deferred, False),
        (tabs[3], excluded, False),
    ]
    for tab, records, removable in groups:
        with tab:
            table = wr2_records_to_table(records, board_df)
            count = len(records)
            total_value = sum(safe_num(item.get("plan_value")) for item in records.values())
            st.caption(f"Кодов: {count} · Сумма: {money_ru(total_value)}")
            if table.empty:
                st.info("Нет кодов в этой группе.")
            else:
                st.dataframe(
                    table.drop(columns=["_plan_line_id"], errors="ignore"),
                    use_container_width=True,
                    hide_index=True,
                )
            if removable and not table.empty:
                st.markdown("**Убрать из паспорта**")
                for _, comp_row in table.iterrows():
                    pid = safe_str(comp_row.get("_plan_line_id"))
                    boq = display_dash(comp_row.get("BOQ-код"))
                    match = board_df[board_df["plan_line_id"].astype(str) == pid]
                    outcome = safe_str(match.iloc[0].get("outcome")) if not match.empty else "—"
                    formed = bool(st.session_state.get(WR2_SESSION_FORMED))
                    label = (
                        f"Убрать {boq} (аудит: исключение из сформированного паспорта)"
                        if formed
                        else f"Убрать {boq} из черновика"
                    )
                    if st.button(label, key=f"wr2_remove_passport_{wr2_sid(pid)}"):
                        remove_errors = wr2_remove_from_passport(pid, boq, outcome)
                        if remove_errors:
                            for err in remove_errors:
                                st.error(err)
                        else:
                            st.rerun()


def wr2_compute_readiness(
    project_sel: str,
    month_sel: str,
    scoped_board: pd.DataFrame,
) -> Dict[str, Any]:
    clean_scope = wr2_passport_scope_rows(scoped_board, allow_risk=False)
    full_scope = wr2_passport_scope_rows(scoped_board, allow_risk=True)
    validation_clean = wr2_validate_management_decisions(clean_scope, allow_risk=False)
    validation_full = wr2_validate_management_decisions(full_scope, allow_risk=True)
    all_errors = validation_clean + validation_full

    include_cnt = 0
    risk_cnt = 0
    if not full_scope.empty:
        for _, scope_row in full_scope.iterrows():
            decision = wr2_get_mgmt_decision(scope_row)
            if decision == WR2_MGMT_INCLUDE:
                include_cnt += 1
            elif decision == WR2_MGMT_INCLUDE_RISK:
                risk_cnt += 1

    blocked_outside = 0
    if not scoped_board.empty:
        for _, scope_row in scoped_board.iterrows():
            if safe_str(scope_row.get("outcome")) != WR2_OUTCOME_BLOCKED:
                continue
            if not wr2_row_in_passport_inclusion(scope_row, allow_risk=True):
                blocked_outside += 1

    value_passport = float(full_scope["plan_value_num"].sum()) if not full_scope.empty else 0.0
    value_risk = 0.0
    if not full_scope.empty:
        for _, scope_row in full_scope.iterrows():
            if wr2_get_mgmt_decision(scope_row) == WR2_MGMT_INCLUDE_RISK:
                value_risk += safe_num(scope_row.get("plan_value_num"))

    checks = [
        ("Выбран конкретный проект и месяц", project_sel != "Все" and month_sel != "Все"),
        ("Есть состав паспорта", not full_scope.empty),
        (
            "Все рискованные включения имеют протокол риска",
            risk_cnt == 0 or len(validation_full) == 0,
        ),
        ("Нет ошибок валидации", len(all_errors) == 0),
    ]
    ready = all(ok for _, ok in checks) and not full_scope.empty

    return {
        "ready": ready,
        "errors": all_errors,
        "metrics": {
            "total": len(scoped_board),
            "in_passport_clean": include_cnt,
            "in_passport_risk": risk_cnt,
            "blocked_outside": blocked_outside,
            "value_passport": value_passport,
            "value_risk": value_risk,
            "critical": blocked_outside,
        },
        "checks": checks,
        "can_clean": not validation_clean and not clean_scope.empty,
        "can_full": not validation_full and not full_scope.empty,
        "clean_scope": clean_scope,
        "full_scope": full_scope,
    }


def render_war_room_v3_passport_readiness(
    project_sel: str,
    month_sel: str,
    board_df: pd.DataFrame,
) -> Dict[str, Any]:
    st.markdown("### Проверка готовности паспорта")
    if project_sel == "Все" or month_sel == "Все":
        st.warning("Выберите конкретный проект и месяц для проверки готовности.")
        return {
            "ready": False,
            "errors": [],
            "checks": [],
            "can_clean": False,
            "can_full": False,
            "clean_scope": pd.DataFrame(),
            "full_scope": pd.DataFrame(),
        }

    scoped_board = board_df[
        (board_df["project_code"].astype(str) == project_sel)
        & (board_df["month_key"].astype(str) == month_sel)
    ].copy()
    if scoped_board.empty:
        st.warning("Нет кодов для выбранного проекта и месяца.")
        return {
            "ready": False,
            "errors": [],
            "checks": [],
            "can_clean": False,
            "can_full": False,
            "clean_scope": pd.DataFrame(),
            "full_scope": pd.DataFrame(),
        }

    readiness = wr2_compute_readiness(project_sel, month_sel, scoped_board)
    metrics = readiness["metrics"]
    c1, c2, c3, c4 = st.columns(4)
    c5, c6, c7, c8 = st.columns(4)
    c1.metric("Всего кодов", metrics["total"])
    c2.metric("Допущено в паспорт", metrics["in_passport_clean"])
    c3.metric("Под риском", metrics["in_passport_risk"])
    c4.metric("Заблокировано вне паспорта", metrics["blocked_outside"])
    c5.metric("Стоимость паспорта", money_ru_compact(metrics["value_passport"]))
    c6.metric("Стоимость под риском", money_ru_compact(metrics["value_risk"]))
    c7.metric("Критические ограничения", metrics["critical"])
    c8.metric("Готовность", "Готово" if readiness["ready"] else "Требует внимания")

    for label, ok in readiness["checks"]:
        if ok:
            st.success(f"✓ {label}")
        else:
            st.warning(f"✗ {label}")

    for err in readiness["errors"]:
        st.error(err)

    return readiness


def render_war_room_v3_obligation_draft(
    project_sel: str,
    month_sel: str,
    board_df: pd.DataFrame,
) -> None:
    st.markdown("### Драфт месячного обязательства")
    st.caption(
        "Состав месячного обязательства по управленческим решениям. "
        "Чисто допущенные коды включаются автоматически. "
        "Корзины и формирование паспорта — по полному scope проекта и месяца, "
        "независимо от фильтров реестра."
    )
    wr2_init_passport_session()

    deferred = st.session_state.get(WR2_SESSION_DEFERRED, {})
    excluded = st.session_state.get(WR2_SESSION_EXCLUDED, {})
    comp = st.session_state.get(WR2_SESSION_COMPOSITION, {})

    scope_ready = project_sel != "Все" and month_sel != "Все"
    month_board = wr2_month_board_from_session()
    if not scope_ready:
        st.warning(
            "Выберите конкретный проект и месяц для формирования месячного обязательства."
        )
        readiness = wr2_compute_readiness(project_sel, month_sel, month_board)
    elif month_board.empty:
        st.warning("Нет кодов для выбранного проекта и месяца.")
        return
    else:
        readiness = wr2_compute_readiness(project_sel, month_sel, month_board)

    draft = wr2_build_draft_summary_and_tables(
        month_board,
        composition=comp,
        deferred=deferred,
        excluded=excluded,
        passport_line_ids=wr2_passport_line_ids_from_session(),
    )
    tables = draft["tables"]
    summary = draft["summary"]
    board_lookup = draft["board_lookup"]
    draft_composition = draft.get("draft_composition") or {}
    commitment_kpis = wr2_compute_commitment_kpis(draft_composition, board_lookup)
    full_scope = readiness.get("full_scope", pd.DataFrame())
    clean_scope = readiness.get("clean_scope", pd.DataFrame())
    can_full = bool(readiness.get("can_full"))
    can_clean = bool(readiness.get("can_clean"))
    ready_status = "Готово" if readiness.get("ready") else "Требует внимания"
    show_workers = any(summary[key].get("workers", 0) > 0 for key in summary)
    obligation_table = tables["obligation"]

    if st.session_state.get(WR2_SESSION_FORMED):
        st.warning("Паспорт уже сформирован. Исключение кодов создаёт аудит-след.")

    st.metric("Готовность к формированию", ready_status)
    for err in readiness.get("errors", []):
        st.error(err)

    st.markdown("#### Количественное обязательство")
    k1, k2, k3 = st.columns(3)
    k1.metric("Кодов в драфте", commitment_kpis.get("draft_count", 0))
    k2.metric("Кодов с утверждённым объёмом", commitment_kpis.get("with_qty", 0))
    k3.metric("Кодов без принятого объёма", commitment_kpis.get("without_qty", 0))
    k4, k5, k6, k7 = st.columns(4)
    k4.metric(
        "Стоимость утверждённых работ",
        money_ru_compact(commitment_kpis.get("committed_work_value", 0)),
    )
    k5.metric(
        "Трудозатраты по обязательству, чел·ч",
        wr2_format_hours(commitment_kpis.get("committed_required_hours", 0)),
    )
    k6.metric(
        "Стоимость труда",
        money_ru_compact(commitment_kpis.get("committed_labor_cost", 0)),
    )
    k7.metric("Количество задействованных звеньев", commitment_kpis.get("crew_count", 0))

    st.markdown("#### Сводка по корзинам")
    s1, s2 = st.columns(2)
    with s1:
        wr2_render_draft_basket_summary(
            "Проект месячного обязательства",
            summary["obligation"],
            show_workers=show_workers,
        )
        wr2_render_draft_basket_summary(
            "Отложено",
            summary["deferred"],
            show_workers=show_workers,
        )
    with s2:
        wr2_render_draft_basket_summary(
            "Включено с риском",
            summary["risk"],
            show_workers=show_workers,
        )
        st.caption(
            "Коды с риском входят в проект обязательства; стоимость риска "
            "показана отдельно и не суммируется повторно."
        )
        wr2_render_draft_basket_summary(
            "Исключено",
            summary["excluded"],
            show_workers=show_workers,
        )

    st.markdown("#### Корзины решений")
    row1a, row1b = st.columns(2)
    with row1a:
        st.markdown(
            f"**Проект месячного обязательства ({summary['obligation']['count']})**"
        )
        wr2_render_basket_dataframe(tables["obligation"])
    with row1b:
        st.markdown(f"**Включено с риском ({summary['risk']['count']})**")
        wr2_render_basket_dataframe(tables["risk"])

    row2a, row2b = st.columns(2)
    with row2a:
        st.markdown(f"**Отложено ({summary['deferred']['count']})**")
        wr2_render_basket_with_review(tables["deferred"], basket_key="deferred")
    with row2b:
        st.markdown(f"**Исключено ({summary['excluded']['count']})**")
        wr2_render_basket_with_review(tables["excluded"], basket_key="excluded")

    created_by = st.text_input(
        "Кто утверждает",
        value="Пользователь Streamlit",
        key="passport_created_by",
    )

    if st.button(
        "Сформировать месячное обязательство",
        key="wr2_form_monthly_obligation_btn",
        disabled=not (scope_ready and can_full),
        type="primary",
    ):
        summary_result = wr2_create_monthly_passport_with_overrides(
            project_code=project_sel,
            month_key=month_sel,
            created_by=created_by.strip() or "Пользователь Streamlit",
            board_df=full_scope,
            allow_risk=True,
        )
        _render_passport_summary(
            summary_result,
            formed_risk=True,
            project_code=project_sel,
            month_key=month_sel,
        )

    with st.expander("Дополнительные действия / аудит", expanded=False):
        if not obligation_table.empty:
            st.markdown("**Убрать код из обязательства**")
            for _, comp_row in obligation_table.iterrows():
                pid = safe_str(comp_row.get("_plan_line_id"))
                boq = display_dash(comp_row.get("BOQ-код"))
                if month_board.empty or "plan_line_id" not in month_board.columns:
                    outcome = "—"
                else:
                    match = month_board[
                        month_board["plan_line_id"].astype(str) == pid
                    ]
                    outcome = (
                        safe_str(match.iloc[0].get("outcome"))
                        if not match.empty
                        else "—"
                    )
                formed = bool(st.session_state.get(WR2_SESSION_FORMED))
                label = (
                    f"Убрать {boq} (аудит: исключение из сформированного паспорта)"
                    if formed
                    else f"Убрать {boq} из драфта"
                )
                if st.button(label, key=f"wr2_remove_obligation_{wr2_sid(pid)}"):
                    remove_errors = wr2_remove_from_passport(pid, boq, outcome)
                    if remove_errors:
                        for err in remove_errors:
                            st.error(err)
                    else:
                        st.rerun()

        clear_disabled = not scope_ready
        clear_confirm = st.checkbox(
            "Подтверждаю отмену всех ACTIVE управленческих решений "
            "для выбранного проекта и месяца",
            key="wr2_clear_obligation_confirm",
            disabled=clear_disabled,
        )
        if clear_disabled:
            st.caption(
                "«Очистить состав» доступно только при выбранных "
                "конкретных проекте и месяце."
            )
        if st.button(
            "Очистить состав",
            key="wr2_clear_obligation_btn",
            disabled=clear_disabled or not clear_confirm,
        ):
            clear_errors = wr2_cancel_all_active_scope_decisions(
                project_sel,
                month_sel,
                created_by.strip(),
            )
            if clear_errors:
                for err in clear_errors:
                    st.error(err)
            else:
                wr2_clear_session_decision_caches()
                st.session_state[WR2_SESSION_DRAFT] = False
                st.session_state[WR2_SESSION_FORMED] = False
                st.session_state[WR2_SESSION_MGMT_REHYDRATED_COUNT] = 0
                wr2_append_audit(
                    {
                        "datetime": datetime.now(timezone.utc).isoformat(),
                        "boq_code": "—",
                        "plan_line_id": "—",
                        "old_outcome": "—",
                        "decision": "CLEAR",
                        "override": False,
                        "basis": "Очищен состав паспорта (cancel ACTIVE scope)",
                        "responsible": created_by,
                        "comment": "—",
                        "persisted": True,
                    }
                )
                st.success("Состав обязательства очищен (решения отменены в Supabase).")
                st.rerun()

        st.markdown("**Расширенные опции**")
        st.caption(
            "Сформировать паспорт только из чисто допущенных кодов (без рисковых включений)."
        )
        if st.button(
            "Сформировать паспорт месяца (без рисков)",
            key="create_monthly_passport_btn",
            disabled=not (scope_ready and can_clean),
        ):
            summary_clean = wr2_create_monthly_passport_with_overrides(
                project_code=project_sel,
                month_key=month_sel,
                created_by=created_by.strip() or "Пользователь Streamlit",
                board_df=clean_scope,
                allow_risk=False,
            )
            _render_passport_summary(summary_clean, formed_risk=False)

        audit = st.session_state.get(WR2_SESSION_AUDIT, [])
        if audit:
            st.markdown(f"**Аудит управленческих решений ({len(audit)})**")
            st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)


def render_war_room_v3(
    constraints_df: pd.DataFrame,
    v2_df: pd.DataFrame,
    queue_df: pd.DataFrame,
) -> None:
    with stage("build war room read model"):
        full_board = build_war_room_read_model(constraints_df, v2_df, queue_df)
    if full_board.empty:
        st.info(
            "Нет кодов для управленческих решений. Отправьте план из конструктора "
            "в допуск или сформируйте проверки в контуре допуска."
        )
        return

    wr2_init_passport_session()
    with stage("filters + apply filters"):
        filters = render_war_room_v3_filters(full_board, constraints_df, v2_df)
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
        wr2_rehydrate_management_decisions(filters["project"], filters["month"])
        month_board = wr2_slice_month_board(
            full_board, filters["project"], filters["month"]
        )
        st.session_state[WR2_SESSION_MONTH_BOARD] = month_board
        wr2_sync_auto_admitted_composition(month_board)
        wr2_store_passport_status_index(
            wr2_load_passport_status_index(filters["project"], filters["month"])
        )
        st.session_state["wr2_passport_board_df"] = board_df.copy()

    with stage("render summary + registry"):
        wr2_render_saved_decisions_indicator(filters["project"], filters["month"])
        render_war_room_v3_summary(board_df)
        selected_pid = render_war_room_v3_unified_registry(board_df, constraints_df)
    st.markdown("---")
    with stage("render management workspace"):
        render_war_room_v3_management_workspace(board_df, selected_pid)
    st.markdown("---")
    with stage("render obligation draft"):
        render_war_room_v3_obligation_draft(
            filters["project"],
            filters["month"],
            board_df,
        )


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
        if outcome == ADMISSION_BLOCKED:
            text = constraint_decision_line_compact(row, dept_ui)
        else:
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
    if text in WR2_FINAL_DECISION_BG:
        return WR2_FINAL_DECISION_BG[text]
    base = wr2_strip_passport_conflict_mark(text)
    if base in WR2_PASSPORT_STATUS_BG:
        return WR2_PASSPORT_STATUS_BG[base]
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


def wr2_passport_scope_rows(
    board_df: pd.DataFrame,
    *,
    allow_risk: bool = True,
) -> pd.DataFrame:
    rows: List[pd.Series] = []
    for _, row in board_df.iterrows():
        pid = safe_str(row.get("plan_line_id"))
        if pid not in st.session_state.get(WR2_SESSION_COMPOSITION, {}):
            continue
        if wr2_row_in_passport_inclusion(row, allow_risk=allow_risk):
            rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def render_war_room_v3_passport_formation(
    project_sel: str,
    month_sel: str,
    board_df: Optional[pd.DataFrame] = None,
    readiness: Optional[Dict[str, Any]] = None,
) -> None:
    st.markdown("### Сформировать паспорт месяца")
    st.caption(
        "Официальное формирование паспорта из управленчески утверждённого состава. "
        "Итог допуска отделов при этом не меняется."
    )
    wr2_init_passport_session()

    if project_sel == "Все" or month_sel == "Все":
        st.warning("Выберите конкретный проект и месяц для формирования паспорта.")
        return

    scoped_board = board_df
    if scoped_board is None:
        scoped_board = st.session_state.get("wr2_passport_board_df")
    if scoped_board is None or scoped_board.empty:
        st.warning("Нет данных для формирования паспорта по выбранным фильтрам.")
        return

    scoped_board = scoped_board[
        (scoped_board["project_code"].astype(str) == project_sel)
        & (scoped_board["month_key"].astype(str) == month_sel)
    ].copy()
    if scoped_board.empty:
        st.warning(
            f"Нет кодов для проекта {project_sel} и месяца {month_sel} по текущим фильтрам."
        )
        return

    if readiness:
        clean_scope = readiness.get("clean_scope", pd.DataFrame())
        full_scope = readiness.get("full_scope", pd.DataFrame())
        can_clean = bool(readiness.get("can_clean"))
        can_full = bool(readiness.get("can_full"))
    else:
        clean_scope = wr2_passport_scope_rows(scoped_board, allow_risk=False)
        full_scope = wr2_passport_scope_rows(scoped_board, allow_risk=True)
        validation_clean = wr2_validate_management_decisions(clean_scope, allow_risk=False)
        validation_full = wr2_validate_management_decisions(full_scope, allow_risk=True)
        can_clean = not validation_clean and not clean_scope.empty
        can_full = not validation_full and not full_scope.empty

    st.caption(
        f"В составе паспорта: {len(full_scope)} код(ов) "
        f"(чистых: {len(clean_scope)}, с риском: {len(full_scope) - len(clean_scope)})."
    )
    if st.session_state.get(WR2_SESSION_DRAFT):
        st.info("Черновик состава паспорта сохранён.")
    if st.session_state.get(WR2_SESSION_FORMED):
        st.warning("Паспорт уже сформирован. Исключение кодов создаёт аудит-след.")

    created_by = st.text_input(
        "Кто утверждает",
        value="Пользователь Streamlit",
        key="passport_created_by",
    )

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Сохранить черновик паспорта", key="wr2_save_passport_draft"):
        st.session_state[WR2_SESSION_DRAFT] = True
        st.session_state[WR2_SESSION_FORMED] = False
        wr2_append_audit(
            {
                "datetime": datetime.now(timezone.utc).isoformat(),
                "boq_code": "—",
                "plan_line_id": "—",
                "old_outcome": "—",
                "decision": "SAVE_DRAFT",
                "override": False,
                "basis": f"Черновик: {len(full_scope)} код(ов)",
                "responsible": created_by,
                "comment": f"{project_sel} / {month_sel}",
            }
        )
        st.success("Черновик состава паспорта сохранён.")
    if b4.button("Очистить состав паспорта", key="wr2_clear_passport"):
        st.session_state[WR2_SESSION_COMPOSITION] = {}
        st.session_state[WR2_SESSION_DEFERRED] = {}
        st.session_state[WR2_SESSION_EXCLUDED] = {}
        st.session_state[WR2_SESSION_DRAFT] = False
        st.session_state[WR2_SESSION_FORMED] = False
        wr2_append_audit(
            {
                "datetime": datetime.now(timezone.utc).isoformat(),
                "boq_code": "—",
                "plan_line_id": "—",
                "old_outcome": "—",
                "decision": "CLEAR",
                "override": False,
                "basis": "Очищен состав паспорта",
                "responsible": created_by,
                "comment": "—",
            }
        )
        st.success("Состав паспорта очищен.")
        st.rerun()

    if b2.button(
        "Сформировать паспорт месяца",
        key="create_monthly_passport_btn",
        disabled=not can_clean,
    ):
        summary = wr2_create_monthly_passport_with_overrides(
            project_code=project_sel,
            month_key=month_sel,
            created_by=created_by.strip() or "Пользователь Streamlit",
            board_df=clean_scope,
            allow_risk=False,
        )
        _render_passport_summary(summary, formed_risk=False)

    if b3.button(
        "Сформировать паспорт с рисками",
        key="create_monthly_passport_risk_btn",
        disabled=not can_full,
    ):
        summary = wr2_create_monthly_passport_with_overrides(
            project_code=project_sel,
            month_key=month_sel,
            created_by=created_by.strip() or "Пользователь Streamlit",
            board_df=full_scope,
            allow_risk=True,
        )
        _render_passport_summary(summary, formed_risk=True)

    audit = st.session_state.get(WR2_SESSION_AUDIT, [])
    if audit:
        with st.expander(f"Аудит управленческих решений ({len(audit)})", expanded=False):
            st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)


def render_passport_formation(
    project_sel: str,
    month_sel: str,
    board_df: Optional[pd.DataFrame] = None,
) -> None:
    st.markdown("### Формирование паспорта месяца")
    st.info(
        "Паспорт формируется **только** из управленчески выбранных кодов (блок «Состав паспорта»). "
        "Итог допуска отделов (Page 21) при этом не меняется."
    )
    wr2_init_passport_session()

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

    clean_scope = wr2_passport_scope_rows(scoped_board, allow_risk=False)
    full_scope = wr2_passport_scope_rows(scoped_board, allow_risk=True)
    st.caption(
        f"В составе паспорта: {len(full_scope)} код(ов) "
        f"(чистых: {len(clean_scope)}, с риском: {len(full_scope) - len(clean_scope)})."
    )
    if st.session_state.get(WR2_SESSION_DRAFT):
        st.info("Черновик состава паспорта сохранён в session.")
    if st.session_state.get(WR2_SESSION_FORMED):
        st.warning("Паспорт уже сформирован. Исключение кодов создаёт аудит-след.")

    created_by = st.text_input(
        "Кто утверждает (created_by / approved_by)",
        value="Пользователь Streamlit",
        key="passport_created_by",
    )

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Сохранить черновик паспорта", key="wr2_save_passport_draft"):
        st.session_state[WR2_SESSION_DRAFT] = True
        st.session_state[WR2_SESSION_FORMED] = False
        wr2_append_audit(
            {
                "datetime": datetime.now(timezone.utc).isoformat(),
                "boq_code": "—",
                "plan_line_id": "—",
                "old_outcome": "—",
                "decision": "SAVE_DRAFT",
                "override": False,
                "basis": f"Черновик: {len(full_scope)} код(ов)",
                "responsible": created_by,
                "comment": f"{project_sel} / {month_sel}",
            }
        )
        st.success("Черновик состава паспорта сохранён в session.")
    if b4.button("Очистить состав паспорта", key="wr2_clear_passport"):
        st.session_state[WR2_SESSION_COMPOSITION] = {}
        st.session_state[WR2_SESSION_DRAFT] = False
        st.session_state[WR2_SESSION_FORMED] = False
        wr2_append_audit(
            {
                "datetime": datetime.now(timezone.utc).isoformat(),
                "boq_code": "—",
                "plan_line_id": "—",
                "old_outcome": "—",
                "decision": "CLEAR",
                "override": False,
                "basis": "Очищен состав паспорта",
                "responsible": created_by,
                "comment": "—",
            }
        )
        st.success("Состав паспорта очищен.")
        st.rerun()

    validation_clean = wr2_validate_management_decisions(clean_scope, allow_risk=False)
    validation_full = wr2_validate_management_decisions(full_scope, allow_risk=True)
    for err in validation_clean + validation_full:
        st.error(err)

    can_clean = not validation_clean and not clean_scope.empty
    can_full = not validation_full and not full_scope.empty

    if b2.button(
        "Сформировать паспорт месяца",
        key="create_monthly_passport_btn",
        disabled=not can_clean,
    ):
        summary = wr2_create_monthly_passport_with_overrides(
            project_code=project_sel,
            month_key=month_sel,
            created_by=created_by.strip() or "Пользователь Streamlit",
            board_df=clean_scope,
            allow_risk=False,
        )
        _render_passport_summary(summary, formed_risk=False)

    if b3.button(
        "Сформировать паспорт с рисками",
        key="create_monthly_passport_risk_btn",
        disabled=not can_full,
    ):
        summary = wr2_create_monthly_passport_with_overrides(
            project_code=project_sel,
            month_key=month_sel,
            created_by=created_by.strip() or "Пользователь Streamlit",
            board_df=full_scope,
            allow_risk=True,
        )
        _render_passport_summary(summary, formed_risk=True)

    audit = st.session_state.get(WR2_SESSION_AUDIT, [])
    if audit:
        with st.expander(f"Аудит управленческих решений ({len(audit)})", expanded=False):
            st.dataframe(pd.DataFrame(audit), use_container_width=True, hide_index=True)


def _render_passport_summary(
    summary: Dict[str, Any],
    *,
    formed_risk: bool,
    project_code: str = "",
    month_key: str = "",
) -> None:
    status = summary.get("status")
    passport_id = display_dash(summary.get("passport_id"))
    project_display = project_code or "—"
    month_display = month_key or "—"

    if status in ("created", "rebuilt"):
        st.session_state[WR2_SESSION_FORMED] = True
        st.session_state[WR2_SESSION_DRAFT] = False
        if status == "rebuilt":
            st.success("Паспорт месяца актуализирован.")
        else:
            st.success("Месячное обязательство сформировано и передано в паспорт месяца.")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("passport_id", passport_id)
        c2.metric("project_code", project_display)
        c3.metric("month_key", month_display)
        c4.metric(
            "Строк включено",
            summary.get("current_rows", summary.get("created_lines", 0)),
        )
        c5, c6, c7 = st.columns(3)
        c5.metric("Было строк", summary.get("previous_rows", 0))
        c6.metric("Стало строк", summary.get("current_rows", summary.get("created_lines", 0)))
        c7.metric("Стоимость", money_ru(summary.get("total_value")))
        st.caption(
            f"Трудозатраты, ч: "
            f"{safe_num(summary.get('total_hours')):,.1f}".replace(",", " ")
        )
        st.info(
            "Данные переданы в Page 12 «Паспорт месяца». Следующий этап — итоговая "
            "сводка, таблица, разбивки и Excel-выгрузка на Page 12."
        )
        st.caption(
            "Откройте Page 12 «Паспорт месяца» в боковом меню и выберите тот же "
            f"проект ({project_display}) и месяц ({month_display}). "
            "Кэш Page 12 может обновляться до ~5 минут (ttl=300)."
        )
        if passport_id != "—" and project_code and month_key:
            for check in wr2_verify_passport_in_storage(
                passport_id, project_code, month_key
            ):
                st.success(f"✓ {check}")
        # No global st.cache_data.clear(); War Room loaders unchanged by passport write.
        # Page 12 load_passport_dataset is not imported here (avoid circular coupling).
    elif status == "already_exists":
        st.info(
            "Паспорт месяца уже существует. Повторное формирование должно "
            "актуализировать состав (rebuilt). Если видите это сообщение — "
            "проверьте, что migration replace_monthly_passport применена."
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("passport_id", passport_id)
        c2.metric("project_code", project_display)
        c3.metric("month_key", month_display)
        st.caption(
            "Откройте Page 12 «Паспорт месяца» и выберите проект и месяц для просмотра."
        )
    elif status in ("no_eligible_lines", "no_source_rows", "no_approved_lines", "validation_error"):
        st.warning("Нет строк, готовых для формирования паспорта месяца")
    else:
        st.error(f"Не удалось сформировать паспорт (status={status}).")

    warnings = summary.get("warnings") or []
    if warnings:
        for warn in warnings:
            st.warning(warn)

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

    if df.empty:
        return

    st.markdown("---")
    st.markdown("### Критические ограничения")
    render_top10(df)
    st.markdown("---")
    st.markdown("### Просроченные ограничения")
    render_overdue(df)
    st.markdown("---")
    st.markdown("### Топ владельцев ограничений")
    render_owners(df)
    st.markdown("---")
    st.markdown("### Динамика ограничений")
    render_gate_layers(df)
    st.markdown("---")
    render_department_summary(df)


def main() -> None:
    start_page("23 War Room")
    st.title("Управление решениями по месячному плану")
    st.caption(
        "Управленческий контур после допуска отделов. "
        "Операционный допуск — на странице «Допуск месячного плана»; "
        "здесь принимаются решения по включению кодов в паспорт месяца."
    )

    with stage("load constraints"):
        base_df = load_constraints()
    if base_df.empty:
        st.info(EMPTY_MSG)
        finish_page()
        return

    with stage("load v2 plan lines"):
        v2_df = load_v2_plan_lines()
    with stage("load review queue"):
        queue_df = load_review_queue()

    with stage("render war room v3"):
        render_war_room_v3(base_df, v2_df, queue_df)

    with st.expander(
        "Аналитика ограничений",
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


    finish_page()


if __name__ == "__main__":
    main()
