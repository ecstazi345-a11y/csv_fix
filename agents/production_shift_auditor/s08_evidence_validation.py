"""S08 — Evidence Validation (deterministic) + Spatial Execution Evidence compatibility.

Layers in this increment:
  A. Claimed execution
  B. Evidence reference
  C. Evidence metadata validation

NOT implemented: content validation (D), physical execution verification (E),
acceptance (F), geometric overlap engine.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import ShiftAuditArtifact, ShiftAuditInput
from agents.production_shift_auditor.s02_contracts import ShiftTechnologicalIntegrityArtifact
from agents.production_shift_auditor.s03_contracts import ShiftPhysicalIntegrityArtifact
from agents.production_shift_auditor.s04_contracts import ShiftExecutionCostArtifact
from agents.production_shift_auditor.s05_contracts import ShiftTemporalIntegrityArtifact
from agents.production_shift_auditor.s06_contracts import ShiftStatisticalAnomalyArtifact
from agents.production_shift_auditor.s07_contracts import (
    CausalStatus,
    ShiftRootCauseArtifact,
)
from agents.production_shift_auditor.s08_contracts import (
    S08_ARTIFACT_SCHEMA_VERSION,
    S08_DEMO_REQUIREMENT_VERSION,
    S08_RULES_VERSION,
    EvidenceAuthority,
    EvidenceFindingStatus,
    EvidenceItem,
    EvidencePolarity,
    EvidenceRequirementSpec,
    EvidenceType,
    EvidenceValidationFinding,
    ExecutionClaimRef,
    HistoryCompleteness,
    HistoricalExecutionRecord,
    QuantityBasis,
    QuantityContext,
    RepresentationType,
    ShiftEvidenceSummary,
    ShiftEvidenceValidationArtifact,
    SpatialReference,
)
from agents.production_shift_auditor.s10_contracts import ShiftOperationClassificationArtifact
from agents.production_shift_auditor.s11_contracts import ShiftLaborBenchmarkArtifact

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _metadata_complete(item: EvidenceItem) -> bool:
    """Structural metadata presence — not content verification."""
    if not item.evidence_identity or not item.source_identity:
        return False
    if not item.project_code:
        return False
    # Content hash never invented; absence is OK
    return True


def _evidence_applicable(
    item: EvidenceItem,
    *,
    project_code: str,
    claim: ExecutionClaimRef,
    authorized_project_scopes: Sequence[str],
) -> tuple[bool, list[str], list[EvidenceFindingStatus]]:
    notes: list[str] = []
    statuses: list[EvidenceFindingStatus] = []

    if item.project_code != project_code:
        if item.project_code not in authorized_project_scopes:
            statuses.append(EvidenceFindingStatus.EVIDENCE_SCOPE_CONFLICT)
            return False, [f"{item.evidence_identity}:CROSS_PROJECT_BLOCKED"], statuses

    if item.physical_object_reference and claim.physical_object_reference:
        if item.physical_object_reference.strip() != claim.physical_object_reference.strip():
            statuses.append(EvidenceFindingStatus.EVIDENCE_SCOPE_CONFLICT)
            return (
                False,
                [f"{item.evidence_identity}:OTHER_PHYSICAL_OBJECT_NOT_APPLIED"],
                statuses,
            )
    elif item.physical_object_reference and not claim.physical_object_reference:
        notes.append(f"{item.evidence_identity}:OBJECT_SCOPED_EVIDENCE_WITHOUT_CLAIM_OBJECT")
        statuses.append(EvidenceFindingStatus.EVIDENCE_APPLICABILITY_NOT_PROVEN)
        return False, notes, statuses
    elif claim.physical_object_reference and not item.physical_object_reference:
        notes.append(
            f"{item.evidence_identity}:EVIDENCE_WITHOUT_OBJECT_NE_OBJECT_SPECIFIC"
        )
        statuses.append(EvidenceFindingStatus.EVIDENCE_APPLICABILITY_NOT_PROVEN)

    if item.operation_code and claim.operation_code:
        if item.operation_code != claim.operation_code:
            statuses.append(EvidenceFindingStatus.EVIDENCE_SCOPE_CONFLICT)
            return (
                False,
                [f"{item.evidence_identity}:OTHER_OPERATION_NOT_AUTO_APPLIED"],
                statuses,
            )
    elif claim.operation_code and not item.operation_code:
        notes.append(
            f"{item.evidence_identity}:OPERATION_UNSPECIFIED_EVIDENCE_NE_AUTO_APPLIED"
        )
        statuses.append(EvidenceFindingStatus.EVIDENCE_APPLICABILITY_NOT_PROVEN)

    if item.execution_event_reference and claim.execution_event_identity:
        if item.execution_event_reference != claim.execution_event_identity:
            notes.append(
                f"{item.evidence_identity}:EXECUTION_EVENT_MISMATCH"
            )
            statuses.append(EvidenceFindingStatus.EVIDENCE_APPLICABILITY_NOT_PROVEN)

    # Temporal: capture ≠ registration; do not invent chronology
    if item.capture_time and item.registration_time:
        if item.capture_time != item.registration_time:
            notes.append(
                f"{item.evidence_identity}:CAPTURE_TIME_DISTINGUISHED_FROM_REGISTRATION_TIME"
            )

    return True, notes, statuses


def _spatial_limitations(refs: Sequence[SpatialReference]) -> list[str]:
    out: list[str] = []
    for r in refs:
        if r.geometry_payload is None:
            out.append(
                f"{r.spatial_reference_identity}:TYPED_GEOMETRY_REFERENCE_WITHOUT_PAYLOAD"
            )
        if r.coordinate_system_or_context is None and r.geometry_payload is not None:
            out.append(
                f"{r.spatial_reference_identity}:MISSING_COORDINATE_BASIS_NOT_COMPARABLE"
            )
        if r.elevation_value is not None and not r.elevation_reference_basis:
            out.append(
                f"{r.spatial_reference_identity}:ELEVATION_WITHOUT_ENGINEERING_BASIS_NOT_AUTO_INTERPRETED"
            )
        if not r.physical_object_identity:
            out.append(
                f"{r.spatial_reference_identity}:MISSING_PHYSICAL_OBJECT_IDENTITY_UNCERTAINTY"
            )
        if not r.revision_identity:
            out.append(
                f"{r.spatial_reference_identity}:MISSING_REVISION_IDENTITY"
            )
        # Identical drawing labels alone never establish object identity
        out.append(
            f"{r.spatial_reference_identity}:DRAWING_LABEL_NE_OBJECT_IDENTITY"
        )
    return out


def _requirement_for(
    claim: ExecutionClaimRef,
    requirements: Sequence[EvidenceRequirementSpec],
    *,
    production_requirements_available: bool,
) -> tuple[Optional[EvidenceRequirementSpec], list[EvidenceFindingStatus], list[str]]:
    if not production_requirements_available and not requirements:
        return (
            None,
            [EvidenceFindingStatus.EVIDENCE_REQUIREMENT_NOT_ESTABLISHED],
            ["PRODUCTION_EVIDENCE_REQUIREMENT_NOT_ESTABLISHED"],
        )
    matches = [
        r
        for r in requirements
        if r.operation_code is None
        or (claim.operation_code and r.operation_code == claim.operation_code)
    ]
    if not matches:
        return (
            None,
            [EvidenceFindingStatus.EVIDENCE_REQUIREMENT_NOT_ESTABLISHED],
            ["no_matching_evidence_requirement_for_operation"],
        )
    # Prefer operation-specific
    specific = [r for r in matches if r.operation_code == claim.operation_code]
    return (specific[0] if specific else matches[0]), [], []


def _finite_nonneg(value: Optional[float]) -> bool:
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v >= 0.0


def _remaining_quantity(
    ctx: Optional[QuantityContext],
    history: Sequence[HistoricalExecutionRecord],
    claim: ExecutionClaimRef,
) -> tuple[
    Optional[float],
    Optional[float],
    list[EvidenceFindingStatus],
    list[str],
]:
    """Compute remaining only against explicit compatible quantity basis.

    CONFIRMED PHYSICAL QUANTITY ≠ CONTRACTUALLY ACCEPTED QUANTITY.
    Missing history ≠ zero history.
    Do not clamp historical overrun to zero without an explicit finding.
    """
    statuses: list[EvidenceFindingStatus] = []
    notes: list[str] = []
    if ctx is None:
        return None, None, [EvidenceFindingStatus.REMAINING_QUANTITY_NOT_PROVEN], [
            "NO_QUANTITY_CONTEXT_SUPPLIED"
        ]

    # Untrusted / demonstration completeness is not production completeness
    auth = (ctx.authority or "").upper()
    if "CLAIMED" in auth or "UNTRUSTED" in auth:
        notes.append(
            "UNTRUSTED_COMPLETE_HISTORY_DECLARATION_NE_AUTHORITATIVE_PRODUCTION_COMPLETENESS"
        )
    if "DEMONSTRATION" in auth:
        notes.append("DEMONSTRATION_HISTORY_AUTHORITY_NE_PRODUCTION_COMPLETENESS")

    if not _finite_nonneg(ctx.basis_quantity):
        statuses.append(EvidenceFindingStatus.INVALID_QUANTITY)
        statuses.append(EvidenceFindingStatus.REMAINING_QUANTITY_NOT_PROVEN)
        notes.append("INVALID_BASIS_QUANTITY_NOT_COMPUTABLE")
        return None, None, statuses, notes

    claimed_probe = ctx.claimed_quantity
    if claimed_probe is None:
        claimed_probe = claim.claimed_quantity
    if claimed_probe is not None and not _finite_nonneg(claimed_probe):
        statuses.append(EvidenceFindingStatus.INVALID_QUANTITY)
        notes.append("INVALID_CLAIMED_QUANTITY_NOT_USED_FOR_EXCESS")
        # remaining may still be computable; excess blocked
        claimed_probe = None

    if ctx.history_completeness in (
        HistoryCompleteness.PARTIAL,
        HistoryCompleteness.UNAVAILABLE,
        HistoryCompleteness.INCOMPATIBLE,
        HistoryCompleteness.UNCERTAIN_REVISION,
    ):
        statuses.append(EvidenceFindingStatus.HISTORY_INCOMPLETE)
        statuses.append(EvidenceFindingStatus.REMAINING_QUANTITY_NOT_PROVEN)
        if ctx.history_completeness == HistoryCompleteness.UNAVAILABLE:
            notes.append("MISSING_HISTORY_NE_ZERO_PREVIOUS_QUANTITY")
        elif ctx.history_completeness == HistoryCompleteness.INCOMPATIBLE:
            notes.append(
                "INCOMPATIBLE_HISTORY_NOT_SILENTLY_AGGREGATED;"
                "COMPLETE_HISTORY_RESULT_NOT_AUTHORITATIVE"
            )
        else:
            notes.append(f"history_completeness={ctx.history_completeness.value}")
        return None, None, statuses, notes

    if not ctx.revision_mapping_proven and ctx.applicable_rd_revision:
        for h in history:
            if h.rd_revision and h.rd_revision != ctx.applicable_rd_revision:
                statuses.append(EvidenceFindingStatus.REVISION_MAPPING_NOT_PROVEN)
                statuses.append(EvidenceFindingStatus.REMAINING_QUANTITY_NOT_PROVEN)
                notes.append("CROSS_REVISION_HISTORY_WITHOUT_PROVEN_MAPPING")
                return None, None, statuses, notes

    if ctx.history_completeness != HistoryCompleteness.COMPLETE:
        statuses.append(EvidenceFindingStatus.REMAINING_QUANTITY_NOT_PROVEN)
        return None, None, statuses, notes

    # Sum only physically confirmed compatible history; collapse same execution event
    prior = 0.0
    seen_events: set[str] = set()
    incompatible_skipped = 0
    for h in history:
        if h.physical_object_reference != ctx.physical_object_reference:
            continue
        if ctx.operation_code and h.operation_code and h.operation_code != ctx.operation_code:
            notes.append(f"{h.record_identity}:OPERATION_SCOPE_MISMATCH_NOT_AGGREGATED")
            incompatible_skipped += 1
            continue
        if h.quantity_unit != ctx.quantity_unit:
            notes.append(f"{h.record_identity}:UNIT_MISMATCH_NOT_AGGREGATED")
            incompatible_skipped += 1
            continue
        if not _finite_nonneg(h.quantity):
            statuses.append(EvidenceFindingStatus.INVALID_QUANTITY)
            notes.append(f"{h.record_identity}:INVALID_HISTORICAL_QUANTITY_EXCLUDED")
            incompatible_skipped += 1
            continue
        # Contractual acceptance ≠ physically confirmed quantity
        if h.quantity_basis == QuantityBasis.ACCEPTED:
            notes.append(
                f"{h.record_identity}:"
                "CONTRACTUALLY_ACCEPTED_NE_PHYSICALLY_CONFIRMED_NOT_SUMMED_AS_PHYSICAL"
            )
            continue
        if h.quantity_basis == QuantityBasis.CLAIMED:
            notes.append(f"{h.record_identity}:CLAIMED_HISTORY_NOT_SUMMED_AS_CONFIRMED")
            continue
        if h.quantity_basis != QuantityBasis.PREVIOUSLY_CONFIRMED or not h.confirmed:
            notes.append(
                f"{h.record_identity}:NOT_PREVIOUSLY_CONFIRMED_PHYSICAL_NOT_SUMMED"
            )
            continue
        # Fixture E: two records of one previously confirmed execution event
        event_key = (h.execution_event_reference or "").strip()
        if event_key:
            if event_key in seen_events:
                notes.append(
                    f"{h.record_identity}:"
                    "DUPLICATE_HISTORICAL_EVENT_REPRESENTATION_NOT_DOUBLE_COUNTED"
                )
                continue
            seen_events.add(event_key)
        prior += float(h.quantity)

    # If incompatible records were present alongside COMPLETE claim, do not
    # silently ignore them into an authoritative complete-history result when
    # they were the only records / or when INCOMPATIBLE was expected — already
    # handled for HistoryCompleteness.INCOMPATIBLE. For COMPLETE with skipped
    # incompatible peers, note uncertainty but keep computable physical sum.
    if incompatible_skipped:
        notes.append(
            f"incompatible_historical_records_skipped={incompatible_skipped};"
            "NOT_SILENTLY_TREATED_AS_COMPATIBLE"
        )

    remaining = float(ctx.basis_quantity) - prior
    notes.append(
        f"remaining_before_new_claim={remaining};basis={ctx.basis_quantity};prior={prior}"
    )

    # Fixture F: historical confirmed exceeds basis — preserve contradiction
    if prior > float(ctx.basis_quantity):
        statuses.append(EvidenceFindingStatus.HISTORICAL_QUANTITY_BASIS_CONTRADICTION)
        notes.append(
            "HISTORICAL_CONFIRMED_EXCEEDS_BASIS;"
            "REMAINING_NOT_CLAMPED_TO_ZERO;"
            f"raw_remaining={remaining}"
        )
        # Keep negative remaining explicit; do not hide overrun

    # Fixture G: prior==0 with COMPLETE + authorized basis is valid zero history
    if prior == 0.0:
        notes.append(
            "ZERO_PREVIOUS_CONFIRMED_WITHIN_SUPPLIED_COMPLETE_HISTORY_AUTHORITY;"
            "MISSING_HISTORY_NE_ZERO_HISTORY"
        )

    excess = None
    if claimed_probe is not None:
        # Compare against raw remaining (may be negative after overrun)
        if float(claimed_probe) > remaining:
            excess = float(claimed_probe) - remaining
            statuses.append(EvidenceFindingStatus.POTENTIAL_QUANTITY_EXCESS)
            notes.append(
                "POTENTIAL_QUANTITY_EXCESS_NE_AUTOMATIC_PAYMENT_REJECTION;"
                "QUANTITY_CHECK_NE_SPATIAL_OVERLAP"
            )
        else:
            notes.append(
                "NO_QUANTITY_EXCEEDANCE_NE_SPATIAL_UNIQUENESS;"
                "SPATIAL_RELATION_MAY_REMAIN_UNRESOLVED"
            )
            statuses.append(EvidenceFindingStatus.SPATIAL_OVERLAP_NOT_EVALUATED)
    return remaining, excess, statuses, notes


def evaluate_s08(
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
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    execution_claims: Sequence[ExecutionClaimRef] = (),
    evidence_items: Sequence[EvidenceItem] = (),
    evidence_requirements: Sequence[EvidenceRequirementSpec] = (),
    historical_execution: Sequence[HistoricalExecutionRecord] = (),
    quantity_contexts: Sequence[QuantityContext] = (),
    authorized_project_scopes: Sequence[str] = (),
    production_evidence_requirements_available: bool = False,
) -> ShiftEvidenceValidationArtifact:
    """Validate evidence metadata / applicability. Never mutates inputs."""
    aid = audit_id or s01.audit_id or str(uuid.uuid4())
    project = audit_input.project_code
    work_date = audit_input.work_date
    scopes = tuple(authorized_project_scopes) or (project,)

    s01_total = s01.s01_metrics.claimed_total_man_minutes
    scenario_cost = s04.cost_conservation.total_calculated_direct_labor_cost_exact

    # Build default claims from operations if none supplied
    claims: list[ExecutionClaimRef] = list(execution_claims)
    if not claims:
        for i, op in enumerate(audit_input.operations):
            claims.append(
                ExecutionClaimRef(
                    execution_event_identity=f"claimed_event:{i}:{op.operation_name}",
                    physical_object_reference=op.physical_object_hint,
                    operation_code=None,
                    operation_name=op.operation_name,
                    claimed_quantity=op.physical_quantity,
                    quantity_unit=op.physical_unit,
                    source_operation_identity=f"op:{i}:{op.operation_name}",
                )
            )
        # Enrich operation codes from S10 when available
        by_name = {
            c.original_operation_text: c.operation_code_candidate
            for c in getattr(s10, "classifications", ()) or ()
        }
        claims = [
            ExecutionClaimRef(
                **{
                    **c.__dict__,
                    "operation_code": by_name.get(c.operation_name or "") or c.operation_code,
                }
            )
            for c in claims
        ]

    findings: list[EvidenceValidationFinding] = []
    meta_ok = 0
    multi_rep = 0
    pot_dup = 0
    rem_ok = 0
    excess_n = 0

    # Index evidence by event / identity for replay detection
    by_evidence_id: dict[str, list[EvidenceItem]] = defaultdict(list)
    for e in evidence_items:
        by_evidence_id[e.evidence_identity].append(e)

    # S07 hypotheses must not auto-promote to established cause
    s07_established = sum(
        1
        for h in s07.hypotheses
        if h.causal_status == CausalStatus.CAUSE_NOT_ESTABLISHED
    )
    # Always stamp that S07 causes remain unestablished
    _ = s07_established

    qty_by_key = {
        (q.physical_object_reference, q.operation_code or ""): q for q in quantity_contexts
    }

    for claim in claims:
        claim_findings_statuses: list[EvidenceFindingStatus] = []
        claim_notes: list[str] = []
        claim_missing: list[str] = []
        applied_evidence: list[EvidenceItem] = []
        representation_types: list[str] = []
        applicability = "NOT_EVALUATED"
        authority = EvidenceAuthority.CLAIMED_REFERENCE

        # Always: claimed execution is layer A — not physical verification
        claim_findings_statuses.append(EvidenceFindingStatus.PHYSICAL_EXECUTION_NOT_VERIFIED)
        claim_notes.append("CLAIMED_EXECUTION_NE_PHYSICAL_EXECUTION_VERIFICATION")
        claim_notes.append("EVIDENCE_CONTENT_VALIDATION_NOT_IMPLEMENTED")
        claim_notes.append("GEOMETRIC_OVERLAP_NOT_EVALUATED")
        claim_findings_statuses.append(EvidenceFindingStatus.SPATIAL_OVERLAP_NOT_EVALUATED)

        # Attach applicable evidence
        for item in evidence_items:
            ok, notes, st = _evidence_applicable(
                item,
                project_code=project,
                claim=claim,
                authorized_project_scopes=scopes,
            )
            claim_notes.extend(notes)
            if not ok:
                claim_findings_statuses.extend(st)
                continue

            # Exact evidence identity replay → not a new physical event
            if len(by_evidence_id.get(item.evidence_identity, ())) > 1:
                claim_notes.append(
                    f"{item.evidence_identity}:EXACT_EVIDENCE_REPLAY_NE_NEW_PHYSICAL_EVENT"
                )

            # New source version ≠ automatic new execution
            if item.source_version:
                claim_notes.append(
                    f"{item.evidence_identity}:SOURCE_VERSION_NE_AUTOMATIC_NEW_EXECUTION"
                )

            claim_findings_statuses.append(EvidenceFindingStatus.EVIDENCE_REFERENCE_PRESENT)
            if item.content_reference is None and item.content_hash is None:
                claim_notes.append(
                    f"{item.evidence_identity}:MISSING_CONTENT_REFERENCE_NOT_FABRICATED"
                )
                claim_findings_statuses.append(
                    EvidenceFindingStatus.EVIDENCE_CONTENT_NOT_VERIFIED
                )
            else:
                # Reference present ≠ content verified
                claim_findings_statuses.append(
                    EvidenceFindingStatus.EVIDENCE_CONTENT_NOT_VERIFIED
                )
                claim_notes.append(
                    f"{item.evidence_identity}:CONTENT_REFERENCE_PRESENT_NE_CONTENT_VERIFIED"
                )
                if item.evidence_type == EvidenceType.PHOTOGRAPHIC:
                    claim_notes.append(
                        f"{item.evidence_identity}:PHOTO_ATTACHMENT_NE_QUANTITY_PROOF"
                    )

            if _metadata_complete(item):
                claim_findings_statuses.append(
                    EvidenceFindingStatus.EVIDENCE_METADATA_VALIDATED
                )
                meta_ok += 1
                authority = EvidenceAuthority.METADATA_VALIDATED
                claim_notes.append(
                    f"{item.evidence_identity}:METADATA_VALIDATION_NE_PHYSICAL_VERIFICATION"
                )
            else:
                claim_missing.append(f"{item.evidence_identity}:incomplete_metadata")

            # Untrusted supplied authority does not grant permissions / escalate
            if item.supplied_validation_authority:
                claim_notes.append(
                    f"{item.evidence_identity}:UNTRUSTED_SUPPLIED_AUTHORITY_DOES_NOT_GRANT_PERMISSIONS"
                )
                supplied = str(item.supplied_validation_authority).upper()
                if any(
                    tok in supplied
                    for tok in (
                        "VERIFIED",
                        "CONTENT_VERIFIED",
                        "PHYSICAL_EXECUTION_VERIFIED",
                        "TRUSTED",
                        "ACCEPTED",
                    )
                ):
                    claim_notes.append(
                        f"{item.evidence_identity}:"
                        "UNTRUSTED_VERIFIED_CLAIM_REJECTED_AUTHORITY_NOT_ESCALATED"
                    )
                # Hard rule: engine never assigns CONTENT_VERIFIED / PHYSICAL from caller
                if authority in (
                    EvidenceAuthority.CONTENT_VERIFIED,
                    EvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED,
                ):
                    authority = EvidenceAuthority.METADATA_VALIDATED

            claim_notes.extend(_spatial_limitations(item.spatial_references))
            for sr in item.spatial_references:
                representation_types.append(sr.representation_type.value)
                # Contradictory object mapping on spatial ref vs claim/evidence
                if (
                    sr.physical_object_identity
                    and claim.physical_object_reference
                    and sr.physical_object_identity.strip()
                    != claim.physical_object_reference.strip()
                ):
                    claim_findings_statuses.append(
                        EvidenceFindingStatus.CONTRADICTORY_OBJECT_MAPPING
                    )
                    claim_notes.append(
                        f"{sr.spatial_reference_identity}:"
                        "CONTRADICTORY_SPATIAL_OBJECT_MAPPING"
                    )
                if (
                    sr.physical_object_identity
                    and item.physical_object_reference
                    and sr.physical_object_identity.strip()
                    != item.physical_object_reference.strip()
                ):
                    claim_findings_statuses.append(
                        EvidenceFindingStatus.CONTRADICTORY_OBJECT_MAPPING
                    )
                    claim_notes.append(
                        f"{sr.spatial_reference_identity}:"
                        "SPATIAL_OBJECT_NE_EVIDENCE_OBJECT"
                    )
                if not sr.physical_object_identity and claim.physical_object_reference:
                    claim_notes.append(
                        f"{sr.spatial_reference_identity}:MISSING_OBJECT_MAPPING_UNCERTAINTY"
                    )

            if item.polarity == EvidencePolarity.SUPPORTING:
                claim_findings_statuses.append(
                    EvidenceFindingStatus.SUPPORTING_EVIDENCE_CONTEXT
                )
            elif item.polarity == EvidencePolarity.CONTRADICTING:
                claim_findings_statuses.append(
                    EvidenceFindingStatus.CONTRADICTING_EVIDENCE_CONTEXT
                )

            # RD revision applicability
            if item.applicable_rd_revision and claim.rd_revision:
                if item.applicable_rd_revision != claim.rd_revision:
                    claim_findings_statuses.append(
                        EvidenceFindingStatus.REVISION_MAPPING_NOT_PROVEN
                    )
                    claim_notes.append(
                        f"{item.evidence_identity}:REVISION_MAPPING_NOT_PROVEN"
                    )
            elif item.applicable_rd_revision or claim.rd_revision:
                claim_findings_statuses.append(
                    EvidenceFindingStatus.REVISION_MAPPING_NOT_PROVEN
                )

            applied_evidence.append(item)
            applicability = "METADATA_APPLICABILITY_CHECKED"

        # Authority ceiling in this increment: never above METADATA_VALIDATED
        if authority in (
            EvidenceAuthority.CONTENT_VERIFIED,
            EvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED,
        ):
            authority = EvidenceAuthority.METADATA_VALIDATED
            claim_notes.append("AUTHORITY_CEILING_METADATA_VALIDATED_IN_THIS_INCREMENT")

        # Source-version conflict for same source_identity without authoritative current
        by_src: dict[str, set[str]] = defaultdict(set)
        for e in applied_evidence:
            if e.source_identity and e.source_version:
                by_src[e.source_identity].add(e.source_version)
        for src, versions in by_src.items():
            if len(versions) > 1:
                claim_findings_statuses.append(
                    EvidenceFindingStatus.SOURCE_VERSION_AUTHORITY_UNCERTAIN
                )
                claim_notes.append(
                    f"{src}:CONTRADICTING_SOURCE_VERSIONS_NOT_SILENTLY_RESOLVED;"
                    f"versions={sorted(versions)};"
                    "AUTHORITATIVE_CURRENT_VERSION_NOT_ESTABLISHED"
                )

        # Duplicate source_identity copies ≠ independent confirmations
        src_counts: dict[str, int] = defaultdict(int)
        for e in applied_evidence:
            if e.source_identity:
                src_counts[e.source_identity] += 1
        for src, n in src_counts.items():
            if n > 1:
                claim_notes.append(
                    f"{src}:DUPLICATE_SOURCE_REPRESENTATIONS_NE_INDEPENDENT_CONFIRMATIONS;"
                    "NO_MAJORITY_VOTING"
                )

        # Multiple drawing revisions attached to same event
        revs = {
            sr.revision_identity
            for e in applied_evidence
            for sr in e.spatial_references
            if sr.revision_identity
        }
        if len(revs) > 1:
            claim_findings_statuses.append(
                EvidenceFindingStatus.REVISION_MAPPING_NOT_PROVEN
            )
            claim_notes.append(
                f"MULTIPLE_DRAWING_REVISIONS_ON_SAME_EVENT={sorted(revs)};"
                "REVISION_MAPPING_NOT_PROVEN"
            )

        # Multiple representations of same event
        unique_reps = tuple(sorted(set(representation_types)))
        if len(unique_reps) >= 2 and claim.claimed_quantity is not None:
            claim_findings_statuses.append(
                EvidenceFindingStatus.MULTIPLE_REPRESENTATIONS_SAME_EVENT
            )
            multi_rep += 1
            claim_notes.append(
                "ONE_PHYSICAL_OBJECT_NE_ONE_DRAWING_REPRESENTATION;"
                "MULTIPLE_REPRESENTATIONS_DO_NOT_MULTIPLY_QUANTITY_OR_LABOR;"
                f"claimed_quantity_preserved={claim.claimed_quantity};"
                f"evidence_count={len(applied_evidence)};execution_event_count=1"
            )

        # Polarity conflict
        pols = {e.polarity for e in applied_evidence}
        if (
            EvidencePolarity.SUPPORTING in pols
            and EvidencePolarity.CONTRADICTING in pols
        ):
            claim_findings_statuses.append(
                EvidenceFindingStatus.CONFLICTING_EVIDENCE_CONTEXT
            )
            claim_notes.append(
                "SUPPORTING_AND_CONTRADICTING_EVIDENCE_PRESERVED;"
                "NO_MAJORITY_VOTING"
            )

        # Requirements
        req, req_st, req_notes = _requirement_for(
            claim,
            evidence_requirements,
            production_requirements_available=production_evidence_requirements_available,
        )
        claim_findings_statuses.extend(req_st)
        claim_notes.extend(req_notes)
        if req is not None:
            claim_notes.append(
                f"requirement={req.requirement_identity}/{req.authority}/"
                f"{req.version};DEMONSTRATION_REQUIREMENT_NE_APPROVED_NORM"
            )
            present_types = {e.evidence_type for e in applied_evidence}
            missing_types = [
                t.value for t in req.required_evidence_types if t not in present_types
            ]
            if missing_types:
                claim_findings_statuses.append(EvidenceFindingStatus.EVIDENCE_MISSING)
                claim_missing.extend(missing_types)
                claim_notes.append(
                    "MISSING_EVIDENCE_NE_PROOF_OF_NON_EXECUTION;"
                    "REQUIRED_TYPE_PRESENT_NE_ALL_REQUIREMENTS_MET"
                )
        elif not production_evidence_requirements_available:
            claim_notes.append("PRODUCTION_EVIDENCE_REQUIREMENT_NOT_ESTABLISHED")

        # Inherit S07 expected evidence as missing-context hints (not established cause)
        for hyp in s07.hypotheses:
            if claim.operation_code and hyp.affected_operation_code == claim.operation_code:
                for need in hyp.expected_supporting_evidence[:3]:
                    if need not in claim_missing:
                        claim_missing.append(f"s07_expected:{need}")
                claim_notes.append(
                    "S07_HYPOTHESIS_NE_ESTABLISHED_CAUSE;"
                    f"hyp={hyp.hypothesis_identity}"
                )

        # Potential duplicate candidates (identity-based only — not geometric)
        peers = [
            c
            for c in claims
            if c.execution_event_identity != claim.execution_event_identity
            and c.physical_object_reference
            and claim.physical_object_reference
            and c.physical_object_reference == claim.physical_object_reference
        ]
        same_op_peers = [
            c for c in peers if c.operation_code and c.operation_code == claim.operation_code
        ]
        diff_op_peers = [
            c for c in peers if c.operation_code and claim.operation_code and c.operation_code != claim.operation_code
        ]
        if diff_op_peers:
            claim_notes.append(
                "SAME_OBJECT_DIFFERENT_OPERATIONS_NE_DUPLICATE_EXECUTION"
            )
        if same_op_peers:
            # Potential duplicate candidate — not proven
            claim_findings_statuses.append(EvidenceFindingStatus.POTENTIAL_DUPLICATE_CLAIM)
            pot_dup += 1
            claim_notes.append(
                "POTENTIAL_DUPLICATE_NE_PROVEN_DUPLICATION;"
                "SAME_OBJECT_SAME_OPERATION_NE_AUTOMATIC_DUPLICATE;"
                "REWORK_NE_AUTOMATIC_DUPLICATE"
            )

        # Remaining quantity
        qctx = qty_by_key.get(
            (claim.physical_object_reference or "", claim.operation_code or "")
        )
        if qctx is None and claim.physical_object_reference:
            qctx = qty_by_key.get((claim.physical_object_reference, ""))

        remaining, excess, q_st, q_notes = _remaining_quantity(
            qctx, historical_execution, claim
        )
        claim_findings_statuses.extend(q_st)
        claim_notes.extend(q_notes)
        if remaining is not None:
            rem_ok += 1
        if excess is not None:
            excess_n += 1

        # Deduplicate statuses preserving order
        statuses = tuple(dict.fromkeys(claim_findings_statuses))
        next_action = (
            "Supply applicable evidence with content validation (S08-D future) "
            "and physical execution verification (S08-E future); "
            "Human Gate retains acceptance."
        )
        if EvidenceFindingStatus.EVIDENCE_MISSING in statuses:
            next_action = (
                "Provide missing required evidence types relative to explicit "
                "requirement; do not treat absence as non-execution proof."
            )
        if EvidenceFindingStatus.POTENTIAL_QUANTITY_EXCESS in statuses:
            next_action = (
                "Clarify quantity basis, prior confirmed history, and spatial "
                "relation; quantity excess is not automatic payment rejection."
            )
        if EvidenceFindingStatus.POTENTIAL_DUPLICATE_CLAIM in statuses:
            next_action = (
                "Clarify whether events are rework, new report version, or "
                "distinct execution; do not delete source history."
            )

        conclusion = (
            f"S08 metadata/applicability check for event "
            f"{claim.execution_event_identity}. "
            f"Evidence refs={len(applied_evidence)}. "
            "ATTACHED≠VALIDATED. MARKUP≠VERIFIED. "
            "PHYSICAL_EXECUTION_NOT_VERIFIED. "
            "No automatic managerial/commercial acceptance."
        )

        findings.append(
            EvidenceValidationFinding(
                finding_identity=f"s08:find:{claim.execution_event_identity}",
                finding_statuses=statuses,
                linked_execution_event=claim.execution_event_identity,
                physical_object_reference=claim.physical_object_reference,
                operation_reference=claim.operation_code or claim.operation_name,
                evidence_references=tuple(e.evidence_identity for e in applied_evidence),
                expected_evidence_requirement=(
                    req.requirement_identity if req is not None else None
                ),
                applicability_status=applicability,
                authority=authority,
                professional_conclusion=conclusion,
                missing_context=tuple(dict.fromkeys(claim_missing)),
                next_recommended_verification_action=next_action,
                claimed_quantity=claim.claimed_quantity,
                quantity_unit=claim.quantity_unit,
                remaining_quantity=remaining,
                potential_excess_quantity=excess,
                evidence_count=len(applied_evidence),
                execution_event_count=1,
                representation_types=unique_reps,
                limitations=tuple(dict.fromkeys(claim_notes)),
                provenance=(
                    f"rules={S08_RULES_VERSION}",
                    f"s05_chronology={s05.chronology_status}",
                    f"s07_hypotheses={len(s07.hypotheses)}",
                    f"s03_findings={len(getattr(s03, 'findings', ()) or ())}",
                    f"s02_findings={len(getattr(s02, 'findings', ()) or ())}",
                    f"s06_signals={len(s06.signals)}",
                    f"s11_labor_no_unit={s11.labor_conservation.labor_without_computable_unit_indicators_man_minutes}",
                ),
            )
        )

    summary = ShiftEvidenceSummary(
        finding_count=len(findings),
        evidence_item_count=len(evidence_items),
        metadata_validated_count=meta_ok,
        content_verified_count=0,
        physical_execution_verified_count=0,
        multiple_representation_event_count=multi_rep,
        potential_duplicate_count=pot_dup,
        remaining_quantity_computable_count=rem_ok,
        potential_excess_count=excess_n,
        total_original_labor_man_minutes=float(s01_total) if s01_total is not None else None,
        scenario_direct_labor_cost_exact=scenario_cost,
        professional_conclusion=(
            f"S08 evidence metadata/applicability complete. "
            f"Findings={len(findings)}. Content validation NOT implemented. "
            f"Physical execution NOT verified. Geometry overlap NOT evaluated. "
            f"Managerial acceptance NOT_IN_SCOPE. "
            f"s01_labor={s01_total}; s04_scenario_cost={scenario_cost}."
        ),
        notes=(
            "ATTACHED_EVIDENCE_NE_VALIDATED_EVIDENCE",
            "MARKUP_NE_VERIFIED_PHYSICAL_EXECUTION",
            "ONE_PHYSICAL_OBJECT_NE_ONE_DRAWING_REPRESENTATION",
            "EVIDENCE_REFERENCE_NE_CONTENT_PROOF",
            "METADATA_VALIDATION_NE_PHYSICAL_VERIFICATION",
            "MISSING_EVIDENCE_NE_PROOF_OF_NON_EXECUTION",
            "SAME_OBJECT_DIFFERENT_OPERATIONS_NE_DUPLICATE",
            "POTENTIAL_DUPLICATE_NE_PROVEN_DUPLICATION",
            "MISSING_HISTORY_NE_ZERO_PREVIOUS_QUANTITY",
            "QUANTITY_CHECK_NE_SPATIAL_OVERLAP",
            "NO_QUANTITY_EXCEEDANCE_NE_SPATIAL_UNIQUENESS",
            "S07_HYPOTHESIS_NE_ESTABLISHED_CAUSE",
            "DEMONSTRATION_REQUIREMENT_NE_APPROVED_PRODUCTION_NORM",
            "CONTRACTUALLY_ACCEPTED_NE_PHYSICALLY_CONFIRMED",
            "MISSING_HISTORY_NE_ZERO_HISTORY",
            "HISTORICAL_OVERRUN_NOT_CLAMPED_TO_ZERO",
            "UNTRUSTED_SUPPLIED_AUTHORITY_NE_TRUSTED_STATUS",
            "NO_MAJORITY_VOTING",
            "GEOMETRIC_OVERLAP_ENGINE_IMPLEMENTED_NO",
            "EVIDENCE_CONTENT_VALIDATION_IMPLEMENTED_NO",
            "PHYSICAL_EXECUTION_VERIFIED_NO",
            "COST_DEVIATION_ENGINE_IMPLEMENTED_NO",
            "COST_DEVIATION_BOUNDARIES_ONLY_YES",
            f"demo_requirement_version={S08_DEMO_REQUIREMENT_VERSION}",
        ),
    )

    observations = (
        "S08 = deterministic evidence metadata/applicability skill.",
        "Layers A/B/C within tested scope; D/E not implemented.",
        "ATTACHED EVIDENCE != VALIDATED EVIDENCE.",
        "MARKUP != VERIFIED PHYSICAL EXECUTION.",
        "ONE PHYSICAL OBJECT != ONE DRAWING REPRESENTATION.",
        "Spatial Execution Evidence compatibility: typed references only.",
        "No Django map editor / CAD / BIM / CV / geometry engine.",
        "No payroll / fraud / commercial / managerial acceptance.",
    )

    return ShiftEvidenceValidationArtifact(
        schema_version=S08_ARTIFACT_SCHEMA_VERSION,
        rules_version=S08_RULES_VERSION,
        audit_id=aid,
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=_utc_now(),
        project_code=project,
        work_date=work_date,
        crew_id=audit_input.crew_id,
        findings=tuple(findings),
        shift_summary=summary,
        observations=observations,
        managerial_acceptance_status="NOT_IN_SCOPE",
        commercial_acceptance_status="NOT_IN_SCOPE",
        payroll_decision_status="NOT_PERFORMED",
        disciplinary_decision_status="NOT_PERFORMED",
        fraud_classification_status="NOT_PERFORMED",
        human_readable_summary=summary.professional_conclusion,
    )
