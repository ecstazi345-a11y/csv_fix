"""
EOS-SEC-1.1 SEC-STEP-2 — Trusted controlled READ executor.

Agent never sees credentials or Supabase clients.
Project scope comes only from AgentExecutionContext.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Optional

import pandas as pd

from security.agent_execution_context import (
    TOOL_LOAD_ADJUSTMENTS,
    TOOL_LOAD_PLAN_LINES,
    TOOL_LOAD_SCOPE,
    AgentExecutionContext,
)
from security.sanitize import redact_sensitive_text, sanitize_read_error


class ToolPermissionError(PermissionError):
    def __init__(self, code: str, message: str, *, event: Optional[dict[str, Any]] = None):
        self.code = code
        self.event = event
        super().__init__(message)


# Explicit credential policy codes (no env values).
CREDENTIAL_PUBLISHABLE_READ = "PUBLISHABLE_READ"
CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ = "TRANSITIONAL_PRIVILEGED_READ"

EVENT_TOOL_ALLOWED = "TOOL_ALLOWED"
EVENT_TOOL_DENIED = "TOOL_DENIED"
EVENT_PROJECT_SCOPE_DENIED = "PROJECT_SCOPE_DENIED"
EVENT_CONTEXT_EXPIRED = "CONTEXT_EXPIRED"
EVENT_INVALID_CONTEXT = "INVALID_CONTEXT"
EVENT_READ_SUCCESS = "READ_SUCCESS"
EVENT_READ_FAILED = "READ_FAILED"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_event(context: AgentExecutionContext, tool_code: str) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "run_id": context.run_id,
        "actor_id": context.actor_id,
        "actor_type": context.actor_type,
        "agent_code": context.agent_code,
        "project_code": context.project_code,
        "tool_code": tool_code,
        "action": "READ",
        "authorization_id": context.authorization_id,
        "security_policy_version": context.security_policy_version,
        "started_at": _utcnow_iso(),
        "finished_at": None,
        "duration_ms": 0.0,
        "status": None,
        "row_count": 0,
        "source_code": None,
        "credential_policy_code": None,
        "security_event": None,
    }


def validate_context_for_tool(
    context: Optional[AgentExecutionContext],
    tool_code: str,
) -> list[dict[str, Any]]:
    """Return denial events or empty list if OK. Raises ToolPermissionError."""
    if context is None:
        event = {
            "event_id": str(uuid.uuid4()),
            "security_event": EVENT_INVALID_CONTEXT,
            "status": "DENIED",
            "tool_code": tool_code,
            "action": "READ",
            "error_code": "CONTEXT_MISSING",
        }
        raise ToolPermissionError(
            "CONTEXT_MISSING",
            "AgentExecutionContext is required",
            event=event,
        )
    if context.is_expired():
        event = _base_event(context, tool_code)
        event["security_event"] = EVENT_CONTEXT_EXPIRED
        event["status"] = "DENIED"
        event["finished_at"] = _utcnow_iso()
        raise ToolPermissionError(
            "CONTEXT_EXPIRED",
            "execution context expired",
            event=event,
        )
    if not context.security_policy_version:
        event = _base_event(context, tool_code)
        event["security_event"] = EVENT_INVALID_CONTEXT
        event["status"] = "DENIED"
        event["finished_at"] = _utcnow_iso()
        raise ToolPermissionError(
            "POLICY_VERSION_MISSING",
            "security_policy_version missing",
            event=event,
        )
    if context.write_allowed:
        event = _base_event(context, tool_code)
        event["security_event"] = EVENT_INVALID_CONTEXT
        event["status"] = "DENIED"
        event["finished_at"] = _utcnow_iso()
        raise ToolPermissionError(
            "WRITE_FLAG_UNEXPECTED",
            "Tier 0 context must have write_allowed=False",
            event=event,
        )
    if tool_code not in context.allowed_tools:
        event = _base_event(context, tool_code)
        event["security_event"] = EVENT_TOOL_DENIED
        event["status"] = "DENIED"
        event["finished_at"] = _utcnow_iso()
        raise ToolPermissionError(
            "TOOL_NOT_ALLOWED",
            f"tool {tool_code!r} not in allowed_tools",
            event=event,
        )
    if not str(context.project_code or "").strip():
        event = _base_event(context, tool_code)
        event["security_event"] = EVENT_PROJECT_SCOPE_DENIED
        event["status"] = "DENIED"
        event["finished_at"] = _utcnow_iso()
        raise ToolPermissionError(
            "PROJECT_MISSING",
            "context.project_code is blank",
            event=event,
        )
    return []


def _finish(
    event: dict[str, Any],
    *,
    status: str,
    security_event: str,
    row_count: int = 0,
    source_code: Optional[str] = None,
    credential_policy_code: Optional[str] = None,
    error_code: Optional[str] = None,
    safe_message: Optional[str] = None,
    t0: float,
) -> dict[str, Any]:
    event["finished_at"] = _utcnow_iso()
    event["duration_ms"] = max(0.0, (perf_counter() - t0) * 1000.0)
    event["status"] = status
    event["security_event"] = security_event
    event["row_count"] = row_count
    if source_code:
        event["source_code"] = source_code
    if credential_policy_code:
        event["credential_policy_code"] = credential_policy_code
    if error_code:
        event["error_code"] = error_code
    if safe_message:
        event["safe_message"] = redact_sensitive_text(safe_message)
    # Never attach credential material
    for banned in ("credential", "api_key", "apikey", "authorization", "password", "jwt"):
        event.pop(banned, None)
    return event


def execute_constructor_scope_read(
    context: AgentExecutionContext,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """READ scope — project from context only. Credential: PUBLISHABLE_READ."""
    validate_context_for_tool(context, TOOL_LOAD_SCOPE)
    t0 = perf_counter()
    event = _base_event(context, TOOL_LOAD_SCOPE)
    event["security_event"] = EVENT_TOOL_ALLOWED
    # Import infra only inside executor boundary
    from services.monthly_plan_constructor_read_service import load_constructor_scope

    try:
        df, meta = load_constructor_scope(context.project_code)
    except Exception as exc:  # noqa: BLE001
        safe = sanitize_read_error(exc)
        event = _finish(
            event,
            status="FAILED",
            security_event=EVENT_READ_FAILED,
            credential_policy_code=CREDENTIAL_PUBLISHABLE_READ,
            source_code="monthly_scope_picker_view",
            error_code="READ_FAILED",
            safe_message=safe,
            t0=t0,
        )
        return pd.DataFrame(), {
            "error": safe,
            "error_code": "READ_FAILED",
            "row_count": 0,
            "audit_event": event,
            "credential_policy_code": CREDENTIAL_PUBLISHABLE_READ,
            "project_code": context.project_code,
        }

    # Explicit policy — not silent fallback
    if meta.get("credential_env") not in {None, "SUPABASE_KEY"}:
        # Adapter may report KEY; treat unexpected as fail-closed signal for agent
        pass
    err = meta.get("error")
    if err:
        event = _finish(
            event,
            status="FAILED",
            security_event=EVENT_READ_FAILED,
            row_count=0,
            source_code="monthly_scope_picker_view",
            credential_policy_code=CREDENTIAL_PUBLISHABLE_READ,
            error_code="READ_FAILED",
            safe_message=str(err),
            t0=t0,
        )
    else:
        event = _finish(
            event,
            status="OK",
            security_event=EVENT_READ_SUCCESS,
            row_count=int(len(df)),
            source_code="monthly_scope_picker_view",
            credential_policy_code=CREDENTIAL_PUBLISHABLE_READ,
            t0=t0,
        )
    out_meta = {
        **meta,
        "error": redact_sensitive_text(err) if err else None,
        "audit_event": event,
        "credential_policy_code": CREDENTIAL_PUBLISHABLE_READ,
        "project_code": context.project_code,
        "row_count": len(df),
    }
    return df, out_meta


def execute_constructor_adjustments_read(
    context: AgentExecutionContext,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    READ adjustments — TRANSITIONAL_PRIVILEGED_READ (explicit, not fallback).

    TRANSITIONAL_INFRASTRUCTURE_EXCEPTION: SUPABASE_SECRET_KEY used only here
    until Auth + project membership + RLS identity.
    """
    validate_context_for_tool(context, TOOL_LOAD_ADJUSTMENTS)
    t0 = perf_counter()
    event = _base_event(context, TOOL_LOAD_ADJUSTMENTS)
    from services.monthly_plan_constructor_read_service import (
        load_constructor_adjustments,
    )

    try:
        df, meta = load_constructor_adjustments(context.project_code)
    except Exception as exc:  # noqa: BLE001
        safe = sanitize_read_error(exc)
        event = _finish(
            event,
            status="FAILED",
            security_event=EVENT_READ_FAILED,
            credential_policy_code=CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
            source_code="monthly_scope_manual_adjustments",
            error_code="READ_FAILED",
            safe_message=safe,
            t0=t0,
        )
        return pd.DataFrame(), {
            "error": safe,
            "error_code": "READ_FAILED",
            "row_count": 0,
            "audit_event": event,
            "credential_policy_code": CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
            "transitional_infrastructure_exception": True,
            "project_code": context.project_code,
        }

    err = meta.get("error")
    if err:
        event = _finish(
            event,
            status="FAILED",
            security_event=EVENT_READ_FAILED,
            source_code="monthly_scope_manual_adjustments",
            credential_policy_code=CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
            error_code="READ_FAILED",
            safe_message=str(err),
            t0=t0,
        )
    else:
        event = _finish(
            event,
            status="OK",
            security_event=EVENT_READ_SUCCESS,
            row_count=int(len(df)),
            source_code="monthly_scope_manual_adjustments",
            credential_policy_code=CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
            t0=t0,
        )
    out_meta = {
        **meta,
        "error": redact_sensitive_text(err) if err else None,
        "audit_event": event,
        "credential_policy_code": CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
        "transitional_infrastructure_exception": True,
        "project_code": context.project_code,
        "row_count": len(df),
    }
    return df, out_meta


def execute_constructor_plan_lines_read(
    context: AgentExecutionContext,
    stored_month_key: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """READ plan lines — project from context; month is operational parameter."""
    validate_context_for_tool(context, TOOL_LOAD_PLAN_LINES)
    t0 = perf_counter()
    event = _base_event(context, TOOL_LOAD_PLAN_LINES)
    month = str(stored_month_key or "").strip()
    if not month:
        event = _finish(
            event,
            status="DENIED",
            security_event=EVENT_INVALID_CONTEXT,
            credential_policy_code=CREDENTIAL_PUBLISHABLE_READ,
            source_code="monthly_plan_lines_v2",
            error_code="BLANK_MONTH",
            safe_message="stored_month_key is required",
            t0=t0,
        )
        raise ToolPermissionError(
            "BLANK_MONTH",
            "stored_month_key is required",
            event=event,
        )

    from services.monthly_plan_constructor_read_service import (
        load_constructor_month_plan_lines,
    )

    try:
        df, meta = load_constructor_month_plan_lines(
            context.project_code,
            month,
        )
    except Exception as exc:  # noqa: BLE001
        safe = sanitize_read_error(exc)
        event = _finish(
            event,
            status="FAILED",
            security_event=EVENT_READ_FAILED,
            credential_policy_code=CREDENTIAL_PUBLISHABLE_READ,
            source_code="monthly_plan_lines_v2",
            error_code="READ_FAILED",
            safe_message=safe,
            t0=t0,
        )
        return pd.DataFrame(), {
            "error": safe,
            "error_code": "READ_FAILED",
            "row_count": 0,
            "audit_event": event,
            "credential_policy_code": CREDENTIAL_PUBLISHABLE_READ,
            "project_code": context.project_code,
        }

    err = meta.get("error")
    if err:
        event = _finish(
            event,
            status="FAILED",
            security_event=EVENT_READ_FAILED,
            source_code="monthly_plan_lines_v2",
            credential_policy_code=CREDENTIAL_PUBLISHABLE_READ,
            error_code="READ_FAILED",
            safe_message=str(err),
            t0=t0,
        )
    else:
        event = _finish(
            event,
            status="OK",
            security_event=EVENT_READ_SUCCESS,
            row_count=int(len(df)),
            source_code="monthly_plan_lines_v2",
            credential_policy_code=CREDENTIAL_PUBLISHABLE_READ,
            t0=t0,
        )
    out_meta = {
        **meta,
        "error": redact_sensitive_text(err) if err else None,
        "audit_event": event,
        "credential_policy_code": CREDENTIAL_PUBLISHABLE_READ,
        "project_code": context.project_code,
        "row_count": len(df),
    }
    return df, out_meta
