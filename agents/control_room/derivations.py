"""
Increment 10.6 — pure deterministic Control Room derivations.

No store access. No LLM. No detail-based inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from agents.control_room.dtos import (
    AgentEventView,
    AgentHandoffView,
    AgentHumanDecisionSurfaceView,
    AgentHumanWaitView,
    AgentProfessionalExecutionPathView,
    AgentRunDetail,
    AgentRunSummary,
    AgentStageOccurrenceView,
    AgentStageView,
    DerivationState,
    HandoffStatus,
    HumanDecisionConsequenceView,
    HumanDecisionRecordView,
    HumanDecisionRequestView,
    ProfessionalExecutionState,
    ProfessionalExecutionStepKind,
    ProfessionalExecutionStepView,
    RealityRefreshStepView,
    StageArtifactView,
    StageDisplayState,
    StageToolExecutionView,
    ToolExecutionStatus,
    WaitClosedBy,
)
from agents.observability.contracts import (
    AgentRun,
    EventType,
    ObservabilityEvent,
    OperationalStatus,
)

_STAGE_TERMINAL = frozenset({EventType.STAGE_COMPLETED, EventType.STAGE_FAILED})
_HITL_WAIT_STAGE = "HUMAN_GATE"


def _merge_derivation_state(current: DerivationState, new: DerivationState) -> DerivationState:
    priority = {
        DerivationState.INCONSISTENT: 3,
        DerivationState.INCOMPLETE: 2,
        DerivationState.OK: 1,
    }
    if priority[new] > priority[current]:
        return new
    return current


def agent_run_to_summary(run: AgentRun) -> AgentRunSummary:
    return AgentRunSummary(
        run_id=run.run_id,
        agent_code=run.agent_code,
        project_code=run.project_code,
        month_key=run.month_key,
        mission_id=run.mission_id,
        operational_status=run.operational_status.value,
        requested_at=run.requested_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        projection_version=run.projection_version,
    )


def agent_run_to_detail(run: AgentRun) -> AgentRunDetail:
    summary = agent_run_to_summary(run)
    payload = run.to_dict()
    safe_summary = tuple(sorted((payload.get("safe_summary") or {}).items()))
    safe_counts = tuple(sorted((payload.get("safe_counts") or {}).items()))
    return AgentRunDetail(
        run_id=summary.run_id,
        agent_code=summary.agent_code,
        project_code=summary.project_code,
        month_key=summary.month_key,
        mission_id=summary.mission_id,
        operational_status=summary.operational_status,
        requested_at=summary.requested_at,
        updated_at=summary.updated_at,
        started_at=summary.started_at,
        completed_at=summary.completed_at,
        projection_version=summary.projection_version,
        request_id=run.request_id,
        agent_version=run.agent_version,
        orchestration_run_id=run.orchestration_run_id,
        initiator_type=run.initiator_type.value,
        initiator_id=run.initiator_id,
        trigger_type=run.trigger_type.value,
        trigger_reason=run.trigger_reason,
        attempt_n=run.attempt_n,
        resume_n=run.resume_n,
        lifecycle_status=run.lifecycle_status,
        interrupt_id=run.interrupt_id,
        decision_id=run.decision_id,
        handoff_id=run.handoff_id,
        error_code=run.error_code,
        safe_error_summary=run.safe_error_summary,
        safe_summary=safe_summary,
        safe_counts=safe_counts,
    )


def observability_event_to_view(event: ObservabilityEvent) -> AgentEventView:
    return AgentEventView(
        event_id=event.event_id,
        event_type=event.event_type.value,
        family=event.family.value,
        status=event.status.value,
        title=event.title,
        occurred_at=event.occurred_at,
        stage_id=event.stage_id,
        node_name=event.node_name,
        attempt_n=event.attempt_n,
        resume_n=event.resume_n,
        interrupt_id=event.interrupt_id,
        decision_id=event.decision_id,
        handoff_id=event.handoff_id,
        artifact_type=event.artifact_type,
        artifact_id=event.artifact_id,
        tool_name=event.tool_name,
    )


def build_event_timeline(events: tuple[ObservabilityEvent, ...]) -> tuple[AgentEventView, ...]:
    return tuple(observability_event_to_view(event) for event in events)


def _stage_occurrence_key(event: ObservabilityEvent) -> Optional[tuple[str, str, int, int, str]]:
    if event.stage_id is None or event.node_name is None:
        return None
    return (
        event.stage_id,
        event.node_name,
        event.attempt_n,
        event.resume_n,
        event.artifact_id or "",
    )


@dataclass
class _StageOccurrenceBuilder:
    stage_id: str
    node_name: str
    attempt_n: int
    resume_n: int
    artifact_id: str
    started_at: datetime
    started_event_id: str
    display_state: StageDisplayState = StageDisplayState.RUNNING
    completed_at: Optional[datetime] = None
    terminal_event_id: Optional[str] = None

    def to_view(self) -> AgentStageOccurrenceView:
        return AgentStageOccurrenceView(
            stage_id=self.stage_id,
            node_name=self.node_name,
            attempt_n=self.attempt_n,
            resume_n=self.resume_n,
            artifact_id=self.artifact_id,
            display_state=self.display_state,
            started_at=self.started_at,
            completed_at=self.completed_at,
            started_event_id=self.started_event_id,
            terminal_event_id=self.terminal_event_id,
        )


def derive_stage_view(
    events: tuple[ObservabilityEvent, ...],
    *,
    events_complete: bool,
) -> AgentStageView:
    derivation_state = DerivationState.OK
    open_by_key: dict[tuple[str, str, int, int, str], _StageOccurrenceBuilder] = {}
    ordered_occurrences: list[_StageOccurrenceBuilder] = []

    for event in events:
        if event.event_type not in {EventType.STAGE_STARTED, *_STAGE_TERMINAL}:
            continue
        key = _stage_occurrence_key(event)
        if key is None:
            derivation_state = _merge_derivation_state(
                derivation_state,
                DerivationState.INCONSISTENT,
            )
            continue

        if event.event_type is EventType.STAGE_STARTED:
            if key in open_by_key:
                derivation_state = DerivationState.INCONSISTENT
                continue
            builder = _StageOccurrenceBuilder(
                stage_id=key[0],
                node_name=key[1],
                attempt_n=key[2],
                resume_n=key[3],
                artifact_id=key[4],
                started_at=event.occurred_at,
                started_event_id=event.event_id,
            )
            open_by_key[key] = builder
            ordered_occurrences.append(builder)
            continue

        builder = open_by_key.get(key)
        if builder is None:
            derivation_state = _merge_derivation_state(
                derivation_state,
                DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
            )
            continue
        if builder.terminal_event_id is not None:
            derivation_state = DerivationState.INCONSISTENT
            continue

        if event.event_type is EventType.STAGE_COMPLETED:
            builder.display_state = StageDisplayState.COMPLETED
        else:
            builder.display_state = StageDisplayState.FAILED
        builder.completed_at = event.occurred_at
        builder.terminal_event_id = event.event_id
        del open_by_key[key]

    if not events_complete:
        derivation_state = _merge_derivation_state(derivation_state, DerivationState.INCOMPLETE)

    current_stage = None
    if events_complete:
        for builder in reversed(ordered_occurrences):
            if builder.display_state is StageDisplayState.RUNNING:
                current_stage = builder.to_view()
                break

    return AgentStageView(
        current_stage=current_stage,
        occurrences=tuple(builder.to_view() for builder in ordered_occurrences),
        derivation_state=derivation_state,
    )


@dataclass
class _WaitBuilder:
    stage_id: str
    resume_n: int
    interrupt_id: Optional[str]
    started_at: datetime
    decision_id: Optional[str] = None
    closed_by: Optional[WaitClosedBy] = None


def derive_human_wait_view(
    run: AgentRun,
    events: tuple[ObservabilityEvent, ...],
    *,
    events_complete: bool,
) -> AgentHumanWaitView:
    derivation_state = DerivationState.OK
    waits_by_ordinal: dict[int, _WaitBuilder] = {}

    for event in events:
        if event.event_type is EventType.HUMAN_WAIT_STARTED:
            if event.stage_id is None:
                derivation_state = DerivationState.INCONSISTENT
                continue
            ordinal = event.resume_n
            if ordinal in waits_by_ordinal and waits_by_ordinal[ordinal].closed_by is None:
                derivation_state = DerivationState.INCONSISTENT
            waits_by_ordinal[ordinal] = _WaitBuilder(
                stage_id=event.stage_id,
                resume_n=ordinal,
                interrupt_id=event.interrupt_id,
                started_at=event.occurred_at,
            )
            continue

        if event.event_type is EventType.HUMAN_DECISION_RECEIVED:
            if event.resume_n not in waits_by_ordinal:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
                )
                continue
            if event.decision_id is not None:
                waits_by_ordinal[event.resume_n].decision_id = event.decision_id
            continue

        if event.event_type is EventType.RUN_RESUMED:
            if event.stage_id != _HITL_WAIT_STAGE:
                continue
            builder = waits_by_ordinal.get(event.resume_n)
            if builder is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
                )
                continue
            if builder.closed_by is not None:
                derivation_state = DerivationState.INCONSISTENT
                continue
            builder.closed_by = WaitClosedBy.RESUMED
            if event.decision_id is not None:
                builder.decision_id = event.decision_id
            continue

        if event.event_type is EventType.RUN_ABORTED:
            if event.stage_id != _HITL_WAIT_STAGE:
                continue
            builder = waits_by_ordinal.get(event.resume_n)
            if builder is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
                )
                continue
            if builder.closed_by is not None:
                derivation_state = DerivationState.INCONSISTENT
                continue
            builder.closed_by = WaitClosedBy.ABORTED
            if event.decision_id is not None:
                builder.decision_id = event.decision_id

    if not events_complete:
        derivation_state = _merge_derivation_state(derivation_state, DerivationState.INCOMPLETE)

    waiting_for_human = run.operational_status is OperationalStatus.WAITING_FOR_HUMAN
    interrupt_id: Optional[str] = None
    wait_started_at: Optional[datetime] = None
    decision_id: Optional[str] = None
    wait_closed_by: Optional[WaitClosedBy] = None
    wait_ordinal: Optional[int] = None

    if waiting_for_human:
        interrupt_id = run.interrupt_id
        matched: Optional[_WaitBuilder] = None
        if interrupt_id is not None:
            for builder in waits_by_ordinal.values():
                if builder.interrupt_id == interrupt_id and builder.closed_by is None:
                    matched = builder
                    break
        if matched is None:
            for builder in sorted(waits_by_ordinal.values(), key=lambda item: item.resume_n, reverse=True):
                if builder.closed_by is None:
                    matched = builder
                    break
        if matched is not None:
            wait_started_at = matched.started_at
            wait_ordinal = matched.resume_n
            decision_id = matched.decision_id
        elif not events_complete:
            derivation_state = _merge_derivation_state(derivation_state, DerivationState.INCOMPLETE)
    elif waits_by_ordinal:
        latest = max(waits_by_ordinal.values(), key=lambda item: item.resume_n)
        wait_ordinal = latest.resume_n
        interrupt_id = latest.interrupt_id
        wait_started_at = latest.started_at
        decision_id = latest.decision_id or run.decision_id
        wait_closed_by = latest.closed_by

    return AgentHumanWaitView(
        waiting_for_human=waiting_for_human,
        interrupt_id=interrupt_id,
        wait_started_at=wait_started_at,
        decision_id=decision_id,
        wait_closed_by=wait_closed_by,
        wait_ordinal=wait_ordinal,
        derivation_state=derivation_state,
    )


@dataclass
class _HandoffBuilder:
    handoff_id: str
    status: HandoffStatus = HandoffStatus.CREATED
    created_at: Optional[datetime] = None
    persisted_at: Optional[datetime] = None


def derive_handoff_view(
    run: AgentRun,
    events: tuple[ObservabilityEvent, ...],
    *,
    events_complete: bool,
) -> AgentHandoffView:
    derivation_state = DerivationState.OK
    by_id: dict[str, _HandoffBuilder] = {}

    for event in events:
        if event.handoff_id is None:
            continue
        if event.event_type is EventType.HANDOFF_CREATED:
            if event.handoff_id in by_id:
                derivation_state = DerivationState.INCONSISTENT
            by_id[event.handoff_id] = _HandoffBuilder(
                handoff_id=event.handoff_id,
                status=HandoffStatus.CREATED,
                created_at=event.occurred_at,
            )
            continue
        if event.event_type is EventType.HANDOFF_PERSISTED:
            builder = by_id.get(event.handoff_id)
            if builder is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
                )
                continue
            if builder.status is HandoffStatus.PERSIST_FAILED:
                derivation_state = DerivationState.INCONSISTENT
                continue
            builder.status = HandoffStatus.PERSISTED
            builder.persisted_at = event.occurred_at
            continue
        if event.event_type is EventType.HANDOFF_PERSIST_FAILED:
            builder = by_id.get(event.handoff_id)
            if builder is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
                )
                continue
            if builder.status is HandoffStatus.PERSISTED:
                derivation_state = DerivationState.INCONSISTENT
                continue
            builder.status = HandoffStatus.PERSIST_FAILED

    if not events_complete:
        derivation_state = _merge_derivation_state(derivation_state, DerivationState.INCOMPLETE)

    selected_id = run.handoff_id
    if selected_id is None and by_id:
        selected_id = sorted(by_id.keys())[-1]

    if selected_id is None:
        return AgentHandoffView(
            handoff_id=None,
            status=HandoffStatus.NOT_STARTED,
            created_at=None,
            persisted_at=None,
            derivation_state=derivation_state,
        )

    builder = by_id.get(selected_id)
    if builder is None:
        derivation_state = _merge_derivation_state(
            derivation_state,
            DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
        )
        return AgentHandoffView(
            handoff_id=selected_id,
            status=HandoffStatus.NOT_STARTED,
            created_at=None,
            persisted_at=None,
            derivation_state=derivation_state,
        )

    return AgentHandoffView(
        handoff_id=builder.handoff_id,
        status=builder.status,
        created_at=builder.created_at,
        persisted_at=builder.persisted_at,
        derivation_state=derivation_state,
    )


def derive_human_decision_request_view(
    events: tuple[ObservabilityEvent, ...],
    *,
    wait_ordinal: Optional[int],
    interrupt_id: Optional[str],
    events_complete: bool,
) -> Optional[HumanDecisionRequestView]:
    if wait_ordinal is None:
        return None
    matches = [
        event
        for event in events
        if event.event_type is EventType.HUMAN_WAIT_STARTED and event.resume_n == wait_ordinal
    ]
    if not matches:
        return None
    derivation_state = DerivationState.OK
    if len(matches) > 1:
        derivation_state = DerivationState.INCONSISTENT
    event = matches[0]
    if interrupt_id is not None and event.interrupt_id is not None and event.interrupt_id != interrupt_id:
        derivation_state = DerivationState.INCONSISTENT
    context = event.human_decision_request
    if context is None:
        derivation_state = _merge_derivation_state(
            derivation_state,
            DerivationState.INCOMPLETE,
        )
        return HumanDecisionRequestView(
            interrupt_id=event.interrupt_id or interrupt_id or "",
            wait_ordinal=wait_ordinal,
            stage_id=event.stage_id or _HITL_WAIT_STAGE,
            reason_code="",
            human_readable_reason=None,
            allowed_decisions=(),
            evidence_refs=(),
            derivation_state=derivation_state,
        )
    return HumanDecisionRequestView(
        interrupt_id=event.interrupt_id or interrupt_id or "",
        wait_ordinal=wait_ordinal,
        stage_id=event.stage_id or _HITL_WAIT_STAGE,
        reason_code=context.reason_code,
        human_readable_reason=context.human_readable_reason,
        allowed_decisions=context.allowed_decisions,
        evidence_refs=context.evidence_refs,
        derivation_state=derivation_state,
    )


def derive_human_decision_record_view(
    events: tuple[ObservabilityEvent, ...],
    *,
    wait_ordinal: Optional[int],
    interrupt_id: Optional[str],
    events_complete: bool,
) -> Optional[HumanDecisionRecordView]:
    if wait_ordinal is None:
        return None
    matches = [
        event
        for event in events
        if event.event_type is EventType.HUMAN_DECISION_RECEIVED and event.resume_n == wait_ordinal
    ]
    if not matches:
        abort_matches = [
            event
            for event in events
            if event.event_type is EventType.RUN_ABORTED
            and event.stage_id == _HITL_WAIT_STAGE
            and event.resume_n == wait_ordinal
            and event.decision_id is not None
        ]
        if len(abort_matches) == 1:
            event = abort_matches[0]
            context = event.human_decision_record
            derivation_state = DerivationState.OK
            if context is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCOMPLETE,
                )
                return None
            return HumanDecisionRecordView(
                decision_id=event.decision_id or "",
                interrupt_id=event.interrupt_id or interrupt_id or "",
                wait_ordinal=wait_ordinal,
                decision_code=context.decision_code,
                actor_id=context.actor_id,
                actor_type=context.actor_type,
                received_at=event.occurred_at,
                derivation_state=derivation_state,
            )
        return None
    derivation_state = DerivationState.OK
    if len(matches) > 1:
        derivation_state = DerivationState.INCONSISTENT
    event = matches[0]
    if interrupt_id is not None and event.interrupt_id is not None and event.interrupt_id != interrupt_id:
        derivation_state = DerivationState.INCONSISTENT
    context = event.human_decision_record
    if context is None:
        derivation_state = _merge_derivation_state(
            derivation_state,
            DerivationState.INCOMPLETE,
        )
        return None
    return HumanDecisionRecordView(
        decision_id=event.decision_id or "",
        interrupt_id=event.interrupt_id or interrupt_id or "",
        wait_ordinal=wait_ordinal,
        decision_code=context.decision_code,
        actor_id=context.actor_id,
        actor_type=context.actor_type,
        received_at=event.occurred_at,
        derivation_state=derivation_state,
    )


def derive_human_decision_consequence_view(
    events: tuple[ObservabilityEvent, ...],
    *,
    wait_ordinal: Optional[int],
    decision_id: Optional[str],
    events_complete: bool,
) -> Optional[HumanDecisionConsequenceView]:
    from agents.observability.contracts import EventStatus

    if wait_ordinal is None:
        return None

    decision_events = [
        event
        for event in events
        if event.event_type is EventType.HUMAN_DECISION_RECEIVED and event.resume_n == wait_ordinal
    ]
    if not decision_events:
        return HumanDecisionConsequenceView(
            decision_received_at=None,
            closed_by=None,
            closed_at=None,
            reality_refresh_started_at=None,
            reality_refresh_completed_at=None,
            reality_refresh_failed_at=None,
            next_stage_id=None,
            next_stage_started_at=None,
            terminal_event_type=None,
            derivation_state=(
                DerivationState.INCOMPLETE if not events_complete else DerivationState.OK
            ),
        )

    derivation_state = DerivationState.OK
    if len(decision_events) > 1:
        derivation_state = DerivationState.INCONSISTENT
    decision_event = decision_events[0]
    decision_received_at = decision_event.occurred_at
    if decision_id is not None and decision_event.decision_id is not None and decision_event.decision_id != decision_id:
        derivation_state = DerivationState.INCONSISTENT

    closed_by: Optional[WaitClosedBy] = None
    closed_at: Optional[datetime] = None
    reality_refresh_started_at: Optional[datetime] = None
    reality_refresh_completed_at: Optional[datetime] = None
    reality_refresh_failed_at: Optional[datetime] = None
    next_stage_id: Optional[str] = None
    next_stage_started_at: Optional[datetime] = None
    terminal_event_type: Optional[str] = None

    start_index = events.index(decision_event)
    for event in events[start_index + 1 :]:
        if event.event_type is EventType.RUN_RESUMED and event.resume_n == wait_ordinal:
            if closed_by is not None:
                derivation_state = DerivationState.INCONSISTENT
            closed_by = WaitClosedBy.RESUMED
            closed_at = event.occurred_at
            continue
        if (
            event.event_type is EventType.RUN_ABORTED
            and event.stage_id == _HITL_WAIT_STAGE
            and event.resume_n == wait_ordinal
        ):
            if closed_by is not None:
                derivation_state = DerivationState.INCONSISTENT
            closed_by = WaitClosedBy.ABORTED
            closed_at = event.occurred_at
            continue
        if event.event_type is EventType.REALITY_REFRESH_STARTED and event.resume_n == wait_ordinal:
            reality_refresh_started_at = event.occurred_at
            continue
        if event.event_type is EventType.REALITY_REFRESH_COMPLETED and event.resume_n == wait_ordinal:
            if event.status is EventStatus.OK:
                reality_refresh_completed_at = event.occurred_at
            else:
                reality_refresh_failed_at = event.occurred_at
            continue
        if (
            event.event_type is EventType.STAGE_STARTED
            and closed_at is not None
            and next_stage_id is None
        ):
            next_stage_id = event.stage_id
            next_stage_started_at = event.occurred_at
            continue
        if event.event_type in {EventType.RUN_COMPLETED, EventType.RUN_FAILED}:
            terminal_event_type = event.event_type.value

    if not events_complete and closed_at is None and reality_refresh_started_at is None:
        derivation_state = _merge_derivation_state(derivation_state, DerivationState.INCOMPLETE)

    return HumanDecisionConsequenceView(
        decision_received_at=decision_received_at,
        closed_by=closed_by,
        closed_at=closed_at,
        reality_refresh_started_at=reality_refresh_started_at,
        reality_refresh_completed_at=reality_refresh_completed_at,
        reality_refresh_failed_at=reality_refresh_failed_at,
        next_stage_id=next_stage_id,
        next_stage_started_at=next_stage_started_at,
        terminal_event_type=terminal_event_type,
        derivation_state=derivation_state,
    )


def derive_human_decision_surface(
    run: AgentRun,
    events: tuple[ObservabilityEvent, ...],
    *,
    human_wait: AgentHumanWaitView,
    events_complete: bool,
) -> AgentHumanDecisionSurfaceView:
    wait_ordinal = human_wait.wait_ordinal
    interrupt_id = human_wait.interrupt_id
    request = derive_human_decision_request_view(
        events,
        wait_ordinal=wait_ordinal,
        interrupt_id=interrupt_id,
        events_complete=events_complete,
    )
    decision = derive_human_decision_record_view(
        events,
        wait_ordinal=wait_ordinal,
        interrupt_id=interrupt_id,
        events_complete=events_complete,
    )
    consequence = derive_human_decision_consequence_view(
        events,
        wait_ordinal=wait_ordinal,
        decision_id=decision.decision_id if decision is not None else human_wait.decision_id,
        events_complete=events_complete,
    )
    return AgentHumanDecisionSurfaceView(
        wait=human_wait,
        request=request,
        decision=decision,
        consequence=consequence,
        authority_modeled=False,
    )


def _stage_correlation_key(
    stage_id: str,
    attempt_n: int,
    resume_n: int,
) -> tuple[str, int, int]:
    return (stage_id, attempt_n, resume_n)


def _collect_stage_tools(
    events: tuple[ObservabilityEvent, ...],
) -> dict[tuple[str, int, int], tuple[StageToolExecutionView, ...]]:
    from agents.observability.contracts import EventStatus

    open_tools: dict[tuple[str, str, int, int], tuple[datetime, str]] = {}
    by_stage: dict[tuple[str, int, int], list[StageToolExecutionView]] = {}

    for event in events:
        if event.tool_name is None or event.stage_id is None:
            continue
        stage_key = _stage_correlation_key(event.stage_id, event.attempt_n, event.resume_n)
        tool_key = (event.stage_id, event.tool_name, event.attempt_n, event.resume_n)

        if event.event_type is EventType.TOOL_CALL_STARTED:
            open_tools[tool_key] = (event.occurred_at, event.event_id)
            continue

        if event.event_type is EventType.TOOL_CALL_COMPLETED:
            started = open_tools.pop(tool_key, None)
            if started is None:
                continue
            status = (
                ToolExecutionStatus.COMPLETED
                if event.status is EventStatus.OK
                else ToolExecutionStatus.FAILED
            )
            view = StageToolExecutionView(
                tool_name=event.tool_name,
                status=status,
                stage_id=event.stage_id,
                attempt_n=event.attempt_n,
                resume_n=event.resume_n,
                started_at=started[0],
                completed_at=event.occurred_at,
            )
            by_stage.setdefault(stage_key, []).append(view)
            continue

        if event.event_type is EventType.TOOL_CALL_DENIED:
            started = open_tools.pop(tool_key, None)
            if started is None:
                continue
            view = StageToolExecutionView(
                tool_name=event.tool_name,
                status=ToolExecutionStatus.DENIED,
                stage_id=event.stage_id,
                attempt_n=event.attempt_n,
                resume_n=event.resume_n,
                started_at=started[0],
                completed_at=event.occurred_at,
            )
            by_stage.setdefault(stage_key, []).append(view)

    for tool_key, (started_at, _event_id) in open_tools.items():
        stage_id, tool_name, attempt_n, resume_n = tool_key
        stage_key = _stage_correlation_key(stage_id, attempt_n, resume_n)
        view = StageToolExecutionView(
            tool_name=tool_name,
            status=ToolExecutionStatus.RUNNING,
            stage_id=stage_id,
            attempt_n=attempt_n,
            resume_n=resume_n,
            started_at=started_at,
            completed_at=None,
        )
        by_stage.setdefault(stage_key, []).append(view)

    return {key: tuple(items) for key, items in by_stage.items()}


def _collect_stage_artifacts(
    events: tuple[ObservabilityEvent, ...],
) -> dict[tuple[str, int, int], tuple[StageArtifactView, ...]]:
    by_stage: dict[tuple[str, int, int], list[StageArtifactView]] = {}
    for event in events:
        if event.event_type is not EventType.ARTIFACT_CREATED:
            continue
        if event.artifact_type is None or event.artifact_id is None or event.stage_id is None:
            continue
        stage_key = _stage_correlation_key(event.stage_id, event.attempt_n, event.resume_n)
        view = StageArtifactView(
            artifact_type=event.artifact_type,
            artifact_id=event.artifact_id,
            stage_id=event.stage_id,
            resume_n=event.resume_n,
            created_at=event.occurred_at,
        )
        by_stage.setdefault(stage_key, []).append(view)
    return {key: tuple(items) for key, items in by_stage.items()}


def _wait_closed_by_ordinal(
    events: tuple[ObservabilityEvent, ...],
    *,
    wait_ordinal: int,
) -> Optional[WaitClosedBy]:
    for event in events:
        if event.resume_n != wait_ordinal:
            continue
        if event.event_type is EventType.RUN_RESUMED and event.stage_id == _HITL_WAIT_STAGE:
            return WaitClosedBy.RESUMED
        if event.event_type is EventType.RUN_ABORTED and event.stage_id == _HITL_WAIT_STAGE:
            return WaitClosedBy.ABORTED
    return None


def _derive_human_decision_surface_for_wait(
    run: AgentRun,
    events: tuple[ObservabilityEvent, ...],
    *,
    wait_ordinal: int,
    interrupt_id: Optional[str],
    wait_started_at: datetime,
    events_complete: bool,
) -> AgentHumanDecisionSurfaceView:
    closed_by = _wait_closed_by_ordinal(events, wait_ordinal=wait_ordinal)
    waiting_for_human = (
        run.operational_status is OperationalStatus.WAITING_FOR_HUMAN
        and closed_by is None
        and run.interrupt_id == interrupt_id
    )
    human_wait = AgentHumanWaitView(
        waiting_for_human=waiting_for_human,
        interrupt_id=interrupt_id,
        wait_started_at=wait_started_at,
        decision_id=None,
        wait_closed_by=closed_by,
        wait_ordinal=wait_ordinal,
        derivation_state=DerivationState.OK,
    )
    request = derive_human_decision_request_view(
        events,
        wait_ordinal=wait_ordinal,
        interrupt_id=interrupt_id,
        events_complete=events_complete,
    )
    decision = derive_human_decision_record_view(
        events,
        wait_ordinal=wait_ordinal,
        interrupt_id=interrupt_id,
        events_complete=events_complete,
    )
    consequence = derive_human_decision_consequence_view(
        events,
        wait_ordinal=wait_ordinal,
        decision_id=decision.decision_id if decision is not None else None,
        events_complete=events_complete,
    )
    wait_derivation = DerivationState.OK
    for part in (request, decision, consequence):
        if part is not None and hasattr(part, "derivation_state"):
            wait_derivation = _merge_derivation_state(wait_derivation, part.derivation_state)
    human_wait = AgentHumanWaitView(
        waiting_for_human=waiting_for_human,
        interrupt_id=interrupt_id,
        wait_started_at=wait_started_at,
        decision_id=decision.decision_id if decision is not None else None,
        wait_closed_by=closed_by,
        wait_ordinal=wait_ordinal,
        derivation_state=wait_derivation,
    )
    return AgentHumanDecisionSurfaceView(
        wait=human_wait,
        request=request,
        decision=decision,
        consequence=consequence,
        authority_modeled=False,
    )


def _stage_display_to_professional(state: StageDisplayState) -> ProfessionalExecutionState:
    if state is StageDisplayState.COMPLETED:
        return ProfessionalExecutionState.COMPLETED
    if state is StageDisplayState.FAILED:
        return ProfessionalExecutionState.FAILED
    return ProfessionalExecutionState.RUNNING


def derive_professional_execution_path(
    run: AgentRun,
    events: tuple[ObservabilityEvent, ...],
    *,
    events_complete: bool,
) -> AgentProfessionalExecutionPathView:
    derivation_state = DerivationState.OK
    stage_tools = _collect_stage_tools(events)
    stage_artifacts = _collect_stage_artifacts(events)

    stage_open: dict[tuple[str, str, int, int, str], AgentStageOccurrenceView] = {}
    steps: list[ProfessionalExecutionStepView] = []
    refresh_open: dict[tuple[int, str], RealityRefreshStepView] = {}
    handoff_open: dict[str, int] = {}

    for event in events:
        if event.event_type is EventType.STAGE_STARTED:
            key = _stage_occurrence_key(event)
            if key is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT,
                )
                continue
            stage_key = _stage_correlation_key(key[0], key[2], key[3])
            occurrence = AgentStageOccurrenceView(
                stage_id=key[0],
                node_name=key[1],
                attempt_n=key[2],
                resume_n=key[3],
                artifact_id=key[4],
                display_state=StageDisplayState.RUNNING,
                started_at=event.occurred_at,
                completed_at=None,
                started_event_id=event.event_id,
                terminal_event_id=None,
            )
            stage_open[key] = occurrence
            tools = stage_tools.get(stage_key, ())
            artifacts = stage_artifacts.get(stage_key, ())
            steps.append(
                ProfessionalExecutionStepView(
                    step_kind=ProfessionalExecutionStepKind.STAGE,
                    step_id=event.event_id,
                    stage_id=key[0],
                    professional_state=ProfessionalExecutionState.RUNNING,
                    started_at=event.occurred_at,
                    completed_at=None,
                    attempt_n=key[2],
                    resume_n=key[3],
                    derivation_state=DerivationState.OK,
                    tools=tools,
                    artifacts=artifacts,
                    human_decision=None,
                    reality_refresh=None,
                    handoff_id=None,
                )
            )
            continue

        if event.event_type in _STAGE_TERMINAL:
            key = _stage_occurrence_key(event)
            if key is None or key not in stage_open:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT if events_complete else DerivationState.INCOMPLETE,
                )
                continue
            occurrence = stage_open[key]
            display_state = (
                StageDisplayState.COMPLETED
                if event.event_type is EventType.STAGE_COMPLETED
                else StageDisplayState.FAILED
            )
            occurrence = AgentStageOccurrenceView(
                stage_id=occurrence.stage_id,
                node_name=occurrence.node_name,
                attempt_n=occurrence.attempt_n,
                resume_n=occurrence.resume_n,
                artifact_id=occurrence.artifact_id,
                display_state=display_state,
                started_at=occurrence.started_at,
                completed_at=event.occurred_at,
                started_event_id=occurrence.started_event_id,
                terminal_event_id=event.event_id,
            )
            stage_open[key] = occurrence
            for index, step in enumerate(steps):
                if (
                    step.step_kind is ProfessionalExecutionStepKind.STAGE
                    and step.step_id == occurrence.started_event_id
                ):
                    steps[index] = ProfessionalExecutionStepView(
                        step_kind=step.step_kind,
                        step_id=step.step_id,
                        stage_id=step.stage_id,
                        professional_state=_stage_display_to_professional(display_state),
                        started_at=step.started_at,
                        completed_at=event.occurred_at,
                        attempt_n=step.attempt_n,
                        resume_n=step.resume_n,
                        derivation_state=step.derivation_state,
                        tools=step.tools,
                        artifacts=step.artifacts,
                        human_decision=step.human_decision,
                        reality_refresh=step.reality_refresh,
                        handoff_id=step.handoff_id,
                    )
                    break
            continue

        if event.event_type is EventType.HUMAN_WAIT_STARTED:
            if event.stage_id is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT,
                )
                continue
            wait_ordinal = event.resume_n
            surface = _derive_human_decision_surface_for_wait(
                run,
                events,
                wait_ordinal=wait_ordinal,
                interrupt_id=event.interrupt_id,
                wait_started_at=event.occurred_at,
                events_complete=events_complete,
            )
            derivation_state = _merge_derivation_state(
                derivation_state,
                surface.wait.derivation_state,
            )
            if surface.request is not None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    surface.request.derivation_state,
                )
            if surface.decision is not None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    surface.decision.derivation_state,
                )
            if surface.consequence is not None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    surface.consequence.derivation_state,
                )
            prof_state = (
                ProfessionalExecutionState.WAITING_FOR_HUMAN
                if surface.wait.waiting_for_human
                else ProfessionalExecutionState.COMPLETED
                if surface.wait.wait_closed_by is WaitClosedBy.RESUMED
                else ProfessionalExecutionState.FAILED
                if surface.wait.wait_closed_by is WaitClosedBy.ABORTED
                else ProfessionalExecutionState.RUNNING
            )
            if surface.request is not None and surface.request.derivation_state is DerivationState.INCOMPLETE:
                prof_state = ProfessionalExecutionState.INCOMPLETE
            steps.append(
                ProfessionalExecutionStepView(
                    step_kind=ProfessionalExecutionStepKind.HUMAN_DECISION,
                    step_id=event.event_id,
                    stage_id=event.stage_id,
                    professional_state=prof_state,
                    started_at=event.occurred_at,
                    completed_at=surface.consequence.closed_at if surface.consequence else None,
                    attempt_n=event.attempt_n,
                    resume_n=wait_ordinal,
                    derivation_state=surface.wait.derivation_state,
                    tools=(),
                    artifacts=(),
                    human_decision=surface,
                    reality_refresh=None,
                    handoff_id=None,
                )
            )
            continue

        if event.event_type is EventType.REALITY_REFRESH_STARTED:
            if event.stage_id is None:
                derivation_state = _merge_derivation_state(
                    derivation_state,
                    DerivationState.INCONSISTENT,
                )
                continue
            refresh_view = RealityRefreshStepView(
                stage_id=event.stage_id,
                resume_n=event.resume_n,
                started_at=event.occurred_at,
                completed_at=None,
                failed_at=None,
                derivation_state=DerivationState.OK,
            )
            refresh_open[(event.resume_n, event.event_id)] = refresh_view
            steps.append(
                ProfessionalExecutionStepView(
                    step_kind=ProfessionalExecutionStepKind.REALITY_REFRESH,
                    step_id=event.event_id,
                    stage_id=event.stage_id,
                    professional_state=ProfessionalExecutionState.RUNNING,
                    started_at=event.occurred_at,
                    completed_at=None,
                    attempt_n=event.attempt_n,
                    resume_n=event.resume_n,
                    derivation_state=DerivationState.OK,
                    tools=(),
                    artifacts=(),
                    human_decision=None,
                    reality_refresh=refresh_view,
                    handoff_id=None,
                )
            )
            continue

        if event.event_type is EventType.REALITY_REFRESH_COMPLETED:
            for index, step in enumerate(steps):
                if (
                    step.step_kind is ProfessionalExecutionStepKind.REALITY_REFRESH
                    and step.resume_n == event.resume_n
                    and step.reality_refresh is not None
                    and step.reality_refresh.completed_at is None
                    and step.reality_refresh.failed_at is None
                ):
                    from agents.observability.contracts import EventStatus

                    completed_at = event.occurred_at if event.status is EventStatus.OK else None
                    failed_at = event.occurred_at if event.status is not EventStatus.OK else None
                    refresh_view = RealityRefreshStepView(
                        stage_id=step.reality_refresh.stage_id,
                        resume_n=step.reality_refresh.resume_n,
                        started_at=step.reality_refresh.started_at,
                        completed_at=completed_at,
                        failed_at=failed_at,
                        derivation_state=DerivationState.OK,
                    )
                    prof_state = (
                        ProfessionalExecutionState.COMPLETED
                        if completed_at is not None
                        else ProfessionalExecutionState.FAILED
                    )
                    steps[index] = ProfessionalExecutionStepView(
                        step_kind=step.step_kind,
                        step_id=step.step_id,
                        stage_id=step.stage_id,
                        professional_state=prof_state,
                        started_at=step.started_at,
                        completed_at=event.occurred_at,
                        attempt_n=step.attempt_n,
                        resume_n=step.resume_n,
                        derivation_state=step.derivation_state,
                        tools=step.tools,
                        artifacts=step.artifacts,
                        human_decision=step.human_decision,
                        reality_refresh=refresh_view,
                        handoff_id=step.handoff_id,
                    )
                    break
            continue

        if event.event_type is EventType.HANDOFF_CREATED and event.handoff_id is not None:
            handoff_open[event.handoff_id] = len(steps)
            steps.append(
                ProfessionalExecutionStepView(
                    step_kind=ProfessionalExecutionStepKind.HANDOFF_MARKER,
                    step_id=event.event_id,
                    stage_id=event.stage_id,
                    professional_state=ProfessionalExecutionState.RUNNING,
                    started_at=event.occurred_at,
                    completed_at=None,
                    attempt_n=event.attempt_n,
                    resume_n=event.resume_n,
                    derivation_state=DerivationState.OK,
                    tools=(),
                    artifacts=(),
                    human_decision=None,
                    reality_refresh=None,
                    handoff_id=event.handoff_id,
                )
            )
            continue

        if event.event_type is EventType.HANDOFF_PERSISTED and event.handoff_id is not None:
            index = handoff_open.get(event.handoff_id)
            if index is not None:
                step = steps[index]
                steps[index] = ProfessionalExecutionStepView(
                    step_kind=step.step_kind,
                    step_id=step.step_id,
                    stage_id=step.stage_id,
                    professional_state=ProfessionalExecutionState.COMPLETED,
                    started_at=step.started_at,
                    completed_at=event.occurred_at,
                    attempt_n=step.attempt_n,
                    resume_n=step.resume_n,
                    derivation_state=step.derivation_state,
                    tools=step.tools,
                    artifacts=step.artifacts,
                    human_decision=step.human_decision,
                    reality_refresh=step.reality_refresh,
                    handoff_id=step.handoff_id,
                )
            continue

        if event.event_type is EventType.HANDOFF_PERSIST_FAILED and event.handoff_id is not None:
            index = handoff_open.get(event.handoff_id)
            if index is not None:
                step = steps[index]
                steps[index] = ProfessionalExecutionStepView(
                    step_kind=step.step_kind,
                    step_id=step.step_id,
                    stage_id=step.stage_id,
                    professional_state=ProfessionalExecutionState.FAILED,
                    started_at=step.started_at,
                    completed_at=event.occurred_at,
                    attempt_n=step.attempt_n,
                    resume_n=step.resume_n,
                    derivation_state=step.derivation_state,
                    tools=step.tools,
                    artifacts=step.artifacts,
                    human_decision=step.human_decision,
                    reality_refresh=step.reality_refresh,
                    handoff_id=step.handoff_id,
                )

    if not events_complete:
        derivation_state = _merge_derivation_state(derivation_state, DerivationState.INCOMPLETE)

    finalized_steps: list[ProfessionalExecutionStepView] = []
    for step in steps:
        if step.step_kind is not ProfessionalExecutionStepKind.STAGE:
            finalized_steps.append(step)
            continue
        stage_key = _stage_correlation_key(step.stage_id or "", step.attempt_n, step.resume_n)
        end_at = step.completed_at
        filtered_tools = tuple(
            tool
            for tool in stage_tools.get(stage_key, ())
            if tool.started_at >= step.started_at
            and (end_at is None or (tool.completed_at or tool.started_at) <= end_at)
        )
        filtered_artifacts = tuple(
            artifact
            for artifact in stage_artifacts.get(stage_key, ())
            if artifact.created_at >= step.started_at
            and (end_at is None or artifact.created_at <= end_at)
        )
        finalized_steps.append(
            ProfessionalExecutionStepView(
                step_kind=step.step_kind,
                step_id=step.step_id,
                stage_id=step.stage_id,
                professional_state=step.professional_state,
                started_at=step.started_at,
                completed_at=step.completed_at,
                attempt_n=step.attempt_n,
                resume_n=step.resume_n,
                derivation_state=step.derivation_state,
                tools=filtered_tools,
                artifacts=filtered_artifacts,
                human_decision=step.human_decision,
                reality_refresh=step.reality_refresh,
                handoff_id=step.handoff_id,
            )
        )

    return AgentProfessionalExecutionPathView(
        steps=tuple(finalized_steps),
        derivation_state=derivation_state,
        history_complete=events_complete,
    )
