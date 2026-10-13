"""
Read-model for the Constructor result already loaded by the Query Port.

Filters and labels only. No Constructor business rules and no writes.
"""

from __future__ import annotations

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
from agents.human_surface.mission_draft import MissionDraft


_VIEW_ORDER = (
    ("all", "Все работы"),
    ("CANDIDATE", "Кандидаты"),
    ("attention", "Требуют решения"),
    ("excluded", "Причины исключения"),
    ("EXCLUDED_COMPLETED", "Выполнено"),
    ("EXCLUDED_NO_REMAINDER", "Без остатка"),
    ("EXCLUDED_ALREADY_PLANNED", "Уже в плане"),
    ("EXCLUDED_INVALID", "Невалидные"),
    ("EXCLUDED_OVERRUN", "Превышение"),
    ("EXCLUDED_INCONSISTENT_QUANTITIES", "Несогласованные объёмы"),
)


def workspace_result_lines(registry: ConstructorDecisionRegistryView) -> tuple[str, ...]:
    counts = dict(registry.outcome_counts)
    return (
        f"В контуре миссии: {registry.total_count}",
        f"Выполнено: {counts.get('EXCLUDED_COMPLETED', 0)}",
        f"Без остатка: {counts.get('EXCLUDED_NO_REMAINDER', 0)}",
        f"Уже включено в план: {counts.get('EXCLUDED_ALREADY_PLANNED', 0)}",
        f"Невалидные данные: {counts.get('EXCLUDED_INVALID', 0)}",
        f"Превышение: {counts.get('EXCLUDED_OVERRUN', 0)}",
        (
            "Несогласованные объёмы: "
            f"{counts.get('EXCLUDED_INCONSISTENT_QUANTITIES', 0)}"
        ),
        f"Кандидаты: {counts.get('CANDIDATE', 0)}",
        f"Требуют решения человека: {registry.attention_count}",
    )


def workspace_run_banner(result: ConstructorProfessionalResultView) -> str:
    project = constructor_project_short(result.project_id)
    month = constructor_month_display(result.month)
    return f"Последний доступный результат: {project} · {month}"


def assignment_differs_from_run(draft: MissionDraft, result: ConstructorProfessionalResultView) -> bool:
    if not draft.planning_month:
        return False
    shown = constructor_month_display(result.month).casefold()
    return shown != draft.planning_month.casefold()


def workspace_filter_options(
    registry: ConstructorDecisionRegistryView,
) -> tuple[tuple[str, str], ...]:
    counts = dict(registry.outcome_counts)
    excluded = sum(count for outcome, count in counts.items() if outcome.startswith("EXCLUDED_"))
    options = []
    for view_id, label in _VIEW_ORDER:
        if view_id == "all":
            count = registry.total_count
        elif view_id == "attention":
            count = registry.attention_count
        elif view_id == "excluded":
            count = excluded
        else:
            count = counts.get(view_id, 0)
        if view_id == "all" or count:
            options.append((view_id, f"{label} ({count})"))
    return tuple(options)


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
            haystack = " ".join((record.boq_code, record.name, record.system or "")).casefold()
            if needle not in haystack:
                continue
        kept.append(record)
    return tuple(kept)


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
                "Остаток": item["Остаток"],
                "Уже запланировано": item["Уже в плане"],
                "Доступный объём": item["Доступно"],
                "Решение Constructor": item["Решение Constructor"],
                "Причина": item["Основание"],
            }
        )
    return tuple(rows)


def _stored_or_blank(value: object) -> str:
    text = str(value or "").strip()
    return text or "—"


def human_review_progress(professional: ConstructorProfessionalResultView) -> tuple[int, int]:
    total = len(professional.candidates)
    decided = sum(1 for item in professional.candidates if str(item.human_review_decision or "").strip())
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


def professional_status_line(result: ConstructorProfessionalResultView) -> str:
    code = str(result.professional_status or "").strip()
    labeled = professional_status_ru(code)
    if labeled != code:
        return labeled
    return PROFESSIONAL_PATH_STATUS_RU.get(code, labeled or "—")


def candidate_situation_line(
    record: ConstructorRowDecisionView,
    professional: ConstructorProfessionalResultView,
) -> str:
    if record.outcome == "CANDIDATE" and constructor_row_awaits_human_review(record, professional):
        return (
            "Constructor довёл позицию до кандидатного состава. "
            "Решение о включении в итоговый пакет ещё не принято."
        )
    if record.outcome == "CANDIDATE":
        return "Позиция вошла в кандидатный состав Constructor."
    return ""


_PROBLEM_OUTCOMES = frozenset(
    {
        "EXCLUDED_INVALID",
        "EXCLUDED_OVERRUN",
        "EXCLUDED_INCONSISTENT_QUANTITIES",
    }
)


def simple_result_filter_options(
    registry: ConstructorDecisionRegistryView,
) -> tuple[tuple[str, str], ...]:
    counts = dict(registry.outcome_counts)
    problems = sum(counts.get(outcome, 0) for outcome in _PROBLEM_OUTCOMES)
    return (
        ("all", f"Все работы ({registry.total_count})"),
        ("attention", f"Требуют решения ({registry.attention_count})"),
        ("CANDIDATE", f"Кандидаты ({counts.get('CANDIDATE', 0)})"),
        ("problems", f"Проблемы ({problems})"),
    )


def _matches_view(
    record: ConstructorRowDecisionView,
    professional: ConstructorProfessionalResultView,
    view_id: str,
) -> bool:
    if view_id == "attention":
        return constructor_row_awaits_human_review(record, professional)
    if view_id == "excluded":
        return record.outcome.startswith("EXCLUDED_")
    if view_id == "problems":
        return record.outcome in _PROBLEM_OUTCOMES
    if view_id and view_id != "all":
        return record.outcome == view_id
    return True

