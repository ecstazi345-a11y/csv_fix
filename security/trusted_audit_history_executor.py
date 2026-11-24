"""EOS-SEC controlled ARTIFACT PERSIST for PSAA history only.

Not product WRITE. write_allowed remains False.
Never touches daily_progress_*, Airtable, norms, payroll, or acceptance tables.
"""

from __future__ import annotations

from typing import Any, Optional

from agents.production_shift_auditor.history_contracts import (
    CODE_HISTORY_PROJECT_DENIED,
    PersistHistoryResult,
    ShiftAuditHistoryError,
    ShiftAuditHistoryRecord,
    build_history_record,
)
from agents.production_shift_auditor.history_store import ShiftAuditHistoryStore
from agents.production_shift_auditor.contracts import (
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from security.agent_execution_context import (
    TOOL_PERSIST_SHIFT_AUDIT_HISTORY,
    TOOL_LOAD_SHIFT_AUDIT_HISTORY,
    AgentExecutionContext,
)
from security.sanitize import assert_no_secrets_in_payload, redact_sensitive_text
from security.trusted_read_executor import ToolPermissionError, validate_context_for_tool


def execute_persist_shift_audit_history(
    context: AgentExecutionContext,
    *,
    audit_input: ShiftAuditInput,
    artifact: ShiftAuditArtifact,
    store: ShiftAuditHistoryStore,
) -> PersistHistoryResult:
    """Persist own PSAA artifact snapshot — controlled, project-scoped, fail-closed."""
    validate_context_for_tool(context, TOOL_PERSIST_SHIFT_AUDIT_HISTORY)
    if context.agent_code != "PRODUCTION_SHIFT_AUDITOR":
        raise ToolPermissionError(
            "AGENT_NOT_ALLOWED",
            "only PRODUCTION_SHIFT_AUDITOR may persist shift audit history",
        )
    if audit_input.project_code != context.project_code:
        raise ShiftAuditHistoryError(
            CODE_HISTORY_PROJECT_DENIED,
            "audit_input.project_code does not match AgentExecutionContext.project_code",
        )
    if artifact.input_provenance.get("project_code") not in (
        None,
        context.project_code,
    ):
        # provenance project must not disagree when present
        if artifact.input_provenance.get("project_code") != context.project_code:
            raise ShiftAuditHistoryError(
                CODE_HISTORY_PROJECT_DENIED,
                "artifact provenance project_code mismatch",
            )

    record = build_history_record(audit_input, artifact)
    assert_no_secrets_in_payload(record.to_dict())
    try:
        result = store.put_if_absent(record)
    except ShiftAuditHistoryError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ShiftAuditHistoryError(
            "PSAA_HISTORY_WRITE_FAILED",
            redact_sensitive_text(str(exc)),
        ) from exc
    assert_no_secrets_in_payload(result.record.to_dict())
    return result


def execute_load_shift_audit_history(
    context: AgentExecutionContext,
    *,
    store: ShiftAuditHistoryStore,
    audit_id: Optional[str] = None,
    work_date: Optional[str] = None,
    crew_id: Optional[str] = None,
    shift_type: Optional[str] = None,
) -> tuple[tuple[ShiftAuditHistoryRecord, ...], dict[str, Any]]:
    """Project-scoped history READ. Cross-project access denied."""
    validate_context_for_tool(context, TOOL_LOAD_SHIFT_AUDIT_HISTORY)
    project = context.project_code

    if audit_id:
        rec = store.get_by_audit_id(audit_id, project_code=project)
        rows = (rec,) if rec is not None else ()
        return rows, {"mode": "by_audit_id", "project_code": project, "row_count": len(rows)}

    if not work_date or not crew_id:
        raise ShiftAuditHistoryError(
            "PSAA_HISTORY_BLOCKER",
            "work_date and crew_id are required when audit_id is not provided",
        )
    rows = store.list_for_shift(
        project_code=project,
        work_date=work_date,
        crew_id=crew_id,
        shift_type=shift_type,
    )
    return rows, {
        "mode": "by_shift_grain",
        "project_code": project,
        "work_date": work_date,
        "crew_id": crew_id,
        "shift_type": shift_type,
        "row_count": len(rows),
    }
