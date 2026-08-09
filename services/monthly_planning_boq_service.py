"""
Deterministic READ-ONLY BOQ planning core (MPO-001A).

Shared by Page 10B Constructor and future Monthly Planning Orchestrator.
No Streamlit, no session_state, no DB writes.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

V2_SCOPE_STATUS_NOT_REQUIRED = "Остаток не требуется"
V2_SCOPE_STATUS_OVERRUN = "Превышение BOQ"


def _v2_safe_num(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _v2_value_per_unit_series(
    total_qty: pd.Series,
    total_value: pd.Series,
    unit_price: pd.Series,
) -> pd.Series:
    tq = pd.to_numeric(total_qty, errors="coerce").fillna(0.0)
    tv = pd.to_numeric(total_value, errors="coerce").fillna(0.0)
    up = pd.to_numeric(unit_price, errors="coerce").fillna(0.0)
    per_unit = up.astype(float).copy()
    mask = tq > 0
    per_unit.loc[mask] = (tv.loc[mask] / tq.loc[mask]).astype(float)
    return per_unit


def _v2_resolve_available_status(
    remaining_qty: float,
    available_qty: float,
    session_planned_qty: float,
) -> str:
    # remaining<=0 without executed>=total is handled upstream as NOT_REQUIRED /
    # COMPLETED / OVERRUN; here only planning availability for remaining > 0.
    if remaining_qty <= 0:
        return "Нет остатка"
    if available_qty < 0:
        return "Перепланировано"
    if available_qty <= 0 and session_planned_qty > 0:
        return "Запланировано полностью"
    if session_planned_qty > 0:
        return "Частично запланировано"
    return "Доступно"


def _v2_apply_boq_availability_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Физический остаток и доступность к планированию.

    Приоритет:
    1. executed_total_qty = daily_executed_qty + manual_executed_before_system
    2. effective_required_qty = total_qty - not_required_qty
    3. overrun относительно effective_required_qty
    4. manual_verified_remaining_qty — только без overrun
    5. not_required + выполнено >= effective → статус «Остаток не требуется»
    """
    if df.empty:
        return df
    out = df.copy()
    total = pd.to_numeric(out["total_qty"], errors="coerce").fillna(0.0)
    daily_executed = pd.to_numeric(out.get("executed_qty"), errors="coerce").fillna(0.0)
    manual_before = pd.to_numeric(
        out.get("manual_executed_before_system", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0)
    not_required = pd.to_numeric(
        out.get("not_required_qty", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    executed_total = daily_executed + manual_before
    planned = pd.to_numeric(
        out.get("already_planned_qty", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0)
    effective_required = (total - not_required).clip(lower=0.0)

    out["daily_executed_qty"] = daily_executed
    out["executed_total_qty"] = executed_total
    out["executed_qty"] = daily_executed
    out["not_required_qty"] = not_required
    out["effective_required_qty"] = effective_required

    verified = pd.to_numeric(
        out.get("manual_verified_remaining_qty", pd.Series(float("nan"), index=out.index)),
        errors="coerce",
    )
    has_verified = verified.notna()

    per_unit = _v2_value_per_unit_series(
        total,
        out.get("total_value", pd.Series(0.0, index=out.index)),
        out.get("unit_price", pd.Series(0.0, index=out.index)),
    )

    out["overrun_qty"] = (executed_total - effective_required).clip(lower=0.0)
    is_overrun = out["overrun_qty"] > 0
    out["remaining_qty"] = (effective_required - executed_total).clip(lower=0.0)
    out["available_to_add_qty"] = (effective_required - executed_total - planned).clip(lower=0.0)

    out.loc[is_overrun, "remaining_qty"] = 0.0
    out.loc[is_overrun, "available_to_add_qty"] = 0.0

    no_overrun = ~is_overrun
    if has_verified.any():
        verified_remaining = verified.clip(lower=0.0)
        verified_mask = has_verified & no_overrun
        out.loc[verified_mask, "remaining_qty"] = verified_remaining.loc[verified_mask]
        out.loc[verified_mask, "available_to_add_qty"] = (
            verified_remaining.loc[verified_mask] - planned.loc[verified_mask]
        ).clip(lower=0.0)

    out["verified_remaining_ignored"] = has_verified & is_overrun

    out["remaining_value"] = out["remaining_qty"] * per_unit
    out["overrun_value"] = out["overrun_qty"] * per_unit
    out["available_to_add_value"] = out["available_to_add_qty"] * per_unit
    out.loc[is_overrun, "remaining_value"] = 0.0
    out.loc[is_overrun, "available_to_add_value"] = 0.0
    total_value = pd.to_numeric(out.get("total_value", 0), errors="coerce").fillna(0.0)
    out["executed_value"] = (total_value - out["remaining_value"]).clip(lower=0.0)
    return out


def _v2_resolve_scope_status_row(row: pd.Series) -> str:
    not_required = _v2_safe_num(row.get("not_required_qty"))
    effective_required = _v2_safe_num(row.get("effective_required_qty"))
    executed_total = _v2_safe_num(row.get("executed_total_qty"))
    total_qty = _v2_safe_num(row.get("total_qty"))
    remaining = _v2_safe_num(row.get("remaining_qty"))
    available = _v2_safe_num(row.get("available_to_add_qty"))
    planned = _v2_safe_num(row.get("already_planned_qty"))
    if (
        not_required > 0
        and remaining <= 0
        and executed_total >= effective_required
        and effective_required > 0
    ):
        return V2_SCOPE_STATUS_NOT_REQUIRED
    # COMPLETED: project qty fully covered by executed (incl. over-execution vs BOQ).
    if total_qty > 0 and executed_total >= total_qty:
        return "Выполнено"
    if _v2_safe_num(row.get("overrun_qty")) > 0:
        return V2_SCOPE_STATUS_OVERRUN
    return _v2_resolve_available_status(remaining, available, planned)


def filter_invalid_v2_boq_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Исключить пустые заголовки/разделы без цены, стоимости, остатка и объёма.

    KEEP if any of:
    - unit_price > 0
    - total_value > 0
    - remaining_qty > 0  (from planning_remaining_qty after normalize)
    - total_qty > 0  (real BOQ with project qty; may be COMPLETED with remaining=0)
    """
    if df.empty:
        return df, 0
    unit_price = pd.to_numeric(df.get("unit_price"), errors="coerce").fillna(0.0)
    total_value = pd.to_numeric(df.get("total_value"), errors="coerce").fillna(0.0)
    # After normalize_v2_scope_df the view field is remaining_qty;
    # accept planning_remaining_qty if present on raw-like frames.
    if "remaining_qty" in df.columns:
        remaining = pd.to_numeric(df["remaining_qty"], errors="coerce").fillna(0.0)
    elif "planning_remaining_qty" in df.columns:
        remaining = pd.to_numeric(df["planning_remaining_qty"], errors="coerce").fillna(0.0)
    else:
        remaining = pd.Series(0.0, index=df.index)
    # After normalize: total_qty; accept total_project_qty on raw-like frames.
    if "total_qty" in df.columns:
        total_qty = pd.to_numeric(df["total_qty"], errors="coerce").fillna(0.0)
    elif "total_project_qty" in df.columns:
        total_qty = pd.to_numeric(df["total_project_qty"], errors="coerce").fillna(0.0)
    else:
        total_qty = pd.Series(0.0, index=df.index)
    valid_mask = (
        (unit_price > 0) | (total_value > 0) | (remaining > 0) | (total_qty > 0)
    )
    excluded = int((~valid_mask).sum())
    return df[valid_mask].reset_index(drop=True), excluded
