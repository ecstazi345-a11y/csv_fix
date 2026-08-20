"""
Streamlit-free READ adapters for Monthly Plan Constructor Agent (MPCA-001).

No writes. No session_state. No page imports.
Column-minimized selects. Credentials stay in this infrastructure layer only.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import pandas as pd

from security.sanitize import (
    assert_no_secrets_in_payload,
    redact_sensitive_text,
    sanitize_read_error,
)
from services.supabase_client import supabase

# Re-export for callers that imported sanitize helpers from this module.
__all__ = [
    "ALLOWED_READ_SOURCES",
    "SCOPE_SELECT_COLUMNS",
    "ADJUSTMENT_SELECT_COLUMNS",
    "PLAN_LINE_SELECT_COLUMNS",
    "load_constructor_scope",
    "load_constructor_adjustments",
    "load_constructor_month_plan_lines",
    "sanitize_read_error",
    "redact_sensitive_text",
    "assert_no_secrets_in_payload",
]

SCOPE_VIEW = "monthly_scope_picker_view"
ADJUSTMENTS_TABLE = "monthly_scope_manual_adjustments"
PLAN_LINES_TABLE = "monthly_plan_lines_v2"

ALLOWED_READ_SOURCES = frozenset({SCOPE_VIEW, ADJUSTMENTS_TABLE, PLAN_LINES_TABLE})

# Column allowlists — AGENT READS ONLY WHAT IT NEEDS (fixed in infrastructure).
SCOPE_SELECT_COLUMNS: tuple[str, ...] = (
    "project_code",
    "facility_building",
    "construction_discipline",
    "boq_code",
    "boq_name",
    "unit_of_measure",
    "total_project_qty",
    "executed_qty_all_time",
    "manual_executed_before_system",
    "manual_verified_remaining_qty",
    "planning_remaining_qty",
    "unit_price",
    "total_project_value",
    "system_label",
    "iwp_id",
)

ADJUSTMENT_SELECT_COLUMNS: tuple[str, ...] = (
    "project_code",
    "facility_building",
    "construction_discipline",
    "boq_code",
    "not_required_qty",
    "not_required_reason",
)

PLAN_LINE_SELECT_COLUMNS: tuple[str, ...] = (
    "plan_line_id",
    "client_line_uid",
    "project_code",
    "month_key",
    "facility",
    "discipline",
    "system",
    "iwp",
    "boq_code",
    "planned_qty",
    "crew",
    "status",
)

# Product Constructor statuses that reserve monthly volume.
ACTIVE_PLAN_LINE_STATUSES = frozenset({"NOT_SENT", "SENT_TO_ADMISSION"})


def _safe_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text


def _scoped_read_client():
    """
    Least-privilege product client: SUPABASE_KEY via services.supabase_client.
    Never returns a service-role client.
    """
    return supabase


def _privileged_adjustments_client():
    """
    Explicit privileged client for adjustments only.

    Required while RLS on monthly_scope_manual_adjustments blocks SUPABASE_KEY.
    Does not silently wrap scoped failures — caller must record credential_env.
    """
    url = os.getenv("SUPABASE_URL")
    secret = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret:
        return None
    from supabase import create_client

    return create_client(url, secret)


def _select_clause(columns: tuple[str, ...]) -> str:
    if not columns or "*" in columns:
        raise ValueError("select(*) forbidden; explicit columns required")
    return ",".join(columns)


def _alias_scope_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map view physical names to domain consumer aliases (no formula change)."""
    if df.empty:
        return df
    out = df.copy()
    if "system" not in out.columns and "system_label" in out.columns:
        out["system"] = out["system_label"]
    if "iwp" not in out.columns and "iwp_id" in out.columns:
        out["iwp"] = out["iwp_id"]
    if "unit" not in out.columns and "unit_of_measure" in out.columns:
        out["unit"] = out["unit_of_measure"]
    if "facility" not in out.columns and "facility_building" in out.columns:
        out["facility"] = out["facility_building"]
    if "discipline" not in out.columns and "construction_discipline" in out.columns:
        out["discipline"] = out["construction_discipline"]
    return out


def load_constructor_scope(
    project_code: Optional[str] = None,
    *,
    limit: int = 10000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """READ monthly_scope_picker_view with column allowlist. Uses SUPABASE_KEY."""
    meta: dict[str, Any] = {
        "source": SCOPE_VIEW,
        "error": None,
        "row_count": 0,
        "project_code_filter": _safe_text(project_code) or None,
        "credential_env": "SUPABASE_KEY",
        "select_columns": list(SCOPE_SELECT_COLUMNS),
    }
    try:
        client = _scoped_read_client()
        query = (
            client.table(SCOPE_VIEW)
            .select(_select_clause(SCOPE_SELECT_COLUMNS))
            .limit(limit)
        )
        code = _safe_text(project_code)
        if code:
            query = query.eq("project_code", code)
        response = query.execute()
        df = _alias_scope_columns(pd.DataFrame(response.data or []))
        meta["row_count"] = len(df)
        return df, meta
    except Exception as exc:  # noqa: BLE001
        meta["error"] = sanitize_read_error(exc)
        return pd.DataFrame(), meta


def load_constructor_adjustments(
    project_code: Optional[str] = None,
    *,
    limit: int = 10000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    READ monthly_scope_manual_adjustments with column allowlist.

    Infrastructure blocker (proven by scoped smoke): SUPABASE_KEY receives 0 rows
    under current RLS, while privileged reads succeed. This loader therefore uses
    SUPABASE_SECRET_KEY **explicitly and only for this table** — no silent
    scoped→secret fallback after a failed KEY attempt.

    SECURITY RELEASE: remove privileged path after RLS grants SELECT on
    monthly_scope_manual_adjustments to the role behind SUPABASE_KEY.
    """
    meta: dict[str, Any] = {
        "source": ADJUSTMENTS_TABLE,
        "error": None,
        "row_count": 0,
        "project_code_filter": _safe_text(project_code) or None,
        "credential_env": "SUPABASE_SECRET_KEY",
        "select_columns": list(ADJUSTMENT_SELECT_COLUMNS),
        "scoped_read_blocked": True,
        "privileged_adjustments_read": True,
        "rls_blocker": (
            "SCOPED_READ_CREDENTIAL_BLOCKED: monthly_scope_manual_adjustments "
            "not readable under SUPABASE_KEY (RLS). Privileged read used for "
            "this source only until RLS/security release."
        ),
    }
    code = _safe_text(project_code)
    priv = _privileged_adjustments_client()
    if priv is None:
        meta["error"] = (
            "ADJUSTMENTS_PRIVILEGED_CREDENTIAL_MISSING: SUPABASE_SECRET_KEY not set; "
            "SUPABASE_KEY cannot read adjustments under current RLS."
        )
        meta["privileged_adjustments_read"] = False
        return pd.DataFrame(), meta
    try:
        query = (
            priv.table(ADJUSTMENTS_TABLE)
            .select(_select_clause(ADJUSTMENT_SELECT_COLUMNS))
            .limit(limit)
        )
        if code:
            query = query.eq("project_code", code)
        response = query.execute()
        df = pd.DataFrame(response.data or [])
        meta["row_count"] = len(df)
        return df, meta
    except Exception as exc:  # noqa: BLE001
        meta["error"] = sanitize_read_error(exc)
        return pd.DataFrame(), meta


def load_constructor_month_plan_lines(
    project_code: str,
    stored_month_key: str,
    *,
    limit: int = 10000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    READ monthly_plan_lines_v2 for project + stored RU month_key.

    Column allowlist. Uses SUPABASE_KEY only.
    """
    meta: dict[str, Any] = {
        "source": PLAN_LINES_TABLE,
        "error": None,
        "row_count": 0,
        "project_code": _safe_text(project_code),
        "month_key": _safe_text(stored_month_key),
        "active_statuses": sorted(ACTIVE_PLAN_LINE_STATUSES),
        "credential_env": "SUPABASE_KEY",
        "select_columns": list(PLAN_LINE_SELECT_COLUMNS),
    }
    code = _safe_text(project_code)
    month = _safe_text(stored_month_key)
    if not code or not month:
        meta["error"] = "blank_project_or_month"
        return pd.DataFrame(), meta
    try:
        client = _scoped_read_client()
        response = (
            client.table(PLAN_LINES_TABLE)
            .select(_select_clause(PLAN_LINE_SELECT_COLUMNS))
            .eq("project_code", code)
            .eq("month_key", month)
            .limit(limit)
            .execute()
        )
        df = pd.DataFrame(response.data or [])
        meta["row_count"] = len(df)
        return df, meta
    except Exception as exc:  # noqa: BLE001
        meta["error"] = sanitize_read_error(exc)
        return pd.DataFrame(), meta
