"""PSAA S03 — Physical Integrity contracts.

Not physical inspection proof. Not managerial acceptance. Not earned value.
Not contract acceptance. SOURCE-NEUTRAL. Serializable (persist not in this increment).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S03_RULES_VERSION = "psaa.s03.physical_integrity.v0.1"
S03_ARTIFACT_SCHEMA_VERSION = "shift_physical_integrity.v0.1"


class PhysicalCheckResult(str, Enum):
    CONSISTENT_WITH_CHECKED_RULE = "CONSISTENT_WITH_CHECKED_RULE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    UNIT_INCOMPATIBILITY = "UNIT_INCOMPATIBILITY"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    PROVEN_RECORD_DUPLICATE = "PROVEN_RECORD_DUPLICATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class PhysicalCheckType(str, Enum):
    QUANTITY_INTEGRITY = "QUANTITY_INTEGRITY"
    UNIT_INTEGRITY = "UNIT_INTEGRITY"
    OBJECT_IDENTITY = "OBJECT_IDENTITY"
    RESULT_STATE = "RESULT_STATE"
    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    BOQ_RELATIONSHIP = "BOQ_RELATIONSHIP"
    COMPOSITE_LIMITATION = "COMPOSITE_LIMITATION"
    CONTEXT_SUFFICIENCY = "CONTEXT_SUFFICIENCY"


class ClaimedResultState(str, Enum):
    PREPARED = "PREPARED"
    MANUFACTURED = "MANUFACTURED"
    DELIVERED = "DELIVERED"
    INSTALLED = "INSTALLED"
    PROCESSED = "PROCESSED"
    INSPECTED = "INSPECTED"
    UNKNOWN = "UNKNOWN"


class MeasurabilityClass(str, Enum):
    """Distinguish rule obligation from ontological measurability."""

    MEASURABLE_RESULT_EXPECTED = "MEASURABLE_RESULT_EXPECTED"
    QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE = "QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE"
    MEASURABILITY_UNKNOWN = "MEASURABILITY_UNKNOWN"
    NOT_QUANTITATIVELY_MEASURABLE = "NOT_QUANTITATIVELY_MEASURABLE"
    COMPOSITE_LIMITED = "COMPOSITE_LIMITED"
    UNKNOWN = "UNKNOWN"  # legacy alias path; prefer MEASURABILITY_UNKNOWN


class BoqRelationshipStatus(str, Enum):
    NO_BOQ_LINK = "NO_BOQ_LINK"
    CLAIMED_LINK_PRESENT = "CLAIMED_LINK_PRESENT"
    OPERATION_NOT_AUTO_CONTRACT_QUANTITY = "OPERATION_NOT_AUTO_CONTRACT_QUANTITY"
    NOT_CONTRACT_ACCEPTED = "NOT_CONTRACT_ACCEPTED"
    NOT_EARNED_VALUE = "NOT_EARNED_VALUE"
    NOT_EVALUATED = "NOT_EVALUATED"


class PhysicalSourceAuthority(str, Enum):
    UNIVERSAL_NUMERIC = "UNIVERSAL_NUMERIC"
    ENGINEERING_REQUIREMENT = "ENGINEERING_REQUIREMENT"
    CONTEXT_RULE = "CONTEXT_RULE"
    DEMONSTRATION_RULE = "DEMONSTRATION_RULE"


@dataclass(frozen=True)
class PriorPhysicalClaimEvidence:
    """Optional cross-shift physical claim — never invented by S03."""

    operation_code: Optional[str]
    physical_quantity: Optional[float]
    physical_unit: Optional[str]
    physical_object_hint: Optional[str] = None
    work_date: Optional[str] = None
    source_record_ids: tuple[str, ...] = ()
    source_note: str = "prior_shift_physical_claim"


@dataclass(frozen=True)
class PhysicalIntegrityFinding:
    check_identity: str
    source_operation_identity: str
    original_operation_text: str
    classified_operation_code: Optional[str]
    classified_operation_name: Optional[str]
    check_type: PhysicalCheckType
    original_claimed_quantity: Optional[float]
    original_unit: Optional[str]
    physical_object_reference: Optional[str]
    claimed_result_state: ClaimedResultState
    measurability: MeasurabilityClass
    applicable_rule_id: Optional[str]
    rule_version: Optional[str]
    source_authority: Optional[PhysicalSourceAuthority]
    source_provenance: tuple[str, ...]
    check_result: PhysicalCheckResult
    supporting_evidence: tuple[str, ...]
    missing_information: tuple[str, ...]
    duplicate_risk: Optional[str]
    boq_relationship_status: BoqRelationshipStatus
    professional_explanation: str
    clarification_request: Optional[str]
    demonstration_rule: bool = False
    claimed_labor_quantity: Optional[float] = None
    claimed_labor_unit: Optional[str] = None


@dataclass(frozen=True)
class ShiftPhysicalIntegrityArtifact:
    schema_version: str
    rules_version: str
    physical_ruleset_version: str
    audit_id: str
    agent_code: str
    agent_version: str
    run_id: Optional[str]
    created_at_utc: str
    project_code: str
    work_date: str
    crew_id: str
    evaluation_domain: str
    findings: tuple[PhysicalIntegrityFinding, ...]
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    physical_validation_scope: str
    human_readable_summary: str
    s03_engine_status: str = "S03_ENGINE_IMPLEMENTED"
    demonstration_rules_status: str = "DEMONSTRATION_PHYSICAL_RULES_PROVEN"
    production_physical_knowledge_status: str = "PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY"
    physical_inspection_status: str = "PHYSICAL_INSPECTION_NOT_PROVEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
