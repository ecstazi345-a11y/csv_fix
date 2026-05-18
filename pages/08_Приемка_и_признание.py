import streamlit as st
import pandas as pd
from services.supabase_client import supabase

st.set_page_config(layout="wide")

st.title("Приемка и признание")
st.caption("Факт СМР → проверка ПТО → признанный объем → деньги")


def money(value):
    try:
        return f"{float(value):,.0f} ₽".replace(",", " ")
    except Exception:
        return "0 ₽"


def num(value):
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def load_table(table_name, limit=10000):
    response = supabase.table(table_name).select("*").limit(limit).execute()
    return pd.DataFrame(response.data)


# ---------- DATA ----------

df = load_table("pto_fact_vs_accepted")

if df.empty:
    st.warning("Нет данных для приемки и признания.")
    st.stop()


# ---------- FILTERS ----------

st.sidebar.markdown("## Фильтры")

projects = ["Все"] + sorted(df["project_code"].dropna().unique().tolist())
selected_project = st.sidebar.selectbox("Проект", projects)

if selected_project != "Все":
    df = df[df["project_code"] == selected_project]

months = ["Все"] + sorted(df["month_key"].dropna().unique().tolist())
selected_month = st.sidebar.selectbox("Месяц", months)

if selected_month != "Все":
    df = df[df["month_key"] == selected_month]

buildings = ["Все"] + sorted(df["facility_building"].dropna().unique().tolist())
selected_building = st.sidebar.selectbox("Здание / титул", buildings)

if selected_building != "Все":
    df = df[df["facility_building"] == selected_building]

disciplines = ["Все"] + sorted(df["construction_discipline"].dropna().unique().tolist())
selected_discipline = st.sidebar.selectbox("Дисциплина", disciplines)

if selected_discipline != "Все":
    df = df[df["construction_discipline"] == selected_discipline]

systems = ["Все"] + sorted(df["system_label"].dropna().unique().tolist())
selected_system = st.sidebar.selectbox("Система", systems)

if selected_system != "Все":
    df = df[df["system_label"] == selected_system]

if st.sidebar.button("🔄 Обновить экран"):
    st.rerun()


# ---------- INTRO ----------

st.markdown(
    """
### Смысл раздела

Раздел показывает разрыв между **выполненным объемом** и **объемом, признанным заказчиком**.

Главный вопрос ПТО:

**что уже выполнено, но еще не превращено в признанные деньги?**
"""
)


# ---------- KPI ----------

fact_total = df["fact_ev_total"].fillna(0).sum()
accepted_total = df["accepted_value"].fillna(0).sum()
gap_total = df["fact_vs_accepted_value_gap"].fillna(0).sum()

mtr_sold_total = df["mtr_sold_value"].fillna(0).sum()
mtr_cost_total = df["mtr_cost_value"].fillna(0).sum()

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric("Выполнено / EV", money(fact_total))
c2.metric("Признано заказчиком", money(accepted_total))
c3.metric("Разрыв факт / признание", money(gap_total))
c4.metric("Проданный МТР", money(mtr_sold_total))
c5.metric("Себестоимость МТР", money(mtr_cost_total))


# ---------- SYSTEM SUMMARY ----------

st.subheader("1. Накопление по системам")

system_df = (
    df.groupby(["project_code", "month_key", "system_label"], dropna=False)
    .agg(
        fact_qty_total=("fact_qty_total", "sum"),
        accepted_qty=("accepted_qty", "sum"),
        fact_ev_total=("fact_ev_total", "sum"),
        accepted_value=("accepted_value", "sum"),
        fact_vs_accepted_value_gap=("fact_vs_accepted_value_gap", "sum"),
        records_count=("records_count", "sum"),
    )
    .reset_index()
)

st.dataframe(system_df, use_container_width=True, height=300)


# ---------- DETAIL TABLE ----------

st.subheader("2. Детализация факт / признание")

detail_cols = [
    "month_key",
    "facility_building",
    "construction_discipline",
    "system_label",
    "iwp_id",
    "boq_code",
    "boq_description",
    "unit_of_measure",
    "project_qty",
    "fact_qty_total",
    "accepted_qty",
    "project_vs_fact_qty_gap",
    "fact_vs_accepted_qty_gap",
    "fact_ev_total",
    "accepted_value",
    "fact_vs_accepted_value_gap",
    "mtr_sold_value",
    "mtr_cost_value",
    "acceptance_status",
    "comment",
]

existing_cols = [c for c in detail_cols if c in df.columns]

st.dataframe(
    df[existing_cols].sort_values("fact_vs_accepted_value_gap", ascending=False),
    use_container_width=True,
    height=450,
)


# ---------- MANUAL INPUT ----------

st.subheader("3. Ввод данных ПТО")

st.info(
    "ПТО фиксирует признанный заказчиком объем, признанную сумму, МТР и причину зависания денег."
)

if df.empty:
    st.warning("Нет строк для ввода.")
else:
    selected_row_index = st.selectbox(
        "Выберите строку агрегации",
        df.index,
        format_func=lambda i: (
            f"{df.loc[i, 'month_key']} | "
            f"{df.loc[i, 'facility_building']} | "
            f"{df.loc[i, 'construction_discipline']} | "
            f"{df.loc[i, 'system_label']} | "
            f"{df.loc[i, 'iwp_id']} | "
            f"{df.loc[i, 'boq_code']}"
        ),
    )

    row = df.loc[selected_row_index]

    st.markdown("#### Выбранная строка")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Проектный объем", num(row.get("project_qty")))
    c2.metric("Факт объем", num(row.get("fact_qty_total")))
    c3.metric("Факт EV", money(row.get("fact_ev_total")))
    c4.metric("Текущий разрыв", money(row.get("fact_vs_accepted_value_gap")))

    with st.form("pto_acceptance_form"):
        accepted_qty = st.number_input(
            "Принятый объем",
            min_value=0.0,
            value=num(row.get("accepted_qty")),
        )

        accepted_value = st.number_input(
            "Признанная сумма, ₽",
            min_value=0.0,
            value=num(row.get("accepted_value")),
        )

        mtr_sold_value = st.number_input(
            "Проданный МТР / оборудование, ₽",
            min_value=0.0,
            value=num(row.get("mtr_sold_value")),
        )

        mtr_cost_value = st.number_input(
            "Себестоимость МТР / оборудования, ₽",
            min_value=0.0,
            value=num(row.get("mtr_cost_value")),
        )

        status_options = [
            "NOT_SUBMITTED",
            "SUBMITTED",
            "UNDER_REVIEW",
            "ACCEPTED",
            "PARTIALLY_ACCEPTED",
            "REJECTED",
            "ON_HOLD",
        ]

        current_status = row.get("acceptance_status")
        default_index = (
            status_options.index(current_status)
            if current_status in status_options
            else 0
        )

        acceptance_status = st.selectbox(
            "Статус признания",
            status_options,
            index=default_index,
        )

        comment = st.text_area(
            "Комментарий ПТО / причина зависания денег",
            value=str(row.get("comment")) if pd.notna(row.get("comment")) else "",
        )

        submitted = st.form_submit_button("Сохранить данные ПТО")

        if submitted:
            payload = {
                "project_code": row.get("project_code"),
                "month_key": row.get("month_key"),
                "facility_building": row.get("facility_building"),
                "construction_discipline": row.get("construction_discipline"),
                "system_label": row.get("system_label"),
                "iwp_id": row.get("iwp_id"),
                "boq_code": row.get("boq_code"),
                "project_qty": num(row.get("project_qty")),
                "accepted_qty": accepted_qty,
                "accepted_value": accepted_value,
                "mtr_sold_value": mtr_sold_value,
                "mtr_cost_value": mtr_cost_value,
                "acceptance_status": acceptance_status,
                "comment": comment,
            }

            supabase.table("pto_acceptance_registry").upsert(
    payload,
    on_conflict="project_code,month_key,facility_building,construction_discipline,system_label,iwp_id,boq_code",
).execute()
            st.success("Данные ПТО сохранены. Обновите экран.")