# ============================================================
# CREW PLAN BURNDOWN — LAYER 1
# Управленческий слой: Month + Crew (+ Week/Day из Daily Progress).
#
# Layer 1: финансово-ресурсный счётчик звена (план месяца vs факт).
# Layer 2: Month → Week → Day → Crew → BOQ → IWP → System → Operation → Unit
#   Три контура: EV/ч, объём BOQ/ч, операции/ч.
# ============================================================

import html as html_lib
from calendar import monthrange
from datetime import date

import pandas as pd
import streamlit as st
from services.supabase_client import supabase


def normalize_html(html: str) -> str:
    """
    Убирает ведущие пробелы в каждой строке.
    Иначе Streamlit Markdown трактует отступы перед <div> как code block
    и показывает сырой HTML (<div style=...>).
    """
    if not html:
        return ""
    return "\n".join(line.lstrip() for line in html.strip().splitlines())


def render_html(html: str) -> None:
    if not html:
        return
    st.markdown(normalize_html(html), unsafe_allow_html=True)


def esc(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return html_lib.escape(str(value))


# --- design tokens ---
C_BG = "#ffffff"
C_BORDER = "#E5E7EB"
C_TEXT = "#111827"
C_MUTED = "#6B7280"
C_BLUE = "#2563EB"
C_GREEN = "#16A34A"
C_AMBER = "#D97706"
C_RED = "#DC2626"
C_GRAY = "#6B7280"

st.set_page_config(layout="wide")

VIEW_NAME = "v_crew_burndown_with_fact"
DP_TABLE = "daily_progress_active"
LABOR_TABLE = "monthly_labor_summary"
FACT_PENDING_STATUS = "Факт ещё не поступил"
MOBILIZED_NO_REPORT_STATUS = "MOBILIZED_NO_REPORT"
MOBILIZED_NO_REPORT_TEXT = (
    "Мобилизовано, но нет Daily Progress"
)
MOBILIZED_NO_REPORT_EXPLANATION = (
    "Звено числится мобилизованным, но за выбранный период нет ни одной записи "
    "Daily Progress. Нужно проверить: работа не велась, простой не зафиксирован "
    "или мастер не подаёт отчёт."
)
MOBILIZED_HEADER_NOTE = "Звено мобилизовано, но Daily Progress отсутствует"

MONTH_NAME_TO_NUM = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}

LAYER_INFO = (
    "**Layer 1** — burn-down звена по месяцу: план работ, direct часы/cost, прогноз, состав. "
    "Фильтры «Неделя» и «День» сужают **факт** из Daily Progress; план остаётся месячным. "
    "**Layer 2** — Month → Week → Day → Crew → BOQ → IWP → System → Operation → Unit: "
    "EV/ч, объём BOQ/ч и операции/ч (реальная работа звена до финального BOQ-объёма)."
)

LAYER2_WARNING = (
    "Layer 2 показывает три разные производительности: деньги/ч, объём/ч и операции/ч. "
    "Операции нужны, чтобы видеть реальную работу звена до появления финального BOQ-объёма "
    "и признанного EV."
)

LAYER2_INTRO = (
    "Layer 2 показывает, из чего состоит факт звена: какие BOQ-коды, IWP, системы и операции "
    "попали в Daily Progress. Это не полный план-факт. Это операционный разбор факта. "
    "Сверка «из скольких плановых BOQ/IWP выполнено» будет добавлена после подключения "
    "monthly_passport_plan и Allowed_Operations."
)

LAYER2_OPERATION_WARNING = (
    "Важно: если «Выполнено операций» = 0, а операция указана, значит на площадке выбрали тип "
    "операции, но не заполнили количество операции. Такая строка полезна как факт выполнения "
    "операции, но не позволяет посчитать операционную выработку."
)

LAYER2_TABLE_HEADERS = [
    "BOQ-код",
    "Наименование работ",
    "IWP / пакет",
    "Система / зона",
    "Операция",
    "Ед. операции",
    "Выполнено операций",
    "Операционная выработка, ед/чел-ч",
    "Ед. BOQ",
    "Выполненный BOQ-объём",
    "Физическая выработка, ед/чел-ч",
    "EV / стоимость факта",
    "Денежная выработка, ₽/чел-ч",
    "Direct часы",
    "Простой",
    "Записей DP",
    "Комментарий качества данных",
]

LAYER2_GROUP_COLS = [
    "boq_code",
    "boq_name",
    "iwp",
    "system",
    "operation_type",
    "operation_unit",
    "unit",
]

NUMERIC_COLS = [
    "plan_work_value_month",
    "plan_direct_hours_month",
    "plan_direct_cost_month",
    "actual_work_value",
    "actual_direct_hours",
    "actual_direct_cost",
    "actual_qty_total",
    "remaining_work_value",
    "remaining_direct_hours",
    "remaining_direct_cost",
    "work_value_burn_pct",
    "direct_hours_burn_pct",
    "direct_cost_burn_pct",
    "margin_after_direct",
    "direct_cost_share",
    "fact_rows",
]

DP_SELECT_COLS = [
    "month_key",
    "created_time",
    "project_code",
    "crew_id",
    "boq",
    "boq_name",
    "unit_of_measure",
    "quantity_today",
    "direct_work_hours",
    "ev_day_value",
    "ac_day_value",
    "idle_hours",
    "facility_building",
    "construction_discipline",
    "iwp_id",
    "system_label",
    "operation_type",
    "operation_quantity",
    "operation_main_parameter",
]

DP_NUMERIC_COLS = [
    "direct_work_hours",
    "ev_day_value",
    "ac_day_value",
    "quantity_today",
    "idle_hours",
    "operation_quantity",
]

RISK_LABELS = {
    "OK": "OK",
    "MEDIUM_DIRECT_COST": "MEDIUM",
    "HIGH_DIRECT_COST": "HIGH",
    "CRITICAL_DIRECT_LOSS": "CRITICAL",
    "NO_LABOR_DATA": "NO DATA",
    "MOBILIZED_NO_REPORT": "MOBILIZED / NO DP",
}

RISK_COLORS = {
    "OK": C_GREEN,
    "MEDIUM_DIRECT_COST": C_AMBER,
    "HIGH_DIRECT_COST": C_AMBER,
    "CRITICAL_DIRECT_LOSS": C_RED,
    "NO_LABOR_DATA": C_GRAY,
    "MOBILIZED_NO_REPORT": "#991B1B",
}

FORECAST_LABELS = {
    "ON_TRACK": "ON TRACK",
    "AT_RISK": "AT RISK",
    "LOSS": "LOSS",
    "NO_FACT": "NO FACT",
}

FORECAST_COLORS = {
    "ON_TRACK": C_GREEN,
    "AT_RISK": C_AMBER,
    "LOSS": C_RED,
    "NO_FACT": C_GRAY,
}

FORECAST_TEXTS = {
    "NO_FACT": "Недостаточно факта для прогноза.",
    "ON_TRACK": "Прогноз с ограничением планом: план работ закрывается, маржа положительная.",
    "AT_RISK": "Прогноз с ограничением планом: риск недоосвоения плана, маржа положительная.",
    "LOSS": "Прогнозная маржа после direct ≤ 0 — риск сжигания cost быстрее результата.",
}

PAGE_CSS = f"""
<style>
    .block-container {{ padding-top: 1rem; padding-bottom: 1.25rem; max-width: 100%; }}
    div[data-testid="stVerticalBlock"] > div {{ gap: 0.2rem; }}
    h5 {{ font-size: 0.9rem !important; color: {C_TEXT}; margin: 0.5rem 0 0.35rem !important; }}
    section.main div[data-testid="stHorizontalBlock"]:has([data-testid="stSelectbox"]) [data-testid="stSelectbox"] > div {{
        max-width: 168px;
    }}
    section.main [data-testid="stSelectbox"] label {{
        font-size: 11px !important;
        color: {C_MUTED} !important;
        padding-bottom: 1px !important;
        margin-bottom: 0 !important;
    }}
    section.main [data-baseweb="select"] > div {{
        min-height: 32px !important;
        font-size: 13px !important;
    }}
    section.main [data-testid="stButton"] button {{
        min-height: 32px !important;
        padding: 0 10px !important;
        border-color: {C_BORDER} !important;
        color: {C_TEXT} !important;
    }}
    section.main [data-testid="column"] {{
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }}
</style>
"""


@st.cache_data(ttl=300)
def load_burndown(limit: int = 5000) -> pd.DataFrame:
    response = supabase.table(VIEW_NAME).select("*").limit(limit).execute()
    df = pd.DataFrame(response.data or [])
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def enrich_dp_dates(df: pd.DataFrame) -> pd.DataFrame:
    """work_date и week_key — только из created_time (в Supabase их нет)."""
    df = df.copy()
    if "created_time" not in df.columns:
        df["work_date"] = None
        df["week_key"] = None
        return df

    dt = pd.to_datetime(df["created_time"], errors="coerce", utc=True)
    df["work_date"] = dt.dt.date
    df.loc[dt.isna(), "work_date"] = None
    df["week_key"] = dt.dt.strftime("%G-W%V")
    df.loc[dt.isna(), "week_key"] = None
    return df


@st.cache_data(ttl=300)
def load_daily_progress(limit: int = 15000) -> pd.DataFrame:
    response = (
        supabase.table(DP_TABLE).select(",".join(DP_SELECT_COLS)).limit(limit).execute()
    )
    df = pd.DataFrame(response.data or [])
    for col in DP_NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = enrich_dp_dates(df)
    if "crew_id" in df.columns:
        df["crew_id"] = df["crew_id"].astype(str).str.strip()
    if "month_key" in df.columns:
        df["month_key"] = df["month_key"].astype(str).str.strip()
    if "week_key" in df.columns:
        mask = df["week_key"].notna()
        df.loc[mask, "week_key"] = df.loc[mask, "week_key"].astype(str).str.strip()
    return df


@st.cache_data(ttl=300)
def load_labor_summary(limit: int = 8000) -> pd.DataFrame:
    cols = (
        "month_key,crew_code,full_name_ru,role,direct_hours_month,"
        "direct_cost_rub_month,budget_status,actual_mobilization_date"
    )
    response = supabase.table(LABOR_TABLE).select(cols).limit(limit).execute()
    df = pd.DataFrame(response.data or [])
    for col in ("direct_hours_month", "direct_cost_rub_month"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "actual_mobilization_date" in df.columns:
        df["actual_mobilization_date"] = pd.to_datetime(
            df["actual_mobilization_date"], errors="coerce"
        ).dt.date
    if "crew_code" in df.columns:
        df["crew_code"] = df["crew_code"].astype(str).str.strip()
    if "month_key" in df.columns:
        df["month_key"] = df["month_key"].astype(str).str.strip()
    return df


def safe_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def norm_str(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def money(value):
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.0f} ₽".replace(",", " ")


def money_per_hour(value):
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.0f} ₽/ч".replace(",", " ")


def hours_fmt(value):
    v = safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.1f} чел-ч".replace(",", " ")


def pct_fmt(value, as_ratio: bool = True):
    v = safe_float(value)
    if v is None:
        return "—"
    pct = v * 100 if as_ratio else v
    return f"{pct:.1f}%"


def burn_ratio(fact, planned):
    f = safe_float(fact)
    p = safe_float(planned)
    if p is None or p == 0:
        return None
    if f is None:
        f = 0.0
    return f / p


def get_burn_color(pct) -> str:
    """Semantic color for progress bar; pct — доля плана в процентах (0–100+)."""
    if pct is None:
        return C_GRAY
    if pct < 25:
        return "#2563EB"  # blue
    if pct < 60:
        return "#16A34A"  # green
    if pct < 85:
        return "#EAB308"  # yellow
    if pct <= 100:
        return "#D97706"  # amber
    return "#DC2626"  # red


def burn_pct_percent(ratio: float | None) -> float:
    if ratio is None:
        return 0.0
    return ratio * 100


def calc_burn_pcts(row: pd.Series) -> dict:
    return {
        "work": burn_ratio(
            row.get("actual_work_value"), row.get("plan_work_value_month")
        ),
        "hours": burn_ratio(
            row.get("actual_direct_hours"), row.get("plan_direct_hours_month")
        ),
        "cost": burn_ratio(
            row.get("actual_direct_cost"), row.get("plan_direct_cost_month")
        ),
    }


def remaining_value(plan, fact):
    p = safe_float(plan)
    f = safe_float(fact) or 0.0
    if p is None:
        return None
    return p - f


def has_burn_fact(row: pd.Series) -> bool:
    fact_rows = safe_float(row.get("fact_rows")) or 0.0
    if fact_rows > 0:
        return True
    for col in ("actual_work_value", "actual_direct_hours", "actual_direct_cost"):
        v = safe_float(row.get(col))
        if v is not None and v != 0:
            return True
    return False


def qty_fmt(value):
    v = safe_float(value)
    if v is None:
        return "0"
    return f"{v:,.1f}".replace(",", " ")


def num_fmt(value, decimals: int = 2) -> str:
    v = safe_float(value)
    if v is None:
        return "0"
    return f"{v:,.{decimals}f}".replace(",", " ")


def per_direct_hour(numerator, direct_hours) -> float:
    hours = safe_float(direct_hours) or 0.0
    if hours <= 0:
        return 0.0
    return (safe_float(numerator) or 0.0) / hours


def series_from_cols(df: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in df.columns:
            s = df[name].fillna("").astype(str).str.strip()
            return s.replace({"nan": "", "None": "", "<NA>": ""})
    return pd.Series([""] * len(df), index=df.index, dtype=object)


def numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(0.0, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def resolve_ev_series(df: pd.DataFrame) -> pd.Series:
    for col in ("ev_day_value", "ev_value", "work_value", "actual_work_value"):
        if col in df.columns:
            return numeric_series(df, col)
    return pd.Series(0.0, index=df.index, dtype=float)


def prepare_layer2_data(dp: pd.DataFrame) -> pd.DataFrame:
    if dp.empty:
        return dp
    out = dp.copy()
    out["boq_code"] = series_from_cols(out, "boq", "boq_code")
    out["boq_name"] = series_from_cols(out, "boq_name")
    out["iwp"] = series_from_cols(out, "iwp_id", "iwp_id_export")
    out["system"] = series_from_cols(out, "system_label", "system_label_iwp")
    out["operation_type"] = series_from_cols(out, "operation_type")
    out["operation_unit"] = series_from_cols(
        out, "operation_main_parameter", "operation_unit"
    )
    out["unit"] = series_from_cols(out, "unit_of_measure")
    out["volume_done"] = numeric_series(out, "quantity_today")
    out["operation_done"] = numeric_series(out, "operation_quantity")
    out["ev_value"] = resolve_ev_series(out)
    out["direct_hours"] = numeric_series(out, "direct_work_hours")
    out["idle_hours"] = numeric_series(out, "idle_hours")
    return out


def build_layer2_aggregate(prepared: pd.DataFrame) -> pd.DataFrame:
    if prepared.empty:
        return pd.DataFrame()

    grouped = prepared.groupby(LAYER2_GROUP_COLS, dropna=False)
    agg = grouped.agg(
        volume_done=("volume_done", "sum"),
        operation_done=("operation_done", "sum"),
        ev_value=("ev_value", "sum"),
        direct_hours=("direct_hours", "sum"),
        idle_hours=("idle_hours", "sum"),
    ).reset_index()
    agg["dp_rows"] = grouped.size().reset_index(drop=True)

    agg["ev_per_direct_hour"] = agg.apply(
        lambda r: per_direct_hour(r["ev_value"], r["direct_hours"]), axis=1
    )
    agg["volume_per_direct_hour"] = agg.apply(
        lambda r: per_direct_hour(r["volume_done"], r["direct_hours"]), axis=1
    )
    agg["operation_per_direct_hour"] = agg.apply(
        lambda r: per_direct_hour(r["operation_done"], r["direct_hours"]), axis=1
    )
    return agg.sort_values(
        ["ev_value", "direct_hours", "boq_code"],
        ascending=[False, False, True],
        na_position="last",
    )


def unique_nonempty(series: pd.Series) -> list[str]:
    vals = series.fillna("").astype(str).str.strip()
    return sorted({v for v in vals if v and v.lower() not in {"nan", "none"}})


def format_physical_productivity(
    total_volume: float, total_hours: float, boq_units: int, single_unit: str
) -> tuple[str, str]:
    hint = "BOQ quantity / direct часы"
    if total_hours <= 0:
        return "—", hint
    if boq_units > 1:
        return "разные ед.", "Нельзя усреднять разные единицы BOQ"
    rate = per_direct_hour(total_volume, total_hours)
    if single_unit:
        return f"{num_fmt(rate)} {single_unit}/чел-ч", hint
    return num_fmt(rate), hint


def productivity_rate_display(
    numerator: float, total_hours: float, unique_units: list[str]
) -> str:
    if total_hours <= 0:
        return "—"
    if len(unique_units) > 1:
        return "разные ед."
    return num_fmt(per_direct_hour(numerator, total_hours))


def layer2_summary_stats(prepared: pd.DataFrame, agg: pd.DataFrame) -> dict:
    if prepared.empty:
        return {
            "boq_codes": 0,
            "iwps": 0,
            "operations": 0,
            "boq_units": 0,
            "operation_units": 0,
            "total_direct_hours": 0.0,
            "total_ev": 0.0,
            "total_boq_volume": 0.0,
            "total_operation_done": 0.0,
            "single_boq_unit": "",
            "avg_ev_per_hour": None,
            "avg_physical_per_hour": None,
            "avg_operation_per_hour": None,
            "physical_display": "—",
            "physical_hint": "BOQ quantity / direct часы",
        }

    boq_mask = prepared["boq_code"] != ""
    iwp_mask = prepared["iwp"] != ""
    op_mask = prepared["operation_type"] != ""
    unit_mask = prepared["unit"] != ""
    op_unit_mask = prepared["operation_unit"] != ""

    total_hours = float(prepared["direct_hours"].sum())
    total_ev = float(prepared["ev_value"].sum())
    total_volume = float(prepared["volume_done"].sum())
    total_operation = float(prepared["operation_done"].sum())

    boq_unit_list = unique_nonempty(prepared.loc[unit_mask, "unit"])
    boq_units = len(boq_unit_list)
    single_boq_unit = boq_unit_list[0] if boq_units == 1 else ""

    avg_ev = per_direct_hour(total_ev, total_hours) if total_hours > 0 else None
    avg_physical = (
        per_direct_hour(total_volume, total_hours) if total_hours > 0 else None
    )
    avg_operation = (
        per_direct_hour(total_operation, total_hours) if total_hours > 0 else None
    )
    physical_display, physical_hint = format_physical_productivity(
        total_volume, total_hours, boq_units, single_boq_unit
    )

    return {
        "boq_codes": int(prepared.loc[boq_mask, "boq_code"].nunique()),
        "iwps": int(prepared.loc[iwp_mask, "iwp"].nunique()),
        "operations": int(prepared.loc[op_mask, "operation_type"].nunique()),
        "boq_units": boq_units,
        "operation_units": int(
            prepared.loc[op_unit_mask, "operation_unit"].nunique()
        ),
        "total_direct_hours": total_hours,
        "total_ev": total_ev,
        "total_boq_volume": total_volume,
        "total_operation_done": total_operation,
        "single_boq_unit": single_boq_unit,
        "avg_ev_per_hour": avg_ev,
        "avg_physical_per_hour": avg_physical,
        "avg_operation_per_hour": avg_operation,
        "physical_display": physical_display,
        "physical_hint": physical_hint,
    }


def build_layer2_totals(agg: pd.DataFrame, prepared: pd.DataFrame) -> dict:
    total_hours = float(agg["direct_hours"].sum()) if not agg.empty else 0.0
    total_volume = float(agg["volume_done"].sum()) if not agg.empty else 0.0
    total_operation = float(agg["operation_done"].sum()) if not agg.empty else 0.0
    total_ev = float(agg["ev_value"].sum()) if not agg.empty else 0.0
    total_idle = float(agg["idle_hours"].sum()) if not agg.empty else 0.0
    total_dp_rows = int(agg["dp_rows"].sum()) if not agg.empty else 0

    boq_units_list = unique_nonempty(prepared["unit"]) if not prepared.empty else []
    op_units_list = (
        unique_nonempty(prepared["operation_unit"]) if not prepared.empty else []
    )

    unit_display = (
        boq_units_list[0]
        if len(boq_units_list) == 1
        else ("разные" if len(boq_units_list) > 1 else "—")
    )
    op_unit_display = (
        op_units_list[0]
        if len(op_units_list) == 1
        else ("разные" if len(op_units_list) > 1 else "—")
    )

    return {
        "boq_code": "ИТОГО",
        "boq_name": "Итого по выбранному срезу",
        "iwp": "—",
        "system": "—",
        "operation_type": "—",
        "operation_unit": op_unit_display,
        "operation_done": total_operation,
        "operation_per_direct_hour": productivity_rate_display(
            total_operation, total_hours, op_units_list
        ),
        "unit": unit_display,
        "volume_done": total_volume,
        "volume_per_direct_hour": productivity_rate_display(
            total_volume, total_hours, boq_units_list
        ),
        "ev_value": total_ev,
        "ev_per_direct_hour": money_per_hour(per_direct_hour(total_ev, total_hours))
        if total_hours > 0
        else "—",
        "direct_hours": total_hours,
        "idle_hours": total_idle,
        "dp_rows": total_dp_rows,
        "quality": "SUMMARY",
        "is_total": True,
    }


def layer2_warning_html() -> str:
    return card_shell(
        f'<div style="font-size:11px;color:{C_TEXT};line-height:1.45;">'
        f"{esc(LAYER2_WARNING)}</div>"
    )


def layer2_intro_html() -> str:
    return card_shell(
        f'<div style="font-size:11px;color:{C_TEXT};line-height:1.45;">'
        f"{esc(LAYER2_INTRO)}</div>",
        "margin-bottom:8px;",
    )


def layer2_operation_warning_html() -> str:
    return card_shell(
        f'<div style="font-size:11px;color:{C_TEXT};line-height:1.45;">'
        f'<strong style="color:{C_AMBER};">Важно.</strong> {esc(LAYER2_OPERATION_WARNING)}</div>',
        f"margin-bottom:8px;border-left:3px solid {C_AMBER};",
    )


def layer2_quality_comment(row: pd.Series) -> str:
    op_type = norm_str(row.get("operation_type"))
    op_done = safe_float(row.get("operation_done")) or 0.0
    direct_hours = safe_float(row.get("direct_hours")) or 0.0

    if direct_hours <= 0:
        return "Нет direct часов"
    if "другое" in op_type.casefold():
        return "Нестандартная операция"
    if op_type and op_done <= 0:
        return "Нет количества операции"
    return "OK"


def layer2_summary_html(stats: dict, period_label: str) -> str:
    period = (
        f'<div style="font-size:10px;color:{C_MUTED};margin-bottom:6px;">'
        f"Период: {esc(period_label)}</div>"
    )
    avg_op = (
        num_fmt(stats["avg_operation_per_hour"])
        if stats["avg_operation_per_hour"] is not None
        else "—"
    )

    def cell(label: str, value: str, hint: str) -> str:
        return (
            f'<div style="border:1px solid {C_BORDER};border-radius:6px;padding:8px 10px;'
            f'background:{C_BG};min-height:72px;">'
            f'<div style="font-size:9px;color:{C_MUTED};">{esc(label)}</div>'
            f'<div style="font-size:15px;font-weight:600;color:{C_TEXT};margin-top:3px;">'
            f"{esc(value)}</div>"
            f'<div style="font-size:8px;color:{C_MUTED};margin-top:4px;line-height:1.35;">'
            f"{esc(hint)}</div></div>"
        )

    count_metrics = "".join(
        cell(label, value, hint)
        for label, value, hint in (
            (
                "BOQ-коды в факте",
                str(stats["boq_codes"]),
                "Сколько BOQ-кодов реально заявлено в Daily Progress",
            ),
            (
                "IWP / пакеты в факте",
                str(stats["iwps"]),
                "Сколько IWP/пакетов попало в факт",
            ),
            (
                "Типы операций в факте",
                str(stats["operations"]),
                "Сколько разных типов операций указали на площадке",
            ),
            (
                "Единицы BOQ",
                str(stats["boq_units"]),
                "Сколько разных единиц измерения BOQ в факте",
            ),
            (
                "Единицы операций",
                str(stats["operation_units"]),
                "Если много разных значений — операции заполняются нестандартизировано",
            ),
        )
    )

    productivity_metrics = "".join(
        cell(label, value, hint)
        for label, value, hint in (
            (
                "Средняя денежная выработка",
                money_per_hour(stats["avg_ev_per_hour"]),
                "EV / direct часы",
            ),
            (
                "Средняя физическая выработка",
                stats["physical_display"],
                stats["physical_hint"],
            ),
            (
                "Средняя операционная выработка",
                avg_op,
                "Operation quantity / direct часы",
            ),
        )
    )

    inner = (
        f'{period}<div style="font-size:11px;font-weight:700;color:{C_TEXT};'
        f'text-transform:uppercase;letter-spacing:0.04em;margin-bottom:8px;">'
        f"Layer 2 · сводка</div>"
        f'<div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));'
        f'gap:6px;margin-bottom:6px;">{count_metrics}</div>'
        f'<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));'
        f'gap:6px;">{productivity_metrics}</div>'
    )
    return card_shell(inner, "margin-top:8px;margin-bottom:8px;")


def layer2_table_row_html(row, td: str, is_total: bool = False) -> str:
    if isinstance(row, dict):
        data = row
    else:
        data = row.to_dict()

    if is_total:
        td = (
            f"padding:6px 7px;border-top:2px solid {C_BORDER};"
            f"background:#F9FAFB;color:{C_TEXT};font-weight:700;"
        )
        op_done_display = num_fmt(data.get("operation_done"))
        op_rate = esc(data.get("operation_per_direct_hour"))
        vol_rate = esc(data.get("volume_per_direct_hour"))
        ev_rate = esc(data.get("ev_per_direct_hour"))
        quality = esc(data.get("quality", "SUMMARY"))
        quality_color = C_TEXT
    else:
        op_type = norm_str(data.get("operation_type"))
        op_done = safe_float(data.get("operation_done")) or 0.0
        op_done_display = num_fmt(op_done) if op_type or op_done > 0 else "—"
        op_rate = esc(num_fmt(data.get("operation_per_direct_hour")))
        vol_rate = esc(num_fmt(data.get("volume_per_direct_hour")))
        ev_rate = esc(money_per_hour(data.get("ev_per_direct_hour")))
        quality = layer2_quality_comment(pd.Series(data))
        quality_color = C_TEXT if quality == "OK" else C_AMBER
        quality = esc(quality)

    return (
        "<tr>"
        f"<td style='{td}'>{esc(data.get('boq_code'))}</td>"
        f"<td style='{td}'>{esc(data.get('boq_name'))}</td>"
        f"<td style='{td}'>{esc(data.get('iwp'))}</td>"
        f"<td style='{td}'>{esc(data.get('system'))}</td>"
        f"<td style='{td}'>{esc(data.get('operation_type') or '—')}</td>"
        f"<td style='{td}'>{esc(data.get('operation_unit'))}</td>"
        f"<td style='{td}'>{esc(op_done_display)}</td>"
        f"<td style='{td}'>{op_rate}</td>"
        f"<td style='{td}'>{esc(data.get('unit'))}</td>"
        f"<td style='{td}'>{esc(num_fmt(data.get('volume_done')))}</td>"
        f"<td style='{td}'>{vol_rate}</td>"
        f"<td style='{td}'>{esc(money(data.get('ev_value')))}</td>"
        f"<td style='{td}'>{ev_rate}</td>"
        f"<td style='{td}'>{esc(hours_fmt(data.get('direct_hours')))}</td>"
        f"<td style='{td}'>{esc(hours_fmt(data.get('idle_hours')))}</td>"
        f"<td style='{td}'>{int(safe_float(data.get('dp_rows')) or 0)}</td>"
        f"<td style='{td};color:{quality_color};font-weight:600;'>{quality}</td>"
        "</tr>"
    )


def layer2_table_html(agg: pd.DataFrame, prepared: pd.DataFrame) -> str:
    if agg.empty:
        return card_shell(
            f'<div style="font-size:11px;color:{C_MUTED};">'
            f"Нет строк Layer 2 для выбранного периода.</div>"
        )

    td = f"padding:5px 7px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};"
    rows = [layer2_table_row_html(row, td) for _, row in agg.iterrows()]
    rows.append(
        layer2_table_row_html(build_layer2_totals(agg, prepared), td, is_total=True)
    )

    th = (
        f"padding:6px 7px;font-size:10px;font-weight:600;color:{C_MUTED};"
        f"border-bottom:1px solid {C_BORDER};white-space:nowrap;"
    )
    head_html = "".join(
        f"<th style='{th}'>{esc(h)}</th>" for h in LAYER2_TABLE_HEADERS
    )

    return (
        f"<div style='overflow-x:auto;border:1px solid {C_BORDER};border-radius:8px;'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:10px;background:{C_BG};'>"
        f"<thead><tr style='background:#F9FAFB;text-align:left;'>{head_html}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def build_layer2_period_label(
    month_key: str, week_key: str, work_date: str
) -> str:
    parts = []
    if month_key != "Все":
        parts.append(f"Месяц: {month_key}")
    if week_key != "Все":
        parts.append(f"Неделя: {week_key}")
    if work_date != "Все":
        parts.append(f"День: {work_date}")
    return " · ".join(parts) if parts else "месяц"


def render_layer2_block(
    dp_slice: pd.DataFrame,
    month_key: str,
    week_key: str,
    work_date: str,
):
    period_label = build_layer2_period_label(month_key, week_key, work_date)
    render_html(layer2_warning_html())
    if dp_slice.empty:
        st.caption("Нет записей Daily Progress для выбранного периода и звена.")
        return

    prepared = prepare_layer2_data(dp_slice)
    agg = build_layer2_aggregate(prepared)
    stats = layer2_summary_stats(prepared, agg)
    render_html(layer2_summary_html(stats, period_label))
    render_html(layer2_intro_html())
    render_html(layer2_operation_warning_html())
    render_html(layer2_table_html(agg, prepared))


def calc_risk(direct_cost_share) -> str:
    share = safe_float(direct_cost_share)
    if share is None:
        return "NO_LABOR_DATA"
    if share > 1:
        return "CRITICAL_DIRECT_LOSS"
    if share > 0.7:
        return "HIGH_DIRECT_COST"
    if share > 0.5:
        return "MEDIUM_DIRECT_COST"
    return "OK"


def is_mobilized_no_report(
    row: pd.Series, roster: pd.DataFrame, month_key: str
) -> bool:
    if not month_key or month_key == "Все":
        return False
    plan_hours = safe_float(row.get("plan_direct_hours_month")) or 0.0
    if plan_hours <= 0:
        return False
    people_count = (
        len(roster)
        if not roster.empty
        else int(safe_float(row.get("people_count")) or 0)
    )
    if people_count <= 0:
        return False
    if count_mobilized_people(roster, month_key) <= 0:
        return False
    fact_rows = int(safe_float(row.get("fact_rows")) or 0)
    actual_hours = safe_float(row.get("actual_direct_hours")) or 0.0
    return fact_rows == 0 and actual_hours == 0


def resolve_crew_risk(
    row: pd.Series, roster: pd.DataFrame, month_key: str
) -> str:
    if is_mobilized_no_report(row, roster, month_key):
        return MOBILIZED_NO_REPORT_STATUS
    return calc_risk(row.get("direct_cost_share"))


def enrich_month_table_with_mobilization(
    table_df: pd.DataFrame, labor: pd.DataFrame, month_key: str
) -> pd.DataFrame:
    if table_df.empty or not month_key or month_key == "Все":
        return table_df
    result = table_df.copy()
    first_dates = []
    mobilized_flags = []
    mobilized_counts = []
    crew_risks = []
    mobilized_no_dp_flags = []
    for _, row in result.iterrows():
        crew = norm_str(row.get("crew"))
        roster = filter_labor_roster(labor, month_key, crew)
        mob_count = count_mobilized_people(roster, month_key)
        first_dates.append(first_mobilization_date(roster))
        mobilized_flags.append(mob_count > 0)
        mobilized_counts.append(mob_count)
        crew_risks.append(resolve_crew_risk(row, roster, month_key))
        fact_rows = int(safe_float(row.get("fact_rows")) or 0)
        actual_hours = safe_float(row.get("actual_direct_hours")) or 0.0
        mobilized_no_dp_flags.append(
            mob_count > 0 and fact_rows == 0 and actual_hours == 0
        )
    result["first_mobilization_date"] = first_dates
    result["mobilized"] = mobilized_flags
    result["mobilized_people_count"] = mobilized_counts
    result["crew_risk"] = crew_risks
    result["mobilized_no_dp"] = mobilized_no_dp_flags
    return result


def filter_options(values, include_all: bool = True) -> list[str]:
    if not values:
        return ["Все"] if include_all else []
    cleaned = sorted({norm_str(v) for v in values if norm_str(v)})
    return (["Все"] + cleaned) if include_all else cleaned


def filter_options_from_df(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    return filter_options(df[col].dropna().tolist())


def apply_burndown_filters(
    df: pd.DataFrame, month_key: str, crew: str
) -> pd.DataFrame:
    result = df.copy()
    if month_key != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str).str.strip() == month_key]
    if crew != "Все" and "crew" in result.columns:
        result = result[result["crew"].astype(str).str.strip() == crew]
    return result


def filter_dp_slice(
    dp: pd.DataFrame,
    month_key: str,
    week_key: str,
    work_date: str,
    crew: str,
) -> pd.DataFrame:
    if dp.empty:
        return dp
    result = dp.copy()
    if month_key != "Все" and "month_key" in result.columns:
        result = result[result["month_key"] == month_key]
    if week_key != "Все" and "week_key" in result.columns:
        result = result[result["week_key"] == week_key]
    if work_date != "Все" and "work_date" in result.columns:
        result = result[
            result["work_date"].apply(lambda d: norm_str(d) == work_date)
        ]
    if crew != "Все" and "crew_id" in result.columns:
        result = result[result["crew_id"] == crew]
    return result


def aggregate_dp_fact(dp_slice: pd.DataFrame, empty_ok: bool = False) -> dict | None:
    if dp_slice.empty:
        if not empty_ok:
            return None
        return {
            "actual_work_value": 0.0,
            "actual_direct_hours": 0.0,
            "actual_direct_cost": 0.0,
            "actual_qty_total": 0.0,
            "fact_rows": 0,
        }
    return {
        "actual_work_value": float(dp_slice["ev_day_value"].fillna(0).sum())
        if "ev_day_value" in dp_slice.columns
        else 0.0,
        "actual_direct_hours": float(dp_slice["direct_work_hours"].fillna(0).sum())
        if "direct_work_hours" in dp_slice.columns
        else 0.0,
        "actual_direct_cost": float(dp_slice["ac_day_value"].fillna(0).sum())
        if "ac_day_value" in dp_slice.columns
        else 0.0,
        "actual_qty_total": float(dp_slice["quantity_today"].fillna(0).sum())
        if "quantity_today" in dp_slice.columns
        else 0.0,
        "fact_rows": len(dp_slice),
    }


def merge_period_fact(row: pd.Series, period_fact: dict | None) -> pd.Series:
    if not period_fact:
        return row
    merged = row.copy()
    for key in (
        "actual_work_value",
        "actual_direct_hours",
        "actual_direct_cost",
        "actual_qty_total",
        "fact_rows",
    ):
        if key in period_fact:
            merged[key] = period_fact[key]
    merged["remaining_work_value"] = remaining_value(
        merged.get("plan_work_value_month"), merged.get("actual_work_value")
    )
    merged["remaining_direct_hours"] = remaining_value(
        merged.get("plan_direct_hours_month"), merged.get("actual_direct_hours")
    )
    merged["remaining_direct_cost"] = remaining_value(
        merged.get("plan_direct_cost_month"), merged.get("actual_direct_cost")
    )
    return merged


def period_filter_active(week_key: str, work_date: str) -> bool:
    return week_key != "Все" or work_date != "Все"


def filter_labor_roster(
    labor: pd.DataFrame, month_key: str, crew: str
) -> pd.DataFrame:
    if labor.empty or month_key == "Все" or crew == "Все":
        return pd.DataFrame()
    result = labor.copy()
    if "month_key" in result.columns:
        result = result[result["month_key"] == month_key]
    if "crew_code" in result.columns:
        result = result[result["crew_code"] == crew]
    if "direct_hours_month" in result.columns:
        result = result[result["direct_hours_month"].fillna(0) > 0]
    sort_cols = [c for c in ("full_name_ru", "role") if c in result.columns]
    if sort_cols:
        result = result.sort_values(sort_cols, na_position="last")
    return result


def parse_iso_date(value) -> date | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def date_fmt(value) -> str:
    parsed = parse_iso_date(value)
    if parsed is None:
        return "—"
    return parsed.strftime("%d.%m.%Y")


def month_key_last_day(month_key: str) -> date | None:
    if not month_key or month_key == "Все":
        return None
    parts = str(month_key).strip().split("-", 1)
    if len(parts) != 2:
        return None
    month_name, year_str = parts[0], parts[1]
    try:
        year = int(year_str)
        month = MONTH_NAME_TO_NUM.get(month_name)
        if not month:
            return None
        return date(year, month, monthrange(year, month)[1])
    except ValueError:
        return None


def is_person_mobilized_in_month(mobilization_date, month_key: str) -> bool:
    mob = parse_iso_date(mobilization_date)
    last_day = month_key_last_day(month_key)
    if mob is None or last_day is None:
        return False
    return mob <= last_day


def count_mobilized_people(roster: pd.DataFrame, month_key: str) -> int:
    if roster.empty or "actual_mobilization_date" not in roster.columns:
        return 0
    return sum(
        1
        for _, person in roster.iterrows()
        if is_person_mobilized_in_month(
            person.get("actual_mobilization_date"), month_key
        )
    )


def first_mobilization_date(roster: pd.DataFrame) -> date | None:
    if roster.empty or "actual_mobilization_date" not in roster.columns:
        return None
    dates = [
        parsed
        for parsed in (
            parse_iso_date(value) for value in roster["actual_mobilization_date"]
        )
        if parsed is not None
    ]
    return min(dates) if dates else None


def labor_summary_stats(roster: pd.DataFrame, month_key: str = "") -> dict:
    if roster.empty:
        return {
            "headcount": 0,
            "mobilized_count": 0,
            "hours": 0.0,
            "cost": 0.0,
            "avg_rate": None,
        }
    hours = float(roster["direct_hours_month"].fillna(0).sum())
    cost = float(roster["direct_cost_rub_month"].fillna(0).sum())
    avg_rate = cost / hours if hours > 0 else None
    mobilized_count = (
        count_mobilized_people(roster, month_key)
        if month_key and month_key != "Все"
        else 0
    )
    return {
        "headcount": len(roster),
        "mobilized_count": mobilized_count,
        "hours": hours,
        "cost": cost,
        "avg_rate": avg_rate,
    }


def badge_html(label: str, color: str) -> str:
    return (
        '<span style="display:inline-block;white-space:nowrap;padding:3px 9px;'
        f"border-radius:4px;background:{color};color:#fff;font-weight:600;"
        f'font-size:10px;line-height:1.2;">{esc(label)}</span>'
    )


def risk_badge_html(risk: str) -> str:
    return badge_html(RISK_LABELS.get(risk, risk), RISK_COLORS.get(risk, C_GRAY))


def forecast_badge_html(status: str) -> str:
    return badge_html(
        FORECAST_LABELS.get(status, status),
        FORECAST_COLORS.get(status, C_GRAY),
    )


def calc_forecast(row: pd.Series) -> dict:
    actual_work = safe_float(row.get("actual_work_value"))
    actual_hours = safe_float(row.get("actual_direct_hours"))
    plan_work = safe_float(row.get("plan_work_value_month")) or 0.0
    plan_hours = safe_float(row.get("plan_direct_hours_month")) or 0.0
    plan_cost = safe_float(row.get("plan_direct_cost_month")) or 0.0

    if actual_hours is None or actual_hours == 0 or actual_work is None or actual_work == 0:
        return {
            "work_value_per_hour": None,
            "forecast_work_value_at_plan_hours": None,
            "forecast_ev_capped": None,
            "forecast_margin_at_completion": None,
            "forecast_status": "NO_FACT",
            "forecast_text": FORECAST_TEXTS["NO_FACT"],
        }

    ev_per_hour = actual_work / actual_hours
    forecast_ev = ev_per_hour * plan_hours
    forecast_ev_capped = min(forecast_ev, plan_work)
    forecast_margin = forecast_ev_capped - plan_cost

    if forecast_margin <= 0:
        status = "LOSS"
    elif forecast_ev_capped >= plan_work:
        status = "ON_TRACK"
    else:
        status = "AT_RISK"

    return {
        "work_value_per_hour": ev_per_hour,
        "forecast_work_value_at_plan_hours": forecast_ev,
        "forecast_ev_capped": forecast_ev_capped,
        "forecast_margin_at_completion": forecast_margin,
        "forecast_status": status,
        "forecast_text": FORECAST_TEXTS[status],
    }


def enrich_with_forecast(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    forecasts = df.apply(calc_forecast, axis=1, result_type="expand")
    return pd.concat(
        [df.reset_index(drop=True), forecasts.reset_index(drop=True)], axis=1
    )


def calc_forecast_totals(
    actual_work: float,
    actual_hours: float,
    plan_work: float,
    plan_hours: float,
    plan_cost: float,
) -> dict:
    row = pd.Series(
        {
            "actual_work_value": actual_work,
            "actual_direct_hours": actual_hours,
            "plan_work_value_month": plan_work,
            "plan_direct_hours_month": plan_hours,
            "plan_direct_cost_month": plan_cost,
        }
    )
    return calc_forecast(row)


def build_month_crews_total_row(table_df: pd.DataFrame) -> dict:
    plan_work = float(table_df["plan_work_value_month"].fillna(0).sum())
    plan_hours = float(table_df["plan_direct_hours_month"].fillna(0).sum())
    plan_cost = float(table_df["plan_direct_cost_month"].fillna(0).sum())
    actual_hours = float(table_df["actual_direct_hours"].fillna(0).sum())
    actual_cost = float(table_df["actual_direct_cost"].fillna(0).sum())
    actual_work = float(table_df["actual_work_value"].fillna(0).sum())
    margin = float(table_df["margin_after_direct"].fillna(0).sum())
    fact_rows = int(table_df["fact_rows"].fillna(0).sum())

    share = burn_ratio(actual_cost, plan_cost) if plan_cost > 0 else None
    ev_per_hour = per_direct_hour(actual_work, actual_hours)

    forecast = calc_forecast_totals(
        actual_work, actual_hours, plan_work, plan_hours, plan_cost
    )

    return {
        "crew": "ИТОГО",
        "plan_work_value_month": plan_work,
        "plan_direct_hours_month": plan_hours,
        "plan_direct_cost_month": plan_cost,
        "actual_direct_hours": actual_hours,
        "actual_direct_cost": actual_cost,
        "fact_rows": fact_rows,
        "margin_after_direct": margin,
        "direct_cost_share": share,
        "risk": "SUMMARY",
        "work_value_per_hour": ev_per_hour,
        "forecast_ev_capped": forecast.get("forecast_ev_capped"),
        "forecast_margin_at_completion": forecast.get("forecast_margin_at_completion"),
        "forecast_status": forecast.get("forecast_status", "NO_FACT"),
    }


def card_shell(inner: str, extra_style: str = "") -> str:
    return (
        f'<div style="border:1px solid {C_BORDER};border-radius:8px;padding:11px 12px;'
        f"background:{C_BG};{extra_style}\">{inner}</div>"
    )


def progress_card_html(
    title: str,
    current_label: str,
    current_value: str,
    plan_value: str,
    remaining_value_str: str,
    pct: float | None,
    bar_color: str = C_BLUE,
    footnote: str = "",
) -> str:
    if pct is None:
        bar_width = 0
        pct_text = "—"
    else:
        bar_width = min(max(pct, 0.0), 1.0) * 100
        pct_text = pct_fmt(pct)

    footnote_html = (
        f'<div style="font-size:10px;color:{C_MUTED};margin-top:5px;line-height:1.35;">'
        f"{esc(footnote)}</div>"
        if footnote
        else ""
    )

    inner = f"""
        <div style="font-size:10px;font-weight:600;color:{C_MUTED};text-transform:uppercase;
                    letter-spacing:0.04em;margin-bottom:6px;">{esc(title)}</div>
        <div style="font-size:18px;font-weight:700;color:{C_TEXT};line-height:1.1;">
            {esc(current_value)}</div>
        <div style="font-size:10px;color:{C_MUTED};margin:2px 0 7px;">{esc(current_label)}</div>
        <div style="display:flex;justify-content:space-between;font-size:10px;
                    color:{C_MUTED};margin-bottom:5px;">
            <span>План: <strong style="color:{C_TEXT};">{esc(plan_value)}</strong></span>
            <span>Остаток: <strong style="color:{C_TEXT};">{esc(remaining_value_str)}</strong></span>
        </div>
        <div style="height:6px;background:{C_BORDER};border-radius:2px;overflow:hidden;
                    margin-bottom:3px;">
            <div style="width:{bar_width:.1f}%;height:100%;background:{bar_color};"></div>
        </div>
        <div style="font-size:10px;font-weight:600;color:{C_TEXT};">{esc(pct_text)}</div>
        {footnote_html}
    """
    return card_shell(inner)


def quantity_info_card_html(row: pd.Series, period_note: str = "") -> str:
    qty = qty_fmt(safe_float(row.get("actual_qty_total")) or 0.0)
    note = period_note or ""
    text = (
        f"Факт объёма по Daily Progress: {qty}. "
        "На Layer 1 объём не агрегируется, потому что разные единицы измерения. "
        "Детализация по BOQ / операциям — в Layer 2 ниже."
    )
    inner = f"""
        <div style="font-size:10px;font-weight:600;color:{C_MUTED};text-transform:uppercase;
                    letter-spacing:0.04em;margin-bottom:5px;">Объём · информация</div>
        <div style="font-size:11px;color:{C_TEXT};line-height:1.45;">{esc(text)}</div>
        {f'<div style="font-size:10px;color:{C_MUTED};margin-top:4px;">{esc(note)}</div>' if note else ""}
    """
    return card_shell(inner)


def metrics_grid_html(row: pd.Series, period_note: str = "") -> str:
    fact_ok = has_burn_fact(row)
    pending_note = "" if fact_ok else f"{FACT_PENDING_STATUS}. "
    burns = calc_burn_pcts(row)
    work_value_burn_pct = burns["work"] if fact_ok else 0.0
    direct_hours_burn_pct = burns["hours"] if fact_ok else 0.0
    direct_cost_burn_pct = burns["cost"] if fact_ok else 0.0

    work_value_color = get_burn_color(burn_pct_percent(work_value_burn_pct))
    hours_color = get_burn_color(burn_pct_percent(direct_hours_burn_pct))
    cost_color = get_burn_color(burn_pct_percent(direct_cost_burn_pct))

    actual_work = safe_float(row.get("actual_work_value")) or 0.0
    actual_hours = safe_float(row.get("actual_direct_hours")) or 0.0
    actual_cost = safe_float(row.get("actual_direct_cost")) or 0.0
    fact_rows = int(safe_float(row.get("fact_rows")) or 0)

    cards = [
        progress_card_html(
            "Work Value Burn",
            "actual_work_value / plan_work_value_month",
            money(actual_work),
            money(row.get("plan_work_value_month")),
            money(remaining_value(
                row.get("plan_work_value_month"), actual_work
            )),
            work_value_burn_pct,
            bar_color=work_value_color,
            footnote=f"{pending_note}Записей DP: {fact_rows}. {period_note}".strip(),
        ),
        progress_card_html(
            "Direct Hours Burn",
            "actual_direct_hours / plan_direct_hours_month",
            hours_fmt(actual_hours),
            hours_fmt(row.get("plan_direct_hours_month")),
            hours_fmt(remaining_value(
                row.get("plan_direct_hours_month"), actual_hours
            )),
            direct_hours_burn_pct,
            bar_color=hours_color,
            footnote=(pending_note or "План → факт → остаток.").strip(),
        ),
        progress_card_html(
            "Direct Cost Burn",
            "actual_direct_cost / plan_direct_cost_month",
            money(actual_cost),
            money(row.get("plan_direct_cost_month")),
            money(remaining_value(
                row.get("plan_direct_cost_month"), actual_cost
            )),
            direct_cost_burn_pct,
            bar_color=cost_color,
            footnote=(pending_note or "План → факт → остаток.").strip(),
        ),
        quantity_info_card_html(row, period_note),
    ]

    return (
        '<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));'
        f'gap:8px;margin-top:8px;">{"".join(cards)}</div>'
    )


def crew_header_html(
    row: pd.Series,
    risk: str,
    period_label: str = "",
    mobilized_no_report: bool = False,
) -> str:
    crew_name = esc(row.get("crew"))
    month = esc(row.get("month_key"))
    fact_rows = int(safe_float(row.get("fact_rows")) or 0)
    badge = risk_badge_html(risk)
    share = esc(pct_fmt(row.get("direct_cost_share")))
    margin = esc(money(row.get("margin_after_direct")))
    fact_note = (
        ""
        if has_burn_fact(row)
        else (
            f'<span style="color:{C_MUTED};font-size:10px;font-weight:600;">'
            f"{esc(FACT_PENDING_STATUS)}</span> · "
        )
    )
    period_html = (
        f'<div style="font-size:10px;color:{C_MUTED};">{esc(period_label)}</div>'
        if period_label
        else ""
    )
    mobil_note_html = (
        f'<div style="font-size:11px;color:#991B1B;font-weight:600;margin-top:2px;">'
        f"{esc(MOBILIZED_HEADER_NOTE)}</div>"
        if mobilized_no_report
        else ""
    )

    inner = f"""
        <div style="display:flex;justify-content:space-between;align-items:flex-start;
                    flex-wrap:wrap;gap:6px;">
            <div style="min-width:0;">
                <div style="font-size:10px;color:{C_MUTED};text-transform:uppercase;
                            letter-spacing:0.04em;">Crew Burn-Down · Layer 1</div>
                <div style="font-size:18px;font-weight:700;color:{C_TEXT};line-height:1.2;">
                    {crew_name}</div>
                {mobil_note_html}
                <div style="font-size:11px;color:{C_MUTED};">{month}</div>
                {period_html}
                <div style="font-size:10px;color:{C_MUTED};margin-top:2px;">
                    {fact_note}DP: <strong style="color:{C_TEXT};">{fact_rows}</strong>
                    · share {share} · маржа {margin}
                </div>
            </div>
            <div style="flex-shrink:0;">{badge}</div>
        </div>
    """
    return card_shell(inner, "margin-bottom:8px;")


def forecast_block_html(row: pd.Series, forecast: dict) -> str:
    status = forecast.get("forecast_status", "NO_FACT")
    badge = forecast_badge_html(status)
    text = esc(forecast.get("forecast_text", ""))
    ev_per_hour = esc(money_per_hour(forecast.get("work_value_per_hour")))
    forecast_ev_raw = esc(money(forecast.get("forecast_work_value_at_plan_hours")))
    forecast_ev_cap = esc(money(forecast.get("forecast_ev_capped")))
    forecast_margin = esc(money(forecast.get("forecast_margin_at_completion")))

    def metric_cell(label: str, value: str, sub: str = "") -> str:
        sub_html = (
            f'<div style="font-size:9px;color:{C_MUTED};margin-top:2px;">{esc(sub)}</div>'
            if sub
            else ""
        )
        return (
            f'<div style="border:1px solid {C_BORDER};border-radius:6px;padding:8px 10px;'
            f'background:{C_BG};">'
            f'<div style="font-size:9px;color:{C_MUTED};text-transform:uppercase;'
            f'letter-spacing:0.03em;">{esc(label)}</div>'
            f'<div style="font-size:15px;font-weight:600;color:{C_TEXT};margin-top:3px;">'
            f"{value}</div>{sub_html}</div>"
        )

    metrics = "".join(
        [
            metric_cell("EV / чел-ч", ev_per_hour),
            metric_cell("Прогноз EV", forecast_ev_raw, "по текущей выработке"),
            metric_cell("Прогноз EV", forecast_ev_cap, "с ограничением планом"),
            metric_cell("Прогноз маржи", forecast_margin, "после direct"),
        ]
    )

    inner = f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    flex-wrap:wrap;gap:6px;margin-bottom:8px;">
            <div style="font-size:11px;font-weight:700;color:{C_TEXT};text-transform:uppercase;
                        letter-spacing:0.04em;">Прогноз исполнения</div>
            <div>{badge}</div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;
                    margin-bottom:6px;">{metrics}</div>
        <div style="font-size:10px;color:{C_MUTED};line-height:1.4;">{text}</div>
    """
    return card_shell(inner, "margin-top:8px;")


def roster_summary_html(stats: dict) -> str:
    rate = money_per_hour(stats["avg_rate"]) if stats["avg_rate"] is not None else "—"
    inner = f"""
        <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;">
            <div><div style="font-size:9px;color:{C_MUTED};">Людей</div>
                <div style="font-size:15px;font-weight:600;color:{C_TEXT};">{stats['headcount']}</div></div>
            <div><div style="font-size:9px;color:{C_MUTED};">Мобилизовано людей</div>
                <div style="font-size:15px;font-weight:600;color:{C_TEXT};">
                    {stats['mobilized_count']}</div></div>
            <div><div style="font-size:9px;color:{C_MUTED};">Direct ч</div>
                <div style="font-size:15px;font-weight:600;color:{C_TEXT};">
                    {esc(hours_fmt(stats['hours']))}</div></div>
            <div><div style="font-size:9px;color:{C_MUTED};">Direct cost</div>
                <div style="font-size:15px;font-weight:600;color:{C_TEXT};">
                    {esc(money(stats['cost']))}</div></div>
            <div><div style="font-size:9px;color:{C_MUTED};">Средняя ставка</div>
                <div style="font-size:15px;font-weight:600;color:{C_TEXT};">{esc(rate)}</div></div>
        </div>
    """
    return card_shell(inner, "margin-bottom:8px;")


def roster_table_html(roster: pd.DataFrame) -> str:
    if roster.empty:
        return ""
    rows = []
    for _, person in roster.iterrows():
        rows.append(
            "<tr>"
            f"<td style='padding:5px 8px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};'>"
            f"{esc(person.get('full_name_ru'))}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};'>"
            f"{esc(person.get('role'))}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};'>"
            f"{esc(date_fmt(person.get('actual_mobilization_date')))}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};'>"
            f"{esc(hours_fmt(person.get('direct_hours_month')))}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};'>"
            f"{esc(money(person.get('direct_cost_rub_month')))}</td>"
            f"<td style='padding:5px 8px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};'>"
            f"{esc(person.get('budget_status'))}</td>"
            "</tr>"
        )
    th = (
        f"padding:6px 8px;font-size:10px;font-weight:600;color:{C_MUTED};"
        f"border-bottom:1px solid {C_BORDER};"
    )
    return (
        f"<div style='overflow-x:auto;border:1px solid {C_BORDER};border-radius:8px;"
        f"margin-top:8px;'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:11px;background:{C_BG};'>"
        f"<thead><tr style='background:#F9FAFB;text-align:left;'>"
        f"<th style='{th}'>ФИО</th><th style='{th}'>Роль</th>"
        f"<th style='{th}'>Дата мобилизации</th>"
        f"<th style='{th}'>План ч</th><th style='{th}'>План cost</th><th style='{th}'>Статус</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_roster_block(month_key: str, crew: str, labor: pd.DataFrame):
    roster = filter_labor_roster(labor, month_key, crew)
    stats = labor_summary_stats(roster, month_key)
    render_html(roster_summary_html(stats))
    render_html(roster_table_html(roster))
    if roster.empty:
        st.caption("Нет людей с direct_hours_month > 0 для выбранного месяца и звена.")


def month_crews_table_row_html(row, td: str, is_total: bool = False) -> str:
    if isinstance(row, dict):
        data = row
    else:
        data = row.to_dict()

    if is_total:
        td = (
            f"padding:6px 8px;border-top:2px solid {C_BORDER};"
            f"background:#F9FAFB;color:{C_TEXT};font-weight:700;"
        )
        risk_label = esc(data.get("risk", "SUMMARY"))
        risk_color = C_GRAY
        mobil_date = "—"
        mobilized_label = "—"
        fc_label = esc(FORECAST_LABELS.get(data.get("forecast_status", "NO_FACT"), "—"))
        fc_color = C_GRAY
    else:
        risk = data.get("crew_risk") or calc_risk(data.get("direct_cost_share"))
        risk_label = esc(RISK_LABELS.get(risk, risk))
        risk_color = RISK_COLORS.get(risk, C_GRAY)
        mobil_date = esc(date_fmt(data.get("first_mobilization_date")))
        mobilized_label = "Да" if data.get("mobilized") else "Нет"
        fc_status = data.get("forecast_status", "NO_FACT")
        if data.get("mobilized_no_dp"):
            fc_label = esc("MOBILIZED NO DP")
            fc_color = "#991B1B"
        else:
            fc_label = esc(FORECAST_LABELS.get(fc_status, fc_status))
            fc_color = FORECAST_COLORS.get(fc_status, C_GRAY)

    return (
        "<tr>"
        f"<td style='{td}'><strong style='color:{C_TEXT};'>"
        f"{esc(data.get('crew'))}</strong></td>"
        f"<td style='{td}'>{esc(money(data.get('plan_work_value_month')))}</td>"
        f"<td style='{td}'>{esc(hours_fmt(data.get('plan_direct_hours_month')))}</td>"
        f"<td style='{td}'>{esc(money(data.get('plan_direct_cost_month')))}</td>"
        f"<td style='{td}'>{esc(hours_fmt(data.get('actual_direct_hours')))}</td>"
        f"<td style='{td}'>{esc(money(data.get('actual_direct_cost')))}</td>"
        f"<td style='{td}'>{int(safe_float(data.get('fact_rows')) or 0)}</td>"
        f"<td style='{td}'>{mobil_date}</td>"
        f"<td style='{td}'>{mobilized_label}</td>"
        f"<td style='{td}'>{esc(money(data.get('margin_after_direct')))}</td>"
        f"<td style='{td}'>{esc(pct_fmt(data.get('direct_cost_share')))}</td>"
        f'<td style="{td}">'
        f'<span style="display:inline-block;background:{risk_color};color:#fff;'
        f'padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;">'
        f"{risk_label}</span></td>"
        f"<td style='{td}'>{esc(money_per_hour(data.get('work_value_per_hour')))}</td>"
        f"<td style='{td}'>{esc(money(data.get('forecast_ev_capped')))}</td>"
        f"<td style='{td}'>{esc(money(data.get('forecast_margin_at_completion')))}</td>"
        f'<td style="{td}">'
        f'<span style="display:inline-block;background:{fc_color};color:#fff;'
        f'padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;">'
        f"{fc_label}</span></td>"
        "</tr>"
    )


def render_compact_table(
    df: pd.DataFrame,
    labor: pd.DataFrame | None = None,
    month_key: str = "",
):
    if df.empty:
        st.info("Нет данных для отображения.")
        return

    table_df = enrich_with_forecast(df)
    if labor is not None and month_key and month_key != "Все":
        table_df = enrich_month_table_with_mobilization(table_df, labor, month_key)
    td = f"padding:5px 8px;border-bottom:1px solid {C_BORDER};color:{C_TEXT};"
    rows_html = [
        month_crews_table_row_html(row, td) for _, row in table_df.iterrows()
    ]
    rows_html.append(
        month_crews_table_row_html(
            build_month_crews_total_row(table_df), td, is_total=True
        )
    )

    th = f"padding:6px 8px;font-size:10px;font-weight:600;color:{C_MUTED};border-bottom:1px solid {C_BORDER};"
    render_html(
        f"<div style='overflow-x:auto;border:1px solid {C_BORDER};border-radius:8px;'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:11px;background:{C_BG};'>"
        f"<thead><tr style='background:#F9FAFB;text-align:left;'>"
        f"<th style='{th}'>Звено</th>"
        f"<th style='{th}'>План работ</th>"
        f"<th style='{th}'>План ч</th>"
        f"<th style='{th}'>План cost</th>"
        f"<th style='{th}'>Факт ч</th>"
        f"<th style='{th}'>Факт cost</th>"
        f"<th style='{th}'>DP</th>"
        f"<th style='{th}'>Первая мобилизация</th>"
        f"<th style='{th}'>Мобилизовано</th>"
        f"<th style='{th}'>Маржа</th>"
        f"<th style='{th}'>Share</th>"
        f"<th style='{th}'>Риск</th>"
        f"<th style='{th}'>EV/ч</th>"
        f"<th style='{th}'>Прогноз EV</th>"
        f"<th style='{th}'>Прогноз маржа</th>"
        f"<th style='{th}'>Прогноз</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def build_period_label(week_key: str, work_date: str) -> str:
    parts = []
    if week_key != "Все":
        parts.append(f"Неделя: {week_key}")
    if work_date != "Все":
        parts.append(f"День: {work_date}")
    return " · ".join(parts)


def render_crew_dashboard(
    row: pd.Series,
    period_note: str = "",
    period_label: str = "",
    month_key: str = "",
    labor_df: pd.DataFrame | None = None,
):
    crew = norm_str(row.get("crew"))
    roster = (
        filter_labor_roster(labor_df, month_key, crew)
        if labor_df is not None
        else pd.DataFrame()
    )
    risk = resolve_crew_risk(row, roster, month_key)
    mobilized_no_report = risk == MOBILIZED_NO_REPORT_STATUS
    forecast = calc_forecast(row)
    render_html(
        crew_header_html(row, risk, period_label, mobilized_no_report=mobilized_no_report)
    )
    if mobilized_no_report:
        st.warning(
            f"**{MOBILIZED_NO_REPORT_TEXT}** — {MOBILIZED_NO_REPORT_EXPLANATION}"
        )
    render_html(metrics_grid_html(row, period_note))
    render_html(forecast_block_html(row, forecast))


def clear_caches():
    load_burndown.clear()
    load_daily_progress.clear()
    load_labor_summary.clear()


# ---------------- UI ----------------

render_html(PAGE_CSS)

st.title("Счётчик звена")
st.caption(
    f"Crew Burn-Down · Layer 1 · {VIEW_NAME} + {DP_TABLE} + {LABOR_TABLE}."
)

df = load_burndown()
dp_df = load_daily_progress()
labor_df = load_labor_summary()

if df.empty:
    st.warning(f"Витрина {VIEW_NAME} пока пустая.")
    st.stop()

st.info(LAYER_INFO)

fc1, fc2, fc3, fc4, fc5, _spacer = st.columns([1, 1, 1, 1, 0.12, 1.2])

with fc1:
    selected_month = st.selectbox("Месяц", filter_options_from_df(df, "month_key"))

dp_month = dp_df.copy()
if selected_month != "Все":
    dp_month = dp_month[dp_month["month_key"] == selected_month]

with fc2:
    week_opts = filter_options_from_df(dp_month, "week_key")
    selected_week = st.selectbox("Неделя", week_opts)

dp_week = dp_month.copy()
if selected_week != "Все" and "week_key" in dp_week.columns:
    dp_week = dp_week[dp_week["week_key"] == selected_week]

with fc3:
    day_opts = filter_options_from_df(dp_week, "work_date")
    selected_day = st.selectbox("День", day_opts)

crew_source = df.copy()
if selected_month != "Все" and "month_key" in crew_source.columns:
    crew_source = crew_source[crew_source["month_key"].astype(str).str.strip() == selected_month]
if "crew" in crew_source.columns:
    crew_vals = crew_source["crew"].dropna().astype(str).str.strip().tolist()
else:
    crew_vals = []
if not dp_month.empty and "crew_id" in dp_month.columns:
    crew_vals += dp_month["crew_id"].dropna().tolist()

with fc4:
    selected_crew = st.selectbox("Звено", filter_options(crew_vals))

with fc5:
    if st.button("↻", help="Обновить", use_container_width=True):
        clear_caches()
        st.rerun()

filtered = apply_burndown_filters(df, selected_month, selected_crew)

period_active = period_filter_active(selected_week, selected_day)
period_label = build_period_label(selected_week, selected_day)
period_note = ""
display_row = None

if selected_crew != "Все" and not filtered.empty:
    display_row = filtered.iloc[0].copy()
    if period_active:
        dp_slice = filter_dp_slice(
            dp_df, selected_month, selected_week, selected_day, selected_crew
        )
        period_fact = aggregate_dp_fact(dp_slice, empty_ok=True)
        display_row = merge_period_fact(display_row, period_fact)
        period_note = f"Факт за период: {period_label}. План — месячный."

st.markdown("##### Burn-down звена")

if selected_crew == "Все":
    st.caption("Выберите звено для детализации.")
elif display_row is None:
    st.warning("Нет данных для выбранного звена.")
else:
    render_crew_dashboard(
        display_row, period_note, period_label, selected_month, labor_df
    )

if selected_month != "Все" and selected_crew != "Все":
    st.markdown("##### Состав звена")
    render_roster_block(selected_month, selected_crew, labor_df)

st.markdown("##### Layer 2 · Производительность")

if selected_month == "Все" or selected_crew == "Все":
    st.caption("Выберите месяц и звено для детализации Layer 2.")
elif selected_month != "Все" and selected_crew != "Все":
    dp_l2 = filter_dp_slice(
        dp_df, selected_month, selected_week, selected_day, selected_crew
    )
    render_layer2_block(dp_l2, selected_month, selected_week, selected_day)

st.markdown("##### Все звенья месяца")

if selected_month == "Все":
    st.caption("Выберите месяц для свода.")
    month_table_df = pd.DataFrame()
else:
    month_table_df = df[df["month_key"].astype(str).str.strip() == selected_month].copy()
    if "crew" in month_table_df.columns:
        month_table_df = month_table_df.sort_values("crew", na_position="last")

if month_table_df.empty:
    st.info("Нет строк для выбранного месяца.")
else:
    render_compact_table(month_table_df, labor_df, selected_month)
