"""
Read-model for the Constructor result already loaded by the Query Port.

Filters and labels only. No Constructor business rules and no writes.
Module 5 presentation: executive-density KPI + chip filters + one table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from agents.control_room.dtos import (
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    constructor_row_awaits_human_review,
)
from agents.control_room.presentation import (
    PROFESSIONAL_PATH_STATUS_RU,
    constructor_decision_table_rows,
    constructor_month_display,
    constructor_project_short,
    professional_status_ru,
)
from agents.human_surface.mission_draft import MissionDraft, WorkingContext


MODULE5_TITLE_RU = "Результат анализа Constructor"
MODULE5_MODE_INCREMENTAL_RU = "Дополнительный анализ"
MODULE5_MODE_INCREMENTAL_FULL_RU = "ДОПОЛНИТЕЛЬНЫЙ АНАЛИЗ ТЕКУЩЕГО ПЛАНА"

# Top-level KPI groups (presentation grouping only).
_PROPOSED_OUTCOMES = frozenset({"CANDIDATE"})
_CONTROL_OUTCOMES = frozenset(
    {
        "EXCLUDED_INCONSISTENT_QUANTITIES",
        "EXCLUDED_INVALID",
        "EXCLUDED_OVERRUN",
    }
)
_NO_ACTION_OUTCOMES = frozenset(
    {
        "EXCLUDED_COMPLETED",
        "EXCLUDED_ALREADY_PLANNED",
        "EXCLUDED_NO_REMAINDER",
        "EXCLUDED_NOT_REQUIRED",
    }
)

# Filter chip ids → presentation labels (counts appended by builder).
_FILTER_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("all", "Все", False),
    ("candidates", "Кандидаты", False),
    ("new_opportunity", "Новые возможности", False),
    ("additional_volume", "Доп. объём", False),
    ("conflict_plan_reality", "План > текущего остатка", True),
    ("source_data", "Исходные данные", False),
    ("overrun", "Overrun", False),
    ("completed", "Выполнено", False),
    ("already_planned", "Уже запланировано", False),
    ("no_remainder", "Нет остатка", False),
    ("not_required", "Не требуется", False),
)

_HS_OUTCOME_LABEL_RU = {
    "CANDIDATE": "Предложено к рассмотрению",
    "EXCLUDED_COMPLETED": "Уже выполнено к текущему состоянию",
    "EXCLUDED_NO_REMAINDER": "Нет физического остатка",
    "EXCLUDED_ALREADY_PLANNED": "Полностью уже запланировано",
    "EXCLUDED_INVALID": "Некорректные / неполные исходные данные",
    "EXCLUDED_OVERRUN": "Overrun / перерасход",
    "EXCLUDED_INCONSISTENT_QUANTITIES": "План > текущего остатка",
    "EXCLUDED_NOT_REQUIRED": "Не требуется",
}

CONFLICT_MANAGER_NOTE_RU = (
    "Плановый объём превышает текущий расчётный физический остаток. "
    "Причину можно определить только с учётом факта выполнения с начала месяца."
)
COMPLETED_MANAGER_NOTE_RU = (
    "Работа уже выполнена к текущему состоянию. Это не означает ошибку планирования."
)


@dataclass(frozen=True)
class Module5ResultSummary:
    """Compact Module 5 KPI / filter summary derived from Decision Registry."""

    total: int
    proposed: int
    control_deviations: int
    no_action: int
    other: int
    new_opportunities: int
    additional_volume: int
    conflict_plan_reality: int
    source_data: int
    overrun: int
    completed: int
    already_planned: int
    no_remainder: int
    not_required: int
    mode_badge: str
    groups_sum_to_total: bool


def workspace_run_banner(result: ConstructorProfessionalResultView) -> str:
    project = constructor_project_short(result.project_id)
    month = constructor_month_display(result.month)
    return f"Последний доступный результат: {project} · {month}"


def assignment_differs_from_run(
    draft: MissionDraft, result: ConstructorProfessionalResultView
) -> bool:
    if not draft.planning_month:
        return False
    shown = constructor_month_display(result.month).casefold()
    return shown != draft.planning_month.casefold()


def professional_status_line(result: ConstructorProfessionalResultView) -> str:
    code = str(result.professional_status or "").strip()
    labeled = professional_status_ru(code)
    if labeled != code:
        return labeled
    return PROFESSIONAL_PATH_STATUS_RU.get(code, labeled or "—")


def module5_state_timestamp(as_of: Optional[datetime]) -> str:
    """Format authoritative state time when provided; empty when unknown."""
    if as_of is None:
        return ""
    try:
        return as_of.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return as_of.strftime("%Y-%m-%d %H:%M")


def _qty_number(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text or text in {"—", "-", "None", "nan", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _already_planned_positive(record: ConstructorRowDecisionView) -> bool:
    planned = _qty_number(record.already_planned_qty)
    return planned is not None and planned > 0


def candidate_presentation_slice(record: ConstructorRowDecisionView) -> Optional[str]:
    """Presentation-only split of CANDIDATE rows. Does not change outcomes."""
    if record.outcome != "CANDIDATE":
        return None
    if _already_planned_positive(record):
        return "additional_volume"
    return "new_opportunity"


def _record_matches_work_context(
    record: ConstructorRowDecisionView,
    context: Optional[WorkingContext],
) -> bool:
    """Apply authoritative Work Context as the only professional scope filter."""
    if context is None:
        return True
    titles = tuple(str(item).strip() for item in (context.titles or ()) if str(item).strip())
    if titles:
        facility = str(record.facility or "").strip()
        if facility not in titles:
            return False
    discipline = str(context.discipline or "").strip()
    if discipline and discipline.casefold() not in {
        "все",
        "все дисциплины",
        "all",
    }:
        if str(record.discipline or "").strip() != discipline:
            return False
    systems = tuple(str(item).strip() for item in (context.systems or ()) if str(item).strip())
    if systems:
        system = str(record.system or "").strip()
        if system not in systems:
            return False
    packages_raw = str(context.packages or "").strip()
    if packages_raw and packages_raw.casefold() not in {"все", "все пакеты", "all"}:
        allowed = tuple(
            part.strip() for part in packages_raw.replace(";", ",").split(",") if part.strip()
        )
        if allowed:
            iwp = str(record.iwp or "").strip()
            if iwp not in allowed:
                return False
    return True


def filter_records_by_work_context(
    records: tuple[ConstructorRowDecisionView, ...] | list[ConstructorRowDecisionView],
    context: Optional[WorkingContext],
) -> tuple[ConstructorRowDecisionView, ...]:
    return tuple(
        item for item in records if _record_matches_work_context(item, context)
    )


def build_module5_result_summary_from_records(
    records: tuple[ConstructorRowDecisionView, ...] | list[ConstructorRowDecisionView],
) -> Module5ResultSummary:
    """KPI / chip counts for an already scoped record set (Work Context applied)."""
    counts: dict[str, int] = {}
    for record in records:
        key = str(record.outcome or "").strip()
        counts[key] = counts.get(key, 0) + 1
    proposed = int(counts.get("CANDIDATE", 0))
    conflict = int(counts.get("EXCLUDED_INCONSISTENT_QUANTITIES", 0))
    source_data = int(counts.get("EXCLUDED_INVALID", 0))
    overrun = int(counts.get("EXCLUDED_OVERRUN", 0))
    completed = int(counts.get("EXCLUDED_COMPLETED", 0))
    already = int(counts.get("EXCLUDED_ALREADY_PLANNED", 0))
    no_rem = int(counts.get("EXCLUDED_NO_REMAINDER", 0))
    not_req = int(counts.get("EXCLUDED_NOT_REQUIRED", 0))
    control = conflict + source_data + overrun
    no_action = completed + already + no_rem + not_req
    total = len(tuple(records))
    accounted = proposed + control + no_action
    other = max(0, total - accounted)

    new_opp = additional = 0
    for record in records:
        slice_id = candidate_presentation_slice(record)
        if slice_id == "new_opportunity":
            new_opp += 1
        elif slice_id == "additional_volume":
            additional += 1

    mode = ""
    if already > 0 or additional > 0:
        mode = MODULE5_MODE_INCREMENTAL_RU

    return Module5ResultSummary(
        total=total,
        proposed=proposed,
        control_deviations=control,
        no_action=no_action,
        other=other,
        new_opportunities=new_opp,
        additional_volume=additional,
        conflict_plan_reality=conflict,
        source_data=source_data,
        overrun=overrun,
        completed=completed,
        already_planned=already,
        no_remainder=no_rem,
        not_required=not_req,
        mode_badge=mode,
        groups_sum_to_total=(accounted + other) == total
        and other == 0
        and (proposed + control + no_action) == total,
    )


def build_module5_result_summary(
    registry: ConstructorDecisionRegistryView,
) -> Module5ResultSummary:
    return build_module5_result_summary_from_records(registry.records)


def module5_kpi_tiles(summary: Module5ResultSummary) -> tuple[tuple[str, str], ...]:
    return (
        ("Изучено", str(summary.total)),
        ("Предложено к рассмотрению", str(summary.proposed)),
        ("Контрольные отклонения", str(summary.control_deviations)),
        ("Не требуют действия", str(summary.no_action)),
    )


def module5_filter_options(
    summary: Module5ResultSummary,
) -> tuple[tuple[str, str, bool], ...]:
    """Return (view_id, label_with_count, emphasize) for chip row."""
    count_by_id = {
        "all": summary.total,
        # Exact Candidate Package / proposed-to-review count (not a split chip).
        "candidates": summary.proposed,
        "new_opportunity": summary.new_opportunities,
        "additional_volume": summary.additional_volume,
        "conflict_plan_reality": summary.conflict_plan_reality,
        "source_data": summary.source_data,
        "overrun": summary.overrun,
        "completed": summary.completed,
        "already_planned": summary.already_planned,
        "no_remainder": summary.no_remainder,
        "not_required": summary.not_required,
    }
    options: list[tuple[str, str, bool]] = []
    for view_id, label, emphasize in _FILTER_SPECS:
        count = int(count_by_id.get(view_id, 0))
        if view_id != "all" and count <= 0:
            continue
        mark = "⚠ " if emphasize and count else ""
        options.append((view_id, f"{mark}{label} · {count}", emphasize and count > 0))
    return tuple(options)


def workspace_result_lines(registry: ConstructorDecisionRegistryView) -> tuple[str, ...]:
    """Compact KPI lines for tests / non-Streamlit consumers."""
    summary = build_module5_result_summary(registry)
    return (
        f"Изучено: {summary.total}",
        f"Предложено к рассмотрению: {summary.proposed}",
        f"Контрольные отклонения: {summary.control_deviations}",
        f"Не требуют действия: {summary.no_action}",
        f"Новые возможности: {summary.new_opportunities}",
        f"Доп. объём: {summary.additional_volume}",
        f"План > текущего остатка: {summary.conflict_plan_reality}",
        f"Исходные данные: {summary.source_data}",
        f"Overrun: {summary.overrun}",
        f"Выполнено: {summary.completed}",
        f"Уже запланировано: {summary.already_planned}",
        f"Нет остатка: {summary.no_remainder}",
        f"Не требуется: {summary.not_required}",
    )


def simple_result_filter_options(
    registry: ConstructorDecisionRegistryView,
) -> tuple[tuple[str, str], ...]:
    """Module 5 chip options without the emphasize flag (compat)."""
    summary = build_module5_result_summary(registry)
    return tuple((view_id, label) for view_id, label, _emph in module5_filter_options(summary))


def workspace_filter_options(
    registry: ConstructorDecisionRegistryView,
) -> tuple[tuple[str, str], ...]:
    return simple_result_filter_options(registry)


def select_workspace_records(
    records: tuple[ConstructorRowDecisionView, ...],
    professional: ConstructorProfessionalResultView,
    *,
    view_id: str,
    text: str = "",
) -> tuple[ConstructorRowDecisionView, ...]:
    """Filter an already loaded decision read model. Does not recompute Constructor outcomes."""
    needle = str(text or "").strip().casefold()
    kept: list[ConstructorRowDecisionView] = []
    for record in records:
        if not _matches_view(record, professional, view_id):
            continue
        if needle:
            haystack = " ".join(
                (record.boq_code, record.name, record.system or "", record.facility or "")
            ).casefold()
            if needle not in haystack:
                continue
        kept.append(record)
    return tuple(kept)


def human_surface_outcome_label(outcome: str) -> str:
    code = str(outcome or "").strip()
    return _HS_OUTCOME_LABEL_RU.get(code, code or "—")


def conflict_deviation_display(record: ConstructorRowDecisionView) -> str:
    if record.outcome != "EXCLUDED_INCONSISTENT_QUANTITIES":
        return "—"
    remaining = _qty_number(record.remaining_qty)
    planned = _qty_number(record.already_planned_qty)
    if remaining is None or planned is None:
        return "—"
    delta = planned - remaining
    text = f"{delta:g}".replace(".", ",")
    return text


def workspace_table_rows(
    records: tuple[ConstructorRowDecisionView, ...] | list[ConstructorRowDecisionView],
    professional: ConstructorProfessionalResultView,
) -> tuple[dict[str, str], ...]:
    source = tuple(records)
    base = constructor_decision_table_rows(source, professional)
    rows = []
    for index, (record, item) in enumerate(zip(source, base), start=1):
        rows.append(
            {
                "№": str(index),
                "Титул": _stored_or_blank(record.facility),
                "Дисциплина": _stored_or_blank(record.discipline),
                "Система": item["Система"],
                "Пакет / IWP": _stored_or_blank(record.iwp),
                "BOQ-код": item["BOQ"],
                "Наименование работы": item["Наименование"],
                "Ед. изм.": item["Ед."],
                "Физический остаток": item["Остаток"],
                "Уже запланировано": item["Уже в плане"],
                "Доступный объём": item["Доступно"],
                "Отклонение": conflict_deviation_display(record),
                "Решение Constructor": human_surface_outcome_label(record.outcome),
                "Причина": item["Основание"],
            }
        )
    return tuple(rows)


def order_records_by_candidate_ids(
    records: tuple[ConstructorRowDecisionView, ...] | list[ConstructorRowDecisionView],
    ordered_candidate_ids: tuple[str, ...] | list[str],
) -> tuple[ConstructorRowDecisionView, ...]:
    """Stable № aliases: Focus Set order within the current Work Context."""
    by_id = {
        str(item.candidate_id): item
        for item in records
        if str(item.candidate_id or "").strip()
    }
    ordered: list[ConstructorRowDecisionView] = []
    for candidate_id in ordered_candidate_ids:
        item = by_id.get(str(candidate_id))
        if item is not None:
            ordered.append(item)
    return tuple(ordered)


def _stored_or_blank(value: object) -> str:
    text = str(value or "").strip()
    return text or "—"


def human_review_progress(professional: ConstructorProfessionalResultView) -> tuple[int, int]:
    total = len(professional.candidates)
    decided = sum(
        1 for item in professional.candidates if str(item.human_review_decision or "").strip()
    )
    return decided, total


def human_decision_tally(
    professional: ConstructorProfessionalResultView,
) -> tuple[int, int, int]:
    agreed = excluded = clarify = 0
    for item in professional.candidates:
        decision = str(item.human_review_decision or "").strip()
        if decision == "ADD":
            agreed += 1
        elif decision == "REMOVE":
            excluded += 1
        elif decision == "REQUIRES_CLARIFICATION":
            clarify += 1
    return agreed, excluded, clarify


def candidate_situation_line(
    record: ConstructorRowDecisionView,
    professional: ConstructorProfessionalResultView,
) -> str:
    if record.outcome == "EXCLUDED_INCONSISTENT_QUANTITIES":
        return CONFLICT_MANAGER_NOTE_RU
    if record.outcome == "EXCLUDED_COMPLETED":
        return COMPLETED_MANAGER_NOTE_RU
    if record.outcome == "CANDIDATE" and constructor_row_awaits_human_review(
        record, professional
    ):
        return (
            "Constructor довёл позицию до кандидатного состава. "
            "Решение о включении в итоговый пакет ещё не принято."
        )
    if record.outcome == "CANDIDATE":
        return "Позиция вошла в кандидатный состав Constructor."
    return ""


def _matches_view(
    record: ConstructorRowDecisionView,
    professional: ConstructorProfessionalResultView,
    view_id: str,
) -> bool:
    # Legacy ids kept for older tests / callers.
    if view_id == "attention":
        return constructor_row_awaits_human_review(record, professional)
    if view_id == "excluded":
        return record.outcome.startswith("EXCLUDED_")
    if view_id == "problems":
        return record.outcome in _CONTROL_OUTCOMES
    if view_id in {"CANDIDATE", "candidates"}:
        return record.outcome == "CANDIDATE"
    if view_id in {"EXCLUDED_COMPLETED", "completed"}:
        return record.outcome == "EXCLUDED_COMPLETED"
    if view_id in {"EXCLUDED_NO_REMAINDER", "no_remainder"}:
        return record.outcome == "EXCLUDED_NO_REMAINDER"
    if view_id in {"EXCLUDED_ALREADY_PLANNED", "already_planned"}:
        return record.outcome == "EXCLUDED_ALREADY_PLANNED"
    if view_id in {"EXCLUDED_INVALID", "source_data"}:
        return record.outcome == "EXCLUDED_INVALID"
    if view_id in {"EXCLUDED_OVERRUN", "overrun"}:
        return record.outcome == "EXCLUDED_OVERRUN"
    if view_id in {"EXCLUDED_INCONSISTENT_QUANTITIES", "conflict_plan_reality"}:
        return record.outcome == "EXCLUDED_INCONSISTENT_QUANTITIES"
    if view_id in {"EXCLUDED_NOT_REQUIRED", "not_required"}:
        return record.outcome == "EXCLUDED_NOT_REQUIRED"
    if view_id == "new_opportunity":
        return candidate_presentation_slice(record) == "new_opportunity"
    if view_id == "additional_volume":
        return candidate_presentation_slice(record) == "additional_volume"
    if view_id and view_id != "all":
        return record.outcome == view_id
    return True
