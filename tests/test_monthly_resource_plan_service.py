"""
Unit tests for month_key helper and Monthly Resource Plan (R1.2).

Run:
  python -m unittest tests.test_monthly_resource_plan_service -v
"""

from __future__ import annotations

import unittest

import pandas as pd

from services.monthly_plan_resource_economic_service import (
    CAPACITY_DATA_MISSING,
    PARTIALLY_FEASIBLE,
    build_resource_economic_models,
)
from services.monthly_resource_plan_service import (
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_REJECTED,
    aggregate_approved_capacity,
    build_plan_line_payload,
    capacity_df_for_page22,
    resource_plan_business_key,
    validate_effective_date_range,
)
from utils.month_key import format_month_key_ru, normalize_month_key


def _plan_line(
    *,
    person: str,
    hours: float,
    status: str,
    project: str = "PRJ_001_БХК",
    month: str = "2026-07",
    crew: str = "АСИ-15",
    role: str = "Electrician",
    person_id: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
) -> dict:
    return {
        "resource_plan_line_id": f"id-{person}-{status}-{hours}-{effective_from}-{effective_to}",
        "project_code": project,
        "month_key": month,
        "crew_code": crew,
        "person_id": person_id,
        "person_name": person,
        "role": role,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "confirmed_available_hours": hours,
        "resource_status": status,
    }


def _boq_lines_control() -> pd.DataFrame:
    """Control-like demand: 955.4 required hours on ASI-15 / июль-2026."""
    # Split into two lines that sum to 955.4 for realism
    return pd.DataFrame(
        [
            {
                "plan_line_id": "L1",
                "project_code": "PRJ_001_БХК",
                "month_key": "июль-2026",
                "boq_code": "1500-04-01-01",
                "boq_name": "Кабель",
                "facility": "T1",
                "discipline": "ELEC",
                "crew_code": "АСИ-15",
                "crew_size": 2,
                "planned_qty": 568,
                "unit": "раскл",
                "labor_hours": 568,
                "norm_hours_per_unit_effective": 1.0,
                "labor_cost": 1_704_000,
                "plan_value": 3_079_128,
                "unit_price": 5421,
            },
            {
                "plan_line_id": "L2",
                "project_code": "PRJ_001_БХК",
                "month_key": "июль-2026",
                "boq_code": "OTHER",
                "boq_name": "Other",
                "facility": "T1",
                "discipline": "ELEC",
                "crew_code": "АСИ-15",
                "crew_size": 2,
                "planned_qty": 387.4,
                "unit": "ед",
                "labor_hours": 387.4,
                "norm_hours_per_unit_effective": 1.0,
                "labor_cost": 500_000,
                "plan_value": 900_000,
                "unit_price": 2323,
            },
        ]
    )


class MonthKeyHelperTests(unittest.TestCase):
    def test_t7_ru_month_normalizes(self) -> None:
        self.assertEqual(normalize_month_key("июль-2026"), "2026-07")
        self.assertEqual(normalize_month_key("август-2026"), "2026-08")
        self.assertEqual(normalize_month_key("январь-2026"), "2026-01")

    def test_t8_en_month_normalizes(self) -> None:
        self.assertEqual(normalize_month_key("July-2026"), "2026-07")
        self.assertEqual(normalize_month_key("August-2026"), "2026-08")
        self.assertEqual(normalize_month_key("January-2026"), "2026-01")

    def test_t9_invalid_month_none(self) -> None:
        self.assertIsNone(normalize_month_key(""))
        self.assertIsNone(normalize_month_key(None))
        self.assertIsNone(normalize_month_key("not-a-month"))
        self.assertIsNone(normalize_month_key("13-2026"))
        self.assertEqual(normalize_month_key("2026-07"), "2026-07")
        self.assertEqual(format_month_key_ru("2026-07"), "июль-2026")


class ResourcePlanAggregateTests(unittest.TestCase):
    def test_t1_draft_hours_excluded(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_DRAFT),
                _plan_line(person="B", hours=88, status=STATUS_DRAFT),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertTrue(cap.empty)

    def test_t2_approved_included(self) -> None:
        lines = pd.DataFrame([_plan_line(person="A", hours=176, status=STATUS_APPROVED)])
        cap = aggregate_approved_capacity(lines)
        self.assertEqual(len(cap), 1)
        self.assertAlmostEqual(float(cap.iloc[0]["available_labor_hours"]), 176.0)

    def test_t3_rejected_excluded(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_APPROVED),
                _plan_line(person="B", hours=200, status=STATUS_REJECTED),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertAlmostEqual(float(cap.iloc[0]["available_labor_hours"]), 176.0)

    def test_t4_two_approved_sum(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_APPROVED),
                _plan_line(person="B", hours=88, status=STATUS_APPROVED),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertAlmostEqual(float(cap.iloc[0]["available_labor_hours"]), 264.0)
        self.assertEqual(int(cap.iloc[0]["roster_row_count"]), 2)

    def test_t5_different_crew_not_mixed(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=100, status=STATUS_APPROVED, crew="АСИ-15"),
                _plan_line(person="B", hours=50, status=STATUS_APPROVED, crew="АСИ-29"),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        by_crew = {r["crew_code"]: float(r["available_labor_hours"]) for _, r in cap.iterrows()}
        self.assertAlmostEqual(by_crew["АСИ-15"], 100.0)
        self.assertAlmostEqual(by_crew["АСИ-29"], 50.0)

    def test_t6_different_month_not_mixed(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=100, status=STATUS_APPROVED, month="2026-07"),
                _plan_line(person="B", hours=50, status=STATUS_APPROVED, month="2026-08"),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        by_month = {r["month_key"]: float(r["available_labor_hours"]) for _, r in cap.iterrows()}
        self.assertAlmostEqual(by_month["2026-07"], 100.0)
        self.assertAlmostEqual(by_month["2026-08"], 50.0)

    def test_t10_no_approved_capacity_missing(self) -> None:
        lines = pd.DataFrame([_plan_line(person="A", hours=176, status=STATUS_DRAFT)])
        cap = aggregate_approved_capacity(lines)
        models = build_resource_economic_models(_boq_lines_control(), cap)
        self.assertEqual(models["crew_model"].iloc[0]["resource_status"], CAPACITY_DATA_MISSING)

    def test_t11_page22_receives_approved_hours(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_APPROVED),
                _plan_line(person="B", hours=88, status=STATUS_APPROVED),
            ]
        )
        cap = capacity_df_for_page22(lines)
        models = build_resource_economic_models(_boq_lines_control(), cap)
        crew = models["crew_model"].iloc[0]
        self.assertAlmostEqual(float(crew["crew_available_hours"]), 264.0)
        self.assertEqual(int(crew["roster_row_count"]), 2)

    def test_t12_control_partial_coverage(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_APPROVED),
                _plan_line(person="B", hours=88, status=STATUS_APPROVED),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        models = build_resource_economic_models(_boq_lines_control(), cap)
        crew = models["crew_model"].iloc[0]
        self.assertAlmostEqual(float(crew["crew_required_hours"]), 955.4, places=1)
        self.assertAlmostEqual(float(crew["crew_available_hours"]), 264.0)
        expected_cov = 264.0 / 955.4
        self.assertAlmostEqual(float(crew["coverage"]), expected_cov, places=4)
        self.assertEqual(crew["resource_status"], PARTIALLY_FEASIBLE)

        control = models["line_model"][
            models["line_model"]["boq_code"].astype(str) == "1500-04-01-01"
        ].iloc[0]
        self.assertAlmostEqual(
            float(control["theoretical_feasible_qty"]),
            568 * expected_cov,
            places=2,
        )

    def test_t13_no_double_count_capacity(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_APPROVED),
                _plan_line(person="B", hours=88, status=STATUS_APPROVED),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        models = build_resource_economic_models(_boq_lines_control(), cap)
        # Two BOQ lines, one crew — available counted once in summary
        self.assertAlmostEqual(models["summary"]["available_labor_hours"], 264.0)
        self.assertEqual(len(models["crew_model"]), 1)

    def test_payload_normalizes_ru_month(self) -> None:
        payload = build_plan_line_payload(
            project_code="PRJ_001_БХК",
            month_key="июль-2026",
            crew_code="АСИ-15",
            person_name="Иванов",
            confirmed_available_hours=88,
            resource_status=STATUS_APPROVED,
        )
        self.assertEqual(payload["month_key"], "2026-07")
        self.assertEqual(payload["resource_status"], STATUS_APPROVED)

    def test_t15_duplicate_same_person_period_same_business_key(self) -> None:
        key_a = resource_plan_business_key(
            project_code="PRJ_001_БХК",
            month_key="июль-2026",
            crew_code="АСИ-15",
            person_id=None,
            person_name="Иванов Алексей",
            effective_from="2026-07-01",
            effective_to="2026-07-15",
        )
        key_b = resource_plan_business_key(
            project_code="PRJ_001_БХК",
            month_key="2026-07",
            crew_code="АСИ-15",
            person_id="",
            person_name="Иванов Алексей",
            effective_from="2026-07-01",
            effective_to="2026-07-15",
        )
        self.assertEqual(key_a, key_b)

    def test_t16_same_person_two_periods_different_keys(self) -> None:
        key_p1 = resource_plan_business_key(
            project_code="PRJ_001_БХК",
            month_key="2026-07",
            crew_code="АСИ-15",
            person_id="P1",
            person_name="Иванов Алексей",
            effective_from="2026-07-01",
            effective_to="2026-07-15",
        )
        key_p2 = resource_plan_business_key(
            project_code="PRJ_001_БХК",
            month_key="2026-07",
            crew_code="АСИ-15",
            person_id="P1",
            person_name="Иванов Алексей",
            effective_from="2026-07-16",
            effective_to="2026-07-31",
        )
        self.assertNotEqual(key_p1, key_p2)

    def test_t17_headcount_one_person_two_periods(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(
                    person="Иванов Алексей",
                    person_id="P1",
                    hours=88,
                    status=STATUS_APPROVED,
                    effective_from="2026-07-01",
                    effective_to="2026-07-15",
                ),
                _plan_line(
                    person="Иванов Алексей",
                    person_id="P1",
                    hours=88,
                    status=STATUS_APPROVED,
                    effective_from="2026-07-16",
                    effective_to="2026-07-31",
                ),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertEqual(int(cap.iloc[0]["approved_people_count"]), 1)
        self.assertEqual(int(cap.iloc[0]["approved_assignment_count"]), 2)

    def test_t18_approved_hours_two_periods_summed(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(
                    person="Иванов Алексей",
                    person_id="P1",
                    hours=88,
                    status=STATUS_APPROVED,
                    effective_from="2026-07-01",
                    effective_to="2026-07-15",
                ),
                _plan_line(
                    person="Иванов Алексей",
                    person_id="P1",
                    hours=88,
                    status=STATUS_APPROVED,
                    effective_from="2026-07-16",
                    effective_to="2026-07-31",
                ),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertAlmostEqual(float(cap.iloc[0]["available_labor_hours"]), 176.0)

    def test_t19_invalid_month_key_rejected(self) -> None:
        self.assertIsNone(normalize_month_key("not-a-month"))
        with self.assertRaises(ValueError):
            build_plan_line_payload(
                project_code="PRJ_001_БХК",
                month_key="not-a-month",
                crew_code="АСИ-15",
                person_name="Иванов",
                confirmed_available_hours=10,
            )

    def test_t20_effective_to_before_from_invalid(self) -> None:
        with self.assertRaises(ValueError):
            validate_effective_date_range("2026-07-20", "2026-07-01")
        with self.assertRaises(ValueError):
            build_plan_line_payload(
                project_code="PRJ_001_БХК",
                month_key="2026-07",
                crew_code="АСИ-15",
                person_name="Иванов",
                confirmed_available_hours=10,
                effective_from="2026-07-20",
                effective_to="2026-07-01",
            )

    def test_t21_approved_requires_approved_metadata(self) -> None:
        payload = build_plan_line_payload(
            project_code="PRJ_001_БХК",
            month_key="2026-07",
            crew_code="АСИ-15",
            person_name="Иванов",
            confirmed_available_hours=88,
            resource_status=STATUS_APPROVED,
            approved_by="planner",
        )
        self.assertEqual(payload["approved_by"], "planner")
        self.assertTrue(payload["approved_at"])

        draft = build_plan_line_payload(
            project_code="PRJ_001_БХК",
            month_key="2026-07",
            crew_code="АСИ-15",
            person_name="Иванов",
            confirmed_available_hours=88,
            resource_status=STATUS_DRAFT,
        )
        self.assertIsNone(draft["approved_by"])
        self.assertIsNone(draft["approved_at"])

    def test_t22_draft_rejected_not_in_approved_capacity(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=100, status=STATUS_DRAFT),
                _plan_line(person="B", hours=200, status=STATUS_REJECTED),
                _plan_line(person="C", hours=50, status=STATUS_APPROVED),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertEqual(len(cap), 1)
        self.assertAlmostEqual(float(cap.iloc[0]["available_labor_hours"]), 50.0)


if __name__ == "__main__":
    unittest.main()