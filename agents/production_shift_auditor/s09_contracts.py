"""PSAA S09 — Shift Acceptance Recommendation contracts.

PROFESSIONAL RECOMMENDATION ≠ MANAGERIAL ACCEPTANCE.
PARTIAL RECOMMENDATION ≠ PARTIAL ACCEPTANCE.
SOFTWARE ENGINE PASS ≠ PRODUCTION VALIDATION.
Does not accept/reject shifts, mutate production events, payroll, or contracts.
Serializable; durable history schema unchanged in this increment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S09_RULES_VERSION = "psaa.s09.acceptance_recommendation.v0.1"
S09_ARTIFACT_SCHEMA_VERSION = "shift_acceptance_recommendation.v0.1"
S09_DEMO_POLICY_VERSION = "psaa.s09.recommendation_policy.v0.1"


class RecommendationStatus(str, Enum):
    """Professional recommendation only — never ACCEPTED / REJECTED."""

    RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE = (
        "RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE"
    )
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    CORRECTION_RECOMMENDED = "CORRECTION_RECOMMENDED"
    PROFESSIONAL_REVIEW_REQUIRED = "PROFESSIONAL_REVIEW_REQUIRED"
    INSUFFICIENT_BASIS_FOR_RECOMMENDATION = "INSUFFICIENT_BASIS_FOR_RECOMMENDATION"


class FindingImpact(str, Enum):
    BLOCKING = "BLOCKING"
    NON_BLOCKING = "NON_BLOCKING"
    INFORMATIONAL = "INFORMATIONAL"


class RecommendationEvidenceAuthority(str, Enum):
    """Ceiling respects S08: metadata validated ≠ content/physical verified."""

    CLAIMED_ONLY = "CLAIMED_ONLY"
    METADATA_PRESENT = "METADATA_PRESENT"
    METADATA_VALIDATED = "METADATA_VALIDATED"
    CONTENT_VERIFIED = "CONTENT_VERIFIED"
    PHYSICAL_EXECUTION_VERIFIED = "PHYSICAL_EXECUTION_VERIFIED"
    INSUFFICIENT = "INSUFFICIENT"
    UNCERTAIN = "UNCERTAIN"


class ReviewPriority(str, Enum):
    INFORMATION = "INFORMATION"
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    HIGH_REVIEW_PRIORITY = "HIGH_REVIEW_PRIORITY"


class SuggestedClarificationRole(str, Enum):
    """Organizational role suggestion — NOT assigned responsibility."""

    FOREMAN = "FOREMAN"
    SITE_SUPERVISOR = "SITE_SUPERVISOR"
    PTO = "PTO"
    MTO = "MTO"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    ENGINEER = "ENGINEER"


class PolicyAuthority(str, Enum):
    DEMONSTRATION_POLICY = "DEMONSTRATION_POLICY"
    PROJECT_ACCEPTANCE_POLICY = "PROJECT_ACCEPTANCE_POLICY"
    APPROVED_PRODUCTION_POLICY = "APPROVED_PRODUCTION_POLICY"
    POLICY_NOT_ESTABLISHED = "POLICY_NOT_ESTABLISHED"


class FindingRepresentationKind(str, Enum):
    """Distinguish original finding vs inherited/hypothesis/action layers."""

    ORIGINAL_FINDING = "ORIGINAL_FINDING"
    INHERITED_REPRESENTATION = "INHERITED_REPRESENTATION"
    CAUSAL_HYPOTHESIS = "CAUSAL_HYPOTHESIS"
    RECOMMENDED_ACTION = "RECOMMENDED_ACTION"


class SharedContextKind(str, Enum):
    SHIFT_LEVEL_LIMITATION = "SHIFT_LEVEL_LIMITATION"
    SHARED_ENGINEERING_CONTEXT = "SHARED_ENGINEERING_CONTEXT"
    PRODUCTION_POLICY_GAP = "PRODUCTION_POLICY_GAP"
    EVIDENCE_AUTHORITY_CEILING = "EVIDENCE_AUTHORITY_CEILING"


@dataclass(frozen=True)
class RecommendationPolicy:
    """Minimal deterministic recommendation policy — ≠ approved production policy."""

    policy_identity: str
    version: str
    provenance: tuple[str, ...]
    authority: PolicyAuthority
    applicable_scope: str
    required_professional_checks: tuple[str, ...]
    blocking_criteria: tuple[str, ...]
    non_blocking_criteria: tuple[str, ...]
    missing_context_treatment: str
    allows_positive_physical_acceptance: bool = False
    production_acceptance_requirements_established: bool = False
    source_note: str = (
        "demonstration_recommendation_policy_not_approved_production_policy"
    )


@dataclass(frozen=True)
class InheritedFindingRef:
    """Reference to a prior-skill finding — one underlying finding stays one proof."""

    skill_code: str
    finding_identity: str
    finding_status_or_result: str
    impact: FindingImpact
    evidence_authority: str
    source_operation_identity: Optional[str] = None
    physical_object_reference: Optional[str] = None
    operation_code: Optional[str] = None
    execution_event_reference: Optional[str] = None
    demonstration_authority: bool = False
    provenance: tuple[str, ...] = ()
    professional_note: str = ""
    underlying_finding_identity: Optional[str] = None
    representation_kind: FindingRepresentationKind = (
        FindingRepresentationKind.ORIGINAL_FINDING
    )
    counts_as_independent_proof: bool = True


@dataclass(frozen=True)
class TargetedNextAction:
    action_identity: str
    action_text: str
    scope_key: str  # object/op/event/shift — for deduplication
    suggested_clarification_role: Optional[SuggestedClarificationRole] = None
    linked_finding_identities: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    shared: bool = False


@dataclass(frozen=True)
class SharedContextRequirement:
    """One shared limitation/request with affected operations listed once."""

    shared_context_identity: str
    context_kind: SharedContextKind
    scope_key: str
    requirement_text: str
    affected_operation_identities: tuple[str, ...]
    affected_operation_names: tuple[str, ...]
    linked_finding_identities: tuple[str, ...] = ()
    suggested_clarification_role: Optional[SuggestedClarificationRole] = None
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationRecommendation:
    recommendation_identity: str
    project_code: str
    shift_reference: str
    source_operation_identity: str
    source_record_ids: tuple[str, ...]
    physical_object_reference: Optional[str]
    canonical_operation_identity: Optional[str]
    operation_code: Optional[str]
    original_operation_text: str
    execution_event_reference: Optional[str]
    original_claimed_quantity: Optional[float]
    original_quantity_unit: Optional[str]
    original_claimed_labor_man_minutes: Optional[float]
    scenario_direct_labor_cost_exact: Optional[str]
    applicable_requirement_references: tuple[str, ...]
    inherited_finding_references: tuple[InheritedFindingRef, ...]
    evidence_authority: RecommendationEvidenceAuthority
    unresolved_contradictions: tuple[str, ...]
    missing_context: tuple[str, ...]
    blocking_findings: tuple[str, ...]
    non_blocking_findings: tuple[str, ...]
    review_priority: ReviewPriority
    recommendation_status: RecommendationStatus
    professional_rationale: str
    recommended_next_actions: tuple[TargetedNextAction, ...]
    suggested_clarification_role: Optional[SuggestedClarificationRole]
    provenance: tuple[str, ...]
    recommendation_policy_version: str
    limitations: tuple[str, ...] = ()
    work_category: Optional[str] = None
    operation_specific_exception: bool = False
    shared_context_references: tuple[str, ...] = ()
    status_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatusLaborBucket:
    recommendation_status: RecommendationStatus
    operation_count: int
    labor_man_minutes: float
    scenario_direct_labor_cost_exact: Optional[str]


@dataclass(frozen=True)
class ShiftRecommendationSummary:
    shift_identity: str
    project_code: str
    work_date: str
    crew_id: str
    total_claimed_labor_man_minutes: Optional[float]
    target_productive_fund_man_minutes: Optional[float]
    mathematical_balance_status: str
    original_operation_count: int
    operation_recommendation_count: int
    recommendations_by_status: tuple[StatusLaborBucket, ...]
    unresolved_shift_level_findings: tuple[str, ...]
    material_blocking_findings: tuple[str, ...]
    evidence_coverage_limitations: tuple[str, ...]
    historical_context_limitations: tuple[str, ...]
    priority_review_items: tuple[str, ...]
    targeted_clarification_requests: tuple[str, ...]
    shift_level_recommendation: RecommendationStatus
    human_decision_required: bool
    scenario_direct_labor_cost_exact: Optional[str]
    explicit_limitations: tuple[str, ...]
    professional_conclusion: str
    shared_context_requirements: tuple[SharedContextRequirement, ...] = ()
    operation_specific_exception_identities: tuple[str, ...] = ()
    reachable_recommendation_statuses: tuple[str, ...] = ()
    reserved_recommendation_statuses: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShiftAcceptanceRecommendationArtifact:
    schema_version: str
    rules_version: str
    policy_version: str
    audit_id: str
    agent_code: str
    agent_version: str
    run_id: Optional[str]
    created_at_utc: str
    project_code: str
    work_date: str
    crew_id: str
    policy: RecommendationPolicy
    consolidated_findings: tuple[InheritedFindingRef, ...]
    operation_recommendations: tuple[OperationRecommendation, ...]
    shift_summary: ShiftRecommendationSummary
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    contractual_recognition_status: str
    commercial_acceptance_status: str
    payroll_decision_status: str
    disciplinary_decision_status: str
    human_decision_required: bool
    human_readable_summary: str
    s09_engine_status: str = "S09_ENGINE_IMPLEMENTED"
    operation_recommendation_generation_status: str = (
        "OPERATION_RECOMMENDATION_GENERATION_PROVEN"
    )
    shift_recommendation_generation_status: str = (
        "SHIFT_RECOMMENDATION_GENERATION_PROVEN"
    )
    finding_consolidation_status: str = "FINDING_CONSOLIDATION_PROVEN"
    labor_conservation_status: str = "LABOR_CONSERVATION_PROVEN"
    positive_physical_acceptance_recommendation_status: str = (
        "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN"
    )
    production_acceptance_policy_status: str = "PRODUCTION_ACCEPTANCE_POLICY_NOT_READY"
    production_acceptance_recommendation_status: str = (
        "PRODUCTION_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN"
    )
    managerial_acceptance_performed_status: str = "MANAGERIAL_ACCEPTANCE_PERFORMED_NO"
    contractual_recognition_performed_status: str = (
        "CONTRACTUAL_RECOGNITION_PERFORMED_NO"
    )
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"
    cost_deviation_engine_status: str = "COST_DEVIATION_ENGINE_IMPLEMENTED_NO"
    cost_deviation_boundaries_status: str = "COST_DEVIATION_BOUNDARIES_ONLY_YES"
    actual_incurred_cost_status: str = "ACTUAL_INCURRED_COST_NOT_PROVEN"
    s08_authority_ceiling_status: str = "AUTHORITY_CEILING_METADATA_VALIDATED"
    physical_execution_verified_status: str = "PHYSICAL_EXECUTION_VERIFIED_NO"
    evidence_content_validation_status: str = "EVIDENCE_CONTENT_VALIDATION_IMPLEMENTED_NO"
    geometric_overlap_engine_status: str = "GEOMETRIC_OVERLAP_ENGINE_IMPLEMENTED_NO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def demonstration_recommendation_policy(
    *,
    production_acceptance_requirements_available: bool = False,
) -> RecommendationPolicy:
    """Demonstration policy — never promoted to approved production authority."""
    if production_acceptance_requirements_available:
        authority = PolicyAuthority.PROJECT_ACCEPTANCE_POLICY
        established = True
        note = "caller_declared_production_requirements_available_still_requires_proof"
    else:
        authority = PolicyAuthority.DEMONSTRATION_POLICY
        established = False
        note = (
            "demonstration_recommendation_policy_not_approved_production_policy; "
            "PRODUCTION_ACCEPTANCE_REQUIREMENTS_NOT_ESTABLISHED"
        )
    return RecommendationPolicy(
        policy_identity="psaa.s09.demo_recommendation_policy",
        version=S09_DEMO_POLICY_VERSION,
        provenance=(
            "psaa.s09.demonstration_policy",
            "inherits_s01_s10_s02_s03_s11_s04_s05_s06_s07_s08",
        ),
        authority=authority,
        applicable_scope="DEMONSTRATION_FIXTURE_AND_TYPED_SUPPLIED_CONTEXT",
        required_professional_checks=(
            "S01_MATHEMATICAL_INTEGRITY",
            "S10_OPERATION_CLASSIFICATION",
            "S02_TECHNOLOGICAL_INTEGRITY",
            "S03_PHYSICAL_INTEGRITY",
            "S11_LABOR_BENCHMARK",
            "S04_EXECUTION_COST",
            "S05_TEMPORAL_INTEGRITY",
            "S06_STATISTICAL_ANOMALY",
            "S07_ROOT_CAUSE",
            "S08_EVIDENCE_VALIDATION",
        ),
        blocking_criteria=(
            "S01_INCOHERENT_ARITHMETIC",
            "S03_INVALID_QUANTITY",
            "S08_EVIDENCE_MISSING_WHEN_REQUIREMENT_APPLICABLE",
            "S08_PHYSICAL_EXECUTION_NOT_VERIFIED_BLOCKS_POSITIVE_PHYSICAL",
            "PRODUCTION_ACCEPTANCE_REQUIREMENTS_NOT_ESTABLISHED_BLOCKS_POSITIVE",
        ),
        non_blocking_criteria=(
            "S02_DEMONSTRATION_FINDING_WITHOUT_PRODUCTION_AUTHORITY",
            "S06_STATISTICAL_ANOMALY_CANDIDATE",
            "S08_POTENTIAL_DUPLICATE_CLAIM",
            "S08_POTENTIAL_QUANTITY_EXCESS",
            "S07_HYPOTHESIS_NOT_ESTABLISHED_CAUSE",
            "DESCRIPTIVE_OBSERVATION",
        ),
        missing_context_treatment=(
            "MISSING_CONTEXT_PRESERVES_UNCERTAINTY_NOT_ZERO_HISTORY_NOT_NON_EXECUTION"
        ),
        allows_positive_physical_acceptance=False,
        production_acceptance_requirements_established=established,
        source_note=note,
    )
