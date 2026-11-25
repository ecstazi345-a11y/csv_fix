"""PSAA-07 / S04 — Execution Cost Analysis tests."""

from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from agents.production_shift_auditor.contracts import (
    LaborSemanticsStatus,
    LaborUnit,
    ManagerialAcceptanceStatus,
    OperationLaborClaim,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.professional_assessment import assess_shift
from agents.production_shift_auditor.s04_contracts import (
    ActualCostVerificationStatus,
    CostCalculationStatus,
    CostCompleteness,
    CostRateAuthority,
    CostRateEconomicType,
    CostRateUnit,
    LaborCostRateReference,
)
from agents.production_shift_auditor.s04_execution_cost import (
    scenario_rate_1000_rub_per_man_hour,
)
from agents.production_shift_auditor.s10_contracts import ClassificationStatus


def _by_name(art, name: str):
    hits = [f for f in art.findings if f.original_operation_text == name]
    assert hits, f"no S04 finding for {name!r}"
    return hits[0]


def _d(s: str | None) -> Decimal:
    assert s is not None
    return Decimal(s)


class FixtureCostArithmeticTests(unittest.TestCase):
    def test_fixture_total_23750_and_unit_costs(self) -> None:
        rate = scenario_rate_1000_rub_per_man_hour()
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_fix",
            cost_rates=(rate,),
        )
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        c = joint.s04.cost_conservation
        self.assertEqual(_d(c.total_claimed_labor_man_minutes), Decimal("1425.0000"))
        self.assertEqual(_d(c.total_calculated_direct_labor_cost_exact), Decimal("23750.0000"))
        self.assertEqual(_d(c.cost_with_computable_unit_indicators_exact), Decimal("10000.0000"))
        self.assertEqual(
            _d(c.cost_without_computable_unit_indicators_exact), Decimal("13750.0000")
        )
        self.assertTrue(c.conservation_holds)
        self.assertEqual(c.calculation_completeness, CostCompleteness.FULL_MONETIZED)
        self.assertEqual(c.currency, "RUB")

        fit = _by_name(joint.s04, "Изготовление фасонных изделий")
        self.assertEqual(_d(fit.computed_direct_labor_cost_exact), Decimal("6666.6667"))
        self.assertEqual(_d(fit.computed_unit_labor_cost_exact), Decimal("166.6667"))
        self.assertTrue(fit.has_computable_unit_cost)

        clad = _by_name(joint.s04, "Монтаж AL CLAD AD")
        self.assertEqual(_d(clad.computed_direct_labor_cost_exact), Decimal("3333.3333"))
        self.assertEqual(_d(clad.computed_unit_labor_cost_exact), Decimal("555.5556"))

        self.assertEqual(len(joint.s04.findings), 11)
        self.assertEqual(
            joint.s04.actual_cost_verification_status,
            ActualCostVerificationStatus.ACTUAL_COST_NOT_PROVEN,
        )
        self.assertEqual(joint.s04.full_execution_cost_status, "FULL_EXECUTION_COST_NOT_COMPUTABLE")
        self.assertEqual(joint.s04.margin_status, "NOT_COMPUTED")
        self.assertEqual(joint.s04.revenue_status, "NOT_COMPUTED")
        self.assertEqual(joint.s04.payroll_decision_status, "NOT_PERFORMED")
        self.assertEqual(joint.s04.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(
            joint.s01.managerial_acceptance_status, ManagerialAcceptanceStatus.NOT_IN_SCOPE
        )

    def test_prep_and_composite_preserve_cost_without_unit(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_prep",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        prep = _by_name(joint.s04, "Подготовка клея")
        self.assertIsNotNone(prep.computed_direct_labor_cost_exact)
        self.assertFalse(prep.has_computable_unit_cost)
        blob = (
            prep.labor_category_note
            + prep.professional_conclusion
            + " ".join(prep.authority_limitations)
        ).lower()
        self.assertIn("labor_without_quantity_ne_automatic_financial_loss", blob)

        # Composite from fixture
        comp_lines = [
            f
            for f in joint.s04.findings
            if f.calculation_status == CostCalculationStatus.COMPOSITE_COST_UNALLOCATED
        ]
        self.assertTrue(comp_lines)
        self.assertIsNotNone(comp_lines[0].computed_direct_labor_cost_exact)
        self.assertFalse(comp_lines[0].has_computable_unit_cost)
        self.assertIn("COMPOSITE", comp_lines[0].professional_conclusion)

    def test_zero_quantity_still_monetizes_labor(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    60,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=0.0,
                    physical_unit="шт",
                ),
            ),
        )
        f = assess_shift(
            inp, audit_id="s04_zq", cost_rates=(scenario_rate_1000_rub_per_man_hour(),)
        ).s04.findings[0]
        self.assertEqual(_d(f.computed_direct_labor_cost_exact), Decimal("1000.0000"))
        self.assertFalse(f.has_computable_unit_cost)
        self.assertIn("LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_FINANCIAL_LOSS", f.authority_limitations)


class RateAuthorityAndGapTests(unittest.TestCase):
    def test_missing_rate_not_zero_fill(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s04_norate")
        self.assertEqual(
            joint.s04.cost_conservation.calculation_completeness,
            CostCompleteness.NONE_MONETIZED,
        )
        self.assertIsNone(joint.s04.cost_conservation.total_calculated_direct_labor_cost_exact)
        for f in joint.s04.findings:
            self.assertIsNone(f.computed_direct_labor_cost_exact)
            self.assertEqual(
                f.calculation_status, CostCalculationStatus.COST_RATE_NOT_AVAILABLE
            )

    def test_hour_field_unproven(self) -> None:
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
        f = assess_shift(
            inp, audit_id="s04_unp", cost_rates=(scenario_rate_1000_rub_per_man_hour(),)
        ).s04.findings[0]
        self.assertEqual(f.calculation_status, CostCalculationStatus.LABOR_SEMANTICS_UNPROVEN)
        self.assertIsNone(f.computed_direct_labor_cost_exact)

    def test_scope_mismatch(self) -> None:
        rate = replace(
            scenario_rate_1000_rub_per_man_hour(),
            applicable_project_scope="OTHER_PROJECT",
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_scope",
            cost_rates=(rate,),
        )
        self.assertEqual(
            joint.s04.findings[0].calculation_status,
            CostCalculationStatus.COST_RATE_NOT_APPLICABLE,
        )

    def test_contract_price_not_applicable(self) -> None:
        rate = LaborCostRateReference(
            rate_identity="contract_price",
            rate_value="5000",
            currency="RUB",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.APPROVED_COST_RATE,
            economic_type=CostRateEconomicType.CONTRACT_UNIT_PRICE,
            provenance="test",
            version="v1",
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_contract",
            cost_rates=(rate,),
        )
        self.assertEqual(
            joint.s04.findings[0].calculation_status,
            CostCalculationStatus.COST_RATE_NOT_APPLICABLE,
        )

    def test_wage_rate_not_applicable(self) -> None:
        rate = LaborCostRateReference(
            rate_identity="wage",
            rate_value="1000",
            currency="RUB",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.APPROVED_COST_RATE,
            economic_type=CostRateEconomicType.WAGE_RATE,
            provenance="test",
            version="v1",
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
        )
        f = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_wage",
            cost_rates=(rate,),
        ).s04.findings[0]
        self.assertEqual(f.calculation_status, CostCalculationStatus.COST_RATE_NOT_APPLICABLE)

    def test_expired_rate_not_applied(self) -> None:
        rate = replace(
            scenario_rate_1000_rub_per_man_hour(),
            valid_from="2010-01-01",
            valid_to="2015-12-31",
        )
        f = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_exp",
            cost_rates=(rate,),
        ).s04.findings[0]
        self.assertEqual(f.calculation_status, CostCalculationStatus.COST_RATE_NOT_APPLICABLE)

    def test_scenario_not_actual_and_approved_not_proven_incurred(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_sc",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        f = _by_name(joint.s04, "Изготовление фасонных изделий")
        self.assertEqual(f.calculation_status, CostCalculationStatus.SCENARIO_COST_COMPUTED)
        self.assertEqual(f.evidence_status, "SCENARIO_CLAIMED_DIRECT_LABOR_COST_NOT_ACTUAL")
        self.assertEqual(
            joint.s04.actual_cost_verification_status,
            ActualCostVerificationStatus.ACTUAL_COST_NOT_PROVEN,
        )

        approved = LaborCostRateReference(
            rate_identity="approved_direct",
            rate_value="1000",
            currency="RUB",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.APPROVED_COST_RATE,
            economic_type=CostRateEconomicType.EMPLOYER_DIRECT_LABOR_COST_RATE,
            provenance="test_approved",
            version="v1",
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
            valid_from="2020-01-01",
            valid_to="2099-12-31",
        )
        j2 = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_appr",
            cost_rates=(approved,),
        )
        f2 = _by_name(j2.s04, "Изготовление фасонных изделий")
        self.assertEqual(f2.calculation_status, CostCalculationStatus.ESTIMATED_COST_COMPUTED)
        self.assertEqual(
            f2.evidence_status, "APPROVED_RATE_USED_BUT_ACTUAL_INCURRED_COST_NOT_PROVEN"
        )
        self.assertEqual(
            j2.s04.actual_cost_verification_status,
            ActualCostVerificationStatus.ACTUAL_COST_NOT_PROVEN,
        )

    def test_multi_currency_not_summed(self) -> None:
        r1 = scenario_rate_1000_rub_per_man_hour()
        r2 = LaborCostRateReference(
            rate_identity="usd",
            rate_value="10",
            currency="USD",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.SCENARIO_RATE,
            economic_type=CostRateEconomicType.EMPLOYER_DIRECT_LABOR_COST_RATE,
            provenance="test",
            version="v1",
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_fx",
            cost_rates=(r1, r2),
        )
        self.assertIsNone(joint.s04.cost_conservation.total_calculated_direct_labor_cost_exact)
        self.assertEqual(
            joint.s04.findings[0].calculation_status,
            CostCalculationStatus.COST_RATE_NOT_APPLICABLE,
        )

    def test_partial_coverage_when_mixed_monetizable(self) -> None:
        # One op with proven labor + rate; inject rate only for project but
        # second assessment path: use unproven alone already covered.
        # Partial: rate present but one op unproven in multi-op input.
        base = build_insulation_pipeline_fixture()
        ops = list(base.operations)
        ops[0] = OperationLaborClaim(
            "Подготовка поверхности",
            1,
            LaborUnit.HOUR_FIELD_UNPROVEN,
        )
        inp = replace(base, operations=tuple(ops), labor_semantics_status=LaborSemanticsStatus.UNPROVEN)
        # With UNPROVEN semantics, S11 may block conversion for HOUR_FIELD only on that line;
        # other lines still have MAN_MINUTE — S11 converts MAN_MINUTE regardless of shift semantics status for unit.
        # Force only first line unproven by keeping EXPLICIT on others via separate units.
        inp = replace(
            base,
            operations=(
                OperationLaborClaim("Подготовка поверхности", 1, LaborUnit.HOUR_FIELD_UNPROVEN),
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    400,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=40.0,
                    physical_unit="шт",
                ),
            ),
        )
        joint = assess_shift(
            inp,
            audit_id="s04_partial",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        self.assertEqual(
            joint.s04.cost_conservation.calculation_completeness,
            CostCompleteness.PARTIAL_COST_COVERAGE,
        )
        self.assertIsNotNone(
            joint.s04.cost_conservation.total_calculated_direct_labor_cost_exact
        )
        statuses = {f.calculation_status for f in joint.s04.findings}
        self.assertIn(CostCalculationStatus.LABOR_SEMANTICS_UNPROVEN, statuses)
        self.assertIn(CostCalculationStatus.SCENARIO_COST_COMPUTED, statuses)


class IntegrationAndSafetyTests(unittest.TestCase):
    def test_joint_serializable_and_no_mutations(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_joint",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        d = joint.s04.to_dict()
        self.assertEqual(d["payroll_decision_status"], "NOT_PERFORMED")
        self.assertEqual(d["commercial_recognition_status"], "NOT_PERFORMED")
        self.assertEqual(d["cost_rate_mutation_status"], "NOT_PERFORMED")
        self.assertEqual(d["contract_price_mutation_status"], "NOT_PERFORMED")
        self.assertEqual(
            d["production_cost_rate_read_adapter_status"], "NOT_IMPLEMENTED_LIMITATION"
        )
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(len(joint.s11.findings), 11)
        self.assertEqual(len(joint.s04.findings), 11)
        # Monetary reconciliation residual documented
        self.assertIsNotNone(joint.s04.cost_conservation.reconciliation_note)
        self.assertTrue(joint.s04.cost_conservation.categories_mutually_exclusive)

    def test_composite_classification_preserved(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_comp_s10",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        self.assertTrue(
            any(
                c.classification_status == ClassificationStatus.COMPOSITE_OPERATION
                for c in joint.s10.classifications
            )
        )


class FinalGateVerificationTests(unittest.TestCase):
    def test_cost_conservation_fixture_partition(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_cons_gate",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        c = joint.s04.cost_conservation
        self.assertEqual(_d(c.total_claimed_labor_man_minutes), Decimal("1425.0000"))
        self.assertEqual(_d(c.monetized_labor_man_minutes), Decimal("1425.0000"))
        self.assertEqual(_d(c.non_monetized_labor_man_minutes), Decimal("0.0000"))
        self.assertEqual(_d(c.total_calculated_direct_labor_cost_exact), Decimal("23750.0000"))
        self.assertEqual(_d(c.cost_with_computable_unit_indicators_exact), Decimal("10000.0000"))
        self.assertEqual(
            _d(c.cost_without_computable_unit_indicators_exact), Decimal("13750.0000")
        )
        self.assertTrue(c.conservation_holds)
        self.assertEqual(len(joint.s04.findings), 11)

    def test_zero_rate_requires_explicit_confirmation(self) -> None:
        bad = LaborCostRateReference(
            rate_identity="zero_bad",
            rate_value="0",
            currency="RUB",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.SCENARIO_RATE,
            economic_type=CostRateEconomicType.EMPLOYER_DIRECT_LABOR_COST_RATE,
            provenance="test",
            version="v1",
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
        )
        f = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_zero_bad",
            cost_rates=(bad,),
        ).s04.findings[0]
        self.assertEqual(f.calculation_status, CostCalculationStatus.COST_RATE_NOT_APPLICABLE)
        self.assertIsNone(f.computed_direct_labor_cost_exact)

        ok = replace(
            bad,
            rate_identity="zero_ok",
            applicability_note="ZERO_RATE_EXPLICITLY_CONFIRMED for demo only",
        )
        f2 = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s04_zero_ok",
            cost_rates=(ok,),
        ).s04.findings[0]
        self.assertEqual(_d(f2.computed_direct_labor_cost_exact), Decimal("0.0000"))
        self.assertIn("ZERO_RATE_EXPLICITLY_CONFIRMED_APPLIED", f2.authority_limitations)

    def test_none_monetized_total_is_none_not_proven_zero(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s04_none")
        c = joint.s04.cost_conservation
        self.assertEqual(c.calculation_completeness, CostCompleteness.NONE_MONETIZED)
        self.assertIsNone(c.total_calculated_direct_labor_cost_exact)
        self.assertIsNone(c.total_calculated_direct_labor_cost_rounded)
        self.assertIn(
            "ZERO_RUB_IS_NOT_PROVEN_SHIFT_COST_WHEN_NONE_MONETIZED",
            " ".join(c.notes),
        )

    def test_category_scoped_rates_without_cross_worker_allocation(self) -> None:
        r_fit = LaborCostRateReference(
            rate_identity="fit_rate",
            rate_value="1000",
            currency="RUB",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.SCENARIO_RATE,
            economic_type=CostRateEconomicType.EMPLOYER_DIRECT_LABOR_COST_RATE,
            provenance="test",
            version="v1",
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
            applicable_labor_category="fitting_fab",
            valid_from="2020-01-01",
            valid_to="2099-12-31",
        )
        r_clad = LaborCostRateReference(
            rate_identity="clad_rate",
            rate_value="2000",
            currency="RUB",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.SCENARIO_RATE,
            economic_type=CostRateEconomicType.EMPLOYER_DIRECT_LABOR_COST_RATE,
            provenance="test",
            version="v1",
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
            applicable_labor_category="cladding",
            valid_from="2020-01-01",
            valid_to="2099-12-31",
        )
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    60,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=6.0,
                    physical_unit="шт",
                    work_kind_hint="fitting_fab",
                ),
                OperationLaborClaim(
                    "Монтаж AL CLAD AD",
                    60,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=1.0,
                    physical_unit="м2",
                    work_kind_hint="cladding",
                ),
            ),
        )
        joint = assess_shift(
            inp, audit_id="s04_multi_cat", cost_rates=(r_fit, r_clad)
        )
        fit = _by_name(joint.s04, "Изготовление фасонных изделий")
        clad = _by_name(joint.s04, "Монтаж AL CLAD AD")
        self.assertEqual(fit.applied_rate_identity, "fit_rate@v1")
        self.assertEqual(clad.applied_rate_identity, "clad_rate@v1")
        self.assertEqual(_d(fit.computed_direct_labor_cost_exact), Decimal("1000.0000"))
        self.assertEqual(_d(clad.computed_direct_labor_cost_exact), Decimal("2000.0000"))
        self.assertIn("NO_CROSS_WORKER_LABOR_ALLOCATION", fit.authority_limitations)
        self.assertIn(
            "NOT_A_FULL_MULTI_RATE_ALLOCATION_ENGINE",
            joint.s04.multi_rate_allocation_status,
        )

    def test_fully_burdened_not_pure_direct(self) -> None:
        rate = LaborCostRateReference(
            rate_identity="burdened",
            rate_value="1000",
            currency="RUB",
            rate_unit=CostRateUnit.PER_MAN_HOUR,
            rate_authority=CostRateAuthority.BUDGET_RATE,
            economic_type=CostRateEconomicType.FULLY_BURDENED_LABOR_COST_RATE,
            provenance="test",
            version="v1",
            included_cost_components=("direct_labor", "site_overhead"),
            applicable_project_scope="FIXTURE_INSULATION_DEMO",
            valid_from="2020-01-01",
            valid_to="2099-12-31",
        )
        f = _by_name(
            assess_shift(
                build_insulation_pipeline_fixture(),
                audit_id="s04_burden",
                cost_rates=(rate,),
            ).s04,
            "Изготовление фасонных изделий",
        )
        self.assertIn("FULLY_BURDENED_NE_PURE_DIRECT_LABOR_COST", f.authority_limitations)
        self.assertNotEqual(f.cost_rate_authority, f.cost_rate_economic_type)

    def test_rounding_residual_not_hidden(self) -> None:
        # 10 × 1 man-minute @ 1000 RUB/h → non-zero display residual possible
        base = build_insulation_pipeline_fixture()
        ops = tuple(
            OperationLaborClaim(
                "Подготовка поверхности",
                1,
                LaborUnit.MAN_MINUTE,
                source_record_ids=(f"row-{i}",),
            )
            for i in range(10)
        )
        inp = replace(base, operations=ops)
        joint = assess_shift(
            inp,
            audit_id="s04_resid",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        c = joint.s04.cost_conservation
        self.assertEqual(len(joint.s04.findings), 10)
        self.assertIsNotNone(c.total_vs_line_sum_residual_rounded)
        self.assertNotEqual(_d(c.total_vs_line_sum_residual_rounded), Decimal("0.00"))
        self.assertIn("ROUNDING_RESIDUAL_NOT_HIDDEN_OR_REDISTRIBUTED", " ".join(c.notes))
        self.assertIn("limited precision", joint.s04.monetary_rounding_policy.lower())


if __name__ == "__main__":
    unittest.main()
