"""PSAA S06 — Statistical Anomaly Detection contracts.

DESCRIPTIVE OBSERVATION ≠ STATISTICAL ANOMALY ≠ PROVEN VIOLATION.
Does not invent norms, remove observations, or assign fraud/payroll outcomes.
Serializable; durable history schema unchanged in this increment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S06_RULES_VERSION = "psaa.s06.statistical_anomaly.v0.1"
S06_ARTIFACT_SCHEMA_VERSION = "shift_statistical_anomaly.v0.1"


class StatisticalSignalStatus(str, Enum):
    DESCRIPTIVE_OBSERVATION = "DESCRIPTIVE_OBSERVATION"
    THRESHOLD_EXCEEDANCE = "THRESHOLD_EXCEEDANCE"
    STATISTICAL_ANOMALY_CANDIDATE = "STATISTICAL_ANOMALY_CANDIDATE"
    INSUFFICIENT_COMPARABLE_HISTORY = "INSUFFICIENT_COMPARABLE_HISTORY"
    REFERENCE_NOT_AVAILABLE = "REFERENCE_NOT_AVAILABLE"
    REFERENCE_NOT_COMPARABLE = "REFERENCE_NOT_COMPARABLE"
    ZERO_DISPERSION = "ZERO_DISPERSION"
    REPORTING_PRECISION_UNKNOWN = "REPORTING_PRECISION_UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VIOLATION_NOT_PROVEN = "VIOLATION_NOT_PROVEN"
    INHERITED_PROFESSIONAL_FINDING = "INHERITED_PROFESSIONAL_FINDING"
    NOT_EVALUATED = "NOT_EVALUATED"


class SignalType(str, Enum):
    LABOR_CONCENTRATION = "LABOR_CONCENTRATION"
    ROUNDING_PATTERN = "ROUNDING_PATTERN"
    REPEATED_VALUE = "REPEATED_VALUE"
    UNIT_LABOR_DEVIATION = "UNIT_LABOR_DEVIATION"
    COST_DEVIATION = "COST_DEVIATION"
    TEMPORAL_SIGNAL = "TEMPORAL_SIGNAL"
    INHERITED_FINDING = "INHERITED_FINDING"
    SAMPLE_INTEGRITY = "SAMPLE_INTEGRITY"


class EvidenceAuthority(str, Enum):
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    CONFIGURED_THRESHOLD = "CONFIGURED_THRESHOLD"
    COMPARABLE_HISTORICAL_SAMPLE = "COMPARABLE_HISTORICAL_SAMPLE"
    INHERITED_FROM_PRIOR_SKILL = "INHERITED_FROM_PRIOR_SKILL"
    # Never assigned by S06 for automatic proven violation:
    PROVEN_VIOLATION = "PROVEN_VIOLATION"


class ReviewPriority(str, Enum):
    INFORMATION = "INFORMATION"
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    # Managerial urgency ≠ evidence strength
    HIGH_REVIEW_PRIORITY = "HIGH_REVIEW_PRIORITY"


class StatisticalMethod(str, Enum):
    DESCRIPTIVE_SHARE = "DESCRIPTIVE_SHARE"
    DIVISIBILITY_COUNT = "DIVISIBILITY_COUNT"
    VALUE_FREQUENCY = "VALUE_FREQUENCY"
    MEDIAN_MAD_MODIFIED_Z = "MEDIAN_MAD_MODIFIED_Z"
    EXPLICIT_THRESHOLD_COMPARISON = "EXPLICIT_THRESHOLD_COMPARISON"
    INHERITED = "INHERITED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ReportingPrecisionPolicy:
    """Caller-declared reporting precision — never invented as universal law."""

    step_minutes: Optional[int] = None
    authority: str = "REPORTING_PRECISION_UNKNOWN"
    version: str = "unspecified"
    source_note: str = "caller_supplied_reporting_precision_policy"


@dataclass(frozen=True)
class StatisticalThresholdConfig:
    """Explicit thresholds with source/version — demonstration ≠ production norm."""

    config_identity: str = "psaa.s06.demo_thresholds.v0.1"
    version: str = "v0.1"
    min_sample_size: int = 5
    mad_modified_z_threshold: float = 3.5
    # Optional share thresholds for THRESHOLD_EXCEEDANCE (not automatic violation)
    top1_share_review_pct: Optional[float] = None
    top3_share_review_pct: Optional[float] = None
    unit_labor_share_of_median_review: Optional[float] = None  # e.g. 2.0 = 200% of median
    # Optional explicit absolute |observed-median| gate when MAD=0 (must be >0 if set)
    zero_dispersion_absolute_deviation_threshold: Optional[float] = None
    authority: str = "DEMONSTRATION_THRESHOLD"
    source_note: str = (
        "demonstration_threshold_not_universal_production_norm; "
        "not approved labor/cost standard"
    )


@dataclass(frozen=True)
class StatisticalReferenceObservation:
    """Typed historical unit-labor observation for S06 reference sample.

    Default sample class is claimed historical — not verified execution proof.
    """

    observation_identity: str
    operation_code: str
    unit_labor_man_minutes_per_physical: float
    physical_unit: str
    project_code: Optional[str] = None
    material_hint: Optional[str] = None
    geometry_hint: Optional[str] = None
    technology_hint: Optional[str] = None
    result_state: Optional[str] = None
    labor_semantics: Optional[str] = None
    execution_conditions_hint: Optional[str] = None
    observation_date: Optional[str] = None  # ISO date; future dates blocked unless allowed
    source_record_identity: Optional[str] = None  # logical source; versions collapse
    source_record_version: Optional[str] = None
    sample_claim_status: str = "CLAIMED_HISTORICAL_SAMPLE"  # ≠ VERIFIED
    source_note: str = "caller_supplied_statistical_reference"


@dataclass(frozen=True)
class StatisticalAnomalySignal:
    signal_identity: str
    signal_type: SignalType
    status: StatisticalSignalStatus
    source_observation_identities: tuple[str, ...]
    canonical_operation_code: Optional[str]
    canonical_operation_name: Optional[str]
    metric: str
    observed_value: Optional[float]
    reference_value: Optional[float]
    sample_size: Optional[int]
    statistical_method: StatisticalMethod
    threshold_reference: Optional[str]
    threshold_authority: Optional[str]
    comparability_status: str
    evidence_authority: EvidenceAuthority
    deviation_value: Optional[float]
    review_priority: ReviewPriority
    limitations: tuple[str, ...]
    provenance: tuple[str, ...]
    rules_version: str
    professional_conclusion: str
    clarification_question: Optional[str]


@dataclass(frozen=True)
class ConcentrationSummary:
    total_claimed_labor_man_minutes: Optional[float]
    maximum_man_minutes: Optional[float]
    minimum_man_minutes: Optional[float]
    maximum_operation_names: tuple[str, ...]
    minimum_operation_names: tuple[str, ...]
    top1_share_pct: Optional[float]
    top3_share_pct: Optional[float]
    top4_share_pct: Optional[float]
    top1_operation_names: tuple[str, ...]
    top3_operation_names: tuple[str, ...]
    top4_operation_names: tuple[str, ...]
    top3_tie_note: Optional[str]
    remaining_after_top3_man_minutes: Optional[float]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class RoundingSummary:
    observation_count: int
    divisible_by_5_count: int
    divisible_by_10_count: int
    reporting_precision_step_minutes: Optional[int]
    reporting_precision_authority: str
    pattern_status: StatisticalSignalStatus
    notes: tuple[str, ...]


@dataclass(frozen=True)
class RepeatedValueSummary:
    distinct_values: int
    repeated_values: tuple[tuple[float, int], ...]  # (value, count) count>=2
    status: StatisticalSignalStatus
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftStatisticalSummary:
    concentration: ConcentrationSummary
    rounding: RoundingSummary
    repeated_values: RepeatedValueSummary
    comparable_reference_coverage: str
    unresolved_context: tuple[str, ...]
    inherited_finding_count: int
    total_original_labor_man_minutes: Optional[float]
    professional_conclusion: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftStatisticalAnomalyArtifact:
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
    signals: tuple[StatisticalAnomalySignal, ...]
    shift_summary: ShiftStatisticalSummary
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    payroll_decision_status: str
    disciplinary_decision_status: str
    fraud_classification_status: str
    human_readable_summary: str
    s06_engine_status: str = "S06_ENGINE_IMPLEMENTED"
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"
    production_history_adapter_status: str = "NOT_IMPLEMENTED_USE_TYPED_REFERENCES"
    # Cost path reuses S04 boundaries; not a full cost-anomaly engine:
    cost_deviation_readiness: str = "COST_DEVIATION_BOUNDARIES_ONLY"
    production_cost_deviation_status: str = "PRODUCTION_COST_DEVIATION_NOT_PROVEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
