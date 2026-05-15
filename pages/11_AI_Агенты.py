import streamlit as st
import pandas as pd
from services.supabase_client import supabase

st.set_page_config(layout="wide")

st.title("AI-Агенты")
st.caption("Автономные цифровые управляющие: контроль процессов, анализ отклонений и усиление управленческих решений")

def load_table(name):
    response = supabase.table(name).select("*").limit(5000).execute()
    return pd.DataFrame(response.data)

def money(v):
    try:
        return f"{float(v):,.0f} ₽".replace(",", " ")
    except Exception:
        return "0 ₽"

st.markdown("## Агент контроля исполнения")

st.info(
    "Агент анализирует план, факт, отклонения, внеплановые работы, ошибки ввода и работу звеньев."
)

if st.button("Проанализировать исполнение проекта"):
    month_summary = load_table("smr_month_summary")
    reconciliation = load_table("smr_reconciliation")
    plan_line = load_table("smr_plan_line_control")
    crew = load_table("smr_crew_control")
    dq = load_table("smr_data_quality_issues")

    approved_plan = month_summary["approved_plan"].sum() if "approved_plan" in month_summary else 0
    matched_ev = month_summary["matched_ev"].sum() if "matched_ev" in month_summary else 0

    fact_only_ev = 0
    if not reconciliation.empty and "reconciliation_status" in reconciliation.columns:
        fact_only_ev = reconciliation[reconciliation["reconciliation_status"] == "FACT_ONLY"]["ev_value"].sum()

    total_ev = matched_ev + fact_only_ev
    remaining = approved_plan - matched_ev

    st.markdown("### 1. Исполнение")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Approved план", money(approved_plan))
    c2.metric("Факт по плану", money(matched_ev))
    c3.metric("Факт вне плана", money(fact_only_ev))
    c4.metric("Остаток", money(remaining))

    st.markdown("### 2. Вывод агента")

    if fact_only_ev > 0:
        st.warning(
            f"Обнаружены внеплановые работы на сумму {money(fact_only_ev)}. "
            "Это признак хаотичного исполнения или работ вне месячного паспорта."
        )

    if remaining > 0:
        st.error(
            f"Не закрыт утвержденный фронт на сумму {money(remaining)}. "
            "Нужно проверить PLAN_ONLY и UNDERPERFORM позиции."
        )

    if not dq.empty:
        dq_impact = dq["raw_ev"].sum() if "raw_ev" in dq.columns else 0
        st.error(
            f"Есть ошибки классификации факта на сумму {money(dq_impact)}. "
            "Проверьте IWP, титул, дисциплину и привязку факта."
        )
    else:
        st.success("Критичных ошибок классификации факта не обнаружено.")

    st.markdown("### 3. ТОП проблемных строк")

    if not plan_line.empty and "value_variance" in plan_line.columns:
        cols = [
            "execution_status",
            "facility_building",
            "construction_discipline",
            "boq_code",
            "iwp_id_export",
            "system_label",
            "plan_crews",
            "fact_crews",
            "plan_value",
            "ev_value",
            "value_variance",
        ]
        cols = [c for c in cols if c in plan_line.columns]

        top = plan_line[cols].sort_values("value_variance", ascending=False).head(10)
        st.dataframe(top, use_container_width=True)

    st.markdown("### 4. Управленческое действие")

    st.markdown(
        """
**Что сделать руководителю:**

1. Проверить строки `PLAN_ONLY` — план есть, факта нет.  
2. Проверить `FACT_ONLY` — факт есть, но работа не была в месячном плане.  
3. Проверить `WRONG_CREW` — звенья работают не по плану.  
4. Исправить ошибки классификации Daily Progress.  
5. На следующую неделю скорректировать фронт, звенья и приоритетные IWP.
"""
    )