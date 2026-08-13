"""
R1.3 Monthly Resource Planning Workbench — pure helper tests.

No live Supabase writes.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from services.monthly_plan_resource_economic_service import (
    CAPACITY_DATA_MISSING,
    PARTIALLY_FEASIBLE,
    RESOURCE_READY,
    build_resource_economic_models,
)
from services.monthly_resource_plan_service import (
    BATCH_APPROVE_AVAILABLE,
    BATCH_SKIP_ALREADY_APPROVED,
    BATCH_SKIP_ALREADY_DRAFT,
    BATCH_SKIP_FALLBACK,
    BATCH_SKIP_REJECTED,
    BATCH_WRITE_AVAILABLE,
    DELETE_AVAILABLE,
    PLAN_UI_APPROVED,
    PLAN_UI_DRAFT,
    PLAN_UI_NOT_ADDED,
    PLAN_UI_REJECTED,
    PRODUCTIVE_HOURS_PER_PERSON_SHIFT,
    ROSTER_MODE_CURRENT_MONTH,
    ROSTER_MODE_FALLBACK,
    STATUS_APPROVED,
    STATUS_DRAFT,
    STATUS_REJECTED,
    WB_STATUS_DEFICIT,
    WB_STATUS_MISSING,
    WB_STATUS_READY,
    aggregate_approved_capacity,
    build_crew_workload_lines,
    build_draft_payload_from_current_month_assignment,
    build_plan_line_payload,
    build_roster_prefill_payload,
    capacity_df_for_page22,
    compute_line_duration_shifts,
    create_draft_resource_plan_from_selection,
    is_resource_line_editable,
    preview_capacity_after_hours_delta,
    resolve_assignment_plan_ui_status,
    resolve_crew_roster_from_labor_summary,
    summarize_crew_demand_from_labor_lines,
    summarize_crew_resource_commitment,
    summarize_proposed_vs_demand,
    summarize_selected_roster_preview,
    update_draft_resource_plan_line,
)


def _plan_line(
    *,
    person: str,
    hours: float,
    status: str,
    person_id: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
) -> dict:
    return {
        "resource_plan_line_id": f"id-{person}-{status}-{hours}-{effective_from}",
        "project_code": "PRJ_001_БХК",
        "month_key": "2026-07",
        "crew_code": "АСИ-15",
        "person_id": person_id,
        "person_name": person,
        "role": "Электромонтажник",
        "effective_from": effective_from,
        "effective_to": effective_to,
        "confirmed_available_hours": hours,
        "resource_status": status,
    }


def _demand_lines(required: float = 955.4) -> pd.DataFrame:
    # Two BOQ lines summing to required hours for ASI-15 / июль-2026
    first = 568.0
    second = required - first
    return pd.DataFrame(
        [
            {
                "plan_line_id": "L1",
                "project_code": "PRJ_001_БХК",
                "month_key": "июль-2026",
                "boq_code": "1500-04-01-01",
                "crew_code": "АСИ-15",
                "planned_qty": 568,
                "labor_hours": first,
                "plan_value": 3_079_128,
                "labor_cost": 1_704_000,
                "norm_hours_per_unit_effective": 1.0,
            },
            {
                "plan_line_id": "L2",
                "project_code": "PRJ_001_БХК",
                "month_key": "июль-2026",
                "boq_code": "1500-04-01-02",
                "crew_code": "АСИ-15",
                "planned_qty": second,
                "labor_hours": second,
                "plan_value": 1_000_000,
                "labor_cost": 500_000,
                "norm_hours_per_unit_effective": 1.0,
            },
        ]
    )


class WorkbenchSummaryTests(unittest.TestCase):
    def test_empty_resource_plan_is_missing(self) -> None:
        summary = summarize_crew_resource_commitment(
            required_hours=955.4,
            approved_available_hours=0.0,
            approved_people_count=0,
            has_approved_plan=False,
        )
        self.assertEqual(summary["status_code"], WB_STATUS_MISSING)
        self.assertEqual(summary["status_ru"], "Ресурсный план не сформирован")
        self.assertIsNone(summary["coverage"])
        self.assertIsNone(summary["hours_gap"])

    def test_zero_confirmed_capacity_is_deficit_not_missing(self) -> None:
        summary = summarize_crew_resource_commitment(
            required_hours=955.4,
            approved_available_hours=0.0,
            approved_people_count=1,
            has_approved_plan=True,
        )
        self.assertEqual(summary["status_code"], WB_STATUS_DEFICIT)
        self.assertAlmostEqual(summary["coverage"], 0.0)

    def test_partial_capacity_deficit(self) -> None:
        summary = summarize_crew_resource_commitment(
            required_hours=955.4,
            approved_available_hours=176.0,
            approved_people_count=1,
            has_approved_plan=True,
        )
        self.assertEqual(summary["status_code"], WB_STATUS_DEFICIT)
        self.assertAlmostEqual(summary["coverage"], 176.0 / 955.4, places=4)
        self.assertAlmostEqual(summary["hours_gap"], 176.0 - 955.4, places=4)

    def test_sufficient_capacity_ready(self) -> None:
        summary = summarize_crew_resource_commitment(
            required_hours=955.4,
            approved_available_hours=1000.0,
            approved_people_count=3,
            has_approved_plan=True,
        )
        self.assertEqual(summary["status_code"], WB_STATUS_READY)

    def test_demand_from_labor_lines_control(self) -> None:
        demand = summarize_crew_demand_from_labor_lines(
            _demand_lines(955.4),
            project_code="PRJ_001_БХК",
            month_key="2026-07",
            crew_code="АСИ-15",
        )
        self.assertTrue(demand["matched"])
        self.assertAlmostEqual(demand["required_hours"], 955.4, places=4)
        self.assertEqual(demand["boq_count"], 2)

    def test_new_row_defaults_draft(self) -> None:
        payload = build_plan_line_payload(
            project_code="PRJ_001_БХК",
            month_key="2026-07",
            crew_code="АСИ-15",
            person_name="Тест",
            confirmed_available_hours=88,
        )
        self.assertEqual(payload["resource_status"], STATUS_DRAFT)
        self.assertIsNone(payload["approved_by"])

    def test_draft_excluded_approved_included_rejected_excluded(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=88, status=STATUS_DRAFT),
                _plan_line(person="B", hours=176, status=STATUS_APPROVED),
                _plan_line(person="C", hours=50, status=STATUS_REJECTED),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertEqual(len(cap), 1)
        self.assertAlmostEqual(float(cap.iloc[0]["available_labor_hours"]), 176.0)

    def test_two_partial_periods_sum_hours_headcount_one(self) -> None:
        lines = pd.DataFrame(
            [
                _plan_line(
                    person="Иванов",
                    hours=88,
                    status=STATUS_APPROVED,
                    person_id="P1",
                    effective_from="2026-07-01",
                    effective_to="2026-07-15",
                ),
                _plan_line(
                    person="Иванов",
                    hours=88,
                    status=STATUS_APPROVED,
                    person_id="P1",
                    effective_from="2026-07-16",
                    effective_to="2026-07-31",
                ),
            ]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertAlmostEqual(float(cap.iloc[0]["available_labor_hours"]), 176.0)
        self.assertEqual(int(cap.iloc[0]["approved_people_count"]), 1)
        self.assertEqual(int(cap.iloc[0]["approved_assignment_count"]), 2)

    def test_preview_does_not_write_and_math(self) -> None:
        preview = preview_capacity_after_hours_delta(
            required_hours=955.4,
            current_approved_hours=176.0,
            current_approved_people=1,
            has_approved_plan=True,
            add_hours=88.0,
            add_new_person=True,
        )
        self.assertFalse(preview["writes"])
        self.assertAlmostEqual(preview["current_approved_hours"], 176.0)
        self.assertAlmostEqual(preview["add_hours"], 88.0)
        self.assertAlmostEqual(preview["projected_approved_hours"], 264.0)
        self.assertAlmostEqual(preview["coverage_pct"], 264.0 / 955.4 * 100.0, places=2)
        self.assertEqual(preview["status_code"], WB_STATUS_DEFICIT)

    def test_control_fixture_before_after_mocked_approve(self) -> None:
        required = 955.4
        before_lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_APPROVED),
                _plan_line(person="B", hours=88, status=STATUS_DRAFT),
            ]
        )
        before_cap = aggregate_approved_capacity(before_lines)
        self.assertAlmostEqual(float(before_cap.iloc[0]["available_labor_hours"]), 176.0)

        preview = preview_capacity_after_hours_delta(
            required_hours=required,
            current_approved_hours=176.0,
            current_approved_people=1,
            has_approved_plan=True,
            add_hours=88.0,
        )
        self.assertAlmostEqual(preview["projected_approved_hours"], 264.0)

        after_lines = pd.DataFrame(
            [
                _plan_line(person="A", hours=176, status=STATUS_APPROVED),
                _plan_line(person="B", hours=88, status=STATUS_APPROVED),
            ]
        )
        after_cap = aggregate_approved_capacity(after_lines)
        self.assertAlmostEqual(float(after_cap.iloc[0]["available_labor_hours"]), 264.0)

        # Page22 receives approved capacity without math changes
        labor = _demand_lines(required)
        models = build_resource_economic_models(labor, capacity_df_for_page22(after_cap))
        crew = models["crew_model"]
        row = crew[crew["crew_code"] == "АСИ-15"].iloc[0]
        self.assertEqual(row["resource_status"], PARTIALLY_FEASIBLE)
        self.assertAlmostEqual(float(row["crew_available_hours"]), 264.0, places=4)

    def test_page22_missing_when_no_approved(self) -> None:
        labor = _demand_lines(955.4)
        models = build_resource_economic_models(labor, capacity_df_for_page22(pd.DataFrame()))
        row = models["crew_model"].iloc[0]
        self.assertEqual(row["resource_status"], CAPACITY_DATA_MISSING)

    def test_page22_ready_when_enough_approved(self) -> None:
        labor = _demand_lines(955.4)
        lines = pd.DataFrame(
            [_plan_line(person="A", hours=1000, status=STATUS_APPROVED)]
        )
        models = build_resource_economic_models(
            labor, capacity_df_for_page22(aggregate_approved_capacity(lines))
        )
        row = models["crew_model"].iloc[0]
        self.assertEqual(row["resource_status"], RESOURCE_READY)

    def test_approved_read_only_policy(self) -> None:
        self.assertTrue(is_resource_line_editable(STATUS_DRAFT))
        self.assertFalse(is_resource_line_editable(STATUS_APPROVED))
        self.assertFalse(is_resource_line_editable(STATUS_REJECTED))

    def test_update_draft_rejects_approved_existing_row(self) -> None:
        result = update_draft_resource_plan_line(
            "id-1",
            person_name="X",
            confirmed_available_hours=10,
            existing_row=_plan_line(person="A", hours=10, status=STATUS_APPROVED),
        )
        self.assertFalse(result["ok"])
        self.assertIn("Черновик", result["error"])

    def test_update_draft_allows_draft_without_live_write(self) -> None:
        existing = _plan_line(person="A", hours=10, status=STATUS_DRAFT)
        existing["resource_plan_line_id"] = "draft-1"
        with patch(
            "services.monthly_resource_plan_service.upsert_resource_plan_line",
            return_value={"ok": True, "error": None, "row": existing},
        ) as mocked:
            result = update_draft_resource_plan_line(
                "draft-1",
                person_name="A2",
                confirmed_available_hours=20,
                existing_row=existing,
            )
            self.assertTrue(result["ok"])
            mocked.assert_called_once()
            payload = mocked.call_args[0][0]
            self.assertEqual(payload["person_name"], "A2")
            self.assertEqual(payload["project_code"], "PRJ_001_БХК")
            self.assertEqual(payload["resource_status"], STATUS_DRAFT)

    def test_no_delete_action(self) -> None:
        self.assertFalse(DELETE_AVAILABLE)

    def test_candidate_hours_not_auto_capacity(self) -> None:
        # Candidate registry hours must not enter capacity unless APPROVED plan row exists
        candidate_hours = 104.0
        lines = pd.DataFrame(
            [_plan_line(person="Иванов", hours=candidate_hours, status=STATUS_DRAFT)]
        )
        cap = aggregate_approved_capacity(lines)
        self.assertTrue(cap.empty)


class R14WorkloadAndRosterTests(unittest.TestCase):
    def _asi28_august_labor(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "plan_line_id": "L1",
                    "project_code": "PRJ_001_БХК",
                    "month_key": "август-2026",
                    "boq_code": "1500-04-01-04",
                    "boq_name": "BOQ-04",
                    "unit": "шт.",
                    "crew": "АСИ-28",
                    "crew_size": 1,
                    "planned_qty": 112.0,
                    "labor_hours": 112.0,
                    "plan_value": 613417.28,
                },
                {
                    "plan_line_id": "L2",
                    "project_code": "PRJ_001_БХК",
                    "month_key": "август-2026",
                    "boq_code": "1500-04-01-01",
                    "boq_name": "BOQ-01",
                    "unit": "шт.",
                    "crew": "АСИ-28",
                    "crew_size": 2,
                    "planned_qty": 568.0,
                    "labor_hours": 568.0,
                    "plan_value": 3_079_128.0,
                },
                {
                    "plan_line_id": "L3",
                    "project_code": "PRJ_001_БХК",
                    "month_key": "август-2026",
                    "boq_code": "1500-09-06-02",
                    "boq_name": "BOQ-02",
                    "unit": "шт.",
                    "crew": "АСИ-28",
                    "crew_size": 2,
                    "planned_qty": 14.0,
                    "labor_hours": 9.8,
                    "plan_value": 56000.0,
                },
            ]
        )

    def test_workload_control_asi28_august(self) -> None:
        labor = self._asi28_august_labor()
        demand = summarize_crew_demand_from_labor_lines(
            labor,
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
        )
        self.assertTrue(demand["matched"])
        self.assertEqual(demand["boq_count"], 3)
        self.assertAlmostEqual(demand["required_hours"], 689.8, places=1)
        self.assertAlmostEqual(demand["plan_value"], 3_748_545.28, places=2)

        workload = build_crew_workload_lines(
            labor,
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
        )
        self.assertEqual(len(workload), 3)
        control = workload[workload["boq_code"] == "1500-04-01-01"].iloc[0]
        self.assertAlmostEqual(float(control["planned_qty"]), 568.0)
        self.assertAlmostEqual(float(control["required_hours"]), 568.0)
        self.assertAlmostEqual(float(control["plan_value"]), 3_079_128.0)

    def test_duration_reuses_constructor_formula(self) -> None:
        # 568 h / (2 people × 8 h/shift) = 35.5 shifts — same as Page10B
        duration = compute_line_duration_shifts(568.0, 2)
        self.assertAlmostEqual(duration or 0.0, 568.0 / (2 * PRODUCTIVE_HOURS_PER_PERSON_SHIFT))
        self.assertAlmostEqual(duration or 0.0, 35.5, places=1)

    def test_proposed_vs_demand_control(self) -> None:
        diag = summarize_proposed_vs_demand(required_hours=689.8, proposed_hours=392.0)
        self.assertAlmostEqual(diag["hours_gap"], 392.0 - 689.8, places=1)
        self.assertAlmostEqual(diag["coverage_pct"], 392.0 / 689.8 * 100.0, places=2)

    @patch("services.monthly_resource_plan_service.load_candidates_from_labor_summary")
    def test_current_month_roster_mode(self, mocked_load: unittest.mock.Mock) -> None:
        mocked_load.return_value = pd.DataFrame(
            [
                {
                    "full_name_ru": "Толстых Я.О.",
                    "role": "Электромонтажник",
                    "month_key": "August-2026",
                    "direct_hours_month": 176,
                    "budget_status": "Approved",
                },
                {
                    "full_name_ru": "Тельнов С.А.",
                    "role": "Электромонтажник",
                    "month_key": "August-2026",
                    "direct_hours_month": 216,
                    "budget_status": "Approved",
                },
            ]
        )
        roster = resolve_crew_roster_from_labor_summary(
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
        )
        self.assertEqual(roster["mode"], ROSTER_MODE_CURRENT_MONTH)
        self.assertAlmostEqual(roster["proposed_hours_total"], 392.0)

    @patch("services.monthly_resource_plan_service.load_candidates_from_labor_summary")
    def test_fallback_prefill_no_historical_hours(self, mocked_load: unittest.mock.Mock) -> None:
        mocked_load.return_value = pd.DataFrame(
            [
                {
                    "full_name_ru": "Иванов И.И.",
                    "role": "Сварщик",
                    "month_key": "June-2026",
                    "direct_hours_month": 208,
                    "actual_mobilization_date": "2026-06-01",
                    "actual_demobilization_date": "2026-06-30",
                }
            ]
        )
        roster = resolve_crew_roster_from_labor_summary(
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
        )
        self.assertEqual(roster["mode"], ROSTER_MODE_FALLBACK)
        prefill = build_roster_prefill_payload(
            roster["rows"].iloc[0],
            roster_mode=ROSTER_MODE_FALLBACK,
        )
        self.assertIsNone(prefill.get("proposed_hours"))
        self.assertIsNone(prefill.get("effective_from"))
        self.assertIsNone(prefill.get("effective_to"))

    def test_current_month_prefill_includes_proposed_hours(self) -> None:
        prefill = build_roster_prefill_payload(
            {
                "full_name_ru": "Толстых Я.О.",
                "role": "Электромонтажник",
                "month_key": "August-2026",
                "direct_hours_month": 176,
                "actual_mobilization_date": "2026-08-01",
                "planned_demobilization_date": "2026-08-31",
            },
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
        )
        self.assertEqual(prefill["person_name"], "Толстых Я.О.")
        self.assertAlmostEqual(prefill["proposed_hours"], 176.0)
        self.assertEqual(prefill["effective_from"], "2026-08-01")
        self.assertEqual(prefill["effective_to"], "2026-08-31")

    def test_proposal_not_in_approved_capacity(self) -> None:
        proposal_only = pd.DataFrame(
            [_plan_line(person="Толстых Я.О.", hours=176, status=STATUS_DRAFT)]
        )
        cap = aggregate_approved_capacity(proposal_only)
        self.assertTrue(cap.empty)


class R141BatchSelectionPreviewTests(unittest.TestCase):
    def _asi28_august_roster(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "full_name_ru": "Толстых Я.О.",
                    "role": "Электромонтажник",
                    "month_key": "August-2026",
                    "direct_hours_month": 176,
                    "budget_status": "Approved",
                },
                {
                    "full_name_ru": "Тельнов С.А.",
                    "role": "Электромонтажник",
                    "month_key": "August-2026",
                    "direct_hours_month": 216,
                    "budget_status": "Approved",
                },
            ]
        )

    def test_both_people_preview_control(self) -> None:
        preview = summarize_selected_roster_preview(
            self._asi28_august_roster(),
            selected_indices=[0, 1],
            required_hours=689.8,
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
        )
        self.assertEqual(preview["selected_people"], 2)
        self.assertAlmostEqual(preview["selected_hours"], 392.0)
        self.assertAlmostEqual(preview["required_hours"], 689.8, places=1)
        self.assertAlmostEqual(preview["hours_gap"], 392.0 - 689.8, places=1)
        self.assertAlmostEqual(preview["coverage_pct"], 392.0 / 689.8 * 100.0, places=2)
        self.assertFalse(preview["is_approved_capacity"])
        self.assertFalse(preview["writes"])

    def test_tolstykh_only_preview(self) -> None:
        preview = summarize_selected_roster_preview(
            self._asi28_august_roster(),
            selected_indices=[0],
            required_hours=689.8,
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
        )
        self.assertEqual(preview["selected_people"], 1)
        self.assertAlmostEqual(preview["selected_hours"], 176.0)
        self.assertAlmostEqual(preview["hours_gap"], 176.0 - 689.8, places=1)
        self.assertAlmostEqual(preview["coverage_pct"], 176.0 / 689.8 * 100.0, places=2)

    def test_empty_selection_zero_hours(self) -> None:
        preview = summarize_selected_roster_preview(
            self._asi28_august_roster(),
            selected_indices=[],
            required_hours=689.8,
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
        )
        self.assertEqual(preview["selected_people"], 0)
        self.assertAlmostEqual(preview["selected_hours"], 0.0)
        self.assertFalse(preview["writes"])

    def test_preview_does_not_write_or_enter_capacity(self) -> None:
        with patch(
            "services.monthly_resource_plan_service.upsert_resource_plan_line"
        ) as mocked_upsert:
            preview = summarize_selected_roster_preview(
                self._asi28_august_roster(),
                selected_indices=[0, 1],
                required_hours=689.8,
                roster_mode=ROSTER_MODE_CURRENT_MONTH,
            )
            mocked_upsert.assert_not_called()
            self.assertFalse(preview["writes"])
        cap = aggregate_approved_capacity(pd.DataFrame())
        self.assertTrue(cap.empty)

    def test_fallback_historical_hours_not_proposed_capacity(self) -> None:
        historical = pd.DataFrame(
            [
                {
                    "full_name_ru": "Иванов И.И.",
                    "role": "Сварщик",
                    "month_key": "June-2026",
                    "direct_hours_month": 208,
                },
                {
                    "full_name_ru": "Петров П.П.",
                    "role": "Сварщик",
                    "month_key": "June-2026",
                    "direct_hours_month": 176,
                },
            ]
        )
        preview = summarize_selected_roster_preview(
            historical,
            selected_indices=[0, 1],
            required_hours=689.8,
            roster_mode=ROSTER_MODE_FALLBACK,
        )
        self.assertEqual(preview["selected_people"], 2)
        self.assertAlmostEqual(preview["selected_hours"], 0.0)
        self.assertFalse(preview["is_approved_capacity"])

    def test_no_false_coverage_when_required_missing(self) -> None:
        preview = summarize_selected_roster_preview(
            self._asi28_august_roster(),
            selected_indices=[0, 1],
            required_hours=0.0,
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
        )
        self.assertIsNone(preview["coverage"])
        self.assertIsNone(preview["coverage_pct"])


class R142BatchDraftCreateTests(unittest.TestCase):
    def _asi28_august_roster(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "full_name_ru": "Толстых Я.О.",
                    "role": "Электромонтажник",
                    "month_key": "August-2026",
                    "direct_hours_month": 176,
                    "budget_status": "Approved",
                    "airtable_record_id": "recTolstykh",
                    "actual_mobilization_date": "2026-07-01",
                    "actual_demobilization_date": "2026-08-26",
                    "planned_demobilization_date": "2026-08-30",
                },
                {
                    "full_name_ru": "Тельнов С.А.",
                    "role": "Электромонтажник",
                    "month_key": "August-2026",
                    "direct_hours_month": 216,
                    "budget_status": "Approved",
                    "airtable_record_id": "recTelnov",
                    "actual_mobilization_date": "2026-07-01",
                    "actual_demobilization_date": "2026-09-05",
                    "planned_demobilization_date": "2026-08-30",
                },
            ]
        )

    def _write_collector(self) -> tuple[list[dict], callable]:
        store: list[dict] = []

        def write_fn(payload: dict) -> dict:
            store.append(dict(payload))
            return {"ok": True, "error": None, "row": dict(payload)}

        return store, write_fn

    def test_batch_create_two_draft_rows(self) -> None:
        store, write_fn = self._write_collector()
        result = create_draft_resource_plan_from_selection(
            self._asi28_august_roster(),
            selected_indices=[0, 1],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
            existing_plan_df=pd.DataFrame(),
            write_fn=write_fn,
        )
        self.assertEqual(result["created_count"], 2)
        self.assertAlmostEqual(result["created_hours"], 392.0)
        self.assertFalse(result["auto_approve"])
        self.assertEqual(len(store), 2)
        self.assertTrue(all(row["resource_status"] == STATUS_DRAFT for row in store))
        names = {row["person_name"] for row in store}
        self.assertEqual(names, {"Толстых Я.О.", "Тельнов С.А."})
        hours = {
            row["person_name"]: row["confirmed_available_hours"] for row in store
        }
        self.assertAlmostEqual(hours["Толстых Я.О."], 176.0)
        self.assertAlmostEqual(hours["Тельнов С.А."], 216.0)
        self.assertEqual(store[0]["source_airtable_record_id"], "recTolstykh")
        self.assertEqual(store[0]["effective_from"], "2026-07-01")
        self.assertEqual(store[0]["effective_to"], "2026-08-26")
        self.assertIsNone(store[0].get("person_id"))

    def test_draft_rows_are_not_approved_capacity(self) -> None:
        store, write_fn = self._write_collector()
        create_draft_resource_plan_from_selection(
            self._asi28_august_roster(),
            selected_indices=[0, 1],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
            existing_plan_df=pd.DataFrame(),
            write_fn=write_fn,
        )
        cap = aggregate_approved_capacity(pd.DataFrame(store))
        self.assertTrue(cap.empty)
        self.assertFalse(BATCH_APPROVE_AVAILABLE)
        self.assertTrue(BATCH_WRITE_AVAILABLE)

    def test_duplicate_protection_does_not_recreate(self) -> None:
        roster = self._asi28_august_roster()
        store, write_fn = self._write_collector()
        first = create_draft_resource_plan_from_selection(
            roster,
            selected_indices=[0, 1],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
            existing_plan_df=pd.DataFrame(),
            write_fn=write_fn,
        )
        self.assertEqual(first["created_count"], 2)
        existing = pd.DataFrame(store)
        existing["month_key"] = "2026-08"
        existing["crew_code"] = "АСИ-28"
        second_store, second_write = self._write_collector()
        second = create_draft_resource_plan_from_selection(
            roster,
            selected_indices=[0, 1],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
            existing_plan_df=existing,
            write_fn=second_write,
        )
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["skipped_count"], 2)
        self.assertEqual(len(second_store), 0)
        self.assertTrue(
            all(item["reason"] == BATCH_SKIP_ALREADY_DRAFT for item in second["skipped"])
        )

    def test_approved_and_rejected_not_recreated(self) -> None:
        roster = self._asi28_august_roster()
        existing = pd.DataFrame(
            [
                _plan_line(person="Толстых Я.О.", hours=176, status=STATUS_APPROVED),
                _plan_line(person="Тельнов С.А.", hours=216, status=STATUS_REJECTED),
            ]
        )
        existing["month_key"] = "2026-08"
        existing["crew_code"] = "АСИ-28"
        existing.loc[0, "source_airtable_record_id"] = "recTolstykh"
        existing.loc[1, "source_airtable_record_id"] = "recTelnov"
        store, write_fn = self._write_collector()
        result = create_draft_resource_plan_from_selection(
            roster,
            selected_indices=[0, 1],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
            existing_plan_df=existing,
            write_fn=write_fn,
        )
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(len(store), 0)
        reasons = {item["reason"] for item in result["skipped"]}
        self.assertEqual(reasons, {BATCH_SKIP_ALREADY_APPROVED, BATCH_SKIP_REJECTED})

    def test_partial_selection_tolstykh_only(self) -> None:
        store, write_fn = self._write_collector()
        result = create_draft_resource_plan_from_selection(
            self._asi28_august_roster(),
            selected_indices=[0],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
            existing_plan_df=pd.DataFrame(),
            write_fn=write_fn,
        )
        self.assertEqual(result["created_count"], 1)
        self.assertAlmostEqual(result["created_hours"], 176.0)
        self.assertEqual(store[0]["person_name"], "Толстых Я.О.")
        self.assertNotIn("Тельнов С.А.", {row["person_name"] for row in store})

    def test_unselected_telnov_not_created(self) -> None:
        store, write_fn = self._write_collector()
        create_draft_resource_plan_from_selection(
            self._asi28_august_roster(),
            selected_indices=[0],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_CURRENT_MONTH,
            existing_plan_df=pd.DataFrame(),
            write_fn=write_fn,
        )
        self.assertEqual(len(store), 1)
        self.assertEqual(store[0]["person_name"], "Толстых Я.О.")

    def test_fallback_does_not_batch_create(self) -> None:
        historical = pd.DataFrame(
            [
                {
                    "full_name_ru": "Иванов И.И.",
                    "role": "Сварщик",
                    "month_key": "June-2026",
                    "direct_hours_month": 208,
                    "airtable_record_id": "recIvanov",
                    "actual_mobilization_date": "2026-06-01",
                    "actual_demobilization_date": "2026-06-30",
                }
            ]
        )
        store, write_fn = self._write_collector()
        result = create_draft_resource_plan_from_selection(
            historical,
            selected_indices=[0],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
            roster_mode=ROSTER_MODE_FALLBACK,
            existing_plan_df=pd.DataFrame(),
            write_fn=write_fn,
        )
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(len(store), 0)
        self.assertEqual(result["errors"][0]["reason"], BATCH_SKIP_FALLBACK)

    def test_missing_dates_are_not_invented(self) -> None:
        row = {
            "full_name_ru": "Толстых Я.О.",
            "direct_hours_month": 176,
            "airtable_record_id": "recTolstykh",
        }
        with self.assertRaises(ValueError):
            build_draft_payload_from_current_month_assignment(
                row,
                project_code="PRJ_001_БХК",
                month_key="2026-08",
                crew_code="АСИ-28",
            )

    def test_ui_status_from_existing_rows(self) -> None:
        roster = self._asi28_august_roster()
        existing = pd.DataFrame(
            [
                {
                    **_plan_line(person="Толстых Я.О.", hours=176, status=STATUS_DRAFT),
                    "month_key": "2026-08",
                    "crew_code": "АСИ-28",
                    "source_airtable_record_id": "recTolstykh",
                }
            ]
        )
        status = resolve_assignment_plan_ui_status(
            existing,
            roster.iloc[0],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
        )
        self.assertEqual(status["code"], PLAN_UI_DRAFT)
        empty_status = resolve_assignment_plan_ui_status(
            pd.DataFrame(),
            roster.iloc[1],
            project_code="PRJ_001_БХК",
            month_key="2026-08",
            crew_code="АСИ-28",
        )
        self.assertEqual(empty_status["code"], PLAN_UI_NOT_ADDED)
        self.assertEqual(PLAN_UI_APPROVED, "approved")
        self.assertEqual(PLAN_UI_REJECTED, "rejected")


if __name__ == "__main__":
    unittest.main()
