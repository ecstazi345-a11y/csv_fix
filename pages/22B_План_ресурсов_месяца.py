# ============================================================
# Page 22B — План ресурсов месяца (R1.3 Workbench)
# Resource commitment workplace for one project/month/crew
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import pandas as pd
import streamlit as st

from services.monthly_plan_labor_service import format_hours, format_money, load_labor_lines
from services.monthly_plan_resource_economic_service import normalize_labor_lines_df
from services.monthly_resource_plan_service import (
    BATCH_WRITE_AVAILABLE,
    DELETE_AVAILABLE,
    PLAN_UI_NOT_ADDED,
    ROSTER_MODE_CURRENT_MONTH,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_REJECTED,
    approve_resource_plan_line,
    build_crew_workload_lines,
    build_roster_prefill_payload,
    create_draft_resource_plan_from_selection,
    get_last_error,
    is_resource_line_editable,
    load_approved_capacity,
    load_resource_plan,
    preview_capacity_after_hours_delta,
    reject_resource_plan_line,
    resolve_assignment_plan_ui_status,
    resolve_crew_roster_from_labor_summary,
    resource_status_label_ru,
    summarize_crew_demand_from_labor_lines,
    summarize_crew_resource_commitment,
    summarize_proposed_vs_demand,
    summarize_selected_roster_preview,
    update_draft_resource_plan_line,
    upsert_resource_plan_line,
)
from utils.month_key import format_month_key_ru, normalize_month_key

st.set_page_config(layout="wide", page_title="План ресурсов месяца")


def _safe(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _options(values: list[str], *, with_all: bool = False) -> list[str]:
    cleaned = sorted({v for v in values if v and v.strip()})
    return (["Все"] + cleaned) if with_all else cleaned


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f} %".replace(".", ",")


def _fmt_gap(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{format_hours(value)}"


def _availability_period(row: pd.Series | dict[str, Any]) -> str:
    start = _safe(row.get("actual_mobilization_date"))
    end = (
        _safe(row.get("actual_demobilization_date"))
        or _safe(row.get("planned_demobilization_date"))
    )
    if start and end:
        return f"{start} — {end}"
    return start or end or "—"


def _roster_row_key(index: int, row: pd.Series) -> str:
    record_id = _safe(row.get("airtable_record_id"))
    if record_id:
        return record_id
    return f"{index}:{_safe(row.get('full_name_ru'))}:{_safe(row.get('role'))}"


st.title("План ресурсов месяца")
st.caption(
    "Ресурсное обязательство месяца: производственная нагрузка звена → "
    "предлагаемый состав → подтверждённые direct-hours в Resource Plan. "
    "Утверждённые часы — Source of Truth для «Ресурсной готовности». "
    "Предложение из кадрового плана ≠ capacity."
)

# ---------------------------------------------------------------------------
# Data loads (read-only)
# ---------------------------------------------------------------------------
plan_all = load_resource_plan()
labor_all = normalize_labor_lines_df(load_labor_lines())
load_err = get_last_error()
if load_err:
    st.warning(
        "Не удалось полностью загрузить ресурсный план. "
        f"Ошибка: {load_err}"
    )

# ---------------------------------------------------------------------------
# BLOCK 1 — Контекст месяца
# ---------------------------------------------------------------------------
st.markdown("### 1. Контекст месяца")

projects = _options(
    [_safe(v) for v in (plan_all["project_code"].tolist() if not plan_all.empty else [])]
    + [_safe(v) for v in (labor_all["project_code"].tolist() if not labor_all.empty else [])]
    + ["PRJ_001_БХК"],
    with_all=False,
)
month_map: dict[str, str] = {}
for raw in (
    (plan_all["month_key"].dropna().astype(str).tolist() if not plan_all.empty else [])
    + (labor_all["month_key"].dropna().astype(str).tolist() if not labor_all.empty else [])
    + ["2026-07", "2026-08"]
):
    canon = normalize_month_key(raw)
    if not canon:
        continue
    label = format_month_key_ru(canon) or canon
    month_map[label] = canon
month_labels = sorted(set(month_map.keys()))

crews = _options(
    [_safe(v) for v in (plan_all["crew_code"].tolist() if not plan_all.empty else [])]
    + [_safe(v) for v in (labor_all["crew_code"].tolist() if not labor_all.empty else [])]
    + ["АСИ-15", "АСИ-28"],
    with_all=False,
)

# Prefer control defaults when present
default_project = "PRJ_001_БХК" if "PRJ_001_БХК" in projects else (projects[0] if projects else "")
default_month_label = next(
    (lbl for lbl, canon in month_map.items() if canon == "2026-08"),
    next(
        (lbl for lbl, canon in month_map.items() if canon == "2026-07"),
        (month_labels[0] if month_labels else ""),
    ),
)
default_crew = "АСИ-28" if "АСИ-28" in crews else (
    "АСИ-15" if "АСИ-15" in crews else (crews[0] if crews else "")
)

f1, f2, f3 = st.columns(3)
with f1:
    project_sel = st.selectbox(
        "Проект",
        projects,
        index=projects.index(default_project) if default_project in projects else 0,
        key="mrp_wb_project",
    )
with f2:
    month_label = st.selectbox(
        "Месяц",
        month_labels,
        index=month_labels.index(default_month_label) if default_month_label in month_labels else 0,
        key="mrp_wb_month",
    )
with f3:
    crew_sel = st.selectbox(
        "Звено",
        crews,
        index=crews.index(default_crew) if default_crew in crews else 0,
        key="mrp_wb_crew",
    )

month_sel = month_map.get(month_label) or normalize_month_key(month_label)
scope_ready = bool(project_sel and month_sel and crew_sel)

if not scope_ready:
    st.info("Выберите проект, месяц и звено.")
    st.stop()

plan_df = load_resource_plan(
    project_code=project_sel,
    month_key=month_sel,
    crew_code=crew_sel,
)
cap = load_approved_capacity(
    project_code=project_sel,
    month_key=month_sel,
    crew_code=crew_sel,
)

approved_hours = float(cap["available_labor_hours"].sum()) if not cap.empty else 0.0
approved_people = int(cap["approved_people_count"].sum()) if not cap.empty else 0
has_approved_plan = (not cap.empty) and (
    approved_people > 0
    or int(cap["approved_assignment_count"].fillna(0).sum()) > 0
    or approved_hours > 0
)

demand = summarize_crew_demand_from_labor_lines(
    labor_all,
    project_code=project_sel,
    month_key=month_sel,
    crew_code=crew_sel,
)
required_hours = float(demand["required_hours"])
commitment = summarize_crew_resource_commitment(
    required_hours=required_hours,
    approved_available_hours=approved_hours,
    approved_people_count=approved_people,
    has_approved_plan=has_approved_plan,
)
roster = resolve_crew_roster_from_labor_summary(
    project_code=project_sel,
    month_key=month_sel,
    crew_code=crew_sel,
    fallback_last_known=True,
)
proposed_hours = float(roster["proposed_hours_total"])
proposed_diag = summarize_proposed_vs_demand(
    required_hours=required_hours,
    proposed_hours=proposed_hours,
)
workload_lines = build_crew_workload_lines(
    labor_all,
    project_code=project_sel,
    month_key=month_sel,
    crew_code=crew_sel,
)

st.markdown(
    f"**Scope:** `{project_sel}` · `{format_month_key_ru(month_sel) or month_sel}` · `{crew_sel}`"
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Требуемые трудозатраты", format_hours(required_hours) if demand["matched"] else "—")
k2.metric(
    "Подтверждённые часы",
    format_hours(approved_hours) if has_approved_plan else "нет",
)
gap_label = "Дефицит / резерв"
if commitment["hours_gap"] is None:
    k3.metric(gap_label, "—")
elif commitment["hours_gap"] >= 0:
    k3.metric("Резерв часов", _fmt_gap(commitment["hours_gap"]))
else:
    k3.metric("Дефицит часов", format_hours(abs(commitment["hours_gap"])))
k4.metric("Покрытие потребности", _fmt_pct(commitment["coverage_pct"]))
k5.metric("Подтверждённых людей", approved_people if has_approved_plan else "—")

extra1, extra2, extra3 = st.columns(3)
extra1.metric("BOQ-кодов звена", demand["boq_count"] if demand["matched"] else "—")
extra2.metric(
    "Стоимость планируемых работ",
    format_money(demand["plan_value"]) if demand["matched"] else "—",
)
extra3.metric("Статус ресурса", commitment["status_ru"])

if commitment["status_code"] == "MISSING":
    st.warning(commitment["status_ru"] + ". Добавьте людей и утвердите часы.")
elif commitment["status_code"] == "DEFICIT":
    st.error(commitment["status_ru"])
else:
    st.success(commitment["status_ru"])

if roster["mode"] == ROSTER_MODE_CURRENT_MONTH and proposed_hours > 0:
    st.markdown("##### Предложение vs подтверждение")
    prop1, prop2, prop3, prop4 = st.columns(4)
    prop1.metric(
        "Предлагается по кадровому плану",
        format_hours(proposed_hours),
        help="Direct hours из monthly_labor_summary за выбранный месяц. Не approved capacity.",
    )
    prop2.metric(
        "Подтверждено в Resource Plan",
        format_hours(approved_hours) if has_approved_plan else "нет",
    )
    if proposed_diag["hours_gap"] is not None and proposed_diag["hours_gap"] < 0:
        prop3.metric("Дефицит (proposal)", format_hours(abs(proposed_diag["hours_gap"])))
    elif proposed_diag["hours_gap"] is not None and proposed_diag["hours_gap"] >= 0:
        prop3.metric("Резерв (proposal)", _fmt_gap(proposed_diag["hours_gap"]))
    else:
        prop3.metric("Дефицит / резерв (proposal)", "—")
    prop4.metric("Покрытие (proposal)", _fmt_pct(proposed_diag["coverage_pct"]))

# ---------------------------------------------------------------------------
# BLOCK 2 — Производственная нагрузка звена
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 2. Производственная нагрузка звена")
st.caption(
    "BOQ scope и трудозатраты из monthly_plan_labor_lines_v1 для выбранного звена. "
    "Длительность/смены — тот же расчёт, что в Конструкторе месячного плана "
    "(required_hours ÷ (crew_size × 8 ч/смена)); сумма по BOQ не показывается — работы могут идти параллельно."
)

if workload_lines.empty:
    st.info("Для выбранного scope нет строк производственной нагрузки.")
else:
    wl_show = workload_lines.copy()
    st.dataframe(
        wl_show[
            [
                "boq_code",
                "boq_name",
                "planned_qty",
                "unit",
                "required_hours",
                "duration_display",
                "plan_value",
            ]
        ].rename(
            columns={
                "boq_code": "BOQ-код",
                "boq_name": "Наименование работы",
                "planned_qty": "Плановый объём",
                "unit": "Ед. изм.",
                "required_hours": "Требуемые трудозатраты, чел·ч",
                "duration_display": "Плановая длительность / смены",
                "plan_value": "Стоимость работ, ₽",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    w1, w2, w3 = st.columns(3)
    w1.metric("BOQ-кодов", demand["boq_count"])
    w2.metric("Требуемые трудозатраты", format_hours(demand["required_hours"]))
    w3.metric("Стоимость работ", format_money(demand["plan_value"]))

# ---------------------------------------------------------------------------
# BLOCK 3 — План ресурсов
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 3. План ресурсов")
st.caption(
    "Главный показатель capacity — подтверждённые direct-hours. "
    "Человек с периодом 01.07–15.07 не считается «целым месяцем» автоматически: "
    "часы задаёт утверждённое значение."
)

if plan_df.empty:
    st.info("В выбранном scope ещё нет строк ресурсного плана.")
else:
    show = plan_df.copy()
    show["Статус"] = show["resource_status"].map(resource_status_label_ru)
    st.dataframe(
        show[
            [
                "person_name",
                "role",
                "effective_from",
                "effective_to",
                "confirmed_available_hours",
                "Статус",
                "comment",
            ]
        ].rename(
            columns={
                "person_name": "ФИО",
                "role": "Профессия",
                "effective_from": "Дата начала",
                "effective_to": "Дата окончания",
                "confirmed_available_hours": "Подтверждённые чел·ч",
                "comment": "Комментарий",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Действия по строке")
    line_options = {
        f"{_safe(r.person_name)} · {resource_status_label_ru(r.resource_status)} · "
        f"{float(r.confirmed_available_hours or 0):.0f} ч · {r.resource_plan_line_id}": str(
            r.resource_plan_line_id
        )
        for r in plan_df.itertuples()
    }
    selected_label = st.selectbox(
        "Строка",
        list(line_options.keys()),
        key="mrp_wb_line",
    )
    selected_id = line_options[selected_label]
    selected_row = plan_df[
        plan_df["resource_plan_line_id"].astype(str) == selected_id
    ].iloc[0]
    selected_status = _safe(selected_row.get("resource_status"))

    a1, a2, a3 = st.columns(3)
    with a1:
        approved_by = st.text_input("Кто утверждает", value="planner", key="mrp_wb_approver")
        if st.button("Утвердить", type="primary", key="mrp_wb_approve"):
            if selected_status == STATUS_APPROVED:
                st.info("Строка уже утверждена.")
            else:
                result = approve_resource_plan_line(selected_id, approved_by=approved_by or "planner")
                if result["ok"]:
                    st.success("Строка утверждена — часы входят в capacity.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(result["error"])
    with a2:
        if st.button("Отклонить", key="mrp_wb_reject"):
            result = reject_resource_plan_line(selected_id)
            if result["ok"]:
                st.success("Строка отклонена — не входит в capacity.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(result["error"])
    with a3:
        st.caption("Удаление строк в R1.3 недоступно." if not DELETE_AVAILABLE else "")

    if is_resource_line_editable(selected_status):
        st.markdown("#### Редактировать черновик")
        with st.form("mrp_wb_edit_draft"):
            e1, e2 = st.columns(2)
            with e1:
                edit_person = st.text_input("ФИО", value=_safe(selected_row.get("person_name")))
                edit_role = st.text_input("Профессия", value=_safe(selected_row.get("role")))
                edit_from = st.text_input(
                    "Дата начала (YYYY-MM-DD)",
                    value=_safe(selected_row.get("effective_from")),
                )
            with e2:
                edit_to = st.text_input(
                    "Дата окончания (YYYY-MM-DD)",
                    value=_safe(selected_row.get("effective_to")),
                )
                edit_hours = st.number_input(
                    "Подтверждённые часы",
                    min_value=0.0,
                    value=float(selected_row.get("confirmed_available_hours") or 0.0),
                    step=8.0,
                )
                edit_comment = st.text_input(
                    "Комментарий",
                    value=_safe(selected_row.get("comment")),
                )
            if st.form_submit_button("Сохранить черновик"):
                result = update_draft_resource_plan_line(
                    selected_id,
                    person_name=edit_person,
                    role=edit_role,
                    effective_from=edit_from or None,
                    effective_to=edit_to or None,
                    confirmed_available_hours=edit_hours,
                    comment=edit_comment,
                    existing_row=selected_row.to_dict(),
                )
                if result["ok"]:
                    st.success("Черновик обновлён")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(result["error"])
    else:
        st.info(
            f"Статус «{resource_status_label_ru(selected_status)}» — только просмотр. "
            "Изменение утверждённой capacity — отдельный workflow."
        )

# ---------------------------------------------------------------------------
# BLOCK 4 — Добавить человека + preview
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 4. Добавить человека в ресурсный план")
st.caption(
    f"Исключительный сценарий: человек вне предложенного состава, "
    f"ручная корректировка, fallback-кандидат. "
    f"Scope: {project_sel} / {format_month_key_ru(month_sel) or month_sel} / {crew_sel}. "
    "Оценка состава месяца — в блоке 5 (выбор не пишет в БД). "
    "Новая строка из этой формы сохраняется как Черновик."
)

# Prefill from candidate / current-month proposal action
prefill = st.session_state.get("mrp_wb_prefill") or {}

preview_hours = st.number_input(
    "Подтверждённые часы (для preview и новой строки)",
    min_value=0.0,
    value=float(prefill.get("proposed_hours") or 0.0),
    step=8.0,
    key="mrp_wb_preview_hours",
    help=(
        "Для текущего месяца можно предзаполнить из кадрового плана; "
        "для fallback-кандидатов часы задаются вручную."
    ),
)
preview = preview_capacity_after_hours_delta(
    required_hours=required_hours,
    current_approved_hours=approved_hours,
    current_approved_people=approved_people,
    has_approved_plan=has_approved_plan,
    add_hours=float(preview_hours),
    add_new_person=True,
)
st.markdown("##### После утверждения (preview, без записи)")
p1, p2, p3, p4 = st.columns(4)
p1.metric("Сейчас подтверждено", format_hours(preview["current_approved_hours"]))
p2.metric("Добавляем", format_hours(preview["add_hours"]))
p3.metric("Будет", format_hours(preview["projected_approved_hours"]))
p4.metric("Покрытие", _fmt_pct(preview["coverage_pct"]))
st.caption(
    f"Потребность: {format_hours(required_hours)}. "
    f"Статус после утверждения: **{preview['status_ru']}**. "
    "Preview ничего не пишет в БД."
)

with st.form("mrp_wb_add_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        form_person = st.text_input("ФИО", value=_safe(prefill.get("person_name")))
        form_role = st.text_input("Профессия", value=_safe(prefill.get("role")))
        form_from = st.text_input("Дата начала (YYYY-MM-DD)", value=_safe(prefill.get("effective_from")))
        form_to = st.text_input("Дата окончания (YYYY-MM-DD)", value=_safe(prefill.get("effective_to")))
    with c2:
        form_hours = st.number_input(
            "Подтверждённые часы",
            min_value=0.0,
            value=float(
                prefill.get("proposed_hours")
                if prefill.get("proposed_hours") is not None
                else preview_hours
            ),
            step=8.0,
        )
        form_comment = st.text_input("Комментарий", value=_safe(prefill.get("comment")))
        st.text_input("Статус", value="Черновик", disabled=True)

    submitted = st.form_submit_button("Сохранить как черновик", type="primary")
    if submitted:
        result = upsert_resource_plan_line(
            {
                "project_code": project_sel,
                "month_key": month_sel,
                "crew_code": crew_sel,
                "person_name": form_person,
                "role": form_role,
                "effective_from": form_from or None,
                "effective_to": form_to or None,
                "confirmed_available_hours": form_hours,
                "resource_status": STATUS_DRAFT,
                "comment": form_comment,
                "source_airtable_record_id": prefill.get("source_airtable_record_id"),
            }
        )
        if result["ok"]:
            st.session_state.pop("mrp_wb_prefill", None)
            st.success("Черновик сохранён. Capacity не изменится, пока строка не утверждена.")
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(result["error"] or "Ошибка сохранения")

# ---------------------------------------------------------------------------
# BLOCK 5 — Предлагаемый состав / fallback кандидаты
# ---------------------------------------------------------------------------
st.markdown("---")
roster_mode = roster["mode"]
if roster_mode == ROSTER_MODE_CURRENT_MONTH:
    st.markdown("### 5. Предлагаемый состав месяца")
    st.caption(
        "Выберите одного, нескольких или весь состав, затем сформируйте черновики. "
        "Часы ниже — предлагаемые (кадровый план). DRAFT не является approved capacity."
    )
else:
    st.markdown("### 5. Кандидаты из последнего известного состава")
    st.caption(
        "За выбранный месяц строк в реестре нет — показан последний известный состав. "
        "ФИО/профессия для prefill; прошлые часы не входят в proposed capacity "
        "и не переносятся как даты нового месяца."
    )

candidates = roster["rows"]

if candidates.empty:
    st.info("Кандидаты для звена не найдены в monthly_labor_summary.")
elif roster_mode == ROSTER_MODE_CURRENT_MONTH:
    cand_reset = candidates.reset_index(drop=True)
    row_keys = [_roster_row_key(i, row) for i, row in cand_reset.iterrows()]
    plan_ui_status = [
        resolve_assignment_plan_ui_status(
            plan_df,
            row,
            project_code=project_sel,
            month_key=month_sel,
            crew_code=crew_sel,
        )
        for _, row in cand_reset.iterrows()
    ]
    selectable_keys = [
        key
        for key, status in zip(row_keys, plan_ui_status)
        if status["code"] == PLAN_UI_NOT_ADDED
    ]
    scope_token = f"{project_sel}|{month_sel}|{crew_sel}"
    if st.session_state.get("mrp_wb_sel_scope") != scope_token:
        st.session_state["mrp_wb_sel_scope"] = scope_token
        st.session_state["mrp_wb_sel_keys"] = []
        st.session_state["mrp_wb_sel_editor_rev"] = (
            int(st.session_state.get("mrp_wb_sel_editor_rev") or 0) + 1
        )

    sel_col, clear_col = st.columns(2)
    with sel_col:
        if st.button("Выбрать весь состав", key="mrp_wb_sel_all"):
            st.session_state["mrp_wb_sel_keys"] = list(selectable_keys)
            st.session_state["mrp_wb_sel_editor_rev"] = (
                int(st.session_state.get("mrp_wb_sel_editor_rev") or 0) + 1
            )
            st.rerun()
    with clear_col:
        if st.button("Снять выбор", key="mrp_wb_sel_none"):
            st.session_state["mrp_wb_sel_keys"] = []
            st.session_state["mrp_wb_sel_editor_rev"] = (
                int(st.session_state.get("mrp_wb_sel_editor_rev") or 0) + 1
            )
            st.rerun()

    selected_set = {
        key
        for key in (st.session_state.get("mrp_wb_sel_keys") or [])
        if key in selectable_keys
    }
    editor_src = pd.DataFrame(
        {
            "Выбрать": [key in selected_set for key in row_keys],
            "ФИО": [_safe(row.get("full_name_ru")) for _, row in cand_reset.iterrows()],
            "Профессия": [_safe(row.get("role")) for _, row in cand_reset.iterrows()],
            "Период": [_availability_period(row) for _, row in cand_reset.iterrows()],
            "Предлагаемые чел·ч": [
                float(row.get("direct_hours_month") or 0)
                for _, row in cand_reset.iterrows()
            ],
            "Статус исходного кадрового плана": [
                _safe(row.get("budget_status")) for _, row in cand_reset.iterrows()
            ],
            "В Resource Plan": [status["label_ru"] for status in plan_ui_status],
        }
    )
    edited = st.data_editor(
        editor_src,
        column_config={
            "Выбрать": st.column_config.CheckboxColumn("Выбрать", default=False),
            "Предлагаемые чел·ч": st.column_config.NumberColumn(format="%.1f"),
        },
        disabled=[
            "ФИО",
            "Профессия",
            "Период",
            "Предлагаемые чел·ч",
            "Статус исходного кадрового плана",
            "В Resource Plan",
        ],
        hide_index=True,
        use_container_width=True,
        key=f"mrp_wb_batch_editor_{int(st.session_state.get('mrp_wb_sel_editor_rev') or 0)}",
    )
    selected_flags = (
        edited["Выбрать"].fillna(False).astype(bool).tolist()
        if not edited.empty
        else []
    )
    selected_indices = [
        i
        for i, on in enumerate(selected_flags)
        if on and i < len(row_keys) and row_keys[i] in selectable_keys
    ]
    st.session_state["mrp_wb_sel_keys"] = [row_keys[i] for i in selected_indices]
    batch_preview = summarize_selected_roster_preview(
        cand_reset,
        selected_indices=selected_indices,
        required_hours=required_hours,
        roster_mode=roster_mode,
    )

    st.markdown("##### Предварительная обеспеченность выбранным составом")
    st.caption(
        "Только preview предлагаемых часов. Не approved capacity, "
        "не меняет «Подтверждённые часы» и Resource Status. Запись в БД не выполняется."
    )
    bp1, bp2, bp3, bp4, bp5 = st.columns(5)
    bp1.metric("Выбрано людей", batch_preview["selected_people"])
    bp2.metric("Предлагаемые часы", format_hours(batch_preview["selected_hours"]))
    bp3.metric(
        "Потребность звена",
        format_hours(required_hours) if demand["matched"] else "—",
    )
    gap = batch_preview["hours_gap"]
    if gap is None:
        bp4.metric("Дефицит / резерв", "—")
    elif gap < 0:
        bp4.metric("Дефицит", format_hours(abs(gap)))
    else:
        bp4.metric("Резерв", _fmt_gap(gap))
    bp5.metric("Покрытие потребности", _fmt_pct(batch_preview["coverage_pct"]))
    st.caption(
        "Preview выбранного состава не меняет «Подтверждённые часы» и Resource Status."
    )

    eligible_n = int(batch_preview["selected_people"])
    eligible_hours = float(batch_preview["selected_hours"])
    can_batch_draft = BATCH_WRITE_AVAILABLE and eligible_n > 0
    with st.form("mrp_wb_batch_draft_form"):
        st.caption(
            f"Будет создано {eligible_n} черновиков на {format_hours(eligible_hours)}. "
            "Это не утверждает ресурсный план."
        )
        batch_submitted = st.form_submit_button(
            "Сформировать черновик ресурсного плана",
            type="primary",
            disabled=not can_batch_draft,
        )
    if not BATCH_WRITE_AVAILABLE:
        st.caption("Массовое создание черновиков недоступно.")
    elif eligible_n == 0:
        st.info("Выберите хотя бы одного человека, который ещё не добавлен в Resource Plan.")
    if batch_submitted and can_batch_draft:
        batch_result = create_draft_resource_plan_from_selection(
            cand_reset,
            selected_indices=selected_indices,
            project_code=project_sel,
            month_key=month_sel,
            crew_code=crew_sel,
            roster_mode=roster_mode,
            existing_plan_df=plan_df,
        )
        st.session_state["mrp_wb_batch_draft_result"] = batch_result
        st.cache_data.clear()
        st.rerun()

    batch_result = st.session_state.pop("mrp_wb_batch_draft_result", None)
    if batch_result:
        created_n = int(batch_result.get("created_count") or 0)
        skipped_n = int(batch_result.get("skipped_count") or 0)
        error_n = int(batch_result.get("error_count") or 0)
        if created_n:
            st.success(
                f"Создано черновиков: {created_n} "
                f"({format_hours(batch_result.get('created_hours') or 0)}). "
                "Capacity не изменится, пока строки не утверждены."
            )
        if skipped_n:
            for item in batch_result.get("skipped") or []:
                st.warning(
                    f"{item.get('person_name') or '—'}: {item.get('message')}"
                )
        if error_n:
            for item in batch_result.get("errors") or []:
                who = item.get("person_name") or "выбор"
                st.error(f"{who}: {item.get('message')}")
        if created_n or skipped_n or error_n:
            st.caption(
                f"Итог: создано {created_n}, пропущено {skipped_n}, ошибки {error_n}."
            )

    with st.expander("Подставить одного человека в форму (исключение)"):
        cand_labels = {
            f"{_safe(row.get('full_name_ru'))} · {_safe(row.get('role'))} · "
            f"{float(row.get('direct_hours_month') or 0):.0f} ч": int(i)
            for i, row in cand_reset.iterrows()
        }
        pick = st.selectbox(
            "Запись",
            list(cand_labels.keys()),
            key="mrp_wb_cand_pick",
        )
        if st.button("Использовать предложение месяца", key="mrp_wb_use_cand"):
            row = cand_reset.iloc[cand_labels[pick]]
            prefill_payload = build_roster_prefill_payload(
                row, roster_mode=roster_mode
            )
            st.session_state["mrp_wb_prefill"] = prefill_payload
            if prefill_payload.get("proposed_hours") is not None:
                st.session_state["mrp_wb_preview_hours"] = float(
                    prefill_payload["proposed_hours"]
                )
            st.success(
                "Форма заполнена: ФИО, профессия, даты и предлагаемые часы. "
                "Сохраните как черновик вручную — capacity не изменится до утверждения."
            )
            st.rerun()
else:
    if roster.get("source_month"):
        st.info(
            "За выбранный месяц строк в реестре нет. "
            f"Показан последний известный состав: {roster['source_month']}."
        )

    show_c = candidates.copy()
    show_c["month_label"] = show_c["month_key"].map(
        lambda v: format_month_key_ru(normalize_month_key(v)) or _safe(v)
    )
    display_cols = [
        "full_name_ru",
        "role",
        "month_label",
        "direct_hours_month",
        "actual_mobilization_date",
        "actual_demobilization_date",
        "planned_demobilization_date",
        "budget_status",
    ]
    st.dataframe(
        show_c[display_cols].rename(
            columns={
                "full_name_ru": "ФИО",
                "role": "Профессия",
                "month_label": "Месяц реестра",
                "direct_hours_month": "Последние direct hours",
                "actual_mobilization_date": "Дата мобилизации",
                "actual_demobilization_date": "Дата демобилизации (факт)",
                "planned_demobilization_date": "Дата демобилизации (план)",
                "budget_status": "Статус кадрового плана",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    cand_reset = candidates.reset_index(drop=True)
    cand_labels = {
        f"{_safe(row.get('full_name_ru'))} · {_safe(row.get('role'))} · {_safe(row.get('month_key'))}": int(i)
        for i, row in cand_reset.iterrows()
    }
    pick = st.selectbox(
        "Запись",
        list(cand_labels.keys()),
        key="mrp_wb_cand_pick",
    )
    if st.button("Использовать как кандидата", key="mrp_wb_use_cand"):
        row = cand_reset.iloc[cand_labels[pick]]
        prefill_payload = build_roster_prefill_payload(row, roster_mode=roster_mode)
        st.session_state["mrp_wb_prefill"] = prefill_payload
        st.success(
            "Форма заполнена ФИО/профессией. "
            "Подтверждённые часы и даты нового месяца задайте вручную."
        )
        st.rerun()
