"""S09 — Shift Acceptance Recommendation (deterministic).

Consolidates prior professional skill results into operation-level and
shift-level recommendations. Does NOT perform managerial acceptance,
contractual recognition, payroll, or commercial recognition.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import (
    MathIntegrityStatus,
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from agents.production_shift_auditor.s02_contracts import (
    SourceAuthority,
    TechCheckResult,
    ShiftTechnologicalIntegrityArtifact,
)
from agents.production_shift_auditor.s03_contracts import (
    PhysicalCheckResult,
    PhysicalSourceAuthority,
    ShiftPhysicalIntegrityArtifact,
)
from agents.production_shift_auditor.s04_contracts import ShiftExecutionCostArtifact
from agents.production_shift_auditor.s05_contracts import ShiftTemporalIntegrityArtifact
from agents.production_shift_auditor.s06_contracts import (
    ShiftStatisticalAnomalyArtifact,
    SignalType,
    StatisticalSignalStatus,
)
from agents.production_shift_auditor.s07_contracts import (
    CausalStatus,
    ShiftRootCauseArtifact,
)
from agents.production_shift_auditor.s08_contracts import (
    EvidenceAuthority,
    EvidenceFindingStatus,
    ShiftEvidenceValidationArtifact,
)
from agents.production_shift_auditor.s09_contracts import (
    S09_ARTIFACT_SCHEMA_VERSION,
    S09_RULES_VERSION,
    FindingImpact,
    FindingRepresentationKind,
    InheritedFindingRef,
    OperationRecommendation,
    PolicyAuthority,
    RecommendationEvidenceAuthority,
    RecommendationPolicy,
    RecommendationStatus,
    ReviewPriority,
    SharedContextKind,
    SharedContextRequirement,
    ShiftAcceptanceRecommendationArtifact,
    ShiftRecommendationSummary,
    StatusLaborBucket,
    SuggestedClarificationRole,
    TargetedNextAction,
    demonstration_recommendation_policy,
)
from agents.production_shift_auditor.s10_contracts import (
    ClassificationStatus,
    ShiftOperationClassificationArtifact,
)
from agents.production_shift_auditor.s11_contracts import ShiftLaborBenchmarkArtifact

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"

_STATUS_RANK = {
    RecommendationStatus.CORRECTION_RECOMMENDED: 60,
    RecommendationStatus.EVIDENCE_REQUIRED: 50,
    RecommendationStatus.CLARIFICATION_REQUIRED: 40,
    RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED: 30,
    RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION: 20,
    RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE: 10,
}

_PRIORITY_RANK = {
    ReviewPriority.INFORMATION: 0,
    ReviewPriority.REVIEW_CANDIDATE: 1,
    ReviewPriority.CLARIFICATION_REQUIRED: 2,
    ReviewPriority.HIGH_REVIEW_PRIORITY: 3,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dec(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _fmt_exact(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return f"{value.quantize(Decimal('0.0001'))}"


def _max_status(*statuses: RecommendationStatus) -> RecommendationStatus:
    return max(statuses, key=lambda s: _STATUS_RANK[s])


def _max_priority(*priorities: ReviewPriority) -> ReviewPriority:
    return max(priorities, key=lambda p: _PRIORITY_RANK[p])


def _map_s08_authority(
    raw: EvidenceAuthority | str | None,
) -> RecommendationEvidenceAuthority:
    name = getattr(raw, "value", str(raw or "INSUFFICIENT"))
    mapping = {
        "CLAIMED_REFERENCE": RecommendationEvidenceAuthority.CLAIMED_ONLY,
        "METADATA_PRESENT": RecommendationEvidenceAuthority.METADATA_PRESENT,
        "METADATA_VALIDATED": RecommendationEvidenceAuthority.METADATA_VALIDATED,
        "CONTENT_VERIFIED": RecommendationEvidenceAuthority.CONTENT_VERIFIED,
        "PHYSICAL_EXECUTION_VERIFIED": (
            RecommendationEvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED
        ),
    }
    return mapping.get(name, RecommendationEvidenceAuthority.INSUFFICIENT)


def _authority_ceiling(
    authorities: Sequence[RecommendationEvidenceAuthority],
) -> RecommendationEvidenceAuthority:
    order = [
        RecommendationEvidenceAuthority.INSUFFICIENT,
        RecommendationEvidenceAuthority.UNCERTAIN,
        RecommendationEvidenceAuthority.CLAIMED_ONLY,
        RecommendationEvidenceAuthority.METADATA_PRESENT,
        RecommendationEvidenceAuthority.METADATA_VALIDATED,
        RecommendationEvidenceAuthority.CONTENT_VERIFIED,
        RecommendationEvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED,
    ]
    # Cap at METADATA_VALIDATED — S08 cannot grant content/physical in this increment
    capped = []
    for a in authorities:
        if a in (
            RecommendationEvidenceAuthority.CONTENT_VERIFIED,
            RecommendationEvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED,
        ):
            capped.append(RecommendationEvidenceAuthority.METADATA_VALIDATED)
        else:
            capped.append(a)
    if not capped:
        return RecommendationEvidenceAuthority.INSUFFICIENT
    return max(capped, key=lambda x: order.index(x))


def _finding_key(skill: str, identity: str) -> str:
    return f"{skill}:{identity}"


def _collect_findings(
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s10: ShiftOperationClassificationArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    s11: ShiftLaborBenchmarkArtifact,
    s04: ShiftExecutionCostArtifact,
    s05: ShiftTemporalIntegrityArtifact,
    s06: ShiftStatisticalAnomalyArtifact,
    s07: ShiftRootCauseArtifact,
    s08: ShiftEvidenceValidationArtifact,
) -> list[InheritedFindingRef]:
    """Collect and de-duplicate inherited findings by (skill, identity)."""
    by_key: dict[str, InheritedFindingRef] = {}

    def add(ref: InheritedFindingRef) -> None:
        key = _finding_key(ref.skill_code, ref.finding_identity)
        if key not in by_key:
            by_key[key] = ref

    # S01 — shift-level mathematical integrity
    s01_id = f"s01:math:{s01.math_integrity_status.value}"
    add(
        InheritedFindingRef(
            skill_code="S01",
            finding_identity=s01_id,
            finding_status_or_result=s01.math_integrity_status.value,
            impact=(
                FindingImpact.BLOCKING
                if s01.math_integrity_status == MathIntegrityStatus.INCOHERENT
                else FindingImpact.INFORMATIONAL
            ),
            evidence_authority="ARITHMETIC_COHERENCE_ONLY",
            provenance=("s01.math_integrity_status",),
            professional_note=(
                "MATHEMATICAL_CONSISTENCY_NE_PHYSICAL_ACCEPTANCE; "
                "SOFTWARE_ENGINE_PASS_NE_PRODUCTION_VALIDATION"
            ),
            underlying_finding_identity=s01_id,
            representation_kind=FindingRepresentationKind.ORIGINAL_FINDING,
            counts_as_independent_proof=True,
        )
    )

    # S10 classifications
    for line in s10.classifications:
        impact = FindingImpact.INFORMATIONAL
        if line.classification_status in (
            ClassificationStatus.AMBIGUOUS,
            ClassificationStatus.INSUFFICIENT_CONTEXT,
            ClassificationStatus.UNKNOWN_OPERATION,
        ):
            impact = FindingImpact.NON_BLOCKING
        add(
            InheritedFindingRef(
                skill_code="S10",
                finding_identity=f"s10:{line.source_operation_identity}",
                finding_status_or_result=line.classification_status.value,
                impact=impact,
                evidence_authority="CLASSIFICATION_CANDIDATE_ONLY",
                source_operation_identity=line.source_operation_identity,
                operation_code=line.operation_code_candidate,
                provenance=("s10.classification",),
                professional_note="CLASSIFICATION_NE_ACCEPTANCE",
            )
        )

    # S02
    for f in s02.findings:
        demo = (
            f.demonstration_rule
            or f.source_authority == SourceAuthority.DEMONSTRATION_RULE
        )
        if f.check_result == TechCheckResult.PROVEN_CONTRADICTION and not demo:
            impact = FindingImpact.BLOCKING
        elif f.check_result in (
            TechCheckResult.PROVEN_CONTRADICTION,
            TechCheckResult.INSUFFICIENT_CONTEXT,
        ):
            impact = FindingImpact.NON_BLOCKING if demo else FindingImpact.NON_BLOCKING
        else:
            impact = FindingImpact.INFORMATIONAL
        add(
            InheritedFindingRef(
                skill_code="S02",
                finding_identity=f.check_identity,
                finding_status_or_result=f.check_result.value,
                impact=impact,
                evidence_authority=(
                    f.source_authority.value if f.source_authority else "UNKNOWN"
                ),
                source_operation_identity=f.source_operation_identity,
                operation_code=f.classified_operation_code,
                demonstration_authority=demo,
                provenance=("s02.technological_check",) + tuple(f.source_provenance),
                professional_note=(
                    "DEMONSTRATION_RULE_AUTHORITY_PRESERVED"
                    if demo
                    else "TECHNOLOGICAL_CHECK_NE_PHYSICAL_PROOF"
                ),
            )
        )

    # S03
    for f in s03.findings:
        demo = (
            f.demonstration_rule
            or f.source_authority == PhysicalSourceAuthority.DEMONSTRATION_RULE
        )
        if f.check_result in (
            PhysicalCheckResult.INVALID_QUANTITY,
            PhysicalCheckResult.UNIT_INCOMPATIBILITY,
            PhysicalCheckResult.PROVEN_RECORD_DUPLICATE,
        ):
            impact = FindingImpact.BLOCKING
        elif f.check_result in (
            PhysicalCheckResult.POSSIBLE_DUPLICATE,
            PhysicalCheckResult.INSUFFICIENT_CONTEXT,
        ):
            impact = FindingImpact.NON_BLOCKING
        else:
            impact = FindingImpact.INFORMATIONAL
        add(
            InheritedFindingRef(
                skill_code="S03",
                finding_identity=f.check_identity,
                finding_status_or_result=f.check_result.value,
                impact=impact,
                evidence_authority=(
                    f.source_authority.value if f.source_authority else "UNKNOWN"
                ),
                source_operation_identity=f.source_operation_identity,
                physical_object_reference=f.physical_object_reference,
                operation_code=f.classified_operation_code,
                demonstration_authority=demo,
                provenance=("s03.physical_check",) + tuple(f.source_provenance),
                professional_note=(
                    "POTENTIAL_DUPLICATE_NE_PROVEN_DUPLICATION"
                    if f.check_result == PhysicalCheckResult.POSSIBLE_DUPLICATE
                    else "CLAIMED_PHYSICAL_NE_VERIFIED"
                ),
            )
        )

    # S11 — reference only; do not invent norms
    for f in getattr(s11, "findings", ()) or ():
        fid = getattr(f, "check_identity", None) or getattr(
            f, "source_operation_identity", "s11_unknown"
        )
        add(
            InheritedFindingRef(
                skill_code="S11",
                finding_identity=f"s11:{fid}",
                finding_status_or_result=str(
                    getattr(
                        getattr(f, "calculation_status", None),
                        "value",
                        getattr(f, "calculation_status", "S11_OBSERVATION"),
                    )
                ),
                impact=FindingImpact.INFORMATIONAL,
                evidence_authority="CLAIMED_LABOR_BENCHMARK_ONLY",
                source_operation_identity=getattr(
                    f, "source_operation_identity", None
                ),
                operation_code=getattr(f, "canonical_operation_code", None)
                or getattr(f, "operation_code", None),
                provenance=("s11.labor_benchmark",),
                professional_note="CLAIMED_UNIT_LABOR_NE_APPROVED_NORM",
            )
        )

    # S04 — cost findings informational; unknown ≠ zero
    for f in s04.findings:
        add(
            InheritedFindingRef(
                skill_code="S04",
                finding_identity=f.check_identity,
                finding_status_or_result=f.calculation_status.value,
                impact=FindingImpact.INFORMATIONAL,
                evidence_authority=f.cost_rate_authority or "SCENARIO_RATE",
                source_operation_identity=f.source_operation_identity,
                operation_code=f.canonical_operation_code,
                provenance=("s04.execution_cost",) + tuple(f.provenance),
                professional_note="SCENARIO_COST_NE_ACTUAL_COST; UNKNOWN_NE_ZERO",
            )
        )

    # S05
    for f in s05.findings:
        fid = getattr(f, "check_identity", None) or getattr(
            f, "source_operation_identity", "s05_unknown"
        )
        statuses = getattr(f, "finding_statuses", ()) or ()
        status_name = (
            statuses[0].value
            if statuses and hasattr(statuses[0], "value")
            else (str(statuses[0]) if statuses else "TEMPORAL_OBSERVATION")
        )
        add(
            InheritedFindingRef(
                skill_code="S05",
                finding_identity=f"s05:{fid}",
                finding_status_or_result=status_name,
                impact=FindingImpact.INFORMATIONAL,
                evidence_authority="CLAIMED_CHRONOLOGY_ONLY",
                source_operation_identity=getattr(
                    f, "source_operation_identity", None
                ),
                provenance=("s05.temporal_integrity",),
                professional_note="CLAIMED_CHRONOLOGY_NE_VERIFIED",
            )
        )

    # S06 — anomaly ≠ violation / rejection
    for sig in s06.signals:
        sid = sig.signal_identity
        status_val = sig.status.value
        type_val = sig.signal_type.value
        inherited = (
            status_val == StatisticalSignalStatus.INHERITED_PROFESSIONAL_FINDING.value
            or type_val == SignalType.INHERITED_FINDING.value
        )
        if status_val in (
            StatisticalSignalStatus.STATISTICAL_ANOMALY_CANDIDATE.value,
            StatisticalSignalStatus.THRESHOLD_EXCEEDANCE.value,
            StatisticalSignalStatus.REVIEW_REQUIRED.value,
        ):
            impact = FindingImpact.NON_BLOCKING
        else:
            impact = FindingImpact.INFORMATIONAL
        if type_val in (
            SignalType.LABOR_CONCENTRATION.value,
            SignalType.ROUNDING_PATTERN.value,
            SignalType.REPEATED_VALUE.value,
        ):
            impact = FindingImpact.INFORMATIONAL
        underlying = None
        if inherited and sig.source_observation_identities:
            # Preserve available original reference; do not invent identity
            underlying = (
                f"s05_or_prior:{sig.source_observation_identities[0]}"
            )
        add(
            InheritedFindingRef(
                skill_code="S06",
                finding_identity=f"s06:{sid}",
                finding_status_or_result=status_val,
                impact=impact,
                evidence_authority=sig.evidence_authority.value,
                source_operation_identity=(
                    sig.source_observation_identities[0]
                    if sig.source_observation_identities
                    else None
                ),
                operation_code=sig.canonical_operation_code,
                provenance=("s06.statistical_anomaly",) + tuple(sig.provenance),
                professional_note=(
                    "STATISTICAL_ANOMALY_NE_PROVEN_VIOLATION; "
                    "REVIEW_PRIORITY_NE_EVIDENCE_AUTHORITY; "
                    + (
                        "INHERITED_REPRESENTATION_NE_INDEPENDENT_PROOF"
                        if inherited
                        else "ORIGINAL_OR_COMPUTED_SIGNAL"
                    )
                ),
                underlying_finding_identity=underlying,
                representation_kind=(
                    FindingRepresentationKind.INHERITED_REPRESENTATION
                    if inherited
                    else FindingRepresentationKind.ORIGINAL_FINDING
                ),
                counts_as_independent_proof=not inherited,
            )
        )

    # S07 — hypotheses never escalate to established cause
    for h in s07.hypotheses:
        add(
            InheritedFindingRef(
                skill_code="S07",
                finding_identity=h.hypothesis_identity,
                finding_status_or_result=h.causal_status.value,
                impact=FindingImpact.INFORMATIONAL,
                evidence_authority=h.evidence_authority.value,
                source_operation_identity=h.affected_operation_identity,
                physical_object_reference=h.physical_object_reference,
                operation_code=h.affected_operation_code,
                provenance=("s07.root_cause_hypothesis",) + tuple(h.provenance),
                professional_note=(
                    "S07_HYPOTHESIS_NE_ESTABLISHED_CAUSE; "
                    "CAUSAL_HYPOTHESIS_NE_INDEPENDENT_PROOF; "
                    f"status={CausalStatus.CAUSE_NOT_ESTABLISHED.value}"
                ),
                underlying_finding_identity=h.linked_finding_identity or None,
                representation_kind=FindingRepresentationKind.CAUSAL_HYPOTHESIS,
                counts_as_independent_proof=False,
            )
        )

    # S08 — authority ceiling METADATA_VALIDATED
    for f in s08.findings:
        statuses = tuple(s.value for s in f.finding_statuses)
        blocking_marks = {
            EvidenceFindingStatus.EVIDENCE_MISSING.value,
            EvidenceFindingStatus.INVALID_QUANTITY.value,
            EvidenceFindingStatus.HISTORICAL_QUANTITY_BASIS_CONTRADICTION.value,
            EvidenceFindingStatus.EVIDENCE_SCOPE_CONFLICT.value,
        }
        review_marks = {
            EvidenceFindingStatus.POTENTIAL_QUANTITY_EXCESS.value,
            EvidenceFindingStatus.POTENTIAL_DUPLICATE_CLAIM.value,
            EvidenceFindingStatus.REMAINING_QUANTITY_NOT_PROVEN.value,
            EvidenceFindingStatus.HISTORY_INCOMPLETE.value,
            EvidenceFindingStatus.REVISION_MAPPING_NOT_PROVEN.value,
            EvidenceFindingStatus.CONTRADICTORY_OBJECT_MAPPING.value,
            EvidenceFindingStatus.SOURCE_VERSION_AUTHORITY_UNCERTAIN.value,
            EvidenceFindingStatus.CONFLICTING_EVIDENCE_CONTEXT.value,
        }
        if any(s in blocking_marks for s in statuses):
            impact = FindingImpact.BLOCKING
        elif any(s in review_marks for s in statuses):
            impact = FindingImpact.NON_BLOCKING
        else:
            impact = FindingImpact.INFORMATIONAL
        # Physical-not-verified always blocks positive physical acceptance
        if EvidenceFindingStatus.PHYSICAL_EXECUTION_NOT_VERIFIED.value in statuses:
            # Keep as blocking for positive physical path, but do not treat as
            # proven non-execution
            if impact == FindingImpact.INFORMATIONAL:
                impact = FindingImpact.NON_BLOCKING
        add(
            InheritedFindingRef(
                skill_code="S08",
                finding_identity=f.finding_identity,
                finding_status_or_result="|".join(statuses),
                impact=impact,
                evidence_authority=f.authority.value,
                source_operation_identity=None,
                physical_object_reference=f.physical_object_reference,
                operation_code=f.operation_reference,
                execution_event_reference=f.linked_execution_event,
                provenance=("s08.evidence_validation",) + tuple(f.provenance),
                professional_note=(
                    "METADATA_VALIDATION_NE_CONTENT_VALIDATION; "
                    "MISSING_EVIDENCE_NE_PROVEN_NON_EXECUTION; "
                    "AUTHORITY_CEILING_METADATA_VALIDATED"
                ),
            )
        )

    _ = audit_input  # reserved for future scope filters
    return list(by_key.values())


def _ops_index(
    audit_input: ShiftAuditInput,
    s10: ShiftOperationClassificationArtifact,
    s04: ShiftExecutionCostArtifact,
    s08: ShiftEvidenceValidationArtifact,
) -> list[dict]:
    """Build one row per source operation / execution event (no double count)."""
    cost_by_id = {f.source_operation_identity: f for f in s04.findings}
    s08_by_event: dict[str, list] = defaultdict(list)
    s08_by_code: dict[str, list] = defaultdict(list)
    for f in s08.findings:
        if f.linked_execution_event:
            s08_by_event[f.linked_execution_event].append(f)
        if f.operation_reference:
            s08_by_code[f.operation_reference].append(f)

    rows: list[dict] = []
    seen_events: set[str] = set()
    classifications = list(s10.classifications)

    for i, op in enumerate(audit_input.operations):
        cl = classifications[i] if i < len(classifications) else None
        sid = (
            cl.source_operation_identity
            if cl
            else (
                op.source_record_ids[0]
                if op.source_record_ids
                else f"op:{i}:{op.operation_name}"
            )
        )
        cost = cost_by_id.get(sid)
        # Prefer explicit S08 claim event when present for this op index/name
        event_ref = f"claimed_event:{i}:{op.operation_name}"
        if event_ref in seen_events:
            continue
        seen_events.add(event_ref)

        labor_mm = float(op.claimed_labor_quantity)
        if op.labor_unit.value == "MAN_HOUR":
            labor_mm = float(op.claimed_labor_quantity) * 60.0

        code = cl.operation_code_candidate if cl else None
        rows.append(
            {
                "source_operation_identity": sid,
                "original_operation_text": op.operation_name,
                "physical_object_reference": op.physical_object_hint,
                "canonical_operation_identity": (
                    cl.canonical_operation_candidate if cl else None
                ),
                "operation_code": code,
                "work_category": cl.work_category if cl else None,
                "execution_event_reference": event_ref,
                "original_claimed_quantity": op.physical_quantity,
                "original_quantity_unit": op.physical_unit,
                "original_claimed_labor_man_minutes": labor_mm,
                "scenario_direct_labor_cost_exact": (
                    cost.computed_direct_labor_cost_exact if cost else None
                ),
                "source_record_ids": tuple(op.source_record_ids),
                "s08_findings": list(s08_by_event.get(event_ref, ()))
                + (list(s08_by_code.get(code, ())) if code else []),
            }
        )

    # Additional S08 execution events not already covered (e.g. typed claims)
    covered_events = {r["execution_event_reference"] for r in rows}
    events_seen: set[str] = set()
    for f in s08.findings:
        ev = f.linked_execution_event
        if not ev or ev in covered_events or ev in events_seen:
            continue
        if ev.startswith("claimed_event:"):
            continue
        events_seen.add(ev)
        related = list(s08_by_event.get(ev, ()))
        first = related[0] if related else f
        labor = None
        cost = None
        rows.append(
            {
                "source_operation_identity": (
                    f"event:{ev}:{first.operation_reference or 'unknown'}"
                ),
                "original_operation_text": first.operation_reference or ev,
                "physical_object_reference": first.physical_object_reference,
                "canonical_operation_identity": first.operation_reference,
                "operation_code": first.operation_reference,
                "work_category": None,
                "execution_event_reference": ev,
                "original_claimed_quantity": first.claimed_quantity,
                "original_quantity_unit": first.quantity_unit,
                "original_claimed_labor_man_minutes": labor,
                "scenario_direct_labor_cost_exact": cost,
                "source_record_ids": (),
                "s08_findings": related,
            }
        )
    return rows


def _findings_for_op(
    consolidated: Sequence[InheritedFindingRef],
    row: dict,
) -> list[InheritedFindingRef]:
    sid = row["source_operation_identity"]
    code = row.get("operation_code")
    obj = row.get("physical_object_reference")
    event = row.get("execution_event_reference")
    name = row.get("original_operation_text")
    out: list[InheritedFindingRef] = []
    for f in consolidated:
        if f.skill_code == "S01":
            # shift-level; attach to all as informational/blocking context
            out.append(f)
            continue
        if f.source_operation_identity and f.source_operation_identity == sid:
            out.append(f)
            continue
        if code and f.operation_code and f.operation_code == code:
            out.append(f)
            continue
        if event and f.execution_event_reference and f.execution_event_reference == event:
            out.append(f)
            continue
        if (
            obj
            and f.physical_object_reference
            and f.physical_object_reference == obj
            and (not f.operation_code or f.operation_code == code)
        ):
            out.append(f)
            continue
        # S08 default claims use operation_name embedded in event
        if f.skill_code == "S08" and event and f.execution_event_reference == event:
            out.append(f)
            continue
        if f.skill_code == "S08" and name and f.execution_event_reference and name in (
            f.execution_event_reference or ""
        ):
            out.append(f)
            continue
    # De-dupe by skill:identity
    uniq: dict[str, InheritedFindingRef] = {}
    for f in out:
        uniq[_finding_key(f.skill_code, f.finding_identity)] = f
    return list(uniq.values())


def _recommend_for_operation(
    *,
    row: dict,
    op_findings: Sequence[InheritedFindingRef],
    policy: RecommendationPolicy,
    s01: ShiftAuditArtifact,
    s07: ShiftRootCauseArtifact,
    s08: ShiftEvidenceValidationArtifact,
    project_code: str,
    shift_reference: str,
    work_category: Optional[str],
) -> OperationRecommendation:
    # Independent blockers only — inherited/hypothesis layers are not extra proof
    blocking = [
        _finding_key(f.skill_code, f.finding_identity)
        for f in op_findings
        if f.impact == FindingImpact.BLOCKING and f.counts_as_independent_proof
    ]
    non_blocking = [
        _finding_key(f.skill_code, f.finding_identity)
        for f in op_findings
        if f.impact == FindingImpact.NON_BLOCKING
    ]
    contradictions: list[str] = []
    missing: list[str] = []
    actions: list[TargetedNextAction] = []
    reason_codes: list[str] = []
    status = RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION
    priority = ReviewPriority.REVIEW_CANDIDATE
    role: Optional[SuggestedClarificationRole] = SuggestedClarificationRole.FOREMAN
    authorities: list[RecommendationEvidenceAuthority] = []
    limitations: list[str] = [
        "PROFESSIONAL_RECOMMENDATION_NE_MANAGERIAL_ACCEPTANCE",
        "PARTIAL_RECOMMENDATION_NE_PARTIAL_ACCEPTANCE",
        "NO_DETECTED_ISSUE_NE_VERIFIED_SHIFT",
        "SOFTWARE_ENGINE_PASS_NE_PRODUCTION_VALIDATION",
    ]
    shared_refs: list[str] = []
    op_specific = False
    auxiliary = work_category in ("auxiliary", "preparation", "quality")

    # S01 arithmetic — shared shift-level when incoherent
    if s01.math_integrity_status == MathIntegrityStatus.INCOHERENT:
        status = _max_status(status, RecommendationStatus.CORRECTION_RECOMMENDED)
        priority = _max_priority(priority, ReviewPriority.HIGH_REVIEW_PRIORITY)
        contradictions.append("S01_ARITHMETIC_INCOHERENT")
        reason_codes.append("S01_ARITHMETIC_INCOHERENT")
        shared_refs.append("shared:s01:arithmetic")
        actions.append(
            TargetedNextAction(
                action_identity="act:correct_arithmetic",
                action_text="Устранить конкретное математическое противоречие в заявленных трудозатратах",
                scope_key="shift:s01:arithmetic",
                suggested_clarification_role=SuggestedClarificationRole.FOREMAN,
                linked_finding_identities=("s01:math:INCOHERENT",),
                provenance=("s09.from_s01",),
                shared=True,
            )
        )

    physical_verified = False
    content_verified = False
    evidence_missing = False
    potential_excess = False
    potential_dup = False
    history_incomplete = False
    demo_tech = False
    anomaly = False
    classification_issue = False
    composite_issue = False
    object_context_insufficient = False
    s08_next_actions: list[str] = []

    for f in op_findings:
        if f.skill_code == "S08":
            authorities.append(_map_s08_authority(f.evidence_authority))
            st = f.finding_status_or_result
            if "PHYSICAL_EXECUTION_VERIFIED" in st and "NOT_VERIFIED" not in st:
                if "PHYSICAL_EXECUTION_NOT_VERIFIED" not in st:
                    physical_verified = True
            if "PHYSICAL_EXECUTION_NOT_VERIFIED" in st:
                physical_verified = False
                limitations.append("PHYSICAL_EXECUTION_NOT_VERIFIED")
                shared_refs.append("shared:s08:physical_not_verified")
            if "EVIDENCE_CONTENT_NOT_VERIFIED" in st:
                limitations.append("METADATA_VALIDATION_NE_CONTENT_VALIDATION")
            if "CONTENT_VERIFIED" in st and "NOT_VERIFIED" not in st:
                if "EVIDENCE_CONTENT_NOT_VERIFIED" not in st:
                    content_verified = True
            if "EVIDENCE_MISSING" in st:
                evidence_missing = True
            if "POTENTIAL_QUANTITY_EXCESS" in st:
                potential_excess = True
            if "POTENTIAL_DUPLICATE_CLAIM" in st:
                potential_dup = True
            if "HISTORY_INCOMPLETE" in st:
                history_incomplete = True
                missing.append("APPLICABLE_EXECUTION_HISTORY_INCOMPLETE_OR_UNAVAILABLE")
                limitations.append("MISSING_HISTORY_NE_ZERO_HISTORY")
            elif "REMAINING_QUANTITY_NOT_PROVEN" in st:
                # Default S08 stamp without history context — shared insufficiency,
                # not an invented per-op history contradiction
                limitations.append("REMAINING_QUANTITY_NOT_PROVEN_WITHOUT_HISTORY_CONTEXT")
                shared_refs.append("shared:s08:physical_not_verified")
            if "MULTIPLE_REPRESENTATIONS_SAME_EVENT" in st:
                limitations.append(
                    "ONE_PHYSICAL_OBJECT_NE_ONE_DRAWING_REPRESENTATION; "
                    "SAME_EVENT_NOT_COUNTED_TWICE"
                )
        if f.skill_code == "S02" and f.demonstration_authority:
            demo_tech = True
            limitations.append("DEMONSTRATION_RULE_AUTHORITY_PRESERVED")
            limitations.append(
                "DEMONSTRATION_TECHNOLOGICAL_FINDING_NE_PRODUCTION_BLOCKER_WITHOUT_AUTHORITY"
            )
        if f.skill_code == "S03":
            if "INVALID_QUANTITY" in f.finding_status_or_result:
                status = _max_status(status, RecommendationStatus.CORRECTION_RECOMMENDED)
                contradictions.append("S03_INVALID_QUANTITY")
                reason_codes.append("S03_INVALID_QUANTITY")
                op_specific = True
                actions.append(
                    TargetedNextAction(
                        action_identity="act:correct_quantity",
                        action_text="Уточнить единицу измерения / исправить недопустимое количество",
                        scope_key=f"op:{row['source_operation_identity']}:quantity",
                        suggested_clarification_role=SuggestedClarificationRole.FOREMAN,
                        linked_finding_identities=(f.finding_identity,),
                        provenance=("s09.from_s03",),
                    )
                )
            if "POSSIBLE_DUPLICATE" in f.finding_status_or_result:
                potential_dup = True
            if "INSUFFICIENT_CONTEXT" in f.finding_status_or_result:
                object_context_insufficient = True
        if (
            f.skill_code == "S06"
            and f.counts_as_independent_proof
            and f.finding_status_or_result
            in (
                StatisticalSignalStatus.STATISTICAL_ANOMALY_CANDIDATE.value,
                StatisticalSignalStatus.THRESHOLD_EXCEEDANCE.value,
                StatisticalSignalStatus.REVIEW_REQUIRED.value,
            )
        ):
            anomaly = True
        if f.skill_code == "S10":
            if f.finding_status_or_result in (
                ClassificationStatus.AMBIGUOUS.value,
                ClassificationStatus.INSUFFICIENT_CONTEXT.value,
                ClassificationStatus.UNKNOWN_OPERATION.value,
            ):
                classification_issue = True
            if f.finding_status_or_result == ClassificationStatus.COMPOSITE_OPERATION.value:
                composite_issue = True
        if f.skill_code == "S07":
            limitations.append("S07_HYPOTHESIS_NE_ESTABLISHED_CAUSE")
            limitations.append("CAUSAL_HYPOTHESIS_NE_INDEPENDENT_PROOF")

    # Reuse S08 next_recommended_verification_action when present for this event
    event = row.get("execution_event_reference")
    for ef in s08.findings:
        if event and ef.linked_execution_event == event and ef.next_recommended_verification_action:
            s08_next_actions.append(ef.next_recommended_verification_action)

    # Reuse S07 targeted clarification for this operation when present
    sid = row["source_operation_identity"]
    for h in s07.hypotheses:
        if h.affected_operation_identity == sid and h.targeted_clarification_question:
            actions.append(
                TargetedNextAction(
                    action_identity=f"act:s07:{h.hypothesis_identity}",
                    action_text=h.targeted_clarification_question,
                    scope_key=f"op:{sid}:s07:{h.hypothesis_identity}",
                    suggested_clarification_role=SuggestedClarificationRole(
                        h.suggested_clarification_role.value
                    )
                    if hasattr(h.suggested_clarification_role, "value")
                    else SuggestedClarificationRole.FOREMAN,
                    linked_finding_identities=(h.hypothesis_identity, h.linked_finding_identity),
                    provenance=("s09.from_s07_targeted_clarification",),
                )
            )
            op_specific = True

    if evidence_missing and not auxiliary:
        status = _max_status(status, RecommendationStatus.EVIDENCE_REQUIRED)
        priority = _max_priority(priority, ReviewPriority.CLARIFICATION_REQUIRED)
        missing.append("REQUIRED_EVIDENCE_MISSING")
        limitations.append("MISSING_EVIDENCE_NE_PROVEN_NON_EXECUTION")
        reason_codes.append("EVIDENCE_REQUIRED_FOR_APPLICABLE_REQUIREMENT")
        op_specific = True
        actions.append(
            TargetedNextAction(
                action_identity="act:provide_evidence",
                action_text=(
                    "Предоставить применимое доказательство и подтвердить "
                    "принадлежность доказательства физическому объекту"
                ),
                scope_key=f"op:{row['source_operation_identity']}:evidence",
                suggested_clarification_role=SuggestedClarificationRole.FOREMAN,
                linked_finding_identities=tuple(
                    f.finding_identity
                    for f in op_findings
                    if f.skill_code == "S08" and "EVIDENCE_MISSING" in f.finding_status_or_result
                ),
                provenance=("s09.from_s08",),
            )
        )
    elif evidence_missing and auxiliary:
        limitations.append(
            "AUXILIARY_OR_PREPARATION_OPERATION_NO_UNIVERSAL_RD_EVIDENCE_PACKAGE"
        )
        reason_codes.append("AUXILIARY_EVIDENCE_PACKAGE_NOT_AUTO_REQUIRED")

    if classification_issue or composite_issue:
        status = _max_status(status, RecommendationStatus.CLARIFICATION_REQUIRED)
        priority = _max_priority(priority, ReviewPriority.CLARIFICATION_REQUIRED)
        missing.append("OPERATION_IDENTITY_OR_COMPOSITION_UNCLEAR")
        reason_codes.append(
            "COMPOSITE_OR_UNCLEAR_OPERATION_COMPOSITION"
            if composite_issue
            else "OPERATION_CLASSIFICATION_CLARIFICATION"
        )
        op_specific = True
        actions.append(
            TargetedNextAction(
                action_identity="act:clarify_operation",
                action_text=(
                    "Уточнить состав объединённой операции; не распределять "
                    "трудозатраты между компонентами без основания"
                    if composite_issue
                    else "Уточнить состав / идентификацию технологической операции"
                ),
                scope_key=f"op:{row['source_operation_identity']}:classify",
                suggested_clarification_role=SuggestedClarificationRole.PTO,
                provenance=("s09.from_s10",),
            )
        )

    if potential_excess:
        status = _max_status(status, RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED)
        priority = _max_priority(priority, ReviewPriority.REVIEW_CANDIDATE)
        contradictions.append("POTENTIAL_QUANTITY_EXCESS")
        limitations.append("POTENTIAL_QUANTITY_EXCESS_NE_PAYMENT_REJECTION")
        reason_codes.append("POTENTIAL_QUANTITY_EXCESS_REVIEW")
        op_specific = True
        actions.append(
            TargetedNextAction(
                action_identity="act:review_quantity_excess",
                action_text="Проверить предыдущие события исполнения и остаточный объём",
                scope_key=f"op:{row['source_operation_identity']}:qty_excess",
                suggested_clarification_role=SuggestedClarificationRole.ENGINEER,
                provenance=("s09.from_s08",),
            )
        )

    if potential_dup:
        status = _max_status(status, RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED)
        limitations.append("POTENTIAL_DUPLICATE_NE_PROVEN_DUPLICATION")
        reason_codes.append("POTENTIAL_DUPLICATE_REVIEW")
        op_specific = True
        actions.append(
            TargetedNextAction(
                action_identity="act:review_duplicate",
                action_text=(
                    "Проверить, не является ли заявление повторным учётом "
                    "того же физического результата"
                ),
                scope_key=f"op:{row['source_operation_identity']}:dup",
                suggested_clarification_role=SuggestedClarificationRole.ENGINEER,
                provenance=("s09.from_s03_s08",),
            )
        )

    if anomaly:
        status = _max_status(status, RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED)
        priority = _max_priority(priority, ReviewPriority.REVIEW_CANDIDATE)
        limitations.append("STATISTICAL_ANOMALY_NE_AUTOMATIC_REJECTION")
        reason_codes.append("STATISTICAL_ANOMALY_CANDIDATE_REVIEW")
        op_specific = True
        actions.append(
            TargetedNextAction(
                action_identity="act:review_anomaly",
                action_text=(
                    "Провести целевой профессиональный разбор статистического "
                    "сигнала (не автоматическое отклонение)"
                ),
                scope_key=f"op:{row['source_operation_identity']}:anomaly",
                suggested_clarification_role=SuggestedClarificationRole.SITE_SUPERVISOR,
                provenance=("s09.from_s06",),
            )
        )

    # Demo technology finding: preserve authority, do NOT auto-escalate status
    if demo_tech:
        reason_codes.append("DEMONSTRATION_TECH_FINDING_NON_BLOCKING")
        shared_refs.append("shared:s02:demonstration_authority")

    if history_incomplete:
        status = _max_status(
            status, RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION
        )
        missing.append("HISTORICAL_CONTEXT_NOT_TREATED_AS_ZERO")
        reason_codes.append("HISTORY_INCOMPLETE_NOT_ZERO")

    # Operation-type-specific actionable hints only when findings support them
    if (
        work_category == "fabrication"
        and object_context_insufficient
        and row.get("original_claimed_quantity") is not None
    ):
        op_specific = True
        actions.append(
            TargetedNextAction(
                action_identity="act:clarify_fabrication_context",
                action_text=(
                    "Уточнить физические характеристики / применимость reference "
                    "observations для изготовления фасонных изделий"
                ),
                scope_key=f"op:{row['source_operation_identity']}:fab_context",
                suggested_clarification_role=SuggestedClarificationRole.ENGINEER,
                provenance=("s09.from_s03_insufficient_context",),
            )
        )
        reason_codes.append("FABRICATION_CONTEXT_CLARIFICATION")

    if (
        work_category in ("cladding", "installation")
        and object_context_insufficient
        and row.get("original_claimed_quantity") is not None
    ):
        op_specific = True
        actions.append(
            TargetedNextAction(
                action_identity="act:clarify_install_object",
                action_text=(
                    "Проверить identity физического объекта и основание "
                    "заявленного объёма"
                ),
                scope_key=f"op:{row['source_operation_identity']}:obj_qty",
                suggested_clarification_role=SuggestedClarificationRole.ENGINEER,
                provenance=("s09.from_s03_insufficient_context",),
            )
        )
        reason_codes.append("INSTALL_OBJECT_QUANTITY_CONTEXT")

    if auxiliary:
        limitations.append("NO_FICTITIOUS_MEASURABLE_QUANTITY_ASSIGNED")
        limitations.append(
            "ABSENCE_OF_QUANTITY_NE_AUTOMATIC_VIOLATION_FOR_AUXILIARY_OPERATION"
        )
        if row.get("original_claimed_quantity") is None:
            reason_codes.append("AUXILIARY_NO_QUANTITY_NOT_VIOLATION")

    # Only surface S08 next-actions that are not the generic future content/physical ask
    for text in dict.fromkeys(s08_next_actions):
        if not text or not op_specific:
            continue
        generic = (
            "content validation (S08-D future)" in text
            or "physical execution verification" in text.lower()
        )
        if generic:
            continue
        actions.append(
            TargetedNextAction(
                action_identity="act:s08_verification",
                action_text=text,
                scope_key=f"op:{row['source_operation_identity']}:s08:{hash(text) & 0xFFFF:x}",
                suggested_clarification_role=SuggestedClarificationRole.ENGINEER,
                provenance=("s09.from_s08_next_verification",),
            )
        )

    # Evidence authority ceiling
    auth = _authority_ceiling(authorities) if authorities else (
        RecommendationEvidenceAuthority.CLAIMED_ONLY
    )
    if auth in (
        RecommendationEvidenceAuthority.CONTENT_VERIFIED,
        RecommendationEvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED,
    ):
        auth = RecommendationEvidenceAuthority.METADATA_VALIDATED
        limitations.append("UNTRUSTED_AUTHORITY_CANNOT_BYPASS_S08_CEILING")

    positive_ok = (
        policy.production_acceptance_requirements_established
        and policy.allows_positive_physical_acceptance
        and physical_verified
        and not blocking
        and s01.math_integrity_status == MathIntegrityStatus.COHERENT
        and not evidence_missing
    )
    if positive_ok:
        status = RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE
        reason_codes.append("POSITIVE_WITHIN_VALIDATED_SCOPE")
    else:
        if status == RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE:
            status = RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION
        if not policy.production_acceptance_requirements_established:
            missing.append("PRODUCTION_ACCEPTANCE_REQUIREMENTS_NOT_ESTABLISHED")
            limitations.append("DEMONSTRATION_POLICY_NE_PRODUCTION_AUTHORITY")
            shared_refs.append("shared:policy:production_requirements_not_established")
            reason_codes.append("PRODUCTION_ACCEPTANCE_REQUIREMENTS_NOT_ESTABLISHED")
        if not physical_verified:
            limitations.append(
                "METADATA_VALIDATION_CANNOT_AUTHORIZE_PHYSICAL_ACCEPTANCE"
            )
            shared_refs.append("shared:s08:physical_not_verified")
            reason_codes.append("PHYSICAL_EXECUTION_NOT_VERIFIED")
            if _STATUS_RANK[status] <= _STATUS_RANK[
                RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION
            ]:
                status = RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION
                reason_codes.append("INSUFFICIENT_BASIS_DEFAULT")

    # Shared gaps are referenced, not repeated as per-op identical actions
    act_uniq: dict[str, TargetedNextAction] = {}
    for a in actions:
        if a.shared:
            continue  # lifted to shift shared_context_requirements
        if a.scope_key not in act_uniq:
            act_uniq[a.scope_key] = a

    if not act_uniq and not op_specific:
        # Transparent insufficient context — no invented operation-specific question
        reason_codes.append("NO_OPERATION_SPECIFIC_ACTION_FORMABLE")
        limitations.append("INSUFFICIENT_CONTEXT_FOR_OPERATION_SPECIFIC_QUESTION")

    rationale_parts = [
        f"status={status.value}",
        f"evidence_authority={auth.value}",
        f"blocking_independent={len(blocking)}",
        f"non_blocking={len(non_blocking)}",
        f"work_category={work_category or 'unknown'}",
        "CLAIMED_EXECUTION_NE_VERIFIED_EXECUTION",
        "HUMAN_DECISION_REQUIRED",
        *reason_codes[:8],
    ]
    if content_verified:
        rationale_parts.append("content_flag_ignored_without_trusted_ceiling_bypass")

    return OperationRecommendation(
        recommendation_identity=(
            f"rec:{row['source_operation_identity']}:{row['execution_event_reference']}"
        ),
        project_code=project_code,
        shift_reference=shift_reference,
        source_operation_identity=row["source_operation_identity"],
        source_record_ids=tuple(row.get("source_record_ids") or ()),
        physical_object_reference=row.get("physical_object_reference"),
        canonical_operation_identity=row.get("canonical_operation_identity"),
        operation_code=row.get("operation_code"),
        original_operation_text=row["original_operation_text"],
        execution_event_reference=row.get("execution_event_reference"),
        original_claimed_quantity=row.get("original_claimed_quantity"),
        original_quantity_unit=row.get("original_quantity_unit"),
        original_claimed_labor_man_minutes=row.get(
            "original_claimed_labor_man_minutes"
        ),
        scenario_direct_labor_cost_exact=row.get("scenario_direct_labor_cost_exact"),
        applicable_requirement_references=(),
        inherited_finding_references=tuple(op_findings),
        evidence_authority=auth,
        unresolved_contradictions=tuple(dict.fromkeys(contradictions)),
        missing_context=tuple(dict.fromkeys(missing)),
        blocking_findings=tuple(blocking),
        non_blocking_findings=tuple(non_blocking),
        review_priority=priority,
        recommendation_status=status,
        professional_rationale="; ".join(rationale_parts),
        recommended_next_actions=tuple(act_uniq.values()),
        suggested_clarification_role=role,
        provenance=(
            "s09.acceptance_recommendation",
            S09_RULES_VERSION,
            policy.version,
        ),
        recommendation_policy_version=policy.version,
        limitations=tuple(dict.fromkeys(limitations)),
        work_category=work_category,
        operation_specific_exception=op_specific,
        shared_context_references=tuple(dict.fromkeys(shared_refs)),
        status_reason_codes=tuple(dict.fromkeys(reason_codes)),
    )


def _build_shared_contexts(
    op_recs: Sequence[OperationRecommendation],
    *,
    s01: ShiftAuditArtifact,
    policy: RecommendationPolicy,
) -> tuple[SharedContextRequirement, ...]:
    """Lift repeated shift/engineering gaps into one shared requirement each."""
    out: list[SharedContextRequirement] = []

    def _affected(pred) -> tuple[tuple[str, ...], tuple[str, ...]]:
        ids = tuple(r.source_operation_identity for r in op_recs if pred(r))
        names = tuple(r.original_operation_text for r in op_recs if pred(r))
        return ids, names

    if not policy.production_acceptance_requirements_established:
        ids, names = _affected(
            lambda r: "shared:policy:production_requirements_not_established"
            in r.shared_context_references
        )
        if ids:
            out.append(
                SharedContextRequirement(
                    shared_context_identity="shared:policy:production_requirements_not_established",
                    context_kind=SharedContextKind.PRODUCTION_POLICY_GAP,
                    scope_key="shift:production_acceptance_requirements",
                    requirement_text=(
                        "PRODUCTION_ACCEPTANCE_REQUIREMENTS_NOT_ESTABLISHED — "
                        "утверждённые требования приёмки не заданы; "
                        "не придумывать универсальный пакет доказательств"
                    ),
                    affected_operation_identities=ids,
                    affected_operation_names=names,
                    suggested_clarification_role=SuggestedClarificationRole.PROJECT_MANAGER,
                    provenance=("s09.shared_context", policy.version),
                )
            )

    ids, names = _affected(
        lambda r: "shared:s08:physical_not_verified" in r.shared_context_references
    )
    if ids:
        out.append(
            SharedContextRequirement(
                shared_context_identity="shared:s08:physical_not_verified",
                context_kind=SharedContextKind.EVIDENCE_AUTHORITY_CEILING,
                scope_key="shift:physical_execution_not_verified",
                requirement_text=(
                    "PHYSICAL_EXECUTION_NOT_VERIFIED / S08 authority ceiling "
                    "METADATA_VALIDATED — metadata validation cannot authorize "
                    "physical acceptance for affected operations"
                ),
                affected_operation_identities=ids,
                affected_operation_names=names,
                suggested_clarification_role=SuggestedClarificationRole.ENGINEER,
                provenance=("s09.shared_context", "s08.authority_ceiling"),
            )
        )

    ids, names = _affected(
        lambda r: "shared:s02:demonstration_authority" in r.shared_context_references
    )
    if ids:
        out.append(
            SharedContextRequirement(
                shared_context_identity="shared:s02:demonstration_authority",
                context_kind=SharedContextKind.SHARED_ENGINEERING_CONTEXT,
                scope_key="shift:s02_demonstration_authority",
                requirement_text=(
                    "Demonstration technological findings present — authority "
                    "preserved; not approved production blockers"
                ),
                affected_operation_identities=ids,
                affected_operation_names=names,
                linked_finding_identities=("S02:DEMONSTRATION_RULE",),
                suggested_clarification_role=SuggestedClarificationRole.PTO,
                provenance=("s09.shared_context", "s02.demonstration"),
            )
        )

    if s01.math_integrity_status == MathIntegrityStatus.INCOHERENT:
        ids, names = _affected(
            lambda r: "shared:s01:arithmetic" in r.shared_context_references
        )
        out.append(
            SharedContextRequirement(
                shared_context_identity="shared:s01:arithmetic",
                context_kind=SharedContextKind.SHIFT_LEVEL_LIMITATION,
                scope_key="shift:s01:arithmetic",
                requirement_text=(
                    "S01 arithmetic incoherence — correct claimed labor totals "
                    "before physical acceptance recommendation"
                ),
                affected_operation_identities=ids or tuple(
                    r.source_operation_identity for r in op_recs
                ),
                affected_operation_names=names or tuple(
                    r.original_operation_text for r in op_recs
                ),
                linked_finding_identities=("s01:math:INCOHERENT",),
                suggested_clarification_role=SuggestedClarificationRole.FOREMAN,
                provenance=("s09.shared_context", "s01"),
            )
        )

    return tuple(out)


def evaluate_s09(
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s10: ShiftOperationClassificationArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    s11: ShiftLaborBenchmarkArtifact,
    s04: ShiftExecutionCostArtifact,
    s05: ShiftTemporalIntegrityArtifact,
    s06: ShiftStatisticalAnomalyArtifact,
    s07: ShiftRootCauseArtifact,
    s08: ShiftEvidenceValidationArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    recommendation_policy: Optional[RecommendationPolicy] = None,
    production_acceptance_requirements_available: bool = False,
) -> ShiftAcceptanceRecommendationArtifact:
    """Consolidate prior skills into professional recommendations. Never mutates inputs."""
    aid = audit_id or s01.audit_id or str(uuid.uuid4())
    policy = recommendation_policy or demonstration_recommendation_policy(
        production_acceptance_requirements_available=(
            production_acceptance_requirements_available
        )
    )
    if not policy.production_acceptance_requirements_established:
        # Ensure demonstration authority is not silently upgraded
        if policy.authority != PolicyAuthority.POLICY_NOT_ESTABLISHED:
            if not production_acceptance_requirements_available:
                policy = RecommendationPolicy(
                    policy_identity=policy.policy_identity,
                    version=policy.version,
                    provenance=policy.provenance,
                    authority=PolicyAuthority.DEMONSTRATION_POLICY,
                    applicable_scope=policy.applicable_scope,
                    required_professional_checks=policy.required_professional_checks,
                    blocking_criteria=policy.blocking_criteria,
                    non_blocking_criteria=policy.non_blocking_criteria,
                    missing_context_treatment=policy.missing_context_treatment,
                    allows_positive_physical_acceptance=False,
                    production_acceptance_requirements_established=False,
                    source_note=(
                        "PRODUCTION_ACCEPTANCE_REQUIREMENTS_NOT_ESTABLISHED; "
                        + policy.source_note
                    ),
                )

    consolidated = _collect_findings(
        audit_input, s01, s10, s02, s03, s11, s04, s05, s06, s07, s08
    )
    rows = _ops_index(audit_input, s10, s04, s08)
    shift_ref = f"{audit_input.project_code}|{audit_input.work_date}|{audit_input.crew_id}"

    op_recs: list[OperationRecommendation] = []
    for row in rows:
        op_findings = _findings_for_op(consolidated, row)
        op_recs.append(
            _recommend_for_operation(
                row=row,
                op_findings=op_findings,
                policy=policy,
                s01=s01,
                s07=s07,
                s08=s08,
                project_code=audit_input.project_code,
                shift_reference=shift_ref,
                work_category=row.get("work_category"),
            )
        )

    shared_contexts = _build_shared_contexts(op_recs, s01=s01, policy=policy)

    # Labor / cost by status — each operation once
    buckets: dict[RecommendationStatus, list[OperationRecommendation]] = defaultdict(
        list
    )
    for r in op_recs:
        buckets[r.recommendation_status].append(r)

    status_buckets: list[StatusLaborBucket] = []
    for st, items in sorted(buckets.items(), key=lambda x: -_STATUS_RANK[x[0]]):
        labor = sum(float(i.original_claimed_labor_man_minutes or 0.0) for i in items)
        cost_sum = Decimal("0")
        any_cost = False
        for i in items:
            d = _dec(i.scenario_direct_labor_cost_exact)
            if d is not None:
                cost_sum += d
                any_cost = True
        status_buckets.append(
            StatusLaborBucket(
                recommendation_status=st,
                operation_count=len(items),
                labor_man_minutes=labor,
                scenario_direct_labor_cost_exact=_fmt_exact(cost_sum)
                if any_cost
                else None,
            )
        )

    material_blockers = tuple(
        dict.fromkeys(
            bid
            for r in op_recs
            for bid in r.blocking_findings
        )
    )
    # Shift-level recommendation: strongest op status; non-blocking alone does not reject shift
    if not op_recs:
        shift_status = RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION
    else:
        shift_status = _max_status(*(r.recommendation_status for r in op_recs))
        # Do not escalate entire shift to CORRECTION solely from non-blocking observations
        only_non_blocking = all(
            r.recommendation_status
            in (
                RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED,
                RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION,
                RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE,
            )
            and not r.blocking_findings
            for r in op_recs
        )
        if (
            only_non_blocking
            and shift_status == RecommendationStatus.CORRECTION_RECOMMENDED
        ):
            shift_status = RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED

    s01_total = (
        s01.s01_metrics.claimed_total_man_minutes if s01.s01_metrics else None
    )
    target = s01.s01_metrics.target_fund_man_minutes if s01.s01_metrics else None
    if target is None:
        target = (
            float(audit_input.crew_size)
            * float(audit_input.productive_hours_per_person)
            * 60.0
        )

    clarifications = tuple(
        dict.fromkeys(
            list(
                a.action_text
                for r in op_recs
                for a in r.recommended_next_actions
            )
            + [sc.requirement_text for sc in shared_contexts]
        )
    )
    op_specific_ids = tuple(
        r.source_operation_identity for r in op_recs if r.operation_specific_exception
    )
    priority_items = tuple(
        r.recommendation_identity
        for r in op_recs
        if r.review_priority
        in (ReviewPriority.HIGH_REVIEW_PRIORITY, ReviewPriority.CLARIFICATION_REQUIRED)
        or r.recommendation_status
        in (
            RecommendationStatus.CORRECTION_RECOMMENDED,
            RecommendationStatus.EVIDENCE_REQUIRED,
            RecommendationStatus.CLARIFICATION_REQUIRED,
        )
    )

    evidence_limits = (
        "PRODUCTION_EVIDENCE_VALIDATION_NOT_PROVEN",
        "EVIDENCE_CONTENT_VALIDATION_NOT_IMPLEMENTED",
        "PHYSICAL_EXECUTION_NOT_VERIFIED",
        "GEOMETRIC_OVERLAP_ENGINE_NOT_IMPLEMENTED",
        "S08_AUTHORITY_CEILING_METADATA_VALIDATED",
    )
    hist_limits = (
        "MISSING_HISTORY_NE_ZERO_HISTORY",
        "CROSS_REVISION_MAPPING_NOT_INFERRED",
    )
    explicit_limits = (
        "PROFESSIONAL_RECOMMENDATION_NE_MANAGERIAL_ACCEPTANCE",
        "MANAGERIAL_ACCEPTANCE_NE_CONTRACTUAL_RECOGNITION",
        "CONTRACTUAL_RECOGNITION_NE_PAYROLL_AUTHORIZATION",
        "PARTIAL_RECOMMENDATION_NE_PARTIAL_ACCEPTANCE",
        "NO_ACCEPTED_OR_REJECTED_QUANTITIES_CREATED",
        "NO_AUTOMATIC_COMMERCIAL_RECOGNITION",
        "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN",
        "PRODUCTION_ACCEPTANCE_REQUIREMENTS_NOT_ESTABLISHED"
        if not policy.production_acceptance_requirements_established
        else "PRODUCTION_REQUIREMENTS_DECLARED_BUT_PHYSICAL_PROOF_STILL_REQUIRED",
        "COST_DEVIATION_ENGINE_IMPLEMENTED_NO",
        "ACTUAL_INCURRED_COST_NOT_PROVEN",
    )

    conclusion = (
        f"Shift-level professional recommendation={shift_status.value}; "
        f"human_decision_required=YES; "
        f"operations={len(op_recs)}; "
        f"material_blockers={len(material_blockers)}; "
        "managerial_acceptance=NOT_PERFORMED"
    )

    summary = ShiftRecommendationSummary(
        shift_identity=shift_ref,
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        total_claimed_labor_man_minutes=s01_total,
        target_productive_fund_man_minutes=target,
        mathematical_balance_status=s01.math_integrity_status.value,
        original_operation_count=len(audit_input.operations),
        operation_recommendation_count=len(op_recs),
        recommendations_by_status=tuple(status_buckets),
        unresolved_shift_level_findings=tuple(
            _finding_key(f.skill_code, f.finding_identity)
            for f in consolidated
            if f.impact != FindingImpact.INFORMATIONAL
        ),
        material_blocking_findings=material_blockers,
        evidence_coverage_limitations=evidence_limits,
        historical_context_limitations=hist_limits,
        priority_review_items=priority_items,
        targeted_clarification_requests=clarifications,
        shift_level_recommendation=shift_status,
        human_decision_required=True,
        scenario_direct_labor_cost_exact=(
            s04.cost_conservation.total_calculated_direct_labor_cost_exact
        ),
        explicit_limitations=explicit_limits,
        professional_conclusion=conclusion,
        shared_context_requirements=shared_contexts,
        operation_specific_exception_identities=op_specific_ids,
        reachable_recommendation_statuses=(
            RecommendationStatus.CLARIFICATION_REQUIRED.value,
            RecommendationStatus.EVIDENCE_REQUIRED.value,
            RecommendationStatus.CORRECTION_RECOMMENDED.value,
            RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED.value,
            RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION.value,
        ),
        reserved_recommendation_statuses=(
            f"{RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE.value} "
            "(reserved under current S08 ceiling / demo policy)",
        ),
    )

    observations = (
        "S09 consolidates prior skills; does not recompute prior metrics",
        "S07 hypotheses not escalated to established causes",
        "S08 authority ceiling METADATA_VALIDATED respected",
        "Findings keyed by skill:identity; inherited/hypothesis layers "
        "retain underlying refs and do not count as independent proof",
        "Shared shift/engineering gaps lifted to shared_context_requirements",
        "Demonstration S02 findings do not auto-escalate recommendation status",
        "Labor counted once per operation recommendation",
        "Human decision required; no managerial acceptance mutation",
        "RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE reserved under current "
        "S08 ceiling and demonstration policy (POSITIVE_PHYSICAL_NOT_PROVEN)",
    )

    positive_status = "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN"
    if any(
        r.recommendation_status
        == RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE
        for r in op_recs
    ):
        # Still not physical acceptance proof unless physical verified under policy
        positive_status = (
            "POSITIVE_RECOMMENDATION_WITHIN_VALIDATED_SCOPE_ONLY_NOT_PHYSICAL_PROOF"
        )

    prod_policy_status = (
        "PRODUCTION_ACCEPTANCE_POLICY_READY"
        if policy.production_acceptance_requirements_established
        and policy.authority == PolicyAuthority.APPROVED_PRODUCTION_POLICY
        else "PRODUCTION_ACCEPTANCE_POLICY_NOT_READY"
    )

    human = (
        f"S09 recommendation for {audit_input.project_code} {audit_input.work_date}: "
        f"{shift_status.value}. Human decision required. "
        f"Claimed labor={s01_total}; S04 scenario cost="
        f"{s04.cost_conservation.total_calculated_direct_labor_cost_exact}."
    )

    return ShiftAcceptanceRecommendationArtifact(
        schema_version=S09_ARTIFACT_SCHEMA_VERSION,
        rules_version=S09_RULES_VERSION,
        policy_version=policy.version,
        audit_id=aid,
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=_utc_now(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        policy=policy,
        consolidated_findings=tuple(consolidated),
        operation_recommendations=tuple(op_recs),
        shift_summary=summary,
        observations=observations,
        managerial_acceptance_status="NOT_IN_SCOPE",
        contractual_recognition_status="NOT_PERFORMED",
        commercial_acceptance_status="NOT_IN_SCOPE",
        payroll_decision_status="NOT_PERFORMED",
        disciplinary_decision_status="NOT_PERFORMED",
        human_decision_required=True,
        human_readable_summary=human,
        positive_physical_acceptance_recommendation_status=positive_status,
        production_acceptance_policy_status=prod_policy_status,
        production_acceptance_recommendation_status=(
            "PRODUCTION_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN"
        ),
        managerial_acceptance_performed_status="MANAGERIAL_ACCEPTANCE_PERFORMED_NO",
        contractual_recognition_performed_status="CONTRACTUAL_RECOGNITION_PERFORMED_NO",
    )
