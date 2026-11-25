"""PSAA S04 — Execution Cost Analysis contracts (direct labor cost only).

CLAIMED LABOR COST ≠ INCURRED ACTUAL COST.
SCENARIO RATE ≠ APPROVED COST RATE.
DIRECT LABOR COST ≠ FULL EXECUTION COST.
Does not mutate rates, payroll, contracts, or revenue.
Serializable; durable history schema unchanged in this increment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S04_RULES_VERSION = "psaa.s04.execution_cost.v0.1"
S04_ARTIFACT_SCHEMA_VERSION = "shift_execution_cost.v0.1"

# Monetary policy: Decimal arithmetic; display/settle round HALF_UP to 0.01.
# Exact (pre-round) values retained for conservation / reconciliation.
S04_MONEY_QUANTUM = "0.01"
S04_EXACT_QUANTUM = "0.0001"
S04_ROUNDING = "ROUND_HALF_UP"


class CostRateAuthority(str, Enum):
    SCENARIO_RATE = "SCENARIO_RATE"
    BUDGET_RATE = "BUDGET_RATE"
    APPROVED_COST_RATE = "APPROVED_COST_RATE"
    OBSERVED_COST_RATE = "OBSERVED_COST_RATE"
    UNKNOWN_RATE_AUTHORITY = "UNKNOWN_RATE_AUTHORITY"


class CostRateEconomicType(str, Enum):
    WAGE_RATE = "WAGE_RATE"
    EMPLOYER_DIRECT_LABOR_COST_RATE = "EMPLOYER_DIRECT_LABOR_COST_RATE"
    FULLY_BURDENED_LABOR_COST_RATE = "FULLY_BURDENED_LABOR_COST_RATE"
    CONTRACT_UNIT_PRICE = "CONTRACT_UNIT_PRICE"
    UNKNOWN_RATE_TYPE = "UNKNOWN_RATE_TYPE"


class CostRateUnit(str, Enum):
    PER_MAN_HOUR = "PER_MAN_HOUR"
    PER_MAN_MINUTE = "PER_MAN_MINUTE"
    UNKNOWN = "UNKNOWN"


class CostCalculationStatus(str, Enum):
    SCENARIO_COST_COMPUTED = "SCENARIO_COST_COMPUTED"
    ESTIMATED_COST_COMPUTED = "ESTIMATED_COST_COMPUTED"
    COST_RATE_NOT_AVAILABLE = "COST_RATE_NOT_AVAILABLE"
    COST_RATE_NOT_APPLICABLE = "COST_RATE_NOT_APPLICABLE"
    LABOR_SEMANTICS_UNPROVEN = "LABOR_SEMANTICS_UNPROVEN"
    UNIT_COST_NOT_COMPUTABLE = "UNIT_COST_NOT_COMPUTABLE"
    COMPOSITE_COST_UNALLOCATED = "COMPOSITE_COST_UNALLOCATED"
    INVALID_INPUT = "INVALID_INPUT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class CostCompleteness(str, Enum):
    FULL_MONETIZED = "FULL_MONETIZED"
    PARTIAL_COST_COVERAGE = "PARTIAL_COST_COVERAGE"
    NONE_MONETIZED = "NONE_MONETIZED"
    NOT_EVALUATED = "NOT_EVALUATED"


class ActualCostVerificationStatus(str, Enum):
    ACTUAL_COST_NOT_PROVEN = "ACTUAL_COST_NOT_PROVEN"
    ACTUAL_COST_CLAIMED_ONLY = "ACTUAL_COST_CLAIMED_ONLY"
    # Never assigned without evidence in S04 v0.1
    VERIFIED_ACTUAL_COST = "VERIFIED_ACTUAL_COST"


@dataclass(frozen=True)
class LaborCostRateReference:
    """Caller-injected typed cost rate — never invented by S04.

    Production cost-rate READ adapter is NOT implemented; inject explicitly.
    """

    rate_identity: str
    rate_value: str  # Decimal-compatible string
    currency: str
    rate_unit: CostRateUnit
    rate_authority: CostRateAuthority
    economic_type: CostRateEconomicType
    provenance: str
    version: str
    included_cost_components: tuple[str, ...] = ("direct_labor",)
    excluded_cost_components: tuple[str, ...] = (
        "materials",
        "equipment",
        "subcontract",
        "site_overhead",
        "general_overhead",
        "payroll_accruals",
        "contract_price",
        "margin",
    )
    applicable_project_scope: Optional[str] = None
    applicable_labor_category: Optional[str] = None
    valid_from: Optional[str] = None  # YYYY-MM-DD inclusive
    valid_to: Optional[str] = None  # YYYY-MM-DD inclusive
    applicability_note: str = ""


@dataclass(frozen=True)
class OperationCostFinding:
    check_identity: str
    source_operation_identity: str
    original_operation_text: str
    canonical_operation_code: Optional[str]
    canonical_operation_name: Optional[str]
    original_claimed_labor_quantity: Optional[float]
    original_labor_unit: Optional[str]
    labor_semantics: Optional[str]
    labor_man_minutes: Optional[str]  # Decimal string
    labor_man_hours: Optional[str]
    original_physical_quantity: Optional[float]
    measurement_unit: Optional[str]
    applied_rate_identity: Optional[str]
    cost_rate_authority: Optional[str]
    cost_rate_economic_type: Optional[str]
    included_cost_components: tuple[str, ...]
    computed_direct_labor_cost_exact: Optional[str]
    computed_direct_labor_cost_rounded: Optional[str]
    computed_unit_labor_cost_exact: Optional[str]
    computed_unit_labor_cost_rounded: Optional[str]
    currency: Optional[str]
    calculation_status: CostCalculationStatus
    cost_completeness: CostCompleteness
    has_computable_unit_cost: bool
    authority_limitations: tuple[str, ...]
    evidence_status: str
    labor_category_note: str  # claimed / productive / paid / etc. — descriptive only
    provenance: tuple[str, ...]
    rules_version: str
    professional_conclusion: str
    clarification_request: Optional[str]
    preserved_claimed_labor_quantity: Optional[float] = None
    preserved_physical_quantity: Optional[float] = None


@dataclass(frozen=True)
class CostConservationSummary:
    total_claimed_labor_man_minutes: str
    monetized_labor_man_minutes: str
    non_monetized_labor_man_minutes: str
    total_calculated_direct_labor_cost_exact: Optional[str]
    total_calculated_direct_labor_cost_rounded: Optional[str]
    cost_with_computable_unit_indicators_exact: Optional[str]
    cost_without_computable_unit_indicators_exact: Optional[str]
    currency: Optional[str]
    conservation_holds: bool
    categories_mutually_exclusive: bool
    calculation_completeness: CostCompleteness
    line_sum_rounded: Optional[str]
    total_vs_line_sum_residual_rounded: Optional[str]
    reconciliation_note: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class ShiftExecutionCostArtifact:
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
    findings: tuple[OperationCostFinding, ...]
    cost_conservation: CostConservationSummary
    applied_rate_summary: Optional[str]
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    payroll_decision_status: str
    commercial_recognition_status: str
    cost_rate_mutation_status: str
    contract_price_mutation_status: str
    actual_cost_verification_status: ActualCostVerificationStatus
    full_execution_cost_status: str
    margin_status: str
    revenue_status: str
    human_readable_summary: str
    monetary_rounding_policy: str = (
        f"Decimal; working quantum={S04_EXACT_QUANTUM} (limited precision, "
        f"not exact periodic fractions); money quantum={S04_MONEY_QUANTUM}; "
        f"{S04_ROUNDING}; residual not hidden/redistributed"
    )
    multi_rate_allocation_status: str = (
        "PER_OPERATION_CATEGORY_OR_SHIFT_WIDE_SELECTION; "
        "NO_CROSS_WORKER_LABOR_ALLOCATION; "
        "NOT_A_FULL_MULTI_RATE_ALLOCATION_ENGINE"
    )
    s04_engine_status: str = "S04_ENGINE_IMPLEMENTED"
    claimed_cost_status: str = "CLAIMED_DIRECT_LABOR_COST_COMPUTABLE_WHEN_RATE_AND_LABOR_ALLOW"
    verified_actual_cost_status: str = "ACTUAL_COST_NOT_PROVEN"
    durable_history_schema_status: str = "UNCHANGED_IN_THIS_INCREMENT"
    production_cost_rate_read_adapter_status: str = "NOT_IMPLEMENTED_LIMITATION"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
