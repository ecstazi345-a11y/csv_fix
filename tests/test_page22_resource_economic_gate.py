"""
Unit tests for Page 22 Resource + Economic Gate helpers (R1).

Run:
  python -m unittest tests.test_page22_resource_economic_gate -v
"""

from __future__ import annotations

import unittest

import pandas as pd

from services.monthly_plan_resource_economic_service import (
    CAPACITY_DATA_MISSING,
    COMBINED_BOTH_RISK,
    COMBINED_ECONOMIC_RISK,
    COMBINED_PRICE_UNDEFINED,
    COMBINED_READY,
    COMBINED_RESOURCE_RISK,
    ECONOMIC_DEFICIT,
    ECONOMIC_OK,
    ITR_DRIVER_REQUIRED_HOURS,
    ITR_POOL_STATUS_PROPOSED,
    NOT_CALCULATED,
    PARTIALLY_FEASIBLE,
    PRICE_NOT_DEFINED,
    RESOURCE_DEFICIT,
    RESOURCE_READY,
    build_crew_decision_economics,
    build_decision_economics_from_models,
    build_resource_economic_crew_model,
    build_resource_economic_line_model,
    build_resource_economic_models,
    build_resource_economic_summary,
    classify_economic_status,
    classify_itr_absorption_management_message,
    count_crews_missing_capacity,
    project_required_direct_hours,
    summarize_proposed_itr_pool,
)


def _line(
    plan_line_id: str,
    crew: str,
    qty: float,
    hours: float,
    plan_value: float = 1000.0,
    labor_cost: float = 500.0,
    project: str = "P1",
    month: str = "2026-08",
    boq: str = "BOQ-1",
) -> dict:
    return {
        "plan_line_id": plan_line_id,
        "project_code": project,
        "month_key": month,
        "boq_code": boq,
        "boq_name": f"Name {boq}",
        "facility": "T1",
        "discipline": "ELEC",
        "crew_code": crew,
        "crew_size": 2,
        "planned_qty": qty,
        "unit": "ед",
        "labor_hours": hours,
        "norm_hours_per_unit_effective": hours / qty if qty else None,
        "labor_cost": labor_cost,
        "plan_value": plan_value,
        "unit_price": plan_value / qty if qty else 0,
    }


def _capacity(
    crew: str,
    available: float,
    project: str = "P1",
    month: str = "2026-08",
    roster_row_count: int = 2,
) -> dict:
    return {
        "project_code": project,
        "month_key": month,
        "crew_code": crew,
        "available_labor_hours": available,
        "available_fte": available / 176.0,
        "fte_gap": 0,
        "roster_row_count": roster_row_count,
        "plan_labor_hours": 0,
    }


class ResourceEconomicGateTests(unittest.TestCase):
    def test_t1_single_crew_partial_coverage(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 568, 700)])
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertAlmostEqual(float(crew.iloc[0]["coverage"]), 330 / 700, places=4)
        self.assertAlmostEqual(float(crew.iloc[0]["coverage_pct"]), 330 / 700 * 100, places=2)
        self.assertEqual(crew.iloc[0]["resource_status"], PARTIALLY_FEASIBLE)

        line_model = build_resource_economic_line_model(lines, crew)
        feasible = float(line_model.iloc[0]["theoretical_feasible_qty"])
        self.assertAlmostEqual(feasible, 568 * (330 / 700), places=2)

    def test_t2_coverage_capped_at_requested(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 100, 200)])
        capacity = pd.DataFrame([_capacity("E-01", 500)])
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertEqual(crew.iloc[0]["resource_status"], RESOURCE_READY)
        self.assertAlmostEqual(float(crew.iloc[0]["coverage"]), 1.0, places=4)

        line_model = build_resource_economic_line_model(lines, crew)
        self.assertAlmostEqual(float(line_model.iloc[0]["theoretical_feasible_qty"]), 100.0)

    def test_t3_multiple_boq_same_crew_no_double_count(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L1", "E-01", 100, 200, boq="A"),
                _line("L2", "E-01", 200, 300, boq="B"),
                _line("L3", "E-01", 150, 200, boq="C"),
            ]
        )
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        models = build_resource_economic_models(lines, capacity)
        summary = models["summary"]
        self.assertAlmostEqual(summary["available_labor_hours"], 330.0)
        self.assertAlmostEqual(summary["required_labor_hours"], 700.0)

        crew = models["crew_model"]
        self.assertEqual(len(crew), 1)
        self.assertAlmostEqual(float(crew.iloc[0]["crew_required_hours"]), 700.0)

    def test_t4_two_crews_independent(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L1", "E-01", 100, 400),
                _line("L2", "E-02", 100, 200),
            ]
        )
        capacity = pd.DataFrame(
            [
                _capacity("E-01", 200),
                _capacity("E-02", 400),
            ]
        )
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertEqual(len(crew), 2)
        by_crew = {row["crew_code"]: row for _, row in crew.iterrows()}
        self.assertEqual(by_crew["E-01"]["resource_status"], PARTIALLY_FEASIBLE)
        self.assertEqual(by_crew["E-02"]["resource_status"], RESOURCE_READY)

        summary = build_resource_economic_summary(crew, build_resource_economic_line_model(lines, crew))
        self.assertAlmostEqual(summary["available_labor_hours"], 600.0)

    def test_t5_missing_capacity_row(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-99", 100, 200)])
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertEqual(crew.iloc[0]["resource_status"], CAPACITY_DATA_MISSING)
        line_model = build_resource_economic_line_model(lines, crew)
        self.assertEqual(line_model.iloc[0]["resource_status"], CAPACITY_DATA_MISSING)

    def test_t6_available_zero_resource_deficit(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 100, 200)])
        capacity = pd.DataFrame([_capacity("E-01", 0)])
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertEqual(crew.iloc[0]["resource_status"], RESOURCE_DEFICIT)
        line_model = build_resource_economic_line_model(lines, crew)
        self.assertEqual(line_model.iloc[0]["resource_status"], RESOURCE_DEFICIT)
        self.assertAlmostEqual(float(line_model.iloc[0]["theoretical_feasible_qty"]), 0.0)

    def test_t7_economic_deficit(self) -> None:
        self.assertEqual(classify_economic_status(1000, 1200), ECONOMIC_DEFICIT)
        lines = pd.DataFrame([_line("L1", "E-01", 100, 200, plan_value=1000, labor_cost=1200)])
        capacity = pd.DataFrame([_capacity("E-01", 500)])
        line_model = build_resource_economic_models(lines, capacity)["line_model"]
        self.assertEqual(line_model.iloc[0]["economic_status"], ECONOMIC_DEFICIT)
        self.assertEqual(line_model.iloc[0]["combined_status"], COMBINED_ECONOMIC_RISK)

    def test_t8_price_not_defined_not_economic_deficit(self) -> None:
        self.assertEqual(classify_economic_status(0, 500), PRICE_NOT_DEFINED)
        lines = pd.DataFrame([_line("L1", "E-01", 100, 200, plan_value=0, labor_cost=500)])
        capacity = pd.DataFrame([_capacity("E-01", 500)])
        line_model = build_resource_economic_models(lines, capacity)["line_model"]
        self.assertEqual(line_model.iloc[0]["economic_status"], PRICE_NOT_DEFINED)
        self.assertEqual(line_model.iloc[0]["combined_status"], COMBINED_PRICE_UNDEFINED)

    def test_t9_empty_input_schema_preserving(self) -> None:
        crew = build_resource_economic_crew_model(pd.DataFrame(), pd.DataFrame())
        line_model = build_resource_economic_line_model(pd.DataFrame(), crew)
        summary = build_resource_economic_summary(crew, line_model)
        self.assertTrue(crew.empty)
        self.assertTrue(line_model.empty)
        self.assertEqual(summary["line_count"], 0)
        self.assertEqual(summary["available_labor_hours"], 0.0)

    def test_t10_feasible_work_value_proportional(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 568, 700, plan_value=1_000_000, labor_cost=700_000)])
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        line_model = build_resource_economic_models(lines, capacity)["line_model"]
        row = line_model.iloc[0]
        ratio = float(row["theoretical_feasible_qty"]) / 568.0
        self.assertAlmostEqual(float(row["feasible_work_value"]), 1_000_000 * ratio, places=0)
        self.assertAlmostEqual(float(row["feasible_labor_cost"]), 700_000 * ratio, places=0)

    def test_t11_summary_unique_crew_available_hours(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L1", "E-01", 100, 100, boq="A"),
                _line("L2", "E-01", 100, 100, boq="B"),
            ]
        )
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        models = build_resource_economic_models(lines, capacity)
        self.assertAlmostEqual(models["summary"]["available_labor_hours"], 330.0)

    def test_t12_missing_required_hours_not_calculated(self) -> None:
        row = _line("L1", "E-01", 100, 0)
        row["labor_hours"] = 0
        row["norm_hours_per_unit_effective"] = None
        lines = pd.DataFrame([row])
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        line_model = build_resource_economic_models(lines, capacity)["line_model"]
        self.assertEqual(line_model.iloc[0]["resource_status"], NOT_CALCULATED)
        self.assertIsNone(line_model.iloc[0]["theoretical_feasible_qty"])

    def test_combined_ready_and_both_risk(self) -> None:
        lines_ok = pd.DataFrame([_line("L1", "E-01", 100, 200, plan_value=1000, labor_cost=500)])
        cap_ok = pd.DataFrame([_capacity("E-01", 500)])
        line_ok = build_resource_economic_models(lines_ok, cap_ok)["line_model"]
        self.assertEqual(line_ok.iloc[0]["combined_status"], COMBINED_READY)

        lines_bad = pd.DataFrame([_line("L1", "E-01", 100, 700, plan_value=1000, labor_cost=500)])
        cap_bad = pd.DataFrame([_capacity("E-01", 100)])
        line_bad = build_resource_economic_models(lines_bad, cap_bad)["line_model"]
        self.assertEqual(line_bad.iloc[0]["combined_status"], COMBINED_RESOURCE_RISK)

        lines_both = pd.DataFrame([_line("L1", "E-01", 100, 700, plan_value=1000, labor_cost=2000)])
        line_both = build_resource_economic_models(lines_both, cap_bad)["line_model"]
        self.assertEqual(line_both.iloc[0]["combined_status"], COMBINED_BOTH_RISK)

    def test_t13_plan_side_row_zero_roster_is_missing(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 100, 200)])
        capacity = pd.DataFrame([_capacity("E-01", 0, roster_row_count=0)])
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertEqual(crew.iloc[0]["resource_status"], CAPACITY_DATA_MISSING)
        self.assertEqual(int(crew.iloc[0]["roster_row_count"]), 0)

    def test_t14_missing_capacity_feasible_qty_is_none(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 568, 568)])
        capacity = pd.DataFrame([_capacity("E-01", 0, roster_row_count=0)])
        line_model = build_resource_economic_models(lines, capacity)["line_model"]
        self.assertEqual(line_model.iloc[0]["resource_status"], CAPACITY_DATA_MISSING)
        self.assertIsNone(line_model.iloc[0]["theoretical_feasible_qty"])
        self.assertIsNone(line_model.iloc[0]["feasible_work_value"])

    def test_t15_confirmed_zero_capacity_is_deficit_with_zero_feasible(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 100, 200)])
        capacity = pd.DataFrame([_capacity("E-01", 0, roster_row_count=3)])
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertEqual(crew.iloc[0]["resource_status"], RESOURCE_DEFICIT)
        line_model = build_resource_economic_line_model(lines, crew)
        self.assertEqual(line_model.iloc[0]["resource_status"], RESOURCE_DEFICIT)
        self.assertAlmostEqual(float(line_model.iloc[0]["theoretical_feasible_qty"]), 0.0)

    def test_t16_missing_capacity_row_is_missing(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-99", 100, 200)])
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        crew = build_resource_economic_crew_model(lines, capacity)
        self.assertEqual(crew.iloc[0]["resource_status"], CAPACITY_DATA_MISSING)

    def test_t17_line_inherits_crew_missing_status(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L1", "E-01", 100, 200, boq="A"),
                _line("L2", "E-01", 200, 300, boq="B"),
            ]
        )
        capacity = pd.DataFrame([_capacity("E-01", 0, roster_row_count=0)])
        line_model = build_resource_economic_models(lines, capacity)["line_model"]
        self.assertTrue((line_model["resource_status"] == CAPACITY_DATA_MISSING).all())
        self.assertTrue(line_model["theoretical_feasible_qty"].isna().all())

    def test_t18_summary_counts_unique_missing_crews(self) -> None:
        lines = pd.DataFrame(
            [
                _line("L1", "E-01", 100, 200, boq="A"),
                _line("L2", "E-01", 200, 300, boq="B"),
                _line("L3", "E-02", 150, 200, boq="C"),
            ]
        )
        capacity = pd.DataFrame(
            [
                _capacity("E-01", 0, roster_row_count=0),
                _capacity("E-02", 0, roster_row_count=0),
            ]
        )
        models = build_resource_economic_models(lines, capacity)
        self.assertEqual(count_crews_missing_capacity(models["crew_model"]), 2)
        self.assertEqual(models["summary"]["crews_missing_capacity_count"], 2)
        self.assertTrue(models["summary"]["has_capacity_data_quality_issue"])

    def test_r12_canonical_month_joins_ru_plan_month(self) -> None:
        """R1.2: plan month_key RU joins approved capacity YYYY-MM."""
        lines = pd.DataFrame([_line("L1", "АСИ-15", 568, 568, month="июль-2026")])
        capacity = pd.DataFrame(
            [
                {
                    "project_code": "P1",
                    "month_key": "2026-07",
                    "crew_code": "АСИ-15",
                    "available_labor_hours": 264,
                    "available_fte": 264 / 176.0,
                    "fte_gap": 0,
                    "roster_row_count": 2,
                    "plan_labor_hours": 0,
                }
            ]
        )
        models = build_resource_economic_models(lines, capacity)
        crew = models["crew_model"].iloc[0]
        self.assertAlmostEqual(float(crew["crew_available_hours"]), 264.0)
        self.assertEqual(crew["resource_status"], PARTIALLY_FEASIBLE)


class DecisionEconomicsR15BTests(unittest.TestCase):
    def _asi28_fixture(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        # Control: required 689.8, value 3748545.28, labor 2069400; approved 176
        lines = pd.DataFrame(
            [
                _line(
                    "L1",
                    "АСИ-28",
                    qty=568,
                    hours=568.0,
                    plan_value=3_079_128.0,
                    labor_cost=1_704_000.0,
                    project="PRJ_001_БХК",
                    month="2026-08",
                    boq="1500-04-01-01",
                ),
                _line(
                    "L2",
                    "АСИ-28",
                    qty=112,
                    hours=112.0,
                    plan_value=613_417.28,
                    labor_cost=336_000.0,
                    project="PRJ_001_БХК",
                    month="2026-08",
                    boq="1500-04-01-04",
                ),
                _line(
                    "L3",
                    "АСИ-28",
                    qty=14,
                    hours=9.8,
                    plan_value=56_000.0,
                    labor_cost=29_400.0,
                    project="PRJ_001_БХК",
                    month="2026-08",
                    boq="1500-09-06-02",
                ),
                # Other crew demand for project denominator
                _line(
                    "LX",
                    "АСИ-10",
                    qty=100,
                    hours=11_047.686534329633,
                    plan_value=1_000_000.0,
                    labor_cost=100_000.0,
                    project="PRJ_001_БХК",
                    month="2026-08",
                    boq="OTHER",
                ),
            ]
        )
        capacity = pd.DataFrame(
            [_capacity("АСИ-28", 176.0, project="PRJ_001_БХК", month="2026-08", roster_row_count=1)]
        )
        return lines, capacity

    def test_requested_not_mixed_with_feasible(self) -> None:
        lines, capacity = self._asi28_fixture()
        models = build_resource_economic_models(lines, capacity)
        crew = models["crew_model"]
        crew28 = crew[crew["crew_code"] == "АСИ-28"].iloc[0]
        proj_req = project_required_direct_hours(
            lines, project_code="PRJ_001_БХК", month_key="2026-08"
        )
        decision = build_decision_economics_from_models(
            crew_row=crew28,
            line_model=models["line_model"],
            project_required_hours=proj_req,
            project_itr_pool=8_664_000.0,
        )
        self.assertAlmostEqual(decision["requested_work_value"], 3_748_545.28, places=2)
        self.assertAlmostEqual(decision["requested_direct_labor"], 2_069_400.0, places=1)
        self.assertAlmostEqual(
            decision["requested_margin_before_itr"], 1_679_145.28, places=2
        )
        self.assertNotAlmostEqual(
            decision["requested_direct_labor"],
            decision["feasible_direct_labor"],
            places=0,
        )
        self.assertFalse(decision["writes"])

    def test_feasible_direct_labor_from_176_hours(self) -> None:
        lines, capacity = self._asi28_fixture()
        models = build_resource_economic_models(lines, capacity)
        crew28 = models["crew_model"][models["crew_model"]["crew_code"] == "АСИ-28"].iloc[0]
        decision = build_decision_economics_from_models(
            crew_row=crew28,
            line_model=models["line_model"],
            project_required_hours=project_required_direct_hours(
                lines, project_code="PRJ_001_БХК", month_key="2026-08"
            ),
            project_itr_pool=8_664_000.0,
        )
        self.assertAlmostEqual(decision["approved_hours"], 176.0, places=1)
        self.assertAlmostEqual(decision["feasible_direct_labor"], 528_000.0, places=0)
        self.assertAlmostEqual(decision["feasible_work_value"], 956_427.91, places=0)
        self.assertAlmostEqual(decision["feasible_margin_before_itr"], 428_427.91, places=0)

    def test_itr_allocation_by_required_hours_and_absorption(self) -> None:
        lines, capacity = self._asi28_fixture()
        models = build_resource_economic_models(lines, capacity)
        crew28 = models["crew_model"][models["crew_model"]["crew_code"] == "АСИ-28"].iloc[0]
        proj_req = project_required_direct_hours(
            lines, project_code="PRJ_001_БХК", month_key="2026-08"
        )
        decision = build_decision_economics_from_models(
            crew_row=crew28,
            line_model=models["line_model"],
            project_required_hours=proj_req,
            project_itr_pool=8_664_000.0,
        )
        self.assertEqual(decision["itr_driver"], ITR_DRIVER_REQUIRED_HOURS)
        expected_full = 8_664_000.0 * (689.8 / proj_req)
        self.assertAlmostEqual(decision["full_allocated_itr"], expected_full, places=0)
        expected_absorbed = expected_full * (176.0 / 689.8)
        self.assertAlmostEqual(decision["absorbed_itr"], expected_absorbed, places=0)
        self.assertAlmostEqual(
            decision["unabsorbed_itr"],
            expected_full - expected_absorbed,
            places=0,
        )
        self.assertAlmostEqual(
            decision["normalized_result_after_absorbed_itr"],
            decision["feasible_margin_before_itr"] - decision["absorbed_itr"],
            places=0,
        )
        self.assertAlmostEqual(
            decision["full_month_operating_result"],
            decision["feasible_margin_before_itr"] - decision["full_allocated_itr"],
            places=0,
        )

    def test_management_message_rule(self) -> None:
        hit = classify_itr_absorption_management_message(
            feasible_direct_result=428_427.91,
            normalized_result=298_514.0,
            full_month_operating_result=-80_746.0,
        )
        self.assertTrue(hit["triggered"])
        self.assertIn("административным контуром", hit["message"])

        miss = classify_itr_absorption_management_message(
            feasible_direct_result=100.0,
            normalized_result=50.0,
            full_month_operating_result=10.0,
        )
        self.assertFalse(miss["triggered"])

        miss2 = classify_itr_absorption_management_message(
            feasible_direct_result=-1.0,
            normalized_result=50.0,
            full_month_operating_result=-10.0,
        )
        self.assertFalse(miss2["triggered"])

    def test_proposed_itr_pool_and_no_capacity_side_effect(self) -> None:
        mls = pd.DataFrame(
            [
                {
                    "project_code": "PRJ_001_БХК",
                    "month_key": "August-2026",
                    "indirect_hours_month": 216,
                    "indirect_cost_rub_month": 648_000,
                    "budget_status": None,
                },
                {
                    "project_code": "PRJ_001_БХК",
                    "month_key": "August-2026",
                    "indirect_hours_month": 0,
                    "indirect_cost_rub_month": 0,
                    "direct_hours_month": 176,
                    "direct_cost_rub_month": 528_000,
                },
            ]
        )
        pool = summarize_proposed_itr_pool(
            mls, project_code="PRJ_001_БХК", month_key="2026-08"
        )
        self.assertTrue(pool["matched"])
        self.assertEqual(pool["pool_status"], ITR_POOL_STATUS_PROPOSED)
        self.assertAlmostEqual(pool["itr_pool"], 648_000.0)
        self.assertFalse(pool["writes"])

        # ITR math must not invent approved capacity
        decision = build_crew_decision_economics(
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            crew_required_hours=689.8,
            project_required_hours=11_737.49,
            approved_hours=176.0,
            coverage=176.0 / 689.8,
            requested_work_value=3_748_545.28,
            requested_direct_labor=2_069_400.0,
            feasible_work_value=956_427.91,
            feasible_direct_labor=528_000.0,
            project_itr_pool=8_664_000.0,
        )
        self.assertAlmostEqual(decision["approved_hours"], 176.0)
        self.assertFalse(decision["writes"])


if __name__ == "__main__":
    unittest.main()
