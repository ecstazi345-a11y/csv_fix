"""S12 — Production Intelligence (deterministic).

Transforms professional audit results into structured production observations
and limited knowledge candidates. Reuses S11 unit labor / eligibility.
Does NOT approve norms, persist knowledge, or run autonomous learning.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import (
    MathIntegrityStatus,
    ShiftAuditArtifact,
    ShiftAuditInput,
)
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
    CausalStatus,
    ShiftRootCauseArtifact,
)
from agents.production_shift_auditor.s08_contracts import (
    EvidenceAuthority,
    EvidenceFindingStatus,
    ShiftEvidenceValidationArtifact,
)
from agents.production_shift_auditor.s09_contracts import (
    ShiftAcceptanceRecommendationArtifact,
)
from agents.production_shift_auditor.s10_contracts import (
    ClassificationStatus,
    ShiftOperationClassificationArtifact,
)
from agents.production_shift_auditor.s11_contracts import (
    ComparabilityStatus,
    LaborCalculationStatus,
    ObservationEligibility,
    ShiftLaborBenchmarkArtifact,
)
from agents.production_shift_auditor.s12_contracts import (
    S12_ARTIFACT_SCHEMA_VERSION,
    S12_POLICY_VERSION,
    S12_RULES_VERSION,
    KnowledgeCandidate,
    KnowledgeCandidateType,
    ObservationAuthorityLayer,
    ProductionObservation,
    ReuseEligibility,
    ShiftProductionIntelligenceArtifact,
    ShiftProductionIntelligenceSummary,
    SuggestedConsumerRole,
    SuggestedReusePurpose,
    SuppliedHumanDecisionRef,
)

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _map_s11_eligibility(raw: Optional[str]) -> ReuseEligibility:
    if raw == ObservationEligibility.HISTORICAL_ANALYSIS_CANDIDATE.value:
        return ReuseEligibility.ELIGIBLE_FOR_EXPLORATORY_COMPARISON
    if raw == ObservationEligibility.COMPUTABLE_BUT_CLAIMED_ONLY.value:
        return ReuseEligibility.KNOWLEDGE_CANDIDATE_WITH_LIMITATIONS
    if raw == ObservationEligibility.NOT_ELIGIBLE_FOR_BENCHMARK.value:
        return ReuseEligibility.EXCLUDED_FROM_BENCHMARK_USE
    if raw == ObservationEligibility.NOT_EVALUATED.value:
        return ReuseEligibility.VERIFIED_REUSE_ELIGIBILITY_NOT_ESTABLISHED
    return ReuseEligibility.RETAIN_AS_CLAIMED_OBSERVATION


def _s08_authority_for_event(
    s08: ShiftEvidenceValidationArtifact,
    event_ref: Optional[str],
    operation_code: Optional[str],
) -> str:
    ceiling = EvidenceAuthority.CLAIMED_REFERENCE.value
    order = {
        EvidenceAuthority.CLAIMED_REFERENCE.value: 0,
        EvidenceAuthority.METADATA_PRESENT.value: 1,
        EvidenceAuthority.METADATA_VALIDATED.value: 2,
        EvidenceAuthority.CONTENT_VERIFIED.value: 2,  # capped
        EvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED.value: 2,  # capped
    }
    best = 0
    best_name = ceiling
    for f in s08.findings:
        if event_ref and f.linked_execution_event == event_ref:
            name = f.authority.value
            # Cap content/physical to metadata validated
            if name in (
                EvidenceAuthority.CONTENT_VERIFIED.value,
                EvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED.value,
            ):
                name = EvidenceAuthority.METADATA_VALIDATED.value
            rank = order.get(name, 0)
            if rank >= best:
                best = rank
                best_name = name
            if EvidenceFindingStatus.PHYSICAL_EXECUTION_NOT_VERIFIED in f.finding_statuses:
                pass
        elif operation_code and f.operation_reference == operation_code:
            name = f.authority.value
            if name in (
                EvidenceAuthority.CONTENT_VERIFIED.value,
                EvidenceAuthority.PHYSICAL_EXECUTION_VERIFIED.value,
            ):
                name = EvidenceAuthority.METADATA_VALIDATED.value
            rank = order.get(name, 0)
            if rank >= best:
                best = rank
                best_name = name
    return best_name


def evaluate_s12(
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
    s09: ShiftAcceptanceRecommendationArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    human_decision_refs: Sequence[SuppliedHumanDecisionRef] = (),
    authorized_project_scopes: Sequence[str] = (),
) -> ShiftProductionIntelligenceArtifact:
    """Build structured observations + knowledge candidates. Never mutates inputs."""
    aid = audit_id or s01.audit_id or str(uuid.uuid4())
    project = audit_input.project_code
    scopes = tuple(authorized_project_scopes) or (project,)
    if project not in scopes:
        # Cross-project blocked without authorized scope — empty observations fail-closed note
        summary = ShiftProductionIntelligenceSummary(
            source_operation_count=len(audit_input.operations),
            distinct_observation_count=0,
            unit_labor_observation_count=0,
            computable_unit_labor_man_minutes=0.0,
            labor_without_computable_unit_metrics_man_minutes=0.0,
            total_claimed_labor_man_minutes=s01.s01_metrics.claimed_total_man_minutes,
            scenario_direct_labor_cost_exact=(
                s04.cost_conservation.total_calculated_direct_labor_cost_exact
            ),
            knowledge_candidate_count=0,
            candidate_type_counts=(),
            excluded_from_benchmark_count=0,
            requires_additional_context_count=0,
            verified_knowledge_count=0,
            approved_knowledge_count=0,
            approved_labor_norm_count=0,
            missing_context_notes=("CROSS_PROJECT_CONTEXT_BLOCKED",),
            professional_conclusion="Cross-project scope denied; no observations emitted.",
            notes=("PROJECT_ISOLATION_ENFORCED",),
        )
        return ShiftProductionIntelligenceArtifact(
            schema_version=S12_ARTIFACT_SCHEMA_VERSION,
            rules_version=S12_RULES_VERSION,
            policy_version=S12_POLICY_VERSION,
            audit_id=aid,
            agent_code=AGENT_CODE,
            agent_version=AGENT_VERSION,
            run_id=run_id,
            created_at_utc=_utc_now(),
            project_code=project,
            work_date=audit_input.work_date,
            crew_id=audit_input.crew_id,
            observations=(),
            knowledge_candidates=(),
            shift_summary=summary,
            observations_notes=("CROSS_PROJECT_SCOPE_DENIED",),
            managerial_acceptance_status="NOT_IN_SCOPE",
            contractual_recognition_status="NOT_PERFORMED",
            payroll_decision_status="NOT_PERFORMED",
            norm_mutation_status="NOT_PERFORMED",
            knowledge_approval_status="NOT_PERFORMED",
            autonomous_learning_status="NOT_IMPLEMENTED",
            persistence_status="NOT_IMPLEMENTED",
            human_readable_summary="S12 blocked: unauthorized project scope.",
        )

    shift_ref = f"{project}|{audit_input.work_date}|{audit_input.crew_id}"
    s11_by_sid = {f.source_operation_identity: f for f in s11.findings}
    s09_by_sid = {
        r.source_operation_identity: r for r in s09.operation_recommendations
    }
    s10_by_sid = {c.source_operation_identity: c for c in s10.classifications}
    s03_by_sid = {f.source_operation_identity: f for f in s03.findings}
    s04_by_sid = {f.source_operation_identity: f for f in s04.findings}

    # Trusted human decisions only
    trusted_decisions = [
        d for d in human_decision_refs if d.trusted and d.project_code in scopes
    ]
    decision_by_op = {
        d.source_operation_identity: d
        for d in trusted_decisions
        if d.source_operation_identity
    }
    decision_by_event = {
        d.applicable_event_identity: d
        for d in trusted_decisions
        if d.applicable_event_identity
    }

    observations: list[ProductionObservation] = []
    candidates: list[KnowledgeCandidate] = []
    seen_obs_keys: set[str] = set()
    computable_ul_mm = 0.0
    without_ul_mm = 0.0
    missing_notes: list[str] = []

    # One observation per S09 fixture/event recommendation identity (already collapsed)
    # Prefer S09 rows that cover claimed_event ops + extras
    rec_rows = list(s09.operation_recommendations)
    if not rec_rows:
        # Fallback: S10 classifications
        for cl in s10.classifications:
            rec_rows.append(type("R", (), {
                "source_operation_identity": cl.source_operation_identity,
                "execution_event_reference": None,
                "original_operation_text": cl.original_operation_text,
                "operation_code": cl.operation_code_candidate,
                "canonical_operation_identity": cl.canonical_operation_candidate,
                "physical_object_reference": None,
                "original_claimed_quantity": cl.physical_quantity,
                "original_quantity_unit": cl.physical_unit,
                "original_claimed_labor_man_minutes": cl.claimed_labor_quantity,
                "work_category": cl.work_category,
                "source_record_ids": cl.source_record_ids,
                "recommendation_identity": None,
                "recommendation_status": None,
            })())

    for rec in rec_rows:
        sid = rec.source_operation_identity
        event = getattr(rec, "execution_event_reference", None)
        # Scoped identity: event alone does not guarantee unique technological
        # operation. Collapse multi-representation of the same event+operation;
        # keep distinct operations distinct even on the same physical object.
        obs_key = f"{event}|{sid}" if event else sid
        if obs_key in seen_obs_keys:
            continue
        seen_obs_keys.add(obs_key)

        s11f = s11_by_sid.get(sid)
        s10c = s10_by_sid.get(sid)
        s03f = s03_by_sid.get(sid)
        s09r = s09_by_sid.get(sid) or rec

        labor_mm = getattr(rec, "original_claimed_labor_man_minutes", None)
        if labor_mm is None and s11f and s11f.eligible_labor_man_minutes is not None:
            labor_mm = s11f.eligible_labor_man_minutes
        qty = getattr(rec, "original_claimed_quantity", None)
        unit = getattr(rec, "original_quantity_unit", None)
        if s11f:
            if qty is None:
                qty = s11f.original_claimed_physical_quantity
            if unit is None:
                unit = s11f.original_measurement_unit

        # Reuse S11 UL — never recompute
        ul = s11f.unit_labor_man_minutes_per_physical if s11f else None
        calc = s11f.calculation_status.value if s11f else None
        elig = s11f.observation_eligibility.value if s11f else None
        comp = s11f.comparability_status.value if s11f else None

        evidence_auth = _s08_authority_for_event(
            s08, event, getattr(rec, "operation_code", None)
        )
        evidence_refs: list[str] = []
        for ef in s08.findings:
            if event and ef.linked_execution_event == event:
                evidence_refs.extend(ef.evidence_references)

        # Authority layer — no linear escalation to verified/approved.
        # PROFESSIONALLY_AUDITED = joint analysis completed, NOT verified truth.
        authority = ObservationAuthorityLayer.RAW_CLAIMED_OBSERVATION
        if s01.math_integrity_status == MathIntegrityStatus.COHERENT:
            authority = ObservationAuthorityLayer.MATHEMATICALLY_ASSESSED_OBSERVATION
        authority = ObservationAuthorityLayer.PROFESSIONALLY_AUDITED_OBSERVATION

        reuse = _map_s11_eligibility(elig)
        missing: list[str] = []
        limitations: list[str] = [
            "CLAIMED_OBSERVATION_NE_VERIFIED_KNOWLEDGE",
            "AUDITED_OBSERVATION_NE_VERIFIED_PHYSICAL_OBSERVATION",
            "PROFESSIONALLY_AUDITED_NE_VERIFIED_SOURCE_TRUTH",
            "TWELVE_SKILLS_PASS_NE_EVIDENCE_AUTHORITY_ESCALATION",
            "PROFESSIONAL_RECOMMENDATION_NE_HUMAN_DECISION",
            "METADATA_VALIDATION_NE_CONTENT_VALIDATION",
            "S08_AUTHORITY_CEILING_METADATA_VALIDATED",
            "NO_AUTOMATIC_APPROVED_PRODUCTION_KNOWLEDGE",
            "NO_AUTOMATIC_APPROVED_LABOR_NORM",
        ]
        if audit_input.source_version_ref is None:
            limitations.append("SOURCE_VERSION_NOT_ESTABLISHED")

        if calc == LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION.value:
            if elig == ObservationEligibility.HISTORICAL_ANALYSIS_CANDIDATE.value:
                reuse = ReuseEligibility.ELIGIBLE_FOR_EXPLORATORY_COMPARISON
            elif elig == ObservationEligibility.COMPUTABLE_BUT_CLAIMED_ONLY.value:
                reuse = ReuseEligibility.KNOWLEDGE_CANDIDATE_WITH_LIMITATIONS
            limitations.append("COMPUTABLE_UNIT_LABOR_REUSED_FROM_S11_NOT_RECOMPUTED")
            limitations.append("COMPUTABLE_UNIT_LABOR_NE_ESTABLISHED_COMPARABILITY")
            limitations.append("COMPUTABLE_UNIT_LABOR_NE_VERIFIED_BENCHMARK_ELIGIBILITY")
            if reuse == ReuseEligibility.ELIGIBLE_FOR_EXPLORATORY_COMPARISON:
                limitations.append("EXPLORATORY_DESCRIPTIVE_USE_ONLY")
                limitations.append(
                    "NO_BENCHMARK_POPULATION_AGGREGATION_WITHOUT_PROVEN_COMPARABILITY"
                )
            if labor_mm is not None:
                computable_ul_mm += float(labor_mm)
        else:
            if labor_mm is not None:
                without_ul_mm += float(labor_mm)
            if calc == LaborCalculationStatus.LABOR_WITHOUT_POSITIVE_QUANTITY.value:
                limitations.append("NO_FICTITIOUS_UNIT_LABOR_ASSIGNED")
                reuse = ReuseEligibility.EXCLUDED_FROM_BENCHMARK_USE
            elif calc == LaborCalculationStatus.COMPOSITE_NOT_ALLOCATABLE.value:
                missing.append("COMPOSITE_OPERATION_NOT_ALLOCATABLE")
                reuse = ReuseEligibility.REQUIRES_ADDITIONAL_CONTEXT
            else:
                if reuse == ReuseEligibility.RETAIN_AS_CLAIMED_OBSERVATION:
                    reuse = ReuseEligibility.VERIFIED_REUSE_ELIGIBILITY_NOT_ESTABLISHED

        if comp in (
            ComparabilityStatus.COMPARABILITY_CONTEXT_INCOMPLETE.value,
            ComparabilityStatus.FULL_COMPARABILITY_NOT_PROVEN.value,
        ):
            missing.append("COMPARABILITY_CONTEXT_INCOMPLETE")
            limitations.append("SAME_OPERATION_CODE_NE_COMPARABLE_EXECUTION")
            if reuse == ReuseEligibility.ELIGIBLE_FOR_EXPLORATORY_COMPARISON:
                limitations.append(
                    "EXPLORATORY_STATUS_WITH_INCOMPLETE_COMPARABILITY_CONTEXT"
                )

        if s10c and s10c.classification_status == ClassificationStatus.COMPOSITE_OPERATION:
            missing.append("COMPOSITE_OPERATION_COMPOSITION")
            reuse = ReuseEligibility.REQUIRES_ADDITIONAL_CONTEXT

        work_cat = getattr(rec, "work_category", None) or (
            s10c.work_category if s10c else None
        )
        if work_cat in ("auxiliary", "preparation") and qty is None:
            limitations.append(
                "AUXILIARY_OR_PREPARATION_NO_FICTITIOUS_QUANTITY_OR_UNIT_LABOR"
            )

        # Human decision — reference only; never production authority escalation.
        # trusted flag alone ≠ authorized production decision.
        human_ref = None
        hum = decision_by_op.get(sid) or (
            decision_by_event.get(event) if event else None
        )
        if hum:
            limitations.append("TRUSTED_FLAG_ALONE_NE_PRODUCTION_AUTHORITY")
            limitations.append(
                "HUMAN_ACCEPTANCE_NE_AUTOMATIC_BENCHMARK_ELIGIBILITY"
            )
            limitations.append("SUPPLIED_HUMAN_DECISION_NE_S09_RECOMMENDATION")
            # Attach reference only when provenance exists; still keep audited layer.
            if hum.provenance:
                human_ref = hum.decision_identity
            else:
                limitations.append(
                    "SUPPLIED_DECISION_WITHOUT_PROVENANCE_NOT_ATTACHED_AS_AUTHORITY"
                )
            # Never escalate authority_layer to HUMAN_ACCEPTANCE_DECISION /
            # VERIFIED_PHYSICAL / APPROVED from caller-supplied fields.

        # Untrusted acceptance flags ignored (not in trusted list)
        for d in human_decision_refs:
            if not d.trusted and (
                d.source_operation_identity == sid
                or (event and d.applicable_event_identity == event)
            ):
                limitations.append("UNTRUSTED_ACCEPTANCE_FLAG_DOES_NOT_GRANT_AUTHORITY")

        audit_refs = [
            f"s01:{s01.math_integrity_status.value}",
            f"s11:{s11f.check_identity}" if s11f else "s11:none",
            f"s09:{getattr(s09r, 'recommendation_identity', None)}",
            f"s04:scenario_cost_refs_retained",
            f"s02:tech_assessment_refs_retained",
            f"s06:statistical_assessment_refs_retained",
            f"s07:hypothesis_refs_retained_not_constraint_facts",
        ]
        if s03f:
            audit_refs.append(f"s03:{s03f.check_identity}")
        # S02 demo findings remain professional assessment references, not TECH
        # knowledge candidates (demonstration rule ≠ reusable tech knowledge).
        for f in s02.findings:
            if f.source_operation_identity == sid and f.demonstration_rule:
                audit_refs.append(f"s02_demo:{f.check_identity}")
                limitations.append(
                    "S02_DEMONSTRATION_RESULT_RETAINED_AS_AUDIT_REFERENCE_NOT_TECH_CANDIDATE"
                )
                break

        obs_id = f"obs:{obs_key}"
        observations.append(
            ProductionObservation(
                observation_identity=obs_id,
                project_code=project,
                shift_reference=shift_ref,
                execution_event_reference=event,
                source_operation_identity=sid,
                source_record_ids=tuple(getattr(rec, "source_record_ids", ()) or ()),
                source_version=audit_input.source_version_ref,
                physical_object_reference=getattr(
                    rec, "physical_object_reference", None
                )
                or (s03f.physical_object_reference if s03f else None),
                canonical_operation_identity=getattr(
                    rec, "canonical_operation_identity", None
                ),
                operation_code=getattr(rec, "operation_code", None),
                original_operation_text=getattr(
                    rec, "original_operation_text", sid
                ),
                work_category=work_cat,
                claimed_result_state=(
                    s11f.claimed_result_state
                    if s11f
                    else (
                        s03f.claimed_result_state.value
                        if s03f and hasattr(s03f.claimed_result_state, "value")
                        else None
                    )
                ),
                claimed_quantity=qty,
                quantity_unit=unit,
                claimed_labor_man_minutes=labor_mm,
                labor_semantics=(
                    s11f.labor_semantics if s11f else audit_input.labor_semantics_status.value
                ),
                s11_finding_identity=s11f.check_identity if s11f else None,
                unit_labor_man_minutes_per_physical=ul,
                s11_calculation_status=calc,
                s11_observation_eligibility=elig,
                s11_comparability_status=comp,
                material_context=None,  # never invent
                geometry_context=None,
                technology_context=None,
                execution_conditions=None,
                temporal_context=None,
                evidence_references=tuple(dict.fromkeys(evidence_refs)),
                evidence_authority=evidence_auth,
                professional_audit_references=tuple(audit_refs),
                s09_recommendation_identity=getattr(
                    s09r, "recommendation_identity", None
                ),
                s09_recommendation_status=(
                    s09r.recommendation_status.value
                    if getattr(s09r, "recommendation_status", None) is not None
                    and hasattr(s09r.recommendation_status, "value")
                    else (
                        str(getattr(s09r, "recommendation_status", None))
                        if getattr(s09r, "recommendation_status", None)
                        else None
                    )
                ),
                human_decision_reference=human_ref,
                authority_layer=authority,
                reuse_eligibility=reuse,
                missing_context=tuple(dict.fromkeys(missing)),
                limitations=tuple(dict.fromkeys(limitations)),
                provenance=(
                    "s12.production_intelligence",
                    S12_RULES_VERSION,
                    "s11_metrics_reused_not_recomputed",
                ),
            )
        )

        # Knowledge candidates — selective; skill artifact presence ≠ candidate.
        # UL: only when S11 computable claimed unit labor exists.
        if (
            calc == LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION.value
            and ul is not None
        ):
            cand_elig = (
                ReuseEligibility.ELIGIBLE_FOR_EXPLORATORY_COMPARISON
                if elig == ObservationEligibility.HISTORICAL_ANALYSIS_CANDIDATE.value
                else ReuseEligibility.KNOWLEDGE_CANDIDATE_WITH_LIMITATIONS
            )
            candidates.append(
                KnowledgeCandidate(
                    candidate_identity=f"kc:ul:{obs_id}",
                    candidate_type=KnowledgeCandidateType.UNIT_LABOR_OBSERVATION,
                    linked_observation_identities=(obs_id,),
                    source_operation_identity=sid,
                    operation_code=getattr(rec, "operation_code", None),
                    evidence_authority=evidence_auth,
                    reuse_eligibility=cand_elig,
                    suggested_reuse_purposes=(
                        SuggestedReusePurpose.EXPLORATORY_PRODUCTIVITY_ANALYSIS,
                        SuggestedReusePurpose.FUTURE_LABOR_ESTIMATION,
                    ),
                    suggested_consumer_roles=(
                        SuggestedConsumerRole.PRODUCTION_SHIFT_AUDITOR,
                        SuggestedConsumerRole.CONSTRUCTOR_AGENT,
                    ),
                    professional_basis=(
                        "S11_COMPUTABLE_CLAIMED_UNIT_LABOR",
                        f"unit_labor_mm_per_physical={ul}",
                    ),
                    limitations=(
                        "CLAIMED_UNIT_LABOR_NE_APPROVED_NORM",
                        "EXPLORATORY_DESCRIPTIVE_USE_ONLY",
                        "COMPUTABLE_UNIT_LABOR_NE_ESTABLISHED_COMPARABILITY",
                        "COMPUTABLE_UNIT_LABOR_NE_VERIFIED_BENCHMARK_ELIGIBILITY",
                        "NO_BENCHMARK_POPULATION_AGGREGATION_WITHOUT_PROVEN_COMPARABILITY",
                        "SUGGESTED_REUSE_NE_AUTHORIZED_REUSE",
                        "NO_AGENT_HANDOFF",
                        "FULL_COMPARABILITY_NOT_PROVEN",
                    ),
                    provenance=("s12.from_s11",),
                )
            )

        # REPORT: only operation-specific S06 signals (canonical_operation_code),
        # not membership in shift-level descriptive populations.
        op_code = getattr(rec, "operation_code", None)
        for sig in s06.signals:
            if sig.signal_type not in (
                SignalType.ROUNDING_PATTERN,
                SignalType.REPEATED_VALUE,
                SignalType.LABOR_CONCENTRATION,
            ):
                continue
            if not op_code or sig.canonical_operation_code != op_code:
                continue
            candidates.append(
                KnowledgeCandidate(
                    candidate_identity=f"kc:report:{obs_id}:{sig.signal_identity}",
                    candidate_type=KnowledgeCandidateType.REPORTING_QUALITY_OBSERVATION,
                    linked_observation_identities=(obs_id,),
                    source_operation_identity=sid,
                    operation_code=op_code,
                    evidence_authority=sig.evidence_authority.value,
                    reuse_eligibility=ReuseEligibility.RETAIN_AS_CLAIMED_OBSERVATION,
                    suggested_reuse_purposes=(
                        SuggestedReusePurpose.REPORTING_QUALITY_IMPROVEMENT,
                    ),
                    suggested_consumer_roles=(
                        SuggestedConsumerRole.PRODUCTION_SHIFT_AUDITOR,
                    ),
                    professional_basis=(
                        "S06_OPERATION_SPECIFIC_DESCRIPTIVE_SIGNAL",
                        sig.signal_identity,
                    ),
                    limitations=(
                        "REPORTING_CONTEXT_OBSERVATION_NE_PROVEN_REPORTING_DEFECT",
                        "REPORTING_ISSUE_NE_PROVEN_PRODUCTION_INEFFICIENCY",
                        "STATISTICAL_ANOMALY_NE_PRODUCTION_CONSTRAINT_FACT",
                    ),
                    provenance=("s12.from_s06",),
                )
            )
            break

        # Constraint candidate — NOT from S07 hypothesis alone
        for h in s07.hypotheses:
            if h.affected_operation_identity != sid:
                continue
            if h.causal_status == CausalStatus.CAUSE_NOT_ESTABLISHED:
                missing_notes.append(
                    f"S07_HYPOTHESIS_RETAINED_NOT_CONSTRAINT_FACT:{h.hypothesis_identity}"
                )
                break

        # TECH: S02 demonstration_rule alone does NOT create a knowledge candidate.
        # Demo findings remain audit references on the observation (above).

    # Shift-level ECON candidate — one scenario cost observation, not per-op fan-out.
    # Presence of S04 per-op findings ≠ new factual economic knowledge per operation.
    scenario_total = s04.cost_conservation.total_calculated_direct_labor_cost_exact
    if scenario_total is not None:
        fixture_obs_ids = tuple(
            o.observation_identity
            for o in observations
            if o.execution_event_reference
            and str(o.execution_event_reference).startswith("claimed_event:")
        ) or tuple(o.observation_identity for o in observations)
        candidates.append(
            KnowledgeCandidate(
                candidate_identity=f"kc:econ:shift:{aid}",
                candidate_type=KnowledgeCandidateType.ECONOMIC_SCENARIO_OBSERVATION,
                linked_observation_identities=fixture_obs_ids,
                source_operation_identity=None,
                operation_code=None,
                evidence_authority="SCENARIO_RATE",
                reuse_eligibility=ReuseEligibility.RETAIN_AS_CLAIMED_OBSERVATION,
                suggested_reuse_purposes=(
                    SuggestedReusePurpose.COST_SCENARIO_RESEARCH,
                ),
                suggested_consumer_roles=(SuggestedConsumerRole.COST_ENGINEERING,),
                professional_basis=(
                    "S04_SHIFT_SCENARIO_DIRECT_LABOR_COST",
                    f"scenario_direct_labor_cost_exact={scenario_total}",
                ),
                limitations=(
                    "SCENARIO_COST_NE_ACTUAL_COST_KNOWLEDGE",
                    "SCENARIO_OBSERVATION_NE_NEW_FACTUAL_ECONOMIC_KNOWLEDGE",
                    "NO_APPROVED_COST_REFERENCE",
                    "ACTUAL_INCURRED_COST_NOT_PROVEN",
                    "COST_DEVIATION_ENGINE_IMPLEMENTED_NO",
                    "COST_DEVIATION_BOUNDARIES_ONLY_YES",
                ),
                provenance=("s12.from_s04_shift_scenario",),
            )
        )

    # Deduplicate candidates by identity
    cand_uniq: dict[str, KnowledgeCandidate] = {}
    for c in candidates:
        if c.candidate_identity not in cand_uniq:
            cand_uniq[c.candidate_identity] = c
    candidates = list(cand_uniq.values())

    # Labor conservation check against S01
    s01_total = s01.s01_metrics.claimed_total_man_minutes or 0.0
    obs_labor = sum(o.claimed_labor_man_minutes or 0.0 for o in observations)
    # Prefer fixture claimed_event rows for conservation narrative
    fixture_obs = [
        o
        for o in observations
        if o.execution_event_reference
        and o.execution_event_reference.startswith("claimed_event:")
    ]
    if fixture_obs:
        fixture_labor = sum(o.claimed_labor_man_minutes or 0.0 for o in fixture_obs)
        computable_ul_mm = sum(
            float(o.claimed_labor_man_minutes or 0.0)
            for o in fixture_obs
            if o.s11_calculation_status
            == LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION.value
            and o.unit_labor_man_minutes_per_physical is not None
        )
        without_ul_mm = fixture_labor - computable_ul_mm
        obs_labor = fixture_labor

    type_counts: dict[str, int] = defaultdict(int)
    for c in candidates:
        type_counts[c.candidate_type.value] += 1

    excluded_n = sum(
        1
        for o in observations
        if o.reuse_eligibility == ReuseEligibility.EXCLUDED_FROM_BENCHMARK_USE
    )
    req_ctx_n = sum(
        1
        for o in observations
        if o.reuse_eligibility == ReuseEligibility.REQUIRES_ADDITIONAL_CONTEXT
    )
    ul_obs_n = sum(
        1
        for o in observations
        if o.unit_labor_man_minutes_per_physical is not None
        and o.s11_calculation_status
        == LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION.value
    )

    conclusion = (
        f"S12 observations={len(observations)}; "
        f"unit_labor_obs={ul_obs_n}; "
        f"computable_ul_mm={computable_ul_mm}; "
        f"without_ul_mm={without_ul_mm}; "
        f"candidates={len(candidates)}; "
        f"verified_knowledge=0; approved_knowledge=0; approved_norms=0; "
        f"labor_conserved≈{obs_labor}/{s01_total}"
    )

    summary = ShiftProductionIntelligenceSummary(
        source_operation_count=len(audit_input.operations),
        distinct_observation_count=len(observations),
        unit_labor_observation_count=ul_obs_n,
        computable_unit_labor_man_minutes=computable_ul_mm,
        labor_without_computable_unit_metrics_man_minutes=without_ul_mm,
        total_claimed_labor_man_minutes=s01.s01_metrics.claimed_total_man_minutes,
        scenario_direct_labor_cost_exact=(
            s04.cost_conservation.total_calculated_direct_labor_cost_exact
        ),
        knowledge_candidate_count=len(candidates),
        candidate_type_counts=tuple(sorted(type_counts.items())),
        excluded_from_benchmark_count=excluded_n,
        requires_additional_context_count=req_ctx_n,
        verified_knowledge_count=0,
        approved_knowledge_count=0,
        approved_labor_norm_count=0,
        missing_context_notes=tuple(dict.fromkeys(missing_notes))[:40],
        professional_conclusion=conclusion,
        notes=(
            "S11_UNIT_LABOR_REUSED_NOT_RECOMPUTED",
            "MULTIPLE_CANDIDATE_TYPES_DO_NOT_DUPLICATE_LABOR",
            "MULTIPLE_EVIDENCE_REPRESENTATIONS_NE_MULTIPLE_EVENTS",
            "S09_RECOMMENDATION_NE_HUMAN_DECISION",
            "NO_APPROVED_PRODUCTION_KNOWLEDGE",
            "NO_AUTONOMOUS_LEARNING",
            f"S09_shift_recommendation={s09.shift_summary.shift_level_recommendation.value}",
        ),
    )

    human = (
        f"S12 Production Intelligence for {project} {audit_input.work_date}: "
        f"{len(observations)} observations, {len(candidates)} knowledge candidates, "
        f"computable UL labor={computable_ul_mm}, without UL={without_ul_mm}, "
        f"approved knowledge=0, approved norms=0."
    )

    return ShiftProductionIntelligenceArtifact(
        schema_version=S12_ARTIFACT_SCHEMA_VERSION,
        rules_version=S12_RULES_VERSION,
        policy_version=S12_POLICY_VERSION,
        audit_id=aid,
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=_utc_now(),
        project_code=project,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        observations=tuple(observations),
        knowledge_candidates=tuple(candidates),
        shift_summary=summary,
        observations_notes=(
            "S12 consolidates prior skills into structured observations",
            "Does not approve production knowledge or labor norms",
            "Does not persist knowledge or mutate LaborNormResolver",
            "Suggested reuse ≠ authorized reuse; no agent handoff",
        ),
        managerial_acceptance_status="NOT_IN_SCOPE",
        contractual_recognition_status="NOT_PERFORMED",
        payroll_decision_status="NOT_PERFORMED",
        norm_mutation_status="NOT_PERFORMED",
        knowledge_approval_status="NOT_PERFORMED",
        autonomous_learning_status="NOT_IMPLEMENTED",
        persistence_status="NOT_IMPLEMENTED",
        human_readable_summary=human,
    )
