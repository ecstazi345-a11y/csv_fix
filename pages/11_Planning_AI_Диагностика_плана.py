# ============================================================
# E.3.2 — AI Диагностика плана
# Источник: public.plan_diagnostics (Supabase view)
# Только отображение — логика диагностики в SQL / Supabase
# ============================================================

import pandas as pd
import streamlit as st
from services.supabase_client import supabase

TABLE_NAME = "plan_diagnostics"

STATUS_ORDER = {"RED": 0, "ORANGE": 1, "YELLOW": 2, "GREEN": 3}
STATUS_EMOJI = {
    "RED": "🔴",
    "ORANGE": "🟠",
    "YELLOW": "🟡",
    "GREEN": "🟢",
}

st.set_page_config(layout="wide")

st.title("AI Диагностика плана")
st.caption(
    "E.3.2 Plan Diagnostics Engine — объяснение «почему план плохой» и «что изменить». "
    "Данные из plan_diagnostics, без пересчёта в UI."
)


@st.cache_data(ttl=300)
def load_plan_diagnostics(limit: int = 5000) -> pd.DataFrame:
    response = supabase.table(TABLE_NAME).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


def money(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"{float(value):,.0f} ₽".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def hours_fmt(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"{float(value):,.0f} чел-ч".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def ratio_fmt(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def filter_options(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def apply_filters(
    df: pd.DataFrame,
    month: str,
    project: str,
    crew: str,
    status: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if month != "Все" and "month_key" in out.columns:
        out = out[out["month_key"].astype(str) == month]
    if project != "Все" and "project_code" in out.columns:
        out = out[out["project_code"].astype(str) == project]
    if crew != "Все" and "crew_code" in out.columns:
        out = out[out["crew_code"].astype(str) == crew]
    if status != "Все" and "diagnostic_status" in out.columns:
        out = out[out["diagnostic_status"].astype(str) == status]
    return out


def sort_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_status_ord"] = out["diagnostic_status"].map(STATUS_ORDER).fillna(99)
    sort_cols = ["_status_ord"]
    if "crew_code" in out.columns:
        sort_cols.append("crew_code")
    if "month_key" in out.columns:
        sort_cols.insert(1, "month_key")
    out = out.sort_values(sort_cols, ascending=[True] * len(sort_cols))
    return out.drop(columns=["_status_ord"], errors="ignore")


def status_banner(status: str, title: str) -> None:
    status = (status or "").upper()
    if status == "RED":
        st.error(title)
    elif status == "ORANGE":
        st.warning(title)
    elif status == "YELLOW":
        st.info(title)
    else:
        st.success(title)


def card_title(row: pd.Series) -> str:
    status = str(row.get("diagnostic_status") or "").upper()
    emoji = STATUS_EMOJI.get(status, "⚪")
    crew = row.get("crew_code") or "—"
    code = row.get("primary_problem_code") or "—"
    return f"{emoji} {crew} — {code}"


def render_card(row: pd.Series) -> None:
    with st.container(border=True):
        status_banner(str(row.get("diagnostic_status")), card_title(row))

        meta_parts = []
        if row.get("month_key"):
            meta_parts.append(f"**Месяц:** {row['month_key']}")
        if row.get("project_code"):
            meta_parts.append(f"**Проект:** {row['project_code']}")
        if row.get("root_cause"):
            meta_parts.append(f"**Причина:** `{row['root_cause']}`")
        if meta_parts:
            st.caption(" · ".join(meta_parts))

        left, right = st.columns(2)

        with left:
            st.markdown("**Экономика**")
            st.metric("Плановый EV", money(row.get("planned_ev_total")))
            st.metric("Стоимость звена", money(row.get("crew_cost_total")))
            st.metric("Маржа", money(row.get("gross_margin")))
            st.metric("EV / Cost", ratio_fmt(row.get("ev_to_cost_ratio")))

        with right:
            st.markdown("**Мощность**")
            st.metric("Доступно чел-ч", hours_fmt(row.get("crew_available_hours")))
            st.metric("Требуется чел-ч (базовый)", hours_fmt(row.get("required_hours_management")))
            st.metric("Требуется чел-ч (P80)", hours_fmt(row.get("required_hours_risk_p80")))
            gap = row.get("hours_gap_management")
            gap_help = "Положительное — резерв часов; отрицательное — нехватка мощности"
            try:
                gap_val = float(gap) if gap is not None and not pd.isna(gap) else None
            except (TypeError, ValueError):
                gap_val = None
            if gap_val is not None:
                st.metric("Разрыв мощности", hours_fmt(gap_val), help=gap_help)
            else:
                st.metric("Разрыв мощности", "—", help=gap_help)

        st.markdown("#### Краткий вывод")
        summary = row.get("executive_summary")
        if summary and str(summary).strip():
            st.markdown(str(summary))
        else:
            st.caption("Нет данных")

        st.markdown("#### Рекомендованное действие")
        action = row.get("management_action")
        if action and str(action).strip():
            st.markdown(str(action))
        else:
            st.caption("Нет данных")

        detail = row.get("detailed_explanation")
        if detail and str(detail).strip():
            with st.expander("Подробное объяснение", expanded=False):
                st.text(str(detail))


try:
    data = load_plan_diagnostics()
except Exception as e:
    st.error(f"Не удалось загрузить {TABLE_NAME}: {e}")
    st.stop()

if data.empty:
    st.warning("Нет данных в plan_diagnostics.")
    st.stop()

# --- фильтры ---
f1, f2, f3, f4 = st.columns(4)

with f1:
    month_sel = st.selectbox("Месяц", filter_options(data, "month_key"))
with f2:
    project_sel = st.selectbox("Проект", filter_options(data, "project_code"))
with f3:
    crew_sel = st.selectbox("Звено", filter_options(data, "crew_code"))
with f4:
    status_sel = st.selectbox("Статус", filter_options(data, "diagnostic_status"))

filtered = apply_filters(data, month_sel, project_sel, crew_sel, status_sel)
filtered = sort_diagnostics(filtered)

# --- сводка ---
st.markdown("---")
s1, s2, s3, s4, s5 = st.columns(5)
s1.metric("Всего карточек", len(filtered))
for col, label, box in [
    (s2, "🔴 RED", "RED"),
    (s3, "🟠 ORANGE", "ORANGE"),
    (s4, "🟡 YELLOW", "YELLOW"),
    (s5, "🟢 GREEN", "GREEN"),
]:
    cnt = 0
    if not filtered.empty and "diagnostic_status" in filtered.columns:
        cnt = int((filtered["diagnostic_status"].astype(str) == box).sum())
    col.metric(label, cnt)

st.markdown("---")

if filtered.empty:
    st.info("Нет диагностик по выбранным фильтрам.")
    st.stop()

for _, row in filtered.iterrows():
    render_card(row)
    st.markdown("")
