"""PSAA S08 — Evidence Validation contracts (+ Spatial Execution Evidence compatibility).

Implements evidence layers A/B/C within this increment:
  A. Claimed execution
  B. Evidence reference
  C. Evidence metadata validation

Does NOT implement:
  D. Evidence content validation
  E. Physical execution verification
  F. Acceptance decision (Human Gate)

ATTACHED EVIDENCE ≠ VALIDATED EVIDENCE.
MARKUP ≠ VERIFIED PHYSICAL EXECUTION.
ONE PHYSICAL OBJECT ≠ ONE DRAWING REPRESENTATION.
Serializable; durable history schema unchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S08_RULES_VERSION = "psaa.s08.evidence_validation.v0.1"
S08_ARTIFACT_SCHEMA_VERSION = "shift_evidence_validation.v0.1"
S08_DEMO_REQUIREMENT_VERSION = "psaa.s08.demo_evidence_requirements.v0.1"


class EvidenceType(str, Enum):
    PHOTOGRAPHIC = "PHOTOGRAPHIC"
    VIDEO = "VIDEO"
    MEASUREMENT = "MEASUREMENT"
    TEST_OR_INSPECTION_PROTOCOL = "TEST_OR_INSPECTION_PROTOCOL"
    SOURCE_ENGINEERING_DOCUMENT = "SOURCE_ENGINEERING_DOCUMENT"
    EXECUTION_RECORD = "EXECUTION_RECORD"
    DEFECT_OR_REWORK_RECORD = "DEFECT_OR_REWORK_RECORD"
    SPATIAL_DRAWING_MARKUP = "SPATIAL_DRAWING_MARKUP"
    HISTORICAL_ACCEPTANCE_REFERENCE = "HISTORICAL_ACCEPTANCE_REFERENCE"
    OTHER = "OTHER"


class EvidencePurpose(str, Enum):
    SUPPORT_CLAIMED_EXECUTION = "SUPPORT_CLAIMED_EXECUTION"
    QUANTITY_SUPPORT = "QUANTITY_SUPPORT"
    OBJECT_IDENTITY = "OBJECT_IDENTITY"
    TECHNOLOGY_COMPLIANCE = "TECHNOLOGY_COMPLIANCE"
    REWORK_CONTEXT = "REWORK_CONTEXT"
    SPATIAL_LOCATION = "SPATIAL_LOCATION"
    OTHER = "OTHER"


class EvidenceAuthority(str, Enum):
    """Authority of the evidence claim — never assigned solely from untrusted text."""

    CLAIMED_REFERENCE = "CLAIMED_REFERENCE"
    METADATA_PRESENT = "METADATA_PRESENT"
    METADATA_VALIDATED = "METADATA_VALIDATED"
    # Content / physical verification reserved — not auto-assigned in this increment:
    CONTENT_VERIFIED = "CONTENT_VERIFIED"
    PHYSICAL_EXECUTION_VERIFIED = "PHYSICAL_EXECUTION_VERIFIED"


class RepresentationType(str, Enum):
    PLAN = "PLAN"
    AXONOMETRY = "AXONOMETRY"
    SECTION = "SECTION"
    BIM_MODEL = "BIM_MODEL"
    OTHER = "OTHER"


class GeometryReferenceKind(str, Enum):
    POINT = "POINT"
    LINE = "LINE"
    AREA = "AREA"
    OBJECT_REFERENCE = "OBJECT_REFERENCE"


class QuantityBasis(str, Enum):
    DESIGN = "DESIGN"
    CONTRACTUAL = "CONTRACTUAL"
    CLAIMED = "CLAIMED"
    PREVIOUSLY_CONFIRMED = "PREVIOUSLY_CONFIRMED"
    ACCEPTED = "ACCEPTED"
    OTHER = "OTHER"


class HistoryCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNCERTAIN_REVISION = "UNCERTAIN_REVISION"


class EvidenceFindingStatus(str, Enum):
    EVIDENCE_REFERENCE_PRESENT = "EVIDENCE_REFERENCE_PRESENT"
    EVIDENCE_METADATA_VALIDATED = "EVIDENCE_METADATA_VALIDATED"
    EVIDENCE_CONTENT_NOT_VERIFIED = "EVIDENCE_CONTENT_NOT_VERIFIED"
    EVIDENCE_APPLICABILITY_NOT_PROVEN = "EVIDENCE_APPLICABILITY_NOT_PROVEN"
    EVIDENCE_SCOPE_CONFLICT = "EVIDENCE_SCOPE_CONFLICT"
    EVIDENCE_REQUIREMENT_NOT_ESTABLISHED = "EVIDENCE_REQUIREMENT_NOT_ESTABLISHED"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    SUPPORTING_EVIDENCE_CONTEXT = "SUPPORTING_EVIDENCE_CONTEXT"
    CONTRADICTING_EVIDENCE_CONTEXT = "CONTRADICTING_EVIDENCE_CONTEXT"
    CONFLICTING_EVIDENCE_CONTEXT = "CONFLICTING_EVIDENCE_CONTEXT"
    MULTIPLE_REPRESENTATIONS_SAME_EVENT = "MULTIPLE_REPRESENTATIONS_SAME_EVENT"
    POTENTIAL_DUPLICATE_CLAIM = "POTENTIAL_DUPLICATE_CLAIM"
    SPATIAL_OVERLAP_NOT_EVALUATED = "SPATIAL_OVERLAP_NOT_EVALUATED"
    REVISION_MAPPING_NOT_PROVEN = "REVISION_MAPPING_NOT_PROVEN"
    HISTORY_INCOMPLETE = "HISTORY_INCOMPLETE"
    REMAINING_QUANTITY_NOT_PROVEN = "REMAINING_QUANTITY_NOT_PROVEN"
    POTENTIAL_QUANTITY_EXCESS = "POTENTIAL_QUANTITY_EXCESS"
    HISTORICAL_QUANTITY_BASIS_CONTRADICTION = "HISTORICAL_QUANTITY_BASIS_CONTRADICTION"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    SOURCE_VERSION_AUTHORITY_UNCERTAIN = "SOURCE_VERSION_AUTHORITY_UNCERTAIN"
    CONTRADICTORY_OBJECT_MAPPING = "CONTRADICTORY_OBJECT_MAPPING"
    PHYSICAL_EXECUTION_NOT_VERIFIED = "PHYSICAL_EXECUTION_NOT_VERIFIED"


class EvidencePolarity(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    AMBIGUOUS = "AMBIGUOUS"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class SpatialReference:
    """Minimal typed spatial reference — geometry payload optional / may be absent."""

    spatial_reference_identity: str
    representation_type: RepresentationType
    geometry_kind: GeometryReferenceKind
    physical_object_identity: Optional[str] = None
    drawing_or_model_identity: Optional[str] = None
    sheet_identity: Optional[str] = None
    revision_identity: Optional[str] = None
    geometry_payload: Optional[str] = None  # typed opaque ref; not computed geometry
    coordinate_system_or_context: Optional[str] = None
    elevation_value: Optional[float] = None
    elevation_reference_basis: Optional[str] = None  # never invented
    geometry_provenance: tuple[str, ...] = ()
    mapping_authority: str = "CLAIMED_SPATIAL_REFERENCE"
    source_note: str = "caller_supplied_spatial_reference"


@dataclass(frozen=True)
class EvidenceItem:
    """Caller-supplied evidence item — free-text fields remain untrusted data."""

    evidence_identity: str
    evidence_type: EvidenceType
    project_code: str
    source_identity: str
    claimed_evidence_purpose: EvidencePurpose = EvidencePurpose.SUPPORT_CLAIMED_EXECUTION
    polarity: EvidencePolarity = EvidencePolarity.SUPPORTING
    source_version: Optional[str] = None
    execution_event_reference: Optional[str] = None
    physical_object_reference: Optional[str] = None
    operation_code: Optional[str] = None
    document_reference: Optional[str] = None
    applicable_rd_revision: Optional[str] = None
    occurrence_time: Optional[str] = None
    capture_time: Optional[str] = None
    registration_time: Optional[str] = None
    content_reference: Optional[str] = None
    content_hash: Optional[str] = None  # only if genuinely available — never invented
    supplied_validation_authority: Optional[str] = None  # untrusted; does not grant rights
    spatial_references: tuple[SpatialReference, ...] = ()
    provenance: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    source_note: str = "caller_supplied_evidence_item"


@dataclass(frozen=True)
class HistoricalExecutionRecord:
    """Typed prior execution context for remaining-quantity checks."""

    record_identity: str
    physical_object_reference: str
    operation_code: Optional[str]
    quantity: float
    quantity_unit: str
    quantity_basis: QuantityBasis
    work_date: Optional[str] = None
    result_state: Optional[str] = None
    rd_revision: Optional[str] = None
    execution_event_reference: Optional[str] = None
    confirmed: bool = False  # previously confirmed within declared fixture/authority
    source_note: str = "caller_supplied_historical_execution"


@dataclass(frozen=True)
class QuantityContext:
    """Explicit quantity basis for remaining-quantity computation."""

    physical_object_reference: str
    operation_code: Optional[str]
    quantity_basis: QuantityBasis
    basis_quantity: float
    quantity_unit: str
    claimed_quantity: Optional[float] = None
    history_completeness: HistoryCompleteness = HistoryCompleteness.UNAVAILABLE
    applicable_rd_revision: Optional[str] = None
    revision_mapping_proven: bool = False
    authority: str = "DEMONSTRATION_QUANTITY_CONTEXT"
    source_note: str = "caller_supplied_quantity_context"


@dataclass(frozen=True)
class EvidenceRequirementSpec:
    """Minimal versioned demonstration evidence requirement — ≠ approved production norm."""

    requirement_identity: str
    operation_code: Optional[str]
    required_evidence_types: tuple[EvidenceType, ...]
    required_purpose: EvidencePurpose
    optional_evidence_types: tuple[EvidenceType, ...] = ()
    version: str = S08_DEMO_REQUIREMENT_VERSION
    authority: str = "DEMONSTRATION_EVIDENCE_REQUIREMENT"
    source_note: str = (
        "demonstration_evidence_requirement_not_approved_production_norm"
    )


@dataclass(frozen=True)
class ExecutionClaimRef:
    """Minimal claimed execution identity for S08 evaluation."""

    execution_event_identity: str
    physical_object_reference: Optional[str]
    operation_code: Optional[str]
    operation_name: Optional[str] = None
    claimed_quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    source_operation_identity: Optional[str] = None
    rd_revision: Optional[str] = None
    work_package_identity: Optional[str] = None


@dataclass(frozen=True)
class EvidenceValidationFinding:
    finding_identity: str
    finding_statuses: tuple[EvidenceFindingStatus, ...]
    linked_execution_event: Optional[str]
    physical_object_reference: Optional[str]
    operation_reference: Optional[str]
    evidence_references: tuple[str, ...]
    expected_evidence_requirement: Optional[str]
    applicability_status: str
    authority: EvidenceAuthority
    professional_conclusion: str
    missing_context: tuple[str, ...]
    next_recommended_verification_action: str
    claimed_quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    remaining_quantity: Optional[float] = None
    potential_excess_quantity: Optional[float] = None
    evidence_count: Optional[int] = None
    execution_event_count: Optional[int] = None
    representation_types: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    rules_version: str = S08_RULES_VERSION


@dataclass(frozen=True)
class ShiftEvidenceSummary:
    finding_count: int
    evidence_item_count: int
    metadata_validated_count: int
    content_verified_count: int
    physical_execution_verified_count: int
    multiple_representation_event_count: int
    potential_duplicate_count: int
    remaining_quantity_computable_count: int
    potential_excess_count: int
    total_original_labor_man_minutes: Optional[float]
    scenario_direct_labor_cost_exact: Optional[str]
    professional_conclusion: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftEvidenceValidationArtifact:
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
    findings: tuple[EvidenceValidationFinding, ...]
    shift_summary: ShiftEvidenceSummary
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    commercial_acceptance_status: str
    payroll_decision_status: str
    disciplinary_decision_status: str
    fraud_classification_status: str
    human_readable_summary: str
    s08_engine_status: str = "S08_ENGINE_IMPLEMENTED"
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"
    evidence_metadata_validation_status: str = "EVIDENCE_METADATA_VALIDATION_PROVEN"
    typed_spatial_reference_compatibility_status: str = (
        "TYPED_SPATIAL_REFERENCE_COMPATIBILITY_PROVEN"
    )
    multiple_representation_identity_status: str = (
        "MULTIPLE_REPRESENTATION_IDENTITY_HANDLING_PROVEN"
    )
    demonstration_remaining_quantity_status: str = (
        "DEMONSTRATION_REMAINING_QUANTITY_CHECK_PROVEN"
    )
    production_evidence_validation_status: str = "PRODUCTION_EVIDENCE_VALIDATION_NOT_PROVEN"
    evidence_content_validation_status: str = "EVIDENCE_CONTENT_VALIDATION_IMPLEMENTED_NO"
    geometric_overlap_engine_status: str = "GEOMETRIC_OVERLAP_ENGINE_IMPLEMENTED_NO"
    physical_execution_verified_status: str = "PHYSICAL_EXECUTION_VERIFIED_NO"
    cost_deviation_engine_status: str = "COST_DEVIATION_ENGINE_IMPLEMENTED_NO"
    cost_deviation_boundaries_status: str = "COST_DEVIATION_BOUNDARIES_ONLY_YES"
    actual_incurred_cost_status: str = "ACTUAL_INCURRED_COST_NOT_PROVEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
