"""
Increment 10.6 — immutable Control Room read-model DTOs.

Agent-neutral. EOS-SEC allowlisted fields only. No raw ObservabilityEvent exposure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class DerivationState(str, Enum):
    OK = "OK"
    INCONSISTENT = "INCONSISTENT"
    INCOMPLETE = "INCOMPLETE"


class StageDisplayState(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class HandoffStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    CREATED = "CREATED"
    PERSISTED = "PERSISTED"
    PERSIST_FAILED = "PERSIST_FAILED"


class WaitClosedBy(str, Enum):
    RESUMED = "RESUMED"
    ABORTED = "ABORTED"


class ProfessionalExecutionStepKind(str, Enum):
    STAGE = "STAGE"
    HUMAN_DECISION = "HUMAN_DECISION"
    REALITY_REFRESH = "REALITY_REFRESH"
    HANDOFF_MARKER = "HANDOFF_MARKER"


class ProfessionalExecutionState(str, Enum):
    COMPLETED = "COMPLETED"
    RUNNING = "RUNNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"
    INCONSISTENT = "INCONSISTENT"


class ToolExecutionStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    DENIED = "DENIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AgentRunSummary:
    run_id: str
    agent_code: str
    project_code: str
    month_key: str
    mission_id: str
    operational_status: str
    requested_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    projection_version: int


@dataclass(frozen=True)
class AgentRunDetail(AgentRunSummary):
    request_id: str
    agent_version: str
    orchestration_run_id: Optional[str]
    initiator_type: str
    initiator_id: str
    trigger_type: str
    trigger_reason: str
    attempt_n: int
    resume_n: int
    lifecycle_status: Optional[str]
    interrupt_id: Optional[str]
    decision_id: Optional[str]
    handoff_id: Optional[str]
    error_code: Optional[str]
    safe_error_summary: Optional[str]
    safe_summary: tuple[tuple[str, Any], ...]
    safe_counts: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class AgentRunListView:
    items: tuple[AgentRunSummary, ...]
    runs_complete: bool
    source_count: int


@dataclass(frozen=True)
class AgentEventView:
    event_id: str
    event_type: str
    family: str
    status: str
    title: str
    occurred_at: datetime
    stage_id: Optional[str]
    node_name: Optional[str]
    attempt_n: int
    resume_n: int
    interrupt_id: Optional[str]
    decision_id: Optional[str]
    handoff_id: Optional[str]
    artifact_type: Optional[str]
    artifact_id: Optional[str]
    tool_name: Optional[str]


@dataclass(frozen=True)
class AgentStageOccurrenceView:
    stage_id: str
    node_name: str
    attempt_n: int
    resume_n: int
    artifact_id: str
    display_state: StageDisplayState
    started_at: datetime
    completed_at: Optional[datetime]
    started_event_id: str
    terminal_event_id: Optional[str]


@dataclass(frozen=True)
class AgentStageView:
    current_stage: Optional[AgentStageOccurrenceView]
    occurrences: tuple[AgentStageOccurrenceView, ...]
    derivation_state: DerivationState


@dataclass(frozen=True)
class AgentHumanWaitView:
    waiting_for_human: bool
    interrupt_id: Optional[str]
    wait_started_at: Optional[datetime]
    decision_id: Optional[str]
    wait_closed_by: Optional[WaitClosedBy]
    wait_ordinal: Optional[int]
    derivation_state: DerivationState


@dataclass(frozen=True)
class HumanDecisionRequestView:
    interrupt_id: str
    wait_ordinal: int
    stage_id: str
    reason_code: str
    human_readable_reason: Optional[str]
    allowed_decisions: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    derivation_state: DerivationState


@dataclass(frozen=True)
class HumanDecisionRecordView:
    decision_id: str
    interrupt_id: str
    wait_ordinal: int
    decision_code: str
    actor_id: str
    actor_type: str
    received_at: datetime
    derivation_state: DerivationState


@dataclass(frozen=True)
class HumanDecisionConsequenceView:
    decision_received_at: Optional[datetime]
    closed_by: Optional[WaitClosedBy]
    closed_at: Optional[datetime]
    reality_refresh_started_at: Optional[datetime]
    reality_refresh_completed_at: Optional[datetime]
    reality_refresh_failed_at: Optional[datetime]
    next_stage_id: Optional[str]
    next_stage_started_at: Optional[datetime]
    terminal_event_type: Optional[str]
    derivation_state: DerivationState


@dataclass(frozen=True)
class AgentHumanDecisionSurfaceView:
    wait: AgentHumanWaitView
    request: Optional[HumanDecisionRequestView]
    decision: Optional[HumanDecisionRecordView]
    consequence: Optional[HumanDecisionConsequenceView]
    authority_modeled: bool


@dataclass(frozen=True)
class AgentHandoffView:
    handoff_id: Optional[str]
    status: HandoffStatus
    created_at: Optional[datetime]
    persisted_at: Optional[datetime]
    failed_at: Optional[datetime]
    handoff_type: Optional[str]
    target_role_code: Optional[str]
    artifact_type: Optional[str]
    artifact_id: Optional[str]
    derivation_state: DerivationState


@dataclass(frozen=True)
class StageToolExecutionView:
    tool_name: str
    status: ToolExecutionStatus
    stage_id: str
    attempt_n: int
    resume_n: int
    started_at: datetime
    completed_at: Optional[datetime]


@dataclass(frozen=True)
class StageArtifactView:
    artifact_type: str
    artifact_id: str
    stage_id: str
    resume_n: int
    created_at: datetime


@dataclass(frozen=True)
class RealityRefreshStepView:
    stage_id: str
    resume_n: int
    started_at: datetime
    completed_at: Optional[datetime]
    failed_at: Optional[datetime]
    derivation_state: DerivationState


@dataclass(frozen=True)
class ProfessionalExecutionStepView:
    step_kind: ProfessionalExecutionStepKind
    step_id: str
    stage_id: Optional[str]
    professional_state: ProfessionalExecutionState
    started_at: datetime
    completed_at: Optional[datetime]
    attempt_n: int
    resume_n: int
    derivation_state: DerivationState
    tools: tuple[StageToolExecutionView, ...]
    artifacts: tuple[StageArtifactView, ...]
    human_decision: Optional[AgentHumanDecisionSurfaceView]
    reality_refresh: Optional[RealityRefreshStepView]
    handoff_id: Optional[str]


@dataclass(frozen=True)
class AgentProfessionalExecutionPathView:
    steps: tuple[ProfessionalExecutionStepView, ...]
    derivation_state: DerivationState
    history_complete: bool


@dataclass(frozen=True)
class DigitalOrganizationExecutionView:
    """Source-side professional work transfer view for Digital Organization Level 1.

    Does not claim receiver acceptance, target run existence, ownership transfer,
    handoff authority, or orchestration completion.
    """

    source_agent_code: str
    source_run_id: str
    source_operational_status: str
    source_completed_at: Optional[datetime]
    handoff: Optional[AgentHandoffView]
    history_complete: bool
    derivation_state: DerivationState


@dataclass(frozen=True)
class AgentRunSnapshot:
    run: AgentRunDetail
    stage: AgentStageView
    human_wait: AgentHumanWaitView
    human_decision_surface: AgentHumanDecisionSurfaceView
    handoff: AgentHandoffView
    professional_execution_path: AgentProfessionalExecutionPathView
    digital_organization: DigitalOrganizationExecutionView
    timeline_events: tuple[AgentEventView, ...]
    events_complete: bool
    read_at: datetime


class ProfessionalResultAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INCONSISTENT = "INCONSISTENT"


@dataclass(frozen=True)
class ConstructorCandidateResultView:
    """One Constructor candidate as stored. Quantities are transcribed text, not a new unit law."""

    candidate_id: str
    boq_code: str
    name: str
    unit: str
    remaining_qty: str
    already_planned_qty: str
    available_qty: str
    labor_status: str
    recommendation: str
    exception_codes: tuple[str, ...]
    human_review_decision: str
    final_disposition: str
    final_reason_code: str


@dataclass(frozen=True)
class ConstructorProfessionalResultView:
    """Read-only Constructor professional result. Missing state is UNAVAILABLE, not invented."""

    availability: ProfessionalResultAvailability
    run_id: str
    mission_id: str
    professional_status: str
    project_id: str
    month: str
    facility_id: str
    discipline: str
    source_candidate_package_id: str
    reviewed_package_id: str
    included_count: Optional[int]
    excluded_count: Optional[int]
    unresolved_count: Optional[int]
    confirm_event_id: str
    confirm_decision: str
    confirm_actor_type: str
    confirm_actor_id: str
    path_statuses: tuple[str, ...]
    candidates: tuple[ConstructorCandidateResultView, ...]
    mission_scope_row_count: Optional[int] = None
    mission_scope_source: str = ""
    scanned_count: Optional[int] = None
    excluded_completed_count: Optional[int] = None
    excluded_no_remainder_count: Optional[int] = None
    already_planned_count: Optional[int] = None
    package_candidate_count: Optional[int] = None


def _empty_constructor_professional_result(
    availability: ProfessionalResultAvailability,
) -> ConstructorProfessionalResultView:
    return ConstructorProfessionalResultView(
        availability=availability,
        run_id="",
        mission_id="",
        professional_status="",
        project_id="",
        month="",
        facility_id="",
        discipline="",
        source_candidate_package_id="",
        reviewed_package_id="",
        included_count=None,
        excluded_count=None,
        unresolved_count=None,
        confirm_event_id="",
        confirm_decision="",
        confirm_actor_type="",
        confirm_actor_id="",
        path_statuses=(),
        candidates=(),
    )


def unavailable_constructor_professional_result() -> ConstructorProfessionalResultView:
    return _empty_constructor_professional_result(ProfessionalResultAvailability.UNAVAILABLE)


def inconsistent_constructor_professional_result() -> ConstructorProfessionalResultView:
    return _empty_constructor_professional_result(ProfessionalResultAvailability.INCONSISTENT)


@dataclass(frozen=True)
class ConstructorRowDecisionView:
    """One stored Constructor row decision. Unknown quantities stay None."""

    source_identity: str
    source_order: int
    boq_code: str
    name: str
    unit: str
    system: Optional[str]
    remaining_qty: Optional[str]
    already_planned_qty: Optional[str]
    available_qty: Optional[str]
    outcome: str
    reason_code: str
    reason_text: str
    requires_human: Optional[bool]
    candidate_created: bool
    candidate_id: str
    facility: str = ""
    discipline: str = ""
    iwp: str = ""


@dataclass(frozen=True)
class ConstructorDecisionRegistryView:
    """Read-only row-decision registry for one Constructor run."""

    availability: ProfessionalResultAvailability
    professional: ConstructorProfessionalResultView
    total_count: int
    outcome_counts: tuple[tuple[str, int], ...]
    known_systems: tuple[str, ...]
    attention_count: int
    records: tuple[ConstructorRowDecisionView, ...]
    selected: Optional[ConstructorRowDecisionView] = None


def constructor_row_awaits_human_review(
    record: ConstructorRowDecisionView,
    professional: ConstructorProfessionalResultView,
) -> bool:
    """Use the later professional candidate state, not requires_human alone."""
    if str(professional.professional_status or "").strip() != "WAITING_FOR_HUMAN_REVIEW":
        return False
    if record.outcome != "CANDIDATE" or not record.candidate_created:
        return False
    matched: Optional[ConstructorCandidateResultView] = None
    for candidate in professional.candidates:
        if record.candidate_id and candidate.candidate_id == record.candidate_id:
            matched = candidate
            break
        if candidate.boq_code == record.boq_code:
            matched = candidate
    if matched is None:
        return True
    return not str(matched.human_review_decision or "").strip()


def empty_constructor_decision_registry(
    professional: ConstructorProfessionalResultView,
) -> ConstructorDecisionRegistryView:
    return ConstructorDecisionRegistryView(
        availability=professional.availability,
        professional=professional,
        total_count=0,
        outcome_counts=(),
        known_systems=(),
        attention_count=0,
        records=(),
        selected=None,
    )
