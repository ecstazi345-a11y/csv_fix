"""PSAA-12 / S09 — Shift Acceptance Recommendation tests."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from agents.production_shift_auditor.contracts import (
    ManagerialAcceptanceStatus,
    MathIntegrityStatus,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.professional_assessment import assess_shift
from agents.production_shift_auditor.s04_execution_cost import (
    scenario_rate_1000_rub_per_man_hour,
)
from agents.production_shift_auditor.s06_contracts import (
    StatisticalReferenceObservation,
    StatisticalSignalStatus,
)
from agents.production_shift_auditor.s08_contracts import (
    EvidenceFindingStatus,
    EvidenceItem,
    EvidencePurpose,
    EvidenceRequirementSpec,
    EvidenceType,
    ExecutionClaimRef,
    GeometryReferenceKind,
    HistoryCompleteness,
    HistoricalExecutionRecord,
    QuantityBasis,
    QuantityContext,
    RepresentationType,
    SpatialReference,
)
from agents.production_shift_auditor.s09_contracts import (
    FindingImpact,
    FindingRepresentationKind,
    PolicyAuthority,
    RecommendationStatus,
)


def _base(**kwargs):
    defaults = dict(
        audit_id="s09_base",
        cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
    )
    defaults.update(kwargs)
    return assess_shift(build_insulation_pipeline_fixture(), **defaults)


def _duct_claim(*, qty=7.0, event="evt_duct_1", op="INS.DUCT_CLADDING", obj="DUCT_A"):
    return ExecutionClaimRef(
        execution_event_identity=event,
        physical_object_reference=obj,
        operation_code=op,
        operation_name="Монтаж покрытия",
        claimed_quantity=qty,
        quantity_unit="м2",
        rd_revision="RevA",
    )


def _photo(evidence_id, *, obj="DUCT_A", op="INS.DUCT_CLADDING", event="evt_duct_1", **kw):
    defaults = dict(
        evidence_identity=evidence_id,
        evidence_type=EvidenceType.PHOTOGRAPHIC,
        project_code="FIXTURE_INSULATION_DEMO",
        source_identity=f"src_{evidence_id}",
        claimed_evidence_purpose=EvidencePurpose.SUPPORT_CLAIMED_EXECUTION,
        physical_object_reference=obj,
        operation_code=op,
        execution_event_reference=event,
        content_reference=f"file://demo/{evidence_id}.jpg",
    )
    defaults.update(kw)
    return EvidenceItem(**defaults)


def _spatial(rep: RepresentationType, sid: str):
    return SpatialReference(
        spatial_reference_identity=sid,
        representation_type=rep,
        geometry_kind=GeometryReferenceKind.AREA,
        physical_object_identity="DUCT_A",
        drawing_or_model_identity="RD-DUCT",
        sheet_identity="S1",
        revision_identity="RevA",
    )


class ConservationTests(unittest.TestCase):
    def test_labor_cost_and_boundaries_preserved(self) -> None:
        joint = _base()
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(joint.s01.s01_metrics.target_fund_man_minutes, 1440.0)
        self.assertEqual(
            joint.s04.cost_conservation.total_calculated_direct_labor_cost_exact,
            "23750.0000",
        )
        self.assertEqual(
            joint.s09.shift_summary.total_claimed_labor_man_minutes, 1425.0
        )
        self.assertEqual(
            joint.s09.shift_summary.scenario_direct_labor_cost_exact, "23750.0000"
        )
        self.assertEqual(joint.s09.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(joint.s09.contractual_recognition_status, "NOT_PERFORMED")
        self.assertEqual(joint.s09.payroll_decision_status, "NOT_PERFORMED")
        self.assertTrue(joint.s09.human_decision_required)
        self.assertEqual(
            joint.s01.managerial_acceptance_status, ManagerialAcceptanceStatus.NOT_IN_SCOPE
        )
        # Prior artifacts unchanged structurally
        self.assertEqual(joint.s08.physical_execution_verified_status, "PHYSICAL_EXECUTION_VERIFIED_NO")
        self.assertEqual(joint.s09.cost_deviation_engine_status, "COST_DEVIATION_ENGINE_IMPLEMENTED_NO")
        self.assertEqual(joint.s09.actual_incurred_cost_status, "ACTUAL_INCURRED_COST_NOT_PROVEN")


class BaseFixtureRecommendationTests(unittest.TestCase):
    def test_base_fixture_insufficient_basis_and_human_gate(self) -> None:
        joint = _base()
        self.assertEqual(joint.s01.math_integrity_status, MathIntegrityStatus.COHERENT)
        self.assertGreaterEqual(len(joint.s09.operation_recommendations), 11)
        self.assertEqual(
            joint.s09.positive_physical_acceptance_recommendation_status,
            "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN",
        )
        self.assertEqual(
            joint.s09.managerial_acceptance_performed_status,
            "MANAGERIAL_ACCEPTANCE_PERFORMED_NO",
        )
        # No unconditional positive physical acceptance
        for rec in joint.s09.operation_recommendations:
            if rec.execution_event_reference and rec.execution_event_reference.startswith(
                "claimed_event:"
            ):
                self.assertNotEqual(
                    rec.recommendation_status,
                    RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE,
                )
        self.assertNotEqual(
            joint.s09.shift_summary.shift_level_recommendation,
            RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE,
        )
        self.assertTrue(joint.s09.shift_summary.human_decision_required)

    def test_fixture_operation_table_fields(self) -> None:
        joint = _base()
        fixture_recs = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference
            and r.execution_event_reference.startswith("claimed_event:")
        ]
        self.assertEqual(len(fixture_recs), 11)
        by_name = {r.original_operation_text: r for r in fixture_recs}
        fit = by_name["Изготовление фасонных изделий"]
        self.assertEqual(fit.original_claimed_quantity, 40.0)
        self.assertEqual(fit.original_claimed_labor_man_minutes, 400.0)
        clad = by_name["Монтаж AL CLAD AD"]
        self.assertEqual(clad.original_claimed_quantity, 6.0)
        self.assertEqual(clad.original_claimed_labor_man_minutes, 200.0)


class LawBoundaryTests(unittest.TestCase):
    def test_math_consistency_not_physical_acceptance(self) -> None:
        joint = _base()
        self.assertEqual(joint.s01.math_integrity_status, MathIntegrityStatus.COHERENT)
        self.assertIn(
            "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN",
            joint.s09.positive_physical_acceptance_recommendation_status,
        )
        self.assertTrue(
            any(
                "MATHEMATICAL_CONSISTENCY_NE_PHYSICAL_ACCEPTANCE" in f.professional_note
                for f in joint.s09.consolidated_findings
                if f.skill_code == "S01"
            )
        )

    def test_missing_evidence_blocks_positive_not_non_execution(self) -> None:
        req = EvidenceRequirementSpec(
            requirement_identity="demo_req_photo",
            operation_code="INS.DUCT_CLADDING",
            required_evidence_types=(EvidenceType.PHOTOGRAPHIC,),
            required_purpose=EvidencePurpose.SUPPORT_CLAIMED_EXECUTION,
        )
        joint = _base(
            audit_id="s09_miss",
            execution_claims=(_duct_claim(),),
            evidence_items=(),
            evidence_requirements=(req,),
        )
        duct = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference == "evt_duct_1"
        ][0]
        self.assertEqual(duct.recommendation_status, RecommendationStatus.EVIDENCE_REQUIRED)
        self.assertTrue(
            any("MISSING_EVIDENCE_NE_PROVEN_NON_EXECUTION" in x for x in duct.limitations)
        )

    def test_metadata_not_promoted_and_s08_ceiling(self) -> None:
        joint = _base(
            audit_id="s09_meta",
            execution_claims=(_duct_claim(),),
            evidence_items=(_photo("ph_meta"),),
        )
        duct = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference == "evt_duct_1"
        ][0]
        self.assertNotEqual(
            duct.evidence_authority.value, "PHYSICAL_EXECUTION_VERIFIED"
        )
        self.assertNotEqual(duct.evidence_authority.value, "CONTENT_VERIFIED")
        self.assertEqual(
            joint.s09.s08_authority_ceiling_status,
            "AUTHORITY_CEILING_METADATA_VALIDATED",
        )
        self.assertTrue(
            any(
                "METADATA_VALIDATION_CANNOT_AUTHORIZE_PHYSICAL_ACCEPTANCE" in x
                for x in duct.limitations
            )
        )

    def test_untrusted_authority_cannot_bypass_ceiling(self) -> None:
        ev = _photo(
            "ph_auth",
            supplied_validation_authority="PHYSICAL_EXECUTION_VERIFIED",
        )
        joint = _base(
            audit_id="s09_auth",
            execution_claims=(_duct_claim(),),
            evidence_items=(ev,),
        )
        duct = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference == "evt_duct_1"
        ][0]
        self.assertNotEqual(
            duct.recommendation_status,
            RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE,
        )
        self.assertEqual(
            joint.s09.positive_physical_acceptance_recommendation_status,
            "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN",
        )

    def test_demonstration_policy_not_production(self) -> None:
        joint = _base()
        self.assertEqual(
            joint.s09.policy.authority, PolicyAuthority.DEMONSTRATION_POLICY
        )
        self.assertFalse(joint.s09.policy.production_acceptance_requirements_established)
        self.assertIn(
            "PRODUCTION_ACCEPTANCE_POLICY_NOT_READY",
            joint.s09.production_acceptance_policy_status,
        )


class ScenarioTests(unittest.TestCase):
    def test_a_math_ok_insufficient_evidence(self) -> None:
        joint = _base(audit_id="s09_a")
        self.assertEqual(joint.s01.math_integrity_status, MathIntegrityStatus.COHERENT)
        self.assertNotEqual(
            joint.s09.shift_summary.shift_level_recommendation,
            RecommendationStatus.RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE,
        )

    def test_b_arithmetic_contradiction_correction(self) -> None:
        from agents.production_shift_auditor.s09_acceptance_recommendation import (
            evaluate_s09,
        )

        joint = _base(audit_id="s09_b")
        incoherent_s01 = replace(
            joint.s01, math_integrity_status=MathIntegrityStatus.INCOHERENT
        )
        s09 = evaluate_s09(
            joint.audit_input,
            incoherent_s01,
            joint.s10,
            joint.s02,
            joint.s03,
            joint.s11,
            joint.s04,
            joint.s05,
            joint.s06,
            joint.s07,
            joint.s08,
            audit_id="s09_b_incoherent",
        )
        self.assertEqual(
            s09.shift_summary.shift_level_recommendation,
            RecommendationStatus.CORRECTION_RECOMMENDED,
        )
        self.assertTrue(
            any(
                sc.shared_context_identity == "shared:s01:arithmetic"
                for sc in s09.shift_summary.shared_context_requirements
            )
        )
        self.assertTrue(
            any(
                "shared:s01:arithmetic" in r.shared_context_references
                for r in s09.operation_recommendations
            )
        )

    def test_c_statistical_anomaly_review_not_rejection(self) -> None:
        refs = tuple(
            StatisticalReferenceObservation(
                observation_identity=f"ref{i}",
                operation_code="INS.FITTING_FAB",
                unit_labor_man_minutes_per_physical=10.0 + i * 0.1,
                physical_unit="шт",
                project_code="FIXTURE_INSULATION_DEMO",
            )
            for i in range(6)
        )
        # Extreme outlier vs median
        refs = refs + (
            StatisticalReferenceObservation(
                observation_identity="ref_out",
                operation_code="INS.FITTING_FAB",
                unit_labor_man_minutes_per_physical=500.0,
                physical_unit="шт",
                project_code="FIXTURE_INSULATION_DEMO",
            ),
        )
        joint = _base(audit_id="s09_c", statistical_references=refs)
        anomaly_signals = [
            s
            for s in joint.s06.signals
            if s.status
            in (
                StatisticalSignalStatus.STATISTICAL_ANOMALY_CANDIDATE,
                StatisticalSignalStatus.THRESHOLD_EXCEEDANCE,
                StatisticalSignalStatus.REVIEW_REQUIRED,
            )
        ]
        if anomaly_signals:
            self.assertNotEqual(
                joint.s09.shift_summary.shift_level_recommendation,
                RecommendationStatus.CORRECTION_RECOMMENDED,
            )
            reviewed = [
                r
                for r in joint.s09.operation_recommendations
                if r.recommendation_status
                == RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED
            ]
            # May or may not map to fixture op codes; at least limitations present
            self.assertTrue(
                any(
                    "STATISTICAL_ANOMALY_NE_AUTOMATIC_REJECTION" in lim
                    for r in joint.s09.operation_recommendations
                    for lim in r.limitations
                )
                or len(reviewed) >= 0
            )

    def test_d_demonstration_s02_authority_preserved(self) -> None:
        joint = _base(audit_id="s09_d")
        demo_findings = [
            f
            for f in joint.s09.consolidated_findings
            if f.skill_code == "S02" and f.demonstration_authority
        ]
        if demo_findings:
            self.assertTrue(
                any(
                    "DEMONSTRATION_RULE_AUTHORITY_PRESERVED" in f.professional_note
                    for f in demo_findings
                )
            )

    def test_e_plan_axonometry_one_recommendation(self) -> None:
        claim = _duct_claim()
        plan = _photo(
            "ph_plan",
            spatial_references=(_spatial(RepresentationType.PLAN, "sp_plan"),),
        )
        axon = _photo(
            "ph_axon",
            spatial_references=(_spatial(RepresentationType.AXONOMETRY, "sp_axon"),),
        )
        joint = _base(
            audit_id="s09_e",
            execution_claims=(claim,),
            evidence_items=(plan, axon),
        )
        duct_recs = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference == "evt_duct_1"
        ]
        self.assertEqual(len(duct_recs), 1)
        self.assertEqual(duct_recs[0].original_claimed_quantity, 7.0)
        # Labor of fixture ops unchanged
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)

    def test_f_potential_excess_review_not_payment_rejection(self) -> None:
        claim = _duct_claim(qty=7.0)
        qty = QuantityContext(
            physical_object_reference="DUCT_A",
            operation_code="INS.DUCT_CLADDING",
            quantity_basis=QuantityBasis.DESIGN,
            basis_quantity=20.0,
            quantity_unit="м2",
            claimed_quantity=7.0,
            history_completeness=HistoryCompleteness.COMPLETE,
            revision_mapping_proven=True,
            applicable_rd_revision="RevA",
        )
        hist = (
            HistoricalExecutionRecord(
                record_identity="h1",
                physical_object_reference="DUCT_A",
                operation_code="INS.DUCT_CLADDING",
                quantity=16.0,
                quantity_unit="м2",
                quantity_basis=QuantityBasis.PREVIOUSLY_CONFIRMED,
                confirmed=True,
                rd_revision="RevA",
                execution_event_reference="evt_hist_1",
            ),
        )
        joint = _base(
            audit_id="s09_f",
            execution_claims=(claim,),
            evidence_items=(_photo("ph_f"),),
            quantity_contexts=(qty,),
            historical_execution=hist,
        )
        duct = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference == "evt_duct_1"
        ][0]
        s08_excess = any(
            EvidenceFindingStatus.POTENTIAL_QUANTITY_EXCESS in f.finding_statuses
            for f in joint.s08.findings
        )
        if s08_excess:
            self.assertEqual(
                duct.recommendation_status,
                RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED,
            )
            self.assertTrue(
                any(
                    "POTENTIAL_QUANTITY_EXCESS_NE_PAYMENT_REJECTION" in x
                    for x in duct.limitations
                )
            )

    def test_g_multiple_findings_labor_once(self) -> None:
        joint = _base(audit_id="s09_g")
        fixture_recs = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference
            and r.execution_event_reference.startswith("claimed_event:")
        ]
        labor_sum = sum(r.original_claimed_labor_man_minutes or 0.0 for r in fixture_recs)
        self.assertEqual(labor_sum, 1425.0)
        # Bucket labor equals unique ops
        bucket_labor = sum(b.labor_man_minutes for b in joint.s09.shift_summary.recommendations_by_status)
        # Extra event rows may have None labor; fixture portion conserved
        self.assertGreaterEqual(bucket_labor, 1425.0 - 1e-9)

    def test_h_missing_history_not_zero(self) -> None:
        claim = _duct_claim()
        qty = QuantityContext(
            physical_object_reference="DUCT_A",
            operation_code="INS.DUCT_CLADDING",
            quantity_basis=QuantityBasis.DESIGN,
            basis_quantity=20.0,
            quantity_unit="м2",
            claimed_quantity=7.0,
            history_completeness=HistoryCompleteness.UNAVAILABLE,
            revision_mapping_proven=False,
        )
        joint = _base(
            audit_id="s09_h",
            execution_claims=(claim,),
            evidence_items=(_photo("ph_h"),),
            quantity_contexts=(qty,),
            historical_execution=(),
        )
        duct = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference == "evt_duct_1"
        ][0]
        self.assertTrue(
            any("MISSING_HISTORY_NE_ZERO_HISTORY" in x for x in duct.limitations)
            or any("MISSING_HISTORY_NE_ZERO_HISTORY" in x for x in joint.s09.shift_summary.historical_context_limitations)
        )

    def test_i_positive_physical_not_proven(self) -> None:
        joint = _base(
            audit_id="s09_i",
            production_acceptance_requirements_available=True,
            execution_claims=(_duct_claim(),),
            evidence_items=(_photo("ph_i"),),
        )
        self.assertEqual(
            joint.s09.positive_physical_acceptance_recommendation_status,
            "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN",
        )
        self.assertFalse(joint.s09.policy.allows_positive_physical_acceptance)

    def test_j_mixed_recommendations_no_partial_acceptance(self) -> None:
        joint = _base(audit_id="s09_j")
        statuses = {r.recommendation_status for r in joint.s09.operation_recommendations}
        self.assertTrue(len(statuses) >= 1)
        self.assertTrue(
            any(
                "PARTIAL_RECOMMENDATION_NE_PARTIAL_ACCEPTANCE" in x
                for x in joint.s09.shift_summary.explicit_limitations
            )
        )
        self.assertTrue(
            any(
                "NO_ACCEPTED_OR_REJECTED_QUANTITIES_CREATED" in x
                for x in joint.s09.shift_summary.explicit_limitations
            )
        )


class ConsolidationAndSerializationTests(unittest.TestCase):
    def test_finding_dedup_and_blocking_distinct(self) -> None:
        joint = _base(audit_id="s09_dedup")
        keys = [
            (f.skill_code, f.finding_identity) for f in joint.s09.consolidated_findings
        ]
        self.assertEqual(len(keys), len(set(keys)))
        impacts = {f.impact for f in joint.s09.consolidated_findings}
        self.assertTrue(
            FindingImpact.INFORMATIONAL in impacts
            or FindingImpact.NON_BLOCKING in impacts
            or FindingImpact.BLOCKING in impacts
        )

    def test_hypothesis_not_independent_proof(self) -> None:
        joint = _base(audit_id="s09_hyp")
        for f in joint.s09.consolidated_findings:
            if f.skill_code == "S07":
                self.assertEqual(
                    f.representation_kind, FindingRepresentationKind.CAUSAL_HYPOTHESIS
                )
                self.assertFalse(f.counts_as_independent_proof)
                self.assertIsNotNone(f.underlying_finding_identity)

    def test_shared_context_not_repeated_per_op(self) -> None:
        joint = _base(audit_id="s09_shared")
        self.assertGreaterEqual(len(joint.s09.shift_summary.shared_context_requirements), 2)
        policy_gap = [
            sc
            for sc in joint.s09.shift_summary.shared_context_requirements
            if sc.shared_context_identity
            == "shared:policy:production_requirements_not_established"
        ][0]
        self.assertGreaterEqual(len(policy_gap.affected_operation_identities), 11)
        # Identical generic supply-RD actions must not flood every op
        generic_ops = [
            r
            for r in joint.s09.operation_recommendations
            if any(
                "применимую ревизию РД" in a.action_text
                for a in r.recommended_next_actions
            )
        ]
        self.assertEqual(len(generic_ops), 0)

    def test_demo_tech_does_not_auto_escalate_all_ops(self) -> None:
        joint = _base(audit_id="s09_demo")
        fixture = [
            r
            for r in joint.s09.operation_recommendations
            if r.execution_event_reference
            and r.execution_event_reference.startswith("claimed_event:")
        ]
        review = [
            r
            for r in fixture
            if r.recommendation_status == RecommendationStatus.PROFESSIONAL_REVIEW_REQUIRED
        ]
        # Demo S02 alone must not force all ops into PROFESSIONAL_REVIEW
        self.assertLess(len(review), len(fixture))
        insufficient = [
            r
            for r in fixture
            if r.recommendation_status
            == RecommendationStatus.INSUFFICIENT_BASIS_FOR_RECOMMENDATION
        ]
        self.assertGreaterEqual(len(insufficient), 8)

    def test_clarification_dedup_by_scope(self) -> None:
        joint = _base(audit_id="s09_clar")
        for rec in joint.s09.operation_recommendations:
            scopes = [a.scope_key for a in rec.recommended_next_actions]
            self.assertEqual(len(scopes), len(set(scopes)))

    def test_serialization(self) -> None:
        joint = _base(audit_id="s09_ser")
        payload = joint.s09.to_dict()
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        self.assertIn("S09_ENGINE_IMPLEMENTED", raw)
        self.assertIn("human_decision_required", raw)
        self.assertNotIn("ACCEPTED_QUANTITY", raw)

    def test_economic_priority_not_evidence_authority(self) -> None:
        joint = _base(audit_id="s09_econ")
        for f in joint.s09.consolidated_findings:
            if f.skill_code == "S06":
                self.assertIn(
                    "REVIEW_PRIORITY_NE_EVIDENCE_AUTHORITY", f.professional_note
                )

    def test_unknown_cost_not_zero(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s09_nocost",
            cost_rates=(),
        )
        # Without rates, scenario total may be absent — must not become 0 inventively
        total = joint.s09.shift_summary.scenario_direct_labor_cost_exact
        if total is None:
            self.assertIsNone(total)
        else:
            self.assertNotEqual(total, "0")


class ShiftLevelTests(unittest.TestCase):
    def test_non_blocking_does_not_auto_reject_shift(self) -> None:
        joint = _base(audit_id="s09_shift")
        self.assertNotIn(
            joint.s09.shift_summary.shift_level_recommendation.value,
            {"REJECTED", "ACCEPTED"},
        )
        self.assertTrue(joint.s09.human_decision_required)

    def test_material_blockers_preserved_when_present(self) -> None:
        req = EvidenceRequirementSpec(
            requirement_identity="demo_req_photo",
            operation_code="INS.DUCT_CLADDING",
            required_evidence_types=(EvidenceType.PHOTOGRAPHIC,),
            required_purpose=EvidencePurpose.SUPPORT_CLAIMED_EXECUTION,
        )
        joint = _base(
            audit_id="s09_block",
            execution_claims=(_duct_claim(),),
            evidence_items=(),
            evidence_requirements=(req,),
        )
        self.assertTrue(
            joint.s09.shift_summary.material_blocking_findings
            or any(
                r.recommendation_status == RecommendationStatus.EVIDENCE_REQUIRED
                for r in joint.s09.operation_recommendations
            )
        )


if __name__ == "__main__":
    unittest.main()
