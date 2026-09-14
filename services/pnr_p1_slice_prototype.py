"""
Page60 Vertical Slice v0.1 — presentation-only P-1.1 motor/fan prototype.

No Supabase, no network, no I/O, no writes, no generated UUIDs.
Prototype keys are not database identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass

PROTO_KEY_PREFIX = "proto:"

KEY_P1 = "proto:p1"
KEY_P11 = "proto:p1.1"
KEY_VEROSA = "proto:verosa"
KEY_FAN_UNIT = "proto:fan-unit"
KEY_FAN = "proto:fan"
KEY_MOTOR = "proto:motor"

SELECTABLE_KEYS: tuple[str, ...] = (KEY_FAN, KEY_MOTOR)

GRAPH_TITLE = "Операционный граф физических объектов системы П-1"
EXECUTION_GRAPH_HEADING = "Операционный граф физического исполнения DYNAMIS"
HISTORY_HEADING = "Структурированная цифровая память физического исполнения"
CONTEXT_PANEL_TITLE = "Инженерный контекст"
LEFT_PANEL_TITLE = "Фиксация физического исполнения"
TREE_LINES: tuple[str, ...] = (
    "П-1",
    "└── П1.1 / 795-U-030A",
    "└── ВЕРОСА-500-194-02-61-УХЛ3",
    "└── Вентиляторный узел",
)
PROTOTYPE_DISCLAIMER = (
    "Контекст для проверки UX. Узлы прототипа не являются записями "
    "реестра до подтверждения в модели данных."
)
SAVE_DISABLED_REASON = (
    "Фиксация события будет доступна после подтверждения "
    "физического объекта в реестре."
)
FAN_NO_REQUIRED_WORK = "Требуемые работы для выбранного объекта ещё не сформированы."
HISTORY_EMPTY_OBJECT = "По выбранному физическому объекту ещё нет зафиксированных событий."
HISTORY_NO_MIXING = (
    "События других физических объектов системы не подмешиваются в эту историю."
)
HISTORY_PERSISTED_LIMITATION = (
    "Объектно-привязанная история на этой странице не подключена. "
    "Журнал событий доступен отдельно и не подмешивается сюда автоматически."
)
EVIDENCE_NOT_CONNECTED = (
    "Хранение подтверждающих материалов ещё не подключено в этом срезе."
)
STEP_UNDEFINED = "Канонический технологический шаг ещё не определён."
CRITERION_UNSET = "Не установлен в текущем контексте"
REQUIREMENT_NEEDS_CONFIRMATION = "Требует инженерного подтверждения"
PROVEN_STATE_NOT_CALCULATED = "Не рассчитано"
IDENTITY_PROTOTYPE = "Прототип инженерного контекста"
NAMEPLATE_UNKNOWN = "Требует подтверждения"
DOCUMENTS_SOURCE_CONTEXT = (
    "Известный инженерный контекст среза: система П-1, установка П1.1 / 795-U-030A, "
    "оборудование ВЕРОСА-500-194-02-61-УХЛ3, вентиляторный узел."
)
DOCUMENTS_EXECUTION_NOT_MODELED = "Не моделированы для данного vertical slice."
DOCUMENTS_READINESS_NOT_CALCULATED = "Не рассчитывается."
NOT_MODELED = "Не моделировано"
CANDIDATE_STEP_CAPTION = "Кандидатный технологический шаг"

RW_MOTOR_01 = "RW-MOTOR-01"
RW_MOTOR_02 = "RW-MOTOR-02"
RW_MOTOR_03 = "RW-MOTOR-03"

COM_INSP_002 = "COM-INSP-002"
COM_ELEC_002 = "COM-ELEC-002"

RIGHT_MODES: tuple[str, ...] = (
    "Дерево",
    "Контекст",
    "История",
    "Требования",
    "Документы",
)

PLACEHOLDER_CONTEXT_NODES: tuple[str, ...] = (
    "ШСАУ П1.1",
    "Блочный ИТП П1.1",
    "П1.2",
    "Воздушный тракт П-1",
    "Внешние связи",
)


@dataclass(frozen=True)
class PrototypeNode:
    key: str
    label: str
    selectable: bool
    parent_key: str | None
    role: str


@dataclass(frozen=True)
class CanonicalStep:
    operation_code: str
    operation_name: str
    candidate: bool


@dataclass(frozen=True)
class RequiredWorkTemplate:
    code: str
    title: str
    target_state: str
    observation: bool
    measurement: bool
    step: CanonicalStep | None
    required_state_name: str


@dataclass(frozen=True)
class ObjectContext:
    physical_object: str
    system: str
    installation: str
    equipment: str
    unit: str
    identity_type: str
    nameplate: str
    provenance: str


NODES: tuple[PrototypeNode, ...] = (
    PrototypeNode(KEY_P1, "П-1 — приточная система", False, None, "system"),
    PrototypeNode(KEY_P11, "П1.1 / 795-U-030A", False, KEY_P1, "installation"),
    PrototypeNode(
        KEY_VEROSA,
        "ВЕРОСА-500-194-02-61-УХЛ3",
        False,
        KEY_P11,
        "equipment",
    ),
    PrototypeNode(KEY_FAN_UNIT, "Вентиляторный узел", False, KEY_VEROSA, "unit"),
    PrototypeNode(KEY_FAN, "Вентилятор", True, KEY_FAN_UNIT, "fan"),
    PrototypeNode(KEY_MOTOR, "Электродвигатель", True, KEY_FAN_UNIT, "motor"),
)

REQUIRED_WORKS: tuple[RequiredWorkTemplate, ...] = (
    RequiredWorkTemplate(
        code=RW_MOTOR_01,
        title="Проверить монтажную готовность электродвигателя П1.1",
        target_state="Монтажно готов",
        observation=True,
        measurement=False,
        step=CanonicalStep(
            operation_code=COM_INSP_002,
            operation_name="Проверка механической готовности объекта",
            candidate=True,
        ),
        required_state_name="Монтажная готовность",
    ),
    RequiredWorkTemplate(
        code=RW_MOTOR_02,
        title="Проверить защитное заземление электродвигателя П1.1",
        target_state="Защитное заземление подтверждено",
        observation=True,
        measurement=False,
        step=None,
        required_state_name="Защитное заземление",
    ),
    RequiredWorkTemplate(
        code=RW_MOTOR_03,
        title="Измерить сопротивление изоляции электродвигателя П1.1",
        target_state="Состояние изоляции подтверждено",
        observation=True,
        measurement=True,
        step=CanonicalStep(
            operation_code=COM_ELEC_002,
            operation_name="Измерение сопротивления изоляции электрооборудования",
            candidate=False,
        ),
        required_state_name="Состояние изоляции",
    ),
)

CONCEPTUAL_CHAIN: tuple[str, ...] = (
    "Исходное состояние",
    "Условие готовности",
    "Конкретная работа",
    "Исполнитель",
    "Технологический шаг",
    "Событие",
    "Наблюдение / Измерение",
    "Подтверждающие материалы",
    "Проверка",
    "Доказанное состояние",
    "Следующая работа",
)

RW_01_CANDIDATE_CHECKS: tuple[str, ...] = (
    "идентификация объекта",
    "визуальный осмотр",
    "проверка монтажной готовности",
    "проверка крепления",
    "проверка очевидных механических повреждений",
)


def is_prototype_key(value: str | None) -> bool:
    text = str(value or "")
    return text.startswith(PROTO_KEY_PREFIX)


def allows_execution_event_write(value: str | None) -> bool:
    return not is_prototype_key(value)


def node_by_key(key: str) -> PrototypeNode:
    for node in NODES:
        if node.key == key:
            return node
    raise KeyError(key)


def selectable_nodes() -> tuple[PrototypeNode, ...]:
    return tuple(node for node in NODES if node.selectable)


def required_works_for(key: str | None) -> tuple[RequiredWorkTemplate, ...]:
    if key == KEY_MOTOR:
        return REQUIRED_WORKS
    return ()


def required_work_by_code(code: str) -> RequiredWorkTemplate:
    for item in REQUIRED_WORKS:
        if item.code == code:
            return item
    raise KeyError(code)


def measurement_capture_enabled(rw_code: str | None) -> bool:
    if not rw_code:
        return False
    return required_work_by_code(rw_code).measurement


def observation_capture_enabled(rw_code: str | None) -> bool:
    if not rw_code:
        return False
    return required_work_by_code(rw_code).observation


def context_for(key: str) -> ObjectContext:
    provenance = f"{IDENTITY_PROTOTYPE}. Ключ среза: {key}."
    if key == KEY_MOTOR:
        return ObjectContext(
            physical_object="Электродвигатель П1.1",
            system="П-1",
            installation="П1.1 / 795-U-030A",
            equipment="ВЕРОСА-500-194-02-61-УХЛ3",
            unit="Вентиляторный узел",
            identity_type=IDENTITY_PROTOTYPE,
            nameplate=NAMEPLATE_UNKNOWN,
            provenance=provenance,
        )
    if key == KEY_FAN:
        return ObjectContext(
            physical_object="Вентилятор П1.1",
            system="П-1",
            installation="П1.1 / 795-U-030A",
            equipment="ВЕРОСА-500-194-02-61-УХЛ3",
            unit="Вентиляторный узел",
            identity_type=IDENTITY_PROTOTYPE,
            nameplate=NAMEPLATE_UNKNOWN,
            provenance=provenance,
        )
    node = node_by_key(key)
    return ObjectContext(
        physical_object=node.label,
        system="П-1",
        installation="П1.1 / 795-U-030A",
        equipment="ВЕРОСА-500-194-02-61-УХЛ3",
        unit="Вентиляторный узел",
        identity_type=IDENTITY_PROTOTYPE,
        nameplate=NAMEPLATE_UNKNOWN,
        provenance=provenance,
    )


def prototype_choice_label(key: str) -> str:
    node = node_by_key(key)
    if key == KEY_MOTOR:
        return "Электродвигатель П1.1 (прототип контекста)"
    if key == KEY_FAN:
        return "Вентилятор П1.1 (прототип контекста)"
    return f"{node.label} (прототип контекста)"
