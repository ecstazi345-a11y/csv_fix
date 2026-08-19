"""
MPO-002A unit tests — deterministic Planning Snapshot (no live writes).

Run:
  C:\\csv_fix\\.venv\\Scripts\\python.exe -m unittest tests.test_monthly_planning_snapshot_service -v
"""

from __future__ import annotations

import unittest

import pandas as pd

from services.monthly_plan_resource_economic_service import (
    CAPACITY_DATA_MISSING,
    PARTIALLY_FEASIBLE,
    build_resource_economic_models,
)
from services.monthly_planning_snapshot_service import build_planning_snapshot
from utils.month_key import normalize_month_key


def _line(
    plan_line_id: str,
    *,
    crew: str = "СУБпо-20",
    qty: float = 90.0,
    hours: float = 60.0,
    boq: str = "BOQ-A",
    project: str = "PRJ_001",
    month: str = "август-2026",
    labor_hours: float | None = None,
) -> dict:
    return {
        "plan_line_id": plan_line_id,
        "project_code": project,
        "month_key": month,
        "boq_code": boq,
        "boq_name": f"Name {boq}",
        "facility": "T1",
        "discipline": "ELEC",
        "crew": crew,
        "crew_code": crew,
        "crew_size": 2,
        "planned_qty": qty,
        "unit": "м3",
        "labor_hours": hours if labor_hours is None else labor_hours,
        "norm_hours_per_unit_effective": None,
        "labor_cost": 100.0,
        "plan_value": 1000.0,
        "unit_price": 10.0,
    }


def _approved_capacity(
    *,
    crew: str = "СУБпо-20",
    hours: float = 80.0,
    project: str = "PRJ_001",
    month: str = "2026-08",
    people: int = 2,
) -> dict:
    return {
        "project_code": project,
        "month_key": month,
        "crew_code": crew,
        "available_labor_hours": hours,
        "approved_available_hours": hours,
        "available_fte": hours / 176.0,
        "roster_row_count": people,
        "approved_people_count": people,
        "fte_gap": 0.0,
    }


class PlanningSnapshotCoreTests(unittest.TestCase):
    def test_case1_one_crew_two_lines_no_capacity_double_count(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L1", qty=90.0, hours=60.0, boq="BOQ-A"),
                _line("L2", qty=90.0, hours=60.0, boq="BOQ-B"),
            ]
        )
        capacity = pd.DataFrame([_approved_capacity(hours=80.0)])
        snap = build_planning_snapshot(
            project_code="PRJ_001",
            month_key="август-2026",
            labor_lines_df=lines,
            approved_capacity_df=capacity,
        )

        self.assertEqual(snap["summary"]["plan_line_count"], 2)
        self.assertEqual(len(snap["plan_lines"]), 2)
        self.assertAlmostEqual(snap["summary"]["approved_available_hours_total"], 80.0)
        self.assertNotEqual(snap["summary"]["approved_available_hours_total"], 160.0)
        self.assertAlmostEqual(snap["summary"]["required_hours_total"], 120.0)
        self.assertAlmostEqual(snap["summary"]["resource_coverage"], 80.0 / 120.0)
        self.assertEqual(snap["data_quality"]["treat_as_planning_change"], False)

        models = build_resource_economic_models(lines, capacity)
        expected_by_id = {
            str(row["plan_line_id"]): row["theoretical_feasible_qty"]
            for _, row in models["line_model"].iterrows()
        }
        for pl in snap["plan_lines"]:
            self.assertEqual(pl["feasibility_status"], PARTIALLY_FEASIBLE)
            self.assertAlmostEqual(pl["resource_coverage"], 80.0 / 120.0)
            self.assertAlmostEqual(pl["crew_approved_available_hours"], 80.0)
            self.assertAlmostEqual(
                pl["theoretical_feasible_qty"],
                float(expected_by_id[pl["plan_line_id"]]),
            )
            self.assertAlmostEqual(pl["theoretical_feasible_qty"], 90.0 * (80.0 / 120.0))

    def test_case2_same_boq_two_plan_lines_not_collapsed(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L-A", crew="СУБпо-20", boq="2041-02-06-01"),
                _line("L-B", crew="АСИ-10", boq="2041-02-06-01"),
            ]
        )
        capacity = pd.DataFrame(
            [
                _approved_capacity(crew="СУБпо-20", hours=80.0),
                _approved_capacity(crew="АСИ-10", hours=80.0),
            ]
        )
        snap = build_planning_snapshot(
            project_code="PRJ_001",
            month_key="август-2026",
            labor_lines_df=lines,
            approved_capacity_df=capacity,
        )
        ids = {row["plan_line_id"] for row in snap["plan_lines"]}
        self.assertEqual(ids, {"L-A", "L-B"})
        self.assertEqual(snap["summary"]["plan_line_count"], 2)
        for row in snap["plan_lines"]:
            self.assertEqual(row["boq_code"], "2041-02-06-01")
            self.assertIn("scope_remaining_not_joined", row["missing_data"])
            self.assertIsNone(row["remaining_qty"])
            self.assertIsNone(row["zero_price_physical"])

    def test_case3_missing_approved_capacity_is_not_zero(self) -> None:
        lines = pd.DataFrame([_line("L1"), _line("L2", boq="BOQ-B")])
        snap = build_planning_snapshot(
            project_code="PRJ_001",
            month_key="август-2026",
            labor_lines_df=lines,
            approved_capacity_df=pd.DataFrame(),
        )
        self.assertEqual(snap["summary"]["capacity_data_missing_crew_count"], 1)
        self.assertIsNone(snap["summary"]["resource_coverage"])
        self.assertIsNone(snap["summary"]["resource_gap_hours"])
        self.assertIsNone(snap["summary"]["approved_available_hours_total"])
        for row in snap["plan_lines"]:
            self.assertEqual(row["feasibility_status"], CAPACITY_DATA_MISSING)
            self.assertIsNone(row["resource_coverage"])
            self.assertIsNone(row["resource_gap_hours"])
            self.assertIsNone(row["theoretical_feasible_qty"])
            self.assertIsNone(row["crew_approved_available_hours"])
            self.assertIn("approved_capacity_missing", row["missing_data"])
        self.assertEqual(snap["data_quality"]["treat_as_planning_change"], False)

    def test_case4_roster_hours_ignored(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L1", hours=60.0),
                _line("L2", hours=60.0, boq="BOQ-B"),
            ]
        )
        capacity = pd.DataFrame([_approved_capacity(hours=80.0)])
        roster = pd.DataFrame(
            [
                {
                    "project_code": "PRJ_001",
                    "month_key": "August-2026",
                    "crew_code": "СУБпо-20",
                    "direct_hours_month": 9999.0,
                }
            ]
        )
        snap = build_planning_snapshot(
            project_code="PRJ_001",
            month_key="август-2026",
            labor_lines_df=lines,
            approved_capacity_df=capacity,
            roster_df=roster,
        )
        self.assertAlmostEqual(snap["summary"]["approved_available_hours_total"], 80.0)
        self.assertAlmostEqual(snap["summary"]["resource_coverage"], 80.0 / 120.0)
        self.assertFalse(snap["source_trace"]["mls_used_as_capacity"])
        self.assertTrue(snap["source_trace"]["no_llm"])

    def test_case5_crew_trailing_space_joins_without_fuzzy(self) -> None:
        lines = pd.DataFrame([_line("L1", crew="СУБпо-20 ", hours=60.0, qty=90.0)])
        capacity = pd.DataFrame([_approved_capacity(crew="СУБпо-20", hours=80.0)])
        snap = build_planning_snapshot(
            project_code="PRJ_001",
            month_key="август-2026",
            labor_lines_df=lines,
            approved_capacity_df=capacity,
        )
        row = snap["plan_lines"][0]
        self.assertEqual(row["crew_code"], "СУБпо-20")
        self.assertAlmostEqual(row["crew_approved_available_hours"], 80.0)
        self.assertNotEqual(row["feasibility_status"], CAPACITY_DATA_MISSING)
        self.assertTrue(
            any(i["code"] == "crew_untrimmed" for i in snap["data_quality"]["issues"])
        )

    def test_case6_month_canonical_uses_existing_normalizer(self) -> None:
        lines = pd.DataFrame([_line("L1", month="август-2026")])
        capacity = pd.DataFrame([_approved_capacity(month="2026-08")])
        snap = build_planning_snapshot(
            project_code="PRJ_001",
            month_key="август-2026",
            labor_lines_df=lines,
            approved_capacity_df=capacity,
        )
        self.assertEqual(normalize_month_key("август-2026"), "2026-08")
        self.assertEqual(snap["run_scope"]["month_key_input"], "август-2026")
        self.assertEqual(snap["run_scope"]["month_key_canonical"], "2026-08")
        self.assertAlmostEqual(snap["plan_lines"][0]["crew_approved_available_hours"], 80.0)

    def test_unique_boq_scope_join_when_single_plan_line(self) -> None:
        lines = pd.DataFrame([_line("L1", boq="9000-00-16-007")])
        capacity = pd.DataFrame([_approved_capacity()])
        scope = pd.DataFrame(
            [
                {
                    "boq_code": "9000-00-16-007",
                    "total_qty": 5.0,
                    "executed_qty": 1.0,
                    "unit_price": 0.0,
                    "total_value": 0.0,
                    "not_required_qty": 0.0,
                    "already_planned_qty": 0.0,
                }
            ]
        )
        snap = build_planning_snapshot(
            project_code="PRJ_001",
            month_key="август-2026",
            labor_lines_df=lines,
            approved_capacity_df=capacity,
            scope_df=scope,
        )
        row = snap["plan_lines"][0]
        self.assertAlmostEqual(row["remaining_qty"], 4.0)
        self.assertAlmostEqual(row["executed_qty"], 1.0)
        self.assertIs(row["completed"], False)
        self.assertIs(row["zero_price_physical"], True)
        self.assertNotIn("scope_remaining_not_joined", row["missing_data"])

    def test_no_llm_imports_in_service_module(self) -> None:
        import services.monthly_planning_snapshot_service as mod

        banned = ("openai", "anthropic", "yandex", "ai_router", "langchain", "langgraph")
        with open(mod.__file__, encoding="utf-8") as handle:
            src = handle.read().lower()
        for name in banned:
            self.assertNotIn(name, src)


if __name__ == "__main__":
    unittest.main()
