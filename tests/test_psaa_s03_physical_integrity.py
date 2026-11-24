"""PSAA-05 / S03 — Physical Integrity tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from agents.production_shift_auditor.contracts import (
    LaborUnit,
    ManagerialAcceptanceStatus,
    OperationLaborClaim,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.professional_assessment import assess_shift
from agents.production_shift_auditor.s03_contracts import (
    BoqRelationshipStatus,
    ClaimedResultState,
    PhysicalCheckResult,
    PhysicalCheckType,
)
from agents.production_shift_auditor.s03_physical_integrity import evaluate_s03
from agents.production_shift_auditor.s10_contracts import ClassificationStatus
from agents.production_shift_auditor.s10_operation_classification import evaluate_s10


def _qty_findings(art, original: str):
    return [
        f
        for f in art.findings
        if f.original_operation_text == original
        and f.check_type
        in {
            PhysicalCheckType.QUANTITY_INTEGRITY,
            PhysicalCheckType.UNIT_INTEGRITY,
            PhysicalCheckType.COMPOSITE_LIMITATION,
            PhysicalCheckType.CONTEXT_SUFFICIENCY,
        }
    ]


class FittingFabricationTests(unittest.TestCase):
    def test_40_pcs_manufactured_not_installed_not_boq(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s03_fit")
        hits = _qty_findings(joint.s03, "Изготовление фасонных изделий")
        self.assertTrue(hits)
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE)
        self.assertEqual(hits[0].original_claimed_quantity, 40.0)
        self.assertEqual(hits[0].claimed_result_state, ClaimedResultState.MANUFACTURED)
        joined = " ".join(hits[0].supporting_evidence)
        self.assertIn("CLAIMED_MANUFACTURED_NE_PROVEN_FABRICATION", joined)
        self.assertIn("MANUFACTURED_NE_INSTALLED_NE_CONTRACT_ACCEPTED_NE_EARNED", joined)
        self.assertIn("CONSISTENT_APPLIES_ONLY_TO_THIS_CHECKED_RULE", joined)
        states = [
            f
            for f in joint.s03.findings
            if f.original_operation_text == "Изготовление фасонных изделий"
            and f.check_type == PhysicalCheckType.RESULT_STATE
        ]
        self.assertEqual(states[0].claimed_result_state, ClaimedResultState.MANUFACTURED)
        boq = [
            f
            for f in joint.s03.findings
            if f.original_operation_text == "Изготовление фасонных изделий"
            and f.check_type == PhysicalCheckType.BOQ_RELATIONSHIP
        ]
        self.assertEqual(boq[0].boq_relationship_status, BoqRelationshipStatus.NOT_CONTRACT_ACCEPTED)
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)


class QuantityValidationTests(unittest.TestCase):
    def test_negative_quantity(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=-1.0,
                    physical_unit="шт",
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        hits = _qty_findings(art, "Изготовление фасонных изделий")
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.INVALID_QUANTITY)
        self.assertIn("ordinary_execution_claim_scope", hits[0].supporting_evidence)
        self.assertIn("NOT_STORNO_OR_CORRECTION_WORKFLOW", hits[0].supporting_evidence)

    def test_missing_quantity_not_replaced_with_zero(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Монтаж прямых участков", 200, LaborUnit.MAN_MINUTE
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        hits = _qty_findings(art, "Монтаж прямых участков")
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.INSUFFICIENT_CONTEXT)
        self.assertIsNone(hits[0].original_claimed_quantity)
        self.assertIn("quantity_absent", hits[0].supporting_evidence)

    def test_zero_quantity_with_labor_not_auto_violation(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    400,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=0.0,
                    physical_unit="шт",
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        hits = _qty_findings(art, "Изготовление фасонных изделий")
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE)
        self.assertTrue(
            any("zero_quantity_with_positive_labor" in e for e in hits[0].supporting_evidence)
        )

    def test_prep_without_quantity(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim("Подготовка поверхности", 30, LaborUnit.MAN_MINUTE),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        hits = _qty_findings(art, "Подготовка поверхности")
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.NOT_APPLICABLE)
        self.assertEqual(
            hits[0].measurability.value, "QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE"
        )
        self.assertIn("quantity_not_required_by_current_rule", hits[0].supporting_evidence)
        self.assertIn("NOT_ONTOLOGICAL_NON_MEASURABILITY", hits[0].supporting_evidence)
        self.assertIn("LABOR_IS_NOT_PHYSICAL_VOLUME", hits[0].supporting_evidence)
        self.assertIn("будущ", hits[0].professional_explanation.lower())


class UnitValidationTests(unittest.TestCase):
    def test_incompatible_unit_for_cladding(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Монтаж AL CLAD AD",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=6.0,
                    physical_unit="шт",
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        hits = _qty_findings(art, "Монтаж AL CLAD AD")
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.INSUFFICIENT_CONTEXT)
        self.assertIn("NO_AUTOMATIC_UNIT_CONVERSION", hits[0].supporting_evidence)

    def test_unknown_unit(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=40.0,
                    physical_unit="коробка",
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        hits = _qty_findings(art, "Изготовление фасонных изделий")
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.INSUFFICIENT_CONTEXT)
        self.assertIn("unknown_unit_semantics", hits[0].supporting_evidence)

    def test_m_to_m2_without_geometry_forbidden(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Монтаж прямых участков",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=12.0,
                    physical_unit="м2",
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        hits = _qty_findings(art, "Монтаж прямых участков")
        self.assertEqual(hits[0].check_result, PhysicalCheckResult.INSUFFICIENT_CONTEXT)
        self.assertNotEqual(hits[0].check_result, PhysicalCheckResult.UNIT_INCOMPATIBILITY)
        self.assertIn("missing_geometry_ne_proven_unit_incompatibility", hits[0].supporting_evidence)
        self.assertIn("NO_AUTOMATIC_UNIT_CONVERSION", hits[0].supporting_evidence)


class ObjectAndDuplicateTests(unittest.TestCase):
    def test_missing_object_identity(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="obj")
        objs = [
            f
            for f in joint.s03.findings
            if f.original_operation_text == "Изготовление фасонных изделий"
            and f.check_type == PhysicalCheckType.OBJECT_IDENTITY
        ]
        self.assertEqual(objs[0].check_result, PhysicalCheckResult.INSUFFICIENT_CONTEXT)

    def test_same_qty_different_objects_not_duplicate(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=40.0,
                    physical_unit="шт",
                    physical_object_hint="LINE-A",
                    source_record_ids=("r1",),
                ),
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=40.0,
                    physical_unit="шт",
                    physical_object_hint="LINE-B",
                    source_record_ids=("r2",),
                ),
            ),
        )
        # Need distinct identities for S10 lines — use notes via unique names? Same name maps both.
        # Use evaluate with two same names — claim_for_line returns first match.
        # Better: different source ids and evaluate duplicates via source_record scan.
        art = evaluate_s03(inp, evaluate_s10(inp))
        dups = [f for f in art.findings if f.check_type == PhysicalCheckType.DUPLICATE_CLAIM]
        self.assertTrue(
            any(
                f.check_result == PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE
                and f.supporting_evidence
                and any("different_objects" in e for e in f.supporting_evidence)
                for f in dups
            )
            or any(
                "different_objects_not_duplicate" in " ".join(f.supporting_evidence) for f in dups
            )
        )

    def test_proven_record_duplicate(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=10.0,
                    physical_unit="шт",
                    source_record_ids=("REC-DUP",),
                ),
                OperationLaborClaim(
                    "Монтаж прямых участков",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=5.0,
                    physical_unit="м",
                    source_record_ids=("REC-DUP",),
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        dups = [
            f
            for f in art.findings
            if f.check_result == PhysicalCheckResult.PROVEN_RECORD_DUPLICATE
        ]
        self.assertTrue(dups)
        self.assertTrue(
            any("within_single_audit_input_only" in e for e in dups[0].supporting_evidence)
        )

    def test_possible_duplicate_not_proven(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=40.0,
                    physical_unit="шт",
                    physical_object_hint="LINE-A",
                    source_record_ids=("a",),
                ),
                OperationLaborClaim(
                    "Изготовление фасонных изделий",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_quantity=40.0,
                    physical_unit="шт",
                    physical_object_hint="LINE-A",
                    source_record_ids=("b",),
                ),
            ),
        )
        art = evaluate_s03(inp, evaluate_s10(inp))
        possibles = [
            f
            for f in art.findings
            if f.check_result == PhysicalCheckResult.POSSIBLE_DUPLICATE
        ]
        self.assertTrue(possibles)
        self.assertTrue(
            all("POSSIBLE_DUPLICATE_NE_PROVEN" in " ".join(f.supporting_evidence) for f in possibles)
        )


class CompositeAndIntegrationTests(unittest.TestCase):
    def test_composite_no_distribution(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="comp")
        comp = [
            f
            for f in joint.s03.findings
            if f.check_type == PhysicalCheckType.COMPOSITE_LIMITATION
        ]
        self.assertTrue(comp)
        self.assertEqual(comp[0].check_result, PhysicalCheckResult.INSUFFICIENT_CONTEXT)
        self.assertIn("NO_AUTOMATIC_QUANTITY_OR_TIME_DISTRIBUTION", comp[0].supporting_evidence)
        self.assertEqual(comp[0].claimed_labor_quantity, 75)

    def test_s02_demo_does_not_prove_physical_execution(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s02s03")
        self.assertTrue(
            any(
                "demonstration rules do NOT prove" in o
                or "industrial physical validity" in o
                for o in joint.s03.observations
            )
        )
        self.assertEqual(joint.s03.physical_inspection_status, "PHYSICAL_INSPECTION_NOT_PROVEN")

    def test_labor_preserved_and_no_acceptance(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="int")
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(
            joint.s01.managerial_acceptance_status, ManagerialAcceptanceStatus.NOT_IN_SCOPE
        )
        self.assertNotIn("ACCEPTED", joint.s03.human_readable_summary)
        self.assertNotIn("REJECTED", joint.s03.human_readable_summary)
        self.assertEqual(joint.s03.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertTrue(joint.s03.to_dict())
        self.assertEqual(joint.s03.s03_engine_status, "S03_ENGINE_IMPLEMENTED")
        self.assertEqual(
            joint.s03.production_physical_knowledge_status,
            "PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY",
        )
        # S10/S02 present
        self.assertTrue(joint.s10.classifications)
        self.assertTrue(joint.s02.findings)
        statuses = {c.classification_status for c in joint.s10.classifications}
        self.assertIn(ClassificationStatus.COMPOSITE_OPERATION, statuses)


class FixtureTableSmokeTests(unittest.TestCase):
    def test_fixture_smoke(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="fix_s03")
        clad = _qty_findings(joint.s03, "Монтаж AL CLAD AD")
        self.assertEqual(clad[0].check_result, PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE)
        self.assertEqual(clad[0].claimed_result_state, ClaimedResultState.INSTALLED)
        self.assertEqual(clad[0].original_claimed_quantity, 6.0)


if __name__ == "__main__":
    unittest.main()
