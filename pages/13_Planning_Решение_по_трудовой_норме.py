# -*- coding: utf-8 -*-
"""
LND-R1 — Решение по трудовой норме (durable human register).

Critical path: manual MANUAL_PROVISIONAL / REJECTED form (no auto network).
Optional: historical hints / ACTIVE / history — only on explicit button click.
"""

from __future__ import annotations

import streamlit as st

from services.labor_norm_decisions import (
    DECISION_APPROVED_PROVISIONAL,
    DECISION_MANUAL_PROVISIONAL,
    HINT_NOT_LOADED_RU,
    HINT_UNAVAILABLE_WARNING_RU,
    HINT_WARNING_RU,
    LaborNormDecisionDraft,
    decision_labels_for_hint_availability,
    decision_to_ru,
    get_active_decision,
    list_decisions,
    load_boq_norm_hints,
    normalize_decision_code,
    page13_remote_plan,
    save_decision,
    safe_text,
)

st.set_page_config(page_title="Решение по трудовой норме", layout="wide")

st.title("Решение по трудовой норме")
st.caption(
    "Человеческий реестр временных (provisional) норм. "
    "Исторический P50/P80 — только подсказка. Constructor в этом контуре не подключён."
)
st.caption(
    "ФИО/идентификатор утверждающего является операторской меткой. "
    "Криптографическая идентификация пользователя в R1 не реализована."
)
st.warning(HINT_WARNING_RU)


def _fmt_num(value) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(number - round(number)) < 1e-9:
        return str(int(round(number)))
    return f"{number:.4g}"


def _grain_key(
    project: str, facility: str, discipline: str, boq: str
) -> tuple[str, str, str, str]:
    return (project, facility, discipline, boq)


# --- Project + optional hint trigger (no auto fetch) ---
st.subheader("Проект и подсказка")
c1, c2 = st.columns([3, 2])
with c1:
    project_code = st.text_input("Проект", value="PRJ_001_БХК").strip()
with c2:
    load_hints_clicked = st.button(
        "Загрузить историческую подсказку", use_container_width=True
    )

if not project_code:
    st.info("Укажите код проекта.")
    st.stop()

# Drop stale hint cache when project changes.
if st.session_state.get("lnd_hints_project") not in (None, project_code):
    for key in (
        "lnd_hints_rows",
        "lnd_hints_error",
        "lnd_hints_project",
        "lnd_selected_hint_key",
    ):
        st.session_state.pop(key, None)

plan = page13_remote_plan(
    load_hints_clicked=load_hints_clicked,
    load_history_clicked=False,
    load_active_clicked=False,
)

if plan["fetch_hints"]:
    rows, err = load_boq_norm_hints(project_code=project_code, max_attempts=2)
    st.session_state["lnd_hints_project"] = project_code
    if err:
        st.session_state["lnd_hints_rows"] = ()
        st.session_state["lnd_hints_error"] = err
        st.warning(HINT_UNAVAILABLE_WARNING_RU)
        st.caption(f"Источник подсказки: {err}")
    else:
        st.session_state["lnd_hints_rows"] = tuple(rows)
        st.session_state["lnd_hints_error"] = ""
        st.success(f"Подсказка загружена: {len(rows)} строк.")

hint_rows = list(st.session_state.get("lnd_hints_rows") or ())
hint_error = safe_text(st.session_state.get("lnd_hints_error"))
hints_loaded_ok = bool(hint_rows) and not hint_error and (
    st.session_state.get("lnd_hints_project") == project_code
)

if not hints_loaded_ok:
    st.info(HINT_NOT_LOADED_RU)

# --- Always-available manual grain (critical path, no network) ---
st.subheader("Grain решения")
m_f, m_d = st.columns(2)
with m_f:
    facility_manual = st.text_input(
        "Титул / объект (facility_building)",
        value=safe_text(st.session_state.get("lnd_manual_facility")) or "16160-13",
    ).strip()
with m_d:
    discipline_manual = st.text_input(
        "Дисциплина (construction_discipline)",
        value=safe_text(st.session_state.get("lnd_manual_discipline")) or "Вентиляция",
    ).strip()
boq_manual = st.text_input(
    "BOQ",
    value=safe_text(st.session_state.get("lnd_manual_boq")),
).strip()
unit_manual = st.text_input(
    "Ед. измерения (unit_of_measure)",
    value=safe_text(st.session_state.get("lnd_manual_unit")),
    help="Обязательна. Тихая конвертация запрещена.",
).strip()
boq_name_manual = st.text_input(
    "Наименование BOQ (необязательно)",
    value=safe_text(st.session_state.get("lnd_manual_boq_name")),
).strip()
st.session_state["lnd_manual_facility"] = facility_manual
st.session_state["lnd_manual_discipline"] = discipline_manual
st.session_state["lnd_manual_boq"] = boq_manual
st.session_state["lnd_manual_unit"] = unit_manual
st.session_state["lnd_manual_boq_name"] = boq_name_manual

selected_hint: dict = {
    "project_code": project_code,
    "facility_building": facility_manual,
    "construction_discipline": discipline_manual,
    "boq_code": boq_manual,
    "boq_name": boq_name_manual,
    "unit_of_measure": unit_manual,
    "p50_hours_per_unit": None,
    "p80_hours_per_unit": None,
    "sample_count": None,
    "confidence": "",
}

# Optional: browse cached hints (local only after successful load)
if hints_loaded_ok:
    st.subheader("Очередь BOQ (кэш подсказки)")
    facilities = sorted(
        {
            safe_text(r.get("facility_building"))
            for r in hint_rows
            if safe_text(r.get("facility_building"))
        }
    )
    disciplines = sorted(
        {
            safe_text(r.get("construction_discipline"))
            for r in hint_rows
            if safe_text(r.get("construction_discipline"))
        }
    )
    f1, f2 = st.columns(2)
    with f1:
        facility_sel = st.selectbox("Фильтр титула", ["Все", *facilities])
    with f2:
        discipline_sel = st.selectbox("Фильтр дисциплины", ["Все", *disciplines])
    filtered = hint_rows
    if facility_sel != "Все":
        filtered = [r for r in filtered if r.get("facility_building") == facility_sel]
    if discipline_sel != "Все":
        filtered = [
            r for r in filtered if r.get("construction_discipline") == discipline_sel
        ]
    table_rows = [
        {
            "BOQ": row["boq_code"],
            "Наименование": row.get("boq_name") or "",
            "Ед.": row.get("unit_of_measure") or "",
            "P50 (подсказка)": _fmt_num(row.get("p50_hours_per_unit")),
            "P80 (подсказка)": _fmt_num(row.get("p80_hours_per_unit")),
            "Наблюдений": (
                row.get("sample_count") if row.get("sample_count") is not None else "—"
            ),
            "Стат. уверенность": row.get("confidence") or "—",
            "_facility": row["facility_building"],
            "_discipline": row["construction_discipline"],
            "_row": row,
        }
        for row in filtered
    ]
    if not table_rows:
        st.info("Нет строк для выбранных фильтров в кэше подсказки.")
    else:
        st.dataframe(
            [{k: v for k, v in row.items() if not k.startswith("_")} for row in table_rows],
            use_container_width=True,
            hide_index=True,
        )
        options = [
            f"{r['BOQ']} · {r['_facility']} · {r['_discipline']} · {r['Ед.']}"
            for r in table_rows
        ]
        use_from_hint = st.checkbox(
            "Подставить выбранный BOQ из подсказки в форму решения",
            value=False,
        )
        selected_label = st.selectbox("Выбранный BOQ из подсказки", options)
        picked = table_rows[options.index(selected_label)]
        if use_from_hint:
            selected_hint = dict(picked["_row"])
            st.session_state["lnd_manual_facility"] = selected_hint["facility_building"]
            st.session_state["lnd_manual_discipline"] = selected_hint[
                "construction_discipline"
            ]
            st.session_state["lnd_manual_boq"] = selected_hint["boq_code"]
            st.session_state["lnd_manual_unit"] = selected_hint["unit_of_measure"]
            st.session_state["lnd_manual_boq_name"] = selected_hint.get("boq_name") or ""

# Gate form completeness (local only)
if not (
    selected_hint.get("facility_building")
    and selected_hint.get("construction_discipline")
    and selected_hint.get("boq_code")
    and selected_hint.get("unit_of_measure")
):
    st.info("Укажите facility, дисциплину, BOQ и единицу измерения, чтобы принять решение.")
    st.stop()

hints_available_for_approved = hints_loaded_ok

st.divider()
st.subheader("Карточка решения")
if hints_available_for_approved:
    st.caption("Историческая подсказка загружена (HINT only).")
else:
    st.caption(HINT_NOT_LOADED_RU)

m1, m2, m3 = st.columns(3)
m1.markdown(f"**BOQ:** `{selected_hint['boq_code']}`")
m2.markdown(f"**Ед.:** `{selected_hint['unit_of_measure']}`")
m3.markdown(f"**Титул:** {selected_hint['facility_building']}")
st.markdown(f"**Наименование:** {selected_hint.get('boq_name') or '—'}")
st.markdown(
    f"**Дисциплина:** {selected_hint['construction_discipline']}  \n"
    f"**P50 (подсказка):** {_fmt_num(selected_hint.get('p50_hours_per_unit'))}  \n"
    f"**P80 (подсказка):** {_fmt_num(selected_hint.get('p80_hours_per_unit'))}  \n"
    f"**Наблюдений:** "
    f"{selected_hint.get('sample_count') if selected_hint.get('sample_count') is not None else '—'}  \n"
    f"**Статистическая уверенность:** {selected_hint.get('confidence') or '—'}  \n"
    f"**Авторитет подсказки:** "
    f"{'только HINT (не VALIDATED)' if hints_available_for_approved else 'не загружена — только ручное решение'}"
)

# Optional ACTIVE (fail-soft, explicit) — not on critical path
load_active_clicked = st.button("Проверить текущее ACTIVE")
if load_active_clicked:
    try:
        active_row = get_active_decision(
            project_code=selected_hint["project_code"],
            facility_building=selected_hint["facility_building"],
            construction_discipline=selected_hint["construction_discipline"],
            boq_code=selected_hint["boq_code"],
        )
        st.session_state["lnd_active_cache"] = (
            None if active_row is None else active_row.to_dict()
        )
        st.session_state["lnd_active_grain"] = _grain_key(
            selected_hint["project_code"],
            selected_hint["facility_building"],
            selected_hint["construction_discipline"],
            selected_hint["boq_code"],
        )
        st.session_state["lnd_active_error"] = ""
    except Exception as exc:  # noqa: BLE001
        st.warning(f"ACTIVE недоступен: {exc}")
        st.session_state["lnd_active_cache"] = None
        st.session_state["lnd_active_error"] = str(exc)
        st.session_state["lnd_active_grain"] = _grain_key(
            selected_hint["project_code"],
            selected_hint["facility_building"],
            selected_hint["construction_discipline"],
            selected_hint["boq_code"],
        )

this_grain = _grain_key(
    selected_hint["project_code"],
    selected_hint["facility_building"],
    selected_hint["construction_discipline"],
    selected_hint["boq_code"],
)
current_dict = None
if st.session_state.get("lnd_active_grain") == this_grain:
    if st.session_state.get("lnd_active_error"):
        st.caption(f"ACTIVE: {st.session_state['lnd_active_error']}")
    current_dict = st.session_state.get("lnd_active_cache")

if current_dict:
    st.info(
        f"Текущее ACTIVE: **{decision_to_ru(current_dict.get('decision'))}** · "
        f"норма={_fmt_num(current_dict.get('approved_norm'))} · "
        f"{current_dict.get('approved_by')} · {current_dict.get('approved_at')}"
    )

decision_labels = decision_labels_for_hint_availability(hints_available_for_approved)
decision_label = st.radio("Решение", decision_labels, horizontal=False)
decision_code = normalize_decision_code(decision_label)
if not decision_code:
    st.error("Недопустимый код решения.")
    st.stop()
if not hints_available_for_approved and decision_code == DECISION_APPROVED_PROVISIONAL:
    st.error(
        "Принять историческую подсказку нельзя: подсказка не загружена. "
        "Используйте ручную временную норму или отклонение."
    )
    st.stop()

default_norm = ""
if (
    decision_code == DECISION_APPROVED_PROVISIONAL
    and selected_hint.get("p50_hours_per_unit") is not None
):
    default_norm = str(selected_hint["p50_hours_per_unit"])
elif current_dict and current_dict.get("approved_norm") is not None:
    default_norm = str(current_dict["approved_norm"])


approved_norm_raw = None
if decision_code in {DECISION_APPROVED_PROVISIONAL, DECISION_MANUAL_PROVISIONAL}:
    approved_norm_raw = st.text_input(
        "Временная норма (чел·ч / ед.)",
        value=default_norm,
        help="Обязательна для APPROVED/MANUAL provisional. Только > 0.",
    )
else:
    st.caption("Для «Отклонить» поле approved_norm не заполняется.")

comment = st.text_area(
    "Комментарий (обязателен)",
    value="",
    help="Основание решения. Обязателен для всех кодов.",
)
approved_by = st.text_input(
    "Кто утверждает (approved_by)",
    value=safe_text(st.session_state.get("labor_norm_approved_by")),
    help=(
        "Операторская метка (ФИО/идентификатор). "
        "Криптографическая идентификация пользователя в R1 не реализована. "
        "Пустое значение — сохранение запрещено."
    ),
)
if approved_by:
    st.session_state["labor_norm_approved_by"] = approved_by

st.caption(
    "Сохранение отменит предыдущее ACTIVE-решение по этому grain "
    "(строка останется в истории как CANCELLED) и создаст новое ACTIVE."
)

if st.button("Сохранить решение", type="primary"):
    suggested = (
        selected_hint.get("p50_hours_per_unit") if hints_available_for_approved else None
    )
    draft = LaborNormDecisionDraft(
        project_code=selected_hint["project_code"],
        facility_building=selected_hint["facility_building"],
        construction_discipline=selected_hint["construction_discipline"],
        boq_code=selected_hint["boq_code"],
        unit_of_measure=selected_hint["unit_of_measure"],
        decision=decision_code,
        approved_by=approved_by,
        comment=comment,
        approved_norm=approved_norm_raw,
        boq_name=selected_hint.get("boq_name") or "",
        suggested_norm=suggested,
        suggested_source="HISTORICAL_P50_HINT" if suggested is not None else "",
        sample_count=(
            selected_hint.get("sample_count") if hints_available_for_approved else None
        ),
        confidence=(
            (selected_hint.get("confidence") or "") if hints_available_for_approved else ""
        ),
        source_reference="",
        expected_unit=selected_hint["unit_of_measure"],
    )
    result = save_decision(draft)
    if not result.get("ok"):
        st.error(result.get("error") or "Ошибка сохранения")
    else:
        data = result.get("data") or {}
        st.success(
            f"Сохранено: {data.get('status')} · decision_id={data.get('decision_id')}"
        )
        if data.get("cancelled_decision_id"):
            st.caption(f"Предыдущее ACTIVE отменено: {data.get('cancelled_decision_id')}")
        # Invalidate optional caches for this grain; do not auto-refetch.
        st.session_state.pop("lnd_active_cache", None)
        st.session_state.pop("lnd_history_cache", None)
        st.session_state.pop("lnd_history_grain", None)

st.divider()
st.subheader("История решений")
load_history_clicked = st.button("Показать историю решений")
history_plan = page13_remote_plan(
    load_hints_clicked=False,
    load_history_clicked=load_history_clicked,
)
if history_plan["fetch_history"]:
    try:
        history = list_decisions(
            project_code=selected_hint["project_code"],
            facility_building=selected_hint["facility_building"],
            construction_discipline=selected_hint["construction_discipline"],
            boq_code=selected_hint["boq_code"],
            include_cancelled=True,
            limit=50,
        )
        st.session_state["lnd_history_cache"] = [h.to_dict() for h in history]
        st.session_state["lnd_history_grain"] = this_grain
        st.session_state["lnd_history_error"] = ""
    except Exception as exc:  # noqa: BLE001
        st.warning(f"История недоступна: {exc}")
        st.session_state["lnd_history_cache"] = []
        st.session_state["lnd_history_error"] = str(exc)
        st.session_state["lnd_history_grain"] = this_grain

if st.session_state.get("lnd_history_grain") == this_grain:
    if st.session_state.get("lnd_history_error"):
        st.caption(f"История: {st.session_state['lnd_history_error']}")
    hist_dicts = st.session_state.get("lnd_history_cache") or []
    if hist_dicts:
        st.dataframe(
            [
                {
                    "status": h.get("decision_status"),
                    "decision": decision_to_ru(h.get("decision")),
                    "approved_norm": _fmt_num(h.get("approved_norm")),
                    "unit": h.get("unit_of_measure"),
                    "approved_by": h.get("approved_by"),
                    "approved_at": h.get("approved_at"),
                    "comment": h.get("comment"),
                    "suggested_norm": _fmt_num(h.get("suggested_norm")),
                    "decision_id": h.get("decision_id"),
                }
                for h in hist_dicts
            ],
            use_container_width=True,
            hide_index=True,
        )
    elif load_history_clicked or "lnd_history_cache" in st.session_state:
        if not st.session_state.get("lnd_history_error"):
            st.caption("Записей пока нет.")
else:
    st.caption("История не загружена — нажмите «Показать историю решений».")
