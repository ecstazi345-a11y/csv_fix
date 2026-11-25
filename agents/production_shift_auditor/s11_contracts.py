"""PSAA S11 — Labor Benchmark & Observation Eligibility contracts.

CLAIMED UNIT LABOR ≠ VERIFIED UNIT LABOR ≠ APPROVED LABOR NORM.
Does not mutate Labor Norm Library. Does not invent benchmarks.
Serializable for future durable history (persist not in this increment).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S11_RULES_VERSION = "psaa.s11.labor_benchmark.v0.1"
S11_ARTIFACT_SCHEMA_VERSION = "shift_labor_benchmark.v0.1"


class LaborCalculationStatus(str, Enum):
    COMPUTABLE_CLAIMED_OBSERVATION = "COMPUTABLE_CLAIMED_OBSERVATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"
    COMPOSITE_NOT_ALLOCATABLE = "COMPOSITE_NOT_ALLOCATABLE"
    UNIT_LABOR_NOT_COMPUTABLE = "UNIT_LABOR_NOT_COMPUTABLE"
    LABOR_WITHOUT_POSITIVE_QUANTITY = "LABOR_WITHOUT_POSITIVE_QUANTITY"


class ObservationEligibility(str, Enum):
    HISTORICAL_ANALYSIS_CANDIDATE = "HISTORICAL_ANALYSIS_CANDIDATE"
    NOT_ELIGIBLE_FOR_BENCHMARK = "NOT_ELIGIBLE_FOR_BENCHMARK"
    COMPUTABLE_BUT_CLAIMED_ONLY = "COMPUTABLE_BUT_CLAIMED_ONLY"
    NOT_EVALUATED = "NOT_EVALUATED"


class ComparabilityStatus(str, Enum):
    """Full engineering comparability is separate from arithmetic computability."""

    FULL_COMPARABILITY_NOT_PROVEN = "FULL_COMPARABILITY_NOT_PROVEN"
    COMPARABILITY_CONTEXT_INCOMPLETE = "COMPARABILITY_CONTEXT_INCOMPLETE"
    BUCKET_COMPARABLE_WITH_LIMITATIONS = "BUCKET_COMPARABLE_WITH_LIMITATIONS"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BenchmarkAuthorityStatus(str, Enum):
    """Injected reference authority — never auto-promoted to approved norm."""

    EXTERNAL_REFERENCE_UNVERIFIED = "EXTERNAL_REFERENCE_UNVERIFIED"
    BENCHMARK_CANDIDATE = "BENCHMARK_CANDIDATE"
    HISTORICAL_OBSERVATION_ONLY = "HISTORICAL_OBSERVATION_ONLY"
    APPROVED_PRODUCTION_NORM = "APPROVED_PRODUCTION_NORM"
    UNKNOWN = "UNKNOWN"


class BenchmarkComparisonStatus(str, Enum):
    BENCHMARK_NOT_AVAILABLE = "BENCHMARK_NOT_AVAILABLE"
    BENCHMARK_COMPARISON_NOT_APPLICABLE = "BENCHMARK_COMPARISON_NOT_APPLICABLE"
    BENCHMARK_COMPARED_CLAIMED_ONLY = "BENCHMARK_COMPARED_CLAIMED_ONLY"
    BENCHMARK_INCOMPATIBLE = "BENCHMARK_INCOMPATIBLE"


@dataclass(frozen=True)
class BenchmarkReference:
    """Optional existing benchmark/norm — never invented by S11.

    EXTERNAL REFERENCE ≠ APPROVED PRODUCTION NORM unless authority_status
    explicitly says APPROVED_PRODUCTION_NORM *and* caller proves it.
    S11 still never mutates norms and never treats inject as auto-approved.
    """

    operation_code: str
    unit_labor_man_hours_per_physical: float
    physical_unit: str
    source_id: str
    source_version: str
    applicability_note: str = ""
    material_hint: Optional[str] = None
    result_state: Optional[str] = None
    geometry_hint: Optional[str] = None
    physical_characteristic_hint: Optional[str] = None
    technology_hint: Optional[str] = None
    labor_semantics: Optional[str] = None
    execution_conditions_hint: Optional[str] = None
    project_scope: Optional[str] = None
    provenance_note: str = "caller_injected_read_only_reference"
    authority_status: BenchmarkAuthorityStatus = (
        BenchmarkAuthorityStatus.EXTERNAL_REFERENCE_UNVERIFIED
    )
    approval_status: str = "NOT_AUTO_APPROVED_BY_S11"


@dataclass(frozen=True)
class HistoricalLaborObservation:
    """Comparable prior observation supplied by caller for aggregation only."""

    operation_code: str
    eligible_labor_man_minutes: float
    physical_quantity: float
    physical_unit: str
    material_hint: Optional[str] = None
    claimed_result_state: Optional[str] = None
    source_note: str = "caller_supplied_comparable_observation"
    observation_identity: Optional[str] = None
    project_code: Optional[str] = None
    geometry_hint: Optional[str] = None
    physical_characteristic_hint: Optional[str] = None
    technology_hint: Optional[str] = None
    labor_semantics: Optional[str] = None
    execution_conditions_hint: Optional[str] = None
    source_record_version: Optional[str] = None


@dataclass(frozen=True)
class LaborObservationFinding:
    check_identity: str
    source_operation_identity: str
    original_operation_text: str
    canonical_operation_code: Optional[str]
    canonical_operation_name: Optional[str]
    original_claimed_labor_quantity: Optional[float]
    original_labor_unit: Optional[str]
    labor_semantics: Optional[str]
    eligible_labor_man_minutes: Optional[float]
    eligible_labor_man_hours: Optional[float]
    original_claimed_physical_quantity: Optional[float]
    original_measurement_unit: Optional[str]
    claimed_result_state: Optional[str]
    unit_labor_man_minutes_per_physical: Optional[float]
    unit_labor_man_hours_per_physical: Optional[float]
    productivity_per_man_hour: Optional[float]
    calculation_status: LaborCalculationStatus
    observation_eligibility: ObservationEligibility
    eligibility_reasons: tuple[str, ...]
    comparability_status: ComparabilityStatus
    comparability_limitations: tuple[str, ...]
    evidence_status: str
    benchmark_comparison_status: BenchmarkComparisonStatus
    benchmark_reference_id: Optional[str]
    benchmark_unit_labor_man_hours: Optional[float]
    benchmark_deviation_pct: Optional[float]
    benchmark_authority_status: Optional[str]
    labor_without_quantity_category: Optional[str]
    provenance: tuple[str, ...]
    rules_version: str
    professional_conclusion: str
    clarification_request: Optional[str]
    # Never rewritten
    preserved_claimed_labor_quantity: Optional[float] = None
    preserved_physical_quantity: Optional[float] = None


@dataclass(frozen=True)
class LaborConservationSummary:
    """Partition of claimed labor — categories are mutually exclusive."""

    total_claimed_labor_man_minutes: float
    labor_with_computable_unit_indicators_man_minutes: float
    labor_without_computable_unit_indicators_man_minutes: float
    preserved_total_man_minutes: float
    conservation_holds: bool
    categories_mutually_exclusive: bool
    labor_without_unit_ne_automatic_losses: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalAggregationSummary:
    operation_code: str
    physical_unit: str
    observation_count: int
    total_quantity: float
    total_eligible_labor_man_minutes: float
    individual_unit_labor_man_minutes: tuple[float, ...]
    quantity_weighted_unit_labor_man_minutes: Optional[float]
    quantity_weighted_unit_labor_man_hours: Optional[float]
    minimum_unit_labor_man_minutes: Optional[float]
    maximum_unit_labor_man_minutes: Optional[float]
    median_unit_labor_man_minutes: Optional[float]
    included_observation_identities: tuple[str, ...]
    excluded_or_non_comparable_count: int
    unresolved_eligibility_notes: tuple[str, ...]
    comparability_status: ComparabilityStatus
    sample_limitations: tuple[str, ...]
    approved_norm_status: str  # always NOT_AN_APPROVED_NORM for S11 aggregates
    benchmark_authority_note: str = "AGGREGATE_IS_NOT_BENCHMARK_AUTHORITY"


@dataclass(frozen=True)
class ShiftLaborBenchmarkArtifact:
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
    findings: tuple[LaborObservationFinding, ...]
    aggregations: tuple[HistoricalAggregationSummary, ...]
    labor_conservation: LaborConservationSummary
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    norm_mutation_status: str
    payroll_decision_status: str
    commercial_recognition_status: str
    human_readable_summary: str
    s11_engine_status: str = "S11_ENGINE_IMPLEMENTED"
    claimed_metrics_status: str = "CLAIMED_UNIT_LABOR_COMPUTABLE_WHEN_DATA_ALLOWS"
    verified_observation_status: str = "VERIFIED_OBSERVATIONS_NOT_PROVEN"
    approved_norm_status: str = "APPROVED_LABOR_NORMS_NOT_CREATED"
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"
    production_labor_norm_read_adapter_status: str = "NOT_IMPLEMENTED_LIMITATION"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
