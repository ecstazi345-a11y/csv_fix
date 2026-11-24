"""PSAA v0.1 contracts — ShiftAuditInput and ShiftAuditArtifact.

Not a global data model. Not Constructor packages. Not product DB schema.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


RULES_VERSION = "psaa.s01.mathematical_integrity.v0.1"
ARTIFACT_SCHEMA_VERSION = "shift_audit_artifact.v0.1"
INPUT_SCHEMA_VERSION = "shift_audit_input.v0.1"


class LaborUnit(str, Enum):
    MAN_MINUTE = "MAN_MINUTE"
    MAN_HOUR = "MAN_HOUR"
    HOUR_FIELD_UNPROVEN = "HOUR_FIELD_UNPROVEN"


class LaborSemanticsStatus(str, Enum):
    EXPLICIT_CLAIM = "EXPLICIT_CLAIM"
    PARTIALLY_PROVEN = "PARTIALLY_PROVEN"
    UNPROVEN = "UNPROVEN"


class DataSourceKind(str, Enum):
    FIXTURE = "FIXTURE"
    DAILY_PROGRESS_ACTIVE = "DAILY_PROGRESS_ACTIVE"
    MIXED = "MIXED"


class MathIntegrityStatus(str, Enum):
    COHERENT = "COHERENT"
    INCOHERENT = "INCOHERENT"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    NOT_EVALUATED = "NOT_EVALUATED"


class DataCompletenessStatus(str, Enum):
    COMPLETE_FOR_S01 = "COMPLETE_FOR_S01"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class ProfessionalCredibilityStatus(str, Enum):
    """Not acceptance. Not proven by S01 alone."""

    NOT_EVALUATED = "NOT_EVALUATED"


class ManagerialAcceptanceStatus(str, Enum):
    """Accept/reject workflow is NOT IN SCOPE for v0.1."""

    NOT_IN_SCOPE = "NOT_IN_SCOPE"


@dataclass(frozen=True)
class PhysicalVolume:
    label: str
    quantity: float
    unit: str
    linked_operation_name: Optional[str] = None


@dataclass(frozen=True)
class OperationLaborClaim:
    """One claimed operation labor line. Names are untrusted text."""

    operation_name: str
    claimed_labor_quantity: float
    labor_unit: LaborUnit
    physical_quantity: Optional[float] = None
    physical_unit: Optional[str] = None
    source_record_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShiftAuditInput:
    """Minimal structured input for PSAA S01."""

    schema_version: str
    source_kind: DataSourceKind
    project_code: str
    work_date: str
    shift_type: Optional[str]
    crew_id: str
    crew_size: int
    productive_hours_per_person: float
    operations: tuple[OperationLaborClaim, ...]
    labor_semantics_status: LaborSemanticsStatus
    labor_semantics_note: str
    source_record_ids: tuple[str, ...] = ()
    physical_volumes: tuple[PhysicalVolume, ...] = ()
    facility_building: Optional[str] = None
    construction_discipline: Optional[str] = None
    foreman: Optional[str] = None
    provenance_notes: tuple[str, ...] = ()
    # Future: bind to immutable shift report version when it exists.
    source_version_ref: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperationAuditLine:
    operation_name: str
    claimed_labor_man_minutes: Optional[float]
    claimed_labor_man_hours: Optional[float]
    share_of_target_fund_pct: Optional[float]
    physical_quantity: Optional[float]
    physical_unit: Optional[str]
    has_physical_volume: bool
    unit_labor_man_minutes_per_physical: Optional[float]
    unit_labor_man_hours_per_physical: Optional[float]
    multiple_of_5_minutes: Optional[bool]
    multiple_of_10_minutes: Optional[bool]
    source_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class S01Metrics:
    target_fund_man_minutes: Optional[float]
    target_fund_man_hours: Optional[float]
    claimed_total_man_minutes: Optional[float]
    claimed_total_man_hours: Optional[float]
    absolute_deviation_man_minutes: Optional[float]
    absolute_deviation_man_hours: Optional[float]
    fund_coverage_pct: Optional[float]
    operations_count: int
    multiples_of_5_minutes_count: Optional[int]
    multiples_of_10_minutes_count: Optional[int]
    top3_operations_man_minutes: Optional[float]
    top3_concentration_of_target_fund_pct: Optional[float]
    top3_operation_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShiftAuditArtifact:
    schema_version: str
    rules_version: str
    audit_id: str
    agent_code: str
    agent_version: str
    run_id: Optional[str]
    created_at_utc: str
    input_provenance: dict[str, Any]
    s01_metrics: S01Metrics
    operations: tuple[OperationAuditLine, ...]
    observations: tuple[str, ...]
    missing_data: tuple[str, ...]
    clarification_questions: tuple[str, ...]
    hypotheses_unproven: tuple[str, ...]
    math_integrity_status: MathIntegrityStatus
    data_completeness_status: DataCompletenessStatus
    professional_credibility_status: ProfessionalCredibilityStatus
    managerial_acceptance_status: ManagerialAcceptanceStatus
    human_readable_conclusion: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
