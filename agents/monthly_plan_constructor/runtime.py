"""
MPCA-001 — Monthly Plan Constructor Agent runtime.

Orchestrates tools → skills → validators → trace → AgentConstructorRun.
READ / CALCULATE / CLASSIFY / PROPOSE only. No product writes. No LLM.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Optional

import pandas as pd

from agents.monthly_plan_constructor.contracts import (
    AGENT_CODE,
    AGENT_NAME_RU,
    AgentConstructorRun,
    BusinessAction,
    STATE_ANALYZING,
    STATE_FAILED,
    STATE_NEEDS_HUMAN,
    STATE_PROPOSAL_READY,
    STATE_READING,
    STATE_STARTING,
    STATE_VALIDATING,
    TraceEvent,
)
from agents.monthly_plan_constructor import skills as skill_mod
from agents.monthly_plan_constructor import tools as tool_mod
from agents.monthly_plan_constructor.validators import (
    validate_proposal,
    validate_run_inputs,
    validate_trace,
)
from security.agent_execution_context import (
    ContextIssueError,
    issue_read_only_agent_context,
)
from security.sanitize import assert_no_secrets_in_payload, redact_sensitive_text
from security.trusted_read_executor import ToolPermissionError
from utils.month_key import normalize_month_key


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    return str(uuid.uuid4())


class _TraceBuffer:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.events: list[TraceEvent] = []

    def record(
        self,
        step_code: str,
        step_name: str,
        *,
        status: str = "OK",
        input_count: int = 0,
        output_count: int = 0,
        summary: str = "",
        error: Optional[str] = None,
        next_recipient: Optional[str] = None,
        started: Optional[float] = None,
    ) -> None:
        finished = perf_counter()
        started_at = started if started is not None else finished
        duration_ms = max(0.0, (finished - started_at) * 1000.0)
        now = _utcnow_iso()
        self.events.append(
            TraceEvent(
                event_id=str(uuid.uuid4()),
                run_id=self.run_id,
                agent_code=AGENT_CODE,
                step_code=step_code,
                step_name=step_name,
                started_at=now,
                finished_at=now,
                duration_ms=duration_ms,
                status=status,
                input_count=input_count,
                output_count=output_count,
                summary=redact_sensitive_text(summary or ""),
                next_recipient=next_recipient,
                error=redact_sensitive_text(error) if error else None,
            )
        )


def run_monthly_plan_constructor_agent(
    project_code: str,
    stored_month_key: str,
    *,
    load_scope_fn: Optional[Callable[..., Any]] = None,
    load_adjustments_fn: Optional[Callable[..., Any]] = None,
    load_plan_lines_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """
    Execute Constructor Agent v0.1 (deterministic, read-only).

    Optional load_*_fn allow unit tests to inject DataFrames without Supabase.
    """
    run_id = _new_run_id()
    started_wall = _utcnow_iso()
    t0 = perf_counter()
    trace = _TraceBuffer(run_id)
    actions: list[BusinessAction] = []
    errors: list[dict[str, Any]] = []

    t_step = perf_counter()
    trace.record(
        "START",
        "Старт агента",
        summary=f"project={project_code!r} month={stored_month_key!r}",
        started=t_step,
    )

    input_errors = validate_run_inputs(project_code, stored_month_key)
    canonical = normalize_month_key(stored_month_key)
    if input_errors:
        errors.extend(input_errors)
        trace.record(
            "FINISH",
            "Завершение с ошибкой входа",
            status="FAILED",
            error="; ".join(e["message"] for e in input_errors),
            started=perf_counter(),
        )
        finished = _utcnow_iso()
        duration_ms = max(0.0, (perf_counter() - t0) * 1000.0)
        run = AgentConstructorRun(
            run_id=run_id,
            agent_code=AGENT_CODE,
            agent_name=AGENT_NAME_RU,
            project_code=str(project_code or ""),
            month_key=str(stored_month_key or ""),
            month_key_canonical=canonical,
            started_at=started_wall,
            finished_at=finished,
            duration_ms=duration_ms,
            state=STATE_FAILED,
            counts={},
            errors=errors,
            actions_performed=[],
            handoff={"proposal_ready": False, "admission_handoff_ready": False},
            trace=[e.to_dict() for e in trace.events],
        )
        payload = run.to_dict()
        assert_no_secrets_in_payload(payload)
        return payload

    # Trusted context — issuer owns permissions; runtime does not invent tools.
    security_audit: list[dict[str, Any]] = []
    try:
        context = issue_read_only_agent_context(
            agent_code=AGENT_CODE,
            project_code=str(project_code),
            run_id=run_id,
        )
    except ContextIssueError as exc:
        errors.append({"code": exc.code, "message": str(exc)})
        trace.record(
            "FINISH",
            "Context issuance failed",
            status="FAILED",
            error=str(exc),
            started=perf_counter(),
        )
        finished = _utcnow_iso()
        payload = AgentConstructorRun(
            run_id=run_id,
            agent_code=AGENT_CODE,
            agent_name=AGENT_NAME_RU,
            project_code=str(project_code or ""),
            month_key=str(stored_month_key or ""),
            month_key_canonical=canonical,
            started_at=started_wall,
            finished_at=finished,
            duration_ms=max(0.0, (perf_counter() - t0) * 1000.0),
            state=STATE_FAILED,
            counts={},
            errors=errors,
            actions_performed=[],
            handoff={"proposal_ready": False, "admission_handoff_ready": False},
            trace=[e.to_dict() for e in trace.events],
            metrics={"execution_context_issued": False},
        ).to_dict()
        assert_no_secrets_in_payload(payload)
        return payload

    # --- READ via thin tools → trusted executor (or test injectors) ---
    t_step = perf_counter()
    try:
        if load_scope_fn is not None:
            scope_df, scope_meta = load_scope_fn(context.project_code)
        else:
            scope_df, scope_meta = tool_mod.load_scope(context)
    except ToolPermissionError as exc:
        if exc.event:
            security_audit.append(exc.event)
        errors.append({"code": exc.code, "message": str(exc)})
        scope_df, scope_meta = pd.DataFrame(), {"error": str(exc), "row_count": 0}
    if scope_meta.get("audit_event"):
        security_audit.append(scope_meta["audit_event"])
    skill_mod.skill_get_working_scope(scope_df, scope_meta)
    trace.record(
        "LOAD_SCOPE",
        "Загрузка рабочего состава",
        input_count=1,
        output_count=int(scope_meta.get("row_count") or len(scope_df)),
        summary=scope_meta.get("error") or f"rows={len(scope_df)}",
        status="ERROR" if scope_meta.get("error") else "OK",
        error=scope_meta.get("error"),
        started=t_step,
    )
    actions.append(
        BusinessAction(
            action="Просмотрен рабочий перечень",
            affected_count=int(len(scope_df)),
            result="Рабочий состав загружен"
            if not scope_meta.get("error")
            else "Ошибка чтения scope",
        )
    )

    t_step = perf_counter()
    try:
        if load_adjustments_fn is not None:
            adj_df, adj_meta = load_adjustments_fn(context.project_code)
        else:
            adj_df, adj_meta = tool_mod.load_adjustments(context)
    except ToolPermissionError as exc:
        if exc.event:
            security_audit.append(exc.event)
        errors.append({"code": exc.code, "message": str(exc)})
        adj_df, adj_meta = pd.DataFrame(), {"error": str(exc), "row_count": 0}
    if adj_meta.get("audit_event"):
        security_audit.append(adj_meta["audit_event"])
    trace.record(
        "LOAD_ADJUSTMENTS",
        "Загрузка корректировок not_required",
        input_count=1,
        output_count=int(adj_meta.get("row_count") or len(adj_df)),
        summary=adj_meta.get("error") or f"rows={len(adj_df)}",
        status="ERROR" if adj_meta.get("error") else "OK",
        error=adj_meta.get("error"),
        started=t_step,
    )
    actions.append(
        BusinessAction(
            action="Прочитаны ручные исключения остатка",
            affected_count=int(len(adj_df)),
            result="Adjustments загружены"
            if not adj_meta.get("error")
            else "Ошибка чтения adjustments",
        )
    )

    t_step = perf_counter()
    try:
        if load_plan_lines_fn is not None:
            plan_df, plan_meta = load_plan_lines_fn(
                context.project_code, stored_month_key
            )
        else:
            plan_df, plan_meta = tool_mod.load_existing_month_plan_lines(
                context, stored_month_key
            )
    except ToolPermissionError as exc:
        if exc.event:
            security_audit.append(exc.event)
        errors.append({"code": exc.code, "message": str(exc)})
        plan_df, plan_meta = pd.DataFrame(), {"error": str(exc), "row_count": 0}
    if plan_meta.get("audit_event"):
        security_audit.append(plan_meta["audit_event"])
    trace.record(
        "LOAD_EXISTING_PLAN",
        "Загрузка существующего месячного плана",
        input_count=1,
        output_count=int(plan_meta.get("row_count") or len(plan_df)),
        summary=plan_meta.get("error") or f"rows={len(plan_df)}",
        status="ERROR" if plan_meta.get("error") else "OK",
        error=plan_meta.get("error"),
        started=t_step,
    )
    actions.append(
        BusinessAction(
            action="Учтён существующий месячный план",
            affected_count=int(len(plan_df)),
            result="Строки плана загружены"
            if not plan_meta.get("error")
            else "Ошибка чтения plan lines",
        )
    )

    # --- ANALYZE (pure) ---
    t_step = perf_counter()
    trace.record(
        "NORMALIZE",
        "Нормализация входных данных",
        input_count=len(scope_df),
        summary="normalize_scope_raw_df + month canonical",
        started=t_step,
    )

    t_step = perf_counter()
    proposal = skill_mod.skill_run_pure_proposal(
        scope_df,
        adj_df,
        plan_df,
        context.project_code,
        stored_month_key,
        scope_load_error=scope_meta.get("error"),
        adjustments_load_error=adj_meta.get("error"),
        plan_lines_load_error=plan_meta.get("error"),
    )
    trace.record(
        "CALCULATE_AVAILABILITY",
        "Расчёт физической доступности",
        input_count=len(scope_df),
        output_count=int(proposal.get("counts", {}).get("scanned") or 0),
        summary="not_required applied once; frozen BOQ metrics",
        started=t_step,
    )
    trace.record(
        "APPLY_EXISTING_PLAN",
        "Применение already_planned",
        input_count=len(plan_df),
        output_count=int(proposal.get("counts", {}).get("scanned") or 0),
        summary="aggregate by facility+discipline+boq",
        started=perf_counter(),
    )
    trace.record(
        "CLASSIFY",
        "Классификация позиций",
        input_count=int(proposal.get("counts", {}).get("scanned") or 0),
        output_count=int(proposal.get("counts", {}).get("candidates") or 0),
        summary="candidate vs exclusion",
        started=perf_counter(),
    )

    counts = dict(proposal.get("counts") or {})
    candidates = list(proposal.get("candidates") or [])
    exclusions = list(proposal.get("exclusions") or [])
    human_issues = list(proposal.get("human_issues") or [])
    errors.extend(list(proposal.get("errors") or []))

    excl_completed = int(counts.get("excluded_completed") or 0)
    excl_nr = int(counts.get("excluded_no_remainder") or 0)
    excl_ap = int(counts.get("excluded_already_planned") or 0)
    if excl_completed:
        actions.append(
            BusinessAction(
                action="Исключены завершённые позиции",
                affected_count=excl_completed,
                result="completed → не кандидаты",
            )
        )
    if excl_nr:
        actions.append(
            BusinessAction(
                action="Исключены позиции без остатка",
                affected_count=excl_nr,
                result="no remainder / not_required",
            )
        )
    if excl_ap:
        actions.append(
            BusinessAction(
                action="Исключены полностью запланированные",
                affected_count=excl_ap,
                result="available_to_add <= 0",
            )
        )

    skill_mod.skill_exclude_unavailable(proposal)
    trace.record(
        "BUILD_CANDIDATES",
        "Формирование кандидатов",
        input_count=int(counts.get("scanned") or 0),
        output_count=len(candidates),
        summary=f"candidates={len(candidates)}",
        started=perf_counter(),
    )
    actions.append(
        BusinessAction(
            action="Сформирован кандидатный состав",
            affected_count=len(candidates),
            result="OPEN_FOR_PLANNING / PARTIAL_REMAINING",
        )
    )

    conflict_skill = skill_mod.skill_detect_conflicts(human_issues)
    skill_mod.skill_build_human_exceptions(human_issues)
    trace.record(
        "DETECT_HUMAN_ISSUES",
        "Выявление исключений для человека",
        input_count=len(candidates),
        output_count=len(human_issues),
        summary=f"issues={len(human_issues)} conflicts={conflict_skill['output']['conflict_count']}",
        started=perf_counter(),
    )
    if human_issues:
        actions.append(
            BusinessAction(
                action="Подняты исключения человеку",
                affected_count=len(human_issues),
                result="human_issues сформированы",
            )
        )

    # --- VALIDATE ---
    t_step = perf_counter()
    val_errors = validate_proposal(proposal)
    errors.extend(val_errors)
    trace.record(
        "VALIDATE",
        "Валидация предложения",
        input_count=len(candidates),
        output_count=len(val_errors),
        status="ERROR" if val_errors else "OK",
        summary=f"validation_errors={len(val_errors)}",
        error="; ".join(e.get("message", "") for e in val_errors) or None,
        started=t_step,
    )

    handoff_skill = skill_mod.skill_prepare_handoff(
        candidates=candidates,
        human_issues=human_issues,
        errors=errors,
        proposal_ok=bool(proposal.get("ok")) and not val_errors,
    )
    handoff = handoff_skill["output"]["handoff"]
    trace.record(
        "PREPARE_HANDOFF",
        "Подготовка handoff",
        input_count=len(candidates),
        output_count=1,
        summary=(
            f"proposal_ready={handoff.get('proposal_ready')} "
            f"admission={handoff.get('admission_handoff_ready')}"
        ),
        next_recipient=handoff.get("recipient"),
        started=perf_counter(),
    )

    blockers = [
        i
        for i in human_issues
        if str(i.get("severity") or "").upper() == "BLOCKER"
    ]
    if errors and not proposal.get("ok"):
        state = STATE_FAILED
    elif blockers:
        state = STATE_NEEDS_HUMAN
    elif handoff.get("proposal_ready"):
        state = STATE_PROPOSAL_READY
    else:
        state = STATE_FAILED

    finished = _utcnow_iso()
    duration_ms = max(0.0, (perf_counter() - t0) * 1000.0)
    trace.record(
        "FINISH",
        "Завершение run",
        status="OK" if state != STATE_FAILED else "FAILED",
        summary=f"lifecycle finished; business_state={state}",
        started=perf_counter(),
    )

    trace_dicts = [e.to_dict() for e in trace.events]
    trace_errors = validate_trace(trace_dicts)
    if trace_errors:
        errors.extend(trace_errors)

    scanned = int(counts.get("scanned") or 0)
    automation_ratio = float((proposal.get("meta") or {}).get("automation_ratio") or 0.0)
    metrics = {
        "scanned": scanned,
        "candidates": len(candidates),
        "excluded_completed": excl_completed,
        "excluded_no_remainder": excl_nr,
        "excluded_already_planned": excl_ap,
        "excluded_invalid": int(counts.get("excluded_invalid") or 0),
        "conflicts": int(counts.get("conflicts") or 0),
        "human_issues": len(human_issues),
        "business_actions": len(actions),
        "trace_events": len(trace_dicts),
        "automation_ratio": automation_ratio,
        "duration_ms": duration_ms,
        "proposal_ready": bool(handoff.get("proposal_ready")),
        "admission_handoff_ready": bool(handoff.get("admission_handoff_ready")),
        "execution_context_issued": True,
        "project_scope_enforced": True,
        "security_audit_event_count": len(security_audit),
    }

    counts_out = {
        "scanned": scanned,
        "candidates": len(candidates),
        "excluded_completed": excl_completed,
        "excluded_no_remainder": excl_nr,
        "excluded_already_planned": excl_ap,
        "excluded_invalid": int(counts.get("excluded_invalid") or 0),
        "conflicts": int(counts.get("conflicts") or 0),
        "human_issues": len(human_issues),
    }

    sanitized_errors: list[dict[str, Any]] = []
    for err in errors:
        if not isinstance(err, dict):
            sanitized_errors.append(
                {"code": "ERROR", "message": redact_sensitive_text(str(err))}
            )
            continue
        sanitized_errors.append(
            {
                **err,
                "message": redact_sensitive_text(str(err.get("message") or "")),
            }
        )

    run = AgentConstructorRun(
        run_id=run_id,
        agent_code=AGENT_CODE,
        agent_name=AGENT_NAME_RU,
        project_code=str(context.project_code),
        month_key=str(stored_month_key),
        month_key_canonical=canonical,
        started_at=started_wall,
        finished_at=finished,
        duration_ms=duration_ms,
        state=state,
        counts=counts_out,
        proposed_candidates=candidates,
        human_issues=human_issues,
        exclusions=exclusions,
        actions_performed=[a.to_dict() for a in actions],
        actions_pending_approval=[],
        handoff=handoff,
        errors=sanitized_errors,
        trace=trace_dicts,
        metrics=metrics,
    )
    # Ensure JSON-serializable and no env secrets in structured output
    payload = run.to_dict()
    payload["execution_context"] = context.to_safe_dict()
    payload["security_audit_events"] = security_audit
    json.dumps(payload, ensure_ascii=False, default=str)
    assert_no_secrets_in_payload(payload)
    return payload


# Silence unused import warnings for state constants used by docs/tests
_ = (STATE_STARTING, STATE_READING, STATE_ANALYZING, STATE_VALIDATING)
