# ============================================================
# Конструктор месячного плана — выбор остатков BoQ
# Источник: public.monthly_scope_picker_view
# Корректировки: public.monthly_scope_manual_adjustments
# ============================================================

import html as html_lib
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from services.supabase_client import supabase

SCOPE_VIEW = "monthly_scope_picker_view"
ADJUSTMENTS_TABLE = "monthly_scope_manual_adjustments"
DRAFT_KEY = "monthly_plan_draft_items"
SELECTED_RK_KEY = "scope_selected_boq_rk"
CUSTOMER_ACCEPTED_KEY = "monthly_scope_customer_accepted"
SCOPE_TABLE_PAGE_SIZE = 25

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

CONFIDENCE_RU = {
    "HIGH": ("Данных достаточно", "badge-conf-high"),
    "MEDIUM": ("Данных средне", "badge-conf-medium"),
    "LOW": ("Данных мало", "badge-conf-low"),
}
NO_HISTORY_NORM_TEXT = "Истории нет — требуется ручная норма"

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


@st.cache_data(ttl=300)
def load_scope(limit: int = 10000) -> pd.DataFrame:
    response = supabase.table(SCOPE_VIEW).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


@st.cache_data(ttl=120)
def load_adjustments(limit: int = 10000) -> pd.DataFrame:
    try:
        response = supabase.table(ADJUSTMENTS_TABLE).select("*").limit(limit).execute()
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
    col_rem = "Остаток объёма"
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
    if "Остаток объёма" in display_df.columns and "Остаток, %" in display_df.columns:
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
    exec_val = (
        pd.to_numeric(df["executed_value_all_time"], errors="coerce").fillna(0).sum()
        if "executed_value_all_time" in df.columns
        else 0.0
    )
    rem_val = (
        pd.to_numeric(df["planning_remaining_value"], errors="coerce").fillna(0).sum()
        if "planning_remaining_value" in df.columns
        else 0.0
    )
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
    adj = adjustments.copy() if not adjustments.empty else pd.DataFrame()
    adj_applied = False

    if not adj.empty:
        for col in merge_keys:
            if col in adj.columns:
                adj[col] = adj[col].astype(str).str.strip()
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
                if col.startswith("manual_") and df[col].notna().any():
                    adj_applied = True

    for col in (
        "manual_executed_before_system",
        "manual_verified_remaining_qty",
        "adjustment_reason",
        "comment",
    ):
        if col not in df.columns:
            df[col] = None

    has_view_planning = (
        "planning_remaining_qty" in df.columns and df["planning_remaining_qty"].notna().any()
    )
    need_planning_recalc = not has_view_planning or adj_applied

    if need_planning_recalc:
        planning_qty = []
        sources = []
        for _, r in df.iterrows():
            total = safe_float(r.get("total_project_qty")) or 0.0
            executed = safe_float(r.get("executed_qty_all_time")) or 0.0
            system_rem = safe_float(r.get("system_remaining_qty")) or 0.0
            m_exec = safe_float(r.get("manual_executed_before_system")) or 0.0
            m_ver = safe_float(r.get("manual_verified_remaining_qty"))

            if m_ver is not None:
                planning_qty.append(m_ver)
                sources.append("MANUAL_VERIFIED")
            elif m_exec > 0:
                planning_qty.append(max(total - executed - m_exec, 0.0))
                sources.append("MANUAL_EXECUTED_BEFORE_SYSTEM")
            else:
                planning_qty.append(max(system_rem, 0.0))
                sources.append("SYSTEM_CALCULATED")

        df["planning_remaining_qty"] = planning_qty
        df["remaining_qty_source"] = sources
    elif "remaining_qty_source" not in df.columns:
        df["remaining_qty_source"] = "SYSTEM_CALCULATED"

    if "planning_remaining_value" not in df.columns:
        unit_price = df["unit_price"].fillna(0) if "unit_price" in df.columns else 0
        df["planning_remaining_value"] = df["planning_remaining_qty"] * unit_price
    else:
        unit_price = df["unit_price"].fillna(0) if "unit_price" in df.columns else 0
        df["planning_remaining_value"] = df["planning_remaining_value"].fillna(
            df["planning_remaining_qty"] * unit_price
        )

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


def apply_filters(
    df: pd.DataFrame,
    project: str,
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
    if facility != "Все" and "facility_building" in out.columns:
        out = out[out["facility_building"].astype(str) == facility]
    if discipline != "Все" and "construction_discipline" in out.columns:
        out = out[out["construction_discipline"].astype(str) == discipline]
    if norm_status != "Все" and "norm_status" in out.columns:
        out = out[out["norm_status"].astype(str) == norm_status]
    if search.strip():
        q = search.strip().lower()
        mask = (
            out["boq_code"].astype(str).str.lower().str.contains(q, na=False)
            | out["boq_name"].astype(str).str.lower().str.contains(q, na=False)
        )
        out = out[mask]
    if "planning_remaining_qty" in out.columns:
        qty_num = pd.to_numeric(out["planning_remaining_qty"], errors="coerce")
        if display_mode == "Только коды с остатком > 0":
            out = out[qty_num > 0]
        elif display_mode == "Закрытые коды = 0":
            out = out[qty_num == 0]
        elif display_mode == "Перевыполненные коды < 0":
            out = out[qty_num < 0]
    return out


def view_has_nonpositive_remaining(df: pd.DataFrame) -> bool:
    if df.empty or "planning_remaining_qty" not in df.columns:
        return False
    qty = pd.to_numeric(df["planning_remaining_qty"], errors="coerce")
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

    table = pd.DataFrame(
        {
            "Код BoQ": out["boq_code"],
            "Наименование": out["boq_name"],
            "Титул": out["facility_building"],
            "Дисциплина": out["construction_discipline"],
            "Всего по BOQ": out["total_project_qty"].apply(qty_fmt),
            "Выполнено по факту": out["executed_qty_all_time"].apply(qty_fmt),
            "Остаток объёма": out["planning_remaining_qty"].apply(qty_fmt),
            "Остаток, %": out.apply(
                lambda r: percent_fmt(
                    r.get("planning_remaining_qty"), r.get("total_project_qty")
                ),
                axis=1,
            ),
            "Остаток, ₽": out["planning_remaining_value"].apply(money),
            "История нормы": out["norm_status"].apply(norm_status_label),
            "Источник остатка": out["remaining_qty_source"].apply(
                lambda x: source_badge_label(str(x))
            ),
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
        "facility_building": row.get("facility_building"),
        "construction_discipline": row.get("construction_discipline"),
        "boq_code": str(row.get("boq_code", "")).strip(),
        "manual_executed_before_system": safe_float(manual_exec),
        "manual_verified_remaining_qty": safe_float(manual_verified),
        "reason": reason.strip() if reason else None,
        "comment": comment.strip() if comment else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return write_client.table(ADJUSTMENTS_TABLE).upsert(
        payload,
        on_conflict="project_code,facility_building,construction_discipline,boq_code",
    ).execute()


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

    st.markdown(
        f"""
        <div class="detail-card">
            <div class="scope-title">{esc(row.get("boq_code"))} · {esc(row.get("boq_name"))}</div>
            <div style="margin:8px 0 4px 0;">
                <span class="scope-badge badge-system">{esc(row.get("facility_building"))}</span>
                <span class="scope-badge badge-system" style="margin-left:6px;">{esc(row.get("construction_discipline"))}</span>
                <span class="scope-badge {norm_cls}" style="margin-left:6px;">{esc(norm)}</span>
                <span class="scope-badge {src_cls}" style="margin-left:6px;">{esc(src_label)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        section_title("Объём и деньги")
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("Всего", qty_fmt(row.get("total_project_qty")))
        v2.metric("Выполнено", qty_fmt(row.get("executed_qty_all_time")))
        v3.metric("Остаток", qty_fmt(row.get("planning_remaining_qty")))
        v4.metric("Остаток ₽", money(row.get("planning_remaining_value")))

    with st.container(border=True):
        section_title("Историческая производительность")
        render_productivity_block(row)

    with st.container(border=True):
        section_title("Системы и пакеты")
        render_systems_block(row)

    rk_full = row_key(row)
    total_qty = safe_float(row.get("total_project_qty")) or 0.0
    executed_qty = safe_float(row.get("executed_qty_all_time")) or 0.0
    accepted_default = get_customer_accepted_qty(rk_full)

    with st.container(border=True):
        section_title("Признание заказчиком")
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

    with st.container(border=True):
        section_title("Корректировка остатка")
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
                save_adjustment(row, inp_exec, verified_val, inp_reason, inp_comment)
                load_adjustments.clear()
                st.success("Корректировка сохранена.")
                st.rerun()
            except Exception as exc:
                st.error(f"Ошибка сохранения: {exc}")

    with st.container(border=True):
        section_title("Добавить в черновик планирования")
        p1, p2, p3 = st.columns(3)
        with p1:
            plan_month = st.text_input("Месяц планирования", key=f"plan_month_{rk}")
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

        planning_max = safe_float(row.get("planning_remaining_qty")) or 0.0
        unit_price = safe_float(row.get("unit_price")) or 0.0

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

        if plan_qty > planning_max > 0:
            st.warning(
                f"Плановый объём ({qty_fmt(plan_qty)}) больше остатка для планирования "
                f"({qty_fmt(planning_max)})."
            )
        elif plan_qty > 0 and planning_max <= 0:
            st.warning("Остаток для планирования равен нулю.")

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

        if st.button("Добавить в черновик", key=f"add_draft_{rk}"):
            if plan_qty <= 0:
                st.warning("Укажите плановый объём больше нуля.")
            elif not str(plan_month).strip():
                st.warning("Укажите месяц планирования.")
            elif planning_max > 0 and plan_qty > planning_max:
                st.warning("Сначала уменьшите объём до остатка для планирования.")
            else:
                draft_item = {
                    "project_code": row.get("project_code"),
                    "boq_code": row.get("boq_code"),
                    "boq_name": row.get("boq_name"),
                    "facility_building": row.get("facility_building"),
                    "construction_discipline": row.get("construction_discipline"),
                    "month_key": str(plan_month).strip(),
                    "crew_code": str(plan_crew).strip() if plan_crew else "",
                    "planned_qty": plan_qty,
                    "plan_value": plan_value,
                    "required_hours": req_hours or 0.0,
                    "norm_scenario": scenario_code,
                    "unit_of_measure": row.get("unit_of_measure"),
                    "comment": plan_comment,
                    "customer_accepted_qty": customer_accepted,
                    "recognition_remaining_qty": recognition_remaining,
                }
                item_key = row_key(row)
                month_str = str(plan_month).strip()
                kept = [
                    d
                    for d in st.session_state[DRAFT_KEY]
                    if not (
                        row_key(pd.Series(d)) == item_key
                        and str(d.get("month_key", "")).strip() == month_str
                    )
                ]
                kept.append(draft_item)
                st.session_state[DRAFT_KEY] = kept
                st.success("Строка добавлена в черновик.")
                st.rerun()


def render_draft_panel():
    st.markdown('<div class="draft-panel-block">', unsafe_allow_html=True)
    st.markdown('<h2 class="draft-panel-title">Черновик месячного плана</h2>', unsafe_allow_html=True)
    draft: list[dict] = st.session_state[DRAFT_KEY]

    if not draft:
        st.caption("Черновик пуст. Добавьте позиции из карточки кода.")
    else:
        show = pd.DataFrame(
            {
                "Код": [d.get("boq_code") for d in draft],
                "Титул": [d.get("facility_building") for d in draft],
                "Дисциплина": [d.get("construction_discipline") for d in draft],
                "Месяц": [d.get("month_key") for d in draft],
                "Звено": [d.get("crew_code") for d in draft],
                "Объём": [qty_fmt(d.get("planned_qty")) for d in draft],
                "Плановая стоимость": [money(d.get("plan_value")) for d in draft],
                "Требуемые чел-часы": [hours_fmt(d.get("required_hours")) for d in draft],
                "Сценарий нормы": [
                    {
                        "P50": NORM_SCENARIO_REALISTIC,
                        "P80": NORM_SCENARIO_CAUTIOUS,
                        "Ручной": NORM_SCENARIO_MANUAL,
                    }.get(d.get("norm_scenario"), d.get("norm_scenario"))
                    for d in draft
                ],
            }
        )
        st.dataframe(show, use_container_width=True, hide_index=True, height=min(180, 36 + len(draft) * 32))

        total_ev = sum(safe_float(x.get("plan_value")) or 0 for x in draft)
        total_hours = sum(safe_float(x.get("required_hours")) or 0 for x in draft)
        m1, m2, m3 = st.columns(3)
        m1.metric("Строк", len(draft))
        m2.metric("Плановая стоимость всего", money(total_ev))
        m3.metric("Требуемые чел-часы всего", hours_fmt(total_hours))

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        if st.button("Очистить черновик", key="clear_draft", use_container_width=True):
            st.session_state[DRAFT_KEY] = []
            st.rerun()
    with b2:
        if st.button("Изменить черновик", key="edit_draft", use_container_width=True):
            st.info("Изменение строк черновика будет добавлено следующим шагом.")
    with b3:
        if st.button("Сохранить черновик", key="save_draft", use_container_width=True):
            st.info("Следующий этап: сохранение черновика в Supabase.")
    with b4:
        if st.button(
            "Отправить в контур допуска и проверки",
            key="send_draft_approval",
            use_container_width=True,
        ):
            st.info(
                "Черновик месячного плана будет передан в контур допуска и проверки. Следующие этапы:\n"
                "1. Проверка остатка по BoQ: не превышает ли план подтверждённый остаток.\n"
                "2. Проверка исторической нормы: есть ли данные P50/P80 или нужна ручная норма.\n"
                "3. Проверка мощности звена: хватает ли человеко-часов.\n"
                "4. Проверка исполнимости фронта: РД, МТР, доступ, смежники, допуски.\n"
                "5. Проверка признаваемости: можно ли будет предъявить объём к КС/приёмке.\n"
                "6. Передача в AI Диагностику плана и AI Action Engine."
            )

    st.markdown("</div>", unsafe_allow_html=True)


# --- main ---
if DRAFT_KEY not in st.session_state:
    st.session_state[DRAFT_KEY] = []
if CUSTOMER_ACCEPTED_KEY not in st.session_state:
    st.session_state[CUSTOMER_ACCEPTED_KEY] = {}
if SELECTED_RK_KEY not in st.session_state:
    st.session_state[SELECTED_RK_KEY] = ""

scope_raw = load_scope()
adjustments_raw = load_adjustments()
crew_options = load_crew_options()

if scope_raw.empty:
    st.warning(f"Витрина {SCOPE_VIEW} пуста. Выполните SQL monthly_scope_picker_v1.sql в Supabase.")
    st.stop()

data = merge_adjustments(scope_raw, adjustments_raw)

f1, f2, f3, f4, f5, f6 = st.columns([1.1, 1.1, 1.1, 1.0, 1.3, 1.2])
with f1:
    sel_project = st.selectbox("Проект", project_filter_options(data))
with f2:
    sel_facility = st.selectbox("Титул / объект", filter_options(data, "facility_building"))
with f3:
    sel_discipline = st.selectbox("Дисциплина", filter_options(data, "construction_discipline"))
with f4:
    sel_norm = st.selectbox("Статус нормы", NORM_STATUS_OPTIONS)
with f5:
    search_text = st.text_input("Поиск по BoQ-коду или названию")
with f6:
    display_mode = st.radio(
        "Режим отображения кодов",
        DISPLAY_MODE_OPTIONS,
        index=1,
    )

filtered = apply_filters(
    data, sel_project, sel_facility, sel_discipline, sel_norm, search_text, display_mode
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
        height=min(420, 42 + len(display_df) * 35),
        on_select="rerun",
        selection_mode="single-row",
        key="scope_boq_table",
    )
    if table_event.selection.rows:
        st.session_state[SELECTED_RK_KEY] = rk_list[table_event.selection.rows[0]]

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
            pct = percent_fmt(prow.get("planning_remaining_qty"), prow.get("total_project_qty"))
            rem = qty_fmt(prow.get("planning_remaining_qty"))
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
            st.markdown("#### Карточка кода")
            render_detail_card(selected_row, crew_options)
        else:
            st.session_state[SELECTED_RK_KEY] = ""

st.divider()
render_draft_panel()

with st.expander("Показать исходные данные"):
    st.dataframe(filtered, use_container_width=True, hide_index=True)
