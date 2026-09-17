"""
ПНР — Фиксация факта (FIELD-1C).

Контролируемый ввод физического факта выполнения ПНР.
Каждое сохранение создаёт новую запись. История не редактируется.

Запуск поля (без меню app.py):
    streamlit run pages/60_ПНР_Фиксация_факта.py
"""

from __future__ import annotations

import sys
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Standalone `streamlit run pages/...` puts this file's directory on sys.path,
# not the repository root. Same bootstrap as form_app / archived standalone scripts.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from services.pnr_p1_engineering_context import (
    AIR_CONTOUR,
    AUTOMATION_FUNCTIONS,
    AUTOMATION_STANDBY,
    CLIMATE_FACTS,
    CLIMATE_HEADING,
    CONFLICT_P1_PARAMETERS,
    DESIGN_FACTS,
    DESIGN_MODE_HEADING,
    DOC_EXECUTION_NOT_FORMED,
    DOC_READINESS_NOT_CALCULATED,
    ELECTROMECHANICAL_CONTOUR,
    EngineeringFact,
    EXECUTION_EXPANDER_TITLE,
    EXTERNAL_DEPENDENCIES,
    FIRE_STOP_CHAIN,
    FLOW_NOT_ROUTING_CAPTION,
    GRAPH_NOT_REGISTRY_CAPTION,
    GRAPH_TITLE,
    HEADER_CONFIGURATION,
    HEADER_IDENTITY,
    HEADER_SERVES,
    IDENTIFICATION_FACTS,
    KV_PARAM_HEADER,
    KV_VALUE_HEADER,
    MISSING_CONTEXT,
    NAV_TITLE,
    PASSPORT_CONTEXT_HEADING,
    PASSPORT_NOT_OBJECT_CAPTION,
    PASSPORT_REQUIRES_P1_CONTEXT,
    PASSPORT_SUBTITLE,
    PASSPORT_TABS,
    PASSPORT_TITLE,
    PHYSICAL_GRAPH_LINES,
    PHYSICAL_MEDIUM,
    PURPOSE_FACTS,
    PURPOSE_PRODUCTION_CONTEXT,
    RELATED_NOT_CHILDREN,
    RELATED_VENTILATION,
    SECTION_TITLES,
    SELECTED_OBJECT_HEADING,
    SERVED_SPACES,
    SOURCE_DOCUMENT_FAMILIES,
    SOURCE_REGISTER,
    THERMAL_CONTOUR,
    format_provenance_caption,
    format_status_text,
    functional_flow_html,
    group_consecutive_by_provenance,
    is_p1_system_context,
    shared_provenance,
)
from services.pnr_left_execution_hierarchy import (
    CONTEXT_NOT_CONNECTED,
    CONTEXT_UNAVAILABLE,
    EMPTY_MODE,
    GENERAL_FIELD_ORDER,
    HIERARCHY_LABELS,
    INTERFACE_NOT_PHYSICAL,
    KEY_MOTOR_P11,
    KEY_SHSAU_P11,
    LIVE_SCOPES_MODE,
    NO_OPERATIONS,
    NO_REQUIRED_WORK,
    NO_WORK_SECTIONS,
    PROTOTYPE_MODE,
    PROTOTYPE_PHYSICAL_CAPTION,
    RW_SHSAU_P1_READY,
    SECTION_ACCEPTANCE,
    SECTION_DOC_READY,
    SECTION_EVIDENCE,
    SECTION_FACTUAL,
    SECTION_GENERAL,
    SECTION_INSPECTION,
    SECTION_OPERATION,
    SECTION_PHYSICAL,
    SECTION_REQUIRED_WORK,
    SECTION_SYSTEM,
    SECTION_WORK_SECTION,
    SECTION_WORK_STATUS,
    WORK_KIND_OPTIONS,
    WORK_KIND_PNR,
    WORK_KIND_SMR,
    WS_AUTO,
    apply_hierarchy_cascade,
    automation_subcontexts_for,
    evidence_category_labels,
    is_prototype_physical_identity,
    operations_for_required_work,
    permits_live_execution_identity,
    physical_choice_ids,
    physical_label,
    queue_display,
    required_work_lookup_key,
    required_works_for_hierarchy,
    reset_dependent_selections,
    slice_required_work,
    status_dimension_labels,
    title_name_display,
    work_section_resolution_mode,
    work_sections_for,
)
from services.pnr_p1_physical_master_catalog import (
    CHILD_KEYS_AFTER_P1_L1_CONTOUR,
    CHILD_KEYS_AFTER_P1_L1_SYSTEM,
    LEVEL1_NOT_INSTANCE_CAPTION,
    SESSION_TRACK_P1_L1_CONTOUR,
    SESSION_TRACK_P1_L1_SYSTEM,
    WIDGET_P1_L1_CLASS,
    WIDGET_P1_L1_CONTOUR,
    contour_label,
    contours as p1_level1_contours,
    object_class_label,
    object_classes_for,
)
from services.pnr_left_execution_hierarchy import (
    CHILD_KEYS_AFTER_AUTO_SUB,
    CHILD_KEYS_AFTER_PHYSICAL,
    CHILD_KEYS_AFTER_REQUIRED_WORK,
    CHILD_KEYS_AFTER_WORK_SECTION,
    SESSION_TRACK_AUTO_SUB,
    SESSION_TRACK_PHYSICAL,
    SESSION_TRACK_REQUIRED_WORK,
    SESSION_TRACK_WORK_SECTION,
)
from services.pnr_p1_slice_prototype import (
    CANDIDATE_STEP_CAPTION,
    CRITERION_UNSET,
    EVIDENCE_NOT_CONNECTED,
    KEY_FAN,
    KEY_MOTOR,
    PROVEN_STATE_NOT_CALCULATED,
    REQUIREMENT_NEEDS_CONFIRMATION,
    RW_01_CANDIDATE_CHECKS,
    SAVE_DISABLED_REASON,
    STEP_UNDEFINED,
    allows_execution_event_write,
    measurement_capture_enabled,
    observation_capture_enabled,
)
from services.pnr_service import (
    PnrConfigError,
    PnrServiceError,
    PnrValidationError,
    WORK_TYPE_CODE_PNR,
    create_structured_execution_event,
    get_work_type_by_code,
    list_active_objects,
    list_active_operations_for_work_scope,
    list_active_projects,
    list_active_titles,
    list_active_work_scopes,
    list_context_disciplines,
    list_system_work_contexts,
    resolve_object_functional_position_id,
)

PNR_SITE_TZ = ZoneInfo("Europe/Moscow")
PREFERRED_PROJECT_CODE = "PRJ_001_SLM"
PREFERRED_TITLE_CODE = "УКПГ2-011"

MODE_CATALOG = "Работа из справочника"
MODE_UNMAPPED = "Работы нет в списке"

DONE_COMPLETED = "Выполнена"
DONE_PARTIAL = "Выполнена частично"
DONE_BLOCKED = "Невозможно выполнить — есть препятствие"
DONE_NOT_COMPLETED = "Не выполнялась"
DONE_OPTIONS = [DONE_COMPLETED, DONE_PARTIAL, DONE_BLOCKED, DONE_NOT_COMPLETED]
DONE_BLOCKED_HELP = (
    "Если работу невозможно выполнить из-за отсутствия готовности, "
    "доступа, материалов, документации или другого препятствия — "
    "выберите «Невозможно выполнить — есть препятствие»."
)

# П-1 Field Pilot presentation boundary only.
# Not a system↔scope architecture. Legacy catalog rows stay in the database.
P1_PILOT_WORK_SCOPE_CODES = (
    "PNR-WS-01-PRESTART",
    "PNR-WS-02-VENT-DRIVE",
    "PNR-WS-03-AUTOMATION",
    "PNR-WS-04-PROTECTION",
    "PNR-WS-05-PTI",
    "PNR-WS-06-AIR-PATH",
    "PNR-WS-07-AERO",
    "PNR-WS-08-COMPLEX-P1",
)

EVAL_CONFORMS = "Соответствует"
EVAL_DOES_NOT_CONFORM = "Не соответствует"
EVAL_NOT_EVALUATED = "Пока не оценивалось"
EVAL_OPTIONS = [EVAL_CONFORMS, EVAL_DOES_NOT_CONFORM, EVAL_NOT_EVALUATED]

OTHER_WORK_YES = "Да"
OTHER_WORK_NO = "Нет"
OTHER_WORK_UNKNOWN = "Не могу определить"
OTHER_WORK_OPTIONS = [OTHER_WORK_YES, OTHER_WORK_NO, OTHER_WORK_UNKNOWN]

BLOCKED_CATEGORY_OTHER_LABEL = "Другое"
BLOCKED_CATEGORY_LABEL_TO_CODE = {
    "Проектная/рабочая документация": "DOCUMENTATION",
    "Строительная готовность": "CONSTRUCTION_READINESS",
    "Смежные работы": "ADJACENT_WORK",
    "Материалы": "MATERIALS",
    "Оборудование": "EQUIPMENT",
    "Электропитание": "POWER_SUPPLY",
    "Теплоноситель / рабочая среда": "WORKING_MEDIUM",
    "Доступ к объекту": "OBJECT_ACCESS",
    "Допуск и безопасность": "PERMIT_SAFETY",
    "Персонал": "PERSONNEL",
    "Инструмент / измерительный прибор": "INSTRUMENT",
    "Автоматизация / ПО / настройки": "AUTOMATION_SOFTWARE",
    "Решение другой стороны": "THIRD_PARTY_DECISION",
    "Погодные / внешние условия": "WEATHER_EXTERNAL",
    BLOCKED_CATEGORY_OTHER_LABEL: "OTHER",
}
BLOCKED_CATEGORY_LABELS = list(BLOCKED_CATEGORY_LABEL_TO_CODE.keys())


def format_project_label(row: dict) -> str:
    return str(row.get("project_name") or row.get("project_code") or "")


def format_title_label(row: dict) -> str:
    return str(row.get("title_name") or row.get("title_code") or "")


def format_discipline_label(row: dict) -> str:
    return str(row.get("discipline_name") or "")


def format_system_context_label(row: dict) -> str:
    return str(row.get("context_system_code") or "")


def format_object_label(row: dict) -> str:
    return str(row.get("object_name") or row.get("object_code") or "")


def format_scope_label(row: dict) -> str:
    return str(row.get("scope_name") or "")


def format_operation_label(row: dict) -> str:
    return str(row.get("operation_name") or "")


def professional_p1_pilot_work_scopes(scopes: list[dict]) -> list[dict]:
    """Show only the eight Professional П-1 Foundation scopes for this pilot.

    Does not deactivate AUT_ALGORITHMS or other legacy catalog rows.
    """
    allowed = set(P1_PILOT_WORK_SCOPE_CODES)
    selected = [
        row
        for row in scopes
        if str(row.get("scope_code") or "") in allowed
    ]

    def sort_key(row: dict) -> tuple:
        raw_seq = row.get("sequence_no")
        try:
            seq_num = int(raw_seq)
            sequenced = 0
        except (TypeError, ValueError):
            sequenced = 1
            seq_num = 0
        return (
            sequenced,
            seq_num,
            str(row.get("scope_name") or ""),
            str(row.get("work_scope_id") or ""),
        )

    return sorted(selected, key=sort_key)


def compute_labor_preview(people_count: int, duration_hours: float | int | Decimal) -> Decimal:
    return Decimal(int(people_count)) * Decimal(str(duration_hours))


def preferred_index(ids: list[str], row_map: dict[str, dict], field: str, preferred: str) -> int:
    for index, row_id in enumerate(ids):
        if row_map[row_id].get(field) == preferred:
            return index
    return 0


def map_execution_evaluation(
    done_label: str, evaluation_label: str | None
) -> tuple[str, str]:
    if done_label == DONE_COMPLETED:
        evaluation_map = {
            EVAL_CONFORMS: "CONFORMS",
            EVAL_DOES_NOT_CONFORM: "DOES_NOT_CONFORM",
            EVAL_NOT_EVALUATED: "NOT_EVALUATED",
        }
        if evaluation_label not in evaluation_map:
            raise ValueError("Не выбрана оценка соответствия.")
        return "COMPLETED", evaluation_map[evaluation_label]
    if done_label == DONE_PARTIAL:
        return "PARTIAL", "NOT_EVALUATED"
    if done_label == DONE_BLOCKED:
        return "BLOCKED", "NOT_EVALUATED"
    if done_label == DONE_NOT_COMPLETED:
        return "NOT_COMPLETED", "NOT_EVALUATED"
    raise ValueError("Не выбран фактический результат.")


def map_other_work_available(label: str) -> bool | None:
    if label == OTHER_WORK_YES:
        return True
    if label == OTHER_WORK_NO:
        return False
    if label == OTHER_WORK_UNKNOWN:
        return None
    raise ValueError("Не выбран ответ про другие работы.")


def map_blocked_category(label: str) -> str:
    code = BLOCKED_CATEGORY_LABEL_TO_CODE.get(label)
    if not code:
        raise ValueError("Не выбрана категория препятствия.")
    return code


def build_partial_detail(completed_text: str, remaining_text: str) -> dict[str, str]:
    completed = (completed_text or "").strip()
    remaining = (remaining_text or "").strip()
    if not completed:
        raise ValueError("Укажите, что выполнено.")
    if not remaining:
        raise ValueError("Укажите, что осталось выполнить.")
    return {"completed_text": completed, "remaining_text": remaining}


def build_blocked_detail(
    category_label: str,
    description: str,
    other_work_label: str,
) -> dict[str, Any]:
    category = map_blocked_category(category_label)
    text = (description or "").strip()
    if category == "OTHER" and not text:
        raise ValueError("Для категории «Другое» укажите, что конкретно препятствует работе.")
    return {
        "constraint_category": category,
        "constraint_description": text or None,
        "other_work_available": map_other_work_available(other_work_label),
    }


def measurements_from_rows(
    rows: list[dict[str, Any]],
    recorded_at: datetime,
) -> list[dict[str, Any]]:
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("Время измерения должно содержать часовой пояс.")
    prepared: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        name = str(row.get("parameter_name") or "").strip()
        unit = str(row.get("unit") or "").strip()
        point = str(row.get("measurement_point") or "").strip()
        instrument = str(row.get("instrument_text") or "").strip()
        raw_value = row.get("value")
        empty_identity = not name and not unit and not point and not instrument
        if empty_identity:
            continue
        if not name or not unit or raw_value is None or raw_value == "":
            raise ValueError(
                f"Измерение {index}: укажите параметр, значение и единицу измерения."
            )
        prepared.append(
            {
                "parameter_name": name,
                "measurement_point": point or None,
                "value": Decimal(str(raw_value)),
                "unit": unit,
                "instrument_text": instrument or None,
                "recorded_at": recorded_at,
            }
        )
    return prepared


def require_selected_work_scope(work_scope_id: Any) -> str:
    text = str(work_scope_id or "").strip()
    if not text:
        raise ValueError("Выберите раздел работ.")
    return text


def submit_fingerprint(kwargs: dict[str, Any]) -> tuple:
    measurements = kwargs.get("measurements") or []
    return (
        kwargs.get("system_id"),
        kwargs.get("object_id"),
        kwargs.get("work_scope_id"),
        kwargs.get("functional_position_id"),
        kwargs.get("operation_id"),
        kwargs.get("unmapped_operation_name"),
        kwargs.get("execution_status"),
        kwargs.get("evaluation_status"),
        kwargs.get("observation_text"),
        str(kwargs.get("partial_detail")),
        str(kwargs.get("blocked_detail")),
        tuple(
            (
                item.get("parameter_name"),
                str(item.get("value")),
                item.get("unit"),
            )
            for item in measurements
        ),
        kwargs["occurred_at"].isoformat(),
        kwargs.get("people_count"),
        str(kwargs.get("duration_hours")),
    )


def build_structured_kwargs(
    *,
    system_id: str,
    object_id: str,
    work_scope_id: str,
    functional_position_id: str | None,
    operation_mode: str,
    operation_id: str | None,
    unmapped_operation_name: str | None,
    execution_status: str,
    evaluation_status: str,
    occurred_at: datetime,
    people_count: int,
    duration_hours: Decimal,
    observation_text: str | None,
    measurements: list[dict[str, Any]] | None,
    blocked_detail: dict[str, Any] | None,
    partial_detail: dict[str, Any] | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "system_id": system_id,
        "object_id": object_id,
        "work_scope_id": work_scope_id,
        "functional_position_id": functional_position_id,
        "execution_status": execution_status,
        "evaluation_status": evaluation_status,
        "occurred_at": occurred_at,
        "people_count": people_count,
        "duration_hours": duration_hours,
        "observation_text": (observation_text or "").strip() or None,
        "measurements": measurements or [],
        "blocked_detail": blocked_detail,
        "partial_detail": partial_detail,
        "source": "STREAMLIT",
    }
    if operation_mode == MODE_UNMAPPED:
        kwargs["operation_id"] = None
        kwargs["unmapped_operation_name"] = (unmapped_operation_name or "").strip() or None
    else:
        kwargs["operation_id"] = operation_id
        kwargs["unmapped_operation_name"] = None
    return kwargs


def build_review_lines(
    *,
    project_name: str,
    title_name: str,
    discipline_name: str,
    system_label: str,
    object_label: str,
    scope_label: str | None,
    work_label: str,
    done_label: str,
    evaluation_label: str | None,
    observation_text: str | None,
    partial_detail: dict[str, Any] | None,
    blocked_detail_label: str | None,
    blocked_description: str | None,
    other_work_label: str | None,
    measurements: list[dict[str, Any]],
    people_count: int,
    duration_hours: Decimal,
    labor_preview: Decimal,
) -> list[str]:
    lines = [
        f"Проект: {project_name}",
        f"Титул: {title_name}",
        "Вид работ: ПНР",
        f"Дисциплина: {discipline_name}",
        f"Система: {system_label}",
        f"Физический объект: {object_label}",
        f"Раздел работ: {scope_label or '—'}",
        f"Работа: {work_label}",
        f"Что произошло: {done_label}",
    ]
    if evaluation_label:
        lines.append(f"Оценка: {evaluation_label}")
    if observation_text:
        lines.append(f"Наблюдение: {observation_text}")
    if partial_detail:
        lines.append(f"Что выполнено: {partial_detail.get('completed_text')}")
        lines.append(f"Что осталось: {partial_detail.get('remaining_text')}")
    if blocked_detail_label:
        lines.append(f"Препятствие: {blocked_detail_label}")
        if blocked_description:
            lines.append(f"Что конкретно препятствует: {blocked_description}")
        if other_work_label:
            lines.append(f"Можно выполнять другие работы: {other_work_label}")
    if measurements:
        compact = ", ".join(
            f"{item['parameter_name']} {item['value']} {item['unit']}"
            for item in measurements
        )
        lines.append(f"Измерения ({len(measurements)}): {compact}")
    else:
        lines.append("Измерения: нет")
    lines.append(f"Количество специалистов: {people_count}")
    lines.append(f"Продолжительность: {duration_hours} ч")
    lines.append(f"Трудозатраты: {labor_preview} чел·ч")
    return lines


def _safe_user_error(exc: BaseException) -> str:
    if isinstance(exc, (PnrConfigError, PnrValidationError, PnrServiceError)):
        return str(exc)
    return "Не удалось сохранить факт ПНР. Повторите попытку."


def _index_by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {str(row[key]): row for row in rows if row.get(key)}


def _load_or_stop(loader, empty_warning: str, fail_message: str):
    try:
        rows = loader()
    except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
        st.error(_safe_user_error(exc))
        st.stop()
    except Exception:
        st.error(fail_message)
        st.stop()
    if not rows:
        st.warning(empty_warning)
        st.stop()
    return rows


def structured_write_permitted(physical_selection: str | None) -> bool:
    return allows_execution_event_write(physical_selection)


def load_functional_position_id(object_id: str | None) -> tuple[str | None, bool]:
    """Read FP map for display. Failure is unresolved, never fabricated.

    Returns (position_id, unresolved). unresolved=True means write must stay
    fail-closed. Empty mapping is a successful None, not unresolved.
    """
    if not object_id:
        return None, False
    try:
        return resolve_object_functional_position_id(object_id=object_id), False
    except (PnrConfigError, PnrServiceError, PnrValidationError):
        return None, True
    except Exception:  # noqa: BLE001
        return None, True


def _find_operation_by_code(operations: list[dict], operation_code: str) -> dict | None:
    for row in operations:
        if str(row.get("operation_code") or "") == operation_code:
            return row
    return None


def _html_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_provenance_caption(facts: list[EngineeringFact] | tuple[EngineeringFact, ...]) -> None:
    shared = shared_provenance(list(facts))
    if shared is None:
        for fact in facts:
            st.caption(format_provenance_caption(fact))
        return
    st.caption(format_provenance_caption(shared))


def _render_kv_groups(rows: tuple[tuple[str, EngineeringFact], ...]) -> None:
    for group, shared in group_consecutive_by_provenance(rows):
        cells = "".join(
            "<tr>"
            f"<td style='padding:0.2rem 0.75rem 0.2rem 0;vertical-align:top'>"
            f"{_html_escape(label)}</td>"
            f"<td style='padding:0.2rem 0;vertical-align:top'>"
            f"{_html_escape(fact.value)}</td>"
            "</tr>"
            for label, fact in group
        )
        st.markdown(
            "<table style='border-collapse:collapse;width:100%;font-size:0.92rem'>"
            "<thead><tr>"
            f"<th style='text-align:left;padding:0.2rem 0.75rem 0.35rem 0'>"
            f"{_html_escape(KV_PARAM_HEADER)}</th>"
            f"<th style='text-align:left;padding:0.2rem 0 0.35rem 0'>"
            f"{_html_escape(KV_VALUE_HEADER)}</th>"
            "</tr></thead><tbody>"
            f"{cells}</tbody></table>",
            unsafe_allow_html=True,
        )
        if shared is not None:
            st.caption(format_provenance_caption(shared))
        else:
            _render_provenance_caption([fact for _label, fact in group])


def _render_bullet_list(items: tuple[str, ...] | list[str]) -> None:
    if not items:
        return
    st.markdown("\n".join(f"- {item}" for item in items))


def _render_flow(steps: tuple[str, ...]) -> None:
    st.markdown(" → ".join(steps))


def _render_passport_header() -> None:
    st.markdown(f"## {PASSPORT_TITLE}")
    st.caption(PASSPORT_SUBTITLE)
    for line in HEADER_IDENTITY:
        st.markdown(line)
    st.markdown("**Обслуживает:** " + "; ".join(HEADER_SERVES))
    st.markdown(f"**Конфигурация:** {HEADER_CONFIGURATION}")


def _served_space_fact(space: dict, key: str) -> EngineeringFact | None:
    value = space.get(key)
    return value if isinstance(value, EngineeringFact) else None


def _render_served_space(space: dict) -> None:
    st.markdown(f"**{space['name']}**")
    relation = _served_space_fact(space, "relation")
    supply = _served_space_fact(space, "supply")
    temperature = _served_space_fact(space, "internal_temperature")
    if relation:
        st.markdown(relation.value)
    if supply:
        st.markdown(f"Подача: {supply.value}")
    if temperature:
        st.markdown(f"Расчётная внутренняя температура: {temperature.value}")
    facts = [item for item in (relation, supply, temperature) if item is not None]
    _render_provenance_caption(facts)


def _render_passport_overview() -> None:
    st.markdown(f"### {SECTION_TITLES['01']}")
    _render_kv_groups(IDENTIFICATION_FACTS)
    st.markdown(f"### {SECTION_TITLES['02']}")
    _render_bullet_list([fact.value for fact in PURPOSE_FACTS])
    _render_provenance_caption(PURPOSE_FACTS)
    st.markdown("**Производственный контекст**")
    _render_bullet_list(list(PURPOSE_PRODUCTION_CONTEXT))
    st.markdown(f"### {SECTION_TITLES['03']}")
    left_space, right_space = st.columns(2)
    with left_space:
        _render_served_space(SERVED_SPACES[0])
    with right_space:
        _render_served_space(SERVED_SPACES[1])
    st.markdown(f"### {SECTION_TITLES['04']}")
    st.markdown(f"**Физическая среда:** {PHYSICAL_MEDIUM.value}")
    _render_provenance_caption([PHYSICAL_MEDIUM])
    st.markdown(functional_flow_html(), unsafe_allow_html=True)
    st.caption(FLOW_NOT_ROUTING_CAPTION)
    st.markdown(f"### {SECTION_TITLES['05']}")
    st.markdown(f"**{DESIGN_MODE_HEADING}**")
    _render_kv_groups(DESIGN_FACTS)
    st.markdown(f"**{CLIMATE_HEADING}**")
    _render_kv_groups(CLIMATE_FACTS)


def _render_passport_physical() -> None:
    st.markdown(f"### {GRAPH_TITLE}")
    st.caption(GRAPH_NOT_REGISTRY_CAPTION)
    st.code("\n".join(PHYSICAL_GRAPH_LINES))
    st.markdown(f"### {SECTION_TITLES['07']}")
    st.markdown("**Воздушный поток**")
    _render_flow(AIR_CONTOUR)
    st.markdown("**Тепловой поток**")
    _render_flow(THERMAL_CONTOUR)
    st.markdown("**Электромеханический поток**")
    _render_flow(ELECTROMECHANICAL_CONTOUR)


def _render_passport_logic() -> None:
    st.markdown(f"### {SECTION_TITLES['08']}")
    _render_bullet_list(list(AUTOMATION_STANDBY) + list(AUTOMATION_FUNCTIONS))
    st.markdown("**Останов по пожарной автоматике**")
    _render_flow(FIRE_STOP_CHAIN)
    st.markdown(f"### {SECTION_TITLES['09']}")
    _render_bullet_list(list(EXTERNAL_DEPENDENCIES))
    st.markdown("**Связанные вентиляционные системы помещения компрессоров**")
    st.caption(RELATED_NOT_CHILDREN)
    _render_bullet_list(
        [f"**{code}:** {meaning}" for code, meaning in RELATED_VENTILATION]
    )


def _render_passport_sources() -> None:
    st.markdown(f"### {SECTION_TITLES['10']}")
    for record in SOURCE_REGISTER:
        bits = [record.family, record.code]
        if record.revision:
            bits.append(record.revision)
        if record.dated:
            bits.append(record.dated)
        st.markdown("**" + " · ".join(bits) + "**")
        st.caption(record.description)
        st.caption(
            format_status_text(record.authority_status, record.verification_status)
        )
    st.markdown(f"### {SECTION_TITLES['12']}")
    st.markdown("**Исходные документы:** " + ", ".join(SOURCE_DOCUMENT_FAMILIES))
    st.markdown(f"**Исполнительная документация:** {DOC_EXECUTION_NOT_FORMED}")
    st.markdown(f"**Документальная готовность:** {DOC_READINESS_NOT_CALCULATED}")


def _render_passport_conflicts() -> None:
    st.markdown(f"### {SECTION_TITLES['11']}")
    conflict = CONFLICT_P1_PARAMETERS
    st.markdown(f"**{conflict.code}: {conflict.title}**")
    st.markdown(f"{conflict.left_source}: " + "; ".join(conflict.left_values))
    st.markdown(f"{conflict.right_source}: " + "; ".join(conflict.right_values))
    st.warning(conflict.status)
    st.markdown("**Отсутствующий контекст**")
    _render_bullet_list(list(MISSING_CONTEXT))


def _render_p1_passport() -> None:
    _render_passport_header()
    overview, physical, logic, sources, conflicts = st.tabs(list(PASSPORT_TABS))
    with overview:
        _render_passport_overview()
    with physical:
        _render_passport_physical()
    with logic:
        _render_passport_logic()
    with sources:
        _render_passport_sources()
    with conflicts:
        _render_passport_conflicts()


st.set_page_config(
    page_title="ПНР — Фиксация факта",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("ПНР — Фиксация факта")
st.caption("Фиксация физического факта выполнения. Каждое сохранение — новая запись.")

left_col, right_col = st.columns([3, 7], gap="large")

with left_col:
    st.markdown(f"### {NAV_TITLE}")
    st.markdown(f"### {SECTION_GENERAL}")
    _ = GENERAL_FIELD_ORDER
    _ = HIERARCHY_LABELS

    projects = _load_or_stop(
        list_active_projects,
        "Нет активных проектов. Обратитесь к администратору.",
        "Не удалось загрузить список проектов.",
    )
    project_map = _index_by_id(projects, "project_id")
    project_ids = list(project_map.keys())
    project_id = st.selectbox(
        "Проект",
        project_ids,
        index=preferred_index(project_ids, project_map, "project_code", PREFERRED_PROJECT_CODE),
        format_func=lambda pid: format_project_label(project_map[pid]),
        key="pnr_project_id",
    )
    project_row = project_map[str(project_id)]

    st.markdown("**Очередь**")
    st.caption(queue_display())

    work_kind = st.selectbox(
        "Вид работ",
        list(WORK_KIND_OPTIONS),
        index=0,
        key="pnr_work_kind",
    )
    st.markdown("**Вид работ: ПНР**")
    if work_kind == WORK_KIND_SMR:
        st.info(
            "Исполнение СМР в этом контуре не подключено. "
            "Фиксация факта доступна только для ПНР."
        )

    titles = _load_or_stop(
        lambda: list_active_titles(project_id=project_id),
        "Для выбранного проекта нет активных титулов.",
        "Не удалось загрузить список титулов.",
    )
    title_map = _index_by_id(titles, "title_id")
    title_ids = list(title_map.keys())
    title_id = st.selectbox(
        "Титул",
        title_ids,
        index=preferred_index(title_ids, title_map, "title_code", PREFERRED_TITLE_CODE),
        format_func=lambda tid: format_title_label(title_map[tid]),
        key="pnr_title_id",
    )
    title_row = title_map[str(title_id)]
    st.markdown("**Наименование титула**")
    st.caption(title_name_display(title_row))

    try:
        pnr_work_type = get_work_type_by_code(work_type_code=WORK_TYPE_CODE_PNR)
    except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
        st.error(_safe_user_error(exc))
        st.stop()
    except Exception:
        st.error("Не удалось определить вид работ ПНР.")
        st.stop()

    if not pnr_work_type:
        st.error("Не найден активный вид работ ПНР.")
        st.stop()

    work_type_id = pnr_work_type["work_type_id"]

    disciplines = _load_or_stop(
        lambda: list_context_disciplines(title_id=title_id, work_type_id=work_type_id),
        "Для выбранного титула нет дисциплин в контексте ПНР.",
        "Не удалось загрузить список дисциплин.",
    )
    discipline_map = _index_by_id(disciplines, "discipline_id")
    discipline_ids = list(discipline_map.keys())
    discipline_id = st.selectbox(
        "Дисциплина",
        discipline_ids,
        format_func=lambda did: format_discipline_label(discipline_map[did]),
        key="pnr_discipline_id",
    )
    discipline_row = discipline_map[str(discipline_id)]

    try:
        contexts = list_system_work_contexts(
            title_id=title_id,
            work_type_id=work_type_id,
            discipline_id=discipline_id,
        )
    except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
        st.error(_safe_user_error(exc))
        st.stop()
    except Exception:
        st.error("Не удалось загрузить список систем.")
        st.stop()

    context_map = _index_by_id(contexts, "system_work_context_id")
    context_ids = list(context_map.keys())
    if not context_ids:
        st.selectbox("Система", ["—"], key="pnr_system_empty")
        st.warning("Нет систем для выбранного контекста.")
        st.stop()

    context_id = st.selectbox(
        SECTION_SYSTEM,
        context_ids,
        format_func=lambda cid: format_system_context_label(context_map[cid]),
        key="pnr_system_context_id",
    )
    context_row = context_map[str(context_id)]
    system_id = str(context_row["system_id"])
    p1_context = is_p1_system_context(context_row.get("context_system_code"))

    st.markdown(f"### {SECTION_PHYSICAL}")
    reset_dependent_selections(
        st.session_state,
        tracker_key=SESSION_TRACK_P1_L1_SYSTEM,
        parent_value=str(context_id) if p1_context else None,
        child_keys=CHILD_KEYS_AFTER_P1_L1_SYSTEM,
    )
    if p1_context:
        level1_contours = p1_level1_contours()
        contour_ids = [item.contour_code for item in level1_contours]
        contour_code = st.selectbox(
            "Физический контур",
            contour_ids,
            format_func=lambda code: next(
                contour_label(item) for item in level1_contours if item.contour_code == code
            ),
            key=WIDGET_P1_L1_CONTOUR,
        )
        reset_dependent_selections(
            st.session_state,
            tracker_key=SESSION_TRACK_P1_L1_CONTOUR,
            parent_value=str(contour_code),
            child_keys=CHILD_KEYS_AFTER_P1_L1_CONTOUR,
        )
        level1_classes = object_classes_for(str(contour_code))
        class_ids = [item.class_code for item in level1_classes]
        if class_ids:
            st.selectbox(
                "Класс физического объекта",
                class_ids,
                format_func=lambda code: next(
                    object_class_label(item)
                    for item in level1_classes
                    if item.class_code == code
                ),
                key=WIDGET_P1_L1_CLASS,
            )
        st.caption(LEVEL1_NOT_INSTANCE_CAPTION)

    st.markdown(f"**{SELECTED_OBJECT_HEADING}**")

    objects = _load_or_stop(
        lambda: list_active_objects(system_id=system_id),
        "Для выбранной системы нет активных физических объектов.",
        "Не удалось загрузить список объектов.",
    )
    object_map = _index_by_id(objects, "object_id")
    persisted_ids = list(object_map.keys())
    persisted_labels = {
        oid: format_object_label(object_map[oid]) for oid in persisted_ids
    }
    choice_ids = physical_choice_ids(
        include_p1_prototype=p1_context,
        persisted_object_ids=persisted_ids,
    )

    def _format_physical_choice(choice_id: str) -> str:
        return physical_label(choice_id, persisted_labels)

    physical_selection = st.selectbox(
        "Физический объект",
        choice_ids,
        format_func=_format_physical_choice,
        key="pnr_physical_selection",
    )
    prototype_selected = is_prototype_physical_identity(str(physical_selection))
    object_id = None if prototype_selected else str(physical_selection)
    object_row = None if prototype_selected else object_map[str(physical_selection)]
    functional_position_id = None
    fp_unresolved = False
    if not prototype_selected:
        functional_position_id, fp_unresolved = load_functional_position_id(object_id)
        if fp_unresolved:
            st.warning(
                "Функциональная позиция объекта сейчас не подтверждена. "
                "Иерархия доступна. Сохранение факта закрыто, пока связь не прочитана."
            )

    st.markdown(_format_physical_choice(str(physical_selection)))
    st.caption(PASSPORT_NOT_OBJECT_CAPTION)
    st.caption(PROTOTYPE_PHYSICAL_CAPTION)
    st.caption(INTERFACE_NOT_PHYSICAL)

    reset_dependent_selections(
        st.session_state,
        tracker_key=SESSION_TRACK_PHYSICAL,
        parent_value=str(physical_selection),
        child_keys=CHILD_KEYS_AFTER_PHYSICAL,
    )

    section_mode = work_section_resolution_mode(str(physical_selection))
    st.markdown(f"### {SECTION_WORK_SECTION}")
    work_scope_id = None
    proto_work_section_key = None
    scope_map: dict[str, dict] = {}
    scopes: list[dict] = []
    if section_mode == LIVE_SCOPES_MODE:
        try:
            scopes = professional_p1_pilot_work_scopes(list_active_work_scopes())
        except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
            st.error(_safe_user_error(exc))
            st.stop()
        except Exception:
            st.error("Не удалось загрузить разделы работ.")
            st.stop()
        scope_map = _index_by_id(scopes, "work_scope_id")
        scope_ids = [
            str(row["work_scope_id"]) for row in scopes if row.get("work_scope_id")
        ]
        if scope_ids:
            work_scope_id = st.selectbox(
                "Раздел работ",
                scope_ids,
                format_func=lambda wid: format_scope_label(scope_map[wid]),
                key="pnr_work_scope_id",
            )
        else:
            st.info(
                "Нет разделов работ профессионального контура П-1. "
                "Можно указать работу, которой нет в списке."
            )
    elif section_mode == PROTOTYPE_MODE:
        proto_sections = work_sections_for(str(physical_selection))
        if proto_sections:
            proto_work_section_key = st.selectbox(
                "Раздел работ",
                [item.key for item in proto_sections],
                format_func=lambda key: next(
                    item.label for item in proto_sections if item.key == key
                ),
                key="pnr_work_section_key",
            )
        else:
            st.info(NO_WORK_SECTIONS)
    else:
        st.info(NO_WORK_SECTIONS)

    section_parent = (
        str(work_scope_id)
        if section_mode == LIVE_SCOPES_MODE
        else proto_work_section_key
    )
    reset_dependent_selections(
        st.session_state,
        tracker_key=SESSION_TRACK_WORK_SECTION,
        parent_value=section_parent,
        child_keys=CHILD_KEYS_AFTER_WORK_SECTION,
    )

    auto_sub_key = None
    auto_subs = automation_subcontexts_for(
        str(physical_selection), proto_work_section_key
    )
    if auto_subs:
        auto_sub_key = st.selectbox(
            "Контекст автоматизации",
            [item.key for item in auto_subs],
            format_func=lambda key: next(
                item.label for item in auto_subs if item.key == key
            ),
            key="pnr_auto_subcontext",
        )
        reset_dependent_selections(
            st.session_state,
            tracker_key=SESSION_TRACK_AUTO_SUB,
            parent_value=str(auto_sub_key),
            child_keys=CHILD_KEYS_AFTER_AUTO_SUB,
        )

    st.markdown(f"### {SECTION_REQUIRED_WORK}")
    hierarchy_required = required_works_for_hierarchy(
        str(physical_selection),
        proto_work_section_key,
        auto_sub_key,
    )
    required_work_code = None
    work_label = ""
    if hierarchy_required:
        required_work_code = st.radio(
            "Конкретная работа",
            [item.code for item in hierarchy_required],
            format_func=lambda code: next(
                f"{item.code} — {item.title}"
                for item in hierarchy_required
                if item.code == code
            ),
            key="pnr_required_work",
        )
        selected_hier_rw = next(
            item for item in hierarchy_required if item.code == required_work_code
        )
        work_label = selected_hier_rw.title
        if selected_hier_rw.source == "slice":
            selected_rw = slice_required_work(str(required_work_code))
            st.caption(f"Целевое состояние: {selected_rw.target_state}")
            if selected_rw.code == "RW-MOTOR-01":
                st.caption("Кандидатный шаблон. Требует инженерного подтверждения.")
                st.caption("; ".join(RW_01_CANDIDATE_CHECKS))
            if selected_rw.code == "RW-MOTOR-02":
                st.caption(f"Критерий: {CRITERION_UNSET}")
                st.caption(f"Применимое требование: {REQUIREMENT_NEEDS_CONFIRMATION}")
            st.markdown("**Технологический шаг**")
            if selected_rw.step is None:
                st.info(STEP_UNDEFINED)
            else:
                if selected_rw.step.candidate:
                    st.caption(CANDIDATE_STEP_CAPTION)
                st.markdown(selected_rw.step.operation_name)
                st.caption(selected_rw.step.operation_code)
            if selected_rw.code == "RW-MOTOR-03":
                st.caption(f"Применимое требование: {REQUIREMENT_NEEDS_CONFIRMATION}")
                st.caption(f"Критерий: {CRITERION_UNSET}")
                st.caption(f"Доказанное состояние: {PROVEN_STATE_NOT_CALCULATED}")
    else:
        st.info(NO_REQUIRED_WORK)

    reset_dependent_selections(
        st.session_state,
        tracker_key=SESSION_TRACK_REQUIRED_WORK,
        parent_value=required_work_code,
        child_keys=CHILD_KEYS_AFTER_REQUIRED_WORK,
    )

    st.markdown(f"### {SECTION_OPERATION}")
    operations: list[dict] = []
    operation_mode = MODE_CATALOG
    operation_id = None
    unmapped_name = None
    proto_operations = operations_for_required_work(required_work_code)
    if proto_operations:
        proto_op_key = st.selectbox(
            "Операция",
            [item.key for item in proto_operations],
            format_func=lambda key: next(
                item.label for item in proto_operations if item.key == key
            ),
            key="pnr_proto_operation_key",
        )
        selected_proto_op = next(
            item for item in proto_operations if item.key == proto_op_key
        )
        if not work_label:
            work_label = selected_proto_op.label
        if selected_proto_op.prototype:
            st.caption("Операция прототипа. Живая строка справочника не создаётся.")
    elif section_mode == LIVE_SCOPES_MODE:
        if work_scope_id:
            try:
                operations = list_active_operations_for_work_scope(work_scope_id=work_scope_id)
            except (PnrConfigError, PnrServiceError, PnrValidationError) as exc:
                st.error(_safe_user_error(exc))
                st.stop()
            except Exception:
                st.error("Не удалось загрузить работы.")
                st.stop()
        operation_mode = st.radio(
            "Как указать работу",
            [MODE_CATALOG, MODE_UNMAPPED],
            index=0,
            key="pnr_operation_mode",
        )
        if operation_mode == MODE_CATALOG:
            if not operations:
                st.warning(
                    "В выбранном разделе нет работ справочника. Выберите «Работы нет в списке»."
                )
            else:
                operation_map = _index_by_id(operations, "operation_id")
                operation_ids = list(operation_map.keys())
                operation_id = st.selectbox(
                    "Работа",
                    operation_ids,
                    format_func=lambda oid: format_operation_label(operation_map[oid]),
                    key="pnr_operation_id",
                )
                work_label = format_operation_label(operation_map[str(operation_id)])
        else:
            unmapped_name = st.text_input(
                "Наименование работы", placeholder="Что выполнялось"
            )
            work_label = (unmapped_name or "").strip()
    else:
        st.info(NO_OPERATIONS)

    st.markdown(f"### {SECTION_FACTUAL}")
    with st.expander(EXECUTION_EXPANDER_TITLE, expanded=False):
        st.markdown("### Фактический результат")

    done_label = st.radio(
        "Работа выполнена?",
        DONE_OPTIONS,
        index=0,
        key="pnr_done",
    )
    st.caption(DONE_BLOCKED_HELP)

    evaluation_label = None
    if done_label == DONE_COMPLETED:
        evaluation_label = st.radio(
            "Полученный результат соответствует требованию?",
            EVAL_OPTIONS,
            index=0,
            key="pnr_evaluation",
        )

    execution_status, evaluation_status = map_execution_evaluation(done_label, evaluation_label)

    observation_text = None
    partial_detail = None
    blocked_detail = None
    blocked_category_label = None
    blocked_description = None
    other_work_label = None
    _partial_completed_draft = ""
    _partial_remaining_draft = ""

    if execution_status == "COMPLETED" and evaluation_status == "DOES_NOT_CONFORM":
        observation_text = st.text_area("Что обнаружено?", height=80, key="pnr_observation")
    elif execution_status == "PARTIAL":
        _partial_completed_draft = st.text_area("Что выполнено?", height=80, key="pnr_partial_done")
        _partial_remaining_draft = st.text_area(
            "Что осталось выполнить?", height=80, key="pnr_partial_left"
        )
        try:
            partial_detail = build_partial_detail(
                _partial_completed_draft, _partial_remaining_draft
            )
        except ValueError:
            partial_detail = None
    elif execution_status == "BLOCKED":
        blocked_category_label = st.selectbox(
            "Что препятствует выполнению?",
            BLOCKED_CATEGORY_LABELS,
            key="pnr_blocked_category",
        )
        blocked_description = st.text_area(
            "Что конкретно препятствует работе?",
            height=80,
            key="pnr_blocked_description",
        )
        other_work_label = st.radio(
            "Можно выполнять другие работы?",
            OTHER_WORK_OPTIONS,
            index=0,
            key="pnr_other_work",
        )
        try:
            blocked_detail = build_blocked_detail(
                blocked_category_label,
                blocked_description,
                other_work_label,
            )
        except ValueError:
            blocked_detail = None
    elif execution_status == "NOT_COMPLETED":
        observation_text = st.text_area(
            "Комментарий к фактическому состоянию (необязательно)",
            height=80,
            key="pnr_not_completed_note",
        )

    if (
        prototype_selected
        and str(physical_selection) == KEY_MOTOR
        and observation_capture_enabled(required_work_code)
        and observation_text is None
    ):
        observation_text = st.text_area("Наблюдение", height=80, key="pnr_slice_observation")

    show_legacy_measurements = not prototype_selected
    show_slice_measurements = measurement_capture_enabled(required_work_code)
    measurement_rows: list[dict[str, Any]] = []
    if show_legacy_measurements:
        st.markdown("### Структурированные данные")
        st.caption("Измерения необязательны.")

        if "pnr_meas_count" not in st.session_state:
            st.session_state.pnr_meas_count = 0

        meas_cols = st.columns(2)
        if meas_cols[0].button("Добавить измерение", key="pnr_meas_add"):
            st.session_state.pnr_meas_count = int(st.session_state.pnr_meas_count) + 1
            st.rerun()
        if meas_cols[1].button("Убрать последнее", key="pnr_meas_remove"):
            current = int(st.session_state.pnr_meas_count)
            if current > 0:
                st.session_state.pnr_meas_count = current - 1
                st.rerun()

        for index in range(int(st.session_state.pnr_meas_count)):
            st.markdown(f"**Измерение {index + 1}**")
            measurement_rows.append(
                {
                    "parameter_name": st.text_input("Параметр", key=f"pnr_meas_param_{index}"),
                    "measurement_point": st.text_input(
                        "Точка измерения", key=f"pnr_meas_point_{index}"
                    ),
                    "value": st.number_input(
                        "Значение",
                        key=f"pnr_meas_value_{index}",
                        step=0.001,
                        format="%.3f",
                        value=0.0,
                    ),
                    "unit": st.text_input("Единица измерения", key=f"pnr_meas_unit_{index}"),
                    "instrument_text": st.text_input("Прибор", key=f"pnr_meas_instr_{index}"),
                }
            )
    elif show_slice_measurements:
        st.markdown("### Измерение")
        measurement_rows.append(
            {
                "parameter_name": st.text_input("Параметр", key="pnr_slice_meas_param"),
                "measurement_point": st.text_input(
                    "Точка измерения", key="pnr_slice_meas_point"
                ),
                "value": st.number_input(
                    "Фактическое значение",
                    key="pnr_slice_meas_value",
                    step=0.001,
                    format="%.3f",
                    value=0.0,
                ),
                "unit": st.text_input("Единица измерения", key="pnr_slice_meas_unit"),
                "instrument_text": st.text_input(
                    "Средство измерения", key="pnr_slice_meas_instr"
                ),
            }
        )

    if prototype_selected:
        st.markdown("### Подтверждающие материалы")
        st.info(EVIDENCE_NOT_CONNECTED)

    st.markdown("### Трудозатраты")

    now_local = datetime.now(PNR_SITE_TZ)
    work_date = st.date_input("Дата выполнения", value=now_local.date())
    work_time = st.time_input(
        "Время выполнения",
        value=time(now_local.hour, now_local.minute),
    )
    occurred_at = datetime.combine(work_date, work_time, tzinfo=PNR_SITE_TZ)

    people_count = st.number_input(
        "Количество специалистов",
        min_value=1,
        step=1,
        value=1,
        key="pnr_people_count",
    )
    duration_hours = st.number_input(
        "Продолжительность, ч",
        min_value=0.0,
        step=0.5,
        value=1.0,
        format="%.2f",
        key="pnr_duration_hours",
    )

    try:
        labor_preview = compute_labor_preview(int(people_count), duration_hours)
    except (InvalidOperation, ValueError, TypeError):
        labor_preview = Decimal("0")

    st.markdown(f"**Трудозатраты:** {labor_preview} чел·ч")
    st.caption("Считается автоматически. Значение нельзя изменить вручную.")

    try:
        preview_measurements = measurements_from_rows(measurement_rows, occurred_at)
        measurement_error = None
    except ValueError as exc:
        preview_measurements = []
        measurement_error = str(exc)

    st.markdown("### Проверка")
    review_lines = build_review_lines(
        project_name=format_project_label(project_row),
        title_name=format_title_label(title_row),
        discipline_name=format_discipline_label(discipline_row),
        system_label=format_system_context_label(context_row),
        object_label=_format_physical_choice(str(physical_selection)),
        scope_label=format_scope_label(scope_map[str(work_scope_id)]) if work_scope_id else None,
        work_label=work_label or "—",
        done_label=done_label,
        evaluation_label=evaluation_label,
        observation_text=(observation_text or "").strip() or None,
        partial_detail=partial_detail,
        blocked_detail_label=blocked_category_label,
        blocked_description=(blocked_description or "").strip() or None,
        other_work_label=other_work_label,
        measurements=preview_measurements,
        people_count=int(people_count),
        duration_hours=Decimal(str(duration_hours)),
        labor_preview=labor_preview,
    )
    st.markdown("\n".join(f"- {line}" for line in review_lines))

    write_permitted = structured_write_permitted(str(physical_selection)) and not fp_unresolved
    if not write_permitted or work_kind != WORK_KIND_PNR:
        st.button("Сохранить факт", type="primary", disabled=True)
        if work_kind != WORK_KIND_PNR:
            st.info("Исполнение СМР в этом контуре не подключено.")
        elif fp_unresolved:
            st.info(
                "Сохранение закрыто: функциональная позиция объекта не подтверждена."
            )
        else:
            st.info(SAVE_DISABLED_REASON)
        submitted = False
    else:
        submitted = st.button("Сохранить факт", type="primary")

    if submitted and structured_write_permitted(str(physical_selection)):
        if fp_unresolved:
            st.error(
                "Сохранение закрыто: функциональная позиция объекта не подтверждена."
            )
        else:
            error_message = None
            selected_scope_id = None
            try:
                selected_scope_id = require_selected_work_scope(work_scope_id)
            except ValueError as exc:
                error_message = str(exc)
            if error_message is None:
                if operation_mode == MODE_CATALOG and not operation_id:
                    error_message = "Выберите работу из справочника или режим «Работы нет в списке»."
                elif operation_mode == MODE_UNMAPPED and not (unmapped_name or "").strip():
                    error_message = "Укажите наименование работы."
                elif execution_status == "COMPLETED" and evaluation_status == "DOES_NOT_CONFORM":
                    if not (observation_text or "").strip():
                        error_message = "Укажите, что обнаружено."
                elif execution_status == "PARTIAL":
                    try:
                        partial_detail = build_partial_detail(
                            _partial_completed_draft, _partial_remaining_draft
                        )
                    except ValueError as exc:
                        error_message = str(exc)
                elif execution_status == "BLOCKED":
                    try:
                        blocked_detail = build_blocked_detail(
                            blocked_category_label or "",
                            blocked_description or "",
                            other_work_label or "",
                        )
                    except ValueError as exc:
                        error_message = str(exc)
                if error_message is None and measurement_error:
                    error_message = measurement_error

            if error_message:
                st.error(error_message)
            else:
                duration_dec = Decimal(str(duration_hours))
                kwargs = build_structured_kwargs(
                    system_id=system_id,
                    object_id=str(object_id),
                    work_scope_id=selected_scope_id,
                    functional_position_id=functional_position_id,
                    operation_mode=operation_mode,
                    operation_id=str(operation_id) if operation_id else None,
                    unmapped_operation_name=unmapped_name,
                    execution_status=execution_status,
                    evaluation_status=evaluation_status,
                    occurred_at=occurred_at,
                    people_count=int(people_count),
                    duration_hours=duration_dec,
                    observation_text=observation_text,
                    measurements=preview_measurements,
                    blocked_detail=blocked_detail,
                    partial_detail=partial_detail,
                )
                fingerprint = submit_fingerprint(kwargs)
                last = st.session_state.get("pnr_last_submit_fingerprint")
                if last == fingerprint:
                    st.warning(
                        "Этот же факт только что отправлен. "
                        "Для новой попытки измените результат или другие данные."
                    )
                else:
                    try:
                        created = create_structured_execution_event(**kwargs)
                    except (PnrConfigError, PnrValidationError, PnrServiceError) as exc:
                        st.error(_safe_user_error(exc))
                    except Exception:
                        st.error("Не удалось сохранить факт ПНР. Повторите попытку.")
                    else:
                        st.session_state.pnr_last_submit_fingerprint = fingerprint
                        st.success("Факт выполнения сохранён.")
                        event_id = (created or {}).get("event_id")
                        if event_id:
                            with st.expander("Технические сведения"):
                                st.caption(f"Идентификатор записи: {event_id}")

    st.markdown(f"### {SECTION_INSPECTION}")
    st.info(CONTEXT_NOT_CONNECTED)
    st.caption("Инспекция отделена от фактического исполнения. Модель данных ещё не подключена.")

    st.markdown(f"### {SECTION_EVIDENCE}")
    st.info(EVIDENCE_NOT_CONNECTED)
    st.caption("Категории: " + ", ".join(evidence_category_labels()) + ".")

    st.markdown(f"### {SECTION_DOC_READY}")
    st.info(CONTEXT_NOT_CONNECTED)
    st.caption("Физическое завершение не означает документальную готовность.")

    st.markdown(f"### {SECTION_ACCEPTANCE}")
    st.info(CONTEXT_NOT_CONNECTED)
    st.caption("Актирование отделено от исполнения, инспекции и доказательств.")

    st.markdown(f"### {SECTION_WORK_STATUS}")
    st.info(CONTEXT_NOT_CONNECTED)
    st.caption("Различаются: " + ", ".join(status_dimension_labels()) + ".")
    st.caption("Доказанное состояние и следующая работа не рассчитываются.")

with right_col:
    if is_p1_system_context(context_row.get("context_system_code")):
        _render_p1_passport()
    else:
        st.caption(PASSPORT_REQUIRES_P1_CONTEXT)
