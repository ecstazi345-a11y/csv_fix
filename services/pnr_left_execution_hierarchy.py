"""
Page60 LEFT execution hierarchy v0.1 — deterministic presentation cascade.

Read-only prototype catalog for P-1 composition where registry data is absent.
No database client, no I/O, no writes, no generated UUIDs.
Prototype keys are not database identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Sequence

from services.pnr_p1_slice_prototype import (
    COM_ELEC_002,
    COM_INSP_002,
    KEY_FAN,
    KEY_MOTOR,
    PROTO_KEY_PREFIX,
    RW_MOTOR_01,
    RW_MOTOR_02,
    RW_MOTOR_03,
    RequiredWorkTemplate,
    allows_execution_event_write,
    is_prototype_key,
    required_work_by_code,
    required_works_for,
)

# Human-facing LEFT hierarchy (navigation order). Do not add machine-layer gates.
HIERARCHY_LABELS: tuple[str, ...] = (
    "Общие данные",
    "Система",
    "Физический объект",
    "Раздел работ",
    "Конкретная работа",
    "Операция",
    "Фактическое исполнение",
    "Инспекция / проверка результата",
    "Доказательства исполнения",
    "Документальная готовность",
    "Актирование / признание результата",
    "Статус работы",
)

SECTION_GENERAL = HIERARCHY_LABELS[0]
SECTION_SYSTEM = HIERARCHY_LABELS[1]
SECTION_PHYSICAL = HIERARCHY_LABELS[2]
SECTION_WORK_SECTION = HIERARCHY_LABELS[3]
SECTION_REQUIRED_WORK = HIERARCHY_LABELS[4]
SECTION_OPERATION = HIERARCHY_LABELS[5]
SECTION_FACTUAL = HIERARCHY_LABELS[6]
SECTION_INSPECTION = HIERARCHY_LABELS[7]
SECTION_EVIDENCE = HIERARCHY_LABELS[8]
SECTION_DOC_READY = HIERARCHY_LABELS[9]
SECTION_ACCEPTANCE = HIERARCHY_LABELS[10]
SECTION_WORK_STATUS = HIERARCHY_LABELS[11]

GENERAL_FIELD_ORDER: tuple[str, ...] = (
    "Проект",
    "Очередь",
    "Вид работ",
    "Титул",
    "Наименование титула",
    "Дисциплина",
    "Система",
)

WORK_KIND_PNR = "ПНР"
WORK_KIND_SMR = "СМР"
WORK_KIND_OPTIONS: tuple[str, ...] = (WORK_KIND_PNR, WORK_KIND_SMR)

CONTEXT_UNAVAILABLE = "Не определено в текущем контексте"
CONTEXT_NOT_CONNECTED = "Слой ещё не подключён к данным продукта"
PROTOTYPE_PHYSICAL_CAPTION = (
    "Варианты с пометкой прототипа не являются записями реестра "
    "и не могут быть отправлены как живые идентификаторы исполнения."
)
INTERFACE_NOT_PHYSICAL = (
    "Межсистемные связи и интерфейсы не являются физическими объектами "
    "этого селектора (сигналы, пожарная автоматика, верхний уровень, "
    "электроснабжение, теплоснабжение)."
)
NO_WORK_SECTIONS = "Для выбранного физического объекта разделы работ ещё не заданы."
NO_REQUIRED_WORK = "Для выбранного раздела конкретные работы ещё не заданы."
NO_OPERATIONS = "Для выбранной работы операции ещё не заданы."
LIVE_SCOPES_MODE = "live_scopes"
PROTOTYPE_MODE = "prototype"
EMPTY_MODE = "empty"

# Prototype physical membership for P-1 presentation (not ontology persistence).
KEY_P11_A = "proto:p1.1-795-u-030a"
KEY_P11_B = "proto:p1.2-795-u-030b"
KEY_SHSAU_P11 = "proto:shsau-p11"
KEY_FAN_P11 = KEY_FAN
KEY_MOTOR_P11 = KEY_MOTOR
KEY_VFD = "proto:vfd-p11"
KEY_DAMPER = "proto:air-damper-p11"
KEY_FILTER = "proto:filter-p11"
KEY_HEATER = "proto:air-heater-p11"
KEY_INSTRUMENT = "proto:kip-p11"
KEY_ITP = "proto:block-itp-p11"
KEY_DUCTS = "proto:ducts-p11"
KEY_REGULATORS = "proto:regulators-p11"
KEY_FIRE_DAMPERS = "proto:fire-dampers-p11"

WS_MECH = "ws:mech-ready"
WS_ELEC = "ws:elec-ready"
WS_AUTO = "ws:automation"
WS_AUTO_PTI = "ws:automation-pti"
WS_AUTO_PROTECT = "ws:automation-protect"
WS_AUTO_INTERLOCK = "ws:automation-interlock"
WS_AUTO_SIGNAL = "ws:automation-signal"
WS_AUTO_CONTROL = "ws:automation-control"
WS_AUTO_INTERSYS = "ws:automation-intersys"
WS_INDIV = "ws:individual-tests"
WS_FUNC = "ws:functional-tests"
WS_COMPLEX = "ws:complex-trial"

RW_SHSAU_P1_READY = "RW-SHSAU-P1-READY"

# TEMPORARY vertical-slice presentation mapping only.
# Not a database identity merge. Not an authoritative relationship.
# Pending the future SYSTEM ↔ PHYSICAL OBJECT ↔ WORK SECTION model.
LIVE_SHSAU_P1_OBJECT_ID = "1796501a-44a6-4d3a-855b-7ea16b9fdc2c"
CASCADE_PRESENTATION_ALIASES: dict[str, str] = {
    LIVE_SHSAU_P1_OBJECT_ID: KEY_SHSAU_P11,
}

OP_READY_CHECK = "proto-op:ready-check"
OP_TRIAL_RUN = "proto-op:trial-run"

SESSION_TRACK_PHYSICAL = "_pnr_hier_physical"
SESSION_TRACK_WORK_SECTION = "_pnr_hier_work_section"
SESSION_TRACK_AUTO_SUB = "_pnr_hier_auto_sub"
SESSION_TRACK_REQUIRED_WORK = "_pnr_hier_required_work"

CHILD_KEYS_AFTER_PHYSICAL: tuple[str, ...] = (
    "pnr_work_section_key",
    "pnr_work_scope_id",
    "pnr_auto_subcontext",
    "pnr_required_work",
    "pnr_operation_id",
    "pnr_proto_operation_key",
    "pnr_operation_mode",
)
CHILD_KEYS_AFTER_WORK_SECTION: tuple[str, ...] = (
    "pnr_auto_subcontext",
    "pnr_required_work",
    "pnr_operation_id",
    "pnr_proto_operation_key",
    "pnr_operation_mode",
)
CHILD_KEYS_AFTER_AUTO_SUB: tuple[str, ...] = (
    "pnr_required_work",
    "pnr_operation_id",
    "pnr_proto_operation_key",
    "pnr_operation_mode",
)
CHILD_KEYS_AFTER_REQUIRED_WORK: tuple[str, ...] = (
    "pnr_operation_id",
    "pnr_proto_operation_key",
    "pnr_operation_mode",
)


@dataclass(frozen=True)
class HierarchyPhysicalObject:
    key: str
    label: str
    kind: str  # physical | installation


@dataclass(frozen=True)
class HierarchyWorkSection:
    key: str
    label: str


@dataclass(frozen=True)
class HierarchyRequiredWork:
    code: str
    title: str
    source: str  # prototype | slice


@dataclass(frozen=True)
class HierarchyOperation:
    key: str
    label: str
    live_operation_code: str | None
    prototype: bool


P1_PHYSICAL_OBJECTS: tuple[HierarchyPhysicalObject, ...] = (
    HierarchyPhysicalObject(KEY_P11_A, "П1.1 / 795-U-030A", "installation"),
    HierarchyPhysicalObject(KEY_P11_B, "П1.2 / 795-U-030B", "installation"),
    HierarchyPhysicalObject(KEY_FAN_P11, "Вентилятор П1.1", "physical"),
    HierarchyPhysicalObject(KEY_MOTOR_P11, "Электродвигатель П1.1", "physical"),
    HierarchyPhysicalObject(KEY_VFD, "Преобразователь частоты", "physical"),
    HierarchyPhysicalObject(KEY_DAMPER, "Воздушный клапан", "physical"),
    HierarchyPhysicalObject(KEY_FILTER, "Фильтр", "physical"),
    HierarchyPhysicalObject(KEY_HEATER, "Воздухонагреватель", "physical"),
    HierarchyPhysicalObject(KEY_INSTRUMENT, "КИП", "physical"),
    HierarchyPhysicalObject(KEY_SHSAU_P11, "ШСАУ П1.1", "physical"),
    HierarchyPhysicalObject(KEY_ITP, "Блочный ИТП", "physical"),
    HierarchyPhysicalObject(KEY_DUCTS, "Воздуховоды", "physical"),
    HierarchyPhysicalObject(KEY_REGULATORS, "Регулирующие устройства", "physical"),
    HierarchyPhysicalObject(KEY_FIRE_DAMPERS, "Противопожарные клапаны", "physical"),
)

_WORK_SECTIONS_BY_OBJECT: dict[str, tuple[HierarchyWorkSection, ...]] = {
    KEY_SHSAU_P11: (
        HierarchyWorkSection(WS_MECH, "Механическая готовность"),
        HierarchyWorkSection(WS_ELEC, "Электротехническая готовность"),
        HierarchyWorkSection(WS_AUTO, "Автоматизация"),
        HierarchyWorkSection(WS_INDIV, "Индивидуальные испытания"),
        HierarchyWorkSection(WS_FUNC, "Функциональные испытания"),
        HierarchyWorkSection(WS_COMPLEX, "Комплексное опробование"),
    ),
    KEY_MOTOR_P11: (
        HierarchyWorkSection(WS_MECH, "Механическая готовность"),
        HierarchyWorkSection(WS_ELEC, "Электротехническая готовность"),
        HierarchyWorkSection(WS_INDIV, "Индивидуальные испытания"),
    ),
    KEY_FAN_P11: (
        HierarchyWorkSection(WS_MECH, "Механическая готовность"),
        HierarchyWorkSection(WS_INDIV, "Индивидуальные испытания"),
    ),
    KEY_VFD: (
        HierarchyWorkSection(WS_ELEC, "Электротехническая готовность"),
        HierarchyWorkSection(WS_AUTO, "Автоматизация"),
        HierarchyWorkSection(WS_INDIV, "Индивидуальные испытания"),
    ),
    KEY_INSTRUMENT: (
        HierarchyWorkSection(WS_AUTO, "Автоматизация"),
        HierarchyWorkSection(WS_INDIV, "Индивидуальные испытания"),
    ),
    KEY_ITP: (
        HierarchyWorkSection(WS_MECH, "Механическая готовность"),
        HierarchyWorkSection(WS_ELEC, "Электротехническая готовность"),
        HierarchyWorkSection(WS_FUNC, "Функциональные испытания"),
    ),
    KEY_P11_A: (
        HierarchyWorkSection(WS_MECH, "Механическая готовность"),
        HierarchyWorkSection(WS_ELEC, "Электротехническая готовность"),
        HierarchyWorkSection(WS_AUTO, "Автоматизация"),
        HierarchyWorkSection(WS_COMPLEX, "Комплексное опробование"),
    ),
    KEY_P11_B: (
        HierarchyWorkSection(WS_MECH, "Механическая готовность"),
        HierarchyWorkSection(WS_ELEC, "Электротехническая готовность"),
        HierarchyWorkSection(WS_COMPLEX, "Комплексное опробование"),
    ),
}

_AUTO_SUBCONTEXTS: tuple[HierarchyWorkSection, ...] = (
    HierarchyWorkSection(WS_AUTO_PTI, "ПТИ"),
    HierarchyWorkSection(WS_AUTO_PROTECT, "Защиты"),
    HierarchyWorkSection(WS_AUTO_INTERLOCK, "Блокировки"),
    HierarchyWorkSection(WS_AUTO_SIGNAL, "Сигнализация"),
    HierarchyWorkSection(WS_AUTO_CONTROL, "Управление"),
    HierarchyWorkSection(WS_AUTO_INTERSYS, "Межсистемные взаимодействия"),
)

_REQUIRED_BY_OBJECT_SECTION: dict[tuple[str, str], tuple[HierarchyRequiredWork, ...]] = {
    (KEY_SHSAU_P11, WS_AUTO_PTI): (
        HierarchyRequiredWork(
            RW_SHSAU_P1_READY,
            "Проверить готовность П-1",
            "prototype",
        ),
    ),
    (KEY_MOTOR_P11, WS_MECH): (
        HierarchyRequiredWork(RW_MOTOR_01, "Проверить монтажную готовность электродвигателя П1.1", "slice"),
    ),
    (KEY_MOTOR_P11, WS_ELEC): (
        HierarchyRequiredWork(RW_MOTOR_02, "Проверить защитное заземление электродвигателя П1.1", "slice"),
        HierarchyRequiredWork(RW_MOTOR_03, "Измерить сопротивление изоляции электродвигателя П1.1", "slice"),
    ),
}

_OPERATIONS_BY_REQUIRED: dict[str, tuple[HierarchyOperation, ...]] = {
    RW_SHSAU_P1_READY: (
        HierarchyOperation(OP_READY_CHECK, "Проверка готовности", None, True),
        HierarchyOperation(OP_TRIAL_RUN, "Пробный пуск", None, True),
    ),
    RW_MOTOR_01: (
        HierarchyOperation(
            f"proto-op:{COM_INSP_002.lower()}",
            "Проверка механической готовности объекта",
            COM_INSP_002,
            True,
        ),
    ),
    RW_MOTOR_03: (
        HierarchyOperation(
            f"proto-op:{COM_ELEC_002.lower()}",
            "Измерение сопротивления изоляции электрооборудования",
            COM_ELEC_002,
            True,
        ),
    ),
}


def hierarchy_labels() -> tuple[str, ...]:
    return HIERARCHY_LABELS


def is_prototype_physical_identity(value: str | None) -> bool:
    return is_prototype_key(value)


def permits_live_execution_identity(value: str | None) -> bool:
    return allows_execution_event_write(value)


def p1_prototype_physical_objects() -> tuple[HierarchyPhysicalObject, ...]:
    return P1_PHYSICAL_OBJECTS


def physical_choice_ids(
    *,
    include_p1_prototype: bool,
    persisted_object_ids: Sequence[str],
) -> list[str]:
    ids = [str(item) for item in persisted_object_ids if item]
    if include_p1_prototype:
        for node in P1_PHYSICAL_OBJECTS:
            if node.key not in ids:
                ids.append(node.key)
    return ids


def physical_label(choice_id: str, persisted_labels: Mapping[str, str] | None = None) -> str:
    if persisted_labels and choice_id in persisted_labels:
        return persisted_labels[choice_id]
    for node in P1_PHYSICAL_OBJECTS:
        if node.key == choice_id:
            suffix = " (прототип контекста)" if is_prototype_key(choice_id) else ""
            return f"{node.label}{suffix}"
    if is_prototype_key(choice_id):
        return f"{choice_id} (прототип контекста)"
    return choice_id


def presentation_cascade_key(physical_key: str | None) -> str | None:
    """Map an explicit allowlisted persisted id to a prototype cascade key.

    Identity of the live object is unchanged. Unknown ids are not inferred.
    """
    if physical_key is None:
        return None
    text = str(physical_key)
    return CASCADE_PRESENTATION_ALIASES.get(text, text)


def work_section_resolution_mode(physical_key: str | None) -> str:
    cascade_key = presentation_cascade_key(physical_key)
    if not cascade_key:
        return EMPTY_MODE
    if is_prototype_key(cascade_key):
        if cascade_key in _WORK_SECTIONS_BY_OBJECT:
            return PROTOTYPE_MODE
        return EMPTY_MODE
    return LIVE_SCOPES_MODE


def work_sections_for(physical_key: str | None) -> tuple[HierarchyWorkSection, ...]:
    cascade_key = presentation_cascade_key(physical_key)
    if not cascade_key:
        return ()
    return _WORK_SECTIONS_BY_OBJECT.get(cascade_key, ())


def automation_subcontexts_for(
    physical_key: str | None,
    work_section_key: str | None,
) -> tuple[HierarchyWorkSection, ...]:
    cascade_key = presentation_cascade_key(physical_key)
    if not cascade_key or work_section_key != WS_AUTO:
        return ()
    if cascade_key not in _WORK_SECTIONS_BY_OBJECT:
        return ()
    sections = _WORK_SECTIONS_BY_OBJECT[cascade_key]
    if not any(item.key == WS_AUTO for item in sections):
        return ()
    return _AUTO_SUBCONTEXTS


def required_work_lookup_key(
    work_section_key: str | None,
    auto_subcontext_key: str | None,
) -> str | None:
    if auto_subcontext_key:
        return str(auto_subcontext_key)
    if work_section_key:
        return str(work_section_key)
    return None


def required_works_for_hierarchy(
    physical_key: str | None,
    work_section_key: str | None,
    auto_subcontext_key: str | None = None,
) -> tuple[HierarchyRequiredWork, ...]:
    cascade_key = presentation_cascade_key(physical_key)
    if not cascade_key:
        return ()
    lookup = required_work_lookup_key(work_section_key, auto_subcontext_key)
    if not lookup:
        return ()
    return _REQUIRED_BY_OBJECT_SECTION.get((cascade_key, lookup), ())


def operations_for_required_work(required_work_code: str | None) -> tuple[HierarchyOperation, ...]:
    if not required_work_code:
        return ()
    return _OPERATIONS_BY_REQUIRED.get(str(required_work_code), ())


def slice_required_work(code: str) -> RequiredWorkTemplate:
    return required_work_by_code(code)


def slice_required_works_for_motor() -> tuple[RequiredWorkTemplate, ...]:
    return required_works_for(KEY_MOTOR)


def title_name_display(title_row: Mapping[str, Any] | None) -> str:
    if not title_row:
        return CONTEXT_UNAVAILABLE
    name = str(title_row.get("title_name") or "").strip()
    code = str(title_row.get("title_code") or "").strip()
    if name and code and name != code:
        return name
    if name:
        return name
    return CONTEXT_UNAVAILABLE


def queue_display() -> str:
    return CONTEXT_UNAVAILABLE


def reset_dependent_selections(
    session_state: MutableMapping[str, Any],
    *,
    tracker_key: str,
    parent_value: str | None,
    child_keys: Sequence[str],
) -> bool:
    """Clear dependent widget state when parent selection changes.

    Returns True when a reset occurred.
    """
    normalized = None if parent_value is None else str(parent_value)
    previous = session_state.get(tracker_key)
    if previous == normalized:
        return False
    for key in child_keys:
        session_state.pop(key, None)
    session_state[tracker_key] = normalized
    return True


def apply_hierarchy_cascade(
    session_state: MutableMapping[str, Any],
    *,
    physical_key: str | None,
    work_section_key: str | None,
    auto_subcontext_key: str | None = None,
    required_work_code: str | None = None,
) -> dict[str, bool]:
    """Reset stale lower selections after parent changes (sequential)."""
    physical_changed = reset_dependent_selections(
        session_state,
        tracker_key=SESSION_TRACK_PHYSICAL,
        parent_value=physical_key,
        child_keys=CHILD_KEYS_AFTER_PHYSICAL,
    )
    if physical_changed:
        session_state.pop(SESSION_TRACK_WORK_SECTION, None)
        session_state.pop(SESSION_TRACK_AUTO_SUB, None)
        session_state.pop(SESSION_TRACK_REQUIRED_WORK, None)

    section_changed = reset_dependent_selections(
        session_state,
        tracker_key=SESSION_TRACK_WORK_SECTION,
        parent_value=work_section_key,
        child_keys=CHILD_KEYS_AFTER_WORK_SECTION,
    )
    if section_changed:
        session_state.pop(SESSION_TRACK_AUTO_SUB, None)
        session_state.pop(SESSION_TRACK_REQUIRED_WORK, None)

    auto_changed = reset_dependent_selections(
        session_state,
        tracker_key=SESSION_TRACK_AUTO_SUB,
        parent_value=auto_subcontext_key,
        child_keys=CHILD_KEYS_AFTER_AUTO_SUB,
    )
    if auto_changed:
        session_state.pop(SESSION_TRACK_REQUIRED_WORK, None)

    required_changed = reset_dependent_selections(
        session_state,
        tracker_key=SESSION_TRACK_REQUIRED_WORK,
        parent_value=required_work_code,
        child_keys=CHILD_KEYS_AFTER_REQUIRED_WORK,
    )
    return {
        "physical": physical_changed,
        "work_section": section_changed,
        "auto_subcontext": auto_changed,
        "required_work": required_changed,
    }


def evidence_category_labels() -> tuple[str, ...]:
    return (
        "фото",
        "измерение",
        "протокол",
        "запись прибора",
        "документ",
        "иное подтверждение",
    )


def status_dimension_labels() -> tuple[str, ...]:
    return (
        "статус выполнения",
        "результат проверки",
        "состояние физического объекта",
        "документальная готовность",
        "статус признания",
    )


__all__ = [
    "CHILD_KEYS_AFTER_AUTO_SUB",
    "CHILD_KEYS_AFTER_PHYSICAL",
    "CHILD_KEYS_AFTER_REQUIRED_WORK",
    "CHILD_KEYS_AFTER_WORK_SECTION",
    "CONTEXT_NOT_CONNECTED",
    "CONTEXT_UNAVAILABLE",
    "EMPTY_MODE",
    "GENERAL_FIELD_ORDER",
    "HIERARCHY_LABELS",
    "HierarchyOperation",
    "HierarchyPhysicalObject",
    "HierarchyRequiredWork",
    "HierarchyWorkSection",
    "INTERFACE_NOT_PHYSICAL",
    "KEY_MOTOR_P11",
    "KEY_SHSAU_P11",
    "LIVE_SCOPES_MODE",
    "LIVE_SHSAU_P1_OBJECT_ID",
    "NO_OPERATIONS",
    "NO_REQUIRED_WORK",
    "NO_WORK_SECTIONS",
    "OP_READY_CHECK",
    "OP_TRIAL_RUN",
    "PROTOTYPE_MODE",
    "PROTOTYPE_PHYSICAL_CAPTION",
    "PROTO_KEY_PREFIX",
    "RW_SHSAU_P1_READY",
    "SECTION_ACCEPTANCE",
    "SECTION_DOC_READY",
    "SECTION_EVIDENCE",
    "SECTION_FACTUAL",
    "SECTION_GENERAL",
    "SECTION_INSPECTION",
    "SECTION_OPERATION",
    "SECTION_PHYSICAL",
    "SECTION_REQUIRED_WORK",
    "SECTION_SYSTEM",
    "SECTION_WORK_SECTION",
    "SECTION_WORK_STATUS",
    "WORK_KIND_OPTIONS",
    "WORK_KIND_PNR",
    "WORK_KIND_SMR",
    "WS_AUTO",
    "WS_AUTO_PTI",
    "apply_hierarchy_cascade",
    "automation_subcontexts_for",
    "evidence_category_labels",
    "hierarchy_labels",
    "is_prototype_physical_identity",
    "operations_for_required_work",
    "p1_prototype_physical_objects",
    "permits_live_execution_identity",
    "physical_choice_ids",
    "physical_label",
    "presentation_cascade_key",
    "queue_display",
    "required_work_lookup_key",
    "required_works_for_hierarchy",
    "reset_dependent_selections",
    "slice_required_work",
    "slice_required_works_for_motor",
    "status_dimension_labels",
    "title_name_display",
    "work_section_resolution_mode",
    "work_sections_for",
]
