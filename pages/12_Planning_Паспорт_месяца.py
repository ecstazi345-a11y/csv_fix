import streamlit as st
import pandas as pd
from services.supabase_client import supabase

st.set_page_config(layout="wide")

VIEW_DASHBOARD = "monthly_plan_passport_dashboard_v1"

PASSPORT_STATUS_RU = {
    "DRAFT": "Черновик",
    "UNDER_REVIEW": "На проверке",
    "APPROVED": "Утверждён",
    "SUPERSEDED": "Заменён",
    "CANCELLED": "Отменён",
}

WEEK_PLAN_STATUS_RU = {
    "NOT_DECOMPOSED": "Не декомпозирован",
    "IN_PROGRESS": "В работе",
    "DECOMPOSED": "Декомпозирован",
}

EMPTY_PASSPORT_TEXT = """
**Утверждённый паспорт месяца пока не сформирован.**

Порядок:

1. Соберите черновик в **Конструкторе месячного плана**.
2. Отправьте его в **контур допуска**.
3. Сформируйте **проверки по отделам**.
4. Снимите **HOLD / FAIL** ограничения.
5. После утверждения система сформирует **Monthly Plan Passport**.
6. Далее паспорт будет декомпозирован в **Неделя → День → Звено**.
"""


@st.cache_data(ttl=300)
def load_passport_dashboard() -> pd.DataFrame:
    try:
        response = supabase.table(VIEW_DASHBOARD).select("*").limit(10000).execute()
        return pd.DataFrame(response.data or [])
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def money(v) -> str:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "0 ₽"
        return f"{float(v):,.0f} ₽".replace(",", " ")
    except Exception:  # noqa: BLE001
        return "0 ₽"


def num(v) -> float:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return 0.0
        return float(v)
    except Exception:  # noqa: BLE001
        return 0.0


def filter_options(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def render_architecture_flow() -> None:
    st.markdown(
        """
```
Draft Monthly Plan
    ↓
Review Queue
    ↓
Constraints / Admission
    ↓
War Room
    ↓
Approved Monthly Plan Passport
    ↓
Week Plan
    ↓
Day Plan
    ↓
Crew Assignment
    ↓
Foreman Shift / Daily Progress
```
"""
    )


def render_empty_blocks() -> None:
    blocks = [
        ("Статус паспорта", "Ожидает утверждения Monthly Plan Passport."),
        ("План месяца", "BOQ-коды, объёмы и стоимость появятся после утверждения."),
        ("Звенья / трудозатраты", "Звенья, часы и трудозатраты — из плана звеньев после утверждения."),
        ("Допуск", "Статус admission по строкам — после прохождения контура допуска."),
        ("Декомпозиция в недели", "Следующий этап после утверждения паспорта (v2)."),
        ("Декомпозиция в дни", "Следующий этап после недельного плана (v2)."),
        ("Звенья и сменные задания", "Foreman Shift / Daily Progress — после декомпозиции (v2)."),
    ]
    for title, caption in blocks:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(caption)


def render_passport_data(df: pd.DataFrame) -> None:
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        selected_month = st.selectbox("Месяц", filter_options(df, "month_key"))
    with col_f2:
        selected_project = st.selectbox("Проект", filter_options(df, "project_code"))

    filtered = df.copy()
    if selected_month != "Все":
        filtered = filtered[filtered["month_key"] == selected_month]
    if selected_project != "Все" and "project_code" in filtered.columns:
        filtered = filtered[filtered["project_code"] == selected_project]

    if filtered.empty:
        st.info("По выбранным фильтрам строк паспорта нет.")
        return

    for col in ("planned_qty", "plan_value", "required_hours", "labor_cost"):
        if col in filtered.columns:
            filtered[col] = pd.to_numeric(filtered[col], errors="coerce")

    passport_status = filtered["passport_status"].iloc[0] if "passport_status" in filtered.columns else "—"
    passport_name = filtered["passport_name"].iloc[0] if "passport_name" in filtered.columns else "—"
    approved_by = filtered["approved_by"].iloc[0] if "approved_by" in filtered.columns else "—"
    approved_at = filtered["approved_at"].iloc[0] if "approved_at" in filtered.columns else "—"

    st.markdown("### Статус паспорта")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Статус", PASSPORT_STATUS_RU.get(str(passport_status), str(passport_status)))
        c2.metric("Наименование", str(passport_name))
        c3.metric("Утвердил", str(approved_by) if approved_by and str(approved_by) != "nan" else "—")
        c4.metric("Дата утверждения", str(approved_at)[:10] if approved_at and str(approved_at) != "nan" else "—")

    st.markdown("### План месяца")
    with st.container(border=True):
        p1, p2, p3 = st.columns(3)
        p1.metric("Строк плана", len(filtered))
        p2.metric("Плановый объём", f"{filtered['planned_qty'].sum():,.2f}" if "planned_qty" in filtered.columns else "—")
        p3.metric("Плановая стоимость", money(filtered["plan_value"].sum() if "plan_value" in filtered.columns else 0))

    st.markdown("### Звенья / трудозатраты")
    with st.container(border=True):
        z1, z2, z3 = st.columns(3)
        crews = filtered["crew_id"].dropna().nunique() if "crew_id" in filtered.columns else 0
        z1.metric("Звеньев", crews)
        z2.metric("Требуемые часы", f"{filtered['required_hours'].sum():,.1f}" if "required_hours" in filtered.columns else "—")
        z3.metric("Трудозатраты", money(filtered["labor_cost"].sum() if "labor_cost" in filtered.columns else 0))

    st.markdown("### Допуск")
    with st.container(border=True):
        if "admission_status" in filtered.columns:
            admission_counts = filtered["admission_status"].fillna("—").value_counts()
            cols = st.columns(min(len(admission_counts), 4) or 1)
            for i, (status, count) in enumerate(admission_counts.items()):
                cols[i % len(cols)].metric(str(status), int(count))
        else:
            st.caption("Статус допуска по строкам — поле admission_status.")

    st.markdown("### Декомпозиция в недели")
    with st.container(border=True):
        if "week_plan_status" in filtered.columns:
            week_counts = filtered["week_plan_status"].fillna("NOT_DECOMPOSED").value_counts()
            for status, count in week_counts.items():
                label = WEEK_PLAN_STATUS_RU.get(str(status), str(status))
                st.markdown(f"- **{label}:** {count} строк")
        else:
            st.caption("Декомпозиция в недели — следующий этап (v2).")

    st.markdown("### Декомпозиция в дни")
    with st.container(border=True):
        st.caption("Декомпозиция в дни будет доступна после формирования недельного плана (v2).")

    st.markdown("### Звенья и сменные задания")
    with st.container(border=True):
        st.caption("Сменные задания прораба формируются после декомпозиции плана (v2).")

    st.markdown("---")
    st.subheader("Строки утверждённого паспорта")

    display_columns = [
        "month_key",
        "project_code",
        "passport_status",
        "facility_building",
        "construction_discipline",
        "boq_code",
        "boq_name",
        "crew_id",
        "planned_qty",
        "plan_value",
        "required_hours",
        "labor_cost",
        "admission_status",
        "week_plan_status",
    ]
    existing = [c for c in display_columns if c in filtered.columns]
    st.dataframe(filtered[existing], use_container_width=True, hide_index=True)


st.title("Паспорт месяца")
st.caption(
    "Approved Monthly Plan Passport — финальный утверждённый результат месячного "
    "планирования после конструктора, допуска и снятия ограничений."
)

st.markdown(
    """
## Назначение раздела

**Паспорт месяца — это НЕ view от review queue и НЕ plan-vs-fact.**

Это финальный утверждённый результат после:

1. **Конструктора месячного планирования**
2. Загрузки двух входных блоков:
   - план работ (BOQ, титул, объём, деньги)
   - план звеньев (звенья, люди, часы, трудозатраты, стоимость)
3. **Проверок допуска** (исполнимый фронт, признаваемость, экономика звена)
4. **Утверждения**

Только после этого появляется **Approved Monthly Plan Passport**.
"""
)

st.divider()
st.markdown("#### Архитектурный поток")
render_architecture_flow()
st.divider()

passport_df = load_passport_dashboard()

if passport_df.empty:
    st.info(EMPTY_PASSPORT_TEXT)
    render_empty_blocks()
else:
    st.success(f"Загружено из `{VIEW_DASHBOARD}`")
    render_passport_data(passport_df)
