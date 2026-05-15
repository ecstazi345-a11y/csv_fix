import streamlit as st
import pandas as pd
from services.supabase_client import supabase

st.set_page_config(layout="wide")

st.title("Качество данных")
st.caption(
    "Эта страница показывает ошибки классификации и ключей, "
    "которые могут искажать план-факт, EV, производительность и управленческие выводы."
)


@st.cache_data(ttl=300)
def load_table(table_name: str, limit: int = 5000) -> pd.DataFrame:
    response = supabase.table(table_name).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


def to_num(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def money(value) -> str:
    try:
        return f"{float(value):,.0f} ₽".replace(",", " ")
    except Exception:
        return "0 ₽"


def first_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def filter_options(df: pd.DataFrame, candidates: list[str]) -> list[str]:
    col = first_col(df, candidates)
    if not col:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def apply_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    issue_type: str,
    facility: str,
    discipline: str,
    facility_col: str | None,
    discipline_col: str | None,
) -> pd.DataFrame:
    if df.empty:
        return df

    result = df.copy()

    if project != "Все" and "project_code" in result.columns:
        result = result[result["project_code"].astype(str) == project]

    if month != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month]

    if issue_type != "Все" and "issue_type" in result.columns:
        result = result[result["issue_type"].astype(str) == issue_type]

    if facility != "Все" and facility_col:
        result = result[result[facility_col].astype(str) == facility]

    if discipline != "Все" and discipline_col:
        result = result[result[discipline_col].astype(str) == discipline]

    return result


def count_by_issue_pattern(df: pd.DataFrame, pattern: str) -> int:
    if df.empty or "issue_type" not in df.columns:
        return 0
    mask = df["issue_type"].astype(str).str.upper().str.contains(pattern.upper(), na=False)
    return int(mask.sum())


def ev_column(df: pd.DataFrame) -> str | None:
    for col in ("raw_ev", "ev_value_at_risk", "ev_at_risk"):
        if col in df.columns:
            return col
    return None


try:
    issues = load_table("smr_data_quality_issues")
except Exception as e:
    st.error(f"Не удалось загрузить smr_data_quality_issues: {e}")
    st.stop()

if issues.empty:
    st.success("Ошибок качества данных не найдено или view пустой.")
    st.stop()

issues = to_num(issues, ["raw_ev", "ev_value_at_risk", "ev_at_risk"])
ev_col = ev_column(issues)

facility_col = first_col(
    issues, ["facility_building", "raw_facility_building", "smr_facility_building"]
)
discipline_col = first_col(
    issues,
    ["construction_discipline", "raw_construction_discipline", "smr_construction_discipline"],
)

# ---------------- filters ----------------

st.subheader("Фильтры")

f1, f2, f3 = st.columns(3)
f4, f5 = st.columns(2)

project_sel = f1.selectbox("project_code", filter_options(issues, ["project_code"]))
month_sel = f2.selectbox("month_key", filter_options(issues, ["month_key"]))
issue_sel = f3.selectbox("issue_type", filter_options(issues, ["issue_type"]))
facility_sel = f4.selectbox(
    "facility_building",
    filter_options(issues, ["facility_building", "raw_facility_building", "smr_facility_building"]),
)
discipline_sel = f5.selectbox(
    "construction_discipline",
    filter_options(
        issues,
        ["construction_discipline", "raw_construction_discipline", "smr_construction_discipline"],
    ),
)

filtered = apply_filters(
    issues,
    project_sel,
    month_sel,
    issue_sel,
    facility_sel,
    discipline_sel,
    facility_col,
    discipline_col,
)

# ---------------- KPI ----------------

st.subheader("Сводка")

total_errors = len(filtered)
ev_at_risk = filtered[ev_col].sum() if ev_col else 0

facility_errors = count_by_issue_pattern(filtered, "FACILITY")
discipline_errors = count_by_issue_pattern(filtered, "DISCIPLINE")
iwp_errors = count_by_issue_pattern(filtered, "IWP")
if not filtered.empty and "issue_type" in filtered.columns:
    _it = filtered["issue_type"].astype(str).str.upper()
    missing_errors = int(
        (_it.str.contains("MISSING", na=False) | _it.str.contains("KEY", na=False)).sum()
    )
else:
    missing_errors = 0

k1, k2, k3 = st.columns(3)
k4, k5, k6 = st.columns(3)

k1.metric("Всего ошибок", f"{total_errors:,}".replace(",", " "))
k2.metric("EV под риском", money(ev_at_risk))
k3.metric("Ошибки Facility", facility_errors)
k4.metric("Ошибки Discipline", discipline_errors)
k5.metric("Ошибки IWP", iwp_errors)
k6.metric("Missing keys / classification", missing_errors)

# ---------------- table ----------------

st.subheader("Проблемные строки")

if filtered.empty:
    st.info("По выбранным фильтрам записей нет.")
else:
    preferred_cols = [
        "project_code",
        "month_key",
        "issue_type",
        "work_boq_code",
        "work_iwp_id",
        "work_system_label",
        "facility_building",
        "construction_discipline",
        "raw_facility_building",
        "smr_facility_building",
        "raw_construction_discipline",
        "smr_construction_discipline",
        "raw_ev",
        "ev_value_at_risk",
    ]
    display_cols = [c for c in preferred_cols if c in filtered.columns]
    if not display_cols:
        display_cols = list(filtered.columns)

    table_view = filtered[display_cols].copy()

    if ev_col and ev_col in table_view.columns:
        sort_col = ev_col
        table_view = table_view.sort_values(sort_col, ascending=False)

    st.dataframe(table_view, use_container_width=True, height=420)

    st.caption(
        "Источник: `smr_data_quality_issues`. "
        "raw_* — как записано в факте; smr_* — классификация по месячному плану. "
        "Регламент синка: `SYNC_REGULATION.md`."
    )
