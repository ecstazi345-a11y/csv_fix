"""S07 — Root Cause Analysis (deterministic).

Converts prior professional findings into testable causal hypotheses.
Does NOT establish root cause from correlation alone.
Does NOT assign blame, send tasks, or validate evidence (S08).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.catalogs.cause_categories_v0_1 import (
    CAUSE_CATALOG_VERSION,
    CauseCategory,
    catalog_entry,
)
from agents.production_shift_auditor.contracts import ShiftAuditArtifact, ShiftAuditInput
from agents.production_shift_auditor.s02_contracts import ShiftTechnologicalIntegrityArtifact
from agents.production_shift_auditor.s03_contracts import ShiftPhysicalIntegrityArtifact
from agents.production_shift_auditor.s04_contracts import ShiftExecutionCostArtifact
from agents.production_shift_auditor.s05_contracts import ShiftTemporalIntegrityArtifact
from agents.production_shift_auditor.s06_contracts import (
    ShiftStatisticalAnomalyArtifact,
    SignalType,
    StatisticalSignalStatus,
)
from agents.production_shift_auditor.s07_contracts import (
    S07_ARTIFACT_SCHEMA_VERSION,
    S07_RULES_VERSION,
    CauseHypothesis,
    CausalContextAuthority,
    CausalContextItem,
    CausalContextKind,
    CausalContextPolarity,
    CausalEvidenceAuthority,
    CausalStatus,
    FindingDomain,
    FindingIntakeRecord,
    InvestigationDisposition,
    ReviewPriority,
    ShiftRootCauseArtifact,
    ShiftRootCauseSummary,
    SuggestedClarificationRole,
)
from agents.production_shift_auditor.s10_contracts import ShiftOperationClassificationArtifact
from agents.production_shift_auditor.s11_contracts import ShiftLaborBenchmarkArtifact

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"

# S06 statuses that warrant production-deviation causal hypotheses
_ACTIONABLE_ANOMALY_STATUSES = frozenset(
    {
        StatisticalSignalStatus.STATISTICAL_ANOMALY_CANDIDATE,
        StatisticalSignalStatus.THRESHOLD_EXCEEDANCE,
    }
)

# Descriptive / non-investigation statuses
_DESCRIPTIVE_SKIP_TYPES = frozenset(
    {
        SignalType.LABOR_CONCENTRATION,
        SignalType.ROUNDING_PATTERN,
        SignalType.REPEATED_VALUE,
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _role_for(category: CauseCategory) -> SuggestedClarificationRole:
    raw = catalog_entry(category).typical_clarification_role
    try:
        return SuggestedClarificationRole(raw)
    except ValueError:
        return SuggestedClarificationRole.FOREMAN


def _priority_from_s06(raw: object, *, economic_boost: bool) -> ReviewPriority:
    name = getattr(raw, "value", str(raw))
    mapping = {
        "INFORMATION": ReviewPriority.INFORMATION,
        "REVIEW_CANDIDATE": ReviewPriority.REVIEW_CANDIDATE,
        "CLARIFICATION_REQUIRED": ReviewPriority.CLARIFICATION_REQUIRED,
        "HIGH_REVIEW_PRIORITY": ReviewPriority.HIGH_REVIEW_PRIORITY,
    }
    base = mapping.get(name, ReviewPriority.REVIEW_CANDIDATE)
    if economic_boost and base == ReviewPriority.REVIEW_CANDIDATE:
        return ReviewPriority.CLARIFICATION_REQUIRED
    if economic_boost and base == ReviewPriority.CLARIFICATION_REQUIRED:
        return ReviewPriority.HIGH_REVIEW_PRIORITY
    return base


def _context_applicable(
    ctx: CausalContextItem,
    *,
    project_code: str,
    work_date: str,
    operation_code: Optional[str],
    physical_object: Optional[str],
    work_package: Optional[str],
    authorized_project_scopes: Sequence[str],
    allow_future_context: bool,
) -> tuple[bool, Optional[str], tuple[str, ...]]:
    """Return (applicable, rejection_note, limitation_notes).

    Same project ≠ same physical object.
    Same physical object ≠ same technological operation.
    Same shift ≠ automatic causal relationship.
    Future occurrence ≠ automatic cause of earlier deviation.
    Later-created document may describe earlier occurrence only with
    explicit temporal applicability (occurrence_time or applicable window).
    """
    limitations: list[str] = []
    if ctx.polarity == CausalContextPolarity.IRRELEVANT_SCOPE:
        return False, f"{ctx.context_identity}:IRRELEVANT_SCOPE_NOT_APPLIED", ()

    if ctx.project_code and ctx.project_code != project_code:
        if ctx.project_code not in authorized_project_scopes and project_code not in authorized_project_scopes:
            return False, f"{ctx.context_identity}:CROSS_PROJECT_BLOCKED_WITHOUT_AUTHORIZED_SCOPE", ()
        if ctx.project_code not in authorized_project_scopes:
            return False, f"{ctx.context_identity}:CROSS_PROJECT_BLOCKED_WITHOUT_AUTHORIZED_SCOPE", ()

    if ctx.physical_object_reference and physical_object:
        if ctx.physical_object_reference.strip() != physical_object.strip():
            return False, (
                f"{ctx.context_identity}:OTHER_PHYSICAL_OBJECT_NOT_AUTO_APPLIED"
            ), ()
    elif ctx.physical_object_reference and not physical_object:
        # Context bound to a specific object cannot attach to unbound finding
        return False, (
            f"{ctx.context_identity}:PHYSICAL_OBJECT_REQUIRED_FOR_SCOPED_CONTEXT"
        ), ()
    elif physical_object and not ctx.physical_object_reference:
        # Project/shift-wide context is not object-specific causal evidence
        limitations.append(
            f"{ctx.context_identity}:PROJECT_OR_SHIFT_WIDE_CONTEXT_NE_OBJECT_SPECIFIC_CAUSAL_EVIDENCE"
        )

    if ctx.operation_code and operation_code and ctx.operation_code != operation_code:
        return False, f"{ctx.context_identity}:OPERATION_MISMATCH_NOT_APPLIED", ()
    if operation_code and not ctx.operation_code:
        limitations.append(
            f"{ctx.context_identity}:OPERATION_UNSPECIFIED_CONTEXT_NE_OPERATION_SPECIFIC_EVIDENCE"
        )

    if ctx.work_package_identity and work_package:
        if ctx.work_package_identity.strip() != work_package.strip():
            return False, f"{ctx.context_identity}:WORK_PACKAGE_MISMATCH_NOT_APPLIED", ()
    elif ctx.work_package_identity and not work_package:
        return False, (
            f"{ctx.context_identity}:WORK_PACKAGE_REQUIRED_FOR_SCOPED_CONTEXT"
        ), ()
    elif work_package and not ctx.work_package_identity:
        limitations.append(
            f"{ctx.context_identity}:PACKAGE_UNSPECIFIED_CONTEXT_NE_PACKAGE_SPECIFIC_EVIDENCE"
        )

    # --- Temporal causality (occurrence ≠ document creation) ---
    occ = ctx.occurrence_time
    if occ and not allow_future_context and occ > work_date:
        return False, (
            f"{ctx.context_identity}:FUTURE_OCCURRENCE_NOT_AUTOMATIC_CAUSE"
        ), ()

    # applicable window
    if ctx.applicable_from and not allow_future_context:
        if ctx.applicable_from > work_date:
            return False, f"{ctx.context_identity}:FUTURE_CONTEXT_NOT_SILENTLY_APPLIED", ()
    if ctx.applicable_to and ctx.applicable_to < work_date and not allow_future_context:
        return False, f"{ctx.context_identity}:CONTEXT_OUTSIDE_SHIFT_APPLICABILITY", ()

    # Later-created document without proven earlier occurrence / applicability
    doc = ctx.document_created_at
    if doc and doc > work_date and not allow_future_context:
        covers = False
        if occ and occ <= work_date:
            covers = True
            limitations.append(
                f"{ctx.context_identity}:LATER_RECORDED_HISTORICAL_EVIDENCE"
            )
        elif ctx.applicable_from and ctx.applicable_from <= work_date and (
            ctx.applicable_to is None or ctx.applicable_to >= work_date
        ):
            covers = True
            limitations.append(
                f"{ctx.context_identity}:LATER_DOCUMENT_WITH_RETROSPECTIVE_APPLICABILITY"
            )
        if not covers:
            return False, (
                f"{ctx.context_identity}:"
                "LATER_DOCUMENT_WITHOUT_TEMPORAL_APPLICABILITY_NOT_AUTO_CAUSE"
            ), ()

    if not ctx.source_identity:
        limitations.append(
            f"{ctx.context_identity}:MISSING_SOURCE_IDENTITY_UNCERTAINTY_PRESERVED"
        )

    return True, None, tuple(limitations)


def _match_kind_to_category(kind: CausalContextKind) -> Optional[CauseCategory]:
    return {
        CausalContextKind.PHYSICAL_COMPLEXITY: CauseCategory.ENGINEERING_PHYSICAL_COMPLEXITY,
        CausalContextKind.MATERIAL_SPECIFICATION: CauseCategory.TECHNOLOGY_AND_MATERIAL,
        CausalContextKind.TECHNOLOGY_DIFFERENCE: CauseCategory.TECHNOLOGY_AND_MATERIAL,
        CausalContextKind.WORK_FRONT_RESTRICTION: CauseCategory.FRONT_READINESS_ORGANIZATIONAL,
        CausalContextKind.MATERIAL_WAITING: CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY,
        CausalContextKind.ALTERNATIVE_PRODUCTIVE_WORK: (
            CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY
        ),
        CausalContextKind.REWORK_EVENT: CauseCategory.REWORK_AND_QUALITY,
        CausalContextKind.RD_REVISION_CHANGE: CauseCategory.REWORK_AND_QUALITY,
        CausalContextKind.LABOR_CONDITION: CauseCategory.LABOR_AND_EXECUTION_CONDITIONS,
        CausalContextKind.OPERATION_AGGREGATION: CauseCategory.SOURCE_DATA_AND_REPORTING_QUALITY,
        CausalContextKind.REPORTING_POLICY: CauseCategory.SOURCE_DATA_AND_REPORTING_QUALITY,
        CausalContextKind.REFERENCE_COMPARABILITY_LIMITATION: (
            CauseCategory.REFERENCE_AND_COMPARISON_LIMITATIONS
        ),
    }.get(kind)


def _resolve_status(
    supporting: Sequence[CausalContextItem],
    contradicting: Sequence[CausalContextItem],
) -> CausalStatus:
    if supporting and contradicting:
        return CausalStatus.CONFLICTING_CONTEXT
    if supporting:
        return CausalStatus.SUPPORTING_CONTEXT_AVAILABLE
    if contradicting:
        return CausalStatus.CONTRADICTORY_CONTEXT_AVAILABLE
    return CausalStatus.INSUFFICIENT_CONTEXT


def _authority_from_contexts(
    supporting: Sequence[CausalContextItem],
    contradicting: Sequence[CausalContextItem],
    *,
    default: CausalEvidenceAuthority,
) -> CausalEvidenceAuthority:
    items = list(supporting) + list(contradicting)
    if not items:
        return default
    ranks = {
        CausalContextAuthority.CLAIMED: CausalEvidenceAuthority.CLAIMED_CONTEXT,
        CausalContextAuthority.DOCUMENTED: CausalEvidenceAuthority.DOCUMENTED_CONTEXT,
        CausalContextAuthority.CONFIRMED: CausalEvidenceAuthority.CONFIRMED_CONTEXT,
        CausalContextAuthority.VERIFIED_FACT: CausalEvidenceAuthority.CONFIRMED_CONTEXT,
    }
    # Strongest supplied authority still ≠ established causation
    order = [
        CausalContextAuthority.VERIFIED_FACT,
        CausalContextAuthority.CONFIRMED,
        CausalContextAuthority.DOCUMENTED,
        CausalContextAuthority.CLAIMED,
    ]
    for a in order:
        if any(c.authority == a for c in items):
            return ranks[a]
    return default


def _evidence_bundle(category: CauseCategory) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Expected supporting / contradictory evidence templates (S07 defines need; S08 validates)."""
    bundles: dict[CauseCategory, tuple[tuple[str, ...], tuple[str, ...]]] = {
        CauseCategory.ENGINEERING_PHYSICAL_COMPLEXITY: (
            (
                "applicable_RD_revision",
                "plan_or_axonometric_representation",
                "dimensions",
                "physical_object_identity",
                "material",
            ),
            (
                "standard_geometry_confirmation",
                "same_complexity_peer_observation",
            ),
        ),
        CauseCategory.TECHNOLOGY_AND_MATERIAL: (
            (
                "material_specification",
                "fabrication_method_record",
                "technology_card_reference",
            ),
            (
                "identical_technology_confirmation",
                "same_material_peer_observation",
            ),
        ),
        CauseCategory.FRONT_READINESS_ORGANIZATIONAL: (
            (
                "work_front_restriction_record",
                "admission_status",
                "predecessor_completion_evidence",
            ),
            (
                "front_ready_confirmation",
                "alternative_work_availability",
            ),
        ),
        CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY: (
            (
                "material_issue_event",
                "required_material_identity",
                "link_to_required_operation",
                "temporal_applicability",
                "waiting_time_interval",
                "alternative_work_context",
            ),
            (
                "on_time_issue_confirmation",
                "alternative_productive_work_confirmation",
                "tool_availability_confirmation",
            ),
        ),
        CauseCategory.REWORK_AND_QUALITY: (
            (
                "previous_execution_event",
                "defect_or_revision_reference",
                "repeated_execution_record",
                "same_physical_object_relation",
            ),
            (
                "first_pass_execution_confirmation",
                "no_revision_confirmation",
            ),
        ),
        CauseCategory.LABOR_AND_EXECUTION_CONDITIONS: (
            (
                "allocation_record",
                "crew_composition",
                "interruption_log",
                "productive_vs_elapsed_clarification",
            ),
            (
                "stable_allocation_confirmation",
                "no_interruption_confirmation",
            ),
        ),
        CauseCategory.SOURCE_DATA_AND_REPORTING_QUALITY: (
            (
                "original_reported_operation",
                "claimed_labor_breakdown",
                "distinct_operations_split",
                "source_version",
            ),
            (
                "atomic_operation_confirmation",
                "quantity_unit_correction",
            ),
        ),
        CauseCategory.REFERENCE_AND_COMPARISON_LIMITATIONS: (
            (
                "comparable_historical_population",
                "technology_conditions_match",
                "benchmark_authority",
            ),
            (
                "verified_comparable_reference",
            ),
        ),
    }
    return bundles[category]


def _question_for(
    category: CauseCategory,
    *,
    op_name: Optional[str],
    finding_summary: str,
) -> str:
    op = op_name or "the reported operation"
    templates = {
        CauseCategory.ENGINEERING_PHYSICAL_COMPLEXITY: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"was physical complexity (geometry/dimensions/accessibility) "
            f"materially different from the comparison basis?"
        ),
        CauseCategory.TECHNOLOGY_AND_MATERIAL: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"did material, thickness, or fabrication/installation technology "
            f"differ from the comparison basis?"
        ),
        CauseCategory.FRONT_READINESS_ORGANIZATIONAL: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"was the work front unavailable, restricted, or blocked by "
            f"incomplete predecessor works during the shift?"
        ),
        CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"was there a documented material/tool delay linked to this operation, "
            f"and was alternative work available?"
        ),
        CauseCategory.REWORK_AND_QUALITY: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"does the claimed labor include rework, defect correction, or "
            f"RD-revision-related repeated execution on the same physical object?"
        ),
        CauseCategory.LABOR_AND_EXECUTION_CONDITIONS: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"can allocation, interruptions, or productive-versus-elapsed time "
            f"uncertainty explain the claimed figure without implying a root cause?"
        ),
        CauseCategory.SOURCE_DATA_AND_REPORTING_QUALITY: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"is the claim an aggregated reporting row, missing quantity/unit, "
            f"or ambiguous labor semantics rather than a single atomic execution?"
        ),
        CauseCategory.REFERENCE_AND_COMPARISON_LIMITATIONS: (
            f"Regarding observation «{finding_summary}» on «{op}»: "
            f"is the historical/benchmark reference population comparable on "
            f"technology, conditions, and object class?"
        ),
    }
    return templates[category]


def _build_hypothesis(
    *,
    finding_id: str,
    domain: FindingDomain,
    disposition: InvestigationDisposition,
    project_code: str,
    source_obs: tuple[str, ...],
    op_identity: Optional[str],
    op_code: Optional[str],
    op_name: Optional[str],
    physical_object: Optional[str],
    category: CauseCategory,
    cause_desc: str,
    reasoning: str,
    finding_summary: str,
    review_priority: ReviewPriority,
    default_authority: CausalEvidenceAuthority,
    supporting: Sequence[CausalContextItem],
    contradicting: Sequence[CausalContextItem],
    extra_missing: Sequence[str] = (),
    extra_limitations: Sequence[str] = (),
) -> CauseHypothesis:
    exp_sup, exp_con = _evidence_bundle(category)
    status = _resolve_status(supporting, contradicting)
    # Without any context, still a generated hypothesis with insufficient context
    if status == CausalStatus.INSUFFICIENT_CONTEXT:
        # Keep distinct: generated + insufficient
        pass
    authority = _authority_from_contexts(
        supporting, contradicting, default=default_authority
    )
    missing = list(extra_missing)
    for e in exp_sup:
        if not any(e.lower() in (c.description or "").lower() for c in supporting):
            if e not in missing:
                missing.append(e)
    if not supporting and not contradicting:
        status = CausalStatus.INSUFFICIENT_CONTEXT

    # Supporting context ≠ proven causal relationship — never escalate to established
    conclusion_bits = [
        f"Possible cause ({category.value}): {cause_desc}.",
        f"Causal status={status.value}.",
        "SUPPORTING_CONTEXT_NE_PROVEN_CAUSAL_RELATIONSHIP.",
        "CAUSE_NOT_ESTABLISHED.",
        "SUGGESTED_CLARIFICATION_ROLE_NE_RESPONSIBLE_PARTY.",
    ]
    conclusion_bits.extend(extra_limitations)

    # Initial status when no context: HYPOTHESIS_GENERATED with insufficient noted
    if not supporting and not contradicting:
        status = CausalStatus.HYPOTHESIS_GENERATED
        missing = tuple(dict.fromkeys([*missing, "typed_causal_context"]))
    else:
        missing = tuple(dict.fromkeys(missing))

    return CauseHypothesis(
        hypothesis_identity=f"s07:hyp:{finding_id}:{category.value}",
        linked_finding_identity=finding_id,
        finding_domain=domain,
        investigation_disposition=disposition,
        project_scope=project_code,
        source_observation_identities=source_obs,
        affected_operation_identity=op_identity,
        affected_operation_code=op_code,
        affected_operation_name=op_name,
        physical_object_reference=physical_object,
        cause_category=category,
        possible_cause_description=cause_desc,
        reasoning_basis=reasoning,
        expected_supporting_evidence=exp_sup,
        expected_contradictory_evidence=exp_con,
        supplied_supporting_context_refs=tuple(c.context_identity for c in supporting),
        supplied_contradicting_context_refs=tuple(
            c.context_identity for c in contradicting
        ),
        missing_context=tuple(missing) if isinstance(missing, (list, tuple)) else (missing,),
        targeted_clarification_question=_question_for(
            category, op_name=op_name, finding_summary=finding_summary
        ),
        suggested_clarification_role=_role_for(category),
        review_priority=review_priority,
        causal_status=status
        if supporting or contradicting
        else CausalStatus.HYPOTHESIS_GENERATED,
        evidence_authority=authority,
        provenance=(
            f"rules={S07_RULES_VERSION}",
            f"catalog={CAUSE_CATALOG_VERSION}",
            f"linked_finding={finding_id}",
            *(f"ctx_support={c.context_identity}/{c.authority.value}" for c in supporting),
            *(
                f"ctx_contra={c.context_identity}/{c.authority.value}"
                for c in contradicting
            ),
        ),
        rules_version=S07_RULES_VERSION,
        catalog_version=CAUSE_CATALOG_VERSION,
        professional_conclusion=" ".join(conclusion_bits),
    )


_AUTHORITY_RANK = {
    CausalContextAuthority.CLAIMED: 1,
    CausalContextAuthority.DOCUMENTED: 2,
    CausalContextAuthority.CONFIRMED: 3,
    CausalContextAuthority.VERIFIED_FACT: 4,
}


def _collapse_duplicate_sources(
    items: list[CausalContextItem],
    rejected: list[str],
) -> list[CausalContextItem]:
    """Multiple copies of the same source_identity are not independent evidence."""
    best: dict[str, CausalContextItem] = {}
    order: list[str] = []
    for ctx in items:
        key = (ctx.source_identity or "").strip() or ctx.context_identity
        if key not in best:
            best[key] = ctx
            order.append(key)
            continue
        prev = best[key]
        if _AUTHORITY_RANK.get(ctx.authority, 0) > _AUTHORITY_RANK.get(prev.authority, 0):
            rejected.append(
                f"{ctx.context_identity}:DUPLICATE_SOURCE_REPRESENTATION_NOT_INDEPENDENT_EVIDENCE"
                f"(kept={prev.context_identity}->upgraded)"
            )
            best[key] = ctx
        else:
            rejected.append(
                f"{ctx.context_identity}:DUPLICATE_SOURCE_REPRESENTATION_NOT_INDEPENDENT_EVIDENCE"
                f"(kept={prev.context_identity})"
            )
    return [best[k] for k in order]


def _filter_contexts_for_hypothesis(
    contexts: Sequence[CausalContextItem],
    *,
    category: CauseCategory,
    project_code: str,
    work_date: str,
    operation_code: Optional[str],
    physical_object: Optional[str],
    work_package: Optional[str],
    authorized_project_scopes: Sequence[str],
    allow_future_context: bool,
) -> tuple[list[CausalContextItem], list[CausalContextItem], list[str], list[str]]:
    supporting: list[CausalContextItem] = []
    contradicting: list[CausalContextItem] = []
    rejected: list[str] = []
    limitations: list[str] = []
    for ctx in contexts:
        ok, note, lims = _context_applicable(
            ctx,
            project_code=project_code,
            work_date=work_date,
            operation_code=operation_code,
            physical_object=physical_object,
            work_package=work_package,
            authorized_project_scopes=authorized_project_scopes,
            allow_future_context=allow_future_context,
        )
        if not ok:
            if note:
                rejected.append(note)
            continue
        limitations.extend(lims)
        mapped = _match_kind_to_category(ctx.context_kind)
        # OTHER can attach if explicitly same operation; otherwise skip auto
        if mapped is not None and mapped != category:
            continue
        if mapped is None and ctx.context_kind != CausalContextKind.OTHER:
            continue
        if mapped is None and category not in (
            CauseCategory.SOURCE_DATA_AND_REPORTING_QUALITY,
            CauseCategory.LABOR_AND_EXECUTION_CONDITIONS,
            CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY,
        ):
            continue
        if ctx.polarity == CausalContextPolarity.SUPPORTING:
            supporting.append(ctx)
        elif ctx.polarity == CausalContextPolarity.CONTRADICTING:
            contradicting.append(ctx)
        elif ctx.polarity == CausalContextPolarity.AMBIGUOUS:
            # Ambiguous contributes to conflict pressure if paired later
            contradicting.append(ctx)
            supporting.append(ctx)
    supporting = _collapse_duplicate_sources(supporting, rejected)
    contradicting = _collapse_duplicate_sources(contradicting, rejected)
    return supporting, contradicting, rejected, limitations


def _dedupe_questions(hypotheses: list[CauseHypothesis]) -> list[CauseHypothesis]:
    """Collapse duplicate clarification questions for the same uncertainty key.

    Same question text across different physical objects / operations must NOT
    be merged — object and operation identity are part of the key.
    """
    seen: dict[str, int] = {}
    out: list[CauseHypothesis] = []
    for h in hypotheses:
        key = (
            f"{h.affected_operation_code or h.affected_operation_identity or ''}|"
            f"{h.physical_object_reference or ''}|"
            f"{h.cause_category.value}|"
            f"{h.linked_finding_identity}|"
            f"{h.targeted_clarification_question}"
        )
        if key in seen:
            continue
        seen[key] = 1
        out.append(h)
    return out


def evaluate_s07(
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s10: ShiftOperationClassificationArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    s11: ShiftLaborBenchmarkArtifact,
    s04: ShiftExecutionCostArtifact,
    s05: ShiftTemporalIntegrityArtifact,
    s06: ShiftStatisticalAnomalyArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    causal_contexts: Sequence[CausalContextItem] = (),
    authorized_project_scopes: Sequence[str] = (),
    allow_future_context: bool = False,
) -> ShiftRootCauseArtifact:
    """Generate causal hypotheses from prior findings. Never mutates inputs."""
    aid = audit_id or s01.audit_id or str(uuid.uuid4())
    project = audit_input.project_code
    work_date = audit_input.work_date
    scopes = tuple(authorized_project_scopes) or (project,)

    intake: list[FindingIntakeRecord] = []
    hypotheses: list[CauseHypothesis] = []
    rejected_notes: list[str] = []
    applied_ctx: list[str] = []
    inherited_keys: set[str] = set()

    s01_total = s01.s01_metrics.claimed_total_man_minutes
    scenario_cost = s04.cost_conservation.total_calculated_direct_labor_cost_exact
    economic_boost = False
    if scenario_cost is not None:
        try:
            # Economic significance may raise review priority only
            economic_boost = float(scenario_cost) >= 10000.0
        except (TypeError, ValueError):
            economic_boost = False

    # Physical object hints from claims (by operation name)
    obj_by_name: dict[str, Optional[str]] = {}
    for claim in audit_input.operations:
        obj_by_name[claim.operation_name] = claim.physical_object_hint

    # --- S06 signal intake ---
    for sig in s06.signals:
        fid = sig.signal_identity
        op_code = sig.canonical_operation_code
        op_name = sig.canonical_operation_name
        op_identity = (
            sig.source_observation_identities[0]
            if sig.source_observation_identities
            else None
        )
        physical_object = obj_by_name.get(op_name or "", None)
        summary = f"{sig.signal_type.value}:{sig.metric}:{sig.status.value}"

        # Skip pure descriptive concentration / rounding / repeated
        if (
            sig.signal_type in _DESCRIPTIVE_SKIP_TYPES
            and sig.status
            in (
                StatisticalSignalStatus.DESCRIPTIVE_OBSERVATION,
                StatisticalSignalStatus.REPORTING_PRECISION_UNKNOWN,
            )
        ):
            intake.append(
                FindingIntakeRecord(
                    finding_identity=fid,
                    finding_domain=FindingDomain.S06_STATISTICAL,
                    disposition=InvestigationDisposition.NO_MANDATORY_INVESTIGATION,
                    source_observation_identities=sig.source_observation_identities,
                    operation_code=op_code,
                    operation_name=op_name,
                    summary=summary,
                    review_priority=ReviewPriority.INFORMATION,
                    notes=(
                        "DESCRIPTIVE_OBSERVATION_NE_MANDATORY_INVESTIGATION",
                        "ROUNDING_NE_FABRICATION"
                        if sig.signal_type == SignalType.ROUNDING_PATTERN
                        else "COST_CONCENTRATION_NE_INEFFICIENCY"
                        if sig.signal_type == SignalType.LABOR_CONCENTRATION
                        else "REPEATED_VALUE_NE_DUPLICATE_EXECUTION",
                        "NO_FABRICATION_HYPOTHESIS_FROM_LEGITIMATE_ROUNDING",
                    ),
                )
            )
            continue

        # Cost scenario boundary — not a production deviation case
        if sig.signal_type == SignalType.COST_DEVIATION and sig.status in (
            StatisticalSignalStatus.DESCRIPTIVE_OBSERVATION,
        ):
            intake.append(
                FindingIntakeRecord(
                    finding_identity=fid,
                    finding_domain=FindingDomain.S04_EXECUTION_COST,
                    disposition=InvestigationDisposition.NO_MANDATORY_INVESTIGATION,
                    source_observation_identities=sig.source_observation_identities,
                    operation_code=op_code,
                    operation_name=op_name,
                    summary=summary,
                    review_priority=ReviewPriority.INFORMATION,
                    notes=(
                        "SCENARIO_COST_NE_ACTUAL_COST",
                        "COST_MAGNITUDE_NE_STATISTICAL_ANOMALY",
                        "COST_DEVIATION_BOUNDARIES_ONLY",
                    ),
                )
            )
            continue

        # Reference / sample limitations → data quality, not production inefficiency
        if sig.status in (
            StatisticalSignalStatus.INSUFFICIENT_COMPARABLE_HISTORY,
            StatisticalSignalStatus.REFERENCE_NOT_AVAILABLE,
            StatisticalSignalStatus.REFERENCE_NOT_COMPARABLE,
        ):
            intake.append(
                FindingIntakeRecord(
                    finding_identity=fid,
                    finding_domain=FindingDomain.DATA_QUALITY,
                    disposition=InvestigationDisposition.DATA_QUALITY_LIMITATION,
                    source_observation_identities=sig.source_observation_identities,
                    operation_code=op_code,
                    operation_name=op_name,
                    summary=summary,
                    review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                    notes=(
                        "DATA_QUALITY_PROBLEM_NE_PRODUCTION_INEFFICIENCY",
                        "MISSING_HISTORY_NE_NORMAL_PERFORMANCE",
                    ),
                )
            )
            # Single hypothesis: reference limitation
            hyp = _make_with_context(
                contexts=causal_contexts,
                finding_id=fid,
                domain=FindingDomain.DATA_QUALITY,
                disposition=InvestigationDisposition.DATA_QUALITY_LIMITATION,
                project_code=project,
                work_date=work_date,
                source_obs=sig.source_observation_identities,
                op_identity=op_identity,
                op_code=op_code,
                op_name=op_name,
                physical_object=physical_object,
                category=CauseCategory.REFERENCE_AND_COMPARISON_LIMITATIONS,
                cause_desc=(
                    "Comparable historical reference population is missing, "
                    "insufficient, or not comparable."
                ),
                reasoning=(
                    "S06 reported reference/sample limitation; this is a comparison "
                    "boundary, not proof of poor productivity."
                ),
                finding_summary=summary,
                review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                default_authority=CausalEvidenceAuthority.OBSERVED_FINDING_ONLY,
                scopes=scopes,
                allow_future=allow_future_context,
                rejected_notes=rejected_notes,
                applied_ctx=applied_ctx,
            )
            hypotheses.append(hyp)
            continue

        # Inherited S05 — reuse once, do not create independent proof duplicates
        if sig.status == StatisticalSignalStatus.INHERITED_PROFESSIONAL_FINDING:
            key = "|".join(sig.source_observation_identities) + "|" + sig.metric
            if key in inherited_keys:
                intake.append(
                    FindingIntakeRecord(
                        finding_identity=fid,
                        finding_domain=FindingDomain.S05_TEMPORAL,
                        disposition=InvestigationDisposition.INHERITED_FINDING_REUSED,
                        source_observation_identities=sig.source_observation_identities,
                        operation_code=op_code,
                        operation_name=op_name,
                        summary=summary,
                        review_priority=ReviewPriority.INFORMATION,
                        notes=(
                            "DUPLICATE_INHERITED_FINDING_NOT_INDEPENDENT_PROOF",
                        ),
                    )
                )
                continue
            inherited_keys.add(key)
            intake.append(
                FindingIntakeRecord(
                    finding_identity=fid,
                    finding_domain=FindingDomain.S05_TEMPORAL,
                    disposition=InvestigationDisposition.INHERITED_FINDING_REUSED,
                    source_observation_identities=sig.source_observation_identities,
                    operation_code=op_code,
                    operation_name=op_name,
                    summary=summary,
                    review_priority=ReviewPriority.REVIEW_CANDIDATE,
                    notes=(
                        "INHERITED_S05_AUTHORITY_RETAINED",
                        "TEMPORAL_ASSOCIATION_NE_CAUSATION",
                    ),
                )
            )
            hyp = _make_with_context(
                contexts=causal_contexts,
                finding_id=fid,
                domain=FindingDomain.S05_TEMPORAL,
                disposition=InvestigationDisposition.INHERITED_FINDING_REUSED,
                project_code=project,
                work_date=work_date,
                source_obs=sig.source_observation_identities,
                op_identity=op_identity,
                op_code=op_code,
                op_name=op_name,
                physical_object=physical_object,
                category=CauseCategory.LABOR_AND_EXECUTION_CONDITIONS,
                cause_desc=(
                    "Claimed temporal/capacity conflict may reflect allocation, "
                    "interruption, or productive-vs-elapsed uncertainty."
                ),
                reasoning=(
                    "Inherited S05 finding reused; temporal association is not "
                    "treated as established causation."
                ),
                finding_summary=summary,
                review_priority=ReviewPriority.REVIEW_CANDIDATE,
                default_authority=CausalEvidenceAuthority.TEMPORAL_ASSOCIATION,
                scopes=scopes,
                allow_future=allow_future_context,
                rejected_notes=rejected_notes,
                applied_ctx=applied_ctx,
                extra_limitations=("TEMPORAL_ASSOCIATION_NE_CAUSATION",),
            )
            hypotheses.append(hyp)
            continue

        # ZERO_DISPERSION: investigate only when review candidate (Case B)
        if sig.status == StatisticalSignalStatus.ZERO_DISPERSION:
            if sig.review_priority.value == "INFORMATION" or (
                sig.deviation_value is not None and abs(float(sig.deviation_value)) < 1e-12
            ):
                intake.append(
                    FindingIntakeRecord(
                        finding_identity=fid,
                        finding_domain=FindingDomain.S06_STATISTICAL,
                        disposition=InvestigationDisposition.NO_MANDATORY_INVESTIGATION,
                        source_observation_identities=sig.source_observation_identities,
                        operation_code=op_code,
                        operation_name=op_name,
                        summary=summary,
                        review_priority=ReviewPriority.INFORMATION,
                        notes=(
                            "ZERO_DISPERSION_EQUAL_MEDIAN_NO_MANDATORY_INVESTIGATION",
                            "NO_DETECTED_ANOMALY_NE_VERIFIED_SHIFT",
                        ),
                    )
                )
                continue
            # Case B — treat like anomaly candidate for hypothesis generation
            pass

        actionable = (
            sig.status in _ACTIONABLE_ANOMALY_STATUSES
            or (
                sig.status == StatisticalSignalStatus.ZERO_DISPERSION
                and sig.review_priority.value
                in ("REVIEW_CANDIDATE", "CLARIFICATION_REQUIRED", "HIGH_REVIEW_PRIORITY")
            )
        )
        if not actionable:
            # Remaining informational S06 signals
            if sig.signal_type == SignalType.UNIT_LABOR_DEVIATION:
                # Still record; may be informational
                intake.append(
                    FindingIntakeRecord(
                        finding_identity=fid,
                        finding_domain=FindingDomain.S06_STATISTICAL,
                        disposition=InvestigationDisposition.NO_MANDATORY_INVESTIGATION,
                        source_observation_identities=sig.source_observation_identities,
                        operation_code=op_code,
                        operation_name=op_name,
                        summary=summary,
                        review_priority=ReviewPriority.INFORMATION,
                        notes=("NON_ACTIONABLE_STATISTICAL_SIGNAL",),
                    )
                )
            continue

        # Actionable unit-labor / anomaly candidate
        intake.append(
            FindingIntakeRecord(
                finding_identity=fid,
                finding_domain=FindingDomain.S06_STATISTICAL,
                disposition=InvestigationDisposition.PRODUCTION_DEVIATION_CANDIDATE,
                source_observation_identities=sig.source_observation_identities,
                operation_code=op_code,
                operation_name=op_name,
                summary=summary,
                review_priority=_priority_from_s06(
                    sig.review_priority, economic_boost=economic_boost
                ),
                notes=(
                    "ANOMALY_NE_ROOT_CAUSE",
                    "CORRELATION_NE_CAUSATION",
                    "STATISTICAL_ANOMALY_NE_PROVEN_VIOLATION",
                ),
            )
        )

        pri = _priority_from_s06(sig.review_priority, economic_boost=economic_boost)
        high = abs(float(sig.deviation_value or 0)) > 0 or (
            sig.observed_value is not None
            and sig.reference_value is not None
            and float(sig.observed_value) > float(sig.reference_value)
        )
        low = (
            sig.observed_value is not None
            and sig.reference_value is not None
            and float(sig.observed_value) < float(sig.reference_value)
        )
        direction = "higher" if high and not low else ("lower" if low else "deviant")

        # Relevant hypothesis set for unit-labor anomaly (not all catalog rows)
        category_specs: list[tuple[CauseCategory, str, str]] = [
            (
                CauseCategory.ENGINEERING_PHYSICAL_COMPLEXITY,
                f"Physical complexity may explain {direction} unit labor versus reference.",
                "Unit-labor anomaly candidate; complexity is a testable possible cause.",
            ),
            (
                CauseCategory.TECHNOLOGY_AND_MATERIAL,
                f"Technology or material differences may explain {direction} unit labor.",
                "Same operation code does not prove identical technology/material conditions.",
            ),
            (
                CauseCategory.REWORK_AND_QUALITY,
                "Claimed labor may include rework or repeated fabrication/installation.",
                "Rework hypothesis is not proven rework without linked execution evidence.",
            ),
            (
                CauseCategory.SOURCE_DATA_AND_REPORTING_QUALITY,
                "Operation aggregation or reporting composition may inflate claimed unit labor.",
                "Data-quality limitation must be distinguished from production inefficiency.",
            ),
            (
                CauseCategory.REFERENCE_AND_COMPARISON_LIMITATIONS,
                "Reference population may be incomplete or not comparable.",
                "Configured threshold exceedance ≠ statistical proof of root cause.",
            ),
        ]
        # Material delay / front readiness only if professionally applicable context present
        def _relevant(kind: CausalContextKind) -> bool:
            for c in causal_contexts:
                if c.context_kind != kind:
                    continue
                ok, _, _ = _context_applicable(
                    c,
                    project_code=project,
                    work_date=work_date,
                    operation_code=op_code,
                    physical_object=physical_object,
                    work_package=None,
                    authorized_project_scopes=scopes,
                    allow_future_context=allow_future_context,
                )
                if ok:
                    return True
            return False

        has_material_ctx = _relevant(CausalContextKind.MATERIAL_WAITING)
        has_front_ctx = _relevant(CausalContextKind.WORK_FRONT_RESTRICTION)
        if has_material_ctx:
            category_specs.append(
                (
                    CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY,
                    "Claimed material delay may be associated with the deviation; "
                    "not automatically the full cause.",
                    "MATERIAL_DELAY_NE_AUTOMATIC_FULL_CAUSE; claimed context ≠ verified fact.",
                )
            )
        if has_front_ctx:
            category_specs.append(
                (
                    CauseCategory.FRONT_READINESS_ORGANIZATIONAL,
                    "Work-front / admission constraint may be associated with the deviation.",
                    "Organizational constraint hypothesis requires scoped confirmation.",
                )
            )

        for cat, desc, reason in category_specs:
            hyp = _make_with_context(
                contexts=causal_contexts,
                finding_id=fid,
                domain=FindingDomain.S06_STATISTICAL,
                disposition=InvestigationDisposition.PRODUCTION_DEVIATION_CANDIDATE,
                project_code=project,
                work_date=work_date,
                source_obs=sig.source_observation_identities,
                op_identity=op_identity,
                op_code=op_code,
                op_name=op_name,
                physical_object=physical_object,
                category=cat,
                cause_desc=desc,
                reasoning=reason,
                finding_summary=summary,
                review_priority=pri,
                default_authority=CausalEvidenceAuthority.STATISTICAL_CORRELATION,
                scopes=scopes,
                allow_future=allow_future_context,
                rejected_notes=rejected_notes,
                applied_ctx=applied_ctx,
                extra_limitations=(
                    "ANOMALY_NE_ROOT_CAUSE",
                    "MULTIPLE_HYPOTHESES_NE_MULTIPLE_INDEPENDENT_LOSSES",
                    "HIGH_ECONOMIC_PRIORITY_NE_HIGH_CAUSAL_CERTAINTY",
                ),
            )
            # Material delay special stamp
            if cat == CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY:
                hyp = CauseHypothesis(
                    **{
                        **hyp.__dict__,
                        "professional_conclusion": (
                            hyp.professional_conclusion
                            + " MATERIAL_DELAY_NE_AUTOMATIC_FULL_CAUSE."
                            + " CLAIMED_CONTEXT_NE_VERIFIED_FACT."
                        ),
                    }
                )
            hypotheses.append(hyp)

    # --- S11 data-quality: labor without computable unit indicators ---
    no_unit = float(
        s11.labor_conservation.labor_without_computable_unit_indicators_man_minutes or 0
    )
    if no_unit > 0:
        fid = "s07:intake:s11:labor_without_unit"
        intake.append(
            FindingIntakeRecord(
                finding_identity=fid,
                finding_domain=FindingDomain.S11_LABOR_BENCHMARK,
                disposition=InvestigationDisposition.DATA_QUALITY_LIMITATION,
                source_observation_identities=(),
                operation_code=None,
                operation_name=None,
                summary=f"labor_without_computable_unit_indicators_mm={no_unit}",
                review_priority=ReviewPriority.INFORMATION,
                notes=(
                    "DATA_QUALITY_PROBLEM_NE_PRODUCTION_INEFFICIENCY",
                    "LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_LOSS",
                ),
            )
        )
        # Do not spawn mandatory multi-cause investigation for this alone

    # --- S10 classification uncertainty (sample) ---
    for f in getattr(s10, "classifications", ()) or ():
        status = getattr(f, "classification_status", None)
        status_name = getattr(status, "value", str(status or ""))
        if status_name in (
            "AMBIGUOUS",
            "UNKNOWN_OPERATION",
            "INSUFFICIENT_CONTEXT",
            "COMPOSITE_OPERATION",
        ):
            fid = f"s07:intake:s10:{getattr(f, 'source_operation_identity', 'unk')}"
            if any(i.finding_identity == fid for i in intake):
                continue
            intake.append(
                FindingIntakeRecord(
                    finding_identity=fid,
                    finding_domain=FindingDomain.S10_CLASSIFICATION,
                    disposition=InvestigationDisposition.DATA_QUALITY_LIMITATION,
                    source_observation_identities=(
                        getattr(f, "source_operation_identity", ""),
                    ),
                    operation_code=getattr(f, "operation_code_candidate", None),
                    operation_name=getattr(f, "canonical_operation_candidate", None)
                    or getattr(f, "original_operation_text", None),
                    summary=f"classification_uncertainty:{status_name}",
                    review_priority=ReviewPriority.REVIEW_CANDIDATE,
                    notes=("DATA_QUALITY_PROBLEM_NE_PRODUCTION_INEFFICIENCY",),
                )
            )

    # Dedupe clarification questions
    before = len(hypotheses)
    hypotheses = _dedupe_questions(hypotheses)
    deduped = before - len(hypotheses)

    # Ensure no hypothesis claims established cause
    final_hyps: list[CauseHypothesis] = []
    for h in hypotheses:
        if h.causal_status == CausalStatus.CAUSE_NOT_ESTABLISHED:
            final_hyps.append(h)
            continue
        # Append explicit cause-not-established stamp on conclusion
        final_hyps.append(
            CauseHypothesis(
                **{
                    **h.__dict__,
                    "professional_conclusion": (
                        h.professional_conclusion
                        + " ESTABLISHED_CAUSE=NO."
                        + " NO_CAUSAL_CONFIDENCE_PERCENT_INVENTED."
                    ),
                }
            )
        )

    investigated = sum(
        1
        for i in intake
        if i.disposition
        in (
            InvestigationDisposition.PRODUCTION_DEVIATION_CANDIDATE,
            InvestigationDisposition.DATA_QUALITY_LIMITATION,
            InvestigationDisposition.INHERITED_FINDING_REUSED,
        )
    )
    skipped = sum(
        1
        for i in intake
        if i.disposition == InvestigationDisposition.NO_MANDATORY_INVESTIGATION
    )
    dq = sum(
        1
        for i in intake
        if i.disposition == InvestigationDisposition.DATA_QUALITY_LIMITATION
    )
    questions = tuple(
        dict.fromkeys(h.targeted_clarification_question for h in final_hyps)
    )

    conclusion = (
        f"S07 generated {len(final_hyps)} causal hypotheses from prior findings. "
        f"Established cause count=0. "
        "ANOMALY≠ROOT CAUSE. CORRELATION≠CAUSATION. "
        "SUPPORTING CONTEXT≠PROVEN CAUSAL RELATIONSHIP. "
        "NO ESTABLISHED CAUSE ≠ VERIFIED NORMAL PERFORMANCE. "
        "Managerial acceptance NOT_IN_SCOPE."
    )
    if deduped:
        conclusion += f" Deduplicated clarification questions={deduped}."

    summary = ShiftRootCauseSummary(
        hypothesis_count=len(final_hyps),
        investigated_finding_count=investigated,
        skipped_descriptive_finding_count=skipped,
        data_quality_limitation_count=dq,
        clarification_question_count=len(questions),
        established_cause_count=0,
        total_original_labor_man_minutes=float(s01_total) if s01_total is not None else None,
        scenario_direct_labor_cost_exact=scenario_cost,
        professional_conclusion=conclusion,
        notes=(
            "ANOMALY_NE_ROOT_CAUSE",
            "CORRELATION_NE_CAUSATION",
            "TEMPORAL_ASSOCIATION_NE_CAUSATION",
            "POSSIBLE_CAUSE_NE_ESTABLISHED_CAUSE",
            "SUPPORTING_CONTEXT_NE_PROVEN_CAUSAL_RELATIONSHIP",
            "MISSING_EVIDENCE_NE_CONTRADICTING_EVIDENCE",
            "NO_SUPPORTING_EVIDENCE_NE_AUTOMATICALLY_FALSE_HYPOTHESIS",
            "MULTIPLE_HYPOTHESES_NE_MULTIPLE_INDEPENDENT_LOSSES",
            "HIGH_ECONOMIC_PRIORITY_NE_HIGH_CAUSAL_CERTAINTY",
            "SUGGESTED_CLARIFICATION_ROLE_NE_RESPONSIBLE_PARTY",
            "DATA_QUALITY_PROBLEM_NE_PRODUCTION_INEFFICIENCY",
            "NO_ESTABLISHED_CAUSE_NE_VERIFIED_NORMAL_PERFORMANCE",
            "COST_DEVIATION_ENGINE_IMPLEMENTED_NO",
            "COST_DEVIATION_BOUNDARIES_ONLY_YES",
            "ACTUAL_INCURRED_COST_NOT_PROVEN",
            "LATE_MATERIAL_ISSUE_NE_PROVEN_CREW_IDLE_TIME",
            "CONSTRAINT_DURATION_NE_PROVEN_LOST_MAN_HOURS",
            "FUTURE_OCCURRENCE_NE_AUTOMATIC_CAUSE",
            "LATER_DOCUMENT_NE_FUTURE_EVENT",
            "PROJECT_OR_SHIFT_WIDE_CONTEXT_NE_OBJECT_SPECIFIC_CAUSAL_EVIDENCE",
            "DUPLICATE_SOURCE_REPRESENTATION_NE_INDEPENDENT_EVIDENCE",
            "CONFIRMED_CONTEXTUAL_FACT_NE_CONFIRMED_CAUSAL_REFUTATION",
            "HYPOTHESIS_NOT_SUPPORTED_REQUIRES_EXPLICIT_CAUSAL_REFUTATION_MECHANISM",
            "S08_VALIDATES_EVIDENCE_S07_DEFINES_NEEDS",
            "SPATIAL_EXECUTION_EVIDENCE_DIRECTION_RETAINED_FOR_S08",
            f"s01_labor_preserved={s01_total}",
            f"s04_scenario_cost_preserved={scenario_cost}",
            f"s02_findings_reused={len(getattr(s02, 'findings', ()) or ())}",
            f"s03_findings_reused={len(getattr(s03, 'findings', ()) or ())}",
            f"s05_chronology={s05.chronology_status}",
            f"rejected_contexts={len(rejected_notes)}",
        ),
    )

    observations = (
        "S07 = deterministic root-cause hypothesis skill.",
        "ANOMALY != ROOT CAUSE.",
        "CORRELATION != CAUSATION.",
        "POSSIBLE CAUSE != ESTABLISHED CAUSE.",
        "SUPPORTING CONTEXT != PROVEN CAUSAL RELATIONSHIP.",
        "Suggested clarification questions are professional recommendations only.",
        "S08 Evidence Validation / Spatial Execution Evidence not implemented.",
        "No payroll / fraud / disciplinary / managerial acceptance.",
        "No causal confidence percentages or opaque root-cause scores.",
    )

    return ShiftRootCauseArtifact(
        schema_version=S07_ARTIFACT_SCHEMA_VERSION,
        rules_version=S07_RULES_VERSION,
        catalog_version=CAUSE_CATALOG_VERSION,
        audit_id=aid,
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=_utc_now(),
        project_code=project,
        work_date=work_date,
        crew_id=audit_input.crew_id,
        finding_intake=tuple(intake),
        hypotheses=tuple(final_hyps),
        applied_context_identities=tuple(dict.fromkeys(applied_ctx)),
        rejected_context_notes=tuple(dict.fromkeys(rejected_notes)),
        shift_summary=summary,
        observations=observations,
        managerial_acceptance_status="NOT_IN_SCOPE",
        payroll_decision_status="NOT_PERFORMED",
        disciplinary_decision_status="NOT_PERFORMED",
        fraud_classification_status="NOT_PERFORMED",
        human_readable_summary=conclusion,
    )


def _make_with_context(
    *,
    contexts: Sequence[CausalContextItem],
    finding_id: str,
    domain: FindingDomain,
    disposition: InvestigationDisposition,
    project_code: str,
    work_date: str,
    source_obs: tuple[str, ...],
    op_identity: Optional[str],
    op_code: Optional[str],
    op_name: Optional[str],
    physical_object: Optional[str],
    category: CauseCategory,
    cause_desc: str,
    reasoning: str,
    finding_summary: str,
    review_priority: ReviewPriority,
    default_authority: CausalEvidenceAuthority,
    scopes: Sequence[str],
    allow_future: bool,
    rejected_notes: list[str],
    applied_ctx: list[str],
    extra_limitations: Sequence[str] = (),
    work_package: Optional[str] = None,
) -> CauseHypothesis:
    supporting, contradicting, rejected, ctx_limits = _filter_contexts_for_hypothesis(
        contexts,
        category=category,
        project_code=project_code,
        work_date=work_date,
        operation_code=op_code,
        physical_object=physical_object,
        work_package=work_package,
        authorized_project_scopes=scopes,
        allow_future_context=allow_future,
    )
    rejected_notes.extend(rejected)
    # Context applicability limitations are recorded (not silent)
    for lim in ctx_limits:
        if lim not in rejected_notes:
            rejected_notes.append(lim)
    for c in supporting + contradicting:
        applied_ctx.append(c.context_identity)
    lim_bits: list[str] = list(extra_limitations)
    if any("PROJECT_OR_SHIFT_WIDE" in x for x in ctx_limits):
        lim_bits.append(
            "PROJECT_OR_SHIFT_WIDE_CONTEXT_NE_OBJECT_SPECIFIC_CAUSAL_EVIDENCE"
        )
    if category == CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY:
        lim_bits.append("LATE_MATERIAL_ISSUE_NE_PROVEN_CREW_IDLE_TIME")
        lim_bits.append("CONSTRAINT_DURATION_NE_PROVEN_LOST_MAN_HOURS")
    lim_bits.append("CONFIRMED_CONTEXTUAL_FACT_NE_CONFIRMED_CAUSAL_REFUTATION")
    lim_bits.append("NO_MAJORITY_VOTING_ON_DOCUMENT_COUNT")
    extra_limitations = tuple(dict.fromkeys(x for x in lim_bits if x))

    # AMBIGUOUS polarity is attached to both lists → treat as conflicting signal
    sup_ids = {c.context_identity for c in supporting}
    con_ids = {c.context_identity for c in contradicting}
    pure_supporting = [c for c in supporting if c.context_identity not in con_ids]
    pure_contradicting = [c for c in contradicting if c.context_identity not in sup_ids]
    ambiguous = [c for c in supporting if c.context_identity in con_ids]

    if ambiguous and not pure_supporting and not pure_contradicting:
        # Only ambiguous → CONFLICTING_CONTEXT
        hyp = _build_hypothesis(
            finding_id=finding_id,
            domain=domain,
            disposition=disposition,
            project_code=project_code,
            source_obs=source_obs,
            op_identity=op_identity,
            op_code=op_code,
            op_name=op_name,
            physical_object=physical_object,
            category=category,
            cause_desc=cause_desc,
            reasoning=reasoning,
            finding_summary=finding_summary,
            review_priority=review_priority,
            default_authority=default_authority,
            supporting=ambiguous,
            contradicting=ambiguous,
            extra_limitations=extra_limitations,
        )
        return CauseHypothesis(
            **{**hyp.__dict__, "causal_status": CausalStatus.CONFLICTING_CONTEXT}
        )

    hyp = _build_hypothesis(
        finding_id=finding_id,
        domain=domain,
        disposition=disposition,
        project_code=project_code,
        source_obs=source_obs,
        op_identity=op_identity,
        op_code=op_code,
        op_name=op_name,
        physical_object=physical_object,
        category=category,
        cause_desc=cause_desc,
        reasoning=reasoning,
        finding_summary=finding_summary,
        review_priority=review_priority,
        default_authority=default_authority,
        supporting=pure_supporting + ambiguous,
        contradicting=pure_contradicting + ambiguous,
        extra_limitations=extra_limitations,
    )
    if (pure_supporting or ambiguous) and (pure_contradicting or ambiguous):
        if pure_supporting and pure_contradicting or ambiguous:
            return CauseHypothesis(
                **{**hyp.__dict__, "causal_status": CausalStatus.CONFLICTING_CONTEXT}
            )
    if pure_supporting and not pure_contradicting and not ambiguous:
        return CauseHypothesis(
            **{
                **hyp.__dict__,
                "causal_status": CausalStatus.SUPPORTING_CONTEXT_AVAILABLE,
            }
        )
    if pure_contradicting and not pure_supporting and not ambiguous:
        return CauseHypothesis(
            **{
                **hyp.__dict__,
                "causal_status": CausalStatus.CONTRADICTORY_CONTEXT_AVAILABLE,
            }
        )
    return hyp
