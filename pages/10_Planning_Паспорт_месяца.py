import streamlit as st
import pandas as pd
from services.queries import get_monthly_plan_vs_fact

st.set_page_config(layout="wide")

st.title("Паспорт месяца")
st.caption("Утвержденная модель месячного плана: объемы, стоимость, звенья, трудозатраты, затраты, фронты и отклонения.")

st.markdown(
    """
## Назначение раздела

Паспорт месяца — это управленческая модель месячного выполнения работ.

Он показывает:

- какие работы включены в план месяца
- какие объемы и стоимость запланированы
- какие звенья закреплены за фронтами
- какие работы утверждены к выполнению
- какой факт уже лег на план
- где возникает отклонение по объему и стоимости

## Управленческий смысл

Паспорт месяца отвечает на вопрос:

**что именно проект должен выполнить в этом месяце, какими ресурсами и на какую стоимость.**

Это основа для контроля исполнения, приемки и последующей конверсии результата в деньги.
"""
)

st.divider()

try:
    data = get_monthly_plan_vs_fact()
    df = pd.DataFrame(data)

    if df.empty:
        st.warning("Витрина monthly_plan_vs_fact пока пустая.")
    else:
        # -----------------------------
        # Подготовка фильтров
        # -----------------------------
        month_options = ["Все"] + sorted(
            [x for x in df["month_key"].dropna().unique().tolist()]
        )
        crew_options = ["Все"] + sorted(
            [x for x in df["crew"].dropna().unique().tolist()]
        )

        col_f1, col_f2 = st.columns(2)

        with col_f1:
            selected_month = st.selectbox("Фильтр по месяцу", month_options)

        with col_f2:
            selected_crew = st.selectbox("Фильтр по звену", crew_options)

        filtered_df = df.copy()

        if selected_month != "Все":
            filtered_df = filtered_df[filtered_df["month_key"] == selected_month]

        if selected_crew != "Все":
            filtered_df = filtered_df[filtered_df["crew"] == selected_crew]

        # -----------------------------
        # Числовые поля на всякий случай
        # -----------------------------
        numeric_cols = [
            "plan_qty_month",
            "plan_pv_workvalue_auto",
            "actual_qty_total",
            "ev_total",
            "direct_work_hours_total",
            "productive_work_hours_total",
            "idle_hours_total",
            "qty_variance",
            "value_variance",
            "qty_progress_percent",
            "value_progress_percent",
        ]

        for col in numeric_cols:
            if col in filtered_df.columns:
                filtered_df[col] = pd.to_numeric(filtered_df[col], errors="coerce")

        # -----------------------------
        # Метрики
        # -----------------------------
        total_plan_qty = (
            filtered_df["plan_qty_month"].sum()
            if "plan_qty_month" in filtered_df.columns
            else 0
        )
        total_actual_qty = (
            filtered_df["actual_qty_total"].sum()
            if "actual_qty_total" in filtered_df.columns
            else 0
        )
        total_plan_value = (
            filtered_df["plan_pv_workvalue_auto"].sum()
            if "plan_pv_workvalue_auto" in filtered_df.columns
            else 0
        )
        total_ev = (
            filtered_df["ev_total"].sum() if "ev_total" in filtered_df.columns else 0
        )
        total_direct_hours = (
            filtered_df["direct_work_hours_total"].sum()
            if "direct_work_hours_total" in filtered_df.columns
            else 0
        )
        total_idle_hours = (
            filtered_df["idle_hours_total"].sum()
            if "idle_hours_total" in filtered_df.columns
            else 0
        )

        qty_gap = total_plan_qty - total_actual_qty
        value_gap = total_plan_value - total_ev

        qty_progress = None
        if total_plan_qty and total_plan_qty != 0:
            qty_progress = round((total_actual_qty / total_plan_qty) * 100, 2)

        value_progress = None
        if total_plan_value and total_plan_value != 0:
            value_progress = round((total_ev / total_plan_value) * 100, 2)

        st.success("Витрина monthly_plan_vs_fact загружена")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Плановый объем", f"{total_plan_qty:,.2f}")
        m2.metric("Выполненный объем", f"{total_actual_qty:,.2f}")
        m3.metric("Плановая стоимость", f"{total_plan_value:,.0f} ₽")
        m4.metric("Освоенная стоимость", f"{total_ev:,.0f} ₽")
        
        m5, m6, m7, m8 = st.columns(4)
        m5.metric("Отклонение по объему", f"{qty_gap:,.2f}")
        m6.metric("Отклонение по стоимости", f"{value_gap:,.2f}")
        m7.metric(
            "Выполнение по объему, %",
            f"{qty_progress if qty_progress is not None else '—'}",
        )
        m8.metric(
            "Выполнение по стоимости, %",
            f"{value_progress if value_progress is not None else '—'}",
        )

        m9, m10 = st.columns(2)
        m9.metric("Прямые трудозатраты", f"{total_direct_hours:,.2f} ч")
        m10.metric("Простои", f"{total_idle_hours:,.2f} ч")
       
        st.divider()

        st.subheader("Таблица План-Факт")

        display_columns = [
            "month_key",
            "crew",
            "facility_building",
            "construction_discipline",
            "boq_code",
            "boq_name",
            "iwp_id_export",
            "system_label",
            "unit_of_measure",
            "plan_qty_month",
            "actual_qty_total",
            "qty_variance",
            "qty_progress_percent",
            "plan_pv_workvalue_auto",
            "ev_total",
            "value_variance",
            "value_progress_percent",
            "direct_work_hours_total",
            "productive_work_hours_total",
            "idle_hours_total",
            "fact_row_count",
            "budget_status",
        ]

        existing_columns = [c for c in display_columns if c in filtered_df.columns]
        st.dataframe(filtered_df[existing_columns], use_container_width=True)

except Exception as e:
    st.error("Ошибка при загрузке monthly_plan_vs_fact")
    st.code(str(e))
