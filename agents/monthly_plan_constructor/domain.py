"""
MPCA-001 — pure deterministic domain for Constructor Agent.

No Supabase. No Streamlit. No LLM. No product writes.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from agents.monthly_plan_constructor.contracts import (
    CANDIDATE_OPEN,
    CANDIDATE_PARTIAL,
    Candidate,
    ExclusionRecord,
    HumanIssue,
)
from services.monthly_planning_boq_service import (
    _v2_apply_boq_availability_metrics,
    _v2_resolve_scope_status_row,
    _v2_safe_num,
    filter_invalid_v2_boq_rows,
)
from services.monthly_planning_scope_read_service import normalize_scope_raw_df
from utils.month_key import normalize_month_key

# Product Constructor statuses that reserve monthly volume (pages/10B).
ACTIVE_PLAN_LINE_STATUSES = frozenset({"NOT_SENT", "SENT_TO_ADMISSION"})

STATUS_COMPLETED = "Выполнено"
STATUS_NOT_REQUIRED = "Остаток не требуется"
STATUS_OVERRUN = "Превышение BOQ"
STATUS_NO_REMAINDER = "Нет остатка"
STATUS_FULLY_PLANNED = "Запланировано полностью"
STATUS_OVERPLANNED = "Перепланировано"
STATUS_PARTIAL = "Частично запланировано"
STATUS_AVAILABLE = "Доступно"

REASON_COMPLETED = "EXCLUDED_COMPLETED"
REASON_NO_REMAINDER = "EXCLUDED_NO_REMAINDER"
REASON_ALREADY_PLANNED = "EXCLUDED_ALREADY_PLANNED"
REASON_INVALID = "EXCLUDED_INVALID"
REASON_OVERRUN = "EXCLUDED_OVERRUN"
REASON_NOT_REQUIRED = "EXCLUDED_NOT_REQUIRED"


def _safe_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text


def _norm_key_part(value: Any) -> str:
    return _safe_text(value).upper()


def adjustment_record_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    """Same grain as Page10B _v2_adjustment_record_key."""
    return (
        _norm_key_part(record.get("project_code")),
        _norm_key_part(
            record.get("facility_building") or record.get("facility")
        ),
        _norm_key_part(
            record.get("construction_discipline") or record.get("discipline")
        ),
        _norm_key_part(record.get("boq_code")),
    )


def planning_grain_key(
    project_code: Any,
    facility: Any,
    discipline: Any,
    boq_code: Any,
) -> tuple[str, str, str, str]:
    return (
        _norm_key_part(project_code),
        _norm_key_part(facility),
        _norm_key_part(discipline),
        _norm_key_part(boq_code),
    )


def merge_not_required_once(
    scope_df: pd.DataFrame,
    adjustments_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply not_required_qty from adjustments exactly once.

    View already includes manual_executed_before_system — do NOT re-apply it.
    """
    if scope_df is None or scope_df.empty:
        return pd.DataFrame() if scope_df is None else scope_df.copy()

    out = scope_df.copy()
    out["not_required_qty"] = 0.0
    out["not_required_reason"] = ""

    if adjustments_df is None or adjustments_df.empty:
        return out
    if "not_required_qty" not in adjustments_df.columns:
        return out

    lookup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for _, row in adjustments_df.iterrows():
        rec = row.to_dict()
        key = adjustment_record_key(rec)
        if not key[3]:
            continue
        lookup[key] = rec

    for idx, row in out.iterrows():
        key = planning_grain_key(
            row.get("project_code"),
            row.get("facility"),
            row.get("discipline"),
            row.get("boq_code"),
        )
        rec = lookup.get(key)
        if not rec:
            continue
        out.at[idx, "not_required_qty"] = _v2_safe_num(rec.get("not_required_qty"))
        out.at[idx, "not_required_reason"] = _safe_text(rec.get("not_required_reason"))
    return out


def aggregate_already_planned(
    plan_lines_df: pd.DataFrame,
    *,
    project_code: str,
    stored_month_key: str,
) -> tuple[dict[tuple[str, str, str, str], dict[str, Any]], list[HumanIssue]]:
    """
    Aggregate planned_qty by project + facility + discipline + boq_code.

    Uses product active statuses: NOT_SENT, SENT_TO_ADMISSION.
    Month match uses stored RU month_key exactly.
    """
    issues: list[HumanIssue] = []
    aggregates: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    if plan_lines_df is None or plan_lines_df.empty:
        return aggregates, issues

    code = _safe_text(project_code)
    month = _safe_text(stored_month_key)
    for _, row in plan_lines_df.iterrows():
        row_project = _safe_text(row.get("project_code"))
        row_month = _safe_text(row.get("month_key"))
        if code and row_project and row_project != code:
            continue
        if month and row_month and row_month != month:
            continue

        status = _safe_text(row.get("status")) or "NOT_SENT"
        if status not in ACTIVE_PLAN_LINE_STATUSES:
            issues.append(
                HumanIssue(
                    code="UNKNOWN_PLAN_LINE_STATUS",
                    severity="WARNING",
                    message=(
                        f"Статус plan line «{status}» вне известной семантики "
                        f"Constructor ({sorted(ACTIVE_PLAN_LINE_STATUSES)}); "
                        "qty не включена в already_planned."
                    ),
                    boq_code=_safe_text(row.get("boq_code")),
                    evidence={
                        "plan_line_id": _safe_text(row.get("plan_line_id")),
                        "status": status,
                    },
                )
            )
            continue

        key = planning_grain_key(
            row_project or code,
            row.get("facility") or row.get("facility_building"),
            row.get("discipline") or row.get("construction_discipline"),
            row.get("boq_code"),
        )
        if not key[3]:
            issues.append(
                HumanIssue(
                    code="AMBIGUOUS_PLAN_LINE_SCOPE",
                    severity="WARNING",
                    message="Строка плана без boq_code — не агрегирована.",
                    evidence={"plan_line_id": _safe_text(row.get("plan_line_id"))},
                )
            )
            continue

        bucket = aggregates.setdefault(
            key,
            {
                "already_planned_qty": 0.0,
                "plan_line_ids": [],
                "systems": set(),
                "iwps": set(),
                "crews": set(),
                "client_line_uids": set(),
            },
        )
        qty = _v2_safe_num(row.get("planned_qty"))
        if qty < 0:
            issues.append(
                HumanIssue(
                    code="INVALID_PLANNED_QTY",
                    severity="BLOCKER",
                    message="Отрицательный planned_qty в существующей строке плана.",
                    boq_code=key[3],
                    evidence={
                        "plan_line_id": _safe_text(row.get("plan_line_id")),
                        "planned_qty": qty,
                    },
                )
            )
            continue
        bucket["already_planned_qty"] += qty
        pid = _safe_text(row.get("plan_line_id"))
        if pid:
            bucket["plan_line_ids"].append(pid)
        sys = _safe_text(row.get("system"))
        iwp = _safe_text(row.get("iwp"))
        crew = _safe_text(row.get("crew") or row.get("crew_code"))
        cuid = _safe_text(row.get("client_line_uid"))
        if sys:
            bucket["systems"].add(sys)
        if iwp:
            bucket["iwps"].add(iwp)
        if crew:
            bucket["crews"].add(crew)
        if cuid:
            bucket["client_line_uids"].add(cuid)

    for key, bucket in aggregates.items():
        if len(bucket["systems"]) > 1 or len(bucket["iwps"]) > 1:
            issues.append(
                HumanIssue(
                    code="CONFLICTING_PLAN_LINES",
                    severity="BLOCKER",
                    message=(
                        "Несколько строк плана по одной BOQ-зернистости "
                        "с разными system/iwp."
                    ),
                    scope_key="|".join(key),
                    boq_code=key[3],
                    evidence={
                        "systems": sorted(bucket["systems"]),
                        "iwps": sorted(bucket["iwps"]),
                        "plan_line_ids": list(bucket["plan_line_ids"]),
                        "crews": sorted(bucket["crews"]),
                    },
                )
            )
    return aggregates, issues


def _enrich_scope_context_columns(
    normalized: pd.DataFrame,
    raw_scope: pd.DataFrame,
) -> pd.DataFrame:
    """Attach system/iwp/unit from raw view when present."""
    out = normalized.copy()
    if raw_scope is None or raw_scope.empty or out.empty:
        for col in ("system", "iwp", "unit"):
            if col not in out.columns:
                out[col] = ""
        return out

    raw = raw_scope.copy()
    raw["_join_boq"] = raw.get("boq_code", pd.Series([""] * len(raw))).map(_norm_key_part)
    fac_col = "facility" if "facility" in raw.columns else "facility_building"
    disc_col = "discipline" if "discipline" in raw.columns else "construction_discipline"
    raw["_join_fac"] = raw.get(fac_col, pd.Series([""] * len(raw))).map(_norm_key_part)
    raw["_join_disc"] = raw.get(disc_col, pd.Series([""] * len(raw))).map(_norm_key_part)
    raw["_join_proj"] = raw.get("project_code", pd.Series([""] * len(raw))).map(_norm_key_part)

    lookup: dict[tuple[str, str, str, str], dict[str, str]] = {}
    for _, row in raw.iterrows():
        key = (
            _safe_text(row.get("_join_proj")),
            _safe_text(row.get("_join_fac")),
            _safe_text(row.get("_join_disc")),
            _safe_text(row.get("_join_boq")),
        )
        lookup[key] = {
            "system": _safe_text(row.get("system")),
            "iwp": _safe_text(row.get("iwp")),
            "unit": _safe_text(row.get("unit")),
        }

    systems: list[str] = []
    iwps: list[str] = []
    units: list[str] = []
    for _, row in out.iterrows():
        key = planning_grain_key(
            row.get("project_code"),
            row.get("facility"),
            row.get("discipline"),
            row.get("boq_code"),
        )
        ctx = lookup.get(key, {})
        systems.append(ctx.get("system", ""))
        iwps.append(ctx.get("iwp", ""))
        units.append(ctx.get("unit", ""))
    out["system"] = systems
    out["iwp"] = iwps
    out["unit"] = units
    return out


def apply_already_planned_to_scope(
    scope_df: pd.DataFrame,
    aggregates: dict[tuple[str, str, str, str], dict[str, Any]],
) -> pd.DataFrame:
    out = scope_df.copy()
    planned_vals: list[float] = []
    ids_vals: list[list[str]] = []
    for _, row in out.iterrows():
        key = planning_grain_key(
            row.get("project_code"),
            row.get("facility"),
            row.get("discipline"),
            row.get("boq_code"),
        )
        bucket = aggregates.get(key)
        if not bucket:
            planned_vals.append(0.0)
            ids_vals.append([])
        else:
            planned_vals.append(float(bucket["already_planned_qty"]))
            ids_vals.append(list(bucket["plan_line_ids"]))
    out["already_planned_qty"] = planned_vals
    out["_existing_plan_line_ids"] = ids_vals
    return out


def _exclusion_for_status(
    row: pd.Series,
    status: str,
) -> Optional[ExclusionRecord]:
    scope_key = "|".join(
        planning_grain_key(
            row.get("project_code"),
            row.get("facility"),
            row.get("discipline"),
            row.get("boq_code"),
        )
    )
    base = dict(
        scope_key=scope_key,
        boq_code=_safe_text(row.get("boq_code")),
        facility=_safe_text(row.get("facility")),
        discipline=_safe_text(row.get("discipline")),
    )
    if status == STATUS_COMPLETED:
        return ExclusionRecord(
            reason_code=REASON_COMPLETED,
            reason_text="Позиция полностью выполнена (executed >= total).",
            **base,
        )
    if status == STATUS_NOT_REQUIRED:
        return ExclusionRecord(
            reason_code=REASON_NOT_REQUIRED,
            reason_text="Остаток не требуется по adjustment.",
            **base,
        )
    if status == STATUS_OVERRUN:
        return ExclusionRecord(
            reason_code=REASON_OVERRUN,
            reason_text="Превышение BOQ — не кандидат.",
            **base,
        )
    if status == STATUS_NO_REMAINDER:
        return ExclusionRecord(
            reason_code=REASON_NO_REMAINDER,
            reason_text="Физический остаток отсутствует.",
            **base,
        )
    if status in {STATUS_FULLY_PLANNED, STATUS_OVERPLANNED}:
        return ExclusionRecord(
            reason_code=REASON_ALREADY_PLANNED,
            reason_text="Доступный к добавлению объём исчерпан существующим планом.",
            **base,
        )
    available = _v2_safe_num(row.get("available_to_add_qty"))
    remaining = _v2_safe_num(row.get("remaining_qty"))
    if remaining <= 0:
        return ExclusionRecord(
            reason_code=REASON_NO_REMAINDER,
            reason_text="Нет остатка после расчёта availability.",
            **base,
        )
    if available <= 0:
        return ExclusionRecord(
            reason_code=REASON_ALREADY_PLANNED,
            reason_text="available_to_add_qty <= 0.",
            **base,
        )
    return None


def classify_scope_rows(
    scope_df: pd.DataFrame,
    *,
    project_code: str,
    stored_month_key: str,
    month_key_canonical: str,
) -> tuple[list[Candidate], list[ExclusionRecord], list[HumanIssue], dict[str, int]]:
    candidates: list[Candidate] = []
    exclusions: list[ExclusionRecord] = []
    issues: list[HumanIssue] = []
    counts = {
        "scanned": 0,
        "candidates": 0,
        "excluded_completed": 0,
        "excluded_no_remainder": 0,
        "excluded_already_planned": 0,
        "excluded_invalid": 0,
        "excluded_other": 0,
        "conflicts": 0,
    }
    if scope_df is None or scope_df.empty:
        return candidates, exclusions, issues, counts

    for _, row in scope_df.iterrows():
        counts["scanned"] += 1
        boq = _safe_text(row.get("boq_code"))
        facility = _safe_text(row.get("facility"))
        discipline = _safe_text(row.get("discipline"))
        proj = _safe_text(row.get("project_code")) or _safe_text(project_code)

        if not boq or not proj:
            counts["excluded_invalid"] += 1
            exclusions.append(
                ExclusionRecord(
                    scope_key=f"{proj}|{facility}|{discipline}|{boq}",
                    boq_code=boq,
                    facility=facility,
                    discipline=discipline,
                    reason_code=REASON_INVALID,
                    reason_text="Неполный ключ scope (project/boq).",
                )
            )
            issues.append(
                HumanIssue(
                    code="AMBIGUOUS_SCOPE",
                    severity="WARNING",
                    message="Строка scope без project_code или boq_code.",
                    boq_code=boq or None,
                    evidence={"facility": facility, "discipline": discipline},
                )
            )
            continue

        # Detect silent negative before clip semantics already applied in metrics.
        raw_available = (
            _v2_safe_num(row.get("effective_required_qty"))
            - _v2_safe_num(row.get("executed_total_qty"))
            - _v2_safe_num(row.get("already_planned_qty"))
        )
        if raw_available < -1e-9 and _v2_safe_num(row.get("overrun_qty")) <= 0:
            issues.append(
                HumanIssue(
                    code="INCONSISTENT_QUANTITIES",
                    severity="BLOCKER",
                    message="already_planned превышает физический остаток.",
                    scope_key=f"{proj}|{facility}|{discipline}|{boq}",
                    boq_code=boq,
                    evidence={
                        "raw_available_before_clip": raw_available,
                        "already_planned_qty": _v2_safe_num(row.get("already_planned_qty")),
                        "remaining_qty": _v2_safe_num(row.get("remaining_qty")),
                    },
                )
            )
            counts["conflicts"] += 1

        status = _safe_text(row.get("status")) or _v2_resolve_scope_status_row(row)
        excl = _exclusion_for_status(row, status)
        if excl is not None:
            exclusions.append(excl)
            if excl.reason_code == REASON_COMPLETED:
                counts["excluded_completed"] += 1
            elif excl.reason_code in {REASON_NO_REMAINDER, REASON_NOT_REQUIRED}:
                counts["excluded_no_remainder"] += 1
            elif excl.reason_code == REASON_ALREADY_PLANNED:
                counts["excluded_already_planned"] += 1
            elif excl.reason_code == REASON_INVALID:
                counts["excluded_invalid"] += 1
            else:
                counts["excluded_other"] += 1
            continue

        available = _v2_safe_num(row.get("available_to_add_qty"))
        planned = _v2_safe_num(row.get("already_planned_qty"))
        state = CANDIDATE_PARTIAL if planned > 0 else CANDIDATE_OPEN
        ids = row.get("_existing_plan_line_ids") or []
        if not isinstance(ids, list):
            ids = list(ids) if ids is not None else []

        candidate = Candidate(
            project_code=proj,
            month_key=stored_month_key,
            month_key_canonical=month_key_canonical,
            facility=facility,
            discipline=discipline,
            system=_safe_text(row.get("system")),
            iwp=_safe_text(row.get("iwp")),
            boq_code=boq,
            boq_name=_safe_text(row.get("boq_name")),
            unit=_safe_text(row.get("unit")),
            total_qty=_v2_safe_num(row.get("total_qty")),
            executed_total_qty=_v2_safe_num(row.get("executed_total_qty")),
            not_required_qty=_v2_safe_num(row.get("not_required_qty")),
            effective_required_qty=_v2_safe_num(row.get("effective_required_qty")),
            remaining_qty=_v2_safe_num(row.get("remaining_qty")),
            already_planned_qty=planned,
            available_to_add_qty=available,
            availability_status=status or STATUS_AVAILABLE,
            existing_plan_line_ids=[str(x) for x in ids],
            candidate_state=state,
            issues=[],
            human_required_fields=["crew", "planned_qty"],
            proposed_plan_qty=None,
            proposed_crew=None,
        )
        if candidate.available_to_add_qty > candidate.remaining_qty + 1e-9:
            issues.append(
                HumanIssue(
                    code="CANDIDATE_EXCEEDS_AVAILABLE",
                    severity="BLOCKER",
                    message="available_to_add_qty превышает remaining_qty.",
                    boq_code=boq,
                    evidence={
                        "available_to_add_qty": candidate.available_to_add_qty,
                        "remaining_qty": candidate.remaining_qty,
                    },
                )
            )
            counts["conflicts"] += 1
            continue

        candidates.append(candidate)
        counts["candidates"] += 1

    return candidates, exclusions, issues, counts


def build_constructor_proposal(
    scope: pd.DataFrame,
    adjustments: pd.DataFrame,
    existing_plan_lines: pd.DataFrame,
    project_code: str,
    stored_month_key: str,
    *,
    scope_load_error: Optional[str] = None,
    adjustments_load_error: Optional[str] = None,
    plan_lines_load_error: Optional[str] = None,
) -> dict[str, Any]:
    """
    Pure core: data in → structured proposal out.

    Does not touch Supabase / Streamlit / LLM.
    """
    canonical = normalize_month_key(stored_month_key)
    errors: list[dict[str, Any]] = []
    human_issues: list[HumanIssue] = []

    if not _safe_text(project_code):
        errors.append({"code": "BLANK_PROJECT", "message": "project_code пуст"})
    if canonical is None:
        errors.append(
            {
                "code": "INVALID_MONTH",
                "message": f"Не удалось нормализовать month_key={stored_month_key!r}",
            }
        )
    if scope_load_error:
        errors.append(
            {
                "code": "SCOPE_READ_FAILED",
                "message": scope_load_error,
            }
        )
    if plan_lines_load_error:
        errors.append(
            {
                "code": "PLAN_LINES_READ_FAILED",
                "message": plan_lines_load_error,
            }
        )
    if adjustments_load_error:
        human_issues.append(
            HumanIssue(
                code="ADJUSTMENTS_READ_FAILED",
                severity="WARNING",
                message=adjustments_load_error,
            )
        )

    if scope_load_error or not _safe_text(project_code) or canonical is None:
        return {
            "ok": False,
            "month_key_canonical": canonical,
            "candidates": [],
            "exclusions": [],
            "human_issues": [i.to_dict() for i in human_issues],
            "counts": {
                "scanned": 0,
                "candidates": 0,
                "excluded_completed": 0,
                "excluded_no_remainder": 0,
                "excluded_already_planned": 0,
                "excluded_invalid": 0,
                "conflicts": 0,
                "human_issues": len(human_issues),
            },
            "errors": errors,
            "meta": {
                "not_required_applied_once": False,
                "manual_executed_reapplied": False,
                "active_plan_statuses": sorted(ACTIVE_PLAN_LINE_STATUSES),
            },
        }

    raw_scope = scope if isinstance(scope, pd.DataFrame) else pd.DataFrame()
    if raw_scope.empty and not scope_load_error:
        # Empty scope without error is valid (no rows) — not silent zero from failure.
        pass

    normalized = normalize_scope_raw_df(raw_scope)
    normalized = _enrich_scope_context_columns(normalized, raw_scope)
    kept, excluded_invalid = filter_invalid_v2_boq_rows(normalized)

    invalid_exclusions: list[ExclusionRecord] = []
    if excluded_invalid > 0 and not normalized.empty:
        # Rows dropped by filter — record as invalid exclusions at aggregate level.
        invalid_exclusions.append(
            ExclusionRecord(
                scope_key="*",
                boq_code="",
                reason_code=REASON_INVALID,
                reason_text=(
                    f"Исключено {excluded_invalid} пустых/невалидных BOQ-строк "
                    "(нет цены, стоимости, остатка и объёма)."
                ),
            )
        )

    with_nr = merge_not_required_once(kept, adjustments)
    aggregates, plan_issues = aggregate_already_planned(
        existing_plan_lines,
        project_code=project_code,
        stored_month_key=stored_month_key,
    )
    human_issues.extend(plan_issues)

    with_plan = apply_already_planned_to_scope(with_nr, aggregates)
    metrics = _v2_apply_boq_availability_metrics(with_plan)
    if not metrics.empty:
        metrics["status"] = metrics.apply(_v2_resolve_scope_status_row, axis=1)

    candidates, exclusions, class_issues, counts = classify_scope_rows(
        metrics,
        project_code=project_code,
        stored_month_key=stored_month_key,
        month_key_canonical=canonical,
    )
    exclusions = invalid_exclusions + exclusions
    counts["excluded_invalid"] = int(counts.get("excluded_invalid", 0)) + int(
        excluded_invalid
    )
    human_issues.extend(class_issues)

    conflict_codes = {
        "CONFLICTING_PLAN_LINES",
        "INCONSISTENT_QUANTITIES",
        "CANDIDATE_EXCEEDS_AVAILABLE",
        "INVALID_PLANNED_QTY",
    }
    conflict_count = sum(1 for i in human_issues if i.code in conflict_codes)
    counts["conflicts"] = max(int(counts.get("conflicts", 0)), conflict_count)
    counts["human_issues"] = len(human_issues)

    scanned = int(counts.get("scanned", 0))
    auto_classified = scanned  # every scanned row gets candidate or exclusion
    automation_ratio = (auto_classified / scanned) if scanned > 0 else 0.0

    return {
        "ok": len(errors) == 0,
        "month_key_canonical": canonical,
        "candidates": [c.to_dict() for c in candidates],
        "exclusions": [e.to_dict() for e in exclusions],
        "human_issues": [i.to_dict() for i in human_issues],
        "counts": counts,
        "errors": errors,
        "meta": {
            "not_required_applied_once": True,
            "manual_executed_reapplied": False,
            "excluded_invalid_filter": excluded_invalid,
            "active_plan_statuses": sorted(ACTIVE_PLAN_LINE_STATUSES),
            "automation_ratio": automation_ratio,
        },
    }
