"""
P-1 Physical Master Catalog — Level 1.

Deterministic read-only catalog of physical contours and object classes.
Scoped to system П-1. No instances, work, operations, or applicability.
No Supabase, Streamlit, I/O, UUID generation, or inference.
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM_CODE = "П-1"

CONTOUR_AIR = "P1-C01-AIR"
CONTOUR_THERMAL = "P1-C02-THERMAL"
CONTOUR_REFRIGERATION = "P1-C03-REFRIGERATION"
CONTOUR_AUTOMATION_EM = "P1-C04-AUTOMATION-EM"

SESSION_TRACK_P1_L1_SYSTEM = "_pnr_p1_l1_system"
SESSION_TRACK_P1_L1_CONTOUR = "_pnr_p1_l1_contour"
WIDGET_P1_L1_CONTOUR = "pnr_p1_contour_code"
WIDGET_P1_L1_CLASS = "pnr_p1_object_class_code"
CHILD_KEYS_AFTER_P1_L1_SYSTEM: tuple[str, ...] = (
    WIDGET_P1_L1_CONTOUR,
    WIDGET_P1_L1_CLASS,
)
CHILD_KEYS_AFTER_P1_L1_CONTOUR: tuple[str, ...] = (WIDGET_P1_L1_CLASS,)

LEVEL1_NOT_INSTANCE_CAPTION = (
    "Уровень 1: физический контур и класс. "
    "Это не конкретный физический экземпляр и не идентификатор исполнения."
)


@dataclass(frozen=True)
class PhysicalObjectClass:
    class_code: str
    class_name: str
    contour_code: str
    sort_order: int


@dataclass(frozen=True)
class PhysicalContour:
    system_code: str
    contour_code: str
    contour_name: str
    sort_order: int
    object_classes: tuple[PhysicalObjectClass, ...]


def _classes(
    contour_code: str,
    names: tuple[str, ...],
    suffixes: tuple[str, ...],
) -> tuple[PhysicalObjectClass, ...]:
    return tuple(
        PhysicalObjectClass(
            class_code=f"{contour_code}-{suffix}",
            class_name=name,
            contour_code=contour_code,
            sort_order=index,
        )
        for index, (name, suffix) in enumerate(zip(names, suffixes, strict=True), start=1)
    )


_AIR_CLASSES = _classes(
    CONTOUR_AIR,
    (
        "Воздухозабор / выброс",
        "Установка",
        "Воздуховоды",
        "Фасонные элементы",
        "Клапаны",
        "Шумоглушители",
        "Воздухораспределители",
        "Обслуживаемая физическая среда",
    ),
    (
        "INTAKE-DISCHARGE",
        "UNIT",
        "DUCTS",
        "FITTINGS",
        "DAMPERS",
        "SILENCERS",
        "DIFFUSERS",
        "SERVED-MEDIUM",
    ),
)

_THERMAL_CLASSES = _classes(
    CONTOUR_THERMAL,
    (
        "Источник / граница подключения",
        "ИТП / узел регулирования",
        "Трубопроводы",
        "Насосы",
        "Арматура",
        "Нагреватель",
    ),
    (
        "SOURCE-BOUNDARY",
        "ITP",
        "PIPING",
        "PUMPS",
        "VALVES",
        "HEATER",
    ),
)

_REFRIGERATION_CLASSES = _classes(
    CONTOUR_REFRIGERATION,
    (
        "Источник холода / холодильная машина",
        "Компрессор",
        "Конденсатор",
        "Испаритель / воздухоохладитель",
        "Фреоновые трубопроводы",
        "Жидкостная линия",
        "Газовая линия",
        "Дренаж конденсата",
        "Арматура",
        "Холодильный агент",
    ),
    (
        "CHILLER",
        "COMPRESSOR",
        "CONDENSER",
        "EVAPORATOR",
        "FREON-PIPING",
        "LIQUID-LINE",
        "GAS-LINE",
        "CONDENSATE-DRAIN",
        "VALVES",
        "REFRIGERANT",
    ),
)

_AUTOMATION_EM_CLASSES = _classes(
    CONTOUR_AUTOMATION_EM,
    (
        "ШСАУ",
        "Силовое питание",
        "Преобразователи частоты",
        "Электродвигатели",
        "Датчики",
        "Исполнительные механизмы",
        "Кабельные / сигнальные связи",
        "Верхний уровень управления",
    ),
    (
        "SHSAU",
        "POWER",
        "VFD",
        "MOTORS",
        "SENSORS",
        "ACTUATORS",
        "CABLE-SIGNAL",
        "SUPERVISORY",
    ),
)

CONTOURS: tuple[PhysicalContour, ...] = (
    PhysicalContour(SYSTEM_CODE, CONTOUR_AIR, "Воздушный контур", 1, _AIR_CLASSES),
    PhysicalContour(SYSTEM_CODE, CONTOUR_THERMAL, "Тепловой контур", 2, _THERMAL_CLASSES),
    PhysicalContour(
        SYSTEM_CODE,
        CONTOUR_REFRIGERATION,
        "Холодильный контур",
        3,
        _REFRIGERATION_CLASSES,
    ),
    PhysicalContour(
        SYSTEM_CODE,
        CONTOUR_AUTOMATION_EM,
        "Автоматизация и электромеханика",
        4,
        _AUTOMATION_EM_CLASSES,
    ),
)


def system_code() -> str:
    return SYSTEM_CODE


def contours() -> tuple[PhysicalContour, ...]:
    return CONTOURS


def contour_by_code(contour_code: str | None) -> PhysicalContour | None:
    if not contour_code:
        return None
    for item in CONTOURS:
        if item.contour_code == contour_code:
            return item
    return None


def object_classes_for(contour_code: str | None) -> tuple[PhysicalObjectClass, ...]:
    contour = contour_by_code(contour_code)
    if contour is None:
        return ()
    return contour.object_classes


def all_object_classes() -> tuple[PhysicalObjectClass, ...]:
    return tuple(item for contour in CONTOURS for item in contour.object_classes)


def contour_label(contour: PhysicalContour) -> str:
    return f"{contour.sort_order:02d}. {contour.contour_name}"


def object_class_label(item: PhysicalObjectClass) -> str:
    return item.class_name


def is_level1_class_code(value: str | None) -> bool:
    if not value:
        return False
    return any(item.class_code == value for item in all_object_classes())


def is_level1_contour_code(value: str | None) -> bool:
    if not value:
        return False
    return any(item.contour_code == value for item in CONTOURS)


__all__ = [
    "CHILD_KEYS_AFTER_P1_L1_CONTOUR",
    "CHILD_KEYS_AFTER_P1_L1_SYSTEM",
    "CONTOUR_AIR",
    "CONTOUR_AUTOMATION_EM",
    "CONTOUR_REFRIGERATION",
    "CONTOUR_THERMAL",
    "CONTOURS",
    "LEVEL1_NOT_INSTANCE_CAPTION",
    "PhysicalContour",
    "PhysicalObjectClass",
    "SESSION_TRACK_P1_L1_CONTOUR",
    "SESSION_TRACK_P1_L1_SYSTEM",
    "SYSTEM_CODE",
    "WIDGET_P1_L1_CLASS",
    "WIDGET_P1_L1_CONTOUR",
    "all_object_classes",
    "contour_by_code",
    "contour_label",
    "contours",
    "is_level1_class_code",
    "is_level1_contour_code",
    "object_class_label",
    "object_classes_for",
    "system_code",
]
