"""
Read-only service for Monthly Planning Labor Engine (Phase 1).

Source: Supabase views from sql/monthly_plan_labor_engine_v1.sql
SoT planned hours: monthly_plan_lines_v2.labor_hours (via views)

No writes. No UI. No business-logic recompute.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from services.supabase_client import supabase

VIEW_LABOR_LINES = "monthly_plan_labor_lines_v1"
VIEW_LABOR_SUMMARY = "monthly_plan_labor_summary_v1"
VIEW_LABOR_ADMISSION = "monthly_plan_labor_admission_v1"
VIEW_LABOR_ADMISSION_SUMMARY = "monthly_plan_labor_admission_summary_v1"
VIEW_CAPACITY = "monthly_plan_capacity_v1"
VIEW_PASSPORT_RESOURCE = "monthly_plan_passport_resource_v1"

DEFAULT_PAGE_SIZE = 1000
DEFAULT_LIMIT = 10000

_last_load_error: Optional[str] = None


def get_last_load_error() -> Optional[str]:
    """Last Supabase read error message, if any (None on success)."""
    return _last_load_error


def empty_dataframe(columns: Optional[list[str]] = None) -> pd.DataFrame:
    """Safe empty DataFrame fallback for failed or empty loads."""
    if columns:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame()


def to_num(value: Any, default: float = 0.0) -> float:
    """Coerce Supabase / pandas values to float."""
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_hours(value: Any) -> str:
    """Human-readable labor hours: «1 234,5 чел-ч»."""
    hours = to_num(value, default=-1.0)
    if hours < 0:
        return "—"
    if hours == 0:
        return "0 чел-ч"
    text = f"{hours:,.1f}".replace(",", " ")
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text} чел-ч"


def format_money(value: Any) -> str:
    """Human-readable RUB: «2 304 000,00 ₽»."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "0,00 ₽"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "0,00 ₽"
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    whole, frac = f"{amount:.2f}".split(".")
    whole_fmt = f"{int(whole):,}".replace(",", " ")
    return f"{sign}{whole_fmt},{frac} ₽"


def format_fte(value: Any, *, decimals: int = 1) -> str:
    """Human-readable FTE: «12,7 чел»."""
    fte = to_num(value, default=-1.0)
    if fte < 0:
        return "—"
    if fte == 0:
        return "0 чел"
    formatted = f"{fte:,.{decimals}f}".replace(",", " ")
    if decimals > 0:
        formatted = formatted.replace(".", ",")
    return f"{formatted} чел"


def _set_load_error(message: Optional[str]) -> None:
    global _last_load_error
    _last_load_error = message


def _apply_filters(
    query: Any,
    *,
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
    passport_id: Optional[str] = None,
) -> Any:
    if project_code:
        query = query.eq("project_code", str(project_code).strip())
    if month_key:
        query = query.eq("month_key", str(month_key).strip())
    if passport_id:
        query = query.eq("passport_id", str(passport_id).strip())
    return query


def _safe_load_view(
    view_name: str,
    *,
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
    passport_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> pd.DataFrame:
    """
    Paginated read from a Supabase view with optional equality filters.
    Returns empty DataFrame on error (see get_last_load_error()).
    """
    _set_load_error(None)
    try:
        rows: list[dict[str, Any]] = []
        offset = 0
        page_size = min(DEFAULT_PAGE_SIZE, max(limit, 1))

        while len(rows) < limit:
            chunk_end = min(offset + page_size - 1, limit - 1)
            if chunk_end < offset:
                break

            query = supabase.table(view_name).select("*")
            query = _apply_filters(
                query,
                project_code=project_code,
                month_key=month_key,
                passport_id=passport_id,
            )
            response = query.range(offset, chunk_end).execute()
            batch = response.data or []
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < (chunk_end - offset + 1):
                break
            offset += page_size

        return pd.DataFrame(rows)
    except Exception as exc:  # noqa: BLE001
        _set_load_error(f"{view_name}: {exc}")
        return empty_dataframe()


def load_labor_lines(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> pd.DataFrame:
    """Plan line labor read-model (grain: plan_line_id)."""
    return _safe_load_view(
        VIEW_LABOR_LINES,
        project_code=project_code,
        month_key=month_key,
    )


def load_labor_summary(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> pd.DataFrame:
    """Monthly plan labor rollup (grain: project_code + month_key)."""
    return _safe_load_view(
        VIEW_LABOR_SUMMARY,
        project_code=project_code,
        month_key=month_key,
    )


def load_labor_admission(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> pd.DataFrame:
    """Admission-scope plan lines with labor status (SENT_TO_ADMISSION)."""
    return _safe_load_view(
        VIEW_LABOR_ADMISSION,
        project_code=project_code,
        month_key=month_key,
    )


def load_labor_admission_summary(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> pd.DataFrame:
    """Admission labor KPI rollup (launch_hours = READY + WARNING)."""
    return _safe_load_view(
        VIEW_LABOR_ADMISSION_SUMMARY,
        project_code=project_code,
        month_key=month_key,
    )


def load_capacity(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> pd.DataFrame:
    """Plan demand vs roster capacity (grain: project + month + crew)."""
    return _safe_load_view(
        VIEW_CAPACITY,
        project_code=project_code,
        month_key=month_key,
    )


def load_passport_resource(
    passport_id: Optional[str] = None,
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> pd.DataFrame:
    """Frozen passport resource commitment (grain: passport_id)."""
    return _safe_load_view(
        VIEW_PASSPORT_RESOURCE,
        passport_id=passport_id,
        project_code=project_code,
        month_key=month_key,
    )
