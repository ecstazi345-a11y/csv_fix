import streamlit as st

st.set_page_config(layout="wide")

st.title("Экономика и маржа")
st.caption(
    "Операционная экономика субподрядчика: direct, indirect, доля ИТР, выгорание труда и маржа."
)

st.markdown(
    """
## Что здесь делаем

Здесь мы смотрим экономику проекта не как бухгалтерию,
а как управленческую систему.

Здесь должны быть:
- direct cost
- indirect cost
- доля ИТР
- EV per direct hour
- burn without recognition
- margin by package

## Для чего нужна страница
Чтобы видеть, где проект реально теряет деньги.
"""
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Direct cost", "—")
c2.metric("Indirect cost", "—")
c3.metric("Доля ИТР", "—")
c4.metric("EV / Direct Hour", "—")

st.info("Позже сюда подключим economic summary и loss analysis.")
