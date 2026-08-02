"""
Read-only crew breakdown for BOQ execution history (page 21 block C).

Grain (same as boq_execution_history_v1, without changing that view):
  project_code + boq + facility_building + construction_discipline

Source: public.daily_progress_active only.
"""

from __future__ import annotations

from typing import Any

from services.supabase_client import supabase

TABLE_DAILY_PROGRESS_ACTIVE = "daily_progress_active"

DP_SELECT_COLUMNS = (
    "project_code,"
    "boq,"
    "facility_building,"
    "construction_discipline,"
    "crew_id,"
    "work_date,"
    "shift_type,"
    "quantity_today,"
    "direct_work_hours,"
    "ac_day_value,"
    "direct_rate_rub_per_hour,"
    "is_deleted"
)


def _norm_key(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _norm_upper(value: Any) -> str:
    return _norm_key(value).upper()


def _safe_num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _row_labor_cost(row: dict[str, Any]) -> float:
    ac = _safe_num(row.get("ac_day_value"))
    if ac > 0:
        return ac
    hours = _safe_num(row.get("direct_work_hours"))
    rate = _safe_num(row.get("direct_rate_rub_per_hour"))
    if hours > 0 and rate > 0:
        return hours * rate
    return 0.0


def _shift_key(row: dict[str, Any], crew_id: str) -> str | None:
    work_date = row.get("work_date")
    if work_date is None or str(work_date).strip() == "":
        return None
    date_text = str(work_date).strip()
    shift = _norm_key(row.get("shift_type"))
    crew = _norm_key(crew_id)
    if shift and crew:
        return f"{date_text}|{shift}|{crew}"
    if shift:
        return f"{date_text}|{shift}"
    return date_text


def _grain_matches(
    row: dict[str, Any],
    *,
    project: str,
    boq: str,
    facility: str,
    discipline: str,
) -> bool:
    if _norm_upper(row.get("project_code")) != _norm_upper(project):
        return False
    if _norm_upper(row.get("boq")) != _norm_upper(boq):
        return False
    row_facility = _norm_upper(row.get("facility_building"))
    row_discipline = _norm_upper(row.get("construction_discipline"))
    want_facility = _norm_upper(facility)
    want_discipline = _norm_upper(discipline)
    if want_facility:
        if row_facility != want_facility:
            return False
    else:
        if row_facility:
            return False
    if want_discipline:
        if row_discipline != want_discipline:
            return False
    else:
        if row_discipline:
            return False
    if bool(row.get("is_deleted")):
        return False
    return True


def get_boq_execution_crew_breakdown(
    project_code: Any,
    boq_code: Any,
    facility_building: Any,
    construction_discipline: Any,
) -> dict[str, Any]:
    """
    Aggregate daily_progress_active by crew_id for one admission grain.

    Returns:
        {
            "found": bool,
            "rows": list[dict],
            "totals": {...},
            "error": str | None,
        }
    """
    empty_totals = {
        "shift_count": 0,
        "actual_qty": 0.0,
        "direct_work_hours": 0.0,
        "labor_cost": 0.0,
        "crew_count": 0,
    }
    project = _norm_key(project_code)
    boq = _norm_key(boq_code)
    facility = _norm_key(facility_building)
    discipline = _norm_key(construction_discipline)

    if not project or not boq:
        return {
            "found": False,
            "rows": [],
            "totals": empty_totals,
            "error": "Недостаточно ключевых данных: project_code / boq_code.",
        }

    try:
        # Broad fetch by project+boq; facility/discipline matched after trim
        # (DP often stores trailing spaces that break PostgREST .eq).
        response = (
            supabase.table(TABLE_DAILY_PROGRESS_ACTIVE)
            .select(DP_SELECT_COLUMNS)
            .eq("project_code", project)
            .eq("boq", boq)
            .limit(10000)
            .execute()
        )
        raw_rows = list(response.data or [])
    except Exception as exc:  # noqa: BLE001
        return {
            "found": False,
            "rows": [],
            "totals": empty_totals,
            "error": f"Ошибка чтения {TABLE_DAILY_PROGRESS_ACTIVE}: {exc}",
        }

    matched = [
        row
        for row in raw_rows
        if _grain_matches(
            row,
            project=project,
            boq=boq,
            facility=facility,
            discipline=discipline,
        )
    ]
    if not matched:
        return {"found": False, "rows": [], "totals": empty_totals, "error": None}

    by_crew: dict[str, dict[str, Any]] = {}
    for row in matched:
        crew_raw = _norm_key(row.get("crew_id"))
        crew_id = crew_raw if crew_raw else "—"
        bucket = by_crew.get(crew_id)
        if bucket is None:
            bucket = {
                "crew_id": crew_id,
                "shift_keys": set(),
                "actual_qty": 0.0,
                "direct_work_hours": 0.0,
                "labor_cost": 0.0,
                "fact_row_count": 0,
            }
            by_crew[crew_id] = bucket
        shift_key = _shift_key(row, crew_id if crew_raw else "")
        if shift_key:
            bucket["shift_keys"].add(shift_key)
        bucket["actual_qty"] += _safe_num(row.get("quantity_today"))
        bucket["direct_work_hours"] += _safe_num(row.get("direct_work_hours"))
        bucket["labor_cost"] += _row_labor_cost(row)
        bucket["fact_row_count"] += 1

    rows: list[dict[str, Any]] = []
    for crew_id in sorted(by_crew.keys(), key=lambda c: (c == "—", c)):
        bucket = by_crew[crew_id]
        rows.append(
            {
                "crew_id": crew_id,
                "shift_count": len(bucket["shift_keys"]),
                "actual_qty": float(bucket["actual_qty"]),
                "direct_work_hours": float(bucket["direct_work_hours"]),
                "labor_cost": float(bucket["labor_cost"]),
                "fact_row_count": int(bucket["fact_row_count"]),
            }
        )

    totals = {
        "shift_count": int(sum(r["shift_count"] for r in rows)),
        "actual_qty": float(sum(r["actual_qty"] for r in rows)),
        "direct_work_hours": float(sum(r["direct_work_hours"] for r in rows)),
        "labor_cost": float(sum(r["labor_cost"] for r in rows)),
        "crew_count": int(
            sum(1 for r in rows if r["crew_id"] and r["crew_id"] != "—")
        ),
    }
    return {"found": True, "rows": rows, "totals": totals, "error": None}
