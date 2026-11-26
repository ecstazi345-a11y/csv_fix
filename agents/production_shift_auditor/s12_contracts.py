"""PSAA S12 — Production Intelligence contracts.

CLAIMED OBSERVATION ≠ VERIFIED KNOWLEDGE.
AUDITED OBSERVATION ≠ VERIFIED PHYSICAL OBSERVATION.
REPEATED OBSERVATION ≠ APPROVED NORM.
KNOWLEDGE CANDIDATE ≠ APPROVED PRODUCTION KNOWLEDGE.
Does not create learning platforms, mutate norms, or approve knowledge.
Serializable; durable history schema unchanged in this increment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S12_RULES_VERSION = "psaa.s12.production_intelligence.v0.1"
S12_ARTIFACT_SCHEMA_VERSION = "shift_production_intelligence.v0.1"
S12_POLICY_VERSION = "psaa.s12.observation_policy.v0.1"


class ObservationAuthorityLayer(str, Enum):
    """Knowledge authority layers — no automatic linear escalation."""

    RAW_CLAIMED_OBSERVATION = "RAW_CLAIMED_OBSERVATION"
    MATHEMATICALLY_ASSESSED_OBSERVATION = "MATHEMATICALLY_ASSESSED_OBSERVATION"
    PROFESSIONALLY_AUDITED_OBSERVATION = "PROFESSIONALLY_AUDITED_OBSERVATION"
    VERIFIED_PHYSICAL_OBSERVATION = "VERIFIED_PHYSICAL_OBSERVATION"  # reserved
    HUMAN_ACCEPTANCE_DECISION = "HUMAN_ACCEPTANCE_DECISION"  # only if trusted supplied
    REUSABLE_KNOWLEDGE_CANDIDATE = "REUSABLE_KNOWLEDGE_CANDIDATE"
    APPROVED_PRODUCTION_KNOWLEDGE = "APPROVED_PRODUCTION_KNOWLEDGE"  # never auto
    APPROVED_PRODUCTION_LABOR_NORM = "APPROVED_PRODUCTION_LABOR_NORM"  # never auto


class ReuseEligibility(str, Enum):
    """Aligned with S11 eligibility — S12 references S11, does not re-decide UL."""

    RETAIN_AS_CLAIMED_OBSERVATION = "RETAIN_AS_CLAIMED_OBSERVATION"
    REQUIRES_ADDITIONAL_CONTEXT = "REQUIRES_ADDITIONAL_CONTEXT"
    ELIGIBLE_FOR_EXPLORATORY_COMPARISON = "ELIGIBLE_FOR_EXPLORATORY_COMPARISON"
    EXCLUDED_FROM_BENCHMARK_USE = "EXCLUDED_FROM_BENCHMARK_USE"
    KNOWLEDGE_CANDIDATE_WITH_LIMITATIONS = "KNOWLEDGE_CANDIDATE_WITH_LIMITATIONS"
    VERIFIED_REUSE_ELIGIBILITY_NOT_ESTABLISHED = (
        "VERIFIED_REUSE_ELIGIBILITY_NOT_ESTABLISHED"
    )


class KnowledgeCandidateType(str, Enum):
    UNIT_LABOR_OBSERVATION = "UNIT_LABOR_OBSERVATION"
    EXECUTION_CONDITION_OBSERVATION = "EXECUTION_CONDITION_OBSERVATION"
    TECHNOLOGICAL_CONTEXT_OBSERVATION = "TECHNOLOGICAL_CONTEXT_OBSERVATION"
    PHYSICAL_COMPLEXITY_OBSERVATION = "PHYSICAL_COMPLEXITY_OBSERVATION"
    CONSTRAINT_OCCURRENCE_OBSERVATION = "CONSTRAINT_OCCURRENCE_OBSERVATION"
    REWORK_OR_QUALITY_OBSERVATION = "REWORK_OR_QUALITY_OBSERVATION"
    REPORTING_QUALITY_OBSERVATION = "REPORTING_QUALITY_OBSERVATION"
    ECONOMIC_SCENARIO_OBSERVATION = "ECONOMIC_SCENARIO_OBSERVATION"


class SuggestedReusePurpose(str, Enum):
    FUTURE_LABOR_ESTIMATION = "FUTURE_LABOR_ESTIMATION"
    FUTURE_PLANNING = "FUTURE_PLANNING"
    EXPLORATORY_PRODUCTIVITY_ANALYSIS = "EXPLORATORY_PRODUCTIVITY_ANALYSIS"
    ENGINEERING_CONTEXT_REVIEW = "ENGINEERING_CONTEXT_REVIEW"
    CONSTRAINT_INVESTIGATION = "CONSTRAINT_INVESTIGATION"
    COST_SCENARIO_RESEARCH = "COST_SCENARIO_RESEARCH"
    REPORTING_QUALITY_IMPROVEMENT = "REPORTING_QUALITY_IMPROVEMENT"


class SuggestedConsumerRole(str, Enum):
    """Suggested consumer — NOT agent handoff / authorization."""

    CONSTRUCTOR_AGENT = "CONSTRUCTOR_AGENT"
    PLANNING_AGENT = "PLANNING_AGENT"
    CONSTRAINT_AGENT = "CONSTRAINT_AGENT"
    PRODUCTION_SHIFT_AUDITOR = "PRODUCTION_SHIFT_AUDITOR"
    COST_ENGINEERING = "COST_ENGINEERING"


@dataclass(frozen=True)
class SuppliedHumanDecisionRef:
    """Caller-supplied trusted historical human decision — never invented by S12."""

    decision_identity: str
    project_code: str
    decision_scope: str
    decision_authority: str
    decision_version: str
    applicable_event_identity: Optional[str] = None
    source_operation_identity: Optional[str] = None
    provenance: tuple[str, ...] = ()
    source_note: str = "caller_supplied_historical_human_decision"
    trusted: bool = False  # untrusted flags do not grant authority


@dataclass(frozen=True)
class ProductionObservation:
    """Minimal typed production observation — references prior skills, no UL recompute."""

    observation_identity: str
    project_code: str
    shift_reference: str
    execution_event_reference: Optional[str]
    source_operation_identity: str
    source_record_ids: tuple[str, ...]
    source_version: Optional[str]
    physical_object_reference: Optional[str]
    canonical_operation_identity: Optional[str]
    operation_code: Optional[str]
    original_operation_text: str
    work_category: Optional[str]
    claimed_result_state: Optional[str]
    claimed_quantity: Optional[float]
    quantity_unit: Optional[str]
    claimed_labor_man_minutes: Optional[float]
    labor_semantics: Optional[str]
    s11_finding_identity: Optional[str]
    unit_labor_man_minutes_per_physical: Optional[float]
    s11_calculation_status: Optional[str]
    s11_observation_eligibility: Optional[str]
    s11_comparability_status: Optional[str]
    material_context: Optional[str]
    geometry_context: Optional[str]
    technology_context: Optional[str]
    execution_conditions: Optional[str]
    temporal_context: Optional[str]
    evidence_references: tuple[str, ...]
    evidence_authority: str
    professional_audit_references: tuple[str, ...]
    s09_recommendation_identity: Optional[str]
    s09_recommendation_status: Optional[str]
    human_decision_reference: Optional[str]
    authority_layer: ObservationAuthorityLayer
    reuse_eligibility: ReuseEligibility
    missing_context: tuple[str, ...]
    limitations: tuple[str, ...]
    provenance: tuple[str, ...]
    policy_version: str = S12_POLICY_VERSION


@dataclass(frozen=True)
class KnowledgeCandidate:
    candidate_identity: str
    candidate_type: KnowledgeCandidateType
    linked_observation_identities: tuple[str, ...]
    source_operation_identity: Optional[str]
    operation_code: Optional[str]
    evidence_authority: str
    reuse_eligibility: ReuseEligibility
    suggested_reuse_purposes: tuple[SuggestedReusePurpose, ...]
    suggested_consumer_roles: tuple[SuggestedConsumerRole, ...]
    professional_basis: tuple[str, ...]
    limitations: tuple[str, ...]
    provenance: tuple[str, ...]
    approved_knowledge_status: str = "APPROVED_PRODUCTION_KNOWLEDGE_NOT_CREATED"
    approved_labor_norm_status: str = "APPROVED_PRODUCTION_LABOR_NORM_NOT_CREATED"
    handoff_status: str = "NO_AGENT_HANDOFF"


@dataclass(frozen=True)
class ShiftProductionIntelligenceSummary:
    source_operation_count: int
    distinct_observation_count: int
    unit_labor_observation_count: int
    computable_unit_labor_man_minutes: float
    labor_without_computable_unit_metrics_man_minutes: float
    total_claimed_labor_man_minutes: Optional[float]
    scenario_direct_labor_cost_exact: Optional[str]
    knowledge_candidate_count: int
    candidate_type_counts: tuple[tuple[str, int], ...]
    excluded_from_benchmark_count: int
    requires_additional_context_count: int
    verified_knowledge_count: int
    approved_knowledge_count: int
    approved_labor_norm_count: int
    missing_context_notes: tuple[str, ...]
    professional_conclusion: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftProductionIntelligenceArtifact:
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
    observations: tuple[ProductionObservation, ...]
    knowledge_candidates: tuple[KnowledgeCandidate, ...]
    shift_summary: ShiftProductionIntelligenceSummary
    observations_notes: tuple[str, ...]
    managerial_acceptance_status: str
    contractual_recognition_status: str
    payroll_decision_status: str
    norm_mutation_status: str
    knowledge_approval_status: str
    autonomous_learning_status: str
    persistence_status: str
    human_readable_summary: str
    s12_engine_status: str = "S12_ENGINE_IMPLEMENTED"
    structured_observation_generation_status: str = (
        "STRUCTURED_OBSERVATION_GENERATION_PROVEN"
    )
    knowledge_candidate_generation_status: str = (
        "KNOWLEDGE_CANDIDATE_GENERATION_PROVEN"
    )
    s11_reuse_eligibility_integration_status: str = (
        "S11_REUSE_ELIGIBILITY_INTEGRATION_PROVEN"
    )
    observation_identity_handling_status: str = "OBSERVATION_IDENTITY_HANDLING_PROVEN"
    labor_conservation_status: str = "LABOR_CONSERVATION_PROVEN"
    verified_production_knowledge_generation_status: str = (
        "VERIFIED_PRODUCTION_KNOWLEDGE_GENERATION_NOT_PROVEN"
    )
    approved_production_knowledge_created_status: str = (
        "APPROVED_PRODUCTION_KNOWLEDGE_CREATED_NO"
    )
    approved_production_labor_norm_created_status: str = (
        "APPROVED_PRODUCTION_LABOR_NORM_CREATED_NO"
    )
    production_knowledge_persistence_status: str = (
        "PRODUCTION_KNOWLEDGE_PERSISTENCE_IMPLEMENTED_NO"
    )
    autonomous_learning_implemented_status: str = "AUTONOMOUS_LEARNING_IMPLEMENTED_NO"
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"
    cost_deviation_engine_status: str = "COST_DEVIATION_ENGINE_IMPLEMENTED_NO"
    cost_deviation_boundaries_status: str = "COST_DEVIATION_BOUNDARIES_ONLY_YES"
    actual_incurred_cost_status: str = "ACTUAL_INCURRED_COST_NOT_PROVEN"
    s08_authority_ceiling_status: str = "AUTHORITY_CEILING_METADATA_VALIDATED"
    physical_execution_verified_status: str = "PHYSICAL_EXECUTION_VERIFIED_NO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
