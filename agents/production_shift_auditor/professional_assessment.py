"""Combine S01 + S10 + S02 + S03 + S11 + S04 + S05 + S06 + S07 without mutating contract schemas."""

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
from agents.production_shift_auditor.s04_contracts import (
    LaborCostRateReference,
    ShiftExecutionCostArtifact,
)
from agents.production_shift_auditor.s04_execution_cost import evaluate_s04
from agents.production_shift_auditor.s05_contracts import (
    OperationTemporalClaim,
    ShiftTemporalContext,
    ShiftTemporalIntegrityArtifact,
)
from agents.production_shift_auditor.s05_temporal_integrity import evaluate_s05
from agents.production_shift_auditor.s06_contracts import (
    ReportingPrecisionPolicy,
    ShiftStatisticalAnomalyArtifact,
    StatisticalReferenceObservation,
    StatisticalThresholdConfig,
)
from agents.production_shift_auditor.s06_statistical_anomaly import evaluate_s06
from agents.production_shift_auditor.s07_contracts import (
    CausalContextItem,
    ShiftRootCauseArtifact,
)
from agents.production_shift_auditor.s07_root_cause import evaluate_s07
from agents.production_shift_auditor.s10_contracts import ShiftOperationClassificationArtifact
from agents.production_shift_auditor.s10_operation_classification import evaluate_s10
from agents.production_shift_auditor.s11_contracts import (
    BenchmarkReference,
    HistoricalLaborObservation,
    ShiftLaborBenchmarkArtifact,
)
from agents.production_shift_auditor.s11_labor_benchmark import evaluate_s11


@dataclass(frozen=True)
class ShiftProfessionalAssessment:
    """Joint S01+S10+S02+S03+S11+S04+S05+S06+S07. Not managerial acceptance."""

    audit_input: ShiftAuditInput
    s01: ShiftAuditArtifact
    s10: ShiftOperationClassificationArtifact
    s02: ShiftTechnologicalIntegrityArtifact
    s03: ShiftPhysicalIntegrityArtifact
    s11: ShiftLaborBenchmarkArtifact
    s04: ShiftExecutionCostArtifact
    s05: ShiftTemporalIntegrityArtifact
    s06: ShiftStatisticalAnomalyArtifact
    s07: ShiftRootCauseArtifact


def assess_shift(
    audit_input: ShiftAuditInput,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    prior_operation_evidence: Sequence[PriorOperationEvidence] = (),
    prior_physical_claims: Sequence[PriorPhysicalClaimEvidence] = (),
    tech_rules_available: bool = True,
    benchmarks: Sequence[BenchmarkReference] = (),
    historical_observations: Sequence[HistoricalLaborObservation] = (),
    cost_rates: Sequence[LaborCostRateReference] = (),
    temporal_claims: Sequence[OperationTemporalClaim] = (),
    shift_temporal_context: Optional[ShiftTemporalContext] = None,
    statistical_threshold_config: Optional[StatisticalThresholdConfig] = None,
    reporting_precision: Optional[ReportingPrecisionPolicy] = None,
    statistical_references: Sequence[StatisticalReferenceObservation] = (),
    causal_contexts: Sequence[CausalContextItem] = (),
    authorized_project_scopes: Sequence[str] = (),
    allow_future_reference_dates: bool = False,
    allow_future_context: bool = False,
    evaluation_as_of_date: Optional[str] = None,
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
    s11 = evaluate_s11(
        audit_input,
        s01,
        s10,
        s02,
        s03,
        audit_id=s01.audit_id,
        run_id=run_id,
        benchmarks=benchmarks,
        historical_observations=historical_observations,
    )
    s04 = evaluate_s04(
        audit_input,
        s01,
        s10,
        s02,
        s03,
        s11,
        audit_id=s01.audit_id,
        run_id=run_id,
        cost_rates=cost_rates,
    )
    s05 = evaluate_s05(
        audit_input,
        s01,
        s10,
        s02,
        s03,
        s11,
        s04,
        audit_id=s01.audit_id,
        run_id=run_id,
        temporal_claims=temporal_claims,
        shift_temporal_context=shift_temporal_context,
    )
    s06 = evaluate_s06(
        audit_input,
        s01,
        s10,
        s02,
        s03,
        s11,
        s04,
        s05,
        audit_id=s01.audit_id,
        run_id=run_id,
        threshold_config=statistical_threshold_config,
        reporting_precision=reporting_precision,
        statistical_references=statistical_references,
        authorized_project_scopes=authorized_project_scopes,
        allow_future_reference_dates=allow_future_reference_dates,
        evaluation_as_of_date=evaluation_as_of_date,
    )
    s07 = evaluate_s07(
        audit_input,
        s01,
        s10,
        s02,
        s03,
        s11,
        s04,
        s05,
        s06,
        audit_id=s01.audit_id,
        run_id=run_id,
        causal_contexts=causal_contexts,
        authorized_project_scopes=authorized_project_scopes,
        allow_future_context=allow_future_context,
    )
    return ShiftProfessionalAssessment(
        audit_input=audit_input,
        s01=s01,
        s10=s10,
        s02=s02,
        s03=s03,
        s11=s11,
        s04=s04,
        s05=s05,
        s06=s06,
        s07=s07,
    )
