"""PSAA S05 — Temporal Integrity contracts.

MAN-MINUTES ≠ ELAPSED MINUTES.
ARITHMETIC LABOR BALANCE ≠ VERIFIED TEMPORAL FEASIBILITY.
CLAIMED CHRONOLOGY ≠ VERIFIED CHRONOLOGY.
Does not invent timestamps or worker allocations.
Serializable; durable history schema unchanged in this increment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S05_RULES_VERSION = "psaa.s05.temporal_integrity.v0.1"
S05_ARTIFACT_SCHEMA_VERSION = "shift_temporal_integrity.v0.1"


class TimestampAuthority(str, Enum):
    EXPLICIT_CLAIMED_INTERVAL = "EXPLICIT_CLAIMED_INTERVAL"
    REGISTRATION_TIMESTAMP_ONLY = "REGISTRATION_TIMESTAMP_ONLY"
    ABSENT = "ABSENT"
    AMBIGUOUS = "AMBIGUOUS"


class CapacityAuthority(str, Enum):
    """Authority under which a capacity limit is applied — not interchangeable."""

    SCENARIO_ASSUMPTION = "SCENARIO_ASSUMPTION"
    CLAIMED_WORKER_ALLOCATION = "CLAIMED_WORKER_ALLOCATION"
    CONFIRMED_AVAILABLE_CREW_CAPACITY = "CONFIRMED_AVAILABLE_CREW_CAPACITY"
    # Not assigned in S05 v0.1 without verified participation evidence:
    EVIDENCE_SUPPORTED_ACTUAL_PARTICIPATION = "EVIDENCE_SUPPORTED_ACTUAL_PARTICIPATION"


class TemporalFindingStatus(str, Enum):
    TIME_BALANCE_COMPUTABLE = "TIME_BALANCE_COMPUTABLE"
    TEMPORAL_CONTEXT_INSUFFICIENT = "TEMPORAL_CONTEXT_INSUFFICIENT"
    CONDITIONAL_DURATION_BOUND_COMPUTED = "CONDITIONAL_DURATION_BOUND_COMPUTED"
    INVALID_TIME_INTERVAL = "INVALID_TIME_INTERVAL"
    OUTSIDE_KNOWN_SHIFT_INTERVAL = "OUTSIDE_KNOWN_SHIFT_INTERVAL"
    CLAIMED_INTERVAL_OVERLAP = "CLAIMED_INTERVAL_OVERLAP"
    EXCLUSIVE_WORKER_ALLOCATION_CONFLICT = "EXCLUSIVE_WORKER_ALLOCATION_CONFLICT"
    # Scenario limit exceeded ≠ proven physical capacity conflict:
    SCENARIO_CAPACITY_LIMIT_EXCEEDED = "SCENARIO_CAPACITY_LIMIT_EXCEEDED"
    # Claimed allocations exceed caller-confirmed available capacity
    # (still ≠ verified physical conflict / fraud):
    CAPACITY_CONFLICT = "CAPACITY_CONFLICT"
    CHRONOLOGY_NOT_PROVEN = "CHRONOLOGY_NOT_PROVEN"
    WORKER_ALLOCATION_NOT_PROVEN = "WORKER_ALLOCATION_NOT_PROVEN"
    INTERVAL_VALID_CLAIMED_ONLY = "INTERVAL_VALID_CLAIMED_ONLY"
    LABOR_EXCEEDS_INTERVAL_CAPACITY = "LABOR_EXCEEDS_INTERVAL_CAPACITY"
    AMBIGUOUS_TIMEZONE_OR_DATE = "AMBIGUOUS_TIMEZONE_OR_DATE"
    NOT_EVALUATED = "NOT_EVALUATED"


class ChronologyVerificationStatus(str, Enum):
    CHRONOLOGY_NOT_PROVEN = "CHRONOLOGY_NOT_PROVEN"
    CLAIMED_INTERVALS_PRESENT_NOT_VERIFIED = "CLAIMED_INTERVALS_PRESENT_NOT_VERIFIED"
    # Never assigned without sufficient evidence in S05 v0.1
    VERIFIED_CHRONOLOGY = "VERIFIED_CHRONOLOGY"


class TemporalFeasibilityStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    FEASIBLE_UNDER_STATED_ASSUMPTIONS = "FEASIBLE_UNDER_STATED_ASSUMPTIONS"
    CONFLICT_IN_CLAIMED_DATA = "CONFLICT_IN_CLAIMED_DATA"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


@dataclass(frozen=True)
class OperationTemporalClaim:
    """Optional caller-supplied temporal context — never invented by S05."""

    source_operation_identity: Optional[str] = None
    original_operation_text: Optional[str] = None
    claimed_start_utc: Optional[str] = None  # ISO-8601 preferred
    claimed_end_utc: Optional[str] = None
    timezone_explicit: bool = False
    timestamp_authority: TimestampAuthority = TimestampAuthority.ABSENT
    registration_timestamp_utc: Optional[str] = None  # NOT execution time
    worker_identities: tuple[str, ...] = ()
    exclusive_active_work: Optional[bool] = None
    participation_semantics: Optional[str] = None
    maximum_simultaneous_workers_scenario: Optional[int] = None
    physical_object_hint: Optional[str] = None
    source_note: str = "caller_supplied_temporal_claim"


@dataclass(frozen=True)
class ShiftTemporalContext:
    """Optional shift-level temporal bounds / scenario capacity."""

    shift_start_utc: Optional[str] = None
    shift_end_utc: Optional[str] = None
    overnight_shift_explicit: bool = False
    maximum_simultaneous_workers_scenario: Optional[int] = None
    # Caller-confirmed available crew capacity (still not physical proof):
    confirmed_available_crew_capacity: Optional[int] = None
    timezone_explicit: bool = False
    source_note: str = "caller_supplied_shift_temporal_context"


@dataclass(frozen=True)
class TemporalOperationFinding:
    check_identity: str
    source_operation_identity: str
    original_operation_text: str
    canonical_operation_code: Optional[str]
    canonical_operation_name: Optional[str]
    original_claimed_labor_quantity: Optional[float]
    original_labor_unit: Optional[str]
    labor_semantics: Optional[str]
    labor_man_minutes: Optional[float]
    claimed_start_utc: Optional[str]
    claimed_end_utc: Optional[str]
    timestamp_authority: TimestampAuthority
    elapsed_duration_minutes: Optional[float]
    worker_identities: tuple[str, ...]
    allocation_evidence_status: str
    conditional_duration_bound_minutes: Optional[float]
    conditional_bound_assumption: Optional[str]
    temporal_findings: tuple[str, ...]
    overlap_findings: tuple[str, ...]
    temporal_capacity_status: str
    chronology_authority: str
    finding_statuses: tuple[TemporalFindingStatus, ...]
    provenance: tuple[str, ...]
    rules_version: str
    professional_conclusion: str
    clarification_request: Optional[str]
    preserved_claimed_labor_quantity: Optional[float] = None
    capacity_conflict_authority: Optional[CapacityAuthority] = None


@dataclass(frozen=True)
class ShiftTemporalSummary:
    target_productive_fund_man_minutes: Optional[float]
    total_claimed_labor_man_minutes: Optional[float]
    signed_deviation_man_minutes: Optional[float]
    coverage_pct: Optional[float]
    time_balance_status: TemporalFindingStatus
    unallocated_relative_to_target_man_minutes: Optional[float]
    unallocated_classification: str
    individual_allocation_readiness: str
    operation_interval_coverage: str
    temporal_feasibility_status: TemporalFeasibilityStatus
    chronology_verification_status: ChronologyVerificationStatus
    unresolved_temporal_findings: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftTemporalIntegrityArtifact:
    schema_version: str
    rules_version: str
    audit_id: str
    agent_code: str
    agent_version: str
    run_id: Optional[str]
    created_at_utc: str
    project_code: str
    work_date: str
    crew_id: str
    evaluation_domain: str
    findings: tuple[TemporalOperationFinding, ...]
    shift_summary: ShiftTemporalSummary
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    payroll_decision_status: str
    disciplinary_decision_status: str
    fraud_classification_status: str
    human_readable_summary: str
    s05_engine_status: str = "S05_ENGINE_IMPLEMENTED"
    mathematical_time_balance_status: str = "COMPUTABLE_WHEN_S01_ALLOWS"
    temporal_feasibility_status_label: str = "ONLY_UNDER_STATED_ASSUMPTIONS"
    chronology_status: str = "CHRONOLOGY_NOT_PROVEN"
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
