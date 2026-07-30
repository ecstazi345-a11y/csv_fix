"""
Read-only loader for public.boq_execution_history_v1.

One row per admission grain:
  project_code + boq_code + facility_building + construction_discipline

No writes. No UI. No business-logic recompute beyond duplicate/empty checks.
"""

from __future__ import annotations

from typing import Any

from services.supabase_client import supabase

VIEW_BOQ_EXECUTION_HISTORY = "boq_execution_history_v1"

HISTORY_SELECT_COLUMNS = (
    "project_code,"
    "boq_code,"
    "facility_building,"
    "construction_discipline,"
    "has_master,"
    "has_history,"
    "project_qty_full,"
    "actual_qty,"
    "execution_percent,"
    "actual_qty_exceeds_full_qty,"
    "direct_work_hours,"
    "labor_cost_actual,"
    "labor_cost_source,"
    "labor_cost_complete,"
    "boq_total_value,"
    "boq_value_source,"
    "current_balance,"
    "labor_budget_used_percent,"
    "labor_consumption_index,"
    "shift_count,"
    "crew_count,"
    "crew_list,"
    "uom_check_status,"
    "uom_mismatch,"
    "forecast_allowed,"
    "forecast_labor_cost,"
    "forecast_result,"
    "data_status,"
    "min_work_date,"
    "max_work_date,"
    "fact_row_count,"
    "master_row_count"
)


def _norm_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def get_boq_execution_history(
    project_code: Any,
    boq_code: Any,
    facility_building: Any,
    construction_discipline: Any,
) -> dict[str, Any]:
    """
    Load exactly one history row for the admission grain.

    Returns:
        {"found": bool, "row": dict | None, "error": str | None}
    """
    project = _norm_key(project_code)
    boq = _norm_key(boq_code)
    facility = _norm_key(facility_building)
    discipline = _norm_key(construction_discipline)

    if not project or not boq:
        return {
            "found": False,
            "row": None,
            "error": "Недостаточно ключевых данных: project_code / boq_code.",
        }

    try:
        query = (
            supabase.table(VIEW_BOQ_EXECUTION_HISTORY)
            .select(HISTORY_SELECT_COLUMNS)
            .eq("project_code", project)
            .eq("boq_code", boq)
        )
        # Empty facility/discipline map to SQL NULL display fields — filter only when set.
        if facility:
            query = query.eq("facility_building", facility)
        else:
            query = query.is_("facility_building", "null")
        if discipline:
            query = query.eq("construction_discipline", discipline)
        else:
            query = query.is_("construction_discipline", "null")

        response = query.limit(5).execute()
        rows = list(response.data or [])
    except Exception as exc:  # noqa: BLE001
        return {
            "found": False,
            "row": None,
            "error": f"Ошибка чтения {VIEW_BOQ_EXECUTION_HISTORY}: {exc}",
        }

    if len(rows) == 0:
        return {"found": False, "row": None, "error": None}

    if len(rows) > 1:
        return {
            "found": False,
            "row": None,
            "error": (
                "Duplicate grain detected: "
                f"{project} / {boq} / {facility or '∅'} / {discipline or '∅'} "
                f"(count={len(rows)})."
            ),
        }

    return {"found": True, "row": rows[0], "error": None}
