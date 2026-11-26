"""PSAA-13 / S12 — Production Intelligence tests."""

from __future__ import annotations

import json
import unittest

from agents.production_shift_auditor.contracts import ManagerialAcceptanceStatus
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.professional_assessment import assess_shift
from agents.production_shift_auditor.s04_execution_cost import (
    scenario_rate_1000_rub_per_man_hour,
)
from agents.production_shift_auditor.s08_contracts import (
    EvidenceItem,
    EvidencePurpose,
    EvidenceType,
    ExecutionClaimRef,
    GeometryReferenceKind,
    RepresentationType,
    SpatialReference,
)
from agents.production_shift_auditor.s11_contracts import (
    HistoricalLaborObservation,
    LaborCalculationStatus,
)
from agents.production_shift_auditor.s12_contracts import (
    KnowledgeCandidateType,
    ObservationAuthorityLayer,
    ReuseEligibility,
    SuppliedHumanDecisionRef,
)
from agents.production_shift_auditor.s12_production_intelligence import evaluate_s12


def _base(**kwargs):
    defaults = dict(
        audit_id="s12_base",
        cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
    )
    defaults.update(kwargs)
    return assess_shift(build_insulation_pipeline_fixture(), **defaults)


def _fixture_obs(joint):
    return [
        o
        for o in joint.s12.observations
        if o.execution_event_reference
        and o.execution_event_reference.startswith("claimed_event:")
    ]


class ConservationTests(unittest.TestCase):
    def test_labor_cost_and_ul_split(self) -> None:
        joint = _base()
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(
            joint.s04.cost_conservation.total_calculated_direct_labor_cost_exact,
            "23750.0000",
        )
        self.assertEqual(joint.s12.shift_summary.total_claimed_labor_man_minutes, 1425.0)
        self.assertEqual(
            joint.s12.shift_summary.scenario_direct_labor_cost_exact, "23750.0000"
        )
        self.assertEqual(
            joint.s12.shift_summary.computable_unit_labor_man_minutes, 600.0
        )
        self.assertEqual(
            joint.s12.shift_summary.labor_without_computable_unit_metrics_man_minutes,
            825.0,
        )
        self.assertEqual(joint.s12.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(
            joint.s12.approved_production_knowledge_created_status,
            "APPROVED_PRODUCTION_KNOWLEDGE_CREATED_NO",
        )
        self.assertEqual(
            joint.s12.approved_production_labor_norm_created_status,
            "APPROVED_PRODUCTION_LABOR_NORM_CREATED_NO",
        )
        self.assertEqual(
            joint.s12.autonomous_learning_implemented_status,
            "AUTONOMOUS_LEARNING_IMPLEMENTED_NO",
        )
        self.assertEqual(
            joint.s01.managerial_acceptance_status, ManagerialAcceptanceStatus.NOT_IN_SCOPE
        )


class S11ReuseTests(unittest.TestCase):
    def test_unit_labor_reused_not_recomputed(self) -> None:
        joint = _base()
        by_name = {o.original_operation_text: o for o in _fixture_obs(joint)}
        fit = by_name["Изготовление фасонных изделий"]
        clad = by_name["Монтаж AL CLAD AD"]
        self.assertEqual(fit.claimed_quantity, 40.0)
        self.assertEqual(fit.claimed_labor_man_minutes, 400.0)
        self.assertEqual(fit.unit_labor_man_minutes_per_physical, 10.0)
        self.assertEqual(
            fit.s11_calculation_status,
            LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION.value,
        )
        self.assertEqual(clad.claimed_quantity, 6.0)
        self.assertEqual(clad.claimed_labor_man_minutes, 200.0)
        self.assertAlmostEqual(clad.unit_labor_man_minutes_per_physical, 200.0 / 6.0)
        # Match S11 finding exactly
        s11_fit = [
            f
            for f in joint.s11.findings
            if f.original_operation_text == "Изготовление фасонных изделий"
        ][0]
        self.assertEqual(
            fit.unit_labor_man_minutes_per_physical,
            s11_fit.unit_labor_man_minutes_per_physical,
        )
        self.assertTrue(
            any(
                "COMPUTABLE_UNIT_LABOR_REUSED_FROM_S11_NOT_RECOMPUTED" in x
                for x in fit.limitations
            )
        )

    def test_no_fictitious_ul_for_auxiliary(self) -> None:
        joint = _base()
        cleanup = [
            o
            for o in _fixture_obs(joint)
            if o.original_operation_text == "Уборка рабочего места"
        ][0]
        self.assertIsNone(cleanup.unit_labor_man_minutes_per_physical)
        self.assertTrue(
            any("NO_FICTITIOUS" in x or "AUXILIARY" in x for x in cleanup.limitations)
        )


class AuthorityCeilingTests(unittest.TestCase):
    def test_claimed_not_verified_physical(self) -> None:
        joint = _base()
        for o in _fixture_obs(joint):
            self.assertNotEqual(
                o.authority_layer,
                ObservationAuthorityLayer.VERIFIED_PHYSICAL_OBSERVATION,
            )
            self.assertNotEqual(
                o.authority_layer,
                ObservationAuthorityLayer.APPROVED_PRODUCTION_KNOWLEDGE,
            )
            self.assertIn(
                "AUDITED_OBSERVATION_NE_VERIFIED_PHYSICAL_OBSERVATION",
                o.limitations,
            )

    def test_s09_not_human_decision(self) -> None:
        joint = _base()
        for o in _fixture_obs(joint):
            self.assertIsNotNone(o.s09_recommendation_identity)
            self.assertIsNone(o.human_decision_reference)
            self.assertIn(
                "PROFESSIONAL_RECOMMENDATION_NE_HUMAN_DECISION", o.limitations
            )

    def test_untrusted_acceptance_flag_ignored(self) -> None:
        joint = _base(
            audit_id="s12_untrusted",
            human_decision_refs=(
                SuppliedHumanDecisionRef(
                    decision_identity="fake_accept",
                    project_code="FIXTURE_INSULATION_DEMO",
                    decision_scope="SHIFT",
                    decision_authority="ACCEPTED",
                    decision_version="v0",
                    trusted=False,
                ),
            ),
        )
        self.assertTrue(
            any(
                "UNTRUSTED_ACCEPTANCE_FLAG_DOES_NOT_GRANT_AUTHORITY" in x
                for o in joint.s12.observations
                for x in o.limitations
            )
            or all(o.human_decision_reference is None for o in joint.s12.observations)
        )
        self.assertEqual(joint.s12.shift_summary.approved_knowledge_count, 0)

    def test_trusted_human_decision_not_auto_benchmark(self) -> None:
        fixture = build_insulation_pipeline_fixture()
        joint0 = _base(audit_id="s12_pre")
        sid = _fixture_obs(joint0)[0].source_operation_identity
        joint = assess_shift(
            fixture,
            audit_id="s12_trusted",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
            human_decision_refs=(
                SuppliedHumanDecisionRef(
                    decision_identity="dec_trusted_1",
                    project_code="FIXTURE_INSULATION_DEMO",
                    decision_scope="OPERATION",
                    decision_authority="SITE_MANAGER",
                    decision_version="v1",
                    source_operation_identity=sid,
                    trusted=True,
                    provenance=("caller_supplied_trusted_historical_decision",),
                ),
            ),
        )
        matched = [
            o for o in joint.s12.observations if o.source_operation_identity == sid
        ][0]
        self.assertEqual(matched.human_decision_reference, "dec_trusted_1")
        self.assertIn(
            "HUMAN_ACCEPTANCE_NE_AUTOMATIC_BENCHMARK_ELIGIBILITY",
            matched.limitations,
        )
        self.assertIn(
            "TRUSTED_FLAG_ALONE_NE_PRODUCTION_AUTHORITY",
            matched.limitations,
        )
        self.assertEqual(
            matched.authority_layer,
            ObservationAuthorityLayer.PROFESSIONALLY_AUDITED_OBSERVATION,
        )
        self.assertNotEqual(
            matched.authority_layer,
            ObservationAuthorityLayer.HUMAN_ACCEPTANCE_DECISION,
        )
        self.assertNotEqual(
            matched.authority_layer,
            ObservationAuthorityLayer.APPROVED_PRODUCTION_LABOR_NORM,
        )

    def test_trusted_without_provenance_not_authority(self) -> None:
        fixture = build_insulation_pipeline_fixture()
        joint0 = _base(audit_id="s12_pre2")
        sid = _fixture_obs(joint0)[0].source_operation_identity
        joint = assess_shift(
            fixture,
            audit_id="s12_trusted_noprov",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
            human_decision_refs=(
                SuppliedHumanDecisionRef(
                    decision_identity="dec_flag_only",
                    project_code="FIXTURE_INSULATION_DEMO",
                    decision_scope="OPERATION",
                    decision_authority="ACCEPTED",
                    decision_version="v0",
                    source_operation_identity=sid,
                    trusted=True,
                    provenance=(),
                ),
            ),
        )
        matched = [
            o for o in joint.s12.observations if o.source_operation_identity == sid
        ][0]
        self.assertIsNone(matched.human_decision_reference)
        self.assertIn(
            "SUPPLIED_DECISION_WITHOUT_PROVENANCE_NOT_ATTACHED_AS_AUTHORITY",
            matched.limitations,
        )


class IdentityAndEvidenceTests(unittest.TestCase):
    def test_same_object_different_operations_distinct(self) -> None:
        claim_a = ExecutionClaimRef(
            execution_event_identity="evt_obj_op_a",
            physical_object_reference="DUCT_SHARED",
            operation_code="INS.PREP",
            claimed_quantity=1.0,
            quantity_unit="шт",
            source_operation_identity="sid_op_a",
        )
        claim_b = ExecutionClaimRef(
            execution_event_identity="evt_obj_op_b",
            physical_object_reference="DUCT_SHARED",
            operation_code="INS.CLADDING",
            claimed_quantity=2.0,
            quantity_unit="м2",
            source_operation_identity="sid_op_b",
        )
        joint = _base(
            audit_id="s12_same_obj",
            execution_claims=(claim_a, claim_b),
        )
        shared = [
            o
            for o in joint.s12.observations
            if o.physical_object_reference == "DUCT_SHARED"
            or o.execution_event_reference in ("evt_obj_op_a", "evt_obj_op_b")
        ]
        # Distinct events/ops must remain distinct observations
        evs = {o.execution_event_reference for o in shared}
        self.assertGreaterEqual(len(evs), 2)
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)

    def test_plan_axonometry_one_observation(self) -> None:
        claim = ExecutionClaimRef(
            execution_event_identity="evt_duct_1",
            physical_object_reference="DUCT_A",
            operation_code="INS.DUCT_CLADDING",
            claimed_quantity=7.0,
            quantity_unit="м2",
        )
        plan = EvidenceItem(
            evidence_identity="ph_plan",
            evidence_type=EvidenceType.SPATIAL_DRAWING_MARKUP,
            project_code="FIXTURE_INSULATION_DEMO",
            source_identity="src_plan",
            claimed_evidence_purpose=EvidencePurpose.SPATIAL_LOCATION,
            execution_event_reference="evt_duct_1",
            physical_object_reference="DUCT_A",
            operation_code="INS.DUCT_CLADDING",
            spatial_references=(
                SpatialReference(
                    spatial_reference_identity="sp_plan",
                    representation_type=RepresentationType.PLAN,
                    geometry_kind=GeometryReferenceKind.AREA,
                    physical_object_identity="DUCT_A",
                ),
            ),
        )
        axon = EvidenceItem(
            evidence_identity="ph_axon",
            evidence_type=EvidenceType.SPATIAL_DRAWING_MARKUP,
            project_code="FIXTURE_INSULATION_DEMO",
            source_identity="src_axon",
            claimed_evidence_purpose=EvidencePurpose.SPATIAL_LOCATION,
            execution_event_reference="evt_duct_1",
            physical_object_reference="DUCT_A",
            operation_code="INS.DUCT_CLADDING",
            spatial_references=(
                SpatialReference(
                    spatial_reference_identity="sp_axon",
                    representation_type=RepresentationType.AXONOMETRY,
                    geometry_kind=GeometryReferenceKind.AREA,
                    physical_object_identity="DUCT_A",
                ),
            ),
        )
        joint = _base(
            audit_id="s12_multi_rep",
            execution_claims=(claim,),
            evidence_items=(plan, axon),
        )
        duct = [
            o
            for o in joint.s12.observations
            if o.execution_event_reference == "evt_duct_1"
        ]
        self.assertEqual(len(duct), 1)
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)

    def test_observation_replay_not_duplicated(self) -> None:
        joint = _base(audit_id="s12_replay")
        # Re-run S12 on same prior artifacts — same identities
        s12b = evaluate_s12(
            joint.audit_input,
            joint.s01,
            joint.s10,
            joint.s02,
            joint.s03,
            joint.s11,
            joint.s04,
            joint.s05,
            joint.s06,
            joint.s07,
            joint.s08,
            joint.s09,
            audit_id="s12_replay_b",
        )
        ids_a = {o.observation_identity for o in joint.s12.observations}
        ids_b = {o.observation_identity for o in s12b.observations}
        self.assertEqual(ids_a, ids_b)

    def test_cross_project_blocked(self) -> None:
        joint = _base(
            audit_id="s12_xp",
            authorized_project_scopes=("OTHER_PROJECT_ONLY",),
        )
        self.assertEqual(len(joint.s12.observations), 0)
        self.assertIn(
            "CROSS_PROJECT_CONTEXT_BLOCKED",
            joint.s12.shift_summary.missing_context_notes,
        )


class KnowledgeCandidateTests(unittest.TestCase):
    def test_unit_labor_candidates_with_limitations(self) -> None:
        joint = _base()
        ul = [
            c
            for c in joint.s12.knowledge_candidates
            if c.candidate_type == KnowledgeCandidateType.UNIT_LABOR_OBSERVATION
        ]
        self.assertEqual(len(ul), 2)
        for c in ul:
            self.assertIn("CLAIMED_UNIT_LABOR_NE_APPROVED_NORM", c.limitations)
            self.assertIn("EXPLORATORY_DESCRIPTIVE_USE_ONLY", c.limitations)
            self.assertIn(
                "NO_BENCHMARK_POPULATION_AGGREGATION_WITHOUT_PROVEN_COMPARABILITY",
                c.limitations,
            )
            self.assertEqual(
                c.approved_labor_norm_status,
                "APPROVED_PRODUCTION_LABOR_NORM_NOT_CREATED",
            )
            self.assertEqual(c.handoff_status, "NO_AGENT_HANDOFF")

    def test_no_automatic_candidate_fan_out(self) -> None:
        joint = _base()
        by_type = dict(joint.s12.shift_summary.candidate_type_counts)
        # UL only for computable ops; ECON one shift-level; no TECH from demo rules;
        # REPORT only when op-specific S06 signal exists (fixture has none).
        self.assertEqual(by_type.get("UNIT_LABOR_OBSERVATION", 0), 2)
        self.assertEqual(by_type.get("ECONOMIC_SCENARIO_OBSERVATION", 0), 1)
        self.assertEqual(by_type.get("TECHNOLOGICAL_CONTEXT_OBSERVATION", 0), 0)
        self.assertEqual(by_type.get("REPORTING_QUALITY_OBSERVATION", 0), 0)
        self.assertEqual(by_type.get("CONSTRAINT_OCCURRENCE_OBSERVATION", 0), 0)
        # Demo S02 retained as audit reference, not TECH candidate
        demo_refs = [
            o
            for o in _fixture_obs(joint)
            if any(
                "S02_DEMONSTRATION_RESULT_RETAINED_AS_AUDIT_REFERENCE_NOT_TECH_CANDIDATE"
                in x
                for x in o.limitations
            )
        ]
        self.assertGreater(len(demo_refs), 0)

    def test_hypothesis_not_constraint_fact(self) -> None:
        joint = _base()
        constraint = [
            c
            for c in joint.s12.knowledge_candidates
            if c.candidate_type == KnowledgeCandidateType.CONSTRAINT_OCCURRENCE_OBSERVATION
        ]
        self.assertEqual(len(constraint), 0)

    def test_demo_tech_not_auto_candidate(self) -> None:
        joint = _base()
        tech = [
            c
            for c in joint.s12.knowledge_candidates
            if c.candidate_type == KnowledgeCandidateType.TECHNOLOGICAL_CONTEXT_OBSERVATION
        ]
        self.assertEqual(len(tech), 0)

    def test_scenario_cost_not_actual(self) -> None:
        joint = _base()
        econ = [
            c
            for c in joint.s12.knowledge_candidates
            if c.candidate_type == KnowledgeCandidateType.ECONOMIC_SCENARIO_OBSERVATION
        ]
        self.assertEqual(len(econ), 1)
        self.assertIsNone(econ[0].source_operation_identity)
        self.assertIn("SCENARIO_COST_NE_ACTUAL_COST_KNOWLEDGE", econ[0].limitations)
        self.assertIn(
            "SCENARIO_OBSERVATION_NE_NEW_FACTUAL_ECONOMIC_KNOWLEDGE",
            econ[0].limitations,
        )

    def test_candidate_types_do_not_duplicate_labor(self) -> None:
        joint = _base()
        # Labor conserved once at observation layer regardless of candidate count
        fixture = _fixture_obs(joint)
        labor = sum(o.claimed_labor_man_minutes or 0.0 for o in fixture)
        self.assertEqual(labor, 1425.0)
        self.assertGreater(joint.s12.shift_summary.knowledge_candidate_count, 0)

    def test_exploratory_eligibility_semantics(self) -> None:
        joint = _base()
        fit = [
            o
            for o in _fixture_obs(joint)
            if o.original_operation_text == "Изготовление фасонных изделий"
        ][0]
        self.assertEqual(
            fit.reuse_eligibility, ReuseEligibility.ELIGIBLE_FOR_EXPLORATORY_COMPARISON
        )
        self.assertIn("COMPARABILITY_CONTEXT_INCOMPLETE", fit.missing_context)
        self.assertIn("EXPLORATORY_DESCRIPTIVE_USE_ONLY", fit.limitations)
        self.assertIn(
            "COMPUTABLE_UNIT_LABOR_NE_ESTABLISHED_COMPARABILITY", fit.limitations
        )
        self.assertIn(
            "NO_BENCHMARK_POPULATION_AGGREGATION_WITHOUT_PROVEN_COMPARABILITY",
            fit.limitations,
        )
        self.assertIn(
            "TWELVE_SKILLS_PASS_NE_EVIDENCE_AUTHORITY_ESCALATION", fit.limitations
        )


class HistoricalAggregationTests(unittest.TestCase):
    def test_synthetic_population_via_s11_not_norm(self) -> None:
        hist = (
            HistoricalLaborObservation(
                operation_code="INS.FITTING_FAB",
                eligible_labor_man_minutes=180.0,
                physical_quantity=20.0,
                physical_unit="шт",
                observation_identity="hB",
                project_code="FIXTURE_INSULATION_DEMO",
            ),
            HistoricalLaborObservation(
                operation_code="INS.FITTING_FAB",
                eligible_labor_man_minutes=550.0,
                physical_quantity=50.0,
                physical_unit="шт",
                observation_identity="hC",
                project_code="FIXTURE_INSULATION_DEMO",
            ),
            HistoricalLaborObservation(
                operation_code="INS.FITTING_FAB",
                eligible_labor_man_minutes=285.0,
                physical_quantity=30.0,
                physical_unit="шт",
                observation_identity="hD",
                project_code="FIXTURE_INSULATION_DEMO",
            ),
            HistoricalLaborObservation(
                operation_code="INS.FITTING_FAB",
                eligible_labor_man_minutes=540.0,
                physical_quantity=60.0,
                physical_unit="шт",
                observation_identity="hE",
                project_code="FIXTURE_INSULATION_DEMO",
            ),
        )
        joint = _base(audit_id="s12_hist", historical_observations=hist)
        # S11 may aggregate; S12 must not declare approved norm
        self.assertEqual(joint.s12.shift_summary.approved_labor_norm_count, 0)
        self.assertEqual(
            joint.s12.approved_production_labor_norm_created_status,
            "APPROVED_PRODUCTION_LABOR_NORM_CREATED_NO",
        )


class SerializationAndIntegrationTests(unittest.TestCase):
    def test_serialization(self) -> None:
        joint = _base(audit_id="s12_ser")
        raw = json.dumps(joint.s12.to_dict(), ensure_ascii=False, default=str)
        self.assertIn("S12_ENGINE_IMPLEMENTED", raw)
        self.assertIn("APPROVED_PRODUCTION_KNOWLEDGE_CREATED_NO", raw)
        self.assertNotIn("AUTONOMOUS_LEARNING_IMPLEMENTED_YES", raw)

    def test_prior_artifacts_unchanged(self) -> None:
        joint = _base(audit_id="s12_prior")
        self.assertEqual(joint.s09.human_decision_required, True)
        self.assertEqual(
            joint.s09.positive_physical_acceptance_recommendation_status,
            "POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN",
        )
        self.assertEqual(joint.s08.physical_execution_verified_status, "PHYSICAL_EXECUTION_VERIFIED_NO")

    def test_operation_table_coverage(self) -> None:
        joint = _base()
        rows = _fixture_obs(joint)
        self.assertEqual(len(rows), 11)
        for o in rows:
            self.assertIsNotNone(o.reuse_eligibility)
            self.assertIsNotNone(o.evidence_authority)
            self.assertTrue(o.limitations)


if __name__ == "__main__":
    unittest.main()
