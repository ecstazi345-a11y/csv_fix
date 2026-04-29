import streamlit as st
import pandas as pd
from services.supabase_client import supabase
st.set_page_config(layout="wide")

st.title("Главная")
st.caption(
    "Главная управленческая кабина проекта: допуск, исполнение, приемка, признание и деньги."
)

st.markdown(
    """
## Назначение раздела

Главная страница предназначена для быстрого понимания состояния проекта.

Здесь должна собираться сводная картина:

- какой объем работ включен в план
- какой фронт готов к выполнению
- какие работы фактически выполнены
- какие объемы переданы на приемку
- какие работы признаны заказчиком
- где возникает разрыв между выполнением и деньгами
- какие зоны требуют немедленного управленческого решения

## Управленческий смысл

Руководитель должен за 1–2 минуты понять:

- где проект движется по плану
- где работы заблокированы
- где факт не превращается в признанный объем
- где формируются потери
- какие действия нужны сегодня
"""
)
def load_table(name):
    response = supabase.table(name).select("*").limit(5000).execute()
    return pd.DataFrame(response.data)


try:
    month_summary = load_table("smr_month_summary")
    reconciliation = load_table("smr_reconciliation")

    approved_plan = month_summary["approved_plan"].sum() if "approved_plan" in month_summary.columns else 0
    matched_ev = month_summary["matched_ev"].sum() if "matched_ev" in month_summary.columns else 0

    fact_only_ev = 0
    if not reconciliation.empty and "reconciliation_status" in reconciliation.columns:
        fact_only_ev = reconciliation[reconciliation["reconciliation_status"] == "FACT_ONLY"]["ev_value"].sum()

    total_ev = matched_ev + fact_only_ev
    gap = approved_plan - matched_ev

except Exception:
    approved_plan = 0
    matched_ev = 0
    fact_only_ev = 0
    total_ev = 0
    gap = 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Approved план", f"{approved_plan:,.0f} ₽".replace(",", " "))
c2.metric("Факт по плану", f"{matched_ev:,.0f} ₽".replace(",", " "))
c3.metric("Всего освоено", f"{total_ev:,.0f} ₽".replace(",", " "))
c4.metric("Разрыв", f"{gap:,.0f} ₽".replace(",", " "))

st.info("Сводная панель проекта будет подключена после формирования итоговой SQL-витрины.")