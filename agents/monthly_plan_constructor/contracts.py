"""
MPCA-001 — structured contracts for Monthly Plan Constructor Agent.

No I/O. No Streamlit. No LLM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"
AGENT_NAME_RU = "Агент формирования кандидатного состава месячного плана"

STATE_STARTING = "STARTING"
STATE_READING = "READING_DATA"
STATE_ANALYZING = "ANALYZING"
STATE_VALIDATING = "VALIDATING"
STATE_NEEDS_HUMAN = "NEEDS_HUMAN"
STATE_PROPOSAL_READY = "PROPOSAL_READY"
STATE_FAILED = "FAILED"

CANDIDATE_OPEN = "OPEN_FOR_PLANNING"
CANDIDATE_PARTIAL = "PARTIAL_REMAINING"

HANDOFF_RECIPIENT = "MONTHLY_PLAN_ADMISSION_AGENT"


@dataclass
class TraceEvent:
    event_id: str
    run_id: str
    agent_code: str
    step_code: str
    step_name: str
    started_at: str
    finished_at: str
    duration_ms: float
    status: str
    input_count: int = 0
    output_count: int = 0
    summary: str = ""
    next_recipient: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BusinessAction:
    action: str
    affected_count: int = 0
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HumanIssue:
    code: str
    severity: str
    message: str
    scope_key: Optional[str] = None
    boq_code: Optional[str] = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExclusionRecord:
    scope_key: str
    boq_code: str
    reason_code: str
    reason_text: str
    facility: str = ""
    discipline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Candidate:
    project_code: str
    month_key: str
    month_key_canonical: str
    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    boq_name: str
    unit: str
    total_qty: float
    executed_total_qty: float
    not_required_qty: float
    effective_required_qty: float
    remaining_qty: float
    already_planned_qty: float
    available_to_add_qty: float
    availability_status: str
    existing_plan_line_ids: list[str] = field(default_factory=list)
    candidate_state: str = CANDIDATE_OPEN
    issues: list[str] = field(default_factory=list)
    human_required_fields: list[str] = field(
        default_factory=lambda: ["crew", "planned_qty"]
    )
    proposed_plan_qty: Optional[float] = None
    proposed_crew: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HandoffContract:
    recipient: str = HANDOFF_RECIPIENT
    ready: bool = False
    reason: str = ""
    candidate_count: int = 0
    blocking_issue_count: int = 0
    proposal_ready: bool = False
    admission_handoff_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentConstructorRun:
    run_id: str
    agent_code: str
    agent_name: str
    project_code: str
    month_key: str
    month_key_canonical: Optional[str]
    started_at: str
    finished_at: str
    duration_ms: float
    state: str
    counts: dict[str, int] = field(default_factory=dict)
    proposed_candidates: list[dict[str, Any]] = field(default_factory=list)
    human_issues: list[dict[str, Any]] = field(default_factory=list)
    exclusions: list[dict[str, Any]] = field(default_factory=list)
    actions_performed: list[dict[str, Any]] = field(default_factory=list)
    actions_pending_approval: list[dict[str, Any]] = field(default_factory=list)
    handoff: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
