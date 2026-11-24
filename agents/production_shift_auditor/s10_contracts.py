"""PSAA S10 — Operation Classification contracts.

Separate from ShiftAuditArtifact (S01). SOURCE-NEUTRAL. Not Operation Registry.
Not acceptance. Not technological validation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional


S10_RULES_VERSION = "psaa.s10.operation_classification.v0.1"
S10_ARTIFACT_SCHEMA_VERSION = "shift_operation_classification.v0.1"


class ClassificationStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    NORMALIZED_MATCH = "NORMALIZED_MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    COMPOSITE_OPERATION = "COMPOSITE_OPERATION"
    UNKNOWN_OPERATION = "UNKNOWN_OPERATION"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class ClassificationMethod(str, Enum):
    DETERMINISTIC_ALIAS = "DETERMINISTIC_ALIAS"
    DETERMINISTIC_NORMALIZED = "DETERMINISTIC_NORMALIZED"
    DETERMINISTIC_CONTEXT = "DETERMINISTIC_CONTEXT"
    DETERMINISTIC_COMPOSITE = "DETERMINISTIC_COMPOSITE"
    DETERMINISTIC_INSUFFICIENT = "DETERMINISTIC_INSUFFICIENT"
    DETERMINISTIC_UNKNOWN = "DETERMINISTIC_UNKNOWN"


@dataclass(frozen=True)
class ClassificationCandidate:
    operation_code: Optional[str]
    canonical_name: Optional[str]
    work_category: Optional[str]
    matching_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationClassificationLine:
    source_operation_identity: str
    original_operation_text: str
    canonical_operation_candidate: Optional[str]
    operation_code_candidate: Optional[str]
    work_category: Optional[str]
    classification_status: ClassificationStatus
    classification_method: ClassificationMethod
    matching_evidence: tuple[str, ...]
    uncertainty_reason: Optional[str]
    clarification_request: Optional[str]
    classification_rules_version: str
    catalog_version: str
    candidates: tuple[ClassificationCandidate, ...] = ()
    provenance: tuple[str, ...] = ()
    # Labor / volume are NEVER rewritten by S10 — only referenced if present on input
    claimed_labor_quantity: Optional[float] = None
    claimed_labor_unit: Optional[str] = None
    physical_quantity: Optional[float] = None
    physical_unit: Optional[str] = None
    source_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShiftOperationClassificationArtifact:
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
    classification_domain: str
    classifications: tuple[OperationClassificationLine, ...]
    observations: tuple[str, ...]
    managerial_acceptance_status: str
    registry_approval_status: str
    human_readable_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
