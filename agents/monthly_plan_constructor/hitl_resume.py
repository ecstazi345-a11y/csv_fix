"""
Constructor Runtime v0.1 Increment 8 — deterministic HITL resume helpers.

NORMAL ADVANCE != HUMAN RESUME.
Professional decision logic lives here — not in LangGraph nodes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    CODE_RUN_ABORTED_BY_HUMAN,
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    HitlContractError,
    ConstructorHumanDecisionRequest,
    ConstructorResumeCommand,
    allowed_decisions_for_reason,
    build_human_decision_request,
    build_scope_summary,
    coerce_resume_command,
    compute_eos_interrupt_id,
    count_wait_ordinal,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    STATUS_APPLYING_HUMAN_DECISION,
    STATUS_FAILED,
    STATUS_REALITY_LOADED,
    STATUS_REVALIDATING_REALITY,
    STATUS_WAITING_FOR_HUMAN,
    ConstructorLifecycleState,
    LifecycleError,
    _append_transition,
    _map_domain_failure,
    _require_aware_utc,
)
from agents.monthly_plan_constructor.mission_scope import (
    ConstructorMissionScope,
    MissionScopeError,
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    ScopeReader,
    SecureReadError,
    read_constructor_reality,
)
from security.agent_execution_context import AgentExecutionContext

SOURCE_HITL_RESUME = "HITL_RESUME"
SOURCE_SECURE_READ = "SECURE_READ"

_SCOPE_DIMS = (
    "facility_scope",
    "discipline_scope",
    "system_scope",
    "iwp_scope",
    "queue_scope",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_decision_request_from_lifecycle(
    state: ConstructorLifecycleState,
    *,
    created_at: Optional[datetime] = None,
) -> ConstructorHumanDecisionRequest:
    """Deterministic request from authoritative WAIT lifecycle evidence."""
    if state.status != STATUS_WAITING_FOR_HUMAN:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "decision request requires WAITING_FOR_HUMAN",
        )
    reason = (state.error_code or "").strip().upper()
    if not reason:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "WAITING_FOR_HUMAN requires error_code",
        )
    wait_ordinal = count_wait_ordinal(state.transitions)
    if wait_ordinal < 1:
        wait_ordinal = 1
    route = "WAIT_HUMAN"
    severity = "BLOCKING"
    evidence_refs: list[str] = []
    if state.exceptions is not None:
        for item in state.exceptions.exceptions:
            if item.exception_code == reason:
                route = item.route
                severity = item.severity
            if item.exception_id:
                evidence_refs.append(str(item.exception_id))
    summary = build_scope_summary(state.scope)
    project = summary.project_code
    return build_human_decision_request(
        run_id=state.run_id,
        mission_id=state.mission_id,
        reason_code=reason,
        route=route,
        severity=severity,
        human_readable_reason=state.terminal_reason or reason,
        wait_ordinal=wait_ordinal,
        current_scope_summary=summary,
        evidence_refs=evidence_refs,
        authorization_id_ref=state.authorization_id,
        project_code=project,
        created_at=created_at or state.updated_at,
        interrupt_id=compute_eos_interrupt_id(
            run_id=state.run_id,
            wait_ordinal=wait_ordinal,
            reason_code=reason,
        ),
    )


def _as_scope_tuple(value: Any) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    raise HitlContractError(
        CODE_HITL_CONTRACT_BLOCKER,
        "scope dimension must be str, list, tuple, or None",
    )


def _is_scope_narrowing_or_equal(
    old: Optional[tuple[str, ...]],
    new: Optional[tuple[str, ...]],
) -> bool:
    """
    None means ALL (widest within project+month).
    Narrowing: ALL → specific, or specific → strict subset / equal.
    Widening (specific → ALL, or adding values) is rejected.
    """
    if old is None:
        return True
    if new is None:
        return False
    return set(new).issubset(set(old))


def _validate_authorization(
    state: ConstructorLifecycleState,
    context: AgentExecutionContext,
    *,
    project_code: str,
) -> None:
    if context is None or not isinstance(context, AgentExecutionContext):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext is required for resume",
        )
    if context.is_expired():
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext expired; revalidation required",
        )
    if context.write_allowed:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "resume requires read-only AgentExecutionContext",
        )
    if str(context.project_code).strip() != str(project_code).strip():
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "authorization project_code mismatch",
        )
    if state.authorization_id and context.authorization_id:
        # Reissue is allowed; mismatch alone is not fatal. Project/run binding is.
        pass
    if context.run_id and state.run_id and str(context.run_id) != str(state.run_id):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "authorization run_id mismatch",
        )


def _resolve_baseline_project_month(
    state: ConstructorLifecycleState,
    *,
    project_code: Any,
    month_key: Any,
    parameters: dict[str, Any],
) -> tuple[str, str]:
    if state.scope is not None:
        base_project = state.scope.project_code
        base_month = state.scope.month_key
    else:
        if project_code is None or month_key is None:
            raise HitlContractError(
                CODE_HITL_CONTRACT_BLOCKER,
                "trusted project_code and month_key required when scope is unbound",
            )
        base_project = str(project_code).strip()
        base_month = str(month_key).strip()

    if "project_code" in parameters and str(parameters["project_code"]).strip() != base_project:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "project_code is immutable within a run",
        )
    if "month_key" in parameters and str(parameters["month_key"]).strip() != base_month:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "month_key is immutable within a run",
        )
    return base_project, base_month


def _apply_clarify_scope(
    state: ConstructorLifecycleState,
    command: ConstructorResumeCommand,
    *,
    project_code: Any,
    month_key: Any,
) -> ConstructorMissionScope:
    params = dict(command.parameters)
    base_project, base_month = _resolve_baseline_project_month(
        state,
        project_code=project_code,
        month_key=month_key,
        parameters=params,
    )

    proposed: dict[str, Any] = {}
    for dim in _SCOPE_DIMS:
        if dim in params:
            proposed[dim] = params[dim]
        elif state.scope is not None:
            proposed[dim] = getattr(state.scope, dim)
        else:
            proposed[dim] = None

    if state.scope is not None:
        for dim in _SCOPE_DIMS:
            old = getattr(state.scope, dim)
            new = _as_scope_tuple(proposed[dim]) if proposed[dim] is not None else None
            # Normalize list params to tuples for comparison after mission_scope build;
            # pre-check with raw conversion:
            raw_new = proposed[dim]
            if raw_new is None:
                new_cmp: Optional[tuple[str, ...]] = None
            else:
                new_cmp = _as_scope_tuple(raw_new)
            if not _is_scope_narrowing_or_equal(old, new_cmp):
                raise HitlContractError(
                    CODE_HITL_CONTRACT_BLOCKER,
                    f"scope expansion rejected for {dim}",
                )

    try:
        return build_constructor_mission_scope(
            project_code=base_project,
            month_key=base_month,
            facility_scope=proposed["facility_scope"],
            discipline_scope=proposed["discipline_scope"],
            system_scope=proposed["system_scope"],
            iwp_scope=proposed["iwp_scope"],
            queue_scope=proposed["queue_scope"],
        )
    except MissionScopeError as exc:
        raise HitlContractError(
            getattr(exc, "code", CODE_HITL_CONTRACT_BLOCKER),
            str(exc),
        ) from exc


def apply_constructor_resume_command(
    state: ConstructorLifecycleState,
    command: Any,
    *,
    context: AgentExecutionContext,
    project_code: Any,
    month_key: Any,
    checkpoint_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    """
    Apply validated human resume command.

    Returns REVALIDATING_REALITY (clarify) or FAILED (abort).
    Does not perform secure read / package / labor.
    """
    if state is None or not isinstance(state, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "ConstructorLifecycleState is required",
        )
    if state.status != STATUS_WAITING_FOR_HUMAN:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"resume requires WAITING_FOR_HUMAN, got {state.status}",
        )

    resume = coerce_resume_command(command)
    stamp = _require_aware_utc(now or _utc_now(), "now")

    if resume.run_id != state.run_id:
        raise HitlContractError(CODE_HITL_CONTRACT_BLOCKER, "run_id mismatch")
    if resume.mission_id != state.mission_id:
        raise HitlContractError(CODE_HITL_CONTRACT_BLOCKER, "mission_id mismatch")

    expected_request = build_decision_request_from_lifecycle(state, created_at=stamp)
    if resume.interrupt_id != expected_request.interrupt_id:
        raise HitlContractError(CODE_HITL_CONTRACT_BLOCKER, "interrupt_id mismatch")

    if resume.expected_checkpoint_id is not None:
        if checkpoint_id is None:
            raise HitlContractError(
                CODE_HITL_CONTRACT_BLOCKER,
                "expected_checkpoint_id provided but checkpoint_id unavailable",
            )
        if resume.expected_checkpoint_id != checkpoint_id:
            raise HitlContractError(
                CODE_HITL_CONTRACT_BLOCKER,
                "expected_checkpoint_id mismatch",
            )

    reason = (state.error_code or "").strip().upper()
    allowed = allowed_decisions_for_reason(reason)
    if resume.decision not in allowed:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"decision {resume.decision} not allowed for reason {reason}",
        )

    # Authorization project baseline: scope if present else trusted project_code.
    if state.scope is not None:
        auth_project = state.scope.project_code
    else:
        if project_code is None:
            raise HitlContractError(
                CODE_HITL_CONTRACT_BLOCKER,
                "project_code required for authorization revalidation",
            )
        auth_project = str(project_code).strip()
    _validate_authorization(state, context, project_code=auth_project)

    applying = _append_transition(
        state,
        to_status=STATUS_APPLYING_HUMAN_DECISION,
        at=stamp,
        trigger_code=resume.decision,
        source_capability=SOURCE_HITL_RESUME,
        note=f"human decision {resume.decision_id}",
        authorization_id=context.authorization_id,
    )

    if resume.decision == DECISION_ABORT_RUN:
        return _append_transition(
            applying,
            to_status=STATUS_FAILED,
            at=stamp,
            trigger_code=CODE_RUN_ABORTED_BY_HUMAN,
            source_capability=SOURCE_HITL_RESUME,
            note=resume.comment or "aborted by human",
            error_code=CODE_RUN_ABORTED_BY_HUMAN,
            terminal_reason=resume.comment or "run aborted by human",
            # Preserve WAIT exceptions for audit; clear current reality-derived truth.
            reality_read=None,
            package=None,
            labor_resolutions=None,
        )

    if resume.decision != DECISION_CLARIFY_SCOPE:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"unsupported decision {resume.decision}",
        )

    new_scope = _apply_clarify_scope(
        state,
        resume,
        project_code=project_code,
        month_key=month_key,
    )

    return _append_transition(
        applying,
        to_status=STATUS_REVALIDATING_REALITY,
        at=stamp,
        trigger_code=resume.decision,
        source_capability=SOURCE_HITL_RESUME,
        note="stale reality invalidated; awaiting fresh secure read",
        scope=new_scope,
        reality_read=None,
        package=None,
        labor_resolutions=None,
        error_code=None,
        terminal_reason=None,
        # Keep exceptions as WAIT audit evidence.
        exceptions=state.exceptions,
        authorization_id=context.authorization_id,
    )


def revalidate_constructor_resume_reality(
    state: ConstructorLifecycleState,
    *,
    context: AgentExecutionContext,
    scope_reader: Optional[ScopeReader] = None,
    now: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    """
    Resume-specific fresh secure read.

    Requires REVALIDATING_REALITY. Does not build package/labor/acceptance.
    """
    if state is None or not isinstance(state, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "ConstructorLifecycleState is required",
        )
    if state.status != STATUS_REVALIDATING_REALITY:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"revalidate requires REVALIDATING_REALITY, got {state.status}",
        )
    if state.scope is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "scope required for revalidation",
        )
    if state.reality_read is not None or state.package is not None or state.labor_resolutions is not None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "stale reality-derived artifacts must be invalidated before revalidation",
        )

    _validate_authorization(state, context, project_code=state.scope.project_code)
    stamp = _require_aware_utc(now or _utc_now(), "now")

    try:
        reality = read_constructor_reality(
            context,
            state.scope,
            scope_reader=scope_reader,
        )
    except SecureReadError as exc:
        return _map_domain_failure(state, exc, at=stamp)
    except MissionScopeError as exc:
        return _map_domain_failure(state, exc, at=stamp)

    return _append_transition(
        state,
        to_status=STATUS_REALITY_LOADED,
        at=stamp,
        source_capability=SOURCE_SECURE_READ,
        note="fresh reality loaded after human resume",
        reality_read=reality,
        authorization_id=context.authorization_id,
    )


def stale_artifacts_cleared(state: ConstructorLifecycleState) -> bool:
    """Predicate for tests / guards: no current reality-derived truth after invalidate."""
    return (
        state.reality_read is None
        and state.package is None
        and state.labor_resolutions is None
    )
