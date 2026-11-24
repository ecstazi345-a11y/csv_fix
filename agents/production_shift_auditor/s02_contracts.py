"""PSAA S02 — Technological Integrity contracts.

Not physical proof. Not managerial acceptance. Not Operation Registry.
SOURCE-NEUTRAL. Serializable for future durable history (persist not in this increment).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S02_RULES_VERSION = "psaa.s02.technological_integrity.v0.1"
S02_ARTIFACT_SCHEMA_VERSION = "shift_technological_integrity.v0.1"


class TechCheckResult(str, Enum):
    CONSISTENT_WITH_CHECKED_RULE = "CONSISTENT_WITH_CHECKED_RULE"
    PROVEN_CONTRADICTION = "PROVEN_CONTRADICTION"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class TechCheckType(str, Enum):
    OPERATION_APPLICABILITY = "OPERATION_APPLICABILITY"
    MATERIAL_APPLICABILITY = "MATERIAL_APPLICABILITY"
    PREREQUISITE = "PREREQUISITE"
    SEQUENCE = "SEQUENCE"
    COMPOSITE_LIMITATION = "COMPOSITE_LIMITATION"
    CONTEXT_SUFFICIENCY = "CONTEXT_SUFFICIENCY"


class SourceAuthority(str, Enum):
    PROJECT_REQUIREMENT = "PROJECT_REQUIREMENT"
    MANUFACTURER_INSTRUCTION = "MANUFACTURER_INSTRUCTION"
    APPROVED_TECH_CARD = "APPROVED_TECH_CARD"
    INTERNAL_PROFESSIONAL_RULE = "INTERNAL_PROFESSIONAL_RULE"
    DEMONSTRATION_RULE = "DEMONSTRATION_RULE"


class ApplicabilityVerdict(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PriorOperationEvidence:
    """Cross-shift / cross-crew evidence supplied by caller — never invented by S02."""

    operation_code: str
    work_date: str
    physical_object_hint: Optional[str] = None
    crew_id: Optional[str] = None
    source_note: str = "prior_shift_evidence"


@dataclass(frozen=True)
class TechnologicalCheckFinding:
    check_identity: str
    source_operation_identity: str
    original_operation_text: str
    classified_operation_code: Optional[str]
    classified_operation_name: Optional[str]
    check_type: TechCheckType
    applicable_rule_id: Optional[str]
    rule_version: Optional[str]
    source_authority: Optional[SourceAuthority]
    source_provenance: tuple[str, ...]
    applicability: ApplicabilityVerdict
    check_result: TechCheckResult
    supporting_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    professional_explanation: str
    clarification_request: Optional[str]
    demonstration_rule: bool = False
    # Labor/volume referenced only — never rewritten
    claimed_labor_quantity: Optional[float] = None
    claimed_labor_unit: Optional[str] = None
    physical_quantity: Optional[float] = None
    physical_unit: Optional[str] = None


@dataclass(frozen=True)
class ShiftTechnologicalIntegrityArtifact:
    schema_version: str
    rules_version: str
    tech_ruleset_version: str
    audit_id: str
    agent_code: str
    agent_version: str
    run_id: Optional[str]
    created_at_utc: str
    project_code: str
    work_date: str
    crew_id: str
    evaluation_domain: str
    findings: tuple[TechnologicalCheckFinding, ...]
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    technological_validation_scope: str
    human_readable_summary: str
    # Readiness gates — do not collapse into one "technology OK" flag
    s02_engine_status: str = "S02_ENGINE_IMPLEMENTED"
    demonstration_rules_status: str = "DEMONSTRATION_RULES_PROVEN"
    production_knowledge_status: str = "PRODUCTION_KNOWLEDGE_NOT_READY"
    production_validation_status: str = "PRODUCTION_VALIDATION_NOT_PROVEN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
