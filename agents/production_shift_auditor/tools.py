"""PSAA allowlisted tools — no credentials, no product writes, no SQL."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from agents.production_shift_auditor.contracts import ShiftAuditArtifact, ShiftAuditInput
from agents.production_shift_auditor.history_contracts import PersistHistoryResult
from agents.production_shift_auditor.history_store import ShiftAuditHistoryStore
from security.agent_execution_context import (
    TOOL_LOAD_SHIFT_AUDIT_HISTORY,
    TOOL_LOAD_SHIFT_DAILY_PROGRESS,
    TOOL_PERSIST_SHIFT_AUDIT_HISTORY,
    AgentExecutionContext,
)
from security.trusted_audit_history_executor import (
    execute_load_shift_audit_history,
    execute_persist_shift_audit_history,
)
from security.trusted_read_executor import (
    ToolPermissionError,
    execute_shift_daily_progress_read,
    validate_context_for_tool,
)


def load_shift_daily_progress(
    context: AgentExecutionContext,
    *,
    crew_id: str,
    work_date: str,
    shift_type: Optional[str] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Narrow READ tool: daily_progress_active for one shift grain."""
    validate_context_for_tool(context, TOOL_LOAD_SHIFT_DAILY_PROGRESS)
    return execute_shift_daily_progress_read(
        context,
        crew_id=crew_id,
        work_date=work_date,
        shift_type=shift_type,
    )


def persist_shift_audit_history(
    context: AgentExecutionContext,
    *,
    audit_input: ShiftAuditInput,
    artifact: ShiftAuditArtifact,
    store: ShiftAuditHistoryStore,
) -> PersistHistoryResult:
    """Controlled ARTIFACT PERSIST — own PSAA history only. Not product WRITE."""
    validate_context_for_tool(context, TOOL_PERSIST_SHIFT_AUDIT_HISTORY)
    return execute_persist_shift_audit_history(
        context,
        audit_input=audit_input,
        artifact=artifact,
        store=store,
    )


def load_shift_audit_history(
    context: AgentExecutionContext,
    *,
    store: ShiftAuditHistoryStore,
    audit_id: Optional[str] = None,
    work_date: Optional[str] = None,
    crew_id: Optional[str] = None,
    shift_type: Optional[str] = None,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """Project-scoped history READ."""
    validate_context_for_tool(context, TOOL_LOAD_SHIFT_AUDIT_HISTORY)
    return execute_load_shift_audit_history(
        context,
        store=store,
        audit_id=audit_id,
        work_date=work_date,
        crew_id=crew_id,
        shift_type=shift_type,
    )


__all__ = [
    "load_shift_daily_progress",
    "persist_shift_audit_history",
    "load_shift_audit_history",
    "ToolPermissionError",
]
