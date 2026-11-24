"""PSAA S01 — Mathematical Integrity fixture + adapter + EOS-SEC registry tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from agents.production_shift_auditor.contracts import (
    DataCompletenessStatus,
    LaborUnit,
    ManagerialAcceptanceStatus,
    MathIntegrityStatus,
    OperationLaborClaim,
    ProfessionalCredibilityStatus,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.read_adapter import (
    ShiftGrainError,
    rows_to_shift_audit_input,
)
from agents.production_shift_auditor.runtime import audit_shift_from_input
from agents.production_shift_auditor.s01_mathematical_integrity import evaluate_s01
from security.agent_execution_context import (
    PSAA_ALLOWED_TOOLS,
    TOOL_LOAD_SHIFT_DAILY_PROGRESS,
    issue_read_only_agent_context,
)
from security.trusted_read_executor import ToolPermissionError, validate_context_for_tool

REPO = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO / "agents" / "production_shift_auditor"


class InsulationFixtureMathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inp = build_insulation_pipeline_fixture()
        self.art = evaluate_s01(self.inp, audit_id="audit_fixture_insulation")

    def test_target_fund(self) -> None:
        m = self.art.s01_metrics
        self.assertEqual(m.target_fund_man_minutes, 1440.0)
        self.assertEqual(m.target_fund_man_hours, 24.0)

    def test_claimed_totals(self) -> None:
        m = self.art.s01_metrics
        self.assertEqual(m.claimed_total_man_minutes, 1425.0)
        self.assertAlmostEqual(m.claimed_total_man_hours or 0.0, 23.75, places=6)

    def test_deviation_and_coverage(self) -> None:
        m = self.art.s01_metrics
        self.assertEqual(m.absolute_deviation_man_minutes, 15.0)
        self.assertAlmostEqual(m.fund_coverage_pct or 0.0, 98.9583, places=4)

    def test_multiples(self) -> None:
        m = self.art.s01_metrics
        self.assertEqual(m.operations_count, 11)
        self.assertEqual(m.multiples_of_5_minutes_count, 11)
        self.assertEqual(m.multiples_of_10_minutes_count, 10)

    def test_top3_concentration(self) -> None:
        m = self.art.s01_metrics
        self.assertEqual(m.top3_operations_man_minutes, 900.0)
        self.assertAlmostEqual(
            m.top3_concentration_of_target_fund_pct or 0.0, 62.5, places=6
        )
        self.assertIn("Изготовление фасонных изделий", m.top3_operation_names)
        self.assertIn("Проклейка теплоизоляционной лентой", m.top3_operation_names)
        self.assertTrue(
            "Монтаж AL CLAD AD" in m.top3_operation_names
            or "Монтаж прямых участков" in m.top3_operation_names
        )

    def test_unit_labor(self) -> None:
        by_name = {o.operation_name: o for o in self.art.operations}
        fit = by_name["Изготовление фасонных изделий"]
        self.assertEqual(fit.unit_labor_man_minutes_per_physical, 10.0)
        clad = by_name["Монтаж AL CLAD AD"]
        self.assertAlmostEqual(
            clad.unit_labor_man_hours_per_physical or 0.0, 200.0 / 60.0 / 6.0, places=4
        )
        self.assertAlmostEqual(
            clad.unit_labor_man_hours_per_physical or 0.0, 0.5556, places=4
        )

    def test_statuses_separated(self) -> None:
        self.assertEqual(self.art.math_integrity_status, MathIntegrityStatus.COHERENT)
        self.assertEqual(
            self.art.data_completeness_status, DataCompletenessStatus.COMPLETE_FOR_S01
        )
        self.assertEqual(
            self.art.professional_credibility_status,
            ProfessionalCredibilityStatus.NOT_EVALUATED,
        )
        self.assertEqual(
            self.art.managerial_acceptance_status,
            ManagerialAcceptanceStatus.NOT_IN_SCOPE,
        )
        blob = self.art.human_readable_conclusion
        self.assertNotIn("ACCEPTED", blob)
        self.assertNotIn("REJECTED", blob)

    def test_runtime_fixture_path(self) -> None:
        result = audit_shift_from_input(self.inp)
        self.assertEqual(result.live_data_proof, "NOT_APPLICABLE_FIXTURE_OR_PREBUILT_INPUT")
        self.assertEqual(result.artifact.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertIn("Целевой производительный фонд", result.artifact.human_readable_conclusion)


class OverfundDiagnosticTests(unittest.TestCase):
    def test_overfund_signed_deviation_and_observation(self) -> None:
        from dataclasses import replace

        from agents.production_shift_auditor.contracts import MathIntegrityStatus

        base = build_insulation_pipeline_fixture()
        ops = list(base.operations)
        ops[0] = replace(ops[0], claimed_labor_quantity=90.0)  # +60 → total 1485
        mutated = replace(base, operations=tuple(ops))
        art = evaluate_s01(mutated, audit_id="audit_overfund")
        m = art.s01_metrics
        self.assertEqual(m.target_fund_man_minutes, 1440.0)
        self.assertEqual(m.claimed_total_man_minutes, 1485.0)
        self.assertEqual(m.absolute_deviation_man_minutes, -45.0)  # signed
        self.assertAlmostEqual(m.fund_coverage_pct or 0.0, 103.125, places=4)
        self.assertEqual(art.math_integrity_status, MathIntegrityStatus.COHERENT)
        over_obs = [o for o in art.observations if "Превышение целевого производительного фонда" in o]
        self.assertTrue(over_obs, "expected explicit overfund diagnostic observation")
        self.assertIn("OVER_FUND", over_obs[0])
        self.assertIn("45", over_obs[0])
        self.assertIn("не доказательство нарушения", over_obs[0])
        self.assertIn("COHERENT означает арифметическую согласованность", over_obs[0])
        self.assertIn("≠ табельное", over_obs[0])
        self.assertIn("OVER_FUND", art.human_readable_conclusion)
        self.assertIn(
            "не означает отсутствие отклонений",
            art.human_readable_conclusion,
        )


class UnprovenHourSemanticsTests(unittest.TestCase):

    def test_hour_field_unproven_blocks_totals(self) -> None:
        from agents.production_shift_auditor.contracts import (
            INPUT_SCHEMA_VERSION,
            DataSourceKind,
            LaborSemanticsStatus,
            ShiftAuditInput,
        )

        inp = ShiftAuditInput(
            schema_version=INPUT_SCHEMA_VERSION,
            source_kind=DataSourceKind.DAILY_PROGRESS_ACTIVE,
            project_code="PRJ_X",
            work_date="2026-01-01",
            shift_type="DAY",
            crew_id="C1",
            crew_size=3,
            productive_hours_per_person=8.0,
            operations=(
                OperationLaborClaim("Op A", 5.0, LaborUnit.HOUR_FIELD_UNPROVEN),
                OperationLaborClaim("Op B", 3.0, LaborUnit.HOUR_FIELD_UNPROVEN),
            ),
            labor_semantics_status=LaborSemanticsStatus.PARTIALLY_PROVEN,
            labor_semantics_note="test",
        )
        art = evaluate_s01(inp)
        self.assertIsNone(art.s01_metrics.claimed_total_man_minutes)
        self.assertEqual(art.math_integrity_status, MathIntegrityStatus.DATA_INCOMPLETE)
        self.assertTrue(any("не конвертируется" in o for o in art.observations))


class ReadAdapterGrainTests(unittest.TestCase):
    def test_conflicting_crew_size(self) -> None:
        rows = [
            {
                "project_code": "P1",
                "crew_id": "C1",
                "work_date": "2026-01-01",
                "shift_type": "DAY",
                "crew_size": 3,
                "airtable_record_id": "recA",
                "operation_type": "A",
                "direct_work_hours": 1.0,
            },
            {
                "project_code": "P1",
                "crew_id": "C1",
                "work_date": "2026-01-01",
                "shift_type": "DAY",
                "crew_size": 4,
                "airtable_record_id": "recB",
                "operation_type": "B",
                "direct_work_hours": 2.0,
            },
        ]
        with self.assertRaises(ShiftGrainError) as ctx:
            rows_to_shift_audit_input(
                rows,
                project_code="P1",
                crew_id="C1",
                work_date="2026-01-01",
                shift_type="DAY",
            )
        self.assertEqual(ctx.exception.code, "CONFLICTING_CREW_SIZE")

    def test_maps_unproven_hours_and_keeps_ids(self) -> None:
        rows = [
            {
                "project_code": "P1",
                "crew_id": "C1",
                "work_date": "2026-01-01",
                "shift_type": "DAY",
                "crew_size": 3,
                "airtable_record_id": "recA",
                "operation_type": "Подготовка",
                "direct_work_hours": 1.5,
                "quantity_today": 10,
                "unit_of_measure": "м2",
            }
        ]
        inp = rows_to_shift_audit_input(
            rows,
            project_code="P1",
            crew_id="C1",
            work_date="2026-01-01",
            shift_type="DAY",
        )
        self.assertEqual(inp.crew_size, 3)
        self.assertEqual(inp.source_record_ids, ("recA",))
        self.assertEqual(inp.operations[0].labor_unit, LaborUnit.HOUR_FIELD_UNPROVEN)
        self.assertEqual(inp.operations[0].physical_quantity, 10.0)


class PsaaSecurityRegistryTests(unittest.TestCase):
    def test_context_issued_with_psaa_tools_only(self) -> None:
        ctx = issue_read_only_agent_context(
            agent_code="PRODUCTION_SHIFT_AUDITOR",
            project_code="PRJ_001_БХК",
        )
        self.assertEqual(ctx.allowed_tools, PSAA_ALLOWED_TOOLS)
        self.assertIs(ctx.write_allowed, False)
        validate_context_for_tool(ctx, TOOL_LOAD_SHIFT_DAILY_PROGRESS)
        with self.assertRaises(ToolPermissionError):
            validate_context_for_tool(ctx, "load_constructor_scope")

    def test_agent_layer_no_credentials(self) -> None:
        banned = (
            "SUPABASE_SECRET_KEY",
            "SUPABASE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "create_client",
            "from services.supabase_client",
        )
        for rel in (
            "contracts.py",
            "s01_mathematical_integrity.py",
            "tools.py",
            "runtime.py",
            "read_adapter.py",
        ):
            src = (AGENT_DIR / rel).read_text(encoding="utf-8")
            for name in banned:
                self.assertNotIn(name, src)
            self.assertNotIn("os.getenv", src)

    def test_manifest_matches_service_columns(self) -> None:
        from services.psaa_shift_read_service import SELECT_COLUMNS

        manifest = json.loads(
            (AGENT_DIR / "specification" / "security_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        fields = set(manifest["read_fields_by_source"]["daily_progress_active"])
        # is_deleted may be in manifest for policy; service selects fixed columns
        self.assertTrue(set(SELECT_COLUMNS).issubset(fields))
        self.assertEqual(manifest["write_access"], False)
        self.assertEqual(manifest["llm_enabled"], False)
        self.assertEqual(set(manifest["allowed_tools"]), set(PSAA_ALLOWED_TOOLS))

    def test_constructor_unchanged_by_psaa_imports(self) -> None:
        # PSAA must not import Constructor professional packages
        for rel in ("runtime.py", "tools.py", "read_adapter.py", "s01_mathematical_integrity.py"):
            src = (AGENT_DIR / rel).read_text(encoding="utf-8")
            self.assertNotIn("agents.monthly_plan_constructor", src)


class ExecutorSignatureTests(unittest.TestCase):
    def test_shift_read_has_no_project_arg(self) -> None:
        import inspect

        from security.trusted_read_executor import execute_shift_daily_progress_read

        sig = inspect.signature(execute_shift_daily_progress_read)
        self.assertNotIn("project_code", sig.parameters)


if __name__ == "__main__":
    unittest.main()
