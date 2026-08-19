"""
MPO-002B — READ-ONLY BOQ reality adapter for Planning Snapshot.

Loads monthly_scope_picker_view, normalizes columns, applies frozen
monthly_planning_boq_service metrics. No Streamlit pages, no writes, no LLM.

Remaining from this adapter is all-time physical remaining BEFORE Constructor
manual not_required adjustments (those live in monthly_scope_manual_adjustments
and are not on the view).
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from services.monthly_planning_boq_service import (
    _v2_apply_boq_availability_metrics,
    filter_invalid_v2_boq_rows,
)

SCOPE_VIEW = "monthly_scope_picker_view"
BARE_PROJECT_LABELS = frozenset({"бхк", "bhk"})


def _empty_meta(**overrides: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source": SCOPE_VIEW,
        "error": None,
        "row_count": 0,
        "excluded_invalid": 0,
        "manual_not_required_adjustments_applied": False,
        "scope_time_basis": "all_time",
        "project_code_filter": None,
        "remaining_semantics": "raw_physical_pre_not_required_adjustments",
    }
    meta.update(overrides)
    return meta


def _safe_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text


def _is_bare_project_label(value: Any) -> bool:
    return _safe_text(value).lower() in BARE_PROJECT_LABELS


def _first_present_column(df: pd.DataFrame, names: tuple[str, ...]) -> Optional[str]:
    for name in names:
        if name in df.columns:
            return name
    return None


def _numeric_series(df: pd.DataFrame, names: tuple[str, ...], default: float = 0.0) -> pd.Series:
    col = _first_present_column(df, names)
    if col is None:
        return pd.Series([default] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _optional_numeric_series(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    col = _first_present_column(df, names)
    if col is None:
        return pd.Series([float("nan")] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _text_series(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    col = _first_present_column(df, names)
    if col is None:
        return pd.Series([""] * len(df), index=df.index, dtype=str)
    return df[col].map(_safe_text)


def normalize_scope_raw_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Map view / alias columns to internal BOQ reality columns. No project remap."""
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    project_raw = _text_series(raw_df, ("project_code",))
    project_code = project_raw.mask(project_raw.map(_is_bare_project_label), "")

    out = pd.DataFrame(
        {
            "project_code": project_code,
            "facility": _text_series(raw_df, ("facility_building", "facility")),
            "discipline": _text_series(raw_df, ("construction_discipline", "discipline")),
            "boq_code": _text_series(raw_df, ("boq_code",)).str.upper(),
            "boq_name": _text_series(raw_df, ("boq_name",)),
            "total_qty": _numeric_series(raw_df, ("total_project_qty", "total_qty")),
            "executed_qty": _numeric_series(
                raw_df, ("executed_qty_all_time", "executed_qty")
            ),
            "unit_price": _numeric_series(raw_df, ("unit_price", "unit_price_num")),
            "total_value": _numeric_series(
                raw_df, ("total_project_value", "total_value", "total_value_num")
            ),
            "remaining_qty": _optional_numeric_series(
                raw_df, ("planning_remaining_qty", "remaining_qty")
            ),
            "manual_executed_before_system": _numeric_series(
                raw_df, ("manual_executed_before_system",)
            ),
            "manual_verified_remaining_qty": _optional_numeric_series(
                raw_df, ("manual_verified_remaining_qty",)
            ),
            "not_required_qty": 0.0,
            "already_planned_qty": 0.0,
        }
    )
    missing_total_value = out["total_value"] <= 0
    out.loc[missing_total_value, "total_value"] = (
        out.loc[missing_total_value, "total_qty"] * out.loc[missing_total_value, "unit_price"]
    )
    return out


def prepare_boq_reality_df(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Normalize → frozen invalid filter → frozen availability metrics."""
    normalized = normalize_scope_raw_df(raw_df)
    if normalized.empty:
        return normalized, _empty_meta()

    kept, excluded = filter_invalid_v2_boq_rows(normalized)
    if kept.empty:
        return kept, _empty_meta(excluded_invalid=excluded, row_count=0)

    metrics = _v2_apply_boq_availability_metrics(kept)
    return metrics, _empty_meta(excluded_invalid=excluded, row_count=len(metrics))


def _fetch_scope_view(
    *,
    project_code: Optional[str] = None,
    limit: int = 10000,
) -> pd.DataFrame:
    from services.supabase_client import supabase

    query = supabase.table(SCOPE_VIEW).select("*").limit(limit)
    code = _safe_text(project_code)
    if code:
        query = query.eq("project_code", code)
    response = query.execute()
    return pd.DataFrame(response.data or [])


def load_monthly_boq_reality(
    project_code: Optional[str] = None,
    *,
    limit: int = 10000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Live READ of monthly_scope_picker_view.

    Does not write. Does not use demo fallback. Does not apply not_required
    adjustments. Empty DataFrame + error meta on failure (never raises).
    """
    filter_code = _safe_text(project_code) or None
    try:
        raw = _fetch_scope_view(project_code=filter_code, limit=limit)
        reality, meta = prepare_boq_reality_df(raw)
        meta["project_code_filter"] = filter_code
        meta["source"] = SCOPE_VIEW
        return reality, meta
    except Exception as exc:  # noqa: BLE001
        return pd.DataFrame(), _empty_meta(
            error=f"{type(exc).__name__}: {exc}",
            project_code_filter=filter_code,
        )
