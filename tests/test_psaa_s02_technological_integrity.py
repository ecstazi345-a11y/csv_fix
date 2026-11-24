"""PSAA-04 / S02 — Technological Integrity tests."""

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
from agents.production_shift_auditor.s02_contracts import (
    PriorOperationEvidence,
    SourceAuthority,
    TechCheckResult,
    TechCheckType,
)
from agents.production_shift_auditor.s02_technological_integrity import evaluate_s02
from agents.production_shift_auditor.s10_contracts import ClassificationStatus
from agents.production_shift_auditor.s10_operation_classification import evaluate_s10


def _find(findings, *, original=None, rule_id=None, check_type=None):
    out = []
    for f in findings:
        if original is not None and f.original_operation_text != original:
            continue
        if rule_id is not None and f.applicable_rule_id != rule_id:
            continue
        if check_type is not None and f.check_type != check_type:
            continue
        out.append(f)
    return out


class ConsistentRuleTests(unittest.TestCase):
    def test_operation_matches_applicable_demo_rule(self) -> None:
        base = build_insulation_pipeline_fixture()
        joint = assess_shift(base, audit_id="s02_consistent")
        hits = _find(
            joint.s02.findings,
            original="Подготовка поверхности",
            rule_id="DEMO.INS.OP_APP.PIPING_INSULATION",
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].check_result, TechCheckResult.CONSISTENT_WITH_CHECKED_RULE)
        self.assertTrue(hits[0].demonstration_rule)
        self.assertEqual(hits[0].source_authority, SourceAuthority.DEMONSTRATION_RULE)


class ProvenContradictionTests(unittest.TestCase):
    def test_proven_material_contradiction_for_cladding(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Монтаж защитного покровного слоя",
                    10,
                    LaborUnit.MAN_MINUTE,
                    material_hint="минераловатные цилиндры ROCKWOOL без покрытия",
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(art.findings, rule_id="DEMO.INS.MAT.CLADDING_SYSTEM")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].check_result, TechCheckResult.PROVEN_CONTRADICTION)
        self.assertTrue(hits[0].demonstration_rule)


class PrerequisiteTests(unittest.TestCase):
    def test_missing_prerequisite_is_insufficient_not_violation(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim("Склеивание швов", 60, LaborUnit.MAN_MINUTE),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(art.findings, rule_id="DEMO.INS.PREREQ.SEAM_AFTER_BONDING_CONTEXT")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].check_result, TechCheckResult.INSUFFICIENT_CONTEXT)
        self.assertNotEqual(hits[0].check_result, TechCheckResult.PROVEN_CONTRADICTION)
        expl = hits[0].professional_explanation
        self.assertTrue(
            "PROVEN VIOLATION" in expl
            or "не доказательство" in expl.lower()
            or "НЕ доказательство" in expl
            or "физического объекта" in expl
        )

    def test_prerequisite_confirmed_in_prior_shift(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Склеивание швов",
                    60,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(
            inp,
            s10,
            prior_operation_evidence=(
                PriorOperationEvidence(
                    operation_code="INS.STRAIGHT_INSTALL",
                    work_date="2025-12-31",
                    physical_object_hint="PIPE-A",
                    crew_id="OTHER_CREW",
                ),
            ),
        )
        hits = _find(art.findings, rule_id="DEMO.INS.PREREQ.SEAM_AFTER_BONDING_CONTEXT")
        self.assertEqual(hits[0].check_result, TechCheckResult.CONSISTENT_WITH_CHECKED_RULE)
        self.assertTrue(any("prior:" in e for e in hits[0].supporting_evidence))
        self.assertTrue(any("shared_physical_object=PIPE-A" in e for e in hits[0].supporting_evidence))

    def test_same_shift_prereq_different_objects_is_insufficient(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Подготовка клея",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-B",
                ),
                OperationLaborClaim(
                    "Монтаж прямых участков",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-B",
                ),
                OperationLaborClaim(
                    "Склеивание швов",
                    60,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(
            art.findings,
            original="Склеивание швов",
            rule_id="DEMO.INS.PREREQ.SEAM_AFTER_BONDING_CONTEXT",
        )
        self.assertEqual(hits[0].check_result, TechCheckResult.INSUFFICIENT_CONTEXT)
        self.assertTrue(
            any("other_object_or_unlinked_prereq_in_shift" in e for e in hits[0].supporting_evidence)
        )

    def test_same_object_prereq_in_shift_is_consistent(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Подготовка клея",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                ),
                OperationLaborClaim(
                    "Склеивание швов",
                    60,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(
            art.findings,
            original="Склеивание швов",
            rule_id="DEMO.INS.PREREQ.SEAM_AFTER_BONDING_CONTEXT",
        )
        self.assertEqual(hits[0].check_result, TechCheckResult.CONSISTENT_WITH_CHECKED_RULE)
        self.assertIn("current_shift_prereq_same_object:INS.ADHESIVE_PREP", hits[0].supporting_evidence)


class CrossObjectAndChronologyTests(unittest.TestCase):
    def test_different_physical_objects_not_mixed_in_sequence(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Подготовка поверхности",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                    notes=("execution_event_time=2026-01-01T09:00:00",),
                ),
                OperationLaborClaim(
                    "Монтаж прямых участков",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-B",
                    notes=("execution_event_time=2026-01-01T08:00:00",),
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(
            art.findings,
            original="Монтаж прямых участков",
            rule_id="DEMO.INS.SEQ.SURFACE_BEFORE_STRAIGHT_SAME_OBJECT",
        )
        self.assertEqual(len(hits), 1)
        # Different objects → no same-object before op → INSUFFICIENT, not contradiction
        self.assertEqual(hits[0].check_result, TechCheckResult.INSUFFICIENT_CONTEXT)
        self.assertNotEqual(hits[0].check_result, TechCheckResult.PROVEN_CONTRADICTION)

    def test_row_order_not_used_as_chronology(self) -> None:
        base = build_insulation_pipeline_fixture()
        # Surface listed AFTER install in rows, but timestamps say surface was earlier
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Монтаж прямых участков",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                    notes=("execution_event_time=2026-01-01T11:00:00",),
                ),
                OperationLaborClaim(
                    "Подготовка поверхности",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                    notes=("execution_event_time=2026-01-01T10:00:00",),
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(
            art.findings,
            original="Монтаж прямых участков",
            rule_id="DEMO.INS.SEQ.SURFACE_BEFORE_STRAIGHT_SAME_OBJECT",
        )
        self.assertEqual(hits[0].check_result, TechCheckResult.CONSISTENT_WITH_CHECKED_RULE)
        self.assertTrue(
            any("row order" in o.lower() or "chronology" in o.lower() for o in art.observations)
        )
        # Evidence uses timestamps, not row indices
        self.assertTrue(any("T10:" in e or "10:00" in e for e in hits[0].supporting_evidence))

    def test_proven_sequence_contradiction_with_timestamps(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Подготовка поверхности",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                    notes=("execution_event_time=2026-01-01T12:00:00",),
                ),
                OperationLaborClaim(
                    "Монтаж прямых участков",
                    10,
                    LaborUnit.MAN_MINUTE,
                    physical_object_hint="PIPE-A",
                    notes=("execution_event_time=2026-01-01T10:00:00",),
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(
            art.findings,
            original="Монтаж прямых участков",
            rule_id="DEMO.INS.SEQ.SURFACE_BEFORE_STRAIGHT_SAME_OBJECT",
        )
        self.assertEqual(hits[0].check_result, TechCheckResult.PROVEN_CONTRADICTION)


class MaterialRuleTests(unittest.TestCase):
    def test_rule_not_applicable_to_material(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Раскрой теплоизоляционного материала",
                    10,
                    LaborUnit.MAN_MINUTE,
                    material_hint="минераловатные маты ROCKWOOL",
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(art.findings, rule_id="DEMO.INS.MAT.CUTTING_ELASTOMER")
        self.assertEqual(hits[0].check_result, TechCheckResult.NOT_APPLICABLE)

    def test_material_unknown(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Раскрой теплоизоляционного материала",
                    10,
                    LaborUnit.MAN_MINUTE,
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        hits = _find(art.findings, rule_id="DEMO.INS.MAT.CUTTING_ELASTOMER")
        self.assertEqual(hits[0].check_result, TechCheckResult.INSUFFICIENT_CONTEXT)


class S10StatusGateTests(unittest.TestCase):
    def test_composite_limits_tech_check(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(base).classifications
        composite = next(
            c for c in line if c.classification_status == ClassificationStatus.COMPOSITE_OPERATION
        )
        art = evaluate_s02(base, evaluate_s10(base))
        hits = _find(
            art.findings,
            original=composite.original_operation_text,
            check_type=TechCheckType.COMPOSITE_LIMITATION,
        )
        self.assertEqual(hits[0].check_result, TechCheckResult.INSUFFICIENT_CONTEXT)
        self.assertIn("NO_AUTOMATIC_TIME_DISTRIBUTION", hits[0].supporting_evidence)

    def test_unknown_operation_not_evaluated(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "Сварка металлоконструкций каркаса", 5, LaborUnit.MAN_MINUTE
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        art = evaluate_s02(inp, s10)
        self.assertEqual(art.findings[0].check_result, TechCheckResult.NOT_EVALUATED)

    def test_insufficient_classification_context(self) -> None:
        base = build_insulation_pipeline_fixture()
        inp = replace(
            base,
            operations=(
                OperationLaborClaim(
                    "6.1. Монтаж теплоизоляции трубопроводов (Thermal_Insulation_Piping)",
                    1,
                    LaborUnit.MAN_MINUTE,
                ),
            ),
        )
        s10 = evaluate_s10(inp)
        self.assertEqual(
            s10.classifications[0].classification_status,
            ClassificationStatus.INSUFFICIENT_CONTEXT,
        )
        art = evaluate_s02(inp, s10)
        self.assertEqual(art.findings[0].check_result, TechCheckResult.INSUFFICIENT_CONTEXT)


class SourceAndIntegrityTests(unittest.TestCase):
    def test_missing_tech_source(self) -> None:
        base = build_insulation_pipeline_fixture()
        s10 = evaluate_s10(base)
        art = evaluate_s02(base, s10, tech_rules_available=False)
        self.assertTrue(art.findings)
        self.assertTrue(
            all(f.check_result == TechCheckResult.INSUFFICIENT_CONTEXT for f in art.findings)
        )
        self.assertTrue(
            all(f.check_type == TechCheckType.CONTEXT_SUFFICIENCY for f in art.findings)
        )

    def test_demo_rule_not_presented_as_production(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="demo_flag")
        demo_findings = [f for f in joint.s02.findings if f.applicable_rule_id]
        self.assertTrue(demo_findings)
        self.assertTrue(all(f.demonstration_rule for f in demo_findings))
        self.assertTrue(
            all(f.source_authority == SourceAuthority.DEMONSTRATION_RULE for f in demo_findings)
        )
        obs = " ".join(joint.s02.observations)
        self.assertIn("DEMONSTRATION", obs)
        self.assertIn("NOT a basis for shift rejection", obs)
        self.assertNotIn("ACCEPTED", joint.s02.human_readable_summary)
        self.assertNotIn("REJECTED", joint.s02.human_readable_summary)
        self.assertEqual(joint.s02.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(joint.s02.s02_engine_status, "S02_ENGINE_IMPLEMENTED")
        self.assertEqual(joint.s02.demonstration_rules_status, "DEMONSTRATION_RULES_PROVEN")
        self.assertEqual(
            joint.s02.production_knowledge_status, "PRODUCTION_KNOWLEDGE_NOT_READY"
        )
        self.assertEqual(
            joint.s02.production_validation_status, "PRODUCTION_VALIDATION_NOT_PROVEN"
        )
        payload = joint.s02.to_dict()
        self.assertEqual(payload["production_knowledge_status"], "PRODUCTION_KNOWLEDGE_NOT_READY")
        self.assertEqual(
            payload["production_validation_status"], "PRODUCTION_VALIDATION_NOT_PROVEN"
        )

    def test_labor_and_volumes_unchanged(self) -> None:
        base = build_insulation_pipeline_fixture()
        joint = assess_shift(base, audit_id="integrity")
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(
            joint.s01.managerial_acceptance_status,
            ManagerialAcceptanceStatus.NOT_IN_SCOPE,
        )
        for op in base.operations:
            matches = [
                f for f in joint.s02.findings if f.original_operation_text == op.operation_name
            ]
            self.assertTrue(matches, msg=op.operation_name)
            self.assertEqual(matches[0].claimed_labor_quantity, op.claimed_labor_quantity)
            self.assertEqual(matches[0].physical_quantity, op.physical_quantity)
            self.assertEqual(matches[0].original_operation_text, op.operation_name)

    def test_s01_s10_not_regressed_in_joint(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="joint_reg")
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        statuses = {c.classification_status for c in joint.s10.classifications}
        self.assertIn(ClassificationStatus.EXACT_MATCH, statuses)
        self.assertIn(ClassificationStatus.COMPOSITE_OPERATION, statuses)
        self.assertIsNotNone(joint.s02)
        self.assertTrue(joint.s02.to_dict())


class FixtureShiftAssessmentTests(unittest.TestCase):
    def test_fixture_human_table_smoke(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="fixture_s02")
        self.assertGreaterEqual(len(joint.s02.findings), 11)
        # Composite present
        self.assertTrue(
            any(f.check_type == TechCheckType.COMPOSITE_LIMITATION for f in joint.s02.findings)
        )
        # Fixture has adhesive+install in shift but NO shared physical_object_hint
        seam = _find(
            joint.s02.findings,
            original="Склеивание швов",
            rule_id="DEMO.INS.PREREQ.SEAM_AFTER_BONDING_CONTEXT",
        )
        self.assertEqual(seam[0].check_result, TechCheckResult.INSUFFICIENT_CONTEXT)
        self.assertTrue(
            any(
                "without_object" in e or "physical_object" in e
                for e in seam[0].missing_evidence + seam[0].supporting_evidence
            )
        )
        self.assertEqual(joint.s02.production_knowledge_status, "PRODUCTION_KNOWLEDGE_NOT_READY")
        self.assertEqual(
            joint.s02.production_validation_status, "PRODUCTION_VALIDATION_NOT_PROVEN"
        )


if __name__ == "__main__":
    unittest.main()
