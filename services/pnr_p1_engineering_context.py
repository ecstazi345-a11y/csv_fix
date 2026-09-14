"""
P-1 Engineering Context Passport v0.2.1 — presentation-only structured model.

Read-only engineering knowledge for Page60 RIGHT surface.
No Supabase, network, writes, UUID generation, SQL, or Required Work.
Not a registry authority and not an execution event model.
Per-fact provenance is preserved; UI may group only identical provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

STATUS_CONFIRMED = "ПОДТВЕРЖДЕНО ИСТОЧНИКОМ"
STATUS_REVISION_CHECK = "ТРЕБУЕТ ПРОВЕРКИ РЕВИЗИИ"
STATUS_CONFLICT = "КОНФЛИКТ / ТРЕБУЕТ ИНЖЕНЕРНОЙ ПРОВЕРКИ"
STATUS_MISSING = "ОТСУТСТВУЕТ КОНТЕКСТ"

CANONICAL_SYSTEM_LABEL = "П-1"
PASSPORT_TITLE = "Паспорт инженерного контекста системы П-1"
PASSPORT_SUBTITLE = (
    "Структурированное инженерное представление назначения, "
    "физической структуры, проектных требований, связей "
    "и происхождения данных системы."
)
NAV_TITLE = "Навигация по физической системе"
GRAPH_TITLE = "Операционный граф физических объектов системы П-1"
FLOW_NOT_ROUTING_CAPTION = (
    "Функциональная схема потока. Не является подтверждённой трассировкой воздуховодов."
)
GRAPH_NOT_REGISTRY_CAPTION = (
    "Статус модели: предварительная инженерная структура. "
    "Идентификация отдельных физических объектов требует подтверждения."
)
EXECUTION_EXPANDER_TITLE = "Фиксация физического исполнения — текущий прототип"
DOC_EXECUTION_NOT_FORMED = (
    "сведения отсутствуют в текущем инженерном контексте"
)
DOC_READINESS_NOT_CALCULATED = "не определена"
RELATED_NOT_CHILDREN = (
    "Указанные системы связаны с П-1 функционально, но не входят в её состав."
)
PASSPORT_REQUIRES_P1_CONTEXT = (
    "Паспорт инженерного контекста доступен при выбранной системе П-1."
)
PASSPORT_CONTEXT_HEADING = "Контекст паспорта"
SELECTED_OBJECT_HEADING = "Выбранный физический объект"
PASSPORT_NOT_OBJECT_CAPTION = (
    "Паспорт относится к системе целиком. "
    "Выбор физического объекта не перестраивает паспорт."
)
DESIGN_MODE_HEADING = "Расчётный режим системы"
CLIMATE_HEADING = "Климатический контекст"
KV_PARAM_HEADER = "Параметр"
KV_VALUE_HEADER = "Значение"

PASSPORT_TABS: tuple[str, ...] = (
    "Обзор",
    "Физическая система",
    "Функциональная логика",
    "Источники",
    "Конфликты",
)

SECTION_TITLES: dict[str, str] = {
    "01": "01. Идентификация системы",
    "02": "02. Назначение и функциональная граница",
    "03": "03. Обслуживаемые помещения и физические зоны",
    "04": "04. Физическая среда и функциональный поток",
    "05": "05. Проектные характеристики и требуемые режимы",
    "06": "06. Операционный граф физических объектов системы П-1",
    "07": "07. Энергетические и технологические контуры",
    "08": "08. Автоматизация и функциональная логика",
    "09": "09. Внешние интерфейсы и зависимости",
    "10": "10. Источники, ревизии и происхождение данных",
    "11": "11. Конфликты, неопределённость и отсутствующий контекст",
    "12": "12. Документальная модель системы",
}

DSS_CODE = "2400-R-NG-795-MH-DSS-0015-00"
DSS_REV = "06C"
DSS_DATE = "29.08.2023"
DSS_LABEL = "DSS 0015 / 06C"
DTS_CODE = "2400-R-NG-795-MH-DTS-0033-00"
DTS_REV = "01D"
DTS_DATE = "25.12.2020"
DTS_LABEL = "DTS 0033 / 01D"
DTS_DRAWING = "120.ЮР.2017-2400-03-2-УКПГ2-011-ОВ1-ОЛ2"
REQ_CODE = "2400-R-NG-795-MH-REQ-0033-00"
MTO_CODE = "2400-R-NG-795-MH-MTO-0018-00"
MTO_REV = "04C"
MTO_DATE = "29.08.2023"


@dataclass(frozen=True)
class EngineeringFact:
    value: str
    source_document: str | None = None
    revision: str | None = None
    source_location: str | None = None
    authority_status: str = STATUS_CONFIRMED
    verification_status: str = STATUS_CONFIRMED


@dataclass(frozen=True)
class SourceRecord:
    family: str
    code: str
    revision: str | None
    dated: str | None
    description: str
    authority_status: str
    verification_status: str


@dataclass(frozen=True)
class ConflictRecord:
    code: str
    title: str
    left_source: str
    left_values: tuple[str, ...]
    right_source: str
    right_values: tuple[str, ...]
    status: str


def is_p1_system_context(context_system_code: str | None) -> bool:
    return str(context_system_code or "").strip() == CANONICAL_SYSTEM_LABEL


def _dss(value: str) -> EngineeringFact:
    return EngineeringFact(
        value=value,
        source_document=DSS_CODE,
        revision=DSS_REV,
        source_location=None,
        authority_status=STATUS_CONFIRMED,
        verification_status=STATUS_CONFIRMED,
    )


def _dts(value: str) -> EngineeringFact:
    return EngineeringFact(
        value=value,
        source_document=DTS_CODE,
        revision=DTS_REV,
        source_location=None,
        authority_status=STATUS_REVISION_CHECK,
        verification_status=STATUS_REVISION_CHECK,
    )


def _req(value: str) -> EngineeringFact:
    return EngineeringFact(
        value=value,
        source_document=REQ_CODE,
        revision=None,
        source_location=None,
        authority_status=STATUS_REVISION_CHECK,
        verification_status=STATUS_REVISION_CHECK,
    )


def fact_provenance(
    fact: EngineeringFact,
) -> tuple[str | None, str | None, str | None, str, str]:
    return (
        fact.source_document,
        fact.revision,
        fact.source_location,
        fact.authority_status,
        fact.verification_status,
    )


def shared_provenance(
    facts: tuple[EngineeringFact, ...] | list[EngineeringFact],
) -> EngineeringFact | None:
    """Return a representative fact only when every fact shares identical provenance."""
    if not facts:
        return None
    key = fact_provenance(facts[0])
    if all(fact_provenance(item) == key for item in facts):
        return facts[0]
    return None


def group_consecutive_by_provenance(
    items: tuple[tuple[str, EngineeringFact], ...] | list[tuple[str, EngineeringFact]],
) -> tuple[tuple[tuple[tuple[str, EngineeringFact], ...], EngineeringFact | None], ...]:
    groups: list[
        tuple[tuple[tuple[str, EngineeringFact], ...], EngineeringFact | None]
    ] = []
    current: list[tuple[str, EngineeringFact]] = []
    for label, fact in items:
        if current and fact_provenance(fact) != fact_provenance(current[0][1]):
            grouped = tuple(current)
            groups.append((grouped, shared_provenance([item[1] for item in grouped])))
            current = []
        current.append((label, fact))
    if current:
        grouped = tuple(current)
        groups.append((grouped, shared_provenance([item[1] for item in grouped])))
    return tuple(groups)


def compact_document_label(code: str | None) -> str:
    if not code:
        return "—"
    for family in ("DSS", "DTS", "REQ", "MTO"):
        token = f"-{family}-"
        if token in code:
            return f"{family}-{code.split(token, 1)[1]}"
    return code


def format_status_text(authority_status: str, verification_status: str) -> str:
    if authority_status == verification_status:
        return authority_status
    return (
        f"Статус источника: {authority_status} · "
        f"Статус проверки: {verification_status}"
    )


def format_provenance_caption(fact: EngineeringFact) -> str:
    bits: list[str] = [compact_document_label(fact.source_document)]
    if fact.revision:
        bits.append(f"рев. {fact.revision}")
    bits.append(format_status_text(fact.authority_status, fact.verification_status))
    return "Источник: " + " · ".join(bits)


HEADER_IDENTITY: tuple[str, ...] = (
    CANONICAL_SYSTEM_LABEL,
    "Приточная механическая вентиляция",
    "П1.1 / 795-U-030A — рабочая",
    "П1.2 / 795-U-030B — резервная",
)

HEADER_SERVES: tuple[str, ...] = (
    "Помещение компрессоров",
    "Маслохозяйство",
)

HEADER_CONFIGURATION = "100% резервирование"

IDENTIFICATION_FACTS: tuple[tuple[str, EngineeringFact], ...] = (
    (
        "Проект",
        _dss("Салмановское (Утреннее) нефтегазоконденсатное месторождение"),
    ),
    ("Объект", _dss("УКПГ-2")),
    ("Титул", _dss("УКПГ2-011")),
    (
        "Назначение титула",
        _dss("Установка дегазации конденсата с компрессорной газов дегазации"),
    ),
    ("Раздел", _dss("ОВ")),
    (
        "Система",
        EngineeringFact(
            value=CANONICAL_SYSTEM_LABEL,
            source_document=DSS_CODE,
            revision=DSS_REV,
            authority_status=STATUS_CONFIRMED,
            verification_status=STATUS_CONFIRMED,
        ),
    ),
    ("Тип", _dss("Приточная механическая вентиляция")),
    ("Рабочая установка", _dts("П1.1 / 795-U-030A")),
    ("Резервная установка", _dts("П1.2 / 795-U-030B")),
    ("Основное оборудование", _req("ВЕРОСА-500-194-02-61-УХЛ3")),
    (
        "Схема",
        EngineeringFact(
            value="рабочая + резервная / 100% резервирование",
            source_document=None,
            revision=None,
            source_location=None,
            authority_status=STATUS_REVISION_CHECK,
            verification_status=STATUS_REVISION_CHECK,
        ),
    ),
)

PURPOSE_FACTS: tuple[EngineeringFact, ...] = (
    _dss(
        "П-1 обеспечивает приточную механическую вентиляцию помещения компрессоров."
    ),
    _dss("Приточный воздух подаётся в рабочую зону помещения компрессоров."),
    _dss("П-1 также обеспечивает приточную вентиляцию маслохозяйства."),
    _dss(
        "Для помещения компрессоров предусмотрена приточно-вытяжная вентиляция "
        "с механическим побуждением."
    ),
)

PURPOSE_PRODUCTION_CONTEXT: tuple[str, ...] = (
    "лёгкий газ",
    "пары конденсата",
    "тепловыделения",
)

SERVED_SPACES: tuple[dict[str, object], ...] = (
    {
        "name": "Помещение компрессоров",
        "relation": _dss("обслуживается системой П-1"),
        "supply": _dss("рабочая зона"),
        "internal_temperature": _dss("+10 °C"),
    },
    {
        "name": "Маслохозяйство",
        "relation": _dss("обслуживается системой П-1"),
        "internal_temperature": _dss("+10 °C"),
    },
)

PHYSICAL_MEDIUM = EngineeringFact(
    value="ВОЗДУХ",
    source_document=DSS_CODE,
    revision=DSS_REV,
    authority_status=STATUS_CONFIRMED,
    verification_status=STATUS_CONFIRMED,
)

FUNCTIONAL_FLOW_TRUNK: tuple[str, ...] = (
    "НАРУЖНЫЙ ВОЗДУХ",
    "ПРИТОЧНАЯ УСТАНОВКА П-1",
    "ФИЛЬТРАЦИЯ",
    "НАГРЕВ",
    "ВЕНТИЛЯТОРНЫЙ УЗЕЛ / СОЗДАНИЕ РАСХОДА И НАПОРА",
    "ВОЗДУХОВОДНАЯ СЕТЬ",
)
FUNCTIONAL_FLOW_COMPRESSOR = "ПОМЕЩЕНИЕ КОМПРЕССОРОВ"
FUNCTIONAL_FLOW_OIL = "МАСЛОХОЗЯЙСТВО"
FUNCTIONAL_FLOW_WORKING_ZONE = "РАБОЧАЯ ЗОНА"

AIR_FLOW_CHAIN: tuple[str, ...] = FUNCTIONAL_FLOW_TRUNK + (
    FUNCTIONAL_FLOW_COMPRESSOR,
    FUNCTIONAL_FLOW_OIL,
    FUNCTIONAL_FLOW_WORKING_ZONE,
)
AIR_FLOW_ALSO_SERVES = "Обслуживание маслохозяйства"

DESIGN_FACTS: tuple[tuple[str, EngineeringFact], ...] = (
    ("Расход воздуха", _dss("18 515 м³/ч")),
    ("Давление", _dss("1034 Па")),
    ("Мощность электродвигателя", _dss("11,0 кВт")),
    ("Температура воздуха после нагрева", _dss("+10 °C")),
    ("Тепловая мощность", _dss("334 900 Вт")),
)

CLIMATE_FACTS: tuple[tuple[str, EngineeringFact], ...] = (
    ("Расчётная наружная температура", _dss("−44 °C")),
    ("Тёплый период", _dss("+13 °C")),
    ("Средняя температура отопительного периода", _dss("−11,6 °C")),
    ("Продолжительность отопительного периода", _dss("344 дня")),
)

PHYSICAL_GRAPH_LINES: tuple[str, ...] = (
    "П-1",
    "├── П1.1 / 795-U-030A [РАБОЧАЯ]",
    "│   ├── ВЕРОСА-500-194-02-61-УХЛ3",
    "│   │   ├── Входная часть",
    "│   │   │   ├── Воздушный клапан",
    "│   │   │   ├── Электропривод LF230-S",
    "│   │   │   └── Гибкая вставка",
    "│   │   ├── Фильтрация",
    "│   │   │   ├── Фильтр G4",
    "│   │   │   └── Датчик перепада давления Метран-150CDR0",
    "│   │   ├── Воздухонагреватель",
    "│   │   │   ├── Жидкостный теплообменник",
    "│   │   │   ├── Входной коллектор",
    "│   │   │   ├── Выходной коллектор",
    "│   │   │   ├── Фланцевые соединения",
    "│   │   │   ├── Дренажный поддон",
    "│   │   │   ├── Защита от замораживания",
    "│   │   │   └── Датчик температуры приточного воздуха",
    "│   │   └── Вентиляторный узел",
    "│   │       ├── Вентилятор",
    "│   │       ├── Электродвигатель",
    "│   │       ├── Преобразователь частоты",
    "│   │       └── Гибкая вставка",
    "│   ├── ШСАУ П1.1",
    "│   └── Блочный ИТП П1.1",
    "├── П1.2 / 795-U-030B [РЕЗЕРВНАЯ]",
    "├── Воздушный тракт П-1",
    "└── Внешние связи",
)

AIR_CONTOUR: tuple[str, ...] = (
    "Наружный воздух",
    "П-1",
    "обработка воздуха",
    "воздуховодная сеть",
    "обслуживаемые помещения",
)

THERMAL_CONTOUR: tuple[str, ...] = (
    "Блочно-модульная водогрейная котельная УКПГ-2",
    "горячая вода 110–70 °C",
    "ИТП",
    "45% пропиленгликоль",
    "воздухонагреватель",
    "передача тепла воздуху",
)

ELECTROMECHANICAL_CONTOUR: tuple[str, ...] = (
    "Электроснабжение",
    "ШСАУ / ПЧ",
    "электродвигатель",
    "вентилятор",
    "механическая энергия",
    "перемещение воздуха",
)

AUTOMATION_STANDBY: tuple[str, ...] = (
    "П1.1 — рабочая",
    "П1.2 — резервная",
    "Рабочая установка → отказ → автоматический запуск резервной установки",
)

AUTOMATION_FUNCTIONS: tuple[str, ...] = (
    "два ШСАУ",
    "выбор основной установки",
    "контроль загрязнения фильтра",
    "защита воздухонагревателя от замораживания",
    "циркуляционный насос",
    "дистанционное управление",
    "интерфейсы датчиков",
    "интерфейсы исполнительных механизмов",
    "интерфейс ПЧ",
    "связь с верхним уровнем",
    "связь с пожарной автоматикой",
)

FIRE_STOP_CHAIN: tuple[str, ...] = (
    "Пожарная автоматика",
    "сигнал",
    "ШСАУ",
    "останов П-1",
)

EXTERNAL_DEPENDENCIES: tuple[str, ...] = (
    "Электроснабжение",
    "Первичное теплоснабжение",
    "Пожарная автоматика",
    "ИСУБ / верхний уровень",
    "Обслуживаемая физическая среда",
)

RELATED_VENTILATION: tuple[tuple[str, str], ...] = (
    ("В1", "вытяжка верхней зоны — 1/3 воздухообмена"),
    ("В2", "вытяжка нижней зоны — 2/3 воздухообмена"),
    ("АВ1 / АВ2", "аварийная вытяжная вентиляция"),
    ("ПЕ1 / ПЕ2", "компенсация воздуха аварийной вентиляции"),
)

SOURCE_REGISTER: tuple[SourceRecord, ...] = (
    SourceRecord(
        family="DSS",
        code=DSS_CODE,
        revision=DSS_REV,
        dated=DSS_DATE,
        description="Рабочая документация «В производство работ»",
        authority_status=STATUS_CONFIRMED,
        verification_status=STATUS_CONFIRMED,
    ),
    SourceRecord(
        family="DTS",
        code=DTS_CODE,
        revision=DTS_REV,
        dated=DTS_DATE,
        description=(
            "Опросный лист П1.1 / П1.2; 795-U-030A / 795-U-030B; "
            f"{DTS_DRAWING}; AFD; "
            "2400-R-NG-795-MH-DTS-0033-00_01D_3_publication.pdf"
        ),
        authority_status=STATUS_REVISION_CHECK,
        verification_status=STATUS_REVISION_CHECK,
    ),
    SourceRecord(
        family="REQ",
        code=REQ_CODE,
        revision=None,
        dated=None,
        description="Бланк-заказ; 795-U-030A / 795-U-030B; состав ВЕРОСА",
        authority_status=STATUS_REVISION_CHECK,
        verification_status=STATUS_REVISION_CHECK,
    ),
    SourceRecord(
        family="MTO",
        code=MTO_CODE,
        revision=MTO_REV,
        dated=MTO_DATE,
        description="Спецификация оборудования / поставка Заказчика",
        authority_status=STATUS_CONFIRMED,
        verification_status=STATUS_CONFIRMED,
    ),
)

CONFLICT_P1_PARAMETERS = ConflictRecord(
    code="КОНФЛИКТ 01",
    title="Параметры П-1",
    left_source=DSS_LABEL,
    left_values=("18 515 м³/ч", "1034 Па"),
    right_source=DTS_LABEL,
    right_values=("18 515 × 1,06 = 19 625 м³/ч", "800 Па"),
    status=STATUS_CONFLICT,
)

MISSING_CONTEXT: tuple[str, ...] = (
    "актуальные контролируемые ревизии части связанных документов",
    "подтверждённая идентификация отдельных компонентов П1.1",
    "детализированный состав П1.2",
    "точная трасса воздуховодов",
    "часть паспортных характеристик оборудования",
)

SOURCE_DOCUMENT_FAMILIES: tuple[str, ...] = ("DSS", "DTS", "REQ", "MTO")


def functional_flow_html() -> str:
    """Simple HTML functional flow. Not a confirmed duct routing."""
    trunk = "".join(
        f'<div style="text-align:center;font-weight:600">{step}</div>'
        f'<div style="text-align:center">↓</div>'
        for step in FUNCTIONAL_FLOW_TRUNK[:-1]
    )
    trunk += (
        f'<div style="text-align:center;font-weight:600">'
        f"{FUNCTIONAL_FLOW_TRUNK[-1]}</div>"
    )
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:0.92rem;'
        'line-height:1.35;max-width:36rem">'
        f"{trunk}"
        '<div style="text-align:center">↙&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↘</div>'
        '<div style="display:flex;justify-content:space-around;gap:1.5rem">'
        '<div style="text-align:center">'
        f'<div style="font-weight:600">{FUNCTIONAL_FLOW_COMPRESSOR}</div>'
        "<div>↓</div>"
        f'<div style="font-weight:600">{FUNCTIONAL_FLOW_WORKING_ZONE}</div>'
        "</div>"
        f'<div style="text-align:center;font-weight:600">{FUNCTIONAL_FLOW_OIL}</div>'
        "</div></div>"
    )
