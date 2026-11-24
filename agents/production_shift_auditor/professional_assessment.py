"""Combine S01 + S10 + S02 + S03 without mutating contract schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import ShiftAuditArtifact, ShiftAuditInput
from agents.production_shift_auditor.s01_mathematical_integrity import evaluate_s01
from agents.production_shift_auditor.s02_contracts import (
    PriorOperationEvidence,
    ShiftTechnologicalIntegrityArtifact,
)
from agents.production_shift_auditor.s02_technological_integrity import evaluate_s02
from agents.production_shift_auditor.s03_contracts import (
    PriorPhysicalClaimEvidence,
    ShiftPhysicalIntegrityArtifact,
)
from agents.production_shift_auditor.s03_physical_integrity import evaluate_s03
from agents.production_shift_auditor.s10_contracts import ShiftOperationClassificationArtifact
from agents.production_shift_auditor.s10_operation_classification import evaluate_s10


@dataclass(frozen=True)
class ShiftProfessionalAssessment:
    """Joint S01+S10+S02+S03. Not managerial acceptance. Not a new SoT model."""

    audit_input: ShiftAuditInput
    s01: ShiftAuditArtifact
    s10: ShiftOperationClassificationArtifact
    s02: ShiftTechnologicalIntegrityArtifact
    s03: ShiftPhysicalIntegrityArtifact


def assess_shift(
    audit_input: ShiftAuditInput,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    prior_operation_evidence: Sequence[PriorOperationEvidence] = (),
    prior_physical_claims: Sequence[PriorPhysicalClaimEvidence] = (),
    tech_rules_available: bool = True,
) -> ShiftProfessionalAssessment:
    s01 = evaluate_s01(audit_input, audit_id=audit_id, run_id=run_id)
    s10 = evaluate_s10(
        audit_input,
        audit_id=s01.audit_id,
        run_id=run_id,
    )
    s02 = evaluate_s02(
        audit_input,
        s10,
        audit_id=s01.audit_id,
        run_id=run_id,
        prior_operation_evidence=prior_operation_evidence,
        tech_rules_available=tech_rules_available,
    )
    s03 = evaluate_s03(
        audit_input,
        s10,
        audit_id=s01.audit_id,
        run_id=run_id,
        prior_physical_claims=prior_physical_claims,
    )
    return ShiftProfessionalAssessment(
        audit_input=audit_input, s01=s01, s10=s10, s02=s02, s03=s03
    )
