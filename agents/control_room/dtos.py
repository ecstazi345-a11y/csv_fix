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
class AgentHandoffView:
    handoff_id: Optional[str]
    status: HandoffStatus
    created_at: Optional[datetime]
    persisted_at: Optional[datetime]
    derivation_state: DerivationState


@dataclass(frozen=True)
class AgentRunSnapshot:
    run: AgentRunDetail
    stage: AgentStageView
    human_wait: AgentHumanWaitView
    handoff: AgentHandoffView
    timeline_events: tuple[AgentEventView, ...]
    events_complete: bool
    read_at: datetime
