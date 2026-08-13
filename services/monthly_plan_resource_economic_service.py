"""
Deterministic read-model for Page 22 — Resource + Economic Feasibility (R1/R1.2).

DataFrame in → DataFrame/dict out. No Streamlit, no Supabase writes.
SoT hours: monthly_plan_lines_v2.labor_hours via monthly_plan_labor_lines_v1.
SoT capacity (R1.2): APPROVED monthly resource plan (crew grain).
Legacy monthly_plan_capacity_v1 is diagnostic only — not commitment capacity.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from services.monthly_plan_labor_service import to_num
from utils.month_key import normalize_month_key

# --- Resource statuses (presentation-only, R1) ---
RESOURCE_READY = "RESOURCE_READY"
PARTIALLY_FEASIBLE = "PARTIALLY_FEASIBLE"
RESOURCE_DEFICIT = "RESOURCE_DEFICIT"
CAPACITY_DATA_MISSING = "CAPACITY_DATA_MISSING"
NOT_CALCULATED = "NOT_CALCULATED"

# --- Economic statuses ---
ECONOMIC_OK = "ECONOMIC_OK"
ECONOMIC_DEFICIT = "ECONOMIC_DEFICIT"
PRICE_NOT_DEFINED = "PRICE_NOT_DEFINED"

# --- Combined presentation labels (Russian) ---
COMBINED_READY = "ГОТОВО К РАССМОТРЕНИЮ"
COMBINED_RESOURCE_RISK = "ДЕФИЦИТ РЕСУРСА"
COMBINED_ECONOMIC_RISK = "ЭКОНОМИЧЕСКИЙ РИСК"
COMBINED_BOTH_RISK = "РЕСУРСНЫЙ + ЭКОНОМИЧЕСКИЙ РИСК"
COMBINED_PRICE_UNDEFINED = "ЦЕНА НЕ ОПРЕДЕЛЕНА"
COMBINED_NOT_CALCULATED = "НЕ РАССЧИТАНО"

RESOURCE_STATUS_RU = {
    RESOURCE_READY: "Ресурс обеспечен",
    PARTIALLY_FEASIBLE: "Ресурса недостаточно",
    RESOURCE_DEFICIT: "Ресурс отсутствует",
    CAPACITY_DATA_MISSING: "Ресурсный план не сформирован",
    NOT_CALCULATED: "Не рассчитано",
}

ECONOMIC_STATUS_RU = {
    ECONOMIC_OK: "Экономически OK",
    ECONOMIC_DEFICIT: "Экономический дефицит",
    PRICE_NOT_DEFINED: "Цена не определена",
}

CREW_LINE_COLUMNS = [
    "plan_line_id",
    "project_code",
    "month_key",
    "boq_code",
    "boq_name",
    "facility",
    "discipline",
    "crew_code",
    "planned_qty",
    "unit",
    "labor_hours",
    "norm_hours_per_unit_effective",
    "labor_cost",
    "plan_value",
    "unit_price",
    "crew_size",
]

CREW_MODEL_COLUMNS = [
    "project_code",
    "month_key",
    "crew_code",
    "boq_count",
    "crew_required_hours",
    "crew_available_hours",
    "hours_gap",
    "coverage",
    "coverage_pct",
    "fte_required",
    "available_fte",
    "fte_gap",
    "roster_row_count",
    "plan_value_total",
    "labor_cost_total",
    "economic_gap",
    "resource_status",
    "economic_status",
    "combined_status",
    "capacity_row_exists",
]

LINE_MODEL_COLUMNS = [
    "plan_line_id",
    "project_code",
    "month_key",
    "boq_code",
    "boq_name",
    "facility",
    "discipline",
    "crew_code",
    "crew_size",
    "requested_qty",
    "unit",
    "required_hours",
    "norm_hours_per_unit",
    "crew_required_hours_total",
    "crew_available_hours",
    "coverage",
    "coverage_pct",
    "theoretical_feasible_qty",
    "volume_deficit_qty",
    "unit_price",
    "requested_work_value",
    "feasible_work_value",
    "requested_labor_cost",
    "feasible_labor_cost",
    "economic_gap",
    "feasible_economic_gap",
    "resource_status",
    "economic_status",
    "combined_status",
]


def _empty_crew_model() -> pd.DataFrame:
    return pd.DataFrame(columns=CREW_MODEL_COLUMNS)


def _empty_line_model() -> pd.DataFrame:
    return pd.DataFrame(columns=LINE_MODEL_COLUMNS)


def _safe_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def _crew_key(project_code: Any, month_key: Any, crew_code: Any) -> tuple[str, str, str]:
    """Join key uses canonical YYYY-MM when month_key is parseable (R1.2)."""
    raw_month = _safe_str(month_key)
    month = normalize_month_key(raw_month) or raw_month
    return (
        _safe_str(project_code),
        month,
        _safe_str(crew_code),
    )


def normalize_labor_lines_df(lines_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize labor lines view columns to internal names."""
    if lines_df is None or lines_df.empty:
        return pd.DataFrame(columns=CREW_LINE_COLUMNS)

    out = lines_df.copy()
    if "crew_code" not in out.columns and "crew" in out.columns:
        out["crew_code"] = out["crew"]
    if "unit" not in out.columns and "unit_of_measure" in out.columns:
        out["unit"] = out["unit_of_measure"]
    if "facility" not in out.columns and "facility_building" in out.columns:
        out["facility"] = out["facility_building"]

    for col in CREW_LINE_COLUMNS:
        if col not in out.columns:
            out[col] = None

    return out


def normalize_capacity_df(capacity_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize capacity view; index by project+month+crew."""
    if capacity_df is None or capacity_df.empty:
        return pd.DataFrame()

    out = capacity_df.copy()
    if "crew_code" not in out.columns and "crew" in out.columns:
        out["crew_code"] = out["crew"]
    return out


def resolve_required_hours(row: pd.Series) -> tuple[float, bool]:
    """
    Return (hours, is_calculated).
    is_calculated False → NOT_CALCULATED for resource feasibility.
    """
    hours = to_num(row.get("labor_hours"), default=-1.0)
    if hours > 0:
        return hours, True

    qty = to_num(row.get("planned_qty"))
    norm = to_num(row.get("norm_hours_per_unit_effective"), default=-1.0)
    if qty > 0 and norm > 0:
        return qty * norm, True

    return 0.0, False


def classify_economic_status(plan_value: float, labor_cost: float) -> str:
    if plan_value <= 0:
        return PRICE_NOT_DEFINED
    if labor_cost > plan_value:
        return ECONOMIC_DEFICIT
    return ECONOMIC_OK


def classify_resource_status_from_coverage(
    *,
    hours_calculated: bool,
    crew_code: str,
    capacity_row_exists: bool,
    roster_row_count: int,
    available_hours: float,
    required_hours: float,
    coverage: Optional[float],
) -> str:
    """R1.1: roster_row_count distinguishes missing capacity from real zero capacity."""
    if not hours_calculated or not crew_code:
        return NOT_CALCULATED
    if not capacity_row_exists or roster_row_count <= 0:
        return CAPACITY_DATA_MISSING
    if available_hours <= 0 and required_hours > 0:
        return RESOURCE_DEFICIT
    if coverage is None:
        return NOT_CALCULATED
    if coverage >= 1.0:
        return RESOURCE_READY
    if coverage > 0:
        return PARTIALLY_FEASIBLE
    return RESOURCE_DEFICIT


def count_crews_missing_capacity(crew_model: pd.DataFrame) -> int:
    """Unique crews with CAPACITY_DATA_MISSING (no double-count)."""
    if crew_model.empty or "resource_status" not in crew_model.columns:
        return 0
    missing = crew_model[crew_model["resource_status"] == CAPACITY_DATA_MISSING]
    if missing.empty:
        return 0
    return int(
        missing.drop_duplicates(subset=["project_code", "month_key", "crew_code"]).shape[0]
    )


def _has_confirmed_roster(capacity_row_exists: bool, roster_row_count: int) -> bool:
    return capacity_row_exists and roster_row_count > 0


def classify_combined_status(
    resource_status: str,
    economic_status: str,
) -> str:
    if economic_status == PRICE_NOT_DEFINED:
        return COMBINED_PRICE_UNDEFINED
    if resource_status == NOT_CALCULATED or resource_status == CAPACITY_DATA_MISSING:
        if economic_status == ECONOMIC_DEFICIT:
            return COMBINED_ECONOMIC_RISK
        return COMBINED_NOT_CALCULATED

    resource_ok = resource_status == RESOURCE_READY
    resource_partial = resource_status == PARTIALLY_FEASIBLE
    economic_ok = economic_status == ECONOMIC_OK

    if resource_ok and economic_ok:
        return COMBINED_READY
    if (resource_partial or resource_status == RESOURCE_DEFICIT) and economic_ok:
        return COMBINED_RESOURCE_RISK
    if resource_ok and not economic_ok:
        return COMBINED_ECONOMIC_RISK
    if not resource_ok and not economic_ok:
        return COMBINED_BOTH_RISK
    if resource_partial and not economic_ok:
        return COMBINED_BOTH_RISK
    return COMBINED_NOT_CALCULATED


def _capacity_lookup(
    capacity_df: pd.DataFrame,
) -> dict[tuple[str, str, str], pd.Series]:
    lookup: dict[tuple[str, str, str], pd.Series] = {}
    if capacity_df.empty:
        return lookup
    for _, row in capacity_df.iterrows():
        key = _crew_key(row.get("project_code"), row.get("month_key"), row.get("crew_code"))
        if key[2]:
            lookup[key] = row
    return lookup


def _compute_crew_coverage(
    required_hours: float,
    available_hours: float,
    capacity_row_exists: bool,
) -> Optional[float]:
    if not capacity_row_exists:
        return None
    if required_hours <= 0:
        return None
    if available_hours <= 0:
        return 0.0
    return min(available_hours / required_hours, 1.0)


def build_resource_economic_crew_model(
    lines_df: pd.DataFrame,
    capacity_df: pd.DataFrame,
) -> pd.DataFrame:
    """One row per project + month + crew from analyzed plan lines."""
    lines = normalize_labor_lines_df(lines_df)
    if lines.empty:
        return _empty_crew_model()

    capacity = normalize_capacity_df(capacity_df)
    cap_lookup = _capacity_lookup(capacity)

    rows: list[dict[str, Any]] = []
    group_cols = ["project_code", "month_key", "crew_code"]
    for (project_code, month_key, crew_code), group in lines.groupby(group_cols, dropna=False):
        crew_code_str = _safe_str(crew_code)
        if not crew_code_str:
            continue

        required_sum = 0.0
        hours_ok = True
        plan_value_total = 0.0
        labor_cost_total = 0.0

        for _, line in group.iterrows():
            hrs, calculated = resolve_required_hours(line)
            if not calculated:
                hours_ok = False
            required_sum += hrs
            plan_value_total += to_num(line.get("plan_value"))
            labor_cost_total += to_num(line.get("labor_cost"))

        cap_key = _crew_key(project_code, month_key, crew_code_str)
        cap_row = cap_lookup.get(cap_key)
        capacity_row_exists = cap_row is not None
        available_hours = to_num(cap_row.get("available_labor_hours")) if capacity_row_exists else 0.0
        fte_required = required_sum / 176.0 if required_sum > 0 else 0.0
        available_fte = to_num(cap_row.get("available_fte")) if capacity_row_exists else 0.0
        fte_gap = to_num(cap_row.get("fte_gap")) if capacity_row_exists else 0.0
        roster_row_count = int(to_num(cap_row.get("roster_row_count"))) if capacity_row_exists else 0
        confirmed_roster = _has_confirmed_roster(capacity_row_exists, roster_row_count)

        coverage = _compute_crew_coverage(required_sum, available_hours, capacity_row_exists)
        resource_status = classify_resource_status_from_coverage(
            hours_calculated=hours_ok and required_sum > 0,
            crew_code=crew_code_str,
            capacity_row_exists=capacity_row_exists,
            roster_row_count=roster_row_count,
            available_hours=available_hours,
            required_hours=required_sum,
            coverage=coverage,
        )
        economic_status = classify_economic_status(plan_value_total, labor_cost_total)
        combined_status = classify_combined_status(resource_status, economic_status)

        presentation_coverage = coverage if confirmed_roster else None
        presentation_available = available_hours if confirmed_roster else None

        rows.append(
            {
                "project_code": _safe_str(project_code),
                "month_key": _safe_str(month_key),
                "crew_code": crew_code_str,
                "boq_count": int(len(group)),
                "crew_required_hours": required_sum,
                "crew_available_hours": presentation_available,
                "hours_gap": (available_hours - required_sum) if confirmed_roster else None,
                "coverage": presentation_coverage,
                "coverage_pct": (presentation_coverage * 100.0)
                if presentation_coverage is not None
                else None,
                "fte_required": fte_required,
                "available_fte": available_fte if confirmed_roster else None,
                "fte_gap": fte_gap if confirmed_roster else None,
                "roster_row_count": roster_row_count,
                "plan_value_total": plan_value_total,
                "labor_cost_total": labor_cost_total,
                "economic_gap": plan_value_total - labor_cost_total,
                "resource_status": resource_status,
                "economic_status": economic_status,
                "combined_status": combined_status,
                "capacity_row_exists": capacity_row_exists,
            }
        )

    if not rows:
        return _empty_crew_model()

    out = pd.DataFrame(rows)
    return out[CREW_MODEL_COLUMNS]


def build_resource_economic_line_model(
    lines_df: pd.DataFrame,
    crew_model: pd.DataFrame,
) -> pd.DataFrame:
    """One row per plan_line_id with proportional feasible quantity."""
    lines = normalize_labor_lines_df(lines_df)
    if lines.empty:
        return _empty_line_model()

    crew_lookup: dict[tuple[str, str, str], pd.Series] = {}
    if not crew_model.empty:
        for _, crow in crew_model.iterrows():
            key = _crew_key(crow.get("project_code"), crow.get("month_key"), crow.get("crew_code"))
            crew_lookup[key] = crow

    rows: list[dict[str, Any]] = []
    for _, line in lines.iterrows():
        plan_line_id = _safe_str(line.get("plan_line_id"))
        project_code = _safe_str(line.get("project_code"))
        month_key = _safe_str(line.get("month_key"))
        crew_code = _safe_str(line.get("crew_code"))

        requested_qty = to_num(line.get("planned_qty"))
        required_hours, hours_calculated = resolve_required_hours(line)
        plan_value = to_num(line.get("plan_value"))
        labor_cost = to_num(line.get("labor_cost"))
        unit_price = to_num(line.get("unit_price"))
        norm = to_num(line.get("norm_hours_per_unit_effective"), default=-1.0)
        if norm < 0:
            norm = None

        crew_key = _crew_key(project_code, month_key, crew_code)
        crew_row = crew_lookup.get(crew_key)

        crew_required_total = to_num(crew_row.get("crew_required_hours")) if crew_row is not None else 0.0
        crew_available = None
        coverage = None
        resource_status = NOT_CALCULATED
        theoretical_feasible_qty = None

        if not hours_calculated:
            resource_status = NOT_CALCULATED
        elif not crew_code:
            resource_status = NOT_CALCULATED
        elif crew_row is None:
            resource_status = CAPACITY_DATA_MISSING
        else:
            resource_status = _safe_str(crew_row.get("resource_status")) or NOT_CALCULATED
            crew_available = crew_row.get("crew_available_hours")
            coverage = crew_row.get("coverage")

            if resource_status == RESOURCE_DEFICIT and requested_qty > 0:
                theoretical_feasible_qty = 0.0
            elif resource_status in (RESOURCE_READY, PARTIALLY_FEASIBLE):
                if coverage is not None and requested_qty > 0:
                    theoretical_feasible_qty = min(requested_qty, requested_qty * float(coverage))
            # CAPACITY_DATA_MISSING / NOT_CALCULATED → feasible qty stays None

        volume_deficit = None
        if theoretical_feasible_qty is not None and requested_qty > 0:
            volume_deficit = max(requested_qty - theoretical_feasible_qty, 0.0)

        economic_status = classify_economic_status(plan_value, labor_cost)
        combined_status = classify_combined_status(resource_status, economic_status)

        feasible_ratio = None
        feasible_work_value = None
        feasible_labor_cost = None
        feasible_economic_gap = None
        if theoretical_feasible_qty is not None and requested_qty > 0:
            feasible_ratio = theoretical_feasible_qty / requested_qty
            feasible_work_value = plan_value * feasible_ratio
            feasible_labor_cost = labor_cost * feasible_ratio
            feasible_economic_gap = feasible_work_value - feasible_labor_cost

        coverage_pct = (float(coverage) * 100.0) if coverage is not None else None

        rows.append(
            {
                "plan_line_id": plan_line_id,
                "project_code": project_code,
                "month_key": month_key,
                "boq_code": _safe_str(line.get("boq_code")),
                "boq_name": _safe_str(line.get("boq_name")),
                "facility": _safe_str(line.get("facility")),
                "discipline": _safe_str(line.get("discipline")),
                "crew_code": crew_code,
                "crew_size": to_num(line.get("crew_size"), default=-1.0),
                "requested_qty": requested_qty,
                "unit": _safe_str(line.get("unit")),
                "required_hours": required_hours if hours_calculated else None,
                "norm_hours_per_unit": norm,
                "crew_required_hours_total": crew_required_total if crew_row is not None else None,
                "crew_available_hours": crew_available,
                "coverage": coverage,
                "coverage_pct": coverage_pct,
                "theoretical_feasible_qty": theoretical_feasible_qty,
                "volume_deficit_qty": volume_deficit,
                "unit_price": unit_price if unit_price > 0 else None,
                "requested_work_value": plan_value if plan_value > 0 else None,
                "feasible_work_value": feasible_work_value,
                "requested_labor_cost": labor_cost if labor_cost > 0 else None,
                "feasible_labor_cost": feasible_labor_cost,
                "economic_gap": plan_value - labor_cost if plan_value > 0 else None,
                "feasible_economic_gap": feasible_economic_gap,
                "resource_status": resource_status,
                "economic_status": economic_status,
                "combined_status": combined_status,
            }
        )

    if not rows:
        return _empty_line_model()

    return pd.DataFrame(rows)[LINE_MODEL_COLUMNS]


def build_resource_economic_summary(
    crew_model: pd.DataFrame,
    line_model: pd.DataFrame,
) -> dict[str, Any]:
    """Top KPI block; available hours counted once per unique crew."""
    if line_model.empty:
        return {
            "line_count": 0,
            "crew_count": 0,
            "requested_work_value": 0.0,
            "required_labor_hours": 0.0,
            "available_labor_hours": 0.0,
            "resource_coverage_pct": None,
            "feasible_work_value": 0.0,
            "labor_cost_total": 0.0,
            "economic_result": 0.0,
            "feasible_economic_result": 0.0,
            "crews_missing_capacity_count": 0,
            "has_capacity_data_quality_issue": False,
        }

    required_labor_hours = float(
        pd.to_numeric(line_model["required_hours"], errors="coerce").fillna(0).sum()
    )
    requested_work_value = float(
        pd.to_numeric(line_model["requested_work_value"], errors="coerce").fillna(0).sum()
    )
    labor_cost_total = float(
        pd.to_numeric(line_model["requested_labor_cost"], errors="coerce").fillna(0).sum()
    )
    feasible_work_value = float(
        pd.to_numeric(line_model["feasible_work_value"], errors="coerce").sum(skipna=True)
    )
    feasible_economic_result = float(
        pd.to_numeric(line_model["feasible_economic_gap"], errors="coerce").sum(skipna=True)
    )

    available_labor_hours = 0.0
    if not crew_model.empty and "crew_available_hours" in crew_model.columns:
        avail = crew_model.drop_duplicates(subset=["project_code", "month_key", "crew_code"])
        confirmed = avail[pd.to_numeric(avail["roster_row_count"], errors="coerce").fillna(0) > 0]
        available_labor_hours = float(
            pd.to_numeric(confirmed["crew_available_hours"], errors="coerce").fillna(0).sum()
        )

    crews_missing_capacity_count = count_crews_missing_capacity(crew_model)

    resource_coverage_pct = None
    if required_labor_hours > 0 and available_labor_hours >= 0:
        resource_coverage_pct = min(available_labor_hours / required_labor_hours, 1.0) * 100.0
        if available_labor_hours > required_labor_hours:
            resource_coverage_pct = (available_labor_hours / required_labor_hours) * 100.0

    return {
        "line_count": len(line_model),
        "crew_count": len(crew_model),
        "requested_work_value": requested_work_value,
        "required_labor_hours": required_labor_hours,
        "available_labor_hours": available_labor_hours,
        "resource_coverage_pct": resource_coverage_pct,
        "feasible_work_value": feasible_work_value,
        "labor_cost_total": labor_cost_total,
        "economic_result": requested_work_value - labor_cost_total,
        "feasible_economic_result": feasible_economic_result,
        "crews_missing_capacity_count": crews_missing_capacity_count,
        "has_capacity_data_quality_issue": crews_missing_capacity_count > 0,
    }


def build_resource_economic_models(
    lines_df: pd.DataFrame,
    capacity_df: pd.DataFrame,
) -> dict[str, Any]:
    """Convenience wrapper: crew + line + summary."""
    crew_model = build_resource_economic_crew_model(lines_df, capacity_df)
    line_model = build_resource_economic_line_model(lines_df, crew_model)
    summary = build_resource_economic_summary(crew_model, line_model)
    return {
        "crew_model": crew_model,
        "line_model": line_model,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# R1.5B — Decision Economics read-model (no writes; not accounting P&L)
# ---------------------------------------------------------------------------

ITR_POOL_STATUS_PROPOSED = "proposed"
ITR_POOL_STATUS_RU = {
    ITR_POOL_STATUS_PROPOSED: "Предварительный",
}
ITR_DRIVER_REQUIRED_HOURS = "required_direct_hours"
ITR_DRIVER_LABEL_RU = "Требуемые трудозатраты звена / требуемые трудозатраты проекта"

RATE_COMPOSITION_WARNING_RU = (
    "Состав ставки прямого труда 3 000 ₽/ч не верифицирован. "
    "Расчёт является управленческим предварительным и может содержать "
    "риск пересечения с overhead/ИТР."
)

ITR_QUALITY_WARNING_RU = (
    "ITR pool сформирован из monthly_labor_summary и пока не имеет "
    "подтверждённого budget approval status."
)

MGMT_MSG_PRODUCTIVE_BUT_ADMIN_OVERHEAD = (
    "Звено производительно, но проект съедается чрезмерным административным контуром."
)
MGMT_MSG_PRODUCTIVE_BUT_ADMIN_OVERHEAD_DETAIL = (
    "Выполнимый производственный объём имеет положительный результат после "
    "пропорционального поглощения ИТР, однако текущий throughput недостаточен "
    "для покрытия полной распределённой месячной доли административного контура."
)


def effective_feasible_coverage(coverage: float | None) -> float:
    """
    Same bound as feasible qty logic: production share cannot exceed 100% of request.
    Missing / non-positive coverage → 0 absorption base.
    """
    if coverage is None:
        return 0.0
    try:
        value = float(coverage)
    except (TypeError, ValueError):
        return 0.0
    if value <= 0:
        return 0.0
    return min(value, 1.0)


def summarize_proposed_itr_pool(
    labor_summary_df: pd.DataFrame,
    *,
    project_code: str,
    month_key: str,
) -> dict[str, Any]:
    """
    Project+month ITR pool from monthly_labor_summary.indirect_cost_rub_month.
    Always labelled proposed in R1.5B (budget_status quality unknown).
    Read-only; no writes.
    """
    empty = {
        "project_code": _safe_str(project_code),
        "month_key": normalize_month_key(month_key) or _safe_str(month_key),
        "itr_pool": 0.0,
        "itr_people_count": 0,
        "itr_hours": 0.0,
        "pool_status": ITR_POOL_STATUS_PROPOSED,
        "pool_status_ru": ITR_POOL_STATUS_RU[ITR_POOL_STATUS_PROPOSED],
        "matched": False,
        "writes": False,
    }
    project = _safe_str(project_code)
    month = normalize_month_key(month_key)
    if not project or not month or labor_summary_df is None or labor_summary_df.empty:
        return empty

    df = labor_summary_df.copy()
    df["_project"] = df.get("project_code", pd.Series(dtype=str)).map(_safe_str)
    df["_month"] = df.get("month_key", pd.Series(dtype=str)).map(normalize_month_key)
    scoped = df[(df["_project"] == project) & (df["_month"] == month)]
    if scoped.empty:
        return empty

    indirect_cost = pd.to_numeric(
        scoped.get("indirect_cost_rub_month"), errors="coerce"
    ).fillna(0.0)
    indirect_hours = pd.to_numeric(
        scoped.get("indirect_hours_month"), errors="coerce"
    ).fillna(0.0)
    itr_mask = (indirect_cost > 0) | (indirect_hours > 0)
    itr_rows = scoped[itr_mask]
    return {
        "project_code": project,
        "month_key": month,
        "itr_pool": float(indirect_cost.sum()),
        "itr_people_count": int(len(itr_rows)),
        "itr_hours": float(indirect_hours.sum()),
        "pool_status": ITR_POOL_STATUS_PROPOSED,
        "pool_status_ru": ITR_POOL_STATUS_RU[ITR_POOL_STATUS_PROPOSED],
        "matched": True,
        "writes": False,
    }


def project_required_direct_hours(
    lines_df: pd.DataFrame,
    *,
    project_code: str,
    month_key: str,
) -> float:
    """Sum labor_hours for one project+month (all crews) — ITR denominator."""
    project = _safe_str(project_code)
    month = normalize_month_key(month_key)
    if not project or not month or lines_df is None or lines_df.empty:
        return 0.0
    df = normalize_labor_lines_df(lines_df)
    if df.empty:
        return 0.0
    df = df.copy()
    df["_project"] = df["project_code"].map(_safe_str)
    df["_month"] = df["month_key"].map(normalize_month_key)
    scoped = df[(df["_project"] == project) & (df["_month"] == month)]
    if scoped.empty:
        return 0.0
    return float(pd.to_numeric(scoped["labor_hours"], errors="coerce").fillna(0).sum())


def classify_itr_absorption_management_message(
    *,
    feasible_direct_result: float,
    normalized_result: float,
    full_month_operating_result: float,
) -> dict[str, Any]:
    """Deterministic R1.5B rule — no LLM, no extra thresholds."""
    trigger = (
        float(feasible_direct_result) > 0
        and float(normalized_result) > 0
        and float(full_month_operating_result) <= 0
    )
    return {
        "triggered": trigger,
        "message": MGMT_MSG_PRODUCTIVE_BUT_ADMIN_OVERHEAD if trigger else None,
        "detail": MGMT_MSG_PRODUCTIVE_BUT_ADMIN_OVERHEAD_DETAIL if trigger else None,
    }


def build_crew_decision_economics(
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
    crew_required_hours: float,
    project_required_hours: float,
    approved_hours: float | None,
    coverage: float | None,
    requested_work_value: float,
    requested_direct_labor: float,
    feasible_work_value: float | None,
    feasible_direct_labor: float | None,
    project_itr_pool: float,
    itr_pool_status: str = ITR_POOL_STATUS_PROPOSED,
) -> dict[str, Any]:
    """
    Layered decision economics for one crew scope.
    Driver v1: required hours share. Absorbed ITR uses effective feasible coverage.
    Not accounting P&L. writes=False always.
    """
    req = max(float(crew_required_hours or 0.0), 0.0)
    proj_req = max(float(project_required_hours or 0.0), 0.0)
    pool = max(float(project_itr_pool or 0.0), 0.0)
    req_value = float(requested_work_value or 0.0)
    req_labor = float(requested_direct_labor or 0.0)
    feas_value = float(feasible_work_value or 0.0) if feasible_work_value is not None else 0.0
    feas_labor = (
        float(feasible_direct_labor or 0.0) if feasible_direct_labor is not None else 0.0
    )
    approved = max(float(approved_hours or 0.0), 0.0)
    eff_cov = effective_feasible_coverage(coverage)

    itr_share = (req / proj_req) if proj_req > 0 else None
    full_allocated = (pool * itr_share) if itr_share is not None else 0.0
    absorbed = full_allocated * eff_cov
    unabsorbed = max(full_allocated - absorbed, 0.0)

    requested_margin = req_value - req_labor
    feasible_margin = feas_value - feas_labor
    normalized = feas_value - feas_labor - absorbed
    full_month = feas_value - feas_labor - full_allocated

    mgmt = classify_itr_absorption_management_message(
        feasible_direct_result=feasible_margin,
        normalized_result=normalized,
        full_month_operating_result=full_month,
    )

    return {
        "project_code": _safe_str(project_code),
        "month_key": normalize_month_key(month_key) or _safe_str(month_key),
        "crew_code": _safe_str(crew_code),
        "requested_work_value": req_value,
        "requested_direct_hours": req,
        "requested_direct_labor": req_labor,
        "requested_margin_before_itr": requested_margin,
        "approved_hours": approved,
        "coverage": float(coverage) if coverage is not None else None,
        "effective_coverage": eff_cov,
        "feasible_work_value": feas_value,
        "feasible_direct_labor": feas_labor,
        "feasible_margin_before_itr": feasible_margin,
        "project_required_hours": proj_req,
        "project_itr_pool": pool,
        "itr_pool_status": itr_pool_status,
        "itr_pool_status_ru": ITR_POOL_STATUS_RU.get(
            itr_pool_status, ITR_POOL_STATUS_RU[ITR_POOL_STATUS_PROPOSED]
        ),
        "itr_driver": ITR_DRIVER_REQUIRED_HOURS,
        "itr_driver_label_ru": ITR_DRIVER_LABEL_RU,
        "itr_share": itr_share,
        "itr_share_pct": (itr_share * 100.0) if itr_share is not None else None,
        "full_allocated_itr": full_allocated,
        "absorbed_itr": absorbed,
        "unabsorbed_itr": unabsorbed,
        "normalized_result_after_absorbed_itr": normalized,
        "full_month_operating_result": full_month,
        "management_message_triggered": mgmt["triggered"],
        "management_message": mgmt["message"],
        "management_message_detail": mgmt["detail"],
        "rate_warning_ru": RATE_COMPOSITION_WARNING_RU,
        "itr_quality_warning_ru": ITR_QUALITY_WARNING_RU,
        "writes": False,
    }


def build_decision_economics_from_models(
    *,
    crew_row: pd.Series | dict[str, Any],
    line_model: pd.DataFrame,
    project_required_hours: float,
    project_itr_pool: float,
    itr_pool_status: str = ITR_POOL_STATUS_PROPOSED,
) -> dict[str, Any]:
    """Compose crew decision economics from existing Page22 models + ITR pool."""
    if isinstance(crew_row, pd.Series):
        crew_row = crew_row.to_dict()

    project = _safe_str(crew_row.get("project_code"))
    month = normalize_month_key(crew_row.get("month_key")) or _safe_str(crew_row.get("month_key"))
    crew = _safe_str(crew_row.get("crew_code"))

    scoped_lines = line_model
    if line_model is not None and not line_model.empty:
        scoped_lines = line_model[
            (line_model["project_code"].map(_safe_str) == project)
            & (line_model["month_key"].map(lambda v: normalize_month_key(v) or _safe_str(v)) == month)
            & (line_model["crew_code"].map(_safe_str) == crew)
        ]

    feasible_value = None
    feasible_labor = None
    if scoped_lines is not None and not scoped_lines.empty:
        feasible_value = float(
            pd.to_numeric(scoped_lines["feasible_work_value"], errors="coerce").sum(skipna=True)
        )
        feasible_labor = float(
            pd.to_numeric(scoped_lines["feasible_labor_cost"], errors="coerce").sum(skipna=True)
        )

    coverage = crew_row.get("coverage")
    if coverage is not None:
        try:
            coverage = float(coverage)
        except (TypeError, ValueError):
            coverage = None

    approved = crew_row.get("crew_available_hours")
    if str(crew_row.get("resource_status")) == CAPACITY_DATA_MISSING:
        approved = 0.0
        coverage = None
        feasible_value = 0.0
        feasible_labor = 0.0

    return build_crew_decision_economics(
        project_code=project,
        month_key=month,
        crew_code=crew,
        crew_required_hours=to_num(crew_row.get("crew_required_hours")),
        project_required_hours=project_required_hours,
        approved_hours=to_num(approved) if approved is not None else 0.0,
        coverage=coverage,
        requested_work_value=to_num(crew_row.get("plan_value_total")),
        requested_direct_labor=to_num(crew_row.get("labor_cost_total")),
        feasible_work_value=feasible_value,
        feasible_direct_labor=feasible_labor,
        project_itr_pool=project_itr_pool,
        itr_pool_status=itr_pool_status,
    )
