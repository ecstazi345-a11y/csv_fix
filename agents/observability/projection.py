"""
Increment 10.4 — pure AgentRun projection from authoritative ObservabilityEvent facts.

Agent-neutral. EventType-driven only. No stage/node/title/detail inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from agents.observability.contracts import (
    AgentRun,
    EventType,
    ObservabilityEvent,
    OperationalStatus,
    build_agent_run,
)


@dataclass(frozen=True)
class AgentRunProjectionChange:
    """
    Constrained mutable AgentRun delta for one accepted event.

    Fields set to None mean "leave unchanged" — not "clear to null".
    """

    operational_status: Optional[OperationalStatus] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    authorization_id: Optional[str] = None
    authorized_by: Optional[str] = None
    security_policy_version: Optional[str] = None
    mission_id: Optional[str] = None
    interrupt_id: Optional[str] = None
    decision_id: Optional[str] = None
    handoff_id: Optional[str] = None
    resume_n: Optional[int] = None


def project_agent_run_event(
    current_run: AgentRun,
    event: ObservabilityEvent,
) -> AgentRunProjectionChange:
    """Derive constrained projection delta from structured EventType semantics only."""
    occurred_at = event.occurred_at
    event_type = event.event_type

    if event_type is EventType.RUN_REQUESTED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.REQUESTED,
            updated_at=occurred_at,
        )

    if event_type is EventType.RUN_AUTHORIZATION_STARTED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.AUTHORIZING,
            updated_at=occurred_at,
        )

    if event_type is EventType.RUN_AUTHORIZED:
        change = AgentRunProjectionChange(
            operational_status=OperationalStatus.AUTHORIZING,
            updated_at=occurred_at,
        )
        if event.authorization_id is not None:
            return AgentRunProjectionChange(
                operational_status=OperationalStatus.AUTHORIZING,
                updated_at=occurred_at,
                authorization_id=event.authorization_id,
            )
        return change

    if event_type is EventType.RUN_DENIED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.AUTHORIZATION_DENIED,
            updated_at=occurred_at,
            completed_at=occurred_at,
        )

    if event_type in {EventType.MISSION_BOUND, EventType.RUN_STARTED}:
        if event_type is EventType.MISSION_BOUND and event.mission_id is not None:
            return AgentRunProjectionChange(
                operational_status=OperationalStatus.STARTING,
                updated_at=occurred_at,
                mission_id=event.mission_id,
            )
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.STARTING,
            updated_at=occurred_at,
        )

    if event_type is EventType.RUN_ADVANCING:
        started_at = current_run.started_at if current_run.started_at is not None else occurred_at
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.RUNNING,
            updated_at=occurred_at,
            started_at=started_at,
        )

    if event_type is EventType.HUMAN_WAIT_STARTED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.WAITING_FOR_HUMAN,
            updated_at=occurred_at,
            interrupt_id=event.interrupt_id,
        )

    if event_type is EventType.RUN_RESUMED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.RUNNING,
            updated_at=occurred_at,
            resume_n=event.resume_n,
        )

    if event_type is EventType.RUN_FAILED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.FAILED,
            updated_at=occurred_at,
            completed_at=occurred_at,
        )

    if event_type is EventType.RUN_ABORTED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.ABORTED,
            updated_at=occurred_at,
            completed_at=occurred_at,
            decision_id=event.decision_id,
        )

    if event_type is EventType.RUN_COMPLETED:
        return AgentRunProjectionChange(
            operational_status=OperationalStatus.COMPLETED,
            updated_at=occurred_at,
            completed_at=occurred_at,
            handoff_id=event.handoff_id,
        )

    return AgentRunProjectionChange(updated_at=occurred_at)


def apply_agent_run_projection_change(
    current_run: AgentRun,
    change: AgentRunProjectionChange,
) -> AgentRun:
    """Merge a constrained projection change into a new validated AgentRun envelope."""
    return build_agent_run(
        run_id=current_run.run_id,
        request_id=current_run.request_id,
        agent_code=current_run.agent_code,
        agent_version=current_run.agent_version,
        mission_id=change.mission_id if change.mission_id is not None else current_run.mission_id,
        project_code=current_run.project_code,
        month_key=current_run.month_key,
        initiator_type=current_run.initiator_type,
        initiator_id=current_run.initiator_id,
        trigger_type=current_run.trigger_type,
        trigger_reason=current_run.trigger_reason,
        operational_status=(
            change.operational_status
            if change.operational_status is not None
            else current_run.operational_status
        ),
        requested_at=current_run.requested_at,
        updated_at=change.updated_at if change.updated_at is not None else current_run.updated_at,
        thread_id=current_run.thread_id,
        attempt_n=current_run.attempt_n,
        resume_n=change.resume_n if change.resume_n is not None else current_run.resume_n,
        projection_version=current_run.projection_version,
        orchestration_run_id=current_run.orchestration_run_id,
        scope_summary=_mapping_from_scope(current_run.scope_summary),
        authorization_id=(
            change.authorization_id
            if change.authorization_id is not None
            else current_run.authorization_id
        ),
        authorized_by=(
            change.authorized_by
            if change.authorized_by is not None
            else current_run.authorized_by
        ),
        security_policy_version=(
            change.security_policy_version
            if change.security_policy_version is not None
            else current_run.security_policy_version
        ),
        lifecycle_status=current_run.lifecycle_status,
        current_stage_id=current_run.current_stage_id,
        current_node=current_run.current_node,
        started_at=change.started_at if change.started_at is not None else current_run.started_at,
        completed_at=(
            change.completed_at if change.completed_at is not None else current_run.completed_at
        ),
        checkpoint_id=current_run.checkpoint_id,
        snapshot_id=current_run.snapshot_id,
        package_id=current_run.package_id,
        interrupt_id=(
            change.interrupt_id if change.interrupt_id is not None else current_run.interrupt_id
        ),
        decision_id=(
            change.decision_id if change.decision_id is not None else current_run.decision_id
        ),
        handoff_id=change.handoff_id if change.handoff_id is not None else current_run.handoff_id,
        safe_summary=_mapping_from_scope(current_run.safe_summary),
        safe_counts=_mapping_from_scope(current_run.safe_counts),
        error_code=current_run.error_code,
        safe_error_summary=current_run.safe_error_summary,
        schema_version=current_run.schema_version,
    )


def _mapping_from_scope(value: tuple[object, ...]) -> dict[str, object]:
    from agents.observability.contracts import _unfreeze_jsonable

    unfrozen = _unfreeze_jsonable(value)
    if isinstance(unfrozen, dict):
        return dict(unfrozen)
    return {}
