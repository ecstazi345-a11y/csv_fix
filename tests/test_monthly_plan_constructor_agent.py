"""
MPCA-001 — unit tests for Monthly Plan Constructor Agent.

Uses only injected DataFrames (no live writes). Live smoke is separate.
"""

from __future__ import annotations

import json
import unittest
from typing import Any

import pandas as pd

from agents.monthly_plan_constructor.domain import (
    ACTIVE_PLAN_LINE_STATUSES,
    aggregate_already_planned,
    build_constructor_proposal,
    merge_not_required_once,
)
from agents.monthly_plan_constructor.runtime import run_monthly_plan_constructor_agent
from utils.month_key import normalize_month_key


def _scope_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "project_code": "PRJ_001_БХК",
        "facility_building": "Здание А",
        "construction_discipline": "ОВ",
        "facility": "Здание А",
        "discipline": "ОВ",
        "system": "SYS-1",
        "iwp": "IWP-1",
        "boq_code": "BOQ-001",
        "boq_name": "Работа 1",
        "unit": "м3",
        "total_project_qty": 100.0,
        "total_qty": 100.0,
        "executed_qty_all_time": 0.0,
        "executed_qty": 0.0,
        "unit_price": 10.0,
        "total_project_value": 1000.0,
        "total_value": 1000.0,
        "planning_remaining_qty": 100.0,
        "manual_executed_before_system": 0.0,
        "manual_verified_remaining_qty": float("nan"),
    }
    base.update(overrides)
    return base


def _adj_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "project_code": "PRJ_001_БХК",
        "facility_building": "Здание А",
        "construction_discipline": "ОВ",
        "boq_code": "BOQ-001",
        "not_required_qty": 0.0,
        "not_required_reason": "",
    }
    base.update(overrides)
    return base


def _plan_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "plan_line_id": "pl-1",
        "client_line_uid": "cuid-1",
        "project_code": "PRJ_001_БХК",
        "month_key": "август-2026",
        "facility": "Здание А",
        "discipline": "ОВ",
        "system": "SYS-1",
        "iwp": "IWP-1",
        "boq_code": "BOQ-001",
        "planned_qty": 10.0,
        "crew": "Бригада-1",
        "status": "NOT_SENT",
    }
    base.update(overrides)
    return base


def _run_injected(
    scope: list[dict[str, Any]],
    adjustments: list[dict[str, Any]] | None = None,
    plans: list[dict[str, Any]] | None = None,
    *,
    project_code: str = "PRJ_001_БХК",
    month: str = "август-2026",
    scope_error: str | None = None,
    plan_error: str | None = None,
) -> dict[str, Any]:
    scope_df = pd.DataFrame(scope)
    adj_df = pd.DataFrame(adjustments or [])
    plan_df = pd.DataFrame(plans or [])

    def load_scope(_code: str):
        meta = {
            "source": "test",
            "error": scope_error,
            "row_count": 0 if scope_error else len(scope_df),
        }
        return (pd.DataFrame() if scope_error else scope_df.copy()), meta

    def load_adj(_code: str):
        return adj_df.copy(), {
            "source": "test",
            "error": None,
            "row_count": len(adj_df),
        }

    def load_plans(_code: str, _month: str):
        meta = {
            "source": "test",
            "error": plan_error,
            "row_count": 0 if plan_error else len(plan_df),
        }
        return (pd.DataFrame() if plan_error else plan_df.copy()), meta

    return run_monthly_plan_constructor_agent(
        project_code,
        month,
        load_scope_fn=load_scope,
        load_adjustments_fn=load_adj,
        load_plan_lines_fn=load_plans,
    )


class TestMonthlyPlanConstructorAgent(unittest.TestCase):
    def test_01_zero_price_physical_survives(self) -> None:
        run = _run_injected(
            [
                _scope_row(
                    boq_code="BOQ-ZERO",
                    unit_price=0.0,
                    total_project_value=0.0,
                    total_value=0.0,
                    total_project_qty=50.0,
                    total_qty=50.0,
                    planning_remaining_qty=50.0,
                )
            ]
        )
        codes = {c["boq_code"] for c in run["proposed_candidates"]}
        self.assertIn("BOQ-ZERO", codes)

    def test_02_completed_excluded(self) -> None:
        run = _run_injected(
            [
                _scope_row(
                    boq_code="BOQ-DONE",
                    executed_qty_all_time=100.0,
                    executed_qty=100.0,
                    planning_remaining_qty=0.0,
                )
            ]
        )
        self.assertEqual(run["counts"]["candidates"], 0)
        self.assertGreaterEqual(run["counts"]["excluded_completed"], 1)
        self.assertTrue(
            any(e["reason_code"] == "EXCLUDED_COMPLETED" for e in run["exclusions"])
        )

    def test_03_no_remainder_excluded(self) -> None:
        run = _run_injected(
            [
                _scope_row(
                    boq_code="BOQ-NR",
                    total_project_qty=10.0,
                    total_qty=10.0,
                    executed_qty_all_time=10.0,
                    executed_qty=10.0,
                    planning_remaining_qty=0.0,
                )
            ]
        )
        # fully executed → completed path; force remaining 0 with partial exec via not_required
        run2 = _run_injected(
            [
                _scope_row(
                    boq_code="BOQ-EMPTY",
                    total_project_qty=10.0,
                    total_qty=10.0,
                    executed_qty_all_time=5.0,
                    executed_qty=5.0,
                    planning_remaining_qty=0.0,
                )
            ],
            adjustments=[_adj_row(boq_code="BOQ-EMPTY", not_required_qty=5.0)],
        )
        self.assertEqual(run2["counts"]["candidates"], 0)
        self.assertTrue(
            any(
                e["reason_code"] in {"EXCLUDED_NO_REMAINDER", "EXCLUDED_NOT_REQUIRED"}
                for e in run2["exclusions"]
            )
        )
        self.assertGreaterEqual(
            run["counts"]["excluded_completed"] + run["counts"]["excluded_no_remainder"],
            1,
        )

    def test_04_not_required_decreases_effective(self) -> None:
        proposal = build_constructor_proposal(
            pd.DataFrame([_scope_row()]),
            pd.DataFrame([_adj_row(not_required_qty=20.0)]),
            pd.DataFrame(),
            "PRJ_001_БХК",
            "август-2026",
        )
        cand = proposal["candidates"][0]
        self.assertEqual(cand["not_required_qty"], 20.0)
        self.assertEqual(cand["effective_required_qty"], 80.0)
        self.assertEqual(cand["remaining_qty"], 80.0)

    def test_05_not_required_applied_once(self) -> None:
        scope = pd.DataFrame([_scope_row()])
        # First normalize path used by domain starts from raw; merge once
        from services.monthly_planning_scope_read_service import normalize_scope_raw_df

        norm = normalize_scope_raw_df(scope)
        adj = pd.DataFrame([_adj_row(not_required_qty=15.0)])
        once = merge_not_required_once(norm, adj)
        twice = merge_not_required_once(once, adj)
        self.assertEqual(float(once.iloc[0]["not_required_qty"]), 15.0)
        self.assertEqual(float(twice.iloc[0]["not_required_qty"]), 15.0)

    def test_06_manual_executed_not_double_applied(self) -> None:
        proposal = build_constructor_proposal(
            pd.DataFrame(
                [
                    _scope_row(
                        executed_qty_all_time=10.0,
                        executed_qty=10.0,
                        manual_executed_before_system=5.0,
                        planning_remaining_qty=85.0,
                    )
                ]
            ),
            pd.DataFrame(),  # no not_required; adjustments must not re-add manual
            pd.DataFrame(),
            "PRJ_001_БХК",
            "август-2026",
        )
        cand = proposal["candidates"][0]
        # executed_total = 10 + 5 = 15; remaining vs effective 100 → 85
        self.assertEqual(cand["executed_total_qty"], 15.0)
        self.assertEqual(cand["remaining_qty"], 85.0)
        self.assertTrue(proposal["meta"]["manual_executed_reapplied"] is False)

    def test_07_existing_plan_reduces_available(self) -> None:
        proposal = build_constructor_proposal(
            pd.DataFrame([_scope_row()]),
            pd.DataFrame(),
            pd.DataFrame([_plan_row(planned_qty=30.0)]),
            "PRJ_001_БХК",
            "август-2026",
        )
        cand = proposal["candidates"][0]
        self.assertEqual(cand["already_planned_qty"], 30.0)
        self.assertEqual(cand["available_to_add_qty"], 70.0)

    def test_08_several_plan_lines_same_boq_aggregate(self) -> None:
        plans = [
            _plan_row(plan_line_id="a", planned_qty=10.0),
            _plan_row(plan_line_id="b", client_line_uid="c2", planned_qty=15.0),
        ]
        aggregates, _ = aggregate_already_planned(
            pd.DataFrame(plans),
            project_code="PRJ_001_БХК",
            stored_month_key="август-2026",
        )
        key = ("PRJ_001_БХК", "ЗДАНИЕ А", "ОВ", "BOQ-001")
        self.assertEqual(aggregates[key]["already_planned_qty"], 25.0)
        self.assertEqual(len(aggregates[key]["plan_line_ids"]), 2)

    def test_09_same_boq_different_facility_not_mixed(self) -> None:
        proposal = build_constructor_proposal(
            pd.DataFrame(
                [
                    _scope_row(facility="Здание А", facility_building="Здание А", boq_code="BOQ-X"),
                    _scope_row(facility="Здание Б", facility_building="Здание Б", boq_code="BOQ-X"),
                ]
            ),
            pd.DataFrame(),
            pd.DataFrame(
                [
                    _plan_row(
                        facility="Здание А",
                        boq_code="BOQ-X",
                        planned_qty=40.0,
                        plan_line_id="p1",
                    )
                ]
            ),
            "PRJ_001_БХК",
            "август-2026",
        )
        by_fac = {c["facility"]: c for c in proposal["candidates"]}
        self.assertEqual(by_fac["Здание А"]["already_planned_qty"], 40.0)
        self.assertEqual(by_fac["Здание Б"]["already_planned_qty"], 0.0)

    def test_10_same_boq_different_discipline_not_mixed(self) -> None:
        proposal = build_constructor_proposal(
            pd.DataFrame(
                [
                    _scope_row(discipline="ОВ", construction_discipline="ОВ", boq_code="BOQ-Y"),
                    _scope_row(
                        discipline="ЭМ",
                        construction_discipline="ЭМ",
                        boq_code="BOQ-Y",
                    ),
                ]
            ),
            pd.DataFrame(),
            pd.DataFrame(
                [
                    _plan_row(
                        discipline="ОВ",
                        boq_code="BOQ-Y",
                        planned_qty=25.0,
                        plan_line_id="p1",
                    )
                ]
            ),
            "PRJ_001_БХК",
            "август-2026",
        )
        by_disc = {c["discipline"]: c for c in proposal["candidates"]}
        self.assertEqual(by_disc["ОВ"]["already_planned_qty"], 25.0)
        self.assertEqual(by_disc["ЭМ"]["already_planned_qty"], 0.0)

    def test_11_partial_planned_stays_candidate(self) -> None:
        run = _run_injected(
            [_scope_row()],
            plans=[_plan_row(planned_qty=40.0)],
        )
        self.assertEqual(run["counts"]["candidates"], 1)
        cand = run["proposed_candidates"][0]
        self.assertEqual(cand["candidate_state"], "PARTIAL_REMAINING")
        self.assertGreater(cand["available_to_add_qty"], 0)

    def test_12_fully_planned_excluded(self) -> None:
        run = _run_injected(
            [_scope_row()],
            plans=[_plan_row(planned_qty=100.0)],
        )
        self.assertEqual(run["counts"]["candidates"], 0)
        self.assertGreaterEqual(run["counts"]["excluded_already_planned"], 1)

    def test_13_crew_not_invented(self) -> None:
        run = _run_injected([_scope_row()])
        cand = run["proposed_candidates"][0]
        self.assertIsNone(cand["proposed_crew"])
        self.assertIn("crew", cand["human_required_fields"])

    def test_14_planned_qty_not_invented(self) -> None:
        run = _run_injected([_scope_row()])
        cand = run["proposed_candidates"][0]
        self.assertIsNone(cand["proposed_plan_qty"])
        self.assertIn("planned_qty", cand["human_required_fields"])

    def test_15_ambiguity_produces_human_issue(self) -> None:
        plans = [
            _plan_row(plan_line_id="1", system="S1", iwp="I1", planned_qty=5.0),
            _plan_row(
                plan_line_id="2",
                client_line_uid="c2",
                system="S2",
                iwp="I2",
                planned_qty=5.0,
            ),
        ]
        run = _run_injected([_scope_row()], plans=plans)
        codes = {i["code"] for i in run["human_issues"]}
        self.assertIn("CONFLICTING_PLAN_LINES", codes)

    def test_16_russian_month_canonicalizes(self) -> None:
        self.assertEqual(normalize_month_key("август-2026"), "2026-08")
        run = _run_injected([_scope_row()], month="август-2026")
        self.assertEqual(run["month_key_canonical"], "2026-08")
        self.assertEqual(run["month_key"], "август-2026")

    def test_17_trace_contains_required_phases(self) -> None:
        run = _run_injected([_scope_row()])
        steps = {e["step_code"] for e in run["trace"]}
        required = {
            "START",
            "LOAD_SCOPE",
            "LOAD_ADJUSTMENTS",
            "LOAD_EXISTING_PLAN",
            "NORMALIZE",
            "CALCULATE_AVAILABILITY",
            "APPLY_EXISTING_PLAN",
            "CLASSIFY",
            "BUILD_CANDIDATES",
            "DETECT_HUMAN_ISSUES",
            "VALIDATE",
            "PREPARE_HANDOFF",
            "FINISH",
        }
        self.assertTrue(required.issubset(steps))

    def test_18_all_duration_ms_non_negative(self) -> None:
        run = _run_injected([_scope_row()])
        self.assertGreaterEqual(run["duration_ms"], 0)
        for event in run["trace"]:
            self.assertGreaterEqual(event["duration_ms"], 0)

    def test_19_actions_performed_generated(self) -> None:
        run = _run_injected([_scope_row()])
        self.assertGreaterEqual(len(run["actions_performed"]), 1)
        self.assertTrue(any("перечень" in a["action"].lower() or "состав" in a["action"].lower() for a in run["actions_performed"]))

    def test_20_no_write_path_used(self) -> None:
        import agents.monthly_plan_constructor.domain as domain
        import agents.monthly_plan_constructor.tools as tools
        import agents.monthly_plan_constructor.runtime as runtime
        import inspect

        for mod in (domain, tools, runtime):
            src = inspect.getsource(mod)
            for banned in ("insert(", "update(", "delete(", "upsert(", ".rpc("):
                # allow comments / strings about bans in docs only — code modules
                self.assertNotIn(banned, src.replace("product INSERT", "").replace("product UPDATE", ""))

    def test_21_missing_critical_source_not_silent_zero(self) -> None:
        run = _run_injected(
            [_scope_row()],
            scope_error="SimulatedScopeFailure",
        )
        self.assertEqual(run["state"], "FAILED")
        self.assertTrue(any(e.get("code") == "SCOPE_READ_FAILED" for e in run["errors"]))
        self.assertEqual(run["counts"].get("scanned", 0), 0)

    def test_22_candidate_cannot_exceed_available(self) -> None:
        run = _run_injected(
            [_scope_row()],
            plans=[_plan_row(planned_qty=30.0)],
        )
        for cand in run["proposed_candidates"]:
            self.assertLessEqual(
                cand["available_to_add_qty"],
                cand["remaining_qty"] + 1e-9,
            )

    def test_23_run_result_serializable(self) -> None:
        run = _run_injected([_scope_row()])
        payload = json.dumps(run, ensure_ascii=False, default=str)
        self.assertTrue(payload.startswith("{"))
        restored = json.loads(payload)
        self.assertEqual(restored["agent_code"], "MONTHLY_PLAN_CONSTRUCTOR")

    def test_24_handoff_state_logically_consistent(self) -> None:
        run = _run_injected([_scope_row()])
        handoff = run["handoff"]
        self.assertTrue(handoff["proposal_ready"])
        self.assertFalse(handoff["admission_handoff_ready"])
        self.assertFalse(handoff["ready"])
        self.assertEqual(handoff["recipient"], "MONTHLY_PLAN_ADMISSION_AGENT")
        self.assertIn(run["state"], {"PROPOSAL_READY", "NEEDS_HUMAN"})

    def test_active_statuses_match_product(self) -> None:
        self.assertEqual(
            ACTIVE_PLAN_LINE_STATUSES,
            frozenset({"NOT_SENT", "SENT_TO_ADMISSION"}),
        )


if __name__ == "__main__":
    unittest.main()
