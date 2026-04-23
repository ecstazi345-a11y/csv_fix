import streamlit as st
import pandas as pd
import requests

SUPABASE_URL = "https://fdaxiedifkikasudcygx.supabase.co"
SUPABASE_KEY = "sb_publishable_SmdSE-IpP6ggL0kYvzBR1g_9EZtG0KL"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

st.set_page_config(page_title="Daily Progress Dashboard", layout="wide")

st.title("Daily Progress Dashboard")
st.caption("Сводная витрина Daily Progress из Supabase")


def format_money(x):
    if x is None:
        return "0"
    return f"{x:,.2f}".replace(",", " ")


def format_hours(x):
    return f"{x:,.2f}".replace(",", " ")


def fetch_table(table_name: str) -> pd.DataFrame:
    url = f"{SUPABASE_URL}/rest/v1/{table_name}?select=*"
    resp = requests.get(url, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return pd.DataFrame(data or [])


@st.cache_data(ttl=60)
def load_main():
    return fetch_table("daily_progress_sum_main")


@st.cache_data(ttl=60)
def load_boq():
    return fetch_table("daily_progress_sum_boq")


@st.cache_data(ttl=60)
def load_foreman():
    return fetch_table("daily_progress_sum_foreman_crew")


df_main = load_main()
df_boq = load_boq()
df_foreman = load_foreman()

if df_main.empty:
    st.warning("Нет данных в daily_progress_sum_main")
    st.stop()

months = ["Все"] + sorted(df_main["month_key"].dropna().unique().tolist())
facilities = ["Все"] + sorted(df_main["facility_building"].dropna().unique().tolist())
disciplines = ["Все"] + sorted(
    df_main["construction_discipline"].dropna().unique().tolist()
)

f1, f2, f3 = st.columns(3)

with f1:
    selected_month = st.selectbox("Месяц", months)

with f2:
    selected_facility = st.selectbox("Титул / Здание", facilities)

with f3:
    selected_discipline = st.selectbox("Дисциплина", disciplines)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if selected_month != "Все":
        out = out[out["month_key"] == selected_month]

    if selected_facility != "Все":
        out = out[out["facility_building"] == selected_facility]

    if selected_discipline != "Все":
        out = out[out["construction_discipline"] == selected_discipline]

    return out


df_main_f = apply_filters(df_main)
df_boq_f = apply_filters(df_boq)
df_foreman_f = apply_filters(df_foreman)

total_ev = (
    df_main_f["ev_day_value_sum"].fillna(0).astype(float).sum()
    if not df_main_f.empty
    else 0
)
total_ac = (
    df_main_f["ac_day_value_sum"].fillna(0).astype(float).sum()
    if not df_main_f.empty
    else 0
)
total_cv = (
    df_main_f["cv_evm_sum"].fillna(0).astype(float).sum() if not df_main_f.empty else 0
)
total_idle_loss = (
    df_main_f["idle_loss_value_sum"].fillna(0).astype(float).sum()
    if not df_main_f.empty
    else 0
)

total_direct_hours = (
    df_main_f["direct_work_hours_sum"].fillna(0).astype(float).sum()
    if not df_main_f.empty
    else 0
)
total_idle_hours = (
    df_main_f["idle_hours_sum"].fillna(0).astype(float).sum()
    if not df_main_f.empty
    else 0
)
total_productive_hours = (
    df_main_f["productive_work_hours_sum"].fillna(0).astype(float).sum()
    if not df_main_f.empty
    else 0
)
total_crew_size = (
    df_main_f["crew_size_sum"].fillna(0).astype(float).sum()
    if not df_main_f.empty
    else 0
)

ev_per_direct_hour = total_ev / total_direct_hours if total_direct_hours else 0
ev_per_productive_hour = (
    total_ev / total_productive_hours if total_productive_hours else 0
)
ev_per_worker = total_ev / total_crew_size if total_crew_size else 0
idle_percent = (
    (total_idle_hours / total_direct_hours * 100) if total_direct_hours else 0
)
productive_percent = (
    (total_productive_hours / total_direct_hours * 100) if total_direct_hours else 0
)
st.divider()
st.subheader("Hours Summary")

hours_df = pd.DataFrame(
    {
        "Metric": ["Direct Hours", "Idle Hours", "Productive Hours", "Crew Size Sum"],
        "Value": [
            total_direct_hours,
            total_idle_hours,
            total_productive_hours,
            total_crew_size,
        ],
    }
)

hours_df["Value"] = hours_df["Value"].map(format_hours)
st.dataframe(hours_df, use_container_width=True, hide_index=True)

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.metric("EV", format_money(total_ev))

with k2:
    st.metric("AC", format_money(total_ac))

with k3:
    st.metric("CV_EVM", format_money(total_cv))

with k4:
    st.metric("Idle Loss", format_money(total_idle_loss))

st.divider()

st.subheader("Месяц × Титул × Дисциплина")
if not df_main_f.empty:
    df_main_display = df_main_f.copy()

    money_cols = [
        "ev_day_value_sum",
        "ac_day_value_sum",
        "cv_evm_sum",
        "cv_cashout_sum",
        "idle_loss_value_sum",
    ]

    for col in money_cols:
        if col in df_main_display.columns:
            df_main_display[col] = df_main_display[col].astype(float).map(format_money)

    st.dataframe(df_main_display, use_container_width=True)
else:
    st.info("Нет данных по выбранным фильтрам.")

st.divider()

st.subheader("Срез по BOQ")
if not df_boq_f.empty:
    df_boq_display = df_boq_f.copy()

    money_cols = [
        "ev_day_value_sum",
        "ac_day_value_sum",
        "cv_evm_sum",
        "cv_cashout_sum",
        "idle_loss_value_sum",
    ]

    for col in money_cols:
        if col in df_boq_display.columns:
            df_boq_display[col] = df_boq_display[col].astype(float).map(format_money)

    st.dataframe(df_boq_display, use_container_width=True)
else:
    st.info("Нет BOQ данных по выбранным фильтрам.")

st.divider()

st.subheader("Срез по мастеру / звену")
if not df_foreman_f.empty:
    df_foreman_display = df_foreman_f.copy()

    money_cols = [
        "ev_day_value_sum",
        "ac_day_value_sum",
        "cv_evm_sum",
        "cv_cashout_sum",
        "idle_loss_value_sum",
    ]

    for col in money_cols:
        if col in df_foreman_display.columns:
            df_foreman_display[col] = (
                df_foreman_display[col].astype(float).map(format_money)
            )

    st.dataframe(df_foreman_display, use_container_width=True)
else:
    st.info("Нет данных по мастеру / звену.")
