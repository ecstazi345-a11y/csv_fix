"""PSAA-06 / S11 — Labor Benchmark & Observation Eligibility tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from agents.production_shift_auditor.contracts import (
    LaborSemanticsStatus,
    LaborUnit,
    ManagerialAcceptanceStatus,
    OperationLaborClaim,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.professional_assessment import assess_shift
from agents.production_shift_auditor.s10_contracts import ClassificationStatus
from agents.production_shift_auditor.s11_contracts import (
    BenchmarkAuthorityStatus,
    BenchmarkComparisonStatus,
    BenchmarkReference,
    ComparabilityStatus,
    HistoricalLaborObservation,
    LaborCalculationStatus,
    ObservationEligibility,
)
from agents.production_shift_auditor.s11_labor_benchmark import (
    aggregate_historical_observations,
    evaluate_s11,
)


def _by_name(art, name: str):
    hits = [f for f in art.findings if f.original_operation_text == name]
    assert hits, f"no S11 finding for {name!r}"
    return hits[0]


class FixtureArithmeticTests(unittest.TestCase):
    def test_fitting_unit_labor_and_productivity(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_fit")
        f = _by_name(joint.s11, "Изготовление фасонных изделий")
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION
        )
        self.assertAlmostEqual(f.unit_labor_man_minutes_per_physical, 10.0)
        self.assertAlmostEqual(f.unit_labor_man_hours_per_physical, 10.0 / 60.0, places=7)
        self.assertAlmostEqual(f.productivity_per_man_hour, 6.0)
        self.assertEqual(
            f.observation_eligibility, ObservationEligibility.HISTORICAL_ANALYSIS_CANDIDATE
        )
        self.assertIn("CLAIMED_UNIT_LABOR_NE_VERIFIED_UNIT_LABOR", f.eligibility_reasons)
        self.assertEqual(f.evidence_status, "CLAIMED_ONLY_NOT_VERIFIED_NOT_APPROVED_NORM")
        self.assertEqual(
            f.benchmark_comparison_status, BenchmarkComparisonStatus.BENCHMARK_NOT_AVAILABLE
        )

    def test_al_clad_unit_labor_and_productivity(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_clad")
        f = _by_name(joint.s11, "Монтаж AL CLAD AD")
        self.assertAlmostEqual(f.unit_labor_man_minutes_per_physical, 200.0 / 6.0, places=7)
        self.assertAlmostEqual(f.unit_labor_man_hours_per_physical, 0.5555556, places=7)
        self.assertAlmostEqual(f.productivity_per_man_hour, 1.8, places=7)
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION
        )

    def test_fixture_total_preserved_and_no_acceptance(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_tot")
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(joint.s11.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(joint.s11.norm_mutation_status, "NOT_PERFORMED")
        self.assertEqual(joint.s11.approved_norm_status, "APPROVED_LABOR_NORMS_NOT_CREATED")
        self.assertEqual(joint.s11.verified_observation_status, "VERIFIED_OBSERVATIONS_NOT_PROVEN")
        blob = (
            joint.s11.human_readable_summary
            + " "
            + " ".join(joint.s11.observations)
            + " "
            + str(joint.s01.managerial_acceptance_status.value)
        )
        self.assertNotIn("ACCEPTED", blob)
        self.assertNotIn("REJECTED", blob)
        self.assertEqual(
            joint.s01.managerial_acceptance_status,
            ManagerialAcceptanceStatus.NOT_IN_SCOPE,
        )
        for f in joint.s11.findings:
            self.assertEqual(f.preserved_claimed_labor_quantity, f.original_claimed_labor_quantity)


class EdgeCaseTests(unittest.TestCase):
    def test_zero_quantity_positive_labor(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    100,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=0.0,
                    physical_unit="шт",
                ),
            ),
        )
        f = assess_shift(inp, audit_id="s11_zq").s11.findings[0]
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.LABOR_WITHOUT_POSITIVE_QUANTITY
        )
        self.assertEqual(f.eligible_labor_man_minutes, 100.0)
        self.assertIsNone(f.unit_labor_man_minutes_per_physical)
        self.assertEqual(f.labor_without_quantity_category, "zero_claimed_quantity")
        self.assertIn("LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_LOSS", f.eligibility_reasons)
        self.assertIn("не объявляется автоматической потерей", f.professional_conclusion.lower())

    def test_absent_quantity(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim("Подготовка поверхности", 30, LaborUnit.MAN_MINUTE),
            ),
        )
        f = assess_shift(inp, audit_id="s11_aq").s11.findings[0]
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.LABOR_WITHOUT_POSITIVE_QUANTITY
        )
        self.assertEqual(f.eligible_labor_man_minutes, 30.0)
        self.assertIsNotNone(f.labor_without_quantity_category)
        self.assertEqual(
            f.observation_eligibility, ObservationEligibility.NOT_ELIGIBLE_FOR_BENCHMARK
        )
        # Preserved for future economics — not auto-loss
        self.assertIn("экономики", f.professional_conclusion.lower())

    def test_zero_labor_positive_quantity(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    0,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=10.0,
                    physical_unit="шт",
                ),
            ),
        )
        f = assess_shift(inp, audit_id="s11_zl").s11.findings[0]
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.UNIT_LABOR_NOT_COMPUTABLE
        )
        self.assertIsNone(f.unit_labor_man_minutes_per_physical)
        self.assertIn("NO_DIVISION_BY_ZERO", f.eligibility_reasons)

    def test_unproven_labor_semantics_no_silent_conversion(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            labor_semantics_status=LaborSemanticsStatus.UNPROVEN,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.HOUR_FIELD_UNPROVEN,
                    physical_quantity=40.0,
                    physical_unit="шт",
                ),
            ),
        )
        f = assess_shift(inp, audit_id="s11_unp").s11.findings[0]
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.UNIT_LABOR_NOT_COMPUTABLE
        )
        self.assertIsNone(f.unit_labor_man_minutes_per_physical)
        self.assertIn("NO_SILENT_CONVERSION_TO_MAN_HOURS", f.eligibility_reasons)

    def test_negative_invalid(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    -5,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=40.0,
                    physical_unit="шт",
                ),
            ),
        )
        f = assess_shift(inp, audit_id="s11_neg").s11.findings[0]
        self.assertEqual(f.calculation_status, LaborCalculationStatus.INVALID_INPUT)

    def test_composite_not_allocated(self) -> None:
        # Fixture already includes COMPOSITE S10 line «Раскрой и устранение деформаций»
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Раскрой и устранение деформаций",
                    75,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=5.0,
                    physical_unit="м2",
                ),
            ),
        )
        joint = assess_shift(inp, audit_id="s11_comp")
        self.assertEqual(
            joint.s10.classifications[0].classification_status,
            ClassificationStatus.COMPOSITE_OPERATION,
        )
        f = joint.s11.findings[0]
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.COMPOSITE_NOT_ALLOCATABLE
        )
        self.assertEqual(f.preserved_claimed_labor_quantity, 75.0)
        self.assertEqual(f.preserved_physical_quantity, 5.0)
        self.assertIsNone(f.unit_labor_man_minutes_per_physical)
        self.assertIn("NO_AUTOMATIC_LABOR_OR_QUANTITY_ALLOCATION", f.eligibility_reasons)

    def test_prep_labor_not_declared_loss(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_prep")
        f = _by_name(joint.s11, "Подготовка клея")
        self.assertEqual(
            f.calculation_status, LaborCalculationStatus.LABOR_WITHOUT_POSITIVE_QUANTITY
        )
        self.assertIn("LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_LOSS", f.eligibility_reasons)
        joined = f.professional_conclusion.lower()
        self.assertIn("не объявляется автоматической потерей", joined)
        self.assertNotIn("доказанная потеря", joined)

    def test_demo_findings_do_not_verify_observation(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_demo")
        f = _by_name(joint.s11, "Изготовление фасонных изделий")
        self.assertEqual(f.evidence_status, "CLAIMED_ONLY_NOT_VERIFIED_NOT_APPROVED_NORM")
        self.assertEqual(
            joint.s11.verified_observation_status, "VERIFIED_OBSERVATIONS_NOT_PROVEN"
        )
        self.assertIn(
            "demonstration_s02_s03_do_not_create_verified_observation",
            f.eligibility_reasons,
        )


class ComparabilityAndAggregationTests(unittest.TestCase):
    def test_different_materials_not_merged(self) -> None:
        obs = (
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                400.0,
                40.0,
                "шт",
                material_hint="PE",
                claimed_result_state="MANUFACTURED",
            ),
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                200.0,
                20.0,
                "шт",
                material_hint="PIR",
                claimed_result_state="MANUFACTURED",
            ),
        )
        aggs = aggregate_historical_observations(obs)
        self.assertEqual(len(aggs), 2)
        for a in aggs:
            self.assertEqual(a.observation_count, 1)
            self.assertEqual(a.approved_norm_status, "NOT_AN_APPROVED_NORM")

    def test_different_result_states_not_merged(self) -> None:
        obs = (
            HistoricalLaborObservation(
                "INS.CLADDING",
                200.0,
                6.0,
                "м2",
                claimed_result_state="INSTALLED",
            ),
            HistoricalLaborObservation(
                "INS.CLADDING",
                100.0,
                3.0,
                "м2",
                claimed_result_state="MANUFACTURED",
            ),
        )
        aggs = aggregate_historical_observations(obs)
        self.assertEqual(len(aggs), 2)

    def test_quantity_weighted_unit_labor(self) -> None:
        # 10 мин/шт on 40шт (400) + 20 мин/шт on 10шт (200)
        # weighted = 600/50 = 12; simple mean of ratios = 15 — must NOT use simple mean
        obs = (
            HistoricalLaborObservation("INS.FITTING_FABRICATION", 400.0, 40.0, "шт"),
            HistoricalLaborObservation("INS.FITTING_FABRICATION", 200.0, 10.0, "шт"),
        )
        aggs = aggregate_historical_observations(obs)
        self.assertEqual(len(aggs), 1)
        a = aggs[0]
        self.assertEqual(a.observation_count, 2)
        self.assertAlmostEqual(a.total_quantity, 50.0)
        self.assertAlmostEqual(a.total_eligible_labor_man_minutes, 600.0)
        self.assertAlmostEqual(a.quantity_weighted_unit_labor_man_minutes, 12.0)
        self.assertNotAlmostEqual(
            a.quantity_weighted_unit_labor_man_minutes,
            sum(a.individual_unit_labor_man_minutes) / len(a.individual_unit_labor_man_minutes),
        )
        self.assertAlmostEqual(a.minimum_unit_labor_man_minutes, 10.0)
        self.assertAlmostEqual(a.maximum_unit_labor_man_minutes, 20.0)
        self.assertAlmostEqual(a.median_unit_labor_man_minutes, 15.0)
        self.assertIn("small_sample_not_an_approved_norm", a.sample_limitations)
        self.assertEqual(a.approved_norm_status, "NOT_AN_APPROVED_NORM")

    def test_small_sample_not_approved_norm(self) -> None:
        obs = (
            HistoricalLaborObservation("INS.CLADDING", 200.0, 6.0, "м2"),
        )
        a = aggregate_historical_observations(obs)[0]
        self.assertEqual(a.observation_count, 1)
        self.assertIn("small_sample_not_an_approved_norm", a.sample_limitations)
        self.assertEqual(a.approved_norm_status, "NOT_AN_APPROVED_NORM")

    def test_missing_benchmark_not_invented(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_nobm")
        for f in joint.s11.findings:
            if f.calculation_status == LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION:
                self.assertEqual(
                    f.benchmark_comparison_status,
                    BenchmarkComparisonStatus.BENCHMARK_NOT_AVAILABLE,
                )
                self.assertIsNone(f.benchmark_reference_id)

    def test_incompatible_benchmark_not_used(self) -> None:
        bm = BenchmarkReference(
            operation_code="INS.CLADDING",
            unit_labor_man_hours_per_physical=0.5,
            physical_unit="м",  # wrong unit vs м2
            source_id="demo_bench",
            source_version="v0",
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s11_bm_bad",
            benchmarks=(bm,),
        )
        f = _by_name(joint.s11, "Монтаж AL CLAD AD")
        self.assertEqual(
            f.benchmark_comparison_status, BenchmarkComparisonStatus.BENCHMARK_INCOMPATIBLE
        )
        self.assertIsNone(f.benchmark_deviation_pct)

    def test_compatible_benchmark_claimed_only(self) -> None:
        bm = BenchmarkReference(
            operation_code="INS.CLADDING",
            unit_labor_man_hours_per_physical=0.5,
            physical_unit="м2",
            source_id="injected_read_only",
            source_version="test-v1",
            applicability_note="test inject only",
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s11_bm_ok",
            benchmarks=(bm,),
        )
        f = _by_name(joint.s11, "Монтаж AL CLAD AD")
        self.assertEqual(
            f.benchmark_comparison_status,
            BenchmarkComparisonStatus.BENCHMARK_COMPARED_CLAIMED_ONLY,
        )
        self.assertIsNotNone(f.benchmark_deviation_pct)
        self.assertIn("BENCHMARK_DEVIATION_NE_PROVEN_INEFFICIENCY", f.eligibility_reasons)
        # No mutation
        self.assertEqual(joint.s11.norm_mutation_status, "NOT_PERFORMED")

    def test_aggregation_via_assess_shift(self) -> None:
        hist = (
            HistoricalLaborObservation("INS.FITTING_FABRICATION", 400.0, 40.0, "шт"),
            HistoricalLaborObservation("INS.FITTING_FABRICATION", 200.0, 10.0, "шт"),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s11_agg",
            historical_observations=hist,
        )
        self.assertTrue(joint.s11.aggregations)
        self.assertEqual(joint.s11.aggregations[0].approved_norm_status, "NOT_AN_APPROVED_NORM")


class IntegrationRegressionSmoke(unittest.TestCase):
    def test_joint_stack_serializable(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_joint")
        self.assertEqual(len(joint.s11.findings), 11)
        d = joint.s11.to_dict()
        self.assertEqual(d["managerial_acceptance_status"], "NOT_IN_SCOPE")
        self.assertEqual(d["payroll_decision_status"], "NOT_PERFORMED")
        self.assertEqual(d["commercial_recognition_status"], "NOT_PERFORMED")
        self.assertEqual(d["durable_history_schema_status"], "UNCHANGED_IN_THIS_INCREMENT")
        self.assertEqual(
            d["production_labor_norm_read_adapter_status"], "NOT_IMPLEMENTED_LIMITATION"
        )
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(len(joint.s10.classifications), 11)
        self.assertTrue(joint.s02.findings)
        self.assertTrue(joint.s03.findings)

    def test_evaluate_s11_direct_does_not_mutate_s01(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_direct")
        before = joint.s01.s01_metrics.claimed_total_man_minutes
        art = evaluate_s11(
            joint.audit_input, joint.s01, joint.s10, joint.s02, joint.s03, audit_id="x"
        )
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, before)
        self.assertEqual(art.norm_mutation_status, "NOT_PERFORMED")


class FinalGateVerificationTests(unittest.TestCase):
    def test_labor_conservation_fixture_1425_600_825(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_cons")
        c = joint.s11.labor_conservation
        self.assertAlmostEqual(c.total_claimed_labor_man_minutes, 1425.0)
        self.assertAlmostEqual(c.labor_with_computable_unit_indicators_man_minutes, 600.0)
        self.assertAlmostEqual(c.labor_without_computable_unit_indicators_man_minutes, 825.0)
        self.assertAlmostEqual(c.preserved_total_man_minutes, 1425.0)
        self.assertTrue(c.conservation_holds)
        self.assertTrue(c.categories_mutually_exclusive)
        self.assertTrue(c.labor_without_unit_ne_automatic_losses)
        # No double-count: sum of partitions == total
        self.assertAlmostEqual(
            c.labor_with_computable_unit_indicators_man_minutes
            + c.labor_without_computable_unit_indicators_man_minutes,
            c.total_claimed_labor_man_minutes,
        )

    def test_geometry_dn50_vs_dn500_not_auto_merged(self) -> None:
        obs = (
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                100.0,
                10.0,
                "шт",
                geometry_hint="DN50",
                claimed_result_state="MANUFACTURED",
            ),
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                500.0,
                10.0,
                "шт",
                geometry_hint="DN500",
                claimed_result_state="MANUFACTURED",
            ),
        )
        aggs = aggregate_historical_observations(obs)
        self.assertEqual(len(aggs), 2)
        for a in aggs:
            self.assertEqual(a.observation_count, 1)
        # Full comparability not claimed merely by code+unit on fixture observation
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s11_comp_gate")
        f = _by_name(joint.s11, "Изготовление фасонных изделий")
        self.assertIn(
            f.comparability_status,
            {
                ComparabilityStatus.COMPARABILITY_CONTEXT_INCOMPLETE,
                ComparabilityStatus.FULL_COMPARABILITY_NOT_PROVEN,
            },
        )
        self.assertIn("SAME_OPERATION_CODE_NE_AUTOMATIC_COMPARABILITY", f.comparability_limitations)
        self.assertIn(
            "example_DN50_vs_DN500_fittings_not_auto_comparable_by_code_and_unit_alone",
            f.comparability_limitations,
        )

    def test_observation_identity_dedupe_and_cross_project(self) -> None:
        obs = (
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                400.0,
                40.0,
                "шт",
                observation_identity="obs-1",
                project_code="P1",
            ),
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                400.0,
                40.0,
                "шт",
                observation_identity="obs-1",  # re-audit same identity
                project_code="P1",
                source_record_version="v2",
            ),
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                200.0,
                10.0,
                "шт",
                observation_identity="obs-2",
                project_code="P2",
            ),
        )
        # Same identity counted once
        aggs_p1 = aggregate_historical_observations(obs, allowed_project_scope="P1")
        self.assertEqual(len(aggs_p1), 1)
        self.assertEqual(aggs_p1[0].observation_count, 1)
        self.assertGreaterEqual(aggs_p1[0].excluded_or_non_comparable_count, 1)
        # Without scope filter: different projects stay in separate buckets
        aggs_all = aggregate_historical_observations(obs)
        joined = " | ".join(" ".join(a.sample_limitations) for a in aggs_all)
        self.assertIn("project_bucket=P1", joined)
        self.assertIn("project_bucket=P2", joined)

    def test_benchmark_authority_not_auto_approved(self) -> None:
        bm = BenchmarkReference(
            operation_code="INS.CLADDING",
            unit_labor_man_hours_per_physical=0.5,
            physical_unit="м2",
            source_id="ext_ref",
            source_version="v3",
            applicability_note="injected",
            provenance_note="caller_injected_read_only_reference",
            authority_status=BenchmarkAuthorityStatus.EXTERNAL_REFERENCE_UNVERIFIED,
            approval_status="NOT_AUTO_APPROVED_BY_S11",
            project_scope="FIXTURE_INSULATION_DEMO",
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s11_bm_auth",
            benchmarks=(bm,),
        )
        f = _by_name(joint.s11, "Монтаж AL CLAD AD")
        self.assertEqual(
            f.benchmark_comparison_status,
            BenchmarkComparisonStatus.BENCHMARK_COMPARED_CLAIMED_ONLY,
        )
        self.assertIsNotNone(f.benchmark_authority_status)
        self.assertIn("EXTERNAL_REFERENCE_UNVERIFIED", f.benchmark_authority_status or "")
        self.assertIn("NOT_AUTO_APPROVED_BY_S11", f.benchmark_authority_status or "")
        self.assertIn(
            "EXTERNAL_BENCHMARK_REFERENCE_NE_APPROVED_LABOR_NORM_BY_S11",
            f.eligibility_reasons,
        )
        self.assertEqual(
            joint.s11.production_labor_norm_read_adapter_status,
            "NOT_IMPLEMENTED_LIMITATION",
        )
        self.assertEqual(joint.s11.approved_norm_status, "APPROVED_LABOR_NORMS_NOT_CREATED")

    def test_weighted_aggregation_presentation_fields(self) -> None:
        obs = (
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                400.0,
                40.0,
                "шт",
                observation_identity="a",
            ),
            HistoricalLaborObservation(
                "INS.FITTING_FABRICATION",
                200.0,
                10.0,
                "шт",
                observation_identity="b",
            ),
        )
        a = aggregate_historical_observations(obs)[0]
        self.assertAlmostEqual(a.quantity_weighted_unit_labor_man_minutes, 12.0)
        self.assertEqual(a.observation_count, 2)
        self.assertEqual(set(a.included_observation_identities), {"a", "b"})
        self.assertEqual(a.benchmark_authority_note, "AGGREGATE_IS_NOT_BENCHMARK_AUTHORITY")
        self.assertEqual(a.approved_norm_status, "NOT_AN_APPROVED_NORM")
        self.assertNotEqual(
            a.comparability_status, ComparabilityStatus.NOT_COMPARABLE
        )


if __name__ == "__main__":
    unittest.main()
