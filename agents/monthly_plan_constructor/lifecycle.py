"""
Constructor Runtime v0.1 Increment 6–8 — Pure Python Lifecycle.

Deterministic coordination of Increments 1–5 for ONE Constructor mission run.
Not a separate agent. Not Streamlit. Not handoff.
Increment 7 adds one-stage advance for LangGraph orchestration (business logic stays here).
Increment 8 adds resume-only statuses; NORMAL ADVANCE != HUMAN RESUME.

Does not reimplement scope/read/package/labor/exception business logic.
Does not invent physical remainder / candidate classification (injected port).
Does not catch broad Exception for business routing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, Sequence, Union

from agents.monthly_plan_constructor.candidate_package import (
    CandidateInput,
    CandidatePackage,
    CandidatePackageError,
    build_candidate_package,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_ENGINE_CONTRACT_BLOCKER,
    ROUTE_FAIL_RUN,
    ROUTE_WAIT_HUMAN,
    SEVERITY_BLOCKING,
    SOURCE_CANDIDATE_PACKAGE,
    SOURCE_LABOR_NORM,
    SOURCE_MISSION_SCOPE,
    SOURCE_SECURE_READ,
    ConstructorExceptionSet,
    ExceptionEngineError,
    build_exception_set,
    exception_from_failure,
    exceptions_from_labor_resolutions,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    LaborNormEvidence,
    LaborNormResolutionSet,
    LaborNormResolverError,
    resolve_labor_norms,
)
from agents.monthly_plan_constructor.mission_scope import (
    ConstructorMissionScope,
    MissionScopeError,
    ScopeValue,
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    ConstructorRealityRead,
    ScopeReader,
    SecureReadError,
    read_constructor_reality,
)
from security.agent_execution_context import AgentExecutionContext

SCHEMA_VERSION = "1.0"

STATUS_CREATED = "CREATED"
STATUS_MISSION_BOUND = "MISSION_BOUND"
STATUS_REALITY_LOADED = "REALITY_LOADED"
STATUS_PACKAGE_BUILT = "PACKAGE_BUILT"
STATUS_LABOR_RESOLVED = "LABOR_RESOLVED"
STATUS_READY_FOR_HANDOFF = "READY_FOR_HANDOFF"
STATUS_WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
STATUS_FAILED = "FAILED"
STATUS_APPLYING_HUMAN_DECISION = "APPLYING_HUMAN_DECISION"
STATUS_REVALIDATING_REALITY = "REVALIDATING_REALITY"

COMPLETION_STATUSES = frozenset(
    {
        STATUS_READY_FOR_HANDOFF,
        STATUS_FAILED,
    }
)

PAUSE_STATUSES = frozenset(
    {
        STATUS_WAITING_FOR_HUMAN,
    }
)

INVOCATION_STOP_STATUSES = frozenset(
    {
        STATUS_READY_FOR_HANDOFF,
        STATUS_WAITING_FOR_HUMAN,
        STATUS_FAILED,
    }
)

# Backward-compatible alias: sync invocation stop set (Inc 6–7 TERMINAL semantics).
TERMINAL_STATUSES = INVOCATION_STOP_STATUSES

RESUME_ONLY_STATUSES = frozenset(
    {
        STATUS_APPLYING_HUMAN_DECISION,
        STATUS_REVALIDATING_REALITY,
    }
)

ACTIVE_STATUSES = frozenset(
    {
        STATUS_CREATED,
        STATUS_MISSION_BOUND,
        STATUS_REALITY_LOADED,
        STATUS_PACKAGE_BUILT,
        STATUS_LABOR_RESOLVED,
        STATUS_READY_FOR_HANDOFF,
        STATUS_WAITING_FOR_HUMAN,
        STATUS_FAILED,
        STATUS_APPLYING_HUMAN_DECISION,
        STATUS_REVALIDATING_REALITY,
    }
)

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_CREATED: frozenset(
        {STATUS_MISSION_BOUND, STATUS_WAITING_FOR_HUMAN, STATUS_FAILED}
    ),
    STATUS_MISSION_BOUND: frozenset(
        {STATUS_REALITY_LOADED, STATUS_WAITING_FOR_HUMAN, STATUS_FAILED}
    ),
    STATUS_REALITY_LOADED: frozenset(
        {STATUS_PACKAGE_BUILT, STATUS_WAITING_FOR_HUMAN, STATUS_FAILED}
    ),
    STATUS_PACKAGE_BUILT: frozenset(
        {STATUS_LABOR_RESOLVED, STATUS_WAITING_FOR_HUMAN, STATUS_FAILED}
    ),
    STATUS_LABOR_RESOLVED: frozenset(
        {
            STATUS_READY_FOR_HANDOFF,
            STATUS_WAITING_FOR_HUMAN,
            STATUS_FAILED,
        }
    ),
    STATUS_READY_FOR_HANDOFF: frozenset(),
    # Resume path only — normal advance must still refuse WAIT.
    STATUS_WAITING_FOR_HUMAN: frozenset({STATUS_APPLYING_HUMAN_DECISION}),
    STATUS_APPLYING_HUMAN_DECISION: frozenset(
        {STATUS_REVALIDATING_REALITY, STATUS_FAILED}
    ),
    STATUS_REVALIDATING_REALITY: frozenset(
        {
            STATUS_REALITY_LOADED,
            STATUS_WAITING_FOR_HUMAN,
            STATUS_FAILED,
        }
    ),
    STATUS_FAILED: frozenset(),
}

CODE_LIFECYCLE_CONTRACT_BLOCKER = "LIFECYCLE_CONTRACT_BLOCKER"

SOURCE_LIFECYCLE = "LIFECYCLE"


class LifecycleError(ValueError):
    """Fail-closed Pure Python Lifecycle contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class LifecycleTransition:
    from_status: str
    to_status: str
    at: datetime
    trigger_code: Optional[str] = None
    source_capability: Optional[str] = None
    note: Optional[str] = None


@dataclass(frozen=True)
class ConstructorLifecycleState:
    run_id: str
    schema_version: str
    status: str
    mission_id: str
    created_at: datetime
    updated_at: datetime
    transitions: tuple[LifecycleTransition, ...] = ()
    scope: Optional[ConstructorMissionScope] = None
    authorization_id: Optional[str] = None
    reality_read: Optional[ConstructorRealityRead] = None
    package: Optional[CandidatePackage] = None
    labor_resolutions: Optional[LaborNormResolutionSet] = None
    exceptions: Optional[ConstructorExceptionSet] = None
    terminal_reason: Optional[str] = None
    error_code: Optional[str] = None


@dataclass(frozen=True)
class CandidateAssemblyResult:
    """Minimum structured input for build_candidate_package. Not a classifier."""

    candidates: tuple[CandidateInput, ...]
    scanned_count: int
    excluded_completed_count: int = 0
    excluded_no_remainder_count: int = 0
    already_planned_count: int = 0


class CandidateAssembler(Protocol):
    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        ...


LaborEvidenceInput = Union[
    Sequence[LaborNormEvidence],
    Callable[[CandidatePackage, ConstructorLifecycleState], Sequence[LaborNormEvidence]],
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"{field_name} must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"{field_name} must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _require_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    return text


def _source_for_error(exc: BaseException) -> str:
    if isinstance(exc, MissionScopeError):
        return SOURCE_MISSION_SCOPE
    if isinstance(exc, SecureReadError):
        return SOURCE_SECURE_READ
    if isinstance(exc, CandidatePackageError):
        return SOURCE_CANDIDATE_PACKAGE
    if isinstance(exc, LaborNormResolverError):
        return SOURCE_LABOR_NORM
    return SOURCE_LIFECYCLE


def _assert_status_invariants(state: ConstructorLifecycleState) -> None:
    status = state.status
    if status not in ACTIVE_STATUSES:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"unknown status {status}",
        )
    if state.updated_at < state.created_at:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "updated_at must not precede created_at",
        )
    if status == STATUS_CREATED:
        return
    if status in {
        STATUS_MISSION_BOUND,
        STATUS_REALITY_LOADED,
        STATUS_PACKAGE_BUILT,
        STATUS_LABOR_RESOLVED,
        STATUS_READY_FOR_HANDOFF,
        STATUS_REVALIDATING_REALITY,
    }:
        if state.scope is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                f"scope required for status {status}",
            )
    if status == STATUS_REVALIDATING_REALITY:
        # After resume invalidate: no current reality-derived truth.
        if (
            state.reality_read is not None
            or state.package is not None
            or state.labor_resolutions is not None
        ):
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "REVALIDATING_REALITY must not carry stale reality-derived artifacts",
            )
        return
    if status in {
        STATUS_REALITY_LOADED,
        STATUS_PACKAGE_BUILT,
        STATUS_LABOR_RESOLVED,
        STATUS_READY_FOR_HANDOFF,
    }:
        if state.reality_read is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                f"reality_read required for status {status}",
            )
    if status in {
        STATUS_PACKAGE_BUILT,
        STATUS_LABOR_RESOLVED,
        STATUS_READY_FOR_HANDOFF,
    }:
        if state.package is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                f"package required for status {status}",
            )
    if status in {STATUS_LABOR_RESOLVED, STATUS_READY_FOR_HANDOFF}:
        if state.labor_resolutions is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                f"labor_resolutions required for status {status}",
            )
    if status == STATUS_READY_FOR_HANDOFF:
        if state.exceptions is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "exceptions required for READY_FOR_HANDOFF",
            )


def is_ready_for_handoff(state: ConstructorLifecycleState) -> bool:
    """Deterministic readiness predicate — not status-string alone."""
    if state.scope is None:
        return False
    if state.reality_read is None:
        return False
    if state.package is None:
        return False
    if state.labor_resolutions is None:
        return False
    if state.exceptions is None:
        return False
    if len(state.labor_resolutions.resolutions) != state.package.candidate_count:
        return False
    if state.labor_resolutions.package_id != state.package.package_id:
        return False
    if any(item.severity == SEVERITY_BLOCKING for item in state.exceptions.exceptions):
        return False
    if not state.exceptions.handoff_allowed():
        return False
    return True


def _append_transition(
    state: ConstructorLifecycleState,
    *,
    to_status: str,
    at: datetime,
    trigger_code: Optional[str] = None,
    source_capability: Optional[str] = None,
    note: Optional[str] = None,
    **updates: Any,
) -> ConstructorLifecycleState:
    from_status = state.status
    allowed = _ALLOWED_TRANSITIONS.get(from_status, frozenset())
    if to_status not in allowed:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"prohibited transition {from_status} → {to_status}",
        )
    stamp = _require_aware_utc(at, "transition.at")
    if stamp < state.created_at:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "transition timestamp precedes created_at",
        )
    transition = LifecycleTransition(
        from_status=from_status,
        to_status=to_status,
        at=stamp,
        trigger_code=_optional_text(trigger_code),
        source_capability=_optional_text(source_capability),
        note=_optional_text(note),
    )
    new_updated = stamp if stamp >= state.updated_at else state.updated_at
    prior_transitions = tuple(state.transitions)
    new_state = replace(
        state,
        status=to_status,
        updated_at=new_updated,
        transitions=prior_transitions + (transition,),
        **updates,
    )
    _assert_status_invariants(new_state)
    return new_state


def create_lifecycle_state(
    *,
    mission_id: str,
    run_id: Optional[str] = None,
    authorization_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    stamp = _require_aware_utc(created_at or _utc_now(), "created_at")
    state = ConstructorLifecycleState(
        run_id=_optional_text(run_id) or str(uuid.uuid4()),
        schema_version=SCHEMA_VERSION,
        status=STATUS_CREATED,
        mission_id=_require_text(mission_id, "mission_id"),
        created_at=stamp,
        updated_at=stamp,
        authorization_id=_optional_text(authorization_id),
        transitions=(),
    )
    _assert_status_invariants(state)
    return state


def _map_domain_failure(
    state: ConstructorLifecycleState,
    exc: Union[
        MissionScopeError,
        CandidatePackageError,
        SecureReadError,
        LaborNormResolverError,
    ],
    *,
    at: datetime,
) -> ConstructorLifecycleState:
    code = getattr(exc, "code", None)
    if not code:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "domain error missing machine code",
        )
    source = _source_for_error(exc)
    package_id = state.package.package_id if state.package is not None else None
    try:
        mapped = exception_from_failure(
            str(code),
            source_capability=source,
            reason=str(exc),
            package_id=package_id,
            observed_at=at,
        )
        exc_set = build_exception_set([mapped], package_id=package_id)
    except ExceptionEngineError as engine_exc:
        return _fail_engine_contract(state, engine_exc, at=at)

    if mapped.route == ROUTE_WAIT_HUMAN:
        terminal = STATUS_WAITING_FOR_HUMAN
    elif mapped.route == ROUTE_FAIL_RUN or mapped.severity == SEVERITY_BLOCKING:
        terminal = STATUS_FAILED
    else:
        terminal = STATUS_FAILED

    return _append_transition(
        state,
        to_status=terminal,
        at=at,
        trigger_code=mapped.exception_code,
        source_capability=source,
        note="mapped domain failure",
        exceptions=exc_set,
        error_code=mapped.exception_code,
        terminal_reason=str(exc),
    )


def _fail_engine_contract(
    state: ConstructorLifecycleState,
    exc: ExceptionEngineError,
    *,
    at: datetime,
) -> ConstructorLifecycleState:
    code = getattr(exc, "code", None) or CODE_ENGINE_CONTRACT_BLOCKER
    return _append_transition(
        state,
        to_status=STATUS_FAILED,
        at=at,
        trigger_code=str(code),
        source_capability=SOURCE_LIFECYCLE,
        note="exception engine contract failure",
        error_code=str(code),
        terminal_reason=str(exc),
        # do not invent a successful ConstructorExceptionSet
        exceptions=state.exceptions,
    )


def _resolve_evidence(
    evidence: LaborEvidenceInput,
    package: CandidatePackage,
    state: ConstructorLifecycleState,
) -> Sequence[LaborNormEvidence]:
    if callable(evidence) and not isinstance(evidence, (list, tuple)):
        return evidence(package, state)
    return evidence  # type: ignore[return-value]


# Finite professional stages that may advance once each on the happy path.
_MAX_LIFECYCLE_ADVANCES = 5


def advance_constructor_reality_read_step(
    state: ConstructorLifecycleState,
    *,
    context: AgentExecutionContext,
    scope_reader: Optional[ScopeReader] = None,
    at: datetime,
) -> ConstructorLifecycleState:
    """
    Advance MISSION_BOUND by one secure reality read.

    MISSION_BOUND → REALITY_LOADED, or domain-mapped WAITING_FOR_HUMAN / FAILED.
    Single source of truth for initial Constructor reality read (Increment 6/7/10.3C).
    """
    if state is None or not isinstance(state, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "ConstructorLifecycleState is required",
        )
    if context is None or not isinstance(context, AgentExecutionContext):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext is required",
        )
    if state.status != STATUS_MISSION_BOUND:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"reality read step requires MISSION_BOUND, got {state.status}",
        )
    if state.scope is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "scope required for REALITY_LOADED advance",
        )
    stamp = _require_aware_utc(at, "at")
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
        note="trusted reality loaded",
        reality_read=reality,
    )


def advance_constructor_lifecycle(
    state: ConstructorLifecycleState,
    *,
    context: AgentExecutionContext,
    project_code: Any,
    month_key: Any,
    assemble_candidates: CandidateAssembler,
    labor_evidence: LaborEvidenceInput = (),
    facility_scope: ScopeValue = None,
    discipline_scope: ScopeValue = None,
    system_scope: ScopeValue = None,
    iwp_scope: ScopeValue = None,
    queue_scope: ScopeValue = None,
    scope_reader: Optional[ScopeReader] = None,
    now: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    """
    Advance authoritative ConstructorLifecycleState by exactly one professional stage.

    Invocation-stop and resume-only statuses cannot be advanced here.
    HUMAN RESUME uses dedicated hitl_resume helpers — not this function.
    Domain failures may transition directly to WAITING_FOR_HUMAN / FAILED.
    """
    if state is None or not isinstance(state, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "ConstructorLifecycleState is required",
        )
    if context is None or not isinstance(context, AgentExecutionContext):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext is required",
        )
    if assemble_candidates is None or not callable(assemble_candidates):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "assemble_candidates port is required",
        )

    stamp = _require_aware_utc(now or _utc_now(), "now")
    status = state.status

    if status in INVOCATION_STOP_STATUSES:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"cannot advance terminal status {status}",
        )
    if status in RESUME_ONLY_STATUSES:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"cannot advance resume-only status {status}; use dedicated resume path",
        )

    if status == STATUS_CREATED:
        try:
            scope = build_constructor_mission_scope(
                project_code=project_code,
                month_key=month_key,
                facility_scope=facility_scope,
                discipline_scope=discipline_scope,
                system_scope=system_scope,
                iwp_scope=iwp_scope,
                queue_scope=queue_scope,
            )
        except MissionScopeError as exc:
            return _map_domain_failure(state, exc, at=stamp)
        return _append_transition(
            state,
            to_status=STATUS_MISSION_BOUND,
            at=stamp,
            source_capability=SOURCE_MISSION_SCOPE,
            note="mission scope bound",
            scope=scope,
        )

    if status == STATUS_MISSION_BOUND:
        return advance_constructor_reality_read_step(
            state,
            context=context,
            scope_reader=scope_reader,
            at=stamp,
        )

    if status == STATUS_REALITY_LOADED:
        if state.scope is None or state.reality_read is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "scope and reality_read required for PACKAGE_BUILT advance",
            )
        try:
            assembly = assemble_candidates(state.reality_read, state.scope)
            if not isinstance(assembly, CandidateAssemblyResult):
                raise LifecycleError(
                    CODE_LIFECYCLE_CONTRACT_BLOCKER,
                    "assemble_candidates must return CandidateAssemblyResult",
                )
            package = build_candidate_package(
                state.scope,
                assembly.candidates,
                mission_id=state.mission_id,
                scanned_count=assembly.scanned_count,
                excluded_completed_count=assembly.excluded_completed_count,
                excluded_no_remainder_count=assembly.excluded_no_remainder_count,
                already_planned_count=assembly.already_planned_count,
                run_id=state.run_id,
                snapshot_id=state.reality_read.read_id,
            )
        except CandidatePackageError as exc:
            return _map_domain_failure(state, exc, at=stamp)
        except LifecycleError:
            raise
        except MissionScopeError as exc:
            return _map_domain_failure(state, exc, at=stamp)
        return _append_transition(
            state,
            to_status=STATUS_PACKAGE_BUILT,
            at=stamp,
            source_capability=SOURCE_CANDIDATE_PACKAGE,
            note="candidate package built",
            package=package,
        )

    if status == STATUS_PACKAGE_BUILT:
        if state.package is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "package required for LABOR_RESOLVED advance",
            )
        try:
            evidence_items = _resolve_evidence(labor_evidence, state.package, state)
            labor = resolve_labor_norms(state.package, evidence_items)
        except LaborNormResolverError as exc:
            return _map_domain_failure(state, exc, at=stamp)
        return _append_transition(
            state,
            to_status=STATUS_LABOR_RESOLVED,
            at=stamp,
            source_capability=SOURCE_LABOR_NORM,
            note="labor norms resolved",
            package=labor.resolved_package,
            labor_resolutions=labor,
        )

    if status == STATUS_LABOR_RESOLVED:
        if state.labor_resolutions is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "labor_resolutions required for terminal advance",
            )
        labor = state.labor_resolutions
        try:
            exc_set = exceptions_from_labor_resolutions(labor, observed_at=stamp)
        except ExceptionEngineError as exc:
            return _fail_engine_contract(state, exc, at=stamp)

        state = replace(state, exceptions=exc_set, updated_at=stamp)
        if not is_ready_for_handoff(state):
            # Labor path should only produce NON_BLOCKING; if somehow blocking, fail closed.
            blocking = state.exceptions.blocking() if state.exceptions else ()
            if blocking:
                first = blocking[0]
                terminal = (
                    STATUS_WAITING_FOR_HUMAN
                    if first.route == ROUTE_WAIT_HUMAN
                    else STATUS_FAILED
                )
                return _append_transition(
                    state,
                    to_status=terminal,
                    at=stamp,
                    trigger_code=first.exception_code,
                    source_capability=SOURCE_LABOR_NORM,
                    note="blocking exception after labor evaluation",
                    error_code=first.exception_code,
                    terminal_reason=first.reason,
                )
            return _append_transition(
                state,
                to_status=STATUS_FAILED,
                at=stamp,
                trigger_code=CODE_LIFECYCLE_CONTRACT_BLOCKER,
                source_capability=SOURCE_LIFECYCLE,
                note="readiness predicate failed after labor evaluation",
                error_code=CODE_LIFECYCLE_CONTRACT_BLOCKER,
                terminal_reason="readiness predicate failed",
            )

        return _append_transition(
            state,
            to_status=STATUS_READY_FOR_HANDOFF,
            at=stamp,
            source_capability=SOURCE_LIFECYCLE,
            note="ready for future handoff (eligibility only)",
        )

    raise LifecycleError(
        CODE_LIFECYCLE_CONTRACT_BLOCKER,
        f"unknown or non-advancing status {status}",
    )


def run_constructor_lifecycle(
    *,
    context: AgentExecutionContext,
    project_code: Any,
    month_key: Any,
    assemble_candidates: CandidateAssembler,
    labor_evidence: LaborEvidenceInput = (),
    facility_scope: ScopeValue = None,
    discipline_scope: ScopeValue = None,
    system_scope: ScopeValue = None,
    iwp_scope: ScopeValue = None,
    queue_scope: ScopeValue = None,
    mission_id: Optional[str] = None,
    run_id: Optional[str] = None,
    scope_reader: Optional[ScopeReader] = None,
    now: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    """
    Run one Constructor mission lifecycle to a terminal status.

    Injected assemble_candidates must NOT be remainder/classification business logic
    inside this module — tests/production supply the port.
    """
    if context is None or not isinstance(context, AgentExecutionContext):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext is required",
        )
    if assemble_candidates is None or not callable(assemble_candidates):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "assemble_candidates port is required",
        )

    stamp = _require_aware_utc(now or _utc_now(), "now")
    mission = _optional_text(mission_id) or f"mission-{uuid.uuid4()}"
    state = create_lifecycle_state(
        mission_id=mission,
        run_id=run_id or context.run_id,
        authorization_id=context.authorization_id,
        created_at=stamp,
    )

    advances = 0
    while state.status not in TERMINAL_STATUSES:
        if advances >= _MAX_LIFECYCLE_ADVANCES:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "lifecycle advance loop exceeded finite stage budget",
            )
        state = advance_constructor_lifecycle(
            state,
            context=context,
            project_code=project_code,
            month_key=month_key,
            assemble_candidates=assemble_candidates,
            labor_evidence=labor_evidence,
            facility_scope=facility_scope,
            discipline_scope=discipline_scope,
            system_scope=system_scope,
            iwp_scope=iwp_scope,
            queue_scope=queue_scope,
            scope_reader=scope_reader,
            now=stamp,
        )
        advances += 1
    return state

