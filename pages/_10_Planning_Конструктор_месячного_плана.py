# ============================================================
# Конструктор месячного плана — выбор остатков BoQ
# Источник: public.monthly_scope_picker_view
# Корректировки: public.monthly_scope_manual_adjustments
# ============================================================

import html as html_lib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from services.constraints_service import create_constraints_for_review_queue
from services.supabase_client import supabase

SCOPE_VIEW = "monthly_scope_picker_view"
ADJUSTMENTS_TABLE = "monthly_scope_manual_adjustments"
DRAFT_KEY = "monthly_plan_draft_items"
SELECTED_RK_KEY = "scope_selected_boq_rk"
CUSTOMER_ACCEPTED_KEY = "monthly_scope_customer_accepted"
SCOPE_TABLE_PAGE_SIZE = 25
DRAFT_EDIT_MODE_KEY = "draft_edit_mode"
SAVED_DRAFT_KEY = "saved_monthly_plan_draft"
REVIEW_QUEUE_KEY = "monthly_plan_review_queue"
SAVED_DRAFT_ID_KEY = "saved_draft_id"
SOURCE_DRAFT_ID_KEY = "source_draft_id"
BASE_DRAFT_LINES_KEY = "base_draft_lines"
ACTIVE_PLAN_MONTH_KEY = "active_plan_month_key"
SELECTED_PLANNING_MONTH_KEY = "selected_planning_month_key"
DEFAULT_PLANNING_MONTH = "июнь-2026"
LINE_SOURCE_SENT_UI = "Ранее отправлено"
LINE_SOURCE_NEW_UI = "Новый код"
SENT_PLAN_STATUSES = ("SENT_TO_REVIEW", "APPROVED")
PREVIOUSLY_SENT_DISPLAY_STATUSES = ("SENT_TO_REVIEW", "APPROVED", "NEED_REVISION")
PREVIOUSLY_SENT_STATUS_PRIORITY = {
    "APPROVED": 0,
    "SENT_TO_REVIEW": 1,
    "NEED_REVISION": 2,
}
SENDABLE_DRAFT_STATUSES = ("DRAFT", "NEED_REVISION")
CONSTRUCTOR_TABLE_COLUMNS = [
    "BOQ Code",
    "Наименование",
    "Ед. изм.",
    "Титул",
    "Дисциплина",
    "Звено",
    "Плановый объём",
    "Плановая стоимость, ₽",
    "Требуется чел-ч",
    "Норма",
    "Стоимость труда, ₽",
    "Дата внесения / отправки",
    "Источник",
]
CONSTRUCTOR_SELECT_COLUMN = "Выбрать"
SELECTED_MONTH_PLAN_ROW_KEY = "selected_month_plan_row_key"
MONTH_PLAN_EDIT_ROW_KEY = "month_plan_edit_row_key"
DRAFT_VIEW_ONLY_KEY = "draft_view_only"
LOADED_DRAFT_STATUS_KEY = "loaded_draft_status"
DRAFT_SKIP_HYDRATE_MONTHS_KEY = "draft_skip_hydrate_months"
DEFAULT_LABOR_RATE_PER_HOUR = 3000.0

DRAFT_STATUS_FILTER_OPTIONS = [
    "Все",
    "DRAFT",
    "SENT_TO_REVIEW",
    "NEED_REVISION",
    "APPROVED",
    "CANCELLED",
    "SUPERSEDED",
]

DRAFT_STATUS_RU = {
    "DRAFT": "Черновик",
    "SENT_TO_REVIEW": "На проверке",
    "NEED_REVISION": "На доработке",
    "APPROVED": "Одобрен",
    "CANCELLED": "Отменён",
    "SUPERSEDED": "Заменён новой версией",
}

MONTH_KEY_ORDER = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]

SAVED_PLAN_DETAIL_COLUMNS = [
    "Код BOQ",
    "Наименование работы",
    "Ед. изм.",
    "Титул",
    "Дисциплина",
    "Месяц",
    "Звено",
    "Задача / зона / помещение",
    "Объём",
    "Плановая стоимость, ₽",
    "Требуется чел-ч",
    "Норма",
    "Стоимость трудозатрат, ₽",
    "Сценарий нормы",
    "Статус строки",
]

SAVED_PLAN_SUMMARY_COLUMNS = [
    "draft_id",
    "project_code",
    "Месяц (сводка)",
    "Титул (сводка)",
    "Дисциплина (сводка)",
    "draft_status",
    "Строк",
    "Плановая стоимость, ₽",
    "Создан",
]

SAVED_DRAFT_DELETE_PREVIEW_COLUMNS = SAVED_PLAN_SUMMARY_COLUMNS

DRAFT_STATUS_RU_TO_CODE = {label: code for code, label in DRAFT_STATUS_RU.items()}

# Статусы черновиков, резервирующих объём в AVAILABLE REMAINING
RESERVING_DRAFT_STATUSES = ("DRAFT", "SENT_TO_REVIEW", "NEED_REVISION", "APPROVED")

# Статусы месячного плана для UX-защиты от случайного дубля при save
MONTHLY_PLAN_GUARD_STATUSES = ("DRAFT", "NEED_REVISION", "SENT_TO_REVIEW", "APPROVED")
MONTHLY_PLAN_GUARD_STATUS_PRIORITY = {
    "DRAFT": 0,
    "NEED_REVISION": 1,
    "SENT_TO_REVIEW": 2,
    "APPROVED": 3,
}

NORM_STATUS_OPTIONS = ["Все", "ИСТОРИЯ ЕСТЬ", "НЕТ ИСТОРИИ"]

REMAINING_SOURCE_RU = {
    "SYSTEM_CALCULATED": "Расчёт системы",
    "MANUAL_EXECUTED_BEFORE_SYSTEM": "Учтено выполнение до Daily Progress",
    "MANUAL_VERIFIED": "Подтверждено вручную",
}

NORM_SCENARIO_REALISTIC = "Реалистичная норма"
NORM_SCENARIO_CAUTIOUS = "Осторожная норма"
NORM_SCENARIO_MANUAL = "Ручная норма"
NORM_SCENARIO_OPTIONS = [NORM_SCENARIO_REALISTIC, NORM_SCENARIO_CAUTIOUS, NORM_SCENARIO_MANUAL]
DISPLAY_MODE_OPTIONS = [
    "Все коды",
    "Только коды с остатком > 0",
    "Закрытые коды = 0",
    "Перевыполненные коды < 0",
]

# Очередь строительства → титулы (facility_building). Пустой список = все титулы.
CONSTRUCTION_STAGE_MAP: dict[str, list[str]] = {
    "Все очереди": [],
    "1-я очередь строительства": ["16160-13", "16160-17"],
    "2-я очередь строительства": ["26160-13", "26160-17"],
}
CONSTRUCTION_STAGE_OPTIONS = list(CONSTRUCTION_STAGE_MAP.keys())

CONFIDENCE_RU = {
    "HIGH": ("Данных достаточно", "badge-conf-high"),
    "MEDIUM": ("Данных средне", "badge-conf-medium"),
    "LOW": ("Данных мало", "badge-conf-low"),
}
NO_HISTORY_NORM_TEXT = "Истории нет — требуется ручная норма"

RU_MONTH_NAMES_LOWER = [
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
]

DRAFT_TABLE_HEIGHT = 650

NORM_SCENARIO_STYLE = {
    NORM_SCENARIO_REALISTIC: "background-color: rgba(59, 130, 246, 0.12); color: #1e40af; font-weight: 600;",
    NORM_SCENARIO_CAUTIOUS: "background-color: rgba(59, 130, 246, 0.08); color: #1e3a8a; font-weight: 600;",
    NORM_SCENARIO_MANUAL: "background-color: rgba(245, 158, 11, 0.14); color: #92400e; font-weight: 600;",
}
NORM_NO_HISTORY_STYLE = "background-color: rgba(107, 114, 128, 0.14); color: #374151; font-weight: 600;"
NORM_HISTORY_STYLE = "background-color: rgba(22, 163, 74, 0.12); color: #166534; font-weight: 600;"

BOQ_NAME_FALLBACKS = ("boq_name", "name", "work_name", "description")
UOM_FALLBACKS = ("unit_of_measure", "unit", "uom")

st.set_page_config(layout="wide")

st.markdown(
    """
    <style>
    .scope-card {
        border: 1px solid #e4e4e7; border-radius: 10px; padding: 14px 16px;
        margin-bottom: 12px; background: #fafafa;
    }
    .scope-title { font-size: 1.05rem; font-weight: 700; color: #18181b; margin: 0 0 4px 0; }
    .scope-sub { font-size: 0.82rem; color: #71717a; margin: 0 0 10px 0; }
    .scope-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 8px 12px; font-size: 0.82rem; margin-bottom: 10px;
    }
    .scope-k { color: #71717a; font-size: 0.75rem; }
    .scope-v { font-weight: 600; color: #27272a; }
    .scope-badge {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 0.72rem; font-weight: 700; color: #fff;
    }
    .badge-history { background: #1b7f3a; }
    .badge-no-history { background: #b91c1c; }
    .badge-manual { background: #b8860b; }
    .badge-system { background: #6b7280; }
    .badge-conf-high { background: #1b7f3a; }
    .badge-conf-medium { background: #b8860b; }
    .badge-conf-low { background: #6b7280; }
    .norm-metric {
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
        padding: 12px; margin-bottom: 8px;
    }
    .norm-metric-title { font-weight: 700; color: #0f172a; font-size: 0.9rem; }
    .norm-metric-value { font-size: 1.1rem; font-weight: 700; color: #18181b; margin: 4px 0; }
    .norm-metric-hint { font-size: 0.78rem; color: #64748b; line-height: 1.35; }
    .norm-row {
        display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 8px 0 6px 0;
    }
    .norm-card {
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px;
        padding: 10px 12px; min-height: 88px;
    }
    .norm-card-title { font-weight: 700; color: #0f172a; font-size: 0.82rem; margin-bottom: 4px; }
    .norm-card-value { font-size: 1rem; font-weight: 700; color: #18181b; margin-bottom: 4px; }
    .norm-card-hint { font-size: 0.72rem; color: #64748b; line-height: 1.3; }
    .chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip {
        display: inline-block; padding: 4px 10px; border-radius: 999px;
        background: #e0e7ff; color: #3730a3; font-size: 0.75rem; font-weight: 600;
    }
    .detail-card {
        border: 1px solid #d4d4d8; border-radius: 10px; padding: 14px 16px;
        background: #fff; margin-top: 10px;
    }
    .plan-block-title {
        font-size: 1.15rem; font-weight: 700; color: #18181b;
        margin: 0 0 10px 0; line-height: 1.3;
    }
    .draft-panel-block {
        border: 1px solid #d4d4d8; border-radius: 12px;
        background: #f8fafc; padding: 16px 18px; margin-top: 16px;
    }
    .draft-panel-title {
        font-size: 1.25rem; font-weight: 700; color: #18181b;
        margin: 0 0 12px 0;
    }
    .quick-open-header {
        font-weight: 700; color: #3f3f46; font-size: 0.82rem;
        padding: 6px 4px; border-bottom: 2px solid #e4e4e7; margin-bottom: 6px;
    }
    div[data-testid="stMetric"] { padding-top: 0.1rem; padding-bottom: 0.1rem; }
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #fafafa;
        border-radius: 10px;
        margin-bottom: 10px;
    }
    div[data-testid="stButton"] button[kind="primary"],
    div[data-testid="stButton"] button[kind="secondary"] {
        background: #0F766E !important;
        color: #ffffff !important;
        border: 1px solid #0F766E !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover,
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background: #115E59 !important;
        border-color: #115E59 !important;
        color: #ffffff !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:active,
    div[data-testid="stButton"] button[kind="secondary"]:active {
        background: #134E4A !important;
        border-color: #134E4A !important;
        color: #ffffff !important;
    }
    /* Page-local premium emerald/teal accent override */
    .stApp {
        --primary-color: #0F766E;
    }
    .stApp input[type="checkbox"],
    .stApp input[type="radio"] {
        accent-color: #0F766E !important;
    }
    .stApp [data-baseweb="checkbox"] input:checked + div {
        border-color: #0F766E !important;
        box-shadow: inset 0 0 0 6px #0F766E !important;
        background-color: rgba(20, 184, 166, 0.12) !important;
    }
    .stApp [data-baseweb="checkbox"] input:hover + div {
        border-color: #14B8A6 !important;
    }
    .stApp [data-baseweb="checkbox"] input:focus-visible + div,
    .stApp input:focus,
    .stApp textarea:focus,
    .stApp select:focus {
        outline: none !important;
        box-shadow: 0 0 0 2px rgba(20, 184, 166, 0.35) !important;
        border-color: #14B8A6 !important;
    }
    .stApp [data-baseweb="radio"] label,
    .stApp [data-baseweb="radio"] label:hover,
    .stApp [data-baseweb="radio"] label:focus-within {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    .stApp [role="switch"][aria-checked="true"] {
        background-color: #0F766E !important;
        border-color: #0F766E !important;
    }
    .stApp [role="switch"][aria-checked="true"]:hover {
        background-color: #14B8A6 !important;
        border-color: #14B8A6 !important;
    }
    /* selected row in st.dataframe (Glide Data Grid override) */
    [data-testid="stDataFrame"] {
        --gdg-accent-color: rgb(16, 185, 129) !important;
        --gdg-accent-light: rgba(16, 185, 129, 0.16) !important;
    }
    [data-testid="stDataFrame"] canvas {
        accent-color: rgb(16, 185, 129) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Конструктор месячного плана")
st.caption(
    "Выбор объёмов в месячный план из реального остатка по BoQ: "
    "всего, выполнено, остаток, деньги и историческая норма."
)

with st.expander("Как читать нормы?"):
    st.markdown(
        """
        Эти нормы не являются сметными нормативами ГЭСН, ФЕР, ТЕР, ЕНиР или корпоративными нормативами. Это фактическая история выполнения работ на проекте по данным Daily Progress.

        Сметные нормы нужны для расчёта стоимости, обоснования цены и сметной логики. Исторические нормы проекта нужны для планирования реальной производительности звеньев.

        Средняя историческая норма — все продуктивные человеко-часы / весь выполненный объём по этому коду. Хороша для общей оценки, но может искажаться сложными сменами.

        Реалистичная норма — значение, по которому половина прошлых смен была не хуже. Рекомендуется как основной сценарий для обычного месячного плана.

        Осторожная норма — значение для риск-сценария. Использовать, если фронт сложный, много доделок, стеснённость, слабая готовность РД/МТР/допусков или нестабильное звено.

        Ручная норма — используется только осознанно начальником участка, когда история неполная, код новый, условия резко отличаются от прошлых или система показывает "Истории нет".

        Если данных мало, решение обязательно должен подтвердить начальник участка.
        """
    )


@st.cache_resource
def get_supabase_write_client() -> Client | None:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def normalize_scope_merge_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Trim/normalize join keys for scope ↔ adjustments merge."""
    if df.empty:
        return df
    out = df.copy()
    key_cols = ["project_code", "facility_building", "construction_discipline", "boq_code"]
    for col in key_cols:
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()
            if col == "boq_code":
                out[col] = out[col].str.upper()
    return out


@st.cache_data(ttl=300)
def load_scope(limit: int = 10000) -> pd.DataFrame:
    response = supabase.table(SCOPE_VIEW).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


@st.cache_data(ttl=120)
def load_adjustments(limit: int = 10000) -> pd.DataFrame:
    """Anon key may be blocked by RLS — fallback to write client (service role)."""
    client = get_supabase_write_client() or supabase
    try:
        response = client.table(ADJUSTMENTS_TABLE).select("*").limit(limit).execute()
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_crew_options(limit: int = 5000) -> list[str]:
    try:
        response = (
            supabase.table("monthly_labor_summary")
            .select("crew_code")
            .limit(limit)
            .execute()
        )
        df = pd.DataFrame(response.data or [])
        if df.empty or "crew_code" not in df.columns:
            return []
        vals = df["crew_code"].dropna().astype(str).str.strip()
        return sorted(vals[vals != ""].unique().tolist())
    except Exception:
        return []


def safe_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_str(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def safe_num(value, default: float = 0.0) -> float:
    v = safe_float(value)
    return default if v is None else v


def compute_planning_remaining_for_row(row) -> tuple[float, str]:
    """Остаток: project_qty − (system_fact + manual_before); manual_verified — override."""
    total = safe_float(row.get("total_project_qty")) or 0.0
    executed = safe_float(row.get("executed_qty_all_time")) or 0.0
    m_ver = row.get("manual_verified_remaining_qty")
    if m_ver is not None and not (isinstance(m_ver, float) and pd.isna(m_ver)):
        verified = safe_float(m_ver)
        if verified is not None:
            return max(verified, 0.0), "MANUAL_VERIFIED"
    m_exec = safe_float(row.get("manual_executed_before_system")) or 0.0
    effective_executed = executed + m_exec
    remaining = max(total - effective_executed, 0.0)
    if m_exec > 0:
        return remaining, "MANUAL_EXECUTED_BEFORE_SYSTEM"
    return remaining, "SYSTEM_CALCULATED"


def ensure_columns(df: pd.DataFrame, columns: dict[str, Any]) -> pd.DataFrame:
    result = df.copy()
    for col, default in columns.items():
        if col not in result.columns:
            result[col] = default
    return result


def pick_field(row: dict | pd.Series, candidates: tuple[str, ...], default: str = "") -> str:
    data = row.to_dict() if isinstance(row, pd.Series) else row
    for key in candidates:
        val = data.get(key)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        text = str(val).strip()
        if text:
            return text
    return default


def pick_series(df: pd.DataFrame, candidates: tuple[str, ...], default: str = "") -> pd.Series:
    for key in candidates:
        if key in df.columns:
            return df[key].fillna("").astype(str).replace("nan", "")
    return pd.Series([default] * len(df), index=df.index)


def format_month_key(year: int, month: int) -> str:
    if month < 1 or month > 12:
        return ""
    return f"{RU_MONTH_NAMES_LOWER[month - 1]}-{year}"


def planning_month_options_2026() -> list[str]:
    return [
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


def get_selected_planning_month() -> str:
    selected = safe_str(st.session_state.get(SELECTED_PLANNING_MONTH_KEY))
    if selected:
        return selected
    return DEFAULT_PLANNING_MONTH


def session_has_other_month_draft_lines(selected_month: str) -> bool:
    target = safe_str(selected_month)
    for key in (BASE_DRAFT_LINES_KEY, DRAFT_KEY):
        for item in st.session_state.get(key, []):
            month = safe_str(item.get("month_key"))
            if month and month != target:
                return True
    return False


def replace_draft_items_by_uid(updated_items: list[dict]) -> None:
    updated_uids = {draft_line_uid(x) for x in updated_items}
    kept = [
        item
        for item in st.session_state.get(DRAFT_KEY, [])
        if draft_line_uid(item) not in updated_uids
    ]
    st.session_state[DRAFT_KEY] = kept + updated_items


def remove_draft_line_uids(uids: set[str]) -> None:
    st.session_state[DRAFT_KEY] = [
        item
        for item in st.session_state.get(DRAFT_KEY, [])
        if draft_line_uid(item) not in uids
    ]


def ensure_new_session_lines_added_at(month_key: str, project_filter: str) -> None:
    """Backfill added_at для новых строк session, если поле потерялось после reload/hydrate."""
    if not month_key:
        return
    sent_lines, _ = load_previously_sent_for_constructor(month_key, project_filter)
    sent_keys = {draft_item_key_parts(item) for item in sent_lines}
    now_iso = datetime.now(timezone.utc).isoformat()
    draft = list(st.session_state.get(DRAFT_KEY, []))
    updated = False
    for i, item in enumerate(draft):
        if safe_str(item.get("month_key")) != month_key:
            continue
        if draft_item_key_parts(item) in sent_keys:
            continue
        if safe_str(item.get("added_at")):
            continue
        draft[i] = {**item, "added_at": now_iso}
        updated = True
    if updated:
        st.session_state[DRAFT_KEY] = draft


def format_added_at_display(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    text = str(value).strip()
    if not text:
        return "—"
    try:
        dt = pd.to_datetime(text, utc=True)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return text[:16]


def resolve_line_added_at_from_sources(
    draft_row: dict | None,
    line_row: dict | None = None,
) -> str | None:
    draft_row = draft_row or {}
    line_row = line_row or {}
    for key in ("submitted_at", "sent_at", "created_at"):
        value = safe_str(draft_row.get(key))
        if value:
            return value
    value = safe_str(line_row.get("created_at"))
    return value or None


def _load_sent_draft_meta(
    draft_ids: list[str],
    project_code: str | None,
) -> list[dict]:
    statuses = list(PREVIOUSLY_SENT_DISPLAY_STATUSES)
    field_variants = (
        "draft_id,draft_status,project_code,month_key,created_at,submitted_at,sent_at",
        "draft_id,draft_status,project_code,month_key,created_at",
    )
    for fields in field_variants:
        try:
            query = (
                supabase.table("monthly_plan_drafts")
                .select(fields)
                .in_("draft_id", draft_ids)
                .in_("draft_status", statuses)
            )
            if project_code:
                query = query.eq("project_code", project_code)
            return query.execute().data or []
        except Exception as exc:  # noqa: BLE001
            if fields.endswith("created_at"):
                return []
            if "does not exist" not in str(exc).lower() and "column" not in str(exc).lower():
                raise
    return []


def resolve_constructor_project_code(project_filter: str, items: list[dict]) -> str | None:
    if project_filter and project_filter != "Все":
        return str(project_filter).strip()
    project_values = {
        safe_str(x.get("project_code"))
        for x in items
        if safe_str(x.get("project_code"))
    }
    if len(project_values) == 1:
        return next(iter(project_values))
    return None


def _pick_best_previously_sent_plan_row(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    ordered = sorted(
        rows,
        key=lambda r: (
            PREVIOUSLY_SENT_STATUS_PRIORITY.get(safe_str(r.get("draft_status")), 99),
            safe_str(r.get("created_at")),
        ),
    )
    best_priority = PREVIOUSLY_SENT_STATUS_PRIORITY.get(
        safe_str(ordered[0].get("draft_status")), 99
    )
    candidates = [
        row
        for row in ordered
        if PREVIOUSLY_SENT_STATUS_PRIORITY.get(safe_str(row.get("draft_status")), 99)
        == best_priority
    ]
    return max(candidates, key=lambda r: safe_str(r.get("created_at")))


@st.cache_data(ttl=60)
def load_previously_sent_lines_for_month(
    project_code: str | None,
    month_key: str,
) -> tuple[list[dict], bool]:
    """Все ранее отправленные строки месяца из всех draft'ов (не только последний)."""
    if not month_key:
        return [], False
    try:
        lines_query = (
            supabase.table("monthly_plan_draft_lines")
            .select("draft_id,project_code")
            .eq("month_key", month_key)
            .limit(5000)
        )
        if project_code:
            lines_query = lines_query.eq("project_code", project_code)
        lines_resp = lines_query.execute()
        line_rows = lines_resp.data or []
        if not line_rows:
            return [], False

        draft_ids = sorted(
            {
                safe_str(row.get("draft_id"))
                for row in line_rows
                if safe_str(row.get("draft_id"))
            }
        )
        sent_drafts = _load_sent_draft_meta(draft_ids, project_code)
        if not sent_drafts:
            return [], False

        draft_meta = {
            safe_str(d.get("draft_id")): d
            for d in sent_drafts
            if safe_str(d.get("draft_id"))
        }
        sent_draft_ids = sorted(draft_meta)
        legacy_mixed = any(
            safe_str(d.get("month_key")).upper() == "MIXED" for d in sent_drafts
        )

        detail_query = (
            supabase.table("monthly_plan_draft_lines")
            .select("*")
            .eq("month_key", month_key)
            .in_("draft_id", sent_draft_ids)
            .limit(5000)
        )
        if project_code:
            detail_query = detail_query.eq("project_code", project_code)
        detail_resp = detail_query.execute()

        rows_by_draft_date: list[tuple[str, dict]] = []
        for row in detail_resp.data or []:
            draft_id = safe_str(row.get("draft_id"))
            if draft_id not in draft_meta:
                continue
            draft_created = safe_str(draft_meta[draft_id].get("created_at"))
            rows_by_draft_date.append((draft_created, row))
        rows_by_draft_date.sort(key=lambda pair: pair[0])

        merged_by_key: dict[tuple[str, str, str, str], dict] = {}
        for _, row in rows_by_draft_date:
            draft_id = safe_str(row.get("draft_id"))
            item = line_db_to_session_item(row)
            if project_code and safe_str(item.get("project_code")) != project_code:
                continue
            key = draft_item_key_parts(item)
            added_at = resolve_line_added_at_from_sources(draft_meta.get(draft_id), row)
            merged_by_key[key] = {
                **item,
                "added_at": added_at,
                "line_id": row.get("line_id"),
                "draft_id": draft_id,
                "line_source_ui": LINE_SOURCE_SENT_UI,
                "read_only": True,
            }

        sent_lines = sorted(
            merged_by_key.values(),
            key=lambda item: draft_item_key_parts(item),
        )
        return sent_lines, legacy_mixed
    except Exception:  # noqa: BLE001
        return [], False


def load_previously_sent_for_constructor(
    month_key: str,
    project_filter: str,
) -> tuple[list[dict], bool]:
    project_code = resolve_constructor_project_code(
        project_filter,
        list(st.session_state.get(DRAFT_KEY, [])),
    )
    sent_lines, legacy_mixed = load_previously_sent_lines_for_month(project_code, month_key)
    if not sent_lines:
        sent_lines, legacy_mixed = load_previously_sent_lines_for_month(None, month_key)
    return sent_lines, legacy_mixed


def get_new_session_lines_for_month(
    month_key: str,
    project_filter: str = "Все",
    *,
    sent_keys: set | None = None,
) -> list[dict]:
    """Новые строки из DRAFT_KEY; строки, совпадающие с previously_sent, исключаются."""
    if sent_keys is None:
        sent_lines, _ = load_previously_sent_for_constructor(month_key, project_filter)
        sent_keys = {draft_item_key_parts(item) for item in sent_lines}
    return [
        item
        for item in filter_lines_by_month_key(list(st.session_state.get(DRAFT_KEY, [])), month_key)
        if draft_item_key_parts(item) not in sent_keys
    ]


def remove_new_session_lines_for_month(month_key: str, project_filter: str) -> None:
    new_lines = get_new_session_lines_for_month(month_key, project_filter)
    remove_uids = {draft_line_uid(item) for item in new_lines}
    st.session_state[DRAFT_KEY] = [
        item
        for item in st.session_state.get(DRAFT_KEY, [])
        if draft_line_uid(item) not in remove_uids
    ]
    st.session_state[SAVED_DRAFT_ID_KEY] = None
    st.session_state[LOADED_DRAFT_STATUS_KEY] = None
    st.session_state[DRAFT_EDIT_MODE_KEY] = False
    skip_months = st.session_state.setdefault(DRAFT_SKIP_HYDRATE_MONTHS_KEY, set())
    skip_months.add(month_key)


def has_unsaved_new_lines(month_key: str, project_filter: str) -> bool:
    new_lines = get_new_session_lines_for_month(month_key, project_filter)
    if not new_lines:
        return False
    saved_id = safe_str(st.session_state.get(SAVED_DRAFT_ID_KEY))
    if not saved_id:
        return True
    saved_count = count_saved_draft_lines_for_month(saved_id, month_key)
    return saved_count != len(new_lines)


def resolve_hydrate_project_code(project_filter: str, month_key: str) -> str | None:
    if project_filter and project_filter != "Все":
        return str(project_filter).strip()
    sent_lines, _ = load_previously_sent_for_constructor(month_key, project_filter)
    return resolve_constructor_project_code(project_filter, sent_lines)


def hydrate_saved_draft_lines_for_month(month_key: str, project_filter: str) -> bool:
    """Восстановить сохранённый черновик месяца из БД после refresh, если session пуст."""
    if not month_key:
        return False
    if st.session_state.get(SOURCE_DRAFT_ID_KEY):
        return False
    skip_months = st.session_state.setdefault(DRAFT_SKIP_HYDRATE_MONTHS_KEY, set())
    if month_key in skip_months:
        return False
    if get_new_session_lines_for_month(month_key, project_filter):
        return False
    project_code = resolve_hydrate_project_code(project_filter, month_key)
    if not project_code:
        return False
    active = find_active_draft_for_project_month(project_code, month_key)
    if not active:
        return False
    draft_id = safe_str(active.get("draft_id"))
    draft_status = safe_str(active.get("draft_status")) or "DRAFT"
    if not draft_id:
        return False
    month_items = filter_lines_by_month_key(load_draft_lines_as_items(draft_id), month_key)
    sent_lines, _ = load_previously_sent_for_constructor(month_key, project_filter)
    sent_keys = {draft_item_key_parts(item) for item in sent_lines}
    new_items = [
        item for item in month_items if draft_item_key_parts(item) not in sent_keys
    ]
    if not new_items:
        return False
    merged = [
        item
        for item in st.session_state.get(DRAFT_KEY, [])
        if safe_str(item.get("month_key")) != month_key
    ]
    merged.extend(new_items)
    st.session_state[DRAFT_KEY] = merged
    st.session_state[SAVED_DRAFT_ID_KEY] = draft_id
    st.session_state[LOADED_DRAFT_STATUS_KEY] = draft_status
    st.session_state[DRAFT_VIEW_ONLY_KEY] = False
    return True


def resolve_draft_lines_for_save(month_key: str | None = None, project_filter: str = "Все") -> list[dict]:
    target_month = safe_str(month_key) or get_selected_planning_month()
    if target_month:
        return get_new_session_lines_for_month(target_month, project_filter)
    sent_lines, _ = load_previously_sent_for_constructor(
        get_selected_planning_month() or "",
        project_filter,
    )
    sent_keys = {draft_item_key_parts(item) for item in sent_lines}
    return [
        item
        for item in st.session_state.get(DRAFT_KEY, [])
        if draft_item_key_parts(item) not in sent_keys
    ]


def count_saved_draft_lines_for_month(draft_id: str, month_key: str) -> int:
    if not draft_id or not month_key:
        return 0
    items = load_draft_lines_as_items(draft_id)
    return len(filter_lines_by_month_key(items, month_key))


def validate_draft_send_context(
    new_lines: list[dict],
    selected_month: str,
) -> tuple[bool, str, str | None]:
    if not new_lines:
        return False, "Нет новых строк для отправки.", None

    saved_draft_id = safe_str(st.session_state.get(SAVED_DRAFT_ID_KEY))
    if not saved_draft_id:
        return False, "Сначала сохраните черновик с новыми строками.", None

    loaded_status = safe_str(st.session_state.get(LOADED_DRAFT_STATUS_KEY))
    if loaded_status not in SENDABLE_DRAFT_STATUSES:
        return (
            False,
            "Нельзя повторно отправить ранее отправленный план. "
            "Сохраните новые строки как черновик дополнения.",
            None,
        )

    source_draft_id = safe_str(st.session_state.get(SOURCE_DRAFT_ID_KEY))
    if source_draft_id and saved_draft_id == source_draft_id:
        return (
            False,
            "Нельзя повторно отправить исходный план. Сначала сохраните черновик дополнения.",
            None,
        )

    saved_line_count = count_saved_draft_lines_for_month(saved_draft_id, selected_month)
    if saved_line_count != len(new_lines):
        return (
            False,
            "Черновик не совпадает с новыми строками на экране. "
            f"Сохранено: {saved_line_count}, новых строк: {len(new_lines)}. "
            "Сохраните черновик перед отправкой.",
            None,
        )

    return True, "", saved_draft_id


def build_constructor_month_lines(
    selected_month: str,
    project_filter: str,
) -> tuple[list[dict], list[dict], bool]:
    ensure_new_session_lines_added_at(selected_month, project_filter)
    sent_lines, legacy_mixed = load_previously_sent_for_constructor(
        selected_month,
        project_filter,
    )
    sent_keys = {draft_item_key_parts(item) for item in sent_lines}
    raw_new_lines = get_new_session_lines_for_month(
        selected_month,
        project_filter,
        sent_keys=sent_keys,
    )
    new_lines = [
        {
            **item,
            "line_source_ui": LINE_SOURCE_NEW_UI,
            "read_only": False,
        }
        for item in raw_new_lines
    ]
    return sent_lines, new_lines, legacy_mixed


def constructor_text(value) -> str:
    text = safe_str(value)
    return text if text else "-"


def constructor_item_norm_cell(item: dict) -> str:
    scenario_code = item.get("norm_scenario")
    norm_value = norm_productivity_fmt(
        item.get("planned_qty"),
        item.get("required_hours"),
        pick_field(item, UOM_FALLBACKS),
    )
    scenario_label = norm_scenario_display(scenario_code)
    if norm_value != "—":
        return f"{norm_value} · {scenario_label}"
    return scenario_label if scenario_label else "-"


def build_constructor_display_df(items: list[dict], *, selected_uid: str = "") -> pd.DataFrame:
    rows: list[dict] = []
    for item in items:
        source_ui = safe_str(item.get("line_source_ui"))
        if source_ui == LINE_SOURCE_NEW_UI:
            source_ui = f"🟢 {LINE_SOURCE_NEW_UI}"
        row_uid = month_plan_row_uid(item)
        boq_label = constructor_text(pick_field(item, ("boq_code",)))
        if selected_uid and row_uid == selected_uid:
            boq_label = f"▶ {boq_label}"
        rows.append(
            {
                "BOQ Code": boq_label,
                "Наименование": constructor_text(pick_field(item, BOQ_NAME_FALLBACKS)),
                "Ед. изм.": constructor_text(pick_field(item, UOM_FALLBACKS)),
                "Титул": constructor_text(pick_field(item, ("facility_building",))),
                "Дисциплина": constructor_text(pick_field(item, ("construction_discipline",))),
                "Звено": constructor_text(item.get("crew_code")),
                "Плановый объём": qty_fmt(safe_num(item.get("planned_qty"))),
                "Плановая стоимость, ₽": money_ru(safe_num(item.get("plan_value"))),
                "Требуется чел-ч": hours_fmt(safe_num(item.get("required_hours"))),
                "Норма": constructor_item_norm_cell(item),
                "Стоимость труда, ₽": money_ru(safe_num(item.get("labor_cost"))),
                "Дата внесения / отправки": format_added_at_display(item.get("added_at")),
                "Источник": constructor_text(source_ui),
            }
        )
    return pd.DataFrame(rows)


def build_constructor_selectable_table_df(
    items: list[dict],
    selected_uid: str,
) -> tuple[pd.DataFrame, list[str]]:
    row_uids = [month_plan_row_uid(item) for item in items]
    table_df = build_constructor_display_df(items, selected_uid=selected_uid)
    table_df.insert(
        0,
        CONSTRUCTOR_SELECT_COLUMN,
        [uid == selected_uid for uid in row_uids],
    )
    return table_df, row_uids


def sync_month_plan_row_selection(
    edited_table: pd.DataFrame,
    row_uids: list[str],
) -> tuple[str | None, bool]:
    if CONSTRUCTOR_SELECT_COLUMN not in edited_table.columns:
        return st.session_state.get(SELECTED_MONTH_PLAN_ROW_KEY), False
    checked = edited_table[CONSTRUCTOR_SELECT_COLUMN].fillna(False).astype(bool)
    checked_indices = [i for i, flag in enumerate(checked) if flag]
    if len(checked_indices) > 1:
        return row_uids[checked_indices[0]], True
    if len(checked_indices) == 1:
        return row_uids[checked_indices[0]], False
    return None, False


def month_plan_row_key_slug(row_uid: str) -> str:
    return row_uid.replace("|", "_").replace(" ", "_")[:120]


def render_month_plan_row_edit_form(
    item: dict,
    source_df: pd.DataFrame,
    crews: list[str],
    selected_month: str,
    project_filter: str,
) -> None:
    row_uid = month_plan_row_uid(item)
    key_slug = month_plan_row_key_slug(row_uid)
    st.markdown("##### Редактирование выбранной строки")
    st.text_input(
        "BOQ Code",
        value=constructor_text(pick_field(item, ("boq_code",))),
        disabled=True,
        key=f"edit_row_boq_{key_slug}",
    )
    st.text_input(
        "Наименование",
        value=constructor_text(pick_field(item, BOQ_NAME_FALLBACKS)),
        disabled=True,
        key=f"edit_row_name_{key_slug}",
    )
    planned_qty = st.number_input(
        "Плановый объём",
        min_value=0.0,
        value=safe_float(item.get("planned_qty")) or 0.0,
        step=0.01,
        key=f"edit_row_qty_{key_slug}",
    )
    if crews:
        crew_default = safe_str(item.get("crew_code"))
        crew_options = [""] + crews
        crew_index = crew_options.index(crew_default) if crew_default in crew_options else 0
        crew_code = st.selectbox(
            "Звено",
            crew_options,
            index=crew_index,
            key=f"edit_row_crew_{key_slug}",
        )
    else:
        crew_code = st.text_input(
            "Звено",
            value=safe_str(item.get("crew_code")),
            key=f"edit_row_crew_{key_slug}",
        )
    comment = st.text_area(
        "Комментарий",
        value=safe_str(item.get("comment")),
        key=f"edit_row_comment_{key_slug}",
    )
    save_col, cancel_col = st.columns(2)
    with save_col:
        save_clicked = st.button("Сохранить изменения строки", key=f"edit_row_save_{key_slug}")
    with cancel_col:
        cancel_clicked = st.button("Отменить", key=f"edit_row_cancel_{key_slug}")

    if cancel_clicked:
        st.session_state.pop(MONTH_PLAN_EDIT_ROW_KEY, None)
        st.rerun()

    if save_clicked:
        if planned_qty <= 0:
            st.error("Плановый объём должен быть больше нуля.")
            return
        updated = dict(item)
        updated["planned_qty"] = planned_qty
        updated["crew_code"] = str(crew_code or "").strip()
        updated["comment"] = str(comment or "").strip()
        updated = recalc_new_line_item_values(updated, source_df)
        remaining_error = validate_new_line_edit_remaining(
            updated,
            source_df,
            selected_month,
            project_filter,
        )
        if remaining_error:
            st.error(remaining_error)
            return
        replace_draft_items_by_uid([updated])
        st.session_state.pop(MONTH_PLAN_EDIT_ROW_KEY, None)
        st.success("Строка обновлена.")
        st.rerun()


def render_month_plan_row_actions(
    merged: list[dict],
    source_df: pd.DataFrame,
    crews: list[str],
    project_filter: str,
    selected_month: str,
    *,
    view_only: bool,
) -> None:
    st.markdown("#### Действия с выбранной строкой")
    selected_uid = safe_str(st.session_state.get(SELECTED_MONTH_PLAN_ROW_KEY))
    if not selected_uid:
        st.caption("Выберите строку галочкой.")
        return

    selected_item = find_month_plan_row_by_uid(merged, selected_uid)
    if selected_item is None:
        st.session_state.pop(SELECTED_MONTH_PLAN_ROW_KEY, None)
        st.session_state.pop(MONTH_PLAN_EDIT_ROW_KEY, None)
        st.caption("Выберите строку галочкой.")
        return

    boq = constructor_text(pick_field(selected_item, ("boq_code",)))
    source_label = safe_str(selected_item.get("line_source_ui"))
    st.info(f"Выбрано: **{boq}** · {source_label or '—'}")

    if not is_new_month_plan_row(selected_item):
        st.warning(
            "Ранее отправленную строку нельзя изменить или удалить из Constructor. "
            "Для отмены нужна процедура отзыва из допуска."
        )
        return

    if view_only:
        st.caption("Режим просмотра — редактирование недоступно.")
        return

    edit_uid = safe_str(st.session_state.get(MONTH_PLAN_EDIT_ROW_KEY))
    if edit_uid == selected_uid:
        render_month_plan_row_edit_form(
            selected_item,
            source_df,
            crews,
            selected_month,
            project_filter,
        )
        return

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if st.button("Изменить выбранную строку", key="month_plan_edit_selected_row"):
            st.session_state[MONTH_PLAN_EDIT_ROW_KEY] = selected_uid
            st.rerun()
    with action_col2:
        if st.button("Удалить выбранную строку", key="month_plan_delete_selected_row"):
            remove_draft_line_uids({draft_line_uid(selected_item)})
            st.session_state.pop(SELECTED_MONTH_PLAN_ROW_KEY, None)
            st.session_state.pop(MONTH_PLAN_EDIT_ROW_KEY, None)
            st.success("Строка удалена.")
            st.rerun()


def render_constructor_unified_summary(display_lines: list[dict]) -> None:
    if not display_lines:
        return
    sent_count = sum(
        1 for item in display_lines if safe_str(item.get("line_source_ui")) == LINE_SOURCE_SENT_UI
    )
    new_count = len(display_lines) - sent_count
    boq_codes = {safe_str(d.get("boq_code")) for d in display_lines if safe_str(d.get("boq_code"))}
    total_ev = sum(safe_num(d.get("plan_value")) for d in display_lines)
    total_hours = sum(safe_num(d.get("required_hours")) for d in display_lines)
    total_labor = sum(safe_num(d.get("labor_cost")) for d in display_lines)

    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.metric("Кол-во BOQ кодов", len(boq_codes))
    k2.metric("Кол-во строк", len(display_lines))
    k3.metric("Плановая стоимость, ₽", money_ru(total_ev))
    k4.metric("Direct hours", hours_fmt(total_hours))
    k5.metric("Стоимость труда, ₽", money_ru(total_labor))
    k6.metric("Ранее отправлено", sent_count)
    k7.metric("Новые строки", new_count)


def build_month_key_options(existing_keys: list[str] | None = None) -> list[str]:
    # month_key должен быть позже унифицирован с Supabase month_key.
    now = datetime.now()
    options: list[str] = []
    for offset in range(4):
        month = now.month + offset
        year = now.year
        while month > 12:
            month -= 12
            year += 1
        key = format_month_key(year, month)
        if key and key not in options:
            options.append(key)
    for key in sorted(existing_keys or []):
        text = safe_str(key)
        if text and text not in options:
            options.append(text)
    return options


def money_ru(value) -> str:
    v = safe_num(value)
    sign = "-" if v < 0 else ""
    amount = abs(v)
    whole, frac = f"{amount:.2f}".split(".")
    whole_fmt = f"{int(whole):,}".replace(",", " ")
    return f"{sign}{whole_fmt},{frac} ₽"


def draft_item_label(item: dict, index: int | None = None) -> str:
    name = pick_field(item, BOQ_NAME_FALLBACKS)[:40]
    crew = safe_str(item.get("crew_code")) or "—"
    scope = safe_str(item.get("line_scope_note")) or "—"
    prefix = f"#{index + 1} " if index is not None else ""
    return (
        f"{prefix}{pick_field(item, ('boq_code',))} | {name or '—'} | "
        f"{qty_fmt(item.get('planned_qty'))} | {crew} | {scope[:35]}"
    )


def draft_has_history(item: dict, source_df: pd.DataFrame) -> bool | None:
    src = source_row_by_key_parts(source_df, draft_item_key_parts(item))
    if src is None:
        return None
    return str(src.get("norm_status") or "").strip() == "ИСТОРИЯ ЕСТЬ"


def norm_scenario_display(scenario: str | None) -> str:
    code = str(scenario or "").strip()
    mapping = {
        NORM_SCENARIO_REALISTIC: "Реалистичная норма",
        NORM_SCENARIO_CAUTIOUS: "Осторожная норма",
        NORM_SCENARIO_MANUAL: "Ручная норма",
        "P50": "Реалистичная норма",
        "P80": "Осторожная норма",
        "Ручной": "Ручная норма",
    }
    return mapping.get(code, code or "—")


def norm_scenario_cell_style(scenario: str | None, has_history: bool | None) -> str:
    code = str(scenario or "").strip()
    if code in ("P50", NORM_SCENARIO_REALISTIC):
        code = NORM_SCENARIO_REALISTIC
    elif code in ("P80", NORM_SCENARIO_CAUTIOUS):
        code = NORM_SCENARIO_CAUTIOUS
    elif code in ("Ручной", NORM_SCENARIO_MANUAL):
        code = NORM_SCENARIO_MANUAL
    if code == NORM_SCENARIO_MANUAL:
        return NORM_SCENARIO_STYLE[NORM_SCENARIO_MANUAL]
    if has_history is False:
        return NORM_NO_HISTORY_STYLE
    if has_history is True and code == NORM_SCENARIO_REALISTIC:
        return NORM_HISTORY_STYLE
    return NORM_SCENARIO_STYLE.get(code, "")


def scope_norm_source_label(row: pd.Series) -> str:
    norm = norm_status_label(row.get("norm_status"))
    if str(row.get("norm_status") or "") == "ИСТОРИЯ ЕСТЬ":
        return f"Историческая норма · {norm}"
    if str(row.get("norm_status") or "") == "НЕТ ИСТОРИИ":
        return f"Нет истории · {norm}"
    return norm


def remove_draft_indices(indices: set[int]) -> None:
    draft: list[dict] = st.session_state.get(DRAFT_KEY, [])
    st.session_state[DRAFT_KEY] = [item for i, item in enumerate(draft) if i not in indices]


def money(value) -> str:
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.0f} ₽".replace(",", " ")


def qty_fmt(value) -> str:
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", " ")


def hours_fmt(value) -> str:
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.1f} чел-ч".replace(",", " ")


def hours_per_unit_fmt(value, no_history: bool = False) -> str:
    if no_history:
        return NO_HISTORY_NORM_TEXT
    v = safe_float(value)
    if v is None:
        return NO_HISTORY_NORM_TEXT
    return f"{v:,.2f} ч/ед".replace(",", " ")


def confidence_display(confidence_level, norm_status: str | None = None) -> tuple[str, str]:
    if str(norm_status or "") == "НЕТ ИСТОРИИ":
        return "Истории нет", "badge-conf-low"
    key = str(confidence_level or "").strip().upper()
    return CONFIDENCE_RU.get(key, ("Данных мало", "badge-conf-low"))


def norm_scenario_hours(row: pd.Series, scenario: str, manual_norm: float = 0.0):
    if str(row.get("norm_status") or "") == "НЕТ ИСТОРИИ" and scenario != NORM_SCENARIO_MANUAL:
        return None
    if scenario == NORM_SCENARIO_REALISTIC:
        return safe_float(row.get("p50_hours_per_unit"))
    if scenario == NORM_SCENARIO_CAUTIOUS:
        return safe_float(row.get("p80_hours_per_unit"))
    if scenario == NORM_SCENARIO_MANUAL and manual_norm > 0:
        return manual_norm
    return None


def esc(value) -> str:
    if value is None:
        return ""
    return html_lib.escape(str(value))


def remaining_percent(planning_remaining, total_project) -> float | None:
    total = safe_float(total_project) or 0.0
    if total == 0:
        return None
    rem = safe_float(planning_remaining)
    if rem is None:
        return None
    return rem / total * 100.0


def percent_fmt(planning_remaining, total_project) -> str:
    pct = remaining_percent(planning_remaining, total_project)
    if pct is None:
        return "—"
    return f"{pct:.1f}%"


def parse_percent_cell(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text == "—":
        return None
    text = text.replace("%", "").strip().replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_qty_cell(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text == "—":
        return None
    text = text.replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def percent_display(value) -> str:
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:.1f}%"


def norm_status_label(value) -> str:
    text = str(value or "").strip()
    if text == "ИСТОРИЯ ЕСТЬ":
        return "История есть"
    if text == "НЕТ ИСТОРИИ":
        return "Нет истории"
    return text or "—"


def remaining_status_css(qty, pct) -> str:
    qty_val = safe_float(qty)
    pct_val = safe_float(pct)
    if qty_val is not None and qty_val < 0:
        return "background-color: rgba(139, 92, 246, 0.16); color: #4c1d95; font-weight: 600;"
    if qty_val is not None and qty_val == 0:
        return "background-color: rgba(16, 185, 129, 0.10); color: #065f46; font-weight: 600;"
    if pct_val is None:
        return ""
    if pct_val <= 10:
        return "background-color: rgba(16, 185, 129, 0.16); color: #065f46; font-weight: 600;"
    if pct_val <= 50:
        return "background-color: rgba(245, 158, 11, 0.16); color: #92400e; font-weight: 600;"
    return "background-color: rgba(249, 115, 22, 0.16); color: #9a3412; font-weight: 600;"


def section_title(title: str) -> None:
    st.markdown(f'<p class="plan-block-title">{esc(title)}</p>', unsafe_allow_html=True)


def highlight_remaining_row(row: pd.Series, selected_row_idx: int | None = None) -> pd.Series:
    styles = pd.Series("", index=row.index)
    col_rem = (
        "Доступный остаток"
        if "Доступный остаток" in row.index
        else ("Остаток" if "Остаток" in row.index else "Остаток объёма")
    )
    col_pct = "Остаток, %"
    if selected_row_idx is not None and row.name == selected_row_idx:
        styles[:] = "background-color: rgba(16, 185, 129, 0.10); color: #0f172a;"

    qty = parse_qty_cell(row.get(col_rem)) if col_rem in row.index else None
    pct = parse_percent_cell(row.get(col_pct)) if col_pct in row.index else None
    color = remaining_status_css(qty, pct)

    if color:
        if col_rem in styles.index:
            styles[col_rem] = color
        if col_pct in styles.index:
            styles[col_pct] = color
    return styles


def apply_scope_table_style(display_df: pd.DataFrame, selected_row_idx: int | None = None):
    rem_col = (
        "Доступный остаток"
        if "Доступный остаток" in display_df.columns
        else ("Остаток" if "Остаток" in display_df.columns else "Остаток объёма")
    )
    if rem_col in display_df.columns and "Остаток, %" in display_df.columns:
        return display_df.style.apply(
            lambda row: highlight_remaining_row(row, selected_row_idx=selected_row_idx),
            axis=1,
        )
    return display_df


def render_filter_summary(df: pd.DataFrame) -> None:
    st.markdown("**Сводка по выбранному срезу**")
    if df.empty:
        st.caption("Нет данных по выбранным фильтрам.")
        return

    total_val = (
        pd.to_numeric(df["total_project_value"], errors="coerce").fillna(0).sum()
        if "total_project_value" in df.columns
        else 0.0
    )
    rem_val = (
        pd.to_numeric(df["planning_remaining_value"], errors="coerce").fillna(0).sum()
        if "planning_remaining_value" in df.columns
        else 0.0
    )
    # Освоено = всего − остаток (учитывает manual_executed_before_system через planning_remaining_*).
    exec_val = max(total_val - rem_val, 0.0)
    total_qty = (
        pd.to_numeric(df["total_project_qty"], errors="coerce").fillna(0).sum()
        if "total_project_qty" in df.columns
        else 0.0
    )
    rem_qty = (
        pd.to_numeric(df["planning_remaining_qty"], errors="coerce").fillna(0).sum()
        if "planning_remaining_qty" in df.columns
        else 0.0
    )
    pct_exec = (exec_val / total_val * 100.0) if total_val else None
    pct_rem = (rem_val / total_val * 100.0) if total_val else None

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("Всего по BOQ, ₽", money(total_val))
    r1c2.metric("Освоено в деньгах", money(exec_val))
    r1c3.metric("Остаток в деньгах", money(rem_val))
    r1c4.metric("Кодов в срезе", len(df))

    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("% освоения", percent_display(pct_exec))
    r2c2.metric("% остатка", percent_display(pct_rem))
    r2c3.metric("Всего объёма", qty_fmt(total_qty))
    r2c4.metric("Остаток объёма", qty_fmt(rem_qty))


def norm_scenario_hint(scenario: str) -> str:
    if scenario in (NORM_SCENARIO_REALISTIC, "Реалистичная норма (P50)"):
        return "Рекомендуется по умолчанию для обычного плана."
    if scenario in (NORM_SCENARIO_CAUTIOUS, "Осторожная норма (P80)"):
        return "Для сложного фронта и риска недовыполнения."
    return "Только если история неполная или условия отличаются."


def get_customer_accepted_qty(rk: str) -> float:
    store = st.session_state.get(CUSTOMER_ACCEPTED_KEY, {})
    return float(store.get(rk, 0.0) or 0.0)


def set_customer_accepted_qty(rk: str, value: float) -> None:
    if CUSTOMER_ACCEPTED_KEY not in st.session_state:
        st.session_state[CUSTOMER_ACCEPTED_KEY] = {}
    st.session_state[CUSTOMER_ACCEPTED_KEY][rk] = value


def row_key(row: pd.Series) -> str:
    parts = [
        str(row.get("project_code", "")),
        str(row.get("facility_building", "")),
        str(row.get("construction_discipline", "")),
        str(row.get("boq_code", "")),
    ]
    return "|".join(parts)


def draft_planned_qty_for_boq(row: pd.Series) -> float:
    draft: list[dict] = st.session_state.get(DRAFT_KEY, [])
    if not draft:
        return 0.0
    target_parts = (
        str(row.get("project_code", "")).strip().upper(),
        str(row.get("facility_building", "")).strip().upper(),
        str(row.get("construction_discipline", "")).strip().upper(),
        str(row.get("boq_code", "")).strip().upper(),
    )
    total = 0.0
    for item in draft:
        item_parts = (
            str(item.get("project_code", "")).strip().upper(),
            str(item.get("facility_building", "")).strip().upper(),
            str(item.get("construction_discipline", "")).strip().upper(),
            str(item.get("boq_code", "")).strip().upper(),
        )
        if item_parts == target_parts:
            total += safe_float(item.get("planned_qty")) or 0.0
    return total


def draft_item_key_parts(item: dict) -> tuple[str, str, str, str]:
    return (
        str(item.get("project_code", "")).strip().upper(),
        str(item.get("facility_building", "")).strip().upper(),
        str(item.get("construction_discipline", "")).strip().upper(),
        str(item.get("boq_code", "")).strip().upper(),
    )


def boq_key_parts_from_row(row: pd.Series | dict) -> tuple[str, str, str, str]:
    if isinstance(row, pd.Series):
        getter = row.get
    else:
        getter = row.get
    return (
        str(getter("project_code", "")).strip().upper(),
        str(getter("facility_building", "")).strip().upper(),
        str(getter("construction_discipline", "")).strip().upper(),
        str(getter("boq_code", "")).strip().upper(),
    )


@st.cache_data(ttl=120)
def _load_reserved_planned_qty_from_db(exclude_draft_id: str = "") -> dict[tuple[str, str, str, str], float]:
    """Сумма planned_qty по сохранённым черновикам (кроме exclude_draft_id)."""
    try:
        drafts_resp = (
            supabase.table("monthly_plan_drafts")
            .select("draft_id")
            .in_("draft_status", list(RESERVING_DRAFT_STATUSES))
            .limit(5000)
            .execute()
        )
        draft_ids = [
            str(r.get("draft_id") or "")
            for r in (drafts_resp.data or [])
            if str(r.get("draft_id") or "") and str(r.get("draft_id") or "") != exclude_draft_id
        ]
        if not draft_ids:
            return {}
        lines_resp = (
            supabase.table("monthly_plan_draft_lines")
            .select(
                "draft_id,project_code,facility_building,construction_discipline,boq_code,planned_qty"
            )
            .in_("draft_id", draft_ids)
            .limit(50000)
            .execute()
        )
    except Exception:
        return {}

    totals: dict[tuple[str, str, str, str], float] = {}
    for line in lines_resp.data or []:
        key = (
            str(line.get("project_code") or "").strip().upper(),
            str(line.get("facility_building") or "").strip().upper(),
            str(line.get("construction_discipline") or "").strip().upper(),
            str(line.get("boq_code") or "").strip().upper(),
        )
        totals[key] = totals.get(key, 0.0) + (safe_float(line.get("planned_qty")) or 0.0)
    return totals


@st.cache_data(ttl=120)
def _load_boq_planning_usage_cache() -> list[dict]:
    """Все строки резервирующих черновиков для блока «Использование в планах»."""
    try:
        drafts_resp = (
            supabase.table("monthly_plan_drafts")
            .select("draft_id,draft_status")
            .in_("draft_status", list(RESERVING_DRAFT_STATUSES))
            .limit(5000)
            .execute()
        )
        draft_status = {
            str(r.get("draft_id") or ""): str(r.get("draft_status") or "")
            for r in (drafts_resp.data or [])
            if str(r.get("draft_id") or "")
        }
        if not draft_status:
            return []
        lines_resp = (
            supabase.table("monthly_plan_draft_lines")
            .select(
                "draft_id,project_code,facility_building,construction_discipline,boq_code,"
                "month_key,crew_id,planned_qty"
            )
            .in_("draft_id", list(draft_status.keys()))
            .limit(50000)
            .execute()
        )
    except Exception:
        return []

    rows: list[dict] = []
    for line in lines_resp.data or []:
        did = str(line.get("draft_id") or "")
        rows.append(
            {
                "project_code": line.get("project_code"),
                "facility_building": line.get("facility_building"),
                "construction_discipline": line.get("construction_discipline"),
                "boq_code": line.get("boq_code"),
                "month_key": line.get("month_key"),
                "crew_id": line.get("crew_id"),
                "planned_qty": line.get("planned_qty"),
                "draft_status": draft_status.get(did, ""),
            }
        )
    return rows


def build_planned_qty_map(draft_items: list[dict] | None = None) -> dict[tuple[str, str, str, str], float]:
    """Активный черновик + сохранённые черновики (без двойного учёта loaded draft_id)."""
    totals: dict[tuple[str, str, str, str], float] = {}
    session_draft: list[dict] = (
        draft_items if draft_items is not None else st.session_state.get(DRAFT_KEY, [])
    )
    current_draft_id = str(st.session_state.get(SAVED_DRAFT_ID_KEY) or "")

    for item in session_draft:
        key = draft_item_key_parts(item)
        totals[key] = totals.get(key, 0.0) + (safe_float(item.get("planned_qty")) or 0.0)

    exclude_id = current_draft_id if session_draft and current_draft_id else ""
    for key, qty in _load_reserved_planned_qty_from_db(exclude_id).items():
        totals[key] = totals.get(key, 0.0) + qty
    return totals


def apply_available_remaining(
    df: pd.DataFrame, planned_map: dict[tuple[str, str, str, str], float]
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    unit_price = (
        pd.to_numeric(out["unit_price"], errors="coerce").fillna(0)
        if "unit_price" in out.columns
        else 0
    )
    p50 = (
        pd.to_numeric(out["p50_hours_per_unit"], errors="coerce").fillna(0)
        if "p50_hours_per_unit" in out.columns
        else 0
    )
    available_qty: list[float] = []
    for _, row in out.iterrows():
        key = boq_key_parts_from_row(row)
        project_rem = safe_float(row.get("planning_remaining_qty")) or 0.0
        reserved = planned_map.get(key, 0.0)
        available_qty.append(project_rem - reserved)
    out["available_remaining_qty"] = available_qty
    out["available_remaining_value"] = out["available_remaining_qty"] * unit_price
    out["available_direct_hours"] = out["available_remaining_qty"] * p50
    out["available_labor_cost"] = out["available_direct_hours"] * DEFAULT_LABOR_RATE_PER_HOUR
    return out


def norm_productivity_fmt(planned_qty, required_hours, unit_of_measure: str = "") -> str:
    """Производительность: ед./чел-ч (фактически применённая по строке)."""
    qty = safe_float(planned_qty) or 0.0
    hours = safe_float(required_hours) or 0.0
    if qty <= 0 or hours <= 0:
        return "—"
    rate = qty / hours
    uom = str(unit_of_measure or "ед.").strip() or "ед."
    return f"{rate:.2f} {uom}/чел-ч"


def render_draft_executive_summary(draft: list[dict]) -> None:
    if not draft:
        return
    months = {safe_str(d.get("month_key")) for d in draft if safe_str(d.get("month_key"))}
    facilities = {safe_str(d.get("facility_building")) for d in draft if safe_str(d.get("facility_building"))}
    month_label = next(iter(months), "—").upper() if len(months) == 1 else "Несколько месяцев"
    facility_label = next(iter(facilities), "—").upper() if len(facilities) == 1 else "Несколько титулов"
    st.markdown(f"#### {month_label} · {facility_label}")

    boq_codes = {safe_str(d.get("boq_code")) for d in draft if safe_str(d.get("boq_code"))}
    total_ev = sum(safe_num(d.get("plan_value")) for d in draft)
    total_hours = sum(safe_num(d.get("required_hours")) for d in draft)
    total_labor = sum(safe_num(d.get("labor_cost")) for d in draft)

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Кол-во BOQ кодов", len(boq_codes))
    k2.metric("Кол-во строк", len(draft))
    k3.metric("Плановая стоимость", money_ru(total_ev))
    k4.metric("Direct hours", hours_fmt(total_hours))
    k5.metric("Стоимость труда", money_ru(total_labor))

    st.markdown("**Срез по звеньям**")
    crew_rows: list[dict] = []
    by_crew: dict[str, list[dict]] = {}
    for item in draft:
        crew = safe_str(item.get("crew_code")) or "—"
        by_crew.setdefault(crew, []).append(item)
    for crew, items in sorted(by_crew.items(), key=lambda x: x[0].casefold()):
        crew_rows.append(
            {
                "Звено": crew,
                "Строк": len(items),
                "Qty": qty_fmt(sum(safe_num(i.get("planned_qty")) for i in items)),
                "План ₽": money_ru(sum(safe_num(i.get("plan_value")) for i in items)),
                "Чел-ч": hours_fmt(sum(safe_num(i.get("required_hours")) for i in items)),
                "Стоимость труда ₽": money_ru(sum(safe_num(i.get("labor_cost")) for i in items)),
            }
        )
    st.dataframe(pd.DataFrame(crew_rows), use_container_width=True, hide_index=True)


def render_boq_planning_usage(row: pd.Series) -> None:
    key = boq_key_parts_from_row(row)
    usage_rows: list[dict] = []
    current_draft_id = str(st.session_state.get(SAVED_DRAFT_ID_KEY) or "")

    for item in st.session_state.get(DRAFT_KEY, []):
        if boq_key_parts_from_row(item) != key:
            continue
        status = str(st.session_state.get(LOADED_DRAFT_STATUS_KEY) or "DRAFT")
        usage_rows.append(
            {
                "Месяц": safe_str(item.get("month_key")) or "—",
                "Титул": safe_str(item.get("facility_building")) or "—",
                "Звено": safe_str(item.get("crew_code")) or "—",
                "Qty": qty_fmt(item.get("planned_qty")),
                "Статус": DRAFT_STATUS_RU.get(status, status or "Черновик (на экране)"),
            }
        )

    for line in _load_boq_planning_usage_cache():
        if boq_key_parts_from_row(line) != key:
            continue
        if current_draft_id and str(line.get("draft_id") or "") == current_draft_id:
            continue
        status_code = str(line.get("draft_status") or "")
        usage_rows.append(
            {
                "Месяц": safe_str(line.get("month_key")) or "—",
                "Титул": safe_str(line.get("facility_building")) or "—",
                "Звено": safe_str(line.get("crew_id")) or "—",
                "Qty": qty_fmt(line.get("planned_qty")),
                "Статус": DRAFT_STATUS_RU.get(status_code, status_code or "—"),
            }
        )

    with st.expander("Использование в планах", expanded=False):
        if not usage_rows:
            st.caption("Этот код ещё не распределён по сохранённым или активным черновикам.")
        else:
            st.dataframe(pd.DataFrame(usage_rows), use_container_width=True, hide_index=True)


def draft_line_uid(item: dict) -> str:
    """Внутренний ключ строки UI-черновика для проверки полного дубликата."""
    qty = safe_float(item.get("planned_qty"))
    if qty is None:
        qty_str = "0"
    else:
        qty_str = f"{qty:.6f}".rstrip("0").rstrip(".") or "0"
    return "|".join(
        [
            safe_str(item.get("month_key")),
            safe_str(item.get("boq_code")),
            safe_str(item.get("crew_code")),
            safe_str(item.get("line_scope_note")),
            qty_str,
        ]
    )


def month_plan_row_uid(item: dict) -> str:
    if safe_str(item.get("line_source_ui")) == LINE_SOURCE_NEW_UI:
        return draft_line_uid(item)
    line_id = safe_str(item.get("line_id"))
    draft_id = safe_str(item.get("draft_id"))
    if draft_id and line_id:
        return f"{draft_id}|{line_id}"
    if line_id:
        return line_id
    return "sent:" + draft_line_uid(item)


def is_new_month_plan_row(item: dict) -> bool:
    return safe_str(item.get("line_source_ui")) == LINE_SOURCE_NEW_UI


def find_month_plan_row_by_uid(items: list[dict], row_uid: str) -> dict | None:
    for item in items:
        if month_plan_row_uid(item) == row_uid:
            return item
    return None


def recalc_new_line_item_values(item: dict, source_df: pd.DataFrame) -> dict:
    updated = dict(item)
    key_parts = draft_item_key_parts(updated)
    src_row = source_row_by_key_parts(source_df, key_parts)
    unit_price = (
        safe_float(src_row.get("unit_price"))
        if src_row is not None
        else safe_float(updated.get("unit_price"))
    )
    unit_price = unit_price or 0.0
    scenario_code = str(updated.get("norm_scenario") or NORM_SCENARIO_REALISTIC)
    if src_row is None:
        norm_hpu = safe_float(updated.get("required_hours")) / max(
            (safe_float(updated.get("planned_qty")) or 1.0), 1e-9
        )
    elif scenario_code == NORM_SCENARIO_REALISTIC:
        norm_hpu = safe_float(src_row.get("p50_hours_per_unit"))
    elif scenario_code == NORM_SCENARIO_CAUTIOUS:
        norm_hpu = safe_float(src_row.get("p80_hours_per_unit"))
    else:
        norm_hpu = safe_float(updated.get("manual_norm_value"))

    planned_qty = safe_float(updated.get("planned_qty")) or 0.0
    updated["plan_value"] = planned_qty * unit_price
    updated["required_hours"] = planned_qty * (norm_hpu or 0.0)
    updated["labor_rate_per_hour"] = DEFAULT_LABOR_RATE_PER_HOUR
    updated["labor_cost"] = (safe_float(updated.get("required_hours")) or 0.0) * DEFAULT_LABOR_RATE_PER_HOUR
    return updated


def validate_new_line_edit_remaining(
    updated_item: dict,
    source_df: pd.DataFrame,
    month_key: str,
    project_filter: str,
) -> str | None:
    sent_lines, _ = load_previously_sent_for_constructor(month_key, project_filter)
    sent_keys = {draft_item_key_parts(item) for item in sent_lines}
    peer_items = [
        item
        for item in filter_lines_by_month_key(list(st.session_state.get(DRAFT_KEY, [])), month_key)
        if draft_item_key_parts(item) not in sent_keys
        and draft_line_uid(item) != draft_line_uid(updated_item)
    ]
    test_items = peer_items + [updated_item]
    planned_map = build_planned_qty_map(test_items)
    key_parts = draft_item_key_parts(updated_item)
    reserved_total = planned_map.get(key_parts, 0.0)
    src_row = source_row_by_key_parts(source_df, key_parts)
    project_remaining = (
        safe_float(src_row.get("planning_remaining_qty")) if src_row is not None else None
    )
    if project_remaining is not None and reserved_total > project_remaining + 1e-9:
        return (
            f"Превышен доступный остаток по коду {key_parts[3]}: "
            f"остаток {qty_fmt(project_remaining)}, запланировано {qty_fmt(reserved_total)}."
        )
    return None


def source_row_by_key_parts(source_df: pd.DataFrame, key_parts: tuple[str, str, str, str]) -> pd.Series | None:
    if source_df.empty:
        return None
    mask = (
        source_df["project_code"].astype(str).str.strip().str.upper().eq(key_parts[0])
        & source_df["facility_building"].astype(str).str.strip().str.upper().eq(key_parts[1])
        & source_df["construction_discipline"].astype(str).str.strip().str.upper().eq(key_parts[2])
        & source_df["boq_code"].astype(str).str.strip().str.upper().eq(key_parts[3])
    )
    match = source_df[mask]
    if match.empty:
        return None
    return match.iloc[0]


def validate_draft_for_save(draft: list[dict], source_df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if not draft:
        errors.append("Черновик пуст.")
        return errors

    planned_map = build_planned_qty_map(draft)
    draft_keys = {draft_item_key_parts(item) for item in draft}

    for idx, item in enumerate(draft, start=1):
        month = str(item.get("month_key") or "").strip()
        crew = str(item.get("crew_code") or "").strip()
        qty = safe_float(item.get("planned_qty")) or 0.0
        scenario = str(item.get("norm_scenario") or "").strip()
        if not month:
            errors.append(f"Строка {idx}: не указан месяц.")
        if not crew:
            errors.append(f"Строка {idx}: не указано звено.")
        if qty <= 0:
            errors.append(f"Строка {idx}: объём должен быть больше нуля.")
        if not scenario:
            errors.append(f"Строка {idx}: не указан сценарий нормы.")

    for key_parts, reserved_total in planned_map.items():
        if key_parts not in draft_keys:
            continue
        src_row = source_row_by_key_parts(source_df, key_parts)
        project_remaining = safe_float(src_row.get("planning_remaining_qty")) if src_row is not None else None
        if project_remaining is not None and reserved_total > project_remaining + 1e-9:
            errors.append(
                "Превышен доступный остаток по коду "
                f"{key_parts[3]} ({key_parts[1]} / {key_parts[2]}): "
                f"остаток проекта {qty_fmt(project_remaining)}, "
                f"уже запланировано {qty_fmt(reserved_total)}, "
                f"доступно {qty_fmt(project_remaining - reserved_total)}."
            )
    return errors


def validate_draft_single_month_key(draft: list[dict]) -> str | None:
    month_values = {
        safe_str(d.get("month_key"))
        for d in draft
        if safe_str(d.get("month_key"))
    }
    if len(month_values) > 1:
        return (
            "Нельзя сохранить один месячный черновик с разными месяцами. "
            "Разделите строки по месяцам."
        )
    return None


def _pick_best_monthly_plan_row(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    ordered = sorted(
        rows,
        key=lambda r: (
            MONTHLY_PLAN_GUARD_STATUS_PRIORITY.get(
                safe_str(r.get("draft_status")), 99
            ),
            safe_str(r.get("created_at")),
        ),
    )
    return ordered[0]


def filter_lines_by_month_key(lines: list[dict], month_key: str) -> list[dict]:
    target = safe_str(month_key)
    if not target:
        return list(lines)
    return [item for item in lines if safe_str(item.get("month_key")) == target]


def resolve_supplement_active_month_key(
    pending_items: list[dict],
    project_filter: str = "",
) -> str | None:
    pending_months = {
        safe_str(x.get("month_key"))
        for x in pending_items
        if safe_str(x.get("month_key"))
    }
    if len(pending_months) == 1:
        return next(iter(pending_months))
    active = safe_str(st.session_state.get(ACTIVE_PLAN_MONTH_KEY))
    if active:
        return active
    selected = safe_str(st.session_state.get(SELECTED_PLANNING_MONTH_KEY))
    if selected:
        return selected
    month_filter = safe_str(st.session_state.get("saved_plans_filter_month"))
    if month_filter and month_filter != "Все":
        return month_filter
    _, month_key = resolve_draft_save_context(pending_items, project_filter)
    return month_key


def resolve_supplement_month_for_saved_plan(
    row: dict,
    lines: list[dict],
) -> str | None:
    selected = get_selected_planning_month()
    if selected:
        return selected
    month_filter = safe_str(st.session_state.get("saved_plans_filter_month"))
    if month_filter and month_filter != "Все":
        return month_filter
    header_month = safe_str(row.get("month_key"))
    if header_month and header_month.upper() != "MIXED":
        return header_month
    line_months = {
        safe_str(line.get("month_key"))
        for line in lines
        if safe_str(line.get("month_key"))
    }
    if len(line_months) == 1:
        return next(iter(line_months))
    return None


def _draft_header_fields(draft: list[dict], draft_status: str = "DRAFT") -> dict:
    project_values = {str(d.get("project_code") or "").strip() for d in draft if str(d.get("project_code") or "").strip()}
    month_values = {str(d.get("month_key") or "").strip() for d in draft if str(d.get("month_key") or "").strip()}
    if len(month_values) > 1:
        raise ValueError(
            "Нельзя сохранить один месячный черновик с разными месяцами. "
            "Разделите строки по месяцам."
        )
    project_code = next(iter(project_values), "")
    month_key = next(iter(month_values), "") if len(month_values) == 1 else ""
    total_plan_value = sum(safe_float(x.get("plan_value")) or 0.0 for x in draft)
    total_required_hours = sum(safe_float(x.get("required_hours")) or 0.0 for x in draft)
    total_labor_cost = sum(safe_float(x.get("labor_cost")) or 0.0 for x in draft)
    draft_comment = "; ".join([str(d.get("comment") or "").strip() for d in draft if str(d.get("comment") or "").strip()][:5]) or None
    return {
        "project_code": project_code or None,
        "month_key": month_key or None,
        "draft_status": draft_status,
        "draft_name": f"Monthly plan draft - {month_key or 'N/A'}",
        "total_plan_value": total_plan_value,
        "total_required_hours": total_required_hours,
        "total_labor_cost": total_labor_cost,
        "rows_count": len(draft),
        "comment": draft_comment,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_draft_line_payloads(draft_id: str, draft: list[dict], source_df: pd.DataFrame) -> list[dict]:
    line_payloads: list[dict] = []
    for item in draft:
        key_parts = draft_item_key_parts(item)
        src_row = source_row_by_key_parts(source_df, key_parts)
        unit_price = safe_float(src_row.get("unit_price")) if src_row is not None else safe_float(item.get("unit_price"))
        unit_price = unit_price or 0.0
        planning_remaining_qty = safe_float(src_row.get("planning_remaining_qty")) if src_row is not None else None
        already_reserved_qty = 0.0
        for other in draft:
            if draft_item_key_parts(other) == key_parts:
                if other is item:
                    break
                already_reserved_qty += safe_float(other.get("planned_qty")) or 0.0
        available_before = (planning_remaining_qty - already_reserved_qty) if planning_remaining_qty is not None else None
        planned_qty = safe_float(item.get("planned_qty")) or 0.0
        required_hours = safe_float(item.get("required_hours")) or 0.0
        selected_hpu = (required_hours / planned_qty) if planned_qty > 0 else 0.0
        labor_rate_per_hour = safe_float(item.get("labor_rate_per_hour")) or DEFAULT_LABOR_RATE_PER_HOUR
        labor_cost = safe_float(item.get("labor_cost")) or (required_hours * labor_rate_per_hour)
        line_payloads.append(
            {
                "draft_id": draft_id,
                "project_code": item.get("project_code"),
                "month_key": item.get("month_key"),
                "facility_building": item.get("facility_building"),
                "construction_discipline": item.get("construction_discipline"),
                "boq_code": item.get("boq_code"),
                "boq_name": item.get("boq_name"),
                "unit_of_measure": item.get("unit_of_measure"),
                "crew_id": item.get("crew_code"),
                "planned_qty": planned_qty,
                "unit_price": unit_price,
                "plan_value": safe_float(item.get("plan_value")) or (planned_qty * unit_price),
                "norm_scenario": item.get("norm_scenario"),
                "selected_hours_per_unit": selected_hpu,
                "required_hours": required_hours,
                "labor_rate_per_hour": labor_rate_per_hour,
                "labor_cost": labor_cost,
                "planning_remaining_qty": planning_remaining_qty,
                "already_reserved_qty": already_reserved_qty,
                "available_qty_before_add": available_before,
                "customer_accepted_qty": safe_float(item.get("customer_accepted_qty")),
                "line_status": "DRAFT",
                "comment": item.get("comment"),
            }
        )
    return line_payloads


def create_draft_in_supabase(draft: list[dict], source_df: pd.DataFrame) -> str:
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — запись черновика недоступна.")

    header_payload = _draft_header_fields(draft, draft_status="DRAFT")
    header_payload["created_by"] = "Streamlit"
    header_resp = write_client.table("monthly_plan_drafts").insert(header_payload).execute()
    if not header_resp.data:
        raise RuntimeError("Не удалось создать запись monthly_plan_drafts.")
    draft_id = str(header_resp.data[0].get("draft_id") or "")
    if not draft_id:
        raise RuntimeError("Не удалось получить draft_id после сохранения monthly_plan_drafts.")
    line_payloads = _build_draft_line_payloads(draft_id, draft, source_df)
    write_client.table("monthly_plan_draft_lines").insert(line_payloads).execute()
    return draft_id


def update_draft_in_supabase(
    draft_id: str,
    draft: list[dict],
    source_df: pd.DataFrame,
    draft_status: str | None = None,
) -> str:
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — запись черновика недоступна.")

    status = draft_status or str(st.session_state.get(LOADED_DRAFT_STATUS_KEY) or "DRAFT")
    if status not in ("DRAFT", "NEED_REVISION"):
        raise RuntimeError(f"Нельзя обновить черновик со статусом {status}.")

    header_payload = _draft_header_fields(draft, draft_status=status)
    write_client.table("monthly_plan_drafts").update(header_payload).eq("draft_id", draft_id).execute()
    write_client.table("monthly_plan_draft_lines").delete().eq("draft_id", draft_id).execute()
    line_payloads = _build_draft_line_payloads(draft_id, draft, source_df)
    if line_payloads:
        write_client.table("monthly_plan_draft_lines").insert(line_payloads).execute()
    return draft_id


def save_draft_to_supabase(
    draft: list[dict],
    source_df: pd.DataFrame,
    existing_draft_id: str | None = None,
) -> str:
    draft = resolve_draft_lines_for_save()
    if not draft:
        raise RuntimeError("Нет новых строк для сохранения.")
    if existing_draft_id:
        loaded_status = str(st.session_state.get(LOADED_DRAFT_STATUS_KEY) or "DRAFT")
        return update_draft_in_supabase(existing_draft_id, draft, source_df, draft_status=loaded_status)
    return create_draft_in_supabase(draft, source_df)


def line_db_to_session_item(line: dict) -> dict:
    scenario = str(line.get("norm_scenario") or NORM_SCENARIO_REALISTIC)
    planned_qty = safe_float(line.get("planned_qty")) or 0.0
    selected_hpu = safe_float(line.get("selected_hours_per_unit"))
    manual_norm = selected_hpu if scenario == NORM_SCENARIO_MANUAL else None
    return {
        "project_code": line.get("project_code"),
        "boq_code": line.get("boq_code"),
        "boq_name": line.get("boq_name"),
        "facility_building": line.get("facility_building"),
        "construction_discipline": line.get("construction_discipline"),
        "unit_of_measure": line.get("unit_of_measure"),
        "month_key": line.get("month_key"),
        "crew_code": line.get("crew_id"),
        "planned_qty": planned_qty,
        "unit_price": line.get("unit_price"),
        "plan_value": line.get("plan_value"),
        "norm_scenario": scenario,
        "manual_norm_value": manual_norm,
        "required_hours": line.get("required_hours"),
        "labor_rate_per_hour": line.get("labor_rate_per_hour") or DEFAULT_LABOR_RATE_PER_HOUR,
        "labor_cost": line.get("labor_cost"),
        "customer_accepted_qty": line.get("customer_accepted_qty"),
        "comment": line.get("comment"),
        "line_scope_note": "",
    }


def load_draft_lines_as_items(draft_id: str) -> list[dict]:
    resp = (
        supabase.table("monthly_plan_draft_lines")
        .select("*")
        .eq("draft_id", draft_id)
        .limit(10000)
        .execute()
    )
    return [line_db_to_session_item(row) for row in (resp.data or [])]


def load_monthly_plan_drafts(status_filter: str) -> pd.DataFrame:
    try:
        query = (
            supabase.table("monthly_plan_drafts")
            .select(
                "draft_id,created_at,project_code,month_key,draft_status,draft_name,"
                "rows_count,total_plan_value,total_required_hours,total_labor_cost"
            )
            .order("created_at", desc=True)
            .limit(500)
        )
        if status_filter and status_filter != "Все":
            query = query.eq("draft_status", status_filter)
        resp = query.execute()
        return pd.DataFrame(resp.data or [])
    except Exception:
        return pd.DataFrame()


def resolve_draft_save_context(
    draft: list[dict],
    project_filter: str,
) -> tuple[str | None, str | None]:
    """project_code + month_key для проверки дубликата черновика (без новой модели месяца)."""
    project_values = {
        safe_str(d.get("project_code"))
        for d in draft
        if safe_str(d.get("project_code"))
    }
    if len(project_values) == 1:
        project_code = next(iter(project_values))
    elif project_filter and project_filter != "Все":
        project_code = str(project_filter).strip()
    else:
        project_code = None

    month_values = {
        safe_str(d.get("month_key"))
        for d in draft
        if safe_str(d.get("month_key"))
    }
    if len(month_values) == 1:
        month_key = next(iter(month_values))
    elif not draft:
        month_options = build_month_key_options()
        month_key = month_options[0] if month_options else None
    else:
        month_key = None

    return project_code, month_key


@st.cache_data(ttl=60)
def find_monthly_plan_for_project_month(
    project_code: str,
    month_key: str,
) -> dict | None:
    """Последний план месяца (DRAFT → NEED_REVISION → SENT_TO_REVIEW → APPROVED)."""
    if not project_code or not month_key:
        return None
    try:
        resp = (
            supabase.table("monthly_plan_drafts")
            .select("draft_id,draft_status,project_code,month_key,created_at")
            .eq("project_code", project_code)
            .eq("month_key", month_key)
            .in_("draft_status", list(MONTHLY_PLAN_GUARD_STATUSES))
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        rows = resp.data or []
        if rows:
            return _pick_best_monthly_plan_row(rows)

        lines_resp = (
            supabase.table("monthly_plan_draft_lines")
            .select("draft_id")
            .eq("project_code", project_code)
            .eq("month_key", month_key)
            .limit(1000)
            .execute()
        )
        draft_ids = sorted(
            {
                safe_str(row.get("draft_id"))
                for row in (lines_resp.data or [])
                if safe_str(row.get("draft_id"))
            }
        )
        if not draft_ids:
            return None
        legacy_resp = (
            supabase.table("monthly_plan_drafts")
            .select("draft_id,draft_status,project_code,month_key,created_at")
            .in_("draft_id", draft_ids)
            .eq("project_code", project_code)
            .in_("draft_status", list(MONTHLY_PLAN_GUARD_STATUSES))
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return _pick_best_monthly_plan_row(legacy_resp.data or [])
    except Exception:  # noqa: BLE001
        return None


def find_active_draft_for_project_month(
    project_code: str,
    month_key: str,
) -> dict | None:
    """Обратная совместимость: только редактируемые черновики."""
    plan = find_monthly_plan_for_project_month(project_code, month_key)
    if plan and safe_str(plan.get("draft_status")) in ("DRAFT", "NEED_REVISION"):
        return plan
    return None


def merge_pending_draft_items(pending_items: list[dict]) -> None:
    merged = list(st.session_state.get(DRAFT_KEY, []))
    known_uids = {draft_line_uid(x) for x in merged}
    for item in pending_items:
        uid = draft_line_uid(item)
        if uid not in known_uids:
            merged.append(item)
            known_uids.add(uid)
    st.session_state[DRAFT_KEY] = merged


def merged_monthly_plan_view() -> list[dict]:
    base = [
        {**item, "line_source": "BASE"}
        for item in st.session_state.get(BASE_DRAFT_LINES_KEY, [])
    ]
    additions = [
        {**item, "line_source": "ADDITION"}
        for item in st.session_state.get(DRAFT_KEY, [])
    ]
    return base + additions


def unified_plan_month_label(items: list[dict]) -> str:
    month_values = {
        safe_str(x.get("month_key"))
        for x in items
        if safe_str(x.get("month_key"))
    }
    if len(month_values) == 1:
        return next(iter(month_values))
    return "—"


def session_boq_item_in_items(items: list[dict], row: pd.Series, month_key: str) -> dict | None:
    target_key = boq_key_parts_from_row(row)
    target_month = safe_str(month_key)
    for item in items:
        if draft_item_key_parts(item) != target_key:
            continue
        if target_month and safe_str(item.get("month_key")) != target_month:
            continue
        return item
    return None


def begin_new_version_from_plan(
    source_draft_id: str,
    pending_items: list[dict],
    project_filter: str = "",
) -> None:
    active_month_key = resolve_supplement_active_month_key(pending_items, project_filter)
    start_new_draft_version(source_draft_id, active_month_key=active_month_key)
    if pending_items:
        merge_pending_draft_items(pending_items)


@st.cache_data(ttl=60)
def find_boq_in_monthly_plans(
    project_code: str,
    month_key: str,
    facility_building: str,
    construction_discipline: str,
    boq_code: str,
    exclude_draft_id: str = "",
) -> list[dict]:
    if not all([project_code, month_key, boq_code]):
        return []
    try:
        drafts_resp = (
            supabase.table("monthly_plan_drafts")
            .select("draft_id,draft_status")
            .eq("project_code", project_code)
            .eq("month_key", month_key)
            .in_("draft_status", list(MONTHLY_PLAN_GUARD_STATUSES))
            .limit(100)
            .execute()
        )
        status_by_id = {
            safe_str(r.get("draft_id")): safe_str(r.get("draft_status"))
            for r in (drafts_resp.data or [])
            if safe_str(r.get("draft_id"))
        }
        draft_ids = [
            did
            for did in status_by_id
            if did and did != str(exclude_draft_id or "")
        ]
        if not draft_ids:
            return []
        lines_resp = (
            supabase.table("monthly_plan_draft_lines")
            .select("draft_id,planned_qty,boq_code,facility_building,construction_discipline")
            .in_("draft_id", draft_ids)
            .eq("boq_code", boq_code)
            .eq("facility_building", facility_building)
            .eq("construction_discipline", construction_discipline)
            .limit(500)
            .execute()
        )
        hits: list[dict] = []
        for line in lines_resp.data or []:
            did = safe_str(line.get("draft_id"))
            hits.append(
                {
                    "draft_id": did,
                    "draft_status": status_by_id.get(did, "—"),
                    "planned_qty": safe_float(line.get("planned_qty")) or 0.0,
                }
            )
        return hits
    except Exception:  # noqa: BLE001
        return []


def session_draft_item_for_boq(row: pd.Series, month_key: str) -> dict | None:
    target_key = boq_key_parts_from_row(row)
    target_month = safe_str(month_key)
    for item in st.session_state.get(DRAFT_KEY, []):
        if draft_item_key_parts(item) != target_key:
            continue
        if target_month and safe_str(item.get("month_key")) != target_month:
            continue
        return item
    return None


def render_boq_add_duplicate_hints(
    row: pd.Series,
    plan_month: str,
    project_remaining: float,
    already_planned: float,
    available_to_add_qty: float,
) -> None:
    project_code = safe_str(row.get("project_code"))
    month_key = safe_str(plan_month)
    boq_code = safe_str(row.get("boq_code"))
    facility = safe_str(row.get("facility_building"))
    discipline = safe_str(row.get("construction_discipline"))
    exclude_id = safe_str(st.session_state.get(SAVED_DRAFT_ID_KEY))

    in_addition = session_draft_item_for_boq(row, month_key)
    in_base = session_boq_item_in_items(
        st.session_state.get(BASE_DRAFT_LINES_KEY, []),
        row,
        month_key,
    )
    db_hits: list[dict] = []
    if project_code and month_key and boq_code:
        db_hits = find_boq_in_monthly_plans(
            project_code,
            month_key,
            facility,
            discipline,
            boq_code,
            exclude_draft_id=exclude_id,
        )

    if in_addition or in_base or db_hits:
        st.warning(
            "BOQ уже присутствует в месячном плане. "
            "Добавляйте только дополнительный объём."
        )

    st.caption(
        f"Уже запланировано в месяце: {qty_fmt(already_planned)} / "
        f"Остаток: {qty_fmt(project_remaining)} / "
        f"Доступно к добавлению: {qty_fmt(available_to_add_qty)}"
    )


def render_active_draft_status_banner(project_filter: str = "Все") -> None:
    selected_month = get_selected_planning_month()
    new_count = len(get_new_session_lines_for_month(selected_month, project_filter))
    saved_id = safe_str(st.session_state.get(SAVED_DRAFT_ID_KEY))
    if saved_id:
        st.caption(f"Черновик сохранён · новых строк в {selected_month}: {new_count}")
    elif new_count:
        st.caption(f"Новых строк в {selected_month}: {new_count} (ещё не сохранены)")
    else:
        st.caption("Добавьте новые коды из карточки BOQ.")


def open_draft_in_constructor(draft_id: str, draft_status: str, *, view_only: bool) -> None:
    items = load_draft_lines_as_items(draft_id)
    st.session_state[DRAFT_KEY] = items
    st.session_state[BASE_DRAFT_LINES_KEY] = []
    st.session_state[SAVED_DRAFT_ID_KEY] = draft_id
    st.session_state[LOADED_DRAFT_STATUS_KEY] = draft_status
    st.session_state[DRAFT_VIEW_ONLY_KEY] = view_only
    st.session_state[DRAFT_EDIT_MODE_KEY] = False
    if not view_only:
        st.session_state[SOURCE_DRAFT_ID_KEY] = None


def start_new_draft_version(source_draft_id: str, active_month_key: str | None = None) -> None:
    all_items = load_draft_lines_as_items(source_draft_id)
    if active_month_key:
        items = filter_lines_by_month_key(all_items, active_month_key)
        st.session_state[ACTIVE_PLAN_MONTH_KEY] = active_month_key
    else:
        items = all_items
        st.session_state.pop(ACTIVE_PLAN_MONTH_KEY, None)
        try:
            header_resp = (
                supabase.table("monthly_plan_drafts")
                .select("month_key")
                .eq("draft_id", source_draft_id)
                .limit(1)
                .execute()
            )
            header_month = safe_str((header_resp.data or [{}])[0].get("month_key"))
        except Exception:  # noqa: BLE001
            header_month = ""
        line_months = {
            safe_str(x.get("month_key"))
            for x in all_items
            if safe_str(x.get("month_key"))
        }
        if header_month.upper() == "MIXED" or len(line_months) > 1:
            st.session_state["legacy_mixed_draft_warning"] = True

    st.session_state[BASE_DRAFT_LINES_KEY] = items
    st.session_state[DRAFT_KEY] = []
    st.session_state[SAVED_DRAFT_ID_KEY] = None
    st.session_state[SOURCE_DRAFT_ID_KEY] = source_draft_id
    st.session_state[LOADED_DRAFT_STATUS_KEY] = "DRAFT"
    st.session_state[DRAFT_VIEW_ONLY_KEY] = False
    st.session_state[DRAFT_EDIT_MODE_KEY] = False
    st.session_state["new_version_info"] = True


def cancel_draft_record(draft_id: str) -> None:
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — отмена черновика недоступна.")
    write_client.table("monthly_plan_drafts").update(
        {"draft_status": "CANCELLED", "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("draft_id", draft_id).execute()


def revoke_draft_from_review(draft_id: str) -> None:
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — отзыв недоступен.")
    write_client.table("monthly_plan_drafts").update(
        {"draft_status": "NEED_REVISION", "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("draft_id", draft_id).execute()
    write_client.table("monthly_plan_review_queue").update(
        {"review_status": "ОТОЗВАНО НА ДОРАБОТКУ"}
    ).eq("draft_id", draft_id).execute()


def _delete_count_rows(response: Any) -> int:
    data = getattr(response, "data", None)
    if isinstance(data, list):
        return len(data)
    return 0


def _is_missing_column_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "does not exist" in msg or ("column" in msg and "unknown" in msg)


# Поля monthly_plan_review_queue, используемые в этом файле (insert/select/update):
# draft_id, line_id, project_code, month_key, facility_building, construction_discipline,
# boq_code, boq_name, crew_id, planned_qty, plan_value, required_hours, labor_rate_per_hour,
# labor_cost, review_status, check_*_status. Колонки id / source_line_id / plan_line_id
# в коде не используются. review_id — в constraints_service и passport; в insert очереди нет.
REVIEW_QUEUE_DELETE_FIELDS = ("line_id", "review_id")


def _fetch_review_queue_link_ids(client: Client, draft_id: str) -> tuple[list[str], list[str]]:
    """Читает line_id/review_id очереди по draft_id; пропускает отсутствующие колонки."""
    line_ids: list[str] = []
    review_ids: list[str] = []
    select_variants = (
        ",".join(REVIEW_QUEUE_DELETE_FIELDS),
        "line_id",
        "*",
    )
    for cols in select_variants:
        try:
            resp = (
                client.table("monthly_plan_review_queue")
                .select(cols)
                .eq("draft_id", draft_id)
                .limit(10000)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            if _is_missing_column_error(exc):
                continue
            break
        for row in resp.data or []:
            lid = str(row.get("line_id") or "").strip()
            if lid:
                line_ids.append(lid)
            rid = str(row.get("review_id") or "").strip()
            if rid:
                review_ids.append(rid)
        break
    return line_ids, review_ids


def _delete_constraints_for_draft(
    client: Client,
    draft_id: str,
    draft_line_ids: list[str],
    review_line_ids: list[str],
    review_ids: list[str],
) -> int:
    """
    Удаляет constraints только для выбранного draft_id.
    Каждый способ в try/except; отсутствие колонки — не fatal.
    """
    deleted = 0
    chunk_size = 200
    line_ids_union = list(
        dict.fromkeys(
            [lid for lid in draft_line_ids + review_line_ids if lid]
        )
    )

    try:
        resp = (
            client.table("monthly_plan_constraints")
            .delete()
            .eq("draft_id", draft_id)
            .execute()
        )
        deleted += _delete_count_rows(resp)
    except Exception as exc:  # noqa: BLE001
        if not _is_missing_column_error(exc):
            pass

    if line_ids_union:
        for offset in range(0, len(line_ids_union), chunk_size):
            chunk = line_ids_union[offset : offset + chunk_size]
            try:
                resp = (
                    client.table("monthly_plan_constraints")
                    .delete()
                    .eq("draft_id", draft_id)
                    .in_("line_id", chunk)
                    .execute()
                )
                deleted += _delete_count_rows(resp)
            except Exception as exc:  # noqa: BLE001
                if _is_missing_column_error(exc):
                    try:
                        resp = (
                            client.table("monthly_plan_constraints")
                            .delete()
                            .in_("line_id", chunk)
                            .execute()
                        )
                        deleted += _delete_count_rows(resp)
                    except Exception:  # noqa: BLE001
                        pass

            for link_field in ("source_line_id", "plan_line_id"):
                try:
                    resp = (
                        client.table("monthly_plan_constraints")
                        .delete()
                        .eq("draft_id", draft_id)
                        .in_(link_field, chunk)
                        .execute()
                    )
                    deleted += _delete_count_rows(resp)
                except Exception:  # noqa: BLE001
                    continue

    unique_review_ids = list(dict.fromkeys(review_ids))
    if unique_review_ids:
        for offset in range(0, len(unique_review_ids), chunk_size):
            chunk = unique_review_ids[offset : offset + chunk_size]
            try:
                resp = (
                    client.table("monthly_plan_constraints")
                    .delete()
                    .eq("draft_id", draft_id)
                    .in_("review_id", chunk)
                    .execute()
                )
                deleted += _delete_count_rows(resp)
            except Exception as exc:  # noqa: BLE001
                if _is_missing_column_error(exc):
                    try:
                        resp = (
                            client.table("monthly_plan_constraints")
                            .delete()
                            .in_("review_id", chunk)
                            .execute()
                        )
                        deleted += _delete_count_rows(resp)
                    except Exception:  # noqa: BLE001
                        pass

    for queue_link_field in ("review_queue_id",):
        try:
            resp = (
                client.table("monthly_plan_constraints")
                .delete()
                .eq("draft_id", draft_id)
                .in_(queue_link_field, unique_review_ids)
                .execute()
            )
            deleted += _delete_count_rows(resp)
        except Exception:  # noqa: BLE001
            continue

    return deleted


def _draft_has_approved_passport(client: Client, draft_id: str, line_ids: list[str]) -> bool:
    try:
        by_draft = (
            client.table("monthly_plan_passports")
            .select("passport_id")
            .eq("draft_id", draft_id)
            .eq("passport_status", "APPROVED")
            .limit(1)
            .execute()
        )
        if by_draft.data:
            return True
    except Exception:  # noqa: BLE001
        return True

    if not line_ids:
        return False

    chunk_size = 200
    for offset in range(0, len(line_ids), chunk_size):
        chunk = line_ids[offset : offset + chunk_size]
        try:
            lines_resp = (
                client.table("monthly_plan_passport_lines")
                .select("passport_id")
                .in_("line_id", chunk)
                .limit(10000)
                .execute()
            )
        except Exception:  # noqa: BLE001
            return True

        passport_ids = list(
            {
                str(row.get("passport_id") or "")
                for row in (lines_resp.data or [])
                if row.get("passport_id")
            }
        )
        if not passport_ids:
            continue

        for pid_offset in range(0, len(passport_ids), chunk_size):
            pid_chunk = passport_ids[pid_offset : pid_offset + chunk_size]
            try:
                approved_resp = (
                    client.table("monthly_plan_passports")
                    .select("passport_id")
                    .in_("passport_id", pid_chunk)
                    .eq("passport_status", "APPROVED")
                    .limit(1)
                    .execute()
                )
            except Exception:  # noqa: BLE001
                return True
            if approved_resp.data:
                return True
    return False


def delete_monthly_plan_draft_cascade(draft_id: str) -> dict[str, Any]:
    """
    Удаляет черновик и связанные записи строго по draft_id.
    Идемпотентен: повторный вызов для отсутствующего draft_id не падает.
    """
    draft_id = str(draft_id or "").strip()
    summary: dict[str, Any] = {
        "draft_id": draft_id,
        "deleted_constraints_count": 0,
        "deleted_review_queue_count": 0,
        "deleted_draft_lines_count": 0,
        "deleted_draft_count": 0,
        "skipped_reason": None,
    }
    if not draft_id:
        summary["skipped_reason"] = "Пустой draft_id"
        return summary

    write_client = get_supabase_write_client()
    if write_client is None:
        summary["skipped_reason"] = "SUPABASE_SECRET_KEY не задан в .env — удаление недоступно"
        return summary

    try:
        draft_resp = (
            write_client.table("monthly_plan_drafts")
            .select("draft_id,draft_status")
            .eq("draft_id", draft_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        summary["skipped_reason"] = f"Ошибка чтения черновика: {exc}"
        return summary

    draft_rows = draft_resp.data or []
    if not draft_rows:
        summary["skipped_reason"] = "Черновик не найден (возможно, уже удалён)"
        return summary

    draft_status = str(draft_rows[0].get("draft_status") or "")
    if draft_status == "APPROVED":
        summary["skipped_reason"] = "Статус APPROVED — удаление запрещено"
        return summary

    try:
        lines_resp = (
            write_client.table("monthly_plan_draft_lines")
            .select("line_id")
            .eq("draft_id", draft_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        summary["skipped_reason"] = f"Ошибка чтения строк черновика: {exc}"
        return summary

    line_ids = [
        str(row.get("line_id") or "")
        for row in (lines_resp.data or [])
        if str(row.get("line_id") or "").strip()
    ]

    if _draft_has_approved_passport(write_client, draft_id, line_ids):
        summary["skipped_reason"] = (
            "Есть утверждённый Monthly Plan Passport, связанный с этим draft_id"
        )
        return summary

    review_line_ids, review_ids = _fetch_review_queue_link_ids(write_client, draft_id)
    summary["deleted_constraints_count"] = _delete_constraints_for_draft(
        write_client,
        draft_id,
        line_ids,
        review_line_ids,
        review_ids,
    )

    try:
        rq_del = (
            write_client.table("monthly_plan_review_queue")
            .delete()
            .eq("draft_id", draft_id)
            .execute()
        )
        summary["deleted_review_queue_count"] = _delete_count_rows(rq_del)
    except Exception as exc:  # noqa: BLE001
        summary["skipped_reason"] = f"Ошибка удаления очереди допуска: {exc}"
        return summary

    try:
        lines_del = (
            write_client.table("monthly_plan_draft_lines")
            .delete()
            .eq("draft_id", draft_id)
            .execute()
        )
        summary["deleted_draft_lines_count"] = _delete_count_rows(lines_del)
    except Exception as exc:  # noqa: BLE001
        summary["skipped_reason"] = f"Ошибка удаления строк черновика: {exc}"
        return summary

    try:
        draft_del = (
            write_client.table("monthly_plan_drafts")
            .delete()
            .eq("draft_id", draft_id)
            .execute()
        )
        summary["deleted_draft_count"] = _delete_count_rows(draft_del)
    except Exception as exc:  # noqa: BLE001
        summary["skipped_reason"] = f"Ошибка удаления черновика: {exc}"
        return summary

    if summary["deleted_draft_count"] == 0:
        summary["skipped_reason"] = "Запись monthly_plan_drafts не удалена"
    return summary


def clear_session_if_deleted_draft(deleted_draft_ids: list[str]) -> None:
    deleted_set = {str(d) for d in deleted_draft_ids if d}
    if not deleted_set:
        return
    current_id = str(st.session_state.get(SAVED_DRAFT_ID_KEY) or "")
    source_id = str(st.session_state.get(SOURCE_DRAFT_ID_KEY) or "")
    if current_id in deleted_set:
        st.session_state[SAVED_DRAFT_ID_KEY] = None
        st.session_state[LOADED_DRAFT_STATUS_KEY] = None
        st.session_state[DRAFT_VIEW_ONLY_KEY] = False
        st.session_state[DRAFT_EDIT_MODE_KEY] = False
        st.session_state[DRAFT_KEY] = []
        st.session_state[BASE_DRAFT_LINES_KEY] = []
    if source_id in deleted_set:
        st.session_state[SOURCE_DRAFT_ID_KEY] = None
        st.session_state[BASE_DRAFT_LINES_KEY] = []


def saved_draft_delete_label(row: dict) -> str:
    created = _format_draft_created_at(row.get("created_at"))
    status = str(row.get("status_label") or row.get("draft_status") or "—")
    title = str(row.get("facility_label") or "—")
    month = str(row.get("month_label") or "—")
    discipline = str(row.get("discipline_label") or "—")
    line_count = int(row.get("rows_count") or 0)
    total_cost = money_ru(row.get("total_plan_value"))
    did = str(row.get("draft_id") or "")
    return (
        f"{created} | {status} | {title} | {month} | {discipline} | "
        f"строк: {line_count} | сумма: {total_cost} | draft_id: {did}"
    )


def saved_draft_preview_row(row: dict) -> dict:
    month_label = str(row.get("month_label") or "—")
    facility_label = str(row.get("facility_label") or "—")
    discipline_label = str(row.get("discipline_label") or "—")
    month_key = str(row.get("month_key") or "").strip()
    month_display = month_label
    if month_key and month_key.upper() != "MIXED" and month_label not in ("—", month_key):
        month_display = f"{month_label} ({month_key})"
    elif month_key and month_key.upper() == "MIXED":
        month_display = f"{month_label} (month_key: MIXED)"
    return {
        "draft_id": str(row.get("draft_id") or ""),
        "project_code": str(row.get("project_code") or "—"),
        "Месяц (сводка)": month_display,
        "Титул (сводка)": facility_label,
        "Дисциплина (сводка)": discipline_label,
        "draft_status": str(row.get("draft_status") or "—"),
        "Строк": int(row.get("rows_count") or 0),
        "Плановая стоимость, ₽": money_ru(row.get("total_plan_value")),
        "Создан": _format_draft_created_at(row.get("created_at")),
    }


def build_saved_drafts_preview_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=SAVED_DRAFT_DELETE_PREVIEW_COLUMNS)
    preview = pd.DataFrame([saved_draft_preview_row(row) for row in rows])
    return preview.reindex(columns=SAVED_DRAFT_DELETE_PREVIEW_COLUMNS)


def maybe_supersede_source_draft(source_draft_id: str) -> None:
    write_client = get_supabase_write_client()
    if write_client is None or not source_draft_id:
        return
    src_resp = (
        write_client.table("monthly_plan_drafts")
        .select("draft_status")
        .eq("draft_id", source_draft_id)
        .limit(1)
        .execute()
    )
    rows = src_resp.data or []
    if not rows:
        return
    status = str(rows[0].get("draft_status") or "")
    if status in ("SENT_TO_REVIEW", "APPROVED"):
        write_client.table("monthly_plan_drafts").update(
            {"draft_status": "SUPERSEDED", "updated_at": datetime.now(timezone.utc).isoformat()}
        ).eq("draft_id", source_draft_id).execute()


def send_draft_to_review_queue(
    draft_id: str,
    source_draft_id: str | None = None,
) -> dict[str, Any]:
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — отправка в контур недоступна.")

    header_resp = (
        write_client.table("monthly_plan_drafts")
        .select("draft_status,rows_count")
        .eq("draft_id", draft_id)
        .limit(1)
        .execute()
    )
    header_rows = header_resp.data or []
    if not header_rows:
        raise RuntimeError("Черновик для отправки не найден.")
    draft_status = safe_str(header_rows[0].get("draft_status"))
    if draft_status not in SENDABLE_DRAFT_STATUSES:
        raise RuntimeError(
            f"Нельзя отправить черновик со статусом {draft_status}. "
            "Сохраните новые строки как отдельный черновик дополнения."
        )
    if source_draft_id and draft_id == source_draft_id:
        raise RuntimeError(
            "Нельзя повторно отправить исходный план. Сохраните черновик дополнения с новыми строками."
        )

    lines_resp = (
        write_client.table("monthly_plan_draft_lines")
        .select("*")
        .eq("draft_id", draft_id)
        .execute()
    )
    lines = lines_resp.data or []
    if not lines:
        raise RuntimeError("Не найдены строки monthly_plan_draft_lines для выбранного draft_id.")

    queue_payloads = []
    for line in lines:
        queue_payloads.append(
            {
                "draft_id": draft_id,
                "line_id": line.get("line_id"),
                "project_code": line.get("project_code"),
                "month_key": line.get("month_key"),
                "facility_building": line.get("facility_building"),
                "construction_discipline": line.get("construction_discipline"),
                "boq_code": line.get("boq_code"),
                "boq_name": line.get("boq_name"),
                "crew_id": line.get("crew_id"),
                "planned_qty": line.get("planned_qty"),
                "plan_value": line.get("plan_value"),
                "required_hours": line.get("required_hours"),
                "labor_rate_per_hour": line.get("labor_rate_per_hour"),
                "labor_cost": line.get("labor_cost"),
                "review_status": "ОЖИДАЕТ ПРОВЕРКИ",
                "check_boq_remaining_status": "ОЖИДАЕТ",
                "check_norm_status": "ОЖИДАЕТ",
                "check_crew_capacity_status": "ОЖИДАЕТ",
                "check_front_readiness_status": "ОЖИДАЕТ",
                "check_acceptability_status": "ОЖИДАЕТ",
            }
        )
    write_client.table("monthly_plan_review_queue").insert(queue_payloads).execute()
    (
        write_client.table("monthly_plan_drafts")
        .update({"draft_status": "SENT_TO_REVIEW", "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("draft_id", draft_id)
        .execute()
    )
    if source_draft_id:
        maybe_supersede_source_draft(source_draft_id)

    try:
        constraints_summary = create_constraints_for_review_queue(draft_id=draft_id)
    except Exception as exc:  # noqa: BLE001
        constraints_summary = {
            "created_count": 0,
            "skipped_count": 0,
            "source_rows_count": len(queue_payloads),
            "errors": [str(exc)],
        }
    return constraints_summary


def constraints_auto_create_succeeded(summary: dict[str, Any]) -> bool:
    if summary.get("errors"):
        return False
    created = int(summary.get("created_count") or 0)
    skipped = int(summary.get("skipped_count") or 0)
    source_rows = int(summary.get("source_rows_count") or 0)
    if created > 0 or skipped > 0:
        return True
    return source_rows == 0


def load_review_queue_rows(draft_id: str) -> pd.DataFrame:
    if not draft_id:
        return pd.DataFrame()
    try:
        resp = (
            supabase.table("monthly_plan_review_queue")
            .select("*")
            .eq("draft_id", draft_id)
            .limit(10000)
            .execute()
        )
        return pd.DataFrame(resp.data or [])
    except Exception:
        return pd.DataFrame()


def render_review_queue_block(draft_id: str) -> None:
    if not draft_id:
        return
    review_df_raw = load_review_queue_rows(draft_id)
    if review_df_raw.empty:
        return
    st.caption("Контур допуска и проверки (текущий черновик)")
    review_df = pd.DataFrame(
        {
            "Код": [r.get("boq_code") for _, r in review_df_raw.iterrows()],
            "Титул": [r.get("facility_building") for _, r in review_df_raw.iterrows()],
            "Дисциплина": [r.get("construction_discipline") for _, r in review_df_raw.iterrows()],
            "Месяц": [r.get("month_key") for _, r in review_df_raw.iterrows()],
            "Звено": [r.get("crew_id") for _, r in review_df_raw.iterrows()],
            "Объём": [qty_fmt(r.get("planned_qty")) for _, r in review_df_raw.iterrows()],
            "Требуемые чел-часы": [hours_fmt(r.get("required_hours")) for _, r in review_df_raw.iterrows()],
            "Стоимость трудозатрат": [money(r.get("labor_cost")) for _, r in review_df_raw.iterrows()],
            "Статус проверки": [r.get("review_status") for _, r in review_df_raw.iterrows()],
            "Требуемые проверки": [
                "Проверка остатка BoQ, Проверка нормы, Проверка мощности звена, "
                "Проверка исполнимости фронта, Проверка признаваемости"
                for _ in range(len(review_df_raw))
            ],
        }
    )
    st.dataframe(review_df, use_container_width=True, hide_index=True, height=min(260, 36 + len(review_df) * 32))
    with st.expander("Что происходит после отправки?"):
        st.markdown(
            """
            1. Проверка остатка по BoQ: не превышает ли план подтверждённый остаток.
            2. Проверка исторической нормы: есть ли данные P50/P80 или нужна ручная норма.
            3. Проверка мощности звена: хватает ли человеко-часов.
            4. Проверка исполнимости фронта: РД, МТР, доступ, смежники, допуски.
            5. Проверка признаваемости: можно ли будет предъявить объём к КС/приёмке.
            6. Передача в AI Диагностику плана и AI Action Engine.
            """
        )


def draft_status_filter_label(code: str) -> str:
    if code == "Все":
        return "Все"
    return f"{code} · {DRAFT_STATUS_RU.get(code, code)}"


def parse_draft_status_filter(label: str) -> str:
    if label == "Все":
        return "Все"
    if " · " in label:
        return label.split(" · ", 1)[0].strip()
    return label.strip()


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def summarize_list_short(items: list[str], max_show: int, *, name_mode: bool = False) -> str:
    unique = _unique_preserve_order(items)
    if not unique:
        return "—"
    max_len = 50 if name_mode else 32
    shown_parts: list[str] = []
    for text in unique[:max_show]:
        part = str(text).strip()
        if name_mode and len(part) > max_len:
            part = part[: max_len - 1].rstrip() + "…"
        shown_parts.append(part)
    result = ", ".join(shown_parts)
    rest = len(unique) - len(shown_parts)
    if rest > 0:
        result += f" … ещё {rest}"
    return result


def load_draft_lines_by_drafts(draft_ids: list[str]) -> dict[str, list[dict]]:
    if not draft_ids:
        return {}
    try:
        resp = (
            supabase.table("monthly_plan_draft_lines")
            .select(
                "draft_id,boq_code,boq_name,unit_of_measure,facility_building,construction_discipline,"
                "month_key,crew_id,planned_qty,plan_value,required_hours,labor_rate_per_hour,labor_cost,"
                "norm_scenario,line_status,comment"
            )
            .in_("draft_id", draft_ids)
            .limit(10000)
            .execute()
        )
    except Exception:
        return {}
    grouped: dict[str, list[dict]] = {}
    for row in resp.data or []:
        did = str(row.get("draft_id") or "")
        if did:
            grouped.setdefault(did, []).append(row)
    return grouped


def norm_scenario_display(value) -> str:
    code = str(value or "").strip()
    mapping = {
        NORM_SCENARIO_REALISTIC: NORM_SCENARIO_REALISTIC,
        NORM_SCENARIO_CAUTIOUS: NORM_SCENARIO_CAUTIOUS,
        NORM_SCENARIO_MANUAL: NORM_SCENARIO_MANUAL,
        "P50": NORM_SCENARIO_REALISTIC,
        "P80": NORM_SCENARIO_CAUTIOUS,
        "Реалистичная норма": NORM_SCENARIO_REALISTIC,
        "Осторожная норма": NORM_SCENARIO_CAUTIOUS,
        "Ручная норма": NORM_SCENARIO_MANUAL,
    }
    return mapping.get(code, code or "—")


def build_draft_lines_detail_df(lines: list[dict]) -> pd.DataFrame:
    if not lines:
        return pd.DataFrame(columns=SAVED_PLAN_DETAIL_COLUMNS)

    def line_scope_from_db(line: dict) -> str:
        note = str(line.get("line_scope_note") or "").strip()
        if note:
            return note
        comment = str(line.get("comment") or "").strip()
        return comment or "—"

    detail = pd.DataFrame(
        {
            "Код BOQ": [line.get("boq_code") or "—" for line in lines],
            "Наименование работы": [line.get("boq_name") or "—" for line in lines],
            "Ед. изм.": [line.get("unit_of_measure") or "—" for line in lines],
            "Титул": [line.get("facility_building") or "—" for line in lines],
            "Дисциплина": [line.get("construction_discipline") or "—" for line in lines],
            "Месяц": [line.get("month_key") or "—" for line in lines],
            "Звено": [line.get("crew_id") or "—" for line in lines],
            "Задача / зона / помещение": [line_scope_from_db(line) for line in lines],
            "Объём": [qty_fmt(line.get("planned_qty")) for line in lines],
            "Плановая стоимость, ₽": [money(line.get("plan_value")) for line in lines],
            "Требуется чел-ч": [hours_fmt(line.get("required_hours")) for line in lines],
            "Норма": [
                norm_productivity_fmt(
                    line.get("planned_qty"),
                    line.get("required_hours"),
                    line.get("unit_of_measure") or "",
                )
                for line in lines
            ],
            "Стоимость трудозатрат, ₽": [money(line.get("labor_cost")) for line in lines],
            "Сценарий нормы": [norm_scenario_display(line.get("norm_scenario")) for line in lines],
            "Статус строки": [line.get("line_status") or "—" for line in lines],
        }
    )
    return detail.reindex(columns=SAVED_PLAN_DETAIL_COLUMNS)


def saved_plan_month_label(header_month: str, lines: list[dict]) -> str:
    month_values = _unique_preserve_order(_line_field_values(lines, "month_key"))
    header = str(header_month or "").strip()
    if header.upper() == "MIXED" or len(month_values) > 1:
        return "Несколько месяцев"
    if header and header.upper() != "MIXED":
        return header
    if len(month_values) == 1:
        return month_values[0]
    return "—"


def saved_plan_field_label(values: list[str], *, several_label: str, max_show: int = 2) -> str:
    unique = _unique_preserve_order(values)
    if not unique:
        return "—"
    if len(unique) == 1:
        return unique[0]
    if len(unique) > max_show:
        return several_label
    return ", ".join(unique)


def saved_plan_expander_title(row: dict, lines: list[dict]) -> str:
    line_count = int(row.get("rows_count") or len(lines) or 0)
    return (
        f"{row.get('month_label') or '—'} · {row.get('facility_label') or '—'} · "
        f"{row.get('discipline_label') or '—'} · {row.get('status_label') or '—'} · "
        f"строк: {line_count} · план: {money_ru(row.get('total_plan_value'))}"
    )


def aggregate_field_label(values: list[str], *, several_label: str) -> str:
    unique = _unique_preserve_order(values)
    if not unique:
        return "—"
    if len(unique) == 1:
        return unique[0]
    return several_label


def summarize_summary_field(values: list[str], *, max_show: int = 2) -> str:
    unique = _unique_preserve_order(values)
    if not unique:
        return "—"
    if len(unique) <= max_show:
        return ", ".join(unique)
    shown = ", ".join(unique[:max_show])
    rest = len(unique) - max_show
    return f"{shown} … ещё {rest}"


def _line_field_values(lines: list[dict], field: str) -> list[str]:
    return [str(line.get(field) or "").strip() for line in lines if str(line.get(field) or "").strip()]


def _first_sort_key(lines: list[dict], field: str) -> str:
    unique = _unique_preserve_order(_line_field_values(lines, field))
    if not unique:
        return ""
    return sorted(unique, key=lambda x: x.casefold())[0]


def month_sort_key(month_value) -> int:
    text = str(month_value or "").strip()
    try:
        return MONTH_KEY_ORDER.index(text)
    except ValueError:
        return len(MONTH_KEY_ORDER)


def enrich_saved_plans_view(
    drafts_df: pd.DataFrame,
    lines_by_draft: dict[str, list[dict]],
) -> pd.DataFrame:
    if drafts_df.empty:
        return pd.DataFrame()

    records: list[dict] = []
    for _, row in drafts_df.iterrows():
        draft_id = str(row.get("draft_id") or "")
        lines = lines_by_draft.get(draft_id, [])
        facility_values = _line_field_values(lines, "facility_building")
        discipline_values = _line_field_values(lines, "construction_discipline")
        header_month = str(row.get("month_key") or "")
        month_label = saved_plan_month_label(header_month, lines)
        facility_label = saved_plan_field_label(
            facility_values, several_label="Несколько титулов", max_show=2
        )
        discipline_label = saved_plan_field_label(
            discipline_values, several_label="Несколько дисциплин", max_show=2
        )
        draft_status = str(row.get("draft_status") or "")
        records.append(
            {
                "draft_id": draft_id,
                "created_at": row.get("created_at"),
                "project_code": row.get("project_code"),
                "month_key": row.get("month_key"),
                "month_label": month_label,
                "draft_status": draft_status,
                "draft_name": row.get("draft_name"),
                "rows_count": row.get("rows_count"),
                "total_plan_value": row.get("total_plan_value"),
                "total_required_hours": row.get("total_required_hours"),
                "total_labor_cost": row.get("total_labor_cost"),
                "facility_label": facility_label,
                "discipline_label": discipline_label,
                "status_label": DRAFT_STATUS_RU.get(draft_status, draft_status),
                "_sort_month": month_sort_key(
                    _first_sort_key(lines, "month_key")
                    if header_month.upper() == "MIXED"
                    else row.get("month_key")
                ),
                "_sort_facility": _first_sort_key(lines, "facility_building"),
                "_sort_discipline": _first_sort_key(lines, "construction_discipline"),
                "_sort_created": pd.to_datetime(row.get("created_at"), utc=True, errors="coerce"),
            }
        )

    view_df = pd.DataFrame(records)
    return view_df.sort_values(
        by=["_sort_month", "_sort_facility", "_sort_discipline", "_sort_created"],
        ascending=[True, True, True, False],
        na_position="last",
    )


def filter_saved_plans_view(
    view_df: pd.DataFrame,
    lines_by_draft: dict[str, list[dict]],
    *,
    month_filter: str,
    facility_filter: str,
    discipline_filter: str,
    status_filter: str,
) -> pd.DataFrame:
    if view_df.empty:
        return view_df

    mask = pd.Series(True, index=view_df.index)
    if month_filter != "Все":
        mask &= view_df["month_key"].astype(str).str.strip().eq(month_filter)
    if status_filter != "Все":
        mask &= view_df["draft_status"].astype(str).str.strip().eq(status_filter)
    if facility_filter != "Все":
        matched: list[bool] = []
        for _, row in view_df.iterrows():
            lines = lines_by_draft.get(str(row.get("draft_id") or ""), [])
            facilities = set(_line_field_values(lines, "facility_building"))
            matched.append(facility_filter in facilities)
        mask &= pd.Series(matched, index=view_df.index)
    if discipline_filter != "Все":
        matched = []
        for _, row in view_df.iterrows():
            lines = lines_by_draft.get(str(row.get("draft_id") or ""), [])
            disciplines = set(_line_field_values(lines, "construction_discipline"))
            matched.append(discipline_filter in disciplines)
        mask &= pd.Series(matched, index=view_df.index)
    return view_df[mask].copy()


def saved_plans_filter_options(
    view_df: pd.DataFrame,
    lines_by_draft: dict[str, list[dict]],
    field: str,
) -> list[str]:
    if field == "month_key":
        values = [
            str(row.get("month_key") or "").strip()
            for _, row in view_df.iterrows()
            if str(row.get("month_key") or "").strip()
        ]
        return sorted(_unique_preserve_order(values), key=lambda x: (month_sort_key(x), x.casefold()))

    values: list[str] = []
    for _, row in view_df.iterrows():
        lines = lines_by_draft.get(str(row.get("draft_id") or ""), [])
        values.extend(_line_field_values(lines, field))
    return sorted(_unique_preserve_order(values), key=lambda x: x.casefold())


def _format_draft_created_at(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    text = str(value).strip()
    if not text:
        return "—"
    try:
        dt = pd.to_datetime(text, utc=True)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return text[:16]


def draft_applies_to_month(row: dict, lines: list[dict], month_key: str) -> bool:
    if not month_key:
        return False
    header = safe_str(row.get("month_key"))
    if header.upper() == "MIXED":
        return any(safe_str(line.get("month_key")) == month_key for line in lines)
    return header == month_key


def summarize_archive_for_month(
    view_df: pd.DataFrame,
    lines_by_draft: dict[str, list[dict]],
    month_key: str,
) -> dict:
    sent_count = 0
    draft_count = 0
    legacy_mixed = False
    if view_df.empty or not month_key:
        return {
            "sent_count": 0,
            "draft_count": 0,
            "legacy_mixed": False,
        }
    for _, row in view_df.iterrows():
        row_dict = dict(row)
        draft_id = safe_str(row_dict.get("draft_id"))
        lines = lines_by_draft.get(draft_id, [])
        if not draft_applies_to_month(row_dict, lines, month_key):
            continue
        if safe_str(row_dict.get("month_key")).upper() == "MIXED":
            legacy_mixed = True
        status = safe_str(row_dict.get("draft_status"))
        if status in ("SENT_TO_REVIEW", "APPROVED"):
            sent_count += 1
        elif status in ("DRAFT", "NEED_REVISION"):
            draft_count += 1
    return {
        "sent_count": sent_count,
        "draft_count": draft_count,
        "legacy_mixed": legacy_mixed,
    }


def render_saved_plans_block() -> None:
    with st.expander("Архив черновиков и отправок — технический блок", expanded=False):
        drafts_df = load_monthly_plan_drafts("Все")
        selected_month = get_selected_planning_month()
        if drafts_df.empty:
            st.caption("Нет архивных записей за выбранный месяц")
            return

        draft_ids = [
            str(r.get("draft_id") or "")
            for _, r in drafts_df.iterrows()
            if str(r.get("draft_id") or "")
        ]
        lines_by_draft = load_draft_lines_by_drafts(draft_ids)
        all_view_df = enrich_saved_plans_view(drafts_df, lines_by_draft)
        archive_summary = summarize_archive_for_month(all_view_df, lines_by_draft, selected_month)

        archive_records_count = archive_summary["sent_count"] + archive_summary["draft_count"]
        if archive_records_count == 0 and not archive_summary["legacy_mixed"]:
            st.caption("Нет архивных записей за выбранный месяц")
            return

        st.markdown(
            f"- **Найдено отправок за выбранный месяц:** {archive_summary['sent_count']}\n"
            f"- **Черновиков:** {archive_summary['draft_count']}\n"
            f"- **Legacy MIXED найден:** {'да' if archive_summary['legacy_mixed'] else 'нет'}"
        )
        if archive_summary["legacy_mixed"]:
            st.info(
                "Есть старый отправленный план с технической меткой MIXED. "
                "В рабочем режиме он отображается по строкам выбранного месяца."
            )

        with st.expander("Показать технические записи", expanded=False):
            month_options = [
                m
                for m in ["Все"] + saved_plans_filter_options(all_view_df, lines_by_draft, "month_key")
                if m.upper() != "MIXED"
            ]
            if "saved_plans_filter_month" not in st.session_state:
                if selected_month in month_options and selected_month.upper() != "MIXED":
                    st.session_state["saved_plans_filter_month"] = selected_month
                else:
                    st.session_state["saved_plans_filter_month"] = "Все"
            status_label_options = ["Все"] + [
                DRAFT_STATUS_RU[code] for code in DRAFT_STATUS_FILTER_OPTIONS if code != "Все"
            ]

            f1, f2 = st.columns(2)
            with f1:
                month_filter = st.selectbox("Месяц", month_options, key="saved_plans_filter_month")
            with f2:
                selected_status_label = st.selectbox(
                    "Статус", status_label_options, key="saved_plans_filter_status"
                )
            status_filter = (
                "Все"
                if selected_status_label == "Все"
                else DRAFT_STATUS_RU_TO_CODE.get(selected_status_label, selected_status_label)
            )

            view_df = filter_saved_plans_view(
                all_view_df,
                lines_by_draft,
                month_filter=month_filter,
                facility_filter="Все",
                discipline_filter="Все",
                status_filter=status_filter,
            )
            if view_df.empty:
                st.caption("Нет сохранённых планов по выбранным фильтрам.")
            else:
                summary_rows = [saved_draft_preview_row(dict(row)) for _, row in view_df.iterrows()]
                summary = build_saved_drafts_preview_df(summary_rows)
                st.dataframe(
                    summary,
                    use_container_width=True,
                    hide_index=True,
                    height=min(240, 44 + len(summary) * 36),
                    column_order=SAVED_PLAN_SUMMARY_COLUMNS,
                )

                delete_candidate_rows: list[dict] = []
                delete_draft_ids: list[str] = []
                delete_row_by_id: dict[str, dict] = {}
                for _, row in view_df.iterrows():
                    draft_id = str(row.get("draft_id") or "")
                    if not draft_id:
                        continue
                    delete_draft_ids.append(draft_id)
                    row_dict = dict(row)
                    delete_candidate_rows.append(row_dict)
                    delete_row_by_id[draft_id] = row_dict

                with st.expander("Удаление сохранённых черновиков", expanded=False):
                    st.caption(
                        "Удаляются только явно выбранные draft_id вместе со строками плана, "
                        "записями очереди допуска и ограничениями этого черновика."
                    )
                    if delete_draft_ids:
                        selected_draft_ids = st.multiselect(
                            "Выберите draft_id для удаления",
                            options=delete_draft_ids,
                            format_func=lambda did: saved_draft_delete_label(
                                delete_row_by_id.get(str(did), {"draft_id": did})
                            ),
                            key="saved_drafts_delete_select",
                        )
                        st.warning("Для удаления введите: УДАЛИТЬ")
                        confirm_delete_text = st.text_input(
                            "Подтверждение удаления",
                            placeholder="Введите УДАЛИТЬ",
                            key="delete_saved_drafts_confirm_text",
                        )
                        if selected_draft_ids:
                            preview_rows = [
                                r
                                for r in delete_candidate_rows
                                if str(r.get("draft_id")) in selected_draft_ids
                            ]
                            st.dataframe(
                                build_saved_drafts_preview_df(preview_rows),
                                use_container_width=True,
                                hide_index=True,
                                column_order=SAVED_DRAFT_DELETE_PREVIEW_COLUMNS,
                            )
                        delete_confirmed = confirm_delete_text.strip().upper() == "УДАЛИТЬ"
                        delete_btn_disabled = not selected_draft_ids or not delete_confirmed
                        if st.button(
                            "Удалить выбранные черновики",
                            key="saved_drafts_delete_btn",
                            type="secondary",
                            disabled=delete_btn_disabled,
                        ):
                            if not selected_draft_ids:
                                st.warning("Выберите черновики для удаления.")
                            elif not delete_confirmed:
                                st.warning("Введите УДАЛИТЬ для подтверждения удаления.")
                            else:
                                deleted_ok: list[str] = []
                                for draft_id in selected_draft_ids:
                                    result = delete_monthly_plan_draft_cascade(draft_id)
                                    if result.get("skipped_reason"):
                                        st.warning(
                                            f"draft_id {draft_id}: {result['skipped_reason']}"
                                        )
                                    else:
                                        deleted_ok.append(draft_id)
                                        st.success(
                                            "Удалено: "
                                            f"draft_id={result.get('draft_id')} · "
                                            f"строк плана={result.get('deleted_draft_lines_count', 0)}"
                                        )
                                if deleted_ok:
                                    clear_session_if_deleted_draft(deleted_ok)
                                    st.rerun()
                    else:
                        st.caption("Нет черновиков для удаления по текущим фильтрам.")

                for _, row in view_df.iterrows():
                    draft_id = str(row.get("draft_id") or "")
                    if not draft_id:
                        continue
                    draft_status = str(row.get("draft_status") or "")
                    status_label = str(row.get("status_label") or "")
                    lines = lines_by_draft.get(draft_id, [])
                    title = saved_plan_expander_title(dict(row), lines)
                    with st.expander(title, expanded=False):
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Проект", str(row.get("project_code") or "—"))
                        m2.metric("Месяц", str(row.get("month_label") or "—"))
                        m3.metric("Статус", status_label)
                        st.caption(
                            f"Создан: {_format_draft_created_at(row.get('created_at'))} · "
                            f"{row.get('draft_name') or 'Без названия'} · draft_id: {draft_id}"
                        )

                        btn_cols = st.columns(4)
                        if draft_status == "DRAFT":
                            if btn_cols[0].button("Открыть в конструкторе", key=f"open_draft_{draft_id}"):
                                open_draft_in_constructor(draft_id, draft_status, view_only=False)
                                st.rerun()
                            if btn_cols[1].button("Отменить черновик", key=f"cancel_draft_{draft_id}"):
                                try:
                                    cancel_draft_record(draft_id)
                                    st.success("Черновик отменён.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Ошибка отмены: {exc}")
                        elif draft_status == "SENT_TO_REVIEW":
                            if btn_cols[0].button("Открыть только для просмотра", key=f"view_draft_{draft_id}"):
                                open_draft_in_constructor(draft_id, draft_status, view_only=True)
                                st.rerun()
                            if btn_cols[1].button(
                                "Создать дополнение к месячному плану",
                                key=f"new_ver_{draft_id}",
                            ):
                                active_month = resolve_supplement_month_for_saved_plan(dict(row), lines)
                                start_new_draft_version(draft_id, active_month_key=active_month)
                                st.rerun()
                            if btn_cols[2].button("Отозвать из проверки", key=f"revoke_{draft_id}"):
                                try:
                                    revoke_draft_from_review(draft_id)
                                    st.success("План отозван из контура допуска и переведён на доработку.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Ошибка отзыва: {exc}")
                        elif draft_status == "NEED_REVISION":
                            if btn_cols[0].button("Открыть для исправления", key=f"fix_draft_{draft_id}"):
                                open_draft_in_constructor(draft_id, draft_status, view_only=False)
                                st.rerun()
                        elif draft_status == "APPROVED":
                            if btn_cols[0].button("Открыть только для просмотра", key=f"view_appr_{draft_id}"):
                                open_draft_in_constructor(draft_id, draft_status, view_only=True)
                                st.rerun()
                            if btn_cols[1].button("Создать корректировку", key=f"corr_{draft_id}"):
                                active_month = resolve_supplement_month_for_saved_plan(dict(row), lines)
                                start_new_draft_version(draft_id, active_month_key=active_month)
                                st.rerun()
                        elif draft_status in ("CANCELLED", "SUPERSEDED"):
                            if btn_cols[0].button("Только просмотр", key=f"view_only_{draft_id}"):
                                open_draft_in_constructor(draft_id, draft_status, view_only=True)
                                st.rerun()

            saved_draft_id = st.session_state.get(SAVED_DRAFT_ID_KEY) or ""
            render_review_queue_block(saved_draft_id)


def merge_adjustments(scope: pd.DataFrame, adjustments: pd.DataFrame) -> pd.DataFrame:
    if scope.empty:
        return scope

    df = scope.copy()
    numeric_cols = [
        "total_project_qty",
        "executed_qty_all_time",
        "system_remaining_qty",
        "planning_remaining_qty",
        "planning_remaining_value",
        "manual_executed_before_system",
        "manual_verified_remaining_qty",
        "unit_price",
        "total_project_value",
        "executed_value_all_time",
        "p50_hours_per_unit",
        "p80_hours_per_unit",
        "weighted_avg_hours_per_unit",
        "estimated_hours_p50_remaining",
        "estimated_hours_p80_remaining",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    total_qty = df["total_project_qty"].fillna(0) if "total_project_qty" in df.columns else 0
    executed_qty = (
        df["executed_qty_all_time"].fillna(0)
        if "executed_qty_all_time" in df.columns
        else 0
    )
    if "system_remaining_qty" not in df.columns:
        df["system_remaining_qty"] = total_qty - executed_qty
    else:
        df["system_remaining_qty"] = df["system_remaining_qty"].fillna(total_qty - executed_qty)

    merge_keys = [
        "project_code",
        "facility_building",
        "construction_discipline",
        "boq_code",
    ]
    df = normalize_scope_merge_keys(df)
    adj = adjustments.copy() if not adjustments.empty else pd.DataFrame()

    if not adj.empty:
        if "reason" in adj.columns and "adjustment_reason" not in adj.columns:
            adj = adj.rename(columns={"reason": "adjustment_reason"})
        adj = normalize_scope_merge_keys(adj)
        for col in ("manual_executed_before_system", "manual_verified_remaining_qty"):
            if col in adj.columns:
                adj[col] = pd.to_numeric(adj[col], errors="coerce")
        keep_cols = merge_keys + [
            c
            for c in (
                "manual_executed_before_system",
                "manual_verified_remaining_qty",
                "adjustment_reason",
                "comment",
            )
            if c in adj.columns
        ]
        adj = adj[keep_cols].drop_duplicates(subset=merge_keys, keep="last")
        df = df.merge(adj, on=merge_keys, how="left", suffixes=("", "_adj"))
        for col in (
            "manual_executed_before_system",
            "manual_verified_remaining_qty",
            "adjustment_reason",
            "comment",
        ):
            adj_col = f"{col}_adj"
            if adj_col in df.columns:
                if col in df.columns:
                    df[col] = df[adj_col].combine_first(df[col])
                else:
                    df[col] = df[adj_col]
                df = df.drop(columns=[adj_col])

    for col in (
        "manual_executed_before_system",
        "manual_verified_remaining_qty",
        "adjustment_reason",
        "comment",
    ):
        if col not in df.columns:
            df[col] = None

    planning_qty = []
    sources = []
    for _, r in df.iterrows():
        rem, src = compute_planning_remaining_for_row(r)
        planning_qty.append(rem)
        sources.append(src)

    df["planning_remaining_qty"] = planning_qty
    df["remaining_qty_source"] = sources

    unit_price = df["unit_price"].fillna(0) if "unit_price" in df.columns else 0
    df["planning_remaining_value"] = df["planning_remaining_qty"] * unit_price

    p50 = df["p50_hours_per_unit"] if "p50_hours_per_unit" in df.columns else None
    p80 = df["p80_hours_per_unit"] if "p80_hours_per_unit" in df.columns else None
    if p50 is not None:
        df["estimated_hours_p50_remaining"] = df["planning_remaining_qty"] * p50
    if p80 is not None:
        df["estimated_hours_p80_remaining"] = df["planning_remaining_qty"] * p80

    return df


def filter_options(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


# Человекочитаемые имена → канонический project_code (если оба есть в данных)
HUMAN_PROJECT_ALIASES = {
    "БХК": "PRJ_001_БХК",
}


def project_filter_options(df: pd.DataFrame) -> list[str]:
    if df.empty or "project_code" not in df.columns:
        return ["Все"]
    vals = df["project_code"].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    canonical = sorted(v for v in vals if v.startswith("PRJ_"))
    if canonical:
        return ["Все"] + canonical
    hide = set()
    for human, canon in HUMAN_PROJECT_ALIASES.items():
        if human in vals and canon in vals:
            hide.add(human)
    shown = sorted(v for v in vals if v not in hide)
    return ["Все"] + shown


def construction_stage_titles(stage: str) -> list[str] | None:
    """Список титулов очереди или None, если выбраны все очереди."""
    titles = CONSTRUCTION_STAGE_MAP.get(stage, [])
    if not titles:
        return None
    return list(titles)


def filter_df_by_construction_stage(df: pd.DataFrame, stage: str) -> pd.DataFrame:
    if df.empty or "facility_building" not in df.columns:
        return df
    titles = construction_stage_titles(stage)
    if titles is None:
        return df
    allowed = {str(t).strip() for t in titles}
    mask = df["facility_building"].astype(str).str.strip().isin(allowed)
    return df[mask].copy()


def facility_filter_options(df: pd.DataFrame, construction_stage: str) -> list[str]:
    scoped = filter_df_by_construction_stage(df, construction_stage)
    return filter_options(scoped, "facility_building")


def apply_filters(
    df: pd.DataFrame,
    project: str,
    construction_stage: str,
    facility: str,
    discipline: str,
    norm_status: str,
    search: str,
    display_mode: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if project != "Все":
        out = out[out["project_code"].astype(str) == project]
    out = filter_df_by_construction_stage(out, construction_stage)
    if facility != "Все" and "facility_building" in out.columns:
        out = out[out["facility_building"].astype(str) == facility]
    if discipline != "Все" and "construction_discipline" in out.columns:
        out = out[out["construction_discipline"].astype(str) == discipline]
    if norm_status != "Все" and "norm_status" in out.columns:
        out = out[out["norm_status"].astype(str) == norm_status]
    if search.strip():
        q = search.strip().lower()
        out = ensure_columns(out, {"boq_code": "", "boq_name": ""})
        name_series = pick_series(out, BOQ_NAME_FALLBACKS)
        mask = (
            out["boq_code"].astype(str).str.lower().str.contains(q, na=False)
            | name_series.str.lower().str.contains(q, na=False)
        )
        out = out[mask]
    if "planning_remaining_qty" in out.columns:
        qty_col = (
            "available_remaining_qty"
            if "available_remaining_qty" in out.columns
            else "planning_remaining_qty"
        )
        qty_num = pd.to_numeric(out[qty_col], errors="coerce")
        if display_mode == "Только коды с остатком > 0":
            out = out[qty_num > 0]
        elif display_mode == "Закрытые коды = 0":
            out = out[qty_num == 0]
        elif display_mode == "Перевыполненные коды < 0":
            out = out[qty_num < 0]
    return out


def view_has_nonpositive_remaining(df: pd.DataFrame) -> bool:
    qty_col = (
        "available_remaining_qty"
        if "available_remaining_qty" in df.columns
        else "planning_remaining_qty"
    )
    if df.empty or qty_col not in df.columns:
        return False
    qty = pd.to_numeric(df[qty_col], errors="coerce")
    return bool((qty <= 0).any())


def source_badge_label(source_code: str) -> str:
    code = str(source_code or "").strip()
    if code == "MANUAL_VERIFIED":
        return "Ручной остаток"
    if code == "SYSTEM_CALCULATED":
        return "Расчёт системы"
    return REMAINING_SOURCE_RU.get(code, code or "—")


def select_label(row: pd.Series) -> str:
    qty = qty_fmt(row.get("planning_remaining_qty"))
    name = str(row.get("boq_name") or "")[:60]
    return (
        f"{row.get('boq_code')} | {row.get('facility_building')} | "
        f"{row.get('construction_discipline')} | {qty} | {name}"
    )


def prepare_scope_work_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_rk"] = out.apply(row_key, axis=1)
    return out.sort_values(
        ["facility_building", "construction_discipline", "boq_code"],
        na_position="last",
    ).reset_index(drop=True)


def build_scope_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    out = prepare_scope_work_df(df) if "_rk" not in df.columns else df.copy()
    if "_rk" not in out.columns:
        out["_rk"] = out.apply(row_key, axis=1)
    out = ensure_columns(
        out,
        {
            "boq_code": "",
            "facility_building": "",
            "construction_discipline": "",
            "total_project_qty": 0,
            "executed_qty_all_time": 0,
            "planning_remaining_qty": 0,
            "available_remaining_qty": 0,
            "available_remaining_value": 0,
            "planning_remaining_value": 0,
            "norm_status": "",
            "remaining_qty_source": "",
        },
    )

    rem_qty = (
        out["available_remaining_qty"]
        if "available_remaining_qty" in out.columns
        else out["planning_remaining_qty"]
    )
    rem_val = (
        out["available_remaining_value"]
        if "available_remaining_value" in out.columns
        else out["planning_remaining_value"]
    )

    boq_names = pick_series(out, BOQ_NAME_FALLBACKS)
    uom = pick_series(out, UOM_FALLBACKS)

    table = pd.DataFrame(
        {
            "BOQ-код": out["boq_code"],
            "Наименование работы": boq_names,
            "Ед. изм.": uom.replace("", "—"),
            "Титул / объект": out["facility_building"],
            "Дисциплина": out["construction_discipline"],
            "Доступный остаток": rem_qty.apply(qty_fmt),
            "Остаток, %": out.apply(
                lambda r: percent_fmt(
                    r.get("available_remaining_qty", r.get("planning_remaining_qty")),
                    r.get("total_project_qty"),
                ),
                axis=1,
            ),
            "Стоимость остатка": rem_val.apply(money_ru),
            "Источник нормы / сценарий нормы": out.apply(scope_norm_source_label, axis=1),
            "_rk": out["_rk"],
        }
    )
    return table


def get_row_by_key(df: pd.DataFrame, key: str) -> pd.Series | None:
    if not key or df.empty:
        return None
    if "_rk" not in df.columns:
        df = df.copy()
        df["_rk"] = df.apply(row_key, axis=1)
    match = df[df["_rk"] == key]
    if match.empty:
        return None
    return match.iloc[0]


def save_adjustment(row: pd.Series, manual_exec, manual_verified, reason: str, comment: str):
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY не задан в .env — запись корректировок недоступна."
        )
    payload = {
        "project_code": str(row.get("project_code", "")).strip(),
        "facility_building": str(row.get("facility_building") or "").strip(),
        "construction_discipline": str(row.get("construction_discipline") or "").strip(),
        "boq_code": str(row.get("boq_code", "")).strip().upper(),
        "manual_executed_before_system": safe_float(manual_exec),
        "manual_verified_remaining_qty": safe_float(manual_verified),
        "reason": reason.strip() if reason else None,
        "comment": comment.strip() if comment else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = write_client.table(ADJUSTMENTS_TABLE).upsert(
        payload,
        on_conflict="project_code,facility_building,construction_discipline,boq_code",
    ).execute()
    if getattr(resp, "error", None):
        raise RuntimeError(f"Supabase upsert error: {resp.error}")
    return resp


def render_productivity_block(row: pd.Series) -> None:
    no_hist = str(row.get("norm_status") or "") == "НЕТ ИСТОРИИ"
    conf_label, conf_cls = confidence_display(row.get("confidence_level"), row.get("norm_status"))

    cards = [
        (
            "Средняя историческая норма",
            hours_per_unit_fmt(row.get("weighted_avg_hours_per_unit"), no_history=no_hist),
            "Все часы / весь объём",
        ),
        (
            "Реалистичная норма",
            hours_per_unit_fmt(row.get("p50_hours_per_unit"), no_history=no_hist),
            "Обычный сценарий",
        ),
        (
            "Осторожная норма",
            hours_per_unit_fmt(row.get("p80_hours_per_unit"), no_history=no_hist),
            "Сложный фронт / риск",
        ),
    ]
    cards_html = "".join(
        f"""
        <div class="norm-card">
            <div class="norm-card-title">{esc(title)}</div>
            <div class="norm-card-value">{esc(value)}</div>
            <div class="norm-card-hint">{esc(hint)}</div>
        </div>
        """
        for title, value, hint in cards
    )
    st.markdown(
        f"""
        <div class="norm-row">{cards_html}</div>
        <span class="scope-badge {conf_cls}">Достоверность данных: {esc(conf_label)}</span>
        """,
        unsafe_allow_html=True,
    )


def render_systems_block(row: pd.Series) -> None:
    has_system = "system_label" in row.index and pd.notna(row.get("system_label"))
    has_iwp = "iwp_id" in row.index and pd.notna(row.get("iwp_id"))
    if has_system or has_iwp:
        system_text = str(row.get("system_label") or "—")
        iwp_text = str(row.get("iwp_id") or "—")
        system_chips = "".join(
            f'<span class="chip">{esc(part.strip())}</span>'
            for part in system_text.split(",")
            if part.strip()
        ) or f'<span class="chip">{esc(system_text)}</span>'
        iwp_chips = "".join(
            f'<span class="chip">{esc(part.strip())}</span>'
            for part in iwp_text.split(",")
            if part.strip()
        ) or f'<span class="chip">{esc(iwp_text)}</span>'
        st.markdown(
            f"""
            <div style="font-size:0.82rem; color:#52525b; margin-bottom:4px;">Системы</div>
            <div class="chip-row">{system_chips}</div>
            <div style="font-size:0.82rem; color:#52525b; margin:8px 0 4px 0;">Пакеты / IWP</div>
            <div class="chip-row">{iwp_chips}</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.caption(
            "Системы и пакеты будут добавлены следующим шагом через расширение источника данных. "
            "Для этого нужно подтянуть из Daily Progress или IWP-реестра перечень "
            "system_label и iwp_id по выбранному BoQ-коду."
        )


def render_detail_card(row: pd.Series, crews: list[str]) -> None:
    rk = row_key(row).replace("|", "_")
    norm = norm_status_label(row.get("norm_status"))
    norm_cls = "badge-history" if str(row.get("norm_status") or "") == "ИСТОРИЯ ЕСТЬ" else "badge-no-history"
    source_code = str(row.get("remaining_qty_source") or "")
    if source_code == "MANUAL_VERIFIED":
        src_cls = "badge-manual"
    elif source_code == "SYSTEM_CALCULATED":
        src_cls = "badge-system"
    else:
        src_cls = "badge-system"
    src_label = source_badge_label(source_code)
    boq_name = pick_field(row, BOQ_NAME_FALLBACKS)

    with st.container(border=True):
        left_col, right_col = st.columns([3, 2])
        with left_col:
            st.markdown(f"**{esc(row.get('boq_code'))}**")
            st.markdown(f"{esc(boq_name) or '—'}")
            st.markdown(
                f"""
                <div style="margin:8px 0 4px 0;">
                    <span class="scope-badge badge-system">{esc(row.get("facility_building"))}</span>
                    <span class="scope-badge badge-system" style="margin-left:6px;">{esc(row.get("construction_discipline"))}</span>
                    <span class="scope-badge {norm_cls}" style="margin-left:6px;">{esc(norm)}</span>
                    <span class="scope-badge {src_cls}" style="margin-left:6px;">{esc(src_label)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with right_col:
            key = boq_key_parts_from_row(row)
            planned_map = build_planned_qty_map()
            project_remaining = safe_float(row.get("planning_remaining_qty")) or 0.0
            already_planned = planned_map.get(key, 0.0)
            available_remaining = project_remaining - already_planned
            m1, m2 = st.columns(2)
            m3, m4 = st.columns(2)
            m1.metric("Всего", qty_fmt(row.get("total_project_qty")))
            m2.metric("Выполнено (факт)", qty_fmt(row.get("executed_qty_all_time")))
            m3.metric("Остаток проекта", qty_fmt(project_remaining))
            m4.metric("Доступно к плану", qty_fmt(available_remaining))
            st.caption(
                f"Уже запланировано: {qty_fmt(already_planned)} · "
                f"Стоимость доступного остатка: {money_ru(available_remaining * (safe_float(row.get('unit_price')) or 0))}"
            )

    render_boq_planning_usage(row)

    with st.expander("Историческая производительность", expanded=False):
        with st.container(border=True):
            render_productivity_block(row)

    with st.expander("Системы и пакеты", expanded=False):
        with st.container(border=True):
            render_systems_block(row)

    rk_full = row_key(row)
    total_qty = safe_float(row.get("total_project_qty")) or 0.0
    executed_qty = safe_float(row.get("executed_qty_all_time")) or 0.0
    accepted_default = get_customer_accepted_qty(rk_full)

    with st.expander("Признание заказчиком", expanded=False):
        with st.container(border=True):
            customer_accepted = st.number_input(
                "Объём, принятый заказчиком",
                min_value=0.0,
                value=float(accepted_default),
                step=0.01,
                key=f"customer_accepted_{rk}",
                help="Физически выполнено может отличаться от принятого заказчиком.",
            )
            set_customer_accepted_qty(rk_full, customer_accepted)
            st.caption("Физически выполнено может отличаться от принятого заказчиком.")
            install_remaining = total_qty - executed_qty
            recognition_remaining = total_qty - customer_accepted
            acc1, acc2, acc3 = st.columns(3)
            acc1.metric("Смонтировано", qty_fmt(executed_qty))
            acc2.metric("Остаток монтажа", qty_fmt(install_remaining))
            acc3.metric("Остаток признания", qty_fmt(recognition_remaining))

    customer_accepted = get_customer_accepted_qty(rk_full)
    recognition_remaining = total_qty - customer_accepted

    with st.expander("Корректировка остатка", expanded=False):
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                inp_exec = st.number_input(
                    "Выполнено до начала учёта",
                    min_value=0.0,
                    value=float(safe_float(row.get("manual_executed_before_system")) or 0.0),
                    step=0.01,
                    key=f"adj_exec_{rk}",
                )
                inp_verified = st.number_input(
                    "Подтверждённый остаток",
                    min_value=0.0,
                    value=float(safe_float(row.get("manual_verified_remaining_qty")) or 0.0),
                    step=0.01,
                    key=f"adj_ver_{rk}",
                )
            with c2:
                reason_val = row.get("manual_adjustment_reason")
                if reason_val is None or (isinstance(reason_val, float) and pd.isna(reason_val)):
                    reason_val = row.get("adjustment_reason")
                comment_val = row.get("manual_adjustment_comment")
                if comment_val is None or (isinstance(comment_val, float) and pd.isna(comment_val)):
                    comment_val = row.get("comment")
                inp_reason = st.text_input(
                    "Причина корректировки",
                    value=str(reason_val or "") if pd.notna(reason_val) else "",
                    key=f"adj_reason_{rk}",
                )
                inp_comment = st.text_area(
                    "Комментарий",
                    value=str(comment_val or "") if pd.notna(comment_val) else "",
                    height=68,
                    key=f"adj_comment_{rk}",
                )

            if st.button("Сохранить корректировку", key=f"save_adj_{rk}"):
                try:
                    verified_val = inp_verified if inp_verified > 0 else None
                    resp = save_adjustment(row, inp_exec, verified_val, inp_reason, inp_comment)
                    load_scope.clear()
                    load_adjustments.clear()
                    saved = (resp.data or [{}])[0] if resp.data else {}
                    st.success(
                        "Корректировка сохранена: "
                        f"до учёта {qty_fmt(saved.get('manual_executed_before_system', inp_exec))} · "
                        f"ключ {saved.get('facility_building') or row.get('facility_building')} / "
                        f"{saved.get('boq_code') or row.get('boq_code')}"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Ошибка сохранения корректировки: {exc}")

    with st.expander("Добавить в черновик планирования", expanded=True):
        plan_month = get_selected_planning_month()
        p1, p2, p3 = st.columns(3)
        with p1:
            st.text_input(
                "Месяц планирования",
                value=plan_month,
                disabled=True,
                key=f"plan_month_display_{rk}",
            )
            plan_qty = st.number_input(
                "Плановый объём",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key=f"plan_qty_{rk}",
            )
        with p2:
            if crews:
                plan_crew = st.selectbox("Звено", [""] + crews, key=f"plan_crew_{rk}")
            else:
                plan_crew = st.text_input("Звено", key=f"plan_crew_{rk}")
            norm_scenario = st.selectbox(
                "Сценарий нормы",
                [
                    "Реалистичная норма (P50)",
                    "Осторожная норма (P80)",
                    "Ручная норма",
                ],
                index=0,
                key=f"plan_norm_{rk}",
            )
            st.caption(norm_scenario_hint(norm_scenario))
        with p3:
            manual_norm = st.number_input(
                "Ручная норма, ч/ед",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key=f"plan_manual_norm_{rk}",
                disabled=norm_scenario != "Ручная норма",
            )
            plan_comment = st.text_input("Комментарий", key=f"plan_comment_{rk}")

        line_scope_note = st.text_input(
            "Задача / зона / помещение / примечание к строке",
            key=f"line_scope_note_{rk}",
        )

        project_remaining = safe_float(row.get("planning_remaining_qty")) or 0.0
        unit_price = safe_float(row.get("unit_price")) or 0.0
        boq_key = boq_key_parts_from_row(row)
        planned_map = build_planned_qty_map()
        already_planned = planned_map.get(boq_key, 0.0)
        available_to_add_qty = max(project_remaining - already_planned, 0.0)

        scenario_code = {
            "Реалистичная норма (P50)": NORM_SCENARIO_REALISTIC,
            "Осторожная норма (P80)": NORM_SCENARIO_CAUTIOUS,
            "Ручная норма": NORM_SCENARIO_MANUAL,
        }.get(norm_scenario, NORM_SCENARIO_REALISTIC)

        hours_per_unit = norm_scenario_hours(row, scenario_code, manual_norm)

        req_hours = (
            (plan_qty * hours_per_unit) if hours_per_unit is not None and plan_qty > 0 else None
        )
        plan_value = plan_qty * unit_price if plan_qty > 0 else 0.0
        labor_rate_per_hour = DEFAULT_LABOR_RATE_PER_HOUR
        labor_cost = (req_hours or 0.0) * labor_rate_per_hour

        if plan_qty > available_to_add_qty + 1e-9 and plan_qty > 0:
            st.warning(
                f"Плановый объём ({qty_fmt(plan_qty)}) больше доступного к планированию "
                f"({qty_fmt(available_to_add_qty)})."
            )
        elif plan_qty > 0 and available_to_add_qty <= 0:
            st.warning("Доступный остаток для планирования исчерпан.")

        lim1, lim2, lim3 = st.columns(3)
        lim1.metric("Остаток проекта", qty_fmt(project_remaining))
        lim2.metric("Уже запланировано", qty_fmt(already_planned))
        lim3.metric("Доступно к добавлению", qty_fmt(available_to_add_qty))
        st.caption(
            "AVAILABLE REMAINING = остаток проекта (факт исполнения) − уже запланировано "
            "в активном и сохранённых черновиках. Признание заказчиком (КС) в расчёте не участвует."
        )
        if available_to_add_qty <= 0:
            st.info("Весь доступный остаток по этому коду уже распределён по планам.")

        if hours_per_unit is not None and plan_qty > 0:
            st.caption(
                f"Требуемые чел-часы = Плановый объём × выбранная норма → "
                f"{qty_fmt(plan_qty)} × {hours_per_unit_fmt(hours_per_unit)} = {hours_fmt(req_hours)} · "
                f"Плановая стоимость (EV): {money(plan_value)}"
            )
        else:
            st.caption(
                f"Требуемые чел-часы = Плановый объём × выбранная норма · "
                f"Плановая стоимость (EV): {money(plan_value)}"
            )

        view_only = bool(st.session_state.get(DRAFT_VIEW_ONLY_KEY, False))
        if view_only:
            st.caption("Режим просмотра загруженного плана — добавление в черновик отключено.")

        render_boq_add_duplicate_hints(
            row,
            str(plan_month).strip(),
            project_remaining,
            already_planned,
            available_to_add_qty,
        )

        add_disabled = (
            view_only
            or (plan_qty > available_to_add_qty)
            or (available_to_add_qty <= 0)
        )
        if st.button("Добавить в черновик", key=f"add_draft_{rk}", disabled=add_disabled):
            if plan_qty <= 0:
                st.warning("Укажите плановый объём больше нуля.")
            elif not str(plan_month).strip():
                st.warning("Укажите месяц планирования.")
            elif plan_qty > available_to_add_qty + 1e-9:
                st.error(
                    "Нельзя добавить объём больше доступного остатка. "
                    f"Остаток проекта: {qty_fmt(project_remaining)}, "
                    f"уже запланировано: {qty_fmt(already_planned)}, "
                    f"доступно: {qty_fmt(available_to_add_qty)}."
                )
            else:
                draft_item = {
                    "project_code": row.get("project_code"),
                    "boq_code": row.get("boq_code"),
                    "boq_name": pick_field(row, BOQ_NAME_FALLBACKS),
                    "facility_building": row.get("facility_building"),
                    "construction_discipline": row.get("construction_discipline"),
                    "month_key": plan_month,
                    "crew_code": str(plan_crew).strip() if plan_crew else "",
                    "line_scope_note": str(line_scope_note).strip(),
                    "planned_qty": plan_qty,
                    "plan_value": plan_value,
                    "required_hours": req_hours or 0.0,
                    "labor_rate_per_hour": labor_rate_per_hour,
                    "labor_cost": labor_cost,
                    "norm_scenario": scenario_code,
                    "manual_norm_value": manual_norm if scenario_code == NORM_SCENARIO_MANUAL else None,
                    "unit_of_measure": pick_field(row, UOM_FALLBACKS),
                    "comment": plan_comment,
                    "customer_accepted_qty": customer_accepted,
                    "recognition_remaining_qty": recognition_remaining,
                    "added_at": datetime.now(timezone.utc).isoformat(),
                    "line_source_ui": LINE_SOURCE_NEW_UI,
                    "read_only": False,
                }
                new_uid = draft_line_uid(draft_item)
                kept = [d for d in st.session_state[DRAFT_KEY] if draft_line_uid(d) != new_uid]
                kept.append(draft_item)
                st.session_state[DRAFT_KEY] = kept
                skip_months = st.session_state.setdefault(DRAFT_SKIP_HYDRATE_MONTHS_KEY, set())
                skip_months.discard(str(plan_month).strip())
                toast_msg = (
                    "Код добавлен в черновик. "
                    "Нажмите «Сохранить черновик» перед обновлением страницы."
                )
                st.toast(toast_msg)
                st.success(toast_msg)
                st.rerun()


def build_draft_display_df(draft: list[dict]) -> pd.DataFrame:
    rows: list[dict] = []
    for item in draft:
        scenario_code = item.get("norm_scenario")
        norm_value = norm_productivity_fmt(
            item.get("planned_qty"),
            item.get("required_hours"),
            pick_field(item, UOM_FALLBACKS),
        )
        scenario_label = norm_scenario_display(scenario_code)
        norm_cell = (
            f"{norm_value} · {scenario_label}" if norm_value != "—" else scenario_label
        )
        rows.append(
            {
                "Line_Source": "BASE" if item.get("line_source") == "BASE" else "ADDITION",
                "Код BOQ": pick_field(item, ("boq_code",)),
                "Наименование работы": pick_field(item, BOQ_NAME_FALLBACKS) or "—",
                "Ед. изм.": pick_field(item, UOM_FALLBACKS) or "—",
                "Титул": pick_field(item, ("facility_building",)),
                "Дисциплина": pick_field(item, ("construction_discipline",)),
                "Месяц": safe_str(item.get("month_key")) or "—",
                "Звено": safe_str(item.get("crew_code")) or "—",
                "Задача / зона / помещение": safe_str(item.get("line_scope_note")) or "—",
                "Объём": qty_fmt(item.get("planned_qty")),
                "Плановая стоимость, ₽": money_ru(item.get("plan_value")),
                "Требуется чел-ч": hours_fmt(item.get("required_hours")),
                "Норма": norm_cell,
                "Стоимость трудозатрат, ₽": money_ru(item.get("labor_cost")),
                "Сценарий нормы": norm_scenario_display(scenario_code),
                "Статус строки": safe_str(item.get("line_status")) or "DRAFT",
                "_scenario_code": scenario_code,
            }
        )
    return pd.DataFrame(rows)


def style_draft_display_df(
    display_df: pd.DataFrame,
    draft: list[dict],
    source_df: pd.DataFrame,
):
    if display_df.empty or "Сценарий нормы" not in display_df.columns:
        return display_df

    def _style_row(row: pd.Series) -> pd.Series:
        styles = pd.Series("", index=row.index)
        idx = row.name
        item = draft[idx] if idx < len(draft) else {}
        scenario = row.get("_scenario_code") or item.get("norm_scenario")
        has_history = draft_has_history(item, source_df)
        color = norm_scenario_cell_style(scenario, has_history)
        if color:
            styles["Сценарий нормы"] = color
        return styles

    show_cols = [c for c in display_df.columns if not c.startswith("_")]
    styled = display_df[show_cols].style.apply(_style_row, axis=1)
    return styled


def draft_table_height(row_count: int) -> int:
    if row_count <= 0:
        return 260
    return min(650, max(260, 90 + row_count * 35))


def render_draft_primary_actions(
    draft: list[dict],
    source_df: pd.DataFrame,
    project_filter: str,
) -> None:
    selected_month = get_selected_planning_month()
    new_lines = get_new_session_lines_for_month(selected_month, project_filter)
    new_count = len(new_lines)
    save_lines = new_lines
    saved_id = st.session_state.get(SAVED_DRAFT_ID_KEY)
    is_supplement = bool(st.session_state.get(SOURCE_DRAFT_ID_KEY))
    project_code, month_key = resolve_draft_save_context(save_lines, project_filter)
    if selected_month:
        month_key = selected_month
    save_blocked = False
    if not saved_id and project_code and month_key and not is_supplement:
        conflicting = find_monthly_plan_for_project_month(project_code, month_key)
        if conflicting:
            existing_id = safe_str(conflicting.get("draft_id"))
            existing_status = safe_str(conflicting.get("draft_status")) or "DRAFT"
            if existing_status in ("DRAFT", "NEED_REVISION"):
                save_blocked = True
                st.warning(
                    "Уже существует активный черновик месяца. "
                    "Чтобы добавить коды в него, сначала откройте его в конструкторе."
                )
                if st.button(
                    "Продолжить существующий черновик",
                    key="continue_existing_draft_btn",
                    type="primary",
                ):
                    pending_items = list(new_lines)
                    open_draft_in_constructor(existing_id, existing_status, view_only=False)
                    if pending_items:
                        merge_pending_draft_items(pending_items)
                    st.rerun()

    send_ok, send_hint, _ = validate_draft_send_context(new_lines, selected_month)
    unsaved = has_unsaved_new_lines(selected_month, project_filter)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Очистить новые строки", key="clear_draft"):
            remove_new_session_lines_for_month(selected_month, project_filter)
            st.session_state[DRAFT_VIEW_ONLY_KEY] = False
            st.session_state.pop(SELECTED_MONTH_PLAN_ROW_KEY, None)
            st.session_state.pop(MONTH_PLAN_EDIT_ROW_KEY, None)
            st.rerun()
    with b2:
        if st.button(
            "Сохранить черновик",
            key="save_draft",
            type="primary" if unsaved else "secondary",
            disabled=save_blocked or not save_lines,
        ):
            month_error = validate_draft_single_month_key(save_lines)
            validation_errors = validate_draft_for_save(save_lines, source_df)
            if not save_lines:
                st.warning("Нет новых строк для сохранения.")
            elif month_error:
                st.error(month_error)
            elif validation_errors:
                st.error("Ошибки черновика:\n- " + "\n- ".join(validation_errors))
            else:
                try:
                    saved_id = st.session_state.get(SAVED_DRAFT_ID_KEY)
                    loaded_status = str(st.session_state.get(LOADED_DRAFT_STATUS_KEY) or "")
                    update_id = (
                        saved_id
                        if saved_id and loaded_status in SENDABLE_DRAFT_STATUSES
                        else None
                    )
                    draft_id = save_draft_to_supabase(
                        save_lines, source_df, existing_draft_id=update_id
                    )
                    st.session_state[SAVED_DRAFT_ID_KEY] = draft_id
                    st.session_state[LOADED_DRAFT_STATUS_KEY] = "DRAFT"
                    st.session_state[DRAFT_VIEW_ONLY_KEY] = False
                    skip_months = st.session_state.setdefault(
                        DRAFT_SKIP_HYDRATE_MONTHS_KEY, set()
                    )
                    skip_months.discard(selected_month)
                    st.success(
                        f"Черновик сохранён. Новых строк: {len(save_lines)}. "
                        "Ранее отправленные строки не затронуты."
                    )
                    _load_reserved_planned_qty_from_db.clear()
                    _load_boq_planning_usage_cache.clear()
                    find_monthly_plan_for_project_month.clear()
                    find_boq_in_monthly_plans.clear()
                    load_previously_sent_lines_for_month.clear()
                except Exception as exc:
                    st.error(f"Ошибка сохранения черновика: {exc}")
    with b3:
        if st.button(
            "Отправить новые строки в контур допуска",
            key="send_draft_approval",
            type="primary" if send_ok and not unsaved else "secondary",
            disabled=not send_ok,
        ):
            can_send, send_error, send_draft_id = validate_draft_send_context(
                new_lines, selected_month
            )
            if not can_send:
                st.warning(send_error)
            elif not send_draft_id:
                st.warning("Сначала сохраните черновик с новыми строками.")
            else:
                try:
                    source_id = st.session_state.get(SOURCE_DRAFT_ID_KEY)
                    constraints_summary = send_draft_to_review_queue(
                        send_draft_id,
                        source_draft_id=source_id,
                    )
                    if source_id:
                        st.session_state[SOURCE_DRAFT_ID_KEY] = None
                    st.session_state[LOADED_DRAFT_STATUS_KEY] = "SENT_TO_REVIEW"
                    st.session_state[DRAFT_VIEW_ONLY_KEY] = True
                    load_previously_sent_lines_for_month.clear()
                    find_monthly_plan_for_project_month.clear()
                    created_constraints = int(constraints_summary.get("created_count") or 0)
                    if constraints_auto_create_succeeded(constraints_summary):
                        st.success(
                            f"Отправлено в контур допуска. "
                            f"Проверки по отделам сформированы: {created_constraints}."
                        )
                    else:
                        st.warning(
                            "Строки отправлены в контур допуска, но проверки по отделам "
                            "не сформированы автоматически. Сформируйте их на странице "
                            "Контур допуска."
                        )
                        for err in constraints_summary.get("errors") or []:
                            st.caption(str(err))
                except Exception as exc:
                    st.error(f"Ошибка отправки в контур: {exc}")

    st.caption(
        f"К отправке: {new_count} новых строк. "
        "Ранее отправленные строки повторно не отправляются."
    )
    if new_count == 0:
        st.warning("Нет новых строк для отправки.")
    elif not send_ok and send_hint:
        st.warning(send_hint)


def render_draft_kpis(draft: list[dict]) -> None:
    total_ev = sum(safe_num(x.get("plan_value")) for x in draft)
    total_hours = sum(safe_num(x.get("required_hours")) for x in draft)
    total_labor_cost = sum(safe_num(x.get("labor_cost")) for x in draft)
    crews = {
        safe_str(x.get("crew_code"))
        for x in draft
        if safe_str(x.get("crew_code"))
    }
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Строк", len(draft))
    k2.metric("Плановая стоимость всего", money_ru(total_ev))
    k3.metric("Требуется чел-ч всего", hours_fmt(total_hours))
    k4.metric("Стоимость трудозатрат всего", money_ru(total_labor_cost))
    k5.metric("Количество звеньев", len(crews))


def render_draft_delete_controls(draft: list[dict]) -> None:
    if not draft:
        return

    st.warning(
        "Удаление доступно только для новых строк текущего месяца. "
        "Ранее отправленные строки удалить из конструктора нельзя."
    )

    st.markdown("##### Удаление одной строки")
    labels = [draft_item_label(item, index=i) for i, item in enumerate(draft)]
    label_to_item = {label: item for label, item in zip(labels, draft)}

    selected_label = st.selectbox(
        "Выберите строку для удаления",
        options=labels,
        key="draft_delete_single_select",
    )
    confirm_single = st.checkbox(
        "Подтверждаю удаление выбранной строки",
        key="draft_delete_single_confirm",
    )
    if st.button("Удалить выбранную строку", key="draft_delete_single_btn"):
        if not confirm_single:
            st.warning("Подтвердите удаление строки.")
        else:
            remove_draft_line_uids({draft_line_uid(label_to_item[selected_label])})
            st.success("Строка удалена из черновика.")
            st.rerun()

    st.divider()
    st.markdown("##### Массовое удаление строк")
    selected_labels = st.multiselect(
        "Выберите строки для удаления",
        options=labels,
        key="draft_delete_bulk_select",
    )
    confirm_bulk = st.checkbox(
        "Подтверждаю удаление выбранных строк",
        key="draft_delete_bulk_confirm",
    )
    if st.button("Удалить выбранные строки", key="draft_delete_bulk_btn"):
        if not selected_labels:
            st.warning("Выберите хотя бы одну строку.")
        elif not confirm_bulk:
            st.warning("Подтвердите массовое удаление.")
        else:
            uids = {draft_line_uid(label_to_item[label]) for label in selected_labels}
            remove_draft_line_uids(uids)
            st.success(f"Удалено строк: {len(uids)}")
            st.rerun()


def render_draft_panel(source_df: pd.DataFrame, crews: list[str], project_filter: str):
    st.markdown('<div class="draft-panel-block">', unsafe_allow_html=True)
    selected_month = get_selected_planning_month()
    sent_lines, new_lines, legacy_mixed = build_constructor_month_lines(
        selected_month,
        project_filter,
    )
    merged = sent_lines + new_lines
    st.markdown(
        f'<h2 class="draft-panel-title">Единый месячный план: {html_lib.escape(selected_month)}</h2>',
        unsafe_allow_html=True,
    )
    if session_has_other_month_draft_lines(selected_month):
        st.warning(
            "В session есть строки другого месяца. "
            "Они не отображаются в текущем месяце."
        )
    if legacy_mixed or st.session_state.pop("legacy_mixed_draft_warning", False):
        st.info(
            "Есть старый отправленный план с технической меткой MIXED. "
            "В рабочем режиме он отображается по строкам выбранного месяца."
        )
    if st.session_state.pop("new_version_info", False):
        pass
    render_active_draft_status_banner(project_filter)
    view_only = bool(st.session_state.get(DRAFT_VIEW_ONLY_KEY, False))
    if view_only:
        st.caption("Режим просмотра: редактирование и сохранение недоступны.")

    if not merged:
        st.caption("Нет строк для выбранного месяца. Добавьте новые коды из карточки BOQ.")
    else:
        render_constructor_unified_summary(merged)
        if new_lines:
            if has_unsaved_new_lines(selected_month, project_filter):
                st.warning(
                    "Новые строки ещё не сохранены. Нажмите «Сохранить черновик», "
                    "иначе после обновления страницы они могут исчезнуть."
                )
            elif safe_str(st.session_state.get(SAVED_DRAFT_ID_KEY)):
                st.caption("Новый код — сохранённый черновик (восстановлен из БД).")
        table_height = draft_table_height(len(merged))
        selected_uid = safe_str(st.session_state.get(SELECTED_MONTH_PLAN_ROW_KEY))
        table_df, row_uids = build_constructor_selectable_table_df(merged, selected_uid)
        select_column_config = {
            col: st.column_config.TextColumn(disabled=True)
            for col in CONSTRUCTOR_TABLE_COLUMNS
        }
        select_column_config[CONSTRUCTOR_SELECT_COLUMN] = st.column_config.CheckboxColumn(
            default=False,
            help="Выберите одну строку для редактирования или удаления",
        )
        edited_table = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
            height=table_height,
            column_config=select_column_config,
            column_order=[CONSTRUCTOR_SELECT_COLUMN] + CONSTRUCTOR_TABLE_COLUMNS,
            disabled=CONSTRUCTOR_TABLE_COLUMNS,
            key="month_plan_unified_select_editor",
        )
        new_selected_uid, multiple_selected = sync_month_plan_row_selection(
            edited_table,
            row_uids,
        )
        if multiple_selected:
            st.warning("Выберите только одну строку.")
        if new_selected_uid != selected_uid:
            st.session_state.pop(MONTH_PLAN_EDIT_ROW_KEY, None)
        st.session_state[SELECTED_MONTH_PLAN_ROW_KEY] = new_selected_uid

        render_month_plan_row_actions(
            merged,
            source_df,
            crews,
            project_filter,
            selected_month,
            view_only=view_only,
        )
        if not view_only:
            render_draft_primary_actions(new_lines, source_df, project_filter)

    st.markdown("</div>", unsafe_allow_html=True)


# --- main ---
if DRAFT_KEY not in st.session_state:
    st.session_state[DRAFT_KEY] = []
if CUSTOMER_ACCEPTED_KEY not in st.session_state:
    st.session_state[CUSTOMER_ACCEPTED_KEY] = {}
if SELECTED_RK_KEY not in st.session_state:
    st.session_state[SELECTED_RK_KEY] = ""
if SELECTED_MONTH_PLAN_ROW_KEY not in st.session_state:
    st.session_state[SELECTED_MONTH_PLAN_ROW_KEY] = None
if MONTH_PLAN_EDIT_ROW_KEY not in st.session_state:
    st.session_state[MONTH_PLAN_EDIT_ROW_KEY] = None
if DRAFT_EDIT_MODE_KEY not in st.session_state:
    st.session_state[DRAFT_EDIT_MODE_KEY] = False
if SAVED_DRAFT_KEY not in st.session_state:
    st.session_state[SAVED_DRAFT_KEY] = None
if REVIEW_QUEUE_KEY not in st.session_state:
    st.session_state[REVIEW_QUEUE_KEY] = None
if SAVED_DRAFT_ID_KEY not in st.session_state:
    st.session_state[SAVED_DRAFT_ID_KEY] = None
if SOURCE_DRAFT_ID_KEY not in st.session_state:
    st.session_state[SOURCE_DRAFT_ID_KEY] = None
if BASE_DRAFT_LINES_KEY not in st.session_state:
    st.session_state[BASE_DRAFT_LINES_KEY] = []
if ACTIVE_PLAN_MONTH_KEY not in st.session_state:
    st.session_state[ACTIVE_PLAN_MONTH_KEY] = None
if SELECTED_PLANNING_MONTH_KEY not in st.session_state:
    st.session_state[SELECTED_PLANNING_MONTH_KEY] = DEFAULT_PLANNING_MONTH
if DRAFT_VIEW_ONLY_KEY not in st.session_state:
    st.session_state[DRAFT_VIEW_ONLY_KEY] = False
if LOADED_DRAFT_STATUS_KEY not in st.session_state:
    st.session_state[LOADED_DRAFT_STATUS_KEY] = None
if DRAFT_SKIP_HYDRATE_MONTHS_KEY not in st.session_state:
    st.session_state[DRAFT_SKIP_HYDRATE_MONTHS_KEY] = set()

scope_raw = load_scope()
adjustments_raw = load_adjustments()
crew_options = load_crew_options()

if scope_raw.empty:
    st.warning(f"Витрина {SCOPE_VIEW} пуста. Выполните SQL monthly_scope_picker_v1.sql в Supabase.")
    st.stop()

data = merge_adjustments(scope_raw, adjustments_raw)
planned_qty_map = build_planned_qty_map()
data = apply_available_remaining(data, planned_qty_map)

planning_month_options = planning_month_options_2026()
current_planning_month = get_selected_planning_month()
planning_month_index = (
    planning_month_options.index(current_planning_month)
    if current_planning_month in planning_month_options
    else planning_month_options.index(DEFAULT_PLANNING_MONTH)
)
selected_planning_month = st.selectbox(
    "Месяц планирования",
    planning_month_options,
    index=planning_month_index,
    key="constructor_planning_month_select",
)
st.session_state[SELECTED_PLANNING_MONTH_KEY] = selected_planning_month
st.session_state[ACTIVE_PLAN_MONTH_KEY] = selected_planning_month

st.divider()

f1, f2, f3, f4, f5, f6, f7 = st.columns([1.0, 1.15, 1.1, 1.0, 1.0, 1.2, 1.2])
with f1:
    sel_project = st.selectbox("Проект", project_filter_options(data))
data_for_stage = data if sel_project == "Все" else data[data["project_code"].astype(str) == sel_project]
with f2:
    sel_construction_stage = st.selectbox(
        "Очередь строительства",
        CONSTRUCTION_STAGE_OPTIONS,
        key="scope_filter_construction_stage",
    )
with f3:
    sel_facility = st.selectbox(
        "Титул / объект",
        facility_filter_options(data_for_stage, sel_construction_stage),
        key="scope_filter_facility",
    )
with f4:
    sel_discipline = st.selectbox("Дисциплина", filter_options(data, "construction_discipline"))
with f5:
    sel_norm = st.selectbox("Статус нормы", NORM_STATUS_OPTIONS)
with f6:
    search_text = st.text_input("Поиск по BOQ-коду / наименованию")
with f7:
    display_mode = st.radio(
        "Режим отображения кодов",
        DISPLAY_MODE_OPTIONS,
        index=1,
    )

filtered = apply_filters(
    data,
    sel_project,
    sel_construction_stage,
    sel_facility,
    sel_discipline,
    sel_norm,
    search_text,
    display_mode,
)

if display_mode != "Только коды с остатком > 0" and not view_has_nonpositive_remaining(scope_raw):
    st.info(
        "В `monthly_scope_picker_view` сейчас нет строк с остатком ≤ 0 — "
        "вероятно, в SQL view стоит фильтр `WHERE planning_remaining_qty > 0` "
        "(или `remaining_qty > 0`). Чтобы видеть перевыполнение (остаток 0 и отрицательный), "
        "нужно убрать это условие в SQL. На странице дополнительной фильтрации нет."
    )

st.caption(
    f"Источник: `{SCOPE_VIEW}` · загружено: {len(scope_raw)} · после фильтров: {len(filtered)}"
)

render_filter_summary(filtered)

st.divider()

st.subheader("Коды BoQ")
if filtered.empty:
    st.info("Нет позиций по выбранным фильтрам.")
else:
    work_df = prepare_scope_work_df(filtered.copy())
    scope_table = build_scope_table(work_df)
    rk_list = scope_table["_rk"].tolist()
    display_df = scope_table.drop(columns=["_rk"])
    selected_key = st.session_state.get(SELECTED_RK_KEY) or ""
    selected_row_idx = rk_list.index(selected_key) if selected_key in rk_list else None

    st.caption(
        "Кликните строку в таблице или нажмите «Открыть код» — ниже откроется детальная карточка."
    )
    styled_table = apply_scope_table_style(display_df, selected_row_idx=selected_row_idx)
    table_event = st.dataframe(
        styled_table,
        use_container_width=True,
        hide_index=True,
        height=min(520, 42 + len(display_df) * 35),
        on_select="rerun",
        selection_mode="single-row",
        key="scope_boq_table",
    )
    selected_rows = (
        getattr(table_event.selection, "rows", [])
        if table_event and table_event.selection
        else []
    )
    if selected_rows:
        selected_idx = selected_rows[0]
        if 0 <= selected_idx < len(rk_list):
            st.session_state[SELECTED_RK_KEY] = rk_list[selected_idx]
        else:
            st.warning("Выбранная строка вне диапазона. Обновите выбор в таблице.")
    else:
        st.info("Выберите BOQ-код в таблице или нажмите кнопку открытия кода ниже.")

    with st.expander("Быстрое открытие кодов", expanded=False):
        total_rows = len(work_df)
        total_pages = max(1, (total_rows - 1) // SCOPE_TABLE_PAGE_SIZE + 1)
        page_num = st.number_input(
            "Страница списка",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key="scope_table_page",
        )
        st.caption(
            f"Строки {(page_num - 1) * SCOPE_TABLE_PAGE_SIZE + 1}–"
            f"{min(int(page_num) * SCOPE_TABLE_PAGE_SIZE, total_rows)} из {total_rows}"
        )

        hdr = st.columns([2.2, 3.5, 1.2, 1.2, 1.0, 0.9])
        hdr[0].markdown('<div class="quick-open-header">Код</div>', unsafe_allow_html=True)
        hdr[1].markdown('<div class="quick-open-header">Наименование</div>', unsafe_allow_html=True)
        hdr[2].markdown(
            '<div class="quick-open-header">Остаток объёма</div>', unsafe_allow_html=True
        )
        hdr[3].markdown('<div class="quick-open-header">Остаток, %</div>', unsafe_allow_html=True)
        hdr[4].markdown('<div class="quick-open-header">Титул</div>', unsafe_allow_html=True)
        hdr[5].markdown('<div class="quick-open-header">Действие</div>', unsafe_allow_html=True)

        page_start = (int(page_num) - 1) * SCOPE_TABLE_PAGE_SIZE
        page_slice = work_df.iloc[page_start : page_start + SCOPE_TABLE_PAGE_SIZE]
        for _, prow in page_slice.iterrows():
            prk = prow["_rk"]
            pct = percent_fmt(
                prow.get("available_remaining_qty", prow.get("planning_remaining_qty")),
                prow.get("total_project_qty"),
            )
            rem = qty_fmt(prow.get("available_remaining_qty", prow.get("planning_remaining_qty")))
            btn_cols = st.columns([2.2, 3.5, 1.2, 1.2, 1.0, 0.9])
            btn_cols[0].markdown(f"**{prow.get('boq_code')}**")
            btn_cols[1].caption(str(prow.get("boq_name") or "")[:70])
            btn_cols[2].write(rem)
            btn_cols[3].write(pct)
            btn_cols[4].write(str(prow.get("facility_building") or "")[:18])
            if btn_cols[5].button("Открыть код", key=f"open_boq_{prk}", type="secondary"):
                st.session_state[SELECTED_RK_KEY] = prk
                st.rerun()

    selected_key = st.session_state.get(SELECTED_RK_KEY) or ""
    if selected_key:
        selected_row = get_row_by_key(work_df, selected_key)
        if selected_row is not None:
            hide_col, _ = st.columns([1.2, 4])
            with hide_col:
                if st.button("Скрыть карточку кода", key="hide_boq_card", type="secondary"):
                    st.session_state[SELECTED_RK_KEY] = ""
                    st.rerun()
            st.markdown("#### Карточка кода")
            render_detail_card(selected_row, crew_options)
        else:
            st.session_state[SELECTED_RK_KEY] = ""

st.divider()
hydrate_saved_draft_lines_for_month(selected_planning_month, sel_project)
render_draft_panel(data, crew_options, sel_project)
render_saved_plans_block()

with st.expander("Показать исходные данные", expanded=False):
    st.dataframe(filtered, use_container_width=True, hide_index=True)
