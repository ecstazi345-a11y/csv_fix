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
    AgentRunDetail,
    AgentRunSummary,
    AgentStageOccurrenceView,
    AgentStageView,
    DerivationState,
    HandoffStatus,
    HumanDecisionConsequenceView,
    HumanDecisionRecordView,
    HumanDecisionRequestView,
    StageDisplayState,
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
