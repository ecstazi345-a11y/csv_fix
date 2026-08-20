"""
MPO-003A tests — deterministic orchestrator runtime (no live DB).

Run:
  C:\\csv_fix\\.venv\\Scripts\\python.exe -m unittest tests.test_monthly_planning_orchestrator_service -v
"""

from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from services.monthly_planning_orchestrator_service import (
    REC_ADMISSION_BLOCKED,
    REC_MIXED,
    REC_NOT_READY,
    REC_READY,
    REC_READY_WITH_WARNINGS,
    REC_RESOURCE_DEFICIT,
    STATE_FAILED,
    STATE_GATHER,
    STATE_HUMAN_DECISION,
    VAL_BLOCKED,
    VAL_PASS,
    VAL_PASS_WITH_WARNINGS,
    build_orchestrator_run,
    run_monthly_planning_orchestrator,
)


def _line(
    plan_line_id: str,
    *,
    required_hours: float = 40.0,
    requested_qty: float = 10.0,
    feasibility: str = "RESOURCE_READY",
    admission: str = "READY",
    missing_data: list[str] | None = None,
    remaining_qty: float | None = None,
    completed: bool | None = False,
) -> dict:
    return {
        "plan_line_id": plan_line_id,
        "boq_code": f"BOQ-{plan_line_id}",
        "crew_code": "CREW-1",
        "requested_qty": requested_qty,
        "remaining_qty": remaining_qty,
        "executed_qty": None if remaining_qty is None else 1.0,
        "completed": completed,
        "zero_price_physical": None,
        "admission_status": admission,
        "open_constraints": 0,
        "blocking_constraints": 1 if admission == "BLOCKED" else 0,
        "required_hours": required_hours,
        "crew_approved_available_hours": None if feasibility == "CAPACITY_DATA_MISSING" else 100.0,
        "resource_coverage": None if feasibility == "CAPACITY_DATA_MISSING" else 1.0,
        "resource_gap_hours": None if feasibility == "CAPACITY_DATA_MISSING" else 0.0,
        "theoretical_feasible_qty": None if feasibility == "CAPACITY_DATA_MISSING" else requested_qty,
        "feasibility_status": feasibility,
        "missing_data": list(missing_data or []),
        "source_refs": ["monthly_plan_labor_lines_v1"],
    }


def _snapshot(
    *,
    lines: list[dict],
    required: float | None = 80.0,
    approved: float | None = 100.0,
    coverage: float | None = 1.0,
    gap: float | None = 20.0,
    blocking: int = 0,
    missing_crew: int = 0,
    issues: list | None = None,
    scope_read_error: str | None = None,
    month_canonical: str | None = "2026-08",
    project: str = "PRJ_001",
    month_input: str = "август-2026",
) -> dict:
    for row in lines:
        if row.get("feasibility_status") in {"PARTIALLY_FEASIBLE", "RESOURCE_DEFICIT"}:
            cov = coverage if coverage is not None else 0.66
            row["resource_coverage"] = cov
            row["theoretical_feasible_qty"] = (row.get("requested_qty") or 0) * cov
    return {
        "run_scope": {
            "project_code": project,
            "month_key_input": month_input,
            "month_key_canonical": month_canonical,
            "filters": {},
        },
        "summary": {
            "plan_line_count": len(lines),
            "required_hours_total": required if lines else 0.0,
            "approved_available_hours_total": approved,
            "resource_coverage": coverage,
            "resource_gap_hours": gap,
            "blocking_line_count": blocking,
            "capacity_data_missing_crew_count": missing_crew,
        },
        "plan_lines": lines,
        "data_quality": {
            "issues": list(issues or []),
            "treat_as_planning_change": False,
        },
        "source_trace": {
            "no_llm": True,
            "mls_used_as_capacity": False,
            "scope_time_basis": "all_time",
            "manual_not_required_adjustments_applied": False,
            "scope_read_error": scope_read_error,
        },
    }


class OrchestratorRuntimeTests(unittest.TestCase):
    def test_1_healthy_run(self) -> None:
        snap = _snapshot(
            lines=[_line("L1"), _line("L2")],
            required=80.0,
            approved=100.0,
            coverage=1.0,
            gap=20.0,
        )
        run = build_orchestrator_run(
            snap,
            project_code="PRJ_001",
            month_key="август-2026",
            run_id="run-1",
            started_at="2026-08-19T00:00:00+00:00",
        )
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["validation"]["status"], VAL_PASS)
        self.assertEqual(run["human_decision"]["recommendation_code"], REC_READY)
        self.assertFalse(run["human_decision"]["writes_allowed"])
        self.assertIsNone(run["human_decision"]["decision_action"])
        self.assertTrue(run["human_decision"]["pending"])

    def test_2_resource_deficit(self) -> None:
        snap = _snapshot(
            lines=[
                _line("L1", required_hours=60.0, feasibility="PARTIALLY_FEASIBLE"),
                _line("L2", required_hours=60.0, feasibility="PARTIALLY_FEASIBLE"),
            ],
            required=120.0,
            approved=80.0,
            coverage=80.0 / 120.0,
            gap=-40.0,
        )
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["validation"]["status"], VAL_PASS_WITH_WARNINGS)
        self.assertEqual(run["human_decision"]["recommendation_code"], REC_RESOURCE_DEFICIT)
        self.assertNotEqual(run["validation"]["status"], VAL_BLOCKED)
        self.assertFalse(run["human_decision"]["writes_allowed"])

    def test_3_admission_blocked(self) -> None:
        snap = _snapshot(
            lines=[
                _line("L1", admission="BLOCKED"),
                _line("L2", admission="READY"),
            ],
            blocking=1,
            required=80.0,
            approved=100.0,
            coverage=1.0,
        )
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["validation"]["status"], VAL_PASS_WITH_WARNINGS)
        self.assertEqual(run["human_decision"]["recommendation_code"], REC_ADMISSION_BLOCKED)

    def test_4_mixed_admission_and_deficit(self) -> None:
        snap = _snapshot(
            lines=[
                _line("L1", admission="BLOCKED", feasibility="PARTIALLY_FEASIBLE"),
                _line("L2", admission="READY", feasibility="PARTIALLY_FEASIBLE"),
            ],
            blocking=1,
            required=120.0,
            approved=80.0,
            coverage=80.0 / 120.0,
            gap=-40.0,
        )
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["human_decision"]["recommendation_code"], REC_MIXED)
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["validation"]["status"], VAL_PASS_WITH_WARNINGS)

    def test_5_capacity_missing_not_zero(self) -> None:
        snap = _snapshot(
            lines=[
                _line("L1", feasibility="CAPACITY_DATA_MISSING", missing_data=["approved_capacity_missing"]),
                _line("L2", feasibility="CAPACITY_DATA_MISSING", missing_data=["approved_capacity_missing"]),
            ],
            required=80.0,
            approved=None,
            coverage=None,
            gap=None,
            missing_crew=1,
        )
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["validation"]["status"], VAL_BLOCKED)
        self.assertEqual(run["human_decision"]["recommendation_code"], REC_NOT_READY)
        self.assertIsNone(run["analysis"]["summary"]["approved_available_hours_total"])
        self.assertIsNone(run["analysis"]["summary"]["resource_gap_hours"])
        self.assertIsNone(run["analysis"]["summary"]["resource_coverage"])
        self.assertNotEqual(run["analysis"]["summary"]["resource_gap_hours"], -80.0)
        codes = {f["code"] for f in run["analysis"]["findings"]}
        self.assertIn("CAPACITY_DATA_MISSING", codes)
        self.assertNotIn("RESOURCE_DEFICIT", codes)
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)

    def test_6_boq_ambiguous(self) -> None:
        snap = _snapshot(
            lines=[
                _line(
                    "L1",
                    missing_data=["scope_remaining_not_joined", "zero_price_physical_not_joined"],
                ),
                _line("L2"),
            ],
            required=80.0,
            approved=100.0,
            coverage=1.0,
        )
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["validation"]["status"], VAL_PASS_WITH_WARNINGS)
        self.assertEqual(run["human_decision"]["recommendation_code"], REC_READY_WITH_WARNINGS)
        self.assertTrue(
            any(f["code"] == "scope_remaining_not_joined" for f in run["analysis"]["findings"])
        )

    def test_7_not_required_gap(self) -> None:
        snap = _snapshot(
            lines=[
                _line("L1", remaining_qty=4.0, missing_data=["not_required_adjustments_not_applied"]),
                _line("L2", remaining_qty=3.0, missing_data=["not_required_adjustments_not_applied"]),
            ],
            required=80.0,
            approved=100.0,
            coverage=1.0,
        )
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["validation"]["status"], VAL_PASS_WITH_WARNINGS)
        self.assertTrue(
            any(f["code"] == "not_required_adjustments_not_applied" for f in run["human_decision"]["warnings"])
        )

    def test_8_partial_source_failure(self) -> None:
        snap = _snapshot(
            lines=[_line("L1"), _line("L2")],
            required=80.0,
            approved=100.0,
            coverage=1.0,
            issues=[{"code": "scope_read_failed", "detail": "view down"}],
            scope_read_error="RuntimeError: view down",
        )
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["gather"]["sources"]["labor"], "OK")
        self.assertEqual(run["gather"]["sources"]["boq_reality"], "FAILED")
        self.assertEqual(run["validation"]["status"], VAL_PASS_WITH_WARNINGS)
        self.assertIsNone(run["error"])

    def test_9_fatal_gather_exception(self) -> None:
        with patch(
            "services.monthly_planning_orchestrator_service.load_planning_snapshot",
            side_effect=RuntimeError("db down"),
        ):
            run = run_monthly_planning_orchestrator("PRJ_001", "август-2026")
        self.assertEqual(run["state"], STATE_FAILED)
        self.assertIsNone(run["snapshot"])
        self.assertIsNone(run["analysis"])
        self.assertIsNone(run["validation"])
        self.assertIsNone(run["human_decision"])
        self.assertIsNotNone(run["error"])
        self.assertEqual(run["trace"][0]["stage"], STATE_GATHER)
        self.assertEqual(run["trace"][0]["status"], "ERROR")

    def test_10_zero_plan_lines(self) -> None:
        snap = _snapshot(lines=[], required=0.0, approved=0.0, coverage=None, gap=None)
        run = build_orchestrator_run(snap, project_code="PRJ_001", month_key="август-2026")
        self.assertEqual(run["state"], STATE_HUMAN_DECISION)
        self.assertEqual(run["validation"]["status"], VAL_BLOCKED)
        self.assertEqual(run["human_decision"]["recommendation_code"], REC_NOT_READY)

    def test_11_determinism(self) -> None:
        snap = _snapshot(lines=[_line("L1"), _line("L2")])
        kwargs = {
            "project_code": "PRJ_001",
            "month_key": "август-2026",
            "filters": {"crew_code": "CREW-1"},
            "run_id": "fixed-run",
            "started_at": "2026-08-19T12:00:00+00:00",
        }
        a = build_orchestrator_run(copy.deepcopy(snap), **kwargs)
        b = build_orchestrator_run(copy.deepcopy(snap), **kwargs)
        self.assertEqual(a["analysis"], b["analysis"])
        self.assertEqual(a["validation"], b["validation"])
        self.assertEqual(a["human_decision"], b["human_decision"])
        self.assertEqual(a["state"], b["state"])

    def test_12_no_writes_no_llm_imports(self) -> None:
        import services.monthly_planning_orchestrator_service as mod

        with open(mod.__file__, encoding="utf-8") as handle:
            src = handle.read()
        self.assertNotIn("import streamlit", src)
        self.assertNotIn("from streamlit", src)
        self.assertNotIn("from pages", src)
        self.assertNotIn("import pages", src)
        self.assertNotIn("ai_router", src)
        self.assertNotIn("openai", src.lower())
        self.assertNotIn("langgraph", src.lower())
        self.assertNotIn("crewai", src.lower())
        self.assertNotIn("upsert", src.lower())
        self.assertNotIn("create_passport", src)
        self.assertNotIn("apply_monthly_plan_management_decision", src)
        self.assertNotIn("from services.monthly_plan_labor_service", src)
        self.assertNotIn("from services.monthly_resource_plan_service", src)
        self.assertNotIn("from services.monthly_planning_boq_service", src)
        self.assertNotIn("from services.monthly_plan_resource_economic_service", src)
        self.assertNotIn("STATE_DONE", src)
        self.assertNotIn('"DONE"', src)


if __name__ == "__main__":
    unittest.main()
