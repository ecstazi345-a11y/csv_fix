import streamlit as st
import pandas as pd
from services.supabase_client import supabase

st.set_page_config(layout="wide")

st.title("СМР / Исполнение / План-Факт")
st.caption(
    "Контур СМР: Monthly Passport Plan → Daily Progress → отклонения → звенья → управленческие выводы."
)


# ---------------- helpers ----------------


def load_table(table_name: str, limit: int = 5000) -> pd.DataFrame:
    response = supabase.table(table_name).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


def to_num(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def money(value):
    try:
        return f"{value:,.0f} ₽".replace(",", " ")
    except Exception:
        return "0 ₽"


def pct(value):
    try:
        return f"{value:.1f}%"
    except Exception:
        return "0%"


def options(df: pd.DataFrame, col: str):
    if col not in df.columns:
        return ["Все"]
    vals = sorted([x for x in df[col].dropna().unique().tolist() if str(x).strip()])
    return ["Все"] + vals


def apply_common_filters(df: pd.DataFrame, project, month, facility, discipline):
    if df.empty:
        return df

    result = df.copy()

    if project != "Все" and "project_code" in result.columns:
        result = result[result["project_code"] == project]

    if month != "Все" and "month_key" in result.columns:
        result = result[result["month_key"] == month]

    if facility != "Все" and "facility_building" in result.columns:
        result = result[result["facility_building"] == facility]

    if discipline != "Все" and "construction_discipline" in result.columns:
        result = result[result["construction_discipline"] == discipline]

    return result


def format_money_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    money_cols = [
        "plan_total",
        "approved_plan",
        "matched_ev",
        "approved_remaining",
        "plan_value",
        "approved_plan_value",
        "ev_value",
        "fact_only_ev",
        "value_variance",
        "value_loss",
        "wrong_crew_ev",
        "planned_value",
        "actual_ev",
        "raw_ev",
        "smr_ev",
        "ev_difference",
    ]

    for col in money_cols:
        if col in result.columns:
            result[col] = result[col].apply(lambda x: money(x))

    return result


# ---------------- load data ----------------

month_summary = load_table("smr_month_summary")
plan_line = load_table("smr_plan_line_control")
reconciliation = load_table("smr_reconciliation")
crew_control = load_table("smr_crew_control")
problem_aggregation = load_table("smr_problem_aggregation")
data_quality = load_table("smr_data_quality_check")
data_quality_issues = load_table("smr_data_quality_issues")

numeric_cols = [
    "plan_total",
    "approved_plan",
    "matched_ev",
    "approved_remaining",
    "execution_percent",
    "plan_qty",
    "actual_qty",
    "plan_value",
    "ev_value",
    "direct_work_hours",
    "idle_hours",
    "wrong_crew_ev",
    "fact_rows",
    "qty_variance",
    "value_variance",
    "planned_value",
    "actual_ev",
    "value_variance",
    "raw_ev",
]

for df in [
    month_summary,
    plan_line,
    reconciliation,
    crew_control,
    problem_aggregation,
    data_quality,
    data_quality_issues,
]:
    to_num(df, numeric_cols)


# ---------------- filters ----------------

st.sidebar.header("Фильтры")

filter_source = pd.concat(
    [
        (
            month_summary[
                [
                    "project_code",
                    "month_key",
                    "facility_building",
                    "construction_discipline",
                ]
            ]
            if not month_summary.empty
            else pd.DataFrame()
        ),
        (
            plan_line[
                [
                    "project_code",
                    "month_key",
                    "facility_building",
                    "construction_discipline",
                ]
            ]
            if not plan_line.empty
            else pd.DataFrame()
        ),
    ],
    ignore_index=True,
)

selected_project = st.sidebar.selectbox(
    "Проект", options(filter_source, "project_code")
)
selected_month = st.sidebar.selectbox("Месяц", options(filter_source, "month_key"))
selected_facility = st.sidebar.selectbox(
    "Здание / титул", options(filter_source, "facility_building")
)
selected_discipline = st.sidebar.selectbox(
    "Дисциплина", options(filter_source, "construction_discipline")
)

crew_source = pd.concat(
    [
        (
            plan_line[["plan_crews"]].rename(columns={"plan_crews": "crew"})
            if "plan_crews" in plan_line.columns
            else pd.DataFrame()
        ),
        (
            crew_control[["crew_id"]].rename(columns={"crew_id": "crew"})
            if "crew_id" in crew_control.columns
            else pd.DataFrame()
        ),
    ],
    ignore_index=True,
)

selected_crew = st.sidebar.selectbox("Звено", options(crew_source, "crew"))

budget_status = st.sidebar.selectbox(
    "Budget Status",
    (
        options(plan_line, "budget_statuses")
        if "budget_statuses" in plan_line.columns
        else ["Все"]
    ),
)

execution_status = st.sidebar.selectbox(
    "Execution Status",
    (
        options(plan_line, "execution_status")
        if "execution_status" in plan_line.columns
        else ["Все"]
    ),
)

st.sidebar.caption(
    "Фильтр по ISO-неделям добавим после появления week_key / iso_week в Supabase."
)
if st.sidebar.button("🔄 Обновить экран"):
    st.rerun()

# ---------------- apply filters ----------------

month_summary_f = apply_common_filters(
    month_summary,
    selected_project,
    selected_month,
    selected_facility,
    selected_discipline,
)

plan_line_f = apply_common_filters(
    plan_line, selected_project, selected_month, selected_facility, selected_discipline
)

reconciliation_f = apply_common_filters(
    reconciliation,
    selected_project,
    selected_month,
    selected_facility,
    selected_discipline,
)

crew_control_f = apply_common_filters(
    crew_control,
    selected_project,
    selected_month,
    selected_facility,
    selected_discipline,
)
problem_aggregation_f = apply_common_filters(
    problem_aggregation,
    selected_project,
    selected_month,
    selected_facility,
    selected_discipline,
)

data_quality_f = apply_common_filters(
    data_quality, selected_project, selected_month, "Все", "Все"
)
data_quality_issues_f = apply_common_filters(
    data_quality_issues, selected_project, selected_month, "Все", "Все"
)
# ---------- Crew / Budget / Execution filters ----------

if selected_crew != "Все":
    if not plan_line_f.empty and "plan_crews" in plan_line_f.columns and "fact_crews" in plan_line_f.columns:
        plan_line_f = plan_line_f[
            plan_line_f["plan_crews"].astype(str).str.contains(selected_crew, na=False)
            | plan_line_f["fact_crews"].astype(str).str.contains(selected_crew, na=False)
        ]

    if not problem_aggregation_f.empty and "plan_crews" in problem_aggregation_f.columns and "fact_crews" in problem_aggregation_f.columns:
        problem_aggregation_f = problem_aggregation_f[
            problem_aggregation_f["plan_crews"].astype(str).str.contains(selected_crew, na=False)
            | problem_aggregation_f["fact_crews"].astype(str).str.contains(selected_crew, na=False)
        ]

    if not crew_control_f.empty and "crew_id" in crew_control_f.columns:
        crew_control_f = crew_control_f[crew_control_f["crew_id"] == selected_crew]

if budget_status != "Все" and "budget_statuses" in plan_line_f.columns:
    plan_line_f = plan_line_f[
        plan_line_f["budget_statuses"].astype(str).str.contains(budget_status, na=False)
    ]

if execution_status != "Все" and "execution_status" in plan_line_f.columns:
    plan_line_f = plan_line_f[
        plan_line_f["execution_status"] == execution_status
    ]


# ---------------- KPI ----------------

# ---------------- KPI ----------------

# ---------- KPI calculations ----------

if selected_crew != "Все":
    crew_kpi = crew_control_f.copy()

    plan_total = (
        crew_kpi["planned_value"].sum()
        if "planned_value" in crew_kpi.columns
        else 0
    )

    approved_plan = (
        crew_kpi["approved_planned_value"].sum()
        if "approved_planned_value" in crew_kpi.columns
        else plan_total
    )

    matched_ev = (
        crew_kpi["actual_ev"].sum()
        if "actual_ev" in crew_kpi.columns
        else 0
    )

    fact_only_ev = 0

else:
    plan_total = (
        month_summary_f["plan_total"].sum()
        if "plan_total" in month_summary_f.columns
        else 0
    )

    approved_plan = (
        month_summary_f["approved_plan"].sum()
        if "approved_plan" in month_summary_f.columns
        else 0
    )

    matched_ev = (
        month_summary_f["matched_ev"].sum()
        if "matched_ev" in month_summary_f.columns
        else 0
    )

    fact_only_ev = 0
    if not reconciliation_f.empty and "reconciliation_status" in reconciliation_f.columns:
        fact_only_ev = reconciliation_f[
            reconciliation_f["reconciliation_status"] == "FACT_ONLY"
        ]["ev_value"].sum()

total_ev = matched_ev + fact_only_ev

approved_remaining = approved_plan - matched_ev
execution_percent_value = (matched_ev / approved_plan * 100) if approved_plan else 0
total_execution_percent = (total_ev / approved_plan * 100) if approved_plan else 0

total_fact = total_ev
chaos_percent = (fact_only_ev / total_fact * 100) if total_fact else 0


# ---------------- UI ----------------
# ---------------- Data Quality ----------------

st.subheader("0. Контроль качества входных данных")

if not data_quality_f.empty:
    dq = data_quality_f.copy()

    issue_cols = [
        "missing_project_code",
        "missing_month_key",
        "missing_boq",
        "missing_iwp_id",
        "missing_system_label",
    ]

    for col in issue_cols + ["total_rows", "ev_value_at_risk"]:
        if col in dq.columns:
            dq[col] = pd.to_numeric(dq[col], errors="coerce").fillna(0)

    total_issues = 0
    for col in issue_cols:
        if col in dq.columns:
            total_issues += dq[col].sum()

    if total_issues == 0:
        st.success(
            "Качество входных данных OK: критичных пропусков по выбранному проекту/месяцу нет."
        )
    else:
        st.error(
            f"Обнаружены пропуски в ключевых полях: {int(total_issues)}. "
            "Эти записи могут выпадать из план-факта."
        )

    st.dataframe(dq, use_container_width=True)
else:
    st.warning("Нет данных в smr_data_quality_check по выбранным фильтрам.")
# ---------------- Data Quality Issues ----------------

st.subheader("0.1 Ошибки классификации факта")

if not data_quality_issues_f.empty:
    issue_total = data_quality_issues_f["raw_ev"].sum()

    st.error(
        f"Обнаружены ошибки классификации факта на сумму: {money(issue_total)}. "
        "Проверьте Facility / Discipline / IWP в Daily Progress."
    )

    issue_cols = [
        "issue_type",
        "work_boq_code",
        "work_iwp_id",
        "work_system_label",
        "raw_facility_building",
        "smr_facility_building",
        "raw_construction_discipline",
        "smr_construction_discipline",
        "raw_ev",
    ]

    existing_issue_cols = [c for c in issue_cols if c in data_quality_issues_f.columns]

    st.dataframe(
        data_quality_issues_f[existing_issue_cols].sort_values(
            "raw_ev", ascending=False
        ),
        use_container_width=True,
        height=280,
    )

    st.caption(
        "raw_* — как факт записан мастером. "
        "smr_* — как эта работа классифицирована в месячном плане."
    )
else:
    st.success("Ошибок классификации факта не обнаружено.")
st.subheader("1. Сводка СМР за период")

c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)

c1.metric("План всего", money(plan_total))
c2.metric("Approved план", money(approved_plan))
c3.metric("Факт по плану / EV", money(matched_ev))
c4.metric("Факт вне плана", money(fact_only_ev))
c5.metric("Всего освоено", money(total_ev))
c6.metric("Остаток Approved", money(approved_remaining))
c7.metric("Исполнение Approved", pct(execution_percent_value))  # ← ВОТ ОНО
c8.metric("Освоение всего", pct(total_execution_percent))

if fact_only_ev > 0:
    st.warning(
        f"Факт вне месячного плана: {money(fact_only_ev)}. "
        f"Доля хаотичного исполнения: {pct(chaos_percent)}. "
        "Нужно разобрать, почему работы выполняются вне утверждённого фронта."
    )

if approved_remaining > 0:
    st.info(
        f"Остаток утверждённого плана: {money(approved_remaining)}. "
        "Это Approved-объём, который ещё не закрыт фактом."
    )


# ---------------- Reconciliation ----------------

st.subheader("2. План / Факт / Вне плана")

if not reconciliation_f.empty:
    rec_summary = (
        reconciliation_f.groupby("reconciliation_status", dropna=False)
        .agg(
            rows_count=("reconciliation_status", "count"),
            plan_qty=("plan_qty", "sum"),
            actual_qty=("actual_qty", "sum"),
            approved_plan_value=("approved_plan_value", "sum"),
            plan_value=("plan_value", "sum"),
            ev_value=("ev_value", "sum"),
        )
        .reset_index()
    )

    st.dataframe(format_money_columns(rec_summary), use_container_width=True)

    st.caption(
        "MATCHED — плановая работа, на которую лёг факт. "
        "PLAN_ONLY — план есть, факта нет. "
        "FACT_ONLY — факт есть, но в месячном плане такой строки не было."
    )
else:
    st.warning("Нет данных по reconciliation для выбранных фильтров.")


# ---------------- Plan line control ----------------

st.subheader("3. Где сломался план по строкам Monthly Passport")

if not plan_line_f.empty:
    plan_cols = [
        "execution_status",
        "month_key",
        "facility_building",
        "construction_discipline",
        "budget_statuses",
        "boq_code",
        "boq_name",
        "iwp_id_export",
        "system_label",
        "plan_crews",
        "fact_crews",
        "plan_qty",
        "actual_qty",
        "plan_value",
        "ev_value",
        "wrong_crew_ev",
        "qty_variance",
        "value_variance",
    ]

    existing_cols = [c for c in plan_cols if c in plan_line_f.columns]

    plan_line_view = plan_line_f[existing_cols].sort_values(
        "value_variance", ascending=False
    )

    st.dataframe(
        format_money_columns(plan_line_view),
        use_container_width=True,
        height=420,
    )

    status_summary = (
        plan_line_f.groupby("execution_status", dropna=False)
        .agg(
            rows_count=("execution_status", "count"),
            plan_value=("plan_value", "sum"),
            ev_value=("ev_value", "sum"),
            wrong_crew_ev=("wrong_crew_ev", "sum"),
        )
        .reset_index()
    )

    st.markdown("#### Статусы исполнения")
    st.dataframe(format_money_columns(status_summary), use_container_width=True)

else:
    st.warning("Нет строк плана по выбранным фильтрам.")


# ---------------- Fact only ----------------

st.subheader("4. Факт вне плана")

fact_only_df = pd.DataFrame()

if not reconciliation_f.empty and "reconciliation_status" in reconciliation_f.columns:
    fact_only_df = reconciliation_f[
        reconciliation_f["reconciliation_status"] == "FACT_ONLY"
    ].copy()

if not fact_only_df.empty:
    fact_cols = [
        "month_key",
        "facility_building",
        "construction_discipline",
        "work_boq_code",
        "boq_name",
        "work_iwp_id",
        "work_system_label",
        "actual_qty",
        "ev_value",
        "direct_work_hours",
        "idle_hours",
    ]

    existing_cols = [c for c in fact_cols if c in fact_only_df.columns]

    st.dataframe(
        fact_only_df[existing_cols].sort_values("ev_value", ascending=False),
        use_container_width=True,
        height=350,
    )

    st.caption(
        "Это работы, которые появились в Daily Progress, но не нашли соответствующую строку в Monthly Passport Plan."
    )
else:
    st.success("Факт вне плана не найден по выбранным фильтрам.")


# ---------------- Plan only ----------------

st.subheader("5. План без факта")

plan_only_df = pd.DataFrame()

if not reconciliation_f.empty and "reconciliation_status" in reconciliation_f.columns:
    plan_only_df = reconciliation_f[
        reconciliation_f["reconciliation_status"] == "PLAN_ONLY"
    ].copy()

if not plan_only_df.empty:
    plan_only_cols = [
        "month_key",
        "facility_building",
        "construction_discipline",
        "work_boq_code",
        "boq_name",
        "work_iwp_id",
        "work_system_label",
        "plan_qty",
        "plan_value",
    ]

    existing_cols = [c for c in plan_only_cols if c in plan_only_df.columns]

    st.dataframe(
        plan_only_df[existing_cols].sort_values("plan_value", ascending=False),
        use_container_width=True,
        height=350,
    )

    st.caption("Это плановые строки Monthly Passport, по которым факт пока не найден.")
else:
    st.success("План без факта не найден по выбранным фильтрам.")


# ---------------- Crew control ----------------

st.subheader("6. Контроль звеньев")

if not crew_control_f.empty:
    crew_cols = [
        "month_key",
        "facility_building",
        "construction_discipline",
        "crew_id",
        "planned_value",
        "actual_ev",
        "actual_qty",
        "value_variance",
        "crew_status",
    ]

    existing_cols = [c for c in crew_cols if c in crew_control_f.columns]

    st.dataframe(
        crew_control_f[existing_cols].sort_values("value_variance", ascending=False),
        use_container_width=True,
        height=350,
    )

    crew_summary = (
        crew_control_f.groupby("crew_status", dropna=False)
        .agg(
            rows_count=("crew_status", "count"),
            planned_value=("planned_value", "sum"),
            actual_ev=("actual_ev", "sum"),
            value_variance=("value_variance", "sum"),
        )
        .reset_index()
    )

    st.markdown("#### Статусы звеньев")
    st.dataframe(crew_summary, use_container_width=True)

else:
    st.warning("Нет данных по звеньям для выбранных фильтров.")


# ---------------- Management notes ----------------
# ---------------- Problem aggregation ----------------

st.subheader("7. ТОП проблем / Кто ломает план")

if not problem_aggregation_f.empty:
    problem_df = problem_aggregation_f.copy()

    problem_cols = [
        "month_key",
        "facility_building",
        "construction_discipline",
        "execution_status",
        "plan_crews",
        "fact_crews",
        "rows_count",
        "plan_value",
        "ev_value",
        "value_loss",
    ]

    existing_cols = [c for c in problem_cols if c in problem_df.columns]

    problem_view = problem_df[existing_cols].sort_values(
        "value_loss", ascending=False
    )

    st.dataframe(
        format_money_columns(problem_view),
        use_container_width=True,
        height=350,
    )

    problem_summary = (
        problem_df.groupby("execution_status", dropna=False)
        .agg(
            rows_count=("rows_count", "sum"),
            plan_value=("plan_value", "sum"),
            ev_value=("ev_value", "sum"),
            value_loss=("value_loss", "sum"),
        )
        .reset_index()
        .sort_values("value_loss", ascending=False)
    )

    st.markdown("#### Сводка проблем по статусам")
    st.dataframe(
        format_money_columns(problem_summary),
        use_container_width=True,
    )

    st.caption(
        "Этот блок показывает, где концентрируются потери: по звеньям, дисциплинам, зданиям и статусам исполнения."
    )
else:
    st.success("Проблемные зоны по выбранным фильтрам не найдены.")
st.subheader("7. Управленческая интерпретация")

st.markdown(
    """
**Как читать экран:**

- `MATCHED` — работа была в месячном плане и факт на неё лёг.
- `PLAN_ONLY` — работа была запланирована, но факта нет.
- `FACT_ONLY` — факт появился, но такой строки в месячном плане не было.
- `WRONG_CREW` — работа выполнена не тем звеном, которое было запланировано.
- `UNDERPERFORM` — работа начата, но плановая стоимость не закрыта.
- `NOT_STARTED` — строка плана есть, факт отсутствует.

**Главная задача начальника участка:**  
снизить `FACT_ONLY`, `PLAN_ONLY`, `WRONG_CREW` и увеличить долю `MATCHED`.
"""
)
