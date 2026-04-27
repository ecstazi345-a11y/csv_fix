import streamlit as st
import pandas as pd
from supabase import create_client, Client
def format_money(x):
    if x is None:
        return "0"
    return f"{x:,.2f}".replace(",", " ")
# =========================
# 1. НАСТРОЙКИ ПОДКЛЮЧЕНИЯ
# =========================
SUPABASE_URL = "https://fdaxiedifkikasudcygx.supabase.co"
SUPABASE_KEY = "sb_publishable_SmdSE-IpP6ggL0kYvzBR1g_9EZtG0KL"

# =========================
# 2. ПОДКЛЮЧЕНИЕ
# =========================
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="BOQ Dashboard",
    layout="wide"
)

st.title("BOQ Dashboard")
st.caption("Сводная витрина по BOQ из Supabase")

# =========================
# 3. ФУНКЦИИ ЗАГРУЗКИ
# =========================
@st.cache_data(ttl=60)
def load_total_boq():
    response = supabase.table("boq_master_api").select("total_value_num").eq("is_deleted", False).execute()
    rows = response.data or []
    total = 0.0
    for row in rows:
        value = row.get("total_value_num")
        if value is not None:
            total += float(value)
    return total


@st.cache_data(ttl=60)
def load_sum_by_building():
    response = supabase.table("boq_sum_by_building").select("*").execute()
    data = response.data or []
    return pd.DataFrame(data)


@st.cache_data(ttl=60)
def load_sum_by_discipline():
    response = supabase.table("boq_sum_by_discipline").select("*").execute()
    data = response.data or []
    return pd.DataFrame(data)


@st.cache_data(ttl=60)
def load_sum_building_discipline():
    response = supabase.table("boq_sum_building_discipline").select("*").execute()
    data = response.data or []
    return pd.DataFrame(data)


def format_money(value):
    if value is None:
        return ""
    return f"{value:,.2f}"


# =========================
# 4. ЗАГРУЗКА ДАННЫХ
# =========================
total_boq = load_total_boq()
df_building = load_sum_by_building()
df_discipline = load_sum_by_discipline()
df_building_discipline = load_sum_building_discipline()
selected_building = st.selectbox(
    "Выбери здание",
    ["Все"] + df_building["facility_building"].tolist()
)
if selected_building != "Все":
    df_building_discipline = df_building_discipline[
        df_building_discipline["facility_building"] == selected_building
    ]
# =========================
# 5. ВЕРХНИЕ KPI
# =========================
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Общая сумма BOQ", format_money(total_boq))

with col2:
     st.metric("Кол-во зданий", format_money(len(df_building)) if not df_building.empty else 0)

with col3:
     st.metric("Кол-во дисциплин", format_money(len(df_discipline)) if not df_discipline.empty else 0)

st.divider()

# =========================
# 6. ТАБЛИЦЫ
# =========================
left, right = st.columns(2)

with left:
    st.subheader("Сумма по зданиям")
    if not df_building.empty:
        df_building_display = df_building.copy()
        if "total_value" in df_building_display.columns:
            df_building_display["total_value"] = df_building_display["total_value"].astype(float).map(format_money)
        st.dataframe(df_building_display, use_container_width=True)
    else:
        st.info("Нет данных по зданиям.")

with right:
    st.subheader("Сумма по дисциплинам")
    if not df_discipline.empty:
        df_discipline_display = df_discipline.copy()
        if "total_value" in df_discipline_display.columns:
            df_discipline_display["total_value"] = df_discipline_display["total_value"].astype(float).map(format_money)
        st.dataframe(df_discipline_display, use_container_width=True)
        st.subheader("График по дисциплинам")

        chart_df = df_discipline.copy()
        chart_df["total_value"] = chart_df["total_value"].astype(float)

        st.bar_chart(
            chart_df.set_index("construction_discipline")["total_value"]
        )
    else:
        st.info("Нет данных по дисциплинам.")
        

st.divider()

st.subheader("Здание × Дисциплина")
if not df_building_discipline.empty:
    df_matrix = df_building_discipline.copy()
    if "total_value" in df_matrix.columns:
        df_matrix["total_value"] = df_matrix["total_value"].astype(float).map(format_money)
    st.dataframe(df_matrix, use_container_width=True)
else:
    st.info("Нет данных по матрице здание × дисциплина.")