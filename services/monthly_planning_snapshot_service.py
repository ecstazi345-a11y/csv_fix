"""
MPO-002A — deterministic READ-ONLY Monthly Planning Snapshot.

Composes existing services. No Streamlit pages, no writes, no LLM.
SoT demand: monthly_plan_labor_lines_v1 / v2 labor_hours.
SoT capacity: load_approved_capacity (monthly_resource_capacity_v1).
monthly_labor_summary is never used as approved capacity.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from services.monthly_plan_labor_service import (
    load_labor_admission,
    load_labor_lines,
    to_num,
)
from services.monthly_plan_resource_economic_service import (
    CAPACITY_DATA_MISSING,
    build_resource_economic_models,
    resolve_required_hours,
)
from services.monthly_planning_boq_service import (
    _v2_apply_boq_availability_metrics,
    _v2_resolve_scope_status_row,
)
from services.monthly_planning_scope_read_service import load_monthly_boq_reality
from services.monthly_resource_plan_service import load_approved_capacity
from utils.month_key import normalize_month_key

SCOPE_REQUIRED_COLS = ("total_qty", "executed_qty")
ISSUE_MISSING_PLAN_LINE_ID = "missing_plan_line_id"
ISSUE_DUPLICATE_PLAN_LINE_ID = "duplicate_plan_line_id"
ISSUE_MONTH_NORMALIZATION = "month_normalization_issue"
ISSUE_CREW_UNTRIMMED = "crew_untrimmed"
ISSUE_MISSING_REQUIRED_HOURS = "missing_required_hours"
ISSUE_APPROVED_CAPACITY_MISSING = "approved_capacity_missing"
ISSUE_SCOPE_REMAINING_NOT_JOINED = "scope_remaining_not_joined"
ISSUE_ADMISSION_UNAVAILABLE = "admission_status_unavailable"
ISSUE_ZERO_PRICE_PHYSICAL_UNJOINED = "zero_price_physical_not_joined"
ISSUE_NOT_REQUIRED_NOT_APPLIED = "not_required_adjustments_not_applied"
ISSUE_SCOPE_READ_FAILED = "scope_read_failed"
ISSUE_PROJECT_CODE_BLANK = "blank_project_code"


def _safe_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _raw_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    return "" if text.strip().lower() == "nan" else text


def _json_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_int(value: Any) -> Optional[int]:
    num = _json_num(value)
    if num is None:
        return None
    return int(num)


def _crew_raw(row: pd.Series) -> str:
    if "crew_code" in row.index and _raw_str(row.get("crew_code")):
        return _raw_str(row.get("crew_code"))
    return _raw_str(row.get("crew"))


def _apply_optional_filters(
    lines: pd.DataFrame,
    *,
    plan_line_id: Optional[str],
    construction_discipline: Optional[str],
    facility_building: Optional[str],
    crew_code: Optional[str],
) -> pd.DataFrame:
    out = lines
    if plan_line_id:
        wanted = _safe_str(plan_line_id)
        pid = out["plan_line_id"].map(_safe_str) if "plan_line_id" in out.columns else pd.Series("", index=out.index)
        out = out.loc[pid == wanted]
    if construction_discipline:
        wanted = _safe_str(construction_discipline)
        disc = out["discipline"].map(_safe_str) if "discipline" in out.columns else pd.Series("", index=out.index)
        out = out.loc[disc == wanted]
    if facility_building:
        wanted = _safe_str(facility_building)
        fac = out["facility"].map(_safe_str) if "facility" in out.columns else pd.Series("", index=out.index)
        if "facility_building" in out.columns:
            fac = fac.where(fac != "", out["facility_building"].map(_safe_str))
        out = out.loc[fac == wanted]
    if crew_code:
        wanted = _safe_str(crew_code)
        crew = out.apply(_crew_raw, axis=1).map(str.strip) if not out.empty else pd.Series(dtype=str)
        out = out.loc[crew == wanted]
    return out.reset_index(drop=True)


def _strip_crew_columns(lines: pd.DataFrame) -> pd.DataFrame:
    out = lines.copy()
    if "crew" in out.columns:
        out["crew"] = out["crew"].map(_safe_str)
    if "crew_code" in out.columns:
        out["crew_code"] = out["crew_code"].map(_safe_str)
    elif "crew" in out.columns:
        out["crew_code"] = out["crew"]
    return out


def _admission_lookup(admission_df: Optional[pd.DataFrame]) -> dict[str, pd.Series]:
    if admission_df is None or admission_df.empty or "plan_line_id" not in admission_df.columns:
        return {}
    lookup: dict[str, pd.Series] = {}
    for _, row in admission_df.iterrows():
        pid = _safe_str(row.get("plan_line_id"))
        if pid:
            lookup[pid] = row
    return lookup


def _key_part(value: Any) -> str:
    return _safe_str(value).upper()


def _line_facility(row: pd.Series) -> str:
    return _key_part(row.get("facility") or row.get("facility_building"))


def _line_discipline(row: pd.Series) -> str:
    return _key_part(row.get("discipline") or row.get("construction_discipline"))


def scope_reality_join_key(row: pd.Series) -> Optional[tuple[str, str, str, str]]:
    """project + facility + discipline + boq. None if any part is blank (no remap)."""
    project = _key_part(row.get("project_code"))
    facility = _line_facility(row)
    discipline = _line_discipline(row)
    boq = _key_part(row.get("boq_code"))
    if not project or not facility or not discipline or not boq:
        return None
    return (project, facility, discipline, boq)


def _prepare_scope_metrics(scope_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if scope_df is None or scope_df.empty:
        return pd.DataFrame()
    if not all(col in scope_df.columns for col in SCOPE_REQUIRED_COLS):
        return pd.DataFrame()
    if "executed_total_qty" in scope_df.columns and "remaining_qty" in scope_df.columns:
        return scope_df.copy()
    return _v2_apply_boq_availability_metrics(scope_df.copy())


def _unique_scope_by_join_key(scope_df: Optional[pd.DataFrame]) -> dict[tuple[str, str, str, str], pd.Series]:
    metrics = _prepare_scope_metrics(scope_df)
    if metrics.empty:
        return {}
    counts: dict[tuple[str, str, str, str], int] = {}
    unique: dict[tuple[str, str, str, str], pd.Series] = {}
    for _, row in metrics.iterrows():
        key = scope_reality_join_key(row)
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
        unique[key] = row
    return {key: unique[key] for key, n in counts.items() if n == 1}


def _scope_fields_for_line(
    *,
    join_key: Optional[tuple[str, str, str, str]],
    plan_line_key_counts: dict[tuple[str, str, str, str], int],
    unique_scope: dict[tuple[str, str, str, str], pd.Series],
) -> tuple[Optional[float], Optional[float], Optional[bool], Optional[bool], list[str]]:
    missing: list[str] = []
    if (
        join_key is None
        or join_key not in unique_scope
        or plan_line_key_counts.get(join_key, 0) != 1
    ):
        missing.append(ISSUE_SCOPE_REMAINING_NOT_JOINED)
        missing.append(ISSUE_ZERO_PRICE_PHYSICAL_UNJOINED)
        return None, None, None, None, missing

    row = unique_scope[join_key]
    remaining = _json_num(row.get("remaining_qty"))
    executed = _json_num(row.get("executed_total_qty"))
    if executed is None:
        executed = _json_num(row.get("executed_qty"))
    status = _v2_resolve_scope_status_row(row)
    completed = status == "Выполнено"
    unit_price = to_num(row.get("unit_price"))
    total_qty = to_num(row.get("total_qty"))
    zero_price_physical = bool(total_qty > 0 and unit_price <= 0)
    missing.append(ISSUE_NOT_REQUIRED_NOT_APPLIED)
    return remaining, executed, completed, zero_price_physical, missing


def build_planning_snapshot(
    *,
    project_code: str,
    month_key: str,
    labor_lines_df: pd.DataFrame,
    approved_capacity_df: pd.DataFrame,
    plan_line_id: Optional[str] = None,
    construction_discipline: Optional[str] = None,
    facility_building: Optional[str] = None,
    crew_code: Optional[str] = None,
    admission_df: Optional[pd.DataFrame] = None,
    scope_df: Optional[pd.DataFrame] = None,
    scope_meta: Optional[dict[str, Any]] = None,
    roster_df: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    """
    Pure snapshot builder. Callers inject DataFrames (tests) or use load_planning_snapshot.

    roster_df is accepted only to document that MLS/roster is ignored.
    """
    del roster_df  # never used for feasibility

    month_canonical = normalize_month_key(month_key)
    dq_issues: list[dict[str, Any]] = []
    if not month_canonical:
        dq_issues.append({"code": ISSUE_MONTH_NORMALIZATION, "detail": str(month_key)})
    requested_project = _safe_str(project_code)
    if not requested_project:
        dq_issues.append({"code": ISSUE_PROJECT_CODE_BLANK, "detail": "requested project_code is blank"})

    scope_meta = dict(scope_meta or {})
    if scope_meta.get("error"):
        dq_issues.append(
            {
                "code": ISSUE_SCOPE_READ_FAILED,
                "detail": str(scope_meta.get("error")),
            }
        )

    filters = {
        "plan_line_id": plan_line_id,
        "construction_discipline": construction_discipline,
        "facility_building": facility_building,
        "crew_code": crew_code,
    }
    filters = {k: v for k, v in filters.items() if v not in (None, "")}

    raw_lines = labor_lines_df.copy() if labor_lines_df is not None else pd.DataFrame()
    if not raw_lines.empty:
        raw_lines = _apply_optional_filters(
            raw_lines,
            plan_line_id=plan_line_id,
            construction_discipline=construction_discipline,
            facility_building=facility_building,
            crew_code=crew_code,
        )

    for _, row in raw_lines.iterrows():
        raw_crew = _crew_raw(row)
        if raw_crew and raw_crew != raw_crew.strip():
            dq_issues.append(
                {
                    "code": ISSUE_CREW_UNTRIMMED,
                    "plan_line_id": _safe_str(row.get("plan_line_id")) or None,
                    "crew_code": raw_crew,
                }
            )

    missing_id_mask = (
        raw_lines["plan_line_id"].map(_safe_str) == ""
        if not raw_lines.empty and "plan_line_id" in raw_lines.columns
        else pd.Series(dtype=bool)
    )
    missing_id_count = int(missing_id_mask.sum()) if len(missing_id_mask) else 0
    if missing_id_count:
        dq_issues.append({"code": ISSUE_MISSING_PLAN_LINE_ID, "count": missing_id_count})

    identified = raw_lines.loc[~missing_id_mask].copy() if missing_id_count else raw_lines
    dup_ids: list[str] = []
    if not identified.empty and "plan_line_id" in identified.columns:
        pid_series = identified["plan_line_id"].map(_safe_str)
        dup_ids = sorted(pid_series[pid_series.duplicated()].unique().tolist())
        if dup_ids:
            dq_issues.append({"code": ISSUE_DUPLICATE_PLAN_LINE_ID, "plan_line_ids": dup_ids})
        identified = identified.loc[~pid_series.duplicated(keep="first")].copy()

    work_lines = _strip_crew_columns(identified)

    models = build_resource_economic_models(work_lines, approved_capacity_df)
    crew_model: pd.DataFrame = models["crew_model"]
    line_model: pd.DataFrame = models["line_model"]
    line_lookup = {
        _safe_str(row.get("plan_line_id")): row
        for _, row in line_model.iterrows()
        if _safe_str(row.get("plan_line_id"))
    }
    crew_lookup = {
        (
            _safe_str(row.get("project_code")),
            normalize_month_key(row.get("month_key")) or _safe_str(row.get("month_key")),
            _safe_str(row.get("crew_code")),
        ): row
        for _, row in crew_model.iterrows()
    }

    admission_map = _admission_lookup(admission_df)
    plan_line_key_counts: dict[tuple[str, str, str, str], int] = {}
    line_join_keys: dict[str, Optional[tuple[str, str, str, str]]] = {}
    for _, row in work_lines.iterrows():
        key = scope_reality_join_key(row)
        pid = _safe_str(row.get("plan_line_id"))
        line_join_keys[pid] = key
        if key is not None:
            plan_line_key_counts[key] = plan_line_key_counts.get(key, 0) + 1
    unique_scope = _unique_scope_by_join_key(scope_df)

    plan_lines: list[dict[str, Any]] = []
    blocking_line_count = 0
    required_hours_total = 0.0

    for _, src in work_lines.iterrows():
        pid = _safe_str(src.get("plan_line_id"))
        boq = _safe_str(src.get("boq_code"))
        crew = _safe_str(src.get("crew_code") or src.get("crew"))
        missing_data: list[str] = []
        source_refs = [
            "monthly_plan_labor_lines_v1",
            "monthly_resource_capacity_v1",
        ]

        hours, hours_ok = resolve_required_hours(src)
        if not hours_ok:
            missing_data.append(ISSUE_MISSING_REQUIRED_HOURS)
            dq_issues.append({"code": ISSUE_MISSING_REQUIRED_HOURS, "plan_line_id": pid})
            required_hours = None
        else:
            required_hours = float(hours)
            required_hours_total += required_hours

        econ = line_lookup.get(pid)
        feasibility_status = CAPACITY_DATA_MISSING if econ is None else _safe_str(econ.get("resource_status"))
        coverage = _json_num(econ.get("coverage")) if econ is not None else None
        feasible_qty = _json_num(econ.get("theoretical_feasible_qty")) if econ is not None else None
        crew_hours = _json_num(econ.get("crew_available_hours")) if econ is not None else None
        requested_qty = _json_num(econ.get("requested_qty")) if econ is not None else _json_num(src.get("planned_qty"))

        month_for_key = normalize_month_key(src.get("month_key")) or _safe_str(src.get("month_key"))
        crew_row = crew_lookup.get((_safe_str(src.get("project_code")), month_for_key, crew))
        gap_hours = _json_num(crew_row.get("hours_gap")) if crew_row is not None else None

        if feasibility_status == CAPACITY_DATA_MISSING:
            missing_data.append(ISSUE_APPROVED_CAPACITY_MISSING)
            coverage = None
            gap_hours = None
            feasible_qty = None
            crew_hours = None
            dq_issues.append({"code": ISSUE_APPROVED_CAPACITY_MISSING, "plan_line_id": pid, "crew_code": crew})

        remaining, executed, completed, zero_price, scope_missing = _scope_fields_for_line(
            join_key=line_join_keys.get(pid),
            plan_line_key_counts=plan_line_key_counts,
            unique_scope=unique_scope,
        )
        missing_data.extend(scope_missing)
        if remaining is not None:
            source_refs.append("monthly_scope_picker_view")

        adm = admission_map.get(pid)
        if adm is None:
            admission_status = None
            open_constraints = None
            blocking_constraints = None
            missing_data.append(ISSUE_ADMISSION_UNAVAILABLE)
        else:
            source_refs.append("monthly_plan_labor_admission_v1")
            admission_status = _safe_str(adm.get("admission_labor_status")) or None
            blocked = int(to_num(adm.get("blocked_cnt")))
            waiting = int(to_num(adm.get("waiting_cnt")))
            warning = int(to_num(adm.get("warning_cnt")))
            blocking_constraints = blocked
            open_constraints = blocked + waiting + warning
            if admission_status == "BLOCKED":
                blocking_line_count += 1

        plan_lines.append(
            {
                "plan_line_id": pid,
                "boq_code": boq or None,
                "crew_code": crew or None,
                "requested_qty": requested_qty,
                "remaining_qty": remaining,
                "executed_qty": executed,
                "completed": completed,
                "zero_price_physical": zero_price,
                "admission_status": admission_status,
                "open_constraints": open_constraints,
                "blocking_constraints": blocking_constraints,
                "required_hours": required_hours,
                "crew_approved_available_hours": crew_hours,
                "resource_coverage": coverage,
                "resource_gap_hours": gap_hours,
                "theoretical_feasible_qty": feasible_qty,
                "feasibility_status": feasibility_status or None,
                "missing_data": missing_data,
                "source_refs": source_refs,
            }
        )

    confirmed = crew_model
    if not confirmed.empty and "roster_row_count" in confirmed.columns:
        confirmed = confirmed[pd.to_numeric(confirmed["roster_row_count"], errors="coerce").fillna(0) > 0]
        confirmed = confirmed.drop_duplicates(subset=["project_code", "month_key", "crew_code"])
    approved_sum = 0.0
    if not confirmed.empty and "crew_available_hours" in confirmed.columns:
        approved_sum = float(
            pd.to_numeric(confirmed["crew_available_hours"], errors="coerce").fillna(0).sum()
        )

    missing_crew_count = 0
    if not crew_model.empty and "resource_status" in crew_model.columns:
        missing_crew_count = int(
            crew_model[crew_model["resource_status"] == CAPACITY_DATA_MISSING]
            .drop_duplicates(subset=["project_code", "month_key", "crew_code"])
            .shape[0]
        )

    if confirmed.empty and missing_crew_count > 0:
        approved_total: Optional[float] = None
    else:
        approved_total = approved_sum

    summary_coverage: Optional[float] = None
    summary_gap: Optional[float] = None
    if missing_crew_count == 0 and required_hours_total > 0 and approved_total is not None:
        summary_coverage = min(approved_total / required_hours_total, 1.0)
        summary_gap = approved_total - required_hours_total

    unique_issues: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in dq_issues:
        key = tuple(sorted((k, str(v)) for k, v in issue.items()))
        if key in seen:
            continue
        seen.add(key)
        unique_issues.append(issue)

    return {
        "run_scope": {
            "project_code": _safe_str(project_code),
            "month_key_input": month_key,
            "month_key_canonical": month_canonical,
            "filters": filters,
        },
        "summary": {
            "plan_line_count": len(plan_lines),
            "required_hours_total": required_hours_total,
            "approved_available_hours_total": approved_total,
            "resource_coverage": summary_coverage,
            "resource_gap_hours": summary_gap,
            "blocking_line_count": blocking_line_count,
            "capacity_data_missing_crew_count": missing_crew_count,
        },
        "plan_lines": plan_lines,
        "data_quality": {
            "issues": unique_issues,
            "treat_as_planning_change": False,
        },
        "source_trace": {
            "labor_demand": "monthly_plan_labor_lines_v1",
            "approved_capacity": "monthly_resource_capacity_v1 via load_approved_capacity",
            "feasibility": "monthly_plan_resource_economic_service.build_resource_economic_models",
            "admission": "monthly_plan_labor_admission_v1 via load_labor_admission",
            "boq_reality": "monthly_scope_picker_view via load_monthly_boq_reality",
            "boq_metrics": "monthly_planning_boq_service (unique project+facility+discipline+boq)",
            "scope_time_basis": "all_time",
            "manual_not_required_adjustments_applied": False,
            "remaining_semantics": "raw_physical_pre_not_required_adjustments",
            "month_normalizer": "utils.month_key.normalize_month_key",
            "mls_used_as_capacity": False,
            "no_llm": True,
            "scope_read_error": scope_meta.get("error"),
        },
    }


def _safe_load_boq_reality(project_code: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        return load_monthly_boq_reality(project_code=project_code)
    except Exception as exc:  # noqa: BLE001
        return pd.DataFrame(), {
            "source": "monthly_scope_picker_view",
            "error": f"{type(exc).__name__}: {exc}",
            "manual_not_required_adjustments_applied": False,
            "scope_time_basis": "all_time",
        }


def load_planning_snapshot(
    *,
    project_code: str,
    month_key: str,
    plan_line_id: Optional[str] = None,
    construction_discipline: Optional[str] = None,
    facility_building: Optional[str] = None,
    crew_code: Optional[str] = None,
) -> dict[str, Any]:
    """Live READ-ONLY load. Does not write. Does not use MLS as capacity."""
    labor = load_labor_lines(project_code=project_code, month_key=month_key)
    capacity = load_approved_capacity(project_code=project_code, month_key=month_key)
    admission = load_labor_admission(project_code=project_code, month_key=month_key)
    scope_df, scope_meta = _safe_load_boq_reality(project_code)
    return build_planning_snapshot(
        project_code=project_code,
        month_key=month_key,
        labor_lines_df=labor,
        approved_capacity_df=capacity,
        plan_line_id=plan_line_id,
        construction_discipline=construction_discipline,
        facility_building=facility_building,
        crew_code=crew_code,
        admission_df=admission,
        scope_df=scope_df,
        scope_meta=scope_meta,
        roster_df=None,
    )
