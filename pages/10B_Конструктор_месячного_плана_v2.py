# ============================================================
# Конструктор месячного плана v2 — каркас страницы
# Production: pages/10_Planning_Конструктор_месячного_плана.py (не изменять)
# ============================================================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from services.monthly_scope_adjustments import (
    delete_adjustment,
    fetch_adjustments_history_for_boq,
    load_adjustments,
    load_scope,
    save_adjustment,
)

# --- Константы UI (заглушки, без бизнес-логики) ---

PAGE_TITLE = "Конструктор месячного плана v2"

SCOPE_MODULE_TITLE = "Остатки и доступность к планированию"
SCOPE_MODULE_SUBTITLE = (
    "Контроль остатка работ, освоения и доступности к месячному планированию."
)

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

BOQ_SCOPE_TABLE_DISPLAY_COLUMNS = [
    "Выбор",
    "Проект",
    "Очередь",
    "Титул",
    "Дисциплина",
    "Система",
    "IWP",
    "Код",
    "Наименование работ",
    "Ед. изм.",
    "Всего",
    "Выполнено",
    "Остаток",
    "% освоения",
    "Уже в плане",
    "Месяц планирования",
    "Дата планирования",
    "Доступно",
    "Статус",
]

V2_PRJ_BHK_CODE_MARKERS = ("PRJ-001-БХК", "PRJ-001-BHK", "PRJ_001_БХК", "PRJ_001_BHK")
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
V2_SCOPE_QTY_COLUMNS = {"Всего", "Выполнено", "Остаток", "Уже в плане", "Доступно"}

V2_SCOPE_STATUS_STYLES = {
    "Доступно": "background-color: #E8F3EA; color: #2F5E3A; border: 1px solid #C5DEC9;",
    "Частично запланировано": "background-color: #E8EEF7; color: #2E4A6E; border: 1px solid #C8D7EA;",
    "Запланировано полностью": "background-color: #E2E8F0; color: #1E3A5F; border: 1px solid #CBD5E1;",
    "Выполнено": "background-color: #F1F5F9; color: #475569; border: 1px solid #E2E8F0;",
    "Перепланировано": "background-color: #F9EDE6; color: #8B4A32; border: 1px solid #E8C9B8;",
    "Требует проверки": "background-color: #FEF6E7; color: #92600A; border: 1px solid #F3DEAA;",
    "Нет остатка": "background-color: #F8FAFC; color: #64748B; border: 1px solid #E2E8F0;",
}

V2_SCOPE_COLUMN_WIDTHS_PX = [
    32, 85, 78, 72, 98, 112, 92, 102, 360, 48, 78, 82, 82, 52, 58, 108, 118, 82, 112,
]

V2_PROGRESS_COLOR_EXECUTED = "#2E5B9A"
V2_PROGRESS_COLOR_REMAINING = "#C97A5C"
V2_PROGRESS_COLOR_AVAILABLE = "#6BAA75"

V2_SCOPE_STATUS_LEGEND = [
    ("Доступно", "#E8F3EA", "#2F5E3A"),
    ("Частично", "#E8EEF7", "#2E4A6E"),
    ("Полностью", "#E2E8F0", "#1E3A5F"),
    ("Выполнено", "#F1F5F9", "#475569"),
    ("Перепланировано", "#F9EDE6", "#8B4A32"),
    ("Проверка", "#FEF6E7", "#92600A"),
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

V2_DRAFT_ITEMS_KEY = "v2_month_plan_draft_items"
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
    "remaining_qty",
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
]

V2_SCOPE_NUMERIC_FIELDS = {
    "total_qty",
    "executed_qty",
    "remaining_qty",
    "already_planned_qty",
    "available_to_add_qty",
    "unit_price",
    "total_value",
    "remaining_value",
    "executed_value",
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
    "Дата добавления",
    "Статус",
    "Месяц",
    "BOQ код",
    "Наименование",
    "Объём",
    "Ед.",
    "Звено",
    "Людей",
    "Норма",
    "Трудозатраты",
    "Длительность",
    "Стоимость объёма",
    "Стоимость труда",
    "Комментарий",
]

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
        .v2-scope-boq-table [data-testid="stDataFrame"] {
            font-size: 0.84rem;
        }
        .v2-scope-boq-table [data-testid="stDataFrame"] td,
        .v2-scope-boq-table [data-testid="stDataFrame"] th {
            padding: 0.28rem 0.45rem !important;
            white-space: nowrap;
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header() -> None:
    st.markdown(f'<h1 class="constructor-v2-header">{PAGE_TITLE}</h1>', unsafe_allow_html=True)


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


def _v2_pick_series(df: pd.DataFrame, field: str, default: Any = "") -> pd.Series:
    for col in V2_SCOPE_FIELD_ALIASES.get(field, [field]):
        if col in df.columns:
            series = df[col]
            if field in V2_SCOPE_NUMERIC_FIELDS:
                return pd.to_numeric(series, errors="coerce").fillna(0.0)
            return series.fillna(default).astype(str).str.strip()
    if field in V2_SCOPE_NUMERIC_FIELDS:
        return pd.Series([0.0] * len(df), index=df.index)
    return pd.Series([default] * len(df), index=df.index)


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
    if executed_value <= 0 and total_value > 0:
        executed_value = max(0.0, total_value - remaining_value)
    if total_value <= 0:
        unit_price = _v2_safe_num(item.get("unit_price"))
        total_qty = _v2_safe_num(item.get("total_qty"))
        total_value = total_qty * unit_price
        if remaining_value <= 0:
            remaining_value = _v2_safe_num(item.get("remaining_qty")) * unit_price
        executed_value = max(0.0, total_value - remaining_value)
    return {
        "total_value": total_value,
        "executed_value": executed_value,
        "remaining_value": remaining_value,
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
                item.get("executed_qty"),
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
    executed_qty = _v2_safe_num(item.get("executed_qty"))
    remaining_qty = _v2_safe_num(item.get("remaining_qty"))
    available_qty = max(0.0, _v2_safe_num(item.get("available_to_add_qty")))

    if total_qty > 0:
        exec_width = min(max(executed_qty / total_qty * 100.0, 0.0), 100.0)
        avail_width = min(max(available_qty / total_qty * 100.0, 0.0), 100.0)
        blocked_width = min(
            max((remaining_qty - available_qty) / total_qty * 100.0, 0.0),
            max(0.0, 100.0 - exec_width - avail_width),
        )
    else:
        exec_width = avail_width = blocked_width = 0.0

    exec_label = f"Выполнено {pct_executed_str}" if exec_width >= 10 else ""
    blocked_label = f"Остаток {pct_remaining_str}" if blocked_width >= 10 else ""
    avail_label = (
        f"Доступно {_v2_format_qty_display_str(available_qty)} {unit}".strip()
        if avail_width >= 8
        else ""
    )

    return f"""
<div class="v2-boq-detail-section-title">Объём и освоение</div>
<div class="v2-boq-volume-row">
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Всего</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(item.get("total_qty"))}</span>
      <span class="v2-boq-volume-cost">{_format_rub(costs["total_value"])}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Выполнено</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(item.get("executed_qty"))}</span>
      <span class="v2-boq-volume-cost executed">{_format_rub(costs["executed_value"])}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">Остаток</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(item.get("remaining_qty"))}</span>
      <span class="v2-boq-volume-cost">{_format_rub(costs["remaining_value"])}</span>
    </div>
  </div>
  <div class="v2-boq-volume-cell">
    <span class="v2-boq-volume-label">% освоения</span>
    <span class="v2-boq-volume-pct">{pct_executed_str}</span>
  </div>
  <div class="v2-boq-volume-cell highlight">
    <span class="v2-boq-volume-label">Доступно к планированию</span>
    <div class="v2-boq-volume-values">
      <span class="v2-boq-volume-qty">{_v2_format_qty_display_str(available_qty)}</span>
      <span class="v2-boq-volume-cost">{unit or "—"}</span>
    </div>
  </div>
</div>
<div class="v2-boq-progress-track">
  <div class="v2-boq-progress-segment executed" style="width:{exec_width:.4f}%;">{exec_label}</div>
  <div class="v2-boq-progress-segment remaining" style="width:{blocked_width:.4f}%;">{blocked_label}</div>
  <div class="v2-boq-progress-segment available" style="width:{avail_width:.4f}%;">{avail_label}</div>
</div>
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
    if V2_DRAFT_ITEMS_KEY not in st.session_state:
        st.session_state[V2_DRAFT_ITEMS_KEY] = []


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
    """Сумма planned_qty из session draft по BOQ-key + month (без DB-reserve)."""
    items: list[dict[str, Any]] = st.session_state.get(V2_DRAFT_ITEMS_KEY) or []
    month_filter = str(month_key or "").strip().lower()
    result: dict[tuple[str, str, str, str, str], float] = {}
    for draft in items:
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
    """month_key и последняя added_at по BOQ-key из session draft."""
    items: list[dict[str, Any]] = st.session_state.get(V2_DRAFT_ITEMS_KEY) or []
    month_filter = str(month_key or "").strip().lower()
    result: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for draft in items:
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
    """Уменьшить available_to_add_qty с учётом session draft (без DB)."""
    if df.empty or not str(month_key or "").strip():
        return df
    planned_map = build_v2_session_planned_qty_map(month_key)
    meta_map = build_v2_session_planned_meta_map(month_key)
    out = df.copy()
    session_planned: list[float] = []
    available: list[float] = []
    statuses: list[str] = []
    planned_months: list[str] = []
    planned_ats: list[str] = []
    for _, row in out.iterrows():
        key = _v2_boq_draft_key_from_row(row, month_key)
        session_qty = planned_map.get(key, 0.0)
        remaining = _v2_safe_num(row.get("remaining_qty"))
        avail = remaining - session_qty
        session_planned.append(session_qty)
        available.append(avail)
        statuses.append(_v2_resolve_available_status(remaining, avail, session_qty))
        if session_qty > 0:
            meta = meta_map.get(key, {})
            planned_months.append(str(meta.get("planned_month") or month_key).strip())
            planned_ats.append(format_v2_added_at_moscow(meta.get("planned_at")))
        else:
            planned_months.append("")
            planned_ats.append("")
    out["already_planned_qty"] = session_planned
    out["available_to_add_qty"] = available
    out["status"] = statuses
    out["planned_month"] = planned_months
    out["planned_at"] = planned_ats
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
) -> dict[str, Any]:
    draft_item: dict[str, Any] = {
        "line_uid": str(uuid4()),
        "project_code": str(item.get("project_code") or "").strip(),
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
        "added_at": datetime.now(timezone.utc).isoformat(),
        "line_source_ui": "Новый код",
        "read_only": False,
    }
    items: list[dict[str, Any]] = list(st.session_state.get(V2_DRAFT_ITEMS_KEY) or [])
    items.append(draft_item)
    st.session_state[V2_DRAFT_ITEMS_KEY] = items
    return draft_item


def load_v2_session_draft_items() -> list[dict[str, Any]]:
    return list(st.session_state.get(V2_DRAFT_ITEMS_KEY) or [])


def clear_v2_session_draft_items() -> None:
    st.session_state[V2_DRAFT_ITEMS_KEY] = []


def compute_v2_month_plan_kpis(items: list[dict[str, Any]]) -> dict[str, float | int]:
    return {
        "total_lines": len(items),
        "new_lines": len(items),
        "plan_value_rub": sum(_v2_safe_num(item.get("plan_value")) for item in items),
        "required_hours": sum(_v2_safe_num(item.get("required_hours")) for item in items),
        "labor_cost_rub": sum(_v2_safe_num(item.get("labor_cost")) for item in items),
    }


def _v2_format_duration_shifts_display(value: Any) -> str:
    shifts = _v2_safe_num(value)
    if shifts <= 0:
        return "—"
    return f"{_v2_format_qty_display_str(shifts)} смены"


def map_v2_session_draft_to_display_df(items: list[dict[str, Any]]) -> pd.DataFrame:
    """Session draft → таблица Модуля 3."""
    if not items:
        return pd.DataFrame(columns=V2_MONTH_PLAN_DISPLAY_COLUMNS)

    sorted_items = sorted(
        items,
        key=lambda item: str(item.get("added_at") or ""),
        reverse=True,
    )
    rows: list[dict[str, str]] = []
    for item in sorted_items:
        rows.append(
            {
                "Дата добавления": format_v2_added_at_moscow(item.get("added_at")) or "—",
                "Статус": V2_SESSION_DRAFT_STATUS,
                "Месяц": str(item.get("month_key") or "—"),
                "BOQ код": str(item.get("boq_code") or "—"),
                "Наименование": str(item.get("boq_name") or "—"),
                "Объём": _v2_format_qty_display_str(item.get("planned_qty")),
                "Ед.": str(item.get("unit") or "—"),
                "Звено": str(item.get("crew_code") or "—"),
                "Людей": str(int(_v2_safe_num(item.get("crew_size"), default=1.0))),
                "Норма": str(item.get("norm_scenario") or "—"),
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
                "Комментарий": str(item.get("comment") or "").strip() or "—",
            }
        )
    return pd.DataFrame(rows, columns=V2_MONTH_PLAN_DISPLAY_COLUMNS)


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


def _v2_adjustment_history_display_df(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    rows: list[dict[str, str]] = []
    for rank, (_, record) in enumerate(history.head(5).iterrows()):
        rec = record.to_dict()
        manual_exec = _v2_safe_num(rec.get("manual_executed_before_system"))
        rows.append(
            {
                "Дата": _v2_format_adjustment_datetime(rec.get("updated_at")),
                "Пользователь": _v2_adjustment_user_label(rec),
                "Ранее выполнено до DP": _v2_format_qty_display_str(manual_exec),
                "Причина": _v2_format_optional_text(rec.get("reason")),
                "Комментарий": _v2_format_optional_text(rec.get("comment")),
                "Статус": "Активна" if rank == 0 else "—",
                "Действие": "Текущая" if rank == 0 else "—",
            }
        )
    return pd.DataFrame(rows)


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


def _v2_render_adjustment_journal(item: pd.Series) -> None:
    """Компактный журнал корректировок + muted danger-zone отката."""
    boq_code = str(item.get("boq_code") or "boq").strip()
    st.markdown('<p class="v2-boq-adj-journal-title">Журнал корректировок</p>', unsafe_allow_html=True)
    history = load_v2_manual_adjustments_history(item)
    if history.empty:
        st.caption("Корректировок пока нет")
        return

    display_df = _v2_adjustment_history_display_df(history)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    if len(history) > 5:
        st.caption("Показаны последние 5")

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


def _v2_clear_scope_caches_after_adjustment_save() -> None:
    _v2_clear_scope_caches_after_adjustment_change()


def _render_residual_adjustment_expander(item: pd.Series) -> None:
    """Expander корректировки остатка — production save через v1 pipeline."""
    boq_code = str(item.get("boq_code") or "boq").strip()
    manual_exec_raw = item.get("manual_executed_before_system", item.get("manual_adjustment_qty", 0))
    manual_exec_default = 0.0 if _v2_is_missing_numeric(manual_exec_raw) else _v2_safe_num(manual_exec_raw)
    total_qty = _v2_safe_num(item.get("total_qty"))

    with st.expander("Корректировка остатка", expanded=False):
        st.markdown(
            '<p class="v2-boq-detail-expander-note">'
            "Используется для объёма, выполненного до запуска Daily Progress."
            "</p>",
            unsafe_allow_html=True,
        )
        inp_exec = st.number_input(
            "Ранее выполнено до Daily Progress",
            min_value=0.0,
            value=float(manual_exec_default),
            step=0.01,
            key=f"v2_adj_exec_{boq_code}",
        )
        if st.button("Сохранить корректировку", key=f"v2_adj_save_{boq_code}"):
            if inp_exec < 0:
                st.error("Ранее выполненный объём не может быть отрицательным.")
            elif inp_exec > total_qty:
                st.error("Ранее выполненный объём не может превышать общий объём BOQ.")
            else:
                try:
                    save_adjustment(
                        _v2_adjustment_save_row(item),
                        inp_exec,
                        None,
                        "Выполнено до запуска Daily Progress",
                        "v2 manual adjustment",
                    )
                    _v2_clear_scope_caches_after_adjustment_save()
                    st.success("Корректировка сохранена")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Ошибка сохранения корректировки: {exc}")

        _v2_render_adjustment_journal(item)


def _render_add_to_month_plan_expander(item: pd.Series) -> None:
    """Expander добавления объёма в текущий месяц планирования (session draft)."""
    boq_code = str(item.get("boq_code") or "boq").strip()
    planning_month = str(st.session_state.get("v2_scope_planning_month") or "").strip()
    available_qty = _v2_safe_num(item.get("available_to_add_qty"))
    session_reserved = _v2_safe_num(item.get("already_planned_qty"))

    with st.expander(
        "Добавить код / объём работ в текущий месяц планирования",
        expanded=False,
    ):
        if not planning_month:
            st.warning("Выберите месяц планирования в фильтрах scope.")
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

        if plan_qty_f > available_qty and plan_qty_f > 0:
            st.warning("Объём превышает доступный остаток.")
        if not has_available:
            st.caption("Нет доступного остатка для планирования.")

        add_disabled = (
            not has_available
            or not qty_ok
            or not crew_valid
            or not manual_ok
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
                append_v2_month_plan_draft_item(
                    item,
                    planning_month,
                    plan_qty_f,
                    str(crew).strip(),
                    norm_scenario,
                    float(manual_norm),
                    comment,
                    preview,
                )
                st.success("Строка добавлена в месячный план")
                st.rerun()

        st.markdown(
            '<p class="v2-boq-action-footnote">'
            "Строка сохраняется в session draft. Supabase и единый план — позже."
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


def _v2_format_scope_table_display(display_df: pd.DataFrame) -> pd.DataFrame:
    """Форматирование чисел и маркер выбранной строки для таблицы."""
    out = display_df.copy()
    for col in V2_SCOPE_QTY_COLUMNS:
        if col in out.columns:
            out[col] = out[col].apply(_v2_format_qty_display_str)
    selected_code = st.session_state.get("v2_scope_selected_boq_code")
    out["Выбор"] = out["Код"].astype(str).apply(
        lambda code: "✓" if code == str(selected_code or "") else ""
    )
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
    fallback_remaining_qty = out["total_qty"] - out["executed_qty"]
    out["remaining_qty"] = view_remaining_qty.where(from_view_qty, fallback_remaining_qty)
    out["_remaining_qty_origin"] = from_view_qty.map({True: "view", False: "fallback"})

    view_remaining_value = pd.to_numeric(out.get("remaining_value"), errors="coerce")
    from_view_value = view_remaining_value.notna()
    fallback_remaining_value = out["remaining_qty"] * out["unit_price"]
    out["remaining_value"] = view_remaining_value.where(from_view_value, fallback_remaining_value)

    out["executed_value"] = (out["total_value"] - out["remaining_value"]).clip(lower=0.0)

    out["percent_executed"] = out.apply(
        lambda row: _v2_calculate_percent_executed_production(
            row["total_value"],
            row["executed_value"],
            row["total_qty"],
            row["executed_qty"],
        ),
        axis=1,
    )
    out["percent_remaining"] = (100.0 - out["percent_executed"]).clip(lower=0.0)

    out["already_planned_qty"] = 0.0
    out["planned_month"] = ""
    out["planned_at"] = ""
    out["available_to_add_qty"] = out["remaining_qty"]
    out["status"] = out["remaining_qty"].apply(
        lambda qty: "Выполнено" if _v2_safe_num(qty) <= 0 else "Доступно"
    )

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
        "norm_hours_per_unit": "-",
        "norm_type": "Не подключено",
        "productivity_history": "Не подключено",
    }
    for col, default in v1_defaults.items():
        if col not in out.columns:
            out[col] = default
        elif col in {"manual_executed_before_system", "manual_adjustment_qty"}:
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
            "Код": scoped_df["boq_code"].astype(str),
            "Наименование работ": scoped_df["boq_name"].astype(str),
            "Ед. изм.": scoped_df["unit"].astype(str).replace({"": "—"}),
            "Всего": scoped_df["total_qty"],
            "Выполнено": scoped_df["executed_qty"],
            "Остаток": scoped_df["remaining_qty"],
            "% освоения": scoped_df["percent_executed"].apply(_v2_format_percent_display_str),
            "Уже в плане": scoped_df["already_planned_qty"],
            "Месяц планирования": _v2_display_text_column(scoped_df["planned_month"]),
            "Дата планирования": scoped_df["planned_at"].apply(
                lambda value: format_v2_added_at_moscow(value) or "—"
                if str(value or "").strip()
                else "—"
            ),
            "Доступно": scoped_df["available_to_add_qty"],
            "Статус": scoped_df["status"].astype(str),
            "Выбор": False,
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
    df["Выбор"] = False
    return df


def prepare_scope_table_df(scope_df: pd.DataFrame) -> pd.DataFrame:
    """Упорядочивание колонок рабочей таблицы BOQ Scope."""
    if scope_df.empty:
        return pd.DataFrame(columns=BOQ_SCOPE_TABLE_DISPLAY_COLUMNS)
    out = scope_df.copy()
    for col in BOQ_SCOPE_TABLE_DISPLAY_COLUMNS:
        if col not in out.columns:
            if col in V2_SCOPE_QTY_COLUMNS:
                out[col] = 0.0
            elif col == "% освоения":
                out[col] = "0%"
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
    st.markdown(
        f'<p class="constructor-v2-scope-module-subtitle">{SCOPE_MODULE_SUBTITLE}</p>',
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
        "v2_scope_planning_month": "июнь-2026",
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
    st.session_state.pop("v2_scope_filters_saved", None)


def render_scope_filters(scoped_df: pd.DataFrame) -> dict[str, str]:
    """Компактная панель фильтров среза."""
    project_options = _v2_project_filter_options(scoped_df)
    queue_options = V2_QUEUE_FILTER_OPTIONS
    title_options = _v2_filter_options(scoped_df, "facility")
    discipline_options = _v2_filter_options(scoped_df, "discipline")
    status_options = _v2_filter_options(scoped_df, "status")

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
                index=PLANNING_MONTH_OPTIONS.index("июнь-2026"),
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
                _v2_reset_scope_filters()
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
    """Подсветка статуса и выбранной строки через Pandas Styler."""

    def _status_style(value: Any) -> str:
        key = str(value)
        return V2_SCOPE_STATUS_STYLES.get(key, V2_SCOPE_STATUS_STYLES.get("Нет остатка", ""))

    def _selection_row_style(row: pd.Series) -> list[str]:
        if selected_code and str(row.get("Код", "")) == str(selected_code):
            return ["background-color: #EFF6FF; font-weight: 600;"] * len(row)
        return [""] * len(row)

    styler = display_df.style.map(_status_style, subset=["Статус"]).apply(
        _selection_row_style, axis=1
    )
    if "Выбор" in display_df.columns:
        styler = styler.set_properties(
            subset=["Выбор"],
            **{"text-align": "center", "font-weight": "700", "color": "#2F5D7C", "font-size": "1rem"},
        )
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
                    ("white-space", "normal"),
                ],
            }
        )
    for col_name, min_w, max_w in (
        ("Система", "120px", "180px"),
        ("IWP", "100px", "160px"),
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


def render_scope_table(ui_df: pd.DataFrame) -> pd.DataFrame:
    """Рабочий список BOQ: styled table + single-row selection."""
    st.markdown("**Рабочий список BOQ**")

    if ui_df.empty:
        st.caption("По выбранным параметрам среза строк не найдено.")
        return ui_df

    render_scope_status_legend()

    display_df = _v2_format_scope_table_display(prepare_scope_table_df(ui_df.copy()))
    selected_code = st.session_state.get("v2_scope_selected_boq_code")

    st.markdown('<div class="v2-scope-boq-table">', unsafe_allow_html=True)
    table_event = st.dataframe(
        style_v2_scope_table(display_df, selected_code),
        use_container_width=True,
        hide_index=True,
        height=min(36 * len(display_df) + 38, 420),
        on_select="rerun",
        selection_mode="single-row",
        key="v2_scope_table_view",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    selection_rows = getattr(getattr(table_event, "selection", None), "rows", None) or []
    if selection_rows:
        st.session_state.v2_scope_selected_boq_code = str(display_df.iloc[selection_rows[0]]["Код"])

    return ui_df


def _v2_status_badge_html(status: str) -> str:
    style = V2_SCOPE_STATUS_STYLES.get(
        status,
        "background-color: #F1F5F9; color: #64748B;",
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
    if status == "Требует проверки":
        return "Требуется проверка корректировок и исходных данных", "warning"
    if status == "Перепланировано" or remaining_qty < 0:
        return "Требуется проверка: объём запланирован сверх остатка", "warning"
    if status == "Выполнено" or available_qty <= 0:
        return "Нет доступного остатка для планирования", "muted"
    if status == "Доступно" or available_qty > 0:
        return "Можно добавить в месячный план", "positive"
    return "Нет доступного остатка для планирования", "muted"


def render_selected_boq_card(scoped_df: pd.DataFrame) -> None:
    """Enterprise detail panel выбранного BOQ-кода."""
    st.markdown("**Детализация выбранного BOQ**")
    selected_code = st.session_state.get("v2_scope_selected_boq_code")

    with st.container(border=True):
        st.markdown('<div class="v2-boq-detail-panel">', unsafe_allow_html=True)
        if not selected_code:
            st.caption("Выберите строку в рабочем списке для просмотра деталей.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        row = scoped_df[scoped_df["boq_code"].astype(str) == str(selected_code)]
        if row.empty:
            st.caption("Выбранный BOQ-код не найден в текущем срезе.")
            st.markdown("</div>", unsafe_allow_html=True)
            return

        item = row.iloc[0]
        status = str(item["status"])

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

        _render_residual_adjustment_expander(item)
        _render_add_to_month_plan_expander(item)

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
    render_scope_module_header()

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
    planning_month = str(st.session_state.get("v2_scope_planning_month") or "").strip()
    if planning_month:
        scoped_df = apply_v2_session_draft_reservation(scoped_df, planning_month)
    load_meta["excluded_invalid"] = excluded_invalid
    load_meta["working_rows"] = len(scoped_df)
    load_meta["calc"] = calc_meta

    filters = render_scope_filters(scoped_df)
    filtered_scoped = apply_scope_filters(scoped_df, filters)
    ui_df = map_v2_scope_to_ui_df(filtered_scoped)

    render_scope_kpi_cards(compute_scope_kpi_metrics(filtered_scoped))

    render_scope_table(ui_df)
    render_selected_boq_card(filtered_scoped)


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
    """Модуль 3: read-only таблица session draft."""
    st.markdown(
        '<p class="constructor-v2-module-hint">'
        "Накопление строк месячного плана в текущей сессии. "
        "Сохранение в Supabase и отправка — позже."
        "</p>",
        unsafe_allow_html=True,
    )

    items = load_v2_session_draft_items()
    if not items:
        st.info("В месячный план пока не добавлены строки.")
        return

    kpis = compute_v2_month_plan_kpis(items)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Строк в плане", f"{kpis['total_lines']:,}".replace(",", " "))
    m2.metric("Новые строки", f"{kpis['new_lines']:,}".replace(",", " "))
    m3.metric("Плановая стоимость, ₽", _format_rub(float(kpis["plan_value_rub"])))
    m4.metric("Трудозатраты, чел-ч", _v2_format_qty_display_str(kpis["required_hours"]))
    m5.metric("Стоимость труда, ₽", _format_rub(float(kpis["labor_cost_rub"])))

    display_df = map_v2_session_draft_to_display_df(items)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=min(36 * len(display_df) + 38, 420),
    )

    if st.button("Очистить новые строки", key="v2_clear_session_draft"):
        clear_v2_session_draft_items()
        st.rerun()


def render_module_plan_actions() -> None:
    """Модуль 4: действия с месячным планом."""
    st.markdown(
        '<p class="constructor-v2-module-hint">'
        "Редактирование и удаление доступны только для новых или неотправленных строк."
        "</p>",
        unsafe_allow_html=True,
    )

    st.info("Строка не выбрана. Выбор строки будет доступен в модуле «Единый месячный план».")

    primary_col, secondary_col = st.columns(2)
    with primary_col:
        st.button("Сохранить", type="primary", disabled=True, key="v2_save_plan")
        st.button("Отправить в контур допуска", disabled=True, key="v2_send_plan")
    with secondary_col:
        st.button("Редактировать выбранную строку", disabled=True, key="v2_edit_row")
        st.button("Удалить выбранную строку", disabled=True, key="v2_delete_row")


def main() -> None:
    inject_page_styles()
    init_v2_session_state()
    render_page_header()

    with st.expander("📥 Загрузка исходных данных", expanded=False):
        render_module_upload_inputs()

    with st.expander("📊 Остатки и доступность к планированию", expanded=False):
        render_module_boq_scope()

    with st.expander("📋 Единый месячный план", expanded=False):
        render_module_month_plan()

    with st.expander("⚙️ Действия с месячным планом", expanded=False):
        render_module_plan_actions()


# --- Точка входа Streamlit ---
st.set_page_config(
    page_title="Конструктор месячного плана v2",
    layout="wide",
    initial_sidebar_state="expanded",
)

main()
