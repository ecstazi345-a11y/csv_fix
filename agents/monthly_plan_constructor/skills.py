"""
MPCA-001 — named skills (working operations).

Each skill: input → action → output. Pure orchestration of domain + tools data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agents.monthly_plan_constructor.domain import (
    aggregate_already_planned,
    apply_already_planned_to_scope,
    build_constructor_proposal,
    classify_scope_rows,
    merge_not_required_once,
)
from agents.monthly_plan_constructor.contracts import (
    HANDOFF_RECIPIENT,
    HandoffContract,
)
from services.monthly_planning_boq_service import (
    _v2_apply_boq_availability_metrics,
    _v2_resolve_scope_status_row,
    filter_invalid_v2_boq_rows,
)
from services.monthly_planning_scope_read_service import normalize_scope_raw_df
from utils.month_key import normalize_month_key


def skill_get_working_scope(
    scope_df: pd.DataFrame,
    scope_meta: dict[str, Any],
) -> dict[str, Any]:
    """1. Получить рабочий состав."""
    return {
        "skill": "get_working_scope",
        "label_ru": "Получить рабочий состав",
        "input": {"row_count_raw": int(scope_meta.get("row_count") or 0)},
        "output": {
            "df": scope_df,
            "meta": scope_meta,
            "error": scope_meta.get("error"),
        },
    }


def skill_calculate_availability(
    scope_df: pd.DataFrame,
    adjustments_df: pd.DataFrame,
) -> dict[str, Any]:
    """2. Рассчитать доступность (normalize + not_required once + metrics)."""
    normalized = normalize_scope_raw_df(scope_df)
    kept, excluded_invalid = filter_invalid_v2_boq_rows(normalized)
    with_nr = merge_not_required_once(kept, adjustments_df)
    # already_planned=0 at this stage; applied in next skill
    with_nr = with_nr.copy()
    if not with_nr.empty and "already_planned_qty" not in with_nr.columns:
        with_nr["already_planned_qty"] = 0.0
    metrics = _v2_apply_boq_availability_metrics(with_nr)
    if not metrics.empty:
        metrics["status"] = metrics.apply(_v2_resolve_scope_status_row, axis=1)
    return {
        "skill": "calculate_availability",
        "label_ru": "Рассчитать доступность",
        "input": {"scope_rows": len(scope_df), "adjustment_rows": len(adjustments_df)},
        "output": {
            "df": metrics,
            "excluded_invalid": excluded_invalid,
            "not_required_applied_once": True,
        },
    }


def skill_apply_existing_month_plan(
    availability_df: pd.DataFrame,
    plan_lines_df: pd.DataFrame,
    project_code: str,
    stored_month_key: str,
) -> dict[str, Any]:
    """3. Учесть существующий месячный план."""
    aggregates, issues = aggregate_already_planned(
        plan_lines_df,
        project_code=project_code,
        stored_month_key=stored_month_key,
    )
    with_plan = apply_already_planned_to_scope(availability_df, aggregates)
    # Recompute available after already_planned
    metrics = _v2_apply_boq_availability_metrics(with_plan)
    if not metrics.empty:
        metrics["status"] = metrics.apply(_v2_resolve_scope_status_row, axis=1)
    return {
        "skill": "apply_existing_month_plan",
        "label_ru": "Учесть существующий месячный план",
        "input": {"plan_line_rows": len(plan_lines_df)},
        "output": {
            "df": metrics,
            "aggregate_keys": len(aggregates),
            "issues": [i.to_dict() for i in issues],
        },
    }


def skill_exclude_unavailable(classified: dict[str, Any]) -> dict[str, Any]:
    """4. Исключить недоступное — uses classify counts/exclusions."""
    return {
        "skill": "exclude_unavailable",
        "label_ru": "Исключить недоступное",
        "input": {"scanned": classified.get("counts", {}).get("scanned", 0)},
        "output": {
            "exclusions": classified.get("exclusions", []),
            "counts": classified.get("counts", {}),
        },
    }


def skill_detect_conflicts(human_issues: list[dict[str, Any]]) -> dict[str, Any]:
    """5. Проверить конфликты."""
    conflict_codes = {
        "CONFLICTING_PLAN_LINES",
        "INCONSISTENT_QUANTITIES",
        "CANDIDATE_EXCEEDS_AVAILABLE",
        "INVALID_PLANNED_QTY",
    }
    conflicts = [i for i in human_issues if i.get("code") in conflict_codes]
    return {
        "skill": "detect_conflicts",
        "label_ru": "Проверить конфликты",
        "input": {"human_issue_count": len(human_issues)},
        "output": {"conflicts": conflicts, "conflict_count": len(conflicts)},
    }


def skill_build_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """6. Сформировать кандидатный состав."""
    return {
        "skill": "build_candidates",
        "label_ru": "Сформировать кандидатный состав",
        "input": {},
        "output": {"candidates": candidates, "count": len(candidates)},
    }


def skill_build_human_exceptions(
    human_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """7. Сформировать исключения для человека."""
    # Exclude routine missing crew/qty — those are human_required_fields on candidates.
    return {
        "skill": "build_human_exceptions",
        "label_ru": "Сформировать исключения для человека",
        "input": {},
        "output": {"human_issues": human_issues, "count": len(human_issues)},
    }


def skill_prepare_handoff(
    *,
    candidates: list[dict[str, Any]],
    human_issues: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    proposal_ok: bool,
) -> dict[str, Any]:
    """8. Подготовить результат для следующего этапа."""
    blockers = [
        i
        for i in human_issues
        if str(i.get("severity") or "").upper() == "BLOCKER"
    ]
    proposal_ready = bool(proposal_ok and not errors)
    # v0.1: candidates still need crew + planned_qty → admission handoff false
    admission_ready = False
    reason = (
        "Кандидаты сформированы; выбор crew/planned_qty и создание строк "
        "плана — за человеком / Admission Agent (не реализовано в v0.1)."
        if proposal_ready and candidates
        else (
            "Предложение пусто или заблокировано ошибками."
            if not proposal_ready
            else "Кандидатов нет; proposal готов как пустой результат."
        )
    )
    handoff = HandoffContract(
        recipient=HANDOFF_RECIPIENT,
        ready=admission_ready,
        reason=reason,
        candidate_count=len(candidates),
        blocking_issue_count=len(blockers),
        proposal_ready=proposal_ready,
        admission_handoff_ready=admission_ready,
    )
    return {
        "skill": "prepare_handoff",
        "label_ru": "Подготовить результат для следующего этапа",
        "input": {
            "candidate_count": len(candidates),
            "blocking_issue_count": len(blockers),
        },
        "output": {"handoff": handoff.to_dict()},
    }


def skill_run_pure_proposal(
    scope: pd.DataFrame,
    adjustments: pd.DataFrame,
    existing_plan_lines: pd.DataFrame,
    project_code: str,
    stored_month_key: str,
    **load_errors: Any,
) -> dict[str, Any]:
    """Facade skill around build_constructor_proposal."""
    return build_constructor_proposal(
        scope,
        adjustments,
        existing_plan_lines,
        project_code,
        stored_month_key,
        scope_load_error=load_errors.get("scope_load_error"),
        adjustments_load_error=load_errors.get("adjustments_load_error"),
        plan_lines_load_error=load_errors.get("plan_lines_load_error"),
    )


# Re-export classify for runtime convenience
__all__ = [
    "skill_get_working_scope",
    "skill_calculate_availability",
    "skill_apply_existing_month_plan",
    "skill_exclude_unavailable",
    "skill_detect_conflicts",
    "skill_build_candidates",
    "skill_build_human_exceptions",
    "skill_prepare_handoff",
    "skill_run_pure_proposal",
    "classify_scope_rows",
    "normalize_month_key",
]
