# ============================================================
# Конструктор месячного плана v2 — каркас страницы
# Production: pages/10_Planning_Конструктор_месячного_плана.py (не изменять)
# ============================================================

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from services.supabase_client import supabase

from services.constraints_service import create_constraints_for_plan_lines
from services.monthly_plan_draft_autosave import (
    clear_autosave_status,
    delete_draft_from_supabase,
    get_autosave_status,
    mark_draft_converted,
    record_autosave_error,
    record_autosave_not_needed,
    record_autosave_success,
)
from services.monthly_scope_adjustments import (
    adjustments_support_not_required_columns,
    delete_adjustment,
    fetch_adjustments_history_for_boq,
    fetch_all_adjustments_history,
    load_adjustments,
    load_scope,
    save_adjustment,
    save_not_required_exclusion,
)

# --- Константы UI (заглушки, без бизнес-логики) ---

PAGE_TITLE = "Конструктор месячного плана"
MONTH_PLAN_REGISTRY_TITLE = "Реестр строк месячного плана"

# TODO: hours_per_person_month must become configurable via planning_config.
# TODO: В будущем фонд часов должен рассчитываться динамически по выбранному месяцу:
# - смены месяца = календарные дни месяца минус воскресенья;
# - фонд = смены месяца × 8 часов;
# - например 26 смен × 8 = 208 ч/чел/мес;
# - текущее значение 176 ч/чел/мес остаётся как default из planning_config.
# Справочно: 176 ч/мес = пятидневная рабочая неделя; 208 ч/мес = 26 смен × 8 ч.
V2_HOURS_PER_PERSON_MONTH = 176
V2_FTE_FUND_HELP = f"Расчёт выполнен по фонду {V2_HOURS_PER_PERSON_MONTH} ч/чел/мес."
V2_FTE_FUND_LABEL = f"Фонд: {V2_HOURS_PER_PERSON_MONTH} ч/чел/мес"

# TODO: Продолжительность плана (KPI «расчётная продолжительность при текущем составе») требует
# отдельной модели календарного графика / уникального состава звеньев.
# sum(crew_size) по строкам реестра некорректен — люди одного звена дублируются на каждой строке.
# TODO: Duration by filtered slice requires calendar model and unique crew availability.
V2_PLAN_LABOR_COST_WARNING_STYLE = "color: #9B4D4D; font-weight: 600;"
V2_PLAN_LABOR_COST_COLUMN_HELP = (
    "Если стоимость труда выше стоимости работ — строка требует проверки нормы или расценки."
)

SCOPE_MODULE_TITLE = "Остатки и доступность к планированию"
SCOPE_MODULE_SUBTITLE = (
    "Контроль остатка работ, освоения и доступности к месячному планированию."
)

V2_PLANNING_MONTH_ALL = "Все месяца"

PLANNING_MONTH_OPTIONS = [
    V2_PLANNING_MONTH_ALL,
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


def _v2_is_all_months_filter(month_key: str) -> bool:
    return str(month_key or "").strip() == V2_PLANNING_MONTH_ALL


def _v2_resolve_planning_month_key(month_key: str) -> str:
    """Конкретный month_key или пустая строка для режима «Все месяца»."""
    resolved = str(month_key or "").strip()
    if _v2_is_all_months_filter(resolved):
        return ""
    return resolved

BOQ_SCOPE_TABLE_DISPLAY_COLUMNS = [
    "Статус",
    "Проект",
    "Очередь",
    "Титул",
    "Дисциплина",
    "Система",
    "IWP",
    "BOQ код",
    "Наименование работ",
    "Ед. изм.",
    "Всего в объёме",
    "Выполнено в объёме",
    "Ручная корректировка, объём",
    "Не освоим в объёме",
    "Доступно в объёме",
    "Всего в стоимости",
    "Выполнено в стоимости",
    "Не освоим в стоимости",
    "Превышение в стоимости",
    "Стоимость доступного объёма",
    "% исполнения",
    "% остатка",
    "Причина корректировки",
]

V2_PRJ_BHK_CODE_MARKERS = ("PRJ-001-БХК", "PRJ-001-BHK", "PRJ_001_БХК", "PRJ_001_BHK")
V2_ADJUSTMENT_AUDIT_DB_FIELDS = {
    "responsible_person": "updated_by",
    "adjustment_reason": "reason",
    "saved_at": "updated_at",
    "created_at": "created_at",
}

V2_ADJUSTMENT_REASON_PLACEHOLDER = (
    "Например: фактически выполнено до запуска Daily Progress / "
    "уточнение остатка / корректировка после проверки ПТО"
)
V2_MANUAL_ADJUSTMENT_REASON_OPTIONS = [
    "Выполнено до запуска Daily Progress",
    "Факт подтверждён актом/исполнительной документацией",
    "Ошибка исходного остатка",
    "Корректировка после сверки с участком",
    "Иное",
]
V2_QUEUE_FILTER_OPTIONS = ["Все", "1 очередь", "2 очередь", "Не определено"]
V2_V1_QUEUE_FACILITY_EXACT = {
    "1 очередь": ["16160-13", "16160-17"],
    "2 очередь": ["26160-13", "26160-17"],
}
V2_SCOPE_COST_COLUMNS = {
    "Всего в стоимости",
    "Выполнено в стоимости",
    "Не освоим в стоимости",
    "Превышение в стоимости",
    "Стоимость доступного объёма",
}

V2_SCOPE_QTY_COLUMNS = {
    "Всего в объёме",
    "Выполнено в объёме",
    "Ручная корректировка, объём",
    "Не освоим в объёме",
    "Доступно в объёме",
}

V2_SCOPE_PERCENT_COLUMNS = {
    "% исполнения",
    "% остатка",
}

V2_NOT_REQUIRED_REASON_OPTIONS = [
    "Ошибка проектного объёма",
    "Уточнение трассы / фактической потребности",
    "Работы не требуются по факту",
    "Исключено решением ПТО / руководителя",
    "Другое",
]
V2_SCOPE_STATUS_NOT_REQUIRED = "Остаток не требуется"
V2_SCOPE_STATUS_OVERRUN = "Превышение BOQ"

V2_SCOPE_STATUS_TABLE_DISPLAY_LABELS: dict[str, str] = {
    V2_SCOPE_STATUS_NOT_REQUIRED: "КОРРЕКТИРОВКА",
    V2_SCOPE_STATUS_OVERRUN: "ПРЕВЫШЕНИЕ",
    "Доступно": "ДОСТУПНО",
    "Выполнено": "ВЫПОЛНЕНО",
}

V2_SCOPE_TABLE_STATUS_TEXT_STYLES: dict[str, str] = {
    "ДОСТУПНО": "color: #A65D3F; font-weight: 600;",
    "ВЫПОЛНЕНО": "color: #4A7C59; font-weight: 600;",
    "ПРЕВЫШЕНИЕ": "color: #6B4C8A; font-weight: 600;",
    "КОРРЕКТИРОВКА": "color: #4A6FA5; font-weight: 600;",
    "Нет остатка": "color: #6B4C8A; font-weight: 600;",
    "Недоступно": "color: #6B4C8A; font-weight: 600;",
}
V2_SCOPE_TABLE_STATUS_TEXT_DEFAULT = "color: #334155; font-weight: 600;"

V2_SCOPE_STATUS_STYLES = {
    "Доступно": (
        "background-color: #EDF5EF; color: #245A32; border: 1px solid #D4E6D8; "
        "border-radius: 4px; font-weight: 600;"
    ),
    V2_SCOPE_STATUS_OVERRUN: (
        "background-color: #FAECEC; color: #8B2E2E; border: 1px solid #E8CECE; "
        "border-radius: 4px; font-weight: 600;"
    ),
    V2_SCOPE_STATUS_NOT_REQUIRED: (
        "background-color: #EDEAF3; color: #43365A; border: 1px solid #D8D2E4; "
        "border-radius: 4px; font-weight: 600;"
    ),
    "Частично запланировано": (
        "background-color: #EEF2F8; color: #2E4A62; border: 1px solid #D5DFEA; "
        "border-radius: 4px; font-weight: 600;"
    ),
    "Запланировано полностью": (
        "background-color: #F5EFE3; color: #6B4E2E; border: 1px solid #E6D9C4; "
        "border-radius: 4px; font-weight: 600;"
    ),
    "Выполнено": (
        "background-color: #E8EEF6; color: #1E4A73; border: 1px solid #CED9E8; "
        "border-radius: 4px; font-weight: 600;"
    ),
    "Перепланировано": (
        "background-color: #F3EBE6; color: #7A4A38; border: 1px solid #E5D5CC; "
        "border-radius: 4px; font-weight: 600;"
    ),
    "Требует проверки": (
        "background-color: #F0F2F5; color: #4B5563; border: 1px solid #DDE1E6; "
        "border-radius: 4px; font-weight: 600;"
    ),
    "Нет остатка": (
        "background-color: #F3F4F6; color: #5B6470; border: 1px solid #E2E5E9; "
        "border-radius: 4px; font-weight: 600;"
    ),
}

V2_SCOPE_COLUMN_WIDTHS_PX = [
    120, 88, 76, 100, 96, 140, 120, 120, 280, 52,
    82, 82, 96, 82, 88, 110, 110, 110, 110, 120, 72, 72, 180,
]

V2_SCOPE_TABLE_COLUMN_WIDTHS: dict[str, int] = {
    "Статус": 120,
    "Проект": 88,
    "Очередь": 76,
    "Титул": 100,
    "Дисциплина": 96,
    "Система": 140,
    "IWP": 120,
    "BOQ код": 120,
    "Наименование работ": 280,
    "Ед. изм.": 52,
    "Всего в объёме": 82,
    "Выполнено в объёме": 82,
    "Ручная корректировка, объём": 96,
    "Не освоим в объёме": 82,
    "Доступно в объёме": 88,
    "Всего в стоимости": 110,
    "Выполнено в стоимости": 110,
    "Не освоим в стоимости": 110,
    "Превышение в стоимости": 110,
    "Стоимость доступного объёма": 120,
    "% исполнения": 72,
    "% остатка": 72,
    "Причина корректировки": 180,
}

V2_PROGRESS_COLOR_EXECUTED = "#2E5B9A"
V2_PROGRESS_COLOR_REMAINING = "#C97A5C"
V2_PROGRESS_COLOR_AVAILABLE = "#6BAA75"

V2_SCOPE_STATUS_LEGEND = [
    ("Доступно", "#EDF5EF", "#245A32"),
    ("Превышение", "#FAECEC", "#8B2E2E"),
    ("Не требуется", "#EDEAF3", "#43365A"),
    ("Частично", "#EEF2F8", "#2E4A62"),
    ("Полностью", "#F5EFE3", "#6B4E2E"),
    ("Выполнено", "#E8EEF6", "#1E4A73"),
    ("Перепланировано", "#F3EBE6", "#7A4A38"),
    ("Проверка", "#F0F2F5", "#4B5563"),
]

V2_PLAN_REGISTRY_FILTER_KEYS = [
    "v2_plan_reg_filter_project",
    "v2_plan_reg_filter_queue",
    "v2_plan_reg_filter_title",
    "v2_plan_reg_filter_discipline",
    "v2_plan_reg_filter_system",
    "v2_plan_reg_filter_iwp",
    "v2_plan_reg_filter_crew",
    "v2_plan_reg_filter_boq",
]

V2_SCOPE_FILTER_SESSION_KEYS = [
    "v2_scope_planning_month",
    "v2_scope_project",
    "v2_scope_queue",
    "v2_scope_title",
    "v2_scope_discipline",
    "v2_scope_status",
    "v2_scope_search_boq",
    "v2_scope_search_iwp",
    "v2_scope_search_system",
]

BOQ_SCOPE_STATUS_OPTIONS = [
    "Все",
    "Доступно",
    V2_SCOPE_STATUS_OVERRUN,
    V2_SCOPE_STATUS_NOT_REQUIRED,
    "Частично запланировано",
    "Запланировано полностью",
    "Выполнено",
    "Перепланировано",
    "Требует проверки",
]

DEMO_SCOPE_KPI: dict[str, Any] = {
    "total_boq_codes": 262,
    "total_cost_rub": 158_869_841,
    "executed_rub": 47_006_782,
    "remaining_rub": 111_863_059,
    "available_qty": 69_783.81,
}

DEMO_SCOPE_PROJECTS = ["Все", "Проект А — Нефтепереработка", "Проект B — Компрессорная"]
DEMO_SCOPE_TITLES = ["Все", "Титул 1", "Титул 2", "Объект К-100"]
DEMO_SCOPE_DISCIPLINES = ["Все", "СМР", "ЭМ", "КИПиА", "ТХ"]

V2_SCOPE_VIEW = "monthly_scope_picker_view"

V2_PLAN_LINES_TABLE = "monthly_plan_lines_v2"
V2_PLAN_ITEMS_KEY = "v2_month_plan_items"
V2_PLAN_SCOPE_KEY = "v2_month_plan_scope"
V2_PLAN_DIRTY_KEY = "v2_month_plan_dirty"
V2_CURRENT_PLANNER_NAME_KEY = "v2_current_planner_name"
V2_PLAN_SELECTED_KEYS = "v2_plan_selected_row_keys"
V2_PLAN_EDIT_ROW_KEY = "v2_plan_edit_row_key"
V2_DRAFT_ITEMS_KEY = V2_PLAN_ITEMS_KEY
V2_PLAN_STATUS_NOT_SENT = "NOT_SENT"
V2_PLAN_STATUS_SENT = "SENT_TO_ADMISSION"
V2_PLAN_STATUS_UI: dict[str, str] = {
    V2_PLAN_STATUS_NOT_SENT: "В допуск не отправлен",
    V2_PLAN_STATUS_SENT: "Отправлен в допуск",
}
V2_PLAN_STATUS_STYLES: dict[str, str] = {
    "В допуск не отправлен": (
        "background-color: #FFF6E5; color: #8A5A00; border: 1px solid #F0E4C8;"
    ),
    "Отправлен в допуск": (
        "background-color: #ECFDF5; color: #047857; border: 1px solid #C6EDE0;"
    ),
}
V2_SAVED_DRAFT_ID_KEY = "v2_saved_draft_id"
V2_DRAFT_LOAD_DEBUG_KEY = "v2_draft_load_debug"
V2_DRAFT_STATUS_SAVED = "SAVED_DRAFT"
V2_DRAFT_SOURCE_MARKER = "constructor_v2"
DEFAULT_LABOR_RATE_PER_HOUR = 3000.0
PRODUCTIVE_HOURS_PER_PERSON_SHIFT = 8.0
NORM_SCENARIO_REALISTIC = "Реалистичная норма"
NORM_SCENARIO_CAUTIOUS = "Осторожная норма"
NORM_SCENARIO_MANUAL = "Ручная норма"
NORM_SCENARIO_OPTIONS = [
    NORM_SCENARIO_REALISTIC,
    NORM_SCENARIO_CAUTIOUS,
    NORM_SCENARIO_MANUAL,
]
V2_CREW_FALLBACK_OPTIONS = [
    "Звено не выбрано",
    "CREW-01",
    "CREW-02",
    "CREW-03",
]
V2_INVALID_CREW_LABELS = {"Звено не выбрано", "", "—", "-"}

V2_SCOPE_INTERNAL_COLUMNS = [
    "project_code",
    "construction_queue",
    "facility",
    "discipline",
    "system",
    "iwp",
    "boq_code",
    "boq_name",
    "unit",
    "total_qty",
    "executed_qty",
    "daily_executed_qty",
    "executed_total_qty",
    "effective_required_qty",
    "not_required_qty",
    "remaining_qty",
    "overrun_qty",
    "already_planned_qty",
    "planned_month",
    "planned_at",
    "available_to_add_qty",
    "percent_executed",
    "status",
    "unit_price",
    "total_value",
    "remaining_value",
    "executed_value",
    "overrun_value",
    "percent_remaining",
    "remaining_qty_source",
    "manual_executed_before_system",
    "manual_verified_remaining_qty",
    "manual_adjustment_reason",
    "manual_adjustment_comment",
    "manual_adjustment_updated_at",
    "manual_adjustment_qty",
    "manual_adjustment_source",
    "norm_hours_per_unit",
    "norm_type",
    "productivity_history",
    "p50_hours_per_unit",
    "p80_hours_per_unit",
    "weighted_avg_hours_per_unit",
    "norm_status",
    "not_required_reason",
    "not_required_responsible_person",
    "not_required_comment",
    "not_required_updated_at",
]

V2_SCOPE_NUMERIC_FIELDS = {
    "total_qty",
    "executed_qty",
    "daily_executed_qty",
    "executed_total_qty",
    "effective_required_qty",
    "not_required_qty",
    "remaining_qty",
    "overrun_qty",
    "already_planned_qty",
    "available_to_add_qty",
    "unit_price",
    "total_value",
    "remaining_value",
    "executed_value",
    "overrun_value",
    "manual_executed_before_system",
    "manual_verified_remaining_qty",
    "norm_hours_per_unit",
    "p50_hours_per_unit",
    "p80_hours_per_unit",
    "weighted_avg_hours_per_unit",
    "percent_executed",
    "percent_remaining",
}

V2_MANUAL_ADJUSTMENT_VIEW_COLUMNS = [
    "manual_executed_before_system",
    "manual_verified_remaining_qty",
    "remaining_qty_source",
    "manual_adjustment_reason",
    "manual_adjustment_comment",
    "updated_at",
]

V2_SCOPE_FIELD_ALIASES: dict[str, list[str]] = {
    "boq_code": ["boq_code", "BOQ код", "BOQ-код", "Код"],
    "boq_name": ["boq_name", "Наименование работ", "description", "name"],
    "unit": ["unit_of_measure", "unit", "Ед. изм.", "Ед."],
    "facility": ["facility_building", "facility", "Титул / объект", "Титул"],
    "discipline": ["construction_discipline", "discipline", "Дисциплина"],
    "construction_queue": ["construction_phase", "construction_queue", "phase", "queue", "Очередь"],
    "system": ["system", "system_label", "systems", "Система"],
    "iwp": ["iwp", "iwp_id", "iwp_code", "IWP"],
    "total_qty": ["total_project_qty", "total_qty", "project_qty", "Было", "Всего"],
    "executed_qty": ["executed_qty_all_time", "executed_qty", "Выполнено"],
    "remaining_qty": ["planning_remaining_qty", "remaining_qty", "Остаток"],
    "remaining_value": ["planning_remaining_value", "remaining_value"],
    "remaining_qty_source": ["remaining_qty_source"],
    "unit_price": ["unit_price", "unit_price_num"],
    "total_value": ["total_project_value", "total_value", "total_value_num"],
    "already_planned_qty": ["already_planned_qty", "already_planned", "Уже в плане"],
    "planned_month": ["planned_month", "plan_month", "month_planned"],
    "planned_at": ["planned_at", "plan_date", "planned_date"],
    "available_to_add_qty": ["available_to_add_qty", "available_remaining_qty", "Доступно"],
    "manual_executed_before_system": ["manual_executed_before_system"],
    "manual_verified_remaining_qty": ["manual_verified_remaining_qty"],
    "manual_adjustment_reason": ["manual_adjustment_reason", "reason"],
    "manual_adjustment_comment": ["manual_adjustment_comment", "comment"],
    "manual_adjustment_updated_at": ["updated_at", "manual_adjustment_updated_at"],
    "manual_adjustment_qty": [
        "manual_executed_before_system",
        "manual_adjustment_qty",
    ],
    "manual_adjustment_source": [
        "manual_adjustment_source",
        "manual_adjustment_reason",
    ],
    "norm_hours_per_unit": [
        "p50_hours_per_unit",
        "weighted_avg_hours_per_unit",
        "norm_hours_per_unit",
    ],
    "norm_type": ["norm_type", "norm_status"],
    "productivity_history": ["productivity_history", "norm_status"],
    "p50_hours_per_unit": ["p50_hours_per_unit"],
    "p80_hours_per_unit": ["p80_hours_per_unit"],
    "weighted_avg_hours_per_unit": ["weighted_avg_hours_per_unit"],
    "norm_status": ["norm_status", "norm_type"],
}

MONTH_PLAN_COLUMNS = [
    "Дата добавления",
    "Статус",
    "BOQ код",
    "Наименование",
    "Объём",
    "Трудозатраты",
    "Стоимость",
    "Звено",
    "Комментарий",
]

V2_MONTH_PLAN_DISPLAY_COLUMNS = [
    "Статус",
    "Проект",
    "Планировщик",
    "Дата планирования",
    "Время планирования МСК",
    "Очередь",
    "Титул",
    "Дисциплина",
    "Система",
    "IWP",
    "BOQ код",
    "Наименование работ",
    "Объём",
    "Ед.",
    "Звено",
    "Людей",
    "Норма",
    "Норма ч/ед.",
    "Произв. 1 чел/ч",
    "Произв. 1 чел/смена",
    "Произв. звена/смена",
    "Трудозатраты",
    "Длительность",
    "Стоимость объёма",
    "Стоимость труда",
]

V2_MONTH_PLAN_NUMERIC_COLUMNS = {
    "Объём",
    "Людей",
    "Норма ч/ед.",
    "Произв. 1 чел/ч",
    "Произв. 1 чел/смена",
    "Произв. звена/смена",
    "Стоимость объёма",
    "Стоимость труда",
}

V2_SESSION_DRAFT_STATUS = "Новая строка"


def inject_page_styles() -> None:
    st.markdown(
        """
        <style>
        .constructor-v2-header {
            margin-bottom: 1rem;
            font-size: 1.65rem;
            font-weight: 700;
            color: #0f172a;
            letter-spacing: -0.02em;
        }
        .constructor-v2-scope-module-title {
            font-size: 1.12rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 0.2rem 0;
            letter-spacing: -0.01em;
        }
        .constructor-v2-scope-module-subtitle {
            color: #64748b;
            font-size: 0.86rem;
            line-height: 1.4;
            margin: 0 0 1rem 0;
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
            min-height: 88px;
        }
        .v2-kpi-card-icon {
            flex: 0 0 34px;
            width: 34px;
            height: 34px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.95rem;
            font-weight: 700;
        }
        .v2-kpi-card--boq .v2-kpi-card-icon { background: #E8EEF5; color: #475F7B; }
        .v2-kpi-card--budget .v2-kpi-card-icon { background: #E7F5EE; color: #2F6B4F; }
        .v2-kpi-card--executed .v2-kpi-card-icon { background: #E6EEF8; color: #2E5B9A; }
        .v2-kpi-card--remaining .v2-kpi-card-icon { background: #F9EDE8; color: #A65F45; }
        .v2-kpi-card--available .v2-kpi-card-icon { background: #EAF4EC; color: #3F7A4A; }
        .v2-kpi-card-body { min-width: 0; }
        .v2-kpi-card-label {
            font-size: 0.72rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.15rem;
        }
        .v2-kpi-card-value {
            font-size: 1.45rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.15;
            margin-bottom: 0.1rem;
        }
        .v2-kpi-card-hint {
            font-size: 0.74rem;
            color: #94a3b8;
            line-height: 1.3;
        }
        .v2-scope-filters-actions {
            display: flex;
            align-items: center;
            gap: 0.65rem;
            margin-top: 0.15rem;
        }
        .v2-scope-reset-btn button {
            background: #ffffff !important;
            color: #475569 !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 6px !important;
            min-height: 38px !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            padding: 0.25rem 0.75rem !important;
        }
        .v2-scope-reset-btn button:hover {
            background: #f8fafc !important;
            border-color: #94a3b8 !important;
            color: #334155 !important;
        }
        .constructor-v2-module-hint {
            color: #64748b;
            font-size: 0.88rem;
            line-height: 1.45;
            margin: 0.5rem 0 1rem 0;
        }
        .constructor-v2-placeholder-box {
            border: 1px dashed #cbd5e1;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            background: #f8fafc;
            color: #64748b;
            font-size: 0.85rem;
            margin-top: 0.5rem;
        }
        .constructor-v2-scope-panel {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.85rem 1rem 0.35rem 1rem;
            background: #ffffff;
            margin-bottom: 0.75rem;
        }
        .constructor-v2-scope-panel-title {
            font-size: 0.82rem;
            font-weight: 600;
            color: #334155;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.65rem;
        }
        .constructor-v2-scope-module-title {
            font-size: 1.12rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 0.2rem 0;
            letter-spacing: -0.01em;
        }
        .constructor-v2-scope-module-subtitle {
            color: #64748b;
            font-size: 0.86rem;
            line-height: 1.4;
            margin: 0 0 1rem 0;
        }
        .constructor-v2-kpi-value {
            font-size: 1.35rem;
            font-weight: 600;
            color: #0f172a;
            line-height: 1.2;
            margin: 0.1rem 0 0.2rem 0;
        }
        .constructor-v2-kpi-label {
            font-size: 0.78rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .constructor-v2-kpi-hint {
            font-size: 0.76rem;
            color: #94a3b8;
        }
        .constructor-v2-boq-card-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: #0f172a;
            margin: 0;
        }
        .constructor-v2-boq-card-meta {
            color: #64748b;
            font-size: 0.86rem;
            margin: 0.15rem 0 0.65rem 0;
        }
        .constructor-v2-boq-card-status {
            font-size: 0.82rem;
            font-weight: 600;
            color: #475569;
            text-align: right;
        }
        .constructor-v2-mgmt-note {
            color: #334155;
            font-size: 0.88rem;
            padding-top: 0.5rem;
            border-top: 1px solid #e2e8f0;
            margin-top: 0.65rem;
        }
        .v2-scope-filters [data-testid="stSelectbox"] > div > div,
        .v2-scope-filters [data-testid="stTextInput"] input {
            background-color: #ffffff !important;
            border: 1px solid #d1d5db !important;
            border-radius: 6px !important;
            color: #1f2937 !important;
        }
        .v2-scope-filters [data-testid="stTextInput"] input:focus {
            border-color: #3b5b7a !important;
            box-shadow: 0 0 0 1px #3b5b7a !important;
        }
        .v2-scope-filters [data-testid="stSelectbox"] > div > div:focus-within {
            border-color: #3b5b7a !important;
            box-shadow: 0 0 0 1px #3b5b7a !important;
        }
        .v2-scope-filters [data-baseweb="select"] > div {
            background-color: #ffffff !important;
        }
        .v2-scope-status-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem 0.5rem;
            margin: 0.35rem 0 0.55rem 0;
        }
        .v2-scope-status-badge {
            display: inline-block;
            padding: 0.15rem 0.55rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 600;
            line-height: 1.3;
            white-space: nowrap;
        }
        .v2-scope-boq-table [data-testid="stDataFrame"],
        .v2-month-plan-table [data-testid="stDataFrame"] {
            font-size: 0.84rem;
        }
        .v2-scope-boq-table [data-testid="stDataFrame"] td,
        .v2-scope-boq-table [data-testid="stDataFrame"] th,
        .v2-month-plan-table [data-testid="stDataFrame"] td,
        .v2-month-plan-table [data-testid="stDataFrame"] th {
            padding: 0.28rem 0.45rem !important;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .v2-scope-boq-table [data-testid="stDataFrame"] {
            overflow-x: auto;
        }
        .v2-month-plan-table [data-testid="stDataFrame"] {
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            overflow-x: auto;
            overflow-y: hidden;
        }
        .v2-month-plan-table [data-testid="stDataFrame"] thead th {
            background: #f8fafc !important;
            color: #475569 !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            border-bottom: 1px solid #e2e8f0 !important;
        }
        .v2-month-plan-table [data-testid="stDataFrame"] tbody td {
            border-bottom: 1px solid #f1f5f9 !important;
            color: #1e293b;
            line-height: 1.25;
            max-height: 2.6em;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .v2-month-plan-table [data-testid="stDataFrame"] div[data-testid="stDataFrameResizable"] {
            overflow-x: auto !important;
        }
        .v2-month-plan-kpi-bar {
            margin: 0.35rem 0 0.75rem 0;
            padding: 0.55rem 0.75rem;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #fafbfc;
        }
        .v2-month-plan-kpi-bar-row2 {
            margin-top: 0.45rem;
            padding-top: 0.45rem;
            border-top: 1px solid #e8edf2;
        }
        .v2-month-plan-kpi-fund-caption {
            font-size: 0.72rem;
            color: #64748b;
            margin-top: -0.15rem;
            line-height: 1.25;
        }
        .v2-month-plan-kpi-fte-wrap {
            display: flex;
            flex-direction: column;
            gap: 0.1rem;
            min-height: 4.5rem;
            justify-content: center;
        }
        .v2-month-plan-kpi-fte-head {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.35rem 0.55rem;
            font-size: 0.78rem;
            color: #64748b;
            line-height: 1.25;
        }
        .v2-month-plan-kpi-fte-label {
            font-weight: 500;
        }
        .v2-month-plan-kpi-fund-inline {
            font-size: 0.72rem;
            font-weight: 600;
            color: #475569;
            white-space: nowrap;
        }
        .v2-month-plan-kpi-fte-value {
            font-size: 1.45rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.1;
            margin: 0;
        }
        .v2-month-plan-action-bar-anchor {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .v2-month-plan-action-bar-anchor + div[data-testid="stHorizontalBlock"] {
            background: #f7f9fc !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 14px !important;
            padding: 8px 10px !important;
            margin: 0.35rem 0 0.6rem 0 !important;
            align-items: stretch !important;
            gap: 0.4rem !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
        }
        .v2-month-plan-action-bar-anchor + div[data-testid="stHorizontalBlock"] > div {
            display: flex;
            align-items: stretch;
            min-height: 0;
        }
        .v2-month-plan-action-bar-anchor + div[data-testid="stHorizontalBlock"] > div:nth-child(1) {
            border-right: 1px solid #e2e8f0;
            padding-right: 0.55rem;
            flex: 0 0 auto;
            min-width: 11rem;
        }
        .v2-plan-metrics-row {
            display: flex;
            flex-direction: row;
            align-items: center;
            gap: 0.75rem;
            height: 100%;
            padding: 0.15rem 0.25rem;
        }
        .v2-plan-metric-inline {
            display: inline-flex;
            align-items: baseline;
            gap: 0.35rem;
            white-space: nowrap;
        }
        .v2-plan-metrics-stack {
            display: flex;
            flex-direction: column;
            gap: 0.3rem;
            width: 6.25rem;
            height: 100%;
            justify-content: center;
        }
        .v2-plan-metric-card {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 0.15rem;
            width: 100%;
            height: 3.1rem;
            min-height: 3.1rem;
            padding: 0.38rem 0.5rem;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            background: #ffffff;
            box-sizing: border-box;
        }
        .v2-plan-metric-top {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.28rem;
            width: 100%;
        }
        .v2-plan-metric-label {
            font-size: 0.66rem;
            font-weight: 500;
            color: #64748b;
            line-height: 1.1;
        }
        .v2-plan-metric-value {
            font-size: 1.28rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1;
            text-align: center;
            width: 100%;
        }
        .v2-plan-btn-hook {
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }
        div:has(> .v2-plan-btn-hook) {
            margin: 0 !important;
            padding: 0 !important;
            min-height: 0 !important;
            line-height: 0 !important;
        }
        div:has(.v2-plan-btn-hook) + div[data-testid="stButton"] {
            margin-bottom: 0 !important;
        }
        .v2-month-plan-action-bar-anchor + div[data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button {
            justify-content: center !important;
        }
        .v2-month-plan-action-bar-anchor + div[data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button p {
            text-align: center !important;
        }
        div:has(.v2-plan-btn-hook-clear) + div[data-testid="stButton"] {
            margin-bottom: 0 !important;
        }
        .v2-month-plan-action-bar-anchor ~ div [data-testid="stHorizontalBlock"] [data-testid="stButton"] {
            width: 100%;
        }
        .v2-month-plan-action-bar-anchor ~ div [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button {
            width: 100% !important;
            min-height: 30px !important;
            max-height: 32px !important;
            border-radius: 10px !important;
            font-size: 0.74rem !important;
            font-weight: 600 !important;
            padding: 0.28rem 0.6rem !important;
            line-height: 1.1 !important;
            box-shadow: none !important;
            transition: transform 140ms ease, background 140ms ease, border-color 140ms ease, box-shadow 140ms ease !important;
            justify-content: flex-start !important;
            gap: 0.35rem !important;
        }
        .v2-month-plan-action-bar-anchor ~ div [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button p {
            white-space: nowrap !important;
            text-align: left !important;
            margin: 0 !important;
            line-height: 1.1 !important;
            font-size: 0.74rem !important;
            font-weight: 600 !important;
        }
        .v2-month-plan-action-bar-anchor ~ div [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button:disabled {
            opacity: 0.45 !important;
            cursor: not-allowed !important;
        }
        .v2-month-plan-action-bar-anchor ~ div [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button:hover:not(:disabled) {
            transform: translateY(-1px);
        }
        div:has(.v2-plan-btn-hook-send) + div[data-testid="stButton"] > button {
            background: linear-gradient(135deg, #486a9a, #34465a) !important;
            color: #ffffff !important;
            border: none !important;
            box-shadow: 0 1px 4px rgba(52, 70, 90, 0.16) !important;
        }
        div:has(.v2-plan-btn-hook-send) + div[data-testid="stButton"] > button:hover:not(:disabled) {
            background: linear-gradient(135deg, #557aa8, #3d536c) !important;
            box-shadow: 0 2px 8px rgba(52, 70, 90, 0.2) !important;
        }
        div:has(.v2-plan-btn-hook-send) + div[data-testid="stButton"] > button p {
            color: #ffffff !important;
            letter-spacing: 0.03em;
        }
        div:has(.v2-plan-btn-hook-save) + div[data-testid="stButton"] > button {
            background: #ffffff !important;
            color: #4a78b5 !important;
            border: 1px solid #4a78b5 !important;
        }
        div:has(.v2-plan-btn-hook-save) + div[data-testid="stButton"] > button:hover:not(:disabled) {
            background: #f4f8fc !important;
            box-shadow: 0 1px 4px rgba(74, 120, 181, 0.12) !important;
        }
        div:has(.v2-plan-btn-hook-save) + div[data-testid="stButton"] > button p {
            color: #4a78b5 !important;
        }
        div:has(.v2-plan-btn-hook-edit) + div[data-testid="stButton"] > button {
            background: #ffffff !important;
            color: #334155 !important;
            border: 1px solid #cbd5e1 !important;
        }
        div:has(.v2-plan-btn-hook-edit) + div[data-testid="stButton"] > button:hover:not(:disabled) {
            background: #f8fafc !important;
        }
        div:has(.v2-plan-btn-hook-edit) + div[data-testid="stButton"] > button p {
            color: #334155 !important;
        }
        div:has(.v2-plan-btn-hook-delete) + div[data-testid="stButton"] > button {
            background: #fff7f7 !important;
            color: #a33a3a !important;
            border: 1px solid #e6b8b8 !important;
        }
        div:has(.v2-plan-btn-hook-delete) + div[data-testid="stButton"] > button:hover:not(:disabled) {
            background: #fef2f2 !important;
        }
        div:has(.v2-plan-btn-hook-delete) + div[data-testid="stButton"] > button p {
            color: #a33a3a !important;
        }
        div:has(.v2-plan-btn-hook-clear) + div[data-testid="stButton"] > button {
            background: #ffffff !important;
            color: #64748b !important;
            border: 1px solid #e2e8f0 !important;
            font-weight: 500 !important;
        }
        div:has(.v2-plan-btn-hook-clear) + div[data-testid="stButton"] > button:hover:not(:disabled) {
            background: #f8fafc !important;
        }
        div:has(.v2-plan-btn-hook-clear) + div[data-testid="stButton"] > button p {
            color: #64748b !important;
            font-weight: 500 !important;
        }
        .v2-month-plan-action-bar-anchor ~ div [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button [data-testid="stIconMaterial"] {
            font-size: 0.95rem !important;
            flex-shrink: 0;
        }
        div:has(.v2-plan-btn-hook-send) + div[data-testid="stButton"] > button [data-testid="stIconMaterial"] {
            color: #ffffff !important;
        }
        div:has(.v2-plan-btn-hook-save) + div[data-testid="stButton"] > button [data-testid="stIconMaterial"] {
            color: #4a78b5 !important;
        }
        div:has(.v2-plan-btn-hook-edit) + div[data-testid="stButton"] > button [data-testid="stIconMaterial"] {
            color: #334155 !important;
        }
        div:has(.v2-plan-btn-hook-delete) + div[data-testid="stButton"] > button [data-testid="stIconMaterial"] {
            color: #a33a3a !important;
        }
        div:has(.v2-plan-btn-hook-clear) + div[data-testid="stButton"] > button [data-testid="stIconMaterial"] {
            color: #64748b !important;
        }
        .v2-month-plan-edit-panel {
            margin: 0.5rem 0 0.75rem 0;
            padding: 0.65rem 0.85rem;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #fafbfc;
        }
        .v2-boq-detail-panel {
            padding: 0.15rem 0.1rem 0.35rem 0.1rem;
        }
        .v2-boq-detail-code {
            font-size: 1.2rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0;
            letter-spacing: -0.01em;
        }
        .v2-boq-detail-name {
            font-size: 0.94rem;
            color: #334155;
            margin: 0.25rem 0 0.35rem 0;
            line-height: 1.35;
        }
        .v2-boq-detail-volume {
            font-size: 1.35rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 0.5rem 0;
            line-height: 1.2;
        }
        .v2-boq-detail-volume-unit {
            font-size: 0.92rem;
            font-weight: 600;
            color: #64748b;
            margin-left: 0.25rem;
        }
        .v2-boq-detail-context {
            font-size: 0.8rem;
            color: #64748b;
            margin: 0 0 0.65rem 0;
            line-height: 1.35;
        }
        .v2-boq-detail-section {
            margin-top: 0.55rem;
            padding-top: 0.55rem;
            border-top: 1px solid #e2e8f0;
        }
        .v2-boq-detail-section-title {
            font-size: 0.76rem;
            font-weight: 700;
            color: #475569;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            margin-bottom: 0.35rem;
        }
        .v2-boq-detail-metric {
            margin-bottom: 0.15rem;
        }
        .v2-boq-detail-metric span {
            display: block;
            font-size: 0.72rem;
            color: #64748b;
        }
        .v2-boq-detail-metric strong {
            font-size: 0.92rem;
            color: #0f172a;
            font-weight: 600;
        }
        .v2-boq-status-badge {
            display: inline-block;
            padding: 0.2rem 0.55rem;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 600;
            white-space: nowrap;
        }
        .v2-boq-decision-badge {
            display: inline-block;
            margin-top: 0.55rem;
            padding: 0.35rem 0.65rem;
            border-radius: 8px;
            font-size: 0.82rem;
            font-weight: 600;
            border: 1px solid #dbe3ea;
            background: #f8fafc;
            color: #334155;
        }
        .v2-boq-decision-badge.positive {
            background: #ecfdf3;
            border-color: #bbf7d0;
            color: #166534;
        }
        .v2-boq-decision-badge.warning {
            background: #fff7ed;
            border-color: #fed7aa;
            color: #9a3412;
        }
        .v2-boq-decision-badge.muted {
            background: #f1f5f9;
            border-color: #e2e8f0;
            color: #64748b;
        }
        .v2-boq-source-badge {
            display: inline-block;
            padding: 0.22rem 0.55rem;
            border-radius: 999px;
            font-size: 0.74rem;
            font-weight: 600;
            border: 1px solid #e2e8f0;
            background: #f8fafc;
            color: #475569;
        }
        .v2-boq-source-badge.system {
            background: #f1f5f9;
            color: #475569;
        }
        .v2-boq-source-badge.manual-exec {
            background: #eff6ff;
            color: #1e40af;
            border-color: #dbeafe;
        }
        .v2-boq-source-badge.manual-verified {
            background: #fff7ed;
            color: #9a3412;
            border-color: #fed7aa;
        }
        .v2-boq-manual-adj-note {
            font-size: 0.78rem;
            color: #64748b;
            margin: 0.45rem 0 0.05rem 0;
            line-height: 1.4;
        }
        .v2-boq-manual-adj-field {
            margin-bottom: 0.2rem;
        }
        .v2-boq-manual-adj-field span {
            display: block;
            font-size: 0.72rem;
            color: #64748b;
        }
        .v2-boq-manual-adj-field strong {
            font-size: 0.86rem;
            color: #0f172a;
            font-weight: 600;
        }
        .v2-boq-manual-adj-mode {
            font-size: 0.74rem;
            font-weight: 700;
            color: #475569;
            margin: 0 0 0.35rem 0;
        }
        .v2-boq-manual-adj-formula {
            font-size: 0.78rem;
            color: #64748b;
            line-height: 1.45;
            margin: 0.1rem 0 0.4rem 0;
        }
        .v2-boq-manual-adj-form-tag {
            font-size: 0.72rem;
            color: #94a3b8;
            margin: 0 0 0.35rem 0;
        }
        .v2-boq-manual-adj-save-note {
            font-size: 0.74rem;
            color: #64748b;
            margin: 0.25rem 0 0;
            line-height: 1.35;
        }
        .v2-boq-action-panel {
            padding: 0.55rem 0.65rem 0.6rem 0.65rem;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #fafbfc;
            height: 100%;
        }
        .v2-boq-action-title {
            font-size: 0.84rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0 0 0.15rem 0;
        }
        .v2-boq-action-purpose {
            font-size: 0.74rem;
            color: #64748b;
            margin: 0 0 0.45rem 0;
            line-height: 1.35;
        }
        .v2-boq-action-status {
            display: inline-block;
            padding: 0.15rem 0.45rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 600;
            border: 1px solid #e2e8f0;
            background: #f8fafc;
            color: #475569;
            margin-bottom: 0.35rem;
        }
        .v2-boq-action-status.active {
            background: #eff6ff;
            border-color: #dbeafe;
            color: #1e40af;
        }
        .v2-boq-action-status.verified {
            background: #fff7ed;
            border-color: #fed7aa;
            color: #9a3412;
        }
        .v2-boq-action-footnote {
            font-size: 0.72rem;
            color: #94a3b8;
            margin: 0.35rem 0 0.15rem 0;
            line-height: 1.35;
        }
        .v2-boq-detail-expander-note {
            font-size: 0.78rem;
            color: #64748b;
            margin: 0 0 0.45rem 0;
            line-height: 1.35;
        }
        .v2-boq-adj-journal-title {
            font-size: 0.78rem;
            font-weight: 700;
            color: #475569;
            margin: 0.65rem 0 0.35rem 0;
        }
        .v2-boq-adj-rollback {
            margin-top: 0.55rem;
            padding: 0.55rem 0.65rem;
            border: 1px solid #e7e5e4;
            border-radius: 8px;
            background: #fafaf9;
        }
        .v2-boq-adj-rollback-title {
            font-size: 0.8rem;
            font-weight: 600;
            color: #78716c;
            margin: 0;
        }
        .v2-boq-adj-rollback-desc {
            font-size: 0.74rem;
            color: #a8a29e;
            margin: 0.25rem 0 0.45rem 0;
            line-height: 1.35;
        }
        .v2-boq-calc-formula {
            font-size: 0.76rem;
            color: #64748b;
            line-height: 1.4;
            margin: 0.45rem 0 0.2rem 0;
        }
        .v2-boq-calc-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.25rem 0.55rem;
            font-size: 0.8rem;
            color: #0f172a;
            margin-top: 0.25rem;
        }
        .v2-boq-calc-strip .sep {
            color: #cbd5e1;
        }
        .v2-boq-calc-strip label {
            font-size: 0.72rem;
            color: #64748b;
            margin-right: 0.2rem;
        }
        .v2-boq-calc-strip strong {
            font-weight: 600;
        }
        .v2-plan-add-zone {
            margin: 0.35rem 0 0.55rem 0;
        }
        .v2-plan-add-context {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem 0.5rem;
            padding: 0.45rem 0.55rem;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            background: #f8fafc;
            margin-bottom: 0.45rem;
        }
        .v2-plan-add-context .chip {
            display: inline-flex;
            flex-direction: column;
            gap: 0.05rem;
            padding: 0.2rem 0.45rem;
            border-radius: 6px;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            min-width: 4.5rem;
        }
        .v2-plan-add-context .chip label {
            font-size: 0.68rem;
            color: #64748b;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .v2-plan-add-context .chip strong {
            font-size: 0.82rem;
            color: #0f172a;
            font-weight: 600;
        }
        .v2-plan-add-context .chip.highlight strong {
            color: #166534;
        }
        .v2-plan-add-name {
            font-size: 0.78rem;
            color: #475569;
            margin: 0 0 0.45rem 0;
            line-height: 1.35;
        }
        .v2-plan-add-preview {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.25rem 0.65rem;
            padding: 0.4rem 0.55rem;
            border: 1px solid #dbeafe;
            border-radius: 8px;
            background: #eff6ff;
            margin: 0.35rem 0 0.45rem 0;
            font-size: 0.8rem;
        }
        .v2-plan-add-preview label {
            font-size: 0.68rem;
            color: #64748b;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            display: block;
        }
        .v2-plan-add-preview strong {
            font-size: 0.86rem;
            color: #1e3a8a;
            font-weight: 700;
        }
        .v2-plan-add-preview .sep {
            color: #93c5fd;
        }
        .v2-plan-add-duration-hint {
            font-size: 0.72rem;
            color: #64748b;
            margin: -0.25rem 0 0.35rem 0.55rem;
        }
        .v2-plan-add-warn {
            font-size: 0.76rem;
            color: #92400e;
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-radius: 6px;
            padding: 0.35rem 0.5rem;
            margin: 0.25rem 0 0.35rem 0;
        }
        .v2-plan-add-norm-hint {
            font-size: 0.72rem;
            color: #64748b;
            margin: 0.15rem 0 0.35rem 0;
            line-height: 1.35;
        }
        .v2-plan-add-norm-strip {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.25rem 0.55rem;
            font-size: 0.76rem;
            color: #334155;
            padding: 0.35rem 0.5rem;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            background: #f8fafc;
            margin-bottom: 0.35rem;
        }
        .v2-plan-add-norm-strip label {
            font-size: 0.68rem;
            color: #64748b;
            margin-right: 0.15rem;
        }
        .v2-plan-add-norm-strip strong {
            font-weight: 600;
            color: #0f172a;
        }
        .v2-plan-add-norm-strip .sep {
            color: #cbd5e1;
        }
        .v2-plan-add-norm-strip.missing {
            background: #fffbeb;
            border-color: #fde68a;
            color: #92400e;
        }
        .v2-boq-volume-row {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.65rem 1rem;
            margin-bottom: 0.65rem;
        }
        .v2-boq-volume-cell {
            min-width: 0;
        }
        .v2-boq-volume-cell.highlight {
            background: #F4FAF5;
            border: 1px solid #D5E8D8;
            border-radius: 8px;
            padding: 0.45rem 0.55rem;
        }
        .v2-boq-volume-label {
            display: block;
            font-size: 0.68rem;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            margin-bottom: 0.2rem;
            white-space: nowrap;
        }
        .v2-boq-volume-values {
            display: flex;
            flex-direction: column;
            gap: 0.12rem;
        }
        .v2-boq-volume-qty {
            font-size: 1.28rem;
            font-weight: 700;
            color: #0f172a;
            line-height: 1.1;
        }
        .v2-boq-volume-cost {
            font-size: 0.92rem;
            font-weight: 600;
            color: #475569;
            line-height: 1.1;
        }
        .v2-boq-volume-cost.executed {
            color: #2E5B9A;
        }
        .v2-boq-volume-pct {
            font-size: 1.15rem;
            font-weight: 700;
            line-height: 1.1;
            color: #0f172a;
        }
        .v2-boq-progress-track {
            display: flex;
            width: 100%;
            height: 28px;
            border-radius: 6px;
            overflow: hidden;
            border: 1px solid #e2e8f0;
            background: #f8fafc;
        }
        .v2-boq-progress-segment {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            min-width: 0;
            font-size: 0.68rem;
            font-weight: 600;
            color: #ffffff;
            white-space: nowrap;
            overflow: hidden;
            padding: 0 0.35rem;
        }
        .v2-boq-progress-segment.executed {
            background: linear-gradient(180deg, #3A6FA8 0%, #2E5B9A 100%);
        }
        .v2-boq-progress-segment.remaining {
            background: linear-gradient(180deg, #D4896C 0%, #C97A5C 100%);
        }
        .v2-boq-progress-segment.available {
            background: linear-gradient(180deg, #7BB885 0%, #6BAA75 100%);
        }
        .constructor-v2-boq-card {
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 0.85rem 1rem;
            background: #f8fafc;
            margin-top: 0.5rem;
        }
        .v2-draft-autosave-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem 1.25rem;
            align-items: center;
            padding: 0.55rem 0.85rem;
            margin: 0.35rem 0 0.75rem 0;
            border-radius: 10px;
            border: 1px solid #e2e8f0;
            background: #f8fafc;
            font-size: 0.86rem;
            color: #334155;
        }
        .v2-draft-autosave-bar--ok {
            border-color: #bbf7d0;
            background: #f0fdf4;
        }
        .v2-draft-autosave-bar--error {
            border-color: #fecaca;
            background: #fef2f2;
        }
        .v2-draft-autosave-bar--found {
            border-color: #fde68a;
            background: #fffbeb;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header() -> None:
    st.markdown(f'<h1 class="constructor-v2-header">{PAGE_TITLE}</h1>', unsafe_allow_html=True)
    st.caption("активная версия v2")


def _empty_table(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def render_module_upload_inputs() -> None:
    """Модуль 0: загрузка исходных данных (архитектурная заглушка)."""
    st.markdown(
        '<p class="constructor-v2-module-hint">'
        "Здесь будет выполняться загрузка исходных файлов для построения месячного плана. "
        "На текущем этапе модуль работает как архитектурная заглушка: файлы не обрабатываются, "
        "не сохраняются и не передаются в production-контур."
        "</p>",
        unsafe_allow_html=True,
    )

    st.markdown("#### 📊 Excel-файлы")
    excel_files = st.file_uploader(
        "Загрузить Excel-файлы для будущего расчёта месячного плана",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        key="v2_excel_uploader",
    )
    st.caption(
        "Предполагаемые типы файлов: BOQ, объёмы работ, нормы трудозатрат, "
        "звенья, месячный бюджет труда, месячный бюджет затрат."
    )

    st.markdown("#### 📄 Word-документы")
    word_files = st.file_uploader(
        "Загрузить Word-документы для будущего анализа исходных требований",
        type=["docx", "doc"],
        accept_multiple_files=True,
        key="v2_word_uploader",
    )
    st.caption(
        "Предполагаемые типы документов: пояснительные записки, требования заказчика, "
        "протоколы, регламенты, технические условия."
    )

    st.session_state.v2_excel_upload_count = len(excel_files) if excel_files else 0
    st.session_state.v2_word_upload_count = len(word_files) if word_files else 0

    def _upload_status(count: int) -> str:
        if count == 0:
            return "Ожидает загрузки"
        return f"Загружено {count} файлов"

    st.markdown("**Статус загрузки**")
    status_df = pd.DataFrame(
        [
            {
                "Категория": "Excel-файлы",
                "Статус": _upload_status(st.session_state.v2_excel_upload_count),
                "Комментарий": "Файлы пока не обрабатываются",
            },
            {
                "Категория": "Word-документы",
                "Статус": _upload_status(st.session_state.v2_word_upload_count),
                "Комментарий": "Документы пока не анализируются",
            },
        ]
    )
    st.dataframe(status_df, use_container_width=True, hide_index=True, height=120)

    st.info(
        "Следующий этап развития модуля: определить состав обязательных файлов, "
        "шаблоны колонок, правила валидации и staging-контур перед записью данных в Supabase."
    )


def _format_rub(value: float) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")


def _format_qty(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ")


def _v2_safe_num(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


_V2_EMPTY_TEXT_VALUES = frozenset({"", "nan", "None", "<NA>"})


def _v2_pick_series(df: pd.DataFrame, field: str, default: Any = "") -> pd.Series:
    aliases = V2_SCOPE_FIELD_ALIASES.get(field, [field])
    present = [col for col in aliases if col in df.columns]

    if field in V2_SCOPE_NUMERIC_FIELDS:
        for col in present:
            return pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return pd.Series([0.0] * len(df), index=df.index)

    if not present:
        return pd.Series([default] * len(df), index=df.index)

    result = pd.Series(pd.NA, index=df.index, dtype=object)
    for col in present:
        candidate = df[col].fillna("").astype(str).str.strip()
        candidate = candidate.mask(candidate.isin(_V2_EMPTY_TEXT_VALUES), pd.NA)
        result = result.fillna(candidate)

    return result.fillna(default).astype(str).str.strip()


def _v2_round_display_qty(value: Any) -> float:
    val = _v2_safe_num(value)
    rounded = round(val, 2)
    if abs(rounded - round(rounded)) < 1e-9:
        return float(int(round(rounded)))
    return rounded


def _v2_format_qty_display_str(value: Any) -> str:
    val = _v2_round_display_qty(value)
    if abs(val - round(val)) < 1e-9:
        return str(int(round(val)))
    text = f"{val:.2f}".rstrip("0").rstrip(".")
    return text


def _v2_calculate_percent_executed(total_qty: Any, executed_qty: Any) -> float:
    total = _v2_safe_num(total_qty)
    executed = _v2_safe_num(executed_qty)
    if total <= 0:
        return 0.0
    return executed / total * 100.0


def _v2_calculate_percent_executed_production(
    total_value: Any,
    executed_value: Any,
    total_qty: Any,
    executed_qty: Any,
) -> float:
    total_val = _v2_safe_num(total_value)
    if total_val > 0:
        executed_val = max(0.0, _v2_safe_num(executed_value))
        return executed_val / total_val * 100.0
    return _v2_calculate_percent_executed(total_qty, executed_qty)


def _v2_value_per_unit_series(
    total_qty: pd.Series,
    total_value: pd.Series,
    unit_price: pd.Series,
) -> pd.Series:
    tq = pd.to_numeric(total_qty, errors="coerce").fillna(0.0)
    tv = pd.to_numeric(total_value, errors="coerce").fillna(0.0)
    up = pd.to_numeric(unit_price, errors="coerce").fillna(0.0)
    per_unit = up.astype(float).copy()
    mask = tq > 0
    per_unit.loc[mask] = (tv.loc[mask] / tq.loc[mask]).astype(float)
    return per_unit


def _v2_safe_df_col(
    df: pd.DataFrame,
    col_name: str,
    default: float | pd.Series = 0.0,
) -> pd.Series:
    """Безопасное чтение числовой колонки без KeyError."""
    if col_name in df.columns:
        return pd.to_numeric(df[col_name], errors="coerce").fillna(0.0)
    if isinstance(default, pd.Series):
        return pd.to_numeric(default, errors="coerce").fillna(0.0)
    return pd.Series([float(default)] * len(df), index=df.index, dtype=float)


def _v2_resolve_scoped_unit_price_series(df: pd.DataFrame) -> pd.Series:
    """Ставка за единицу из известных колонок scoped row."""
    unit = pd.Series([0.0] * len(df), index=df.index, dtype=float)
    for col in ("unit_price", "unit_rate", "price_per_unit", "v2_unit_price"):
        if col in df.columns:
            unit = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            break
    return _v2_value_per_unit_series(
        _v2_safe_df_col(df, "total_qty"),
        _v2_safe_df_col(df, "total_value"),
        unit,
    )


def _v2_scope_remaining_value_series(scoped_df: pd.DataFrame) -> pd.Series:
    if "remaining_value" in scoped_df.columns:
        return _v2_safe_df_col(scoped_df, "remaining_value")
    qty = _v2_safe_df_col(scoped_df, "remaining_qty")
    return qty * _v2_resolve_scoped_unit_price_series(scoped_df)


def _v2_scope_executed_value_series(scoped_df: pd.DataFrame) -> pd.Series:
    if "executed_value" in scoped_df.columns:
        return _v2_safe_df_col(scoped_df, "executed_value")
    total = _v2_safe_df_col(scoped_df, "total_value")
    remaining = _v2_scope_remaining_value_series(scoped_df)
    return (total - remaining).clip(lower=0.0)


def _v2_scope_table_executed_value_series(scoped_df: pd.DataFrame) -> pd.Series:
    """Стоимость выполненного объёма для таблицы BOQ (только display).

    В scoped row ``executed_value`` = ``total_value - remaining_value``; при остатке 0
    после корректировки это даёт всю стоимость BOQ, а не фактически выполненный объём.
    Для таблицы: ``executed_total_qty × ставка``, не выше ``total_value``.
    """
    per_unit = _v2_resolve_scoped_unit_price_series(scoped_df)
    executed_qty = _v2_safe_df_col(scoped_df, "executed_total_qty")
    total_value = _v2_safe_df_col(scoped_df, "total_value")
    return (executed_qty * per_unit).clip(lower=0.0).clip(upper=total_value)


def _v2_scope_available_value_series(scoped_df: pd.DataFrame) -> pd.Series:
    if "available_to_add_value" in scoped_df.columns:
        return _v2_safe_df_col(scoped_df, "available_to_add_value")
    if "available_value" in scoped_df.columns:
        return _v2_safe_df_col(scoped_df, "available_value")
    qty = _v2_safe_df_col(scoped_df, "available_to_add_qty")
    return qty * _v2_resolve_scoped_unit_price_series(scoped_df)


def _v2_has_manual_verified_remaining(value: Any) -> bool:
    return not _v2_is_missing_numeric(value)


def _v2_verified_remaining_ignored_by_overrun(item: pd.Series) -> bool:
    return _v2_safe_num(item.get("overrun_qty")) > 0 and _v2_has_manual_verified_remaining(
        item.get("manual_verified_remaining_qty")
    )


def _v2_merge_not_required_from_adjustments(df: pd.DataFrame) -> pd.DataFrame:
    """Подмешать исключения остатка из monthly_scope_manual_adjustments."""
    out = df.copy()
    out["not_required_qty"] = 0.0
    out["not_required_reason"] = ""
    out["not_required_responsible_person"] = ""
    out["not_required_comment"] = ""
    out["not_required_updated_at"] = ""

    adj = load_adjustments()
    if adj.empty or "not_required_qty" not in adj.columns:
        return out

    lookup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for _, row in adj.iterrows():
        lookup[_v2_adjustment_record_key(row.to_dict())] = row.to_dict()

    for idx, row in out.iterrows():
        key = _v2_adjustment_record_key(
            {
                "project_code": row.get("project_code"),
                "facility_building": row.get("facility"),
                "construction_discipline": row.get("discipline"),
                "boq_code": row.get("boq_code"),
            }
        )
        rec = lookup.get(key)
        if not rec:
            continue
        out.at[idx, "not_required_qty"] = _v2_safe_num(rec.get("not_required_qty"))
        out.at[idx, "not_required_reason"] = str(rec.get("not_required_reason") or "").strip()
        out.at[idx, "not_required_responsible_person"] = str(
            rec.get("not_required_responsible_person") or ""
        ).strip()
        out.at[idx, "not_required_comment"] = str(rec.get("not_required_comment") or "").strip()
        out.at[idx, "not_required_updated_at"] = str(rec.get("not_required_updated_at") or "").strip()
    return out


def _v2_raw_remaining_before_exclusion(item: pd.Series) -> float:
    total = _v2_safe_num(item.get("total_qty"))
    executed_total = _v2_safe_num(
        item.get(
            "executed_total_qty",
            _v2_safe_num(item.get("executed_qty"))
            + _v2_safe_num(item.get("manual_executed_before_system")),
        )
    )
    return max(total - executed_total, 0.0)


V2_QTY_COMPARE_EPSILON = 1e-6


def _v2_qty_exceeds_limit(entered_qty: float, limit_qty: float) -> bool:
    """Сравнение объёмов с учётом float precision (UI 17.8 vs ввод 17.80)."""
    entered = round(float(entered_qty), 3)
    limit = round(float(limit_qty), 3)
    return entered > limit + V2_QTY_COMPARE_EPSILON


def _v2_format_qty_validation_str(value: Any) -> str:
    """Формат объёма в сообщениях валидации (2 знака после запятой)."""
    return f"{_v2_safe_num(value):.2f}"


def _v2_apply_boq_availability_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Физический остаток и доступность к планированию.

    Приоритет:
    1. executed_total_qty = daily_executed_qty + manual_executed_before_system
    2. effective_required_qty = total_qty - not_required_qty
    3. overrun относительно effective_required_qty
    4. manual_verified_remaining_qty — только без overrun
    5. not_required + выполнено >= effective → статус «Остаток не требуется»
    """
    if df.empty:
        return df
    out = df.copy()
    total = pd.to_numeric(out["total_qty"], errors="coerce").fillna(0.0)
    daily_executed = pd.to_numeric(out.get("executed_qty"), errors="coerce").fillna(0.0)
    manual_before = pd.to_numeric(
        out.get("manual_executed_before_system", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0)
    not_required = pd.to_numeric(
        out.get("not_required_qty", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    executed_total = daily_executed + manual_before
    planned = pd.to_numeric(
        out.get("already_planned_qty", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0)
    effective_required = (total - not_required).clip(lower=0.0)

    out["daily_executed_qty"] = daily_executed
    out["executed_total_qty"] = executed_total
    out["executed_qty"] = daily_executed
    out["not_required_qty"] = not_required
    out["effective_required_qty"] = effective_required

    verified = pd.to_numeric(
        out.get("manual_verified_remaining_qty", pd.Series(float("nan"), index=out.index)),
        errors="coerce",
    )
    has_verified = verified.notna()

    per_unit = _v2_value_per_unit_series(
        total,
        out.get("total_value", pd.Series(0.0, index=out.index)),
        out.get("unit_price", pd.Series(0.0, index=out.index)),
    )

    out["overrun_qty"] = (executed_total - effective_required).clip(lower=0.0)
    is_overrun = out["overrun_qty"] > 0
    out["remaining_qty"] = (effective_required - executed_total).clip(lower=0.0)
    out["available_to_add_qty"] = (effective_required - executed_total - planned).clip(lower=0.0)

    out.loc[is_overrun, "remaining_qty"] = 0.0
    out.loc[is_overrun, "available_to_add_qty"] = 0.0

    no_overrun = ~is_overrun
    if has_verified.any():
        verified_remaining = verified.clip(lower=0.0)
        verified_mask = has_verified & no_overrun
        out.loc[verified_mask, "remaining_qty"] = verified_remaining.loc[verified_mask]
        out.loc[verified_mask, "available_to_add_qty"] = (
            verified_remaining.loc[verified_mask] - planned.loc[verified_mask]
        ).clip(lower=0.0)

    out["verified_remaining_ignored"] = has_verified & is_overrun

    out["remaining_value"] = out["remaining_qty"] * per_unit
    out["overrun_value"] = out["overrun_qty"] * per_unit
    out["available_to_add_value"] = out["available_to_add_qty"] * per_unit
    out.loc[is_overrun, "remaining_value"] = 0.0
    out.loc[is_overrun, "available_to_add_value"] = 0.0
    total_value = pd.to_numeric(out.get("total_value", 0), errors="coerce").fillna(0.0)
    out["executed_value"] = (total_value - out["remaining_value"]).clip(lower=0.0)
    return out


def _v2_resolve_scope_status_row(row: pd.Series) -> str:
    if _v2_safe_num(row.get("overrun_qty")) > 0:
        return V2_SCOPE_STATUS_OVERRUN
    not_required = _v2_safe_num(row.get("not_required_qty"))
    effective_required = _v2_safe_num(row.get("effective_required_qty"))
    executed_total = _v2_safe_num(row.get("executed_total_qty"))
    remaining = _v2_safe_num(row.get("remaining_qty"))
    available = _v2_safe_num(row.get("available_to_add_qty"))
    planned = _v2_safe_num(row.get("already_planned_qty"))
    if (
        not_required > 0
        and remaining <= 0
        and executed_total >= effective_required
        and effective_required > 0
    ):
        return V2_SCOPE_STATUS_NOT_REQUIRED
    return _v2_resolve_available_status(remaining, available, planned)


def _v2_pick_view_numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    """Числовая колонка view без fillna(0) — NaN означает «нет значения»."""
    if column not in df.columns:
        return pd.Series([float("nan")] * len(df), index=df.index)
    return pd.to_numeric(df[column], errors="coerce")


def _v2_format_percent_display_str(value: Any) -> str:
    pct = _v2_safe_num(value)
    rounded = round(pct, 1)
    if abs(rounded - round(rounded)) < 1e-9:
        return f"{int(round(rounded))}%"
    return f"{rounded:.1f}%"


def _v2_detail_boq_costs(item: pd.Series) -> dict[str, float]:
    """Production-стоимости BOQ для detail panel (из scoped row)."""
    total_value = _v2_safe_num(item.get("total_value"))
    remaining_value = _v2_safe_num(item.get("remaining_value"))
    executed_value = _v2_safe_num(item.get("executed_value"))
    overrun_value = _v2_safe_num(item.get("overrun_value"))
    available_value = _v2_safe_num(item.get("available_to_add_value"))
    overrun_qty = _v2_safe_num(item.get("overrun_qty"))
    available_qty = _v2_safe_num(item.get("available_to_add_qty"))

    if overrun_qty > 0:
        remaining_value = 0.0
        available_value = 0.0
        if overrun_value <= 0:
            per_unit = _v2_value_per_unit_series(
                pd.Series([item.get("total_qty")]),
                pd.Series([total_value]),
                pd.Series([item.get("unit_price", 0.0)]),
            ).iloc[0]
            overrun_value = overrun_qty * per_unit
    elif available_qty <= 0:
        available_value = 0.0

    if executed_value <= 0 and total_value > 0:
        executed_value = max(0.0, total_value - remaining_value)
    if total_value <= 0:
        unit_price = _v2_safe_num(item.get("unit_price"))
        total_qty = _v2_safe_num(item.get("total_qty"))
        total_value = total_qty * unit_price
        if remaining_value <= 0 and overrun_qty <= 0:
            remaining_value = _v2_safe_num(item.get("remaining_qty")) * unit_price
        executed_value = max(0.0, total_value - remaining_value)
        if available_qty > 0 and available_value <= 0:
            available_value = available_qty * unit_price
    return {
        "total_value": total_value,
        "executed_value": executed_value,
        "remaining_value": remaining_value,
        "overrun_value": overrun_value,
        "available_value": available_value,
    }


def _v2_detail_volume_percents(item: pd.Series) -> tuple[float, float]:
    """% освоения и остаток в % для detail panel (max 1 знак после запятой)."""
    if "percent_executed" in item.index:
        pct_executed = round(_v2_safe_num(item.get("percent_executed")), 1)
    else:
        costs = _v2_detail_boq_costs(item)
        pct_executed = round(
            _v2_calculate_percent_executed_production(
                costs["total_value"],
                costs["executed_value"],
                item.get("total_qty"),
                item.get("executed_total_qty", item.get("executed_qty")),
            ),
            1,
        )
    if "percent_remaining" in item.index:
        pct_remaining = round(_v2_safe_num(item.get("percent_remaining")), 1)
    else:
        pct_remaining = round(max(0.0, 100.0 - pct_executed), 1)
    return pct_executed, pct_remaining


def _v2_render_boq_volume_acquisition_html(item: pd.Series) -> str:
    """Enterprise секция «Объём и освоение»: метрики + segmented progress bar."""
    costs = _v2_detail_boq_costs(item)
    pct_executed, pct_remaining = _v2_detail_volume_percents(item)
    pct_executed_str = _v2_format_percent_display_str(pct_executed)
    pct_remaining_str = _v2_format_percent_display_str(pct_remaining)
    unit = str(item.get("unit") or "").strip()

    total_qty = _v2_safe_num(item.get("total_qty"))
    not_required_qty = _v2_safe_num(item.get("not_required_qty"))
    effective_required_qty = _v2_safe_num(
        item.get("effective_required_qty", max(total_qty - not_required_qty, 0.0))
    )
    daily_executed_qty = _v2_safe_num(item.get("daily_executed_qty", item.get("executed_qty")))
    manual_before_qty = _v2_safe_num(item.get("manual_executed_before_system"))
    executed_total_qty = _v2_safe_num(
        item.get("executed_total_qty", daily_executed_qty + manual_before_qty)
    )
    remaining_qty = _v2_safe_num(item.get("remaining_qty"))
    overrun_qty = _v2_safe_num(item.get("overrun_qty"))
    available_qty = max(0.0, _v2_safe_num(item.get("available_to_add_qty")))
    is_overrun = overrun_qty > 0

    per_unit = (
        costs["total_value"] / total_qty
        if total_qty > 0
        else _v2_safe_num(item.get("unit_price"))
    )
    daily_executed_value = daily_executed_qty * per_unit
    manual_before_value = manual_before_qty * per_unit
    executed_total_value = min(executed_total_qty * per_unit, costs["total_value"]) if costs["total_value"] > 0 else executed_total_qty * per_unit
    not_required_reason = _v2_format_optional_text(item.get("not_required_reason"))
    not_required_person = _v2_format_optional_text(item.get("not_required_responsible_person"))
    not_required_at = format_v2_added_at_moscow(item.get("not_required_updated_at")) or "—"

    progress_base = effective_required_qty if effective_required_qty > 0 else total_qty
    if progress_base > 0:
        exec_width = min(max(executed_total_qty / progress_base * 100.0, 0.0), 100.0)
        avail_width = min(max(available_qty / progress_base * 100.0, 0.0), 100.0)
        blocked_width = min(
            max((remaining_qty - available_qty) / progress_base * 100.0, 0.0),
            max(0.0, 100.0 - exec_width - avail_width),
        )
    elif total_qty > 0:
        exec_width = min(max(executed_total_qty / total_qty * 100.0, 0.0), 100.0)
        avail_width = min(max(available_qty / total_qty * 100.0, 0.0), 100.0)
        blocked_width = min(
            max((remaining_qty - available_qty) / total_qty * 100.0, 0.0),
            max(0.0, 100.0 - exec_width - avail_width),
        )
    else:
        exec_width = avail_width = blocked_width = 0.0

    exec_label = f"Выполнено {pct_executed_str}" if exec_width >= 10 else ""
    blocked_label = f"Остаток {pct_remaining_str}" if blocked_width >= 10 and not is_overrun else ""
    avail_label = (
        f"Доступно {_v2_format_qty_display_str(available_qty)} {unit}".strip()
        if avail_width >= 8 and not is_overrun
        else ""
    )

    overrun_cell = ""
    if is_overrun:
        overrun_cell = f"""
  <div class="v2-boq-volume-cell overrun">
    <span class="v2-boq-volume-label">Превышение BOQ</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(overrun_qty)}</span>
      <span class="v2-boq-volume-cost overrun">{_format_rub(costs["overrun_value"])}</span>
    </div>
  </div>"""

    overrun_warning = ""
    if is_overrun:
        overrun_warning = (
            '<div class="v2-plan-add-warn">'
            "Факт превышает BOQ. Требуется проверка Daily Progress / BOQ / допработ."
            "</div>"
        )
    verified_ignored_warning = ""
    if _v2_verified_remaining_ignored_by_overrun(item):
        verified_ignored_warning = (
            '<div class="v2-plan-add-warn">'
            "Ручной подтверждённый остаток не применён, так как факт выполнения уже превышает BOQ."
            "</div>"
        )

    return f"""
<div class="v2-boq-detail-section-title">Объём и освоение</div>
<div class="v2-boq-volume-row">
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Проектный объём</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(total_qty)}</span>
      <span class="v2-boq-volume-cost">{_format_rub(costs["total_value"])}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Исключено из выполнения</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(not_required_qty)}</span>
      <span class="v2-boq-volume-cost">{not_required_reason}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Рабочий объём к выполнению</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(effective_required_qty)}</span>
      <span class="v2-boq-volume-cost">{unit or "—"}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Выполнено по Daily Progress</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(daily_executed_qty)}</span>
      <span class="v2-boq-volume-cost executed">{_format_rub(daily_executed_value)}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Выполнено до 03.11</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(manual_before_qty)}</span>
      <span class="v2-boq-volume-cost">{_format_rub(manual_before_value)}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Выполнено всего</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(executed_total_qty)}</span>
      <span class="v2-boq-volume-cost executed">{_format_rub(executed_total_value)}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Остаток к выполнению</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(remaining_qty)}</span>
      <span class="v2-boq-volume-cost">{_format_rub(costs["remaining_value"])}</span>
    </div>
  </div>{overrun_cell}
  <div class="v2-boq-volume-cell highlight">
    <span class="v2-boq-volume-label">Доступно к планированию</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(available_qty)}</span>
      <span class="v2-boq-volume-cost">{_format_rub(costs["available_value"])}</span>
    </div>
  </div>
</div>
<div class="v2-boq-volume-row">
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Кто внёс исключение</span>
    <span class="v2-boq-volume-pct">{not_required_person}</span>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Когда внёс</span>
    <span class="v2-boq-volume-pct">{not_required_at}</span>
  </div>
</div>
<div class="v2-boq-progress-track">
  <div class="v2-boq-progress-segment executed" style="width:{exec_width:.4f}%;">{exec_label}</div>
  <div class="v2-boq-progress-segment remaining" style="width:{blocked_width:.4f}%;">{blocked_label}</div>
  <div class="v2-boq-progress-segment available" style="width:{avail_width:.4f}%;">{avail_label}</div>
</div>
{overrun_warning}
{verified_ignored_warning}
"""


def _v2_map_adjustment_source(raw: Any) -> str:
    code = str(raw or "").strip().upper()
    if not code:
        return "Не применялась"
    mapping = {
        "MANUAL_VERIFIED": "Ручной остаток",
        "MANUAL_EXECUTED_BEFORE_SYSTEM": "Корректировка выполненного",
        "SYSTEM_CALCULATED": "Не применялась",
    }
    return mapping.get(code, str(raw).strip() or "Не применялась")


def _v2_format_remaining_qty_source_label(raw: Any) -> str:
    """Отображение remaining_qty_source для блока ручной корректировки."""
    code = str(raw or "").strip().upper()
    if not code:
        return "Не определено"
    mapping = {
        "SYSTEM_CALCULATED": "Системный расчёт",
        "MANUAL_EXECUTED_BEFORE_SYSTEM": "Учтён ранее выполненный объём",
        "MANUAL_VERIFIED": "Подтверждённый остаток вручную",
    }
    return mapping.get(code, str(raw).strip() or "Не определено")


def _v2_remaining_source_badge_html(raw: Any) -> str:
    code = str(raw or "").strip().upper()
    label = _v2_format_remaining_qty_source_label(raw)
    tone = "system"
    if code == "MANUAL_EXECUTED_BEFORE_SYSTEM":
        tone = "manual-exec"
    elif code == "MANUAL_VERIFIED":
        tone = "manual-verified"
    return f'<span class="v2-boq-source-badge {tone}">{label}</span>'


def _v2_is_missing_numeric(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and not str(value).strip():
        return True
    return False


def _v2_format_manual_executed_display(value: Any) -> str:
    if _v2_is_missing_numeric(value):
        return "Не применялось"
    qty = _v2_safe_num(value)
    if qty <= 0:
        return "Не применялось"
    return _v2_format_qty_display_str(qty)


def _v2_format_manual_verified_display(value: Any) -> str:
    if _v2_is_missing_numeric(value):
        return "Не задано"
    return _v2_format_qty_display_str(value)


def _v2_format_optional_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Не указано"
    text = str(value).strip()
    return text if text else "Не указано"


def _v2_format_adjustment_datetime(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "Не указано"
    text = str(value).strip()
    if not text:
        return "Не указано"
    try:
        return pd.to_datetime(text).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return text


def _v2_format_draft_added_at(value: Any) -> str:
    """Короткий формат даты добавления в session draft."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return pd.to_datetime(text).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return text


def format_v2_added_at_moscow(added_at: Any) -> str:
    """Display-only: ISO UTC added_at → Europe/Moscow DD.MM.YYYY HH:MM."""
    if added_at is None or (isinstance(added_at, float) and pd.isna(added_at)):
        return ""
    text = str(added_at).strip()
    if not text:
        return ""
    try:
        parsed = pd.to_datetime(text, utc=False)
        if pd.isna(parsed):
            return ""
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize(timezone.utc)
        else:
            parsed = parsed.tz_convert(timezone.utc)
        moscow = parsed.tz_convert(ZoneInfo("Europe/Moscow"))
        return moscow.strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


def _v2_format_planned_date_moscow(planned_at: Any) -> str:
    """Дата планирования (МСК) для таблицы месячного плана."""
    formatted = format_v2_added_at_moscow(planned_at)
    if not formatted:
        return "—"
    return formatted.split(" ", 1)[0]


def _v2_format_planned_time_moscow(planned_at: Any) -> str:
    """Время планирования (МСК) для таблицы месячного плана."""
    formatted = format_v2_added_at_moscow(planned_at)
    if not formatted or " " not in formatted:
        return "—"
    return formatted.split(" ", 1)[1]


def _v2_manual_adjustment_row_fields(item: pd.Series) -> dict[str, Any]:
    """Read-only поля корректировки из scoped row с production-fallback."""
    manual_exec_raw = item.get("manual_executed_before_system", item.get("manual_adjustment_qty", 0))
    manual_exec = 0.0 if _v2_is_missing_numeric(manual_exec_raw) else _v2_safe_num(manual_exec_raw)

    verified_raw = item.get("manual_verified_remaining_qty")
    manual_verified = None if _v2_is_missing_numeric(verified_raw) else _v2_safe_num(verified_raw)

    source_raw = item.get("remaining_qty_source", "")
    if source_raw is None or (isinstance(source_raw, float) and pd.isna(source_raw)):
        remaining_source = "Не определено"
    else:
        remaining_source = str(source_raw).strip() or "Не определено"

    return {
        "manual_executed_before_system": manual_exec,
        "manual_verified_remaining_qty": manual_verified,
        "remaining_qty_source": remaining_source,
        "manual_adjustment_reason": item.get("manual_adjustment_reason", ""),
        "manual_adjustment_comment": item.get("manual_adjustment_comment", ""),
        "manual_adjustment_updated_at": item.get("manual_adjustment_updated_at"),
        "total_qty": _v2_safe_num(item.get("total_qty")),
        "executed_qty": _v2_safe_num(item.get("executed_qty")),
        "remaining_qty": _v2_safe_num(item.get("remaining_qty")),
    }


def _v2_render_remaining_calc_strip_html(fields: dict[str, Any]) -> str:
    """Компактная строка: Всего | Daily Progress | Ранее выполнено | Остаток."""
    parts = [
        ("Всего", _v2_format_qty_display_str(fields["total_qty"])),
        ("Daily Progress", _v2_format_qty_display_str(fields["executed_qty"])),
        ("Ранее выполнено", _v2_format_qty_display_str(fields["manual_executed_before_system"])),
        ("Остаток", _v2_format_qty_display_str(fields["remaining_qty"])),
    ]
    cells = "".join(
        f"<span><label>{label}</label><strong>{value}</strong></span>"
        + ('<span class="sep">|</span>' if idx < len(parts) - 1 else "")
        for idx, (label, value) in enumerate(parts)
    )
    return f'<div class="v2-boq-calc-strip">{cells}</div>'


def _v2_parse_norm_hours_value(value: Any) -> float | None:
    if value is None or str(value).strip() in {"", "-", "—"}:
        return None
    parsed = _v2_safe_num(value, default=float("nan"))
    if pd.isna(parsed) or parsed <= 0:
        return None
    return parsed


def init_v2_session_state() -> None:
    legacy_key = "v2_month_plan_draft_items"
    if legacy_key in st.session_state and V2_PLAN_ITEMS_KEY not in st.session_state:
        st.session_state[V2_PLAN_ITEMS_KEY] = st.session_state.pop(legacy_key)
    if V2_PLAN_ITEMS_KEY not in st.session_state:
        st.session_state[V2_PLAN_ITEMS_KEY] = []
    if V2_PLAN_SCOPE_KEY not in st.session_state:
        st.session_state[V2_PLAN_SCOPE_KEY] = ""
    if V2_PLAN_DIRTY_KEY not in st.session_state:
        st.session_state[V2_PLAN_DIRTY_KEY] = False
    if V2_PLAN_SELECTED_KEYS not in st.session_state:
        st.session_state[V2_PLAN_SELECTED_KEYS] = []
    if V2_PLAN_EDIT_ROW_KEY not in st.session_state:
        st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""
    for key, value in _v2_default_scope_filter_values().items():
        st.session_state.setdefault(key, value)
    for key, value in _v2_default_plan_registry_filter_values().items():
        st.session_state.setdefault(key, value)


def _v2_boq_draft_key_parts(
    project_code: str,
    facility: str,
    discipline: str,
    boq_code: str,
    month_key: str,
) -> tuple[str, str, str, str, str]:
    return (
        str(project_code or "").strip().upper(),
        str(facility or "").strip().upper(),
        str(discipline or "").strip().upper(),
        str(boq_code or "").strip().upper(),
        str(month_key or "").strip().lower(),
    )


def _v2_boq_draft_key_from_row(row: pd.Series, month_key: str) -> tuple[str, str, str, str, str]:
    return _v2_boq_draft_key_parts(
        str(row.get("project_code") or ""),
        str(row.get("facility") or ""),
        str(row.get("discipline") or ""),
        str(row.get("boq_code") or ""),
        month_key,
    )


def build_v2_session_planned_qty_map(
    month_key: str | None = None,
) -> dict[tuple[str, str, str, str, str], float]:
    """Сумма planned_qty только для несохранённых добавлений (is_pending), без DB-плана."""
    items: list[dict[str, Any]] = st.session_state.get(V2_DRAFT_ITEMS_KEY) or []
    month_filter = str(month_key or "").strip().lower()
    result: dict[tuple[str, str, str, str, str], float] = {}
    for draft in items:
        if draft.get("is_pending") is not True:
            continue
        key = _v2_boq_draft_key_parts(
            str(draft.get("project_code") or ""),
            str(draft.get("facility") or ""),
            str(draft.get("discipline") or ""),
            str(draft.get("boq_code") or ""),
            str(draft.get("month_key") or ""),
        )
        if month_filter and key[4] != month_filter:
            continue
        result[key] = result.get(key, 0.0) + _v2_safe_num(draft.get("planned_qty"))
    return result


def build_v2_session_planned_meta_map(
    month_key: str | None = None,
) -> dict[tuple[str, str, str, str, str], dict[str, str]]:
    """month_key и added_at по BOQ-key только для несохранённых добавлений (is_pending)."""
    items: list[dict[str, Any]] = st.session_state.get(V2_DRAFT_ITEMS_KEY) or []
    month_filter = str(month_key or "").strip().lower()
    result: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for draft in items:
        if draft.get("is_pending") is not True:
            continue
        key = _v2_boq_draft_key_parts(
            str(draft.get("project_code") or ""),
            str(draft.get("facility") or ""),
            str(draft.get("discipline") or ""),
            str(draft.get("boq_code") or ""),
            str(draft.get("month_key") or ""),
        )
        if month_filter and key[4] != month_filter:
            continue
        added_at = str(draft.get("added_at") or "").strip()
        draft_month = str(draft.get("month_key") or "").strip()
        if key not in result:
            result[key] = {"planned_month": draft_month, "planned_at": added_at}
            continue
        existing_at = result[key].get("planned_at") or ""
        if added_at and (not existing_at or added_at > existing_at):
            result[key]["planned_at"] = added_at
        if draft_month:
            result[key]["planned_month"] = draft_month
    return result


def _v2_resolve_available_status(
    remaining_qty: float,
    available_qty: float,
    session_planned_qty: float,
) -> str:
    if remaining_qty <= 0:
        return "Выполнено"
    if available_qty < 0:
        return "Перепланировано"
    if available_qty <= 0 and session_planned_qty > 0:
        return "Запланировано полностью"
    if session_planned_qty > 0:
        return "Частично запланировано"
    return "Доступно"


def apply_v2_session_draft_reservation(df: pd.DataFrame, month_key: str) -> pd.DataFrame:
    """Уменьшить available_to_add_qty только для несохранённых добавлений в session."""
    if df.empty or not str(month_key or "").strip():
        return df
    planned_map = build_v2_session_planned_qty_map(month_key)
    meta_map = build_v2_session_planned_meta_map(month_key)
    out = df.copy()
    session_planned: list[float] = []
    planned_months: list[str] = []
    planned_ats: list[str] = []
    for _, row in out.iterrows():
        key = _v2_boq_draft_key_from_row(row, month_key)
        session_qty = planned_map.get(key, 0.0)
        session_planned.append(session_qty)
        if session_qty > 0:
            meta = meta_map.get(key, {})
            planned_months.append(str(meta.get("planned_month") or month_key).strip())
            planned_ats.append(format_v2_added_at_moscow(meta.get("planned_at")))
        else:
            planned_months.append("")
            planned_ats.append("")
    out["already_planned_qty"] = session_planned
    out["planned_month"] = planned_months
    out["planned_at"] = planned_ats
    out = _v2_apply_boq_availability_metrics(out)
    out["status"] = out.apply(_v2_resolve_scope_status_row, axis=1)
    return out


@st.cache_data(ttl=300, show_spinner=False)
def _cached_load_v2_crew_codes(limit: int = 5000) -> tuple[tuple[str, ...], str | None]:
    """Production v1: monthly_labor_summary.crew_code only (read-only)."""
    try:
        from services.supabase_client import supabase

        response = (
            supabase.table("monthly_labor_summary")
            .select("crew_code")
            .limit(limit)
            .execute()
        )
        df = pd.DataFrame(response.data or [])
        if df.empty:
            return tuple(), "monthly_labor_summary: пустой ответ"
        if "crew_code" not in df.columns:
            return tuple(), "monthly_labor_summary: колонка crew_code не найдена"
        vals = df["crew_code"].dropna().astype(str).str.strip()
        crews = sorted(vals[vals != ""].unique().tolist())
        if not crews:
            return tuple(), "monthly_labor_summary: crew_code пустой у всех строк"
        return tuple(crews), None
    except Exception as exc:  # noqa: BLE001
        return tuple(), f"{type(exc).__name__}: {exc}"


@st.cache_data(ttl=300, show_spinner=False)
def _cached_load_v2_crew_size_map(limit: int = 5000) -> dict[str, int]:
    """crew_size в monthly_labor_summary отсутствует — только ручной ввод в UI."""
    return {}


def load_v2_crew_options() -> list[str]:
    crews, load_error = _cached_load_v2_crew_codes()
    if load_error:
        st.session_state["v2_crew_load_error"] = load_error
        st.session_state["v2_crew_loaded_from_supabase"] = False
        st.session_state["v2_crew_supabase_count"] = 0
        return list(V2_CREW_FALLBACK_OPTIONS)

    st.session_state.pop("v2_crew_load_error", None)
    if crews:
        st.session_state["v2_crew_loaded_from_supabase"] = True
        st.session_state["v2_crew_supabase_count"] = len(crews)
        return ["Звено не выбрано", *crews]

    st.session_state["v2_crew_load_error"] = "monthly_labor_summary: нет данных crew_code"
    st.session_state["v2_crew_loaded_from_supabase"] = False
    st.session_state["v2_crew_supabase_count"] = 0
    return list(V2_CREW_FALLBACK_OPTIONS)


def _v2_render_crew_load_caption() -> None:
    err = st.session_state.get("v2_crew_load_error")
    if err:
        st.caption(f"Ошибка загрузки звеньев: {err}")
    elif st.session_state.get("v2_crew_loaded_from_supabase"):
        count = int(st.session_state.get("v2_crew_supabase_count") or 0)
        st.caption(f"Звенья загружены из monthly_labor_summary: {count}")
    else:
        st.caption("Используется резервный список звеньев")


def load_v2_crew_size_map() -> dict[str, int]:
    return _cached_load_v2_crew_size_map()


def _v2_resolve_crew_size(crew_code: str, size_map: dict[str, int]) -> int:
    size = size_map.get(str(crew_code or "").strip())
    if size is None or size < 1:
        return 1
    return int(size)


def _v2_norm_has_no_history(item: pd.Series) -> bool:
    raw_status = str(item.get("norm_status") or "").strip().upper()
    if raw_status == "НЕТ ИСТОРИИ":
        return True
    return str(item.get("productivity_history") or "").strip() == "Нет"


def v2_norm_scenario_hours(
    item: pd.Series,
    scenario: str,
    manual_norm: float = 0.0,
) -> float | None:
    if _v2_norm_has_no_history(item) and scenario != NORM_SCENARIO_MANUAL:
        return None
    if scenario == NORM_SCENARIO_REALISTIC:
        return _v2_parse_norm_hours_value(item.get("p50_hours_per_unit"))
    if scenario == NORM_SCENARIO_CAUTIOUS:
        return _v2_parse_norm_hours_value(item.get("p80_hours_per_unit"))
    if scenario == NORM_SCENARIO_MANUAL and manual_norm > 0:
        return manual_norm
    return None


def v2_compute_plan_add_preview(
    item: pd.Series,
    plan_qty: float,
    norm_scenario: str,
    manual_norm: float,
    crew_size: float = 1.0,
) -> dict[str, Any]:
    unit_price = _v2_safe_num(item.get("unit_price"))
    plan_value = plan_qty * unit_price if plan_qty > 0 else 0.0
    norm_hours = v2_norm_scenario_hours(item, norm_scenario, manual_norm)
    required_hours = plan_qty * norm_hours if norm_hours is not None and plan_qty > 0 else 0.0
    safe_crew_size = max(int(_v2_safe_num(crew_size, default=1.0)), 1)
    productive_hours_per_person_shift = PRODUCTIVE_HOURS_PER_PERSON_SHIFT
    crew_day_capacity_hours = safe_crew_size * productive_hours_per_person_shift
    duration_shifts = (
        required_hours / crew_day_capacity_hours if required_hours > 0 else 0.0
    )
    labor_cost = required_hours * DEFAULT_LABOR_RATE_PER_HOUR
    needs_manual_norm = (
        _v2_norm_has_no_history(item) and norm_scenario != NORM_SCENARIO_MANUAL
    ) or (
        norm_scenario != NORM_SCENARIO_MANUAL and norm_hours is None and plan_qty > 0
    )
    capacity_int = int(crew_day_capacity_hours)
    capacity_display = (
        f"{capacity_int} чел-ч/смена"
        if crew_day_capacity_hours == capacity_int
        else f"{_v2_format_qty_display_str(crew_day_capacity_hours)} чел-ч/смена"
    )
    return {
        "unit_price": unit_price,
        "plan_value": plan_value,
        "norm_hours_per_unit": norm_hours,
        "required_hours": required_hours,
        "crew_size": safe_crew_size,
        "productive_hours_per_person_shift": productive_hours_per_person_shift,
        "crew_day_capacity_hours": crew_day_capacity_hours,
        "duration_shifts": duration_shifts,
        "labor_cost": labor_cost,
        "needs_manual_norm": needs_manual_norm,
        "plan_value_display": _format_rub(plan_value) if plan_value > 0 else "—",
        "norm_hours_display": (
            _v2_format_qty_display_str(norm_hours) if norm_hours is not None else "—"
        ),
        "required_hours_display": (
            f"{_v2_format_qty_display_str(required_hours)} чел-ч"
            if required_hours > 0
            else "—"
        ),
        "crew_size_display": str(safe_crew_size),
        "crew_capacity_display": capacity_display if required_hours > 0 else "—",
        "duration_display": (
            f"{_v2_format_qty_display_str(duration_shifts)} смены"
            if duration_shifts > 0
            else "—"
        ),
        "duration_hint": (
            f"{safe_crew_size} × 8 = {capacity_int} чел-ч/смена"
            if required_hours > 0
            else ""
        ),
        "labor_cost_display": _format_rub(labor_cost) if labor_cost > 0 else "—",
    }


def _v2_format_norm_hours_chip(value: Any) -> str:
    parsed = _v2_parse_norm_hours_value(value)
    if parsed is None:
        return "—"
    return f"{_v2_format_qty_display_str(parsed)} ч/ед"


def _v2_norm_history_label(item: pd.Series) -> str:
    return "Есть история" if not _v2_norm_has_no_history(item) else "Нет истории"


def _v2_render_plan_add_context_html(
    item: pd.Series,
    planning_month: str,
    available_qty: float,
) -> str:
    unit = str(item.get("unit") or "—")
    unit_price = _v2_safe_num(item.get("unit_price"))
    price_display = _format_rub(unit_price) if unit_price > 0 else "—"
    facility = str(item.get("facility") or "—").strip() or "—"
    discipline = str(item.get("discipline") or "—").strip() or "—"
    norm_label = _v2_norm_history_label(item)
    chips = [
        ("Месяц", planning_month, ""),
        ("Код", str(item.get("boq_code") or "—"), ""),
        ("Ед.", unit, ""),
        ("Доступно", _v2_format_qty_display_str(available_qty), " highlight"),
        ("Цена/ед.", price_display, ""),
        ("Титул", facility, ""),
        ("Дисциплина", discipline, ""),
        ("Норма", norm_label, ""),
    ]
    cells = "".join(
        f'<span class="chip{css}"><label>{label}</label><strong>{value}</strong></span>'
        for label, value, css in chips
    )
    return f'<div class="v2-plan-add-context">{cells}</div>'


def _v2_render_norm_scenario_hint_html() -> str:
    return (
        '<p class="v2-plan-add-norm-hint">'
        "Реалистичная норма = P50 · Осторожная норма = P80 · Ручная норма = ввод вручную"
        "</p>"
    )


def _v2_render_norm_history_strip_html(item: pd.Series) -> str:
    if _v2_norm_has_no_history(item):
        return (
            '<div class="v2-plan-add-norm-strip missing">'
            "<span><label>История нормы</label><strong>Нет</strong></span>"
            '<span class="sep">|</span>'
            "<span>Укажите ручную норму.</span>"
            "</div>"
        )
    parts = [
        ("История нормы", "Есть"),
        ("P50", _v2_format_norm_hours_chip(item.get("p50_hours_per_unit"))),
        ("P80", _v2_format_norm_hours_chip(item.get("p80_hours_per_unit"))),
        ("Средняя", _v2_format_norm_hours_chip(item.get("weighted_avg_hours_per_unit"))),
    ]
    cells = "".join(
        f"<span><label>{label}</label><strong>{value}</strong></span>"
        + ('<span class="sep">|</span>' if idx < len(parts) - 1 else "")
        for idx, (label, value) in enumerate(parts)
    )
    return f'<div class="v2-plan-add-norm-strip">{cells}</div>'


def _v2_render_plan_add_preview_html(preview: dict[str, Any]) -> str:
    metrics = [
        ("Стоимость", preview["plan_value_display"]),
        ("Норма, ч/ед", preview["norm_hours_display"]),
        ("Трудозатраты", preview["required_hours_display"]),
        ("Людей в звене", preview["crew_size_display"]),
        ("Производительность звена", preview["crew_capacity_display"]),
        ("Длительность", preview["duration_display"]),
        ("Стоимость труда", preview["labor_cost_display"]),
    ]
    cells = "".join(
        f"<span><label>{label}</label><strong>{value}</strong></span>"
        + ('<span class="sep">|</span>' if idx < len(metrics) - 1 else "")
        for idx, (label, value) in enumerate(metrics)
    )
    hint = str(preview.get("duration_hint") or "").strip()
    hint_html = (
        f'<p class="v2-plan-add-duration-hint">{hint}</p>' if hint else ""
    )
    return f'<div class="v2-plan-add-preview">{cells}</div>{hint_html}'


def _v2_crew_is_valid(crew: str) -> bool:
    text = str(crew or "").strip()
    return text not in V2_INVALID_CREW_LABELS


def append_v2_month_plan_draft_item(
    item: pd.Series,
    planning_month: str,
    plan_qty: float,
    crew_code: str,
    norm_scenario: str,
    manual_norm: float,
    comment: str,
    preview: dict[str, Any],
    planned_by: str,
) -> dict[str, Any]:
    planned_at = datetime.now(timezone.utc).isoformat()
    draft_item: dict[str, Any] = {
        "plan_line_id": None,
        "status": V2_PLAN_STATUS_NOT_SENT,
        "is_pending": True,
        "line_uid": str(uuid4()),
        "project_code": str(item.get("project_code") or "").strip(),
        "construction_queue": _v2_plan_item_queue_from_scope_row(item),
        "facility": str(item.get("facility") or "").strip(),
        "discipline": str(item.get("discipline") or "").strip(),
        "system": str(item.get("system") or "").strip(),
        "iwp": str(item.get("iwp") or "").strip(),
        "boq_code": str(item.get("boq_code") or "").strip().upper(),
        "boq_name": str(item.get("boq_name") or "").strip(),
        "unit": str(item.get("unit") or "").strip(),
        "month_key": planning_month,
        "crew_code": crew_code,
        "crew_size": preview["crew_size"],
        "planned_qty": plan_qty,
        "unit_price": preview["unit_price"],
        "plan_value": preview["plan_value"],
        "norm_scenario": norm_scenario,
        "manual_norm_value": manual_norm if norm_scenario == NORM_SCENARIO_MANUAL else None,
        "norm_hours_per_unit": preview["norm_hours_per_unit"],
        "required_hours": preview["required_hours"],
        "productive_hours_per_person_shift": preview["productive_hours_per_person_shift"],
        "crew_day_capacity_hours": preview["crew_day_capacity_hours"],
        "duration_shifts": preview["duration_shifts"],
        "labor_rate_per_hour": DEFAULT_LABOR_RATE_PER_HOUR,
        "labor_cost": preview["labor_cost"],
        "comment": comment.strip(),
        "planned_by": str(planned_by or "").strip(),
        "planned_at": planned_at,
        "added_at": planned_at,
        "line_source_ui": "Новый код",
        "read_only": False,
    }
    items: list[dict[str, Any]] = list(st.session_state.get(V2_DRAFT_ITEMS_KEY) or [])
    items.append(draft_item)
    st.session_state[V2_DRAFT_ITEMS_KEY] = items
    st.session_state[V2_PLAN_DIRTY_KEY] = True
    _v2_autosave_draft_scope(
        str(draft_item.get("project_code") or "").strip(),
        str(draft_item.get("month_key") or "").strip(),
    )
    return draft_item


def load_v2_session_draft_items() -> list[dict[str, Any]]:
    return list(st.session_state.get(V2_DRAFT_ITEMS_KEY) or [])


def clear_v2_session_draft_items() -> None:
    st.session_state[V2_DRAFT_ITEMS_KEY] = []
    st.session_state[V2_PLAN_DIRTY_KEY] = False


def _v2_plan_scope_key(project_code: str, month_key: str) -> str:
    return f"{project_code.strip().upper()}|{month_key.strip().lower()}"


def _v2_plan_status_display(status: Any) -> str:
    code = str(status or V2_PLAN_STATUS_NOT_SENT).strip()
    return V2_PLAN_STATUS_UI.get(code, code or "—")


def _v2_plan_item_queue_from_scope_row(row: Any) -> str:
    """Очередь из scope row (monthly_scope_picker_view) или по титулу."""
    if isinstance(row, dict):
        queue = str(row.get("construction_queue") or "").strip()
        facility = str(row.get("facility") or "").strip()
    else:
        queue = str(row.get("construction_queue") or "").strip()
        facility = str(row.get("facility") or "").strip()
    if queue:
        return queue
    return derive_construction_queue_from_facility(facility)


def _v2_plan_item_queue(item: dict[str, Any]) -> str:
    """Очередь для строки месячного плана (session / DB)."""
    return _v2_plan_item_queue_from_scope_row(item)


# --- Monthly plan v2 persistence (monthly_plan_lines_v2) ---


@st.cache_data(ttl=300, show_spinner=False)
def _cached_v2_plan_lines_support_planner_columns() -> bool:
    """Проверка наличия planned_by / planned_at в monthly_plan_lines_v2."""
    try:
        supabase.table(V2_PLAN_LINES_TABLE).select("planned_by,planned_at").limit(0).execute()
        return True
    except Exception:  # noqa: BLE001
        return False


def _v2_strip_planner_fields_from_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    out.pop("planned_by", None)
    out.pop("planned_at", None)
    return out


def _v2_plan_db_payload_from_item(item: dict[str, Any]) -> dict[str, Any]:
    payload = map_v2_session_item_to_plan_db_row(item)
    if _cached_v2_plan_lines_support_planner_columns():
        return payload
    return _v2_strip_planner_fields_from_plan_payload(payload)


def load_v2_month_plan_lines(project_code: str, month_key: str) -> list[dict[str, Any]]:
    """Загрузить строки единого месячного плана из Supabase."""
    project_code = str(project_code or "").strip()
    month_key = str(month_key or "").strip()
    if not project_code or not month_key:
        return []

    def _run(client: Client) -> list[dict[str, Any]]:
        resp = (
            client.table(V2_PLAN_LINES_TABLE)
            .select("*")
            .eq("project_code", project_code)
            .eq("month_key", month_key)
            .order("created_at", desc=False)
            .limit(10000)
            .execute()
        )
        return list(resp.data or [])

    try:
        rows = _run(supabase)
    except Exception:  # noqa: BLE001
        rows = []

    if rows:
        return [map_v2_plan_db_row_to_session_item(row) for row in rows]

    write_client = get_v2_supabase_write_client()
    if write_client is None:
        return []
    try:
        return [map_v2_plan_db_row_to_session_item(row) for row in _run(write_client)]
    except Exception:  # noqa: BLE001
        return []


def map_v2_plan_db_row_to_session_item(row: dict[str, Any]) -> dict[str, Any]:
    """Строка monthly_plan_lines_v2 → session item."""
    plan_line_id = str(row.get("plan_line_id") or "").strip()
    planned_qty = _v2_safe_num(row.get("planned_qty"))
    labor_hours = _v2_safe_num(row.get("labor_hours"))
    crew_size_raw = row.get("crew_size")
    crew_size = (
        float(crew_size_raw)
        if crew_size_raw is not None and str(crew_size_raw).strip()
        else 1.0
    )
    status = str(row.get("status") or V2_PLAN_STATUS_NOT_SENT).strip()
    crew_day_capacity = crew_size * PRODUCTIVE_HOURS_PER_PERSON_SHIFT
    duration_shifts = labor_hours / crew_day_capacity if crew_day_capacity > 0 else 0.0
    norm_hpu = labor_hours / planned_qty if planned_qty > 0 else 0.0
    planned_at = str(row.get("planned_at") or row.get("created_at") or row.get("updated_at") or "").strip()
    if not planned_at:
        planned_at = datetime.now(timezone.utc).isoformat()
    planned_by = str(row.get("planned_by") or "").strip()
    return {
        "plan_line_id": plan_line_id or None,
        "status": status,
        "is_pending": False,
        "line_uid": plan_line_id or str(uuid4()),
        "project_code": str(row.get("project_code") or "").strip(),
        "facility": str(row.get("facility") or "").strip(),
        "discipline": str(row.get("discipline") or "").strip(),
        "construction_queue": derive_construction_queue_from_facility(
            str(row.get("facility") or "")
        ),
        "system": str(row.get("system") or "").strip(),
        "iwp": str(row.get("iwp") or "").strip(),
        "boq_code": str(row.get("boq_code") or "").strip().upper(),
        "boq_name": str(row.get("boq_name") or "").strip(),
        "unit": str(row.get("unit") or "").strip(),
        "month_key": str(row.get("month_key") or "").strip(),
        "crew_code": str(row.get("crew") or "").strip(),
        "crew_size": crew_size,
        "planned_qty": planned_qty,
        "unit_price": _v2_safe_num(row.get("unit_price")),
        "plan_value": _v2_safe_num(row.get("plan_value")),
        "norm_scenario": NORM_SCENARIO_REALISTIC,
        "manual_norm_value": None,
        "norm_hours_per_unit": norm_hpu,
        "required_hours": labor_hours,
        "productive_hours_per_person_shift": PRODUCTIVE_HOURS_PER_PERSON_SHIFT,
        "crew_day_capacity_hours": crew_day_capacity,
        "duration_shifts": duration_shifts,
        "labor_rate_per_hour": DEFAULT_LABOR_RATE_PER_HOUR,
        "labor_cost": _v2_safe_num(row.get("labor_cost")),
        "comment": "",
        "planned_by": planned_by,
        "planned_at": planned_at,
        "added_at": planned_at,
        "line_source_ui": "Месячный план",
        "read_only": status == V2_PLAN_STATUS_SENT,
        "sent_to_constraints_at": row.get("sent_to_constraints_at"),
    }


def map_v2_session_item_to_plan_db_row(item: dict[str, Any]) -> dict[str, Any]:
    """Session item → payload для insert/update monthly_plan_lines_v2."""
    planned_qty = _v2_safe_num(item.get("planned_qty"))
    required_hours = _v2_safe_num(item.get("required_hours"))
    unit_price = _v2_safe_num(item.get("unit_price"))
    labor_cost = _v2_safe_num(item.get("labor_cost"))
    plan_value = _v2_safe_num(item.get("plan_value"))
    if plan_value <= 0 and planned_qty > 0 and unit_price > 0:
        plan_value = planned_qty * unit_price
    if labor_cost <= 0 and required_hours > 0:
        labor_cost = required_hours * _v2_safe_num(
            item.get("labor_rate_per_hour"), default=DEFAULT_LABOR_RATE_PER_HOUR
        )
    crew_size = int(_v2_safe_num(item.get("crew_size"), default=1.0))
    system = str(item.get("system") or "").strip()
    iwp = str(item.get("iwp") or "").strip()
    payload: dict[str, Any] = {
        "project_code": item.get("project_code"),
        "month_key": item.get("month_key"),
        "facility": item.get("facility"),
        "discipline": item.get("discipline"),
        "system": system or None,
        "iwp": iwp or None,
        "boq_code": item.get("boq_code"),
        "boq_name": item.get("boq_name"),
        "unit": item.get("unit"),
        "planned_qty": planned_qty,
        "crew": item.get("crew_code"),
        "crew_size": crew_size,
        "labor_hours": required_hours,
        "labor_cost": labor_cost,
        "unit_price": unit_price if unit_price > 0 else None,
        "plan_value": plan_value if plan_value > 0 else None,
        "status": str(item.get("status") or V2_PLAN_STATUS_NOT_SENT),
    }
    planned_by = str(item.get("planned_by") or "").strip()
    planned_at = str(item.get("planned_at") or item.get("added_at") or "").strip()
    if planned_by:
        payload["planned_by"] = planned_by
    if planned_at:
        payload["planned_at"] = planned_at
    return payload


def save_v2_month_plan(
    project_code: str,
    month_key: str,
    items: list[dict[str, Any]],
) -> dict[str, int]:
    """Upsert несохранённых строк session в monthly_plan_lines_v2."""
    write_client = get_v2_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — сохранение плана недоступно.")

    scope_items = _v2_filter_items_for_scope(items, project_code, month_key)
    to_save = [
        item
        for item in scope_items
        if item.get("is_pending")
        or not str(item.get("plan_line_id") or "").strip()
    ]
    validation_errors = validate_v2_draft_for_save(to_save)
    if validation_errors:
        raise ValueError("\n".join(validation_errors))
    if not to_save:
        raise ValueError("Нет несохранённых строк для сохранения.")

    inserted = 0
    updated = 0
    for item in to_save:
        status = str(item.get("status") or V2_PLAN_STATUS_NOT_SENT)
        if status == V2_PLAN_STATUS_SENT:
            continue

        payload = _v2_plan_db_payload_from_item(item)
        plan_line_id = str(item.get("plan_line_id") or "").strip()

        if plan_line_id:
            write_client.table(V2_PLAN_LINES_TABLE).update(payload).eq(
                "plan_line_id", plan_line_id
            ).eq("status", V2_PLAN_STATUS_NOT_SENT).execute()
            updated += 1
        else:
            resp = write_client.table(V2_PLAN_LINES_TABLE).insert(payload).execute()
            if not resp.data:
                raise RuntimeError("Не удалось вставить строку monthly_plan_lines_v2.")
            inserted += 1

    hydrate_v2_month_plan_if_needed(project_code, month_key, force=True)
    _v2_finalize_draft_after_plan_save(project_code, month_key)
    return {"inserted": inserted, "updated": updated, "total": len(scope_items)}


def hydrate_v2_month_plan_if_needed(
    project_code: str,
    month_key: str,
    *,
    force: bool = False,
) -> None:
    """Подгрузить план из Supabase при смене project+month (без кнопки load draft)."""
    project_code = str(project_code or "").strip()
    month_key = str(month_key or "").strip()
    if not project_code or not month_key or project_code == "Все":
        return

    scope_key = _v2_plan_scope_key(project_code, month_key)
    if not force and st.session_state.get(V2_PLAN_SCOPE_KEY) == scope_key:
        return

    if st.session_state.get(V2_PLAN_SCOPE_KEY) != scope_key:
        st.session_state[V2_PLAN_SELECTED_KEYS] = []
        st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""

    items: list[dict[str, Any]] = list(st.session_state.get(V2_PLAN_ITEMS_KEY) or [])
    kept = [
        item
        for item in items
        if not _v2_item_matches_scope(item, project_code, month_key)
    ]
    pending_new = [
        item
        for item in items
        if _v2_item_matches_scope(item, project_code, month_key)
        and item.get("is_pending") is True
        and not str(item.get("plan_line_id") or "").strip()
    ]

    if force:
        loaded = load_v2_month_plan_lines(project_code, month_key)
        st.session_state[V2_PLAN_ITEMS_KEY] = kept + loaded
        st.session_state[V2_PLAN_SCOPE_KEY] = scope_key
        st.session_state[V2_PLAN_DIRTY_KEY] = False
        return

    loaded = load_v2_month_plan_lines(project_code, month_key)
    st.session_state[V2_PLAN_ITEMS_KEY] = kept + loaded + pending_new
    st.session_state[V2_PLAN_SCOPE_KEY] = scope_key
    st.session_state[V2_PLAN_DIRTY_KEY] = bool(pending_new)


# --- Save / load draft v2 (Supabase monthly_plan_drafts / monthly_plan_draft_lines) ---


@st.cache_resource
def get_v2_supabase_write_client() -> Client | None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "SOCKS_PROXY",
        "socks_proxy",
    ):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def _v2_resolve_draft_scope() -> tuple[str, str] | None:
    month_key = _v2_resolve_planning_month_key(
        str(st.session_state.get("v2_scope_planning_month") or "").strip()
    )
    project_code = str(st.session_state.get("v2_scope_project") or "").strip()
    if not month_key or not project_code or project_code == "Все":
        return None
    return project_code, month_key


def _v2_item_matches_scope(item: dict[str, Any], project_code: str, month_key: str) -> bool:
    return (
        str(item.get("project_code") or "").strip().upper()
        == project_code.strip().upper()
        and str(item.get("month_key") or "").strip().lower() == month_key.strip().lower()
    )


def _v2_saved_draft_select_fields() -> str:
    return (
        "draft_id,project_code,month_key,updated_at,rows_count,"
        "total_plan_value,total_required_hours,total_labor_cost,comment"
    )


def _v2_query_saved_draft_rows(
    month_key: str,
    project_code: str | None = None,
) -> list[dict[str, Any]]:
    """Read SAVED_DRAFT rows; fallback to service role if anon returns empty."""
    month_key = str(month_key or "").strip()
    if not month_key:
        return []

    def _run(client: Client) -> list[dict[str, Any]]:
        query = (
            client.table("monthly_plan_drafts")
            .select(_v2_saved_draft_select_fields())
            .eq("month_key", month_key)
            .eq("draft_status", V2_DRAFT_STATUS_SAVED)
            .order("updated_at", desc=True)
            .limit(1)
        )
        if project_code:
            query = query.eq("project_code", project_code)
        resp = query.execute()
        return list(resp.data or [])

    try:
        rows = _run(supabase)
    except Exception:  # noqa: BLE001
        rows = []

    if rows:
        return rows

    write_client = get_v2_supabase_write_client()
    if write_client is None:
        return []
    try:
        return _run(write_client)
    except Exception:  # noqa: BLE001
        return []


def _v2_row_to_saved_draft_meta(row: dict[str, Any]) -> dict[str, Any] | None:
    draft_id = str(row.get("draft_id") or "").strip()
    if not draft_id:
        return None
    return {
        "draft_id": draft_id,
        "project_code": str(row.get("project_code") or "").strip(),
        "month_key": str(row.get("month_key") or "").strip(),
        "updated_at": row.get("updated_at"),
        "rows_count": int(row.get("rows_count") or 0),
        "total_plan_value": _v2_safe_num(row.get("total_plan_value")),
        "total_required_hours": _v2_safe_num(row.get("total_required_hours")),
        "total_labor_cost": _v2_safe_num(row.get("total_labor_cost")),
    }


def resolve_v2_saved_draft_lookup() -> tuple[dict[str, Any], str, str] | None:
    """Найти SAVED_DRAFT для текущего месяца; project_code из фильтра или из header."""
    month_key = _v2_resolve_planning_month_key(
        str(st.session_state.get("v2_scope_planning_month") or "").strip()
    )
    if not month_key:
        return None

    project_filter = str(st.session_state.get("v2_scope_project") or "").strip()
    if project_filter and project_filter != "Все":
        rows = _v2_query_saved_draft_rows(month_key, project_filter)
        if rows:
            meta = _v2_row_to_saved_draft_meta(rows[0])
            if meta:
                project_code = str(meta.get("project_code") or project_filter).strip()
                return meta, project_code, month_key

    rows = _v2_query_saved_draft_rows(month_key, project_code=None)
    if not rows:
        return None
    meta = _v2_row_to_saved_draft_meta(rows[0])
    if not meta:
        return None
    project_code = str(meta.get("project_code") or "").strip()
    if not project_code:
        return None
    return meta, project_code, month_key


def _v2_filter_items_for_scope(
    items: list[dict[str, Any]],
    project_code: str,
    month_key: str,
) -> list[dict[str, Any]]:
    return [item for item in items if _v2_item_matches_scope(item, project_code, month_key)]


def _v2_count_session_items_for_scope(project_code: str, month_key: str) -> int:
    return len(_v2_filter_items_for_scope(load_v2_session_draft_items(), project_code, month_key))


def find_v2_saved_draft_id(project_code: str, month_key: str) -> str | None:
    rows = _v2_query_saved_draft_rows(month_key, project_code)
    if not rows:
        return None
    draft_id = str(rows[0].get("draft_id") or "").strip()
    return draft_id or None


def fetch_v2_saved_draft_meta(project_code: str, month_key: str) -> dict[str, Any] | None:
    rows = _v2_query_saved_draft_rows(month_key, project_code)
    if not rows:
        return None
    return _v2_row_to_saved_draft_meta(rows[0])


def validate_v2_draft_for_save(items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not items:
        errors.append("Нет строк для сохранения.")
        return errors
    for idx, item in enumerate(items, start=1):
        qty = _v2_safe_num(item.get("planned_qty"))
        crew = str(item.get("crew_code") or "").strip()
        scenario = str(item.get("norm_scenario") or "").strip()
        if qty <= 0:
            errors.append(f"Строка {idx}: объём должен быть больше нуля.")
        if not _v2_crew_is_valid(crew):
            errors.append(f"Строка {idx}: не указано звено.")
        if not scenario:
            errors.append(f"Строка {idx}: не указан сценарий нормы.")
    return errors


def build_v2_draft_header_payload(
    items: list[dict[str, Any]],
    project_code: str,
    month_key: str,
    *,
    for_create: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "project_code": project_code,
        "month_key": month_key,
        "draft_status": V2_DRAFT_STATUS_SAVED,
        "draft_name": f"Monthly plan v2 - {month_key}",
        "total_plan_value": sum(_v2_safe_num(item.get("plan_value")) for item in items),
        "total_required_hours": sum(_v2_safe_num(item.get("required_hours")) for item in items),
        "total_labor_cost": sum(_v2_safe_num(item.get("labor_cost")) for item in items),
        "rows_count": len(items),
        "comment": V2_DRAFT_SOURCE_MARKER,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if for_create:
        payload["created_by"] = "Streamlit v2"
    return payload


def _v2_map_session_item_to_db_line(draft_id: str, item: dict[str, Any]) -> dict[str, Any]:
    planned_qty = _v2_safe_num(item.get("planned_qty"))
    required_hours = _v2_safe_num(item.get("required_hours"))
    unit_price = _v2_safe_num(item.get("unit_price"))
    labor_rate = _v2_safe_num(item.get("labor_rate_per_hour"), default=DEFAULT_LABOR_RATE_PER_HOUR)
    norm_hpu = _v2_safe_num(item.get("norm_hours_per_unit"))
    if norm_hpu <= 0 and planned_qty > 0:
        norm_hpu = required_hours / planned_qty
    comment = str(item.get("comment") or "").strip()
    payload: dict[str, Any] = {
        "draft_id": draft_id,
        "project_code": item.get("project_code"),
        "month_key": item.get("month_key"),
        "facility_building": item.get("facility"),
        "construction_discipline": item.get("discipline"),
        "boq_code": item.get("boq_code"),
        "boq_name": item.get("boq_name"),
        "unit_of_measure": item.get("unit"),
        "crew_id": item.get("crew_code"),
        "planned_qty": planned_qty,
        "unit_price": unit_price,
        "plan_value": _v2_safe_num(item.get("plan_value")) or (planned_qty * unit_price),
        "norm_scenario": item.get("norm_scenario"),
        "selected_hours_per_unit": norm_hpu,
        "required_hours": required_hours,
        "labor_rate_per_hour": labor_rate,
        "labor_cost": _v2_safe_num(item.get("labor_cost")) or (required_hours * labor_rate),
        "line_status": "DRAFT",
        "comment": comment or None,
    }
    if _cached_v2_plan_lines_support_planner_columns():
        planned_by = str(item.get("planned_by") or "").strip()
        planned_at = str(item.get("planned_at") or item.get("added_at") or "").strip()
        if planned_by:
            payload["planned_by"] = planned_by
        if planned_at:
            payload["planned_at"] = planned_at
    return payload


def build_v2_draft_line_payloads(draft_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_v2_map_session_item_to_db_line(draft_id, item) for item in items]


def save_v2_draft_to_supabase(
    project_code: str,
    month_key: str,
    items: list[dict[str, Any]],
) -> str:
    write_client = get_v2_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — запись черновика недоступна.")

    scope_items = _v2_filter_items_for_scope(items, project_code, month_key)
    validation_errors = validate_v2_draft_for_save(scope_items)
    if validation_errors:
        raise ValueError("\n".join(validation_errors))
    if not scope_items:
        raise ValueError(
            "Нет строк для сохранения: проверьте, что project/month в фильтре "
            "совпадают с добавленными строками."
        )

    existing_id = str(st.session_state.get(V2_SAVED_DRAFT_ID_KEY) or "").strip()
    if not existing_id:
        existing_id = find_v2_saved_draft_id(project_code, month_key) or ""

    if existing_id:
        header_payload = build_v2_draft_header_payload(
            scope_items, project_code, month_key, for_create=False
        )
        write_client.table("monthly_plan_drafts").update(header_payload).eq(
            "draft_id", existing_id
        ).execute()
        write_client.table("monthly_plan_draft_lines").delete().eq("draft_id", existing_id).execute()
        line_payloads = build_v2_draft_line_payloads(existing_id, scope_items)
        if line_payloads:
            write_client.table("monthly_plan_draft_lines").insert(line_payloads).execute()
        draft_id = existing_id
    else:
        header_payload = build_v2_draft_header_payload(
            scope_items, project_code, month_key, for_create=True
        )
        header_resp = write_client.table("monthly_plan_drafts").insert(header_payload).execute()
        if not header_resp.data:
            raise RuntimeError("Не удалось создать запись monthly_plan_drafts.")
        draft_id = str(header_resp.data[0].get("draft_id") or "")
        if not draft_id:
            raise RuntimeError("Не удалось получить draft_id после сохранения monthly_plan_drafts.")
        line_payloads = build_v2_draft_line_payloads(draft_id, scope_items)
        if line_payloads:
            write_client.table("monthly_plan_draft_lines").insert(line_payloads).execute()

    st.session_state[V2_SAVED_DRAFT_ID_KEY] = draft_id
    return draft_id


def map_v2_db_line_to_session_item(line: dict[str, Any], header_updated_at: str) -> dict[str, Any]:
    norm_scenario = str(line.get("norm_scenario") or NORM_SCENARIO_REALISTIC)
    planned_qty = _v2_safe_num(line.get("planned_qty"))
    selected_hpu = _v2_safe_num(line.get("selected_hours_per_unit"))
    required_hours = _v2_safe_num(line.get("required_hours"))
    if required_hours <= 0 and planned_qty > 0 and selected_hpu > 0:
        required_hours = planned_qty * selected_hpu
    crew_size = 1.0
    crew_day_capacity = crew_size * PRODUCTIVE_HOURS_PER_PERSON_SHIFT
    duration_shifts = required_hours / crew_day_capacity if crew_day_capacity > 0 else 0.0
    manual_norm = selected_hpu if norm_scenario == NORM_SCENARIO_MANUAL else None
    planned_at = str(line.get("planned_at") or header_updated_at or "").strip()
    if not planned_at:
        planned_at = datetime.now(timezone.utc).isoformat()
    planned_by = str(line.get("planned_by") or "").strip()
    return {
        "line_uid": str(uuid4()),
        "project_code": str(line.get("project_code") or "").strip(),
        "facility": str(line.get("facility_building") or "").strip(),
        "discipline": str(line.get("construction_discipline") or "").strip(),
        "system": str(line.get("system") or "").strip(),
        "iwp": str(line.get("iwp") or "").strip(),
        "boq_code": str(line.get("boq_code") or "").strip().upper(),
        "boq_name": str(line.get("boq_name") or "").strip(),
        "unit": str(line.get("unit_of_measure") or "").strip(),
        "month_key": str(line.get("month_key") or "").strip(),
        "crew_code": str(line.get("crew_id") or "").strip(),
        "crew_size": crew_size,
        "planned_qty": planned_qty,
        "unit_price": _v2_safe_num(line.get("unit_price")),
        "plan_value": _v2_safe_num(line.get("plan_value")),
        "norm_scenario": norm_scenario,
        "manual_norm_value": manual_norm,
        "norm_hours_per_unit": selected_hpu,
        "required_hours": required_hours,
        "productive_hours_per_person_shift": PRODUCTIVE_HOURS_PER_PERSON_SHIFT,
        "crew_day_capacity_hours": crew_day_capacity,
        "duration_shifts": duration_shifts,
        "labor_rate_per_hour": _v2_safe_num(
            line.get("labor_rate_per_hour"), default=DEFAULT_LABOR_RATE_PER_HOUR
        ),
        "labor_cost": _v2_safe_num(line.get("labor_cost")),
        "comment": str(line.get("comment") or "").strip(),
        "planned_by": planned_by,
        "planned_at": planned_at,
        "added_at": planned_at,
        "line_source_ui": "Загружено из Supabase",
        "read_only": False,
    }


def _v2_query_draft_line_rows(draft_id: str) -> list[dict[str, Any]]:
    """Строки monthly_plan_draft_lines; fallback на service role как у header lookup."""
    draft_id = str(draft_id or "").strip()
    if not draft_id:
        return []

    def _run(client: Client) -> list[dict[str, Any]]:
        resp = (
            client.table("monthly_plan_draft_lines")
            .select("*")
            .eq("draft_id", draft_id)
            .limit(10000)
            .execute()
        )
        return list(resp.data or [])

    try:
        rows = _run(supabase)
    except Exception:  # noqa: BLE001
        rows = []

    if rows:
        return rows

    write_client = get_v2_supabase_write_client()
    if write_client is None:
        return []
    try:
        return _run(write_client)
    except Exception:  # noqa: BLE001
        return []


def load_v2_draft_lines_from_supabase(draft_id: str, header_updated_at: str) -> list[dict[str, Any]]:
    return [
        map_v2_db_line_to_session_item(row, header_updated_at)
        for row in _v2_query_draft_line_rows(draft_id)
    ]


def apply_v2_loaded_draft_to_session(
    loaded_items: list[dict[str, Any]],
    project_code: str,
    month_key: str,
    draft_id: str,
) -> None:
    kept = [
        item
        for item in load_v2_session_draft_items()
        if not _v2_item_matches_scope(item, project_code, month_key)
    ]
    existing_plan = load_v2_month_plan_lines(project_code, month_key)
    st.session_state[V2_DRAFT_ITEMS_KEY] = kept + existing_plan + loaded_items
    st.session_state[V2_SAVED_DRAFT_ID_KEY] = draft_id


def load_v2_saved_draft_into_session(
    meta: dict[str, Any],
    project_code: str,
    month_key: str,
) -> int:
    """Загрузить lines по draft_id из meta (без повторного lookup header)."""
    draft_id = str(meta.get("draft_id") or "").strip()
    if not draft_id:
        raise RuntimeError("В meta черновика отсутствует draft_id.")

    header_updated_at = str(meta.get("updated_at") or "")
    raw_rows = _v2_query_draft_line_rows(draft_id)
    loaded_items = _v2_prepare_restored_draft_items(
        load_v2_draft_lines_from_supabase(draft_id, header_updated_at)
    )

    apply_project = str(meta.get("project_code") or project_code).strip()
    apply_month = str(meta.get("month_key") or month_key).strip()
    apply_v2_loaded_draft_to_session(loaded_items, apply_project, apply_month, draft_id)

    session_count = len(load_v2_session_draft_items())
    st.session_state[V2_DRAFT_LOAD_DEBUG_KEY] = {
        "draft_id": draft_id,
        "project_code": project_code,
        "month_key": month_key,
        "header_rows_count": int(meta.get("rows_count") or 0),
        "lines_db": len(raw_rows),
        "mapped_items": len(loaded_items),
        "session_items": session_count,
    }

    if not loaded_items and int(meta.get("rows_count") or 0) > 0:
        raise RuntimeError(
            f"В header указано {meta['rows_count']} строк, но monthly_plan_draft_lines "
            f"пуст для draft_id={draft_id}."
        )
    if not loaded_items:
        raise RuntimeError("Строки черновика не найдены в monthly_plan_draft_lines.")

    return len(loaded_items)


def render_v2_saved_draft_banner(
    meta: dict[str, Any],
    project_code: str,
    month_key: str,
) -> None:
    updated_display = format_v2_added_at_moscow(meta.get("updated_at")) or "—"
    project_filter = str(st.session_state.get("v2_scope_project") or "").strip()
    filter_hint = ""
    if not project_filter or project_filter == "Все":
        filter_hint = (
            f"  \nВ фильтре Scope выбран «Все» — для резервирования выберите проект "
            f"`{project_code}`."
        )

    st.info(
        f"**Найден сохранённый черновик**  \n"
        f"Проект: `{project_code}` | Месяц: `{month_key}`  \n"
        f"Строк: **{meta['rows_count']}** | "
        f"Плановая стоимость: **{_format_rub(float(meta['total_plan_value']))}** | "
        f"Обновлён: **{updated_display}** (МСК)"
        f"{filter_hint}"
    )

    session_count = _v2_count_session_items_for_scope(project_code, month_key)
    if session_count > 0:
        st.warning(
            f"В текущей сессии уже есть **{session_count}** строк для этого проекта и месяца. "
            "Загрузка заменит их строками из Supabase."
        )

    if st.button("Загрузить сохранённый черновик", key="v2_load_saved_draft"):
        try:
            loaded_count = load_v2_saved_draft_into_session(meta, project_code, month_key)
            if loaded_count > 0:
                st.success(f"Загружено строк: {loaded_count}")
                st.rerun()
            else:
                st.error("Строки черновика не загружены в session.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Не удалось загрузить черновик: {exc}")


def compute_v2_month_plan_kpis(items: list[dict[str, Any]]) -> dict[str, float | int]:
    required_hours = sum(_v2_safe_num(item.get("required_hours")) for item in items)
    plan_value_rub = sum(_v2_safe_num(item.get("plan_value")) for item in items)
    labor_cost_rub = sum(_v2_safe_num(item.get("labor_cost")) for item in items)
    return {
        "total_lines": len(items),
        "new_lines": sum(1 for item in items if item.get("is_pending")),
        "plan_value_rub": plan_value_rub,
        "required_hours": required_hours,
        "labor_cost_rub": labor_cost_rub,
        "fte_required": (
            required_hours / V2_HOURS_PER_PERSON_MONTH
            if V2_HOURS_PER_PERSON_MONTH > 0
            else 0.0
        ),
        "labor_to_plan_pct": (
            labor_cost_rub / plan_value_rub * 100.0 if plan_value_rub > 0 else 0.0
        ),
        "risky_lines": sum(
            1 for item in items if _v2_plan_labor_cost_exceeds_plan_value(item)
        ),
    }


def _v2_plan_labor_cost_exceeds_plan_value(item: dict[str, Any]) -> bool:
    """Display-only: стоимость труда выше стоимости объёма работ."""
    labor_cost = _v2_safe_num(item.get("labor_cost"))
    plan_value = _v2_safe_num(item.get("plan_value"))
    return labor_cost > plan_value and labor_cost > 0


def _v2_format_labor_to_plan_pct_display(pct: float, plan_value_rub: float) -> str:
    if plan_value_rub <= 0:
        return "—"
    return f"{pct:.1f}".replace(".", ",") + " %"


def _v2_plan_registry_field_value(item: dict[str, Any], field: str) -> str:
    if field == "queue":
        return str(_v2_plan_item_queue(item) or "").strip()
    if field == "project":
        return str(item.get("project_code") or "").strip()
    if field == "title":
        return str(item.get("facility") or "").strip()
    if field == "discipline":
        return str(item.get("discipline") or "").strip()
    if field == "system":
        return str(item.get("system") or "").strip()
    if field == "iwp":
        return str(item.get("iwp") or "").strip()
    if field == "crew":
        return str(item.get("crew_code") or "").strip()
    if field == "boq":
        return str(item.get("boq_code") or "").strip()
    return ""


def _v2_plan_registry_filter_options(items: list[dict[str, Any]], field: str) -> list[str]:
    values = sorted(
        {
            text
            for item in items
            if (text := _v2_plan_registry_field_value(item, field)) and text != "—"
        }
    )
    return ["Все", *values] if values else ["Все"]


def _v2_default_plan_registry_filter_values() -> dict[str, str]:
    return {key: "Все" for key in V2_PLAN_REGISTRY_FILTER_KEYS}


def _v2_apply_plan_registry_filters(
    items: list[dict[str, Any]],
    filters: dict[str, str],
) -> list[dict[str, Any]]:
    filtered = items
    mapping = {
        "project": "project",
        "queue": "queue",
        "title": "title",
        "discipline": "discipline",
        "system": "system",
        "iwp": "iwp",
        "crew": "crew",
        "boq": "boq",
    }
    for filter_key, field in mapping.items():
        selected = str(filters.get(filter_key) or "Все").strip()
        if selected == "Все":
            continue
        filtered = [
            item
            for item in filtered
            if _v2_plan_registry_field_value(item, field) == selected
        ]
    return filtered


def render_v2_plan_registry_filters(items: list[dict[str, Any]]) -> dict[str, str]:
    """Локальные фильтры реестра строк месячного плана (только display/KPI slice)."""
    for key, value in _v2_default_plan_registry_filter_values().items():
        st.session_state.setdefault(key, value)

    project_options = _v2_plan_registry_filter_options(items, "project")
    queue_options = _v2_plan_registry_filter_options(items, "queue")
    title_options = _v2_plan_registry_filter_options(items, "title")
    discipline_options = _v2_plan_registry_filter_options(items, "discipline")
    system_options = _v2_plan_registry_filter_options(items, "system")
    iwp_options = _v2_plan_registry_filter_options(items, "iwp")
    crew_options = _v2_plan_registry_filter_options(items, "crew")
    boq_options = _v2_plan_registry_filter_options(items, "boq")

    _v2_sync_filter_option("v2_plan_reg_filter_project", project_options)
    _v2_sync_filter_option("v2_plan_reg_filter_queue", queue_options)
    _v2_sync_filter_option("v2_plan_reg_filter_title", title_options)
    _v2_sync_filter_option("v2_plan_reg_filter_discipline", discipline_options)
    _v2_sync_filter_option("v2_plan_reg_filter_system", system_options)
    _v2_sync_filter_option("v2_plan_reg_filter_iwp", iwp_options)
    _v2_sync_filter_option("v2_plan_reg_filter_crew", crew_options)
    _v2_sync_filter_option("v2_plan_reg_filter_boq", boq_options)

    st.markdown('<div class="v2-plan-registry-filters">', unsafe_allow_html=True)
    with st.container(border=True):
        row1 = st.columns(4)
        with row1[0]:
            st.selectbox("Проект", project_options, key="v2_plan_reg_filter_project")
        with row1[1]:
            st.selectbox("Очередь", queue_options, key="v2_plan_reg_filter_queue")
        with row1[2]:
            st.selectbox("Титул", title_options, key="v2_plan_reg_filter_title")
        with row1[3]:
            st.selectbox("Дисциплина", discipline_options, key="v2_plan_reg_filter_discipline")
        row2 = st.columns(4)
        with row2[0]:
            st.selectbox("Система", system_options, key="v2_plan_reg_filter_system")
        with row2[1]:
            st.selectbox("IWP", iwp_options, key="v2_plan_reg_filter_iwp")
        with row2[2]:
            st.selectbox("Звено", crew_options, key="v2_plan_reg_filter_crew")
        with row2[3]:
            st.selectbox("BOQ-код", boq_options, key="v2_plan_reg_filter_boq")
    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "project": st.session_state.get("v2_plan_reg_filter_project", "Все"),
        "queue": st.session_state.get("v2_plan_reg_filter_queue", "Все"),
        "title": st.session_state.get("v2_plan_reg_filter_title", "Все"),
        "discipline": st.session_state.get("v2_plan_reg_filter_discipline", "Все"),
        "system": st.session_state.get("v2_plan_reg_filter_system", "Все"),
        "iwp": st.session_state.get("v2_plan_reg_filter_iwp", "Все"),
        "crew": st.session_state.get("v2_plan_reg_filter_crew", "Все"),
        "boq": st.session_state.get("v2_plan_reg_filter_boq", "Все"),
    }


def _v2_format_staffing_need_display(fte: float) -> str:
    if fte <= 0:
        return "0 чел"
    return f"{fte:.1f}".replace(".", ",") + " чел"


def _v2_format_duration_shifts_display(value: Any) -> str:
    shifts = _v2_safe_num(value)
    if shifts <= 0:
        return "—"
    return f"{_v2_format_qty_display_str(shifts)} смены"


def _v2_plan_display_optional_text(value: Any) -> str:
    text = str(value or "").strip()
    return text or "—"


def _v2_plan_display_norm_hours_per_unit(item: dict[str, Any]) -> str:
    norm_hpu = _v2_safe_num(item.get("norm_hours_per_unit"))
    if norm_hpu <= 0:
        return "—"
    return _v2_format_qty_display_str(norm_hpu)


def _v2_plan_display_productivity(
    item: dict[str, Any],
    *,
    hours_multiplier: float,
    period_suffix: str,
) -> str:
    """Display-only: объём/чел·ч, объём/чел·смена или объём/звено·смена."""
    norm_hpu = _v2_safe_num(item.get("norm_hours_per_unit"))
    if norm_hpu <= 0:
        return "—"
    unit = str(item.get("unit") or "").strip() or "ед."
    value = hours_multiplier / norm_hpu
    return f"{_v2_format_qty_display_str(value)} {unit}/{period_suffix}"


def _v2_plan_display_productivity_per_person_hour(item: dict[str, Any]) -> str:
    return _v2_plan_display_productivity(item, hours_multiplier=1.0, period_suffix="ч")


def _v2_plan_display_productivity_per_person_shift(item: dict[str, Any]) -> str:
    return _v2_plan_display_productivity(
        item, hours_multiplier=PRODUCTIVE_HOURS_PER_PERSON_SHIFT, period_suffix="смена"
    )


def _v2_plan_display_productivity_crew_shift(item: dict[str, Any]) -> str:
    crew_size = max(int(_v2_safe_num(item.get("crew_size"), default=1.0)), 1)
    return _v2_plan_display_productivity(
        item,
        hours_multiplier=crew_size * PRODUCTIVE_HOURS_PER_PERSON_SHIFT,
        period_suffix="смена",
    )


def map_v2_session_draft_to_display_df(items: list[dict[str, Any]]) -> pd.DataFrame:
    """Session plan → таблица реестра строк месячного плана."""
    if not items:
        return pd.DataFrame(columns=V2_MONTH_PLAN_DISPLAY_COLUMNS)

    sorted_items = sorted(
        items,
        key=lambda item: str(item.get("added_at") or ""),
        reverse=True,
    )
    rows: list[dict[str, str]] = []
    for item in sorted_items:
        facility = str(item.get("facility") or "").strip() or "—"
        discipline = str(item.get("discipline") or "").strip() or "—"
        planned_at = item.get("planned_at") or item.get("added_at")
        rows.append(
            {
                "Статус": _v2_plan_status_display(item.get("status")),
                "Проект": str(item.get("project_code") or "—"),
                "Планировщик": _v2_plan_display_optional_text(item.get("planned_by")),
                "Дата планирования": _v2_format_planned_date_moscow(planned_at),
                "Время планирования МСК": _v2_format_planned_time_moscow(planned_at),
                "Очередь": _v2_plan_item_queue(item) or "—",
                "Титул": facility,
                "Дисциплина": discipline,
                "Система": _v2_plan_display_optional_text(item.get("system")),
                "IWP": _v2_plan_display_optional_text(item.get("iwp")),
                "BOQ код": str(item.get("boq_code") or "—"),
                "Наименование работ": str(item.get("boq_name") or "—"),
                "Объём": _v2_format_qty_display_str(item.get("planned_qty")),
                "Ед.": str(item.get("unit") or "—"),
                "Звено": str(item.get("crew_code") or "—"),
                "Людей": str(int(_v2_safe_num(item.get("crew_size"), default=1.0))),
                "Норма": str(item.get("norm_scenario") or "—"),
                "Норма ч/ед.": _v2_plan_display_norm_hours_per_unit(item),
                "Произв. 1 чел/ч": _v2_plan_display_productivity_per_person_hour(item),
                "Произв. 1 чел/смена": _v2_plan_display_productivity_per_person_shift(item),
                "Произв. звена/смена": _v2_plan_display_productivity_crew_shift(item),
                "Трудозатраты": (
                    f"{_v2_format_qty_display_str(item.get('required_hours'))} чел-ч"
                    if _v2_safe_num(item.get("required_hours")) > 0
                    else "—"
                ),
                "Длительность": _v2_format_duration_shifts_display(item.get("duration_shifts")),
                "Стоимость объёма": (
                    _format_rub(_v2_safe_num(item.get("plan_value")))
                    if _v2_safe_num(item.get("plan_value")) > 0
                    else "—"
                ),
                "Стоимость труда": (
                    _format_rub(_v2_safe_num(item.get("labor_cost")))
                    if _v2_safe_num(item.get("labor_cost")) > 0
                    else "—"
                ),
            }
        )
    return pd.DataFrame(rows, columns=V2_MONTH_PLAN_DISPLAY_COLUMNS)


def style_v2_month_plan_table(
    display_df: pd.DataFrame,
    *,
    labor_cost_warnings: list[bool] | None = None,
) -> Any:
    """Zebra rows, muted status badges, выравнивание чисел."""

    def _status_style(value: Any) -> str:
        return V2_PLAN_STATUS_STYLES.get(str(value), "")

    def _zebra_row_style(row: pd.Series) -> list[str]:
        bg = "#FAFBFC" if row.name % 2 == 1 else "#FFFFFF"
        return [f"background-color: {bg};"] * len(row)

    def _labor_cost_style(row: pd.Series) -> list[str]:
        idx = int(row.name)
        warnings = labor_cost_warnings or []
        if 0 <= idx < len(warnings) and warnings[idx]:
            return [V2_PLAN_LABOR_COST_WARNING_STYLE] * len(row)
        return [""] * len(row)

    styler = display_df.style.apply(_zebra_row_style, axis=1).map(
        _status_style, subset=["Статус"]
    )
    if "Стоимость труда" in display_df.columns:
        styler = styler.apply(_labor_cost_style, subset=["Стоимость труда"], axis=1)
    for col in V2_MONTH_PLAN_NUMERIC_COLUMNS:
        if col in display_df.columns:
            styler = styler.set_properties(subset=[col], **{"text-align": "right"})
    return styler


def _v2_plan_row_key(item: dict[str, Any]) -> str:
    plan_line_id = str(item.get("plan_line_id") or "").strip()
    if plan_line_id:
        return plan_line_id
    line_uid = str(item.get("line_uid") or "").strip()
    if line_uid:
        return line_uid
    return str(uuid4())


def _v2_plan_sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: str(item.get("added_at") or ""), reverse=True)


def _v2_find_plan_item_by_key(
    items: list[dict[str, Any]],
    row_key: str,
) -> dict[str, Any] | None:
    target = str(row_key or "").strip()
    if not target:
        return None
    for item in items:
        if _v2_plan_row_key(item) == target:
            return item
    return None


def _v2_replace_plan_item_in_session(row_key: str, updated_item: dict[str, Any]) -> None:
    target = str(row_key or "").strip()
    items = load_v2_session_draft_items()
    st.session_state[V2_PLAN_ITEMS_KEY] = [
        updated_item if _v2_plan_row_key(item) == target else item for item in items
    ]


def _v2_plan_selection_stats(
    scope_items: list[dict[str, Any]],
    selected_keys: list[str],
) -> dict[str, int]:
    key_set = {str(key).strip() for key in selected_keys if str(key).strip()}
    selected_count = 0
    sendable_count = 0
    editable_count = 0
    deletable_count = 0
    for item in scope_items:
        row_key = _v2_plan_row_key(item)
        if row_key not in key_set:
            continue
        selected_count += 1
        status = str(item.get("status") or V2_PLAN_STATUS_NOT_SENT)
        if status != V2_PLAN_STATUS_NOT_SENT:
            continue
        deletable_count += 1
        editable_count += 1
        if str(item.get("plan_line_id") or "").strip():
            sendable_count += 1
    sent_to_admission_count = sum(
        1
        for item in scope_items
        if str(item.get("status") or V2_PLAN_STATUS_NOT_SENT) == V2_PLAN_STATUS_SENT
    )
    return {
        "selected": selected_count,
        "sendable": sendable_count,
        "sent_to_admission": sent_to_admission_count,
        "editable": editable_count,
        "deletable": deletable_count,
    }


def apply_v2_plan_line_edit(
    item: dict[str, Any],
    *,
    planned_qty: float,
    crew_code: str,
    crew_size: float,
    norm_scenario: str,
    norm_hours_per_unit: float,
    comment: str,
) -> dict[str, Any]:
    """Пересчитать editable-поля строки плана и пометить как pending."""
    series = pd.Series(dict(item))
    manual_norm = norm_hours_per_unit if norm_scenario == NORM_SCENARIO_MANUAL else 0.0
    if norm_scenario == NORM_SCENARIO_REALISTIC and norm_hours_per_unit > 0:
        series["p50_hours_per_unit"] = norm_hours_per_unit
    if norm_scenario == NORM_SCENARIO_CAUTIOUS and norm_hours_per_unit > 0:
        series["p80_hours_per_unit"] = norm_hours_per_unit

    preview = v2_compute_plan_add_preview(
        series,
        float(planned_qty),
        norm_scenario,
        float(manual_norm),
        float(crew_size),
    )
    if preview.get("needs_manual_norm") and norm_hours_per_unit > 0:
        preview = v2_compute_plan_add_preview(
            series,
            float(planned_qty),
            NORM_SCENARIO_MANUAL,
            float(norm_hours_per_unit),
            float(crew_size),
        )
        norm_scenario = NORM_SCENARIO_MANUAL
        manual_norm = norm_hours_per_unit

    updated = dict(item)
    norm_hpu = preview.get("norm_hours_per_unit")
    if norm_hpu is None and norm_hours_per_unit > 0:
        norm_hpu = norm_hours_per_unit
    updated.update(
        {
            "planned_qty": float(planned_qty),
            "crew_code": str(crew_code).strip(),
            "crew_size": preview["crew_size"],
            "norm_scenario": norm_scenario,
            "manual_norm_value": manual_norm if norm_scenario == NORM_SCENARIO_MANUAL else None,
            "norm_hours_per_unit": _v2_safe_num(norm_hpu),
            "required_hours": preview["required_hours"],
            "productive_hours_per_person_shift": preview["productive_hours_per_person_shift"],
            "crew_day_capacity_hours": preview["crew_day_capacity_hours"],
            "duration_shifts": preview["duration_shifts"],
            "plan_value": preview["plan_value"],
            "labor_cost": preview["labor_cost"],
            "comment": str(comment or "").strip(),
            "is_pending": True,
            "read_only": False,
        }
    )
    return updated


def send_v2_plan_lines_to_admission(
    project_code: str,
    month_key: str,
    row_keys: list[str],
) -> dict[str, int]:
    """Отправка в допуск: constraints → monthly_plan_lines_v2 status.

    Для выбранных NOT_SENT строк с plan_line_id:
    1) create_constraints_for_plan_lines (line_id = plan_line_id),
    2) при успехе — status → SENT_TO_ADMISSION, sent_to_constraints_at → now().
    """
    write_client = get_v2_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — отправка недоступна.")

    key_set = {str(key).strip() for key in row_keys if str(key).strip()}
    if not key_set:
        raise ValueError("Не выбраны строки для отправки в допуск.")

    scope_items = _v2_filter_items_for_scope(
        load_v2_session_draft_items(), project_code, month_key
    )
    skipped = 0
    unsaved: list[str] = []
    to_send: list[dict[str, Any]] = []

    for item in scope_items:
        row_key = _v2_plan_row_key(item)
        if row_key not in key_set:
            continue
        status = str(item.get("status") or V2_PLAN_STATUS_NOT_SENT)
        if status == V2_PLAN_STATUS_SENT:
            skipped += 1
            continue
        plan_line_id = str(item.get("plan_line_id") or "").strip()
        if not plan_line_id:
            unsaved.append(str(item.get("boq_code") or row_key))
            continue
        to_send.append(item)

    if unsaved:
        raise ValueError(
            "Сначала сохраните несохранённые строки: "
            + ", ".join(unsaved[:5])
            + ("…" if len(unsaved) > 5 else "")
        )
    if not to_send:
        raise ValueError("Нет строк NOT_SENT для отправки в допуск.")

    constraint_result = create_constraints_for_plan_lines(to_send)
    if constraint_result["errors"]:
        raise RuntimeError(
            "Не удалось создать ограничения: "
            + "; ".join(constraint_result["errors"][:5])
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    sent = 0
    for item in to_send:
        plan_line_id = str(item.get("plan_line_id") or "").strip()
        write_client.table(V2_PLAN_LINES_TABLE).update(
            {
                "status": V2_PLAN_STATUS_SENT,
                "sent_to_constraints_at": now_iso,
            }
        ).eq("plan_line_id", plan_line_id).eq("status", V2_PLAN_STATUS_NOT_SENT).execute()
        sent += 1

    st.session_state[V2_PLAN_SELECTED_KEYS] = []
    st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""
    hydrate_v2_month_plan_if_needed(project_code, month_key, force=True)
    return {
        "sent": sent,
        "skipped": skipped,
        "constraints_created": constraint_result["created"],
        "constraints_skipped": constraint_result["skipped"],
    }


def delete_v2_plan_lines(
    project_code: str,
    month_key: str,
    row_keys: list[str],
) -> dict[str, int]:
    """Удалить выбранные NOT_SENT строки из session и DB."""
    write_client = get_v2_supabase_write_client()
    key_set = {str(key).strip() for key in row_keys if str(key).strip()}
    if not key_set:
        raise ValueError("Не выбраны строки для удаления.")

    deleted = 0
    skipped = 0
    kept_items: list[dict[str, Any]] = []

    for item in load_v2_session_draft_items():
        if not _v2_item_matches_scope(item, project_code, month_key):
            kept_items.append(item)
            continue
        row_key = _v2_plan_row_key(item)
        if row_key not in key_set:
            kept_items.append(item)
            continue
        status = str(item.get("status") or V2_PLAN_STATUS_NOT_SENT)
        if status == V2_PLAN_STATUS_SENT:
            kept_items.append(item)
            skipped += 1
            continue
        plan_line_id = str(item.get("plan_line_id") or "").strip()
        if plan_line_id:
            if write_client is None:
                raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — удаление недоступно.")
            write_client.table(V2_PLAN_LINES_TABLE).delete().eq(
                "plan_line_id", plan_line_id
            ).eq("status", V2_PLAN_STATUS_NOT_SENT).execute()
        deleted += 1

    st.session_state[V2_PLAN_ITEMS_KEY] = kept_items
    st.session_state[V2_PLAN_SELECTED_KEYS] = []
    st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""
    scope_items = _v2_filter_items_for_scope(kept_items, project_code, month_key)
    st.session_state[V2_PLAN_DIRTY_KEY] = any(item.get("is_pending") for item in scope_items)
    _v2_autosave_draft_scope(project_code, month_key)
    return {"deleted": deleted, "skipped": skipped}


def clear_v2_pending_plan_lines_for_scope(project_code: str, month_key: str) -> int:
    """Удалить только несохранённые pending строки текущего scope."""
    kept = [
        item
        for item in load_v2_session_draft_items()
        if not (
            _v2_item_matches_scope(item, project_code, month_key)
            and item.get("is_pending") is True
        )
    ]
    removed = len(load_v2_session_draft_items()) - len(kept)
    st.session_state[V2_PLAN_ITEMS_KEY] = kept
    st.session_state[V2_PLAN_DIRTY_KEY] = False
    st.session_state[V2_PLAN_SELECTED_KEYS] = []
    st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""
    _v2_autosave_draft_scope(project_code, month_key)
    return removed


def _v2_pending_draft_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Строки, которые можно писать в draft: только несохранённые pending."""
    return [item for item in items if item.get("is_pending") is True]


def _v2_scope_plan_row_counts(
    project_code: str,
    month_key: str,
) -> tuple[int, int]:
    """(pending_count, saved_not_in_draft_count) для текущего scope."""
    scope_items = _v2_filter_items_for_scope(
        load_v2_session_draft_items(), project_code, month_key
    )
    pending_count = sum(1 for item in scope_items if item.get("is_pending") is True)
    saved_count = sum(
        1
        for item in scope_items
        if item.get("is_pending") is not True
        and str(item.get("plan_line_id") or "").strip()
    )
    return pending_count, saved_count


def _v2_prepare_restored_draft_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pending-строки из draft → session (без plan_line_id, только NOT_SENT)."""
    prepared: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        row["is_pending"] = True
        row["plan_line_id"] = None
        row["status"] = V2_PLAN_STATUS_NOT_SENT
        row["read_only"] = False
        row["line_source_ui"] = "Черновик"
        prepared.append(row)
    return prepared


def _v2_resolve_scope_draft_id(project_code: str, month_key: str) -> str:
    draft_id = str(st.session_state.get(V2_SAVED_DRAFT_ID_KEY) or "").strip()
    if draft_id:
        return draft_id
    return find_v2_saved_draft_id(project_code, month_key) or ""


def _v2_autosave_draft_scope(project_code: str, month_key: str) -> None:
    """Autosave только pending-строк scope в monthly_plan_drafts / monthly_plan_draft_lines."""
    project_code = str(project_code or "").strip()
    month_key = str(month_key or "").strip()
    if not project_code or not month_key:
        return

    scope_items = _v2_filter_items_for_scope(load_v2_session_draft_items(), project_code, month_key)
    pending_items = _v2_pending_draft_items(scope_items)
    if not pending_items:
        try:
            _v2_clear_scope_draft_storage(project_code, month_key)
            record_autosave_not_needed()
        except Exception as exc:  # noqa: BLE001
            record_autosave_error(str(exc))
        return

    try:
        save_v2_draft_to_supabase(project_code, month_key, pending_items)
        record_autosave_success(len(pending_items))
    except Exception as exc:  # noqa: BLE001
        record_autosave_error(str(exc))


def _v2_clear_scope_draft_storage(project_code: str, month_key: str) -> None:
    write_client = get_v2_supabase_write_client()
    if write_client is None:
        raise RuntimeError("SUPABASE_SECRET_KEY не задан в .env — очистка черновика недоступна.")
    draft_id = _v2_resolve_scope_draft_id(project_code, month_key)
    if draft_id:
        delete_draft_from_supabase(write_client, draft_id)
    st.session_state.pop(V2_SAVED_DRAFT_ID_KEY, None)
    clear_autosave_status()


def _v2_finalize_draft_after_plan_save(project_code: str, month_key: str) -> None:
    write_client = get_v2_supabase_write_client()
    if write_client is None:
        clear_autosave_status()
        return
    draft_id = _v2_resolve_scope_draft_id(project_code, month_key)
    if draft_id:
        try:
            mark_draft_converted(write_client, draft_id)
        except Exception:  # noqa: BLE001
            pass
    st.session_state.pop(V2_SAVED_DRAFT_ID_KEY, None)
    clear_autosave_status()


def render_v2_draft_autosave_status_bar(project_code: str, month_key: str) -> None:
    """Компактный статус autosave-черновика для модуля месячного плана."""
    autosave = get_autosave_status()
    saved_draft = resolve_v2_saved_draft_lookup()
    draft_meta = saved_draft[0] if saved_draft else None

    error_text = str(autosave.get("error") or "").strip()
    saved_at = autosave.get("saved_at")
    not_needed = bool(autosave.get("not_needed"))
    pending_in_scope, saved_not_in_draft = _v2_scope_plan_row_counts(project_code, month_key)

    if error_text:
        status_label = "ошибка"
        status_kind = "error"
    elif not_needed or (pending_in_scope == 0 and not draft_meta):
        status_label = "не требуется: несохранённых строк нет"
        status_kind = "empty"
    elif saved_at:
        status_label = "автосохранён"
        status_kind = "ok"
    elif draft_meta:
        status_label = "найден, не восстановлен"
        status_kind = "found"
    else:
        status_label = "не найден"
        status_kind = "empty"

    draft_pending_count = autosave.get("row_count")
    if draft_pending_count is None and draft_meta:
        draft_pending_count = int(draft_meta.get("rows_count") or 0)
    if draft_pending_count is None:
        draft_pending_count = pending_in_scope

    saved_display = format_v2_added_at_moscow(saved_at) if saved_at else "—"
    if saved_display == "—" and draft_meta:
        saved_display = format_v2_added_at_moscow(draft_meta.get("updated_at")) or "—"

    legacy_draft_rows = int(draft_meta.get("rows_count") or 0) if draft_meta else 0
    if legacy_draft_rows > pending_in_scope and pending_in_scope == 0:
        st.warning(
            "Обнаружен черновик **старого формата** (до патча Фаза 1): в нём могут быть "
            f"**{legacy_draft_rows}** строк, включая уже сохранённые в план. "
            "Перед восстановлением нажмите **«Очистить черновик»** или удалите запись в Supabase — "
            "иначе при восстановлении возможны дубликаты."
        )

    st.markdown(
        f"""
        <div class="v2-draft-autosave-bar v2-draft-autosave-bar--{status_kind}">
            <span><strong>Черновик:</strong> {status_label}</span>
            <span><strong>Автосохранение:</strong> {saved_display} МСК</span>
            <span><strong>Несохранённых в черновике:</strong> {draft_pending_count}</span>
            <span><strong>Уже сохранённых (не в черновике):</strong> {saved_not_in_draft}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    btn_restore, btn_clear, _ = st.columns([1, 1, 2])
    with btn_restore:
        restore_disabled = saved_draft is None
        if st.button(
            "Восстановить черновик",
            key="v2_draft_autosave_restore_btn",
            disabled=restore_disabled,
        ):
            try:
                meta, restore_project, restore_month = saved_draft  # type: ignore[misc]
                loaded_count = load_v2_saved_draft_into_session(
                    meta, restore_project, restore_month
                )
                st.session_state[V2_PLAN_DIRTY_KEY] = True
                record_autosave_success(loaded_count)
                st.success(f"Восстановлено строк черновика: {loaded_count}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                record_autosave_error(str(exc))
                st.error(f"Не удалось восстановить черновик: {exc}")
    with btn_clear:
        clear_disabled = draft_meta is None and not str(saved_at or "").strip()
        if st.button(
            "Очистить черновик",
            key="v2_draft_autosave_clear_btn",
            disabled=clear_disabled,
        ):
            try:
                _v2_clear_scope_draft_storage(project_code, month_key)
                st.success("Черновик очищен.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                record_autosave_error(str(exc))
                st.error(f"Не удалось очистить черновик: {exc}")


def render_v2_plan_edit_panel(item: dict[str, Any]) -> None:
    """Форма редактирования одной NOT_SENT строки."""
    row_key = _v2_plan_row_key(item)
    st.markdown('<div class="v2-month-plan-edit-panel">', unsafe_allow_html=True)
    st.markdown("**Редактирование строки**")
    meta_col1, meta_col2, meta_col3 = st.columns(3)
    meta_col1.caption(f"Проект: {item.get('project_code') or '—'}")
    meta_col2.caption(f"Месяц: {item.get('month_key') or '—'}")
    meta_col3.caption(f"Статус: {_v2_plan_status_display(item.get('status'))}")
    st.caption(
        f"BOQ {item.get('boq_code') or '—'} · "
        f"{item.get('boq_name') or '—'} · "
        f"{item.get('facility') or '—'} / {item.get('discipline') or '—'}"
    )

    crew_options = load_v2_crew_options()
    current_crew = str(item.get("crew_code") or "Звено не выбрано").strip()
    crew_index = crew_options.index(current_crew) if current_crew in crew_options else 0
    current_scenario = str(item.get("norm_scenario") or NORM_SCENARIO_REALISTIC)
    scenario_index = (
        NORM_SCENARIO_OPTIONS.index(current_scenario)
        if current_scenario in NORM_SCENARIO_OPTIONS
        else 0
    )

    left, right = st.columns(2)
    with left:
        planned_qty = st.number_input(
            "Объём",
            min_value=0.0,
            value=float(_v2_safe_num(item.get("planned_qty"))),
            step=0.01,
            key=f"v2_plan_edit_qty_{row_key}",
        )
        crew_code = st.selectbox(
            "Звено",
            crew_options,
            index=crew_index,
            key=f"v2_plan_edit_crew_{row_key}",
        )
        crew_size = st.number_input(
            "Людей",
            min_value=1,
            step=1,
            value=int(_v2_safe_num(item.get("crew_size"), default=1.0)),
            key=f"v2_plan_edit_crew_size_{row_key}",
        )
    with right:
        norm_scenario = st.selectbox(
            "Норма",
            NORM_SCENARIO_OPTIONS,
            index=scenario_index,
            key=f"v2_plan_edit_norm_{row_key}",
        )
        norm_hours_per_unit = st.number_input(
            "Норма ч/ед.",
            min_value=0.0,
            value=float(_v2_safe_num(item.get("norm_hours_per_unit"))),
            step=0.01,
            key=f"v2_plan_edit_norm_hpu_{row_key}",
        )
        comment = st.text_input(
            "Комментарий",
            value=str(item.get("comment") or ""),
            key=f"v2_plan_edit_comment_{row_key}",
        )

    btn_apply, btn_cancel = st.columns(2)
    with btn_apply:
        if st.button("Применить изменения", key=f"v2_plan_edit_apply_{row_key}"):
            try:
                updated = apply_v2_plan_line_edit(
                    item,
                    planned_qty=float(planned_qty),
                    crew_code=str(crew_code),
                    crew_size=float(crew_size),
                    norm_scenario=str(norm_scenario),
                    norm_hours_per_unit=float(norm_hours_per_unit),
                    comment=str(comment),
                )
                _v2_replace_plan_item_in_session(row_key, updated)
                st.session_state[V2_PLAN_DIRTY_KEY] = True
                st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""
                _v2_autosave_draft_scope(
                    str(updated.get("project_code") or "").strip(),
                    str(updated.get("month_key") or "").strip(),
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Не удалось применить изменения: {exc}")
    with btn_cancel:
        if st.button("Отмена", key=f"v2_plan_edit_cancel_{row_key}"):
            st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


_V2_PLAN_METRIC_ICON_USERS = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="#4a78b5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
    '<circle cx="9" cy="7" r="4"/>'
    '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
    '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
    "</svg>"
)
_V2_PLAN_METRIC_ICON_SEND = (
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="#2f7a4a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="22" y1="2" x2="11" y2="13"/>'
    '<polygon points="22 2 15 22 11 13 2 9 22 2"/>'
    "</svg>"
)


def render_v2_plan_action_bar(
    project_code: str,
    month_key: str,
    scope_items: list[dict[str, Any]],
    selected_keys: list[str],
    *,
    bar_key_suffix: str = "main",
) -> None:
    """Компактная command panel — visual only."""
    stats = _v2_plan_selection_stats(scope_items, selected_keys)
    has_pending = any(item.get("is_pending") for item in scope_items)

    st.markdown('<div class="v2-month-plan-action-bar-anchor"></div>', unsafe_allow_html=True)
    metrics_col, actions_col = st.columns([0.42, 2.58], vertical_alignment="center")
    with metrics_col:
        st.markdown(
            '<div class="v2-plan-metrics-row">'
            f'<div class="v2-plan-metric-inline">'
            f'<span class="v2-plan-metric-label">Выбрано:</span>'
            f'<span class="v2-plan-metric-value">{stats["selected"]}</span>'
            f"</div>"
            f'<div class="v2-plan-metric-inline">'
            f'<span class="v2-plan-metric-label">К допуску:</span>'
            f'<span class="v2-plan-metric-value">{stats["sent_to_admission"]}</span>'
            f"</div>"
            "</div>",
            unsafe_allow_html=True,
        )
    with actions_col:
        btn1, btn2, btn3, btn4, btn5 = st.columns(5, gap="small")
        with btn1:
            st.markdown('<div class="v2-plan-btn-hook v2-plan-btn-hook-send"></div>', unsafe_allow_html=True)
            if st.button(
                "В ДОПУСК",
                icon=":material/send:",
                disabled=stats["sendable"] == 0,
                key=f"v2_plan_send_{bar_key_suffix}",
            ):
                try:
                    result = send_v2_plan_lines_to_admission(
                        project_code, month_key, selected_keys
                    )
                    st.success(
                        f"Отправлено в допуск: {result['sent']} строк. "
                        f"Создано проверок: {result['constraints_created']}. "
                        f"Пропущено дубликатов: {result['constraints_skipped']}. "
                        "Статус: «Отправлен в допуск»."
                    )
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Не удалось отправить в допуск: {exc}")
        with btn2:
            st.markdown('<div class="v2-plan-btn-hook v2-plan-btn-hook-save"></div>', unsafe_allow_html=True)
            if st.button(
                "Сохранить план",
                icon=":material/save:",
                disabled=not has_pending,
                key=f"v2_plan_save_{bar_key_suffix}",
            ):
                try:
                    result = save_v2_month_plan(
                        project_code, month_key, load_v2_session_draft_items()
                    )
                    st.success(
                        f"Месячный план сохранён: добавлено {result['inserted']}, "
                        f"обновлено {result['updated']}."
                    )
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Не удалось сохранить месячный план: {exc}")
        with btn3:
            st.markdown('<div class="v2-plan-btn-hook v2-plan-btn-hook-edit"></div>', unsafe_allow_html=True)
            if st.button(
                "Изменить строку",
                icon=":material/edit:",
                disabled=stats["editable"] != 1,
                key=f"v2_plan_edit_{bar_key_suffix}",
            ):
                editable_keys = [
                    _v2_plan_row_key(item)
                    for item in scope_items
                    if _v2_plan_row_key(item) in set(selected_keys)
                    and str(item.get("status") or V2_PLAN_STATUS_NOT_SENT)
                    == V2_PLAN_STATUS_NOT_SENT
                ]
                if len(editable_keys) == 1:
                    st.session_state[V2_PLAN_EDIT_ROW_KEY] = editable_keys[0]
                    st.rerun()
        with btn4:
            st.markdown('<div class="v2-plan-btn-hook v2-plan-btn-hook-delete"></div>', unsafe_allow_html=True)
            if st.button(
                "Удалить строки",
                icon=":material/delete:",
                disabled=stats["deletable"] == 0,
                key=f"v2_plan_delete_{bar_key_suffix}",
            ):
                try:
                    result = delete_v2_plan_lines(project_code, month_key, selected_keys)
                    st.success(f"Удалено строк: {result['deleted']}.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Не удалось удалить строки: {exc}")
        with btn5:
            st.markdown('<div class="v2-plan-btn-hook v2-plan-btn-hook-clear"></div>', unsafe_allow_html=True)
            if st.button(
                "Очистить несохранённые",
                icon=":material/ink_eraser:",
                disabled=not has_pending,
                key=f"v2_plan_clear_{bar_key_suffix}",
            ):
                clear_v2_pending_plan_lines_for_scope(project_code, month_key)
                st.rerun()


def _v2_adjustment_save_row(item: pd.Series) -> pd.Series:
    """Ключи v1 для save_adjustment (facility_building / construction_discipline)."""
    return pd.Series(
        {
            "project_code": str(item.get("project_code") or "").strip(),
            "facility_building": str(item.get("facility") or "").strip(),
            "construction_discipline": str(item.get("discipline") or "").strip(),
            "boq_code": str(item.get("boq_code") or "").strip().upper(),
        }
    )


def _v2_adjustment_keys_complete(item: pd.Series) -> bool:
    keys = _v2_adjustment_save_row(item)
    return all(str(keys[col]).strip() for col in keys.index)


@st.cache_data(ttl=120, show_spinner=False)
def _cached_fetch_v2_manual_adjustments_history(
    project_code: str,
    facility_building: str,
    construction_discipline: str,
    boq_code: str,
) -> pd.DataFrame:
    return fetch_adjustments_history_for_boq(
        project_code,
        facility_building,
        construction_discipline,
        boq_code,
    )


def load_v2_manual_adjustments_history(row: pd.Series) -> pd.DataFrame:
    """Журнал корректировок по выбранному BOQ из monthly_scope_manual_adjustments."""
    if not _v2_adjustment_keys_complete(row):
        return pd.DataFrame()
    keys = _v2_adjustment_save_row(row)
    return _cached_fetch_v2_manual_adjustments_history(
        str(keys["project_code"]),
        str(keys["facility_building"]),
        str(keys["construction_discipline"]),
        str(keys["boq_code"]),
    )


@st.cache_data(ttl=120, show_spinner=False)
def _cached_load_v2_all_manual_adjustments() -> pd.DataFrame:
    """Все ручные корректировки за всё время."""
    return fetch_all_adjustments_history()


def load_v2_all_manual_adjustments() -> pd.DataFrame:
    return _cached_load_v2_all_manual_adjustments()


def _v2_adjustment_record_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("project_code") or "").strip().upper(),
        str(record.get("facility_building") or "").strip().upper(),
        str(record.get("construction_discipline") or "").strip().upper(),
        str(record.get("boq_code") or "").strip().upper(),
    )


def _v2_selected_adjustment_key(item: pd.Series) -> tuple[str, str, str, str]:
    keys = _v2_adjustment_save_row(item)
    return _v2_adjustment_record_key(keys.to_dict())


@st.cache_data(ttl=300, show_spinner=False)
def _cached_v2_scope_boq_name_lookup() -> dict[tuple[str, str, str, str], str]:
    scope_df = load_scope()
    if scope_df.empty:
        return {}
    lookup: dict[tuple[str, str, str, str], str] = {}
    for _, row in scope_df.iterrows():
        key = _v2_adjustment_record_key(row.to_dict())
        if not key[3]:
            continue
        name = str(row.get("boq_name") or "").strip()
        if name:
            lookup[key] = name
    return lookup


def _v2_sort_adjustment_history_all(
    history: pd.DataFrame,
    selected_key: tuple[str, str, str, str],
) -> pd.DataFrame:
    if history.empty:
        return history
    df = history.copy()
    df["_is_selected"] = df.apply(
        lambda row: _v2_adjustment_record_key(row.to_dict()) == selected_key,
        axis=1,
    )
    updated_at = pd.to_datetime(df.get("updated_at"), errors="coerce", utc=True)
    created_at = pd.to_datetime(df.get("created_at"), errors="coerce", utc=True)
    df["_sort_at"] = updated_at.fillna(created_at)
    return (
        df.sort_values(by=["_is_selected", "_sort_at"], ascending=[False, False], na_position="last")
        .drop(columns=["_is_selected", "_sort_at"])
        .reset_index(drop=True)
    )


def _v2_adjustment_user_label(record: dict[str, Any]) -> str:
    for col in ("updated_by", "created_by", "user_email", "user"):
        value = record.get(col)
        if value is not None and not (isinstance(value, float) and pd.isna(value)):
            text = str(value).strip()
            if text:
                return text
    if str(record.get("comment") or "").strip() == "v2 manual adjustment":
        return "system / v2"
    return "Не указан"


def _v2_adjustment_audit_field_mapping_caption() -> None:
    st.caption(
        "Поля аудита в Supabase (`monthly_scope_manual_adjustments`): "
        f"ФИО → `{V2_ADJUSTMENT_AUDIT_DB_FIELDS['responsible_person']}`, "
        f"причина → `{V2_ADJUSTMENT_AUDIT_DB_FIELDS['adjustment_reason']}`, "
        f"время сохранения → `{V2_ADJUSTMENT_AUDIT_DB_FIELDS['saved_at']}` (МСК в UI). "
        "Отдельная SQL migration не требуется."
    )


V2_ADJUSTMENT_AUDIT_DISPLAY_COLUMNS = [
    "Текущий код",
    "BOQ-код",
    "Наименование",
    "Титул",
    "Дисциплина",
    "Ранее выполнено до системы",
    "Ручной подтверждённый остаток",
    "Исключено из выполнения",
    "Причина исключения",
    "ФИО (исключение)",
    "ФИО ответственного",
    "Причина корректировки",
    "Дата создания",
    "Дата обновления",
    "Исключение обновлено",
]


def _v2_adjustment_audit_history_df(history: pd.DataFrame, item: pd.Series) -> pd.DataFrame:
    """Таблица аудита всех ручных корректировок с отметкой выбранного BOQ."""
    if history.empty:
        return pd.DataFrame(columns=V2_ADJUSTMENT_AUDIT_DISPLAY_COLUMNS)

    selected_key = _v2_selected_adjustment_key(item)
    selected_boq_name = str(item.get("boq_name") or "").strip()
    name_lookup = _cached_v2_scope_boq_name_lookup()
    rows: list[dict[str, str]] = []
    for _, record in history.iterrows():
        rec = record.to_dict()
        record_key = _v2_adjustment_record_key(rec)
        is_selected = record_key == selected_key
        verified_raw = rec.get("manual_verified_remaining_qty")
        verified_display = (
            _v2_format_qty_display_str(verified_raw)
            if not _v2_is_missing_numeric(verified_raw)
            else "—"
        )
        boq_name = name_lookup.get(record_key) or (selected_boq_name if is_selected else "—")
        rows.append(
            {
                "Текущий код": "Да" if is_selected else "",
                "BOQ-код": str(rec.get("boq_code") or "—"),
                "Наименование": boq_name or "—",
                "Титул": str(rec.get("facility_building") or "—"),
                "Дисциплина": str(rec.get("construction_discipline") or "—"),
                "Ранее выполнено до системы": _v2_format_qty_display_str(
                    rec.get("manual_executed_before_system")
                ),
                "Ручной подтверждённый остаток": verified_display,
                "Исключено из выполнения": _v2_format_qty_display_str(rec.get("not_required_qty")),
                "Причина исключения": _v2_format_optional_text(rec.get("not_required_reason")),
                "ФИО (исключение)": _v2_format_optional_text(
                    rec.get("not_required_responsible_person")
                ),
                "ФИО ответственного": _v2_adjustment_user_label(rec),
                "Причина корректировки": _v2_format_optional_text(rec.get("reason")),
                "Дата создания": format_v2_added_at_moscow(rec.get("created_at")) or "—",
                "Дата обновления": format_v2_added_at_moscow(rec.get("updated_at")) or "—",
                "Исключение обновлено": format_v2_added_at_moscow(rec.get("not_required_updated_at"))
                or "—",
            }
        )
    return pd.DataFrame(rows)[V2_ADJUSTMENT_AUDIT_DISPLAY_COLUMNS]


def _v2_style_adjustment_audit_table(display_df: pd.DataFrame) -> Any:
    """Подсветка строк выбранного BOQ в таблице аудита."""

    def _row_style(row: pd.Series) -> list[str]:
        if str(row.get("Текущий код", "")).strip() == "Да":
            return ["background-color: #EFF6FF; font-weight: 600;"] * len(row)
        return [""] * len(row)

    return display_df.style.apply(_row_style, axis=1)


def _v2_render_adjustment_audit_history(item: pd.Series) -> None:
    """Expander полной истории всех ручных корректировок остатка."""
    with st.expander("История всех ручных корректировок остатка", expanded=False):
        st.caption(
            "Показаны все ручные корректировки. "
            "Выбранный BOQ поднят наверх и отмечен в колонке «Текущий код»."
        )
        history = _v2_sort_adjustment_history_all(
            load_v2_all_manual_adjustments(),
            _v2_selected_adjustment_key(item),
        )
        display_df = _v2_adjustment_audit_history_df(history, item)
        if display_df.empty:
            st.caption("Сохранённых ручных корректировок пока нет.")
            return
        st.dataframe(
            _v2_style_adjustment_audit_table(display_df),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"Всего записей в `monthly_scope_manual_adjustments`: {len(display_df)}."
        )


def _v2_render_adjustment_rollback(item: pd.Series) -> None:
    """Muted danger-zone отката текущей корректировки."""
    boq_code = str(item.get("boq_code") or "boq").strip()
    history = load_v2_manual_adjustments_history(item)
    if history.empty:
        return

    st.markdown(
        '<div class="v2-boq-adj-rollback">'
        '<p class="v2-boq-adj-rollback-title">Откатить текущую корректировку</p>'
        '<p class="v2-boq-adj-rollback-desc">'
        "Будет удалена ручная корректировка по выбранному BOQ. "
        "После удаления остаток снова будет рассчитан по Daily Progress."
        "</p></div>",
        unsafe_allow_html=True,
    )
    confirm = st.checkbox(
        "Я понимаю, что корректировка будет удалена из Supabase",
        key=f"v2_adj_delete_confirm_{boq_code}",
    )
    if st.button(
        "Удалить корректировку",
        key=f"v2_adj_delete_{boq_code}",
        disabled=not confirm,
    ):
        if not _v2_adjustment_keys_complete(item):
            st.error("Невозможно удалить корректировку: неполный ключ BOQ.")
            return
        try:
            delete_v2_manual_adjustment(item)
            _v2_clear_scope_caches_after_adjustment_change()
            st.success("Корректировка удалена. Остаток будет пересчитан.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Ошибка удаления корректировки: {exc}")


def _v2_render_adjustment_journal(item: pd.Series) -> None:
    """Журнал корректировок: полная история + откат."""
    _v2_render_adjustment_audit_history(item)
    _v2_render_adjustment_rollback(item)


def delete_v2_manual_adjustment(row: pd.Series) -> None:
    """Удалить корректировку выбранного BOQ из monthly_scope_manual_adjustments."""
    if not _v2_adjustment_keys_complete(row):
        raise ValueError("Невозможно удалить корректировку: неполный ключ BOQ.")
    delete_adjustment(_v2_adjustment_save_row(row))


def _v2_clear_scope_caches_after_adjustment_change() -> None:
    load_scope.clear()
    load_adjustments.clear()
    _cached_fetch_v2_scope_view.clear()
    _cached_fetch_v2_manual_adjustments_history.clear()
    _cached_load_v2_all_manual_adjustments.clear()
    _cached_v2_scope_boq_name_lookup.clear()


def _v2_clear_scope_caches_after_adjustment_save() -> None:
    _v2_clear_scope_caches_after_adjustment_change()


def _render_residual_adjustment_content(item: pd.Series) -> None:
    """Содержимое корректировки остатка — production save через v1 pipeline."""
    boq_code = str(item.get("boq_code") or "boq").strip()
    manual_exec_raw = item.get("manual_executed_before_system", item.get("manual_adjustment_qty", 0))
    manual_exec_default = 0.0 if _v2_is_missing_numeric(manual_exec_raw) else _v2_safe_num(manual_exec_raw)
    total_qty = _v2_safe_num(item.get("total_qty"))

    inp_exec = st.number_input(
        "Ранее выполнено до Daily Progress",
        min_value=0.0,
        value=float(manual_exec_default),
        step=0.01,
        key=f"v2_adj_exec_{boq_code}",
    )
    responsible_person = st.text_input(
        "ФИО ответственного за корректировку",
        value="",
        key=f"v2_adj_responsible_{boq_code}",
    )
    adjustment_reason = st.text_input(
        "Причина корректировки",
        value="",
        placeholder=V2_ADJUSTMENT_REASON_PLACEHOLDER,
        key=f"v2_adj_reason_{boq_code}",
    )
    _v2_adjustment_audit_field_mapping_caption()

    if st.button("Сохранить корректировку", key=f"v2_adj_save_{boq_code}"):
        responsible_text = str(responsible_person or "").strip()
        reason_text = str(adjustment_reason or "").strip()
        if not responsible_text:
            st.error("Укажите ФИО ответственного за корректировку.")
        elif not reason_text:
            st.error("Укажите причину корректировки.")
        elif inp_exec < 0:
            st.error("Ранее выполненный объём не может быть отрицательным.")
        elif inp_exec > total_qty:
            st.error("Ранее выполненный объём не может превышать общий объём BOQ.")
        else:
            try:
                save_adjustment(
                    _v2_adjustment_save_row(item),
                    inp_exec,
                    None,
                    reason_text,
                    "v2 manual adjustment",
                    updated_by=responsible_text,
                )
                saved_at_msk = format_v2_added_at_moscow(
                    datetime.now(timezone.utc).isoformat()
                )
                _v2_clear_scope_caches_after_adjustment_save()
                st.success(
                    f"Корректировка сохранена: {responsible_text}, {saved_at_msk or '—'}"
                )
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Ошибка сохранения корректировки: {exc}")

    st.divider()
    _render_not_required_exclusion_section(item)
    _v2_render_adjustment_journal(item)


def _render_not_required_exclusion_section(item: pd.Series) -> None:
    """Секция исключения остатка из выполнения."""
    boq_code = str(item.get("boq_code") or "boq").strip()
    total_qty = _v2_safe_num(item.get("total_qty"))
    max_exclude_qty = _v2_raw_remaining_before_exclusion(item)
    default_exclude = _v2_safe_num(item.get("not_required_qty"))
    default_reason = str(item.get("not_required_reason") or "").strip()
    if default_reason and default_reason not in V2_NOT_REQUIRED_REASON_OPTIONS:
        default_reason = "Другое"

    st.markdown("**Исключение остатка из выполнения**")
    st.caption(
        "Для BOQ, где часть проектного объёма не требуется к выполнению "
        "(ошибка проекта, уточнение трассы и т.п.)."
    )
    if not adjustments_support_not_required_columns():
        st.warning(
            "Колонки not_required_* в Supabase ещё не созданы. "
            "Выполните `sql/monthly_scope_not_required_exclusion.sql`, затем перезапустите приложение."
        )
        return

    inp_exclude = st.number_input(
        "Объём, не требующий выполнения",
        min_value=0.0,
        value=float(default_exclude),
        step=0.01,
        key=f"v2_not_req_qty_{boq_code}",
    )
    exclude_reason = st.selectbox(
        "Причина исключения",
        V2_NOT_REQUIRED_REASON_OPTIONS,
        index=V2_NOT_REQUIRED_REASON_OPTIONS.index(default_reason)
        if default_reason in V2_NOT_REQUIRED_REASON_OPTIONS
        else 0,
        key=f"v2_not_req_reason_{boq_code}",
    )
    exclude_responsible = st.text_input(
        "ФИО ответственного",
        value=str(item.get("not_required_responsible_person") or "").strip(),
        key=f"v2_not_req_responsible_{boq_code}",
    )
    exclude_comment = st.text_area(
        "Основание / комментарий",
        value=str(item.get("not_required_comment") or "").strip(),
        key=f"v2_not_req_comment_{boq_code}",
        height=72,
    )
    st.caption(
        f"Максимум к исключению по текущему остатку: "
        f"{_v2_format_qty_display_str(max_exclude_qty)}. "
        "Поля Supabase: not_required_qty, not_required_reason, "
        "not_required_responsible_person, not_required_comment, not_required_updated_at."
    )

    if st.button("Сохранить исключение остатка", key=f"v2_not_req_save_{boq_code}"):
        responsible_text = str(exclude_responsible or "").strip()
        reason_text = str(exclude_reason or "").strip()
        exclude_qty = float(inp_exclude)
        if exclude_qty <= 0:
            st.error("Объём исключения должен быть больше 0.")
        elif not responsible_text:
            st.error("Укажите ФИО ответственного.")
        elif not reason_text:
            st.error("Укажите причину исключения.")
        elif _v2_qty_exceeds_limit(exclude_qty, max_exclude_qty):
            st.error(
                f"Исключаемый объём не может превышать текущий остаток "
                f"({_v2_format_qty_validation_str(max_exclude_qty)})."
            )
        elif _v2_qty_exceeds_limit(exclude_qty, total_qty):
            st.error("Исключаемый объём не может превышать проектный объём BOQ.")
        else:
            try:
                save_not_required_exclusion(
                    _v2_adjustment_save_row(item),
                    exclude_qty,
                    reason_text,
                    responsible_text,
                    str(exclude_comment or "").strip(),
                )
                saved_at_msk = format_v2_added_at_moscow(datetime.now(timezone.utc).isoformat())
                _v2_clear_scope_caches_after_adjustment_save()
                st.success(f"Исключение сохранено: {responsible_text}, {saved_at_msk or '—'}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Ошибка сохранения исключения: {exc}")


def _render_add_to_month_plan_content(item: pd.Series) -> None:
    """Содержимое добавления объёма в текущий месяц планирования (session draft)."""
    boq_code = str(item.get("boq_code") or "boq").strip()
    planning_month = _v2_resolve_planning_month_key(
        str(st.session_state.get("v2_scope_planning_month") or "").strip()
    )
    available_qty = _v2_safe_num(item.get("available_to_add_qty"))
    session_reserved = _v2_safe_num(item.get("already_planned_qty"))
    is_overrun = (
        str(item.get("status") or "") == V2_SCOPE_STATUS_OVERRUN
        or _v2_safe_num(item.get("overrun_qty")) > 0
    )
    is_not_required = str(item.get("status") or "") == V2_SCOPE_STATUS_NOT_REQUIRED

    if is_overrun:
        st.warning(
            "Факт превышает BOQ. Требуется проверка Daily Progress / BOQ / допработ. "
            "Добавление в месячный план недоступно."
        )
        return
    if is_not_required:
        st.info("Остаток не требуется к выполнению. Добавление в месячный план недоступно.")
        return

    if not planning_month:
        st.warning(
            "Выберите конкретный месяц планирования в фильтрах scope "
            "(не «Все месяца»)."
        )
        return

    st.markdown(
        _v2_render_plan_add_context_html(item, planning_month, available_qty),
        unsafe_allow_html=True,
    )
    boq_name = str(item.get("boq_name") or "").strip()
    if boq_name:
        st.markdown(
            f'<p class="v2-plan-add-name">{boq_name}</p>',
            unsafe_allow_html=True,
        )
    if session_reserved > 0:
        st.caption(
            f"В текущей сессии уже запланировано: "
            f"{_v2_format_qty_display_str(session_reserved)} {item.get('unit', '')}"
        )

    if V2_CURRENT_PLANNER_NAME_KEY not in st.session_state:
        st.session_state[V2_CURRENT_PLANNER_NAME_KEY] = ""
    st.text_input(
        "ФИО планировщика",
        key=V2_CURRENT_PLANNER_NAME_KEY,
        placeholder="Обязательное поле",
    )

    st.markdown('<div class="v2-plan-add-zone">', unsafe_allow_html=True)
    input_left, input_right = st.columns([1.1, 1])
    with input_left:
        plan_qty = st.number_input(
            "Объём к планированию",
            min_value=0.0,
            value=0.0,
            step=0.01,
            key=f"v2_plan_qty_{boq_code}",
        )
        crew_options = load_v2_crew_options()
        crew_size_map = load_v2_crew_size_map()
        crew_key = f"v2_plan_crew_{boq_code}"
        size_key = f"v2_plan_crew_size_{boq_code}"
        prev_crew_key = f"v2_plan_crew_prev_{boq_code}"
        crew_col, size_col = st.columns([2, 1])
        with crew_col:
            crew = st.selectbox(
                "Звено / crew",
                crew_options,
                key=crew_key,
            )
            _v2_render_crew_load_caption()
        with size_col:
            if st.session_state.get(prev_crew_key) != crew:
                st.session_state[size_key] = _v2_resolve_crew_size(crew, crew_size_map)
                st.session_state[prev_crew_key] = crew
            if size_key not in st.session_state:
                st.session_state[size_key] = _v2_resolve_crew_size(crew, crew_size_map)
            crew_size = st.number_input(
                "Кол-во людей в звене",
                min_value=1,
                step=1,
                key=size_key,
            )
    with input_right:
        st.markdown(_v2_render_norm_scenario_hint_html(), unsafe_allow_html=True)
        st.markdown(_v2_render_norm_history_strip_html(item), unsafe_allow_html=True)
        norm_scenario = st.selectbox(
            "Сценарий нормы",
            NORM_SCENARIO_OPTIONS,
            key=f"v2_plan_norm_{boq_code}",
        )
        manual_norm = 0.0
        if norm_scenario == NORM_SCENARIO_MANUAL:
            manual_norm = st.number_input(
                "Ручная норма, ч/ед",
                min_value=0.0,
                value=0.0,
                step=0.01,
                key=f"v2_plan_manual_norm_{boq_code}",
            )
        comment = st.text_input(
            "Комментарий",
            value="",
            key=f"v2_plan_comment_{boq_code}",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    preview = v2_compute_plan_add_preview(
        item,
        float(plan_qty),
        norm_scenario,
        float(manual_norm),
        float(crew_size),
    )
    st.markdown(_v2_render_plan_add_preview_html(preview), unsafe_allow_html=True)

    if preview["needs_manual_norm"]:
        st.markdown(
            '<div class="v2-plan-add-warn">'
            "Для кода нет исторической нормы. Укажите ручную норму."
            "</div>",
            unsafe_allow_html=True,
        )

    plan_qty_f = float(plan_qty)
    crew_valid = _v2_crew_is_valid(crew)
    manual_ok = norm_scenario != NORM_SCENARIO_MANUAL or float(manual_norm) > 0
    qty_ok = plan_qty_f > 0 and plan_qty_f <= available_qty
    has_available = available_qty > 0
    planner_name = str(st.session_state.get(V2_CURRENT_PLANNER_NAME_KEY) or "").strip()
    planner_ok = bool(planner_name)

    if plan_qty_f > available_qty and plan_qty_f > 0:
        st.warning("Объём превышает доступный остаток.")
    if not has_available:
        st.caption("Нет доступного остатка для планирования.")

    add_disabled = (
        not has_available
        or not qty_ok
        or not crew_valid
        or not manual_ok
        or not planner_ok
        or preview["needs_manual_norm"]
    )

    btn_col, _ = st.columns([1, 2])
    with btn_col:
        if st.button(
            "Добавить в месячный план",
            type="primary",
            disabled=add_disabled,
            key=f"v2_plan_add_{boq_code}",
        ):
            if not planner_ok:
                st.error("Укажите ФИО планировщика")
            else:
                append_v2_month_plan_draft_item(
                    item,
                    planning_month,
                    plan_qty_f,
                    str(crew).strip(),
                    norm_scenario,
                    float(manual_norm),
                    comment,
                    preview,
                    planner_name,
                )
                st.success("Строка добавлена в месячный план")
                st.rerun()

    st.markdown(
        '<p class="v2-boq-action-footnote">'
        "Строка добавляется в месячный план. Для записи в Supabase нажмите "
        "«Сохранить месячный план» в модуле действий."
        "</p>",
        unsafe_allow_html=True,
    )


def _v2_map_norm_type(raw: Any) -> str:
    text = str(raw or "").strip().upper()
    if text in {"ИСТОРИЯ ЕСТЬ", "HISTORY", "ИСТОРИЧЕСКАЯ"}:
        return "Историческая"
    if text in {"НЕТ ИСТОРИИ", "NO_HISTORY", "БЕЗ ИСТОРИИ"}:
        return "Без истории"
    if text in {"MANUAL", "РУЧНАЯ"}:
        return "Ручная"
    return "Не подключено"


def _v2_map_productivity_history(raw: Any) -> str:
    text = str(raw or "").strip().upper()
    if text in {"ИСТОРИЯ ЕСТЬ", "HISTORY", "ЕСТЬ"}:
        return "Есть"
    if text in {"НЕТ ИСТОРИИ", "NO_HISTORY", "НЕТ"}:
        return "Нет"
    return "Не подключено"


def _v2_format_norm_hours_display(value: Any) -> str:
    val = _v2_safe_num(value, default=float("nan"))
    if pd.isna(val) or val <= 0:
        return "-"
    return _v2_format_qty_display_str(val)


def _v2_scope_table_manual_executed_qty_series(scoped_df: pd.DataFrame) -> pd.Series:
    """Ручная корректировка выполненного объёма (manual_executed_before_system)."""
    return _v2_safe_df_col(scoped_df, "manual_executed_before_system")


def _v2_scope_table_not_required_qty_series(scoped_df: pd.DataFrame) -> pd.Series:
    """Исключённый из выполнения объём (not_required_qty)."""
    return _v2_safe_df_col(scoped_df, "not_required_qty")


def _v2_scope_table_not_required_value_series(scoped_df: pd.DataFrame) -> pd.Series:
    """Стоимость исключённого остатка — только not_required_qty, не manual."""
    qty = _v2_scope_table_not_required_qty_series(scoped_df)
    per_unit = _v2_resolve_scoped_unit_price_series(scoped_df)
    return (qty * per_unit).where(qty > 0, 0.0)


def _v2_scope_table_overrun_value_series(scoped_df: pd.DataFrame) -> pd.Series:
    """Стоимость превышения BOQ для таблицы (display-only)."""
    if "overrun_value" in scoped_df.columns:
        return _v2_safe_df_col(scoped_df, "overrun_value")
    qty = _v2_safe_df_col(scoped_df, "overrun_qty")
    per_unit = _v2_resolve_scoped_unit_price_series(scoped_df)
    return qty * per_unit


def _v2_scope_adjustment_reason_column(scoped_df: pd.DataFrame) -> pd.Series:
    """Причина: исключение остатка или ручная корректировка выполненного."""
    manual_qty = _v2_scope_table_manual_executed_qty_series(scoped_df)
    exclude_qty = _v2_scope_table_not_required_qty_series(scoped_df)
    manual_reason = (
        scoped_df["manual_adjustment_reason"].astype(str).str.strip()
        if "manual_adjustment_reason" in scoped_df.columns
        else pd.Series("", index=scoped_df.index)
    )
    exclude_reason = (
        scoped_df["not_required_reason"].astype(str).str.strip()
        if "not_required_reason" in scoped_df.columns
        else pd.Series("", index=scoped_df.index)
    )

    def _label(m_qty: float, e_qty: float, m_reason: str, e_reason: str) -> str:
        e_text = str(e_reason or "").strip()
        m_text = str(m_reason or "").strip()
        if e_qty > 0 and e_text and e_text not in {"—", "nan", "None", "<NA>"}:
            return e_text
        if m_qty > 0 and m_text and m_text not in {"—", "nan", "None", "<NA>"}:
            return m_text
        if e_qty > 0:
            return "Исключение остатка из выполнения"
        if m_qty > 0:
            return "Ручная корректировка выполненного"
        return "—"

    return pd.Series(
        [
            _label(m, e, mr, er)
            for m, e, mr, er in zip(
                manual_qty, exclude_qty, manual_reason, exclude_reason, strict=False
            )
        ],
        index=scoped_df.index,
    )


def _v2_scope_status_table_display_label(status: str) -> str:
    """Отображаемый label статуса в таблице BOQ (внутреннее значение не меняется)."""
    key = str(status or "").strip()
    return V2_SCOPE_STATUS_TABLE_DISPLAY_LABELS.get(key, key)


def _v2_format_scope_table_display(display_df: pd.DataFrame) -> pd.DataFrame:
    """Форматирование чисел и display-label статуса для таблицы."""
    out = display_df.copy()
    for col in V2_SCOPE_QTY_COLUMNS:
        if col in out.columns:
            out[col] = out[col].apply(_v2_format_qty_display_str)
    for col in V2_SCOPE_COST_COLUMNS:
        if col in out.columns:
            out[col] = out[col].apply(
                lambda value: _format_rub(_v2_safe_num(value)) if _v2_safe_num(value) > 0 else "—"
            )
    for col in V2_SCOPE_PERCENT_COLUMNS:
        if col in out.columns:
            out[col] = out[col].apply(_v2_format_percent_display_str)
    if "Статус" in out.columns:
        out["Статус"] = out["Статус"].apply(_v2_scope_status_table_display_label)
    return out


def derive_construction_queue_from_facility(facility: str) -> str:
    """Вычисляемая очередь строительства по титулу / объекту."""
    text = str(facility or "")
    if "16160-13" in text or "16160-17" in text:
        return "1 очередь"
    if "26160-13" in text or "26160-17" in text:
        return "2 очередь"
    return "Не определено"


def _v2_is_bare_bhk_project_label(value: Any) -> bool:
    """Точное совпадение «БХК» / «BHK», не подстрока в PRJ-001-БХК."""
    text = str(value or "").strip().upper()
    return text in {"БХК", "BHK"}


def _v2_is_valid_project_filter_option(value: Any) -> bool:
    """project_code допустим в dropdown «Проект» (голый «БХК» скрывается)."""
    text = str(value or "").strip()
    if not text:
        return False
    return not _v2_is_bare_bhk_project_label(text)


def _v2_is_prj_bhk_code(value: Any) -> bool:
    """Код проекта PRJ-001-БХК (варианты с _ / -)."""
    text = str(value or "").strip().upper().replace("_", "-").replace(" ", "")
    if text in {m.upper().replace("_", "-") for m in V2_PRJ_BHK_CODE_MARKERS}:
        return True
    return text.startswith("PRJ-001") and ("БХК" in text or "BHK" in text)


def normalize_project_filter_values(df: pd.DataFrame) -> pd.Series:
    """
    Нормализованный project_code для фильтра и таблицы.
    Только колонка project_code; project_name не подставляется.
    Голый «БХК» / «BHK» обнуляется (не попадает в dropdown), строка не удаляется.
    """
    if df.empty:
        return pd.Series(dtype=str)

    if "project_code" not in df.columns:
        return pd.Series([""] * len(df), index=df.index)

    result = df["project_code"].fillna("").astype(str).str.strip()
    bare_bhk = result.apply(_v2_is_bare_bhk_project_label)
    result = result.mask(bare_bhk, "")
    return result


@st.cache_data(ttl=300, show_spinner=False)
def _cached_fetch_v2_scope_view(limit: int) -> pd.DataFrame:
    from services.supabase_client import supabase

    response = supabase.table(V2_SCOPE_VIEW).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


def _demo_raw_scope_df() -> pd.DataFrame:
    """View-подобный demo fallback для normalize/calculate pipeline."""
    demo = build_demo_boq_scope_df()
    qty = pd.to_numeric(demo["Было"], errors="coerce").fillna(0.0)
    unit_price = pd.Series([1250.0, 890.0, 4200.0, 650.0, 3100.0, 15000.0, 9800.0, 7200.0])
    return pd.DataFrame(
        {
            "project_code": ["PRJ_001_БХК"] * len(demo),
            "construction_queue": [""] * len(demo),
            "facility_building": [
                "16160-13 Block A",
                "26160-17 Zone B",
                "16160-17 Unit C",
                "Титул 1",
                "26160-13 Area D",
                "Объект К-100",
                "16160-13 Block E",
                "Титул 2",
            ],
            "construction_discipline": demo["Дисциплина"].astype(str),
            "system_label": ["SYS-A", "SYS-B", "SYS-C", "SYS-A", "SYS-D", "SYS-B", "SYS-C", "SYS-D"],
            "iwp_id": ["IWP-101", "IWP-204", "IWP-310", "IWP-101", "IWP-220", "IWP-310", "IWP-118", "IWP-204"],
            "boq_code": demo["BOQ код"].astype(str),
            "boq_name": demo["Наименование работ"].astype(str),
            "unit_of_measure": demo["Ед. изм."].astype(str),
            "total_project_qty": qty,
            "executed_qty_all_time": pd.to_numeric(demo["Выполнено"], errors="coerce").fillna(0.0),
            "planning_remaining_qty": pd.to_numeric(demo["Остаток"], errors="coerce").fillna(0.0),
            "unit_price": unit_price,
            "total_project_value": qty * unit_price,
            "planning_remaining_value": pd.to_numeric(demo["Остаток"], errors="coerce").fillna(0.0)
            * unit_price,
            "remaining_qty_source": "SYSTEM_CALCULATED",
        }
    )


def load_v2_boq_scope_from_supabase(limit: int = 10000) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Read-only загрузка BOQ Scope из monthly_scope_picker_view.
    Не пишет в БД и не меняет session_state.
    """
    meta: dict[str, Any] = {
        "source": V2_SCOPE_VIEW,
        "is_fallback": False,
        "error": None,
        "columns": [],
        "row_count": 0,
    }
    try:
        raw = _cached_fetch_v2_scope_view(limit)
        meta["columns"] = list(raw.columns)
        meta["row_count"] = len(raw)
        return raw, meta
    except Exception as exc:  # noqa: BLE001
        demo_raw = _demo_raw_scope_df()
        meta.update(
            {
                "source": "demo fallback",
                "is_fallback": True,
                "error": str(exc),
                "columns": list(demo_raw.columns),
                "row_count": len(demo_raw),
            }
        )
        return demo_raw, meta


def normalize_v2_scope_df(df: pd.DataFrame) -> pd.DataFrame:
    """Приведение полей view к единой внутренней структуре v2 scope."""
    if df.empty:
        return pd.DataFrame(columns=V2_SCOPE_INTERNAL_COLUMNS)

    normalized = pd.DataFrame(
        {
            "project_code": normalize_project_filter_values(df),
            "construction_queue": _v2_pick_series(df, "construction_queue"),
            "facility": _v2_pick_series(df, "facility"),
            "discipline": _v2_pick_series(df, "discipline"),
            "system": _v2_pick_series(df, "system"),
            "iwp": _v2_pick_series(df, "iwp"),
            "boq_code": _v2_pick_series(df, "boq_code"),
            "boq_name": _v2_pick_series(df, "boq_name"),
            "unit": _v2_pick_series(df, "unit"),
            "total_qty": _v2_pick_series(df, "total_qty", 0.0),
            "executed_qty": _v2_pick_series(df, "executed_qty", 0.0),
            "remaining_qty": _v2_pick_view_numeric_series(df, "planning_remaining_qty"),
            "remaining_value": _v2_pick_view_numeric_series(df, "planning_remaining_value"),
            "remaining_qty_source": _v2_pick_series(df, "remaining_qty_source"),
            "unit_price": _v2_pick_series(df, "unit_price", 0.0),
            "total_value": _v2_pick_series(df, "total_value", 0.0),
            "already_planned_qty": _v2_pick_series(df, "already_planned_qty", 0.0),
            "planned_month": _v2_pick_series(df, "planned_month"),
            "planned_at": _v2_pick_series(df, "planned_at"),
        }
    )
    normalized["boq_code"] = normalized["boq_code"].astype(str).str.strip().str.upper()
    normalized["construction_queue"] = normalized["facility"].apply(derive_construction_queue_from_facility)
    missing_total_value = normalized["total_value"] <= 0
    normalized.loc[missing_total_value, "total_value"] = (
        normalized.loc[missing_total_value, "total_qty"]
        * normalized.loc[missing_total_value, "unit_price"]
    )
    normalized["manual_executed_before_system"] = _v2_pick_series(
        df, "manual_executed_before_system", 0.0
    )
    normalized["manual_adjustment_qty"] = normalized["manual_executed_before_system"]
    normalized["manual_verified_remaining_qty"] = _v2_pick_view_numeric_series(
        df, "manual_verified_remaining_qty"
    )
    normalized["manual_adjustment_reason"] = _v2_pick_series(df, "manual_adjustment_reason")
    normalized["manual_adjustment_comment"] = _v2_pick_series(df, "manual_adjustment_comment")
    normalized["manual_adjustment_updated_at"] = _v2_pick_series(df, "manual_adjustment_updated_at")
    normalized["_view_planning_remaining_qty"] = _v2_pick_view_numeric_series(
        df, "planning_remaining_qty"
    )
    adjustment_source_raw = _v2_pick_series(df, "manual_adjustment_source")
    normalized["manual_adjustment_source"] = adjustment_source_raw.apply(_v2_map_adjustment_source)
    norm_status_raw = _v2_pick_series(df, "norm_status")
    normalized["norm_status"] = norm_status_raw
    normalized["norm_type"] = norm_status_raw.apply(_v2_map_norm_type)
    normalized["productivity_history"] = norm_status_raw.apply(_v2_map_productivity_history)
    normalized["p50_hours_per_unit"] = _v2_pick_series(df, "p50_hours_per_unit", 0.0)
    normalized["p80_hours_per_unit"] = _v2_pick_series(df, "p80_hours_per_unit", 0.0)
    normalized["weighted_avg_hours_per_unit"] = _v2_pick_series(
        df, "weighted_avg_hours_per_unit", 0.0
    )
    norm_hours_raw = _v2_pick_series(df, "norm_hours_per_unit", 0.0)
    normalized["norm_hours_per_unit"] = norm_hours_raw.apply(_v2_format_norm_hours_display)
    return normalized


def _v2_raw_project_name_series(raw_df: pd.DataFrame, index: pd.Index) -> pd.Series:
    if not raw_df.empty and len(raw_df) == len(index) and "project_name" in raw_df.columns:
        return raw_df["project_name"].reindex(index).fillna("").astype(str).str.strip()
    return pd.Series([""] * len(index), index=index)


def _v2_build_bhk_project_name_diagnostics(
    raw_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
) -> dict[str, Any]:
    """Read-only: project_name = БХК vs project_code (без удаления строк)."""
    empty_result: dict[str, Any] = {
        "rows_project_name_bhk": 0,
        "rows_with_prj_code": 0,
        "rows_empty_project_code": 0,
        "total_value_project_name_bhk": 0.0,
        "project_code_missing_rows": pd.DataFrame(),
    }
    if normalized_df.empty:
        return empty_result

    project_name = _v2_raw_project_name_series(raw_df, normalized_df.index)
    name_is_bhk = project_name.apply(_v2_is_bare_bhk_project_label)
    norm_codes = normalized_df["project_code"].fillna("").astype(str).str.strip()
    code_is_prj = norm_codes.apply(_v2_is_prj_bhk_code)
    empty_code = norm_codes == ""

    bhk_rows = normalized_df[name_is_bhk]
    total_value = float(
        pd.to_numeric(bhk_rows.get("total_value"), errors="coerce").fillna(0).sum()
    )
    missing_rows = normalized_df[name_is_bhk & empty_code]
    missing_preview = (
        _v2_cost_rows_preview(missing_rows, "project_code_missing")
        if not missing_rows.empty
        else pd.DataFrame()
    )

    return {
        "rows_project_name_bhk": int(name_is_bhk.sum()),
        "rows_with_prj_code": int((name_is_bhk & code_is_prj).sum()),
        "rows_empty_project_code": int((name_is_bhk & empty_code).sum()),
        "total_value_project_name_bhk": total_value,
        "project_code_missing_rows": missing_preview,
    }


def _v2_diag_remaining_qty_series(df: pd.DataFrame) -> pd.Series:
    rem = pd.to_numeric(df.get("remaining_qty"), errors="coerce")
    total = pd.to_numeric(df.get("total_qty"), errors="coerce").fillna(0.0)
    executed = pd.to_numeric(df.get("executed_qty"), errors="coerce").fillna(0.0)
    return rem.where(rem.notna(), total - executed)


def _v2_diag_remaining_value_series(df: pd.DataFrame) -> pd.Series:
    rem_val = pd.to_numeric(df.get("remaining_value"), errors="coerce")
    unit_price = pd.to_numeric(df.get("unit_price"), errors="coerce").fillna(0.0)
    fallback = _v2_diag_remaining_qty_series(df) * unit_price
    return rem_val.where(rem_val.notna(), fallback)


def _v2_diag_aggregate_metrics(df: pd.DataFrame) -> dict[str, float | int]:
    if df.empty:
        return {
            "rows": 0,
            "total_value": 0.0,
            "remaining_value": 0.0,
            "total_qty": 0.0,
            "remaining_qty": 0.0,
        }
    return {
        "rows": len(df),
        "total_value": float(pd.to_numeric(df.get("total_value"), errors="coerce").fillna(0).sum()),
        "remaining_value": float(_v2_diag_remaining_value_series(df).sum()),
        "total_qty": float(pd.to_numeric(df.get("total_qty"), errors="coerce").fillna(0).sum()),
        "remaining_qty": float(_v2_diag_remaining_qty_series(df).sum()),
    }


def _v2_apply_v1_style_queue_filter(df: pd.DataFrame, queue_filter: str) -> pd.DataFrame:
    """v1: facility строго in ['16160-13', ...], не substring."""
    if df.empty or queue_filter in {"", "Все"}:
        return df
    titles = {str(t).strip() for t in V2_V1_QUEUE_FACILITY_EXACT.get(queue_filter, [])}
    if not titles:
        return df
    facility = df.get("facility", df.get("facility_building", pd.Series([""] * len(df))))
    mask = facility.fillna("").astype(str).str.strip().isin(titles)
    return df[mask].copy()


def _v2_build_invalid_excluded_preview(normalized_df: pd.DataFrame, limit: int = 100) -> pd.DataFrame:
    if normalized_df.empty:
        return pd.DataFrame()
    valid_mask = (normalized_df["unit_price"] > 0) | (normalized_df["total_value"] > 0)
    excluded = normalized_df[~valid_mask].copy()
    if excluded.empty:
        return pd.DataFrame()

    rem_qty = _v2_diag_remaining_qty_series(excluded)
    rem_val = _v2_diag_remaining_value_series(excluded)
    return pd.DataFrame(
        {
            "project_code": excluded.get("project_code", pd.Series([""] * len(excluded))).astype(str),
            "facility": excluded.get("facility", pd.Series([""] * len(excluded))).astype(str),
            "discipline": excluded.get("discipline", pd.Series([""] * len(excluded))).astype(str),
            "boq_code": excluded.get("boq_code", pd.Series([""] * len(excluded))).astype(str),
            "boq_name": excluded.get("boq_name", pd.Series([""] * len(excluded))).astype(str),
            "unit_price": pd.to_numeric(excluded.get("unit_price"), errors="coerce").fillna(0),
            "total_value": pd.to_numeric(excluded.get("total_value"), errors="coerce").fillna(0),
            "total_qty": pd.to_numeric(excluded.get("total_qty"), errors="coerce").fillna(0),
            "planning_remaining_qty": rem_qty,
            "planning_remaining_value": rem_val,
        }
    ).head(limit)


def _v2_collect_project_facility_uniques(raw_df: pd.DataFrame) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for col in ("project_code", "project_name", "project"):
        if col in raw_df.columns:
            vals = raw_df[col].dropna().astype(str).str.strip()
            result[col] = sorted({v for v in vals if v})
    if "facility_building" in raw_df.columns:
        vals = raw_df["facility_building"].dropna().astype(str).str.strip()
        result["facility_building"] = sorted({v for v in vals if v})[:200]
    return result


def build_v1_v2_filter_diagnostics(
    raw_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
    filters: dict[str, str],
) -> dict[str, Any]:
    """Пошаговая сверка фильтрации v1/v2 для диагностики расхождений KPI."""
    steps: list[dict[str, Any]] = []

    def _record(step: str, frame: pd.DataFrame) -> pd.DataFrame:
        metrics = _v2_diag_aggregate_metrics(frame)
        steps.append({"Шаг": step, **metrics})
        return frame

    current = normalized_df.copy()
    steps.append(
        {
            "Шаг": "1. raw rows from monthly_scope_picker_view",
            **_v2_diag_aggregate_metrics(normalized_df),
        }
    )

    if filters.get("project", "Все") != "Все":
        current = current[current["project_code"].astype(str) == filters["project"]]
    current = _record("2. rows after project filter", current)

    if filters.get("queue", "Все") != "Все":
        current = current[current["construction_queue"].astype(str) == filters["queue"]]
    current = _record("3. rows after construction queue filter (v2)", current)

    if filters.get("title", "Все") != "Все":
        current = current[current["facility"].astype(str) == filters["title"]]
    current = _record("4. rows after title/facility filter", current)

    if filters.get("discipline", "Все") != "Все":
        current = current[current["discipline"].astype(str) == filters["discipline"]]
    current = _record("5. rows after discipline filter", current)

    before_invalid = current.copy()
    before_metrics = _v2_diag_aggregate_metrics(before_invalid)
    steps.append({"Шаг": "6. rows before invalid price/value exclusion", **before_metrics})

    valid_mask = (before_invalid["unit_price"] > 0) | (before_invalid["total_value"] > 0)
    excluded_count = int((~valid_mask).sum())
    excluded_df = before_invalid[~valid_mask]
    excluded_metrics = _v2_diag_aggregate_metrics(excluded_df)
    steps.append(
        {
            "Шаг": "7. rows excluded by invalid price/value rule",
            "rows": excluded_count,
            "total_value": excluded_metrics["total_value"],
            "remaining_value": excluded_metrics["remaining_value"],
            "total_qty": excluded_metrics["total_qty"],
            "remaining_qty": excluded_metrics["remaining_qty"],
        }
    )

    after_invalid = before_invalid[valid_mask].copy()
    after_metrics = _v2_diag_aggregate_metrics(after_invalid)
    steps.append({"Шаг": "8. rows after invalid price/value exclusion", **after_metrics})

    for step_no, label, metrics in (
        (9, "total_value before invalid exclusion", before_metrics),
        (10, "total_value after invalid exclusion", after_metrics),
        (11, "remaining_value before invalid exclusion", before_metrics),
        (12, "remaining_value after invalid exclusion", after_metrics),
        (13, "total_qty before invalid exclusion", before_metrics),
        (14, "total_qty after invalid exclusion", after_metrics),
        (15, "remaining_qty before invalid exclusion", before_metrics),
        (16, "remaining_qty after invalid exclusion", after_metrics),
    ):
        steps.append({"Шаг": f"{step_no}. {label}", **metrics})

    queue_filter = filters.get("queue", "Все")
    v1_queue_rows = len(_v2_apply_v1_style_queue_filter(before_invalid, queue_filter))
    if queue_filter in {"", "Все"}:
        v2_queue_rows = len(before_invalid)
    else:
        v2_queue_rows = len(
            before_invalid[before_invalid["construction_queue"].astype(str) == queue_filter]
        )

    steps_df = pd.DataFrame(steps)
    display = pd.DataFrame()
    if not steps_df.empty:
        display = steps_df.copy()
        for col in ("total_value", "remaining_value"):
            display[col] = display[col].apply(lambda v: _format_rub(float(v)) if pd.notna(v) else "—")
        for col in ("total_qty", "remaining_qty"):
            display[col] = display[col].apply(
                lambda v: _v2_format_qty_display_str(v) if pd.notna(v) else "—"
            )
        display = display.rename(columns={"rows": "Строк"})

    return {
        "steps_df": display,
        "excluded_preview": _v2_build_invalid_excluded_preview(before_invalid, limit=100),
        "unique_labels": _v2_collect_project_facility_uniques(raw_df),
        "v1_queue_rows": v1_queue_rows,
        "v2_queue_rows": v2_queue_rows,
        "queue_filter": queue_filter,
        "excluded_lost": excluded_metrics,
        "before_invalid_rows": before_metrics["rows"],
        "after_invalid_rows": after_metrics["rows"],
        "bhk_project_name_diag": _v2_build_bhk_project_name_diagnostics(raw_df, normalized_df),
        "actual_v2_pipeline_note": (
            "Фактический pipeline v2: normalize → invalid exclusion → calculate → UI filters. "
            "Таблица выше симулирует UI filters → invalid exclusion для пошаговой сверки с v1."
        ),
    }


def _v2_diag_cost_triplet(df: pd.DataFrame) -> dict[str, float]:
    """total_value, planning_remaining_value, executed_value для диагностики стоимости."""
    if df.empty:
        return {
            "total_value": 0.0,
            "planning_remaining_value": 0.0,
            "executed_value": 0.0,
        }
    total_value = float(pd.to_numeric(df.get("total_value"), errors="coerce").fillna(0).sum())
    planning_remaining_value = float(_v2_diag_remaining_value_series(df).sum())
    executed_value = max(0.0, total_value - planning_remaining_value)
    return {
        "total_value": total_value,
        "planning_remaining_value": planning_remaining_value,
        "executed_value": executed_value,
    }


def _v2_row_identity_series(df: pd.DataFrame) -> pd.Series:
    return (
        df.get("project_code", pd.Series([""] * len(df))).astype(str).str.upper().str.strip()
        + "|"
        + df.get("facility", pd.Series([""] * len(df))).astype(str).str.upper().str.strip()
        + "|"
        + df.get("discipline", pd.Series([""] * len(df))).astype(str).str.upper().str.strip()
        + "|"
        + df.get("boq_code", pd.Series([""] * len(df))).astype(str).str.upper().str.strip()
    )


def _v2_invalid_exclusion_reason(row: pd.Series) -> str:
    unit_price = _v2_safe_num(row.get("unit_price"))
    total_value = _v2_safe_num(row.get("total_value"))
    rem_val = _v2_safe_num(_v2_diag_remaining_value_series(pd.DataFrame([row])).iloc[0])
    base = "invalid price/value (unit_price ≤ 0 и total_value ≤ 0)"
    if total_value > 0 or rem_val > 0:
        return f"{base} · ⚠ стоимость > 0 — проверить правило фильтрации"
    return base


def _v2_cost_rows_preview(df: pd.DataFrame, reason: str) -> pd.DataFrame:
    """Табличное представление строк с reason_excluded."""
    if df.empty:
        return pd.DataFrame()
    rem_qty = _v2_diag_remaining_qty_series(df)
    rem_val = _v2_diag_remaining_value_series(df)
    total_val = pd.to_numeric(df.get("total_value"), errors="coerce").fillna(0)
    exec_val = (total_val - rem_val).clip(lower=0)
    reasons = (
        df.apply(_v2_invalid_exclusion_reason, axis=1)
        if reason == "invalid price/value"
        else pd.Series([reason] * len(df), index=df.index)
    )
    return pd.DataFrame(
        {
            "project_code": df.get("project_code", pd.Series([""] * len(df))).astype(str),
            "facility": df.get("facility", pd.Series([""] * len(df))).astype(str),
            "discipline": df.get("discipline", pd.Series([""] * len(df))).astype(str),
            "boq_code": df.get("boq_code", pd.Series([""] * len(df))).astype(str),
            "boq_name": df.get("boq_name", pd.Series([""] * len(df))).astype(str),
            "unit_price": pd.to_numeric(df.get("unit_price"), errors="coerce").fillna(0),
            "total_qty": pd.to_numeric(df.get("total_qty"), errors="coerce").fillna(0),
            "total_value": total_val,
            "planning_remaining_qty": rem_qty,
            "planning_remaining_value": rem_val,
            "executed_value": exec_val,
            "reason_excluded": reasons.astype(str),
        }
    )


def _v2_sum_excluded_value(excluded_preview: pd.DataFrame, column: str) -> float:
    if excluded_preview.empty or column not in excluded_preview.columns:
        return 0.0
    return float(pd.to_numeric(excluded_preview[column], errors="coerce").fillna(0).sum())


def build_v2_cost_discrepancy_diagnostics(
    raw_df: pd.DataFrame,
    normalized_df: pd.DataFrame,
    filters: dict[str, str],
) -> dict[str, Any]:
    """Диагностика расхождения total_value / remaining / executed между v1 и v2."""
    cost_steps: list[dict[str, Any]] = []
    exclusion_frames: list[pd.DataFrame] = []
    loss_buckets: dict[str, float] = {
        "invalid": 0.0,
        "queue_title_discipline": 0.0,
        "project": 0.0,
    }

    def _append_step(label: str, frame: pd.DataFrame, *, rows: int | None = None) -> None:
        triplet = _v2_diag_cost_triplet(frame)
        cost_steps.append(
            {
                "Шаг": label,
                "Строк": rows if rows is not None else len(frame),
                **triplet,
            }
        )

    def _exclude(current: pd.DataFrame, removed: pd.DataFrame, reason: str, bucket: str | None) -> pd.DataFrame:
        if removed.empty:
            return current
        preview = _v2_cost_rows_preview(removed, reason)
        exclusion_frames.append(preview)
        if bucket:
            loss_buckets[bucket] += _v2_sum_excluded_value(preview, "total_value")
        return current.drop(index=removed.index, errors="ignore")

    current = normalized_df.copy()
    raw_triplet = _v2_diag_cost_triplet(current)
    _append_step("1. raw scope до любых исключений", current)

    if filters.get("project", "Все") != "Все":
        keep = current["project_code"].astype(str) == filters["project"]
        removed = current[~keep]
        current = _exclude(current, removed, "project filter", "project")
    _append_step("2. после фильтра проекта", current)

    if filters.get("queue", "Все") != "Все":
        keep = current["construction_queue"].astype(str) == filters["queue"]
        removed = current[~keep]
        current = _exclude(current, removed, "очередь filter", "queue_title_discipline")
    _append_step("3. после фильтра очереди", current)

    if filters.get("title", "Все") != "Все":
        keep = current["facility"].astype(str) == filters["title"]
        removed = current[~keep]
        current = _exclude(current, removed, "title/facility filter", "queue_title_discipline")
    _append_step("4. после фильтра титула", current)

    if filters.get("discipline", "Все") != "Все":
        keep = current["discipline"].astype(str) == filters["discipline"]
        removed = current[~keep]
        current = _exclude(current, removed, "discipline filter", "queue_title_discipline")
    _append_step("5. после фильтра дисциплины", current)

    before_invalid = current.copy()
    _append_step("6. до исключения invalid price/value", before_invalid)

    valid_mask = (before_invalid["unit_price"] > 0) | (before_invalid["total_value"] > 0)
    invalid_removed = before_invalid[~valid_mask]
    invalid_preview = _v2_cost_rows_preview(invalid_removed, "invalid price/value")
    if not invalid_preview.empty:
        exclusion_frames.append(invalid_preview)
    invalid_triplet = _v2_diag_cost_triplet(invalid_removed)
    loss_buckets["invalid"] = invalid_triplet["total_value"]
    cost_steps.append(
        {
            "Шаг": "7. сумма исключённых invalid строк",
            "Строк": len(invalid_removed),
            **invalid_triplet,
        }
    )

    after_invalid = before_invalid[valid_mask].copy()
    _append_step("8. после исключения invalid price/value", after_invalid)

    after_triplet = _v2_diag_cost_triplet(after_invalid)
    before_triplet = _v2_diag_cost_triplet(before_invalid)
    cost_steps.append(
        {
            "Шаг": "9. разница before invalid − after invalid",
            "Строк": len(before_invalid) - len(after_invalid),
            "total_value": before_triplet["total_value"] - after_triplet["total_value"],
            "planning_remaining_value": (
                before_triplet["planning_remaining_value"] - after_triplet["planning_remaining_value"]
            ),
            "executed_value": before_triplet["executed_value"] - after_triplet["executed_value"],
        }
    )

    all_excluded = (
        pd.concat(exclusion_frames, ignore_index=True)
        if exclusion_frames
        else pd.DataFrame()
    )
    if not all_excluded.empty:
        impact_mask = (all_excluded["total_value"] > 0) | (all_excluded["planning_remaining_value"] > 0)
        impact_rows = all_excluded[impact_mask].copy()
    else:
        impact_rows = pd.DataFrame()

    final_ids = set(_v2_row_identity_series(after_invalid))
    raw_ids = _v2_row_identity_series(normalized_df)
    missing_mask = ~raw_ids.isin(final_ids)
    missing_rows = normalized_df[missing_mask].copy()
    if not missing_rows.empty:
        missing_preview = _v2_cost_rows_preview(missing_rows, "отсутствует после фильтрации v2")
        missing_preview["abs_total_value"] = missing_preview["total_value"].abs()
        top_missing = missing_preview.sort_values("abs_total_value", ascending=False).head(50)
        top_missing = top_missing.drop(columns=["abs_total_value"])
    else:
        top_missing = pd.DataFrame()

    explained_total = (
        loss_buckets["invalid"]
        + loss_buckets["queue_title_discipline"]
        + loss_buckets["project"]
    )
    raw_to_final_delta = raw_triplet["total_value"] - after_triplet["total_value"]

    cost_steps_df = pd.DataFrame(cost_steps)
    if not cost_steps_df.empty:
        display = cost_steps_df.copy()
        for col in ("total_value", "planning_remaining_value", "executed_value"):
            display[col] = display[col].apply(lambda v: _format_rub(float(v)))
        cost_steps_df = display

    return {
        "cost_steps_df": cost_steps_df,
        "impact_rows_df": impact_rows,
        "top_missing_df": top_missing,
        "summary": {
            "loss_invalid": loss_buckets["invalid"],
            "loss_queue_title_discipline": loss_buckets["queue_title_discipline"],
            "loss_project": loss_buckets["project"],
            "explained_total": explained_total,
            "raw_to_final_delta": raw_to_final_delta,
            "raw_total_value": raw_triplet["total_value"],
            "final_total_value": after_triplet["total_value"],
        },
    }


def filter_invalid_v2_boq_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Исключить заголовки/разделы без цены и стоимости.
    Невалидно: unit_price <= 0 и total_value <= 0.
    """
    if df.empty:
        return df, 0
    valid_mask = (df["unit_price"] > 0) | (df["total_value"] > 0)
    excluded = int((~valid_mask).sum())
    return df[valid_mask].reset_index(drop=True), excluded


def calculate_v2_basic_scope_metrics(
    df: pd.DataFrame,
    source_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read-only production-расчёт остатка из view + fallback; без already_planned из БД."""
    source_cols = source_columns or list(df.columns)
    calc_meta: dict[str, Any] = {
        "uses_planning_remaining_from_view": False,
        "remaining_from_view_count": 0,
        "remaining_fallback_count": 0,
        "manual_adjustment_columns_present": [
            col for col in V2_MANUAL_ADJUSTMENT_VIEW_COLUMNS if col in source_cols
        ],
        "reconciliation_preview": pd.DataFrame(),
    }
    if df.empty:
        return pd.DataFrame(columns=V2_SCOPE_INTERNAL_COLUMNS), calc_meta

    out = df.copy() if "total_qty" in df.columns else normalize_v2_scope_df(df)
    calc_meta["uses_planning_remaining_from_view"] = bool(
        "_view_planning_remaining_qty" in out.columns
        and out["_view_planning_remaining_qty"].notna().any()
    )

    if "_view_planning_remaining_qty" not in out.columns:
        out["_view_planning_remaining_qty"] = out.get(
            "remaining_qty", pd.Series([float("nan")] * len(out), index=out.index)
        )

    view_remaining_qty = pd.to_numeric(out.get("remaining_qty"), errors="coerce")
    from_view_qty = view_remaining_qty.notna()
    out["_view_planning_remaining_qty"] = view_remaining_qty
    out["_remaining_qty_origin"] = from_view_qty.map({True: "view", False: "fallback"})

    # planning_remaining_qty из view — только для диагностики; расчёт availability ниже.
    out["already_planned_qty"] = 0.0
    out["planned_month"] = ""
    out["planned_at"] = ""
    out = _v2_merge_not_required_from_adjustments(out)
    out = _v2_apply_boq_availability_metrics(out)

    out["percent_executed"] = out.apply(
        lambda row: _v2_calculate_percent_executed_production(
            row["total_value"],
            row["executed_value"],
            row.get("effective_required_qty", row["total_qty"]),
            row.get("executed_total_qty", row["executed_qty"]),
        ),
        axis=1,
    )
    out["percent_remaining"] = (100.0 - out["percent_executed"]).clip(lower=0.0)
    out["status"] = out.apply(_v2_resolve_scope_status_row, axis=1)

    if "remaining_qty_source" not in out.columns:
        out["remaining_qty_source"] = ""
    out["remaining_qty_source"] = out["remaining_qty_source"].fillna("").astype(str).str.strip()

    v1_defaults = {
        "manual_executed_before_system": 0.0,
        "manual_adjustment_qty": 0.0,
        "manual_adjustment_reason": "",
        "manual_adjustment_comment": "",
        "manual_adjustment_updated_at": "",
        "manual_adjustment_source": "Не применялась",
        "not_required_qty": 0.0,
        "not_required_reason": "",
        "not_required_responsible_person": "",
        "not_required_comment": "",
        "not_required_updated_at": "",
        "effective_required_qty": 0.0,
        "norm_hours_per_unit": "-",
        "norm_type": "Не подключено",
        "productivity_history": "Не подключено",
    }
    for col, default in v1_defaults.items():
        if col not in out.columns:
            out[col] = default
        elif col in {
            "manual_executed_before_system",
            "manual_adjustment_qty",
            "not_required_qty",
            "effective_required_qty",
        }:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        elif col != "manual_adjustment_source":
            out[col] = out[col].replace("", default).fillna(default)

    if "manual_verified_remaining_qty" not in out.columns:
        out["manual_verified_remaining_qty"] = float("nan")

    out["manual_adjustment_source"] = out["remaining_qty_source"].apply(_v2_map_adjustment_source)

    calc_meta["remaining_from_view_count"] = int(from_view_qty.sum())
    calc_meta["remaining_fallback_count"] = int((~from_view_qty).sum())
    calc_meta["reconciliation_preview"] = _build_production_reconciliation_df(out)

    return out[V2_SCOPE_INTERNAL_COLUMNS], calc_meta


def _build_production_reconciliation_df(out: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Сверочная таблица production-полей для диагностики."""
    if out.empty:
        return pd.DataFrame()

    view_planning = out.get(
        "_view_planning_remaining_qty",
        pd.Series([float("nan")] * len(out), index=out.index),
    )

    def _view_qty_fmt(value: Any) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return _v2_format_qty_display_str(value)

    def _source_label(row: pd.Series) -> str:
        origin = str(row.get("_remaining_qty_origin") or "")
        source = str(row.get("remaining_qty_source") or "").strip()
        if source:
            return f"{origin} · {_v2_map_adjustment_source(source)}"
        return origin or "fallback"

    preview = pd.DataFrame(
        {
            "BOQ код": out["boq_code"].astype(str),
            "Всего": out["total_qty"].apply(_v2_format_qty_display_str),
            "Executed из view": out["executed_qty"].apply(_v2_format_qty_display_str),
            "Planning remaining из view": view_planning.apply(_view_qty_fmt),
            "Remaining в v2": out["remaining_qty"].apply(_v2_format_qty_display_str),
            "Источник остатка": out.apply(_source_label, axis=1),
            "Total value": out["total_value"].apply(_format_rub),
            "Remaining value": out["remaining_value"].apply(_format_rub),
            "Executed value": out["executed_value"].apply(_format_rub),
            "% освоения": out["percent_executed"].apply(_v2_format_percent_display_str),
        }
    )
    return preview.head(limit)


def _v2_display_text_column(series: pd.Series) -> pd.Series:
    """Текстовая колонка для UI: пусто / nan → «—»."""
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"": "—", "nan": "—", "None": "—", "<NA>": "—"})
    )


def map_v2_scope_to_ui_df(scoped_df: pd.DataFrame) -> pd.DataFrame:
    """Internal scoped dataframe → колонки рабочей таблицы Модуля 1."""
    if scoped_df.empty:
        return pd.DataFrame(columns=BOQ_SCOPE_TABLE_DISPLAY_COLUMNS)

    ui = pd.DataFrame(
        {
            "Проект": scoped_df["project_code"].astype(str),
            "Очередь": scoped_df["construction_queue"].astype(str).replace({"": "—"}),
            "Титул": scoped_df["facility"].astype(str),
            "Дисциплина": scoped_df["discipline"].astype(str),
            "Система": _v2_display_text_column(scoped_df["system"]),
            "IWP": _v2_display_text_column(scoped_df["iwp"]),
            "BOQ код": scoped_df["boq_code"].astype(str),
            "Наименование работ": scoped_df["boq_name"].astype(str),
            "Ед. изм.": scoped_df["unit"].astype(str).replace({"": "—"}),
            "Всего в объёме": scoped_df["total_qty"],
            "Выполнено в объёме": scoped_df["executed_total_qty"],
            "Ручная корректировка, объём": _v2_scope_table_manual_executed_qty_series(scoped_df),
            "Не освоим в объёме": _v2_scope_table_not_required_qty_series(scoped_df),
            "Доступно в объёме": scoped_df["available_to_add_qty"],
            "Всего в стоимости": _v2_safe_df_col(scoped_df, "total_value"),
            "Выполнено в стоимости": _v2_scope_table_executed_value_series(scoped_df),
            "Не освоим в стоимости": _v2_scope_table_not_required_value_series(scoped_df),
            "Превышение в стоимости": _v2_scope_table_overrun_value_series(scoped_df),
            "Стоимость доступного объёма": _v2_scope_available_value_series(scoped_df),
            "% исполнения": scoped_df["percent_executed"],
            "% остатка": scoped_df["percent_remaining"],
            "Причина корректировки": _v2_scope_adjustment_reason_column(scoped_df),
            "Статус": scoped_df["status"].astype(str),
        }
    )
    return ui[BOQ_SCOPE_TABLE_DISPLAY_COLUMNS]


def build_demo_boq_scope_df() -> pd.DataFrame:
    """Демо-данные BOQ Scope. Заменить на загрузку из monthly_scope_picker_view."""
    rows = [
        {
            "BOQ код": "BOQ-001",
            "Наименование работ": "Монтаж металлоконструкций",
            "Ед. изм.": "т",
            "Титул / объект": "Титул 1",
            "Дисциплина": "СМР",
            "Было": 1200.0,
            "Выполнено": 450.0,
            "Ручная корректировка": 0.0,
            "Остаток": 750.0,
            "Уже запланировано": 200.0,
            "Доступно к добавлению": 550.0,
            "Статус": "Частично запланировано",
        },
        {
            "BOQ код": "BOQ-014",
            "Наименование работ": "Прокладка кабельных линий",
            "Ед. изм.": "м",
            "Титул / объект": "Титул 2",
            "Дисциплина": "ЭМ",
            "Было": 8500.0,
            "Выполнено": 2100.0,
            "Ручная корректировка": -50.0,
            "Остаток": 6350.0,
            "Уже запланировано": 0.0,
            "Доступно к добавлению": 6350.0,
            "Статус": "Доступно",
        },
        {
            "BOQ код": "BOQ-027",
            "Наименование работ": "Настройка КИП",
            "Ед. изм.": "шт",
            "Титул / объект": "Объект К-100",
            "Дисциплина": "КИПиА",
            "Было": 320.0,
            "Выполнено": 320.0,
            "Ручная корректировка": 0.0,
            "Остаток": 0.0,
            "Уже запланировано": 0.0,
            "Доступно к добавлению": 0.0,
            "Статус": "Выполнено",
        },
        {
            "BOQ код": "BOQ-033",
            "Наименование работ": "Изоляция трубопроводов",
            "Ед. изм.": "м²",
            "Титул / объект": "Титул 1",
            "Дисциплина": "ТХ",
            "Было": 4200.0,
            "Выполнено": 900.0,
            "Ручная корректировка": 100.0,
            "Остаток": 3400.0,
            "Уже запланировано": 3400.0,
            "Доступно к добавлению": 0.0,
            "Статус": "Запланировано полностью",
        },
        {
            "BOQ код": "BOQ-041",
            "Наименование работ": "Бетонирование фундаментов",
            "Ед. изм.": "м³",
            "Титул / объект": "Титул 2",
            "Дисциплина": "СМР",
            "Было": 980.0,
            "Выполнено": 120.0,
            "Ручная корректировка": 0.0,
            "Остаток": 860.0,
            "Уже запланировано": 920.0,
            "Доступно к добавлению": 0.0,
            "Статус": "Перепланировано",
        },
        {
            "BOQ код": "BOQ-052",
            "Наименование работ": "Пусконаладочные работы",
            "Ед. изм.": "компл",
            "Титул / объект": "Объект К-100",
            "Дисциплина": "ЭМ",
            "Было": 12.0,
            "Выполнено": 2.0,
            "Ручная корректировка": 0.0,
            "Остаток": 10.0,
            "Уже запланировано": 3.0,
            "Доступно к добавлению": 7.0,
            "Статус": "Требует проверки",
        },
        {
            "BOQ код": "BOQ-058",
            "Наименование работ": "Монтаж щитового оборудования",
            "Ед. изм.": "шт",
            "Титул / объект": "Титул 1",
            "Дисциплина": "ЭМ",
            "Было": 64.0,
            "Выполнено": 10.0,
            "Ручная корректировка": 0.0,
            "Остаток": 54.0,
            "Уже запланировано": 0.0,
            "Доступно к добавлению": 54.0,
            "Статус": "Доступно",
        },
        {
            "BOQ код": "BOQ-071",
            "Наименование работ": "Гидроиспытания",
            "Ед. изм.": "уч",
            "Титул / объект": "Титул 2",
            "Дисциплина": "ТХ",
            "Было": 18.0,
            "Выполнено": 4.0,
            "Ручная корректировка": 0.0,
            "Остаток": 14.0,
            "Уже запланировано": 6.0,
            "Доступно к добавлению": 8.0,
            "Статус": "Частично запланировано",
        },
    ]
    df = pd.DataFrame(rows)
    return df


def prepare_scope_table_df(scope_df: pd.DataFrame) -> pd.DataFrame:
    """Упорядочивание колонок рабочей таблицы BOQ Scope."""
    if scope_df.empty:
        return pd.DataFrame(columns=BOQ_SCOPE_TABLE_DISPLAY_COLUMNS)
    out = scope_df.copy()
    for col in BOQ_SCOPE_TABLE_DISPLAY_COLUMNS:
        if col not in out.columns:
            if col in V2_SCOPE_QTY_COLUMNS or col in V2_SCOPE_COST_COLUMNS:
                out[col] = 0.0
            elif col in V2_SCOPE_PERCENT_COLUMNS:
                out[col] = 0.0
            else:
                out[col] = ""
    for col in V2_SCOPE_QTY_COLUMNS:
        if col in out.columns:
            out[col] = out[col].apply(_v2_round_display_qty)
    return out[BOQ_SCOPE_TABLE_DISPLAY_COLUMNS]


def compute_scope_kpi_metrics(scope_df: pd.DataFrame) -> dict[str, Any]:
    """Агрегаты среза из internal scoped или UI dataframe."""
    if scope_df.empty:
        return {
            "total_boq_codes": 0,
            "total_cost_rub": 0.0,
            "executed_rub": 0.0,
            "remaining_rub": 0.0,
            "available_qty": 0.0,
        }

    if "total_qty" in scope_df.columns:
        total_cost_rub = float(scope_df["total_value"].sum())
        remaining_rub = float(scope_df["remaining_value"].sum())
        executed_rub = max(0.0, total_cost_rub - remaining_rub)
        return {
            "total_boq_codes": len(scope_df),
            "total_cost_rub": total_cost_rub,
            "executed_rub": executed_rub,
            "remaining_rub": remaining_rub,
            "available_qty": float(scope_df["available_to_add_qty"].clip(lower=0).sum()),
        }

    legacy_numeric = {"Всего", "Остаток", "Доступно", "Уже в плане"}
    if legacy_numeric.intersection(scope_df.columns):
        return {
            "total_boq_codes": len(scope_df),
            "total_cost_rub": float(scope_df.get("Всего", pd.Series(dtype=float)).sum()),
            "executed_rub": float(scope_df.get("Выполнено", pd.Series(dtype=float)).sum()),
            "remaining_rub": float(scope_df.get("Остаток", pd.Series(dtype=float)).sum()),
            "available_qty": float(scope_df.get("Доступно", pd.Series(dtype=float)).sum()),
        }

    return {
        "total_boq_codes": len(scope_df),
        "total_cost_rub": float(scope_df["Было"].sum()),
        "executed_rub": float(scope_df["Выполнено"].sum()),
        "remaining_rub": float(scope_df["Остаток"].sum()),
        "available_qty": float(scope_df["Доступно к добавлению"].sum()),
    }


def _v2_project_filter_options(scoped_df: pd.DataFrame) -> list[str]:
    """Опции фильтра проекта — project_code; голый «БХК» не показывается."""
    if scoped_df.empty or "project_code" not in scoped_df.columns:
        return ["Все"]
    values = scoped_df["project_code"].dropna().astype(str).str.strip()
    unique = sorted({value for value in values if _v2_is_valid_project_filter_option(value)})
    return ["Все", *unique]


def _v2_filter_options(scoped_df: pd.DataFrame, column: str) -> list[str]:
    if scoped_df.empty or column not in scoped_df.columns:
        return ["Все"]
    values = scoped_df[column].dropna().astype(str).str.strip()
    unique = sorted({value for value in values if value and value != "—"})
    return ["Все", *unique]


def apply_scope_filters(scoped_df: pd.DataFrame, filters: dict[str, str]) -> pd.DataFrame:
    """Клиентская фильтрация internal scoped dataframe."""
    if scoped_df.empty:
        return scoped_df

    filtered = scoped_df.copy()
    if filters.get("project", "Все") != "Все":
        filtered = filtered[filtered["project_code"].astype(str) == filters["project"]]
    if filters.get("queue", "Все") != "Все":
        filtered = filtered[filtered["construction_queue"].astype(str) == filters["queue"]]
    if filters.get("title", "Все") != "Все":
        filtered = filtered[filtered["facility"].astype(str) == filters["title"]]
    if filters.get("discipline", "Все") != "Все":
        filtered = filtered[filtered["discipline"].astype(str) == filters["discipline"]]
    if filters.get("status", "Все") != "Все":
        filtered = filtered[filtered["status"].astype(str) == filters["status"]]

    search_boq = filters.get("search_boq", "").strip().lower()
    if search_boq:
        mask = (
            filtered["boq_code"].astype(str).str.lower().str.contains(search_boq, na=False)
            | filtered["boq_name"].astype(str).str.lower().str.contains(search_boq, na=False)
        )
        filtered = filtered[mask]

    search_iwp = filters.get("search_iwp", "").strip().lower()
    if search_iwp:
        filtered = filtered[
            filtered["iwp"].astype(str).str.lower().str.contains(search_iwp, na=False)
        ]

    search_system = filters.get("search_system", "").strip().lower()
    if search_system:
        filtered = filtered[
            filtered["system"].astype(str).str.lower().str.contains(search_system, na=False)
        ]

    return filtered.reset_index(drop=True)


def render_scope_module_header() -> None:
    """Заголовок модуля остатков и доступности."""
    st.markdown(
        f'<p class="constructor-v2-scope-module-title">{SCOPE_MODULE_TITLE}</p>',
        unsafe_allow_html=True,
    )


def _render_scope_kpi_card_html(label: str, value: str, hint: str, variant: str, icon: str) -> str:
    return f"""
<div class="v2-kpi-card v2-kpi-card--{variant}">
  <div class="v2-kpi-card-icon">{icon}</div>
  <div class="v2-kpi-card-body">
    <div class="v2-kpi-card-label">{label}</div>
    <div class="v2-kpi-card-value">{value}</div>
    <div class="v2-kpi-card-hint">{hint}</div>
  </div>
</div>
"""


def render_scope_kpi_cards(metrics: dict[str, Any]) -> None:
    """KPI-карточки среза — enterprise style."""
    cards_html = "".join(
        [
            _render_scope_kpi_card_html(
                "BOQ кодов",
                f"{metrics['total_boq_codes']:,}".replace(",", " "),
                "в выбранном срезе",
                "boq",
                "BOQ",
            ),
            _render_scope_kpi_card_html(
                "Бюджет среза",
                _format_rub(float(metrics["total_cost_rub"])),
                "общая стоимость",
                "budget",
                "₽",
            ),
            _render_scope_kpi_card_html(
                "Выполнено",
                _format_rub(float(metrics["executed_rub"])),
                "факт по срезу",
                "executed",
                "✓",
            ),
            _render_scope_kpi_card_html(
                "Остаток",
                _format_rub(float(metrics["remaining_rub"])),
                "к выполнению",
                "remaining",
                "◐",
            ),
            _render_scope_kpi_card_html(
                "Доступно",
                _format_qty(float(metrics["available_qty"])),
                "к планированию",
                "available",
                "＋",
            ),
        ]
    )
    st.markdown(f'<div class="v2-kpi-row">{cards_html}</div>', unsafe_allow_html=True)


def _v2_sync_filter_option(key: str, options: list[str]) -> None:
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = options[0]


def _v2_default_scope_filter_values() -> dict[str, str]:
    return {
        "v2_scope_planning_month": V2_PLANNING_MONTH_ALL,
        "v2_scope_project": "Все",
        "v2_scope_queue": "Все",
        "v2_scope_title": "Все",
        "v2_scope_discipline": "Все",
        "v2_scope_status": "Все",
        "v2_scope_search_boq": "",
        "v2_scope_search_iwp": "",
        "v2_scope_search_system": "",
    }


def _v2_restore_persisted_scope_filters() -> None:
    if not st.session_state.get("v2_scope_persist_filters"):
        return
    saved = st.session_state.get("v2_scope_filters_saved")
    if not isinstance(saved, dict):
        return
    for key in V2_SCOPE_FILTER_SESSION_KEYS:
        if key in saved:
            st.session_state[key] = saved[key]


def _v2_save_persisted_scope_filters() -> None:
    if st.session_state.get("v2_scope_persist_filters"):
        st.session_state["v2_scope_filters_saved"] = {
            key: st.session_state.get(key) for key in V2_SCOPE_FILTER_SESSION_KEYS
        }


def _v2_reset_scope_filters() -> None:
    for key, value in _v2_default_scope_filter_values().items():
        st.session_state[key] = value
    st.session_state["v2_scope_persist_filters"] = False
    st.session_state.pop("v2_scope_filters_saved", None)


def render_scope_filters(scoped_df: pd.DataFrame) -> dict[str, str]:
    """Компактная панель фильтров среза."""
    if st.session_state.pop("v2_scope_filters_reset_requested", False):
        _v2_reset_scope_filters()

    project_options = _v2_project_filter_options(scoped_df)
    queue_options = V2_QUEUE_FILTER_OPTIONS
    title_options = _v2_filter_options(scoped_df, "facility")
    discipline_options = _v2_filter_options(scoped_df, "discipline")
    status_options = _v2_filter_options(scoped_df, "status")

    _v2_sync_filter_option("v2_scope_planning_month", PLANNING_MONTH_OPTIONS)
    _v2_sync_filter_option("v2_scope_project", project_options)
    _v2_sync_filter_option("v2_scope_queue", queue_options)
    _v2_sync_filter_option("v2_scope_title", title_options)
    _v2_sync_filter_option("v2_scope_discipline", discipline_options)
    _v2_sync_filter_option("v2_scope_status", status_options)

    _v2_restore_persisted_scope_filters()

    st.markdown('<div class="v2-scope-filters">', unsafe_allow_html=True)
    with st.container(border=True):
        row1 = st.columns(6)
        with row1[0]:
            st.selectbox(
                "Месяц",
                PLANNING_MONTH_OPTIONS,
                key="v2_scope_planning_month",
            )
        with row1[1]:
            st.selectbox("Проект", project_options, key="v2_scope_project")
        with row1[2]:
            st.selectbox("Очередь", queue_options, key="v2_scope_queue")
        with row1[3]:
            st.selectbox("Титул", title_options, key="v2_scope_title")
        with row1[4]:
            st.selectbox("Дисциплина", discipline_options, key="v2_scope_discipline")
        with row1[5]:
            st.selectbox("Статус", status_options, key="v2_scope_status")

        row2 = st.columns([1.15, 1.15, 1.15, 0.95, 0.55])
        with row2[0]:
            st.text_input("Поиск BOQ", placeholder="Код / наименование", key="v2_scope_search_boq")
        with row2[1]:
            st.text_input("Поиск IWP", placeholder="IWP", key="v2_scope_search_iwp")
        with row2[2]:
            st.text_input("Поиск системы", placeholder="Система", key="v2_scope_search_system")
        with row2[3]:
            st.checkbox(
                "Сохранять фильтры в браузере",
                key="v2_scope_persist_filters",
            )
        with row2[4]:
            st.markdown('<div class="v2-scope-reset-btn">', unsafe_allow_html=True)
            if st.button("Сбросить фильтры", key="v2_scope_reset_filters", use_container_width=True):
                st.session_state["v2_scope_filters_reset_requested"] = True
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    _v2_save_persisted_scope_filters()

    return {
        "month": st.session_state.get("v2_scope_planning_month", ""),
        "project": st.session_state.get("v2_scope_project", "Все"),
        "queue": st.session_state.get("v2_scope_queue", "Все"),
        "title": st.session_state.get("v2_scope_title", "Все"),
        "discipline": st.session_state.get("v2_scope_discipline", "Все"),
        "status": st.session_state.get("v2_scope_status", "Все"),
        "search_boq": st.session_state.get("v2_scope_search_boq", ""),
        "search_iwp": st.session_state.get("v2_scope_search_iwp", ""),
        "search_system": st.session_state.get("v2_scope_search_system", ""),
    }


def render_scope_status_legend() -> None:
    """Компактная легенда статусов над таблицей BOQ."""
    badges_html = "".join(
        f'<span class="v2-scope-status-badge" style="background:{bg};color:{fg};">{label}</span>'
        for label, bg, fg in V2_SCOPE_STATUS_LEGEND
    )
    st.markdown(
        f'<div class="v2-scope-status-legend">{badges_html}</div>',
        unsafe_allow_html=True,
    )


def style_v2_scope_table(display_df: pd.DataFrame, selected_code: str | None = None) -> Any:
    """Цвет текста статуса в колонке «Статус» (без подсветки строк)."""
    del selected_code

    def _status_style(value: Any) -> str:
        key = str(value)
        return V2_SCOPE_TABLE_STATUS_TEXT_STYLES.get(
            key, V2_SCOPE_TABLE_STATUS_TEXT_DEFAULT
        )

    styler = display_df.style.map(_status_style, subset=["Статус"])
    for col in V2_SCOPE_COST_COLUMNS:
        if col in display_df.columns:
            styler = styler.set_properties(subset=[col], **{"text-align": "right", "white-space": "nowrap"})
    col_styles = [
        {
            "selector": f"thead th:nth-child({idx + 1}), tbody td:nth-child({idx + 1})",
            "props": [
                ("min-width", f"{width}px"),
                ("max-width", f"{width}px"),
            ],
        }
        for idx, width in enumerate(V2_SCOPE_COLUMN_WIDTHS_PX[: len(display_df.columns)])
    ]
    if "Наименование работ" in display_df.columns:
        name_idx = list(display_df.columns).index("Наименование работ")
        col_styles.append(
            {
                "selector": f"thead th:nth-child({name_idx + 1}), tbody td:nth-child({name_idx + 1})",
                "props": [
                    ("min-width", "320px"),
                    ("max-width", "420px"),
                    ("white-space", "nowrap"),
                ],
            }
        )
    for col_name, min_w, max_w in (
        ("Система", "160px", "220px"),
        ("IWP", "140px", "200px"),
        ("BOQ код", "120px", "160px"),
        ("Причина корректировки", "140px", "240px"),
    ):
        if col_name in display_df.columns:
            idx = list(display_df.columns).index(col_name)
            col_styles.append(
                {
                    "selector": f"thead th:nth-child({idx + 1}), tbody td:nth-child({idx + 1})",
                    "props": [
                        ("min-width", min_w),
                        ("max-width", max_w),
                    ],
                }
            )
    return styler.set_table_styles(col_styles, overwrite=False)


def _v2_build_scope_table_column_config(display_df: pd.DataFrame) -> dict[str, Any]:
    """Ширины колонок «Рабочий список BOQ» через st.column_config."""
    config: dict[str, Any] = {}
    for col in display_df.columns:
        width = V2_SCOPE_TABLE_COLUMN_WIDTHS.get(col)
        if width is not None:
            config[col] = st.column_config.TextColumn(col, width=width, disabled=True)
        else:
            config[col] = st.column_config.TextColumn(col, disabled=True)
    return config


def render_scope_table(ui_df: pd.DataFrame) -> pd.DataFrame:
    """Рабочий список BOQ: styled table + single-row selection."""
    if ui_df.empty:
        st.caption("По выбранным параметрам среза строк не найдено.")
        return ui_df

    display_df = _v2_format_scope_table_display(prepare_scope_table_df(ui_df.copy()))
    selected_code = st.session_state.get("v2_scope_selected_boq_code")
    table_height = max(600, min(36 * len(display_df) + 38, 900))

    st.markdown('<div class="v2-scope-boq-table">', unsafe_allow_html=True)
    table_event = st.dataframe(
        style_v2_scope_table(display_df, selected_code),
        use_container_width=True,
        hide_index=True,
        height=table_height,
        on_select="rerun",
        selection_mode="single-row",
        column_config=_v2_build_scope_table_column_config(display_df),
        key="v2_scope_table_view",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    selection_rows = getattr(getattr(table_event, "selection", None), "rows", None) or []
    if selection_rows and not display_df.empty:
        selected_idx = int(selection_rows[0])
        if 0 <= selected_idx < len(display_df):
            st.session_state.v2_scope_selected_boq_code = str(
                display_df.iloc[selected_idx]["BOQ код"]
            )
        else:
            st.session_state.v2_scope_selected_boq_code = ""
            st.caption("Выбор строки сброшен: список BOQ был обновлён.")

    return ui_df


def _v2_status_badge_html(status: str) -> str:
    style = V2_SCOPE_STATUS_STYLES.get(
        status,
        V2_SCOPE_STATUS_STYLES.get("Нет остатка", "background-color: #F3F4F6; color: #5B6470;"),
    )
    return f'<span class="v2-boq-status-badge" style="{style}">{status}</span>'


def _v2_detail_metric_html(label: str, value: str) -> str:
    return (
        f'<div class="v2-boq-detail-metric"><span>{label}</span>'
        f"<strong>{value}</strong></div>"
    )


def _scope_decision_message(
    status: str,
    available_qty: float,
    remaining_qty: float,
) -> tuple[str, str]:
    """Управленческий вывод: (текст, tone: positive | warning | muted)."""
    if status == V2_SCOPE_STATUS_OVERRUN:
        return (
            "Факт превышает BOQ. Требуется проверка Daily Progress / BOQ / допработ.",
            "warning",
        )
    if status == V2_SCOPE_STATUS_NOT_REQUIRED:
        return "Остаток исключён из выполнения. Планирование недоступно.", "muted"
    if status == "Требует проверки":
        return "Требуется проверка корректировок и исходных данных", "warning"
    if status == "Перепланировано" or remaining_qty < 0:
        return "Требуется проверка: объём запланирован сверх остатка", "warning"
    if status == "Выполнено" or available_qty <= 0:
        return "Нет доступного остатка для планирования", "muted"
    if status == "Доступно" or available_qty > 0:
        return "Можно добавить в месячный план", "positive"
    return "Нет доступного остатка для планирования", "muted"


def _v2_get_selected_scope_item(scoped_df: pd.DataFrame) -> pd.Series | None:
    selected_code = st.session_state.get("v2_scope_selected_boq_code")
    if not selected_code:
        return None
    row = scoped_df[scoped_df["boq_code"].astype(str) == str(selected_code)]
    if row.empty:
        return None
    return row.iloc[0]


def render_selected_boq_card(scoped_df: pd.DataFrame) -> None:
    """Enterprise detail panel выбранного BOQ-кода."""
    selected_code = st.session_state.get("v2_scope_selected_boq_code")

    if not selected_code:
        st.caption("Выберите строку в рабочем списке для просмотра деталей.")
        return

    row = scoped_df[scoped_df["boq_code"].astype(str) == str(selected_code)]
    if row.empty:
        st.caption("Выбранный BOQ-код не найден в текущем срезе.")
        return

    item = row.iloc[0]
    status = str(item["status"])

    with st.container(border=True):
        st.markdown('<div class="v2-boq-detail-panel">', unsafe_allow_html=True)

        header_left, header_right = st.columns([4, 1])
        with header_left:
            st.markdown(
                f'<p class="v2-boq-detail-code">{item["boq_code"]}</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<p class="v2-boq-detail-name">{item["boq_name"]}</p>',
                unsafe_allow_html=True,
            )
            unit_text = str(item.get("unit") or "—").strip() or "—"
            st.markdown(
                f'<p class="v2-boq-detail-volume">'
                f'{_v2_format_qty_display_str(item.get("total_qty"))}'
                f'<span class="v2-boq-detail-volume-unit">{unit_text}</span>'
                f"</p>",
                unsafe_allow_html=True,
            )
        with header_right:
            st.markdown(_v2_status_badge_html(status), unsafe_allow_html=True)

        context = " · ".join(
            [
                str(item["project_code"] or "—"),
                str(item["construction_queue"] or "—"),
                str(item["facility"] or "—"),
                str(item["discipline"] or "—"),
                _v2_display_text_column(pd.Series([item.get("system")])).iloc[0],
                _v2_display_text_column(pd.Series([item.get("iwp")])).iloc[0],
            ]
        )
        st.markdown(
            f'<p class="v2-boq-detail-context">{context}</p>',
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown(_v2_render_boq_volume_acquisition_html(item), unsafe_allow_html=True)

        message, tone = _scope_decision_message(
            status,
            _v2_safe_num(item["available_to_add_qty"]),
            _v2_safe_num(item["remaining_qty"]),
        )
        st.markdown(
            f'<span class="v2-boq-decision-badge {tone}">{message}</span>',
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)


def render_scope_data_diagnostics(
    load_meta: dict[str, Any],
    raw_df: pd.DataFrame,
    scoped_df: pd.DataFrame,
    calc_meta: dict[str, Any] | None = None,
    *,
    normalized_df: pd.DataFrame | None = None,
    filters: dict[str, str] | None = None,
    filtered_scoped_df: pd.DataFrame | None = None,
) -> None:
    """Диагностика read-only источника данных Модуля 1."""
    calc_meta = calc_meta or {}
    filters = filters or {}
    with st.expander("Диагностика источника данных", expanded=False):
        st.markdown(f"**Источник:** `{load_meta.get('source', '—')}`")
        st.markdown(f"**Всего строк из источника:** {load_meta.get('row_count', len(raw_df))}")
        st.markdown(
            f"**Исключено невалидных строк (без цены/стоимости):** "
            f"{load_meta.get('excluded_invalid', 0)}"
        )
        st.markdown(f"**Рабочих BOQ после фильтрации:** {load_meta.get('working_rows', len(scoped_df))}")
        if load_meta.get("error"):
            st.caption(f"Ошибка загрузки: {load_meta['error']}")

        uses_view_remaining = calc_meta.get("uses_planning_remaining_from_view", False)
        st.markdown(
            f"**planning_remaining_qty из view:** "
            f"{'да' if uses_view_remaining else 'нет (fallback total − executed)'}"
        )
        st.markdown(
            f"**Строк с remaining из view:** {calc_meta.get('remaining_from_view_count', 0)} · "
            f"**fallback:** {calc_meta.get('remaining_fallback_count', 0)}"
        )

        manual_cols = calc_meta.get("manual_adjustment_columns_present") or []
        st.markdown("**Колонки view для manual adjustments:**")
        if manual_cols:
            st.code(", ".join(manual_cols))
        else:
            st.caption("Колонки manual adjustments в источнике не обнаружены.")

        columns = load_meta.get("columns") or list(raw_df.columns)
        st.markdown("**Колонки dataframe источника:**")
        st.code(", ".join(columns) if columns else "—")

        if not scoped_df.empty and "project_code" in scoped_df.columns:
            projects = sorted(
                {str(v).strip() for v in scoped_df["project_code"].dropna() if str(v).strip()}
            )
            st.markdown("**Уникальные project_code в рабочем срезе:**")
            st.code(", ".join(projects) if projects else "—")

        reconciliation = calc_meta.get("reconciliation_preview")
        if isinstance(reconciliation, pd.DataFrame) and not reconciliation.empty:
            st.markdown("**Сверка production-полей**")
            st.dataframe(reconciliation, use_container_width=True, hide_index=True)

        if normalized_df is not None:
            st.markdown("---")
            st.markdown("**Сверка фильтрации v1/v2**")
            filter_diag = build_v1_v2_filter_diagnostics(raw_df, normalized_df, filters)
            st.caption(filter_diag.get("actual_v2_pipeline_note", ""))

            if filtered_scoped_df is not None:
                st.markdown(
                    f"**Фактический KPI v2 (текущие фильтры):** "
                    f"{len(filtered_scoped_df)} кодов · "
                    f"бюджет {_format_rub(float(filtered_scoped_df['total_value'].sum())) if not filtered_scoped_df.empty else '0 ₽'} · "
                    f"остаток {_format_rub(float(filtered_scoped_df['remaining_value'].sum())) if not filtered_scoped_df.empty else '0 ₽'}"
                )

            steps_df = filter_diag.get("steps_df")
            if isinstance(steps_df, pd.DataFrame) and not steps_df.empty:
                st.dataframe(steps_df, use_container_width=True, hide_index=True)

            lost = filter_diag.get("excluded_lost") or {}
            st.caption(
                "Потери на invalid price/value (unit_price ≤ 0 **и** total_value ≤ 0): "
                f"{lost.get('rows', 0)} строк · "
                f"{_format_rub(float(lost.get('total_value', 0)))} · "
                f"остаток {_format_rub(float(lost.get('remaining_value', 0)))} · "
                f"объём {_v2_format_qty_display_str(lost.get('remaining_qty', 0))}"
            )

            queue_filter = filter_diag.get("queue_filter", "Все")
            if queue_filter != "Все":
                st.caption(
                    f"Очередь «{queue_filter}»: v2 substring/derived = {filter_diag.get('v2_queue_rows', 0)} строк · "
                    f"v1 exact facility match = {filter_diag.get('v1_queue_rows', 0)} строк"
                )

            extra_filters = []
            if filters.get("status", "Все") != "Все":
                extra_filters.append(f"status={filters['status']}")
            if filters.get("search_boq", "").strip():
                extra_filters.append("search_boq")
            if filters.get("search_iwp", "").strip():
                extra_filters.append("search_iwp")
            if filters.get("search_system", "").strip():
                extra_filters.append("search_system")
            if extra_filters:
                st.caption(
                    "Дополнительные фильтры v2 (отсутствуют в v1): "
                    + ", ".join(extra_filters)
                )

            unique_labels = filter_diag.get("unique_labels") or {}
            st.markdown("**Уникальные project_code / project_name / facility (raw view):**")
            for label, values in unique_labels.items():
                bhk_hits = [v for v in values if _v2_is_bare_bhk_project_label(v)]
                st.markdown(f"- `{label}` ({len(values)}): {', '.join(values[:30])}{'…' if len(values) > 30 else ''}")
                if bhk_hits:
                    st.caption(f"  ℹ `{label}` содержит голый «БХК» (не PRJ-код): {', '.join(bhk_hits)}")

            bhk_diag = filter_diag.get("bhk_project_name_diag") or {}
            st.markdown("**БХК в project_name / проверка нормализации проекта**")
            st.caption(
                "Строки не удаляются из scope; голый «БХК» скрыт только в dropdown «Проект»."
            )
            st.markdown(
                f"- Строк с `project_name = БХК`: **{bhk_diag.get('rows_project_name_bhk', 0)}**\n"
                f"- Из них с `project_code = PRJ-001-БХК` (варианты): "
                f"**{bhk_diag.get('rows_with_prj_code', 0)}**\n"
                f"- Из них с пустым `project_code`: "
                f"**{bhk_diag.get('rows_empty_project_code', 0)}**\n"
                f"- Сумма `total_value` по строкам с `project_name = БХК`: "
                f"**{_format_rub(float(bhk_diag.get('total_value_project_name_bhk', 0)))}**"
            )
            missing_code_rows = bhk_diag.get("project_code_missing_rows")
            if isinstance(missing_code_rows, pd.DataFrame) and not missing_code_rows.empty:
                st.markdown("**Строки `project_code_missing` (project_name = БХК, код пустой)**")
                st.dataframe(missing_code_rows, use_container_width=True, hide_index=True)

            excluded_preview = filter_diag.get("excluded_preview")
            if isinstance(excluded_preview, pd.DataFrame) and not excluded_preview.empty:
                st.markdown("**Исключённые строки (invalid price/value), первые 100**")
                st.dataframe(excluded_preview, use_container_width=True, hide_index=True)
            else:
                st.caption("Исключённых строк по правилу invalid price/value не найдено.")

            st.markdown("---")
            st.markdown("**Проверка расхождения стоимости**")
            cost_diag = build_v2_cost_discrepancy_diagnostics(raw_df, normalized_df, filters)
            cost_steps_df = cost_diag.get("cost_steps_df")
            if isinstance(cost_steps_df, pd.DataFrame) and not cost_steps_df.empty:
                st.dataframe(cost_steps_df, use_container_width=True, hide_index=True)

            impact_rows = cost_diag.get("impact_rows_df")
            if isinstance(impact_rows, pd.DataFrame) and not impact_rows.empty:
                st.markdown("**Строки, влияющие на расхождение стоимости**")
                st.caption(
                    "Строки, исключённые из v2, у которых total_value > 0 "
                    "или planning_remaining_value > 0."
                )
                st.dataframe(impact_rows, use_container_width=True, hide_index=True)
            else:
                st.caption(
                    "Нет исключённых строк с total_value > 0 или planning_remaining_value > 0."
                )

            top_missing = cost_diag.get("top_missing_df")
            if isinstance(top_missing, pd.DataFrame) and not top_missing.empty:
                st.markdown("**Top строк по стоимости, которые есть до фильтра, но отсутствуют после фильтра**")
                st.dataframe(top_missing, use_container_width=True, hide_index=True)

            summary = cost_diag.get("summary") or {}
            loss_filters = (
                float(summary.get("loss_queue_title_discipline", 0))
                + float(summary.get("loss_project", 0))
            )
            st.markdown("**Summary расхождения стоимости**")
            st.markdown(
                f"- Потеря от invalid exclusion: {_format_rub(float(summary.get('loss_invalid', 0)))}\n"
                f"- Потеря от очереди/title/discipline/project filter: {_format_rub(loss_filters)}\n"
                f"- Итого объяснённая разница: {_format_rub(float(summary.get('explained_total', 0)))}"
            )
            st.caption(
                f"raw total → final total: "
                f"{_format_rub(float(summary.get('raw_total_value', 0)))} → "
                f"{_format_rub(float(summary.get('final_total_value', 0)))} "
                f"(delta {_format_rub(float(summary.get('raw_to_final_delta', 0)))})"
            )


def render_scope_calc_architecture() -> None:
    """Свернутый блок логики расчёта остатка."""
    with st.expander("Архитектура расчёта остатка", expanded=False):
        st.markdown(
            f"**Источник данных:**  \n"
            f"`{V2_SCOPE_VIEW}`"
        )
        st.markdown(
            "**Основная логика:**  \n\n"
            "**Всего:**  \n"
            "`total_project_qty`  \n\n"
            "**Факт из Daily Progress:**  \n"
            "`executed_qty_all_time`  \n\n"
            "**Ручная корректировка ранее выполненного объёма:**  \n"
            "`manual_executed_before_system`  \n\n"
            "**Подтверждённый остаток вручную:**  \n"
            "`manual_verified_remaining_qty`  \n\n"
            "**Production-остаток:**  \n"
            "`planning_remaining_qty`  \n\n"
            "**Стоимость остатка:**  \n"
            "`planning_remaining_value`"
        )
        st.markdown(
            "**Логика:**  \n\n"
            "Если задан `manual_verified_remaining_qty`:  \n"
            "&nbsp;&nbsp;&nbsp;&nbsp;**Остаток** = `manual_verified_remaining_qty`  \n\n"
            "Иначе:  \n"
            "&nbsp;&nbsp;&nbsp;&nbsp;**Остаток** = "
            "`total_project_qty` − `executed_qty_all_time` − `manual_executed_before_system`"
        )
        st.markdown(
            "**В v2:**  \n"
            "`remaining_qty` = `planning_remaining_qty` из `monthly_scope_picker_view`"
        )
        st.caption(
            "Диагностика сверки временно отключена из рабочего интерфейса. "
            "При необходимости её можно вернуть для технического анализа."
        )


def render_module_boq_scope() -> None:
    """Модуль 1: остатки и доступность к планированию."""
    raw_df, load_meta = load_v2_boq_scope_from_supabase()
    if load_meta.get("is_fallback"):
        st.warning(
            "Supabase недоступна или загрузка scope не удалась. "
            "Показан demo fallback. Детали — в «Диагностика источника данных»."
        )
    elif raw_df.empty:
        st.warning(
            f"Витрина `{V2_SCOPE_VIEW}` пуста. Проверьте SQL view и данные BOQ master."
        )

    normalized_df = normalize_v2_scope_df(raw_df)
    valid_df, excluded_invalid = filter_invalid_v2_boq_rows(normalized_df)
    scoped_df, calc_meta = calculate_v2_basic_scope_metrics(
        valid_df,
        source_columns=load_meta.get("columns"),
    )
    _v2_sync_filter_option("v2_scope_planning_month", PLANNING_MONTH_OPTIONS)
    planning_month = _v2_resolve_planning_month_key(
        str(st.session_state.get("v2_scope_planning_month") or "").strip()
    )
    if planning_month:
        scoped_df = apply_v2_session_draft_reservation(scoped_df, planning_month)
    load_meta["excluded_invalid"] = excluded_invalid
    load_meta["working_rows"] = len(scoped_df)
    load_meta["calc"] = calc_meta

    filters = render_scope_filters(scoped_df)
    filtered_scoped = apply_scope_filters(scoped_df, filters)
    ui_df = map_v2_scope_to_ui_df(filtered_scoped)

    render_scope_kpi_cards(compute_scope_kpi_metrics(filtered_scoped))

    selected_item = _v2_get_selected_scope_item(filtered_scoped)

    with st.expander("Рабочий список BOQ-кодов", expanded=True):
        render_scope_table(ui_df)

    with st.expander(
        "Детализация выбранного BOQ",
        expanded=selected_item is not None,
    ):
        render_selected_boq_card(filtered_scoped)

    with st.expander("Корректировка остатка", expanded=False):
        if selected_item is None:
            st.caption("Выберите BOQ в рабочем списке.")
        else:
            _render_residual_adjustment_content(selected_item)

    with st.expander("Добавить код", expanded=False):
        if selected_item is None:
            st.caption("Выберите BOQ в рабочем списке.")
        else:
            _render_add_to_month_plan_content(selected_item)


def render_module_add_boq() -> None:
    """Модуль 2: добавление BOQ в месячный план."""
    st.markdown(
        '<p class="constructor-v2-module-hint">'
        "Модуль предназначен для формирования новых строк месячного плана."
        "</p>",
        unsafe_allow_html=True,
    )

    st.text_input("Выбранный BOQ-код", value="", disabled=True, key="v2_selected_boq")
    c1, c2 = st.columns(2)
    with c1:
        st.number_input(
            "Объём планирования",
            min_value=0.0,
            value=0.0,
            step=0.01,
            disabled=True,
            key="v2_plan_qty",
        )
        st.selectbox("Звено / crew", ["—"], disabled=True, key="v2_plan_crew")
    with c2:
        st.selectbox(
            "Норма трудозатрат",
            ["Реалистичная (P50)", "Осторожная (P80)", "Ручная"],
            disabled=True,
            key="v2_plan_norm",
        )
        st.text_area("Комментарий", value="", disabled=True, key="v2_plan_comment", height=88)

    st.button(
        "Добавить в месячный план",
        type="primary",
        disabled=True,
        key="v2_add_to_plan",
        help="Кнопка будет активирована после подключения модуля добавления.",
    )


def render_module_month_plan() -> None:
    """Модуль 3: реестр строк месячного плана (session + monthly_plan_lines_v2)."""
    st.markdown(
        '<p class="constructor-v2-module-hint">'
        "Строки загружаются автоматически при выборе проекта и месяца. "
        "Выберите строки в таблице для действий."
        "</p>",
        unsafe_allow_html=True,
    )

    scope = _v2_resolve_draft_scope()
    if not scope:
        st.caption(
            "Выберите конкретный проект (не «Все») и месяц (не «Все месяца») "
            "в фильтрах Scope."
        )
        return

    project_code, month_key = scope
    hydrate_v2_month_plan_if_needed(project_code, month_key)
    render_v2_draft_autosave_status_bar(project_code, month_key)
    items = _v2_filter_items_for_scope(load_v2_session_draft_items(), project_code, month_key)

    sorted_items = _v2_plan_sort_items(items)
    registry_filters = render_v2_plan_registry_filters(sorted_items)

    if not items:
        st.info("Для выбранного месяца пока нет строк месячного плана.")
        return

    filtered_items = _v2_apply_plan_registry_filters(sorted_items, registry_filters)
    selected_keys: list[str] = list(st.session_state.get(V2_PLAN_SELECTED_KEYS) or [])

    active_filters = [
        label
        for label, key in (
            ("Проект", "project"),
            ("Очередь", "queue"),
            ("Титул", "title"),
            ("Дисциплина", "discipline"),
            ("Система", "system"),
            ("IWP", "iwp"),
            ("Звено", "crew"),
            ("BOQ-код", "boq"),
        )
        if str(registry_filters.get(key) or "Все") != "Все"
    ]
    if active_filters:
        st.caption(
            f"Срез реестра: {len(filtered_items)} из {len(sorted_items)} строк "
            f"({', '.join(active_filters)})."
        )

    kpis = compute_v2_month_plan_kpis(filtered_items)
    st.markdown('<div class="v2-month-plan-kpi-bar">', unsafe_allow_html=True)
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Строк в плане", f"{kpis['total_lines']:,}".replace(",", " "))
    m2.metric("Несохранённые", f"{kpis['new_lines']:,}".replace(",", " "))
    m3.metric("Плановая стоимость работ", _format_rub(float(kpis["plan_value_rub"])))
    m4.metric("Трудозатраты, чел·ч", _v2_format_qty_display_str(kpis["required_hours"]))
    m5.metric("Стоимость труда", _format_rub(float(kpis["labor_cost_rub"])))
    with m6:
        st.markdown(
            f'<div class="v2-month-plan-kpi-fte-wrap" title="{V2_FTE_FUND_HELP}">'
            f'<div class="v2-month-plan-kpi-fte-head">'
            f'<span class="v2-month-plan-kpi-fte-label">Расчётная потребность в персонале</span>'
            f'<span class="v2-month-plan-kpi-fund-inline">{V2_FTE_FUND_LABEL}</span>'
            f"</div>"
            f'<p class="v2-month-plan-kpi-fte-value">'
            f"{_v2_format_staffing_need_display(float(kpis['fte_required']))}"
            f"</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
    st.markdown('<div class="v2-month-plan-kpi-bar-row2">', unsafe_allow_html=True)
    k7, k8, k9 = st.columns(3)
    k7.metric(
        "Стоимость труда / Стоимость работ, %",
        _v2_format_labor_to_plan_pct_display(
            float(kpis["labor_to_plan_pct"]),
            float(kpis["plan_value_rub"]),
        ),
    )
    k8.metric("Экономически опасных строк", f"{kpis['risky_lines']:,}".replace(",", " "))
    with k9:
        st.caption(
            "Расчётная продолжительность при текущем составе — "
            "будет добавлена после модели календарного графика "
            "(sum crew_size по строкам некорректен)."
        )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if not filtered_items:
        st.info("По выбранным фильтрам реестра строк не найдено.")
        render_v2_plan_action_bar(
            project_code, month_key, items, selected_keys, bar_key_suffix="main"
        )
        return

    edit_row_key = str(st.session_state.get(V2_PLAN_EDIT_ROW_KEY) or "").strip()
    if edit_row_key:
        edit_item = _v2_find_plan_item_by_key(items, edit_row_key)
        if edit_item and str(edit_item.get("status") or V2_PLAN_STATUS_NOT_SENT) == V2_PLAN_STATUS_NOT_SENT:
            render_v2_plan_edit_panel(edit_item)
        else:
            st.session_state[V2_PLAN_EDIT_ROW_KEY] = ""

    display_df = map_v2_session_draft_to_display_df(filtered_items)
    labor_cost_warnings = [
        _v2_plan_labor_cost_exceeds_plan_value(item) for item in filtered_items
    ]
    table_height = max(600, min(36 * len(display_df) + 38, 900))
    st.markdown('<div class="v2-month-plan-table">', unsafe_allow_html=True)
    table_event = st.dataframe(
        style_v2_month_plan_table(display_df, labor_cost_warnings=labor_cost_warnings),
        use_container_width=True,
        hide_index=True,
        height=table_height,
        on_select="rerun",
        selection_mode="multi-row",
        key="v2_month_plan_table_select",
        column_config={
            "Стоимость труда": st.column_config.TextColumn(
                "Стоимость труда",
                help=V2_PLAN_LABOR_COST_COLUMN_HELP,
            ),
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)

    selection_rows = getattr(getattr(table_event, "selection", None), "rows", None) or []
    selected_keys = [
        _v2_plan_row_key(filtered_items[row_idx])
        for row_idx in selection_rows
        if 0 <= row_idx < len(filtered_items)
    ]
    st.session_state[V2_PLAN_SELECTED_KEYS] = selected_keys

    render_v2_plan_action_bar(
        project_code, month_key, items, selected_keys, bar_key_suffix="main"
    )


def render_module_plan_actions() -> None:
    """Legacy: действия перенесены в реестр строк месячного плана."""
    st.caption(f"Действия с планом — в блоке «{MONTH_PLAN_REGISTRY_TITLE}» выше.")


def main() -> None:
    inject_page_styles()
    init_v2_session_state()
    scope = _v2_resolve_draft_scope()
    if scope:
        hydrate_v2_month_plan_if_needed(*scope)
    render_page_header()

    with st.expander("📊 Остатки и доступность к планированию", expanded=False):
        render_module_boq_scope()

    with st.expander(f"📋 {MONTH_PLAN_REGISTRY_TITLE}", expanded=False):
        render_module_month_plan()

    with st.expander("📥 Загрузка исходных данных", expanded=False):
        render_module_upload_inputs()


# --- Точка входа Streamlit ---
st.set_page_config(
    page_title="Конструктор месячного плана",
    layout="wide",
    initial_sidebar_state="expanded",
)

main()
