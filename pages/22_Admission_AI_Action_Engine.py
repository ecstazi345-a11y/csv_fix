# ============================================================
# Page 22 — Ресурсная готовность месячного плана (R1)
# Resource + Economic Feasibility (read-only)
# Secondary: ИИ-рекомендации (plan_corrective_actions_view)
# ============================================================

from __future__ import annotations

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

from services.monthly_plan_labor_service import (
    format_hours,
    format_money,
    get_last_load_error,
    load_labor_lines,
    to_num,
)
from services.supabase_client import supabase
from services.monthly_plan_resource_economic_service import (
    CAPACITY_DATA_MISSING,
    ECONOMIC_STATUS_RU,
    RESOURCE_DEFICIT,
    RESOURCE_STATUS_RU,
    build_decision_economics_from_models,
    build_resource_economic_models,
    build_resource_economic_summary,
    project_required_direct_hours,
    summarize_proposed_itr_pool,
)
from services.monthly_resource_plan_service import (
    get_last_error as get_resource_plan_error,
    load_approved_capacity,
)
from utils.month_key import format_month_key_ru, normalize_month_key

# --- AI Action Engine (preserved) ---
TABLE_VIEW = "plan_corrective_actions_view"
TABLE_ACTIONS = "plan_corrective_actions"

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

SEVERITY_RU = {
    "CRITICAL": "Критично",
    "HIGH": "Высокий риск",
    "MEDIUM": "Средний риск",
    "LOW": "Низкий риск",
}

ACTION_STATUS_RU = {
    "PENDING": "Ожидает решения",
    "APPROVED": "Одобрено",
    "REJECTED": "Отклонено",
    "APPLIED": "Применено",
    "ROLLED_BACK": "Откат",
}

ACTION_TYPE_RU = {
    "SCOPE_ADD": "Добавить денежный фронт",
    "SCOPE_REMOVE": "Убрать лишний объём",
    "SCOPE_SWAP": "Заменить фронт",
    "ECONOMIC_BLOCK": "Проверить / заблокировать убыточный фронт",
    "PRODUCTIVITY_SCENARIO_CHANGE": "Изменить сценарий производительности",
    "PLAN_REBALANCE": "Перебалансировать месяц",
    "COMPLETE_TO_CLOSE": "Доделать до закрытия",
    "LOSS_ACCEPTED_TO_UNLOCK_CASH": "Принять убыток ради открытия денег",
    "CREW_REDUCE": "Сократить звено",
    "CREW_REALLOCATE": "Перераспределить людей",
}

SEVERITY_ALERT = {
    "CRITICAL": ("🔴", "КРИТИЧНО"),
    "HIGH": ("🟠", "РИСК"),
    "MEDIUM": ("🟡", "ВНИМАНИЕ"),
    "LOW": ("🟢", "НОРМА"),
}

ALERT_CSS_CLASS = {
    "CRITICAL": "war-alert-critical",
    "HIGH": "war-alert-high",
    "MEDIUM": "war-alert-medium",
    "LOW": "war-alert-low",
}

CONTROL_BOQ_CODE = "1500-04-01-01"

st.set_page_config(layout="wide")

st.markdown(
    """
    <style>
    .re22-caption { font-size: 0.88rem; color: #52525b; margin-bottom: 0.75rem; }
    .re22-note {
        background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;
        padding: 0.55rem 0.75rem; font-size: 0.84rem; color: #475569; margin: 0.5rem 0 0.85rem 0;
    }
    .re22-status-deficit { color: #b91c1c; font-weight: 600; }
    .re22-status-ok { color: #166534; font-weight: 500; }
    .re22-status-warn { color: #a16207; font-weight: 600; }
    .re22-status-muted { color: #64748b; }
    .war-card { background: #fafafa; border: 1px solid #e4e4e7; border-radius: 8px;
        padding: 0.5rem 0.65rem 0.55rem 0.65rem; margin-bottom: 0.55rem; }
    .war-alert { font-size: 0.92rem; font-weight: 600; line-height: 1.35;
        padding: 0.42rem 0.6rem; margin-bottom: 0.45rem; border-radius: 4px; color: #18181b; }
    .war-alert-critical { background: #fef2f2; border-left: 4px solid #b91c1c; }
    .war-alert-high { background: #fff7ed; border-left: 4px solid #c2410c; }
    .war-alert-medium { background: #fefce8; border-left: 4px solid #a16207; }
    .war-alert-low { background: #f0fdf4; border-left: 4px solid #15803d; }
    .war-meta { font-size: 0.76rem; color: #71717A; line-height: 1.35; margin: 0.1rem 0 0.25rem 0; }
    .war-label { font-size: 0.8rem; font-weight: 600; color: #52525b; margin: 0.3rem 0 0.12rem 0; }
    .war-text { font-size: 0.86rem; color: #27272a; line-height: 1.42; margin: 0 0 0.3rem 0; }
    .war-do-box {
        background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706;
        padding: 0.5rem 0.7rem; margin: 0.15rem 0 0.4rem 0;
        font-size: 0.92rem; font-weight: 600; color: #1c1917; line-height: 1.42;
    }
    .war-complete-box {
        background: #fff1f2; border: 1px solid #fecdd3; border-left: 4px solid #e11d48;
        padding: 0.5rem 0.65rem; margin: 0.35rem 0 0.35rem 0;
        font-size: 0.84rem; color: #881337; line-height: 1.42;
    }
    .war-decision-label { font-size: 0.8rem; font-weight: 600; color: #3f3f46;
        margin: 0.35rem 0 0.2rem 0; }
    .re22-banner-missing {
        background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706;
        border-radius: 6px; padding: 0.65rem 0.85rem; font-size: 0.88rem;
        color: #78350f; margin: 0.65rem 0 0.85rem 0; line-height: 1.45;
    }
    .re22-banner-deficit {
        background: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid #b91c1c;
        border-radius: 6px; padding: 0.65rem 0.85rem; font-size: 0.88rem;
        color: #7f1d1d; margin: 0.65rem 0 0.85rem 0; line-height: 1.45;
    }
    .re22-mgmt-msg {
        background: #fff7ed; border: 1px solid #fed7aa; border-left: 4px solid #c2410c;
        border-radius: 6px; padding: 0.7rem 0.85rem; margin: 0.55rem 0 0.85rem 0;
        font-size: 0.9rem; color: #9a3412; line-height: 1.45;
    }
    .re22-warn-box {
        background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px;
        padding: 0.55rem 0.75rem; font-size: 0.84rem; color: #92400e;
        margin: 0.35rem 0 0.75rem 0; line-height: 1.4;
    }
    div[data-testid="stMetricLabel"] { font-size: 0.76rem !important; }
    div[data-testid="stMetricValue"] { font-size: 1.02rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def esc(value: Any) -> str:
    if value is None:
        return ""
    return html_lib.escape(str(value))


def safe_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def money_rub(value: Any) -> str:
    num = to_num(value, default=-1.0)
    if num < 0:
        return "—"
    return format_money(num)


def money_rub_signed(value: Any) -> str:
    """Allow negative managerial results (not accounting P&L labels)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    return format_money(num)


def qty_display(value: Any, decimals: int = 2) -> str:
    num = to_num(value, default=-1.0)
    if num < 0:
        return "—"
    text = f"{num:,.{decimals}f}".replace(",", " ")
    if decimals > 0:
        text = text.replace(".", ",")
    return text


def pct_display(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return f"{float(value):,.1f}".replace(",", " ").replace(".", ",") + " %"


def filter_options(values: list[str]) -> list[str]:
    cleaned = sorted({v for v in values if v and v.strip()})
    return ["Все"] + cleaned


def raw_filter_values(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return []
    vals = df[col].dropna().astype(str).str.strip()
    return sorted(vals[vals != ""].unique().tolist())


@st.cache_data(ttl=300)
def cached_load_resource_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Plan demand + APPROVED resource-plan capacity (R1.2 SoT)."""
    lines = load_labor_lines()
    capacity = load_approved_capacity()
    return lines, capacity


@st.cache_data(ttl=300)
def cached_load_labor_summary_for_itr() -> pd.DataFrame:
    """Read-only MLS columns for proposed ITR pool (R1.5B)."""
    cols = (
        "project_code,month_key,full_name_ru,crew_code,"
        "direct_hours_month,indirect_hours_month,"
        "direct_cost_rub_month,indirect_cost_rub_month,budget_status,support_function"
    )
    try:
        response = supabase.table("monthly_labor_summary").select(cols).limit(20000).execute()
        return pd.DataFrame(response.data or [])
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def apply_line_filters(
    line_df: pd.DataFrame,
    *,
    project: str,
    month: str,
    facility: str,
    discipline: str,
    crew: str,
    resource_status: str,
    economic_status: str,
    boq_search: str,
) -> pd.DataFrame:
    if line_df.empty:
        return line_df
    out = line_df.copy()
    if project != "Все":
        out = out[out["project_code"].astype(str) == project]
    if month != "Все":
        out = out[out["month_key"].astype(str) == month]
    if facility != "Все" and "facility" in out.columns:
        out = out[out["facility"].astype(str) == facility]
    if discipline != "Все" and "discipline" in out.columns:
        out = out[out["discipline"].astype(str) == discipline]
    if crew != "Все":
        out = out[out["crew_code"].astype(str) == crew]
    if resource_status != "Все":
        out = out[out["resource_status"].astype(str) == resource_status]
    if economic_status != "Все":
        out = out[out["economic_status"].astype(str) == economic_status]
    if boq_search.strip():
        needle = boq_search.strip().lower()
        mask = out["boq_code"].astype(str).str.lower().str.contains(needle, na=False)
        if "boq_name" in out.columns:
            mask = mask | out["boq_name"].astype(str).str.lower().str.contains(needle, na=False)
        out = out[mask]
    return out


def filter_crew_by_lines(crew_df: pd.DataFrame, line_df: pd.DataFrame) -> pd.DataFrame:
    if crew_df.empty or line_df.empty:
        return crew_df.head(0).copy()
    keys = set(
        zip(
            line_df["project_code"].astype(str),
            line_df["month_key"].astype(str),
            line_df["crew_code"].astype(str),
        )
    )
    mask = crew_df.apply(
        lambda r: (str(r["project_code"]), str(r["month_key"]), str(r["crew_code"])) in keys,
        axis=1,
    )
    return crew_df[mask].copy()


def build_crew_display_table(crew_df: pd.DataFrame) -> pd.DataFrame:
    if crew_df.empty:
        return pd.DataFrame(
            columns=[
                "Звено",
                "Плановых BOQ",
                "Запрошено трудозатрат, чел·ч",
                "Доступно, чел·ч",
                "Дефицит / резерв, чел·ч",
                "Покрытие, %",
                "Требуется FTE",
                "Доступно FTE",
                "Статус ресурса",
                "Стоимость планируемых работ",
                "Плановая стоимость прямого труда",
                "Маржинальный результат до ИТР",
                "Статус экономики",
            ]
        )
    rows = []
    for _, row in crew_df.iterrows():
        is_missing = str(row.get("resource_status")) == CAPACITY_DATA_MISSING
        rows.append(
            {
                "Звено": row.get("crew_code") or "—",
                "Плановых BOQ": int(to_num(row.get("boq_count"))),
                "Запрошено трудозатрат, чел·ч": format_hours(row.get("crew_required_hours")),
                "Доступно, чел·ч": "—" if is_missing else format_hours(row.get("crew_available_hours")),
                "Дефицит / резерв, чел·ч": "—" if is_missing else format_hours(row.get("hours_gap")),
                "Покрытие, %": "—" if is_missing else pct_display(row.get("coverage_pct")),
                "Требуется FTE": qty_display(row.get("fte_required"), 1),
                "Доступно FTE": "—" if is_missing else qty_display(row.get("available_fte"), 1),
                "Статус ресурса": RESOURCE_STATUS_RU.get(
                    str(row.get("resource_status")), str(row.get("resource_status"))
                ),
                "Стоимость планируемых работ": money_rub(row.get("plan_value_total")),
                "Плановая стоимость прямого труда": money_rub(row.get("labor_cost_total")),
                "Маржинальный результат до ИТР": money_rub(row.get("economic_gap")),
                "Статус экономики": ECONOMIC_STATUS_RU.get(
                    str(row.get("economic_status")), str(row.get("economic_status"))
                ),
            }
        )
    return pd.DataFrame(rows)


def build_line_display_table(line_df: pd.DataFrame) -> pd.DataFrame:
    if line_df.empty:
        return pd.DataFrame(
            columns=[
                "BOQ-код",
                "Наименование",
                "Титул / объект",
                "Дисциплина",
                "Звено",
                "Запрошенный объём",
                "Ед.",
                "Требуется, чел·ч",
                "Покрытие звена, %",
                "Расчётно выполнимый объём",
                "Дефицит объёма",
                "Цена за ед.",
                "Запрошенная стоимость",
                "Расчётно выполнимая стоимость",
                "Плановая стоимость прямого труда (запрошено)",
                "Маржинальный результат до ИТР (запрошено)",
                "Ресурсный статус",
                "Экономический статус",
                "Итоговый статус",
            ]
        )
    rows = []
    for _, row in line_df.iterrows():
        is_missing = str(row.get("resource_status")) == CAPACITY_DATA_MISSING
        rows.append(
            {
                "BOQ-код": row.get("boq_code") or "—",
                "Наименование": row.get("boq_name") or "—",
                "Титул / объект": row.get("facility") or "—",
                "Дисциплина": row.get("discipline") or "—",
                "Звено": row.get("crew_code") or "—",
                "Запрошенный объём": qty_display(row.get("requested_qty")),
                "Ед.": row.get("unit") or "—",
                "Требуется, чел·ч": format_hours(row.get("required_hours")),
                "Покрытие звена, %": "—" if is_missing else pct_display(row.get("coverage_pct")),
                "Расчётно выполнимый объём": "—"
                if is_missing
                else qty_display(row.get("theoretical_feasible_qty")),
                "Дефицит объёма": "—" if is_missing else qty_display(row.get("volume_deficit_qty")),
                "Цена за ед.": money_rub(row.get("unit_price")),
                "Запрошенная стоимость": money_rub(row.get("requested_work_value")),
                "Расчётно выполнимая стоимость": "—"
                if is_missing
                else money_rub(row.get("feasible_work_value")),
                "Плановая стоимость прямого труда (запрошено)": money_rub(row.get("requested_labor_cost")),
                "Маржинальный результат до ИТР (запрошено)": money_rub(row.get("economic_gap")),
                "Ресурсный статус": RESOURCE_STATUS_RU.get(
                    str(row.get("resource_status")), str(row.get("resource_status"))
                ),
                "Экономический статус": ECONOMIC_STATUS_RU.get(
                    str(row.get("economic_status")), str(row.get("economic_status"))
                ),
                "Итоговый статус": row.get("combined_status") or "—",
            }
        )
    return pd.DataFrame(rows)


def render_resource_economic_gate() -> None:
    st.title("Ресурсная готовность месячного плана")
    st.markdown(
        '<p class="re22-caption">Проверка объёма, трудовых ресурсов и экономики '
        "перед принятием месячного обязательства</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="re22-note">'
        "Анализ включает весь план месяца по выбранным фильтрам; "
        "фильтр только допущенных кодов будет подключён на следующем этапе. "
        "<strong>Доступная мощность</strong> берётся только из утверждённого "
        "Monthly Resource Plan (статус APPROVED). "
        "Исходный Crew_Register / monthly_labor_summary — справочник кандидатов, "
        "не commitment capacity. "
        "Сформировать и утвердить план ресурсов: страница "
        "«План ресурсов месяца»."
        "</div>",
        unsafe_allow_html=True,
    )

    lines_raw, capacity_raw = cached_load_resource_data()
    load_err = get_last_load_error()
    plan_err = get_resource_plan_error()
    if load_err:
        st.error(f"Не удалось загрузить строки плана: {load_err}")
    if plan_err:
        st.warning(
            "Утверждённый ресурсный план недоступен или таблица ещё не развёрнута. "
            f"Детали: {plan_err}. "
            "Пока нет APPROVED строк — статус CAPACITY_DATA_MISSING."
        )

    if lines_raw.empty:
        st.info("Нет строк месячного плана для анализа. Сначала сформируйте план в Конструкторе.")
        return

    models = build_resource_economic_models(lines_raw, capacity_raw)
    line_all = models["line_model"]
    crew_all = models["crew_model"]

    st.markdown("---")
    f1, f2, f3, f4 = st.columns(4)
    f5, f6, f7, f8 = st.columns(4)

    with f1:
        project_sel = st.selectbox(
            "Проект",
            filter_options(raw_filter_values(line_all, "project_code")),
            key="re22_filter_project",
        )
    with f2:
        month_sel = st.selectbox(
            "Месяц",
            filter_options(raw_filter_values(line_all, "month_key")),
            key="re22_filter_month",
        )
    with f3:
        facility_sel = st.selectbox(
            "Титул / объект",
            filter_options(raw_filter_values(line_all, "facility")),
            key="re22_filter_facility",
        )
    with f4:
        discipline_sel = st.selectbox(
            "Дисциплина",
            filter_options(raw_filter_values(line_all, "discipline")),
            key="re22_filter_discipline",
        )
    with f5:
        crew_sel = st.selectbox(
            "Звено",
            filter_options(raw_filter_values(line_all, "crew_code")),
            key="re22_filter_crew",
        )
    with f6:
        resource_sel = st.selectbox(
            "Статус ресурса",
            filter_options(list(RESOURCE_STATUS_RU.keys())),
            format_func=lambda x: "Все" if x == "Все" else RESOURCE_STATUS_RU.get(x, x),
            key="re22_filter_resource",
        )
    with f7:
        economic_sel = st.selectbox(
            "Статус экономики",
            filter_options(list(ECONOMIC_STATUS_RU.keys())),
            format_func=lambda x: "Все" if x == "Все" else ECONOMIC_STATUS_RU.get(x, x),
            key="re22_filter_economic",
        )
    with f8:
        boq_search = st.text_input("Поиск BOQ", key="re22_filter_boq", placeholder="Код или наименование")

    line_filtered = apply_line_filters(
        line_all,
        project=project_sel,
        month=month_sel,
        facility=facility_sel,
        discipline=discipline_sel,
        crew=crew_sel,
        resource_status=resource_sel,
        economic_status=economic_sel,
        boq_search=boq_search,
    )
    crew_filtered = filter_crew_by_lines(crew_all, line_filtered)

    summary = build_resource_economic_summary(crew_filtered, line_filtered)

    missing_crew_count = int(summary.get("crews_missing_capacity_count") or 0)
    deficit_crew_count = 0
    if not crew_filtered.empty:
        deficit_crew_count = int(
            crew_filtered.drop_duplicates(subset=["project_code", "month_key", "crew_code"])
            .loc[lambda df: df["resource_status"] == RESOURCE_DEFICIT]
            .shape[0]
        )

    if missing_crew_count > 0:
        st.markdown(
            f'<div class="re22-banner-missing">'
            f"<strong>Не для всех звеньев сформирован подтверждённый ресурсный план на выбранный месяц.</strong><br>"
            f"Расчёт выполнимого объёма для таких звеньев не выполняется.<br>"
            f"Без ресурсного плана: {missing_crew_count} "
            f"{'звено' if missing_crew_count == 1 else 'звена' if 2 <= missing_crew_count <= 4 else 'звеньев'}."
            f"</div>",
            unsafe_allow_html=True,
        )

    if deficit_crew_count > 0:
        st.markdown(
            f'<div class="re22-banner-deficit">'
            f"<strong>Подтверждённая мощность недостаточна.</strong> "
            f"Звеньев с ресурсным дефицитом: {deficit_crew_count}."
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    k1, k2, k3, k4, k5, k6, k7, k8 = st.columns(8)
    k1.metric("Запрошенная стоимость работ", money_rub(summary["requested_work_value"]))
    k2.metric("Требуемые трудозатраты", format_hours(summary["required_labor_hours"]))
    k3.metric("Доступные трудозатраты", format_hours(summary["available_labor_hours"]))
    k4.metric("Ресурсное покрытие", pct_display(summary["resource_coverage_pct"]))
    k5.metric("Расчётно выполнимая стоимость", money_rub(summary["feasible_work_value"]))
    k6.metric(
        "Плановая стоимость прямого труда (запрошено)",
        money_rub(summary["labor_cost_total"]),
        help="Стоимость прямого труда всего requested scope. Не сравнивать с выполнимой стоимостью.",
    )
    k7.metric(
        "Маржинальный результат до ИТР (запрошено)",
        money_rub(summary["economic_result"]),
        help="Requested Work Value − Requested Direct Labor. Не бухгалтерская прибыль.",
    )
    k8.metric("Звенья без ресурсного плана", str(missing_crew_count))

    # ------------------------------------------------------------------
    # R1.5B Decision Economics (read-model only)
    # ------------------------------------------------------------------
    decision_ready = (
        project_sel != "Все"
        and month_sel != "Все"
        and crew_sel != "Все"
        and not crew_filtered.empty
    )
    if decision_ready:
        mls_raw = cached_load_labor_summary_for_itr()
        month_canon = normalize_month_key(month_sel) or str(month_sel)
        itr_pool_info = summarize_proposed_itr_pool(
            mls_raw,
            project_code=project_sel,
            month_key=month_canon,
        )
        proj_req_hours = project_required_direct_hours(
            lines_raw,
            project_code=project_sel,
            month_key=month_canon,
        )
        crew_scope = crew_filtered[
            (crew_filtered["project_code"].astype(str) == str(project_sel))
            & (
                crew_filtered["month_key"].map(
                    lambda v: normalize_month_key(v) or str(v)
                )
                == month_canon
            )
            & (crew_filtered["crew_code"].astype(str) == str(crew_sel))
        ]
        if not crew_scope.empty:
            decision = build_decision_economics_from_models(
                crew_row=crew_scope.iloc[0],
                line_model=line_filtered,
                project_required_hours=proj_req_hours,
                project_itr_pool=float(itr_pool_info["itr_pool"]),
                itr_pool_status=str(itr_pool_info["pool_status"]),
            )

            st.markdown("---")
            st.markdown("### Управленческая экономика (decision-support)")
            st.caption(
                f"Scope: `{project_sel}` · "
                f"`{format_month_key_ru(month_canon) or month_canon}` · `{crew_sel}`. "
                "Это не бухгалтерский P&L и не окончательная прибыль/убыток."
            )
            st.markdown(
                f'<div class="re22-warn-box"><strong>Ставка прямого труда.</strong> '
                f"{html_lib.escape(decision['rate_warning_ru'])}</div>",
                unsafe_allow_html=True,
            )

            st.markdown("#### Экономика запрошенного объёма")
            st.caption("Вопрос: выгоден ли весь желаемый scope до ИТР?")
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Стоимость запрошенных работ", money_rub(decision["requested_work_value"]))
            r2.metric("Требуемые трудозатраты", format_hours(decision["requested_direct_hours"]))
            r3.metric(
                "Плановая стоимость прямого труда",
                money_rub(decision["requested_direct_labor"]),
            )
            r4.metric(
                "Маржинальный результат до ИТР",
                money_rub(decision["requested_margin_before_itr"]),
            )

            st.markdown("#### Экономика расчётно выполнимого объёма")
            st.caption(
                "Вопрос: выгодна ли та часть scope, которую реально способны выполнить? "
                "Не сравнивать выполнимую стоимость с прямым трудом всего requested scope."
            )
            f1b, f2b, f3b, f4b = st.columns(4)
            f1b.metric("Подтверждённая мощность", format_hours(decision["approved_hours"]))
            f2b.metric(
                "Расчётно выполнимая стоимость работ",
                money_rub(decision["feasible_work_value"]),
            )
            f3b.metric(
                "Стоимость прямого труда выполнимого объёма",
                money_rub(decision["feasible_direct_labor"]),
            )
            f4b.metric(
                "Маржинальный результат выполнимого объёма до ИТР",
                money_rub(decision["feasible_margin_before_itr"]),
            )

            st.markdown("#### Административный контур / ИТР")
            st.caption(
                f"Статус пула: {decision['itr_pool_status_ru']}. "
                f"{decision['itr_quality_warning_ru']} "
                f"База распределения: {decision['itr_driver_label_ru']}."
            )
            i1, i2, i3, i4 = st.columns(4)
            i1.metric(
                "Предварительный ИТР проекта за месяц",
                money_rub(decision["project_itr_pool"]),
            )
            i2.metric(
                "Доля звена",
                pct_display(
                    decision["itr_share_pct"]
                    if decision["itr_share_pct"] is not None
                    else None
                ),
            )
            i3.metric(
                "Полная распределённая доля ИТР",
                money_rub(decision["full_allocated_itr"]),
            )
            i4.metric("Поглощённый ИТР", money_rub(decision["absorbed_itr"]))
            i5, i6, i7 = st.columns(3)
            i5.metric("Непоглощённый ИТР", money_rub(decision["unabsorbed_itr"]))
            i6.metric(
                "Нормализованный результат после поглощённого ИТР",
                money_rub_signed(decision["normalized_result_after_absorbed_itr"]),
                help=(
                    "Feasible Value − Feasible Direct Labor − Absorbed ITR. "
                    "Экономика выполнимого объёма с пропорциональным поглощением overhead."
                ),
            )
            i7.metric(
                "Результат месяца после полной доли ИТР",
                money_rub_signed(decision["full_month_operating_result"]),
                help=(
                    "Показывает результат при отнесении на звено полной месячной доли "
                    "административного контура. Не является бухгалтерской прибылью/убытком."
                ),
            )
            st.caption(
                "Непоглощённый ИТР — часть административного контура, не покрытая текущей "
                "расчётно выполнимой производственной мощностью. Не трактуется автоматически "
                "как вина звена."
            )

            if decision.get("management_message_triggered"):
                st.markdown(
                    f'<div class="re22-mgmt-msg">'
                    f"<strong>{html_lib.escape(decision['management_message'])}</strong><br>"
                    f"{html_lib.escape(decision['management_message_detail'])}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
    elif project_sel != "Все" and month_sel != "Все" and crew_sel == "Все":
        st.caption(
            "Для блока управленческой экономики ИТР выберите конкретное звено "
            "(не «Все»)."
        )

    st.markdown("### Мощность звеньев")
    crew_display = build_crew_display_table(crew_filtered)
    st.dataframe(crew_display, use_container_width=True, hide_index=True)

    st.markdown("### Реализуемость объёмов")
    line_display = build_line_display_table(line_filtered)
    st.dataframe(line_display, use_container_width=True, hide_index=True)

    control_rows = line_all[
        line_all["boq_code"].astype(str).str.strip() == CONTROL_BOQ_CODE
    ]
    with st.expander(f"Контрольный BOQ {CONTROL_BOQ_CODE}", expanded=False):
        if control_rows.empty:
            st.caption("Код не найден в текущей выборке данных.")
        else:
            for _, crow in control_rows.iterrows():
                crew_key = (
                    str(crow.get("project_code")),
                    str(crow.get("month_key")),
                    str(crow.get("crew_code")),
                )
                crew_match = crew_all[
                    (crew_all["project_code"].astype(str) == crew_key[0])
                    & (crew_all["month_key"].astype(str) == crew_key[1])
                    & (crew_all["crew_code"].astype(str) == crew_key[2])
                ]
                roster_row_count = (
                    int(to_num(crew_match.iloc[0]["roster_row_count"]))
                    if not crew_match.empty
                    else 0
                )
                st.json(
                    {
                        "project": crow.get("project_code"),
                        "month": crow.get("month_key"),
                        "plan_line_id": crow.get("plan_line_id"),
                        "requested_qty": crow.get("requested_qty"),
                        "labor_hours": crow.get("required_hours"),
                        "norm_hours_per_unit": crow.get("norm_hours_per_unit"),
                        "crew": crow.get("crew_code"),
                        "crew_size": crow.get("crew_size"),
                        "crew_required_hours_total": crow.get("crew_required_hours_total"),
                        "roster_row_count": roster_row_count,
                        "crew_available_hours": crow.get("crew_available_hours"),
                        "coverage": crow.get("coverage"),
                        "theoretical_feasible_qty": crow.get("theoretical_feasible_qty"),
                        "unit_price": crow.get("unit_price"),
                        "requested_work_value": crow.get("requested_work_value"),
                        "feasible_work_value": crow.get("feasible_work_value"),
                        "labor_cost": crow.get("requested_labor_cost"),
                        "economic_gap": crow.get("economic_gap"),
                        "resource_status": crow.get("resource_status"),
                        "economic_status": crow.get("economic_status"),
                    }
                )


# ============================================================
# AI Action Engine — preserved secondary section
# ============================================================


def has_write_credentials() -> bool:
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    url = os.getenv("SUPABASE_URL")
    return bool(secret_key and url)


@st.cache_resource
def get_supabase_write_client() -> Client | None:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


@st.cache_data(ttl=300)
def load_actions(limit: int = 5000) -> pd.DataFrame:
    response = supabase.table(TABLE_VIEW).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


def map_label(value: str, mapping: dict[str, str]) -> str:
    return mapping.get(str(value).strip(), str(value))


def filter_selectbox(
    label: str,
    df: pd.DataFrame,
    col: str,
    mapping: dict[str, str] | None,
    key: str,
) -> str:
    raw_vals = raw_filter_values(df, col)
    options: list[tuple[str, str]] = [("Все", "Все")]
    for raw in raw_vals:
        display = map_label(raw, mapping) if mapping else raw
        options.append((display, raw))
    labels = [item[0] for item in options]
    label_to_value = {item[0]: item[1] for item in options}
    selected = st.selectbox(label, labels, key=key)
    return label_to_value[selected]


def plain_filter_selectbox(label: str, df: pd.DataFrame, col: str, key: str) -> str:
    opts = ["Все"] + raw_filter_values(df, col)
    return st.selectbox(label, opts, key=key)


def apply_ai_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    crew: str,
    severity: str,
    action_type: str,
    action_status: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if project != "Все" and "project_code" in out.columns:
        out = out[out["project_code"].astype(str) == project]
    if month != "Все" and "month_key" in out.columns:
        out = out[out["month_key"].astype(str) == month]
    if crew != "Все" and "crew_code" in out.columns:
        out = out[out["crew_code"].astype(str) == crew]
    if severity != "Все" and "severity" in out.columns:
        out = out[out["severity"].astype(str) == severity]
    if action_type != "Все" and "action_type" in out.columns:
        out = out[out["action_type"].astype(str) == action_type]
    if action_status != "Все" and "action_status" in out.columns:
        out = out[out["action_status"].astype(str) == action_status]
    return out


def sort_actions(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_severity_ord"] = out["severity"].map(SEVERITY_ORDER).fillna(99)
    sort_cols = ["_severity_ord"]
    if "action_priority_sort" in out.columns:
        sort_cols.append("action_priority_sort")
    if "month_key" in out.columns:
        sort_cols.append("month_key")
    if "crew_code" in out.columns:
        sort_cols.append("crew_code")
    out = out.sort_values(
        [c for c in sort_cols if c in out.columns],
        ascending=[True] * len(sort_cols),
    )
    return out.drop(columns=["_severity_ord"], errors="ignore")


def action_type_label(row: pd.Series) -> str:
    raw = safe_text(row.get("action_type"))
    if raw:
        return ACTION_TYPE_RU.get(raw, safe_text(row.get("action_type_ru")) or raw)
    return safe_text(row.get("action_type_ru")) or "—"


def short_action_label(row: pd.Series) -> str:
    text = action_type_label(row)
    if len(text) > 42:
        return text[:39] + "…"
    return text


def money_compact(value: Any) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        num = float(value)
        formatted = f"{abs(num):,.0f}".replace(",", " ")
        sign = "−" if num < 0 else ""
        return f"{sign}{formatted} ₽"
    except (TypeError, ValueError):
        return "—"


def hours_reserve_fmt(value: Any) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        num = float(value)
        formatted = f"{abs(num):,.0f}".replace(",", " ")
        if num > 0:
            return f"+{formatted} ч"
        if num < 0:
            return f"−{formatted} ч"
        return "0 ч"
    except (TypeError, ValueError):
        return "—"


def alert_bar_line(row: pd.Series) -> str:
    level = str(row.get("severity") or "").upper()
    emoji, label = SEVERITY_ALERT.get(level, ("⚪", "СТАТУС"))
    crew = row.get("crew_code") or "—"
    action = short_action_label(row)
    effect = money_compact(row.get("current_margin"))
    return f"{emoji} {label} | {crew} | {action} | {effect}"


def render_alert_bar(row: pd.Series) -> None:
    level = str(row.get("severity") or "").upper()
    css_class = ALERT_CSS_CLASS.get(level, "war-alert-medium")
    line = esc(alert_bar_line(row))
    st.markdown(
        f'<div class="war-alert {css_class}">{line}</div>',
        unsafe_allow_html=True,
    )


def is_truthy(value: Any) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "да"}


def needs_completion_block(row: pd.Series) -> bool:
    action_type = str(row.get("action_type") or "").upper()
    return is_truthy(row.get("is_completion_required")) or action_type == "COMPLETE_TO_CLOSE"


def bool_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return "Да" if is_truthy(value) else "Нет"


def update_status(action_id: str, payload: dict):
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY не задан в .env — запись в plan_corrective_actions недоступна."
        )
    return (
        write_client.table(TABLE_ACTIONS)
        .update(payload)
        .eq("action_id", action_id)
        .execute()
    )


def approve_action(action_id: str):
    return update_status(
        action_id,
        {
            "action_status": "APPROVED",
            "approved_by": "streamlit_user",
            "approved_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def reject_action(action_id: str):
    return update_status(
        action_id,
        {
            "action_status": "REJECTED",
            "rejected_reason": "Отклонено через интерфейс",
        },
    )


def render_decision_controls(row: pd.Series) -> None:
    action_id = safe_text(row.get("action_id"))
    status_raw = safe_text(row.get("action_status")) or ""

    if status_raw == "APPROVED":
        st.success("Решение уже принято: Одобрено")
        return
    if status_raw == "REJECTED":
        st.warning("Решение уже принято: Отклонено")
        return

    if not action_id:
        st.caption("Нет идентификатора решения — обновление недоступно.")
        return

    write_enabled = has_write_credentials()
    if not write_enabled:
        st.warning(
            "SUPABASE_SECRET_KEY не найден в C:\\csv_fix\\.env — кнопки отключены. "
            "Перезапустите Streamlit после правки .env."
        )

    _, foot_btn1, foot_btn2 = st.columns([4, 1, 1])
    with foot_btn1:
        if st.button("Одобрить", key=f"approve_{action_id}", disabled=not write_enabled):
            try:
                approve_action(action_id)
                load_actions.clear()
                st.success("Решение одобрено")
                st.rerun()
            except Exception as e:
                st.error("Не удалось обновить статус решения")
                st.exception(e)
    with foot_btn2:
        if st.button("Отклонить", key=f"reject_{action_id}", disabled=not write_enabled):
            try:
                reject_action(action_id)
                load_actions.clear()
                st.warning("Решение отклонено")
                st.rerun()
            except Exception as e:
                st.error("Не удалось обновить статус решения")
                st.exception(e)


def problem_codes(row: pd.Series) -> str | None:
    parts = []
    for col in ("affected_boq_code", "recommended_boq_code"):
        text = safe_text(row.get(col))
        if text:
            parts.append(text)
    if not parts:
        return None
    return ", ".join(dict.fromkeys(parts))


def render_ai_card(row: pd.Series) -> None:
    st.markdown('<div class="war-card">', unsafe_allow_html=True)
    render_alert_bar(row)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Финансовый результат плана", money_compact(row.get("current_margin")))
    m2.metric("Объём покрытия к добавлению", money_compact(row.get("recommended_ev_add")))
    m3.metric("Результат после решения", money_compact(row.get("expected_margin")))
    m4.metric("Резерв / дефицит часов", hours_reserve_fmt(row.get("capacity_delta_hours")))

    st.markdown('<p class="war-label">Что произошло?</p>', unsafe_allow_html=True)
    summary = safe_text(row.get("executive_summary"))
    if summary:
        st.markdown(f'<p class="war-text">{esc(summary)}</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="war-meta">Нет данных</p>', unsafe_allow_html=True)

    st.markdown('<p class="war-label">Что делать?</p>', unsafe_allow_html=True)
    action = safe_text(row.get("management_action"))
    if action:
        st.markdown(f'<div class="war-do-box">{esc(action)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="war-meta">Нет данных</p>', unsafe_allow_html=True)

    if needs_completion_block(row):
        complete_html = (
            "<div class='war-complete-box'>"
            "<strong>⚠ Проверить завершение системы</strong><br>"
            "Убыточный фронт нельзя автоматически убрать — возможно, его нужно доделать "
            "для сдачи, КС или открытия денег.<br>"
            f"Причина: {esc(safe_text(row.get('completion_reason')) or '—')} · "
            f"Приёмка: {bool_label(row.get('unlocks_acceptance'))} · "
            f"Деньги: {bool_label(row.get('unlocks_cash'))} · "
            f"Эффект: {money_compact(row.get('net_cash_effect'))}"
            "</div>"
        )
        st.markdown(complete_html, unsafe_allow_html=True)

    detail = safe_text(row.get("detailed_explanation"))
    if detail:
        with st.expander("Подробное объяснение", expanded=False):
            st.text(detail)

    st.markdown('<p class="war-decision-label">Управленческое решение</p>', unsafe_allow_html=True)
    meta_parts = []
    if safe_text(row.get("month_key")):
        meta_parts.append(f"Месяц: {esc(row['month_key'])}")
    if safe_text(row.get("project_code")):
        meta_parts.append(f"Проект: {esc(row['project_code'])}")
    status_raw = safe_text(row.get("action_status"))
    if status_raw:
        meta_parts.append(esc(map_label(status_raw, ACTION_STATUS_RU)))
    decision = safe_text(row.get("action_decision_label"))
    if decision:
        meta_parts.append(esc(decision))
    codes = problem_codes(row)
    if codes:
        meta_parts.append(f"Коды: {esc(codes)}")
    if meta_parts:
        st.markdown(
            f'<p class="war-meta">{" · ".join(meta_parts)}</p>',
            unsafe_allow_html=True,
        )

    render_decision_controls(row)
    st.markdown("</div>", unsafe_allow_html=True)


def kpi_negative_margin_sum(df: pd.DataFrame) -> float:
    if df.empty or "current_margin" not in df.columns:
        return 0.0
    margins = pd.to_numeric(df["current_margin"], errors="coerce")
    negative = margins[margins < 0]
    return float(negative.sum()) if not negative.empty else 0.0


def kpi_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


def render_ai_action_engine_section() -> None:
    st.markdown("---")
    with st.expander("ИИ-рекомендации и корректирующие действия", expanded=False):
        st.caption(
            "Вторичный блок — очередь управленческих решений из plan_corrective_actions_view."
        )
        try:
            data = load_actions()
        except Exception as e:
            st.error(f"Не удалось загрузить очередь решений: {e}")
            return

        if data.empty:
            st.info("Нет данных в очереди управленческих решений.")
            return

        f1, f2, f3 = st.columns(3)
        f4, f5, f6 = st.columns(3)
        with f1:
            project_sel = plain_filter_selectbox("Проект", data, "project_code", "ai_filter_project")
        with f2:
            month_sel = plain_filter_selectbox("Месяц", data, "month_key", "ai_filter_month")
        with f3:
            crew_sel = plain_filter_selectbox("Звено", data, "crew_code", "ai_filter_crew")
        with f4:
            severity_sel = filter_selectbox(
                "Уровень риска", data, "severity", SEVERITY_RU, "ai_filter_severity"
            )
        with f5:
            action_type_sel = filter_selectbox(
                "Тип действия", data, "action_type", ACTION_TYPE_RU, "ai_filter_action_type"
            )
        with f6:
            action_status_sel = filter_selectbox(
                "Статус решения", data, "action_status", ACTION_STATUS_RU, "ai_filter_action_status"
            )

        filtered = apply_ai_filters(
            data,
            project_sel,
            month_sel,
            crew_sel,
            severity_sel,
            action_type_sel,
            action_status_sel,
        )
        filtered = sort_actions(filtered)

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Всего решений", len(filtered))
        critical_cnt = 0
        pending_cnt = 0
        if not filtered.empty:
            if "severity" in filtered.columns:
                critical_cnt = int((filtered["severity"].astype(str) == "CRITICAL").sum())
            if "action_status" in filtered.columns:
                pending_cnt = int((filtered["action_status"].astype(str) == "PENDING").sum())
        k2.metric("Критические", critical_cnt)
        k3.metric("Ожидают решения", pending_cnt)
        k4.metric("Суммарный убыток", money_rub(kpi_negative_margin_sum(filtered)))
        k5.metric("Объём покрытия к добавлению", money_rub(kpi_sum(filtered, "recommended_ev_add")))
        k6.metric("Улучшение результата", money_rub(kpi_sum(filtered, "margin_delta")))

        if filtered.empty:
            st.info("Нет решений по выбранным фильтрам.")
            return

        for _, row in filtered.iterrows():
            render_ai_card(row)

        with st.expander("Показать исходные данные ИИ", expanded=False):
            st.dataframe(filtered, use_container_width=True, hide_index=True)


# --- Main ---
render_resource_economic_gate()
render_ai_action_engine_section()
