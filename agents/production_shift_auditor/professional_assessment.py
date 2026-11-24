"""Combine S01 + S10 without mutating either contract schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agents.production_shift_auditor.contracts import ShiftAuditArtifact, ShiftAuditInput
from agents.production_shift_auditor.s01_mathematical_integrity import evaluate_s01
from agents.production_shift_auditor.s10_contracts import ShiftOperationClassificationArtifact
from agents.production_shift_auditor.s10_operation_classification import evaluate_s10


@dataclass(frozen=True)
class ShiftProfessionalAssessment:
    """Joint S01+S10 result. Not managerial acceptance. Not a new SoT model."""

    audit_input: ShiftAuditInput
    s01: ShiftAuditArtifact
    s10: ShiftOperationClassificationArtifact


def assess_shift(
    audit_input: ShiftAuditInput,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> ShiftProfessionalAssessment:
    s01 = evaluate_s01(audit_input, audit_id=audit_id, run_id=run_id)
    s10 = evaluate_s10(
        audit_input,
        audit_id=s01.audit_id,
        run_id=run_id,
    )
    return ShiftProfessionalAssessment(audit_input=audit_input, s01=s01, s10=s10)
