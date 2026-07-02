import html
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

from services.constraint_display import (
    constraint_block_substance,
    is_generic_block_reason,
    is_insufficient_block_description,
    registry_specific_block_reason,
)
from services.constraints_loader import fetch_all_constraints
from services.supabase_client import supabase

load_dotenv()

st.set_page_config(layout="wide")

TABLE_CONSTRAINTS = "monthly_plan_constraints"
TABLE_EVIDENCE = "monthly_plan_constraint_evidence"
VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"
V2_PLAN_LINES_TABLE = "monthly_plan_lines_v2"

PLANNING_MONTH_OPTIONS = [
    "январь-2026",
    "февраль-2026",
    "март-2026",
    "апрель-2026",
    "май-2026",
    "июнь-2026",
    "июль-2026",
    "август-2026",
    "сентябрь-2026",
    "октябрь-2026",
    "ноябрь-2026",
    "декабрь-2026",
]

V2_PLAN_LINE_SELECT_COLUMNS = [
    "plan_line_id",
    "project_code",
    "month_key",
    "queue",
    "facility",
    "title",
    "discipline",
    "system",
    "iwp",
    "boq_code",
    "boq_name",
    "planned_qty",
    "unit",
    "labor_hours",
    "labor_cost",
    "crew_size",
    "unit_price",
    "plan_value",
    "crew",
    "status",
    "sent_to_constraints_at",
]

NO_CONSTRAINT_CATEGORY = "Ограничений нет"

FILTER_SESSION_KEYS = {
    "month": "admission_filter_month",
    "project": "admission_filter_project",
    "queue": "admission_filter_queue",
    "title": "admission_filter_title",
    "discipline": "admission_filter_discipline",
    "check_status": "admission_filter_check_status",
    "search_boq": "admission_filter_search_boq",
    "search_iwp": "admission_filter_search_iwp",
    "search_system": "admission_filter_search_system",
    "department": "admission_filter_department",
    "overdue_only": "admission_filter_overdue_only",
}

ADMISSION_FILTER_MEMORY_ENABLED_KEY = "admission_filter_memory_enabled"
ADMISSION_FILTERS_LOCKED_KEY = "admission_filters_locked"
ADMISSION_FILTERS_LOCKED_SNAPSHOT_KEY = "admission_filters_locked_snapshot"
ADMISSION_FILTERS_PERSISTED_KEY = "admission_filters_persisted"
ADMISSION_FILTERS_RESET_REQUESTED_KEY = "admission_filters_reset_requested"
ADMISSION_FILTERS_LOCK_REQUESTED_KEY = "admission_filters_lock_requested"

ADMISSION_FILTER_DEFAULTS: dict[str, Any] = {
    FILTER_SESSION_KEYS["month"]: "Все",
    FILTER_SESSION_KEYS["project"]: "Все",
    FILTER_SESSION_KEYS["queue"]: "Все",
    FILTER_SESSION_KEYS["title"]: "Все",
    FILTER_SESSION_KEYS["discipline"]: "Все",
    FILTER_SESSION_KEYS["check_status"]: "Все",
    FILTER_SESSION_KEYS["search_boq"]: "",
    FILTER_SESSION_KEYS["search_iwp"]: "",
    FILTER_SESSION_KEYS["search_system"]: "",
    FILTER_SESSION_KEYS["department"]: "Все",
    FILTER_SESSION_KEYS["overdue_only"]: False,
}

CONSTRAINT_EDIT_SELECT_KEY = "constraints_edit_select"
TABLE_SELECTED_ID_KEY = "constraints_table_selected_id"
TABLE_SELECTION_KEY = "constraints_table_select"
TABLE_HEIGHT_PX = 560

PACKAGE_TABLE_SELECTION_KEY = "admission_package_table_select"
PACKAGE_SELECTED_KEY = "admission_package_selected_key"
PACKAGE_CHECK_TABLE_KEY = "admission_package_check_table_select"
PACKAGE_TABLE_HEIGHT_PX = 36 * 25 + 38  # ~25 visible rows in «Список месячного плана для допуска»
PACKAGE_CHECK_TABLE_HEIGHT_PX = 280
ADMISSION_HOURS_PER_PERSON_MONTH = 176  # фонд ч/чел/мес — KPI конструктора; в таблицах допуска не показываем FTE
ADMISSION_PRODUCTIVE_HOURS_PER_PERSON_SHIFT = 8.0  # как PRODUCTIVE_HOURS_PER_PERSON_SHIFT в 10B

WORKBENCH_DETAIL_CID_KEY = "admission_workbench_detail_cid"
WORKBENCH_MAX_ROWS = 80

DIRECT_ADMIT_SELECTED_CID_KEY = "direct_admit_selected_cid"
DIRECT_ADMIT_PENDING_ACTION_KEY = "direct_admit_pending_action"
DIRECT_ADMIT_LAYOUT_KEY = "direct_admit_layout_preset"

DIRECT_ADMIT_LAYOUT_PRESETS: dict[str, list[float]] = {
    "Баланс": [28, 42, 30],
    "Широкая очередь": [35, 40, 25],
    "Широкая фиксация": [24, 38, 38],
}

DIRECT_ADMIT_PANE_HEIGHT_PX = 1450
DIRECT_ADMIT_GOV_BLOCKS_SCROLL_HEIGHT_PX = 920

DIRECT_ADMIT_FIXATION_ORIGIN_OPTIONS = [
    "Внутреннее",
    "Внешнее",
    "Смешанное",
]

DIRECT_ADMIT_FIXATION_CATEGORY_OPTIONS = [
    "РД",
    "МТР",
    "Фронт работ",
    "ОТиТБ",
    "Качество",
    "ПНР",
    "Коммерческий блок",
    "Заказчик / ГП",
    "Исполнительная документация",
    "Другое",
]

DIRECT_ADMIT_FIXATION_SEVERITY_LABELS = [
    "Низкая",
    "Средняя",
    "Высокая",
    "Критическая",
]

DIRECT_ADMIT_FIXATION_IMPACT_OPTIONS = [
    "Блокирует работы",
    "Частично ограничивает",
    "Создаёт риск",
    "Требует уточнения",
]

DIRECT_ADMIT_FIXATION_OWNER_SIDE_OPTIONS = [
    "Заказчик",
    "Генподрядчик",
    "Субподрядчик",
    "PM подрядчик",
    "Технический надзор",
    "Авторский надзор",
    "Проектировщик",
    "Вендор / поставщик оборудования",
    "МТО / снабжение",
    "ПТО",
    "Производство / участок",
    "QA/QC",
    "ОТиТБ / HSE",
    "ПНР",
    "Коммерческий блок / договорной отдел",
    "Сметный отдел",
    "Логистика",
    "Склад / входной контроль",
    "Смежный подрядчик",
    "Эксплуатация / будущий пользователь",
    "Государственный надзор / разрешительные органы",
    "Другое",
]

DIRECT_ADMIT_QUEUE_STATUS = {
    "pending": ("Требует допуска", "#64748b", "#2E5B9A"),
    "approved": ("Допущено", "#64748b", "#2F6B4F"),
    "blocked": ("Заблокировано", "#b45353", "#9B3D3D"),
    "clarify": ("Требует уточнения", "#b45309", "#92610E"),
}

DIRECT_ADMIT_CONSTRAINT_TYPE_OPTIONS = [
    "Рабочая документация",
    "Материально-техническое обеспечение",
    "Фронт работ",
    "Охрана труда и промышленная безопасность",
    "Контроль качества",
    "Пусконаладочные работы",
    "Коммерческие / договорные вопросы",
    "Проектное управление",
    "Другое",
]

DIRECT_ADMIT_CONSTRAINT_TYPE_LEGACY_RU: dict[str, str] = {
    "РД": "Рабочая документация",
    "МТР": "Материально-техническое обеспечение",
    "Front": "Фронт работ",
    "Исполнительная": "Рабочая документация",
    "Разрешение": "Коммерческие / договорные вопросы",
    "Люди": "Проектное управление",
    "Техника": "Фронт работ",
}

DIRECT_ADMIT_ROLE_OPTIONS = [
    "Участок",
    "ПТО",
    "МТО",
    "PM",
    "Заказчик",
    "ГП",
    "Субподрядчик",
    "Другое",
]

DIRECT_ADMIT_SEVERITY_OPTIONS = ["LOW", "MEDIUM", "HIGH"]

DIRECT_ADMIT_BLOCK_REASON_HELP = (
    "Причина должна отвечать на вопрос: **что конкретно мешает выполнить работу?**\n\n"
    "Примеры:\n"
    "- отсутствует утверждённая РД по системе Х;\n"
    "- не поставлены клапаны DN150;\n"
    "- зона занята смежниками;\n"
    "- отсутствует решение Технического запроса №45;\n"
    "- отсутствует допуск к помещению."
)

DIRECT_ADMIT_BLOCK_DESCRIPTION_HELP = (
    "**Что требуется сделать для снятия ограничения?**\n\n"
    "Примеры:\n"
    "- выпустить РД ревизии 5;\n"
    "- завершить монтаж кабельных трасс;\n"
    "- поставить оборудование;\n"
    "- согласовать ТЗ."
)

DIRECT_ADMIT_BLOCK_REASON_VALIDATION_ERROR = (
    "Необходимо указать конкретную причину блокировки.\n"
    "Пример:\n"
    "- отсутствует утвержденная РД;\n"
    "- отсутствует фронт работ;\n"
    "- отсутствуют МТР;\n"
    "- зона не передана;\n"
    "- отсутствует согласование ТЗ;\n"
    "- отсутствует исполнительная документация."
)

DIRECT_ADMIT_BLOCK_DESCRIPTION_VALIDATION_ERROR = (
    "Опишите суть ограничения и требуемое действие."
)

DIRECT_ADMIT_GENERIC_CRITERIA = [
    "Данные понятны",
    "Ограничений не выявлено",
    "Ответственный определён",
    "Решение можно зафиксировать",
]

DIRECT_ADMIT_CRIT_STATUS_READY = "READY"
DIRECT_ADMIT_CRIT_STATUS_PARTIAL = "PARTIAL"
DIRECT_ADMIT_CRIT_STATUS_RISK = "RISK"
DIRECT_ADMIT_CRIT_STATUS_BLOCKER = "BLOCKER"
DIRECT_ADMIT_CRIT_STATUS_UNCHECKED = "UNCHECKED"

DIRECT_ADMIT_CRIT_STATUS_ORDER = [
    DIRECT_ADMIT_CRIT_STATUS_UNCHECKED,
    DIRECT_ADMIT_CRIT_STATUS_READY,
    DIRECT_ADMIT_CRIT_STATUS_PARTIAL,
    DIRECT_ADMIT_CRIT_STATUS_RISK,
    DIRECT_ADMIT_CRIT_STATUS_BLOCKER,
]

DIRECT_ADMIT_CRIT_STATUS_UI = {
    DIRECT_ADMIT_CRIT_STATUS_READY: ("ГОТОВО", "#2F6B4F"),
    DIRECT_ADMIT_CRIT_STATUS_PARTIAL: ("ЧАСТИЧНО", "#C4920A"),
    DIRECT_ADMIT_CRIT_STATUS_RISK: ("РИСК", "#C2410C"),
    DIRECT_ADMIT_CRIT_STATUS_BLOCKER: ("БЛОКЕР", "#B45353"),
    DIRECT_ADMIT_CRIT_STATUS_UNCHECKED: ("НЕ ПРОВЕРЕНО", "#64748b"),
}

DIRECT_ADMIT_OTHER_CRITERION_LABEL = "Другое ограничение"

DIRECT_ADMIT_CRITERIA_BY_DEPT: dict[str, list[str]] = {
    "Участок": [
        "Фронт работ передан",
        "Стройготовность обеспечена",
        "Смежники не блокируют",
        "Доступ к зоне обеспечен",
        "Леса / подмости готовы",
        "Подъёмные механизмы доступны",
        "Инструмент и оснастка доступны",
        "Бригада укомплектована",
        "Критические простои отсутствуют",
        "Производственный маршрут выполним",
        "Другое ограничение",
    ],
    "ПТО": [
        "Актуальная РД выдана в производство работ",
        "Пакет работ IWP сформирован и доступен",
        "Расхождения и неточности в проектной документации проверены",
        "Сопроводительная документация на МТР для входного контроля получена",
        "Ведомость объёмов сверена с актуальной РД",
        "Технические запросы и согласования по данному коду не блокируют выполнение работ",
        "Узлы, детали и проектные решения достаточны для выполнения работ",
        "Исполнительная документация и требования к оформлению работ понятны",
        "Другое ограничение",
    ],
    "МТО": [
        "Критический МТР обеспечен",
        "Комплектность МТР подтверждена",
        "Длительно поставляемые позиции обеспечены",
        "МТР доставлены в зону",
        "Входной контроль пройден",
        "Паспорта/сертификаты доступны",
        "Дефицитных позиций нет",
        "Буфер материалов достаточен",
        "Оснастка/расходники обеспечены",
        "Риск дефицита отсутствует",
        "Другое ограничение",
    ],
    "QAQC": [
        "Критерии качества понятны",
        "План инспекций и требования к приёмке доступны",
        "Точки контроля и освидетельствования определены",
        "Возможность предъявления обеспечена",
        "Предыдущий этап принят",
        "Блокирующих записей о несоответствии нет",
        "Инспекция доступна",
        "Готовность пакета испытаний подтверждена",
        "Документация качества готова",
        "Критическое удержание по качеству отсутствует",
        "Другое ограничение",
    ],
    "ОТиТБ": [
        "Наряд-допуск действителен",
        "Риски и оценка безопасности работ согласованы",
        "Рабочая зона безопасна",
        "Огневой допуск активен",
        "Подъёмные операции согласованы",
        "Блокировка и маркировка оборудования подтверждена",
        "Замечания по ОТиТБ отсутствуют",
        "Аварийная готовность обеспечена",
        "Обязательный надзор назначен",
        "Блокирующих замечаний по ОТиТБ нет",
        "Другое ограничение",
    ],
    "Коммерческий отдел": [
        "Объём работ официально выдан",
        "Доступ официально предоставлен",
        "Ограничение формально зафиксировано",
        "Неурегулированных изменений нет",
        "Зависимость от заказчика снята",
        "Платёжных ограничений нет",
        "Все согласования получены",
        "Контрактный риск допустим",
        "Событие задержки зафиксировано",
        "Блокирующей переписки нет",
        "Другое ограничение",
    ],
    "ПНР": [
        "Механическая готовность подтверждена",
        "Перечень доработок допустим",
        "Электропитание подано",
        "Автоматика готова",
        "Утилиты доступны",
        "Поддержка поставщика оборудования подтверждена",
        "Среда испытаний доступна",
        "Предпусконаладочные работы завершены",
        "Документация готова",
        "Последовательность запуска утверждена",
        "Другое ограничение",
    ],
}

DIRECT_ADMIT_CRITERIA_WARN_KEY = "direct_admit_criteria_warn"
DIRECT_ADMIT_DECISION_DRAFT_KEY = "direct_admit_decision_draft"
DIRECT_ADMIT_DECISION_FIO_ERROR_KEY = "direct_admit_decision_fio_error"
DIRECT_ADMIT_DECISION_WARN_KEY = "direct_admit_decision_warn"
DIRECT_ADMIT_DECISION_RECOMMENDED_KEY = "direct_admit_decision_recommended"
DIRECT_ADMIT_STATUS_PATCHES_KEY = "direct_admit_status_patches"

PACKAGE_STATUS_OPEN = "OPEN"
PACKAGE_STATUS_READY = "READY"
PACKAGE_STATUS_BLOCKED = "BLOCKED"

PACKAGE_STATUS_FILTER_OPTIONS = [
    "Все",
    PACKAGE_STATUS_OPEN,
    PACKAGE_STATUS_READY,
    PACKAGE_STATUS_BLOCKED,
]

PACKAGE_STATUS_RU = {
    PACKAGE_STATUS_OPEN: "🟡 Проверяется",
    PACKAGE_STATUS_READY: "🟢 Допущен к исполнению",
    PACKAGE_STATUS_BLOCKED: "🔴 Заблокирован",
}

PACKAGE_STATUS_TABLE_LABEL = {
    PACKAGE_STATUS_OPEN: "Проверяется",
    PACKAGE_STATUS_READY: "Допущено",
    PACKAGE_STATUS_BLOCKED: "Заблокировано",
}

ADMISSION_STATUS_TEXT_STYLE = {
    "Проверяется": "color: #2E5B9A;",
    "Допущено": "color: #2F6B4F;",
    "Заблокировано": "color: #9B3D3D;",
    "Требует уточнения": "color: #92610E;",
}

PACKAGE_STATUS_STYLE = {
    PACKAGE_STATUS_OPEN: "background-color: #E6EEF8; color: #2E5B9A;",
    PACKAGE_STATUS_READY: "background-color: #E7F5EE; color: #2F6B4F;",
    PACKAGE_STATUS_BLOCKED: "background-color: #FEE2E2; color: #B91C1C;",
}

ADMISSION_MAIN_TABLE_NUMERIC_COLUMNS = {
    "Объём",
    "Стоимость объёма",
    "Трудозатраты, чел·ч",
    "Людей в звене",
    "Длительность, смен",
    "Стоимость труда",
    "Труд / стоимость работ, %",
}

# TODO v2 persistence: system/iwp must be saved from 10B to monthly_plan_lines_v2.
V2_PLAN_LINE_BASE_COLUMNS = [
    "plan_line_id",
    "project_code",
    "month_key",
    "facility",
    "discipline",
    "boq_code",
    "boq_name",
    "unit",
    "planned_qty",
    "labor_hours",
    "labor_cost",
    "crew_size",
    "unit_price",
    "plan_value",
    "crew",
    "status",
    "sent_to_constraints_at",
]

V2_PLAN_LINE_OPTIONAL_COLUMNS = [
    "queue",
    "title",
    "system",
    "iwp",
    "planned_by",
    "planned_at",
]

CHECK_STATUS_PRIORITY = {
    "FAIL": 0,
    "HOLD": 1,
    "WARNING": 2,
    "ОЖИДАЕТ": 3,
    "PASS": 99,
}

PACKAGE_TABLE_COLUMNS_RU = {
    "package_status_ui": "Статус допуска",
    "bottleneck_summary": "Почему / узкое место",
    "who_holds_display": "Удерживает",
    "month_key": "Месяц",
    "project_code": "Проект",
    "queue_display": "Очередь",
    "title_display": "Титул",
    "discipline_display": "Дисциплина",
    "boq_code": "BOQ-код",
    "boq_name": "Наименование",
    "crew_display": "Звено",
    "planned_qty_display": "Объём",
    "unit_display": "Ед.",
    "required_hours_display": "Часы",
    "plan_value_display": "Стоимость",
    "waiting_checks_count": "Ожидают",
    "blocked_checks_count": "Блок",
    "sent_to_constraints_display": "Передано в допуск, МСК",
    "short_line_id": "ID строки",
}

ADMISSION_MAIN_TABLE_COLUMNS = [
    "package_status_ui",
    "project_code",
    "queue_display",
    "title_display",
    "discipline_display",
    "system_display",
    "iwp_display",
    "boq_code",
    "boq_name",
    "unit_display",
    "planned_qty_display",
    "plan_value_display",
    "required_hours_display",
    "crew_size_display",
    "duration_shifts_display",
    "labor_cost_display",
    "labor_to_plan_pct_display",
    "crew_display",
    "who_holds_display",
    "planned_by_display",
    "sent_to_constraints_display",
]

ADMISSION_MAIN_TABLE_COLUMNS_RU = {
    "project_code": "Проект",
    "queue_display": "Очередь",
    "title_display": "Титул",
    "discipline_display": "Дисциплина",
    "system_display": "Система",
    "iwp_display": "IWP",
    "boq_code": "BOQ код",
    "boq_name": "Наименование работ",
    "unit_display": "Ед.",
    "planned_qty_display": "Объём",
    "plan_value_display": "Стоимость объёма",
    "required_hours_display": "Трудозатраты, чел·ч",
    "crew_size_display": "Людей в звене",
    "duration_shifts_display": "Длительность, смен",
    "labor_cost_display": "Стоимость труда",
    "labor_to_plan_pct_display": "Труд / стоимость работ, %",
    "crew_display": "Звено",
    "package_status_ui": "Статус допуска",
    "who_holds_display": "Удерживает",
    "planned_by_display": "Кто запланировал",
    "planned_date_display": "Дата планирования",
    "planned_time_msk_display": "Время планирования МСК",
    "sent_to_constraints_display": "Передано в допуск, МСК",
}

AUTO_SCHEDULE_PREFIX = "[AUTO] Срок перенесён"

RESPONSIBILITY_SIDE_OPTIONS = [
    "Не определено",
    "Наша организация / Субподрядчик",
    "Генподрядчик",
    "Заказчик",
    "Проектировщик",
    "Поставщик / Вендор",
    "Технический надзор",
]

OWNER_ROLE_PRESETS = [
    "Руководитель проекта",
    "Руководитель строительства",
    "Начальник участка",
    "Мастер",
    "Инженер ПТО",
    "Руководитель ПТО",
    "Инженер МТО",
    "Руководитель МТО",
    "Инженер ОТиТБ",
    "Инженер QA/QC",
    "Представитель заказчика",
    "Представитель генподрядчика",
    "Представитель проектировщика",
    "Представитель поставщика / вендора",
    "Коммерческий менеджер",
    "Другое",
    "Не требуется",
]

OWNER_NAME_PRESETS = [
    "Не назначен",
    "Не требуется",
    "Храпов Алексей",
    "Масимов Виктор",
    "Руководитель ПТО",
    "Руководитель МТО",
    "Начальник участка",
    "Представитель заказчика",
    "Представитель генподрядчика",
    "Другое",
]

GATE_LAYER_RU = {
    "EXECUTABILITY": "Исполнимый фронт",
    "ACCEPTABILITY": "Признаваемость",
    "CREW_ECONOMICS": "Экономика звена",
}

CHECK_STATUS_RU = {
    "ОЖИДАЕТ": "Ожидает проверки",
    "PASS": "Пройдено",
    "WARNING": "Риск / требуется уточнение",
    "HOLD": "Удержание / блокировка",
    "FAIL": "Не пройдено",
}

RESOLUTION_RU = {
    "OPEN": "Открыто",
    "IN_PROGRESS": "В работе",
    "RESOLVED": "Закрыто",
    "CANCELLED": "Отменено",
}

SEVERITY_RU = {
    "LOW": "Низкая",
    "MEDIUM": "Средняя",
    "HIGH": "Высокая",
    "CRITICAL": "Критическая",
}

CHECK_STATUS_OPTIONS = ["ОЖИДАЕТ", "PASS", "WARNING", "HOLD", "FAIL"]
RESOLUTION_OPTIONS = ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"]
SEVERITY_OPTIONS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

DEPARTMENT_RU = {
    "Участок": "Линейное управление / Field Construction Management",
    "ПТО": "ПТО / Engineering & Work Packaging",
    "МТО": "МТО / Procurement & Materials",
    "ОТиТБ": "HSE / ОТиПБ",
    "QAQC": "QA/QC",
    "Коммерческий отдел": "Коммерческий контроль / Contract & Commercial",
    "Руководство": "Проектное управление / Project Management",
}

CATEGORY_BY_DEPARTMENT: Dict[str, List[str]] = {
    "ПТО": [
        "РД не выдана",
        "РД не актуальна / устаревшая ревизия",
        "Нет IWP / пакет работ не сформирован",
        "Нет Work Package / методики выполнения",
        "Не подтверждён объём BOQ",
        "Несоответствие BOQ и РД",
        "Не согласованы изменения",
        "Нет ответа на RFI",
        "Нет исполнительной схемы",
        "Нет As-built основы",
        "Нет акта скрытых работ",
        "Нет привязки к системе / зоне",
        "Несоответствие РД и фактического фронта",
        "Другое",
    ],
    "МТО": [
        "Материал не поставлен",
        "Оборудование не поставлено",
        "Нет сертификатов / паспортов",
        "Не выполнен входной контроль",
        "Материал не тот / пересорт",
        "Нет крепежа / расходников",
        "Нет складского подтверждения",
        "Нет комплектации по системе",
        "Нет логистики до зоны работ",
        "Поставка обещана, но просрочена",
        "Материал зарезервирован под другой фронт",
        "Другое",
    ],
    "Участок": [
        "Фронт физически не открыт",
        "Смежники мешают",
        "Нет доступа в зону",
        "Нет лесов / подмостей / подъёмника",
        "Нет техники / механизации",
        "Зона не подготовлена",
        "Нет людей / звена",
        "Нет мастера / ответственного",
        "Невозможно безопасно выполнить",
        "Не завершены предшествующие работы",
        "Другое",
    ],
    "ОТиТБ": [
        "Нет наряда-допуска",
        "Нет допуска персонала",
        "Нет инструктажа",
        "Нет безопасных условий",
        "Нет ограждений / знаков",
        "Работы повышенной опасности не согласованы",
        "Нет СИЗ / спецусловий",
        "Нет ППР / технологической карты для опасных работ",
        "Нет допуска к высотным работам",
        "Другое",
    ],
    "QAQC": [
        "Нет ИТП / плана контроля",
        "Не определена точка инспекции",
        "Нет возможности предъявить качество",
        "Нет актов скрытых работ",
        "Нет протоколов испытаний",
        "Нет подтверждения ВИК / контроля",
        "Требуется инспекция заказчика",
        "Нет чек-листа контроля",
        "Нет лабораторного / инструментального подтверждения",
        "Другое",
    ],
    "Коммерческий отдел": [
        "Нет основания для предъявления",
        "Нет ДС / изменение не оформлено",
        "Объём не признаётся заказчиком",
        "Работа вне BOQ",
        "Нет подтверждающих документов",
        "Риск отказа в КС",
        "Нет подписанного акта / протокола",
        "Нет коммерческого основания для оплаты",
        "Не подтверждена цена / расценка",
        "Другое",
    ],
    "Руководство": [
        "Недостаточно людей",
        "Перегруз звена",
        "Норма выработки не подтверждена",
        "Высокая себестоимость",
        "Отрицательная маржа",
        "Недостаточно часов до конца месяца",
        "Не подтверждён состав звена",
        "Работа не приоритетна по Critical Value Path",
        "Нет управленческого решения по запуску",
        "Другое",
    ],
}

ADMISSION_INFO = (
    "Страница объединяет три контура допуска:\n"
    "1) **Исполнимый фронт** — можно ли физически выполнить работу.\n"
    "2) **Признаваемость** — можно ли довести работу до инспекции, признания, "
    "предъявления и закрытия объёма.\n"
    "3) **Экономика звена** — можно ли выполнить без убытка."
)

BOQ_MULTI_CONSTRAINT_INFO = (
    "Один BOQ-код может иметь несколько ограничений в разных контурах: исполнимый фронт, "
    "признаваемость, экономика звена. У одного подразделения также может быть несколько "
    "проверок по одной BOQ-строке (например, ПТО — и по РД/IWP, и по признаваемости "
    "исполнительной документации)."
)

TABLE_COLUMNS = [
    "check_status",
    "project_code",
    "month_key",
    "boq_code",
    "boq_name",
    "responsible_department",
    "gate_layer",
    "check_name",
    "severity",
    "resolution_status",
    "owner_name",
    "target_resolution_date",
    "days_overdue",
    "value_at_risk_display",
    "updated_by",
    "comment",
]

TABLE_COLUMNS_RU = {
    "project_code": "Проект",
    "month_key": "Месяц",
    "boq_code": "BOQ-код",
    "boq_name": "Наименование работы",
    "responsible_department": "Отдел",
    "gate_layer": "Контур допуска",
    "check_name": "Проверка",
    "check_status": "Статус проверки",
    "severity": "Критичность",
    "resolution_status": "Статус устранения",
    "owner_name": "Владелец",
    "target_resolution_date": "Срок закрытия",
    "days_overdue": "Просрочка, дней",
    "value_at_risk_display": "Стоимость под риском",
    "updated_by": "Кто обновил",
    "comment": "Комментарий",
}

CHECK_STATUS_BG_RU = {
    "Ожидает проверки": "background-color: #f3f4f6;",
    "Пройдено": "background-color: #dcfce7;",
    "Риск / требуется уточнение": "background-color: #fef9c3;",
    "Удержание / блокировка": "background-color: #ffedd5;",
    "Не пройдено": "background-color: #fee2e2;",
}

DECISION_REGISTRY_CHECK_STATUS_DISPLAY: Dict[str, str] = {
    "Ожидает проверки": "ПРОВЕРЯЕТСЯ",
    "ОЖИДАЕТ": "ПРОВЕРЯЕТСЯ",
    "Пройдено": "ПРОЙДЕНО",
    "PASS": "ПРОЙДЕНО",
    "Риск / требуется уточнение": "УТОЧНЕНИЕ",
    "WARNING": "УТОЧНЕНИЕ",
    "Удержание / блокировка": "ЗАБЛОКИРОВАНО",
    "HOLD": "ЗАБЛОКИРОВАНО",
    "Не пройдено": "НЕ ПРОЙДЕНО",
    "FAIL": "НЕ ПРОЙДЕНО",
}

DECISION_REGISTRY_VALUE_COLUMN_RU = "Стоимость под решением"

DECISION_REGISTRY_TABLE_COLUMNS = [
    "check_status",
    "month_display",
    "boq_code",
    "boq_name",
    "system_display",
    "iwp_display",
    "responsible_department",
    "updated_by",
    "decision_at_display",
    "constraint_reason_display",
    "target_resolution_date",
    "severity",
    "owner_name",
]

DECISION_REGISTRY_TABLE_COLUMNS_RU = {
    "check_status": "Статус проверки",
    "month_display": "Месяц",
    "boq_code": "BOQ-код",
    "boq_name": "Наименование",
    "system_display": "Система",
    "iwp_display": "Пакет работ / IWP",
    "responsible_department": "Отдел",
    "updated_by": "Последнее обновление внёс",
    "decision_at_display": "Дата решения",
    "constraint_reason_display": "Причина / суть ограничения",
    "target_resolution_date": "Срок устранения",
    "severity": "Критичность",
    "owner_name": "Владелец решения",
}

DECISION_REGISTRY_MONTH_FIELDS = ("month_key", "Month_Key", "Year_Quarter_Month_Week_ID")

DECISION_REGISTRY_SYSTEM_FIELDS = (
    "system",
    "system_label",
    "system_label_iwp",
)

DECISION_REGISTRY_IWP_FIELDS = (
    "iwp",
    "iwp_id",
    "iwp_id_export",
    "package_name",
    "work_package",
)

DECISION_REGISTRY_NUMERIC_COLUMNS = {
    "Объём месяца",
    "Стоимость объёма",
    "Трудозатраты, чел·ч",
    "Людей в звене",
    "Длительность, смен",
    "Стоимость труда",
    "Труд / стоимость работ, %",
    DECISION_REGISTRY_VALUE_COLUMN_RU,
}

DECISION_REGISTRY_CHECK_STATUS_TEXT_STYLE = {
    "ПРОВЕРЯЕТСЯ": ADMISSION_STATUS_TEXT_STYLE["Проверяется"],
    "ПРОЙДЕНО": ADMISSION_STATUS_TEXT_STYLE["Допущено"],
    "УТОЧНЕНИЕ": ADMISSION_STATUS_TEXT_STYLE["Требует уточнения"],
    "ЗАБЛОКИРОВАНО": ADMISSION_STATUS_TEXT_STYLE["Заблокировано"],
    "НЕ ПРОЙДЕНО": ADMISSION_STATUS_TEXT_STYLE["Заблокировано"],
}

ADMISSION_SHARED_TABLE_COLUMN_WIDTHS: dict[str, str] = {
    "Статус проверки": "small",
    "Статус допуска": "small",
    "Проект": "small",
    "Месяц": "small",
    "Очередь": "small",
    "Дисциплина": "medium",
    "Система": "medium",
    "IWP": "medium",
    "BOQ код": "small",
    "BOQ-код": "small",
    "Наименование работ": "large",
    "Наименование работы": "large",
    "Отдел": "medium",
    "Контур допуска": "medium",
    "Проверка": "medium",
    "Трудозатраты, чел·ч": "small",
    "Людей в звене": "small",
    "Длительность, смен": "small",
    "Стоимость труда": "medium",
    "Труд / стоимость работ, %": "small",
    "Владелец решения": "medium",
    DECISION_REGISTRY_VALUE_COLUMN_RU: "medium",
    "Последнее обновление внёс": "medium",
    "Комментарий": "large",
}

ADMISSION_PLAN_LIST_COLUMN_WIDTHS: dict[str, str] = {
    **ADMISSION_SHARED_TABLE_COLUMN_WIDTHS,
    "Титул": "medium",
    "Ед.": "small",
    "Объём": "small",
    "Стоимость объёма": "medium",
    "Звено": "small",
    "Удерживает": "medium",
    "Кто запланировал": "medium",
    "Передано в допуск, МСК": "medium",
}


def build_admission_table_column_config(
    display_df: pd.DataFrame,
    width_map: dict[str, str],
) -> dict[str, Any]:
    """Стабильные ширины колонок admission-таблиц через st.column_config."""
    config: dict[str, Any] = {}
    for col in display_df.columns:
        width = width_map.get(col)
        if width is not None:
            config[col] = st.column_config.TextColumn(col, width=width, disabled=True)
        else:
            config[col] = st.column_config.TextColumn(col, disabled=True)
    return config


def safe_str(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def safe_num(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0


def safe_date(value: Any) -> Optional[date]:
    if value is None or pd.isna(value) or safe_str(value) == "":
        return None
    try:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return pd.to_datetime(value).date()
    except Exception:  # noqa: BLE001
        return None


def money_ru(value: Any) -> str:
    """Единый денежный формат: 2 304 000,00 ₽"""
    try:
        if value is None or pd.isna(value):
            return "0,00 ₽"
        amount = float(value)
        sign = "-" if amount < 0 else ""
        amount = abs(amount)
        whole, frac = f"{amount:.2f}".split(".")
        whole_fmt = f"{int(whole):,}".replace(",", " ")
        return f"{sign}{whole_fmt},{frac} ₽"
    except Exception:  # noqa: BLE001
        return "0,00 ₽"


def money_ru_compact(value: Any) -> str:
    """Компактный формат для строк очереди: 242k ₽, 1,2M ₽."""
    amount = safe_num(value)
    if amount == 0:
        return "—"
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1_000_000:
        val = amount / 1_000_000
        text = f"{val:.1f}".replace(".", ",")
        return f"{sign}{text}M ₽"
    if amount >= 1_000:
        return f"{sign}{int(round(amount / 1_000))}k ₽"
    return money_ru(amount)


def display_dash(value: Any) -> str:
    text = safe_str(value)
    return text if text else "—"


def normalize_line_id(value: Any) -> str:
    return safe_str(value).lower()


def has_meaningful_value(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    return safe_str(value) != ""


def format_qty_display(value: Any) -> str:
    if not has_meaningful_value(value):
        return "—"
    return f"{safe_num(value):,.2f}".replace(",", " ").replace(".", ",")


def format_labor_hours_display(value: Any) -> str:
    hours = safe_num(value)
    if hours <= 0:
        return "—"
    return f"{hours:,.1f}".replace(",", " ")


def format_crew_size_display(value: Any) -> str:
    crew_size = int(max(safe_num(value), 0))
    if crew_size <= 0:
        return "—"
    return str(crew_size)


def compute_duration_shifts(labor_hours: Any, crew_size: Any) -> float:
    safe_hours = safe_num(labor_hours)
    if safe_hours <= 0:
        return 0.0
    safe_crew_raw = safe_num(crew_size)
    if safe_crew_raw <= 0:
        safe_crew = 1
    else:
        safe_crew = max(int(safe_crew_raw), 1)
    crew_day_capacity = safe_crew * ADMISSION_PRODUCTIVE_HOURS_PER_PERSON_SHIFT
    return safe_hours / crew_day_capacity


def format_duration_shifts_display(labor_hours: float, crew_size: float) -> str:
    duration = compute_duration_shifts(labor_hours, crew_size)
    if duration <= 0:
        return "—"
    return f"{duration:,.1f}".replace(",", " ").replace(".", ",") + " смен"


def append_v2_labor_display_columns(
    row: Dict[str, Any],
    v2_row: Dict[str, Any],
    *,
    fallback_labor_hours: float = 0.0,
) -> None:
    """Трудовой контур допуска — по логике конструктора 10B (crew_size, duration_shifts)."""
    labor_hours = (
        safe_num(v2_row.get("labor_hours"))
        if v2_row and v2_row.get("labor_hours") is not None
        else fallback_labor_hours
    )
    labor_cost = safe_num(v2_row.get("labor_cost")) if v2_row else 0.0
    plan_value = safe_num(row.get("plan_value"))
    if v2_row and v2_row.get("plan_value") is not None:
        plan_value = safe_num(v2_row.get("plan_value"))
    crew_size = 1
    if v2_row and v2_row.get("crew_size") is not None:
        crew_raw = safe_num(v2_row.get("crew_size"))
        crew_size = max(int(crew_raw), 1) if crew_raw > 0 else 1
    row["required_hours_display"] = format_labor_hours_display(labor_hours)
    row["crew_size_display"] = format_crew_size_display(crew_size)
    row["duration_shifts_display"] = format_duration_shifts_display(labor_hours, crew_size)
    row["labor_cost_display"] = format_money_display(labor_cost)
    labor_to_plan_pct = labor_cost / plan_value * 100.0 if plan_value > 0 else 0.0
    row["labor_to_plan_pct_display"] = format_labor_to_plan_pct_display(
        labor_to_plan_pct, plan_value
    )


def format_labor_to_plan_pct_display(pct: float, plan_value: float) -> str:
    if plan_value <= 0:
        return "—"
    return f"{pct:.1f}".replace(".", ",") + " %"


def format_money_display(value: Any) -> str:
    amount = safe_num(value)
    if amount <= 0:
        return "—"
    return money_ru(amount)


def format_datetime_ru(value: Any) -> str:
    if value is None or pd.isna(value) or safe_str(value) == "":
        return "—"
    try:
        return pd.to_datetime(value).strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return "—"


def format_date_ru(value: date | None) -> str:
    if value is None:
        return "—"
    return value.strftime("%d.%m.%Y")


def format_date_any_ru(value: Any) -> str:
    return format_date_ru(safe_date(value))


def get_write_client() -> Optional[Client]:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def reverse_map(mapping: Dict[str, str]) -> Dict[str, str]:
    return {v: k for k, v in mapping.items()}


def dept_ui(db_value: Any) -> str:
    return DEPARTMENT_RU.get(safe_str(db_value), safe_str(db_value))


def dept_db(ui_value: str) -> str:
    return reverse_map(DEPARTMENT_RU).get(ui_value.strip(), ui_value.strip())


def plan_line_key(row: pd.Series) -> str:
    line_id = safe_str(row.get("line_id"))
    if line_id:
        return f"line:{line_id}"
    parts = [
        safe_str(row.get("project_code")),
        safe_str(row.get("month_key")),
        safe_str(row.get("facility_building")),
        safe_str(row.get("construction_discipline")),
        safe_str(row.get("boq_code")),
        safe_str(row.get("crew_id")),
    ]
    return "composite:" + "|".join(parts)


def package_key_from_row(row: pd.Series) -> str:
    line_id = safe_str(row.get("line_id"))
    if line_id:
        return f"line:{line_id}"
    return plan_line_key(row)


def short_line_id(line_id: Any, package_key: str) -> str:
    raw = safe_str(line_id)
    if raw:
        return raw[:8] if len(raw) > 8 else raw
    suffix = package_key.split(":", 1)[-1]
    return suffix[:12] if suffix else "—"


def compute_package_status(group: pd.DataFrame) -> str:
    statuses: List[str] = []
    for _, row in group.iterrows():
        statuses.append(norm_check_status_key(row.get("check_status")))
    if any(status in ("HOLD", "FAIL") for status in statuses):
        return PACKAGE_STATUS_BLOCKED
    if statuses and all(status == "PASS" for status in statuses):
        return PACKAGE_STATUS_READY
    return PACKAGE_STATUS_OPEN


def compute_bottleneck_department(group: pd.DataFrame) -> str:
    best_dept = ""
    best_prio = 999
    for _, row in group.iterrows():
        status = norm_check_status_key(row.get("check_status"))
        prio = CHECK_STATUS_PRIORITY.get(status, 50)
        if prio < best_prio:
            best_prio = prio
            best_dept = safe_str(row.get("responsible_department"))
    return best_dept


def find_blocking_check(group: pd.DataFrame) -> Optional[pd.Series]:
    best_row: Optional[pd.Series] = None
    best_prio = 999
    for _, row in group.iterrows():
        status = norm_check_status_key(row.get("check_status"))
        if status not in ("HOLD", "FAIL"):
            continue
        prio = CHECK_STATUS_PRIORITY.get(status, 50)
        if prio < best_prio:
            best_prio = prio
            best_row = row
    return best_row


def compute_waiting_departments(group: pd.DataFrame) -> List[str]:
    departments: List[str] = []
    for _, row in group.iterrows():
        status = norm_check_status_key(row.get("check_status"))
        if status not in ("ОЖИДАЕТ", "WARNING"):
            continue
        dept = safe_str(row.get("responsible_department"))
        if dept and dept not in departments:
            departments.append(dept)
    return departments


def format_waiting_checks_label(count: int) -> str:
    n = max(int(count), 0)
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} проверка ожидает"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return f"{n} проверки ожидают"
    return f"{n} проверок ожидает"


def compute_package_clarity(
    group: pd.DataFrame,
    package_status: str,
    waiting_checks_count: int,
    blocked_checks_count: int,
    fallback_department: str,
) -> Dict[str, str]:
    blocking_row = find_blocking_check(group)
    blocking_department = (
        safe_str(blocking_row.get("responsible_department"))
        if blocking_row is not None
        else fallback_department
    )
    blocking_check_name = (
        safe_str(blocking_row.get("check_name")) if blocking_row is not None else ""
    )
    blocking_department_ui = dept_ui(blocking_department) if blocking_department else "—"
    waiting_departments = compute_waiting_departments(group)
    waiting_departments_label = ", ".join(dept_ui(d) for d in waiting_departments[:4])

    if package_status == PACKAGE_STATUS_BLOCKED:
        blocking_reason = f"🔴 Заблокирован: {blocking_department_ui}"
        bottleneck_summary = blocking_department_ui
        who_holds = blocking_department_ui
    elif package_status == PACKAGE_STATUS_READY:
        blocking_reason = "🟢 Все проверки пройдены"
        bottleneck_summary = "Все проверки пройдены"
        who_holds = "—"
    else:
        waiting_label = format_waiting_checks_label(waiting_checks_count)
        blocking_reason = f"🟡 Проверяется: {waiting_label}"
        if waiting_departments_label:
            bottleneck_summary = waiting_departments_label
        elif waiting_checks_count > 0:
            bottleneck_summary = waiting_label
        else:
            bottleneck_summary = "Проверяется"
        who_holds = "Проверяется"

    return {
        "blocking_reason": blocking_reason,
        "blocking_department": blocking_department,
        "blocking_check_name": blocking_check_name,
        "bottleneck_summary": bottleneck_summary,
        "who_holds_display": who_holds,
        "waiting_departments_label": waiting_departments_label,
    }


def build_package_dataframe(constraints_df: pd.DataFrame) -> pd.DataFrame:
    """Одна строка плана / пакет = одна строка (группировка по line_id или legacy key)."""
    if constraints_df.empty:
        return pd.DataFrame()

    working = constraints_df.copy()
    working["_package_key"] = working.apply(package_key_from_row, axis=1)

    packages: List[Dict[str, Any]] = []
    for package_key, group in working.groupby("_package_key", sort=False):
        first = group.iloc[0]
        line_id = safe_str(first.get("line_id")) or None
        statuses = [norm_check_status_key(row.get("check_status")) for _, row in group.iterrows()]

        total_checks = len(group)
        blocked_checks = sum(1 for status in statuses if status in ("HOLD", "FAIL"))
        passed_checks = sum(1 for status in statuses if status == "PASS")
        open_checks = sum(
            1 for status in statuses if status in ("ОЖИДАЕТ", "WARNING")
        )
        plan_value = row_risk_value(first)
        required_hours = safe_num(first.get("required_hours"))

        package_status = compute_package_status(group)
        bottleneck = compute_bottleneck_department(group)
        clarity = compute_package_clarity(
            group,
            package_status,
            open_checks,
            blocked_checks,
            bottleneck,
        )

        packages.append(
            {
                "package_key": package_key,
                "line_id": line_id,
                "project_code": safe_str(first.get("project_code")),
                "month_key": safe_str(first.get("month_key")),
                "facility_building": safe_str(first.get("facility_building")),
                "construction_discipline": safe_str(first.get("construction_discipline")),
                "boq_code": safe_str(first.get("boq_code")),
                "boq_name": safe_str(first.get("boq_name")),
                "crew_id": safe_str(first.get("crew_id")),
                "required_hours": required_hours,
                "plan_value": plan_value,
                "total_checks": total_checks,
                "open_checks": open_checks,
                "blocked_checks": blocked_checks,
                "passed_checks": passed_checks,
                "waiting_checks_count": open_checks,
                "blocked_checks_count": blocked_checks,
                "package_status": package_status,
                "bottleneck_department": bottleneck,
                "short_line_id": short_line_id(line_id, package_key),
                **clarity,
            }
        )

    result = pd.DataFrame(packages)
    if result.empty:
        return result

    result["package_status_ui"] = result["package_status"].map(
        lambda v: PACKAGE_STATUS_RU.get(str(v), str(v))
    )
    return result


def field_display(value: Any) -> str:
    text = safe_str(value)
    return text if text else "—"


def derive_construction_queue_from_facility(facility: str) -> str:
    text = str(facility or "")
    if "16160-13" in text or "16160-17" in text:
        return "1 очередь"
    if "26160-13" in text or "26160-17" in text:
        return "2 очередь"
    return "Не определено"


def format_datetime_moscow(value: Any) -> str:
    if value is None or pd.isna(value) or safe_str(value) == "":
        return "—"
    try:
        parsed = pd.to_datetime(value, utc=True)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize(timezone.utc)
        moscow = parsed.tz_convert(ZoneInfo("Europe/Moscow"))
        return moscow.strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return "—"


def format_planned_date_moscow(value: Any) -> str:
    """Дата планирования (МСК) для таблицы допуска."""
    formatted = format_datetime_moscow(value)
    if formatted == "—":
        return "—"
    return formatted.split(" ", 1)[0]


def format_planned_time_moscow(value: Any) -> str:
    """Время планирования (МСК) для таблицы допуска."""
    formatted = format_datetime_moscow(value)
    if formatted == "—" or " " not in formatted:
        return "—"
    return f"{formatted.split(' ', 1)[1]} МСК"


def now_moscow_text() -> str:
    return datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M MSK")


def now_moscow_decision_text() -> str:
    return datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК")


def append_action_comment(existing: str, line: str) -> str:
    base = (existing or "").strip()
    return f"{base}\n{line}".strip() if base else line


def last_decision_display(row: pd.Series) -> str:
    updated_by = audit_last_updated_by(row)
    last_at = audit_last_updated_at(row)
    if updated_by and last_at is not None and not pd.isna(last_at):
        return f"{updated_by}, {format_datetime_moscow(last_at)}"
    if updated_by:
        return updated_by
    if last_at is not None and not pd.isna(last_at):
        return format_datetime_moscow(last_at)
    return "—"


def _merge_v2_plan_line_rows(
    merged: Dict[str, Dict[str, Any]],
    rows: List[Dict[str, Any]],
) -> None:
    for row in rows:
        key = normalize_line_id(row.get("plan_line_id"))
        if not key:
            continue
        if key not in merged:
            merged[key] = dict(row)
            continue
        for field, value in row.items():
            if has_meaningful_value(value):
                merged[key][field] = value


@st.cache_data(ttl=300)
def load_v2_plan_lines_for_constraints(line_ids: Tuple[str, ...]) -> pd.DataFrame:
    """Join key: monthly_plan_constraints.line_id = monthly_plan_lines_v2.plan_line_id."""
    unique_ids = [line_id for line_id in dict.fromkeys(line_ids) if safe_str(line_id)]
    if not unique_ids:
        return pd.DataFrame()

    merged: Dict[str, Dict[str, Any]] = {}
    chunk_size = 200

    for offset in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[offset : offset + chunk_size]
        try:
            response = (
                supabase.table(V2_PLAN_LINES_TABLE)
                .select(",".join(V2_PLAN_LINE_BASE_COLUMNS))
                .in_("plan_line_id", chunk)
                .execute()
            )
            _merge_v2_plan_line_rows(merged, response.data or [])
        except Exception:  # noqa: BLE001
            continue

        for optional_col in V2_PLAN_LINE_OPTIONAL_COLUMNS:
            try:
                response = (
                    supabase.table(V2_PLAN_LINES_TABLE)
                    .select(f"plan_line_id,{optional_col}")
                    .in_("plan_line_id", chunk)
                    .execute()
                )
                _merge_v2_plan_line_rows(merged, response.data or [])
            except Exception:  # noqa: BLE001
                # TODO v2 persistence: system/iwp must be saved from 10B to monthly_plan_lines_v2.
                continue

    if not merged:
        return pd.DataFrame()
    return pd.DataFrame(list(merged.values()))


def enrich_packages_with_v2_lines(
    packages_df: pd.DataFrame,
    v2_df: pd.DataFrame,
) -> pd.DataFrame:
    if packages_df.empty:
        return packages_df

    v2_lookup: Dict[str, Dict[str, Any]] = {}
    if not v2_df.empty and "plan_line_id" in v2_df.columns:
        for _, row in v2_df.iterrows():
            key = normalize_line_id(row.get("plan_line_id"))
            if key:
                v2_lookup[key] = row.to_dict()

    enriched_rows: List[Dict[str, Any]] = []
    for _, pkg in packages_df.iterrows():
        line_id = safe_str(pkg.get("line_id"))
        v2_row = v2_lookup.get(normalize_line_id(line_id), {})

        facility_v2 = safe_str(v2_row.get("facility"))
        title = (
            safe_str(v2_row.get("title"))
            or facility_v2
            or safe_str(pkg.get("facility_building"))
        )
        queue = safe_str(v2_row.get("queue"))
        if not queue:
            queue = derive_construction_queue_from_facility(title or facility_v2)
        discipline = safe_str(v2_row.get("discipline")) or safe_str(
            pkg.get("construction_discipline")
        )
        crew = safe_str(v2_row.get("crew")) or safe_str(pkg.get("crew_id"))
        planned_qty = v2_row.get("planned_qty") if v2_row else None
        unit = safe_str(v2_row.get("unit")) if v2_row else ""
        plan_value = safe_num(pkg.get("plan_value"))
        if v2_row and v2_row.get("plan_value") is not None:
            plan_value = safe_num(v2_row.get("plan_value"))
        sent_at = v2_row.get("sent_to_constraints_at") if v2_row else None
        planned_by = safe_str(v2_row.get("planned_by")) if v2_row else ""
        planned_at = v2_row.get("planned_at") if v2_row else None

        row = pkg.to_dict()
        row["queue_display"] = field_display(queue) if queue else "—"
        row["title_display"] = field_display(title)
        row["discipline_display"] = field_display(discipline)
        # TODO v2 persistence: system/iwp must be saved from 10B to monthly_plan_lines_v2.
        row["system_display"] = field_display(v2_row.get("system")) if v2_row else "—"
        row["iwp_display"] = field_display(v2_row.get("iwp")) if v2_row else "—"
        row["crew_display"] = field_display(crew)
        row["unit_display"] = field_display(unit)
        row["planned_qty_display"] = format_qty_display(planned_qty)
        row["plan_value"] = plan_value
        row["plan_value_display"] = format_money_display(plan_value)
        append_v2_labor_display_columns(
            row,
            v2_row,
            fallback_labor_hours=safe_num(pkg.get("required_hours")),
        )
        row["sent_to_constraints_display"] = (
            format_datetime_moscow(sent_at) if has_meaningful_value(sent_at) else "—"
        )
        row["planned_by_display"] = field_display(planned_by) if planned_by else "—"
        row["planned_date_display"] = format_planned_date_moscow(planned_at)
        row["planned_time_msk_display"] = format_planned_time_moscow(planned_at)
        row["package_status_ui"] = PACKAGE_STATUS_RU.get(
            safe_str(row.get("package_status")),
            safe_str(row.get("package_status")),
        )
        enriched_rows.append(row)

    return pd.DataFrame(enriched_rows)


def enrich_decision_registry_with_v2_lines(
    registry_df: pd.DataFrame,
    v2_df: pd.DataFrame,
) -> pd.DataFrame:
    """Добавляет поля строки плана v2 для реестра решений (по line_id ограничения)."""
    if registry_df.empty:
        return registry_df

    v2_lookup: Dict[str, Dict[str, Any]] = {}
    if not v2_df.empty and "plan_line_id" in v2_df.columns:
        for _, row in v2_df.iterrows():
            key = normalize_line_id(row.get("plan_line_id"))
            if key:
                v2_lookup[key] = row.to_dict()

    enriched_rows: List[Dict[str, Any]] = []
    for _, constraint in registry_df.iterrows():
        line_id = safe_str(constraint.get("line_id"))
        v2_row = v2_lookup.get(normalize_line_id(line_id), {})

        facility_v2 = safe_str(v2_row.get("facility"))
        title = (
            safe_str(v2_row.get("title"))
            or facility_v2
            or safe_str(constraint.get("facility_building"))
        )
        queue = safe_str(v2_row.get("queue"))
        if not queue:
            queue = derive_construction_queue_from_facility(title or facility_v2)
        discipline = safe_str(v2_row.get("discipline")) or safe_str(
            constraint.get("construction_discipline")
        )
        plan_value = safe_num(constraint.get("plan_value"))
        if v2_row and v2_row.get("plan_value") is not None:
            plan_value = safe_num(v2_row.get("plan_value"))
        crew_code = safe_str(v2_row.get("crew")) or safe_str(constraint.get("crew_id"))
        planned_qty = v2_row.get("planned_qty") if v2_row else None

        row = constraint.to_dict()
        row["plan_value"] = plan_value
        row["queue_display"] = field_display(queue) if queue else "—"
        row["discipline_display"] = field_display(discipline)
        row["system_display"] = format_registry_system_display(row, v2_row)
        row["iwp_display"] = format_registry_iwp_display(row, v2_row)
        row["month_display"] = format_registry_month_display(row, v2_row)
        row["planned_qty_month_display"] = format_qty_display(planned_qty)
        row["plan_value_month_display"] = format_money_display(plan_value)
        row["crew_code_display"] = field_display(crew_code) if crew_code else "—"
        row["constraint_reason_display"] = format_registry_constraint_reason_display(row)
        row["decision_at_display"] = format_registry_decision_at_display(row)
        append_v2_labor_display_columns(
            row,
            v2_row,
            fallback_labor_hours=safe_num(constraint.get("required_hours")),
        )
        enriched_rows.append(row)

    return pd.DataFrame(enriched_rows)


def month_filter_options(packages_df: pd.DataFrame) -> List[str]:
    data_months: List[str] = []
    if not packages_df.empty and "month_key" in packages_df.columns:
        data_months = [
            month
            for month in packages_df["month_key"].dropna().astype(str).str.strip().unique()
            if month
        ]
    merged = list(dict.fromkeys([*PLANNING_MONTH_OPTIONS, *sorted(data_months)]))
    return ["Все"] + merged


def package_filter_options(packages_df: pd.DataFrame, col: str) -> List[str]:
    if packages_df.empty or col not in packages_df.columns:
        return ["Все"]
    vals = packages_df[col].astype(str).str.strip()
    vals = vals[(vals != "") & (vals != "—")].unique().tolist()
    return ["Все"] + sorted(vals)


def apply_constraint_prefilters(
    df: pd.DataFrame,
    overdue_only: bool,
) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    if overdue_only and "is_overdue" in result.columns:
        result = result[result["is_overdue"].astype(bool)]
    return result


def apply_queue_filters(
    df: pd.DataFrame,
    department: str,
    check_status: str,
    overdue_only: bool,
) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    if department != "Все" and "responsible_department" in result.columns:
        result = result[result["responsible_department"].astype(str) == department]
    if check_status != "Все" and "check_status" in result.columns:
        result = result[
            result["check_status"].astype(str).apply(norm_check_status_key) == check_status
        ]
    if overdue_only and "is_overdue" in result.columns:
        result = result[result["is_overdue"].astype(bool)]
    return result


def filter_decision_registry_df(
    scope_df: pd.DataFrame,
    department: str,
    check_status: str,
    overdue_only: bool,
) -> pd.DataFrame:
    """Реестр решений: scope_df уже отфильтрован по пакетам страницы + фильтры очереди."""
    return apply_queue_filters(scope_df, department, check_status, overdue_only)


def apply_package_filters(
    packages_df: pd.DataFrame,
    month: str,
    project: str,
    queue: str,
    title: str,
    discipline: str,
    package_status: str,
    search_boq: str,
    search_iwp: str,
    search_system: str,
) -> pd.DataFrame:
    if packages_df.empty:
        return packages_df
    result = packages_df.copy()
    if month != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month]
    if project != "Все" and "project_code" in result.columns:
        result = result[result["project_code"].astype(str) == project]
    if queue != "Все" and "queue_display" in result.columns:
        result = result[result["queue_display"].astype(str) == queue]
    if title != "Все" and "title_display" in result.columns:
        result = result[result["title_display"].astype(str) == title]
    if discipline != "Все" and "discipline_display" in result.columns:
        result = result[result["discipline_display"].astype(str) == discipline]
    if package_status != "Все" and "package_status" in result.columns:
        result = result[result["package_status"].astype(str) == package_status]
    if search_boq.strip():
        query = search_boq.strip().lower()
        mask = pd.Series(False, index=result.index)
        for col in ("boq_code", "boq_name", "short_line_id", "line_id"):
            if col in result.columns:
                mask = mask | result[col].astype(str).str.lower().str.contains(query, na=False)
        result = result[mask]
    if search_iwp.strip() and "iwp_display" in result.columns:
        query = search_iwp.strip().lower()
        result = result[result["iwp_display"].astype(str).str.lower().str.contains(query, na=False)]
    if search_system.strip() and "system_display" in result.columns:
        query = search_system.strip().lower()
        result = result[
            result["system_display"].astype(str).str.lower().str.contains(query, na=False)
        ]
    return result


def filter_constraints_by_package_keys(
    constraints_df: pd.DataFrame,
    package_keys: set[str],
) -> pd.DataFrame:
    if constraints_df.empty or not package_keys:
        return pd.DataFrame()
    working = constraints_df.copy()
    working["_package_key"] = working.apply(package_key_from_row, axis=1)
    filtered = working[working["_package_key"].astype(str).isin(package_keys)]
    return filtered.drop(columns=["_package_key"], errors="ignore")


def reset_admission_filters() -> None:
    for session_key, default in ADMISSION_FILTER_DEFAULTS.items():
        st.session_state[session_key] = default


def admission_filter_values_from_session() -> dict[str, Any]:
    return {
        session_key: st.session_state.get(session_key, ADMISSION_FILTER_DEFAULTS[session_key])
        for session_key in ADMISSION_FILTER_DEFAULTS
    }


def persist_admission_filters() -> None:
    st.session_state[ADMISSION_FILTERS_PERSISTED_KEY] = admission_filter_values_from_session()


def lock_admission_filters() -> None:
    snapshot = admission_filter_values_from_session()
    st.session_state[ADMISSION_FILTERS_LOCKED_SNAPSHOT_KEY] = snapshot
    st.session_state[ADMISSION_FILTERS_LOCKED_KEY] = True
    st.session_state[ADMISSION_FILTERS_LOCK_REQUESTED_KEY] = True
    persist_admission_filters()


def admission_filter_memory_active() -> bool:
    return bool(st.session_state.get(ADMISSION_FILTER_MEMORY_ENABLED_KEY)) or bool(
        st.session_state.get(ADMISSION_FILTERS_LOCKED_KEY)
    )


def request_admission_filters_reset() -> None:
    st.session_state[ADMISSION_FILTERS_RESET_REQUESTED_KEY] = True


def admission_filter_status_text() -> str:
    if st.session_state.get(ADMISSION_FILTERS_LOCKED_KEY):
        return "Рабочий срез зафиксирован, изменения фильтров продолжают сохраняться"
    if st.session_state.get(ADMISSION_FILTER_MEMORY_ENABLED_KEY):
        return "Фильтры сохраняются"
    return "Фильтры не сохраняются"


def apply_admission_filter_memory_before_widgets() -> None:
    """Восстановление / сброс фильтров до создания widget-ключей."""
    if st.session_state.pop(ADMISSION_FILTERS_RESET_REQUESTED_KEY, False):
        reset_admission_filters()
        st.session_state[ADMISSION_FILTER_MEMORY_ENABLED_KEY] = False
        st.session_state[ADMISSION_FILTERS_LOCKED_KEY] = False
        st.session_state.pop(ADMISSION_FILTERS_LOCKED_SNAPSHOT_KEY, None)
        st.session_state.pop(ADMISSION_FILTERS_PERSISTED_KEY, None)
        st.session_state.pop(ADMISSION_FILTERS_LOCK_REQUESTED_KEY, None)
        return

    if st.session_state.pop(ADMISSION_FILTERS_LOCK_REQUESTED_KEY, False):
        st.session_state[ADMISSION_FILTER_MEMORY_ENABLED_KEY] = True

    if ADMISSION_FILTER_MEMORY_ENABLED_KEY not in st.session_state:
        st.session_state[ADMISSION_FILTER_MEMORY_ENABLED_KEY] = False
    if ADMISSION_FILTERS_LOCKED_KEY not in st.session_state:
        st.session_state[ADMISSION_FILTERS_LOCKED_KEY] = False

    if st.session_state.get(ADMISSION_FILTER_MEMORY_ENABLED_KEY):
        persisted = st.session_state.get(ADMISSION_FILTERS_PERSISTED_KEY) or {}
        for session_key, value in persisted.items():
            # Восстанавливаем только отсутствующие ключи: иначе persisted
            # перезапишет новое widget value до отрисовки selectbox.
            if session_key not in st.session_state:
                st.session_state[session_key] = value


def sync_admission_filter_memory_after_widgets() -> None:
    if admission_filter_memory_active():
        persist_admission_filters()


def inject_admission_page_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.25rem;
            max-width: 100%;
        }
        .admission-v2-filters {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.85rem 1rem 0.35rem 1rem;
            background: #ffffff;
            margin-bottom: 0.75rem;
        }
        .admission-v2-filters [data-testid="stSelectbox"] > div > div,
        .admission-v2-filters [data-testid="stTextInput"] input {
            min-height: 38px;
            font-size: 0.86rem;
        }
        .v2-kpi-row {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.85rem 0 1rem 0;
        }
        .v2-kpi-card {
            display: flex;
            align-items: flex-start;
            gap: 0.65rem;
            padding: 0.85rem 0.95rem;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #ffffff;
            min-height: 78px;
        }
        .v2-kpi-card-icon {
            flex: 0 0 34px;
            width: 34px;
            height: 34px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            font-weight: 700;
        }
        .v2-kpi-card--total .v2-kpi-card-icon { background: #E8EEF5; color: #475F7B; }
        .v2-kpi-card--open .v2-kpi-card-icon { background: #E6EEF8; color: #2E5B9A; }
        .v2-kpi-card--ready .v2-kpi-card-icon { background: #E7F5EE; color: #2F6B4F; }
        .v2-kpi-card--blocked .v2-kpi-card-icon { background: #FEE2E2; color: #B91C1C; }
        .v2-kpi-card--risk .v2-kpi-card-icon { background: #F9EDE8; color: #A65F45; }
        .v2-kpi-card-label {
            font-size: 0.72rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.15rem;
        }
        .v2-kpi-card-value {
            font-size: 1.35rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.15;
        }
        .admission-package-header {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.9rem 1rem;
            background: #f8fafc;
            margin: 0.75rem 0 1rem 0;
        }
        .admission-explanation {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            margin: 0.5rem 0 0.85rem 0;
            font-size: 0.86rem;
            line-height: 1.5;
            color: #334155;
            background: #ffffff;
        }
        .admission-explanation--blocked {
            border-color: #fecaca;
            background: #fffafb;
        }
        .admission-explanation--open {
            border-color: #fde68a;
            background: #fffdf5;
        }
        .admission-explanation--ready {
            border-color: #bbf7d0;
            background: #f7fdf9;
        }
        .admission-filter-reset button {
            background: #ffffff !important;
            color: #475569 !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 6px !important;
            min-height: 38px !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
        }
        .admission-module-panel {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #ffffff;
            padding: 0.85rem 1rem 0.75rem 1rem;
            margin: 0.5rem 0 0.75rem 0;
        }
        .admission-module-kpi-bar {
            margin: 0.15rem 0 0.55rem 0;
            padding: 0.55rem 0.75rem;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #fafbfc;
        }
        .admission-module-kpi-bar [data-testid="stMetricLabel"] {
            font-size: 0.72rem !important;
            color: #64748b !important;
        }
        .admission-module-kpi-bar [data-testid="stMetricValue"] {
            font-size: 1.15rem !important;
            color: #0f172a !important;
        }
        .admission-module-kpi-detail {
            margin: 0 0 0.65rem 0;
            padding: 0.45rem 0.65rem;
            border: 1px solid #f1f5f9;
            border-radius: 8px;
            background: #fcfcfd;
        }
        .admission-module-kpi-detail [data-testid="stMetricLabel"] {
            font-size: 0.68rem !important;
            color: #94a3b8 !important;
        }
        .admission-module-kpi-detail [data-testid="stMetricValue"] {
            font-size: 0.95rem !important;
            color: #334155 !important;
        }
        .admission-plan-list-kpi-panel {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #f8fafc;
            padding: 0.75rem 0.85rem 0.65rem;
            margin: 0.35rem 0 0.85rem 0;
        }
        .admission-plan-list-kpi-group + .admission-plan-list-kpi-group {
            margin-top: 0.65rem;
            padding-top: 0.65rem;
            border-top: 1px solid #e2e8f0;
        }
        .admission-plan-list-kpi-group-title {
            font-size: 0.7rem;
            font-weight: 700;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin: 0 0 0.45rem 0;
        }
        .admission-plan-list-kpi-row--risk {
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 0.55rem;
            margin-bottom: 0.15rem;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card {
            min-height: 66px;
            padding: 0.6rem 0.7rem;
            gap: 0.5rem;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card-icon {
            flex: 0 0 28px;
            width: 28px;
            height: 28px;
            font-size: 0.75rem;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card-label {
            font-size: 0.62rem;
            line-height: 1.2;
        }
        .admission-plan-list-kpi-row--risk .v2-kpi-card-value {
            font-size: 1.05rem;
        }
        .v2-kpi-card--muted .v2-kpi-card-icon {
            background: #f1f5f9;
            color: #64748b;
        }
        .admission-plan-table [data-testid="stDataFrame"] {
            font-size: 0.84rem;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            overflow: hidden;
        }
        .admission-plan-table [data-testid="stDataFrame"] td,
        .admission-plan-table [data-testid="stDataFrame"] th {
            padding: 0.28rem 0.45rem !important;
            white-space: nowrap;
        }
        .admission-plan-table [data-testid="stDataFrame"] thead th {
            background: #f8fafc !important;
            color: #475569 !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            border-bottom: 1px solid #e2e8f0 !important;
        }
        .admission-plan-table [data-testid="stDataFrame"] tbody td {
            border-bottom: 1px solid #f1f5f9 !important;
            color: #1e293b;
            line-height: 1.25;
            background: #ffffff !important;
        }
        .admission-plan-table [data-testid="stDataFrame"] div[data-testid="stDataFrameResizable"] {
            overflow-x: auto !important;
        }
        .wb-section {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #ffffff;
            padding: 0.65rem 0.85rem 0.5rem 0.85rem;
            margin-bottom: 0.75rem;
        }
        .wb-queue-header {
            font-size: 0.72rem;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            padding: 0.2rem 0 0.35rem 0;
            border-bottom: 1px solid #f1f5f9;
            margin-bottom: 0.15rem;
        }
        .direct-admit-shell {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            background: #fafbfc;
            padding: 0.65rem 0.75rem 0.55rem 0.75rem;
            margin: 0.65rem 0 0.75rem 0;
        }
        .da-module-header {
            margin-bottom: 0.55rem;
            padding-bottom: 0.45rem;
            border-bottom: 1px solid #e2e8f0;
        }
        .da-module-title {
            font-size: 1.02rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.2;
        }
        .da-module-sub {
            font-size: 0.78rem;
            color: #64748b;
            margin-top: 0.18rem;
            line-height: 1.35;
        }
        .da-module-progress {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem 1rem;
            font-size: 0.76rem;
            color: #64748b;
            margin-top: 0.35rem;
        }
        .da-module-progress strong { color: #334155; font-weight: 600; }
        .da-dept-chip-card {
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
            padding: 0.4rem 0.6rem;
            margin-bottom: 0.35rem;
        }
        .da-dept-chip-label {
            font-size: 0.68rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .da-dept-chip-name {
            font-size: 1.05rem;
            font-weight: 700;
            color: #1e3a5f;
            line-height: 1.2;
            margin-top: 0.08rem;
        }
        .da-dept-chip-role {
            font-size: 0.72rem;
            color: #475569;
            margin-top: 0.12rem;
            line-height: 1.3;
        }
        .da-pane {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #ffffff;
            padding: 0.5rem 0.6rem 0.45rem 0.6rem;
        }
        .da-pane-heading {
            font-size: 0.82rem;
            font-weight: 700;
            color: #334155;
            margin-bottom: 0.08rem;
        }
        .da-pane-sub {
            font-size: 0.72rem;
            color: #94a3b8;
            margin-bottom: 0.4rem;
            line-height: 1.3;
        }
        .da-pane-counter {
            font-size: 0.72rem;
            color: #64748b;
            padding: 0.28rem 0.4rem;
            border: 1px solid #f1f5f9;
            border-radius: 6px;
            background: #f8fafc;
            margin-bottom: 0.4rem;
        }
        #da-queue-scroll-host { display: none; }
        #da-gov-scroll-host { display: none; }
        [data-testid="stHorizontalBlock"]:has(.da-direct-admit-pane-marker) {
            align-items: stretch !important;
        }
        [data-testid="stHorizontalBlock"]:has(.da-direct-admit-pane-marker) > div[data-testid="stColumn"] {
            display: flex !important;
            flex-direction: column !important;
        }
        [data-testid="stHorizontalBlock"]:has(.da-direct-admit-pane-marker) > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {
            flex: 1 1 auto !important;
            display: flex !important;
            flex-direction: column !important;
        }
        [data-testid="stHorizontalBlock"]:has(.da-direct-admit-pane-marker) [data-testid="stVerticalBlockBorderWrapper"]:has(.da-direct-admit-pane-marker) {
            flex: 1 1 auto !important;
            min-height: 1450px !important;
            height: 1450px !important;
            box-sizing: border-box !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-queue-scroll-host) {
            max-height: 1450px !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            scrollbar-width: auto;
            scrollbar-color: #94a3b8 #eef2f7;
            padding-right: 0.15rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-queue-scroll-host)::-webkit-scrollbar {
            width: 11px;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-queue-scroll-host)::-webkit-scrollbar-track {
            background: #eef2f7;
            border-radius: 6px;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-queue-scroll-host)::-webkit-scrollbar-thumb {
            background: #94a3b8;
            border-radius: 6px;
            border: 2px solid #eef2f7;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-queue-scroll-host)::-webkit-scrollbar-thumb:hover {
            background: #64748b;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host) {
            max-height: 1450px !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            scrollbar-width: auto;
            scrollbar-color: #94a3b8 #eef2f7;
            padding-right: 0.15rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host)::-webkit-scrollbar {
            width: 11px;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host)::-webkit-scrollbar-track {
            background: #eef2f7;
            border-radius: 6px;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host)::-webkit-scrollbar-thumb {
            background: #94a3b8;
            border-radius: 6px;
            border: 2px solid #eef2f7;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host)::-webkit-scrollbar-thumb:hover {
            background: #64748b;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host) [data-testid="stExpander"] {
            border: 1px solid #e2e8f0 !important;
            border-radius: 6px !important;
            background: #ffffff !important;
            margin-bottom: 0.32rem !important;
            box-shadow: none !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host) [data-testid="stExpander"] details summary {
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            color: #334155 !important;
            padding: 0.28rem 0.45rem !important;
            min-height: 0 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host) [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            padding: 0.12rem 0.42rem 0.32rem 0.42rem !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host) .da-fix-panel {
            border: 1px solid #eef2f7;
            border-radius: 5px;
            background: #fafbfc;
            padding: 0.22rem 0.28rem;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(#da-gov-scroll-host) [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            gap: 0.35rem !important;
        }
        [data-testid="stVerticalBlock"]:has(#da-gov-decision-host) [data-testid="stExpander"] {
            border: 1px solid #e2e8f0 !important;
            border-radius: 6px !important;
            background: #ffffff !important;
            margin-bottom: 0.32rem !important;
            box-shadow: none !important;
        }
        [data-testid="stVerticalBlock"]:has(#da-gov-decision-host) [data-testid="stExpander"] details summary {
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            color: #334155 !important;
            padding: 0.28rem 0.45rem !important;
            min-height: 0 !important;
        }
        [data-testid="stVerticalBlock"]:has(#da-gov-decision-host) [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            padding: 0.12rem 0.42rem 0.32rem 0.42rem !important;
        }
        #da-gov-decision-host { display: none; }
        .da-queue-card {
            border: 1px solid #e2e8f0;
            border-radius: 5px;
            background: #ffffff;
            padding: 0.18rem 0.38rem 0.16rem 0.38rem;
            margin-bottom: 0.08rem;
            line-height: 1.22;
        }
        .da-queue-card-selected {
            border-color: #93c5fd;
            background: #eff6ff;
        }
        .da-queue-row1 {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.25rem;
        }
        .da-queue-row1-main {
            display: flex;
            align-items: baseline;
            flex: 1;
            min-width: 0;
            gap: 0.4rem;
        }
        .da-queue-ordinal {
            font-size: 0.76rem;
            font-weight: 700;
            color: #334155;
            flex-shrink: 0;
            min-width: 1.35rem;
        }
        .da-queue-code {
            font-size: 0.84rem;
            font-weight: 700;
            color: #0f172a;
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .da-queue-row1-right {
            display: flex;
            align-items: center;
            gap: 0.25rem;
            flex-shrink: 0;
        }
        .da-queue-vybran {
            font-size: 0.66rem;
            font-weight: 600;
            color: #2563eb;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            flex-shrink: 0;
        }
        .da-queue-name {
            display: block;
            font-size: 0.75rem;
            color: #334155;
            margin-top: 0.06rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            white-space: normal;
            word-break: break-word;
            line-height: 1.22;
            max-height: 2.5em;
        }
        .da-queue-status-line {
            display: block;
            font-size: 0.72rem;
            margin-top: 0.06rem;
            line-height: 1.2;
        }
        .da-queue-status-label {
            color: #334155;
            font-weight: 400;
        }
        .da-queue-status-value {
            font-weight: 500;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)),
        div[data-testid="stVerticalBlock"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)) {
            position: relative !important;
            margin-bottom: 0.08rem !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)) [data-testid="stElementContainer"]:has([data-testid="stButton"]),
        div[data-testid="stVerticalBlock"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)) [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
            position: absolute !important;
            inset: 0 !important;
            z-index: 2 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: auto !important;
            min-height: 0 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)) [data-testid="stButton"],
        div[data-testid="stVerticalBlock"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)) [data-testid="stButton"] {
            position: absolute !important;
            inset: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: 100% !important;
            width: 100% !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)) [data-testid="stButton"] button,
        div[data-testid="stVerticalBlock"]:has(.da-queue-card-clickable):not(:has(#da-queue-scroll-host)) [data-testid="stButton"] button {
            opacity: 0 !important;
            width: 100% !important;
            height: 100% !important;
            min-height: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            background: transparent !important;
            cursor: pointer !important;
            box-shadow: none !important;
        }
        .da-queue-pane-wrap [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0 !important;
        }
        .da-queue-pane-wrap [data-testid="stCaptionContainer"] {
            margin-bottom: 0.12rem !important;
        }
        .direct-admit-queue-item {
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            background: #ffffff;
            padding: 0.38rem 0.45rem;
            margin-bottom: 0.28rem;
        }
        .direct-admit-queue-item.selected {
            border-color: #93c5fd;
            background: #f8fafc;
            box-shadow: inset 3px 0 0 #3b82f6;
        }
        .da-queue-selected-badge {
            font-size: 0.62rem;
            font-weight: 600;
            color: #1d4ed8;
            background: #dbeafe;
            border-radius: 4px;
            padding: 0.05rem 0.35rem;
            margin-left: auto;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .da-queue-line1 {
            display: flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.78rem;
            font-weight: 600;
            color: #0f172a;
            line-height: 1.25;
        }
        .da-queue-line1 .status-label {
            font-weight: 500;
            font-size: 0.72rem;
        }
        .direct-admit-queue-name {
            font-size: 0.74rem;
            color: #475569;
            line-height: 1.25;
            margin-top: 0.1rem;
        }
        .direct-admit-queue-meta {
            font-size: 0.71rem;
            color: #64748b;
            line-height: 1.28;
            margin-top: 0.08rem;
        }
        .da-empty-state {
            font-size: 0.82rem;
            color: #64748b;
            padding: 0.75rem 0.5rem;
            border: 1px dashed #e2e8f0;
            border-radius: 6px;
            background: #f8fafc;
            text-align: center;
        }
        .direct-admit-boq-code {
            font-size: 1.22rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.15;
        }
        .direct-admit-boq-name {
            font-size: 0.84rem;
            color: #334155;
            margin-top: 0.12rem;
            line-height: 1.32;
        }
        .da-status-chip {
            display: inline-block;
            font-size: 0.72rem;
            font-weight: 500;
            margin-top: 0.25rem;
        }
        .direct-admit-section-label {
            font-size: 0.67rem;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin: 0.45rem 0 0.22rem 0;
        }
        .da-kv-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.15rem 0.65rem;
            font-size: 0.76rem;
            color: #475569;
            line-height: 1.35;
        }
        .da-kv-grid span.label { color: #94a3b8; }
        .da-kv-grid span.val { color: #334155; font-weight: 500; }
        .da-metrics-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.35rem;
            margin-top: 0.15rem;
        }
        .da-metric-card {
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            background: #f8fafc;
            padding: 0.35rem 0.45rem;
        }
        .da-metric-card .label {
            font-size: 0.65rem;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .da-metric-card .value {
            font-size: 0.8rem;
            font-weight: 600;
            color: #0f172a;
            margin-top: 0.08rem;
            line-height: 1.2;
        }
        .da-check-block {
            font-size: 0.76rem;
            color: #475569;
            line-height: 1.4;
            padding: 0.35rem 0.45rem;
            border: 1px solid #f1f5f9;
            border-radius: 6px;
            background: #fcfcfd;
        }
        .da-check-block strong { color: #334155; }
        .da-criteria-box {
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            background: #fcfcfd;
            padding: 0.35rem 0.45rem 0.25rem 0.45rem;
        }
        .da-criteria-box label {
            font-size: 0.76rem !important;
        }
        .da-criteria-progress {
            font-size: 0.72rem;
            color: #64748b;
            margin-top: 0.2rem;
            padding-top: 0.2rem;
            border-top: 1px solid #f1f5f9;
        }
        div[data-testid="stHorizontalBlock"] .da-queue-pick button {
            min-height: 26px !important;
            padding: 0.08rem 0.4rem !important;
            font-size: 0.71rem !important;
            font-weight: 500 !important;
            border-radius: 5px !important;
            margin-top: 0.15rem !important;
        }
        .da-history-block {
            font-size: 0.76rem;
            color: #475569;
            line-height: 1.42;
            padding: 0.4rem 0.5rem;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            background: #f8fafc;
        }
        .da-history-block .title {
            font-size: 0.68rem;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.25rem;
        }
        div[data-testid="stHorizontalBlock"] .direct-admit-actions button {
            min-height: 38px !important;
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            border-radius: 6px !important;
        }
        div[data-testid="stHorizontalBlock"] .da-queue-pick button {
            min-height: 28px !important;
            padding: 0.1rem 0.35rem !important;
            font-size: 0.72rem !important;
        }
        div[data-testid="stHorizontalBlock"] .wb-btn-row button {
            min-height: 30px !important;
            padding: 0.15rem 0.45rem !important;
            font-size: 0.76rem !important;
            font-weight: 500 !important;
            border-radius: 5px !important;
        }
        div[data-testid="stHorizontalBlock"] .wb-btn-row button[kind="primary"] {
            background: #1e3a5f !important;
            border-color: #1e3a5f !important;
        }
        .wb-detail-strip {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #f8fafc;
            padding: 0.55rem 0.75rem;
            margin: 0.5rem 0 0.65rem 0;
            font-size: 0.8rem;
            color: #475569;
            line-height: 1.45;
        }
        [data-testid="stSegmentedControl"] {
            margin-bottom: 0.5rem;
        }
        [data-testid="stSegmentedControl"] button {
            font-size: 0.8rem !important;
            min-height: 32px !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)),
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) {
            position: relative !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) .da-block-d-pass-visual {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 34px;
            padding: 0.18rem 0.35rem;
            border-radius: 0.5rem;
            background-color: #2F6B4F;
            border: 1px solid #2F6B4F;
            color: #ffffff;
            font-size: 0.76rem;
            font-weight: 600;
            line-height: 1.2;
            text-align: center;
            transition: background-color 0.15s ease, border-color 0.15s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)):hover .da-block-d-pass-visual {
            background-color: #276052;
            border-color: #276052;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stElementContainer"]:has([data-testid="stButton"]),
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
            position: absolute !important;
            inset: 0 !important;
            z-index: 2 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: auto !important;
            min-height: 0 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"],
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] {
            position: absolute !important;
            inset: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: 100% !important;
            width: 100% !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] button,
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-pass):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] button {
            opacity: 0 !important;
            width: 100% !important;
            height: 100% !important;
            min-height: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            background: transparent !important;
            cursor: pointer !important;
            box-shadow: none !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)),
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) {
            position: relative !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) .da-block-d-clarify-visual {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 34px;
            padding: 0.18rem 0.35rem;
            border-radius: 0.5rem;
            background-color: #C4920A;
            border: 1px solid #C4920A;
            color: #ffffff;
            font-size: 0.76rem;
            font-weight: 600;
            line-height: 1.2;
            text-align: center;
            transition: background-color 0.15s ease, border-color 0.15s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)):hover .da-block-d-clarify-visual {
            background-color: #A67C08;
            border-color: #A67C08;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stElementContainer"]:has([data-testid="stButton"]),
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
            position: absolute !important;
            inset: 0 !important;
            z-index: 2 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: auto !important;
            min-height: 0 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"],
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] {
            position: absolute !important;
            inset: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: 100% !important;
            width: 100% !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] button,
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-clarify):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] button {
            opacity: 0 !important;
            width: 100% !important;
            height: 100% !important;
            min-height: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            background: transparent !important;
            cursor: pointer !important;
            box-shadow: none !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)),
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) {
            position: relative !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) .da-block-d-block-visual {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 34px;
            padding: 0.18rem 0.35rem;
            border-radius: 0.5rem;
            background-color: #9B3D3D;
            border: 1px solid #9B3D3D;
            color: #ffffff;
            font-size: 0.76rem;
            font-weight: 600;
            line-height: 1.2;
            text-align: center;
            transition: background-color 0.15s ease, border-color 0.15s ease;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)):hover .da-block-d-block-visual {
            background-color: #863434;
            border-color: #863434;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stElementContainer"]:has([data-testid="stButton"]),
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stElementContainer"]:has([data-testid="stButton"]) {
            position: absolute !important;
            inset: 0 !important;
            z-index: 2 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: auto !important;
            min-height: 0 !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"],
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] {
            position: absolute !important;
            inset: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            height: 100% !important;
            width: 100% !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] button,
        div[data-testid="stVerticalBlock"]:has(.da-block-d-btn-block):not(:has(#da-queue-scroll-host)):not(:has([data-testid="stSelectbox"])):not(:has(.da-c2-matrix-marker)):not(:has(.da-c2-crit-ctrl-marker)) [data-testid="stButton"] button {
            opacity: 0 !important;
            width: 100% !important;
            height: 100% !important;
            min-height: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            background: transparent !important;
            cursor: pointer !important;
            box-shadow: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_risk_sum(df: pd.DataFrame) -> float:
    """Сумма plan_value/value_at_risk один раз на строку плана (не × число отделов)."""
    if df.empty:
        return 0.0
    tmp = df.copy()
    tmp["_plan_line_key"] = tmp.apply(plan_line_key, axis=1)
    tmp["_risk_val"] = tmp.apply(row_risk_value, axis=1)
    deduped = tmp.drop_duplicates(subset=["_plan_line_key"], keep="first")
    return float(deduped["_risk_val"].sum())


def ru_label(tech: str, mapping: Dict[str, str]) -> str:
    if tech == "Все":
        return "Все"
    return mapping.get(tech, tech)


def norm_tech_value(
    value: Any,
    tech_options: List[str],
    mapping: Dict[str, str],
    default: str,
) -> str:
    if value is None or pd.isna(value):
        return default
    raw = str(value).strip()
    if raw in tech_options:
        return raw
    rev = reverse_map(mapping)
    if raw in rev:
        return rev[raw]
    upper = raw.upper()
    if upper in tech_options:
        return upper
    return default


def norm_check_status_key(value: Any) -> str:
    return norm_tech_value(value, CHECK_STATUS_OPTIONS, CHECK_STATUS_RU, "ОЖИДАЕТ")


def ru_selectbox(
    label: str,
    tech_options: List[str],
    mapping: Dict[str, str],
    current_tech: str,
    key: Optional[str] = None,
) -> str:
    labels = [mapping.get(t, t) for t in tech_options]
    current_tech = norm_tech_value(current_tech, tech_options, mapping, tech_options[0])
    current_label = mapping.get(current_tech, current_tech)
    index = labels.index(current_label) if current_label in labels else 0
    selected_label = st.selectbox(label, labels, index=index, key=key)
    rev = reverse_map(mapping)
    return rev.get(selected_label, tech_options[labels.index(selected_label)])


def filter_options_ru(
    df: pd.DataFrame,
    col: str,
    mapping: Dict[str, str],
) -> List[str]:
    """Технические значения для фильтра; отображение — через format_func."""
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals, key=lambda v: ru_label(v, mapping))


def category_options_for_department(department: str, current: str) -> List[str]:
    dept = safe_str(department)
    opts = list(CATEGORY_BY_DEPARTMENT.get(dept, ["Другое"]))
    if NO_CONSTRAINT_CATEGORY not in opts:
        opts.append(NO_CONSTRAINT_CATEGORY)
    if current and current not in opts:
        opts = [current] + opts
    return opts


def init_filter_defaults(options: List[str], session_key: str, default: str = "Все") -> None:
    if session_key not in st.session_state:
        st.session_state[session_key] = default
    elif st.session_state[session_key] not in options:
        st.session_state[session_key] = default if default in options else options[0]


def combined_constraint_reason(row: pd.Series) -> str:
    block = safe_str(row.get("block_reason"))
    root = safe_str(row.get("root_cause"))
    if block and root and block != root:
        return f"{block}\n{root}"
    return block or root


def format_registry_decision_at_display(row: Dict[str, Any]) -> str:
    for col in ("last_action_at", "updated_at"):
        if has_meaningful_value(row.get(col)):
            return format_datetime_moscow(row.get(col))
    return "—"


def _registry_first_field_value(*sources: Dict[str, Any], fields: tuple[str, ...]) -> str:
    for source in sources:
        if not source:
            continue
        for field in fields:
            value = safe_str(source.get(field)).strip()
            if value:
                return value
    return ""


def format_registry_month_display(
    constraint_row: Dict[str, Any],
    v2_row: Dict[str, Any],
) -> str:
    month = _registry_first_field_value(
        constraint_row,
        v2_row,
        fields=DECISION_REGISTRY_MONTH_FIELDS,
    )
    return field_display(month) if month else "—"


def format_registry_system_display(
    constraint_row: Dict[str, Any],
    v2_row: Dict[str, Any],
) -> str:
    system = _registry_first_field_value(
        constraint_row,
        v2_row,
        fields=DECISION_REGISTRY_SYSTEM_FIELDS,
    )
    return field_display(system) if system else "—"


def format_registry_iwp_display(
    constraint_row: Dict[str, Any],
    v2_row: Dict[str, Any],
) -> str:
    iwp = _registry_first_field_value(
        constraint_row,
        v2_row,
        fields=DECISION_REGISTRY_IWP_FIELDS,
    )
    return field_display(iwp) if iwp else "—"


def format_registry_constraint_reason_display(row: Dict[str, Any]) -> str:
    """Одна колонка: сначала суть из root_cause/comment, иначе не-generic block_reason."""
    substance = constraint_block_substance(row)
    if substance and not is_generic_block_reason(substance):
        return field_display(substance)
    specific_block = registry_specific_block_reason(row)
    if specific_block:
        return field_display(specific_block)
    return "—"


def constraint_occurrence_date(row: pd.Series) -> date:
    for col in ("constraint_created_at", "created_at"):
        if col in row.index:
            parsed = safe_date(row.get(col))
            if parsed:
                return parsed
    return date.today()


def constraint_duration_days(
    occurrence: Optional[date],
    target: Optional[date],
) -> str:
    if occurrence is None:
        return "—"
    end = target if target else date.today()
    return str(max((end - occurrence).days, 0))


def infer_responsibility_side(row: pd.Series) -> str:
    """Fallback из owner_department / responsible_department без записи в БД."""
    raw = safe_str(row.get("owner_department") or row.get("responsible_department"))
    if not raw:
        return "Не определено"
    lowered = raw.lower()
    if any(x in lowered for x in ("заказчик", "customer", "client")):
        return "Заказчик"
    if any(x in lowered for x in ("генподряд", "ген подряд")):
        return "Генподрядчик"
    if any(x in lowered for x in ("проектир", "птo", "пто", "engineering")):
        return "Проектировщик"
    if any(x in lowered for x in ("мто", "постав", "vendor", "вендор")):
        return "Поставщик / Вендор"
    if any(x in lowered for x in ("надзор", "техническ")):
        return "Технический надзор"
    if raw in DEPARTMENT_RU or dept_ui(raw) in DEPARTMENT_RU.values():
        return "Наша организация / Субподрядчик"
    return "Не определено"


def owner_role_options(current: str) -> List[str]:
    opts = list(OWNER_ROLE_PRESETS)
    if current and current not in opts:
        opts = [current] + opts
    return opts


def owner_name_options(current: str) -> List[str]:
    opts = list(OWNER_NAME_PRESETS)
    if current and current not in opts:
        opts = [current] + opts
    return opts


def constraint_human_label(row: pd.Series) -> str:
    status_key = norm_check_status_key(row.get("check_status"))
    status_ui = CHECK_STATUS_RU.get(status_key, status_key)
    dept = dept_ui(row.get("responsible_department"))
    boq = safe_str(row.get("boq_code")) or "—"
    name = safe_str(row.get("boq_name")) or "—"
    check = safe_str(row.get("check_name")) or "—"
    return f"{boq} | {name} | {dept} | {check} | {status_ui}"


def resolution_is_closed(resolution_status: str) -> bool:
    key = norm_tech_value(resolution_status, RESOLUTION_OPTIONS, RESOLUTION_RU, "OPEN")
    return key in ("RESOLVED", "CANCELLED")


def overdue_days_for_card(target: Optional[date], resolution_status: str) -> int:
    if resolution_is_closed(resolution_status):
        return 0
    if target is None:
        return 0
    return max((date.today() - target).days, 0)


def count_schedule_reschedules(comment: str) -> int:
    if not comment:
        return 0
    return sum(1 for line in comment.splitlines() if line.strip().startswith(AUTO_SCHEDULE_PREFIX))


def parse_schedule_history(comment: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    if not comment:
        return items
    for line in comment.splitlines():
        text = line.strip()
        if not text.startswith(AUTO_SCHEDULE_PREFIX):
            continue
        body = text[len(AUTO_SCHEDULE_PREFIX) :].strip().lstrip(":").strip()
        note = ""
        if "не выдержан" in body.lower():
            note = "не выдержан"
        arrow = "→"
        if arrow in body:
            left, right = body.split(arrow, 1)
            old_part = left.strip().split(",")[0].strip()
            new_part = right.split(",")[0].strip()
            items.append({"old": old_part, "new": new_part, "note": note})
    return items


def is_owner_optional(check_status: str, category: str) -> bool:
    if norm_check_status_key(check_status) == "PASS":
        return True
    return category == NO_CONSTRAINT_CATEGORY


def resolve_selected_constraint_id(df: pd.DataFrame, label_keys: List[str]) -> str:
    """Приоритет: выделение в таблице → ручной dropdown → последний выбор → первая строка."""
    selection_state = st.session_state.get(TABLE_SELECTION_KEY, {})
    selected_rows = selection_state.get("selection", {}).get("rows", [])
    if selected_rows:
        row_idx = int(selected_rows[0])
        if 0 <= row_idx < len(df):
            picked = safe_str(df.iloc[row_idx].get("constraint_id"))
            if picked in label_keys:
                st.session_state[TABLE_SELECTED_ID_KEY] = picked
                return picked

    manual = st.session_state.get(CONSTRAINT_EDIT_SELECT_KEY)
    if manual and manual in label_keys:
        return str(manual)

    stored = st.session_state.get(TABLE_SELECTED_ID_KEY)
    if stored and stored in label_keys:
        return str(stored)

    return label_keys[0]


def apply_no_constraint_form_preset(constraint_id: str) -> None:
    st.session_state[f"form_preset_{constraint_id}"] = {
        "check_status": "PASS",
        "resolution_status": "RESOLVED",
        "owner_name": "Не требуется",
        "owner_role": "Не требуется",
        "value_at_risk": 0.0,
        "category": NO_CONSTRAINT_CATEGORY,
    }
    for widget_key in (
        f"check_status_{constraint_id}",
        f"resolution_{constraint_id}",
        f"severity_{constraint_id}",
        f"owner_name_sel_{constraint_id}",
        f"owner_role_sel_{constraint_id}",
        f"owner_name_custom_{constraint_id}",
        f"owner_role_custom_{constraint_id}",
        f"value_at_risk_{constraint_id}",
        f"category_{constraint_id}",
    ):
        st.session_state.pop(widget_key, None)


def resolve_owner_name(choice: str, custom: str) -> str:
    if choice == "Другое":
        return custom.strip()
    if choice == "Не назначен":
        return ""
    return choice


def append_schedule_change_comment(
    existing_comment: str,
    old_target: Optional[date],
    new_target: date,
    saver_name: str,
) -> str:
    old_s = old_target.isoformat() if old_target else "—"
    new_s = new_target.isoformat()
    not_met = ""
    if old_target and old_target < date.today() and new_target > old_target:
        not_met = " (старый срок не выдержан)"
    line = (
        f"{AUTO_SCHEDULE_PREFIX}: {old_s} → {new_s}{not_met}, "
        f"дата изменения: {date.today().isoformat()}, кем: {saver_name}"
    )
    base = (existing_comment or "").strip()
    return f"{base}\n{line}".strip() if base else line


def audit_last_updated_at(row: pd.Series) -> Any:
    for col in ("updated_at", "last_action_at", "last_updated_at"):
        if col in row.index and not pd.isna(row.get(col)):
            return row.get(col)
    return None


def audit_last_updated_by(row: pd.Series) -> str:
    for col in ("updated_by", "last_updated_by"):
        if col in row.index:
            text = safe_str(row.get(col))
            if text:
                return text
    return ""


@st.cache_data(ttl=120)
def load_constraint_evidence(constraint_id: str) -> pd.DataFrame:
    if not constraint_id:
        return pd.DataFrame()
    try:
        resp = (
            supabase.table(TABLE_EVIDENCE)
            .select("*")
            .eq("constraint_id", constraint_id)
            .order("uploaded_at", desc=True)
            .limit(100)
            .execute()
        )
        return pd.DataFrame(resp.data or [])
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def insert_evidence_metadata(
    constraint_id: str,
    file_name: str,
    uploaded_by: str,
    description: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """
    Сохраняет метаданные в monthly_plan_constraint_evidence (без файла в Storage).
  Возвращает (error, evidence_id).
    """
    client = get_write_client()
    if client is None:
        return "SUPABASE_SECRET_KEY не задан в .env — сохранение доказательства недоступно.", None
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    evidence_type = "OTHER"
    if ext in ("png", "jpg", "jpeg"):
        evidence_type = "PHOTO"
    payload: Dict[str, Any] = {
        "constraint_id": constraint_id,
        "file_name": file_name,
        "uploaded_by": uploaded_by or None,
        "description": description or None,
        "evidence_type": evidence_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = client.table(TABLE_EVIDENCE).insert(payload).execute()
        rows = resp.data or []
        evidence_id = str(rows[0].get("evidence_id") or "") if rows else ""
        return None, evidence_id or None
    except Exception as exc:  # noqa: BLE001
        return str(exc), None


def style_check_status_bg(val: Any) -> str:
    return CHECK_STATUS_BG_RU.get(str(val), "")


def style_check_status_text(val: Any) -> str:
    text = str(val).strip()
    if not text or text == "—":
        return "color: #64748b;"
    lower = text.lower()
    if "пройдено" in lower or "допущено" in lower or "закрыто" in lower:
        return "color: #2F6B4F; font-weight: 600;"
    if "риск" in lower or "уточнен" in lower or "в работе" in lower:
        return "color: #92610E; font-weight: 600;"
    if (
        "удержание" in lower
        or "блокир" in lower
        or "не пройдено" in lower
        or lower == "открыто"
    ):
        return "color: #9B3D3D; font-weight: 600;"
    if "ожидает" in lower or "не проверен" in lower:
        return "color: #64748b;"
    return "color: #475569;"


def format_decision_registry_check_status_display(val: Any) -> str:
    """Display-only: короткие enterprise-статусы в верхнем регистре."""
    text = str(val).strip()
    if not text or text == "—":
        return text
    mapped = DECISION_REGISTRY_CHECK_STATUS_DISPLAY.get(text)
    if mapped:
        return mapped
    return text.upper()


def style_decision_registry_check_status_text(val: Any) -> str:
    """Мягкие цвета статусов — как в таблице «Список месячного плана для допуска»."""
    text = str(val).strip().upper()
    if not text or text == "—":
        return "color: #64748b;"
    return DECISION_REGISTRY_CHECK_STATUS_TEXT_STYLE.get(text, "color: #475569;")


def style_overdue_bg(val: Any) -> str:
    try:
        if int(float(val)) > 0:
            return "background-color: #fee2e2;"
    except Exception:  # noqa: BLE001
        pass
    return ""


def style_severity_text(val: Any) -> str:
    text = str(val)
    if text in ("Критическая", "CRITICAL"):
        return "color: #b91c1c; font-weight: 700;"
    if text in ("Высокая", "HIGH"):
        return "color: #c2410c; font-weight: 600;"
    return ""


def filter_options(df: pd.DataFrame, col: str) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def row_risk_value(row: pd.Series) -> float:
    if "value_at_risk" in row.index and not pd.isna(row.get("value_at_risk")):
        return safe_num(row.get("value_at_risk"))
    return safe_num(row.get("plan_value"))


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    created_col = (
        "constraint_created_at"
        if "constraint_created_at" in result.columns
        else "created_at"
    )

    if "days_open" not in result.columns:
        days_open: List[int] = []
        for _, row in result.iterrows():
            start = safe_date(row.get(created_col)) if created_col in result.columns else None
            resolved = safe_date(row.get("resolved_at")) if "resolved_at" in result.columns else None
            end = date.today() if resolved is None else resolved
            if start is None:
                days_open.append(0)
            else:
                days_open.append(max((end - start).days, 0))
        result["days_open"] = days_open

    if "days_overdue" not in result.columns or "is_overdue" not in result.columns:
        overdue_days: List[int] = []
        overdue_flags: List[bool] = []
        for _, row in result.iterrows():
            status = safe_str(row.get("resolution_status")).upper()
            target = safe_date(row.get("target_resolution_date"))
            if status in {"RESOLVED", "CANCELLED"} or target is None or target >= date.today():
                overdue_days.append(0)
                overdue_flags.append(False)
            else:
                overdue_days.append((date.today() - target).days)
                overdue_flags.append(True)
        if "days_overdue" not in result.columns:
            result["days_overdue"] = overdue_days
        if "is_overdue" not in result.columns:
            result["is_overdue"] = overdue_flags

    result["value_at_risk_display"] = result.apply(row_risk_value, axis=1)
    return result


@st.cache_data(ttl=300)
def load_constraints() -> pd.DataFrame:
    try:
        rows = fetch_all_constraints(supabase, VIEW_DASHBOARD_V2)
        return enrich_dataframe(pd.DataFrame(rows))
    except Exception:  # noqa: BLE001
        try:
            rows = fetch_all_constraints(supabase, TABLE_CONSTRAINTS)
            return enrich_dataframe(pd.DataFrame(rows))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Не удалось загрузить ограничения: {exc}")
            return pd.DataFrame()


def apply_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
    department: str,
    check_status: str,
    resolution_status: str,
    overdue_only: bool,
    search: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    if project != "Все" and "project_code" in result.columns:
        result = result[result["project_code"].astype(str) == project]
    if month != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month]
    if facility != "Все" and "facility_building" in result.columns:
        result = result[result["facility_building"].astype(str) == facility]
    if discipline != "Все" and "construction_discipline" in result.columns:
        result = result[result["construction_discipline"].astype(str) == discipline]
    if department != "Все" and "responsible_department" in result.columns:
        result = result[result["responsible_department"].astype(str) == department]
    if check_status != "Все" and "check_status" in result.columns:
        result = result[result["check_status"].astype(str) == check_status]
    if resolution_status != "Все" and "resolution_status" in result.columns:
        result = result[result["resolution_status"].astype(str) == resolution_status]
    if overdue_only and "is_overdue" in result.columns:
        result = result[result["is_overdue"].astype(bool)]
    if search.strip():
        q = search.strip().lower()
        mask = pd.Series(False, index=result.index)
        for col in ("boq_code", "boq_name", "owner_name", "line_id"):
            if col in result.columns:
                mask = mask | result[col].astype(str).str.lower().str.contains(q, na=False)
        result = result[mask]
    return result


def constraint_label(row: pd.Series) -> str:
    status_key = norm_check_status_key(row.get("check_status"))
    status_ui = CHECK_STATUS_RU.get(status_key, status_key)
    gate_ui = GATE_LAYER_RU.get(safe_str(row.get("gate_layer")), safe_str(row.get("gate_layer")))
    return (
        f"{dept_ui(row.get('responsible_department'))} | "
        f"{safe_str(row.get('boq_code'))} | "
        f"{safe_str(row.get('check_name'))} | "
        f"{gate_ui} | "
        f"{status_ui}"
    )


def update_constraint_record(
    constraint_id: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    client = get_write_client()
    if client is None:
        return "SUPABASE_SECRET_KEY не задан в .env — сохранение недоступно."
    try:
        client.table(TABLE_CONSTRAINTS).update(payload).eq(
            "constraint_id", constraint_id
        ).execute()
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def _apply_cell_style(styler, func, column: str):
    if column not in styler.data.columns:
        return styler
    if hasattr(styler, "map"):
        return styler.map(func, subset=pd.IndexSlice[:, [column]])
    return styler.applymap(func, subset=pd.IndexSlice[:, [column]])


def style_table(df_in: pd.DataFrame):
    styler = df_in.style
    styler = _apply_cell_style(styler, style_check_status_bg, TABLE_COLUMNS_RU["check_status"])
    styler = _apply_cell_style(styler, style_overdue_bg, TABLE_COLUMNS_RU["days_overdue"])
    severity_col = TABLE_COLUMNS_RU.get("severity", "Критичность")
    styler = _apply_cell_style(styler, style_severity_text, severity_col)
    return styler


def style_decision_registry_table(df_in: pd.DataFrame):
    styler = df_in.style
    status_col = DECISION_REGISTRY_TABLE_COLUMNS_RU.get("check_status", "Статус проверки")
    labor_pct_col = DECISION_REGISTRY_TABLE_COLUMNS_RU.get(
        "labor_to_plan_pct_display", "Труд / стоимость работ, %"
    )
    if status_col in styler.data.columns:
        styler = _apply_cell_style(styler, style_decision_registry_check_status_text, status_col)
    if labor_pct_col in styler.data.columns:
        styler = _apply_cell_style(styler, style_admission_labor_to_plan_pct_text, labor_pct_col)
    for col in DECISION_REGISTRY_NUMERIC_COLUMNS:
        if col in df_in.columns:
            styler = styler.set_properties(subset=[col], **{"text-align": "right"})
    return styler


def render_kpi_top_bar(df: pd.DataFrame) -> None:
    """Компактная сводка без замены детальных KPI."""
    total = len(df)
    open_cnt = 0
    if "resolution_status" in df.columns:
        open_cnt = len(
            df[df["resolution_status"].astype(str).isin(["OPEN", "IN_PROGRESS"])]
        )
    overdue_cnt = int(df["is_overdue"].astype(bool).sum()) if "is_overdue" in df.columns else 0
    hold_cnt = len(df[df["check_status"].astype(str) == "HOLD"]) if "check_status" in df.columns else 0
    fail_cnt = len(df[df["check_status"].astype(str) == "FAIL"]) if "check_status" in df.columns else 0
    risk_sum = kpi_risk_sum(df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Всего ограничений", total)
    c2.metric("Открыто", open_cnt)
    c3.metric("Просрочено", overdue_cnt)
    c4.metric("HOLD / FAIL", hold_cnt + fail_cnt)
    c5.metric("Стоимость под риском", money_ru(risk_sum))


def render_kpis(df: pd.DataFrame) -> None:
    render_admission_module_check_kpis(df, packages_df=None)


def blocked_admission_value(packages_df: pd.DataFrame) -> float:
    if packages_df.empty or "package_status" not in packages_df.columns:
        return 0.0
    blocked = packages_df[packages_df["package_status"].astype(str) == PACKAGE_STATUS_BLOCKED]
    if blocked.empty or "plan_value" not in blocked.columns:
        return 0.0
    return float(blocked["plan_value"].sum())


def render_admission_module_summary_kpis(packages_df: pd.DataFrame) -> None:
    total = len(packages_df)
    open_cnt = (
        int((packages_df["package_status"] == PACKAGE_STATUS_OPEN).sum()) if total else 0
    )
    ready_cnt = (
        int((packages_df["package_status"] == PACKAGE_STATUS_READY).sum()) if total else 0
    )
    blocked_cnt = (
        int((packages_df["package_status"] == PACKAGE_STATUS_BLOCKED).sum()) if total else 0
    )
    risk_sum = (
        float(packages_df["plan_value"].sum())
        if total and "plan_value" in packages_df.columns
        else 0.0
    )

    st.markdown('<div class="admission-module-kpi-bar">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Строк в допуске", total)
    c2.metric("Ожидают проверки", open_cnt)
    c3.metric("Допущено отделами", ready_cnt)
    c4.metric("Заблокировано", blocked_cnt)
    c5.metric("Стоимость допуска", money_ru(risk_sum))
    st.markdown("</div>", unsafe_allow_html=True)


def render_admission_module_check_kpis(
    scope_df: pd.DataFrame,
    packages_df: Optional[pd.DataFrame] = None,
) -> None:
    total = len(scope_df)
    wait_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "ОЖИДАЕТ"])
        if "check_status" in scope_df.columns
        else 0
    )
    pass_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "PASS"])
        if "check_status" in scope_df.columns
        else 0
    )
    warn_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "WARNING"])
        if "check_status" in scope_df.columns
        else 0
    )
    hold_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "HOLD"])
        if "check_status" in scope_df.columns
        else 0
    )
    fail_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "FAIL"])
        if "check_status" in scope_df.columns
        else 0
    )
    overdue_cnt = (
        int(scope_df["is_overdue"].astype(bool).sum())
        if "is_overdue" in scope_df.columns
        else 0
    )
    blocked_value = blocked_admission_value(packages_df) if packages_df is not None else 0.0

    st.markdown('<div class="admission-module-kpi-detail">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Всего строк для допуска", total)
    c2.metric("Ожидают проверки", wait_cnt)
    c3.metric("Пройдено проверок", pass_cnt)
    c4.metric("Уточнение требуется", warn_cnt)
    c5.metric("Удержание / блок", hold_cnt + fail_cnt)
    c6.metric("Просрочено", overdue_cnt)
    c7.metric("Стоимость под блокировкой", money_ru(blocked_value))
    st.markdown("</div>", unsafe_allow_html=True)


def _admission_plan_list_kpi_card_html(label: str, value: str, variant: str) -> str:
    icons = {
        "total": "∑",
        "open": "○",
        "ready": "✓",
        "blocked": "!",
        "risk": "₽",
        "muted": "·",
        "pass": "✓",
    }
    icon = icons.get(variant, "·")
    return (
        f'<div class="v2-kpi-card v2-kpi-card--{variant}">'
        f'<div class="v2-kpi-card-icon">{icon}</div>'
        f"<div>"
        f'<div class="v2-kpi-card-label">{label}</div>'
        f'<div class="v2-kpi-card-value">{value}</div>'
        f"</div></div>"
    )


def render_admission_plan_list_kpi_panel(
    packages_df: pd.DataFrame,
    scope_df: pd.DataFrame,
) -> None:
    """Компактная KPI-панель блока «Список месячного плана для допуска»."""
    pkg_total = len(packages_df)
    pkg_open = (
        int((packages_df["package_status"] == PACKAGE_STATUS_OPEN).sum()) if pkg_total else 0
    )
    pkg_ready = (
        int((packages_df["package_status"] == PACKAGE_STATUS_READY).sum()) if pkg_total else 0
    )
    pkg_blocked = (
        int((packages_df["package_status"] == PACKAGE_STATUS_BLOCKED).sum()) if pkg_total else 0
    )
    admission_value = (
        float(packages_df["plan_value"].sum())
        if pkg_total and "plan_value" in packages_df.columns
        else 0.0
    )

    check_total = len(scope_df)
    wait_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "ОЖИДАЕТ"])
        if "check_status" in scope_df.columns
        else 0
    )
    pass_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "PASS"])
        if "check_status" in scope_df.columns
        else 0
    )
    warn_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "WARNING"])
        if "check_status" in scope_df.columns
        else 0
    )
    hold_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "HOLD"])
        if "check_status" in scope_df.columns
        else 0
    )
    fail_cnt = (
        len(scope_df[scope_df["check_status"].astype(str) == "FAIL"])
        if "check_status" in scope_df.columns
        else 0
    )
    overdue_cnt = (
        int(scope_df["is_overdue"].astype(bool).sum())
        if "is_overdue" in scope_df.columns
        else 0
    )
    blocked_value = blocked_admission_value(packages_df)

    volume_cards = "".join(
        [
            _admission_plan_list_kpi_card_html("Строк в допуске", str(pkg_total), "total"),
            _admission_plan_list_kpi_card_html("Ожидают проверки", str(pkg_open), "open"),
            _admission_plan_list_kpi_card_html("Допущено отделами", str(pkg_ready), "ready"),
            _admission_plan_list_kpi_card_html("Заблокировано", str(pkg_blocked), "blocked"),
            _admission_plan_list_kpi_card_html(
                "Стоимость допуска", money_ru(admission_value), "risk"
            ),
        ]
    )
    risk_cards = "".join(
        [
            _admission_plan_list_kpi_card_html(
                "Всего строк для допуска", str(check_total), "total"
            ),
            _admission_plan_list_kpi_card_html("Ожидают проверки", str(wait_cnt), "open"),
            _admission_plan_list_kpi_card_html("Пройдено проверок", str(pass_cnt), "ready"),
            _admission_plan_list_kpi_card_html(
                "Уточнение требуется", str(warn_cnt), "muted"
            ),
            _admission_plan_list_kpi_card_html(
                "Удержание / блок", str(hold_cnt + fail_cnt), "blocked"
            ),
            _admission_plan_list_kpi_card_html("Просрочено", str(overdue_cnt), "muted"),
            _admission_plan_list_kpi_card_html(
                "Стоимость под блокировкой",
                money_ru(blocked_value),
                "risk",
            ),
        ]
    )

    st.markdown(
        f"""
        <div class="admission-plan-list-kpi-panel">
            <div class="admission-plan-list-kpi-group">
                <div class="admission-plan-list-kpi-group-title">Объём допуска</div>
                <div class="v2-kpi-row">{volume_cards}</div>
            </div>
            <div class="admission-plan-list-kpi-group">
                <div class="admission-plan-list-kpi-group-title">Риски допуска</div>
                <div class="v2-kpi-row admission-plan-list-kpi-row--risk">{risk_cards}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_package_executive_cards(packages_df: pd.DataFrame) -> None:
    total = len(packages_df)
    open_cnt = int((packages_df["package_status"] == PACKAGE_STATUS_OPEN).sum()) if total else 0
    ready_cnt = int((packages_df["package_status"] == PACKAGE_STATUS_READY).sum()) if total else 0
    blocked_cnt = int((packages_df["package_status"] == PACKAGE_STATUS_BLOCKED).sum()) if total else 0
    risk_sum = float(packages_df["plan_value"].sum()) if total and "plan_value" in packages_df.columns else 0.0

    st.markdown(
        f"""
        <div class="v2-kpi-row">
            <div class="v2-kpi-card v2-kpi-card--total">
                <div class="v2-kpi-card-icon">∑</div>
                <div>
                    <div class="v2-kpi-card-label">Строк в допуске</div>
                    <div class="v2-kpi-card-value">{total}</div>
                </div>
            </div>
            <div class="v2-kpi-card v2-kpi-card--open">
                <div class="v2-kpi-card-icon">○</div>
                <div>
                    <div class="v2-kpi-card-label">Ожидают допуска</div>
                    <div class="v2-kpi-card-value">{open_cnt}</div>
                </div>
            </div>
            <div class="v2-kpi-card v2-kpi-card--ready">
                <div class="v2-kpi-card-icon">✓</div>
                <div>
                    <div class="v2-kpi-card-label">Допущено отделами</div>
                    <div class="v2-kpi-card-value">{ready_cnt}</div>
                </div>
            </div>
            <div class="v2-kpi-card v2-kpi-card--blocked">
                <div class="v2-kpi-card-icon">!</div>
                <div>
                    <div class="v2-kpi-card-label">Заблокировано</div>
                    <div class="v2-kpi-card-value">{blocked_cnt}</div>
                </div>
            </div>
            <div class="v2-kpi-card v2-kpi-card--risk">
                <div class="v2-kpi-card-icon">₽</div>
                <div>
                    <div class="v2-kpi-card-label">Стоимость допуска</div>
                    <div class="v2-kpi-card-value">{money_ru(risk_sum)}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_workbench_dataframe(
    constraints_df: pd.DataFrame,
    packages_df: pd.DataFrame,
) -> pd.DataFrame:
    if constraints_df.empty:
        return pd.DataFrame()

    pkg_lookup: Dict[str, Dict[str, Any]] = {}
    for _, pkg in packages_df.iterrows():
        entry = pkg.to_dict()
        pkg_key = safe_str(pkg.get("package_key"))
        line_id = safe_str(pkg.get("line_id"))
        if pkg_key:
            pkg_lookup[pkg_key] = entry
        if line_id:
            pkg_lookup[f"line:{line_id}"] = entry

    rows: List[Dict[str, Any]] = []
    for _, constraint in constraints_df.iterrows():
        pkg_key = package_key_from_row(constraint)
        pkg = pkg_lookup.get(pkg_key, {})
        status_key = norm_check_status_key(constraint.get("check_status"))
        resolution_key = norm_tech_value(
            constraint.get("resolution_status"),
            RESOLUTION_OPTIONS,
            RESOLUTION_RU,
            "OPEN",
        )
        gate = safe_str(constraint.get("gate_layer"))
        row = constraint.to_dict()
        row.update(
            {
                "queue_display": pkg.get("queue_display", "—"),
                "title_display": pkg.get("title_display", "—"),
                "discipline_display": pkg.get("discipline_display", "—"),
                "crew_display": pkg.get("crew_display", "—"),
                "planned_qty_display": pkg.get("planned_qty_display", "—"),
                "unit_display": pkg.get("unit_display", "—"),
                "required_hours_display": pkg.get("required_hours_display", "—"),
                "plan_value_display": pkg.get(
                    "plan_value_display", money_ru_compact(row_risk_value(constraint))
                ),
                "labor_cost_display": pkg.get("labor_cost_display", "—"),
                "system_display": pkg.get("system_display", "—"),
                "iwp_display": pkg.get("iwp_display", "—"),
                "project_code_display": safe_str(
                    pkg.get("project_code") or constraint.get("project_code")
                ),
                "month_key_display": safe_str(
                    pkg.get("month_key") or constraint.get("month_key")
                ),
                "check_status_ui": CHECK_STATUS_RU.get(status_key, status_key),
                "resolution_status_ui": RESOLUTION_RU.get(resolution_key, resolution_key),
                "responsible_department_ui": dept_ui(constraint.get("responsible_department")),
                "last_decision_display": last_decision_display(constraint),
                "is_crew_economics": gate == "CREW_ECONOMICS",
                "_sort_prio": CHECK_STATUS_PRIORITY.get(status_key, 50),
            }
        )
        rows.append(row)

    result = pd.DataFrame(rows)
    return result.sort_values("_sort_prio").drop(columns=["_sort_prio"])


def check_status_dot_color(status_key: str) -> str:
    if status_key in ("HOLD", "FAIL"):
        return "#dc2626"
    if status_key == "PASS":
        return "#16a34a"
    if status_key == "WARNING":
        return "#ca8a04"
    return "#94a3b8"


def apply_check_quick_action(
    row: pd.Series,
    action: str,
    saver_name: str,
    comment_text: str = "",
) -> Optional[str]:
    constraint_id = safe_str(row.get("constraint_id"))
    if not constraint_id:
        return "У записи нет constraint_id."

    now_iso = datetime.now(timezone.utc).isoformat()
    saver = saver_name or "Пользователь Streamlit"
    dept_label = dept_ui(row.get("responsible_department"))
    existing_comment = safe_str(row.get("comment"))

    if action == "pass":
        note = f"[{now_moscow_text()}] Допущено отделом: {dept_label}"
        payload: Dict[str, Any] = {
            "check_status": "PASS",
            "resolution_status": "RESOLVED",
            "constraint_category": NO_CONSTRAINT_CATEGORY,
            "owner_name": saver,
            "owner_role": "Не требуется",
            "value_at_risk": 0.0,
            "comment": append_action_comment(existing_comment, note),
            "updated_by": saver,
            "last_action_at": now_iso,
            "updated_at": now_iso,
            "resolved_at": now_iso,
            "resolved_by": saver,
            "last_comment_at": now_iso,
        }
    elif action == "hold":
        reason = comment_text.strip()
        if not reason:
            return "Укажите причину блокировки в поле комментария."
        note = f"[{now_moscow_text()}] Заблокировано ({dept_label}): {reason}"
        payload = {
            "check_status": "HOLD",
            "resolution_status": "OPEN",
            "block_reason": reason,
            "root_cause": reason,
            "comment": append_action_comment(existing_comment, note),
            "updated_by": saver,
            "last_action_at": now_iso,
            "updated_at": now_iso,
            "last_comment_at": now_iso,
        }
    elif action == "clarify":
        reason = comment_text.strip()
        if not reason:
            return "Укажите текст уточнения в поле комментария."
        note = f"[{now_moscow_text()}] Требуется уточнение ({dept_label}): {reason}"
        payload = {
            "check_status": "WARNING",
            "resolution_status": "IN_PROGRESS",
            "comment": append_action_comment(existing_comment, note),
            "updated_by": saver,
            "last_action_at": now_iso,
            "updated_at": now_iso,
            "last_comment_at": now_iso,
        }
    else:
        return "Неизвестное действие."

    return update_constraint_record(constraint_id, payload)


def direct_admit_queue_status(status_key: str) -> tuple[str, str, str]:
    """UI label, dot color, text color for queue item."""
    if status_key in ("HOLD", "FAIL"):
        return DIRECT_ADMIT_QUEUE_STATUS["blocked"]
    if status_key == "PASS":
        return DIRECT_ADMIT_QUEUE_STATUS["approved"]
    if status_key == "WARNING":
        return DIRECT_ADMIT_QUEUE_STATUS["clarify"]
    return DIRECT_ADMIT_QUEUE_STATUS["pending"]


def direct_admit_is_pending(status_key: str) -> bool:
    return norm_check_status_key(status_key) in ("ОЖИДАЕТ", "WARNING")


def compute_direct_admit_progress(workbench_df: pd.DataFrame) -> dict[str, int]:
    counts = {"total": 0, "pending": 0, "approved": 0, "blocked": 0, "clarify": 0}
    if workbench_df.empty:
        return counts
    counts["total"] = len(workbench_df)
    for _, row in workbench_df.iterrows():
        status_key = norm_check_status_key(row.get("check_status"))
        if status_key in ("HOLD", "FAIL"):
            counts["blocked"] += 1
        elif status_key == "PASS":
            counts["approved"] += 1
        elif status_key == "WARNING":
            counts["clarify"] += 1
        else:
            counts["pending"] += 1
    return counts


def resolve_direct_admit_selected_cid(
    workbench_df: pd.DataFrame,
    prefer_pending: bool = True,
) -> str:
    if workbench_df.empty:
        return ""
    cids = workbench_df["constraint_id"].astype(str).tolist()
    stored = safe_str(st.session_state.get(DIRECT_ADMIT_SELECTED_CID_KEY))
    if stored in cids:
        return stored
    if prefer_pending:
        for _, row in workbench_df.iterrows():
            if direct_admit_is_pending(row.get("check_status")):
                return safe_str(row.get("constraint_id"))
    return safe_str(workbench_df.iloc[0].get("constraint_id"))


def advance_direct_admit_selection(workbench_df: pd.DataFrame, current_cid: str) -> str:
    if workbench_df.empty:
        return ""
    cids = workbench_df["constraint_id"].astype(str).tolist()
    if current_cid not in cids:
        return resolve_direct_admit_selected_cid(workbench_df)
    start_idx = cids.index(current_cid) + 1
    for cid in cids[start_idx:] + cids[:start_idx]:
        row = workbench_df[workbench_df["constraint_id"].astype(str) == cid].iloc[0]
        if direct_admit_is_pending(row.get("check_status")):
            return cid
    return current_cid


def sort_workbench_for_queue(workbench_df: pd.DataFrame) -> pd.DataFrame:
    """Pending items first; completed (PASS) sink to bottom."""
    if workbench_df.empty:
        return workbench_df
    out = workbench_df.copy()
    out["_da_sort"] = out["check_status"].apply(
        lambda value: CHECK_STATUS_PRIORITY.get(norm_check_status_key(value), 50)
    )
    out = out.sort_values(["_da_sort", "boq_code"], ascending=[True, True])
    return out.drop(columns=["_da_sort"])


def direct_admit_layout_weights() -> list[float]:
    preset = st.session_state.get(DIRECT_ADMIT_LAYOUT_KEY, "Баланс")
    if preset not in DIRECT_ADMIT_LAYOUT_PRESETS:
        preset = "Баланс"
    return DIRECT_ADMIT_LAYOUT_PRESETS[preset]


def resolve_direct_admit_dept_key(department_label: str, row: pd.Series | None) -> str:
    if department_label and department_label != "Все":
        return department_label
    if row is not None:
        return safe_str(row.get("responsible_department"))
    return ""


def direct_admit_criteria_for_department(dept_key: str) -> list[str]:
    if dept_key in DIRECT_ADMIT_CRITERIA_BY_DEPT:
        return DIRECT_ADMIT_CRITERIA_BY_DEPT[dept_key]
    return list(DIRECT_ADMIT_GENERIC_CRITERIA)


def _da_crit_status_key(cid: str, idx: int) -> str:
    return f"da_crit_{cid}_{idx}"


def _da_crit_pct_key(cid: str, idx: int) -> str:
    return f"da_crit_pct_{cid}_{idx}"


def _da_crit_normalize_status(raw: Any) -> str:
    if raw is True:
        return DIRECT_ADMIT_CRIT_STATUS_READY
    if raw is False or raw is None or safe_str(raw) == "":
        return DIRECT_ADMIT_CRIT_STATUS_UNCHECKED
    status = safe_str(raw)
    if status in DIRECT_ADMIT_CRIT_STATUS_UI:
        return status
    return DIRECT_ADMIT_CRIT_STATUS_UNCHECKED


def _da_crit_read_row(cid: str, idx: int) -> tuple[str, int | None]:
    status = _da_crit_normalize_status(st.session_state.get(_da_crit_status_key(cid, idx)))
    pct_raw = st.session_state.get(_da_crit_pct_key(cid, idx))
    pct: int | None = None
    if pct_raw is not None and safe_str(pct_raw) != "":
        try:
            pct = int(float(pct_raw))
            pct = max(0, min(100, pct))
        except (TypeError, ValueError):
            pct = None
    return status, pct


def _da_crit_score_points(status: str, pct: int | None) -> float | None:
    if status == DIRECT_ADMIT_CRIT_STATUS_READY:
        return 100.0
    if status == DIRECT_ADMIT_CRIT_STATUS_PARTIAL:
        return float(pct if pct is not None else 0)
    if status == DIRECT_ADMIT_CRIT_STATUS_RISK:
        return 50.0
    if status == DIRECT_ADMIT_CRIT_STATUS_BLOCKER:
        return 0.0
    return None


def _da_crit_status_label(status: str) -> str:
    return DIRECT_ADMIT_CRIT_STATUS_UI.get(
        status,
        DIRECT_ADMIT_CRIT_STATUS_UI[DIRECT_ADMIT_CRIT_STATUS_UNCHECKED],
    )[0]


def direct_admit_constraint_type_label(value: str) -> str:
    text = safe_str(value)
    if not text:
        return "—"
    return DIRECT_ADMIT_CONSTRAINT_TYPE_LEGACY_RU.get(text, text)


def _da_crit_attention_lines(cid: str, criteria: list[str]) -> list[str]:
    """Строки для блока 4: БЛОКЕР / РИСК / ЧАСТИЧНО из session_state критериев."""
    status_prefix = {
        DIRECT_ADMIT_CRIT_STATUS_BLOCKER: "БЛОКЕР",
        DIRECT_ADMIT_CRIT_STATUS_RISK: "РИСК",
        DIRECT_ADMIT_CRIT_STATUS_PARTIAL: "ЧАСТИЧНО",
    }
    status_order = {
        DIRECT_ADMIT_CRIT_STATUS_BLOCKER: 0,
        DIRECT_ADMIT_CRIT_STATUS_RISK: 1,
        DIRECT_ADMIT_CRIT_STATUS_PARTIAL: 2,
    }
    items: list[tuple[int, int, str]] = []
    for idx, crit_label in enumerate(criteria):
        status, pct = _da_crit_read_row(cid, idx)
        prefix = status_prefix.get(status)
        if not prefix:
            continue
        if status == DIRECT_ADMIT_CRIT_STATUS_PARTIAL and pct is not None:
            line = f"{prefix}: {crit_label} — {pct}%"
        else:
            line = f"{prefix}: {crit_label}"
        items.append((status_order[status], idx, line))
    items.sort(key=lambda item: (item[0], item[1]))
    return [line for _, _, line in items]


def _render_fixation_criteria_attention_section(cid: str, criteria: list[str]) -> None:
    st.markdown("**Критерии, требующие внимания**")
    lines = _da_crit_attention_lines(cid, criteria)
    if not lines:
        st.caption("Блокирующие и рискованные критерии не выявлены.")
        return
    lines_html = "".join(
        f'<div style="font-size:0.78rem;color:#334155;margin:0.1rem 0;line-height:1.35;">'
        f"{html.escape(line)}</div>"
        for line in lines
    )
    st.markdown(
        f'<div class="da-fix-panel" style="padding:0.35rem 0.45rem;">{lines_html}</div>',
        unsafe_allow_html=True,
    )


def _da_crit_status_css_suffix(status: str) -> str:
    return status.lower().replace("_", "-")


def _da_exec_bar_fill_style(score_pct: int, blocker_count: int) -> str:
    if score_pct >= 80 and blocker_count <= 1:
        color = "#2F6B4F"
    elif score_pct >= 50:
        color = "#C4920A"
    else:
        color = "#B45353"
    gradient = "linear-gradient(90deg, #B45353 0%, #C4920A 52%, #2F6B4F 100%)"
    if score_pct >= 80 and blocker_count <= 1:
        fill_bg = color
    elif score_pct >= 50:
        fill_bg = gradient
    else:
        fill_bg = color
    return f"width:{score_pct}%;background:{fill_bg};"


def _da_crit_status_badge_html(status: str, pct: int | None = None) -> str:
    label, color = DIRECT_ADMIT_CRIT_STATUS_UI.get(
        status,
        DIRECT_ADMIT_CRIT_STATUS_UI[DIRECT_ADMIT_CRIT_STATUS_UNCHECKED],
    )
    text = label
    if status == DIRECT_ADMIT_CRIT_STATUS_PARTIAL and pct is not None:
        text = f"{label} {pct}%"
    return (
        f'<div class="da-c2-exec-badge" style="color:{color};">'
        f"{html.escape(text)}</div>"
    )


def direct_admit_criteria_summary(
    cid: str,
    criteria: list[str],
) -> dict[str, Any]:
    counts = {
        DIRECT_ADMIT_CRIT_STATUS_READY: 0,
        DIRECT_ADMIT_CRIT_STATUS_PARTIAL: 0,
        DIRECT_ADMIT_CRIT_STATUS_RISK: 0,
        DIRECT_ADMIT_CRIT_STATUS_BLOCKER: 0,
        DIRECT_ADMIT_CRIT_STATUS_UNCHECKED: 0,
    }
    score_points: list[float] = []
    for idx in range(len(criteria)):
        status, pct = _da_crit_read_row(cid, idx)
        counts[status] = counts.get(status, 0) + 1
        points = _da_crit_score_points(status, pct)
        if points is not None:
            score_points.append(points)
    total = len(criteria) or 1
    score_pct = int(round(sum(score_points) / total)) if score_points else 0
    return {
        "counts": counts,
        "score_pct": score_pct,
        "total": len(criteria),
    }


def direct_admit_criteria_progress(cid: str, criteria: list[str]) -> tuple[int, int]:
    ready = sum(
        1
        for idx in range(len(criteria))
        if _da_crit_read_row(cid, idx)[0] == DIRECT_ADMIT_CRIT_STATUS_READY
    )
    return ready, len(criteria)


def _da_resolve_owner_role(dept_key: str) -> str:
    dept_label = dept_ui(dept_key) if dept_key else ""
    if dept_label in DIRECT_ADMIT_ROLE_OPTIONS:
        return dept_label
    return "Другое"


def build_direct_admit_decision_draft(
    action: str,
    cid: str,
    dept_key: str,
    officer_fio: str,
    criteria: list[str],
) -> dict[str, Any]:
    owner = dept_ui(dept_key) if dept_key else "—"
    decided_at = now_moscow_decision_text()
    owner_role = _da_resolve_owner_role(dept_key)
    if action == "pass":
        return {
            "cid": cid,
            "action": "pass",
            "decision_label": "ДОПУЩЕНО",
            "reason": "Критерии допуска выполнены",
            "action_text": "Включить код в месячный план / разрешить выполнение работ",
            "owner": owner,
            "target_date": date.today(),
            "officer_fio": officer_fio,
            "decided_at_msk": decided_at,
            "owner_role": owner_role,
        }
    if action == "clarify":
        return {
            "cid": cid,
            "action": "clarify",
            "decision_label": "ТРЕБУЕТ УТОЧНЕНИЯ",
            "reason": "Есть непроверенные / частично снятые / рискованные ограничения",
            "action_text": "Запросить уточнение у ответственного отдела",
            "owner": owner,
            "target_date": date.today() + timedelta(days=2),
            "officer_fio": officer_fio,
            "decided_at_msk": decided_at,
            "owner_role": owner_role,
        }
    return {
        "cid": cid,
        "action": "block",
        "decision_label": "ЗАБЛОКИРОВАНО",
        "reason": "",
        "action_text": "Зафиксировать ограничение и назначить корректирующее действие",
        "owner": owner,
        "target_date": date.today(),
        "officer_fio": officer_fio,
        "decided_at_msk": decided_at,
        "owner_role": owner_role,
    }


def format_direct_admit_audit_trail(draft: dict[str, Any]) -> str:
    return (
        f"{draft['decided_at_msk']}\n"
        f"{draft['officer_fio']}\n"
        f"Решение:\n{draft['decision_label']}\n\n"
        f"Причина:\n{draft['reason']}"
    )


def _da_gov_fixation_summary_text(draft: dict[str, Any]) -> str:
    target_text = draft["target_date"].strftime("%d.%m.%Y")
    return (
        f"Тип решения: {draft['decision_label']}\n"
        f"Причина: {draft['reason']}\n"
        f"Действие: {draft['action_text']}\n"
        f"Ответственный: {draft['owner']}\n"
        f"Срок: {target_text}\n"
        f"ФИО принявшего решение: {draft['officer_fio']}\n"
        f"Дата и время: {draft['decided_at_msk']}"
    )


def apply_direct_admit_decision_draft_to_gov(
    prefix: str,
    pending_action: str,
    draft: dict[str, Any],
    cid: str,
) -> None:
    if draft.get("cid") != cid:
        return
    summary = _da_gov_fixation_summary_text(draft)
    if pending_action == "pass":
        st.session_state[f"{prefix}_pass_by"] = draft["officer_fio"]
        st.session_state[f"{prefix}_pass_comment"] = summary
        return
    if pending_action == "clarify":
        st.session_state[f"{prefix}_owner"] = draft["owner"]
        st.session_state[f"{prefix}_role"] = draft["owner_role"]
        st.session_state[f"{prefix}_target"] = draft["target_date"]
        st.session_state[f"{prefix}_desc"] = summary
        return
    st.session_state[f"{prefix}_owner"] = draft["owner"]
    st.session_state[f"{prefix}_role"] = draft["owner_role"]
    st.session_state[f"{prefix}_target"] = draft["target_date"]
    draft_reason = safe_str(draft.get("reason"))
    if draft_reason and not is_generic_block_reason(draft_reason):
        st.session_state[f"{prefix}_block_reason"] = draft_reason
    else:
        st.session_state[f"{prefix}_block_reason"] = ""


def _da_clear_decision_session() -> None:
    st.session_state.pop(DIRECT_ADMIT_DECISION_DRAFT_KEY, None)
    st.session_state.pop(DIRECT_ADMIT_DECISION_FIO_ERROR_KEY, None)
    st.session_state.pop(DIRECT_ADMIT_DECISION_WARN_KEY, None)
    st.session_state.pop(DIRECT_ADMIT_DECISION_RECOMMENDED_KEY, None)


def _da_decision_button_handler(
    action: str,
    cid: str,
    dept_key: str,
    criteria: list[str],
    officer_fio: str,
) -> None:
    if not officer_fio.strip():
        st.session_state[DIRECT_ADMIT_DECISION_FIO_ERROR_KEY] = cid
        return

    summary = direct_admit_criteria_summary(cid, criteria)
    counts = summary["counts"]
    st.session_state.pop(DIRECT_ADMIT_DECISION_FIO_ERROR_KEY, None)
    st.session_state.pop(DIRECT_ADMIT_DECISION_WARN_KEY, None)
    st.session_state.pop(DIRECT_ADMIT_DECISION_RECOMMENDED_KEY, None)

    if action == "pass":
        checked_now, total_now = direct_admit_criteria_progress(cid, criteria)
        if checked_now < total_now:
            st.session_state[DIRECT_ADMIT_CRITERIA_WARN_KEY] = True
        else:
            st.session_state.pop(DIRECT_ADMIT_CRITERIA_WARN_KEY, None)
        if counts[DIRECT_ADMIT_CRIT_STATUS_BLOCKER] > 0:
            st.session_state[DIRECT_ADMIT_DECISION_WARN_KEY] = (
                "Обнаружены блокирующие ограничения"
            )
    elif action == "clarify":
        st.session_state.pop(DIRECT_ADMIT_CRITERIA_WARN_KEY, None)
        partial_risk = (
            counts[DIRECT_ADMIT_CRIT_STATUS_UNCHECKED]
            + counts[DIRECT_ADMIT_CRIT_STATUS_PARTIAL]
            + counts[DIRECT_ADMIT_CRIT_STATUS_RISK]
        )
        if partial_risk > 0:
            st.session_state[DIRECT_ADMIT_DECISION_RECOMMENDED_KEY] = (
                "Рекомендуется уточнение: есть непроверенные, частичные или рискованные критерии"
            )
    else:
        st.session_state.pop(DIRECT_ADMIT_CRITERIA_WARN_KEY, None)

    draft = build_direct_admit_decision_draft(action, cid, dept_key, officer_fio, criteria)
    st.session_state[DIRECT_ADMIT_DECISION_DRAFT_KEY] = draft
    st.session_state[DIRECT_ADMIT_PENDING_ACTION_KEY] = action
    apply_direct_admit_decision_draft_to_gov(f"da_gov_{cid[:8]}", action, draft, cid)


def _render_direct_admit_block_d(
    cid: str,
    criteria: list[str],
    dept_key: str,
) -> None:
    st.markdown('<div class="da-c2-section-title">D. Решение</div>', unsafe_allow_html=True)

    officer_key = f"da_officer_{cid[:8]}"
    officer_fio = st.text_input(
        "ФИО лица, принимающего решение",
        placeholder="Виталий Тронин",
        key=officer_key,
    )
    if safe_str(officer_fio).strip():
        st.session_state.pop(DIRECT_ADMIT_DECISION_FIO_ERROR_KEY, None)
    if st.session_state.get(DIRECT_ADMIT_DECISION_FIO_ERROR_KEY) == cid:
        st.error("Укажите ФИО лица, принимающего решение")

    warn_msg = st.session_state.get(DIRECT_ADMIT_DECISION_WARN_KEY)
    if warn_msg:
        st.warning(warn_msg)
    rec_msg = st.session_state.get(DIRECT_ADMIT_DECISION_RECOMMENDED_KEY)
    if rec_msg:
        st.info(rec_msg)

    a1, a2, a3 = st.columns(3, gap="small")
    with a1:
        with st.container(border=False):
            st.markdown(
                '<span class="da-block-d-btn-pass"></span>'
                '<div class="da-block-d-pass-visual" style="display:flex;align-items:center;'
                'justify-content:center;min-height:34px;padding:0.18rem 0.35rem;border-radius:0.5rem;'
                'background-color:#2F6B4F;border:1px solid #2F6B4F;color:#ffffff;font-size:0.76rem;'
                'font-weight:600;line-height:1.2;text-align:center;">ДОПУСТИТЬ</div>',
                unsafe_allow_html=True,
            )
            if st.button("ДОПУСТИТЬ", key=f"da_act_pass_{cid[:8]}", use_container_width=True):
                officer_value = safe_str(officer_fio).strip() or safe_str(
                    st.session_state.get(officer_key)
                ).strip()
                _da_decision_button_handler(
                    "pass", cid, dept_key, criteria, officer_value
                )
                st.rerun()
    with a2:
        with st.container(border=False):
            st.markdown(
                '<span class="da-block-d-btn-clarify"></span>'
                '<div class="da-block-d-clarify-visual" style="display:flex;align-items:center;'
                'justify-content:center;min-height:34px;padding:0.18rem 0.35rem;border-radius:0.5rem;'
                'background-color:#C4920A;border:1px solid #C4920A;color:#ffffff;font-size:0.76rem;'
                'font-weight:600;line-height:1.2;text-align:center;">ТРЕБУЕТ ДОРАБОТКИ</div>',
                unsafe_allow_html=True,
            )
            if st.button("ТРЕБУЕТ ДОРАБОТКИ", key=f"da_act_clarify_{cid[:8]}", use_container_width=True):
                officer_value = safe_str(officer_fio).strip() or safe_str(
                    st.session_state.get(officer_key)
                ).strip()
                _da_decision_button_handler(
                    "clarify", cid, dept_key, criteria, officer_value
                )
                st.rerun()
    with a3:
        with st.container(border=False):
            st.markdown(
                '<span class="da-block-d-btn-block"></span>'
                '<div class="da-block-d-block-visual" style="display:flex;align-items:center;'
                'justify-content:center;min-height:34px;padding:0.18rem 0.35rem;border-radius:0.5rem;'
                'background-color:#9B3D3D;border:1px solid #9B3D3D;color:#ffffff;font-size:0.76rem;'
                'font-weight:600;line-height:1.2;text-align:center;">ЗАБЛОКИРОВАТЬ</div>',
                unsafe_allow_html=True,
            )
            if st.button("ЗАБЛОКИРОВАТЬ", key=f"da_act_block_{cid[:8]}", use_container_width=True):
                officer_value = safe_str(officer_fio).strip() or safe_str(
                    st.session_state.get(officer_key)
                ).strip()
                _da_decision_button_handler(
                    "block", cid, dept_key, criteria, officer_value
                )
                st.rerun()


def _render_da_criteria_executability_summary(cid: str, criteria: list[str]) -> None:
    summary = direct_admit_criteria_summary(cid, criteria)
    counts = summary["counts"]
    score_pct = summary["score_pct"]
    blocker_count = counts[DIRECT_ADMIT_CRIT_STATUS_BLOCKER]
    bar_style = _da_exec_bar_fill_style(score_pct, blocker_count)
    st.markdown(
        f'<div class="da-c2-exec-summary">'
        f'<span style="color:#2F6B4F;">ГОТОВО: {counts[DIRECT_ADMIT_CRIT_STATUS_READY]}</span>'
        f'<span style="color:#C4920A;">ЧАСТИЧНО: {counts[DIRECT_ADMIT_CRIT_STATUS_PARTIAL]}</span>'
        f'<span style="color:#C2410C;">РИСК: {counts[DIRECT_ADMIT_CRIT_STATUS_RISK]}</span>'
        f'<span style="color:#B45353;">БЛОКЕРЫ: {blocker_count}</span>'
        f"</div>"
        f'<div class="da-c2-exec-score-line">EXECUTABILITY SCORE: {score_pct}%</div>'
        f'<div class="da-c2-exec-bar-track">'
        f'<div class="da-c2-exec-bar-fill" style="{bar_style}"></div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_direct_admit_block_c(
    cid: str,
    criteria: list[str],
    dept_criteria_label: str,
    row: pd.Series,
    saver_name: str,
) -> None:
    st.markdown('<div class="da-c2-section-title">C. Критерии допуска</div>', unsafe_allow_html=True)
    st.caption(dept_criteria_label)
    with st.container(border=True):
        _render_da_criteria_executability_summary(cid, criteria)
        st.markdown(
            '<div class="da-c2-matrix-head"><span>Критерий</span><span>Статус</span></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<span class="da-c2-matrix-marker"></span>', unsafe_allow_html=True)
        for crit_idx, crit_label in enumerate(criteria):
            status_key = _da_crit_status_key(cid, crit_idx)
            pct_key = _da_crit_pct_key(cid, crit_idx)
            current_status, current_pct = _da_crit_read_row(cid, crit_idx)
            crit_col, badge_col, ctrl_col = st.columns([0.46, 0.24, 0.30], gap="small")
            with crit_col:
                st.markdown(
                    f'<div class="da-c2-crit-label">{html.escape(crit_label)}</div>',
                    unsafe_allow_html=True,
                )
                if crit_label == DIRECT_ADMIT_OTHER_CRITERION_LABEL:
                    other_text = st.text_input(
                        "Прочее ограничение",
                        value="",
                        placeholder="Опишите ограничение вручную…",
                        key=f"da_crit_other_text_{cid}",
                        label_visibility="collapsed",
                    )
                    if st.button(
                        "Сохранить ограничение",
                        key=f"da_crit_other_save_{cid}",
                        use_container_width=True,
                    ):
                        err = apply_check_quick_action(
                            row,
                            "clarify",
                            saver_name,
                            other_text,
                        )
                        if err:
                            st.warning(err)
                        else:
                            st.cache_data.clear()
                            st.success("Ограничение сохранено в реестр проверки.")
                            st.rerun()
            with ctrl_col:
                try:
                    status_index = DIRECT_ADMIT_CRIT_STATUS_ORDER.index(current_status)
                except ValueError:
                    status_index = 0
                selected_status = st.selectbox(
                    "Статус",
                    DIRECT_ADMIT_CRIT_STATUS_ORDER,
                    index=status_index,
                    format_func=_da_crit_status_label,
                    key=status_key,
                    label_visibility="collapsed",
                )
                st.markdown(
                    f'<span class="da-c2-crit-ctrl-marker da-c2-crit-{_da_crit_status_css_suffix(selected_status)}"></span>',
                    unsafe_allow_html=True,
                )
                selected_pct: int | None = None
                if selected_status == DIRECT_ADMIT_CRIT_STATUS_PARTIAL:
                    selected_pct = int(
                        st.number_input(
                            "%",
                            min_value=0,
                            max_value=100,
                            value=current_pct if current_pct is not None else 0,
                            step=5,
                            key=pct_key,
                            label_visibility="collapsed",
                        )
                    )
            with badge_col:
                st.markdown(
                    _da_crit_status_badge_html(selected_status, selected_pct),
                    unsafe_allow_html=True,
                )
        summary = direct_admit_criteria_summary(cid, criteria)
        st.markdown(
            f'<div class="da-c2-score">EXECUTABILITY SCORE: {summary["score_pct"]}%</div>',
            unsafe_allow_html=True,
        )


def direct_admit_mtr_cost_display(row: pd.Series) -> str:
    for field in ("mtr_cost_display", "mtr_cost_value", "mtr_cost", "material_cost"):
        raw = row.get(field)
        if has_meaningful_value(raw):
            try:
                return format_money_display(safe_num(raw))
            except Exception:  # noqa: BLE001
                return field_display(raw)
    return "—"


def _render_da_compact_grid_html(cells: list[tuple[str, str]], *, columns: int = 2) -> str:
    """Compact label/value metric grid for center pane (rendering only)."""
    if not cells:
        return ""
    col_w = max(1, min(columns, 3))
    rows_html: list[str] = []
    for row_start in range(0, len(cells), col_w):
        chunk = cells[row_start : row_start + col_w]
        cells_html = []
        for label, value in chunk:
            lbl = html.escape(label)
            val = html.escape(value or "—")
            cells_html.append(
                f'<div class="da-c2-cell">'
                f'<div class="da-c2-label">{lbl}</div>'
                f'<div class="da-c2-value">{val}</div>'
                f"</div>"
            )
        while len(cells_html) < col_w:
            cells_html.append('<div class="da-c2-cell da-c2-cell-empty"></div>')
        rows_html.append(f'<div class="da-c2-row da-c2-cols-{col_w}">{"".join(cells_html)}</div>')
    return f'<div class="da-c2-grid">{"".join(rows_html)}</div>'


def _da_center_status_badge_html(status_key: str, queue_label: str, queue_text_color: str) -> str:
    label = html.escape(queue_label.upper())
    return (
        f'<span class="da-c2-status-badge" style="color:{queue_text_color};">'
        f"{label}</span>"
    )


def _da_center_pills_html(pills: list[str]) -> str:
    items = [
        f'<span class="da-c2-pill">{html.escape(p)}</span>'
        for p in pills
        if p and p != "—"
    ]
    if not items:
        return ""
    return f'<div class="da-c2-pills">{"".join(items)}</div>'


def _da_center_pane_styles() -> str:
    return """
    <style>
    .da-c2-header {
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        background: #f8fafc;
        padding: 0.45rem 0.55rem 0.4rem 0.55rem;
        margin-bottom: 0.35rem;
    }
    .da-c2-header-top {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    .da-c2-code {
        font-size: 1.05rem;
        font-weight: 700;
        color: #0f172a;
        letter-spacing: 0.01em;
        line-height: 1.15;
    }
    .da-c2-status-badge {
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        white-space: nowrap;
    }
    .da-c2-title {
        font-size: 0.82rem;
        font-weight: 600;
        color: #1e293b;
        margin-top: 0.18rem;
        line-height: 1.25;
        white-space: normal;
        word-break: break-word;
    }
    .da-c2-desc {
        font-size: 0.72rem;
        color: #64748b;
        margin-top: 0.12rem;
        line-height: 1.3;
    }
    .da-c2-pills {
        display: flex;
        flex-wrap: wrap;
        gap: 0.25rem;
        margin-top: 0.28rem;
    }
    .da-c2-pill {
        display: inline-block;
        font-size: 0.66rem;
        font-weight: 600;
        color: #475569;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 999px;
        padding: 0.08rem 0.42rem;
        line-height: 1.2;
    }
    .da-c2-section-title {
        font-size: 0.74rem;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin: 0.28rem 0 0.18rem 0;
    }
    .da-c2-panel {
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        background: #ffffff;
        padding: 0.35rem 0.4rem 0.3rem 0.4rem;
        margin-bottom: 0.25rem;
    }
    .da-c2-ab-outer {
        display: flex;
        align-items: stretch;
        gap: 0.35rem;
        margin-bottom: 0.25rem;
    }
    .da-c2-ab-side {
        flex: 1 1 0;
        min-width: 0;
        display: flex;
        flex-direction: column;
    }
    .da-c2-ab-panel {
        flex: 1 1 auto;
        margin-bottom: 0;
    }
    .da-c2-grid { width: 100%; }
    .da-c2-row {
        display: grid;
        gap: 0.28rem;
        margin-bottom: 0.22rem;
    }
    .da-c2-row:last-child { margin-bottom: 0; }
    .da-c2-cols-2 { grid-template-columns: 1fr 1fr; }
    .da-c2-cols-3 { grid-template-columns: 1fr 1fr 1fr; }
    .da-c2-cell {
        border: 1px solid #f1f5f9;
        border-radius: 4px;
        background: #fafbfc;
        padding: 0.22rem 0.32rem;
        min-height: 2.1rem;
    }
    .da-c2-cell-empty {
        visibility: hidden;
        border-color: transparent;
        background: transparent;
    }
    .da-c2-label {
        font-size: 0.62rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        line-height: 1.15;
    }
    .da-c2-value {
        font-size: 0.78rem;
        font-weight: 600;
        color: #0f172a;
        line-height: 1.25;
        margin-top: 0.06rem;
        word-break: break-word;
    }
    .da-c2-matrix-head {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 0.35rem;
        font-size: 0.62rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        padding: 0 0.05rem 0.18rem 0.05rem;
        border-bottom: 1px solid #f1f5f9;
        margin-bottom: 0.12rem;
    }
    .da-c2-matrix-row {
        display: grid;
        grid-template-columns: 1fr auto auto;
        gap: 0.35rem;
        align-items: center;
        padding: 0.14rem 0.05rem;
        border-bottom: 1px solid #f8fafc;
    }
    .da-c2-matrix-row:last-child { border-bottom: none; }
    .da-c2-crit-label {
        font-size: 0.85rem;
        color: #334155;
        line-height: 1.25;
    }
    .da-c2-exec-badge {
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        white-space: nowrap;
    }
    [data-testid="column"]:has(.da-c2-crit-ctrl-marker) [data-testid="stSelectbox"] [data-baseweb="select"] span {
        font-size: 0.74rem !important;
    }
    [data-testid="column"]:has(.da-c2-crit-ready) [data-testid="stSelectbox"] div[data-baseweb="select"] {
        border-color: #2F6B4F !important;
    }
    [data-testid="column"]:has(.da-c2-crit-partial) [data-testid="stSelectbox"] div[data-baseweb="select"] {
        border-color: #C4920A !important;
    }
    [data-testid="column"]:has(.da-c2-crit-risk) [data-testid="stSelectbox"] div[data-baseweb="select"] {
        border-color: #C2410C !important;
    }
    [data-testid="column"]:has(.da-c2-crit-blocker) [data-testid="stSelectbox"] div[data-baseweb="select"] {
        border-color: #B45353 !important;
    }
    [data-testid="column"]:has(.da-c2-crit-unchecked) [data-testid="stSelectbox"] div[data-baseweb="select"] {
        border-color: #94a3b8 !important;
    }
    [data-testid="column"]:has(.da-c2-crit-ready) [data-testid="stSelectbox"] span {
        color: #2F6B4F !important;
    }
    [data-testid="column"]:has(.da-c2-crit-partial) [data-testid="stSelectbox"] span {
        color: #C4920A !important;
    }
    [data-testid="column"]:has(.da-c2-crit-risk) [data-testid="stSelectbox"] span {
        color: #C2410C !important;
    }
    [data-testid="column"]:has(.da-c2-crit-blocker) [data-testid="stSelectbox"] span {
        color: #B45353 !important;
    }
    [data-testid="column"]:has(.da-c2-crit-unchecked) [data-testid="stSelectbox"] span {
        color: #64748b !important;
    }
    .da-c2-exec-summary {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        font-size: 0.68rem;
        font-weight: 600;
        color: #475569;
        margin-bottom: 0.18rem;
    }
    .da-c2-exec-score-line {
        font-size: 0.72rem;
        font-weight: 700;
        color: #1e40af;
        margin-bottom: 0.15rem;
    }
    .da-c2-exec-bar-track {
        height: 6px;
        background: #e2e8f0;
        border-radius: 4px;
        overflow: hidden;
        margin-bottom: 0.22rem;
    }
    .da-c2-exec-bar-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.15s ease;
    }
    .da-c2-score {
        font-size: 0.72rem;
        font-weight: 700;
        color: #1e40af;
        margin-top: 0.22rem;
        padding-top: 0.18rem;
        border-top: 1px solid #f1f5f9;
    }
    [data-testid="column"]:has(.da-c2-matrix-marker) [data-testid="stCheckbox"] {
        margin-top: 0 !important;
    }
    [data-testid="column"]:has(.da-c2-matrix-marker) [data-testid="stCheckbox"] label {
        min-height: 0 !important;
    }
    #da-center-scroll-host {
        display: none;
    }
    </style>
    """


def _da_center_optional_field(row: pd.Series, *keys: str) -> str:
    for key in keys:
        val = row.get(key)
        if has_meaningful_value(val):
            return field_display(val)
    return "—"


def render_direct_admit_module_header(
    department_label: str,
    progress: dict[str, int],
) -> None:
    if department_label != "Все":
        dept_full = dept_ui(department_label)
        if " / " in dept_full:
            dept_chip_name, dept_role = dept_full.split(" / ", 1)
            dept_chip_name = dept_chip_name.strip()
            dept_role = dept_role.strip()
        else:
            dept_chip_name = dept_full
            dept_role = DEPARTMENT_RU.get(department_label, "")
            if dept_role == dept_chip_name:
                dept_role = "Контур допуска выбранного отдела"
    else:
        dept_chip_name = "Все отделы"
        dept_role = "Выберите отдел допуска в фильтрах, чтобы работать от имени конкретного отдела."

    st.markdown(
        f'<div class="da-dept-chip-card"><div class="da-dept-chip-label">ВЫБРАН ОТДЕЛ ДОПУСКА</div>'
        f'<div class="da-dept-chip-name">{html.escape(dept_chip_name)}</div></div>',
        unsafe_allow_html=True,
    )
    if department_label == "Все":
        st.caption(dept_role)
    st.caption(
        "Очередь → решение → фиксация. Выберите код слева, проверьте критерии в центре, "
        "зафиксируйте решение справа."
    )
    st.caption(
        f"Всего в очереди: **{progress['total']}** · "
        f"Осталось: **{progress['pending']}** · "
        f"Допущено: **{progress['approved']}** · "
        f"Заблокировано: **{progress['blocked']}** · "
        f"Уточнение: **{progress['clarify']}**"
    )


def _render_fixation_context_section(row: pd.Series, prefix: str) -> None:
    dept_pill = field_display(row.get("responsible_department_ui"))
    if dept_pill == "—":
        dept_pill = dept_ui(row.get("responsible_department"))

    status_key = norm_check_status_key(row.get("check_status"))
    status_label, _, _ = direct_admit_queue_status(status_key)
    status_display = field_display(row.get("check_status_ui"))
    if status_display == "—":
        status_display = status_label

    severity_raw = safe_str(row.get("severity"))
    severity_display = "—"
    if severity_raw:
        severity_display = SEVERITY_RU.get(
            norm_tech_value(severity_raw, SEVERITY_OPTIONS, SEVERITY_RU, "MEDIUM"),
            severity_raw,
        )
    sev_saved = safe_str(st.session_state.get(f"{prefix}_sev"))
    if sev_saved:
        severity_display = SEVERITY_RU.get(sev_saved, sev_saved)

    impact_display = safe_str(st.session_state.get(f"{prefix}_mvp_impact")) or "—"

    cells = [
        ("BOQ-код", field_display(row.get("boq_code"))),
        ("Наименование работ", field_display(row.get("boq_name"))),
        ("Отдел допуска", dept_pill),
        ("Статус допуска", status_display),
        ("Критичность", severity_display),
        ("Влияние", impact_display),
    ]
    st.markdown(
        f'<div class="da-fix-panel">{_render_da_compact_grid_html(cells, columns=2)}</div>',
        unsafe_allow_html=True,
    )
    st.caption("Полный контекст см. в блоке **2. Решение по коду**")


def _sync_fixation_blocks_to_governance_keys(
    prefix: str,
    saver_name: str,
    draft: dict[str, Any],
    cid: str,
    row: pd.Series,
) -> None:
    """UI-only: подставляет block 2/3 в скрытые ключи block 5 для save."""
    owner_side = safe_str(st.session_state.get(f"{prefix}_mvp_owner_side")).strip()
    owner_detail = safe_str(st.session_state.get(f"{prefix}_mvp_owner_detail")).strip()

    role_key = f"{prefix}_role"
    if owner_side:
        st.session_state[role_key] = owner_side
    elif role_key not in st.session_state or not safe_str(st.session_state.get(role_key)).strip():
        if draft.get("cid") == cid and safe_str(draft.get("owner_role")).strip():
            st.session_state[role_key] = draft["owner_role"]
        else:
            st.session_state[role_key] = "Другое"

    owner_key = f"{prefix}_owner"
    if owner_detail:
        st.session_state[owner_key] = owner_detail
    elif owner_key not in st.session_state or not safe_str(st.session_state.get(owner_key)).strip():
        fallback = ""
        if draft.get("cid") == cid:
            fallback = safe_str(draft.get("owner")).strip()
        if not fallback:
            fallback = safe_str(row.get("owner_name")).strip()
        if not fallback:
            fallback = saver_name
        st.session_state[owner_key] = fallback

    desc_key = f"{prefix}_desc"
    impediment = safe_str(st.session_state.get(f"{prefix}_mvp_impediment")).strip()
    if impediment and not safe_str(st.session_state.get(desc_key)).strip():
        st.session_state[desc_key] = impediment


_DIRECT_ADMIT_JOURNAL_LINE_RE = re.compile(
    r"^\[(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})\]\s*(.+)$"
)
_DIRECT_ADMIT_AUDIT_SUMMARY_PREFIXES = (
    "Тип решения:",
    "Причина:",
    "Действие:",
    "Ответственный:",
    "Срок:",
    "ФИО принявшего решение:",
    "Дата и время:",
    "Решение:",
)


def _direct_admit_governance_decision_label(status_key: str) -> str:
    if status_key == "PASS":
        return "Допуск"
    if status_key == "WARNING":
        return "Требует доработки"
    if status_key in ("HOLD", "FAIL"):
        return "Блокировка"
    return "—"


def _direct_admit_audit_reason(row: pd.Series) -> str:
    for col in ("block_reason", "root_cause"):
        text = safe_str(row.get(col)).strip()
        if text:
            return text
    return ""


def _direct_admit_classify_journal_action(text: str) -> str:
    lower = text.lower()
    if "допущено" in lower:
        return "Допуск"
    if "уточнение" in lower or "доработ" in lower:
        return "Требует доработки"
    if "заблокировано" in lower or "блокир" in lower:
        return "Блокировка"
    return "Действие"


def _direct_admit_comment_journal(comment_raw: str) -> list[dict[str, str]]:
    comment = safe_str(comment_raw).strip()
    if not comment:
        return []
    events: list[dict[str, str]] = []
    for line in comment.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _DIRECT_ADMIT_JOURNAL_LINE_RE.match(stripped)
        if not match:
            continue
        body = match.group(2).strip()
        events.append(
            {
                "datetime_msk": f"{match.group(1)} МСК",
                "author": "—",
                "action": _direct_admit_classify_journal_action(body),
                "comment": body,
            }
        )
    return events


def _direct_admit_comment_free_text(
    comment_raw: str,
    reason: str,
    journal_events: list[dict[str, str]],
) -> str:
    comment = safe_str(comment_raw).strip()
    if not comment:
        return ""
    event_bodies = {event["comment"] for event in journal_events}
    remaining: list[str] = []
    for line in comment.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _DIRECT_ADMIT_JOURNAL_LINE_RE.match(stripped):
            continue
        if any(stripped.startswith(prefix) for prefix in _DIRECT_ADMIT_AUDIT_SUMMARY_PREFIXES):
            continue
        if stripped in event_bodies:
            continue
        if reason and stripped == reason:
            continue
        remaining.append(stripped)
    return "\n".join(remaining).strip()


def _render_fixation_audit_journal_table(
    journal_events: list[dict[str, str]],
    trailing_note: str = "",
) -> None:
    rows_html: list[str] = []
    for event in reversed(journal_events):
        rows_html.append(
            "<tr>"
            f'<td style="padding:0.25rem 0.35rem;vertical-align:top;white-space:nowrap;">'
            f"{html.escape(event['datetime_msk'])}</td>"
            f'<td style="padding:0.25rem 0.35rem;vertical-align:top;">'
            f"{html.escape(event['author'])}</td>"
            f'<td style="padding:0.25rem 0.35rem;vertical-align:top;">'
            f"{html.escape(event['action'])}</td>"
            f'<td style="padding:0.25rem 0.35rem;vertical-align:top;white-space:pre-wrap;">'
            f"{html.escape(event['comment'])}</td>"
            "</tr>"
        )
    table_html = (
        '<table style="width:100%;border-collapse:collapse;font-size:0.78rem;color:#334155;">'
        "<thead><tr>"
        '<th style="text-align:left;padding:0.25rem 0.35rem;color:#64748b;font-weight:600;">'
        "Дата / время</th>"
        '<th style="text-align:left;padding:0.25rem 0.35rem;color:#64748b;font-weight:600;">'
        "Автор</th>"
        '<th style="text-align:left;padding:0.25rem 0.35rem;color:#64748b;font-weight:600;">'
        "Действие</th>"
        '<th style="text-align:left;padding:0.25rem 0.35rem;color:#64748b;font-weight:600;">'
        "Комментарий</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table>"
    )
    st.markdown(
        f'<div class="da-fix-panel" style="padding:0.35rem 0.45rem;overflow-x:auto;">'
        f"{table_html}</div>",
        unsafe_allow_html=True,
    )
    if trailing_note:
        st.markdown(
            f'<div class="da-fix-panel" style="padding:0.35rem 0.45rem;font-size:0.78rem;'
            f'color:#334155;line-height:1.35;white-space:pre-wrap;margin-top:0.35rem;">'
            f"{html.escape(trailing_note)}</div>",
            unsafe_allow_html=True,
        )


def _render_fixation_classification_pass_info() -> None:
    st.info(
        "Ограничения отсутствуют.\n\n"
        "Код готов к включению в месячный план."
    )


def _render_fixation_plan_pass_info() -> None:
    st.info("Дополнительные мероприятия не требуются.")


def _render_fixation_classification_section(prefix: str) -> None:
    st.caption(
        "Классификация и владелец (session_state). "
        "Категория и критичность для сохранения — в блоке 5."
    )
    st.selectbox(
        "Происхождение ограничения",
        DIRECT_ADMIT_FIXATION_ORIGIN_OPTIONS,
        key=f"{prefix}_mvp_origin",
    )
    st.selectbox(
        "Сторона-владелец ограничения",
        DIRECT_ADMIT_FIXATION_OWNER_SIDE_OPTIONS,
        index=None,
        placeholder="Выберите сторону-владельца",
        key=f"{prefix}_mvp_owner_side",
    )
    st.text_input(
        "Конкретный владелец / подразделение / ФИО",
        placeholder="Например: Тихонин Николай / ПТО ГП / отдел МТО",
        key=f"{prefix}_mvp_owner_detail",
    )
    st.selectbox(
        "Влияние",
        DIRECT_ADMIT_FIXATION_IMPACT_OPTIONS,
        key=f"{prefix}_mvp_impact",
    )


def _render_fixation_plan_section(
    prefix: str,
    row: pd.Series,
) -> None:
    st.caption(
        "Рабочий план снятия ограничения (session_state). "
        "Официальный срок фиксации — в блоке **5. Какое решение официально фиксируем**."
    )
    control_key = f"{prefix}_mvp_next_control"
    if control_key not in st.session_state:
        st.session_state[control_key] = date.today()
    st.text_area(
        "Что мешает выполнить работу",
        key=f"{prefix}_mvp_impediment",
        height=68,
        placeholder="Кратко опишите препятствие",
    )
    st.text_area(
        "Что необходимо сделать",
        key=f"{prefix}_mvp_action",
        height=68,
        placeholder="Конкретные шаги для снятия ограничения",
    )
    st.date_input(
        "Следующий контроль",
        key=control_key,
    )
    st.caption(f"Выбрано: {format_date_any_ru(st.session_state.get(control_key))}")


def _render_fixation_audit_content(
    row: pd.Series,
    cid: str = "",
    criteria: list[str] | None = None,
) -> None:
    status_key = norm_check_status_key(row.get("check_status"))
    queue_label, _, _ = direct_admit_queue_status(status_key)
    decision_label = _direct_admit_governance_decision_label(status_key)
    updated_by = audit_last_updated_by(row) or safe_str(row.get("resolved_by"))
    updated_by_display = field_display(updated_by)
    updated_at_display = format_datetime_moscow(audit_last_updated_at(row))
    owner_display = field_display(row.get("owner_name"))
    target_text = format_date_any_ru(row.get("target_resolution_date"))
    reason_raw = _direct_admit_audit_reason(row)
    reason_display = field_display(reason_raw)

    comment_raw = safe_str(row.get("comment"))
    journal_events = _direct_admit_comment_journal(comment_raw)
    if journal_events and updated_by_display != "—":
        journal_events[-1]["author"] = updated_by_display

    if journal_events:
        last_action_display = journal_events[-1]["comment"]
    elif decision_label != "—":
        last_action_display = decision_label
    else:
        last_action_display = "—"

    st.markdown("**A. Текущее состояние**")
    state_cells = [
        ("Статус допуска", queue_label),
        ("Последнее действие", last_action_display),
        ("Решение", decision_label),
        ("Инициатор / кто зафиксировал", updated_by_display),
        ("Дата / время (МСК)", updated_at_display),
        ("Владелец ограничения", owner_display),
        ("Срок ответа / снятия", target_text),
        ("Причина", reason_display),
    ]
    st.markdown(
        f'<div class="da-fix-panel">{_render_da_compact_grid_html(state_cells, columns=2)}</div>',
        unsafe_allow_html=True,
    )

    if cid and criteria is not None:
        _render_fixation_criteria_attention_section(cid, criteria)

    st.markdown("**B. Журнал действий**")
    free_text = _direct_admit_comment_free_text(comment_raw, reason_raw, journal_events)
    if journal_events:
        _render_fixation_audit_journal_table(journal_events, free_text)
    elif free_text:
        st.markdown(
            f'<div class="da-fix-panel" style="padding:0.35rem 0.45rem;font-size:0.78rem;'
            f'color:#334155;line-height:1.35;white-space:pre-wrap;">'
            f"{html.escape(free_text)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Записей в журнале пока нет.")

    st.markdown("**C. История по BOQ-коду**")
    st.caption(
        "Полная межмесячная история по BOQ-коду будет доступна после подключения журнала ограничений."
    )


def _render_fixation_decision_section(
    row: pd.Series,
    prefix: str,
    cid: str,
    pending_action: str,
    saver_name: str,
    workbench_df: pd.DataFrame,
) -> None:
    if not pending_action:
        st.info(
            "Выберите решение в центре: Допустить, Требует доработки или Заблокировать."
        )
        return

    draft = st.session_state.get(DIRECT_ADMIT_DECISION_DRAFT_KEY) or {}

    if pending_action == "pass":
        st.markdown(
            "Код допускается к включению в месячный план.\n\n"
            "Данное решение будет официально зафиксировано в контуре допуска."
        )
    elif pending_action == "clarify":
        st.markdown(
            "Код не может быть допущен без дополнительной проработки.\n\n"
            "Данное решение будет официально зафиксировано в контуре допуска."
        )
    elif pending_action == "block":
        st.markdown(
            "Код не может быть допущен до устранения ограничения.\n\n"
            "Данное решение будет официально зафиксировано в контуре допуска."
        )

    if draft.get("cid") == cid:
        st.caption(f"Решение принято: {draft.get('decided_at_msk', now_moscow_decision_text())}")

    if pending_action == "pass":
        pass_by_key = f"{prefix}_pass_by"
        pass_comment_key = f"{prefix}_pass_comment"
        if pass_by_key not in st.session_state:
            st.session_state[pass_by_key] = saver_name
        if pass_comment_key not in st.session_state:
            st.session_state[pass_comment_key] = ""
        st.markdown("**Допуск**")
        comment = st.text_area(
            "Комментарий (необязательно)",
            key=pass_comment_key,
            height=72,
        )
        admitted_by = st.text_input(
            "Кто допустил",
            key=pass_by_key,
        )
        if not (draft.get("cid") == cid):
            st.caption(f"Время фиксации: {now_moscow_text()} (МСК)")
        if st.button("Сохранить допуск", type="primary", key=f"{prefix}_save_pass"):
            officer = admitted_by.strip()
            if not officer:
                st.error("Укажите ФИО лица, принимающего решение")
            else:
                save_comment = comment.strip()
                if draft.get("cid") == cid:
                    audit = format_direct_admit_audit_trail(draft)
                    if audit not in save_comment:
                        save_comment = (
                            f"{audit}\n\n{save_comment}" if save_comment else audit
                        )
                err = save_direct_admission_decision(
                    row,
                    "pass",
                    officer,
                    comment=save_comment,
                    owner_name=officer,
                )
                if err:
                    st.error(err)
                else:
                    st.cache_data.clear()
                    st.session_state.pop(DIRECT_ADMIT_PENDING_ACTION_KEY, None)
                    _da_clear_decision_session()
                    st.session_state[DIRECT_ADMIT_SELECTED_CID_KEY] = advance_direct_admit_selection(
                        workbench_df,
                        cid,
                    )
                    st.rerun()
        if st.button("Отмена", key=f"{prefix}_cancel_pass"):
            st.session_state.pop(DIRECT_ADMIT_PENDING_ACTION_KEY, None)
            _da_clear_decision_session()
            st.rerun()
        return

    dept = safe_str(row.get("responsible_department"))
    category_opts = category_options_for_department(dept, "Другое")
    merged_types = list(
        dict.fromkeys([*DIRECT_ADMIT_CONSTRAINT_TYPE_OPTIONS, *category_opts[:6]])
    )

    _sync_fixation_blocks_to_governance_keys(prefix, saver_name, draft, cid, row)

    if pending_action == "clarify":
        target_label = "Срок ответа / снятия"
        save_label = "Зафиксировать уточнение"
    else:
        target_label = "Срок ответа / снятия"
        save_label = "Зафиксировать блокировку"

    target_key = f"{prefix}_target"
    desc_key = f"{prefix}_desc"
    block_reason_key = f"{prefix}_block_reason"
    if target_key not in st.session_state:
        st.session_state[target_key] = (
            safe_date(row.get("target_resolution_date")) or date.today()
        )
    if desc_key not in st.session_state:
        st.session_state[desc_key] = ""
    if pending_action == "block" and block_reason_key not in st.session_state:
        st.session_state[block_reason_key] = ""

    owner_side_hint = safe_str(st.session_state.get(f"{prefix}_mvp_owner_side"))
    owner_detail_hint = safe_str(st.session_state.get(f"{prefix}_mvp_owner_detail"))
    if owner_side_hint or owner_detail_hint:
        owner_parts = [p for p in (owner_side_hint, owner_detail_hint) if p]
        st.caption(f"Владелец для сохранения: {' · '.join(owner_parts)}")

    constraint_type = st.selectbox(
        "Категория для фиксации в реестре допуска",
        merged_types,
        key=f"{prefix}_ctype",
        format_func=direct_admit_constraint_type_label,
    )
    st.caption(
        "Выберите обобщённую категорию, под которой решение будет сохранено в контуре допуска."
    )
    if pending_action == "block":
        st.text_area(
            "Причина блокировки",
            key=block_reason_key,
            height=140,
            placeholder="Укажите конкретную причину блокировки",
        )
        st.markdown(DIRECT_ADMIT_BLOCK_REASON_HELP)
    st.text_area(
        "Описание для фиксации",
        key=desc_key,
        height=220,
        placeholder="Опишите суть ограничения и требуемое действие",
    )
    if pending_action == "block":
        st.markdown(DIRECT_ADMIT_BLOCK_DESCRIPTION_HELP)
    st.date_input(
        target_label,
        key=target_key,
    )
    st.caption(f"Выбрано: {format_date_any_ru(st.session_state.get(f'{prefix}_target'))}")
    severity = st.selectbox(
        "Критичность",
        DIRECT_ADMIT_SEVERITY_OPTIONS,
        format_func=lambda v: SEVERITY_RU.get(v, v),
        index=1,
        key=f"{prefix}_sev",
    )

    btn_col, cancel_col = st.columns(2)
    if btn_col.button(save_label, type="primary", key=f"{prefix}_save_gov"):
        _sync_fixation_blocks_to_governance_keys(prefix, saver_name, draft, cid, row)
        decision_officer = ""
        if draft.get("cid") == cid:
            decision_officer = safe_str(draft.get("officer_fio")).strip()
        if not decision_officer:
            decision_officer = safe_str(st.session_state.get(f"da_officer_{cid[:8]}")).strip()
        if not decision_officer:
            st.error("Укажите ФИО лица, принимающего решение")
        elif pending_action == "block":
            user_block_reason = safe_str(st.session_state.get(f"{prefix}_block_reason")).strip()
            user_description = safe_str(st.session_state.get(f"{prefix}_desc")).strip()
            validation_failed = False
            if not user_block_reason or is_generic_block_reason(user_block_reason):
                st.error(DIRECT_ADMIT_BLOCK_REASON_VALIDATION_ERROR)
                validation_failed = True
            if is_insufficient_block_description(user_description):
                st.error(DIRECT_ADMIT_BLOCK_DESCRIPTION_VALIDATION_ERROR)
                validation_failed = True
            if not validation_failed:
                save_description = user_description
                save_block_reason = user_block_reason
                if draft.get("cid") == cid:
                    audit = format_direct_admit_audit_trail(
                        {**draft, "reason": user_block_reason}
                    )
                    if audit not in save_description:
                        save_description = (
                            f"{audit}\n\n{save_description}" if save_description else audit
                        )
                err = save_direct_admission_decision(
                    row,
                    pending_action,
                    decision_officer,
                    constraint_type=constraint_type,
                    owner_role=safe_str(st.session_state.get(f"{prefix}_role")),
                    owner_name=(
                        safe_str(st.session_state.get(f"{prefix}_owner")).strip()
                        or safe_str(draft.get("owner"))
                    ),
                    description=save_description,
                    block_reason=save_block_reason,
                    target_date=st.session_state.get(f"{prefix}_target"),
                    severity=severity,
                )
                if err:
                    st.warning(err)
                else:
                    st.cache_data.clear()
                    st.session_state.pop(DIRECT_ADMIT_PENDING_ACTION_KEY, None)
                    _da_clear_decision_session()
                    st.session_state[DIRECT_ADMIT_SELECTED_CID_KEY] = advance_direct_admit_selection(
                        workbench_df,
                        cid,
                    )
                    st.rerun()
        else:
            save_description = safe_str(st.session_state.get(f"{prefix}_desc")).strip()
            save_block_reason = safe_str(st.session_state.get(f"{prefix}_block_reason")).strip()
            if draft.get("cid") == cid:
                audit = format_direct_admit_audit_trail(draft)
                if audit not in save_description:
                    save_description = (
                        f"{audit}\n\n{save_description}" if save_description else audit
                    )
            err = save_direct_admission_decision(
                row,
                pending_action,
                decision_officer,
                constraint_type=constraint_type,
                owner_role=safe_str(st.session_state.get(f"{prefix}_role")),
                owner_name=(
                    safe_str(st.session_state.get(f"{prefix}_owner")).strip()
                    or safe_str(draft.get("owner"))
                ),
                description=save_description,
                block_reason=save_block_reason,
                target_date=st.session_state.get(f"{prefix}_target"),
                severity=severity,
            )
            if err:
                st.warning(err)
            else:
                st.cache_data.clear()
                st.session_state.pop(DIRECT_ADMIT_PENDING_ACTION_KEY, None)
                _da_clear_decision_session()
                st.session_state[DIRECT_ADMIT_SELECTED_CID_KEY] = advance_direct_admit_selection(
                    workbench_df,
                    cid,
                )
                st.rerun()
    if cancel_col.button("Отмена", key=f"{prefix}_cancel"):
        st.session_state.pop(DIRECT_ADMIT_PENDING_ACTION_KEY, None)
        _da_clear_decision_session()
        st.rerun()


def _render_fixation_mvp_blocks_1_4(
    row: pd.Series,
    prefix: str,
    pending_action: str,
) -> None:
    with st.expander("1. Контекст кода", expanded=True):
        _render_fixation_context_section(row, prefix)

    with st.expander("2. Кто владеет проблемой и откуда она пришла", expanded=True):
        if pending_action == "pass":
            _render_fixation_classification_pass_info()
        else:
            _render_fixation_classification_section(prefix)

    with st.expander("3. Что нужно сделать для снятия ограничения", expanded=True):
        if pending_action == "pass":
            _render_fixation_plan_pass_info()
        else:
            _render_fixation_plan_section(prefix, row)

    with st.expander("4. Аудит и история", expanded=True):
        audit_cid = safe_str(row.get("constraint_id"))
        audit_criteria = direct_admit_criteria_for_department(
            safe_str(row.get("responsible_department"))
        )
        _render_fixation_audit_content(row, audit_cid, audit_criteria)


def _render_fixation_mvp_block_5(
    row: pd.Series,
    prefix: str,
    cid: str,
    pending_action: str,
    saver_name: str,
    workbench_df: pd.DataFrame,
) -> None:
    st.markdown(
        '<div id="da-gov-decision-host" class="da-fixation-decision-body"></div>',
        unsafe_allow_html=True,
    )
    with st.expander("5. Какое решение официально фиксируем", expanded=True):
        _render_fixation_decision_section(
            row, prefix, cid, pending_action, saver_name, workbench_df
        )


def _render_fixation_mvp_sections(
    row: pd.Series,
    prefix: str,
    saver_name: str,
    pending_action: str,
    workbench_df: pd.DataFrame,
    cid: str,
) -> None:
    st.markdown(_da_center_pane_styles(), unsafe_allow_html=True)

    with st.container(height=DIRECT_ADMIT_GOV_BLOCKS_SCROLL_HEIGHT_PX, border=False):
        st.markdown(
            '<div id="da-gov-scroll-host" class="da-fixation-scroll-body"></div>',
            unsafe_allow_html=True,
        )
        _render_fixation_mvp_blocks_1_4(row, prefix, pending_action)

    _render_fixation_mvp_block_5(
        row, prefix, cid, pending_action, saver_name, workbench_df
    )


def render_direct_admit_fixation_history(row: pd.Series) -> None:
    with st.container(border=True):
        st.markdown("**История и фиксация**")
        audit_cid = safe_str(row.get("constraint_id"))
        audit_criteria = direct_admit_criteria_for_department(
            safe_str(row.get("responsible_department"))
        )
        _render_fixation_audit_content(row, audit_cid, audit_criteria)


def direct_admit_check_status_for_action(action: str) -> str:
    if action == "pass":
        return "PASS"
    if action == "clarify":
        return "WARNING"
    if action == "block":
        return "HOLD"
    return "ОЖИДАЕТ"


def _register_direct_admit_status_patch(constraint_id: str, action: str) -> str:
    status = direct_admit_check_status_for_action(action)
    patches = dict(st.session_state.get(DIRECT_ADMIT_STATUS_PATCHES_KEY) or {})
    patches[safe_str(constraint_id)] = status
    st.session_state[DIRECT_ADMIT_STATUS_PATCHES_KEY] = patches
    return status


def apply_direct_admit_status_patches(df: pd.DataFrame) -> pd.DataFrame:
    patches = st.session_state.get(DIRECT_ADMIT_STATUS_PATCHES_KEY) or {}
    if df.empty or not patches:
        return df
    out = df.copy()
    remaining: dict[str, str] = {}
    for cid, patched_status in patches.items():
        mask = out["constraint_id"].astype(str) == safe_str(cid)
        if not mask.any():
            remaining[safe_str(cid)] = patched_status
            continue
        db_status = norm_check_status_key(out.loc[mask, "check_status"].iloc[0])
        target_status = norm_check_status_key(patched_status)
        if db_status == target_status:
            continue
        out.loc[mask, "check_status"] = target_status
        if "check_status_ui" in out.columns:
            out.loc[mask, "check_status_ui"] = CHECK_STATUS_RU.get(target_status, target_status)
        remaining[safe_str(cid)] = patched_status
    st.session_state[DIRECT_ADMIT_STATUS_PATCHES_KEY] = remaining
    return out


def save_direct_admission_decision(
    row: pd.Series,
    action: str,
    saver_name: str,
    *,
    comment: str = "",
    constraint_type: str = "",
    owner_role: str = "",
    owner_name: str = "",
    description: str = "",
    block_reason: str = "",
    target_date: date | None = None,
    severity: str = "MEDIUM",
) -> Optional[str]:
    """Save governance decision from right pane (existing DB fields only)."""
    constraint_id = safe_str(row.get("constraint_id"))
    if not constraint_id:
        return "У записи нет constraint_id."

    dept_label = dept_ui(row.get("responsible_department"))
    existing_comment = safe_str(row.get("comment"))
    now_iso = datetime.now(timezone.utc).isoformat()
    owner = owner_name.strip() or saver_name
    role = owner_role.strip() or "Другое"
    category = constraint_type.strip() or "Другое"
    target_iso = (
        target_date.isoformat()
        if target_date
        else (safe_date(row.get("target_resolution_date")) or date.today()).isoformat()
    )
    check_status = direct_admit_check_status_for_action(action)

    if action == "pass":
        note = f"[{now_moscow_text()}] Допущено отделом: {dept_label}."
        if comment.strip():
            note = f"{note} {comment.strip()}"
        payload = {
            "check_status": check_status,
            "resolution_status": "RESOLVED",
            "constraint_category": NO_CONSTRAINT_CATEGORY,
            "owner_name": owner,
            "owner_role": "Не требуется",
            "value_at_risk": 0.0,
            "comment": append_action_comment(existing_comment, note),
            "updated_by": saver_name,
            "last_action_at": now_iso,
            "updated_at": now_iso,
            "resolved_at": now_iso,
            "resolved_by": saver_name,
            "last_comment_at": now_iso,
        }
        err = update_constraint_record(constraint_id, payload)
        if err is None:
            _register_direct_admit_status_patch(constraint_id, action)
            load_constraints.clear()
        return err

    description = description.strip()
    block_reason_text = block_reason.strip()
    if action == "block":
        if not block_reason_text:
            return "Причина блокировки обязательна."
        if not description:
            description = block_reason_text
    elif action == "clarify" and not description:
        return "Краткое описание обязательно для уточнения."

    if action == "clarify":
        note = f"[{now_moscow_text()}] Требуется уточнение ({dept_label}): {description}"
        payload: Dict[str, Any] = {
            "check_status": check_status,
            "resolution_status": "IN_PROGRESS",
            "constraint_category": category,
            "owner_name": owner,
            "owner_role": role,
            "block_reason": description,
            "root_cause": description,
            "target_resolution_date": target_iso,
            "severity": severity,
            "comment": append_action_comment(existing_comment, note),
            "updated_by": saver_name,
            "last_action_at": now_iso,
            "updated_at": now_iso,
            "last_comment_at": now_iso,
        }
    elif action == "block":
        note = f"[{now_moscow_text()}] Заблокировано ({dept_label}): {description}"
        payload = {
            "check_status": check_status,
            "resolution_status": "OPEN",
            "constraint_category": category,
            "owner_name": owner,
            "owner_role": role,
            "block_reason": block_reason_text or description,
            "root_cause": description,
            "target_resolution_date": target_iso,
            "severity": severity,
            "comment": append_action_comment(existing_comment, note),
            "updated_by": saver_name,
            "last_action_at": now_iso,
            "updated_at": now_iso,
            "last_comment_at": now_iso,
        }
    else:
        return "Неизвестное действие."

    err = update_constraint_record(constraint_id, payload)
    if err is None:
        _register_direct_admit_status_patch(constraint_id, action)
        load_constraints.clear()
    return err


def _da_queue_select_id(row: pd.Series, idx: int) -> str:
    cid = safe_str(row.get("constraint_id"))
    if cid:
        return cid
    line_id = safe_str(row.get("line_id"))
    dept = safe_str(row.get("responsible_department"))
    check = safe_str(row.get("check_name"))
    return f"{line_id}|{dept}|{check}|{idx}"


def _da_queue_widget_key(select_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in select_id)
    return f"da_qsel_{safe}"


def _da_queue_status_display(status_key: str) -> tuple[str, str]:
    """Queue-pane display colors only (does not alter status logic)."""
    label, _, _ = direct_admit_queue_status(status_key)
    if status_key == "PASS":
        return label, "#2F6B4F"
    if status_key in ("HOLD", "FAIL"):
        return label, "#9B3D3D"
    return label, "#92610E"


def _da_queue_select_item(select_id: str) -> None:
    st.session_state[DIRECT_ADMIT_SELECTED_CID_KEY] = select_id
    st.session_state.pop(DIRECT_ADMIT_PENDING_ACTION_KEY, None)
    st.session_state.pop(DIRECT_ADMIT_CRITERIA_WARN_KEY, None)
    _da_clear_decision_session()


def _da_queue_card_html(
    ordinal: int,
    boq_code: str,
    boq_name: str,
    status_label: str,
    status_color: str,
    *,
    is_selected: bool,
    clickable: bool = False,
) -> str:
    code = html.escape(boq_code)
    name = html.escape(boq_name)
    title_attr = f' title="{html.escape(boq_name)}"' if boq_name else ""
    status_value = html.escape(status_label)
    card_cls = "da-queue-card da-queue-card-display"
    if is_selected:
        card_cls += " da-queue-card-selected"
    if clickable:
        card_cls += " da-queue-card-clickable"
    vybran = (
        f'<span class="da-queue-row1-right"><span class="da-queue-vybran">ВЫБРАН</span></span>'
        if is_selected
        else ""
    )
    return (
        f'<div class="{card_cls}">'
        f'<div class="da-queue-row1">'
        f'<div class="da-queue-row1-main">'
        f'<span class="da-queue-ordinal">{ordinal}.</span>'
        f'<span class="da-queue-code">{code}</span>'
        f"</div>{vybran}</div>"
        f'<div class="da-queue-name"{title_attr}>{name}</div>'
        f'<div class="da-queue-status-line">'
        f'<span class="da-queue-status-label">Статус проверки: </span>'
        f'<span class="da-queue-status-value" style="color:{status_color};">{status_value}</span>'
        f"</div></div>"
    )


def render_direct_admit_queue_pane(
    workbench_df: pd.DataFrame,
    selected_cid: str,
) -> None:
    progress = compute_direct_admit_progress(workbench_df)
    st.markdown("**1. Очередь допуска**")
    st.caption(
        f'{progress["total"]} всего · {progress["pending"]} ост · '
        f'{progress["approved"]} доп · {progress["blocked"]} блок · '
        f'{progress["clarify"]} уточн'
    )

    sorted_df = sort_workbench_for_queue(workbench_df)
    with st.container(height=DIRECT_ADMIT_PANE_HEIGHT_PX, border=False):
        st.markdown('<div id="da-queue-scroll-host"></div>', unsafe_allow_html=True)
        for pos, (_, row) in enumerate(sorted_df.iterrows()):
            ordinal = pos + 1
            select_id = _da_queue_select_id(row, pos)
            if not select_id:
                continue
            status_key = norm_check_status_key(row.get("check_status"))
            status_text, status_color = _da_queue_status_display(status_key)
            boq_code = safe_str(row.get("boq_code")) or "—"
            boq_name = safe_str(row.get("boq_name")) or "—"
            is_selected = select_id == selected_cid

            if is_selected:
                st.markdown(
                    _da_queue_card_html(
                        ordinal,
                        boq_code,
                        boq_name,
                        status_text,
                        status_color,
                        is_selected=True,
                    ),
                    unsafe_allow_html=True,
                )
            else:
                with st.container(border=False):
                    st.markdown(
                        _da_queue_card_html(
                            ordinal,
                            boq_code,
                            boq_name,
                            status_text,
                            status_color,
                            is_selected=False,
                            clickable=True,
                        ),
                        unsafe_allow_html=True,
                    )
                    st.button(
                        "\u200b",
                        key=_da_queue_widget_key(select_id),
                        on_click=_da_queue_select_item,
                        args=(select_id,),
                        use_container_width=True,
                    )


def render_direct_admit_center_pane(
    row: pd.Series | None,
    department_label: str,
) -> None:
    if row is None:
        st.markdown("**2. Решение по коду**")
        with st.container(height=DIRECT_ADMIT_PANE_HEIGHT_PX, border=False):
            st.markdown('<div id="da-center-scroll-host"></div>', unsafe_allow_html=True)
            st.info("Выберите код в очереди слева.")
        return

    st.markdown(_da_center_pane_styles(), unsafe_allow_html=True)
    st.markdown("**2. Решение по коду**")

    status_key = norm_check_status_key(row.get("check_status"))
    queue_label, _, queue_text_color = direct_admit_queue_status(status_key)
    boq_code = safe_str(row.get("boq_code")) or "—"
    boq_name = safe_str(row.get("boq_name")) or "—"
    cid = safe_str(row.get("constraint_id"))
    dept_key = resolve_direct_admit_dept_key(department_label, row)
    criteria = direct_admit_criteria_for_department(dept_key)

    with st.container(height=DIRECT_ADMIT_PANE_HEIGHT_PX, border=False):
        st.markdown('<div id="da-center-scroll-host"></div>', unsafe_allow_html=True)

        dept_pill = dept_ui(dept_key) if dept_key else field_display(row.get("discipline_display"))
        header_pills = [
            dept_pill,
            field_display(row.get("discipline_display")),
            field_display(row.get("title_display")),
            field_display(row.get("month_key_display")),
        ]
        status_badge = _da_center_status_badge_html(status_key, queue_label, queue_text_color)
        pills_html = _da_center_pills_html(header_pills)
        st.markdown(
            f'<div class="da-c2-header">'
            f'<div class="da-c2-header-top">'
            f'<span class="da-c2-code">{html.escape(boq_code)}</span>'
            f"{status_badge}"
            f"</div>"
            f'<div class="da-c2-title">{html.escape(boq_name)}</div>'
            f"{pills_html}"
            f"</div>",
            unsafe_allow_html=True,
        )
        check_name = field_display(row.get("check_name"))
        if check_name != "—":
            st.caption(f"Проверка: {check_name}")

        qty = field_display(row.get("planned_qty_display"))
        unit = field_display(row.get("unit_display"))
        mtr_cost = direct_admit_mtr_cost_display(row)
        hours_raw = field_display(row.get("required_hours_display"))
        hours_val = f"{hours_raw} ч" if hours_raw != "—" else "—"
        context_cells = [
            ("Проект", field_display(row.get("project_code_display"))),
            ("Титул", field_display(row.get("title_display"))),
            ("Месяц", field_display(row.get("month_key_display"))),
            ("Отдел", dept_pill),
            ("Система", field_display(row.get("system_display"))),
            ("IWP", field_display(row.get("iwp_display"))),
        ]
        econ_cells = [
            ("Плановая стоимость СМР", field_display(row.get("plan_value_display"))),
            ("Звено", field_display(row.get("crew_display"))),
            ("Объём по СМР", qty),
            ("Плановая стоимость МТР", mtr_cost),
            (
                "Кол-во в звене",
                _da_center_optional_field(
                    row,
                    "crew_count_display",
                    "crew_qty_display",
                    "crew_count",
                    "crew_qty",
                ),
            ),
            ("Ед. изм.", unit),
            ("Плановая стоимость труда", field_display(row.get("labor_cost_display"))),
            ("Трудозатраты", hours_val),
            (
                "Норма примененная",
                _da_center_optional_field(
                    row,
                    "applied_norm_display",
                    "norm_display",
                    "labor_norm_display",
                    "applied_norm",
                    "labor_norm",
                ),
            ),
        ]
        st.markdown(
            f'<div class="da-c2-ab-outer">'
            f'<div class="da-c2-ab-side">'
            f'<div class="da-c2-section-title">A. Контекст</div>'
            f'<div class="da-c2-panel da-c2-ab-panel">'
            f"{_render_da_compact_grid_html(context_cells, columns=2)}"
            f"</div></div>"
            f'<div class="da-c2-ab-side">'
            f'<div class="da-c2-section-title">B. Экономика</div>'
            f'<div class="da-c2-panel da-c2-ab-panel">'
            f"{_render_da_compact_grid_html(econ_cells, columns=3)}"
            f"</div></div></div>",
            unsafe_allow_html=True,
        )

        dept_criteria_label = dept_ui(dept_key) if dept_key else "Общие критерии"
        saver_name = st.session_state.get("constraints_saver_name", "Пользователь Streamlit")
        _render_direct_admit_block_c(cid, criteria, dept_criteria_label, row, saver_name)

        if st.session_state.get(DIRECT_ADMIT_CRITERIA_WARN_KEY):
            st.warning(
                "Перед допуском отметьте критерии или выберите Уточнить/Блокировать."
            )

        _render_direct_admit_block_d(cid, criteria, dept_key)


def render_direct_admit_governance_pane(
    row: pd.Series | None,
    pending_action: str,
    saver_name: str,
    workbench_df: pd.DataFrame,
) -> None:
    st.markdown("**3. Фиксация решения**")
    if row is None:
        st.info("Выберите код в очереди для просмотра истории.")
        return

    cid = safe_str(row.get("constraint_id"))
    prefix = f"da_gov_{cid[:8]}"

    _render_fixation_mvp_sections(
        row, prefix, saver_name, pending_action, workbench_df, cid
    )


def render_direct_admission_by_department_module(
    queue_df: pd.DataFrame,
    packages_df: pd.DataFrame,
    department_label: str,
) -> None:
    """Three-pane direct admission: очередь → решение → фиксация."""
    with st.expander("Непосредственный допуск по отделам", expanded=False):
        workbench_df = apply_direct_admit_status_patches(
            build_workbench_dataframe(queue_df, packages_df)
        )
        if workbench_df.empty:
            with st.container(border=True):
                render_direct_admit_module_header(
                    department_label, compute_direct_admit_progress(workbench_df)
                )
                st.info("Нет проверок для текущих фильтров. Уточните месяц, проект или отдел.")
            return

        progress = compute_direct_admit_progress(workbench_df)
        selected_cid = resolve_direct_admit_selected_cid(workbench_df)
        st.session_state[DIRECT_ADMIT_SELECTED_CID_KEY] = selected_cid

        selected_row: pd.Series | None = None
        if selected_cid:
            selected_rows = workbench_df[
                workbench_df["constraint_id"].astype(str) == selected_cid
            ]
            if not selected_rows.empty:
                selected_row = selected_rows.iloc[0]

        pending_action = safe_str(st.session_state.get(DIRECT_ADMIT_PENDING_ACTION_KEY))
        saver_name = st.session_state.get("constraints_saver_name", "Пользователь Streamlit")

        with st.container(border=True):
            render_direct_admit_module_header(department_label, progress)

            layout_options = list(DIRECT_ADMIT_LAYOUT_PRESETS.keys())
            if DIRECT_ADMIT_LAYOUT_KEY not in st.session_state:
                st.session_state[DIRECT_ADMIT_LAYOUT_KEY] = "Баланс"
            st.segmented_control(
                "Макет панелей",
                layout_options,
                key=DIRECT_ADMIT_LAYOUT_KEY,
                label_visibility="collapsed",
            )

            weights = direct_admit_layout_weights()
            pane_left, pane_center, pane_right = st.columns(weights)

            with pane_left:
                with st.container(border=True):
                    st.markdown(
                        '<span class="da-direct-admit-pane-marker" aria-hidden="true"></span>',
                        unsafe_allow_html=True,
                    )
                    render_direct_admit_queue_pane(workbench_df, selected_cid)

            with pane_center:
                with st.container(border=True):
                    st.markdown(
                        '<span class="da-direct-admit-pane-marker" aria-hidden="true"></span>',
                        unsafe_allow_html=True,
                    )
                    render_direct_admit_center_pane(selected_row, department_label)

            with pane_right:
                with st.container(border=True):
                    st.markdown(
                        '<span class="da-direct-admit-pane-marker" aria-hidden="true"></span>',
                        unsafe_allow_html=True,
                    )
                    render_direct_admit_governance_pane(
                        selected_row, pending_action, saver_name, workbench_df
                    )


def render_queue_detail_summary(row: pd.Series) -> None:
    qty = field_display(row.get("planned_qty_display"))
    unit = field_display(row.get("unit_display"))
    qty_text = f"{qty} {unit}" if qty != "—" and unit != "—" else qty
    status_ui = CHECK_STATUS_RU.get(
        norm_check_status_key(row.get("check_status")),
        safe_str(row.get("check_status")),
    )
    resolution_ui = RESOLUTION_RU.get(
        norm_tech_value(
            row.get("resolution_status"),
            RESOLUTION_OPTIONS,
            RESOLUTION_RU,
            "OPEN",
        ),
        safe_str(row.get("resolution_status")),
    )

    d1, d2, d3 = st.columns(3)
    d1.markdown(f"**BOQ:** {safe_str(row.get('boq_code'))} — {safe_str(row.get('boq_name')) or '—'}")
    d1.markdown(f"**Титул:** {field_display(row.get('title_display'))}")
    d1.markdown(f"**Дисциплина:** {field_display(row.get('discipline_display'))}")
    d2.markdown(f"**Звено:** {field_display(row.get('crew_display'))}")
    d2.markdown(f"**Объём:** {qty_text}")
    d2.markdown(
        f"**Часы / стоимость:** {field_display(row.get('required_hours_display'))} ч · "
        f"{field_display(row.get('plan_value_display'))}"
    )
    d3.markdown(f"**Проверка:** {safe_str(row.get('check_name')) or '—'}")
    d3.markdown(f"**Отдел:** {dept_ui(row.get('responsible_department'))}")
    d3.markdown(f"**Статус:** {status_ui} · **Устранение:** {resolution_ui}")

    c1, c2 = st.columns(2)
    c1.markdown(f"**Комментарий:** {field_display(row.get('comment'))}")
    c2.markdown(f"**Причина блокировки:** {field_display(row.get('block_reason'))}")
    st.caption(f"Последнее действие: {last_decision_display(row)}")


def render_workbench_queue_row(
    row: pd.Series,
    row_index: int,
    saver_name: str,
) -> None:
    constraint_id = safe_str(row.get("constraint_id"))
    if not constraint_id:
        return

    status_key = norm_check_status_key(row.get("check_status"))
    dot_color = check_status_dot_color(status_key)
    status_ui = CHECK_STATUS_RU.get(status_key, status_key)
    resolution_ui = field_display(row.get("resolution_status_ui"))
    boq_name = safe_str(row.get("boq_name")) or "—"
    boq_code = safe_str(row.get("boq_code")) or "—"
    queue = field_display(row.get("queue_display"))
    title = field_display(row.get("title_display"))
    discipline = field_display(row.get("discipline_display"))
    crew = field_display(row.get("crew_display"))
    qty = field_display(row.get("planned_qty_display"))
    unit = field_display(row.get("unit_display"))
    hours = field_display(row.get("required_hours_display"))
    cost = field_display(row.get("plan_value_display"))
    check_name = safe_str(row.get("check_name")) or "—"
    dept_ui_label = field_display(row.get("responsible_department_ui"))
    last_decision = field_display(row.get("last_decision_display"))
    economics_note = " · AI" if row.get("is_crew_economics") else ""

    qty_line = f"{qty} {unit}" if qty != "—" and unit != "—" else qty
    prefix = f"wb_{row_index}_{constraint_id[:8]}"
    comment_key = f"{prefix}_comment"

    c_main, c_actions = st.columns([5.0, 3.0])
    with c_main:
        st.markdown(
            f"""
            <div style="border-bottom:1px solid #f1f5f9;padding:0.28rem 0 0.32rem 0;">
                <div style="display:flex;align-items:center;gap:0.35rem;">
                    <span style="color:{dot_color};font-size:0.5rem;">●</span>
                    <span style="font-weight:600;font-size:0.84rem;color:#0f172a;">{boq_code}</span>
                    <span style="font-size:0.84rem;color:#334155;">{boq_name}</span>
                </div>
                <div style="font-size:0.75rem;color:#64748b;margin:0.06rem 0 0 0.8rem;line-height:1.3;">
                    {title} · {discipline} · {queue} · Звено: {crew}
                </div>
                <div style="font-size:0.75rem;color:#64748b;margin:0.03rem 0 0 0.8rem;line-height:1.3;">
                    Объём: {qty_line} · Часы: {hours} · Стоимость: {cost}
                </div>
                <div style="font-size:0.75rem;color:#475569;margin:0.03rem 0 0 0.8rem;line-height:1.3;">
                    Проверка: {check_name}{economics_note} · Отдел: {dept_ui_label}
                </div>
                <div style="font-size:0.75rem;color:#475569;margin:0.03rem 0 0 0.8rem;line-height:1.3;">
                    Статус: {status_ui} · Устранение: {resolution_ui} · Последнее: {last_decision}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        action_comment = st.text_input(
            "Комментарий к блокировке / уточнению",
            value="",
            key=comment_key,
            placeholder="Обязательно для «Заблокировать» и «Уточнить»",
            label_visibility="collapsed",
        )

    with c_actions:
        st.markdown('<div class="wb-btn-row">', unsafe_allow_html=True)
        ar1, ar2 = st.columns(2)
        if ar1.button("Допустить", key=f"{prefix}_pass", use_container_width=True):
            err = apply_check_quick_action(row, "pass", saver_name)
            if err:
                st.error(err)
            else:
                st.cache_data.clear()
                st.rerun()
        if ar2.button("Заблокировать", key=f"{prefix}_hold", use_container_width=True):
            err = apply_check_quick_action(row, "hold", saver_name, action_comment)
            if err:
                st.warning(err)
            else:
                st.cache_data.clear()
                st.rerun()
        ar3, ar4 = st.columns(2)
        if ar3.button("Уточнить", key=f"{prefix}_warn", use_container_width=True):
            err = apply_check_quick_action(row, "clarify", saver_name, action_comment)
            if err:
                st.warning(err)
            else:
                st.cache_data.clear()
                st.rerun()
        detail_open = st.session_state.get(WORKBENCH_DETAIL_CID_KEY) == constraint_id
        detail_label = "Скрыть" if detail_open else "Подробнее"
        if ar4.button(detail_label, key=f"{prefix}_detail", use_container_width=True):
            if detail_open:
                st.session_state.pop(WORKBENCH_DETAIL_CID_KEY, None)
            else:
                st.session_state[WORKBENCH_DETAIL_CID_KEY] = constraint_id
                st.session_state[TABLE_SELECTED_ID_KEY] = constraint_id
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def render_admission_queue(
    queue_df: pd.DataFrame,
    packages_df: pd.DataFrame,
    department_label: str,
) -> Optional[pd.Series]:
    workbench_df = build_workbench_dataframe(queue_df, packages_df)

    if workbench_df.empty:
        dept_text = (
            f"отдела «{dept_ui(department_label)}»"
            if department_label != "Все"
            else "выбранных фильтров"
        )
        st.caption(f"Нет проверок для {dept_text}.")
        return None

    total = len(workbench_df)
    shown = workbench_df.head(WORKBENCH_MAX_ROWS)
    dept_note = (
        f" · {dept_ui(department_label)}"
        if department_label != "Все"
        else ""
    )
    st.caption(f"{total} проверок{dept_note}")

    saver_name = st.session_state.get("constraints_saver_name", "Пользователь Streamlit")
    for idx, (_, row) in enumerate(shown.iterrows()):
        render_workbench_queue_row(row, idx, saver_name)

    if total > WORKBENCH_MAX_ROWS:
        st.caption(f"Показаны первые {WORKBENCH_MAX_ROWS} из {total}. Уточните фильтры.")

    detail_cid = st.session_state.get(WORKBENCH_DETAIL_CID_KEY)
    if not detail_cid:
        return None

    detail_rows = workbench_df[
        workbench_df["constraint_id"].astype(str) == str(detail_cid)
    ]
    if detail_rows.empty:
        return None
    return detail_rows.iloc[0]


def style_package_status_bg(val: Any) -> str:
    for status, style in PACKAGE_STATUS_STYLE.items():
        if val == PACKAGE_STATUS_RU.get(status, status):
            return style
    return ""


def style_package_table(df_in: pd.DataFrame):
    styler = df_in.style
    status_col = PACKAGE_TABLE_COLUMNS_RU.get("package_status_ui", "Статус допуска")
    if status_col in styler.data.columns:
        styler = _apply_cell_style(styler, style_package_status_bg, status_col)
    return styler


def style_admission_status_text(val: Any) -> str:
    text = str(val).strip().upper()
    for key, style in ADMISSION_STATUS_TEXT_STYLE.items():
        if key.upper() in text:
            return style
    return "color: #475569;"


def _parse_labor_to_plan_pct_display(val: Any) -> float | None:
    text = str(val).strip()
    if not text or text == "—":
        return None
    cleaned = text.replace("%", "").strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def style_admission_labor_to_plan_pct_text(val: Any) -> str:
    """Подсветка >=100% — тот же красный, что у статуса «Заблокировано»."""
    pct = _parse_labor_to_plan_pct_display(val)
    if pct is not None and pct >= 100.0:
        return ADMISSION_STATUS_TEXT_STYLE["Заблокировано"]
    return ""


def style_admission_main_table(df_in: pd.DataFrame):
    status_col = ADMISSION_MAIN_TABLE_COLUMNS_RU.get("package_status_ui", "Статус допуска")
    labor_pct_col = ADMISSION_MAIN_TABLE_COLUMNS_RU.get(
        "labor_to_plan_pct_display", "Труд / стоимость работ, %"
    )
    styler = df_in.style
    if status_col in styler.data.columns:
        styler = _apply_cell_style(styler, style_admission_status_text, status_col)
    if labor_pct_col in styler.data.columns:
        styler = _apply_cell_style(styler, style_admission_labor_to_plan_pct_text, labor_pct_col)
    for col in ADMISSION_MAIN_TABLE_NUMERIC_COLUMNS:
        if col in df_in.columns:
            styler = styler.set_properties(subset=[col], **{"text-align": "right"})
    return styler


def prepare_constraint_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display_df = df.copy()
    if "responsible_department" in display_df.columns:
        display_df["responsible_department"] = display_df["responsible_department"].apply(dept_ui)
    if "gate_layer" in display_df.columns:
        display_df["gate_layer"] = display_df["gate_layer"].apply(
            lambda v: GATE_LAYER_RU.get(safe_str(v), safe_str(v))
        )
    if "check_status" in display_df.columns:
        display_df["check_status"] = display_df["check_status"].apply(
            lambda v: CHECK_STATUS_RU.get(norm_check_status_key(v), safe_str(v))
        )
    if "severity" in display_df.columns:
        display_df["severity"] = display_df["severity"].apply(
            lambda v: SEVERITY_RU.get(
                norm_tech_value(v, SEVERITY_OPTIONS, SEVERITY_RU, "MEDIUM"),
                safe_str(v),
            )
        )
    if "updated_by" in display_df.columns:
        display_df["updated_by"] = display_df["updated_by"].apply(display_dash)
    if "owner_name" in display_df.columns:
        display_df["owner_name"] = display_df["owner_name"].apply(display_dash)
    if "resolution_status" in display_df.columns:
        display_df["resolution_status"] = display_df["resolution_status"].apply(
            lambda v: RESOLUTION_RU.get(
                norm_tech_value(v, RESOLUTION_OPTIONS, RESOLUTION_RU, safe_str(v)),
                safe_str(v),
            )
        )
    if "value_at_risk_display" in display_df.columns:
        display_df["value_at_risk_display"] = display_df["value_at_risk_display"].apply(money_ru)
    if "target_resolution_date" in display_df.columns:
        display_df["target_resolution_date"] = display_df["target_resolution_date"].apply(
            lambda v: safe_date(v).isoformat() if safe_date(v) else "—"
        )
    return display_df


def prepare_decision_registry_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display_df = prepare_constraint_display_df(df)
    for col in (
        "month_display",
        "system_display",
        "iwp_display",
        "decision_at_display",
        "constraint_reason_display",
    ):
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(display_dash)
    return display_df


def resolve_selected_package_key(packages_df: pd.DataFrame) -> str:
    keys = packages_df["package_key"].astype(str).tolist()
    if not keys:
        return ""

    selection_state = st.session_state.get(PACKAGE_TABLE_SELECTION_KEY, {})
    selected_rows = selection_state.get("selection", {}).get("rows", [])
    if selected_rows:
        row_idx = int(selected_rows[0])
        if 0 <= row_idx < len(keys):
            picked = keys[row_idx]
            st.session_state[PACKAGE_SELECTED_KEY] = picked
            return picked

    stored = st.session_state.get(PACKAGE_SELECTED_KEY)
    if stored in keys:
        return str(stored)

    return keys[0]


def filter_constraints_for_package(
    constraints_df: pd.DataFrame,
    package_key: str,
) -> pd.DataFrame:
    if constraints_df.empty or not package_key:
        return pd.DataFrame()
    working = constraints_df.copy()
    working["_package_key"] = working.apply(package_key_from_row, axis=1)
    return working[working["_package_key"].astype(str) == package_key].drop(
        columns=["_package_key"], errors="ignore"
    )


def resolve_selected_constraint_id_in_subset(
    df: pd.DataFrame,
    label_keys: List[str],
    selection_key: str,
) -> str:
    selection_state = st.session_state.get(selection_key, {})
    selected_rows = selection_state.get("selection", {}).get("rows", [])
    if selected_rows:
        row_idx = int(selected_rows[0])
        if 0 <= row_idx < len(df):
            picked = safe_str(df.iloc[row_idx].get("constraint_id"))
            if picked in label_keys:
                st.session_state[TABLE_SELECTED_ID_KEY] = picked
                return picked

    manual = st.session_state.get(CONSTRAINT_EDIT_SELECT_KEY)
    if manual and manual in label_keys:
        return str(manual)

    stored = st.session_state.get(TABLE_SELECTED_ID_KEY)
    if stored and stored in label_keys:
        return str(stored)

    return label_keys[0]


def render_package_explanation(
    pkg_row: pd.Series,
    package_constraints: pd.DataFrame,
) -> None:
    status_key = safe_str(pkg_row.get("package_status"))
    if status_key == PACKAGE_STATUS_BLOCKED:
        dept = dept_ui(pkg_row.get("blocking_department")) or field_display(
            pkg_row.get("who_holds_display")
        )
        check_name = field_display(pkg_row.get("blocking_check_name"))
        st.markdown(
            f"""
            <div class="admission-explanation admission-explanation--blocked">
                <strong>🔴 Работа заблокирована</strong><br>
                <span><strong>Причина:</strong> {dept} → {check_name}</span><br>
                <span><strong>Что это значит:</strong> Пакет пока нельзя выпускать в производство или предъявление.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if status_key == PACKAGE_STATUS_READY:
        st.markdown(
            """
            <div class="admission-explanation admission-explanation--ready">
                <strong>🟢 Работа допущена к исполнению</strong><br>
                <span>Все проверки завершены.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    waiting_label = safe_str(pkg_row.get("waiting_departments_label"))
    if not waiting_label and not package_constraints.empty:
        waiting_label = ", ".join(
            dept_ui(dept)
            for dept in compute_waiting_departments(package_constraints)[:5]
        )
    waiting_text = waiting_label or format_waiting_checks_label(
        int(safe_num(pkg_row.get("waiting_checks_count")))
    )
    st.markdown(
        f"""
        <div class="admission-explanation admission-explanation--open">
            <strong>🟡 Работа проверяется</strong><br>
            <span><strong>Ожидаются проверки:</strong> {field_display(waiting_text)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_package_header(pkg_row: pd.Series) -> None:
    status_key = safe_str(pkg_row.get("package_status"))
    status_ui = PACKAGE_STATUS_RU.get(status_key, status_key)
    reason_ui = safe_str(pkg_row.get("blocking_reason"))
    line_display = safe_str(pkg_row.get("line_id")) or safe_str(pkg_row.get("package_key"))

    st.markdown(
        f"""
        <div class="admission-package-header">
            <div style="font-size:1.05rem;font-weight:700;color:#0f172a;margin-bottom:0.35rem;">
                {safe_str(pkg_row.get("boq_code"))} — {safe_str(pkg_row.get("boq_name")) or "—"}
            </div>
            <div style="font-size:0.86rem;color:#475569;line-height:1.55;">
                <span><strong>Очередь:</strong> {field_display(pkg_row.get("queue_display"))}</span>
                &nbsp;·&nbsp;
                <span><strong>Титул:</strong> {field_display(pkg_row.get("title_display"))}</span>
                &nbsp;·&nbsp;
                <span><strong>Дисциплина:</strong> {field_display(pkg_row.get("discipline_display"))}</span>
            </div>
            <div style="font-size:0.86rem;color:#475569;line-height:1.55;margin-top:0.25rem;">
                <span><strong>Система:</strong> {field_display(pkg_row.get("system_display"))}</span>
                &nbsp;·&nbsp;
                <span><strong>IWP:</strong> {field_display(pkg_row.get("iwp_display"))}</span>
                &nbsp;·&nbsp;
                <span><strong>Звено:</strong> {field_display(pkg_row.get("crew_display"))}</span>
            </div>
            <div style="font-size:0.86rem;color:#475569;line-height:1.55;margin-top:0.25rem;">
                <span><strong>Объём:</strong> {field_display(pkg_row.get("planned_qty_display"))} {field_display(pkg_row.get("unit_display")) if field_display(pkg_row.get("unit_display")) != "—" else ""}</span>
                &nbsp;·&nbsp;
                <span><strong>Часы:</strong> {field_display(pkg_row.get("required_hours_display"))}</span>
                &nbsp;·&nbsp;
                <span><strong>Стоимость:</strong> {field_display(pkg_row.get("plan_value_display"))}</span>
            </div>
            <div style="font-size:0.86rem;color:#475569;line-height:1.55;margin-top:0.25rem;">
                <span><strong>Отправлено в допуск MSK:</strong> {field_display(pkg_row.get("sent_to_constraints_display"))}</span>
                &nbsp;·&nbsp;
                <span><strong>Статус допуска:</strong> {status_ui}</span>
                &nbsp;·&nbsp;
                <span><strong>plan_line_id:</strong> <code>{line_display}</code></span>
            </div>
            <div style="font-size:0.86rem;color:#475569;line-height:1.55;margin-top:0.25rem;">
                <span><strong>Итог:</strong> {field_display(reason_ui)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_edit_card(row: pd.Series) -> None:
    st.markdown("### Детализация выбранной проверки")
    st.caption(BOQ_MULTI_CONSTRAINT_INFO)
    info1, info2, info3 = st.columns(3)
    info1.markdown(f"**BOQ-код:** {safe_str(row.get('boq_code'))}")
    info1.markdown(f"**Наименование:** {safe_str(row.get('boq_name'))}")
    info1.markdown(f"**Плановая стоимость:** {money_ru(row.get('plan_value'))}")
    info2.markdown(
        f"**Контур допуска:** {GATE_LAYER_RU.get(safe_str(row.get('gate_layer')), safe_str(row.get('gate_layer')))}"
    )
    info2.markdown(f"**Отдел:** {dept_ui(row.get('responsible_department'))}")
    info2.markdown(f"**Проверка:** {safe_str(row.get('check_name'))}")
    info3.markdown(
        f"**Текущий статус:** "
        f"{CHECK_STATUS_RU.get(norm_check_status_key(row.get('check_status')), safe_str(row.get('check_status')))}"
    )
    info3.markdown(f"**Дней открыто:** {int(safe_num(row.get('days_open')))}")

    info4, info5, info6 = st.columns(3)
    target = safe_date(row.get("target_resolution_date"))
    info4.markdown(f"**Просрочка по сроку:** {int(safe_num(row.get('days_overdue')))} дн.")
    if "evidence_count" in row.index and not pd.isna(row.get("evidence_count")):
        info5.markdown(f"**Доказательств:** {int(safe_num(row.get('evidence_count')))}")
    promised = safe_date(row.get("effective_promised_date"))
    if promised:
        info5.markdown(f"**Дата обещания:** {promised.isoformat()}")
    if "days_since_promise" in row.index and safe_num(row.get("days_since_promise")) > 0:
        info6.markdown(f"**Просрочка обещания:** {int(safe_num(row.get('days_since_promise')))} дн.")

    st.markdown("---")
    constraint_id = safe_str(row.get("constraint_id"))
    if not constraint_id:
        st.error("У записи нет constraint_id — сохранение недоступно.")
        return

    preset_key = f"form_preset_{constraint_id}"
    preset = st.session_state.pop(preset_key, None) or {}

    current_check = norm_check_status_key(preset.get("check_status") or row.get("check_status"))
    current_resolution = norm_tech_value(
        preset.get("resolution_status") or row.get("resolution_status"),
        RESOLUTION_OPTIONS,
        RESOLUTION_RU,
        "OPEN",
    )
    current_severity = norm_tech_value(
        row.get("severity"), SEVERITY_OPTIONS, SEVERITY_RU, "MEDIUM"
    )
    dept = safe_str(row.get("responsible_department"))
    current_category = safe_str(preset.get("category") or row.get("constraint_category")) or "Другое"
    category_opts = category_options_for_department(dept, current_category)
    if current_category not in category_opts:
        current_category = "Другое"

    preset_owner = safe_str(preset.get("owner_name"))
    preset_role = safe_str(preset.get("owner_role"))
    preset_risk = preset.get("value_at_risk")

    e1, e2 = st.columns(2)
    new_check_status = ru_selectbox(
        "Статус проверки",
        CHECK_STATUS_OPTIONS,
        CHECK_STATUS_RU,
        current_check,
        key=f"check_status_{constraint_id}",
    )
    new_resolution_status = ru_selectbox(
        "Статус устранения",
        RESOLUTION_OPTIONS,
        RESOLUTION_RU,
        current_resolution,
        key=f"resolution_{constraint_id}",
    )

    st.markdown("**Владелец и сторона ответственности**")
    owner_dept_raw = safe_str(row.get("owner_department") or row.get("responsible_department"))
    resp_side_key = f"resp_side_{constraint_id}"
    if resp_side_key not in st.session_state:
        st.session_state[resp_side_key] = infer_responsibility_side(row)

    o1, o2, o3 = st.columns(3)
    side_index = (
        RESPONSIBILITY_SIDE_OPTIONS.index(st.session_state[resp_side_key])
        if st.session_state[resp_side_key] in RESPONSIBILITY_SIDE_OPTIONS
        else 0
    )
    o1.selectbox(
        "Сторона ответственности",
        RESPONSIBILITY_SIDE_OPTIONS,
        index=side_index,
        key=resp_side_key,
    )

    current_owner_name = preset_owner or safe_str(row.get("owner_name"))
    name_opts = owner_name_options(current_owner_name)
    name_index = name_opts.index(current_owner_name) if current_owner_name in name_opts else 0
    owner_name_choice = o2.selectbox(
        "Владелец ограничения",
        name_opts,
        index=name_index,
        key=f"owner_name_sel_{constraint_id}",
    )
    owner_name_custom_default = (
        current_owner_name
        if current_owner_name and current_owner_name not in OWNER_NAME_PRESETS
        else ""
    )
    if owner_name_choice == "Другое":
        owner_name = st.text_input(
            "Укажите владельца",
            value=owner_name_custom_default,
            key=f"owner_name_custom_{constraint_id}",
        )
    else:
        owner_name = resolve_owner_name(owner_name_choice, "")

    current_owner_role = preset_role or safe_str(row.get("owner_role"))
    role_opts = owner_role_options(current_owner_role)
    role_index = role_opts.index(current_owner_role) if current_owner_role in role_opts else 0
    owner_role_choice = o3.selectbox(
        "Роль владельца",
        role_opts,
        index=role_index,
        key=f"owner_role_sel_{constraint_id}",
    )
    if owner_role_choice == "Другое":
        owner_role = st.text_input(
            "Укажите роль владельца",
            value=current_owner_role if current_owner_role not in OWNER_ROLE_PRESETS else "",
            key=f"owner_role_custom_{constraint_id}",
        )
    else:
        owner_role = owner_role_choice

    owner_department = (
        dept_ui(owner_dept_raw) if owner_dept_raw in DEPARTMENT_RU else owner_dept_raw
    )

    st.markdown("**Контроль сроков**")
    d1, d2, d3, d4 = st.columns(4)
    new_occurrence_date = d1.date_input(
        "Дата возникновения ограничения",
        value=constraint_occurrence_date(row),
        key=f"occurrence_{constraint_id}",
    )
    target_default = target or date.today()
    new_target_date = d2.date_input(
        "Текущая требуемая дата устранения",
        value=target_default,
        key=f"target_{constraint_id}",
    )
    overdue_display = overdue_days_for_card(safe_date(new_target_date), new_resolution_status)
    d3.number_input(
        "Просрочка, дней",
        value=int(overdue_display),
        disabled=True,
        key=f"overdue_{constraint_id}",
    )
    record_comment = safe_str(row.get("comment"))
    d4.number_input(
        "Количество переносов срока",
        value=count_schedule_reschedules(record_comment),
        disabled=True,
        key=f"reschedule_cnt_{constraint_id}",
    )

    history_items = parse_schedule_history(record_comment)
    if history_items:
        st.caption("История сроков / переносов")
        for item in history_items:
            suffix = f" — {item['note']}" if item.get("note") else ""
            st.text(f"{item.get('old', '—')} → {item.get('new', '—')}{suffix}")

    new_severity = ru_selectbox(
        "Критичность",
        SEVERITY_OPTIONS,
        SEVERITY_RU,
        current_severity,
        key=f"severity_{constraint_id}",
    )

    st.caption(
        "Выберите тип ограничения. Это нужно для совещания и анализа bottleneck по отделам."
    )
    category_labels = category_opts
    category_index = (
        category_labels.index(current_category)
        if current_category in category_labels
        else category_labels.index("Другое")
    )
    new_category = st.selectbox(
        "Тип ограничения",
        category_labels,
        index=category_index,
        key=f"category_{constraint_id}",
    )
    if new_category == NO_CONSTRAINT_CATEGORY:
        if st.button(
            "Заполнить форму рекомендуемыми значениями (PASS / без ограничений)",
            key=f"preset_pass_{constraint_id}",
        ):
            apply_no_constraint_form_preset(constraint_id)
            st.rerun()

    if is_owner_optional(new_check_status, new_category):
        st.caption(
            "Для PASS / «Ограничений нет» владелец ограничения и роль не обязательны."
        )

    reason_combined = st.text_area(
        "Причина ограничения",
        value=combined_constraint_reason(row),
        key=f"reason_{constraint_id}",
        help="Сохраняется в поля «Причина блокировки» и «Корневая причина» в базе.",
    )
    comment = st.text_area("Комментарий", value=safe_str(row.get("comment")))

    default_risk = float(preset_risk) if preset_risk is not None else row_risk_value(row)
    st.markdown(f"**Текущая стоимость под риском:** {money_ru(default_risk)}")
    new_value_at_risk = st.number_input(
        "Стоимость под риском для сохранения, ₽",
        min_value=0.0,
        value=float(default_risk),
        step=1000.0,
        format="%.2f",
        help="Введите число без пробелов. Отображение суммы выше форматируется автоматически.",
        key=f"value_at_risk_{constraint_id}",
    )
    st.caption(f"Будет сохранено как: {money_ru(new_value_at_risk)}")

    st.markdown("**Аудит последнего изменения (только просмотр)**")
    audit1, audit2 = st.columns(2)
    audit1.text_input(
        "Последнее обновление (last_updated_at)",
        value=format_datetime_ru(audit_last_updated_at(row)),
        disabled=True,
    )
    audit2.text_input(
        "Кто обновил (last_updated_by)",
        value=audit_last_updated_by(row) or "—",
        disabled=True,
    )

    saver_name = st.text_input(
        "Кто сохраняет сейчас",
        value=st.session_state.get("constraints_saver_name", "Пользователь Streamlit"),
        key=f"saver_{constraint_id}",
    )
    st.session_state["constraints_saver_name"] = saver_name

    st.markdown("**Доказательства действий**")
    st.info(
        "Постоянное сохранение файлов будет подключено через Supabase Storage / "
        f"{TABLE_EVIDENCE}."
    )

    if st.button("Сохранить изменение", type="primary", key=f"save_{constraint_id}"):
        now_iso = datetime.now(timezone.utc).isoformat()
        reason_text = reason_combined.strip()
        final_block_reason = reason_text
        if new_category != "Другое" and new_category != NO_CONSTRAINT_CATEGORY and not final_block_reason:
            final_block_reason = new_category
        payload: Dict[str, Any] = {
            "check_status": new_check_status,
            "resolution_status": new_resolution_status,
            "owner_name": owner_name or None,
            "owner_role": owner_role or None,
            "owner_department": dept_db(owner_department) if owner_department else None,
            "target_resolution_date": new_target_date.isoformat(),
            "severity": new_severity,
            "constraint_category": new_category,
            "root_cause": reason_text or None,
            "block_reason": final_block_reason or None,
            "comment": None,
            "value_at_risk": new_value_at_risk,
            "updated_by": saver_name or None,
            "last_action_at": now_iso,
            "updated_at": now_iso,
        }
        if "constraint_created_at" in row.index:
            occurrence_iso = datetime.combine(
                new_occurrence_date, datetime.min.time(), tzinfo=timezone.utc
            ).isoformat()
            payload["constraint_created_at"] = occurrence_iso

        final_comment = comment.strip()
        old_target = safe_date(row.get("target_resolution_date"))
        if old_target != new_target_date:
            final_comment = append_schedule_change_comment(
                final_comment, old_target, new_target_date, saver_name
            )
        payload["comment"] = final_comment or None

        if final_comment or final_block_reason:
            payload["last_comment_at"] = now_iso
        if new_resolution_status == "RESOLVED":
            payload["resolved_at"] = now_iso
            payload["resolved_by"] = saver_name or None

        err = update_constraint_record(constraint_id, payload)
        if err:
            st.error(err)
        else:
            st.success("Ограничение обновлено")
            st.cache_data.clear()
            st.rerun()


def prepare_admission_main_table(packages_df: pd.DataFrame) -> pd.DataFrame:
    if packages_df.empty:
        return pd.DataFrame(columns=list(ADMISSION_MAIN_TABLE_COLUMNS_RU.values()))

    show_cols = [c for c in ADMISSION_MAIN_TABLE_COLUMNS if c in packages_df.columns]
    view = packages_df[show_cols].copy()
    if "package_status" in packages_df.columns and "package_status_ui" in view.columns:
        view["package_status_ui"] = packages_df["package_status"].map(
            lambda value: PACKAGE_STATUS_TABLE_LABEL.get(
                safe_str(value),
                field_display(value),
            )
        ).apply(
            lambda label: str(label).strip().upper()
            if str(label).strip() and str(label).strip() != "—"
            else label
        )
    for col in show_cols:
        if col == "package_status_ui":
            continue
        view[col] = view[col].apply(field_display)
    return view.rename(columns=ADMISSION_MAIN_TABLE_COLUMNS_RU)


def render_admission_plan_list_module(
    packages_df: pd.DataFrame,
    scope_df: pd.DataFrame,
) -> None:
    with st.expander("Список месячного плана для допуска", expanded=False):
        st.caption(
            "Строки месячного плана, отправленные из Конструктора v2 в контур допуска."
        )

        st.markdown('<div class="admission-module-panel">', unsafe_allow_html=True)
        render_admission_plan_list_kpi_panel(packages_df, scope_df)

        if packages_df.empty:
            st.caption("По выбранным фильтрам строк нет.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        table_view = prepare_admission_main_table(packages_df)
        row_count = len(table_view)
        st.markdown('<div class="admission-plan-table">', unsafe_allow_html=True)
        st.dataframe(
            style_admission_main_table(table_view),
            use_container_width=True,
            hide_index=True,
            height=PACKAGE_TABLE_HEIGHT_PX,
            on_select="rerun",
            selection_mode="single-row",
            key=PACKAGE_TABLE_SELECTION_KEY,
            column_config=build_admission_table_column_config(
                table_view, ADMISSION_PLAN_LIST_COLUMN_WIDTHS
            ),
        )
        st.markdown("</div>", unsafe_allow_html=True)
        st.caption(f"Показано {row_count} строк.")
        st.markdown("</div>", unsafe_allow_html=True)


def render_admission_line_details(
    packages_df: pd.DataFrame,
    scope_df: pd.DataFrame,
) -> None:
    if packages_df.empty:
        st.caption("По выбранным фильтрам строк нет.")
        return

    selected_package_key = resolve_selected_package_key(packages_df)
    pkg_row = packages_df[
        packages_df["package_key"].astype(str) == selected_package_key
    ].iloc[0]
    package_constraints = filter_constraints_for_package(scope_df, selected_package_key)

    render_package_header(pkg_row)

    if package_constraints.empty:
        st.warning("Для выбранного пакета нет проверок в текущей выборке.")
        return

    st.markdown("#### Статус допуска строки")
    render_package_explanation(pkg_row, package_constraints)
    package_display_df = prepare_constraint_display_df(package_constraints)
    check_show_cols = [
        c
        for c in (
            "responsible_department",
            "gate_layer",
            "check_name",
            "check_status",
            "resolution_status",
            "target_resolution_date",
            "days_overdue",
        )
        if c in package_display_df.columns
    ]
    check_table_view = package_display_df[check_show_cols].rename(
        columns={
            "responsible_department": "Отдел",
            "gate_layer": "Контур",
            "check_name": "Проверка",
            "check_status": "Статус",
            "resolution_status": "Устранение",
            "target_resolution_date": "Срок",
            "days_overdue": "Просрочка",
        }
    )
    st.dataframe(
        style_table(check_table_view),
        use_container_width=True,
        hide_index=True,
        height=PACKAGE_CHECK_TABLE_HEIGHT_PX,
        on_select="rerun",
        selection_mode="single-row",
        key=PACKAGE_CHECK_TABLE_KEY,
    )

    labels: Dict[str, str] = {}
    for _, row in package_constraints.iterrows():
        cid = safe_str(row.get("constraint_id"))
        if cid:
            labels[cid] = constraint_human_label(row)
    if not labels:
        st.warning("Нет записей с constraint_id для редактирования.")
        return

    label_keys = list(labels.keys())
    selected_id = resolve_selected_constraint_id_in_subset(
        package_constraints, label_keys, PACKAGE_CHECK_TABLE_KEY
    )
    selected_row = package_constraints[
        package_constraints["constraint_id"].astype(str) == selected_id
    ].iloc[0]

    st.markdown(f"**Редактирование проверки:** {constraint_human_label(selected_row)}")
    render_edit_card(selected_row)


def render_decision_registry_module(
    registry_df: pd.DataFrame,
    v2_lines_df: pd.DataFrame,
) -> None:
    with st.expander("Реестр решений по допуску", expanded=False):
        st.caption(
            "Журнал решений, принятых отделами по кодам месячного плана. "
            "Используется для контроля статуса допуска, блокировок, доработок и истории согласования."
        )
        st.caption("Показаны решения по текущему фильтру страницы.")
        if registry_df.empty:
            st.info("По текущему набору фильтров решений не найдено.")
            return
        technical_df = enrich_decision_registry_with_v2_lines(registry_df, v2_lines_df)
        technical_df = prepare_decision_registry_display_df(technical_df)
        show_cols = [c for c in DECISION_REGISTRY_TABLE_COLUMNS if c in technical_df.columns]
        table_view = technical_df[show_cols].rename(columns=DECISION_REGISTRY_TABLE_COLUMNS_RU)
        status_col = DECISION_REGISTRY_TABLE_COLUMNS_RU["check_status"]
        if status_col in table_view.columns:
            table_view[status_col] = table_view[status_col].apply(
                format_decision_registry_check_status_display
            )
        st.dataframe(
            style_decision_registry_table(table_view),
            use_container_width=True,
            hide_index=True,
            height=PACKAGE_TABLE_HEIGHT_PX,
        )


def render_admission_secondary_panels(
    packages_df: pd.DataFrame,
    scope_df: pd.DataFrame,
    queue_df: pd.DataFrame,
    v2_lines_df: pd.DataFrame,
    department_sel: str,
) -> None:
    with st.expander("Детали выбранной строки и проверки", expanded=False):
        render_admission_line_details(packages_df, scope_df)

    render_decision_registry_module(queue_df, v2_lines_df)


def main() -> None:
    inject_admission_page_styles()

    st.title("Контур допуска месячного плана")
    st.caption(
        "Проверка готовности работ к включению в исполнимый месячный план. "
        "Каждый отдел допускает строки в своей зоне ответственности перед передачей в War Room."
    )

    base_df = load_constraints()
    if base_df.empty:
        st.info(
            "Строк в допуске пока нет. Отправьте план из "
            "10B Конструктора месячного плана v2."
        )
        return

    packages_base = build_package_dataframe(base_df)
    line_ids = tuple(
        safe_str(line_id)
        for line_id in packages_base.get("line_id", pd.Series(dtype=str)).tolist()
        if safe_str(line_id)
    )
    v2_lines_df = load_v2_plan_lines_for_constraints(line_ids)
    packages_enriched = enrich_packages_with_v2_lines(packages_base, v2_lines_df)

    check_status_opts = filter_options_ru(base_df, "check_status", CHECK_STATUS_RU)

    st.markdown("### Фильтры")
    with st.container():
        st.markdown('<div class="admission-v2-filters">', unsafe_allow_html=True)
        r1c1, r1c2, r1c3, r1c4, r1c5, r1c6 = st.columns(6)
        r2c1, r2c2, r2c3, r2c4, r2c5, r2c6 = st.columns([1.2, 1.2, 1.2, 1.0, 0.9, 0.8])

        month_opts = month_filter_options(packages_enriched)
        project_opts = package_filter_options(packages_enriched, "project_code")
        queue_opts = package_filter_options(packages_enriched, "queue_display")
        title_opts = package_filter_options(packages_enriched, "title_display")
        discipline_opts = package_filter_options(packages_enriched, "discipline_display")
        department_opts = filter_options(base_df, "responsible_department")

        apply_admission_filter_memory_before_widgets()

        init_filter_defaults(month_opts, FILTER_SESSION_KEYS["month"])
        init_filter_defaults(project_opts, FILTER_SESSION_KEYS["project"])
        init_filter_defaults(queue_opts, FILTER_SESSION_KEYS["queue"])
        init_filter_defaults(title_opts, FILTER_SESSION_KEYS["title"])
        init_filter_defaults(discipline_opts, FILTER_SESSION_KEYS["discipline"])
        init_filter_defaults(check_status_opts, FILTER_SESSION_KEYS["check_status"])
        init_filter_defaults(department_opts, FILTER_SESSION_KEYS["department"])
        if FILTER_SESSION_KEYS["search_boq"] not in st.session_state:
            st.session_state[FILTER_SESSION_KEYS["search_boq"]] = ""
        if FILTER_SESSION_KEYS["search_iwp"] not in st.session_state:
            st.session_state[FILTER_SESSION_KEYS["search_iwp"]] = ""
        if FILTER_SESSION_KEYS["search_system"] not in st.session_state:
            st.session_state[FILTER_SESSION_KEYS["search_system"]] = ""
        if FILTER_SESSION_KEYS["overdue_only"] not in st.session_state:
            st.session_state[FILTER_SESSION_KEYS["overdue_only"]] = False

        month_sel = r1c1.selectbox("Месяц", month_opts, key=FILTER_SESSION_KEYS["month"])
        project_sel = r1c2.selectbox("Проект", project_opts, key=FILTER_SESSION_KEYS["project"])
        queue_sel = r1c3.selectbox("Очередь", queue_opts, key=FILTER_SESSION_KEYS["queue"])
        title_sel = r1c4.selectbox("Титул", title_opts, key=FILTER_SESSION_KEYS["title"])
        discipline_sel = r1c5.selectbox(
            "Дисциплина", discipline_opts, key=FILTER_SESSION_KEYS["discipline"]
        )
        check_status_sel = r1c6.selectbox(
            "Статус проверки",
            check_status_opts,
            format_func=lambda v: CHECK_STATUS_RU.get(v, v) if v != "Все" else "Все",
            key=FILTER_SESSION_KEYS["check_status"],
        )

        search_boq = r2c1.text_input("Поиск BOQ", key=FILTER_SESSION_KEYS["search_boq"])
        search_iwp = r2c2.text_input("Поиск IWP", key=FILTER_SESSION_KEYS["search_iwp"])
        search_system = r2c3.text_input(
            "Поиск системы", key=FILTER_SESSION_KEYS["search_system"]
        )
        department_sel = r2c4.selectbox(
            "Отдел допуска",
            department_opts,
            format_func=lambda v: dept_ui(v) if v != "Все" else "Все",
            key=FILTER_SESSION_KEYS["department"],
        )
        overdue_only = r2c5.checkbox(
            "Только просроченные", key=FILTER_SESSION_KEYS["overdue_only"]
        )
        with r2c6:
            st.markdown('<div class="admission-filter-reset"></div>', unsafe_allow_html=True)

        r3c1, r3c2, r3c3, r3c4 = st.columns([1.3, 1.4, 1.3, 2.0])
        with r3c1:
            st.checkbox("Сохранять фильтры", key=ADMISSION_FILTER_MEMORY_ENABLED_KEY)
        with r3c2:
            if st.button("Зафиксировать фильтры", key="admission_filter_lock_btn"):
                lock_admission_filters()
                st.rerun()
        with r3c3:
            if st.button("Сбросить фильтры", key="admission_filter_reset_filters_btn"):
                request_admission_filters_reset()
                st.rerun()
        with r3c4:
            st.caption(admission_filter_status_text())

        sync_admission_filter_memory_after_widgets()
        st.markdown("</div>", unsafe_allow_html=True)

    packages_work = build_package_dataframe(base_df)
    packages_work = enrich_packages_with_v2_lines(packages_work, v2_lines_df)
    packages_df = apply_package_filters(
        packages_work,
        month_sel,
        project_sel,
        queue_sel,
        title_sel,
        discipline_sel,
        "Все",
        search_boq,
        search_iwp,
        search_system,
    )
    visible_package_keys = set(packages_df["package_key"].astype(str).tolist())
    scope_df = filter_constraints_by_package_keys(base_df, visible_package_keys)
    queue_df = filter_decision_registry_df(
        scope_df,
        department_sel,
        check_status_sel,
        overdue_only,
    )

    render_admission_plan_list_module(packages_df, scope_df)
    render_direct_admission_by_department_module(queue_df, packages_df, department_sel)

    # Legacy-блок деталей и ручного редактирования проверки временно скрыт из UI.
    # Основной контур допуска — «Непосредственный допуск по отделам».
    # render_admission_secondary_panels(packages_df, scope_df, queue_df, department_sel)

    render_decision_registry_module(queue_df, v2_lines_df)


if __name__ == "__main__":
    main()
