"""PSAA-03 / S10 — Operation Classification & Normalization tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from agents.production_shift_auditor.contracts import (
    LaborUnit,
    ManagerialAcceptanceStatus,
    OperationLaborClaim,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.history_store import InMemoryShiftAuditHistoryStore
from agents.production_shift_auditor.professional_assessment import assess_shift
from agents.production_shift_auditor.s01_mathematical_integrity import evaluate_s01
from agents.production_shift_auditor.s10_contracts import ClassificationStatus
from agents.production_shift_auditor.s10_operation_classification import (
    evaluate_s10,
    normalize_operation_text,
)
from agents.production_shift_auditor.tools import persist_shift_audit_history
from security.agent_execution_context import issue_read_only_agent_context


class NormalizationAliasTests(unittest.TestCase):
    def test_same_canonical_for_cutting_aliases(self) -> None:
        base = build_insulation_pipeline_fixture()
        variants = (
            "Резали каучук",
            "Раскрой K-FLEX",
            "Нарезка теплоизоляции",
            "раскрой каучука",
        )
        codes = []
        for text in variants:
            inp = replace(
                base,
                operations=(
                    OperationLaborClaim(
                        text, 10, LaborUnit.MAN_MINUTE, material_hint="каучук"
                    ),
                ),
            )
            art = evaluate_s10(inp, audit_id=f"cut_{normalize_operation_text(text)[:12]}")
            line = art.classifications[0]
            self.assertIn(
                line.classification_status,
                {
                    ClassificationStatus.EXACT_MATCH,
                    ClassificationStatus.NORMALIZED_MATCH,
                },
                msg=text,
            )
            self.assertEqual(line.operation_code_candidate, "INS.CUTTING")
            self.assertEqual(
                line.canonical_operation_candidate,
                "Раскрой теплоизоляционного материала",
            )
            self.assertEqual(line.original_operation_text, text)
            codes.append(line.operation_code_candidate)
        self.assertEqual(set(codes), {"INS.CUTTING"})

    def test_different_ops_not_merged(self) -> None:
        base = build_insulation_pipeline_fixture()
        a = evaluate_s10(
            replace(
                base,
                operations=(OperationLaborClaim("Подготовка поверхности", 1, LaborUnit.MAN_MINUTE),),
            )
        ).classifications[0]
        b = evaluate_s10(
            replace(
                base,
                operations=(
                    OperationLaborClaim("Изготовление фасонных изделий", 1, LaborUnit.MAN_MINUTE),
                ),
            )
        ).classifications[0]
        self.assertEqual(a.operation_code_candidate, "INS.SURFACE_PREP")
        self.assertEqual(b.operation_code_candidate, "INS.FITTING_FABRICATION")
        self.assertNotEqual(a.operation_code_candidate, b.operation_code_candidate)


class StatusPathTests(unittest.TestCase):
    def test_unknown(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(
                    OperationLaborClaim(
                        "Сварка металлоконструкций каркаса", 5, LaborUnit.MAN_MINUTE
                    ),
                ),
            )
        ).classifications[0]
        self.assertEqual(line.classification_status, ClassificationStatus.UNKNOWN_OPERATION)
        self.assertIsNone(line.operation_code_candidate)

    def test_ambiguous(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(OperationLaborClaim("Монтаж изоляции", 5, LaborUnit.MAN_MINUTE),),
            )
        ).classifications[0]
        self.assertEqual(line.classification_status, ClassificationStatus.AMBIGUOUS)
        self.assertGreaterEqual(len(line.candidates), 2)
        self.assertIsNone(line.operation_code_candidate)

    def test_composite_no_labor_split(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(
                    OperationLaborClaim(
                        "Раскрой каучука и монтаж прямых участков",
                        120,
                        LaborUnit.MAN_MINUTE,
                    ),
                ),
            )
        ).classifications[0]
        self.assertEqual(
            line.classification_status, ClassificationStatus.COMPOSITE_OPERATION
        )
        self.assertEqual(line.claimed_labor_quantity, 120)
        self.assertIn("NO_AUTOMATIC_TIME_DISTRIBUTION", line.matching_evidence)
        self.assertGreaterEqual(len(line.candidates), 2)

    def test_material_context_supports_cutting(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(
                    OperationLaborClaim(
                        "Резали каучук",
                        15,
                        LaborUnit.MAN_MINUTE,
                        material_hint="каучук K-FLEX",
                    ),
                ),
            )
        ).classifications[0]
        self.assertEqual(line.operation_code_candidate, "INS.CUTTING")
        self.assertEqual(line.original_operation_text, "Резали каучук")


class FixtureShiftClassificationTests(unittest.TestCase):
    def test_fixture_shift_table(self) -> None:
        art = evaluate_s10(build_insulation_pipeline_fixture(), audit_id="s10_fixture")
        by_orig = {c.original_operation_text: c for c in art.classifications}
        expected_codes = {
            "Подготовка поверхности": "INS.SURFACE_PREP",
            "Замеры и разметка": "INS.MARKING",
            "Подготовка клея": "INS.ADHESIVE_PREP",
            "Монтаж прямых участков": "INS.STRAIGHT_INSTALL",
            "Фиксация малярным скотчем": "INS.AUX_TAPE_FIX",
            "Склеивание швов": "INS.SEAM_BONDING",
            "Изготовление фасонных изделий": "INS.FITTING_FABRICATION",
            "Монтаж AL CLAD AD": "INS.CLADDING",
            "Проклейка теплоизоляционной лентой": "INS.TAPE",
            "Уборка рабочего места": "INS.AUX_CLEANUP",
        }
        for orig, code in expected_codes.items():
            line = by_orig[orig]
            self.assertEqual(line.operation_code_candidate, code, msg=orig)
            self.assertIn(
                line.classification_status,
                {
                    ClassificationStatus.EXACT_MATCH,
                    ClassificationStatus.NORMALIZED_MATCH,
                },
                msg=orig,
            )
        # Composite: cutting joined with deformation removal — not EXACT cutting
        composite = by_orig["Раскрой и устранение деформаций"]
        self.assertEqual(
            composite.classification_status, ClassificationStatus.COMPOSITE_OPERATION
        )
        self.assertIsNone(composite.operation_code_candidate)
        self.assertEqual(composite.claimed_labor_quantity, 75)
        # labor/volume untouched on matched lines
        fit = by_orig["Изготовление фасонных изделий"]
        self.assertEqual(fit.physical_quantity, 40.0)
        self.assertEqual(fit.claimed_labor_quantity, 400)
        glue = by_orig["Подготовка клея"]
        self.assertEqual(glue.canonical_operation_candidate, "Подготовка клеевого состава")
        mark = by_orig["Замеры и разметка"]
        self.assertEqual(mark.canonical_operation_candidate, "Замеры и разметка")

        self.assertEqual(art.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(art.registry_approval_status, "NOT_APPROVED_BY_AGENT")
        self.assertNotIn("ACCEPTED", art.human_readable_summary)
        self.assertNotIn("REJECTED", art.human_readable_summary)


class IntegrityAndHistoryTests(unittest.TestCase):
    def test_s10_does_not_change_labor_or_acceptance(self) -> None:
        base = build_insulation_pipeline_fixture()
        joint = assess_shift(base, audit_id="joint_1")
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(
            joint.s01.managerial_acceptance_status,
            ManagerialAcceptanceStatus.NOT_IN_SCOPE,
        )
        for line, op in zip(joint.s10.classifications, base.operations):
            self.assertEqual(line.original_operation_text, op.operation_name)
            self.assertEqual(line.claimed_labor_quantity, op.claimed_labor_quantity)
            self.assertEqual(line.physical_quantity, op.physical_quantity)

    def test_s01_history_still_readable_after_s10(self) -> None:
        store = InMemoryShiftAuditHistoryStore()
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="FIXTURE_INSULATION_DEMO",
        )
        base = build_insulation_pipeline_fixture()
        s01 = evaluate_s01(base, audit_id="hist_s01_only")
        persist_shift_audit_history(ctx, audit_input=base, artifact=s01, store=store)
        # S10 runs separately and must not rewrite history payload
        evaluate_s10(base, audit_id="hist_s01_only")
        loaded = store.get_by_audit_id(
            "hist_s01_only", project_code="FIXTURE_INSULATION_DEMO"
        )
        assert loaded is not None
        self.assertEqual(
            loaded.artifact_snapshot["s01_metrics"]["claimed_total_man_minutes"],
            1425.0,
        )
        self.assertNotIn("classifications", loaded.artifact_snapshot)


class EmptyTextTests(unittest.TestCase):
    def test_insufficient_context(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(OperationLaborClaim("   ", 1, LaborUnit.MAN_MINUTE),),
            )
        ).classifications[0]
        self.assertEqual(
            line.classification_status, ClassificationStatus.INSUFFICIENT_CONTEXT
        )

    def test_general_work_type_not_forced_to_specific_op(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(
                    OperationLaborClaim(
                        "6.1. Монтаж теплоизоляции трубопроводов (Thermal_Insulation_Piping)",
                        1,
                        LaborUnit.MAN_MINUTE,
                    ),
                ),
            )
        ).classifications[0]
        self.assertEqual(
            line.classification_status, ClassificationStatus.INSUFFICIENT_CONTEXT
        )
        self.assertIsNone(line.operation_code_candidate)
        self.assertIn("general_work_type_or_enum_label", line.matching_evidence)


class SemanticGranularityTests(unittest.TestCase):
    def test_alias_hit_is_normalized_not_automatic_equivalence(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(
                    OperationLaborClaim("Монтаж прямых участков", 1, LaborUnit.MAN_MINUTE),
                ),
            )
        ).classifications[0]
        self.assertEqual(line.classification_status, ClassificationStatus.NORMALIZED_MATCH)
        self.assertEqual(line.operation_code_candidate, "INS.STRAIGHT_INSTALL")

    def test_cutting_with_deformation_is_composite(self) -> None:
        base = build_insulation_pipeline_fixture()
        line = evaluate_s10(
            replace(
                base,
                operations=(
                    OperationLaborClaim(
                        "Раскрой и устранение деформаций", 75, LaborUnit.MAN_MINUTE
                    ),
                ),
            )
        ).classifications[0]
        self.assertEqual(line.classification_status, ClassificationStatus.COMPOSITE_OPERATION)
        self.assertEqual(line.claimed_labor_quantity, 75)
        self.assertTrue(any("раскро" in (c.canonical_name or "").lower() or
                            (c.operation_code or "").endswith("CUTTING")
                            for c in line.candidates) or
                        any("CUTTING" in (c.operation_code or "") for c in line.candidates))



if __name__ == "__main__":
    unittest.main()
