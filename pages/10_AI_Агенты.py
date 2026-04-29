import streamlit as st
import pandas as pd
from services.supabase_client import supabase

st.set_page_config(layout="wide")

st.title("AI-Агенты")
st.caption("Автономные цифровые управляющие: контроль процессов и анализ отклонений")

st.markdown("### Анализ исполнения проекта")

# 🔽 Кнопка запуска анализа
if st.button("Проанализировать исполнение"):

    try:
        # тянем данные из Supabase
        data = supabase.table("monthly_plan_vs_fact").select("*").execute()

        df = pd.DataFrame(data.data)

        if df.empty:
            st.warning("Нет данных для анализа")
        else:
            plan_total = df["plan_total"].sum()
            fact_total = df["fact_total"].sum()

            deviation = plan_total - fact_total

            st.markdown("## Результат анализа")

            st.write(f"План: {int(plan_total):,}".replace(",", " "))
            st.write(f"Факт: {int(fact_total):,}".replace(",", " "))
            st.write(f"Отклонение: {int(deviation):,}".replace(",", " "))

            if deviation > 0:
                st.error("Проект недовыполняется относительно плана")
            else:
                st.success("Исполнение соответствует или превышает план")

    except Exception as e:
        st.error(f"Ошибка анализа: {e}")