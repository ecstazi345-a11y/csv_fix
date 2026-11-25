"""PSAA S07 — Root Cause Analysis contracts.

ANOMALY ≠ ROOT CAUSE · CORRELATION ≠ CAUSATION · POSSIBLE ≠ ESTABLISHED.
Does not assign blame, payroll, fraud, or managerial acceptance.
Does not implement S08 evidence validation or case-management platform.
Serializable; durable history schema unchanged in this increment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional

from agents.production_shift_auditor.catalogs.cause_categories_v0_1 import (
    CAUSE_CATALOG_VERSION,
    CauseCategory,
)


S07_RULES_VERSION = "psaa.s07.root_cause_analysis.v0.1"
S07_ARTIFACT_SCHEMA_VERSION = "shift_root_cause_analysis.v0.1"


class CausalStatus(str, Enum):
    HYPOTHESIS_GENERATED = "HYPOTHESIS_GENERATED"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    SUPPORTING_CONTEXT_AVAILABLE = "SUPPORTING_CONTEXT_AVAILABLE"
    CONTRADICTORY_CONTEXT_AVAILABLE = "CONTRADICTORY_CONTEXT_AVAILABLE"
    CONFLICTING_CONTEXT = "CONFLICTING_CONTEXT"
    HYPOTHESIS_NOT_SUPPORTED = "HYPOTHESIS_NOT_SUPPORTED"
    CAUSE_NOT_ESTABLISHED = "CAUSE_NOT_ESTABLISHED"


class CausalEvidenceAuthority(str, Enum):
    """Authority of the causal claim — never invent confidence percentages."""

    OBSERVED_FINDING_ONLY = "OBSERVED_FINDING_ONLY"
    CLAIMED_CONTEXT = "CLAIMED_CONTEXT"
    DOCUMENTED_CONTEXT = "DOCUMENTED_CONTEXT"
    CONFIRMED_CONTEXT = "CONFIRMED_CONTEXT"
    STATISTICAL_CORRELATION = "STATISTICAL_CORRELATION"
    TEMPORAL_ASSOCIATION = "TEMPORAL_ASSOCIATION"
    # Never assigned automatically as proven causation in this increment:
    ESTABLISHED_CAUSAL_RELATIONSHIP = "ESTABLISHED_CAUSAL_RELATIONSHIP"


class ReviewPriority(str, Enum):
    INFORMATION = "INFORMATION"
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    HIGH_REVIEW_PRIORITY = "HIGH_REVIEW_PRIORITY"


class SuggestedClarificationRole(str, Enum):
    """Organizational role suggestion — NOT assigned responsibility."""

    FOREMAN = "FOREMAN"  # мастер
    SITE_SUPERVISOR = "SITE_SUPERVISOR"  # начальник участка
    PTO = "PTO"
    MTO = "MTO"
    PROJECT_MANAGER = "PROJECT_MANAGER"


class FindingDomain(str, Enum):
    """Which prior skill finding family triggered hypothesis generation."""

    S01_MATHEMATICAL = "S01_MATHEMATICAL"
    S10_CLASSIFICATION = "S10_CLASSIFICATION"
    S02_TECHNOLOGICAL = "S02_TECHNOLOGICAL"
    S03_PHYSICAL = "S03_PHYSICAL"
    S11_LABOR_BENCHMARK = "S11_LABOR_BENCHMARK"
    S04_EXECUTION_COST = "S04_EXECUTION_COST"
    S05_TEMPORAL = "S05_TEMPORAL"
    S06_STATISTICAL = "S06_STATISTICAL"
    DATA_QUALITY = "DATA_QUALITY"


class InvestigationDisposition(str, Enum):
    """Whether an observed finding warrants causal hypothesis work."""

    NO_MANDATORY_INVESTIGATION = "NO_MANDATORY_INVESTIGATION"
    DATA_QUALITY_LIMITATION = "DATA_QUALITY_LIMITATION"
    PRODUCTION_DEVIATION_CANDIDATE = "PRODUCTION_DEVIATION_CANDIDATE"
    INHERITED_FINDING_REUSED = "INHERITED_FINDING_REUSED"


class CausalContextKind(str, Enum):
    WORK_FRONT_RESTRICTION = "WORK_FRONT_RESTRICTION"
    MATERIAL_WAITING = "MATERIAL_WAITING"
    PHYSICAL_COMPLEXITY = "PHYSICAL_COMPLEXITY"
    MATERIAL_SPECIFICATION = "MATERIAL_SPECIFICATION"
    RD_REVISION_CHANGE = "RD_REVISION_CHANGE"
    REWORK_EVENT = "REWORK_EVENT"
    OPERATION_AGGREGATION = "OPERATION_AGGREGATION"
    REPORTING_POLICY = "REPORTING_POLICY"
    REFERENCE_COMPARABILITY_LIMITATION = "REFERENCE_COMPARABILITY_LIMITATION"
    TECHNOLOGY_DIFFERENCE = "TECHNOLOGY_DIFFERENCE"
    LABOR_CONDITION = "LABOR_CONDITION"
    # Existence of alternative work limits idle-time attribution for material delay
    ALTERNATIVE_PRODUCTIVE_WORK = "ALTERNATIVE_PRODUCTIVE_WORK"
    OTHER = "OTHER"


class CausalContextPolarity(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    AMBIGUOUS = "AMBIGUOUS"
    IRRELEVANT_SCOPE = "IRRELEVANT_SCOPE"


class CausalContextAuthority(str, Enum):
    CLAIMED = "CLAIMED"
    DOCUMENTED = "DOCUMENTED"
    CONFIRMED = "CONFIRMED"
    # Verified still ≠ established causation for the full deviation magnitude
    VERIFIED_FACT = "VERIFIED_FACT"


@dataclass(frozen=True)
class CausalContextItem:
    """Minimal typed causal context — free-text comments remain untrusted data.

    Temporal fields (do not invent chronology; do not expand S05):
      occurrence_time — physical occurrence of the described event
      observation_time — when the event was observed
      registration_time — when it entered a system of record
      document_created_at — when a describing document was created
      applicable_from/to — retrospective applicability window for the shift

    Later-recorded historical evidence (document_created_at after shift) may
    apply only when occurrence_time or applicable window covers the shift.
    A future occurrence is never an automatic cause of an earlier deviation.
    """

    context_identity: str
    context_kind: CausalContextKind
    polarity: CausalContextPolarity
    authority: CausalContextAuthority
    description: str
    source_identity: str
    project_code: Optional[str] = None
    physical_object_reference: Optional[str] = None
    operation_code: Optional[str] = None
    work_package_identity: Optional[str] = None
    source_operation_identity: Optional[str] = None
    applicable_from: Optional[str] = None  # ISO date — applicability window start
    applicable_to: Optional[str] = None
    occurrence_time: Optional[str] = None  # physical occurrence (ISO date)
    observation_time: Optional[str] = None
    registration_time: Optional[str] = None
    document_created_at: Optional[str] = None
    provenance: tuple[str, ...] = ()
    source_note: str = "caller_supplied_causal_context"


@dataclass(frozen=True)
class CauseHypothesis:
    hypothesis_identity: str
    linked_finding_identity: str
    finding_domain: FindingDomain
    investigation_disposition: InvestigationDisposition
    project_scope: str
    source_observation_identities: tuple[str, ...]
    affected_operation_identity: Optional[str]
    affected_operation_code: Optional[str]
    affected_operation_name: Optional[str]
    physical_object_reference: Optional[str]
    cause_category: CauseCategory
    possible_cause_description: str
    reasoning_basis: str
    expected_supporting_evidence: tuple[str, ...]
    expected_contradictory_evidence: tuple[str, ...]
    supplied_supporting_context_refs: tuple[str, ...]
    supplied_contradicting_context_refs: tuple[str, ...]
    missing_context: tuple[str, ...]
    targeted_clarification_question: str
    suggested_clarification_role: SuggestedClarificationRole
    review_priority: ReviewPriority
    causal_status: CausalStatus
    evidence_authority: CausalEvidenceAuthority
    provenance: tuple[str, ...]
    rules_version: str
    catalog_version: str
    professional_conclusion: str
    # Explicit: suggested role ≠ responsible party; no confidence %
    responsible_party_status: str = "NOT_ASSIGNED"
    causal_confidence_status: str = "NOT_INVENTED"
    economic_loss_allocation_status: str = "NOT_PERFORMED"


@dataclass(frozen=True)
class FindingIntakeRecord:
    """Normalized finding intake — descriptive metrics may be recorded without investigation."""

    finding_identity: str
    finding_domain: FindingDomain
    disposition: InvestigationDisposition
    source_observation_identities: tuple[str, ...]
    operation_code: Optional[str]
    operation_name: Optional[str]
    summary: str
    review_priority: ReviewPriority
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftRootCauseSummary:
    hypothesis_count: int
    investigated_finding_count: int
    skipped_descriptive_finding_count: int
    data_quality_limitation_count: int
    clarification_question_count: int
    established_cause_count: int
    total_original_labor_man_minutes: Optional[float]
    scenario_direct_labor_cost_exact: Optional[str]
    professional_conclusion: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftRootCauseArtifact:
    schema_version: str
    rules_version: str
    catalog_version: str
    audit_id: str
    agent_code: str
    agent_version: str
    run_id: Optional[str]
    created_at_utc: str
    project_code: str
    work_date: str
    crew_id: str
    finding_intake: tuple[FindingIntakeRecord, ...]
    hypotheses: tuple[CauseHypothesis, ...]
    applied_context_identities: tuple[str, ...]
    rejected_context_notes: tuple[str, ...]
    shift_summary: ShiftRootCauseSummary
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    payroll_decision_status: str
    disciplinary_decision_status: str
    fraud_classification_status: str
    human_readable_summary: str
    s07_engine_status: str = "S07_ENGINE_IMPLEMENTED"
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"
    production_root_cause_proof: str = "PRODUCTION_ROOT_CAUSE_PROOF_NOT_PROVEN"
    established_cause_status: str = "CAUSE_NOT_ESTABLISHED"
    typed_causal_context_engine_status: str = "TYPED_CAUSAL_CONTEXT_ENGINE_IMPLEMENTED_WITHIN_TESTED_SCOPE"
    cost_deviation_engine_status: str = "COST_DEVIATION_ENGINE_IMPLEMENTED_NO"
    cost_deviation_boundaries_status: str = "COST_DEVIATION_BOUNDARIES_ONLY_YES"
    actual_incurred_cost_status: str = "ACTUAL_INCURRED_COST_NOT_PROVEN"
    cause_catalog_authority: str = "DEMONSTRATION_CAUSE_CATALOG"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Re-export for callers
__all__ = [
    "CAUSE_CATALOG_VERSION",
    "S07_ARTIFACT_SCHEMA_VERSION",
    "S07_RULES_VERSION",
    "CauseCategory",
    "CausalStatus",
    "CausalEvidenceAuthority",
    "ReviewPriority",
    "SuggestedClarificationRole",
    "FindingDomain",
    "InvestigationDisposition",
    "CausalContextKind",
    "CausalContextPolarity",
    "CausalContextAuthority",
    "CausalContextItem",
    "CauseHypothesis",
    "FindingIntakeRecord",
    "ShiftRootCauseSummary",
    "ShiftRootCauseArtifact",
]
