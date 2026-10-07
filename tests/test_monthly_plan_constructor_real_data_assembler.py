"""
Increment 11A / EXISTING-MONTH-PLAN-AWARENESS — RealDataShadowAdapter tests.

Injected trusted-read results only. No live Supabase. No product writes.
Existing month plan is authoritative operational state, not a human benchmark.
"""

from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    build_candidate_package,
)
from agents.monthly_plan_constructor.lifecycle import CandidateAssemblyResult
from agents.monthly_plan_constructor.mission_scope import (
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.real_data_assembler import (
    CODE_ADJUSTMENTS_READ_FAILED,
    CODE_DOMAIN_BLOCKER,
    CODE_PLAN_LINES_READ_FAILED,
    CODE_SNAPSHOT_MISMATCH,
    CODE_SNAPSHOT_MISSING,
    RealDataAssemblerError,
    RealDataShadowAdapter,
    _candidate_id_from_grain,
    _norm_month,
    _norm_part,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    SecureReadError,
    read_constructor_reality,
)
from security.agent_execution_context import issue_read_only_agent_context

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY = "16160-17"
DISCIPLINE = "Автоматизация"
SYSTEM = "SYS-1"
IWP = "IWP-1"
BOQ = "BOQ-001"
REPO = Path(__file__).resolve().parents[1]
ASSEMBLER_PATH = (
    REPO / "agents" / "monthly_plan_constructor" / "real_data_assembler.py"
)
SCOPE_PATCH = (
    "agents.monthly_plan_constructor.real_data_assembler.execute_constructor_scope_read"
)
ADJ_PATCH = (
    "agents.monthly_plan_constructor.real_data_assembler."
    "execute_constructor_adjustments_read"
)
PLAN_PATCH = (
    "agents.monthly_plan_constructor.real_data_assembler."
    "execute_constructor_plan_lines_read"
)
# Trusted capability must be used; infrastructure table name must not be called
# directly from the assembler.
TRUSTED_PLAN_CAPABILITY = "execute_constructor_plan_lines_read"
FORBIDDEN_INFRA_BYPASS = (
    "load_constructor_month_plan_lines",
    "monthly_plan_lines_v2",
)
HUMAN_BENCHMARK_TOKENS = (
    "session_state",
    "st.session_state",
)
WRITE_TOKENS = (
    "insert",
    "update",
    "upsert",
    "delete",
    "create_client",
    "streamlit",
    "openai",
)


def _mission(**overrides: object):
    payload: dict[str, object] = {"project_code": PROJECT, "month_key": MONTH}
    payload.update(overrides)
    return build_constructor_mission_scope(**payload)  # type: ignore[arg-type]


def _context(project_code: str = PROJECT):
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=project_code,
    )


def _scope_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_code": PROJECT,
        "facility_building": FACILITY,
        "construction_discipline": DISCIPLINE,
        "facility": FACILITY,
        "discipline": DISCIPLINE,
        "system": SYSTEM,
        "system_label": SYSTEM,
        "iwp": IWP,
        "iwp_id": IWP,
        "boq_code": BOQ,
        "boq_name": "Кабель",
        "unit_of_measure": "м",
        "unit": "м",
        "total_project_qty": 100.0,
        "executed_qty_all_time": 10.0,
        "manual_executed_before_system": 0.0,
        "manual_verified_remaining_qty": None,
        "planning_remaining_qty": 90.0,
        "unit_price": 12.0,
        "total_project_value": 1200.0,
    }
    base.update(overrides)
    return base


def _adj_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_code": PROJECT,
        "facility_building": FACILITY,
        "construction_discipline": DISCIPLINE,
        "boq_code": BOQ,
        "not_required_qty": 0.0,
        "not_required_reason": "",
    }
    base.update(overrides)
    return base


def _plan_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "plan_line_id": "pl-1",
        "client_line_uid": "cuid-1",
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY,
        "discipline": DISCIPLINE,
        "system": SYSTEM,
        "iwp": IWP,
        "boq_code": BOQ,
        "planned_qty": 30.0,
        "crew": "Бригада-1",
        "status": "NOT_SENT",
    }
    base.update(overrides)
    return base


def _ok_meta(**overrides: object) -> dict[str, object]:
    meta: dict[str, object] = {
        "error": None,
        "row_count": 1,
        "credential_env": "SUPABASE_KEY",
    }
    meta.update(overrides)
    return meta


def _read_triple(
    scope_rows: list[dict[str, object]],
    adj_rows: list[dict[str, object]] | None = None,
    plan_rows: list[dict[str, object]] | None = None,
    *,
    scope_meta: dict[str, object] | None = None,
    adj_meta: dict[str, object] | None = None,
    plan_meta: dict[str, object] | None = None,
):
    scope_df = pd.DataFrame(scope_rows)
    adj_df = pd.DataFrame(adj_rows if adj_rows is not None else [_adj_row()])
    if plan_rows is None:
        plan_df = pd.DataFrame()
        default_plan_meta = _ok_meta(row_count=0)
    else:
        plan_df = pd.DataFrame(plan_rows)
        default_plan_meta = _ok_meta(row_count=len(plan_rows))
    return (
        patch(SCOPE_PATCH, return_value=(scope_df, scope_meta or _ok_meta())),
        patch(ADJ_PATCH, return_value=(adj_df, adj_meta or _ok_meta())),
        patch(
            PLAN_PATCH,
            return_value=(plan_df, plan_meta or default_plan_meta),
        ),
    )


def _capture(
    adapter: RealDataShadowAdapter,
    mission=None,
    context=None,
    **read_kwargs,
):
    scope_patch, adj_patch, plan_patch = _read_triple(**read_kwargs)
    with scope_patch, adj_patch, plan_patch:
        return read_constructor_reality(
            context or _context(),
            mission or _mission(),
            scope_reader=adapter.scope_reader,
        )


class RealDataAssemblerTests(unittest.TestCase):
    def test_a_real_quantity_preserved_with_empty_plan(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(adapter, mission, scope_rows=[_scope_row()], plan_rows=[])
        result = adapter(reality, mission)
        self.assertIsInstance(result, CandidateAssemblyResult)
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(float(candidate["available_to_add_qty"]), 90.0)
        self.assertEqual(float(candidate["remaining_qty"]), 90.0)
        self.assertEqual(float(candidate["already_planned_qty"]), 0.0)

    def test_b_no_human_benchmark_contamination(self) -> None:
        source = ASSEMBLER_PATH.read_text(encoding="utf-8")
        self.assertIn(TRUSTED_PLAN_CAPABILITY, source)
        for token in FORBIDDEN_INFRA_BYPASS:
            self.assertNotIn(token, source)
        lowered = source.lower()
        for token in HUMAN_BENCHMARK_TOKENS:
            self.assertNotIn(token, lowered)
        # Existing plan is operational state (real already_planned), not a forced zero.
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(
            adapter,
            mission,
            scope_rows=[_scope_row()],
            plan_rows=[_plan_row(planned_qty=30.0)],
        )
        result = adapter(reality, mission)
        self.assertEqual(float(result.candidates[0]["already_planned_qty"]), 30.0)
        self.assertEqual(float(result.candidates[0]["available_to_add_qty"]), 60.0)

    def test_c_not_required_applied_once(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(
            adapter,
            mission,
            scope_rows=[
                _scope_row(executed_qty_all_time=0.0, planning_remaining_qty=100.0)
            ],
            adj_rows=[_adj_row(not_required_qty=30.0)],
            plan_rows=[],
        )
        result = adapter(reality, mission)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(float(result.candidates[0]["available_to_add_qty"]), 70.0)
        self.assertEqual(float(result.candidates[0]["remaining_qty"]), 70.0)

    def test_d_unresolved_labor_keeps_candidate(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(
            adapter,
            mission,
            scope_rows=[_scope_row()],
            plan_rows=[_plan_row(planned_qty=20.0)],
        )
        result = adapter(reality, mission)
        self.assertEqual(result.candidates[0]["labor_norm_status"], LABOR_UNRESOLVED)
        package = build_candidate_package(
            mission,
            result.candidates,
            mission_id="mission-11a",
            scanned_count=result.scanned_count,
            excluded_completed_count=result.excluded_completed_count,
            excluded_no_remainder_count=result.excluded_no_remainder_count,
            already_planned_count=result.already_planned_count,
            run_id="run-11a",
            snapshot_id=reality.read_id,
        )
        self.assertEqual(package.candidate_count, 1)
        self.assertEqual(package.candidates[0].labor_norm_status, LABOR_UNRESOLVED)

    def test_e_out_of_scope_data_does_not_become_candidate(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission(facility_scope=FACILITY)
        reality = _capture(
            adapter,
            mission,
            scope_rows=[
                _scope_row(),
                _scope_row(
                    facility="16160-13",
                    facility_building="16160-13",
                    boq_code="BOQ-OUT",
                ),
            ],
            plan_rows=[],
        )
        self.assertEqual(reality.row_count, 1)
        self.assertEqual(reality.rows[0].boq_code, BOQ)
        result = adapter(reality, mission)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0]["boq_code"], BOQ)
        self.assertEqual(result.candidates[0]["facility"], FACILITY)

    def test_f_snapshot_reality_mismatch_fails_closed(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        _capture(adapter, mission, scope_rows=[_scope_row()], plan_rows=[])
        other = RealDataShadowAdapter()
        other_reality = _capture(
            other,
            mission,
            scope_rows=[_scope_row(boq_code="BOQ-OTHER")],
            plan_rows=[],
        )
        with self.assertRaises(RealDataAssemblerError) as raised:
            adapter(other_reality, mission)
        self.assertEqual(raised.exception.code, CODE_SNAPSHOT_MISMATCH)

    def test_g_assembly_without_snapshot_fails_closed(self) -> None:
        adapter = RealDataShadowAdapter()
        other = RealDataShadowAdapter()
        reality = _capture(other, scope_rows=[_scope_row()], plan_rows=[])
        with self.assertRaises(RealDataAssemblerError) as raised:
            adapter(reality, _mission())
        self.assertEqual(raised.exception.code, CODE_SNAPSHOT_MISSING)

    def test_h_failed_adjustments_read_does_not_create_package_input(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        scope_df = pd.DataFrame([_scope_row()])
        with patch(SCOPE_PATCH, return_value=(scope_df, _ok_meta())), patch(
            ADJ_PATCH,
            return_value=(
                pd.DataFrame(),
                {"error": "ADJUSTMENTS_PRIVILEGED_CREDENTIAL_MISSING", "row_count": 0},
            ),
        ), patch(
            PLAN_PATCH,
            return_value=(pd.DataFrame(), _ok_meta(row_count=0)),
        ):
            with self.assertRaises(SecureReadError) as raised:
                read_constructor_reality(
                    _context(),
                    mission,
                    scope_reader=adapter.scope_reader,
                )
        self.assertEqual(raised.exception.code, CODE_ADJUSTMENTS_READ_FAILED)
        with self.assertRaises(RealDataAssemblerError) as assemble_error:
            adapter.assemble_candidates(
                _capture(
                    RealDataShadowAdapter(),
                    mission,
                    scope_rows=[_scope_row()],
                    plan_rows=[],
                ),
                mission,
            )
        self.assertEqual(assemble_error.exception.code, CODE_SNAPSHOT_MISSING)

    def test_i_run_isolation(self) -> None:
        first = RealDataShadowAdapter()
        second = RealDataShadowAdapter()
        mission = _mission()
        first_reality = _capture(
            first, mission, scope_rows=[_scope_row()], plan_rows=[]
        )
        second_reality = _capture(
            second,
            mission,
            scope_rows=[
                _scope_row(
                    boq_code="BOQ-TWO",
                    planning_remaining_qty=40.0,
                    executed_qty_all_time=60.0,
                    total_project_qty=100.0,
                )
            ],
            plan_rows=[],
        )
        first_result = first(first_reality, mission)
        second_result = second(second_reality, mission)
        self.assertEqual(first_result.candidates[0]["boq_code"], BOQ)
        self.assertEqual(float(first_result.candidates[0]["available_to_add_qty"]), 90.0)
        self.assertEqual(second_result.candidates[0]["boq_code"], "BOQ-TWO")
        self.assertEqual(float(second_result.candidates[0]["available_to_add_qty"]), 40.0)
        with self.assertRaises(RealDataAssemblerError) as raised:
            first(second_reality, mission)
        self.assertEqual(raised.exception.code, CODE_SNAPSHOT_MISMATCH)

    def test_j_successful_refresh_replaces_snapshot(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        first_reality = _capture(
            adapter, mission, scope_rows=[_scope_row()], plan_rows=[]
        )
        self.assertEqual(first_reality.rows[0].boq_code, BOQ)
        second_reality = _capture(
            adapter,
            mission,
            scope_rows=[
                _scope_row(
                    boq_code="BOQ-REFRESH",
                    planning_remaining_qty=55.0,
                    executed_qty_all_time=45.0,
                )
            ],
            plan_rows=[],
        )
        result = adapter(second_reality, mission)
        self.assertEqual(result.candidates[0]["boq_code"], "BOQ-REFRESH")
        self.assertEqual(float(result.candidates[0]["available_to_add_qty"]), 55.0)
        with self.assertRaises(RealDataAssemblerError):
            adapter(first_reality, mission)

    def test_k_failed_refresh_does_not_make_failed_data_authoritative(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        first_reality = _capture(
            adapter, mission, scope_rows=[_scope_row()], plan_rows=[]
        )
        with patch(
            SCOPE_PATCH,
            return_value=(pd.DataFrame(), {"error": "READ_FAILED", "row_count": 0}),
        ), patch(ADJ_PATCH, return_value=(pd.DataFrame([_adj_row()]), _ok_meta())), patch(
            PLAN_PATCH,
            return_value=(pd.DataFrame(), _ok_meta(row_count=0)),
        ):
            with self.assertRaises(SecureReadError):
                read_constructor_reality(
                    _context(),
                    mission,
                    scope_reader=adapter.scope_reader,
                )
        result = adapter(first_reality, mission)
        self.assertEqual(result.candidates[0]["boq_code"], BOQ)
        self.assertEqual(float(result.candidates[0]["available_to_add_qty"]), 90.0)

    def test_l_deterministic_candidate_id(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(adapter, mission, scope_rows=[_scope_row()], plan_rows=[])
        first = adapter(reality, mission).candidates[0]["candidate_id"]
        second = adapter(reality, mission).candidates[0]["candidate_id"]
        self.assertEqual(first, second)
        expected = _candidate_id_from_grain(
            (
                _norm_part(PROJECT),
                _norm_month(MONTH),
                _norm_part(FACILITY),
                _norm_part(DISCIPLINE),
                _norm_part(SYSTEM),
                _norm_part(IWP),
                "",
                _norm_part(BOQ),
            )
        )
        self.assertEqual(first, expected)
        long_system = "X" * 200
        long_adapter = RealDataShadowAdapter()
        long_reality = _capture(
            long_adapter,
            mission,
            scope_rows=[_scope_row(system=long_system, system_label=long_system)],
            plan_rows=[],
        )
        long_id = long_adapter(long_reality, mission).candidates[0]["candidate_id"]
        self.assertTrue(str(long_id).startswith("sha256:"))
        self.assertEqual(
            long_id,
            "sha256:"
            + hashlib.sha256(
                "|".join(
                    (
                        _norm_part(PROJECT),
                        _norm_month(MONTH),
                        _norm_part(FACILITY),
                        _norm_part(DISCIPLINE),
                        _norm_part(long_system),
                        _norm_part(IWP),
                        "",
                        _norm_part(BOQ),
                    )
                ).encode("utf-8")
            ).hexdigest(),
        )

    def test_m_no_product_write_path(self) -> None:
        source = ASSEMBLER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr.lower())
        for token in ("insert", "update", "upsert", "delete", "create_client"):
            self.assertNotIn(token, called)
        lowered = source.lower()
        self.assertNotIn("streamlit", lowered)
        self.assertNotIn("openai", lowered)
        self.assertNotIn("create_client", source)

    def test_failed_adjustments_does_not_replace_previous_snapshot(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        first_reality = _capture(
            adapter, mission, scope_rows=[_scope_row()], plan_rows=[]
        )
        with patch(
            SCOPE_PATCH,
            return_value=(pd.DataFrame([_scope_row(boq_code="BOQ-NEW")]), _ok_meta()),
        ), patch(
            ADJ_PATCH,
            return_value=(pd.DataFrame(), {"error": "RLS_BLOCKED", "row_count": 0}),
        ), patch(
            PLAN_PATCH,
            return_value=(pd.DataFrame(), _ok_meta(row_count=0)),
        ):
            with self.assertRaises(SecureReadError) as raised:
                read_constructor_reality(
                    _context(),
                    mission,
                    scope_reader=adapter.scope_reader,
                )
        self.assertEqual(raised.exception.code, CODE_ADJUSTMENTS_READ_FAILED)
        result = adapter(first_reality, mission)
        self.assertEqual(result.candidates[0]["boq_code"], BOQ)

    def test_queue_is_blank_when_not_authoritative(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(adapter, mission, scope_rows=[_scope_row()], plan_rows=[])
        self.assertEqual(adapter(reality, mission).candidates[0]["queue"], "")

    def test_domain_blocker_does_not_become_empty_success(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(adapter, mission, scope_rows=[_scope_row()], plan_rows=[])
        with patch(
            "agents.monthly_plan_constructor.real_data_assembler.build_constructor_proposal",
            return_value={
                "ok": False,
                "candidates": [],
                "errors": [{"code": "SCOPE_READ_FAILED", "message": "blocked"}],
                "human_issues": [],
                "counts": {},
            },
        ):
            with self.assertRaises(RealDataAssemblerError) as raised:
                adapter(reality, mission)
        self.assertEqual(raised.exception.code, CODE_DOMAIN_BLOCKER)

    def test_no_global_cache_across_instances(self) -> None:
        first = RealDataShadowAdapter()
        _capture(first, scope_rows=[_scope_row()], plan_rows=[])
        self.assertIsNone(RealDataShadowAdapter()._snapshot)

    def test_partial_existing_plan_reduces_available(self) -> None:
        """physical remaining 90, planned 30 → available 60."""
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(
            adapter,
            mission,
            scope_rows=[_scope_row()],
            plan_rows=[_plan_row(planned_qty=30.0)],
        )
        result = adapter(reality, mission)
        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(float(candidate["remaining_qty"]), 90.0)
        self.assertEqual(float(candidate["already_planned_qty"]), 30.0)
        self.assertEqual(float(candidate["available_to_add_qty"]), 60.0)

    def test_fully_planned_excluded_by_domain(self) -> None:
        """Domain excludes when existing plan exhausts available remainder."""
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(
            adapter,
            mission,
            scope_rows=[_scope_row()],
            plan_rows=[_plan_row(planned_qty=90.0)],
        )
        result = adapter(reality, mission)
        self.assertEqual(len(result.candidates), 0)
        self.assertGreaterEqual(result.already_planned_count, 1)

    def test_valid_empty_plan_keeps_prior_semantics(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        reality = _capture(adapter, mission, scope_rows=[_scope_row()], plan_rows=[])
        result = adapter(reality, mission)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(float(result.candidates[0]["already_planned_qty"]), 0.0)
        self.assertEqual(float(result.candidates[0]["available_to_add_qty"]), 90.0)
        self.assertEqual(result.already_planned_count, 0)

    def test_plan_read_failure_fails_closed(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        first_reality = _capture(
            adapter, mission, scope_rows=[_scope_row()], plan_rows=[]
        )
        with patch(
            SCOPE_PATCH,
            return_value=(pd.DataFrame([_scope_row(boq_code="BOQ-NEW")]), _ok_meta()),
        ), patch(
            ADJ_PATCH,
            return_value=(pd.DataFrame([_adj_row()]), _ok_meta()),
        ), patch(
            PLAN_PATCH,
            return_value=(
                pd.DataFrame(),
                {"error": "PLAN_READ_FAILED", "row_count": 0},
            ),
        ):
            with self.assertRaises(SecureReadError) as raised:
                read_constructor_reality(
                    _context(),
                    mission,
                    scope_reader=adapter.scope_reader,
                )
        self.assertEqual(raised.exception.code, CODE_PLAN_LINES_READ_FAILED)
        # Previous successful snapshot remains authoritative — not replaced by empty plan.
        result = adapter(first_reality, mission)
        self.assertEqual(result.candidates[0]["boq_code"], BOQ)
        self.assertEqual(float(result.candidates[0]["available_to_add_qty"]), 90.0)

    def test_plan_read_uses_trusted_capability_with_mission_month(self) -> None:
        adapter = RealDataShadowAdapter()
        mission = _mission()
        context = _context()
        with patch(
            SCOPE_PATCH,
            return_value=(pd.DataFrame([_scope_row()]), _ok_meta()),
        ) as scope_mock, patch(
            ADJ_PATCH,
            return_value=(pd.DataFrame([_adj_row()]), _ok_meta()),
        ), patch(
            PLAN_PATCH,
            return_value=(pd.DataFrame([_plan_row(planned_qty=15.0)]), _ok_meta()),
        ) as plan_mock:
            reality = read_constructor_reality(
                context,
                mission,
                scope_reader=adapter.scope_reader,
            )
        plan_mock.assert_called_once()
        args, kwargs = plan_mock.call_args
        self.assertIs(args[0], context)
        self.assertEqual(args[1], mission.month_key)
        result = adapter(reality, mission)
        self.assertEqual(float(result.candidates[0]["already_planned_qty"]), 15.0)
        self.assertEqual(float(result.candidates[0]["available_to_add_qty"]), 75.0)
        scope_mock.assert_called_once()

    def test_hardcoded_empty_plan_removed_from_assembly(self) -> None:
        source = ASSEMBLER_PATH.read_text(encoding="utf-8")
        self.assertIn("snapshot.plan_frame", source)
        self.assertIn(TRUSTED_PLAN_CAPABILITY, source)
        # Assembly must not pass a literal empty frame as the plan argument.
        self.assertNotIn(
            "build_constructor_proposal(\n"
            "            snapshot.scope_frame,\n"
            "            snapshot.adjustments_frame,\n"
            "            pd.DataFrame(),",
            source,
        )


if __name__ == "__main__":
    unittest.main()
