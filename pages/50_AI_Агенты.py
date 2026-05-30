import streamlit as st
import pandas as pd
from services.supabase_client import supabase

st.set_page_config(layout="wide")

st.title("AI Center / AI-Агенты")
st.caption(
    "Agent Harness — orchestration layer между Execution OS и AI-агентами: "
    "контекст, действия, проверка, human approval, audit."
)

AGENTS_CATALOG = [
    {
        "Агент": "AI Диагност плана",
        "Роль": "Диагностика месячного плана до запуска",
        "Входные данные": "Monthly Passport + Historical Productivity",
        "Выход": "Риск плана, перегрузка, недопуск",
        "Статус": "MVP",
    },
    {
        "Агент": "AI Constraint Controller",
        "Роль": "Контроль ограничений допуска",
        "Входные данные": "monthly_plan_constraints",
        "Выход": "Блокировки, owners, overdue",
        "Статус": "planned",
    },
    {
        "Агент": "AI Action Engine",
        "Роль": "Генерация корректирующих действий",
        "Входные данные": "AI findings",
        "Выход": "Action items",
        "Статус": "MVP",
    },
    {
        "Агент": "AI EVM Analyst",
        "Роль": "Анализ earned value",
        "Входные данные": "EV / AC / SPI / CPI",
        "Выход": "Диагностика исполнения",
        "Статус": "planned",
    },
    {
        "Агент": "AI Foreman Assistant",
        "Роль": "Поддержка прораба на фронте",
        "Входные данные": "Daily Progress + фронт + нормы",
        "Выход": "Подсказки, риски смены",
        "Статус": "planned",
    },
    {
        "Агент": "AI Contract / Claim Analyst",
        "Роль": "Коммерческий контроль и претензии",
        "Входные данные": "BOQ + акты + изменения",
        "Выход": "Основания предъявления, риски КС",
        "Статус": "planned",
    },
    {
        "Агент": "AI War Room Analyst",
        "Роль": "Совещание по блокировкам",
        "Входные данные": "constraints + overdue + owners",
        "Выход": "ТОП блокировок, agenda",
        "Статус": "planned",
    },
    {
        "Агент": "AI Acceptance Analyst",
        "Роль": "Признаваемость и приёмка",
        "Входные данные": "Приёмка + инспекции + акты",
        "Выход": "Риск непризнания, gap",
        "Статус": "planned",
    },
    {
        "Агент": "AI MTO Planner",
        "Роль": "Обеспечение материалами",
        "Входные данные": "План + поставки + остатки",
        "Выход": "Риски МТО, дефицит",
        "Статус": "planned",
    },
    {
        "Агент": "AI PTO Engineer",
        "Роль": "РД / IWP / исполнительность",
        "Входные данные": "РД + IWP + BOQ",
        "Выход": "Готовность документации",
        "Статус": "planned",
    },
]

STATUS_COLOR = {
    "MVP": "🟢",
    "planned": "🟡",
    "idea": "⚪",
}


def load_table(name: str) -> pd.DataFrame:
    response = supabase.table(name).select("*").limit(5000).execute()
    return pd.DataFrame(response.data or [])


def money(v) -> str:
    try:
        return f"{float(v):,.0f} ₽".replace(",", " ")
    except Exception:  # noqa: BLE001
        return "0 ₽"


def render_agent_catalog() -> None:
    st.markdown("## Каталог AI-агентов Execution OS")
    st.caption("Текущие и планируемые агенты в контуре Agent Harness.")

    catalog_df = pd.DataFrame(AGENTS_CATALOG)
    st.dataframe(catalog_df, use_container_width=True, hide_index=True)

    st.markdown("#### Карточки агентов")
    for row in AGENTS_CATALOG:
        badge = STATUS_COLOR.get(row["Статус"], "⚪")
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{row['Агент']}** — {row['Роль']}")
            c2.markdown(f"{badge} **{row['Статус']}**")
            c3, c4 = st.columns(2)
            c3.markdown(f"**Вход:** {row['Входные данные']}")
            c4.markdown(f"**Выход:** {row['Выход']}")

    st.markdown("---")
    st.markdown("## Агент контроля исполнения (активный MVP)")
    st.info(
        "Агент анализирует план, факт, отклонения, внеплановые работы, "
        "ошибки ввода и работу звеньев."
    )

    if st.button("Проанализировать исполнение проекта", key="exec_agent_analyze"):
        month_summary = load_table("smr_month_summary")
        reconciliation = load_table("smr_reconciliation")
        plan_line = load_table("smr_plan_line_control")
        crew = load_table("smr_crew_control")
        dq = load_table("smr_data_quality_issues")

        approved_plan = month_summary["approved_plan"].sum() if "approved_plan" in month_summary else 0
        matched_ev = month_summary["matched_ev"].sum() if "matched_ev" in month_summary else 0

        fact_only_ev = 0
        if not reconciliation.empty and "reconciliation_status" in reconciliation.columns:
            fact_only_ev = reconciliation[
                reconciliation["reconciliation_status"] == "FACT_ONLY"
            ]["ev_value"].sum()

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


def render_agent_harness() -> None:
    st.markdown("## Agent Harness / Контур управления AI-агентами")
    st.caption("Harness — orchestration layer между Execution OS и AI-агентами.")

    st.markdown(
        """
```
Execution OS
      ↓
Context Builder
      ↓
Agent Harness
      ↓
AI Agent
      ↓
Action Engine
      ↓
Human Approval
      ↓
Supabase / Audit Trail
```
"""
    )

    st.markdown("### Что делает Harness")
    h1, h2, h3 = st.columns(3)
    h4, h5 = st.columns(2)

    with h1.container(border=True):
        st.markdown("**Контекст**")
        st.markdown(
            "Подтягивает Supabase, исторические данные, ограничения, "
            "нормы, статус фронта."
        )
    with h2.container(border=True):
        st.markdown("**Действие**")
        st.markdown("Агент не просто отвечает — формирует action.")
    with h3.container(border=True):
        st.markdown("**Проверка**")
        st.markdown("Backpressure: SQL, KPI, правила, validation.")
    with h4.container(border=True):
        st.markdown("**Human Approval**")
        st.markdown("Ничего критичного без человека.")
    with h5.container(border=True):
        st.markdown("**Audit**")
        st.markdown("Все решения логируются.")

    st.markdown("---")
    st.info(
        "**DATA** → **CONTEXT** → **AGENT** → **ACTION** → **VALIDATION** → "
        "**HUMAN APPROVAL** → **RESULT** → **AUDIT**"
    )

    st.markdown("### Как это работает в Execution OS")
    st.markdown(
        """
1. Начальник участка загрузил месячный план
2. Harness собрал контекст
3. AI Диагност проверил нормы
4. Constraint Controller нашёл блокировки
5. Action Engine создал задачи
6. War Room получил проблемы
7. Человек подтвердил
8. Данные ушли в Execution OS
"""
    )

    st.warning(
        "**LLM без harness** = умный чат.\n\n"
        "**LLM + Harness** = исполнитель внутри среды проекта.\n\n"
        "Execution OS не строится вокруг «чата». "
        "Execution OS строится вокруг: **контекста + действий + контроля результата**."
    )


def render_ai_status() -> None:
    st.markdown("## Статус AI системы")
    st.caption("Сводка по агентам Execution OS (статично, v1).")

    total = len(AGENTS_CATALOG)
    mvp = sum(1 for a in AGENTS_CATALOG if a["Статус"] == "MVP")
    planned = sum(1 for a in AGENTS_CATALOG if a["Статус"] == "planned")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Всего агентов", total)
    c2.metric("В MVP", mvp)
    c3.metric("В разработке", planned)
    c4.metric("Подключено к данным", mvp)
    c5.metric("Готово к автоматизации", 1)

    st.markdown("---")
    st.markdown("#### Агенты по статусу")
    status_df = (
        pd.DataFrame(AGENTS_CATALOG)
        .groupby("Статус", as_index=False)
        .size()
        .rename(columns={"size": "Количество"})
    )
    st.dataframe(status_df, use_container_width=True, hide_index=True)

    st.info(
        "Следующий шаг: связать Agent Harness с Action Engine и War Room "
        "для сквозного цикла «диагностика → действие → подтверждение»."
    )


def render_roadmap() -> None:
    st.markdown("## Roadmap AI / Agent Harness")

    roadmap = [
        ("v1", "Ручной запуск анализа", "🟢 Текущая фаза"),
        ("v2", "AI action items", "🟡 В работе"),
        ("v3", "War Room automation", "⚪ Запланировано"),
        ("v4", "AI orchestration", "⚪ Запланировано"),
        ("v5", "Autonomous execution assistant", "⚪ Vision"),
    ]

    for version, title, phase in roadmap:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 2])
            c1.markdown(f"**{version}**")
            c2.markdown(title)
            c3.markdown(phase)


tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Каталог AI-агентов",
        "Agent Harness",
        "Статус AI системы",
        "Roadmap",
    ]
)

with tab1:
    render_agent_catalog()

with tab2:
    render_agent_harness()

with tab3:
    render_ai_status()

with tab4:
    render_roadmap()
